"""Exact-SHA, zero-skip OCR acceptance against an explicitly disposable database."""
import argparse
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from psycopg.conninfo import conninfo_to_dict
    from lukart_work.ingestion.ocr import OCRConfig
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tessdata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if os.environ.get('TESTED_SHA') != sha:
        raise SystemExit('EXACT_TESTED_SHA_REQUIRED')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise SystemExit('CLEAN_CHECKOUT_REQUIRED')
    destinations = [conninfo_to_dict(os.environ[key]).get('dbname', '')
                    for key in ('LUKART_TEST_DSN', 'LUKART_TEST_ADMIN_DSN')]
    if len(set(destinations)) != 1 or not destinations[0].startswith('lukart_ocr_acceptance_'):
        raise SystemExit('DISPOSABLE_OCR_DATABASE_REQUIRED')
    config = OCRConfig(str(Path(shutil.which('tesseract') or '').resolve()),
        str(args.tessdata.resolve()), str(Path(shutil.which('pdftoppm') or '').resolve()))
    pin = config.pin()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    config_path = output / 'ocr-config.json'
    config_path.write_text(json.dumps(config.payload()), encoding='utf-8')
    os.environ['LUKART_OCR_TEST_CONFIG'] = str(config_path)
    paths = [p for folder in ('lukart_work', 'tests', 'scripts') for p in (ROOT/folder).rglob('*')
             if p.suffix in ('.py', '.sql', '.js') and '__pycache__' not in p.parts]
    paths += [ROOT/'pyproject.toml', ROOT/'schemas/IngestionResult.schema.json']
    def sources():
        return {p.relative_to(ROOT).as_posix():sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                for p in sorted(paths)}
    before = sources()
    names = ['tests.ocr_intake_acceptance', 'tests.test_stage04',
        'tests.test_stage05.FactEvidenceTests.test_golden_explicit_admission_and_confirmation_preserve_history',
        'tests.test_stage05.FactEvidenceTests.test_wrong_pin_index_kind_scope_and_missing_source_fail_closed',
        'tests.test_stage05.FactEvidenceTests.test_no_implicit_approval_and_forbidden_status_injection',
        'tests.test_operator_host.OperatorBrowserContractTests',
        'tests.test_operator_host.OperatorGuidedCaseUIContractTests']
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames(names))
    log = stream.getvalue()
    (output/'tests.log').write_text(log, encoding='utf-8')
    unchanged = before == sources()
    passed = result.wasSuccessful() and not result.skipped and unchanged
    report = dict(tested_sha=sha, result='PASS' if passed else 'FAIL', synthetic_only=True,
        actual_human_acceptance=False, final_approval=False, tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        sources_unchanged=unchanged, tested_sources=before, ocr_engine=pin.model_dump(mode='json'))
    (output/'status.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(log)
    print(json.dumps({k:v for k,v in report.items() if k!='tested_sources'}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
