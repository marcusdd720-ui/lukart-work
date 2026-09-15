"""Local trusted authentication adapter. Tokens never come from domain payloads.

Provisioning is an administrative Python API, not an exposed domain command.
An external identity provider can implement the same session interface later.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from threading import RLock
from uuid import UUID

from lukart_work.domain.models import Actor
from lukart_work.validation.rules import Violation


@dataclass(frozen=True)
class Principal:
    actor: Actor
    tenant_id: UUID
    case_id: UUID
    actions: frozenset[str]

    def require(self, tenant_id, case_id, action):
        if (tenant_id, case_id) != (self.tenant_id, self.case_id) or action not in self.actions:
            raise Violation('FORBIDDEN')


class TokenAuthority:
    """Process-local capabilities, with revocation serialized against active requests.

    Only SHA-256 token digests are retained. Restart fails closed: a trusted host
    must provision fresh tokens. Database results and idempotency survive restart.
    This adapter defines no business role catalogue or external login UI.
    """
    def __init__(self):
        self._lock = RLock()
        self._tokens = {}

    def provision(self, principal):
        token = token_urlsafe(32)
        with self._lock:
            self._tokens[sha256(token.encode()).digest()] = principal
        return token

    def revoke(self, token):
        with self._lock:
            self._tokens.pop(sha256(token.encode()).digest(), None)

    @contextmanager
    def session(self, token):
        # Keep revocation from racing with commit in this local adapter.
        with self._lock:
            principal = self._tokens.get(sha256(token.encode()).digest()) if isinstance(token, str) else None
            if principal is None:
                raise Violation('FORBIDDEN')
            yield principal
