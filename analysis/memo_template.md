# Salty Snacks — FY2026 line-review decision memo

*To: VP Merchandising · Data: Bramblewood POS, inventory and merchandising extracts, FY2024–FY2025 (synthetic) ·
Generated from code by `analysis/build_memo.py`; every figure is a named query result in `analysis/results/`.
Method and decision rules were [committed before any outcome was computed](../analysis/PLAN.md).*

| Question | Answer | Dollar figure (90% range) | Recommendation |
|---|---|---|---|
| 1. Delisting test | **Inconclusive** — the test cannot detect a GP change smaller than {d_mde} | {d_dollar} per year if rolled out to the other large stores ({d_dollar_ci}) | Do not roll out on this evidence; rerun as a randomized, full-year test |
| 2. Promotions | **Not yet answered** | — | See below |
| 3. Price increases | **Not identified** from the data; break-even analysis favours Golden Ridge, tortilla is a coin flip | Golden Ridge {p_gr_gp} ({p_gr_gp_ci}); tortilla {p_bs_gp} ({p_bs_gp_ci}) — scenarios, not estimates | Keep Golden Ridge; test the tortilla price in a randomized subset of stores |
| 4. Forecast and in-stock | **Forecast over-forecasts by {f_bias}** ({f_bias_ci}); out-of-stock cost not yet answered | {f_cost} of planned inventory against demand that did not occur in FY2025 | Apply per-subcategory bias correction now; it cut FY2025 bias to {f_bias_after} out of sample |
| 5. Vendor funding | **Under-billed** on approved promotions | {v_low} to {v_high} | Bill the scan-back shortfall now; verify display execution before billing displays |

## 1. Delisting test (stores 102, 106, 113, 116 from FY2025 W27)

Category gross profit in the test stores moved **{d_effect}** relative to {d_donors} comparison stores (90% CI
{d_ci}; wild cluster bootstrap p = {d_p}; randomization p = {d_ri_p}). Units fell **{d_units}** ({d_units_ci},
p = {d_units_p}) while net sales were flat ({d_sales}), consistent with shoppers switching to retained items:
retained SKUs gained **{d_transfer}** of the dollars the delisted SKUs lost ({d_transfer_ci}).

Why this is not a rollout: with four test stores the smallest GP change detectable 80% of the time is {d_mde};
power against a real 2% loss is only {d_power2}. A fake treatment date one year earlier (FY2024 W27) shows a
{d_fake24} "effect" (p = {d_fake24_p}), so large stores have their own second-half seasonality that this design
does not remove; a year-over-year adjustment would put the effect near {d_yoy} (exploratory). Synthetic-control
and large-store-only comparisons agree in direction but not magnitude ({d_sc}; {d_large}).
**Next:** randomize the planogram across matched large-store pairs and run it for a full year so seasonality
differences cancel.

## 2. Promotions — not yet answered

Deferred to protect depth on questions 1 and 3. Planned method: lift against a non-promoted store-SKU baseline,
net of cannibalisation (same subcategory) and a two-week post-promotion dip, with a per-event P&L including
vendor funding.

## 3. Spring 2025 regular-price increases

| | Golden Ridge kettle | Bramble Select tortilla (private label) |
|---|---|---|
| Increase / margin before | {p_gr_inc} / {p_gr_margin} | {p_bs_inc} / {p_bs_margin} |
| Break-even own-price elasticity | **{p_gr_be}** | **{p_bs_be}** |
| Pooled subcategory elasticity (unvalidated) | {p_gr_pooled} ({p_gr_pooled_ci}) | {p_bs_pooled} ({p_bs_pooled_ci}) |

An increase loses gross profit only if shoppers are more price-sensitive than the break-even elasticity — pure
arithmetic on price and cost. Neither event-level design passed its own checks: the pre-registered comparison
failed pre-trend (p {p_gr_pretrend}), fake-date and backtest checks, and an exploratory within-SKU cross-zone
design failed the backtest (Golden Ridge) or pre-trends (tortilla). The pooled model across all
{p_pooled_n} non-promoted SKU-store-weeks suggests kettle is inelastic ({p_gr_pooled}) — far from
{p_gr_be}, so Golden Ridge very likely paid off — while private-label tortilla sits near its break-even.
By subcategory: {p_subcats}. Private label is more price-sensitive by {p_pl_shift} elasticity points (shift {p_pl_shift_ci}), identified
only from Bramble Select changes. **Next:** test the tortilla price in randomly chosen stores for 13 weeks.

## 4. Forecast and in-stock

FY2025 forecast bias is **{f_bias}** (SKU-bootstrap {f_bias_ci}); WAPE {f_wape}. Bias is {f_bias_promo} in
promoted weeks versus {f_bias_nonpromo} otherwise. The forecast still beats naive benchmarks (MASE {f_mase_lag2}
vs the lag-2 actual; {f_mase_seasonal} vs last year), so it should be corrected, not replaced: per-subcategory
factors learned on FY2024 cut FY2025 bias from {f_bias} to {f_bias_after} and WAPE from {f_wape} to
{f_wape_after}. **Out-of-stock cost — not yet answered:** a weekly on-hand snapshot cannot date a stock-out;
the planned lower-bound method is in the analysis plan.

## 5. Vendor funding

On {v_events} approved events, scan-back owed on observed units exceeds scan-back billed by **{v_low}**;
if every planned display ran, the gap rises to **{v_high}**. {v_noclaim} approved events have no claim at all.
Everything billed on approved events was collected; {v_cancelled} was billed on cancelled events and not
collected.

## How the results were checked

- **Ground truth:** the dataset's answer key is distributed separately and is not public, so it was not used.
- **Second implementation:** {x_checks} headline coefficients and clustered SEs re-estimated by an independent
  pure-Python solver ({x_status}); CI repeats them in R `fixest`.
- **Planted effects:** known effects added to the real data were recovered exactly (delist ±2%, elasticity −1.5).
- **Deviations from plan:** (1) delist GP indexed to each store's pre-period mean, because one comparison
  store-week had negative GP (log version: {d_log}); (2) the cross-zone price design and (3) the year-over-year
  delist adjustment were added after diagnostics and are labelled exploratory; (4) promotions and out-of-stock
  cost deferred.
