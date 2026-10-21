# The methods in plain English

This page explains every statistical method the [decision memo](decision_memo.md) and the
[FY2026 plan](fy2026_plan.md) use: what it does, why it was chosen here, and the questions a reviewer or interviewer
is likely to ask. The exact specification of each method is in the [analysis plan](../analysis/PLAN.md). The
figures quoted here come from the memo.

## Comparing test stores with control stores (difference-in-differences)

**Used for:** the delisting test (question 1).

Four large stores switched to a smaller planogram in FY2025 week 27. Comparing their profit before and after the
switch isn't enough, because the whole chain also changed over that time (seasons, inflation, holidays). So the
analysis compares the *change* in the test stores with the *change* in 18 comparison stores over the same weeks.
The difference between those two changes is the estimated effect of the switch.

It is run as a regression with **store fixed effects** (each store has its own normal level of sales) and **week
fixed effects** (each week has its own chain-wide shock). What is left is the effect of the switch.

- *Why log gross profit?* So the effect reads as a percentage, and a big store and a small store count equally.
- *Main assumption:* without the switch, test and comparison stores would have moved in parallel. The fake-date
  check below tests this assumption, and here it **failed**, which is why the memo calls the result inconclusive.

## Why errors are "clustered by store", and why only four test stores matters

Weeks from the same store aren't independent. A store that has a good week tends to have a good next week. If
every store-week were treated as a separate data point, the model would think it had far more information than it
does and would report ranges that are too narrow. **Clustering by store** treats each store as one block of
evidence, so the uncertainty is measured across stores, which is the level where the treatment was assigned.

The catch: only 4 stores got the new planogram. Clustered errors behave as if there are 22 independent pieces of
evidence, but the treated side has just 4, so the usual ranges come out too narrow. Two simple fixes are used:

- **A wider t critical value.** The 90% range is the estimate ± *t* × the clustered standard error, where *t*
  comes from Student's t distribution with **3 degrees of freedom** (4 test stores − 1). That gives *t* = 2.35
  instead of 1.645, so the range is about 40% wider. Rule of thumb: the smaller group sets the sample size.
- **Permutation test:** pretend that each possible group of 4 comparison stores had been the test group
  (3,060 combinations) and see how often a "fake" effect is as big as the real one. If it often is, the real one
  isn't convincing. For the delist profit result this happens 22% of the time (p = 0.22).

## Placebo and fake-date checks

If a method finds an effect where none can exist, it can't be trusted where one might exist. A **fake-date
check** moves the test date to a time when nothing happened (for example, a year earlier) and re-runs the analysis.
It should find roughly zero. For the delist test it found a +2.4% "effect" a year earlier, which shows that large
stores have their own second-half seasonality. That is why the profit result isn't trusted, while the transfer rate
below passed the same checks and is used.

## Minimum detectable effect (power)

The **minimum detectable effect (MDE)** is the smallest true effect the test would detect 80% of the time. With 4
test stores it is about 4.3%, so a real 2% profit loss would usually go unnoticed. "No significant effect" here
means "the test was too small to tell", not "no effect".

## Transfer rate (τ)

When products are delisted, some shoppers buy a different product instead of leaving. The **transfer rate** is the
dollars gained by the remaining products per dollar lost on the delisted ones. The test measured about 124%
(90% range 83% to 164%). That means remaining products more than made up the lost sales, partly because they took
over the freed shelf space. The cut list uses this rate to estimate the profit change from cutting each product,
and only cuts a product if the change is positive even at the low end of the range.

## Price elasticity and break-even elasticity

**Price elasticity** is the percentage change in units sold for a 1% change in price. For example, −0.5 means a 10%
price increase loses about 5% of units.

The **break-even elasticity** is the sensitivity at which a price increase leaves gross profit unchanged. It comes
from price and cost alone, with no statistics. If shoppers are less sensitive than break-even, the increase made
money. For Golden Ridge, break-even is −2.78 and the estimated sensitivity is about −0.52, so the increase very
likely paid off even though the event-level designs couldn't measure it directly.

## Promotion baseline (what would have sold without the promotion)

**Used for:** question 2.

A model fitted only on weeks with no promotion nearby predicts what each product would have sold in each store
and week. The promotion's **lift** is actual sales minus that baseline. Two costs are then subtracted:

- **Post-promotion dip:** shoppers stock up, so the next two weeks sell less.
- **Cannibalisation:** sister products in the same subcategory sell less while one is on promotion.

The check: the same model predicts held-out weeks with no promotion, and must be within ±2% there.

## Stock-outs as censored demand

**Used for:** question 4.

When a shelf is empty, sales show what was *available*, not what shoppers *wanted*. Demand is "censored" at the
stock level. The model estimates how much demand probably went above the available stock, using how much a
product's weekly sales normally vary. The result is labelled a lower bound and *exploratory*, because the
approach was chosen after seeing some results (the plan's addendum says exactly what was seen).

## Bootstrap ranges

Most other 90% ranges (promotions, stock-outs, forecast bias) come from a **store bootstrap**: resample the 24 stores with replacement thousands of times, redo
the calculation each time, and take the middle 90% of the results. It answers "how different would this be with a
different mix of stores?"

## Low / base / high scenarios for the FY2026 plan

The plan has five levers, each with its own uncertainty, and some of them overlap (a delisted product's
promotions can't also be counted in the promotion lever). Each uncertain input is set three ways:

- **Estimated inputs** (transfer rate, price elasticities, promotion results): the low end of the 90% range, the
  estimate, and the high end.
- **Negotiation inputs**, which have no data behind them: vendors re-win none, half or all of the dropped events'
  funding; 50%, 75% or 100% of the under-billing is recovered.

The **base case** uses the middle values. The **low case** puts every input at its bad end at the same time, and
the **high case** at its good end. Because everything going wrong at once is unlikely, the low case is a modeled
low case rather than a probability. It is not a guaranteed lower bound: basket effects, vendor reactions and
implementation costs are left out of every case and could take the outcome below it. The plan stays positive in
the modeled low case.

## What still needs a test

None of the decisions is settled beyond doubt, and each rests on a stated assumption:

- **Promotions without a display** lost money before vendor funding in FY2025. Dropping them assumes vendors and
  shoppers respond as modeled.
- **The cut list** is positive at the low end of the transfer rate, but that rate was measured on slow sellers in
  four large stores. Applying it to other formats is an assumption, so the plan pilots the cuts with a store
  holdout before a chain rollout.
- **Golden Ridge's price** is far from break-even only if the unvalidated pooled elasticity is roughly right.
- **The tortilla price** is a few thousand dollars either way, less than a store test would cost.

The biggest uncertainty, how much vendor money is re-won, is decided at the negotiating table, not by a test.

## Checking the numbers twice

Every headline coefficient and its clustered standard error is re-estimated by a separate pure-Python
implementation and by the R `fixest` package in CI. They must agree to within 1e-6 (estimate) and 1e-4 (standard
error). This catches coding mistakes, not design mistakes.

## The fixed analysis plan, and what it does and doesn't prove

The metrics, comparison groups and decision rules for each question were written down and committed
([`analysis/PLAN.md`](../analysis/PLAN.md)) before the first results commit; promotions and out-of-stock cost were
added in a later addendum, after some unit-level aggregates had been seen. This makes it hard to quietly pick the
method that gives the nicest answer. Every later change is logged as a deviation with a reason. It isn't a formal
pre-registration with an outside registry. The plan commit and the first results commit were made about half an hour
apart by the same person, and a later author-email correction rewrote the repository's history (new commit IDs; same
files, messages and dates). Git timestamps are set by whoever commits, so Git history alone cannot prove when results
were first computed. The plan shows discipline rather than proving independence.

## Questions to be ready for

- **"Why not just compare test stores before and after?"** Chain-wide changes over the same weeks would be
  mistaken for the effect. The comparison stores remove those.
- **"Why cluster by store?"** Weeks within a store are correlated, and stores are what was assigned to the test.
  Treating every week as independent would make the ranges too narrow.
- **"Four stores isn't enough, is it?"** No. That is why the range uses 3 degrees of freedom (test stores − 1),
  why the permutation test is reported, why the MDE is reported, and why the answer is "inconclusive".
- **"If the delist profit result failed, why trust the transfer rate?"** It passed the same fake-date checks the
  profit result failed, and it holds when comparing the same season year over year.
- **"How do you know the promotion baseline is right?"** It predicts held-out non-promotion weeks within ±2%, and
  the pre-promotion weeks within ±3%.
- **"What's the weakest part?"** The vendor-funding share in the promotion lever is a negotiation outcome with no
  data behind it. The plan is built to stay positive even if vendors keep all of it. The stock-out cost is
  exploratory.
- **"What would you do with more time or data?"** Randomize the planogram across matched store pairs for a full
  year, and record display execution so funding can be verified.
