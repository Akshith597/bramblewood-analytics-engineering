"""Render docs/fy2026_plan.md and docs/scorecard.md from analysis/results/*.json (same rules as the memo:
named placeholders only, no hand-typed figures; CI regenerates both and fails on any difference)."""

from analysis.build_memo import load, money, num, pct, rng
from analysis.common import ROOT
from analysis.plan import CUT_CELLS, KEEP_CELLS

PLAN_TEMPLATE = ROOT / 'analysis/plan_template.md'
PLAN = ROOT / 'docs/fy2026_plan.md'
SCORE_TEMPLATE = ROOT / 'analysis/scorecard_template.md'
SCORECARD = ROOT / 'docs/scorecard.md'
PG_NAME = {'PG-SS-L-2024': 'L', 'PG-SS-M-2024': 'M', 'PG-SS-S-2024': 'S'}


def pos(v):
    return money(v).lstrip('+')


def cut_rows(a):
    by_sku = {}
    for c in a['ranked']:
        if c['cut']:
            s = by_sku.setdefault(c['sku_id'], {'item': c['description'], 'sub': c['subcategory'], 'pg': [],
                                                'facings': 0.0, 'gp': 0.0, 'gp_low': 0.0, 'gpf': []})
            s['pg'].append(PG_NAME[c['planogram']])
            s['facings'] += c['facings']
            s['gp'] += c['chain_gp_change']
            s['gp_low'] += c['chain_gp_change_tau_low']
            s['gpf'].append(c['gp_per_facing'])
    rows = sorted(by_sku.items(), key=lambda kv: min(kv[1]['gpf']))
    span = lambda v: pos(min(v)) if pos(min(v)) == pos(max(v)) else f'{pos(min(v))}–{pos(max(v))}'
    return '\n'.join(f"| {k} | {v['item']} | {v['sub']} | {', '.join(sorted(v['pg']))} | {v['facings']:.0f} | "
                     f"{span(v['gpf'])} | {money(v['gp'])} ({money(v['gp_low'])}) |" for k, v in rows)


def plan_figures(r):
    p, a, s, pr, ph = r['plan'], r['assortment'], r['inventory_sim'], r['promotions'], r['physical']
    lev = p['by_lever']
    cells = pr['fy2025']['mechanic_display']
    inp = p['inputs']['promo']
    drop_gpbf = sum(cells[c]['gp_before_funding'] for c in CUT_CELLS)
    changed = (f"the {pos(ph['restated']['memo_over_forecast_cost'])} over-forecast is restated to "
               f"{pos(ph['restated']['excess_store_stock_cost'])} of extra store stock (receipts follow sales); the "
               f"\"apply the bias correction now\" advice is withdrawn for store ordering (no saving at equal service: "
               f"{money(s['verdict']['policy_cost_saving_at_best_z'])}); the year-long delist test is not run; forecast bias on weeks without a stock-out is "
               f"{pct(ph['bias_refit']['in_stock_weeks']['bias'])}, not lower, because stock-outs are demand spikes.")
    return {
        'plan_gp': money(p['total']['base']), 'plan_ci': rng(*p['total']['range'], money),
        'plan_low_note': 'positive even in the low case' if p['total']['positive_in_low_case']
        else 'the low case is negative',
        'backbill': rng(p['one_off_backbill']['lower_scan_only'], p['one_off_backbill']['upper_scan_plus_planned_display'], pos),
        'drop_events': str(sum(cells[c]['events'] for c in CUT_CELLS)),
        'keep_events': str(sum(cells[c]['events'] for c in KEEP_CELLS)),
        'promo_gp': money(lev['promo_calendar']['base']), 'promo_ci': rng(*lev['promo_calendar']['range'], money),
        'drop_gpbf': money(drop_gpbf), 'promo_rho0': money(p['promo_funding_sensitivity']['rho_0']),
        'drop_funding': pos(sum(inp[c]['scan_back'] + inp[c]['display_fee'] for c in CUT_CELLS)),
        'vendor_gp': money(lev['vendor_terms']['base']), 'vendor_ci': rng(*lev['vendor_terms']['range'], money),
        'underbilled': pct(p['inputs']['vendor']['underbilled_share'], signed=False),
        'cut_n': str(a['chain']['distinct_skus_cut']), 'cut_gp': money(lev['assortment']['base']),
        'cut_ci': rng(*lev['assortment']['range'], money),
        'tau': pct(a['tau']['point'], 0, signed=False), 'tau_ci': rng(*a['tau']['ci90'], lambda x: pct(x, 0, signed=False)),
        'tortilla_action': {'hold': 'keep', 'roll_back': 'roll back'}[p['tortilla_action']],
        'price_gp': money(lev['prices']['base']), 'price_ci': rng(*lev['prices']['range'], money),
        'fc_gp': money(lev['forecast']['base']) if lev['forecast']['base'] else '$0', 'sim_saving': money(s['verdict']['policy_cost_saving_at_best_z']),
        'promo_share': pct(lev['promo_calendar']['share_of_range_width'], 0, signed=False),
        'display_breakeven': pct(p['display_events']['breakeven_rho_to_drop'], 0, signed=False),
        'alt_gp': money(p['if_display_also_dropped']['base']), 'alt_ci': rng(*p['if_display_also_dropped']['range'], money),
        'cut_rows': cut_rows(a), 'changed': changed,
        'u_vals': ', '.join(pct(v, 0, signed=False) for v in p['design']['inputs_low_base_high']['u'][:2])
        + ' or ' + pct(p['design']['inputs_low_base_high']['u'][2], 0, signed=False),
    }


def fmt_value(v, unit):
    if v is None:
        return '—'
    if unit in ('share over baseline', 'share vs baseline', 'share of actual', 'share of demand', 'share of GP',
                'log points'):
        return pct(v)
    if unit == 'ratio':
        return pct(v, 0, signed=False)
    return num(v)


def score_figures(r):
    sc = r['scorecard']
    rows = '\n'.join(
        f"| {x['parameter']}{'' if x['primary'] else ' *(secondary)*'} | {fmt_value(x['estimate'], x['unit'])} | "
        f"{rng(*x['ci90'], lambda v: fmt_value(v, x['unit'])) if x['ci90'] else '—'} | "
        f"{fmt_value(x['truth'], x['unit']) if x['truth'] is not None else 'pending'} | "
        f"{fmt_value(x['error'], x['unit']) if x['error'] is not None else '—'} | "
        f"{'—' if x['covered'] is None else ('yes' if x['covered'] else '**no**')} |" for x in sc['rows'])
    if sc['key_received']:
        status = f"key received; {sc['scored']} of {sc['parameters']} parameters scored."
        summary = (f"Coverage: **{sc['covered']} of {sc['scored']}** ({pct(sc['coverage'], 0, signed=False)}) inside "
                   'their 90% intervals. By family: ' + '; '.join(
                       f"{k} {v['covered']}/{v['scored']}" for k, v in sorted(sc['by_family'].items())) + '.')
        wrong = '\n'.join(f"- **{w['parameter']}**: estimate {w['estimate']}, truth {w['truth']}, interval "
                          f"{w['ci90']}. Affects: {w['claims_affected']}." for w in sc['proved_wrong']) or \
            'Nothing: every truth fell inside its frozen 90% interval.'
    else:
        status = f"no answer key is available — {sc['parameters']} parameters frozen, none scored."
        summary = ('The dataset was generated by AI ([provenance](../data/SOURCE_README.md)). The brief mentions a '
                   'generator and answer key, but neither is in this repository and no public copy could be found, so '
                   'it is unknown whether a key exists. If one is obtained, truth, error and coverage fill in '
                   'automatically when it is committed as `analysis/scorecard/answer_key.json`. Until then, the '
                   'estimates are checked only by the planted-effect, backtest and second-implementation checks in '
                   'the [decision memo](decision_memo.md#how-the-results-were-checked).')
        wrong = ('Nothing: no answer key is available, so no estimate has been tested against ground truth. '
                 'This section lists every parameter whose 90% interval misses the truth, with the claims it touches.')
    ph, s = r['physical'], r['inventory_sim']
    physical_wrong = '\n'.join([
        f"- **The {pos(ph['restated']['memo_over_forecast_cost'])} forecast figure** was planned units, not stock: "
        f"stores received {pct(ph['receipts_vs_forecast_fy2025']['receipts_over_actual'], signed=False)} more than "
        f"they sold, and comparable-store stock rose {pos(ph['restated']['excess_store_stock_cost'])} on average.",
        f"- **\"Apply the bias correction now\"**: on an inventory replay the correction finds no saving at each "
        f"forecast's best safety stock ({money(s['verdict']['policy_cost_saving_at_best_z'])}).",
        f"- **Bias on clean weeks would be lower**: it is higher ({pct(ph['bias_refit']['in_stock_weeks']['bias'])}), "
        'because stock-out weeks are the weeks the forecast under-calls.',
        '- **The README** still said promotions and out-of-stock cost were "not yet answered" after the memo had '
        'answered them; it is now rendered from results and checked in CI.'])
    return {'status': status, 'summary': summary, 'rows': rows, 'wrong': wrong, 'physical_wrong': physical_wrong}


def render_plan(results=None):
    results = results or load()
    return PLAN_TEMPLATE.read_text(encoding='utf-8').format(**plan_figures(results))


def render_scorecard(results=None):
    results = results or load()
    return SCORE_TEMPLATE.read_text(encoding='utf-8').format(**score_figures(results))


def main():
    PLAN.write_text(render_plan(), encoding='utf-8', newline='\n')
    SCORECARD.write_text(render_scorecard(), encoding='utf-8', newline='\n')
    print(f'Wrote {PLAN.relative_to(ROOT)} and {SCORECARD.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
