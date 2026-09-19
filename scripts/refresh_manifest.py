"""Manifest of versioned/task files as UTF-8 text normalized to LF, excluding itself."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
manifest = {}
for name in sorted(set(names), key=lambda item: item.replace('\\', '/')):
    normalized = name.replace('\\', '/')
    if (
        normalized.startswith(('build/', 'dist/', 'lukart_work_domain_contracts.egg-info/'))
        or normalized == 'reports/manifest.sha256.json'
    ):
        continue
    path = ROOT / name
    if path.is_file():
        manifest[normalized] = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
(ROOT / 'reports/manifest.sha256.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(f'Manifest: {len(manifest)} files; CRLF normalized to LF; egg-info excluded.')
