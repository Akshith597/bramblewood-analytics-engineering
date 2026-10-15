"""Shared plumbing for the decision analyses: read-only warehouse access and deterministic outputs."""
from pathlib import Path
import csv
import json
import math

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'analysis' / 'results'
PANELS = ROOT / 'target' / 'analysis_panels'


def connect():
    con = duckdb.connect(str(ROOT / 'warehouse/bramblewood.duckdb'), read_only=True)
    con.execute('set threads = 1')  # deterministic floating-point summation order
    return con


def pct_effect(log_points):
    return math.exp(log_points) - 1


def round_floats(value, digits=6):
    if isinstance(value, float):
        return float(f'{value:.{digits}g}') if value else 0.0
    if isinstance(value, dict):
        return {str(k): round_floats(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_floats(v, digits) for v in value]
    return value


def write_result(name, payload):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f'{name}.json').write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n',
                                          encoding='utf-8', newline='\n')


def export_panel(name, rows):
    """Write an estimation panel for the independent R cross-check (generated, not committed)."""
    PANELS.mkdir(parents=True, exist_ok=True)
    with (PANELS / f'{name}.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
