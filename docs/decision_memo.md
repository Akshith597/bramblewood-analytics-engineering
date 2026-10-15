# Salty Snacks — FY2026 line-review decision memo

*To: VP Merchandising · Data: Bramblewood POS, inventory and merchandising extracts, FY2024–FY2025 (synthetic) ·
Generated from code by `analysis/build_memo.py`; every figure is a named query result in `analysis/results/`.
Method and decision rules were [committed before any outcome was computed](../analysis/PLAN.md).*

| Question | Answer | Dollar figure (90% range) | Recommendation |
|---|---|---|---|
| 1. Delisting test | **Inconclusive** — the test cannot detect a GP change smaller than 4.3% | +$15.3K per year if rolled out to the other large stores (−$19.7K to +$50.3K) | Do not roll out on this evidence; rerun as a randomized, full-year test |
| 2. Promotions | **Not yet answered** | — | See below |
| 3. Price increases | **Not identified** from the data; break-even analysis favours Golden Ridge, tortilla is a coin flip | Golden Ridge +$52.9K (+$49.4K to +$56.3K); tortilla −$1.2K (−$11.4K to +$8.3K) — scenarios, not estimates | Keep Golden Ridge; test the tortilla price in a randomized subset of stores |
| 4. Forecast and in-stock | **Forecast over-forecasts by +13.4%** (+11.8% to +15.0%); out-of-stock cost not yet answered | $1.05M of planned inventory against demand that did not occur in FY2025 | Apply per-subcategory bias correction now; it cut FY2025 bias to +0.5% out of sample |
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
differences cancel.

## 2. Promotions — not yet answered

Deferred to protect depth on questions 1 and 3. Planned method: lift against a non-promoted store-SKU baseline,
net of cannibalisation (same subcategory) and a two-week post-promotion dip, with a per-event P&L including
vendor funding.

## 3. Spring 2025 regular-price increases

| | Golden Ridge kettle | Bramble Select tortilla (private label) |
|---|---|---|
| Increase / margin before | +8.2% / 33.4% | +9.9% / 43.3% |
| Break-even own-price elasticity | **−2.78** | **−2.18** |
| Pooled subcategory elasticity (unvalidated) | −0.52 (−0.73 to −0.30) | −2.44 (−3.05 to −1.84) |

An increase loses gross profit only if shoppers are more price-sensitive than the break-even elasticity — pure
arithmetic on price and cost. Neither event-level design passed its own checks: the pre-registered comparison
failed pre-trend (p < 0.001), fake-date and backtest checks, and an exploratory within-SKU cross-zone
design failed the backtest (Golden Ridge) or pre-trends (tortilla). The pooled model across all
206,724 non-promoted SKU-store-weeks suggests kettle is inelastic (−0.52) — far from
−2.78, so Golden Ridge very likely paid off — while private-label tortilla sits near its break-even.
By subcategory: Potato Chips −2.05; Cheese Snacks −1.96; Pretzels −1.37; Tortilla Chips −1.29; Popcorn −1.16 (not identified); Nuts −1.11; Trail Mix −0.83; Kettle Chips −0.52. Private label is more price-sensitive by 1.15 elasticity points (shift −1.46 to −0.84), identified
only from Bramble Select changes. **Next:** test the tortilla price in randomly chosen stores for 13 weeks.

## 4. Forecast and in-stock

FY2025 forecast bias is **+13.4%** (SKU-bootstrap +11.8% to +15.0%); WAPE 22.5%. Bias is +22.8% in
promoted weeks versus +10.0% otherwise. The forecast still beats naive benchmarks (MASE 0.45
vs the lag-2 actual; 0.53 vs last year), so it should be corrected, not replaced: per-subcategory
factors learned on FY2024 cut FY2025 bias from +13.4% to +0.5% and WAPE from 22.5% to
19.1%. **Out-of-stock cost — not yet answered:** a weekly on-hand snapshot cannot date a stock-out;
the planned lower-bound method is in the analysis plan.

## 5. Vendor funding

On 771 approved events, scan-back owed on observed units exceeds scan-back billed by **$65.5K**;
if every planned display ran, the gap rises to **$133.0K**. 150 approved events have no claim at all.
Everything billed on approved events was collected; $974.65 was billed on cancelled events and not
collected.

## How the results were checked

- **Ground truth:** the dataset's answer key is distributed separately and is not public, so it was not used.
- **Second implementation:** 18 headline coefficients and clustered SEs re-estimated by an independent
  pure-Python solver (all agree); CI repeats them in R `fixest`.
- **Planted effects:** known effects added to the real data were recovered exactly (delist ±2%, elasticity −1.5).
- **Deviations from plan:** (1) delist GP indexed to each store's pre-period mean, because one comparison
  store-week had negative GP (log version: +1.4%, −3.8% to +6.7%); (2) the cross-zone price design and (3) the year-over-year
  delist adjustment were added after diagnostics and are labelled exploratory; (4) promotions and out-of-stock
  cost deferred.
