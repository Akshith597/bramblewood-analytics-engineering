"""Stage the dbt Core v1 documentation files after a successful validated build."""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    receipt = json.loads((ROOT / 'evidence/dbt_build_results.json').read_text(encoding='utf-8'))
    results = receipt.get('results', [])
    if not results or any(row['status'] not in ('success', 'pass') for row in results
                          if not row['unique_id'].startswith('exposure.')):
        raise RuntimeError('Documentation publication requires a successful dbt build')
    reconciliation = json.loads((ROOT / 'evidence/independent_reconciliation.json').read_text(encoding='utf-8'))
    if reconciliation.get('status') != 'pass':
        raise RuntimeError('Independent reconciliation must pass before publication')

    files = ['index.html', 'manifest.json', 'catalog.json', 'insights.html']
    for name in files:
        path = ROOT / 'target' / name
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f'Missing generated site file: {path}')
        if name.endswith('.json'):
            json.loads(path.read_text(encoding='utf-8'))

    destination = ROOT / 'public_site'
    destination.mkdir(exist_ok=True)
    for name in files:
        shutil.copyfile(ROOT / 'target' / name, destination / name)
    (destination / '.nojekyll').touch()
    print('Staged dbt documentation and insights page in public_site/')


if __name__ == '__main__':
    main()
