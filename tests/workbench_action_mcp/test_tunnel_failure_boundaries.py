from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sys

import pytest

import integrations.workbench_action_mcp.runtime as action_runtime
import integrations.workbench_action_mcp.tunnel as tunnel_module
from integrations.business_mcp_auth.audit import AuditAcquisitionUncertain
from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
from integrations.workbench_action_mcp.tunnel import (
    SERVER_NAME,
    TunnelConfigurationError,
    create_runtime_channel,
    create_tunnel_action_server,
    load_tunnel_config,
    parse_tunnel_config,
    run_configured_stdio,
    run_stdio,
)
from integrations.workbench_read_mcp.runtime import RuntimeCloseUncertain

from tests.workbench_action_mcp.test_tunnel import (
    KEY_A,
    KEY_B,
    OTHER_CHANNEL,
    _call,
    _document,
    _error_code,
)


def test_unknown_tool_name_never_reaches_sdk_warning_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)
    sentinel = "SECRET_PATCH_CONTENT\n" + ("W" * 16384)

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        try:
            server = create_tunnel_action_server(runtime)
            caplog.set_level(logging.DEBUG, logger="mcp.server.lowlevel.server")
            result = await _call(server, sentinel, {"argv": ["/bin/sh"]})
            assert _error_code(result) == "TOOL_NOT_AVAILABLE"
            assert result.isError is True
            assert result.content[0].text == '{"code":"TOOL_NOT_AVAILABLE"}'
        finally:
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())
    assert sentinel not in caplog.text
    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err
    for record in caplog.records:
        rendered = record.getMessage()
        assert sentinel not in rendered
        assert "SECRET_PATCH_CONTENT" not in rendered
        if record.args:
            assert sentinel not in str(record.args)


def test_direct_acquisition_uncertainty_before_assignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)

    def boom(_cls, **_kwargs):
        raise RuntimeCloseUncertain(
            "synthetic acquisition uncertainty",
            primary_error=OSError("root rollback"),
            cleanup_errors=(OSError("audit close"),),
        )

    monkeypatch.setattr(WorkbenchActionRuntime, "open_channel", classmethod(boom))

    async def attempt() -> None:
        await create_runtime_channel(config)

    with pytest.raises(TunnelConfigurationError) as caught:
        asyncio.run(attempt())
    assert caught.value.code == "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"


def test_audit_acquisition_uncertainty_translated_before_assignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)

    def refuse_audit_open(_cls, *_args, **_kwargs):
        raise AuditAcquisitionUncertain(
            "synthetic audit acquisition cleanup uncertainty",
            primary_error=OSError("audit fd"),
            cleanup_errors=(OSError("audit close"),),
        )

    monkeypatch.setattr(
        action_runtime.DurableAuthAuditSink,
        "open",
        classmethod(refuse_audit_open),
    )

    async def attempt() -> None:
        await create_runtime_channel(config)

    with pytest.raises(TunnelConfigurationError) as caught:
        asyncio.run(attempt())
    assert caught.value.code == "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"


def test_acquisition_uncertainty_with_host_fd_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)
    host_fds: list[int] = []
    leaked: list[int] = []
    real_open = tunnel_module._open_safe_directory
    real_close = os.close

    def tracking_open(path: str) -> int:
        descriptor = real_open(path)
        host_fds.append(descriptor)
        return descriptor

    def failing_close(fd: int) -> None:
        if fd in host_fds:
            leaked.append(fd)
            raise OSError("host fd close failed")
        return real_close(fd)

    def boom(_cls, **_kwargs):
        raise RuntimeCloseUncertain(
            "synthetic acquisition uncertainty",
            primary_error=OSError("root rollback"),
            cleanup_errors=(OSError("audit close"),),
        )

    monkeypatch.setattr(tunnel_module, "_open_safe_directory", tracking_open)
    monkeypatch.setattr(os, "close", failing_close)
    monkeypatch.setattr(WorkbenchActionRuntime, "open_channel", classmethod(boom))
    try:
        async def attempt() -> None:
            await create_runtime_channel(config)

        with pytest.raises(TunnelConfigurationError) as caught:
            asyncio.run(attempt())
        assert caught.value.code == "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"
    finally:
        for fd in leaked:
            try:
                real_close(fd)
            except OSError:
                pass


def test_host_fd_close_uncertainty_after_assignment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)
    host_fds: list[int] = []
    leaked: list[int] = []
    closed: list[WorkbenchActionRuntime] = []
    real_open = tunnel_module._open_safe_directory
    real_close = os.close
    real_aclose = WorkbenchActionRuntime.aclose

    def tracking_open(path: str) -> int:
        descriptor = real_open(path)
        host_fds.append(descriptor)
        return descriptor

    def failing_close(fd: int) -> None:
        if fd in host_fds:
            leaked.append(fd)
            raise OSError("host fd close failed")
        return real_close(fd)

    async def tracking_aclose(self, *, timeout: float):
        closed.append(self)
        return await real_aclose(self, timeout=timeout)

    monkeypatch.setattr(tunnel_module, "_open_safe_directory", tracking_open)
    monkeypatch.setattr(os, "close", failing_close)
    monkeypatch.setattr(WorkbenchActionRuntime, "aclose", tracking_aclose)
    try:
        async def attempt() -> None:
            await create_runtime_channel(config)

        with pytest.raises(TunnelConfigurationError) as caught:
            asyncio.run(attempt())
        assert caught.value.code == "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"
        assert closed
    finally:
        for fd in leaked:
            try:
                real_close(fd)
            except OSError:
                pass


def test_startup_cleanup_uncertain_maps_to_exit_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_path: str):
        raise TunnelConfigurationError("TUNNEL_STARTUP_CLEANUP_UNCERTAIN")

    monkeypatch.setattr(tunnel_module, "load_tunnel_config", boom)
    assert run_configured_stdio("/unused") == 5


def test_server_construction_failure_revokes_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        revoked: list[bool] = []
        closed: list[float] = []
        original_revoke = runtime.revoke
        original_aclose = runtime.aclose

        def track_revoke() -> None:
            revoked.append(True)
            original_revoke()

        async def track_aclose(*, timeout: float):
            closed.append(timeout)
            await original_aclose(timeout=timeout)

        runtime.revoke = track_revoke
        runtime.aclose = track_aclose
        monkeypatch.setattr(
            tunnel_module,
            "create_tunnel_action_server",
            lambda _runtime: (_ for _ in ()).throw(
                ValueError("server construction refused")
            ),
        )
        with pytest.raises(ValueError, match="server construction refused"):
            await run_stdio(runtime, close_timeout_seconds=1.0)
        assert revoked == [True]
        assert closed == [1.0]

    asyncio.run(exercise())


def test_initialization_options_failure_revokes_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)

    def boom(self, **_kwargs):
        raise RuntimeError("initialization options refused")

    monkeypatch.setattr(tunnel_module.Server, "create_initialization_options", boom)

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        revoked: list[bool] = []
        closed: list[bool] = []
        original_revoke = runtime.revoke
        original_aclose = runtime.aclose

        def track_revoke() -> None:
            revoked.append(True)
            original_revoke()

        async def track_aclose(*, timeout: float):
            closed.append(True)
            await original_aclose(timeout=timeout)

        runtime.revoke = track_revoke
        runtime.aclose = track_aclose
        with pytest.raises(RuntimeError, match="initialization options refused"):
            await run_stdio(runtime, close_timeout_seconds=1.0)
        assert revoked == [True]
        assert closed == [True]

    asyncio.run(exercise())


def test_uncertain_close_is_not_masked_by_server_construction_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        revoked: list[bool] = []

        def track_revoke() -> None:
            revoked.append(True)

        async def uncertain(*, timeout: float):
            raise RuntimeCloseUncertain("descriptor close is uncertain")

        runtime.revoke = track_revoke
        runtime.aclose = uncertain
        monkeypatch.setattr(
            tunnel_module,
            "create_tunnel_action_server",
            lambda _runtime: (_ for _ in ()).throw(
                ValueError("server construction refused")
            ),
        )
        with pytest.raises(RuntimeCloseUncertain) as caught:
            await run_stdio(runtime, close_timeout_seconds=1.0)
        assert revoked == [True]
        assert isinstance(caught.value.__cause__, ValueError)
        runtime.revoke = WorkbenchActionRuntime.revoke.__get__(runtime)
        await WorkbenchActionRuntime.aclose(runtime, timeout=5.0)

    asyncio.run(exercise())


def test_stdio_initialize_list_shutdown_roundtrip(tmp_path: Path) -> None:
    from tests.test_mcp_stdio_boundary import child, initialize

    assert importlib.metadata.version("mcp") == "1.28.1"
    document, _, _, _ = _document(tmp_path)
    config_path = tmp_path / "tunnel.json"
    config_path.write_text(json.dumps(document))
    os.chmod(config_path, 0o600)
    script = Path(__file__).resolve().parents[2] / "scripts" / "mastermind_workbench_action_stdio.py"
    with child([sys.executable, str(script), "--config", str(config_path)]) as process:
        initialize(process)
        process.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = process.receive()["result"]["tools"]
        assert {tool["name"] for tool in tools} == {
            "workspace_manifest", "read_project_file", "preview_text_replace",
            "prepare_text_patch", "commit_text_patch", "reconcile_text_patch",
            "prepare_project_command", "run_project_command",
            "read_action_result", "read_action_artifact", "reconcile_action",
        }
        process.assert_exit(0)
        assert not process.fallback_used


def test_same_inode_key_rewrite_during_load_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    key_file = Path(str(document["action_key_file"]))
    swapped = {"done": False}
    real_read = os.read

    def swap_after_read(fd: int, n: int) -> bytes:
        data = real_read(fd, n)
        if not swapped["done"] and data:
            key_file.write_text(KEY_B + "\n")
            os.chmod(key_file, 0o600)
            swapped["done"] = True
        return data

    monkeypatch.setattr(os, "read", swap_after_read)
    with pytest.raises(TunnelConfigurationError) as caught:
        tunnel_module._secure_action_key(str(key_file))
    assert caught.value.code == "TUNNEL_CONFIGURATION_REFUSED"
    text = f"{caught.value!s} {caught.value!r}"
    assert KEY_A not in text
    assert KEY_B not in text


def test_same_inode_config_rewrite_during_load_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    config_file = tmp_path / "tunnel.json"
    config_file.write_text(json.dumps(document))
    os.chmod(config_file, 0o600)
    other = dict(document)
    other["workspace_id"] = OTHER_CHANNEL.workspace_id
    swapped = {"done": False}
    real_read = os.read

    def swap_after_read(fd: int, n: int) -> bytes:
        data = real_read(fd, n)
        if not swapped["done"] and data:
            config_file.write_text(json.dumps(other))
            os.chmod(config_file, 0o600)
            swapped["done"] = True
        return data

    monkeypatch.setattr(os, "read", swap_after_read)
    with pytest.raises(TunnelConfigurationError) as caught:
        load_tunnel_config(str(config_file))
    assert caught.value.code == "TUNNEL_CONFIGURATION_REFUSED"


def test_key_close_uncertainty_wins_over_primary_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, _, _, _ = _document(tmp_path)
    key_file = Path(str(document["action_key_file"]))
    owned = {"fd": -1}
    real_open = os.open
    real_close = os.close
    real_read = os.read

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if Path(path) == key_file:
            owned["fd"] = fd
        return fd

    def failing_read(fd: int, n: int) -> bytes:
        if fd == owned["fd"]:
            raise OSError("short read")
        return real_read(fd, n)

    def failing_close(fd: int) -> None:
        if fd == owned["fd"]:
            raise OSError("key fd close failed")
        return real_close(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "read", failing_read)
    monkeypatch.setattr(os, "close", failing_close)
    try:
        with pytest.raises(TunnelConfigurationError) as caught:
            tunnel_module._secure_action_key(str(key_file))
        assert caught.value.code == "TUNNEL_STARTUP_CLEANUP_UNCERTAIN"
        text = f"{caught.value!s} {caught.value!r}"
        assert KEY_A not in text
        assert KEY_B not in text
    finally:
        if owned["fd"] >= 0:
            try:
                real_close(owned["fd"])
            except OSError:
                pass
