"""Opaque byte storage; requires a trusted, scoped, case-locked core UoW."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid5, NAMESPACE_URL
from lukart_work.domain.models import Value, VersionPin, Hash
from lukart_work.core.postgres import canonical
from lukart_work.validation.rules import Violation

MAX_BYTES = 16 * 1024 * 1024
CATEGORIES = frozenset(('source', 'raw_input', 'raw_output', 'render', 'prompt', 'model',
                        'provider', 'rule', 'validator', 'render_profile', 'generator', 'knowledge',
                        'package'))


class ArtifactRecord(Value):
    tenant_id: UUID
    case_id: UUID
    artifact_id: UUID
    category: str
    name: str
    version: str
    content_hash: Hash
    byte_length: int
    policy: VersionPin
    retain_until: datetime
    created_at: datetime
    actor_id: UUID
    availability: Literal['AVAILABLE', 'DELETED']


class RetentionPolicies:
    """Trusted exact policy pin -> days. Unknown pins retain indefinitely."""
    def __init__(self, policies=()):
        self._durations = {}
        for pin, days in policies:
            if type(days) is not int or days < 0:
                raise ValueError('INVALID_RETENTION')
            self._durations[canonical(pin)] = days

    def deadline(self, pin, now):
        days = self._durations.get(canonical(pin))
        return datetime(9999, 1, 1, tzinfo=timezone.utc) if days is None else now + timedelta(days=days)


class ObjectStore:
    def __init__(self, tx):
        self.connection, self.scope = tx.connection, tx.scope

    def metadata(self, target):
        row = self.connection.execute('SELECT category,name,version,content_hash,byte_length,policy,retain_until,created_at,actor_id FROM lw_storage.artifacts WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s', (*self.scope, target)).fetchone()
        if row is None:
            raise Violation('BROKEN_REFERENCE')
        deleted = self.connection.execute('SELECT 1 FROM lw_storage.tombstones WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s', (*self.scope, target)).fetchone()
        data = dict(zip(('category','name','version','content_hash','byte_length','policy','retain_until','created_at','actor_id'), row))
        data['policy'] = VersionPin.model_validate_json(data['policy'])
        return ArtifactRecord(tenant_id=self.scope[0], case_id=self.scope[1], artifact_id=target,
                              availability='DELETED' if deleted else 'AVAILABLE', **data)

    def put(self, target, category, name, version, data, policy, actor_id, now, policies):
        if category not in CATEGORIES or not isinstance(data, bytes) or len(data) > MAX_BYTES:
            raise Violation('SCHEMA_INVALID')
        if any(not isinstance(s, str) or not s or len(s) > 200 for s in (name, version)):
            raise Violation('SCHEMA_INVALID')
        policy = VersionPin.model_validate_json(canonical(policy))
        content_hash = sha256(data).hexdigest()
        row = self.connection.execute('SELECT artifact_id FROM lw_storage.artifacts WHERE tenant_id=%s AND case_id=%s AND category=%s AND name=%s AND version=%s', (*self.scope, category, name, version)).fetchone()
        if row:
            old = self.metadata(row[0])
            if (old.artifact_id, old.content_hash, old.policy, old.actor_id) != (target, content_hash, policy, actor_id):
                raise Violation('CONFLICT')
            self.read(target)
            return old
        deadline = policies.deadline(policy, now)
        self.connection.execute('INSERT INTO lw_storage.artifacts VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (*self.scope, target, category, name, version, content_hash, len(data), canonical(policy), deadline, now, actor_id))
        self.connection.execute('INSERT INTO lw_storage.blobs VALUES (%s,%s,%s,%s)', (*self.scope, target, data))
        return self.metadata(target)

    def read(self, target):
        item = self.metadata(target)
        if item.availability != 'AVAILABLE':
            raise Violation('PROVENANCE_MISSING')
        row = self.connection.execute('SELECT data FROM lw_storage.blobs WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s', (*self.scope, target)).fetchone()
        data = bytes(row[0]) if row else None
        if data is None or len(data) != item.byte_length or sha256(data).hexdigest() != item.content_hash:
            raise Violation('INVALID_HASH')
        return data

    def hold(self, target, held, actor_id, now):
        item = self.metadata(target)
        if type(held) is not bool or item.availability != 'AVAILABLE':
            raise Violation('GATE_DENIED')
        self.connection.execute('INSERT INTO lw_storage.holds (tenant_id,case_id,artifact_id,held,recorded_at,actor_id) VALUES (%s,%s,%s,%s,%s,%s)', (*self.scope, target, held, now, actor_id))

    def delete(self, target, actor_id, now):
        item = self.metadata(target)
        if item.availability == 'DELETED':
            return item
        hold = self.connection.execute('SELECT held FROM lw_storage.holds WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s ORDER BY entry_order DESC LIMIT 1', (*self.scope, target)).fetchone()
        if item.retain_until > now or (hold and hold[0]):
            raise Violation('GATE_DENIED')
        self.connection.execute('INSERT INTO lw_storage.tombstones VALUES (%s,%s,%s,%s,%s,%s)', (*self.scope, target, now, actor_id, item.content_hash))
        self.connection.execute('DELETE FROM lw_storage.blobs WHERE tenant_id=%s AND case_id=%s AND artifact_id=%s', (*self.scope, target))
        return self.metadata(target)


def artifact_id(scope, category, name, version):
    return uuid5(NAMESPACE_URL, canonical([str(v) for v in scope] + [category, name, version]))
