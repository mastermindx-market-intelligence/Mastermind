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
from integrations.workbench_action_mcp.command_contracts import RECIPE_SHA256
from integrations.workbench_action_mcp.tunnel import (
    TunnelConfigurationError,
    create_runtime_channel,
    create_tunnel_action_server,
    parse_tunnel_config,
)
from integrations.workbench_stdio_boundary import MAX_WIRE_BYTES
from integrations.workbench_read_mcp.runtime import RuntimeCloseIncomplete
from tests.test_mcp_stdio_boundary import child, initialize
from tests.workbench_action_mcp.test_tunnel import (
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
ALL_TOOLS = {
    "workspace_manifest",
    "read_project_file",
    "preview_text_replace",
    "prepare_text_patch",
    "commit_text_patch",
    "reconcile_text_patch",
    *COMMAND_TOOLS,
}


def _file_sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _command_document(tmp_path):
    document, project, audit, key = _document(tmp_path)
    python = os.path.realpath(sys.executable)
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
    tmp_path, recipe_id, exit_code
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
    tmp_path, monkeypatch: pytest.MonkeyPatch
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
