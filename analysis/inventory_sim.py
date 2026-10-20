"""Q4 — judge the forecast correction on an inventory simulation, not WAPE.

A forecast is worth what it does to the shelf: how often the item is there (service), how much stock it takes
(inventory carried) and the gross profit lost when it is not. This replays FY2025 store by store, SKU by SKU:

- Demand: units sold plus the censored-demand model's lost units on zero-stock weeks (analysis/stockouts.py).
- Forecast: the chain two-week-lead forecast, split to stores by each store's share of the SKU's units over the
  13 weeks that were known when the order was placed. "Corrected" multiplies it by the per-subcategory factors
  learned on FY2024 (analysis/results/forecast.json) — the correction the memo recommends.
- Policy: weekly review, order placed at the end of week w for delivery at the start of week w + 2 (the forecast
  is run two weeks ahead), rounded up to whole case packs (every receipt in the extract is a case-pack multiple).
  Order-up-to level = forecast for weeks w+1 and w+2 + z · σ · √2, where σ is the RMS of that forecast's own store
  errors over the trailing 13 weeks (so a less biased forecast also earns a smaller buffer); the order covers the
  gap to stock on hand plus the order already in transit. z is the safety factor.
- Calibration: with the raw forecast, z is the smallest grid value whose zero-stock rate is at or below the
  observed FY2025 rate; simulated stock and receipts are reported against the actual records.
- How stores actually replenish: weekly receipts are regressed on the same week's, the previous week's and the
  next week's sales and on opening stock. Salty snacks are typically delivered direct to store by vendor reps
  several times a week, which shows up as receipts tracking the same week's sales; under that process the chain
  forecast does not set store stock, and the simulation describes forecast-driven (warehouse) replenishment.
- Outcomes per policy: fill rate (units sold ÷ demand), share of store-SKU-weeks ending at zero, average stock at
  cost, lost GP (lost units × regular unit margin), carrying cost (an assumed 25% a year of stock at cost, with
  15%/35% sensitivity) and their sum, the cost of the policy.
- Verdict: each forecast gets its own best safety factor (lowest policy cost on the grid); the correction's value
  is the difference in those minimum policy costs. Also reported: the stock each forecast needs to reach the same
  fill rate (interpolated along its frontier). WAPE is not used.
"""
import csv
import json
import math

import numpy as np

from analysis.common import PANELS, RESULTS, connect, round_floats, write_result

CARRY_RATE = 0.25
CARRY_SENSITIVITY = (0.15, 0.35)
K_GRID = [round(x * 0.25, 2) for x in range(0, 25)]    # z = 0 … 6
FILL_TARGETS = (0.975, 0.98, 0.985, 0.99)
TRAIL = 13

ROWS_SQL = """
with c as (select week_key, fiscal_year, row_number() over (order by week_start) as w from stg_fiscal_calendar),
s as (select store_id, sku_id, week_key, sum(units)::double as units from int_sales_enriched group by all),
m as (select sku_id, avg(regular_unit_price - unit_cost)::double as reg_margin, avg(unit_cost)::double as unit_cost
      from int_sales_enriched where fiscal_year = 2025 group by 1)
select i.store_id, i.sku_id, c.w, c.fiscal_year, coalesce(s.units, 0) as units, i.on_hand_eow::double as on_hand,
       i.receipts_units::double as receipts, i.zero_stock_snapshot, it.case_pack, it.subcategory, m.reg_margin, m.unit_cost
from fct_inventory i join c using (week_key) join stg_items it using (sku_id) left join s using (store_id, sku_id, week_key)
left join m using (sku_id)
"""

FORECAST_SQL = """
with c as (select week_key, row_number() over (order by week_start) as w from stg_fiscal_calendar)
select f.sku_id, c.w, f.forecast_units::double from stg_forecast f join c using (week_key)
"""


def load(con):
    cur = con.execute(ROWS_SQL)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    lost = {}
    with (PANELS / 'stockout_lost_units.csv').open(encoding='utf-8') as handle:
        for r in csv.DictReader(handle):
            lost[(int(r['store_id']), r['sku_id'], int(r['w']))] = float(r['lost_units'])
    fc = {(sku, w): f for sku, w, f in con.execute(FORECAST_SQL).fetchall()}
    return rows, lost, fc


def build_arrays(rows, lost, fc):
    weeks = sorted({r['w'] for r in rows})
    w0 = min(r['w'] for r in rows if r['fiscal_year'] == 2025)
    series = sorted({(r['store_id'], r['sku_id']) for r in rows})
    idx = {s: i for i, s in enumerate(series)}
    n, t = len(series), max(weeks) + 1
    units, demand, on_hand, receipts = (np.zeros((n, t)) for _ in range(4))
    carried, zero = np.zeros((n, t), bool), np.zeros((n, t), bool)
    meta = {}
    for r in rows:
        i = idx[(r['store_id'], r['sku_id'])]
        units[i, r['w']] = r['units']
        demand[i, r['w']] = r['units'] + lost.get((r['store_id'], r['sku_id'], r['w']), 0.0)
        carried[i, r['w']] = True
        on_hand[i, r['w']] = r['on_hand']
        receipts[i, r['w']] = r['receipts']
        zero[i, r['w']] = r['zero_stock_snapshot']
        meta[i] = (r['sku_id'], r['subcategory'], r['case_pack'], r['reg_margin'] or 0.0, r['unit_cost'] or 0.0)
    sku = [meta[i][0] for i in range(n)]
    chain_units = {}
    for i, s in enumerate(sku):
        chain_units.setdefault(s, np.zeros(t))
        chain_units[s] += units[i]
    # Store forecast for week w: chain forecast × the store's share of the SKU over the TRAIL weeks ending w−3,
    # the last full week known when the order is placed at the end of week w−2.
    forecast = np.zeros((n, t))
    for i, s in enumerate(sku):
        cu = chain_units[s]
        for w in range(TRAIL + 3, t):
            lo, hi = max(1, w - 2 - TRAIL), w - 2
            den = cu[lo:hi].sum()
            share = units[i, lo:hi].sum() / den if den > 0 else 0.0
            forecast[i, w] = fc.get((s, w), 0.0) * share
    return {'series': series, 'w0': w0, 't': t, 'units': units, 'demand': demand, 'carried': carried,
            'on_hand': on_hand, 'receipts': receipts, 'zero': zero, 'forecast': forecast,
            'subcategory': np.array([meta[i][1] for i in range(n)]),
            'case_pack': np.array([meta[i][2] for i in range(n)], float),
            'margin': np.array([meta[i][3] for i in range(n)]), 'cost': np.array([meta[i][4] for i in range(n)])}


def trailing_sigma(a, forecast):
    """RMS store forecast error over the TRAIL weeks ending w (known when ordering at the end of week w)."""
    sq = np.where(a['carried'], (forecast - a['units']) ** 2, 0.0)
    cnt = a['carried'].astype(float)
    csq, ccnt = np.cumsum(sq, axis=1), np.cumsum(cnt, axis=1)
    sig = np.zeros_like(forecast)
    sig[:, TRAIL:] = (csq[:, TRAIL:] - csq[:, :-TRAIL]) / np.maximum(ccnt[:, TRAIL:] - ccnt[:, :-TRAIL], 1)
    return np.sqrt(sig)


def simulate(a, forecast, k, sigma=None):
    """Replay FY2025 under an order-up-to policy with safety factor k (= z). Returns outcome totals."""
    w0, t = a['w0'], a['t']
    sigma = trailing_sigma(a, forecast) if sigma is None else sigma
    inv = a['on_hand'][:, w0 - 1].copy()            # actual stock at the end of FY2024
    arrive = {w0: a['receipts'][:, w0].copy(), w0 + 1: a['receipts'][:, w0 + 1].copy()}  # already ordered
    sold_t = lost_t = stock_cost = zero_weeks = weeks = gp_lost = rec_t = 0.0
    for w in range(w0, t):
        live = a['carried'][:, w]
        avail = inv + arrive[w]
        sold = np.minimum(a['demand'][:, w], avail) * live
        lost = (a['demand'][:, w] - sold) * live
        inv = (avail - sold) * live
        sold_t += sold.sum()
        lost_t += lost.sum()
        rec_t += arrive[w].sum()
        gp_lost += (lost * a['margin']).sum()
        stock_cost += (inv * a['cost']).sum()
        zero_weeks += ((inv <= 0) & live).sum()
        weeks += live.sum()
        if w + 2 < t:
            # End of week w: order for delivery at the start of w + 2.
            target = forecast[:, w + 1] + forecast[:, w + 2] + k * sigma[:, w] * math.sqrt(2)
            need = np.maximum(target - inv - arrive[w + 1], 0.0)
            arrive[w + 2] = np.ceil(need / a['case_pack'] - 1e-9) * a['case_pack'] * a['carried'][:, w + 2]
    n_weeks = t - w0
    avg_stock = stock_cost / n_weeks
    out = {'k': k, 'fill_rate': sold_t / (sold_t + lost_t), 'zero_stock_share': zero_weeks / weeks,
           'units_sold': sold_t, 'lost_units': lost_t, 'receipts': rec_t, 'avg_stock_cost': avg_stock,
           'lost_gp': gp_lost, 'carrying_cost': CARRY_RATE * avg_stock}
    out['policy_cost'] = out['lost_gp'] + out['carrying_cost']
    out['policy_cost_carry_sensitivity'] = {str(c): gp_lost + c * avg_stock for c in CARRY_SENSITIVITY}
    return out


def observed_process(a):
    """Regress weekly receipts on sales the week before, the same week and the week after, and opening stock."""
    w0, t = a['w0'], a['t']
    live = a['carried'][:, w0:t - 1] & a['carried'][:, w0 - 1:t - 2] & a['carried'][:, w0 + 1:t]
    cols = [a['units'][:, w0 - 1:t - 2], a['units'][:, w0:t - 1], a['units'][:, w0 + 1:t], a['on_hand'][:, w0 - 1:t - 2]]
    x = np.column_stack([c[live] for c in cols] + [np.ones(live.sum())])
    y = a['receipts'][:, w0:t - 1][live]
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    resid = y - x @ beta
    return {'coef_sales_prev_week': beta[0], 'coef_sales_same_week': beta[1], 'coef_sales_next_week': beta[2],
            'coef_opening_stock': beta[3], 'r2': 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum(),
            'rows': int(live.sum())}


def actual_outcomes(a):
    w0, t = a['w0'], a['t']
    live = a['carried'][:, w0:t]
    inv = a['on_hand'][:, w0:t]
    lost = (a['demand'][:, w0:t] - a['units'][:, w0:t]) * live
    return {'fill_rate': a['units'][:, w0:t].sum() / a['demand'][:, w0:t].sum(),
            'zero_stock_share': (a['zero'][:, w0:t] & live).sum() / live.sum(),
            'avg_stock_cost': (inv * a['cost'][:, None]).sum() / (t - w0), 'receipts': a['receipts'][:, w0:t].sum(),
            'lost_gp': (lost * a['margin'][:, None]).sum()}


def tune(a, forecast, target_zero):
    """Smallest k on the grid whose zero-stock share is at or below the target."""
    sigma = trailing_sigma(a, forecast)
    runs = [simulate(a, forecast, k, sigma) for k in K_GRID]
    ok = [r for r in runs if r['zero_stock_share'] <= target_zero]
    return (min(ok, key=lambda r: r['k']) if ok else max(runs, key=lambda r: r['k'])), runs


def stock_at_fill(runs, target):
    """Stock at cost needed to reach a fill rate, interpolated along the frontier (None if out of reach)."""
    pts = sorted((r['fill_rate'], r['avg_stock_cost']) for r in runs)
    for (f0, s0), (f1, s1) in zip(pts, pts[1:]):
        if f0 <= target <= f1:
            return s0 + (s1 - s0) * (target - f0) / (f1 - f0) if f1 > f0 else s0
    return None


def main():
    con = connect()
    rows, lost, fc = load(con)
    a = build_arrays(rows, lost, fc)
    factors = json.loads((RESULTS / 'forecast.json').read_text(encoding='utf-8'))['bias_correction_backtest']['factors']
    corr = a['forecast'] * np.array([factors[s] for s in a['subcategory']])[:, None]
    actual = actual_outcomes(a)
    raw_cal, raw_runs = tune(a, a['forecast'], actual['zero_stock_share'])
    same_k = simulate(a, corr, raw_cal['k'])
    corr_tuned, corr_runs = tune(a, corr, raw_cal['zero_stock_share'])
    # Equal-stock comparison: the corrected policy holding no more stock than the calibrated raw one.
    equal_stock = max((r for r in corr_runs if r['avg_stock_cost'] <= raw_cal['avg_stock_cost']),
                      key=lambda r: r['k'], default=None)
    best_raw = min(raw_runs, key=lambda r: r['policy_cost'])
    best_corr = min(corr_runs, key=lambda r: r['policy_cost'])
    delta = best_raw['policy_cost'] - best_corr['policy_cost']
    at_fill = {str(f): {'raw': stock_at_fill(raw_runs, f), 'corrected': stock_at_fill(corr_runs, f)}
               for f in FILL_TARGETS}
    result = {
        'design': {'carry_rate': CARRY_RATE, 'z_grid': K_GRID, 'trail_weeks': TRAIL, 'weeks': a['t'] - a['w0'],
                   'store_sku_series': len(a['series'])},
        'actual_fy2025': actual,
        'observed_replenishment': observed_process(a),
        'raw_calibrated': raw_cal,
        'corrected_same_k': same_k,
        'corrected_same_service': corr_tuned,
        'corrected_equal_stock': equal_stock,
        'frontier': {'raw': [{k: r[k] for k in ('k', 'fill_rate', 'zero_stock_share', 'avg_stock_cost', 'lost_gp',
                                                 'policy_cost')} for r in raw_runs],
                     'corrected': [{k: r[k] for k in ('k', 'fill_rate', 'zero_stock_share', 'avg_stock_cost',
                                                       'lost_gp', 'policy_cost')} for r in corr_runs]},
        'min_cost': {'raw': {k: best_raw[k] for k in ('k', 'fill_rate', 'avg_stock_cost', 'lost_gp', 'policy_cost')},
                     'corrected': {k: best_corr[k] for k in ('k', 'fill_rate', 'avg_stock_cost', 'lost_gp',
                                                             'policy_cost')}},
        'stock_at_fill_rate': at_fill,
        'verdict': {
            'policy_cost_saving_at_best_z': delta,
            'policy_cost_saving_at_best_z_carry_sensitivity': {
                str(c): min(r['lost_gp'] + c * r['avg_stock_cost'] for r in raw_runs)
                - min(r['lost_gp'] + c * r['avg_stock_cost'] for r in corr_runs) for c in CARRY_SENSITIVITY},
            'stock_change_same_service': corr_tuned['avg_stock_cost'] - raw_cal['avg_stock_cost'],
            'lost_gp_change_same_z': same_k['lost_gp'] - raw_cal['lost_gp'],
            'material_threshold': 5000.0,
            'adopt': delta > 5000.0,
            'note': 'Correcting the bias without re-tuning safety stock removes the cushion the bias was providing; '
                    'the fair comparison re-tunes z to the same zero-stock rate. Applies to forecast-driven '
                    'replenishment; under the observed process store receipts follow same-week sales.'},
    }
    result = json.loads(json.dumps(result, default=lambda o: o.item()))   # numpy scalars → Python
    write_result('inventory_sim', round_floats(result))
    return result


if __name__ == '__main__':
    r = round_floats(main())
    for k in ('actual_fy2025', 'observed_replenishment', 'raw_calibrated', 'corrected_same_k', 'corrected_same_service', 'corrected_equal_stock',
              'min_cost', 'stock_at_fill_rate', 'verdict'):
        print(k, json.dumps(r[k]))
