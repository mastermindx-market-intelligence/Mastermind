#!/usr/bin/env python3
"""Host-local sparse worktree helper for 256 GB Mastermind fleet Macs.

This is a storage adapter over Git's own worktree registry, not a scheduler,
lease database, garbage collector, or writer-ownership authority.

The helper deliberately owns only the HOT tier:
- one public blobless source clone per configured repository;
- sparse linked worktrees on the local internal SSD;
- a free-space admission floor;
- Git worktree locks carrying the creating session identity;
- read-only census.

Cold archive and deletion are intentionally NOT implemented here.  Existing
workspace / worktree-GC owners remain responsible for release and reclamation.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "mastermind.mini_worktree/v1"
CONFIG_SCHEMA = "mastermind.mini_worktree_config/v1"
LOCK_PREFIX = "mastermind-mini-hot:v2"
LEGACY_LOCK_PREFIX = "mastermind-mini-hot:v1"
PREPARED_CONFIG_KEY = "mastermind.miniPrepared"
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
EXACT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class MiniWorktreeError(RuntimeError):
    """A mini worktree operation refused before unsafe mutation."""


@dataclasses.dataclass(frozen=True)
class RepoSpec:
    key: str
    url: str
    default_branch: str
    exclude_dirs: tuple[str, ...]
    git_ssh_command_env: str | None = None


@dataclasses.dataclass(frozen=True)
class HostConfig:
    store_root: Path
    hot_root: Path
    min_free_bytes: int
    resume_free_bytes: int
    repos: Mapping[str, RepoSpec]


def _run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = dict(os.environ)
    merged["GIT_TERMINAL_PROMPT"] = "0"
    merged["GIT_OPTIONAL_LOCKS"] = "0"
    if env:
        merged.update(env)
    proc = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        env=merged,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise MiniWorktreeError(f"{' '.join(args)} failed: {detail[:1200]}")
    return proc


def _git(
    root: Path,
    *args: str,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> str:
    proc = _run(("git", "-C", str(root), *args), check=check, env=env)
    return proc.stdout.strip()


def _normal_url(value: str) -> str:
    value = value.strip().rstrip("/")
    return value[:-4] if value.endswith(".git") else value


def load_config(path: Path) -> HostConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise MiniWorktreeError(f"config unreadable: {path}: {exc}") from exc
    if raw.get("schema_version") != CONFIG_SCHEMA:
        raise MiniWorktreeError("unsupported mini worktree config schema")
    store_root = Path(str(raw.get("store_root", ""))).expanduser()
    hot_root = Path(str(raw.get("hot_root", ""))).expanduser()
    if not store_root.is_absolute() or not hot_root.is_absolute():
        raise MiniWorktreeError("store_root and hot_root must be absolute")
    try:
        min_free = int(raw["min_free_bytes"])
        resume_free = int(raw["resume_free_bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MiniWorktreeError("invalid free-space thresholds") from exc
    if min_free < 1 or resume_free < min_free:
        raise MiniWorktreeError("resume_free_bytes must be >= min_free_bytes > 0")
    repos_raw = raw.get("repositories")
    if not isinstance(repos_raw, dict) or not repos_raw:
        raise MiniWorktreeError("repositories must be a non-empty object")
    repos: dict[str, RepoSpec] = {}
    for key, value in repos_raw.items():
        if not isinstance(key, str) or not SAFE_NAME_RE.fullmatch(key):
            raise MiniWorktreeError(f"unsafe repository key: {key!r}")
        if type(value) is not dict or set(value) not in (
            {"url", "default_branch", "exclude_dirs"},
            {"url", "default_branch", "exclude_dirs", "git_ssh_command_env"},
        ):
            raise MiniWorktreeError(f"repository {key} config is invalid")
        url = value.get("url")
        branch = value.get("default_branch")
        excludes = value.get("exclude_dirs", [])
        ssh_env = value.get("git_ssh_command_env")
        if (
            type(url) is not str
            or not url
            or url != url.strip()
            or any(character in url for character in ("\x00", "\n", "\r"))
            or not isinstance(branch, str)
            or not SAFE_NAME_RE.fullmatch(branch)
            or not isinstance(excludes, list)
            or not all(isinstance(item, str) and item and "/" not in item for item in excludes)
            or (ssh_env is not None and (type(ssh_env) is not str or not ENV_NAME_RE.fullmatch(ssh_env)))
        ):
            raise MiniWorktreeError(f"repository {key} config is invalid")
        is_ssh = url.startswith("git@github.com:") or url.startswith("ssh://")
        is_https = url.startswith("https://github.com/")
        if (not is_ssh and not is_https) or (is_ssh != (ssh_env is not None)):
            raise MiniWorktreeError(f"repository {key} remote identity is invalid")
        repos[key] = RepoSpec(
            key,
            url,
            branch,
            tuple(sorted(set(excludes))),
            ssh_env,
        )
    return HostConfig(store_root.resolve(), hot_root.resolve(), min_free, resume_free, repos)


def _free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return int(shutil.disk_usage(probe).free)


def _storage_observation(cfg: HostConfig) -> tuple[dict[str, int | None], str | None]:
    """One read-only observation shared by admission checks and the census."""
    observed: dict[str, int | None] = {}
    failures: list[str] = []
    for label, root in (("HOT", cfg.hot_root), ("STORE", cfg.store_root)):
        try:
            free = _free_bytes(root)
            if type(free) is not int or free < 0:
                raise ValueError("invalid free-space observation")
        except (OSError, ValueError, TypeError, OverflowError):
            observed[label] = None
            failures.insert(0, f"{label}_STORAGE_OBSERVATION_UNAVAILABLE")
            continue
        observed[label] = free
        if free < cfg.min_free_bytes:
            failures.append(f"{label}_STORAGE_LOW_SPACE free={free} floor={cfg.min_free_bytes}")
    return observed, failures[0] if failures else None


def require_free_space(cfg: HostConfig) -> int:
    """Observe both allocation targets; this is not a capacity reservation."""
    observed, failure = _storage_observation(cfg)
    if failure is not None:
        raise MiniWorktreeError(failure)
    free = observed["HOT"]
    if free is None:
        raise MiniWorktreeError("HOT_STORAGE_OBSERVATION_UNAVAILABLE")
    return free


def _repo(cfg: HostConfig, key: str) -> tuple[RepoSpec, Path]:
    try:
        spec = cfg.repos[key]
    except KeyError as exc:
        raise MiniWorktreeError(f"unknown repository key: {key}") from exc
    return spec, cfg.store_root / key


def _repo_remote_env(spec: RepoSpec) -> dict[str, str] | None:
    name = spec.git_ssh_command_env
    if name is None:
        return None
    value = os.environ.get(name)
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or len(value.encode("utf-8")) > 8192
    ):
        raise MiniWorktreeError(
            f"required Git SSH identity is unavailable for repository {spec.key}"
        )
    return {"GIT_SSH_COMMAND": value}


def _verify_store(spec: RepoSpec, store: Path) -> None:
    if not store.is_dir():
        raise MiniWorktreeError(f"source store missing: {store}")
    observed = _git(store, "remote", "get-url", "origin")
    if _normal_url(observed) != _normal_url(spec.url):
        raise MiniWorktreeError(
            f"source store origin mismatch: expected {spec.url}, observed {observed}"
        )
    if _git(store, "rev-parse", "--is-inside-work-tree") != "true":
        raise MiniWorktreeError(f"source store is not a working Git repository: {store}")


def _tracked_top_dirs(
    store: Path,
    ref: str,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    out = _git(store, "ls-tree", "-d", "--name-only", ref, env=env)
    return [line for line in out.splitlines() if line]


def _sparse_include_dirs(
    store: Path,
    spec: RepoSpec,
    ref: str,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    excluded = set(spec.exclude_dirs)
    return [
        name
        for name in _tracked_top_dirs(store, ref, env=env)
        if name not in excluded
    ]


def _apply_sparse_profile(
    worktree: Path,
    include_dirs: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    # Every operation below can materialize promisor objects in a blobless
    # checkout, so private-repository identity must remain attached throughout.
    _git(worktree, "sparse-checkout", "init", "--cone", env=env)
    if include_dirs:
        _git(worktree, "sparse-checkout", "set", *include_dirs, env=env)
    else:
        # Root files only is still a valid sparse profile.
        _git(worktree, "sparse-checkout", "set", env=env)
    _git(worktree, "read-tree", "-mu", "HEAD", env=env)


def bootstrap_repo(cfg: HostConfig, key: str) -> dict[str, Any]:
    spec, store = _repo(cfg, key)
    # Resolve the owner-controlled identity before any clone/directory mutation.
    remote_env = _repo_remote_env(spec)
    free = require_free_space(cfg)
    cfg.store_root.mkdir(parents=True, exist_ok=True)
    created = False
    if not store.exists():
        _run(
            (
                "git",
                "clone",
                "--filter=blob:none",
                "--sparse",
                "--single-branch",
                "--branch",
                spec.default_branch,
                spec.url,
                str(store),
            ),
            env=remote_env,
        )
        created = True
    require_free_space(cfg)
    _verify_store(spec, store)
    status = _git(store, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise MiniWorktreeError(f"source store is dirty; refusing bootstrap mutation: {store}")
    _git(
        store,
        "fetch",
        "--prune",
        "origin",
        spec.default_branch,
        env=remote_env,
    )
    ref = f"refs/remotes/origin/{spec.default_branch}"
    head = _git(store, "rev-parse", "--verify", f"{ref}^{{commit}}", env=remote_env)
    if not EXACT_SHA_RE.fullmatch(head):
        raise MiniWorktreeError("resolved default branch is not an exact commit")
    includes = _sparse_include_dirs(store, spec, ref, env=remote_env)
    require_free_space(cfg)
    if remote_env is None:
        _apply_sparse_profile(store, includes)
    else:
        _apply_sparse_profile(store, includes, env=remote_env)
    free = require_free_space(cfg)
    return {
        "repository": key,
        "store": str(store),
        "created": created,
        "remote_head": head,
        "excluded_dirs": list(spec.exclude_dirs),
        "included_top_dirs": includes,
        "free_bytes": free,
    }


def _porcelain_worktrees(store: Path) -> list[dict[str, str]]:
    out = _git(store, "worktree", "list", "--porcelain")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*out.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, sep, value = line.partition(" ")
        current[key] = value if sep else ""
    return records


def _lexical_path(path: Path) -> Path:
    """Normalize an absolute path without following symlinks."""
    return Path(os.path.abspath(os.fspath(path)))


def _registered_at(store: Path, destination: Path) -> dict[str, str] | None:
    wanted = _lexical_path(destination)
    for record in _porcelain_worktrees(store):
        try:
            candidate = _lexical_path(Path(record["worktree"]))
        except (KeyError, OSError, TypeError, ValueError):
            continue
        if candidate == wanted:
            return record
    return None


def _preparation_is_complete(path: Path, lock_reason: str) -> bool:
    """Read v2 construction proof from Git's existing per-worktree config."""
    try:
        enabled = _run(
            ("git", "-C", str(path), "config", "--bool", "--get", "extensions.worktreeConfig"),
            check=False,
        )
        if enabled.returncode != 0 or enabled.stdout.strip() != "true":
            return False
        marker = _run(
            ("git", "-C", str(path), "config", "--worktree", "--get-all", PREPARED_CONFIG_KEY),
            check=False,
        )
        return marker.returncode == 0 and marker.stdout.splitlines() == [lock_reason]
    except (OSError, MiniWorktreeError):
        return False


def create_worktree(
    cfg: HostConfig,
    key: str,
    name: str,
    session_id: str,
) -> dict[str, Any]:
    if not SAFE_NAME_RE.fullmatch(name):
        raise MiniWorktreeError("unsafe worktree name")
    if not SAFE_NAME_RE.fullmatch(session_id):
        raise MiniWorktreeError("unsafe session id")
    spec, store = _repo(cfg, key)
    destination = cfg.hot_root / key / name
    branch = f"mmx/{key}/{name}"
    lock_reason = f"{LOCK_PREFIX} repo={key} name={name} session={session_id}"
    legacy_lock = f"{LEGACY_LOCK_PREFIX} repo={key} name={name} session={session_id}"

    existing = None
    if store.exists():
        _verify_store(spec, store)
        existing = _registered_at(store, destination)
    if existing is not None:
        observed_branch = existing.get("branch", "").removeprefix("refs/heads/")
        observed_lock = existing.get("locked", "")
        if observed_branch != branch or observed_lock not in {lock_reason, legacy_lock}:
            raise MiniWorktreeError(
                "existing worktree identity does not match this exact session"
            )
        # Resume is local custody recovery, not a new network/bootstrap effect.
        # The registered lexical path is part of identity; never follow a replacement symlink.
        if destination.is_symlink():
            raise MiniWorktreeError("registered workspace path is a symlink; reconcile on this host")
        if not destination.is_dir():
            raise MiniWorktreeError("registered workspace unavailable; reconcile on this host")
        current_head = _git(destination, "rev-parse", "--verify", "HEAD^{commit}")
        if current_head != existing.get("HEAD"):
            raise MiniWorktreeError("registered workspace source moved during resume")
        if observed_lock == lock_reason and not _preparation_is_complete(destination, observed_lock):
            raise MiniWorktreeError("workspace preparation incomplete; reconcile on this host")
        # Legacy v1 acquired its lock only after hydration. Preserve successful
        # old sessions without retrofitting their config or requiring free space.
        lock_reason = observed_lock
        return {
            "repository": key,
            "workspace": str(destination),
            "branch": branch,
            "head": existing.get("HEAD", ""),
            "lock_reason": lock_reason,
            "reused": True,
            "bootstrap": None,
        }
    if os.path.lexists(destination):
        raise MiniWorktreeError(f"destination already exists but is not registered: {destination}")
    bootstrap = bootstrap_repo(cfg, key)
    # Re-resolve after bootstrap and before creating a branch/worktree. A host
    # owner may have revoked the identity while the fetch/materialization ran.
    remote_env = _repo_remote_env(spec)
    require_free_space(cfg)
    destination.parent.mkdir(parents=True, exist_ok=True)
    branch_probe = _run(
        ("git", "-C", str(store), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"),
        check=False,
    )
    if branch_probe.returncode == 0:
        raise MiniWorktreeError(f"local branch already exists without this workspace: {branch}")

    # Freeze the bootstrap snapshot. Another session may advance origin meanwhile.
    # Explicit commissioned-parent acquisition remains with the Workspace owner.
    base_ref = bootstrap["remote_head"]
    if not isinstance(base_ref, str) or not EXACT_SHA_RE.fullmatch(base_ref):
        raise MiniWorktreeError("bootstrap did not supply an exact source commit")
    _git(
        store,
        "worktree",
        "add",
        "--no-checkout",
        "--lock",
        "--reason",
        lock_reason,
        "--no-track",
        "-b",
        branch,
        str(destination),
        base_ref,
        env=remote_env,
    )
    try:
        includes = _sparse_include_dirs(
            store, spec, base_ref, env=remote_env
        )
        if remote_env is None:
            _apply_sparse_profile(destination, includes)
        else:
            _apply_sparse_profile(destination, includes, env=remote_env)
    except BaseException:
        # The v2 lock is already held. Preserve incomplete work for reconciliation.
        raise
    head = _git(destination, "rev-parse", "HEAD")
    registered = _registered_at(store, destination)
    if (
        head != base_ref
        or registered is None
        or registered.get("HEAD") != base_ref
        or registered.get("branch") != f"refs/heads/{branch}"
        or registered.get("locked") != lock_reason
    ):
        raise MiniWorktreeError("prepared workspace identity moved; reconcile on this host")
    require_free_space(cfg)
    # Git owns the existing per-worktree config and lock. This marker proves only
    # completed construction; it grants no writer release or cleanup authority.
    _git(destination, "config", "--worktree", PREPARED_CONFIG_KEY, lock_reason)
    if not _preparation_is_complete(destination, lock_reason):
        raise MiniWorktreeError("workspace preparation incomplete; reconcile on this host")
    return {
        "repository": key,
        "workspace": str(destination),
        "branch": branch,
        "head": head,
        "lock_reason": lock_reason,
        "reused": False,
        "excluded_dirs": list(spec.exclude_dirs),
        "included_top_dirs": includes,
        "bootstrap": bootstrap,
    }


def census(cfg: HostConfig) -> dict[str, Any]:
    observed, failure = _storage_observation(cfg)
    storage_state = (
        "UNKNOWN" if any(value is None for value in observed.values())
        else "LOW_SPACE" if failure is not None else "READY"
    )
    result: dict[str, Any] = {
        "free_bytes": observed["HOT"],
        "store_free_bytes": observed["STORE"],
        "storage": {
            "state": storage_state,
            "new_allocation_allowed": failure is None,
            "reason": failure,
            "reservation": False,
        },
        "floor_bytes": cfg.min_free_bytes,
        "resume_bytes": cfg.resume_free_bytes,
        "repositories": {},
    }
    hot_root = _lexical_path(cfg.hot_root)
    for key in sorted(cfg.repos):
        _, store = _repo(cfg, key)
        if not store.is_dir():
            result["repositories"][key] = {"state": "NOT_BOOTSTRAPPED", "worktrees": []}
            continue
        rows: list[dict[str, Any]] = []
        for record in _porcelain_worktrees(store):
            try:
                path = _lexical_path(Path(record["worktree"]))
                path.relative_to(hot_root)
            except (KeyError, OSError, TypeError, ValueError):
                continue
            status_known = False
            dirty: bool | None = None
            null_reason = "GIT_STATUS_UNAVAILABLE"
            if Path(path).is_symlink():
                null_reason = "WORKTREE_PATH_SYMLINK"
            elif (
                path.is_dir()
                and record.get("locked", "").startswith(LOCK_PREFIX + " ")
                and not _preparation_is_complete(path, record["locked"])
            ):
                null_reason = "WORKTREE_PREPARATION_INCOMPLETE"
            else:
                try:
                    status_result = _run(
                        ("git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"),
                        check=False,
                    )
                    status_known = status_result.returncode == 0
                    dirty = bool(status_result.stdout.strip()) if status_known else None
                except (OSError, MiniWorktreeError):
                    status_known, dirty = False, None
            rows.append(
                {
                    "path": str(path),
                    "head": record.get("HEAD", ""),
                    "branch": record.get("branch", "").removeprefix("refs/heads/"),
                    "lock_reason": record.get("locked", ""),
                    "dirty": dirty,
                    "observation_state": "OBSERVED" if status_known else "UNKNOWN",
                    "null_reason": None if status_known else null_reason,
                }
            )
        state = "READY" if all(row["observation_state"] == "OBSERVED" for row in rows) else "PARTIAL"
        result["repositories"][key] = {"state": state, "worktrees": rows}
    return result


def _emit(action: str, receipt: Any, effect: str) -> int:
    print(
        json.dumps(
            {
                "schema_version": SCHEMA,
                "action": action,
                "effect": effect,
                "receipt": receipt,
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--config",
        default=os.environ.get(
            "MASTERMIND_MINI_WORKTREE_CONFIG",
            str(Path.home() / ".config/mastermind/mini-worktrees.json"),
        ),
    )
    sub = ap.add_subparsers(dest="action", required=True)
    boot = sub.add_parser("bootstrap", help="create/update blobless sparse source stores")
    boot.add_argument("--repo", default="all")
    create = sub.add_parser("create", help="create/reuse one locked sparse hot worktree")
    create.add_argument("--repo", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--session-id", required=True)
    sub.add_parser("census", help="read-only hot-worktree census")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load_config(Path(args.config).expanduser())
        if args.action == "bootstrap":
            keys = sorted(cfg.repos) if args.repo == "all" else [args.repo]
            rows = [bootstrap_repo(cfg, key) for key in keys]
            return _emit("bootstrap", rows, "APPLIED")
        if args.action == "create":
            receipt = create_worktree(cfg, args.repo, args.name, args.session_id)
            return _emit("create", receipt, "NOT_APPLIED" if receipt["reused"] else "APPLIED")
        return _emit("census", census(cfg), "NOT_APPLIED")
    except MiniWorktreeError as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA,
                    "action": getattr(args, "action", "unknown"),
                    # A failed mutating command may already have cloned/fetched/added.
                    # Do not turn a partial failure into permission to retry elsewhere.
                    "effect": "EFFECT_UNKNOWN" if args.action in {"bootstrap", "create"} else "NOT_APPLIED",
                    "reconciliation_required": args.action in {"bootstrap", "create"},
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
