# Runbook

## Clean setup

Use Python 3.12. Run commands from the repository root.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts/run_all.py
python scripts/verify_repeatability.py
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
| Verify deterministic rebuild | `python scripts/verify_repeatability.py` |
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
- **Failure partway through:** Stop consumption, fix the input/model, rerun the whole pipeline and inspect the new receipt. A failed local dbt run is not an atomic rollback of every table.

## Operational acceptance criteria

Every model builds, every data and unit test passes, every source store-week ties out independently, and repeated loads reproduce the same model fingerprints. Review the cost exception and metric limitations even when checks pass. Historical source coverage is not a live freshness SLA.

## Publication

The source README describes the data as fictional and publishable as-is; the original attribution is retained. No original author or explicit dataset license is supplied. This package does not invent one. The repository can be reviewed locally now; before redistributing it under a license, obtain or record the dataset's license separately from your code license.

The publication guide describes repository and Pages setup. Refer to the GitHub Actions run and the release evidence for actual hosted validation status.
