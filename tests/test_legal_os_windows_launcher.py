"""Static guard for the Windows one-window LEGAL OS start script.

The historical version failed before launching Python because cmd.exe
interpreted parentheses in an ECHO within a parenthesized IF block.
No secret-dependent config is executed in this test.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "START-LUKART-LEGAL-OS.cmd"


class WindowsLauncherRegressionTests(unittest.TestCase):
    def test_batch_does_not_use_fragile_parenthesis_blocks(self):
        code = LAUNCHER.read_text(encoding="utf-8")
        self.assertNotIn("(", code)
        self.assertNotIn(")", code)
        self.assertIn("if not defined LUKART_TRUSTED_CONFIG goto missing_config", code)
        self.assertIn(':missing_config', code)
        self.assertIn("goto start_server", code)

    def test_launches_case_only_with_same_trusted_python_config(self):
        code = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn(r'.venv\Scripts\python.exe', code)
        self.assertIn("--port 8786 --legal-os", code)
        self.assertIn('--config "%LUKART_TRUSTED_CONFIG%"', code)
        self.assertNotIn("setx ", code.lower())
        self.assertNotIn("pip install", code.lower())


if __name__ == "__main__":
    unittest.main()
