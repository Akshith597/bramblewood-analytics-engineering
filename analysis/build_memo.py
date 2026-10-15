"""Render docs/decision_memo.md from analysis/results/*.json and analysis/memo_template.md.

Every figure in the memo is a named placeholder filled from a result file. The narrative also makes a few
qualitative claims ("inconclusive", "far from break-even"); CLAIMS asserts each one against the results, so a
re-run that changes a conclusion fails the build instead of silently publishing stale wording.
"""
import json
import re

from analysis.common import RESULTS, ROOT

TEMPLATE = ROOT / 'analysis/memo_template.md'
MEMO = ROOT / 'docs/decision_memo.md'


def load():
    return {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in sorted(RESULTS.glob('*.json'))}


def pct(v, digits=1, signed=True):
    s = f'{v * 100:+.{digits}f}%' if signed else f'{v * 100:.{digits}f}%'
    return s.replace('-', '−')


def money(v):
    sign = '−' if v < 0 else ('+' if v > 0 else '')
    v = abs(v)
    body = f'${v / 1e6:.2f}M' if v >= 1e6 else (f'${v / 1e3:.1f}K' if v >= 1e3 else f'${v:,.2f}')
    return sign + body


def num(v, digits=2):
    return f'{v:.{digits}f}'.replace('-', '−')


def rng(lo, hi, fmt):
    return f'{fmt(lo)} to {fmt(hi)}'


def pval(p):
    return '< 0.001' if p < 0.001 else f'{p:.3f}'


def figures(r):
    d, p, f, v = r['delist'], r['pricing'], r['forecast'], r['funding']
    pr, dec, pooled = p['preregistered'], p['decisions'], p['pooled']
    gr, bs = dec['golden_ridge_kettle'], dec['bramble_select_tortilla']
    subs = pooled['by_subcategory']
    out = {
        'd_effect': pct(d['gp']['beta']), 'd_ci': rng(*d['gp']['ci90_wild'], pct),
        'd_p': pval(d['gp']['p_wild']), 'd_ri_p': pval(d['gp']['randomization']['p_value']),
        'd_donors': str(len(d['donor_stores'])),
        'd_mde': pct(abs(d['decision']['mde_pct']), signed=False),
        'd_power2': pct(d['gp']['randomization']['power_against_loss']['2pct'], 0, signed=False),
        'd_units': pct(abs(d['units']['beta']), signed=False), 'd_units_ci': rng(*d['units']['ci90_wild'], pct),
        'd_units_p': pval(d['units']['p_wild']), 'd_sales': pct(d['sales']['beta']),
        'd_transfer': pct(d['transfer']['transfer_rate'], 0, signed=False),
        'd_transfer_ci': rng(*d['transfer']['transfer_rate_ci90'], lambda x: pct(x, 0, signed=False)),
        'd_fake24': pct(d['gp_fake_dates']['FY2024-W27']['beta']),
        'd_fake24_p': pval(d['gp_fake_dates']['FY2024-W27']['p_wild']),
        'd_yoy': pct(d['exploratory_yoy_adjusted_gp']),
        'd_sc': 'synthetic control ' + pct(d['gp_synthetic_control']['effect_mean']),
        'd_large': 'large-store controls only ' + pct(d['gp_large_controls_only']['beta']),
        'd_dollar': money(d['rollout']['annual_gp_change']),
        'd_dollar_ci': rng(*d['rollout']['annual_gp_change_ci90'], money),
        'd_log': pct(d['gp_log_sensitivity']['beta']) + ', ' + rng(*d['gp_log_sensitivity']['ci90_wild'], pct),
        'p_gr_inc': pct(gr['price_increase']), 'p_bs_inc': pct(bs['price_increase']),
        'p_gr_margin': pct(gr['margin_before'], signed=False), 'p_bs_margin': pct(bs['margin_before'], signed=False),
        'p_gr_be': num(gr['breakeven_elasticity']), 'p_bs_be': num(bs['breakeven_elasticity']),
        'p_gr_pooled': num(gr['pooled_elasticity_used']), 'p_bs_pooled': num(bs['pooled_elasticity_used']),
        'p_gr_pooled_ci': rng(*gr['pooled_elasticity_range'], num),
        'p_bs_pooled_ci': rng(*bs['pooled_elasticity_range'], num),
        'p_gr_gp': money(gr['conditional_annual_gp_change']),
        'p_gr_gp_ci': rng(*gr['conditional_annual_gp_range'], money),
        'p_bs_gp': money(bs['conditional_annual_gp_change']),
        'p_bs_gp_ci': rng(*bs['conditional_annual_gp_range'], money),
        'p_gr_pretrend': pval(pr['golden_ridge_kettle']['event_study']['pre_trend_p']),
        'p_pooled_n': f"{pooled['n']:,}",
        'p_subcats': '; '.join(f"{s} {num(x['elasticity'])}" + ('' if x['identified'] else ' (not identified)')
                               for s, x in sorted(subs.items(), key=lambda kv: kv[1]['elasticity'])),
        'p_pl_shift': num(abs(pooled['private_label_shift']['elasticity_shift'])),
        'p_pl_shift_ci': rng(*pooled['private_label_shift']['ci90'], num),
        'f_bias': pct(f['fy2025']['bias']), 'f_bias_ci': rng(*f['fy2025']['bias_ci90_sku_bootstrap'], pct),
        'f_wape': pct(f['fy2025']['wape'], signed=False),
        'f_bias_promo': pct(f['by_promoted']['True']['bias']),
        'f_bias_nonpromo': pct(f['by_promoted']['False']['bias']),
        'f_mase_lag2': num(f['mase']['vs_lag2_naive']), 'f_mase_seasonal': num(f['mase']['vs_seasonal_naive']),
        'f_bias_after': pct(f['bias_correction_backtest']['bias_after']),
        'f_wape_after': pct(f['bias_correction_backtest']['wape_after'], signed=False),
        'f_cost': money(f['fy2025_net_overforecast']['cost']).lstrip('+'),
        'v_low': money(v['approved_gap_range']['lower_scan_only']).lstrip('+'),
        'v_high': money(v['approved_gap_range']['upper_scan_plus_planned_display']).lstrip('+'),
        'v_events': f"{v['by_status']['Approved']['events']:,}",
        'v_noclaim': f"{v['by_status']['Approved']['events_without_claim']:,}",
        'v_cancelled': money(v['cancelled_billed_not_collected']).lstrip('+'),
        'x_checks': str(len(r['crosscheck_python']['checks'])),
        'x_status': 'all agree' if r['crosscheck_python']['status'] == 'pass' else 'DISAGREEMENT',
    }
    return out


CLAIMS = {
    'Q1 outcome is underpowered/inconclusive': lambda r: r['delist']['decision']['outcome'] == 'underpowered',
    'Q1 fake FY2024 date is significant at 10%': lambda r: r['delist']['gp_fake_dates']['FY2024-W27']['p_wild'] < 0.10,
    'Q1 robustness estimates share the sign of the main estimate': lambda r: all(
        x > 0 for x in (r['delist']['gp']['beta'], r['delist']['gp_synthetic_control']['effect_mean'],
                        r['delist']['gp_large_controls_only']['beta'])),
    'Q1 units fell significantly': lambda r: r['delist']['units']['ci90_wild'][1] < 0,
    'Q1 net sales flat (CI spans 0)': lambda r: r['delist']['sales']['ci90_wild'][0] < 0 < r['delist']['sales']['ci90_wild'][1],
    'Q3 no design credible for either event': lambda r: all(
        x['outcome'] == 'not_identified' for x in r['pricing']['decisions'].values()),
    'Q3 kettle pooled range is far below break-even': lambda r: (
        r['pricing']['decisions']['golden_ridge_kettle']['pooled_elasticity_range'][0]
        > r['pricing']['decisions']['golden_ridge_kettle']['breakeven_elasticity'] + 1),
    'Q3 tortilla break-even inside pooled range (coin flip)': lambda r: (
        r['pricing']['decisions']['bramble_select_tortilla']['pooled_elasticity_range'][0]
        < r['pricing']['decisions']['bramble_select_tortilla']['breakeven_elasticity']
        < r['pricing']['decisions']['bramble_select_tortilla']['pooled_elasticity_range'][1]),
    'Q3 private label more price-sensitive': lambda r: r['pricing']['pooled']['private_label_shift']['ci90'][1] < 0,
    'Q3 popcorn is the only unidentified subcategory': lambda r: [
        s for s, x in r['pricing']['pooled']['by_subcategory'].items() if not x['identified']] == ['Popcorn'],
    'Q3 exploratory zone design failed GR backtest': lambda r: not r['pricing']['zone_dose']['backtest']['covered'],
    'Q3 exploratory zone design failed tortilla pre-trend': lambda r: (
        not r['pricing']['zone_dose']['bramble_select_tortilla']['checks_passed']['pre_trend']),
    'Q4 over-forecast is significant': lambda r: r['forecast']['fy2025']['bias_ci90_sku_bootstrap'][0] > 0,
    'Q4 forecast beats naive benchmarks': lambda r: max(r['forecast']['mase']['vs_lag2_naive'],
                                                         r['forecast']['mase']['vs_seasonal_naive']) < 1,
    'Q4 out-of-sample correction helps': lambda r: (
        r['forecast']['bias_correction_backtest']['wape_after'] < r['forecast']['bias_correction_backtest']['wape_before']),
    'Q4 promoted weeks more biased': lambda r: r['forecast']['by_promoted']['True']['bias'] > r['forecast']['by_promoted']['False']['bias'],
    'Q5 scan-back under-billed': lambda r: r['funding']['approved_gap_range']['lower_scan_only'] > 0,
    'Q5 approved fully collected': lambda r: abs(r['funding']['approved_billed_not_collected']) < 0.005,
    'Planted effects recovered': lambda r: all(
        abs(x['recovered_shift'] - float(k)) < 1e-6 for k, x in r['delist']['gp_planted_effect'].items()) and all(
        abs(r['pricing'][d][e]['planted_elasticity_recovered'] + 1.5) < 1e-5
        for d in ('preregistered', 'zone_dose') for e in ('golden_ridge_kettle', 'bramble_select_tortilla')),
}


def render(results=None):
    results = results or load()
    failed = [name for name, check in CLAIMS.items() if not check(results)]
    if failed:
        raise AssertionError('Memo narrative no longer matches results: ' + '; '.join(failed))
    template = TEMPLATE.read_text(encoding='utf-8')
    values = figures(results)
    missing = set(re.findall(r'\{(\w+)\}', template)) - set(values)
    if missing:
        raise KeyError(f'Template placeholders without a result: {sorted(missing)}')
    return template.format(**values)


def main():
    MEMO.write_text(render(), encoding='utf-8', newline='\n')
    print(f'Wrote {MEMO.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
