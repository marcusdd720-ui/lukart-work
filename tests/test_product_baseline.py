"""LW-PB-01 contract and current-state characterization, not product certification.

Portable tests execute the real Core/auth/parser on a labelled in-memory repository.
PostgreSQL tests are separate: no mock replaces CommandService or its gates.
The current denials must be revisited when a later authorized package adds a path.
"""
import ast
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha1
import json
from pathlib import Path
import subprocess
from typing import get_args
import unittest
from uuid import UUID

from lukart_work.contracts.messages import CommandResult, DomainError
from lukart_work.core.requests import Operation
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from lukart_work.validation.rules import digest, ref
from tests import test_stage02 as pg_core

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'acceptance/product-baseline-v1.json'


def validate_contract(value):
    """Integrity of the acceptance specification; this cannot validate the product."""
    if value['scope'] != 'LW-PB-01' or value['repository'] != 'marcusdd720-ui/lukart-work':
        raise ValueError('WRONG_SCOPE')
    if value['base_sha'] != 'f88c3137ef96542ac836478d0f266dcc883ec406':
        raise ValueError('BASE_CHANGED_REBASE_REQUIRED')
    for key in ('catalogue', 'requirements', 'acceptance', 'human_gates'):
        ids = [item['id'] for item in value[key]]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('DUPLICATE_OR_EMPTY_IDS')
    if {x['id'] for x in value['catalogue']} != {
        'PL-PRE-PAYMENT-1', 'PL-PRE-COMPLAINT-1', 'PL-PRE-REPLY-1'
    }:
        raise ValueError('CATALOGUE_NOT_FROZEN')
    if value['jurisdiction']['country'] != 'PL' or value['jurisdiction']['currency'] != 'PLN':
        raise ValueError('JURISDICTION_NOT_FROZEN')
    from lukart_work.contracts.messages import REQUIRED_CHECKS
    if tuple(value['required_checks']) != REQUIRED_CHECKS:
        raise ValueError('CHECK_COVERAGE')
    members = [x['name'] for x in value['final_package']]
    if len(members) != len(set(members)) or set(members) != {
        'final.docx', 'final.pdf', 'document.json', 'validation.json', 'sources.json',
        'evidence-map.json', 'argument-map.json', 'audit.json', 'release.json', 'manifest.json'
    }:
        raise ValueError('PACKAGE_COVERAGE')
    acceptance_ids = {x['id'] for x in value['acceptance']}
    requirement_ids = {x['id'] for x in value['requirements']}
    for item in value['requirements']:
        if not all(item.get(key) for key in ('goal', 'source', 'source_paths', 'stages', 'verifier', 'definition_of_done', 'acceptance_ids')):
            raise ValueError('REQUIREMENT_TRACEABILITY')
        if not set(item['acceptance_ids']) <= acceptance_ids:
            raise ValueError('UNKNOWN_ACCEPTANCE')
        if not set(item['source_paths']) <= set(value['source_index']):
            raise ValueError('UNPINNED_SOURCE')
        if item['status']['certified']:
            raise ValueError('NO_BUILDER_CERTIFICATION')
    for item in value['acceptance']:
        if not set(item['blockers']) <= requirement_ids:
            raise ValueError('UNKNOWN_BLOCKER')
        if not all(item.get(key) for key in ('procedure', 'expected', 'verifier', 'definition_of_done')):
            raise ValueError('ACCEPTANCE_NOT_REPRODUCIBLE')
    if not all(value['separation'].get(role) for role in ('builder', 'verifier', 'promoter')):
        raise ValueError('SEPARATION_REQUIRED')
    if not value['product_e2e']['public_only'] or value['product_e2e']['state'] != 'BLOCKED':
        raise ValueError('NO_CURRENT_PRODUCT_PASS')
    formal_fields = {'document_type_id', 'recipient_organ', 'parties_roles', 'place_date',
                     'case_reference_signature', 'title', 'requests_demands', 'reasoning',
                     'facts', 'evidence', 'legal_authorities', 'attachments', 'signature_requirements',
                     'representation_power', 'render_requirements', 'final_approval_requirements'}
    for document_type in value['catalogue']:
        if document_type['current_support'] != 'NOT SUPPORTED / FUTURE':
            raise ValueError('NO_UNTESTED_TYPE_SUPPORT')
        fields = document_type['formal_requirements']
        if len(fields) != len(formal_fields) or {f['field'] for f in fields} != formal_fields:
            raise ValueError('FORMAL_FIELD_COVERAGE')
        for field in fields:
            if not all(field.get(key) for key in ('requirement_id', 'source', 'support', 'implementation_mapping', 'verifier', 'acceptance_test', 'definition_of_done')):
                raise ValueError('TYPE_TRACEABILITY')
    steps = value['full_path_steps']
    if [step['id'] for step in steps] != [f'S{i:02}' for i in range(1, 15)]:
        raise ValueError('FULL_PATH_ORDER')
    for step in steps:
        if not all(step.get(key) for key in ('input', 'preconditions', 'authority', 'state_transition', 'output', 'evidence', 'negative_cases', 'verifier', 'definition_of_done')):
            raise ValueError('INCOMPLETE_STEP_CONTRACT')
        if not set(step['requirements']) <= requirement_ids:
            raise ValueError('STEP_REQUIREMENT_UNKNOWN')


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text())

    def test_traceability_and_frozen_scope(self):
        validate_contract(self.contract)
        self.assertEqual({s for r in self.contract['requirements'] for s in r['stages']},
                         {f'{i:02}' for i in range(3, 14)})

    def test_missing_unknown_duplicate_and_self_certification_fail_closed(self):
        mutations = [
            lambda c: c['final_package'].pop(),
            lambda c: c['required_checks'].pop(),
            lambda c: c['requirements'][0].update(verifier=''),
            lambda c: c['requirements'][0].update(acceptance_ids=['MISSING']),
            lambda c: c['source_index'].pop('AGENTS.md'),
            lambda c: c['catalogue'].append(c['catalogue'][0]),
            lambda c: c['requirements'][0]['status'].update(certified=True),
            lambda c: c['product_e2e'].update(state='PASS'),
            lambda c: c['jurisdiction'].update(country='DE'),
            lambda c: c['catalogue'][0]['formal_requirements'].pop(),
            lambda c: c['catalogue'][0].update(current_support='SUPPORTED'),
            lambda c: c['full_path_steps'][0].update(authority=''),
            lambda c: c['full_path_steps'].pop(),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation.__code__.co_firstlineno):
                bad = deepcopy(self.contract)
                mutation(bad)
                with self.assertRaises(ValueError):
                    validate_contract(bad)

    def test_sources_are_exact_base_blobs_and_production_unchanged(self):
        base = self.contract['base_sha']
        for path, pin in self.contract['source_index'].items():
            saved = (ROOT / path).read_bytes()
            actual = sha1(b'blob ' + str(len(saved)).encode() + b'\0' + saved).hexdigest()
            self.assertEqual(actual, pin['git_blob_sha'], path)
            self.assertEqual(pin['base_sha'], base)
        # Works in shallow exact-candidate CI: source pins came from verified base tree.
        for path, expected in self.contract['production_tree_pins'].items():
            current = subprocess.check_output(['git', 'ls-tree', 'HEAD', '--', path], cwd=ROOT, text=True)
            self.assertEqual(current.split()[2], expected, path)
        diff = subprocess.check_output(['git', 'diff', 'HEAD', '--', 'lukart_work', 'schemas', '.github', 'pyproject.toml'], cwd=ROOT)
        self.assertEqual(diff, b'')

    def test_pure_final_evaluator_has_no_production_call_site(self):
        calls = []
        for path in (ROOT / 'lukart_work').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', None)
                    if name == 'evaluate_release':
                        calls.append((path.relative_to(ROOT).as_posix(), node.lineno))
        self.assertEqual(calls, [], 'A later public path requires new acceptance evidence, not this base characterization')


class MemoryRepository:
    """Test-only repository port. No assertion here proves PostgreSQL/RLS durability."""
    def __init__(self):
        self.state = {'sequence': 0, 'records': {}, 'objects': {}, 'commands': {}, 'events': (), 'outbox': ()}

    @contextmanager
    def transaction(self, tenant, case):
        before = deepcopy(self.state)
        tx = MemoryTransaction(self, (tenant, case))
        try:
            yield tx
        except BaseException:
            self.state = before
            raise


class MemoryTransaction:
    def __init__(self, repository, scope):
        self.repository, self.scope = repository, scope

    @property
    def state(self):
        return self.repository.state

    def sequence(self):
        return self.state['sequence']

    def set_sequence(self, value):
        self.state['sequence'] = value

    def records(self):
        return dict(self.state['records'])

    def heads(self):
        heads = {}
        for entity in self.state['records'].values():
            key = (entity.kind, entity.id)
            if key not in heads or heads[key].revision < entity.revision:
                heads[key] = entity
        return tuple(heads.values())

    def objects(self, category, cls):
        return tuple(v for (kind, _), v in self.state['objects'].items() if kind == category)

    def append(self, entity):
        self.state['records'][ref(entity)] = entity

    def replay(self, key, input_hash):
        value = self.state['commands'].get(key)
        if value is not None:
            from lukart_work.validation.rules import Violation
            if value[0] != input_hash:
                raise Violation('IDEMPOTENCY_CONFLICT')
            return value[1]

    def last_event_hash(self):
        return digest(self.state['events'][-1]) if self.state['events'] else None

    def finish(self, request, input_hash, result, events):
        self.state['commands'][request.meta.idempotency_key] = (input_hash, result)
        self.state['events'] += tuple(events)
        self.state['outbox'] += tuple(events)


class PublicGateTests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case = UUID(int=1000), UUID(int=1)
        self.authority = TokenAuthority()
        self.principal = Principal(Actor(id=UUID(int=900), kind='HUMAN'), self.tenant, self.case,
                                   frozenset(get_args(Operation)))
        self.token = self.authority.provision(self.principal)
        self.repo = MemoryRepository()
        self.service = CommandService(self.repo, self.authority,
                                      clock=lambda: datetime(2026, 10, 2, tzinfo=timezone.utc))
        self.counter = 10
        self.sequence = 0
        request = self.request('CreateCase', {'title': 'Synthetic PB01', 'jurisdiction': 'PL',
                                             'retention_policy': {'id': 'synthetic', 'version': '1.0.0', 'content_hash': 'a' * 64}})
        result = self.service.execute(json.dumps(request), self.token)
        self.assertIsInstance(result, CommandResult, result)
        self.sequence = result.case_sequence
        self.assertEqual(self.sequence, 1)
        self.create_request, self.create_result = request, result

    def request(self, operation, data=None):
        self.counter += 1
        identifier = str(UUID(int=self.counter))
        return {'contract': 'urn:lukart:work:CoreRequest:1.0.0', 'operation': operation,
                'meta': {'command_id': identifier, 'tenant_id': str(self.tenant), 'case_id': str(self.case),
                         'idempotency_key': identifier, 'expected_case_sequence': self.sequence,
                         'correlation_id': identifier}, 'data': data or {}}

    def approval_data(self):
        # Valid Core intent envelope, deliberately no invented render/approval authority.
        # The unconditional denial precedes Decision construction and target resolution.
        return {'decision_type': 'DOCUMENT_APPROVAL', 'outcome': 'ACCEPT',
                'rationale': 'Synthetic denied intent, no purported final approval'}

    def denied_without_writes(self, request, code='GATE_DENIED', token=None):
        before = deepcopy(self.repo.state)
        result = self.service.execute(json.dumps(request), self.token if token is None else token)
        self.assertIsInstance(result, DomainError, result)
        self.assertEqual(result.code, code)
        self.assertEqual(self.repo.state, before)
        self.assertFalse(result.retryable)
        return result

    def test_create_case_is_real_public_execution_and_replay(self):
        self.assertEqual(self.service.execute(json.dumps(self.create_request), self.token), self.create_result)
        self.assertEqual(self.repo.state['sequence'], 1)
        self.assertEqual(len(self.repo.state['events']), 1)
        self.assertEqual(self.repo.state['events'], self.repo.state['outbox'])

    def test_document_approval_is_gate_denied_for_authorized_human(self):
        request = self.request('RecordDecision', self.approval_data())
        self.denied_without_writes(request)
        self.denied_without_writes(request)

    def test_request_release_is_gate_denied_for_authorized_human(self):
        request = self.request('RequestRelease')
        self.denied_without_writes(request)
        self.denied_without_writes(request)

    def test_caller_pass_and_final_payload_cannot_bypass_release(self):
        self.denied_without_writes(self.request('RequestRelease', {
            'status': 'FINAL', 'checks': [{'check': 'render', 'outcome': 'PASS'}], 'render_hashes': ['a' * 64]}))

    def test_authentication_ai_and_scope_fail_before_business_gate(self):
        request = self.request('RequestRelease')
        self.denied_without_writes(request, 'FORBIDDEN', 'unprovisioned')
        for principal in (
            Principal(Actor(id=UUID(int=901), kind='AI'), self.tenant, self.case, frozenset(get_args(Operation))),
            Principal(self.principal.actor, UUID(int=1001), self.case, self.principal.actions),
            Principal(self.principal.actor, self.tenant, self.case, frozenset()),
        ):
            self.denied_without_writes(request, 'FORBIDDEN', self.authority.provision(principal))

    def test_legacy_generation_validation_and_certification_do_not_supply_final_authority(self):
        for operation in ('GenerateDocument', 'ValidateDraft'):
            self.denied_without_writes(self.request(operation))
        self.denied_without_writes(self.request('RecordDecision', {'decision_type': 'CERTIFICATION'}))


@unittest.skipUnless(pg_core.DSN and pg_core.ADMIN, 'PB01 real PostgreSQL evidence NOT VERIFIED: both isolated DSNs required')
class PostgreSQLGateTests(unittest.TestCase):
    def test_authorized_human_denials_rollback_all_scoped_tables(self):
        import psycopg
        from psycopg import sql
        harness = pg_core.Stage02Tests()
        harness.setUp()  # CreateCase via real public service, role and PostgreSQL RLS.
        def inventory():
            with psycopg.connect(pg_core.ADMIN) as connection:
                return {table: connection.execute(sql.SQL('SELECT * FROM lw_core.{} WHERE tenant_id=%s AND case_id=%s ORDER BY 1,2').format(sql.Identifier(table)),
                                                  (harness.tenant, harness.case_id)).fetchall()
                        for table in ('cases', 'revisions', 'heads', 'objects', 'commands', 'events', 'outbox')}
        data = {'decision_type': 'DOCUMENT_APPROVAL', 'outcome': 'ACCEPT',
                'rationale': 'Synthetic denied intent without fabricated render authority'}
        for request in (harness.request('RecordDecision', data), harness.request('RequestRelease')):
            before = inventory()
            for _ in range(2):
                harness.assert_error(request, 'GATE_DENIED')
                self.assertEqual(inventory(), before)

    def test_denials_also_hold_after_real_stage10_validation(self):
        from tests.test_stage10 import ValidationTests
        harness = ValidationTests()
        harness.setUp()
        _case, draft = harness.generated()
        review_id = harness.review(draft)
        result, run_id, _request = harness.validate(draft, review_id)
        validated = harness.get(result.refs[0])
        self.assertEqual(validated.status, 'VALIDATED')
        projection = harness.projection(run_id)
        self.assertTrue(projection.eligible_for_approval)
        self.assertEqual(projection.execution.run.render_hashes, ())
        self.assertEqual(projection.execution.run.checks[-1].outcome, 'NOT_RUN')
        before = harness.state()
        harness.assert_error(harness.request('RecordDecision', {
            'decision_type': 'DOCUMENT_APPROVAL', 'targets': [ref(validated).model_dump(mode='json')],
            'outcome': 'ACCEPT', 'rationale': 'Synthetic denied intent; rendered artifacts do not exist'}), 'GATE_DENIED')
        harness.assert_error(harness.request('RequestRelease'), 'GATE_DENIED')
        self.assertEqual(harness.state(), before)
        # This upstream synthetic fixture contains privileged legal-authority setup; it is NOT
        # a supported-letter public E2E acceptance and must never be reported as one.
