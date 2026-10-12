"""Project the existing Runtime pin through the authenticated Control channel.

This is not a lease, first-use ledger, attendance producer or signing authority.
Only the kernel-authenticated Control peer may turn this public projection into
an internal command. The concrete Backend must recheck it and consume the
original controller's O_EXCL reservation before any provider effect. Missing
records never reconstruct this command during recovery.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
import hashlib
import json
import math
import time
from typing import Any, Mapping

from ops.executive_os.capacity_broker_topology import CONTROL_UID

SCHEMA = "mastermind.fabric_control_start/v1"
_PEER_VERIFIED = object()
_FIELDS = frozenset({"schema_version", "attempt_id", "fence_generation",
                     "pin_version", "pin_identity_sha256", "lease_expires_at"})


class ControlStartRefused(ValueError):
    pass


def _material(payload):
    return {k: v for k, v in payload.items()
            if k not in {"control_start", "start_request_sha256"}}


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def launch_identity(payload):
    material = _material(payload)
    return _sha({"physical_binding_sha256": material["physical_binding_sha256"],
                 "request": material})


def _expiry(value):
    try:
        if type(value) is not str or not value.endswith(("Z", "+00:00")):
            raise ValueError
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        result = parsed.timestamp()
        if not math.isfinite(result):
            raise ValueError
        return result
    except (ValueError, OverflowError, OSError) as exc:
        raise ControlStartRefused("invalid_runtime_lease_expiry") from exc


def command_from_validated_pin(attempt, payload):
    """Called by Control immediately after validate_pinned_remote_launch.

    This pure projection cannot validate the opaque lease. The caller keeps
    that token in Runtime and must not reconstruct a fresh command on recovery.
    """
    from control_plane.executive_runtime import Attempt, AttemptStatus, REMOTE_LAUNCH_IDENTITY_KEY

    if (type(attempt) is not Attempt or attempt.status is not AttemptStatus.CLAIMED
            or attempt.attempt_id != payload["binding"]["attempt_id"]
            or attempt.job_id != payload["binding"]["job_id"]
            or attempt.pid is not None or attempt.provider_session_id is not None
            or attempt.launch_metadata.get(REMOTE_LAUNCH_IDENTITY_KEY, {}).get("sha256")
            != launch_identity(payload)):
        raise ControlStartRefused("runtime_pin_does_not_match_launch")
    value = {"schema_version": SCHEMA, "attempt_id": attempt.attempt_id,
             "fence_generation": attempt.fence_generation, "pin_version": attempt.version,
             "pin_identity_sha256": launch_identity(payload),
             "lease_expires_at": attempt.lease_expires_at}
    _validate(value, payload)
    return value


def _validate(value, payload):
    if (type(value) is not dict or set(value) != _FIELDS
            or value["schema_version"] != SCHEMA
            or value["attempt_id"] != payload["binding"]["attempt_id"]
            or value["pin_identity_sha256"] != launch_identity(payload)
            or any(type(value[k]) is not int or not 1 <= value[k] <= 2**63 - 1
                   for k in ("fence_generation", "pin_version"))):
        raise ControlStartRefused("control_start_projection_mismatch")
    return _expiry(value["lease_expires_at"])


@dataclasses.dataclass(frozen=True)
class ControlStartAuthority:
    """In-process command only; JSON fields and correlation do not construct it."""

    payload_sha256: str
    pin_identity_sha256: str
    attempt_id: str
    fence_generation: int
    pin_version: int
    expires_at: float
    _peer_verified: object = dataclasses.field(default=None, repr=False, compare=False)

    def require(self, payload: Mapping[str, Any], *, now=None):
        observed = time.time() if now is None else now
        if (self._peer_verified is not _PEER_VERIFIED
                or type(observed) not in (int, float) or not math.isfinite(observed)
                or observed >= self.expires_at
                or self.payload_sha256 != _sha(_material(payload))
                or self.pin_identity_sha256 != launch_identity(payload)
                or self.attempt_id != payload["binding"]["attempt_id"]):
            raise ControlStartRefused("control_start_authority_unavailable")


def authorize_control_command(payload, *, peer, now=None):
    """Bridge boundary, after kernel peer resolution; never a public token API."""
    from control_plane.executive_worker_broker import PeerCredentials

    if type(peer) is not PeerCredentials or peer.uid != CONTROL_UID:
        raise ControlStartRefused("control_peer_required")
    value = payload.get("control_start")
    expires = _validate(value, payload)
    authority = ControlStartAuthority(
        payload_sha256=_sha(_material(payload)), pin_identity_sha256=value["pin_identity_sha256"],
        attempt_id=value["attempt_id"], fence_generation=value["fence_generation"],
        pin_version=value["pin_version"], expires_at=expires, _peer_verified=_PEER_VERIFIED)
    authority.require(payload, now=now)
    return authority
