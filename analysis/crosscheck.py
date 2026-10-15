"""Re-estimate the headline coefficients with the independent pure-Python implementation.

Reads the exported estimation panels (target/analysis_panels/*.csv), so it shares neither SQL nor solver code
with the primary estimates. analysis/crosscheck.R repeats the same comparisons with R fixest in CI.
"""
import csv
import json

from analysis.common import PANELS, RESULTS, round_floats, write_result
from analysis.delist import TREATED
from analysis.fe_reference import feols_reference

TOL_BETA, TOL_SE = 1e-6, 1e-4


def read(name):
    with (PANELS / f'{name}.csv').open(encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def delist_rows():
    rows = read('delist_panel')
    switch = min(int(r['week_index']) for r in rows if r['week_key'] == 'FY2025-W27')
    base = {}
    for r in rows:
        if int(r['week_index']) < switch:
            base.setdefault(r['store_id'], []).append(float(r['gp']))
    out = []
    for r in rows:
        treat = int(r['store_id']) in TREATED and int(r['week_index']) >= switch
        out.append({'store': r['store_id'], 'week': r['week_key'], 'cluster_id': r['store_id'],
                    'y': float(r['gp']) / (sum(base[r['store_id']]) / len(base[r['store_id']])),
                    'd': 1.0 if treat else 0.0})
    return out


def pricing_rows(name, cluster):
    return [{'fe_a': r['fe_a'], 'fe_b': r['fe_b'], 'fe_c': r['fe_c'], 'cluster_id': r[cluster],
             'y': float(r['log_units']), 'x_own': float(r['x_own']), 'x_cross': float(r['x_cross'])}
            for r in read(name)]


def main():
    delist = json.loads((RESULTS / 'delist.json').read_text(encoding='utf-8'))
    pricing = json.loads((RESULTS / 'pricing.json').read_text(encoding='utf-8'))
    checks = []

    ref = feols_reference(delist_rows(), 'y', ['d'], ['store', 'week'])
    checks.append(('delist_gp_beta', delist['gp']['beta'], ref['beta']['d'], TOL_BETA))
    checks.append(('delist_gp_se_cr1', delist['gp']['se_cr1'], ref['se']['d'], TOL_SE))

    fes = {'preregistered': ['fe_a', 'fe_b'], 'zone_dose': ['fe_a', 'fe_b', 'fe_c']}
    for design, fe_list in fes.items():
        for event in ('golden_ridge_kettle', 'bramble_select_tortilla'):
            ref = feols_reference(pricing_rows(f'{event}_{design}', 'store_id'), 'y', ['x_own', 'x_cross'], fe_list)
            for x in ('x_own', 'x_cross'):
                primary = pricing[design][event][x]
                checks.append((f'{design}_{event}_{x}_beta', primary['elasticity'], ref['beta'][x], TOL_BETA * 10))
                checks.append((f'{design}_{event}_{x}_se', primary['se_store_cr1'], ref['se'][x], TOL_SE))

    rows = []
    for name, primary, reference, tol in checks:
        # Primary values are stored at 6 significant figures; compare relative to that precision.
        diff = abs(primary - reference)
        allowed = max(tol, 5e-6 * abs(reference))
        rows.append({'check': name, 'primary': primary, 'reference': reference, 'abs_diff': diff,
                     'pass': diff <= allowed})
    failed = [r['check'] for r in rows if not r['pass']]
    write_result('crosscheck_python', round_floats({'status': 'fail' if failed else 'pass', 'checks': rows}))
    if failed:
        raise AssertionError(f'Implementations disagree: {failed}')
    print(f'{len(rows)} cross-checks passed')


if __name__ == '__main__':
    main()
