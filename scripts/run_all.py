"""Fail-fast local/CI build. Rebuilds all bounded historical data deterministically."""

from pathlib import Path
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
for args in [
    ("scripts/invoke_dbt.py", "deps"),
    ("scripts/ingest.py",),
    ("scripts/invoke_dbt.py", "source", "freshness"),
    ("scripts/invoke_dbt.py", "build"),
    ("scripts/verify_project.py",),
    ("scripts/independent_reconcile.py",),
    ("scripts/invoke_dbt.py", "docs", "generate"),
    ("scripts/export_evidence.py",),
    ("scripts/build_insights.py",),
]:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
    if args == ("scripts/invoke_dbt.py", "build"):
        (ROOT / 'evidence').mkdir(exist_ok=True)
        receipt = json.loads((ROOT / 'target/run_results.json').read_text(encoding='utf-8'))
        # Keep executed results; remove local machine paths from the portable copy.
        for key in ('project_dir', 'profiles_dir', 'log_path'):
            if key in receipt.get('args', {}):
                receipt['args'][key] = '<project-root>' + ('/logs' if key == 'log_path' else '')
        (ROOT / 'evidence/dbt_build_results.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
