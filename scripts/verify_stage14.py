"""Stage 14 acceptance runner: full repository regression, zero tolerated skips."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
suite=unittest.defaultTestLoader.discover(str(ROOT/"tests"),top_level_dir=str(ROOT))
result=unittest.TextTestRunner(verbosity=2).run(suite)
report={
 "contract":"urn:lukart:work:Stage14Verification:1.0.0",
 "stage":"14 UNIVERSUM Execution Kernel",
 "tested_sha":os.environ.get("TESTED_SHA") or os.environ.get("GITHUB_SHA") or "LOCAL_UNBOUND",
 "tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
 "skips":len(result.skipped),"result":"PASS" if result.wasSuccessful() and not result.skipped else "FAIL",
 "source_sha256":{}
}
for rel in (".github/workflows/stage14.yml","lukart_work/factory/universum.py","reports/stage14-stage13-replay.json","tests/test_stage14.py"):
 p=ROOT/rel
 if p.is_file(): report["source_sha256"][rel]=hashlib.sha256(p.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
out=ROOT/"build"/"stage14";out.mkdir(parents=True,exist_ok=True)
(out/"verification.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(report,indent=2,sort_keys=True))
sys.exit(0 if report["result"]=="PASS" else 1)
