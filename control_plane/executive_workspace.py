"""Credential-free per-job Git workspace preparation for Executive OS.

The supervisor, not the model process, owns workspace creation.  A local clone
copies Git metadata instead of linking to the administrative repository, checks
out one immutable base commit, creates one task branch, and removes every
remote before the worker starts.
"""
from __future__ import annotations

import dataclasses
import os
import re
import subprocess
from pathlib import Path
from typing import Sequence


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class WorkspaceError(RuntimeError):
    """A job workspace could not be prepared without sharing authority."""


@dataclasses.dataclass(frozen=True)
class WorkspaceReceipt:
    source_repository: str
    workspace_path: str
    base_sha: str
    branch: str
    remote_count: int
    git_dir_is_private: bool

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


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


def prepare_credentialless_clone(
    source_repository: str | Path,
    workspace_root: str | Path,
    *,
    job_id: str,
    base_sha: str,
    branch: str | None = None,
) -> WorkspaceReceipt:
    """Create one independent, no-remote clone beneath ``workspace_root``.

    The destination name is derived only from a validated job ID.  Existing
    paths are refused rather than cleaned or overwritten.
    """
    safe_job_id = str(job_id).strip()
    if not _JOB_ID_RE.fullmatch(safe_job_id):
        raise WorkspaceError("job_id is unsafe for a workspace name")
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
    status = _run(["git", "status", "--porcelain=v1"], cwd=destination, env=env)
    git_dir = destination / ".git"
    if actual_base != resolved_base or status or remaining or not git_dir.is_dir():
        raise WorkspaceError("prepared workspace failed its clean, exact-SHA, no-remote self-check")
    return WorkspaceReceipt(
        source_repository=str(source),
        workspace_path=str(destination),
        base_sha=actual_base,
        branch=selected_branch,
        remote_count=0,
        git_dir_is_private=True,
    )
