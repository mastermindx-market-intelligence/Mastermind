"""Fail-closed qualification for the GitHub Codespaces DevBox runtime."""
from __future__ import annotations

import dataclasses
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

_CODESPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")


class CodespacePreflightError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class CodespacePreflight:
    codespace_name: str
    forwarded_host: str
    forwarded_mcp_url: str
    repository: str
    observed_head: str
    repo_root: Path
    state_root: Path
    port: int


def _refuse(message: str) -> None:
    raise CodespacePreflightError(message)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _git(repo: Path, *args: str) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodespacePreflightError("Git observation is unavailable") from exc
    if completed.returncode != 0:
        _refuse("Git observation is unavailable")
    return completed.stdout.strip()


def _exact_repo_root(value: Path | str) -> Path:
    lexical = Path(value).absolute()
    if lexical.is_symlink():
        _refuse("repository root must not be a symlink")
    try:
        info = lexical.lstat()
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise CodespacePreflightError("repository root is unavailable") from exc
    if not stat.S_ISDIR(info.st_mode) or resolved != lexical:
        _refuse("repository root must be an exact real directory")
    observed_root = Path(_git(resolved, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if observed_root != resolved:
        _refuse("repo-root must be the exact Git worktree root")
    return resolved


def _exact_state_root(value: Path | str, *, repo_root: Path) -> Path:
    lexical = Path(value).absolute()
    if lexical.is_symlink():
        _refuse("state root must not be a symlink")
    if lexical.exists():
        try:
            info = lexical.lstat()
            resolved = lexical.resolve(strict=True)
        except OSError as exc:
            raise CodespacePreflightError("state root is unavailable") from exc
        if not stat.S_ISDIR(info.st_mode) or resolved != lexical:
            _refuse("state root must be an exact real directory")
        selected = resolved
    else:
        parent = lexical.parent
        if parent.is_symlink():
            _refuse("state parent must not be a symlink")
        try:
            parent_info = parent.lstat()
            parent_real = parent.resolve(strict=True)
        except OSError as exc:
            raise CodespacePreflightError("state parent must already exist") from exc
        if not stat.S_ISDIR(parent_info.st_mode) or parent_real != parent:
            _refuse("state parent must be an exact real directory")
        selected = parent_real / lexical.name
    if _is_relative_to(selected, repo_root) or _is_relative_to(repo_root, selected):
        _refuse("state root and repository root must be disjoint")
    return selected


def qualify_codespace_environment(
    *,
    repo_root: Path | str,
    state_root: Path | str,
    expected_repository: str,
    port: int,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> CodespacePreflight:
    """Return only owner-safe Codespace facts or fail before service startup."""

    selected_platform = sys.platform if platform_name is None else platform_name
    selected_env = os.environ if env is None else env
    if selected_platform != "linux" or selected_env.get("CODESPACES") != "true":
        _refuse("qualified GitHub Codespaces Linux is required")
    if type(port) is not int or not 1 <= port <= 65535:
        _refuse("port is invalid")
    if type(expected_repository) is not str or _REPOSITORY_RE.fullmatch(expected_repository) is None:
        _refuse("expected repository is invalid")
    if selected_env.get("GITHUB_REPOSITORY") != expected_repository:
        _refuse("Codespace repository identity does not match")

    codespace_name = selected_env.get("CODESPACE_NAME")
    forwarding_domain = selected_env.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    if type(codespace_name) is not str or _CODESPACE_RE.fullmatch(codespace_name) is None:
        _refuse("Codespace name is invalid")
    if type(forwarding_domain) is not str or _DOMAIN_RE.fullmatch(forwarding_domain) is None:
        _refuse("Codespace forwarding domain is invalid")

    repo = _exact_repo_root(repo_root)
    state = _exact_state_root(state_root, repo_root=repo)
    head = _git(repo, "rev-parse", "HEAD")
    if _HEAD_RE.fullmatch(head) is None:
        _refuse("repository HEAD is invalid")

    forwarded_host = f"{codespace_name}-{port}.{forwarding_domain}"
    return CodespacePreflight(
        codespace_name=codespace_name,
        forwarded_host=forwarded_host,
        forwarded_mcp_url=f"https://{forwarded_host}/mcp",
        repository=expected_repository,
        observed_head=head,
        repo_root=repo,
        state_root=state,
        port=port,
    )


__all__ = [
    "CodespacePreflight",
    "CodespacePreflightError",
    "qualify_codespace_environment",
]
