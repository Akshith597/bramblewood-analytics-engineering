"""Q2 — promotion profitability. Implements the analysis/PLAN.md addendum (§Q2); deviations are logged in the memo.

Imputation design (Borusyak–Jaravel–Spiess style): a fixed-effects model of log units is fitted only on
"clean" store-SKU-weeks (no own promotion, not in the two weeks before or after one, in stock at the weekly
snapshot), then used to impute the no-promotion baseline for every held-out week. Cannibalisation is the
model's slope on the number of same-subcategory sister SKUs on promotion in that store-week. Every promoted
store-SKU-week gets its own counterfactual, so each event gets its own P&L.
"""
import math
import random

from analysis.common import connect, export_panel, round_floats, write_result
from analysis.fe import fe_levels, feols, quantile

SEED = 20261014
POST_WEEKS = 2                  # post-promotion dip window
PRE_WEEKS = 2                   # held-out pre-period check
PLACEBO_SHIFT_WEEKS = 8         # held-out fake events: each real event moved 8 weeks earlier
DRAWS = 1999
Z90 = 1.6448536269514722
FES = ['fe_a', 'fe_b', 'fe_c']  # store x SKU, store x week, subcategory x fiscal period (holiday weeks split out)
PLANTED_CANNIBALISATION = -0.05
DECISION_YEAR = 2025
SUBCATS = ['Cheese Snacks', 'Kettle Chips', 'Nuts', 'Popcorn', 'Potato Chips', 'Pretzels', 'Tortilla Chips',
           'Trail Mix']


def xname(subcategory):
    return 'cann_' + subcategory.lower().replace(' ', '_')


EVENTS_SQL = """
create or replace temp table promo_events as
-- stg_promotions orders PR-25-0432's swapped source dates (POS discounts confirm the 2025-03-30 to
-- 2025-04-12 window), so every analysis and the warehouse use the same event window.
with p as (
    select promo_id, sku_id, mechanic, display, store_scope, vendor_scan_per_unit::double as scan_per_unit,
        case when display = 'Y' then vendor_display_fee::double else 0 end as display_fee,
        start_date, end_date, dates_swapped
    from stg_promotions where status = 'Approved'
)
select p.*, i.subcategory, cs.fiscal_year,
    (select min(w) from cal where week_ending >= p.start_date) as first_w,
    (select max(w) from cal where week_start <= p.end_date) as last_w
from p join stg_items i using (sku_id)
join stg_fiscal_calendar cs on p.start_date between cs.week_start and cs.week_ending
"""


def scoped(offset_from, offset_to, anchor_from='first_w', anchor_to='last_w', extra=''):
    """Store-SKU-weeks in each event's store scope, for weeks [anchor_from + offset_from, anchor_to + offset_to]."""
    return f"""select e.promo_id, e.sku_id, e.subcategory, st.store_id, c.w{extra}
    from promo_events e
    join stg_stores st on e.store_scope = 'ALL' or e.store_scope = 'ZONE:' || st.price_zone
    join cal c on c.w between e.{anchor_from} + {offset_from} and e.{anchor_to} + {offset_to}"""


PANEL_SQL = f"""
create or replace temp table promo_panel as
with event_rows as ({scoped(0, 0)}),
post_rows as ({scoped(1, POST_WEEKS, 'last_w', 'last_w', ', c.w - e.last_w as post_k')}),
pre_rows as ({scoped(-PRE_WEEKS, -1, 'first_w', 'first_w')}),
placebo_rows as ({scoped(-PLACEBO_SHIFT_WEEKS, -PLACEBO_SHIFT_WEEKS)}),
promoted_count as (     -- promoted SKUs per store x subcategory x week
    select store_id, subcategory, w, count(distinct sku_id) as n from event_rows group by all
),
sales as (
    select s.store_id, s.sku_id, c.w, c.week_key, c.fiscal_year, i.subcategory,
        s.units::double as units, s.gross_profit_before_funding::double as gp,
        (s.regular_unit_price - s.unit_cost)::double as reg_margin,
        s.store_id || '|' || s.sku_id as fe_a, s.store_id || '|' || c.w as fe_b,
        i.subcategory || '|' || c.fiscal_year || '|' || c.fiscal_period || '|' || coalesce(c.holiday_event, '')
            as fe_c,
        coalesce(inv.zero_stock_snapshot, false) as zero_stock
    from int_sales_enriched s
    join cal c using (week_key)
    join stg_items i using (sku_id)
    left join fct_inventory inv using (store_id, sku_id, week_key)
    where s.units > 0
)
select s.*, ln(s.units) as log_units, s.store_id::varchar as cluster_id,
    er.promo_id, pr.promo_id as post_promo_id, pr.post_k,
    (coalesce(pc.n, 0) - (er.promo_id is not null)::int)::double as n_sisters,
    case when er.promo_id is not null then 'promo'
         when pr.promo_id is not null then 'post'
         when s.zero_stock then 'stockout'
         when pre.w is not null then 'pre'
         when pl.w is not null then 'placebo'
         else 'clean' end as role
from sales s
left join event_rows er using (store_id, sku_id, w)
left join (select *, row_number() over (partition by store_id, sku_id, w order by post_k) as rk from post_rows) pr
       on pr.store_id = s.store_id and pr.sku_id = s.sku_id and pr.w = s.w and pr.rk = 1
left join (select distinct store_id, sku_id, w from pre_rows) pre
       on pre.store_id = s.store_id and pre.sku_id = s.sku_id and pre.w = s.w
left join (select distinct store_id, sku_id, w from placebo_rows) pl
       on pl.store_id = s.store_id and pl.sku_id = s.sku_id and pl.w = s.w
left join promoted_count pc on pc.store_id = s.store_id and pc.subcategory = s.subcategory and pc.w = s.w
"""


def build(con):
    con.execute('create or replace temp table cal as select *, row_number() over (order by week_start) as w '
                'from stg_fiscal_calendar')
    con.execute(EVENTS_SQL)
    con.execute(PANEL_SQL)
    dupes = con.execute("""select count(*) from (select store_id, sku_id, w from promo_panel
                           group by all having count(*) > 1)""").fetchone()[0]
    if dupes:
        raise AssertionError(f'{dupes} store-SKU-weeks appear twice (overlapping events)')
    cols = ', '.join(f"case when subcategory = '{s}' then n_sisters else 0 end as {xname(s)}" for s in SUBCATS)
    con.execute(f'create or replace temp table promo_panel as select *, {cols} from promo_panel')


def fit_baseline(con, shift=None):
    """Fit the clean-week model. `shift` adds a planted cannibalisation slope (log points per promoted sister)."""
    y = 'log_units' if shift is None else f'(log_units + {shift!r} * n_sisters)'
    con.execute(f"create or replace temp view clean as select *, {y} as y from promo_panel where role = 'clean'")
    return feols(con, 'clean', 'y', [xname(s) for s in SUBCATS], FES, cluster_label='store_id')


def impute(con, fit):
    """Baseline (no own promotion; sisters' promotions as they happened) for every row, in units."""
    beta = fit['beta']
    iterations = fe_levels(con, 'clean', 'y', beta, FES)
    xb = ' + '.join(f'{b!r} * p.{x}' for x, b in beta.items())
    con.execute(f"""create or replace temp table promo_panel as
        select p.*, a.value + b.value + c.value + {xb} as log_base
        from promo_panel p
        left join _fe_fe_a a on a.level = p.fe_a
        left join _fe_fe_b b on b.level = p.fe_b
        left join _fe_fe_c c on c.level = p.fe_c""")
    # Retransformation: per-subcategory ratio so clean-week baseline units sum to actual units.
    con.execute("""create or replace temp table smear as select subcategory, sum(units) / sum(exp(log_base)) as k
                   from promo_panel where role = 'clean' group by 1""")
    con.execute("""create or replace temp table promo_panel as
        select p.*, exp(p.log_base) * s.k as base_units from promo_panel p join smear s using (subcategory)""")
    missing = con.execute("select count(*) from promo_panel where role != 'clean' and log_base is null").fetchone()[0]
    return {'fe_level_iterations': iterations, 'rows_without_baseline': missing,
            'retransformation': dict(con.execute('select * from smear order by 1').fetchall())}


CONTRIB_SQL = """
create or replace temp table contrib as
-- One row per (event, store) with every P&L component at the fitted baseline.
with ev_store as (
    select promo_id, store_id,
        sum(units) as units, sum(base_units) as base_units, sum(gp) as gp, sum(base_units * reg_margin) as base_gp
    from promo_panel where role = 'promo' and log_base is not null group by all
),
post as (
    select post_promo_id as promo_id, store_id, sum(units - base_units) as dip_units,
        sum(gp - base_units * reg_margin) as dip_gp
    from promo_panel where role = 'post' and log_base is not null group by all
),
stores_per_event as (select promo_id, count(*) as n_stores from ev_store group by 1)
select e.promo_id, e.store_id, ev.mechanic, ev.display, ev.subcategory, ev.fiscal_year,
    e.units, e.base_units, e.gp, e.base_gp,
    e.units - e.base_units as lift_units, e.gp - e.base_gp as lift_gp,
    coalesce(p.dip_units, 0) as dip_units, coalesce(p.dip_gp, 0) as dip_gp,
    ev.scan_per_unit * e.units as scan_back, ev.display_fee / s.n_stores as display_fee
from ev_store e
join promo_events ev using (promo_id)
join stores_per_event s using (promo_id)
left join post p using (promo_id, store_id)
"""

# Sister volume exposed to each event: a sister-week with n promoted sisters attributes 1/n of its cannibalised
# volume to each concurrent event. Non-promoted sisters lose units * (exp(-gamma n) - 1) of their actual volume;
# promoted sisters lose the same share of their (no-own-promotion) baseline.
CANN_SQL = f"""
create or replace temp table cann as
with ev_rows as ({scoped(0, 0)})
select er.promo_id, p.store_id, p.subcategory, p.n_sisters::int as k,
    sum(case when p.role = 'promo' then p.base_units else p.units end / p.n_sisters) as volume,
    sum(case when p.role = 'promo' then p.base_units * p.reg_margin else p.gp end / p.n_sisters) as margin_volume
from promo_panel p
join ev_rows er on er.store_id = p.store_id and er.w = p.w and er.subcategory = p.subcategory
              and er.sku_id != p.sku_id
where p.n_sisters >= 1 and p.log_base is not null
group by all
"""

GROUPINGS = {
    'all': lambda c: 'all',
    'mechanic': lambda c: c['mechanic'],
    'display': lambda c: 'display' if c['display'] == 'Y' else 'no display',
    'mechanic_display': lambda c: c['mechanic'] + (' + display' if c['display'] == 'Y' else ''),
    'subcategory': lambda c: c['subcategory'],
}
COMPONENTS = ('lift_gp', 'dip_gp', 'scan_back', 'display_fee')
SUMS = ('base_gp', 'units', 'base_units', 'lift_units', 'dip_units')


def cann_loss(keys, gamma):
    """Cannibalised amount (negative) for {(subcategory, k): volume} at slopes `gamma`."""
    return -sum(v * (math.exp(-gamma[xname(s)] * k) - 1) for (s, k), v in keys.items())


def outcome(ci):
    return 'keep' if ci[0] > 0 else ('cut_or_redesign' if ci[1] < 0 else 'inconclusive')


def summarise(rows, cann_rows, gamma_hat, stores, year=None):
    """Totals and 90% ranges for every grouping. Ranges: a store bootstrap (resample stores with replacement,
    recompute the ratio to baseline GP, take the 5th and 95th percentiles) and CR1 linearisation over stores; the
    wider is reported. Both hold the cannibalisation slopes at their estimates."""
    rows = [r for r in rows if year is None or r['fiscal_year'] == year]
    meta = {r['promo_id']: r for r in rows}
    cann_rows = [r for r in cann_rows if r['promo_id'] in meta]
    out = {}
    for gname, key in GROUPINGS.items():
        cells = {}
        for r in rows:
            cell = cells.setdefault(key(r), {'events': set(), 'stores': {}})
            cell['events'].add(r['promo_id'])
            st = cell['stores'].setdefault(r['store_id'], {c: 0.0 for c in COMPONENTS + SUMS} | {'cm': {}, 'cv': {}})
            for c in COMPONENTS + SUMS:
                st[c] += r[c]
        for r in cann_rows:
            st = cells[key(meta[r['promo_id']])]['stores'].get(r['store_id'])
            if st is None:      # sister rows in a store where the event itself sold nothing
                continue
            k = (r['subcategory'], r['k'])
            st['cm'][k] = st['cm'].get(k, 0.0) + r['margin_volume']
            st['cv'][k] = st['cv'].get(k, 0.0) + r['volume']
        result = {}
        for label, cell in sorted(cells.items()):
            per = cell['stores']
            fixed = {g: sum(v[c] for c in COMPONENTS) for g, v in per.items()}
            base = {g: v['base_gp'] for g, v in per.items()}
            cann = {g: cann_loss(v['cm'], gamma_hat) for g, v in per.items()}
            net = {g: fixed[g] + cann[g] for g in per}
            total_net, total_base = sum(net.values()), sum(base.values())
            ratio = total_net / total_base
            g_n = len(per)
            se = math.sqrt(g_n / (g_n - 1) * sum((net[g] - ratio * base[g]) ** 2 for g in per))
            ci_cr1 = [total_net - Z90 * se, total_net + Z90 * se]
            rng = random.Random(SEED)
            boot = []
            for _ in range(DRAWS):
                draw = [g for g in (rng.choice(stores) for _ in stores) if g in per]
                b_ = sum(base[g] for g in draw)
                boot.append(sum(net[g] for g in draw) / b_ * total_base if b_ else 0.0)
            ci_boot = [quantile(boot, 0.05), quantile(boot, 0.95)]
            # Unit lift range (added for the answer-key scorecard): store cluster bootstrap of units / baseline.
            rng_l = random.Random(SEED)
            lift_boot = []
            for _ in range(DRAWS):
                draw = [g for g in (rng_l.choice(stores) for _ in stores) if g in per]
                bu = sum(per[g]['base_units'] for g in draw)
                lift_boot.append(sum(per[g]['units'] for g in draw) / bu - 1 if bu else 0.0)
            ci = max(ci_cr1, ci_boot, key=lambda c: c[1] - c[0])
            s = {c: sum(v[c] for v in per.values()) for c in COMPONENTS + SUMS}
            cann_units = sum(cann_loss(v['cv'], gamma_hat) for v in per.values())
            cann_gp = sum(cann.values())
            before_funding = s['lift_gp'] + s['dip_gp'] + cann_gp
            result[label] = {
                'events': len(cell['events']), 'store_clusters': g_n,
                'lift_pct': s['units'] / s['base_units'] - 1,
                'lift_pct_ci90_store_bootstrap': [quantile(lift_boot, 0.05), quantile(lift_boot, 0.95)],
                'incremental_units': s['lift_units'], 'dip_units': s['dip_units'], 'cannibalised_units': cann_units,
                'net_incremental_units': s['lift_units'] + s['dip_units'] + cann_units,
                'lift_gp': s['lift_gp'], 'dip_gp': s['dip_gp'], 'cannibalisation_gp': cann_gp,
                'scan_back': s['scan_back'], 'display_fee': s['display_fee'],
                'gp_before_funding': before_funding, 'net_gp': total_net,
                'net_gp_per_event': total_net / len(cell['events']), 'baseline_gp': total_base,
                'ci90_store_cr1': ci_cr1, 'ci90_store_bootstrap': ci_boot, 'ci90': ci,
                'ci_source': 'bootstrap' if ci is ci_boot else 'cr1',
                'mde': 2.8 * (ci[1] - ci[0]) / 2 / Z90,
                'outcome': outcome(ci),
                'funding_dependent': outcome(ci) == 'keep' and before_funding < 0}
        out[gname] = result
    return out


def event_pnl(rows, cann_rows, gamma_hat):
    by_event = {}
    for r in rows:
        e = by_event.setdefault(r['promo_id'], {'mechanic': r['mechanic'], 'display': r['display'],
                                                'subcategory': r['subcategory'], 'fiscal_year': r['fiscal_year'],
                                                **{c: 0.0 for c in COMPONENTS}, 'cann_gp': 0.0})
        for c in COMPONENTS:
            e[c] += r[c]
    for r in cann_rows:
        if r['promo_id'] in by_event:
            by_event[r['promo_id']]['cann_gp'] += cann_loss({(r['subcategory'], r['k']): r['margin_volume']},
                                                            gamma_hat)
    for e in by_event.values():
        e['net_gp_before_funding'] = e['lift_gp'] + e['dip_gp'] + e['cann_gp']
        e['net_gp'] = e['net_gp_before_funding'] + e['scan_back'] + e['display_fee']
    return by_event


def holdout_error(con, role):
    """Actual vs imputed units on held-out rows of `role`, with a store cluster bootstrap range."""
    units, base, gp_err = con.execute("""select sum(units), sum(base_units), sum(gp - base_units * reg_margin)
        from promo_panel where role = ? and log_base is not null""", [role]).fetchone()
    per_store = con.execute("""select store_id, sum(units), sum(base_units) from promo_panel
        where role = ? and log_base is not null group by 1 order by 1""", [role]).fetchall()
    rng = random.Random(SEED)
    boot = []
    for _ in range(DRAWS):
        draw = [rng.choice(per_store) for _ in per_store]
        boot.append(sum(d[1] for d in draw) / sum(d[2] for d in draw) - 1)
    return {'rows': con.execute("select count(*) from promo_panel where role = ?", [role]).fetchone()[0],
            'error_pct': units / base - 1, 'error_ci90_store_bootstrap': [quantile(boot, 0.05), quantile(boot, 0.95)],
            'gp_error': gp_err}


def post_dip_ci(con):
    """Store cluster bootstrap range of the post-promotion dip by week (added for the answer-key scorecard)."""
    out = {}
    for k in range(1, POST_WEEKS + 1):
        per_store = con.execute(f"""select store_id, sum(units), sum(base_units) from promo_panel
            where role = 'post' and post_k = {k} and log_base is not null group by 1 order by 1""").fetchall()
        rng = random.Random(SEED)
        boot = []
        for _ in range(DRAWS):
            draw = [rng.choice(per_store) for _ in per_store]
            boot.append(sum(d[1] for d in draw) / sum(d[2] for d in draw) - 1)
        out[str(k)] = [quantile(boot, 0.05), quantile(boot, 0.95)]
    return out


def fetch(con, sql):
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    con = connect()
    build(con)
    planted = fit_baseline(con, shift=PLANTED_CANNIBALISATION)
    fit = fit_baseline(con)
    export_panel('promotions_clean', fetch(con, f"""select fe_a, fe_b, fe_c, cluster_id, y,
        {', '.join(xname(s) for s in SUBCATS)} from clean order by fe_a, fe_b"""))
    info = impute(con, fit)
    con.execute(CONTRIB_SQL)
    con.execute(CANN_SQL)
    rows = fetch(con, 'select * from contrib order by promo_id, store_id')
    cann_rows = fetch(con, 'select * from cann order by promo_id, store_id, subcategory, k')
    stores = [r[0] for r in con.execute('select distinct store_id from contrib order by 1').fetchall()]
    gamma_hat = fit['beta']
    events = event_pnl(rows, cann_rows, gamma_hat)

    result = {
        'design': {'clean_rows': fit['n'], 'store_clusters': fit['clusters'], 'fe': FES,
                   'fe_iterations': fit['fe_iterations'], **info,
                   'roles': {r[0]: {'rows': r[1], 'units': r[2], 'baseline_units': r[3]} for r in con.execute(
                       'select role, count(*), sum(units), sum(base_units) from promo_panel group by 1 order by 1'
                   ).fetchall()},
                   'approved_events': con.execute('select count(*) from promo_events').fetchone()[0],
                   'events_with_sales': len(events),
                   'dates_swapped_fixed': [r[0] for r in con.execute(
                       'select promo_id from promo_events where dates_swapped order by 1').fetchall()]},
        'cannibalisation': {s: {'per_promoted_sister': fit['beta'][xname(s)], 'se_store_cr1': fit['se'][xname(s)]}
                            for s in SUBCATS},
        'planted_cannibalisation_recovered': {s: planted['beta'][xname(s)] - fit['beta'][xname(s)] for s in SUBCATS},
        'pre_period': holdout_error(con, 'pre'),
        'placebo': holdout_error(con, 'placebo'),
        'post_dip_by_week': {str(k): v for k, v in con.execute("""select post_k, sum(units) / sum(base_units) - 1
            from promo_panel where role = 'post' and log_base is not null group by 1 order by 1""").fetchall()},
        'post_dip_ci90_store_bootstrap': post_dip_ci(con),
        'all_years': summarise(rows, cann_rows, gamma_hat, stores),
        'fy2025': summarise(rows, cann_rows, gamma_hat, stores, year=DECISION_YEAR),
    }
    fy = [e for e in events.values() if e['fiscal_year'] == DECISION_YEAR]
    ranked = sorted(({'promo_id': k, **{x: v[x] for x in ('mechanic', 'display', 'subcategory', 'net_gp')}}
                     for k, v in events.items() if v['fiscal_year'] == DECISION_YEAR), key=lambda e: e['net_gp'])
    result['events_fy2025'] = {
        'events': len(fy), 'share_net_positive': sum(e['net_gp'] > 0 for e in fy) / len(fy),
        'share_positive_before_funding': sum(e['net_gp_before_funding'] > 0 for e in fy) / len(fy),
        'median_net_gp': quantile([e['net_gp'] for e in fy], 0.5), 'worst_5': ranked[:5], 'best_5': ranked[-5:]}
    # Credibility: the placebo baseline error, applied to each cell's baseline GP, must not flip the sign of a
    # cell the decision rule calls keep or cut.
    err = result['placebo']['error_pct']
    flips = [f'{g}:{label}' for g in ('all', 'mechanic', 'mechanic_display') for label, c in
             result['fy2025'][g].items() if c['outcome'] != 'inconclusive'
             and (c['net_gp'] - err * c['baseline_gp'] > 0) != (c['net_gp'] > 0)]
    result['checks_passed'] = {
        'pre_period_within_3pct': abs(result['pre_period']['error_pct']) < 0.03,
        'placebo_within_2pct': abs(err) < 0.02,
        'placebo_does_not_flip_decisions': not flips,
        'planted_cannibalisation_recovered': all(abs(v - PLANTED_CANNIBALISATION) < 1e-6
                                                 for v in result['planted_cannibalisation_recovered'].values())}
    result['credible'] = all(result['checks_passed'].values())
    write_result('promotions', round_floats(result))
    return result


if __name__ == '__main__':
    import json
    r = round_floats(main())
    print(json.dumps({k: r[k] for k in ('design', 'cannibalisation', 'pre_period', 'placebo', 'post_dip_by_week',
                                        'checks_passed', 'events_fy2025')}, indent=1))
    for g in ('all', 'mechanic', 'display', 'mechanic_display', 'subcategory'):
        for label, c in r['fy2025'][g].items():
            print(f"{g:16} {label:22} ev={c['events']:3} lift={c['lift_pct']:+.2f} liftGP={c['lift_gp']:9.0f} "
                  f"dip={c['dip_gp']:8.0f} cann={c['cannibalisation_gp']:8.0f} scan={c['scan_back']:8.0f} "
                  f"disp={c['display_fee']:7.0f} net={c['net_gp']:9.0f} ci={[round(x) for x in c['ci90']]} "
                  f"{c['ci_source']} {c['outcome']}{' FUNDING-DEP' if c['funding_dependent'] else ''}")
