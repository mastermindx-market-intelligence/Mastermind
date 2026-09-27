#!/usr/bin/env python3
"""Prepare one Linux secondary host for the existing Executive worker/gateway path.

This root-only installer is intentionally inert after installation. It establishes
fixed Executive service principals, an immutable release, one root-owned native
Codex binary, and rendered systemd unit files. It does not create provider
credentials, network trust material, Worker/Capacity registrations, Runtime rows,
or start/enable/reload any service.
"""
from __future__ import annotations

import argparse
import dataclasses
import grp
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Callable, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

_MODE_OWNER_RWX = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
_MODE_ROOT_TRAVERSE = _MODE_OWNER_RWX | stat.S_IXGRP | stat.S_IXOTH
_MODE_ROOT_DIR = (
    _MODE_OWNER_RWX
    | stat.S_IRGRP | stat.S_IXGRP
    | stat.S_IROTH | stat.S_IXOTH
)
_MODE_ROOT_FILE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH

CONTROL_HOME = Path("/var/lib/mastermind-executive/control/home")
WORKER_HOME = Path("/var/lib/mastermind-executive/workers/codex-01/provider-home")
STATE_ROOT = Path("/var/lib/mastermind-executive")
WORKSPACE_ROOT = STATE_ROOT / "workspaces"
RUN_ROOT = STATE_ROOT / "runs"
WORKER_STATE = STATE_ROOT / "workers/codex-01/state"
CONFIG_ROOT = Path("/etc/mastermind-executive")
INSTALL_ROOT = Path("/opt/mastermind-executive")
RELEASES_ROOT = INSTALL_ROOT / "releases"
BIN_ROOT = INSTALL_ROOT / "bin"
UNIT_ROOT = Path("/etc/systemd/system")
LOG_ROOT = Path("/var/log/mastermind-executive")
WORKER_LOG_ROOT = LOG_ROOT / "worker"
GATEWAY_LOG_ROOT = LOG_ROOT / "gateway"

RELEASE_PATHS = (
    "control_plane",
    "ops/executive_os",
    "scripts/executive_os_linux_worker.py",
    "scripts/executive_os_remote_worker_gateway.py",
)
CENTRAL_UNITS = (
    "mastermind-executive-control.service",
    "mastermind-executive-mcp.service",
    "mastermind-executive-sol-state-relay.service",
)
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9A-Za-z_-]+){1,5}$")
_GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "LC_ALL": "C",
}
_GIT_SAFE_CONFIG = (
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
)


class EnrollmentError(RuntimeError):
    """Bounded Linux host-enrollment refusal."""


@dataclasses.dataclass(frozen=True)
class Args:
    source_repo: Path
    expected_sha: str
    expected_tree: str
    codex_source_binary: Path
    codex_version: str
    codex_sha256: str


@dataclasses.dataclass(frozen=True)
class ServiceIdentities:
    control_user: str
    control_group: str
    control_uid: int
    control_gid: int
    worker_user: str
    worker_group: str
    worker_uid: int
    worker_gid: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--codex-source-binary", type=Path, required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--codex-sha256", required=True)
    return parser


def _run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    input_bytes: bytes | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(argv),
            cwd=os.fspath(cwd) if cwd is not None else None,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
            timeout=120,
            env=dict(env) if env is not None else None,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EnrollmentError(f"command_failed:{Path(argv[0]).name}") from exc


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return _run(
        ["/usr/bin/git", *_GIT_SAFE_CONFIG, "-C", os.fspath(repo), *args],
        check=check,
        env=_GIT_ENV,
    )


def verify_git_config_safe(repo: Path) -> None:
    raw = _git(repo, "config", "--local", "--name-only", "--list").stdout
    try:
        keys = [line for line in raw.decode("utf-8", errors="strict").splitlines() if line]
    except UnicodeDecodeError as exc:
        raise EnrollmentError("source_git_config_invalid") from exc
    allowed_exact = {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "remote.origin.url",
        "remote.origin.fetch",
    }
    forbidden_prefixes = (
        "filter.", "include.", "includeif.", "diff.", "merge.",
        "credential.", "url.", "http.", "ssh.",
    )
    for key in keys:
        lower = key.lower()
        if lower in allowed_exact:
            continue
        if lower.startswith("branch.") and (lower.endswith(".remote") or lower.endswith(".merge")):
            continue
        if lower.startswith(forbidden_prefixes) or lower.startswith("core."):
            raise EnrollmentError(f"source_git_config_unsafe:{key}")
        raise EnrollmentError(f"source_git_config_unreviewed:{key}")


def verify_source_identity(repo: Path, expected_sha: str, expected_tree: str) -> dict[str, str]:
    repo = Path(repo)
    if not repo.is_absolute() or not repo.is_dir() or repo.is_symlink():
        raise EnrollmentError("source_repo_invalid")
    if _HEX40.fullmatch(expected_sha) is None:
        raise EnrollmentError("expected_commit_invalid")
    if _HEX40.fullmatch(expected_tree) is None:
        raise EnrollmentError("expected_tree_invalid")

    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if status.strip():
        raise EnrollmentError("source_repo_dirty")
    commit = _git(repo, "rev-parse", "HEAD").stdout.decode("ascii", errors="strict").strip()
    tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.decode("ascii", errors="strict").strip()
    if commit != expected_sha:
        raise EnrollmentError("source_commit_mismatch")
    if tree != expected_tree:
        raise EnrollmentError("source_tree_mismatch")
    return {"commit": commit, "tree": tree}


def verify_root_source_custody(repo: Path) -> None:
    repo = Path(repo)
    try:
        repo_info = repo.lstat()
        git_info = (repo / ".git").lstat()
    except OSError as exc:
        raise EnrollmentError("source_custody_unavailable") from exc
    if not stat.S_ISDIR(repo_info.st_mode) or stat.S_ISLNK(repo_info.st_mode):
        raise EnrollmentError("source_repo_not_direct")
    if repo_info.st_uid != 0 or stat.S_IMODE(repo_info.st_mode) & 0o022:
        raise EnrollmentError("source_repo_custody_invalid")
    if not stat.S_ISDIR(git_info.st_mode) or git_info.st_uid != 0:
        raise EnrollmentError("source_git_custody_invalid")
    verify_git_config_safe(repo)

    listed = _git(repo, "ls-files", "-z").stdout.split(b"\0")
    for encoded in listed:
        if not encoded:
            continue
        relative = encoded.decode("utf-8", errors="strict")
        target = repo / relative
        info = target.lstat()
        if stat.S_ISLNK(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
            raise EnrollmentError("source_member_custody_invalid")
        if info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022:
            raise EnrollmentError("source_member_custody_invalid")


def load_canonical_identities(
    repo: Path, *, require_root_owner: bool = True
) -> ServiceIdentities:
    source = Path(repo) / "ops/executive_os/bootstrap-host.sh"
    try:
        info = source.lstat()
    except OSError as exc:
        raise EnrollmentError("canonical_identity_source_unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or (require_root_owner and info.st_uid != 0)
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise EnrollmentError("canonical_identity_source_unsafe")
    text = source.read_text(encoding="utf-8")
    fields = (
        "CONTROL_USER", "CONTROL_GROUP", "CONTROL_UID", "CONTROL_GID",
        "WORKER_USER", "WORKER_GROUP", "WORKER_UID", "WORKER_GID",
    )
    values: dict[str, str] = {}
    for key in fields:
        matches = re.findall(rf"^{key}=\"?([A-Za-z0-9_.-]+)\"?$", text, re.MULTILINE)
        if len(matches) != 1:
            raise EnrollmentError(f"canonical_identity_field_invalid:{key}")
        values[key] = matches[0]
    name_re = re.compile(r"^_?[A-Za-z][A-Za-z0-9_.-]*$")
    for key in ("CONTROL_USER", "CONTROL_GROUP", "WORKER_USER", "WORKER_GROUP"):
        if name_re.fullmatch(values[key]) is None:
            raise EnrollmentError(f"canonical_identity_name_invalid:{key}")
    try:
        control_uid = int(values["CONTROL_UID"])
        control_gid = int(values["CONTROL_GID"])
        worker_uid = int(values["WORKER_UID"])
        worker_gid = int(values["WORKER_GID"])
    except ValueError as exc:
        raise EnrollmentError("canonical_identity_numeric_invalid") from exc
    if min(control_uid, control_gid, worker_uid, worker_gid) <= 0:
        raise EnrollmentError("canonical_identity_numeric_invalid")
    if control_uid == worker_uid or control_gid == worker_gid:
        raise EnrollmentError("canonical_identity_not_separated")
    return ServiceIdentities(
        control_user=values["CONTROL_USER"], control_group=values["CONTROL_GROUP"],
        control_uid=control_uid, control_gid=control_gid,
        worker_user=values["WORKER_USER"], worker_group=values["WORKER_GROUP"],
        worker_uid=worker_uid, worker_gid=worker_gid,
    )


def read_identity_state() -> dict[str, dict[str, Any]]:
    users_by_name: dict[str, Any] = {}
    users_by_uid: dict[str, str] = {}
    groups_by_name: dict[str, int] = {}
    groups_by_gid: dict[str, str] = {}
    for entry in pwd.getpwall():
        users_by_name[entry.pw_name] = {
            "uid": entry.pw_uid,
            "gid": entry.pw_gid,
            "home": entry.pw_dir,
            "shell": entry.pw_shell,
        }
        users_by_uid[str(entry.pw_uid)] = entry.pw_name
    for entry in grp.getgrall():
        groups_by_name[entry.gr_name] = entry.gr_gid
        groups_by_gid[str(entry.gr_gid)] = entry.gr_name
    return {
        "users_by_name": users_by_name,
        "users_by_uid": users_by_uid,
        "groups_by_name": groups_by_name,
        "groups_by_gid": groups_by_gid,
    }


def _classify_one(
    state: Mapping[str, Mapping[str, Any]],
    *,
    name: str,
    group: str,
    uid: int,
    gid: int,
    home: Path,
) -> str:
    users = state["users_by_name"]
    by_uid = state["users_by_uid"]
    groups = state["groups_by_name"]
    by_gid = state["groups_by_gid"]
    other_user = by_uid.get(str(uid))
    if other_user not in (None, name):
        raise EnrollmentError(f"UID {uid} is already assigned")
    other_group = by_gid.get(str(gid))
    if other_group not in (None, group):
        raise EnrollmentError(f"GID {gid} is already assigned")
    existing_group = groups.get(group)
    if existing_group not in (None, gid):
        raise EnrollmentError(f"group {group} has the wrong GID")
    existing = users.get(name)
    if existing is None:
        # A same-operation interruption can land the exact reviewed group before
        # useradd runs. Re-adopt only that exact name/GID pair; foreign identity
        # collisions were already rejected above.
        if existing_group is not None:
            return "create_user"
        return "create"
    if (
        existing.get("uid") != uid
        or existing.get("gid") != gid
        or existing.get("home") != os.fspath(home)
        or existing.get("shell") != "/usr/sbin/nologin"
        or existing_group != gid
    ):
        raise EnrollmentError(f"user {name} differs from the reviewed identity")
    return "verify"


def classify_identity_plan(
    state: Mapping[str, Mapping[str, Any]], identities: ServiceIdentities
) -> dict[str, str]:
    return {
        "control": _classify_one(
            state, name=identities.control_user, group=identities.control_group,
            uid=identities.control_uid, gid=identities.control_gid, home=CONTROL_HOME,
        ),
        "worker": _classify_one(
            state, name=identities.worker_user, group=identities.worker_group,
            uid=identities.worker_uid, gid=identities.worker_gid, home=WORKER_HOME,
        ),
    }


def ensure_service_identities(identities: ServiceIdentities) -> None:
    plan = classify_identity_plan(read_identity_state(), identities)
    specs = (
        ("control", identities.control_group, identities.control_gid, identities.control_user, identities.control_uid, CONTROL_HOME),
        ("worker", identities.worker_group, identities.worker_gid, identities.worker_user, identities.worker_uid, WORKER_HOME),
    )
    for key, group, gid, user, uid, home in specs:
        if plan[key] == "verify":
            continue
        if plan[key] == "create":
            _run(["/usr/sbin/groupadd", "--system", "--gid", str(gid), group])
        elif plan[key] != "create_user":
            raise EnrollmentError(f"identity_plan_invalid:{key}")
        _run(
            [
                "/usr/sbin/useradd",
                "--system",
                "--uid",
                str(uid),
                "--gid",
                str(gid),
                "--home-dir",
                os.fspath(home),
                "--shell",
                "/usr/sbin/nologin",
                "--no-create-home",
                user,
            ]
        )
    classify_identity_plan(read_identity_state(), identities)


def assert_central_control_absent() -> None:
    roots = (
        Path("/etc/systemd/system"),
        Path("/run/systemd/system"),
        Path("/usr/lib/systemd/system"),
        Path("/lib/systemd/system"),
    )
    for unit in CENTRAL_UNITS:
        if any((root / unit).exists() or (root / unit).is_symlink() for root in roots):
            raise EnrollmentError(f"central_unit_installed:{unit}")
        for verb in ("is-active", "is-enabled"):
            result = _run(
                ["/usr/bin/systemctl", verb, "--quiet", unit],
                check=False,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
            if result.returncode == 0:
                raise EnrollmentError(f"central_unit_present:{unit}")


def _stable_file_digest(path: Path) -> tuple[str, dict[str, int]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EnrollmentError("codex_source_must_be_direct") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise EnrollmentError("codex_source_must_be_direct")
        if not before.st_mode & 0o111:
            raise EnrollmentError("codex_source_not_executable")
        magic = os.read(fd, 4)
        if magic != b"\x7fELF":
            raise EnrollmentError("codex_source_not_elf")
        os.lseek(fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode")
    if any(getattr(before, field) != getattr(after, field) for field in identity_fields):
        raise EnrollmentError("codex_source_changed_during_inspection")
    return digest.hexdigest(), {
        "device": before.st_dev,
        "inode": before.st_ino,
        "size": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "ctime_ns": before.st_ctime_ns,
        "mode": stat.S_IMODE(before.st_mode),
    }


def inspect_codex_source(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_absolute():
        raise EnrollmentError("codex_source_not_absolute")
    digest, identity = _stable_file_digest(path)
    return {"path": path, "sha256": digest, "identity": identity}


def _mkdir(path: Path, uid: int, gid: int, mode: int) -> None:
    created = False
    if not path.exists() and not path.is_symlink():
        path.mkdir(mode=mode)
        created = True
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise EnrollmentError(f"directory_invalid:{path}")
    if created:
        os.chown(path, uid, gid)
        os.chmod(path, mode)
        info = path.lstat()
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
        raise EnrollmentError(f"directory_metadata_invalid:{path}")


def ensure_directories(identities: ServiceIdentities) -> None:
    _mkdir(STATE_ROOT, 0, 0, _MODE_ROOT_TRAVERSE)
    _mkdir(STATE_ROOT / "control", 0, 0, _MODE_ROOT_TRAVERSE)
    _mkdir(CONTROL_HOME, identities.control_uid, identities.control_gid, _MODE_OWNER_RWX)
    _mkdir(STATE_ROOT / "workers", 0, 0, _MODE_ROOT_TRAVERSE)
    _mkdir(STATE_ROOT / "workers/codex-01", 0, 0, _MODE_ROOT_TRAVERSE)
    _mkdir(WORKER_HOME, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
    _mkdir(WORKSPACE_ROOT, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
    _mkdir(RUN_ROOT, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
    _mkdir(WORKER_STATE, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
    _mkdir(CONFIG_ROOT, 0, 0, _MODE_ROOT_DIR)
    _mkdir(INSTALL_ROOT, 0, 0, _MODE_ROOT_DIR)
    _mkdir(RELEASES_ROOT, 0, 0, _MODE_ROOT_DIR)
    _mkdir(BIN_ROOT, 0, 0, _MODE_ROOT_DIR)
    _mkdir(LOG_ROOT, 0, 0, _MODE_ROOT_TRAVERSE)
    _mkdir(WORKER_LOG_ROOT, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
    _mkdir(GATEWAY_LOG_ROOT, identities.control_uid, identities.control_gid, _MODE_OWNER_RWX)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise EnrollmentError("short_write")
        view = view[written:]


def _copy_codex_stably(source: Path, destination: Path, expected: Mapping[str, Any]) -> None:
    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temp = destination.with_name(f".{destination.name}.staging-{os.getpid()}")
    dest_fd = None
    try:
        before = os.fstat(source_fd)
        identity = expected["identity"]
        if (
            before.st_dev != identity["device"]
            or before.st_ino != identity["inode"]
            or before.st_size != identity["size"]
            or before.st_mtime_ns != identity["mtime_ns"]
            or before.st_ctime_ns != identity["ctime_ns"]
            or stat.S_IMODE(before.st_mode) != identity["mode"]
        ):
            raise EnrollmentError("codex_source_identity_moved")
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        dest_fd = os.open(temp, flags, 0o500)
        digest = hashlib.sha256()
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            _write_all(dest_fd, block)
        os.fsync(dest_fd)
        after = os.fstat(source_fd)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise EnrollmentError("codex_source_changed_during_copy")
        if digest.hexdigest() != expected["sha256"]:
            raise EnrollmentError("codex_source_digest_moved")
        os.fchown(dest_fd, 0, 0)
        os.fchmod(dest_fd, 0o555)
        os.fsync(dest_fd)
        os.close(dest_fd)
        dest_fd = None
        os.replace(temp, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if dest_fd is not None:
            os.close(dest_fd)
        os.close(source_fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def install_codex_binary(
    source_info: Mapping[str, Any],
    version: str,
    expected_sha256: str,
) -> Path:
    if _VERSION.fullmatch(version) is None:
        raise EnrollmentError("codex_version_invalid")
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise EnrollmentError("codex_sha256_invalid")
    if source_info["sha256"] != expected_sha256:
        raise EnrollmentError("codex_source_digest_not_accepted")
    destination = BIN_ROOT / f"codex-{version}"
    source = Path(source_info["path"])
    if destination.exists() or destination.is_symlink():
        info = destination.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o555
        ):
            raise EnrollmentError("installed_codex_identity_invalid")
        digest, _ = _stable_file_digest(destination)
        if digest != expected_sha256:
            raise EnrollmentError("installed_codex_digest_conflict")
    else:
        _copy_codex_stably(source, destination, source_info)
    # Deliberately do not execute the candidate as root. The #1022 worker
    # service performs the existing Codex version/binary attestation only
    # after privilege has dropped to the dedicated worker principal.
    return destination


def _safe_archive_members(archive: tarfile.TarFile) -> None:
    for member in archive.getmembers():
        pure = Path(member.name)
        if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
            raise EnrollmentError("release_archive_path_invalid")
        if not (member.isdir() or member.isreg()):
            raise EnrollmentError("release_archive_type_invalid")


def _verify_release_tree(root: Path) -> None:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        info = current_path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
            raise EnrollmentError("installed_release_metadata_invalid")
        for name in files:
            path = current_path / name
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != 0
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                raise EnrollmentError("installed_release_metadata_invalid")


def install_release(repo: Path, expected_sha: str, expected_tree: str) -> Path:
    manifest_tool = repo / "ops/executive_os/release_manifest.py"
    try:
        manifest_info = manifest_tool.lstat()
    except OSError as exc:
        raise EnrollmentError("release_manifest_source_unavailable") from exc
    if (
        not stat.S_ISREG(manifest_info.st_mode)
        or stat.S_ISLNK(manifest_info.st_mode)
        or manifest_info.st_uid != 0
        or manifest_info.st_nlink != 1
        or stat.S_IMODE(manifest_info.st_mode) & 0o022
    ):
        raise EnrollmentError("release_manifest_source_unsafe")
    destination = RELEASES_ROOT / expected_sha
    if destination.exists() or destination.is_symlink():
        if not destination.is_dir() or destination.is_symlink():
            raise EnrollmentError("release_destination_invalid")
        _verify_release_tree(destination)
        _run(
            [
                "/usr/bin/python3", "-I", "-S", "-B", os.fspath(manifest_tool),
                "verify", "--root", os.fspath(destination),
                "--commit-sha", expected_sha, "--tree-sha", expected_tree,
            ]
        )
    else:
        staging = Path(tempfile.mkdtemp(prefix=f".release-{expected_sha}.", dir=RELEASES_ROOT))
        archive_path = staging.parent / f".archive-{expected_sha}-{os.getpid()}.tar"
        try:
            archive = _git(repo, "archive", expected_sha, "--", *RELEASE_PATHS).stdout
            archive_path.write_bytes(archive)
            with tarfile.open(archive_path, mode="r:") as tar:
                _safe_archive_members(tar)
                tar.extractall(staging, filter="data")
            for root, dirs, files in os.walk(staging):
                os.chown(root, 0, 0)
                os.chmod(root, _MODE_ROOT_DIR)
                for name in files:
                    path = Path(root) / name
                    os.chown(path, 0, 0)
                    os.chmod(path, _MODE_ROOT_FILE)
            for executable in (
                staging / "scripts/executive_os_linux_worker.py",
                staging / "scripts/executive_os_remote_worker_gateway.py",
            ):
                os.chmod(executable, 0o555)
            _run(
                [
                    "/usr/bin/python3",
                    "-I",
                    "-S",
                    "-B",
                    os.fspath(manifest_tool),
                    "create",
                    "--root",
                    os.fspath(staging),
                    "--commit-sha",
                    expected_sha,
                    "--tree-sha",
                    expected_tree,
                ]
            )
            _run(
                [
                    "/usr/bin/python3",
                    "-I",
                    "-S",
                    "-B",
                    os.fspath(manifest_tool),
                    "verify",
                    "--root",
                    os.fspath(staging),
                    "--commit-sha",
                    expected_sha,
                    "--tree-sha",
                    expected_tree,
                ]
            )
            os.replace(staging, destination)
            _verify_release_tree(destination)
            parent_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        finally:
            try:
                archive_path.unlink()
            except FileNotFoundError:
                pass
            if staging.exists():
                shutil.rmtree(staging)
    return destination


def render_systemd_units(
    *, release_root: Path, codex_binary: Path, identities: ServiceIdentities
) -> dict[str, str]:
    template_root = release_root / "ops/executive_os"
    replacements = {
        "__WORKER_ID__": "codex-01",
        "__WORKER_SOCKET_UNIT__": "mastermind-executive-worker-codex-01.socket",
        "__WORKER_SERVICE_UNIT__": "mastermind-executive-worker-codex-01.service",
        "__WORKER_USER__": identities.worker_user,
        "__WORKER_GROUP__": identities.worker_group,
        "__CONTROL_USER__": identities.control_user,
        "__CONTROL_GROUP__": identities.control_group,
        "__PROVIDER_HOME__": os.fspath(WORKER_HOME),
        "__PYTHON_BINARY__": "/usr/bin/python3",
        "__WORKER_ENTRYPOINT__": os.fspath(release_root / "scripts/executive_os_linux_worker.py"),
        "__WORKER_CONFIG__": os.fspath(CONFIG_ROOT / "worker-codex-01.json"),
        "__WORKSPACE_ROOT__": os.fspath(WORKSPACE_ROOT),
        "__RUN_ROOT__": os.fspath(RUN_ROOT),
        "__UID_SWEEP_PARENT__": os.fspath(WORKER_STATE),
        "__WORKER_STDOUT__": os.fspath(WORKER_LOG_ROOT / "stdout.log"),
        "__WORKER_STDERR__": os.fspath(WORKER_LOG_ROOT / "stderr.log"),
        "__WORKER_SOCKET__": "/run/mastermind-executive-worker-codex-01.sock",
        "__HOST_REF__": "UNENROLLED_HOST_REF",
        "__GATEWAY_ENTRYPOINT__": os.fspath(
            release_root / "scripts/executive_os_remote_worker_gateway.py"
        ),
        "__GATEWAY_CONFIG__": os.fspath(CONFIG_ROOT / "remote-worker-gateway.json"),
        "__GATEWAY_STDOUT__": os.fspath(GATEWAY_LOG_ROOT / "stdout.log"),
        "__GATEWAY_STDERR__": os.fspath(GATEWAY_LOG_ROOT / "stderr.log"),
    }
    sources = {
        "mastermind-executive-worker-codex-01.service": "mastermind-executive-worker.service.template",
        "mastermind-executive-worker-codex-01.socket": "mastermind-executive-worker.socket.template",
        "mastermind-executive-remote-worker-gateway.service": (
            "mastermind-executive-remote-worker-gateway.service.template"
        ),
    }
    rendered: dict[str, str] = {}
    for destination, source in sources.items():
        text = (template_root / source).read_text(encoding="utf-8")
        for key, value in replacements.items():
            text = text.replace(key, value)
        active_lines = [
            line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if (
            "__" in text
            or "[Install]" in active_lines
            or any(line.startswith("WantedBy=") for line in active_lines)
        ):
            raise EnrollmentError("systemd_unit_not_inert_or_unrendered")
        rendered[destination] = text
    return rendered


def _write_root_unit(path: Path, data: bytes) -> None:
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != _MODE_ROOT_FILE
            or path.read_bytes() != data
        ):
            raise EnrollmentError(f"systemd_unit_conflict:{path.name}")
        return
    fd = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        _write_all(fd, data)
        os.fchown(fd, 0, 0)
        os.fchmod(fd, _MODE_ROOT_FILE)
        os.fsync(fd)
    finally:
        os.close(fd)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def install_inert_units(
    release_root: Path, codex_binary: Path, identities: ServiceIdentities
) -> tuple[str, ...]:
    rendered = render_systemd_units(
        release_root=release_root, codex_binary=codex_binary, identities=identities
    )
    with tempfile.TemporaryDirectory(prefix="mastermind-systemd-verify.") as temporary:
        verify_paths: list[str] = []
        for name, text in rendered.items():
            path = Path(temporary) / name
            path.write_text(text, encoding="utf-8")
            verify_paths.append(os.fspath(path))
        _run(["/usr/bin/systemd-analyze", "verify", *verify_paths])
    for name, text in rendered.items():
        _write_root_unit(UNIT_ROOT / name, text.encode("utf-8"))
    return tuple(sorted(rendered))


def apply_enrollment(args: Args) -> dict[str, Any]:
    if platform.system() != "Linux":
        raise EnrollmentError("linux_required")
    if os.geteuid() != 0:
        raise EnrollmentError("root_required")
    assert_central_control_absent()
    verify_root_source_custody(args.source_repo)
    identity = verify_source_identity(args.source_repo, args.expected_sha, args.expected_tree)
    identities = load_canonical_identities(args.source_repo)
    source_info = inspect_codex_source(args.codex_source_binary)
    if source_info["sha256"] != args.codex_sha256:
        raise EnrollmentError("codex_source_digest_not_accepted")
    ensure_service_identities(identities)
    ensure_directories(identities)
    release = install_release(args.source_repo, args.expected_sha, args.expected_tree)
    codex_binary = install_codex_binary(
        source_info, args.codex_version, args.codex_sha256
    )
    units = install_inert_units(release, codex_binary, identities)
    assert_central_control_absent()
    return {
        "schema": "mastermind.linux_secondary_worker_enrollment/v1",
        "outcome": "READY_FOR_PROVIDER_AND_MTLS_ENROLLMENT",
        "release_sha": identity["commit"],
        "release_tree": identity["tree"],
        "codex_version": args.codex_version,
        "codex_sha256": source_info["sha256"],
        "units_installed_inert": list(units),
        "services_activated": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    ns = _parser().parse_args(list(argv) if argv is not None else None)
    if _HEX40.fullmatch(ns.expected_sha) is None or _HEX40.fullmatch(ns.expected_tree) is None:
        sys.stderr.write("invalid source identity\n")
        return 64
    if _VERSION.fullmatch(ns.codex_version) is None:
        sys.stderr.write("invalid Codex version\n")
        return 64
    if re.fullmatch(r"[0-9a-f]{64}", ns.codex_sha256) is None:
        sys.stderr.write("invalid Codex digest\n")
        return 64
    args = Args(
        source_repo=ns.source_repo,
        expected_sha=ns.expected_sha,
        expected_tree=ns.expected_tree,
        codex_source_binary=ns.codex_source_binary,
        codex_version=ns.codex_version,
        codex_sha256=ns.codex_sha256,
    )
    try:
        receipt = apply_enrollment(args)
    except EnrollmentError as exc:
        sys.stderr.write(f"enrollment refused: {exc}\n")
        return 65
    sys.stdout.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
