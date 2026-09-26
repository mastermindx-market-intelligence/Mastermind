from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import mini_worktree as mw


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _fixture(tmp_path: Path) -> tuple[mw.HostConfig, Path]:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q", "-b", "main")
    _git(source, "config", "user.name", "Mini Worktree Test")
    _git(source, "config", "user.email", "mini-worktree@example.invalid")
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    for name in ("src", "data", "vendor"):
        (source / name).mkdir()
        (source / name / f"{name}.txt").write_text(name + "\n", encoding="utf-8")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "fixture")

    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(remote)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _git(remote, "config", "uploadpack.allowFilter", "true")
    _git(remote, "config", "uploadpack.allowAnySHA1InWant", "true")

    spec = mw.RepoSpec(
        key="fixture",
        url=remote.as_uri(),
        default_branch="main",
        exclude_dirs=("vendor",),
    )
    cfg = mw.HostConfig(
        store_root=tmp_path / "stores",
        hot_root=tmp_path / "hot",
        min_free_bytes=1,
        resume_free_bytes=2,
        repos={"fixture": spec},
    )
    return cfg, source


def test_bootstrap_is_blobless_sparse_and_excludes_heavy_dir(tmp_path: Path):
    cfg, _ = _fixture(tmp_path)
    receipt = mw.bootstrap_repo(cfg, "fixture")
    store = Path(receipt["store"])

    assert receipt["created"] is True
    assert (store / "src" / "src.txt").read_text() == "src\n"
    assert (store / "data" / "data.txt").read_text() == "data\n"
    assert not (store / "vendor").exists()
    assert _git(store, "config", "--get", "remote.origin.promisor") == "true"
    assert _git(store, "config", "--get", "remote.origin.partialclonefilter") == "blob:none"
    assert _git(store, "config", "--get", "core.sparseCheckout") == "true"

    second = mw.bootstrap_repo(cfg, "fixture")
    assert second["created"] is False


def test_low_space_refuses_before_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg, _ = _fixture(tmp_path)
    monkeypatch.setattr(mw, "_free_bytes", lambda _path: 0)

    with pytest.raises(mw.MiniWorktreeError, match="HOT_STORAGE_LOW_SPACE"):
        mw.bootstrap_repo(cfg, "fixture")

    assert not (cfg.store_root / "fixture").exists()


def test_create_is_sparse_locked_and_exact_session_idempotent(tmp_path: Path):
    cfg, _ = _fixture(tmp_path)

    first = mw.create_worktree(cfg, "fixture", "task-001", "session-001")
    worktree = Path(first["workspace"])
    assert first["reused"] is False
    assert (worktree / "src" / "src.txt").exists()
    assert not (worktree / "vendor").exists()
    assert _git(worktree, "config", "--get", "core.sparseCheckout") == "true"

    store = cfg.store_root / "fixture"
    rows = mw._porcelain_worktrees(store)
    record = next(row for row in rows if Path(row["worktree"]).resolve() == worktree.resolve())
    assert record["locked"] == first["lock_reason"]

    same = mw.create_worktree(cfg, "fixture", "task-001", "session-001")
    assert same["reused"] is True
    assert same["workspace"] == str(worktree)

    with pytest.raises(mw.MiniWorktreeError, match="identity does not match"):
        mw.create_worktree(cfg, "fixture", "task-001", "session-other")


def test_census_uses_git_registry_and_reports_dirt(tmp_path: Path):
    cfg, _ = _fixture(tmp_path)
    receipt = mw.create_worktree(cfg, "fixture", "task-002", "session-002")
    worktree = Path(receipt["workspace"])
    (worktree / "local.txt").write_text("unique\n", encoding="utf-8")

    result = mw.census(cfg)
    rows = result["repositories"]["fixture"]["worktrees"]
    assert len(rows) == 1
    assert rows[0]["path"] == str(worktree.resolve())
    assert rows[0]["dirty"] is True
    assert rows[0]["lock_reason"].startswith(mw.LOCK_PREFIX)


def test_load_config_rejects_relative_roots_and_bad_schema(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "wrong",
                "store_root": str(tmp_path / "stores"),
                "hot_root": str(tmp_path / "hot"),
                "min_free_bytes": 1,
                "resume_free_bytes": 2,
                "repositories": {
                    "fixture": {
                        "url": "https://github.com/example/repo.git",
                        "default_branch": "main",
                        "exclude_dirs": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(mw.MiniWorktreeError, match="unsupported"):
        mw.load_config(path)
