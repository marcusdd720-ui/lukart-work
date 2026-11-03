import json
from datetime import date
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "pl-pre-payment-1.schema.json").read_text(encoding="utf-8"))
PROFILE = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
FIXTURE = json.loads((ROOT / "fixture.synthetic.json").read_text(encoding="utf-8"))

def validate(value):
    if not isinstance(value, dict) or set(value) != set(SCHEMA["required"]):
        raise ValueError("EXACT_REQUIRED_FIELDS")
    for key, spec in SCHEMA["properties"].items():
        if "const" in spec and value.get(key) != spec["const"]:
            raise ValueError("CONST:" + key)
    if not re.fullmatch(SCHEMA["properties"]["principal_amount_decimal"]["pattern"], value["principal_amount_decimal"]):
        raise ValueError("DECIMAL")
    for key in ("performance_due_date", "requested_payment_date_human"):
        date.fromisoformat(value[key])
    if not isinstance(value["payment_history"], list) or not value["payment_history"]:
        raise ValueError("PAYMENT_HISTORY")
    for item in value["payment_history"]:
        if set(item) != {"event", "date", "amount_decimal", "status"}:
            raise ValueError("PAYMENT_EVENT_FIELDS")
        date.fromisoformat(item["date"])
        if item["status"] not in {"paid", "unpaid", "reversed"}:
            raise ValueError("PAYMENT_STATUS")
        if not re.fullmatch(r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$", item["amount_decimal"]):
            raise ValueError("PAYMENT_AMOUNT")
    dest = value["payment_destination"]
    if set(dest) != {"destination_kind", "display_label"} or dest["destination_kind"] not in {"contractual_account_reference", "other_human_confirmed"}:
        raise ValueError("PAYMENT_DESTINATION")
    return True

class H5SyntheticPilotTests(unittest.TestCase):
    def test_profile_is_explicitly_unadmitted(self):
        self.assertEqual(PROFILE["status"], "REVIEW_ONLY_NOT_PRODUCT")
        self.assertEqual(PROFILE["product_support"], "NOT_SUPPORTED_FUTURE")
        self.assertEqual(PROFILE["execution"]["native_execute"], "BLOCKED")
        self.assertEqual(PROFILE["execution"]["read_package"], "BLOCKED")
        self.assertTrue(PROFILE["scope"]["synthetic_only"])
        self.assertFalse(PROFILE["scope"]["real_case_data"])
    def test_fixture_is_synthetic_and_valid(self):
        self.assertIn("SYNTHETIC", FIXTURE["claim_basis"])
        self.assertTrue(validate(FIXTURE))
    def test_missing_human_input_fails(self):
        bad = dict(FIXTURE); bad.pop("requested_payment_date_human")
        with self.assertRaises(ValueError): validate(bad)
    def test_unknown_field_fails(self):
        bad = dict(FIXTURE); bad["interest_amount"] = "0.00"
        with self.assertRaises(ValueError): validate(bad)
    def test_invalid_amount_fails(self):
        bad = dict(FIXTURE); bad["principal_amount_decimal"] = "1250"
        with self.assertRaises(ValueError): validate(bad)
    def test_invalid_currency_fails(self):
        bad = dict(FIXTURE); bad["currency_PLN"] = "EUR"
        with self.assertRaises(ValueError): validate(bad)
    def test_invalid_payment_status_fails(self):
        bad = json.loads(json.dumps(FIXTURE)); bad["payment_history"][0]["status"] = "maybe"
        with self.assertRaises(ValueError): validate(bad)
    def test_missing_payment_destination_fails(self):
        bad = dict(FIXTURE); bad["payment_destination"] = {}
        with self.assertRaises(ValueError): validate(bad)
    def test_no_positive_native_operations_are_authorized(self):
        self.assertEqual(PROFILE["execution"]["native_execute"], "BLOCKED")
        self.assertEqual(PROFILE["execution"]["read_package"], "BLOCKED")

if __name__ == "__main__":
    unittest.main()
