"""Exercise the delivered macros on edge cases independently of the data extract."""
from pathlib import Path
import unittest

import duckdb
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]


class MacroGuards(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect()
        self.addCleanup(self.con.close)

    def overlap_query(self):
        template = (ROOT / 'macros/tests/no_overlapping_periods.sql').read_text()
        # dbt's test block is a named Jinja macro; adapt the two block tags for plain Jinja.
        template = template.replace('{% test ', '{% macro ').replace('{% endtest %}', '{% endmacro %}')
        macro = Environment().from_string(template).module.no_overlapping_periods
        return macro('period_fixture', ['sku_id'], 'effective_start', 'effective_end')

    def test_upc_padding_retains_existing_twelve_digit_key(self):
        macro = Environment().from_string((ROOT / 'macros/normalize_upc.sql').read_text()).module.normalize_upc
        padded = self.con.execute('select ' + macro("'41230001146'")).fetchone()[0]
        unchanged = self.con.execute('select ' + macro("'812450001342'")).fetchone()[0]
        self.assertEqual(padded, '041230001146')
        self.assertEqual(unchanged, '812450001342')

    def create_fixture(self, rows):
        self.con.execute('create table period_fixture(sku_id varchar, effective_start date, effective_end date)')
        self.con.executemany('insert into period_fixture values (?, ?, ?)', rows)

    def test_adjacent_nonoverlapping_and_different_partitions(self):
        self.create_fixture([('A', '2025-01-01', '2025-01-07'), ('A', '2025-01-08', None),
                             ('B', '2025-01-01', None)])
        self.assertEqual(self.con.execute(self.overlap_query()).fetchall(), [])

    def test_inclusive_touching_boundary_is_overlap(self):
        self.create_fixture([('A', '2025-01-01', '2025-01-08'), ('A', '2025-01-08', None)])
        self.assertEqual(len(self.con.execute(self.overlap_query()).fetchall()), 1)

    def test_identical_open_intervals_are_not_hidden(self):
        self.create_fixture([('A', '2025-01-01', None), ('A', '2025-01-01', None)])
        self.assertEqual(len(self.con.execute(self.overlap_query()).fetchall()), 1)


if __name__ == '__main__':
    unittest.main()
