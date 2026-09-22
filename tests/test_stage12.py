"""Stage 12 Audit / Provenance integration and adversarial tests."""
import unittest
from uuid import uuid4

from lukart_work.audit import AuditPackage, AuditService, AuditTrace, audit_pin, verify_audit_package
from lukart_work.contracts.messages import DomainError
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from lukart_work.validation.rules import Violation, digest

from tests import test_stage02 as core


@unittest.skipUnless(core.DSN, 'PostgreSQL integration NOT EXECUTED: configure LUKART_TEST_DSN or local cluster')
class Stage12Tests(unittest.TestCase):
    def setUp(self):
        self.tenant, self.case_id = uuid4(), uuid4()
        self.actor = Actor(id=uuid4(), kind='HUMAN')
        self.authority = TokenAuthority()
        self.principal = Principal(self.actor, self.tenant, self.case_id, core.ACTIONS | {'AuditRead'})
        self.token = self.authority.provision(self.principal)
        self.repo = PostgresRepository(core.DSN)
        self.service = CommandService(self.repo, self.authority)
        self.audit = AuditService(self.repo, self.authority)
        self.sequence = 0
        self.create_case()

    def test_package_is_deterministic_and_exact_chain(self):
        first = self.audit.package(self.token)
        second = self.audit.package(self.token)
        self.assertIsInstance(first, AuditPackage, first)
        self.assertEqual(first, second)
        self.assertEqual(first.case_sequence, self.sequence)
        self.assertEqual(first.implementation, audit_pin())
        self.assertEqual(first.chain_head_hash, first.event_hashes[-1])
        self.assertEqual(first.outbox_event_ids, tuple(event.audit.event_id for event in first.events))
        self.assertEqual(verify_audit_package(first, expected_implementation=audit_pin()), digest(first))

    def test_trace_follows_fact_to_source_and_audit_events(self):
        fact, _party, _evidence, _source_id = self.fact()
        trace = self.audit.trace(self.token, fact)
        self.assertIsInstance(trace, AuditTrace, trace)
        self.assertEqual(trace.completeness, 'COMPLETE')
        self.assertIn(fact, trace.revisions)
        self.assertTrue(trace.sources)
        self.assertTrue(trace.event_ids)
        self.assertEqual(trace.package_hash, digest(self.audit.package(self.token)))

    def test_tampered_declared_event_hash_is_rejected(self):
        package = self.audit.package(self.token)
        body = package.model_dump(mode='json')
        body['event_hashes'][-1] = '0' * 64
        body['chain_head_hash'] = '0' * 64
        forged = AuditPackage.model_validate(body)
        with self.assertRaises(Violation) as ctx:
            verify_audit_package(forged)
        self.assertEqual(ctx.exception.code, 'INVALID_HASH')

    def test_audit_read_is_authorized_and_ai_is_not_a_trust_boundary(self):
        denied = self.authority.provision(
            Principal(self.actor, self.tenant, self.case_id, core.ACTIONS)
        )
        result = self.audit.package(denied)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'FORBIDDEN')

        ai = Actor(id=uuid4(), kind='AI')
        ai_token = self.authority.provision(
            Principal(ai, self.tenant, self.case_id, frozenset({'AuditRead'}))
        )
        result = self.audit.package(ai_token)
        self.assertIsInstance(result, DomainError)
        self.assertEqual(result.code, 'FORBIDDEN')

    def test_audit_package_contains_hashes_not_raw_source_bytes(self):
        self.fact()
        package = self.audit.package(self.token)
        self.assertIsInstance(package, AuditPackage, package)
        self.assertNotIn('Synthetic payment receipt.', package.model_dump_json())


for _name in ('request', 'run_request', 'apply', 'query', 'get', 'create_case', 'party', 'fact'):
    setattr(Stage12Tests, _name, getattr(core.Stage02Tests, _name))


if __name__ == '__main__':
    unittest.main()
