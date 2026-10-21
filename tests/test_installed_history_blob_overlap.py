"""Bounded test-only falsifier; no installed source/service access or mutation."""
from pathlib import Path
import subprocess
import threading
import time
import pytest
from integrations.executive_mcp import installed


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    record = repo / "agentos/workstreams/WS-TEST.md"
    record.parent.mkdir(parents=True)
    record.write_text("first\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    record.write_text("second\n")
    (repo / "plain.txt").write_text("current blob\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "second")
    return repo


@pytest.mark.parametrize("scope", ["all", "macro_brief"])
def test_current_blobs_can_progress_while_ancestry_enumeration_is_pending(tmp_path, monkeypatch, scope):
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    blob_started = threading.Event()
    ancestry_started = threading.Event()
    blob_overlap = []
    observed_overlap = []
    maps = []
    real_probe = installed._require_git_object_types

    def probe(path, expected_types, **kwargs):
        maps.append(dict(expected_types))
        if expected_types and set(expected_types.values()) == {"blob"}:
            blob_started.set()
            blob_overlap.append(ancestry_started.wait(timeout=2.0))
        return real_probe(path, expected_types, **kwargs)

    def runner(argv, **kwargs):
        if list(argv[1:3]) == ["rev-list", "--parents"]:
            # Synchronization fact, not a speed claim: current source cannot
            # enter blob validation until this ancestry call returns.
            ancestry_started.set()
            observed_overlap.append(blob_started.wait(timeout=2.0))
        return installed._default_packet_runner(argv, **kwargs)

    monkeypatch.setattr(installed, "_require_git_object_types", probe)
    captures = []
    actual = installed._clean_git_snapshot(
        repo, runner=runner, env=installed._installed_child_env(code_root=repo, macro_root=repo),
        label="Macro source", content_scope=scope, include_seal=True,
        snapshot_capture=captures, deadline=time.monotonic() + 10.0,
    )
    assert actual[0] == head
    assert len(captures) == 1
    commits = set(_git(repo, "rev-list", "HEAD").splitlines())
    blobs = {line.split()[2] for line in _git(repo, "ls-tree", "-r", "HEAD").splitlines()}
    checked = {oid: kind for mapping in maps for oid, kind in mapping.items()}
    assert all(checked.get(oid) == "commit" for oid in commits)
    assert all(checked.get(oid) == "blob" for oid in blobs)
    assert observed_overlap == [True], "ancestry blocks independent current-blob proof"
    assert blob_overlap == [True], "current blobs block independent ancestry proof"
