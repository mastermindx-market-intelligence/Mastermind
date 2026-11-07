"""Actual pinned ingress/assembly/retention bodies with explicit edge doubles.

No provider, installed host, EVAL, or full native service acceptance is claimed.
The source fixtures are unmodified upstream files; only selected AST definitions
are executed, with their original module name, globals and source filename.
"""
import ast
import asyncio
import contextlib
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import threading
import textwrap
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Optional

import pytest

from integrations.hermes_runtime import native_gateway_entry as entry
from integrations.hermes_runtime import native_request_observation as observation
from integrations.hermes_runtime.errors import RuntimeRefusal

FIXTURES = Path(__file__).parent / "fixtures/request_observation"
MANIFEST = json.loads((FIXTURES / "provenance.json").read_text())


class NativeStoreError(Exception):
    pass


def module(monkeypatch, name, **values):
    result = ModuleType(name)
    result.__dict__.update(values)
    monkeypatch.setitem(__import__("sys").modules, name, result)
    return result


def definitions(monkeypatch, vendor, path, names, *, values=None, methods=None):
    item = MANIFEST["files"][path]
    data = (FIXTURES / item["fixture"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == item["sha256"]
    if "blob" in item:
        assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == item["blob"]
        assert len(data) == item["bytes"]
    target = vendor / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o644)
    name = path.removesuffix(".py").replace("/", ".")
    result = module(monkeypatch, name, __file__=str(target), **(values or {}))
    selected = []
    for node in ast.parse(data, filename=str(target)).body:
        if getattr(node, "name", None) in names:
            if isinstance(node, ast.ClassDef) and methods:
                node.body = [child for child in node.body if getattr(child, "name", None) in methods]
            selected.append(node)
    assert {node.name for node in selected} == set(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(target), "exec"), vars(result))
    return result


@pytest.fixture
def native(tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    home = tmp_path / "home/profiles/mmsecretary"
    for name in ("gateway", "agent", "hermes_cli"):
        module(monkeypatch, name, __path__=[str(vendor / name)])
    calls, publications = [], []
    async def note(*args):
        return None
    module(monkeypatch, "gateway.session_completion_notes", note_if_unviewed=note)
    module(monkeypatch, "gateway.session_policy", policy_for_source=lambda *args: None)
    module(monkeypatch, "gateway.session_managed_worker", managed_policy=lambda *args: None,
           admit_managed=None, ManagedExecutionUnknown=type("ManagedExecutionUnknown", (Exception,), {}))
    module(monkeypatch, "gateway.session_ingress_media", restore_attachments=lambda payload: {})
    module(monkeypatch, "gateway.session_operator", is_viewer_input=lambda row: True)
    module(monkeypatch, "gateway.config", Platform=SimpleNamespace(API_SERVER="api", LOCAL="local"))
    module(monkeypatch, "gateway.session_api_turn", api_execution=ContextVar("api", default=None),
           prepare_api_execution=lambda *args: {"content": []})
    module(monkeypatch, "gateway.session_display", display_turn_scope=lambda *args: contextlib.nullcontext())
    module(monkeypatch, "gateway.session_surface", surface_turn_scope=lambda *args: contextlib.nullcontext())
    module(monkeypatch, "gateway.session_cli_turn", cli_turn_scope=lambda *args: contextlib.nullcontext())
    module(monkeypatch, "gateway.session_automation", admission_display=lambda payload: {"text": payload["text"]})
    module(monkeypatch, "agent.redact", redact_sensitive_text=lambda text: text.replace("PRIVATE_OUTPUT", "[redacted]"))
    module(monkeypatch, "agent.turn_context", reanchor_current_turn_user_idx=lambda messages, user: 0 if messages else -1)
    module(monkeypatch, "agent.conversation_loop", _system_prompt_for_hooks=lambda kwargs, messages: kwargs.get("system"),
           _moa_client_consumes_prepared_request=lambda client: False,
           _redecorate_prompt_cache_for_provider=lambda agent, messages, **kw: (messages, kw["moa_prepared"], kw["tools_for_api"]))
    lifecycle = module(monkeypatch, "hermes_cli.lifecycle", has_hook=lambda name: True)
    def hook(name, **kwargs):
        calls.append("hook")
        kwargs["request"]["system"] = "hook system\nΩ"
    lifecycle.invoke_hook = hook
    def middleware(payload, **kwargs):
        calls.append("middleware")
        before = dict(payload)
        payload["instructions"] = "middleware instruction"
        return SimpleNamespace(payload=payload, original_payload=before, trace=[])
    module(monkeypatch, "hermes_cli.middleware", apply_llm_request_middleware=middleware)

    results = definitions(monkeypatch, vendor, "gateway/session_results.py", {"_redacted", "prepare_result"},
                          values={"execution_result": ContextVar("terminal", default=None)})
    terminal = definitions(monkeypatch, vendor, "hermes_state_terminal.py",
                           {"compact_result", "encode_result", "load_result"}, values={"json": json, "_STORED": "_stored"})
    requests = definitions(monkeypatch, vendor, "agent/turn_api_request.py",
        {"ApiRequestBuild", "_set_extra_header", "_fire_pre_api_request_hook", "build_api_request"},
        values={"dataclass": dataclass, "Any": Any, "logger": logging.getLogger(__name__),
                "env_var_enabled": lambda name: False,
                "sanitize_outbound_kwargs": lambda *args: calls.append("sanitize"),
                "strip_images_for_rejecting_model": lambda *args: None,
                "observe_request_tools": lambda *args: None})
    tool_executor = definitions(monkeypatch, vendor, "agent/tool_executor.py",
        {"_ToolCallRef", "_ManagedToolResult", "_dispatch_authorized_once", "_commit_tool_result",
         "_run_agent_tool_execution_middleware", "_flush_session_db_after_tool_progress"},
        values={"dataclass": dataclass, "Any": Any, "Callable": Callable, "Optional": Optional,
                "BudgetConfig": object, "_ConcurrentToolAuthorizationGate": object,
                "threading": threading, "json": json, "logging": logging, "logger": logging.getLogger(__name__)})
    authority_module = definitions(monkeypatch, vendor, "gateway/session_authority.py", {"SessionAuthority"},
        methods={"_handle", "_stamp_claim", "adopt_agent", "check_approval_generation", "_execute_claimed"},
        values={"contextlib": contextlib, "asyncio": asyncio, "RuntimeStoreError": NativeStoreError,
                "SessionRef": lambda profile, session: SimpleNamespace(profile_id=profile, session_id=session),
                "SessionHandle": lambda ref, instance, epoch, revision, generation, state:
                    SimpleNamespace(execution_generation=generation, execution_state=state)})
    class Event:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.internal, self.metadata = False, {}
        def get_command(self):
            return None
    async def execution_scope(*args):
        return contextlib.nullcontext()
    async def marker(*args):
        calls.append("marker")
    ingress = definitions(monkeypatch, vendor, "gateway/session_ingress.py", {"execute_admission"}, values={
        "MessageEvent": Event, "admission_author": ContextVar("author", default=None),
        "viewer_turn": ContextVar("viewer", default=None), "executing_admission": ContextVar("executing", default=False),
        "row_turn_author": lambda *args: None, "_execution_scope": execution_scope,
        "_hand_over_turn_marker": marker, "_release_turn_marker": marker})
    finite = definitions(monkeypatch, vendor, "gateway/session_finite.py", {"finite_turn_scope", "execute_finite_admission"},
                         values={"contextmanager": contextlib.contextmanager, "_finite_turn": ContextVar("finite", default=None),
                                 "_unattended_turn": ContextVar("unattended", default=False)})
    authority = authority_module.SessionAuthority()
    authority.profile_id, authority.epoch, authority.instance_id = str(home), 2, "instance-1"
    authority.sessions, authority.executing, authority.adopted = {}, {}, {}
    authority.pending_results, authority.pending_deliveries = {}, {}
    authority.delivered_stops, authority.pending_stops, authority.pending_steers = {}, {}, {}
    authority.native_waiters, authority.retiring = set(), False
    authority._publish_pending = lambda ref: None
    rows = {}
    def stored_session(sid):
        # The original generation owner reads storage outside the event lock.
        assert not authority.sessions[sid].event_stream.lock._is_owned()
        return {"runtime_revision": 1, "runtime_generation": rows[sid]["generation"]}
    authority.db = SimpleNamespace(get_session=stored_session)
    authority._pending_rows = lambda ref: [rows[ref.session_id]]
    runner = SimpleNamespace(session_authority=authority, session_runtime_descriptor={"instance_id": "instance-1", "authority_epoch": 2},
        config=SimpleNamespace(multiplex_profiles=False), _draining=False, _adapter_for_source=lambda source: None)
    authority.runner = runner
    excerpt = MANIFEST["executor_excerpt"]
    code = (FIXTURES / excerpt["fixture"]).read_bytes()
    assert hashlib.sha256(code).hexdigest() == excerpt["sha256"]
    executor = module(monkeypatch, "gateway.run", asyncio=asyncio, copy_context=copy_context)
    exec(compile(textwrap.dedent(code.decode()), str(vendor / "gateway/run.py"), "exec"), vars(executor))
    runner._get_executor = lambda: None  # Actual event-loop executor; no provider/host service.
    runner._run_in_executor_with_context = executor._run_in_executor_with_context.__get__(runner)
    launch = SimpleNamespace(check=lambda: calls.append("source-check"), owner=SimpleNamespace(closed=False),
                             closure=SimpleNamespace(closed=False))
    binding = observation.install_request_observation(launch, vendor, home, "mmsecretary")
    binding.bind_authority(runner)

    def agent_for(sid):
        return SimpleNamespace(session_id="physical-" + sid, platform="api", model="requested-label", provider="requested-provider",
            base_url="https://provider.invalid", api_mode="chat_completions", tools=[], max_tokens=100,
            _empty_content_retries=0, _reset_stream_delivery_tracking=lambda: None,
            _reapply_reasoning_echo_for_provider=lambda messages: None,
            _build_api_kwargs=lambda messages, **kwargs: {"messages": messages, "extra_headers": {"Authorization": "SECRET_HEADER"}},
            _api_request_payload_for_hook=lambda kwargs: kwargs)
    def claim(sid="session-1", admission="admission-1", generation=3):
        ref = SimpleNamespace(profile_id=str(home), session_id=sid)
        row = {"admission_id": admission, "generation": generation, "status": "started", "payload": {"text": "question", "finite": True}}
        live = SimpleNamespace(source=SimpleNamespace(platform="api"), review=None, event_stream=SimpleNamespace(
            lock=threading.RLock(), execution=None, publish=lambda *args, **kwargs: publications.append((args, kwargs))))
        rows[sid] = row
        authority.sessions[sid] = live
        authority._stamp_claim(ref, live, row)
        agent = agent_for(sid)
        authority.adopt_agent(sid, generation, agent)
        return ref, row, agent
    def build(agent, text="request Ω\n  ", **overrides):
        args = dict(api_messages=[{"role": "user", "content": text}], _moa_prepared_request=None, tools_for_api=[],
                    system_message="system", messages=[], original_user_message="question", approx_tokens=4, total_chars=10,
                    retry_count=0, api_call_count=1, api_request_id="request-1", api_start_time=0,
                    effective_task_id="task-1", turn_id="turn-1")
        args.update(overrides)
        return requests.build_api_request(agent, **args)
    return SimpleNamespace(vendor=vendor, home=home, calls=calls, publications=publications, requests=requests, results=results,
                           terminal=terminal, ingress=ingress, finite=finite, authority=authority, runner=runner,
                           launch=launch, binding=binding, rows=rows, claim=claim, build=build, lifecycle=lifecycle,
                           tool_executor=tool_executor)


def run_admission(native, *, behavior=None, text="question"):
    ref, row, agent = native.claim()
    row["payload"]["text"] = text
    async def handle(event):
        native.calls.append("handler")
        if behavior:
            return await behavior(ref, row, agent)
        assembled = await native.runner._run_in_executor_with_context(native.build, agent)
        native.expected_content = {key: assembled.api_kwargs[key] for key in observation.CONTENT_FIELDS if key in assembled.api_kwargs}
        native.results.execution_result.get()["result"] = {
            "final_response": "PRIVATE_OUTPUT", "completed": True, "messages": [], "tools": ["omitted"]}
        return "PRIVATE_OUTPUT"
    native.runner._handle_message = handle
    response = asyncio.run(native.finite.execute_finite_admission(native.authority, ref, row))
    return ref, row, agent, response


def test_actual_ingress_assembly_and_terminal_storage_join(native, monkeypatch):
    ref, row, agent, response = run_admission(native)
    assert response == "PRIVATE_OUTPUT"
    outer = native.authority.pending_results[row["admission_id"]]
    doc = outer[observation.RESULT_KEY]
    assert doc["scope"] == dict(role="mmsecretary", session_id=ref.session_id, admission_id=row["admission_id"],
        authority_epoch=2, execution_generation=3, instance_id="instance-1")
    encoded = json.dumps(native.expected_content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert doc["observations"][0]["content_sha256"] == hashlib.sha256(encoded).hexdigest()
    assert doc["observations"][0]["content_bytes"] == len(encoded)
    assert doc["observations"][0]["agent_session_id"] == agent.session_id
    assert doc["observations"][0]["fields"] == ["messages", "system", "instructions"]
    assert native.calls.count("handler") == native.calls.count("hook") == native.calls.count("marker") == 1
    assert native.calls.index("sanitize") < native.calls.index("middleware") < native.calls.index("hook")
    assert len(native.publications) == 1  # Original claim only; no event observer or second delivery.
    outcome, stored = native.results.prepare_result(row, response, "completed", outer)
    restored = native.terminal.load_result(json.dumps(native.terminal.encode_result(stored)))
    assert outcome == "completed" and restored[observation.RESULT_KEY] == doc
    assert restored["result"]["final_response"] == "[redacted]"
    assert "tools" not in restored["result"]
    assert doc["provider_dispatch_proven"] is False and doc["model_identity_verified"] is False
    assert doc["coverage"] == "assembly_hooks_only"
    metadata = json.dumps(doc)
    assert all(value not in metadata for value in ("SECRET_HEADER", "PRIVATE_OUTPUT", "hook system", "middleware instruction", "requested-label"))
    assert observation._current.get() is None
    # Continue the actual producer/redaction/codec output through the original
    # authenticated-owner reader. Only its storage edge is a fixture here.
    from integrations.hermes_runtime import native_session_control as control
    retained = dict(row, principal_id="uid:994", target_session_id=ref.session_id,
        request_id="original-submission", intent="queue", seq=1, status="terminal",
        outcome=outcome, owner_epoch=doc["scope"]["authority_epoch"])
    reads, closes = [], []
    db = SimpleNamespace(close=lambda: closes.append(True))
    monkeypatch.setattr(control, "_db", lambda home: db)
    module(monkeypatch, "hermes_state_runtime", find_session_admission=lambda *a, **kw: retained,
           get_session_admission=lambda *a, **kw: retained)
    def original(_db, admission_id):
        assert _db is db
        reads.append(admission_id)
        return restored
    monkeypatch.setattr(native.results, "admission_result", original, raising=False)
    # A restart changes today's descriptor. Original evidence keeps its own
    # instance/epoch and joins the stored historical receipt, not this descriptor.
    native.runner.session_runtime_descriptor.update(instance_id="successor-instance", authority_epoch=99)
    result = control._read_original(native.home, {
        "operation": "read_original", "profile_id": str(native.home), "session_id": ref.session_id,
        "submission_id": "original-submission", "input_sha256": control.input_digest(row["payload"]["text"]),
        "admission_id": row["admission_id"]}, "uid:994")
    assert result["request_observation"] == doc
    assert result["answer"] == "[redacted]" and result["successful"] is True
    assert result["terminal_metadata"]["output"]["sha256"] == hashlib.sha256(b"[redacted]").hexdigest()
    assert reads == [row["admission_id"]] and closes == [True]
    assert restored[observation.RESULT_KEY] == doc


@pytest.mark.parametrize("outcome", ["failed", "interrupted"])
def test_native_failure_flags_and_outer_metadata_remain_separate(native, outcome):
    async def handle(ref, row, agent):
        native.build(agent)
        native.results.execution_result.get()["result"] = {"final_response": "", "messages": [], outcome: True,
                                                            observation.RESULT_KEY: {"spoof": True}}
        return "notice"
    _, row, _, response = run_admission(native, behavior=handle)
    outer = native.authority.pending_results[row["admission_id"]]
    status, stored = native.results.prepare_result(row, response, "completed", outer)
    assert status == outcome and stored["result"]["completed"] is False
    assert stored["result"][observation.RESULT_KEY] == {"spoof": True}
    assert stored[observation.RESULT_KEY]["schema"] == observation.SCHEMA


@pytest.mark.parametrize("exception", [RuntimeError("native failure"), asyncio.CancelledError()])
def test_native_exception_and_cancellation_are_preserved_without_synthetic_result(native, exception):
    async def handle(ref, row, agent):
        native.build(agent)
        raise exception
    with pytest.raises(type(exception)) as caught:
        run_admission(native, behavior=handle)
    assert caught.value is exception
    assert native.authority.pending_results == {} and observation._current.get() is None
    assert native.calls.count("marker") == 1


def test_late_copied_context_is_sealed_and_request_mutation_does_not_rewrite_digest(native):
    retained = {}
    async def handle(ref, row, agent):
        built = native.build(agent)
        retained.update(context=copy_context(), agent=agent, before=observation._content_digest(built.api_kwargs))
        built.api_kwargs["messages"][0]["content"] = "later mutation"
        native.results.execution_result.get()["result"] = {"final_response": "answer", "messages": []}
        return "answer"
    _, row, _, _ = run_admission(native, behavior=handle)
    doc = native.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]
    before = json.dumps(doc, sort_keys=True)
    retained["context"].run(native.build, retained["agent"], "late callback")
    assert json.dumps(doc, sort_keys=True) == before
    assert doc["observations"][0]["content_sha256"] == retained["before"]["content_sha256"]


@pytest.mark.parametrize("change", ["generation", "epoch", "instance", "draining", "live", "adopted"])
def test_stale_claim_cannot_contribute(native, change):
    async def handle(ref, row, agent):
        if change == "generation": native.rows[ref.session_id] = {**row, "generation": 4}
        elif change == "epoch": native.authority.epoch += 1
        elif change == "instance": native.authority.instance_id = "new-instance"
        elif change == "draining": native.runner._draining = True
        elif change == "live": native.authority.sessions[ref.session_id] = SimpleNamespace()
        elif change == "adopted": native.authority.adopted[ref.session_id] = (row["generation"], SimpleNamespace(**vars(agent)))
        native.build(agent)
        native.results.execution_result.get()["result"] = {"final_response": "answer", "messages": []}
        return "answer"
    _, row, _, _ = run_admission(native, behavior=handle)
    doc = native.authority.pending_results[row["admission_id"]].get(observation.RESULT_KEY)
    assert doc is None or not doc["observations"]


def test_equivalent_agent_object_does_not_satisfy_adoption(native):
    ref, row, agent = native.claim()
    class AlwaysEqual:
        def __eq__(self, other):
            raise AssertionError("custody must never invoke agent equality")
    scope = native.binding.scope(native.authority, ref, row)
    scope.record(AlwaysEqual(), {"messages": []}, {})
    assert scope.events == [] and scope.errors == {"unbound_or_stale_agent"}


def test_interleaved_admissions_use_their_own_context(native):
    claims = [native.claim("session-" + str(i), "admission-" + str(i)) for i in range(2)]
    async def handle(event):
        index = int(event.message_id[-1])
        ref, row, agent = claims[index]
        await asyncio.sleep(0)
        await native.runner._run_in_executor_with_context(native.build, agent, "content-" + str(index))
        native.results.execution_result.get()["result"] = {"final_response": str(index), "messages": []}
        return str(index)
    native.runner._handle_message = handle
    async def execute():
        return await asyncio.gather(*(native.finite.execute_finite_admission(native.authority, ref, row) for ref, row, _ in claims))
    assert asyncio.run(execute()) == ["0", "1"]
    docs = [native.authority.pending_results[row["admission_id"]][observation.RESULT_KEY] for _, row, _ in claims]
    assert [doc["scope"]["admission_id"] for doc in docs] == ["admission-0", "admission-1"]
    assert docs[0]["observations"][0]["content_sha256"] != docs[1]["observations"][0]["content_sha256"]


def test_no_observation_is_explicit_and_preexisting_outer_field_is_preserved(native):
    async def handle(ref, row, agent):
        return "no turn"
    _, row, _, _ = run_admission(native, behavior=handle)
    outer = native.authority.pending_results[row["admission_id"]]
    doc = outer[observation.RESULT_KEY]
    assert doc["coverage"] == "no_assembly_observation" and doc["observations"] == []
    assert outer["result"]["failed"] is True  # Original API no-turn behavior.
    ref, row, agent = native.claim()
    scope = native.binding.scope(native.authority, ref, row)
    marker = outer[observation.RESULT_KEY] = object()
    scope.finish()
    assert outer[observation.RESULT_KEY] is marker


def test_bounded_observations_and_identifiers(native):
    async def handle(ref, row, agent):
        for count in range(12):
            native.build(agent, api_request_id="r" * 256, turn_id="t" * 256, api_call_count=count)
        native.results.execution_result.get()["result"] = {"messages": []}
        return "answer"
    _, row, _, _ = run_admission(native, behavior=handle)
    doc = native.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]
    assert len(doc["observations"]) == observation.MAX_EVENTS and doc["overflow"]
    assert len(json.dumps(doc).encode()) <= observation.MAX_METADATA_BYTES


def test_invalid_labels_are_omitted_without_calling_custom_serializers(native):
    ref, row, agent = native.claim()
    scope = native.binding.scope(native.authority, ref, row)
    scope.record(agent, {"messages": []}, {"turn_id": "bad\ud800", "api_request_id": "a" * 257,
                                        "api_call_count": True, "retry_count": -1})
    assert set(scope.events[0]["invalid_fields"]) == {"turn_id", "api_request_id", "api_call_count", "retry_count"}
    assert all(key not in scope.events[0] for key in scope.events[0]["invalid_fields"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 2**129, object(), {1: "key"}, "\ud800"])
def test_non_json_content_refuses_without_stringifying(value):
    with pytest.raises((ValueError, TypeError, UnicodeError)):
        observation._content_digest({"messages": value})


def test_digest_is_presence_sensitive_and_exact_for_unicode_and_whitespace():
    values = [{}, {"messages": None}, {"messages": []}, {"messages": "a"}, {"messages": "a "}, {"messages": "é"}, {"messages": "e\u0301"}]
    assert len({observation._content_digest(value)["content_sha256"] for value in values}) == len(values)
    assert observation._content_digest({"messages": [], "extra_headers": object()}) == observation._content_digest({"messages": []})


def test_content_depth_cycle_and_work_bounds(monkeypatch):
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError): observation._content_digest({"messages": cycle})
    deep = []
    for _ in range(observation.MAX_DEPTH + 1): deep = [deep]
    with pytest.raises(observation._ObservationLimit): observation._content_digest({"messages": deep})
    monkeypatch.setattr(observation, "MAX_NODES", 8)
    with pytest.raises(observation._ObservationLimit): observation._content_digest({"messages": {str(i): i for i in range(50)}})
    monkeypatch.setattr(observation, "MAX_CONTENT_BYTES", 16)
    with pytest.raises(observation._ObservationLimit): observation._content_digest({"messages": "é" * 12})


def test_shared_prompt_digest_preserves_historical_value_budget(monkeypatch):
    # This helper is also used by the accepted native Agent OS prompt receipt.
    # Two nested lists plus their leaf have exactly three value nodes, depth 2.
    value = {"messages": [["kept"]]}
    monkeypatch.setattr(observation, "MAX_DEPTH", 2)
    monkeypatch.setattr(observation, "MAX_NODES", 3)
    raw = b'{"messages":[["kept"]]}'
    got = observation._content_digest(value)
    assert got["content_sha256"] == hashlib.sha256(raw).hexdigest()
    assert got["content_bytes"] == len(raw)
    # The tools digest deliberately includes its supplied object's root/keys.
    assert observation._tools_digest({"tools": value}) == {"status": "unavailable", "reason": "content_limit"}
    monkeypatch.setattr(observation, "MAX_NODES", 2)
    with pytest.raises(observation._ObservationLimit): observation._content_digest(value)
    monkeypatch.setattr(observation, "MAX_NODES", 3)
    monkeypatch.setattr(observation, "MAX_DEPTH", 1)
    with pytest.raises(observation._ObservationLimit): observation._content_digest(value)


def test_source_mutation_or_duplicate_install_refuses_before_rebinding(native):
    wrapper = native.ingress.execute_admission
    with pytest.raises(RuntimeRefusal, match="ALREADY_BOUND"):
        observation.install_request_observation(native.launch, native.vendor, native.home, "mmsecretary")
    assert native.ingress.execute_admission is wrapper
    path = native.vendor / "gateway/session_ingress.py"
    path.write_bytes(path.read_bytes() + b"\n# changed\n")
    with pytest.raises(RuntimeRefusal, match="SOURCE_MISMATCH"):
        observation.install_request_observation(native.launch, native.vendor, native.home, "mmsecretary")


def test_original_function_origin_and_authority_binding_are_qualified(native):
    original = native.requests.build_api_request
    native.requests.build_api_request = lambda *args: None
    with pytest.raises(RuntimeRefusal, match="SEAM_CHANGED"):
        observation._original_function(native.requests, "build_api_request")
    native.requests.build_api_request = original
    assert observation._original_function(native.requests, "build_api_request") is original
    native.runner.session_runtime_descriptor["authority_epoch"] += 1
    with pytest.raises(RuntimeRefusal, match="AUTHORITY_MISMATCH"):
        native.binding.bind_authority(native.runner)


def test_observer_authority_qualification_precedes_control_socket(monkeypatch, tmp_path):
    from integrations.hermes_runtime import native_session_control as control
    calls = []
    async def factory(*args, **kwargs): calls.append("factory")
    def refuse(runner): raise RuntimeRefusal("OBSERVATION_REFUSED")
    monkeypatch.setattr(entry, "_digest", lambda *args, **kwargs: entry.RUN_API_SHA256)
    monkeypatch.setattr(control, "install_private_control", lambda *args, **kwargs: calls.append("socket"))
    api = SimpleNamespace(start_gateway_api=factory)
    runner = SimpleNamespace(session_authority=SimpleNamespace(profile_id=str(tmp_path), instance_id="i", epoch=2),
        session_runtime_descriptor={"instance_id": "i", "authority_epoch": 2}, config=SimpleNamespace(multiplex_profiles=False))
    entry.bind_native_api(api, vendor=tmp_path, role_home=tmp_path, role="mmsecretary", host="127.0.0.2", port=18766,
                          request_observation=SimpleNamespace(bind_authority=refuse))
    with pytest.raises(RuntimeRefusal, match="OBSERVATION_REFUSED"):
        asyncio.run(api.start_gateway_api(runner))
    assert calls == []


def test_actual_claim_owner_seals_observation_before_clearing_execution(native):
    ref, row, agent = native.claim()
    async def handle(event):
        await native.runner._run_in_executor_with_context(native.build, agent)
        native.results.execution_result.get()["result"] = {"final_response": "answer", "messages": []}
        return "answer"
    native.runner._handle_message = handle
    result = asyncio.run(native.authority._execute_claimed(ref, native.authority.sessions[ref.session_id], row))
    assert result == ("answer", "completed")
    assert native.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]["observations"]
    assert ref.session_id not in native.authority.executing


def test_cancelled_native_executor_cannot_attach_late_observation_to_successor(native):
    ref, row, agent = native.claim()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def worker():
        started.set()
        try:
            assert release.wait(5)
            native.build(agent, "late old request")
        finally:
            finished.set()
    async def handle(event):
        task = asyncio.create_task(native.runner._run_in_executor_with_context(worker))
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        native.results.execution_result.get()["result"] = {"failed": True, "completed": False, "messages": []}
        return "cancelled worker"
    native.runner._handle_message = handle
    async def execute():
        try:
            await native.authority._execute_claimed(ref, native.authority.sessions[ref.session_id], row)
            outer = native.authority.pending_results[row["admission_id"]]
            before = json.dumps(outer, sort_keys=True)
            _, successor, _ = native.claim(ref.session_id, "successor", row["generation"] + 1)
            release.set()
            assert await asyncio.to_thread(finished.wait, 3)
            assert json.dumps(outer, sort_keys=True) == before
            assert outer[observation.RESULT_KEY]["observations"] == []
            assert successor["admission_id"] not in native.authority.pending_results
        finally:
            release.set()
    asyncio.run(execute())


def test_native_adoption_change_during_hash_is_rechecked_under_original_lock(native, monkeypatch):
    ref, row, agent = native.claim()
    scope = native.binding.scope(native.authority, ref, row)
    started, release = threading.Event(), threading.Event()
    errors = []
    original = observation._content_digest
    def digest(kwargs):
        started.set()
        assert release.wait(3)
        return original(kwargs)
    monkeypatch.setattr(observation, "_content_digest", digest)
    def record():
        try:
            scope.record(agent, {"messages": []}, {})
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=record)
    thread.start()
    try:
        assert started.wait(3)
        native.authority.adopt_agent(ref.session_id, row["generation"], SimpleNamespace())
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive() and not errors
    assert scope.events == [] and scope.errors == {"unbound_or_stale_agent"}
