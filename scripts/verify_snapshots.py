"""Show that the Type 2 snapshots record history, not only the first load.

A normal build snapshots an unchanged master, so every key has exactly one version and the Type 2 logic is never
exercised. This script copies the built warehouse, edits the raw masters in the copy, runs `dbt snapshot` and checks
the versions that result:

- a changed item attribute closes the old version and opens a new one at the same instant;
- a re-sorted item master (new extract row numbers, same attributes) adds no versions;
- a store removed from the master has its version closed, not deleted;
- every other key keeps its single open version.
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
NEW_DESCRIPTION = 'Snapshot check: renamed item'


def snapshot(database, target):
    env = {**os.environ, 'BRAMBLEWOOD_DUCKDB': str(database)}
    command = [sys.executable, 'scripts/invoke_dbt.py', 'snapshot', '--target-path', str(target)]
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def versions(con, table, key):
    """Each key's versions in order: (key, is_current, closes exactly when the next version opens)."""
    return con.execute(
        f"""
        select
            {key},
            count(*) as versions,
            count(*) filter (where dbt_valid_to is null) as open_versions,
            count(*) filter (where dbt_valid_to is not null and dbt_valid_to = next_from) as handed_over
        from (
            select *, lead(dbt_valid_from) over (partition by {key} order by dbt_valid_from) as next_from
            from main_snapshots.{table}
        )
        group by {key}
        order by {key}
        """
    ).fetchall()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def verify(work):
    # Views name the catalog after the file, so the copy keeps the file name in its own folder.
    database = work / BASE.name
    shutil.copy2(BASE, database)
    with duckdb.connect(str(database)) as con:
        items_before = versions(con, 'snap_items', 'sku_id')
        stores_before = versions(con, 'snap_stores', 'store_id')
        check(
            all(tuple(v) == (1, 1, 0) for _, *v in items_before + stores_before),
            'Expected one open version per key before any change; run a clean build first',
        )
        sku = items_before[0][0]
        store = stores_before[-1][0]
        con.execute('update raw.items set description = ? where sku_id = ?', [NEW_DESCRIPTION, sku])
        # A re-sorted extract: every row number changes, no attribute does.
        con.execute('update raw.items set _source_row = _source_row + 1000')
        con.execute('delete from raw.stores where store_id = ?', [store])
    snapshot(database, work / 'target')
    with duckdb.connect(str(database), read_only=True) as con:
        items = {key: tuple(v) for key, *v in versions(con, 'snap_items', 'sku_id')}
        stores = {key: tuple(v) for key, *v in versions(con, 'snap_stores', 'store_id')}
        current = con.execute(
            'select description from main_snapshots.snap_items where sku_id = ? and dbt_valid_to is null', [sku]
        ).fetchall()
        closed = con.execute(
            'select count(*) from main_snapshots.snap_items '
            'where sku_id = ? and dbt_valid_to is not null and description != ?',
            [sku, NEW_DESCRIPTION],
        ).fetchone()[0]
    check(items[sku] == (2, 1, 1), f'Changed item {sku} should have a closed and an open version: {items[sku]}')
    check(current == [(NEW_DESCRIPTION,)], f'Open version of {sku} should carry the new attribute: {current}')
    check(closed == 1, f'Closed version of {sku} should keep the old attribute')
    unchanged = [key for key, v in items.items() if key != sku and v != (1, 1, 0)]
    check(not unchanged, f'Re-sorting the item master created versions for unchanged items: {unchanged[:5]}')
    check(stores[store] == (1, 0, 0), f'Removed store {store} should keep one closed version: {stores[store]}')
    others = [key for key, v in stores.items() if key != store and v != (1, 1, 0)]
    check(not others, f'Unchanged stores gained or lost versions: {others[:5]}')
    return {
        'status': 'pass',
        'cases': {
            'changed_item_attribute': {'versions': 2, 'open_versions': 1, 'old_version_closed_at_new_start': True},
            'resorted_item_master': {'items_checked': len(items) - 1, 'new_versions': 0},
            'removed_store': {'versions': 1, 'open_versions': 0},
            'unchanged_stores': {'stores_checked': len(stores) - 1, 'new_versions': 0},
        },
    }


def main():
    with tempfile.TemporaryDirectory(prefix='snapshots-') as temporary:
        receipt = verify(Path(temporary))
    (ROOT / 'evidence/snapshot_history.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print('PASS: Type 2 snapshots version a changed item, ignore a re-sort and close a removed store')


if __name__ == '__main__':
    main()
