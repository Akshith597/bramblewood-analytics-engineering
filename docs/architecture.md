# Architecture and design decisions

## Data flow

```mermaid
flowchart LR
  A[POS CSV] --> R[(DuckDB raw schema)]
  B[Inventory CSV] --> R
  C[Merchandising workbook: 12 sheets] --> R
  R --> S[Staging: types, dates, keys, exceptions]
  S --> I[Intermediate keys, cost intervals, enriched sales and funding aggregates]
  S --> D[Conformed item, store, week, vendor dimensions]
  I --> F[Sales, inventory, claims facts]
  S --> F
  F --> M[Category, forecast, availability, assortment, funding marts]
  M --> E[SQL evidence exports]
  R --> Q[Raw hashes and row-level lineage]
  S --> T[dbt unit and data tests]
  F --> T
  M --> T
  T --> G[Local build / GitHub Actions quality gate]
```

## ADR 01 — DuckDB + dbt + a small Python loader

**Decision:** Python only reads formats and records provenance; SQL owns business transformation. dbt owns dependencies, tests and catalog generation. DuckDB provides a local analytical warehouse.

**Why:** The extracts are small enough for a laptop and have no live API, CDC stream or source modification timestamp. A reviewer can reproduce the warehouse without cloud credentials. Queryable raw data makes reconciliation inspectable.

**Tradeoff:** This is not a multi-user production service. There is no scheduler, secrets service, warehouse RBAC or production monitoring. A cloud migration would retain the model DAG while adapting SQL, ingestion and deployment.

## ADR 02 — Deterministic full rebuild

**Decision:** Replace raw tables transactionally, then build the entire bounded history. Source hashes identify exactly which bytes were loaded. A separate test hashes every ordered model before and after reload.

**Why:** Incremental append based on sales week would miss backdated costs, returns and corrected old extracts. The supplied files contain no reliable update timestamp.

**Tradeoff:** Work scales with historical volume. For larger sources, add file manifests plus batch IDs, source-updated timestamps, merge keys, affected-partition recomputation, and atomic promotion of a validated warehouse. Do not use the maximum sales date as a universal watermark.

**Revision — incremental `fct_sales`:** The largest fact is now incremental for the case the watermark concern does not cover: late or corrected POS rows in recent weeks. Each incremental run restates every fiscal week ending within `sales_restatement_lookback_days` (default 28) of the latest loaded week, using `delete+insert` on `week_key`, so rows that vanish from a corrected extract are removed rather than left behind. Backdated cost, price or master-data corrections still change weeks outside that window, so they require `dbt build --full-refresh`. The publication workflow always builds in a fresh workspace, so every published release is a full build. `verify_repeatability.py` runs the second build incrementally and requires every model to hash identically to the full build.

## ADR 03 — Keep grain explicit

**Decision:** Chain forecasts join chain SKU-week actuals. Claims aggregate to promotion before joining promotions. Inventory retains its own grain. Planograms and price/cost tables use tested temporal joins.

**Why:** Directly joining chain forecasts to store sales or claims to multiple eligible sales rows would inflate metrics. SQL measures should be safe before visualization.

**Tradeoff:** More models and explicit joins are easier to audit than one wide denormalized table with ambiguous measures.

## ADR 04 — Disclose cost ambiguity

**Decision:** Latest-start cost precedence, with the original end date and an adjustment flag retained. The source overlap is exposed in the evidence exports. Other period overlaps are build failures.

**Why:** A raw temporal join initially failed the quality gate. An explicit rule makes the warehouse usable while preserving uncertainty. The sensitivity export measures the exact financial difference from keeping the prior cost.

**Production next step:** Confirm the policy with merchandising or finance, attach a source-owner ticket, and version the correction. The current project has no such confirmation.

## ADR 05 — Nulls are information

**Decision:** Use a full outer sales/inventory mart and preserve missing sales on scheduled planogram rows. Approved promotions lacking claims become review flags.

**Why:** Missing extraction, genuine zero demand, unavailable stock and an unexecuted plan are different states. Defaulting them all to zero would encode an unsupported business claim.

## Failure and publication boundary

`scripts/run_all.py` exits nonzero on a failed ingestion, dbt build or independent reconciliation. Direct development builds may leave partially refreshed tables. The optional `scripts/publish_warehouse.py` workflow copies a batch and project into a temporary workspace, verifies source hashes and extraction age, runs the warehouse gates plus repeatability, then copies the database and evidence into a new release directory. Only after those steps succeed does `os.replace` atomically switch `current.json` on the same filesystem. Readers resolve the pointer once and open that release read-only; existing readers retain their previous release. Failed builds do not modify the published pointer.

Each delivery has a source manifest with hashes and actual extraction timestamps. Corrected historical files receive a new manifest and a full rebuild, avoiding date-watermark omissions. Missing, extra or changed source files reject the snapshot. A batch that expires during its build is rejected before publication. A `check` command evaluates the published extraction age without rebuilding and returns a nonzero exit status on failure, suitable for a scheduler to monitor. File modification time and successful ingestion do not establish source freshness.

This is a local publication demonstration, with a single-publisher lock and immutable-by-convention release files. It does not provide distributed locking, access controls, scheduled execution, alert routing, automatic retention or power-loss durability guarantees. Failed pointer swaps may leave an unreferenced release for inspection. A process crash may leave a lock; operators must verify no publisher is running before removing it. Consumers must use the pointer; directly querying the development database bypasses this publication boundary. See the [runbook](runbook.md#validated-batch-publication).

`scripts/verify_project.py` rejects raw-source reads outside staging, intermediate dependencies on marts, missing staging coverage, undocumented columns and unenforced mart contracts. The reusable overlap test, UPC macro and pinned dbt_utils package are checked alongside the dbt build.

The GitHub Actions workflow runs the complete build, independent reconciliation, repeatability, macro guards, SQLFluff and pre-commit. Deployment remains gated behind the warehouse build. Remote execution status is recorded separately in the repository and delivery evidence.

