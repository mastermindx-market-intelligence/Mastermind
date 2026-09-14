from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

from integrations.workbench_action_mcp import tunnel as tunnel_module
from integrations.workbench_action_mcp.tunnel import (
    create_runtime_channel,
    create_tunnel_action_server,
    parse_tunnel_config,
)
from tests.workbench_action_mcp.test_tunnel import (
    _audit_lines,
    _call,
    _document,
    _error_code,
    _tools,
)
from tests.test_mcp_stdio_boundary import child, initialize


READ_TOOLS = {
    "workspace_manifest",
    "read_project_file",
    "preview_text_replace",
}
PATCH_TOOLS = {
    "prepare_text_patch",
    "commit_text_patch",
    "reconcile_text_patch",
}
COMMAND_TOOLS = {
    "prepare_project_command",
    "run_project_command",
    "read_action_result",
    "reconcile_action",
}


def test_unified_server_lists_read_patch_and_command_tools_with_closed_schemas(tmp_path) -> None:
    document, project, _, _ = _document(tmp_path)
    (project / "sample.py").write_text("value = 1\n", encoding="utf-8")

    async def exercise() -> None:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            tools = await _tools(create_tunnel_action_server(runtime))
            assert {tool.name for tool in tools} == READ_TOOLS | PATCH_TOOLS | COMMAND_TOOLS
            assert "preview_project_command" not in {tool.name for tool in tools}
            for tool in tools:
                assert tool.inputSchema.get("additionalProperties") is False
                assert tool.outputSchema.get("additionalProperties") is False
                if tool.name in READ_TOOLS:
                    assert tool.annotations.readOnlyHint is True
                    assert tool.annotations.destructiveHint is False
        finally:
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_manifest_validates_live_scope_and_describes_unified_profile(tmp_path) -> None:
    document, project, audit, _ = _document(tmp_path)
    (project / "sample.py").write_text("value = 1\n", encoding="utf-8")

    async def exercise() -> dict:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            result = await _call(create_tunnel_action_server(runtime), "workspace_manifest", {})
            assert result.isError is False
            return result.structuredContent
        finally:
            await runtime.aclose(timeout=5.0)

    manifest = asyncio.run(exercise())
    assert manifest["tool"] == "workspace_manifest"
    assert manifest["ok"] is True
    assert manifest["profile"] == "attended_workbench_f0"
    assert manifest["mutation_allowed"] is True
    assert manifest["data"]["capability_state"] == "BUILT_NOT_PROVEN"
    assert manifest["data"]["supported_tools"] == [
        "workspace_manifest",
        "read_project_file",
        "preview_text_replace",
        "prepare_text_patch",
        "commit_text_patch",
        "reconcile_text_patch",
        "prepare_project_command",
        "run_project_command",
        "read_action_result",
        "reconcile_action",
    ]
    assert manifest["data"]["effects"] == {
        "file_write": True,
        "process_start": True,
        "network_call": False,
        "durable_prepare": False,
    }
    assert manifest["data"]["profile"] == "attended_workbench_f0"
    assert [recipe["recipe_id"] for recipe in manifest["data"]["recipes"]] == [
        "canary_checksum",
        "canary_refuse",
    ]
    assert [row["tool"] for row in _audit_lines(audit)] == ["workspace_manifest"]


def test_read_and_preview_use_same_runtime_without_mutating(tmp_path) -> None:
    document, project, audit, _ = _document(tmp_path)
    target = project / "sample.py"
    original = "".join(f"line {number}\n" for number in range(45)).encode()
    target.write_bytes(original)
    before = hashlib.sha256(original).hexdigest()

    async def exercise():
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        calls = 0
        original_run_io = runtime.run_io

        async def counted_run_io(operation):
            nonlocal calls
            calls += 1
            return await original_run_io(operation)

        runtime.run_io = counted_run_io
        try:
            server = create_tunnel_action_server(runtime)
            read = await _call(
                server,
                "read_project_file",
                {"relative_path": "sample.py", "line_start": 0, "line_count": 40},
            )
            preview = await _call(
                server,
                "preview_text_replace",
                {
                    "relative_path": "sample.py",
                    "expected_sha256": before,
                    "old_text": "line 0",
                    "new_text": "changed",
                },
            )
            return read, preview, calls
        finally:
            await runtime.aclose(timeout=5.0)

    read, preview, calls = asyncio.run(exercise())
    assert calls == 2
    assert read.isError is False
    assert read.structuredContent["data"]["line_start"] == 0
    assert read.structuredContent["data"]["line_end"] == 40
    assert read.structuredContent["data"]["next_line"] == 40
    assert preview.isError is False
    assert preview.structuredContent["data"]["status"] == "PREVIEW_ONLY"
    assert preview.structuredContent["data"]["applied"] is False
    assert target.read_bytes() == original
    assert [row["tool"] for row in _audit_lines(audit)] == [
        "read_project_file",
        "preview_text_replace",
    ]


def test_read_refusal_is_error_and_audited_without_echo(tmp_path) -> None:
    document, project, audit, _ = _document(tmp_path)
    (project / "sample.py").write_text("value = 1\n", encoding="utf-8")
    private = "private-" + "x" * 2048

    async def exercise() -> tuple[str, str]:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            server = create_tunnel_action_server(runtime)
            invalid = await _call(
                server,
                "read_project_file",
                {"relative_path": "sample.py", "root": private},
            )
            runtime.revoke()
            revoked = await _call(
                server,
                "read_project_file",
                {"relative_path": "sample.py"},
            )
            assert private not in "".join(item.text for item in invalid.content)
            return _error_code(invalid), _error_code(revoked)
        finally:
            await runtime.aclose(timeout=5.0)

    invalid, revoked = asyncio.run(exercise())
    assert invalid == "INVALID_REQUEST"
    assert revoked == "CHANNEL_ADMISSION_REFUSED"
    rows = _audit_lines(audit)
    assert [(row["tool"], row["code"], row["accepted"]) for row in rows] == [
        ("read_project_file", "request_refused", False),
        ("read_project_file", "channel_refused", False),
    ]


def test_expired_read_is_refused_and_audited(tmp_path, monkeypatch) -> None:
    document, project, audit, _ = _document(tmp_path)
    (project / "sample.py").write_text("value = 1\n", encoding="utf-8")
    expires_at_ms = document["lease"]["lease_expires_at_ms"]

    async def exercise() -> str:
        runtime = await create_runtime_channel(parse_tunnel_config(document))
        try:
            server = create_tunnel_action_server(runtime)
            monkeypatch.setattr(
                tunnel_module.time, "time", lambda: expires_at_ms / 1000
            )
            result = await _call(
                server, "read_project_file", {"relative_path": "sample.py"}
            )
            return _error_code(result)
        finally:
            await runtime.aclose(timeout=5.0)

    assert asyncio.run(exercise()) == "CHANNEL_ADMISSION_REFUSED"
    rows = _audit_lines(audit)
    assert [(row["tool"], row["code"], row["accepted"]) for row in rows] == [
        ("read_project_file", "channel_refused", False)
    ]


def test_native_stdio_dispatches_all_three_read_routes_and_exits_cleanly(
    tmp_path,
) -> None:
    document, project, _, _ = _document(tmp_path)
    target = project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)
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
        calls = (
            (2, "workspace_manifest", {}),
            (3, "read_project_file", {"relative_path": "sample.py"}),
            (
                4,
                "preview_text_replace",
                {
                    "relative_path": "sample.py",
                    "expected_sha256": hashlib.sha256(original).hexdigest(),
                    "old_text": "value = 1",
                    "new_text": "value = 2",
                },
            ),
        )
        observed = {}
        for request_id, name, arguments in calls:
            process.send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            result = process.receive()["result"]
            assert result["isError"] is False
            observed[name] = result["structuredContent"]
        process.assert_exit(0)
        assert not process.fallback_used

    assert observed["workspace_manifest"]["data"]["capability_state"] == "BUILT_NOT_PROVEN"
    assert observed["read_project_file"]["data"]["content"] == "value = 1\n"
    assert observed["preview_text_replace"]["data"]["status"] == "PREVIEW_ONLY"
    assert target.read_bytes() == original
