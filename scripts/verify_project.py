"""Enforce layer boundaries and machine-readable contract/documentation coverage."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'target/manifest.json').read_text(encoding='utf-8'))
    models = {key: value for key, value in manifest['nodes'].items()
              if value['resource_type'] == 'model' and value['package_name'] == 'bramblewood'}
    sources = {key for key, value in manifest['sources'].items() if value['package_name'] == 'bramblewood'}
    staged_sources = set()
    contracts = 0
    described_columns = 0
    errors = []
    for key, model in models.items():
        layer = Path(model['original_file_path']).parts[1]
        for parent in model['depends_on']['nodes']:
            if parent.startswith('source.'):
                if layer != 'staging':
                    errors.append(f'{key} bypasses staging: {parent}')
                else:
                    staged_sources.add(parent)
            elif parent in models:
                parent_layer = Path(models[parent]['original_file_path']).parts[1]
                if layer == 'staging' or (layer == 'intermediate' and parent_layer == 'marts'):
                    errors.append(f'{key} has invalid {parent_layer} parent {parent}')
        if not model.get('description', '').strip():
            errors.append(f'{key} lacks a model description')
        for column in model['columns'].values():
            if not column.get('description', '').strip() or not column.get('data_type'):
                errors.append(f'{key}.{column["name"]} lacks description/type')
            else:
                described_columns += 1
        if layer == 'marts':
            if not model['config'].get('contract', {}).get('enforced'):
                errors.append(f'{key} lacks an enforced contract')
            else:
                contracts += 1
    if staged_sources != sources:
        errors.append(f'Sources without direct staging coverage: {sorted(sources-staged_sources)}')
    if errors:
        raise AssertionError('\n'.join(errors))
    receipt = {'status': 'pass', 'models': len(models), 'staged_sources': len(staged_sources),
               'enforced_mart_contracts': contracts, 'documented_typed_columns': described_columns,
               'exposures': len(manifest['exposures'])}
    (ROOT / 'evidence/project_quality.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
