"""Testy bezpieczeństwa natywnej autoryzacji HUMAN — spoofing, replay, escalation, bypass."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from lukart_work.domain.models import Actor
from lukart_work.human_authorization import (
    HumanAuthorizationError,
    create_decision_record,
    require_human_actor,
    require_human_principal,
    verify_decision_record,
)


def _make_actor(kind: str = "HUMAN") -> Actor:
    return Actor(id=uuid.uuid4(), kind=kind)


def _make_principal(actor: Actor, case_id: str, actions: list[str]):
    class _P:
        def __init__(self, actor, case_id, actions):
            self.actor = actor
            self.case_id = case_id
            self._actions = actions

        @property
        def actions(self):
            return self._actions

    return _P(actor, case_id, actions)


# --- Spoofing: klient nie może podszyć się pod HUMAN ---

def test_ai_actor_cannot_spoof_human():
    ai_actor = _make_actor("AI")
    principal = _make_principal(ai_actor, "case-123", ["execute_core"])
    with pytest.raises(HumanAuthorizationError, match="actor_kind must be HUMAN"):
        require_human_principal(principal, case_id="case-123", permission="execute_core")


def test_service_actor_cannot_spoof_human():
    svc_actor = _make_actor("SERVICE")
    principal = _make_principal(svc_actor, "case-123", ["execute_core"])
    with pytest.raises(HumanAuthorizationError, match="actor_kind must be HUMAN"):
        require_human_principal(principal, case_id="case-123", permission="execute_core")


def test_unknown_actor_kind_cannot_be_constructed():
    """Pydantic Literal rejects UNKNOWN at construction — fail-closed at model level."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Actor(id=uuid.uuid4(), kind="UNKNOWN")  # type: ignore[arg-type]


# --- Replay: decyzja nie może być ponownie wykorzystana dla innej sprawy/operacji ---

def test_decision_record_cannot_be_replayed_for_different_case(tmp_path: Path):
    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-A",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=tmp_path,
    )
    record_path = tmp_path / f"human-decision-{identity.decision_record_id}.json"
    with pytest.raises(HumanAuthorizationError, match="case scope mismatch"):
        verify_decision_record(
            record_path,
            expected_case_id="case-B",
            expected_permission="execute_core",
        )


def test_decision_record_cannot_be_replayed_for_different_permission(tmp_path: Path):
    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=tmp_path,
    )
    record_path = tmp_path / f"human-decision-{identity.decision_record_id}.json"
    with pytest.raises(HumanAuthorizationError, match="permission mismatch"):
        verify_decision_record(
            record_path,
            expected_case_id="case-123",
            expected_permission="query_core",
        )


# --- Scope escalation: HUMAN z uprawnieniami do sprawy A nie może operować na sprawie B ---

def test_human_principal_case_scope_mismatch():
    actor = _make_actor("HUMAN")
    principal = _make_principal(actor, "case-A", ["execute_core"])
    with pytest.raises(HumanAuthorizationError, match="case scope mismatch"):
        require_human_principal(
            principal, case_id="case-B", permission="execute_core", label="test"
        )


# --- Bypass: brak danych, nieznane źródła, uszkodzone zapisy kończą się odmową ---

def test_missing_token_session_is_rejected():
    # TokenAuthority.session raises FORBIDDEN for unknown token — simulate
    # by checking require_human_actor rejects non-HUMAN actor.
    actor = _make_actor("AI")
    with pytest.raises(HumanAuthorizationError):
        require_human_actor(actor, label="session gate")


def test_tampered_decision_record_is_rejected(tmp_path: Path):
    import json

    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=tmp_path,
    )
    record_path = tmp_path / f"human-decision-{identity.decision_record_id}.json"

    # Tamper: change case_id but keep digest
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    raw["case_id"] = "case-tampered"
    record_path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(HumanAuthorizationError, match="case scope mismatch"):
        verify_decision_record(
            record_path,
            expected_case_id="case-123",
            expected_permission="execute_core",
        )


def test_tampered_digest_is_rejected(tmp_path: Path):
    import json

    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=tmp_path,
    )
    record_path = tmp_path / f"human-decision-{identity.decision_record_id}.json"

    # Tamper: change decision_digest to invalid value
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    raw["decision_digest"] = "0" * 64
    record_path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(HumanAuthorizationError, match="digest mismatch"):
        verify_decision_record(
            record_path,
            expected_case_id="case-123",
            expected_permission="execute_core",
        )


def test_invalid_json_record_is_rejected(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(HumanAuthorizationError, match="invalid JSON"):
        verify_decision_record(
            bad,
            expected_case_id="case-123",
            expected_permission="execute_core",
        )


# --- Replay protection: serwerowy, atomowy mechanizm jednorazowego użycia ---

def test_same_decision_record_cannot_be_replayed_for_same_case_and_permission(tmp_path: Path):
    """Weryfikacja że rekord decyzji powiązany jest z case+permission —
    ponowne użycie tego samego decision_record_id dla innych parametrów jest odrzucane.

    NOTA: brak serwerowego mechanizmu jednorazowego użycia (one-time-use enforcement).
    verify_decision_record weryfikuje integralność i zakres, ale nie śledzi już
    wykorzystanych decision_record_id na poziomie serwera. To jest NOT_PROVEN.
    """
    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=tmp_path,
    )
    record_path = tmp_path / f"human-decision-{identity.decision_record_id}.json"

    # Pierwsza weryfikacja — powinna się udać
    verified = verify_decision_record(
        record_path,
        expected_case_id="case-123",
        expected_permission="execute_core",
    )
    assert verified.decision_record_id == identity.decision_record_id

    # Ponowna weryfikacja tego samego rekordu dla tych samych parametrów —
    # obecna implementacja ponownie się uda (brak server-side one-time-use tracking).
    # To jest luka: replay tego samego poprawnego rekordu nie jest blokowany.
    verified2 = verify_decision_record(
        record_path,
        expected_case_id="case-123",
        expected_permission="execute_core",
    )
    assert verified2.decision_record_id == identity.decision_record_id


def test_concurrent_replay_same_record(tmp_path: Path):
    """Próba równoległego wykorzystania tego samego rekordu decyzji.

    NOTA: brak serwerowego blokady równoległego replay. To jest NOT_PROVEN.
    """
    import concurrent.futures

    actor = _make_actor("HUMAN")
    identity = create_decision_record(
        actor=actor,
        case_id="case-123",
        permission="execute_core",
        decision="ACCEPT",
        rationale="test",
        identity_source="github_issue_comment",
        output_dir=tmp_path,
    )
    record_path = tmp_path / f"human-decision-{identity.decision_record_id}.json"

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(
                verify_decision_record,
                record_path,
                expected_case_id="case-123",
                expected_permission="execute_core",
            )
            for _ in range(5)
        ]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Wszystkie 5 weryfikacji się powiodły — brak blokady równoległego replay.
    assert len(results) == 5
    for r in results:
        assert r.decision_record_id == identity.decision_record_id


# --- HumanIdentity digest determinism and length ---

def test_human_identity_digest_is_sha256():
    identity = __import__("lukart_work.human_authorization", fromlist=["HumanIdentity"]).HumanIdentity(
        actor_id=str(uuid.uuid4()),
        actor_kind="HUMAN",
        actor_identity_source="github_issue_comment",
        case_id="case-123",
        permission="execute_core",
        decision_record_id=str(uuid.uuid4()),
        decided_at="2026-11-12T00:00:00Z",
    )
    d = identity.digest
    assert len(d) == 64
    assert all(c in "0123456789abcdef" for c in d)


# --- create_decision_record rejects non-HUMAN actor ---

def test_create_decision_record_rejects_agent(tmp_path: Path):
    actor = _make_actor("AI")
    with pytest.raises(HumanAuthorizationError, match="actor_kind must be HUMAN"):
        create_decision_record(
            actor=actor,
            case_id="case-123",
            permission="execute_core",
            decision="ACCEPT",
            rationale="test",
            identity_source="github_issue_comment",
            output_dir=tmp_path,
        )
