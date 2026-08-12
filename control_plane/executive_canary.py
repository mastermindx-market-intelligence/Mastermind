"""Distinct-principal, content-blind secret-canary probe.

The probe performs open-only permission checks.  It never reads a sentinel,
credential, database, or sidecar byte, and its successful receipt contains only
fixed statuses plus a SHA-256 commitment to the exact probe configuration.
"""

from __future__ import annotations

import dataclasses
import errno
import hashlib
import hmac
import json
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from control_plane.codex_worker import SECRET_CANARY_SCHEMA_VERSION

WORKER_AUTH_EXCEPTION = "DEDICATED_CODEX_HOME_ONLY"
REQUIRED_CHECKS = (
    "control_service_environment",
    "administrative_checkout",
    "executive_database",
    "other_worker_home",
    "forbidden_production_path",
)
_ENVIRONMENT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_DENIED_ERRNOS = frozenset({errno.EACCES, errno.EPERM})
_DATABASE_SIDECARS = ("-wal", "-shm", "-journal")
_READ_ONLY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)

OpenFunction = Callable[[Path, int], int]
CloseFunction = Callable[[int], None]
ClockFunction = Callable[[], datetime]


class SecretCanaryError(RuntimeError):
    """A safe, path-free reason why no passing receipt can be issued."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class PrincipalIdentity:
    real_uid: int
    effective_uid: int
    real_gid: int
    effective_gid: int

    @classmethod
    def current(cls) -> PrincipalIdentity:
        return cls(
            real_uid=os.getuid(),
            effective_uid=os.geteuid(),
            real_gid=os.getgid(),
            effective_gid=os.getegid(),
        )


@dataclasses.dataclass(frozen=True)
class SecretCanaryConfig:
    expected_worker_uid: int
    expected_worker_gid: int
    control_uid: int
    control_gid: int
    control_environment_sentinel: str
    control_environment_probe_sha256: str
    administrative_checkout_sentinel: Path
    executive_database: Path
    other_worker_home_sentinel: Path
    forbidden_production_sentinel: Path
    codex_home: Path


def _absolute_paths(config: SecretCanaryConfig) -> tuple[Path, ...]:
    return (
        config.administrative_checkout_sentinel,
        config.executive_database,
        config.other_worker_home_sentinel,
        config.forbidden_production_sentinel,
        config.codex_home,
    )


def _database_paths(database: Path) -> tuple[Path, ...]:
    if not database.name:
        raise SecretCanaryError("CANARY_CONFIGURATION_INVALID")
    return (
        database,
        *(database.with_name(database.name + suffix) for suffix in _DATABASE_SIDECARS),
    )


def _validate_config(config: SecretCanaryConfig) -> None:
    if not isinstance(config, SecretCanaryConfig):
        raise SecretCanaryError("CANARY_CONFIGURATION_INVALID")
    identifiers = (
        config.expected_worker_uid,
        config.expected_worker_gid,
        config.control_uid,
        config.control_gid,
    )
    if any(type(value) is not int or value < 0 for value in identifiers):
        raise SecretCanaryError("CANARY_CONFIGURATION_INVALID")
    if config.expected_worker_uid == 0 or config.expected_worker_gid == 0:
        raise SecretCanaryError("CANARY_EXPECTED_PRINCIPAL_IS_ROOT")
    if (
        config.expected_worker_uid == config.control_uid
        or config.expected_worker_gid == config.control_gid
    ):
        raise SecretCanaryError("CANARY_PRINCIPALS_NOT_DISTINCT")
    if not isinstance(
        config.control_environment_sentinel, str
    ) or not _ENVIRONMENT_NAME_RE.fullmatch(config.control_environment_sentinel):
        raise SecretCanaryError("CANARY_CONFIGURATION_INVALID")
    if (
        not isinstance(config.control_environment_probe_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", config.control_environment_probe_sha256)
        is None
    ):
        raise SecretCanaryError("CANARY_CONFIGURATION_INVALID")
    paths = _absolute_paths(config)
    if any(not isinstance(path, Path) or not path.is_absolute() for path in paths):
        raise SecretCanaryError("CANARY_PATH_NOT_ABSOLUTE")
    protected = (
        config.administrative_checkout_sentinel,
        *_database_paths(config.executive_database),
        config.other_worker_home_sentinel,
        config.forbidden_production_sentinel,
    )
    auth = config.codex_home / "auth.json"
    lexical_paths = [os.fspath(path) for path in (*protected, auth)]
    if any("\x00" in path for path in lexical_paths):
        raise SecretCanaryError("CANARY_CONFIGURATION_INVALID")
    if len(lexical_paths) != len(set(lexical_paths)):
        raise SecretCanaryError("CANARY_CONFIGURATION_INVALID")


def _validate_principal(
    config: SecretCanaryConfig,
    principal: PrincipalIdentity,
) -> None:
    if not isinstance(principal, PrincipalIdentity):
        raise SecretCanaryError("CANARY_PRINCIPAL_INVALID")
    values = dataclasses.astuple(principal)
    if any(type(value) is not int or value < 0 for value in values):
        raise SecretCanaryError("CANARY_PRINCIPAL_INVALID")
    if (
        principal.real_uid != config.expected_worker_uid
        or principal.effective_uid != config.expected_worker_uid
        or principal.real_gid != config.expected_worker_gid
        or principal.effective_gid != config.expected_worker_gid
    ):
        raise SecretCanaryError("CANARY_PRINCIPAL_MISMATCH")


def _open_must_be_denied(
    path: Path,
    *,
    opener: OpenFunction,
    closer: CloseFunction,
) -> None:
    try:
        descriptor = opener(path, _READ_ONLY_FLAGS)
    except OSError as exc:
        if exc.errno in _DENIED_ERRNOS:
            return
        raise SecretCanaryError("CANARY_PROTECTED_OPEN_NOT_PERMISSION_DENIED") from None
    try:
        closer(descriptor)
    except OSError:
        raise SecretCanaryError(
            "CANARY_PROTECTED_OPEN_UNEXPECTEDLY_SUCCEEDED"
        ) from None
    raise SecretCanaryError("CANARY_PROTECTED_OPEN_UNEXPECTEDLY_SUCCEEDED")


def _open_dedicated_auth(
    path: Path,
    *,
    opener: OpenFunction,
    closer: CloseFunction,
) -> None:
    """Open and immediately close auth.json without reading or serializing bytes."""

    try:
        descriptor = opener(path, _READ_ONLY_FLAGS)
    except OSError:
        raise SecretCanaryError("CANARY_DEDICATED_AUTH_NOT_OPENABLE") from None
    try:
        closer(descriptor)
    except OSError:
        raise SecretCanaryError("CANARY_DEDICATED_AUTH_CLOSE_FAILED") from None


def _observed_at(clock: ClockFunction | None) -> str:
    value = clock() if clock is not None else datetime.now(UTC)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SecretCanaryError("CANARY_CLOCK_INVALID")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="strict")).hexdigest()


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path)).hexdigest()


def _receipt_sha256(
    *,
    config: SecretCanaryConfig,
    principal: PrincipalIdentity,
    checks: Mapping[str, str],
    observed_at: str,
) -> str:
    """Commit to exact probe inputs without returning their path or name content."""

    material: dict[str, Any] = {
        "schema_version": SECRET_CANARY_SCHEMA_VERSION,
        "observed_at": observed_at,
        "checks": dict(checks),
        "worker_auth_exception": WORKER_AUTH_EXCEPTION,
        "principal": {
            "expected_worker_uid": config.expected_worker_uid,
            "expected_worker_gid": config.expected_worker_gid,
            "control_uid": config.control_uid,
            "control_gid": config.control_gid,
            "real_uid": principal.real_uid,
            "effective_uid": principal.effective_uid,
            "real_gid": principal.real_gid,
            "effective_gid": principal.effective_gid,
        },
        "control_environment_sentinel_sha256": _sha256_text(
            config.control_environment_sentinel
        ),
        "control_environment_probe_sha256": config.control_environment_probe_sha256,
        "target_path_sha256": {
            "administrative_checkout": [
                _sha256_path(config.administrative_checkout_sentinel)
            ],
            "executive_database": [
                _sha256_path(path)
                for path in _database_paths(config.executive_database)
            ],
            "other_worker_home": [_sha256_path(config.other_worker_home_sentinel)],
            "forbidden_production_path": [
                _sha256_path(config.forbidden_production_sentinel)
            ],
            "dedicated_codex_auth": [_sha256_path(config.codex_home / "auth.json")],
        },
    }
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_secret_canary(
    config: SecretCanaryConfig,
    *,
    opener: OpenFunction = os.open,
    closer: CloseFunction = os.close,
    environment: Mapping[str, str] | None = None,
    principal: PrincipalIdentity | None = None,
    clock: ClockFunction | None = None,
) -> dict[str, Any]:
    """Return one validator-compatible receipt or fail without partial output."""

    _validate_config(config)
    observed_principal = principal or PrincipalIdentity.current()
    _validate_principal(config, observed_principal)
    visible_environment = os.environ if environment is None else environment
    if config.control_environment_sentinel in visible_environment:
        raise SecretCanaryError("CANARY_CONTROL_ENVIRONMENT_VISIBLE")

    _open_must_be_denied(
        config.administrative_checkout_sentinel,
        opener=opener,
        closer=closer,
    )
    for path in _database_paths(config.executive_database):
        _open_must_be_denied(path, opener=opener, closer=closer)
    _open_must_be_denied(
        config.other_worker_home_sentinel,
        opener=opener,
        closer=closer,
    )
    _open_must_be_denied(
        config.forbidden_production_sentinel,
        opener=opener,
        closer=closer,
    )
    _open_dedicated_auth(
        config.codex_home / "auth.json",
        opener=opener,
        closer=closer,
    )

    checks = dict.fromkeys(REQUIRED_CHECKS, "DENIED")
    observed_at = _observed_at(clock)
    return {
        "schema_version": SECRET_CANARY_SCHEMA_VERSION,
        "passed": True,
        "checks": checks,
        "receipt_sha256": _receipt_sha256(
            config=config,
            principal=observed_principal,
            checks=checks,
            observed_at=observed_at,
        ),
        "control_environment_probe_sha256": config.control_environment_probe_sha256,
        "observed_at": observed_at,
        "worker_auth_exception": WORKER_AUTH_EXCEPTION,
    }


def validate_secret_canary_binding(
    config: SecretCanaryConfig,
    principal: PrincipalIdentity,
    verdict: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute the strict receipt commitment for one exact probe configuration."""

    from control_plane.codex_worker import (
        LaunchValidationError,
        validate_secret_canary_verdict,
    )

    _validate_config(config)
    _validate_principal(config, principal)
    try:
        document = validate_secret_canary_verdict(verdict, require_passed=True)
    except LaunchValidationError as exc:
        raise SecretCanaryError("CANARY_RECEIPT_SHAPE_INVALID") from exc
    if (
        document["control_environment_probe_sha256"]
        != config.control_environment_probe_sha256
    ):
        raise SecretCanaryError("CANARY_CONTROL_PROBE_BINDING_MISMATCH")
    expected = _receipt_sha256(
        config=config,
        principal=principal,
        checks=document["checks"],
        observed_at=document["observed_at"],
    )
    if not hmac.compare_digest(document["receipt_sha256"], expected):
        raise SecretCanaryError("CANARY_RECEIPT_BINDING_MISMATCH")
    return document


__all__ = [
    "REQUIRED_CHECKS",
    "WORKER_AUTH_EXCEPTION",
    "PrincipalIdentity",
    "SecretCanaryConfig",
    "SecretCanaryError",
    "run_secret_canary",
    "validate_secret_canary_binding",
]
