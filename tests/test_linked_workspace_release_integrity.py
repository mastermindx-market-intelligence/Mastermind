from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from control_plane import executive_workspace as owner
from scripts import mastermind_workspace as cli


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True,
                                   stderr=subprocess.PIPE).strip()


@pytest.fixture
def release_case(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-q", "-b", "master")
    git(source, "config", "user.name", "Release integrity fixture")
    git(source, "config", "user.email", "release@example.invalid")
    (source / "README.md").write_text("base\n")
    (source / ".gitignore").write_text("cache/\n")
    git(source, "add", "README.md", ".gitignore")
    git(source, "commit", "-qm", "base")
    base = git(source, "rev-parse", "HEAD")
    root = tmp_path / "workspaces"
    operation = "release-integrity"
    branch = "sol/web-release-integrity"
    made = owner.prepare_linked_worktree(source, root, operation_id=operation,
        lane="web", base_sha=base, branch=branch)
    target = Path(made.workspace_path)
    admin = Path((target / ".git").read_text().removeprefix("gitdir: ").strip())
    for key in ("MASTERMIND_WORKSPACE_REPOSITORIES", "MASTERMIND_WORKSPACE_STORAGE_POLICY",
                "MASTERMIND_WORKSPACE_REQUIRE_MOUNT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MASTERMIND_SOURCE_REPO", str(source))
    monkeypatch.setenv("MASTERMIND_AGENT_WORKSPACE_ROOT", str(root))
    return source, root, target, admin, operation, branch, base


def mutation_observer(monkeypatch, *, lost_reply: str | None = None):
    calls = []
    real = owner._run

    def observe(argv, **kwargs):
        mutation = len(argv) > 4 and list(argv)[3:5] in (
            ["worktree", "unlock"], ["worktree", "remove"], ["worktree", "lock"])
        if mutation:
            calls.append(list(argv))
        result = real(argv, **kwargs)
        if mutation and argv[4] == lost_reply:
            raise owner.WorkspaceError("simulated lost reply after native Git mutation")
        return result

    monkeypatch.setattr(owner, "_run", observe)
    return calls


def test_release_succeeds_when_unrelated_fleet_enumeration_is_unavailable(release_case, monkeypatch):
    source, root, target, _, operation, branch, base = release_case
    sibling = owner.prepare_linked_worktree(source, root, operation_id="other-owner",
        lane="web", base_sha=base, branch="sol/web-other-owner")
    sibling_path = Path(sibling.workspace_path)
    (sibling_path / "unpublished.txt").write_text("retain this writer\n")
    sibling_inode = sibling_path.stat().st_ino

    def unavailable(*args, **kwargs):
        raise owner.WorkspaceError("unrelated fleet enumeration exceeded its deadline")

    monkeypatch.setattr(owner, "_worktree_records", unavailable)
    receipt = owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert receipt.removed and receipt.state == "REMOVED"
    assert not target.exists()
    assert git(source, "rev-parse", branch) == base
    assert sibling_path.stat().st_ino == sibling_inode
    assert (sibling_path / "unpublished.txt").read_text() == "retain this writer\n"


@pytest.mark.parametrize("lost_reply", ["unlock", "remove"])
def test_cli_lost_mutation_reply_never_claims_no_effect(release_case, monkeypatch, capsys, lost_reply):
    source, _, target, _, operation, branch, base = release_case
    calls = mutation_observer(monkeypatch, lost_reply=lost_reply)
    code = cli.main(["release", "--operation-id", operation, "--lane", "web"])
    output = capsys.readouterr()
    result = json.loads(output.err or output.out)
    assert code == 2
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert result["retry_authorized"] is False
    assert result["operation_id"] == operation
    assert result["workspace_path"] == str(target)
    assert any(call[4] == lost_reply for call in calls)
    assert git(source, "rev-parse", branch) == base


def test_cli_preflight_refusal_is_still_no_effect(release_case, monkeypatch, capsys):
    _, _, target, admin, operation, _, _ = release_case
    (admin / "locked").write_text("another owner\n")
    calls = mutation_observer(monkeypatch)
    code = cli.main(["release", "--operation-id", operation, "--lane", "web"])
    output = capsys.readouterr()
    result = json.loads(output.err or output.out)
    assert code == 2 and result["effect"] == "NOT_APPLIED"
    assert calls == [] and target.exists()


def test_duplicate_native_registration_refuses_before_unlock(release_case, monkeypatch):
    source, root, target, admin, operation, _, _ = release_case
    duplicate = admin.parent / "duplicate-native-registration"
    shutil.copytree(admin, duplicate)
    calls = mutation_observer(monkeypatch)
    with pytest.raises(owner.WorkspaceError):
        owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert calls == []
    assert target.exists() and (admin / "locked").exists() and (duplicate / "locked").exists()


@pytest.mark.parametrize("change", ["head", "branch", "lock", "gitfile", "backref", "directory"])
def test_identity_change_after_inspection_preserves_target(release_case, monkeypatch, change):
    source, root, target, admin, operation, _, _ = release_case
    real_inspect = owner.inspect_linked_worktree
    before_inode = target.stat().st_ino

    def inspect_then_change(*args, **kwargs):
        receipt = real_inspect(*args, **kwargs)
        assert receipt.state == "RELEASABLE"
        if change == "head":
            (target / "README.md").write_text("new committed work\n")
            git(target, "add", "README.md")
            git(target, "commit", "-qm", "new owner work")
        elif change == "branch":
            git(target, "checkout", "-qb", "sol/new-owner")
        elif change == "lock":
            (admin / "locked").write_text("mastermind-linked-worktree:v1 operation=new-owner lane=web base=other\n")
        elif change == "gitfile":
            replacement = target / "gitfile.swap"
            replacement.write_bytes((target / ".git").read_bytes())
            replacement.replace(target / ".git")
        elif change == "backref":
            (admin / "gitdir").write_text(str(target.parent / "different" / ".git") + "\n")
        else:
            retained = target.with_name("preserved-original")
            target.rename(retained)
            shutil.copytree(retained, target)
            assert target.stat().st_ino != before_inode
        return receipt

    monkeypatch.setattr(owner, "inspect_linked_worktree", inspect_then_change)
    calls = mutation_observer(monkeypatch)
    with pytest.raises(owner.WorkspaceError):
        owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert calls == [] and target.exists()
    if change == "head":
        assert (target / "README.md").read_text() == "new committed work\n"
    if change == "directory":
        assert target.with_name("preserved-original").exists()


def test_new_ignored_file_after_inspection_is_preserved(release_case, monkeypatch):
    source, root, target, admin, operation, _, _ = release_case
    real_inspect = owner.inspect_linked_worktree
    original_lock = (admin / "locked").read_bytes()

    def inspect_then_write(*args, **kwargs):
        receipt = real_inspect(*args, **kwargs)
        (target / "cache").mkdir()
        (target / "cache" / "important.txt").write_text("not disposable\n")
        return receipt

    monkeypatch.setattr(owner, "inspect_linked_worktree", inspect_then_write)
    calls = mutation_observer(monkeypatch)
    receipt = owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert receipt.state == "PRESERVED_DIRTY" and not receipt.removed
    assert calls == [] and (admin / "locked").read_bytes() == original_lock
    assert (target / "cache" / "important.txt").read_text() == "not disposable\n"


@pytest.mark.parametrize("change", ["ignored", "directory", "foreign_lock", "dangling_lock"])
def test_post_unlock_change_never_removes_or_relocks_a_replacement(release_case, monkeypatch, change):
    source, root, target, admin, operation, _, _ = release_case
    original_lock = (admin / "locked").read_bytes()
    calls = mutation_observer(monkeypatch)
    real_run = owner._run

    def change_after_unlock(argv, **kwargs):
        result = real_run(argv, **kwargs)
        if len(argv) > 4 and list(argv)[3:5] == ["worktree", "unlock"]:
            if change == "ignored":
                (target / "cache").mkdir()
                (target / "cache" / "important.txt").write_text("new work\n")
            elif change == "directory":
                retained = target.with_name("preserved-original")
                target.rename(retained)
                shutil.copytree(retained, target)
            elif change == "foreign_lock":
                (admin / "locked").write_text("another owner\n")
            else:
                (admin / "locked").symlink_to(admin / "missing-lock-target")
        return result

    monkeypatch.setattr(owner, "_run", change_after_unlock)
    with pytest.raises(owner.LinkedWorkspaceReleaseEffectUnknown) as raised:
        owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert raised.value.details["retry_authorized"] is False
    assert target.exists() and not any(call[4] == "remove" for call in calls)
    if change == "ignored":
        assert (admin / "locked").read_bytes() == original_lock
        assert raised.value.details["lock_restoration"] == "ORIGINAL_LOCK_RESTORED"
        assert (target / "cache" / "important.txt").read_text() == "new work\n"
    else:
        assert not any(call[4] == "lock" for call in calls)
    if change == "directory":
        assert target.with_name("preserved-original").exists()
        assert not (admin / "locked").exists()
    if change == "foreign_lock":
        assert (admin / "locked").read_text() == "another owner\n"
    if change == "dangling_lock":
        assert (admin / "locked").is_symlink()


def test_partial_native_removal_stays_unknown_after_original_lock_restoration(release_case, monkeypatch):
    source, root, target, admin, operation, branch, base = release_case
    original_lock = (admin / "locked").read_bytes()
    real_run = owner._run
    attempted = []

    def partially_remove(argv, **kwargs):
        if len(argv) > 4 and list(argv)[3:5] == ["worktree", "remove"]:
            attempted.append(list(argv))
            (target / "README.md").unlink()
            raise owner.WorkspaceError("native removal interrupted after deleting a file")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(owner, "_run", partially_remove)
    with pytest.raises(owner.LinkedWorkspaceReleaseEffectUnknown) as raised:
        owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert len(attempted) == 1 and target.exists() and not (target / "README.md").exists()
    assert (admin / "locked").read_bytes() == original_lock
    assert raised.value.details["lock_restoration"] == "ORIGINAL_LOCK_RESTORED"
    assert raised.value.details["retry_authorized"] is False
    assert git(source, "rev-parse", branch) == base


@pytest.mark.parametrize("alias", ["case", "double_separator"])
def test_native_suffix_aliases_refuse_before_unlock(release_case, monkeypatch, alias):
    source, root, target, admin, operation, _, _ = release_case
    duplicate = admin.parent / "native-suffix-alias"
    shutil.copytree(admin, duplicate)
    native = str(target).swapcase() if alias == "case" else "/other/" + str(target)
    (duplicate / "gitdir").write_text(native + "/.git\n")
    calls = mutation_observer(monkeypatch)
    with pytest.raises(owner.WorkspaceError):
        owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert calls == [] and target.exists()
    assert (admin / "locked").exists() and (duplicate / "locked").exists()


def test_unrelated_registration_between_observations_does_not_block_release(release_case, monkeypatch):
    source, root, target, _, operation, branch, base = release_case
    real_inspect = owner.inspect_linked_worktree
    peers = []

    def inspect_then_register(*args, **kwargs):
        receipt = real_inspect(*args, **kwargs)
        peer = owner.prepare_linked_worktree(source, root, operation_id="new-independent-owner",
            lane="web", base_sha=base, branch="sol/web-new-independent-owner")
        peers.append(Path(peer.workspace_path))
        (peers[0] / "unpublished.txt").write_text("active independent work\n")
        return receipt

    monkeypatch.setattr(owner, "inspect_linked_worktree", inspect_then_register)
    receipt = owner.release_linked_worktree(source, root, target, expected_operation_id=operation)
    assert receipt.removed and not target.exists()
    assert (peers[0] / "unpublished.txt").read_text() == "active independent work\n"
    assert git(source, "rev-parse", branch) == base
