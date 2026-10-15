# From retail extracts to trusted analytical data

**Bramblewood Retail Analytics Warehouse**  
Analytics engineering portfolio · dbt / DuckDB / SQL / Python  
Synthetic data · FY2024–FY2025 · 24 stores · 151 master SKUs

[Decision memo](decision_memo.md) · [Live insights dashboard](https://akshith597.github.io/bramblewood-analytics-engineering/insights.html) · [dbt catalog](https://akshith597.github.io/bramblewood-analytics-engineering/) · [Repository](https://github.com/Akshith597/bramblewood-analytics-engineering)

## Business context

A fictional regional grocer needs consistent answers about category performance, replenishment, assortment and vendor funding. The supplied POS, inventory and merchandising systems disagree on keys and date formats, while prices, costs and shelf plans change over time.

The project asks: **How can these extracts become reusable business data without silently changing their meaning?** The deliverable is a tested warehouse and evidence trail that a reviewer can rebuild locally.

## Approach

Python lands 14 tables without business transformations and records file hashes plus source row numbers. dbt normalizes POS keys and dates, classifies rejected/replayed rows, resolves dimensional keys, and builds facts at explicit grains. Business marts reuse those facts for category performance, forecast accuracy, availability, assortment productivity and funding review.

All joins are designed around grain. Chain forecasts meet chain actuals; claims aggregate before they meet promotions; weekly facts meet exactly one effective price and cost. Independent Python arithmetic checks the sales results without reusing the transformation SQL.

## The most instructive failure

The initial cost-overlap test failed for `SS-1081`. One cost record ended March 1, 2025 while the next began February 16. Joining both directly would duplicate affected sales rows and distort revenue as well as margin.

The implemented policy lets the later effective start supersede the old cost. The original end date and adjustment flag remain queryable. **34 sales rows and 224 net units are affected; choosing the newer cost increases estimated COGS by $29.12.** This is disclosed sensitivity, not a source-owner-confirmed correction. See [cost evidence](../evidence/cost_policy_sensitivity.csv).

## Verified engineering outcomes

| Outcome | Evidence |
|---|---|
| 273,376 input POS rows → 273,262 accepted rows | 113 exact replays and one embedded header classified; no unexplained loss |
| $8,489.86 of duplicated source revenue prevented from entering the fact | [Reconciliation](../evidence/reconciliation.csv) |
| $21,886,423.88 accepted net sales | Independent comparison across 2,427 store-weeks |
| 30,985 UPCs and 83,351 legacy dates normalized | [Quality observations](../evidence/quality_observations.csv) |
| 160 return records preserved | Negative net sales were not treated as invalid data |
| 35 dbt models; 96 data tests; 4 unit tests; 13 enforced contracts | [Build results](../evidence/dbt_build_results.json) |
| 1,888 inventory-only records retained | Missing sales was not converted into zero demand |

## Business questions the marts can now support

**Category reporting.** Net sales are $10,586,731.33 in FY2024 and $11,299,692.55 in FY2025. Estimated gross margin before vendor funding is 29.29% and 28.37%, respectively. These are chain totals and include changing store coverage; they are not same-store growth or causal pricing effects. [Annual results](../evidence/annual_metrics.csv)

**Forecast review.** FY2025 forecast WAPE is 22.53% and bias is +13.40%, indicating overforecast on matched SKU-weeks. All 7,184 forecast rows have observed actuals. Actual sales can be stock-constrained; this is not unconstrained demand accuracy. FY2024 has 288 startup rows with lead time other than two weeks, so unfiltered year-over-year comparisons mix horizons. [Forecast results](../evidence/forecast_metrics.csv)

**Funding review.** Approved events have **$1,252,142.25 estimated contractual funding owed**, versus **$1,119,166.80 billed and collected**, exposing a **$132,975.45 estimated billing gap**. The estimate combines $781,642.25 scan-back on observed scoped net units and $470,500.00 planned display fees. It assumes planned approved events and displays executed; missing sales/discount signals are explicitly flagged. Separately, two cancelled-event claims total **$974.65 billed but uncollected**. Cancelled claims are a different control exception and are not added to the approved billing gap. [Waterfall](../evidence/funding_waterfall.csv) · [Assumption sensitivity](../evidence/funding_assumption_sensitivity.csv) · [Review queue](../evidence/funding_exception_queue.csv)

## What this demonstrates

The project shows SQL transformation, dimensional modeling, effective-dated joins, reconciliation, automated testing, lineage, metric governance and operational tradeoffs. Its strongest feature is that **ambiguous source data stays visible even after the warehouse builds successfully**.

No real retailer outcome, production deployment, causal uplift or realized recovery is claimed. The brief's delisting, pricing, forecast and funding questions are answered in the [decision memo](decision_memo.md) using a pre-registered [analysis plan](../analysis/PLAN.md); promotion profitability and out-of-stock cost remain open.
