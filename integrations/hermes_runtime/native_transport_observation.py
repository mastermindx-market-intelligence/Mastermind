"""A contribution to the original native request observer, never another store.

The selected synchronous HTTPX boundary is below SDK retry/redirect handling.
Entry, returned headers and a subsequently consumed body are different facts.
Unsupported, late, missing and truncated evidence stays explicitly incomplete.
No request, client, response body, credential, retry or result is created here.
"""
from __future__ import annotations

import copy
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import time
from types import ModuleType

from .errors import RuntimeRefusal

SCHEMA = "mastermind.hermes_native_transport_observation/v3"
PROVIDER_SCHEMA_V2 = "mastermind.hermes_native_transport_observation/v2"
PREVIOUS_SCHEMA = "mastermind.hermes_native_transport_observation/v1"
PROVIDER_SCHEMAS = frozenset({SCHEMA, PROVIDER_SCHEMA_V2})
APPLICATION_SCHEMA = "mastermind.hermes_native_transport_observation/v4"
APPLICATION_COVERAGE = "selected_nonstream_httpx_and_application_owner_only"
COVERAGE = "selected_nonstream_sync_httpx_only"
EXECUTION_STAGE = "original_execute_admission_wrapper"
HTTP_STAGE = "httpx_client_send_single_request"
HTTPX_SOURCE_SHA256 = "c43f941baefe58c91e96d00039e1868fe719d91453026d7db1647194563bff8d"
SOURCE_SHA256 = {
    "agent/conversation_loop.py": "36dd6f02b169a544a95598dee74cb775914420dc700cc88cc946effd103b72bc",
    "agent/turn_api_call.py": "809f38471e58b20d68911c73b39945c3b2b4f1e9de1c8be7d451ac3f91774be1",
    "agent/chat_completion_helpers.py": "7c822d0213d9471ec3b9a04ffb0604badbe3761520e1948cb9fc9b7f67466e1c",
    "agent/chat_completion_nonstream.py": "34d4afad0a0c7228a0518eed4a2521ba1a340f509c83784c74abceb56f1becb7",
    "agent/chat_completion_headers.py": "6240d0fc4f935353b86c007c27cc4fd00223f6bc6c141b0b30486441e38b29b2",
    "agent/sdk_transform_bypass.py": "6887046105bd5e666631aa9a0d0a81488392ba8978ede650ae4e31abc36ccbd6",
}
MAX_CALLS = 8
MAX_DISPATCHES = 16
MAX_ATTEMPTS = 16
UPDATE_RESERVE_BYTES = 1024
SAMPLING_FIELDS = (
    "seed", "temperature", "top_p", "top_k", "min_p", "n", "max_tokens",
    "max_completion_tokens", "frequency_penalty", "presence_penalty",
    "reasoning_effort", "reasoning", "thinking", "stop", "logit_bias",
)
IDENTIFIERS = ("agent_session_id", "turn_id", "api_request_id")
EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"})
ERRORS = frozenset({
    "transport_observation_failed", "transport_binding_changed", "unbound_logical_call",
    "unsupported_dispatch", "unsupported_client", "multiple_clients", "client_changed",
    "clock_unavailable", "clock_regression", "process_observation_unavailable",
    "process_changed", "wire_metadata_unavailable", "response_metadata_unavailable",
    "application_identity_unavailable", "application_return_unavailable",
})
_call_context = ContextVar("mastermind_native_transport_call", default=None)
_dispatch_context = ContextVar("mastermind_native_transport_dispatch", default=None)
_HEX = re.compile(r"[0-9a-f]{64}")
_SHA = re.compile(r"[0-9a-f]{40}")
_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _observation():
    from . import native_request_observation
    return native_request_observation


def _hash(value):
    return _observation()._json_digest(value)[0]


def _clock():
    # Wall time labels the actual wrapper edge; duration uses only monotonic time.
    wall, mono = time.time_ns() // 1_000_000, time.monotonic_ns()
    if type(wall) is not int or not 0 <= wall <= 2**53 - 1 or type(mono) is not int:
        raise ValueError("clock unavailable")
    return wall, mono


def _scalar(value, kind):
    if value is None:
        return {"status": "null"}
    if kind in {"model", "effort"}:
        if not _observation()._text(value):
            return {"status": "invalid"}
        if kind == "effort" and value in EFFORTS:
            return {"status": "present", "value": value}
        # Provider labels are arbitrary text, including on errors and proxies.
        # Keep byte identity, never a credential-bearing URL or error as a label.
        raw = value.encode("utf-8", "strict")
        return {"status": "observed_digest" if kind == "model" else "unrecognized_digest",
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    valid = type(value) is int and -(2**63) <= value < 2**63
    return {"status": "present", "value": value} if valid else {"status": "invalid"}


def _runtime_provider(agent):
    """Digest the actual native runtime selector; never retain arbitrary labels."""
    try:
        return _scalar(getattr(agent, "provider"), "model")
    except AttributeError:
        return {"status": "absent"}
    except Exception:
        return {"status": "unobserved"}


def _field(value, name, kind):
    return _scalar(value[name], kind) if name in value else {"status": "absent"}


def _json_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("nonfinite JSON")
    value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                       parse_constant=nonfinite)
    if type(value) is not dict:
        raise ValueError("object required")
    # Bound the whole tree, including fields which are never retained.
    _observation()._json_digest(value)
    return value


def _request_projection(request):
    obs = _observation()
    result = {
        "method": request.method if request.method in {"GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"} else None,
        "origin_sha256": _hash([request.url.scheme, request.url.host, request.url.port]),
        "body_state": "unavailable", "body_sha256": None, "body_bytes": None,
        "content_sha256": None, "content_fields": None, "tools_sha256": None,
        "tools_state": "unobserved", "explicit_sampling_sha256": None,
        "sampling_fields": None, "model": {"status": "unobserved"},
        "seed": {"status": "unobserved"}, "reasoning_effort": {"status": "unobserved"},
    }
    # This property never reads the network or drains an unconsumed request stream.
    try:
        raw = request.content
    except Exception:
        return result
    if type(raw) is not bytes:
        return result
    result["body_bytes"] = len(raw)
    if len(raw) > obs.MAX_CONTENT_BYTES:
        result["body_state"] = "oversized"
        return result
    result["body_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        value = _json_object(raw)
        content = obs._content_digest(value)
        tools = obs._tools_digest(value)
        selected = {key: value[key] for key in SAMPLING_FIELDS if key in value}
        sampling = _hash(selected)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        result["body_state"] = "unqualified_json"
        return result
    effort = _field(value, "reasoning_effort", "effort")
    reasoning = value.get("reasoning")
    if type(reasoning) is dict and "effort" in reasoning:
        nested = _scalar(reasoning["effort"], "effort")
        effort = nested if effort["status"] == "absent" else (
            effort if effort == nested else {"status": "conflicting"})
    result.update(
        body_state="observed_json_object", content_sha256=content["content_sha256"],
        content_fields=content["fields"], tools_state=tools["status"],
        tools_sha256=tools.get("sha256"), explicit_sampling_sha256=sampling,
        sampling_fields=list(selected), model=_field(value, "model", "model"),
        seed=_field(value, "seed", "integer"), reasoning_effort=effort,
    )
    return result


def _response_projection(response, *, consumed=False):
    result = {"status_code": response.status_code, "body_state": "not_observed",
              "body_sha256": None, "body_bytes": None,
              "reported_model": {"status": "unobserved"}}
    if not consumed:
        return result
    # Never call read(), iter_bytes(), json() or close(). The original SDK owns
    # stream consumption, abort and cleanup. Reuse only already-consumed bytes.
    if not response.is_stream_consumed:
        result["body_state"] = "unconsumed"
        return result
    try:
        raw = response.content
    except Exception:
        result["body_state"] = "unavailable"
        return result
    if type(raw) is not bytes:
        result["body_state"] = "unavailable"
        return result
    result["body_bytes"] = len(raw)
    if len(raw) > _observation().MAX_CONTENT_BYTES:
        result["body_state"] = "oversized"
        return result
    result["body_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        value = _json_object(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        result["body_state"] = "consumed_unqualified_json"
        return result
    result.update(body_state="consumed_json_object", reported_model=_field(value, "model", "model"))
    return result


def _process(launch):
    """Reuse the existing held process-image owner; never infer a principal."""
    pid = os.getpid()
    measured = launch.observe_child(pid)
    facts = {"pid": pid, "boot_id": measured["boot_id"], "start_identity": measured["start_identity"],
             "image_sha256": measured["sha256"], "release_sha": launch.owner.root.name,
             "manifest_sha256": launch.owner.manifest_sha256()}
    for key in ("real_uid", "effective_uid", "real_gid", "effective_gid"):
        facts[key] = measured[key]
    result = {"status": "observed", "facts": facts, "fingerprint": _hash(facts)}
    _validate_process(result)
    launch.check()
    return result


@dataclass
class _Span:
    record: dict
    monotonic_start: int | None
    task_id: str | None = None


class Contribution:
    """Bounded ephemeral fields of one original admission observation scope."""

    def __init__(self, scope, installation):
        self.scope, self.installation = scope, installation
        self.calls, self.dispatches, self.attempts = [], [], []
        self.application_attempts, self.application_seen = [], False
        self.errors, self.overflow = set(), False
        credentials = installation.credential_installation
        self.credential_scope = None
        try:
            self.credential_scope = credentials.scope(scope) if credentials is not None else None
        except Exception:
            self.errors.add("transport_observation_failed")
        self.execution = {"stage": EXECUTION_STAGE, "outcome": "unobserved",
                          "started_at_ms": None, "finished_at_ms": None, "duration_ms": None,
                          "process_start": {"status": "unavailable"},
                          "process_end": {"status": "unavailable"}, "same_process": None}
        self.start_ns = None
        try:
            self.execution["started_at_ms"], self.start_ns = _clock()
        except Exception:
            self.errors.add("clock_unavailable")
        try:
            self.execution["process_start"] = _process(scope.binding.launch)
        except Exception:
            self.errors.add("process_observation_unavailable")

    def error(self, code):
        with self.scope.lock:
            if not self.scope.closed:
                self.errors.add(code)

    def observe_unbound_transport(self):
        # A gap belongs only to this original admission. Never borrow a foreign
        # dispatch identity or redirect a copied stale context to a new owner.
        with self.scope.live.event_stream.lock, self.scope.lock:
            if not self.scope.closed and self.scope.current():
                self.errors.add("unsupported_dispatch")

    def _clock_start(self):
        try:
            return _clock()
        except Exception:
            self.error("clock_unavailable")
            return None, None

    def _clock_end(self, span):
        wall, mono = self._clock_start()
        duration = None if mono is None or span.monotonic_start is None else (mono - span.monotonic_start) // 1_000_000
        if duration is not None and duration < 0:
            self.error("clock_regression")
            duration = None
        if wall is not None and span.record["started_at_ms"] is not None and wall < span.record["started_at_ms"]:
            self.error("clock_regression")
        return {"finished_at_ms": wall, "duration_ms": duration}

    def begin(self, kind, agent, *, identifiers=None, caller=None, dispatch_sequence=None, request=None):
        if not self.scope._tool_current(agent):
            return None
        wall, mono = self._clock_start()
        record = {"state": "entered", "started_at_ms": wall, "finished_at_ms": None, "duration_ms": None}
        if kind == "application":
            record.update(dispatch_sequence=dispatch_sequence, request=request, response=None,
                          runtime_provider=_runtime_provider(agent))
            records, maximum = self.application_attempts, MAX_ATTEMPTS
        elif kind == "attempt":
            record.update(dispatch_sequence=dispatch_sequence, request=_request_projection(request), response=None,
                          runtime_provider=_runtime_provider(agent), auth_mechanism="unavailable")
            records, maximum = self.attempts, MAX_ATTEMPTS
        else:
            identifiers = identifiers or {}
            values = {"agent_session_id": getattr(agent, "session_id", None),
                      "turn_id": identifiers.get("turn_id", getattr(agent, "_current_turn_id", None)),
                      "api_request_id": identifiers.get("api_request_id", getattr(agent, "_current_api_request_id", None))}
            record["identity"] = {key: value for key, value in values.items() if _observation()._text(value)}
            record["invalid_fields"] = [key for key, value in values.items() if value is not None and key not in record["identity"]]
            if kind == "call":
                for key in ("api_call_count", "retry_count"):
                    value = identifiers.get(key)
                    record[key] = value if _observation()._integer(value) else None
                records, maximum = self.calls, MAX_CALLS
            else:
                if caller is not None:
                    # The nonstream worker carries the call's copied context;
                    # today's mutable agent labels can already name another call.
                    record["identity"] = dict(caller.record["identity"])
                    record["invalid_fields"] = list(caller.record["invalid_fields"])
                record.update(call_sequence=caller.record["sequence"] if caller else None,
                              client_binding="pending", runtime_provider=_runtime_provider(agent),
                              provider_client_check="pending", auth_client_check="pending")
                records, maximum = self.dispatches, MAX_DISPATCHES
        with self.scope.live.event_stream.lock, self.scope.lock:
            if self.scope.closed or not self.scope.current() or not self.scope.adopted(agent):
                return None
            if len(records) >= maximum or (kind in {"attempt", "application"}
                    and len(self.attempts) + len(self.application_attempts) >= MAX_ATTEMPTS):
                self.overflow = True
                return None
            record["sequence"] = len(records) + 1
            from .native_application_observation import UPDATE_RESERVE_BYTES as APPLICATION_RESERVE
            size = _observation()._encoded_size(record) + (APPLICATION_RESERVE if kind == "application" else UPDATE_RESERVE_BYTES)
            if self.scope.metadata_bytes + size > _observation().MAX_METADATA_BYTES:
                self.overflow = self.scope.metadata_overflow = True
                return None
            self.scope.metadata_bytes += size
            records.append(record)
        return _Span(record, mono, (identifiers or {}).get("effective_task_id") if kind == "call" else None)

    def mark_application(self, agent):
        with self.scope.live.event_stream.lock, self.scope.lock:
            if not self.scope.closed and self.scope.current() and self.scope.adopted(agent):
                self.application_seen = True

    def finish(self, agent, span, state, **fields):
        if span is None or not self.scope._tool_current(agent):
            return
        timing = self._clock_end(span)
        with self.scope.live.event_stream.lock, self.scope.lock:
            if not self.scope.closed and self.scope.current() and self.scope.adopted(agent):
                span.record.update(state=state, **timing, **fields)

    def update(self, agent, span, **fields):
        if span is None or not self.scope._tool_current(agent):
            return
        with self.scope.live.event_stream.lock, self.scope.lock:
            if not self.scope.closed and self.scope.current() and self.scope.adopted(agent):
                span.record.update(fields)

    def check_provider_client(self, agent, span):
        """Observe the original factory return without changing its client.

        Conflict and loss are sticky within this dispatch. A later factory
        return or restored mutable label cannot erase an earlier failed join.
        """
        if span is None or not self.scope._tool_current(agent):
            return
        actual = _runtime_provider(agent)
        with self.scope.live.event_stream.lock, self.scope.lock:
            if self.scope.closed or not self.scope.current() or not self.scope.adopted(agent):
                return
            selected = span.record["runtime_provider"]
            previous = span.record["provider_client_check"]
            if previous == "conflicting":
                return
            if actual["status"] == selected["status"] == "observed_digest":
                observed = "matched" if actual == selected else "conflicting"
            else:
                observed = "unavailable"
            if previous == "unavailable" and observed == "matched":
                observed = "unavailable"
            span.record["provider_client_check"] = observed

    def seal_execution(self, outcome):
        """Called only under the original scope/event locks, before closing."""
        wall = duration = None
        try:
            wall, mono = _clock()
            if self.start_ns is not None:
                duration = (mono - self.start_ns) // 1_000_000
                if duration < 0:
                    duration = None
                    self.errors.add("clock_regression")
            if self.execution["started_at_ms"] is not None and wall < self.execution["started_at_ms"]:
                self.errors.add("clock_regression")
        except Exception:
            self.errors.add("clock_unavailable")
        self.execution.update(outcome=outcome, finished_at_ms=wall, duration_ms=duration)
        if self.credential_scope is not None:
            try:
                self.credential_scope.close()
            except Exception:
                self.errors.add("transport_observation_failed")
                try:
                    self.credential_scope.discard()
                except Exception:
                    pass  # Never replace the original terminal outcome.

    def observe_execution_end(self):
        """Process I/O follows sealing, outside the original event/scope locks."""
        errors = set()
        try:
            end = _process(self.scope.binding.launch)
        except Exception:
            end = {"status": "unavailable"}
            errors.add("process_observation_unavailable")
        start = self.execution["process_start"]
        same = start == end if start["status"] == end["status"] == "observed" else None
        if same is False:
            errors.add("process_changed")
        with self.scope.lock:
            if self.scope.closed:
                self.errors.update(errors)
                self.execution.update(process_end=end, same_process=same)

    def document(self, *, force_empty=False):
        from .native_application_observation import STAGE as APPLICATION_STAGE, CLIENT_SHA256
        value = {
            "schema": SCHEMA, "coverage": COVERAGE, "http_stage": HTTP_STAGE,
            "installation": self.installation.description(), "complete_evaluation": False,
            "provider_delivery_proven": False, "model_identity_verified": False,
            "execution": self.execution, "calls": [] if force_empty else self.calls,
            "dispatches": [] if force_empty else self.dispatches,
            "attempts": [] if force_empty else self.attempts,
            "errors": sorted(self.errors), "overflow": self.overflow or force_empty,
        }
        if self.application_seen:
            value.update(schema=APPLICATION_SCHEMA, coverage=APPLICATION_COVERAGE,
                         application_stage=APPLICATION_STAGE, application_client_source_sha256=CLIENT_SHA256,
                         application_attempts=[] if force_empty else self.application_attempts)
        return copy.deepcopy(value)


class _Dispatch:
    def __init__(self, contribution, agent, span, task_id=None):
        self.contribution, self.agent, self.span = contribution, agent, span
        self.task_id = task_id
        self.client = None
        self.credential = None
        try:
            self.credential = (contribution.credential_scope.dispatch(agent)
                               if contribution.credential_scope is not None else None)
        except Exception:
            contribution.error("transport_observation_failed")
        self.failed = False
        self.responses = []  # Bounded by the retained attempt budget; never persisted.


class Installation:
    def __init__(self, binding, *, reason=None, commit=None, current=None):
        self.binding, self.reason, self._commit = binding, reason, commit
        self._current = current
        self.credential_installation = None

    def bind_credentials(self, vendor, profile):
        if self.credential_installation is not None or not self.registered_current():
            return
        from integrations.hermes_harness.native_model_credential import prepare_native_credential_observation
        self.binding.launch.check()
        selected = prepare_native_credential_observation(self.binding, vendor, profile)
        self.credential_installation = selected
        selected.commit()

    def registered_current(self):
        return self.reason is None and self._current is not None and self._current()

    def description(self):
        return ({"status": "unavailable", "reason": self.reason} if self.reason else
                {"status": "qualified", "httpx_client_source_sha256": HTTPX_SOURCE_SHA256})

    def commit(self):
        if self._commit is not None:
            self._commit()


def prepare(binding, vendor):
    """Qualify all seams before any mutation. Unavailable closes only this leaf."""
    from .native_gateway_entry import _digest, _vendor_module
    from .native_request_observation import _original_function
    try:
        modules = {}
        for path, expected in SOURCE_SHA256.items():
            if _digest(vendor / path, maximum=512 * 1024) != expected:
                return Installation(binding, reason="native_source_unqualified")
            name = path.removesuffix(".py").replace("/", ".")
            module = _vendor_module(name, vendor)
            if type(module) is not ModuleType:
                return Installation(binding, reason="native_seam_unqualified")
            modules[name] = module
        calls, helpers = modules["agent.turn_api_call"], modules["agent.chat_completion_helpers"]
        conversation = modules["agent.conversation_loop"]
        call = _original_function(calls, "perform_api_call")
        if conversation.perform_api_call is not call:
            return Installation(binding, reason="native_seam_unqualified")
        dispatch = _original_function(helpers, "_dispatch_nonstreaming_api_request")
        _original_function(helpers, "_context_thread_target")
        import httpx
        import httpx._client as client_module
        client_class = httpx.Client
        client_file = Path(client_module.__file__).resolve(strict=True)
        if (_digest(client_file, maximum=128 * 1024) != HTTPX_SOURCE_SHA256
                or client_class is not client_module.Client):
            return Installation(binding, reason="httpx_source_unqualified")
        original_methods = {}
        for name in ("send", "_send_handling_auth", "_send_handling_redirects", "_send_single_request"):
            method = getattr(client_class, name)
            if (not inspect.isfunction(method) or method.__globals__ is not vars(client_module)
                    or Path(method.__code__.co_filename).resolve() != client_file):
                return Installation(binding, reason="httpx_seam_unqualified")
            original_methods[name] = method
        if (getattr(calls, "_mmx_transport_observation_bound", False)
                or getattr(helpers, "_mmx_transport_observation_bound", False)
                or getattr(client_module, "_mmx_transport_observation_bound", False)):
            return Installation(binding, reason="original_binding_retained")
    except Exception:
        return Installation(binding, reason="transport_source_unavailable")

    from .native_application_observation import qualify as qualify_application
    application_source = qualify_application()

    def scope():
        value = _observation()._current.get()
        return value if value is not None and value.binding is binding else None

    def transport_context():
        # This guard observes only ownership, never a request or response. Keep
        # the original invocation outside the try so it cannot be replayed if
        # the transport itself raises.
        try:
            context, owner = _dispatch_context.get(), scope()
            if owner is not None:
                if context is not None and context.contribution is owner.transport:
                    return context
                owner.transport.observe_unbound_transport()
        except Exception:
            # No weaker error() fallback: it cannot verify stale ownership.
            pass
        return None

    def note(contribution, method, *args, **kwargs):
        try:
            return getattr(contribution, method)(*args, **kwargs)
        except Exception:
            contribution.error("transport_observation_failed")
            return None

    def credential_failure(context):
        # A failed optional callback cannot replace the original outcome or
        # leave an earlier matched record eligible for publication.
        try:
            if context.credential is not None:
                context.credential.discard()
        except Exception:
            pass
        try:
            context.contribution.error("transport_observation_failed")
            note(context.contribution, "update", context.agent, context.span,
                 auth_client_check="unavailable")
        except Exception:
            pass

    def current():
        return (calls.perform_api_call is observed_call
                and conversation.perform_api_call is observed_call
                and helpers._dispatch_nonstreaming_api_request is observed_dispatch
                and client_class._send_single_request is observed_single
                and all(getattr(client_class, name) is method for name, method in original_methods.items()
                        if name != "_send_single_request"))

    @wraps(call)
    def observed_call(agent, **kwargs):
        owner = scope()
        if owner is None:
            return call(agent, **kwargs)
        contribution = owner.transport
        span = note(contribution, "begin", "call", agent, identifiers=kwargs)
        token = _call_context.set((owner, span))
        state = "raised"
        try:
            result = call(agent, **kwargs)
            state = "returned"
            return result
        finally:
            _call_context.reset(token)
            note(contribution, "finish", agent, span, state)

    def observed_dispatch(agent, api_kwargs, *, make_client):
        owner = scope()
        if owner is None:
            return dispatch(agent, api_kwargs, make_client=make_client)
        if owner.evaluation is not None:
            # Execution middleware may change/repeat an earlier assembly. The
            # selected input fence belongs to this original dispatch boundary,
            # outside observation's fail-open policy and before client use.
            owner.evaluation.require_request(agent, api_kwargs)
        contribution = owner.transport
        caller = _call_context.get()
        caller_span = caller[1] if caller is not None and caller[0] is owner else None
        if caller_span is None:
            contribution.error("unbound_logical_call")
        span = note(contribution, "begin", "dispatch", agent,
                    caller=caller_span)
        context = _Dispatch(contribution, agent, span, caller_span.task_id if caller_span is not None else None)
        qualified = (current() and getattr(agent, "api_mode", None) == "chat_completions"
                     and getattr(agent, "provider", None) != "moa")
        if not qualified:
            contribution.error("unsupported_dispatch" if current() else "transport_binding_changed")
            note(contribution, "update", agent, span, client_binding="unsupported")

        def original_client(*args, **kwargs):
            # The original factory owns creation and its exceptions. Nothing
            # observed afterwards may replace its returned object or outcome.
            client = make_client(*args, **kwargs)
            if qualified and not context.failed:
                try:
                    is_application = (application_source is not None
                        and type(client) is application_source.client)
                    if is_application:
                        supported = current() and application_source.client_current(client, observed_application)
                        transport_client = client
                    else:
                        transport_client = getattr(client, "_client", None)
                        supported = (isinstance(transport_client, client_class) and current()
                            and all(getattr(getattr(transport_client, name, None), "__func__", None)
                                    is (observed_single if name == "_send_single_request" else method)
                                    for name, method in original_methods.items()))
                except Exception:
                    transport_client, supported = None, False
                if not supported or (context.client is not None and context.client is not transport_client):
                    previous = context.client is not None
                    context.client = None
                    context.failed = True
                    contribution.error("multiple_clients" if previous else "unsupported_client")
                    note(contribution, "update", agent, span, client_binding="multiple" if previous else "unsupported")
                else:
                    context.client = transport_client
                    note(contribution, "check_provider_client", agent, span)
                    note(contribution, "update", agent, span,
                         client_binding="qualified_application" if is_application else "qualified_sync_httpx")
                    if is_application:
                        note(contribution, "mark_application", agent)
                        note(contribution, "update", agent, span, auth_client_check="unavailable")
                    if context.credential is not None and not is_application:
                        try:
                            context.credential.bind(client)
                            note(contribution, "update", agent, span,
                                 auth_client_check=context.credential.client_status())
                        except Exception:
                            credential_failure(context)
            return client

        token = _dispatch_context.set(context)
        state = "raised"
        try:
            result = dispatch(agent, api_kwargs, make_client=original_client)
            state = "returned"
            return result
        finally:
            _dispatch_context.reset(token)
            for attempt, response in context.responses:
                try:
                    projected = _response_projection(response, consumed=True)
                    note(contribution, "update", agent, attempt, response=projected)
                except Exception:
                    contribution.error("response_metadata_unavailable")
            context.responses.clear()
            if context.credential is not None:
                try:
                    status = ("unavailable" if application_source is not None
                              and type(context.client) is application_source.client
                              else context.credential.client_status())
                    note(contribution, "update", agent, span, auth_client_check=status)
                except Exception:
                    credential_failure(context)
                finally:
                    try:
                        context.credential.close()
                    except Exception:
                        credential_failure(context)
            note(contribution, "finish", agent, span, state)

    def observed_application(client, **kwargs):
        context = transport_context()
        if context is None:
            return application_source.create(client, **kwargs)
        contribution, agent = context.contribution, context.agent
        snapshot, attempt = None, None
        try:
            if (context.failed or context.client is not client or context.span is None
                    or not current() or not application_source.client_current(client, observed_application)):
                raise ValueError("application binding changed")
            snapshot = application_source.snapshot(context, kwargs)
            attempt = note(contribution, "begin", "application", agent,
                dispatch_sequence=context.span.record["sequence"], request=snapshot[2])
        except Exception:
            contribution.error("application_identity_unavailable")
        try:
            result = application_source.create(client, **kwargs)
        except BaseException:
            note(contribution, "finish", agent, attempt, "raised")
            raise
        projected = None
        try:
            if (snapshot is None or not current() or context.failed
                    or not application_source.client_current(client, observed_application)
                    or not application_source.unchanged(snapshot)):
                raise ValueError("application return binding changed")
            projected = application_source.project(result, snapshot)
        except Exception:
            contribution.error("application_return_unavailable")
        note(contribution, "finish", agent, attempt,
             "returned" if projected is not None else "returned_unobserved", response=projected)
        return result

    original_single = original_methods["_send_single_request"]
    def observed_single(client, request):
        context = transport_context()
        if context is None:
            return original_single(client, request)
        contribution, agent, dispatch_span = context.contribution, context.agent, context.span
        if context.client is not client or dispatch_span is None or not current():
            contribution.error("client_changed" if current() else "transport_binding_changed")
            return original_single(client, request)
        attempt = note(contribution, "begin", "attempt", agent,
                       dispatch_sequence=dispatch_span.record["sequence"], request=request)
        if context.credential is not None:
            try:
                mechanism = context.credential.mechanism(client, request)
                note(contribution, "update", agent, attempt, auth_mechanism=mechanism)
            except Exception:
                credential_failure(context)
        try:
            response = original_single(client, request)
        except BaseException:
            note(contribution, "finish", agent, attempt, "raised")
            raise
        if type(response) is httpx.Response:
            try:
                projected = _response_projection(response)
                note(contribution, "finish", agent, attempt, "headers_returned", response=projected)
                if attempt is not None:
                    context.responses.append((attempt, response))
            except Exception:
                contribution.error("response_metadata_unavailable")
                note(contribution, "finish", agent, attempt, "headers_unobserved")
        else:
            contribution.error("response_metadata_unavailable")
            note(contribution, "finish", agent, attempt, "headers_unobserved")
        return response

    def commit():
        binding.launch.check()
        if (calls.perform_api_call is not call or conversation.perform_api_call is not call
                or helpers._dispatch_nonstreaming_api_request is not dispatch
                or any(getattr(client_class, name) is not method for name, method in original_methods.items())
                or application_source is not None and not application_source.current(application_source.create)):
            raise RuntimeRefusal("NATIVE_TRANSPORT_ORIGINAL_BINDING_CHANGED")
        # All objects are qualified native modules/classes, with no user setter.
        # A partial exceptional install is never retried or reported unavailable.
        calls.perform_api_call = observed_call
        conversation.perform_api_call = observed_call
        helpers._dispatch_nonstreaming_api_request = observed_dispatch
        client_class._send_single_request = observed_single
        if application_source is not None:
            application_source.client.create = observed_application
        calls._mmx_transport_observation_bound = True
        helpers._mmx_transport_observation_bound = True
        client_module._mmx_transport_observation_bound = True

    return Installation(binding, commit=commit, current=current)


def _shape(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("invalid transport observation")


def _text(value):
    if not _observation()._text(value):
        raise ValueError("invalid transport label")


def _integer(value, *, positive=False, optional=False):
    if value is None and optional:
        return
    if not _observation()._integer(value) or positive and value == 0:
        raise ValueError("invalid transport integer")


def _digest(value, *, optional=False):
    if value is None and optional:
        return
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("invalid transport digest")


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError("invalid transport state")


def _validate_scalar(value, kind, *, conflict=False):
    if type(value) is not dict:
        raise ValueError("invalid scalar observation")
    status = value.get("status")
    choices = {"unobserved", "absent", "null", "invalid", "present"}
    if kind == "model":
        choices.remove("present")
        choices.add("observed_digest")
    if kind == "effort":
        choices.add("unrecognized_digest")
    if conflict:
        choices.add("conflicting")
    _enum(status, choices)
    if status in {"observed_digest", "unrecognized_digest"}:
        _shape(value, ("status", "sha256", "bytes"))
        _digest(value["sha256"])
        _integer(value["bytes"], positive=True)
        if value["bytes"] > 256:
            raise ValueError("observed label byte bound")
        return
    _shape(value, ("status", "value") if status == "present" else ("status",))
    if status == "present":
        if _scalar(value["value"], kind) != value:
            raise ValueError("invalid observed scalar")


def _validate_process(value):
    if type(value) is not dict:
        raise ValueError("invalid process observation")
    if value.get("status") == "unavailable":
        _shape(value, ("status",))
        return
    _shape(value, ("status", "facts", "fingerprint"))
    _enum(value["status"], {"observed"})
    facts = value["facts"]
    _shape(facts, ("pid", "boot_id", "start_identity", "real_uid", "effective_uid", "real_gid",
                   "effective_gid", "image_sha256", "release_sha", "manifest_sha256"))
    _integer(facts["pid"], positive=True)
    for key in ("real_uid", "effective_uid", "real_gid", "effective_gid"):
        _integer(facts[key])
    if type(facts["start_identity"]) is not str or re.fullmatch(r"[0-9]{1,20}", facts["start_identity"]) is None:
        raise ValueError("invalid process birth ticks")
    if type(facts["boot_id"]) is not str or _BOOT.fullmatch(facts["boot_id"]) is None:
        raise ValueError("invalid observed boot")
    if type(facts["release_sha"]) is not str or _SHA.fullmatch(facts["release_sha"]) is None:
        raise ValueError("invalid observed release")
    for key in ("image_sha256", "manifest_sha256"):
        _digest(facts[key])
    if value["fingerprint"] != _hash(facts):
        raise ValueError("process observation changed")


def _validate_timing(record):
    for key in ("started_at_ms", "finished_at_ms", "duration_ms"):
        _integer(record[key], optional=True)
    if record["duration_ms"] is not None and (record["started_at_ms"] is None or record["finished_at_ms"] is None):
        raise ValueError("invalid observed timing")


def _validate_request(value):
    _shape(value, ("method", "origin_sha256", "body_state", "body_sha256", "body_bytes",
                   "content_sha256", "content_fields", "tools_sha256", "tools_state",
                   "explicit_sampling_sha256", "sampling_fields", "model", "seed", "reasoning_effort"))
    if value["method"] is not None:
        _enum(value["method"], {"GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"})
    _digest(value["origin_sha256"])
    _enum(value["body_state"], {"unavailable", "oversized", "unqualified_json", "observed_json_object"})
    _integer(value["body_bytes"], optional=True)
    for key in ("body_sha256", "content_sha256", "tools_sha256", "explicit_sampling_sha256"):
        _digest(value[key], optional=True)
    _enum(value["tools_state"], {"unobserved", "absent", "observed", "unavailable"})
    _validate_scalar(value["model"], "model")
    _validate_scalar(value["seed"], "integer")
    _validate_scalar(value["reasoning_effort"], "effort", conflict=True)
    observed = value["body_state"] == "observed_json_object"
    for key, choices in (("content_fields", _observation().CONTENT_FIELDS), ("sampling_fields", SAMPLING_FIELDS)):
        fields = value[key]
        if observed:
            if type(fields) is not list or fields != [name for name in choices if name in fields]:
                raise ValueError("invalid explicit field projection")
        elif fields is not None:
            raise ValueError("unobserved wire fields")
    if observed:
        if any(value[key] is None for key in ("body_sha256", "body_bytes", "content_sha256", "explicit_sampling_sha256")):
            raise ValueError("incomplete JSON observation")
        if any(value[key]["status"] == "unobserved" for key in ("model", "seed", "reasoning_effort")):
            raise ValueError("incomplete scalar observation")
        if value["tools_state"] == "unobserved" or (value["tools_state"] == "observed") != (value["tools_sha256"] is not None):
            raise ValueError("incomplete tools observation")
    elif (any(value[key] is not None for key in ("content_sha256", "tools_sha256", "explicit_sampling_sha256"))
          or value["tools_state"] != "unobserved"
          or any(value[key] != {"status": "unobserved"} for key in ("model", "seed", "reasoning_effort"))):
        raise ValueError("invented wire fields")
    size, digest = value["body_bytes"], value["body_sha256"]
    if value["body_state"] == "unavailable" and (size is not None or digest is not None):
        raise ValueError("unavailable request has bytes")
    if value["body_state"] in {"unqualified_json", "observed_json_object"} and (size is None or digest is None):
        raise ValueError("observed request missing bytes")
    if digest is not None and (size is None or size > _observation().MAX_CONTENT_BYTES):
        raise ValueError("wire byte bound")
    if value["body_state"] == "oversized" and (size is None or size <= _observation().MAX_CONTENT_BYTES or digest is not None):
        raise ValueError("invalid oversized wire record")


def _validate_response(value):
    _shape(value, ("status_code", "body_state", "body_sha256", "body_bytes", "reported_model"))
    if type(value["status_code"]) is not int or not 100 <= value["status_code"] <= 599:
        raise ValueError("invalid HTTP status")
    _enum(value["body_state"], {"not_observed", "unconsumed", "unavailable", "oversized",
                                "consumed_unqualified_json", "consumed_json_object"})
    _digest(value["body_sha256"], optional=True)
    _integer(value["body_bytes"], optional=True)
    _validate_scalar(value["reported_model"], "model")
    consumed = value["body_state"] in {"consumed_unqualified_json", "consumed_json_object"}
    if consumed != (value["body_sha256"] is not None):
        raise ValueError("response consumption disagreement")
    if consumed and (value["body_bytes"] is None or value["body_bytes"] > _observation().MAX_CONTENT_BYTES):
        raise ValueError("response byte bound")
    if value["body_state"] == "oversized":
        if value["body_bytes"] is None or value["body_bytes"] <= _observation().MAX_CONTENT_BYTES:
            raise ValueError("invalid oversized response")
    elif not consumed and value["body_bytes"] is not None:
        raise ValueError("unobserved response has bytes")
    if value["body_state"] != "consumed_json_object" and value["reported_model"] != {"status": "unobserved"}:
        raise ValueError("unobserved response model")
    if value["body_state"] == "consumed_json_object" and value["reported_model"] == {"status": "unobserved"}:
        raise ValueError("incomplete response model")


def validate_document(value):
    """Closed historical projection, never a claim of producer authenticity."""
    application_observed = type(value) is dict and value.get("schema") == APPLICATION_SCHEMA
    extra = ("application_stage", "application_client_source_sha256", "application_attempts") if application_observed else ()
    _shape(value, ("schema", "coverage", "http_stage", "installation", "complete_evaluation",
                   "provider_delivery_proven", "model_identity_verified", "execution", "calls",
                   "dispatches", "attempts", "errors", "overflow", *extra))
    _enum(value["schema"], {*PROVIDER_SCHEMAS, PREVIOUS_SCHEMA, APPLICATION_SCHEMA})
    provider_observed = value["schema"] in PROVIDER_SCHEMAS or application_observed
    auth_observed = value["schema"] == SCHEMA or application_observed
    if application_observed:
        from .native_application_observation import STAGE as APPLICATION_STAGE, CLIENT_SHA256
        _enum(value["application_stage"], {APPLICATION_STAGE})
        _enum(value["application_client_source_sha256"], {CLIENT_SHA256})
    for key, expected in (("coverage", APPLICATION_COVERAGE if application_observed else COVERAGE), ("http_stage", HTTP_STAGE)):
        _enum(value[key], {expected})
    if any(value[key] is not False for key in ("complete_evaluation", "provider_delivery_proven", "model_identity_verified")):
        raise ValueError("unsupported evidence promotion")
    if type(value["overflow"]) is not bool:
        raise ValueError("invalid transport overflow")
    installation = value["installation"]
    if type(installation) is not dict:
        raise ValueError("invalid installation projection")
    if installation.get("status") == "qualified":
        _shape(installation, ("status", "httpx_client_source_sha256"))
        _enum(installation["httpx_client_source_sha256"], {HTTPX_SOURCE_SHA256})
    else:
        _shape(installation, ("status", "reason"))
        _enum(installation["status"], {"unavailable"})
        _enum(installation["reason"], {"native_source_unqualified", "native_seam_unqualified",
              "httpx_source_unqualified", "httpx_seam_unqualified", "original_binding_retained",
              "transport_source_unavailable"})
    errors = value["errors"]
    if type(errors) is not list or any(type(e) is not str or e not in ERRORS for e in errors) or errors != sorted(set(errors)):
        raise ValueError("invalid transport error projection")
    execution = value["execution"]
    _shape(execution, ("stage", "outcome", "started_at_ms", "finished_at_ms", "duration_ms",
                       "process_start", "process_end", "same_process"))
    _enum(execution["stage"], {EXECUTION_STAGE})
    _enum(execution["outcome"], {"unobserved", "returned", "raised"})
    _validate_timing(execution)
    _validate_process(execution["process_start"])
    _validate_process(execution["process_end"])
    both = execution["process_start"]["status"] == execution["process_end"]["status"] == "observed"
    expected_same = execution["process_start"] == execution["process_end"] if both else None
    if type(execution["same_process"]) is not type(expected_same) or execution["same_process"] != expected_same:
        raise ValueError("process comparison disagreement")
    if (not both and "process_observation_unavailable" not in errors
            or expected_same is False and "process_changed" not in errors):
        raise ValueError("missing process observation error")
    counts = {}
    for kind, maximum in (("calls", MAX_CALLS), ("dispatches", MAX_DISPATCHES), ("attempts", MAX_ATTEMPTS)):
        records = value[kind]
        if type(records) is not list or len(records) > maximum:
            raise ValueError("transport record bound")
        counts[kind] = len(records)
        for sequence, record in enumerate(records, 1):
            common = ("sequence", "state", "started_at_ms", "finished_at_ms", "duration_ms")
            fields = (("dispatch_sequence", "request", "response") if kind == "attempts" else
                      ("identity", "invalid_fields", "api_call_count", "retry_count") if kind == "calls" else
                      ("identity", "invalid_fields", "call_sequence", "client_binding"))
            if provider_observed and kind != "calls":
                fields += ("runtime_provider",)
                if kind == "dispatches":
                    fields += ("provider_client_check",)
            if auth_observed and kind != "calls":
                fields += ("auth_mechanism",) if kind == "attempts" else ("auth_client_check",)
            _shape(record, (*common, *fields))
            if auth_observed and kind != "calls":
                _enum(record["auth_mechanism"] if kind == "attempts" else record["auth_client_check"],
                      {"API_KEY", "unavailable", "conflicting"} if kind == "attempts" else
                      {"pending", "matched", "unavailable", "conflicting"})
                if (kind == "dispatches" and record["auth_client_check"] == "matched"
                        and record["client_binding"] != "qualified_sync_httpx"):
                    raise ValueError("credential witness without original client")
            if provider_observed and kind != "calls":
                _validate_scalar(record["runtime_provider"], "model")
            if type(record["sequence"]) is not int or record["sequence"] != sequence:
                raise ValueError("transport sequence disagreement")
            _enum(record["state"], {"entered", "raised", "headers_returned", "headers_unobserved"}
                  if kind == "attempts" else {"entered", "raised", "returned"})
            _validate_timing(record)
            if record["state"] == "entered" and any(record[key] is not None for key in ("finished_at_ms", "duration_ms")):
                raise ValueError("unfinished record has terminal time")
            if kind == "attempts":
                _integer(record["dispatch_sequence"], positive=True)
                if record["dispatch_sequence"] > counts["dispatches"]:
                    raise ValueError("foreign dispatch")
                dispatch = value["dispatches"][record["dispatch_sequence"] - 1]
                if dispatch["client_binding"] not in {"qualified_sync_httpx", "multiple"}:
                    raise ValueError("attempt without qualified client")
                _validate_request(record["request"])
                if (record["state"] == "headers_returned") != (record["response"] is not None):
                    raise ValueError("returned headers disagreement")
                if record["state"] == "headers_unobserved" and "response_metadata_unavailable" not in errors:
                    raise ValueError("missing response metadata error")
                if record["response"] is not None:
                    _validate_response(record["response"])
                    if record["state"] != "headers_returned":
                        raise ValueError("response without returned headers")
            else:
                identity = record["identity"]
                if type(identity) is not dict or any(key not in IDENTIFIERS for key in identity):
                    raise ValueError("invalid native request identity")
                for item in identity.values():
                    _text(item)
                invalid = record["invalid_fields"]
                if (type(invalid) is not list or any(type(key) is not str or key not in IDENTIFIERS or key in identity for key in invalid)
                        or len(invalid) != len(set(invalid))):
                    raise ValueError("invalid missing native identity")
                if kind == "calls":
                    _integer(record["api_call_count"], optional=True)
                    _integer(record["retry_count"], optional=True)
                else:
                    _integer(record["call_sequence"], positive=True, optional=True)
                    if record["call_sequence"] is not None and record["call_sequence"] > counts["calls"]:
                        raise ValueError("foreign logical call")
                    if record["call_sequence"] is not None:
                        call = value["calls"][record["call_sequence"] - 1]
                        if record["identity"] != call["identity"] or record["invalid_fields"] != call["invalid_fields"]:
                            raise ValueError("logical call identity disagreement")
                    elif "unbound_logical_call" not in errors:
                        raise ValueError("missing unbound call error")
                    _enum(record["client_binding"], {"pending", "unsupported", "multiple", "qualified_sync_httpx"}
                          | ({"qualified_application"} if application_observed else set()))
                    if record["client_binding"] == "multiple" and "multiple_clients" not in errors:
                        raise ValueError("missing multiple-client error")
                    if provider_observed:
                        check = record["provider_client_check"]
                        _enum(check, {"pending", "matched", "unavailable", "conflicting"})
                        if check in {"matched", "conflicting"} and record["runtime_provider"]["status"] != "observed_digest":
                            raise ValueError("unobserved runtime provider comparison")
    if application_observed:
        from .native_application_observation import validate_entry, validate_return
        records = value["application_attempts"]
        if type(records) is not list or len(records) + counts["attempts"] > MAX_ATTEMPTS:
            raise ValueError("shared transport attempt bound")
        counts["application_attempts"] = len(records)
        for sequence, record in enumerate(records, 1):
            _shape(record, ("sequence", "state", "started_at_ms", "finished_at_ms", "duration_ms",
                           "dispatch_sequence", "request", "response", "runtime_provider"))
            if type(record["sequence"]) is not int or record["sequence"] != sequence:
                raise ValueError("application sequence disagreement")
            _enum(record["state"], {"entered", "raised", "returned", "returned_unobserved"})
            _validate_timing(record)
            if record["state"] == "entered" and any(record[key] is not None for key in ("finished_at_ms", "duration_ms")):
                raise ValueError("unfinished application terminal time")
            _integer(record["dispatch_sequence"], positive=True)
            if record["dispatch_sequence"] > counts["dispatches"]:
                raise ValueError("foreign application dispatch")
            dispatch = value["dispatches"][record["dispatch_sequence"] - 1]
            if dispatch["client_binding"] not in {"qualified_application", "multiple"}:
                raise ValueError("application without qualified client")
            validate_entry(record["request"])
            native = record["request"]["native_identity"]
            if dispatch["identity"] != {"agent_session_id": native["session_id"],
                    "turn_id": native["turn_id"], "api_request_id": native["api_request_id"]}:
                raise ValueError("application native identity disagreement")
            _validate_scalar(record["runtime_provider"], "model")
            if (record["state"] == "returned") != (record["response"] is not None):
                raise ValueError("application returned evidence disagreement")
            if record["state"] == "returned_unobserved" and "application_return_unavailable" not in errors:
                raise ValueError("application unavailable evidence unmarked")
            if record["response"] is not None:
                validate_return(record["response"], record["request"])
    if installation["status"] == "unavailable" and any(counts.values()):
        raise ValueError("records from unavailable instrumentation")
    if _observation()._encoded_size(value) > _observation().MAX_METADATA_BYTES:
        raise ValueError("transport metadata bound")
    return copy.deepcopy(value)
