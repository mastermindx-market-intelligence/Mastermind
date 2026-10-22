"""Offline installer tests. Never invoke Cursor inference or the Fabric broker."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from integrations.cursor_agent_mastermind import install


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    w = tmp_path / "repo"
    w.mkdir()
    subprocess.run(["git", "init", "-q", str(w)], check=True)
    return w


def test_project_projection_is_explicit_reversible_and_idempotent(repo: Path) -> None:
    plan = install.project(repo)
    assert plan["state"] == "NOT_APPLIED"
    assert len(plan["files"]) == 5
    assert not (repo / ".cursor").exists()
    applied = install.project(repo, "apply")
    assert applied["state"] == "APPLIED"
    assert len(applied["created"]) == 5
    ready = install.project(repo, "verify")
    assert ready["state"] == "READY"
    assert len(install.project(repo, "apply")["created"]) == 0
    for record in ready["files"]:
        assert record["status"] == "unchanged"
        assert install.digest((repo / ".cursor" / record["path"]).read_bytes()) == record["sha256"]


def test_existing_paper_mcp_and_extra_agents_survive(repo: Path) -> None:
    (repo / ".cursor" / "agents").mkdir(parents=True)
    (repo / ".cursor" / "mcp.json").write_text('{"mcpServers":{"paper":{"command":"paper"}}}')
    (repo / ".cursor" / "agents" / "user-owned.md").write_text("KEEP\n")
    install.project(repo, "apply")
    assert json.loads((repo / ".cursor" / "mcp.json").read_text())["mcpServers"]["paper"]["command"] == "paper"
    assert (repo / ".cursor" / "agents" / "user-owned.md").read_text() == "KEEP\n"


def test_conflict_blocks_all_writes(repo: Path) -> None:
    t = repo / ".cursor" / "agents"
    t.mkdir(parents=True)
    (t / "mmx-fabric-operator.md").write_text("OWNER-CONFLICT\n")
    with pytest.raises(install.ProjectionRefused, match="conflicting"):
        install.project(repo, "apply")
    assert not (t / "mmx-repo-explorer.md").exists()
    assert (t / "mmx-fabric-operator.md").read_text() == "OWNER-CONFLICT\n"


def test_symlink_and_non_root_refused(repo: Path, tmp_path: Path) -> None:
    inner = repo / "child"
    inner.mkdir()
    with pytest.raises(install.ProjectionRefused, match="exact Git root"):
        install.project(inner)
    (repo / ".cursor").symlink_to(tmp_path)
    with pytest.raises(install.ProjectionRefused, match="symlink"):
        install.project(repo)


def test_intermediate_skills_symlink_is_refused_before_writes(repo: Path, tmp_path: Path) -> None:
    root = repo / ".cursor"
    root.mkdir()
    (root / "skills").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(install.ProjectionRefused, match="symlink"):
        install.project(repo, "apply")
    assert not (root / "agents" / "mmx-repo-explorer.md").exists()


def test_source_digest_drift_blocks_all_writes(repo: Path, tmp_path: Path, monkeypatch) -> None:
    source_copy = tmp_path / "source"
    shutil.copytree(install.ROOT, source_copy)
    p = source_copy / "agents/mmx-repo-explorer.md"
    p.write_text(p.read_text() + "\nDRIFT\n")
    monkeypatch.setattr(install, "ROOT", source_copy)
    with pytest.raises(install.ProjectionRefused, match="source digest mismatch"):
        install.project(repo, "apply")
    assert not (repo / ".cursor").exists()


def test_non_git_workspace_refused(tmp_path: Path) -> None:
    with pytest.raises(install.ProjectionRefused, match="Git root"):
        install.project(tmp_path)
