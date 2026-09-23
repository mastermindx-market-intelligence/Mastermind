#!/usr/bin/env python3
"""Install the host-local mini worktree helper and its fixed fleet profile.

This installer is deliberately user-scoped and non-privileged.  It installs no
daemon, scheduler, sweeper, credential, or provider state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

CONFIG_SCHEMA = "mastermind.mini_worktree_config/v1"
INSTALL_SCHEMA = "mastermind.mini_worktree_install/v1"
GIB = 1024 ** 3

REPOSITORIES = {
    "mastermind": {
        "url": "https://github.com/mastermindx-market-intelligence/Mastermind.git",
        "default_branch": "master",
        "exclude_dirs": ["vendor"],
    },
    "macro": {
        "url": "https://github.com/mastermindx-market-intelligence/macro.git",
        "default_branch": "main",
        "exclude_dirs": ["data", "site", "mockups", "verify_shots"],
    },
    "terminal": {
        "url": "https://github.com/mastermindx-market-intelligence/mastermind-terminal.git",
        "default_branch": "master",
        "exclude_dirs": [],
    },
}


class InstallError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _git_sha(source_root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and len(value) == 40 else "unversioned"


def desired_config(home: Path) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA,
        "store_root": str((home / "Projects/MastermindX/repos").resolve()),
        "hot_root": str((home / ".mastermind/worktrees").resolve()),
        "min_free_bytes": 50 * GIB,
        "resume_free_bytes": 70 * GIB,
        "repositories": REPOSITORIES,
    }


def install(
    *,
    source_root: Path,
    home: Path,
    bootstrap: bool,
) -> dict[str, object]:
    helper_source = source_root / "scripts/mini_worktree.py"
    if not helper_source.is_file():
        raise InstallError(f"missing helper source: {helper_source}")
    source_sha = _git_sha(source_root)

    payload_root = home / ".local/share/mastermind/mini-worktree" / source_sha
    helper_target = payload_root / "mini_worktree.py"
    wrapper = home / ".local/bin/mmx-mini-worktree"
    config_path = home / ".config/mastermind/mini-worktrees.json"

    config = desired_config(home)
    config_bytes = (json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8")

    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InstallError(f"existing config is unreadable: {config_path}: {exc}") from exc
        if existing != config:
            raise InstallError(
                f"existing config differs; refusing overwrite without owner reconciliation: {config_path}"
            )
        config_changed = False
    else:
        _atomic_write(config_path, config_bytes, 0o600)
        config_changed = True

    payload_root.mkdir(parents=True, exist_ok=True)
    helper_bytes = helper_source.read_bytes()
    if not helper_target.exists() or helper_target.read_bytes() != helper_bytes:
        _atomic_write(helper_target, helper_bytes, 0o755)
        helper_changed = True
    else:
        helper_changed = False

    wrapper_body = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"exec python3 '{helper_target}' --config '{config_path}' \"$@\"\n"
    ).encode("utf-8")
    if not wrapper.exists() or wrapper.read_bytes() != wrapper_body:
        _atomic_write(wrapper, wrapper_body, 0o755)
        wrapper_changed = True
    else:
        wrapper_changed = False

    bootstrap_receipt = None
    if bootstrap:
        proc = subprocess.run(
            [str(wrapper), "bootstrap", "--repo", "all"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            raise InstallError(
                f"bootstrap failed rc={proc.returncode}: {(proc.stderr or proc.stdout).strip()[:2000]}"
            )
        bootstrap_receipt = json.loads(proc.stdout)

    return {
        "schema_version": INSTALL_SCHEMA,
        "source_sha": source_sha,
        "helper": str(helper_target),
        "helper_sha256": _sha256(helper_target),
        "wrapper": str(wrapper),
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "changes": {
            "config": config_changed,
            "helper": helper_changed,
            "wrapper": wrapper_changed,
        },
        "bootstrap": bootstrap_receipt,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = install(
            source_root=Path(args.source_root).expanduser().resolve(),
            home=Path(args.home).expanduser().resolve(),
            bootstrap=bool(args.bootstrap),
        )
    except InstallError as exc:
        print(json.dumps({"schema_version": INSTALL_SCHEMA, "effect": "NOT_APPLIED", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"schema_version": INSTALL_SCHEMA, "effect": "APPLIED", "receipt": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
