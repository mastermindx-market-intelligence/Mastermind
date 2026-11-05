"""Closed, secret-free physical host-capacity capture payload builder.

The builder turns one already validated ``mastermind.host_capacity_snapshot/v1``
snapshot plus a trusted host/boot/pool binding into a detached, canonical,
bounded capture payload.  It performs no acquisition, no filesystem read, no
persistence, no clock read, and no provider, host, network, auth or Runtime
effect.  Origin and admission stay explicitly external: this builder never
grants authenticity, schedulability, or capacity authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from control_plane.executive_host_capacity import (
    CAPACITY_POOL_REF_RE,
    INT64_MAX,
    HostCapacityContractError,
    canonical_host_capacity_json,
    validate_host_capacity_snapshot,
)
from control_plane.executive_host_pressure import BOOT_REF_RE, HOST_REF_RE


CAPTURE_SCHEMA = "mastermind.physical_capacity_capture/v1"
CAPTURE_CAPABILITY = "OBSERVATION_ONLY"
MAX_PAYLOAD_BYTES = 36_864
MAX_OPERATION_KEY_CHARS = 160
MAX_REVISION_CHARS = 128
MAX_FINGERPRINT_CHARS = 200

COMMIT_SHA256_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

BINDING_FIELDS: tuple[str, ...] = (
    "host_ref",
    "boot_ref",
    "capacity_pool_ref",
    "operation_key",
    "request_fingerprint",
    "source_commit_sha",
    "source_helper_sha256",
    "policy_revision",
    "host_qualification_revision",
    "runtime_identity_sha256",
)
BINDING_FIELD_SET = frozenset(BINDING_FIELDS)

_REVISION_FIELDS = frozenset({"policy_revision", "host_qualification_revision"})



class CapacityCaptureInvalid(ValueError):
    """One stable, text-free physical capacity capture refusal."""

    def __str__(self) -> str:
        return "CAPACITY_CAPTURE_INVALID"


def _refuse() -> None:
    raise CapacityCaptureInvalid("CAPACITY_CAPTURE_INVALID") from None


def _integer(value: Any, *, minimum: int) -> int:
    if type(value) is not int or not minimum <= value <= INT64_MAX:
        _refuse()
    return value


def _reference(value: Any, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse()
    return value


def _digest(value: Any, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse()
    return value


def _bounded_text(value: Any, *, maximum: int, revision: bool) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        _refuse()
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        _refuse()
    if not value.isprintable():
        _refuse()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value) is None:
        _refuse()
    return value


def _validate_binding(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != BINDING_FIELD_SET:
        _refuse()
    binding = {
        "host_ref": _reference(value.get("host_ref"), HOST_REF_RE),
        "boot_ref": _reference(value.get("boot_ref"), BOOT_REF_RE),
        "capacity_pool_ref": _reference(
            value.get("capacity_pool_ref"), CAPACITY_POOL_REF_RE
        ),
        "operation_key": _bounded_text(
            value.get("operation_key"), maximum=MAX_OPERATION_KEY_CHARS, revision=False
        ),
        "request_fingerprint": _digest(value.get("request_fingerprint"), DIGEST_SHA256_RE),
        "source_commit_sha": _digest(value.get("source_commit_sha"), COMMIT_SHA256_RE),
        "source_helper_sha256": _digest(
            value.get("source_helper_sha256"), DIGEST_SHA256_RE
        ),
        "policy_revision": _bounded_text(
            value.get("policy_revision"), maximum=MAX_REVISION_CHARS, revision=True
        ),
        "host_qualification_revision": _bounded_text(
            value.get("host_qualification_revision"),
            maximum=MAX_REVISION_CHARS,
            revision=True,
        ),
        "runtime_identity_sha256": _digest(
            value.get("runtime_identity_sha256"), DIGEST_SHA256_RE
        ),
    }
    return {field: binding[field] for field in BINDING_FIELDS}


def build_capture_payload(
    snapshot: Mapping[str, Any],
    *,
    expected_binding: Mapping[str, Any],
    snapshot_sha256: Any,
    decision_time_ms: Any,
    max_age_ms: Any,
) -> dict[str, Any]:
    """Return one closed, canonical, bounded capture payload or refuse.

    ``snapshot`` must be a secret-free ``mastermind.host_capacity_snapshot/v1``
    whose canonical SHA-256 equals ``snapshot_sha256`` and whose host, boot and
    capacity-pool references exactly match the trusted ``expected_binding``.
    ``decision_time_ms`` must be an integer clock at or after the snapshot's
    oldest observation instant, and ``max_age_ms`` must be a positive integer
    owner bound.  The payload is observation-only by construction.
    """
    try:
        normalized = validate_host_capacity_snapshot(snapshot)
    except (HostCapacityContractError, TypeError, ValueError):
        _refuse()

    if type(snapshot_sha256) is not str or DIGEST_SHA256_RE.fullmatch(
        snapshot_sha256
    ) is None:
        _refuse()
    try:
        rendered = canonical_host_capacity_json(normalized)
    except (HostCapacityContractError, TypeError, ValueError):
        _refuse()
    if hashlib.sha256(rendered).hexdigest() != snapshot_sha256:
        _refuse()

    binding = _validate_binding(expected_binding)
    if (
        binding["host_ref"] != normalized["host_ref"]
        or binding["boot_ref"] != normalized["boot_ref"]
        or binding["capacity_pool_ref"] != normalized["capacity_pool_ref"]
    ):
        _refuse()

    decision = _integer(decision_time_ms, minimum=1)
    _integer(max_age_ms, minimum=1)
    oldest_window_start_ms = normalized["observed_at_ms"] - normalized["total_observation_window_ms"]
    if (oldest_window_start_ms < 0 or decision < normalized["observed_at_ms"]
            or decision - oldest_window_start_ms > max_age_ms):
        _refuse()

    payload: dict[str, Any] = {
        "schema": CAPTURE_SCHEMA,
        "snapshot": normalized,
        "snapshot_sha256": snapshot_sha256,
        "binding": binding,
        "decision_time_ms": decision,
        "capability": CAPTURE_CAPABILITY,
        "can_place_work": False,
    }
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError):
        _refuse()
    if len(encoded) + 1 > MAX_PAYLOAD_BYTES:
        _refuse()
    return payload


__all__ = [
    "BINDING_FIELDS",
    "CAPTURE_CAPABILITY",
    "CAPTURE_SCHEMA",
    "MAX_PAYLOAD_BYTES",
    "CapacityCaptureInvalid",
    "build_capture_payload",
]


# Observation-only capture boundary: this builder never grants authenticity,
# admission, schedulability, or any capacity authority.  The origin/admission
# boundary is explicitly external and stays outside this closed payload.
