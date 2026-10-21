"""Show that the incremental fct_sales path handles changed inputs, not only unchanged ones.

verify_repeatability.py proves an unchanged input rebuilds identically. This script starts from a built warehouse,
copies it once per case, edits the raw POS table in the copy, runs fct_sales incrementally and compares it with
int_sales_enriched, which is what a full rebuild would load. Inside the lookback window every change must match;
outside it the incremental run is expected to miss the change until `--full-refresh`, which must then match.
"""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import duckdb

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'warehouse/bramblewood.duckdb'
# Raw rows of one parsed week, found through the row audit so legacy date formats and replays are included.
WEEK_ROWS = 'select _source_row from main.stg_pos_audit where parsed_week_ending = ?'
ACCEPTED = "select _source_row from main.stg_pos_audit where disposition = 'accepted'"


def dbt(database, target, *args):
    env = {**os.environ, 'BRAMBLEWOOD_DUCKDB': str(database)}
    command = [sys.executable, 'scripts/invoke_dbt.py', 'run', '-s', 'fct_sales', '--target-path', str(target), *args]
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def weeks(con):
    rows = con.execute('select distinct week_ending from main.fct_sales order by 1 desc').fetchall()
    return [r[0] for r in rows]


def mismatches(con):
    columns = ', '.join(
        r[0]
        for r in con.execute(
            "select column_name from information_schema.columns where table_name = 'fct_sales' order by ordinal_position"
        ).fetchall()
    )
    expected = f'select {columns} from main.int_sales_enriched'
    missing = con.execute(f'select count(*) from ({expected} except all select {columns} from main.fct_sales)')
    missing = missing.fetchone()[0]
    extra = con.execute(f'select count(*) from (select {columns} from main.fct_sales except all {expected})')
    return {'missing_from_fct_sales': missing, 'extra_in_fct_sales': extra.fetchone()[0]}


def change_units(con, week):
    row = con.execute(f'{ACCEPTED} and parsed_week_ending = ? and parsed_units > 0 order by 1 limit 1', [week])
    con.execute(
        'update raw.pos_weekly_sales set units = cast(cast(units as integer) + 1 as varchar) where _source_row = ?',
        [row.fetchone()[0]],
    )


def delete_some_rows(con, week):
    con.execute(
        f'delete from raw.pos_weekly_sales where _source_row in ({ACCEPTED} and parsed_week_ending = ? '
        'order by 1 limit 25)',
        [week],
    )


def delete_week(con, week):
    con.execute(f'delete from raw.pos_weekly_sales where _source_row in ({WEEK_ROWS})', [week])


def empty_target(con, week):
    con.execute('delete from main.fct_sales')


CASES = [
    # name, edit, which week (index from the latest), whether the change is inside the lookback window
    ('changed_amount_inside_window', change_units, 1, True),
    ('deleted_rows_inside_window', delete_some_rows, 1, True),
    ('deleted_week_inside_window', delete_week, 2, True),
    ('deleted_latest_week', delete_week, 0, True),
    ('empty_target', empty_target, 0, True),
    ('correction_outside_window', change_units, -1, False),
]


def run_case(work, name, edit, week_index, inside):
    # Views name the catalog after the file, so each copy keeps the file name in its own folder.
    (work / name).mkdir()
    database = work / name / BASE.name
    shutil.copy2(BASE, database)
    with duckdb.connect(str(database)) as con:
        edit(con, weeks(con)[week_index])
    dbt(database, work / 'target')
    with duckdb.connect(str(database), read_only=True) as con:
        incremental = mismatches(con)
    result = {'inside_lookback_window': inside, 'after_incremental_run': incremental}
    matched = not any(incremental.values())
    if inside and not matched:
        raise AssertionError(f'{name}: incremental run differs from a full rebuild: {incremental}')
    if not inside:
        if matched:
            raise AssertionError(f'{name}: a correction outside the window was not expected to load incrementally')
        dbt(database, work / 'target', '--full-refresh')
        with duckdb.connect(str(database), read_only=True) as con:
            result['after_full_refresh'] = mismatches(con)
        if any(result['after_full_refresh'].values()):
            raise AssertionError(f'{name}: full refresh differs from the source: {result["after_full_refresh"]}')
    database.unlink()
    return result


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='incremental-') as temporary:
        results = {name: run_case(Path(temporary), name, edit, index, inside) for name, edit, index, inside in CASES}
    (ROOT / 'evidence/incremental_changes.json').write_text(
        json.dumps({'status': 'pass', 'cases': results}, indent=2) + '\n', encoding='utf-8'
    )
    print(f'PASS: {len(results)} incremental change cases behave as documented')
