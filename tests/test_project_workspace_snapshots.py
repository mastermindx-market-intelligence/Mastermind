"""Allocator-only proof: local fixture Git/files, no provider or installed runtime."""
import hashlib
import os
from pathlib import Path
import subprocess

import pytest

from control_plane import executive_workspace as workspace_owner


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True,
        env=workspace_owner.git_observation_env(os.environ)).strip()


def fixture(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "Fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    (source / "src").mkdir()
    (source / "src/result.txt").write_text("initial\n")
    (source / ".gitignore").write_text("ignored.txt\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "fixture base")
    base = git(source, "rev-parse", "HEAD")
    receipt = workspace_owner.prepare_credentialless_clone(source, tmp_path / "workspaces",
        job_id="PROJECT", base_sha=base, branch="codex/project",
        shared_gid=os.getegid(), shared_write_paths=("src/result.txt",))
    workspace = Path(receipt.workspace_path)
    return workspace, base


def terminal(workspace, base, *, seed="a", content="first code result\n"):
    if content is not None:
        (workspace / "src/result.txt").write_text(content)
    seal = workspace_owner.seal_control_owned_paths({"workspace": workspace})
    after = seal["paths"]["workspace"]["after"]
    data = (workspace / "src/result.txt").read_bytes()
    return dict(job_id="JOB-" + seed, attempt_id="ATT-" + seed,
        terminal_receipt_sha256=seed * 64, role="work" if content is not None else "review",
        base_sha=base, head_sha=base,
        artifacts=[] if content is None else [dict(path="src/result.txt",
            sha256=hashlib.sha256(data).hexdigest(), size=len(data))],
        workspace_identity={key: after[key] for key in ("path", "device", "inode", "uid", "gid")})


def handoff(workspace, base, terminals, current=lambda: None):
    return workspace_owner.prepare_project_workspace_handoff(workspace,
        branch="codex/project", root_job_id="JOB-ROOT", base_sha=base,
        terminals=terminals, shared_gid=os.getegid(), current=current)


def test_uncommitted_sealed_artifacts_become_exact_replayable_clean_snapshot(tmp_path):
    workspace, base = fixture(tmp_path)
    first = terminal(workspace, base)
    result = handoff(workspace, base, [first])
    assert result["commit"] != base and git(workspace, "status", "--porcelain") == ""
    assert git(workspace, "show", result["commit"] + ":src/result.txt") == "first code result"
    assert git(workspace, "show", "-s", "--format=%an <%ae>", "HEAD") == (
        "Mastermind workspace service <workspace-snapshot@mastermind.invalid>")
    assert handoff(workspace, base, [first]) == result
    review = terminal(workspace, result["commit"], seed="b", content=None)
    assert handoff(workspace, base, [first, review]) == result
    second = terminal(workspace, result["commit"], seed="c", content="follow-on code\n")
    final = handoff(workspace, base, [first, review, second])
    assert final["snapshot_terminal_digests"] == ["a" * 64, "c" * 64]
    assert git(workspace, "rev-list", "--count", base + "..HEAD") == "2"
    assert git(workspace, "status", "--porcelain") == ""


@pytest.mark.parametrize("fault", ["extra", "ignored", "bytes", "symlink", "hardlink", "mode", "unsealed", "ambiguous", "foreign_commit"])
def test_snapshot_never_adopts_unsealed_or_ambiguous_changes(tmp_path, fault):
    workspace, base = fixture(tmp_path)
    value = terminal(workspace, base)
    values = [value]
    if fault == "extra":
        (workspace / "extra.txt").write_text("unsealed")
    elif fault == "ignored":
        (workspace / "ignored.txt").write_text("unsealed")
    elif fault == "bytes":
        (workspace / "src/result.txt").write_text("unsealed")
    elif fault == "symlink":
        (workspace / "src/result.txt").unlink()
        (workspace / "src/result.txt").symlink_to(tmp_path / "outside")
    elif fault == "hardlink":
        os.link(workspace / "src/result.txt", tmp_path / "outside")
    elif fault == "mode":
        (workspace / "src/result.txt").chmod(0o750)
    elif fault == "unsealed":
        workspace.chmod(0o750)
    elif fault == "ambiguous":
        values.append({**value, "job_id": "OTHER", "terminal_receipt_sha256": "f" * 64})
    else:
        git(workspace, "config", "user.name", "Fixture")
        git(workspace, "config", "user.email", "fixture@example.invalid")
        git(workspace, "add", "src/result.txt")
        git(workspace, "commit", "-qm", "unproven model commit")
    before = git(workspace, "rev-parse", "HEAD")
    with pytest.raises((workspace_owner.WorkspaceError, OSError)):
        handoff(workspace, base, values)
    assert git(workspace, "rev-parse", "HEAD") == before


@pytest.mark.parametrize("added", [False, True])
def test_interrupted_ref_cas_reconciles_original_snapshot_and_index_only(tmp_path, monkeypatch, added):
    workspace, base = fixture(tmp_path)
    value = terminal(workspace, base)
    if added:
        (workspace / "src/result.txt").write_text("initial\n")
        data = b"new verified artifact\n"
        (workspace / "src/added.txt").write_bytes(data)
        value["artifacts"] = [dict(path="src/added.txt", sha256=hashlib.sha256(data).hexdigest(), size=len(data))]
    replace = os.replace
    def lose(source, target):
        if Path(target) == workspace / ".git/index":
            raise OSError("inert crash after original ref CAS")
        return replace(source, target)
    monkeypatch.setattr(os, "replace", lose)
    with pytest.raises(OSError, match="original ref CAS"):
        handoff(workspace, base, [value])
    committed = git(workspace, "rev-parse", "HEAD")
    assert committed != base and workspace.stat().st_mode & 0o777 == 0o700
    monkeypatch.setattr(os, "replace", replace)
    recovered = handoff(workspace, base, [value])
    assert recovered["commit"] == committed
    assert git(workspace, "rev-list", "--count", base + "..HEAD") == "1"
    assert git(workspace, "status", "--porcelain") == ""
    assert handoff(workspace, base, [value]) == recovered


def test_quiescence_or_source_withdrawal_stops_before_ref_cas(tmp_path):
    workspace, base = fixture(tmp_path)
    value = terminal(workspace, base)
    checks = []
    def current():
        checks.append(1)
        if len(checks) == 3:
            raise workspace_owner.WorkspaceError("actual active attempt acquired workspace")
    with pytest.raises(workspace_owner.WorkspaceError, match="active attempt"):
        handoff(workspace, base, [value], current)
    assert git(workspace, "rev-parse", "HEAD") == base
    assert workspace.stat().st_mode & 0o777 == 0o700


def test_snapshot_observation_preserves_shared_index_and_unknown_index_is_refused(tmp_path):
    workspace, base = fixture(tmp_path)
    value = terminal(workspace, base)
    adopted = handoff(workspace, base, [value])
    index = workspace / ".git/index"
    before = index.stat()
    assert workspace_owner._project_changed_paths(workspace, adopted["commit"]) == set()
    after = index.stat()
    assert (before.st_ino, before.st_mode, before.st_mtime_ns) == (
        after.st_ino, after.st_mode, after.st_mtime_ns)
    # Exact working files alone do not authorize replacing an unrelated index.
    terminal(workspace, adopted["commit"], seed="b", content=None)
    other = workspace_owner._project_git(workspace, "hash-object", "-w", "--stdin",
        data=b"unrelated staged object", mutate=True).strip()
    workspace_owner._project_git(workspace, "update-index", "-z", "--index-info",
        data=b"100644 " + other + b"\tsrc/result.txt\0", mutate=True)
    # Git creates its replacement index under the caller's umask (0644 at 022).
    # Restore the fixture's service custody so this exercises unknown contents,
    # rather than the earlier refusal of a world-readable Git control file.
    unknown_index = index.read_bytes()
    index.chmod(before.st_mode & 0o777)
    unknown_before = index.stat()
    assert git(workspace, "rev-parse", ":src/result.txt") == other.decode()
    with pytest.raises(workspace_owner.WorkspaceError, match="original interrupted parent"):
        handoff(workspace, base, [value])
    assert index.read_bytes() == unknown_index
    unknown_after = index.stat()
    assert (unknown_before.st_ino, unknown_before.st_mode, unknown_before.st_mtime_ns) == (
        unknown_after.st_ino, unknown_after.st_mode, unknown_after.st_mtime_ns)
    assert git(workspace, "rev-parse", "HEAD") == adopted["commit"]


def test_snapshot_bounds_cover_every_currently_admitted_descendant_and_repair():
    from control_plane.executive_coo_policy import CooCyclePolicy
    for version in (1, 2):
        policy = CooCyclePolicy.load(version=version)
        # Terminal Jobs, repairs and reviews continue charging the same total.
        assert policy.max_children_total <= workspace_owner.PROJECT_WORKSPACE_MAX_SNAPSHOTS
        assert policy.max_children_total + 1 <= workspace_owner.PROJECT_WORKSPACE_MAX_TERMINALS


def test_git_content_address_corruption_is_refused(tmp_path):
    import zlib
    workspace, base = fixture(tmp_path)
    value = terminal(workspace, base)
    adopted = handoff(workspace, base, [value])
    oid = adopted["commit"]
    loose = workspace / ".git/objects" / oid[:2] / oid[2:]
    raw = zlib.decompress(loose.read_bytes())
    changed = raw.replace(b"workspace-snapshot@", b"workspace-snapshox@")
    assert len(changed) == len(raw) and changed != raw
    loose.write_bytes(zlib.compress(changed))
    # Some Git builds reject the corrupt address during rev-parse itself;
    # others let the allocator independently detect the same hash mismatch.
    with pytest.raises(workspace_owner.WorkspaceError,
                       match="content does not match its address|hash mismatch"):
        workspace_owner.inspect_project_workspace_revision(workspace, branch="codex/project",
            root_job_id="JOB-ROOT", base_sha=base, terminals=[value])
