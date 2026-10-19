"""Answer-key scorecard: freeze every estimate and 90% interval, then score them against the dataset's ground truth.

    python -m analysis.scorecard freeze    # write analysis/scorecard/frozen_estimates.json (once, before the key)
    python -m analysis.scorecard           # score frozen estimates against analysis/scorecard/answer_key.json

Rules fixed before the key is opened (re-frozen once as `estimates-frozen-v2`, still before the key: deviation 12):

- Scored values are the frozen file, never a re-run. tests_python/test_scorecard.py fails if any current result
  differs from its frozen value, so an estimator cannot be re-tuned after the key without the test (and the
  deviation log) showing it.
- error = estimate − truth; covered = truth inside the frozen 90% interval (both ends inclusive). Expected
  coverage is 90%; parameters frozen without an interval are scored for error only and counted as not covered.
- The key is transcribed into answer_key.json in its own commit, with each parameter mapped to the ids below. A
  truth defined differently from the estimate (e.g. a different elasticity or lift definition) is converted only
  by a rule written in analysis/scorecard/DEVIATIONS.md before the converted number is compared, and flagged.
- Anything learned from the key is logged in DEVIATIONS.md as a deviation; estimates and the plan are not changed.
- A parameter whose 90% interval misses the truth is listed under "What the scorecard proved wrong", with the
  public claims that depend on it (CLAIMS below), so a miss is traced to the decisions it touched.
"""
import json
import sys

from analysis.common import RESULTS, ROOT, round_floats

DIR = ROOT / 'analysis/scorecard'
FROZEN = DIR / 'frozen_estimates.json'
KEY = DIR / 'answer_key.json'
Z90 = 1.6448536

# Which public claims rest on each parameter family (used to trace a miss to the decisions it touched).
CLAIMS = {
    'elasticity': 'Q3 price verdicts (Golden Ridge keep; tortilla near break-even, rolled back) and the price lever',
    'promo_lift': 'Q2 promotion P&L and the promo-calendar lever (drop events without a display)',
    'cannibalisation': 'Q2 promotion P&L (sister losses) and the promo-calendar lever',
    'pantry_loading': 'Q2 promotion P&L (post-promotion dip) and the promo-calendar lever',
    'forecast_bias': 'Q4 forecast verdict, the $1.05M restatement and the inventory simulation',
    'delist': 'Q1 delist verdict and the cut list (transfer rate τ)',
}


def res(name):
    return json.loads((RESULTS / f'{name}.json').read_text(encoding='utf-8'))


def entry(pid, family, label, unit, estimate, ci90, source, primary=True, note=None):
    e = {'id': pid, 'family': family, 'parameter': label, 'unit': unit, 'estimate': estimate,
         'ci90': list(ci90) if ci90 else None, 'source': source, 'primary': primary}
    if note:
        e['note'] = note
    return e


def collect():
    """Every scored estimate, read from the current results."""
    p, pr, f, ph, d = res('pricing'), res('promotions'), res('forecast'), res('physical'), res('delist')
    out = []
    for s, x in sorted(p['pooled']['by_subcategory'].items()):
        out.append(entry(f'elasticity.{s}', 'elasticity', f'Own-price elasticity, {s} (national/regional brands)',
                         'elasticity', x['elasticity'], x['ci90'], 'pricing.pooled.by_subcategory',
                         note=None if x['identified'] else 'flagged not identified before the key'))
    pl = p['pooled']['private_label_shift']
    out.append(entry('elasticity.private_label_shift', 'elasticity', 'Private-label shift in own-price elasticity',
                     'elasticity points', pl['elasticity_shift'], pl['ci90'], 'pricing.pooled.private_label_shift'))
    for key, label in (('golden_ridge_kettle', 'Golden Ridge kettle'), ('bramble_select_tortilla',
                                                                          'Bramble Select (private label) tortilla')):
        x = p['decisions'][key]
        out.append(entry(f'elasticity.{key}', 'elasticity', f'Own-price elasticity, {label}', 'elasticity',
                         x['pooled_elasticity_used'], x['pooled_elasticity_range'], f'pricing.decisions.{key}'))
    for label, c in sorted(pr['fy2025']['mechanic_display'].items()):
        out.append(entry(f'promo_lift.{label}', 'promo_lift', f'Unit lift in promoted weeks, {label} (FY2025)',
                         'share over baseline', c['lift_pct'], c['lift_pct_ci90_store_bootstrap'],
                         'promotions.fy2025.mechanic_display'))
    a = pr['fy2025']['all']['all']
    out.append(entry('promo_lift.all', 'promo_lift', 'Unit lift in promoted weeks, all events (FY2025)',
                     'share over baseline', a['lift_pct'], a['lift_pct_ci90_store_bootstrap'], 'promotions.fy2025.all'))
    for s, x in sorted(pr['cannibalisation'].items()):
        out.append(entry(f'cannibalisation.{s}', 'cannibalisation',
                         f'Log change in a sister SKU\'s units per promoted same-subcategory SKU, {s}', 'log points',
                         x['per_promoted_sister'], [x['per_promoted_sister'] - Z90 * x['se_store_cr1'],
                                                    x['per_promoted_sister'] + Z90 * x['se_store_cr1']],
                         'promotions.cannibalisation'))
    for k, v in sorted(pr['post_dip_by_week'].items()):
        out.append(entry(f'pantry_loading.week{k}', 'pantry_loading',
                         f'Units vs baseline in post-promotion week {k} (pantry-loading dip)', 'share vs baseline',
                         v, pr['post_dip_ci90_store_bootstrap'][k], 'promotions.post_dip_by_week'))
    b = ph['bias_refit']
    out.append(entry('forecast_bias.fy2025_restored_demand', 'forecast_bias',
                     'Forecast bias FY2025, censored demand restored (primary)', 'share of demand',
                     b['restored_demand_all_weeks']['bias'], b['restored_demand_all_weeks']['ci90'], 'physical.bias_refit'))
    out.append(entry('forecast_bias.fy2025_in_stock_weeks', 'forecast_bias',
                     'Forecast bias FY2025, weeks with no stock-out (requested refit; selected on low demand)',
                     'share of actual', b['in_stock_weeks']['bias'], b['in_stock_weeks']['ci90'], 'physical.bias_refit',
                     primary=False))
    out.append(entry('forecast_bias.fy2025_all_weeks', 'forecast_bias', 'Forecast bias FY2025, all weeks (memo)',
                     'share of actual', f['fy2025']['bias'], f['fy2025']['bias_ci90_sku_bootstrap'], 'forecast.fy2025',
                     primary=False))
    for s, x in sorted(b['in_stock_by_subcategory'].items()):
        out.append(entry(f'forecast_bias.in_stock.{s}', 'forecast_bias', f'Forecast bias FY2025 in-stock weeks, {s}',
                         'share of actual', x['bias'], x['ci90'], 'physical.bias_refit.in_stock_by_subcategory',
                         primary=False))
    out.append(entry('delist.gp_effect', 'delist', 'Delist test: category GP effect in test stores',
                     'share of GP', d['gp']['beta'], d['gp']['ci90'], 'delist.gp'))
    out.append(entry('delist.units_effect', 'delist', 'Delist test: category units effect', 'log points',
                     d['units']['beta'], d['units']['ci90'], 'delist.units'))
    out.append(entry('delist.sales_effect', 'delist', 'Delist test: category net sales effect', 'log points',
                     d['sales']['beta'], d['sales']['ci90'], 'delist.sales'))
    out.append(entry('delist.transfer_rate', 'delist', 'Delist test: retained-SKU sales gained per $ of delisted '
                     'sales lost', 'ratio', d['transfer']['transfer_rate'], d['transfer']['transfer_rate_ci90'],
                     'delist.transfer'))
    return round_floats(out)


def freeze():
    DIR.mkdir(parents=True, exist_ok=True)
    payload = {'frozen_before_answer_key': True, 'tag': 'estimates-frozen-v2', 'parameters': collect()}
    FROZEN.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Froze {len(payload["parameters"])} parameters to {FROZEN.relative_to(ROOT)}')


def score_rows(frozen, key):
    """Pure scoring rule: error = estimate − truth; covered = truth within the frozen 90% interval, inclusive."""
    rows, wrong = [], []
    for e in frozen:
        t = key.get(e['id'])
        row = {**e, 'truth': t, 'error': None, 'covered': None}
        if t is not None:
            row['error'] = e['estimate'] - t
            row['covered'] = bool(e['ci90'] and e['ci90'][0] <= t <= e['ci90'][1])
            if not row['covered']:
                wrong.append({'id': e['id'], 'parameter': e['parameter'], 'estimate': e['estimate'], 'truth': t,
                              'ci90': e['ci90'], 'claims_affected': CLAIMS[e['family']]})
        rows.append(row)
    scored = [r for r in rows if r['truth'] is not None]
    families = {}
    for r in scored:
        f = families.setdefault(r['family'], {'scored': 0, 'covered': 0})
        f['scored'] += 1
        f['covered'] += r['covered']
    return {'key_received': bool(key), 'parameters': len(rows), 'scored': len(scored),
            'covered': sum(r['covered'] for r in scored),
            'coverage': sum(r['covered'] for r in scored) / len(scored) if scored else None,
            'by_family': families, 'rows': rows, 'proved_wrong': wrong,
            'unmapped_key_ids': sorted(set(key) - {e['id'] for e in frozen})}


def score():
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))['parameters']
    key = json.loads(KEY.read_text(encoding='utf-8'))['truth'] if KEY.exists() else {}
    result = score_rows(frozen, key)
    (RESULTS / 'scorecard.json').write_text(json.dumps(round_floats(result), indent=2, sort_keys=True) + '\n',
                                            encoding='utf-8', newline='\n')
    return result


def main():
    score()


if __name__ == '__main__':
    if sys.argv[1:] == ['freeze']:
        freeze()
    else:
        r = score()
        print(f"key received: {r['key_received']}; scored {r['scored']}/{r['parameters']}; coverage {r['coverage']}")
