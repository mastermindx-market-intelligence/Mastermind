from __future__ import annotations

import hashlib
import os
import signal
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


def _commission_repository(
    tmp_path: Path,
    source: Path,
    *,
    include_unrelated: bool = True,
) -> tuple[Path, str, str]:
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
    if include_unrelated:
        (repo / "unrelated.txt").write_text(
            "newer source material\n", encoding="utf-8"
        )
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


def _acquiring_plan(
    source: Path,
    commission_sha: str,
    brief: str,
    *,
    max_uncompressed_bytes: int = 1 << 20,
    max_pack_bytes: int = 1 << 20,
) -> workspace.CommissionDependencyPlan:
    return workspace.CommissionDependencyPlan(
        source_repository=source,
        commission_ref=CommissionRef(
            repository="mastermindx-market-intelligence/Mastermind",
            commit=commission_sha,
            path="research/executive_commissions/COMMISSION.md",
            content_sha256=hashlib.sha256(brief.encode("utf-8")).hexdigest(),
        ),
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=max_uncompressed_bytes,
            max_pack_bytes=max_pack_bytes,
            max_cpu_seconds=5,
        ),
        acquire_missing_from_canonical=True,
    )


def test_acquisition_flag_stays_network_inert_when_exact_delta_is_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source, include_unrelated=False)
    plan = _acquiring_plan(commission_source, commission_sha, brief)

    def forbid_acquisition(*args, **kwargs):
        raise AssertionError("local-complete commission attempted network acquisition")

    monkeypatch.setattr(workspace, "_acquire_commission_quarantine", forbid_acquisition)
    receipt = workspace.prepare_credentialless_clone(
        source,
        tmp_path / "workspaces",
        job_id="JOB-COMMISSION-011",
        base_sha=base_sha,
        commission_dependency=plan,
    )

    prepared = Path(receipt.workspace_path)
    assert _git(prepared, "rev-parse", "HEAD") == base_sha
    assert _git(prepared, "remote") == ""
    assert _git(prepared, "cat-file", "-e", f"{commission_sha}^{{commit}}") == ""


def test_missing_delta_acquires_only_in_scrubbed_control_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source, include_unrelated=False)
    _git(commission_source, "config", "uploadpack.allowFilter", "true")
    plan = _acquiring_plan(source, commission_sha, brief)
    monkeypatch.setattr(
        workspace,
        "_canonical_commission_remote_url",
        lambda ref: commission_source.resolve().as_uri(),
    )

    original_prepare = workspace._prepare_commission_dependency
    observed: dict[str, object] = {}

    def inspect_scrubbed_source(destination, *, base_sha, plan, env):
        dependency_source = Path(plan.source_repository)
        observed["source"] = dependency_source
        observed["remote"] = _git(dependency_source, "remote")
        observed["fetch_head"] = (dependency_source / "FETCH_HEAD").exists()
        pack_dir = dependency_source / "objects" / "pack"
        observed["promisor"] = (
            [path.name for path in pack_dir.glob("*.promisor")]
            if pack_dir.is_dir()
            else []
        )
        return original_prepare(
            destination,
            base_sha=base_sha,
            plan=plan,
            env=env,
        )

    monkeypatch.setattr(
        workspace, "_prepare_commission_dependency", inspect_scrubbed_source
    )
    root = tmp_path / "workspaces"
    receipt = workspace.prepare_credentialless_clone(
        source,
        root,
        job_id="JOB-COMMISSION-012",
        base_sha=base_sha,
        commission_dependency=plan,
    )

    prepared = Path(receipt.workspace_path)
    quarantine = Path(observed["source"])
    assert ".commission-acquisition" in quarantine.parts
    assert observed["remote"] == ""
    assert observed["fetch_head"] is False
    assert observed["promisor"] == []
    assert not quarantine.exists()
    assert not (root / ".commission-acquisition").exists()
    assert _git(prepared, "rev-parse", "HEAD") == base_sha
    assert _git(prepared, "remote") == ""
    assert _git(prepared, "show", f"{commission_sha}:{plan.commission_ref.path}") == brief.rstrip("\n")


def test_matching_crash_identity_reconciles_partial_control_construction(
    tmp_path: Path,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source, include_unrelated=False)
    plan = _acquiring_plan(commission_source, commission_sha, brief)
    root = tmp_path / "workspaces"
    root.mkdir(mode=0o700)
    destination = root / "job-commission-013"
    destination.mkdir(mode=0o700)
    (destination / "partial").write_text("partial\n", encoding="utf-8")
    acquisition_root = root / ".commission-acquisition"
    acquisition_root.mkdir(mode=0o700)
    operation = acquisition_root / "job-commission-013"
    operation.mkdir(mode=0o700)
    (operation / "identity").write_bytes(
        workspace._commission_acquisition_identity(
            job_id="JOB-COMMISSION-013",
            base_sha=base_sha,
            ref=plan.commission_ref,
        )
    )

    receipt = workspace.prepare_credentialless_clone(
        source,
        root,
        job_id="JOB-COMMISSION-013",
        base_sha=base_sha,
        commission_dependency=plan,
    )

    assert Path(receipt.workspace_path).is_dir()
    assert not operation.exists()
    assert not (root / ".commission-acquisition").exists()


def test_matching_crash_identity_refuses_final_destination_symlink(
    tmp_path: Path,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(
        tmp_path, source, include_unrelated=False
    )
    plan = _acquiring_plan(commission_source, commission_sha, brief)
    root = tmp_path / "workspaces"
    root.mkdir(mode=0o700)
    victim = root / "victim"
    victim.mkdir(mode=0o700)
    marker = victim / "must-survive"
    marker.write_text("preserve\n", encoding="utf-8")
    destination = root / "job-commission-symlink"
    destination.symlink_to(victim.name, target_is_directory=True)

    acquisition_root = root / ".commission-acquisition"
    acquisition_root.mkdir(mode=0o700)
    operation = acquisition_root / "job-commission-symlink"
    operation.mkdir(mode=0o700)
    (operation / "identity").write_bytes(
        workspace._commission_acquisition_identity(
            job_id="JOB-COMMISSION-SYMLINK",
            base_sha=base_sha,
            ref=plan.commission_ref,
        )
    )

    with pytest.raises(workspace.WorkspaceError, match="ambiguous workspace path"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-SYMLINK",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert destination.is_symlink()
    assert destination.readlink() == Path("victim")
    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert operation.is_dir()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX process crash")
def test_crash_after_workspace_validation_before_commit_remains_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source, include_unrelated=False)
    _git(commission_source, "config", "uploadpack.allowFilter", "true")
    plan = _acquiring_plan(source, commission_sha, brief)
    monkeypatch.setattr(
        workspace,
        "_canonical_commission_remote_url",
        lambda ref: commission_source.resolve().as_uri(),
    )
    root = tmp_path / "workspaces"
    destination = root / "job-commission-crash-gap"
    original_observe = workspace.observe_launch_cleanliness
    original_lstat = Path.lstat
    state = {"workspace_validated": False}

    def mark_workspace_validated(run_git):
        result = original_observe(run_git)
        state["workspace_validated"] = True
        return result

    def crash_before_commit(path: Path):
        if state["workspace_validated"] and path == destination:
            os._exit(73)
        return original_lstat(path)

    monkeypatch.setattr(
        workspace,
        "observe_launch_cleanliness",
        mark_workspace_validated,
    )
    monkeypatch.setattr(Path, "lstat", crash_before_commit)
    pid = os.fork()
    if pid == 0:
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-CRASH-GAP",
            base_sha=base_sha,
            commission_dependency=plan,
        )
        os._exit(72)
    _pid, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 73

    monkeypatch.setattr(Path, "lstat", original_lstat)
    monkeypatch.setattr(
        workspace,
        "observe_launch_cleanliness",
        original_observe,
    )
    receipt = workspace.prepare_credentialless_clone(
        source,
        root,
        job_id="JOB-COMMISSION-CRASH-GAP",
        base_sha=base_sha,
        commission_dependency=plan,
    )

    assert Path(receipt.workspace_path).is_dir()
    assert not (root / ".commission-acquisition").exists()


def test_mismatched_crash_identity_refuses_without_deleting_workspace(
    tmp_path: Path,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source, include_unrelated=False)
    plan = _acquiring_plan(commission_source, commission_sha, brief)
    root = tmp_path / "workspaces"
    root.mkdir(mode=0o700)
    destination = root / "job-commission-014"
    destination.mkdir(mode=0o700)
    marker = destination / "do-not-delete"
    marker.write_text("preserve\n", encoding="utf-8")
    acquisition_root = root / ".commission-acquisition"
    acquisition_root.mkdir(mode=0o700)
    operation = acquisition_root / "job-commission-014"
    operation.mkdir(mode=0o700)
    (operation / "identity").write_bytes(b"wrong-identity\n")

    with pytest.raises(workspace.WorkspaceError, match="identity drifted"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-014",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert operation.exists()


def test_acquisition_pack_bound_refuses_and_discards_all_partial_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source, include_unrelated=False)
    _git(commission_source, "config", "uploadpack.allowFilter", "true")
    plan = _acquiring_plan(
        source,
        commission_sha,
        brief,
        max_pack_bytes=1,
    )
    monkeypatch.setattr(
        workspace,
        "_canonical_commission_remote_url",
        lambda ref: commission_source.resolve().as_uri(),
    )
    root = tmp_path / "workspaces"

    with pytest.raises(workspace.WorkspaceError, match="commission acquisition"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-015",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert not (root / "job-commission-015").exists()
    assert not (root / ".commission-acquisition").exists()


def test_noncanonical_repository_cannot_enable_network_acquisition(
    tmp_path: Path,
) -> None:
    source, _base_sha = _base_repository(tmp_path / "source")
    with pytest.raises(workspace.WorkspaceError, match="repository is not canonical"):
        workspace.CommissionDependencyPlan(
            source_repository=source,
            commission_ref=CommissionRef(
                repository="example/not-mastermind",
                commit="1" * 40,
                path="research/executive_commissions/COMMISSION.md",
                content_sha256="2" * 64,
            ),
            limits=workspace.CommissionDependencyLimits(
                max_objects=8,
                max_metadata_bytes=4096,
                max_uncompressed_bytes=4096,
                max_pack_bytes=4096,
            ),
            acquire_missing_from_canonical=True,
        )


def test_acquisition_bounds_total_uncompressed_object_expansion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source = tmp_path / "commission-source-large"
    subprocess.run(
        ["git", "clone", "-q", str(source), str(commission_source)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _git(commission_source, "config", "user.email", "test@example.com")
    _git(commission_source, "config", "user.name", "Commission Preparation Test")
    _git(commission_source, "config", "uploadpack.allowFilter", "true")
    brief = "# Mission\n\nBound total object expansion.\n"
    target = (
        commission_source
        / "research"
        / "executive_commissions"
        / "COMMISSION.md"
    )
    target.parent.mkdir(parents=True)
    target.write_text(brief, encoding="utf-8")
    (commission_source / "a.bin").write_bytes(b"a" * 700)
    (commission_source / "b.bin").write_bytes(b"b" * 700)
    _git(commission_source, "add", ".")
    _git(commission_source, "commit", "-q", "-m", "large connected delta")
    commission_sha = _git(commission_source, "rev-parse", "HEAD")
    plan = _acquiring_plan(
        source,
        commission_sha,
        brief,
        max_uncompressed_bytes=1024,
        max_pack_bytes=1 << 20,
    )
    monkeypatch.setattr(
        workspace,
        "_canonical_commission_remote_url",
        lambda ref: commission_source.resolve().as_uri(),
    )
    root = tmp_path / "workspaces"

    with pytest.raises(workspace.WorkspaceError, match="bytes exceed limit"):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-016",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert not (root / "job-commission-016").exists()
    assert not (root / ".commission-acquisition").exists()


def test_acquisition_fetch_uses_native_limits_fixed_remote_and_no_proxy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        def wait(self, timeout=None):
            captured["timeout"] = timeout
            return 0

        def kill(self):
            captured["killed"] = True

    def fake_popen(command, **kwargs):
        captured["command"] = list(command)
        captured["env"] = dict(kwargs["env"])
        captured["start_new_session"] = kwargs.get("start_new_session")
        return FakeProcess()

    monkeypatch.setattr(workspace.subprocess, "Popen", fake_popen)
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit="1" * 40,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256="2" * 64,
    )
    limits = workspace.CommissionDependencyLimits(
        max_objects=16,
        max_metadata_bytes=4096,
        max_uncompressed_bytes=8192,
        max_pack_bytes=16384,
        max_cpu_seconds=7,
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "HTTPS_PROXY": "http://should-not-survive.invalid",
        "http_proxy": "http://should-not-survive.invalid",
    }

    workspace._run_canonical_acquisition_fetch(
        tmp_path,
        remote_url="https://github.com/mastermindx-market-intelligence/Mastermind.git",
        ref=ref,
        limits=limits,
        env=env,
    )

    command = captured["command"]
    assert command[:2] == ["/bin/sh", "-c"]
    assert "ulimit -f" in command[2]
    assert "ulimit -t" in command[2]
    assert "http.followRedirects=false" in command
    assert "http.proxy=" in command
    assert "--quiet" in command
    assert "--no-tags" in command
    assert "--no-write-fetch-head" in command
    assert workspace._COMMISSION_ACQUISITION_REMOTE in command
    assert ref.commit in command
    fetch_env = captured["env"]
    assert "HTTPS_PROXY" not in fetch_env
    assert "http_proxy" not in fetch_env
    assert fetch_env["GIT_NO_LAZY_FETCH"] == "1"
    assert fetch_env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert captured["start_new_session"] is True


def test_acquisition_timeout_kills_and_reaps_entire_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {"waits": []}

    class TimedOutProcess:
        pid = 42420
        returncode = None

        def wait(self, timeout=None):
            captured["waits"].append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired("git fetch", timeout)
            self.returncode = -signal.SIGKILL
            return self.returncode

        def kill(self):
            raise AssertionError("timeout must not kill only the parent process")

    def fake_popen(command, **kwargs):
        captured["start_new_session"] = kwargs.get("start_new_session")
        return TimedOutProcess()

    killpg_calls: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(workspace.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        workspace.os,
        "killpg",
        lambda pgid, value: killpg_calls.append((pgid, value)),
    )
    ref = CommissionRef(
        repository="mastermindx-market-intelligence/Mastermind",
        commit="1" * 40,
        path="research/executive_commissions/COMMISSION.md",
        content_sha256="2" * 64,
    )
    limits = workspace.CommissionDependencyLimits(
        max_objects=16,
        max_metadata_bytes=4096,
        max_uncompressed_bytes=8192,
        max_pack_bytes=16384,
        max_cpu_seconds=1,
    )

    with pytest.raises(workspace.WorkspaceError, match="fetch timed out"):
        workspace._run_canonical_acquisition_fetch(
            tmp_path,
            remote_url=(
                "https://github.com/"
                "mastermindx-market-intelligence/Mastermind.git"
            ),
            ref=ref,
            limits=limits,
            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        )

    assert captured["start_new_session"] is True
    assert killpg_calls == [(42420, signal.SIGKILL)]
    assert captured["waits"][-1] is None


def test_broken_local_dependency_source_refuses_without_network_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(tmp_path, source, include_unrelated=False)
    broken_source = tmp_path / "not-a-git-repository"
    broken_source.mkdir()
    plan = _acquiring_plan(broken_source, commission_sha, brief)
    acquisition_calls: list[object] = []

    def forbid_acquisition(*args, **kwargs):
        acquisition_calls.append((args, kwargs))
        raise AssertionError("broken local Git source reached network acquisition")

    monkeypatch.setattr(workspace, "_acquire_commission_quarantine", forbid_acquisition)

    with pytest.raises(
        workspace.WorkspaceError,
        match="local object state is unreadable",
    ):
        workspace.prepare_credentialless_clone(
            source,
            tmp_path / "workspaces",
            job_id="JOB-COMMISSION-017",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert acquisition_calls == []
    assert not (tmp_path / "workspaces" / "job-commission-017").exists()


def test_canonical_acquisition_refuses_unrelated_post_base_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source, commission_sha, brief = _commission_repository(
        tmp_path, source
    )
    _git(commission_source, "config", "uploadpack.allowFilter", "true")
    plan = _acquiring_plan(source, commission_sha, brief)
    monkeypatch.setattr(
        workspace,
        "_canonical_commission_remote_url",
        lambda ref: commission_source.resolve().as_uri(),
    )

    root = tmp_path / "workspaces"
    with pytest.raises(
        workspace.WorkspaceError,
        match="commission.*source scope",
    ):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-SCOPE-UNRELATED",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert not (root / "job-commission-scope-unrelated").exists()
    assert not (root / ".commission-acquisition").exists()


def test_canonical_acquisition_requires_direct_child_of_assigned_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source = tmp_path / "commission-direct-child"
    subprocess.run(
        ["git", "clone", "-q", str(source), str(commission_source)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _git(commission_source, "config", "user.email", "test@example.com")
    _git(commission_source, "config", "user.name", "Commission Scope Test")
    _git(commission_source, "config", "uploadpack.allowFilter", "true")
    target = (
        commission_source
        / "research"
        / "executive_commissions"
        / "COMMISSION.md"
    )
    target.parent.mkdir(parents=True)
    target.write_text("# Draft\n", encoding="utf-8")
    _git(commission_source, "add", str(target.relative_to(commission_source)))
    _git(commission_source, "commit", "-q", "-m", "intermediate commission")
    brief = "# Final mission\n\nUse only the exact immutable brief.\n"
    target.write_text(brief, encoding="utf-8")
    _git(commission_source, "add", str(target.relative_to(commission_source)))
    _git(commission_source, "commit", "-q", "-m", "final commission")
    commission_sha = _git(commission_source, "rev-parse", "HEAD")
    plan = _acquiring_plan(source, commission_sha, brief)
    monkeypatch.setattr(
        workspace,
        "_canonical_commission_remote_url",
        lambda ref: commission_source.resolve().as_uri(),
    )

    root = tmp_path / "workspaces"
    with pytest.raises(
        workspace.WorkspaceError,
        match="direct child",
    ):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-SCOPE-HISTORY",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert not (root / "job-commission-scope-history").exists()
    assert not (root / ".commission-acquisition").exists()


def test_canonical_acquisition_requires_regular_commission_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, base_sha = _base_repository(tmp_path / "source")
    commission_source = tmp_path / "commission-symlink"
    subprocess.run(
        ["git", "clone", "-q", str(source), str(commission_source)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _git(commission_source, "config", "user.email", "test@example.com")
    _git(commission_source, "config", "user.name", "Commission Scope Test")
    _git(commission_source, "config", "uploadpack.allowFilter", "true")
    target = (
        commission_source
        / "research"
        / "executive_commissions"
        / "COMMISSION.md"
    )
    target.parent.mkdir(parents=True)
    link_value = "README.md"
    target.symlink_to(link_value)
    _git(commission_source, "add", str(target.relative_to(commission_source)))
    _git(commission_source, "commit", "-q", "-m", "symlink commission")
    commission_sha = _git(commission_source, "rev-parse", "HEAD")
    plan = workspace.CommissionDependencyPlan(
        source_repository=source,
        commission_ref=CommissionRef(
            repository="mastermindx-market-intelligence/Mastermind",
            commit=commission_sha,
            path="research/executive_commissions/COMMISSION.md",
            content_sha256=hashlib.sha256(link_value.encode()).hexdigest(),
        ),
        limits=workspace.CommissionDependencyLimits(
            max_objects=64,
            max_metadata_bytes=1 << 16,
            max_uncompressed_bytes=1 << 20,
            max_pack_bytes=1 << 20,
            max_cpu_seconds=5,
        ),
        acquire_missing_from_canonical=True,
    )
    monkeypatch.setattr(
        workspace,
        "_canonical_commission_remote_url",
        lambda ref: commission_source.resolve().as_uri(),
    )

    root = tmp_path / "workspaces"
    with pytest.raises(
        workspace.WorkspaceError,
        match="regular file",
    ):
        workspace.prepare_credentialless_clone(
            source,
            root,
            job_id="JOB-COMMISSION-SCOPE-SYMLINK",
            base_sha=base_sha,
            commission_dependency=plan,
        )

    assert not (root / "job-commission-scope-symlink").exists()
    assert not (root / ".commission-acquisition").exists()
