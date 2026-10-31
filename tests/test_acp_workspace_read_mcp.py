from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path

import pytest

from integrations.workbench_read_mcp.observer import ReadRefusal


def _mod():
    from integrations.acp_worker import workspace_read_mcp
    return workspace_read_mcp


def _workspace(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir(mode=0o700)
    (root / "memo.txt").write_text(
        "alpha line\nneedle ONE\nbeta line\nneedle two\nomega\n",
        encoding="utf-8",
    )
    sub = root / "sub"
    sub.mkdir(mode=0o700)
    (sub / "other.txt").write_text("sub needle three\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret\n", encoding="utf-8")
    return root, outside


def _env(root: Path, *, deadline_ms: int | None = None) -> dict[str, str]:
    if deadline_ms is None:
        deadline_ms = int(time.time() * 1000) + 60_000
    return {
        "MMX_ACP_WORKSPACE_PATH": str(root),
        "MMX_ACP_WORKSPACE_BASE_SHA": "a" * 40,
        "MMX_ACP_RUN_ID": "RUN-1",
        "MMX_ACP_JOB_ID": "JOB-1",
        "MMX_ACP_WORKER_ID": "acp-worker-01",
        "MMX_ACP_DEADLINE_MS": str(deadline_ms),
    }


def test_gateway_reads_one_exact_workspace_file_with_existing_observer(tmp_path):
    m = _mod()
    root, _ = _workspace(tmp_path)
    gateway = m.WorkspaceReadGateway.from_environment(_env(root))
    try:
        result = gateway.call("read_file", {
            "relative_path": "memo.txt",
            "start_line": 1,
            "max_lines": 2,
            "max_content_bytes": 1024,
        })
        assert result["ok"] is True
        assert result["tool"] == "read_file"
        data = result["data"]
        assert data["content"] == "needle ONE\nbeta line\n"
        assert data["line_start"] == 1
        assert data["line_end"] == 3
        assert data["file_sha256"] == hashlib.sha256(
            (root / "memo.txt").read_bytes()
        ).hexdigest()
        assert data["run_id"] == "RUN-1"
        assert data["job_id"] == "JOB-1"
        assert data["worker_id"] == "acp-worker-01"
    finally:
        gateway.close()


def test_gateway_searches_one_file_page_without_tree_crawl(tmp_path):
    m = _mod()
    root, _ = _workspace(tmp_path)
    gateway = m.WorkspaceReadGateway.from_environment(_env(root))
    try:
        result = gateway.call("search_text", {
            "relative_path": "memo.txt",
            "query": "needle",
            "start_line": 0,
            "max_lines": 5,
            "max_matches": 8,
            "case_sensitive": False,
        })
        assert result["ok"] is True
        data = result["data"]
        assert [(row["line"], row["text"]) for row in data["matches"]] == [
            (1, "needle ONE"),
            (3, "needle two"),
        ]
        assert data["query"] == "needle"
        assert data["searched_line_start"] == 0
        assert data["searched_line_end"] == 5
        assert data["next_line"] is None
    finally:
        gateway.close()


@pytest.mark.parametrize("relative_path", [
    "../outside.txt", "/etc/passwd", ".git/config", "sub/../../outside.txt",
])
def test_gateway_refuses_escape_paths(tmp_path, relative_path):
    m = _mod()
    root, _ = _workspace(tmp_path)
    gateway = m.WorkspaceReadGateway.from_environment(_env(root))
    try:
        result = gateway.call("read_file", {"relative_path": relative_path})
        assert result["ok"] is False
        assert result["error"]["code"] in {"INVALID_REQUEST", "PROJECT_READ_REFUSED"}
    finally:
        gateway.close()


def test_gateway_refuses_symlink_leaf_even_when_it_points_inside_workspace(tmp_path):
    m = _mod()
    root, _ = _workspace(tmp_path)
    (root / "link.txt").symlink_to(root / "memo.txt")
    gateway = m.WorkspaceReadGateway.from_environment(_env(root))
    try:
        result = gateway.call("read_file", {"relative_path": "link.txt"})
        assert result["ok"] is False
        assert result["error"]["code"] == "UNSAFE_FILE_TYPE"
    finally:
        gateway.close()


def test_gateway_deadline_is_a_real_scope_fence(tmp_path):
    m = _mod()
    root, _ = _workspace(tmp_path)
    gateway = m.WorkspaceReadGateway.from_environment(
        _env(root, deadline_ms=int(time.time() * 1000) - 1)
    )
    try:
        result = gateway.call("read_file", {"relative_path": "memo.txt"})
        assert result["ok"] is False
        assert result["error"]["code"] == "SCOPE_EXPIRED"
    finally:
        gateway.close()


def test_gateway_refuses_root_identity_change_after_construction(tmp_path):
    m = _mod()
    root, _ = _workspace(tmp_path)
    gateway = m.WorkspaceReadGateway.from_environment(_env(root))
    moved = tmp_path / "workspace-old"
    root.rename(moved)
    root.mkdir(mode=0o700)
    (root / "memo.txt").write_text("replacement\n", encoding="utf-8")
    try:
        result = gateway.call("read_file", {"relative_path": "memo.txt"})
        assert result["ok"] is False
        assert result["error"]["code"] in {"SCOPE_UNAVAILABLE", "ROOT_IDENTITY_CHANGED", "SOURCE_CHANGED"}
    finally:
        gateway.close()


@pytest.mark.parametrize("mutation", [
    lambda env: env.pop("MMX_ACP_RUN_ID"),
    lambda env: env.__setitem__("MMX_ACP_WORKSPACE_PATH", "relative"),
    lambda env: env.__setitem__("MMX_ACP_WORKSPACE_BASE_SHA", "bad"),
    lambda env: env.__setitem__("MMX_ACP_DEADLINE_MS", "not-int"),
    lambda env: env.__setitem__("MMX_ACP_JOB_ID", "bad\njob"),
])
def test_environment_contract_is_closed_and_nonsecret(tmp_path, mutation):
    m = _mod()
    root, _ = _workspace(tmp_path)
    env = _env(root)
    mutation(env)
    with pytest.raises(ValueError, match="ACP workspace read environment"):
        m.WorkspaceReadGateway.from_environment(env)


def test_mcp_surface_is_exactly_two_readonly_tools_and_digest_matches_canonical_owner():
    m = _mod()
    from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest

    tools = m.tool_catalog()
    assert [tool["name"] for tool in tools] == ["read_file", "search_text"]
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
    assert all(tool["annotations"]["destructiveHint"] is False for tool in tools)
    assert observed_mcp_tool_schema_digest({"tools": {row["name"]: row for row in tools}}) == (
        m.TOOL_SCHEMA_DIGEST
    )


def test_search_result_is_bounded_and_never_echoes_more_than_requested(tmp_path):
    m = _mod()
    root, _ = _workspace(tmp_path)
    (root / "many.txt").write_text(
        "".join(f"needle {index:04d}\n" for index in range(200)),
        encoding="utf-8",
    )
    gateway = m.WorkspaceReadGateway.from_environment(_env(root))
    try:
        result = gateway.call("search_text", {
            "relative_path": "many.txt",
            "query": "needle",
            "max_lines": 128,
            "max_matches": 3,
            "case_sensitive": True,
        })
        assert result["ok"] is True
        assert len(result["data"]["matches"]) == 3
        assert result["data"]["matches_truncated"] is True
        assert result["data"]["next_line"] == 128
        assert len(json.dumps(result).encode()) < m.MAX_RESULT_BYTES
    finally:
        gateway.close()
