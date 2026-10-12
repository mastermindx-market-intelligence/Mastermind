"""Real HTTP/adapter/PTY boundaries; never launches a provider or a Desktop app."""
from __future__ import annotations

import contextlib
import http.client
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import claude, contract, runner
from scripts import chairman_control_room as server

SID = "22222222-2222-4222-8222-222222222222"
BID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def navigation(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "projects"
    transcript = store / claude._slugify_project_dir(str(project)) / (SID + ".jsonl")
    transcript.parent.mkdir(parents=True)
    transcript.write_text("", encoding="utf-8")
    cli = tmp_path / "bridge-cli"
    cli.write_text("fixture only", encoding="utf-8")
    cli.chmod(0o700)
    binding = sb.new_binding(
        work_ref="WS:CCR", role="chairman", provider="claude_code",
        locator_kind="claude_code_session",
        locator={"project_dir": str(project), "session_id": SID},
        observed_at="2026-10-02T00:00:00Z", binding_id=BID,
    )
    return binding, store, cli


def version_ok(*args, **kwargs):
    return {"code": 0, "stdout": "2.1.285 (Claude Code)", "stderr": "", "timed_out": False}


def acknowledged(**overrides):
    return {"code": 0, "stdout": f"Opening session {SID} in Claude Desktop\r\n",
            "stderr": "", "timed_out": False, "started": True,
            "output_truncated": False, "process_reaped": True, **overrides}


def invoke(navigation, result, *, probe=version_ok):
    binding, store, cli = navigation
    calls = []
    def handoff(argv, **kwargs):
        calls.append((argv, kwargs))
        if isinstance(result, Exception):
            raise result
        return result
    outcome = contract.open_binding(
        binding, probe, claude_projects_dir=str(store), target_surface="desktop",
        claude_desktop_cli=str(cli), claude_desktop_handoff_runner=handoff,
    )
    return outcome, calls


@contextlib.contextmanager
def http_server(tmp_path, navigation, result):
    binding, store, cli = navigation
    bindings = tmp_path / "bindings.json"
    sb.save_bindings({"schema": sb.SCHEMA, "bindings": [binding]}, bindings)
    calls = []
    def handoff(argv, **kwargs):
        calls.append((argv, kwargs))
        return result
    config = server.ServerConfig(
        repo_root=tmp_path, macro_root=str(tmp_path), bindings_path=bindings,
        token="isolated-test-token", origin="http://127.0.0.1:0", port=0,
        runner=version_ok, claude_projects_dir=str(store), claude_desktop_cli=str(cli),
        claude_desktop_handoff_runner=handoff,
        now_fn=lambda: "2026-10-02T01:00:00Z",
    )
    httpd = server.ControlRoomServer(("127.0.0.1", 0), server.ChairmanControlRoomHandler, config)
    config.port = httpd.server_address[1]
    config.origin = f"http://127.0.0.1:{config.port}"
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    def post(target):
        conn = http.client.HTTPConnection("127.0.0.1", config.port, timeout=10)
        try:
            conn.request("POST", "/api/open", json.dumps({"binding_id": BID, "target_surface": target}),
                         {"X-CCR-Token": config.token, "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()
    try:
        yield post, calls, bindings
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize("bad", [[], {}, ["desktop"], {"surface": "desktop"}, True, 0, 1.5, "unknown"])
def test_http_rejects_bad_target_without_dispatch_or_binding_write(tmp_path, navigation, bad):
    with http_server(tmp_path, navigation, acknowledged()) as (post, calls, bindings):
        before = bindings.read_bytes()
        status, result = post(bad)
        assert status == 400
        assert "target_surface" in result["detail"]
        assert calls == []
        assert bindings.read_bytes() == before


@pytest.mark.parametrize("response", [None, [], {}, acknowledged(stdout=None),
    acknowledged(code=False), acknowledged(timed_out=True), acknowledged(code=1),
    acknowledged(stdout="not an acknowledgement"), acknowledged(output_truncated=True),
    RuntimeError("private backend path /private/sensitive")])
def test_uncertain_handoff_is_not_reported_as_known_failure(navigation, response):
    outcome, calls = invoke(navigation, response)
    assert outcome["ok"] is False
    assert outcome["failure_kind"] == "effect_unknown"
    assert outcome["verified"] is False
    assert len(calls) == 1
    assert SID not in json.dumps(outcome)
    assert "/private/sensitive" not in json.dumps(outcome)
    assert "retry" in outcome["detail"].lower()


def test_proven_process_not_started_remains_known_runner_error(navigation):
    outcome, calls = invoke(navigation, {
        "code": None, "stdout": "", "stderr": "file missing", "timed_out": False,
        "started": False, "output_truncated": False, "process_reaped": True,
    })
    assert outcome["failure_kind"] == "runner_error"
    assert outcome["verified"] is False
    assert len(calls) == 1


def test_http_unknown_does_not_advance_verified_stamp(tmp_path, navigation):
    with http_server(tmp_path, navigation, acknowledged(timed_out=True)) as (post, calls, bindings):
        before = bindings.read_bytes()
        status, outcome = post("desktop")
        assert status == 200
        assert outcome["failure_kind"] == "effect_unknown"
        assert bindings.read_bytes() == before
        assert len(calls) == 1


def test_real_http_positive_preserves_exact_identity(navigation, tmp_path):
    with http_server(tmp_path, navigation, acknowledged()) as (post, calls, bindings):
        status, outcome = post("desktop")
        assert status == 200 and outcome["verified"] is True
        assert outcome["action"] == "opened_desktop"
        assert "visible app state was not checked" in outcome["detail"].lower()
        assert calls[0][0] == [str(navigation[2]), "--desktop", "--resume", SID]
        doc = json.loads(bindings.read_text())
        assert doc["bindings"][0]["last_verified_at"] == "2026-10-02T01:00:00Z"


@pytest.mark.parametrize("probe_result", [None, [], {},
    {"code": False, "stdout": "2.1.285", "timed_out": False},
    {"code": 0, "stdout": None, "timed_out": False},
    {"code": 0, "stdout": "2.1.284", "timed_out": False}])
def test_invalid_version_never_reaches_handoff(navigation, probe_result):
    outcome, calls = invoke(navigation, acknowledged(), probe=lambda *a, **k: probe_result)
    assert outcome["failure_kind"] == "not_installed"
    assert calls == []


def test_pty_retains_bounded_output_while_draining_child():
    result = runner.run_argv_pty(
        [sys.executable, "-c", "import os; [os.write(1,b'x'*4096) for _ in range(512)]"],
        timeout=10, max_bytes=123,
    )
    assert result["code"] == 0
    assert result["stdout"] == "x" * 123
    assert result["output_truncated"] is True
    assert result["started"] is True and result["process_reaped"] is True


def test_capture_is_bounded_before_output_serialization():
    capture = runner._BoundedPTYOutput(13)
    for _ in range(1000):
        capture.append(b"x" * 1024)
        assert len(capture.data) <= 13
    assert capture.truncated is True


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"timeout": -1}, {"timeout": True},
    {"timeout": float("nan")}, {"timeout": float("inf")}, {"max_bytes": -1},
    {"max_bytes": True}])
def test_pty_invalid_limits_refuse_before_openpty(monkeypatch, kwargs):
    def forbidden():
        raise AssertionError("invalid limits must not open a PTY")
    monkeypatch.setattr(runner.pty, "openpty", forbidden)
    with pytest.raises(ValueError):
        runner.run_argv_pty([sys.executable, "-c", "pass"], **kwargs)


def test_pty_spawn_failure_has_no_handoff_effect(tmp_path):
    result = runner.run_argv_pty([str(tmp_path / "missing-executable")])
    assert result["started"] is False
    assert result["code"] is None
    assert result["timed_out"] is False
    assert result["process_reaped"] is True


def test_pty_timeout_reaps_owned_child():
    code = "import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(30)"
    result = runner.run_argv_pty([sys.executable, "-c", code], timeout=1, max_bytes=1024)
    assert result["timed_out"] is True and result["started"] is True
    assert result["process_reaped"] is True
    pid = int(result["stdout"].strip())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_pty_post_exit_drain_obeys_deadline(monkeypatch):
    start = time.monotonic()
    class Finished:
        pid = 99999999
        def poll(self): return 0
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: Finished())
    monkeypatch.setattr(runner.os, "killpg", lambda *a: None)
    monkeypatch.setattr(runner.os, "read", lambda *a: b"x" * 4096)
    # The old unbounded post-exit drain returns only after this artificial stream stops.
    monkeypatch.setattr(runner.select, "select", lambda r, w, e, timeout:
                        (r if time.monotonic() - start < 0.2 else [], [], []))
    result = runner.run_argv_pty([sys.executable, "-c", "pass"], timeout=0.03, max_bytes=16)
    assert result["timed_out"] is True
    assert result["output_truncated"] is True
    assert len(result["stdout"].encode()) <= 16


def test_actual_browser_helpers_preserve_visible_uncertainty():
    """Execute the real JS helpers in Node; not copied Python predicates."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node unavailable")
    src = (Path(__file__).resolve().parents[1] / "app/static/chairman_control/control_room.js").read_text()
    functions = []
    for name in ("openBinding", "openBindingButton"):
        start = src.index("  function " + name + "(")
        end = src.index("\n  function ", start + 5)
        functions.append(src[start:end])
    harness = r'''
import assert from 'node:assert/strict';
let response, posts=0, refreshes=0;
const safeText = (value, fallback) => typeof value === 'string' ? value : fallback;
const postJSON = () => {posts++; return response instanceof Error ? Promise.reject(response) : Promise.resolve(response);};
const loadState = () => {refreshes++;};
const OPEN_LABEL = {};
const bindingConfidence = () => ({openable:true});
const document = {createElement: () => ({parentNode:null, setAttribute(){}})};
const parent = {appendChild(node){node.parentNode=this; this.status=node;}};
const button = (label, cls, handler) => ({label, className:cls, handler, parentNode:parent, nextSibling:null});
''' + '\n'.join(functions) + r'''
const b={binding_id:'opaque-binding',role:'chairman'};
const trigger = openBindingButton(b,'Desktop','desktop');
response={ok:false,failure_kind:'effect_unknown',detail:'Inspect the bound session before retrying'};
await trigger.handler({stopPropagation(){}});
assert.ok(parent.status, 'normal button must show its outcome instead of discarding it');
assert.match(parent.status.textContent,/uncertain|unknown/i);
assert.doesNotMatch(parent.status.textContent,/did not open/i);
assert.equal(refreshes,0,'failed refresh must not erase the outcome');
assert.equal(posts,1,'never automatically replay');
response=new Error('response lost');
await trigger.handler({stopPropagation(){}});
assert.match(parent.status.textContent,/unknown|uncertain/i);
assert.equal(posts,2);
response={ok:true,action:'opened_desktop',verified:true};
await trigger.handler({stopPropagation(){}});
assert.match(parent.status.textContent,/accepted/i);
assert.equal(refreshes,1);
assert.equal(posts,3);
assert.equal(trigger.disabled,false);
'''
    completed = subprocess.run([node, "--input-type=module", "-e", harness], capture_output=True,
                               text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
