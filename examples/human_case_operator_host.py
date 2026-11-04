"""Trusted Windows HUMAN host configuration using SSPI and an external SID policy."""
import os
from pathlib import Path
import runpy
from lukart_work.operator import GeneratorPismOperator
from native_windows.windows_identity import WindowsHumanAuthManager, create_authenticator

def trusted_module(variable):
    path=Path(os.environ[variable])
    if not path.is_absolute() or not path.is_file() or path.suffix!=".py":
        raise ValueError("TRUSTED_PRIVATE_PYTHON_CONFIGURATION_REQUIRED")
    return runpy.run_path(str(path))

def build_operator():
    host=trusted_module("LUKART_TRUSTED_CASE_HOST")
    operator=host["build_operator"]()
    if not isinstance(operator,GeneratorPismOperator) or operator.binding is not None:
        raise ValueError("TRUSTED_CASE_OPERATOR_REQUIRED")
    authenticator=create_authenticator(operator)
    if not isinstance(authenticator,WindowsHumanAuthManager) or not authenticator.has_enabled_bindings:
        raise ValueError("ENABLED_WINDOWS_HUMAN_POLICY_REQUIRED")
    import psycopg
    with psycopg.connect(operator.core.repository._dsn) as connection:
        readonly=connection.execute("SHOW transaction_read_only").fetchone()[0]
        role=connection.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        if readonly!="off" or role!=(False,False):
            raise ValueError("RESTRICTED_WRITE_CAPABLE_RUNTIME_REQUIRED")
    operator._human_authenticator=authenticator
    return operator
