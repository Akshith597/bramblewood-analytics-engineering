"""Render README.md from analysis/readme_template.md, the analysis results and the build evidence.

The README is the most-read public claim in the repository, so it gets the same treatment as the memo: every
figure is a named placeholder filled from a generated file (analysis/results/*.json or evidence/*.json), the
template may not contain hand-typed numbers (tests_python/test_public_claims.py), and CI regenerates it and fails
on any difference.
"""
import json

from analysis.build_memo import figures as memo_figures, load, money, pct, rng
from analysis.common import ROOT

TEMPLATE = ROOT / 'analysis/readme_template.md'
README = ROOT / 'README.md'
EVIDENCE = ROOT / 'evidence'


def evidence():
    names = ('summary', 'independent_reconciliation', 'project_quality', 'load_manifest', 'insights_figures',
             'dbt_build_results')
    return {n: json.loads((EVIDENCE / f'{n}.json').read_text(encoding='utf-8')) for n in names}


def count(n):
    return f'{n:,.0f}'


def evidence_figures(e):
    s, rec, q, ins = e['summary'], e['independent_reconciliation'], e['project_quality'], e['insights_figures']
    kinds = {}
    for r in e['dbt_build_results']['results']:
        kind = r['unique_id'].split('.')[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    disp = {r['disposition']: r for r in s['reconciliation']}
    obs = s['quality_observations'][0]
    annual = {r['fiscal_year']: r for r in s['annual_metrics']}
    cost = s['cost_policy_sensitivity'][0]
    cov = {r['has_sales_record']: r['records'] for r in s['availability_coverage']}
    fc = {r['fiscal_year']: r for r in s['forecast_metrics']}
    tables = {t: n for f in e['load_manifest']['files'] for t, n in f['tables'].items()}
    sources = len(tables)
    sheets = len(next(f['tables'] for f in e['load_manifest']['files'] if f['file'].endswith('.xlsx')))
    subs = ins['subcategories']
    growers = sorted((k for k, v in subs.items() if v['growth'] > 0), key=lambda k: -subs[k]['growth'])
    largest = ins['largest_subcategory']
    margin_loser = min(subs, key=lambda k: subs[k]['margin_change_pp'])
    pp = lambda v: f'{v:+.1f} pp'.replace('-', '−')
    cancelled = next(r for r in s['funding_waterfall'] if r['status'] == 'Cancelled')
    return {
        'stores': count(ins['stores']), 'skus': count(ins['skus']), 'weeks': count(tables['fiscal_calendar']),
        'source_tables': count(sources), 'csvs': count(sources - sheets), 'sheets': count(sheets), 'models': count(q['models']),
        'contracts': count(q['enforced_mart_contracts']), 'columns': count(q['documented_typed_columns']),
        'data_tests': count(kinds.get('test', 0)), 'unit_tests': count(kinds.get('unit_test', 0)),
        'all_checks': count(kinds.get('test', 0) + kinds.get('unit_test', 0)),
        'pos_rows': count(sum(r['source_rows'] for r in s['reconciliation'])),
        'pos_accepted': count(disp['accepted']['source_rows']),
        'net_sales_exact': f"${float(rec['net_sales']):,.2f}", 'store_weeks': count(rec['store_weeks_reconciled']),
        'replay_rows': count(disp['exact_replay']['source_rows']),
        'replay_sales': f"${disp['exact_replay']['net_sales']:,.2f}",
        'upcs_padded': count(obs['upcs_padded']), 'legacy_dates': count(obs['legacy_dates']),
        'cost_rows': count(cost['affected_sales_rows']), 'cost_cogs': f"${cost['cogs_increase_vs_prior_cost']:,.2f}",
        'return_rows': count(obs['return_rows']), 'inventory_only': count(cov[False]),
        'cancelled_billed': f"${cancelled['total_billed']:,.2f}",
        'comp_stores': count(ins['comparable_stores']), 'comp_growth': pct(ins['comparable_growth']),
        'chain_growth': pct(annual[2025]['net_sales'] / annual[2024]['net_sales'] - 1),
        'shrinking': count(ins['subcategories_shrinking']), 'n_subcats': count(len(subs)),
        'growers': ', '.join(f"**{g} ({pct(subs[g]['growth'], 0)})**" for g in growers),
        'margin_loser': margin_loser, 'margin_loser_sales': pct(subs[margin_loser]['growth']),
        'margin_loser_pp': pp(subs[margin_loser]['margin_change_pp']),
        'largest': largest, 'largest_sales': pct(subs[largest]['growth']),
        'largest_pp': pp(subs[largest]['margin_change_pp']),
        'fc_periods': 'every period' if ins['forecast_periods_over_fy2025'] == ins['forecast_periods_fy2025']
        else f"{ins['forecast_periods_over_fy2025']} of {ins['forecast_periods_fy2025']} periods",
        'fc_bias_fy25': pct(fc[2025]['bias']), 'fc_wape_fy25': pct(fc[2025]['wape'], signed=False),
    }


def plan_figures(r):
    """README lines for the FY2026 plan and the work beyond the five questions (empty until those results exist)."""
    p, lev, ph, sc = r['plan'], r['plan']['by_lever'], r['physical'], r['scorecard']
    pos = lambda v: money(v).lstrip('+')
    plan = (f"The [one-page FY2026 plan](docs/fy2026_plan.md) models a **scenario-estimated annual GP opportunity of {money(p['total']['base'])} "
            f"after vendor funding** (low to high case {rng(*p['total']['range'], money)}). Drop promotions without a display "
            f"({money(lev['promo_calendar']['base'])}), treat vendor funding as a budget to re-negotiate and bill in full "
            f"({money(lev['vendor_terms']['base'])}), cut {r['assortment']['chain']['distinct_skus_cut']} SKUs on GP per "
            f"facing and measured demand transfer ({money(lev['assortment']['base'])}), keep Golden Ridge's price "
            f"({money(lev['prices']['base'])} with the tortilla call), and leave store replenishment alone. "
            f"The low and high cases set every uncertain input to the pessimistic or optimistic end of its range at once: "
            f"the 90% intervals of the transfer rate, elasticities and promotion results, plus stated assumptions about "
            f"how much vendor funding is re-won and how much under-billing is recovered. Unmodeled basket effects, vendor "
            f"responses and implementation costs can change the outcome. This is a scenario estimate, "
            f"not realized savings or a forecast.")
    ph_line = (f"That over-forecast never reached store shelves: receipts follow sales, and the "
               f"{pos(ph['restated']['memo_over_forecast_cost'])} of over-forecast units at cost became "
               f"{pos(ph['restated']['excess_store_stock_cost'])} of extra store stock; an inventory replay finds no saving from "
               f"the correction at equal service ({money(r['inventory_sim']['verdict']['policy_cost_saving_at_best_z'])}).")
    score = (f"Every estimate and interval is frozen for the [answer-key scorecard](docs/scorecard.md); "
             + ('the key is scored there.' if sc['key_received'] else "a request to the dataset's author is drafted and the "
                                                                'key is not yet scored.'))
    return {'plan_readme': plan, 'ph_readme': ph_line, 'scorecard_readme': score,
            'plan_total': money(p['total']['base']), 'plan_range': rng(*p['total']['range'], money),
            'a_plan': money(lev['assortment']['base'])}


def render(results=None, ev=None):
    results = results or load()
    values = {**memo_figures(results), **evidence_figures(ev or evidence()), **plan_figures(results)}
    return TEMPLATE.read_text(encoding='utf-8').format(**values)


def main():
    README.write_text(render(), encoding='utf-8', newline='\n')
    print(f'Wrote {README.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

