"""Closed secret-free Phase 1F-C placement and principal evidence schemas.

The helpers are pure: they perform no host lookup, filesystem access, provider
call, or database write.  The supervisor owns observations; Runtime joins them
to immutable placement facts and persists only canonical JSON plus SHA-256.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import posixpath
import re
from collections.abc import Mapping
from typing import Any


PLACEMENT_SCHEMA = "mastermind.executive_placement_snapshot/v1"
PRINCIPAL_OBSERVATION_SCHEMA = "mastermind.operator_principal_observation/v1"
PRINCIPAL_SNAPSHOT_SCHEMA = "mastermind.execution_principal_snapshot/v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9._@+:-]{0,127}$")
_OS_PRINCIPAL_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class OrchestrationPrincipalError(ValueError):
    """A placement, observation, or principal snapshot is not the closed wire."""


@dataclasses.dataclass(frozen=True)
class OSProcessCredentialObservation:
    """Read-only host credentials for the exact TX-3-bound process."""

    process_identity: dict[str, Any]
    os_principal_name: str
    os_principal_uid: int

    def __post_init__(self) -> None:
        validate_process_identity(self.process_identity)
        _text(
            self.os_principal_name,
            name="os_principal_name",
            pattern=_OS_PRINCIPAL_RE,
        )
        _integer(self.os_principal_uid, name="os_principal_uid")


@dataclasses.dataclass(frozen=True)
class ProviderHomeIdentityObservation:
    """Fresh symlink-safe lstat identity of one explicit provider home."""

    provider_home_identity: dict[str, Any]

    def __post_init__(self) -> None:
        validate_provider_home_identity(self.provider_home_identity)


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OrchestrationPrincipalError(f"value is not canonical JSON data: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _closed(value: Any, *, name: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        actual = sorted(value) if isinstance(value, Mapping) else type(value).__name__
        raise OrchestrationPrincipalError(
            f"{name} must have exactly {sorted(keys)}; got {actual}"
        )
    return value


def _text(value: Any, *, name: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OrchestrationPrincipalError(f"{name} must be non-empty canonical text")
    if "\x00" in value:
        raise OrchestrationPrincipalError(f"{name} contains NUL")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OrchestrationPrincipalError(f"{name} is not UTF-8 text") from exc
    if pattern is not None and pattern.fullmatch(value) is None:
        raise OrchestrationPrincipalError(f"{name} has an unsupported form")
    return value


def _integer(value: Any, *, name: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OrchestrationPrincipalError(f"{name} must be an integer")
    if value < (1 if positive else 0):
        raise OrchestrationPrincipalError(f"{name} is outside its non-negative bound")
    return value


_HOME_KEYS = frozenset({"path", "device", "inode", "uid", "gid", "mode"})
_PROCESS_KEYS = frozenset({"pid", "pgid", "process_start_identity", "boot_id"})
_OBSERVATION_KEYS = frozenset(
    {
        "schema_version",
        "attempt_id",
        "worker_id",
        "process_generation_id",
        "provider_session_id",
        "process_identity",
        "os_principal_name",
        "os_principal_uid",
        "provider_home_identity",
        "observed_at_ms",
    }
)


def validate_provider_home_identity(value: Any) -> dict[str, Any]:
    raw = _closed(value, name="provider_home_identity", keys=_HOME_KEYS)
    path = _text(raw["path"], name="provider_home_identity.path")
    if (
        not path.startswith("/")
        or "//" in path
        or path != posixpath.normpath(path)
        or (path != "/" and path.endswith("/"))
    ):
        raise OrchestrationPrincipalError("provider_home_identity.path must be canonical absolute")
    resolved = {
        "path": path,
        "device": _integer(raw["device"], name="provider_home_identity.device"),
        "inode": _integer(raw["inode"], name="provider_home_identity.inode"),
        "uid": _integer(raw["uid"], name="provider_home_identity.uid"),
        "gid": _integer(raw["gid"], name="provider_home_identity.gid"),
        "mode": _integer(raw["mode"], name="provider_home_identity.mode"),
    }
    if resolved["mode"] != 0o700:
        raise OrchestrationPrincipalError("provider_home_identity.mode must be 0700")
    return resolved


def validate_process_identity(value: Any) -> dict[str, Any]:
    raw = _closed(value, name="process_identity", keys=_PROCESS_KEYS)
    return {
        "pid": _integer(raw["pid"], name="process_identity.pid", positive=True),
        "pgid": _integer(raw["pgid"], name="process_identity.pgid", positive=True),
        "process_start_identity": _text(
            raw["process_start_identity"], name="process_identity.process_start_identity"
        ),
        "boot_id": _text(raw["boot_id"], name="process_identity.boot_id"),
    }


@dataclasses.dataclass(frozen=True)
class OperatorPrincipalObservation:
    attempt_id: str
    worker_id: str
    process_generation_id: str
    provider_session_id: str
    process_identity: dict[str, Any]
    os_principal_name: str
    os_principal_uid: int
    provider_home_identity: dict[str, Any]
    observed_at_ms: int
    schema_version: str = PRINCIPAL_OBSERVATION_SCHEMA

    @classmethod
    def from_dict(cls, value: Any) -> "OperatorPrincipalObservation":
        raw = _closed(
            value, name="operator principal observation", keys=_OBSERVATION_KEYS
        )
        if raw["schema_version"] != PRINCIPAL_OBSERVATION_SCHEMA:
            raise OrchestrationPrincipalError("unsupported principal observation schema")
        uid = _integer(raw["os_principal_uid"], name="os_principal_uid")
        home = validate_provider_home_identity(raw["provider_home_identity"])
        if home["uid"] != uid:
            raise OrchestrationPrincipalError(
                "provider-home owner uid must equal observed process uid"
            )
        return cls(
            attempt_id=_text(raw["attempt_id"], name="attempt_id", pattern=_ID_RE),
            worker_id=_text(raw["worker_id"], name="worker_id", pattern=_ID_RE),
            process_generation_id=_text(
                raw["process_generation_id"], name="process_generation_id", pattern=_ID_RE
            ),
            provider_session_id=_text(
                raw["provider_session_id"], name="provider_session_id", pattern=_ID_RE
            ),
            process_identity=validate_process_identity(raw["process_identity"]),
            os_principal_name=_text(
                raw["os_principal_name"], name="os_principal_name", pattern=_OS_PRINCIPAL_RE
            ),
            os_principal_uid=uid,
            provider_home_identity=home,
            observed_at_ms=_integer(raw["observed_at_ms"], name="observed_at_ms"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "process_generation_id": self.process_generation_id,
            "provider_session_id": self.provider_session_id,
            "process_identity": dict(self.process_identity),
            "os_principal_name": self.os_principal_name,
            "os_principal_uid": self.os_principal_uid,
            "provider_home_identity": dict(self.provider_home_identity),
            "observed_at_ms": self.observed_at_ms,
        }


def build_placement_snapshot(
    *,
    worker_id: str,
    quota_class: str,
    provider: str,
    account_label: str,
    observed_at_ms: int,
) -> dict[str, Any]:
    value = {
        "schema_version": PLACEMENT_SCHEMA,
        "worker_id": _text(worker_id, name="worker_id", pattern=_ID_RE),
        "quota_class": _text(quota_class, name="quota_class", pattern=_ID_RE),
        "provider": _text(provider, name="provider", pattern=_PROVIDER_RE),
        "account_label": _text(account_label, name="account_label", pattern=_ACCOUNT_RE),
        "observed_at_ms": _integer(observed_at_ms, name="observed_at_ms"),
    }
    return value


def validate_placement_snapshot(value: Any) -> dict[str, Any]:
    raw = _closed(
        value,
        name="placement snapshot",
        keys=frozenset(
            {
                "schema_version",
                "worker_id",
                "quota_class",
                "provider",
                "account_label",
                "observed_at_ms",
            }
        ),
    )
    if raw["schema_version"] != PLACEMENT_SCHEMA:
        raise OrchestrationPrincipalError("unsupported placement snapshot schema")
    return build_placement_snapshot(
        worker_id=raw["worker_id"],
        quota_class=raw["quota_class"],
        provider=raw["provider"],
        account_label=raw["account_label"],
        observed_at_ms=raw["observed_at_ms"],
    )


def build_execution_principal_snapshot(
    *,
    attempt_id: str,
    placement_snapshot: Any,
    observation: OperatorPrincipalObservation | Mapping[str, Any],
) -> dict[str, Any]:
    placement = validate_placement_snapshot(placement_snapshot)
    observed = (
        observation
        if isinstance(observation, OperatorPrincipalObservation)
        else OperatorPrincipalObservation.from_dict(observation)
    )
    if observed.attempt_id != attempt_id or observed.worker_id != placement["worker_id"]:
        raise OrchestrationPrincipalError("principal observation placement mismatch")
    return {
        "schema_version": PRINCIPAL_SNAPSHOT_SCHEMA,
        "attempt_id": _text(attempt_id, name="attempt_id", pattern=_ID_RE),
        "worker_id": placement["worker_id"],
        "quota_class": placement["quota_class"],
        "provider": placement["provider"],
        "account_label": placement["account_label"],
        "placement_snapshot_digest": digest(placement),
        "os_principal_name": observed.os_principal_name,
        "os_principal_uid": observed.os_principal_uid,
        "provider_home_identity": dict(observed.provider_home_identity),
    }


def validate_digest(value: Any, *, name: str = "digest") -> str:
    return _text(value, name=name, pattern=_DIGEST_RE)


__all__ = [
    "OSProcessCredentialObservation",
    "OperatorPrincipalObservation",
    "OrchestrationPrincipalError",
    "PLACEMENT_SCHEMA",
    "PRINCIPAL_OBSERVATION_SCHEMA",
    "PRINCIPAL_SNAPSHOT_SCHEMA",
    "ProviderHomeIdentityObservation",
    "build_execution_principal_snapshot",
    "build_placement_snapshot",
    "canonical_bytes",
    "digest",
    "validate_digest",
    "validate_placement_snapshot",
    "validate_process_identity",
    "validate_provider_home_identity",
]
