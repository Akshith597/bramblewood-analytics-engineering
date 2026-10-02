# Data contracts and metric definitions

This project models a **synthetic historical extract**, not a live retailer. Sales cover February 4, 2024–January 31, 2026 (FY2024–FY2025). Claim submissions extend to April 13, 2026. The extract has no collection timestamps or documented snapshot timestamp, so collections cannot be reconstructed as of fiscal year-end.

## Model contracts

| Model | Grain / key | Contract and use |
|---|---|---|
| `stg_pos_audit` | Original POS row / `_source_row` | Preserve original fields, typed fields, replay rank and disposition. No silent drops. |
| `int_pos_accepted` | Store × UPC × week ending | Accepted rows only; dates normalized; UPC is a 12-character string. Signed returns retained. |
| `stg_inventory` | Store × SKU × fiscal week | Typed weekly snapshot; `fiscal_week` renamed `week_key`. |
| `stg_item_cost` | SKU × effective start | Typed source cost periods with DATE boundaries and DECIMAL unit cost. |
| `int_item_cost_intervals` | SKU × effective start | Latest-start precedence with original end date and adjustment flag retained. |
| `dim_item` | SKU / `sku_id` | Current item-master attributes. UPC is unique. Replacement SKU stays distinct. |
| `dim_store` | Store / `store_id` | Current store attributes; open and remodel dates retained. |
| `dim_week` | Fiscal week / `week_key` | Authoritative fiscal calendar; Sunday–Saturday weeks. |
| `dim_vendor` | Vendor / `vendor_id` | Current vendor attributes and payment terms. |
| `int_sales_keys` | Accepted POS row | Left joins to staged masters resolve SKU and fiscal week without hiding unmatched records. |
| `int_sales_enriched` | Store × SKU × fiscal week | Reusable effective-cost/price enrichment upstream of all marts. |
| `fct_sales` | Store × SKU × fiscal week / `sales_key` | One source row with one effective cost and one zone price. Stable MD5 key is an identifier, not a security control. |
| `fct_inventory` | Store × SKU × fiscal week / `inventory_key` | Observed receipts and Saturday stock, including explicit zero-stock flags. |
| `fct_vendor_claims` | Claim / `claim_id` | Billed and collected amounts; multiple claims per promotion remain possible. |
| `int_promotion_sales` | Promotion × sales key | Approved event eligibility by SKU, inclusive dates and store zone. Explicit ambiguity count. |
| `mart_category_weekly` | Subcategory × fiscal week | Additive sales, units, estimated gross profit and discounts. |
| `mart_availability` | Union of sales and inventory store × SKU × week keys | Full outer join and presence flags prevent missing observations becoming zero. |
| `mart_forecast_accuracy` | Forecast SKU × target week | Actuals aggregated to chain grain before joining. Run week and forecast lead retained. |
| `mart_promotion_funding` | Promotion | Estimated owed scan/display funding versus actual billed and collected; cancellation and execution caveats retained. |
| `mart_assortment_productivity` | Scheduled store × SKU × week | Effective store planogram and item facings, with left-joined observed sales. |
| `audit_reconciliation` | POS disposition | Row, unit and money control totals. |

Dimensions are Type 1 views of the supplied master data, materialized as tables. This is **not** a reconstructed Type 2 history of item or store attributes. Cost, price and planogram tables carry their own effective periods.

All 14 raw sources have one direct staging projection. Staging owns DATE, INTEGER and DECIMAL casts, UPC normalization, and canonical subcategory labels. Intermediates depend only on staged or intermediate models. Facts and marts use `ref()` exclusively. `scripts/verify_project.py` checks these boundaries against the parsed dbt manifest.

Every one of the 13 mart-layer models has `contract.enforced: true` and explicit types for every output column in `models/marts/schema.yml`. Key/required fact columns also have physical `not_null` constraints and relational data tests. All 370 modeled columns have types and descriptions available in dbt docs; the markdown complements those machine-readable definitions.

## Semantic contracts

| Metric | Definition | Important boundary |
|---|---|---|
| Net sales | `SUM(net_sales)` | Dollars after promotional discounts; returns remain signed. |
| Net units | `SUM(units)` | Sales minus returns. Not positive shopper demand. |
| Estimated COGS | `SUM(units × effective unit_cost)` | Vendor list cost at week ending; not landed accounting cost. |
| Gross profit before funding | `SUM(net_sales - estimated_cogs)` | Excludes vendor funding, shrink, freight and operating costs. |
| Gross margin rate | `SUM(gross_profit_before_funding) / SUM(net_sales)` | Ratio of sums; never average row margins. |
| Forecast WAPE | `SUM(ABS(forecast_units - actual_units)) / SUM(ABS(actual_units))` | Matched SKU-weeks only; null when denominator is zero. Report coverage and lead horizon. |
| Forecast bias | `SUM(forecast_units - actual_units) / SUM(ABS(actual_units))` | Positive means overforecast. Actual sales can be constrained by stock. |
| Zero-stock snapshot share | Zero `on_hand_eow` rows / observed inventory rows | Saturday snapshot; not weekly out-of-stock rate or lost sales. |
| Uncollected billed amount | `SUM(total_billed - amount_collected)` | Extract status, not confirmed overdue debt or recoverable cash. |
| Approved event without claim | Approved calendar event with no claim row | Review queue; not proof of missing funding or execution. |
| Estimated owed funding | Observed unambiguous net promo units × contractual scan rate, plus flat display fee once per approved display event | Calendar-based execution assumption; not confirmed receivables. Cancelled events owe zero; ambiguous assignment makes scan/total owed null. |
| Estimated billing gap | Estimated owed minus actual billed | Signed value exposes potential underbilling and overbilling without netting away cancelled-event exceptions. |
| Estimated collection gap | Estimated owed minus collected | Estimated billing gap plus actual billed-minus-collected balance. |
| Sales per scheduled facing | Observed sales / scheduled facings | Planogram allocation, not observed shelf execution. For aggregates, use ratio of sums and disclose missing sales. |

## Source normalization and exception policy

1. A repeated CSV header is classified and excluded from sales, but retained in the audit model.
2. Only **byte-equivalent field tuples** in the same POS extract are replay-deduplicated. The earliest source row wins. Normalized-key conflicts fail tests; they are not summed or silently overwritten.
3. Eleven-digit UPCs are left-padded to 12 digits; other lengths or nonnumeric keys fail the invalid-record gate. SKU replacements are not merged automatically.
4. Dates accept explicit `YYYY-MM-DD` and US `MM/DD/YYYY` formats. Locale inference is not used.
5. Monetary POS fields use `DECIMAL(18,2)`. The original fields remain available in `raw` and the audit model.
6. For overlapping costs, the later `effective_start` supersedes the previous record. The prior end is shortened to the day before the next start. Same-start conflicts fail. This is a disclosed modeling assumption, not a correction confirmed by the source owner.
7. Other temporal overlaps fail the build. No general “take any matching row” logic is permitted.
8. Source cost and price dates are inclusive. Weekly cost and price are evaluated at Saturday; within-week changes would require daily data or a weighting policy.
9. No eligible observed sales means zero *observed scan units* in the funding estimate; it does not prove zero demand. Planned approved display fees remain in the estimate and are flagged `no_observed_sales` or `no_discount_execution_signal` for confirmation. The funding sensitivity export separates these assumptions.
10. `Tortilla chips ` in the item master is normalized to `Tortilla Chips`. Eight canonical subcategories are enforced with accepted-values tests.

## Data not sufficient to establish

- A causal promotion ROI, price elasticity, or delisting effect. Seasonality, stores, controls, cannibalization, post-event demand and execution require a separate study.
- Stockout duration, lost demand or lost-sales dollars from a single weekly on-hand observation.
- True vendor funding entitlement from planned promotions alone.
- Historical SCD attributes or collection balances at a past date from current extracts.

The dataset's original analyst brief is preserved in `data/SOURCE_README.md` as background. This project's delivered scope is the tested analytics engineering foundation and descriptive business checks; it does not claim to complete all five causal analyst studies.
