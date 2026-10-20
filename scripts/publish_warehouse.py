"""Local batch publication: immutable candidate build, freshness gate, atomic pointer.

Consumers read current.json once, then open that release's database read-only.
Only the pointer changes; an existing published database is never overwritten.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
COPY_DIRS = ('data', 'models', 'macros', 'tests', 'scripts', 'analyses', 'analysis', 'docs', 'evidence')


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('Extraction timestamps must include a UTC offset')
    return parsed.astimezone(timezone.utc)


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def sources(root):
    files = sorted(p for p in (root / 'data/raw').iterdir() if p.suffix in ('.csv', '.xlsx'))
    if not files:
        raise ValueError('No source extracts found')
    return {p.name: digest(p) for p in files}


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def make_manifest(root, extracted_at):
    """Call only when a source owner delivers a batch; never infer age from mtime."""
    extracted = timestamp(extracted_at).isoformat()
    return {'files': {name: {'sha256': sha, 'extracted_at_utc': extracted} for name, sha in sources(root).items()}}


def validate_freshness(manifest, max_age_hours, now=None):
    now = now or utcnow()
    if not math.isfinite(max_age_hours) or max_age_hours <= 0:
        raise ValueError('Maximum source age must be finite and positive')
    if not manifest.get('files'):
        raise ValueError('Source manifest is empty')
    ages = {}
    for name, meta in manifest['files'].items():
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Manifest file names must be basenames')
        age = (now - timestamp(meta['extracted_at_utc'])).total_seconds() / 3600
        if age < 0 or age > max_age_hours:
            raise ValueError(f'Source freshness failed: {name}, age {age:.2f} hours')
        ages[name] = age
    return ages


def verify_snapshot(root, manifest):
    expected = {name: meta['sha256'] for name, meta in manifest['files'].items()}
    if sources(root) != expected:
        raise ValueError('Source files differ from the batch manifest; publication rejected')


def build(candidate):
    for script in ('run_all.py', 'verify_repeatability.py'):
        subprocess.run([sys.executable, str(candidate / 'scripts' / script)], cwd=candidate, check=True)


def publish(root, destination, manifest, max_age_hours=24, builder=None):
    root, destination = root.resolve(), destination.resolve()
    # Keep output away from copied source directories, including custom destinations.
    if destination == root or any(destination.is_relative_to(root / d) for d in COPY_DIRS):
        raise ValueError('Publication destination cannot be inside a copied source directory')
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / '.publisher.lock'
    lock.mkdir()  # Refuse concurrent publishers; do not steal a stale lock automatically.
    run_id = uuid.uuid4().hex
    try:
        validate_freshness(manifest, max_age_hours)
        verify_snapshot(root, manifest)
        with tempfile.TemporaryDirectory(prefix='.build-', dir=destination) as temporary:
            candidate = Path(temporary)
            for name in COPY_DIRS:
                if (root / name).exists():
                    shutil.copytree(
                        root / name, candidate / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc')
                    )
            for source in root.iterdir():
                if source.is_file() and source.suffix in ('.yml', '.yaml', '.txt'):
                    shutil.copy2(source, candidate / source.name)
            verify_snapshot(candidate, manifest)
            (builder or build)(candidate)
            # Reject a batch that expired during a long build, or was altered by a build step.
            ages = validate_freshness(manifest, max_age_hours)
            verify_snapshot(candidate, manifest)
            database = candidate / 'warehouse/bramblewood.duckdb'
            if not database.is_file() or database.stat().st_size == 0:
                raise ValueError('Validated build did not produce a database')
            release = destination / 'releases' / run_id
            release.mkdir(parents=True)
            shutil.copy2(database, release / 'bramblewood.duckdb')
            shutil.copytree(candidate / 'evidence', release / 'evidence')
            batch_id = hashlib.sha256(json.dumps(manifest['files'], sort_keys=True).encode()).hexdigest()
            receipt = {
                'release_id': run_id,
                'batch_id': batch_id,
                'published_at_utc': utcnow().isoformat(),
                'database': f'releases/{run_id}/bramblewood.duckdb',
                'source_manifest': manifest,
                'source_age_hours_at_publish': ages,
                'database_sha256': digest(release / 'bramblewood.duckdb'),
            }
            atomic_json(release / 'release.json', receipt)
            atomic_json(destination / 'current.json', receipt)
            return receipt
    finally:
        lock.rmdir()


def check(destination, max_age_hours):
    receipt = json.loads((destination / 'current.json').read_text(encoding='utf-8'))
    validate_freshness(receipt['source_manifest'], max_age_hours)
    database = (destination / receipt['database']).resolve()
    if not database.is_relative_to((destination / 'releases').resolve()) or not database.is_file():
        raise ValueError('Published database is missing or outside releases')
    return {'status': 'fresh', 'release_id': receipt['release_id']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    manifest_parser = sub.add_parser('manifest', help='Record a newly delivered source batch')
    manifest_parser.add_argument('--extracted-at', required=True, help='Actual extraction time with timezone')
    manifest_parser.add_argument('--output', required=True, type=Path)
    for name in ('publish', 'check'):
        command = sub.add_parser(name)
        command.add_argument('--destination', type=Path, default=ROOT / 'warehouse/published')
        command.add_argument('--max-source-age-hours', type=float, default=24)
        if name == 'publish':
            command.add_argument('--source-manifest', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'manifest':
            atomic_json(args.output, make_manifest(ROOT, args.extracted_at))
            result = {'status': 'manifest_created', 'path': str(args.output)}
        elif args.command == 'publish':
            manifest = json.loads(args.source_manifest.read_text(encoding='utf-8'))
            result = publish(ROOT, args.destination, manifest, args.max_source_age_hours)
        else:
            result = check(args.destination, args.max_source_age_hours)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
