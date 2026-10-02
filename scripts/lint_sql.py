"""Run dbt-aware SQLFluff and preserve a portable UTF-8 JSON lint receipt."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [sys.executable, '-m', 'sqlfluff', 'lint', 'models', 'tests', 'analyses', '--format', 'json'],
    cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
)
(ROOT / 'evidence').mkdir(exist_ok=True)
(ROOT / 'evidence/sqlfluff.json').write_text(result.stdout, encoding='utf-8')
if result.stderr:
    print(result.stderr, file=sys.stderr)
print('SQLFluff passed' if result.returncode == 0 else 'SQLFluff failed; see evidence/sqlfluff.json')
sys.exit(result.returncode)
