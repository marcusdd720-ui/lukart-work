"""Stage 09 Controlled Drafting assurance on real PostgreSQL; synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import unittest
from typing import get_args
from uuid import uuid4

from lukart_work.contracts.messages import AIResult, CommandResult, DomainError, DomainEvent
from lukart_work.core.postgres import canonical, decode
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor
from lukart_work.drafting.contracts import (
    DraftingRejectionTrace, DraftingTerminalResult, DraftingTrace,
)
from lukart_work.drafting.service import ControlledDraftingService
from lukart_work.planner.contracts import PlannerOperation, stage08_actions
from lukart_work.planner.service import DocumentPlannerService
from lukart_work.procedural.contracts import ProceduralOperation
from lukart_work.procedural.service import ProceduralEngineService
from lukart_work.validation.rules import Violation, digest, ref
from tests import test_stage02 as core


class SyntheticProvider:
    def __init__(self, responder=None):
        self.responder = responder
        self.calls = 0
        self.receipt_overrides = {}

    def propose(self, invocation):
        self.calls += 1
        if self.responder is None:
            raise AssertionError('Synthetic provider responder not configured')
        return self.responder(invocation)

    def execution_receipt(self, request_id):
        value = {
            'contract': 'urn:lukart:work:ModelExecutionReceipt:1.0.0',
            'request_id': request_id,
            'provider': core.PIN,
            'model': core.PIN,
            'generator': core.PIN,
            'model_parameters_hash': 'b' * 64,
        }
        value.update(self.receipt_overrides)
        return value


@unittest.skipUnless(core.ADMIN and core.DSN, 'Stage 09 requires isolated PostgreSQL')
class ControlledDraftingTests(core.Stage02Tests):
    def setUp(self):
        super().setUp()
        self.authority.revoke(self.token)
        actions = (
            self.principal.actions
            | frozenset(get_args(PlannerOperation))
            | frozenset(get_args(ProceduralOperation))
            | {'GetDocumentPlan'}
        )
        self.principal = Principal(self.actor, self.tenant, self.case_id, actions)
        self.token = self.authority.provision(self.principal)
        self.planner = DocumentPlannerService(self.repo, self.authority)
        self.procedural = ProceduralEngineService(self.repo, self.authority)
        self.profile = {
            'profile': 'QUICK',
            'prompt': core.PIN,
            'model': core.PIN,
            'provider': core.PIN,
            'generator': core.PIN,
            'output_contract': core.PIN,
            'data_policy': core.PIN,
            'validators': [core.PIN],
            'render_profile': core.PIN,
            'model_parameters_hash': 'b' * 64,
        }
        self.provider = SyntheticProvider()
        self.drafting = ControlledDraftingService(
            self.repo, self.authority, self.provider, {'QUICK': self.profile}
        )

    def prequest(self, operation, data=None, target=None):
        request = self.request(operation, data, target)
        request['contract'] = 'urn:lukart:work:PlannerRequest:1.0.0'
        request['rationale'] = 'Synthetic Stage 09 planning intent'
        return request

    def pexecute(self, request):
        return self.planner.execute(json.dumps(request), self.token)

    def papply(self, operation, data=None, target=None):
        result = self.pexecute(self.prequest(operation, data, target))
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        return result

    def proc_request(self, operation, data=None, target=None):
        request = self.request(operation, data, target)
        request['contract'] = 'urn:lukart:work:ProceduralRequest:1.0.0'
        request['rationale'] = 'Synthetic Stage 09 legal authority fixture'
        return request

    def proc_apply(self, operation, data=None, target=None):
        result = self.procedural.execute(
            json.dumps(self.proc_request(operation, data, target)), self.token
        )
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        return result

    def legal_authority_fixture(
        self, source_id, *, jurisdiction='PL', effective_period=None,
        applicable_document_types=None, interpretation='SETTLED'
    ):
        effective_period = effective_period or {'start': '2026-01-01', 'end': None}
        applicable_document_types = (
            [core.PIN]
            if applicable_document_types is None
            else applicable_document_types
        )
        source = self.proc_apply('RegisterProceduralSource', {
            'source_id': str(source_id),
            'registry_id': 'urn:synthetic:stage09:legal-source',
            'registry_version': '2026-09-18',
            'jurisdiction': jurisdiction,
            'source_type': 'LAW',
            'title': 'Synthetic Stage 09 Legal Source',
            'identifier': 'SYN-STAGE09-LAW',
            'effective_period': effective_period,
            'source_uri': 'https://example.invalid/stage09-law',
            'authority_level': 'BINDING',
        }).refs[0]
        source = self.proc_apply('VerifyProceduralSource', target=source).refs[0]
        rule = self.proc_apply('RegisterProceduralRule', {
            'sources': [source.model_dump(mode='json')],
            'statement': 'Synthetic Stage 09 binding legal proposition',
            'jurisdiction': jurisdiction,
            'effective_period': effective_period,
            'applicable_document_types': applicable_document_types,
            'interpretation': interpretation,
            'spec': {
                'category': 'FORMAL_REQUIREMENT',
                'code': 'SYN-STAGE09-LEGAL',
                'applies_when': [],
                'requirements': [{
                    'path': '/case/status',
                    'operator': 'PRESENT',
                    'operand': None,
                }],
                'severity': 'BLOCKER',
                'deadline': None,
            },
        }).refs[0]
        reviewed = self.proc_apply('ReviewProceduralRule', target=rule).refs[0]
        approval = self.decision('INTERPRETATION', [reviewed])
        rule = self.proc_apply(
            'ActivateProceduralRule',
            {'decision': approval.model_dump(mode='json')},
            reviewed,
        ).refs[0]

        quote = 'Synthetic payment receipt.'
        citation = self.apply('AddCitation', {
            'source': source.model_dump(mode='json'),
            'locator': {
                'unit': 'RECORD',
                'value': '1',
                'fragment_hash': sha256(quote.encode()).hexdigest(),
            },
            'supported': rule.model_dump(mode='json'),
            'quotation': quote,
        }, inputs=[source.model_dump(mode='json'), rule.model_dump(mode='json')])[0].refs[0]
        citation = self.apply('BindCitation', target=citation)[0].refs[0]
        citation = self.apply('VerifyCitation', target=citation)[0].refs[0]
        return source, rule, citation, approval

    def test_public_citation_lifecycle_is_audited_and_human_only(self):
        _fact, _party, _evidence, source_id = self.fact()
        source, rule, citation, _approval = self.legal_authority_fixture(source_id)
        self.assertEqual(self.get(citation).status, 'VERIFIED')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            citation_events = tuple(
                event for event in tx.events()
                if event.audit.operation in ('AddCitation', 'BindCitation', 'VerifyCitation')
            )
            self.assertEqual(
                tuple(event.audit.operation for event in citation_events),
                ('AddCitation', 'BindCitation', 'VerifyCitation'),
            )
            self.assertEqual(
                tuple(event.audit.sequence for event in citation_events),
                tuple(range(self.sequence - 2, self.sequence + 1)),
            )

        service_actor = Actor(id=uuid4(), kind='SERVICE')
        service_token = self.authority.provision(
            Principal(service_actor, self.tenant, self.case_id, self.principal.actions)
        )
        quote = 'Synthetic payment receipt.'
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            before = (
                tx.sequence(),
                tx.records(),
                tx.events(),
                tx.outbox(),
                tx.audit_inventory(),
            )
        denied = self.service.execute(json.dumps(self.request('AddCitation', {
            'source': source.model_dump(mode='json'),
            'locator': {
                'unit': 'RECORD', 'value': '1',
                'fragment_hash': sha256(quote.encode()).hexdigest(),
            },
            'supported': rule.model_dump(mode='json'),
            'quotation': quote,
        })), service_token)
        self.assertIsInstance(denied, DomainError)
        self.assertEqual(denied.code, 'FORBIDDEN')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            after = (
                tx.sequence(),
                tx.records(),
                tx.events(),
                tx.outbox(),
                tx.audit_inventory(),
            )
        self.assertEqual(after, before)

    def approved_planning_case(
        self, requirements=('REQUESTS', 'ATTACHMENTS'), *, legal=False,
        legal_kwargs=None, confirm_fact=True, extra_context_request=False
    ):
        fact, party, evidence, source_id = self.fact()
        if confirm_fact:
            reviewed_fact = self.apply('ReviewFact', target=fact)[0].refs[0]
            fact_acceptance = self.decision('FACT_ACCEPTANCE', [reviewed_fact])
            fact = self.apply(
                'ConfirmFact',
                {'decision': fact_acceptance.model_dump(mode='json')},
                reviewed_fact,
            )[0].refs[0]
        filing = self.apply('AddFiling', {
            'document_type': core.PIN,
            'direction': 'OUTGOING',
            'recipient': party.model_dump(mode='json'),
            'authors': [party.model_dump(mode='json')],
        })[0].refs[0]
        issue = self.apply('AddIssue', {
            'question': 'Synthetic Stage 09 issue',
            'facts': [fact.model_dump(mode='json')],
            'rules': [],
        })[0].refs[0]
        claim = self.apply('AddClaim', {
            'claim_type': 'ASSERTION',
            'statement': 'Synthetic Stage 09 assertion',
            'claimant': party.model_dump(mode='json'),
            'issues': [issue.model_dump(mode='json')],
            'facts': [fact.model_dump(mode='json')],
            'rules': [],
            'support': 'SOURCE_BACKED',
        })[0].refs[0]
        objective = self.apply('AddRequest', {
            'filing': filing.model_dump(mode='json'),
            'request_type': 'SYNTHETIC_RELIEF',
            'text': 'Synthetic requested outcome',
            'claims': [claim.model_dump(mode='json')],
            'evidence': [evidence.model_dump(mode='json')],
        })[0].refs[0]
        extra_request = None
        if extra_context_request:
            extra_request = self.apply('AddRequest', {
                'filing': filing.model_dump(mode='json'),
                'request_type': 'SYNTHETIC_CONTEXT_ONLY',
                'text': 'Synthetic context-only request',
                'claims': [claim.model_dump(mode='json')],
                'evidence': [evidence.model_dump(mode='json')],
            })[0].refs[0]
        legal_source = legal_rule = citation = legal_approval = None
        if legal:
            legal_source, legal_rule, citation, legal_approval = (
                self.legal_authority_fixture(source_id, **(legal_kwargs or {}))
            )
        snapshot = self.snapshot()
        snapshot_acceptance = self.accept(snapshot)
        plan_data = {
            'snapshot_id': str(snapshot.id),
            'snapshot_hash': digest(snapshot),
            'filing': filing.model_dump(mode='json'),
            'objectives': [objective.model_dump(mode='json')],
            'position_scope': 'Synthetic Stage 09 controlled drafting scope',
            'argument_order': [],
            'evidence': [evidence.model_dump(mode='json')],
            'sections': [{
                'section_type': 'SYNTHETIC',
                'title': 'Synthetic section',
                'arguments': [],
                'allowed_inputs': [
                    fact.model_dump(mode='json'),
                    evidence.model_dump(mode='json'),
                    claim.model_dump(mode='json'),
                    objective.model_dump(mode='json'),
                    *([] if extra_request is None else [
                        extra_request.model_dump(mode='json'),
                    ]),
                    *([] if not legal else [
                        legal_rule.model_dump(mode='json'),
                        citation.model_dump(mode='json'),
                    ]),
                ],
                'required_inputs': [
                    fact.model_dump(mode='json'),
                    evidence.model_dump(mode='json'),
                    objective.model_dump(mode='json'),
                    *([] if not legal else [
                        legal_rule.model_dump(mode='json'),
                        citation.model_dump(mode='json'),
                    ]),
                ],
                'allowed_claims': [claim.model_dump(mode='json')],
                'forbidden': [
                    'UNSUPPORTED_ASSERTION',
                    'UNMARKED_INFERENCE',
                    'NEW_FACT',
                    'NEW_LEGAL_RULE',
                ],
                'requirements': list(requirements),
            }],
        }
        proposed = self.papply('PlanDocument', plan_data).refs[0]
        reviewed = self.papply('ReviewDocumentPlan', target=proposed).refs[0]
        approval = self.decision('PLAN_APPROVAL', [reviewed])
        approved = self.papply(
            'ApproveDocumentPlan',
            {'decision': approval.model_dump(mode='json')},
            reviewed,
        ).refs[0]
        return {
            'fact': fact,
            'party': party,
            'evidence': evidence,
            'filing': filing,
            'claim': claim,
            'objective': objective,
            'extra_request': extra_request,
            'snapshot': snapshot,
            'snapshot_acceptance': snapshot_acceptance,
            'plan': approved,
            'plan_approval': approval,
            'legal_source': legal_source,
            'legal_rule': legal_rule,
            'citation': citation,
            'legal_approval': legal_approval,
        }

    def generate_request(self, case):
        return {
            'operation': 'GenerateDocument',
            'meta': {
                'command_id': str(uuid4()),
                'tenant_id': str(self.tenant),
                'case_id': str(self.case_id),
                'idempotency_key': str(uuid4()),
                'expected_case_sequence': self.sequence,
                'correlation_id': str(uuid4()),
            },
            'document_type': core.PIN,
            'objective_ids': [str(case['objective'].id)],
            'snapshot_id': str(case['snapshot'].id),
            'snapshot_hash': digest(case['snapshot']),
            'plan': case['plan'].model_dump(mode='json'),
            'profile': 'QUICK',
        }

    @staticmethod
    def statement(text, statement_type, support, refs, *, inference_label=None, citations=()):
        return {
            'id': str(uuid4()),
            'text': text,
            'statement_type': statement_type,
            'support': support,
            'refs': [item.model_dump(mode='json') for item in refs],
            'citations': [item.model_dump(mode='json') for item in citations],
            'inference_label': inference_label,
        }

    def valid_output(self, case, invocation):
        return {
            'request_id': str(invocation.request.request_id),
            'snapshot_hash': invocation.request.snapshot_hash,
            'disposition': 'PROPOSE',
            'proposals': [],
            'section': {
                'section': invocation.section.model_dump(mode='json'),
                'statements': [
                    self.statement(
                        'Synthetic source-backed factual statement.',
                        'FACTUAL',
                        'SOURCE_BACKED',
                        (case['fact'], case['evidence']),
                    ),
                    self.statement(
                        'Synthetic requested outcome.',
                        'REQUEST',
                        'SOURCE_BACKED',
                        (case['objective'],),
                    ),
                ],
            },
            'missing_information': [],
            'reason': None,
        }

    def draft_heads(self):
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            return tuple(item for item in tx.heads() if item.kind == 'Draft')

    def test_golden_generate_document_commits_only_generated_draft_and_auditable_trace(self):
        case = self.approved_planning_case()
        supplied_ids = []
        def responder(invocation):
            output = self.valid_output(case, invocation)
            supplied_ids.extend(item['id'] for item in output['section']['statements'])
            return output
        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.sequence = result.case_sequence
        self.assertEqual(self.provider.calls, 1)
        draft = self.get(result.refs[0])
        self.assertEqual(draft.status, 'GENERATED')
        self.assertNotIn('FINAL', draft.status)
        stored_ids = [str(item.id) for section in draft.sections for item in section.statements]
        self.assertNotEqual(stored_ids, supplied_ids)
        self.assertEqual(
            {item.statement_type for item in draft.sections[0].statements},
            {'FACTUAL', 'REQUEST'},
        )
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            traces = tx.objects('drafting_trace', DraftingTrace)
            self.assertEqual(len(traces), 1)
            trace = traces[0]
            self.assertEqual(len(trace.raw_outputs), 1)
            self.assertEqual(len(trace.execution_receipts), 1)
            self.assertEqual(
                trace.execution_receipts[0].request_id,
                trace.invocations[0].request.request_id,
            )
            self.assertEqual(trace.raw_output_hash, digest(trace.raw_outputs))
            self.assertEqual(trace.results[0].disposition, 'PROPOSE')
            events = tx.events()
            self.assertEqual(events[-1].event_type, 'DraftGenerated')
            self.assertEqual(tx.outbox(), events)

    def test_same_command_replay_does_not_call_model_again(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        request = self.generate_request(case)
        first = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(first, CommandResult, first)
        self.sequence = first.case_sequence
        self.assertEqual(self.provider.calls, 1)
        second = self.drafting.generate(json.dumps(request), self.token)
        self.assertEqual(second, first)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(len(self.draft_heads()), 1)

    def test_concurrent_same_command_calls_model_once(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        request = self.generate_request(case)
        raw = json.dumps(request)

        authority_a = TokenAuthority()
        authority_b = TokenAuthority()
        token_a = authority_a.provision(self.principal)
        token_b = authority_b.provision(self.principal)
        service_a = ControlledDraftingService(
            self.repo, authority_a, self.provider, {'QUICK': self.profile}
        )
        service_b = ControlledDraftingService(
            self.repo, authority_b, self.provider, {'QUICK': self.profile}
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service_a.generate, raw, token_a)
            second = pool.submit(service_b.generate, raw, token_b)
            results = (first.result(), second.result())
        self.assertTrue(all(isinstance(result, CommandResult) for result in results))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(len(self.draft_heads()), 1)

    def test_abstain_stays_abstain_is_audited_and_replays_without_model_call(self):
        case = self.approved_planning_case()
        def responder(invocation):
            return {
                'request_id': str(invocation.request.request_id),
                'snapshot_hash': invocation.request.snapshot_hash,
                'disposition': 'ABSTAIN',
                'proposals': [],
                'section': None,
                'missing_information': ['Synthetic missing information'],
                'reason': 'Insufficient evidence for controlled drafting',
            }
        self.provider.responder = responder
        request = self.generate_request(case)
        before = self.sequence
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.disposition, 'ABSTAIN')
        self.assertEqual(self.provider.calls, 1)
        self.assertFalse(self.draft_heads())
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertEqual(tx.sequence(), before + 1)
            traces = tx.objects('drafting_trace', DraftingTrace)
            self.assertEqual(len(traces), 1)
            self.assertEqual(traces[0].results[-1].disposition, 'ABSTAIN')
            self.assertEqual(traces[0].raw_output_hash, digest(traces[0].raw_outputs))
            events = tx.events()
            self.assertEqual(events[-1].event_type, 'DraftingAbstained')
            self.assertEqual(tx.outbox(), events)
        replay = self.drafting.generate(json.dumps(request), self.token)
        self.assertEqual(replay, result)
        self.assertEqual(self.provider.calls, 1)
        self.assertFalse(self.draft_heads())

    def test_abstain_lost_sequence_cas_writes_no_terminal_event(self):
        case = self.approved_planning_case()
        changed = {'done': False}

        def responder(invocation):
            if not changed['done']:
                changed['done'] = True
                self.apply('AddParty', {
                    'party_type': 'PERSON',
                    'display_name': 'Synthetic concurrent ABSTAIN mutation',
                    'identity_evidence': [],
                })
            return {
                'request_id': str(invocation.request.request_id),
                'snapshot_hash': invocation.request.snapshot_hash,
                'disposition': 'ABSTAIN',
                'proposals': [],
                'section': None,
                'missing_information': ['Synthetic concurrent mutation'],
                'reason': 'Synthetic ABSTAIN after sequence change',
            }

        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'CONFLICT')
        self.assertEqual(self.provider.calls, 1)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertFalse(any(
                event.event_type == 'DraftingAbstained' for event in tx.events()
            ))

    def test_rejection_lost_sequence_cas_writes_no_terminal_event(self):
        case = self.approved_planning_case()
        changed = {'done': False}

        def responder(invocation):
            if not changed['done']:
                changed['done'] = True
                self.apply('AddParty', {
                    'party_type': 'PERSON',
                    'display_name': 'Synthetic concurrent rejection mutation',
                    'identity_evidence': [],
                })
            output = self.valid_output(case, invocation)
            output['proposals'] = [{
                'proposal_id': str(uuid4()),
                'proposed_kind': 'Fact',
                'statement': 'Synthetic rejected proposal',
                'support': 'SOURCE_BACKED',
                'source_refs': [case['fact'].model_dump(mode='json')],
                'anchors': [],
                'uncertainty': 'LOW',
            }]
            return output

        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'CONFLICT')
        self.assertEqual(self.provider.calls, 1)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertFalse(any(
                event.event_type == 'DraftingRejected' for event in tx.events()
            ))

    def test_stage09_product_authority_can_draft_but_cannot_use_legacy_planning_bypass(self):
        case = self.approved_planning_case()
        restricted_actions = stage08_actions(self.principal.actions) | {'GetDocumentPlan'}
        self.assertIn('GenerateDocument', restricted_actions)
        self.assertNotIn('AddSection', restricted_actions)
        restricted = Principal(
            self.actor, self.tenant, self.case_id, restricted_actions
        )
        restricted_token = self.authority.provision(restricted)
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        result = self.drafting.generate(
            json.dumps(self.generate_request(case)), restricted_token
        )
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.assertEqual(self.provider.calls, 1)

    def test_model_cannot_propose_domain_fact_or_claim_write(self):
        case = self.approved_planning_case()
        def responder(invocation):
            output = self.valid_output(case, invocation)
            output['proposals'] = [{
                'proposal_id': str(uuid4()),
                'proposed_kind': 'Fact',
                'statement': 'Synthetic attempt to create a fact',
                'support': 'SOURCE_BACKED',
                'source_refs': [case['fact'].model_dump(mode='json')],
                'anchors': [],
                'uncertainty': 'LOW',
            }]
            return output
        self.provider.responder = responder
        before = self.get(case['fact'])
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'GATE_DENIED')
        self.assertEqual(self.get(case['fact']), before)
        self.assertEqual(self.provider.calls, 1)
        replay = self.drafting.generate(json.dumps(request), self.token)
        self.assertEqual(replay, result)
        self.assertEqual(self.provider.calls, 1)
        self.assertFalse(self.draft_heads())

    def test_model_cannot_hide_new_fact_as_structural_text(self):
        case = self.approved_planning_case()
        def responder(invocation):
            output = self.valid_output(case, invocation)
            output['section']['statements'][0] = self.statement(
                'Synthetic hidden factual assertion.',
                'STRUCTURAL',
                'SOURCE_BACKED',
                (case['fact'],),
            )
            return output
        self.provider.responder = responder
        result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'GATE_DENIED')
        self.assertFalse(self.draft_heads())

    def test_unmarked_inference_and_unsupported_statement_fail_closed(self):
        case = self.approved_planning_case()
        for statement in (
            self.statement(
                'Synthetic unmarked inference.',
                'INFERENCE',
                'SOURCE_BACKED',
                (case['fact'],),
            ),
            self.statement(
                'Synthetic unsupported assertion.',
                'FACTUAL',
                'UNSUPPORTED',
                (case['fact'],),
            ),
        ):
            self.provider.calls = 0
            def responder(invocation, statement=statement):
                output = self.valid_output(case, invocation)
                output['section']['statements'][0] = statement
                return output
            self.provider.responder = responder
            result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
            self.assertIsInstance(result, DraftingTerminalResult, result)
            self.assertIn(result.error.code, {'GATE_DENIED', 'UNSUPPORTED'})
            self.assertFalse(self.draft_heads())
            self.sequence += 1

    def test_candidate_or_claim_cannot_be_materialized_as_factual_prose(self):
        for mode in ('CANDIDATE_FACT', 'CLAIM_WITH_EVIDENCE'):
            with self.subTest(mode=mode):
                case = self.approved_planning_case(confirm_fact=False)
                def responder(invocation, mode=mode):
                    output = self.valid_output(case, invocation)
                    refs = (
                        (case['fact'], case['evidence'])
                        if mode == 'CANDIDATE_FACT'
                        else (case['claim'], case['evidence'])
                    )
                    output['section']['statements'][0] = self.statement(
                        'Synthetic unconfirmed proposition.',
                        'FACTUAL',
                        'SOURCE_BACKED',
                        refs,
                    )
                    return output
                self.provider.responder = responder
                request = self.generate_request(case)
                before_calls = self.provider.calls
                result = self.drafting.generate(json.dumps(request), self.token)
                self.assertIsInstance(result, DraftingTerminalResult, result)
                self.assertEqual(result.error.code, 'GATE_DENIED')
                self.assertEqual(self.provider.calls, before_calls + 1)
                replay = self.drafting.generate(json.dumps(request), self.token)
                self.assertEqual(replay, result)
                self.assertEqual(self.provider.calls, before_calls + 1)
                self.assertFalse(self.draft_heads())
                with self.repo.transaction(self.tenant, self.case_id) as tx:
                    rejections = tx.objects(
                        'drafting_rejection_trace', DraftingRejectionTrace
                    )
                    self.assertTrue(rejections)
                    self.assertEqual(tx.events()[-1].event_type, 'DraftingRejected')
                    self.assertEqual(tx.outbox(), tx.events())
                self.sequence += 1

    def test_request_statement_cannot_expand_approved_plan_objectives(self):
        case = self.approved_planning_case(extra_context_request=True)
        def responder(invocation):
            output = self.valid_output(case, invocation)
            output['section']['statements'].append(self.statement(
                'Synthetic unapproved additional request.',
                'REQUEST',
                'SOURCE_BACKED',
                (case['extra_request'],),
            ))
            return output
        self.provider.responder = responder
        result = self.drafting.generate(
            json.dumps(self.generate_request(case)), self.token
        )
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'GATE_DENIED')
        self.assertFalse(self.draft_heads())

    def test_legal_rule_must_be_currently_applicable_before_model_call(self):
        bad_rules = (
            {
                'effective_period': {
                    'start': '2020-01-01',
                    'end': '2025-12-31',
                },
            },
            {'jurisdiction': 'DE'},
            {
                'applicable_document_types': [{
                    'id': 'other-document',
                    'version': '1.0.0',
                    'content_hash': 'd' * 64,
                }],
            },
            {'interpretation': 'DISPUTED'},
            {'interpretation': 'UNKNOWN'},
        )
        for legal_kwargs in bad_rules:
            with self.subTest(legal_kwargs=legal_kwargs):
                case = self.approved_planning_case(
                    legal=True, legal_kwargs=legal_kwargs
                )
                self.provider.responder = (
                    lambda invocation, case=case: self.valid_output(case, invocation)
                )
                before_calls = self.provider.calls
                result = self.drafting.generate(
                    json.dumps(self.generate_request(case)), self.token
                )
                self.assertIsInstance(result, DomainError, result)
                self.assertEqual(result.code, 'GATE_DENIED')
                self.assertEqual(self.provider.calls, before_calls)

    def test_execution_receipt_mismatch_is_terminal_and_replays_without_model_call(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        self.provider.receipt_overrides = {'model_parameters_hash': 'c' * 64}
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'GATE_DENIED')
        self.assertEqual(self.provider.calls, 1)
        replay = self.drafting.generate(json.dumps(request), self.token)
        self.assertEqual(replay, result)
        self.assertEqual(self.provider.calls, 1)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            traces = tx.objects(
                'drafting_rejection_trace', DraftingRejectionTrace
            )
            self.assertEqual(len(traces), 1)
            self.assertEqual(traces[0].error.code, 'GATE_DENIED')
            self.assertEqual(tx.events()[-1].event_type, 'DraftingRejected')

    def test_provider_exception_is_terminal_and_replays_without_second_call(self):
        case = self.approved_planning_case()
        def explode(_):
            raise RuntimeError('synthetic provider failure')
        self.provider.responder = explode
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'UNKNOWN')
        self.assertEqual(self.provider.calls, 1)
        replay = self.drafting.generate(json.dumps(request), self.token)
        self.assertEqual(replay, result)
        self.assertEqual(self.provider.calls, 1)

    def test_multisection_provider_failure_records_failing_request_id(self):
        case = self.approved_planning_case()
        original_invocations = self.drafting._invocations
        invocation_pair = {}

        def two_invocations(*args):
            first = original_invocations(*args)[0]
            second = first.model_copy(update={
                'request': first.request.model_copy(update={'request_id': uuid4()})
            })
            invocation_pair['value'] = (first, second)
            return first, second

        self.drafting._invocations = two_invocations
        def responder(invocation):
            if invocation.request.request_id == invocation_pair['value'][1].request.request_id:
                raise RuntimeError('synthetic second-section failure')
            return self.valid_output(case, invocation)

        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.disposition, 'REJECT')
        self.assertEqual(
            result.request_id,
            invocation_pair['value'][1].request.request_id,
        )
        self.assertEqual(self.provider.calls, 2)
        self.assertFalse(self.draft_heads())
        replay = self.drafting.generate(json.dumps(request), self.token)
        self.assertEqual(replay, result)
        self.assertEqual(self.provider.calls, 2)

    def test_multisection_receipt_mismatch_records_failing_request_id(self):
        case = self.approved_planning_case()
        original_invocations = self.drafting._invocations
        invocation_pair = {}

        def two_invocations(*args):
            first = original_invocations(*args)[0]
            second = first.model_copy(update={
                'request': first.request.model_copy(update={'request_id': uuid4()})
            })
            invocation_pair['value'] = (first, second)
            return first, second

        self.drafting._invocations = two_invocations
        def responder(invocation):
            if invocation.request.request_id == invocation_pair['value'][1].request.request_id:
                self.provider.receipt_overrides = {
                    'model_parameters_hash': 'c' * 64
                }
            return self.valid_output(case, invocation)

        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.disposition, 'REJECT')
        self.assertEqual(
            result.request_id,
            invocation_pair['value'][1].request.request_id,
        )
        self.assertEqual(self.provider.calls, 2)
        self.assertFalse(self.draft_heads())
        replay = self.drafting.generate(json.dumps(request), self.token)
        self.assertEqual(replay, result)
        self.assertEqual(self.provider.calls, 2)

    def test_domain_event_v2_reader_accepts_historical_v1_payload(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        result = self.drafting.generate(
            json.dumps(self.generate_request(case)), self.token
        )
        self.assertIsInstance(result, CommandResult, result)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            event = tx.events()[-1]
        raw = canonical(event)
        historical = decode(
            ('urn:lukart:work:DomainEvent:1.0.0', raw, digest(event)),
            DomainEvent,
        )
        self.assertEqual(historical, event)

    def test_domain_event_v1_rejects_v2_only_terminal_events(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        result = self.drafting.generate(
            json.dumps(self.generate_request(case)), self.token
        )
        self.assertIsInstance(result, CommandResult, result)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            event = tx.events()[-1]
        for event_type in ('DraftingRejected', 'DraftingAbstained'):
            with self.subTest(event_type=event_type):
                payload = event.model_dump(mode='json')
                payload['event_type'] = event_type
                with self.assertRaises(ValueError):
                    decode(
                        ('urn:lukart:work:DomainEvent:1.0.0',
                         canonical(payload), digest(payload)),
                        DomainEvent,
                    )

    def test_domain_event_v2_reader_accepts_drafting_rejected(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        result = self.drafting.generate(
            json.dumps(self.generate_request(case)), self.token
        )
        self.assertIsInstance(result, CommandResult, result)
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            event = tx.events()[-1]
        payload = event.model_dump(mode='json')
        payload['event_type'] = 'DraftingRejected'
        decoded = decode(
            (f'urn:lukart:work:DomainEvent:2.0.0',
             canonical(payload), digest(payload)),
            DomainEvent,
        )
        self.assertEqual(decoded.event_type, 'DraftingRejected')

    def test_reference_outside_approved_section_contract_is_rejected(self):
        case = self.approved_planning_case()
        outside = self.apply('AddRequest', {
            'filing': case['filing'].model_dump(mode='json'),
            'request_type': 'POST_SNAPSHOT_SYNTHETIC',
            'text': 'Outside frozen drafting inputs',
            'claims': [case['claim'].model_dump(mode='json')],
            'evidence': [case['evidence'].model_dump(mode='json')],
        })[0].refs[0]
        def responder(invocation):
            output = self.valid_output(case, invocation)
            output['section']['statements'][0]['refs'].append(outside.model_dump(mode='json'))
            return output
        self.provider.responder = responder
        result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'GATE_DENIED')
        self.assertFalse(self.draft_heads())

    def test_request_objective_cannot_disappear(self):
        case = self.approved_planning_case(requirements=('ATTACHMENTS',))
        def responder(invocation):
            output = self.valid_output(case, invocation)
            output['section']['statements'] = output['section']['statements'][:1]
            return output
        self.provider.responder = responder
        result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'GATE_DENIED')
        self.assertFalse(self.draft_heads())

    def test_legal_statement_requires_live_rule_verified_citation_and_verified_source(self):
        case = self.approved_planning_case(
            requirements=('REQUESTS', 'ATTACHMENTS', 'CITATIONS'),
            legal=True,
        )
        def responder(invocation):
            output = self.valid_output(case, invocation)
            output['section']['statements'].append(self.statement(
                'Synthetic legal proposition backed by verified authority.',
                'LEGAL',
                'SOURCE_BACKED',
                (case['legal_rule'],),
                citations=(case['citation'],),
            ))
            return output
        self.provider.responder = responder
        result = self.drafting.generate(
            json.dumps(self.generate_request(case)), self.token
        )
        self.assertIsInstance(result, CommandResult, result)
        self.assertEqual(result.state, 'APPLIED')
        self.assertEqual(self.provider.calls, 1)
        draft = self.get(result.refs[0])
        legal = [
            statement
            for section in draft.sections
            for statement in section.statements
            if statement.statement_type == 'LEGAL'
        ]
        self.assertEqual(len(legal), 1)
        self.assertEqual(legal[0].refs, (case['legal_rule'],))
        self.assertEqual(legal[0].citations, (case['citation'],))
        self.assertEqual(draft.status, 'GENERATED')

    def test_revoked_legal_interpretation_approval_blocks_before_model_call(self):
        case = self.approved_planning_case(
            requirements=('REQUESTS', 'ATTACHMENTS', 'CITATIONS'),
            legal=True,
        )
        self.apply('RevokeDecision', target=case['legal_approval'])
        with self.authority.session(self.token) as principal:
            with self.repo.transaction(self.tenant, self.case_id) as tx:
                records = tx.records()
                heads = {(item.kind, item.id): item for item in tx.heads()}
                with self.assertRaises(Violation) as caught:
                    self.drafting._legal_rule(
                        case['legal_rule'], records, heads, principal,
                        heads[('Case', self.case_id)],
                        records[case['filing']],
                        self.drafting.clock().date(),
                    )
                self.assertEqual(caught.exception.code, 'GATE_DENIED')

        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        result = self.drafting.generate(
            json.dumps(self.generate_request(case)), self.token
        )
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'STALE')
        self.assertEqual(self.provider.calls, 0)
        self.assertFalse(self.draft_heads())

    def test_plan_approval_revocation_blocks_model_call(self):
        case = self.approved_planning_case()
        self.apply('RevokeDecision', target=case['plan_approval'])
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'GATE_DENIED')
        self.assertEqual(self.provider.calls, 0)
        self.assertFalse(self.draft_heads())

    def test_plan_approval_change_between_proposal_and_commit_is_conflict(self):
        case = self.approved_planning_case()
        mutated = {'done': False}
        def responder(invocation):
            if not mutated['done']:
                mutated['done'] = True
                self.apply('RevokeDecision', target=case['plan_approval'])
            return self.valid_output(case, invocation)
        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'CONFLICT')
        self.assertEqual(self.provider.calls, 1)
        self.assertFalse(self.draft_heads())

    def test_snapshot_acceptance_change_between_proposal_and_commit_is_conflict(self):
        case = self.approved_planning_case()
        mutated = {'done': False}
        def responder(invocation):
            if not mutated['done']:
                mutated['done'] = True
                self.apply('RevokeDecision', target=case['snapshot_acceptance'])
            return self.valid_output(case, invocation)
        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'CONFLICT')
        self.assertEqual(self.provider.calls, 1)
        self.assertFalse(self.draft_heads())

    def test_case_change_between_proposal_and_commit_is_conflict_without_draft(self):
        case = self.approved_planning_case()
        mutated = {'done': False}
        def responder(invocation):
            if not mutated['done']:
                mutated['done'] = True
                self.apply('AddParty', {
                    'party_type': 'PERSON',
                    'display_name': 'Synthetic concurrent mutation',
                    'identity_evidence': [],
                })
            return self.valid_output(case, invocation)
        self.provider.responder = responder
        request = self.generate_request(case)
        result = self.drafting.generate(json.dumps(request), self.token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'CONFLICT')
        self.assertEqual(self.provider.calls, 1)
        self.assertFalse(self.draft_heads())

    def test_ai_actor_and_model_status_injection_are_denied(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        ai = Principal(
            Actor(id=uuid4(), kind='AI'),
            self.tenant,
            self.case_id,
            self.principal.actions,
        )
        ai_token = self.authority.provision(ai)
        result = self.drafting.generate(json.dumps(self.generate_request(case)), ai_token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, 'FORBIDDEN')
        self.assertEqual(self.provider.calls, 0)

        def injected(invocation):
            output = self.valid_output(case, invocation)
            output['status'] = 'FINAL'
            return output
        self.provider.responder = injected
        result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'SCHEMA_INVALID')
        self.assertFalse(self.draft_heads())

    def test_transaction_rollback_covers_draft_trace_audit_and_outbox(self):
        case = self.approved_planning_case()
        self.provider.responder = lambda invocation: self.valid_output(case, invocation)
        original = self.drafting._dependencies
        def fail_after_trace(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('synthetic rollback')
        self.drafting._dependencies = fail_after_trace
        result = self.drafting.generate(json.dumps(self.generate_request(case)), self.token)
        self.assertIsInstance(result, DraftingTerminalResult, result)
        self.assertEqual(result.error.code, 'UNKNOWN')
        with self.repo.transaction(self.tenant, self.case_id) as tx:
            self.assertFalse(any(item.kind == 'Draft' for item in tx.heads()))
            self.assertFalse(tx.objects('drafting_trace', DraftingTrace))
            self.assertEqual(tx.events(), tx.outbox())


if __name__ == '__main__':
    unittest.main()
