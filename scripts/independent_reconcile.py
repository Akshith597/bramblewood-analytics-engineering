"""Independent Decimal/Python check against the raw POS CSV; does not reuse the dbt cleaning SQL.

The raw file is re-read with Python's csv module and summed with Decimal at store x UPC x week, the grain of
fct_sales, and every key must match the warehouse exactly. The replay rule (drop a row that repeats an earlier row
field for field) is written again here instead of imported, and the rows it drops must equal, in count and in
dollars, what the warehouse's own row audit labels `exact_replay`. So a disagreement about which rows are replays
fails here even when the accepted totals happen to agree.
"""

from pathlib import Path
from decimal import Decimal
from datetime import datetime
from collections import defaultdict
import csv
import json
import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW_POS = ROOT / 'data/raw/pos_weekly_sales.csv'
WAREHOUSE = ROOT / 'warehouse/bramblewood.duckdb'


def parse_week(text):
    """The extract mixes ISO dates with the legacy feed's US dates."""
    return datetime.strptime(text, '%m/%d/%Y' if '/' in text else '%Y-%m-%d').date()


def rebuild(csv_path):
    """Sum the raw POS file by store, 12-digit UPC and week, counting the header and replay rows it leaves out."""
    totals = defaultdict(lambda: {'rows': 0, 'units': 0, 'net_sales': Decimal('0.00')})
    seen = set()
    excluded = {'embedded_headers': 0, 'exact_replays': 0, 'replay_net_sales': Decimal('0.00')}
    with Path(csv_path).open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['store_nbr'] == 'store_nbr':
                excluded['embedded_headers'] += 1
                continue
            values = tuple(row.values())
            if values in seen:
                excluded['exact_replays'] += 1
                excluded['replay_net_sales'] += Decimal(row['net_sales'])
                continue
            seen.add(values)
            key = (int(row['store_nbr']), row['upc'].strip().zfill(12), parse_week(row['week_ending']))
            totals[key]['rows'] += 1
            totals[key]['units'] += int(row['units'])
            totals[key]['net_sales'] += Decimal(row['net_sales'])
    return dict(totals), excluded


def modeled(database):
    """The warehouse's sales at the same grain, and what its row audit says it excluded as replays."""
    with duckdb.connect(str(database), read_only=True) as con:
        sales = {
            (store, upc, week): {'rows': rows, 'units': units, 'net_sales': net_sales}
            for store, upc, week, rows, units, net_sales in con.execute(
                'select store_id, upc, week_ending, count(*), sum(units), sum(net_sales) from fct_sales group by 1, 2, 3'
            ).fetchall()
        }
        replays = con.execute(
            "select count(*), coalesce(sum(parsed_net_sales), 0) from stg_pos_audit where disposition = 'exact_replay'"
        ).fetchone()
    return sales, {'exact_replays': replays[0], 'replay_net_sales': replays[1]}


def roll_up(totals):
    """Store-week totals, the grain the receipt has always reported."""
    weeks = defaultdict(lambda: {'rows': 0, 'units': 0, 'net_sales': Decimal('0.00')})
    for (store, _upc, week), measures in totals.items():
        for name, value in measures.items():
            weeks[(store, week)][name] += value
    return dict(weeks)


def reconcile(csv_path=RAW_POS, database=WAREHOUSE):
    totals, excluded = rebuild(csv_path)
    sales, audited = modeled(database)
    if totals != sales:
        differing = sorted(key for key in totals.keys() | sales.keys() if totals.get(key) != sales.get(key))
        raise AssertionError(
            f'Independent store-SKU-week reconciliation failed for {len(differing)} keys, first: {differing[:5]}'
        )
    for name, value in audited.items():
        if excluded[name] != value:
            raise AssertionError(f'Replay rule disagrees with the row audit on {name}: {excluded[name]} vs {value}')
    return {
        'status': 'pass',
        'store_sku_weeks_reconciled': len(totals),
        'store_weeks_reconciled': len(roll_up(totals)),
        'accepted_rows': sum(v['rows'] for v in totals.values()),
        'embedded_headers': excluded['embedded_headers'],
        'exact_replays': excluded['exact_replays'],
        'replay_net_sales': str(excluded['replay_net_sales']),
        'net_sales': str(sum(v['net_sales'] for v in totals.values())),
        'method': 'Python csv + Decimal compared to every dbt store-SKU-week total; replays compared to the row audit',
    }


def main():
    receipt = reconcile()
    (ROOT / 'evidence/independent_reconciliation.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
