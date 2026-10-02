{% docs __overview__ %}

# Bramblewood Retail Analytics Warehouse

An analytics engineering portfolio by **Aakshith Reddy**, built with **dbt, DuckDB, SQL and Python**.

**35 models · 14 staged sources · 13 enforced contracts · 100 dbt checks**

This synthetic case study turns disconnected retail extracts into auditable sales, inventory, forecasting, assortment and vendor-funding marts for a fictional 24-store grocer. All companies and transactions are fictional; dollar amounts are dataset findings, not real client outcomes.

## The business result

Approved promotions imply **$1,252,142.25 in estimated contractual funding**, compared with **$1,119,166.80 billed and collected**: an estimated **$132,975.45 billing gap**. Scan funding uses eligible signed net units; a planned display fee is counted once per approved display event. Display execution is not independently verified, ambiguous event assignments remain null, and cancelled-event claims are separate exceptions. This estimate is a review queue, not a confirmed receivable.

Open [the promotion funding mart](#!/model/model.bramblewood.mart_promotion_funding) to inspect its definitions, types, SQL and dependencies.

## Engineering decisions to review

- **Layer boundaries:** every raw table has staging coverage. Intermediate models reuse staging/intermediate models; marts use model references. A manifest-based CI check enforces these rules.
- **Typed interfaces:** staging normalizes dates and decimal amounts; facts, dimensions and business marts enforce declared dbt contracts.
- **Auditable cleaning:** 113 exact replay rows representing $8,489.86 are excluded, while malformed rows and original source-row lineage remain available. Signed returns are preserved.
- **Temporal correctness:** a reusable inclusive-period overlap test and documented latest-start cost precedence protect joins from fanout.
- **Independent controls:** accepted net sales of $21,886,423.88 reconcile to source CSVs using Python Decimal across all 2,427 store-weeks. CI also checks complete rebuild repeatability, macro edge cases, SQLFluff and pre-commit.

## Explore the project

| Review focus | Model |
|---|---|
| Sales grain and effective-dated enrichment | [Sales fact](#!/model/model.bramblewood.fct_sales) |
| Owed, billed, collected and exception flags | [Promotion funding](#!/model/model.bramblewood.mart_promotion_funding) |
| Chain-level forecast alignment | [Forecast accuracy](#!/model/model.bramblewood.mart_forecast_accuracy) |
| Inventory and sales coverage | [Availability](#!/model/model.bramblewood.mart_availability) |
| Assortment and shelf productivity | [Assortment productivity](#!/model/model.bramblewood.mart_assortment_productivity) |
| Rejected/replayed source rows | [Reconciliation audit](#!/model/model.bramblewood.audit_reconciliation) |

Each model page contains column definitions and compiled SQL. Use **View Lineage Graph** to follow its sources and consumers. Two exposures document the evidence pack and vendor-funding review.

[Source code and reproducible setup](https://github.com/Akshith597/bramblewood-analytics-engineering) · [Case study](https://github.com/Akshith597/bramblewood-analytics-engineering/blob/main/docs/case_study.md) · [Hosted quality gate](https://github.com/Akshith597/bramblewood-analytics-engineering/actions/workflows/ci.yml)

{% enddocs %}
