from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

import mcp.types as mcp_types
import pytest

import integrations.workbench_action_mcp.action_artifacts as action_artifacts
import integrations.workbench_action_mcp.runtime as runtime_module
import integrations.workbench_action_mcp.tunnel as tunnel_module
import integrations.workbench_read_mcp.observer as read_observer
from integrations.workbench_action_mcp.command_contracts import RECIPE_SHA256
from integrations.workbench_action_mcp.tunnel import (
    TunnelConfigurationError,
    create_runtime_channel,
    create_tunnel_action_server,
    parse_tunnel_config,
)
from integrations.workbench_stdio_boundary import MAX_WIRE_BYTES
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeCloseUncertain,
)
from tests.test_mcp_stdio_boundary import child, initialize
from tests.workbench_action_mcp.test_tunnel import (
    _audit_lines,
    _call,
    _document,
    _error_code,
    _tools,
)


RECIPE_ROOT = str(
    Path(__file__).resolve().parents[2]
    / "integrations"
    / "workbench_action_mcp"
    / "recipes"
)
COMMAND_TOOLS = {
    "prepare_project_command",
    "run_project_command",
    "read_action_result",
    "reconcile_action",
}
_PRIVATE_PYTHON = ""
ALL_TOOLS = {
    "workspace_manifest",
    "read_project_file",
    "preview_text_replace",
    "prepare_text_patch",
    "commit_text_patch",
    "reconcile_text_patch",
    *COMMAND_TOOLS,
}
_NATIVE_PROCESS_INSPECTOR = runtime_module.ProcessInspector


def _file_sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _StableBootProcessInspector:
    """Test boot observer that preserves real native process inspection."""

    def __init__(self, boot_session_id: str) -> None:
        self._boot_session_id = boot_session_id
        self._native = _NATIVE_PROCESS_INSPECTOR()

    def boot_session_id(self) -> str:
        return self._boot_session_id

    def inspect(self, pid: int):
        return self._native.inspect(pid)


def _install_boot_observer(
    monkeypatch: pytest.MonkeyPatch, boot_session_id: str
) -> None:
    def observer() -> _StableBootProcessInspector:
        return _StableBootProcessInspector(boot_session_id)

    monkeypatch.setattr(runtime_module, "ProcessInspector", observer)
    monkeypatch.setattr(tunnel_module, "ProcessInspector", observer)


@pytest.fixture
def stable_process_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_boot_observer(monkeypatch, "test-stable-boot-session")


@pytest.fixture(scope="module", autouse=True)
def _bind_private_python(private_python_executable: str):
    global _PRIVATE_PYTHON
    _PRIVATE_PYTHON = private_python_executable
    yield
    _PRIVATE_PYTHON = ""


def _command_document(tmp_path):
    document, project, audit, key = _document(tmp_path)
    assert _PRIVATE_PYTHON
    python = _PRIVATE_PYTHON
    document.update(
        {
            "python_executable": python,
            "python_sha256": _file_sha256(python),
            "recipe_root": RECIPE_ROOT,
            "process_deadline_seconds": 5.0,
        }
    )
    return document, project, audit, key


def test_ten_tool_inventory_annotations_and_closed_schemas(tmp_path) -> None:
    document, project, _, _ = _command_document(tmp_path)
    (project / "sample.py").write_text("value = 1\n", encoding="utf-8")

    async def exercise() -> None:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            tools = await _tools(create_tunnel_action_server(runtime))
            assert {tool.name for tool in tools} == ALL_TOOLS
            assert "preview_project_command" not in {tool.name for tool in tools}
            for tool in tools:
                assert tool.inputSchema.get("additionalProperties") is False
                assert tool.outputSchema.get("additionalProperties") is False
            by_name = {tool.name: tool for tool in tools}
            assert by_name["run_project_command"].annotations.readOnlyHint is False
            for name in COMMAND_TOOLS - {"run_project_command"}:
                assert by_name[name].annotations.readOnlyHint is True
        finally:
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_patch_read_and_command_share_one_runtime_store_and_token_codec(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    (project / "sample.py").write_text("value = 1\n", encoding="utf-8")
    captured = {}
    real_read = tunnel_module.create_bound_read_composition
    real_patch = tunnel_module.create_text_patch_port
    real_command = tunnel_module.create_command_port

    def read(runtime):
        captured["read_runtime"] = runtime
        return real_read(runtime)

    def patch(**kwargs):
        captured["patch"] = kwargs
        return real_patch(**kwargs)

    def command(**kwargs):
        captured["command"] = kwargs
        return real_command(**kwargs)

    monkeypatch.setattr(tunnel_module, "create_bound_read_composition", read)
    monkeypatch.setattr(tunnel_module, "create_text_patch_port", patch)
    monkeypatch.setattr(tunnel_module, "create_command_port", command)

    async def exercise() -> None:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            create_tunnel_action_server(runtime)
            assert captured["read_runtime"] is runtime
            assert captured["patch"]["artifact_store"] is runtime.artifact_store
            assert captured["command"]["artifact_store"] is runtime.artifact_store
            assert captured["patch"]["token_codec"] is captured["command"]["token_codec"]
            assert captured["patch"]["run_io"].__self__ is runtime
            assert captured["command"]["run_io"].__self__ is runtime
        finally:
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "field",
    [
        "python_executable",
        "python_sha256",
        "recipe_root",
        "process_deadline_seconds",
    ],
)
def test_command_host_configuration_is_required_and_closed(tmp_path, field) -> None:
    document, _, _, _ = _command_document(tmp_path)
    document.pop(field)
    with pytest.raises(TunnelConfigurationError):
        parse_tunnel_config(document)


def test_command_inputs_reject_model_selected_host_knobs_and_audit_refusals(
    tmp_path,
) -> None:
    document, project, audit, _ = _command_document(tmp_path)
    target = project / "sample.py"
    content = b"value = 1\n"
    target.write_bytes(content)
    requests = {
        "prepare_project_command": {
            "project_ref": document["lease"]["project_ref"],
            "relative_path": "sample.py",
            "recipe_id": "canary_checksum",
            "expected_sha256": hashlib.sha256(content).hexdigest(),
            "environment": {"PATH": "/tmp"},
        },
        "run_project_command": {"action_ref": "opaque", "executable": "/bin/sh"},
        "read_action_result": {
            "action_ref": "opaque",
            "stream": "stdout",
            "result_path": "/tmp/result",
        },
        "reconcile_action": {"action_ref": "opaque", "host_id": "b" * 64},
    }

    async def exercise() -> list[str]:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            server = create_tunnel_action_server(runtime)
            return [
                _error_code(await _call(server, name, arguments))
                for name, arguments in requests.items()
            ]
        finally:
            await runtime.aclose(timeout=5.0)

    assert asyncio.run(exercise()) == ["INVALID_REQUEST"] * 4
    rows = _audit_lines(audit)
    assert [(row["tool"], row["code"], row["accepted"]) for row in rows] == [
        (name, "request_refused", False) for name in requests
    ]


def test_command_process_deadline_cannot_exceed_command_contract(tmp_path) -> None:
    document, _, _, _ = _command_document(tmp_path)
    document["process_deadline_seconds"] = 15.001
    with pytest.raises(TunnelConfigurationError):
        parse_tunnel_config(document)


def test_manifest_reports_final_tools_recipes_and_limits_without_durable_prepare(
    tmp_path,
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    (project / "sample.py").write_text("value = 1\n", encoding="utf-8")

    async def exercise():
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            return await _call(
                create_tunnel_action_server(runtime), "workspace_manifest", {}
            )
        finally:
            await runtime.aclose(timeout=5.0)

    result = asyncio.run(exercise())
    assert result.isError is False
    data = result.structuredContent["data"]
    assert set(data["supported_tools"]) == ALL_TOOLS
    assert data["recipes"] == [
        {"recipe_id": name, "sha256": RECIPE_SHA256[name]}
        for name in ("canary_checksum", "canary_refuse")
    ]
    assert data["effects"] == {
        "file_write": True,
        "process_start": True,
        "network_call": False,
        "durable_prepare": False,
    }
    assert data["limits"]["process_deadline_seconds"] == 5.0
    assert data["limits"]["command_result_page_lines"] == 128
    assert data["limits"]["command_result_page_bytes"] == 8192


@pytest.mark.parametrize(
    ("recipe_id", "exit_code"),
    [("canary_checksum", 0), ("canary_refuse", 7)],
)
def test_command_routes_preserve_actual_exit_and_read_40_lines(
    tmp_path, recipe_id, exit_code, stable_process_boot
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    target = project / "sample.py"
    content = b"value = 1\n"
    target.write_bytes(content)

    async def exercise():
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            server = create_tunnel_action_server(runtime)
            prepared = await _call(
                server,
                "prepare_project_command",
                {
                    "project_ref": document["lease"]["project_ref"],
                    "relative_path": "sample.py",
                    "recipe_id": recipe_id,
                    "expected_sha256": hashlib.sha256(content).hexdigest(),
                },
            )
            assert prepared.isError is False
            action_ref = prepared.structuredContent["action_ref"]
            applied = await _call(
                server, "run_project_command", {"action_ref": action_ref}
            )
            page = await _call(
                server,
                "read_action_result",
                {
                    "action_ref": action_ref,
                    "stream": "stdout",
                    "start_line": 0,
                    "max_lines": 40,
                    "max_content_bytes": 8192,
                },
            )
            reconciled = await _call(
                server, "reconcile_action", {"action_ref": action_ref}
            )
            return applied, page, reconciled
        finally:
            await runtime.aclose(timeout=5.0)

    applied, page, reconciled = asyncio.run(exercise())
    assert applied.isError is False
    assert applied.structuredContent["exit_code"] == exit_code
    assert applied.structuredContent["isError"] is False
    assert reconciled.isError is False
    assert reconciled.structuredContent["exit_code"] == exit_code
    assert page.isError is False
    assert page.structuredContent["line_end"] == 40
    assert page.structuredContent["next_line"] is None
    assert len(page.structuredContent["content"].splitlines()) == 40
    assert target.read_bytes() == content


def test_cancelled_command_process_evidence_fsync_keeps_runtime_owned_until_drain(
    tmp_path, monkeypatch: pytest.MonkeyPatch, stable_process_boot
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    document["close_timeout_seconds"] = 0.05
    target = project / "sample.py"
    content = b"value = 1\n"
    target.write_bytes(content)
    entered = threading.Event()
    release = threading.Event()
    real_os = action_artifacts.os
    store_fd = -1

    class HeldProcessEvidenceFsync:
        def __getattr__(self, name):
            return getattr(real_os, name)

        def fsync(self, fd):
            opened = real_os.fstat(fd)
            for name in real_os.listdir(store_fd):
                if not name.endswith(".process"):
                    continue
                named = real_os.stat(name, dir_fd=store_fd, follow_symlinks=False)
                if (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino):
                    entered.set()
                    if not release.wait(timeout=8):
                        raise OSError("test process evidence fsync was not released")
                    break
            return real_os.fsync(fd)

    async def exercise() -> None:
        nonlocal store_fd
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        store_fd = runtime.artifact_store.dir_fd
        monkeypatch.setattr(action_artifacts, "os", HeldProcessEvidenceFsync())
        task = None
        try:
            server = create_tunnel_action_server(runtime)
            prepared = await _call(
                server,
                "prepare_project_command",
                {
                    "project_ref": document["lease"]["project_ref"],
                    "relative_path": "sample.py",
                    "recipe_id": "canary_checksum",
                    "expected_sha256": hashlib.sha256(content).hexdigest(),
                },
            )
            assert prepared.isError is False
            task = asyncio.create_task(
                _call(
                    server,
                    "run_project_command",
                    {"action_ref": prepared.structuredContent["action_ref"]},
                )
            )
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            cancelled = await task
            assert cancelled.isError is False
            assert cancelled.structuredContent["effect_state"] == "EFFECT_UNKNOWN"
            with pytest.raises(RuntimeCloseIncomplete):
                await runtime.aclose(timeout=0.05)
            assert real_os.fstat(store_fd).st_ino == runtime.artifact_store.inode
            release.set()
            await runtime.aclose(timeout=5.0)
            with pytest.raises(OSError):
                real_os.fstat(store_fd)
        finally:
            release.set()
            if task is not None and not task.done():
                task.cancel()
            try:
                await runtime.aclose(timeout=5.0)
            except BaseException:
                pass

    asyncio.run(exercise())


def test_read_observer_close_uncertainty_marks_shared_store_and_runtime_close(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    target = project / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")
    target_identity = target.stat()
    real_os = read_observer.os
    failed = False

    class UncertainReadClose:
        def __getattr__(self, name):
            return getattr(real_os, name)

        def close(self, fd):
            nonlocal failed
            opened = real_os.fstat(fd)
            real_os.close(fd)
            if not failed and (opened.st_dev, opened.st_ino) == (
                target_identity.st_dev,
                target_identity.st_ino,
            ):
                failed = True
                raise OSError("synthetic read observer close uncertainty")

    async def exercise() -> None:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        monkeypatch.setattr(read_observer, "os", UncertainReadClose())
        server = create_tunnel_action_server(runtime)
        first = await _call(
            server, "read_project_file", {"relative_path": "sample.py"}
        )
        assert _error_code(first) == "PROJECT_CLEANUP_UNCERTAIN"
        assert runtime.artifact_store.cleanup_reasons == ("read_observer_close",)
        refused = await _call(server, "workspace_manifest", {})
        assert _error_code(refused) == "PROJECT_CLEANUP_UNCERTAIN"
        with pytest.raises(RuntimeCloseUncertain):
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_valid_large_escaped_preview_fits_exact_mcp_wire_envelope(tmp_path) -> None:
    document, project, _, _ = _command_document(tmp_path)
    old_text = "UNIQUE!!"
    new_text = '"' * 16384
    content = "\\" * 6064 + old_text + "\\" * 6064
    (project / "sample.py").write_text(content, encoding="utf-8")
    config_path = tmp_path / "tunnel.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    os.chmod(config_path, 0o600)
    launcher = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mastermind_workbench_action_stdio.py"
    )

    with child([sys.executable, str(launcher), "--config", str(config_path)]) as process:
        initialize(process)
        request_id = "\U0010ffff" * 256
        process.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": "preview_text_replace",
                    "arguments": {
                        "relative_path": "sample.py",
                        "expected_sha256": hashlib.sha256(content.encode()).hexdigest(),
                        "old_text": old_text,
                        "new_text": new_text,
                    },
                },
            }
        )
        response = process.receive()
        assert response["id"] == request_id
        assert response["result"]["isError"] is False
        assert len(response["result"]["content"][0]["text"].encode()) == 81_965
        assert len(json.dumps(response, ensure_ascii=False).encode()) < MAX_WIRE_BYTES
        process.assert_exit(0)


def test_control_character_request_id_gets_closed_preview_limit_error(tmp_path) -> None:
    document, project, _, _ = _command_document(tmp_path)
    old_text = "UNIQUE!!"
    new_text = '"' * 16384
    content = "\\" * 6704 + old_text + "\\" * 6704
    (project / "sample.py").write_text(content, encoding="utf-8")
    config_path = tmp_path / "tunnel.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    os.chmod(config_path, 0o600)
    launcher = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mastermind_workbench_action_stdio.py"
    )

    with child([sys.executable, str(launcher), "--config", str(config_path)]) as process:
        initialize(process)
        request_id = "\x01" * 256
        process.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": "preview_text_replace",
                    "arguments": {
                        "relative_path": "sample.py",
                        "expected_sha256": hashlib.sha256(content.encode()).hexdigest(),
                        "old_text": old_text,
                        "new_text": new_text,
                    },
                },
            }
        )
        response = process.receive()
        assert response["id"] == request_id
        assert "error" not in response
        assert response["result"]["isError"] is True
        assert json.loads(response["result"]["content"][0]["text"]) == {
            "code": "PREVIEW_TOO_LARGE"
        }
        process.assert_exit(0)
        assert b"WORKBENCH_MCP_OUTPUT_LIMIT" not in process.stderr()


def test_oversized_escaped_preview_returns_closed_preview_error(tmp_path) -> None:
    document, project, _, _ = _command_document(tmp_path)
    old_text = "UNIQUE"
    new_text = '"' * 16384
    content = "\\" * 8000 + old_text + "\\" * 8000
    (project / "sample.py").write_text(content, encoding="utf-8")

    async def exercise():
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            return await _call(
                create_tunnel_action_server(runtime),
                "preview_text_replace",
                {
                    "relative_path": "sample.py",
                    "expected_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "old_text": old_text,
                    "new_text": new_text,
                },
            )
        finally:
            await runtime.aclose(timeout=5.0)

    assert _error_code(asyncio.run(exercise())) == "PREVIEW_TOO_LARGE"


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason=(
        "native positive command recovery requires Darwin's kernel boot-session "
        "identity; non-Darwin adapter identities are deliberately refused"
    ),
)
def test_native_stdio_all_ten_routes_and_restart_command_reconciliation(
    tmp_path,
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    document["lease"]["allowed_paths"] = ["sample.py", "created.txt"]
    original = b"value = 1\n"
    replaced = b"value = 2\n"
    (project / "sample.py").write_bytes(original)
    config_path = tmp_path / "tunnel.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    os.chmod(config_path, 0o600)
    launcher = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mastermind_workbench_action_stdio.py"
    )
    request_id = 10
    invoked: set[str] = set()

    def call(process, name, arguments):
        nonlocal request_id
        request_id += 1
        invoked.add(name)
        process.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        response = process.receive()
        assert response["id"] == request_id
        assert response["result"]["isError"] is False
        return response["result"]["structuredContent"]

    command_refs = {}
    with child([sys.executable, str(launcher), "--config", str(config_path)]) as process:
        initialize(process)
        manifest = call(process, "workspace_manifest", {})
        assert set(manifest["data"]["supported_tools"]) == ALL_TOOLS
        assert call(
            process, "read_project_file", {"relative_path": "sample.py"}
        )["data"]["content"] == original.decode()
        preview = call(
            process,
            "preview_text_replace",
            {
                "relative_path": "sample.py",
                "expected_sha256": hashlib.sha256(original).hexdigest(),
                "old_text": "value = 1",
                "new_text": "value = 2",
            },
        )
        assert preview["data"]["applied"] is False

        prepared_replace = call(
            process,
            "prepare_text_patch",
            {
                "project_ref": document["lease"]["project_ref"],
                "relative_path": "sample.py",
                "mode": "REPLACE",
                "expected_sha256": hashlib.sha256(original).hexdigest(),
                "old_text": "value = 1",
                "new_text": "value = 2",
            },
        )
        replaced_result = call(
            process,
            "commit_text_patch",
            {"action_ref": prepared_replace["action_ref"]},
        )
        assert replaced_result["effect_state"] == "APPLIED"
        assert call(
            process,
            "reconcile_text_patch",
            {"action_ref": prepared_replace["action_ref"]},
        )["effect_state"] == "APPLIED"
        assert call(
            process, "read_project_file", {"relative_path": "sample.py"}
        )["data"]["content"] == replaced.decode()

        prepared_create = call(
            process,
            "prepare_text_patch",
            {
                "project_ref": document["lease"]["project_ref"],
                "relative_path": "created.txt",
                "mode": "CREATE",
                "new_text": "created\n",
            },
        )
        assert call(
            process,
            "commit_text_patch",
            {"action_ref": prepared_create["action_ref"]},
        )["effect_state"] == "APPLIED"
        assert call(
            process, "read_project_file", {"relative_path": "created.txt"}
        )["data"]["content"] == "created\n"

        for recipe_id, exit_code in (
            ("canary_checksum", 0),
            ("canary_refuse", 7),
        ):
            prepared = call(
                process,
                "prepare_project_command",
                {
                    "project_ref": document["lease"]["project_ref"],
                    "relative_path": "sample.py",
                    "recipe_id": recipe_id,
                    "expected_sha256": hashlib.sha256(replaced).hexdigest(),
                },
            )
            command_refs[recipe_id] = prepared["action_ref"]
            applied = call(
                process,
                "run_project_command",
                {"action_ref": prepared["action_ref"]},
            )
            assert applied["exit_code"] == exit_code
        process.assert_exit(0)

    artifact = Path(document["artifact_directory"])
    before_reconcile = {
        path.name: (path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_size)
        for path in artifact.iterdir()
    }
    with child([sys.executable, str(launcher), "--config", str(config_path)]) as process:
        initialize(process)
        for recipe_id, exit_code in (
            ("canary_checksum", 0),
            ("canary_refuse", 7),
        ):
            action_ref = command_refs[recipe_id]
            page = call(
                process,
                "read_action_result",
                {
                    "action_ref": action_ref,
                    "stream": "stdout",
                    "start_line": 0,
                    "max_lines": 40,
                    "max_content_bytes": 8192,
                },
            )
            assert page["exit_code"] == exit_code
            assert page["line_end"] == 40
            assert page["next_line"] is None
            assert len(page["content"].splitlines()) == 40
            reconciled = call(
                process, "reconcile_action", {"action_ref": action_ref}
            )
            assert reconciled["effect_state"] == "APPLIED"
            assert reconciled["exit_code"] == exit_code
        process.assert_exit(0)

    after_reconcile = {
        path.name: (path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_size)
        for path in artifact.iterdir()
    }
    assert after_reconcile == before_reconcile
    assert invoked == ALL_TOOLS
    assert (project / "sample.py").read_bytes() == replaced
    assert (project / "created.txt").read_bytes() == b"created\n"


def test_explicit_adapter_boot_refuses_command_prepare_without_artifact_or_effect(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    target = project / "sample.py"
    content = b"value = 1\n"
    target.write_bytes(content)
    artifact = Path(document["artifact_directory"])
    before = tuple(artifact.iterdir())
    monkeypatch.setattr(runtime_module.platform, "system", lambda: "Linux")
    _install_boot_observer(monkeypatch, "adapter-explicit-test")

    async def exercise():
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            return await _call(
                create_tunnel_action_server(runtime),
                "prepare_project_command",
                {
                    "project_ref": document["lease"]["project_ref"],
                    "relative_path": "sample.py",
                    "recipe_id": "canary_checksum",
                    "expected_sha256": hashlib.sha256(content).hexdigest(),
                },
            )
        finally:
            await runtime.aclose(timeout=5.0)

    refused = asyncio.run(exercise())
    assert _error_code(refused) == "ACTION_UNAVAILABLE"
    assert tuple(artifact.iterdir()) == before
    assert target.read_bytes() == content


@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="non-Darwin native child proves the real adapter boot refusal",
)
def test_native_stdio_adapter_boot_refuses_command_without_claim_spawn_or_effect(
    tmp_path,
) -> None:
    document, project, _, _ = _command_document(tmp_path)
    target = project / "sample.py"
    content = b"value = 1\n"
    target.write_bytes(content)
    artifact = Path(document["artifact_directory"])
    before = tuple(artifact.iterdir())
    config_path = tmp_path / "tunnel.json"
    config_path.write_text(json.dumps(document), encoding="utf-8")
    os.chmod(config_path, 0o600)
    launcher = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mastermind_workbench_action_stdio.py"
    )

    with child([sys.executable, str(launcher), "--config", str(config_path)]) as process:
        initialize(process)
        process.send(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "prepare_project_command",
                    "arguments": {
                        "project_ref": document["lease"]["project_ref"],
                        "relative_path": "sample.py",
                        "recipe_id": "canary_checksum",
                        "expected_sha256": hashlib.sha256(content).hexdigest(),
                    },
                },
            }
        )
        response = process.receive()
        assert response["id"] == 20
        result = response["result"]
        assert result["isError"] is True
        assert json.loads(result["content"][0]["text"]) == {
            "code": "ACTION_UNAVAILABLE"
        }
        process.assert_exit(0)

    assert tuple(artifact.iterdir()) == before
    assert target.read_bytes() == content


def test_launcher_describe_reports_exact_ten_tool_source_profile(tmp_path) -> None:
    launcher = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mastermind_workbench_action_stdio.py"
    )
    import subprocess

    completed = subprocess.run(
        [sys.executable, "-S", str(launcher), "--describe"],
        cwd="/",
        env={"PATH": os.environ.get("PATH", "")},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 0
    assert set(json.loads(completed.stdout)["tools"]) == ALL_TOOLS
