"""Load immutable extracts; business transformations belong in dbt SQL."""

from pathlib import Path
import hashlib
import json
import platform
from datetime import datetime, timezone
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "data" / "raw"
    warehouse = ROOT / "warehouse"
    warehouse.mkdir(exist_ok=True)
    files = sorted(source.iterdir())
    manifest = {
        "loaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
        "files": [],
    }
    with duckdb.connect(str(warehouse / "bramblewood.duckdb")) as con:
        con.execute("BEGIN")
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        # Load audit for dbt source freshness: when each raw table was last replaced, not when it was extracted.
        con.execute(
            "CREATE OR REPLACE TABLE raw._load_log "
            "(table_name VARCHAR, source_file VARCHAR, row_count BIGINT, loaded_at_utc TIMESTAMPTZ)"
        )
        for path in files:
            meta = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "tables": {}}
            if path.suffix == ".csv":
                tables = {path.stem: pd.read_csv(path, dtype=str, keep_default_na=False)}
            elif path.suffix == ".xlsx":
                tables = pd.read_excel(path, sheet_name=None, dtype={"upc": str})
            else:
                continue
            for table, frame in tables.items():
                frame = frame.copy()
                frame["_source_file"] = path.name
                frame["_source_row"] = range(2, len(frame) + 2)
                con.register("incoming", frame)
                con.execute(f'CREATE OR REPLACE TABLE raw."{table}" AS SELECT * FROM incoming')
                con.unregister("incoming")
                meta["tables"][table] = len(frame)
                con.execute(
                    "INSERT INTO raw._load_log VALUES (?, ?, ?, ?)",
                    [table, path.name, len(frame), manifest["loaded_at_utc"]],
                )
            manifest["files"].append(meta)
        con.execute("COMMIT")
    (warehouse / "load_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Loaded", sum(len(f["tables"]) for f in manifest["files"]), "raw tables")


if __name__ == "__main__":
    main()
