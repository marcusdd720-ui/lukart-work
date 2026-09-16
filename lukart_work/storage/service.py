"""Authenticated local storage facade. Provisioning is a trusted host API."""
from datetime import datetime, timezone
from uuid import UUID
from lukart_work.core.service import safe_error
from lukart_work.storage.objects import ObjectStore, artifact_id, RetentionPolicies
from lukart_work.validation.rules import Violation
from pydantic import ValidationError


class StorageService:
    def __init__(self, repository, authority):
        self.repository, self.authority = repository, authority

    def _run(self, token, action, callback):
        try:
            with self.authority.session(token) as p:
                p.require(p.tenant_id, p.case_id, action)
                if p.actor.kind == 'AI' or (action in ('StorageDelete', 'StorageHold') and p.actor.kind != 'HUMAN'):
                    raise Violation('FORBIDDEN')
                with self.repository.transaction(p.tenant_id, p.case_id) as tx:
                    if not tx.sequence():
                        raise Violation('BROKEN_REFERENCE')
                    result = callback(ObjectStore(tx), p, datetime.now(timezone.utc))
                    p.require(p.tenant_id, p.case_id, action)
                return result
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValueError, TypeError, ValidationError, OverflowError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'):
                return safe_error('CONFLICT' if getattr(error, 'sqlstate', '') == '23505' else 'UNKNOWN', UUID(int=0))
            raise

    def put(self, token, category, name, version, data, policy):
        return self._run(token, 'StorageWrite', lambda s, p, now: s.put(
            artifact_id(s.scope, category, name, version), category, name, version,
            data, policy, p.actor.id, now, self.repository.retention_policies or RetentionPolicies()))

    def read(self, token, target):
        return self._run(token, 'StorageRead', lambda s, p, now: s.read(target))

    def resolve(self, token, category, pin):
        """Resolve an exact independent version pin, never an implicit latest."""
        def resolve_pin(s, p, now):
            from lukart_work.domain.models import VersionPin
            from lukart_work.core.postgres import canonical
            checked = VersionPin.model_validate_json(canonical(pin))
            target = artifact_id(s.scope, category, checked.id, checked.version)
            item = s.metadata(target)
            if item.content_hash != checked.content_hash:
                raise Violation('INVALID_HASH')
            return s.read(target)
        return self._run(token, 'StorageRead', resolve_pin)

    def metadata(self, token, target):
        return self._run(token, 'StorageRead', lambda s, p, now: s.metadata(target))

    def hold(self, token, target, held):
        return self._run(token, 'StorageHold', lambda s, p, now: s.hold(target, held, p.actor.id, now))

    def delete(self, token, target):
        return self._run(token, 'StorageDelete', lambda s, p, now: s.delete(target, p.actor.id, now))
