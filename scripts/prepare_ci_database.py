"""Prepare the disposable PostgreSQL service used by CI; no local secrets read."""
import os
from pathlib import Path
import psycopg
from psycopg import sql
from lukart_work.storage.migrations import configure_egress_roles

ROOT = Path(__file__).resolve().parents[1]
with psycopg.connect(os.environ['LUKART_TEST_ADMIN_DSN']) as connection:
    if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='lw_core_runtime'").fetchone():
        connection.execute(sql.SQL('CREATE ROLE lw_core_runtime LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}').format(sql.Literal(os.environ['LUKART_TEST_RUNTIME_PASSWORD'])))
    if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='lw_ai_egress_host'").fetchone():
        connection.execute(sql.SQL('CREATE ROLE lw_ai_egress_host LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(sql.Literal(os.environ['LUKART_TEST_EGRESS_HOST_PASSWORD'])))
    connection.execute((ROOT / 'lukart_work/core/migration.sql').read_text())
    connection.execute((ROOT / 'lukart_work/core/migration_ai_egress.sql').read_text())
    connection.execute('GRANT USAGE ON SCHEMA lw_core TO lw_core_runtime')
    connection.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA lw_core TO lw_core_runtime')
    connection.execute('GRANT UPDATE ON lw_core.cases,lw_core.heads TO lw_core_runtime')
    configure_egress_roles(connection, 'lw_core_runtime', 'lw_ai_egress_host')
    connection.execute('GRANT USAGE ON ALL SEQUENCES IN SCHEMA lw_core TO lw_core_runtime')
print('Disposable CI database prepared.')
