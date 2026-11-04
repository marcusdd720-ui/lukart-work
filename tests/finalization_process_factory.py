"""Test-only deterministic CASE fixture and fresh-process PB02/PB03 bootstrap.

The fixture uses disposable synthetic PostgreSQL only. Each server process
reconstructs the same Principal, creates a new TokenAuthority, and provisions
new in-memory tokens. Tokens are returned only over the parent's private pipe.
"""
from __future__ import annotations

import json
import os
import sys
from hashlib import sha1, sha256
from uuid import UUID, uuid4, uuid5

from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor
from lukart_work.finalization.contracts import (
    FinalizationProfile,
    FinalPackageProfile,
    semantic_profile_pin,
)
from lukart_work.operator import GeneratorPismOperator
from lukart_work.operator_host import create_server
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
from lukart_work.storage.objects import RetentionPolicies
from lukart_work.contracts.messages import CommandResult
from tests import test_stage02 as core
from tests.test_stage09 import SyntheticProvider
from tests.test_finalization import FinalizationTests

TENANT_ID = UUID("1a0c8c2e-8e16-4c18-9a91-2eae9d3c1001")
CASE_ID = UUID("2b1d9d3f-9f27-4d29-a3b2-3fbf9d4c2002")
ACTOR_ID = UUID("3c2eae40-a038-4e3a-b4c3-4c0c0e5d3003")
FOREIGN_CASE_ID = uuid5(CASE_ID, "foreign-case-process-restart-test")
CRASH_EXIT_CODE = 86


def _dsn() -> str:
    if not core.DSN or not core.ADMIN_RUNTIME:
        raise RuntimeError("ISOLATED_POSTGRESQL_REQUIRED")
    return core.DSN


def seed_fixture(tested_sha: str):
    """Create one stable synthetic CASE and a validated draft in PostgreSQL."""
    _dsn()
    if len(tested_sha) != 40 or any(c not in "0123456789abcdef" for c in tested_sha):
        raise ValueError("EXACT_TESTED_SHA_REQUIRED")

    fixed = iter((TENANT_ID, CASE_ID, ACTOR_ID))
    original_uuid4 = core.uuid4

    def stable_principal_uuid():
        try:
            return next(fixed)
        except StopIteration:
            return original_uuid4()

    FinalizationTests.setUpClass()
    fixture = FinalizationTests("test_public_happy_path_persists_exact_bytes_approval_and_release_chain")
    # Only the first three UUID allocations in Stage02 setUp are fixed:
    # tenant, case and actor. Command/idempotency/correlation IDs remain unique.
    from unittest.mock import patch
    with patch.object(core, "uuid4", stable_principal_uuid):
        fixture.setUp()

    if (fixture.tenant, fixture.case_id, fixture.actor.id) != (TENANT_ID, CASE_ID, ACTOR_ID):
        raise RuntimeError("STABLE_SYNTHETIC_PRINCIPAL_MISMATCH")
    if fixture.actor.kind != "HUMAN":
        raise RuntimeError("SYNTHETIC_HUMAN_KIND_REQUIRED")

    draft, validation_run_id = fixture.validated()
    fixture.package_profile = fixture.package_profile.model_copy(update={"build_revision": tested_sha})
    render_request = fixture.final_request(
        "RenderDraft",
        draft,
        validation_run_id=str(validation_run_id),
        semantic_profile=semantic_profile_pin(fixture.final_profile).model_dump(mode="json"),
    )
    render_id = uuid5(UUID(render_request["meta"]["command_id"]), "persisted-render")

    payload = {
        "tested_sha": tested_sha,
        "tenant_id": str(TENANT_ID),
        "case_id": str(CASE_ID),
        "actor_id": str(ACTOR_ID),
        "actor_kind": "HUMAN",
        "actions": sorted(fixture.principal.actions),
        "case_profile": fixture.final_profile.model_dump(mode="json"),
        "drafting_profile": fixture.profile,
        "package_profile": fixture.package_profile.model_dump(mode="json"),
        "render_request": render_request,
        "render_id": str(render_id),
        "draft_ref": draft.model_dump(mode="json"),
        "validation_run_id": str(validation_run_id),
        "seed_case_sequence": fixture.sequence,
    }
    # Prove the complete bootstrap descriptor is JSON-serializable before
    # sending it to a child process. It contains no token or credential.
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return fixture, payload


def build_child_runtime(payload: dict, *, crash_operation: str | None = None):
    """Create a fresh operator, authority and loopback server in this process."""
    _dsn()
    tenant_id = UUID(payload["tenant_id"])
    case_id = UUID(payload["case_id"])
    actor = Actor(id=UUID(payload["actor_id"]), kind=payload["actor_kind"])
    actions = frozenset(payload["actions"])
    principal = Principal(actor, tenant_id, case_id, actions)

    authority = TokenAuthority()
    token = authority.provision(principal)
    foreign_principal = Principal(actor, tenant_id, FOREIGN_CASE_ID, actions)
    foreign_token = authority.provision(foreign_principal)

    repository = PostgresRepository(
        core.DSN, storage=True, retention_policies=RetentionPolicies()
    )
    case_profile = FinalizationProfile.model_validate(payload["case_profile"])
    package_profile = FinalPackageProfile.model_validate(payload["package_profile"])
    operator = GeneratorPismOperator(
        repository=repository,
        authority=authority,
        case_profile=case_profile,
        drafting_profiles={"QUICK": payload["drafting_profile"]},
        provider=SyntheticProvider(),
        package_profile=package_profile,
    )

    if crash_operation is not None:
        if crash_operation not in {"RenderDraft", "AssembleFinalPackage"}:
            raise ValueError("UNSUPPORTED_TEST_CRASH_POINT")
        original = operator.execute_finalization

        def execute_with_crash(request, supplied_token):
            result = original(request, supplied_token)
            operation = request.get("operation") if isinstance(request, dict) else None
            if (
                operation == crash_operation
                and isinstance(result, CommandResult)
                and result.state == "APPLIED"
            ):
                # execute() has returned only after its PostgreSQL transaction
                # committed. Terminate the OS process before HTTP reply().
                os._exit(CRASH_EXIT_CODE)
            return result

        operator.execute_finalization = execute_with_crash

    server = create_server(operator, port=0)
    return server, token, foreign_token, repository


def child_main() -> int:
    """Child entry point. stdout is a private in-memory parent/child pipe."""
    try:
        payload = json.load(sys.stdin)
        crash_operation = payload.pop("_crash_operation", None)
        server, token, foreign_token, _repository = build_child_runtime(
            payload, crash_operation=crash_operation
        )
        # Never print these tokens to a terminal or log. The parent captures
        # this single line directly in memory from subprocess.PIPE.
        sys.stdout.write(json.dumps({
            "pid": os.getpid(),
            "port": server.server_port,
            "token": token,
            "foreign_token": foreign_token,
        }) + "\n")
        sys.stdout.flush()
        server.serve_forever(poll_interval=0.05)
        server.server_close()
        return 0
    except BaseException:
        # Do not include request bodies, DSNs, principals or tokens in stderr.
        sys.stderr.write("PROCESS_RESTART_CHILD_BOOTSTRAP_FAILED\n")
        sys.stderr.flush()
        return 70


if __name__ == "__main__" and "--child" in sys.argv:
    raise SystemExit(child_main())
