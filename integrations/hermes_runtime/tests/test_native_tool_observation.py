"""Pinned native callback/commit bodies, registry and original retained reader.

Provider, plugin-policy, heartbeat and storage edges are controlled doubles.
No live Executive send, private socket, account, or installed host is used.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import contextlib
import copy
import hashlib
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from typing import Optional

import pytest

from integrations.hermes_runtime import native_request_observation as observation
from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime.tests.test_native_request_observation import (
    FIXTURES, MANIFEST, definitions, module, native, run_admission,
)
from integrations.hermes_runtime.tests.test_native_agentos_memory import source as memory_source
from integrations.hermes_harness import native_tool_registration as delegate
from integrations.hermes_harness.tests.test_native_tool_registration import (
    COMMAND, JOB_ID, _RecordingTransport, _envelope,
)


@pytest.fixture
def engine(native, monkeypatch):
    """Full real registry; exact executor bodies, with named dependency edges."""
    for name in ("tools", "tools.connectors", "hermes_cli.observability"):
        module(monkeypatch, name, __path__=[])
    module(monkeypatch, "hermes_constants", hermes_home_key=lambda scope=None: str(native.home) if scope is None else scope,
           normalize_scope=lambda value: None if value is None else str(Path(value).resolve()))
    item = MANIFEST["files"]["tools/registry.py"]
    raw = (FIXTURES / item["fixture"]).read_bytes()
    assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == item["blob"]
    target = native.vendor / "tools/registry.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    registry_module = module(monkeypatch, "tools.registry", __file__=str(target))
    exec(compile(raw, str(target), "exec"), vars(registry_module))
    registry = registry_module.ToolRegistry()
    thread_context = memory_source(monkeypatch, native.vendor, "tools/thread_context.py")
    # Callback installation is a controlled environment edge; the full pinned
    # context copier and thread runner execute, with no approval prompt invoked.
    monkeypatch.setattr(thread_context, "_callback_api", lambda: ())
    module(monkeypatch, "agent.terminal_approval_batch", prepare_current_terminal=lambda ref: None,
           bind_prepared_dispatch=lambda callback: callback)
    module(monkeypatch, "agent.tool_progress_relay", bound_tool_progress=lambda *a: contextlib.nullcontext())
    module(monkeypatch, "tools.connectors.data_use", collect_data_use=lambda: contextlib.nullcontext(set()))
    module(monkeypatch, "hermes_cli.observability.shared_metrics_harness", observe_tool_outcome=lambda *a: None)
    sys.modules["agent.conversation_loop"]._maybe_inject_run_budget_wrapup = lambda *a: None
    module(monkeypatch, "agent.turn_iteration_prep", _maybe_inject_iteration_budget_warning=lambda *a: None)
    module(monkeypatch, "hermes_state", classify_persistence_error=lambda exc: "fixture_error")
    state = SimpleNamespace(plugin_block=None, pruned=[], guard=True, flush=True, flushes=[], entered=[],
                            synthetic=False, commit_error=None, commit_wait=None, flush_impl=None)
    executor = native.tool_executor
    def flush(agent, messages, **kwargs):
        state.flushes.append(copy.deepcopy(messages))
        if state.commit_wait is not None:
            state.commit_wait()
        return state.flush
    def persist(**kwargs):
        if state.commit_error is not None:
            raise state.commit_error
        return kwargs["content"]
    vars(executor).update(
        _pre_tool_block=lambda agent, ref: (state.plugin_block, ref.args),
        _context_pruned_argument_paths=lambda *a: state.pruned,
        _PRUNED_TOOL_ARGUMENTS_ERROR="pruned", _PRUNED_TOOL_ARGUMENTS_MESSAGE="recover source",
        _blocked_tool_result=lambda *a, **kw: json.dumps({"error": "POLICY_BODY_SECRET"}),
        _begin_tool_execution=lambda agent, ref, index: state.entered.append(ref.call_id),
        _run_with_activity_heartbeat=lambda agent, name, fn: fn(),
        tool_hook_ids=lambda *a: {},
        observe_onboarding_result=lambda agent, name, args, result: result,
        _is_multimodal_tool_result=lambda result: False,
        maybe_persist_tool_result=persist, get_active_env=lambda task: None,
        _record_persisted_path_for_stub=lambda *a: None, note_tool_result=lambda *a: None,
        make_tool_result_message=lambda name, result, call_id, **kw: {"role": "tool", "tool_call_id": call_id, "content": result},
        lsp_deferred=SimpleNamespace(forward_to_agent=lambda *a: None),
        plugin_live_notes=SimpleNamespace(attach_to_tool_message=lambda *a: None),
        stamp_data_use=lambda *a: None,
        _safe_callback=lambda *a, **kw: None, _LARGE_TOOL_RESULT_TRIM_CHARS=1000000,
    )
    def relay(name, args, fn, **kwargs):
        return fn(args), args
    module(monkeypatch, "agent.relay_tools", execute=relay)
    middleware = sys.modules["hermes_cli.middleware"]
    middleware.apply_tool_request_middleware = lambda name, args, **kw: SimpleNamespace(payload=args, trace=[])
    middleware.run_tool_execution_middleware = lambda name, args, fn, **kw: "SYNTHETIC_SECRET" if state.synthetic else fn(args)
    def prepare(agent):
        agent._current_turn_id, agent._current_api_request_id = "turn-1", "request-1"
        agent._tool_guardrails = SimpleNamespace(before_call=lambda *a: SimpleNamespace(allows_execution=state.guard))
        agent.tool_progress_callback, agent.tool_result_metadata_callback = None, None
        agent._touch_activity = lambda *a: None
        agent._subdirectory_hints = SimpleNamespace(check_tool_call=lambda *a: None)
        agent._tool_result_content_for_active_model = lambda name, result: result
        agent._flush_messages_to_session_db = state.flush_impl or (lambda messages: flush(agent, messages))
        return agent
    def ref(call_id="call-1", *, name="mmx_delegate", args=None, task="task-1"):
        return executor._ToolCallRef(name, args or {"action": "selected_child_submit", "command": COMMAND}, task, call_id, [])
    def execute(agent, outer_ref, callback=None, *, scope_block=None):
        prepare(agent)
        callback = callback or (lambda args: registry.dispatch(outer_ref.name, args,
                    session_id=agent.session_id, task_id=outer_ref.task_id))
        # This original function constructs its own inner ref. Commit will use
        # the caller's different outer ref, matching the actual native path.
        return executor._run_agent_tool_execution_middleware(agent, **outer_ref.middleware_kwargs(),
                    execute=callback, scope_block=scope_block)
    def commit(agent, outer_ref, result="RESULT_BODY_SECRET", **kwargs):
        prepare(agent)
        args = dict(budget=None, tool_duration=0.01, is_error=False, blocked=False, effect_disposition=None)
        args.update(kwargs)
        return executor._commit_tool_result(agent, [], outer_ref, result, **args)
    native.engine = SimpleNamespace(state=state, registry=registry, prepare=prepare, ref=ref,
        execute=execute, commit=commit, thread_context=thread_context)
    return native


def read_original(native, monkeypatch, row, response):
    outer = native.authority.pending_results[row["admission_id"]]
    outcome, stored = native.results.prepare_result(row, response, "completed", outer)
    restored = native.terminal.load_result(json.dumps(native.terminal.encode_result(stored)))
    scope = restored[observation.RESULT_KEY]["scope"]
    retained = dict(row, principal_id="fixture-principal", target_session_id=scope["session_id"],
                    request_id="original-submission", intent="queue", seq=1, status="terminal",
                    outcome=outcome, owner_epoch=scope["authority_epoch"])
    db = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(control, "_db", lambda home: db)
    module(monkeypatch, "hermes_state_runtime", find_session_admission=lambda *a, **kw: retained,
           get_session_admission=lambda *a, **kw: retained)
    monkeypatch.setattr(native.results, "admission_result", lambda *a: restored, raising=False)
    def read():
        return control._read_original(native.home, {"operation": "read_original", "profile_id": str(native.home),
            "session_id": scope["session_id"], "submission_id": "original-submission",
            "input_sha256": control.input_digest(row["payload"]["text"]), "admission_id": row["admission_id"]},
            "fixture-principal")
    return restored, read


def run_tools(engine, monkeypatch, behavior):
    async def handle(ref, row, agent):
        await behavior(engine.engine, agent)
        engine.results.execution_result.get()["result"] = {"final_response": "PRIVATE_OUTPUT", "completed": True, "messages": []}
        return "PRIVATE_OUTPUT"
    _, row, _, response = run_admission(engine, behavior=handle)
    restored, read = read_original(engine, monkeypatch, row, response)
    result = read()
    assert result["answer"] == "[redacted]" and result["successful"] is True
    assert result["request_observation"] == restored[observation.RESULT_KEY]
    return result["request_observation"], restored, read


def test_actual_post_hook_schema_registry_delegate_commit_and_original_reader(engine, monkeypatch):
    transport = _RecordingTransport(_envelope())
    expected = {}
    async def behavior(e, agent):
        e.prepare(agent)
        binding = delegate.NativeDelegateBinding(transport=transport, currentness_guard=lambda: True,
            profile_id=str(engine.home), session_id=agent.session_id, task_id="task-1", command=COMMAND, job_id=JOB_ID)
        e.registry.register("mmx_delegate", "mastermind", delegate.NATIVE_TOOL_SCHEMA,
            delegate.native_delegate_handler(binding), dynamic_schema_overrides=lambda: {"description": "dynamic schema"})
        schemas = e.registry.get_definitions({"mmx_delegate"})
        agent._build_api_kwargs = lambda messages, **kw: {"messages": messages, "tools": copy.deepcopy(schemas)}
        original_hook = engine.lifecycle.invoke_hook
        def hook(name, **kw):
            original_hook(name, **kw)
            kw["request"]["tools"][0]["function"]["description"] = "HOOK_SCHEMA_SECRET Ω"
        monkeypatch.setattr(engine.lifecycle, "invoke_hook", hook)
        built = engine.build(agent)
        expected.update(observation._tools_digest(built.api_kwargs))
        ref = e.ref()
        managed = e.execute(agent, ref)
        assert json.loads(managed.result)["state"] == "ACTIVE"
        assert e.commit(agent, ref, managed.result, blocked=managed.blocked) is not None
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert doc["observations"][0]["tools"] == expected
    assert doc["executions"][0]["state"] == "returned"
    assert doc["commits"][0]["state"] == "commit_tuple_returned"
    assert doc["commits"][0]["correlation"] == {"status": "unique_identity_match", "execution_sequence": 1}
    assert transport.calls == [("submit", COMMAND)] and len(engine.engine.state.flushes) == 1
    assert doc["provider_dispatch_proven"] is False and doc["model_identity_verified"] is False
    assert all(secret not in json.dumps(doc) for secret in (COMMAND, "HOOK_SCHEMA_SECRET", "ACTIVE", "RESULT_BODY_SECRET"))


@pytest.mark.parametrize("value", [None, [], {}, False, "", 0, [{"function": {"name": "secret schema"}}]])
def test_tools_presence_kinds_and_digest_are_distinct(engine, monkeypatch, value):
    async def behavior(e, agent):
        agent._build_api_kwargs = lambda messages, **kw: {"messages": messages, "tools": value}
        engine.build(agent)
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    tools = doc["observations"][0]["tools"]
    assert tools == observation._tools_digest({"tools": value}) and tools["status"] == "observed"
    assert tools != observation._tools_digest({})


@pytest.mark.parametrize("bad", [object(), float("nan"), "x" * (observation.MAX_CONTENT_BYTES + 1)])
def test_invalid_tools_do_not_erase_valid_content(engine, monkeypatch, bad):
    async def behavior(e, agent):
        agent._build_api_kwargs = lambda messages, **kw: {"messages": messages, "tools": bad}
        engine.build(agent)
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert doc["observations"][0]["tools"]["status"] == "unavailable"
    assert doc["observations"][0]["content_bytes"] > 0


@pytest.mark.parametrize("gate", ["scope", "plugin", "pruned", "guardrail", "synthetic"])
def test_native_policy_and_synthetic_results_do_not_claim_callback_entry(engine, monkeypatch, gate):
    callbacks = []
    async def behavior(e, agent):
        if gate == "plugin": e.state.plugin_block = "refused"
        if gate == "pruned": e.state.pruned = ["argument"]
        if gate == "guardrail": e.state.guard = False
        if gate == "synthetic": e.state.synthetic = True
        ref = e.ref()
        managed = e.execute(agent, ref, lambda args: callbacks.append(args), scope_block="refused" if gate == "scope" else None)
        e.commit(agent, ref, managed.result, blocked=managed.blocked, is_error=managed.blocked)
        # This upstream flag is true for native pre-callback refusals.
        assert managed.dispatched is (gate != "synthetic")
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert callbacks == [] and doc["executions"] == []
    assert doc["commits"][0]["correlation"] == {"status": "callback_not_observed"}


@pytest.mark.parametrize("mode,expected", [("success", "commit_tuple_returned"), ("false", "commit_none_returned"), ("raise", "raised")])
def test_original_flush_outcome_remains_separate_from_execution(engine, monkeypatch, mode, expected):
    async def behavior(e, agent):
        ref = e.ref()
        e.execute(agent, ref, lambda args: "RETURN_SECRET")
        e.state.flush = mode != "false"
        if mode == "raise": e.state.commit_error = RuntimeError("FLUSH_SECRET")
        if mode == "raise":
            with pytest.raises(RuntimeError, match="FLUSH_SECRET"):
                e.commit(agent, ref, "RETURN_SECRET", effect_disposition="unknown", is_error=True)
        else:
            e.commit(agent, ref, "RETURN_SECRET", effect_disposition="unknown", is_error=True)
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert doc["executions"][0]["state"] == "returned"
    commit = doc["commits"][0]
    assert commit["state"] == expected and commit["reported_effect_disposition"] == "unknown"
    assert commit["is_error"] is True and commit["correlation"]["status"] == "unique_identity_match"
    assert "RETURN_SECRET" not in json.dumps(doc) and "FLUSH_SECRET" not in json.dumps(doc)


def test_callback_exception_is_preserved_without_exception_text(engine, monkeypatch):
    original = RuntimeError("CALLBACK_SECRET")
    async def behavior(e, agent):
        def fail(args): raise original
        with pytest.raises(RuntimeError) as caught:
            e.execute(agent, e.ref(), fail)
        assert caught.value is original
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert doc["executions"][0]["state"] == "raised" and doc["commits"] == []
    assert "CALLBACK_SECRET" not in json.dumps(doc)


@pytest.mark.parametrize("disabled", [False, True])
def test_actual_noop_persistence_can_return_a_normal_commit_tuple(engine, monkeypatch, disabled):
    persistence = definitions(monkeypatch, engine.vendor, "agent/session_persistence.py",
        {"_persist_lock", "SessionPersistenceMixin"},
        methods={"_flush_messages_to_session_db", "_flush_messages_to_session_db_unlocked"},
        values={"Optional": Optional, "nullcontext": contextlib.nullcontext})
    async def behavior(e, agent):
        agent._persist_disabled = disabled
        agent._session_db = object() if disabled else None
        agent._flush_messages_to_session_db_unlocked = persistence.SessionPersistenceMixin._flush_messages_to_session_db_unlocked.__get__(agent)
        e.state.flush_impl = persistence.SessionPersistenceMixin._flush_messages_to_session_db.__get__(agent)
        assert e.state.flush_impl([]) is None
        e.execute(agent, e.ref(), lambda args: "result")
        result = e.commit(agent, e.ref())
        assert type(result) is tuple and len(result) == 3
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert doc["commits"][0]["state"] == "commit_tuple_returned"
    assert engine.engine.state.flushes == []
    assert "durable" not in json.dumps(doc) and "acknowledged" not in json.dumps(doc)


def test_observer_failure_cannot_block_or_replay_native_execution(engine, monkeypatch):
    original = observation._Scope.tool_start
    calls = []
    def fail(scope, *args, **kwargs):
        if "commit" not in kwargs:
            raise ValueError("OBSERVER_SECRET")
        return original(scope, *args, **kwargs)
    monkeypatch.setattr(observation._Scope, "tool_start", fail)
    async def behavior(e, agent):
        managed = e.execute(agent, e.ref(), lambda args: calls.append(True) or "result")
        e.commit(agent, e.ref(), managed.result)
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert calls == [True] and len(engine.engine.state.flushes) == 1
    assert doc["executions"] == [] and doc["errors"] == ["tool_observation_failed"]
    assert doc["commits"][0]["correlation"] == {"status": "coverage_limited"}
    assert "OBSERVER_SECRET" not in json.dumps(doc)


def test_agent_replacement_with_identical_labels_cannot_create_a_unique_join(engine, monkeypatch):
    async def behavior(e, agent):
        e.execute(agent, e.ref(), lambda args: "result")
        replacement = SimpleNamespace(**vars(agent))
        scope = observation._current.get()
        engine.authority.adopt_agent(scope.session_id, scope.generation, replacement)
        e.commit(replacement, e.ref())
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert doc["errors"] == ["tool_agent_changed"]
    assert doc["commits"][0]["correlation"] == {"status": "coverage_limited"}


def test_generation_change_after_entry_does_not_upgrade_the_record(engine, monkeypatch):
    async def behavior(e, agent):
        def callback(args):
            scope = observation._current.get()
            engine.rows[scope.session_id] = {**engine.rows[scope.session_id], "generation": scope.generation + 1}
            return "result"
        e.execute(agent, e.ref(), callback)
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert doc["executions"][0]["state"] == "entered" and doc["errors"] == ["tool_observation_failed"]


def test_foreign_agent_cannot_contribute_tool_evidence(engine, monkeypatch):
    calls = []
    async def behavior(e, agent):
        foreign = SimpleNamespace(**vars(agent))
        e.execute(foreign, e.ref(), lambda args: calls.append(True) or "result")
        e.commit(foreign, e.ref())
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert calls == [True]  # Optional observation adds no authorization decision.
    assert doc["executions"] == doc["commits"] == []
    assert doc["errors"] == ["unbound_or_stale_agent"]


def test_actual_thread_context_concurrency_commits_in_different_order(engine, monkeypatch):
    async def behavior(e, agent):
        e.prepare(agent)
        ready, release = threading.Event(), threading.Event()
        first, second = e.ref("call-a"), e.ref("call-b")
        def slow(args):
            ready.set()
            assert release.wait(3)
            return "FIRST_SECRET"
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(e.thread_context.propagate_context_to_thread(lambda: e.execute(agent, first, slow)))
            assert ready.wait(3)
            fast = pool.submit(e.thread_context.propagate_context_to_thread(lambda: e.execute(agent, second, lambda args: "SECOND_SECRET")))
            assert fast.result(3).result == "SECOND_SECRET"
            e.commit(agent, second, "SECOND_SECRET")
            release.set()
            assert future.result(3).result == "FIRST_SECRET"
            e.commit(agent, first, "FIRST_SECRET")
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert [x["identity"]["tool_call_id"] for x in doc["executions"]] == ["call-a", "call-b"]
    assert [x["correlation"]["execution_sequence"] for x in doc["commits"]] == [2, 1]
    assert [x["sequence"] for x in doc["commits"]] == [3, 4]


@pytest.mark.parametrize("mode,expected", [("duplicate_execution", "ambiguous_identity"), ("duplicate_commit", "ambiguous_identity"),
    ("missing", "incomplete_identity"), ("commit_first", "invalid_order")])
def test_ambiguous_or_missing_native_identity_never_gets_a_positive_join(engine, monkeypatch, mode, expected):
    async def behavior(e, agent):
        ref = e.ref(None if mode == "missing" else "same-call")
        if mode == "commit_first": e.commit(agent, ref)
        e.execute(agent, ref, lambda args: "result")
        if mode == "duplicate_execution": e.execute(agent, ref, lambda args: "other result")
        if mode != "commit_first": e.commit(agent, ref)
        if mode == "duplicate_commit": e.commit(agent, ref)
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert all(x["correlation"] == {"status": expected} for x in doc["commits"])


def test_late_worker_cannot_strengthen_sealed_evidence(engine, monkeypatch):
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    workers = []
    async def behavior(e, agent):
        ref = e.ref()
        def callback(args):
            started.set()
            assert release.wait(3)
            return "LATE_SECRET"
        def work():
            try: e.execute(agent, ref, callback)
            finally: finished.set()
        worker = threading.Thread(target=e.thread_context.propagate_context_to_thread(work))
        workers.append(worker)
        worker.start()
        assert started.wait(3)
        e.commit(agent, ref, "timeout", is_error=True, effect_disposition="unknown")
    try:
        doc, restored, read = run_tools(engine, monkeypatch, behavior)
        before = json.dumps(restored, sort_keys=True)
        assert doc["executions"][0]["state"] == "entered"
        release.set()
        assert finished.wait(3)
        assert json.dumps(restored, sort_keys=True) == before and read()["request_observation"] == doc
    finally:
        release.set()
        for worker in workers: worker.join(3)


@pytest.mark.parametrize("mode", ["count", "bytes"])
def test_shared_budget_overflow_is_explicit_and_does_not_affect_native_calls(engine, monkeypatch, mode):
    callbacks = []
    async def behavior(e, agent):
        for index in range(25):
            ref = e.ref(str(index) if mode == "count" else ('"\\' * 120 + str(index)))
            if mode == "bytes":
                ref.task_id = '"\\' * 128
            e.execute(agent, ref, lambda args: callbacks.append(True) or "result")
            e.commit(agent, ref)
    doc, _, _ = run_tools(engine, monkeypatch, behavior)
    assert len(callbacks) == 25 and len(engine.engine.state.flushes) == 25
    assert doc["tool_overflow"] is True
    assert len(json.dumps(doc, ensure_ascii=False, allow_nan=False).encode()) <= observation.MAX_METADATA_BYTES
    assert all(x["correlation"]["status"] == "coverage_limited" for x in doc["commits"])


@pytest.mark.parametrize("case", ["raw_args", "wrong_join", "duplicate_sequence", "wrong_order", "invented_state", "true_proof",
    "missing_gap", "extra_tools", "bad_flag", "bad_scope", "unexpected_identity"])
def test_malformed_v2_projection_preserves_original_answer(engine, monkeypatch, case):
    async def behavior(e, agent):
        e.execute(agent, e.ref(), lambda args: "result")
        e.commit(agent, e.ref())
    _, restored, read = run_tools(engine, monkeypatch, behavior)
    doc = restored[observation.RESULT_KEY]
    if case == "raw_args": doc["executions"][0]["args"] = {"password": "SECRET"}
    elif case == "wrong_join": doc["commits"][0]["correlation"]["execution_sequence"] = 9
    elif case == "duplicate_sequence": doc["commits"][0]["sequence"] = 1
    elif case == "wrong_order":
        doc["executions"][0]["sequence"], doc["commits"][0]["sequence"] = 2, 1
        doc["commits"][0]["correlation"]["execution_sequence"] = 2
    elif case == "invented_state": doc["commits"][0]["state"] = "effect_proven"
    elif case == "true_proof": doc["provider_dispatch_proven"] = True
    elif case == "missing_gap": doc["metadata_overflow"] = True
    elif case == "extra_tools": doc["observations"] = [{"tools": {"raw": "SECRET"}}]
    elif case == "bad_flag": doc["commits"][0]["blocked"] = 0
    elif case == "bad_scope": doc["scope"]["admission_id"] = "foreign"
    elif case == "unexpected_identity": doc["executions"][0]["identity"]["raw_result"] = "SECRET"
    result = read()
    assert result["answer"] == "[redacted]" and result["successful"] is True
    assert result["request_observation_error"] == "INVALID_RETAINED_OBSERVATION"
    assert "request_observation" not in result
