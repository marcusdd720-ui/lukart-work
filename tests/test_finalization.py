"""PB02 trusted render/persist/approval/release tests on real PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1, sha256
import json
import unittest
from uuid import UUID, uuid4, uuid5
from unittest.mock import patch

import psycopg

from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.drafting.service import ControlledDraftingService
from lukart_work.finalization.contracts import (
    FINAL_PACKAGE_MEMBER_NAMES,
    FinalPackageProfile,
    FinalPackageRecord,
    FinalizationProfile,
    FinalizationProjection,
    FinalizationRelease,
    semantic_profile_pin,
)
from lukart_work.finalization.service import FinalizationService
from lukart_work.planner.service import DocumentPlannerService
from lukart_work.procedural.service import ProceduralEngineService
from lukart_work.rendering.profiles import OFFICIAL_PL_V1, profile_pin
from lukart_work.storage.migrations import grant_runtime, migrate
from lukart_work.storage.objects import ObjectStore, RetentionPolicies
from lukart_work.validation.rules import digest, ref
from lukart_work.validation.service import ValidationEngineService
from tests import test_stage02 as core
from tests import test_stage10 as validation


FINALIZATION_ACTIONS = {
    "RenderDraft",
    "ApproveFinalDocument",
    "RequestFinalRelease",
    "GetFinalization",
    "GetFinalRelease",
    "ReadFinalArtifact",
    "AssembleFinalPackage",
    "GetFinalPackage",
    "ReadFinalPackageMember",
    "AuditRead",
}


class FinalPackageContractTests(unittest.TestCase):
    def test_package_profile_requires_exact_git_commit_sha(self):
        value = dict(
            profile_id="urn:lukart:work:synthetic-final-package-profile",
            version="1.0.0",
            baseline_contract_hash=sha256(b"synthetic-pb01-contract").hexdigest(),
        )
        profile = FinalPackageProfile(
            **value,
            build_revision=sha1(b"synthetic-build-revision").hexdigest(),
        )
        self.assertEqual(len(profile.build_revision), 40)
        with self.assertRaises(ValueError):
            FinalPackageProfile(
                **value,
                build_revision=sha256(b"not-a-git-commit-sha").hexdigest(),
            )


@unittest.skipUnless(core.ADMIN_RUNTIME and core.DSN, "PB02 requires isolated PostgreSQL")
class FinalizationTests(validation.ValidationTests):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(core.ADMIN_RUNTIME) as connection:
            migrate(connection)
            grant_runtime(connection, "lw_core_runtime")

    def setUp(self):
        super().setUp()
        self.repo = PostgresRepository(
            core.DSN, storage=True, retention_policies=RetentionPolicies()
        )
        self.service = CommandService(self.repo, self.authority)
        self.planner = DocumentPlannerService(self.repo, self.authority)
        self.procedural = ProceduralEngineService(self.repo, self.authority)
        self.profile["render_profile"] = profile_pin(OFFICIAL_PL_V1).model_dump(mode="json")
        self.drafting = ControlledDraftingService(
            self.repo, self.authority, self.provider, {"QUICK": self.profile}
        )
        self.validation = ValidationEngineService(self.repo, self.authority)
        self.authority.revoke(self.token)
        self.principal = Principal(
            self.actor,
            self.tenant,
            self.case_id,
            self.principal.actions | FINALIZATION_ACTIONS,
        )
        self.token = self.authority.provision(self.principal)
        self.final_profile = FinalizationProfile(
            profile_id="urn:lukart:work:synthetic-finalization-profile",
            version="1.0.0",
            document_type=core.PIN,
            header="SYNTETYCZNE PISMO TESTOWE",
            render_profile=profile_pin(OFFICIAL_PL_V1),
        )
        self.package_profile = FinalPackageProfile(
            profile_id="urn:lukart:work:synthetic-final-package-profile",
            version="1.0.0",
            build_revision=sha1(b"synthetic-build-revision").hexdigest(),
            baseline_contract_hash=sha256(b"synthetic-pb01-contract").hexdigest(),
        )
        self.finalization = FinalizationService(
            self.repo,
            self.authority,
            (self.final_profile,),
            package_profile=self.package_profile,
        )

    def final_request(self, operation, draft, **extra):
        request = self.request(operation, target=ref(draft))
        request.pop("data")
        request.update(
            contract="urn:lukart:work:FinalizationRequest:1.0.0",
            draft_hash=digest(draft),
            snapshot_hash=draft.snapshot_hash,
            rationale="Synthetic explicit HUMAN finalization intent",
            **extra,
        )
        return request

    def final_apply(self, request, *, service=None, token=None):
        result = (service or self.finalization).execute(
            json.dumps(request), token or self.token
        )
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return result

    def final_query(self, operation, render_id, **extra):
        query = dict(
            contract="urn:lukart:work:FinalizationQuery:1.0.0",
            operation=operation,
            tenant_id=str(self.tenant),
            case_id=str(self.case_id),
            render_id=str(render_id),
            **extra,
        )
        return self.finalization.query(json.dumps(query), self.token)

    def validated(self):
        _case, draft = self.generated()
        review = self.review(draft)
        result, run_id, _request = self.validate(draft, review)
        return self.get(result.refs[0]), run_id

    def render(self, draft, run_id):
        request = self.final_request(
            "RenderDraft",
            draft,
            validation_run_id=str(run_id),
            semantic_profile=semantic_profile_pin(self.final_profile).model_dump(mode="json"),
        )
        result = self.final_apply(request)
        render_id = uuid5(UUID(request["meta"]["command_id"]), "persisted-render")
        return render_id, result, request

    def approve(self, draft, render_id):
        result = self.final_apply(
            self.final_request("ApproveFinalDocument", draft, render_id=str(render_id))
        )
        return self.get(result.refs[0]), result.refs[1]

    def release_request(self, draft, render_id):
        return self.final_request("RequestFinalRelease", draft, render_id=str(render_id))

    def package_request(self, draft, render_id):
        return self.final_request("AssembleFinalPackage", draft, render_id=str(render_id))

    def released(self):
        validated, run_id = self.validated()
        render_id, _, _ = self.render(validated, run_id)
        rendered, _approval = self.approve(validated, render_id)
        self.final_apply(self.release_request(rendered, render_id))
        return rendered, render_id

    def package_query(self, operation, render_id, **extra):
        query = dict(
            contract="urn:lukart:work:FinalizationQuery:1.0.0",
            operation=operation,
            tenant_id=str(self.tenant),
            case_id=str(self.case_id),
            render_id=str(render_id),
            **extra,
        )
        return self.finalization.query(json.dumps(query), self.token)

    def test_public_happy_path_persists_exact_bytes_approval_and_release_chain(self):
        validated, run_id = self.validated()
        render_id, render_result, render_request = self.render(validated, run_id)
        projection = self.final_query("GetFinalization", render_id)
        self.assertIsInstance(projection, FinalizationProjection, projection)
        self.assertIsNone(projection.approval)
        self.assertEqual(projection.render.committed_sequence, render_result.case_sequence)
        docx = self.final_query("ReadFinalArtifact", render_id, format="DOCX")
        pdf = self.final_query("ReadFinalArtifact", render_id, format="PDF")
        self.assertEqual(sha256(docx).hexdigest(), projection.render.artifacts[0].artifact.content_hash)
        self.assertEqual(sha256(pdf).hexdigest(), projection.render.artifacts[1].artifact.content_hash)

        rendered, approval_ref = self.approve(validated, render_id)
        self.assertEqual(rendered.status, "RENDERED")
        projection = self.final_query("GetFinalization", render_id)
        self.assertEqual(projection.approval.approval, approval_ref)
        self.assertTrue(all(item.outcome == "PASS" for item in projection.approval.post_render_run.checks))
        self.assertEqual(
            projection.approval.post_render_run.render_hashes,
            tuple(item.artifact.content_hash for item in projection.render.artifacts),
        )

        release_request = self.release_request(rendered, render_id)
        release_result = self.final_apply(release_request)
        release = self.final_query("GetFinalRelease", render_id)
        self.assertIsInstance(release, FinalizationRelease, release)
        self.assertEqual(release.result.eligibility, "FINAL")
        self.assertEqual(release.committed_sequence, release_result.case_sequence)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            events = tx.events()
            outbox = tx.outbox()
            finalization_events = events[-3:]
            self.assertEqual(
                tuple(item.event_type for item in finalization_events),
                ("RevisionAppended", "DecisionRecorded", "ReleaseGranted"),
            )
            self.assertEqual(
                tuple(item.audit.sequence for item in finalization_events),
                tuple(range(render_result.case_sequence, release_result.case_sequence + 1)),
            )
            self.assertEqual(
                tuple(item.audit.event_id for item in outbox[-3:]),
                tuple(item.audit.event_id for item in finalization_events),
            )
            self.assertEqual(
                finalization_events[-1].audit.previous_event_hash,
                digest(finalization_events[-2]),
            )
            self.assertEqual(release.audit_previous_event_hash, digest(finalization_events[-2]))
            before = (tx.sequence(), tx.audit_inventory(), events, outbox)
        self.assertEqual(self.finalization.execute(json.dumps(release_request), self.token), release_result)
        self.assertEqual(self.finalization.execute(json.dumps(render_request), self.token), render_result)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(
                (tx.sequence(), tx.audit_inventory(), tx.events(), tx.outbox()),
                before,
            )

    def test_render_uses_validation_pinned_evidence_when_history_shares_anchor(self):
        validated, run_id = self.validated()
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            records = tx.records()
            plan = records[validated.plan]
            approval = records[plan.approval]
            accepted = records[plan.evidence[0]]
            sharing_anchor = [
                item
                for item in records.values()
                if getattr(item, "kind", None) == "Evidence"
                and item.source == accepted.source
            ]
        self.assertGreaterEqual(len(sharing_anchor), 2)
        self.assertTrue(any(
            target.kind == "DocumentPlan"
            and target.id == plan.id
            and target.revision == plan.revision - 1
            for target in approval.targets
        ))

        render_id, _, _ = self.render(validated, run_id)
        projection = self.final_query("GetFinalization", render_id)
        attachment_refs = {
            target
            for block in projection.render.meta.model.blocks
            if block.role == "ATTACHMENT_ITEM"
            for target in block.refs
        }
        self.assertEqual(attachment_refs, {plan.evidence[0]})

    def test_caller_cannot_inject_semantics_pass_receipt_or_wrong_profile(self):
        draft, run_id = self.validated()
        base = self.final_request(
            "RenderDraft",
            draft,
            validation_run_id=str(run_id),
            semantic_profile=semantic_profile_pin(self.final_profile).model_dump(mode="json"),
        )
        for name, value in (
            ("document", {"header": "FORGED"}),
            ("checks", [{"check": "render", "outcome": "PASS"}]),
            ("release_receipt", {"status": "FINAL"}),
            ("render_hashes", ["0" * 64]),
        ):
            bad = dict(base, **{name: value})
            result = self.finalization.execute(json.dumps(bad), self.token)
            self.assertIsInstance(result, DomainError)
            self.assertEqual(result.code, "SCHEMA_INVALID")
        bad = json.loads(json.dumps(base))
        bad["semantic_profile"]["content_hash"] = "0" * 64
        self.assertEqual(self.finalization.execute(json.dumps(bad), self.token).code, "GATE_DENIED")

    def test_artifact_failure_rolls_back_bytes_record_sequence_and_event(self):
        draft, run_id = self.validated()
        request = self.final_request(
            "RenderDraft",
            draft,
            validation_run_id=str(run_id),
            semantic_profile=semantic_profile_pin(self.final_profile).model_dump(mode="json"),
        )
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            before = (
                tx.sequence(),
                tx.audit_inventory(),
                tx.events(),
                tx.connection.execute(
                    "SELECT count(*) FROM lw_storage.artifacts WHERE tenant_id=%s AND case_id=%s",
                    (self.tenant, self.case_id),
                ).fetchone()[0],
            )
        original = ObjectStore.put
        calls = 0

        def fail_second(store, *args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(store, *args, **kwargs)
            if calls == 2:
                raise RuntimeError("synthetic rollback after both artifact writes")
            return result

        with patch.object(ObjectStore, "put", fail_second):
            with self.assertRaisesRegex(RuntimeError, "synthetic rollback"):
                self.finalization.execute(json.dumps(request), self.token)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            after = (
                tx.sequence(),
                tx.audit_inventory(),
                tx.events(),
                tx.connection.execute(
                    "SELECT count(*) FROM lw_storage.artifacts WHERE tenant_id=%s AND case_id=%s",
                    (self.tenant, self.case_id),
                ).fetchone()[0],
            )
        self.assertEqual(after, before)

    def test_release_cas_race_revocation_and_scope_fail_closed(self):
        validated, run_id = self.validated()
        render_id, _, _ = self.render(validated, run_id)
        rendered, approval = self.approve(validated, render_id)
        requests = [self.release_request(rendered, render_id) for _ in range(2)]
        authority = TokenAuthority()
        token = authority.provision(self.principal)
        other = FinalizationService(self.repo, authority, (self.final_profile,))
        with ThreadPoolExecutor(2) as pool:
            results = [
                pool.submit(self.finalization.execute, json.dumps(requests[0]), self.token),
                pool.submit(other.execute, json.dumps(requests[1]), token),
            ]
            results = [item.result() for item in results]
        self.assertEqual(sum(isinstance(item, CommandResult) for item in results), 1)
        self.assertEqual([item.code for item in results if isinstance(item, DomainError)], ["CONFLICT"])

        other_tenant = uuid4()
        wrong = authority.provision(
            Principal(self.actor, other_tenant, self.case_id, self.principal.actions)
        )
        query = dict(
            contract="urn:lukart:work:FinalizationQuery:1.0.0",
            operation="GetFinalRelease",
            tenant_id=str(self.tenant),
            case_id=str(self.case_id),
            render_id=str(render_id),
        )
        self.assertEqual(other.query(json.dumps(query), wrong).code, "FORBIDDEN")

        # A separate case proves revocation blocks before any release record is written.
        self.setUp()
        validated, run_id = self.validated()
        render_id, _, _ = self.render(validated, run_id)
        rendered, approval = self.approve(validated, render_id)
        self.apply("RevokeDecision", target=approval)
        before = self.state()
        denied = self.finalization.execute(
            json.dumps(self.release_request(rendered, render_id)), self.token
        )
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "STALE")
        self.assertEqual(self.state(), before)

    def test_final_package_has_ten_verified_members_and_survives_restart(self):
        rendered, render_id = self.released()
        result = self.final_apply(self.package_request(rendered, render_id))
        package = self.package_query("GetFinalPackage", render_id)
        self.assertIsInstance(package, FinalPackageRecord, package)
        self.assertEqual(package.committed_sequence, result.case_sequence)
        self.assertEqual(tuple(item.name for item in package.members), FINAL_PACKAGE_MEMBER_NAMES)
        self.assertEqual(package.manifest.members, package.members[:-1])
        self.assertNotIn("manifest.json", tuple(item.name for item in package.manifest.members))

        data = {}
        for member in package.members:
            body = self.package_query(
                "ReadFinalPackageMember", render_id, member=member.name
            )
            self.assertIsInstance(body, bytes, member.name)
            self.assertEqual(sha256(body).hexdigest(), member.content_hash)
            self.assertEqual(len(body), member.byte_length)
            data[member.name] = body
        for name in FINAL_PACKAGE_MEMBER_NAMES[2:]:
            json.loads(data[name])
        manifest = json.loads(data["manifest.json"])
        self.assertEqual(len(manifest["members"]), 9)
        self.assertEqual(manifest["release_hash"], package.manifest.release_hash)

        restarted = FinalizationService(
            self.repo,
            self.authority,
            (self.final_profile,),
            package_profile=self.package_profile,
        )
        query = dict(
            contract="urn:lukart:work:FinalizationQuery:1.0.0",
            operation="GetFinalPackage",
            tenant_id=str(self.tenant),
            case_id=str(self.case_id),
            render_id=str(render_id),
        )
        self.assertEqual(restarted.query(json.dumps(query), self.token), package)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.events()[-1].event_type, "FinalPackageAssembled")
            self.assertEqual(tx.events()[-1].audit.sequence, result.case_sequence)
            self.assertEqual(tx.outbox()[-1], tx.events()[-1])

    def test_package_requires_release_and_rolls_back_partial_member_writes(self):
        validated, run_id = self.validated()
        render_id, _, _ = self.render(validated, run_id)
        rendered, _approval = self.approve(validated, render_id)
        before = self.state()
        denied = self.finalization.execute(
            json.dumps(self.package_request(rendered, render_id)), self.token
        )
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "BROKEN_REFERENCE")
        self.assertEqual(self.state(), before)

        self.final_apply(self.release_request(rendered, render_id))
        request = self.package_request(rendered, render_id)
        unconfigured = FinalizationService(
            self.repo,
            self.authority,
            (self.final_profile,),
        )
        before_unconfigured = self.state()
        denied = unconfigured.execute(json.dumps(request), self.token)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "GATE_DENIED")
        self.assertEqual(self.state(), before_unconfigured)

        with self.repo.transaction(self.tenant, self.case_id) as tx:
            before = (
                tx.sequence(),
                tx.audit_inventory(),
                tx.events(),
                tx.connection.execute(
                    "SELECT count(*) FROM lw_storage.artifacts "
                    "WHERE tenant_id=%s AND case_id=%s AND category='package'",
                    (self.tenant, self.case_id),
                ).fetchone()[0],
            )
        original = ObjectStore.put
        calls = 0

        def fail_third_package_member(store, *args, **kwargs):
            nonlocal calls
            result = original(store, *args, **kwargs)
            if args[1] == "package":
                calls += 1
                if calls == 3:
                    raise RuntimeError("synthetic package rollback")
            return result

        with patch.object(ObjectStore, "put", fail_third_package_member):
            with self.assertRaisesRegex(RuntimeError, "synthetic package rollback"):
                self.finalization.execute(json.dumps(request), self.token)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            after = (
                tx.sequence(),
                tx.audit_inventory(),
                tx.events(),
                tx.connection.execute(
                    "SELECT count(*) FROM lw_storage.artifacts "
                    "WHERE tenant_id=%s AND case_id=%s AND category='package'",
                    (self.tenant, self.case_id),
                ).fetchone()[0],
            )
        self.assertEqual(after, before)

        injected = dict(request, package_profile=self.package_profile.model_dump(mode="json"))
        self.assertEqual(
            self.finalization.execute(json.dumps(injected), self.token).code,
            "SCHEMA_INVALID",
        )

    def test_historical_package_reads_survive_validation_pin_change(self):
        rendered, render_id = self.released()
        self.final_apply(self.package_request(rendered, render_id))
        expected = self.package_query("GetFinalPackage", render_id)
        expected_docx = self.final_query("ReadFinalArtifact", render_id, format="DOCX")
        expected_pdf = self.final_query("ReadFinalArtifact", render_id, format="PDF")
        expected_manifest = self.package_query(
            "ReadFinalPackageMember", render_id, member="manifest.json"
        )
        # A real deployment changes this content pin. Previously every read
        # accidentally called the current rendering/authorization code and failed.
        with patch("lukart_work.rendering.service.validation_pin", return_value=core.PIN):
            with patch.object(
                self.finalization.renderer, "render",
                side_effect=AssertionError("historical reads must not re-render"),
            ):
                projection = self.final_query("GetFinalization", render_id)
                self.assertIsInstance(projection, FinalizationProjection)
                self.assertEqual(self.final_query("GetFinalRelease", render_id).render_id, render_id)
                self.assertEqual(
                    self.final_query("ReadFinalArtifact", render_id, format="DOCX"), expected_docx
                )
                self.assertEqual(
                    self.final_query("ReadFinalArtifact", render_id, format="PDF"), expected_pdf
                )
                self.assertEqual(self.package_query("GetFinalPackage", render_id), expected)
                self.assertEqual(
                    self.package_query("ReadFinalPackageMember", render_id, member="manifest.json"),
                    expected_manifest,
                )

    def test_source_pin_change_still_blocks_stale_approval_mutation(self):
        validated, run_id = self.validated()
        render_id, _, _ = self.render(validated, run_id)
        request = self.final_request(
            "ApproveFinalDocument", validated, render_id=str(render_id)
        )
        before = self.state()
        with patch("lukart_work.rendering.service.validation_pin", return_value=core.PIN):
            denied = self.finalization.execute(json.dumps(request), self.token)
            self.assertIsInstance(denied, DomainError)
            self.assertEqual(denied.code, "STALE")
            self.assertIsInstance(
                self.final_query("GetFinalization", render_id), FinalizationProjection
            )
        self.assertEqual(self.state(), before)

    def test_package_assembly_requires_audit_read_and_preserves_other_grants(self):
        rendered, render_id = self.released()
        request = json.dumps(self.package_request(rendered, render_id))
        before = self.state()
        no_audit = self.authority.provision(
            Principal(self.actor, self.tenant, self.case_id,
                      self.principal.actions - {"AuditRead"})
        )
        denied = self.finalization.execute(request, no_audit)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "FORBIDDEN")
        self.assertEqual(self.state(), before)

        # Assembling a package does not require a grant to read its members.
        assembler = self.authority.provision(
            Principal(self.actor, self.tenant, self.case_id,
                      self.principal.actions - {"GetFinalPackage", "ReadFinalPackageMember"})
        )
        applied = self.finalization.execute(request, assembler)
        self.assertIsInstance(applied, CommandResult, applied)
        self.assertEqual(applied.state, "APPLIED")
        self.assertIsInstance(self.package_query("GetFinalPackage", render_id), FinalPackageRecord)

    def test_audit_member_requires_both_capabilities_but_other_reads_work(self):
        rendered, render_id = self.released()
        self.final_apply(self.package_request(rendered, render_id))
        query = dict(
            contract="urn:lukart:work:FinalizationQuery:1.0.0",
            operation="ReadFinalPackageMember",
            tenant_id=str(self.tenant),
            case_id=str(self.case_id),
            render_id=str(render_id),
        )

        def read(member, token):
            return self.finalization.query(json.dumps(dict(query, member=member)), token)

        no_audit = self.authority.provision(
            Principal(self.actor, self.tenant, self.case_id,
                      self.principal.actions - {"AuditRead"})
        )
        denied = read("audit.json", no_audit)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "FORBIDDEN")
        self.assertIsInstance(read("manifest.json", no_audit), bytes)
        self.assertIsInstance(read("final.pdf", no_audit), bytes)
        package_query = dict(query, operation="GetFinalPackage", member=None)
        self.assertIsInstance(
            self.finalization.query(json.dumps(package_query), no_audit), FinalPackageRecord
        )

        no_member_read = self.authority.provision(
            Principal(self.actor, self.tenant, self.case_id,
                      self.principal.actions - {"ReadFinalPackageMember"})
        )
        denied = read("audit.json", no_member_read)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "FORBIDDEN")
        foreign = self.authority.provision(
            Principal(self.actor, self.tenant, uuid4(), self.principal.actions)
        )
        denied = read("audit.json", foreign)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "FORBIDDEN")
        self.assertIsInstance(read("audit.json", self.token), bytes)

    def test_package_reads_require_distinct_capabilities_and_detect_tamper(self):
        rendered, render_id = self.released()
        self.final_apply(self.package_request(rendered, render_id))
        package = self.package_query("GetFinalPackage", render_id)
        self.assertIsInstance(package, FinalPackageRecord)

        limited = self.authority.provision(
            Principal(
                self.actor,
                self.tenant,
                self.case_id,
                self.principal.actions - {"GetFinalPackage", "ReadFinalPackageMember"},
            )
        )
        query = dict(
            contract="urn:lukart:work:FinalizationQuery:1.0.0",
            operation="GetFinalPackage",
            tenant_id=str(self.tenant),
            case_id=str(self.case_id),
            render_id=str(render_id),
        )
        denied = self.finalization.query(json.dumps(query), limited)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, "FORBIDDEN")

        manifest = package.members[-1]
        with psycopg.connect(core.ADMIN_RUNTIME) as connection:
            connection.execute("ALTER TABLE lw_storage.blobs DISABLE TRIGGER guarded_blob")
            connection.execute(
                "UPDATE lw_storage.blobs SET data=%s "
                "WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s",
                (b"{}", self.tenant, self.case_id, manifest.artifact_id),
            )
            connection.execute("ALTER TABLE lw_storage.blobs ENABLE TRIGGER guarded_blob")
        corrupted = self.finalization.query(json.dumps(query), self.token)
        self.assertIsInstance(corrupted, DomainError)
        self.assertEqual(corrupted.code, "INVALID_HASH")


if __name__ == "__main__":
    unittest.main()
