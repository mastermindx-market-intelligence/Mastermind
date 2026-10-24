"""Direct result display and the private existing-Event consumption join.

Runtime validates the real Supervisor terminal evidence and current access.
The projector is DATA only. The Event helper is called only by Runtime inside
its existing transaction; it never acquires a store, source, lease or worker.
"""
from __future__ import annotations

import dataclasses
import re

from common import direct_native_result_contract as wire
from control_plane import executive_runtime as runtime_owner

EVENT_TYPE = "DIRECT_NATIVE_RESULT_CONSUMED"
CONSUMPTION_SCHEMA = "mastermind.direct_native_result_consumption.v1"
IDENTITY_KEYS = frozenset({"principal_scope", "receiver_binding_digest", "source_digest", "admission_digest"})
_EVENT_COLUMNS = (
    "command_id,aggregate_type,aggregate_id,event_type,actor,job_id,attempt_id,"
    "CASE WHEN length(CAST(payload_json AS BLOB))<=4096 THEN payload_json ELSE NULL END AS payload_json"
)


class DirectResultProjectionError(ValueError):
    pass


def _refuse():
    raise DirectResultProjectionError("direct-native retained result unavailable")


def _identity(value):
    if type(value) is not dict or set(value) != IDENTITY_KEYS:
        _refuse()
    return {k: wire.hex_digest(value[k]) for k in IDENTITY_KEYS}


def _completion(value):
    if type(value) is not dict or set(value) != {"payload", "terminal_digest", "terminal_record"}:
        _refuse()
    wire.hex_digest(value["terminal_digest"])
    terminal = value["terminal_record"]
    if (type(terminal) is not dict or terminal.get("payload") != value["payload"]
            or wire.digest(terminal) != value["terminal_digest"]):
        _refuse()
    payload = value["payload"]
    if type(payload) is not dict or set(payload) != wire.PAYLOAD_KEYS:
        _refuse()
    # Runtime's deep proof owns content meaning. Malformed source DATA is
    # refused, not reclassified as a harmless display-size omission.
    for name in ("summary", "current_state"):
        if type(payload[name]) is not str:
            _refuse()
    for name in ("completed_steps", "next_actions"):
        if type(payload[name]) is not list or any(type(x) is not str for x in payload[name]):
            _refuse()
    for text in (payload["summary"], payload["current_state"], *payload["completed_steps"], *payload["next_actions"]):
        if any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in text):
            _refuse()
    wire.canonical_bytes(value)
    return value


@dataclasses.dataclass(frozen=True)
class DirectNativeResultProjection:
    complete: dict
    content_over_budget: dict


def project_direct_native_result(snapshot, receipt):
    """Project actual owner-issued material after its observation closes."""
    snapshot_type = getattr(runtime_owner, "BoundedDirectResultSnapshot", None)
    if snapshot_type is None or type(snapshot) is not snapshot_type:
        _refuse()
    if type(receipt) is not runtime_owner.RuntimeReadObservationReceipt:
        _refuse()
    if (receipt.schema != runtime_owner.RUNTIME_READ_OBSERVATION_SCHEMA
            or receipt.state != "SAME" or type(receipt.before) is not int
            or type(receipt.after) is not int or receipt.before < 0
            or receipt.before != receipt.after
            or type(snapshot.read_generation) is not str
            or re.fullmatch(r"[0-9a-f]{32}", snapshot.read_generation) is None
            or receipt.source_identity != snapshot.read_generation):
        _refuse()
    selection = wire.validate_selection(dict(work_ref=snapshot.work_ref,
        job_id=snapshot.job_id, attempt_id=snapshot.attempt_id))
    _identity(snapshot.admission)
    completion = _completion(snapshot.completion)
    if completion["terminal_digest"] != wire.hex_digest(snapshot.terminal_digest):
        _refuse()
    consumption = wire.validate_consumption(snapshot.consumption)
    over = wire.unavailable(selection, "CONTENT_OVER_BUDGET")
    try:
        complete = wire.available(selection, completion["payload"], snapshot.terminal_digest, consumption)
    except wire.DirectResultContractError:
        # Source shape/meaning has already been qualified above. This branch
        # omits content only, and never fabricates an acknowledgment.
        complete = wire.unavailable(selection, "CONTENT_OVER_BUDGET")
    return DirectNativeResultProjection(complete=complete, content_over_budget=over)


def consumption_command_id(operation_key, identity):
    """Stable DATA identity; the Runtime guard authenticates its actual user."""
    return "direct-native-consume:" + wire.digest(dict(
        schema=CONSUMPTION_SCHEMA, operation_key=wire.identifier(operation_key),
        identity=_identity(identity)))


def _same_event(event, payload, selected, command_id):
    return (event is not None and event["command_id"] == command_id
        and event["event_type"] == EVENT_TYPE and event["aggregate_type"] == "job"
        and event["aggregate_id"] == selected["job_id"] and event["job_id"] == selected["job_id"]
        and event["attempt_id"] == selected["attempt_id"] and event["actor"] == "direct-native-parent"
        and _event_payload(event) == payload)


def _event_payload(row):
    if type(row["payload_json"]) is not str:
        _refuse()
    try:
        return runtime_owner._strict_canonical_json_loads(row["payload_json"], name="direct consumption Event")
    except runtime_owner.StateConflict:
        _refuse()


def direct_consumption_state(connection, selection, identity, terminal_digest):
    """Bounded DATA read inside the already-qualified Runtime observation."""
    selected = wire.validate_selection(selection)
    identity = _identity(identity)
    wire.hex_digest(terminal_digest)
    rows = connection.execute(
        "SELECT " + _EVENT_COLUMNS + " "
        "FROM events WHERE event_type=? AND job_id=? AND attempt_id=? ORDER BY event_id LIMIT 2",
        (EVENT_TYPE, selected["job_id"], selected["attempt_id"])).fetchall()
    if not rows:
        return dict(state="UNCONSUMED", receipt_digest=None)
    if len(rows) != 1:
        _refuse()
    row = rows[0]
    try:
        payload = _event_payload(row)
        if (type(payload) is not dict or set(payload) != {
            "schema", "selection", "result_digest", "identity", "operation_key"
        } or payload["schema"] != CONSUMPTION_SCHEMA or payload["selection"] != selected
            or payload["identity"] != identity or payload["result_digest"] != terminal_digest
            or row["command_id"] != consumption_command_id(payload["operation_key"], identity)
            or row["aggregate_type"] != "job" or row["aggregate_id"] != selected["job_id"]
            or row["actor"] != "direct-native-parent"):
            _refuse()
    except (KeyError, ValueError, TypeError):
        _refuse()
    return dict(state="CONSUMED", receipt_digest=wire.digest(payload))


def consume_direct_result_in_transaction(runtime, connection, selection, *, access, command_id):
    """Private Runtime-owned transaction helper. No stand-alone auth entry.

    Same command replay returns the exact original Event payload. Changed
    terminal/source/receiver or conflicting command reuse refuses before any
    append. Source and access are checked again before return/transaction commit.
    A lost HTTP response is reconciled by read, never by relaunching a Job.
    """
    if type(runtime) is not runtime_owner.Runtime or not connection.in_transaction:
        _refuse()
    selected = wire.validate_request(selection, consume=True)
    current_selection = {k: selected[k] for k in wire.SELECTION_KEYS}
    identity = _identity(runtime.require_direct_result_access(connection, current_selection, access))
    if command_id != consumption_command_id(selected["operation_key"], identity):
        _refuse()
    completion = _completion(runtime.validate_direct_completion(connection, current_selection))
    if completion["terminal_digest"] != selected["result_digest"]:
        _refuse()
    payload = dict(schema=CONSUMPTION_SCHEMA, selection=current_selection,
        result_digest=selected["result_digest"], identity=identity,
        operation_key=selected["operation_key"])
    # Reject acknowledgment of content this bounded direct view cannot carry.
    wire.available(current_selection, completion["payload"], selected["result_digest"],
                   dict(state="UNCONSUMED", receipt_digest=None))
    previous = connection.execute("SELECT " + _EVENT_COLUMNS + " FROM events WHERE command_id=?",
                                  (command_id,)).fetchone()
    if previous is not None:
        if not _same_event(previous, payload, current_selection, command_id):
            _refuse()
    else:
        if direct_consumption_state(connection, current_selection, identity,
                                    selected["result_digest"])["state"] != "UNCONSUMED":
            _refuse()  # Do not append a second acknowledgment under another key.
        runtime.store.append_event(connection, aggregate_type="job", aggregate_id=selected["job_id"],
            event_type=EVENT_TYPE, actor="direct-native-parent", job_id=selected["job_id"],
            attempt_id=selected["attempt_id"], payload=payload, command_id=command_id)
    if (_identity(runtime.require_direct_result_access(connection, current_selection, access)) != identity
            or _completion(runtime.validate_direct_completion(connection, current_selection)) != completion):
        _refuse()
    return dict(state="CONSUMED", receipt_digest=wire.digest(payload))
