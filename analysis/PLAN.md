# Analysis plan — committed before any outcome was computed

This plan fixes the metric, comparison groups, windows, estimator, inference and decision rule for each of the
VP's five questions *before* looking at results, so the answer cannot drift toward a convenient one. Treatment
definitions below come only from structural tables (planograms, regular prices, store master), not from sales.
Any later deviation is logged in the memo's "Deviations from plan" section with a reason.

Inputs: dbt staging/intermediate models built from the raw extracts (`stg_*`, `int_sales_enriched`), never the
marts or `evidence/` files. Weeks are fiscal weeks (Sunday–Saturday). All bootstraps use fixed seeds.

## Ground truth

`data/SOURCE_README.md` states the generator and answer key are distributed separately; no public copy exists
(web and GitHub code search, 2026-10-14). Validation therefore relies on planted-effect recovery, held-out
backtests and a second implementation. If the answer key is obtained later, recovered estimates are compared to
it without re-tuning.

## Q1 — Delisting test (FY2025 W27)

- **Treatment:** stores 102, 106, 113, 116 moved from `PG-SS-L-2024` (151 SKUs) to `PG-SS-L-TEST25` (131 SKUs,
  same 410 facings) effective 2025-08-03 = FY2025 W27. 20 SKUs delisted.
- **Donor/control pool:** every store open for all 104 weeks except the treated stores, 112 (remodel
  2025-06-15 → 2025-08-02 overlaps the switch) and 124 (opened 2025-06-01). 18 stores.
- **Windows:** pre = FY2024 W1–FY2025 W26 (78 weeks); post = FY2025 W27–W52 (26 weeks).
- **Primary metric:** log weekly category gross profit before vendor funding, store-week.
  Secondary: log net sales, log units. Decomposition: lost sales on delisted SKUs vs gain on retained SKUs
  (transfer rate).
- **Estimator:** two-way fixed-effects DiD (store + week FE). Robustness: synthetic control (convex donor
  weights fitted on pre-period log GP, averaged over treated stores); large-format-only controls (101, 117).
- **Inference:** few clusters, so conventional cluster-robust SEs are reported but not relied on.
  Primary: wild cluster bootstrap by store (Webb weights, restricted null, 9,999 draws). Also randomization
  inference over all C(18,4) = 3,060 placebo assignments of the treatment to donor stores.
- **Checks:** event study in 4-week bins with a joint pre-period test; fake treatment dates FY2024 W27 and
  FY2025 W1 (pre-period data only); planted −2% / +2% effects must be recovered; minimum detectable effect
  = 2.8 × SD of the randomization distribution (80% power, 5% two-sided).
- **Decision rule:** recommend rollout to large-format stores if the GP point estimate ≥ 0 **and** the 90% CI
  lower bound > −1.0% (unmeasured operational savings assumed to cover at most a 1% GP loss). If the CI
  includes losses beyond −1%, do not roll out; if the MDE exceeds 3%, say the test is underpowered and recommend
  extending it. **Dollar figure:** effect × annual category GP of large-format stores (annualized, with CI).

## Q3 — Spring 2025 regular-price increases

- **Events:** Golden Ridge kettle (incl. item-master spelling variant "Golden Rdge"), 2025-04-06; Bramble Select
  (private label) tortilla, 2025-05-04. Increase size varies by price zone, giving dose variation.
- **Groups per event:** treated = SKUs whose regular price changed on that date; sisters = other SKUs in the same
  subcategory without a regular-price change in the window; controls = SKUs in subcategories with no
  regular-price change in the window.
- **Sample:** SKU-store-weeks with positive units, ±13 weeks around the event, excluding promoted weeks for the
  SKU in that store's zone and the 2 weeks after each promotion, and excluding stores 112 and 124.
- **Model:** log units = ε_own · (treated × post × Δlog p_zone) + ε_cross · (sister × post × Δlog p_zone)
  + SKU×store FE + store×week FE. ε_own is the own-price elasticity; ε_cross the cross-price elasticity.
- **Inference:** standard errors clustered by store (as specified) **and** wild cluster bootstrap by SKU, since
  price varies at SKU level; the more conservative interval is reported.
- **Checks:** event-study pre-trends; fake event date 26 weeks earlier; planted elasticity recovery;
  **backtest:** the kettle elasticity estimated from the Aug-2024 Crispwell Kettle increase must predict the
  Golden Ridge volume response within its 90% prediction interval.
- **Price sensitivity by subcategory / private label:** pooled FE model on all non-promoted regular-price
  variation (SKU×store, store×week, subcategory×fiscal-period FE) with subcategory and private-label
  interactions. Subcategories without usable price variation are reported as not identified.
- **Decision rule:** an increase was a good decision if the 13-week change in gross profit (own SKUs + sister
  SKUs, versus the no-increase counterfactual implied by the estimates) is positive with a 90% CI excluding 0.
  **Dollar figure:** annualized ΔGP with CI.

## Q4 — Forecast accuracy and bias

- **Metrics:** bias = Σ(forecast − actual)/Σactual and WAPE by subcategory, forecast horizon and promoted vs
  non-promoted weeks; MASE versus a seasonal-naive forecast (same fiscal week last year) and a lag-2 naive
  forecast (the actual available at run time). FY2025 is the evaluation year.
- **Dollar figure:** over-forecast units × unit cost (inventory carried) — an exposure measure, not a loss.
- **Out-of-stock cost:** a weekly on-hand snapshot cannot date a stock-out within the week. Planned method:
  lost units = baseline demand (same store-SKU, adjacent in-stock non-promoted weeks) minus actual, on
  zero-stock weeks, as a lower-bound range. Answered only if time allows after Q1 and Q3; otherwise marked
  not yet answered.

## Q2 — Promotion profitability

Planned method: incremental lift vs a store-SKU baseline from non-promoted weeks, net of cannibalisation
(sister SKUs, same subcategory) and a post-promotion dip (2 weeks), plus a per-event P&L including vendor
funding. Deferred behind Q1 and Q3; marked not yet answered if not completed.

## Q5 — Vendor funding

Owed vs billed vs collected from the promotion calendar and claims. Range: lower bound = scan-back on observed
scoped units only; upper bound = scan-back plus planned display fees for approved events. Not causal.

## Second implementation

Every headline estimate is computed twice: DuckDB SQL demeaning + a small exact solver, and an independent
pure-Python Frisch–Waugh–Lovell implementation. CI also runs R `fixest` on the exported panels; estimates must
agree within 1e-6 (point) and 1e-4 (SE).
