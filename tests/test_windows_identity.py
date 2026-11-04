import base64,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from lukart_work.core.security import TokenAuthority
from lukart_work.validation.rules import Violation
from native_windows.windows_identity import (
    WindowsHumanAuthManager,
    WindowsHumanIdentityPolicy,
    WindowsIdentityError,
)

SID = "S-1-5-21-1-2-3-1001"


def doc(actions=None, enabled=True):
    return {
        "schema": "urn:lukart:work:WindowsHumanIdentityPolicy:1.0.0",
        "policy_id": "TEST",
        "session_ttl_seconds": 60,
        "principals": [{
            "sid": SID,
            "actor_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "case_id": str(uuid4()),
            "actions": actions or ["GetCaseHead"],
            "enabled": enabled,
        }],
    }


def parse_policy(path):
    # Parser/handshake tests use synthetic temporary files. The independent
    # DACL policy is exercised in tests.test_windows_dacl and the native
    # Windows integration test.
    with patch("native_windows.windows_identity.verify_protected_file"):
        return WindowsHumanIdentityPolicy.from_path(path)


def load(document):
    td = tempfile.TemporaryDirectory()
    path = Path(td.name) / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return td, parse_policy(path)


class FakeContext:
    def __init__(self):
        self.complete = False
        self.client_principal = "TESTDOMAIN\\operator"

    def step(self, token):
        if token == b"c1":
            return b"s1"
        if token == b"c2":
            self.complete = True
            return None
        raise ValueError("bad")


class PolicyTests(unittest.TestCase):
    def test_exact_sid_maps_to_human_case_scope(self):
        td, policy = load(doc(["GetCaseHead", "GetRevision"]))
        self.addCleanup(td.cleanup)
        principal = policy.resolve_sid(SID)
        self.assertEqual(principal.actor.kind, "HUMAN")
        self.assertEqual(principal.actions, frozenset({"GetCaseHead", "GetRevision"}))
        self.assertEqual(len(policy.digest), 64)

    def test_unknown_disabled_wildcard_duplicate_fail_closed(self):
        td, policy = load(doc(enabled=False))
        self.addCleanup(td.cleanup)
        with self.assertRaises(WindowsIdentityError):
            policy.resolve_sid(SID)
        with self.assertRaises(WindowsIdentityError):
            policy.resolve_sid("S-1-5-21-1-2-3-9")

        td2 = tempfile.TemporaryDirectory()
        self.addCleanup(td2.cleanup)
        path = Path(td2.name) / "policy.json"
        path.write_text(json.dumps(doc(["*"])), encoding="utf-8")
        with self.assertRaises(WindowsIdentityError):
            parse_policy(path)
        duplicate = doc()
        duplicate["principals"].append(duplicate["principals"][0])
        path.write_text(json.dumps(duplicate), encoding="utf-8")
        with self.assertRaises(WindowsIdentityError):
            parse_policy(path)

    def test_boolean_ttl_unknown_field_and_relative_path_rejected(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        path = Path(td.name) / "policy.json"
        for document in ({**doc(), "session_ttl_seconds": True}, {**doc(), "unexpected": 1}):
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(WindowsIdentityError):
                parse_policy(path)
        with self.assertRaises(WindowsIdentityError):
            parse_policy(Path("relative.json"))


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.td, self.policy = load(doc())
        self.addCleanup(self.td.cleanup)
        self.authority = TokenAuthority()
        self.manager = WindowsHumanAuthManager(
            self.authority,
            self.policy,
            context_factory=FakeContext,
            sid_resolver=lambda _account: SID,
        )
        self.addCleanup(self.manager.close)

    def handshake(self, manager=None):
        manager = manager or self.manager
        first = manager.authenticate(session_token=None, handshake_id=None, authorization=None)
        second = manager.authenticate(
            session_token=None,
            handshake_id=first.handshake_id,
            authorization="Negotiate " + base64.b64encode(b"c1").decode(),
        )
        third = manager.authenticate(
            session_token=None,
            handshake_id=second.handshake_id,
            authorization="Negotiate " + base64.b64encode(b"c2").decode(),
        )
        self.assertEqual((first.state, second.state, third.state), ("CHALLENGE", "CONTINUE", "AUTHENTICATED"))
        return third.session_token

    def test_human_capability_has_exact_case_scope(self):
        token = self.handshake()
        with self.authority.session(token) as principal:
            self.assertEqual(principal.actor.kind, "HUMAN")
            self.assertEqual(principal.actions, frozenset({"GetCaseHead"}))
        self.assertEqual(
            self.manager.authenticate(session_token=token, handshake_id=None, authorization=None).state,
            "AUTHENTICATED",
        )

    def test_malformed_token_denied(self):
        first = self.manager.authenticate(session_token=None, handshake_id=None, authorization=None)
        result = self.manager.authenticate(
            session_token=None,
            handshake_id=first.handshake_id,
            authorization="Negotiate !!!",
        )
        self.assertEqual(result.state, "DENIED")

    def test_expired_session_revoked(self):
        now = [0.0]
        manager = WindowsHumanAuthManager(
            self.authority,
            self.policy,
            context_factory=FakeContext,
            sid_resolver=lambda _account: SID,
            clock=lambda: now[0],
        )
        self.addCleanup(manager.close)
        token = self.handshake(manager)
        now[0] = 61
        self.assertEqual(
            manager.authenticate(session_token=token, handshake_id=None, authorization=None).state,
            "CHALLENGE",
        )
        with self.assertRaises(Violation):
            with self.authority.session(token):
                pass

    def test_close_revokes_token(self):
        token = self.handshake()
        self.manager.close()
        with self.assertRaises(Violation):
            with self.authority.session(token):
                pass


if __name__ == "__main__":
    unittest.main()
