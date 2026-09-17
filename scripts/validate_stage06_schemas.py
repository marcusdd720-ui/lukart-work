"""Stage 06: deterministic Draft 2020-12 metaschema validation evidence."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
hashes = {}
for path in sorted((ROOT / 'schemas').glob('*.json')):
    schema = json.loads(path.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(
        path.read_bytes().replace(b'\r\n', b'\n')
    ).hexdigest()
report = {
    'stage': '06 Document Registry',
    'engine': 'jsonschema',
    'engine_version': importlib.metadata.version('jsonschema'),
    'dialect': 'https://json-schema.org/draft/2020-12/schema',
    'schemas': len(hashes),
    'result': 'PASS',
    'schema_hashes': hashes,
}
(ROOT / 'reports/stage06-schema-validation.json').write_text(
    json.dumps(report, indent=2) + '\n', encoding='utf-8'
)
print(json.dumps({k: v for k, v in report.items() if k != 'schema_hashes'}))
