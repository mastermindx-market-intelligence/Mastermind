"""Existing Desktop parent enrollment, separate from provider session launch.

The private host owner must supply BOTH a qualified live peer and a context
manager that holds its actual current writer through the Runtime commit. A
thread/read response, hook payload, UUID, or caller-created dataclass is not
that authority. There is intentionally no default host factory or RPC endpoint.
The installed Desktop currently exposes no qualified writer-fence provider.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from uuid import UUID, uuid4
import weakref

from control_plane.executive_peer_identity import (
    PeerIdentityError, require_installed_service_peer,
)
from control_plane.operator_harness_contract import (
    ProcessIdentityObservation, ProcessGenerationRef, SessionEpochRef,
    OperationReceiptKind,
)

ENROLLMENT_KIND = "enroll_existing_desktop_parent"
ENROLLMENT_SCHEMA = "mastermind.desktop_parent_enrollment/v1"


@dataclass(frozen=True, slots=True)
class DesktopParentObservation:
    """Owner observation only; constructing this record confers no authority."""

    root_thread_id: str
    thread_id: str
    turn_id: str
    thread_status: str
    turn_status: str
    parent_thread_id: str | None
    forked_from_id: str | None
    can_accept_direct_input: bool | None
    process: ProcessIdentityObservation
    root_job_id: str
    attempt_id: str
    worker_id: str
    requested_profile_digest: str
    authority_policy_hash: str
    effective_grant_digest: str
    placement_snapshot_digest: str


class _DesktopParentOwner:
    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise TypeError("Desktop parent owner requires trusted host composition")


@dataclass(frozen=True, slots=True)
class _Owner:
    peer: object
    installed_binding: object
    writer_fence: object
    observe: object
    receiver_pid: int


_OWNERS = weakref.WeakKeyDictionary()


def _bind_desktop_parent_owner(*, peer, installed_binding, writer_fence, observe):
    """Private composition inside the trusted host service; not an RPC factory.

    The service owner supplies its own observation and writer-lock callbacks,
    never callbacks or identity assertions deserialized from a client. A lock
    supplied by a test proves transaction mechanics, not Desktop capability.
    This module does not install, trust, or manufacture a host implementation.
    """
    require_installed_service_peer(peer, installed_binding)
    if not callable(writer_fence) or not callable(observe):
        raise TypeError("a real host writer fence and observer are required")
    owner = object.__new__(_DesktopParentOwner)
    _OWNERS[owner] = _Owner(peer, installed_binding, writer_fence, observe, os.getpid())
    return owner


def _observation_value(value):
    from control_plane.executive_runtime import StateConflict, _ohf_jsonable
    if type(value) is not DesktopParentObservation:
        raise StateConflict("typed host observation required")
    # Detach all mutable/nested input, including reflectively altered records.
    try:
        encoded = json.dumps(_ohf_jsonable(value), sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        return json.loads(encoded), hashlib.sha256(encoded.encode()).hexdigest()
    except (TypeError, ValueError):
        raise StateConflict("invalid host observation") from None


@contextmanager
def _hold_owner(owner):
    from control_plane.executive_runtime import StateConflict
    if type(owner) is not _DesktopParentOwner or owner not in _OWNERS:
        raise StateConflict("trusted Desktop host owner unavailable")
    state = _OWNERS[owner]
    if state.receiver_pid != os.getpid():
        raise StateConflict("Desktop enrollment receiver changed")
    try:
        def peer_signature():
            peer = require_installed_service_peer(state.peer, state.installed_binding)
            return tuple(getattr(peer, field) for field in (
                "real_boot_id", "audit_identity_digest", "service_label",
                "installed_release", "config_digest", "connection_instance"))

        first_peer = peer_signature()
        with state.writer_fence():
            first, digest = _observation_value(state.observe())
            if first["process"]["boot_id"] != first_peer[0]:
                raise StateConflict("Desktop parent is not on the qualified host boot")

            def revalidate():
                current_peer = peer_signature()
                current, current_digest = _observation_value(state.observe())
                if current_peer != first_peer or current != first or current_digest != digest:
                    raise StateConflict("Desktop current writer changed")

            revalidate()
            yield first, digest, revalidate
    except PeerIdentityError as exc:
        raise StateConflict("Desktop host authentication unavailable") from exc


def enroll_existing_parent(registry, *, attempt_id, fence_generation, lease_token,
                           operation_id, expected_root_thread_id, expected_turn_id, owner):
    """Bind an already-running original parent without creating a Job or launch.

    A canonical Attempt/profile must already have been admitted by its owner.
    Enrollment supplies identity, never policy, placement or a new root grant.
    Attestation and downstream work admission remain their separate canonical
    checks. This operation is deduplicated in the existing Runtime event log.
    """
    from control_plane.executive_runtime import (
        AttemptStatus, OperatorHarnessRegistry, StateConflict, _json_loads,
        _finite_existing_effect, _finite_charged_reservation, _ohf_process,
    )
    if type(registry) is not OperatorHarnessRegistry:
        raise StateConflict("canonical Runtime enrollment owner required")
    try:
        root_uuid = UUID(expected_root_thread_id)
        if str(root_uuid) != expected_root_thread_id or root_uuid.int == 0:
            raise ValueError
        if type(expected_turn_id) is not str or not expected_turn_id or len(expected_turn_id) > 160:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise StateConflict("exact original Desktop thread and turn required") from None
    with _hold_owner(owner) as (observed, observation_digest, revalidate):
        if (observed["root_thread_id"] != expected_root_thread_id
                or observed["thread_id"] != expected_root_thread_id
                or observed["turn_id"] != expected_turn_id
                or observed["thread_status"] != "active"
                or observed["turn_status"] != "inProgress"
                or observed["can_accept_direct_input"] is not True
                or observed["parent_thread_id"] is not None
                or observed["forked_from_id"] is not None):
            raise StateConflict("original active Desktop parent is not established")
        process = ProcessIdentityObservation(**observed["process"])
        if (type(process.pid) is not int or type(process.pgid) is not int
                or type(process.process_start_identity) is not str
                or type(process.boot_id) is not str):
            raise StateConflict("exact Desktop process instance required")
        pid, pgid, start, boot = _ohf_process(process)
        with registry.store.transaction() as connection:
            now = registry.store.now_ms()
            row = registry._leased(connection, attempt_id=attempt_id,
                fence_generation=fence_generation, lease_token=lease_token,
                timestamp=now, statuses={AttemptStatus.CLAIMED, AttemptStatus.RUNNING},
                allow_existing_parent=True)
            job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            if (job is None or observed["root_job_id"] != job["root_job_id"]
                    or observed["attempt_id"] != row["attempt_id"]
                    or observed["worker_id"] != row["worker_id"]
                    or observed["requested_profile_digest"] != row["requested_execution_profile_digest"]
                    or observed["authority_policy_hash"] != row["authority_policy_hash"]):
                raise StateConflict("Desktop inherited grant differs from canonical Attempt")
            _inherited_grant(row, observed)
            seal = connection.execute("""SELECT payload_json FROM events
                WHERE aggregate_type='attempt' AND aggregate_id=?
                  AND event_type='OHF_PROFILE_SEALED' AND attempt_id=? AND worker_id=?
                ORDER BY event_id DESC LIMIT 1""",
                (attempt_id, attempt_id, row["worker_id"])).fetchone()
            if seal is None or _json_loads(seal["payload_json"], fallback={}) != {
                    "profile_digest": row["requested_execution_profile_digest"]}:
                raise StateConflict("committed canonical profile seal required")
            intent = registry._event(connection, operation_id.command_id)
            if intent is not None:
                payload = _json_loads(intent["payload_json"], fallback={})
                if (intent["aggregate_type"] != "operator_operation"
                        or intent["event_type"] != OperationReceiptKind.INTENT.value
                        or intent["attempt_id"] != attempt_id
                        or payload.get("operation_kind") != ENROLLMENT_KIND
                        or payload.get("observation_digest") != observation_digest):
                    raise StateConflict("Desktop enrollment operation differs")
                from control_plane.operator_harness_contract import operation_receipt_command_id
                applied = registry._event(connection, operation_receipt_command_id(
                    operation_id, OperationReceiptKind.APPLIED))
                uncertain = registry._event(connection, operation_receipt_command_id(
                    operation_id, OperationReceiptKind.EFFECT_UNKNOWN))
                if applied is None or uncertain is not None:
                    raise StateConflict("Desktop enrollment has unresolved operation evidence")
                current = connection.execute("""SELECT e.*,g.process_generation_id,
                       g.executive_writer_held,g.pid,g.pgid,g.process_start_identity,g.boot_id
                    FROM harness_session_epochs e JOIN process_generations g
                      ON g.session_epoch_id=e.session_epoch_id
                    WHERE e.attempt_id=? AND e.session_epoch_id=? AND g.process_generation_id=?
                      AND g.ended_at_ms IS NULL AND g.provider_writer_state='HELD'
                      AND g.generation_number=1 AND e.epoch_number=1""",
                    (attempt_id, payload.get("session_epoch_id"), payload.get("process_generation_id"))).fetchone()
                if (current is None or current["state"] != "CURRENT"
                        or current["executive_writer_held"] != 1
                        or current["provider_session_id"] != expected_root_thread_id
                        or (current["pid"], current["pgid"], current["process_start_identity"], current["boot_id"])
                        != (pid, pgid, start, boot)):
                    raise StateConflict("Desktop enrollment writer is no longer current")
                eid, gid = current["session_epoch_id"], current["process_generation_id"]
                validated_enrollment_receipts(connection, row, gid)
            else:
                if row["status"] != AttemptStatus.CLAIMED.value:
                    raise StateConflict("initial Desktop enrollment requires CLAIMED Attempt")
                if connection.execute("""SELECT 1 FROM harness_session_epochs
                      WHERE attempt_id=? OR provider_session_id=?""",
                      (attempt_id, expected_root_thread_id)).fetchone():
                    raise StateConflict("Desktop parent or Attempt already has enrollment history")
                now = _finite_charged_reservation(registry.store, connection, row, stage="start_reserve")
                if now >= int(row["lease_expires_at_ms"]):
                    raise StateConflict("Desktop enrollment lease expired")
                _finite_existing_effect(registry.store, connection, str(row["job_id"]))
                eid, gid = "ohf-desktop-epoch-" + uuid4().hex, "ohf-generation-" + uuid4().hex
                connection.execute("""INSERT INTO harness_session_epochs
                    (session_epoch_id,attempt_id,worker_id,epoch_number,provider_session_id,state,created_at_ms)
                    VALUES(?,?,?,1,?,'CURRENT',?)""",
                    (eid, attempt_id, row["worker_id"], expected_root_thread_id, now))
                connection.execute("""INSERT INTO process_generations
                    (process_generation_id,session_epoch_id,worker_id,provider_session_id,
                     generation_number,pid,pgid,process_start_identity,boot_id,started_at_ms,
                     last_observed_at_ms,executive_writer_held,provider_writer_state,created_at_ms)
                    VALUES(?,?,?,?,1,?,?,?,?,?,?,1,'HELD',?)""",
                    (gid,eid,row["worker_id"],expected_root_thread_id,pid,pgid,start,boot,now,now,now))
                payload = {"schema_version": ENROLLMENT_SCHEMA, "operation_kind": ENROLLMENT_KIND,
                    "attempt_id": attempt_id, "session_epoch_id": eid, "process_generation_id": gid,
                    "worker_id": row["worker_id"], "provider_session_id": expected_root_thread_id,
                    "turn_id": expected_turn_id, "observation": observed,
                    "observation_digest": observation_digest}
                registry._receipt(connection, op=operation_id, kind=OperationReceiptKind.INTENT,
                                  row=row, payload=payload)
                registry._receipt(connection, op=operation_id, kind=OperationReceiptKind.APPLIED,
                    row=row, payload={"operation_kind": ENROLLMENT_KIND,
                        "provider_session_id": expected_root_thread_id, "process_generation_id": gid,
                        "observation_digest": observation_digest})
                connection.execute("""UPDATE attempts SET status='RUNNING',updated_at_ms=?,
                    version=version+1 WHERE attempt_id=?""", (now,attempt_id))
            revalidate()  # The real host fence remains held through SQLite COMMIT.
            # Host qualification may consume the remaining lease time. Recheck
            # the canonical fence/token at the final transaction boundary.
            registry._leased(connection, attempt_id=attempt_id,
                fence_generation=fence_generation, lease_token=lease_token,
                timestamp=registry.store.now_ms(), statuses={AttemptStatus.RUNNING},
                allow_existing_parent=True)
        return SessionEpochRef(eid,attempt_id,str(row["worker_id"]),1), ProcessGenerationRef(gid,eid,1,str(row["worker_id"]))



def has_existing_parent(connection, attempt_id):
    """Canonical epoch identity also preserves refusal if a receipt is damaged."""
    return connection.execute("""SELECT 1 FROM harness_session_epochs
        WHERE attempt_id=? AND session_epoch_id LIKE 'ohf-desktop-epoch-%'""",
        (attempt_id,)).fetchone() is not None


def _inherited_grant(row, observed):
    from control_plane.executive_runtime import (
        StateConflict, PersistenceError, _load_canonical_digest_pair,
    )
    try:
        grant = _load_canonical_digest_pair(row["effective_grant_json"],
            row["effective_grant_digest"], name="Desktop inherited grant")
        placement = _load_canonical_digest_pair(row["placement_snapshot_json"],
            row["placement_snapshot_digest"], name="Desktop placement")
    except PersistenceError as exc:
        raise StateConflict("Desktop inherited authority is not sealed") from exc
    if (not isinstance(grant, dict) or grant.get("job_id") != row["job_id"]
            or grant.get("policy_sha") != row["authority_policy_hash"]
            or not isinstance(placement, dict) or placement.get("worker_id") != row["worker_id"]
            or placement.get("quota_class") != row["quota_class"]
            or observed.get("effective_grant_digest") != row["effective_grant_digest"]
            or observed.get("placement_snapshot_digest") != row["placement_snapshot_digest"]):
        raise StateConflict("Desktop inherited authority differs from canonical grant")


def validated_enrollment_receipts(connection, row, generation_id):
    """Read the exact enrollment pair, never reinterpret it as START_SESSION.

    This is a durable-evidence validator, not a fresh host observation. Canonical
    binding/attestation readers retain their own current-lease and principal checks.
    """
    from control_plane.executive_runtime import StateConflict, _strict_canonical_json_loads
    from control_plane.operator_harness_contract import OperationId, operation_receipt_command_id
    def reject():
        raise StateConflict("Desktop enrollment durable evidence drifted")
    epoch = connection.execute("""SELECT g.*,e.attempt_id,e.worker_id AS epoch_worker,e.provider_session_id AS epoch_session,e.epoch_number
        FROM process_generations g JOIN harness_session_epochs e
        ON e.session_epoch_id=g.session_epoch_id WHERE g.process_generation_id=?""",
        (generation_id,)).fetchone()
    if (epoch is None or epoch["attempt_id"] != row["attempt_id"]
            or epoch["worker_id"] != row["worker_id"] or epoch["epoch_worker"] != row["worker_id"]
            or epoch["generation_number"] != 1 or epoch["epoch_number"] != 1
            or not epoch["session_epoch_id"].startswith("ohf-desktop-epoch-")
            or epoch["provider_session_id"] != epoch["epoch_session"]):
        reject()
    events = connection.execute("""SELECT * FROM events
        WHERE aggregate_type='operator_operation' AND attempt_id=?
          AND json_extract(payload_json,'$.process_generation_id')=? ORDER BY event_id""",
        (row["attempt_id"],generation_id)).fetchall()
    if len(events) != 2:
        reject()
    intent, applied = events
    op = OperationId(intent["aggregate_id"])
    job = connection.execute("SELECT root_job_id FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
    try:
        payload = _strict_canonical_json_loads(str(intent["payload_json"]), name="Desktop INTENT")
        result = _strict_canonical_json_loads(str(applied["payload_json"]), name="Desktop APPLIED")
        observed = payload["observation"]
        process = observed["process"]
        detached, digest = _observation_value(DesktopParentObservation(**{
            **observed, "process": ProcessIdentityObservation(**process)}))
        _inherited_grant(row, observed)
        root = str(UUID(observed["thread_id"]))
    except (KeyError, ValueError, TypeError):
        reject()
    expected = {"schema_version": ENROLLMENT_SCHEMA, "operation_kind": ENROLLMENT_KIND,
        "attempt_id": row["attempt_id"], "session_epoch_id": epoch["session_epoch_id"],
        "process_generation_id": generation_id, "worker_id": row["worker_id"],
        "provider_session_id": epoch["epoch_session"], "turn_id": observed["turn_id"],
        "observation": detached, "observation_digest": digest}
    expected_applied = {"operation_kind": ENROLLMENT_KIND,
        "provider_session_id": epoch["epoch_session"], "process_generation_id": generation_id,
        "observation_digest": digest}
    if (payload != expected or result != expected_applied or root != observed["thread_id"]
            or UUID(root).int == 0 or root != observed["root_thread_id"] or root != epoch["epoch_session"]
            or job is None or observed["root_job_id"] != job["root_job_id"]
            or observed["attempt_id"] != row["attempt_id"] or observed["worker_id"] != row["worker_id"]
            or observed["requested_profile_digest"] != row["requested_execution_profile_digest"]
            or observed["authority_policy_hash"] != row["authority_policy_hash"]
            or observed["thread_status"] != "active" or observed["turn_status"] != "inProgress"
            or observed["can_accept_direct_input"] is not True
            or observed["parent_thread_id"] is not None or observed["forked_from_id"] is not None
            or not isinstance(observed["turn_id"], str) or not observed["turn_id"]
            or type(process["pid"]) is not int or type(process["pgid"]) is not int
            or process["pid"] <= 0 or process["pgid"] <= 0
            or any(process[key] != epoch[key] for key in ("pid","pgid","process_start_identity","boot_id"))):
        reject()
    for event, kind in ((intent, OperationReceiptKind.INTENT), (applied, OperationReceiptKind.APPLIED)):
        if (event["aggregate_type"] != "operator_operation" or event["aggregate_id"] != op.command_id
                or event["event_type"] != kind.value or event["actor"] != "supervisor"
                or any(event[key] != row[key] for key in ("job_id","attempt_id","worker_id","quota_class"))
                or event["command_id"] != (op.command_id if kind is OperationReceiptKind.INTENT else
                    operation_receipt_command_id(op, kind))):
            reject()
    if connection.execute("SELECT 1 FROM events WHERE aggregate_id=? AND event_type=?",
        (op.command_id, OperationReceiptKind.EFFECT_UNKNOWN.value)).fetchone():
        reject()
    return intent, applied, expected, expected_applied
