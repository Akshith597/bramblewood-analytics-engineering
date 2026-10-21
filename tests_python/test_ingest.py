"""Raw-load guards with small fixture extracts; no warehouse dependencies."""
from pathlib import Path
import tempfile
import unittest

import duckdb
import pandas as pd

from scripts import ingest


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / 'raw'
        self.source.mkdir()
        self.warehouse = Path(self.temporary.name) / 'warehouse'

    def write_workbook(self, *sheets):
        with pd.ExcelWriter(self.source / 'merch.xlsx') as writer:
            for sheet in sheets:
                pd.DataFrame({'id': ['1']}).to_excel(writer, sheet_name=sheet, index=False)

    def test_sheet_and_csv_with_the_same_table_name_are_rejected_before_loading(self):
        (self.source / 'inventory.csv').write_text('id\n1\n', encoding='utf-8')
        self.write_workbook('Inventory', 'items')
        with self.assertRaisesRegex(ValueError, 'inventory.csv and merch.xlsx|merch.xlsx and inventory.csv'):
            ingest.main(self.source, self.warehouse)
        self.assertFalse((self.warehouse / 'bramblewood.duckdb').exists())

    def test_distinct_names_load_with_lineage(self):
        (self.source / 'sales.csv').write_text('id,amount\n1,10\n2,20\n', encoding='utf-8')
        self.write_workbook('items')
        ingest.main(self.source, self.warehouse)
        with duckdb.connect(str(self.warehouse / 'bramblewood.duckdb'), read_only=True) as con:
            self.assertEqual(con.execute('select max(_source_row) from raw.sales').fetchone()[0], 3)
            self.assertEqual(con.execute('select count(*) from raw._load_log').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
