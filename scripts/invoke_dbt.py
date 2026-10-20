"""Portable dbt invocation using the currently active Python environment."""

import os
import sys
from pathlib import Path
from dbt.cli.main import dbtRunner

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ.setdefault("DBT_SEND_ANONYMOUS_USAGE_STATS", "false")
result = dbtRunner().invoke(sys.argv[1:] + ["--profiles-dir", str(ROOT)])
if not result.success:
    if result.exception:
        print(result.exception, file=sys.stderr)
    sys.exit(1)
