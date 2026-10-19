"""Q1, second half — which SKUs to cut: a ranked list on GP per facing and demand transfer, within planogram space.

For each planogram (L, M, S) as set at the end of FY2025:

- GP per facing = FY2025 gross profit per store-year of the SKU in stores on that planogram ÷ its facings.
- Demand transfer: when a SKU is cut and its facings go to retained SKUs, the delist test measured that retained
  SKUs gained τ dollars of sales per dollar the delisted SKUs lost (analysis/results/delist.json; τ = 1.24, 90%
  0.81 to 1.66). That rate already includes the reallocation of the freed facings, which is what a cut does.
  Cutting SKU i changes annual GP per store by  −GP_i + τ · sales_i · m_rest,  where m_rest is the gross margin
  rate of the retained SKUs in the same subcategory and planogram.
- Space limits: total facings per planogram are fixed (as in the test); freed facings go one at a time to the
  retained same-subcategory SKU selling the most units per facing, capped at the largest facing count any SKU has
  in that planogram today, and within shelf capacity scaling (capacity per facing held constant).
- Scope limits, so the test's τ is not extrapolated beyond what it measured: candidates are SKUs selling no more
  per store-year than the largest SKU the test cut (τ was measured on slow sellers; a best-seller's shoppers are
  not known to switch at that rate); at most as many cuts per planogram as the test made (20 in the large
  planogram, pro rata by SKU count elsewhere); at least 60% of each subcategory's SKUs retained; no SKU launched
  during FY2025 (less than a year of sales) or already discontinued.
- Ranking: GP per facing, lowest first, among candidates. Decision rule: cut only if the GP change is positive
  even at the lower end of τ's 90% range ("safe at τ low").

Check on τ (added with this module, after the delist results were known): the GP estimate failed its fake-date
check because large stores have their own second-half seasonality, so τ gets the same checks — the retained-sales
DiD at the fake date FY2024 W27 and FY2025 W1 (should be ~0), and a same-season version (FY2025 W27–52 vs
FY2024 W27–52) that cancels the seasonality.

The result carries the A + τ·B decomposition of the chain GP change so the FY2026 plan model can draw τ.
"""
from analysis.common import RESULTS, connect, round_floats, write_result
import json

FY_END = "date '2026-01-31'"
MIN_RETAIN_SHARE = 0.6
STORES_FY2026 = {'L': 8, 'M': 10, 'S': 6}

CURRENT_SQL = f"""
select planogram_id, sku_id, facings::double as facings, shelf_capacity_units::double as capacity
from stg_planograms
where planogram_id in ('PG-SS-L-2024', 'PG-SS-M-2024', 'PG-SS-S-2024')
  and effective_start <= {FY_END} and (effective_end is null or effective_end >= {FY_END})
"""

# FY2025 sales of each SKU in the stores and weeks it was on that store's planogram (base planograms only, so
# the four test stores contribute only their pre-test weeks).
SALES_SQL = """
with c as (select week_key, week_start, week_ending, fiscal_year from stg_fiscal_calendar where fiscal_year = 2025),
sp as (select sp.store_id, sp.planogram_id, c.week_key from stg_store_planogram sp join c
       on c.week_start >= sp.effective_start and (sp.effective_end is null or c.week_ending <= sp.effective_end)
       where sp.planogram_id in ('PG-SS-L-2024', 'PG-SS-M-2024', 'PG-SS-S-2024')),
pg as (select p.planogram_id, p.sku_id, c.week_key from stg_planograms p join c
       on c.week_start >= p.effective_start and (p.effective_end is null or c.week_ending <= p.effective_end)),
carried as (select sp.store_id, sp.planogram_id, pg.sku_id, sp.week_key from sp join pg using (planogram_id, week_key)),
s as (select store_id, sku_id, week_key, sum(units)::double as units, sum(net_sales)::double as sales,
             sum(gross_profit_before_funding)::double as gp from int_sales_enriched group by all)
select k.planogram_id, k.sku_id, count(*) as store_weeks, sum(coalesce(s.units, 0)) as units,
    sum(coalesce(s.sales, 0)) as sales, sum(coalesce(s.gp, 0)) as gp
from carried k left join s using (store_id, sku_id, week_key)
group by all
"""

ITEMS_SQL = """select sku_id, description, brand, brand_type, subcategory, status, launch_date from stg_items"""

TEST_DELISTED_SQL = """
select sku_id from stg_planograms where planogram_id = 'PG-SS-L-2024' and effective_end is null
except select sku_id from stg_planograms where planogram_id = 'PG-SS-L-TEST25' and effective_end is null
"""


def evaluate(pg, rows, items, tau, tau_low, support):
    fmt = pg.split('-')[2]
    subs = {}
    for r in rows:
        subs.setdefault(items[r['sku_id']]['subcategory'], []).append(r)
    out = []
    for r in rows:
        it = items[r['sku_id']]
        rest = [x for x in subs[it['subcategory']] if x['sku_id'] != r['sku_id']]
        rest_sales = sum(x['sales_py'] for x in rest)
        m_rest = sum(x['gp_py'] for x in rest) / rest_sales if rest_sales else 0.0
        a, b = -r['gp_py'], r['sales_py'] * m_rest           # per store-year: change = a + tau * b
        eligible = (it['status'] == 'Active' and (it['launch_date'] is None or str(it['launch_date']) < '2025-02-02')
                    and len(rest) > 0 and r['sales_py'] <= support)
        out.append({'planogram': pg, 'format': fmt, 'sku_id': r['sku_id'], 'description': it['description'],
                    'brand': it['brand'], 'brand_type': it['brand_type'], 'subcategory': it['subcategory'],
                    'facings': r['facings'], 'units_py': r['units_py'], 'sales_py': r['sales_py'],
                    'gp_py': r['gp_py'], 'gp_per_facing': r['gp_py'] / r['facings'], 'margin_rest': m_rest,
                    'a_per_store': a, 'b_per_store': b, 'gp_change_per_store': a + tau * b,
                    'gp_change_per_store_tau_low': a + tau_low * b,
                    'chain_gp_change': (a + tau * b) * STORES_FY2026[fmt],
                    'chain_gp_change_tau_low': (a + tau_low * b) * STORES_FY2026[fmt],
                    'eligible': eligible})
    return out


def select_cuts(cands, max_cuts, sku_count_by_sub):
    chosen, cut_by_sub = [], {}
    for c in sorted(cands, key=lambda c: (c['gp_per_facing'], c['sku_id'])):
        if len(chosen) >= max_cuts or not c['eligible'] or c['gp_change_per_store_tau_low'] <= 0:
            continue
        n = sku_count_by_sub[c['subcategory']]
        if (n - cut_by_sub.get(c['subcategory'], 0) - 1) < MIN_RETAIN_SHARE * n:
            continue
        cut_by_sub[c['subcategory']] = cut_by_sub.get(c['subcategory'], 0) + 1
        chosen.append(c)
    return chosen


def reallocate(cuts, rows, items):
    """Freed facings to the best-selling-per-facing retained SKU in the same subcategory, within the planogram's
    current maximum facings per SKU. Total facings unchanged."""
    cut_ids = {c['sku_id'] for c in cuts}
    cap = max(r['facings'] for r in rows)
    facings = {r['sku_id']: r['facings'] for r in rows if r['sku_id'] not in cut_ids}
    upf = {r['sku_id']: r['units_py'] for r in rows}
    moves = {}
    for c in cuts:
        for _ in range(int(c['facings'])):
            pool = [s for s in facings if items[s]['subcategory'] == c['subcategory'] and facings[s] < cap]
            if not pool:
                pool = [s for s in facings if facings[s] < cap]
            best = max(pool, key=lambda s: (upf[s] / facings[s], s))
            facings[best] += 1
            moves[best] = moves.get(best, 0) + 1
    return {'facings_freed': sum(c['facings'] for c in cuts), 'facings_added': moves,
            'total_facings_before': sum(r['facings'] for r in rows), 'total_facings_after': sum(facings.values()),
            'max_facings_per_sku': cap}


def tau_checks(con):
    from analysis.delist import Did, TREATED, load, series
    panel, switch, _ = load(con)
    donors = tuple(s for s in sorted(panel) if s not in TREATED)
    weeks = list(range(104))
    level = {m: series(panel, m, transform=float) for m in ('delisted_sales', 'retained_sales')}
    lost = -Did(level['delisted_sales'], TREATED, donors, weeks[:switch - 1], weeks[switch - 1:]).fit()[0]
    out = {}
    for label, pre, post in (('fake_FY2024-W27', weeks[:26], weeks[26:52]), ('fake_FY2025-W01', weeks[:52], weeks[52:78]),
                             ('same_season_yoy', weeks[26:52], weeks[78:104])):
        fit = Did(level['retained_sales'], TREATED, donors, pre, post).infer()
        out[label] = {'retained_change_per_store_week': fit['beta'], 'ci90': fit['ci90'],
                      'implied_tau': fit['beta'] / lost, 'implied_tau_ci90': [v / lost for v in fit['ci90']]}
    out['passed'] = all(v['ci90'][0] < 0 < v['ci90'][1] for k, v in out.items() if k.startswith('fake'))
    return out


def main():
    con = connect()
    delist = json.loads((RESULTS / 'delist.json').read_text(encoding='utf-8'))
    tau = delist['transfer']['transfer_rate']
    tau_low, tau_high = delist['transfer']['transfer_rate_ci90']
    test_cut = delist_test = {r[0] for r in con.execute(TEST_DELISTED_SQL).fetchall()}
    cols = ['sku_id', 'description', 'brand', 'brand_type', 'subcategory', 'status', 'launch_date']
    items = {r[0]: dict(zip(cols, r)) for r in con.execute(ITEMS_SQL).fetchall()}
    current = {}
    for pg, sku, f, cap in con.execute(CURRENT_SQL).fetchall():
        current.setdefault(pg, {})[sku] = {'facings': f, 'capacity': cap}
    sales = {(pg, sku): (sw, u, s, g) for pg, sku, sw, u, s, g in con.execute(SALES_SQL).fetchall()}
    max_cuts_l = len(delist_test)
    n_l = len(current['PG-SS-L-2024'])

    # Support of tau: the largest per-store-year sales among the SKUs the test cut (large planogram, pre-test).
    l_sales = {}
    for (pg, sku), (sw, u, s_, g) in sales.items():
        if pg == 'PG-SS-L-2024' and sku in delist_test and sw:
            l_sales[sku] = s_ * 52.0 / sw
    support = max(l_sales.values())
    by_pg, all_cands, summary = {}, [], {}
    for pg, skus in sorted(current.items()):
        rows = []
        for sku, v in skus.items():
            sw, u, s, g = sales.get((pg, sku), (0, 0.0, 0.0, 0.0))
            per = 52.0 / sw if sw else 0.0   # store-weeks → per store-year
            rows.append({'sku_id': sku, 'facings': v['facings'], 'units_py': u * per, 'sales_py': s * per,
                         'gp_py': g * per, 'store_weeks': sw})
        cands = evaluate(pg, rows, items, tau, tau_low, support)
        sku_count_by_sub = {}
        for c in cands:
            sku_count_by_sub[c['subcategory']] = sku_count_by_sub.get(c['subcategory'], 0) + 1
        max_cuts = round(max_cuts_l * len(rows) / n_l)
        cuts = select_cuts(cands, max_cuts, sku_count_by_sub)
        cut_ids = {c['sku_id'] for c in cuts}
        ranked = sorted(cands, key=lambda c: (not c['eligible'], c['gp_per_facing'], c['sku_id']))
        for i, c in enumerate(ranked, 1):
            c['rank'] = i
            c['cut'] = c['sku_id'] in cut_ids
        fmt = pg.split('-')[2]
        a = sum(c['a_per_store'] for c in cuts) * STORES_FY2026[fmt]
        b = sum(c['b_per_store'] for c in cuts) * STORES_FY2026[fmt]
        summary[pg] = {'skus': len(rows), 'max_cuts': max_cuts, 'cuts': len(cuts), 'stores_fy2026': STORES_FY2026[fmt],
                       'chain_a': a, 'chain_b': b, 'chain_gp_change': a + tau * b,
                       'chain_gp_change_tau_range': [a + tau_low * b, a + tau_high * b],
                       'space': reallocate(cuts, rows, items),
                       'cut_skus': [c['sku_id'] for c in sorted(cuts, key=lambda c: c['rank'])]}
        by_pg[pg] = ranked
        all_cands += ranked

    a = sum(s['chain_a'] for s in summary.values())
    b = sum(s['chain_b'] for s in summary.values())
    l_ranked = by_pg['PG-SS-L-2024']
    top20 = {c['sku_id'] for c in l_ranked[:max_cuts_l]}
    cut_l = {c['sku_id'] for c in l_ranked if c['cut']}
    # Consistency with the test: the transfer model's prediction for the 20 SKUs the test actually cut.
    test_rows = [c for c in l_ranked if c['sku_id'] in delist_test]
    result = {
        'tau': {'point': tau, 'ci90': [tau_low, tau_high], 'source': 'delist test, retained sales gained / delisted '
                'sales lost, with facings reallocated'},
        'tau_checks': tau_checks(con),
        'rules': {'support_max_sales_per_store_year': support, 'max_cuts_large': max_cuts_l, 'min_retain_share_per_subcategory': MIN_RETAIN_SHARE,
                  'decision': 'cut if GP change > 0 at the lower end of the 90% range of tau',
                  'stores_fy2026': STORES_FY2026},
        'by_planogram': summary,
        'chain': {'a': a, 'b': b, 'gp_change': a + tau * b, 'gp_change_tau_range': [a + tau_low * b, a + tau_high * b],
                  'distinct_skus_cut': len({c['sku_id'] for c in all_cands if c['cut']})},
        'test_overlap': {'test_delisted': len(delist_test),
                         'in_model_top_n_large': len(top20 & delist_test),
                         'in_model_cut_list_large': len(cut_l & delist_test),
                         'test_skus_model_gp_change_per_store': sum(c['gp_change_per_store'] for c in test_rows),
                         'test_skus_model_gp_change_per_store_tau_low': sum(c['gp_change_per_store_tau_low'] for c in test_rows),
                         'test_skus_gp_per_store': sum(c['gp_py'] for c in test_rows)},
        'ranked': [{k: c[k] for k in ('planogram', 'rank', 'sku_id', 'description', 'brand', 'brand_type',
                                      'subcategory', 'facings', 'units_py', 'sales_py', 'gp_py', 'gp_per_facing',
                                      'margin_rest', 'gp_change_per_store', 'gp_change_per_store_tau_low',
                                      'chain_gp_change', 'chain_gp_change_tau_low', 'eligible', 'cut')}
                   for c in all_cands],
    }
    write_result('assortment', round_floats(result))
    return result


if __name__ == '__main__':
    r = round_floats(main())
    print(json.dumps({k: r[k] for k in ('tau', 'tau_checks', 'chain', 'test_overlap')}, indent=1))
    for pg, s in r['by_planogram'].items():
        print(pg, {k: s[k] for k in ('skus', 'max_cuts', 'cuts', 'chain_gp_change', 'chain_gp_change_tau_range')},
              s['space']['facings_freed'], s['space']['total_facings_before'], s['space']['total_facings_after'])
    for c in [c for c in r['ranked'] if c['planogram'] == 'PG-SS-L-2024'][:25]:
        print(c['rank'], c['sku_id'], c['subcategory'][:8], c['brand'][:12], c['facings'], round(c['gp_py']),
              round(c['gp_per_facing']), round(c['gp_change_per_store']), round(c['gp_change_per_store_tau_low']),
              c['eligible'], c['cut'])
