"""Compile the project for the optional Snowflake target without an account, and check the result is Snowflake SQL.

What this proves: every model except fct_sales renders for the Snowflake adapter, the adapter-dispatched macros
resolve to their Snowflake implementations, and each compiled statement parses under sqlglot's Snowflake grammar.

What it does not prove: that the SQL runs or returns the same rows on Snowflake. Nothing here connects to an
account. fct_sales is left out because `is_incremental()` has to ask the warehouse whether the table exists.

Needs requirements-snowflake.txt (dbt-snowflake), which the DuckDB build does not install.
"""

from pathlib import Path
import os
import subprocess
import sys

import sqlglot

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'target/snowflake'
# Models that need a live connection to compile, and why.
NEEDS_CONNECTION = {'fct_sales': 'is_incremental() looks the target table up in the warehouse'}
# DuckDB-only functions the dispatched macros replace; none may survive in Snowflake output.
DUCKDB_ONLY = ('try_strptime', 'regexp_full_match')
# Each dispatched Snowflake implementation and a model that must contain it.
DISPATCHED = {'try_to_date': 'stg_pos_audit', 'regexp_like': 'stg_pos_audit'}


def compile_for_snowflake():
    # The profile requires these two; any value works because nothing connects.
    env = {**os.environ}
    env.setdefault('SNOWFLAKE_ACCOUNT', 'offline-compile-check')
    env.setdefault('SNOWFLAKE_USER', 'offline-compile-check')
    command = [
        sys.executable,
        'scripts/invoke_dbt.py',
        'compile',
        '--target',
        'snowflake',
        '--no-introspect',
        '--no-populate-cache',
        '--target-path',
        str(TARGET),
    ]
    for model in NEEDS_CONNECTION:
        command += ['--exclude', model]
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def check_compiled(models_dir, expected):
    """Return the problems found in a folder of compiled model SQL (empty when it is clean)."""
    compiled = {
        path.stem: path.read_text(encoding='utf-8')
        for path in sorted(models_dir.rglob('*.sql'))
        if path.parent.suffix != '.yml'
    }
    problems = [f'{name} was not compiled' for name in sorted(expected - compiled.keys())]
    for name, sql in compiled.items():
        lowered = sql.lower()
        problems += [f'{name} still calls DuckDB-only {fn}()' for fn in DUCKDB_ONLY if fn + '(' in lowered]
        try:
            sqlglot.parse_one(sql, read='snowflake')
        except sqlglot.errors.SqlglotError as error:
            problems.append(f'{name} does not parse as Snowflake SQL: {str(error).splitlines()[0]}')
    for fn, model in DISPATCHED.items():
        if fn + '(' not in compiled.get(model, '').lower():
            problems.append(f'{model} does not use the Snowflake implementation {fn}()')
    return problems


def project_models():
    return {path.stem for path in (ROOT / 'models').rglob('*.sql')} - NEEDS_CONNECTION.keys()


def main():
    compile_for_snowflake()
    expected = project_models()
    problems = check_compiled(TARGET / 'compiled/bramblewood/models', expected)
    if problems:
        raise AssertionError('\n'.join(problems))
    skipped = ', '.join(f'{name} ({reason})' for name, reason in NEEDS_CONNECTION.items())
    print(
        f'PASS: {len(expected)} models compile for Snowflake and parse as Snowflake SQL. Not compiled: {skipped}. '
        'Nothing was executed against an account.'
    )


if __name__ == '__main__':
    main()
