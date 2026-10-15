"""Q4 — out-of-stock cost (exploratory). Implements the analysis/PLAN.md addendum (§Q4 out-of-stock).

On a zero-stock snapshot week the store sold everything it had (sales = prior on-hand + receipts), so demand
was at least the sales. Lost units are estimated as the expected demand above that floor, using the Q2 baseline
model's imputed demand and the empirical distribution of its in-stock residuals. The originally planned
adjacent-week estimator is also reported unchanged.
"""
import bisect
import json
import math
import random

from analysis.common import RESULTS, connect, export_panel, round_floats, write_result
from analysis.fe import quantile
from analysis.promotions import SEED, build, fit_baseline, impute

DECISION_YEAR = 2025
BINS = 10
BIN_SENSITIVITY = (5, 20)
ADJACENT = 2                    # nearest in-stock non-promoted weeks on each side
ADJACENT_MAX_GAP = 6
PLANTED_CENSOR = 0.7
CALIBRATION_TOLERANCE = 0.25
PRIORITY_SHARE = 0.01           # decision threshold: 1% of FY2025 category GP
DRAWS = 1999

ROWS_SQL = """
with inv as (
    select i.store_id, i.sku_id, c.w,
        lag(i.on_hand_eow) over (partition by i.store_id, i.sku_id order by c.w) + i.receipts_units as available
    from fct_inventory i join cal c using (week_key)
)
select p.store_id, p.sku_id, p.w, p.fiscal_year, p.role, p.zero_stock, p.post_k, p.units, p.gp, p.reg_margin,
    p.log_units, p.log_base, p.base_units, inv.available, e.mechanic || case when e.display = 'Y' then ' + display' else '' end
        as cell, e.scan_per_unit
from promo_panel p
left join inv using (store_id, sku_id, w)
left join promo_events e using (promo_id)
where p.log_base is not null
order by p.store_id, p.sku_id, p.w
"""


class Tail:
    """Empirical residual distribution: P(e >= t) and E[exp(e) | e >= t]."""

    def __init__(self, residuals):
        self.v = sorted(residuals)
        self.suffix = [0.0] * (len(self.v) + 1)
        for i in range(len(self.v) - 1, -1, -1):
            self.suffix[i] = self.suffix[i + 1] + math.exp(self.v[i])

    def survival(self, t):
        return (len(self.v) - bisect.bisect_left(self.v, t)) / len(self.v)

    def cond_exp(self, t):
        i = bisect.bisect_left(self.v, t)
        return self.suffix[i] / (len(self.v) - i) if i < len(self.v) else math.exp(t)  # beyond the observed tail


class BinnedTail:
    """Clean-week residuals split by quantile bins of predicted log demand (noise shrinks with volume)."""

    def __init__(self, clean, bins):
        mus = sorted(r['log_base'] for r in clean)
        self.cuts = [mus[int(len(mus) * i / bins)] for i in range(1, bins)]
        groups = {}
        for r in clean:
            groups.setdefault(self.bin(r['log_base']), []).append(r['log_units'] - r['log_base'])
        self.tails = {b: Tail(v) for b, v in groups.items()}

    def bin(self, mu):
        return bisect.bisect_right(self.cuts, mu)

    def __call__(self, mu):
        return self.tails[self.bin(mu)]


def lost_units(mu, sold, tail):
    return max(math.exp(mu) * tail.cond_exp(math.log(sold) - mu) - sold, 0.0)


def censored_estimates(rows, clean, bins):
    """Lost units and GP for every zero-stock week. Returns per-row records."""
    tails = BinnedTail(clean, bins)
    post_shift = {}
    for k in (1, 2):
        e = [r['log_units'] - r['log_base'] for r in rows if r['role'] == 'post' and r['post_k'] == k
             and not r['zero_stock']]
        post_shift[k] = sum(e) / len(e)
    promo_resid = {}
    for r in rows:
        if r['role'] == 'promo' and not r['zero_stock']:
            promo_resid.setdefault(r['cell'], []).append(r['log_units'] - r['log_base'])
    promo_shift = {c: sum(v) / len(v) for c, v in promo_resid.items()}
    promo_tail = {c: Tail([x - promo_shift[c] for x in v]) for c, v in promo_resid.items()}
    out = []
    for r in rows:
        if not r['zero_stock']:
            continue
        if r['role'] == 'promo':
            group, mu = 'promoted', r['log_base'] + promo_shift[r['cell']]
            units = lost_units(mu, r['units'], promo_tail[r['cell']])
            margin = r['gp'] / r['units'] + r['scan_per_unit']
        else:
            mu = r['log_base'] + (post_shift[r['post_k']] if r['role'] == 'post' else 0.0)
            group = 'non_promoted'
            units = lost_units(mu, r['units'], tails(mu))
            margin = r['reg_margin']
        out.append({'store_id': r['store_id'], 'sku_id': r['sku_id'], 'w': r['w'], 'fiscal_year': r['fiscal_year'], 'group': group,
                    'lost_units': units, 'lost_gp': units * margin, 'sold': r['units']})
    return out, tails


def totals(records, year, group):
    sel = [r for r in records if r['fiscal_year'] == year and r['group'] == group]
    return {'zero_stock_weeks': len(sel), 'units_sold': sum(r['sold'] for r in sel),
            'lost_units': sum(r['lost_units'] for r in sel), 'lost_gp': sum(r['lost_gp'] for r in sel)}


def store_bootstrap(records, year, group):
    """Resample stores; lost GP per zero-stock week x the observed number of zero-stock weeks."""
    per = {}
    for r in records:
        if r['fiscal_year'] == year and r['group'] == group:
            s = per.setdefault(r['store_id'], [0.0, 0])
            s[0] += r['lost_gp']
            s[1] += 1
    stores = sorted(per)
    n_weeks = sum(v[1] for v in per.values())
    rng = random.Random(SEED)
    boot = []
    for _ in range(DRAWS):
        draw = [per[rng.choice(stores)] for _ in stores]
        boot.append(sum(d[0] for d in draw) / sum(d[1] for d in draw) * n_weeks)
    return [quantile(boot, 0.05), quantile(boot, 0.95)]


def adjacent_week_estimator(rows):
    """Originally planned estimator: mean of the nearest in-stock non-promoted weeks on each side, minus actual."""
    by_key = {}
    for r in rows:
        by_key.setdefault((r['store_id'], r['sku_id']), []).append(r)
    clean_roles = {'clean', 'pre', 'placebo'}
    out = []
    for series in by_key.values():
        weeks = {r['w']: r for r in series}
        for r in series:
            if r['role'] != 'stockout':
                continue
            sides = []
            for step in (-1, 1):
                found = [weeks[r['w'] + step * d]['units'] for d in range(1, ADJACENT_MAX_GAP + 1)
                         if r['w'] + step * d in weeks and weeks[r['w'] + step * d]['role'] in clean_roles][:ADJACENT]
                sides.append(found)
            if all(sides):
                base = sum(sides[0] + sides[1]) / len(sides[0] + sides[1])
                out.append({'fiscal_year': r['fiscal_year'], 'lost_units': base - r['units'],
                            'lost_gp': (base - r['units']) * r['reg_margin']})
    fy = [o for o in out if o['fiscal_year'] == DECISION_YEAR]
    return {'zero_stock_weeks_with_both_sides': len(fy), 'lost_units': sum(o['lost_units'] for o in fy),
            'lost_gp': sum(o['lost_gp'] for o in fy),
            'share_weeks_with_positive_loss': sum(o['lost_units'] > 0 for o in fy) / len(fy),
            'informative': sum(o['lost_units'] for o in fy) > 0}


def main():
    con = connect()
    build(con)
    impute(con, fit_baseline(con))
    cur = con.execute(ROWS_SQL)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    clean = [r for r in rows if r['role'] == 'clean']
    records, tails = censored_estimates(rows, clean, BINS)
    # Per-week censored demand, reused by analysis/physical.py (bias on restored demand) and the inventory simulation.
    export_panel('stockout_lost_units', [{k: r[k] for k in ('store_id', 'sku_id', 'w', 'fiscal_year', 'group',
                                                            'sold', 'lost_units')} for r in records])

    # Calibration: predicted number of stock-outs among non-promoted weeks with known availability.
    eligible = [r for r in rows if r['role'] in ('clean', 'stockout') and r['available'] and r['available'] > 0]
    predicted = sum(tails(r['log_base']).survival(math.log(r['available']) - r['log_base']) for r in eligible)
    observed = sum(r['role'] == 'stockout' for r in eligible)

    # Planted censoring on held-out placebo weeks: true lost units are known.
    placebo = [r for r in rows if r['role'] == 'placebo' and r['units'] >= 2]
    truth = recovered = 0.0
    for r in placebo:
        sold = max(math.floor(PLANTED_CENSOR * r['units']), 1)
        truth += r['units'] - sold
        recovered += lost_units(r['log_base'], sold, tails(r['log_base']))

    # Post-hoc (not registered): censor at an availability set independently of the week's demand shock (the
    # imputed baseline), as real stock-outs are; weeks selling above it are the "stock-outs".
    truth_ph = recovered_ph = 0.0
    weeks_ph = 0
    for r in placebo:
        cap = max(math.floor(r['base_units']), 1)
        if r['units'] > cap:
            weeks_ph += 1
            truth_ph += r['units'] - cap
            recovered_ph += lost_units(r['log_base'], cap, tails(r['log_base']))

    category_gp = con.execute(f"""select sum(gross_profit_before_funding)::double from int_sales_enriched
        where fiscal_year = {DECISION_YEAR}""").fetchone()[0]
    primary = totals(records, DECISION_YEAR, 'non_promoted')
    ci_boot = store_bootstrap(records, DECISION_YEAR, 'non_promoted')
    sensitivity = {str(b): totals(censored_estimates(rows, clean, b)[0], DECISION_YEAR, 'non_promoted')['lost_gp']
                   for b in BIN_SENSITIVITY}
    ci = [min(ci_boot[0], *sensitivity.values()), max(ci_boot[1], *sensitivity.values())]
    promoted = totals(records, DECISION_YEAR, 'promoted')
    promoted['ci90_store_bootstrap'] = store_bootstrap(records, DECISION_YEAR, 'promoted')

    transfer = json.loads((RESULTS / 'delist.json').read_text(encoding='utf-8'))['transfer']
    keep = [1 - transfer['transfer_rate_ci90'][1], 1 - transfer['transfer_rate_ci90'][0]]
    result = {
        'design': {'zero_stock_weeks_all_years': len(records), 'bins': BINS, 'decision_year': DECISION_YEAR,
                   'note': 'Exploratory: estimator chosen after the planned estimator was seen to be negative.'},
        'preregistered_adjacent_weeks': adjacent_week_estimator(rows),
        'calibration': {'eligible_weeks': len(eligible), 'predicted_stockouts': predicted,
                        'observed_stockouts': observed, 'ratio': predicted / observed,
                        'passed': abs(predicted / observed - 1) <= CALIBRATION_TOLERANCE},
        'planted_censoring': {'weeks': len(placebo), 'true_lost_units': truth, 'recovered_lost_units': recovered,
                              'recovered_share': recovered / truth, 'below_truth': recovered <= truth,
                              'note': 'Censoring at 70% of the week\'s own sales ties the floor to the demand '
                                      'shock, unlike a real stock-out; see the post-hoc check.'},
        'planted_censoring_posthoc': {'weeks': weeks_ph, 'true_lost_units': truth_ph,
                                      'recovered_lost_units': recovered_ph, 'recovered_share': recovered_ph / truth_ph,
                                      'note': 'Not registered. Availability = imputed baseline units.'},
        'fy2025_non_promoted': {**primary, 'ci90_store_bootstrap': ci_boot, 'bin_sensitivity_lost_gp': sensitivity,
                                'ci90': ci, 'share_of_category_gp': primary['lost_gp'] / category_gp,
                                'ci90_share_of_category_gp': [v / category_gp for v in ci]},
        'fy2025_promoted_secondary': promoted,
        'fy2024_non_promoted': totals(records, 2024, 'non_promoted'),
        'category_gp_fy2025': category_gp,
        'substitution_context': {'delist_transfer_rate': transfer['transfer_rate'],
                                 'category_loss_range': [primary['lost_gp'] * keep[0], primary['lost_gp'] * keep[1]],
                                 'note': 'Lost SKU GP x (1 - transfer rate from the delist test); permanent '
                                         'delisting is not a temporary stock-out, so context only.'},
    }
    result['checks_passed'] = {'calibration_within_25pct': result['calibration']['passed'],
                               'planted_recovery_below_truth': result['planted_censoring']['below_truth']}
    result['credible'] = all(result['checks_passed'].values())
    result['decision'] = {'threshold_share_of_category_gp': PRIORITY_SHARE,
                          'outcome': 'prioritise_replenishment' if ci[0] > PRIORITY_SHARE * category_gp
                          else 'lower_priority_than_forecast_bias'}
    write_result('stockouts', round_floats(result))
    return result


if __name__ == '__main__':
    print(json.dumps(round_floats(main()), indent=1))
