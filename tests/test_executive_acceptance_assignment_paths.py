"""Real filesystem regressions for terminal assignment containment and aliases."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance as subject


@pytest.fixture
def assignment(tmp_path: Path):
    real = tmp_path.resolve() / "real"
    workspace = real / "workspaces" / "proof-current"
    output = real / "runs" / "attempt-1" / "output"
    receipts = real / "receipts"
    workspace.mkdir(parents=True)
    output.mkdir(parents=True)
    receipts.mkdir()
    result = output / "result.json"
    result.write_text("{}")
    alias = tmp_path / "configured"
    alias.symlink_to(real, target_is_directory=True)
    job = {"job_id": "job-1", "current_attempt_id": "attempt-1", "worktree": str(workspace)}
    attempt = {"job_id": "job-1", "attempt_id": "attempt-1", "result_path": str(result), "status": "COMPLETED"}
    return SimpleNamespace(real=real, alias=alias, workspace=workspace, output=output,
                           result=result, receipts=receipts, job=job, attempt=attempt)


def resolve(a):
    return subject._durable_assignment_paths(
        a.job, a.attempt, workspace_root=a.alias / "workspaces", run_root=a.alias / "runs",
    )


@pytest.mark.parametrize("status", ["COMPLETED", "LOST"])
def test_trusted_config_alias_accepts_canonical_durable_paths(assignment, status):
    a = assignment
    a.attempt["status"] = status
    assert resolve(a) == (a.workspace, a.output.parent)


@pytest.mark.parametrize("status", ["COMPLETED", "LOST"])
def test_missing_result_is_valid_only_for_lost_assignment(assignment, status):
    a = assignment
    a.attempt["status"] = status
    a.result.unlink()
    if status == "LOST":
        assert resolve(a) == (a.workspace, a.output.parent)
    else:
        with pytest.raises(subject.AcceptanceError, match="missing"):
            resolve(a)


@pytest.mark.parametrize("kind", ["live-symlink", "dangling-symlink", "directory", "fifo", "hardlink"])
def test_lost_result_cannot_replace_absence_with_invalid_leaf(assignment, kind):
    a = assignment
    a.attempt["status"] = "LOST"
    a.result.unlink()
    target = a.real / "other-result"
    if kind == "live-symlink":
        target.write_text("{}"); a.result.symlink_to(target)
    elif kind == "dangling-symlink":
        a.result.symlink_to(target)
    elif kind == "directory":
        a.result.mkdir()
    elif kind == "fifo":
        os.mkfifo(a.result)
    else:
        target.write_text("{}"); os.link(target, a.result)
    with pytest.raises(subject.AcceptanceError, match="single regular"):
        resolve(a)


@pytest.mark.parametrize("field, spelling", [
    ("worktree", "alias"), ("result_path", "alias"),
    ("worktree", "relative"), ("result_path", "relative"),
    ("worktree", "dotdot"), ("result_path", "dotdot"),
    ("worktree", "double-slash"), ("result_path", "double-slash"),
    ("worktree", "trailing-slash"), ("result_path", "trailing-slash"),
])
def test_durable_paths_are_never_repaired_to_a_canonical_spelling(assignment, field, spelling):
    a = assignment
    row = a.job if field == "worktree" else a.attempt
    original = row[field]
    if spelling == "alias":
        row[field] = original.replace(str(a.real), str(a.alias), 1)
    elif spelling == "relative":
        row[field] = original.lstrip("/")
    elif spelling == "dotdot":
        p = Path(original); row[field] = str(p.parent / ".." / p.parent.name / p.name)
    elif spelling == "double-slash":
        row[field] = original.replace("/real/", "/real//")
    else:
        row[field] = original + "/"
    with pytest.raises(subject.AcceptanceError, match="escaped"):
        resolve(a)


@pytest.mark.parametrize("which", ["workspace", "output"])
def test_assignment_parent_symlink_escape_refuses(assignment, which):
    a = assignment
    outside = a.real / "outside"
    outside.mkdir()
    if which == "workspace":
        a.workspace.rmdir(); a.workspace.symlink_to(outside, target_is_directory=True)
    else:
        a.result.unlink(); a.output.rmdir()
        (outside / "result.json").write_text("{}")
        a.output.symlink_to(outside, target_is_directory=True)
    with pytest.raises(subject.AcceptanceError, match="escaped"):
        resolve(a)


@pytest.mark.parametrize("which", ["nested-workspace", "wrong-attempt", "missing-workspace"])
def test_assignment_must_have_exact_existing_roots(assignment, which):
    a = assignment
    if which == "nested-workspace":
        nested = a.workspace / "nested"; nested.mkdir(); a.job["worktree"] = str(nested)
    elif which == "wrong-attempt":
        a.attempt["attempt_id"] = a.job["current_attempt_id"] = "attempt-2"
    else:
        a.workspace.rmdir()
    with pytest.raises(subject.AcceptanceError, match="escaped"):
        resolve(a)


def test_seal_lookup_uses_canonical_config_root_and_exact_returned_path(assignment, monkeypatch):
    a = assignment
    seal = a.receipts / "attempt-1" / "assignment-seal-receipt.json"
    seal.parent.mkdir(); seal.write_text("{}"); seal.chmod(0o600)
    instance = object.__new__(subject.Acceptance)
    instance.config = {"proof_workspace_root": str(a.alias / "workspaces"),
                       "worker_runs_root": str(a.alias / "runs"),
                       "receipts_root": str(a.alias / "receipts")}
    instance.control_identity = SimpleNamespace(pw_uid=os.getuid())
    instance.worker_group = SimpleNamespace(gr_gid=os.getgid())
    seen = []
    monkeypatch.setattr(subject, "_validate_assignment_seal_payload", lambda payload, **kw: seen.append(kw))
    monkeypatch.setattr(instance, "_raw_worker_path_probe", lambda *args, **kwargs: {"passed": True})
    monkeypatch.setattr(instance, "_write_json", lambda *args: None)
    assert instance._assert_terminal_assignment_boundary(
        a.job, a.attempt, receipt_name="test.json", seal_path=str(seal),
    ) == (a.workspace, a.output.parent)
    assert seen[0]["workspace"] == a.workspace
    with pytest.raises(subject.AcceptanceError, match="seal receipt path drifted"):
        instance._assert_terminal_assignment_boundary(
            a.job, a.attempt, receipt_name="test.json",
            seal_path=str(a.alias / "receipts" / "attempt-1" / seal.name),
        )
