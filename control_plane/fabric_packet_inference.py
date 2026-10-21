"""One-shot, tool-free inference inside an existing, admitted Fabric Attempt.

This is an enforcement primitive, NOT a Worker/backend, admission, credential
loader or durable lifecycle. Trusted composition supplies the original Runtime
binding, fixed provider route, incumbent effect fence and forwarder. The fence
must consume durable first-use authority before provider I/O; this object's lock
only prevents concurrent/repeated calls in this live instance. Reconstructing it
does not authorize replay. Current subscription/harness policies still apply.

No model tools, code execution, filesystem operations or tool dispatch exist here.
Only the frozen packet is sent. The entire bounded Anthropic text stream is
validated before any text is delivered. Local forwarding shutdown is deliberately
separate from provider cancellation, OS cleanup and Worker-assignment revocation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import inspect
import json
import re
import threading
from typing import Callable

from control_plane.attempt_inference_endpoint import (
    AttemptInferenceBinding, InferenceEndpointContractError, InferenceForwardRefused,
    _validate_binding, _validate_receipt,
)
from control_plane.opencode_go_pooled_transport import ProviderRequest, _freeze_request

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class PacketInferenceError(RuntimeError):
    """Finite diagnostics only; never include provider payload or credentials."""


def _refuse(code):
    raise PacketInferenceError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class PacketInferenceContract:
    root_id: str
    job_id: str
    attempt_id: str
    effective_grant_digest: str
    commission_sha256: str
    physical_binding_sha256: str
    packet: str = field(repr=False)
    max_tokens: int = 8192
    max_response_bytes: int = 1024 * 1024
    max_text_bytes: int = 128 * 1024

    def __post_init__(self):
        for value in (self.root_id, self.job_id, self.attempt_id):
            if type(value) is not str or _ID.fullmatch(value) is None:
                _refuse("INVALID_ORIGINAL_LINEAGE")
        for value in (self.effective_grant_digest, self.commission_sha256,
                      self.physical_binding_sha256):
            if type(value) is not str or _SHA.fullmatch(value) is None:
                _refuse("INVALID_ORIGINAL_BINDING")
        try:
            valid = (type(self.packet) is str and self.packet.strip()
                     and "\x00" not in self.packet
                     and len(self.packet.encode("utf-8")) <= 512 * 1024)
        except UnicodeError:
            valid = False
        if not valid:
            _refuse("INVALID_PACKET")
        for value, maximum in ((self.max_tokens, 32768),
                               (self.max_response_bytes, 1024 * 1024),
                               (self.max_text_bytes, 512 * 1024)):
            if type(value) is not int or not 1 <= value <= maximum:
                _refuse("INVALID_PACKET_BOUND")

    def binding(self):
        return {name: getattr(self, name) for name in (
            "root_id", "job_id", "attempt_id", "effective_grant_digest",
            "commission_sha256", "physical_binding_sha256")}


@dataclass(frozen=True)
class PacketInferenceResult:
    text: str = field(repr=False)
    receipt_json: bytes


def _object(value, required, optional=()):
    if type(value) is not dict or not set(required) <= set(value) <= set(required) | set(optional):
        _refuse("UNSUPPORTED_PROVIDER_STREAM")
    return value


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _refuse("DUPLICATE_PROVIDER_FIELD")
            result[key] = value
        return result

    def constant(_):
        _refuse("NONFINITE_PROVIDER_FIELD")

    try:
        result = json.loads(raw.decode("utf-8", errors="strict"),
                            object_pairs_hook=pairs, parse_constant=constant)
        _canonical(result)
        return result
    except (ValueError, UnicodeError, RecursionError):
        _refuse("MALFORMED_PROVIDER_STREAM")


def _usage(value):
    _object(value, (), ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                        "cache_read_input_tokens"))
    if any(type(v) is not int or v < 0 for v in value.values()):
        _refuse("UNSUPPORTED_PROVIDER_USAGE")


def _text_stream(raw, *, model, max_text_bytes):
    """Closed Anthropic text subset, including exact terminal ordering."""
    raw = raw.replace(b"\r\n", b"\n")
    if b"\r" in raw or not raw.endswith(b"\n\n"):
        _refuse("INCOMPLETE_PROVIDER_STREAM")
    started = finished = terminal = False
    active = None
    next_index = 0
    text = []
    size = 0

    def append(value):
        nonlocal size
        if type(value) is not str:
            _refuse("NON_TEXT_PROVIDER_CONTENT")
        size += len(value.encode("utf-8"))
        if size > max_text_bytes:
            _refuse("TEXT_BOUND_EXCEEDED")
        text.append(value)

    for frame in raw[:-2].split(b"\n\n"):
        lines = frame.split(b"\n")
        if (len(lines) != 2 or not lines[0].startswith(b"event: ")
                or not lines[1].startswith(b"data: ")):
            _refuse("UNSUPPORTED_PROVIDER_FRAMING")
        value = _strict_json(lines[1][6:])
        if (type(value) is not dict or type(value.get("type")) is not str
                or lines[0][7:] != value["type"].encode("utf-8") or terminal):
            _refuse("UNSUPPORTED_PROVIDER_EVENT")
        kind = value["type"]
        if kind == "ping":
            _object(value, ("type",))
            continue
        if kind == "message_start":
            _object(value, ("type", "message"))
            message = _object(value["message"],
                ("id", "type", "role", "model", "content", "stop_reason", "stop_sequence", "usage"))
            if (started or type(message["id"]) is not str or not message["id"]
                    or message["type"] != "message" or message["role"] != "assistant"
                    or message["model"] != model or message["content"] != []
                    or message["stop_reason"] is not None or message["stop_sequence"] is not None):
                _refuse("FOREIGN_PROVIDER_MESSAGE")
            _usage(message["usage"])
            started = True
            continue
        if not started or finished and kind != "message_stop":
            _refuse("INVALID_PROVIDER_ORDER")
        if kind in {"content_block_start", "content_block_delta", "content_block_stop"}:
            extra = {"content_block_start": "content_block", "content_block_delta": "delta"}.get(kind)
            _object(value, ("type", "index") + ((extra,) if extra else ()))
            if type(value["index"]) is not int or value["index"] != next_index:
                _refuse("FOREIGN_CONTENT_BLOCK")
            if kind == "content_block_start":
                block = _object(value[extra], ("type", "text"))
                if active is not None or block["type"] != "text":
                    _refuse("MODEL_TOOL_OR_NON_TEXT_BLOCK_REFUSED")
                active = next_index
                append(block["text"])
            elif kind == "content_block_delta":
                delta = _object(value[extra], ("type", "text"))
                if active != next_index or delta["type"] != "text_delta":
                    _refuse("MODEL_TOOL_OR_NON_TEXT_DELTA_REFUSED")
                append(delta["text"])
            else:
                if active != next_index:
                    _refuse("INVALID_CONTENT_STOP")
                active = None
                next_index += 1
        elif kind == "message_delta":
            _object(value, ("type", "delta", "usage"))
            delta = _object(value["delta"], ("stop_reason", "stop_sequence"))
            if active is not None or delta != {"stop_reason": "end_turn", "stop_sequence": None}:
                _refuse("NON_TEXT_OR_INCOMPLETE_TERMINAL")
            _usage(value["usage"])
            finished = True
        elif kind == "message_stop":
            _object(value, ("type",))
            if not finished or active is not None:
                _refuse("INCOMPLETE_PROVIDER_STREAM")
            terminal = True
        else:
            _refuse("MODEL_TOOL_OR_UNSUPPORTED_EVENT_REFUSED")
    if not terminal or not size:
        _refuse("INCOMPLETE_PROVIDER_STREAM")
    return "".join(text)


class PacketOnlyInference:
    """Single admitted inference; existing owner must retain result/receipts.

    ``claim_once`` is the incumbent durable Attempt fence, not a new ledger.
    It receives a canonical immutable identity and must validate current grant,
    exact physical route and unused original Attempt before returning. A caller
    assertion or a fresh object is not authority. Exceptions never allow replay.
    ``forward`` uses the existing bound provider owner; no account selection or
    credential material enters this module. No default production composition is
    supplied. The original subscription/harness admission must still permit it.
    """

    def __init__(self, contract: PacketInferenceContract, route: AttemptInferenceBinding,
                 *, forward: Callable, claim_once: Callable):
        if type(contract) is not PacketInferenceContract:
            _refuse("INVALID_CONTRACT")
        try:
            _validate_binding(route)
        except InferenceEndpointContractError:
            raise PacketInferenceError("INVALID_INFERENCE_ROUTE") from None
        if route.protocol != "anthropic" or route.session_id != contract.attempt_id:
            _refuse("FOREIGN_ATTEMPT_OR_PROTOCOL")
        if not callable(forward) or not callable(claim_once):
            _refuse("EXISTING_OWNER_REQUIRED")
        self.contract, self.route = contract, route
        self._forward, self._claim_once = forward, claim_once
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._used = self._active = self._closed = False
        self._outcome = "UNSTARTED"
        body = _canonical({"model": route.model_id, "stream": True,
            "max_tokens": contract.max_tokens,
            "messages": [{"role": "user", "content": contract.packet}]})
        self._request = _freeze_request(ProviderRequest("messages", route.session_id,
            {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}, body), replayable=False)
        self._identity = _canonical({"binding": contract.binding(),
            "route_id": route.route_id, "route_generation": route.route_generation,
            "model_id": route.model_id, "protocol": route.protocol,
            "packet_sha256": _sha(contract.packet.encode()), "request_sha256": _sha(body),
            "max_response_bytes": contract.max_response_bytes,
            "max_text_bytes": contract.max_text_bytes})

    def execute(self) -> PacketInferenceResult:
        with self._lock:
            if self._used or self._closed:
                _refuse("ORIGINAL_ATTEMPT_ALREADY_CONSUMED_OR_CLOSED")
            self._used = self._active = True
        raw = bytearray()

        def consume(chunk):
            if self._cancel.is_set():
                _refuse("FORWARDING_CANCELLED_PROVIDER_EFFECT_UNRESOLVED")
            if type(chunk) is not bytes or not chunk:
                _refuse("INVALID_PROVIDER_CHUNK")
            if len(raw) + len(chunk) > self.contract.max_response_bytes:
                _refuse("RESPONSE_BOUND_EXCEEDED")
            raw.extend(chunk)

        outcome = "OWNER_CLAIM_UNCONFIRMED"
        try:
            if self._cancel.is_set():
                outcome = "CLOSED_BEFORE_OWNER_CLAIM"
                _refuse(outcome)
            claim_result = self._claim_once(self._identity)
            # The incumbent synchronous fence acknowledges by returning None.
            # A false verdict or un-awaited async callback is not admission.
            if claim_result is not None:
                if inspect.iscoroutine(claim_result):
                    claim_result.close()
                _refuse("OWNER_CLAIM_UNCONFIRMED")
            # A successful original-owner claim is a known effect even when
            # cancellation prevents the subsequent provider call. Never undo it
            # or call it unconfirmed. close() may race an already-active claim;
            # only the incumbent owner can reconcile its durable state.
            outcome = "OWNER_CLAIMED_PROVIDER_NOT_INVOKED"
            if self._cancel.is_set():
                _refuse("CLOSED_BEFORE_PROVIDER_FORWARD")
            outcome = "PROVIDER_EFFECT_UNRESOLVED"
            forwarded = self._forward(self._request, on_chunk=consume, cancel=self._cancel)
            receipt = _validate_receipt(forwarded, self.route)
            if self._cancel.is_set():
                _refuse("FORWARDING_CANCELLED_PROVIDER_EFFECT_UNRESOLVED")
            if (receipt.http_status != 200 or not receipt.terminal_observed
                    or receipt.bytes_forwarded != len(raw)):
                _refuse("PROVIDER_TERMINAL_OR_CAPTURE_UNPROVEN")
            text = _text_stream(bytes(raw), model=self.route.model_id,
                                max_text_bytes=self.contract.max_text_bytes)
            encoded = text.encode("utf-8")
            sealed = _canonical({"schema_version": "mastermind.fabric_packet_inference/v1",
                "identity": _strict_json(self._identity), "identity_sha256": _sha(self._identity),
                "response_sha256": _sha(raw), "response_bytes": len(raw),
                "text_sha256": _sha(encoded), "text_bytes": len(encoded),
                "provider_terminal_observed": True, "model_tools_exposed": False,
                "provider_cancellation_proven": False, "os_cleanup_proven": False,
                "assignment_revocation_proven": False})
            outcome = "TEXT_INFERENCE_COMPLETE"
            return PacketInferenceResult(text, sealed)
        except InferenceForwardRefused:
            outcome = "PROVIDER_ADMISSION_REFUSED"
            raise PacketInferenceError(outcome) from None
        except PacketInferenceError:
            raise
        except Exception:
            raise PacketInferenceError(outcome) from None
        finally:
            with self._lock:
                self._active = False
                self._closed = True
                self._outcome = outcome

    def close(self):
        """Stop local forwarding; never claim upstream cancellation or kill a UID."""
        with self._lock:
            self._closed = True
            self._cancel.set()

    def forwarding_shutdown_receipt(self) -> bytes:
        with self._lock:
            if not self._closed or self._active:
                _refuse("FORWARDING_SHUTDOWN_UNPROVEN")
            return _canonical({"schema_version": "mastermind.fabric_packet_forwarding_shutdown/v1",
                "identity_sha256": _sha(self._identity), "forwarding_disabled": True,
                "inflight_call_returned": self._used, "outcome": self._outcome,
                "durable_owner_readback_required": True, "provider_cancellation_proven": False,
                "os_cleanup_proven": False, "assignment_revocation_proven": False})
