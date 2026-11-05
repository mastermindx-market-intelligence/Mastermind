"""Installed-process resume proof; no remote network or production paths are used."""
import json
import os
import subprocess
from pathlib import Path

from scripts import install_mini_worktree_host as installer
from scripts import mini_worktree as mw
from test_mini_worktree import _fixture, _git


def test_installed_helper_resumes_complete_v2_and_refuses_incomplete(tmp_path, monkeypatch):
    cfg, _source = _fixture(tmp_path)
    # Real constructor establishes the fixture; the installed process consumes it.
    first = mw.create_worktree(cfg, "fixture", "packaged", "fixture-session")
    workspace = Path(first["workspace"])
    home = tmp_path / "installed-home"
    home.mkdir()
    monkeypatch.setenv("MACRO_GIT_REMOTE", "git@github.com:mastermindx-market-intelligence/macro.git")
    monkeypatch.setenv("MACRO_GIT_SSH_COMMAND", "ssh")
    source = Path(__file__).resolve().parents[1]
    installed = installer.install(source_root=source, home=home, bootstrap=False)
    canonical = "https://github.com/mastermindx-market-intelligence/Mastermind.git"
    # Resume performs no network. Fixture origin and config retain exact identity.
    _git(cfg.store_root / "fixture", "remote", "set-url", "origin", canonical)
    config = Path(installed["config"])
    config.write_text(json.dumps({"schema_version": mw.CONFIG_SCHEMA,
        "store_root": str(cfg.store_root), "hot_root": str(cfg.hot_root),
        "min_free_bytes": 1, "resume_free_bytes": 2,
        "repositories": {"fixture": {"url": canonical, "default_branch": "main", "exclude_dirs": ["vendor"]}}}))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "MACRO_", "PYTHONPATH", "PYTHONHOME"))}
    env.update(HOME=str(home), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
               GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="")
    def invoke(*args, expected=0):
        result = subprocess.run([installed["wrapper"], *args], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected, result.stderr
        return json.loads(result.stdout if expected == 0 else result.stderr)
    create = ("create", "--repo", "fixture", "--name", "packaged", "--session-id", "fixture-session")
    resumed = invoke(*create)
    assert resumed["receipt"]["reused"] is True
    assert resumed["receipt"]["lock_reason"] == first["lock_reason"]
    assert (workspace / "src/src.txt").is_file()
    assert not (workspace / "vendor").exists()
    assert invoke("census")["receipt"]["repositories"]["fixture"]["state"] == "READY"
    (workspace / "active.txt").write_text("preserve")
    assert invoke(*create)["receipt"]["reused"] is True
    _git(workspace, "config", "--worktree", "--unset-all", "mastermind.miniPrepared")
    rejected = invoke(*create, expected=2)
    assert rejected["effect"] == "EFFECT_UNKNOWN"
    assert "preparation incomplete" in rejected["error"]
    assert (workspace / "active.txt").read_text() == "preserve"
    assert invoke("census")["receipt"]["repositories"]["fixture"]["state"] == "PARTIAL"
