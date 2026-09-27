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


@pytest.mark.parametrize("prior_effect", ["APPLIED", "NOT_APPLIED", "EFFECT_UNKNOWN"])
@pytest.mark.parametrize("retirement", ["action_expired", "browser_expired", "process_gone"])
def test_reconcile_recovers_existing_receipt_after_execution_capability_retires(
    tmp_path: Path, prior_effect: str, retirement: str
):
    """Receipt authority outlives execution authority, never the current caller."""
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        if prior_effect == "EFFECT_UNKNOWN":
            raise BrowserRelayError("lost reply after possible dispatch")
        if prior_effect == "NOT_APPLIED":
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
        action_ref = port.prepare_action(
            caller, browser_ref, "browser_click", {"target": "button"}
        )
        first = port.run_action(caller, browser_ref, action_ref)
        assert first["effect_state"] == prior_effect
        if retirement == "action_expired":
            port._clock_ms = lambda: 6000
        elif retirement == "browser_expired":
            port._clock_ms = lambda: 8500
        else:
            from control_plane.codex_worker import ProcessIdentityError

            class GoneInspector:
                def inspect(self, _pid):
                    raise ProcessIdentityError("owned browser process retired")

            port._inspector = GoneInspector()

        recovered = port.reconcile_action(caller, browser_ref, action_ref)
        assert recovered["effect_state"] == prior_effect
        assert recovered["reconciled"] is True
        assert "result" not in recovered
        assert len(calls) == 1
        # Historical evidence access must never re-enable the retired action.
        with pytest.raises(BrowserPortRefused):
            port.run_action(caller, browser_ref, action_ref)
        assert len(calls) == 1
    finally:
        os.close(fd)


@pytest.mark.parametrize("tamper", ["browser", "action", "caller", "owner"])
def test_historical_reconciliation_keeps_exact_authority_binding(tmp_path: Path, tamper: str):
    import dataclasses

    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        raise BrowserRelayError("lost reply after possible dispatch")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        assert port.run_action(caller, browser_ref, action_ref)["effect_state"] == "EFFECT_UNKNOWN"
        port._clock_ms = lambda: 6000
        if tamper == "browser":
            browser_ref = "x" + browser_ref[1:]
        elif tamper == "action":
            action_ref = "x" + action_ref[1:]
        elif tamper == "caller":
            caller = dataclasses.replace(caller, subject_digest="f" * 64)
        else:
            original_resolver = port._resolve_binding

            def moved_resolver(actual, project):
                binding = original_resolver(actual, project)
                return dataclasses.replace(binding, scope=dataclasses.replace(
                    binding.scope, generation="generation:replacement"))

            port._resolve_binding = moved_resolver
        with pytest.raises(BrowserPortRefused):
            port.reconcile_action(caller, browser_ref, action_ref)
        assert len(calls) == 1
    finally:
        os.close(fd)


@pytest.mark.parametrize("expired", ["caller", "scope", "clock-regression"])
def test_historical_reconciliation_rechecks_read_authority_after_owner_lookup(
    tmp_path: Path, expired: str
):
    import dataclasses

    def relay(_path, request, *, timeout):
        raise AssertionError("read-only reconciliation must not dispatch")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        action_ref = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        original_resolver = port._resolve_binding
        now = [2000]
        port._clock_ms = lambda: now[0]

        def delayed_resolver(actual, project):
            binding = original_resolver(actual, project)
            if expired == "caller":
                now[0] = 10000
                return dataclasses.replace(binding, scope=dataclasses.replace(
                    binding.scope, expires_at_ms=20000))
            now[0] = 9000 if expired == "scope" else 1999
            return binding

        port._resolve_binding = delayed_resolver
        with pytest.raises(BrowserPortRefused, match="AUTH_EXPIRED|CLOCK_UNAVAILABLE"):
            port.reconcile_action(caller, browser_ref, action_ref)
        assert list((tmp_path / "artifacts").iterdir()) == []
    finally:
        os.close(fd)


@pytest.mark.parametrize("preprepare", [True, False])
@pytest.mark.parametrize("reply", ["lost", "tool_error"])
@pytest.mark.parametrize("reopen", [True, False])
def test_prior_unknown_blocks_fresh_action_without_replacing_original(
    tmp_path: Path, preprepare: bool, reply: str, reopen: bool
):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        if reply == "lost":
            raise BrowserRelayError("synthetic lost reply")
        return {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"], "resource_id": "c" * 32,
            "ok": True, "result": {"content": [], "isError": True},
        }

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    reopened_fd = None
    try:
        first = port.prepare_action(caller, browser_ref, "browser_click", {"target": "submit"})
        second = port.prepare_action(caller, browser_ref, "browser_click", {"target": "submit"}) if preprepare else None
        assert port.run_action(caller, browser_ref, first)["effect_state"] == "EFFECT_UNKNOWN"
        if reopen:
            reopened_fd = os.open(tmp_path / "artifacts", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            port = BrowserActionPort(
                resolve_binding=port._resolve_binding, clock_ms=port._clock_ms,
                codec=port.codec, artifact_store=adopt_artifact_store(reopened_fd),
                host_binding=port._host_binding, inspector=Inspector(),
                relay_root=tmp_path / "relay", relay_requester=relay,
                action_ttl_ms=3000, relay_timeout_seconds=2,
            )
        if second is None:
            second = port.prepare_action(caller, browser_ref, "browser_click", {"target": "submit"})
        before = sorted(p.name for p in (tmp_path / "artifacts").iterdir())
        with pytest.raises(BrowserPortRefused, match="PRIOR_EFFECT_UNRESOLVED"):
            port.run_action(caller, browser_ref, second)
        assert len(calls) == 1
        assert sorted(p.name for p in (tmp_path / "artifacts").iterdir()) == before
        assert port.reconcile_action(caller, browser_ref, first)["effect_state"] == "EFFECT_UNKNOWN"
        assert port.run_action(caller, browser_ref, first)["effect_state"] == "EFFECT_UNKNOWN"
        assert len(calls) == 1
    finally:
        if reopened_fd is not None:
            os.close(reopened_fd)
        os.close(fd)


@pytest.mark.parametrize("prior_effect", ["APPLIED", "NOT_APPLIED"])
def test_terminal_prior_action_allows_new_action(tmp_path: Path, prior_effect: str):
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        response = {
            "schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"], "resource_id": "c" * 32,
            "ok": prior_effect == "APPLIED",
        }
        if prior_effect == "APPLIED":
            response["result"] = {"content": [], "isError": False}
        else:
            response["error"] = "REQUEST_REFUSED"
        return response

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        for _ in range(2):
            action = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
            assert port.run_action(caller, browser_ref, action)["effect_state"] == prior_effect
        assert len(calls) == 2
    finally:
        os.close(fd)


def test_new_resource_reference_cannot_escape_same_store_uncertainty(tmp_path: Path):
    import dataclasses
    calls = []

    def relay(_path, request, *, timeout):
        calls.append(request)
        raise BrowserRelayError("synthetic lost reply")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        first = port.prepare_action(caller, browser_ref, "browser_click", {"target": "submit"})
        assert port.run_action(caller, browser_ref, first)["effect_state"] == "EFFECT_UNKNOWN"
        new_resource = dataclasses.replace(
            port.codec.decode_resource(browser_ref, now_ms=2000), start_action_id="e" * 32)
        new_ref = port.codec.encode_resource(new_resource)
        second = port.prepare_action(caller, new_ref, "browser_click", {"target": "submit"})
        with pytest.raises(BrowserPortRefused, match="PRIOR_EFFECT_UNRESOLVED"):
            port.run_action(caller, new_ref, second)
        assert len(calls) == 1
    finally:
        os.close(fd)


@pytest.mark.parametrize("kind", ["claim", "result", "stdout", "unrecognized"])
def test_orphan_evidence_blocks_new_browser_action(tmp_path: Path, kind: str):
    def relay(*_args, **_kwargs):
        raise AssertionError("orphan evidence must refuse before dispatch")

    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        orphan = tmp_path / "artifacts" / ("e" * 32 + "." + kind)
        orphan.write_bytes(b"{}")
        before = {p.name: p.read_bytes() for p in (tmp_path / "artifacts").iterdir()}
        action = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        with pytest.raises(BrowserPortRefused, match="PRIOR_EFFECT_UNRESOLVED"):
            port.run_action(caller, browser_ref, action)
        assert {p.name: p.read_bytes() for p in (tmp_path / "artifacts").iterdir()} == before
    finally:
        os.close(fd)
