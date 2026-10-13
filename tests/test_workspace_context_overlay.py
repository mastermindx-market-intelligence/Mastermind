from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess

import pytest

from control_plane.workspace_context_overlay import (
    OVERLAY_SCHEMA,
    WorkspaceContextOverlayError,
    build_workspace_overlay,
)
from scripts import workspace_context_overlay as adapter

OPERATION = "context-test-001"
LANE = "web"


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q", "-b", "master")
    _git(source, "config", "user.email", "overlay-fixture@example.invalid")
    _git(source, "config", "user.name", "Overlay Fixture")
    (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "README.md").write_text("# Fixture\n", encoding="utf-8")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "base")
    base = _git(source, "rev-parse", "HEAD")

    root = tmp_path / "workspaces"
    root.mkdir()
    workspace = root / LANE / OPERATION
    workspace.parent.mkdir()
    branch = f"sol/{LANE}-{OPERATION}"
    _git(source, "worktree", "add", "-q", "-b", branch, str(workspace), base)
    _git(
        source,
        "worktree",
        "lock",
        "--reason",
        f"mastermind-linked-worktree:v1 operation={OPERATION} lane={LANE} base={base}",
        str(workspace),
    )
    _git(workspace, "config", "user.email", "overlay-fixture@example.invalid")
    _git(workspace, "config", "user.name", "Overlay Fixture")
    return source, root, workspace, base


def _observe(source: Path, root: Path, workspace: Path) -> dict:
    return adapter.observe_workspace_overlay(
        source_repo=source,
        workspace_root=root,
        workspace_path=workspace,
        operation_id=OPERATION,
        lane=LANE,
    )


def test_clean_acquired_workspace_has_empty_overlay(tmp_path: Path):
    source, root, workspace, base = _fixture(tmp_path)
    overlay = _observe(source, root, workspace)

    assert overlay["schema"] == OVERLAY_SCHEMA
    assert overlay["authoritative"] is False
    assert overlay["derived_read_only"] is True
    assert overlay["custody_owner"] == "mmx-workspace"
    assert overlay["operation_id"] == OPERATION
    assert overlay["base_sha"] == base
    assert overlay["head_sha"] == base
    assert overlay["dirty"] is False
    assert overlay["committed_changes"] == []
    assert overlay["working_changes"] == []
    assert overlay["safe_changed_paths"] == []


def test_working_file_content_changes_overlay_generation(tmp_path: Path):
    source, root, workspace, _base = _fixture(tmp_path)
    path = workspace / "app.py"

    path.write_text("VALUE = 2\n", encoding="utf-8")
    first = _observe(source, root, workspace)
    path.write_text("VALUE = 3\n", encoding="utf-8")
    second = _observe(source, root, workspace)

    assert first["dirty"] is True
    assert first["safe_changed_paths"] == ["app.py"]
    assert first["working_changes"][0]["content_state"] == "HASHED"
    assert first["working_changes"][0]["content_sha256"]
    assert first["overlay_generation"] != second["overlay_generation"]
    assert (
        first["working_changes"][0]["content_sha256"]
        != second["working_changes"][0]["content_sha256"]
    )


def test_untracked_safe_file_is_hashed(tmp_path: Path):
    source, root, workspace, _base = _fixture(tmp_path)
    (workspace / "new.py").write_text("NEW = True\n", encoding="utf-8")
    overlay = _observe(source, root, workspace)

    row = next(item for item in overlay["working_changes"] if item["path"] == "new.py")
    assert row["status"] == "??"
    assert row["content_state"] == "HASHED"
    assert len(row["content_sha256"]) == 64


def test_sensitive_changed_path_is_opaque(tmp_path: Path):
    source, root, workspace, _base = _fixture(tmp_path)
    (workspace / ".env.py").write_text("TOKEN = 'fixture-secret'\n", encoding="utf-8")
    overlay = _observe(source, root, workspace)
    serialized = json.dumps(overlay, sort_keys=True)

    assert overlay["sensitive_change_count"] == 1
    assert ".env.py" not in serialized
    sensitive = next(
        item
        for item in overlay["working_changes"]
        if item["content_state"] == "SENSITIVE_PATH"
    )
    assert sensitive["path"] is None
    assert len(sensitive["path_digest"]) == 64
    assert sensitive["content_sha256"] is None


def test_committed_change_is_relative_to_acquired_base(tmp_path: Path):
    source, root, workspace, base = _fixture(tmp_path)
    (workspace / "app.py").write_text("VALUE = 7\n", encoding="utf-8")
    _git(workspace, "add", "app.py")
    _git(workspace, "commit", "-qm", "advance")
    head = _git(workspace, "rev-parse", "HEAD")

    overlay = _observe(source, root, workspace)

    assert overlay["base_sha"] == base
    assert overlay["head_sha"] == head
    assert overlay["head_sha"] != overlay["base_sha"]
    assert overlay["dirty"] is False
    assert overlay["safe_changed_paths"] == ["app.py"]
    assert overlay["committed_changes"] == [
        {
            "status": "M",
            "path": "app.py",
            "path_digest": None,
            "content_sha256": None,
            "content_state": "COMMITTED_REF",
        }
    ]


def test_committed_and_uncommitted_change_are_both_visible(tmp_path: Path):
    source, root, workspace, _base = _fixture(tmp_path)
    (workspace / "app.py").write_text("VALUE = 7\n", encoding="utf-8")
    _git(workspace, "add", "app.py")
    _git(workspace, "commit", "-qm", "advance")
    (workspace / "README.md").write_text("# Changed\n", encoding="utf-8")

    overlay = _observe(source, root, workspace)

    assert overlay["dirty"] is True
    assert overlay["safe_changed_paths"] == ["README.md", "app.py"]
    assert [item["path"] for item in overlay["committed_changes"]] == ["app.py"]
    assert [item["path"] for item in overlay["working_changes"]] == ["README.md"]


@pytest.mark.parametrize(
    ("operation_id", "lane"),
    [
        ("wrong-op", LANE),
        (OPERATION, "review"),
    ],
)
def test_wrong_workspace_identity_is_refused(
    tmp_path: Path, operation_id: str, lane: str
):
    source, root, workspace, _base = _fixture(tmp_path)
    with pytest.raises(WorkspaceContextOverlayError, match="operation identity"):
        adapter.observe_workspace_overlay(
            source_repo=source,
            workspace_root=root,
            workspace_path=workspace,
            operation_id=operation_id,
            lane=lane,
        )


def test_unlocked_workspace_is_refused(tmp_path: Path):
    source, root, workspace, _base = _fixture(tmp_path)
    _git(source, "worktree", "unlock", str(workspace))
    with pytest.raises(WorkspaceContextOverlayError, match="custody lock"):
        _observe(source, root, workspace)


def test_workspace_outside_managed_root_is_refused(tmp_path: Path):
    source, _root, workspace, _base = _fixture(tmp_path)
    wrong_root = tmp_path / "wrong-root"
    wrong_root.mkdir()
    with pytest.raises(WorkspaceContextOverlayError, match="outside"):
        adapter.observe_workspace_overlay(
            source_repo=source,
            workspace_root=wrong_root,
            workspace_path=workspace,
            operation_id=OPERATION,
            lane=LANE,
        )


def test_pure_overlay_is_byte_deterministic():
    committed = [
        {
            "status": "M",
            "path": "app.py",
            "path_digest": None,
            "content_sha256": None,
            "content_state": "COMMITTED_REF",
        }
    ]
    working = [
        {
            "status": " M",
            "path": "README.md",
            "path_digest": None,
            "content_sha256": "a" * 64,
            "content_state": "HASHED",
        }
    ]
    kwargs = dict(
        operation_id=OPERATION,
        lane=LANE,
        base_sha="b" * 40,
        head_sha="c" * 40,
        branch=f"sol/{LANE}-{OPERATION}",
        committed_changes=committed,
        working_changes=working,
    )
    left = build_workspace_overlay(**kwargs)
    right = build_workspace_overlay(**kwargs)
    assert left == right
    assert json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def test_sensitive_row_cannot_smuggle_raw_path():
    row = {
        "status": "??",
        "path": ".env",
        "path_digest": None,
        "content_sha256": None,
        "content_state": "SENSITIVE_PATH",
    }
    with pytest.raises(WorkspaceContextOverlayError, match="opaque"):
        build_workspace_overlay(
            operation_id=OPERATION,
            lane=LANE,
            base_sha="b" * 40,
            head_sha="b" * 40,
            branch=f"sol/{LANE}-{OPERATION}",
            committed_changes=[],
            working_changes=[row],
        )


def test_pure_overlay_has_no_filesystem_network_runtime_imports():
    source_path = (
        Path(__file__).parents[1] / "control_plane" / "workspace_context_overlay.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    forbidden = {
        "os",
        "pathlib",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "time",
        "random",
        "app",
        "runtime",
    }
    assert imports.isdisjoint(forbidden)
