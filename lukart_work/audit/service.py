"""Read-only Stage 12 audit/provenance service over the canonical Core ledger."""
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from lukart_work.core.service import safe_error
from lukart_work.domain import models as m
from lukart_work.validation.rules import Violation, digest, ref, walk

from .contracts import AuditPackage, AuditTrace


AUDIT_POLICY_FILES = (
    'audit/contracts.py',
    'audit/service.py',
    'contracts/messages.py',
    'core/postgres.py',
)


def audit_policy_artifact(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    return {
        'profile': 'SHA-256 of source bytes with CRLF normalized to LF',
        'files': {
            name: sha256((root / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for name in AUDIT_POLICY_FILES
        },
    }


def audit_pin(root=None):
    return m.VersionPin(
        id='urn:lukart:work:AuditProvenanceService',
        version='1.0.0',
        content_hash=digest(audit_policy_artifact(root)),
    )


def verify_audit_package(package, *, expected_implementation=None):
    checked = AuditPackage.model_validate_json(
        package.model_dump_json() if isinstance(package, AuditPackage) else AuditPackage.model_validate(package).model_dump_json()
    )
    actual = tuple(digest(event) for event in checked.events)
    if actual != checked.event_hashes:
        raise Violation('INVALID_HASH')
    if expected_implementation is not None and checked.implementation != expected_implementation:
        raise Violation('INVALID_HASH')
    return digest(checked)


class AuditService:
    """Authorized immutable projection; never writes audit history or domain state."""

    def __init__(self, repository, authority):
        self.repository = repository
        self.authority = authority

    def _run(self, token, callback):
        try:
            with self.authority.session(token) as principal:
                principal.require(principal.tenant_id, principal.case_id, 'AuditRead')
                if principal.actor.kind == 'AI':
                    raise Violation('FORBIDDEN')
                with self.repository.transaction(principal.tenant_id, principal.case_id) as tx:
                    if not tx.sequence():
                        raise Violation('BROKEN_REFERENCE')
                    result = callback(tx, principal)
                    principal.require(principal.tenant_id, principal.case_id, 'AuditRead')
                return result
        except Violation as error:
            return safe_error(error.code, UUID(int=0))
        except (ValidationError, ValueError, TypeError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))
        except Exception as error:
            if type(error).__module__.startswith('psycopg'):
                return safe_error(
                    'CONFLICT' if getattr(error, 'sqlstate', '') in ('23505', '40001', '40P01') else 'UNKNOWN',
                    UUID(int=0),
                )
            raise

    @staticmethod
    def _package(tx, principal):
        events = tx.events()
        outbox = tx.outbox()
        if not events:
            raise Violation('PROVENANCE_MISSING')
        event_ids = tuple(event.audit.event_id for event in events)
        if tuple(event.audit.event_id for event in outbox) != event_ids:
            raise Violation('PROVENANCE_MISSING')
        hashes = tuple(digest(event) for event in events)
        package = AuditPackage(
            contract='urn:lukart:work:AuditPackage:1.0.0',
            tenant_id=principal.tenant_id,
            case_id=principal.case_id,
            case_sequence=tx.sequence(),
            heads=tuple(ref(entity) for entity in tx.heads()),
            events=events,
            event_hashes=hashes,
            outbox_event_ids=event_ids,
            chain_head_hash=hashes[-1],
            implementation=audit_pin(),
        )
        verify_audit_package(package, expected_implementation=package.implementation)
        return package

    def package(self, token):
        return self._run(token, self._package)

    def trace(self, token, target):
        try:
            checked_target = m.Ref.model_validate(target)
        except (ValidationError, ValueError, TypeError):
            return safe_error('SCHEMA_INVALID', UUID(int=0))

        def build(tx, principal):
            records = tx.records()
            if checked_target not in records:
                raise Violation('BROKEN_REFERENCE')
            visited = set()
            anchors = set()
            pending = [checked_target]
            while pending:
                current = pending.pop()
                if current in visited:
                    continue
                item = records.get(current)
                if item is None:
                    raise Violation('BROKEN_REFERENCE')
                visited.add(current)
                anchors.update(walk(item, m.SourceAnchor))
                pending.extend(walk(item, m.Ref))
            for anchor in anchors:
                tx.source_bytes(anchor.document_id)

            package = self._package(tx, principal)
            event_ids = tuple(
                event.audit.event_id
                for event in package.events
                if any(subject in visited for subject in event.subjects)
            )
            represented = {
                subject
                for event in package.events
                for subject in event.subjects
                if subject in visited
            }
            completeness = 'COMPLETE' if anchors and represented == visited else 'INCOMPLETE'
            return AuditTrace(
                contract='urn:lukart:work:AuditTrace:1.0.0',
                tenant_id=principal.tenant_id,
                case_id=principal.case_id,
                target=checked_target,
                package_hash=digest(package),
                revisions=tuple(sorted(visited, key=lambda r: (r.kind, str(r.id), r.revision))),
                sources=tuple(sorted(anchors, key=lambda a: a.model_dump_json())),
                event_ids=event_ids,
                completeness=completeness,
            )

        return self._run(token, build)
