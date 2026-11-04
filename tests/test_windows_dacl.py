import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_windows.dacl import WindowsDaclError, validate_acl_entries

WRITE = 0x00000002 | 0x00000004 | 0x00000010 | 0x00000100 | 0x00000040 | 0x00010000 | 0x00040000 | 0x00080000
SYSTEM = "S-1-5-18"
ADMINS = "S-1-5-32-544"
TRUSTED_INSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"


def ace(sid, rights=WRITE, kind="Allow", inherited=False):
    return {"sid": sid, "type": kind, "rights": rights, "inherited": inherited}


class WindowsDaclPolicyTests(unittest.TestCase):
    def test_only_trusted_windows_principals_may_write(self):
        validate_acl_entries(
            [ace(SYSTEM), ace(ADMINS), ace(TRUSTED_INSTALLER), ace("S-1-5-32-545", 0x1)],
            owner_sid=ADMINS,
        )
        validate_acl_entries(
            [ace(SYSTEM, inherited=True), ace(ADMINS, inherited=True)],
            owner_sid=SYSTEM,
        )

    def test_untrusted_allow_write_is_rejected(self):
        with self.assertRaisesRegex(WindowsDaclError, "UNTRUSTED_WRITE"):
            validate_acl_entries(
                [ace(SYSTEM), ace(ADMINS), ace("S-1-5-32-545")],
                owner_sid=ADMINS,
            )

    def test_untrusted_owner_is_rejected(self):
        with self.assertRaisesRegex(WindowsDaclError, "OWNER_UNTRUSTED"):
            validate_acl_entries(
                [ace(SYSTEM), ace(ADMINS)],
                owner_sid="S-1-5-21-1-2-3-1001",
            )

    def test_current_admin_owner_and_creator_owner_are_allowed(self):
        current_user = "S-1-5-21-1-2-3-1001"
        allowed = frozenset({SYSTEM, ADMINS, current_user})
        validate_acl_entries(
            [ace(SYSTEM), ace(ADMINS), ace(current_user), ace("S-1-3-0")],
            owner_sid=current_user,
            allowed_sids=allowed,
        )

    def test_missing_trusted_write_grant_is_rejected(self):
        with self.assertRaisesRegex(WindowsDaclError, "INCOMPLETE"):
            validate_acl_entries([ace(SYSTEM)], owner_sid=ADMINS)

    def test_trusted_and_broad_deny_are_rejected(self):
        for denied_sid in (SYSTEM, ADMINS, "S-1-1-0", "S-1-5-11", "S-1-5-32-545"):
            with self.subTest(denied_sid=denied_sid):
                with self.assertRaises(WindowsDaclError):
                    validate_acl_entries(
                        [ace(SYSTEM), ace(ADMINS), ace(denied_sid, kind="Deny")],
                        owner_sid=ADMINS,
                    )

    @unittest.skipUnless(os.name == "nt", "Windows trusted host boundary only")
    def test_trusted_host_module_checks_acl_before_execution(self):
        from examples.human_case_operator_host import trusted_module

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trusted_host.py"
            path.write_text("marker = 'loaded'\n", encoding="utf-8")
            with patch.dict(os.environ, {"LUKART_TRUSTED_CASE_HOST": str(path)}):
                with patch("examples.human_case_operator_host.verify_protected_file") as verifier:
                    module = trusted_module("LUKART_TRUSTED_CASE_HOST")
            self.assertEqual(module["marker"], "loaded")
            verifier.assert_called_once_with(path.resolve())
    def test_malformed_acl_is_rejected(self):
        for entries in (
            None,
            [],
            [None],
            [{"sid": SYSTEM, "type": "Allow", "rights": True, "inherited": False}],
        ):
            with self.subTest(entries=entries):
                with self.assertRaises(WindowsDaclError):
                    validate_acl_entries(entries, owner_sid=ADMINS)


if __name__ == "__main__":
    unittest.main()
