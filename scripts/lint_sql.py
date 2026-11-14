"""Run dbt-aware SQLFluff and keep a reproducible JSON lint receipt."""

from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATHS = ('models', 'tests', 'analyses')


def lint_receipt(report):
    """Keep each linted file and its violations; drop the per-rule timings, which differ on every run."""
    return sorted(
        ({'filepath': Path(f['filepath']).as_posix(), 'violations': f['violations']} for f in report),
        key=lambda f: f['filepath'],
    )


def main():
    result = subprocess.run(
        [sys.executable, '-m', 'sqlfluff', 'lint', *PATHS, '--format', 'json'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    try:
        receipt = lint_receipt(json.loads(result.stdout))
    except json.JSONDecodeError:
        # SQLFluff could not produce a report at all (for example, the dbt project failed to compile).
        print(result.stdout, file=sys.stderr)
        return result.returncode or 1
    (ROOT / 'evidence').mkdir(exist_ok=True)
    (ROOT / 'evidence/sqlfluff.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print('SQLFluff passed' if result.returncode == 0 else 'SQLFluff failed; see evidence/sqlfluff.json')
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
