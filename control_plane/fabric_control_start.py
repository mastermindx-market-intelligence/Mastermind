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


def command_from_validated_pin(attempt, payload, *, runtime=None, foreground_receipt=None):
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
    if foreground_receipt is not None:
        from control_plane.foreground_operation import require_start
        from control_plane.executive_fabric_bridge_broker import start_request_sha256
        from control_plane.remote_attempt_transport import _read_claim, RemoteTransportPurpose

        require_start(foreground_receipt, payload["binding"],
                      payload["physical_binding_sha256"], start_request_sha256(payload))
        job, current, quota, join = _read_claim(runtime,
            job_id=attempt.job_id, attempt_id=attempt.attempt_id,
            purpose=RemoteTransportPurpose.LAUNCH)
        if (current != attempt or job.root_job_id != payload["binding"]["root_id"]
                or quota.fence_generation != attempt.fence_generation):
            raise ControlStartRefused("foreground_capacity_moved")
        value["owner_projection"] = {
            "attendance": foreground_receipt.as_dict(),
            "capacity": {"registered_join": join.to_dict(),
                "active_job_id": quota.active_job_id,
                "active_attempt_id": quota.active_attempt_id,
                "fence_generation": quota.fence_generation,
                "status": quota.status.value},
        }
        # Preserve the Runtime lease fact; foreground lifetime is a separate
        # actual-principal bound on this command, never a lease extension.
        value["foreground_expires_at"] = foreground_receipt.principal_deadline()
        # A real scope may close or move during the independent Capacity read.
        require_start(foreground_receipt, payload["binding"],
                      payload["physical_binding_sha256"], start_request_sha256(payload))
    _validate(value, payload)
    return value


def _validate(value, payload):
    if (type(value) is not dict or set(value) not in (_FIELDS, _FIELDS | {"owner_projection", "foreground_expires_at"})
            or value["schema_version"] != SCHEMA
            or value["attempt_id"] != payload["binding"]["attempt_id"]
            or value["pin_identity_sha256"] != launch_identity(payload)
            or any(type(value[k]) is not int or not 1 <= value[k] <= 2**63 - 1
                   for k in ("fence_generation", "pin_version"))):
        raise ControlStartRefused("control_start_projection_mismatch")
    if "owner_projection" in value:
        _validate_owner_projection(value["owner_projection"], payload, value["fence_generation"])
        deadline = value["foreground_expires_at"]
        if type(deadline) is not int or not 0 < deadline <= 2**53:
            raise ControlStartRefused("control_foreground_expiry_invalid")
        return min(_expiry(value["lease_expires_at"]), deadline)
    return _expiry(value["lease_expires_at"])


def _validate_owner_projection(projection, payload, fence):
    """Validate inert evidence arriving from the authenticated Control peer.

    This is not a public attendance issuer or independent Capacity grant.
    The producer above reads their actual owners in the live invocation.
    """
    from control_plane.executive_capacity_join import RegisteredCapacityJoin, validate_capacity_join
    from control_plane.executive_fabric_bridge_broker import start_request_sha256
    try:
        if type(projection) is not dict or set(projection) != {"attendance", "capacity"}:
            raise ValueError()
        attendance, capacity = projection["attendance"], projection["capacity"]
        if (type(attendance) is not dict or set(attendance) != set(payload["binding"]) | {
                "physical_binding_sha256", "start_request_sha256", "principal_identity",
                "operation_key", "arguments_sha256"}
                or any(attendance[k] != v for k, v in payload["binding"].items())
                or attendance["physical_binding_sha256"] != payload["physical_binding_sha256"]
                or attendance["start_request_sha256"] != start_request_sha256(payload)
                or type(attendance["principal_identity"]) not in (tuple, list)
                or len(attendance["principal_identity"]) != 5
                or any(type(v) is not str or not v for v in attendance["principal_identity"])
                or type(attendance["operation_key"]) is not str or not attendance["operation_key"]
                or type(attendance["arguments_sha256"]) is not str
                or len(attendance["arguments_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in attendance["arguments_sha256"])):
            raise ValueError()
        if (type(capacity) is not dict or set(capacity) != {"registered_join", "active_job_id",
                "active_attempt_id", "fence_generation", "status"}
                or capacity["active_job_id"] != payload["binding"]["job_id"]
                or capacity["active_attempt_id"] != payload["binding"]["attempt_id"]
                or type(capacity["fence_generation"]) is not int
                or capacity["fence_generation"] != fence or capacity["status"] != "BUSY"):
            raise ValueError()
        raw = capacity["registered_join"]
        if type(raw) is not dict or set(raw) != {"worker_id", "quota_class", "provider", "capacity_join"}:
            raise ValueError()
        join = RegisteredCapacityJoin(raw["worker_id"], raw["quota_class"], raw["provider"],
                                      validate_capacity_join(raw["capacity_join"]))
        if join.worker_id != payload["launch_spec"]["worker_id"]:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ControlStartRefused("control_owner_projection_mismatch") from None


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
    _owner_projection: bytes | None = dataclasses.field(default=None, repr=False, compare=False)

    def require(self, payload: Mapping[str, Any], *, now=None):
        observed = time.time() if now is None else now
        if (self._peer_verified is not _PEER_VERIFIED
                or type(observed) not in (int, float) or not math.isfinite(observed)
                or observed >= self.expires_at
                or self.payload_sha256 != _sha(_material(payload))
                or self.pin_identity_sha256 != launch_identity(payload)
                or self.attempt_id != payload["binding"]["attempt_id"]):
            raise ControlStartRefused("control_start_authority_unavailable")

    def owner_projection(self, payload):
        self.require(payload)
        if self._owner_projection is None:
            raise ControlStartRefused("foreground_owner_projection_required")
        projection = json.loads(self._owner_projection)
        _validate_owner_projection(projection, payload, self.fence_generation)
        return projection


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
        pin_version=value["pin_version"], expires_at=expires, _peer_verified=_PEER_VERIFIED,
        _owner_projection=(json.dumps(value["owner_projection"], sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode() if "owner_projection" in value else None))
    authority.require(payload, now=now)
    return authority
