"""Q1 — FY2025 W27 delisting test. Implements analysis/PLAN.md §Q1 without deviation unless logged."""
from itertools import combinations
import math
import random

from analysis.common import connect, export_panel, pct_effect, round_floats, write_result
from analysis.fe import WEBB, quantile

TREATED = (102, 106, 113, 116)
EXCLUDED = (112, 124)            # remodel overlapping the switch; opened mid-test
LARGE_CONTROLS = (101, 117)
ROLLOUT_STORES = (101, 112, 117, 124)
SWITCH_WEEK = 'FY2025-W27'
DRAWS = 9999
SEED = 20261014

PANEL_SQL = """
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
where not list_contains($excluded, s.store_id)
group by all
order by s.store_id, w.week_index
"""


def load(con):
    rows = con.execute(PANEL_SQL, {'excluded': list(EXCLUDED)}).fetchall()
    cols = [d[0] for d in con.description]
    panel = {}
    for row in rows:
        r = dict(zip(cols, row))
        panel.setdefault(r['store_id'], []).append(r)
    switch = con.execute("select count(*) + 1 from stg_fiscal_calendar where week_start < "
                         "(select week_start from stg_fiscal_calendar where week_key = ?)", [SWITCH_WEEK]).fetchone()[0]
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

    def _bootstrap_y(self, base, residual, weights):
        nw = len(self.weeks)
        shocked = {s: [w * residual[s][t] for t in range(nw)] for s, w in zip(self.stores, weights)}
        col = [sum(shocked[s][t] for s in self.stores) / len(self.stores) for t in range(nw)]
        return {s: [base[s][t] + shocked[s][t] - col[t] for t in range(nw)] for s in self.stores}

    def wild(self, draws=DRAWS, seed=SEED, level=0.90):
        """Restricted (null-imposed) wild cluster bootstrap-t p-value and unrestricted bootstrap-t CI."""
        beta, se = self.fit()
        t_obs = beta / se
        rng = random.Random(seed)
        zero = {s: [0.0] * len(self.weeks) for s in self.stores}
        fitted_u = {s: [beta * d for d in self.d_tilde[s]] for s in self.stores}
        resid_u = {s: [y - f for y, f in zip(self.y_tilde[s], fitted_u[s])] for s in self.stores}
        exceed, t_u = 0, []
        for _ in range(draws):
            weights = [rng.choice(WEBB) for _ in self.stores]
            b_r, s_r = self.fit(self._bootstrap_y(zero, self.y_tilde, weights))
            exceed += abs(b_r / s_r) >= abs(t_obs)
            b_u, s_u = self.fit(self._bootstrap_y(fitted_u, resid_u, weights))
            t_u.append(abs((b_u - beta) / s_u))
        crit = quantile(t_u, level)
        return {'beta': beta, 'se_cr1': se, 'p_wild': (exceed + 1) / (draws + 1),
                'ci90_wild': [beta - crit * se, beta + crit * se], 'clusters': self.g, 'draws': draws}


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


def project_to_simplex(v):
    u = sorted(v, reverse=True)
    css, rho, theta = 0.0, 0, 0.0
    for i, ui in enumerate(u, 1):
        css += ui
        t = (css - 1) / i
        if ui - t > 0:
            rho, theta = i, t
    return [max(x - theta, 0.0) for x in v]


def synthetic_control(y, unit, donors, pre, post, iterations=4000):
    """Intercept-shifted (demeaned) synthetic control fitted by projected gradient on the simplex."""
    mean = {s: sum(y[s][w] for w in pre) / len(pre) for s in (unit, *donors)}
    target = [y[unit][w] - mean[unit] for w in pre]
    x = {s: [y[s][w] - mean[s] for w in pre] for s in donors}
    weights = [1 / len(donors)] * len(donors)
    lipschitz = sum(sum(v * v for v in x[s]) for s in donors)
    step = 1 / lipschitz
    for _ in range(iterations):
        fit = [sum(wt * x[s][t] for wt, s in zip(weights, donors)) for t in range(len(pre))]
        grad = [sum((f - tv) * x[s][t] for t, (f, tv) in enumerate(zip(fit, target))) for s in donors]
        weights = project_to_simplex([wt - step * g for wt, g in zip(weights, grad)])

    def gap(w):
        return y[unit][w] - mean[unit] - sum(wt * (y[s][w] - mean[s]) for wt, s in zip(weights, donors))

    pre_rmspe = math.sqrt(sum(gap(w) ** 2 for w in pre) / len(pre))
    post_rmspe = math.sqrt(sum(gap(w) ** 2 for w in post) / len(post))
    return {'effect': sum(gap(w) for w in post) / len(post), 'pre_rmspe': pre_rmspe,
            'ratio': post_rmspe / pre_rmspe, 'weights': {s: wt for s, wt in zip(donors, weights) if wt > 0.01}}


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

    primary = Did(y['gp'], TREATED, donors, pre, post).wild()
    result['gp'] = primary
    result['gp']['randomization'] = randomization(y['gp'], donors, pre, post, primary['beta'],
                                                  loss_shift=lambda d: -d)
    # Sensitivity for deviation 1: the pre-registered log GP, dropping the one undefined week for every store.
    bad = {w for s, rows in panel.items() for w, r in enumerate(rows) if r['gp'] <= 0}
    log_gp = {s: [math.log(r['gp']) if w not in bad else 0.0 for w, r in enumerate(rows)] for s, rows in panel.items()}
    result['gp_log_sensitivity'] = Did(log_gp, TREATED, donors, [w for w in pre if w not in bad],
                                       [w for w in post if w not in bad]).wild(draws=1999)
    result['gp_log_sensitivity']['dropped_week_indexes'] = sorted(bad)
    result['gp']['event_study'] = event_study(y['gp'], TREATED, donors, switch - 1, weeks)
    for metric in ('sales', 'units'):
        result[metric] = Did(y[metric], TREATED, donors, pre, post).wild()
        result[metric]['randomization'] = randomization(y[metric], donors, pre, post, result[metric]['beta'])

    # Robustness: large-format controls only (6 clusters: Webb weights are designed for this).
    result['gp_large_controls_only'] = Did(y['gp'], TREATED, LARGE_CONTROLS, pre, post).wild()

    # Robustness: synthetic control per treated store, with in-space placebo ranks.
    sc = {s: synthetic_control(y['gp'], s, donors, pre, post) for s in TREATED}
    placebo_ratios = [synthetic_control(y['gp'], d, tuple(x for x in donors if x != d), pre, post)['ratio']
                      for d in donors]
    result['gp_synthetic_control'] = {
        'effect_mean': sum(v['effect'] for v in sc.values()) / len(sc),
        'by_store': {str(s): {'effect': v['effect'], 'pre_rmspe': v['pre_rmspe'], 'ratio': v['ratio'],
                              'rank_p': (1 + sum(r >= v['ratio'] for r in placebo_ratios)) / (1 + len(placebo_ratios)),
                              'weights': {str(k): w for k, w in v['weights'].items()}}
                     for s, v in sc.items()}}

    # Fake treatment dates using pre-switch data only.
    fakes = {}
    for label, cut, end in (('FY2024-W27', 26, 52), ('FY2025-W01', 52, 78)):
        fakes[label] = Did(y['gp'], TREATED, donors, weeks[:cut], weeks[cut:end]).wild(draws=1999)
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
    gained_fit = Did(level['retained_sales'], TREATED, donors, pre, post).wild(draws=1999)
    result['transfer'] = {'delisted_sales_lost_per_store_week': lost,
                          'retained_sales_change_per_store_week': gained_fit['beta'],
                          'retained_ci90': gained_fit['ci90_wild'],
                          'transfer_rate': gained_fit['beta'] / lost,
                          'transfer_rate_ci90': [v / lost for v in gained_fit['ci90_wild']]}

    # Dollar figure: annual GP of the large-format stores that a rollout would add.
    weekly = con.execute("""
        select store_id, avg(gp) from (
            select store_id, week_key, sum(gross_profit_before_funding)::double as gp
            from int_sales_enriched where fiscal_year = 2025 and not remodel_week
              and list_contains($stores, store_id) group by all) group by 1""",
                         {'stores': list(ROLLOUT_STORES)}).fetchall()
    annual_gp = sum(v for _, v in weekly) * 52
    effect = primary['beta']               # indexed scale: already a proportion of pre-period GP
    ci = list(primary['ci90_wild'])
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
