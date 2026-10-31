"""Original-caller provenance and replies on the existing Runtime/Dialogue owners.

One immutable Runtime event binds an authenticated CONTINUE request before its
carrier effect. It is evidence of REQUESTED only. Agent Dialogue remains the
only send/dedup owner; this module creates no endpoint, retry or session store.
"""
from __future__ import annotations

import dataclasses
import base64
import hmac
import secrets
from contextlib import contextmanager
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE, AppPolicies
from integrations.business_mcp_auth.contracts import validate_resource_policy
from control_plane.executive_runtime import Runtime
from control_plane.native_continuation import (
    _ACTOR,
    _EPOCH,
    _EVENT,
    _GENERATION,
    _IDENTITY,
    _PAYLOAD,
    _PREFIX,
    _READ,
    _SCHEMA,
    _SHA,
    _TOKEN,
    _canonical,
    _continue_key,
    _digest,
    _epoch,
    _generation,
    _request_key,
    _validate_payload,
    stored_continuation_request,
)
from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2, validate_parent_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import CONTROL_VERSION_V2, RELAY_PARENT_ATTESTATION, call_service
from integrations.workspace_agent_runtime_binding import _read_current_target, _read_dialogue_source
from control_plane.wake_ledger import AckMode, LedgerPhase, wake_record_from_event
from control_plane.wake_persist import WakeLedgerRepository
from .dialogue_reply import AgentDialogueContinueWriter
from .native_read import NativeReplyReadBinding
from .native_reply import NativeReplyBinding
from .runtime_owner import RuntimeCodexTargetProjector, RuntimeFabricTargetProjector
from .schemas import BridgeError, validate_tool_arguments

_COMMIT_EVENT = "SESSION_BRIDGE_CONTINUE_COMMIT_STARTED"
_COMMIT_SCHEMA = "mastermind.session_bridge.continue_commit.v1"
_COMMIT_PREFIX = "session-bridge-continue-commit:"
_NATIVE_COMMIT_EVENT = "SESSION_BRIDGE_NATIVE_REPLY_COMMIT_STARTED"
_NATIVE_COMMIT_PREFIX = "session-bridge-native-reply-commit:"


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


def _trusted_read_pair(policies: AppPolicies | None):
    """Validate exactly one owner-supplied OAuth read/submit policy pair.

    The private caller may provide a verified principal, NEVER the pairing
    authority. Without a trusted pair only exact-policy original reads work.
    No new durable identity/authorization registry is introduced.
    """
    if policies is None:
        return None
    if type(policies) is not AppPolicies:
        raise TypeError("trusted read and submit policy pair required")
    try:
        read = validate_resource_policy(policies.read)
        submit = validate_resource_policy(policies.submit)
        if (tuple(read.required_scopes) != (READ_SCOPE,)
                or tuple(submit.required_scopes) != tuple(sorted((READ_SCOPE, SUBMIT_SCOPE)))
                or read.policy_id == submit.policy_id
                or read.resource != submit.resource
                or read.issuer != submit.issuer
                or read.allowed_subject_digests != submit.allowed_subject_digests):
            raise ValueError
    except Exception:
        raise ValueError("trusted read and submit policy pair invalid") from None
    return read, submit


def _read_matches_original(original: dict, current: dict,
                           principal: NeutralPrincipalProjection, *, trusted_pair) -> bool:
    """Preserve SEND provenance; admit only its explicitly paired READ policy.

    The original immutable request identifies its admitted submit policy; an
    independent READ grant may be exercised only when the *current trusted host*
    explicitly configures that same submit policy and its exact read counterpart.
    No caller-supplied policy, scope, or identity can manufacture this pairing.
    """
    if original == current:
        return True
    if trusted_pair is None or type(principal) is not NeutralPrincipalProjection:
        return False
    read, submit = trusted_pair
    return (
        tuple(principal.scopes) == (READ_SCOPE,)
        and isinstance(original, dict) and set(original) == set(_IDENTITY)
        and original.get("policy_id") == submit.policy_id
        and current.get("policy_id") == read.policy_id
        and original.get("resource") == read.resource
        and original.get("issuer_digest") == hashlib.sha256(read.issuer.encode("utf-8")).hexdigest()
        and original.get("subject_digest") in read.allowed_subject_digests
        and all(original.get(key) == current.get(key)
                for key in _IDENTITY if key != "policy_id")
    )


def _validate_original_writer(value, facts) -> None:
    if (_generation(facts) != value["generation"]
            or (facts.job_id, facts.worker_id) != (value["job_id"], value["worker_id"])):
        raise ValueError("original writer changed")


def _validate_original_epoch(value, current) -> None:
    if _epoch(current) != value["epoch"]:
        raise ValueError("original session changed")


def _validate_original_dialogue_source(value, source) -> None:
    commission = (source.commission_ref.to_dict() if hasattr(source.commission_ref,"to_dict")
                  else dict(source.commission_ref))
    if (source.work_ref != value["context"]["work_ref"]
            or commission != value["context"]["commission_ref"]
            or source.watch_mode != value["context"]["watch_mode"]):
        raise ValueError("original dialogue source changed")


def _validate_original_physical_events(value, events, *, parent_fingerprint=None) -> None:
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
                or (parent_fingerprint is not None
                    and physical.parent_fingerprint != parent_fingerprint)
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


class RuntimeSessionReturn:
    """Stateless joins over immutable request events and the current writer."""

    def __init__(self, runtime: Runtime, *, fabric: RuntimeFabricTargetProjector,
                 codex: RuntimeCodexTargetProjector, socket_path: Path,
                 service_call=call_service, authorized_policies: AppPolicies | None = None,
                 reference_cursor_key: bytes | None = None):
        if (type(runtime) is not Runtime or type(fabric) is not RuntimeFabricTargetProjector
                or type(codex) is not RuntimeCodexTargetProjector
                or not Path(socket_path).is_absolute() or not callable(service_call)):
            raise TypeError("existing Runtime and canonical owners are required")
        self.runtime, self.fabric, self.codex = runtime, fabric, codex
        self.socket_path, self.service_call = Path(socket_path), service_call
        self._trusted_read_pair = _trusted_read_pair(authorized_policies)
        if reference_cursor_key is not None and (
                type(reference_cursor_key) is not bytes or len(reference_cursor_key) != 32):
            raise TypeError("trusted 32-byte session composition cursor key required")
        # The installed Control composition shares this key across its
        # per-frame providers; process restart rotates it automatically.
        self._reference_cursor_key = (
            reference_cursor_key if reference_cursor_key is not None
            else secrets.token_bytes(32))

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
        prior = self._existing_request(args, identity)
        if prior is not None:
            return prior[1]["read_ref"]
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

    def _existing_request(self, args, identity):
        """Authenticate immutable provenance without requiring a live worker."""
        read_ref = "session-reply-" + _request_key(args["operation_key"])
        event = self.runtime.events.get_event_by_command_id(
            _PREFIX + _request_key(args["operation_key"]))
        if event is None:
            return None
        try:
            event, value = self._stored_request(read_ref)
            if (value["principal"] != identity
                    or value["target_ref"] != args["target_ref"]
                    or value["operation_key"] != args["operation_key"]
                    or value["input_sha256"] != _digest({
                        k: args[k] for k in ("instruction", "stop_condition")})):
                raise ValueError("original request changed")
            return event, value
        except Exception:
            raise BridgeError("operation_carrier_conflict",
                              "continuation binding is unavailable") from None

    @staticmethod
    def _commit_payload(event, message):
        return {
            "schema": _COMMIT_SCHEMA, "request_event_id": event.event_id,
            "request_event_sha256": _digest(event.to_dict()),
            "message_key": message["message_key"], "fingerprint": message["fingerprint"],
            "message_sha256": _digest(message),
        }

    def _native_commit_admission(self, event, events, *, connection=None):
        """Recognize only the closed native admission bound to this request.

        Its opaque reply hashes attest admission, not carrier success. Parent
        recovery must not need a live native writer or a visible native reply.
        """
        command = _NATIVE_COMMIT_PREFIX + event.aggregate_id
        indexed = self.runtime.store.get_event_by_command_id(command, connection=connection)
        return self._native_commit_admission_from_events(event, events, indexed)

    def _native_commit_admission_from_events(self, event, events, indexed):
        """Validate detached facts with the incumbent native admission law."""
        command = _NATIVE_COMMIT_PREFIX + event.aggregate_id
        native = [item for item in events if item.event_type == _NATIVE_COMMIT_EVENT]
        if not native and indexed is None:
            return None
        expected_key = "asd-native-reply-" + hashlib.sha256(
            ("mastermind.session_bridge.native_reply.v1\n" + event.payload["operation_key"]).encode()
        ).hexdigest()[:40]
        if (len(native) != 1 or indexed is None or native[0].to_dict() != indexed.to_dict()
                or indexed.actor != _ACTOR or indexed.command_id != command
                or indexed.aggregate_type != event.aggregate_type
                or indexed.aggregate_id != event.aggregate_id
                or (indexed.job_id, indexed.attempt_id, indexed.worker_id) !=
                   (event.job_id, event.attempt_id, event.worker_id)):
            raise ValueError("native reply admission changed")
        payload = indexed.payload
        if (set(payload) != {"schema", "request_event_id", "request_event_sha256",
                            "message_key", "fingerprint", "message_sha256", "binding_sha256"}
                or payload["schema"] != "mastermind.session_bridge.native_reply_commit.v1"
                or type(payload["request_event_id"]) is not int
                or payload["request_event_id"] != event.event_id
                or payload["request_event_sha256"] != _digest(event.to_dict())
                or payload["message_key"] != expected_key
                or any(type(payload[key]) is not str or _SHA.fullmatch(payload[key]) is None
                       for key in ("fingerprint", "message_sha256", "binding_sha256"))):
            raise ValueError("native reply admission payload changed")
        return indexed

    def _commit_started(self, event, message, *, connection=None):
        """Validate the sole commit-start fact on the existing request aggregate."""
        events = self.runtime.store.bounded_aggregate_events(
            "session_bridge_continue", event.aggregate_id, connection=connection)
        others = [item for item in events if item.event_id != event.event_id]
        native = self._native_commit_admission(event, others, connection=connection)
        if native is not None:
            others = [item for item in others if item.event_id != native.event_id]
        command = _COMMIT_PREFIX + event.aggregate_id
        indexed = self.runtime.store.get_event_by_command_id(command, connection=connection)
        return self._commit_started_from_events(event, message, others, native, indexed)

    def _commit_started_from_events(self, event, message, others, native, indexed):
        """Match already acquired/pruned aggregate facts to the exact message."""
        command = _COMMIT_PREFIX + event.aggregate_id
        if not others and indexed is None and native is None:
            return False
        if (len(others) != 1 or indexed is None or others[0].to_dict() != indexed.to_dict()
                or indexed.event_type != _COMMIT_EVENT or indexed.actor != _ACTOR
                or indexed.command_id != command
                or (indexed.job_id, indexed.attempt_id, indexed.worker_id) !=
                   (event.job_id, event.attempt_id, event.worker_id)
                or indexed.payload != self._commit_payload(event, message)):
            raise ValueError("continuation commit fact changed")
        if native is not None and native.event_id <= indexed.event_id:
            raise ValueError("native admission precedes continuation commit")
        return True

    def begin_continuation_commit(self, principal, arguments, *,
                                  binding, context, request_message, message):
        """Record the READY-to-COMMIT boundary once; retries only reconcile.

        This is an evidence transition on the existing aggregate, not permission
        to retry Relay or evidence that the provider accepted the message.
        """
        args = validate_tool_arguments("session_send", arguments)
        try:
            with self.runtime.store.transaction() as connection:
                prior = self._existing_request(args, _principal(principal, submit=True))
                if prior is None:
                    raise ValueError("original request unavailable")
                event, value = prior
                target, current_binding = self._target(args["target_ref"])
                _, _, facts = self._request(value["read_ref"])
                expected_context = AgentDialogueContinueWriter._context(current_binding)
                expected = AgentDialogueContinueWriter._message(
                    request_message=request_message, context=expected_context,
                    instruction=args["instruction"], stop_condition=args["stop_condition"],
                    operation_key=args["operation_key"])
                predecessor = validate_message_v2(request_message)
                final_message = validate_message_v2(message)
                if (dataclasses.asdict(binding) != dataclasses.asdict(current_binding)
                        or _digest(dataclasses.asdict(current_binding)) != value["binding_sha256"]
                        or current_binding.continuation_operation_key != args["operation_key"]
                        or target.generation != value["target_generation"]
                        or _epoch(target.epoch) != value["epoch"]
                        or context != expected_context
                        or predecessor["message_key"] != value["predecessor_message_key"]
                        or predecessor["message_type"] not in {"ACK", "PROGRESS", "BLOCKED", "RESULT"}
                        or any(predecessor[k] != value["context"][k] for k in (
                            "actor_ref", "applies_to", "work_ref", "commission_ref", "session_ref"))
                        or (predecessor["message_type"] == "BLOCKED"
                            and predecessor["body"].get("needed_from") != "sol")
                        or final_message != expected
                        or expected["message_key"] != value["request_message_key"]):
                    raise ValueError("final continuation binding changed")
                # The transaction excludes a second local writer between this
                # current Runtime binding check and the one durable admission.
                locked_facts = self.runtime.current_harness_binding_source(
                    value["attempt_id"], connection=connection)
                if (_generation(locked_facts) != _generation(facts)
                        or (locked_facts.job_id, locked_facts.attempt_id, locked_facts.worker_id)
                           != (value["job_id"], value["attempt_id"], value["worker_id"])):
                    raise ValueError("final writer changed")
                if self._commit_started(event, expected, connection=connection):
                    raise ValueError("continuation COMMIT may already have occurred")
                self.runtime.store.append_event(
                    connection, aggregate_type="session_bridge_continue",
                    aggregate_id=event.aggregate_id, event_type=_COMMIT_EVENT, actor=_ACTOR,
                    job_id=event.job_id, attempt_id=event.attempt_id, worker_id=event.worker_id,
                    payload=self._commit_payload(event, expected),
                    command_id=_COMMIT_PREFIX + event.aggregate_id)
        except Exception:
            raise BridgeError("carrier_effect_unknown",
                              "continuation COMMIT cannot be admitted again") from None

    async def reconcile_existing_send(self, principal, arguments):
        """Read the original carrier; a duplicate never re-enters effect owners.

        REQUESTED provenance alone claims no effect. A COMMIT_STARTED fact
        forbids a second COMMIT. Only the exact canonical CONTINUE permits a
        duplicate receipt. An unreadable or changed carrier
        cannot fall through to a resend.
        """
        args = validate_tool_arguments("session_send", arguments)
        identity = _principal(principal, submit=True)
        prior = self._existing_request(args, identity)
        if prior is None:
            return None
        event, value = prior
        try:
            context = {**value["context"], "actor_ref": {
                "kind": "executive_surface", "seat": "ceo", "reasoning_surface": "chatgpt"}}
            response = await self.service_call(self.socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": context, "thread_ts": value["thread_ts"]}})
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError("carrier unavailable")
            result = response.get("result")
            if (not isinstance(result, dict)
                    or result.get("thread_ts") != value["thread_ts"]
                    or result.get("historical_messages") != []
                    or type(result.get("mutated_count")) is not int
                    or result["mutated_count"] != 0
                    or not isinstance(result.get("messages"), list)
                    or len(result["messages"]) > 256):
                raise ValueError("carrier changed")
            messages = [validate_message_v2(item["message"]) for item in result["messages"]]
            predecessors = [m for m in messages
                            if m["message_key"] == value["predecessor_message_key"]]
            if (len(predecessors) != 1
                    or predecessors[0]["message_type"] not in {"ACK", "PROGRESS", "BLOCKED", "RESULT"}
                    or any(predecessors[0][k] != value["context"][k] for k in (
                        "actor_ref", "applies_to", "work_ref", "commission_ref", "session_ref"))
                    or (predecessors[0]["message_type"] == "BLOCKED"
                        and predecessors[0]["body"].get("needed_from") != "sol")):
                raise ValueError("original predecessor unavailable")
            expected = AgentDialogueContinueWriter._message(
                request_message=predecessors[0], context=context,
                instruction=args["instruction"], stop_condition=args["stop_condition"],
                operation_key=args["operation_key"])
            requests = [m for m in messages
                        if m["message_key"] == value["request_message_key"]
                        or (m["reply_to_message_key"] == value["predecessor_message_key"]
                            and m["actor_ref"]["kind"] == "executive_surface")]
            if requests and (len(requests) != 1 or requests[0] != expected):
                raise ValueError("original continuation changed")
            after = self._existing_request(args, _principal(principal, submit=True))
            if after is None or after[0].to_dict() != event.to_dict():
                raise ValueError("original authorization changed")
            started = self._commit_started(event, expected)
            if not requests:
                if started:
                    raise ValueError("original COMMIT outcome is still unknown")
                return None  # current writer must still authorize any new effect
            return {
                "reply_committed": True, "action": "DUPLICATE",
                "message_key": expected["message_key"], "fingerprint": expected["fingerprint"],
                "thread_ts": value["thread_ts"],
            }
        except Exception:
            raise BridgeError("carrier_effect_unknown",
                              "original continuation could not be reconciled") from None

    def _stored_request(self, read_ref: str):
        return stored_continuation_request(self.runtime, read_ref)

    def _request(self, read_ref: str):
        event, value = self._stored_request(read_ref)
        facts = self.runtime.current_harness_binding_source(value["attempt_id"])
        _validate_original_writer(value, facts)
        current = _read_current_target(self.runtime, value["context"]["operation_key"])
        _validate_original_epoch(value, current)
        source = _read_dialogue_source(self.runtime, value["root_job_id"])
        _validate_original_dialogue_source(value, source)
        self._same_thread(value)
        return event, value, facts

    def _same_thread(self, value, *, parent_fingerprint=None):
        # Parent messages may advance on this thread. No second physical thread
        # may be substituted; every matching Wake source is validated by its owner.
        events = self.runtime.events.list_events(job_id=value["job_id"], attempt_id=value["attempt_id"])
        _validate_original_physical_events(
            value, events, parent_fingerprint=parent_fingerprint)

    @staticmethod
    def _continuation_messages(value, result):
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
        if any(requests[0][k] != value["context"][k] for k in (
                "applies_to", "work_ref", "commission_ref", "session_ref")):
            raise ValueError("original request context changed")
        return messages, requests[0]

    async def _read_bound_parent(self, value):
        response = await self.service_call(self.socket_path, {
            "version": CONTROL_VERSION_V2, "operation": "read_bound_parent",
            "args": {"context": value["context"], "thread_ts": value["thread_ts"]}})
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise ValueError("canonical parent unavailable")
        result = response["result"]
        if (type(result) is not dict
                or set(result) != {"attestation", "thread_ts", "parent"}
                or result["attestation"] != RELAY_PARENT_ATTESTATION
                or result["thread_ts"] != value["thread_ts"]):
            raise ValueError("canonical parent binding changed")
        parent = validate_parent_v2(result["parent"])
        if any(parent[k] != value["context"][k] for k in (
                "work_ref", "commission_ref", "session_ref", "operation_key", "watch_mode")):
            raise ValueError("canonical parent context changed")
        return parent

    async def read_continuation_source(self, *, read_ref):
        """Internal read for the root publisher; never a grant or public endpoint.

        The immutable event already binds the authenticated original caller.
        Publication separately requires the existing root transaction owner.
        """
        try:
            event, value, _ = self._request(read_ref)
            parent = await self._read_bound_parent(value)
            self._same_thread(value, parent_fingerprint=parent["fingerprint"])
            response = await self.service_call(self.socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": value["context"], "thread_ts": value["thread_ts"]}})
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError("canonical continuation unavailable")
            messages, message = self._continuation_messages(value, response["result"])
            if await self._read_bound_parent(value) != parent:
                raise ValueError("canonical parent changed during read")
            after, _, _ = self._request(read_ref)
            if after.to_dict() != event.to_dict():
                raise ValueError("original authorization changed")
            self._same_thread(value, parent_fingerprint=parent["fingerprint"])
            return {"event": event.to_dict(), "request": value,
                    "parent": parent, "message": message, "messages": messages}
        except Exception:
            raise BridgeError("source_unavailable",
                              "authorized canonical continuation is unavailable") from None

    def session_reply_references(
        self, *, principal, work_ref: str, root_job_id: str | None = None,
        cursor: str | None = None, page_size: int = 16,
    ) -> dict:
        """READ-only bounded projection from immutable original request Events.

        Rows are REFERENCE_ONLY, never COMMIT, reply availability or parent ACK.
        Process-local signed cursors expire on composition restart. This method
        does not allocate an active operation slot or issue any Dialogue effects.
        """
        try:
            identity = _principal(principal)
            if (type(work_ref) is not str or _TOKEN.fullmatch(work_ref) is None
                    or (root_job_id is not None and
                        (type(root_job_id) is not str or _TOKEN.fullmatch(root_job_id) is None))
                    or type(page_size) is not int or not 1 <= page_size <= 32):
                raise ValueError("invalid reference selector")
            scope = hashlib.sha256(_canonical({
                "principal": identity, "scopes": tuple(principal.scopes),
                "work_ref": work_ref, "root_job_id": root_job_id,
            })).hexdigest()
            if cursor is None:
                watermark, before = None, None
            else:
                if type(cursor) is not str or len(cursor) > 2048:
                    raise ValueError("invalid cursor")
                raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
                # Python's permissive decoder can ignore or normalize trailing
                # material. Require the single canonical encoding before HMAC
                # verification: every byte of the supplied cursor is bound.
                if base64.urlsafe_b64encode(raw).decode("ascii") != cursor:
                    raise ValueError("noncanonical cursor")
                if len(raw) > 384 or len(raw) < 33:
                    raise ValueError("invalid cursor size")
                body, mac = raw[:-32], raw[-32:]
                expected = hmac.digest(self._reference_cursor_key, body, "sha256")
                if not hmac.compare_digest(mac, expected):
                    raise ValueError("invalid cursor authentication")
                state = json.loads(body)
                if (type(state) is not dict or set(state) != {"v", "s", "w", "p"}
                        or state["v"] != 1 or state["s"] != scope
                        or type(state["w"]) is not int or state["w"] < 0
                        or type(state["p"]) is not int or state["p"] < 1):
                    raise ValueError("invalid cursor binding")
                watermark, before = state["w"], state["p"]
            original_principals = [tuple(identity[key] for key in _IDENTITY)]
            if self._trusted_read_pair is not None:
                original = {**identity, "policy_id": self._trusted_read_pair[1].policy_id}
                if _read_matches_original(original, identity, principal,
                                          trusted_pair=self._trusted_read_pair):
                    paired = tuple(original[key] for key in _IDENTITY)
                    if paired not in original_principals:
                        original_principals.append(paired)
            with self.runtime.observe_bounded_read() as observation:
                watermark, position, references = observation.read_session_reply_references_bounded(
                    work_ref=work_ref, root_job_id=root_job_id,
                    original_principals=tuple(original_principals),
                    high_water=watermark, before_event_id=before, page_size=page_size,
                )
            # A failed close/finalization cannot release a partial public page.
            # Unbound Runtime's finalized UNKNOWN receipt remains admissible.
            _ = observation.receipt
            rows = list(references)
            # Never claim completeness when a partial metadata window exists.
            more = position is not None and position > 1
            next_cursor = None
            if more:
                body = _canonical({"v": 1, "s": scope, "w": watermark, "p": position})
                next_cursor = base64.urlsafe_b64encode(
                    body + hmac.digest(self._reference_cursor_key, body, "sha256")
                ).decode("ascii")
            if _principal(principal) != identity:
                raise ValueError("authorization changed")
            return {"schema": "mastermind.session_reply_references.v1",
                    "status": "PARTIAL" if more else "COMPLETE",
                    "references": rows, "next_cursor": next_cursor,
                    "high_water": watermark}
        except Exception:
            raise BridgeError("reply_unavailable",
                              "authorized canonical reply references unavailable") from None

    def resolve_operation_read_ref(self, *, principal, operation_key):
        """Recover an original caller's reference using immutable provenance only."""
        try:
            identity = _principal(principal)
            if not isinstance(operation_key, str) or _TOKEN.fullmatch(operation_key) is None:
                raise ValueError("invalid original operation")
            read_ref = "session-reply-" + _request_key(operation_key)
            with self.runtime.observe_bounded_read() as observation:
                _, value = observation.read_session_original_request_bounded(read_ref=read_ref)
            # Provenance-only recovery does not require COMMIT or a live target.
            # Closing/finalization failures withhold the reference; UNKNOWN is valid.
            _ = observation.receipt
            if not _read_matches_original(value["principal"], identity, principal,
                    trusted_pair=self._trusted_read_pair) or value["operation_key"] != operation_key:
                raise ValueError("foreign original operation")
            return value["read_ref"]
        except Exception:
            raise BridgeError("reply_unavailable", "authorized canonical reply is unavailable") from None

    def _read_request(self, read_ref):
        """A committed result retains its original read provenance after cleanup.

        This grants no target discovery, writer lease, attention or execution.
        Uncommitted requests still need the current writer. A native admission
        proves COMMIT admission only; the exact canonical reply must also be
        read and matched before any result can be returned.
        """
        if not isinstance(read_ref, str) or _READ.fullmatch(read_ref) is None:
            raise ValueError("invalid read reference")
        with self.runtime.observe_bounded_read() as observation:
            event, value, events, indexed, native_indexed = (
                observation.read_session_reply_evidence_bounded(read_ref=read_ref))
        # No acquired fact escapes a failed physical close/finalization. This
        # immutable selection requires a receipt, never a SAME state assertion.
        _ = observation.receipt
        admission = self._native_commit_admission_from_events(event, events, native_indexed)
        others = tuple(item for item in events if item.event_id != event.event_id
                       and (admission is None or item.event_id != admission.event_id))
        if admission is None:
            # The live fallback acquires its own fresh original request.
            # Close and finalize that separate observation before validating
            # or exposing its material through the shared provenance rules.
            with self.runtime.observe_bounded_read() as live_observation:
                live_event, live_value, facts, current, source, scoped_events = (
                    live_observation.read_session_live_writer_bounded(read_ref=read_ref))
            _ = live_observation.receipt
            _validate_original_writer(live_value, facts)
            _validate_original_epoch(live_value, current)
            _validate_original_dialogue_source(live_value, source)
            _validate_original_physical_events(live_value, scoped_events)
            event, value = live_event, live_value
        return event, value, admission, others, indexed

    async def require_committed_native_reply(self, *, read_ref):
        """Internal owner read of the exact reply; grants no parent identity."""
        try:
            event, value, _ = self._request(read_ref)
            response = await self.service_call(self.socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": value["context"], "thread_ts": value["thread_ts"]}})
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError("canonical carrier unavailable")
            messages, request = self._continuation_messages(value, response["result"])
            events = self.runtime.store.bounded_aggregate_events(
                event.aggregate_type, event.aggregate_id)
            admission = self._native_commit_admission(event, events)
            if admission is None or not self._commit_started(event, request):
                raise ValueError("native COMMIT unavailable")
            replies = [item for item in messages
                if item["message_key"] == admission.payload["message_key"]]
            if (len(replies) != 1 or _digest(replies[0]) != admission.payload["message_sha256"]
                    or replies[0]["fingerprint"] != admission.payload["fingerprint"]
                    or replies[0]["reply_to_message_key"] != value["request_message_key"]
                    or replies[0]["message_type"] != "PROGRESS"
                    or replies[0]["body"].get("stage") != "message_reply"
                    or any(replies[0][key] != value["context"][key] for key in (
                        "actor_ref", "applies_to", "work_ref", "commission_ref", "session_ref"))):
                raise ValueError("exact canonical native reply unavailable")
            after, after_value, _ = self._request(read_ref)
            after_events = self.runtime.store.bounded_aggregate_events(
                after.aggregate_type, after.aggregate_id)
            after_admission = self._native_commit_admission(after, after_events)
            if (after.to_dict() != event.to_dict() or after_value != value
                    or after_admission is None or after_admission.to_dict() != admission.to_dict()
                    or not self._commit_started(after, request)):
                raise ValueError("canonical commit changed during read")
            return replies[0]
        except Exception:
            raise BridgeError("reply_unavailable", "exact canonical native reply unavailable") from None

    async def resolve_read(self, *, principal, read_ref):
        try:
            identity = _principal(principal)
            event, value, admission, others, indexed = self._read_request(read_ref)
            if not _read_matches_original(value["principal"], identity, principal,
                    trusted_pair=self._trusted_read_pair):
                raise ValueError("foreign principal")
            response = await self.service_call(self.socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": value["context"], "thread_ts": value["thread_ts"]}})
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError("carrier unavailable")
            messages, request = self._continuation_messages(value, response["result"])
            if admission is not None and not self._commit_started_from_events(
                    event, request, others, admission, indexed):
                raise ValueError("original continuation COMMIT is unavailable")
            expected_reply_key = "asd-native-reply-" + hashlib.sha256(
                ("mastermind.session_bridge.native_reply.v1\n" + value["operation_key"]).encode()
            ).hexdigest()[:40]
            replies = [m for m in messages
                       if m["message_key"] == expected_reply_key
                       and m["reply_to_message_key"] == value["request_message_key"]]
            if len(replies) != 1:
                raise ValueError("reply unavailable or ambiguous")
            reply = replies[0]
            if admission is not None and (
                    reply["fingerprint"] != admission.payload["fingerprint"]
                    or _digest(reply) != admission.payload["message_sha256"]):
                raise ValueError("canonical reply differs from its native COMMIT admission")
            if (reply["message_type"] != "PROGRESS" or reply["body"].get("stage") != "message_reply"
                    or any(reply[k] != value["context"][k] for k in (
                        "actor_ref", "applies_to", "work_ref", "commission_ref", "session_ref"))
                    or any(request[k] != value["context"][k] for k in (
                        "applies_to", "work_ref", "commission_ref", "session_ref"))):
                raise ValueError("reply context changed")
            after, after_value, after_admission, after_others, after_indexed = self._read_request(read_ref)
            if (after.to_dict() != event.to_dict()
                    or (None if admission is None else admission.to_dict())
                    != (None if after_admission is None else after_admission.to_dict())
                    or not _read_matches_original(after_value["principal"], _principal(principal),
                        principal, trusted_pair=self._trusted_read_pair)):
                raise ValueError("authorization changed")
            if after_admission is not None and not self._commit_started_from_events(
                    after, request, after_others, after_admission, after_indexed):
                raise ValueError("original continuation COMMIT changed during read")
            return NativeReplyReadBinding(
                authorized_principal=principal, read_ref=read_ref,
                request_ref=event.command_id, request_message_key=value["request_message_key"],
                thread_ts=value["thread_ts"], reply_message_key=reply["message_key"],
                reply_fingerprint=reply["fingerprint"], context=DialogueContextV2(**value["context"]),
                authorization_revision="event-" + str(event.event_id))
        except Exception:
            raise BridgeError("reply_unavailable", "authorized canonical reply is unavailable") from None

    def require_native_ack(self, binding, *, workspace_id, channel_id, connection=None):
        """Reuse the exact causal inbound ACK; never claim parent consumption.

        Wake ingress validates its native session/turn observation and stores a
        versioned evidence facet in TARGET_ACKNOWLEDGED. Historical ACKs without
        that evidence cannot register this new callback. Recheck today's writer,
        consume the existing validated ACK/delivery pair, never a model claim.
        """
        try:
            current = self.resolve(native_session_id=binding.native_session_id,
                operation_key=binding.reply_operation_key, in_reply_to=binding.request_message_key)
            if dataclasses.asdict(current) != dataclasses.asdict(binding):
                raise ValueError("native binding changed")
            request_event, value, facts = self._request("session-reply-" + _request_key(binding.reply_operation_key))
            if value["carrier"] != {"workspace_id": workspace_id, "channel_id": channel_id,
                                     "thread_ts": binding.thread_ts}:
                raise ValueError("outside installed carrier")
            if connection is not None:
                locked = self.runtime.current_harness_binding_source(value["attempt_id"], connection=connection)
                if locked != facts:
                    raise ValueError("native writer changed")
            events = self.runtime.events.list_events(job_id=value["job_id"], attempt_id=value["attempt_id"])
            if len(events) > 1024:
                raise ValueError("native evidence exceeds bound")
            repo = WakeLedgerRepository(self.runtime)
            matched = []
            for event in events:
                if event.event_type != LedgerPhase.WAKE_REQUESTED.value:
                    continue
                record = wake_record_from_event(event)
                source = record.physical_source
                if (source is None or source.operation_key != value["context"]["operation_key"]
                        or source.predecessor_message_key != binding.request_message_key):
                    continue
                # _request/_same_thread has already checked root/Attempt/worker,
                # original carrier and workstream for all matching sources.
                records = (repo.list_ledger_records_on_connection(connection, record.obligation.obligation_id)
                           if connection is not None else
                           tuple(item.record for item in repo.list_records(record.obligation.obligation_id)))
                for item in records:
                    ack = item.ack
                    if (item.phase is LedgerPhase.TARGET_ACKNOWLEDGED and ack is not None
                            and ack.ack_mode is AckMode.REASONING_SESSION
                            and ack.reasoning_surface == "codex"
                            and ack.binding_id == binding.binding_id
                            and ack.binding_generation == binding.binding_generation
                            and ack.native_continuation is not None):
                        evidence = ack.native_continuation
                        delivered = next((r for r in records if r.command_id == ack.delivered_command_id), None)
                        if (evidence.request_event_id != request_event.event_id
                                or evidence.request_event_sha256 != _digest(request_event.to_dict())
                                or evidence.target_attempt_id != facts.attempt_id
                                or evidence.process_generation_id != binding.process_generation_id
                                or evidence.native_session_sha256 != hashlib.sha256(binding.native_session_id.encode()).hexdigest()
                                or delivered is None or evidence.nudge_id != delivered.nudge_id):
                            raise ValueError("native consumption evidence changed")
                        matched.append(item.command_id)
            if len(matched) != 1:
                raise ValueError("exact native continuation acknowledgment unavailable")
            return matched[0]
        except Exception:
            raise BridgeError("binding_unavailable", "exact native continuation acknowledgment unavailable") from None

    def _native_commit_source(self, binding, message, *, connection):
        if type(binding) is not NativeReplyBinding:
            raise ValueError("native binding unavailable")
        current = self.resolve(native_session_id=binding.native_session_id,
            operation_key=binding.reply_operation_key, in_reply_to=binding.request_message_key)
        if dataclasses.asdict(current) != dataclasses.asdict(binding):
            raise ValueError("native return changed")
        event, value = self._stored_request("session-reply-" + _request_key(binding.reply_operation_key))
        facts = self.runtime.current_harness_binding_source(value["attempt_id"], connection=connection)
        if (_generation(facts) != value["generation"]
                or (facts.job_id, facts.worker_id) != (value["job_id"], value["worker_id"])):
            raise ValueError("native writer changed")
        validated = validate_message_v2(message)
        expected_key = "asd-native-reply-" + hashlib.sha256(
            ("mastermind.session_bridge.native_reply.v1\n" + binding.reply_operation_key).encode()
        ).hexdigest()[:40]
        if (validated != message or validated["message_key"] != expected_key
                or validated["message_type"] != "PROGRESS"
                or validated["body"].get("stage") != "message_reply"
                or validated["reply_to_message_key"] != value["request_message_key"]
                or any(validated[k] != value["context"][k] for k in (
                    "actor_ref", "applies_to", "work_ref", "commission_ref", "session_ref"))):
            raise ValueError("native message changed")
        return event, {
            "schema": "mastermind.session_bridge.native_reply_commit.v1",
            "request_event_id": event.event_id,
            "request_event_sha256": _digest(event.to_dict()),
            "message_key": validated["message_key"], "fingerprint": validated["fingerprint"],
            "message_sha256": _digest(validated),
            "binding_sha256": _digest(dataclasses.asdict(binding)),
        }

    @contextmanager
    def native_reply_commit_fence(self, binding, message, *, guard):
        """Durably admit once, then fence Runtime through the local COMMIT write.

        The host supplies the connected-child/capability guard. Both transactions
        are synchronous: canonical carrier reads precede them, and drain/response
        waits follow them. The first transaction MUST commit before any external
        handoff; a crash cannot roll its admission back. A revocation in the gap
        leaves a conservative unknown that only the original carrier can settle.
        This is not a distributed fence on Slack/provider execution.
        """
        try:
            if not callable(guard):
                raise ValueError("authenticated guard required")
            with self.runtime.store.transaction() as connection:
                guard(connection)
                event, payload = self._native_commit_source(binding, message, connection=connection)
                command = _NATIVE_COMMIT_PREFIX + event.aggregate_id
                if self.runtime.store.get_event_by_command_id(command, connection=connection) is not None:
                    raise BridgeError("carrier_effect_unknown", "native reply requires original-operation reconciliation")
                self.runtime.store.append_event(
                    connection, aggregate_type="session_bridge_continue", aggregate_id=event.aggregate_id,
                    event_type=_NATIVE_COMMIT_EVENT, actor=_ACTOR,
                    job_id=event.job_id, attempt_id=event.attempt_id, worker_id=event.worker_id,
                    payload=payload, command_id=command)
        except BridgeError:
            raise
        except Exception:
            raise BridgeError("binding_unavailable", "native COMMIT was not admitted") from None
        with self.runtime.store.transaction() as connection:
            try:
                guard(connection)
                current_event, current_payload = self._native_commit_source(binding, message, connection=connection)
                stored = self.runtime.store.get_event_by_command_id(command, connection=connection)
                if (current_event.to_dict() != event.to_dict() or current_payload != payload
                        or stored is None or stored.event_type != _NATIVE_COMMIT_EVENT
                        or stored.actor != _ACTOR or stored.aggregate_id != event.aggregate_id
                        or stored.aggregate_type != "session_bridge_continue" or stored.payload != payload
                        or (stored.job_id, stored.attempt_id, stored.worker_id)
                           != (event.job_id, event.attempt_id, event.worker_id)):
                    raise ValueError("native admission changed")
            except Exception:
                raise BridgeError("carrier_effect_unknown", "native reply requires original-operation reconciliation") from None
            # Caller may perform only the synchronous local transport handoff.
            yield

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
