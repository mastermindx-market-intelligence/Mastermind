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
LOCK_PREFIX = "mastermind-mini-hot:v1"
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
EXACT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class MiniWorktreeError(RuntimeError):
    """A mini worktree operation refused before unsafe mutation."""


@dataclasses.dataclass(frozen=True)
class RepoSpec:
    key: str
    url: str
    default_branch: str
    exclude_dirs: tuple[str, ...]


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


def _git(root: Path, *args: str, check: bool = True) -> str:
    proc = _run(("git", "-C", str(root), *args), check=check)
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
        if not isinstance(value, dict):
            raise MiniWorktreeError(f"repository {key} config is invalid")
        url = value.get("url")
        branch = value.get("default_branch")
        excludes = value.get("exclude_dirs", [])
        if (
            not isinstance(url, str)
            or not url.startswith("https://github.com/")
            or not isinstance(branch, str)
            or not SAFE_NAME_RE.fullmatch(branch)
            or not isinstance(excludes, list)
            or not all(isinstance(item, str) and item and "/" not in item for item in excludes)
        ):
            raise MiniWorktreeError(f"repository {key} config is invalid")
        repos[key] = RepoSpec(key, url, branch, tuple(sorted(set(excludes))))
    return HostConfig(store_root.resolve(), hot_root.resolve(), min_free, resume_free, repos)


def _free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return int(shutil.disk_usage(probe).free)


def require_free_space(cfg: HostConfig) -> int:
    free = _free_bytes(cfg.hot_root)
    if free < cfg.min_free_bytes:
        raise MiniWorktreeError(
            f"HOT_STORAGE_LOW_SPACE free={free} floor={cfg.min_free_bytes}"
        )
    return free


def _repo(cfg: HostConfig, key: str) -> tuple[RepoSpec, Path]:
    try:
        spec = cfg.repos[key]
    except KeyError as exc:
        raise MiniWorktreeError(f"unknown repository key: {key}") from exc
    return spec, cfg.store_root / key


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


def _tracked_top_dirs(store: Path, ref: str) -> list[str]:
    out = _git(store, "ls-tree", "-d", "--name-only", ref)
    return [line for line in out.splitlines() if line]


def _sparse_include_dirs(store: Path, spec: RepoSpec, ref: str) -> list[str]:
    excluded = set(spec.exclude_dirs)
    return [name for name in _tracked_top_dirs(store, ref) if name not in excluded]


def _apply_sparse_profile(worktree: Path, include_dirs: Sequence[str]) -> None:
    _git(worktree, "sparse-checkout", "init", "--cone")
    if include_dirs:
        _git(worktree, "sparse-checkout", "set", *include_dirs)
    else:
        # Root files only is still a valid sparse profile.
        _git(worktree, "sparse-checkout", "set")
    _git(worktree, "read-tree", "-mu", "HEAD")


def bootstrap_repo(cfg: HostConfig, key: str) -> dict[str, Any]:
    spec, store = _repo(cfg, key)
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
            )
        )
        created = True
    _verify_store(spec, store)
    status = _git(store, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise MiniWorktreeError(f"source store is dirty; refusing bootstrap mutation: {store}")
    _git(store, "fetch", "--prune", "origin", spec.default_branch)
    ref = f"refs/remotes/origin/{spec.default_branch}"
    head = _git(store, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not EXACT_SHA_RE.fullmatch(head):
        raise MiniWorktreeError("resolved default branch is not an exact commit")
    includes = _sparse_include_dirs(store, spec, ref)
    _apply_sparse_profile(store, includes)
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


def _registered_at(store: Path, destination: Path) -> dict[str, str] | None:
    wanted = destination.resolve()
    for record in _porcelain_worktrees(store):
        try:
            candidate = Path(record["worktree"]).resolve()
        except (KeyError, OSError):
            continue
        if candidate == wanted:
            return record
    return None


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
    bootstrap = bootstrap_repo(cfg, key)
    spec, store = _repo(cfg, key)
    destination = cfg.hot_root / key / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    branch = f"mmx/{key}/{name}"
    lock_reason = (
        f"{LOCK_PREFIX} repo={key} name={name} session={session_id}"
    )

    existing = _registered_at(store, destination)
    if existing is not None:
        observed_branch = existing.get("branch", "").removeprefix("refs/heads/")
        if observed_branch != branch or existing.get("locked", "") != lock_reason:
            raise MiniWorktreeError(
                "existing worktree identity does not match this exact session"
            )
        return {
            "repository": key,
            "workspace": str(destination),
            "branch": branch,
            "head": existing.get("HEAD", ""),
            "lock_reason": lock_reason,
            "reused": True,
            "bootstrap": bootstrap,
        }
    if os.path.lexists(destination):
        raise MiniWorktreeError(f"destination already exists but is not registered: {destination}")
    ref_check = _git(store, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    if ref_check:
        # _git returns stdout only; quiet success is "", so use subprocess status.
        pass
    branch_probe = _run(
        ("git", "-C", str(store), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"),
        check=False,
    )
    if branch_probe.returncode == 0:
        raise MiniWorktreeError(f"local branch already exists without this workspace: {branch}")

    base_ref = f"refs/remotes/origin/{spec.default_branch}"
    _git(
        store,
        "worktree",
        "add",
        "--no-checkout",
        "--no-track",
        "-b",
        branch,
        str(destination),
        base_ref,
    )
    try:
        includes = _sparse_include_dirs(store, spec, base_ref)
        _apply_sparse_profile(destination, includes)
        _git(store, "worktree", "lock", "--reason", lock_reason, str(destination))
    except BaseException:
        # Never force-remove a partially-created carrier.  Preserve for inspection.
        raise
    head = _git(destination, "rev-parse", "HEAD")
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
    result: dict[str, Any] = {
        "free_bytes": _free_bytes(cfg.hot_root),
        "floor_bytes": cfg.min_free_bytes,
        "resume_bytes": cfg.resume_free_bytes,
        "repositories": {},
    }
    hot_root = cfg.hot_root.resolve()
    for key in sorted(cfg.repos):
        _, store = _repo(cfg, key)
        if not store.is_dir():
            result["repositories"][key] = {"state": "NOT_BOOTSTRAPPED", "worktrees": []}
            continue
        rows: list[dict[str, Any]] = []
        for record in _porcelain_worktrees(store):
            path = Path(record["worktree"]).resolve()
            try:
                path.relative_to(hot_root)
            except ValueError:
                continue
            status = _git(path, "status", "--porcelain=v1", "--untracked-files=all", check=False)
            rows.append(
                {
                    "path": str(path),
                    "head": record.get("HEAD", ""),
                    "branch": record.get("branch", "").removeprefix("refs/heads/"),
                    "lock_reason": record.get("locked", ""),
                    "dirty": bool(status),
                }
            )
        result["repositories"][key] = {"state": "READY", "worktrees": rows}
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
            return _emit("bootstrap", rows, "APPLIED" if any(row["created"] for row in rows) else "NOT_APPLIED")
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
                    "effect": "NOT_APPLIED",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
