"""FY2026 plan — one gross-profit change with a low / base / high range.

Each uncertain input gets three values: a pessimistic one, a base one and an optimistic one (the ends of its 90%
interval for estimated inputs; stated assumptions for the negotiation inputs). The low case puts every input at its
bad end at once and the high case at its good end, so the range is deliberately wide: it is a planning envelope,
not a probability statement.

Levers (annual GP change for FY2026 against the FY2025 run-rate, gross profit after vendor funding):

1. Assortment: the cut list (analysis/assortment.py). Change = A + τ·B, τ at its estimate and at its 90% CI ends.
2. Prices: hold both spring 2025 increases. FY2025 carried Golden Ridge for only part of the year and FY2026 carries
   it all year, so the plan gains the uncovered weeks of each increase. Own-price elasticity at the pooled estimate
   and its 90% CI ends; GP change at elasticity ε is Q0 · [(1+x)^ε (p1 − c) − (p0 − c)], with Q0 backed out of the
   pricing result. Private-label tortilla, which sits near break-even, takes whichever action (hold or roll back)
   has the higher GP at the point estimate.
3. Promo calendar: drop the events without a display (TPR, BOGO, multi-buy alone). Vendor funding is treated as a
   negotiable budget, not as profit an event creates: dropping an event avoids its GP before funding (lift, dip,
   cannibalisation; analysis/promotions.py), and the vendor's scan-back for it is lost except for a share ρ that
   is renegotiated into allowances on the events kept. ρ is a negotiation outcome with no data behind it:
   low 0 (vendors move none of it), base 0.5, high 1 (all of it), and the plan is chosen so the lever is positive
   even at ρ = 0. Display events are kept: dropping them pays only if ρ exceeds a break-even share (reported), so
   that call waits for the vendor negotiation.
4. Vendor terms: bill scan-back on every kept event. FY2025 under-billed scan-back by a measured share of what was
   owed (analysis/funding.py); the plan recovers u of that share on the kept events' scan-back: low 50%, base
   75%, high 100%.
   The FY2025 back-bill is one-off cash, shown separately and not in the run-rate GP change.
5. Forecast: no store-replenishment change. The inventory simulation (analysis/inventory_sim.py) found the
   correction does not lower the cost of service once safety stock is re-tuned, and store receipts follow sales,
   not the forecast. Lever value 0; the corrected number is for planning and budgeting only.

Overlaps handled: promotions of cut SKUs are removed from the promo lever (their promoted weeks are already in the
SKUs' GP), scaled by the share of stores where the SKU is cut; a cut SKU that is also a priced SKU would be removed
from the price lever (checked, reported); the promo cells share one baseline model, so they move to their low or
high ends together.
"""
import itertools
import json

from analysis.common import RESULTS, connect, round_floats, write_result

CUT_CELLS = ('BOGO', 'Multi-buy', 'TPR')
KEEP_CELLS = ('BOGO + display', 'Multi-buy + display', 'TPR + display')
Z90 = 1.6448536


def res(name):
    return json.loads((RESULTS / f'{name}.json').read_text(encoding='utf-8'))


def sd_from_ci(ci):
    return (ci[1] - ci[0]) / (2 * Z90)


def price_lever(pricing, con):
    weeks_uncovered = {}
    fy_start = con.execute("select min(week_start) from stg_fiscal_calendar where fiscal_year = 2025").fetchone()[0]
    out = {}
    for key, date in (('golden_ridge_kettle', None), ('bramble_select_tortilla', None)):
        d = pricing['decisions'][key]
        event = pricing['preregistered'][key]['event_date']
        weeks = con.execute("select (?::date - ?::date) / 7", [event, fy_start]).fetchone()[0]
        weeks_uncovered[key] = weeks
        x, p0, p1, c = d['price_increase'], d['pre_price'], d['post_price'], d['unit_cost']
        eps = d['pooled_elasticity_used']
        q0 = d['conditional_annual_gp_change'] / ((1 + x) ** eps * (p1 - c) - (p0 - c))
        out[key] = {'x': x, 'p0': p0, 'p1': p1, 'c': c, 'q0': q0, 'eps': eps,
                    'eps_range': sorted(d['pooled_elasticity_range']), 'weeks_uncovered': weeks,
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
    rows = con.execute("""
        select p.sku_id, p.mechanic || case when p.display = 'Y' then ' + display' else '' end as cell, count(*)
        from stg_promotions p join stg_fiscal_calendar c on p.start_date between c.week_start and c.week_ending
        where p.status = 'Approved' and c.fiscal_year = 2025 and list_contains(?, p.sku_id) group by all""",
                       [list(weight)]).fetchall()
    by_cell = {}
    for sku, cell, n in rows:
        by_cell[cell] = by_cell.get(cell, 0.0) + n * weight[sku]
    return by_cell, weight


def tortilla_action(p):
    return 'hold' if gp_change(p, p['eps']) >= 0 else 'roll_back'


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
    priced = {'golden_ridge_kettle': (['Golden Ridge', 'Golden Rdge'], 'Kettle Chips'),
              'bramble_select_tortilla': (['Bramble Select'], 'Tortilla Chips')}
    price_overlap = {}
    for key, (brands, subcategory) in priced.items():
        skus = {r[0] for r in con.execute('select sku_id from stg_items where list_contains(?, brand) and subcategory = ?',
                                          [brands, subcategory]).fetchall()}
        price_overlap[key] = sorted(skus & set(weight))
    return {
        'assortment': {'a': a['chain']['a'], 'b': a['chain']['b'], 'tau': a['tau']['point'],
                       'tau_range': sorted(a['tau']['ci90']), 'skus_cut': a['chain']['distinct_skus_cut']},
        'price': price_lever(pricing, con), 'price_overlap_with_cuts': price_overlap,
        'promo': promo,
        'vendor': {'scan_owed': approved['scan_owed'], 'scan_billed': approved['scan_billed'],
                   'underbilled_share': (approved['scan_owed'] - approved['scan_billed']) / approved['scan_owed'],
                   'one_off_backbill': fund['approved_gap_range']},
        'tortilla_action': tortilla_action(price_lever(pricing, con)['bramble_select_tortilla']),
        'forecast': {'policy_cost_saving': sim['verdict']['policy_cost_saving_at_best_z'], 'adopted': sim['verdict']['adopt']},
    }


def input_values(inp):
    """(low end, base, high end) for every uncertain input. z_promo is the shared promo-cell error in SDs."""
    a = inp['assortment']
    vals = {'tau': (a['tau_range'][0], a['tau'], a['tau_range'][1]),
            'z_promo': (-Z90, 0.0, Z90), 'rho': (0.0, 0.5, 1.0), 'u': (0.5, 0.75, 1.0)}
    for k, p in inp['price'].items():
        vals[f'eps:{k}'] = (p['eps_range'][0], p['eps'], p['eps_range'][1])
    return vals


def as_draw(values):
    return {'tau': values['tau'], 'z_promo': values['z_promo'], 'rho': values['rho'], 'u': values['u'],
            'eps': {k.split(':', 1)[1]: v for k, v in values.items() if k.startswith('eps:')}}


def evaluate(inp, d, plan=None):
    """Lever values for one set of input values. `plan` overrides decisions (used for the display what-if)."""
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


def scenarios(inp, plan=None):
    """Base case, plus the lowest and highest value of each lever and of the total over every combination of
    input ends. Each input moves one lever only, so the low total is every lever at its low end at once."""
    vals = input_values(inp)
    names = list(vals)
    base = evaluate(inp, as_draw({k: v[1] for k, v in vals.items()}), plan)
    combos = [evaluate(inp, as_draw(dict(zip(names, ends))), plan)
              for ends in itertools.product(*[(v[0], v[2]) for v in vals.values()])]
    out = {k: {'base': base[k], 'range': [min(c[k] for c in combos), max(c[k] for c in combos)]} for k in base}
    totals = [sum(c.values()) for c in combos]
    out_total = {'base': sum(base.values()), 'range': [min(totals), max(totals)]}
    out_total['positive_in_low_case'] = out_total['range'][0] > 0
    return out_total, out


def main():
    con = connect()
    inp = build_inputs(con)
    total, by_lever = scenarios(inp)
    width = total['range'][1] - total['range'][0]
    for k, v in by_lever.items():
        v['share_of_range_width'] = (v['range'][1] - v['range'][0]) / width if width else 0.0
    # Robustness of the promo lever to the funding assumption.
    p = inp['promo']
    keep = {c: 1 - x['cut_sku_event_share'] for c, x in p.items()}
    promo_at = lambda rho: sum(keep[c] * (-p[c]['gp_before_funding'] - (1 - rho) * (p[c]['scan_back'] + p[c]['display_fee']))
                               for c in CUT_CELLS)
    disp_gpbf = sum(keep[c] * p[c]['gp_before_funding'] for c in KEEP_CELLS)
    disp_funding = sum(keep[c] * (p[c]['scan_back'] + p[c]['display_fee']) for c in KEEP_CELLS)
    result = {
        'design': {'method': 'low / base / high scenarios over the ends of each input range',
                   'drop_cells': CUT_CELLS, 'keep_cells': KEEP_CELLS,
                   'inputs_low_base_high': input_values(inp),
                   'rho_note': 'assumption: share of dropped-event vendor funding re-won in negotiation',
                   'billing_recovery_note': 'assumption: share of the under-billing recovered on kept events'},
        'inputs': inp,
        'total': total,
        'by_lever': by_lever,
        'promo_funding_sensitivity': {'rho_0': promo_at(0.0), 'rho_0.5': promo_at(0.5), 'rho_1': promo_at(1.0)},
        'display_events': {'gp_before_funding': disp_gpbf, 'funding': disp_funding,
                           'breakeven_rho_to_drop': 1 + disp_gpbf / disp_funding if disp_funding else None,
                           'note': 'Dropping display events pays only if vendors keep more than this share of '
                                   'their display funding in other forms.'},
        'one_off_backbill': inp['vendor']['one_off_backbill'],
        'tortilla_action': inp['tortilla_action'],
    }
    upside, _ = scenarios(inp, {'drop_cells': CUT_CELLS + KEEP_CELLS})
    result['if_display_also_dropped'] = {**upside, 'note': 'Not the plan: shown to size the negotiation. Positive only '
                                         'if vendors keep more than the break-even share of display funding.'}
    write_result('plan', round_floats(result))
    return result


if __name__ == '__main__':
    r = round_floats(main())
    print(json.dumps({k: r[k] for k in ('total', 'by_lever', 'promo_funding_sensitivity', 'display_events')}, indent=1))
    print(json.dumps(r['inputs']['price_overlap_with_cuts']), json.dumps({c: x['cut_sku_event_share'] for c, x in r['inputs']['promo'].items()}))
