from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from common.commission_ref import CommissionRef
import control_plane.executive_workspace as workspace


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _base_repository(root: Path) -> tuple[Path, str]:
    root.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "master"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Commission Preparation Test")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD")


def _commission_repository(tmp_path: Path, source: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "commission-source"
    subprocess.run(
        ["git", "clone", "-q", str(source), str(repo)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Commission Preparation Test")
    brief = "# Mission\n\nPerform the exact bounded task.\n"
    target = repo / "research" / "executive_commissions" / "COMMISSION.md"
    target.parent.mkdir(parents=True)
    target.write_text(brief, encoding="utf-8")
    (repo / "unrelated.txt").write_text("newer source material\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "publish commission")
    return repo, _git(repo, "rev-parse", "HEAD"), brief


def test_prepares_bounded_commission_objects_without_moving_workspace_head(
    tmp_path: Path,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
        ),
    )

    receipt = workspace.prepare_credentialless_clone(
        source,
        tmp_path / "workspaces",
        job_id="JOB-COMMISSION-001",
        base_sha=base_sha,
        commission_dependency=plan,
    )

    prepared = Path(receipt.workspace_path)
    assert _git(prepared, "rev-parse", "HEAD") == base_sha
    assert _git(prepared, "remote") == ""
    assert _git(prepared, "cat-file", "-t", commission_sha) == "commit"
    assert _git(prepared, "show", f"{commission_sha}:{ref.path}") == brief.rstrip("\n")
    assert _git(prepared, "status", "--porcelain=v1") == ""



def test_refuses_commission_object_count_over_limit_and_discards_workspace(
    tmp_path: Path,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=1,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
        ),
    )
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="object count exceeds limit"):
        workspace.prepare_credentialless_clone(
            source, root, job_id="JOB-COMMISSION-002",
            base_sha=base_sha, commission_dependency=plan,
        )
    assert not (root / "job-commission-002").exists()



def test_refuses_sparse_pack_with_incomplete_commission_commit_connectivity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
        ),
    )
    sparse_oids = [
        commission_sha,
        _git(commission_source, "rev-parse", f"{commission_sha}^{{tree}}"),
        _git(commission_source, "rev-parse", f"{commission_sha}:research"),
        _git(commission_source, "rev-parse", f"{commission_sha}:research/executive_commissions"),
        _git(commission_source, "rev-parse", f"{commission_sha}:{ref.path}"),
    ]

    original = workspace._run_bounded_bytes_with_input

    def sparse_pack(
        argv,
        *,
        cwd,
        env,
        input_bytes,
        max_stdout_bytes,
        bytes_limit_message,
        max_stdout_lines=None,
        lines_limit_message=None,
    ):
        if "pack-objects" in argv:
            completed = subprocess.run(
                ["git", "pack-objects", "--stdout"],
                cwd=commission_source,
                input=("\n".join(sparse_oids) + "\n").encode("ascii"),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return completed.stdout
        return original(
            argv,
            cwd=cwd,
            env=env,
            input_bytes=input_bytes,
            max_stdout_bytes=max_stdout_bytes,
            bytes_limit_message=bytes_limit_message,
            max_stdout_lines=max_stdout_lines,
            lines_limit_message=lines_limit_message,
        )

    monkeypatch.setattr(workspace, "_run_bounded_bytes_with_input", sparse_pack)
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="connectivity"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-003",
            base_sha=base_sha,
            commission_dependency=plan,
        )
    assert not (root / "job-commission-003").exists()



def test_refuses_commission_preparation_that_changes_destination_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
        ),
    )
    original = workspace._run_bytes_with_input

    def ref_mutating_index_pack(argv, *, cwd, env, input_bytes):
        result = original(argv, cwd=cwd, env=env, input_bytes=input_bytes)
        if "index-pack" in argv:
            destination = Path(argv[argv.index("-C") + 1])
            subprocess.run(
                ["git", "update-ref", "refs/heads/injected", base_sha],
                cwd=destination,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        return result

    monkeypatch.setattr(workspace, "_run_bytes_with_input", ref_mutating_index_pack)
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="refs"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-004",
            base_sha=base_sha,
            commission_dependency=plan,
        )
    assert not (root / "job-commission-004").exists()



def test_refuses_wrong_commission_digest_before_handoff(tmp_path: Path) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, _brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256="0" * 64,
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
        ),
    )
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="digest differs"):
        workspace.prepare_credentialless_clone(
            source, root, job_id="JOB-COMMISSION-005",
            base_sha=base_sha, commission_dependency=plan,
        )
    assert not (root / "job-commission-005").exists()



def test_refuses_oversized_commission_before_reading_blob_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=8,
            max_pack_bytes=1 << 20,
        ),
    )
    original = workspace._run_bytes
    blob_reads = []

    def observe_blob_read(argv, *, cwd, env):
        if "cat-file" in argv and "blob" in argv:
            blob_reads.append(tuple(argv))
        return original(argv, cwd=cwd, env=env)

    monkeypatch.setattr(workspace, "_run_bytes", observe_blob_read)
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="bytes exceed limit"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-006",
            base_sha=base_sha,
            commission_dependency=plan,
        )
    assert blob_reads == []
    assert not (root / "job-commission-006").exists()


def test_refuses_commission_history_outside_assigned_base(tmp_path: Path) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    other, _other_base = _base_repository(tmp_path / "other")
    _git(other, "checkout", "--orphan", "independent")
    for child in other.iterdir():
        if child.name != ".git":
            if child.is_dir():
                import shutil
                shutil.rmtree(child)
            else:
                child.unlink()
    (other / "independent.txt").write_text("unrelated history\n", encoding="utf-8")
    _git(other, "add", ".")
    _git(other, "commit", "-q", "-m", "independent root")
    _git(other, "branch", "-M", "master")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, other)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
        ),
    )
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="does not descend"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-007",
            base_sha=base_sha,
            commission_dependency=plan,
        )
    assert not (root / "job-commission-007").exists()


def test_invalid_commission_plan_refuses_before_workspace_creation(tmp_path: Path) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="plan is invalid"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-008",
            base_sha=base_sha,
            commission_dependency=object(),  # type: ignore[arg-type]
        )
    assert not root.exists()



def test_refuses_object_metadata_over_limit_before_import(tmp_path: Path) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
        ),
    )
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="metadata exceeds limit"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-009",
            base_sha=base_sha,
            commission_dependency=plan,
        )
    assert not (root / "job-commission-009").exists()



def test_pack_generation_uses_bounded_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit=commission_sha,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
    )
    plan = workspace.CommissionDependencyPlan(
        source_repository=commission_source,
        commission_ref=ref,
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=8,
        ),
    )
    original = workspace._run_bytes_with_input

    def forbid_unbounded_pack(argv, *, cwd, env, input_bytes):
        if "pack-objects" in argv:
            raise AssertionError("pack generation used unbounded stdout capture")
        return original(argv, cwd=cwd, env=env, input_bytes=input_bytes)

    monkeypatch.setattr(workspace, "_run_bytes_with_input", forbid_unbounded_pack)
    root = tmp_path / "workspaces"
    with pytest.raises(workspace.WorkspaceError, match="pack exceeds limit"):
        workspace.prepare_credentialless_clone(
            source, root, job_id="JOB-COMMISSION-010",
            base_sha=base_sha, commission_dependency=plan,
        )
    assert not (root / "job-commission-010").exists()
