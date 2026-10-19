# Salty Snacks — FY2026 line-review decision memo

*To: VP Merchandising · Data: Bramblewood POS, inventory and merchandising extracts, FY2024–FY2025 (synthetic) ·
Generated from code by `analysis/build_memo.py`; every figure is a named query result in `analysis/results/`.
Method and decision rules were [committed before any outcome was computed](../analysis/PLAN.md).
The combined FY2026 plan built on these answers is [one page](fy2026_plan.md); estimates are frozen for the [answer-key scorecard](scorecard.md).*

| Question | Answer | Dollar figure (90% range) | Recommendation |
|---|---|---|---|
| 1. Delisting test | **Inconclusive** — the test cannot detect a GP change smaller than 4.3%; but its transfer rate passes its placebo checks and prices a cut list | Test planogram: +$15.3K per year if rolled out (−$19.7K to +$50.3K). Cut list of 11 SKUs: +$49.2K per year (+$14.8K to +$83.6K) | Do not roll out the test planogram; cut the 11 SKUs that lose least GP per facing, planogram by planogram |
| 2. Promotions | **Break-even on vendor money owed; below zero on money actually collected** (both ranges span zero) — 1% of FY2025 events made gross profit before funding | +$13.4K net in FY2025 on funding owed (−$60.9K to +$93.5K); −$47.7K on funding collected (−$122.1K to +$32.4K); −$661.0K before funding | Cut or redesign promotions without a display; keep display events only where display execution is verified and the fee collected |
| 3. Price increases | **Not identified** from the data; break-even analysis favours Golden Ridge, tortilla is a coin flip | Golden Ridge +$52.9K (+$49.4K to +$56.3K); tortilla −$1.2K (−$11.4K to +$8.3K) — scenarios, not estimates | Keep Golden Ridge; tortilla: roll the price back — a randomized test is worth less than it costs |
| 4. Forecast and in-stock | **Forecast over-forecasts by +13.4%** (+11.8% to +15.0%); +12.5% with censored demand restored. The over-forecast never reached store shelves | $1.05M of planned units at cost, of which $19.4K became extra store stock; stock-outs $26.4K ($20.7K to $31.8K) | Correct the planning number for budgets, but do not re-tune store replenishment around it: at equal service it saves nothing (−$941.32) |
| 5. Vendor funding | **Under-billed** on approved promotions | $65.5K to $133.0K | Bill the scan-back shortfall now; verify display execution before billing displays |

## 1. Delisting test (stores 102, 106, 113, 116 from FY2025 W27)

Category gross profit in the test stores moved **+1.9%** relative to 18 comparison stores (90% CI
−2.5% to +6.4%; wild cluster bootstrap p = 0.417; randomization p = 0.220). Units fell **1.4%** (−2.0% to −0.7%,
p = 0.017) while net sales were flat (−0.7%), consistent with shoppers switching to retained items:
retained SKUs gained **124%** of the dollars the delisted SKUs lost (81% to 166%).

Why this is not a rollout: with four test stores the smallest GP change detectable 80% of the time is 4.3%;
power against a real 2% loss is only 28%. A fake treatment date one year earlier (FY2024 W27) shows a
+2.4% "effect" (p = 0.021), so large stores have their own second-half seasonality that this design
does not remove; a year-over-year adjustment would put the effect near −0.5% (exploratory). Synthetic-control
and large-store-only comparisons agree in direction but not magnitude (synthetic control +0.5%; large-store controls only +0.3%).
**Next:** randomize the planogram across matched large-store pairs and run it for a full year so seasonality
differences cancel. *Update:* the inventory and value-of-information work below finds that test not worth its cost.

**Which SKUs earn their space.** The test did measure one thing cleanly: retained SKUs gained 124% of the
dollars the delisted SKUs lost, a rate that, unlike the GP effect, passes both fake-date checks (−0.18, −0.07 at the fake dates) and
holds year over year (1.30, 0.86 to 1.75). Cutting SKU *i* therefore changes GP by −GP<sub>i</sub> + τ · sales<sub>i</sub> · margin of its
subcategory's retained SKUs. Ranked by GP per facing, within each planogram's fixed facings, among SKUs no bigger
than the ones the test cut, and cut only if the change is positive at the low end of τ's range: 11 SKUs
(7 in the large planogram, 8 in the medium planogram, 7 in the small planogram), +$49.2K a year (+$14.8K to +$83.6K). 10 of the test's 20 delisted SKUs fall in the large planogram's
bottom 20 by GP per facing. Full list: [FY2026 plan](fy2026_plan.md).

## 2. Promotions (FY2025 events)

Each promoted store-SKU-week is compared with an imputed baseline: what that SKU would have sold in that store
that week without the promotion, from a model fitted only on weeks with no promotion nearby. Promotions sold
189% more units than baseline (391,499 extra units across 397 events), but the weeks after a
promotion fell 27% and 13% below baseline, and same-subcategory sister SKUs lost 136,498 units
(each promoted sister cuts a sister's sales by 2% to 12%, depending on subcategory).

| Mechanic | Events | Unit lift | GP before funding | Vendor funding owed | Net GP, funding owed (90% range with model error) | Net GP, funding collected | Decision rule |
|---|---|---|---|---|---|---|---|
| BOGO | 21 | +382% | −$77.4K | +$54.5K | **−$22.9K** (−$25.8K to −$20.1K) | −$24.4K (−$27.4K to −$21.6K) | Cut or redesign |
| BOGO + display | 26 | +634% | −$149.4K | +$189.2K | **+$39.8K** (+$30.3K to +$49.3K) | +$23.6K (+$14.1K to +$33.1K) | Keep (funding-dependent) |
| Multi-buy | 52 | +94% | −$50.4K | +$19.5K | **−$30.9K** (−$43.4K to −$18.5K) | −$32.7K (−$45.1K to −$20.2K) | Cut or redesign |
| Multi-buy + display | 25 | +179% | −$28.0K | +$47.6K | **+$19.6K** (+$13.8K to +$26.1K) | +$15.0K (+$9.3K to +$21.5K) | Keep (funding-dependent) |
| TPR | 155 | +117% | −$216.6K | +$108.0K | **−$108.6K** (−$131.7K to −$85.4K) | −$115.0K (−$138.0K to −$91.7K) | Cut or redesign |
| TPR + display | 118 | +204% | −$139.1K | +$255.6K | **+$116.5K** (+$84.4K to +$151.5K) | +$85.7K (+$53.5K to +$120.6K) | Keep (funding-dependent) |

Before funding, the promotions' net GP was **−$661.0K**: only 1% of events made money on their own. Vendor
funding owed under the deal terms ($674.4K, of which $232.0K display fees) turns that into
**+$13.4K** (−$14.4K to +$47.0K), with 36% of events net positive. Every display cell clears zero only because of
its display fee, and display execution cannot be verified from these extracts (question 5). By subcategory:
Potato Chips +$31.0K; Tortilla Chips +$8.7K; Cheese Snacks +$5.6K; Kettle Chips +$3.1K; Popcorn −$302.13; Trail Mix −$1.9K; Pretzels −$9.4K; Nuts −$23.4K. FY2024 and FY2025 together: +$66.7K (+$15.1K to +$129.1K).

**On cash actually collected,** vendors paid $613.2K of the $674.4K owed for these events, so FY2025
promotions net **−$47.7K** (−$122.1K to +$32.4K); FY2024 and FY2025 together, −$66.5K
(−$204.9K to +$82.8K). Whether promotions pay at all depends on collecting what the deals promise.

**Model error.** The ranges in the paragraph above reflect store-to-store sampling only. The table's ranges, and
the collected-funding ranges, also add two model errors: the baseline could be off by up to 1.1% (the widest held-out bound below), and
estimating cannibalisation only from stores that differ within the same week moves net GP by +$36.4K in
total. Together they widen the FY2025 total to −$60.9K to +$93.5K. Every keep or cut decision in the table holds under
the wider ranges and on collected funding.

Checks: in the two weeks before each promotion, held out of the fit, sales were −0.6% from the baseline;
fake promotions placed eight weeks earlier were −0.1% from it; a planted cannibalisation slope of
−0.05 was recovered exactly. **Next:** stop non-display TPR, BOGO and multi-buy events or renegotiate their
funding; audit display execution before relying on display fees; run any promotion you keep with a randomised
holdout of stores.

## 3. Spring 2025 regular-price increases

| | Golden Ridge kettle | Bramble Select tortilla (private label) |
|---|---|---|
| Increase / margin before | +8.2% / 33.4% | +9.9% / 43.3% |
| Break-even own-price elasticity | **−2.78** | **−2.18** |
| Pooled subcategory elasticity (unvalidated) | −0.52 (−0.73 to −0.30) | −2.44 (−3.05 to −1.84) |

An increase loses gross profit only if shoppers are more price-sensitive than the break-even elasticity — pure
arithmetic on price and cost. Neither event-level design passed its own checks: the planned comparison
failed pre-trend (p < 0.001), fake-date and backtest checks, and an exploratory within-SKU cross-zone
design failed the backtest (Golden Ridge) or pre-trends (tortilla). The pooled model across all
206,724 non-promoted SKU-store-weeks suggests kettle is inelastic (−0.52) — far from
−2.78, so Golden Ridge very likely paid off — while private-label tortilla sits near its break-even.
By subcategory: Potato Chips −2.05; Cheese Snacks −1.96; Pretzels −1.37; Tortilla Chips −1.29; Popcorn −1.16 (not identified); Nuts −1.11; Trail Mix −0.83; Kettle Chips −0.52. Private label is more price-sensitive by 1.15 elasticity points (shift −1.46 to −0.84), identified
only from Bramble Select changes. **Next:** the tortilla decision is worth $501.24 even with perfect
information, less than a 13-week store test costs; take the action with the higher expected GP (roll the price back).

## 4. Forecast and in-stock

FY2025 forecast bias is **+13.4%** (SKU-bootstrap +11.8% to +15.0%); WAPE 22.5%. Bias is +22.8% in
promoted weeks versus +10.0% otherwise. The forecast still beats naive benchmarks (MASE 0.45
vs the lag-2 actual; 0.53 vs last year), so it should be corrected, not replaced: per-subcategory
factors learned on FY2024 cut FY2025 bias from +13.4% to +0.5% and WAPE from 22.5% to
19.1%.

**Did the over-forecast become stock? No.** Receipts and on-hand obey the stock-flow identity on 91% of
store-SKU-weeks (shrink 0.4% of receipts). In FY2025 stores received 0.9% more units than they
sold while the forecast was +13.4% over: receipts follow sales, not the forecast — weekly receipts move
1.26 units per unit sold the same week and 0.09 per unit sold the week before, the signature of
direct-store delivery. Average store stock at cost in comparable stores rose $19.4K, 1.8% of the
$1.05M the memo first quoted, and year-end stock fell $11.1K. Distribution-centre stock is not in the
extracts, so excess held upstream cannot be measured. Refit on weeks with no stock-out, bias is +19.3%
(+17.4% to +21.1%) — higher, not lower, because stock-outs happen in demand spikes the forecast under-calls
(−10.6% on those weeks); with their censored demand restored instead, bias is +12.5%
(+10.8% to +14.1%).

**Is the correction worth it? Judged on stock, not WAPE: no.** Replaying FY2025 store by store with
forecast-driven, case-pack orders and a safety stock sized on each forecast's own errors, each forecast at its
best safety factor costs about the same (lost GP + carrying cost at 25% a year: raw $178.5K, corrected
$179.4K); to reach 98% fill the corrected forecast needs $352.0K of stock against
$345.8K. The bias was acting as safety stock; removing it only moves that stock into the buffer. Both
forecast-driven policies need far more stock ($366.2K at best) than stores actually held ($224.4K
at 99.2% fill), so the current delivery process should not be replaced by forecast-driven ordering.

**Out-of-stock cost (exploratory).** On the 1,085 non-promoted FY2025 weeks that ended with zero stock, the
store sold everything it had, so demand was at least what it sold. Using the promotion baseline model and the
spread of its in-stock errors, the expected demand above that floor is 13,959 units, or **$26.4K** of gross
profit ($20.7K to $31.8K; 0.8% of category GP), plus $4.8K in promoted weeks. That is below the 1%
threshold for prioritising replenishment work. Treat it as a floor, not a measurement: the planned
adjacent-week method gives −$36.1K (stock-outs happen in demand spikes, so neighbouring weeks understate
demand); the model predicts 1,360 stock-outs against 1,857 observed, so its demand tail is too
thin; and a planted test recovered 135% of known losses when the floor was tied to the week's own sales,
but 92% under realistic censoring (post-hoc). **Next:** capture a daily stock-out flag or time of
stock-out; the weekly snapshot cannot measure this well.

## 5. Vendor funding

On 771 approved events, scan-back owed on observed units exceeds scan-back billed by **$65.5K**;
if every planned display ran, the gap rises to **$133.0K**. 150 approved events have no claim at all.
Everything billed on approved events was collected; $974.65 was billed on cancelled events and not
collected.

## How the results were checked

- **Ground truth:** the answer key is distributed separately; a [request to the dataset's author](answer_key_request.md) is drafted.
  Every estimate and interval was frozen in the tagged commit `estimates-frozen-v1` before the key was opened;
  the [scorecard](scorecard.md) compares them to it without re-tuning.
- **Second implementation:** 34 headline coefficients and clustered SEs re-estimated by an independent
  pure-Python solver (all agree); CI repeats them in R `fixest`.
- **Planted effects:** known effects added to the real data were recovered exactly (delist ±2%, elasticity −1.5).
- **Deviations from plan:** (1) delist GP indexed to each store's pre-period mean, because one comparison
  store-week had negative GP (log version: +1.4%, −3.8% to +6.7%); (2) the cross-zone price design and (3) the year-over-year
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
