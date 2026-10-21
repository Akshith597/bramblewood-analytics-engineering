"""Failure-and-recovery drill for the publication workflow; runs weekly on GitHub Actions.

It exercises the real publisher end to end, with full warehouse builds, in a throwaway destination:

1. publish a release and confirm the `check` monitor passes;
2. an incident the monitor must catch: the published source is older than a tight age limit;
3. a bad delivery that must be refused: a source file changes after its manifest was recorded, and the release
   pointer must not move;
4. recovery: a fresh manifest for the restored files publishes a new release that carries snapshot history forward,
   the monitor passes again, and the earlier release is left untouched.

Any outcome other than the expected one exits nonzero. This is a drill on CI runners, not a production deployment.
"""

from pathlib import Path
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import publish_warehouse as publisher  # noqa: E402

# Overridable because Windows path limits break dbt package installs inside a deeply nested build folder.
DESTINATION = Path(os.environ.get('RECOVERY_DRILL_DESTINATION', ROOT / 'warehouse/drill'))
TAMPERED = ROOT / 'data/raw/store_inventory_weekly.csv'


def expect_failure(action, message):
    try:
        action()
    except ValueError as error:
        if message not in str(error):
            raise AssertionError(f'Failed for the wrong reason: {error}') from error
        return str(error)
    raise AssertionError(f'Expected a failure containing "{message}"')


def current_release():
    return json.loads((DESTINATION / 'current.json').read_text(encoding='utf-8'))['release_id']


def main():
    shutil.rmtree(DESTINATION, ignore_errors=True)
    steps = {}

    manifest = publisher.make_manifest(ROOT, publisher.utcnow().isoformat())
    first = publisher.publish(ROOT, DESTINATION, manifest)
    steps['1_publish'] = {'release_id': first['release_id'], 'check': publisher.check(DESTINATION, 24)}

    steps['2_stale_source_detected'] = {
        'error': expect_failure(lambda: publisher.check(DESTINATION, 1 / 3600), 'freshness'),
        'max_source_age_hours': 1 / 3600,
    }

    original = TAMPERED.read_bytes()
    try:
        TAMPERED.write_bytes(original + b'\n')
        error = expect_failure(lambda: publisher.publish(ROOT, DESTINATION, manifest), 'differ')
    finally:
        TAMPERED.write_bytes(original)
    if current_release() != first['release_id']:
        raise AssertionError('A refused batch moved the release pointer')
    steps['3_tampered_batch_refused'] = {'error': error, 'pointer_unchanged': True}

    fresh = publisher.make_manifest(ROOT, publisher.utcnow().isoformat())
    second = publisher.publish(ROOT, DESTINATION, fresh)
    if not second['snapshot_history_carried']:
        raise AssertionError('Recovery release did not carry snapshot history')
    first_database = DESTINATION / first['database']
    if publisher.digest(first_database) != first['database_sha256']:
        raise AssertionError('Recovery changed the earlier release')
    steps['4_recovered'] = {
        'release_id': second['release_id'],
        'check': publisher.check(DESTINATION, 24),
        'snapshot_history_carried': second['snapshot_history_carried'],
        'previous_release_intact': True,
    }

    (ROOT / 'target').mkdir(exist_ok=True)
    (ROOT / 'target/recovery_drill.json').write_text(
        json.dumps({'status': 'pass', 'steps': steps}, indent=2) + '\n', encoding='utf-8'
    )
    print('PASS: publish, stale-source detection, tampered-batch refusal and recovery behaved as expected')


if __name__ == '__main__':
    main()
