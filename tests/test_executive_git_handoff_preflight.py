"""Fail-closed tests for the Gate B Git-handoff preflight instrument.

These tests cover the diagnostic only. They do not change production Git
observation, handoff validation, safe.directory, or worker ownership.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / "ops" / "executive_os" / "git_handoff_preflight.py"
SPEC = importlib.util.spec_from_file_location(
    "executive_git_handoff_preflight_hardening", PREFLIGHT_PATH
)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)

PROBE_ID = "gate-b-deadbeefcafe"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    return result.stdout.strip()


def _tiny_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tracked.txt").write_text("hello-stimulus\n", encoding="utf-8")
    (repo / "link-target.txt").write_text("target\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Gate B Test")
    _git(repo, "config", "user.email", "gate-b@example.invalid")
    _git(repo, "add", "tracked.txt", "link-target.txt")
    _git(repo, "commit", "-qm", "seed")
    return repo


def _workspace_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def _cleanup(
    *,
    expected: Path,
    workspace_root: Path,
    before: list[dict],
    supervisor_home: Path | None = None,
    existed: bool = False,
) -> bool:
    home = supervisor_home or (workspace_root / ".supervisor-home")
    return preflight._cleanup(
        expected_workspace=expected,
        workspace_root=workspace_root,
        supervisor_home=home,
        supervisor_home_existed=existed,
        before=before,
        control_uid=os.geteuid(),
    )


def test_gate_b_cm1_child_failure_before_json_cleans_derived_workspace(tmp_path: Path):
    root = _workspace_root(tmp_path)
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    before = preflight.snapshot_workspace_root(root)
    expected.mkdir()
    (expected / "clone-marker").write_text("child created this before JSON failed\n")
    assert expected.is_dir()
    restored = _cleanup(expected=expected, workspace_root=root, before=before)
    assert restored is True
    assert preflight.path_lexists(expected) is False
    assert preflight.workspace_root_restored(before, preflight.snapshot_workspace_root(root))


def test_gate_b_cm2_wrong_child_path_is_not_cleanup_authority(tmp_path: Path):
    root = _workspace_root(tmp_path)
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    before = preflight.snapshot_workspace_root(root)
    expected.mkdir()
    (expected / "real-clone").write_text("derived\n")
    outsider = tmp_path / "outsider"
    outsider.mkdir()
    (outsider / "do-not-delete").write_text("keep\n")
    with pytest.raises(preflight.PreflightError, match="not the derived workspace"):
        preflight.child_workspace_matches_derived(
            expected=expected, returned=str(outsider)
        )
    restored = _cleanup(expected=expected, workspace_root=root, before=before)
    assert restored is True
    assert preflight.path_lexists(expected) is False
    assert (outsider / "do-not-delete").read_text() == "keep\n"


def test_gate_b_cm3_symlink_cleanup_unlinks_link_and_preserves_target(tmp_path: Path):
    root = _workspace_root(tmp_path)
    canary = tmp_path / "canary-target"
    canary.mkdir()
    (canary / "secret").write_text("preserve\n")
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    before = preflight.snapshot_workspace_root(root)
    expected.symlink_to(canary)
    restored = _cleanup(expected=expected, workspace_root=root, before=before)
    assert restored is True
    assert preflight.path_lexists(expected) is False
    assert (canary / "secret").read_text() == "preserve\n"


def test_gate_b_cm4_broken_symlink_is_unlinked(tmp_path: Path):
    root = _workspace_root(tmp_path)
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    before = preflight.snapshot_workspace_root(root)
    expected.symlink_to(tmp_path / "missing-target")
    assert expected.exists() is False
    assert preflight.path_lexists(expected) is True
    restored = _cleanup(expected=expected, workspace_root=root, before=before)
    assert restored is True
    assert preflight.path_lexists(expected) is False


def test_gate_b_cm5_unexpected_object_is_refused_and_left_in_place(tmp_path: Path):
    root = _workspace_root(tmp_path)
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    expected.write_text("not a workspace directory\n")
    before = preflight.snapshot_workspace_root(root)
    with pytest.raises(preflight.PreflightError, match="unexpected object"):
        _cleanup(expected=expected, workspace_root=root, before=before)
    assert expected.is_file()
    assert expected.read_text() == "not a workspace directory\n"


def test_gate_b_cm6_preexisting_supervisor_home_is_preserved(tmp_path: Path):
    root = _workspace_root(tmp_path)
    home = root / ".supervisor-home"
    home.mkdir(mode=0o700)
    marker = home / "preexisting"
    marker.write_text("keep-me\n")
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    expected.mkdir()
    before = preflight.snapshot_workspace_root(root)
    # before includes the leftover workspace; remove it then compare against
    # a snapshot that still has the preexisting home.
    before_with_home = [
        item for item in before if item["name"] != PROBE_ID
    ]
    restored = _cleanup(
        expected=expected,
        workspace_root=root,
        before=before_with_home,
        supervisor_home=home,
        existed=True,
    )
    assert restored is True
    assert marker.read_text() == "keep-me\n"
    assert home.is_dir()


def test_gate_b_cm7_unsafe_probe_created_supervisor_home_is_refused(tmp_path: Path):
    root = _workspace_root(tmp_path)
    home = root / ".supervisor-home"
    home.mkdir(mode=0o755)
    os.chmod(home, 0o755)
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    before = preflight.snapshot_workspace_root(root)
    with pytest.raises(preflight.PreflightError, match="private empty directory"):
        _cleanup(
            expected=expected,
            workspace_root=root,
            before=before,
            supervisor_home=home,
            existed=False,
        )
    assert home.is_dir()


def test_gate_b_cm8_release_raw_symlink_is_refused(tmp_path: Path):
    sha = "a" * 40
    real = tmp_path / "real" / sha
    real.mkdir(parents=True)
    link = tmp_path / "releases" / sha
    link.parent.mkdir()
    link.symlink_to(real)
    with pytest.raises(preflight.PreflightError, match="must not be a symlink"):
        preflight.require_release_sha(link, sha)
    accepted = preflight.require_release_sha(real, sha)
    assert accepted == real.resolve(strict=True)


def test_gate_b_cm9_workspace_root_raw_symlink_is_refused(tmp_path: Path):
    real = tmp_path / "real-root"
    real.mkdir(mode=0o700)
    os.chmod(real, 0o700)
    link = tmp_path / "linked-root"
    link.symlink_to(real)
    with pytest.raises(preflight.PreflightError, match="must not be a symlink"):
        preflight.require_workspace_root(link, control_uid=os.geteuid())
    canonical = preflight.require_workspace_root(real, control_uid=os.geteuid())
    assert canonical == real.resolve(strict=True)


def test_gate_b_cm10_mtime_stimulus_is_content_preserving(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    relative, path = preflight.select_tracked_regular_file(repo)
    assert relative == "link-target.txt" or relative == "tracked.txt"
    before = preflight.regular_file_identity(path, relative=relative)
    stimulus = preflight.apply_mtime_stimulus(path, relative=relative)
    after = preflight.regular_file_identity(path, relative=relative)
    stability = preflight.stimulus_payload_stable(before, after)
    assert stimulus["selection_method"] == preflight.STIMULUS_METHOD
    assert stimulus["after_touch"]["mtime_ns"] != before["mtime_ns"]
    assert after["mtime_ns"] != before["mtime_ns"]
    assert after["sha256"] == before["sha256"]
    assert after["size"] == before["size"]
    assert stability == {
        "bytes_unchanged": True,
        "size_unchanged": True,
        "ownership_mode_unchanged": True,
    }
    mutated = dict(after)
    mutated["sha256"] = hashlib.sha256(b"tampered").hexdigest()
    assert preflight.stimulus_payload_stable(before, mutated)["bytes_unchanged"] is False


def test_gate_b_select_tracked_regular_file_skips_symlinks(tmp_path: Path):
    repo = _tiny_repo(tmp_path)
    link = repo / "tracked-link"
    link.symlink_to("link-target.txt")
    _git(repo, "add", "tracked-link")
    _git(repo, "commit", "-qm", "add tracked symlink")
    relative, path = preflight.select_tracked_regular_file(repo)
    assert not path.is_symlink()
    assert path.is_file()
    assert relative != "tracked-link"


def test_gate_b_index_lock_absent_uses_lstat(tmp_path: Path):
    workspace = tmp_path / "workspace"
    git_dir = workspace / ".git"
    git_dir.mkdir(parents=True)
    assert preflight.index_lock_absent(workspace) is True
    lock = git_dir / "index.lock"
    lock.symlink_to(tmp_path / "missing-lock-target")
    assert lock.exists() is False
    assert preflight.index_lock_absent(workspace) is False


def test_gate_b_derived_workspace_is_root_child_and_rejects_escape(tmp_path: Path):
    root = _workspace_root(tmp_path)
    derived = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    assert derived.parent == root
    assert derived.name == PROBE_ID
    with pytest.raises(preflight.PreflightError, match="unsafe generated probe id"):
        preflight.derive_workspace_path(workspace_root=root, probe_id="../escape")


def test_gate_b_cleanup_refuses_path_outside_workspace_root(tmp_path: Path):
    root = _workspace_root(tmp_path)
    outsider = tmp_path / PROBE_ID
    outsider.mkdir()
    with pytest.raises(preflight.PreflightError, match="escaped workspace root"):
        preflight.remove_probe_workspace(outsider, workspace_root=root)
    assert outsider.is_dir()


def test_gate_b_empty_probe_created_supervisor_home_is_removed(tmp_path: Path):
    root = _workspace_root(tmp_path)
    home = root / ".supervisor-home"
    home.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    before = [item for item in preflight.snapshot_workspace_root(root) if item["name"] != ".supervisor-home"]
    restored = _cleanup(
        expected=expected,
        workspace_root=root,
        before=before,
        supervisor_home=home,
        existed=False,
    )
    assert restored is True
    assert preflight.path_lexists(home) is False


def test_gate_b_probe_created_symlink_supervisor_home_is_refused(tmp_path: Path):
    root = _workspace_root(tmp_path)
    target = tmp_path / "home-target"
    target.mkdir()
    home = root / ".supervisor-home"
    home.symlink_to(target)
    expected = preflight.derive_workspace_path(workspace_root=root, probe_id=PROBE_ID)
    before = preflight.snapshot_workspace_root(root)
    with pytest.raises(preflight.PreflightError, match="private empty directory"):
        _cleanup(
            expected=expected,
            workspace_root=root,
            before=before,
            supervisor_home=home,
            existed=False,
        )
    assert home.is_symlink()
    assert target.is_dir()


def test_gate_b_index_stability_fields_detect_mtime_rewrite(tmp_path: Path):
    index = tmp_path / "index"
    index.write_bytes(b"idx")
    index.chmod(0o640)
    meta = preflight.index_metadata(index)
    assert set(preflight.INDEX_STABILITY_FIELDS) <= set(meta)
    changed = dict(meta)
    changed["mtime_ns"] = int(meta["mtime_ns"]) + 1
    assert preflight.index_observation_stable(meta, changed) is False
    assert preflight.index_observation_stable(meta, dict(meta)) is True


def test_gate_b_release_canonical_name_must_match_sha(tmp_path: Path):
    sha = "b" * 40
    wrong = tmp_path / ("c" * 40)
    wrong.mkdir()
    with pytest.raises(preflight.PreflightError, match="exact expected SHA"):
        preflight.require_release_sha(wrong, sha)


def test_gate_b_world_writable_workspace_root_still_refused(tmp_path: Path):
    world = tmp_path / "world"
    world.mkdir()
    world.chmod(0o755)
    with pytest.raises(preflight.PreflightError, match="unsafe workspace-root"):
        preflight.require_workspace_root(world, control_uid=os.geteuid())
