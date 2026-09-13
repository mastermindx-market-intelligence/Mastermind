"""Closed, data-only contract for authenticated multi-host Worker Broker transport.

This module owns no lifecycle, queue, placement, retry, provider credential, or
network side effect. It binds an already-selected Executive Job/Attempt/Worker/
host operation to one exact existing Worker Broker request payload.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import ipaddress
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any


REMOTE_BROKER_REQUEST_SCHEMA = "mastermind.remote_worker_broker_request/v1"
REMOTE_BROKER_RESPONSE_SCHEMA = "mastermind.remote_worker_broker_response/v1"

_JOB_ID_RE = re.compile(r"^JOB-\d{3,}$")
_ATTEMPT_ID_RE = re.compile(r"^ATT-[0-9a-f]{32}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\.?$"
)

_REQUEST_KEYS = frozenset(
    {
        "schema",
        "host_ref",
        "job_id",
        "attempt_id",
        "worker_id",
        "operation_id",
        "broker_operation",
        "request_sha256",
        "broker_request",
    }
)
_RESPONSE_KEYS = frozenset(
    {
        "schema",
        "host_ref",
        "job_id",
        "attempt_id",
        "worker_id",
        "operation_id",
        "request_sha256",
        "outcome",
        "broker_response",
        "observed_at",
    }
)


class RemoteWorkerTransportError(ValueError):
    """Closed refusal for malformed or unsafe MH1 transport values."""


class RemoteOperationConflict(RemoteWorkerTransportError):
    """The same stable remote operation identity was reused inconsistently."""


def _json_normalize(value: Any, *, field: str) -> Any:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return json.loads(encoded.decode("utf-8"))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RemoteWorkerTransportError(f"{field} must be canonical JSON") from exc


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _json_normalize(_thaw(value), field="value")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def broker_request_sha256(broker_request: Mapping[str, Any]) -> str:
    if not isinstance(broker_request, Mapping):
        raise RemoteWorkerTransportError("broker_request must be an object")
    return hashlib.sha256(canonical_json_bytes(broker_request)).hexdigest()


def _object(value: Any, *, field: str) -> dict[str, Any]:
    normalized = _json_normalize(value, field=field)
    if not isinstance(normalized, dict):
        raise RemoteWorkerTransportError(f"{field} must be an object")
    return normalized


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], *, field: str) -> None:
    if set(value) != expected:
        raise RemoteWorkerTransportError(
            f"{field} must contain exactly {sorted(expected)!r}"
        )


def _match(value: Any, pattern: re.Pattern[str], *, field: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RemoteWorkerTransportError(f"{field} is malformed")
    return value


def _identifier(value: Any, *, field: str) -> str:
    result = _match(value, _IDENTIFIER_RE, field=field)
    if "@" in result:
        raise RemoteWorkerTransportError(f"{field} must be an opaque non-PII token")
    return result


def _digest(value: Any, *, field: str) -> str:
    return _match(value, _DIGEST_RE, field=field)


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise RemoteWorkerTransportError("observed_at must be a timestamp string")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise RemoteWorkerTransportError("observed_at is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RemoteWorkerTransportError("observed_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _endpoint_host(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RemoteWorkerTransportError("endpoint_host is malformed")
    if any(token in value for token in ("/", "\\", "://", "\x00")):
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            raise RemoteWorkerTransportError("endpoint_host is malformed") from exc
        return value
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        if _HOSTNAME_RE.fullmatch(value) is None:
            raise RemoteWorkerTransportError("endpoint_host is malformed")
        return value[:-1] if value.endswith(".") else value


def _absolute_path(value: Any, *, field: str) -> Path:
    try:
        path = Path(value)
    except TypeError as exc:
        raise RemoteWorkerTransportError(f"{field} must be a filesystem path") from exc
    if not path.is_absolute():
        raise RemoteWorkerTransportError(f"{field} must be absolute")
    return path


@dataclasses.dataclass(frozen=True)
class BrokerTransportBinding:
    """Root-managed local control-host binding; never a durable/public receipt."""

    host_ref: str
    endpoint_host: str = dataclasses.field(repr=False)
    endpoint_port: int
    expected_server_certificate_sha256: str = dataclasses.field(repr=False)
    client_certificate_path: Path = dataclasses.field(repr=False)
    client_private_key_path: Path = dataclasses.field(repr=False)
    ca_certificate_path: Path = dataclasses.field(repr=False)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "host_ref", _identifier(self.host_ref, field="host_ref"))
        object.__setattr__(self, "endpoint_host", _endpoint_host(self.endpoint_host))
        if type(self.endpoint_port) is not int or not 1 <= self.endpoint_port <= 65535:
            raise RemoteWorkerTransportError("endpoint_port must be an integer in 1..65535")
        object.__setattr__(
            self,
            "expected_server_certificate_sha256",
            _digest(
                self.expected_server_certificate_sha256,
                field="expected_server_certificate_sha256",
            ),
        )
        for field in (
            "client_certificate_path",
            "client_private_key_path",
            "ca_certificate_path",
        ):
            object.__setattr__(self, field, _absolute_path(getattr(self, field), field=field))
        timeout = float(self.timeout_seconds)
        if not 0.1 <= timeout <= 3600.0:
            raise RemoteWorkerTransportError("timeout_seconds is outside the safe range")
        object.__setattr__(self, "timeout_seconds", timeout)


@dataclasses.dataclass(frozen=True)
class RemoteBrokerRequest:
    schema: str
    host_ref: str
    job_id: str
    attempt_id: str
    worker_id: str
    operation_id: str
    broker_operation: str
    request_sha256: str
    broker_request: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema != REMOTE_BROKER_REQUEST_SCHEMA:
            raise RemoteWorkerTransportError("remote request schema is unsupported")
        object.__setattr__(self, "host_ref", _identifier(self.host_ref, field="host_ref"))
        object.__setattr__(self, "job_id", _match(self.job_id, _JOB_ID_RE, field="job_id"))
        object.__setattr__(
            self,
            "attempt_id",
            _match(self.attempt_id, _ATTEMPT_ID_RE, field="attempt_id"),
        )
        object.__setattr__(self, "worker_id", _identifier(self.worker_id, field="worker_id"))
        object.__setattr__(
            self, "operation_id", _identifier(self.operation_id, field="operation_id")
        )
        object.__setattr__(
            self,
            "broker_operation",
            _identifier(self.broker_operation, field="broker_operation"),
        )
        request = _object(_thaw(self.broker_request), field="broker_request")
        embedded_operation = request.get("operation")
        if embedded_operation is not None and embedded_operation != self.broker_operation:
            raise RemoteWorkerTransportError(
                "broker_operation does not match embedded broker request operation"
            )
        actual = broker_request_sha256(request)
        expected = _digest(self.request_sha256, field="request_sha256")
        if not hmac.compare_digest(actual, expected):
            raise RemoteWorkerTransportError("broker request hash does not match request_sha256")
        object.__setattr__(self, "request_sha256", expected)
        object.__setattr__(self, "broker_request", _freeze(request))

    @classmethod
    def build(
        cls,
        *,
        host_ref: str,
        job_id: str,
        attempt_id: str,
        worker_id: str,
        operation_id: str,
        broker_operation: str,
        broker_request: Mapping[str, Any],
    ) -> "RemoteBrokerRequest":
        request = _object(_thaw(broker_request), field="broker_request")
        return cls(
            schema=REMOTE_BROKER_REQUEST_SCHEMA,
            host_ref=host_ref,
            job_id=job_id,
            attempt_id=attempt_id,
            worker_id=worker_id,
            operation_id=operation_id,
            broker_operation=broker_operation,
            request_sha256=broker_request_sha256(request),
            broker_request=request,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RemoteBrokerRequest":
        raw = _object(_thaw(value), field="remote request")
        _exact_keys(raw, _REQUEST_KEYS, field="remote request")
        return cls(**raw)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "host_ref": self.host_ref,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "operation_id": self.operation_id,
            "broker_operation": self.broker_operation,
            "request_sha256": self.request_sha256,
            "broker_request": _thaw(self.broker_request),
        }


@dataclasses.dataclass(frozen=True)
class RemoteBrokerResponse:
    schema: str
    host_ref: str
    job_id: str
    attempt_id: str
    worker_id: str
    operation_id: str
    request_sha256: str
    outcome: str
    broker_response: Mapping[str, Any]
    observed_at: str

    def __post_init__(self) -> None:
        if self.schema != REMOTE_BROKER_RESPONSE_SCHEMA:
            raise RemoteWorkerTransportError("remote response schema is unsupported")
        object.__setattr__(self, "host_ref", _identifier(self.host_ref, field="host_ref"))
        object.__setattr__(self, "job_id", _match(self.job_id, _JOB_ID_RE, field="job_id"))
        object.__setattr__(
            self,
            "attempt_id",
            _match(self.attempt_id, _ATTEMPT_ID_RE, field="attempt_id"),
        )
        object.__setattr__(self, "worker_id", _identifier(self.worker_id, field="worker_id"))
        object.__setattr__(
            self, "operation_id", _identifier(self.operation_id, field="operation_id")
        )
        object.__setattr__(
            self, "request_sha256", _digest(self.request_sha256, field="request_sha256")
        )
        object.__setattr__(self, "outcome", _identifier(self.outcome, field="outcome"))
        object.__setattr__(
            self,
            "broker_response",
            _freeze(_object(_thaw(self.broker_response), field="broker_response")),
        )
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at))

    @classmethod
    def build(
        cls,
        *,
        request: RemoteBrokerRequest,
        outcome: str,
        broker_response: Mapping[str, Any],
        observed_at: str,
    ) -> "RemoteBrokerResponse":
        return cls(
            schema=REMOTE_BROKER_RESPONSE_SCHEMA,
            host_ref=request.host_ref,
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            worker_id=request.worker_id,
            operation_id=request.operation_id,
            request_sha256=request.request_sha256,
            outcome=outcome,
            broker_response=broker_response,
            observed_at=observed_at,
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        expected_request: RemoteBrokerRequest | None = None,
    ) -> "RemoteBrokerResponse":
        raw = _object(_thaw(value), field="remote response")
        _exact_keys(raw, _RESPONSE_KEYS, field="remote response")
        response = cls(**raw)
        if expected_request is not None:
            expected = (
                expected_request.host_ref,
                expected_request.job_id,
                expected_request.attempt_id,
                expected_request.worker_id,
                expected_request.operation_id,
            )
            actual = (
                response.host_ref,
                response.job_id,
                response.attempt_id,
                response.worker_id,
                response.operation_id,
            )
            if actual != expected or not hmac.compare_digest(
                response.request_sha256, expected_request.request_sha256
            ):
                raise RemoteWorkerTransportError(
                    "remote response identity does not match the request identity"
                )
        return response

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "host_ref": self.host_ref,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "operation_id": self.operation_id,
            "request_sha256": self.request_sha256,
            "outcome": self.outcome,
            "broker_response": _thaw(self.broker_response),
            "observed_at": self.observed_at,
        }


def assert_operation_replay_compatible(
    prior: RemoteBrokerRequest,
    candidate: RemoteBrokerRequest,
) -> None:
    """Refuse identity/payload mutation under one stable remote operation key."""

    if prior.operation_id != candidate.operation_id:
        return
    prior_identity = (
        prior.host_ref,
        prior.job_id,
        prior.attempt_id,
        prior.worker_id,
        prior.broker_operation,
    )
    candidate_identity = (
        candidate.host_ref,
        candidate.job_id,
        candidate.attempt_id,
        candidate.worker_id,
        candidate.broker_operation,
    )
    if prior_identity != candidate_identity:
        raise RemoteOperationConflict(
            "remote operation identity was reused with different bound identity"
        )
    if not hmac.compare_digest(prior.request_sha256, candidate.request_sha256):
        raise RemoteOperationConflict(
            "remote operation identity was reused with changed broker payload"
        )


__all__ = [
    "REMOTE_BROKER_REQUEST_SCHEMA",
    "REMOTE_BROKER_RESPONSE_SCHEMA",
    "BrokerTransportBinding",
    "RemoteBrokerRequest",
    "RemoteBrokerResponse",
    "RemoteOperationConflict",
    "RemoteWorkerTransportError",
    "assert_operation_replay_compatible",
    "broker_request_sha256",
    "canonical_json_bytes",
]
