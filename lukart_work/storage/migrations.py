"""Explicit owner-only, transactional, checksummed schema upgrade from Stage 02."""
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from lukart_work.validation.rules import Violation

ROOT = Path(__file__).resolve().parent
MIGRATIONS = ((1, ROOT.parent / 'core/migration.sql'), (2, ROOT / 'migration.sql'))


def schema_fingerprint(connection, schema):
    """Compare executable schema structure, not just table names and RLS flags."""
    queries = (
        "SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind IN ('r','p','v','m') ORDER BY c.relname",
        "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE n.nspname=%s AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum",
        "SELECT c.relname,t.conname,t.contype,t.convalidated,pg_get_constraintdef(t.oid,true) FROM pg_constraint t JOIN pg_class c ON c.oid=t.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s ORDER BY c.relname,t.conname",
        "SELECT tablename,policyname,permissive,roles::text,cmd,qual,with_check FROM pg_policies WHERE schemaname=%s ORDER BY tablename,policyname",
        "SELECT c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,true) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND NOT t.tgisinternal ORDER BY c.relname,t.tgname",
        "SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s ORDER BY p.proname",
        "SELECT c.relname,coalesce(r.rolname,'PUBLIC'),a.privilege_type,a.is_grantable FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname=%s AND c.relname IN ('ai_egress_budgets','ai_egress_grants') ORDER BY c.relname,r.rolname,a.privilege_type,a.is_grantable",
        "SELECT c.relname,col.attname,coalesce(r.rolname,'PUBLIC'),a.privilege_type,a.is_grantable FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute col ON col.attrelid=c.oid AND col.attnum>0 CROSS JOIN LATERAL aclexplode(col.attacl) a LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname=%s AND c.relname IN ('ai_egress_budgets','ai_egress_grants') ORDER BY c.relname,col.attname,r.rolname,a.privilege_type,a.is_grantable",
    )
    return tuple(tuple(tuple(value.replace(schema + '.', '__schema__.') if isinstance(value,str) else value for value in row)
                       for row in connection.execute(query,(schema,)).fetchall()) for query in queries)



def _legacy_core_fingerprint(fingerprint):
    """Remove only the explicitly admitted AI extension from the Stage 02 comparison.

    The original core objects, constraints, RLS, triggers and functions must
    remain structurally identical. Unknown additions are NOT silently ignored.
    The opt-in egress extension has its separate migration and tests.
    """
    extension_tables = frozenset(("ai_egress_budgets", "ai_egress_grants"))
    extension_functions = frozenset(("ai_egress_immutable_identity",))
    return tuple(
        tuple(row for row in section
              if row[0] not in (extension_functions if index == 5 else extension_tables))
        for index, section in enumerate(fingerprint)
    )


def verify_legacy_schema(connection, script):
    from psycopg import sql
    probe = 'lw_stage03_probe_' + uuid4().hex
    # This empty schema is created and removed inside the migration transaction.
    # No user-provided names or existing objects are dropped.
    connection.execute(script.replace('lw_core',probe))
    # Fail closed on a partial extension; a complete installed extension
    # must be compared, including grants, RLS, triggers and function bodies.
    presence = (
        connection.execute("SELECT to_regclass('lw_core.ai_egress_budgets')").fetchone()[0] is not None,
        connection.execute("SELECT to_regclass('lw_core.ai_egress_grants')").fetchone()[0] is not None,
        connection.execute("SELECT to_regprocedure('lw_core.ai_egress_immutable_identity()')").fetchone()[0] is not None,
    )
    if any(presence) and not all(presence):
        raise Violation('UNKNOWN')
    actual = schema_fingerprint(connection, 'lw_core')
    if all(presence):
        extension = (ROOT.parent / 'core/migration_ai_egress.sql').read_text(encoding='utf-8')
        connection.execute(extension.replace('lw_core', probe))
        configure_egress_roles(connection, 'lw_core_runtime', 'lw_ai_egress_host', schema=probe)
    else:
        actual = _legacy_core_fingerprint(actual)
    matches = actual == schema_fingerprint(connection, probe)
    connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(probe)))
    if not matches:
        raise Violation('UNKNOWN')


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
                verify_legacy_schema(connection,script)
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

    # A generic application credential must never mint AI egress authority.
    if connection.execute("SELECT to_regclass('lw_core.ai_egress_budgets')").fetchone()[0]:
        for stmt in (
            'REVOKE ALL PRIVILEGES ON lw_core.ai_egress_budgets,lw_core.ai_egress_grants FROM {}',
            'REVOKE UPDATE (used_calls,reserved_calls,revoked_at,revoked_by) ON lw_core.ai_egress_budgets FROM {}',
            'REVOKE UPDATE (consumed_at,consumed_by,revoked_at,revoked_by) ON lw_core.ai_egress_grants FROM {}',
            'GRANT SELECT ON lw_core.ai_egress_budgets,lw_core.ai_egress_grants TO {}',
        ):
            connection.execute(sql.SQL(stmt).format(sql.Identifier(role)))


def configure_egress_roles(connection, runtime_role, host_role, *, schema='lw_core'):
    """Owner-only explicit grants; host secret never belongs to application runtime.

    Trusted host has just SELECT on core cases and bounded egress INSERT/UPDATE.
    The runtime role retains read-only egress inspection and no write access.
    Neither role owns tables, may bypass RLS, or inherits the other.
    """
    from psycopg import sql
    if runtime_role == host_role:
        raise Violation('FORBIDDEN')
    for role in (runtime_role, host_role):
        flags = connection.execute(
            'SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname=%s',
            (role,),
        ).fetchone()
        if flags is None or not flags[0] or any(flags[1:]):
            raise Violation('FORBIDDEN')
    if connection.execute(
        "SELECT pg_has_role(%s,%s,'member') OR pg_has_role(%s,%s,'member')",
        (runtime_role, host_role, host_role, runtime_role),
    ).fetchone()[0]:
        raise Violation('FORBIDDEN')
    name = sql.Identifier(schema)
    normal = sql.Identifier(runtime_role)
    trusted = sql.Identifier(host_role)
    def query(statement, role):
        connection.execute(sql.SQL(statement).format(schema=name, role=role))
    for stmt in (
        'REVOKE ALL PRIVILEGES ON {schema}.ai_egress_budgets,{schema}.ai_egress_grants FROM {role}',
        'REVOKE UPDATE (used_calls,reserved_calls,revoked_at,revoked_by) ON {schema}.ai_egress_budgets FROM {role}',
        'REVOKE UPDATE (consumed_at,consumed_by,revoked_at,revoked_by) ON {schema}.ai_egress_grants FROM {role}',
        'GRANT SELECT ON {schema}.ai_egress_budgets,{schema}.ai_egress_grants TO {role}',
    ):
        query(stmt, normal)
    for stmt in (
        'GRANT USAGE ON SCHEMA {schema} TO {role}',
        'GRANT SELECT ON {schema}.cases TO {role}',
        'GRANT SELECT,INSERT ON {schema}.ai_egress_budgets,{schema}.ai_egress_grants TO {role}',
        'GRANT UPDATE (used_calls,reserved_calls,revoked_at,revoked_by) ON {schema}.ai_egress_budgets TO {role}',
        'GRANT UPDATE (consumed_at,consumed_by,revoked_at,revoked_by) ON {schema}.ai_egress_grants TO {role}',
    ):
        query(stmt, trusted)
