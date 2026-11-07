"""Bounded request-assembly observations retained by the original admission.

This observes a declared construction stage. It neither dispatches work nor
attests model identity, provider delivery, complete source coverage or EVAL.
"""
from __future__ import annotations

from contextvars import ContextVar
import hashlib
import inspect
import json
import math
from pathlib import Path
import threading
from types import ModuleType

from .errors import RuntimeRefusal

SCHEMA = "mastermind.hermes_request_observation/v1"
RESULT_KEY = "mastermind_request_observation"
STAGE = "assembled_content_after_pre_request_hooks"
CONTENT_FIELDS = ("messages", "input", "system", "instructions")
MAX_CONTENT_BYTES = 4 * 1024 * 1024
MAX_NODES = 65536
MAX_DEPTH = 64
MAX_EVENTS = 8
MAX_METADATA_BYTES = 16 * 1024
SOURCE_SHA256 = {
    "gateway/session_ingress.py": "e8b038cbaff9eaced033051b14cf6973395b16106c23c1af1034d281bae467b8",
    "agent/turn_api_request.py": "fae43abf285e6f2b82d1820b7bd62ee10214676a48d6af552b8d62530e59dd15",
    "gateway/session_authority.py": "f6eba4d4e17f35e9bcaaf664d1dece93bca8ceccddba3d6d2ad99aa7983bb15f",
    "gateway/session_results.py": "ca926bccfa9d5345b8ec3a2d773462535afa24c82ca4d79e6d6ef490b92e94d2",
    "gateway/session_finite.py": "65b9ddd09dfabf23cc96efc2cffa32d8d5c1ce808589a2271e1fc8b6e7ec6db4",
    "hermes_state_terminal.py": "8aa9e944badb01960d2c754821acd0734088f08a263ed1baac00cacc33c8e7d2",
}
_current: ContextVar[_Scope | None] = ContextVar("mastermind_request_observation", default=None)


class _ObservationLimit(ValueError):
    pass


def _text(value):
    if (type(value) is not str or not 0 < len(value) <= 256
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        return False
    try:
        return len(value.encode("utf-8", "strict")) <= 256
    except UnicodeError:
        return False


def _integer(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def _content_digest(api_kwargs):
    """Detach exact JSON content with bounded work; retain only its digest."""
    if type(api_kwargs) is not dict:
        raise ValueError("unsupported_content")
    nodes = 0
    raw_bytes = 0
    active = set()
    def copy(value, depth):
        nonlocal nodes, raw_bytes
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise _ObservationLimit("content_limit")
        kind = type(value)
        if kind is str:
            if len(value) > MAX_CONTENT_BYTES:
                raise _ObservationLimit("content_limit")
            raw_bytes += len(value.encode("utf-8", "strict"))
            if raw_bytes > MAX_CONTENT_BYTES:
                raise _ObservationLimit("content_limit")
            return value
        if value is None or kind is bool:
            return value
        if kind is int:
            if value.bit_length() > 128:
                raise ValueError("unsupported_content")
            return value
        if kind is float:
            if not math.isfinite(value):
                raise ValueError("unsupported_content")
            return value
        if kind not in (dict, list) or id(value) in active:
            raise ValueError("unsupported_content")
        active.add(id(value))
        try:
            if kind is list:
                return [copy(item, depth + 1) for item in value]
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("unsupported_content")
                result[copy(key, depth + 1)] = copy(item, depth + 1)
            return result
        finally:
            active.remove(id(value))
    selected = {key: copy(api_kwargs[key], 0) for key in CONTENT_FIELDS if key in api_kwargs}
    digest, size = hashlib.sha256(), 0
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False,
                               check_circular=False, separators=(",", ":"))
    for piece in encoder.iterencode(selected):
        raw = piece.encode("utf-8", "strict")
        size += len(raw)
        if size > MAX_CONTENT_BYTES:
            raise _ObservationLimit("content_limit")
        digest.update(raw)
    return {"fields": list(selected), "content_sha256": digest.hexdigest(), "content_bytes": size,
            "canonicalization": "json_sorted_keys_utf8_no_spaces_v1"}


def project_request_observation(value, *, admission: dict, role: str):
    """Return only a closed, bounded observation of this original admission.

    The stored epoch/generation qualify historical evidence after restart.
    The current process is not an execution witness. The instance label is
    retained as reported evidence; the admission store has no instance join.
    Invalid metadata never replaces an otherwise valid native result.
    """
    top = {"schema", "stage", "scope", "observations", "errors", "overflow",
           "coverage", "provider_dispatch_proven", "model_identity_verified"}
    scope_keys = {"role", "session_id", "admission_id", "authority_epoch",
                  "execution_generation", "instance_id"}
    if type(value) is not dict or len(value) != len(top) or set(value) != top:
        return None
    if (value["schema"] != SCHEMA or value["stage"] != STAGE
            or value["provider_dispatch_proven"] is not False
            or value["model_identity_verified"] is not False
            or type(value["overflow"]) is not bool):
        return None
    scope = value["scope"]
    if (type(scope) is not dict or len(scope) != len(scope_keys) or set(scope) != scope_keys
            or any(not _text(scope[key]) for key in
                   ("role", "session_id", "admission_id", "instance_id"))
            or not _integer(scope["authority_epoch"]) or scope["authority_epoch"] < 1
            or not _integer(scope["execution_generation"])):
        return None
    # No None/bool coercion and no comparison with the new owner's epoch.
    if (type(admission) is not dict or type(admission.get("ref")) is not dict
            or type(admission.get("authority_epoch")) is not int
            or type(admission.get("execution_generation")) is not int
            or scope["role"] != role
            or scope["session_id"] != admission["ref"].get("session_id")
            or scope["admission_id"] != admission.get("admission_id")
            or scope["authority_epoch"] != admission["authority_epoch"]
            or scope["execution_generation"] != admission["execution_generation"]):
        return None
    events, errors = value["observations"], value["errors"]
    error_codes = {"content_limit", "unsupported_content", "observation_failed",
                   "unbound_or_stale_agent"}
    if (type(events) is not list or len(events) > MAX_EVENTS
            or type(errors) is not list or len(errors) > len(error_codes)
            or any(type(item) is not str or item not in error_codes for item in errors)
            or len(errors) != len(set(errors))
            or value["coverage"] != ("assembly_hooks_only" if events else "no_assembly_observation")):
        return None
    required = {"fields", "content_sha256", "content_bytes", "canonicalization"}
    labels = {"turn_id", "api_request_id", "agent_session_id"}
    counters = {"api_call_count", "retry_count"}
    optional = labels | counters
    allowed = required | optional | {"invalid_fields"}
    for event in events:
        if (type(event) is not dict or not len(required) <= len(event) <= len(allowed)
                or not required <= set(event) <= allowed):
            return None
        digest, fields, size = event["content_sha256"], event["fields"], event["content_bytes"]
        if (type(digest) is not str or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                or type(size) is not int or not 2 <= size <= MAX_CONTENT_BYTES
                or event["canonicalization"] != "json_sorted_keys_utf8_no_spaces_v1"
                or type(fields) is not list or len(fields) > len(CONTENT_FIELDS)
                or any(type(key) is not str or key not in CONTENT_FIELDS for key in fields)
                or fields != [key for key in CONTENT_FIELDS if key in fields]):
            return None
        if (any(not _text(event[key]) for key in labels if key in event)
                or any(not _integer(event[key]) for key in counters if key in event)):
            return None
        if "invalid_fields" in event:
            invalid = event["invalid_fields"]
            if (type(invalid) is not list or not 1 <= len(invalid) <= len(optional)
                    or any(type(key) is not str or key not in optional or key in event for key in invalid)
                    or len(invalid) != len(set(invalid))):
                return None
    # All containers and selected values are bounded before serialization.
    # Round-trip detaches the result; never return aliases into owner storage.
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return json.loads(raw) if len(raw) <= MAX_METADATA_BYTES else None
    except (ValueError, TypeError, UnicodeError):
        return None


class _Scope:
    def __init__(self, binding, authority, ref, row, live):
        self.binding, self.authority, self.live = binding, authority, live
        self.session_id, self.admission_id = ref.session_id, row["admission_id"]
        self.generation, self.epoch = row["generation"], authority.epoch
        self.instance_id = authority.instance_id
        self.events, self.errors = [], set()
        self.overflow = False
        self.closed = False
        self.lock = threading.Lock()

    def current(self):
        owner = self.authority
        return (self.binding.authority is owner and not self.binding.launch.owner.closed
                and not self.binding.launch.closure.closed
                and str(owner.profile_id) == str(self.binding.role_home)
                and owner.instance_id == self.instance_id and owner.epoch == self.epoch
                and not owner.retiring and not owner.runner._draining
                and owner.sessions.get(self.session_id) is self.live
                and owner.executing.get(self.session_id) == self.generation
                and self.live.event_stream.execution == {
                    "authority_epoch": self.epoch, "execution_generation": self.generation,
                    "admission_id": self.admission_id})

    def fail(self, reason):
        with self.lock:
            if not self.closed:
                self.errors.add(reason)

    def adopted(self, agent):
        adopted = self.authority.adopted.get(self.session_id)
        return (type(adopted) is tuple and len(adopted) == 2
                and adopted[0] == self.generation and adopted[1] is agent)

    def record(self, agent, api_kwargs, identifiers):
        with self.lock:
            if self.closed:
                return
            if len(self.events) >= MAX_EVENTS:
                self.overflow = True
                return
        with self.live.event_stream.lock:
            if not self.current() or not self.adopted(agent):
                self.fail("unbound_or_stale_agent")
                return
        # The original native owner checks the current stored generation. This
        # runs on the request executor, never a viewer/event-delivery observer.
        self.authority.check_approval_generation(self.session_id, self.generation)
        event = _content_digest(api_kwargs)
        invalid = []
        for key in ("turn_id", "api_request_id"):
            value = identifiers.get(key)
            if _text(value):
                event[key] = value
            elif value is not None:
                invalid.append(key)
        for key in ("api_call_count", "retry_count"):
            value = identifiers.get(key)
            if _integer(value):
                event[key] = value
            elif value is not None:
                invalid.append(key)
        agent_session = getattr(agent, "session_id", None)
        if _text(agent_session):
            event["agent_session_id"] = agent_session
        elif agent_session is not None:
            invalid.append("agent_session_id")
        if invalid:
            event["invalid_fields"] = invalid
        self.authority.check_approval_generation(self.session_id, self.generation)
        with self.live.event_stream.lock, self.lock:
            if self.closed:
                return
            if not self.current() or not self.adopted(agent):
                self.errors.add("unbound_or_stale_agent")
            elif len(self.events) >= MAX_EVENTS:
                self.overflow = True
            else:
                self.events.append(event)

    def finish(self):
        # Match the original stamp/adoption/retirement lock ordering. SQLite
        # generation reads stay outside this lock on the request executor.
        with self.live.event_stream.lock, self.lock:
            self.closed = True  # Late copied contexts can no longer contribute.
            if not self.current():
                return
            document = {"schema": SCHEMA, "stage": STAGE,
                "scope": {"role": self.binding.role, "session_id": self.session_id,
                          "admission_id": self.admission_id, "authority_epoch": self.epoch,
                          "execution_generation": self.generation, "instance_id": self.instance_id},
                "observations": list(self.events), "errors": sorted(self.errors),
                "overflow": self.overflow,
                "coverage": "assembly_hooks_only" if self.events else "no_assembly_observation",
                "provider_dispatch_proven": False, "model_identity_verified": False}
            if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_METADATA_BYTES:
                return
            pending = self.authority.pending_results.get(self.admission_id)
            # The outer pending result is created by native ingress, independently
            # of the agent result body. Preserve any pre-existing field on collision.
            if type(pending) is not dict or type(pending.get("result")) is not dict or RESULT_KEY in pending:
                return
            pending[RESULT_KEY] = document


class _Binding:
    def __init__(self, launch, role_home, role, authority_class):
        self.launch, self.role_home, self.role = launch, role_home, role
        self.authority_class = authority_class
        self.authority = None

    def bind_authority(self, runner):
        self.launch.check()
        authority = getattr(runner, "session_authority", None)
        descriptor = getattr(runner, "session_runtime_descriptor", None)
        if (type(authority) is not self.authority_class or authority.runner is not runner
                or str(authority.profile_id) != str(self.role_home) or type(descriptor) is not dict
                or descriptor.get("instance_id") != authority.instance_id
                or descriptor.get("authority_epoch") != authority.epoch
                or not _text(authority.instance_id) or not _integer(authority.epoch)
                or getattr(runner.config, "multiplex_profiles", False)
                or (self.authority is not None and self.authority is not authority)):
            raise RuntimeRefusal("NATIVE_OBSERVATION_AUTHORITY_MISMATCH")
        self.authority = authority

    def scope(self, authority, ref, row):
        try:
            if (self.authority is not authority or type(row) is not dict
                    or str(ref.profile_id) != str(self.role_home) or not _text(ref.session_id)
                    or not _text(row.get("admission_id")) or not _integer(row.get("generation"))):
                return None
            live = authority.sessions.get(ref.session_id)
            if live is None:
                return None
            scope = _Scope(self, authority, ref, row, live)
            return scope if scope.current() else None
        except Exception:
            return None


def _original_function(module, name, *, asynchronous=False):
    function = getattr(module, name, None)
    if (not inspect.isfunction(function) or function.__globals__ is not vars(module)
            or function.__module__ != module.__name__
            or Path(function.__code__.co_filename).resolve() != Path(module.__file__).resolve()
            or inspect.iscoroutinefunction(function) is not asynchronous):
        raise RuntimeRefusal("NATIVE_OBSERVATION_SEAM_CHANGED")
    return function


def install_request_observation(launch, vendor: Path, role_home: Path, role: str):
    """Bind once after native profile selection, before the original gateway starts."""
    from .native_gateway_entry import _digest, _vendor_module
    launch.check()
    modules = {}
    for path, expected in SOURCE_SHA256.items():
        if _digest(vendor / path, maximum=128 * 1024) != expected:
            raise RuntimeRefusal("NATIVE_OBSERVATION_SOURCE_MISMATCH")
        name = path.removesuffix(".py").replace("/", ".")
        module = _vendor_module(name, vendor)
        if type(module) is not ModuleType or getattr(module, "_mmx_request_observation_bound", False):
            raise RuntimeRefusal("NATIVE_OBSERVATION_ALREADY_BOUND")
        modules[name] = module
    ingress, requests = modules["gateway.session_ingress"], modules["agent.turn_api_request"]
    execute = _original_function(ingress, "execute_admission", asynchronous=True)
    hook = _original_function(requests, "_fire_pre_api_request_hook")
    _original_function(requests, "build_api_request")
    _original_function(modules["gateway.session_finite"], "execute_finite_admission", asynchronous=True)
    authority_class = modules["gateway.session_authority"].SessionAuthority
    if not inspect.isclass(authority_class) or authority_class.__module__ != "gateway.session_authority":
        raise RuntimeRefusal("NATIVE_OBSERVATION_SEAM_CHANGED")
    binding = _Binding(launch, role_home, role, authority_class)

    async def execute_observed(authority, ref, row):
        scope = binding.scope(authority, ref, row)
        if scope is None:
            return await execute(authority, ref, row)
        token = _current.set(scope)
        try:
            return await execute(authority, ref, row)
        finally:
            _current.reset(token)
            try:
                scope.finish()
            except Exception:
                # Instrumentation must not replace a native outcome/exception.
                scope.closed = True

    def observe_request(agent, api_kwargs, api_messages, _llm_middleware_trace, **kwargs):
        result = hook(agent, api_kwargs, api_messages, _llm_middleware_trace, **kwargs)
        scope = _current.get()
        if scope is not None and scope.binding is binding:
            try:
                scope.record(agent, api_kwargs, kwargs)
            except _ObservationLimit:
                scope.fail("content_limit")
            except (ValueError, TypeError, UnicodeError):
                scope.fail("unsupported_content")
            except Exception:
                scope.fail("observation_failed")
        return result

    launch.check()
    ingress.execute_admission = execute_observed
    requests._fire_pre_api_request_hook = observe_request
    ingress._mmx_request_observation_bound = True
    requests._mmx_request_observation_bound = True
    return binding
