"""Opt-in real macOS Phase 1C-A launchd and distinct-UID acceptance proof.

This command intentionally mutates only the reviewed Executive OS runtime and
the two fixed launchd jobs. It cannot run in CI: root, dedicated accounts, an
exact clean ``origin/master`` checkout, private worker auth, launchd, and one
real Codex allocation are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import pwd
import grp
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "mastermind.executive_host_acceptance/v1"
CONTROL_LABEL = "com.mastermind.executive.control"
WORKER_LABEL = "com.mastermind.executive.worker.codex"
CONTROL_USER = "_mastermind_exec"
CONTROL_GROUP = "_mastermind_exec"
WORKER_USER = "_mastermind_worker"
WORKER_GROUP = "_mastermind_worker"
OPS_GROUP = "_mastermind_ops"
SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
RUNTIME_ROOT = Path("/var/db/mastermind-executive")
CONTROL_CONFIG = SYSTEM_ROOT / "config" / "control.json"
WORKER_CONFIG = SYSTEM_ROOT / "config" / "worker-codex.json"
CONTROL_PLIST = Path(f"/Library/LaunchDaemons/{CONTROL_LABEL}.plist")
WORKER_PLIST = Path(f"/Library/LaunchDaemons/{WORKER_LABEL}.plist")
CONTROL_SOCKET = Path("/var/run/mastermind-executive/control.sock")
WORKER_SOCKET = Path("/var/run/mastermind-executive/worker.sock")
CONTROL_ENV_CANARY = "EXECUTIVE_CONTROL_CANARY_VALUE"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ACCOUNT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_UUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
_TERMINAL_JOB_STATES = {
    "COMPLETED",
    "FAILED",
    "LOST",
    "CANCELLED",
    "RATE_LIMITED",
}
_ASSIGNMENT_SEAL_SCHEMA = "mastermind.executive_assignment_seal/v1"
_WORKSPACE_ROTATION_SCHEMA = "mastermind.executive_workspace_rotation/v1"


class AcceptanceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _run(
    argv: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    timeout: float = 60.0,
    label: str,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        [os.fspath(value) for value in argv],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env=dict(env) if env is not None else None,
    )
    if check and completed.returncode != 0:
        raise AcceptanceError(f"{label} failed with exit {completed.returncode}")
    return completed


def _json_output(completed: subprocess.CompletedProcess[bytes], *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"{label} did not return valid JSON") from exc
    if not isinstance(value, dict):
        raise AcceptanceError(f"{label} did not return a JSON object")
    return value


def _safe_json(path: Path) -> dict[str, Any]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise AcceptanceError(f"unsafe JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise AcceptanceError(f"JSON file does not contain an object: {path}")
    return value


def _durable_assignment_paths(
    job: Mapping[str, Any],
    attempt: Mapping[str, Any],
    *,
    workspace_root: Path,
    run_root: Path,
) -> tuple[Path, Path]:
    """Resolve assignment roots only from the durable Job and Attempt rows."""

    job_id = job.get("job_id")
    attempt_id = attempt.get("attempt_id")
    workspace_raw = job.get("worktree")
    result_raw = attempt.get("result_path")
    if (
        not isinstance(job_id, str)
        or not isinstance(attempt_id, str)
        or _ID_RE.fullmatch(job_id) is None
        or _ID_RE.fullmatch(attempt_id) is None
        or attempt.get("job_id") != job_id
        or job.get("current_attempt_id") != attempt_id
        or not isinstance(workspace_raw, str)
        or not isinstance(result_raw, str)
    ):
        raise AcceptanceError("durable assignment identity is incomplete")
    workspace = Path(workspace_raw)
    run_dir = Path(result_raw).parent.parent
    if (
        not workspace.is_absolute()
        or workspace.parent != workspace_root
        or run_dir != run_root / attempt_id
        or Path(result_raw) != run_dir / "output" / "result.json"
    ):
        raise AcceptanceError("durable assignment paths escaped their configured roots")
    return workspace, run_dir


def _validate_assignment_seal_payload(
    payload: Mapping[str, Any],
    *,
    job_id: str,
    attempt_id: str,
    workspace: Path,
    run_dir: Path,
    control_uid: int,
    worker_gid: int,
) -> None:
    if (
        set(payload)
        != {
            "schema_version",
            "sealed_at",
            "control_uid",
            "paths",
            "passed",
            "attempt_id",
            "job_id",
            "uid_sweep",
        }
        or not isinstance(payload.get("sealed_at"), str)
        or payload.get("schema_version") != _ASSIGNMENT_SEAL_SCHEMA
        or payload.get("passed") is not True
        or payload.get("job_id") != job_id
        or payload.get("attempt_id") != attempt_id
        or payload.get("control_uid") != control_uid
    ):
        raise AcceptanceError("assignment seal receipt identity drifted")
    paths = payload.get("paths")
    if not isinstance(paths, Mapping) or set(paths) != {"workspace", "run"}:
        raise AcceptanceError("assignment seal receipt path set is incomplete")
    for label, expected_path in (("workspace", workspace), ("run", run_dir)):
        value = paths.get(label)
        before = value.get("before") if isinstance(value, Mapping) else None
        after = value.get("after") if isinstance(value, Mapping) else None
        if (
            not isinstance(value, Mapping)
            or set(value) != {"before", "after", "worker_traversal_revoked"}
            or not isinstance(before, Mapping)
            or not isinstance(after, Mapping)
            or set(before)
            != {"path", "device", "inode", "mode", "uid", "gid", "mtime_ns"}
            or set(after)
            != {"path", "device", "inode", "mode", "uid", "gid", "mtime_ns"}
            or value.get("worker_traversal_revoked") is not True
            or before.get("path") != os.fspath(expected_path)
            or after.get("path") != os.fspath(expected_path)
            or before.get("uid") != control_uid
            or before.get("gid") != worker_gid
            or not isinstance(before.get("mode"), int)
            or before["mode"] & 0o010 == 0
            or after.get("mode") != 0o700
            or after.get("uid") != control_uid
            or after.get("gid") != worker_gid
            or any(before.get(key) != after.get(key) for key in ("device", "inode", "uid", "gid"))
        ):
            raise AcceptanceError(f"assignment seal for {label} is incomplete")
    sweep = payload.get("uid_sweep")
    if (
        not isinstance(sweep, Mapping)
        or sweep.get("schema_version") != "mastermind.executive_uid_sweep/v1"
        or sweep.get("passed") is not True
        or sweep.get("residual_pids_after") != []
    ):
        raise AcceptanceError("assignment seal has no final passing UID sweep")


def _validate_raw_worker_probe_payload(
    value: Mapping[str, Any],
    *,
    expected_labels: set[str],
    worker_uid: int,
    worker_gid: int,
    expect_access: bool,
) -> None:
    supplementary = value.get("supplementary_gids")
    if (
        value.get("schema_version")
        != "mastermind.executive_raw_worker_path_probe/v1"
        or value.get("effective_uid") != worker_uid
        or value.get("real_uid") != worker_uid
        or value.get("effective_gid") != worker_gid
        or value.get("real_gid") != worker_gid
        or not isinstance(supplementary, list)
        or any(not isinstance(group_id, int) for group_id in supplementary)
        or set(supplementary) - {worker_gid}
    ):
        raise AcceptanceError("raw assignment probe used the wrong worker principal")
    results = value.get("results")
    if not isinstance(results, Mapping) or set(results) != expected_labels:
        raise AcceptanceError("raw assignment probe result set drifted")
    for label, operations in results.items():
        if not isinstance(operations, Mapping) or set(operations) != {
            "open",
            "stat",
            "list",
        }:
            raise AcceptanceError(f"raw assignment probe for {label} is incomplete")
        for operation, result in operations.items():
            if not isinstance(result, Mapping) or set(result) != {
                "allowed",
                "error_class",
                "errno_name",
            }:
                raise AcceptanceError("raw assignment probe operation is malformed")
            if expect_access:
                if (
                    result.get("allowed") is not True
                    or result.get("error_class") is not None
                    or result.get("errno_name") is not None
                ):
                    raise AcceptanceError(
                        f"current assignment {label} unexpectedly denied {operation}"
                    )
            elif (
                result.get("allowed") is not False
                or result.get("error_class") != "PermissionError"
                or result.get("errno_name") != "EACCES"
            ):
                raise AcceptanceError(
                    f"sealed assignment {label} did not return EACCES for {operation}"
                )


def _empty_directory(path: Path, *, label: str) -> None:
    if not path.is_dir() or path.is_symlink():
        raise AcceptanceError(f"{label} is not a real directory")
    if any(path.iterdir()):
        raise AcceptanceError(f"{label} is not clean; archive it before acceptance")


def _directory_attribute(record: str, attribute: str) -> str:
    completed = _run(
        ["/usr/bin/dscl", ".", "-read", record, attribute],
        label=f"directory attribute {record} {attribute}",
    )
    text = completed.stdout.decode("utf-8", errors="strict").splitlines()
    if not text or ":" not in text[0]:
        raise AcceptanceError("directory attribute output is malformed")
    return text[0].split(":", 1)[1].strip()


def _directory_values(record: str, attribute: str) -> tuple[str, ...]:
    completed = _run(
        ["/usr/bin/dscl", ".", "-read", record, attribute],
        label=f"directory values {record} {attribute}",
        check=False,
    )
    if completed.returncode != 0:
        return ()
    lines = completed.stdout.decode("utf-8", errors="strict").splitlines()
    if not lines or ":" not in lines[0]:
        return ()
    first = lines[0].split(":", 1)[1].split()
    continuation = [value for line in lines[1:] for value in line.split()]
    return tuple(first + continuation)


def _validate_protected_membership_snapshot(
    snapshot: Mapping[str, Any],
    *,
    control_user: str,
    worker_user: str,
    operator_user: str,
    control_uid: int,
    worker_uid: int,
    operator_uid: int,
    control_gid: int,
    worker_gid: int,
    ops_gid: int,
) -> dict[str, list[str]]:
    """Prove all four macOS membership representations are exact."""

    users = snapshot.get("users")
    groups = snapshot.get("groups")
    group_primary_gids = snapshot.get("group_primary_gids")
    if (
        not isinstance(users, Mapping)
        or not isinstance(groups, Mapping)
        or not isinstance(group_primary_gids, Mapping)
    ):
        raise AcceptanceError("directory membership snapshot is malformed")
    expected = {
        CONTROL_GROUP: (control_gid, {control_user}, set()),
        WORKER_GROUP: (worker_gid, {worker_user}, {control_user}),
        OPS_GROUP: (ops_gid, set(), {operator_user}),
    }
    reviewed_users = {control_user, worker_user, operator_user}
    reviewed_uuids: dict[str, str] = {}
    for name in reviewed_users:
        record = users.get(name)
        generated = record.get("generated_uid") if isinstance(record, Mapping) else None
        if not isinstance(generated, str) or _UUID_RE.fullmatch(generated) is None:
            raise AcceptanceError(f"reviewed account {name} has no valid GeneratedUID")
        reviewed_uuids[name] = generated.upper()
    if len(set(reviewed_uuids.values())) != len(reviewed_uuids):
        raise AcceptanceError("reviewed account GeneratedUID values are not unique")

    for name, uid in (
        (control_user, control_uid),
        (worker_user, worker_uid),
        (operator_user, operator_uid),
    ):
        record = users.get(name)
        if not isinstance(record, Mapping) or record.get("unique_uid") != uid:
            raise AcceptanceError(f"reviewed account {name} UniqueID drifted")
        owners = {
            str(candidate)
            for candidate, candidate_record in users.items()
            if isinstance(candidate_record, Mapping)
            and candidate_record.get("unique_uid") == uid
        }
        if owners != {name}:
            raise AcceptanceError(f"UniqueID {uid} has duplicate or aliased owners")

    for name, gid in (
        (CONTROL_GROUP, control_gid),
        (WORKER_GROUP, worker_gid),
        (OPS_GROUP, ops_gid),
    ):
        owners = {
            str(candidate)
            for candidate, candidate_gid in group_primary_gids.items()
            if candidate_gid == gid
        }
        if owners != {name}:
            raise AcceptanceError(f"protected GID {gid} has duplicate or aliased owners")

    effective: dict[str, list[str]] = {}
    for group_name, (gid, expected_primary, expected_named) in expected.items():
        group = groups.get(group_name)
        if not isinstance(group, Mapping) or group.get("primary_gid") != gid:
            raise AcceptanceError(f"protected group {group_name} identity drifted")
        group_uuid = group.get("generated_uid")
        if not isinstance(group_uuid, str) or _UUID_RE.fullmatch(group_uuid) is None:
            raise AcceptanceError(f"protected group {group_name} has no valid GeneratedUID")
        primary_members = {
            str(name)
            for name, record in users.items()
            if isinstance(record, Mapping) and record.get("primary_gid") == gid
        }
        if primary_members != expected_primary:
            raise AcceptanceError(
                f"protected group {group_name} has hidden primary-GID members"
            )
        named_members = set(group.get("name_members", ()))
        if named_members != expected_named:
            raise AcceptanceError(f"protected group {group_name} named members drifted")
        uuid_members = {str(value).upper() for value in group.get("uuid_members", ())}
        expected_uuids = {reviewed_uuids[name] for name in expected_named}
        if uuid_members != expected_uuids:
            raise AcceptanceError(
                f"protected group {group_name} has UUID-only or stale members"
            )
        if tuple(group.get("nested_groups", ())):
            raise AcceptanceError(f"protected group {group_name} has nested groups")
        effective[group_name] = sorted(primary_members | named_members)
    return effective


def _numeric_directory_census(
    record_type: str, attribute: str, *, label: str
) -> dict[str, int]:
    listed = _run(
        ["/usr/bin/dscl", ".", "-list", f"/{record_type}", attribute],
        label=label,
    ).stdout.decode("utf-8", errors="strict")
    result: dict[str, int] = {}
    for line in listed.splitlines():
        fields = line.rsplit(maxsplit=1)
        if len(fields) != 2:
            raise AcceptanceError(f"{label} is malformed")
        try:
            numeric = int(fields[1])
        except ValueError as exc:
            raise AcceptanceError(f"{label} contains an invalid numeric value") from exc
        if fields[0] in result:
            raise AcceptanceError(f"{label} repeats a directory record")
        result[fields[0]] = numeric
    return result


def _live_directory_membership_snapshot(*, operator_user: str) -> dict[str, Any]:
    user_primary_gids = _numeric_directory_census(
        "Users", "PrimaryGroupID", label="local user primary-GID census"
    )
    user_unique_uids = _numeric_directory_census(
        "Users", "UniqueID", label="local user UniqueID census"
    )
    users: dict[str, dict[str, Any]] = {
        name: {
            "primary_gid": user_primary_gids.get(name),
            "unique_uid": user_unique_uids.get(name),
        }
        for name in set(user_primary_gids) | set(user_unique_uids)
    }
    for name in (CONTROL_USER, WORKER_USER, operator_user):
        if name not in users:
            raise AcceptanceError(f"reviewed account is absent from local census: {name}")
        users[name]["generated_uid"] = _directory_attribute(
            f"/Users/{name}", "GeneratedUID"
        )
    groups: dict[str, dict[str, Any]] = {}
    for name in (CONTROL_GROUP, WORKER_GROUP, OPS_GROUP):
        groups[name] = {
            "primary_gid": int(_directory_attribute(f"/Groups/{name}", "PrimaryGroupID")),
            "generated_uid": _directory_attribute(f"/Groups/{name}", "GeneratedUID"),
            "name_members": _directory_values(f"/Groups/{name}", "GroupMembership"),
            "uuid_members": _directory_values(f"/Groups/{name}", "GroupMembers"),
            "nested_groups": _directory_values(f"/Groups/{name}", "NestedGroups"),
        }
    group_primary_gids = _numeric_directory_census(
        "Groups", "PrimaryGroupID", label="local group PrimaryGroupID census"
    )
    return {
        "users": users,
        "groups": groups,
        "group_primary_gids": group_primary_gids,
    }


def _assert_no_acl(path: Path) -> None:
    mode = _run(
        ["/usr/bin/stat", "-f", "%Sp", path],
        label=f"filesystem ACL check {path}",
    ).stdout.decode("ascii", errors="strict").strip()
    if "+" in mode:
        raise AcceptanceError(f"unexpected filesystem ACL: {path}")


class Acceptance:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.source_repository = args.source_repo.resolve(strict=True)
        self.expected_sha = args.expected_sha
        self.operator_user = args.operator_user
        self.python = Path(sys.executable).resolve(strict=True)
        self.release = SYSTEM_ROOT / "releases" / self.expected_sha
        self.control_identity = pwd.getpwnam(CONTROL_USER)
        self.worker_identity = pwd.getpwnam(WORKER_USER)
        self.operator_identity = pwd.getpwnam(self.operator_user)
        self.control_group = grp.getgrnam(CONTROL_GROUP)
        self.worker_group = grp.getgrnam(WORKER_GROUP)
        self.ops_group = grp.getgrnam(OPS_GROUP)
        self.config: dict[str, Any] = {}
        self.worker_config: dict[str, Any] = {}
        self.receipt_root = RUNTIME_ROOT / "control" / "acceptance" / self.expected_sha
        self.services_started = False
        self.helper: subprocess.Popen[bytes] | None = None
        self.helper_pid: int | None = None
        self.nonexecutive_disabled_before: str | None = None
        self.protected_group_effective: dict[str, list[str]] = {}

    def _service_environment(self, user: str, home: Path) -> list[str]:
        return [
            "/usr/bin/sudo",
            "-u",
            user,
            "/usr/bin/env",
            "-i",
            f"HOME={home}",
            "PYTHONDONTWRITEBYTECODE=1",
            "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG=C.UTF-8",
            "LC_ALL=C.UTF-8",
            "TZ=UTC",
        ]

    def _write_bytes(self, name: str, payload: bytes) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name):
            raise AcceptanceError("unsafe acceptance receipt name")
        destination = self.receipt_root / name
        temporary = self.receipt_root / f".{name}.{os.getpid()}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o400,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short acceptance receipt write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chown(temporary, self.control_identity.pw_uid, self.control_group.gr_gid)
        os.chmod(temporary, 0o400)
        temporary.replace(destination)
        return destination

    def _write_json(self, name: str, value: Any) -> Path:
        payload = (
            json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
        return self._write_bytes(name, payload)

    def _control_request(self, command: str, *values: str, persist: str | None = None) -> dict[str, Any]:
        argv = [
            *self._service_environment(
                self.operator_user,
                Path(self.operator_identity.pw_dir),
            ),
            os.fspath(self.python),
            "-I",
            "-S",
            "-B",
            "-c",
            (
                "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
                "runpy.run_module('scripts.executive_os_phase1c',run_name='__main__')"
            ),
            os.fspath(self.release),
            "--socket",
            os.fspath(CONTROL_SOCKET),
            command,
            *values,
        ]
        completed = _run(
            argv,
            cwd=self.release,
            timeout=90.0,
            label=f"control command {command}",
        )
        response = _json_output(completed, label=f"control command {command}")
        if response.get("ok") is not True or not isinstance(response.get("result"), (dict, list)):
            raise AcceptanceError(f"control command {command} was rejected")
        if persist is not None:
            self._write_json(persist, response)
        return response

    def _broker_status(self, persist: str) -> dict[str, Any]:
        code = (
            "import json,sys; "
            "from control_plane.executive_worker_broker import WorkerBrokerClient; "
            "value=WorkerBrokerClient(sys.argv[1]).request_sync('status',{}); "
            "print(json.dumps(value,sort_keys=True,separators=(',',':')))"
        )
        completed = _run(
            [
                *self._service_environment(
                    CONTROL_USER,
                    Path(self.control_identity.pw_dir),
                ),
                os.fspath(self.python),
                "-I",
                "-S",
                "-B",
                "-c",
                "import sys; sys.path.insert(0,sys.argv.pop(1)); " + code,
                os.fspath(self.release),
                os.fspath(WORKER_SOCKET),
            ],
            cwd=self.release,
            label="worker broker status",
        )
        value = _json_output(completed, label="worker broker status")
        if (
            value.get("worker_uid") != self.worker_identity.pw_uid
            or value.get("worker_gid") != self.worker_group.gr_gid
            or value.get("supplementary_gids") != []
            or not isinstance(value.get("startup_sweep"), dict)
            or value["startup_sweep"].get("passed") is not True
            or value.get("quarantined_reason") is not None
        ):
            raise AcceptanceError("worker broker did not attest the dedicated principal boundary")
        self._write_json(persist, value)
        return value

    def _launchd_pid(self, label: str) -> int | None:
        completed = _run(
            ["/bin/launchctl", "print", f"system/{label}"],
            label=f"launchd status {label}",
            check=False,
        )
        if completed.returncode != 0:
            return None
        match = re.search(rb"(?m)^\s*pid = ([0-9]+)\s*$", completed.stdout)
        return int(match.group(1)) if match is not None else None

    def _nonexecutive_disabled_digest(self) -> str:
        completed = _run(
            ["/bin/launchctl", "print-disabled", "system"],
            label="system launchd disabled-state snapshot",
        )
        payload = b"\n".join(
            line
            for line in completed.stdout.splitlines()
            if CONTROL_LABEL.encode() not in line and WORKER_LABEL.encode() not in line
        )
        return hashlib.sha256(payload).hexdigest()

    def _wait_pid(self, label: str, *, different_from: int | None = None) -> int:
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            pid = self._launchd_pid(label)
            if pid is not None and pid != different_from:
                return pid
            time.sleep(0.25)
        raise AcceptanceError(f"launchd did not produce a new PID for {label}")

    def _wait_control(self, *, different_from: int | None = None) -> int:
        pid = self._wait_pid(CONTROL_LABEL, different_from=different_from)
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            try:
                self._control_request("status")
                return pid
            except AcceptanceError:
                time.sleep(0.25)
        raise AcceptanceError("control service did not become ready")

    def _job(self, job_id: str, *, persist: str | None = None) -> dict[str, Any]:
        response = self._control_request("job", job_id)
        result = response["result"]
        if not isinstance(result, dict) or result.get("job_id") != job_id:
            raise AcceptanceError("job response identity mismatch")
        if persist is not None:
            self._write_json(persist, response)
        return result

    def _wait_job(self, job_id: str, desired: set[str], *, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last = self._job(job_id)
            status = last.get("status")
            if status in desired:
                return last
            if status in _TERMINAL_JOB_STATES and status not in desired:
                raise AcceptanceError(f"job {job_id} reached unexpected terminal state {status}")
            time.sleep(1.0)
        status = last.get("status") if last else "unavailable"
        raise AcceptanceError(f"job {job_id} timed out in state {status}")

    def _assert_attempt_attestation(self, job: Mapping[str, Any], name: str) -> dict[str, Any]:
        attempt_id = job.get("current_attempt_id")
        if not isinstance(attempt_id, str):
            raise AcceptanceError("job has no current attempt identity")
        response = self._control_request("attempt", attempt_id)
        attempt = response["result"]
        if not isinstance(attempt, dict):
            raise AcceptanceError("attempt response is malformed")
        metadata = attempt.get("launch_metadata")
        attestation = metadata.get("launch_attestation") if isinstance(metadata, dict) else None
        required = {
            "schema_version",
            "executable_path",
            "binary",
            "rendered_argv",
            "environment_keys",
            "permission_profile_sha256",
            "prompt_sha256",
            "expected_base_sha",
            "observed_base_sha",
            "workspace_identity",
            "worker_identity",
            "provider_home_identity",
            "secret_canary_verdict",
            "isolation_manifest_sha256",
            "launch_nonce",
            "process_identity",
        }
        if not isinstance(attestation, dict) or not required.issubset(attestation):
            raise AcceptanceError("durable launch attestation is incomplete")
        identity = attestation["process_identity"]
        identity_required = {
            "pid",
            "pgid",
            "session_id",
            "start_identity",
            "boot_id",
            "effective_uid",
            "effective_gid",
            "real_uid",
            "real_gid",
        }
        if not isinstance(identity, dict) or set(identity) != identity_required:
            raise AcceptanceError("durable process identity is incomplete")
        if any(
            identity[key] != expected
            for key, expected in {
                "effective_uid": self.worker_identity.pw_uid,
                "real_uid": self.worker_identity.pw_uid,
                "effective_gid": self.worker_group.gr_gid,
                "real_gid": self.worker_group.gr_gid,
            }.items()
        ):
            raise AcceptanceError("launch attestation has the wrong worker principal")
        if (
            attestation.get("expected_base_sha") != self.expected_sha
            or attestation.get("observed_base_sha") != self.expected_sha
            or attestation.get("secret_canary_verdict", {}).get("passed") is not True
            or re.fullmatch(
                r"[0-9a-f]{64}", str(attestation.get("isolation_manifest_sha256") or "")
            )
            is None
        ):
            raise AcceptanceError("launch attestation does not bind exact SHA and canary")
        self._write_json(name, response)
        return attempt

    def _assert_worker_cannot_list_assignment_roots(self) -> None:
        code = (
            "import errno,os,sys; "
            "bad=[]; "
            "\nfor path in sys.argv[1:]:"
            "\n try: list(os.scandir(path)); bad.append('VISIBLE')"
            "\n except OSError as exc:"
            "\n  if exc.errno not in (errno.EACCES,errno.EPERM): bad.append(type(exc).__name__)"
            "\nraise SystemExit(0 if not bad else 2)"
        )
        _run(
            [
                *self._service_environment(
                    WORKER_USER, Path(self.worker_identity.pw_dir)
                ),
                self.python,
                "-I",
                "-S",
                "-B",
                "-c",
                code,
                self.config["proof_workspace_root"],
                self.config["worker_runs_root"],
            ],
            cwd=self.release,
            label="worker denial for assignment-root directory listings",
        )
        self._write_json(
            "assignment-root-nonlistability.json",
            {
                "passed": True,
                "workspace_root_listing": "DENIED",
                "run_root_listing": "DENIED",
            },
        )

    def _raw_worker_path_probe(
        self, paths: Mapping[str, Path], *, expect_access: bool
    ) -> dict[str, Any]:
        """Probe kernel DAC as the raw worker principal, outside Codex."""

        code = r'''
import errno,json,os,sys
raw=sys.argv[3:]
if len(raw)%2: raise SystemExit(64)
results={}
for index in range(0,len(raw),2):
    label,path=raw[index],raw[index+1]
    operations={}
    probes=(
        ("open",lambda: os.close(os.open(path,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_CLOEXEC",0)))),
        ("stat",lambda: os.stat(os.path.join(path,"."),follow_symlinks=False)),
        ("list",lambda: next(os.scandir(path),None)),
    )
    for operation,probe in probes:
        try:
            probe()
            operations[operation]={"allowed":True,"error_class":None,"errno_name":None}
        except OSError as exc:
            operations[operation]={"allowed":False,"error_class":type(exc).__name__,"errno_name":errno.errorcode.get(exc.errno,"UNKNOWN")}
    results[label]=operations
value={
    "schema_version":"mastermind.executive_raw_worker_path_probe/v1",
    "effective_uid":os.geteuid(),"real_uid":os.getuid(),
    "effective_gid":os.getegid(),"real_gid":os.getgid(),
    "supplementary_gids":sorted(set(os.getgroups())),"results":results,
}
print(json.dumps(value,sort_keys=True,separators=(",",":")))
'''
        argv: list[str | os.PathLike[str]] = [
            *self._service_environment(WORKER_USER, Path(self.worker_identity.pw_dir)),
            self.python,
            "-I",
            "-S",
            "-B",
            "-c",
            code,
            str(self.worker_identity.pw_uid),
            str(self.worker_group.gr_gid),
        ]
        for label, path in sorted(paths.items()):
            argv.extend((label, path))
        completed = _run(
            argv,
            cwd=self.release,
            label="raw worker-UID assignment path probe",
        )
        value = _json_output(completed, label="raw worker-UID assignment path probe")
        _validate_raw_worker_probe_payload(
            value,
            expected_labels=set(paths),
            worker_uid=self.worker_identity.pw_uid,
            worker_gid=self.worker_group.gr_gid,
            expect_access=expect_access,
        )
        return value

    def _assert_terminal_assignment_boundary(
        self,
        job: Mapping[str, Any],
        attempt: Mapping[str, Any],
        *,
        receipt_name: str,
        seal_path: str | None = None,
    ) -> tuple[Path, Path]:
        workspace, run_dir = _durable_assignment_paths(
            job,
            attempt,
            workspace_root=Path(self.config["proof_workspace_root"]),
            run_root=Path(self.config["worker_runs_root"]),
        )
        attempt_id = str(attempt["attempt_id"])
        expected_seal = (
            Path(self.config["receipts_root"])
            / attempt_id
            / "assignment-seal-receipt.json"
        )
        if seal_path is not None and Path(seal_path) != expected_seal:
            raise AcceptanceError("assignment seal receipt path drifted")
        info = expected_seal.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != self.control_identity.pw_uid
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise AcceptanceError("assignment seal receipt is not control-private")
        raw = expected_seal.read_bytes()
        seal = _safe_json(expected_seal)
        _validate_assignment_seal_payload(
            seal,
            job_id=str(job["job_id"]),
            attempt_id=attempt_id,
            workspace=workspace,
            run_dir=run_dir,
            control_uid=self.control_identity.pw_uid,
            worker_gid=self.worker_group.gr_gid,
        )
        probe = self._raw_worker_path_probe(
            {"workspace": workspace, "run": run_dir}, expect_access=False
        )
        self._write_json(
            receipt_name,
            {
                "schema_version": "mastermind.executive_terminal_assignment_boundary/v1",
                "passed": True,
                "job_id": job["job_id"],
                "attempt_id": attempt_id,
                "workspace_path": os.fspath(workspace),
                "run_path": os.fspath(run_dir),
                "assignment_seal_receipt_path": os.fspath(expected_seal),
                "assignment_seal_receipt_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_worker_probe": probe,
            },
        )
        return workspace, run_dir

    def validate_install(self) -> None:
        if os.geteuid() != 0 or sys.platform != "darwin":
            raise AcceptanceError("real host acceptance requires root on macOS")
        if _SHA_RE.fullmatch(self.expected_sha) is None:
            raise AcceptanceError("expected SHA must be exactly 40 lowercase hexadecimal characters")
        if _ACCOUNT_RE.fullmatch(self.operator_user) is None:
            raise AcceptanceError("operator account name is invalid")
        if self.control_identity.pw_uid == self.worker_identity.pw_uid:
            raise AcceptanceError("control and worker service accounts are not distinct")
        expected_accounts = {
            CONTROL_USER: (
                self.control_identity.pw_uid,
                self.control_group.gr_gid,
                os.fspath(RUNTIME_ROOT / "control" / "home"),
            ),
            WORKER_USER: (
                self.worker_identity.pw_uid,
                self.worker_group.gr_gid,
                os.fspath(RUNTIME_ROOT / "workers" / "codex-01" / "provider-home"),
            ),
        }
        for account, (uid, gid, home) in expected_accounts.items():
            expected_attributes = {
                "UniqueID": str(uid),
                "PrimaryGroupID": str(gid),
                "RealName": f"{account} service account",
                "NFSHomeDirectory": home,
                "UserShell": "/usr/bin/false",
                "IsHidden": "1",
                "Password": "*",
                "AuthenticationAuthority": ";DisabledUser;",
            }
            if any(
                _directory_attribute(f"/Users/{account}", key) != expected
                for key, expected in expected_attributes.items()
            ):
                raise AcceptanceError(f"service account {account} attributes drifted")
        operator_groups = os.getgrouplist(
            self.operator_user,
            self.operator_identity.pw_gid,
        )
        if self.ops_group.gr_gid not in operator_groups:
            raise AcceptanceError("operator is not in the reviewed Executive ops group")
        if set(
            os.getgrouplist(CONTROL_USER, self.control_identity.pw_gid)
        ) != {self.control_group.gr_gid, self.worker_group.gr_gid}:
            raise AcceptanceError("control account supplementary groups drifted")
        if set(
            os.getgrouplist(WORKER_USER, self.worker_identity.pw_gid)
        ) != {self.worker_group.gr_gid}:
            raise AcceptanceError("worker account has a supplementary group")
        membership_snapshot = _live_directory_membership_snapshot(
            operator_user=self.operator_user
        )
        self.protected_group_effective = _validate_protected_membership_snapshot(
            membership_snapshot,
            control_user=CONTROL_USER,
            worker_user=WORKER_USER,
            operator_user=self.operator_user,
            control_uid=self.control_identity.pw_uid,
            worker_uid=self.worker_identity.pw_uid,
            operator_uid=self.operator_identity.pw_uid,
            control_gid=self.control_group.gr_gid,
            worker_gid=self.worker_group.gr_gid,
            ops_gid=self.ops_group.gr_gid,
        )

        head = _run(
            ["/usr/bin/git", "-C", self.source_repository, "rev-parse", "HEAD"],
            label="source HEAD",
        ).stdout.decode().strip()
        remote = _run(
            [
                "/usr/bin/git",
                "-C",
                self.source_repository,
                "rev-parse",
                "refs/remotes/origin/master",
            ],
            label="origin/master",
        ).stdout.decode().strip()
        dirty = _run(
            [
                "/usr/bin/git",
                "-C",
                self.source_repository,
                "status",
                "--porcelain=v1",
                "--untracked-files=normal",
            ],
            label="source cleanliness",
        ).stdout
        if head != self.expected_sha or remote != self.expected_sha or dirty:
            raise AcceptanceError("source is not a clean checkout of exact origin/master")
        tree_sha = _run(
            [
                "/usr/bin/git",
                "-C",
                self.source_repository,
                "rev-parse",
                f"{self.expected_sha}^{{tree}}",
            ],
            label="source tree identity",
        ).stdout.decode().strip()
        _run(
            [
                self.python,
                "-I",
                "-S",
                "-B",
                self.release / "ops" / "executive_os" / "release_manifest.py",
                "verify",
                "--root",
                self.release,
                "--commit-sha",
                self.expected_sha,
                "--tree-sha",
                tree_sha,
            ],
            label="installed release manifest",
        )

        self.config = _safe_json(CONTROL_CONFIG)
        self.worker_config = _safe_json(WORKER_CONFIG)
        for config_path, group_gid in (
            (CONTROL_CONFIG, self.control_group.gr_gid),
            (WORKER_CONFIG, self.worker_group.gr_gid),
        ):
            config_info = config_path.lstat()
            if (
                config_info.st_uid != 0
                or config_info.st_gid != group_gid
                or stat.S_IMODE(config_info.st_mode) != 0o440
            ):
                raise AcceptanceError("installed service config ownership or mode drifted")
        for protected_path in (
            SYSTEM_ROOT,
            SYSTEM_ROOT / "config",
            self.release,
            RUNTIME_ROOT,
            RUNTIME_ROOT / "control",
            RUNTIME_ROOT / "jobs",
            Path(self.config["proof_workspace_root"]),
            Path(self.config["worker_runs_root"]),
            Path(self.config["worker_provider_home"]),
            CONTROL_CONFIG,
            WORKER_CONFIG,
            CONTROL_PLIST,
            WORKER_PLIST,
        ):
            _assert_no_acl(protected_path)
        expected_config = {
            "control_uid": self.control_identity.pw_uid,
            "worker_uid": self.worker_identity.pw_uid,
            "worker_gid": self.worker_group.gr_gid,
            "shared_run_gid": self.worker_group.gr_gid,
            "proof_base_sha": self.expected_sha,
            "proof_source_repository": os.fspath(
                RUNTIME_ROOT / "control" / "admin-checkout" / self.expected_sha
            ),
            "proof_workspace_root": os.fspath(RUNTIME_ROOT / "jobs" / "workspaces"),
            "secret_canary_receipt_path": os.fspath(
                RUNTIME_ROOT / "control" / "canaries" / "secret-canary.json"
            ),
        }
        if any(self.config.get(key) != value for key, value in expected_config.items()):
            raise AcceptanceError("installed control config differs from exact host policy")
        if self.operator_identity.pw_uid not in self.config.get("allowed_peer_uids", []):
            raise AcceptanceError("operator UID is not allowed by the control service")
        if (
            self.worker_config.get("worker_uid") != self.worker_identity.pw_uid
            or self.worker_config.get("control_uid") != self.control_identity.pw_uid
            or self.worker_config.get("worker_gid") != self.worker_group.gr_gid
        ):
            raise AcceptanceError("installed worker config differs from exact host policy")
        for shared_root in (
            Path(self.config["proof_workspace_root"]),
            Path(self.config["worker_runs_root"]),
        ):
            root_info = shared_root.lstat()
            if (
                stat.S_ISLNK(root_info.st_mode)
                or not stat.S_ISDIR(root_info.st_mode)
                or root_info.st_uid != self.control_identity.pw_uid
                or root_info.st_gid != self.worker_group.gr_gid
                or stat.S_IMODE(root_info.st_mode) != 0o710
            ):
                raise AcceptanceError("assignment root is not control/worker mode 0710")
        provider_info = Path(self.config["worker_provider_home"]).lstat()
        if (
            stat.S_ISLNK(provider_info.st_mode)
            or not stat.S_ISDIR(provider_info.st_mode)
            or provider_info.st_uid != self.worker_identity.pw_uid
            or provider_info.st_gid != self.worker_group.gr_gid
            or stat.S_IMODE(provider_info.st_mode) != 0o700
        ):
            raise AcceptanceError("dedicated worker provider home policy drifted")

        for plist_path, mode in ((CONTROL_PLIST, 0o644), (WORKER_PLIST, 0o644)):
            info = plist_path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != mode
            ):
                raise AcceptanceError(f"unsafe installed launchd plist: {plist_path}")
        with CONTROL_PLIST.open("rb") as handle:
            control_plist = plistlib.load(handle)
        with WORKER_PLIST.open("rb") as handle:
            worker_plist = plistlib.load(handle)
        expected_control_argv = [
            os.fspath(self.python),
            "-I",
            "-S",
            "-B",
            os.fspath(self.release / "scripts" / "executive_os_phase1c_control_wrapper.py"),
            "--config",
            os.fspath(CONTROL_CONFIG),
            "--sentinel-file",
            os.fspath(SYSTEM_ROOT / "config" / "control-env-canary"),
            "--attestation",
            os.fspath(Path(self.config["control_environment_attestation_path"])),
            "--release-root",
            os.fspath(self.release),
        ]
        expected_worker_argv = [
            os.fspath(self.python),
            "-I",
            "-S",
            "-B",
            os.fspath(self.release / "scripts" / "executive_os_phase1c_worker.py"),
            "serve",
            "--config",
            os.fspath(WORKER_CONFIG),
        ]
        if control_plist.get("ProgramArguments") != expected_control_argv:
            raise AcceptanceError("installed control ProgramArguments drifted")
        if worker_plist.get("ProgramArguments") != expected_worker_argv:
            raise AcceptanceError("installed worker ProgramArguments drifted")
        if (
            control_plist.get("WorkingDirectory") != os.fspath(self.release)
            or worker_plist.get("WorkingDirectory") != os.fspath(self.release)
            or control_plist.get("UserName") != CONTROL_USER
            or worker_plist.get("UserName") != WORKER_USER
        ):
            raise AcceptanceError("installed launchd execution contract drifted")
        if any(
            isinstance(item, str) and "__" in item
            for plist in (control_plist, worker_plist)
            for item in plist.get("ProgramArguments", [])
        ):
            raise AcceptanceError("installed launchd arguments retain placeholders")
        if CONTROL_ENV_CANARY in control_plist.get("EnvironmentVariables", {}):
            raise AcceptanceError("control environment canary value leaked into the launchd plist")
        if CONTROL_ENV_CANARY in worker_plist.get("EnvironmentVariables", {}):
            raise AcceptanceError("worker plist received the control environment canary")
        sentinel_info = (SYSTEM_ROOT / "config" / "control-env-canary").lstat()
        if (
            stat.S_ISLNK(sentinel_info.st_mode)
            or not stat.S_ISREG(sentinel_info.st_mode)
            or sentinel_info.st_uid != 0
            or sentinel_info.st_gid != self.control_group.gr_gid
            or stat.S_IMODE(sentinel_info.st_mode) != 0o440
        ):
            raise AcceptanceError("control environment canary file is not root/control 0440")

        database = Path(self.config["runtime_root"]) / "data" / "control_plane" / "executive.sqlite3"
        if database.exists() or database.is_symlink():
            raise AcceptanceError("Executive runtime is not clean; archive it before acceptance")
        for field, label in (
            ("proof_workspace_root", "proof workspace root"),
            ("worker_runs_root", "worker runs root"),
            ("receipts_root", "launch receipts root"),
            ("backup_root", "backup root"),
        ):
            _empty_directory(Path(self.config[field]), label=label)
        if Path(self.config["secret_canary_receipt_path"]).exists():
            raise AcceptanceError("a prior secret-canary receipt exists")
        if self.receipt_root.exists() or self.receipt_root.is_symlink():
            raise AcceptanceError("an acceptance directory already exists for this SHA")
        self.receipt_root.mkdir(parents=True, mode=0o700)
        os.chown(self.receipt_root, self.control_identity.pw_uid, self.control_group.gr_gid)
        os.chmod(self.receipt_root, 0o700)
        self.nonexecutive_disabled_before = self._nonexecutive_disabled_digest()
        self._write_json(
            "nonexecutive-launchd-before.json",
            {"sha256": self.nonexecutive_disabled_before, "labels_excluded": 2},
        )
        self._write_json(
            "protected-group-membership.json",
            {
                "passed": True,
                "effective_members": self.protected_group_effective,
                "primary_gid_census": "COMPLETE",
                "name_members": "EXACT",
                "uuid_members": "EXACT",
                "nested_groups": "ABSENT",
            },
        )

    def _create_sentinel(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            value = (secrets.token_hex(32) + "\n").encode("ascii")
            os.write(descriptor, value)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chown(path, self.control_identity.pw_uid, self.control_group.gr_gid)
        os.chmod(path, 0o600)

    def initialize_runtime_and_fixtures(self) -> None:
        control_home = Path(self.control_identity.pw_dir)
        runtime_root = Path(self.config["runtime_root"])
        _run(
            [
                *self._service_environment(CONTROL_USER, control_home),
                self.python,
                "-I",
                "-S",
                "-B",
                "-c",
                (
                    "import sys; sys.path.insert(0,sys.argv[1]); "
                    "from control_plane.executive_runtime import RuntimeStore; RuntimeStore(sys.argv[2])"
                ),
                os.fspath(self.release),
                runtime_root,
            ],
            cwd=self.release,
            label="control-principal database initialization",
        )
        database = runtime_root / "data" / "control_plane" / "executive.sqlite3"
        if not database.is_file():
            raise AcceptanceError("control principal did not initialize the Executive database")

        admin_sentinel = (
            Path(self.config["proof_source_repository"])
            / ".git"
            / "executive-secret-canary"
        )
        other_sentinel = (
            RUNTIME_ROOT / "canary-fixtures" / "other-worker-home" / "sentinel"
        )
        production_sentinel = (
            RUNTIME_ROOT / "canary-fixtures" / "production-like" / "sentinel"
        )
        protected = [admin_sentinel, other_sentinel, production_sentinel]
        for path in protected:
            self._create_sentinel(path)

    def install_secret_canary_receipt(
        self,
        *,
        environment_probe: Mapping[str, Any],
        environment_probe_sha256: str,
    ) -> None:
        runtime_root = Path(self.config["runtime_root"])
        database = runtime_root / "data" / "control_plane" / "executive.sqlite3"
        admin_sentinel = (
            Path(self.config["proof_source_repository"])
            / ".git"
            / "executive-secret-canary"
        )
        other_sentinel = RUNTIME_ROOT / "canary-fixtures" / "other-worker-home" / "sentinel"
        production_sentinel = RUNTIME_ROOT / "canary-fixtures" / "production-like" / "sentinel"
        canary_argv = [
            *self._service_environment(
                WORKER_USER,
                Path(self.worker_identity.pw_dir),
            ),
            self.python,
            "-I",
            "-S",
            "-B",
            self.release / "scripts" / "executive_os_phase1c_canary.py",
            "--expected-worker-uid",
            str(self.worker_identity.pw_uid),
            "--expected-worker-gid",
            str(self.worker_group.gr_gid),
            "--control-uid",
            str(self.control_identity.pw_uid),
            "--control-gid",
            str(self.control_group.gr_gid),
            "--control-env-sentinel",
            CONTROL_ENV_CANARY,
            "--control-environment-probe-sha256",
            environment_probe_sha256,
            "--administrative-checkout-sentinel",
            admin_sentinel,
            "--executive-database",
            database,
            "--other-worker-home-sentinel",
            other_sentinel,
            "--forbidden-production-sentinel",
            production_sentinel,
            "--codex-home",
            self.config["worker_provider_home"],
        ]
        completed = _run(
            canary_argv,
            cwd=self.release,
            label="distinct-principal secret canary",
        )
        receipt = _json_output(completed, label="secret canary")
        if receipt.get("passed") is not True:
            raise AcceptanceError("secret canary did not pass")
        destination = Path(self.config["secret_canary_receipt_path"])
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        envelope = {
            "schema_version": "mastermind.executive_secret_canary_envelope/v1",
            "secret_canary": receipt,
            "control_environment_probe": dict(environment_probe),
            "control_environment_probe_sha256": environment_probe_sha256,
        }
        temporary.write_bytes(
            (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )
        os.chown(temporary, self.control_identity.pw_uid, self.control_group.gr_gid)
        os.chmod(temporary, 0o400)
        temporary.replace(destination)
        self._write_json("secret-canary-envelope.json", envelope)

    def _assert_process_principal(self, pid: int, uid: int, gid: int, label: str) -> None:
        completed = _run(
            ["/bin/ps", "-o", "uid=,gid=,pid=,pgid=,sess=", "-p", str(pid)],
            label=f"{label} process identity",
        )
        fields = completed.stdout.decode("ascii", errors="strict").split()
        if len(fields) != 5 or int(fields[0]) != uid or int(fields[1]) != gid:
            raise AcceptanceError(f"{label} process is running under the wrong principal")

    def _assert_environment_boundary(
        self, control_pid: int, worker_pid: int
    ) -> tuple[dict[str, Any], str]:
        attestation = _safe_json(Path(self.config["control_environment_attestation_path"]))
        identity = attestation.get("process_identity")
        if (
            attestation.get("schema_version")
            != "mastermind.executive_control_environment_attestation/v1"
            or attestation.get("sentinel_present") is not True
            or not isinstance(identity, dict)
            or identity.get("pid") != control_pid
            or identity.get("effective_uid") != self.control_identity.pw_uid
            or identity.get("real_uid") != self.control_identity.pw_uid
        ):
            raise AcceptanceError("control environment attestation is not bound to the live service")
        value_sha = attestation.get("sentinel_value_sha256")
        if not isinstance(value_sha, str) or re.fullmatch(r"[0-9a-f]{64}", value_sha) is None:
            raise AcceptanceError("control environment attestation has no value commitment")
        probe = _run(
            [
                *self._service_environment(
                    WORKER_USER,
                    Path(self.worker_identity.pw_dir),
                ),
                self.python,
                "-I",
                "-S",
                "-B",
                self.release / "scripts" / "executive_os_phase1c_env_probe.py",
                "--pid",
                str(control_pid),
                "--label",
                CONTROL_LABEL,
                "--sentinel-name",
                CONTROL_ENV_CANARY,
                "--sentinel-value-sha256",
                value_sha,
                "--config-sha256",
                attestation["config_sha256"],
                "--release-manifest-sha256",
                attestation["release_manifest_sha256"],
                "--expected-worker-uid",
                str(self.worker_identity.pw_uid),
                "--expected-worker-gid",
                str(self.worker_group.gr_gid),
            ],
            cwd=self.release,
            label="worker-principal live control environment probe",
        )
        probe_receipt = _json_output(probe, label="worker-principal environment probe")
        if probe_receipt.get("passed") is not True:
            raise AcceptanceError("worker-principal environment probe did not pass")
        self._write_json(f"control-environment-probe-{control_pid}.json", probe_receipt)
        probe_sha256 = _canonical_json_sha256(probe_receipt)
        denied = _run(
            [
                *self._service_environment(
                    WORKER_USER,
                    Path(self.worker_identity.pw_dir),
                ),
                self.python,
                "-I",
                "-S",
                "-B",
                "-c",
                (
                    "import errno,os,sys; "
                    "\ntry: os.open(sys.argv[1],os.O_RDONLY); raise SystemExit(2)"
                    "\nexcept OSError as exc: raise SystemExit(0 if exc.errno in (errno.EACCES,errno.EPERM) else 3)"
                ),
                SYSTEM_ROOT / "config" / "control-env-canary",
            ],
            cwd=self.release,
            label="worker denial for private control environment file",
        )
        if denied.returncode != 0:
            raise AcceptanceError("worker could read the private control environment file")
        return probe_receipt, probe_sha256

    def _activate_live_canary(self, control_pid: int, worker_pid: int) -> None:
        status = self._control_request("status")
        if status["result"].get("service_state") != "AWAITING_CANARY":
            raise AcceptanceError("new control process did not enter canary quarantine")
        environment_probe, environment_probe_sha256 = self._assert_environment_boundary(
            control_pid, worker_pid
        )
        self.install_secret_canary_receipt(
            environment_probe=environment_probe,
            environment_probe_sha256=environment_probe_sha256,
        )
        try:
            os.kill(control_pid, signal.SIGHUP)
        except ProcessLookupError as exc:
            raise AcceptanceError("control service disappeared before canary reload") from exc
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if self._launchd_pid(CONTROL_LABEL) != control_pid:
                raise AcceptanceError("SIGHUP canary reload changed the live control PID")
            try:
                state = self._control_request("status")["result"]
            except AcceptanceError:
                time.sleep(0.25)
                continue
            if state.get("service_state") == "READY":
                return
            time.sleep(0.25)
        raise AcceptanceError("live control service did not reload the canary envelope")

    def start_and_attest_services(self) -> tuple[int, int]:
        _run(
            ["/bin/bash", self.release / "ops" / "executive_os" / "service-control.sh", "start"],
            label="Executive service start",
        )
        self.services_started = True
        control_pid = self._wait_control()
        worker_pid = self._wait_pid(WORKER_LABEL)
        self._assert_process_principal(
            control_pid,
            self.control_identity.pw_uid,
            self.control_group.gr_gid,
            "control",
        )
        self._assert_process_principal(
            worker_pid,
            self.worker_identity.pw_uid,
            self.worker_group.gr_gid,
            "worker",
        )
        status = self._control_request("status", persist="awaiting-canary-status.json")
        if status["result"].get("service_state") != "AWAITING_CANARY":
            raise AcceptanceError("control service did not start in AWAITING_CANARY quarantine")
        self._activate_live_canary(control_pid, worker_pid)
        broker = self._broker_status("worker-broker-startup.json")
        self._assert_worker_cannot_list_assignment_roots()
        self._write_json(
            "launchd-principals.json",
            {
                "control": {"pid": control_pid, "uid": self.control_identity.pw_uid},
                "worker": {
                    "pid": worker_pid,
                    "uid": self.worker_identity.pw_uid,
                    "gid": self.worker_group.gr_gid,
                    "supplementary_gids": broker["supplementary_gids"],
                },
            },
        )
        status = _run(
            ["/bin/bash", self.release / "ops" / "executive_os" / "status.sh"],
            label="host service status",
        )
        self._write_bytes("host-status.txt", status.stdout)
        return control_pid, worker_pid

    def successful_job(self) -> str:
        self._control_request("health", persist="health-before-success.json")
        self._control_request("register-worker", persist="registered-worker.json")
        created = self._control_request("create-proof-job", persist="success-job-created.json")
        job_id = created["result"].get("job_id")
        if not isinstance(job_id, str):
            raise AcceptanceError("proof job creation returned no job identity")
        self._control_request("dispatch", job_id, persist="success-dispatch.json")
        job = self._wait_job(
            job_id,
            {"COMPLETED"},
            timeout=self.args.success_timeout,
        )
        if not job.get("checkpoint"):
            raise AcceptanceError("successful job has no durable checkpoint")
        self._write_json("success-job-final.json", {"ok": True, "result": job})
        attempt = self._assert_attempt_attestation(job, "success-attempt.json")
        self._assert_terminal_assignment_boundary(
            job,
            attempt,
            receipt_name="success-terminal-assignment-boundary.json",
        )
        broker = self._broker_status("worker-broker-after-success.json")
        sweep = broker.get("last_sweep")
        if not isinstance(sweep, dict) or sweep.get("passed") is not True:
            raise AcceptanceError("successful job has no passing dedicated-UID sweep")
        self._write_json("success-uid-sweep.json", sweep)
        return job_id

    def restart_after_completion(self, job_id: str, old_pid: int) -> int:
        _run(
            ["/bin/launchctl", "kickstart", "-k", f"system/{CONTROL_LABEL}"],
            label="control restart after completion",
        )
        new_pid = self._wait_control(different_from=old_pid)
        self._activate_live_canary(new_pid, self._wait_pid(WORKER_LABEL))
        job = self._job(job_id, persist="success-job-after-restart.json")
        if job.get("status") != "COMPLETED":
            raise AcceptanceError("completed job was not reconstructed after service restart")
        self._write_json(
            "completed-restart.json",
            {"old_pid": old_pid, "new_pid": new_pid, "job_id": job_id, "status": "PASS"},
        )
        return new_pid

    def _spawn_detached_helper(self) -> int:
        helper_pid_path = RUNTIME_ROOT / "workers" / "codex-01" / "state" / "acceptance-helper.pid"
        helper_pid_path.unlink(missing_ok=True)
        token = f"phase1c-setsid-{uuid.uuid4().hex}"
        code = (
            "import os,pathlib,sys,time; "
            "os.setsid(); p=pathlib.Path(sys.argv[1]); "
            "p.write_text(str(os.getpid())+'\\n',encoding='ascii'); p.chmod(0o600); "
            "time.sleep(1800)"
        )
        self.helper = subprocess.Popen(
            [
                *self._service_environment(
                    WORKER_USER,
                    Path(self.worker_identity.pw_dir),
                ),
                os.fspath(self.python),
                "-c",
                code,
                os.fspath(helper_pid_path),
                token,
            ],
            cwd=self.release,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if helper_pid_path.is_file():
                try:
                    pid = int(helper_pid_path.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    time.sleep(0.1)
                    continue
                if pid > 1:
                    self.helper_pid = pid
                    return pid
            if self.helper.poll() is not None:
                break
            time.sleep(0.1)
        raise AcceptanceError("detached-session fault helper did not start")

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def interrupted_job(self, old_control_pid: int) -> tuple[str, int]:
        created = self._control_request("create-proof-job", persist="interrupted-job-created.json")
        job_id = created["result"].get("job_id")
        if not isinstance(job_id, str):
            raise AcceptanceError("interrupted proof job creation returned no identity")
        self._control_request("dispatch", job_id, persist="interrupted-dispatch.json")
        running = self._wait_job(
            job_id,
            {"RUNNING", "CHECKPOINTED"},
            timeout=self.args.active_timeout,
        )
        if not running.get("checkpoint"):
            raise AcceptanceError("active attempt crossed RUNNING without a durable checkpoint")
        interrupted_attempt_id = running.get("current_attempt_id")
        if not isinstance(interrupted_attempt_id, str):
            raise AcceptanceError("active proof job has no durable attempt identity")
        self._assert_attempt_attestation(running, "interrupted-attempt-before-kill.json")
        helper_pid = self._spawn_detached_helper()
        still_active = self._job(job_id)
        if still_active.get("status") not in {"RUNNING", "CHECKPOINTED"}:
            raise AcceptanceError("proof job finished before abrupt-restart fault injection")
        _run(
            ["/bin/launchctl", "kill", "SIGKILL", f"system/{CONTROL_LABEL}"],
            label="abrupt active control-service kill",
        )
        new_pid = self._wait_control(different_from=old_control_pid)
        self._activate_live_canary(new_pid, self._wait_pid(WORKER_LABEL))
        lost = self._wait_job(job_id, {"LOST"}, timeout=90.0)
        if not lost.get("checkpoint"):
            raise AcceptanceError("LOST attempt did not preserve its checkpoint")
        self._write_json("interrupted-job-lost.json", {"ok": True, "result": lost})
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and self._pid_exists(helper_pid):
            time.sleep(0.1)
        if self._pid_exists(helper_pid):
            raise AcceptanceError("detached-session worker process survived the UID sweep")

        restart_status = self._control_request(
            "status", persist="interrupted-restart-status.json"
        )["result"]
        outcomes = restart_status.get("startup_reconciliation")
        outcome = next(
            (
                item
                for item in outcomes
                if isinstance(item, dict)
                and item.get("attempt_id") == interrupted_attempt_id
            ),
            None,
        ) if isinstance(outcomes, list) else None
        evidence_path_raw = (
            outcome.get("uid_sweep_receipt_path") if isinstance(outcome, dict) else None
        )
        if not isinstance(evidence_path_raw, str):
            raise AcceptanceError("restart reconciliation has no control-owned UID evidence")
        evidence_path = Path(evidence_path_raw)
        evidence_info = evidence_path.lstat()
        if (
            stat.S_ISLNK(evidence_info.st_mode)
            or not stat.S_ISREG(evidence_info.st_mode)
            or evidence_info.st_uid != self.control_identity.pw_uid
            or stat.S_IMODE(evidence_info.st_mode) & 0o077
        ):
            raise AcceptanceError("restart reconciliation UID evidence is not control-private")
        evidence = _safe_json(evidence_path)
        sweep = evidence.get("uid_sweep")
        terminal_sweep = (
            sweep.get("preceding_terminal_sweep") if isinstance(sweep, dict) else None
        )
        if (
            not isinstance(sweep, dict)
            or sweep.get("passed") is not True
            or sweep.get("residual_pids_after") != []
            or sweep.get("reason") != "status_absence"
            or not isinstance(terminal_sweep, dict)
            or terminal_sweep.get("schema_version")
            != "mastermind.executive_uid_sweep/v1"
            or terminal_sweep.get("passed") is not True
            or terminal_sweep.get("reason") != "run_terminal"
            or helper_pid not in terminal_sweep.get("residual_pids_before", [])
            or terminal_sweep.get("residual_pids_after") != []
        ):
            raise AcceptanceError("control-owned terminal and fresh UID sweeps did not pass")
        self._write_json("interrupted-reconciliation-evidence.json", evidence)

        seal_path_raw = (
            outcome.get("assignment_seal_receipt_path")
            if isinstance(outcome, dict)
            else None
        )
        if not isinstance(seal_path_raw, str):
            raise AcceptanceError("restart reconciliation has no assignment seal evidence")
        lost_attempt_response = self._control_request("attempt", interrupted_attempt_id)
        lost_attempt = lost_attempt_response["result"]
        if not isinstance(lost_attempt, dict):
            raise AcceptanceError("LOST attempt response is malformed")
        prior_workspace, _prior_run = self._assert_terminal_assignment_boundary(
            lost,
            lost_attempt,
            receipt_name="lost-terminal-assignment-boundary.json",
            seal_path=seal_path_raw,
        )

        requeued_response = self._control_request(
            "requeue",
            job_id,
            persist="interrupted-job-requeued.json",
        )
        requeued = requeued_response["result"]
        if not isinstance(requeued, dict) or requeued.get("status") != "QUEUED":
            raise AcceptanceError("LOST proof job was not explicitly requeued")
        rotation = requeued.get("workspace_rotation")
        if (
            not isinstance(rotation, dict)
            or rotation.get("schema_version") != _WORKSPACE_ROTATION_SCHEMA
            or rotation.get("workspace_path") != os.fspath(prior_workspace)
            or not isinstance(rotation.get("archive_path"), str)
            or not isinstance(rotation.get("receipt_path"), str)
        ):
            raise AcceptanceError("workspace rotation evidence is incomplete")
        archive_path = Path(rotation["archive_path"])
        expected_archive = (
            Path(self.config["proof_workspace_root"])
            / ".lost-attempts"
            / job_id
            / interrupted_attempt_id
        )
        if archive_path != expected_archive:
            raise AcceptanceError("archived prior workspace path drifted")
        rotation_receipt_path = Path(rotation["receipt_path"])
        rotation_info = rotation_receipt_path.lstat()
        archive_info = archive_path.lstat()
        fresh_info = prior_workspace.lstat()
        if (
            stat.S_ISLNK(rotation_info.st_mode)
            or not stat.S_ISREG(rotation_info.st_mode)
            or rotation_info.st_nlink != 1
            or rotation_info.st_uid != self.control_identity.pw_uid
            or stat.S_IMODE(rotation_info.st_mode) & 0o077
            or not stat.S_ISDIR(archive_info.st_mode)
            or archive_info.st_uid != self.control_identity.pw_uid
            or stat.S_IMODE(archive_info.st_mode) != 0o700
            or not stat.S_ISDIR(fresh_info.st_mode)
            or fresh_info.st_uid != self.control_identity.pw_uid
            or fresh_info.st_gid != self.worker_group.gr_gid
            or stat.S_IMODE(fresh_info.st_mode) & 0o070 != 0o050
        ):
            raise AcceptanceError("workspace rotation DAC boundary drifted")
        rotation_receipt_raw = rotation_receipt_path.read_bytes()
        rotation_receipt_sha256 = hashlib.sha256(rotation_receipt_raw).hexdigest()
        rotation_receipt = _safe_json(rotation_receipt_path)
        if (
            rotation.get("receipt_sha256") != rotation_receipt_sha256
            or rotation_receipt.get("schema_version") != _WORKSPACE_ROTATION_SCHEMA
            or rotation_receipt.get("job_id") != job_id
            or rotation_receipt.get("attempt_id") != interrupted_attempt_id
            or rotation_receipt.get("workspace_path") != os.fspath(prior_workspace)
            or rotation_receipt.get("archive_path") != os.fspath(archive_path)
        ):
            raise AcceptanceError("workspace rotation receipt identity drifted")
        archived_probe = self._raw_worker_path_probe(
            {"archived_workspace": archive_path}, expect_access=False
        )
        self._write_json(
            "requeue-workspace-rotation-boundary.json",
            {
                "schema_version": "mastermind.executive_requeue_workspace_boundary/v1",
                "passed": True,
                "job_id": job_id,
                "lost_attempt_id": interrupted_attempt_id,
                "archived_workspace_path": os.fspath(archive_path),
                "fresh_workspace_path": os.fspath(prior_workspace),
                "rotation_receipt_path": os.fspath(rotation_receipt_path),
                "rotation_receipt_sha256": rotation_receipt_sha256,
                "archived_raw_worker_probe": archived_probe,
            },
        )
        dispatch_response = self._control_request(
            "dispatch", job_id, persist="requeued-dispatch.json"
        )
        dispatch_result = dispatch_response["result"]
        dispatched_attempt = (
            dispatch_result.get("attempt") if isinstance(dispatch_result, dict) else None
        )
        fresh_attempt_id = (
            dispatched_attempt.get("attempt_id")
            if isinstance(dispatched_attempt, dict)
            else None
        )
        if (
            not isinstance(fresh_attempt_id, str)
            or dispatched_attempt.get("job_id") != job_id
            or fresh_attempt_id == interrupted_attempt_id
        ):
            raise AcceptanceError("requeued dispatch returned no fresh attempt identity")
        fresh_probe = self._raw_worker_path_probe(
            {"current_workspace": prior_workspace}, expect_access=True
        )
        self._write_json(
            "requeue-active-assignment-boundary.json",
            {
                "schema_version": "mastermind.executive_active_assignment_boundary/v1",
                "passed": True,
                "job_id": job_id,
                "attempt_id": fresh_attempt_id,
                "workspace_path": os.fspath(prior_workspace),
                "raw_worker_probe": fresh_probe,
            },
        )
        completed = self._wait_job(
            job_id,
            {"COMPLETED"},
            timeout=self.args.success_timeout,
        )
        self._write_json("requeued-job-final.json", {"ok": True, "result": completed})
        completed_attempt = self._assert_attempt_attestation(
            completed, "requeued-attempt.json"
        )
        if completed_attempt.get("attempt_id") != fresh_attempt_id:
            raise AcceptanceError("requeued completion changed the active attempt identity")
        self._assert_terminal_assignment_boundary(
            completed,
            completed_attempt,
            receipt_name="requeued-terminal-assignment-boundary.json",
        )
        archive_after_terminal = self._raw_worker_path_probe(
            {"archived_workspace": archive_path}, expect_access=False
        )
        self._write_json(
            "requeued-archive-still-denied.json",
            {
                "schema_version": "mastermind.executive_archived_workspace_boundary/v1",
                "passed": True,
                "job_id": job_id,
                "lost_attempt_id": interrupted_attempt_id,
                "completed_attempt_id": completed_attempt["attempt_id"],
                "archived_workspace_path": os.fspath(archive_path),
                "raw_worker_probe": archive_after_terminal,
            },
        )
        return job_id, new_pid

    def backup_restore(self, expected_jobs: Sequence[str]) -> None:
        backup = self._control_request("backup", persist="backup-created.json")
        result = backup["result"]
        database_path = result.get("database_path") if isinstance(result, dict) else None
        if not isinstance(database_path, str):
            raise AcceptanceError("online backup returned no database path")
        name = Path(database_path).name
        self._control_request("verify-backup", name, persist="backup-verified.json")

        _run(
            ["/bin/bash", self.release / "ops" / "executive_os" / "service-control.sh", "stop"],
            label="graceful stop before restore",
        )
        self.services_started = False
        offline_prefix = [
            *self._service_environment(
                CONTROL_USER,
                Path(self.control_identity.pw_dir),
            ),
            self.python,
            "-I",
            "-S",
            "-B",
            "-c",
            (
                "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
                "runpy.run_module('scripts.executive_os_phase1c',run_name='__main__')"
            ),
            self.release,
        ]
        for command, receipt in (
            ("restore-verify", "restore-drill.json"),
            ("restore-backup", "restore-applied.json"),
        ):
            completed = _run(
                [*offline_prefix, command, "--config", CONTROL_CONFIG, name],
                cwd=self.release,
                timeout=120.0,
                label=command,
            )
            self._write_json(receipt, _json_output(completed, label=command))
        _run(
            ["/bin/bash", self.release / "ops" / "executive_os" / "service-control.sh", "start"],
            label="service start after restore",
        )
        self.services_started = True
        control_pid = self._wait_control()
        self._activate_live_canary(control_pid, self._wait_pid(WORKER_LABEL))
        self._control_request("health", persist="health-after-restore.json")
        for index, job_id in enumerate(expected_jobs, 1):
            job = self._job(job_id, persist=f"restored-job-{index}.json")
            if job.get("status") != "COMPLETED":
                raise AcceptanceError("restored database lost completed job history")

    def _assert_no_public_listener(self) -> None:
        for account in (CONTROL_USER, WORKER_USER):
            completed = _run(
                [
                    "/usr/sbin/lsof",
                    "-nP",
                    "-a",
                    "-u",
                    account,
                    "-iTCP",
                    "-sTCP:LISTEN",
                ],
                label=f"TCP listener scan for {account}",
                check=False,
            )
            lines = completed.stdout.splitlines()
            if len(lines) > 1:
                raise AcceptanceError(f"{account} owns a TCP listener")
        if not CONTROL_SOCKET.is_socket() or not WORKER_SOCKET.is_socket():
            raise AcceptanceError("private Unix launchd sockets are unavailable")

    def _sentinel_sources(self) -> list[Path]:
        return [
            SYSTEM_ROOT / "config" / "control-env-canary",
            Path(self.config["proof_source_repository"])
            / ".git"
            / "executive-secret-canary",
            RUNTIME_ROOT / "canary-fixtures" / "other-worker-home" / "sentinel",
            RUNTIME_ROOT / "canary-fixtures" / "production-like" / "sentinel",
        ]

    def leakage_scan(self, control_pid: int) -> None:
        values: list[bytes] = []
        for source in self._sentinel_sources():
            if source.is_file():
                values.append(source.read_bytes().strip())
        if any(not value for value in values):
            raise AcceptanceError("empty canary value invalidates leakage scanning")

        scan_roots = [
            Path("/var/log/mastermind-executive"),
            Path(self.config["runtime_root"]),
            Path(self.config["receipts_root"]),
            Path(self.config["worker_runs_root"]),
            Path(self.config["proof_workspace_root"]),
            self.receipt_root,
        ]
        excluded = {path.resolve(strict=False) for path in self._sentinel_sources()}
        leaks: list[str] = []
        for root in scan_roots:
            if not root.exists():
                continue
            for directory, _names, filenames in os.walk(root, followlinks=False):
                for filename in filenames:
                    path = Path(directory) / filename
                    if path.resolve(strict=False) in excluded:
                        continue
                    try:
                        payload = path.read_bytes()
                    except (OSError, MemoryError):
                        continue
                    if any(value in payload for value in values):
                        leaks.append(os.fspath(path))
        process_table = _run(
            ["/bin/ps", "eww", "-axo", "pid=,command="],
            label="process argv/environment leakage scan",
        ).stdout.splitlines()
        for line in process_table:
            fields = line.lstrip().split(maxsplit=1)
            if not fields:
                continue
            try:
                pid = int(fields[0])
            except ValueError:
                continue
            if pid == control_pid:
                continue  # the private control environment is the intended source.
            if any(value in line for value in values):
                leaks.append(f"process:{pid}")
        if leaks:
            self._write_json("leakage-failures.json", {"locations": sorted(set(leaks))})
            raise AcceptanceError("a canary value escaped into a receipt, artifact, log, or process")
        self._write_json(
            "leakage-scan.json",
            {
                "passed": True,
                "value_count": len(values),
                "control_environment_source_excluded": True,
                "locations_with_values": 0,
            },
        )

    def run(self) -> None:
        self.validate_install()
        self.initialize_runtime_and_fixtures()
        control_pid, _worker_pid = self.start_and_attest_services()
        success_job_id = self.successful_job()
        control_pid = self.restart_after_completion(success_job_id, control_pid)
        interrupted_job_id, control_pid = self.interrupted_job(control_pid)
        self.backup_restore((success_job_id, interrupted_job_id))
        control_pid = self._wait_control()
        self._wait_pid(WORKER_LABEL)
        if self._control_request("status")["result"].get("service_state") != "READY":
            raise AcceptanceError("final control service is not READY")
        nonexecutive_after = self._nonexecutive_disabled_digest()
        if (
            self.nonexecutive_disabled_before is None
            or nonexecutive_after != self.nonexecutive_disabled_before
        ):
            raise AcceptanceError("a non-Executive launchd disabled state changed during proof")
        self._write_json(
            "nonexecutive-launchd-after.json",
            {"sha256": nonexecutive_after, "unchanged": True, "labels_excluded": 2},
        )
        self._assert_no_public_listener()
        self.leakage_scan(control_pid)
        final_status = _run(
            ["/bin/bash", self.release / "ops" / "executive_os" / "status.sh"],
            label="final host status",
        )
        self._write_bytes("final-host-status.txt", final_status.stdout)
        self._write_json(
            "acceptance-summary.json",
            {
                "schema_version": SCHEMA_VERSION,
                "passed": True,
                "observed_at": _now(),
                "exact_origin_master_sha": self.expected_sha,
                "release_root": os.fspath(self.release),
                "control_uid": self.control_identity.pw_uid,
                "worker_uid": self.worker_identity.pw_uid,
                "success_job_id": success_job_id,
                "interrupted_requeued_job_id": interrupted_job_id,
                "detached_session_cleanup": "PASS",
                "terminal_assignment_sealing": "PASS",
                "lost_workspace_rotation_boundary": "PASS",
                "backup_restore": "PASS",
                "no_public_listener": "PASS",
                "credential_leakage_scan": "PASS",
                "financial_scheduler_activation": "NOT_REQUESTED_OR_TOUCHED",
            },
        )

    def cleanup_after_failure(self) -> None:
        if self.helper_pid is not None and self._pid_exists(self.helper_pid):
            try:
                os.kill(self.helper_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.services_started and self.release.is_dir():
            _run(
                ["/bin/bash", self.release / "ops" / "executive_os" / "service-control.sh", "stop"],
                label="failure cleanup service stop",
                check=False,
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the opt-in exact-SHA Executive OS Phase 1C-A host acceptance proof."
    )
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--operator-user", required=True)
    parser.add_argument("--success-timeout", type=float, default=2400.0)
    parser.add_argument("--active-timeout", type=float, default=120.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.success_timeout < 60 or args.success_timeout > 7200:
        print("acceptance error: success timeout is outside 60..7200 seconds", file=sys.stderr)
        return 2
    if args.active_timeout < 10 or args.active_timeout > 600:
        print("acceptance error: active timeout is outside 10..600 seconds", file=sys.stderr)
        return 2
    acceptance: Acceptance | None = None
    try:
        acceptance = Acceptance(args)
        acceptance.run()
    except (AcceptanceError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        if acceptance is not None:
            acceptance.cleanup_after_failure()
        print(f"acceptance error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Phase 1C-A acceptance PASS; receipts: {acceptance.receipt_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
