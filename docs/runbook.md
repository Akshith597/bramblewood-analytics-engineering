# Runbook

## Clean setup

Use Python 3.12. Run commands from the repository root.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts/run_all.py
python scripts/verify_repeatability.py
python scripts/verify_incremental.py
python -m unittest discover -s tests_python -v
python -m sqlfluff lint models tests analyses
python -m pre_commit install
```

On macOS/Linux, activate with `source .venv/bin/activate`. If PowerShell activation is blocked, use `.venv\Scripts\python.exe` directly for each command. Direct project dependencies are pinned; transitive dependencies are resolved by pip and are not a fully locked environment.

## Inspect the warehouse

```python
import duckdb
con = duckdb.connect('warehouse/bramblewood.duckdb', read_only=True)
print(con.sql('SELECT * FROM audit_reconciliation').df())
print(con.sql('SELECT * FROM mart_category_weekly LIMIT 8').df())
```

## Browse lineage and SQL

```text
python scripts/invoke_dbt.py docs serve --port 8080
```

Then visit `http://localhost:8080`. The generated catalog has model lineage and compiled SQL. Stop the server with Ctrl+C. `target/` is generated locally and is excluded from Git; `evidence/dbt_build_results.json` is the portable build receipt.

## Targeted tasks

| Task | Command |
|---|---|
| Reload supplied files | `python scripts/ingest.py` |
| Build models and tests | `python scripts/invoke_dbt.py build` |
| Run only fixture-based unit tests | `python scripts/invoke_dbt.py test --select test_type:unit` |
| Test existing models | `python scripts/invoke_dbt.py test` |
| Independent source tie-out | `python scripts/independent_reconcile.py` |
| Check raw reload freshness | `python scripts/invoke_dbt.py source freshness` |
| Snapshot item and store history | `python scripts/invoke_dbt.py snapshot` |
| Rebuild the incremental sales fact from scratch | `python scripts/invoke_dbt.py build --full-refresh` |
| Verify deterministic rebuild (unchanged input) | `python scripts/verify_repeatability.py` |
| Verify incremental handling of changed input | `python scripts/verify_incremental.py` |
| Regenerate all delivery evidence | `python scripts/run_all.py` |

## Troubleshooting

- **Database locked:** Stop any writer or dbt docs session using the warehouse, then retry. DuckDB is a local file database.
- **Invalid POS row:** Inspect `stg_pos_audit` where `disposition='invalid_record'`. Do not filter it away to make tests pass. Correct ingestion/contract only with an explicit policy.
- **Contract mismatch:** Compare output columns and types with `models/marts/schema.yml`. Correct SQL/schema intentionally; disabling the contract bypasses the public model guarantee.
- **Lint failure:** Run `python -m sqlfluff fix models tests analyses`, review the edits, then rerun lint. SQLFluff uses the dbt templater and the project's DuckDB profile; install dev requirements and run `dbt deps` first.
- **Duplicate sales key:** Check normalized UPC, date and source rows. Nonidentical records sharing a business key require a source correction or an explicit aggregation rule.
- **Temporal overlap:** Inspect the applicable raw effective periods. Only cost has an explicit latest-start policy; other overlaps fail.
- **Missing key or cost:** Review left-join failures, source master coverage and lifecycle dates. Do not convert missing cost to zero.
- **Stale evidence:** Run the complete pipeline. Documentation generation overwrites dbt's default run-results file, so the runner preserves the build receipt before generating docs.
- **Stale source warning or error:** `source freshness` warns when a raw table was last reloaded more than 24 hours ago and fails after 72 hours, using the `raw._load_log` table that `ingest.py` writes. Rerun ingestion. This checks that loading still runs, not how old the extract is; the publication workflow checks extraction age against the batch manifest.
- **Backdated correction:** `fct_sales` incremental runs restate only the weeks inside `sales_restatement_lookback_days`. After a cost, price, master-data or older POS correction, run `build --full-refresh`.
- **Failure partway through:** Stop consumption, fix the input/model, rerun the whole pipeline and inspect the new receipt. A failed local dbt run is not an atomic rollback of every table.

## Operational acceptance criteria

Every model builds, every data and unit test passes, every source store-week ties out independently, and repeated loads reproduce the same model fingerprints. Review the cost exception and metric limitations even when checks pass. Historical source coverage is not a live freshness SLA.

## Validated batch publication

For a newly delivered batch, record the source owner's actual extraction timestamp and hashes. If files were extracted at different times, edit their individual `extracted_at_utc` values in the manifest to match their provenance. Never replace an old extraction time with today's date just to pass the gate. The committed synthetic historical extracts are a fixture, so this example is a workflow demonstration, not evidence of a live feed.

```powershell
# Replace this timestamp with the actual extraction time supplied with the batch.
python scripts/publish_warehouse.py manifest --extracted-at "2026-10-18T12:00:00Z" --output source_batch.json
python scripts/publish_warehouse.py publish --source-manifest source_batch.json --max-source-age-hours 24
python scripts/publish_warehouse.py check --max-source-age-hours 24
```

The default destination is `warehouse/published/`; use `--destination` on both publish and check to override it. Source manifests can be stored outside the repository. The age gate is a configurable delivery SLA, not the age of business transactions inside the batch. Future timestamps, missing offsets, hash mismatches, and expired batches fail. The publish command runs `run_all.py` and `verify_repeatability.py` in an isolated copy; it publishes warehouse data and evidence, not a regenerated business recommendation.

Every corrected source delivery gets a new manifest, even when filenames stay the same. All historical data rebuilds, then contracts, tests, reconciliation and repeatability gate publication. Schema changes that violate those checks fail rather than silently advancing the release. Compatible upstream schema extensions are not automatically prohibited; the dbt contracts define the consumer boundary. Numeric business conclusions and frozen estimates still require their separate analytical review.

Read the pointer once per consumer session, and retain that database path for the session:

```python
import json
from pathlib import Path
import duckdb

published = Path('warehouse/published')
release = json.loads((published / 'current.json').read_text(encoding='utf-8'))
con = duckdb.connect(str(published / release['database']), read_only=True)
```

Schedule the `check` command using your operating-system scheduler or monitoring service. It emits JSON and exits nonzero on stale sources, missing publication, missing database, or a database checksum mismatch; route that exit status to your alert service. No scheduler or external alert is installed by this change. Keep the original extraction timestamps when retrying a failed build. Old release files remain available to existing readers and are never overwritten by the publisher.

If a build fails, the last published pointer stays unchanged; inspect the command's failure output, correct the batch or model and retry. A crash can leave `.publisher.lock` in the destination. Confirm no publisher is active before manually removing that empty directory. Unreferenced releases can remain after a failed pointer swap; inspect them before any manual retention cleanup. Do not delete a release while readers may still be using it.

Each new release starts from the current release's snapshot tables (`snap_items`, `snap_stores`), so Type 2 history accumulates across publications; the receipt lists the tables carried forward under `snapshot_history_carried`. The first release starts history empty.

Run `python -m unittest discover -s tests_python -p test_publication.py -v` for filesystem-fixture checks covering corrected batches, stale inputs, failed builds, concurrent publication failed atomic pointer replacement and snapshot history carried between releases. These tests verify the publication boundary; the actual warehouse build must still pass with the full dataset and installed dependencies.

## Scheduled recovery drill

[`recovery-drill.yml`](../.github/workflows/recovery-drill.yml) runs [`scripts/recovery_drill.py`](../scripts/recovery_drill.py) every Monday on GitHub Actions, and on demand from the Actions tab. It uses the real publisher, with full warehouse builds, in a throwaway destination:

| Step | Expected outcome |
|---|---|
| Publish a release | `check` passes |
| Incident: the source is older than a one-second age limit | `check` fails with a freshness error |
| Bad delivery: a source file changes after its manifest | publication is refused before building; the release pointer does not move |
| Recovery: a fresh manifest for the restored files | a new release publishes, carries snapshot history forward, `check` passes, and the earlier release is untouched |

Any other outcome fails the job. The receipts are uploaded as the `recovery-drill` artifact. Publication also refuses to copy history out of a current release whose database fails its checksum. Run it locally with `python scripts/recovery_drill.py`; on Windows, set `RECOVERY_DRILL_DESTINATION` to a short path such as `C:\drill`, because dbt packages exceed the path-length limit inside a deep build folder.

This is a drill on CI runners. It shows the failure and recovery paths working; it is not a monitored production deployment, and it has no alert delivery or access control.

## Publication

The dataset in `data/` was generated by AI and is fictional; [data/SOURCE_README.md](../data/SOURCE_README.md) records its provenance. The project's MIT license covers the code and documentation only, not the dataset, and no separate dataset license has been documented. Record one before redistributing the data on its own terms.

The publication guide describes repository and Pages setup. Refer to the GitHub Actions run and the release evidence for actual hosted validation status.

