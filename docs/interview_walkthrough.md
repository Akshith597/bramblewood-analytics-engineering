# Five-minute project walkthrough

Use this as a rehearsal outline. Describe your own role accurately; the repository's AI-assisted history and synthetic dataset are part of the explanation.

| Time | Show | Explain |
|---|---|---|
| First minute | README and dashboard | The fictional retailer needs consistent sales, inventory and funding measures. This is a local warehouse demonstration, with AI-generated source extracts and AI-assisted implementation. |
| Second minute | `models/staging/stg_pos_audit.sql` | Raw rows receive a disposition. Exact raw-field replays are removed before normalization; disagreements at the normalized key fail validation. Explain why `SELECT DISTINCT` alone loses the audit trail. |
| Third minute | `models/intermediate/int_item_cost_intervals.sql` and the sales fact | Effective-dated joins can multiply revenue. Explain latest-start precedence, the retained exception flag, the sensitivity calculation and the need for source-owner confirmation. |
| Fourth minute | `models/marts/fct_sales.sql` and `macros/restate_sales_window.sql` | The incremental load deletes and reloads a recent date window, including deleted weeks. Older corrections require a full refresh. Distinguish unchanged-input repeatability from changed-input correctness tests. |
| Final minute | Reconciliation receipt and architecture scope | The independent CSV/Decimal implementation checks store-week counts, units and sales. Explain what it does not prove: every row-level mapping, statistical causality, dataset ground truth or production operating experience. |

## Questions to answer without assistance

- What is the grain of each fact and mart, and which joins could cause fanout?
- When is a missing value different from zero? Show a model that preserves that distinction.
- Why is estimated funding a review queue rather than a confirmed receivable?
- What happens if a source removes a week or corrects a sale outside the restatement window?
- Which business rules would need finance or merchandising approval?
- What did you personally decide, what did AI implement, and which checks did you inspect or run yourself?

## Small SQL exercise

On a separate practice branch, build a store-week sales summary from `fct_sales` with signed units, net sales and a row count. Declare its grain and add a uniqueness check on store and week, then reconcile its totals to the fact. Preserve returns and avoid joining inventory or claims at incompatible grains.

Run the project checks and explain the generated SQL and any failure before using AI to help. This is a practice task, not a claim that the exercise has already been completed.

## Scope to state clearly

The warehouse and recovery drill run locally or on GitHub runners. Snowflake SQL has been compiled but has not run on a live account. The dataset generator and answer key are unavailable, and the statistical extension has no dataset-ground-truth score. Use the warehouse's reproducibility and failure tests as the primary evidence.
