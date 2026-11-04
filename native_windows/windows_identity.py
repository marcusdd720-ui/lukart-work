"""Native Windows Negotiate authentication and case-scoped HUMAN capabilities.

The browser authenticates with Windows SSPI. The resulting account SID is mapped
through an administrator-owned local policy to one explicit tenant/CASE scope.
No password is collected, persisted, logged, or forwarded to WORK.
"""
from __future__ import annotations

import base64
import binascii
import ctypes
import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import monotonic
from uuid import UUID
from typing import Any, Callable

from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.domain.models import Actor
from lukart_work.validation.rules import Violation, strict_json
from native_windows.dacl import verify_protected_file

_POLICY_SCHEMA = "urn:lukart:work:WindowsHumanIdentityPolicy:1.0.0"
_SID_PATTERN = re.compile(r"^S-1-(?:[0-9]+-)+[0-9]+$")
_ACTION_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")
_MAX_POLICY_BYTES = 64 * 1024
_MAX_NEGOTIATE_TOKEN_BYTES = 64 * 1024
_MAX_HANDSHAKES = 32
_MAX_HANDSHAKE_STEPS = 5
_HANDSHAKE_TTL_SECONDS = 60


class WindowsIdentityError(ValueError):
    """Fail-closed Windows identity or policy error."""


@dataclass(frozen=True, slots=True)
class _PrincipalBinding:
    sid: str
    actor_id: str
    tenant_id: str
    case_id: str
    actions: frozenset[str]
    enabled: bool


@dataclass(frozen=True, slots=True)
class WindowsHumanIdentityPolicy:
    policy_id: str
    session_ttl_seconds: int
    principals: dict[str, _PrincipalBinding]
    digest: str

    @classmethod
    def from_path(cls, path: str | Path) -> "WindowsHumanIdentityPolicy":
        source = Path(path)
        if not source.is_absolute() or source.is_symlink() or not source.is_file():
            raise WindowsIdentityError("TRUSTED_WINDOWS_IDENTITY_POLICY_REQUIRED")
        resolved = source.resolve(strict=True)
        if os.name == "nt":
            verify_protected_file(resolved)
        if str(resolved).startswith("\\\\"):
            raise WindowsIdentityError("LOCAL_WINDOWS_IDENTITY_POLICY_REQUIRED")
        raw = resolved.read_bytes()
        if not raw or len(raw) > _MAX_POLICY_BYTES:
            raise WindowsIdentityError("WINDOWS_IDENTITY_POLICY_SIZE_INVALID")
        try:
            document = strict_json(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError, Violation, RecursionError) as exc:
            raise WindowsIdentityError("WINDOWS_IDENTITY_POLICY_INVALID") from exc
        if not isinstance(document, dict) or set(document) != {
            "schema", "policy_id", "session_ttl_seconds", "principals"
        }:
            raise WindowsIdentityError("WINDOWS_IDENTITY_POLICY_SCHEMA_INVALID")
        if document["schema"] != _POLICY_SCHEMA:
            raise WindowsIdentityError("WINDOWS_IDENTITY_POLICY_SCHEMA_UNSUPPORTED")
        policy_id = document["policy_id"]
        if not isinstance(policy_id, str) or not policy_id.strip() or len(policy_id) > 128:
            raise WindowsIdentityError("WINDOWS_IDENTITY_POLICY_ID_INVALID")
        ttl = document["session_ttl_seconds"]
        if type(ttl) is not int or not 60 <= ttl <= 3600:
            raise WindowsIdentityError("WINDOWS_IDENTITY_SESSION_TTL_INVALID")
        entries = document["principals"]
        if not isinstance(entries, list) or len(entries) > 256:
            raise WindowsIdentityError("WINDOWS_IDENTITY_PRINCIPALS_INVALID")
        bindings: dict[str, _PrincipalBinding] = {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "sid", "actor_id", "tenant_id", "case_id", "actions", "enabled"
            }:
                raise WindowsIdentityError("WINDOWS_IDENTITY_PRINCIPAL_SCHEMA_INVALID")
            sid = entry["sid"]
            if not isinstance(sid, str) or not _SID_PATTERN.fullmatch(sid):
                raise WindowsIdentityError("WINDOWS_IDENTITY_SID_INVALID")
            if sid in bindings:
                raise WindowsIdentityError("WINDOWS_IDENTITY_SID_DUPLICATE")
            identifiers: list[str] = []
            for field in ("actor_id", "tenant_id", "case_id"):
                value = entry[field]
                if not isinstance(value, str):
                    raise WindowsIdentityError("WINDOWS_IDENTITY_SCOPE_INVALID")
                try:
                    parsed = UUID(value)
                except (ValueError, AttributeError) as exc:
                    raise WindowsIdentityError("WINDOWS_IDENTITY_SCOPE_INVALID") from exc
                if str(parsed) != value.lower():
                    raise WindowsIdentityError("WINDOWS_IDENTITY_SCOPE_NONCANONICAL")
                identifiers.append(str(parsed))
            actions = entry["actions"]
            if (
                not isinstance(actions, list)
                or len(actions) > 128
                or any(not isinstance(action, str) or not _ACTION_PATTERN.fullmatch(action) for action in actions)
                or len(set(actions)) != len(actions)
                or "*" in actions
            ):
                raise WindowsIdentityError("WINDOWS_IDENTITY_ACTIONS_INVALID")
            enabled = entry["enabled"]
            if type(enabled) is not bool:
                raise WindowsIdentityError("WINDOWS_IDENTITY_ENABLED_INVALID")
            bindings[sid] = _PrincipalBinding(
                sid=sid,
                actor_id=identifiers[0],
                tenant_id=identifiers[1],
                case_id=identifiers[2],
                actions=frozenset(actions),
                enabled=enabled,
            )
        return cls(
            policy_id=policy_id,
            session_ttl_seconds=ttl,
            principals=bindings,
            digest=hashlib.sha256(raw).hexdigest(),
        )

    def resolve_sid(self, sid: str) -> Principal:
        binding = self.principals.get(sid)
        if binding is None or not binding.enabled or not binding.actions:
            raise WindowsIdentityError("WINDOWS_HUMAN_NOT_ADMITTED")
        return Principal(
            actor=Actor(id=UUID(binding.actor_id), kind="HUMAN"),
            tenant_id=UUID(binding.tenant_id),
            case_id=UUID(binding.case_id),
            actions=binding.actions,
        )


@dataclass(frozen=True, slots=True)
class WindowsAuthOutcome:
    state: str
    handshake_id: str | None = None
    challenge: str | None = None
    session_token: str | None = None


@dataclass(slots=True)
class _Handshake:
    context: Any
    created_at: float
    steps: int = 0


def account_name_to_sid(account_name: str) -> str:
    """Resolve the authenticated SSPI account name to its canonical Windows SID."""
    if os.name != "nt":
        raise WindowsIdentityError("WINDOWS_SSPI_REQUIRED")
    if not isinstance(account_name, str) or not account_name or len(account_name) > 512:
        raise WindowsIdentityError("WINDOWS_ACCOUNT_NAME_INVALID")
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("Advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
    lookup = advapi32.LookupAccountNameW
    lookup.argtypes = (
        wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPVOID,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
    )
    lookup.restype = wintypes.BOOL
    sid_size = wintypes.DWORD(0)
    domain_size = wintypes.DWORD(0)
    sid_use = wintypes.DWORD(0)
    lookup(None, account_name, None, ctypes.byref(sid_size), None,
           ctypes.byref(domain_size), ctypes.byref(sid_use))
    if ctypes.get_last_error() != 122 or sid_size.value == 0:
        raise WindowsIdentityError("WINDOWS_ACCOUNT_LOOKUP_FAILED")
    sid_buffer = ctypes.create_string_buffer(sid_size.value)
    domain_buffer = ctypes.create_unicode_buffer(max(domain_size.value, 1))
    if not lookup(None, account_name, sid_buffer, ctypes.byref(sid_size),
                  domain_buffer, ctypes.byref(domain_size), ctypes.byref(sid_use)):
        raise WindowsIdentityError("WINDOWS_ACCOUNT_LOOKUP_FAILED")
    convert = advapi32.ConvertSidToStringSidW
    convert.argtypes = (wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR))
    convert.restype = wintypes.BOOL
    sid_text = wintypes.LPWSTR()
    if not convert(sid_buffer, ctypes.byref(sid_text)):
        raise WindowsIdentityError("WINDOWS_SID_CONVERSION_FAILED")
    try:
        result = sid_text.value
    finally:
        kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
        kernel32.LocalFree.restype = wintypes.HLOCAL
        kernel32.LocalFree(sid_text)
    if not isinstance(result, str) or not _SID_PATTERN.fullmatch(result):
        raise WindowsIdentityError("WINDOWS_SID_INVALID")
    return result


def _new_sspi_context() -> Any:
    if os.name != "nt":
        raise WindowsIdentityError("WINDOWS_SSPI_REQUIRED")
    try:
        import spnego
    except ImportError as exc:
        raise WindowsIdentityError("WINDOWS_AUTH_EXTRA_REQUIRED") from exc
    return spnego.server(
        protocol="negotiate",
        hostname="localhost",
        service="HTTP",
        options=spnego.NegotiateOptions.use_sspi,
    )


class WindowsHumanAuthManager:
    """Bounded SSPI handshake and short-lived, case-scoped WORK capability issuer."""

    def __init__(
        self,
        authority: TokenAuthority,
        policy: WindowsHumanIdentityPolicy,
        *,
        context_factory: Callable[[], Any] = _new_sspi_context,
        sid_resolver: Callable[[str], str] = account_name_to_sid,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(authority, TokenAuthority):
            raise WindowsIdentityError("TOKEN_AUTHORITY_REQUIRED")
        if not isinstance(policy, WindowsHumanIdentityPolicy):
            raise WindowsIdentityError("WINDOWS_IDENTITY_POLICY_REQUIRED")
        self._authority = authority
        self._policy = policy
        self._context_factory = context_factory
        self._sid_resolver = sid_resolver
        self._clock = clock
        self._lock = RLock()
        self._handshakes: dict[str, _Handshake] = {}
        self._sessions: dict[bytes, tuple[str, float]] = {}

    @property
    def policy_digest(self) -> str:
        return self._policy.digest

    @property
    def session_ttl_seconds(self) -> int:
        return self._policy.session_ttl_seconds

    @property
    def has_enabled_bindings(self) -> bool:
        return any(binding.enabled and binding.actions for binding in self._policy.principals.values())

    def _prune(self, now: float) -> None:
        for handshake_id, handshake in tuple(self._handshakes.items()):
            if now - handshake.created_at > _HANDSHAKE_TTL_SECONDS:
                self._handshakes.pop(handshake_id, None)
        for digest, (token, expires_at) in tuple(self._sessions.items()):
            if now >= expires_at:
                self._sessions.pop(digest, None)
                self._authority.revoke(token)

    def _new_handshake(self, now: float) -> str | None:
        if len(self._handshakes) >= _MAX_HANDSHAKES:
            return None
        try:
            context = self._context_factory()
        except Exception:
            return None
        handshake_id = secrets.token_urlsafe(32)
        self._handshakes[handshake_id] = _Handshake(context, now)
        return handshake_id

    def authenticate(
        self,
        *,
        session_token: str | None,
        handshake_id: str | None,
        authorization: str | None,
    ) -> WindowsAuthOutcome:
        now = self._clock()
        with self._lock:
            self._prune(now)
            if session_token:
                digest = hashlib.sha256(session_token.encode("utf-8")).digest()
                active = self._sessions.get(digest)
                if active is not None and active[0] == session_token and now < active[1]:
                    self._sessions[digest] = (session_token, now + self._policy.session_ttl_seconds)
                    return WindowsAuthOutcome("AUTHENTICATED", session_token=session_token)
                if active is not None:
                    self._sessions.pop(digest, None)
                    self._authority.revoke(active[0])
            if authorization is None:
                identifier = handshake_id if handshake_id in self._handshakes else self._new_handshake(now)
                if identifier is None:
                    return WindowsAuthOutcome("DENIED")
                return WindowsAuthOutcome("CHALLENGE", handshake_id=identifier, challenge="Negotiate")
            if (
                not isinstance(authorization, str)
                or not authorization.startswith("Negotiate ")
                or len(authorization) > 2 * _MAX_NEGOTIATE_TOKEN_BYTES
            ):
                return WindowsAuthOutcome("DENIED")
            identifier = handshake_id if handshake_id in self._handshakes else self._new_handshake(now)
            if identifier is None:
                return WindowsAuthOutcome("DENIED")
            try:
                encoded = authorization[10:]
                incoming = base64.b64decode(encoded, validate=True)
                if not incoming or len(incoming) > _MAX_NEGOTIATE_TOKEN_BYTES:
                    raise WindowsIdentityError("WINDOWS_NEGOTIATE_TOKEN_INVALID")
                handshake = self._handshakes[identifier]
                handshake.steps += 1
                if handshake.steps > _MAX_HANDSHAKE_STEPS:
                    self._handshakes.pop(identifier, None)
                    return WindowsAuthOutcome("DENIED")
                outgoing = handshake.context.step(incoming)
                if not handshake.context.complete:
                    if not outgoing:
                        self._handshakes.pop(identifier, None)
                        return WindowsAuthOutcome("DENIED")
                    return WindowsAuthOutcome(
                        "CONTINUE",
                        handshake_id=identifier,
                        challenge="Negotiate " + base64.b64encode(outgoing).decode("ascii"),
                    )
                account_name = handshake.context.client_principal
                if not isinstance(account_name, str) or not account_name:
                    self._handshakes.pop(identifier, None)
                    return WindowsAuthOutcome("DENIED")
                sid = self._sid_resolver(account_name)
                principal = self._policy.resolve_sid(sid)
                token = self._authority.provision(principal)
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                self._sessions[digest] = (token, now + self._policy.session_ttl_seconds)
                self._handshakes.pop(identifier, None)
                return WindowsAuthOutcome("AUTHENTICATED", session_token=token)
            except (ValueError, TypeError, binascii.Error, OSError, WindowsIdentityError):
                self._handshakes.pop(identifier, None)
                return WindowsAuthOutcome("DENIED")

    def close(self) -> None:
        with self._lock:
            for token, _expires_at in self._sessions.values():
                self._authority.revoke(token)
            self._sessions.clear()
            self._handshakes.clear()


def create_authenticator(operator: Any) -> WindowsHumanAuthManager:
    """Factory used by the trusted private Windows identity adapter module."""
    if not hasattr(operator, "core") or not isinstance(operator.core.authority, TokenAuthority):
        raise WindowsIdentityError("TRUSTED_CASE_OPERATOR_REQUIRED")
    policy_path = os.environ.get("LUKART_HUMAN_IDENTITY_POLICY", "")
    if not policy_path:
        raise WindowsIdentityError("LUKART_HUMAN_IDENTITY_POLICY_REQUIRED")
    policy = WindowsHumanIdentityPolicy.from_path(policy_path)
    manager = WindowsHumanAuthManager(operator.core.authority, policy)
    if not manager.has_enabled_bindings:
        raise WindowsIdentityError("ENABLED_WINDOWS_HUMAN_POLICY_REQUIRED")
    return manager
