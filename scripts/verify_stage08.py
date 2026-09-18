"""Stage 08 acceptance: full regression with deterministic machine-readable evidence."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
files = [
    p for folder in ('lukart_work', 'tests', 'scripts')
    for p in (ROOT / folder).rglob('*')
    if p.is_file() and p.suffix in ('.py', '.sql', '.ps1') and '__pycache__' not in p.parts
]
report = dict(
    stage='08 Document Planner',
    tests=result.testsRun,
    failures=len(result.failures),
    errors=len(result.errors),
    skipped=len(result.skipped),
    result='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL',
    evidence_binding='TESTED_SOURCE_SHA256',
    stage_08_closed=False,
    tested_sources={
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        for p in sorted(files)
    },
)
(ROOT / 'reports/stage08-status.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(stream.getvalue())
print(json.dumps({k: v for k, v in report.items() if k != 'tested_sources'}))
sys.exit(0 if report['result'] == 'PASS' else 1)
