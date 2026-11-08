"""Qualified original worker retirement; no gateway, provider or socket is started."""
from __future__ import annotations

import ast
import asyncio
from collections import deque
from contextlib import suppress
from functools import partial
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WORKER = "gateway/session_managed_worker.py"
RUNTIME = "gateway/session_runtime_workers.py"
DONOR_BLOBS = {
    WORKER: "86baeb5c76304465f14e685a5e48828d5cbb695c",
    RUNTIME: "a22f82587ed5c80ae2641d589d5f8856eca59d0f",
}


class StoreError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def sources():
    from integrations.hermes_qualification.native_eval_inputs import qualify
    privacy = Path(__file__).resolve().parents[2] / "hermes_qualification/workspace_oauth_privacy/fixtures"
    values = {}
    for path in qualify.PATHS:
        root = (FIXTURES / "request_observation" if path == "gateway/session_authority.py"
                else FIXTURES / "native_eval_inputs"
                if path.startswith("hermes_state_") or path in DONOR_BLOBS else privacy)
        values[path] = (root / (path.replace("/", "__") + ".source")).read_bytes()
    patched = qualify.prepare_sources(values)
    for path, expected in DONOR_BLOBS.items():
        raw = (FIXTURES / "native_eval_inputs" / (path.replace("/", "__") + ".source")).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected
        # This fallback permits the same behavioral regression to run on the
        # preceding qualified derivation, before the owner repair is applied.
        patched.setdefault(path, raw)
    return patched


def compile_nodes(raw, names, namespace, path):
    nodes = [n for n in ast.parse(raw).body if getattr(n, "name", None) in names]
    assert {n.name for n in nodes} == set(names)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[])),
                 path, "exec"), namespace)


def module(monkeypatch, name, **attributes):
    value = ModuleType(name)
    value.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, value)
    return value


@pytest.fixture
def owners(monkeypatch):
    raw = sources()
    module(monkeypatch, "gateway", __path__=[])
    module(monkeypatch, "agent", __path__=[])
    module(monkeypatch, "hermes_state_runtime", RuntimeStoreError=StoreError)
    module(monkeypatch, "gateway.session_tui_side", _abandoned=lambda holder: False)
    module(monkeypatch, "gateway.run_runtime", stop_authority_turns=lambda *a, **k: None)
    module(monkeypatch, "agent.interrupt_compat", request_hard_interrupt=lambda *a, **k: None)
    runtime = module(monkeypatch, "gateway.session_runtime_workers",
                     asyncio=asyncio, RuntimeStoreError=StoreError,
                     all_authorities=lambda runner: runner.authorities)
    names = {n.name for n in ast.parse(raw[RUNTIME]).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    compile_nodes(raw[RUNTIME], names, runtime.__dict__, RUNTIME)
    worker = module(monkeypatch, "gateway.session_managed_worker",
                    asyncio=asyncio, suppress=suppress, partial=partial, json=json,
                    os=os, queue=queue, deque=deque, threading=threading, subprocess=subprocess,
                    sys=sys, time=time, RuntimeStoreError=StoreError,
                    HELLO_SECONDS=60, STOP_ACK_SECONDS=30, Path=Path,
                    __file__=str(FIXTURES / "native_eval_inputs/gateway__session_managed_worker.py.source"),
                    WORKER_POPEN={"start_new_session": True, "close_fds": True})
    compile_nodes(raw[WORKER], {"ManagedWorker", "ManagedExecutionUnknown", "execute_managed",
                  "_close_worker_safely", "_prune_retired_worker", "_bind_worker_reservation",
                  "_spawn_registered_worker", "_mark_spawning"},
                  worker.__dict__, WORKER)
    return SimpleNamespace(worker=worker, runtime=runtime, raw=raw, monkeypatch=monkeypatch,
                           original_tracked_write=runtime.tracked_write)


class Process:
    """Fixture process handle: no signals, processes or network operations."""
    pid = 999999999

    def __init__(self, alive=True):
        self.alive = alive
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.waits = []

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.alive:
            raise subprocess.TimeoutExpired("fixture", timeout)
        return 0


def worker(owners, *, alive=True, closed=False):
    result = owners.worker.ManagedWorker(Process(alive))
    result._signal_worker = lambda **kwargs: None
    result._signal_group = lambda **kwargs: None
    if closed:
        result.closed.set()
    return result


def authority(value):
    runner = SimpleNamespace(_running_agents={})
    result = SimpleNamespace(_managed_workers={"session": value}, sessions={}, runner=runner)
    runner.authorities = [result]
    return result


def finish(value):
    value.closed.set()
    value.process.alive = False
    for stream in (value.process.stdin, value.process.stdout, value.process.stderr):
        stream.close()


def test_io_stop_does_not_remove_live_worker_from_capacity(owners):
    value = worker(owners, closed=True)
    owner = authority(value)
    assert owners.runtime.uncounted_runtime_work(owner.runner) == 1
    assert owner._managed_workers["session"] is value


def test_profile_join_keeps_original_ownership_while_managed_teardown_is_pending(owners):
    value = worker(owners, closed=True)
    owner = authority(value)
    with pytest.raises(TimeoutError, match="ownership retained"):
        asyncio.run(owners.runtime.join_authority_work(owner, timeout=0))
    assert owner._managed_workers["session"] is value


def test_close_does_not_close_stdin_owned_by_an_inflight_sender(owners):
    value = worker(owners, alive=False)
    value.write_lock.acquire()
    try:
        value.close()
        assert not value.process.stdin.closed
    finally:
        value.write_lock.release()


def test_original_execute_retains_map_entry_during_and_after_unproven_close(owners):
    seen = []
    value = worker(owners)
    owner = authority(value)
    owner.adopt_agent = lambda *a: None
    ref = SimpleNamespace(session_id="session")
    row = {"admission_id": "admission", "generation": 7}
    async def context(*a):
        return "fixture", None
    async def spawn(*a):
        return value, value.process
    async def next_frame(*a, **k):
        raise StoreError("fixture_hello_lost")
    def close():
        seen.append(owner._managed_workers.get("session") is value)
        value.closed.set()
    value.next_frame = next_frame
    value.close = close
    owners.worker._mark_spawning = lambda *a: None
    owners.worker._stopped_before_spawn = lambda *a: False
    owners.worker._spawn_registered_worker = spawn
    module(owners.monkeypatch, "gateway.run_turn_progress", publish_worker_tool_event=lambda *a: False)
    module(owners.monkeypatch, "gateway.session_context_refs", managed_turn_text=context,
           refused_turn_result=lambda *a: None)
    with pytest.raises(StoreError, match="fixture_hello_lost"):
        asyncio.run(owners.worker.execute_managed(owner, ref, row, object()))
    assert seen == [True]
    assert owner._managed_workers["session"] is value


@pytest.mark.parametrize("edge", ["process", "writer", "reader", "stderr", "pipe"])
def test_retirement_requires_every_owned_resource_to_finish(owners, edge):
    value = worker(owners, alive=False)
    finish(value)
    if edge == "process":
        value.process.alive = True
    elif edge == "pipe":
        value.process.stdin = io.BytesIO()
    else:
        setattr(value, {"stderr": "stderr_drain"}.get(edge, edge),
                SimpleNamespace(is_alive=lambda: True))
    assert value.retirement_complete() is False


def test_exit_zero_and_closed_owned_resources_can_retire(owners):
    value = worker(owners, alive=False)
    finish(value)
    assert value.retirement_complete() is True
    owner = authority(value)
    assert owners.runtime.uncounted_runtime_work(owner.runner) == 0
    assert owner._managed_workers == {}
    asyncio.run(owners.runtime.join_authority_work(owner, timeout=0))


@pytest.mark.parametrize("which", ["reader", "stderr_drain"])
def test_close_handles_an_allocated_but_unstarted_io_thread(owners, which):
    value = worker(owners, alive=False)
    setattr(value, which, threading.Thread(target=lambda: None))
    value.close()
    assert value.retirement_complete() is True


def test_retirement_probe_does_not_signal_join_wait_or_restart(owners):
    value = worker(owners, alive=False)
    finish(value)
    def forbidden(*a, **k):
        pytest.fail("observation performed a cleanup or execution action")
    value.process.wait = forbidden
    value._signal_worker = value._signal_group = forbidden
    value.writer.join = forbidden
    assert value.retirement_complete() is True
    assert value.process.waits == []


@pytest.mark.parametrize("status", ["same", "reused", "missing", "denied"])
def test_verified_interpreter_identity_must_be_resolved_without_signalling(owners, status):
    value = worker(owners, alive=False)
    finish(value)
    value.worker = (123456789, "original-birth")
    class ProcessError(Exception):
        pass
    class Missing(ProcessError):
        pass
    def lookup(pid):
        assert pid == 123456789
        if status == "missing":
            raise Missing()
        if status == "denied":
            raise ProcessError()
        return SimpleNamespace(birth="other-birth" if status == "reused" else "original-birth")
    module(owners.monkeypatch, "psutil", Process=lookup, Error=ProcessError, NoSuchProcess=Missing)
    module(owners.monkeypatch, "hermes_cli", __path__=[])
    module(owners.monkeypatch, "hermes_cli.process_identity", process_birth=lambda proc: proc.birth)
    assert value.retirement_complete() is (status in {"reused", "missing"})


@pytest.mark.parametrize("replace_map", [False, True])
def test_retirement_never_prunes_a_replacement_owner_or_entry(owners, replace_map):
    original = worker(owners, alive=False)
    finish(original)
    replacement = worker(owners, closed=True)
    owner = authority(original)
    def changed():
        if replace_map:
            owner._managed_workers = {"session": replacement}
        else:
            owner._managed_workers["session"] = replacement
        return True
    original.retirement_complete = changed
    with pytest.raises(StoreError, match="managed_worker_owner_changed"):
        list(owners.runtime.managed_workers(owner))
    assert owner._managed_workers["session"] is replacement


def claim_owner(owners, value, *, unknown=False):
    pending = [{"status": "unknown" if unknown else "queued", "admission_id": "next-admission",
                "request_id": "next-request", "payload": {}}]
    claimed = []
    tree = ast.parse(owners.raw["gateway/session_authority.py"])
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SessionAuthority")
    names = {"_claim_next", "_claim_with_retry", "_drain_stopping"}
    cls.body = [n for n in cls.body if getattr(n, "name", None) in names]
    namespace = {"asyncio": asyncio, "partial": partial, "RuntimeStoreError": StoreError,
                 "sqlite3": __import__("sqlite3"), "_CLAIM_RETRY_MIN_S": .001,
                 "_CLAIM_RETRY_MAX_S": .01,
                 "list_session_admissions": lambda *a, **k: list(pending)}
    def claim(*a, **k):
        claimed.append(k)
        return {"admission_id": k["head"], "generation": 8}
    namespace["claim_session_input"] = claim
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, cls], type_ignores=[])),
                 "gateway/session_authority.py", "exec"), namespace)
    owner = object.__new__(namespace["SessionAuthority"])
    owner._managed_workers = {"session": value}
    owner.runner = SimpleNamespace(_draining=False)
    owner.retiring = False
    owner.db, owner.epoch = object(), 1
    owner._classic_turn_holds = lambda route: False
    owner._require_admission_open = lambda: None
    owner._admission_gate = lambda: object()
    owner._stamp_claim = lambda ref, live, row: row
    owner.pauses = []
    owner._pause = lambda ref, reason: owner.pauses.append(reason)
    live = SimpleNamespace(claim_gate=asyncio.Lock(), mutation_lock=asyncio.Lock(),
                           source=SimpleNamespace(platform="telegram"), route="route", rescan=False)
    owner.sessions = {"session": live}
    module(owners.monkeypatch, "gateway.config",
           Platform=SimpleNamespace(LOCAL="local", API_SERVER="api"))
    async def tracked_write(authority, write, *, then):
        return then(write())
    owners.runtime.tracked_write = tracked_write
    return owner, live, SimpleNamespace(session_id="session"), pending, claimed


def test_next_claim_waits_before_any_successor_is_claimed(owners):
    value = worker(owners, closed=True)
    owner, live, ref, pending, claimed = claim_owner(owners, value)
    assert asyncio.run(owner._claim_next(ref, live)) == ("managed_retiring", pending[0])
    assert claimed == []
    assert pending[0]["status"] == "queued"


def test_unknown_execution_keeps_priority_over_retirement_wait(owners):
    value = worker(owners, closed=True)
    owner, live, ref, pending, claimed = claim_owner(owners, value, unknown=True)
    with pytest.raises(StoreError, match="unknown_execution"):
        asyncio.run(owner._claim_next(ref, live))
    assert claimed == []
    assert pending[0]["status"] == "unknown"


def test_existing_claim_loop_resumes_only_after_original_worker_retires(owners):
    value = worker(owners, closed=True)
    owner, live, ref, pending, claimed = claim_owner(owners, value)
    async def run():
        task = asyncio.create_task(owner._claim_with_retry(ref, live))
        await asyncio.sleep(.005)
        assert not task.done() and claimed == []
        finish(value)
        result = await asyncio.wait_for(task, .25)
        return result
    row, first = asyncio.run(run())
    assert row["admission_id"] == first["admission_id"] == "next-admission"
    assert len(claimed) == 1 and owner._managed_workers == {}


def test_existing_claim_loop_stops_with_the_original_queued_head_intact(owners):
    value = worker(owners, closed=True)
    owner, live, ref, pending, claimed = claim_owner(owners, value)
    owner.retiring = True
    assert asyncio.run(owner._claim_with_retry(ref, live)) is None
    assert claimed == [] and pending[0]["status"] == "queued"
    assert owner._managed_workers["session"] is value


def test_send_after_io_stop_is_refused_and_closes_its_owned_pipe(owners):
    value = worker(owners, alive=False, closed=True)
    owners.worker.encode_frame = lambda frame: b"fixture"
    with pytest.raises(StoreError, match="managed_worker_lost"):
        value.send({"type": "fixture"})
    assert value.process.stdin.closed


@pytest.mark.parametrize("cleanup_error", [False, True])
def test_finished_result_survives_pending_teardown_and_original_queue_resumes(owners, cleanup_error):
    value = worker(owners)
    owner, live, ref, pending, claimed = claim_owner(owners, value)
    owner.pending_results = {}
    owner.executing = {"session": 7}
    owner.adopt_agent = lambda *a: None
    owner.runner._running_agents = {}
    owner.runner.authorities = [owner]
    live.task = None
    live.event_stream = SimpleNamespace(lock=threading.RLock(), execution={})
    live.controls = SimpleNamespace(snapshot=lambda *a: None)
    result = {"final_response": "retained original answer"}
    frames = iter([{"type": "hello"}, {"type": "result", "result": result}, {"type": "finished"}])
    async def frame(*a, **k):
        return next(frames)
    sent = []
    value.next_frame = frame
    value.send = sent.append
    class Writer:
        ident = None
        alive = False
        def start(self):
            self.ident, self.alive = 1, True
        def join(self, timeout=None):
            self.alive = False
        def is_alive(self):
            return self.alive
    value.writer = Writer()
    if cleanup_error:
        original_close = value.close
        def failed_close():
            original_close()
            raise OSError("fixture cleanup failure")
        value.close = failed_close
    async def context(*a):
        return "fixture", None
    async def spawn(*a):
        return value, value.process
    async def tracked_write(authority, write, *, then=None):
        out = write()
        followed = out if then is None else then(out)
        return await followed if asyncio.iscoroutine(followed) else followed
    owners.runtime.tracked_write = tracked_write
    owners.worker._mark_spawning = lambda *a: None
    owners.worker._stopped_before_spawn = lambda *a: False
    owners.worker._spawn_registered_worker = spawn
    owners.worker._bootstrap = lambda *a: {"api_key": None}
    owners.worker._prompt_frame = lambda *a: False
    owners.worker.accept_result = lambda row: (row, {"fixture_tokens": 3})
    owners.worker._with_stop_cause = lambda row, worker: row
    owners.worker._settled_session_usage = lambda *a: {}
    module(owners.monkeypatch, "gateway.run_turn_progress", publish_worker_tool_event=lambda *a: False)
    module(owners.monkeypatch, "gateway.session_context_refs", managed_turn_text=context,
           refused_turn_result=lambda *a: None)
    owners.worker.reserve_admission_worker = lambda *a, **k: {
        "pid": value.process.pid, "birth": "fixture-birth", "secret": "fixture-only",
        "session_id": "session", "execution_id": "execution"}
    row = {"admission_id": "original-admission", "generation": 7, "principal_id": "fixture"}
    async def run():
        answer = await owners.worker.execute_managed(owner, ref, row, object())
        assert answer == result["final_response"]
        retained = json.loads(json.dumps(owner.pending_results))
        assert retained == {"original-admission": {
            "result": {**result, "local_viewer": True}, "usage": {"fixture_tokens": 3}}}
        assert owner._managed_workers["session"] is value
        assert owners.runtime.uncounted_runtime_work(owner.runner) == 1
        with pytest.raises(TimeoutError, match="ownership retained"):
            await owners.runtime.join_authority_work(owner, timeout=0)
        task = asyncio.create_task(owner._claim_with_retry(ref, live))
        await asyncio.sleep(.005)
        assert not task.done() and claimed == []
        finish(value)
        next_row, head = await asyncio.wait_for(task, .25)
        assert next_row["admission_id"] == head["admission_id"] == "next-admission"
        assert owner.pending_results == retained
        assert owner._managed_workers == {} and len(claimed) == 1
    asyncio.run(run())
    assert sent[-1] == {"type": "finish"}


def test_inflight_sender_closes_its_own_pipe_after_stop(owners):
    entered, release = threading.Event(), threading.Event()
    class Pipe(io.BytesIO):
        def write(self, data):
            entered.set()
            assert release.wait(1)
            return super().write(data)
    value = worker(owners, alive=False)
    value.process.stdin = Pipe()
    owners.worker.encode_frame = lambda frame: b"fixture"
    failures = []
    def send():
        try:
            value.send({"type": "fixture"})
        except BaseException as error:
            failures.append(error)
    sender = threading.Thread(target=send)
    sender.start()
    try:
        assert entered.wait(1)
        value.close()
        assert not value.process.stdin.closed
        assert value.retirement_complete() is False
    finally:
        release.set()
        sender.join(timeout=1)
    assert not sender.is_alive() and not failures
    assert value.process.stdin.closed and value.retirement_complete()


def test_control_writer_finally_never_waits_for_another_sender(owners):
    value = worker(owners, alive=False, closed=True)
    value.write_lock.acquire()
    thread = threading.Thread(target=value._write_controls)
    thread.start()
    try:
        thread.join(timeout=.25)
        assert not thread.is_alive()
        assert not value.process.stdin.closed
    finally:
        value.write_lock.release()
        thread.join(timeout=1)
    with pytest.raises(StoreError):
        value.send({"type": "closed"})
    assert value.process.stdin.closed


def test_real_finite_child_handle_and_pipes_retire(owners):
    # Ordinary finite local child only; the two signal functions are explicit
    # fixture edges. No native gateway, provider, socket or credential is used.
    process = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    value = worker(owners, alive=False)
    value.process = process
    try:
        assert process.wait(timeout=5) == 0
        value.close()
        assert value.retirement_complete() is True
        assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


@pytest.mark.parametrize("replace_map", [False, True])
def test_finalizer_rechecks_identity_after_retirement_observation(owners, replace_map):
    original = worker(owners, alive=False)
    finish(original)
    replacement = worker(owners, closed=True)
    owner = authority(original)
    captured = owner._managed_workers
    def changed():
        if replace_map:
            owner._managed_workers = {"session": replacement}
        else:
            captured["session"] = replacement
        return True
    original.retirement_complete = changed
    assert owners.worker._prune_retired_worker(owner, "session", captured, original) is False
    assert owner._managed_workers["session"] is replacement


def test_full_snapshot_refuses_insertions_before_yielding_or_pruning(owners):
    pending = worker(owners, closed=True)
    original = worker(owners, alive=False)
    finish(original)
    replacement = worker(owners, closed=True)
    owner = authority(pending)
    owner._managed_workers["second"] = original
    def changed():
        owner._managed_workers["new-session"] = replacement
        return True
    original.retirement_complete = changed
    with pytest.raises(StoreError, match="managed_worker_owner_changed"):
        next(owners.runtime.managed_workers(owner))
    assert owner._managed_workers["second"] is original
    assert owner._managed_workers["new-session"] is replacement


def test_failed_retirement_inspection_stays_counted(owners):
    value = worker(owners, alive=False)
    finish(value)
    def failed():
        raise OSError("fixture inspection unavailable")
    value.retirement_complete = failed
    owner = authority(value)
    assert owners.runtime.uncounted_runtime_work(owner.runner) == 1
    assert owners.worker._prune_retired_worker(owner, "session", owner._managed_workers, value) is False
    assert owner._managed_workers["session"] is value


@pytest.mark.parametrize("alive", [False, True])
def test_stderr_start_failure_occurs_after_process_custody_is_registered(owners, alive):
    process = Process(alive=alive)
    owner = SimpleNamespace()
    ref, row = SimpleNamespace(session_id="session"), {"generation": 7}
    observed = []
    async def acquire(factory, *args, **kwargs):
        assert factory is subprocess.Popen
        return process
    def failed_drain(value, path):
        observed.append(owner._managed_workers.get("session") is value)
        value.stderr_drain = threading.Thread(target=lambda: None)
        raise OSError("fixture thread start failure")
    owners.monkeypatch.setattr(owners.worker.ManagedWorker, "drain_stderr", failed_drain)
    owners.monkeypatch.setattr(owners.worker.ManagedWorker, "_signal_worker", lambda *a, **k: None)
    owners.monkeypatch.setattr(owners.worker.ManagedWorker, "_signal_group", lambda *a, **k: None)
    owners.worker._worker_env = lambda *a: {}
    owners.worker._latched_stop_cause = lambda *a: None
    module(owners.monkeypatch, "gateway.session_worker_spawn", acquire_process=acquire)
    module(owners.monkeypatch, "gateway.session_managed_worker_log",
           worker_log_path=lambda *a: Path("fixture-only.log"))
    owner.profile_id = "/fixture"
    with pytest.raises(OSError, match="fixture thread start failure"):
        asyncio.run(owners.worker._spawn_registered_worker(owner, ref, row))
    assert observed == [True] and owner._managed_spawning == {}
    if alive:
        retained = owner._managed_workers["session"]
        assert retained.process is process and retained.closed.is_set()
        assert not retained.retirement_complete()
    else:
        assert owner._managed_workers == {}
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed


def reservation_setup(owners, value):
    owner = authority(value)
    owner.adopt_agent = lambda *a: None
    owner.pending_results, owner.waiters = {}, {}
    owner.executing = {"session": 7}
    published = []
    live = SimpleNamespace(event_stream=SimpleNamespace(
        lock=threading.RLock(), execution={}, publish=lambda *a, **k: published.append((a, k))),
        controls=SimpleNamespace(snapshot=lambda *a: None), task=None)
    owner.sessions = {"session": live}
    owner._publish_pending = lambda *a: None
    ref = SimpleNamespace(session_id="session")
    row = {"admission_id": "original-admission", "generation": 7, "principal_id": "fixture"}
    async def context(*a):
        return "fixture", None
    async def spawn(*a):
        return value, value.process
    owners.worker._mark_spawning = lambda *a: None
    owners.worker._stopped_before_spawn = lambda *a: False
    owners.worker._spawn_registered_worker = spawn
    owners.worker._bootstrap = lambda *a: {"api_key": None}
    owners.worker._prompt_frame = lambda *a: False
    owners.runtime.tracked_write = owners.original_tracked_write
    value.send = lambda *a: None
    value.writer = SimpleNamespace(ident=None, start=lambda: None, is_alive=lambda: False)
    module(owners.monkeypatch, "gateway.run_turn_progress", publish_worker_tool_event=lambda *a: False)
    module(owners.monkeypatch, "gateway.session_context_refs", managed_turn_text=context,
           refused_turn_result=lambda *a: None)
    return owner, ref, row, published


def test_original_unknown_survives_cleanup_error(owners):
    value = worker(owners)
    owner, ref, row, published = reservation_setup(owners, value)
    reads = []
    async def frame(*a, **k):
        if not reads:
            reads.append(True)
            return {"type": "hello"}
        raise StoreError("fixture worker lost")
    value.next_frame = frame
    owners.worker.reserve_admission_worker = lambda *a, **k: {
        "pid": value.process.pid, "birth": "fixture-birth", "secret": "fixture-only",
        "session_id": "session", "execution_id": "execution"}
    unknown = []
    module(owners.monkeypatch, "gateway.session_worker_reservation",
           lose_admission_worker=lambda *a: unknown.append("unknown"))
    def failed_close():
        value.closed.set()
        raise OSError("fixture cleanup failure")
    value.close = failed_close
    with pytest.raises(owners.worker.ManagedExecutionUnknown, match="managed_worker_unknown"):
        asyncio.run(owners.worker.execute_managed(owner, ref, row, object()))
    assert unknown == ["unknown"] and owner._managed_workers["session"] is value
    assert owners.runtime.uncounted_runtime_work(owner.runner) == 1


def test_cancelled_reservation_binds_late_identity_in_the_original_tracked_task(owners):
    value = worker(owners, alive=False)
    owner, ref, row, published = reservation_setup(owners, value)
    entered, release = threading.Event(), threading.Event()
    gone, signals = [], []
    async def frame(*a, **k):
        return {"type": "hello"}
    value.next_frame = frame
    def reserve(*a, **k):
        entered.set()
        assert release.wait(2)
        return {"pid": 123456789, "birth": "original-birth", "secret": "fixture-only",
                "session_id": "session", "execution_id": "execution"}
    owners.worker.reserve_admission_worker = reserve
    owners.worker._interrupted_before_bootstrap = lambda *a: "interrupted before bootstrap"
    owners.worker._bootstrap = lambda *a: pytest.fail("cancelled admission was bootstrapped")
    def signal(**kwargs):
        if value.worker is not None:
            signals.append(value.worker)
            gone.append(True)
    value._signal_worker = signal
    class ProcessError(Exception):
        pass
    class Missing(ProcessError):
        pass
    def lookup(pid):
        assert pid == 123456789
        if gone:
            raise Missing()
        return SimpleNamespace(birth="original-birth")
    module(owners.monkeypatch, "psutil", Process=lookup, Error=ProcessError, NoSuchProcess=Missing)
    module(owners.monkeypatch, "hermes_cli", __path__=[])
    module(owners.monkeypatch, "hermes_cli.process_identity", process_birth=lambda proc: proc.birth)
    async def run():
        task = asyncio.create_task(owners.worker.execute_managed(owner, ref, row, object()))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            assert await task == "interrupted before bootstrap"
            assert value.reservation_unresolved and value.worker is None
            assert value.retirement_complete() is False
            assert owner._managed_workers["session"] is value
            assert len(owner._mutation_tasks) == 1
            release.set()
            await asyncio.wait_for(asyncio.gather(*list(owner._mutation_tasks)), 1)
            assert not value.reservation_unresolved
            assert value.worker == (123456789, "original-birth")
            assert signals == [value.worker]
            assert list(owners.runtime.managed_workers(owner)) == []
        finally:
            release.set()
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    asyncio.run(run())


def test_unresolved_reservation_cannot_be_retired_from_closed_launcher_pipes(owners):
    value = worker(owners, alive=False)
    finish(value)
    value.reservation_unresolved = True
    owner = authority(value)
    assert not value.retirement_complete()
    assert owners.runtime.uncounted_runtime_work(owner.runner) == 1
    assert owner._managed_workers["session"] is value


def test_current_derivation_binds_all_exact_worker_postimages():
    from integrations.hermes_qualification.native_eval_inputs import qualify
    from ops.executive_os import native_gateway_sources as owner
    patched = sources()
    assert owner.EVAL_INPUTS_DERIVATION_PATCH == hashlib.sha256(
        (qualify.ROOT / "guard.patch").read_bytes()).hexdigest()
    assert set(patched) == set(owner.EVAL_INPUTS_DERIVATION_POSTIMAGES)
    assert {name: hashlib.sha256(raw).hexdigest() for name, raw in patched.items()
            } == owner.EVAL_INPUTS_DERIVATION_POSTIMAGES
