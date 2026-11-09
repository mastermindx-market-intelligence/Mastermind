from __future__ import annotations

import os
from pathlib import Path

import pytest

from control_plane.codex_worker import ProcessIdentity
from control_plane.browser_resource_contract import APP_CONTROL_TOOL_SCHEMA_DIGEST, ALLOWED_BROWSER_TOOLS, APP_CONTROL_TOOLS
from integrations.workbench_action_mcp.action_artifacts import (
    ActionHostBinding,
    adopt_artifact_store,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ActionScope,
    ProjectActionBinding,
)
from integrations.workbench_browser_mcp.contracts import (
    BrowserRefCodec,
    BrowserResourceRef,
)
from integrations.workbench_browser_mcp.browser_port import (
    BrowserActionPort,
    BrowserPortRefused,
)
from integrations.workbench_browser_mcp.relay import BrowserRelayError


class Inspector:
    def inspect(self, pid: int) -> ProcessIdentity:
        assert pid == 4321
        return ProcessIdentity(
            start_identity="1700000000.000001",
            pgid=4321,
            session_id=4321,
            effective_uid=os.geteuid(),
            effective_gid=os.getegid(),
            real_uid=os.getuid(),
            real_gid=os.getgid(),
        )


def _open_store(root: Path):
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.set_inheritable(fd, False)
    return fd, adopt_artifact_store(fd)


def _fixture(tmp_path: Path, relay, *, app_control: bool = False):
    fd, store = _open_store(tmp_path / "artifacts")
    relay_root = tmp_path / "relay"
    relay_root.mkdir(mode=0o700)
    os.chmod(relay_root, 0o700)
    caller = ActionCaller(
        subject_digest="a" * 64,
        client_ref="client:browser",
        resource="https://workbench.example/browser",
        scopes=("workbench.browser",),
        expires_at=10,
    )
    scope = ActionScope(
        root_fd=99,
        root_device=1,
        root_inode=2,
        context_ref="context:browser",
        responsibility_ref="responsibility:browser",
        operation_ref="operation:browser",
        owner_ref="owner:browser",
        generation="generation:browser",
        allowed_paths=(),
        expires_at_ms=9000,
    )
    binding = ProjectActionBinding(caller=caller, project_ref="project:browser", scope=scope)
    host = ActionHostBinding(host_id="b" * 64, boot_session_id="boot:browser")
    codec = BrowserRefCodec(b"k" * 32, allowed_tools=ALLOWED_BROWSER_TOOLS | APP_CONTROL_TOOLS if app_control else ALLOWED_BROWSER_TOOLS)
    resource = BrowserResourceRef(
        schema="mastermind.workbench_browser_ref.v1",
        start_action_id="c" * 32,
        subject_digest=caller.subject_digest,
        client_ref=caller.client_ref,
        resource=caller.resource,
        project_ref=binding.project_ref,
        context_ref=scope.context_ref,
        responsibility_ref=scope.responsibility_ref,
        operation_ref=scope.operation_ref,
        owner_ref=scope.owner_ref,
        generation=scope.generation,
        host_id=host.host_id,
        boot_session_id=host.boot_session_id,
        relay_pid=4321,
        relay_start_identity="1700000000.000001",
        relay_pgid=4321,
        relay_session_id=4321,
        mode="isolated",
        profile_ref=None,
        tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST if app_control else "d" * 64,
        issued_at_ms=1000,
        expires_at_ms=8000,
    )
    browser_ref = codec.encode_resource(resource)

    port = BrowserActionPort(
        resolve_binding=lambda actual, project: binding
        if actual == caller and project == binding.project_ref
        else None,
        clock_ms=lambda: 2000,
        codec=codec,
        artifact_store=store,
        host_binding=host,
        inspector=Inspector(),
        relay_root=relay_root,
        relay_requester=relay,
        action_ttl_ms=3000,
        relay_timeout_seconds=2,
    )
    return fd, caller, port, browser_ref


def test_read_only_tool_calls_relay_without_creating_action_artifact(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append((request, timeout))
        return {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"],
            "resource_id": "c" * 32,
            "ok": True,
            "result": {"content": [{"type": "text", "text": "snapshot"}], "isError": False},
        }

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        result = port.call_read_tool(caller, browser_ref, "browser_snapshot", {})
        assert result["isError"] is False
        assert len(calls) == 1
        assert list((tmp_path / "artifacts").iterdir()) == []
    finally:
        os.close(fd)


@pytest.mark.parametrize("status,effect", [("DISPATCHED", "APPLIED"), ("NO_CHANGE", "NOT_APPLIED"), ("REFUSED", "NOT_APPLIED"), ("EFFECT_UNKNOWN", "EFFECT_UNKNOWN"), ("unexpected", "EFFECT_UNKNOWN")])
def test_app_profile_classifies_only_dispatch_and_reconciles_without_replay(tmp_path, status, effect):
    calls = []
    def relay(_path, request, *, timeout):
        calls.append(request)
        value = {"schema": "mastermind.os.app-control.v1", "status": status, "code": "SOURCE_PROOF"}
        return {"schema": "mastermind.workbench_browser_relay_response.v1", "request_id": request["request_id"],
                "resource_id": "c" * 32, "ok": True,
                "result": {"content": [{"type": "text", "text": "source proof"}], "structuredContent": value,
                           "isError": status in {"REFUSED", "EFFECT_UNKNOWN"}}}
    fd, caller, port, browser_ref = _fixture(tmp_path, relay, app_control=True)
    try:
        action_ref = port.prepare_action(caller, browser_ref, "mastermind_os_navigate", {"observation": "original", "route": "Projects"})
        first = port.run_action(caller, browser_ref, action_ref)
        assert first["effect_state"] == effect
        assert first["result"]["structuredContent"]["status"] == status
        assert port.reconcile_action(caller, browser_ref, action_ref)["effect_state"] == effect
        assert port.run_action(caller, browser_ref, action_ref)["effect_state"] == effect
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_app_profile_lost_response_retains_original_unknown_effect(tmp_path):
    calls = []
    def relay(_path, request, *, timeout):
        calls.append(request)
        raise BrowserRelayError("source proof: response lost after UI dispatch")
    fd, caller, port, browser_ref = _fixture(tmp_path, relay, app_control=True)
    try:
        action_ref = port.prepare_action(caller, browser_ref, "mastermind_os_act", {"observation": "original", "target": "control-1", "action": "activate"})
        assert port.run_action(caller, browser_ref, action_ref)["effect_state"] == "EFFECT_UNKNOWN"
        assert port.reconcile_action(caller, browser_ref, action_ref)["effect_state"] == "EFFECT_UNKNOWN"
        assert port.run_action(caller, browser_ref, action_ref)["effect_state"] == "EFFECT_UNKNOWN"
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_baseline_port_cannot_prepare_or_read_app_tools(tmp_path):
    def relay(*_args, **_kwargs):
        raise AssertionError("ungranted app tool reached relay")
    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        with pytest.raises(BrowserPortRefused):
            port.call_read_tool(caller, browser_ref, "mastermind_os_inspect", {})
        with pytest.raises(BrowserPortRefused):
            port.prepare_action(caller, browser_ref, "mastermind_os_act", {})
        assert list((tmp_path / "artifacts").iterdir()) == []
    finally:
        os.close(fd)


@pytest.mark.parametrize("lost_response", [False, True])
def test_disabling_profile_preserves_original_receipt_recovery_without_new_dispatch(tmp_path, lost_response):
    calls = []
    def relay(_path, request, *, timeout):
        calls.append(request)
        if lost_response:
            raise BrowserRelayError("source proof: response lost after dispatch")
        return {"schema": "mastermind.workbench_browser_relay_response.v1", "request_id": request["request_id"],
                "resource_id": "c" * 32, "ok": True,
                "result": {"content": [], "isError": False,
                           "structuredContent": {"schema": "mastermind.os.app-control.v1", "status": "DISPATCHED", "code": "UI_EVENT_DISPATCHED"}}}
    fd, caller, port, browser_ref = _fixture(tmp_path, relay, app_control=True)
    try:
        args = {"observation": "original", "route": "Projects"}
        original = port.prepare_action(caller, browser_ref, "mastermind_os_navigate", args)
        unrun = port.prepare_action(caller, browser_ref, "mastermind_os_navigate", args)
        effect = "EFFECT_UNKNOWN" if lost_response else "APPLIED"
        assert port.run_action(caller, browser_ref, original)["effect_state"] == effect
        # Same original key/store/owner, but future app actions are disabled.
        port._codec = BrowserRefCodec(b"k" * 32)
        assert port.reconcile_action(caller, browser_ref, original)["effect_state"] == effect
        assert port.run_action(caller, browser_ref, original)["effect_state"] == effect
        assert port.reconcile_action(caller, browser_ref, unrun)["effect_state"] == "NOT_APPLIED"
        with pytest.raises(BrowserPortRefused, match="BROWSER_ACTION_INVALID"):
            port.run_action(caller, browser_ref, unrun)
        with pytest.raises(BrowserPortRefused):
            port.prepare_action(caller, browser_ref, "mastermind_os_navigate", args)
        assert len(calls) == 1
    finally:
        os.close(fd)


@pytest.mark.skipif(not os.environ.get("MM_APP_CONTROL_CHROMIUM"), reason="Explicit isolated source-proof Chromium required")
def test_actual_app_prepare_run_check_and_lost_response_over_original_stdio_child(tmp_path):
    """Real rendered App and child; synthetic identity/process binding only.

    This deliberately proves the stdio/action adapter, not installed OAuth,
    the separately tested Unix-socket owner, provider work, or live acceptance.
    """
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import shutil
    import threading
    from integrations.workbench_browser_mcp.relay import McpStdioSession, playwright_child_argv
    from control_plane.browser_resource_contract import browser_tools_for_digest
    root = Path(__file__).resolve().parents[1]
    fixture_root = root / "app/mastermind_os/dist-browser-proof"
    assert (fixture_root / "agent-control-proof.html").is_file(), "Build isolated source fixture first"
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(fixture_root), **kwargs)
        def do_GET(self):
            if not self.path.startswith("/os/"):
                self.send_error(404); return
            self.path = self.path[3:]
            super().do_GET()
        def log_message(self, *_args):
            pass
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    origin = f"http://127.0.0.1:{http.server_port}"
    argv = playwright_child_argv(node_executable=shutil.which("node"),
        mcp_cli_path=str(root / "integrations/worker_browser_runtime/node_modules/@playwright/mcp/cli.js"),
        chrome_executable=os.environ["MM_APP_CONTROL_CHROMIUM"], output_dir=str(tmp_path), mode="isolated", profile_dir=None, app_control_origin=origin)
    session = McpStdioSession(argv=argv, env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        allowed_tools=browser_tools_for_digest(APP_CONTROL_TOOL_SCHEMA_DIGEST), expected_tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST)
    calls, results, lose = [], [], {"next": False}
    def relay(_path, request, *, timeout):
        calls.append(request)
        result = session.call(request["tool"], request["arguments"])
        results.append(result)
        if lose["next"]:
            lose["next"] = False
            raise BrowserRelayError("injected response loss after actual app dispatch")
        return {"schema": "mastermind.workbench_browser_relay_response.v1", "request_id": request["request_id"],
                "resource_id": "c" * 32, "ok": True, "result": result}
    fd = None
    try:
        session.start()
        fd, caller, port, browser_ref = _fixture(tmp_path, relay, app_control=True)
        def run(name, arguments):
            ref = port.prepare_action(caller, browser_ref, name, arguments)
            return ref, port.run_action(caller, browser_ref, ref)
        def read(name="mastermind_os_inspect", arguments=None):
            return port.call_read_tool(caller, browser_ref, name, arguments or {})["structuredContent"]
        _, opened = run("browser_navigate", {"url": origin + "/os/agent-control-proof.html"})
        assert opened["effect_state"] == "APPLIED", results[-1]
        observed = read(); assert observed["access"] == "AVAILABLE"
        _, moved = run("mastermind_os_navigate", {"observation": observed["observation"], "route": "Search"})
        assert moved["effect_state"] == "APPLIED"
        assert read("mastermind_os_check", {"route": "Search"})["status"] == "PASS"
        observed = read(); field = next(row for row in observed["controls"] if row["name"] == "Search available sources")
        _, edited = run("mastermind_os_act", {"observation": observed["observation"], "target": field["ref"], "action": "fill", "value": "Alpha"})
        assert edited["effect_state"] == "APPLIED"
        assert next(row for row in read()["controls"] if row["name"] == "Search available sources")["value"] == "Alpha"
        observed = read(); disabled = next(row for row in observed["controls"] if row["name"] == "New conversation")
        assert disabled["enabled"] is False
        _, refused = run("mastermind_os_act", {"observation": observed["observation"], "target": disabled["ref"], "action": "activate"})
        assert refused["effect_state"] == "NOT_APPLIED"
        assert refused["result"]["structuredContent"]["code"] == "TARGET_DISABLED"
        observed = read(); lose["next"] = True
        original, unknown = run("mastermind_os_navigate", {"observation": observed["observation"], "route": "Today"})
        assert unknown["effect_state"] == "EFFECT_UNKNOWN"
        dispatched = len(calls)
        assert port.run_action(caller, browser_ref, original)["effect_state"] == "EFFECT_UNKNOWN"
        assert port.reconcile_action(caller, browser_ref, original)["effect_state"] == "EFFECT_UNKNOWN"
        assert len(calls) == dispatched
        assert read("mastermind_os_check", {"route": "Today"})["status"] == "PASS"
        assert port.reconcile_action(caller, browser_ref, original)["effect_state"] == "EFFECT_UNKNOWN"
    finally:
        if fd is not None: os.close(fd)
        session.close(); http.shutdown(); http.server_close(); thread.join(timeout=2)


def test_mutating_action_replay_returns_receipt_without_second_click(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        return {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"],
            "resource_id": "c" * 32,
            "ok": True,
            "result": {"content": [{"type": "text", "text": "clicked"}], "isError": False},
        }

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(
            caller, browser_ref, "browser_click", {"target": "button"}
        )
        first = port.run_action(caller, browser_ref, action_ref)
        second = port.run_action(caller, browser_ref, action_ref)
        assert first["effect_state"] == "APPLIED"
        assert first["result"]["isError"] is False
        assert second["effect_state"] == "APPLIED"
        assert second["reconciled"] is True
        assert "result" not in second
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_lost_relay_response_becomes_effect_unknown_and_never_replays(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        raise BrowserRelayError("connection lost after dispatch")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(
            caller, browser_ref, "browser_click", {"target": "submit"}
        )
        first = port.run_action(caller, browser_ref, action_ref)
        second = port.run_action(caller, browser_ref, action_ref)
        assert first["effect_state"] == "EFFECT_UNKNOWN"
        assert second["effect_state"] == "EFFECT_UNKNOWN"
        assert second["reconciled"] is True
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_explicit_relay_refusal_is_not_applied_and_is_replay_safe(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        return {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"],
            "resource_id": "c" * 32,
            "ok": False,
            "error": "REQUEST_REFUSED",
        }

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(
            caller, browser_ref, "browser_click", {"target": "button"}
        )
        first = port.run_action(caller, browser_ref, action_ref)
        second = port.run_action(caller, browser_ref, action_ref)
        assert first["effect_state"] == "NOT_APPLIED"
        assert second["effect_state"] == "NOT_APPLIED"
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_read_only_and_mutating_tool_surfaces_do_not_cross(tmp_path: Path):
    def relay(_path, request, *, timeout):
        raise AssertionError("should not dispatch")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        with pytest.raises(BrowserPortRefused, match="READ_ONLY"):
            port.prepare_action(caller, browser_ref, "browser_snapshot", {})
        with pytest.raises(BrowserPortRefused, match="MUTATING"):
            port.call_read_tool(caller, browser_ref, "browser_click", {"target": "button"})
    finally:
        os.close(fd)


def test_wrong_process_identity_refuses_before_relay(tmp_path: Path):
    def relay(_path, request, *, timeout):
        raise AssertionError("should not dispatch")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        bad = BrowserResourceRef(
            **{
                **port.codec.decode_resource(browser_ref, now_ms=2000).__dict__,
                "relay_start_identity": "different",
            }
        )
        bad_ref = port.codec.encode_resource(bad)
        with pytest.raises(BrowserPortRefused, match="PROCESS_IDENTITY_CHANGED"):
            port.call_read_tool(caller, bad_ref, "browser_snapshot", {})
    finally:
        os.close(fd)


@pytest.mark.parametrize("effect", ["APPLIED", "NOT_APPLIED", "EFFECT_UNKNOWN"])
def test_durable_action_receipt_survives_relay_death_and_action_expiry(
    tmp_path: Path, effect: str
):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        if effect == "EFFECT_UNKNOWN":
            raise BrowserRelayError("response lost after dispatch")
        if effect == "NOT_APPLIED":
            return {
                "schema": "mastermind.workbench_browser_relay_response.v1",
                "request_id": request["request_id"],
                "resource_id": "c" * 32,
                "ok": False,
                "error": "REQUEST_REFUSED",
            }
        return {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"],
            "resource_id": "c" * 32,
            "ok": True,
            "result": {"content": [], "isError": False},
        }

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        assert port.run_action(caller, browser_ref, action_ref)["effect_state"] == effect

        class DeadInspector:
            def inspect(self, pid):
                raise ProcessLookupError(pid)

        port._inspector = DeadInspector()
        port._clock_ms = lambda: 8500  # action and resource references have expired
        assert port.reconcile_action(caller, browser_ref, action_ref)["effect_state"] == effect
        replay = port.run_action(caller, browser_ref, action_ref)
        assert replay["effect_state"] == effect
        assert replay["reconciled"] is True
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_expired_unclaimed_action_does_not_dispatch(tmp_path: Path):
    def relay(_path, request, *, timeout):
        raise AssertionError("expired action must not dispatch")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        port._clock_ms = lambda: 6000  # action expires at 5000, resource at 8000
        with pytest.raises(BrowserPortRefused, match="BROWSER_ACTION_INVALID"):
            port.run_action(caller, browser_ref, action_ref)
        assert port.reconcile_action(caller, browser_ref, action_ref)["effect_state"] == "NOT_APPLIED"
        assert list((tmp_path / "artifacts").iterdir()) == []
    finally:
        os.close(fd)


def test_unknown_effect_allows_only_bound_read_after_resource_expiry(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request["tool"])
        if request["tool"] == "browser_click":
            raise BrowserRelayError("click reply lost")
        assert request["tool"] == "browser_snapshot"
        return {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"],
            "resource_id": "c" * 32,
            "ok": True,
            "result": {"content": [{"type": "text", "text": "same carrier"}], "isError": False},
        }

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        assert port.run_action(caller, browser_ref, action_ref)["effect_state"] == "EFFECT_UNKNOWN"
        port._clock_ms = lambda: 8500  # resource expires at 8000; caller at 10000
        snapshot = port.call_read_tool(caller, browser_ref, "browser_snapshot", {})
        assert snapshot["content"][0]["text"] == "same carrier"
        with pytest.raises(BrowserPortRefused, match="BROWSER_REF_INVALID"):
            port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        with pytest.raises(BrowserPortRefused, match="MUTATING_TOOL_REQUIRES_ACTION_REF"):
            port.call_read_tool(caller, browser_ref, "browser_click", {"target": "button"})

        original_resolver = port._resolve_binding
        port._resolve_binding = lambda *_: None
        with pytest.raises(BrowserPortRefused, match="BROWSER_BINDING_CHANGED"):
            port.call_read_tool(caller, browser_ref, "browser_snapshot", {})
        port._resolve_binding = original_resolver

        class ChangedInspector:
            def inspect(self, pid):
                observed = Inspector().inspect(pid)
                return type(observed)(**{**observed.__dict__, "start_identity": "changed"})

        port._inspector = ChangedInspector()
        with pytest.raises(BrowserPortRefused, match="PROCESS_IDENTITY_CHANGED"):
            port.call_read_tool(caller, browser_ref, "browser_snapshot", {})
        port._inspector = Inspector()
        port._clock_ms = lambda: 10000
        with pytest.raises(BrowserPortRefused, match="BROWSER_BINDING_CHANGED"):
            port.call_read_tool(caller, browser_ref, "browser_snapshot", {})
        assert calls == ["browser_click", "browser_snapshot"]
    finally:
        os.close(fd)
