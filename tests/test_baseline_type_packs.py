from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import ValidationError

from lukart_work.type_packs.pl_pre_complaint_1 import (
    ADMISSION_STATUS as COMPLAINT_STATUS,
    TYPE_CONTRACT_PIN as COMPLAINT_PIN,
    TYPE_ID as COMPLAINT_ID,
    PLPreComplaint1Input,
    negative_payloads as complaint_negative_payloads,
    positive_fixture as complaint_positive_fixture,
)
from lukart_work.type_packs.pl_pre_payment_1 import (
    ADMISSION_STATUS as PAYMENT_STATUS,
    TYPE_CONTRACT_PIN as PAYMENT_PIN,
    TYPE_ID as PAYMENT_ID,
    PLPrePayment1Input,
    negative_payloads as payment_negative_payloads,
    positive_fixture as payment_positive_fixture,
)
from lukart_work.type_packs.pl_pre_reply_1 import (
    ADMISSION_STATUS as REPLY_STATUS,
    TYPE_CONTRACT_PIN as REPLY_PIN,
    TYPE_ID as REPLY_ID,
    PLPreReply1Input,
    negative_payloads as reply_negative_payloads,
    positive_fixture as reply_positive_fixture,
)


ROOT = Path(__file__).resolve().parents[1]


class BaselineTypePackTests(unittest.TestCase):
    def test_all_three_type_packs_exist_in_canonical_package(self) -> None:
        for package in (
            "pl_pre_payment_1",
            "pl_pre_complaint_1",
            "pl_pre_reply_1",
        ):
            base = ROOT / "lukart_work" / "type_packs" / package
            self.assertTrue((base / "__init__.py").is_file())
            self.assertTrue((base / "contract.py").is_file())
            self.assertTrue((base / "fixture.py").is_file())
            self.assertTrue((base / "negative_cases.py").is_file())

    def test_legacy_broken_pack_paths_are_absent(self) -> None:
        self.assertFalse((ROOT / "luart_work" / "types" / "payment_type.py").exists())
        self.assertFalse((ROOT / "types" / "pl-pre-reply-1").exists())

    def test_type_identity_and_admission_are_fail_closed(self) -> None:
        self.assertEqual("PL-PRE-PAYMENT-1", PAYMENT_ID)
        self.assertEqual("PL-PRE-COMPLAINT-1", COMPLAINT_ID)
        self.assertEqual("PL-PRE-REPLY-1", REPLY_ID)
        self.assertEqual("NOT_ADMITTED", PAYMENT_STATUS)
        self.assertEqual("NOT_ADMITTED", COMPLAINT_STATUS)
        self.assertEqual("NOT_ADMITTED", REPLY_STATUS)

    def test_contract_pins_are_stable_sha256_and_distinct(self) -> None:
        pins = {PAYMENT_PIN, COMPLAINT_PIN, REPLY_PIN}
        self.assertEqual(3, len(pins))
        for pin in pins:
            self.assertEqual(64, len(pin))
            int(pin, 16)

    def test_positive_fixtures_validate(self) -> None:
        self.assertIsInstance(payment_positive_fixture(), PLPrePayment1Input)
        self.assertIsInstance(complaint_positive_fixture(), PLPreComplaint1Input)
        self.assertIsInstance(reply_positive_fixture(), PLPreReply1Input)

    def test_invalid_dates_and_unknown_timezone_fail_closed(self) -> None:
        profiles = (
            (PLPrePayment1Input, payment_positive_fixture, "performance_due_date_iso"),
            (PLPreComplaint1Input, complaint_positive_fixture, "performance_date_iso"),
            (PLPreReply1Input, reply_positive_fixture, "incoming_demand_date_iso"),
        )
        for model, positive, specific_date in profiles:
            fixture = positive().model_dump(mode="json")
            for field in ("evaluation_date_iso", "document_date_iso", specific_date):
                for bad in ("2026-02-30", "2026-1-2", "tomorrow"):
                    with self.subTest(model=model.__name__, field=field, bad=bad):
                        with self.assertRaises(ValidationError):
                            model.model_validate({**fixture, field: bad})
            with self.subTest(model=model.__name__, field="evaluation_timezone"):
                with self.assertRaises(ValidationError):
                    model.model_validate({**fixture, "evaluation_timezone": "Not/A_Timezone"})

    def test_negative_fixtures_fail_closed(self) -> None:
        cases = (
            (PLPrePayment1Input, payment_negative_payloads()),
            (PLPreComplaint1Input, complaint_negative_payloads()),
            (PLPreReply1Input, reply_negative_payloads()),
        )
        for model, payloads in cases:
            self.assertGreaterEqual(len(payloads), 4)
            for name, payload in payloads:
                with self.subTest(model=model.__name__, case=name):
                    with self.assertRaises(ValidationError):
                        model.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
