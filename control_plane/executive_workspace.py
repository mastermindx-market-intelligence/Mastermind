"""Git workspace custody for Executive workers and trusted attended sessions.

The supervisor, not the model process, owns workspace creation. Untrusted workers
receive private credentialless clones with distinct Git metadata. Trusted attended
Web/host sessions may instead receive linked worktrees that share only the source
repository object store and remain bound to one explicit operation.
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
from typing import Callable, Mapping, Sequence


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_LINKED_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_LINKED_LANE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_EXACT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LINKED_WORKTREE_LOCK_PREFIX = "mastermind-linked-worktree:v1"
LAUNCH_CLEAN_STATUS_ARGS = (
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
)
LAUNCH_CLEAN_UNTRACKED_ARGS = ("ls-files", "--others", "-z")


class WorkspaceError(RuntimeError):
    """A job workspace could not be prepared without sharing authority."""


class GitHandoffError(WorkspaceError):
    """Shared Git metadata is not a valid control-to-worker handoff."""


class AssignmentSealError(WorkspaceError):
    """A terminal worker assignment could not be made control-private."""


# Filesystem/Git execution states inside the existing workspace lifecycle.
# This is not a database or scheduler state machine.
#
# STATE A — CONTROL_CONSTRUCTION
#   workspace owned and manipulated only by control
#   Git mutation is allowed (clone / checkout / switch / remote-remove)
#
# STATE B — SHARED_HANDOFF
#   control remains owner; worker group receives only reviewed access
#   Git mutation by control is no longer allowed
#   control may observe only; worker may perform its audited preflight
#   worker may write only declared workspace artifact paths and may not write .git
#   Invariant: no control-side Git observation may modify worker-required Git metadata
#
# STATE C — TERMINAL_SEALED
#   workspace root becomes control-private 0700
#   worker traversal revoked; forensic/control observation only
CONTROL_CONSTRUCTION = "CONTROL_CONSTRUCTION"
SHARED_HANDOFF = "SHARED_HANDOFF"
TERMINAL_SEALED = "TERMINAL_SEALED"


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


def git_observation_env(base: Mapping[str, str]) -> dict[str, str]:
    """Return a new mapping that forces post-handoff Git observation read-only.

    Optional Git locks are how Apple Git rewrites ``.git/index`` during an
    otherwise observational ``status``.  After STATE B (SHARED_HANDOFF) that
    rewrite is forbidden: it can recreate the index as mode 0600 under the
    control umask and make the worker unable to open it.  Construction Git
    (clone/checkout/switch) must keep the ordinary control environment.
    """

    result = dict(base)
    result["GIT_OPTIONAL_LOCKS"] = "0"
    return result


def _handoff_lstat(path: Path) -> os.stat_result:
    """Observe one path without following it. Tests may wrap this seam."""

    return path.lstat()


def _require_shared_readonly_node(
    path: Path,
    *,
    label: str,
    control_uid: int,
    shared_gid: int,
    directory: bool,
) -> os.stat_result:
    try:
        info = _handoff_lstat(path)
    except OSError as exc:
        raise GitHandoffError(f"{label} is unavailable for shared Git handoff") from exc
    if stat.S_ISLNK(info.st_mode):
        raise GitHandoffError(f"{label} must not be a symlink")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise GitHandoffError(f"{label} must be a real directory")
        group_ok = bool(info.st_mode & stat.S_IRGRP) and bool(info.st_mode & stat.S_IXGRP)
    else:
        if not stat.S_ISREG(info.st_mode):
            raise GitHandoffError(f"{label} must be a regular file")
        if info.st_nlink != 1:
            raise GitHandoffError(f"{label} must have exactly one link")
        group_ok = bool(info.st_mode & stat.S_IRGRP)
    mode = stat.S_IMODE(info.st_mode)
    if (
        info.st_uid != int(control_uid)
        or info.st_gid != int(shared_gid)
        or not group_ok
        or mode & stat.S_IWGRP
        or mode & stat.S_IRWXO
    ):
        raise GitHandoffError(
            f"{label} is not control-owned, worker-group readable, and unwritable"
        )
    return info


def validate_shared_git_handoff(
    workspace: str | Path,
    *,
    control_uid: int,
    shared_gid: int,
) -> None:
    """Fail closed if STATE B Git metadata is not worker-readable and immutable.

    Observes only. Never chmod/chown. A malformed handoff must not be healed.
    """

    root = Path(workspace)
    _require_shared_readonly_node(
        root,
        label="workspace root",
        control_uid=control_uid,
        shared_gid=shared_gid,
        directory=True,
    )
    git_dir = root / ".git"
    _require_shared_readonly_node(
        git_dir,
        label=".git",
        control_uid=control_uid,
        shared_gid=shared_gid,
        directory=True,
    )
    _require_shared_readonly_node(
        git_dir / "index",
        label=".git/index",
        control_uid=control_uid,
        shared_gid=shared_gid,
        directory=False,
    )
    _require_shared_readonly_node(
        git_dir / "config",
        label=".git/config",
        control_uid=control_uid,
        shared_gid=shared_gid,
        directory=False,
    )
    _require_shared_readonly_node(
        git_dir / "HEAD",
        label=".git/HEAD",
        control_uid=control_uid,
        shared_gid=shared_gid,
        directory=False,
    )
    lock = git_dir / "index.lock"
    try:
        _handoff_lstat(lock)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise GitHandoffError(".git/index.lock could not be observed") from exc
    raise GitHandoffError(".git/index.lock must not exist after shared handoff")


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


@dataclasses.dataclass(frozen=True)
class LinkedWorkspaceReceipt:
    """Custody receipt for a trusted same-principal linked Git worktree.

    Executive workers still require a private credentialless clone. Attended
    Web/host sessions may share only the administrative Git object store.
    """

    source_repository: str
    workspace_root: str
    workspace_path: str
    operation_id: str
    lane: str
    base_sha: str
    head_sha: str
    branch: str
    common_git_dir: str
    lock_reason: str
    reused: bool

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class LinkedWorkspaceReleaseReceipt:
    source_repository: str
    workspace_path: str
    state: str
    head_sha: str
    branch: str
    dirty: bool
    recoverability: str
    removed: bool
    reason: str

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
    # STATE A — CONTROL_CONSTRUCTION: mutating Git is allowed. Do not wrap
    # clone/checkout/switch/remote-remove in the read-only observation env.
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
        # STATE B — SHARED_HANDOFF: DAC sharing is complete. Control Git may
        # observe only. Canonical cleanliness must be measured AFTER sharing
        # (#63) and must not refresh `.git/index` under the control umask (#75).
        cleanliness_env = git_observation_env(env)
        cleanliness = observe_launch_cleanliness(
            lambda arguments: _run_bytes(
                ["git", *arguments], cwd=destination, env=cleanliness_env
            )
        )
        if cleanliness.dirty:
            raise WorkspaceError(
                "prepared workspace failed the canonical launch cleanliness predicate"
            )
        if shared_gid is not None:
            validate_shared_git_handoff(
                destination,
                control_uid=os.geteuid(),
                shared_gid=int(shared_gid),
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


def _common_git_dir(repository: Path, *, env: dict[str, str]) -> Path:
    raw = _run(
        ["git", "-C", str(repository), "rev-parse", "--git-common-dir"],
        cwd=None,
        env=env,
    )
    path = Path(raw)
    if not path.is_absolute():
        path = repository / path
    return path.resolve()


def _worktree_records(source: Path, *, env: dict[str, str]) -> list[dict[str, str]]:
    """Parse ``git worktree list --porcelain`` without inventing new state."""

    output = _run(
        ["git", "-C", str(source), "worktree", "list", "--porcelain"],
        cwd=None,
        env=env,
    )
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, value = line.partition(" ")
        current[key] = value if separator else ""
    return records


def _worktree_record(
    source: Path, destination: Path, *, env: dict[str, str]
) -> dict[str, str] | None:
    wanted = str(destination.resolve())
    for record in _worktree_records(source, env=env):
        raw = record.get("worktree")
        if raw and str(Path(raw).resolve()) == wanted:
            return record
    return None


def _run_status(
    argv: Sequence[str], *, cwd: Path | None, env: dict[str, str]
) -> tuple[int, str, str]:
    """Run a bounded Git predicate where exit 1 can be meaningful."""

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
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _managed_linked_lock_reason(*, operation_id: str, lane: str, base_sha: str) -> str:
    return (
        f"{LINKED_WORKTREE_LOCK_PREFIX} operation={operation_id} "
        f"lane={lane} base={base_sha}"
    )


def _lock_value(reason: str, key: str) -> str | None:
    marker = f"{key}="
    for token in reason.split():
        if token.startswith(marker):
            return token[len(marker) :]
    return None


def _require_linked_identity(
    source: Path,
    destination: Path,
    *,
    env: dict[str, str],
    expected_lock_reason: str | None = None,
) -> tuple[dict[str, str], str, str, Path]:
    record = _worktree_record(source, destination, env=env)
    if record is None:
        raise WorkspaceError("workspace is not registered to the source repository")
    reason = record.get("locked", "")
    if not reason.startswith(LINKED_WORKTREE_LOCK_PREFIX):
        raise WorkspaceError("workspace is not a managed linked worktree")
    if expected_lock_reason is not None and reason != expected_lock_reason:
        raise WorkspaceError("workspace lock identity does not match the requested operation")
    if not destination.is_dir():
        raise WorkspaceError("registered linked workspace path is unavailable")
    dot_git = destination / ".git"
    if not dot_git.is_file():
        raise WorkspaceError("linked workspace must use a worktree .git file")
    source_common = _common_git_dir(source, env=env)
    destination_common = _common_git_dir(destination, env=env)
    if destination_common != source_common:
        raise WorkspaceError("linked workspace does not share the source Git common directory")
    head = _run(["git", "-C", str(destination), "rev-parse", "HEAD"], cwd=None, env=env)
    branch = _run(
        ["git", "-C", str(destination), "branch", "--show-current"], cwd=None, env=env
    )
    return record, head, branch, destination_common


def prepare_linked_worktree(
    source_repository: str | Path,
    workspace_root: str | Path,
    *,
    operation_id: str,
    lane: str,
    base_sha: str,
    branch: str,
    workspace_name: str | None = None,
) -> LinkedWorkspaceReceipt:
    """Acquire one low-storage linked worktree for a trusted attended session.

    The function is idempotent for the same operation/path/branch/base identity.
    It never removes remotes or changes shared repository configuration.  It is
    therefore only for the same authenticated OS principal as the source owner;
    untrusted Executive workers must continue to use ``prepare_credentialless_clone``.
    """

    operation = str(operation_id).strip()
    selected_lane = str(lane).strip().lower()
    selected_base = str(base_sha).strip().lower()
    selected_branch = str(branch).strip()
    name = str(workspace_name or operation).strip().lower()
    if not _LINKED_OPERATION_RE.fullmatch(operation):
        raise WorkspaceError("operation_id is unsafe for linked workspace custody")
    if not _LINKED_LANE_RE.fullmatch(selected_lane):
        raise WorkspaceError("lane is unsafe for linked workspace custody")
    if not _LINKED_OPERATION_RE.fullmatch(name):
        raise WorkspaceError("workspace_name is unsafe for linked workspace custody")
    if not _EXACT_SHA_RE.fullmatch(selected_base):
        raise WorkspaceError("base_sha must be an exact 40-character lowercase commit SHA")

    source = Path(source_repository).expanduser().resolve()
    root = Path(workspace_root).expanduser().resolve()
    if not source.is_dir():
        raise WorkspaceError(f"source repository is not a directory: {source}")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lane_root = (root / selected_lane).resolve()
    if lane_root.parent != root:
        raise WorkspaceError("linked workspace lane escaped its assigned root")
    lane_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = (lane_root / name).resolve()
    if destination.parent != lane_root:
        raise WorkspaceError("linked workspace destination escaped its assigned lane")

    env = _git_env(root / ".control-home")
    _run(["git", "-C", str(source), "rev-parse", "--is-inside-work-tree"], cwd=None, env=env)
    resolved_base = _run(
        ["git", "-C", str(source), "rev-parse", "--verify", f"{selected_base}^{{commit}}"],
        cwd=None,
        env=env,
    ).lower()
    if resolved_base != selected_base:
        raise WorkspaceError("base_sha did not resolve to the exact requested commit")
    _run(["git", "check-ref-format", "--branch", selected_branch], cwd=source, env=env)
    expected_lock = _managed_linked_lock_reason(
        operation_id=operation, lane=selected_lane, base_sha=resolved_base
    )

    if destination.exists():
        _, head, actual_branch, common = _require_linked_identity(
            source, destination, env=env, expected_lock_reason=expected_lock
        )
        if actual_branch != selected_branch:
            raise WorkspaceError("existing linked workspace branch does not match the operation")
        return LinkedWorkspaceReceipt(
            source_repository=str(source),
            workspace_root=str(root),
            workspace_path=str(destination),
            operation_id=operation,
            lane=selected_lane,
            base_sha=resolved_base,
            head_sha=head,
            branch=actual_branch,
            common_git_dir=str(common),
            lock_reason=expected_lock,
            reused=True,
        )

    branch_code, existing_branch, _ = _run_status(
        ["git", "-C", str(source), "rev-parse", "--verify", "--quiet", f"refs/heads/{selected_branch}"],
        cwd=None,
        env=env,
    )
    if branch_code == 0 and existing_branch:
        raise WorkspaceError("linked workspace branch already exists without its bound workspace")
    if branch_code not in {0, 1}:
        raise WorkspaceError("could not determine whether the linked workspace branch exists")

    created = False
    try:
        _run(
            [
                "git",
                "-C",
                str(source),
                "worktree",
                "add",
                "-b",
                selected_branch,
                str(destination),
                resolved_base,
            ],
            cwd=None,
            env=env,
        )
        created = True
        _run(
            [
                "git",
                "-C",
                str(source),
                "worktree",
                "lock",
                "--reason",
                expected_lock,
                str(destination),
            ],
            cwd=None,
            env=env,
        )
        _, head, actual_branch, common = _require_linked_identity(
            source, destination, env=env, expected_lock_reason=expected_lock
        )
        if head.lower() != resolved_base or actual_branch != selected_branch:
            raise WorkspaceError("linked workspace failed its exact base/branch self-check")
        cleanliness = observe_launch_cleanliness(
            lambda arguments: _run_bytes(
                ["git", *arguments],
                cwd=destination,
                env=git_observation_env(env),
            )
        )
        if cleanliness.dirty:
            raise WorkspaceError("linked workspace was not clean immediately after acquisition")
    except BaseException:
        if created:
            _run_status(
                ["git", "-C", str(source), "worktree", "unlock", str(destination)],
                cwd=None,
                env=env,
            )
            _run_status(
                ["git", "-C", str(source), "worktree", "remove", "--force", str(destination)],
                cwd=None,
                env=env,
            )
            branch_code, branch_head, _ = _run_status(
                ["git", "-C", str(source), "rev-parse", f"refs/heads/{selected_branch}"],
                cwd=None,
                env=env,
            )
            if branch_code == 0 and branch_head.lower() == resolved_base:
                _run_status(
                    ["git", "-C", str(source), "branch", "-D", selected_branch],
                    cwd=None,
                    env=env,
                )
        raise

    return LinkedWorkspaceReceipt(
        source_repository=str(source),
        workspace_root=str(root),
        workspace_path=str(destination),
        operation_id=operation,
        lane=selected_lane,
        base_sha=resolved_base,
        head_sha=head,
        branch=actual_branch,
        common_git_dir=str(common),
        lock_reason=expected_lock,
        reused=False,
    )


def inspect_linked_worktree(
    source_repository: str | Path,
    workspace_root: str | Path,
    workspace_path: str | Path,
    *,
    expected_operation_id: str | None = None,
) -> LinkedWorkspaceReleaseReceipt:
    """Classify whether a managed linked worktree can be removed without data loss."""

    source = Path(source_repository).expanduser().resolve()
    root = Path(workspace_root).expanduser().resolve()
    destination = Path(workspace_path).expanduser().resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise WorkspaceError("workspace is outside the managed linked-worktree root") from exc
    if destination == root:
        raise WorkspaceError("managed workspace may not be the workspace root itself")
    env = _git_env(root / ".control-home")
    record, head, branch, _ = _require_linked_identity(source, destination, env=env)
    lock_reason = record.get("locked", "")
    if expected_operation_id is not None:
        observed_operation = _lock_value(lock_reason, "operation")
        if observed_operation != expected_operation_id:
            raise WorkspaceError("workspace operation identity does not match the release request")
    base = _lock_value(lock_reason, "base") or ""
    cleanliness = observe_launch_cleanliness(
        lambda arguments: _run_bytes(
            ["git", *arguments], cwd=destination, env=git_observation_env(env)
        )
    )
    if cleanliness.dirty:
        return LinkedWorkspaceReleaseReceipt(
            source_repository=str(source),
            workspace_path=str(destination),
            state="PRESERVED_DIRTY",
            head_sha=head,
            branch=branch,
            dirty=True,
            recoverability="WORKSPACE_ONLY_CHANGES_PRESENT",
            removed=False,
            reason="tracked or untracked workspace changes are present",
        )

    if head.lower() == base.lower():
        recoverability = "UNCHANGED_FROM_ACQUIRED_BASE"
    else:
        ancestor_code, _, _ = _run_status(
            [
                "git",
                "-C",
                str(source),
                "merge-base",
                "--is-ancestor",
                head,
                "refs/remotes/origin/master",
            ],
            cwd=None,
            env=env,
        )
        remote_head = ""
        if branch:
            remote_code, remote_value, _ = _run_status(
                ["git", "-C", str(source), "rev-parse", f"refs/remotes/origin/{branch}"],
                cwd=None,
                env=env,
            )
            if remote_code == 0:
                remote_head = remote_value
        if ancestor_code == 0:
            recoverability = "HEAD_REACHABLE_FROM_ORIGIN_MASTER"
        elif remote_head.lower() == head.lower():
            recoverability = "HEAD_PUBLISHED_TO_ORIGIN_BRANCH"
        else:
            return LinkedWorkspaceReleaseReceipt(
                source_repository=str(source),
                workspace_path=str(destination),
                state="PRESERVED_UNPUBLISHED",
                head_sha=head,
                branch=branch,
                dirty=False,
                recoverability="LOCAL_HEAD_NOT_RECOVERABLE_FROM_OBSERVED_ORIGIN_REFS",
                removed=False,
                reason="clean workspace has commits not observed on origin/master or origin branch",
            )

    return LinkedWorkspaceReleaseReceipt(
        source_repository=str(source),
        workspace_path=str(destination),
        state="RELEASABLE",
        head_sha=head,
        branch=branch,
        dirty=False,
        recoverability=recoverability,
        removed=False,
        reason="workspace is clean and its HEAD is recoverable without this checkout",
    )


def release_linked_worktree(
    source_repository: str | Path,
    workspace_root: str | Path,
    workspace_path: str | Path,
    *,
    expected_operation_id: str | None = None,
) -> LinkedWorkspaceReleaseReceipt:
    """Remove a managed linked worktree only after fail-closed recoverability checks."""

    inspection = inspect_linked_worktree(
        source_repository,
        workspace_root,
        workspace_path,
        expected_operation_id=expected_operation_id,
    )
    if inspection.state != "RELEASABLE":
        return inspection

    source = Path(source_repository).expanduser().resolve()
    root = Path(workspace_root).expanduser().resolve()
    destination = Path(workspace_path).expanduser().resolve()
    env = _git_env(root / ".control-home")
    record = _worktree_record(source, destination, env=env)
    if record is None:
        raise WorkspaceError("workspace registration disappeared before release")
    original_lock_reason = record.get("locked", "")
    if not original_lock_reason.startswith(LINKED_WORKTREE_LOCK_PREFIX):
        raise WorkspaceError("workspace custody lock disappeared before release")

    _run(
        ["git", "-C", str(source), "worktree", "unlock", str(destination)],
        cwd=None,
        env=env,
    )
    try:
        _run(
            ["git", "-C", str(source), "worktree", "remove", str(destination)],
            cwd=None,
            env=env,
        )
    except BaseException:
        # Preserve the exact original custody identity if removal did not
        # complete. Never synthesize a replacement operation/base on failure.
        if destination.exists():
            _run_status(
                [
                    "git",
                    "-C",
                    str(source),
                    "worktree",
                    "lock",
                    "--reason",
                    original_lock_reason,
                    str(destination),
                ],
                cwd=None,
                env=env,
            )
        raise

    return dataclasses.replace(
        inspection,
        state="REMOVED",
        removed=True,
        reason="clean recoverable linked worktree removed; branch/ref history retained",
    )
