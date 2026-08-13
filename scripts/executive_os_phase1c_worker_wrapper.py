"""Drop launchd's inherited root groups before entering the worker broker.

Darwin's ``InitGroups=false`` suppresses ``initgroups(3)``; it does not clear
the supplementary groups inherited from system launchd.  This fixed-purpose
wrapper therefore starts as root, validates the root-owned worker policy,
clears the group vector, irreversibly selects the dedicated worker UID/GID,
and immediately execs the unprivileged broker.  No Job input or arbitrary
command is accepted at this boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "control_uid",
        "worker_uid",
        "worker_gid",
        "worker_user",
        "worker_id",
        "workspace_root",
        "run_root",
        "provider_home",
        "codex_binary",
        "allowed_codex_versions",
        "required_team_identifier",
        "launchd_socket_name",
        "uid_sweep_receipt",
        "require_secret_canary",
    }
)
_CONFIG_SCHEMA_VERSION = "mastermind.executive_worker_broker_config/v1"
_WORKER_USER = "_mastermind_worker"
_MAX_CONFIG_BYTES = 64 * 1024


class WorkerWrapperError(RuntimeError):
    """The privileged transition contract is unsafe or incomplete."""


@dataclass(frozen=True)
class WorkerDropPolicy:
    uid: int
    gid: int
    home: Path
    config: Path
    release: Path
    python: Path
    entrypoint: Path


def _trusted_regular_file(
    path: Path,
    *,
    owner_uid: int,
    group_gid: int | None = None,
    exact_mode: int | None = None,
) -> os.stat_result:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != owner_uid
        or (group_gid is not None and info.st_gid != group_gid)
        or (exact_mode is not None and stat.S_IMODE(info.st_mode) != exact_mode)
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise WorkerWrapperError("trusted worker input metadata differs")
    return info


def load_drop_policy(
    config_path: Path,
    release: Path,
    *,
    trusted_root_uid: int = 0,
    account_lookup: Callable[[str], pwd.struct_passwd] = pwd.getpwnam,
    wrapper_path: Path | None = None,
    python_path: Path | None = None,
) -> WorkerDropPolicy:
    """Validate the only root-authoritative inputs before selecting a UID."""

    config_path = Path(config_path)
    release = Path(release)
    if not config_path.is_absolute() or not release.is_absolute():
        raise WorkerWrapperError("worker wrapper paths must be absolute")
    release_info = release.lstat()
    if (
        stat.S_ISLNK(release_info.st_mode)
        or not stat.S_ISDIR(release_info.st_mode)
        or release_info.st_uid != trusted_root_uid
        or stat.S_IMODE(release_info.st_mode) & 0o022
    ):
        raise WorkerWrapperError("installed release root is not trusted")

    preliminary = config_path.lstat()
    if preliminary.st_size > _MAX_CONFIG_BYTES:
        raise WorkerWrapperError("worker config exceeds its size limit")
    _trusted_regular_file(config_path, owner_uid=trusted_root_uid, exact_mode=0o440)
    try:
        raw = config_path.read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkerWrapperError("worker config is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != _CONFIG_FIELDS:
        raise WorkerWrapperError("worker config fields differ")
    if value.get("schema_version") != _CONFIG_SCHEMA_VERSION:
        raise WorkerWrapperError("worker config schema differs")
    if value.get("worker_user") != _WORKER_USER:
        raise WorkerWrapperError("worker account name differs")
    uid = value.get("worker_uid")
    gid = value.get("worker_gid")
    control_uid = value.get("control_uid")
    if (
        type(uid) is not int
        or type(gid) is not int
        or type(control_uid) is not int
        or uid <= 0
        or gid <= 0
        or control_uid <= 0
        or uid == control_uid
    ):
        raise WorkerWrapperError("worker principal identifiers differ")
    _trusted_regular_file(
        config_path,
        owner_uid=trusted_root_uid,
        group_gid=gid,
        exact_mode=0o440,
    )

    account = account_lookup(_WORKER_USER)
    home_value = value.get("provider_home")
    if (
        account.pw_uid != uid
        or account.pw_gid != gid
        or account.pw_shell != "/usr/bin/false"
        or not isinstance(home_value, str)
        or not Path(home_value).is_absolute()
        or account.pw_dir != home_value
    ):
        raise WorkerWrapperError("worker directory identity differs")
    home = Path(home_value)
    home_info = home.lstat()
    if (
        stat.S_ISLNK(home_info.st_mode)
        or not stat.S_ISDIR(home_info.st_mode)
        or home_info.st_uid != uid
        or home_info.st_gid != gid
        or stat.S_IMODE(home_info.st_mode) != 0o700
    ):
        raise WorkerWrapperError("worker provider home differs")

    manifest = release / ".executive-release-manifest.json"
    _trusted_regular_file(manifest, owner_uid=trusted_root_uid)
    wrapper = Path(__file__).resolve(strict=True) if wrapper_path is None else wrapper_path
    python = Path(sys.executable).resolve(strict=True) if python_path is None else python_path
    _trusted_regular_file(wrapper, owner_uid=trusted_root_uid)
    python_info = _trusted_regular_file(python, owner_uid=trusted_root_uid)
    if not stat.S_IMODE(python_info.st_mode) & 0o111:
        raise WorkerWrapperError("trusted Python executable is not executable")
    entrypoint = release / "scripts" / "executive_os_phase1c_worker.py"
    _trusted_regular_file(entrypoint, owner_uid=trusted_root_uid)
    return WorkerDropPolicy(
        uid=uid,
        gid=gid,
        home=home,
        config=config_path,
        release=release,
        python=python,
        entrypoint=entrypoint,
    )


def drop_worker_privileges(uid: int, gid: int) -> None:
    """Clear inherited groups before irreversibly dropping root authority."""

    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    if (
        os.getuid() != uid
        or os.geteuid() != uid
        or os.getgid() != gid
        or os.getegid() != gid
        or os.getgroups()
    ):
        raise WorkerWrapperError("worker privilege drop did not reach the exact principal")
    try:
        os.setgroups([gid])
    except PermissionError:
        pass
    else:
        raise WorkerWrapperError("worker retained supplementary-group authority")
    try:
        os.setuid(0)
    except PermissionError:
        pass
    else:
        raise WorkerWrapperError("worker retained root authority")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if any(value != 0 for value in (os.getuid(), os.geteuid(), os.getgid(), os.getegid())):
            raise WorkerWrapperError("worker wrapper must begin as root")
        release = args.release_root.resolve(strict=True)
        if release != _ROOT or Path.cwd().resolve(strict=True) != release:
            raise WorkerWrapperError("worker wrapper is outside its installed release")
        policy = load_drop_policy(args.config, release)
        environment = {
            "HOME": os.fspath(policy.home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "NO_COLOR": "1",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "TZ": "UTC",
        }
        argv = [
            os.fspath(policy.python),
            "-I",
            "-S",
            "-B",
            os.fspath(policy.entrypoint),
            "serve",
            "--config",
            os.fspath(policy.config),
        ]
        drop_worker_privileges(policy.uid, policy.gid)
        os.execve(argv[0], argv, environment)
    except (
        WorkerWrapperError,
        KeyError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"worker wrapper error: {type(exc).__name__}", file=sys.stderr)
        return 2
    raise AssertionError("execve returned")


if __name__ == "__main__":
    raise SystemExit(main())
