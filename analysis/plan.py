"""FY2026 plan — one gross-profit change with a 90% range, from a Monte Carlo over every lever's uncertainty.

Levers (annual GP change for FY2026 against the FY2025 run-rate, gross profit after vendor funding):

1. Assortment: the cut list (analysis/assortment.py). Change = A + τ·B, τ ~ Normal(test estimate, its SE).
2. Prices: hold both spring 2025 increases. FY2025 carried Golden Ridge for only part of the year and FY2026 carries
   it all year, so the plan gains the uncovered weeks of each increase. Own-price elasticity ~ Normal(pooled
   estimate, its SE); GP change at elasticity ε is Q0 · [(1+x)^ε (p1 − c) − (p0 − c)], with Q0 backed out of the
   pricing result. Private-label tortilla, which sits near break-even, takes whichever action (hold or roll back)
   has the higher expected GP under the elasticity prior; analysis/evoi.py prices the test that would settle it.
3. Promo calendar: drop the events without a display (TPR, BOGO, multi-buy alone). Vendor funding is treated as a
   negotiable budget, not as profit an event creates: dropping an event avoids its GP before funding (lift, dip,
   cannibalisation; analysis/promotions.py), and the vendor's scan-back for it is lost except for a share ρ that
   is renegotiated into allowances on the events kept. ρ is a negotiation outcome with no data behind it:
   ρ ~ Beta(2, 2) (mean 0.5), and the plan is chosen so the lever is positive even at ρ = 0. Display events are
   kept: dropping them pays only if ρ exceeds a break-even share (reported), so that call waits for the vendor
   negotiation and the holdout test.
4. Vendor terms: bill scan-back on every kept event. FY2025 under-billed scan-back by a measured share of what was
   owed (analysis/funding.py); the plan recovers u ~ Uniform(0.5, 1) of that share on the kept events' scan-back.
   The FY2025 back-bill is one-off cash, shown separately and not in the run-rate GP change.
5. Forecast: no store-replenishment change. The inventory simulation (analysis/inventory_sim.py) found the
   correction does not lower the cost of service once safety stock is re-tuned, and store receipts follow sales,
   not the forecast. Lever value 0; the corrected number is for planning and budgeting only.

Interactions carried in the draw: promotions of cut SKUs are removed from the promo lever (their promoted weeks
are already in the SKUs' GP), scaled by the share of stores where the SKU is cut; a cut SKU that is also a priced
SKU would be removed from the price lever (checked, reported); the promo lever's cells share one baseline model, so
their errors are drawn perfectly correlated (wider, not narrower). Everything else is drawn independently.
"""
import json
import math
import random

from analysis.common import RESULTS, connect, round_floats, write_result

SEED = 20261015
DRAWS = 20000
CUT_CELLS = ('BOGO', 'Multi-buy', 'TPR')
KEEP_CELLS = ('BOGO + display', 'Multi-buy + display', 'TPR + display')
Z90 = 1.6448536


def res(name):
    return json.loads((RESULTS / f'{name}.json').read_text(encoding='utf-8'))


def sd_from_ci(ci):
    return (ci[1] - ci[0]) / (2 * Z90)


def quant(xs, q):
    xs = sorted(xs)
    i = q * (len(xs) - 1)
    lo = math.floor(i)
    return xs[lo] + (xs[min(lo + 1, len(xs) - 1)] - xs[lo]) * (i - lo)


def price_lever(pricing, con):
    weeks_uncovered = {}
    fy_start = con.execute("select min(week_start) from stg_fiscal_calendar where fiscal_year = 2025").fetchone()[0]
    out = {}
    for key, date in (('golden_ridge_kettle', None), ('bramble_select_tortilla', None)):
        d = pricing['decisions'][key]
        event = pricing['preregistered'][key]['event_date']
        weeks = con.execute(f"select ('{event}'::date - '{fy_start}'::date) / 7").fetchone()[0]
        weeks_uncovered[key] = weeks
        x, p0, p1, c = d['price_increase'], d['pre_price'], d['post_price'], d['unit_cost']
        eps = d['pooled_elasticity_used']
        q0 = d['conditional_annual_gp_change'] / ((1 + x) ** eps * (p1 - c) - (p0 - c))
        out[key] = {'x': x, 'p0': p0, 'p1': p1, 'c': c, 'q0': q0, 'eps': eps,
                    'eps_sd': sd_from_ci(d['pooled_elasticity_range']), 'weeks_uncovered': weeks,
                    'annual_gp_change_at_eps': d['conditional_annual_gp_change'],
                    'breakeven_elasticity': d['breakeven_elasticity']}
    return out


def gp_change(p, eps):
    return p['q0'] * ((1 + p['x']) ** eps * (p['p1'] - p['c']) - (p['p0'] - p['c']))


def cut_sku_promos(con, assortment):
    """FY2025 approved events of cut SKUs by cell, weighted by the share of FY2026 stores where the SKU is cut."""
    stores = assortment['rules']['stores_fy2026']
    total = sum(stores.values())
    weight = {}
    for pg, s in assortment['by_planogram'].items():
        for sku in s['cut_skus']:
            weight[sku] = weight.get(sku, 0.0) + stores[pg.split('-')[2]] / total
    if not weight:
        return {}, weight
    skus = ', '.join(f"'{k}'" for k in weight)
    rows = con.execute(f"""
        select p.sku_id, p.mechanic || case when p.display = 'Y' then ' + display' else '' end as cell, count(*)
        from stg_promotions p join stg_fiscal_calendar c on p.start_date between c.week_start and c.week_ending
        where p.status = 'Approved' and c.fiscal_year = 2025 and p.sku_id in ({skus}) group by all""").fetchall()
    by_cell = {}
    for sku, cell, n in rows:
        by_cell[cell] = by_cell.get(cell, 0.0) + n * weight[sku]
    return by_cell, weight


def tortilla_action(p, draws=DRAWS):
    rng = random.Random(SEED)
    mean_gain = sum(gp_change(p, rng.gauss(p['eps'], p['eps_sd'])) for _ in range(draws)) / draws
    return 'hold' if mean_gain >= 0 else 'roll_back'


def build_inputs(con):
    a, pr, pricing, fund, sim = res('assortment'), res('promotions'), res('pricing'), res('funding'), res('inventory_sim')
    cells = pr['fy2025']['mechanic_display']
    cut_events, weight = cut_sku_promos(con, a)
    promo = {}
    for c in CUT_CELLS + KEEP_CELLS:
        x = cells[c]
        overlap = min(cut_events.get(c, 0.0) / x['events'], 1.0)
        promo[c] = {'events': x['events'], 'cut_sku_event_share': overlap,
                    'gp_before_funding': x['gp_before_funding'], 'sd': sd_from_ci(x['ci90']),
                    'scan_back': x['scan_back'], 'display_fee': x['display_fee']}
    approved = fund['by_status']['Approved']
    priced = {'golden_ridge_kettle': "brand in ('Golden Ridge', 'Golden Rdge') and subcategory = 'Kettle Chips'",
              'bramble_select_tortilla': "brand = 'Bramble Select' and subcategory = 'Tortilla Chips'"}
    price_overlap = {}
    for key, cond in priced.items():
        skus = {r[0] for r in con.execute(f'select sku_id from stg_items where {cond}').fetchall()}
        price_overlap[key] = sorted(skus & set(weight))
    return {
        'assortment': {'a': a['chain']['a'], 'b': a['chain']['b'], 'tau': a['tau']['point'],
                       'tau_sd': sd_from_ci(a['tau']['ci90']), 'skus_cut': a['chain']['distinct_skus_cut']},
        'price': price_lever(pricing, con), 'price_overlap_with_cuts': price_overlap,
        'promo': promo,
        'vendor': {'scan_owed': approved['scan_owed'], 'scan_billed': approved['scan_billed'],
                   'underbilled_share': (approved['scan_owed'] - approved['scan_billed']) / approved['scan_owed'],
                   'one_off_backbill': fund['approved_gap_range']},
        'tortilla_action': tortilla_action(price_lever(pricing, con)['bramble_select_tortilla']),
        'forecast': {'policy_cost_saving': sim['verdict']['policy_cost_saving_at_best_z'], 'adopted': sim['verdict']['adopt']},
    }


def draw_levers(inp, rng):
    """One draw of every uncertain input; returns lever values and the drawn parameters."""
    tau = rng.gauss(inp['assortment']['tau'], inp['assortment']['tau_sd'])
    z_promo = rng.gauss(0, 1)                     # one shared baseline-model error across promo cells
    rho = rng.betavariate(2, 2)
    u = rng.uniform(0.5, 1.0)
    eps = {k: rng.gauss(p['eps'], p['eps_sd']) for k, p in inp['price'].items()}
    return {'tau': tau, 'z_promo': z_promo, 'rho': rho, 'u': u, 'eps': eps}


def evaluate(inp, d, plan=None):
    """Lever values for one draw. `plan` overrides decisions (used by analysis/evoi.py)."""
    plan = {'cut_assortment': True, 'drop_cells': CUT_CELLS, 'tortilla': inp['tortilla_action'], **(plan or {})}
    a = inp['assortment']
    assortment = (a['a'] + d['tau'] * a['b']) if plan['cut_assortment'] else 0.0
    promo = 0.0
    kept_scan = 0.0
    for c, x in inp['promo'].items():
        keep_share = 1 - (x['cut_sku_event_share'] if plan['cut_assortment'] else 0.0)
        if c in plan['drop_cells']:
            gpbf = x['gp_before_funding'] + d['z_promo'] * x['sd']
            funding = x['scan_back'] + x['display_fee']
            promo += keep_share * (-gpbf - (1 - d['rho']) * funding)
        else:
            kept_scan += keep_share * x['scan_back']
    vendor = d['u'] * inp['vendor']['underbilled_share'] * kept_scan
    price = 0.0
    for key, p in inp['price'].items():
        if plan['cut_assortment'] and inp['price_overlap_with_cuts'][key]:
            continue
        carry = gp_change(p, d['eps'][key]) * p['weeks_uncovered'] / 52
        if key == 'bramble_select_tortilla' and plan['tortilla'] == 'roll_back':
            carry = -gp_change(p, d['eps'][key]) * (52 - p['weeks_uncovered']) / 52
        price += carry
    return {'assortment': assortment, 'prices': price, 'promo_calendar': promo, 'vendor_terms': vendor,
            'forecast': 0.0}


def summarise(xs):
    n = len(xs)
    mean = sum(xs) / n
    return {'mean': mean, 'median': quant(xs, 0.5), 'ci90': [quant(xs, 0.05), quant(xs, 0.95)],
            'p_positive': sum(x > 0 for x in xs) / n,
            'sd': math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))}


def simulate(inp, plan=None, draws=DRAWS, seed=SEED):
    rng = random.Random(seed)
    rows = []
    for _ in range(draws):
        d = draw_levers(inp, rng)
        rows.append((d, evaluate(inp, d, plan)))
    return rows


def main():
    con = connect()
    inp = build_inputs(con)
    rows = simulate(inp)
    levers = list(rows[0][1])
    totals = [sum(v.values()) for _, v in rows]
    by_lever = {k: summarise([v[k] for _, v in rows]) for k in levers}
    var_total = summarise(totals)['sd'] ** 2
    # Contribution to variance: share of the total variance removed when a lever is held at its mean.
    for k in levers:
        others = [t - v[k] + by_lever[k]['mean'] for t, (_, v) in zip(totals, rows)]
        sd = summarise(others)['sd']
        by_lever[k]['variance_share_removed_if_known'] = 1 - sd ** 2 / var_total if var_total else 0.0
    # Robustness of the promo lever to the funding assumption.
    p = inp['promo']
    keep = {c: 1 - x['cut_sku_event_share'] for c, x in p.items()}
    promo_at = lambda rho: sum(keep[c] * (-p[c]['gp_before_funding'] - (1 - rho) * (p[c]['scan_back'] + p[c]['display_fee']))
                               for c in CUT_CELLS)
    disp_gpbf = sum(keep[c] * p[c]['gp_before_funding'] for c in KEEP_CELLS)
    disp_funding = sum(keep[c] * (p[c]['scan_back'] + p[c]['display_fee']) for c in KEEP_CELLS)
    result = {
        'design': {'draws': DRAWS, 'seed': SEED, 'drop_cells': CUT_CELLS, 'keep_cells': KEEP_CELLS,
                   'rho_prior': 'Beta(2,2) — assumption, negotiation outcome', 'billing_recovery_prior': 'Uniform(0.5,1)'},
        'inputs': inp,
        'total': summarise(totals),
        'by_lever': by_lever,
        'promo_funding_sensitivity': {'rho_0': promo_at(0.0), 'rho_0.5': promo_at(0.5), 'rho_1': promo_at(1.0)},
        'display_events': {'gp_before_funding': disp_gpbf, 'funding': disp_funding,
                           'breakeven_rho_to_drop': 1 + disp_gpbf / disp_funding if disp_funding else None,
                           'note': 'Dropping display events pays only if vendors keep more than this share of '
                                   'their display funding in other forms.'},
        'one_off_backbill': inp['vendor']['one_off_backbill'],
        'tortilla_action': inp['tortilla_action'],
    }
    upside = summarise([sum(evaluate(inp, d, {'drop_cells': CUT_CELLS + KEEP_CELLS}).values()) for d, _ in rows])
    result['if_display_also_dropped'] = {**upside, 'note': 'Not the plan: shown to size the negotiation. Positive only '
                                         'if vendors keep more than the break-even share of display funding.'}
    write_result('plan', round_floats(result))
    return result


if __name__ == '__main__':
    r = round_floats(main())
    print(json.dumps({k: r[k] for k in ('total', 'by_lever', 'promo_funding_sensitivity', 'display_events')}, indent=1))
    print(json.dumps(r['inputs']['price_overlap_with_cuts']), json.dumps({c: x['cut_sku_event_share'] for c, x in r['inputs']['promo'].items()}))
