"""Test the forecast dollar claim against the physical records (receipts and on-hand), and refit forecast bias
on weeks that did not stock out.

The memo's $1.05M is forecast minus actual at unit cost: inventory *planned* against demand that did not occur.
It only becomes money if the over-forecast turned into stock. The inventory extract records what each store
received and held every week, so this checks whether it did:

1. Flow identity: on_hand[t-1] + receipts[t] - units[t] = on_hand[t], per store-SKU-week (the residual is shrink
   or count error). If it holds, receipts and on-hand are a trustworthy physical record.
2. Did receipts follow the forecast or the sales? Chain SKU-week receipts vs forecast vs actual.
3. Did store stock build up? On-hand at cost, end of FY2024 vs end of FY2025, and weeks of supply, comparable
   stores (open all 104 weeks, no remodel) so the new store's opening fill is not mistaken for excess.
4. Restate the $1.05M as the physical excess at store level (DC stock is not in the extracts).
5. Refit forecast bias on chain SKU-weeks where no store ended the week at zero stock, so censored demand does not
   inflate the bias; repeat the FY2024-trained correction on in-stock weeks only. Stock-outs happen in demand
   spikes, so dropping those weeks also drops the weeks the forecast under-calls; the bias is therefore also
   computed on all weeks with censored demand restored (actual + the stock-out model's lost units).
"""
import csv
import random

from analysis.common import PANELS, connect, round_floats, write_result
from analysis.fe import quantile
from analysis.forecast import PANEL_SQL, SEED, metrics

FLOW_SQL = """
with s as (select store_id, sku_id, week_key, sum(units)::double as units,
                  sum(estimated_cogs)::double / nullif(sum(units), 0) as unit_cost
           from int_sales_enriched group by all),
c as (select week_key, fiscal_year, row_number() over (order by week_start) as idx from stg_fiscal_calendar),
cost as (select sku_id, avg(unit_cost)::double as unit_cost from stg_item_cost group by 1),
j as (
    select i.store_id, i.sku_id, i.week_key, c.idx, c.fiscal_year, i.receipts_units::double as receipts,
        i.on_hand_eow::double as on_hand, coalesce(s.units, 0) as units, i.zero_stock_snapshot,
        lag(i.on_hand_eow) over (partition by i.store_id, i.sku_id order by c.idx)::double as prev,
        coalesce(s.unit_cost, cost.unit_cost) as unit_cost
    from fct_inventory i join c using (week_key) left join s using (store_id, sku_id, week_key)
    left join cost using (sku_id)
)
select * from j
"""

COMPARABLE_SQL = """
select store_id from int_sales_enriched join stg_stores using (store_id)
where remodel_start is null group by 1 having count(distinct week_key) = 104
"""


def flow_identity(rows):
    out = {}
    for year in (2024, 2025):
        rs = [r for r in rows if r['fiscal_year'] == year and r['prev'] is not None]
        resid = [r['prev'] + r['receipts'] - r['units'] - r['on_hand'] for r in rs]
        out[str(year)] = {'store_sku_weeks': len(rs), 'receipts_units': sum(r['receipts'] for r in rs),
                          'units_sold': sum(r['units'] for r in rs),
                          'exact_share': sum(abs(x) < 1e-9 for x in resid) / len(rs),
                          'shrink_units': sum(resid), 'shrink_share_of_receipts': sum(resid) / sum(r['receipts'] for r in rs)}
    return out


def on_hand_change(rows, stores, unit_cost):
    snap = lambda week: sum(r['on_hand'] * unit_cost[r['sku_id']] for r in rows
                            if r['week_key'] == week and r['store_id'] in stores)
    start, end = snap('FY2024-W52'), snap('FY2025-W52')
    by_year = {}
    for year in (2024, 2025):
        rs = [r for r in rows if r['fiscal_year'] == year and r['store_id'] in stores]
        weeks = len({r['week_key'] for r in rs})
        avg_on_hand = sum(r['on_hand'] for r in rs) / weeks
        avg_sold = sum(r['units'] for r in rs) / weeks
        by_year[str(year)] = {'avg_on_hand_units': avg_on_hand, 'avg_weekly_units_sold': avg_sold,
                              'weeks_of_supply': avg_on_hand / avg_sold,
                              'avg_on_hand_cost': sum(r['on_hand'] * unit_cost[r['sku_id']] for r in rs) / weeks}
    return {'on_hand_cost_end_fy2024': start, 'on_hand_cost_end_fy2025': end, 'change': end - start,
            'by_year': by_year}


def receipts_vs_forecast(rows, panel):
    """Chain SKU-week: do receipts track the forecast or the sales?"""
    rec = {}
    for r in rows:
        if r['fiscal_year'] == 2025:
            key = (r['sku_id'], r['week_key'])
            rec[key] = rec.get(key, 0.0) + r['receipts']
    joined = [(p['forecast'], p['actual'], rec.get((p['sku_id'], p['week_key']), 0.0), p['unit_cost'])
              for p in panel if p['fiscal_year'] == 2025 and p['unit_cost'] is not None]
    f, a, rc = (sum(x[i] for x in joined) for i in range(3))
    # Which explains receipts better week to week: this week's forecast or this week's sales?
    def r2(xs, ys):
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        return sxy * sxy / (sxx * syy)
    return {'sku_weeks': len(joined), 'forecast_units': f, 'actual_units': a, 'receipt_units': rc,
            'forecast_over_actual': f / a - 1, 'receipts_over_actual': rc / a - 1,
            'over_forecast_cost': sum((x[0] - x[1]) * x[3] for x in joined),
            'receipts_minus_sales_cost': sum((x[2] - x[1]) * x[3] for x in joined),
            'r2_receipts_on_forecast': r2([x[0] for x in joined], [x[2] for x in joined]),
            'r2_receipts_on_sales': r2([x[1] for x in joined], [x[2] for x in joined])}


def bootstrap(rows, draws=1999):
    by_sku = {}
    for r in rows:
        by_sku.setdefault(r['sku_id'], []).append(r)
    skus, rng = sorted(by_sku), random.Random(SEED)
    stats = [metrics([r for s in (rng.choice(skus) for _ in skus) for r in by_sku[s]])['bias'] for _ in range(draws)]
    return [quantile(stats, 0.05), quantile(stats, 0.95)]


def restored_demand(con):
    """Chain SKU-week lost units from analysis/stockouts.py (run first), keyed by week_key."""
    week = dict(con.execute('select row_number() over (order by week_start), week_key from stg_fiscal_calendar')
                .fetchall())
    lost = {}
    with (PANELS / 'stockout_lost_units.csv').open(encoding='utf-8') as handle:
        for r in csv.DictReader(handle):
            key = (r['sku_id'], week[int(r['w'])])
            lost[key] = lost.get(key, 0.0) + float(r['lost_units'])
    return lost


def bias_refit(rows, panel, lost):
    stocked_out = {(r['sku_id'], r['week_key']) for r in rows if r['zero_stock_snapshot']}
    for p in panel:
        p['in_stock'] = (p['sku_id'], p['week_key']) not in stocked_out
    fy25 = [p for p in panel if p['fiscal_year'] == 2025]
    ins = [p for p in fy25 if p['in_stock']]
    out = {'all_weeks': {**metrics(fy25), 'ci90': bootstrap(fy25)},
           'in_stock_weeks': {**metrics(ins), 'ci90': bootstrap(ins)},
           'stocked_out_weeks': metrics([p for p in fy25 if not p['in_stock']]),
           'in_stock_by_promoted': {str(k): metrics([p for p in ins if p['promoted'] == k]) for k in (False, True)},
           'in_stock_by_subcategory': {s: {**metrics([p for p in ins if p['subcategory'] == s]),
                                           'ci90': bootstrap([p for p in ins if p['subcategory'] == s], 999)}
                                       for s in sorted({p['subcategory'] for p in ins})}}
    restored = [{**p, 'actual': p['actual'] + lost.get((p['sku_id'], p['week_key']), 0.0)} for p in fy25]
    out['restored_demand_all_weeks'] = {**metrics(restored), 'ci90': bootstrap(restored),
                                        'lost_units_added': sum(r['actual'] for r in restored)
                                        - sum(p['actual'] for p in fy25)}
    out['selection_note'] = ('Stock-out weeks are demand spikes the forecast under-calls, so dropping them raises '
                             'the measured bias; restoring censored demand on all weeks is the less selected '
                             'estimate and is the one carried into the plan.')
    train = [p for p in panel if p['fiscal_year'] == 2024 and p['lead_weeks'] == 2 and p['in_stock']]
    factor = {s: sum(p['actual'] for p in train if p['subcategory'] == s)
              / sum(p['forecast'] for p in train if p['subcategory'] == s) for s in {p['subcategory'] for p in train}}
    corrected = [{**p, 'forecast': p['forecast'] * factor[p['subcategory']]} for p in ins]
    out['correction_in_stock'] = {'factors': factor, 'trained_on': 'FY2024 lead-2 in-stock chain SKU-weeks',
                                  'evaluated_on': 'FY2025 in-stock chain SKU-weeks',
                                  'before': metrics(ins), 'after': metrics(corrected)}
    return out


def main():
    con = connect()
    cur = con.execute(FLOW_SQL)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur = con.execute(PANEL_SQL)
    cols = [d[0] for d in cur.description]
    panel = [dict(zip(cols, r)) for r in cur.fetchall()]
    comparable = {r[0] for r in con.execute(COMPARABLE_SQL).fetchall()}
    unit_cost = {}
    for r in rows:
        if r['unit_cost'] is not None:
            unit_cost.setdefault(r['sku_id'], r['unit_cost'])
    all_stores = {r['store_id'] for r in rows}

    flow = flow_identity(rows)
    receipts = receipts_vs_forecast(rows, panel)
    stock_comp = on_hand_change(rows, comparable, unit_cost)
    stock_all = on_hand_change(rows, all_stores, unit_cost)
    refit = bias_refit(rows, panel, restored_demand(con))
    # Excess store stock: the rise in average on-hand at cost in comparable stores (the year-end snapshot fell).
    excess = max(0.0, stock_comp['by_year']['2025']['avg_on_hand_cost'] - stock_comp['by_year']['2024']['avg_on_hand_cost'])
    result = {
        'flow_identity': flow, 'receipts_vs_forecast_fy2025': receipts,
        'store_stock_comparable': stock_comp, 'store_stock_all_stores': stock_all,
        'comparable_stores': len(comparable),
        'restated': {
            'memo_over_forecast_cost': receipts['over_forecast_cost'],
            'receipts_minus_sales_cost': receipts['receipts_minus_sales_cost'],
            'excess_store_stock_cost': excess,
            'excess_share_of_memo_figure': excess / receipts['over_forecast_cost'],
            'reached_stores': excess > 0.1 * receipts['over_forecast_cost'],
            'note': 'Store receipts followed sales, not the forecast; the over-forecast is a planning-number '
                    'error. Distribution-centre stock is not in the extracts, so excess held upstream cannot '
                    'be ruled out or measured.'},
        'bias_refit': refit,
    }
    write_result('physical', round_floats(result))
    return result


if __name__ == '__main__':
    import json
    r = round_floats(main())
    print(json.dumps({k: r[k] for k in ('flow_identity', 'receipts_vs_forecast_fy2025', 'store_stock_comparable',
                                        'restated')}, indent=1))
    print(json.dumps({k: r['bias_refit'][k] for k in ('all_weeks', 'in_stock_weeks', 'stocked_out_weeks', 'restored_demand_all_weeks',
                                                      'in_stock_by_promoted', 'correction_in_stock')}, indent=1))
