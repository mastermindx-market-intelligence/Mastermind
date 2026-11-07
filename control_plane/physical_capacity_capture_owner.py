"""Private capture custody between the existing sealed composer and Event writer.

This does not collect or admit anything. Only the same issued physical caller,
after its successful evaluator, can bind an optional original Event capture.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import weakref

_MINT = object()
_ISSUED = weakref.WeakSet()


@dataclasses.dataclass(frozen=True, eq=False)
class _CapacityCapture:
    store: object
    caller: object
    command_id: str
    action: str
    request_fingerprint: str
    decision_time_ms: int
    payload_json: str
    _seal: object = dataclasses.field(repr=False)


def _refuse():
    from control_plane.executive_physical_resources import PhysicalResourceRefusal
    raise PhysicalResourceRefusal("CAPACITY_CAPTURE_BINDING_INVALID", "original capacity capture custody is invalid")


def mint_capacity_capture(broker, caller, reservation, evaluation, *, connection, timestamp):
    from control_plane import executive_physical_admission as admission
    # Legacy/test callers and observations without this evidence retain the
    # original admission/persistence behavior; no synthetic capture is created.
    if type(caller) is not admission.PhysicalCallerContext:
        return None
    context = admission.admit(broker, reservation, caller, connection=connection, stage="capture")
    evidence = context["observations"].get("host_capacity_evidence")
    if evidence is None:
        return None
    if (type(evidence) is not dict or set(evidence) != {"snapshot", "snapshot_sha256"}
            or type(evaluation) is not dict or evaluation.get("admitted") is not True
            or evaluation.get("code") not in {"RESERVED", "FRESH_BEGIN"}
            or evaluation.get("request_fingerprint") != caller.fingerprint
            or evaluation.get("host_capacity_snapshot_sha256") != evidence["snapshot_sha256"]):
        _refuse()
    action = {"RESERVED": "reserve", "FRESH_BEGIN": "begin"}[evaluation["code"]]
    expected_command = caller.reserve_command_id if action == "reserve" else caller.begin_command_id
    if reservation["command_id"] != expected_command or evaluation.get("fresh_begin") is not (action == "begin"):
        _refuse()
    policy = context["policy"]
    hosts = [host for host in policy["host_qualifications"] if host["host_id"] == caller.host_ref and host["boot_id"] == caller.boot_ref]
    if len(hosts) != 1 or evaluation.get("host_qualification_revision") != hosts[0]["qualification_revision"]:
        _refuse()
    source = reservation["source_binding"]
    from control_plane.physical_capacity_capture import build_capture_payload
    try:
        payload = build_capture_payload(
            evidence["snapshot"], snapshot_sha256=evidence["snapshot_sha256"],
            decision_time_ms=timestamp, max_age_ms=policy["freshness"]["sample_max_age_ms"],
            expected_binding={
                "host_ref": caller.host_ref, "boot_ref": caller.boot_ref,
                "capacity_pool_ref": hosts[0]["capacity_pool_ref"],
                "operation_key": reservation["operation_key"], "request_fingerprint": caller.fingerprint,
                "source_commit_sha": source["commit_sha"], "source_helper_sha256": source["helper_sha256"],
                "policy_revision": policy["policy_revision"],
                "host_qualification_revision": hosts[0]["qualification_revision"],
                "runtime_identity_sha256": hashlib.sha256(admission._canonical(admission.runtime_identity(caller.store, connection)).encode()).hexdigest(),
            },
        )
    except (ValueError, TypeError, KeyError):
        _refuse()
    capture = _CapacityCapture(broker.store, caller, reservation["command_id"], action, caller.fingerprint, timestamp,
                               admission._canonical(payload), _MINT)
    _ISSUED.add(capture)
    return capture


def capture_for_event(capture, *, store, reservation, action, original_event_id, timestamp):
    if (type(capture) is not _CapacityCapture or capture not in _ISSUED or capture._seal is not _MINT
            or capture.store is not store or capture.command_id != reservation["command_id"]
            or type(timestamp) is not int or timestamp != capture.decision_time_ms
            or action != capture.action or action not in {"reserve", "begin"} or original_event_id is not None):
        _refuse()
    from control_plane import executive_physical_admission as admission
    from control_plane.executive_physical_resources import physical_request_fingerprint
    caller = capture.caller
    if (type(caller) is not admission.PhysicalCallerContext or caller not in admission._ISSUED
            or caller._seal is not admission._MINT or caller.store is not store
            or physical_request_fingerprint(reservation) != capture.request_fingerprint
            or caller.fingerprint != capture.request_fingerprint):
        _refuse()
    return json.loads(capture.payload_json)
