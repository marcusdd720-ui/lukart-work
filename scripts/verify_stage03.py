"""Stage 03 acceptance: full regression, skip is failure; historical reports preserved."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'),top_level_dir=str(ROOT))
result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
(ROOT/'reports/stage03-unittest.txt').write_text(stream.getvalue(),encoding='utf-8')
files = [p for folder in ('lukart_work','tests','scripts') for p in (ROOT/folder).rglob('*')
         if p.is_file() and p.suffix in ('.py','.sql','.ps1') and '__pycache__' not in p.parts]
report = dict(stage='03 Storage + Versioning',python=platform.python_version(),tests=result.testsRun,
    failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
    result='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL',
    executed_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    ci_remote='EXECUTED' if os.environ.get('GITHUB_ACTIONS')=='true' else 'NOT_EXECUTED',
    stage_03_closed=False,
    tested_sources={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in sorted(files)})
(ROOT/'reports/stage03-status.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(stream.getvalue())
print(json.dumps({k:v for k,v in report.items() if k!='tested_sources'}))
sys.exit(0 if report['result']=='PASS' else 1)
