"""Rejected catalogue removal contract."""
import importlib.util
import unittest
from pathlib import Path
from lukart_work.type_packs.runtime import RUNTIME_PROFILES, finalization_profiles, runtime_profile

class BaselineTypePackTests(unittest.TestCase):
    def test_rejected_packages_are_absent(self):
        for name in ("pl_pre_payment_1", "pl_pre_complaint_1", "pl_pre_reply_1"):
            self.assertIsNone(importlib.util.find_spec("lukart_work.type_packs." + name))
            self.assertFalse((Path(__file__).resolve().parents[1] / "lukart_work/type_packs" / name).exists())

    def test_no_implicit_replacement_registration(self):
        self.assertEqual(RUNTIME_PROFILES, ())
        self.assertEqual(finalization_profiles(), ())
        for value in ("PL-PRE-PAYMENT-1", "PL-PRE-COMPLAINT-1", "PL-PRE-REPLY-1", None):
            with self.assertRaisesRegex(ValueError, "UNSUPPORTED_DOCUMENT_TYPE"):
                runtime_profile(value)
