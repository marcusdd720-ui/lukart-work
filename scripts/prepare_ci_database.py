"""Prepare the disposable PostgreSQL service used by CI; no local secrets read."""
import os

import psycopg
from psycopg import sql

from lukart_work.storage.migrations import grant_runtime, migrate


with psycopg.connect(os.environ['LUKART_TEST_ADMIN_DSN'], autocommit=True) as connection:
    if not connection.execute(
        "SELECT 1 FROM pg_roles WHERE rolname='lw_core_runtime'"
    ).fetchone():
        connection.execute(
            sql.SQL(
                'CREATE ROLE lw_core_runtime LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}'
            ).format(sql.Literal(os.environ['LUKART_TEST_RUNTIME_PASSWORD']))
        )
    migrate(connection)
    grant_runtime(connection, 'lw_core_runtime')
print('Disposable CI core + storage database prepared.')
