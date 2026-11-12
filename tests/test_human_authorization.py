"""Testy fail-closed natywnej autoryzacji HUMAN dla WORK."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lukart_work.domain.models import Actor
from lukart_work.human_authorization import (
    HumanAuthorizationError,
    HumanIdentity,
    create_decision_record,
    require_human_actor,
    require_human_principal,
    verify_decision_record,
)


def _make_actor(kind: str = "HUMAN") -> Actor:
    return Actor(id=uuid.uuid4(), kind=kind)


def test_require_human_actor_accepts_human() -> None:
    actor = _make_actor("HUMAN")
    require_human_actor(actor, label="test")


def test_require_human_actor_rejects_agent() -> None:
    actor = _make_actor("AI")
    with pytest.raises(HumanAuthorizationError, match="actor_kind must be HUMAN"):
        require_human_actor(actor, label="test")


def test_require_human_actor_rejects_service() -> None:
    actor = _make_actor("SERVICE")
    with pytest.raises(HumanAuthorizationError, match="actor_kind must be HUMAN"):
        require_human_actor(actor, label="test")


class _FakePrincipal:
    def __init__(self, actor: Actor, case_id: str, actions: list[str]) -> None:
        self.actor = actor
        self.case_id = case_id
        self._actions = actions

    @property
    def actions(self) -> list[str]:
        return self._actions


def test_require_human_principal_accepts_human_with_scope() -> None:
    actor = _make_actor("HUMAN")
    principal = _FakePrincipal(actor, "case-123", ["execute_core"])
    require_human_principal(
        principal, case_id="case-123", permission="execute_core", label="test"
    )


def test_require_human_principal_rejects_agent() -> None:
    actor = _make_actor("AI")
    principal = _FakePrincipal(actor, "case-123", ["execute_core"])
    with pytest.raises(HumanAuthorizationError, match="actor_kind must be HUMAN"):
        require_human_principal(
            principal, case_id="case-123", permission="execute_core", label="test"
        )


def test_require_human_principal_rejects_case_scope_mismatch() -> None:
    actor = _make_actor("HUMAN")
    principal = _FakePrincipal(actor, "case-123", ["execute_core"])
    with pytest.raises(HumanAuthorizationError, match="case scope mismatch"):
        require_human_principal(
            principal, case_id="case-999", permission="execute_core", label="test"
        )


def test_require_human_principal_rejects_missing_permission() -> None:
    actor = _make_actor("HUMAN")
    principal = _FakePrincipal(actor, "case-123", ["query_core"])
    with pytest.raises(HumanAuthorizationError, match="not granted"):
        require_human_principal(
            principal, case_id="case-123", permission="execute_core", label="test"
        )


def test_create_and_verify_decision_record(tmp_path: Path) -> None:
    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test decision",
        identity_source="github_issue_comment",
        output_dir=tmp_path,
    )

    assert identity.actor_kind == "HUMAN"
    assert identity.case_id == "case-123"
    assert identity.permission == "execute_core"
    assert len(identity.decision_record_id) > 0
    assert identity.decided_at.endswith("Z")

    files = list(tmp_path.glob("human-decision-*.json"))
    assert len(files) == 1

    verified = verify_decision_record(
        files[0],
        expected_case_id="case-123",
        expected_permission="execute_core",
        expected_actor_kind="HUMAN",
    )
    assert verified.decision_record_id == identity.decision_record_id
    assert verified.digest == identity.digest


def test_verify_decision_record_rejects_wrong_case() -> None:
    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=Path("/tmp/human_test_wrong_case"),
    )
    record_path = Path("/tmp/human_test_wrong_case") / f"human-decision-{identity.decision_record_id}.json"
    with pytest.raises(HumanAuthorizationError, match="case scope mismatch"):
        verify_decision_record(
            record_path,
            expected_case_id="case-999",
            expected_permission="execute_core",
        )


def test_verify_decision_record_rejects_wrong_permission() -> None:
    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=Path("/tmp/human_test_wrong_perm"),
    )
    record_path = Path("/tmp/human_test_wrong_perm") / f"human-decision-{identity.decision_record_id}.json"
    with pytest.raises(HumanAuthorizationError, match="permission mismatch"):
        verify_decision_record(
            record_path,
            expected_case_id="case-123",
            expected_permission="query_core",
        )


def test_create_decision_record_rejects_agent() -> None:
    actor = _make_actor("AI")
    with pytest.raises(HumanAuthorizationError, match="actor_kind must be HUMAN"):
        create_decision_record(
            actor=actor,
            case_id="case-123",
            permission="execute_core",
            decision="ACCEPT",
            rationale="test",
            identity_source="github_issue_comment",
            output_dir=Path("/tmp/human_test_agent"),
        )


def test_human_identity_digest_is_deterministic() -> None:
    identity = HumanIdentity(
        actor_id=str(uuid.uuid4()),
        actor_kind="HUMAN",
        actor_identity_source="github_issue_comment",
        case_id="case-123",
        permission="execute_core",
        decision_record_id=str(uuid.uuid4()),
        decided_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    d1 = identity.digest
    d2 = identity.digest
    assert d1 == d2
    assert len(d1) == 64
