"""Original-caller provenance and replies on the existing Runtime/Dialogue owners.

One immutable Runtime event binds an authenticated CONTINUE request before its
carrier effect. It is evidence of REQUESTED only. Agent Dialogue remains the
only send/dedup owner; this module creates no endpoint, retry or session store.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE
from control_plane.executive_runtime import Runtime
from control_plane.operator_harness_contract import runtime_binding_id_for
from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import CONTROL_VERSION_V2, call_service
from integrations.workspace_agent_runtime_binding import _read_current_target, _read_dialogue_source
from control_plane.wake_ledger import LedgerPhase, wake_record_from_event
from .dialogue_reply import AgentDialogueContinueWriter
from .native_read import NativeReplyReadBinding
from .native_reply import NativeReplyBinding
from .runtime_owner import RuntimeCodexTargetProjector, RuntimeFabricTargetProjector
from .schemas import BridgeError, validate_tool_arguments

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
    if type(value["context"]) is not dict or DialogueContextV2(**value["context"]).normalized() != value["context"]:
        raise ValueError("request context malformed")



def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _principal(principal: NeutralPrincipalProjection, *, submit: bool = False) -> dict:
    now = time.time()
    scopes = {READ_SCOPE}
    if submit:
        scopes.add(SUBMIT_SCOPE)
    if (type(principal) is not NeutralPrincipalProjection
            or type(principal.issued_at) is not int
            or type(principal.expires_at) is not int
            or not principal.issued_at <= now < principal.expires_at
            or not scopes <= set(principal.scopes)):
        raise BridgeError("reply_unavailable", "authorized canonical reply is unavailable")
    identity = {key: getattr(principal, key) for key in _IDENTITY}
    if any(type(value) is not str or not value for value in identity.values()):
        raise BridgeError("reply_unavailable", "authorized canonical reply is unavailable")
    return identity


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


class RuntimeSessionReturn:
    """Stateless joins over immutable request events and the current writer."""

    def __init__(self, runtime: Runtime, *, fabric: RuntimeFabricTargetProjector,
                 codex: RuntimeCodexTargetProjector, socket_path: Path,
                 service_call=call_service):
        if (type(runtime) is not Runtime or type(fabric) is not RuntimeFabricTargetProjector
                or type(codex) is not RuntimeCodexTargetProjector
                or not Path(socket_path).is_absolute() or not callable(service_call)):
            raise TypeError("existing Runtime and canonical owners are required")
        self.runtime, self.fabric, self.codex = runtime, fabric, codex
        self.socket_path, self.service_call = Path(socket_path), service_call

    def _target(self, target_ref):
        if target_ref.startswith("codex:"):
            native = self.codex.resolve(target_ref)
            return native.fabric, native.reply_binding()
        target = self.fabric.resolve(target_ref)
        return target, target.reply_binding()

    def bind_request(self, principal, arguments) -> str:
        """Record exact provenance; never assert that a carrier was committed."""
        args = validate_tool_arguments("session_send", arguments)
        identity = _principal(principal, submit=True)
        try:
            target, binding = self._target(args["target_ref"])
        except BridgeError:
            raise BridgeError("binding_unavailable", "continuation binding is unavailable") from None
        if binding.continuation_operation_key != args["operation_key"]:
            raise BridgeError("operation_carrier_conflict", "continuation binding is unavailable")
        context = AgentDialogueContinueWriter._context(binding)
        context["actor_ref"] = dict(binding.current_writer)
        context = DialogueContextV2(**context).normalized()
        key = _request_key(args["operation_key"])
        read_ref = "session-reply-" + key
        with self.runtime.store.transaction() as connection:
            facts = self.runtime.current_harness_binding_source(
                target.epoch.attempt_id, connection=connection)
            if (facts.job_id != target.epoch.job_id
                    or facts.worker_id != target.epoch.worker_id
                    or facts.session_epoch_id != target.epoch.harness_session_epoch_id
                    or facts.generation_number != target.epoch.harness_generation_number
                    or facts.provider_session_id != target.epoch.harness_provider_session_id):
                raise BridgeError("binding_unavailable", "continuation binding is unavailable")
            roots = self.runtime.store.list_events(
                job_id=target.epoch.root_job_id, connection=connection)
            roots = [event for event in roots if event.event_type == "JOB_CREATED"]
            if len(roots) != 1:
                raise BridgeError("binding_unavailable", "original root is unavailable")
            root = roots[0]
            payload = {
                "schema": _SCHEMA, "principal": identity,
                "target_ref": args["target_ref"], "target_generation": target.generation,
                "operation_key": args["operation_key"],
                "binding_sha256": _digest(dataclasses.asdict(binding)),
                "root_job_id": target.epoch.root_job_id, "root_event_id": root.event_id,
                "root_event_sha256": _digest(root.to_dict()),
                "job_id": facts.job_id, "attempt_id": facts.attempt_id,
                "worker_id": facts.worker_id, "generation": _generation(facts),
                "context": context, "thread_ts": binding.thread_ts,
                "predecessor_message_key": binding.reply_to_message_key,
                "request_message_key": _continue_key(args["operation_key"]),
                "input_sha256": _digest({k: args[k] for k in ("instruction", "stop_condition")}),
                "read_ref": read_ref, "epoch": _epoch(target.epoch),
                "carrier": {key:getattr(target.physical.identity,key)
                            for key in ("workspace_id", "channel_id", "thread_ts")},
            }
            _validate_payload(payload)
            command_id = _PREFIX + key
            prior = self.runtime.store.get_event_by_command_id(command_id, connection=connection)
            if prior is not None:
                if (prior.event_type != _EVENT or prior.actor != _ACTOR
                        or prior.aggregate_type != "session_bridge_continue"
                        or prior.aggregate_id != key or prior.job_id != facts.job_id
                        or prior.attempt_id != facts.attempt_id
                        or prior.worker_id != facts.worker_id or prior.payload != payload):
                    raise BridgeError("operation_carrier_conflict", "continuation binding is unavailable")
            else:
                self.runtime.store.append_event(
                    connection, aggregate_type="session_bridge_continue", aggregate_id=key,
                    event_type=_EVENT, actor=_ACTOR, job_id=facts.job_id,
                    attempt_id=facts.attempt_id, worker_id=facts.worker_id,
                    payload=payload, command_id=command_id)
        return read_ref

    def _request(self, read_ref: str):
        match = _READ.fullmatch(read_ref) if isinstance(read_ref, str) else None
        if match is None:
            raise ValueError("invalid read reference")
        event = self.runtime.events.get_event_by_command_id(_PREFIX + match[1])
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
        roots = [e for e in self.runtime.events.list_events(job_id=value["root_job_id"])
                 if e.event_type == "JOB_CREATED"]
        if (len(roots) != 1 or roots[0].event_id != value["root_event_id"]
                or _digest(roots[0].to_dict()) != value["root_event_sha256"]):
            raise ValueError("original root changed")
        facts = self.runtime.current_harness_binding_source(value["attempt_id"])
        if (_generation(facts) != value["generation"]
                or (facts.job_id, facts.worker_id) != (value["job_id"], value["worker_id"])):
            raise ValueError("original writer changed")
        current = _read_current_target(self.runtime, value["context"]["operation_key"])
        if _epoch(current) != value["epoch"]:
            raise ValueError("original session changed")
        source = _read_dialogue_source(self.runtime, value["root_job_id"])
        commission = (source.commission_ref.to_dict() if hasattr(source.commission_ref,"to_dict")
                      else dict(source.commission_ref))
        if (source.work_ref != value["context"]["work_ref"]
                or commission != value["context"]["commission_ref"]
                or source.watch_mode != value["context"]["watch_mode"]):
            raise ValueError("original dialogue source changed")
        self._same_thread(value)
        return event, value, facts

    def _same_thread(self, value):
        # Parent messages may advance on this thread. No second physical thread
        # may be substituted; every matching Wake source is validated by its owner.
        events = self.runtime.events.list_events(job_id=value["job_id"], attempt_id=value["attempt_id"])
        if len(events) > 1024:
            raise ValueError("physical source evidence exceeds bound")
        found = False
        for event in events:
            if event.event_type != LedgerPhase.WAKE_REQUESTED.value:
                continue
            physical = event.payload.get("physical_source")
            if not isinstance(physical, dict) or physical.get("operation_key") != value["context"]["operation_key"]:
                continue
            record = wake_record_from_event(event)
            physical, obligation = record.physical_source, record.obligation
            if (physical is None or obligation is None
                    or {k:getattr(physical,k) for k in ("workspace_id","channel_id","thread_ts")} != value["carrier"]
                    or physical.candidate.root_job_id != value["root_job_id"]
                    or physical.candidate.job_id != value["job_id"]
                    or physical.candidate.attempt_id != value["attempt_id"]
                    or physical.candidate.worker_id != value["worker_id"]
                    or obligation.job_id != value["job_id"] or obligation.attempt_id != value["attempt_id"]
                    or obligation.source_workstream != value["context"]["work_ref"]):
                raise ValueError("original physical carrier changed")
            found = True
        if not found:
            raise ValueError("original physical carrier absent")

    async def resolve_read(self, *, principal, read_ref):
        try:
            identity = _principal(principal)
            event, value, _ = self._request(read_ref)
            if value["principal"] != identity:
                raise ValueError("foreign principal")
            response = await self.service_call(self.socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": value["context"], "thread_ts": value["thread_ts"]}})
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError("carrier unavailable")
            result = response["result"]
            if (result.get("thread_ts") != value["thread_ts"]
                    or result.get("historical_messages") != []
                    or type(result.get("mutated_count")) is not int
                    or result["mutated_count"] != 0
                    or not isinstance(result.get("messages"), list)
                    or len(result["messages"]) > 256):
                raise ValueError("carrier changed")
            messages = [validate_message_v2(item["message"]) for item in result["messages"]]
            requests = [m for m in messages if m["message_key"] == value["request_message_key"]]
            if (len(requests) != 1 or requests[0]["message_type"] != "CONTINUE"
                    or requests[0]["reply_to_message_key"] != value["predecessor_message_key"]
                    or requests[0]["actor_ref"] != {
                        "kind": "executive_surface", "seat": "ceo", "reasoning_surface": "chatgpt"}
                    or requests[0]["body"].get("scope_change") is not False
                    or _digest({k: requests[0]["body"][k] for k in ("instruction", "stop_condition")})
                       != value["input_sha256"]):
                raise ValueError("original request unavailable")
            expected_reply_key = "asd-native-reply-" + hashlib.sha256(
                ("mastermind.session_bridge.native_reply.v1\n" + value["operation_key"]).encode()
            ).hexdigest()[:40]
            replies = [m for m in messages
                       if m["message_key"] == expected_reply_key
                       and m["reply_to_message_key"] == value["request_message_key"]]
            if len(replies) != 1:
                raise ValueError("reply unavailable or ambiguous")
            reply = replies[0]
            if (reply["message_type"] != "PROGRESS" or reply["body"].get("stage") != "message_reply"
                    or any(reply[k] != value["context"][k] for k in (
                        "actor_ref", "applies_to", "work_ref", "commission_ref", "session_ref"))
                    or any(requests[0][k] != value["context"][k] for k in (
                        "applies_to", "work_ref", "commission_ref", "session_ref"))):
                raise ValueError("reply context changed")
            after, after_value, _ = self._request(read_ref)
            if after.to_dict() != event.to_dict() or after_value["principal"] != _principal(principal):
                raise ValueError("authorization changed")
            return NativeReplyReadBinding(
                authorized_principal=principal, read_ref=read_ref,
                request_ref=event.command_id, request_message_key=value["request_message_key"],
                thread_ts=value["thread_ts"], reply_message_key=reply["message_key"],
                reply_fingerprint=reply["fingerprint"], context=DialogueContextV2(**value["context"]),
                authorization_revision="event-" + str(event.event_id))
        except Exception:
            raise BridgeError("reply_unavailable", "authorized canonical reply is unavailable") from None

    def resolve(self, *, native_session_id, operation_key, in_reply_to):
        """Native host still authenticates its connection and owns atomic fencing."""
        try:
            key = _request_key(operation_key)
            _, value, facts = self._request("session-reply-" + key)
            if (value["operation_key"] != operation_key or value["request_message_key"] != in_reply_to
                    or facts.provider_session_id != native_session_id):
                raise ValueError("native request binding changed")
            if not value["target_ref"].startswith("codex:"):
                raise ValueError("native Codex owner is required")
            target, binding = self._target(value["target_ref"])
            # The existing Relay emits a new Wake for this CONTINUE. Its
            # physical source advances the same target's predecessor to the
            # request key; that causal advance must not revoke the reply.
            # Reconstruct only the original predecessor, then compare every
            # other frozen binding field. A later/unrelated leaf is not this
            # request and cannot authorize a stale native reply.
            original_binding = dataclasses.replace(
                binding, reply_to_message_key=value["predecessor_message_key"]
            )
            if (binding.reply_to_message_key not in {
                        value["predecessor_message_key"], value["request_message_key"]}
                    or original_binding.continuation_operation_key != operation_key
                    or _digest(dataclasses.asdict(original_binding)) != value["binding_sha256"]
                    or target.generation != value["target_generation"]):
                raise ValueError("native carrier binding changed")
            generation = value["generation"]
            return NativeReplyBinding(
                native_session_id=native_session_id, binding_id=generation["binding_id"],
                binding_generation=generation["binding_generation"],
                process_generation_id=generation["process_generation_id"],
                context=DialogueContextV2(**value["context"]), thread_ts=value["thread_ts"],
                request_message_key=in_reply_to, reply_operation_key=operation_key)
        except Exception:
            raise BridgeError("binding_unavailable", "exact native return binding unavailable") from None
