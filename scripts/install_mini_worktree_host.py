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
from typing import Mapping

CONFIG_SCHEMA = "mastermind.mini_worktree_config/v1"
INSTALL_SCHEMA = "mastermind.mini_worktree_install/v1"
HELPER_SCHEMA = "mastermind.mini_worktree/v1"
MACRO_REMOTE_ENV = "MACRO_GIT_REMOTE"
MACRO_SSH_COMMAND_ENV = "MACRO_GIT_SSH_COMMAND"
GIB = 1024 ** 3

# Public repositories retain fixed source identities. Macro is intentionally
# absent: its private-repository remote and SSH identity must come through the
# accepted host-owner environment seam, never an anonymous literal fallback.
REPOSITORIES = {
    "mastermind": {
        "url": "https://github.com/mastermindx-market-intelligence/Mastermind.git",
        "default_branch": "master",
        "exclude_dirs": ["vendor"],
    },
    "terminal": {
        "url": "https://github.com/mastermindx-market-intelligence/mastermind-terminal.git",
        "default_branch": "master",
        "exclude_dirs": [],
    },
}


class InstallError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        effect: str = "NOT_APPLIED",
        reconciliation_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.effect = effect
        self.reconciliation_required = reconciliation_required


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


def _bounded_environment_value(
    environ: Mapping[str, str],
    name: str,
    *,
    maximum_bytes: int,
) -> str:
    value = environ.get(name)
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or len(value.encode("utf-8")) > maximum_bytes
    ):
        raise InstallError(f"required host-owner environment {name} is unavailable")
    return value


def _macro_repository(environ: Mapping[str, str]) -> dict[str, object]:
    remote = _bounded_environment_value(
        environ, MACRO_REMOTE_ENV, maximum_bytes=2048
    )
    _bounded_environment_value(
        environ, MACRO_SSH_COMMAND_ENV, maximum_bytes=8192
    )
    allowed_remotes = {
        "git@github.com:mastermindx-market-intelligence/macro.git",
        "ssh://git@github.com/mastermindx-market-intelligence/macro.git",
    }
    if remote not in allowed_remotes:
        raise InstallError(
            "MACRO_GIT_REMOTE must name the canonical Macro repository over SSH"
        )
    return {
        "url": remote,
        "default_branch": "main",
        "exclude_dirs": ["data", "site", "mockups", "verify_shots"],
        # Store only the owner-approved environment variable name. The command
        # and key material remain in the host owner's private process context.
        "git_ssh_command_env": MACRO_SSH_COMMAND_ENV,
    }


def desired_config(
    home: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    source = os.environ if environ is None else environ
    repositories = {
        key: dict(value) for key, value in REPOSITORIES.items()
    }
    repositories["macro"] = _macro_repository(source)
    return {
        "schema_version": CONFIG_SCHEMA,
        "store_root": str((home / "Projects/MastermindX/repos").resolve()),
        "hot_root": str((home / ".mastermind/worktrees").resolve()),
        "min_free_bytes": 50 * GIB,
        "resume_free_bytes": 70 * GIB,
        "repositories": repositories,
    }


def _qualified_bootstrap_receipt(
    stdout: str,
    *,
    expected_repositories: set[str],
) -> dict[str, object]:
    try:
        document = json.loads(stdout)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise InstallError(
            "bootstrap returned malformed success evidence",
            effect="EFFECT_UNKNOWN",
            reconciliation_required=True,
        ) from exc
    if (
        type(document) is not dict
        or set(document) != {"schema_version", "action", "effect", "receipt"}
        or document.get("schema_version") != HELPER_SCHEMA
        or document.get("action") != "bootstrap"
        or document.get("effect") != "APPLIED"
        or type(document.get("receipt")) is not list
    ):
        raise InstallError(
            "bootstrap returned unqualified success evidence",
            effect="EFFECT_UNKNOWN",
            reconciliation_required=True,
        )
    expected_row_keys = {
        "repository",
        "store",
        "created",
        "remote_head",
        "excluded_dirs",
        "included_top_dirs",
        "free_bytes",
    }
    observed: list[str] = []
    for row in document["receipt"]:
        if type(row) is not dict or set(row) != expected_row_keys:
            raise InstallError(
                "bootstrap returned unqualified repository evidence",
                effect="EFFECT_UNKNOWN",
                reconciliation_required=True,
            )
        repository = row.get("repository")
        store = row.get("store")
        head = row.get("remote_head")
        excluded = row.get("excluded_dirs")
        included = row.get("included_top_dirs")
        free = row.get("free_bytes")
        if (
            type(repository) is not str
            or type(store) is not str
            or not Path(store).is_absolute()
            or type(row.get("created")) is not bool
            or type(head) is not str
            or len(head) != 40
            or any(character not in "0123456789abcdef" for character in head)
            or type(excluded) is not list
            or type(included) is not list
            or not all(type(value) is str and value for value in excluded + included)
            or type(free) is not int
            or free < 0
        ):
            raise InstallError(
                "bootstrap returned invalid repository evidence",
                effect="EFFECT_UNKNOWN",
                reconciliation_required=True,
            )
        observed.append(repository)
    if len(observed) != len(set(observed)) or set(observed) != expected_repositories:
        raise InstallError(
            "bootstrap success evidence does not cover the configured repositories",
            effect="EFFECT_UNKNOWN",
            reconciliation_required=True,
        )
    return document


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
            # Bootstrap is mutating and may have cloned/fetched before failing.
            # Preserve that uncertainty instead of advertising retry-safe zero effect.
            raise InstallError(
                f"bootstrap failed rc={proc.returncode}: {(proc.stderr or proc.stdout).strip()[:2000]}",
                effect="EFFECT_UNKNOWN",
                reconciliation_required=True,
            )
        bootstrap_receipt = _qualified_bootstrap_receipt(
            proc.stdout,
            expected_repositories=set(config["repositories"]),
        )

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
        payload: dict[str, object] = {
            "schema_version": INSTALL_SCHEMA,
            "effect": exc.effect,
            "error": str(exc),
        }
        if exc.reconciliation_required:
            payload["reconciliation_required"] = True
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"schema_version": INSTALL_SCHEMA, "effect": "APPLIED", "receipt": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
