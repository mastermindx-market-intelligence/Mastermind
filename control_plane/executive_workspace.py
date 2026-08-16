"""Credential-free per-job Git workspace preparation for Executive OS.

The supervisor, not the model process, owns workspace creation.  A local clone
copies Git metadata instead of linking to the administrative repository, checks
out one immutable base commit, creates one task branch, and removes every
remote before the worker starts.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
LAUNCH_CLEAN_STATUS_ARGS = (
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
)
LAUNCH_CLEAN_UNTRACKED_ARGS = ("ls-files", "--others", "-z")


class WorkspaceError(RuntimeError):
    """A job workspace could not be prepared without sharing authority."""


class AssignmentSealError(WorkspaceError):
    """A terminal worker assignment could not be made control-private."""


@dataclasses.dataclass(frozen=True)
class LaunchCleanlinessObservation:
    """The one launch-cleanliness definition shared by every boundary."""

    status: bytes
    all_untracked: bytes

    @property
    def dirty(self) -> bool:
        return bool(self.status or self.all_untracked)


def observe_launch_cleanliness(
    run_git: Callable[[Sequence[str]], bytes],
) -> LaunchCleanlinessObservation:
    """Run the worker's exact tracked and all-untracked launch predicate."""

    status = run_git(LAUNCH_CLEAN_STATUS_ARGS)
    all_untracked = run_git(LAUNCH_CLEAN_UNTRACKED_ARGS)
    if not isinstance(status, bytes) or not isinstance(all_untracked, bytes):
        raise TypeError("launch cleanliness Git observations must be bytes")
    return LaunchCleanlinessObservation(status=status, all_untracked=all_untracked)


@dataclasses.dataclass(frozen=True)
class WorkspaceReceipt:
    source_repository: str
    workspace_path: str
    base_sha: str
    branch: str
    remote_count: int
    git_dir_is_private: bool
    workspace_uid: int
    workspace_gid: int
    workspace_mode: int

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def _seal_identity(path: Path, info: os.stat_result) -> dict[str, object]:
    return {
        "path": str(path),
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mode": stat.S_IMODE(info.st_mode),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mtime_ns": int(info.st_mtime_ns),
    }


def seal_control_owned_paths(
    paths: dict[str, str | Path],
    *,
    control_uid: int | None = None,
) -> dict[str, object]:
    """Remove worker traversal at control-owned assignment boundaries.

    Worker-created descendants can remain worker-owned: after the terminal UID
    sweep there are no live worker file descriptors, and mode ``0700`` on each
    control-owned assignment root makes every descendant unreachable to the
    worker principal.  Every requested boundary is attempted even if another
    fails; successful revocations are never rolled back.
    """

    if not paths or any(
        not isinstance(label, str) or not label or not Path(value).is_absolute()
        for label, value in paths.items()
    ):
        raise AssignmentSealError("assignment seal requires named absolute paths")
    expected_uid = os.geteuid() if control_uid is None else int(control_uid)
    canonical_values = [Path(value).resolve(strict=False) for value in paths.values()]
    if len(canonical_values) != len(set(canonical_values)):
        raise AssignmentSealError("assignment seal paths must be distinct")

    sealed: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    for label, raw_path in sorted(paths.items()):
        path = Path(raw_path)
        descriptor: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            before = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != expected_uid
                or stat.S_IMODE(before.st_mode) & 0o007
            ):
                raise AssignmentSealError(
                    f"{label} boundary is not a control-owned protected directory"
                )
            before_identity = _seal_identity(path.resolve(strict=True), before)
            os.fchmod(descriptor, 0o700)
            os.fsync(descriptor)
            after = os.fstat(descriptor)
            after_identity = _seal_identity(path.resolve(strict=True), after)
            stable_fields = ("device", "inode", "uid", "gid")
            if any(
                before_identity[field] != after_identity[field]
                for field in stable_fields
            ) or after_identity["mode"] != 0o700:
                raise AssignmentSealError(f"{label} boundary did not seal to mode 0700")
            sealed[label] = {
                "before": before_identity,
                "after": after_identity,
                "worker_traversal_revoked": True,
            }
        except (AssignmentSealError, OSError) as exc:
            errors.append(f"{label}:{type(exc).__name__}")
        finally:
            if descriptor is not None:
                os.close(descriptor)
    if errors or len(sealed) != len(paths):
        raise AssignmentSealError(
            "terminal assignment seal failed closed: " + ",".join(errors)
        )
    return {
        "schema_version": "mastermind.executive_assignment_seal/v1",
        "sealed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "control_uid": expected_uid,
        "paths": sealed,
        "passed": True,
    }


def _git_env(home: Path) -> dict[str, str]:
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        home.chmod(0o700)
    except OSError:
        pass
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }


def _run(argv: Sequence[str], *, cwd: Path | None, env: dict[str, str]) -> str:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceError(f"workspace command could not run: {argv[0]}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1000:]
        raise WorkspaceError(f"workspace command failed ({completed.returncode}): {detail}")
    return completed.stdout.strip()


def _run_bytes(
    argv: Sequence[str], *, cwd: Path | None, env: dict[str, str]
) -> bytes:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceError(f"workspace command could not run: {argv[0]}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).decode(
            "utf-8", errors="replace"
        ).strip()[-1000:]
        raise WorkspaceError(f"workspace command failed ({completed.returncode}): {detail}")
    return completed.stdout


def _share_symlink_with_group(path: Path, *, shared_gid: int) -> None:
    """Expose only a symlink's payload to the worker group, never its target."""

    try:
        before = path.lstat()
        if not stat.S_ISLNK(before.st_mode):
            raise WorkspaceError("shared symlink preparation received a non-symlink")
        os.chown(path, -1, int(shared_gid), follow_symlinks=False)
        # Darwin applies the creating process's umask to symlink modes.  A
        # control-created 0700 link cannot be read by the worker, and Apple Git
        # then reports the tracked link as modified.  Linux symlinks normally
        # remain 0777, so the chmod is needed only where link modes are real.
        chmod_is_supported = os.chmod in os.supports_follow_symlinks
        desired_mode: int | None = None
        if chmod_is_supported:
            desired_mode = (stat.S_IMODE(before.st_mode) & 0o700) | stat.S_IRGRP
            os.chmod(path, desired_mode, follow_symlinks=False)
        after = path.lstat()
    except (NotImplementedError, OSError) as exc:
        raise WorkspaceError(
            "tracked symlink could not be made read-only for the worker group"
        ) from exc
    mode = stat.S_IMODE(after.st_mode)
    # Linux keeps symlink mode 0777 even when the API accepts
    # follow_symlinks=False; those bits are not enforced there, and the parent
    # directories carry the traversal fence.  Darwin does enforce link modes,
    # so require the exact restrictive postcondition on the production host.
    darwin_mode_invalid = sys.platform == "darwin" and (
        desired_mode is None
        or mode != desired_mode
        or bool(mode & (stat.S_IWGRP | stat.S_IRWXO))
    )
    if (
        after.st_gid != int(shared_gid)
        or not mode & stat.S_IRGRP
        or darwin_mode_invalid
    ):
        raise WorkspaceError(
            "tracked symlink is not read-only for only the worker group"
        )


def _discard_partial_workspace(destination: Path) -> None:
    """Remove a workspace this call created but could not finish.

    ``prepare_credentialless_clone`` refuses a destination that already
    exists, so anything present when preparation fails was created by this
    call and is safe to discard.  Leaving it is not merely wasted space:
    ``git clone`` writes ``HEAD -> refs/heads/.invalid`` and copies objects
    incrementally, so an interrupted clone (the 60 s ``_run`` timeout firing
    on a loaded host, say) leaves a destination that has no resolvable HEAD
    and is missing the base commit.  That corpse then makes the *next*
    preparation for the same job ID fail with "workspace already exists",
    and it keeps the workspace root non-empty -- which the host acceptance
    flow refuses outright, demanding the state be archived before it will
    run at all.  One transient timeout otherwise wedges every later attempt.

    Cleanup never masks the original failure: any error raised while
    discarding is swallowed so the caller still sees the real cause.
    """

    try:
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        elif destination.is_dir():
            shutil.rmtree(destination, ignore_errors=True)
    except OSError:
        pass


def prepare_credentialless_clone(
    source_repository: str | Path,
    workspace_root: str | Path,
    *,
    job_id: str,
    base_sha: str,
    branch: str | None = None,
    shared_gid: int | None = None,
    shared_write_paths: Sequence[str] = (),
) -> WorkspaceReceipt:
    """Create one independent, no-remote clone beneath ``workspace_root``.

    The destination name is derived only from a validated job ID.  Existing
    paths are refused rather than cleaned or overwritten.
    """
    safe_job_id = str(job_id).strip()
    if not _JOB_ID_RE.fullmatch(safe_job_id):
        raise WorkspaceError("job_id is unsafe for a workspace name")
    if shared_write_paths and shared_gid is None:
        raise WorkspaceError("shared_write_paths requires shared_gid")
    normalized_write_paths: list[PurePosixPath] = []
    for raw in shared_write_paths:
        if (
            not isinstance(raw, str)
            or not raw
            or "\\" in raw
            or "\x00" in raw
            or any(character in raw for character in "*?[")
        ):
            raise WorkspaceError("shared write paths must be exact repository-relative paths")
        parsed = PurePosixPath(raw)
        if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
            raise WorkspaceError("shared write paths must be canonical and repository-relative")
        if (
            parsed.parts[0] in {".git", ".codex"}
            or parsed.as_posix() == "config.toml"
            or any(part == ".env" or part.startswith(".env.") for part in parsed.parts)
        ):
            raise WorkspaceError("shared write path targets protected metadata")
        normalized_write_paths.append(parsed)
    if len(normalized_write_paths) != len(
        {path.as_posix() for path in normalized_write_paths}
    ):
        raise WorkspaceError("shared write paths contain duplicates")
    source = Path(source_repository).expanduser().resolve()
    root = Path(workspace_root).expanduser().resolve()
    if not source.is_dir():
        raise WorkspaceError(f"source repository is not a directory: {source}")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = (root / safe_job_id.lower()).resolve()
    if destination.parent != root:
        raise WorkspaceError("workspace destination escaped its assigned root")
    if destination.exists():
        raise WorkspaceError(f"workspace already exists: {destination}")

    selected_branch = branch or f"codex/job-{safe_job_id.lower()}"
    env = _git_env(root / ".supervisor-home")
    _run(["git", "-C", str(source), "rev-parse", "--is-inside-work-tree"], cwd=None, env=env)
    resolved_base = _run(
        ["git", "-C", str(source), "rev-parse", "--verify", f"{base_sha}^{{commit}}"],
        cwd=None,
        env=env,
    )
    _run(["git", "check-ref-format", "--branch", selected_branch], cwd=source, env=env)
    try:
        _run(
            ["git", "clone", "--local", "--no-hardlinks", "--no-checkout", str(source), str(destination)],
            cwd=None,
            env=env,
        )
        _run(["git", "checkout", "--detach", resolved_base], cwd=destination, env=env)
        _run(["git", "switch", "-c", selected_branch], cwd=destination, env=env)
        remotes = _run(["git", "remote"], cwd=destination, env=env).splitlines()
        for remote in remotes:
            if remote.strip():
                _run(["git", "remote", "remove", remote.strip()], cwd=destination, env=env)
        remaining = [line for line in _run(["git", "remote"], cwd=destination, env=env).splitlines() if line]
        actual_base = _run(["git", "rev-parse", "HEAD"], cwd=destination, env=env)
        git_dir = destination / ".git"
        if actual_base != resolved_base or remaining or not git_dir.is_dir():
            raise WorkspaceError("prepared workspace failed its exact-SHA, no-remote self-check")
        if shared_gid is not None:
            for current_root, directory_names, file_names in os.walk(
                destination, topdown=True, followlinks=False
            ):
                current = Path(current_root)
                for candidate in [current, *(current / name for name in directory_names)]:
                    info = candidate.lstat()
                    if stat.S_ISLNK(info.st_mode):
                        _share_symlink_with_group(candidate, shared_gid=int(shared_gid))
                        continue
                    os.chown(candidate, -1, int(shared_gid))
                    os.chmod(candidate, 0o750)
                for name in file_names:
                    candidate = current / name
                    info = candidate.lstat()
                    if stat.S_ISLNK(info.st_mode):
                        _share_symlink_with_group(candidate, shared_gid=int(shared_gid))
                        continue
                    os.chown(candidate, -1, int(shared_gid))
                    original = stat.S_IMODE(info.st_mode)
                    group_execute = 0o010 if original & 0o111 else 0
                    os.chmod(candidate, (original & 0o700) | 0o040 | group_execute)

            for relative in normalized_write_paths:
                current = destination
                for part in relative.parts[:-1]:
                    candidate = current / part
                    if os.path.lexists(candidate):
                        info = candidate.lstat()
                        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                            raise WorkspaceError(
                                "shared write path crosses a non-directory or symlink"
                            )
                    else:
                        candidate.mkdir(mode=0o750)
                    os.chown(candidate, -1, int(shared_gid))
                    os.chmod(candidate, 0o750)
                    current = candidate
                parent = current
                os.chown(parent, -1, int(shared_gid))
                os.chmod(parent, 0o770)
                target = parent / relative.name
                if os.path.lexists(target):
                    info = target.lstat()
                    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                        raise WorkspaceError(
                            "shared write target must be a regular non-symlink file"
                        )
                    original = stat.S_IMODE(info.st_mode)
                    group_execute = 0o010 if original & 0o111 else 0
                    os.chown(target, -1, int(shared_gid))
                    os.chmod(target, (original & 0o700) | 0o060 | group_execute)
        # Observational: do not let `git status` refresh `.git/index` under the
        # control umask after shared-group preparation.  Worker launch then
        # cannot open a 0600 index.  Clone/checkout commands keep the ordinary
        # control Git environment; only this final cleanliness read is locked.
        cleanliness_env = dict(env)
        cleanliness_env["GIT_OPTIONAL_LOCKS"] = "0"
        cleanliness = observe_launch_cleanliness(
            lambda arguments: _run_bytes(
                ["git", *arguments], cwd=destination, env=cleanliness_env
            )
        )
        if cleanliness.dirty:
            raise WorkspaceError(
                "prepared workspace failed the canonical launch cleanliness predicate"
            )
        workspace_info = destination.lstat()
    except BaseException:
        # Any failure past this point leaves a half-written clone that
        # would block every later attempt for this job ID.  Discard it
        # and re-raise the real cause unchanged.
        _discard_partial_workspace(destination)
        raise
    return WorkspaceReceipt(
        source_repository=str(source),
        workspace_path=str(destination),
        base_sha=actual_base,
        branch=selected_branch,
        remote_count=0,
        git_dir_is_private=True,
        workspace_uid=workspace_info.st_uid,
        workspace_gid=workspace_info.st_gid,
        workspace_mode=stat.S_IMODE(workspace_info.st_mode),
    )
