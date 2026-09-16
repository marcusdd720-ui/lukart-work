"""Explicit owner-only, transactional, checksummed schema upgrade from Stage 02."""
from hashlib import sha256
from pathlib import Path
from lukart_work.validation.rules import Violation

ROOT = Path(__file__).resolve().parent
MIGRATIONS = ((1, ROOT.parent / 'core/migration.sql'), (2, ROOT / 'migration.sql'))


def migrate(connection):
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(73003001)')
        connection.execute('CREATE SCHEMA IF NOT EXISTS lw_migrations')
        connection.execute('REVOKE ALL ON SCHEMA lw_migrations FROM PUBLIC')
        connection.execute('CREATE TABLE IF NOT EXISTS lw_migrations.ledger (version integer PRIMARY KEY, checksum text NOT NULL)')
        saved = dict(connection.execute('SELECT version,checksum FROM lw_migrations.ledger ORDER BY version').fetchall())
        if set(saved) not in (set(), {1}, {1, 2}):
            raise Violation('UNKNOWN')
        for version, path in MIGRATIONS:
            script = path.read_text(encoding='utf-8')
            checksum = sha256(script.encode()).hexdigest()
            if version in saved:
                if saved[version] != checksum:
                    raise Violation('INVALID_HASH')
                continue
            if version == 1 and connection.execute("SELECT to_regclass('lw_core.cases')").fetchone()[0]:
                expected = {
                    'cases': 'tenant_id case_id sequence',
                    'revisions': 'tenant_id case_id revision_key kind entity_id revision contract payload content_hash',
                    'heads': 'tenant_id case_id kind entity_id revision_key',
                    'objects': 'tenant_id case_id category object_id contract payload content_hash original_bytes',
                    'commands': 'tenant_id case_id idempotency_key input_hash contract payload content_hash',
                    'events': 'tenant_id case_id event_id sequence contract payload content_hash event_order',
                    'outbox': 'tenant_id case_id event_id',
                }
                actual = {}
                for table, column in connection.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='lw_core' ORDER BY table_name,ordinal_position"):
                    actual.setdefault(table, []).append(column)
                if actual != {k: v.split() for k, v in expected.items()}:
                    raise Violation('UNKNOWN')
                # Do not certify an unprotected look-alike as the Stage 02 baseline.
                protected = connection.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='lw_core' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity").fetchone()[0]
                if protected != 7:
                    raise Violation('FORBIDDEN')
            else:
                connection.execute(script)
            connection.execute('INSERT INTO lw_migrations.ledger VALUES (%s,%s)', (version, checksum))


def grant_runtime(connection, role):
    from psycopg import sql
    for statement in (
        'GRANT USAGE ON SCHEMA lw_core,lw_storage TO {}',
        'GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA lw_core,lw_storage TO {}',
        'GRANT UPDATE ON lw_core.cases,lw_core.heads TO {}',
        'GRANT DELETE ON lw_storage.blobs TO {}',
        'GRANT USAGE ON ALL SEQUENCES IN SCHEMA lw_core,lw_storage TO {}',
    ):
        connection.execute(sql.SQL(statement).format(sql.Identifier(role)))
