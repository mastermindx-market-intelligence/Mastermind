"""Fixed native Responses transport drivers for the existing A application owner.

Two inert, fixed drivers turn an application request into an immutable native
``responses`` POST body and perform exactly one bounded POST on an
already-selected account.

Ownership boundary (this file grants none of it):

* A driver is a component, not a grant. Construction, compilation and sending
  are not admission, not an account selection and not a retry policy.
* ``A`` (``lease_broker`` / ``go_lease_gateway``) stays the only admission,
  intent, effect, usage and settlement owner. The driver never writes A's
  request record, terminal receipt, cost ledger or a provider cooldown file.
* No listener, daemon, queue, state store, credential store or catalogue.
  Realm, protocol, endpoint, broker pool and permitted models are fixed at
  construction from the shared owners and are not caller-selectable.
* Exactly one POST is attempted per permitted call: no retry, no failover, no
  account rotation, no redirect, no proxy reroute and no resend after any
  exception.

Required incumbent join order (the owner composes this, not the driver):

1. stable private authentication and a bounded request identity;
2. A's original ``recover_application`` (terminal/pending/unknown never sends);
3. ``prepare_request`` — pure compile/freeze, before any intent is recorded;
4. A's ``begin`` selects the exact account;
5. ``preflight_account`` — account-specific checks on that account only;
6. A's ``prepare`` records the original intent;
7. ``send_prepared`` — one POST;
8. the original handler calls ``complete_application`` or
   ``mark_application_unknown``;
9. independent downstream delivery/close.

The existing A/B join can project a source-sealed HTTP recipe into its same
application request owner. This driver supplies no application permission or
availability: native generation, enrollment, current grant and real-path
qualification remain separate requirements. A flat generation supplies the
verified projection bytes and manifest digest; repository-only construction
retains the reviewed shared realm owner.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

SCHEMA = "mastermind.application_http_transports.v1"

RESPONSES_PROTOCOL = "responses"

# Closed, source-bounded limits. These bound the compiled request, the observed
# response and the single send; they are not provider policy.
MAX_LOGICAL_BYTES = 1024 * 1024
MAX_WIRE_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_MESSAGES = 256
MAX_MESSAGE_CHARS = 65536
MAX_TOOLS = 64
MAX_TOOL_SCHEMA_BYTES = 65536
MAX_OUTPUT_TOKENS = 65536
# An observed token count must be an actual integer in 0..10**12; anything
# else (bool, float, negative, out of range, missing) stays unknown.
MAX_TOKEN_VALUE = 10 ** 12
MAX_TIMEOUT_SECONDS = 600.0
MIN_TIMEOUT_SECONDS = 0.05

_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}")
_TOOL_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
_TOOL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")

USER_AGENT = "mastermind-application-responses-transport/1"

_LOGICAL_FIELDS = frozenset({
    "model", "messages", "tools", "tool_choice", "max_tokens", "stream",
})
_OUTPUT_CONTROL_FIELDS = frozenset({
    "temperature", "top_p", "stop", "presence_penalty", "frequency_penalty",
    "seed", "n", "response_format", "logprobs", "logprobs_top_k", "top_logprobs",
    "parallel_tool_calls", "stream_options", "max_completion_tokens", "reasoning",
    "modalities", "store", "background", "include", "truncation",
    "previous_response_id", "metadata", "user", "service_tier",
    "safety_identifier", "prompt_cache_key", "extra_body",
})
_TOOL_CHOICE_NAMES = frozenset({"auto", "none", "required"})


class TransportRefused(ValueError):
    """A bounded refusal. Never a provider, credential or path diagnostic."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


# ── closed JSON handling ─────────────────────────────────────────────────────


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise TransportRefused("closed_json_refused", "duplicate_key")
        value[key] = item
    return value


def _constant(_value):
    raise TransportRefused("nonfinite_value")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise TransportRefused("closed_json_refused") from None


def _reject_nonfinite(value: Any, depth: int = 0) -> None:
    if depth > 64:
        raise TransportRefused("request_too_large")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TransportRefused("nonfinite_value")
    elif isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_nonfinite(item, depth + 1)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ── owner-supplied I/O contract ──────────────────────────────────────────────


@dataclass(frozen=True)
class TransportRequest:
    """One owner-supplied POST. The driver never builds its own socket.

    ``timeout_seconds`` is a bounded relative budget computed from the
    remaining original permit lifetime at dispatch. ``deadline_seconds`` is
    that same original permit expiry exposed as an absolute wall-clock value:
    the I/O owner may enforce the whole exchange against it, and remains
    solely responsible for doing so. Neither value proves cancellation or the
    absence of upstream effects; the owner's I/O owns that truth.
    """

    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes
    timeout_seconds: float
    allow_redirects: bool
    use_environment_proxy: bool
    deadline_seconds: Optional[float] = None


@dataclass(frozen=True)
class TransportResponse:
    """One complete final HTTP response as the owner observed it.

    ``framing_complete`` is the owner's assertion that the status line, headers
    and body were read whole. ``final_url`` is the URL the response actually
    came from; a value other than the fixed endpoint means a redirect was
    followed and the effect left the admitted destination.
    """

    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str
    framing_complete: bool
    declared_content_length: Optional[int] = None


# ── compiled call, permit and account binding ────────────────────────────────


@dataclass(frozen=True)
class CompiledCall:
    """An immutable compiled call: logical digest plus exact native wire bytes.

    Compiled before A records intent and never mutated afterwards. The logical
    digest identifies the original application payload; the wire digest
    identifies the exact bytes that will be POSTed. They are never conflated.
    """

    driver_id: str
    realm_id: str
    provider: str
    pool: str
    endpoint: str
    protocol: str
    model: str
    logical_payload_digest: str
    wire_body: bytes
    wire_body_digest: str
    max_output_tokens: Optional[int]


@dataclass(frozen=True)
class DispatchPermit:
    """The frozen original permit context handed over by the incumbent owner.

    ``dispatch_permitted``, ``request_digest``, ``logical_payload_digest`` and
    ``wire_body_digest`` come from A's own request record: root's join must
    bind the compiled logical digest AND the exact expected native wire digest
    into the same A record that already holds the original request digest.
    ``expires_at`` is the immutable original expiry — no callback extends it
    and no replacement permit is minted. ``request_digest`` (A's original
    recovery identity), ``logical_payload_digest`` (application payload) and
    ``wire_body_digest`` (exact native wire bytes) stay separate values.
    """

    dispatch_id: str
    request_digest: str
    logical_payload_digest: str
    wire_body_digest: str
    account: str
    model: str
    lease_id: str
    expires_at: float
    dispatch_permitted: bool


@dataclass(frozen=True)
class AccountBinding:
    """The already-selected account and its owner-bound credential loader.

    ``credential_loader`` is the caller's existing owner-bound loader for that
    exact account. The driver never accepts a user-supplied key, never reads a
    key file, never infers an account and never calls pick/select.
    """

    account: str
    credential_loader: Callable[[str], str]
    eligibility: Optional[Callable[[str], None]] = None


@dataclass(frozen=True)
class TransportObservation:
    """What the driver observed. Settlement stays with the incumbent A handler.

    ``disposition`` is the only authority: ``complete`` means a complete final
    HTTP response was observed; ``unknown`` means the effect is ambiguous and
    the original request must remain pending/unknown. A local error is never a
    terminal HTTP status. ``served_model``/``usage`` are observed upstream
    evidence carried independently of answer normalization: a known error or a
    non-answer outcome still reports what the upstream actually declared
    (unknown fields stay ``None``, never zero-filled, never filled from the
    requested model). Settlement of observed usage stays with the incumbent
    owner; this observation writes no accounting record.
    """

    driver_id: str
    dispatch_id: str
    account: str
    model: str
    disposition: str
    result_status: str
    upstream_status: Optional[int]
    upstream_body_sha256: Optional[str]
    normalized: Optional[Dict[str, Any]]
    normalized_sha256: Optional[str]
    served_model: Optional[str]
    served_model_known: bool
    usage: Dict[str, Optional[int]]
    reason: Optional[str]


# ── the fixed native identity ────────────────────────────────────────────────


@dataclass(frozen=True)
class DriverIdentity:
    driver_id: str
    realm_id: str
    provider: str
    pool: str
    base_url: str
    endpoint: str
    protocol: str
    env_key: str
    default_model: Optional[str]
    allowed_models: frozenset


def _shared_realm(realm_id: str):
    """Resolve the reviewed realm and protocol from the shared owners only."""
    try:
        from control_plane.codex_provider_realm import REVIEWED_CODEX_PROVIDER_REALMS
        from control_plane.provider_protocols import validate_provider_protocol
    except Exception:
        raise TransportRefused("realm_owner_unavailable", realm_id) from None
    realm = REVIEWED_CODEX_PROVIDER_REALMS.get(realm_id)
    if realm is None:
        raise TransportRefused("realm_owner_unavailable", realm_id)
    try:
        protocol = validate_provider_protocol(realm.wire_api)
    except Exception:
        raise TransportRefused("unsupported_wire_protocol", realm_id) from None
    if protocol != RESPONSES_PROTOCOL:
        raise TransportRefused("unsupported_wire_protocol", realm_id)
    return realm, protocol


# ── request compiler ─────────────────────────────────────────────────────────


def _text_parts(message: Mapping[str, Any], index: int) -> List[str]:
    """Exact text parts of one chat message. Unknown blocks are refused."""
    content = message.get("content")
    if content is None:
        return []
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = []
        for part in content:
            if (not isinstance(part, dict) or set(part) != {"type", "text"}
                    or part.get("type") != "text" or not isinstance(part.get("text"), str)):
                raise TransportRefused("unsupported_content_part", str(index))
            parts.append(part["text"])
    else:
        raise TransportRefused("unsupported_content_part", str(index))
    for text in parts:
        if len(text) > MAX_MESSAGE_CHARS:
            raise TransportRefused("message_too_large", str(index))
        if "\x00" in text:
            raise TransportRefused("invalid_text", str(index))
    return parts


def _tool_calls(message: Mapping[str, Any], index: int, seen: set) -> List[Dict[str, Any]]:
    calls = message.get("tool_calls")
    if calls is None:
        return []
    if not isinstance(calls, list):
        raise TransportRefused("invalid_tool_calls", str(index))
    out: List[Dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"id", "type", "function"}:
            raise TransportRefused("invalid_tool_call", str(index))
        if call["type"] != "function":
            raise TransportRefused("unsupported_tool_call_type", str(index))
        call_id = call["id"]
        if not isinstance(call_id, str) or _TOOL_ID_RE.fullmatch(call_id) is None:
            raise TransportRefused("invalid_tool_call_id", str(index))
        if call_id in seen:
            raise TransportRefused("tool_call_duplicate", call_id)
        seen.add(call_id)
        function = call["function"]
        if not isinstance(function, dict) or set(function) - {"name", "arguments"}:
            raise TransportRefused("invalid_tool_call", str(index))
        name = function.get("name")
        if not isinstance(name, str) or _TOOL_NAME_RE.fullmatch(name) is None:
            raise TransportRefused("invalid_tool_name", str(index))
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise TransportRefused("invalid_tool_arguments", call_id)
        try:
            parsed = json.loads(arguments, object_pairs_hook=_pairs,
                                parse_constant=_constant)
        except TransportRefused:
            raise TransportRefused("invalid_tool_arguments", call_id) from None
        except (ValueError, TypeError, RecursionError):
            raise TransportRefused("invalid_tool_arguments", call_id) from None
        if not isinstance(parsed, dict):
            raise TransportRefused("invalid_tool_arguments", call_id)
        out.append({"type": "function_call", "call_id": call_id,
                    "name": name, "arguments": arguments})
    return out


def _tool_output(message: Mapping[str, Any], index: int, seen: set, answered: set) -> Dict[str, Any]:
    if set(message) - {"role", "tool_call_id", "content", "name"}:
        raise TransportRefused("invalid_tool_message", str(index))
    call_id = message.get("tool_call_id")
    if not isinstance(call_id, str) or _TOOL_ID_RE.fullmatch(call_id) is None:
        raise TransportRefused("invalid_tool_call_id", str(index))
    if call_id not in seen:
        raise TransportRefused("tool_call_unpaired", call_id)
    if call_id in answered:
        raise TransportRefused("tool_call_replayed", call_id)
    answered.add(call_id)
    content = message.get("content")
    if not isinstance(content, str):
        raise TransportRefused("invalid_tool_result", call_id)
    if len(content) > MAX_MESSAGE_CHARS:
        raise TransportRefused("message_too_large", str(index))
    if "\x00" in content:
        raise TransportRefused("invalid_text", str(index))
    return {"type": "function_call_output", "call_id": call_id, "output": content}


def _tools(logical: Mapping[str, Any]) -> List[Dict[str, Any]]:
    tools = logical.get("tools")
    if tools is None:
        return []
    if not isinstance(tools, list):
        raise TransportRefused("invalid_tools")
    if len(tools) > MAX_TOOLS:
        raise TransportRefused("too_many_tools")
    out: List[Dict[str, Any]] = []
    names: set = set()
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) != {"type", "function"}:
            raise TransportRefused("invalid_tool_schema")
        if tool["type"] != "function":
            raise TransportRefused("unsupported_tool_type")
        function = tool["function"]
        if not isinstance(function, dict) or set(function) - {"name", "description", "parameters", "strict"}:
            raise TransportRefused("invalid_tool_schema")
        name = function.get("name")
        if not isinstance(name, str) or _TOOL_NAME_RE.fullmatch(name) is None:
            raise TransportRefused("invalid_tool_name")
        if name in names:
            raise TransportRefused("tool_duplicate", name)
        names.add(name)
        entry: Dict[str, Any] = {"type": "function", "name": name}
        description = function.get("description")
        if description is not None:
            if not isinstance(description, str) or len(description) > MAX_MESSAGE_CHARS:
                raise TransportRefused("invalid_tool_schema")
            entry["description"] = description
        parameters = function.get("parameters")
        if parameters is not None:
            if not isinstance(parameters, dict):
                raise TransportRefused("invalid_tool_schema")
            if len(_canonical(parameters)) > MAX_TOOL_SCHEMA_BYTES:
                raise TransportRefused("tool_schema_too_large")
            entry["parameters"] = parameters
        strict = function.get("strict")
        if strict is not None:
            if type(strict) is not bool:
                raise TransportRefused("invalid_tool_schema")
            entry["strict"] = strict
        out.append(entry)
    return out


def _tool_choice(logical: Mapping[str, Any], tools: List[Dict[str, Any]]) -> Optional[Any]:
    choice = logical.get("tool_choice")
    if choice is None:
        return None
    if isinstance(choice, str):
        if choice not in _TOOL_CHOICE_NAMES:
            raise TransportRefused("unsupported_tool_choice")
        return choice
    if isinstance(choice, dict):
        if set(choice) != {"type", "function"} or choice.get("type") != "function":
            raise TransportRefused("unsupported_tool_choice")
        function = choice.get("function")
        if not isinstance(function, dict) or set(function) != {"name"}:
            raise TransportRefused("unsupported_tool_choice")
        name = function.get("name")
        if not isinstance(name, str) or name not in {tool["name"] for tool in tools}:
            raise TransportRefused("tool_choice_unknown")
        return {"type": "function", "name": name}
    raise TransportRefused("unsupported_tool_choice")


def _input_items(logical: Mapping[str, Any]) -> List[Dict[str, Any]]:
    messages = logical.get("messages")
    if not isinstance(messages, list) or not messages:
        raise TransportRefused("invalid_messages")
    if len(messages) > MAX_MESSAGES:
        raise TransportRefused("too_many_messages")
    items: List[Dict[str, Any]] = []
    declared: set = set()
    answered: set = set()
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise TransportRefused("invalid_message", str(index))
        role = message.get("role")
        if role in ("system", "user"):
            if set(message) - {"role", "content"}:
                raise TransportRefused("unsupported_message_field", str(index))
            parts = _text_parts(message, index)
            if not parts:
                raise TransportRefused("missing_content", str(index))
            items.append({"role": role,
                          "content": [{"type": "input_text", "text": part} for part in parts]})
        elif role == "assistant":
            if set(message) - {"role", "content", "tool_calls", "name"}:
                raise TransportRefused("unsupported_message_field", str(index))
            parts = _text_parts(message, index)
            calls = _tool_calls(message, index, declared)
            if parts:
                items.append({"role": "assistant",
                              "content": [{"type": "output_text", "text": part} for part in parts]})
            elif not calls:
                raise TransportRefused("empty_message", str(index))
            items.extend(calls)
        elif role == "tool":
            items.append(_tool_output(message, index, declared, answered))
        else:
            raise TransportRefused("unsupported_message_role", str(index))
    return items


def _token_value(value: Any) -> Optional[int]:
    """An actual token count: ``int`` in 0..MAX_TOKEN_VALUE, nothing else.

    ``bool``, ``float``, negative and out-of-range values, ``None`` and every
    other shape stay unknown (``None``) — never zero-filled, never guessed.
    """
    if type(value) is not int or value < 0 or value > MAX_TOKEN_VALUE:
        return None
    return value


def _usage_evidence(document: Any) -> Dict[str, Optional[int]]:
    """Observed token usage of a parsed upstream document, partial-tolerant."""
    usage = document.get("usage") if isinstance(document, dict) else None
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None}
    return {"input_tokens": _token_value(usage.get("input_tokens")),
            "output_tokens": _token_value(usage.get("output_tokens"))}


def _serving_model(document: Any) -> Tuple[Optional[str], bool]:
    """The actually served model of a parsed upstream document, if declared.

    Never filled from the requested or bound model and never aliased; a
    mismatch with the request is preserved as the honest observation it is.
    """
    if not isinstance(document, dict):
        return None, False
    model = document.get("model")
    if isinstance(model, str) and model:
        return model, True
    return None, False


def _normalize_responses(document: Any) -> Optional[Dict[str, Any]]:
    """Normalize a proven complete Responses output; None when unproven.

    Only the closed supported subset is normalized: assistant text and
    function calls. An unknown output item, an incomplete status or an error
    body yields None, so the caller sees a truthful protocol outcome instead
    of a guessed answer.
    """
    if not isinstance(document, dict):
        return None
    if document.get("status") != "completed":
        return None
    if document.get("error") is not None or document.get("incomplete_details") is not None:
        return None
    output = document.get("output")
    if not isinstance(output, list):
        return None
    texts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            return None
        kind = item.get("type")
        if kind == "message":
            if item.get("role") != "assistant" or not isinstance(item.get("content"), list):
                return None
            for part in item["content"]:
                if (not isinstance(part, dict) or part.get("type") != "output_text"
                        or not isinstance(part.get("text"), str)):
                    return None
                texts.append(part["text"])
        elif kind == "function_call":
            call_id = item.get("call_id")
            name = item.get("name")
            arguments = item.get("arguments")
            if (not isinstance(call_id, str) or not isinstance(name, str)
                    or not isinstance(arguments, str)):
                return None
            tool_calls.append({"id": call_id, "type": "function",
                               "function": {"name": name, "arguments": arguments}})
        else:
            return None
    served_model, served_model_known = _serving_model(document)
    return {
        "text": "".join(texts),
        "tool_calls": tool_calls,
        "served_model": served_model,
        "served_model_known": served_model_known,
        "usage": _usage_evidence(document),
    }


# ── the fixed drivers ────────────────────────────────────────────────────────


class _FixedResponsesDriver:
    """Shared implementation of the two fixed native Responses realms.

    Subclasses fix the realm, the broker pool and the permitted model
    identifiers. Nothing here accepts a caller-chosen endpoint, provider,
    pool, protocol or model set.
    """

    driver_id = ""
    realm_id = ""
    pool = ""
    allowed_models: frozenset = frozenset()
    default_model: Optional[str] = None

    def __init__(self, *, transport: Callable[[TransportRequest], TransportResponse],
                 clock: Callable[[], float] = time.time,
                 max_timeout_seconds: float = MAX_TIMEOUT_SECONDS,
                 realm_projection: Optional[bytes] = None,
                 projection_sha256: Optional[str] = None):
        if realm_projection is None and projection_sha256 is None:
            # Repository callers retain their reviewed shared owner. A flat
            # generation always supplies BOTH sealed inputs and never takes
            # this branch, including after a malformed projection.
            realm, protocol = _shared_realm(self.realm_id)
        else:
            try:
                from application_http_realm_projection import validate_projection
                document = validate_projection(realm_projection, expected_sha256=projection_sha256)
                matches = [row for row in document["drivers"] if row["driver_id"] == self.driver_id]
                if len(matches) != 1:
                    raise ValueError("driver inventory differs")
                row = matches[0]
                if (row["realm_id"] != self.realm_id or row["pool"] != self.pool
                        or frozenset(row["allowed_models"]) != self.allowed_models
                        or row["default_model"] != self.default_model):
                    raise ValueError("driver declaration differs")
                realm = SimpleNamespace(realm_id=row["realm_id"], provider_alias=row["provider"],
                    base_url=row["base_url"], env_key=row["env_key"])
                protocol = row["protocol"]
            except Exception:
                raise TransportRefused("sealed_realm_refused", self.realm_id) from None
        if (type(max_timeout_seconds) is not float and type(max_timeout_seconds) is not int) \
                or isinstance(max_timeout_seconds, bool) \
                or not math.isfinite(max_timeout_seconds) \
                or not MIN_TIMEOUT_SECONDS <= max_timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise TransportRefused("invalid_timeout_bound")
        if not callable(transport):
            raise TransportRefused("transport_owner_unavailable")
        self._transport = transport
        self._clock = clock
        self._max_timeout = float(max_timeout_seconds)
        self._consumed: set = set()
        self._claim_lock = threading.Lock()
        self._identity = DriverIdentity(
            driver_id=self.driver_id,
            realm_id=realm.realm_id,
            provider=realm.provider_alias,
            pool=self.pool,
            base_url=realm.base_url,
            endpoint=realm.base_url + "/responses",
            protocol=protocol,
            env_key=realm.env_key,
            default_model=self.default_model,
            allowed_models=frozenset(self.allowed_models),
        )

    # -- identity ---------------------------------------------------------
    @property
    def identity(self) -> DriverIdentity:
        return self._identity

    # -- compile ----------------------------------------------------------
    def prepare_request(self, logical_request: Any) -> CompiledCall:
        """Compile one logical application request into frozen native bytes.

        Pure: no provider I/O, no credential lookup, no admission and no
        persistent write. Every unsupported or ambiguous shape is refused here,
        before any intent is recorded.
        """
        logical = self._logical_payload(logical_request)
        model = self._model(logical)
        body: Dict[str, Any] = {"model": model, "input": _input_items(logical),
                                 "stream": False}
        tools = _tools(logical)
        if tools:
            body["tools"] = tools
        choice = _tool_choice(logical, tools)
        if choice is not None:
            body["tool_choice"] = choice
        max_output_tokens = self._max_output_tokens(logical)
        if max_output_tokens is not None:
            body["max_output_tokens"] = max_output_tokens
        wire = _canonical(body)
        if len(wire) > MAX_WIRE_BYTES:
            raise TransportRefused("request_too_large")
        return CompiledCall(
            driver_id=self._identity.driver_id,
            realm_id=self._identity.realm_id,
            provider=self._identity.provider,
            pool=self._identity.pool,
            endpoint=self._identity.endpoint,
            protocol=self._identity.protocol,
            model=model,
            logical_payload_digest=_sha256(_canonical(logical)),
            wire_body=wire,
            wire_body_digest=_sha256(wire),
            max_output_tokens=max_output_tokens,
        )

    def _logical_payload(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
            if len(raw) > MAX_LOGICAL_BYTES:
                raise TransportRefused("request_too_large")
            try:
                parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                                    parse_constant=_constant)
            except TransportRefused:
                raise
            except (ValueError, TypeError, UnicodeError, RecursionError):
                raise TransportRefused("closed_json_refused") from None
        elif isinstance(value, dict):
            parsed = value
        else:
            raise TransportRefused("invalid_logical_request")
        if not isinstance(parsed, dict):
            raise TransportRefused("invalid_logical_request")
        _reject_nonfinite(parsed)
        if len(_canonical(parsed)) > MAX_LOGICAL_BYTES:
            raise TransportRefused("request_too_large")
        for field in parsed:
            if field in _LOGICAL_FIELDS:
                continue
            if field in _OUTPUT_CONTROL_FIELDS:
                raise TransportRefused("unsupported_output_control", str(field))
            raise TransportRefused("unsupported_request_field", str(field))
        if "stream" in parsed and parsed["stream"] is not False:
            raise TransportRefused("streaming_unsupported")
        return parsed

    def _model(self, logical: Mapping[str, Any]) -> str:
        model = logical.get("model")
        if model is None:
            if self.default_model is None:
                raise TransportRefused("model_required")
            model = self.default_model
        if not isinstance(model, str) or not model:
            raise TransportRefused("model_required")
        if _MODEL_RE.fullmatch(model) is None:
            raise TransportRefused("invalid_model")
        if model not in self._identity.allowed_models:
            raise TransportRefused("model_not_qualified", model)
        return model

    @staticmethod
    def _max_output_tokens(logical: Mapping[str, Any]) -> Optional[int]:
        if "max_tokens" not in logical:
            return None
        value = logical["max_tokens"]
        if type(value) is not int or not 1 <= value <= MAX_OUTPUT_TOKENS:
            raise TransportRefused("invalid_max_tokens")
        return value

    # -- account preflight ------------------------------------------------
    def preflight_account(self, compiled: CompiledCall, binding: AccountBinding) -> None:
        """Account-specific checks on the already-selected account only.

        Never selects, reserves, rotates or infers an account, and never calls
        the incumbent owner's ``pick``.
        """
        if not isinstance(compiled, CompiledCall) or compiled.driver_id != self._identity.driver_id:
            raise TransportRefused("driver_mismatch")
        if not isinstance(binding, AccountBinding):
            raise TransportRefused("invalid_account_binding")
        if not isinstance(binding.account, str) or _ID_RE.fullmatch(binding.account) is None:
            raise TransportRefused("invalid_account_binding")
        if not callable(binding.credential_loader):
            raise TransportRefused("credential_owner_unavailable")
        if binding.eligibility is not None:
            if not callable(binding.eligibility):
                raise TransportRefused("invalid_account_binding")
            try:
                binding.eligibility(binding.account)
            except TransportRefused:
                raise
            except SystemExit:
                # The incumbent owner signals its bounded fail-closed exit with
                # SystemExit; it becomes a bounded refusal, never a crash.
                raise TransportRefused("account_not_eligible", binding.account) from None
            except Exception:
                raise TransportRefused("account_not_eligible", binding.account) from None

    # -- the single send ---------------------------------------------------
    def preflight_credential(self, compiled: CompiledCall, binding: AccountBinding) -> None:
        """Validate the selected account's actual owner credential before intent.

        Discard the private value immediately. send_prepared independently
        loads it again after the durable original permit, so revocation or
        replacement cannot borrow this earlier check or extend its lifetime.
        """
        self.preflight_account(compiled, binding)
        self._credential(binding, binding.account)

    def send_prepared(self, compiled: CompiledCall, permit: DispatchPermit,
                      binding: AccountBinding) -> TransportObservation:
        """POST the frozen bytes once, on the bound account, and observe it.

        The permit is the frozen original context: without it there is no
        effect. A mutated body, model, account or an expired permit is refused
        before any POST. Identity, the original expiry and the once-only
        claim are all fenced before any owner callback runs, and the remaining
        lifetime is recomputed immediately before the only I/O invocation —
        after the eligibility and credential callbacks — so a slow callback
        can never spend lifetime the original permit no longer has. The expiry
        is never extended and no replacement permit is created. The in-memory
        claim is acquired atomically before any callback can reenter this
        path and is never released afterwards, including after a callback
        failure or an expired recheck; a genuine re-send needs a new original
        A dispatch. It complements A's durable first-use fence and, after a
        reconstruction, authorizes nothing by itself — A's durable fence stays
        authoritative. A local refusal or error after durable A intent stays
        pending/unknown; no HTTP status is fabricated to release capacity.
        """
        self._check_identity(compiled, permit, binding)
        remaining = permit.expires_at - float(self._clock())
        if remaining <= 0:
            raise TransportRefused("permit_expired")
        if remaining < MIN_TIMEOUT_SECONDS:
            raise TransportRefused("permit_expired")
        # Atomic once-only claim: acquired before any callback can reenter
        # the send path, so a duplicate or reentrant original dispatch
        # refuses without a second credential action or transport call.
        self._claim_dispatch(permit.dispatch_id)
        self.preflight_account(compiled, binding)
        credential = self._credential(binding, permit.account)
        # The original expiry is immutable. Recheck the clock now — after all
        # callbacks and credential work — and bound the timeout by the
        # remaining original lifetime at dispatch, never by a stale value.
        remaining = permit.expires_at - float(self._clock())
        if remaining <= 0:
            raise TransportRefused("permit_expired")
        timeout = min(self._max_timeout, remaining)
        if timeout < MIN_TIMEOUT_SECONDS:
            raise TransportRefused("permit_expired")
        request = TransportRequest(
            method="POST",
            url=self._identity.endpoint,
            headers={
                "Authorization": "Bearer " + credential,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            body=compiled.wire_body,
            timeout_seconds=timeout,
            allow_redirects=False,
            use_environment_proxy=False,
            deadline_seconds=float(permit.expires_at),
        )
        try:
            response = self._transport(request)
        except Exception:
            return self._unknown(compiled, permit, "transport_exception")
        return self._observe(compiled, permit, response)

    def _claim_dispatch(self, dispatch_id: str) -> None:
        """Atomically claim the one permitted send of this dispatch.

        The claim is a bounded in-memory complement of A's durable first-use
        fence. It is acquired exactly once and never cleared — not after a
        callback failure, not after an expired recheck, not after an unknown
        effect — because a second send of the same original dispatch is
        forbidden without fresh original-owner recovery.
        """
        with self._claim_lock:
            if dispatch_id in self._consumed:
                raise TransportRefused("dispatch_already_consumed")
            self._consumed.add(dispatch_id)

    def _check_identity(self, compiled: CompiledCall, permit: DispatchPermit,
                        binding: AccountBinding) -> None:
        if not isinstance(compiled, CompiledCall):
            raise TransportRefused("invalid_compiled_call")
        if compiled.driver_id != self._identity.driver_id:
            raise TransportRefused("driver_mismatch")
        if compiled.endpoint != self._identity.endpoint:
            raise TransportRefused("driver_mismatch")
        if not isinstance(permit, DispatchPermit):
            raise TransportRefused("invalid_permit")
        if permit.dispatch_permitted is not True:
            raise TransportRefused("dispatch_not_permitted")
        for value, label in ((permit.dispatch_id, "dispatch_id"),
                             (permit.account, "account"),
                             (permit.lease_id, "lease_id"),
                             (permit.model, "model")):
            if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
                raise TransportRefused("invalid_permit", label)
        for value, label in ((permit.request_digest, "request_digest"),
                             (permit.logical_payload_digest, "logical_payload_digest"),
                             (permit.wire_body_digest, "wire_body_digest")):
            if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
                raise TransportRefused("invalid_permit", label)
        if (isinstance(permit.expires_at, bool)
                or not isinstance(permit.expires_at, (int, float))
                or not math.isfinite(permit.expires_at)):
            raise TransportRefused("invalid_permit", "expires_at")
        # The compiled call must carry the same fixed identity the driver
        # resolved from the shared owners — never a caller-chosen destination
        # or a mutable alias.
        for value, label in ((compiled.realm_id, "realm_id"),
                             (compiled.provider, "provider"),
                             (compiled.pool, "pool"),
                             (compiled.protocol, "protocol"),
                             (compiled.endpoint, "endpoint")):
            if value != getattr(self._identity, label):
                raise TransportRefused("driver_mismatch", label)
        if not isinstance(binding, AccountBinding):
            raise TransportRefused("invalid_account_binding")
        if binding.account != permit.account:
            raise TransportRefused("account_mismatch")
        if compiled.model != permit.model:
            raise TransportRefused("model_mismatch")
        if compiled.logical_payload_digest != permit.logical_payload_digest:
            raise TransportRefused("logical_digest_mismatch")
        # The expected wire material is bound to the original permit: the
        # compiled call's self-recorded digest must equal the owner-recorded
        # expected digest, and the actual bytes must hash to it. Replacing
        # the bytes together with their recomputed self-hash cannot pass.
        if compiled.wire_body_digest != permit.wire_body_digest:
            raise TransportRefused("wire_digest_mismatch")
        if _sha256(compiled.wire_body) != permit.wire_body_digest:
            raise TransportRefused("wire_body_mutated")

    def _credential(self, binding: AccountBinding, account: str) -> str:
        try:
            value = binding.credential_loader(account)
        except SystemExit:
            # The incumbent owner signals an unavailable credential with a
            # bounded fail-closed exit; it becomes a bounded refusal.
            raise TransportRefused("credential_unavailable", account) from None
        except Exception:
            raise TransportRefused("credential_unavailable", account) from None
        if not isinstance(value, str):
            raise TransportRefused("credential_unavailable", account)
        value = value.strip()
        if not value or len(value) > 4096 or any(ch in value for ch in "\r\n\x00"):
            raise TransportRefused("credential_unavailable", account)
        return value

    def _unknown(self, compiled: CompiledCall, permit: DispatchPermit,
                 reason: str) -> TransportObservation:
        return TransportObservation(
            driver_id=self._identity.driver_id,
            dispatch_id=permit.dispatch_id,
            account=permit.account,
            model=compiled.model,
            disposition="unknown",
            result_status="ambiguous",
            upstream_status=None,
            upstream_body_sha256=None,
            normalized=None,
            normalized_sha256=None,
            served_model=None,
            served_model_known=False,
            usage={"input_tokens": None, "output_tokens": None},
            reason=reason,
        )

    def _observe(self, compiled: CompiledCall, permit: DispatchPermit,
                 response: Any) -> TransportObservation:
        if not isinstance(response, TransportResponse):
            return self._unknown(compiled, permit, "invalid_transport_response")
        if not isinstance(response.final_url, str) or response.final_url != self._identity.endpoint:
            return self._unknown(compiled, permit, "upstream_redirect_refused")
        status = response.status
        if type(status) is not int or not 200 <= status <= 599:
            return self._unknown(compiled, permit, "upstream_no_final_status")
        if response.framing_complete is not True:
            return self._unknown(compiled, permit, "upstream_incomplete")
        body = response.body
        if not isinstance(body, (bytes, bytearray)):
            return self._unknown(compiled, permit, "invalid_transport_response")
        body = bytes(body)
        if len(body) > MAX_RESPONSE_BYTES:
            return self._unknown(compiled, permit, "upstream_response_too_large")
        if (response.declared_content_length is not None
                and response.declared_content_length != len(body)):
            return self._unknown(compiled, permit, "upstream_incomplete")
        digest = _sha256(body)
        # Strict closed parse of the complete bounded body. Duplicate keys,
        # nonfinite constants and malformed JSON leave the evidence unknown —
        # nothing is extracted from a document that failed the strict parse,
        # and no truncated or unproven body is ever parsed into a fabricated
        # complete response.
        document, parsed = self._parse_document(body)
        if status != 200:
            # A complete upstream error is a known terminal error. It is never
            # a retry trigger and never rotates the account. Its serving model
            # and usage — when the error body truthfully declares them — are
            # preserved even though no answer is normalized.
            return self._complete(compiled, permit, status, digest, "upstream_error",
                                  None, document, parsed)
        if not parsed:
            return self._complete(compiled, permit, status, digest,
                                  "upstream_protocol_error", None, document, parsed)
        normalized = _normalize_responses(document)
        if normalized is None:
            label = ("upstream_error" if isinstance(document, dict)
                     and document.get("error") is not None
                     else "upstream_incomplete_output")
            return self._complete(compiled, permit, status, digest, label,
                                  None, document, parsed)
        return self._complete(compiled, permit, status, digest, "ok",
                              normalized, document, parsed)

    @staticmethod
    def _parse_document(body: bytes) -> Tuple[Optional[Any], bool]:
        """Strict closed JSON parse: (document, parsed). Never partial."""
        try:
            document = json.loads(body.decode("utf-8"), object_pairs_hook=_pairs,
                                  parse_constant=_constant)
        except TransportRefused:
            return None, False
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return None, False
        return document, True

    def _complete(self, compiled: CompiledCall, permit: DispatchPermit, status: int,
                  digest: str, result_status: str,
                  normalized: Optional[Dict[str, Any]], document: Any = None,
                  parsed: bool = False) -> TransportObservation:
        normalized_sha = _sha256(_canonical(normalized)) if normalized is not None else None
        if normalized is not None:
            served_model = normalized.get("served_model")
            served_model_known = bool(normalized.get("served_model_known", False))
            usage = dict(normalized.get("usage")
                         or {"input_tokens": None, "output_tokens": None})
        else:
            # Model/usage observation is independent of answer normalization:
            # a known error or a non-answer outcome still carries the serving
            # model and usage the upstream actually reported (unknown fields
            # stay None). Root's shared owner settles known usage once; this
            # driver writes no accounting record and grants no replay.
            served_model, served_model_known = _serving_model(document if parsed else None)
            usage = _usage_evidence(document if parsed else None)
        return TransportObservation(
            driver_id=self._identity.driver_id,
            dispatch_id=permit.dispatch_id,
            account=permit.account,
            model=compiled.model,
            disposition="complete",
            result_status=result_status,
            upstream_status=status,
            upstream_body_sha256=digest,
            normalized=normalized,
            normalized_sha256=normalized_sha,
            served_model=served_model,
            served_model_known=served_model_known,
            usage=usage,
            reason=None,
        )


class MiniMaxResponsesDriver(_FixedResponsesDriver):
    """Fixed MiniMax Token Plan Responses transport.

    Realm ``minimax-token-plan`` (provider ``minimax``, base
    ``https://api.minimax.io/v1``), native broker pool ``minimax``. The only
    permitted model is ``MiniMax-M3``: the identifier the native
    ``codex_minimax`` configuration selects and the identifier recorded as
    requested and served in
    ``review_evidence/provider_realms/minimax_codex_responses_20260915.json``.
    That receipt proves transport reachability only — not a governed canary,
    capacity, usage policy, autonomous routing or application permission.
    """

    driver_id = "minimax-token-plan.responses"
    realm_id = "minimax-token-plan"
    pool = "minimax"
    allowed_models = frozenset({"MiniMax-M3"})
    default_model = None


class BailianResponsesDriver(_FixedResponsesDriver):
    """Fixed Alibaba Token Plan Responses transport.

    Realm ``alibaba-token-plan-sg`` (provider ``alibaba``, base
    ``https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1``),
    native broker pool ``bailian`` — the Alibaba realm is served by the
    incumbent ``bailian`` capacity pool, never by a new ``alibaba`` pool. The
    permitted models are ``qwen3.8-max`` (the native ``codex_bailian``
    selection) and ``qwen3.8-flash`` (the incumbent
    ``bailian_keys.effective_model`` default for an unspecified call). Explicit
    models are preserved verbatim; nothing is case-folded or substituted.
    """

    driver_id = "alibaba-token-plan-sg.responses"
    realm_id = "alibaba-token-plan-sg"
    pool = "bailian"
    allowed_models = frozenset({"qwen3.8-max", "qwen3.8-flash"})
    default_model = "qwen3.8-flash"


__all__ = [
    "SCHEMA",
    "AccountBinding",
    "BailianResponsesDriver",
    "CompiledCall",
    "DispatchPermit",
    "DriverIdentity",
    "MiniMaxResponsesDriver",
    "TransportObservation",
    "TransportRefused",
    "TransportRequest",
    "TransportResponse",
]
