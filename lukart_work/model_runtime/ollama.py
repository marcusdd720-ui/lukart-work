"""Stage 13 local model runtime adapters.

The adapter is deliberately outside Case state. It may return an untrusted AIResult
payload and a cryptographic/version receipt, but it cannot write the ledger, approve
facts, resolve contradictions, or cross a HUMAN authorization boundary.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import http.client
import ipaddress
import json
import socket
import threading
from typing import Callable, Mapping
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import ValidationError

from lukart_work.contracts.messages import AIResult
from lukart_work.domain.models import VersionPin
from lukart_work.drafting.contracts import (
    DraftingInvocation, ModelExecutionReceipt,
)
from lukart_work.validation.rules import digest


class ProviderError(RuntimeError):
    code = "PROVIDER_ERROR"


class ProviderPolicyError(ProviderError):
    code = "PROVIDER_POLICY"


class ProviderUnavailable(ProviderError):
    code = "PROVIDER_UNAVAILABLE"


class ProviderTimeout(ProviderError):
    code = "PROVIDER_TIMEOUT"


class ProviderModelMissing(ProviderError):
    code = "MODEL_MISSING"


class ProviderProtocolError(ProviderError):
    code = "PROVIDER_PROTOCOL"


class ProviderResponseTooLarge(ProviderError):
    code = "PROVIDER_RESPONSE_TOO_LARGE"


class ProviderBusy(ProviderError):
    code = "PROVIDER_BUSY"


class ProviderCancelled(ProviderError):
    code = "PROVIDER_CANCELLED"


def _no_constant(value):
    raise ValueError(f"non-json constant: {value}")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def strict_json_bytes(raw: bytes):
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_no_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProviderProtocolError() from exc


def ollama_parameters_hash(*, options=None, keep_alive="5m") -> str:
    """Bind every generation parameter controlled by this adapter."""
    return digest({
        "stream": False,
        "format": AIResult.model_json_schema(),
        "options": dict(options or {}),
        "keep_alive": keep_alive,
    })


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    endpoint: str
    model_name: str
    provider: VersionPin
    model: VersionPin
    generator: VersionPin
    model_parameters_hash: str
    connect_timeout: float = 3.0
    response_timeout: float = 120.0
    max_response_bytes: int = 2_000_000
    max_prompt_bytes: int = 1_000_000
    max_concurrency: int = 1
    keep_alive: str = "5m"
    options: Mapping[str, object] = field(default_factory=dict)
    local_only: bool = True
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "::1", "localhost")

    def __post_init__(self):
        parsed = urlsplit(self.endpoint)
        host = parsed.hostname
        try:
            parsed.port
        except ValueError as exc:
            raise ProviderPolicyError() from exc
        if (
            parsed.scheme not in ("http", "https")
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ProviderPolicyError()
        if host not in set(self.allowed_hosts):
            raise ProviderPolicyError()
        if self.local_only and not _is_loopback_host(host):
            raise ProviderPolicyError()
        if not self.model_name or any(ord(ch) < 32 for ch in self.model_name):
            raise ProviderPolicyError()
        if not all(isinstance(pin, VersionPin) for pin in (self.provider, self.model, self.generator)):
            raise ProviderPolicyError()
        if (
            not isinstance(self.model_parameters_hash, str)
            or len(self.model_parameters_hash) != 64
            or any(ch not in "0123456789abcdef" for ch in self.model_parameters_hash)
        ):
            raise ProviderPolicyError()
        try:
            frozen_options = MappingProxyType(dict(self.options))
            json.dumps(
                dict(frozen_options), ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":")
            )
        except (TypeError, ValueError) as exc:
            raise ProviderPolicyError() from exc
        object.__setattr__(self, "options", frozen_options)
        if self.connect_timeout <= 0 or self.response_timeout <= 0:
            raise ProviderPolicyError()
        if self.max_response_bytes < 1024 or self.max_prompt_bytes < 1024:
            raise ProviderPolicyError()
        if self.max_concurrency < 1 or self.max_concurrency > 64:
            raise ProviderPolicyError()
        expected = ollama_parameters_hash(
            options=self.options, keep_alive=self.keep_alive
        )
        if self.model_parameters_hash != expected:
            raise ProviderPolicyError()

    @property
    def parsed_endpoint(self):
        return urlsplit(self.endpoint)


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        try:
            addresses = {
                item[4][0] for item in socket.getaddrinfo(
                    host, None, type=socket.SOCK_STREAM
                )
            }
        except OSError as exc:
            raise ProviderPolicyError() from exc
        return bool(addresses) and all(
            ipaddress.ip_address(value).is_loopback for value in addresses
        )
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class OllamaHttpTransport:
    """Bounded direct HTTP transport. Proxy environment variables are not consulted."""

    def __init__(self, config: OllamaConfig):
        self.config = config
        self._lock = threading.Lock()
        self._active: dict[UUID, http.client.HTTPConnection] = {}

    def cancel(self, request_id: UUID):
        with self._lock:
            connection = self._active.get(request_id)
        if connection is not None:
            connection.close()

    def json_request(self, method: str, path: str, payload, request_id: UUID):
        if path not in ("/api/tags", "/api/generate"):
            raise ProviderPolicyError()
        parsed = self.config.parsed_endpoint
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        cls = (
            http.client.HTTPSConnection
            if parsed.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = cls(parsed.hostname, port, timeout=self.config.connect_timeout)
        with self._lock:
            if request_id in self._active:
                raise ProviderProtocolError()
            self._active[request_id] = connection
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            try:
                body = json.dumps(
                    payload, ensure_ascii=False, allow_nan=False,
                    sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ProviderProtocolError() from exc
            headers["Content-Type"] = "application/json"
        try:
            connection.connect()
            if connection.sock is None:
                raise ProviderUnavailable()
            connection.sock.settimeout(self.config.response_timeout)
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(self.config.max_response_bytes + 1)
            if len(raw) > self.config.max_response_bytes:
                raise ProviderResponseTooLarge()
            if response.status == 404:
                raise ProviderModelMissing()
            if response.status == 429:
                raise ProviderBusy()
            if response.status != 200:
                raise ProviderUnavailable()
            value = strict_json_bytes(raw)
            if not isinstance(value, dict):
                raise ProviderProtocolError()
            return value
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderTimeout() from exc
        except ProviderError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise ProviderUnavailable() from exc
        finally:
            with self._lock:
                self._active.pop(request_id, None)
            connection.close()


class OllamaProvider:
    """Attested local provider compatible with Stage 09 ControlledDraftingService."""

    def __init__(
        self,
        config: OllamaConfig,
        prompt_builder: Callable[[DraftingInvocation], str],
        transport=None,
    ):
        self.config = config
        self.prompt_builder = prompt_builder
        self.transport = transport or OllamaHttpTransport(config)
        self._capacity = threading.BoundedSemaphore(config.max_concurrency)
        self._lock = threading.Lock()
        self._receipts: OrderedDict[UUID, ModelExecutionReceipt] = OrderedDict()
        self._cancelled: set[UUID] = set()

    def cancel(self, request_id: UUID):
        with self._lock:
            self._cancelled.add(request_id)
        cancel = getattr(self.transport, "cancel", None)
        if cancel is not None:
            cancel(request_id)

    def _check_cancelled(self, request_id: UUID):
        with self._lock:
            if request_id in self._cancelled:
                raise ProviderCancelled()

    def _model_digest(self, request_id: UUID) -> str:
        value = self.transport.json_request(
            "GET", "/api/tags", None, request_id
        )
        models = value.get("models")
        if not isinstance(models, list):
            raise ProviderProtocolError()
        for item in models:
            if not isinstance(item, dict):
                raise ProviderProtocolError()
            names = (item.get("name"), item.get("model"))
            if self.config.model_name in names:
                model_digest = item.get("digest")
                if (
                    not isinstance(model_digest, str)
                    or len(model_digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in model_digest)
                ):
                    raise ProviderProtocolError()
                return model_digest
        raise ProviderModelMissing()

    def health(self) -> dict:
        request_id = UUID(int=0)
        actual = self._model_digest(request_id)
        return {
            "status": "READY" if actual == self.config.model.content_hash else "DRIFT",
            "model_name": self.config.model_name,
            "model_digest": actual,
        }

    def propose(self, invocation: DraftingInvocation):
        request_id = invocation.request.request_id
        if not self._capacity.acquire(blocking=False):
            raise ProviderBusy()
        try:
            self._check_cancelled(request_id)
            before = self._model_digest(request_id)
            if before != self.config.model.content_hash:
                raise ProviderProtocolError()
            try:
                prompt = self.prompt_builder(invocation)
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderProtocolError() from exc
            if not isinstance(prompt, str) or not prompt:
                raise ProviderProtocolError()
            if len(prompt.encode("utf-8")) > self.config.max_prompt_bytes:
                raise ProviderResponseTooLarge()
            self._check_cancelled(request_id)
            payload = {
                "model": self.config.model_name,
                "prompt": prompt,
                "stream": False,
                "format": AIResult.model_json_schema(),
                "keep_alive": self.config.keep_alive,
                "options": dict(self.config.options),
            }
            envelope = self.transport.json_request(
                "POST", "/api/generate", payload, request_id
            )
            self._check_cancelled(request_id)
            after = self._model_digest(request_id)
            if before != after or after != self.config.model.content_hash:
                raise ProviderProtocolError()
            if envelope.get("done") is not True:
                raise ProviderProtocolError()
            if envelope.get("model") != self.config.model_name:
                raise ProviderProtocolError()
            raw = envelope.get("response")
            if not isinstance(raw, str) or not raw.strip():
                raise ProviderProtocolError()
            try:
                result = AIResult.model_validate_json(raw)
            except ValidationError as exc:
                raise ProviderProtocolError() from exc
            if (
                result.request_id != invocation.request.request_id
                or result.snapshot_hash != invocation.request.snapshot_hash
            ):
                raise ProviderProtocolError()
            receipt = ModelExecutionReceipt(
                contract="urn:lukart:work:ModelExecutionReceipt:1.0.0",
                request_id=request_id,
                provider=self.config.provider,
                model=self.config.model,
                generator=self.config.generator,
                model_parameters_hash=self.config.model_parameters_hash,
            )
            with self._lock:
                self._receipts[request_id] = receipt
                while len(self._receipts) > self.config.max_concurrency * 2:
                    self._receipts.popitem(last=False)
            return result.model_dump(mode="json")
        finally:
            with self._lock:
                self._cancelled.discard(request_id)
            self._capacity.release()

    def execution_receipt(self, request_id: UUID) -> ModelExecutionReceipt:
        with self._lock:
            receipt = self._receipts.pop(request_id, None)
        if receipt is None:
            raise ProviderProtocolError()
        return receipt
