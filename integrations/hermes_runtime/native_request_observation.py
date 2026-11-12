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

LEGACY_SCHEMA = "mastermind.hermes_request_observation/v1"
PREVIOUS_SCHEMA = "mastermind.hermes_request_observation/v2"
SCHEMA = "mastermind.hermes_request_observation/v3"
RESULT_KEY = "mastermind_request_observation"
STAGE = "assembled_content_after_pre_request_hooks"
TOOLS_STAGE = "assembled_tools_after_pre_request_hooks"
TOOL_COVERAGE = "native_callback_and_result_commit_hooks_only"
CANONICALIZATION = "json_sorted_keys_utf8_no_spaces_v1"
CONTENT_FIELDS = ("messages", "input", "system", "instructions")
TOOL_IDENTIFIERS = ("agent_session_id", "turn_id", "api_request_id", "task_id", "tool_call_id", "tool_name")
TOOL_ERRORS = ("tool_observation_failed", "tool_agent_changed")
MAX_CONTENT_BYTES = 4 * 1024 * 1024
MAX_NODES = 65536
MAX_DEPTH = 64
MAX_EVENTS = 8
MAX_TOOL_EVENTS = 16  # Per kind, also subject to the one shared byte budget.
MAX_METADATA_BYTES = 16 * 1024
METADATA_RESERVE_BYTES = 4096  # Scope, closed errors/overflow and document envelope.
TOOL_UPDATE_RESERVE_BYTES = 256  # Terminal state and sealing-time correlation.
SOURCE_SHA256 = {
    "gateway/session_ingress.py": "e8b038cbaff9eaced033051b14cf6973395b16106c23c1af1034d281bae467b8",
    "agent/turn_api_request.py": "fae43abf285e6f2b82d1820b7bd62ee10214676a48d6af552b8d62530e59dd15",
    "gateway/session_authority.py": "f6eba4d4e17f35e9bcaaf664d1dece93bca8ceccddba3d6d2ad99aa7983bb15f",
    "gateway/session_results.py": "ca926bccfa9d5345b8ec3a2d773462535afa24c82ca4d79e6d6ef490b92e94d2",
    "gateway/session_finite.py": "65b9ddd09dfabf23cc96efc2cffa32d8d5c1ce808589a2271e1fc8b6e7ec6db4",
    "hermes_state_terminal.py": "8aa9e944badb01960d2c754821acd0734088f08a263ed1baac00cacc33c8e7d2",
    "agent/tool_executor.py": "1b1b67d4b88f73c51dc147d0e0383b36c561d921d278d801326de5ba24b29702",
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


def _json_digest(value, *, project_content=False):
    """Detach one exact, bounded JSON value; never retain its body."""
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
    # Historical content observes each selected value at depth zero; its fixed
    # projection keys are encoded but do not consume the value traversal budget.
    # Whole tools values retain independent root/key accounting.
    selected = ({key: copy(value[key], 0) for key in CONTENT_FIELDS if key in value}
                if project_content else copy(value, 0))
    digest, size = hashlib.sha256(), 0
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False,
                               check_circular=False, separators=(",", ":"))
    for piece in encoder.iterencode(selected):
        raw = piece.encode("utf-8", "strict")
        size += len(raw)
        if size > MAX_CONTENT_BYTES:
            raise _ObservationLimit("content_limit")
        digest.update(raw)
    return digest.hexdigest(), size


def _content_digest(api_kwargs):
    """Presence-sensitive content projection, unchanged from historical v1."""
    if type(api_kwargs) is not dict:
        raise ValueError("unsupported_content")
    selected = {key: api_kwargs[key] for key in CONTENT_FIELDS if key in api_kwargs}
    digest, size = _json_digest(api_kwargs, project_content=True)
    return {"fields": list(selected), "content_sha256": digest, "content_bytes": size,
            "canonicalization": CANONICALIZATION}


def _tools_digest(api_kwargs):
    if "tools" not in api_kwargs:
        return {"status": "absent"}
    value = api_kwargs["tools"]
    try:
        digest, size = _json_digest(value)
    except _ObservationLimit:
        return {"status": "unavailable", "reason": "content_limit"}
    except (ValueError, TypeError, UnicodeError):
        return {"status": "unavailable", "reason": "unsupported_content"}
    except Exception:
        return {"status": "unavailable", "reason": "observation_failed"}
    kind = {type(None): "null", bool: "boolean", int: "number", float: "number",
            str: "string", list: "array", dict: "object"}[type(value)]
    return {"status": "observed", "kind": kind, "sha256": digest, "bytes": size,
            "canonicalization": CANONICALIZATION}


def _tool_identity(agent, ref):
    values = (getattr(agent, "session_id", None), getattr(agent, "_current_turn_id", None),
              getattr(agent, "_current_api_request_id", None), getattr(ref, "task_id", None),
              getattr(ref, "call_id", None), getattr(ref, "name", None))
    identity, invalid = {}, []
    for key, value in zip(TOOL_IDENTIFIERS, values):
        if _text(value):
            identity[key] = value
        elif value is not None:
            invalid.append(key)
    return identity, invalid


def _identity_key(identity):
    # Different native refs are constructed by middleware and commit. Neither
    # Python object identity nor a provider call ID alone joins those facts.
    return tuple(identity[key] for key in TOOL_IDENTIFIERS) if set(identity) == set(TOOL_IDENTIFIERS) else None


def _encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


class _Scope:
    def __init__(self, binding, authority, ref, row, live):
        self.binding, self.authority, self.live = binding, authority, live
        self.session_id, self.admission_id = ref.session_id, row["admission_id"]
        self.generation, self.epoch = row["generation"], authority.epoch
        self.instance_id = authority.instance_id
        self.events, self.errors = [], set()
        self.executions, self.commits = [], []
        self.tool_sequence, self.tool_agent = 0, None
        self.overflow = False
        self.tool_overflow = self.metadata_overflow = False
        self.metadata_bytes = METADATA_RESERVE_BYTES
        self.closed = False
        self.evaluation = None
        self.lock = threading.Lock()
        from .native_transport_observation import Contribution
        self.transport = Contribution(self, binding.transport_installation)

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

    def _reserve(self, event, *, tool=False):
        size = _encoded_size(event) + 2 + (TOOL_UPDATE_RESERVE_BYTES if tool else 0)
        if self.metadata_bytes + size > MAX_METADATA_BYTES:
            self.metadata_overflow = True
            if tool:
                self.tool_overflow = True
            else:
                self.overflow = True
            return False
        self.metadata_bytes += size
        return True

    def _tool_current(self, agent):
        with self.live.event_stream.lock, self.lock:
            if self.closed:
                return False
            if not self.current() or not self.adopted(agent):
                self.errors.add("unbound_or_stale_agent")
                return False
        self.authority.check_approval_generation(self.session_id, self.generation)
        return True

    def tool_start(self, agent, ref, *, commit=None):
        if not self._tool_current(agent):
            return None
        identity, invalid = _tool_identity(agent, ref)
        event = {"identity": identity, "invalid_fields": invalid,
                 "state": "entered" if commit is None else "pending"}
        if commit is not None:
            for key in ("blocked", "is_error"):
                if type(commit.get(key)) is bool:
                    event[key] = commit[key]
                else:
                    invalid.append(key)
            value = commit.get("effect_disposition")
            if value is None or type(value) is str and value in {"none", "unknown"}:
                event["reported_effect_disposition"] = value
            else:
                invalid.append("reported_effect_disposition")
        self.authority.check_approval_generation(self.session_id, self.generation)
        with self.live.event_stream.lock, self.lock:
            if self.closed:
                return None
            if not self.current() or not self.adopted(agent):
                self.errors.add("unbound_or_stale_agent")
                return None
            if self.tool_agent is None:
                self.tool_agent = agent
            elif self.tool_agent is not agent:
                self.errors.add("tool_agent_changed")
            records = self.executions if commit is None else self.commits
            if len(records) >= MAX_TOOL_EVENTS:
                self.tool_overflow = True
                return None
            event["sequence"] = self.tool_sequence + 1  # Shared observer order, never a provider ID.
            if not self._reserve(event, tool=True):
                return None
            self.tool_sequence += 1
            records.append(event)
            return event

    def tool_finish(self, agent, event, state):
        if event is None or not self._tool_current(agent):
            return
        with self.live.event_stream.lock, self.lock:
            if self.closed:
                return
            if not self.current() or not self.adopted(agent):
                self.errors.add("unbound_or_stale_agent")
                return
            # The callback closes over its own bounded record. No lookup by a
            # duplicate tool ID and no raw ref/argument/result is retained.
            event["state"] = state

    def _correlate_tools(self):
        limited = self.tool_overflow or self.metadata_overflow or bool(
            self.errors & {*TOOL_ERRORS, "unbound_or_stale_agent"}) or any(
                _identity_key(event["identity"]) is None for event in (*self.executions, *self.commits))
        for commit in self.commits:
            key = _identity_key(commit["identity"])
            candidates = [event for event in self.executions if key is not None and _identity_key(event["identity"]) == key]
            same_commits = [event for event in self.commits if key is not None and _identity_key(event["identity"]) == key]
            if key is None:
                status = "incomplete_identity"
            elif limited:
                status = "coverage_limited"
            elif len(candidates) > 1 or len(same_commits) > 1:
                status = "ambiguous_identity"
            elif not candidates:
                status = "callback_not_observed"
            elif candidates[0]["sequence"] >= commit["sequence"]:
                status = "invalid_order"
            else:
                status = "unique_identity_match"
            correlation = {"status": status}
            if status == "unique_identity_match":
                correlation["execution_sequence"] = candidates[0]["sequence"]
            commit["correlation"] = correlation

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
        event["tools"] = _tools_digest(api_kwargs)
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
            elif self._reserve(event):
                self.events.append(event)
                return event

    def finish(self, *, execution_outcome="unobserved"):
        # Match the original stamp/adoption/retirement lock ordering. SQLite
        # generation reads stay outside this lock on the request executor.
        with self.live.event_stream.lock, self.lock:
            if self.closed:
                return
            self.transport.seal_execution(execution_outcome)
            self.closed = True  # Late copied contexts can no longer contribute.
            if not self.current():
                return
            self._correlate_tools()
            self.tool_agent = None
        # End-process observation cannot extend the accepted contribution window.
        # It performs source/process I/O outside both original locks.
        self.transport.observe_execution_end()
        with self.live.event_stream.lock, self.lock:
            if not self.current():
                return
            document = {"schema": SCHEMA, "stage": STAGE,
                "scope": {"role": self.binding.role, "session_id": self.session_id,
                          "admission_id": self.admission_id, "authority_epoch": self.epoch,
                          "execution_generation": self.generation, "instance_id": self.instance_id},
                "observations": list(self.events), "errors": sorted(self.errors),
                "overflow": self.overflow,
                "tools_stage": TOOLS_STAGE, "tool_coverage": TOOL_COVERAGE,
                "executions": list(self.executions), "commits": list(self.commits),
                "tool_overflow": self.tool_overflow, "metadata_overflow": self.metadata_overflow,
                "coverage": "assembly_hooks_only" if self.events else "no_assembly_observation",
                "provider_dispatch_proven": False, "model_identity_verified": False,
                "transport": self.transport.document()}
            evaluation = self.evaluation.document() if self.evaluation is not None else None
            if _encoded_size(document) + (_encoded_size(evaluation) if evaluation is not None else 0) > MAX_METADATA_BYTES:
                # Defensive envelope fallback: absence must never masquerade as
                # complete empty coverage. No answer/native state is changed.
                document.update(observations=[], executions=[], commits=[], overflow=True,
                                tool_overflow=True, metadata_overflow=True,
                                coverage="no_assembly_observation",
                                transport=self.transport.document(force_empty=True))
                if self.evaluation is not None:
                    evaluation = self.evaluation.document(force_empty=True)
            pending = self.authority.pending_results.get(self.admission_id)
            # The outer pending result is created by native ingress, independently
            # of the agent result body. Preserve any pre-existing field on collision.
            if type(pending) is not dict or type(pending.get("result")) is not dict or RESULT_KEY in pending:
                return
            pending[RESULT_KEY] = document
            if evaluation is not None:
                from .native_eval_inputs import RESULT_KEY as EVAL_RESULT_KEY
                if EVAL_RESULT_KEY not in pending:
                    pending[EVAL_RESULT_KEY] = evaluation


class _Binding:
    def __init__(self, launch, role_home, role, authority_class):
        self.launch, self.role_home, self.role = launch, role_home, role
        self.authority_class = authority_class
        self.authority = None
        self.transport_installation = None
        self.evaluation_owner = None
        self.memory_factory = None

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
    selected_sources = dict(SOURCE_SHA256)
    if "evaluation_inputs" in getattr(launch, "recipe", {}):
        from .native_eval_inputs import authority_source_sha
        selected_sources["gateway/session_authority.py"] = authority_source_sha(launch, vendor)
    for path, expected in selected_sources.items():
        if _digest(vendor / path, maximum=128 * 1024) != expected:
            raise RuntimeRefusal("NATIVE_OBSERVATION_SOURCE_MISMATCH")
        name = path.removesuffix(".py").replace("/", ".")
        module = _vendor_module(name, vendor)
        if type(module) is not ModuleType or getattr(module, "_mmx_request_observation_bound", False):
            raise RuntimeRefusal("NATIVE_OBSERVATION_ALREADY_BOUND")
        modules[name] = module
    ingress, requests = modules["gateway.session_ingress"], modules["agent.turn_api_request"]
    executor = modules["agent.tool_executor"]
    execute = _original_function(ingress, "execute_admission", asynchronous=True)
    hook = _original_function(requests, "_fire_pre_api_request_hook")
    _original_function(requests, "build_api_request")
    _original_function(modules["gateway.session_finite"], "execute_finite_admission", asynchronous=True)
    dispatch_tool = _original_function(executor, "_dispatch_authorized_once")
    commit_tool = _original_function(executor, "_commit_tool_result")
    authority_class = modules["gateway.session_authority"].SessionAuthority
    if not inspect.isclass(authority_class) or authority_class.__module__ != "gateway.session_authority":
        raise RuntimeRefusal("NATIVE_OBSERVATION_SEAM_CHANGED")
    binding = _Binding(launch, role_home, role, authority_class)
    from .native_transport_observation import prepare
    binding.transport_installation = prepare(binding, vendor)

    async def execute_observed(authority, ref, row):
        scope = binding.scope(authority, ref, row)
        marked = (type(row) is dict and type(row.get("payload")) is dict and any(
            type(key) is str and key.startswith("mastermind_eval_inputs") for key in row["payload"]))
        if marked:
            # Input selection is required execution behavior. A marked row
            # cannot use optional observation's fail-open ordinary-turn path.
            from .native_eval_inputs import NativeEvalInputOwner
            if scope is None or type(binding.evaluation_owner) is not NativeEvalInputOwner:
                raise RuntimeRefusal("NATIVE_EVAL_RECEIVER_UNAVAILABLE")
            scope.evaluation = binding.evaluation_owner.restore(scope, row)
        if scope is None:
            return await execute(authority, ref, row)
        token = _current.set(scope)
        execution_outcome = "raised"
        try:
            result = await execute(authority, ref, row)
            execution_outcome = "returned"
            return result
        finally:
            _current.reset(token)
            try:
                scope.finish(execution_outcome=execution_outcome)
            except Exception:
                # Instrumentation must not replace a native outcome/exception.
                scope.closed = True

    def observe_request(agent, api_kwargs, api_messages, _llm_middleware_trace, **kwargs):
        result = hook(agent, api_kwargs, api_messages, _llm_middleware_trace, **kwargs)
        scope = _current.get()
        if scope is not None and scope.binding is binding:
            if scope.evaluation is not None:
                # This check follows actual pre-request hooks and is outside
                # the observation-only failure policy, before provider dispatch.
                scope.evaluation.require_request(agent, api_kwargs)
            try:
                event = scope.record(agent, api_kwargs, kwargs)
                if event is not None and scope.evaluation is not None:
                    try:
                        scope.evaluation.record_assembly(agent, api_kwargs, event)
                    except Exception:
                        scope.evaluation.fail("assembly_unavailable")
            except _ObservationLimit:
                scope.fail("content_limit")
            except (ValueError, TypeError, UnicodeError):
                scope.fail("unsupported_content")
            except Exception:
                scope.fail("observation_failed")
        return result

    def tool_scope():
        scope = _current.get()
        return scope if scope is not None and scope.binding is binding else None

    def tool_note(scope, method, *args, **kwargs):
        try:
            return getattr(scope, method)(*args, **kwargs)
        except Exception:
            scope.fail("tool_observation_failed")
            return None

    def observe_dispatch(agent, state, ref, *, execute, **kwargs):
        scope = tool_scope()
        if scope is None:
            return dispatch_tool(agent, state, ref, execute=execute, **kwargs)

        def entered(*args, **callback_kwargs):
            event = tool_note(scope, "tool_start", agent, ref)
            try:
                result = execute(*args, **callback_kwargs)
            except BaseException:
                tool_note(scope, "tool_finish", agent, event, "raised")
                raise
            tool_note(scope, "tool_finish", agent, event, "returned")
            return result

        # Original scope, plugin, argument and guardrail policy still runs once.
        # Only its actual callback entry is observed, not state.dispatched.
        return dispatch_tool(agent, state, ref, execute=entered, **kwargs)

    def observe_commit(agent, messages, ref, function_result, **kwargs):
        scope = tool_scope()
        event = tool_note(scope, "tool_start", agent, ref, commit=kwargs) if scope is not None else None
        try:
            result = commit_tool(agent, messages, ref, function_result, **kwargs)
        except BaseException:
            if scope is not None:
                tool_note(scope, "tool_finish", agent, event, "raised")
            raise
        if scope is not None:
            state = ("commit_tuple_returned" if type(result) is tuple and len(result) == 3 else
                     "commit_none_returned" if result is None else "unrecognized_return")
            tool_note(scope, "tool_finish", agent, event, state)
        return result

    launch.check()
    binding.transport_installation.commit()
    ingress.execute_admission = execute_observed
    requests._fire_pre_api_request_hook = observe_request
    executor._dispatch_authorized_once = observe_dispatch
    executor._commit_tool_result = observe_commit
    ingress._mmx_request_observation_bound = True
    requests._mmx_request_observation_bound = True
    executor._mmx_request_observation_bound = True
    return binding
