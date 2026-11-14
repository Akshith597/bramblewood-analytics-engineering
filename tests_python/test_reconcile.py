"""The independent reconciliation on a small fixture: it must pass when the warehouse agrees and fail when not."""

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import duckdb

from scripts import independent_reconcile as rec

HEADER = 'store_nbr,upc,week_ending,units,gross_sales,promo_discount,net_sales\n'
RAW = (
    HEADER
    + '101,41230001146,2024-02-10,2,8.00,0.00,8.00\n'  # 11-digit UPC, ISO date
    + '101,041230001146,02/17/2024,-1,-4.00,0.00,-4.00\n'  # legacy date, a return
    + '101,41230001146,2024-02-10,2,8.00,0.00,8.00\n'  # exact replay of the first row
    + HEADER  # header embedded by the concatenated feed
    + '102,812450001342,2024-02-10,3,9.30,0.30,9.00\n'
)
FACT = [
    (101, '041230001146', date(2024, 2, 10), 2, Decimal('8.00')),
    (101, '041230001146', date(2024, 2, 17), -1, Decimal('-4.00')),
    (102, '812450001342', date(2024, 2, 10), 3, Decimal('9.00')),
]


class IndependentReconcileTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.csv = Path(temporary.name) / 'pos.csv'
        self.csv.write_text(RAW, encoding='utf-8')
        self.database = Path(temporary.name) / 'warehouse.duckdb'

    def build(self, fact=FACT, replays=(Decimal('8.00'),)):
        self.database.unlink(missing_ok=True)
        with duckdb.connect(str(self.database)) as con:
            con.execute(
                'create table fct_sales (store_id integer, upc varchar, week_ending date, units integer, '
                'net_sales decimal(18, 2))'
            )
            con.executemany('insert into fct_sales values (?, ?, ?, ?, ?)', fact)
            con.execute('create table stg_pos_audit (disposition varchar, parsed_net_sales decimal(18, 2))')
            for net_sales in replays:
                con.execute("insert into stg_pos_audit values ('exact_replay', ?)", [net_sales])

    def test_rebuild_pads_upcs_reads_both_date_formats_and_counts_exclusions(self):
        totals, excluded = rec.rebuild(self.csv)
        self.assertEqual(set(totals), {(s, u, w) for s, u, w, _, _ in FACT})
        self.assertEqual(
            totals[(101, '041230001146', date(2024, 2, 10))], {'rows': 1, 'units': 2, 'net_sales': Decimal('8.00')}
        )
        self.assertEqual(excluded, {'embedded_headers': 1, 'exact_replays': 1, 'replay_net_sales': Decimal('8.00')})

    def test_matching_warehouse_passes_with_exact_decimal_totals(self):
        self.build()
        receipt = rec.reconcile(self.csv, self.database)
        self.assertEqual(receipt['status'], 'pass')
        self.assertEqual((receipt['store_sku_weeks_reconciled'], receipt['store_weeks_reconciled']), (3, 3))
        self.assertEqual((receipt['accepted_rows'], receipt['net_sales']), (3, '13.00'))

    def test_one_cent_difference_on_one_key_fails(self):
        self.build(fact=FACT[:2] + [(102, '812450001342', date(2024, 2, 10), 3, Decimal('9.01'))])
        with self.assertRaisesRegex(AssertionError, 'failed for 1 keys'):
            rec.reconcile(self.csv, self.database)

    def test_offsetting_errors_inside_a_store_week_fail(self):
        # Two SKUs in one store-week, one a dollar high and one a dollar low: the store-week total still ties out.
        self.csv.write_text(RAW + '101,812450001342,2024-02-10,1,5.00,0.00,5.00\n', encoding='utf-8')
        self.build(
            fact=[
                (101, '041230001146', date(2024, 2, 10), 2, Decimal('9.00')),
                (101, '812450001342', date(2024, 2, 10), 1, Decimal('4.00')),
            ]
            + FACT[1:]
        )
        with self.assertRaisesRegex(AssertionError, 'failed for 2 keys'):
            rec.reconcile(self.csv, self.database)

    def test_a_row_missing_from_the_warehouse_fails(self):
        self.build(fact=FACT[:2])
        with self.assertRaisesRegex(AssertionError, 'reconciliation failed'):
            rec.reconcile(self.csv, self.database)

    def test_disagreeing_with_the_row_audit_about_replays_fails(self):
        self.build(replays=())
        with self.assertRaisesRegex(AssertionError, 'Replay rule disagrees'):
            rec.reconcile(self.csv, self.database)


if __name__ == '__main__':
    unittest.main()
