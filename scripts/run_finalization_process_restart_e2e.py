"""PB02/PB03 synthetic OS-process crash/restart/replay acceptance harness."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from http.client import HTTPConnection, HTTPException
from io import BytesIO
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
from threading import Thread
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lukart_work.contracts.messages import CommandResult
from lukart_work.core.postgres import PostgresRepository
from lukart_work.finalization.contracts import (
    FINAL_PACKAGE_MEMBER_NAMES,
    FinalizationApproval,
    FinalizationRelease,
    FinalPackageRecord,
    PersistedRender,
)
from lukart_work.finalization.service import (
    APPROVAL_CATEGORY,
    PACKAGE_CATEGORY,
    RELEASE_CATEGORY,
    RENDER_CATEGORY,
)
from lukart_work.storage.objects import RetentionPolicies
from tests import test_stage02 as core
from tests.finalization_process_factory import (
    CRASH_EXIT_CODE,
    seed_fixture,
)

def require(condition, label):
    if not condition:
        raise AssertionError(label)

def current_sha():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(len(head) == 40 and all(c in "0123456789abcdef" for c in head), "INVALID_CHECKOUT_SHA")
    require(not os.environ.get("TESTED_SHA") or os.environ["TESTED_SHA"] == head, "TESTED_SHA_MISMATCH")
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip(),
            "DIRTY_CHECKOUT")
    return head

class ServerProcess:
    def __init__(self, payload, crash_operation=None):
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-X", "utf8", "-m", "tests.finalization_process_factory", "--child"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        child_payload = dict(payload)
        if crash_operation is not None:
            child_payload["_crash_operation"] = crash_operation
        self.process.stdin.write(json.dumps(child_payload, ensure_ascii=False, allow_nan=False))
        self.process.stdin.close()
        ready_queue = queue.Queue(maxsize=1)

        def read_ready():
            ready_queue.put(self.process.stdout.readline())

        Thread(target=read_ready, daemon=True).start()
        try:
            line = ready_queue.get(timeout=45)
        except queue.Empty as exc:
            self.stop()
            raise RuntimeError("CHILD_START_TIMEOUT") from exc
        if not line:
            stderr = self.process.stderr.read()
            raise RuntimeError("CHILD_START_FAILED:" + (stderr.strip() or "NO_CHILD_OUTPUT"))
        self.control = json.loads(line)
        self.pid = self.control["pid"]
        self.port = self.control["port"]
        self.token = self.control["token"]
        self.foreign_token = self.control["foreign_token"]
        require(self.pid != os.getpid(), "CHILD_MUST_HAVE_DISTINCT_OS_PID")
        require(self.token and self.foreign_token and self.token != self.foreign_token,
                "FRESH_PRIVATE_TOKENS_REQUIRED")

    def post(self, route, payload, token=None, *, binary=False):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            connection.request(
                "POST", "/api/" + route, body=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + (token or self.token),
                    "Origin": f"http://127.0.0.1:{self.port}",
                    "Sec-Fetch-Site": "same-origin",
                },
            )
            response = connection.getresponse()
            data = response.read()
            headers = {key.lower(): value for key, value in response.getheaders()}
            require(response.status == 200, "HTTP_" + route.upper() + "_STATUS_" + str(response.status))
            if binary:
                require(headers.get("content-type") == "application/octet-stream",
                        "BINARY_CONTENT_TYPE_REQUIRED")
                return data, headers
            require(headers.get("content-type") == "application/json",
                    "JSON_CONTENT_TYPE_REQUIRED")
            return json.loads(data.decode("utf-8"))
        finally:
            connection.close()

    def expect_crash_after_commit(self, route, payload):
        observed_transport_failure = False
        try:
            self.post(route, payload)
        except (OSError, HTTPException, TimeoutError):
            observed_transport_failure = True
        require(observed_transport_failure, "CRASH_MUST_INTERRUPT_HTTP_RESPONSE")
        code = self.process.wait(timeout=30)
        require(code == CRASH_EXIT_CODE, "CHILD_DID_NOT_EXIT_AT_INJECTED_POST_COMMIT_CRASH")
        return code

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass

def database_snapshot(payload):
    repository = PostgresRepository(
        core.DSN, storage=True, retention_policies=RetentionPolicies()
    )
    tenant_id, case_id = UUID(payload["tenant_id"]), UUID(payload["case_id"])
    render_id = UUID(payload["render_id"])
    with repository.transaction(tenant_id, case_id) as tx:
        events, outbox = tx.events(), tx.outbox()
        renders = tx.objects(RENDER_CATEGORY, PersistedRender)
        approvals = tx.objects(APPROVAL_CATEGORY, FinalizationApproval)
        releases = tx.objects(RELEASE_CATEGORY, FinalizationRelease)
        packages = tx.objects(PACKAGE_CATEGORY, FinalPackageRecord)
        render = next((item for item in renders if item.id == render_id), None)
        approval = next((item for item in approvals if item.render_id == render_id), None)
        release = next((item for item in releases if item.render_id == render_id), None)
        package = next((item for item in packages if item.render_id == render_id), None)
        return {
            "sequence": tx.sequence(),
            "event_ids": tuple(item.audit.event_id for item in events),
            "outbox_ids": tuple(item.audit.event_id for item in outbox),
            "events_equal_outbox": events == outbox,
            "audit_inventory": tx.audit_inventory(),
            "operations": tuple(
                (name, sum(1 for event in events if event.audit.operation == name))
                for name in ("RenderDraft", "ApproveFinalDocument",
                             "RequestFinalRelease", "AssembleFinalPackage")
            ),
            "render_count": len(renders),
            "approval_count": len(approvals),
            "release_count": len(releases),
            "package_count": len(packages),
            "render": render,
            "approval": approval,
            "release": release,
            "package": package,
        }

def command_result(value):
    require(isinstance(value, dict) and value.get("state") == "APPLIED",
            "EXPECTED_APPLIED_COMMAND_RESULT")
    return CommandResult.model_validate_json(json.dumps(value, ensure_ascii=False, allow_nan=False))

def error_code(value):
    require(isinstance(value, dict) and isinstance(value.get("code"), str),
            "EXPECTED_DOMAIN_ERROR")
    return value["code"]

def read_member(server, payload, render_id, member):
    return server.post("query_finalization", {
        "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
        "operation": "ReadFinalPackageMember",
        "tenant_id": payload["tenant_id"],
        "case_id": payload["case_id"],
        "render_id": render_id,
        "member": member,
    }, binary=True)

def run():
    tested_sha = current_sha()
    fixture, payload = seed_fixture(tested_sha)
    render_request = payload["render_request"]
    render_id = payload["render_id"]
    require(payload["tenant_id"] == "1a0c8c2e-8e16-4c18-9a91-2eae9d3c1001", "TENANT_ID_NOT_STABLE")
    require(payload["case_id"] == "2b1d9d3f-9f27-4d29-a3b2-3fbf9d4c2002", "CASE_ID_NOT_STABLE")
    require(payload["actor_id"] == "3c2eae40-a038-4e3a-b4c3-4c0c0e5d3003", "ACTOR_ID_NOT_STABLE")
    require(payload["actor_kind"] == "HUMAN", "SYNTHETIC_HUMAN_PRINCIPAL_REQUIRED")

    # First fresh server commits RenderDraft and is killed after execute()
    # returns but before the HTTP handler can write its response.
    first = ServerProcess(payload, crash_operation="RenderDraft")
    try:
        first_pid, first_token = first.pid, first.token
        first.expect_crash_after_commit("execute_finalization", render_request)
    finally:
        first.stop()
    after_render_crash = database_snapshot(payload)
    require(after_render_crash["render_count"] == 1, "RENDER_NOT_DURABLE_AFTER_PROCESS_CRASH")
    require(after_render_crash["operations"][0][1] == 1, "RENDER_EVENT_NOT_UNIQUE")
    require(after_render_crash["events_equal_outbox"], "RENDER_EVENT_OUTBOX_DIVERGENCE")

    # New OS process, same stable Principal, fresh TokenAuthority and token.
    second = ServerProcess(payload, crash_operation="AssembleFinalPackage")
    try:
        second_pid, second_token = second.pid, second.token
        require(second_pid != first_pid, "RESTART_MUST_USE_NEW_OS_PROCESS")
        require(second_token != first_token, "RESTART_MUST_PROVISION_FRESH_TOKEN")
        before_render_replay = database_snapshot(payload)
        replayed_render = command_result(second.post("execute_finalization", render_request))
        require(replayed_render.case_sequence == before_render_replay["sequence"],
                "RENDER_REPLAY_SEQUENCE_CHANGED")
        require(database_snapshot(payload) == before_render_replay,
                "RENDER_REPLAY_CREATED_DUPLICATE_STATE")

        fixture.sequence = replayed_render.case_sequence
        validated_draft = fixture.get(replayed_render.refs[0])
        approval_request = fixture.final_request(
            "ApproveFinalDocument", validated_draft, render_id=render_id
        )
        approval_result = command_result(second.post("execute_finalization", approval_request))
        fixture.sequence = approval_result.case_sequence
        rendered_draft = fixture.get(approval_result.refs[0])

        release_request = fixture.release_request(rendered_draft, UUID(render_id))
        release_result = command_result(second.post("execute_finalization", release_request))
        fixture.sequence = release_result.case_sequence
        release_projection = second.post("query_finalization", {
            "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
            "operation": "GetFinalRelease",
            "tenant_id": payload["tenant_id"],
            "case_id": payload["case_id"],
            "render_id": render_id,
        })
        require(release_projection.get("result", {}).get("eligibility") == "FINAL",
                "FINAL_RELEASE_NOT_PERSISTED")

        package_request = fixture.package_request(rendered_draft, UUID(render_id))
        before_package_crash = database_snapshot(payload)
        second.expect_crash_after_commit("execute_finalization", package_request)
    finally:
        second.stop()

    after_package_crash = database_snapshot(payload)
    require(after_package_crash["package_count"] == 1, "PACKAGE_NOT_DURABLE_AFTER_PROCESS_CRASH")
    require(after_package_crash["operations"][3][1] == 1, "PACKAGE_ASSEMBLY_EVENT_NOT_UNIQUE")
    require(after_package_crash["events_equal_outbox"], "PACKAGE_EVENT_OUTBOX_DIVERGENCE")
    require(after_package_crash["package"] is not None, "PACKAGE_RECORD_MISSING")

    # A third fresh OS process replays the exact package command and reads all
    # ten immutable members. No token is persisted or reused across processes.
    third = ServerProcess(payload)
    try:
        third_pid, third_token = third.pid, third.token
        require(third_pid not in {first_pid, second_pid}, "THIRD_PROCESS_PID_NOT_DISTINCT")
        require(third_token not in {first_token, second_token}, "THIRD_PROCESS_TOKEN_NOT_FRESH")
        replayed_package = command_result(third.post("execute_finalization", package_request))
        require(replayed_package.case_sequence == after_package_crash["sequence"],
                "PACKAGE_REPLAY_SEQUENCE_CHANGED")
        require(database_snapshot(payload) == after_package_crash,
                "PACKAGE_REPLAY_CREATED_DUPLICATE_STATE")

        package_json = third.post("query_finalization", {
            "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
            "operation": "GetFinalPackage",
            "tenant_id": payload["tenant_id"],
            "case_id": payload["case_id"],
            "render_id": render_id,
        })
        package = FinalPackageRecord.model_validate_json(json.dumps(package_json, ensure_ascii=False, allow_nan=False))
        require(tuple(member.name for member in package.members) == FINAL_PACKAGE_MEMBER_NAMES,
                "EXACT_TEN_PACKAGE_MEMBERS_REQUIRED")
        require(len(package.members) == 10, "TEN_PACKAGE_MEMBERS_REQUIRED")

        member_bytes = {}
        for member in package.members:
            body, _headers = read_member(third, payload, render_id, member.name)
            require(len(body) == member.byte_length, "PACKAGE_MEMBER_LENGTH:" + member.name)
            require(sha256(body).hexdigest() == member.content_hash,
                    "PACKAGE_MEMBER_SHA256:" + member.name)
            member_bytes[member.name] = body

        from docx import Document
        from pypdf import PdfReader
        docx = Document(BytesIO(member_bytes["final.docx"]))
        pdf = PdfReader(BytesIO(member_bytes["final.pdf"]))
        docx_text = "\n".join(paragraph.text for paragraph in docx.paragraphs)
        pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        require(bool(docx_text.strip()), "FINAL_DOCX_NOT_PARSEABLE")
        require(bool(pdf.pages) and bool(pdf_text.strip()), "FINAL_PDF_NOT_PARSEABLE")
        require("SYNTETYCZNE PISMO TESTOWE" in docx_text, "DOCX_SYNTHETIC_HEADER_MISSING")
        require("SYNTETYCZNE PISMO TESTOWE" in pdf_text, "PDF_SYNTHETIC_HEADER_MISSING")

        # Same idempotency key with a changed body must fail closed.
        tampered_request = deepcopy(render_request)
        tampered_request["rationale"] += " tampered after process restart"
        require(error_code(third.post("execute_finalization", tampered_request))
                == "IDEMPOTENCY_CONFLICT", "TAMPERED_REPLAY_NOT_DENIED")

        # A new command with the old expected sequence is stale and must not write.
        stale_request = deepcopy(render_request)
        stale_request["meta"]["command_id"] = str(uuid4())
        stale_request["meta"]["idempotency_key"] = str(uuid4())
        stale_request["meta"]["correlation_id"] = str(uuid4())
        stale_request["meta"]["expected_case_sequence"] = payload["seed_case_sequence"]
        before_stale = database_snapshot(payload)
        require(error_code(third.post("execute_finalization", stale_request)) == "CONFLICT",
                "STALE_COMMAND_NOT_DENIED")
        require(database_snapshot(payload) == before_stale, "STALE_COMMAND_MUTATED_STATE")

        # Same tenant but foreign case scope cannot read this package.
        foreign = third.post("query_finalization", {
            "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
            "operation": "GetFinalPackage",
            "tenant_id": payload["tenant_id"],
            "case_id": payload["case_id"],
            "render_id": render_id,
        }, token=third.foreign_token)
        require(error_code(foreign) == "FORBIDDEN", "FOREIGN_PRINCIPAL_NOT_DENIED")

        # Privileged storage tamper must be detected against the immutable
        # package manifest after the OS-process restart. Always restore bytes.
        import psycopg
        manifest_member = next(member for member in package.members if member.name == "manifest.json")
        original_manifest = member_bytes["manifest.json"]
        with psycopg.connect(core.ADMIN_RUNTIME) as connection:
            connection.execute("ALTER TABLE lw_storage.blobs DISABLE TRIGGER guarded_blob")
            try:
                connection.execute(
                    "UPDATE lw_storage.blobs SET data=%s WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s",
                    (b"{}", UUID(payload["tenant_id"]), UUID(payload["case_id"]), manifest_member.artifact_id),
                )
            finally:
                connection.execute("ALTER TABLE lw_storage.blobs ENABLE TRIGGER guarded_blob")
        try:
            tampered_package = third.post("query_finalization", {
                "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
                "operation": "GetFinalPackage",
                "tenant_id": payload["tenant_id"],
                "case_id": payload["case_id"],
                "render_id": render_id,
            })
            require(error_code(tampered_package) == "INVALID_HASH", "STORAGE_TAMPER_NOT_DENIED")
        finally:
            with psycopg.connect(core.ADMIN_RUNTIME) as connection:
                connection.execute("ALTER TABLE lw_storage.blobs DISABLE TRIGGER guarded_blob")
                try:
                    connection.execute(
                        "UPDATE lw_storage.blobs SET data=%s WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s",
                        (original_manifest, UUID(payload["tenant_id"]), UUID(payload["case_id"]), manifest_member.artifact_id),
                    )
                finally:
                    connection.execute("ALTER TABLE lw_storage.blobs ENABLE TRIGGER guarded_blob")

        restored_package = third.post("query_finalization", {
            "contract": "urn:lukart:work:FinalizationQuery:1.0.0",
            "operation": "GetFinalPackage",
            "tenant_id": payload["tenant_id"],
            "case_id": payload["case_id"],
            "render_id": render_id,
        })
        require(restored_package.get("id") == package.id.__str__(), "PACKAGE_NOT_RESTORED_AFTER_TAMPER_TEST")
        final_snapshot = database_snapshot(payload)
        require(final_snapshot["events_equal_outbox"], "FINAL_EVENT_OUTBOX_DIVERGENCE")
        require(final_snapshot["operations"] == (
            ("RenderDraft", 1), ("ApproveFinalDocument", 1),
            ("RequestFinalRelease", 1), ("AssembleFinalPackage", 1),
        ), "FINALIZATION_EVENT_COUNTS_NOT_EXACT")
        require((final_snapshot["render_count"], final_snapshot["approval_count"],
                 final_snapshot["release_count"], final_snapshot["package_count"]) == (1, 1, 1, 1),
                "FINALIZATION_RECORD_COUNTS_NOT_EXACT")

        receipt = {
            "contract": "urn:lukart:work:ProcessRestartFinalizationE2EReceipt:1.0.0",
            "result": "PASS",
            "tested_sha": tested_sha,
            "synthetic_only": True,
            "execution_scope": "THREE_DISTINCT_OS_PROCESSES_LOOPBACK_HTTP_POSTGRESQL_18",
            "principal": {
                "tenant_id": payload["tenant_id"],
                "case_id": payload["case_id"],
                "actor_id": payload["actor_id"],
                "actor_kind": payload["actor_kind"],
                "actions_sha256": sha256(json.dumps(payload["actions"], separators=(",", ":")).encode()).hexdigest(),
            },
            "processes": [
                {"pid": first_pid, "crash_after_commit": "RenderDraft", "exit_code": CRASH_EXIT_CODE},
                {"pid": second_pid, "crash_after_commit": "AssembleFinalPackage", "exit_code": CRASH_EXIT_CODE},
                {"pid": third_pid, "role": "fresh-token-replay-and-verification"},
            ],
            "fresh_authority_tokens": "THREE_DISTINCT_IN_MEMORY_TOKENS_PRIVATE_PIPE_ONLY",
            "replay": {
                "render": "PASS_NO_DUPLICATE_EVENTS_OUTBOX_OR_SEQUENCE_ADVANCE",
                "package": "PASS_NO_DUPLICATE_EVENTS_OUTBOX_OR_SEQUENCE_ADVANCE",
            },
            "finalization": {
                "render": "PERSISTED",
                "approval": "PERSISTED_SYNTHETIC_HUMAN_FIXTURE",
                "release": "FINAL",
                "package_members": len(package.members),
                "package_member_sha256_and_lengths": "10/10 PASS",
                "docx_parse": "PASS",
                "pdf_parse": "PASS",
                "event_outbox_equality": True,
                "unique_event_counts": dict(final_snapshot["operations"]),
                "unique_record_counts": {
                    "render": final_snapshot["render_count"],
                    "approval": final_snapshot["approval_count"],
                    "release": final_snapshot["release_count"],
                    "package": final_snapshot["package_count"],
                },
            },
            "negative_checks": {
                "tampered_idempotent_request": "IDEMPOTENCY_CONFLICT",
                "stale_expected_sequence": "CONFLICT",
                "foreign_case_principal": "FORBIDDEN",
                "tampered_persisted_manifest_bytes": "INVALID_HASH",
                "tampered_storage_restored": True,
            },
            "non_claims": [
                "Synthetic HUMAN principal only; no native Windows HUMAN authentication.",
                "Synthetic document type only; no legal/type admission.",
                "No ROS-to-WORK H5 execution or product approval is established.",
                "No production deployment or go-live is established.",
            ],
        }
        evidence_dir = ROOT / "build" / "process-restart-e2e"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"result": "PASS", "tested_sha": tested_sha,
                          "receipt": "build/process-restart-e2e/receipt.json",
                          "processes": [first_pid, second_pid, third_pid],
                          "package_members": len(package.members)}))
    finally:
        third.stop()

if __name__ == "__main__":
    run()
