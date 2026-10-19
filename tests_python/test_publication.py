"""Publication failure boundaries with small filesystem fixtures; no warehouse dependencies."""
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import publish_warehouse as publisher


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project'
        self.raw = self.root / 'data/raw'
        self.raw.mkdir(parents=True)
        (self.raw / 'sales.csv').write_text('id,amount\n1,10\n', encoding='utf-8')
        self.destination = self.root / 'warehouse/published'
        self.manifest = publisher.make_manifest(self.root, publisher.utcnow().isoformat())

    @staticmethod
    def build_fixture(candidate):
        (candidate / 'warehouse').mkdir()
        # A sentinel file tests publication, not DuckDB correctness.
        (candidate / 'warehouse/bramblewood.duckdb').write_bytes((candidate / 'data/raw/sales.csv').read_bytes())
        (candidate / 'evidence').mkdir(exist_ok=True)
        (candidate / 'evidence/build.json').write_text('{"passed":true}', encoding='utf-8')

    def publish(self, manifest=None, builder=None):
        return publisher.publish(self.root, self.destination, manifest or self.manifest,
                                 builder=builder or self.build_fixture)

    def test_corrected_batch_creates_new_release_and_preserves_old_database(self):
        first = self.publish()
        old_database = self.destination / first['database']
        old_bytes = old_database.read_bytes()
        (self.raw / 'sales.csv').write_text('id,amount\n1,20\n', encoding='utf-8')
        second_manifest = publisher.make_manifest(self.root, publisher.utcnow().isoformat())
        second = self.publish(second_manifest)
        self.assertNotEqual(first['batch_id'], second['batch_id'])
        self.assertEqual(old_database.read_bytes(), old_bytes)
        self.assertNotEqual((self.destination / second['database']).read_bytes(), old_bytes)
        self.assertEqual(json.loads((self.destination / 'current.json').read_text())['release_id'], second['release_id'])
        self.assertEqual(publisher.check(self.destination, 24)['status'], 'fresh')

    def test_failed_build_keeps_previous_pointer(self):
        self.publish()
        before = (self.destination / 'current.json').read_bytes()
        def fail(candidate):
            raise subprocess.CalledProcessError(1, 'dbt build')
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish(builder=fail)
        self.assertEqual((self.destination / 'current.json').read_bytes(), before)
        self.assertFalse((self.destination / '.publisher.lock').exists())

    def test_snapshot_hash_mismatch_blocks_build(self):
        (self.raw / 'sales.csv').write_text('corrected', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'differ'):
            self.publish()
        self.assertFalse((self.destination / 'current.json').exists())

    def test_stale_and_future_batches_are_rejected(self):
        for age in (timedelta(hours=25), timedelta(hours=-1)):
            with self.subTest(age=age):
                manifest = publisher.make_manifest(self.root, (publisher.utcnow() - age).isoformat())
                with self.assertRaisesRegex(ValueError, 'freshness'):
                    self.publish(manifest)

    def test_source_change_during_snapshot_is_rejected(self):
        copy = publisher.shutil.copytree
        def altered_copy(source, target, *args, **kwargs):
            result = copy(source, target, *args, **kwargs)
            if source.name == 'data':
                (target / 'raw/sales.csv').write_text('changed', encoding='utf-8')
            return result
        with patch.object(publisher.shutil, 'copytree', side_effect=altered_copy):
            with self.assertRaisesRegex(ValueError, 'differ'):
                self.publish()

    def test_batch_expiring_during_build_does_not_publish(self):
        now = publisher.utcnow()
        def long_build(candidate):
            self.build_fixture(candidate)
        with patch.object(publisher, 'utcnow', side_effect=[now, now + timedelta(hours=25)]):
            with self.assertRaisesRegex(ValueError, 'freshness'):
                self.publish(builder=long_build)

    def test_pointer_swap_failure_preserves_current_release(self):
        self.publish()
        before = (self.destination / 'current.json').read_bytes()
        replace = publisher.os.replace
        def fail_pointer(source, target):
            if target.name == 'current.json':
                raise PermissionError('pointer busy')
            return replace(source, target)
        with patch.object(publisher.os, 'replace', side_effect=fail_pointer):
            with self.assertRaises(PermissionError):
                self.publish()
        self.assertEqual((self.destination / 'current.json').read_bytes(), before)

    def test_concurrent_publisher_is_refused_without_removing_its_lock(self):
        self.destination.mkdir(parents=True)
        lock = self.destination / '.publisher.lock'
        lock.mkdir()
        with self.assertRaises(FileExistsError):
            self.publish()
        self.assertTrue(lock.exists())

    def test_check_detects_age_after_publication(self):
        self.publish()
        with patch.object(publisher, 'utcnow', return_value=publisher.utcnow() + timedelta(hours=25)):
            with self.assertRaisesRegex(ValueError, 'freshness'):
                publisher.check(self.destination, 24)

    def test_invalid_threshold_and_naive_timestamp_rejected(self):
        for threshold in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                publisher.validate_freshness(self.manifest, threshold)
        with self.assertRaises(ValueError):
            publisher.make_manifest(self.root, '2026-10-18T12:00:00')

    def test_real_subprocess_failure_is_not_published(self):
        scripts = self.root / 'scripts'
        scripts.mkdir()
        (scripts / 'run_all.py').write_text('raise SystemExit(2)\n', encoding='utf-8')
        with self.assertRaises(subprocess.CalledProcessError):
            publisher.publish(self.root, self.destination, self.manifest)
        self.assertFalse((self.destination / 'current.json').exists())


if __name__ == '__main__':
    unittest.main()
