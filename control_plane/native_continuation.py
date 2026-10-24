"""Immutable native CONTINUE evidence over canonical Runtime and dialogue contracts.

No transport, callback, registry or lifecycle is owned here.
"""
from __future__ import annotations
import hashlib
import json
import re
from typing import Any, Protocol, runtime_checkable
from common.agent_dialogue_contract_v2 import normalize_context_v2
from control_plane.operator_harness_contract import runtime_binding_id_for
from control_plane.executive_current_target import read_current_target
from control_plane.wake_ledger import NativeContinuationAckEvidence, LedgerPhase


@runtime_checkable
class NativeContinuationSource(Protocol):
    """Trusted installed composition port; Runtime retains every authority fence.

    The integration owner constructs the concrete source. Core callers receive
    no SDK, transport constructor, or caller-authored binding through this port.
    """
    runtime: Any

    async def read_continuation_source(self, *, read_ref: str) -> dict: ...

    def resolve(self, *, native_session_id: str, operation_key: str,
                in_reply_to: str) -> Any: ...

    def require_native_ack(self, binding: Any, *, workspace_id: str,
                           channel_id: str) -> Any: ...

    async def require_committed_native_reply(self, *, read_ref: str) -> Any: ...


_SCHEMA = "mastermind.session_bridge.continue_request.v1"


_EVENT = "SESSION_BRIDGE_CONTINUE_REQUESTED"


_ACTOR = "executive-session-bridge"


_PREFIX = "session-bridge-continue:"


_READ = re.compile(r"^session-reply-([0-9a-f]{64})$")


_IDENTITY = ("policy_id", "issuer_digest", "resource", "subject_digest", "client_ref")


_PAYLOAD = frozenset({"schema", "principal", "target_ref", "target_generation", "operation_key",
    "binding_sha256", "root_job_id", "root_event_id", "root_event_sha256", "job_id", "attempt_id",
    "worker_id", "generation", "context", "thread_ts", "predecessor_message_key",
    "request_message_key", "input_sha256", "read_ref", "epoch", "carrier"})


_EPOCH = ("root_job_id", "job_id", "session_ref", "attempt_id", "worker_id", "fence_generation",
          "harness_session_epoch_id", "harness_generation_number", "harness_provider_session_id",
          "harness_provider", "harness_account_label", "harness_owner_seat")


def _epoch(target):
    value = {key:getattr(target,key) for key in _EPOCH}
    value["harness_provider_session_id"] = hashlib.sha256(value["harness_provider_session_id"].encode()).hexdigest()
    return value


_GENERATION = frozenset({"session_epoch_id", "process_generation_id", "binding_id",
    "binding_generation", "native_session_sha256"})


_SHA = re.compile(r"^[0-9a-f]{64}$")


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def _request_key(operation_key):
    return _digest({"schema": _SCHEMA, "operation_key": operation_key})


def _validate_payload(value):
    if type(value) is not dict or set(value) != _PAYLOAD or value["schema"] != _SCHEMA:
        raise ValueError("request schema changed")
    if (type(value["principal"]) is not dict or set(value["principal"]) != set(_IDENTITY)
            or any(type(v) is not str or not v or len(v) > 2048 for v in value["principal"].values())
            or type(value["root_event_id"]) is not int or value["root_event_id"] < 1
            or type(value["generation"]) is not dict or set(value["generation"]) != _GENERATION
            or type(value["generation"]["binding_generation"]) is not int
            or value["generation"]["binding_generation"] < 1):
        raise ValueError("request identity malformed")
    for field in ("binding_sha256", "root_event_sha256", "input_sha256"):
        if not isinstance(value[field], str) or _SHA.fullmatch(value[field]) is None:
            raise ValueError("request digest malformed")
    for field in ("target_ref", "target_generation", "operation_key", "root_job_id", "job_id",
                  "attempt_id", "worker_id", "predecessor_message_key", "request_message_key", "read_ref"):
        if not isinstance(value[field], str) or _TOKEN.fullmatch(value[field]) is None:
            raise ValueError("request reference malformed")
    if (not isinstance(value["thread_ts"], str)
            or re.fullmatch(r"[0-9]{10}\.[0-9]{6}", value["thread_ts"]) is None):
        raise ValueError("request thread malformed")
    for field in ("session_epoch_id", "process_generation_id", "binding_id"):
        item = value["generation"][field]
        if not isinstance(item, str) or _TOKEN.fullmatch(item) is None:
            raise ValueError("request generation malformed")
    native = value["generation"]["native_session_sha256"]
    if not isinstance(native, str) or _SHA.fullmatch(native) is None:
        raise ValueError("native generation malformed")
    if (type(value["epoch"]) is not dict or set(value["epoch"]) != set(_EPOCH)
            or type(value["carrier"]) is not dict
            or set(value["carrier"]) != {"workspace_id", "channel_id", "thread_ts"}
            or value["carrier"]["thread_ts"] != value["thread_ts"]
            or any(type(v) is not str or not v for v in value["carrier"].values())):
        raise ValueError("original physical source malformed")
    if type(value["context"]) is not dict or normalize_context_v2(**value["context"]) != value["context"]:
        raise ValueError("request context malformed")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _continue_key(operation_key: str) -> str:
    digest = hashlib.sha256(
        ("mastermind.session_bridge.continue.v1\n" + operation_key).encode()
    ).hexdigest()[:40]
    return "asd-dot-continue-" + digest


def _generation(facts) -> dict:
    return {
        "session_epoch_id": facts.session_epoch_id,
        "process_generation_id": facts.process_generation_id,
        "binding_id": runtime_binding_id_for(facts.attempt_id, facts.session_epoch_id),
        "binding_generation": facts.generation_number,
        "native_session_sha256": hashlib.sha256(facts.provider_session_id.encode()).hexdigest(),
    }


def stored_continuation_request(runtime, read_ref: str):
    match = _READ.fullmatch(read_ref) if isinstance(read_ref, str) else None
    if match is None:
        raise ValueError("invalid read reference")
    event = runtime.events.get_event_by_command_id(_PREFIX + match[1])
    if (event is None or event.event_type != _EVENT or event.actor != _ACTOR
            or event.aggregate_type != "session_bridge_continue"
            or event.aggregate_id != match[1]):
        raise ValueError("request unavailable")
    value = event.payload
    _validate_payload(value)
    if (value.get("schema") != _SCHEMA or value.get("read_ref") != read_ref
            or _request_key(value["operation_key"]) != match[1]
            or value["request_message_key"] != _continue_key(value["operation_key"])
            or (event.job_id, event.attempt_id, event.worker_id) != (
                value["job_id"], value["attempt_id"], value["worker_id"])):
        raise ValueError("request binding changed")
    try:
        root = runtime.store.unique_root_created_event(value["root_job_id"])
    except ValueError:
        raise ValueError("original root changed") from None
    if (root.event_id != value["root_event_id"]
            or _digest(root.to_dict()) != value["root_event_sha256"]):
        raise ValueError("original root changed")
    return event, value


def native_continuation_ack_evidence(runtime, requested, delivered, trusted, *, connection):
    obligation, source = requested.obligation, requested.physical_source
    if (source is None or obligation is None or obligation.attempt_id != trusted.target_attempt_id
            or obligation.wake_kind != 'dialogue_turn_pending'
            or obligation.source_kind != 'agent_dialogue_attention'
            or delivered.phase is not LedgerPhase.DELIVERED or delivered.reasoning_surface != 'codex'
            or delivered.wake_transport != 'codex-app-server' or delivered.nudge_id != trusted.nudge_id):
        raise ValueError('not an authenticated native continuation')
    events = runtime.store.list_events(aggregate_type='session_bridge_continue',
        attempt_id=trusted.target_attempt_id, connection=connection)
    if len(events) > 256:
        raise ValueError('continuation evidence exceeds bound')
    matches = [event for event in events if event.event_type == 'SESSION_BRIDGE_CONTINUE_REQUESTED'
               and event.payload.get('request_message_key') == source.predecessor_message_key]
    if len(matches) != 1:
        raise ValueError('exact original CONTINUE unavailable')
    event, value = stored_continuation_request(runtime, matches[0].payload['read_ref'])
    facts = runtime.current_harness_binding_source(trusted.target_attempt_id, connection=connection)
    if (event.to_dict() != matches[0].to_dict() or not value['target_ref'].startswith('codex:')
            or _generation(facts) != value['generation']
            or facts.provider_session_id != trusted.provider_session_id
            or facts.process_generation_id != trusted.process_generation_id
            or value['generation']['binding_id'] != trusted.binding_id
            or value['generation']['binding_generation'] != trusted.binding_generation
            or source.operation_key != value['context']['operation_key']
            or {k:getattr(source,k) for k in ('workspace_id','channel_id','thread_ts')} != value['carrier']
            or (source.candidate.root_job_id,source.candidate.job_id,source.candidate.attempt_id,source.candidate.worker_id)
               != (value['root_job_id'],value['job_id'],value['attempt_id'],value['worker_id'])
            or obligation.job_id != value['job_id'] or obligation.source_workstream != value['context']['work_ref']
            or _epoch(read_current_target(runtime, source.operation_key)) != value['epoch']):
        raise ValueError('native continuation authority changed')
    return NativeContinuationAckEvidence(schema='mastermind.native_continuation_ack.v1',
        request_event_id=event.event_id,request_event_sha256=_digest(event.to_dict()),
        target_attempt_id=trusted.target_attempt_id,process_generation_id=trusted.process_generation_id,
        native_session_sha256=hashlib.sha256(trusted.provider_session_id.encode()).hexdigest(),
        native_turn_sha256=hashlib.sha256(trusted.provider_native_turn_id.encode()).hexdigest(),
        nudge_id=trusted.nudge_id)
