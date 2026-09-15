"""Isolated synthetic-test process: prove replay survives process termination.

Not an application entry point. The test host provisions a fresh capability.
"""
import json
import sys
from uuid import UUID
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from tests.test_stage02 import DSN, ACTIONS

if __name__ == '__main__':
    payload = json.load(sys.stdin)
    request = payload['request']
    authority = TokenAuthority()
    principal = Principal(Actor.model_validate_json(json.dumps(payload['actor'])), UUID(request['meta']['tenant_id']),
                          UUID(request['meta']['case_id']), ACTIONS)
    token = authority.provision(principal)
    result = CommandService(PostgresRepository(DSN), authority).execute(json.dumps(request), token)
    print(result.model_dump_json())
