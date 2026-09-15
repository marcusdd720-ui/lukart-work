"""Required Stage 02 runner: a skipped database test is not a passing gate."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
log = stream.getvalue()
(ROOT / 'reports/stage02-unittest.txt').write_text(log, encoding='utf-8')
report = dict(stage='02 Case Core', python=platform.python_version(), tests=result.testsRun,
              failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
              result='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL',
              scope='Synthetic core + real PostgreSQL integration; no legal, production or certification claim',
              ci_remote='EXECUTED' if os.environ.get('GITHUB_ACTIONS') == 'true' else 'NOT_EXECUTED', stage_02_closed=False)
files = [p for folder in ('lukart_work', 'tests', 'scripts') for p in (ROOT / folder).rglob('*')
         if p.is_file() and p.suffix in ('.py', '.sql', '.ps1') and '__pycache__' not in p.parts]
snapshot = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for p in sorted(files)}
report['tested_source_representation'] = 'UTF-8 source files with CRLF normalized to LF'
report['tested_sources'] = snapshot
(ROOT / 'reports/stage02-status.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(log)
print(json.dumps({k: v for k, v in report.items() if k != 'tested_sources'}))
sys.exit(0 if report['result'] == 'PASS' else 1)
