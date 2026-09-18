"""Validate every exported JSON Schema with an independent Draft 2020-12 engine."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
schemas = sorted((ROOT / 'schemas').glob('*.json'))
hashes = {}
for path in schemas:
    schema = json.loads(path.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    name = path.relative_to(ROOT).as_posix()
    hashes[name] = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()

report = {
    'result': 'PASS',
    'engine': f"jsonschema {importlib.metadata.version('jsonschema')} Draft202012Validator",
    'schemas_checked': len(schemas),
    'schema_hashes': hashes,
}
(ROOT / 'reports/stage09-schema-validation.json').write_text(
    json.dumps(report, indent=2) + '\n', encoding='utf-8'
)
print(json.dumps({k: v for k, v in report.items() if k != 'schema_hashes'}))
