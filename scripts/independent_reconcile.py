"""Independent Decimal/Python check against raw CSV; does not reuse dbt cleaning SQL."""

from pathlib import Path
from decimal import Decimal
from datetime import datetime
from collections import defaultdict
import csv
import json
import duckdb

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    totals = defaultdict(lambda: {'rows': 0, 'units': 0, 'net_sales': Decimal('0.00')})
    seen = set()
    headers = 0
    replays = 0
    for row in csv.DictReader((ROOT / 'data/raw/pos_weekly_sales.csv').open(newline='', encoding='utf-8')):
        if row['store_nbr'] == 'store_nbr':
            headers += 1
            continue
        values = tuple(row.values())
        if values in seen:
            replays += 1
            continue
        seen.add(values)
        date = datetime.strptime(row['week_ending'], '%m/%d/%Y' if '/' in row['week_ending'] else '%Y-%m-%d').date()
        key = (int(row['store_nbr']), date)
        totals[key]['rows'] += 1
        totals[key]['units'] += int(row['units'])
        totals[key]['net_sales'] += Decimal(row['net_sales'])
    with duckdb.connect(str(ROOT / 'warehouse/bramblewood.duckdb'), read_only=True) as con:
        modeled = {
            (s, d): {'rows': n, 'units': u, 'net_sales': v}
            for s, d, n, u, v in con.execute(
                'select store_id, week_ending, count(*), sum(units), sum(net_sales) from fct_sales group by 1,2'
            ).fetchall()
        }
    if dict(totals) != modeled:
        raise AssertionError('Independent store-week reconciliation failed')
    receipt = {
        'status': 'pass',
        'store_weeks_reconciled': len(totals),
        'accepted_rows': len(seen),
        'embedded_headers': headers,
        'exact_replays': replays,
        'net_sales': str(sum(v['net_sales'] for v in totals.values())),
        'method': 'Python csv + Decimal compared to every dbt store-week total',
    }
    (ROOT / 'evidence/independent_reconciliation.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))
