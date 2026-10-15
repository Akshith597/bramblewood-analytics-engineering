"""Render docs/fy2026_plan.md and docs/scorecard.md from analysis/results/*.json (same rules as the memo:
named placeholders only, no hand-typed figures; CI regenerates both and fails on any difference)."""
import json

from analysis.build_memo import load, money, num, pct, rng
from analysis.common import ROOT
from analysis.plan import CUT_CELLS, KEEP_CELLS
from analysis.scorecard import FROZEN

PLAN_TEMPLATE = ROOT / 'analysis/plan_template.md'
PLAN = ROOT / 'docs/fy2026_plan.md'
SCORE_TEMPLATE = ROOT / 'analysis/scorecard_template.md'
SCORECARD = ROOT / 'docs/scorecard.md'
PG_NAME = {'PG-SS-L-2024': 'L', 'PG-SS-M-2024': 'M', 'PG-SS-S-2024': 'S'}
TEST_NAME = {'tortilla_price': ('Tortilla price, random half of stores, 13 weeks', 'Keep or roll back the private-label price'),
             'assortment_cut': ('Cut list in random large-store pairs, full year', 'Cut the list chain-wide or not'),
             'display_holdout': ('Display events withheld in a random quarter of stores, half a year',
                                 'Keep or drop display events')}


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
    p, a, e, s, pr, ph = r['plan'], r['assortment'], r['evoi'], r['inventory_sim'], r['promotions'], r['physical']
    lev = p['by_lever']
    cells = pr['fy2025']['mechanic_display']
    inp = p['inputs']['promo']
    drop_gpbf = sum(cells[c]['gp_before_funding'] for c in CUT_CELLS)
    tests = '\n'.join(
        f"| {TEST_NAME[k][0]} | {TEST_NAME[k][1]} | {pos(t['evsi'])} | {pos(t['total_cost'])} | {money(t['net_value'])} | "
        f"{'Run' if t['net_value'] > 0 else 'Do not run'} |" for k in e['ranking'] for t in [e['tests'][k]])
    changed = (f"the {pos(ph['restated']['memo_over_forecast_cost'])} over-forecast is restated to "
               f"{pos(ph['restated']['excess_store_stock_cost'])} of extra store stock (receipts follow sales); the "
               f"\"apply the bias correction now\" advice is withdrawn for store ordering (no saving at equal service: "
               f"{money(s['verdict']['policy_cost_saving_at_best_z'])}); the tortilla and delist tests "
               f"are not worth running; forecast bias on weeks without a stock-out is "
               f"{pct(ph['bias_refit']['in_stock_weeks']['bias'])}, not lower, because stock-outs are demand spikes.")
    return {
        'plan_gp': money(p['total']['mean']), 'plan_ci': rng(*p['total']['ci90'], money),
        'plan_p_pos': pct(p['total']['p_positive'], 0, signed=False), 'plan_draws': f"{p['design']['draws']:,}",
        'backbill': rng(p['one_off_backbill']['lower_scan_only'], p['one_off_backbill']['upper_scan_plus_planned_display'], pos),
        'drop_events': str(sum(cells[c]['events'] for c in CUT_CELLS)),
        'keep_events': str(sum(cells[c]['events'] for c in KEEP_CELLS)),
        'promo_gp': money(lev['promo_calendar']['mean']), 'promo_ci': rng(*lev['promo_calendar']['ci90'], money),
        'drop_gpbf': money(drop_gpbf), 'promo_rho0': money(p['promo_funding_sensitivity']['rho_0']),
        'drop_funding': pos(sum(inp[c]['scan_back'] + inp[c]['display_fee'] for c in CUT_CELLS)),
        'vendor_gp': money(lev['vendor_terms']['mean']), 'vendor_ci': rng(*lev['vendor_terms']['ci90'], money),
        'underbilled': pct(p['inputs']['vendor']['underbilled_share'], signed=False),
        'cut_n': str(a['chain']['distinct_skus_cut']), 'cut_gp': money(lev['assortment']['mean']),
        'cut_ci': rng(*lev['assortment']['ci90'], money),
        'tau': pct(a['tau']['point'], 0, signed=False), 'tau_ci': rng(*a['tau']['ci90'], lambda x: pct(x, 0, signed=False)),
        'tortilla_action': {'hold': 'keep', 'roll_back': 'roll back'}[p['tortilla_action']],
        'price_gp': money(lev['prices']['mean']), 'price_ci': rng(*lev['prices']['ci90'], money),
        'fc_gp': money(lev['forecast']['mean']) if lev['forecast']['mean'] else '$0', 'sim_saving': money(s['verdict']['policy_cost_saving_at_best_z']),
        'promo_var': pct(lev['promo_calendar']['variance_share_removed_if_known'], 0, signed=False),
        'display_breakeven': pct(p['display_events']['breakeven_rho_to_drop'], 0, signed=False),
        'alt_gp': money(p['if_display_also_dropped']['mean']), 'alt_ci': rng(*p['if_display_also_dropped']['ci90'], money),
        'cut_rows': cut_rows(a), 'exec_cost': pos(e['design']['execution_cost_assumed']), 'test_rows': tests,
        'rho_evpi': pos(e['tests']['display_holdout']['funding_share_evpi']), 'changed': changed,
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
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))['parameters']
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
        status = (f"answer key not yet received — {sc['parameters']} parameters frozen, none scored. The request to the "
                  'dataset\'s author is drafted and has not been sent.')
        summary = 'Truth, error and coverage fill in automatically when `analysis/scorecard/answer_key.json` is committed.'
        wrong = ('Nothing yet: the key has not been received, so no estimate has been tested against ground truth. '
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
