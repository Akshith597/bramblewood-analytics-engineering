"""Q1 — FY2025 W27 delisting test. Implements analysis/PLAN.md §Q1 without deviation unless logged."""
from itertools import combinations
import math

from analysis.common import connect, export_panel, pct_effect, round_floats, write_result
from analysis.fe import quantile, t_crit, t_sf2

TREATED = (102, 106, 113, 116)
EXCLUDED = (112, 124)            # remodel overlapping the switch; opened mid-test
LARGE_CONTROLS = (101, 117)
ROLLOUT_STORES = (101, 112, 117, 124)
SWITCH_WEEK = 'FY2025-W27'

PANEL_SQL = f"""
with delisted as (
    select sku_id from stg_planograms where planogram_id = 'PG-SS-L-2024'
    except
    select sku_id from stg_planograms where planogram_id = 'PG-SS-L-TEST25'
),
weeks as (
    select week_key, row_number() over (order by week_start) as week_index from stg_fiscal_calendar
)
select s.store_id, s.week_key, w.week_index,
    sum(s.gross_profit_before_funding)::double as gp,
    sum(s.net_sales)::double as sales,
    sum(s.units)::double as units,
    coalesce(sum(s.net_sales) filter (where s.sku_id in (select sku_id from delisted)), 0)::double as delisted_sales,
    coalesce(sum(s.net_sales) filter (where s.sku_id not in (select sku_id from delisted)), 0)::double as retained_sales
from int_sales_enriched as s
join weeks as w using (week_key)
where s.store_id not in {EXCLUDED}
group by all
order by s.store_id, w.week_index
"""


def load(con):
    rows = con.execute(PANEL_SQL).fetchall()
    cols = [d[0] for d in con.description]
    panel = {}
    for row in rows:
        r = dict(zip(cols, row))
        panel.setdefault(r['store_id'], []).append(r)
    switch = con.execute(f"select count(*) + 1 from stg_fiscal_calendar where week_start < "
                         f"(select week_start from stg_fiscal_calendar where week_key = '{SWITCH_WEEK}')").fetchone()[0]
    lengths = {len(v) for v in panel.values()}
    if lengths != {104}:
        raise AssertionError(f'Delist panel must be balanced at 104 weeks, got {lengths}')
    return panel, switch, [dict(zip(cols, r)) for r in rows]


def series(panel, metric, transform=math.log):
    return {s: [transform(r[metric]) for r in rows] for s, rows in panel.items()}


def indexed(panel, metric, pre):
    """Value / the store's own pre-period mean: a proportional scale that tolerates negative weeks."""
    out = {}
    for s, rows in panel.items():
        base = sum(rows[w][metric] for w in pre) / len(pre)
        out[s] = [r[metric] / base for r in rows]
    return out


class Did:
    """Balanced-panel TWFE DiD with block adoption; closed forms are exact for this design."""

    def __init__(self, y, treated, controls, pre, post):
        self.y, self.treated, self.controls = y, tuple(treated), tuple(controls)
        self.stores = self.treated + self.controls
        self.weeks = list(pre) + list(post)
        self.post = set(post)
        n_t, n_w = len(self.stores), len(self.weeks)
        d = {s: [1.0 if (s in self.treated and w in self.post) else 0.0 for w in self.weeks] for s in self.stores}
        self.d_tilde = self._demean(d)
        self.sdd = sum(v * v for s in self.stores for v in self.d_tilde[s])
        self.y_tilde = self._demean({s: [y[s][w] for w in self.weeks] for s in self.stores})
        self.n, self.g = n_t * n_w, n_t

    def _demean(self, data):
        stores, nw = self.stores, len(self.weeks)
        row = {s: sum(data[s]) / nw for s in stores}
        col = [sum(data[s][t] for s in stores) / len(stores) for t in range(nw)]
        grand = sum(row.values()) / len(stores)
        return {s: [data[s][t] - row[s] - col[t] + grand for t in range(nw)] for s in stores}

    def fit(self, y_tilde=None):
        y_tilde = y_tilde or self.y_tilde
        beta = sum(a * b for s in self.stores for a, b in zip(self.d_tilde[s], y_tilde[s])) / self.sdd
        scores = [sum(dd * (yy - beta * dd) for dd, yy in zip(self.d_tilde[s], y_tilde[s])) for s in self.stores]
        se = math.sqrt(self.g / (self.g - 1) * sum(x * x for x in scores)) / self.sdd
        return beta, se

    def infer(self, level=0.90):
        """Estimate, store-clustered (CR1) standard error, and a t-based p-value and 90% CI.

        Only four stores received the change, so a clustered standard error is less reliable than its 22 clusters
        suggest. The degrees of freedom are therefore set by the smaller group: (test stores - 1) = 3, which gives
        a critical value of 2.35 instead of 1.645 and a correspondingly wider, more cautious range.
        """
        beta, se = self.fit()
        df = min(len(self.treated), len(self.controls)) - 1
        crit = t_crit(df, level)
        return {'beta': beta, 'se_cr1': se, 't_stat': beta / se, 'df': df, 'p_value': t_sf2(beta / se, df),
                'ci90': [beta - crit * se, beta + crit * se], 'clusters': self.g}


def store_change(y, stores, pre, post):
    return {s: sum(y[s][w] for w in post) / len(post) - sum(y[s][w] for w in pre) / len(pre) for s in stores}


def randomization(y, donors, pre, post, observed, k=len(TREATED), loss_shift=lambda d: math.log(1 - d)):
    """Placebo distribution over every k-store subset of the donor pool (balanced closed form)."""
    change = store_change(y, donors, pre, post)
    total = sum(change.values())
    placebo = []
    for subset in combinations(donors, k):
        inside = sum(change[s] for s in subset)
        placebo.append(inside / k - (total - inside) / (len(donors) - k))
    sd = math.sqrt(sum(p * p for p in placebo) / len(placebo) - (sum(placebo) / len(placebo)) ** 2)
    p_value = (1 + sum(abs(p) >= abs(observed) for p in placebo)) / (1 + len(placebo))
    crit = quantile([abs(p) for p in placebo], 0.95)
    power = {f'{int(d * 100)}pct': sum(abs(p + loss_shift(d)) > crit for p in placebo) / len(placebo)
             for d in (0.01, 0.02, 0.03, 0.05)}
    return {'assignments': len(placebo), 'p_value': p_value, 'placebo_sd': sd, 'mde_log': 2.8 * sd,
            'power_against_loss': power}


def event_study(y, treated, donors, switch_index, weeks):
    """4-week bins relative to the switch; reference bin = the 4 weeks before it."""
    bins = {}
    for w in weeks:
        bins.setdefault((w - switch_index) // 4, []).append(w)

    def coefs(t_set, c_set):
        gap = {b: sum(y[s][w] for s in t_set for w in ws) / (len(t_set) * len(ws))
               - sum(y[s][w] for s in c_set for w in ws) / (len(c_set) * len(ws)) for b, ws in bins.items()}
        return {b: gap[b] - gap[-1] for b in sorted(bins) if b != -1}

    observed = coefs(treated, donors)
    pre_stat = max(abs(v) for b, v in observed.items() if b < -1)
    placebo_stats = []
    for subset in combinations(donors, len(treated)):
        rest = [s for s in donors if s not in subset]
        placebo_stats.append(max(abs(v) for b, v in coefs(subset, rest).items() if b < -1))
    p_pre = (1 + sum(p >= pre_stat for p in placebo_stats)) / (1 + len(placebo_stats))
    return {'bins': {str(b): v for b, v in observed.items()}, 'max_abs_pre_coef': pre_stat,
            'pre_trend_p_randomization': p_pre}


def main():
    con = connect()
    panel, switch, flat = load(con)
    export_panel('delist_panel', flat)
    stores = sorted(panel)
    donors = tuple(s for s in stores if s not in TREATED)
    weeks = list(range(104))
    pre, post = weeks[:switch - 1], weeks[switch - 1:]
    if (len(pre), len(post)) != (78, 26):
        raise AssertionError(f'Unexpected window lengths {len(pre)}/{len(post)}')

    result = {'treated_stores': TREATED, 'donor_stores': donors, 'excluded_stores': EXCLUDED,
              'pre_weeks': len(pre), 'post_weeks': len(post)}
    # Deviation 1 (logged in memo): GP is indexed to each store's pre-period mean instead of logged, because
    # store 111 has negative GP in FY2025 W27 (chain-wide ~30% promotion week). Effect stays proportional.
    y = {'gp': indexed(panel, 'gp', pre), 'sales': series(panel, 'sales'), 'units': series(panel, 'units')}

    primary = Did(y['gp'], TREATED, donors, pre, post).infer()
    result['gp'] = primary
    result['gp']['randomization'] = randomization(y['gp'], donors, pre, post, primary['beta'],
                                                  loss_shift=lambda d: -d)
    # Sensitivity for deviation 1: the pre-registered log GP, dropping the one undefined week for every store.
    bad = {w for s, rows in panel.items() for w, r in enumerate(rows) if r['gp'] <= 0}
    log_gp = {s: [math.log(r['gp']) if w not in bad else 0.0 for w, r in enumerate(rows)] for s, rows in panel.items()}
    result['gp_log_sensitivity'] = Did(log_gp, TREATED, donors, [w for w in pre if w not in bad],
                                       [w for w in post if w not in bad]).infer()
    result['gp_log_sensitivity']['dropped_week_indexes'] = sorted(bad)
    result['gp']['event_study'] = event_study(y['gp'], TREATED, donors, switch - 1, weeks)
    for metric in ('sales', 'units'):
        result[metric] = Did(y[metric], TREATED, donors, pre, post).infer()
        result[metric]['randomization'] = randomization(y[metric], donors, pre, post, result[metric]['beta'])

    # Robustness: large-format controls only (2 control stores, so only the point estimate is informative).
    result['gp_large_controls_only'] = Did(y['gp'], TREATED, LARGE_CONTROLS, pre, post).infer()

    # Fake treatment dates using pre-switch data only.
    fakes = {}
    for label, cut, end in (('FY2024-W27', 26, 52), ('FY2025-W01', 52, 78)):
        fakes[label] = Did(y['gp'], TREATED, donors, weeks[:cut], weeks[cut:end]).infer()
    result['gp_fake_dates'] = fakes

    # Planted effects: shift treated post-period log GP by a known amount; the estimator must move by it.
    planted = {}
    for delta in (-0.02, 0.02):
        shifted = {s: [v + (delta if (s in TREATED and w in set(post)) else 0.0) for w, v in enumerate(vals)]
                   for s, vals in y['gp'].items()}
        b, _ = Did(shifted, TREATED, donors, pre, post).fit()
        planted[str(delta)] = {'recovered_shift': b - primary['beta']}
    result['gp_planted_effect'] = planted

    # Transfer: retained-SKU dollar gain per dollar of delisted-SKU sales lost (levels, $ per store-week).
    level = {m: series(panel, m, transform=float) for m in ('delisted_sales', 'retained_sales')}
    lost = -Did(level['delisted_sales'], TREATED, donors, pre, post).fit()[0]
    gained_fit = Did(level['retained_sales'], TREATED, donors, pre, post).infer()
    result['transfer'] = {'delisted_sales_lost_per_store_week': lost,
                          'retained_sales_change_per_store_week': gained_fit['beta'],
                          'retained_ci90': gained_fit['ci90'],
                          'transfer_rate': gained_fit['beta'] / lost,
                          'transfer_rate_ci90': [v / lost for v in gained_fit['ci90']]}

    # Dollar figure: annual GP of the large-format stores that a rollout would add.
    weekly = con.execute(f"""
        select store_id, avg(gp) from (
            select store_id, week_key, sum(gross_profit_before_funding)::double as gp
            from int_sales_enriched where fiscal_year = 2025 and not remodel_week
              and store_id in {ROLLOUT_STORES} group by all) group by 1""").fetchall()
    annual_gp = sum(v for _, v in weekly) * 52
    effect = primary['beta']               # indexed scale: already a proportion of pre-period GP
    ci = list(primary['ci90'])
    result['rollout'] = {'stores': ROLLOUT_STORES, 'annual_gp_base': annual_gp,
                         'annual_gp_change': annual_gp * effect,
                         'annual_gp_change_ci90': [annual_gp * v for v in ci]}

    rule_lower = -0.01
    mde = -result['gp']['randomization']['mde_log']
    if abs(mde) > 0.03:
        decision = 'underpowered'
    elif effect >= 0 and ci[0] > rule_lower:
        decision = 'roll_out'
    else:
        decision = 'do_not_roll_out'
    result['decision'] = {'gp_effect_pct': effect, 'gp_effect_ci90_pct': ci, 'mde_pct': mde,
                          'rule_lower_bound': rule_lower, 'outcome': decision}
    # Exploratory (not pre-registered, not used for the decision): the FY2024 W27 fake date shows a
    # same-season gap of similar size, so subtract it as a year-over-year (triple-difference) adjustment.
    result['exploratory_yoy_adjusted_gp'] = primary['beta'] - fakes['FY2024-W27']['beta']
    write_result('delist', round_floats(result))
    return result


if __name__ == '__main__':
    import json
    print(json.dumps(round_floats(main()['decision']), indent=2))
