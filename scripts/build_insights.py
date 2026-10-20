"""Render business-facing charts and a static insights page from the validated marts.

Dependency-free SVG keeps the figures reproducible in CI and readable on GitHub.
Outputs:
  docs/assets/insights/*.svg          committed figures embedded in the README
  evidence/insights_figures.json      the headline numbers behind the figures, read by analysis/build_public.py
  target/insights.html                dashboard page published next to the dbt catalog
"""

from pathlib import Path
from html import escape
import json
import math

import duckdb

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / 'docs/assets/insights'

SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK_2 = '#52514e'
MUTED = '#8a8984'
GRID = '#e6e5e0'
PRIOR = '#b4b2aa'  # prior-year context series
SERIES_1 = '#2a78d6'  # current year / primary measure
SERIES_2 = '#eb6834'  # secondary measure / funding gap
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

# Comparable stores: selling in all 104 weeks with no remodel, so year-over-year changes are like-for-like.
COMPARABLE = """comparable as (
        select store_id from fct_sales join dim_store using (store_id)
        where remodel_start is null group by 1 having count(distinct week_key) = 104)"""

QUERIES = {
    'weekly_sales': f"""with {COMPARABLE}
        select w.fiscal_year, w.fiscal_week, sum(s.net_sales) as net_sales,
            count(distinct s.store_id) as stores
        from fct_sales as s join dim_week as w using (week_key)
        where s.store_id in (select store_id from comparable)
        group by all order by 1, 2""",
    'holidays': """select fiscal_year, fiscal_week, holiday_event from dim_week
        where holiday_event is not null order by 1, 2""",
    'subcategory': f"""with {COMPARABLE}
        select i.subcategory,
            sum(s.net_sales) filter (where s.fiscal_year = 2024) as sales_fy24,
            sum(s.net_sales) filter (where s.fiscal_year = 2025) as sales_fy25,
            sum(s.gross_profit_before_funding) filter (where s.fiscal_year = 2024)
                / sum(s.net_sales) filter (where s.fiscal_year = 2024) as margin_fy24,
            sum(s.gross_profit_before_funding) filter (where s.fiscal_year = 2025)
                / sum(s.net_sales) filter (where s.fiscal_year = 2025) as margin_fy25
        from fct_sales as s join dim_item as i using (sku_id)
        where s.store_id in (select store_id from comparable)
        group by 1 order by sales_fy25 desc""",
    'forecast': """select w.fiscal_year, w.fiscal_period,
        sum(f.absolute_error_units) / sum(abs(f.actual_units)) as wape,
        sum(f.error_units) / sum(abs(f.actual_units)) as bias
        from mart_forecast_accuracy as f join dim_week as w using (week_key)
        where f.has_actual and f.lead_weeks = 2 group by all order by 1, 2""",
    'funding': """select v.vendor_name, sum(p.funding_owed_estimate) as owed,
        sum(p.total_billed) as billed, sum(p.owed_minus_billed_estimate) as gap,
        count(*) filter (where p.approved_without_claim) as unclaimed_events
        from mart_promotion_funding as p join dim_vendor as v using (vendor_id)
        where p.status = 'Approved' group by 1 having sum(p.funding_owed_estimate) > 0
        order by gap desc""",
    'kpis': """select
        (select sum(source_rows) from audit_reconciliation) as source_rows,
        (select source_rows from audit_reconciliation where disposition = 'accepted') as accepted_rows,
        (select sum(net_sales) from fct_sales) as net_sales,
        (select sum(gross_profit_before_funding) / sum(net_sales) from fct_sales) as margin,
        (select count(distinct store_id) from fct_sales) as stores,
        (select count(distinct sku_id) from fct_sales) as skus,
        (select sum(owed_minus_billed_estimate) from mart_promotion_funding
            where status = 'Approved') as funding_gap""",
}


def money(value, digits=0):
    value = float(value)
    if abs(value) >= 1e6:
        return f'${value / 1e6:,.{max(digits, 1)}f}M'
    if abs(value) >= 1e3:
        return f'${value / 1e3:,.{digits}f}K'
    return f'${value:,.0f}'


def pct(value, digits=1, signed=False):
    return f'{float(value) * 100:{"+" if signed else ""}.{digits}f}%'


def nice_ticks(low, high, count=5):
    span = (high - low) or 1
    raw = span / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = (low // step) * step
    ticks, tick = [], start
    while tick <= high + step * 0.999:
        ticks.append(round(tick, 10))
        tick += step
    return ticks


class Figure:
    """Minimal SVG builder: a titled card with a plot region and footnote."""

    def __init__(self, width, height, title, subtitle, note):
        self.width, self.height = width, height
        self.parts = [
            f'<rect width="{width}" height="{height}" rx="12" fill="{SURFACE}" stroke="{GRID}"/>',
            self.text(28, 40, title, size=19, weight=650),
            self.text(28, 64, subtitle, size=13.5, fill=INK_2),
            self.text(28, height - 18, note, size=11.5, fill=MUTED),
        ]
        self.title = title
        self.subtitle = subtitle

    @staticmethod
    def text(x, y, value, size=12, fill=INK, weight=400, anchor='start', extra=''):
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{extra}>{escape(str(value))}</text>'
        )

    def add(self, *parts):
        self.parts.extend(parts)

    def svg(self):
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" font-family="{FONT}">\n'
            f'<title>{escape(self.title)}</title><desc>{escape(self.subtitle)}</desc>\n'
            + '\n'.join(self.parts)
            + '\n</svg>\n'
        )


def tip(value):
    return f'<title>{escape(value)}</title>'


def line_path(points):
    return 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in points)


def weekly_sales_figure(rows, holidays):
    totals = {y: sum(float(r['net_sales']) for r in rows if r['fiscal_year'] == y) for y in (2024, 2025)}
    ahead = sum(
        1
        for a, b in zip((r for r in rows if r['fiscal_year'] == 2025), (r for r in rows if r['fiscal_year'] == 2024))
        if float(a['net_sales']) > float(b['net_sales'])
    )
    stores = rows[0]['stores']
    fig = Figure(
        960,
        400,
        f'Weekly net sales, {stores} comparable stores, FY2024 vs FY2025',
        f'Comparable-store sales {pct(totals[2025] / totals[2024] - 1, signed=True)} year over year; '
        f'FY2025 is ahead in {ahead} of 52 weeks. Dashed lines mark holiday weeks.',
        'Source: fct_sales · stores selling all 104 weeks with no remodel (excludes #112 remodel, '
        '#124 opened FY2025) · accepted POS, returns netted · descriptive, not causal · synthetic data',
    )
    left, right, top, bottom = 76, 880, 118, 342
    values = [float(r['net_sales']) for r in rows]
    ticks = nice_ticks(0, max(values))
    y_max = ticks[-1]
    x = lambda week: left + (week - 1) / 51 * (right - left)
    y = lambda value: bottom - value / y_max * (bottom - top)
    for tick in ticks:
        fig.add(
            f'<line x1="{left}" x2="{right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" stroke="{GRID}"/>',
            fig.text(left - 10, y(tick) + 4, money(tick), size=11.5, fill=INK_2, anchor='end'),
        )
    for week in (1, 13, 26, 39, 52):
        fig.add(fig.text(x(week), bottom + 20, f'Wk {week}', size=11.5, fill=INK_2, anchor='middle'))
    # Holiday markers use FY2025 calendar positions.
    for i, holiday in enumerate(h for h in holidays if h['fiscal_year'] == 2025):
        hx = x(holiday['fiscal_week'])
        label_y = top - 26 + (i % 2) * 13
        fig.add(
            f'<line x1="{hx:.1f}" x2="{hx:.1f}" y1="{label_y + 4:.1f}" y2="{bottom}" stroke="{GRID}" '
            f'stroke-dasharray="3 3"/>',
            fig.text(hx, label_y, holiday['holiday_event'], size=10.5, fill=MUTED, anchor='middle'),
        )
    for year, color in ((2024, PRIOR), (2025, SERIES_1)):
        series = [r for r in rows if r['fiscal_year'] == year]
        points = [(x(r['fiscal_week']), y(float(r['net_sales']))) for r in series]
        fig.add(
            f'<path d="{line_path(points)}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
        )
        for r, (px, py) in zip(series, points):
            fig.add(
                f'<circle class="hit" cx="{px:.1f}" cy="{py:.1f}" r="7" fill="transparent">'
                + tip(f'FY{year} week {r["fiscal_week"]}: {money(r["net_sales"], 1)} ({r["stores"]} stores)')
                + '</circle>'
            )
        end_x, end_y = points[-1]
        total = sum(float(r['net_sales']) for r in series)
        fig.add(
            f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="4" fill="{color}" stroke="{SURFACE}" stroke-width="2"/>',
            fig.text(end_x + 10, end_y + (-6 if year == 2025 else 12), f'FY{year}', size=12, weight=650),
            fig.text(end_x + 10, end_y + (8 if year == 2025 else 26), money(total, 2), size=11, fill=INK_2),
        )
    return fig


def subcategory_figure(rows):
    row_h = 40
    top = 112
    growth = {r['subcategory']: float(r['sales_fy25']) / float(r['sales_fy24']) - 1 for r in rows}
    margin = {r['subcategory']: (float(r['margin_fy25']) - float(r['margin_fy24'])) * 100 for r in rows}
    fastest = sorted(growth, key=growth.get, reverse=True)[:2]
    weakest = min(margin, key=margin.get)
    fig = Figure(
        960,
        top + row_h * len(rows) + 52,
        'Net sales and gross margin by subcategory, comparable stores',
        f'{fastest[0]} ({pct(growth[fastest[0]], 0, True)}) and {fastest[1]} '
        f'({pct(growth[fastest[1]], 0, True)}) grew fastest; {weakest} gave up the most margin '
        f'({margin[weakest]:+.1f} pp).',
        'Source: fct_sales · comparable stores only · gross margin before vendor funding · '
        'descriptive changes, not causal effects · synthetic data',
    )
    left, right = 178, 640
    peak = max(float(r['sales_fy25']) for r in rows)
    scale = lambda value: float(value) / peak * (right - left)
    fig.add(
        f'<rect x="{left}" y="82" width="10" height="10" rx="2" fill="{PRIOR}"/>',
        fig.text(left + 16, 91, 'FY2024', size=12, fill=INK_2),
        f'<rect x="{left + 80}" y="82" width="10" height="10" rx="2" fill="{SERIES_1}"/>',
        fig.text(left + 96, 91, 'FY2025', size=12, fill=INK_2),
        fig.text(700, 91, 'Sales YoY', size=12, fill=INK_2, weight=600),
        fig.text(800, 91, 'FY2025 margin (pp change)', size=12, fill=INK_2, weight=600),
    )
    for i, r in enumerate(rows):
        y0 = top + i * row_h
        margin_change = margin[r['subcategory']]
        fig.add(fig.text(left - 12, y0 + 19, r['subcategory'], size=12.5, anchor='end'))
        for offset, key, color, year in ((4, 'sales_fy24', PRIOR, 2024), (16, 'sales_fy25', SERIES_1, 2025)):
            fig.add(
                f'<rect class="hit" x="{left}" y="{y0 + offset}" width="{max(scale(r[key]), 2):.1f}" height="10" '
                f'rx="2" fill="{color}">' + tip(f'{r["subcategory"]} FY{year}: {money(r[key], 2)}') + '</rect>'
            )
        fig.add(
            fig.text(left + scale(r['sales_fy25']) + 8, y0 + 25, money(r['sales_fy25'], 2), size=11, fill=INK_2),
            fig.text(700, y0 + 22, pct(growth[r['subcategory']], signed=True), size=12.5, weight=600),
            fig.text(
                800,
                y0 + 22,
                f'{pct(r["margin_fy25"])}  ({margin_change:+.1f} pp)',
                size=12.5,
                fill=INK if margin_change < -1 else INK_2,
                weight=600 if margin_change < -1 else 400,
            ),
        )
    return fig


def forecast_figure(rows):
    wape = [float(r['wape']) for r in rows]
    over = sum(float(r['bias']) > 0 for r in rows)
    fig = Figure(
        960,
        380,
        'Forecast accuracy by fiscal period (two-week lead)',
        f'The chain forecast over-forecasts in '
        f'{"every one" if over == len(rows) else over} of {len(rows)} periods; '
        f'WAPE ranges {pct(min(wape), 0)}–{pct(max(wape), 0)}.',
        'Source: mart_forecast_accuracy · WAPE = Σ|forecast − actual| / Σactual; bias = Σ(forecast − actual) / '
        'Σactual · actuals may be stock-constrained · synthetic data',
    )
    left, right, top, bottom = 64, 840, 100, 318
    ticks = nice_ticks(0, max(max(float(r['wape']), float(r['bias'])) for r in rows))
    y_max = ticks[-1]
    n = len(rows)
    x = lambda i: left + i / (n - 1) * (right - left)
    y = lambda value: bottom - value / y_max * (bottom - top)
    for tick in ticks:
        fig.add(
            f'<line x1="{left}" x2="{right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" '
            f'stroke="{INK_2 if tick == 0 else GRID}"/>',
            fig.text(left - 10, y(tick) + 4, pct(tick, 0), size=11.5, fill=INK_2, anchor='end'),
        )
    for i, r in enumerate(rows):
        if r['fiscal_period'] in (1, 7):
            fig.add(
                fig.text(
                    x(i),
                    bottom + 20,
                    f'FY{r["fiscal_year"]} P{r["fiscal_period"]}',
                    size=11.5,
                    fill=INK_2,
                    anchor='middle',
                )
            )
    for key, color, label in (('wape', SERIES_1, 'WAPE'), ('bias', SERIES_2, 'Bias')):
        points = [(x(i), y(float(r[key]))) for i, r in enumerate(rows)]
        fig.add(
            f'<path d="{line_path(points)}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
        )
        for r, (px, py) in zip(rows, points):
            fig.add(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{color}"/>'
                f'<circle class="hit" cx="{px:.1f}" cy="{py:.1f}" r="8" fill="transparent">'
                + tip(f'FY{r["fiscal_year"]} P{r["fiscal_period"]} {label}: {pct(r[key])}')
                + '</circle>'
            )
        end_x, end_y = points[-1]
        fig.add(fig.text(end_x + 10, end_y + 4, label, size=12, weight=650))
    return fig


def funding_figure(rows):
    row_h = 34
    top = 104
    fig = Figure(
        960,
        top + row_h * len(rows) + 52,
        'Estimated vendor funding owed but not billed',
        'Approved promotions: contractual scan-back + display fees minus amounts billed, by vendor.',
        'Source: mart_promotion_funding · estimate assumes approved events executed as planned · '
        'a review queue, not recovered cash · synthetic data',
    )
    left, right = 290, 650
    peak = max(float(r['gap']) for r in rows)
    fig.add(
        fig.text(left, 90, 'Owed − billed', size=12, fill=INK_2, weight=600),
        fig.text(760, 90, 'Owed vs billed', size=12, fill=INK_2, weight=600),
    )
    for i, r in enumerate(rows):
        y0 = top + i * row_h
        width = max(float(r['gap']) / peak * (right - left), 2)
        fig.add(
            fig.text(left - 12, y0 + 17, r['vendor_name'], size=12.5, anchor='end'),
            f'<rect class="hit" x="{left}" y="{y0 + 5}" width="{width:.1f}" height="16" rx="3" fill="{SERIES_2}">'
            + tip(
                f'{r["vendor_name"]}: owed {money(r["owed"], 1)}, billed {money(r["billed"], 1)}, '
                f'gap {money(r["gap"], 1)}; {r["unclaimed_events"]} approved events without a claim'
            )
            + '</rect>',
            fig.text(left + width + 8, y0 + 18, money(r['gap'], 1), size=12, weight=600),
            fig.text(760, y0 + 18, f'{money(r["owed"])} vs {money(r["billed"])}', size=12, fill=INK_2),
        )
    return fig


def table_html(headers, rows):
    head = ''.join(f'<th>{escape(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{escape(str(c))}</td>' for c in row) + '</tr>' for row in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def page_html(kpis, figures):
    tiles = [
        (money(kpis['net_sales'], 1), 'accepted net sales, FY2024–FY2025'),
        (pct(kpis['margin']), 'gross margin before vendor funding'),
        (f'{kpis["accepted_rows"]:,} / {kpis["source_rows"]:,}', 'POS rows accepted; every exclusion classified'),
        (money(kpis['funding_gap']), 'estimated funding owed but not billed'),
        (f'{kpis["stores"]} · {kpis["skus"]}', 'stores · SKUs with sales'),
    ]
    tile_html = ''.join(f'<div class="tile"><b>{escape(v)}</b><span>{escape(label)}</span></div>' for v, label in tiles)
    sections = ''.join(
        f'<section><figure>{svg}</figure><details><summary>Data table</summary>{table}</details></section>'
        for svg, table in figures
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bramblewood Insights</title>
<style>
:root {{ --bg:#f3f2ee; --surface:{SURFACE}; --ink:{INK}; --ink-2:{INK_2}; --line:{GRID}; --accent:#102d2d; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#141413; --surface:#1f1f1e;
  --ink:#f5f5f3; --ink-2:#c3c2b7; --line:#3a3a37; --accent:#9fd3cc; }} }}
:root[data-theme="dark"] {{ --bg:#141413; --surface:#1f1f1e; --ink:#f5f5f3; --ink-2:#c3c2b7; --line:#3a3a37; --accent:#9fd3cc; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:{FONT}; line-height:1.5; }}
main {{ max-width:1000px; margin:0 auto; padding:32px 16px 64px; }}
header h1 {{ margin:0 0 4px; font-size:28px; }}
header p {{ margin:0; color:var(--ink-2); }}
nav {{ margin:12px 0 24px; display:flex; gap:16px; flex-wrap:wrap; }}
nav a {{ color:var(--accent); font-weight:600; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:24px; }}
.tile {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.tile b {{ display:block; font-size:22px; font-variant-numeric:tabular-nums; }}
.tile span {{ color:var(--ink-2); font-size:13px; }}
section {{ margin-bottom:28px; }}
figure {{ margin:0; overflow-x:auto; }}
figure svg {{ max-width:100%; height:auto; display:block; }}
.hit:hover {{ stroke:{INK}; stroke-width:1.5; }}
details {{ margin-top:6px; }}
summary {{ cursor:pointer; color:var(--ink-2); font-size:14px; }}
table {{ border-collapse:collapse; font-size:13px; margin-top:8px; width:100%; background:var(--surface); }}
th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; font-variant-numeric:tabular-nums; }}
.note {{ color:var(--ink-2); font-size:13px; border-top:1px solid var(--line); padding-top:16px; }}
</style></head>
<body><main>
<header><h1>Bramblewood retail insights</h1>
<p>Generated from tested dbt marts on every build. Hover a mark for its value; open a data table for exact figures.</p></header>
<nav><a href="index.html">dbt catalog &amp; lineage</a>
<a href="https://github.com/Akshith597/bramblewood-analytics-engineering">Source code</a>
<a href="https://github.com/Akshith597/bramblewood-analytics-engineering/blob/main/docs/case_study.md">Case study</a></nav>
<div class="tiles">{tile_html}</div>
{sections}
<p class="note">Synthetic portfolio data: all companies and transactions are fictional. Figures describe the supplied
extracts and are not real outcomes, recovered funds or causal effects.</p>
</main></body></html>
'''


def headline_figures(data):
    """Numbers the README quotes about the charts, so its prose is rendered rather than typed."""
    weekly = data['weekly_sales']
    totals = {y: sum(float(r['net_sales']) for r in weekly if r['fiscal_year'] == y) for y in (2024, 2025)}
    subs = {
        r['subcategory']: {
            'growth': float(r['sales_fy25']) / float(r['sales_fy24']) - 1,
            'margin_change_pp': (float(r['margin_fy25']) - float(r['margin_fy24'])) * 100,
            'sales_fy25': float(r['sales_fy25']),
        }
        for r in data['subcategory']
    }
    fy25 = [r for r in data['forecast'] if r['fiscal_year'] == 2025]
    return {
        'comparable_stores': weekly[0]['stores'],
        'comparable_growth': totals[2025] / totals[2024] - 1,
        'subcategories': subs,
        'subcategories_shrinking': sum(v['growth'] < 0 for v in subs.values()),
        'largest_subcategory': max(subs, key=lambda s: subs[s]['sales_fy25']),
        'forecast_periods_fy2025': len(fy25),
        'forecast_periods_over_fy2025': sum(float(r['bias']) > 0 for r in fy25),
        'stores': data['kpis'][0]['stores'],
        'skus': data['kpis'][0]['skus'],
    }


def main():
    with duckdb.connect(str(ROOT / 'warehouse/bramblewood.duckdb'), read_only=True) as con:
        data = {}
        for name, query in QUERIES.items():
            cursor = con.execute(query)
            columns = [c[0] for c in cursor.description]
            data[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]

    built = {
        'weekly_net_sales': (
            weekly_sales_figure(data['weekly_sales'], data['holidays']),
            table_html(
                ['Fiscal year', 'Week', 'Net sales', 'Stores'],
                [
                    (r['fiscal_year'], r['fiscal_week'], f'${float(r["net_sales"]):,.2f}', r['stores'])
                    for r in data['weekly_sales']
                ],
            ),
        ),
        'subcategory_performance': (
            subcategory_figure(data['subcategory']),
            table_html(
                ['Subcategory', 'FY2024 sales', 'FY2025 sales', 'FY2024 margin', 'FY2025 margin'],
                [
                    (
                        r['subcategory'],
                        f'${float(r["sales_fy24"]):,.2f}',
                        f'${float(r["sales_fy25"]):,.2f}',
                        pct(r['margin_fy24'], 2),
                        pct(r['margin_fy25'], 2),
                    )
                    for r in data['subcategory']
                ],
            ),
        ),
        'forecast_accuracy': (
            forecast_figure(data['forecast']),
            table_html(
                ['Fiscal year', 'Period', 'WAPE', 'Bias'],
                [
                    (r['fiscal_year'], r['fiscal_period'], pct(r['wape'], 2), pct(r['bias'], 2, True))
                    for r in data['forecast']
                ],
            ),
        ),
        'funding_gap_by_vendor': (
            funding_figure(data['funding']),
            table_html(
                ['Vendor', 'Owed (est.)', 'Billed', 'Owed − billed', 'Approved events without claim'],
                [
                    (
                        r['vendor_name'],
                        f'${float(r["owed"]):,.2f}',
                        f'${float(r["billed"]):,.2f}',
                        f'${float(r["gap"]):,.2f}',
                        r['unclaimed_events'],
                    )
                    for r in data['funding']
                ],
            ),
        ),
    }

    FIGURES.mkdir(parents=True, exist_ok=True)
    for name, (figure, _) in built.items():
        (FIGURES / f'{name}.svg').write_text(figure.svg(), encoding='utf-8', newline='\n')
    (ROOT / 'target').mkdir(exist_ok=True)
    kpis = data['kpis'][0]
    (ROOT / 'target/insights.html').write_text(
        page_html(kpis, [(fig.svg(), table) for fig, table in built.values()]), encoding='utf-8', newline='\n'
    )
    (ROOT / 'evidence/insights_figures.json').write_text(
        json.dumps(headline_figures(data), indent=2, sort_keys=True, default=float) + '\n',
        encoding='utf-8',
        newline='\n',
    )
    print(json.dumps({'figures': sorted(built), 'page': 'target/insights.html'}))


if __name__ == '__main__':
    main()
