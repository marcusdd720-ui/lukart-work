"""Trusted host configuration bridge; deliberately grants no identity or permissions.

The administrator supplies two private Python files via the named environment
variables. The identity adapter authenticates the actual human and delivers the
fresh capability privately. Missing identity, authority or write access fails closed.
"""
import os
from pathlib import Path
import runpy

from lukart_work.core.security import Principal
from lukart_work.operator import GeneratorPismOperator


def trusted_module(variable):
    path = Path(os.environ[variable])
    if not path.is_absolute() or not path.is_file() or path.suffix != '.py':
        raise ValueError('TRUSTED_PRIVATE_PYTHON_CONFIGURATION_REQUIRED')
    return runpy.run_path(str(path))


def build_operator():
    host = trusted_module('LUKART_TRUSTED_CASE_HOST')
    identity = trusted_module('LUKART_HUMAN_IDENTITY_ADAPTER')
    operator = host['build_operator']()
    if not isinstance(operator, GeneratorPismOperator) or operator.binding is not None:
        raise ValueError('TRUSTED_CASE_OPERATOR_REQUIRED')
    # This function MUST authenticate against the administrator's actual identity
    # and grant mapping. Neither actor IDs nor action sets are invented here.
    principal = identity['authenticate_human'](operator)
    if not isinstance(principal, Principal) or principal.actor.kind != 'HUMAN':
        raise ValueError('AUTHENTICATED_HUMAN_REQUIRED')
    for action in ('CreateCase', 'AmendDraft', 'GetCaseHead', 'GetRevision'):
        principal.require(principal.tenant_id, principal.case_id, action)
    import psycopg
    with psycopg.connect(operator.core.repository._dsn) as connection:
        readonly = connection.execute('SHOW transaction_read_only').fetchone()[0]
        role = connection.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        if readonly != 'off' or role != (False, False):
            raise ValueError('RESTRICTED_WRITE_CAPABLE_RUNTIME_REQUIRED')
    token = operator.core.authority.provision(principal)
    try:
        identity['deliver_capability_privately'](token)
    except Exception:
        operator.core.authority.revoke(token)
        raise
    return operator
