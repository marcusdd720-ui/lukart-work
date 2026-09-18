"""Scoped PostgreSQL unit of work. Runtime credentials must not own the tables.

Deployment/migration is explicit; constructing a repository never runs DDL.
The transaction lock serializes one case, including first creation. RLS is an
additional boundary beneath mandatory application authorization.
"""
from contextlib import contextmanager
from hashlib import sha256
import json

from lukart_work.domain.models import ENTITIES
from lukart_work.contracts.messages import (
    SourceDocument, Snapshot, DomainEvent, LegacyDomainEventV1, CommandResult,
)
from lukart_work.contracts.versions import contract_version
from lukart_work.validation.rules import digest, ref, Violation


def canonical(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def key(target):
    return f'{target.kind}:{target.id}:{target.revision}'


def urn(cls):
    return f'urn:lukart:work:{cls.__name__}:{contract_version(cls.__name__)}'


def decode(row, cls):
    contract, raw, content_hash = row
    # Verify the saved representation BEFORE parsing a historical payload.
    expected = urn(cls)
    legacy_domain_event = (
        cls is DomainEvent
        and expected == 'urn:lukart:work:DomainEvent:2.0.0'
        and contract == 'urn:lukart:work:DomainEvent:1.0.0'
    )
    if contract != expected and not legacy_domain_event:
        raise Violation('UNKNOWN')
    if sha256(raw.encode('utf-8')).hexdigest() != content_hash:
        raise Violation('INVALID_HASH')
    if legacy_domain_event:
        LegacyDomainEventV1.model_validate_json(raw)
    return cls.model_validate_json(raw)


class PostgresRepository:
    def __init__(self, dsn, *, storage=False, retention_policies=None):
        self._dsn = dsn
        self.storage = storage
        self.retention_policies = retention_policies

    # Internal CaseRepository port; public reads go through CommandService.query.
    def get_revision(self, tenant_id, case_id, target):
        with self.transaction(tenant_id, case_id) as tx:
            entity = tx.records().get(target)
            if entity is None:
                raise Violation('BROKEN_REFERENCE')
            return entity

    def get_heads(self, tenant_id, case_id):
        with self.transaction(tenant_id, case_id) as tx:
            return tx.sequence(), tuple(ref(e) for e in tx.heads())

    def get_snapshot(self, tenant_id, case_id, snapshot_id):
        with self.transaction(tenant_id, case_id) as tx:
            return tx.object('snapshot', snapshot_id, Snapshot)

    @contextmanager
    def external_call_lock(self, tenant_id, case_id, idempotency_key):
        """Serialize one external-call idempotency key across processes without locking the case."""
        import psycopg
        with psycopg.connect(self._dsn) as connection:
            role = connection.execute(
                'SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user'
            ).fetchone()
            if role is None or any(role):
                raise Violation('FORBIDDEN')
            lock = int.from_bytes(
                sha256(
                    f'external-call/{tenant_id}/{case_id}/{idempotency_key}'.encode()
                ).digest()[:8],
                'big',
                signed=True,
            )
            connection.execute('SELECT pg_advisory_lock(%s)', (lock,))
            try:
                yield
            finally:
                connection.execute('SELECT pg_advisory_unlock(%s)', (lock,))

    @contextmanager
    def transaction(self, tenant_id, case_id):
        import psycopg
        with psycopg.connect(self._dsn) as connection:
            with connection.transaction():
                connection.execute("SET LOCAL TIME ZONE 'UTC'")
                # A superuser or BYPASSRLS runtime would invalidate the isolation proof.
                role = connection.execute('SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
                if role is None or any(role):
                    raise Violation('FORBIDDEN')
                if connection.execute("SELECT 1 FROM pg_tables WHERE schemaname IN ('lw_core','lw_storage') AND tableowner=current_user LIMIT 1").fetchone():
                    raise Violation('FORBIDDEN')
                connection.execute("SELECT set_config('lw.tenant', %s, true), set_config('lw.case', %s, true)", (str(tenant_id), str(case_id)))
                lock = int.from_bytes(sha256(f'{tenant_id}/{case_id}'.encode()).digest()[:8], 'big', signed=True)
                connection.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
                tx = UnitOfWork(connection, tenant_id, case_id)
                tx.storage = self.storage
                tx.retention_policies = self.retention_policies
                yield tx


class UnitOfWork:
    def __init__(self, connection, tenant_id, case_id):
        self.connection = connection
        self.scope = (tenant_id, case_id)

    def sequence(self):
        row = self.connection.execute('SELECT sequence FROM lw_core.cases WHERE tenant_id=%s AND case_id=%s', self.scope).fetchone()
        return row[0] if row else 0

    def set_sequence(self, sequence):
        self.connection.execute('INSERT INTO lw_core.cases VALUES (%s,%s,%s) ON CONFLICT (tenant_id,case_id) DO UPDATE SET sequence=EXCLUDED.sequence', (*self.scope, sequence))

    def records(self):
        types = {c.__name__: c for c in ENTITIES}
        rows = self.connection.execute('SELECT revision_key,kind,entity_id,revision,contract,payload,content_hash FROM lw_core.revisions WHERE tenant_id=%s AND case_id=%s ORDER BY revision', self.scope).fetchall()
        records = {}
        for revision_key, kind, entity_id, revision, *row in rows:
            if kind not in types:
                raise Violation('UNKNOWN')
            entity = decode(row, types[kind])
            if (entity.tenant_id, entity.case_id) != self.scope:
                raise Violation('CROSS_CASE')
            if (key(ref(entity)), entity.id, entity.revision) != (revision_key, entity_id, revision):
                raise Violation('INVALID_HASH')
            records[ref(entity)] = entity
        return records

    def heads(self):
        rows = self.connection.execute('SELECT revision_key FROM lw_core.heads WHERE tenant_id=%s AND case_id=%s ORDER BY kind, entity_id', self.scope).fetchall()
        records = {key(r): e for r, e in self.records().items()}
        return tuple(records[row[0]] for row in rows)

    def append(self, entity):
        raw = canonical(entity)
        self.connection.execute('INSERT INTO lw_core.revisions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)', (*self.scope, key(ref(entity)), entity.kind, entity.id, entity.revision, urn(type(entity)), raw, digest(entity)))
        self.connection.execute('INSERT INTO lw_core.heads VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,case_id,kind,entity_id) DO UPDATE SET revision_key=EXCLUDED.revision_key', (*self.scope, entity.kind, entity.id, key(ref(entity))))

    def objects(self, category, cls):
        rows = self.connection.execute('SELECT contract,payload,content_hash FROM lw_core.objects WHERE tenant_id=%s AND case_id=%s AND category=%s', (*self.scope, category)).fetchall()
        return tuple(decode(row, cls) for row in rows)

    def object(self, category, object_id, cls):
        row = self.connection.execute('SELECT contract,payload,content_hash FROM lw_core.objects WHERE tenant_id=%s AND case_id=%s AND category=%s AND object_id=%s', (*self.scope, category, object_id)).fetchone()
        if row is None:
            raise Violation('BROKEN_REFERENCE')
        value = decode(row, cls)
        if hasattr(value, 'tenant_id') and (value.tenant_id, value.case_id) != self.scope:
            raise Violation('CROSS_CASE')
        if category in ('source', 'snapshot') and value.id != object_id:
            raise Violation('INVALID_HASH')
        return value

    def put_object(self, category, object_id, value, source_bytes=None):
        if category == 'source' and getattr(self, 'storage', False):
            from lukart_work.storage.objects import ObjectStore, RetentionPolicies
            ObjectStore(self).put(object_id, 'source', str(object_id), '1', source_bytes,
                value.retention_policy, value.actor.id, value.received_at,
                self.retention_policies or RetentionPolicies())
            source_bytes = None
        self.connection.execute('INSERT INTO lw_core.objects VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', (*self.scope, category, object_id, urn(type(value)), canonical(value), digest(value), source_bytes))

    def source_bytes(self, object_id):
        source = self.object('source', object_id, SourceDocument)
        row = self.connection.execute("SELECT original_bytes FROM lw_core.objects WHERE tenant_id=%s AND case_id=%s AND category='source' AND object_id=%s", (*self.scope, object_id)).fetchone()
        data = bytes(row[0]) if row and row[0] is not None else None
        if data is None and getattr(self, 'storage', False):
            from lukart_work.storage.objects import ObjectStore
            data = ObjectStore(self).read(object_id)
        if data is None or len(data) != source.byte_length or sha256(data).hexdigest() != source.content_hash:
            raise Violation('PROVENANCE_MISSING')
        return data

    def replay_types(self, idempotency_key, input_hash, types):
        row = self.connection.execute('SELECT input_hash,contract,payload,content_hash FROM lw_core.commands WHERE tenant_id=%s AND case_id=%s AND idempotency_key=%s', (*self.scope, idempotency_key)).fetchone()
        if row is None:
            return None
        if row[0] != input_hash:
            raise Violation('IDEMPOTENCY_CONFLICT')
        for cls in types:
            if row[1] == urn(cls):
                return decode(row[1:], cls)
        raise Violation('UNKNOWN')

    def replay(self, idempotency_key, input_hash):
        return self.replay_types(idempotency_key, input_hash, (CommandResult,))

    def finish_result(self, request, input_hash, result, events):
        self.connection.execute('INSERT INTO lw_core.commands VALUES (%s,%s,%s,%s,%s,%s,%s)', (*self.scope, request.meta.idempotency_key, input_hash, urn(type(result)), canonical(result), digest(result)))
        for event in events:
            raw = canonical(event)
            self.connection.execute('INSERT INTO lw_core.events (tenant_id,case_id,event_id,sequence,contract,payload,content_hash) VALUES (%s,%s,%s,%s,%s,%s,%s)', (*self.scope, event.audit.event_id, event.audit.sequence, urn(DomainEvent), raw, digest(event)))
            self.connection.execute('INSERT INTO lw_core.outbox VALUES (%s,%s,%s)', (*self.scope, event.audit.event_id))

    def finish(self, request, input_hash, result, events):
        if not isinstance(result, CommandResult):
            raise Violation('SCHEMA_INVALID')
        self.finish_result(request, input_hash, result, events)

    def last_event_hash(self):
        self.events()  # Validate the chain before extending it.
        row = self.connection.execute('SELECT content_hash FROM lw_core.events WHERE tenant_id=%s AND case_id=%s ORDER BY sequence DESC,event_order DESC LIMIT 1', self.scope).fetchone()
        return row[0] if row else None  # Preserve the original stored representation.

    def events(self):
        rows = self.connection.execute('SELECT event_id,sequence,contract,payload,content_hash FROM lw_core.events WHERE tenant_id=%s AND case_id=%s ORDER BY sequence,event_order', self.scope).fetchall()
        result = []
        previous = None
        for event_id, sequence, *row in rows:
            event = decode(row, DomainEvent)
            if (event.audit.tenant_id, event.audit.case_id) != self.scope or (event.audit.event_id, event.audit.sequence) != (event_id, sequence):
                raise Violation('INVALID_HASH')
            if event.audit.previous_event_hash != previous:
                raise Violation('INVALID_HASH')
            result.append(event)
            previous = row[2]
        return tuple(result)

    def outbox(self):
        # The shared path checks contract, bytes and the complete predecessor chain.
        events = self.events()
        rows = self.connection.execute('SELECT event_id FROM lw_core.outbox WHERE tenant_id=%s AND case_id=%s', self.scope).fetchall()
        ids = {row[0] for row in rows}
        return tuple(event for event in events if event.audit.event_id in ids)
