"""Read-only Stage 11 manifest and recorded evidence consistency check."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads(
    (ROOT / 'reports/manifest.sha256.json').read_text(encoding='utf-8')
)
names = subprocess.check_output(
    ['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
    cwd=ROOT,
    text=True,
).splitlines()
expected = {
    name for name in names
    if not name.startswith('lukart_work_domain_contracts.egg-info/')
    and name != 'reports/manifest.sha256.json'
}
assert set(manifest) == expected, 'MANIFEST_COVERAGE'
for name, checksum in manifest.items():
    actual = hashlib.sha256(
        (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
    ).hexdigest()
    assert actual == checksum, 'MANIFEST_HASH:' + name

report = json.loads(
    (ROOT / 'reports/stage11-status.json').read_text(encoding='utf-8')
)
assert report['result'] == 'PASS'
assert report['failures'] == report['errors'] == report['skipped'] == 0
assert report['tests'] > 0
assert report['stage_11_closed'] is False
for name, checksum in report['tested_sources'].items():
    actual = hashlib.sha256(
        (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
    ).hexdigest()
    assert actual == checksum, 'TESTED_SOURCE_DRIFT:' + name

schema_report = json.loads(
    (ROOT / 'reports/stage11-schema-validation.json').read_text(encoding='utf-8')
)
assert schema_report['result'] == 'PASS'
for name, checksum in schema_report['schema_hashes'].items():
    actual = hashlib.sha256(
        (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
    ).hexdigest()
    assert actual == checksum, 'SCHEMA_DRIFT:' + name

for folder in ('schemas', 'reports'):
    for path in (ROOT / folder).glob('*.json'):
        json.loads(path.read_text(encoding='utf-8'))
print(
    f'PASS: {len(manifest)} manifest entries; '
    'Stage 11 evidence and schema hashes consistent.'
)
