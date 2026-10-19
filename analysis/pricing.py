"""Q3 — spring-2025 regular-price increases. Implements analysis/PLAN.md §Q3."""
import datetime
import math
import random

from analysis.common import connect, export_panel, round_floats, write_result
from analysis.fe import clustered_ci, feols, quantile, wald_pvalue, wild_draws

EXCLUDED_STORES = (112, 124)
HALF_WINDOW_DAYS = 91          # 13 weeks either side
POST_PROMO_DAYS = 14           # post-promotion dip exclusion
SEED = 20261014
EVENTS = {
    'golden_ridge_kettle': {'date': '2025-04-06', 'subcategory': 'Kettle Chips'},
    'bramble_select_tortilla': {'date': '2025-05-04', 'subcategory': 'Tortilla Chips'},
}
BACKTEST = {'crispwell_kettle_2024': {'date': '2024-08-25', 'subcategory': 'Kettle Chips'}}


def build_panel(con, name, date, subcategory, shift_days=0, export=True):
    """SKU-store-week panel for one event. `shift_days` moves the window for the fake-date test only."""
    con.execute("""
    create or replace temp table event_panel as
    with changes as (   -- every regular-price change after launch pricing
        select sku_id, price_zone, effective_start,
               ln(reg_retail / lag(reg_retail) over (partition by sku_id, price_zone order by effective_start)) as dlogp
        from stg_reg_price
    ),
    treated as (
        select sku_id, price_zone, dlogp from changes where effective_start = $date::date
    ),
    changed_in_window as (
        select distinct c.sku_id, i.subcategory from changes c join stg_items i using (sku_id)
        where c.dlogp is not null
          and c.effective_start between $centre - $half_window and $centre + $half_window
    ),
    groups as (
        select i.sku_id, i.subcategory, i.brand_type,
            case when i.sku_id in (select sku_id from treated) then 'treated'
                 when i.subcategory = $subcategory then 'sister'
                 else 'control' end as role
        from stg_items i
        where i.sku_id in (select sku_id from treated)
           or (i.sku_id not in (select sku_id from changed_in_window)
               and (i.subcategory = $subcategory
                    or i.subcategory not in (select subcategory from changed_in_window)))
    ),
    promo_weeks as (
        select distinct p.sku_id, st.store_id, cal.week_key
        from stg_promotions p
        join stg_stores st on p.store_scope = 'ALL' or p.store_scope = 'ZONE:' || st.price_zone
        join stg_fiscal_calendar cal
          on cal.week_start <= p.end_date + $post_promo_days and cal.week_ending >= p.start_date
    ),
    zone_dose as (
        select price_zone, avg(dlogp) as dose from treated group by 1
    )
    select s.sku_id || '|' || s.store_id as fe_a, s.store_id || '|' || s.week_key as fe_b,
        s.sku_id || '|' || s.week_key as fe_c,
        s.sku_id, s.store_id, s.week_key, g.role, g.subcategory,
        cal.week_start, cal.week_start >= $centre as post,
        ln(s.units)::double as log_units, s.units, s.net_sales::double as net_sales,
        s.unit_cost::double as unit_cost, s.regular_unit_price::double as reg_price,
        s.gross_sales::double / s.units as realized_price,
        coalesce(t.dlogp, 0)::double as own_dose, z.dose::double as zone_dose
    from int_sales_enriched s
    join groups g using (sku_id)
    join stg_fiscal_calendar cal using (week_key)
    left join treated t on t.sku_id = s.sku_id and t.price_zone = s.price_zone
    left join zone_dose z on z.price_zone = s.price_zone
    where s.units > 0
      and not list_contains($excluded, s.store_id)
      and cal.week_start between $centre - $half_window and $centre + $half_window - 1
      and (s.sku_id, s.store_id, s.week_key) not in (select sku_id, store_id, week_key from promo_weeks)
    """, {'date': date, 'centre': datetime.date.fromisoformat(date) + datetime.timedelta(days=shift_days),
          'subcategory': subcategory, 'half_window': HALF_WINDOW_DAYS, 'post_promo_days': POST_PROMO_DAYS,
          'excluded': list(EXCLUDED_STORES)})
    con.execute("""create or replace temp table event_panel as select *,
        case when role = 'treated' and post then own_dose else 0 end::double as x_own,
        case when role = 'sister' and post then zone_dose else 0 end::double as x_cross
        from event_panel""")
    rows = con.execute('select * from event_panel order by sku_id, store_id, week_key').fetchall()
    cols = [d[0] for d in con.description]
    if export:
        export_panel(name, [dict(zip(cols, r)) for r in rows])
    roles = dict(con.execute('select role, count(distinct sku_id) from event_panel group by 1').fetchall())
    price_check = con.execute("""select avg((abs(realized_price - reg_price) <= 0.01)::int) from event_panel""").fetchone()[0]
    return {'rows': len(rows), 'skus_by_role': roles, 'share_realized_price_equals_regular': price_check}


DESIGNS = {
    # Pre-registered: treated vs sister vs control-subcategory SKUs over time.
    'preregistered': ['fe_a', 'fe_b'],
    # Exploratory deviation 2 (adopted after the pre-registered design failed its checks): identify the
    # elasticity only from cross-zone differences in the size of the same SKU's increase in the same week.
    # SKU x week FE absorb chain-wide promotions, SKU seasonality and any SKU-level shock.
    'zone_dose': ['fe_a', 'fe_b', 'fe_c'],
}


def fit(con, cluster, design='preregistered'):
    con.execute(f'create or replace temp view est as select *, {cluster}::varchar as cluster_id from event_panel')
    return feols(con, 'est', 'log_units', ['x_own', 'x_cross'], DESIGNS[design], cluster_label=cluster)


def event_study(con, design='preregistered'):
    """Role x 4-week-bin terms (dose-weighted for the zone design); joint CR1 (store) Wald test on pre bins."""
    con.execute("""create or replace temp view est as
        with b as (select *, floor(date_diff('day', (select min(week_start) from event_panel where post), week_start) / 28)::int as bin
                   from event_panel)
        select *, store_id::varchar as cluster_id from b""")
    bins = [r[0] for r in con.execute('select distinct bin from est where bin != -1 order by 1').fetchall()]
    terms = []
    for b in bins:
        for role in ('treated', 'sister'):
            name = f'{role}_b{b}'.replace('-', 'm')
            weight = ('own_dose' if role == 'treated' else 'zone_dose') if design == 'zone_dose' else '1'
            terms.append((name, f"(role = '{role}' and bin = {b})::int::double * {weight} as {name}"))
    con.execute('create or replace temp view est_es as select *, ' + ', '.join(t for _, t in terms) + ' from est')
    es = feols(con, 'est_es', 'log_units', [n for n, _ in terms], DESIGNS[design], cluster_label='store_id')
    pre = [n for n, _ in terms if '_bm' in n and n.startswith('treated')]
    stat, p = wald_pvalue(es, pre)
    return {'treated_bins': {n: es['beta'][n] for n, _ in terms if n.startswith('treated')},
            'pre_bins_tested': len(pre), 'wald_stat': stat, 'pre_trend_p': p}


def gp_change(con, own_draws, cross_draws, annualize=52 / 13):
    """13-week gross-profit change vs the no-increase counterfactual, for each elasticity draw.

    Treated SKUs: actual GP minus counterfactual GP at the old price with volume exp(-eps*dose) higher.
    Sisters: actual GP minus counterfactual GP with volume exp(-eps_cross*dose) different. All post-window
    units in all eligible stores (promoted weeks included, since the increase also moved promoted volume).
    """
    rows = con.execute("""
        select g.role, coalesce(t.own_dose, 0), coalesce(z.zone_dose, 0),
               sum(s.units)::double, sum(s.net_sales)::double, sum(s.estimated_cogs)::double
        from int_sales_enriched s
        join (select distinct sku_id, role from event_panel where role in ('treated', 'sister')) g using (sku_id)
        join stg_fiscal_calendar cal using (week_key)
        left join (select distinct sku_id, store_id, own_dose from event_panel where role = 'treated') t
               on t.sku_id = s.sku_id and t.store_id = s.store_id
        left join (select distinct store_id, zone_dose from event_panel) z on z.store_id = s.store_id
        where not list_contains(?, s.store_id)
          and cal.week_start >= (select min(week_start) from event_panel where post)
          and cal.week_start <= (select max(week_start) from event_panel)
        group by all""", [list(EXCLUDED_STORES)]).fetchall()
    out = []
    for e_own, e_cross in zip(own_draws, cross_draws):
        delta = 0.0
        for role, dose, zdose, units, sales, cogs in rows:
            if role == 'treated':
                cf_units = units * math.exp(-e_own * dose)
                cf_sales = sales / units * math.exp(-dose) * cf_units
                cf_cogs = cogs / units * cf_units
            else:
                cf_units = units * math.exp(-e_cross * zdose)
                cf_sales, cf_cogs = sales / units * cf_units, cogs / units * cf_units
            delta += (sales - cogs) - (cf_sales - cf_cogs)
        out.append(delta * annualize)
    return out


def mvn_draws(fit_, names, n, seed):
    """Normal draws using the CR1 covariance (2x2 Cholesky)."""
    idx = [list(fit_['beta']).index(x) for x in names]
    v = [[fit_['_vcov'][i][j] for j in idx] for i in idx]
    l11 = math.sqrt(v[0][0]); l21 = v[1][0] / l11; l22 = math.sqrt(max(v[1][1] - l21 ** 2, 0))
    rng = random.Random(seed)
    draws = []
    for _ in range(n):
        z1, z2 = rng.gauss(0, 1), rng.gauss(0, 1)
        draws.append({names[0]: fit_['beta'][names[0]] + l11 * z1,
                      names[1]: fit_['beta'][names[1]] + l21 * z1 + l22 * z2})
    return draws


def analyse_event(con, name, spec, design, draws=4999):
    info = build_panel(con, f'{name}_{design}', spec['date'], spec['subcategory'])
    store_fit, sku_fit = fit(con, 'store_id', design), fit(con, 'sku_id', design)
    sku_samples = wild_draws(sku_fit, draws, SEED)
    result = {'event_date': spec['date'], **info}
    for x in ('x_own', 'x_cross'):
        store_ci, sku_ci = clustered_ci(store_fit, x), [
            store_fit['beta'][x] - quantile([abs(s[x] - store_fit['beta'][x]) for s in sku_samples], 0.90),
            store_fit['beta'][x] + quantile([abs(s[x] - store_fit['beta'][x]) for s in sku_samples], 0.90)]
        wider = 'sku_wild' if sku_ci[1] - sku_ci[0] > store_ci[1] - store_ci[0] else 'store_cr1'
        result[x] = {'elasticity': store_fit['beta'][x], 'se_store_cr1': store_fit['se'][x],
                     'ci90_store_cr1': store_ci, 'ci90_sku_wild': sku_ci, 'sku_clusters': sku_fit['clusters'],
                     'store_clusters': store_fit['clusters'], 'reported_ci90': max(store_ci, sku_ci,
                     key=lambda c: c[1] - c[0]), 'reported_ci_source': wider}
    result['n'] = store_fit['n']
    result['event_study'] = event_study(con, design)
    # Planted elasticity: add -1.5 x dose to treated post log units; the estimate must move by exactly -1.5.
    con.execute('create or replace temp table _orig as select * from event_panel')
    con.execute("create or replace temp table event_panel as select * replace (log_units + -1.5 * x_own as log_units) from _orig")
    planted = fit(con, 'store_id', design)['beta']['x_own'] - store_fit['beta']['x_own']
    con.execute('create or replace temp table event_panel as select * from _orig')
    result['planted_elasticity_recovered'] = planted
    # Dollar impact: draws from the more conservative of the two inference schemes.
    names = ['x_own', 'x_cross']
    normal = mvn_draws(store_fit, names, draws, SEED)
    gp_sku = gp_change(con, [s['x_own'] for s in sku_samples], [s['x_cross'] for s in sku_samples])
    gp_store = gp_change(con, [s['x_own'] for s in normal], [s['x_cross'] for s in normal])
    point = gp_change(con, [store_fit['beta']['x_own']], [store_fit['beta']['x_cross']])[0]
    ci_sku = [quantile(gp_sku, 0.05), quantile(gp_sku, 0.95)]
    ci_store = [quantile(gp_store, 0.05), quantile(gp_store, 0.95)]
    ci = max(ci_sku, ci_store, key=lambda c: c[1] - c[0])
    result['annual_gp_change'] = {'point': point, 'ci90': ci, 'ci90_store_cr1': ci_store, 'ci90_sku_wild': ci_sku}
    result['decision'] = 'good_decision' if ci[0] > 0 else ('bad_decision' if ci[1] < 0 else 'inconclusive')
    # Fake date 26 weeks earlier with the same groups and rules.
    build_panel(con, f'{name}_{design}_fake', spec['date'], spec['subcategory'], shift_days=-182)
    fake = fit(con, 'store_id', design)
    result['fake_date'] = {'elasticity': fake['beta']['x_own'], 'ci90_store_cr1': clustered_ci(fake, 'x_own'),
                           'cross': fake['beta']['x_cross'], 'cross_ci90_store_cr1': clustered_ci(fake, 'x_cross')}
    return result


def breakeven(con, spec):
    """Own-price elasticity at which the increase leaves the treated SKUs' gross profit unchanged.

    Uses the pre-increase regular price p0, post-increase regular price p1 and unit cost c (unit-weighted over
    the 13 weeks before the event): GP-neutral when (p1 - c) q1 = (p0 - c) q0, i.e.
    eps* = ln((p0 - c) / (p1 - c)) / ln(p1 / p0). No causal assumption is involved.
    """
    p0, p1, c, units = con.execute("""
        with t as (
            select sku_id, price_zone, reg_retail as p1,
                   lag(reg_retail) over (partition by sku_id, price_zone order by effective_start) as p0,
                   effective_start
            from stg_reg_price)
        select sum(t.p0 * s.units) / sum(s.units), sum(t.p1 * s.units) / sum(s.units),
               sum(s.unit_cost * s.units) / sum(s.units), sum(s.units)
        from int_sales_enriched s
        join stg_fiscal_calendar cal using (week_key)
        join t on t.sku_id = s.sku_id and t.price_zone = s.price_zone and t.effective_start = $date::date
        where cal.week_start between $date::date - $half_window and $date::date - 1
    """, {'date': spec['date'], 'half_window': HALF_WINDOW_DAYS}).fetchone()
    p0, p1, c = float(p0), float(p1), float(c)
    return {'pre_price': p0, 'post_price': p1, 'unit_cost': c, 'price_increase': p1 / p0 - 1,
            'margin_before': (p0 - c) / p0, 'breakeven_elasticity': math.log((p0 - c) / (p1 - c)) / math.log(p1 / p0)}


def pooled_elasticities(con):
    """All non-promoted regular-price variation, by subcategory, plus a private-label slope shift."""
    con.execute("""
    create or replace temp table est_pooled as
    with promo_weeks as (
        select distinct p.sku_id, st.store_id, cal.week_key
        from stg_promotions p
        join stg_stores st on p.store_scope = 'ALL' or p.store_scope = 'ZONE:' || st.price_zone
        join stg_fiscal_calendar cal
          on cal.week_start <= p.end_date + $post_promo_days and cal.week_ending >= p.start_date
    )
    select s.sku_id || '|' || s.store_id as fe_a, s.store_id || '|' || s.week_key as fe_b,
        i.subcategory || '|' || cal.fiscal_year || '|' || cal.fiscal_period as fe_c,
        s.store_id::varchar as cluster_id, ln(s.units)::double as log_units,
        ln(s.regular_unit_price)::double as lp, i.subcategory, i.brand_type
    from int_sales_enriched s join stg_items i using (sku_id) join stg_fiscal_calendar cal using (week_key)
    where s.units > 0 and not list_contains($excluded, s.store_id)
      and (s.sku_id, s.store_id, s.week_key) not in (select sku_id, store_id, week_key from promo_weeks)
    """, {'post_promo_days': POST_PROMO_DAYS, 'excluded': list(EXCLUDED_STORES)})
    subcats = [r[0] for r in con.execute('select distinct subcategory from est_pooled order by 1').fetchall()]
    names = {s: 'lp_' + s.lower().replace(' ', '_') for s in subcats}
    changes = dict(con.execute("""select i.subcategory, count(*) from stg_reg_price p join stg_items i using (sku_id)
        where p.effective_start > (select min(effective_start) from stg_reg_price) group by 1""").fetchall())
    # Subcategory names come from the data, so they are bound; only the generated column names are composed.
    cols = ', '.join(f"case when subcategory = $s{i} then lp else 0 end as {n}" for i, n in enumerate(names.values()))
    con.execute(f"create or replace temp table est_pooled_by_subcat as select *, {cols}, "
                "case when brand_type = 'Private Label' then lp else 0 end as lp_private_label from est_pooled",
                {f's{i}': s for i, s in enumerate(names)})
    xs = list(names.values()) + ['lp_private_label']
    f = feols(con, 'est_pooled_by_subcat', 'log_units', xs, ['fe_a', 'fe_b', 'fe_c'], cluster_label='store_id')
    out = {}
    for s, n in names.items():
        se = f['se'][n]
        out[s] = {'elasticity': f['beta'][n], 'se_store_cr1': se, 'ci90': clustered_ci(f, n),
                  'regular_price_changes': changes.get(s, 0),
                  'identified': changes.get(s, 0) >= 6 and se < 0.75}
    return {'by_subcategory': out,
            'private_label_shift': {'elasticity_shift': f['beta']['lp_private_label'],
                                    'ci90': clustered_ci(f, 'lp_private_label'),
                                    'note': 'identified only from Bramble Select tortilla and trail-mix changes'},
            'n': f['n'], 'fe_iterations': f['fe_iterations']}


def main():
    con = connect()
    result = {}
    for design in DESIGNS:
        block = {name: analyse_event(con, name, spec, design) for name, spec in EVENTS.items()}
        back = {}
        for name, spec in BACKTEST.items():
            info = build_panel(con, f'{name}_{design}', spec['date'], spec['subcategory'])
            f = fit(con, 'store_id', design)
            back[name] = {**info, 'elasticity': f['beta']['x_own'], 'se_store_cr1': f['se']['x_own']}
        gr = block['golden_ridge_kettle']['x_own']
        ck = back['crispwell_kettle_2024']
        band = 1.6448536269514722 * math.sqrt(ck['se_store_cr1'] ** 2 + gr['se_store_cr1'] ** 2)
        block['backtest'] = {**back, 'predicted_golden_ridge_elasticity': ck['elasticity'],
                             'prediction_interval90': [ck['elasticity'] - band, ck['elasticity'] + band],
                             'observed_golden_ridge_elasticity': gr['elasticity'],
                             'covered': abs(gr['elasticity'] - ck['elasticity']) <= band}
        for name in EVENTS:
            ev = block[name]
            fake_ci = ev['fake_date']['ci90_store_cr1']
            ev['checks_passed'] = {'pre_trend': ev['event_study']['pre_trend_p'] > 0.10,
                                   'fake_date': fake_ci[0] <= 0 <= fake_ci[1],
                                   'backtest': block['backtest']['covered']}
            ev['credible'] = all(ev['checks_passed'].values())
        result[design] = block
    result['pooled'] = pooled_elasticities(con)
    for name, spec in EVENTS.items():
        be = breakeven(con, spec)
        credible = [d for d in DESIGNS if result[d][name]['credible']]
        # Conditional dollar impact: own effect only, at the pooled subcategory elasticity (+ private-label
        # shift where relevant). The pooled model has no event-level validation, so this is a scenario.
        pooled = result['pooled']['by_subcategory'][spec['subcategory']]
        shift = result['pooled']['private_label_shift'] if name == 'bramble_select_tortilla' else None
        eps = pooled['elasticity'] + (shift['elasticity_shift'] if shift else 0)
        lo = pooled['ci90'][0] + (shift['ci90'][0] if shift else 0)
        hi = pooled['ci90'][1] + (shift['ci90'][1] if shift else 0)
        build_panel(con, name, spec['date'], spec['subcategory'], export=False)
        gp = gp_change(con, [eps, lo, hi], [0.0, 0.0, 0.0])
        result.setdefault('decisions', {})[name] = {
            **be, 'credible_designs': credible,
            'outcome': result[credible[0]][name]['decision'] if credible else 'not_identified',
            'pooled_elasticity_used': eps, 'pooled_elasticity_range': [lo, hi],
            'conditional_annual_gp_change': gp[0],
            'conditional_annual_gp_range': sorted(gp[1:]),
            'conditional_note': 'Scenario at the pooled elasticity; endpoints add the CI bounds of each term, '
                                'which is conservative. Not validated at the event level.'}
    write_result('pricing', round_floats(result))
    return result


if __name__ == '__main__':
    import json
    r = round_floats(main())
    print(json.dumps({d: {k: {x: r[d][k].get(x) for x in ('x_own', 'annual_gp_change', 'decision', 'checks_passed')}
                          for k in EVENTS} for d in DESIGNS}, indent=1))
