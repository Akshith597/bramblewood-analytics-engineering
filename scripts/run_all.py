"""Fail-fast local/CI build. Rebuilds all bounded historical data deterministically."""

from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DBT_BUILD = ("scripts/invoke_dbt.py", "build")
STEPS = [
    ("scripts/invoke_dbt.py", "deps"),
    ("scripts/ingest.py",),
    ("scripts/invoke_dbt.py", "source", "freshness"),
    DBT_BUILD,
    ("scripts/verify_project.py",),
    ("scripts/independent_reconcile.py",),
    ("scripts/invoke_dbt.py", "docs", "generate"),
    ("scripts/export_evidence.py",),
    ("scripts/build_insights.py",),
]


def build_receipt(run_results):
    """Reduce dbt's run_results.json to what a build proves: which nodes ran and how each one ended.

    Timestamps, durations, thread names, the invocation id and machine paths differ on every run, so they are left
    out. That makes the committed receipt reproducible, and CI fails when it differs from a fresh build. The complete
    run_results.json is uploaded with each CI run.
    """
    return {
        'metadata': {
            'dbt_version': run_results['metadata']['dbt_version'],
            'dbt_schema_version': run_results['metadata']['dbt_schema_version'],
        },
        'results': sorted(
            (
                {'unique_id': r['unique_id'], 'status': r['status'], 'failures': r['failures'], 'message': r['message']}
                for r in run_results['results']
            ),
            key=lambda r: r['unique_id'],
        ),
    }


def write_build_receipt(root=ROOT):
    run_results = json.loads((root / 'target/run_results.json').read_text(encoding='utf-8'))
    (root / 'evidence').mkdir(exist_ok=True)
    (root / 'evidence/dbt_build_results.json').write_text(
        json.dumps(build_receipt(run_results), indent=2) + '\n', encoding='utf-8'
    )


def main():
    for args in STEPS:
        subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
        if args == DBT_BUILD:
            write_build_receipt()


if __name__ == '__main__':
    main()
