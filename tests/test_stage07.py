"""Stage 07 Procedural Intelligence acceptance on real PostgreSQL; synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import get_args
from unittest.mock import patch
import unittest
from uuid import UUID, uuid4, uuid5

import psycopg

from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.postgres import UnitOfWork, canonical
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor, Ref
from lukart_work.facts.contracts import FactOperation
from lukart_work.facts.service import FactEvidenceService
from lukart_work.procedural.contracts import (
    ProceduralAssessment, ProceduralOperation, ProceduralRuleBinding,
)
from lukart_work.procedural.service import CATEGORY, ProceduralEngineService
from lukart_work.validation.rules import digest
from tests import test_stage02 as core

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / 'tests/golden_cases/procedural_engine.json').read_text())


@unittest.skipUnless(core.ADMIN and core.DSN, 'Stage 07 requires isolated PostgreSQL')
class ProceduralEngineTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case_id, self.sequence = uuid4(), uuid4(), 0
        self.actor = Actor(id=uuid4(), kind='HUMAN')
        self.authority = TokenAuthority()
        actions = (core.ACTIONS | frozenset(get_args(FactOperation))
                   | frozenset(get_args(ProceduralOperation))
                   | {'GetFactEvidenceMatrix', 'AssessProcedure'})
        self.principal = Principal(self.actor, self.tenant, self.case_id, actions)
        self.token = self.authority.provision(self.principal)
        self.repo = core.PostgresRepository(core.DSN)
        self.service = CommandService(self.repo, self.authority)
        self.fact_service = FactEvidenceService(self.repo, self.authority)
        self.procedural = ProceduralEngineService(self.repo, self.authority)
        self.apply('CreateCase', {
            'title': 'Synthetic Stage 07 case',
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'retention_policy': core.PIN,
        })

    def request(self, operation, data=None, target=None, contract='urn:lukart:work:CoreRequest:1.0.0'):
        return {
            'contract': contract,
            'operation': operation,
            'meta': {
                'command_id': str(uuid4()),
                'tenant_id': str(self.tenant),
                'case_id': str(self.case_id),
                'idempotency_key': str(uuid4()),
                'expected_case_sequence': self.sequence,
                'correlation_id': str(uuid4()),
            },
            'target': target.model_dump(mode='json') if target else None,
            'data': data or {},
        }

    def execute(self, request, token=None, service=None):
        return (service or self.service).execute(json.dumps(request), token or self.token)

    def apply(self, operation, data=None, target=None):
        result = self.execute(self.request(operation, data, target))
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return result

    def prequest(self, operation, data=None, target=None):
        request = self.request(operation, data, target, 'urn:lukart:work:ProceduralRequest:1.0.0')
        request['rationale'] = 'Synthetic Stage 07 procedural operation'
        return request

    def pexecute(self, request, token=None):
        return self.procedural.execute(json.dumps(request), token or self.token)

    def papply(self, operation, data=None, target=None):
        result = self.pexecute(self.prequest(operation, data, target))
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return result

    def fexecute(self, operation, target, data=None):
        request = self.request(operation, data, target, 'urn:lukart:work:FactEvidenceRequest:1.0.0')
        request['rationale'] = 'Synthetic Stage 07 human fact/evidence review'
        result = self.fact_service.execute(json.dumps(request), self.token)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return result

    def decision(self, decision_type, targets):
        return self.apply('RecordDecision', {
            'decision_type': decision_type,
            'targets': [r.model_dump(mode='json') for r in targets],
            'outcome': 'ACCEPT',
            'rationale': 'Synthetic Stage 07 human decision',
        }).refs[0]

    def source(self, content):
        request = self.request('RegisterSource', {
            'content_base64': base64.b64encode(content).decode(),
            'media_type': 'text/plain',
            'retention_policy': core.PIN,
        })
        result = self.execute(request)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        return uuid5(UUID(request['meta']['command_id']), 'source')

    def legal_source(self, content=b'SYNTHETIC PROCEDURAL RULE SOURCE'):
        source_id = self.source(content)
        registered = self.papply('RegisterProceduralSource', {
            'source_id': str(source_id),
            'registry_id': 'urn:synthetic:procedural-registry',
            'registry_version': '2026-09-18',
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'source_type': 'LAW',
            'title': 'Synthetic Procedural Source',
            'identifier': 'SYN-PROC-2026',
            'effective_period': {'start': '2026-01-01', 'end': None},
            'source_uri': 'https://example.invalid/synthetic-procedure',
            'authority_level': 'BINDING',
        }).refs[0]
        return self.papply('VerifyProceduralSource', target=registered).refs[0]

    def register_rule(self, source_ref, spec, *, interpretation='SETTLED', document_types=None):
        return self.papply('RegisterProceduralRule', {
            'sources': [source_ref.model_dump(mode='json')],
            'statement': 'Synthetic procedural rule ' + spec['code'],
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'effective_period': {'start': '2026-01-01', 'end': None},
            'applicable_document_types': document_types or [core.PIN],
            'interpretation': interpretation,
            'spec': spec,
        }).refs[0]

    def activate_rule(self, rule):
        reviewed = self.papply('ReviewProceduralRule', target=rule).refs[0]
        decision = self.decision('INTERPRETATION', [reviewed])
        return self.papply('ActivateProceduralRule', {'decision': decision.model_dump(mode='json')}, reviewed).refs[0]

    def rule(self, source_ref, spec, *, interpretation='SETTLED', document_types=None):
        return self.activate_rule(self.register_rule(
            source_ref, spec, interpretation=interpretation, document_types=document_types
        ))

    @staticmethod
    def requirement(category, code, path, operator, operand, severity='BLOCKER', applies_when=()):
        return {
            'category': category,
            'code': code,
            'applies_when': list(applies_when),
            'requirements': [{'path': path, 'operator': operator, 'operand': operand}],
            'severity': severity,
            'deadline': None,
        }

    @staticmethod
    def deadline(code='SYN-DEADLINE', *, mode='CALENDAR_DAYS'):
        return {
            'category': 'DEADLINE',
            'code': code,
            'applies_when': [],
            'requirements': [],
            'severity': 'BLOCKER',
            'deadline': {
                'trigger_key': 'service_date',
                'offset_days': 14,
                'timezone': 'Europe/Warsaw',
                'due_time': '23:59',
                'calendar_mode': mode,
            },
        }

    def principals_and_filing(self):
        appellant = self.apply('AddParty', {
            'party_type': 'PERSON', 'display_name': 'Synthetic Appellant', 'identity_evidence': [],
        }).refs[0]
        representative = self.apply('AddParty', {
            'party_type': 'PERSON', 'display_name': 'Synthetic Representative', 'identity_evidence': [],
        }).refs[0]
        institution = self.apply('AddInstitution', {
            'institution_type': 'COURT',
            'name': 'Synthetic Procedural Court',
            'jurisdiction': GOLDEN['case_jurisdiction'],
        }).refs[0]
        proceeding = self.apply('AddProceeding', {
            'proceeding_type': 'SYNTHETIC_APPEAL',
            'institution': institution.model_dump(mode='json'),
            'participants': [{
                'party': appellant.model_dump(mode='json'),
                'role': 'APPELLANT',
                'represented_by': representative.model_dump(mode='json'),
            }],
            'reference_number': 'SYN-07',
            'parent_proceeding': None,
        }).refs[0]
        filing = self.apply('AddFiling', {
            'document_type': core.PIN,
            'direction': 'OUTGOING',
            'proceeding': proceeding.model_dump(mode='json'),
            'recipient': institution.model_dump(mode='json'),
            'authors': [representative.model_dump(mode='json')],
        }).refs[0]
        return appellant, representative, institution, proceeding, filing

    def fact_datum(self, key, value, subject):
        content = ('SYNTHETIC EVIDENCE ' + key).encode()
        source_id = self.source(content)
        checksum = sha256(content).hexdigest()
        anchor = {
            'document_id': str(source_id),
            'document_hash': checksum,
            'locator': {'unit': 'RECORD', 'value': 'STAGE07_' + key.upper(), 'fragment_hash': checksum},
        }
        evidence = self.apply('AddEvidence', {
            'evidence_type': 'DOCUMENT',
            'description': 'Synthetic evidence for ' + key,
            'source': anchor,
            'authenticity': 'UNKNOWN',
            'submitted_in': None,
        }).refs[0]
        evidence = self.fexecute('ReviewEvidence', evidence).refs[0]
        evidence = self.fexecute('AcceptEvidence', evidence).refs[0]
        request = self.request('AddFact', {
            'statement': canonical({'key': key, 'value': value}),
            'support': 'SOURCE_BACKED',
            'evidence': [evidence.model_dump(mode='json')],
            'subjects': [subject.model_dump(mode='json')],
            'event_date': None,
            'amount': None,
            'key_fact': True,
        })
        request['anchors'] = [anchor]
        result = self.execute(request)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        reviewed = self.fexecute('ReviewFact', result.refs[0]).refs[0]
        decision = self.decision('FACT_ACCEPTANCE', [reviewed])
        confirmed = self.fexecute('ConfirmFact', reviewed, {'decision': decision.model_dump(mode='json')}).refs[0]
        return {'key': key, 'classification': 'FACT', 'value': value, 'facts': [confirmed.model_dump(mode='json')]}

    def assess(self, filing, context=(), token=None, evaluation_date=None):
        query = {
            'contract': 'urn:lukart:work:ProceduralQuery:1.0.0',
            'operation': 'AssessProcedure',
            'tenant_id': str(self.tenant),
            'case_id': str(self.case_id),
            'filing': filing.model_dump(mode='json'),
            'evaluation_date': evaluation_date or GOLDEN['evaluation_date'],
            'context': list(context),
        }
        return self.procedural.assess(json.dumps(query), token or self.token)

    def test_golden_all_procedural_dimensions_are_deterministic_and_provenance_bound(self):
        appellant, representative, institution, _, filing = self.principals_and_filing()
        source = self.legal_source()
        specs = [
            self.requirement('ORGAN', 'SYN-ORGAN', '/recipient/institution_type', 'EQUALS', 'COURT'),
            self.requirement('JURISDICTION', 'SYN-JURIS', '/case/jurisdiction', 'EQUALS', GOLDEN['case_jurisdiction']),
            self.requirement('VENUE', 'SYN-VENUE', '/proceeding/institution_id', 'EQUALS', str(institution.id)),
            self.requirement('STANDING_AUTHORITY', 'SYN-STANDING', '/proceeding/representative_ids', 'CONTAINS_ALL', [str(representative.id)]),
            self.requirement('FILING_TOPOLOGY', 'SYN-TOPOLOGY', '/filing/recipient_id', 'EQUALS', str(institution.id)),
            self.requirement('CHANNEL', 'SYN-CHANNEL', '/context/channel', 'ONE_OF', ['SYNTHETIC_PORTAL', 'REGISTERED_MAIL']),
            self.requirement('FORMAL_REQUIREMENT', 'SYN-FORMAL', '/context/form_complete', 'EQUALS', True),
            self.requirement('SIGNATURE', 'SYN-SIGNATURE', '/context/signature_present', 'EQUALS', True),
            self.requirement('COPIES', 'SYN-COPIES', '/context/copies_count', 'MIN_INTEGER', 2),
            self.requirement('ATTACHMENTS', 'SYN-ATTACH', '/context/attachments', 'CONTAINS_ALL', ['ANNEX_A']),
            self.deadline(),
        ]
        active_rules = [self.rule(source, spec) for spec in specs]
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            records = tx.records()
            bindings = {b.rule: b for b in tx.objects(CATEGORY, ProceduralRuleBinding)}
            for target in active_rules:
                rule = records[target]
                binding = bindings[target]
                self.assertEqual(rule.requirement.operator, 'EQUALS')
                self.assertEqual(rule.requirement.field_path, '/procedural_spec')
                self.assertEqual(rule.requirement.operand, canonical(binding.spec))
                self.assertEqual(rule.requirement.severity, binding.spec.severity)
        context = [
            self.fact_datum('channel', GOLDEN['channel'], appellant),
            self.fact_datum('form_complete', True, appellant),
            self.fact_datum('signature_present', True, appellant),
            self.fact_datum('copies_count', GOLDEN['copies_count'], appellant),
            self.fact_datum('attachments', GOLDEN['attachments'], appellant),
            self.fact_datum('service_date', GOLDEN['service_date'], appellant),
        ]
        first = self.assess(filing, context)
        second = self.assess(filing, context)
        self.assertIsInstance(first, ProceduralAssessment, first)
        self.assertEqual(first, second)
        self.assertEqual(set(GOLDEN['expected_categories']), {f.category for f in first.findings})
        self.assertEqual(set(first.rules_considered), set(active_rules))
        for finding in first.findings:
            self.assertIn(finding.rule, active_rules)
            self.assertEqual(finding.sources, (source,))
            self.assertTrue(finding.binding_hash)
            if finding.category == 'DEADLINE':
                self.assertEqual((finding.outcome, finding.due_at.isoformat()), ('CALCULATED', GOLDEN['deadline_due']))
            else:
                self.assertEqual(finding.outcome, 'SATISFIED', finding)
        context_findings = [f for f in first.findings if f.path.startswith('/context/')]
        self.assertTrue(context_findings)
        self.assertTrue(all(f.facts for f in context_findings))

    def test_claim_unknown_unresolved_and_interpretation_do_not_become_fact(self):
        appellant, _, _, _, filing = self.principals_and_filing()
        source = self.legal_source()
        channel_rule = self.rule(source, self.requirement('CHANNEL', 'CLAIM-BOUNDARY', '/context/channel', 'EQUALS', 'SYNTHETIC_PORTAL'))
        claim = self.assess(filing, [{'key': 'channel', 'classification': 'CLAIM', 'value': 'SYNTHETIC_PORTAL', 'facts': []}])
        finding = next(f for f in claim.findings if f.rule == channel_rule)
        self.assertEqual((finding.applicability, finding.outcome), ('APPLICABLE', 'ABSTAIN'))

        conditional = self.rule(source, self.requirement(
            'VENUE', 'APPLICABILITY-BOUNDARY', '/case/status', 'EQUALS', 'OPEN',
            applies_when=({'path': '/context/venue_basis', 'operator': 'EQUALS', 'operand': True},),
        ))
        for classification, expected in [('UNKNOWN', 'UNKNOWN'), ('UNRESOLVED', 'UNRESOLVED'), ('INTERPRETATION', 'ABSTAIN')]:
            datum = {'key': 'venue_basis', 'classification': classification, 'facts': []}
            if classification != 'UNKNOWN':
                datum['value'] = True
            result = self.assess(filing, [datum])
            item = next(f for f in result.findings if f.rule == conditional)
            self.assertEqual((item.applicability, item.outcome), (expected, expected))

        malformed = {
            'contract': 'urn:lukart:work:ProceduralQuery:1.0.0',
            'operation': 'AssessProcedure',
            'tenant_id': str(self.tenant), 'case_id': str(self.case_id),
            'filing': filing.model_dump(mode='json'),
            'evaluation_date': GOLDEN['evaluation_date'],
            'context': [{'key': 'channel', 'classification': 'FACT', 'value': 'SYNTHETIC_PORTAL', 'facts': []}],
        }
        self.assertEqual(self.procedural.assess(json.dumps(malformed), self.token).code, 'SCHEMA_INVALID')

    def test_fact_context_requires_exact_current_confirmed_evidence_bound_fact(self):
        appellant, _, _, _, filing = self.principals_and_filing()
        source = self.legal_source()
        self.rule(source, self.requirement('CHANNEL', 'FACT-BINDING', '/context/channel', 'EQUALS', 'SYNTHETIC_PORTAL'))
        datum = self.fact_datum('other_key', 'SYNTHETIC_PORTAL', appellant)
        forged = dict(datum, key='channel')
        result = self.assess(filing, [forged])
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'GATE_DENIED')

    def test_rule_applicability_covers_not_applicable_unknown_and_disputed_interpretation(self):
        _, _, _, _, filing = self.principals_and_filing()
        source = self.legal_source()
        # A document-type mismatch provides a deterministic NOT_APPLICABLE without mutating canonical state.
        wrong_doc = {'id': 'synthetic-other', 'version': '1.0.0', 'content_hash': 'b' * 64}
        wrong_jurisdiction = self.activate_rule(self.register_rule(
            source, self.requirement('JURISDICTION', 'WRONG-DOC', '/case/status', 'EQUALS', 'OPEN'),
            document_types=[wrong_doc],
        ))
        disputed = self.rule(source, self.requirement('VENUE', 'DISPUTED-RULE', '/case/status', 'EQUALS', 'OPEN'), interpretation='DISPUTED')
        unknown = self.rule(source, self.requirement('ORGAN', 'UNKNOWN-RULE', '/case/status', 'EQUALS', 'OPEN'), interpretation='UNKNOWN')
        result = self.assess(filing)
        by_rule = {f.rule: f for f in result.findings}
        self.assertEqual((by_rule[wrong_jurisdiction].applicability, by_rule[wrong_jurisdiction].outcome), ('NOT_APPLICABLE', 'NOT_APPLICABLE'))
        self.assertEqual((by_rule[disputed].applicability, by_rule[disputed].outcome), ('UNRESOLVED', 'UNRESOLVED'))
        self.assertEqual((by_rule[unknown].applicability, by_rule[unknown].outcome), ('UNKNOWN', 'UNKNOWN'))

    def test_deadline_requires_verified_trigger_and_abstains_for_business_calendar(self):
        appellant, _, _, _, filing = self.principals_and_filing()
        source = self.legal_source()
        calendar_rule = self.rule(source, self.deadline('BUSINESS-DAY', mode='BUSINESS_DAYS'))
        missing = self.assess(filing)
        item = next(f for f in missing.findings if f.rule == calendar_rule)
        self.assertEqual(item.outcome, 'UNKNOWN')
        claim = self.assess(filing, [{'key': 'service_date', 'classification': 'CLAIM', 'value': GOLDEN['service_date'], 'facts': []}])
        item = next(f for f in claim.findings if f.rule == calendar_rule)
        self.assertEqual(item.outcome, 'ABSTAIN')
        datum = self.fact_datum('service_date', GOLDEN['service_date'], appellant)
        verified = self.assess(filing, [datum])
        item = next(f for f in verified.findings if f.rule == calendar_rule)
        self.assertEqual((item.outcome, item.message), ('ABSTAIN', 'BUSINESS_CALENDAR_NOT_SUPPORTED_IN_STAGE07'))

    def test_activation_requires_verified_source_and_correct_live_human_decision(self):
        raw_source_id = self.source(b'UNVERIFIED SYNTHETIC LEGAL SOURCE')
        raw_source = self.papply('RegisterProceduralSource', {
            'source_id': str(raw_source_id),
            'registry_id': 'urn:synthetic:unverified',
            'registry_version': '1',
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'source_type': 'LAW',
            'title': 'Unverified Synthetic Source',
            'identifier': 'UNVERIFIED-1',
            'effective_period': {'start': '2026-01-01', 'end': None},
            'source_uri': 'https://example.invalid/unverified',
            'authority_level': 'BINDING',
        }).refs[0]
        request = self.prequest('RegisterProceduralRule', {
            'sources': [raw_source.model_dump(mode='json')],
            'statement': 'Must fail closed',
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'effective_period': {'start': '2026-01-01', 'end': None},
            'applicable_document_types': [core.PIN],
            'interpretation': 'SETTLED',
            'spec': self.requirement('ORGAN', 'UNVERIFIED-SOURCE', '/case/status', 'EQUALS', 'OPEN'),
        })
        self.assertEqual(self.pexecute(request).code, 'GATE_DENIED')

        source = self.legal_source(b'VERIFIED SYNTHETIC LEGAL SOURCE')
        rule = self.register_rule(source, self.requirement('ORGAN', 'DECISION-GATE', '/case/status', 'EQUALS', 'OPEN'))
        reviewed = self.papply('ReviewProceduralRule', target=rule).refs[0]
        wrong = self.decision('STRATEGY', [reviewed])
        denied = self.pexecute(self.prequest('ActivateProceduralRule', {'decision': wrong.model_dump(mode='json')}, reviewed))
        self.assertEqual(denied.code, 'GATE_DENIED')

    def test_exact_replay_idempotency_conflict_and_concurrent_cas(self):
        source_id = self.source(b'SYNTHETIC REPLAY SOURCE')
        request = self.prequest('RegisterProceduralSource', {
            'source_id': str(source_id),
            'registry_id': 'urn:synthetic:replay',
            'registry_version': '1',
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'source_type': 'LAW',
            'title': 'Replay Source',
            'identifier': 'REPLAY-1',
            'effective_period': {'start': '2026-01-01', 'end': None},
            'source_uri': 'https://example.invalid/replay',
            'authority_level': 'BINDING',
        })
        first = self.pexecute(request)
        self.assertIsInstance(first, CommandResult, first)
        self.sequence = first.case_sequence
        self.assertEqual(self.pexecute(request), first)
        changed = json.loads(json.dumps(request))
        changed['data']['title'] = 'Changed replay payload'
        self.assertEqual(self.pexecute(changed).code, 'IDEMPOTENCY_CONFLICT')
        source = self.papply('VerifyProceduralSource', target=first.refs[0]).refs[0]
        rule = self.register_rule(source, self.requirement('ORGAN', 'CAS-RULE', '/case/status', 'EQUALS', 'OPEN'))
        left = self.prequest('ReviewProceduralRule', target=rule)
        right = self.prequest('ReviewProceduralRule', target=rule)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.pexecute, (left, right)))
        applied = [r for r in results if isinstance(r, CommandResult)]
        denied = [r for r in results if isinstance(r, DomainError)]
        self.assertEqual((len(applied), len(denied), denied[0].code), (1, 1, 'CONFLICT'))
        self.sequence = applied[0].case_sequence

    def test_rls_object_immutability_and_forged_binding_fail_closed(self):
        _, _, _, _, filing = self.principals_and_filing()
        source = self.legal_source()
        active = self.rule(source, self.requirement('ORGAN', 'IMMUTABLE', '/case/status', 'EQUALS', 'OPEN'))
        with psycopg.connect(core.DSN) as connection:
            connection.execute("SELECT set_config('lw.tenant', %s, true), set_config('lw.case', %s, true)", (str(self.tenant), str(self.case_id)))
            own = connection.execute("SELECT count(*) FROM lw_core.objects WHERE category='procedural_rule_binding'").fetchone()[0]
            connection.execute("SELECT set_config('lw.case', %s, true)", (str(uuid4()),))
            hidden = connection.execute("SELECT count(*) FROM lw_core.objects WHERE category='procedural_rule_binding'").fetchone()[0]
        self.assertGreater(own, 0)
        self.assertEqual(hidden, 0)
        with psycopg.connect(core.ADMIN, autocommit=True) as connection:
            with self.assertRaises(psycopg.errors.IntegrityConstraintViolation):
                connection.execute(
                    "UPDATE lw_core.objects SET payload=payload WHERE tenant_id=%s AND case_id=%s AND category='procedural_rule_binding'",
                    (self.tenant, self.case_id),
                )
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            history = sorted(tx.objects(CATEGORY, ProceduralRuleBinding), key=lambda b: b.revision)
            last = [b for b in history if b.rule.id == active.id][-1]
        forged = ProceduralRuleBinding(
            id=uuid4(),
            tenant_id=self.tenant,
            case_id=self.case_id,
            rule=Ref(kind='LegalRule', id=active.id, revision=active.revision + 1),
            revision=active.revision + 1,
            previous_hash=digest(last),
            sources=last.sources,
            spec=last.spec,
            actor=last.actor,
            recorded_at=last.recorded_at,
            implementation=last.implementation,
        )
        with psycopg.connect(core.ADMIN, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO lw_core.objects VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (self.tenant, self.case_id, CATEGORY, forged.id,
                 'urn:lukart:work:ProceduralRuleBinding:1.0.0',
                 canonical(forged), digest(forged), None),
            )
        result = self.assess(filing)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'INVALID_HASH')

    def test_transaction_rollback_leaves_no_rule_binding_audit_or_outbox(self):
        source = self.legal_source()
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            before = (tx.sequence(), len(tx.records()), len(tx.objects(CATEGORY, ProceduralRuleBinding)),
                      len(tx.events()), len(tx.outbox()))
        request = self.prequest('RegisterProceduralRule', {
            'sources': [source.model_dump(mode='json')],
            'statement': 'Synthetic rollback rule',
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'effective_period': {'start': '2026-01-01', 'end': None},
            'applicable_document_types': [core.PIN],
            'interpretation': 'SETTLED',
            'spec': self.requirement('ORGAN', 'ROLLBACK', '/case/status', 'EQUALS', 'OPEN'),
        })
        with patch.object(UnitOfWork, 'finish', side_effect=RuntimeError('synthetic rollback')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic rollback'):
                self.pexecute(request)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            after = (tx.sequence(), len(tx.records()), len(tx.objects(CATEGORY, ProceduralRuleBinding)),
                     len(tx.events()), len(tx.outbox()))
        self.assertEqual(after, before)

    def test_cross_scope_service_write_and_ai_read_are_forbidden(self):
        _, _, _, _, filing = self.principals_and_filing()
        actions = self.principal.actions
        service_token = self.authority.provision(Principal(
            Actor(id=uuid4(), kind='SERVICE'), self.tenant, self.case_id, actions
        ))
        source_id = self.source(b'SYNTHETIC SERVICE ATTEMPT')
        request = self.prequest('RegisterProceduralSource', {
            'source_id': str(source_id),
            'registry_id': 'urn:synthetic:service',
            'registry_version': '1',
            'jurisdiction': GOLDEN['case_jurisdiction'],
            'source_type': 'LAW',
            'title': 'Service Attempt',
            'identifier': 'SERVICE-1',
            'effective_period': {'start': '2026-01-01', 'end': None},
            'source_uri': 'https://example.invalid/service',
            'authority_level': 'BINDING',
        })
        self.assertEqual(self.pexecute(request, service_token).code, 'FORBIDDEN')
        ai_token = self.authority.provision(Principal(
            Actor(id=uuid4(), kind='AI'), self.tenant, self.case_id, actions
        ))
        self.assertEqual(self.assess(filing, token=ai_token).code, 'FORBIDDEN')
        foreign_token = self.authority.provision(Principal(
            Actor(id=uuid4(), kind='HUMAN'), uuid4(), uuid4(), actions
        ))
        self.assertEqual(self.assess(filing, token=foreign_token).code, 'FORBIDDEN')


if __name__ == '__main__':
    unittest.main()
