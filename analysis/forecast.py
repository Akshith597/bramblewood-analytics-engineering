"""Q4 — forecast accuracy and bias (descriptive). Implements analysis/PLAN.md §Q4."""
import random

from analysis.common import connect, round_floats, write_result
from analysis.fe import quantile

SEED = 20261014

PANEL_SQL = """
with actual as (
    select sku_id, week_key, sum(units)::double as actual, sum(estimated_cogs)::double / nullif(sum(units), 0) as unit_cost
    from int_sales_enriched group by 1, 2
),
cal as (select week_key, week_start, fiscal_year, fiscal_week,
               row_number() over (order by week_start) as idx from stg_fiscal_calendar),
promoted as (
    select distinct p.sku_id, c.week_key from stg_promotions p
    join stg_fiscal_calendar c on c.week_start <= p.end_date and c.week_ending >= p.start_date
    where p.status = 'Approved'
)
select f.sku_id, i.subcategory, c.fiscal_year, f.week_key, f.forecast_units::double as forecast,
    coalesce(a.actual, 0) as actual, a.unit_cost,
    (c.week_start - r.week_start) / 7 as lead_weeks,
    (f.sku_id, f.week_key) in (select sku_id, week_key from promoted) as promoted,
    lag2.actual as naive_lag2, ly.actual as naive_last_year
from stg_forecast f
join stg_items i using (sku_id)
join cal c on c.week_key = f.week_key
join cal r on r.week_key = f.forecast_run_week
left join actual a on a.sku_id = f.sku_id and a.week_key = f.week_key
left join cal c2 on c2.idx = c.idx - 2
left join actual lag2 on lag2.sku_id = f.sku_id and lag2.week_key = c2.week_key
left join cal c3 on c3.fiscal_year = c.fiscal_year - 1 and c3.fiscal_week = c.fiscal_week
left join actual ly on ly.sku_id = f.sku_id and ly.week_key = c3.week_key
-- Same scored-pair rule as mart_forecast_accuracy: a row without a forecast quantity is not scored.
where f.forecast_units is not null
"""


def metrics(rows):
    actual = sum(r['actual'] for r in rows)
    err = sum(r['forecast'] - r['actual'] for r in rows)
    abs_err = sum(abs(r['forecast'] - r['actual']) for r in rows)
    return {'rows': len(rows), 'bias': err / actual, 'wape': abs_err / actual}


def bootstrap_bias(rows, draws=1999):
    by_sku = {}
    for r in rows:
        by_sku.setdefault(r['sku_id'], []).append(r)
    skus = sorted(by_sku)
    rng = random.Random(SEED)
    stats = []
    for _ in range(draws):
        sample = [r for s in (rng.choice(skus) for _ in skus) for r in by_sku[s]]
        stats.append(metrics(sample)['bias'])
    return [quantile(stats, 0.05), quantile(stats, 0.95)]


def main():
    con = connect()
    cur = con.execute(PANEL_SQL)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    fy25 = [r for r in rows if r['fiscal_year'] == 2025]
    result = {'fy2025': {**metrics(fy25), 'bias_ci90_sku_bootstrap': bootstrap_bias(fy25)}}
    result['by_subcategory'] = {s: metrics([r for r in fy25 if r['subcategory'] == s])
                                for s in sorted({r['subcategory'] for r in fy25})}
    result['by_promoted'] = {str(p): metrics([r for r in fy25 if r['promoted'] == p]) for p in (False, True)}
    result['by_lead_weeks_all_years'] = {str(k): metrics([r for r in rows if r['lead_weeks'] == k])
                                         for k in sorted({r['lead_weeks'] for r in rows})}
    comparable = [r for r in fy25 if r['naive_lag2'] is not None and r['naive_last_year'] is not None]
    mae = lambda key: sum(abs(r[key] - r['actual']) for r in comparable) / len(comparable)
    result['mase'] = {'rows': len(comparable), 'vs_lag2_naive': mae('forecast') / mae('naive_lag2'),
                      'vs_seasonal_naive': mae('forecast') / mae('naive_last_year'),
                      'bias_lag2_naive': sum(r['naive_lag2'] - r['actual'] for r in comparable)
                      / sum(r['actual'] for r in comparable)}
    costed = [r for r in fy25 if r['unit_cost'] is not None]
    result['fy2025_net_overforecast'] = {
        'units': sum(r['forecast'] - r['actual'] for r in costed),
        'cost': sum((r['forecast'] - r['actual']) * r['unit_cost'] for r in costed),
        'note': 'Net forecast minus actual at unit cost: inventory planned against demand that did not occur. '
                'An exposure; the realised loss depends on order policy and carrying cost, not in the extracts.'}
    # Out-of-sample bias correction: learn one scale factor per subcategory on FY2024 two-week-lead rows,
    # apply it to FY2025, and compare error. Tests whether the bias is stable enough to correct.
    fy24 = [r for r in rows if r['fiscal_year'] == 2024 and r['lead_weeks'] == 2]
    factor = {s: sum(r['actual'] for r in fy24 if r['subcategory'] == s)
              / sum(r['forecast'] for r in fy24 if r['subcategory'] == s) for s in {r['subcategory'] for r in fy24}}
    corrected = [{**r, 'forecast': r['forecast'] * factor[r['subcategory']]} for r in fy25]
    after = metrics(corrected)
    result['bias_correction_backtest'] = {
        'trained_on': 'FY2024 lead-2 rows', 'evaluated_on': 'FY2025',
        'factors': factor, 'wape_before': result['fy2025']['wape'], 'wape_after': after['wape'],
        'bias_before': result['fy2025']['bias'], 'bias_after': after['bias']}
    write_result('forecast', round_floats(result))
    return result


if __name__ == '__main__':
    import json
    r = round_floats(main())
    print(json.dumps({k: r[k] for k in ('fy2025', 'mase', 'fy2025_net_overforecast', 'bias_correction_backtest')}, indent=1))
