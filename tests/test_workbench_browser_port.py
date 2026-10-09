from __future__ import annotations

import os
from pathlib import Path

import pytest

from control_plane.codex_worker import ProcessIdentity
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


def _fixture(tmp_path: Path, relay):
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
    codec = BrowserRefCodec(b"k" * 32)
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
        tool_schema_digest="d" * 64,
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


def test_owner_can_observe_exact_live_resource_without_dispatch(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        raise AssertionError("resource observation must not invoke the browser relay")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        observed = port.observe_resource(caller, browser_ref)
        assert observed.start_action_id == "c" * 32
        assert observed.relay_pid == 4321
        assert observed.relay_start_identity == "1700000000.000001"
        assert observed.tool_schema_digest == "d" * 64
        assert calls == []
        assert list((tmp_path / "artifacts").iterdir()) == []
    finally:
        os.close(fd)


def test_owner_tab_observation_hardcodes_list_and_creates_no_action_claim(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append((request, timeout))
        return {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"],
            "resource_id": "c" * 32,
            "ok": True,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "### Result\n- 0: (current) [Example](https://example.test/path)",
                    }
                ],
                "isError": False,
            },
        }

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        result = port.observe_tab_group(caller, browser_ref)
        assert result["isError"] is False
        assert len(calls) == 1
        request, timeout = calls[0]
        assert request["kind"] == "tool"
        assert request["tool"] == "browser_tabs"
        assert request["arguments"] == {"action": "list"}
        assert timeout == 2
        assert list((tmp_path / "artifacts").iterdir()) == []
    finally:
        os.close(fd)


def test_owner_tab_observation_refuses_relay_errors_without_retry(tmp_path: Path):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        raise BrowserRelayError("synthetic transport loss")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        with pytest.raises(BrowserPortRefused, match="BROWSER_TAB_OBSERVATION_UNAVAILABLE"):
            port.observe_tab_group(caller, browser_ref)
        assert len(calls) == 1
        assert list((tmp_path / "artifacts").iterdir()) == []
    finally:
        os.close(fd)
