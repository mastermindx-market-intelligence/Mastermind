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
from contextlib import nullcontext
import fcntl
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
    # The existing broker/result import closure used by both Linux entrypoints.
    # Include the exact import closure without fixture servers, assets or runners.
    "scripts/ohf/__init__.py",
    "scripts/ohf/redaction.py",
    "scripts/ohf/capability_skill_projection.py",
    "scripts/ohf/laboratory.py",
    "scripts/ohf/protocol.py",
    "scripts/ohf/fixtures/__init__.py",
    # First-party runtime/native-BYOK source and role data only. This does not
    # install third-party dependencies, enroll credentials, attest a running
    # interpreter/unit, or install a delegation CLI entrypoint.
    "common",
    "integrations/__init__.py",
    "integrations/hermes_runtime",
    # Exact existing pure-YAML closure; no third-party installation or ambient site.
    "ops/native_fabric/quota_continuity/candidate/paid_yaml_runtime.py",
    "ops/native_fabric/quota_continuity/candidate/paid_pyyaml_6_0_3.zip",
    "ops/native_fabric/quota_continuity/candidate/paid_pyyaml_provenance.json",
    # The shared runtime-custody factory and the incumbent process-identity
    # helper. Both are reused as-is; neither is copied into the release.
    "ops/native_fabric/quota_continuity/candidate/paid_initializer.py",
    "ops/native_fabric/quota_continuity/candidate/linux_process_identity.py",
    "integrations/hermes_harness",
    # Native consumer imports include this package and its eager bridge/tool closure.
    "integrations/hermes_delegate",
    "integrations/hermes_models",
    "integrations/hermes_steward",
    "integrations/hermes_qualification",
    "integrations/business_mcp_auth/__init__.py",
    "integrations/business_mcp_auth/claims.py",
    "integrations/business_mcp_auth/contracts.py",
    "integrations/mastermind_secretary_mcp/__init__.py",
    "integrations/mastermind_secretary_mcp/schemas.py",
)
CENTRAL_UNITS = (
    "mastermind-executive-control.service",
    "mastermind-executive-mcp.service",
    "mastermind-executive-sol-state-relay.service",
)
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9A-Za-z_-]+){1,5}$")
_MAX_HERMES_ARGUMENT = 64 * 1024
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
    codex_source_binary: Path | None = None
    codex_version: str | None = None
    codex_sha256: str | None = None
    hermes_runtime: dict[str, Any] | None = None
    component: str = "secondary-worker"
    gateway_config_file: Path | None = None
    gateway_config_sha256: str | None = None
    expected_gateway_unit_sha256: str | None = None


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
    parser.add_argument("--component", choices=("secondary-worker", "hermes-host-observation"),
                        default="secondary-worker")
    parser.add_argument("--codex-source-binary", type=Path)
    parser.add_argument("--codex-version")
    parser.add_argument("--codex-sha256")
    parser.add_argument("--gateway-config-file", type=Path,
                        help="Root-staged observation input, root:gateway 0440 in a protected 0750 directory")
    parser.add_argument("--gateway-config-sha256", help="SHA-256 of the exact input bytes")
    parser.add_argument(
        "--expected-gateway-unit-sha256",
        help="Replace only the exact inactive gateway unit; preserve its installed observation config",
    )
    parser.add_argument(
        "--hermes-runtime-json",
        help=("Optional approved Hermes runtime installation input as one JSON "
              "object. It is frozen into the release manifest; the manifest is "
              "never retrofitted."),
    )
    return parser


def _closed_pairs(items):
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _require_hermes_source_checkout(source_repo: Path) -> None:
    """Keep the imported Hermes renderer in the accepted source checkout."""
    try:
        matches = Path(source_repo).resolve(strict=True) == _ROOT.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise EnrollmentError("hermes_source_checkout_unavailable") from exc
    if not matches:
        raise EnrollmentError("hermes_source_checkout_mismatch")


def decode_hermes_runtime(raw: str | None, *, source_repo: Path | None = None
                          ) -> dict[str, Any] | None:
    """Bounded closed decode of the optional approved installation input.

    ``None`` (an absent argument) and an explicit JSON ``null`` both mean the
    release carries no installation member. A malformed or non-canonical
    document is refused before the first mutation.
    """
    if raw is None:
        return None
    if type(raw) is not str or not 0 < len(raw) <= _MAX_HERMES_ARGUMENT:
        raise EnrollmentError("hermes_runtime_json_invalid")
    try:
        document = json.loads(raw, object_pairs_hook=_closed_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EnrollmentError("hermes_runtime_json_invalid") from exc
    if document is None:
        return None
    if source_repo is not None:
        _require_hermes_source_checkout(source_repo)
    from ops.executive_os.release_manifest import validate_hermes_runtime_installation
    try:
        return validate_hermes_runtime_installation(document)
    except Exception as exc:
        raise EnrollmentError("hermes_runtime_invalid") from exc


def _hermes_runtime_argument(hermes_runtime: Mapping[str, Any] | None) -> str:
    """The exact JSON the manifest tool receives; absence is explicit null."""
    if hermes_runtime is None:
        return "null"
    return json.dumps(hermes_runtime, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


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


def verify_root_source_custody(
    repo: Path, *, expected_owner_uid: int = 0
) -> None:
    repo = Path(repo)
    git_dir = repo / ".git"

    # Checking only the checkout itself does not fence its pathname. A user
    # who can write a parent directory can rename even a root-owned checkout
    # and replace its path before later root Git/Python operations.
    if not repo.is_absolute() or ".." in repo.parts:
        raise EnrollmentError("source_ancestor_custody_invalid")
    for ancestor in reversed(repo.parents):
        try:
            info = ancestor.lstat()
        except OSError as exc:
            raise EnrollmentError("source_ancestor_custody_invalid") from exc
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid not in (0, int(expected_owner_uid))
        ):
            raise EnrollmentError("source_ancestor_custody_invalid")
        if stat.S_IMODE(info.st_mode) & 0o022:
            # A root-owned sticky directory (for example /tmp) prevents
            # unprivileged renames of root-owned descendants. Other writable
            # ancestors leave the checked checkout path replaceable.
            if not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
                raise EnrollmentError("source_ancestor_custody_invalid")

    def require_directory(path: Path, *, code: str) -> None:
        try:
            info = path.lstat()
        except OSError as exc:
            raise EnrollmentError(code) from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != int(expected_owner_uid)
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise EnrollmentError(code)

    def require_file(path: Path, *, code: str) -> None:
        try:
            info = path.lstat()
        except OSError as exc:
            raise EnrollmentError(code) from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != int(expected_owner_uid)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise EnrollmentError(code)

    require_directory(repo, code="source_repo_custody_invalid")
    require_directory(git_dir, code="source_git_custody_invalid")

    # Git is executed as root later. Close the complete local Git administrative
    # tree before invoking it so a non-root writer cannot race object/config/ref
    # bytes between source verification and `git archive`.
    for current, directory_names, file_names in os.walk(
        git_dir, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        require_directory(current_path, code="source_git_custody_invalid")
        for name in directory_names:
            require_directory(current_path / name, code="source_git_custody_invalid")
        for name in file_names:
            require_file(current_path / name, code="source_git_custody_invalid")

    verify_git_config_safe(repo)

    listed = _git(repo, "ls-files", "-z").stdout.split(b"\0")
    parent_directories: set[Path] = {repo}
    for encoded in listed:
        if not encoded:
            continue
        relative = encoded.decode("utf-8", errors="strict")
        target = repo / relative
        info = target.lstat()
        parent = target.parent
        while parent != repo:
            parent_directories.add(parent)
            parent = parent.parent
        if stat.S_ISLNK(info.st_mode):
            if info.st_uid != int(expected_owner_uid):
                raise EnrollmentError("source_member_custody_invalid")
            continue
        require_file(target, code="source_member_custody_invalid")

    # Root-owned tracked files are insufficient when a writable ancestor lets a
    # non-root process unlink/replace them after verification. Close every
    # tracked-file ancestor used by the accepted checkout.
    for directory in sorted(parent_directories, key=os.fspath):
        require_directory(directory, code="source_directory_custody_invalid")


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
    state: Mapping[str, Mapping[str, Any]], identities: ServiceIdentities, *, gateway_only: bool = False
) -> dict[str, str]:
    plan = {
        "control": _classify_one(
            state, name=identities.control_user, group=identities.control_group,
            uid=identities.control_uid, gid=identities.control_gid, home=CONTROL_HOME,
        ),
    }
    if not gateway_only:
        plan["worker"] = _classify_one(
            state, name=identities.worker_user, group=identities.worker_group,
            uid=identities.worker_uid, gid=identities.worker_gid, home=WORKER_HOME,
        )
    return plan


def ensure_service_identities(identities: ServiceIdentities, *, gateway_only: bool = False) -> None:
    plan = classify_identity_plan(read_identity_state(), identities, gateway_only=gateway_only)
    specs = (
        ("control", identities.control_group, identities.control_gid, identities.control_user, identities.control_uid, CONTROL_HOME),
        ("worker", identities.worker_group, identities.worker_gid, identities.worker_user, identities.worker_uid, WORKER_HOME),
    )
    for key, group, gid, user, uid, home in specs:
        if key not in plan:
            continue
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
    classify_identity_plan(read_identity_state(), identities, gateway_only=gateway_only)


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


def ensure_directories(identities: ServiceIdentities, *, gateway_only: bool = False) -> None:
    _mkdir(STATE_ROOT, 0, 0, _MODE_ROOT_TRAVERSE)
    _mkdir(STATE_ROOT / "control", 0, 0, _MODE_ROOT_TRAVERSE)
    _mkdir(CONTROL_HOME, identities.control_uid, identities.control_gid, _MODE_OWNER_RWX)
    if not gateway_only:
        _mkdir(STATE_ROOT / "workers", 0, 0, _MODE_ROOT_TRAVERSE)
        _mkdir(STATE_ROOT / "workers/codex-01", 0, 0, _MODE_ROOT_TRAVERSE)
        _mkdir(WORKER_HOME, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
        _mkdir(WORKSPACE_ROOT, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
        _mkdir(RUN_ROOT, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
        _mkdir(WORKER_STATE, identities.worker_uid, identities.worker_gid, _MODE_OWNER_RWX)
    _mkdir(CONFIG_ROOT, 0, 0, _MODE_ROOT_DIR)
    if gateway_only:
        from ops.executive_os.remote_worker_gateway_service import LINUX_HOST_OBSERVATION_ROOT
        _mkdir(LINUX_HOST_OBSERVATION_ROOT, 0, identities.control_gid, 0o750)
    _mkdir(INSTALL_ROOT, 0, 0, _MODE_ROOT_DIR)
    _mkdir(RELEASES_ROOT, 0, 0, _MODE_ROOT_DIR)
    if not gateway_only:
        _mkdir(BIN_ROOT, 0, 0, _MODE_ROOT_DIR)
    _mkdir(LOG_ROOT, 0, 0, _MODE_ROOT_TRAVERSE)
    if not gateway_only:
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


def _prepare_native_dependencies(repo: Path, destination: Path, expected_sha: str,
                                 expected_tree: str, hermes_runtime) -> None:
    if hermes_runtime is None or not any("native_gateway" in row for row in hermes_runtime["roles"]):
        return
    # Same immutable release, same frozen input, before unit/config selection.
    # Failure leaves the source release inert and eligible for exact adoption.
    _run([
        "/usr/bin/python3", "-I", "-S", "-B",
        os.fspath(repo / "ops/executive_os/release_manifest.py"),
        "prepare-hermes-dependencies", "--root", os.fspath(destination),
        "--commit-sha", expected_sha, "--tree-sha", expected_tree,
        "--hermes-runtime-json", _hermes_runtime_argument(hermes_runtime),
    ])


def install_release(repo: Path, expected_sha: str, expected_tree: str,
                     *, hermes_runtime: Mapping[str, Any] | None = None) -> Path:
    """Create or adopt the immutable release at its final path.

    The manifest tool is always the accepted source copy under ``repo``; the
    staging or installed copy is never executed. The expected installation
    input is always passed explicitly, including its absence, so an existing
    release with a different or missing member conflicts before anything is
    mutated and the immutable manifest is never retrofitted.
    """
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
    expectation = _hermes_runtime_argument(hermes_runtime)
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
                "--hermes-runtime-json", expectation,
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
                    "--hermes-runtime-json",
                    expectation,
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
                    "--hermes-runtime-json",
                    expectation,
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
    _prepare_native_dependencies(repo, destination, expected_sha, expected_tree, hermes_runtime)
    return destination


def _assert_release_input_adoption(repo: Path, expected_sha: str, expected_tree: str,
                                   hermes_runtime: Mapping[str, Any] | None) -> None:
    """Refuse an installed release whose frozen input differs, before mutation.

    The immutable manifest is never retrofitted: an existing release with a
    different installation member, or with no member where one is expected,
    is a conflict and not an in-place upgrade.
    """
    destination = RELEASES_ROOT / expected_sha
    if not (destination.exists() or destination.is_symlink()):
        return
    if not destination.is_dir() or destination.is_symlink():
        raise EnrollmentError("release_destination_invalid")
    manifest_tool = repo / "ops/executive_os/release_manifest.py"
    result = _run(
        [
            "/usr/bin/python3", "-I", "-S", "-B", os.fspath(manifest_tool),
            "verify", "--root", os.fspath(destination),
            "--commit-sha", expected_sha, "--tree-sha", expected_tree,
            "--hermes-runtime-json", _hermes_runtime_argument(hermes_runtime),
        ],
        check=False,
    )
    if result.returncode != 0:
        raise EnrollmentError("release_manifest_input_conflict")


def expected_hermes_role_units(release_commit: str,
                               hermes_runtime: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """The exact role units this release expects, at the FINAL release path.

    This installer never writes these units and never starts a role; the
    host owner installs exactly these bytes. The ExecStart must name the
    final installed release, never a temporary archive or staging path.
    """
    from integrations.hermes_runtime.errors import RuntimeRefusal
    from integrations.hermes_runtime.system_service import render_role_units_from_installation

    try:
        rendered = render_role_units_from_installation(
            hermes_runtime, release_commit=release_commit)
    except RuntimeRefusal as exc:
        raise EnrollmentError("hermes_role_unit_invalid") from exc
    final_root = str(RELEASES_ROOT / release_commit)
    expected: dict[str, dict[str, str]] = {}
    for role, text in rendered.items():
        exec_lines = [line for line in text.splitlines() if line.startswith("ExecStart=")]
        if len(exec_lines) != 1:
            raise EnrollmentError("hermes_role_unit_invalid")
        exec_start = exec_lines[0][len("ExecStart="):]
        if (f" {final_root}/ops/executive_os/release_manifest.py hermes-runtime supervise "
                not in exec_start):
            raise EnrollmentError("hermes_role_unit_release_path_invalid")
        expected[role] = {
            "path": str(UNIT_ROOT / f"hermes-runtime-{role}.service"),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "exec_start": exec_start,
        }
    return expected


def render_systemd_units(
    *, release_root: Path, codex_binary: Path | None, identities: ServiceIdentities,
    gateway_only: bool = False, source_root: Path | None = None,
) -> dict[str, str]:
    template_root = (release_root if source_root is None else source_root) / "ops/executive_os"
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
    if gateway_only:
        from ops.executive_os.remote_worker_gateway_service import LINUX_HOST_OBSERVATION_CONFIG
        replacements["__GATEWAY_CONFIG__"] = os.fspath(LINUX_HOST_OBSERVATION_CONFIG)
        sources = {name: source for name, source in sources.items() if "gateway" in name}
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


_GATEWAY_UNIT = "mastermind-executive-remote-worker-gateway.service"


def _assert_gateway_inert() -> None:
    expected = {
        "Id": _GATEWAY_UNIT, "LoadState": "loaded", "ActiveState": "inactive",
        "SubState": "dead", "UnitFileState": "static", "MainPID": "0",
        "ControlPID": "0", "Job": "", "FragmentPath": os.fspath(UNIT_ROOT / _GATEWAY_UNIT),
        "DropInPaths": "",
    }
    result = _run(
        ["/usr/bin/systemctl", "show", "--no-pager",
         *(f"--property={key}" for key in expected), _GATEWAY_UNIT],
        check=False, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    try:
        rows = result.stdout.decode("utf-8").splitlines()
        pairs = [row.split("=", 1) for row in rows]
        if (result.returncode != 0 or len(result.stdout) > 16384
                or len(pairs) != len(expected) or any(len(pair) != 2 for pair in pairs)
                or len({pair[0] for pair in pairs}) != len(expected)
                or dict(pairs) != expected):
            raise EnrollmentError("gateway_predecessor_not_inert")
    except UnicodeError as exc:
        raise EnrollmentError("gateway_predecessor_not_inert") from exc


class _InertGatewayReplacement:
    """One exact predecessor transition in the existing unit publisher.

    Role/source custody remains held independently of the replaced unit inode.
    An exact desired postimage can be observed after an interrupted original call;
    that observation never claims which historical call performed the write.
    """

    def __init__(self, args: Args, raw: bytes, config, identities: ServiceIdentities):
        from ops.executive_os.release_manifest import (
            _HeldReleaseSources, _held_identity, _linux_source_acl, ReleaseManifestError,
        )
        self.args, self.raw, self.identities = args, raw, identities
        self.role_sha = config.hermes_role_metadata_read.implementation_sha
        self.path = UNIT_ROOT / _GATEWAY_UNIT
        self.published = False
        self.recovered = False
        self.replacement_sha256: str | None = None
        self.owner = None
        self.fd = None
        try:
            self.desired = render_systemd_units(
                release_root=RELEASES_ROOT / args.expected_sha, codex_binary=None,
                identities=identities, gateway_only=True, source_root=args.source_repo,
            )[_GATEWAY_UNIT].encode("utf-8")
            self.owner = _HeldReleaseSources(RELEASES_ROOT / self.role_sha)
            if self.owner.hermes_runtime_input() != args.hermes_runtime:
                raise EnrollmentError("gateway_predecessor_role_input_conflict")
            self.parent_fd = self.owner.hold(UNIT_ROOT, directory=True)
            self.fd = os.open(self.path.name,
                              os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                              dir_fd=self.parent_fd)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _linux_source_acl(self.fd, False)
            info = os.fstat(self.fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != _MODE_ROOT_FILE
                    or not 0 < info.st_size <= 64 * 1024):
                raise EnrollmentError("gateway_predecessor_unit_conflict")
            self.unit_identity = _held_identity(info, False)
            data = os.pread(self.fd, info.st_size + 1, 0)
            self.unit_sha256 = hashlib.sha256(data).hexdigest()
            if len(data) != info.st_size:
                raise EnrollmentError("gateway_predecessor_unit_conflict")
            if data == self.desired:
                self.published = self.recovered = True
                self.replacement_sha256 = self.unit_sha256
            elif self.unit_sha256 != args.expected_gateway_unit_sha256:
                raise EnrollmentError("gateway_predecessor_unit_conflict")
            self.check()
        except (OSError, ReleaseManifestError) as exc:
            self.close()
            raise EnrollmentError("gateway_predecessor_unqualified") from exc
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, _kind, error, _traceback):
        self.close()
        if self.published and isinstance(error, (EnrollmentError, OSError)):
            raise EnrollmentError("gateway_replacement_postimage_requires_reconciliation") from error

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.owner is not None:
            self.owner.close()

    def check(self) -> None:
        from ops.executive_os.release_manifest import (
            _held_identity, _linux_source_acl, ReleaseManifestError,
        )
        try:
            self.owner.check()
            if (self.fd is None
                    or _held_identity(os.fstat(self.fd), False) != self.unit_identity
                    or _held_identity(os.stat(self.path.name, dir_fd=self.parent_fd,
                                             follow_symlinks=False), False) != self.unit_identity):
                raise EnrollmentError("gateway_predecessor_changed")
            _linux_source_acl(self.fd, False)
            current, _ = _observation_input(self.args, self.identities)
            if current != self.raw or not _observation_config_adoption(self.raw, self.identities):
                raise EnrollmentError("gateway_predecessor_config_changed")
            _assert_gateway_inert()
            if not _observation_config_adoption(self.raw, self.identities):
                raise EnrollmentError("gateway_predecessor_config_changed")
            # The source manifest, ancestors AND current unit stay qualified
            # through the last potentially blocking config/manager observation.
            self.owner.check()
            if (_held_identity(os.fstat(self.fd), False) != self.unit_identity
                    or _held_identity(os.stat(self.path.name, dir_fd=self.parent_fd,
                                             follow_symlinks=False), False) != self.unit_identity):
                raise EnrollmentError("gateway_predecessor_changed")
        except (OSError, ReleaseManifestError) as exc:
            raise EnrollmentError("gateway_predecessor_changed") from exc

    def publish(self, path: Path, data: bytes) -> None:
        from ops.executive_os.release_manifest import _held_identity, _linux_source_acl, ReleaseManifestError
        if path != self.path or data != self.desired or not 0 < len(data) <= 64 * 1024:
            raise EnrollmentError("gateway_replacement_target_invalid")
        if self.published:
            if not self.recovered:
                raise EnrollmentError("gateway_predecessor_already_consumed")
            self.check()
            return
        self.check()
        fd, temporary = tempfile.mkstemp(prefix=f".{_GATEWAY_UNIT}.", dir=UNIT_ROOT)
        temporary_name = Path(temporary).name
        created = os.fstat(fd)
        created_inode = (created.st_dev, created.st_ino)
        replaced = False
        try:
            # Keep the postimage inode locked before it becomes the named unit.
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _write_all(fd, data)
            os.fchown(fd, 0, 0)
            os.fchmod(fd, _MODE_ROOT_FILE)
            os.fsync(fd)
            _linux_source_acl(fd, False)
            staged_identity = _held_identity(os.fstat(fd), False)
            self.check()
            if (_held_identity(os.stat(temporary_name, dir_fd=self.parent_fd,
                                      follow_symlinks=False), False) != staged_identity):
                raise EnrollmentError("gateway_replacement_staging_changed")
            os.replace(temporary_name, path.name,
                       src_dir_fd=self.parent_fd, dst_dir_fd=self.parent_fd)
            replaced = self.published = True
            os.close(self.fd)
            self.fd, fd = fd, None
            self.unit_identity = _held_identity(os.fstat(self.fd), False)
            self.unit_sha256 = hashlib.sha256(data).hexdigest()
            os.fsync(self.parent_fd)
            info = os.fstat(self.fd)
            if ((info.st_dev, info.st_ino) != created_inode
                    or self.unit_identity[:-1] != staged_identity[:-1]
                    or info.st_size != len(data)
                    or os.pread(self.fd, len(data) + 1, 0) != data):
                raise EnrollmentError("gateway_replacement_readback_failed")
            self.check()
            self.replacement_sha256 = self.unit_sha256
        except (OSError, ReleaseManifestError, EnrollmentError) as exc:
            if self.published:
                raise EnrollmentError("gateway_replacement_postimage_requires_reconciliation") from exc
            if isinstance(exc, EnrollmentError):
                raise
            raise EnrollmentError("gateway_replacement_io_failed") from exc
        finally:
            if fd is not None:
                os.close(fd)
            if not replaced:
                try:
                    info = os.stat(temporary_name, dir_fd=self.parent_fd, follow_symlinks=False)
                    if (info.st_dev, info.st_ino) == created_inode:
                        os.unlink(temporary_name, dir_fd=self.parent_fd)
                except FileNotFoundError:
                    pass


def _write_root_unit(path: Path, data: bytes, *, predecessor: _InertGatewayReplacement | None = None) -> None:
    if predecessor is not None:
        predecessor.publish(path, data)
        return
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
    release_root: Path, codex_binary: Path | None, identities: ServiceIdentities, *, gateway_only: bool = False,
    predecessor: _InertGatewayReplacement | None = None,
) -> tuple[str, ...]:
    if predecessor is not None and not gateway_only:
        raise EnrollmentError("gateway_replacement_component_invalid")
    rendered = render_systemd_units(
        release_root=release_root, codex_binary=codex_binary, identities=identities, gateway_only=gateway_only
    )
    with tempfile.TemporaryDirectory(prefix="mastermind-systemd-verify.") as temporary:
        verify_paths: list[str] = []
        for name, text in rendered.items():
            path = Path(temporary) / name
            path.write_text(text, encoding="utf-8")
            verify_paths.append(os.fspath(path))
        _run(["/usr/bin/systemd-analyze", "verify", *verify_paths])
    for name, text in rendered.items():
        _write_root_unit(UNIT_ROOT / name, text.encode("utf-8"), predecessor=predecessor)
    return tuple(sorted(rendered))


def _observation_input(args: Args, identities: ServiceIdentities):
    from ops.executive_os import remote_worker_gateway_service as gateway
    if (args.gateway_config_file is None or type(args.gateway_config_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", args.gateway_config_sha256) is None):
        raise EnrollmentError("host_observation_input_required")
    try:
        path = gateway._safe_absolute(args.gateway_config_file, code="GATEWAY_CONFIG_INVALID")
        gateway._trusted_observation_ancestors(path.parent)
        raw = gateway._secure_regular_file(
            path, root=path.parent, expected_owner_uid=0, expected_group_gid=identities.control_gid,
            max_bytes=gateway.MAX_CONFIG_BYTES, read_bytes=True,
        )
        if hashlib.sha256(raw).hexdigest() != args.gateway_config_sha256:
            raise EnrollmentError("host_observation_input_changed")
        config = gateway.decode_host_observation_gateway_config(raw, expected_group_gid=identities.control_gid)
        if args.expected_gateway_unit_sha256 is None:
            if config.hermes_role_metadata_read.implementation_sha != args.expected_sha:
                raise EnrollmentError("host_observation_release_pin_mismatch")
        elif (type(args.expected_gateway_unit_sha256) is not str
              or re.fullmatch(r"[0-9a-f]{64}", args.expected_gateway_unit_sha256) is None
              or not _observation_config_adoption(raw, identities)):
            raise EnrollmentError("gateway_predecessor_config_required")
        return raw, config
    except (OSError, ValueError, TypeError) as exc:
        raise EnrollmentError("host_observation_input_unqualified") from exc


def _observation_config_adoption(raw: bytes, identities: ServiceIdentities) -> bool:
    from ops.executive_os import remote_worker_gateway_service as gateway
    path = gateway.LINUX_HOST_OBSERVATION_CONFIG
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    try:
        actual = gateway._secure_regular_file(
            path, root=gateway.LINUX_HOST_OBSERVATION_ROOT, expected_owner_uid=0,
            expected_group_gid=identities.control_gid, max_bytes=gateway.MAX_CONFIG_BYTES, read_bytes=True,
        )
        if actual != raw:
            raise EnrollmentError("host_observation_config_conflict")
        gateway.load_remote_worker_gateway_config(path, expected_group_gid=identities.control_gid)
        return True
    except (OSError, ValueError, TypeError) as exc:
        raise EnrollmentError("host_observation_config_conflict") from exc


def _install_observation_config(raw: bytes, identities: ServiceIdentities) -> str:
    from ops.executive_os import remote_worker_gateway_service as gateway
    path = gateway.LINUX_HOST_OBSERVATION_CONFIG
    if not _observation_config_adoption(raw, identities):
        # The fixed destination is never replaced. An interruption is reconciled
        # by inspecting this same file; partial or different content conflicts.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            _write_all(fd, raw)
            os.fchown(fd, 0, identities.control_gid)
            os.fchmod(fd, 0o440)
            os.fsync(fd)
        finally:
            os.close(fd)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    if not _observation_config_adoption(raw, identities):
        raise EnrollmentError("host_observation_config_unproven")
    config = gateway.load_remote_worker_gateway_config(path, expected_group_gid=identities.control_gid)
    return gateway.remote_worker_gateway_config_digest(config)


def _apply_host_observation(args: Args, identity, identities: ServiceIdentities) -> dict[str, Any]:
    if (args.hermes_runtime is None or any(value is not None for value in
            (args.codex_source_binary, args.codex_version, args.codex_sha256))):
        raise EnrollmentError("host_observation_component_inputs_invalid")
    raw, config = _observation_input(args, identities)
    _observation_config_adoption(raw, identities)
    replacement = (
        _InertGatewayReplacement(args, raw, config, identities)
        if args.expected_gateway_unit_sha256 is not None else None
    )
    with replacement if replacement is not None else nullcontext():
        role_sha = replacement.role_sha if replacement is not None else args.expected_sha
        expected_units = expected_hermes_role_units(role_sha, args.hermes_runtime)
        _assert_release_input_adoption(args.source_repo, args.expected_sha, args.expected_tree, args.hermes_runtime)
        classify_identity_plan(read_identity_state(), identities, gateway_only=True)
        ensure_service_identities(identities, gateway_only=True)
        ensure_directories(identities, gateway_only=True)
        release = install_release(args.source_repo, args.expected_sha, args.expected_tree,
                                  hermes_runtime=args.hermes_runtime)
        current_raw, _ = _observation_input(args, identities)
        if current_raw != raw:
            raise EnrollmentError("host_observation_input_changed")
        if replacement is None:
            digest = _install_observation_config(raw, identities)
            units = install_inert_units(release, None, identities, gateway_only=True)
        else:
            # Replacement never creates or rewrites the original fixed config.
            from ops.executive_os.remote_worker_gateway_service import remote_worker_gateway_config_digest
            replacement.check()
            digest = remote_worker_gateway_config_digest(config)
            units = install_inert_units(release, None, identities, gateway_only=True,
                                        predecessor=replacement)
        assert_central_control_absent()
        if replacement is not None:
            replacement.check()
        receipt = {
            "schema": "mastermind.linux_secondary_worker_enrollment/v1",
            "component": "hermes-host-observation",
            "outcome": "HOST_OBSERVATION_INSTALLED_INERT",
            "release_sha": identity["commit"], "release_tree": identity["tree"],
            "gateway_config_sha256": args.gateway_config_sha256,
            "gateway_config_canonical_sha256": digest,
            "units_installed_inert": list(units), "services_activated": False,
            "hermes_role_units_expected": expected_units,
        }
        if replacement is not None:
            receipt.update(
                gateway_predecessor_unit_sha256=args.expected_gateway_unit_sha256,
                gateway_unit_sha256=replacement.replacement_sha256,
                gateway_publication_state=("POSTIMAGE_OBSERVED" if replacement.recovered else "PUBLISHED"),
                preserved_role_implementation_sha=role_sha,
            )
        return receipt


def apply_enrollment(args: Args) -> dict[str, Any]:
    if args.hermes_runtime is not None or args.component == "hermes-host-observation":
        _require_hermes_source_checkout(args.source_repo)
    if platform.system() != "Linux":
        raise EnrollmentError("linux_required")
    if os.geteuid() != 0:
        raise EnrollmentError("root_required")
    assert_central_control_absent()
    verify_root_source_custody(args.source_repo)
    identity = verify_source_identity(args.source_repo, args.expected_sha, args.expected_tree)
    identities = load_canonical_identities(args.source_repo)
    if args.component == "hermes-host-observation":
        return _apply_host_observation(args, identity, identities)
    if (args.component != "secondary-worker" or args.codex_source_binary is None
            or type(args.codex_version) is not str or _VERSION.fullmatch(args.codex_version) is None
            or type(args.codex_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", args.codex_sha256) is None
            or args.gateway_config_file is not None or args.gateway_config_sha256 is not None
            or args.expected_gateway_unit_sha256 is not None):
        raise EnrollmentError("secondary_worker_component_inputs_invalid")
    source_info = inspect_codex_source(args.codex_source_binary)
    if source_info["sha256"] != args.codex_sha256:
        raise EnrollmentError("codex_source_digest_not_accepted")
    # The expected role units are rendered before the host is touched, so an
    # unqualified recipe refuses before any mutation instead of after it.
    expected_units = {}
    if args.hermes_runtime is not None:
        expected_units = expected_hermes_role_units(args.expected_sha, args.hermes_runtime)
    # An already installed release must agree with the expected frozen input
    # before this run mutates anything on the host.
    _assert_release_input_adoption(args.source_repo, args.expected_sha,
                                   args.expected_tree, args.hermes_runtime)
    ensure_service_identities(identities)
    ensure_directories(identities)
    release = install_release(args.source_repo, args.expected_sha, args.expected_tree,
                              hermes_runtime=args.hermes_runtime)
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
        "hermes_role_units_expected": expected_units,
    }


def main(argv: Sequence[str] | None = None) -> int:
    ns = _parser().parse_args(list(argv) if argv is not None else None)
    if _HEX40.fullmatch(ns.expected_sha) is None or _HEX40.fullmatch(ns.expected_tree) is None:
        sys.stderr.write("invalid source identity\n")
        return 64
    if ns.component == "secondary-worker":
        if (ns.codex_source_binary is None or type(ns.codex_version) is not str
                or _VERSION.fullmatch(ns.codex_version) is None
                or type(ns.codex_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", ns.codex_sha256) is None
                or ns.gateway_config_file is not None or ns.gateway_config_sha256 is not None
                or ns.expected_gateway_unit_sha256 is not None):
            sys.stderr.write("invalid secondary Worker component inputs\n")
            return 64
    elif (ns.gateway_config_file is None or type(ns.gateway_config_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", ns.gateway_config_sha256) is None
            or any(value is not None for value in (ns.codex_source_binary, ns.codex_version, ns.codex_sha256))
            or (ns.expected_gateway_unit_sha256 is not None and
                re.fullmatch(r"[0-9a-f]{64}", ns.expected_gateway_unit_sha256) is None)):
        sys.stderr.write("invalid host observation component inputs\n")
        return 64
    try:
        hermes_runtime = decode_hermes_runtime(
            ns.hermes_runtime_json, source_repo=ns.source_repo)
    except EnrollmentError as exc:
        sys.stderr.write(f"enrollment refused: {exc}\n")
        return 65
    args = Args(
        source_repo=ns.source_repo,
        expected_sha=ns.expected_sha,
        expected_tree=ns.expected_tree,
        codex_source_binary=ns.codex_source_binary,
        codex_version=ns.codex_version,
        codex_sha256=ns.codex_sha256,
        hermes_runtime=hermes_runtime,
        component=ns.component,
        gateway_config_file=ns.gateway_config_file,
        gateway_config_sha256=ns.gateway_config_sha256,
        expected_gateway_unit_sha256=ns.expected_gateway_unit_sha256,
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
