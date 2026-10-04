"""Canonical continuation input and same-turn reply on the incumbent carrier."""
from __future__ import annotations

import hashlib
from pathlib import Path

from common.redaction import sanitize_external_text
from control_plane.operator_harness_contract import AttentionContinuationInput
from .native_reply import NativeReplyWriter
from .runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from .runtime_return import RuntimeSessionReturn
from .schemas import BridgeError


def build_native_continuation_callbacks(runtime, *, dialogue_socket_path: Path):
    fabric = RuntimeFabricTargetProjector(runtime)
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: True)
    returns = RuntimeSessionReturn(runtime, fabric=fabric, codex=codex,
                                   socket_path=dialogue_socket_path)

    async def read_source(physical, binding):
        read_ref = returns.read_ref_for_physical_source(physical)
        source = await returns.read_continuation_source(read_ref=read_ref)
        request, parent, message = source["request"], source["parent"], source["message"]
        generation = request["generation"]
        if (
            request["context"]["operation_key"] != physical.operation_key
            or request["request_message_key"] != physical.predecessor_message_key
            or request["carrier"] != {k: getattr(physical, k) for k in
                                      ("workspace_id", "channel_id", "thread_ts")}
            or parent["fingerprint"] != physical.parent_fingerprint
            or message["message_key"] != physical.predecessor_message_key
            or message["fingerprint"] != physical.predecessor_message_fingerprint
            or message["message_type"] != "CONTINUE"
            or generation["binding_id"] != binding.binding_id
            or generation["binding_generation"] != binding.binding_generation
            or generation["native_session_sha256"]
               != hashlib.sha256(binding.native_handle.encode("utf-8")).hexdigest()
        ):
            raise BridgeError("binding_unavailable", "continuation source changed")
        projection = AttentionContinuationInput.create(
            obligation_id=physical.obligation_id,
            operation_key=request["operation_key"],
            request_message_key=request["request_message_key"],
            physical_source_sha256=physical.digest,
            continuation_text=message["body"]["instruction"],
            stop_condition=message["body"]["stop_condition"])
        return projection, request

    async def source_input(physical, binding):
        projection, _ = await read_source(physical, binding)
        return projection

    async def publish(physical, binding, evidence):
        source, request = await read_source(physical, binding)
        if (any(getattr(evidence, k) != getattr(source, k) for k in (
                "obligation_id", "operation_key", "request_message_key",
                "physical_source_sha256", "immutable_input_sha256"))
                or evidence.target_attempt_id != request["attempt_id"]
                or evidence.process_generation_id != request["generation"]["process_generation_id"]
                or evidence.binding_id != binding.binding_id
                or evidence.binding_generation != binding.binding_generation
                or evidence.provider_session_sha256
                   != hashlib.sha256(binding.native_handle.encode("utf-8")).hexdigest()
                or any(sanitize_external_text(getattr(evidence, k), limit=700) != getattr(evidence, k)
                       for k in ("text", "next_step"))):
            raise BridgeError("binding_unavailable", "stored continuation evidence changed")
        # Resolver rechecks the current native generation and exact original request
        # before send; deterministic same-operation reply reconciles post-send loss.
        receipt = await NativeReplyWriter(
            returns, native_session_id=binding.native_handle,
            socket_path=dialogue_socket_path)({
                "operation_key": evidence.operation_key,
                "in_reply_to": evidence.request_message_key,
                "text": evidence.text, "next_step": evidence.next_step})
        if (receipt["reply_committed"] is not True
                or receipt["in_reply_to"] != evidence.request_message_key
                or receipt["parent_consumed"] is not False):
            raise BridgeError("carrier_effect_unknown", "native reply receipt is invalid")

    return source_input, publish
