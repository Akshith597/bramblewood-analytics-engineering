"""Prevent stale warehouse objects from masking removed-model references."""
import unittest

from scripts.export_evidence import referenced_models


class EvidenceReferencesTest(unittest.TestCase):
    def test_using_join_needs_no_warehouse_binding(self):
        self.assertEqual(
            referenced_models('select * from mart_forecast_accuracy join dim_week using (week_key)'),
            {'mart_forecast_accuracy', 'dim_week'},
        )

    def test_cte_alias_is_not_a_physical_model(self):
        self.assertEqual(
            referenced_models('with totals as (select * from removed_model) select * from totals'),
            {'removed_model'},
        )


if __name__ == '__main__':
    unittest.main()
