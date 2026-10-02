# Interview and application pack

## Project title

**Bramblewood Retail Analytics Warehouse — dbt, DuckDB, SQL & Python**

## Resume bullets

Use these after running and understanding the project yourself. Keep it labeled as a synthetic portfolio project, not an employer engagement.

- Built a reproducible dbt/DuckDB retail warehouse with 35 models and 13 enforced contracts spanning sales, inventory, forecasts, assortment and vendor funding across 24 fictional stores and 104 fiscal weeks.
- Implemented 96 SQL data tests, 4 dbt unit tests and 4 independent macro guards, with source reconciliation, deterministic rebuild checks, SQLFluff and CI for 273,262 accepted POS records.
- Resolved replayed records, inconsistent UPC/date formats and effective-dated cost overlaps; prevented $8,489.86 of duplicate revenue in the synthetic extract while retaining row-level audit lineage.
- Modeled estimated funding owed versus billed and collected, identifying a $132,975.45 synthetic approved-event billing gap with execution assumptions and cancellation exceptions documented.

## 60-second introduction

“I built an analytics engineering portfolio project around a fictional grocer with disconnected POS, inventory and merchandising extracts. The core problem was making the business metrics trustworthy. I used Python to land the files, DuckDB as the local warehouse, and dbt to model and test the transformations. The sales fact has a clear store-SKU-week grain, cost and price joins are effective-dated, and every cleaning decision is traceable. The quality gates caught a cost overlap that would have multiplied sales rows. I documented a precedence policy and quantified its margin sensitivity. The deliverable is a reproducible warehouse with business marts, tests, lineage and evidence—not a claim of real client savings.”

## Five-minute demo

1. **Problem and architecture (45 seconds):** Open README and `docs/architecture.md`. Explain why raw, staging and marts are separated.
2. **A messy record (60 seconds):** Open `stg_pos_audit.sql` and its unit fixtures. Demonstrate legacy dates, UPC normalization, duplicate replay handling and retained returns.
3. **The dangerous join (60 seconds):** Open `fct_sales.sql`, `stg_item_cost.sql` and `evidence/cost_policy_sensitivity.csv`. Explain the initial overlap failure and the $29.12 sensitivity.
4. **Trust evidence (60 seconds):** Open the dbt build receipt, independent reconciliation and repeatability output. Explain why a row-count test alone is insufficient.
5. **Business usability (45 seconds):** Open the forecast and funding marts. Explain why planned promotion eligibility is not realized lift and why a weekly zero-stock snapshot is not lost sales.
6. **Production tradeoffs (30 seconds):** Explain full refresh, lack of source update timestamps, and atomic publication as the next architecture step.

## Questions worth practicing

**Why not incremental models?** The bounded extract has no reliable modification timestamp, and effective-cost changes can restate older weeks. Full rebuild is intentional here. At larger scale I would add ingestion batches and change metadata, determine affected keys/partitions, and compare incremental output with a full-refresh reference.

**How do you prevent double counting?** I define grain before joining. I aggregate forecasts to SKU-week actuals and claims to promotions, test effective-period uniqueness, and assert both counts and money through the sales pipeline.

**Is your cost fix correct?** It is an explicit latest-start assumption. The source does not confirm it. I preserve the original periods, expose the exception, measure the dollar sensitivity and would ask the data owner to resolve it in production.

**Why not remove negative sales?** They are net returns under the supplied dictionary. Dropping them overstates sales; the unit fixtures ensure they survive normalization.

**Does a green build prove business truth?** No. It proves the specified contracts and examples hold for the supplied inputs. The source could still omit transactions or contain a plausible but wrong price. Source-owner reconciliation and better source metadata remain necessary.

**Can you claim funding recovery?** No. The mart measures billed minus collected in the extract and flags calendar events without claims. Recovery requires execution evidence, claim validation and collection activity.

**Did you run this in production?** It is a synthetic portfolio project. GitHub Actions runs the reproducible warehouse build, SQLFluff, pre-commit, macro guards and reconciliations; the hosted run receipt is separate from a real production retailer deployment.

## Personalize before applying

Add your name and repository URL to your resume, run the pipeline, inspect the SQL, and record a short demo in your own words. Add one extension you can defend—for example, tested incremental restatement with a synthetic change fixture. Describe tool assistance honestly if asked; understanding the decisions matters more than presenting generated code as unaided work.
