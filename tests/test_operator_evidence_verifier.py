"""Synthetic negative evidence and real renderer format checks; no live API/DB claim."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.verify_generator_pism_operator_evidence import (
    EXPECTED, parse_typed, validate_formats, verify, verify_member,
)
from lukart_work.core.postgres import canonical
from lukart_work.finalization.contracts import FinalSourcesRecord
from lukart_work.rendering.service import RenderingEngine
from tests.stage11_render_fixture import build_fixture

ROOT = Path(__file__).resolve().parents[1]
SHA = 'efbb9006afbddfcbf7e181888845735aa912e44c'


def forged_package(root):
    directory = root / 'package'
    directory.mkdir()
    members = []
    for name in EXPECTED:
        value = (b'PK-invalid-docx' if name == 'final.docx' else
                 b'%PDF-invalid-pdf' if name == 'final.pdf' else
                 json.dumps({'unrelated_text': 'FINAL'}).encode() if name == 'release.json' else
                 json.dumps({'members': [{'name': n, 'content_hash': '0' * 64, 'byte_length': 0}
                     for n in EXPECTED[:-1]]}).encode() if name == 'manifest.json' else b'{}')
        (directory / name).write_bytes(value)
        members.append({'name': name, 'content_hash': sha256(value).hexdigest(), 'byte_length': len(value)})
    evidence = {'contract': 'urn:lukart:work:GeneratorPismOperatorE2EEvidence:1.0.0',
                'result': 'PASS', 'tested_sha': SHA, 'synthetic_only': True,
                'human_actor_kind': 'HUMAN', 'legal_type_admission': 'HUMAN_REQUIRED',
                'release_eligibility': 'FINAL', 'package_member_count': 10, 'package_members': members,
                'direct_artifacts': {x['name']: {k: v for k, v in x.items() if k != 'name'}
                    for x in members[:2]}}
    path = root / 'evidence.json'
    path.write_text(json.dumps(evidence), encoding='utf-8')
    return path, directory


class OperatorEvidenceVerifierTests(unittest.TestCase):
    def test_forged_package_never_returns_pass_even_python_optimized(self):
        for optimized in (False, True):
            with self.subTest(optimized=optimized), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path, directory = forged_package(root)
                output = root / 'report.json'
                command = [sys.executable] + (['-O'] if optimized else []) + [
                    str(ROOT / 'scripts/verify_generator_pism_operator_evidence.py'),
                    '--evidence', str(path), '--package-dir', str(directory),
                    '--expected-sha', SHA, '--output', str(output)]
                result = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())

    def test_false_manifest_metadata_cannot_pass_member_hash_or_length(self):
        data = b'actual member'
        good = {'content_hash': sha256(data).hexdigest(), 'byte_length': len(data)}
        verify_member(data, good)
        for field, value in [('content_hash', '0' * 64), ('byte_length', 0), ('byte_length', True)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                verify_member(data, {**good, field: value})

    def test_canonical_typed_json_accepts_valid_contract_rejects_empty_or_duplicate(self):
        value = FinalSourcesRecord(contract='urn:lukart:work:FinalSourcesRecord:1.0.0', sources=(), anchors=())
        data = canonical(value).encode('utf-8')
        self.assertEqual(parse_typed(data, FinalSourcesRecord), value)
        for invalid in (b'{}', b'{"contract":"x","contract":"y"}', b' '+data):
            with self.subTest(invalid=invalid), self.assertRaises(Exception):
                parse_typed(invalid, FinalSourcesRecord)

    def test_real_renderer_docx_pdf_parsed_positive_invalid_magic_only_rejected(self):
        request, records, validation = build_fixture()
        bundle = RenderingEngine().render(request, records, validation)
        validate_formats(bundle.docx, bundle.pdf)
        for docx, pdf in ((b'PK-invalid', bundle.pdf), (bundle.docx, b'%PDF-invalid')):
            with self.assertRaises(Exception):
                validate_formats(docx, pdf)

    def test_duplicate_evidence_and_bad_expected_sha_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, directory = forged_package(Path(tmp))
            with self.assertRaises(ValueError):
                verify(path, directory, 'x' * 40)
            path.write_text('{"result":"FAIL","result":"PASS"}', encoding='utf-8')
            with self.assertRaises(Exception):
                verify(path, directory, SHA)

    def test_existing_pass_output_is_not_reused_or_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, directory = forged_package(root)
            output = root / 'report.json'
            output.write_text('previous evidence', encoding='utf-8')
            result = subprocess.run([sys.executable,
                str(ROOT / 'scripts/verify_generator_pism_operator_evidence.py'),
                '--evidence', str(path), '--package-dir', str(directory),
                '--expected-sha', SHA, '--output', str(output)], capture_output=True, text=True, cwd=ROOT)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('OUTPUT_ALREADY_EXISTS', result.stderr)
            self.assertEqual(output.read_text(), 'previous evidence')


def native_synthetic_package(root):
    """Native contracts + actual rendered bytes; synthetic decisions, no DB issuance."""
    from lukart_work.audit import AuditPackage, audit_pin
    from lukart_work.contracts import messages as wire
    from lukart_work.core.security import Principal
    from lukart_work.domain import models as domain
    from lukart_work.finalization import contracts as final
    from lukart_work.finalization.service import FinalizationService, PACKAGE_MEDIA_TYPES
    from lukart_work.validation.rules import digest as object_digest, ref
    from tests.fixtures import ACTOR, H, NOW, PIN, next_rev, source, uid
    request, records, validation = build_fixture()
    bundle = RenderingEngine().render(request, records, validation)
    validated = records[request.document.draft]
    rendered = next_rev(next_rev(validated, 'APPROVED'), 'RENDERED')
    tenant, case = validated.tenant_id, validated.case_id
    render = final.PersistedRender(
        id=uid(1100), tenant_id=tenant, case_id=case, validated_draft=ref(validated),
        validated_draft_hash=object_digest(validated), snapshot_id=validated.snapshot_id,
        snapshot_hash=validated.snapshot_hash, semantic_profile=PIN,
        document=request.document, validation=validation, meta=bundle.meta,
        artifacts=tuple(final.PersistedRenderArtifact(artifact_id=uid(1200+i), artifact=item)
                        for i, item in enumerate(bundle.meta.receipt.artifacts)),
        actor=ACTOR, recorded_at=NOW, committed_sequence=3)
    post_manifest = final.PostRenderManifest(
        input_validation=wire.ValidationRunPin(id=validation.execution.run.id,
                                               content_hash=object_digest(validation.execution.run)),
        input_validation_projection_hash=object_digest(validation),
        render_receipt_hash=object_digest(bundle.meta.receipt), rendered_draft=ref(rendered),
        rendered_draft_hash=object_digest(rendered), approval=domain.Ref(kind='Decision',id=uid(1300),revision=1),
        approval_hash=H, artifacts=bundle.meta.receipt.artifacts, policy=PIN)
    post_run = wire.ValidationRun(id=uid(1400), tenant_id=tenant,case_id=case,draft=ref(rendered),
        draft_hash=object_digest(rendered),snapshot_hash=rendered.snapshot_hash,policy=PIN,completed_at=NOW,
        checks=tuple(wire.CheckResult(check=name,outcome='PASS',validator=PIN) for name in wire.REQUIRED_CHECKS),
        findings=(),render_hashes=tuple(item.content_hash for item in bundle.meta.receipt.artifacts),
        execution_manifest_hash=object_digest(post_manifest))
    approval = final.FinalizationApproval(render_id=render.id,tenant_id=tenant,case_id=case,
        rendered_draft=ref(rendered),rendered_draft_hash=object_digest(rendered),approval=post_manifest.approval,
        approval_hash=H,post_render_run=post_run,manifest=post_manifest,actor=ACTOR,recorded_at=NOW,committed_sequence=4)
    target = domain.RenderTarget(tenant_id=tenant,case_id=case,snapshot_id=rendered.snapshot_id,
        snapshot_hash=rendered.snapshot_hash,draft=ref(rendered),draft_hash=object_digest(rendered),
        render_hashes=post_run.render_hashes)
    receipt = wire.ReleaseReceipt(target=target,approval=approval.approval,approval_hash=H,
        runs=(wire.ValidationRunPin(id=post_run.id,content_hash=object_digest(post_run)),),policy=PIN,case_sequence=4)
    release = final.FinalizationRelease(id=uid(1500),render_id=render.id,tenant_id=tenant,case_id=case,
        result=wire.ReleaseResult(eligibility='FINAL',reasons=(),draft=ref(rendered),snapshot_hash=rendered.snapshot_hash,
                                 render_hashes=post_run.render_hashes,receipt=receipt),
        approval=approval.approval,approval_hash=H,audit_previous_event_hash=H,actor=ACTOR,recorded_at=NOW,committed_sequence=5)
    events=[]
    hashes=[]
    for i in range(1,6):
        event=wire.DomainEvent(event_type='ReleaseGranted' if i==5 else 'RevisionAppended',subjects=(ref(rendered),),
            audit=wire.AuditEvent(event_id=uid(1600+i),tenant_id=tenant,case_id=case,sequence=i,actor=ACTOR,
                timestamp=NOW,operation='Synthetic fixture',command_id=uid(1700+i),correlation_id=uid(1800+i),
                input_hash=H,output_hash=H,previous_event_hash=hashes[-1] if hashes else None,
                source_versions=(),model_provider=None,rule_version=PIN))
        events.append(event)
        hashes.append(object_digest(event))
    audit=AuditPackage(contract='urn:lukart:work:AuditPackage:1.0.0',tenant_id=tenant,case_id=case,case_sequence=5,
        heads=(),revisions=(),objects=(),commands=(),events=tuple(events),event_hashes=tuple(hashes),
        outbox_event_ids=tuple(e.audit.event_id for e in events),chain_head_hash=hashes[-1],implementation=audit_pin())
    profile=final.FinalPackageProfile(profile_id='synthetic:package',version='1.0.0',build_revision=SHA,baseline_contract_hash=H)
    evidence_map,argument_map=FinalizationService._package_maps(records,render,Principal(ACTOR,tenant,case,frozenset()))
    anchors=tuple(sorted({*render.document.attachments,*(a for n in evidence_map.nodes for a in n.anchors),
                         *(a for n in argument_map.nodes for a in n.anchors)},key=lambda x:x.model_dump_json()))
    sources=final.FinalSourcesRecord(contract='urn:lukart:work:FinalSourcesRecord:1.0.0',sources=(source(),),anchors=anchors)
    payloads={'final.docx':bundle.docx,'final.pdf':bundle.pdf,
        'document.json':canonical(final.FinalDocumentRecord(contract='urn:lukart:work:FinalDocumentRecord:1.0.0',
                         profile=profile,document_type=PIN,draft=rendered,render=render)).encode(),
        'validation.json':canonical(final.FinalValidationRecord(contract='urn:lukart:work:FinalValidationRecord:1.0.0',
                           pre_render=validation,approval=approval)).encode(),
        'sources.json':canonical(sources).encode(),'evidence-map.json':canonical(evidence_map).encode(),
        'argument-map.json':canonical(argument_map).encode(),'audit.json':canonical(audit).encode(),
        'release.json':canonical(release).encode()}
    members=tuple(final.FinalPackageMember(name=name,artifact_id=uid(1900+i),media_type=PACKAGE_MEDIA_TYPES[name],
                         content_hash=sha256(payloads[name]).hexdigest(),byte_length=len(payloads[name]))
                   for i,name in enumerate(EXPECTED[:-1]))
    manifest=final.FinalPackageManifest(contract='urn:lukart:work:FinalPackageManifest:1.0.0',package_id=uid(2000),
        tenant_id=tenant,case_id=case,render_id=render.id,release_id=release.id,case_sequence=5,profile=profile,
        document_type=PIN,release_hash=object_digest(release),audit_package_hash=object_digest(audit),members=members)
    payloads['manifest.json']=canonical(manifest).encode()
    directory=root/'package'
    directory.mkdir()
    for name,data in payloads.items():
        (directory/name).write_bytes(data)
    member_evidence=[{'name':name,'content_hash':sha256(payloads[name]).hexdigest(),'byte_length':len(payloads[name])}
                     for name in EXPECTED]
    evidence={'contract':'urn:lukart:work:GeneratorPismOperatorE2EEvidence:1.0.0','result':'PASS','tested_sha':SHA,
              'synthetic_only':True,'human_actor_kind':'HUMAN','legal_type_admission':'HUMAN_REQUIRED',
              'release_eligibility':'FINAL','type_contract_pin':PIN.content_hash,'package_member_count':10,
              'package_members':member_evidence,'direct_artifacts':{x['name']:{k:v for k,v in x.items() if k!='name'}
                 for x in member_evidence[:2]},'package_id':str(manifest.package_id),'render_id':str(render.id),
              'release_id':str(release.id),'final_case_sequence':6,'event_count':6}
    path=root/'evidence.json'
    path.write_text(json.dumps(evidence),encoding='utf-8')
    return path,directory


class OperatorEvidenceNativePositiveTests(unittest.TestCase):
    def test_entire_native_synthetic_ten_member_package_validates_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence,directory=native_synthetic_package(Path(tmp))
            result=verify(evidence,directory,SHA)
            self.assertEqual(result['result'],'PASS')
            self.assertEqual(result['scope'],'OFFLINE_PACKAGE_INTEGRITY_ONLY')
            self.assertEqual(result['human_decision_authenticity'],'NOT_VERIFIED')
            self.assertEqual(result['repository_issuance'],'NOT_VERIFIED')
