"""Estimator checks on simulated panels with known parameters (no warehouse needed)."""
import csv
import math
import random
import tempfile
import unittest
from pathlib import Path

import duckdb

from analysis.fe import chi2_sf, clustered_ci, fe_levels, feols, t_crit, t_sf2
from analysis.fe_reference import feols_reference


def simulated_panel(seed=7, units=30, periods=40, beta=(-1.8, 0.6)):
    """Unbalanced two-way FE panel; x1 is correlated with both FEs so omitting them would bias beta."""
    rng = random.Random(seed)
    unit_fe = {u: rng.gauss(0, 2) for u in range(units)}
    time_fe = {t: rng.gauss(0, 1) for t in range(periods)}
    rows = []
    for u in range(units):
        cluster_shock = rng.gauss(0, 0.3)
        for t in range(periods):
            if rng.random() < 0.15:
                continue  # unbalanced
            x1 = 0.5 * unit_fe[u] + 0.4 * time_fe[t] + rng.gauss(0, 1)
            x2 = rng.gauss(0, 1) + 0.3 * x1
            y = beta[0] * x1 + beta[1] * x2 + unit_fe[u] + time_fe[t] + cluster_shock * x1 + rng.gauss(0, 1)
            rows.append({'fe_a': f'u{u}', 'fe_b': f't{t}', 'cluster_id': f'u{u}', 'y': y, 'x1': x1, 'x2': x2})
    return rows


class FixedEffectsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = simulated_panel()
        cls.con = duckdb.connect()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'panel.csv'
            with path.open('w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(cls.rows[0]))
                writer.writeheader()
                writer.writerows(cls.rows)
            cls.con.execute(f"create table panel as select * from read_csv('{path.as_posix()}')")
        cls.fit = feols(cls.con, 'panel', 'y', ['x1', 'x2'], ['fe_a', 'fe_b'])

    def test_recovers_planted_coefficients(self):
        for name, truth in (('x1', -1.8), ('x2', 0.6)):
            lo, hi = clustered_ci(self.fit, name, 0.95)
            self.assertLess(lo, truth)
            self.assertGreater(hi, truth)

    def test_two_implementations_agree(self):
        ref = feols_reference(self.rows, 'y', ['x1', 'x2'], ['fe_a', 'fe_b'])
        for name in ('x1', 'x2'):
            self.assertAlmostEqual(self.fit['beta'][name], ref['beta'][name], places=7)
            self.assertAlmostEqual(self.fit['se'][name], ref['se'][name], places=6)
        self.assertEqual(self.fit['n'], ref['n'])

    def test_t_distribution_matches_reference_values(self):
        for df, expected in ((5, 2.015048), (21, 1.720743), (1000, 1.646379)):
            self.assertAlmostEqual(t_crit(df, 0.90), expected, places=5)
        self.assertAlmostEqual(t_sf2(2.0, 10), 0.0733880, places=6)

    def test_chi_square_tail_matches_reference_values(self):
        for stat, df, expected in ((3.841459, 1, 0.05), (5.991465, 2, 0.05), (18.30704, 10, 0.05), (2.0, 4, 0.7357589)):
            self.assertAlmostEqual(chi2_sf(stat, df), expected, places=5)

    def test_fixed_effect_levels_satisfy_normal_equations(self):
        fe_levels(self.con, 'panel', 'y', self.fit['beta'], ['fe_a', 'fe_b'])
        b = self.fit['beta']
        self.con.execute(f"""create or replace temp table _e as
            select p.fe_a, p.fe_b, p.x1, p.y - {b['x1']!r} * p.x1 - {b['x2']!r} * p.x2 - a.value - t.value as e
            from panel p join _fe_fe_a a on a.level = p.fe_a join _fe_fe_b t on t.level = p.fe_b""")
        worst = self.con.execute("""select greatest(
            (select max(abs(m)) from (select avg(e) as m from _e group by fe_a)),
            (select max(abs(m)) from (select avg(e) as m from _e group by fe_b)),
            abs((select sum(x1 * e) from _e)) / (select count(*) from _e))""").fetchone()[0]
        self.assertLess(worst, 1e-7)

    def test_reference_cholesky_path_matches_for_three_regressors(self):
        rows = [{**r, 'z': math.sin(i) + 0.2 * r['x2']} for i, r in enumerate(self.rows)]
        self.con.execute('create or replace table panel3 (fe_a varchar, fe_b varchar, cluster_id varchar, '
                         'y double, x1 double, x2 double, z double)')
        self.con.executemany('insert into panel3 values (?, ?, ?, ?, ?, ?, ?)',
                             [[r[c] for c in ('fe_a', 'fe_b', 'cluster_id', 'y', 'x1', 'x2', 'z')] for r in rows])
        fit = feols(self.con, 'panel3', 'y', ['x1', 'x2', 'z'], ['fe_a', 'fe_b'])
        ref = feols_reference(rows, 'y', ['x1', 'x2', 'z'], ['fe_a', 'fe_b'])
        for name in ('x1', 'x2', 'z'):
            self.assertAlmostEqual(fit['beta'][name], ref['beta'][name], places=7)
            self.assertAlmostEqual(fit['se'][name], ref['se'][name], places=6)

    def test_omitting_fixed_effects_would_bias(self):
        naive = sum(r['x1'] * r['y'] for r in self.rows) / sum(r['x1'] ** 2 for r in self.rows)
        self.assertGreater(abs(naive - (-1.8)), 0.2)
        self.assertLess(abs(self.fit['beta']['x1'] - (-1.8)), 0.2)


if __name__ == '__main__':
    unittest.main()
