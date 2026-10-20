"""Compare every model's ordered contents before and after a complete reload/build."""

from pathlib import Path
import hashlib
import json
import subprocess
import sys
import duckdb

ROOT = Path(__file__).resolve().parents[1]


def fingerprints():
    result = {}
    with duckdb.connect(str(ROOT / 'warehouse/bramblewood.duckdb'), read_only=True) as con:
        manifest = json.loads((ROOT / 'target/manifest.json').read_text(encoding='utf-8'))
        names = sorted(
            n['name']
            for n in manifest['nodes'].values()
            if n['resource_type'] == 'model' and n['package_name'] == 'bramblewood'
        )
        for name in names:
            cur = con.execute(f'SELECT * FROM "{name}" ORDER BY ALL')
            digest = hashlib.sha256()
            count = 0
            while rows := cur.fetchmany(10000):
                for row in rows:
                    digest.update((json.dumps(row, default=str, separators=(',', ':')) + '\n').encode())
                count += len(rows)
            result[name] = {'rows': count, 'sha256': digest.hexdigest()}
    return result


if __name__ == '__main__':
    before = fingerprints()
    subprocess.run([sys.executable, 'scripts/ingest.py'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'scripts/invoke_dbt.py', 'build'], cwd=ROOT, check=True)
    after = fingerprints()
    if not before or before != after:
        raise AssertionError('Full rebuild changed model contents')
    (ROOT / 'evidence/repeatability.json').write_text(
        json.dumps({'status': 'pass', 'models': after}, indent=2), encoding='utf-8'
    )
    print(f'PASS: {len(after)} models identical after full reload and rebuild')
