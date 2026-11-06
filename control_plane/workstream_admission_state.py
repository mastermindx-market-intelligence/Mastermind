"""Pause/resume event-chain composition in the existing Runtime Job owner.

All persistence and locking belong to RuntimeStore. These functions introduce
no store/controller, invoke no Job lifecycle, and expose no public action port.
"""
from __future__ import annotations

from control_plane.executive_runtime import StateConflict, PersistenceError, _workstream_suspension_receipt
from control_plane.workstream_admission_contract import canonical_work_ref, _token

_EVENT_FIELDS = ("event_id", "aggregate_type", "aggregate_id", "event_type", "command_id", "actor", "payload_json", "created_at_ms")


def _resume_receipt(connection, row):
    from control_plane.workstream_resumption_contract import parse_resumption_event
    previous = connection.execute("SELECT * FROM events WHERE aggregate_type='workstream' AND aggregate_id=? AND sequence<? ORDER BY sequence DESC LIMIT 1",
        (row["aggregate_id"], row["sequence"])).fetchone()
    if (previous is None or row["sequence"] != previous["sequence"] + 1
            or previous["event_type"] != "WORKSTREAM_ADMISSION_SUSPENDED"):
        raise StateConflict("WORKSTREAM_RESUMPTION_SOURCE_INVALID")
    try:
        pause = _workstream_suspension_receipt(previous)
        return parse_resumption_event({key:row[key] for key in _EVENT_FIELDS}, pause)
    except (ValueError, KeyError, TypeError):
        raise StateConflict("WORKSTREAM_RESUMPTION_SOURCE_INVALID") from None


def current_transition(connection, work_ref):
    row = connection.execute("SELECT * FROM events WHERE aggregate_type='workstream' AND aggregate_id=? ORDER BY sequence DESC LIMIT 1", (work_ref,)).fetchone()
    if row is None:
        return None
    if row["event_type"] == "WORKSTREAM_ADMISSION_SUSPENDED":
        return _workstream_suspension_receipt(row)
    if row["event_type"] == "WORKSTREAM_ADMISSION_RESUMED":
        return _resume_receipt(connection, row)
    raise StateConflict("WORKSTREAM_SUSPENSION_SOURCE_INVALID")


def _selectors(work_ref, command_id, actor):
    try:
        return canonical_work_ref(work_ref), _token(command_id), _token(actor)
    except ValueError:
        raise StateConflict("WORKSTREAM_RESUMPTION_INVALID") from None


def _original(connection, work_ref, command_id, actor, expected_digest=None):
    row = connection.execute("SELECT * FROM events WHERE command_id=?", (command_id,)).fetchone()
    if row is None:
        return None
    if (row["event_type"] != "WORKSTREAM_ADMISSION_RESUMED" or row["aggregate_type"] != "workstream"
            or row["aggregate_id"] != work_ref or row["actor"] != actor):
        raise StateConflict("WORKSTREAM_RESUMPTION_COMMAND_MISMATCH")
    receipt = _resume_receipt(connection, row)
    if expected_digest is not None and receipt["request_digest"] != expected_digest:
        raise StateConflict("WORKSTREAM_RESUMPTION_COMMAND_MISMATCH")
    return receipt


def read_resume_command(registry, work_ref, *, command_id, actor):
    """Exact original-command observation; None is not proof of no effect."""
    selected, command, who = _selectors(work_ref, command_id, actor)
    with registry.store.read() as connection:
        return _original(connection, selected, command, who)


def resume_in_owner(registry, work_ref, *, command_id, actor,
                    expected_pause_event_id, expected_pause_receipt_digest, _commit_guard=None):
    from control_plane.workstream_resumption_contract import make_resume_request, make_resume_payload, request_digest, pause_receipt_digest
    selected, command, who = _selectors(work_ref, command_id, actor)
    if _commit_guard is not None and not callable(_commit_guard):
        raise StateConflict("WORKSTREAM_RESUMPTION_GUARD_INVALID")
    def recheck():
        if _commit_guard is not None:
            _commit_guard()
    try:
        request = make_resume_request(selected, command, who, expected_pause_event_id, expected_pause_receipt_digest)
        expected_digest, payload = request_digest(request), make_resume_payload(request)
    except ValueError:
        raise StateConflict("WORKSTREAM_RESUMPTION_INVALID") from None
    recheck()
    with registry.store.read() as connection:
        existing = _original(connection, selected, command, who, expected_digest)
    if existing is not None:
        recheck()
        return existing
    with registry.store.transaction() as connection:
        registry.store._assert_owned_snapshot_connection(connection)
        recheck()
        receipt = _original(connection, selected, command, who, expected_digest)
        if receipt is None:
            pause = current_transition(connection, selected)
            if pause is None or pause["state"] != "PAUSED":
                raise StateConflict("WORKSTREAM_RESUMPTION_NOT_PAUSED")
            if (pause["event_id"] != expected_pause_event_id
                    or pause_receipt_digest(pause) != expected_pause_receipt_digest):
                raise StateConflict("WORKSTREAM_RESUMPTION_STALE_PAUSE")
            registry.store.append_event(connection, aggregate_type="workstream", aggregate_id=selected,
                event_type="WORKSTREAM_ADMISSION_RESUMED", command_id=command, actor=who, payload=payload)
            row = connection.execute("SELECT * FROM events WHERE command_id=?", (command,)).fetchone()
            if row is None:
                raise PersistenceError("workstream resumption receipt disappeared")
            receipt = _resume_receipt(connection, row)
        recheck()
    return receipt
