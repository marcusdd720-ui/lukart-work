"""Synthetic Stage 09 reproducibility and generated-artifact coverage."""
import hashlib
import json
from pathlib import Path
import unittest

from lukart_work.drafting.contracts import DraftingTerminalResult


ROOT = Path(__file__).resolve().parents[1]


class Stage09ReproducibilityTests(unittest.TestCase):
    def test_packaging_artifacts_are_excluded_from_manifest_inputs(self):
        source = (ROOT / 'scripts/refresh_manifest.py').read_text(encoding='utf-8')
        self.assertIn("'build/'", source)
        self.assertIn("'dist/'", source)
        self.assertIn("lukart_work_domain_contracts.egg-info/", source)

    def test_baseline_hash_normalizes_line_endings(self):
        lf_content = b"synthetic baseline\nline\n"
        crlf_content = lf_content.replace(b'\n', b'\r\n')
        expected = hashlib.sha256(lf_content).hexdigest()
        self.assertEqual(
            expected,
            hashlib.sha256(lf_content.replace(b'\r\n', b'\n')).hexdigest(),
        )
        self.assertEqual(
            expected,
            hashlib.sha256(crlf_content.replace(b'\r\n', b'\n')).hexdigest(),
        )

    def test_schema_ordering_uses_normalized_posix_paths(self):
        paths = [Path('schemas/z.json'), Path('schemas/a.json')]
        ordered = sorted(paths, key=lambda path: path.as_posix())
        self.assertEqual(
            [path.as_posix() for path in ordered],
            ['schemas/a.json', 'schemas/z.json'],
        )
        source = (ROOT / 'scripts/validate_stage09_schemas.py').read_text(
            encoding='utf-8'
        )
        self.assertIn('relative_to(ROOT).as_posix()', source)

    def test_terminal_result_schema_is_exported_and_versioned(self):
        path = ROOT / 'schemas/DraftingTerminalResult.schema.json'
        self.assertTrue(path.is_file())
        schema = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(
            schema['$id'],
            'urn:lukart:work:DraftingTerminalResult:1.0.0',
        )
        self.assertEqual(schema, {
            **DraftingTerminalResult.model_json_schema(),
            '$schema': schema['$schema'],
            '$id': schema['$id'],
        })
        package_source = (ROOT / 'verify_package.py').read_text(encoding='utf-8')
        export_source = (ROOT / 'export_contracts.py').read_text(encoding='utf-8')
        self.assertIn('DraftingTerminalResult', package_source)
        self.assertIn('DraftingTerminalResult', export_source)


if __name__ == '__main__':
    unittest.main()
