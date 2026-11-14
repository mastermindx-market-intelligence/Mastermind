#!/usr/bin/env python3
"""Linux Claude WorktreeCreate fallback for repositories without their own hook.

Uses Git's existing worktree registry. Does not run in the Fabric worker creation
transaction and must not be installed as a replacement for Fabric's mint helper.
No cleanup, remote fetch, provider calls or source-checkout normalization.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

MIN_FREE_BYTES = 20 * (1024 ** 3)
LOCK_PREFIX = "mastermind-ubuntu-claude-native:v1"
MAX_PROFILE_BYTES = 32 * 1024
MAX_EVENT_BYTES = 16 * 1024


class Refused(RuntimeError):
    pass


def _owned_regular(path: Path, limit: int) -> bytes:
    try:
        if path.is_symlink():
            raise Refused("SYMLINKED_INPUT")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > limit:
            raise Refused("INPUT_SHAPE_OR_OWNER")
        data = path.read_bytes()
        if len(data) > limit:
            raise Refused("INPUT_TOO_LARGE")
        return data
    except OSError as exc:
        raise Refused("INPUT_UNAVAILABLE") from exc


def _project_hook(root: Path) -> bool:
    for name in ("settings.json", "settings.local.json"):
        path = root / ".claude" / name
        if not path.is_file():
            continue
        try:
            raw = json.loads(_owned_regular(path, MAX_PROFILE_BYTES))
            if isinstance(raw, dict) and isinstance(raw.get("hooks"), dict) and raw["hooks"].get("WorktreeCreate"):
                return True
        except (Refused, ValueError, TypeError):
            # Never adopt an uncertain file as proof that another hook owns the mint.
            raise Refused("PROJECT_HOOK_UNQUALIFIED")
    return False


def _defer_to_project(cwd: Path, project: str | None) -> bool:
    roots = []
    if project:
        roots.append(Path(project).expanduser())
    roots.extend([cwd, *cwd.parents])
    seen = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        if _project_hook(root):
            return True
        if (root / ".git").exists():
            break
    return False


def _git_env() -> dict[str, str]:
    # Local worktree operations should never execute inherited Git transport or
    # loader overrides. The source Git config is still a security review input.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k not in (
        "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _git(root: Path, *args: str, allow_failure: bool = False) -> str:
    argv = ["/usr/bin/git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-C", str(root), *args]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=15, env=_git_env())
    if p.returncode and not allow_failure:
        raise Refused("GIT_" + (args[0] if args else "UNKNOWN").upper().replace("-", "_") + "_REFUSED")
    return p.stdout.strip() if p.returncode == 0 else ""


def _safe_ancestry(root: Path, home: Path) -> None:
    try:
        if not root.is_absolute() or root.resolve(strict=True) != root:
            raise Refused("SOURCE_SYMLINK_OR_MISSING")
        if not root.is_relative_to(home):
            raise Refused("SOURCE_OUTSIDE_HOME")
        path = root
        while path != home.parent:
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o022):
                raise Refused("SOURCE_DIRECTORY_CUSTODY")
            if path == home:
                break
            path = path.parent
    except OSError as exc:
        raise Refused("SOURCE_DIRECTORY_UNAVAILABLE") from exc


def _profile(root: Path, commit: str) -> list[str]:
    body = _git(root, "ls-tree", "-d", "--name-only", commit)
    dirs = [s for s in body.splitlines() if s]
    if len(dirs) > 2048 or any("/" in d or d in (".", "..") for d in dirs):
        raise Refused("TREE_INVALID")
    f = root / "config" / "sparse_worktree.json"
    excludes: set[str] = set()
    if f.is_file():
        # An untracked or locally modified profile cannot quietly change the
        # checkout policy for this pinned source commit.
        wanted = _git(root, "rev-parse", "--verify", commit + ":config/sparse_worktree.json")
        current = _git(root, "hash-object", "--", str(f))
        if not re.fullmatch(r"[0-9a-f]{40}", wanted) or current != wanted:
            raise Refused("PROFILE_SOURCE_DRIFT")
        try:
            data = json.loads(_owned_regular(f, MAX_PROFILE_BYTES))
        except (ValueError, TypeError) as exc:
            raise Refused("PROFILE_INVALID") from exc
        if not isinstance(data, dict) or data.get("enabled") is not True:
            raise Refused("PROFILE_DISABLED_OR_INVALID")
        items = data.get("exclude_dirs")
        if (not isinstance(items, list) or len(items) > 40
                or any(not isinstance(s, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", s) is None for s in items)):
            raise Refused("PROFILE_EXCLUDES_INVALID")
        excludes = set(items)
    return [d for d in dirs if d not in excludes]


def _ensure_private_dir(path: Path, parent: Path) -> None:
    if path.exists():
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refused("PRIVATE_DIRECTORY_CUSTODY")
        return
    # The supplied parent has already been owner-checked; any caller racing
    # this mkdir must create the same restricted directory or be refused.
    if not path.parent.samefile(parent):
        raise Refused("PRIVATE_PARENT_MISMATCH")
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    _ensure_private_dir(path, parent)


def _registered(root: Path, destination: Path) -> dict[str, str] | None:
    raw = _git(root, "worktree", "list", "--porcelain")
    for chunk in raw.split("\n\n"):
        row = dict(line.partition(" ")[::2] for line in chunk.splitlines() if line)
        if row.get("worktree") == str(destination):
            return row
    return None


def _create(event: dict, home: Path) -> Path | None:
    if sys.platform != "linux":
        raise Refused("LINUX_ONLY")
    name = event.get("name") or event.get("worktree_name")
    session = event.get("session_id")
    cwd = event.get("cwd")
    if (not isinstance(name, str) or not name.strip() or len(name) > 100
            or not isinstance(session, str) or not session or len(session) > 512
            or not isinstance(cwd, str) or not cwd or len(cwd) > 1024):
        raise Refused("EVENT_IDENTITY_REQUIRED")
    source = Path(cwd).expanduser()
    if _defer_to_project(source, os.environ.get("CLAUDE_PROJECT_DIR")):
        return None
    root_str = _git(source, "rev-parse", "--show-toplevel")
    root = Path(root_str)
    _safe_ancestry(root, home)
    # No remote operations, and do not let a dirty shared donor accidentally
    # qualify as the source of a new native session's branch.
    if _git(root, "status", "--porcelain=v1", "--untracked-files=no"):
        raise Refused("SOURCE_DIRTY")
    commit = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise Refused("HEAD_UNQUALIFIED")
    includes = _profile(root, commit)
    common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    digest = hashlib.sha256((common + "\0" + name + "\0" + session).encode()).hexdigest()
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:48] or "session"
    branch = "claude/ubuntu-" + slug + "-" + digest[:12]
    if not _git(root, "check-ref-format", "--branch", branch):
        # check-ref-format has no stdout for success; the call itself validated it.
        pass
    folder = home / ".claude" / "worktrees" / "mmx-sparse"
    repo_folder = folder / hashlib.sha256(common.encode()).hexdigest()[:16]
    destination = repo_folder / (slug + "-" + digest[:16])
    lock_reason = LOCK_PREFIX + ":" + digest
    for p in (home / ".claude", home / ".claude" / "worktrees", folder):
        if p.is_symlink():
            raise Refused("OUTPUT_SYMLINK")
    if (home / ".claude").is_dir() and (home / ".claude").stat().st_uid != os.getuid():
        raise Refused("CLAUDE_HOME_CUSTODY")
    if not (home / ".claude").exists():
        _ensure_private_dir(home / ".claude", home)
    for p in (home / ".claude" / "worktrees", folder, repo_folder):
        _ensure_private_dir(p, p.parent)
    if destination.is_symlink():
        raise Refused("DESTINATION_SYMLINK")
    if destination.exists():
        row = _registered(root, destination)
        if (row is None or row.get("branch") != "refs/heads/" + branch
                or row.get("locked") != lock_reason
                or _git(destination, "rev-parse", "HEAD") != commit
                or _git(destination, "config", "--get", "core.sparseCheckout") != "true"):
            raise Refused("DESTINATION_FOREIGN_OR_UNQUALIFIED")
        return destination
    if shutil.disk_usage(folder).free < MIN_FREE_BYTES:
        raise Refused("DISK_RESERVE")
    if _git(root, "show-ref", "--verify", "refs/heads/" + branch, allow_failure=True):
        raise Refused("BRANCH_OCCUPIED")
    _git(root, "worktree", "add", "--no-checkout", "--lock", "--reason", lock_reason,
         "--no-track", "-b", branch, str(destination), commit)
    # Once Git has created a worktree, never auto-remove it if a later stage
    # fails. Preserve its exact path, branch and lock for owner reconciliation.
    _git(destination, "sparse-checkout", "init", "--cone")
    _git(destination, "sparse-checkout", "set", "--cone", "--", *includes)
    _git(destination, "read-tree", "-mu", "HEAD")
    row = _registered(root, destination)
    if (row is None or row.get("branch") != "refs/heads/" + branch
            or row.get("locked") != lock_reason or row.get("HEAD") != commit
            or _git(destination, "config", "--get", "core.sparseCheckout") != "true"
            or _git(destination, "status", "--porcelain=v1", "--untracked-files=all")):
        raise Refused("CREATED_WORKTREE_UNQUALIFIED")
    return destination


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
    try:
        if len(raw) > MAX_EVENT_BYTES:
            raise Refused("EVENT_TOO_LARGE")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise Refused("EVENT_NOT_OBJECT")
        destination = _create(event, Path.home().resolve(strict=True))
        if destination is not None:
            print(destination)  # Hook protocol: path only on stdout.
        return 0
    except (Refused, ValueError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        code = str(exc) if isinstance(exc, Refused) else type(exc).__name__.upper()
        print("MMX_UBUNTU_SPARSE_REFUSED:" + code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
