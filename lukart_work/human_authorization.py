"""Fail-closed native HUMAN authorization for WORK CASE operations.

Rozróżnia aktorów HUMAN od technicznych (AGENT, SERVICE) i wymaga
jawnego powiązania decyzji z konkretną sprawą (case_id) i operacją (permission).
Wszystkie decyzje są zapisywane trwale z SHA-256 i pochodzeniem (actor_identity_source).

Ten moduł nie generuje fikcyjnych decyzji ani podpisów HUMAN.
Nie zastępuje niezależnej recenzji PB02/PB03.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# fcntl jest dostępne wyłącznie na platformach Unix-like (Linux CI runner).
# Na Windows moduł nie istnieje — import jest opóźniony do momentu pierwszego
# użycia, aby moduł mógł zostać zaimportowany i skompilowany także na Windows.
# Jeśli fcntl jest niedostępne, mark_decision_record_used i verify_decision_record
# kończą się błędem (fail-closed), co jest bezpieczniejsze niż cicha brak blokady.
try:  # pragma: no cover - platform-specific
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from lukart_work.domain.models import Actor


class HumanAuthorizationError(ValueError):
    """Fail-closed violation of HUMAN authorization boundary."""


class ActorKind(str):
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"
    AI = "AI"


@dataclass(frozen=True, slots=True)
class HumanIdentity:
    """Zweryfikowana tożsamość aktora HUMAN.

    actor_kind musi być "HUMAN" — SERVICE i AI są odrzucane fail-closed.
    actor_identity_source wskazuje źródło tożsamości (np. "github_issue_comment").
    decision_record_id to trwały, audytowalny zapis decyzji.
    artifact_id powiązuje decyzję z konkretnym artefaktem wyjściowym.
    """

    actor_id: str
    actor_kind: str
    actor_identity_source: str
    case_id: str
    permission: str
    decision_record_id: str
    decided_at: str
    artifact_id: str | None = None

    def canonical_dict(self) -> dict[str, object]:
        return {
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
            "actor_identity_source": self.actor_identity_source,
            "case_id": self.case_id,
            "permission": self.permission,
            "decision_record_id": self.decision_record_id,
            "decided_at": self.decided_at,
            "artifact_id": self.artifact_id,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.canonical_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()


def require_human_actor(actor: Actor, *, label: str = "HUMAN authorization") -> None:
    """Odrzuca fail-closed każdego aktora, który nie jest HUMAN.

    AGENT, SERVICE, AI i inne konta techniczne są odrzucane.
    Nie można podszyć się pod człowieka za pomocą tokena usługi.
    """
    if actor.kind != "HUMAN":
        raise HumanAuthorizationError(
            f"{label}: actor_kind must be HUMAN, got {actor.kind!r}"
        )


def require_human_principal(
    principal: Any,
    *,
    case_id: str,
    permission: str,
    artifact_id: str | None = None,
    label: str = "HUMAN authorization",
) -> None:
    """Wymaga, by Principal dotyczył konkretnej sprawy, operacji i opcjonalnie artefaktu,
    a jego aktor był HUMAN."""
    require_human_actor(principal.actor, label=label)
    if str(principal.case_id) != case_id:
        raise HumanAuthorizationError(
            f"{label}: case scope mismatch (expected {case_id}, "
            f"got {principal.case_id})"
        )
    if permission not in set(principal.actions):
        raise HumanAuthorizationError(
            f"{label}: permission {permission} not granted to actor {principal.actor.id}"
        )
    if artifact_id is not None:
        # artifact_id w Principal nie jest obecnie w modelu domenowym;
        # wiązanie artefaktu odbywa się na poziomie decisione record.
        pass


def _used_records_lock_path(output_dir: Path) -> Path:
    return output_dir / ".human-decision-used.lock"


def _used_records_path(output_dir: Path) -> Path:
    return output_dir / ".human-decision-used.json"


def _load_used_records(output_dir: Path) -> set[str]:
    """Wczytuje zbiór już wykorzystanych decision_record_id (serwerowy rejestr)."""
    path = _used_records_path(output_dir)
    if not path.is_file():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(value, dict):
        return set(value.get("used", []))
    return set()


def _save_used_records(output_dir: Path, used: set[str]) -> None:
    """Zapisuje rejestr wykorzystanych decision_record_id atomowo (temp + fsync + replace)."""
    path = _used_records_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps({"used": sorted(used)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # fsync pliku tymczasowego przed replace, aby dane trafiły na dysk
    with open(tmp_path, "rb") as fh:
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def mark_decision_record_used(
    output_dir: Path,
    decision_record_id: str,
    *,
    case_id: str,
    permission: str,
) -> None:
    """Atomowo oznacza decision_record_id jako wykorzystane (one-time-use enforcement).

    Raises HumanAuthorizationError jeśli rekord został już wykorzystany.
    """
    lock_path = _used_records_lock_path(output_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(lock_path, "a+")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        used = _load_used_records(output_dir)
        if decision_record_id in used:
            raise HumanAuthorizationError(
                f"decision record {decision_record_id} already used (one-time-use enforcement)"
            )
        used.add(decision_record_id)
        _save_used_records(output_dir, used)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


def is_decision_record_used(
    output_dir: Path,
    decision_record_id: str,
) -> bool:
    """Sprawdza czy decision_record_id został już wykorzystany."""
    used = _load_used_records(output_dir)
    return decision_record_id in used


def create_decision_record(
    *,
    actor: Actor,
    case_id: str,
    permission: str,
    decision: str,
    rationale: str,
    identity_source: str,
    output_dir: Path,
    artifact_id: str | None = None,
) -> HumanIdentity:
    """Tworzy trwały zapis decyzji HUMAN z SHA-256.

    Nie generuje fikcyjnej decyzji — caller musi przekazać rzeczywistą decyzję
    podjętą przez człowieka.
    """
    require_human_actor(actor, label="create_decision_record")

    decision_id = str(uuid.uuid4())
    decided_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    identity = HumanIdentity(
        actor_id=str(actor.id),
        actor_kind=actor.kind,
        actor_identity_source=identity_source,
        case_id=case_id,
        permission=permission,
        decision_record_id=decision_id,
        decided_at=decided_at,
        artifact_id=artifact_id,
    )

    record = {
        "schema": "lukart.human-decision-record.v1",
        "decision_record_id": decision_id,
        "actor_id": str(actor.id),
        "actor_kind": actor.kind,
        "actor_identity_source": identity_source,
        "case_id": case_id,
        "permission": permission,
        "decision": decision,
        "rationale": rationale,
        "decided_at": decided_at,
        "artifact_id": artifact_id,
        "decision_digest": identity.digest,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    record_path = output_dir / f"human-decision-{decision_id}.json"
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return identity


def verify_decision_record(
    record_path: Path,
    *,
    expected_case_id: str,
    expected_permission: str,
    expected_actor_kind: str = "HUMAN",
    expected_artifact_id: str | None = None,
    output_dir: Path | None = None,
    enforce_one_time_use: bool = True,
) -> HumanIdentity:
    """Weryfikuje trwały zapis decyzji HUMAN fail-closed.

    Jeśli enforce_one_time_use=True i output_dir podane, sprawdza serwerowy
    rejestr wykorzystanych decision_record_id i atomowo oznacza rekord jako
    wykorzystany po pomyślnej weryfikacji — wszystko pod jedną blokadą plikową,
    aby wyeliminować race condition między check a mark.
    """
    try:
        value = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HumanAuthorizationError(f"decision record is invalid JSON: {record_path}") from exc

    if not isinstance(value, dict):
        raise HumanAuthorizationError("decision record must be a JSON object")

    if value.get("schema") != "lukart.human-decision-record.v1":
        raise HumanAuthorizationError("unsupported decision record schema")

    if value.get("actor_kind") != expected_actor_kind:
        raise HumanAuthorizationError(
            f"decision record actor_kind must be {expected_actor_kind}, "
            f"got {value.get('actor_kind')!r}"
        )

    if value.get("case_id") != expected_case_id:
        raise HumanAuthorizationError("decision record case scope mismatch")

    if value.get("permission") != expected_permission:
        raise HumanAuthorizationError("decision record permission mismatch")

    if expected_artifact_id is not None:
        if value.get("artifact_id") != expected_artifact_id:
            raise HumanAuthorizationError("decision record artifact_id mismatch")

    decision_record_id = value.get("decision_record_id")
    if not isinstance(decision_record_id, str) or not decision_record_id:
        raise HumanAuthorizationError("decision record missing decision_record_id")

    # One-time-use enforcement: check+mark pod jedną blokadą — brak okna TOCTOU.
    if enforce_one_time_use and output_dir is not None:
        if fcntl is None:
            raise HumanAuthorizationError(
                "one-time-use enforcement unavailable: fcntl not supported on this platform"
            )
        lock_path = _used_records_lock_path(output_dir)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "a+")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)  # type: ignore[reportAttributeAccessIssue]
            used = _load_used_records(output_dir)
            if decision_record_id in used:
                raise HumanAuthorizationError(
                    f"decision record {decision_record_id} already used (one-time-use enforcement)"
                )
            used.add(decision_record_id)
            _save_used_records(output_dir, used)
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)  # type: ignore[reportAttributeAccessIssue]
            except OSError:
                pass
            lock_fd.close()

    identity = HumanIdentity(
        actor_id=str(value["actor_id"]),
        actor_kind=str(value["actor_kind"]),
        actor_identity_source=str(value["actor_identity_source"]),
        case_id=str(value["case_id"]),
        permission=str(value["permission"]),
        decision_record_id=str(value["decision_record_id"]),
        decided_at=str(value["decided_at"]),
        artifact_id=value.get("artifact_id"),
    )

    if identity.digest != value.get("decision_digest"):
        raise HumanAuthorizationError("decision record digest mismatch")

    return identity
