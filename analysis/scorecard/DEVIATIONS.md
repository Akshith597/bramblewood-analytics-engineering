# Deviation log

Everything decided after a result was seen, in order. Entries above the line were written **before** the answer
key was requested or opened and are frozen with the estimates (tag `estimates-frozen-v1`). Entries below it record
what the key taught; they never change a frozen estimate, interval or the plan.

Deviations 1–5 (delist GP indexing, cross-zone price design, year-over-year delist adjustment, the Q2/Q4 addendum,
the censored-demand stock-out estimator) are in the [decision memo](../../docs/decision_memo.md#how-the-results-were-checked).

## Before the key (FY2026 round)

6. **Cut-list support.** The first ranking applied the delist test's transfer rate to every SKU and put
   best-sellers (e.g. a seven-facing tortilla item) at the top, because a low-margin SKU's sales "transfer" to
   higher-margin sisters at τ > 1. τ was measured on two-facing slow sellers, so candidates were restricted to SKUs
   selling no more per store-year than the largest SKU the test cut, and ranked by GP per facing. Changed after
   seeing the first list.
7. **Checks on τ.** Fake-date (FY2024 W27, FY2025 W1) and same-season year-over-year versions of the transfer rate
   were added after the GP effect was known to fail its fake-date check. τ passed both.
8. **Inventory simulation policy.** The first version set order-up-to stock at a fixed percentage above forecast;
   it could not reach the observed stock-out rate at any setting, so safety stock was changed to z × the forecast's
   own trailing error (the textbook form). The verdict rule (compare each forecast at its own best z) was fixed
   after the first version had run.
9. **Intervals added for the scorecard.** Promotion unit lift and the post-promotion dip had point estimates only.
   Store-cluster bootstrap ranges were added (same seed and draw count as the existing ranges). They hold the
   baseline model fixed, so they understate uncertainty from the model itself. Cannibalisation intervals are
   ±1.645 × the store-clustered SE already reported.
10. **Primary forecast bias.** The requested refit on weeks without a stock-out came out higher than the all-week
    bias. Stock-out weeks are demand spikes, so the refit selects low-demand weeks. Bias on all weeks with censored
    demand restored was then made the primary estimate. All three versions are frozen and scored.
11. **Elasticity labels.** The pooled model's subcategory elasticities are frozen as the brands' own-price
    elasticity, with private label as a separate shift. If the key defines elasticity per SKU, at a different
    level, or as a cross-price term, the conversion rule is written here before any converted number is compared.

---

## After the key

*(Empty: the key has not been received.)*
