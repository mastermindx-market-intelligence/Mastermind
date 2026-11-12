"""Pinned caller/worker/dispatch bodies and actual HTTPX/OpenAI with in-process I/O.

Admission, phase dependencies, process custody and watchdog registry edges are
declared fixtures. No socket, provider, account, host service or EVAL is used.
"""
import ast
import asyncio
import contextlib
import contextvars
import copy
from dataclasses import dataclass, fields
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from typing import Any, Optional
import uuid

import httpx
import pytest

from integrations.hermes_runtime import native_request_observation as observation
from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime import native_transport_observation as transport
from integrations.hermes_runtime.tests.test_native_request_observation import module, native, run_admission

FIXTURES = Path(__file__).parent / "fixtures/transport_observation"
MANIFEST = json.loads((FIXTURES / "provenance.json").read_text())


def source(native, monkeypatch, path, names=None, *, values=None, methods=None):
    item = MANIFEST["files"][path]
    data = (FIXTURES / item["fixture"]).read_bytes()
    assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
    assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == item["blob"]
    target = native.vendor / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    # Match the incumbent pinned-source fixture regardless of the runner umask.
    # The production source owner still rejects group/other-writable input.
    target.chmod(0o644)
    name = path.removesuffix(".py").replace("/", ".")
    result = module(monkeypatch, name, __file__=str(target), **(values or {}))
    if names is None:
        code = data
    else:
        selected = [node for node in ast.parse(data).body if getattr(node, "name", None) in names]
        assert {node.name for node in selected} == names
        if methods:
            for node in selected:
                if isinstance(node, ast.ClassDef):
                    node.body = [child for child in node.body if getattr(child, "name", None) in methods]
        code = ast.Module(body=selected, type_ignores=[])
    exec(compile(code, str(target), "exec"), vars(result))
    return result


@dataclass
class PhaseVerdict:
    action: str = "fallthrough"


@pytest.fixture
def engine(native, monkeypatch):
    def raise_phase_error(agent, *, api_error):
        raise api_error
    bypass = source(native, monkeypatch, "agent/sdk_transform_bypass.py")
    headers = source(native, monkeypatch, "agent/chat_completion_headers.py")
    helpers = source(native, monkeypatch, "agent/chat_completion_helpers.py",
        {"_dispatch_nonstreaming_api_request", "_context_thread_target"}, values={
            "contextvars": contextvars, "bypass_chat_sdk_request_transform": bypass.bypass_chat_sdk_request_transform,
            "_chat_completion_capturing_headers": headers._chat_completion_capturing_headers,
            "logger": logging.getLogger(__name__)})
    worker = source(native, monkeypatch, "agent/chat_completion_nonstream.py", {"_NonStreamRequest"},
        methods={"_make_client", "_call", "_install_codex_request_token", "_retire_codex_request_token"},
        values={"h": helpers})
    calls = source(native, monkeypatch, "agent/turn_api_call.py",
        {"ApiCallVerdict", "_should_stream", "perform_api_call", "stop_thinking_spinner"},
        values={"dataclass": dataclass, "Any": Any, "nullcontext": contextlib.nullcontext})
    conversation = source(native, monkeypatch, "agent/conversation_loop.py", {"_run_phase", "_run_api_retry_loop"},
        values={**{k: v for k, v in vars(sys.modules["agent.conversation_loop"]).items() if not k.startswith("__")},
            "_LoopState": object, "Any": Any, "Optional": Optional, "inspect": inspect, "fields": fields,
            "_PHASE_PARAMS": {}, "_LATCHED_VERDICT_FIELDS": {},
            "perform_api_call": calls.perform_api_call,
            "nous_rate_limit_guard": lambda agent: PhaseVerdict(),
            "build_api_request": lambda agent: PhaseVerdict(),
            "handle_api_error": raise_phase_error,
            "check_api_response": lambda agent: PhaseVerdict("break")})
    # Real donor import statement establishes the cached caller alias.
    imports = [n for n in ast.parse((native.vendor / "agent/conversation_loop.py").read_text()).body
               if isinstance(n, ast.ImportFrom) and n.module == "agent.turn_api_call"]
    assert len(imports) == 1
    monkeypatch.setattr(calls, "handle_api_interrupt", lambda **kw: None, raising=False)
    monkeypatch.setattr(calls, "nous_rate_limit_guard", conversation.nous_rate_limit_guard, raising=False)
    exec(compile(ast.Module(body=imports, type_ignores=[]), conversation.__file__, "exec"), vars(conversation))
    module(monkeypatch, "agent.relay_llm", execute=lambda payload, next_call, **kw: next_call(payload))
    middleware = sys.modules["hermes_cli.middleware"]
    monkeypatch.setattr(middleware, "run_llm_execution_middleware", lambda payload, next_call, **kw: next_call(payload), raising=False)

    # Restore global HTTPX hooks after each isolated qualification fixture.
    import httpx._client as client_module
    monkeypatch.setattr(httpx.Client, "_send_single_request", httpx.Client._send_single_request)
    monkeypatch.setattr(client_module, "_mmx_transport_observation_bound", False, raising=False)
    # Preserve a bounded cause for the production fail-closed source check.
    # Record only its line and exception class; no exception text or file data.
    qualification_errors = []
    previous_trace = sys.gettrace()
    def qualification_trace(frame, event, value):
        if event == "exception" and frame.f_code is transport.prepare.__code__:
            qualification_errors.append((frame.f_lineno, type(value[1]).__name__))
        return qualification_trace
    try:
        sys.settrace(qualification_trace)
        installation = transport.prepare(native.binding, native.vendor)
    finally:
        sys.settrace(previous_trace)
    assert installation.description()["status"] == "qualified", (installation.description(), qualification_errors)
    native.binding.transport_installation = installation
    installation.commit()
    assert conversation.perform_api_call is calls.perform_api_call
    assert "api_kwargs" in inspect.signature(conversation.perform_api_call).parameters

    boot = str(uuid.uuid4())
    process_calls = []
    native.launch.owner.root = Path("a" * 40)
    native.launch.owner.manifest_sha256 = lambda: "b" * 64
    def process(pid):
        assert pid == os.getpid()
        process_calls.append(pid)
        return {"boot_id": boot, "start_identity": "12345", "sha256": "c" * 64,
                "real_uid": os.getuid(), "effective_uid": os.geteuid(),
                "real_gid": os.getgid(), "effective_gid": os.getegid()}
    native.launch.observe_child = process
    native.helpers, native.worker, native.conversation, native.middleware = helpers, worker, conversation, middleware
    native.process_calls, native.cleanups, native.factories = process_calls, [], []

    def invoke(agent, payload, make_client, *, request_id="request-A", threaded=True,
               native_client_lifecycle=False, turn_id="turn-A"):
        agent._disable_streaming = True
        agent._has_pending_redirect = lambda: False
        agent.thinking_callback = None
        agent._current_turn_id, agent._current_api_request_id = turn_id, request_id
        def call(payload):
            obj = worker._NonStreamRequest.__new__(worker._NonStreamRequest)
            obj.agent, obj.api_kwargs = agent, payload
            obj.result, obj.cancelled = {"response": None, "error": None}, False
            obj.codex_token, obj.codex_retired, obj.codex_watchdog_state = None, False, None
            clients = []
            def factory(**kwargs):
                native.factories.append(kwargs["reason"])
                value = make_client()
                return value
            if not native_client_lifecycle:
                agent._create_request_openai_client = factory
            def register(client, **kw):
                clients.append(client)
                return client
            def close(reason):
                native.cleanups.append(reason)
                for client in clients:
                    if native_client_lifecycle:
                        agent._close_request_openai_client(client, reason=reason)
                    else:
                        client.close()
            obj.clients = SimpleNamespace(set_client=register, close_once=close)
            if threaded:
                thread = threading.Thread(target=helpers._context_thread_target(obj._call))
                thread.start()
                thread.join(5)
                assert not thread.is_alive()
            else:
                obj._call()
            if obj.result["error"]:
                raise obj.result["error"]
            return obj.result["response"]
        agent._interruptible_api_call = call
        args = dict(api_kwargs=payload, _original_api_kwargs=copy.deepcopy(payload), _llm_middleware_trace=[],
            _moa_prepared_request=None, _retry=SimpleNamespace(), thinking_spinner=None, retry_count=0,
            api_call_count=1, api_request_id=request_id, effective_task_id="task-A", turn_id=turn_id, interrupted=False)
        state = SimpleNamespace(**args, max_retries=1)
        assert conversation._run_api_retry_loop(agent, state) is None
        return state.response
    native.invoke = invoke
    return native


def payload(**overrides):
    return {"model": "private-model-label", "messages": [{"role": "user", "content": "PRIVATE_PROMPT Ω\n"}],
            "tools": [{"type": "function", "function": {"name": "private_tool", "parameters": {"type": "object"}}}],
            "seed": 0, "reasoning_effort": "high", **overrides}


def success(model="reported-label"):
    return {"id": "fixture-completion", "object": "chat.completion", "created": 1, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "PRIVATE_OUTPUT"}, "finish_reason": "stop"}]}


def sdk(handler, *, retries=0):
    openai = pytest.importorskip("openai")
    return openai.OpenAI(api_key="PRIVATE_KEY", base_url="https://provider.invalid/v1/",
        max_retries=retries, http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))


def run_call(engine, make_client, *, request=None, behavior=None):
    request = payload() if request is None else request
    async def handle(ref, row, agent):
        response = engine.invoke(agent, request, make_client)
        if behavior:
            behavior(ref, row, agent, response)
        engine.results.execution_result.get()["result"] = {"final_response": "PRIVATE_OUTPUT", "completed": True, "messages": []}
        return "PRIVATE_OUTPUT"
    ref, row, agent, response = run_admission(engine, behavior=handle)
    return engine.authority.pending_results[row["admission_id"]][observation.RESULT_KEY], (ref, row, agent, response)


@pytest.mark.parametrize("retry_first,redirect", [(False, False), (True, False), (False, True)])
def test_actual_caller_sdk_retries_redirects_and_wire_bypass(engine, retry_first, redirect):
    pytest.importorskip("openai")
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        if retry_first and len(seen) == 1:
            return httpx.Response(500, headers={"retry-after-ms": "1"}, json={"error": {"message": "fixture"}})
        if redirect and len(seen) == 1:
            return httpx.Response(307, headers={"location": "https://provider.invalid/v1/redirected"})
        return httpx.Response(200, json=success())
    doc, _ = run_call(engine, lambda: sdk(handler, retries=1))
    value = doc["transport"]
    assert transport.validate_document(value) == value
    assert len(value["calls"]) == len(value["dispatches"]) == 1
    assert len(value["attempts"]) == len(seen) == (2 if retry_first or redirect else 1)
    assert len(engine.factories) == len(engine.cleanups) == 1
    assert engine.cleanups == ["request_complete"] and len(engine.process_calls) == 2
    assert value["execution"]["same_process"] is True
    assert value["execution"]["outcome"] == "returned"
    assert all(body["messages"] == payload()["messages"] and body["tools"] == payload()["tools"] for body in seen)
    for index, (event, body) in enumerate(zip(value["attempts"], seen)):
        assert event["state"] == "headers_returned"
        if redirect and index:
            # HTTPX rebuilds the redirect with the original stream. At entry
            # its new Request has no materialized .content; the real transport
            # consumes it later. Observation must not drain it to fill the gap.
            assert event["request"]["body_state"] == "unavailable"
            assert event["request"]["content_sha256"] is None
            assert event["request"]["seed"] == {"status": "unobserved"}
            continue
        assert event["request"]["content_sha256"] == observation._content_digest(body)["content_sha256"]
        assert event["request"]["tools_sha256"] == observation._tools_digest(body)["sha256"]
        assert event["request"]["seed"] == {"status": "present", "value": 0}
        assert event["request"]["reasoning_effort"] == {"status": "present", "value": "high"}
    assert value["attempts"][-1]["response"]["reported_model"] == transport._scalar("reported-label", "model")
    assert value["errors"] == []
    assert all(value[k] is False for k in ("complete_evaluation", "provider_delivery_proven", "model_identity_verified"))
    assert not any(secret in json.dumps(doc) for secret in ("PRIVATE_KEY", "PRIVATE_PROMPT", "PRIVATE_OUTPUT", "private_tool", "private-model-label", "provider.invalid"))


def facade(*, raising_property=False, on_create=None):
    class Facade:
        def __init__(self):
            self.closed = 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: on_create(kw) if on_create else success()))
        @property
        def _client(self):
            if raising_property:
                raise ValueError("PRIVATE_QUALIFICATION_FAILURE")
            return None
        def close(self):
            self.closed += 1
    return Facade()


def test_observer_property_failure_preserves_original_factory_result_and_cleanup(engine):
    client = facade(raising_property=True)
    doc, _ = run_call(engine, lambda: client)
    value = doc["transport"]
    assert client.closed == 1 and len(engine.factories) == 1 and engine.cleanups == ["request_complete"]
    assert value["calls"][0]["state"] == value["dispatches"][0]["state"] == "returned"
    assert value["dispatches"][0]["client_binding"] == "unsupported"
    assert value["attempts"] == [] and value["errors"] == ["unsupported_client"]
    assert "PRIVATE_QUALIFICATION_FAILURE" not in json.dumps(value)
    transport.validate_document(value)


def test_middleware_synthesis_has_call_and_no_dispatch(engine, monkeypatch):
    monkeypatch.setattr(engine.middleware, "run_llm_execution_middleware", lambda *a, **kw: success())
    doc, _ = run_call(engine, lambda: pytest.fail("synthetic middleware must not create client"))
    value = doc["transport"]
    assert len(value["calls"]) == 1 and value["dispatches"] == value["attempts"] == []
    assert engine.factories == engine.cleanups == [] and value["errors"] == []
    transport.validate_document(value)


def test_multiple_middleware_callbacks_remain_distinct_dispatches(engine, monkeypatch):
    pytest.importorskip("openai")
    def twice(payload, next_call, **kwargs):
        next_call(payload)
        return next_call(payload)
    monkeypatch.setattr(engine.middleware, "run_llm_execution_middleware", twice)
    doc, _ = run_call(engine, lambda: sdk(lambda request: httpx.Response(200, json=success())))
    value = doc["transport"]
    assert len(value["calls"]) == 1 and len(value["dispatches"]) == len(value["attempts"]) == 2
    assert [x["call_sequence"] for x in value["dispatches"]] == [1, 1]
    assert [x["dispatch_sequence"] for x in value["attempts"]] == [1, 2]
    transport.validate_document(value)


def test_delayed_dispatch_uses_captured_call_identity(engine, monkeypatch):
    def change_labels(payload, next_call, **kwargs):
        # A copied worker runs after the same adopted agent's fields advance.
        current = observation._current.get()
        agent = current.authority.adopted[current.session_id][1]
        target = engine.helpers._context_thread_target(lambda: next_call(payload))
        agent._current_turn_id, agent._current_api_request_id = "later-turn", "later-request"
        return target()
    monkeypatch.setattr(engine.middleware, "run_llm_execution_middleware", change_labels)
    doc, _ = run_call(engine, lambda: facade())
    value = doc["transport"]
    assert value["dispatches"][0]["identity"] == value["calls"][0]["identity"]
    assert value["dispatches"][0]["identity"]["api_request_id"] == "request-A"
    transport.validate_document(value)


def test_sealing_precedes_slow_process_end_observation(engine, monkeypatch):
    saved = {}
    original_process = engine.launch.observe_child
    def end_process(pid):
        if saved:
            scope = saved["scope"]
            assert scope.closed
            before = copy.deepcopy(scope.transport.calls)
            saved["context"].run(engine.invoke, saved["agent"], payload(), lambda: facade())
            assert scope.transport.calls == before
        return original_process(pid)
    engine.launch.observe_child = end_process
    def remember(ref, row, agent, response):
        saved.update(scope=observation._current.get(), context=contextvars.copy_context(), agent=agent)
    doc, _ = run_call(engine, lambda: facade(), behavior=remember)
    assert len(doc["transport"]["calls"]) == 1
    assert doc["transport"]["execution"]["same_process"] is True
    transport.validate_document(doc["transport"])


def test_original_factory_exception_and_missing_terminal_remain_original(engine):
    failure = RuntimeError("PRIVATE_FACTORY_ERROR")
    async def handle(ref, row, agent):
        engine.invoke(agent, payload(), lambda: (_ for _ in ()).throw(failure))
    with pytest.raises(RuntimeError) as caught:
        run_admission(engine, behavior=handle)
    assert caught.value is failure
    assert not engine.authority.pending_results
    assert engine.cleanups == ["request_error_cleanup"]
    assert observation._current.get() is None


def test_wire_and_response_canaries_are_digest_only_and_missing_seed_is_absent():
    secret = "https://user:PRIVATE_PASSWORD@provider.invalid/PRIVATE_PATH"
    request = httpx.Request("POST", secret + "?key=PRIVATE_QUERY", headers={"Authorization": "Bearer PRIVATE_HEADER"},
        json=payload(model=secret, reasoning_effort="Bearer PRIVATE_EFFORT", reasoning={"effort": "Bearer PRIVATE_NESTED"}))
    projected = transport._request_projection(request)
    response = transport._response_projection(httpx.Response(200, json=success("Bearer PRIVATE_RESPONSE")), consumed=True)
    encoded = json.dumps([projected, response])
    assert "PRIVATE_" not in encoded and "provider.invalid" not in encoded
    assert projected["model"]["status"] == "observed_digest"
    assert projected["reasoning_effort"] == {"status": "conflicting"}
    transport._validate_request(projected)
    transport._validate_response(response)
    no_seed = payload(); no_seed.pop("seed")
    assert transport._request_projection(httpx.Request("POST", "https://example.invalid", json=no_seed))["seed"] == {"status": "absent"}


def test_projection_does_not_drain_request_or_response_stream():
    visited = []
    def stream():
        visited.append("drained")
        yield b'PRIVATE_STREAM'
    request = httpx.Request("POST", "https://example.invalid", content=stream())
    response = httpx.Response(200, content=stream())
    projected = transport._request_projection(request)
    answer = transport._response_projection(response, consumed=True)
    assert projected["body_state"] == "unavailable" and answer["body_state"] == "unconsumed"
    assert visited == [] and not response.is_closed
    transport._validate_request(projected); transport._validate_response(answer)


@pytest.mark.parametrize("body", [b'{"seed":1,"seed":2}', b'{"seed":NaN}', b'[]', b'not json'])
def test_noncanonical_wire_is_retained_only_as_byte_digest(body):
    value = transport._request_projection(httpx.Request("POST", "https://example.invalid", content=body))
    assert value["body_state"] == "unqualified_json" and value["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert value["seed"] == {"status": "unobserved"}
    transport._validate_request(value)


@pytest.mark.parametrize("kind,field,bad", [
    ("request", "body_state", "unavailable"), ("request", "tools_state", "unobserved"),
    ("request", "model", {"status": "present", "value": "PRIVATE_LABEL"}),
    ("request", "seed", {"status": "unobserved"}),
    ("response", "body_state", "oversized"), ("response", "reported_model", {"status": "unobserved"}),
    ("response", "body_bytes", None),
])
def test_conditional_projection_matrix_rejects_impossible_states(kind, field, bad):
    if kind == "request":
        value = transport._request_projection(httpx.Request("POST", "https://example.invalid", json=payload()))
        validate = transport._validate_request
    else:
        value = transport._response_projection(httpx.Response(200, json=success()), consumed=True)
        validate = transport._validate_response
    validate(value)
    value[field] = bad
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize("mutation", ["identity", "client", "response", "duration", "process", "promotion"])
def test_closed_reader_rejects_correlations_and_false_promotion(engine, mutation):
    pytest.importorskip("openai")
    doc, _ = run_call(engine, lambda: sdk(lambda request: httpx.Response(200, json=success())))
    value = copy.deepcopy(doc["transport"])
    if mutation == "identity": value["dispatches"][0]["identity"]["turn_id"] = "other"
    if mutation == "client": value["dispatches"][0]["client_binding"] = "pending"
    if mutation == "response": value["attempts"][0]["response"] = None
    if mutation == "duration": value["execution"]["started_at_ms"] = None
    if mutation == "process": value["execution"]["process_end"] = {"status": "unavailable"}; value["execution"]["same_process"] = None
    if mutation == "promotion": value["complete_evaluation"] = True
    with pytest.raises(ValueError): transport.validate_document(value)


def test_shared_budget_is_bounded_without_changing_original_calls(engine, monkeypatch):
    def many(payload, next_call, **kwargs):
        for _ in range(transport.MAX_DISPATCHES + 2):
            result = next_call(payload)
        return result
    monkeypatch.setattr(engine.middleware, "run_llm_execution_middleware", many)
    doc, _ = run_call(engine, lambda: facade())
    assert len(engine.factories) == transport.MAX_DISPATCHES + 2
    assert doc["transport"]["overflow"] is True
    assert observation._encoded_size(doc) <= observation.MAX_METADATA_BYTES
    transport.validate_document(doc["transport"])


def retained_read(engine, carrier, monkeypatch):
    ref, row, agent, response = carrier
    outer = engine.authority.pending_results[row["admission_id"]]
    outcome, stored = engine.results.prepare_result(row, response, "completed", outer)
    saved = engine.terminal.load_result(json.dumps(engine.terminal.encode_result(stored)))
    principal = f"uid:{os.getuid()}"
    retained = dict(row, principal_id=principal, target_session_id=ref.session_id,
        request_id="original-submission", intent="queue", seq=1, status="terminal", outcome=outcome,
        owner_epoch=saved[observation.RESULT_KEY]["scope"]["authority_epoch"])
    monkeypatch.setattr(control, "_db", lambda home: SimpleNamespace(close=lambda: None))
    module(monkeypatch, "hermes_state_runtime", find_session_admission=lambda *a, **kw: retained,
           get_session_admission=lambda *a, **kw: retained)
    monkeypatch.setattr(engine.results, "admission_result", lambda *a: saved, raising=False)
    params = {"operation": "read_original", "profile_id": str(engine.home), "session_id": ref.session_id,
        "submission_id": "original-submission", "input_sha256": control.input_digest(row["payload"]["text"]),
        "admission_id": row["admission_id"]}
    return saved, lambda: control._read_original(engine.home, params, principal)


def test_actual_sdk_document_survives_original_redaction_codec_and_authenticated_reader(engine, monkeypatch):
    pytest.importorskip("openai")
    doc, carrier = run_call(engine, lambda: sdk(lambda request: httpx.Response(200, json=success("Bearer PRIVATE_MODEL"))))
    saved, read = retained_read(engine, carrier, monkeypatch)
    result = read()
    assert result["answer"] == "[redacted]" and result["request_observation"] == doc
    assert "PRIVATE_" not in json.dumps(result)
    # Rejection of one impossible field does not erase the original answer.
    saved[observation.RESULT_KEY]["transport"]["attempts"][0]["response"] = None
    result = read()
    assert "request_observation" not in result
    assert result["request_observation_error"] == "INVALID_RETAINED_OBSERVATION"
    assert result["answer"] == "[redacted]"


@pytest.mark.parametrize("schema", [observation.LEGACY_SCHEMA, observation.PREVIOUS_SCHEMA])
def test_historical_schemas_keep_exact_shape_and_do_not_inherit_transport(engine, monkeypatch, schema):
    doc, carrier = run_call(engine, lambda: facade())
    saved, read = retained_read(engine, carrier, monkeypatch)
    old = saved[observation.RESULT_KEY]
    old["schema"] = schema
    old.pop("transport")
    if schema == observation.LEGACY_SCHEMA:
        for key in ("tools_stage", "tool_coverage", "executions", "commits", "tool_overflow", "metadata_overflow"):
            old.pop(key)
    result = read()
    assert result["request_observation"] == old
    old["transport"] = doc["transport"]
    assert read()["request_observation_error"] == "INVALID_RETAINED_OBSERVATION"


def test_clock_failure_does_not_substitute_zero_or_change_native_return(engine, monkeypatch):
    monkeypatch.setattr(transport, "_clock", lambda: (_ for _ in ()).throw(ValueError("clock edge")))
    doc, _ = run_call(engine, lambda: facade())
    value = doc["transport"]
    assert "clock_unavailable" in value["errors"]
    assert all(value["execution"][key] is None for key in ("started_at_ms", "finished_at_ms", "duration_ms"))
    assert value["execution"]["outcome"] == "returned"
    transport.validate_document(value)


def test_process_failure_is_explicit_and_original_return_is_preserved(engine):
    engine.launch.observe_child = lambda pid: (_ for _ in ()).throw(ValueError("owner edge"))
    doc, _ = run_call(engine, lambda: facade())
    value = doc["transport"]
    assert "process_observation_unavailable" in value["errors"]
    assert value["execution"]["same_process"] is None
    assert value["execution"]["process_start"] == value["execution"]["process_end"] == {"status": "unavailable"}
    transport.validate_document(value)


def test_changed_native_caller_binding_is_not_promoted_or_replaced(engine, monkeypatch):
    original = engine.conversation.perform_api_call
    monkeypatch.setattr(sys.modules["agent.turn_api_call"], "perform_api_call", lambda **kw: pytest.fail("replacement not ours"))
    doc, _ = run_call(engine, lambda: facade())
    assert engine.conversation.perform_api_call is original
    assert "transport_binding_changed" in doc["transport"]["errors"]
    assert doc["transport"]["attempts"] == []
    transport.validate_document(doc["transport"])


def test_source_drift_cannot_install_or_replace_original_hooks(engine):
    current = engine.conversation.perform_api_call
    source = engine.vendor / "agent/conversation_loop.py"
    source.write_bytes(source.read_bytes() + b'\n# changed caller\n')
    candidate = transport.prepare(engine.binding, engine.vendor)
    assert candidate.description() == {"status": "unavailable", "reason": "native_source_unqualified"}
    candidate.commit()
    assert engine.conversation.perform_api_call is current


def test_httpx_archive_review_is_exact_and_does_not_hide_drift():
    from tests.executive_identity_review import reviewed_literal_spans
    from tests.test_ceo_submit_armed_composition import _scan_added_identity_diff, _d8_frozen_source_diff
    path = "integrations/hermes_runtime/tests/fixtures/transport_observation/httpx___client.py.source"
    text = (Path(__file__).resolve().parents[3] / path).read_text()
    assert reviewed_literal_spans(path, text) == ((73, 42, 45, "int"),)
    assert _scan_added_identity_diff(_d8_frozen_source_diff(path, text), source_postimages={path: text}) == []
    changed = text + "\n"
    assert reviewed_literal_spans(path, changed) == ()
    assert "443" in _scan_added_identity_diff(_d8_frozen_source_diff(path, changed), source_postimages={path: changed})
