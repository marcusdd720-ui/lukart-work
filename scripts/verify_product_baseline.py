"""LW-PB-01 evidence runner; missing integration or E2E can never become PASS.

Default: contract + current denial diagnostics + real PostgreSQL denial tests.
--portable: explicitly limited contract/diagnostic evidence, never admission.
--product-e2e: the requested full acceptance is currently unimplemented: exit 1.
No writes to production code, domain state or historical reports.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def source_text_bytes(data):
    """Repository source identity profile only; never apply to document artifact bytes."""
    return data.replace(b'\r\n', b'\n')


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable', action='store_true')
    parser.add_argument('--product-e2e', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/pb01')
    args = parser.parse_args(argv)
    from tests import test_product_baseline as tests
    contract_raw = tests.CONTRACT.read_bytes()
    contract_bytes = source_text_bytes(contract_raw)
    contract = json.loads(contract_bytes)
    tests.validate_contract(contract)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != contract['base_sha']:
        ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', contract['base_sha'], head], cwd=ROOT)
        if ancestor.returncode:
            raise SystemExit('BASE_CHANGED_REBASE_REQUIRED')
    source_names = ['acceptance/product-baseline-v1.json', 'docs/PRODUCT_BASELINE_1.md',
                    'tests/test_product_baseline.py', 'scripts/verify_product_baseline.py']
    report = {
        'scope': 'LW-PB-01', 'repository': contract['repository'], 'base_sha': contract['base_sha'],
        'head_sha': head, 'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
        'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
        'contract_sha256': sha256(contract_bytes).hexdigest(),
        'hash_profile': 'Source UTF-8 bytes, CRLF normalized to LF; Git blobs separately verified',
        'contract_raw_sha256': sha256(contract_raw).hexdigest(),
        'source_sha256': {name: sha256(source_text_bytes((ROOT / name).read_bytes())).hexdigest() for name in source_names},
        'source_raw_sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in source_names},
        'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
        'independent_review': 'NOT_VERIFIED', 'certification': 'NOT_VERIFIED',
        'product_e2e': 'BLOCKED', 'blocked_requirements': ['PB-017', 'PB-018', 'PB-019', 'PB-020', 'PB-021'],
        'evidence_kind': 'BUILDER_LOCAL',
    }
    report['candidate_sha'] = None if report['working_tree_dirty'] else head
    logs = []
    if args.product_e2e:
        report.update(result='BLOCKED', mode='PRODUCT_E2E', reason=contract['product_e2e']['reason'])
        code = 1
    else:
        groups = [('contract', tests.ContractTests), ('public_denials_memory_port', tests.PublicGateTests)]
        if not args.portable:
            groups.append(('postgresql_denials', tests.PostgreSQLGateTests))
        report['groups'] = {}
        for name, cls in groups:
            stream = io.StringIO()
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
            logs.append(stream.getvalue())
            report['groups'][name] = {'tests': result.testsRun, 'failures': len(result.failures),
                                     'errors': len(result.errors), 'skipped': len(result.skipped),
                                     'result': 'PASS' if result.wasSuccessful() and not result.skipped else 'FAIL'}
        report['postgresql'] = 'NOT_VERIFIED' if args.portable or report['groups']['postgresql_denials']['result'] != 'PASS' else 'VALIDATED_LOCAL'
        passed = all(group['result'] == 'PASS' for group in report['groups'].values())
        report['mode'] = 'PORTABLE_LIMITED' if args.portable else 'LW-PB-01'
        report['result'] = 'PASS_LIMITED' if args.portable and passed else ('READY_FOR_INDEPENDENT_REVIEW' if passed else 'BLOCKED')
        code = 0 if passed else 1
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'test-output.txt').write_text('\n'.join(logs), encoding='utf-8')
    (args.output / 'status.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('\n'.join(logs))
    print(json.dumps(report, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(run())
