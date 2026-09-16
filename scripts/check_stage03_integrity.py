"""Read-only package manifest and recorded test-evidence consistency check."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT/'reports/manifest.sha256.json').read_text(encoding='utf-8'))
names = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
expected = {n for n in names if not n.startswith('lukart_work_domain_contracts.egg-info/') and n != 'reports/manifest.sha256.json'}
assert set(manifest) == expected, 'MANIFEST_COVERAGE'
for name, checksum in manifest.items():
    assert hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() == checksum, name
report = json.loads((ROOT/'reports/stage03-status.json').read_text(encoding='utf-8'))
assert report['result'] == 'PASS' and report['failures'] == report['errors'] == report['skipped'] == 0
for name, checksum in report['tested_sources'].items():
    assert hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() == checksum, 'TESTED_SOURCE_DRIFT:' + name
for folder in ('schemas','reports'):
    for path in (ROOT/folder).glob('*.json'):
        json.loads(path.read_text(encoding='utf-8'))
print(f'PASS: {len(manifest)} manifest entries; reports and tested source hashes consistent.')
