"""Hand-checkable cases for the pure calculations inside the business analyses (no warehouse needed).

The estimators have their own simulation tests (test_fe.py) and an independent R cross-check. These cover the
arithmetic around them: accuracy metrics, censored-demand tails, the stock-flow identity, cut selection, the price
lever and the inventory replay. Each expected value can be worked out on paper.
"""

import math
import unittest

import numpy as np

from business_analysis import assortment, forecast, inventory_sim, physical, plan, stockouts
from business_analysis.common import pct_effect, round_floats


class CommonTest(unittest.TestCase):
    def test_log_points_convert_to_percent_effects(self):
        self.assertEqual(pct_effect(0.0), 0.0)
        self.assertAlmostEqual(pct_effect(math.log(1.25)), 0.25)
        self.assertAlmostEqual(pct_effect(math.log(0.8)), -0.2)

    def test_rounding_keeps_six_significant_figures_at_every_depth(self):
        rounded = round_floats({'a': 1234.56789, 'b': [0.000123456789, (2, 3.0)], 'c': 'text', 4: 0.0})
        self.assertEqual(rounded, {'a': 1234.57, 'b': [0.000123457, [2, 3.0]], 'c': 'text', '4': 0.0})


class ForecastMetricsTest(unittest.TestCase):
    ROWS = [{'forecast': 120, 'actual': 100}, {'forecast': 80, 'actual': 100}, {'forecast': 110, 'actual': 100}]

    def test_bias_nets_errors_and_wape_does_not(self):
        m = forecast.metrics(self.ROWS)
        self.assertEqual(m['rows'], 3)
        self.assertAlmostEqual(m['bias'], 10 / 300)  # +20 − 20 + 10 over 300 actual units
        self.assertAlmostEqual(m['wape'], 50 / 300)  # 20 + 20 + 10 over 300 actual units

    def test_bootstrap_interval_is_reproducible_and_brackets_a_constant_bias(self):
        rows = [{'sku_id': f'S{i}', 'forecast': 110, 'actual': 100} for i in range(5)]
        low, high = forecast.bootstrap_bias(rows, draws=99)
        self.assertAlmostEqual(low, 0.10)
        self.assertAlmostEqual(high, 0.10)
        self.assertEqual(forecast.bootstrap_bias(rows, draws=99), [low, high])


class CensoredDemandTest(unittest.TestCase):
    def setUp(self):
        self.tail = stockouts.Tail([-1.0, 0.0, 1.0, 2.0])

    def test_survival_is_the_share_of_residuals_at_or_above_the_threshold(self):
        self.assertEqual(self.tail.survival(-5.0), 1.0)
        self.assertEqual(self.tail.survival(0.0), 0.75)
        self.assertEqual(self.tail.survival(1.5), 0.25)
        self.assertEqual(self.tail.survival(9.0), 0.0)

    def test_conditional_mean_averages_the_residuals_above_the_threshold(self):
        self.assertAlmostEqual(self.tail.cond_exp(1.0), (math.e + math.e**2) / 2)
        # Beyond the observed tail there is nothing to average, so demand is taken to equal the threshold.
        self.assertAlmostEqual(self.tail.cond_exp(9.0), math.exp(9.0))

    def test_lost_units_are_expected_demand_above_what_sold_and_never_negative(self):
        # Predicted 10 units, sold 10: demand was at least the prediction, so the tail above residual 0 applies.
        expected_demand = 10 * (1 + math.e + math.e**2) / 3
        self.assertAlmostEqual(stockouts.lost_units(math.log(10), 10, self.tail), expected_demand - 10)
        # Sold far more than any observed residual allows: demand is taken to equal sales, so nothing was lost.
        self.assertAlmostEqual(stockouts.lost_units(math.log(10), 10_000, self.tail), 0.0, places=6)
        self.assertGreaterEqual(stockouts.lost_units(math.log(10), 10_000, self.tail), 0.0)

    def test_binned_tail_routes_a_prediction_to_its_volume_bin(self):
        clean = [{'log_base': float(i), 'log_units': float(i) + (0.1 if i < 5 else 0.5)} for i in range(10)]
        binned = stockouts.BinnedTail(clean, bins=2)
        self.assertEqual((binned.bin(0.0), binned.bin(4.9), binned.bin(5.0), binned.bin(99.0)), (0, 0, 1, 1))
        self.assertAlmostEqual(binned(1.0).v[0], 0.1)
        self.assertAlmostEqual(binned(8.0).v[0], 0.5)


class StockFlowTest(unittest.TestCase):
    def test_flow_identity_measures_shrink_and_skips_rows_without_an_opening_balance(self):
        rows = [
            {'fiscal_year': 2024, 'prev': None, 'receipts': 50, 'units': 10, 'on_hand': 40},  # no opening stock
            {'fiscal_year': 2024, 'prev': 40, 'receipts': 20, 'units': 30, 'on_hand': 30},  # exact
            {'fiscal_year': 2024, 'prev': 30, 'receipts': 20, 'units': 25, 'on_hand': 20},  # 5 units missing
            {'fiscal_year': 2025, 'prev': 20, 'receipts': 10, 'units': 10, 'on_hand': 20},  # exact
        ]
        out = physical.flow_identity(rows)
        self.assertEqual(out['2024']['store_sku_weeks'], 2)
        self.assertEqual(out['2024']['exact_share'], 0.5)
        self.assertEqual(out['2024']['shrink_units'], 5)
        self.assertEqual(out['2024']['shrink_share_of_receipts'], 5 / 40)
        self.assertEqual(
            out['2025'],
            {
                'store_sku_weeks': 1,
                'receipts_units': 10,
                'units_sold': 10,
                'exact_share': 1.0,
                'shrink_units': 0,
                'shrink_share_of_receipts': 0.0,
            },
        )


class CutSelectionTest(unittest.TestCase):
    @staticmethod
    def candidate(sku, gp_per_facing, sub='Chips', eligible=True, gain=1.0):
        return {
            'sku_id': sku,
            'gp_per_facing': gp_per_facing,
            'subcategory': sub,
            'eligible': eligible,
            'gp_change_per_store_tau_low': gain,
        }

    def test_cuts_the_least_productive_eligible_skus_first_up_to_the_limit(self):
        cands = [self.candidate('C', 3.0), self.candidate('A', 1.0), self.candidate('B', 2.0)]
        chosen = assortment.select_cuts(cands, max_cuts=2, sku_count_by_sub={'Chips': 10})
        self.assertEqual([c['sku_id'] for c in chosen], ['A', 'B'])

    def test_skips_ineligible_skus_and_cuts_that_lose_money_in_the_low_case(self):
        cands = [
            self.candidate('A', 1.0, eligible=False),
            self.candidate('B', 2.0, gain=0.0),
            self.candidate('C', 3.0, gain=-4.0),
            self.candidate('D', 4.0),
        ]
        chosen = assortment.select_cuts(cands, max_cuts=5, sku_count_by_sub={'Chips': 10})
        self.assertEqual([c['sku_id'] for c in chosen], ['D'])

    def test_never_cuts_a_subcategory_below_its_retained_share(self):
        # Five SKUs and a 60% floor: two may go, the third would leave only two of five.
        cands = [self.candidate(s, i) for i, s in enumerate('ABCDE')]
        chosen = assortment.select_cuts(cands, max_cuts=5, sku_count_by_sub={'Chips': 5})
        self.assertEqual([c['sku_id'] for c in chosen], ['A', 'B'])
        self.assertGreaterEqual(5 - len(chosen), assortment.MIN_RETAIN_SHARE * 5)


class PriceLeverTest(unittest.TestCase):
    P = {'q0': 100.0, 'x': 0.10, 'p0': 4.00, 'p1': 4.40, 'c': 2.00}

    def test_no_demand_response_keeps_the_whole_price_increase(self):
        self.assertAlmostEqual(plan.gp_change(self.P, eps=0.0), 100 * 0.40)

    def test_unit_elastic_demand_gives_back_volume(self):
        # Units fall to 100 / 1.1; margin per unit rises from 2.00 to 2.40.
        self.assertAlmostEqual(plan.gp_change(self.P, eps=-1.0), 100 / 1.1 * 2.40 - 200)

    def test_a_ninety_percent_interval_implies_its_standard_deviation(self):
        self.assertAlmostEqual(plan.sd_from_ci([-plan.Z90, plan.Z90]), 1.0)
        self.assertAlmostEqual(plan.sd_from_ci([2.0, 2.0]), 0.0)


class InventoryReplayTest(unittest.TestCase):
    """One store-SKU, six weeks, constant demand of 10 and a perfect forecast; the replay starts at week 2."""

    def arrays(self, opening_stock, demand=10.0):
        t = 6
        full = lambda v: np.full((1, t), float(v))
        return {
            'w0': 2,
            't': t,
            'on_hand': full(opening_stock),
            'receipts': full(demand),
            'units': full(demand),
            'demand': full(demand),
            'carried': np.ones((1, t), bool),
            'case_pack': np.array([1.0]),
            'margin': np.array([2.0]),
            'cost': np.array([1.0]),
        }

    def run_policy(self, opening_stock, k=0.0):
        a = self.arrays(opening_stock)
        return inventory_sim.simulate(a, forecast=a['demand'].copy(), k=k, sigma=np.zeros((1, a['t'])))

    def test_a_perfect_forecast_fills_every_unit_with_no_safety_stock(self):
        out = self.run_policy(opening_stock=0)
        self.assertEqual(out['fill_rate'], 1.0)
        self.assertEqual(out['lost_units'], 0.0)
        self.assertEqual(out['units_sold'], 40.0)  # 4 replayed weeks × 10
        self.assertEqual(out['receipts'], 40.0)
        self.assertEqual(out['zero_stock_share'], 1.0)  # stock runs to zero at each week's end
        self.assertEqual(out['policy_cost'], 0.0)

    def test_units_are_conserved_and_excess_opening_stock_is_worked_down(self):
        out = self.run_policy(opening_stock=15)
        self.assertEqual(out['fill_rate'], 1.0)
        # Sold 40 from 15 opening + receipts, so receipts are at most 40 and ending stock is what is left over.
        self.assertLessEqual(out['receipts'], 40.0)
        self.assertGreaterEqual(15 + out['receipts'] - out['units_sold'], 0.0)
        self.assertAlmostEqual(out['carrying_cost'], inventory_sim.CARRY_RATE * out['avg_stock_cost'])
        self.assertAlmostEqual(out['policy_cost'], out['lost_gp'] + out['carrying_cost'])

    def test_demand_above_supply_is_lost_and_costed_at_margin(self):
        a = self.arrays(opening_stock=0)
        a['demand'][:] = 15.0  # true demand exceeds the forecast of 10
        out = inventory_sim.simulate(a, forecast=np.full((1, 6), 10.0), k=0.0, sigma=np.zeros((1, 6)))
        self.assertEqual(out['units_sold'] + out['lost_units'], 60.0)
        self.assertEqual(out['lost_units'], 20.0)  # 5 short in each of 4 weeks
        self.assertEqual(out['lost_gp'], 40.0)  # at a margin of 2.00
        self.assertAlmostEqual(out['fill_rate'], 40 / 60)

    def test_more_safety_stock_never_lowers_the_fill_rate(self):
        a = self.arrays(opening_stock=0)
        a['demand'][:] = 15.0
        sigma = np.full((1, 6), 4.0)
        fills = [inventory_sim.simulate(a, np.full((1, 6), 10.0), k, sigma)['fill_rate'] for k in (0.0, 1.0, 3.0)]
        self.assertEqual(fills, sorted(fills))
        self.assertGreater(fills[-1], fills[0])


if __name__ == '__main__':
    unittest.main()
