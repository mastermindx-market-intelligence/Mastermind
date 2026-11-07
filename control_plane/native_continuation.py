"""Immutable native CONTINUE evidence over canonical Runtime and dialogue contracts.

No transport, callback, registry or lifecycle is owned here.

The native Secretary continuation contracts below describe the immutable
request/recovery projection of a native Secretary continuation. They are pure:
no registry, lifecycle, queue, receipt store, identity owner, transport or SQL
write is introduced. The existing Runtime owners remain the only durable
writers, and every native identifier here is a projection of an already
selected immutable composition.
"""
from __future__ import annotations
import hashlib
import json
import re
from typing import Any, NamedTuple, Protocol, runtime_checkable
from common.agent_dialogue_contract_v2 import normalize_context_v2
from control_plane.operator_harness_contract import runtime_binding_id_for
from control_plane.workstream_admission_contract import canonical_work_ref
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


# ---------------------------------------------------------------------------
# Native Secretary durable continuation (pure contracts)
# ---------------------------------------------------------------------------
#
# A native Secretary continuation has no Dialogue carrier, no Attempt lease and
# no worker. Its request is therefore a different immutable projection of the
# same Runtime aggregate family: the existing session_bridge_continue
# aggregate, the existing continue request command prefix and the existing
# continue commit command derivation are reused unchanged, so every existing
# owner that already understands a continuation request keeps seeing exactly
# one request Event on exactly one aggregate.

HERMES_BINDING_SCHEMA = "mastermind.session_bridge.hermes_secretary_binding.v1"
HERMES_TARGET_SCHEMA = "mastermind.session_bridge.hermes_secretary_target.v1"
HERMES_OPERATION_SCHEMA = "mastermind.session_bridge.hermes_secretary_operation.v1"
HERMES_REQUEST_SCHEMA = "mastermind.session_bridge.hermes_secretary_request.v1"
HERMES_COMMIT_SCHEMA = "mastermind.session_bridge.hermes_secretary_commit.v1"

HERMES_KIND = "hermes_secretary"
HERMES_META_KIND = "hermes_meta"


class HermesContinuationFamily(NamedTuple):
    """One closed schema/digest domain; no route, registry or authority."""
    kind: str
    binding_schema: str
    target_schema: str
    operation_schema: str
    request_schema: str
    commit_schema: str
    result_schema: str
    native_schema: str
    submission_prefix: str

    @property
    def target_prefix(self) -> str:
        return self.kind + ":"


_HERMES_FAMILIES = (
    HermesContinuationFamily(
        HERMES_KIND, HERMES_BINDING_SCHEMA, HERMES_TARGET_SCHEMA,
        HERMES_OPERATION_SCHEMA, HERMES_REQUEST_SCHEMA, HERMES_COMMIT_SCHEMA,
        "mastermind.session_bridge.hermes_secretary_result.v1",
        "mastermind.hermes_secretary_native_control/v1", "session-secretary-"),
    HermesContinuationFamily(
        HERMES_META_KIND, "mastermind.session_bridge.hermes_meta_binding.v1",
        "mastermind.session_bridge.hermes_meta_target.v1",
        "mastermind.session_bridge.hermes_meta_operation.v1",
        "mastermind.session_bridge.hermes_meta_request.v1",
        "mastermind.session_bridge.hermes_meta_commit.v1",
        "mastermind.session_bridge.hermes_meta_result.v1",
        "mastermind.hermes_meta_native_control/v1", "session-meta-"),
)
HERMES_KINDS = tuple(family.kind for family in _HERMES_FAMILIES)
HERMES_REQUEST_SCHEMAS = tuple(family.request_schema for family in _HERMES_FAMILIES)
HERMES_RESULT_SCHEMAS = tuple(family.result_schema for family in _HERMES_FAMILIES)
HERMES_TARGET_PREFIXES = tuple(family.target_prefix for family in _HERMES_FAMILIES)


def hermes_family(kind: str) -> HermesContinuationFamily:
    if type(kind) is str:
        for family in _HERMES_FAMILIES:
            if kind == family.kind:
                return family
    raise ValueError("native conversation kind is unsupported")


def hermes_family_for_schema(schema: str, *, component: str) -> HermesContinuationFamily:
    if (type(schema) is not str or type(component) is not str
            or component not in ("binding", "target", "operation", "request", "commit", "result", "native")):
        raise ValueError("native conversation schema is unsupported")
    for family in _HERMES_FAMILIES:
        if schema == getattr(family, component + "_schema"):
            return family
    raise ValueError("native conversation schema is unsupported")


def hermes_family_for_target(target_ref: str) -> HermesContinuationFamily:
    if type(target_ref) is not str or re.fullmatch(
            r"(hermes_secretary|hermes_meta):[0-9a-f]{64}", target_ref) is None:
        raise ValueError("native conversation target is malformed")
    return hermes_family(target_ref.split(":", 1)[0])


_HERMES_BINDING_KEYS = frozenset({
    "schema", "composition_sha256", "host_ref", "root_id", "root_job_id", "work_ref",
    "session_id", "profile_id", "principal_id", "expected_host_binding_sha256",
    "expected_implementation_sha"})
_HERMES_TARGET_KEYS = frozenset({
    "profile_id", "session_id", "principal_id", "instance_id",
    "authority_epoch", "revision", "execution_generation"})
_HERMES_REQUEST_KEYS = frozenset({
    "schema", "principal", "work_ref", "root_job_id", "root_event_id", "root_event_sha256",
    "target_ref", "target_generation", "operation_key", "binding", "binding_sha256",
    "input", "input_sha256", "native_request", "native_request_sha256",
    "native_input_sha256", "read_ref"})
_HERMES_COMMIT_KEYS = frozenset({
    "schema", "request_event_id", "request_event_sha256", "operation_key", "read_ref",
    "binding_sha256", "native_request_sha256", "native_input_sha256", "submission_id"})
_HERMES_NATIVE_REQUEST_KEYS = frozenset({"operation", "target", "submission_id", "text"})
_HERMES_INPUT_KEYS = frozenset({"instruction", "stop_condition"})

# The existing session_bridge continuation commit derivation. These mirror the
# literals owned by integrations/session_bridge/runtime_return.py; the Runtime
# reader proves that the aggregate Event and the global command index agree
# before either is used.
_HERMES_COMMIT_EVENT = "SESSION_BRIDGE_CONTINUE_COMMIT_STARTED"
_HERMES_COMMIT_PREFIX = "session-bridge-continue-commit:"
_LEGACY_NATIVE_COMMIT_EVENT = "SESSION_BRIDGE_NATIVE_REPLY_COMMIT_STARTED"

_HERMES_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HERMES_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_HERMES_HOST_REF = re.compile(r"^host-[0-9a-f]{64}$")
_HERMES_JOB_ID = re.compile(r"^JOB-[0-9]{1,9}$")

_HERMES_MAX_NATIVE_ID = 1024
_HERMES_MAX_INPUT_CODEPOINTS = 700
_HERMES_MAX_TEXT_BYTES = 16384
_HERMES_MAX_PAYLOAD_BYTES = 65536


def _hermes_native_id(value: Any) -> str:
    """Exact native identifier: nonempty, bounded, control-free, valid UTF-8."""
    if type(value) is not str or not value or len(value) > _HERMES_MAX_NATIVE_ID:
        raise ValueError("native Secretary identifier is malformed")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("native Secretary identifier is malformed")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("native Secretary identifier is malformed") from None
    return value


def _hermes_binding(value: Any) -> dict:
    """Validate the selected immutable composition binding."""
    if type(value) is not dict or set(value) != set(_HERMES_BINDING_KEYS):
        raise ValueError("native Secretary binding is malformed")
    hermes_family_for_schema(value["schema"], component="binding")
    for field in ("composition_sha256", "expected_host_binding_sha256"):
        item = value[field]
        if type(item) is not str or _HERMES_SHA256.fullmatch(item) is None:
            raise ValueError("native Secretary binding digest is malformed")
    item = value["expected_implementation_sha"]
    if type(item) is not str or _HERMES_SHA1.fullmatch(item) is None:
        raise ValueError("native Secretary binding digest is malformed")
    for field in ("host_ref", "root_id", "root_job_id", "work_ref"):
        item = value[field]
        if type(item) is not str or _TOKEN.fullmatch(item) is None:
            raise ValueError("native Secretary binding reference is malformed")
    if _HERMES_HOST_REF.fullmatch(value["host_ref"]) is None:
        raise ValueError("native Secretary binding host reference is malformed")
    if _HERMES_JOB_ID.fullmatch(value["root_job_id"]) is None:
        raise ValueError("native Secretary binding root job is malformed")
    canonical_work_ref(value["work_ref"])
    for field in ("session_id", "profile_id", "principal_id"):
        _hermes_native_id(value[field])
    return dict(value)


def _hermes_native_target(value: Any) -> dict:
    """Validate the native owner's own session target."""
    if type(value) is not dict or set(value) != set(_HERMES_TARGET_KEYS):
        raise ValueError("native Secretary target is malformed")
    for field in ("profile_id", "session_id", "principal_id", "instance_id"):
        _hermes_native_id(value[field])
    for field in ("authority_epoch", "revision", "execution_generation"):
        # ``type(...) is int`` rejects bool; a bool is never a real counter.
        if type(value[field]) is not int:
            raise ValueError("native Secretary target counter is malformed")
    if (value["authority_epoch"] < 1 or value["revision"] < 0
            or value["execution_generation"] < 0):
        raise ValueError("native Secretary target counter is malformed")
    return dict(value)


def _hermes_principal(value: Any) -> dict:
    """Validate the existing Office principal projection, unchanged."""
    if type(value) is not dict or set(value) != set(_IDENTITY):
        raise ValueError("native Secretary principal is malformed")
    for item in value.values():
        if type(item) is not str or not item or len(item) > 2048:
            raise ValueError("native Secretary principal is malformed")
    return dict(value)


def _hermes_principal_filter(value: Any) -> tuple[tuple[str, ...], ...]:
    """Accept one identity, or the trusted READ/SEND pair, in _IDENTITY order."""
    if type(value) is not tuple or not 1 <= len(value) <= 2:
        raise ValueError("native Secretary principal filter is required")
    for identity in value:
        if (type(identity) is not tuple or len(identity) != len(_IDENTITY)
                or any(type(item) is not str or not item for item in identity)):
            raise ValueError("native Secretary principal filter is malformed")
    if len(set(value)) != len(value):
        raise ValueError("native Secretary principal filter is ambiguous")
    if len(value) == 2 and value[0][1:] != value[1][1:]:
        raise ValueError("native Secretary principal filter is malformed")
    return value


def _hermes_input_text(value: Any) -> str:
    """Exact instruction text: nonblank, bounded, preserved verbatim."""
    if (type(value) is not str or not value.strip()
            or len(value) > _HERMES_MAX_INPUT_CODEPOINTS):
        raise ValueError("native Secretary instruction is malformed")
    return value


def _hermes_native_request(value: Any) -> dict:
    """Validate the native owner's own submission request."""
    if type(value) is not dict or set(value) != set(_HERMES_NATIVE_REQUEST_KEYS):
        raise ValueError("native Secretary native request is malformed")
    if value["operation"] != "submit":
        raise ValueError("native Secretary native request operation changed")
    _hermes_native_id(value["submission_id"])
    text = value["text"]
    if type(text) is not str or not text.strip():
        raise ValueError("native Secretary native request text is malformed")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("native Secretary native request text is malformed") from None
    if size > _HERMES_MAX_TEXT_BYTES:
        raise ValueError("native Secretary native request text is malformed")
    return dict(value)


def _hermes_target_material(binding: dict, root_event_id: int,
                             root_event_sha256: str, native_target: dict) -> dict:
    """The exact material that binds a native Secretary target.

    The Office principal is deliberately absent: the trusted READ/SEND pair
    must derive the same target from the same immutable composition.
    """
    family = hermes_family_for_schema(binding["schema"], component="binding")
    return {"schema": family.target_schema, "binding": binding,
            "root_event_id": root_event_id, "root_event_sha256": root_event_sha256,
            "native_target": native_target}


def _hermes_target_ref(target_digest: str, *, kind: str = HERMES_KIND) -> str:
    return hermes_family(kind).target_prefix + target_digest


def _hermes_operation_key(target_ref: str) -> str:
    family = hermes_family_for_target(target_ref)
    return "session-continue-" + _digest(
        {"schema": family.operation_schema, "target_ref": target_ref})


def _hermes_native_input_digest(text: str) -> str:
    """The native owner's own input digest; _digest is ASCII-only.

    ``_digest`` escapes non-ASCII text, so it cannot stand in for the native
    owner's digest of the same bytes.
    """
    return hashlib.sha256(json.dumps(
        {"text": text, "finite": True}, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _hermes_root_event(root_event: Any, binding: dict) -> Any:
    """Require the actual selected JOB_CREATED Event of the bound root."""
    from control_plane.executive_runtime import Event
    if not isinstance(root_event, Event):
        raise ValueError("native Secretary root Event is unavailable")
    if (root_event.event_type != "JOB_CREATED"
            or type(root_event.event_id) is not int or root_event.event_id < 1
            or root_event.job_id != binding["root_job_id"]
            or root_event.aggregate_type != "job"
            or root_event.aggregate_id != binding["root_job_id"]
            or type(root_event.sequence) is not int or root_event.sequence != 1
            or root_event.attempt_id is not None or root_event.worker_id is not None
            or root_event.quota_class is not None):
        raise ValueError("native Secretary root Event is malformed")
    return root_event


def _hermes_derived_target_from_material(material: dict) -> dict:
    """Derive the target, generation, operation and request keys together."""
    family = hermes_family_for_schema(material["binding"]["schema"], component="binding")
    if material["schema"] != family.target_schema:
        raise ValueError("native conversation target family changed")
    digest = _digest(material)
    target_ref = _hermes_target_ref(digest, kind=family.kind)
    operation_key = _hermes_operation_key(target_ref)
    return {"digest": digest, "target_ref": target_ref,
            "target_generation": digest[:24], "operation_key": operation_key,
            "request_key": _request_key(operation_key)}


def _hermes_derived_target(binding: dict, root_event: Any,
                            native_target: dict) -> dict:
    """Derive the target keys from the bound root and native target."""
    return _hermes_derived_target_from_material(_hermes_target_material(
        binding, root_event.event_id, _digest(root_event.to_dict()), native_target))


def build_hermes_continuation_target(*, binding: dict, root_event,
                                     native_target: dict) -> dict:
    """Derive the addressable native Secretary target from bound provenance."""
    binding = _hermes_binding(binding)
    native_target = _hermes_native_target(native_target)
    for field in ("profile_id", "session_id", "principal_id"):
        if native_target[field] != binding[field]:
            raise ValueError("native Secretary target does not match the binding")
    _hermes_root_event(root_event, binding)
    derived = _hermes_derived_target(binding, root_event, native_target)
    return {"kind": hermes_family_for_schema(binding["schema"], component="binding").kind,
            "target_ref": derived["target_ref"],
            "generation": derived["target_generation"],
            "addressable": True,
            "continuation_operation_key": derived["operation_key"],
            "work_ref": binding["work_ref"],
            "root_job_id": binding["root_job_id"]}


def build_hermes_continuation_request(*, principal: dict, binding: dict, root_event,
                                       native_target: dict, arguments: dict) -> dict:
    """Build the immutable native Secretary request payload."""
    binding = _hermes_binding(binding)
    family = hermes_family_for_schema(binding["schema"], component="binding")
    native_target = _hermes_native_target(native_target)
    principal = _hermes_principal(principal)
    _hermes_root_event(root_event, binding)
    if type(arguments) is not dict or set(arguments) != {
            "target_ref", "instruction", "stop_condition", "operation_key"}:
        raise ValueError("native Secretary arguments are malformed")
    derived = _hermes_derived_target(binding, root_event, native_target)
    if (arguments["target_ref"] != derived["target_ref"]
            or arguments["operation_key"] != derived["operation_key"]):
        raise ValueError("native Secretary arguments do not match the derived target")
    instruction = _hermes_input_text(arguments["instruction"])
    stop_condition = _hermes_input_text(arguments["stop_condition"])
    text = ("Instruction:\n" + instruction + "\n\nCompletion condition:\n" + stop_condition)
    native_request = {"operation": "submit", "target": dict(native_target),
                      "submission_id": family.submission_prefix + derived["request_key"],
                      "text": text}
    payload = {
        "schema": family.request_schema,
        "principal": principal,
        "work_ref": binding["work_ref"],
        "root_job_id": binding["root_job_id"],
        "root_event_id": root_event.event_id,
        "root_event_sha256": _digest(root_event.to_dict()),
        "target_ref": derived["target_ref"],
        "target_generation": derived["target_generation"],
        "operation_key": derived["operation_key"],
        "binding": binding,
        "binding_sha256": _digest(binding),
        "input": {"instruction": instruction, "stop_condition": stop_condition},
        "input_sha256": _digest({"instruction": instruction,
                                 "stop_condition": stop_condition}),
        "native_request": native_request,
        "native_request_sha256": _digest(native_request),
        "native_input_sha256": _hermes_native_input_digest(text),
        "read_ref": "session-reply-" + derived["request_key"],
    }
    return validate_hermes_continuation_request(payload)


def validate_hermes_continuation_request(value: Any) -> dict:
    """Validate the closed native Secretary request payload and detach it."""
    if type(value) is not dict or set(value) != set(_HERMES_REQUEST_KEYS):
        raise ValueError("native Secretary request is malformed")
    family = hermes_family_for_schema(value["schema"], component="request")
    principal = _hermes_principal(value["principal"])
    binding = _hermes_binding(value["binding"])
    if binding["schema"] != family.binding_schema:
        raise ValueError("native conversation request binding family changed")
    if value["binding_sha256"] != _digest(binding):
        raise ValueError("native Secretary request binding changed")
    source = value["input"]
    if type(source) is not dict or set(source) != set(_HERMES_INPUT_KEYS):
        raise ValueError("native Secretary request input is malformed")
    instruction = _hermes_input_text(source["instruction"])
    stop_condition = _hermes_input_text(source["stop_condition"])
    if value["input_sha256"] != _digest({"instruction": instruction,
                                         "stop_condition": stop_condition}):
        raise ValueError("native Secretary request input changed")
    native_request = _hermes_native_request(value["native_request"])
    native_target = _hermes_native_target(native_request["target"])
    for field in ("profile_id", "session_id", "principal_id"):
        if native_target[field] != binding[field]:
            raise ValueError("native Secretary request target does not match the binding")
    if type(value["root_event_id"]) is not int or value["root_event_id"] < 1:
        raise ValueError("native Secretary request root is malformed")
    if (type(value["root_event_sha256"]) is not str
            or _HERMES_SHA256.fullmatch(value["root_event_sha256"]) is None):
        raise ValueError("native Secretary request root is malformed")
    if (value["work_ref"] != binding["work_ref"]
            or value["root_job_id"] != binding["root_job_id"]):
        raise ValueError("native Secretary request scope changed")
    material = _hermes_target_material(
        binding, value["root_event_id"], value["root_event_sha256"], native_target)
    derived = _hermes_derived_target_from_material(material)
    if (value["target_ref"] != derived["target_ref"]
            or value["target_generation"] != derived["target_generation"]
            or value["operation_key"] != derived["operation_key"]
            or value["read_ref"] != "session-reply-" + derived["request_key"]):
        raise ValueError("native Secretary request derivation changed")
    if native_request["submission_id"] != family.submission_prefix + derived["request_key"]:
        raise ValueError("native Secretary request submission changed")
    text = ("Instruction:\n" + instruction + "\n\nCompletion condition:\n" + stop_condition)
    if native_request["text"] != text:
        raise ValueError("native Secretary request prompt changed")
    if value["native_request_sha256"] != _digest(native_request):
        raise ValueError("native Secretary request native digest changed")
    if value["native_input_sha256"] != _hermes_native_input_digest(text):
        raise ValueError("native Secretary request native input changed")
    detached = {
        "schema": family.request_schema,
        "principal": dict(principal),
        "work_ref": binding["work_ref"],
        "root_job_id": binding["root_job_id"],
        "root_event_id": value["root_event_id"],
        "root_event_sha256": value["root_event_sha256"],
        "target_ref": derived["target_ref"],
        "target_generation": derived["target_generation"],
        "operation_key": derived["operation_key"],
        "binding": dict(binding),
        "binding_sha256": value["binding_sha256"],
        "input": {"instruction": instruction, "stop_condition": stop_condition},
        "input_sha256": value["input_sha256"],
        "native_request": {"operation": native_request["operation"],
                           "target": dict(native_target),
                           "submission_id": native_request["submission_id"],
                           "text": native_request["text"]},
        "native_request_sha256": value["native_request_sha256"],
        "native_input_sha256": value["native_input_sha256"],
        "read_ref": value["read_ref"],
    }
    if len(_canonical(detached)) > _HERMES_MAX_PAYLOAD_BYTES:
        raise ValueError("native Secretary request exceeds the payload bound")
    return detached


def _hermes_request_event(event) -> dict:
    """Validate the actual immutable Event independently of caller authority."""
    from control_plane.executive_runtime import Event
    if not isinstance(event, Event):
        raise ValueError("native Secretary request Event is unavailable")
    value = validate_hermes_continuation_request(event.payload)
    request_key = _request_key(value["operation_key"])
    if (type(event.event_id) is not int or event.event_id < 1
            or type(event.sequence) is not int or event.sequence != 1
            or event.event_type != _EVENT or event.actor != _ACTOR
            or event.aggregate_type != "session_bridge_continue"
            or event.aggregate_id != request_key
            or event.command_id != _PREFIX + request_key
            or event.job_id != value["root_job_id"]
            or event.attempt_id is not None or event.worker_id is not None
            or event.quota_class is not None):
        raise ValueError("native Secretary request Event is malformed")
    return value


def validate_hermes_continuation_request_event(event, *,
                                               original_principals) -> dict:
    """Validate the original caller before any selected root is read."""
    principals = _hermes_principal_filter(original_principals)
    value = _hermes_request_event(event)
    identity = tuple(value["principal"][key] for key in _IDENTITY)
    if identity not in principals:
        raise ValueError("native Secretary request identity is foreign")
    return value


def build_hermes_continuation_commit(request_event, *, operation_name: str,
                                     native_request: dict) -> dict:
    """Bind the detached native submission to the immutable request Event."""
    value = _hermes_request_event(request_event)
    if operation_name != "submit":
        raise ValueError("native Secretary operation is not a submission")
    supplied = _hermes_native_request(native_request)
    if supplied != value["native_request"]:
        raise ValueError("native Secretary native request changed")
    family = hermes_family_for_schema(value["schema"], component="request")
    return {"schema": family.commit_schema,
            "request_event_id": request_event.event_id,
            "request_event_sha256": _digest(request_event.to_dict()),
            "operation_key": value["operation_key"],
            "read_ref": value["read_ref"],
            "binding_sha256": value["binding_sha256"],
            "native_request_sha256": value["native_request_sha256"],
            "native_input_sha256": value["native_input_sha256"],
            "submission_id": value["native_request"]["submission_id"]}


def validate_hermes_continuation_commit(value: Any, *, request_event) -> dict:
    """Validate the closed native Secretary commit payload and its joins."""
    if type(value) is not dict or set(value) != set(_HERMES_COMMIT_KEYS):
        raise ValueError("native Secretary commit is malformed")
    family = hermes_family_for_schema(value["schema"], component="commit")
    if type(value["request_event_id"]) is not int or value["request_event_id"] < 1:
        raise ValueError("native Secretary commit is malformed")
    request = _hermes_request_event(request_event)
    if request["schema"] != family.request_schema:
        raise ValueError("native conversation commit family changed")
    if (value["request_event_id"] != request_event.event_id
            or value["request_event_sha256"] != _digest(request_event.to_dict())
            or value["operation_key"] != request["operation_key"]
            or value["read_ref"] != request["read_ref"]
            or value["binding_sha256"] != request["binding_sha256"]
            or value["native_request_sha256"] != request["native_request_sha256"]
            or value["native_input_sha256"] != request["native_input_sha256"]
            or value["submission_id"] != request["native_request"]["submission_id"]):
        raise ValueError("native Secretary commit join changed")
    return dict(value)


def hermes_continuation_commit_evidence(request_event, events, indexed_commit,
                                         indexed_native_commit):
    """Select the optional native commit fact from the request aggregate.

    The aggregate holds exactly the original request and at most one native
    commit. A legacy native-reply commit is a different admission and is never
    the commit of a native Secretary request.
    """
    from control_plane.executive_runtime import Event
    request = _hermes_request_event(request_event)
    if (type(events) is not tuple
            or any(not isinstance(item, Event) for item in events)
            or (indexed_commit is not None and not isinstance(indexed_commit, Event))):
        raise ValueError("native Secretary aggregate is malformed")
    if indexed_native_commit is not None:
        raise ValueError("legacy native reply commit is not a native Secretary commit")
    if any(item.event_type == _LEGACY_NATIVE_COMMIT_EVENT for item in events):
        raise ValueError("legacy native reply commit is not a native Secretary commit")
    request_key = _request_key(request["operation_key"])
    requests = [item for item in events if item.event_type == _EVENT]
    commits = [item for item in events if item.event_type == _HERMES_COMMIT_EVENT]
    if (len(requests) != 1
            or _canonical(requests[0].to_dict()) != _canonical(request_event.to_dict())):
        raise ValueError("native Secretary aggregate request is missing or changed")
    if len(commits) > 1:
        raise ValueError("native Secretary aggregate has more than one commit")
    if len(events) != 1 + len(commits):
        raise ValueError("native Secretary aggregate has an unrelated event")
    if not commits:
        if indexed_commit is not None:
            raise ValueError("native Secretary commit index disagrees with the aggregate")
        return None
    commit = commits[0]
    if (indexed_commit is None
            or _canonical(indexed_commit.to_dict()) != _canonical(commit.to_dict())):
        raise ValueError("native Secretary commit index disagrees with the aggregate")
    if (type(commit.event_id) is not int or commit.event_id <= request_event.event_id
            or type(commit.sequence) is not int or commit.sequence != 2
            or commit.aggregate_type != "session_bridge_continue"
            or commit.aggregate_id != request_key
            or commit.actor != _ACTOR
            or commit.command_id != _HERMES_COMMIT_PREFIX + request_key
            or commit.job_id != request["root_job_id"]
            or commit.attempt_id is not None or commit.worker_id is not None
            or commit.quota_class is not None):
        raise ValueError("native Secretary commit fact changed")
    if (events[0].event_type != _EVENT or events[1].event_type != _HERMES_COMMIT_EVENT
            or commit.sequence != 2):
        raise ValueError("native Secretary aggregate sequence changed")
    validate_hermes_continuation_commit(commit.payload, request_event=request_event)
    return commit


def hermes_continuation_read_request(request: dict, *,
                                     admission_id: str | None = None) -> dict:
    """Project the native owner's own read_original request for one submission.

    An unknown admission ID is omitted rather than guessed; the parent
    forwarder maps that omission to the native owner's own ``None``.
    """
    value = validate_hermes_continuation_request(request)
    result = {"operation": "read_original",
              "session_id": value["binding"]["session_id"],
              "submission_id": value["native_request"]["submission_id"],
              "input_sha256": value["native_input_sha256"]}
    if admission_id is not None:
        result["admission_id"] = _hermes_native_id(admission_id)
    return result
