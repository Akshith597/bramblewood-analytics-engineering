# Salty Snacks — FY2026 line-review decision memo

*To: VP Merchandising · Data: Bramblewood POS, inventory and merchandising extracts, FY2024–FY2025 (synthetic) ·
Generated from code by `analysis/build_memo.py`; every figure is a named query result in `analysis/results/`.
Method and decision rules were [committed before any outcome was computed](../analysis/PLAN.md).
The combined FY2026 plan built on these answers is [one page](fy2026_plan.md); estimates are frozen for the [answer-key scorecard](scorecard.md).*

| Question | Answer | Dollar figure (90% range) | Recommendation |
|---|---|---|---|
| 1. Delisting test | **Inconclusive** — the test cannot detect a GP change smaller than {d_mde}; but its transfer rate passes its placebo checks and prices a cut list | Test planogram: {d_dollar} per year if rolled out ({d_dollar_ci}). Cut list of {a_cuts} SKUs: {a_gp} per year ({a_gp_ci}) | Do not roll out the test planogram; cut the {a_cuts} SKUs that lose least GP per facing, planogram by planogram |
| 2. Promotions | **Break-even on vendor money owed; below zero on money actually collected** (both ranges span zero) — {q2_pos_before} of FY2025 events made gross profit before funding | {q2_net} net in FY2025 on funding owed ({q2_ci_model}); {q2_net_coll} on funding collected ({q2_coll_ci}); {q2_before} before funding | Cut or redesign promotions without a display; keep display events only where display execution is verified and the fee collected |
| 3. Price increases | **Not identified** from the data; break-even analysis favours Golden Ridge, tortilla is a coin flip | Golden Ridge {p_gr_gp} ({p_gr_gp_ci}); tortilla {p_bs_gp} ({p_bs_gp_ci}) — scenarios, not estimates | Keep Golden Ridge; tortilla: {e_tortilla_action} — a randomized test is worth less than it costs |
| 4. Forecast and in-stock | **Forecast over-forecasts by {f_bias}** ({f_bias_ci}); {ph_bias_restored} with censored demand restored. The over-forecast never reached store shelves | {f_cost} of planned units at cost, of which {ph_excess} became extra store stock; stock-outs {o_gp} ({o_ci}) | Correct the planning number for budgets, but do not re-tune store replenishment around it: at equal service it saves nothing ({s_saving}) |
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
differences cancel. *Update:* the inventory and value-of-information work below finds that test not worth its cost.

**Which SKUs earn their space.** The test did measure one thing cleanly: retained SKUs gained {d_transfer} of the
dollars the delisted SKUs lost, a rate that, unlike the GP effect, passes both fake-date checks ({a_tau_fake}) and
holds year over year ({a_tau_yoy}). Cutting SKU *i* therefore changes GP by −GP<sub>i</sub> + τ · sales<sub>i</sub> · margin of its
subcategory's retained SKUs. Ranked by GP per facing, within each planogram's fixed facings, among SKUs no bigger
than the ones the test cut, and cut only if the change is positive at the low end of τ's range: {a_cuts} SKUs
({a_by_pg}), {a_gp} a year ({a_gp_ci}). {a_overlap} of the test's {a_test_n} delisted SKUs fall in the large planogram's
bottom {a_test_n} by GP per facing. Full list: [FY2026 plan](fy2026_plan.md).

## 2. Promotions (FY2025 events)

Each promoted store-SKU-week is compared with an imputed baseline: what that SKU would have sold in that store
that week without the promotion, from a model fitted only on weeks with no promotion nearby. Promotions sold
{q2_lift} more units than baseline ({q2_incr_units} extra units across {q2_events} events), but the weeks after a
promotion fell {q2_dip1} and {q2_dip2} below baseline, and same-subcategory sister SKUs lost {q2_cann_units} units
(each promoted sister cuts a sister's sales by {q2_cann_range}, depending on subcategory).

| Mechanic | Events | Unit lift | GP before funding | Vendor funding owed | Net GP, funding owed (90% range with model error) | Net GP, funding collected | Decision rule |
|---|---|---|---|---|---|---|---|
{q2_cells}

Before funding, the promotions' net GP was **{q2_before}**: only {q2_pos_before} of events made money on their own. Vendor
funding owed under the deal terms ({q2_funding}, of which {q2_display_fees} display fees) turns that into
**{q2_net}** ({q2_ci}), with {q2_pos_net} of events net positive. Every display cell clears zero only because of
its display fee, and display execution cannot be verified from these extracts (question 5). By subcategory:
{q2_subcats}. FY2024 and FY2025 together: {q2_all_years} ({q2_all_years_ci}).

**On cash actually collected,** vendors paid {q2_collected} of the {q2_funding} owed for these events, so FY2025
promotions net **{q2_net_coll}** ({q2_coll_ci}); FY2024 and FY2025 together, {q2_all_years_coll}
({q2_all_years_coll_ci}). Whether promotions pay at all depends on collecting what the deals promise.

**Model error.** The ranges in the paragraph above reflect store-to-store sampling only. The table's ranges, and
the collected-funding ranges, also add two model errors: the baseline could be off by up to {q2_base_err} (the widest held-out bound below), and
estimating cannibalisation only from stores that differ within the same week moves net GP by {q2_spec_shift} in
total. Together they widen the FY2025 total to {q2_ci_model}. Every keep or cut decision in the table holds under
the wider ranges and on collected funding.

Checks: in the two weeks before each promotion, held out of the fit, sales were {q2_pre} from the baseline;
fake promotions placed eight weeks earlier were {q2_placebo} from it; a planted cannibalisation slope of
{q2_planted} was recovered exactly. **Next:** stop non-display TPR, BOGO and multi-buy events or renegotiate their
funding; audit display execution before relying on display fees; run any promotion you keep with a randomised
holdout of stores.

## 3. Spring 2025 regular-price increases

| | Golden Ridge kettle | Bramble Select tortilla (private label) |
|---|---|---|
| Increase / margin before | {p_gr_inc} / {p_gr_margin} | {p_bs_inc} / {p_bs_margin} |
| Break-even own-price elasticity | **{p_gr_be}** | **{p_bs_be}** |
| Pooled subcategory elasticity (unvalidated) | {p_gr_pooled} ({p_gr_pooled_ci}) | {p_bs_pooled} ({p_bs_pooled_ci}) |

An increase loses gross profit only if shoppers are more price-sensitive than the break-even elasticity — pure
arithmetic on price and cost. Neither event-level design passed its own checks: the planned comparison
failed pre-trend (p {p_gr_pretrend}), fake-date and backtest checks, and an exploratory within-SKU cross-zone
design failed the backtest (Golden Ridge) or pre-trends (tortilla). The pooled model across all
{p_pooled_n} non-promoted SKU-store-weeks suggests kettle is inelastic ({p_gr_pooled}) — far from
{p_gr_be}, so Golden Ridge very likely paid off — while private-label tortilla sits near its break-even.
By subcategory: {p_subcats}. Private label is more price-sensitive by {p_pl_shift} elasticity points (shift {p_pl_shift_ci}), identified
only from Bramble Select changes. **Next:** the tortilla decision is worth {e_tortilla_evpi} even with perfect
information, less than a 13-week store test costs; take the action with the higher expected GP ({e_tortilla_action}).

## 4. Forecast and in-stock

FY2025 forecast bias is **{f_bias}** (SKU-bootstrap {f_bias_ci}); WAPE {f_wape}. Bias is {f_bias_promo} in
promoted weeks versus {f_bias_nonpromo} otherwise. The forecast still beats naive benchmarks (MASE {f_mase_lag2}
vs the lag-2 actual; {f_mase_seasonal} vs last year), so it should be corrected, not replaced: per-subcategory
factors learned on FY2024 cut FY2025 bias from {f_bias} to {f_bias_after} and WAPE from {f_wape} to
{f_wape_after}.

**Did the over-forecast become stock? No.** Receipts and on-hand obey the stock-flow identity on {ph_exact} of
store-SKU-weeks (shrink {ph_shrink} of receipts). In FY2025 stores received {ph_receipts_over} more units than they
sold while the forecast was {f_bias} over: receipts follow sales, not the forecast — weekly receipts move
{ph_coef_same} units per unit sold the same week and {ph_coef_prev} per unit sold the week before, the signature of
direct-store delivery. Average store stock at cost in comparable stores rose {ph_excess}, {ph_excess_share} of the
{f_cost} the memo first quoted, and year-end stock fell {ph_yearend}. Distribution-centre stock is not in the
extracts, so excess held upstream cannot be measured. Refit on weeks with no stock-out, bias is {ph_bias_instock}
({ph_bias_instock_ci}) — higher, not lower, because stock-outs happen in demand spikes the forecast under-calls
({ph_bias_stockout} on those weeks); with their censored demand restored instead, bias is {ph_bias_restored}
({ph_bias_restored_ci}).

**Is the correction worth it? Judged on stock, not WAPE: no.** Replaying FY2025 store by store with
forecast-driven, case-pack orders and a safety stock sized on each forecast's own errors, each forecast at its
best safety factor costs about the same (lost GP + carrying cost at {s_carry}: raw {s_raw_cost}, corrected
{s_corr_cost}); to reach {s_fill_target} fill the corrected forecast needs {s_stock_corr} of stock against
{s_stock_raw}. The bias was acting as safety stock; removing it only moves that stock into the buffer. Both
forecast-driven policies need far more stock ({s_raw_stock} at best) than stores actually held ({s_actual_stock}
at {s_actual_fill} fill), so the current delivery process should not be replaced by forecast-driven ordering.

**Out-of-stock cost (exploratory).** On the {o_weeks} non-promoted FY2025 weeks that ended with zero stock, the
store sold everything it had, so demand was at least what it sold. Using the promotion baseline model and the
spread of its in-stock errors, the expected demand above that floor is {o_units} units, or **{o_gp}** of gross
profit ({o_ci}; {o_share} of category GP), plus {o_promo_gp} in promoted weeks. That is below the {o_threshold}
threshold for prioritising replenishment work. Treat it as a floor, not a measurement: the planned
adjacent-week method gives {o_prereg_gp} (stock-outs happen in demand spikes, so neighbouring weeks understate
demand); the model predicts {o_calib_pred} stock-outs against {o_calib_obs} observed, so its demand tail is too
thin; and a planted test recovered {o_planted} of known losses when the floor was tied to the week's own sales,
but {o_posthoc} under realistic censoring (post-hoc). **Next:** capture a daily stock-out flag or time of
stock-out; the weekly snapshot cannot measure this well.

## 5. Vendor funding

On {v_events} approved events, scan-back owed on observed units exceeds scan-back billed by **{v_low}**;
if every planned display ran, the gap rises to **{v_high}**. {v_noclaim} approved events have no claim at all.
Everything billed on approved events was collected; {v_cancelled} was billed on cancelled events and not
collected.

## How the results were checked

- **Ground truth:** the answer key is distributed separately; a [request to the dataset's author](answer_key_request.md) is drafted.
  Every estimate and interval was frozen in the tagged commit `estimates-frozen-v1` before the key was opened;
  the [scorecard](scorecard.md) compares them to it without re-tuning.
- **Second implementation:** {x_checks} headline coefficients and clustered SEs re-estimated by an independent
  pure-Python solver ({x_status}); CI repeats them in R `fixest`.
- **Planted effects:** known effects added to the real data were recovered exactly (delist ±2%, elasticity −1.5).
- **Deviations from plan:** (1) delist GP indexed to each store's pre-period mean, because one comparison
  store-week had negative GP (log version: {d_log}); (2) the cross-zone price design and (3) the year-over-year
  delist adjustment were added after diagnostics and are labelled exploratory; (4) promotions and out-of-stock
  cost were specified in a later plan addendum, written after unit-level aggregates (not dollars) had been seen;
  the addendum lists what was seen; (5) the out-of-stock estimator was switched to censored demand after the
  planned one came out negative, so that answer is exploratory, and a realistic planted check was added
  post-hoc. Data fix: one promotion with swapped start and end dates in the source was corrected, confirmed by
  POS discounts. Added in the FY2026 round, after the results above were known: (6) the cut list restricts
  candidates to SKUs no bigger than those the test cut, after a first unrestricted ranking put best-sellers at the
  top; (7) fake-date and same-season checks on τ; (8) the inventory simulation's safety stock was changed from a
  fixed percentage of forecast to a multiple of each forecast's own error, after the first version could not match
  the observed stock-out rate; (9) store-bootstrap ranges for promotion lift and the post-promotion dip, for the
  scorecard; (10) restored-demand bias was made primary after the requested in-stock refit was seen to select on
  low demand. (11) the frozen elasticities are labelled as the brands' own-price elasticity, with private label as a
  separate shift; (12) after review of the promotions result, net GP on funding collected and a model-error band
  (held-out baseline error plus an alternative cannibalisation specification) were added; the planned ranges and
  decisions are still reported and did not change. All are logged in [the deviation log](../analysis/scorecard/DEVIATIONS.md).
