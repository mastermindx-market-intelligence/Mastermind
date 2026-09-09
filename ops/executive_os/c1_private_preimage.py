"""Read-only C1 private-host preimage collector.

The collector deliberately exposes a small, closed public contract.  Runtime
adapters and the CLI are added below the pure classification/serialization
layer so callers can test policy without touching a host.
"""

from __future__ import annotations

import argparse
import grp
import json
import math
import os
import plistlib
import pwd
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn, Sequence


SCHEMA = "mastermind.c1_private_preimage/v1"
STATES = frozenset({"FACTS", "DEGRADED", "REFUSED", "UNSETTLED"})
CLASSIFICATIONS = frozenset(
    {
        "UNSAFE",
        "EFFECT_UNKNOWN",
        "ACTIVE_FOREIGN",
        "ACTIVE_OWNED",
        "MATCHING_STOPPED",
        "STALE_STOPPED",
        "ABSENT_CLEAN",
        "UNKNOWN",
    }
)
REASON_CODES = frozenset(
    {
        "ACL_UNKNOWN",
        "COMMAND_NONZERO",
        "COMMAND_OUTPUT_OVERSIZED",
        "COMMAND_REFUSED",
        "COMMAND_TIMEOUT",
        "CONTENT_AGGREGATE_OVERSIZED",
        "CONTENT_OVERSIZED",
        "FILESYSTEM_DENIED",
        "FILESYSTEM_TORN",
        "INVALID_ARGUMENTS",
        "INVALID_RECEIPT",
        "MALFORMED_LAUNCHD",
        "MALFORMED_PROCESS",
        "MALFORMED_TRUSTED_DOCUMENT",
        "NONFINITE_RECEIPT",
        "PATH_ESCAPE",
        "PLATFORM_REFUSED",
        "PRINCIPAL_MISMATCH",
        "ROOT_REQUIRED",
        "UNSAFE_ACL",
        "UNSAFE_ANCESTOR",
        "UNSAFE_METADATA",
        "UNSUPPORTED_TYPE",
    }
)

LABELS = (
    "com.mastermind.executive.control",
    "com.mastermind.executive.worker.codex",
    "com.mastermind.executive.backup",
    "com.mastermind.executive.sol-state-relay",
    "com.mastermind.executive.agent-relay",
)
PLISTS = tuple(f"/Library/LaunchDaemons/{label}.plist" for label in LABELS)
SYSTEM_ROOT = "/Library/Application Support/MastermindExecutive"
RUNTIME_ROOT = "/var/db/mastermind-executive"
CONTROL_CONFIG = f"{SYSTEM_ROOT}/config/control.json"
WORKER_CONFIG = f"{SYSTEM_ROOT}/config/worker-codex.json"
PYTHON_PROVENANCE = f"{SYSTEM_ROOT}/python-runtime.json"
CODEX_ATTESTATION = f"{SYSTEM_ROOT}/codex-attestation-0.147.0.json"
CONTENT_PATHS = (*PLISTS, CONTROL_CONFIG, WORKER_CONFIG, PYTHON_PROVENANCE, CODEX_ATTESTATION)
METADATA_PATHS = (
    f"{SYSTEM_ROOT}/config/sol-state-relay.json",
    f"{SYSTEM_ROOT}/config/sol-state-relay.token",
    f"{SYSTEM_ROOT}/config/agent-relay.json",
    f"{SYSTEM_ROOT}/config/agent-relay.token",
    f"{SYSTEM_ROOT}/config/executive-dr-key.b64",
    f"{SYSTEM_ROOT}/config/control-env-canary",
    f"{RUNTIME_ROOT}/control/dr/executive-dr-token",
    f"{RUNTIME_ROOT}/control/canaries/secret-canary.json",
    f"{RUNTIME_ROOT}/control/canaries/control-environment-attestation.json",
    f"{RUNTIME_ROOT}/workers/codex-01/provider-home/auth.json",
    f"{RUNTIME_ROOT}/jobs/workspaces",
    f"{RUNTIME_ROOT}/jobs/runs",
    f"{RUNTIME_ROOT}/control/launch-receipts",
    f"{RUNTIME_ROOT}/control/backups",
    f"{RUNTIME_ROOT}/control/dr-receipts",
    "/var/run/mastermind-executive/ceo-ingress.sock",
    "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
    "/var/run/mastermind-agent-relay/agent-relay.sock",
)
PRINCIPALS = {
    "_mastermind_exec": {
        "uid": 450,
        "gid": 450,
        "home": "/var/db/mastermind-executive/control/home",
        "shell": "/usr/bin/false",
    },
    "_mastermind_worker": {
        "uid": 451,
        "gid": 451,
        "home": "/var/db/mastermind-executive/workers/codex-01/provider-home",
        "shell": "/usr/bin/false",
    },
    "_mastermind_sol_relay": {
        "uid": 452,
        "gid": 452,
        "home": "/var/db/mastermind-executive/sol-state-relay/home",
        "shell": "/usr/bin/false",
    },
    "_mastermind_agent_relay": {
        "uid": 457,
        "gid": 457,
        "home": "/var/db/mastermind-agent-relay/home",
        "shell": "/usr/bin/false",
    },
}
SERVICE_OWNERS = {
    "com.mastermind.executive.control": ("_mastermind_exec", 450, 450),
    "com.mastermind.executive.worker.codex": ("_mastermind_worker", 451, 451),
    "com.mastermind.executive.backup": ("_mastermind_exec", 450, 450),
    "com.mastermind.executive.sol-state-relay": ("_mastermind_sol_relay", 452, 452),
    "com.mastermind.executive.agent-relay": ("_mastermind_agent_relay", 457, 457),
}
MAX_CONTENT_BYTES = 1024 * 1024
MAX_AGGREGATE_BYTES = 9 * MAX_CONTENT_BYTES
MAX_COMMAND_BYTES = 64 * 1024
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PreimageRefusal(ValueError):
    """A closed, public refusal suitable for receipt reason codes."""

    def __init__(self, code: str) -> None:
        if code not in REASON_CODES:
            raise ValueError("unknown preimage refusal code")
        super().__init__(code)
        self.code = code


class PreimageUnsettled(RuntimeError):
    """A probe completed without enough bounded evidence to settle state."""

    def __init__(self, code: str) -> None:
        if code not in REASON_CODES:
            raise ValueError("unknown preimage unsettled code")
        super().__init__(code)
        self.code = code


def classify_preimage(snapshot: dict[str, Any]) -> str:
    """Classify a collected snapshot using the frozen precedence order."""

    if snapshot.get("unsafe"):
        return "UNSAFE"
    if snapshot.get("effect_unknown"):
        return "EFFECT_UNKNOWN"

    active_services = [
        service for service in snapshot.get("services", ()) if service.get("active")
    ]
    if any(not service.get("owned") for service in active_services):
        return "ACTIVE_FOREIGN"
    if active_services:
        return "ACTIVE_OWNED"
    if snapshot.get("matching_installation"):
        return "MATCHING_STOPPED"
    if snapshot.get("coherent_stale_installation"):
        return "STALE_STOPPED"
    return "ABSENT_CLEAN"


def _reject_nonfinite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise PreimageRefusal("NONFINITE_RECEIPT")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_nonfinite(key)
            _reject_nonfinite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_nonfinite(item)


def canonical_receipt(receipt: dict[str, Any]) -> bytes:
    """Return deterministic UTF-8 JSON with exactly one trailing newline."""

    _reject_nonfinite(receipt)
    try:
        payload = json.dumps(
            receipt,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        _raise_refusal("INVALID_RECEIPT", exc)
    return payload.encode("utf-8") + b"\n"


def _raise_refusal(code: str, cause: Exception) -> NoReturn:
    raise PreimageRefusal(code) from cause


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
        result[key] = value
    return result


def _project_mapping(value: Any, fields: dict[str, type]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    result: dict[str, Any] = {}
    for name, expected_type in fields.items():
        if name not in value or type(value[name]) is not expected_type:
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
        result[name] = value[name]
    return result


def parse_projected_json(payload: bytes, *, fields: dict[str, type]) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except PreimageRefusal:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT") from None
    return _project_mapping(value, fields)


def parse_projected_plist(payload: bytes, *, fields: dict[str, type]) -> dict[str, Any]:
    try:
        value = plistlib.loads(payload, fmt=None, dict_type=dict)
    except (plistlib.InvalidFileException, ValueError, TypeError):
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT") from None
    return _project_mapping(value, fields)


def validate_named_path(expected: str, observed: str) -> str:
    """Bind an observed name to a frozen lexical path.

    macOS maintains ``/var`` as an alias to ``/private/var``; that exact prefix
    translation is the sole accepted alias.
    """

    if observed == expected:
        return expected
    if expected.startswith("/var/") and observed == "/private" + expected:
        return expected
    raise PreimageRefusal("PATH_ESCAPE")


def _file_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def project_metadata(path: str, info: os.stat_result) -> dict[str, Any]:
    return {
        "path": path,
        "exists": True,
        "type": _file_type(info.st_mode),
        "device": info.st_dev,
        "inode": info.st_ino,
        "link_count": info.st_nlink,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def _allowed_command(argv: tuple[str, ...]) -> bool:
    if argv == ("/bin/launchctl", "print-disabled", "system"):
        return True
    if len(argv) == 3 and argv[:2] == ("/bin/launchctl", "print"):
        return argv[2] in {f"system/{label}" for label in LABELS}
    if len(argv) == 5 and argv[:4] == ("/bin/ps", "-o", "uid=,gid=,pid=,ppid="):
        return argv[4].isdigit() and int(argv[4]) > 0
    if len(argv) == 4 and argv[:3] == ("/usr/bin/stat", "-f", "%Sp"):
        return _is_frozen_path(argv[3])
    return False


def _is_frozen_path(path: str) -> bool:
    if path in frozenset((*CONTENT_PATHS, *METADATA_PATHS)):
        return True
    release_prefix = f"{SYSTEM_ROOT}/releases/"
    if not path.startswith(release_prefix):
        return False
    relative = path[len(release_prefix) :]
    pieces = relative.split("/")
    return bool(
        pieces
        and _SHA_RE.fullmatch(pieces[0])
        and (len(pieces) == 1 or pieces[1:] == [".executive-release-manifest.json"])
    )


class CommandAdapter:
    def __init__(self, *, runner: Callable[..., Any] = subprocess.run) -> None:
        self._runner = runner

    def run(self, argv: Sequence[str]) -> dict[str, str]:
        command = tuple(argv)
        if not _allowed_command(command):
            raise PreimageRefusal("COMMAND_REFUSED")
        try:
            completed = self._runner(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=5,
                shell=False,
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            raise PreimageUnsettled("COMMAND_TIMEOUT") from None
        if (
            completed.returncode == 113
            and len(command) == 3
            and command[:2] == ("/bin/launchctl", "print")
        ):
            return {"status": "absent", "stdout": ""}
        if completed.returncode != 0:
            raise PreimageUnsettled("COMMAND_NONZERO")
        if len(completed.stdout) > MAX_COMMAND_BYTES or len(completed.stderr) > MAX_COMMAND_BYTES:
            raise PreimageUnsettled("COMMAND_OUTPUT_OVERSIZED")
        try:
            output = completed.stdout.decode("utf-8")
        except UnicodeDecodeError:
            raise PreimageUnsettled("COMMAND_OUTPUT_OVERSIZED") from None
        return {"status": "ok", "stdout": output}


def parse_launchd_state(output: str) -> dict[str, Any]:
    states = re.findall(r"(?m)^\s*state\s*=\s*([a-z]+)\s*$", output)
    pids = re.findall(r"(?m)^\s*pid\s*=\s*([^\s]+)\s*$", output)
    if len(states) != 1 or len(pids) > 1:
        raise PreimageUnsettled("MALFORMED_LAUNCHD")
    state_value = states[0]
    active = state_value == "running"
    pid: int | None = None
    if pids:
        if not pids[0].isdigit() or int(pids[0]) <= 0:
            raise PreimageUnsettled("MALFORMED_LAUNCHD")
        pid = int(pids[0])
    if active and pid is None:
        raise PreimageUnsettled("MALFORMED_LAUNCHD")
    return {"active": active, "pid": pid, "state": state_value}


def parse_disabled_state(output: str) -> dict[str, bool]:
    matches = re.findall(
        r'(?m)^\s*"(com\.mastermind\.executive\.[A-Za-z0-9.-]+)"\s*=>\s*(true|false)\s*$',
        output,
    )
    values: dict[str, bool] = {}
    for label, raw_value in matches:
        if label not in LABELS or label in values:
            raise PreimageUnsettled("MALFORMED_LAUNCHD")
        values[label] = raw_value == "true"
    if set(values) != set(LABELS):
        raise PreimageUnsettled("MALFORMED_LAUNCHD")
    return values


def parse_process_identity(output: str, *, expected_pid: int) -> dict[str, int]:
    lines = [line.split() for line in output.splitlines() if line.strip()]
    if len(lines) != 1 or len(lines[0]) != 4 or not all(part.isdigit() for part in lines[0]):
        raise PreimageUnsettled("MALFORMED_PROCESS")
    uid, gid, pid, ppid = map(int, lines[0])
    if expected_pid <= 0 or pid != expected_pid:
        raise PreimageUnsettled("MALFORMED_PROCESS")
    return {"uid": uid, "gid": gid, "pid": pid, "ppid": ppid}


def service_owned(
    label: str, plist: dict[str, Any] | None, process: dict[str, int]
) -> bool:
    expected = SERVICE_OWNERS.get(label)
    if expected is None or plist is None:
        return False
    username, uid, gid = expected
    return bool(
        plist.get("Label") == label
        and plist.get("UserName") == username
        and process.get("uid") == uid
        and process.get("gid") == gid
        and process.get("pid", 0) > 0
    )


def expected_document_fixture(release_sha: str, tree_sha: str) -> dict[str, dict[str, Any]]:
    """Build the normalized identity surface used by tests and evaluation."""

    documents: dict[str, dict[str, Any]] = {
        "release_manifest": {
            "schema_version": "mastermind.executive_release_manifest/v1",
            "commit_sha": release_sha,
            "tree_sha": tree_sha,
        },
        CONTROL_CONFIG: {
            "schema_version": "mastermind.executive_control_config/v1",
            "proof_base_sha": release_sha,
        },
        WORKER_CONFIG: {
            "schema_version": "mastermind.executive_worker_broker_config/v4",
        },
        PYTHON_PROVENANCE: {
            "schema_version": "mastermind.executive_python_runtime/v1",
        },
        CODEX_ATTESTATION: {
            "schema_version": "mastermind.executive_codex_attestation/v1",
        },
    }
    for label, path in zip(LABELS, PLISTS, strict=True):
        documents[path] = {
            "Label": label,
            "UserName": SERVICE_OWNERS[label][0],
            "release_sha": release_sha,
        }
    return documents


def evaluate_installation(
    documents: dict[str, dict[str, Any]], expected_release_sha: str, expected_tree_sha: str
) -> dict[str, bool]:
    required = set(expected_document_fixture(expected_release_sha, expected_tree_sha))
    if set(documents) != required:
        return {
            "matching_installation": False,
            "coherent_stale_installation": False,
            "effect_unknown": bool(documents),
        }
    manifest = documents["release_manifest"]
    release_values = {
        manifest.get("commit_sha"),
        documents[CONTROL_CONFIG].get("proof_base_sha"),
        *(documents[path].get("release_sha") for path in PLISTS),
    }
    release_values.discard(None)
    if len(release_values) != 1 or not all(
        isinstance(value, str) and _SHA_RE.fullmatch(value) for value in release_values
    ):
        return {
            "matching_installation": False,
            "coherent_stale_installation": False,
            "effect_unknown": True,
        }
    installed_sha = next(iter(release_values))
    installed_tree = manifest.get("tree_sha")
    if not isinstance(installed_tree, str) or _SHA_RE.fullmatch(installed_tree) is None:
        return {
            "matching_installation": False,
            "coherent_stale_installation": False,
            "effect_unknown": True,
        }
    matching = installed_sha == expected_release_sha and installed_tree == expected_tree_sha
    return {
        "matching_installation": matching,
        "coherent_stale_installation": not matching,
        "effect_unknown": False,
    }


def _plist_release_sha(arguments: list[Any]) -> str:
    if not all(isinstance(value, str) for value in arguments):
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    values = {
        match.group(1)
        for value in arguments
        if (match := re.search(r"/releases/([0-9a-f]{40})(?:/|$)", value)) is not None
    }
    if len(values) != 1:
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    return next(iter(values))


def parse_content_document(
    path: str, payload: bytes, *, manifest_path: str
) -> tuple[str, dict[str, Any]]:
    if path in PLISTS:
        value = parse_projected_plist(
            payload,
            fields={"Label": str, "UserName": str, "ProgramArguments": list},
        )
        value["release_sha"] = _plist_release_sha(value.pop("ProgramArguments"))
        return path, value
    if path == CONTROL_CONFIG:
        return path, parse_projected_json(
            payload, fields={"schema_version": str, "proof_base_sha": str}
        )
    if path in (WORKER_CONFIG, PYTHON_PROVENANCE, CODEX_ATTESTATION):
        return path, parse_projected_json(payload, fields={"schema_version": str})
    if path == manifest_path:
        return "release_manifest", parse_projected_json(
            payload,
            fields={"schema_version": str, "commit_sha": str, "tree_sha": str},
        )
    raise PreimageRefusal("PATH_ESCAPE")


def _metadata_is_unsafe(item: dict[str, Any]) -> bool:
    if not item.get("exists"):
        return False
    if item.get("type") in {"symlink", "other"}:
        return True
    mode = item.get("mode")
    return bool(
        item.get("uid") not in {0, 450, 451, 452, 457}
        or not isinstance(mode, int)
        or mode & 0o022
        or (item.get("type") == "file" and item.get("link_count") != 1)
    )


class FilesystemAdapter:
    """Production filesystem adapter; it never exposes mutating operations."""

    def metadata(self, path: str) -> dict[str, Any]:
        if not _is_frozen_path(path):
            raise PreimageRefusal("PATH_ESCAPE")
        self._validate_ancestors(path)
        try:
            return project_metadata(path, os.lstat(path))
        except FileNotFoundError:
            return {"path": path, "exists": False}
        except PermissionError:
            raise PreimageUnsettled("FILESYSTEM_DENIED") from None

    def read(self, path: str) -> bytes:
        if path not in CONTENT_PATHS and not path.endswith(
            "/.executive-release-manifest.json"
        ):
            raise PreimageRefusal("PATH_ESCAPE")
        self._validate_ancestors(path)
        return _read_bounded_file(path)

    @staticmethod
    def _validate_ancestors(path: str) -> None:
        current = Path("/")
        for part in Path(path).parts[1:-1]:
            current /= part
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                return
            except PermissionError:
                raise PreimageUnsettled("FILESYSTEM_DENIED") from None
            if stat.S_ISLNK(info.st_mode):
                if os.fspath(current) == "/var":
                    try:
                        target = os.readlink(current)
                    except OSError:
                        raise PreimageUnsettled("FILESYSTEM_TORN") from None
                    if target not in ("private/var", "/private/var"):
                        raise PreimageRefusal("PATH_ESCAPE")
                    continue
                raise PreimageRefusal("UNSAFE_ANCESTOR")
            if not stat.S_ISDIR(info.st_mode):
                raise PreimageRefusal("UNSAFE_ANCESTOR")
            if info.st_uid not in {0, 450, 451, 452, 457} or stat.S_IMODE(info.st_mode) & 0o022:
                raise PreimageRefusal("UNSAFE_ANCESTOR")


def _read_bounded_file(path: str) -> bytes:
    lexical = Path(path)
    try:
        info_before = os.lstat(lexical)
    except PermissionError:
        raise PreimageUnsettled("FILESYSTEM_DENIED") from None
    if stat.S_ISLNK(info_before.st_mode):
        raise PreimageRefusal("PATH_ESCAPE")
    if not stat.S_ISREG(info_before.st_mode):
        raise PreimageRefusal("UNSUPPORTED_TYPE")
    if info_before.st_size > MAX_CONTENT_BYTES:
        raise PreimageRefusal("CONTENT_OVERSIZED")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(lexical, flags)
        try:
            descriptor_before = os.fstat(descriptor)
            if (descriptor_before.st_dev, descriptor_before.st_ino) != (
                info_before.st_dev,
                info_before.st_ino,
            ):
                raise PreimageUnsettled("FILESYSTEM_TORN")
            chunks: list[bytes] = []
            remaining = MAX_CONTENT_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            descriptor_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        info_after = os.lstat(lexical)
    except PermissionError:
        raise PreimageUnsettled("FILESYSTEM_DENIED") from None
    identities = {
        (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        for value in (info_before, descriptor_before, descriptor_after, info_after)
    }
    if len(identities) != 1:
        raise PreimageUnsettled("FILESYSTEM_TORN")
    if len(payload) > MAX_CONTENT_BYTES:
        raise PreimageRefusal("CONTENT_OVERSIZED")
    return payload


def enforce_content_budget(sizes: Sequence[int]) -> int:
    total = 0
    for size in sizes:
        if type(size) is not int or size < 0:
            raise PreimageRefusal("UNSAFE_METADATA")
        if size > MAX_CONTENT_BYTES:
            raise PreimageRefusal("CONTENT_OVERSIZED")
        total += size
        if total > MAX_AGGREGATE_BYTES:
            raise PreimageRefusal("CONTENT_AGGREGATE_OVERSIZED")
    return total


def inspect_acl(filesystem: Any, commands: Any, path: str) -> bool:
    """Inspect the macOS ACL marker while binding it to one stable inode."""

    before = filesystem.metadata(path)
    if not before.get("exists"):
        return False
    result = commands.run(("/usr/bin/stat", "-f", "%Sp", path))
    after = filesystem.metadata(path)
    if (before.get("device"), before.get("inode")) != (
        after.get("device"),
        after.get("inode"),
    ):
        raise PreimageUnsettled("FILESYSTEM_TORN")
    marker = result.get("stdout")
    if not isinstance(marker, str) or re.fullmatch(
        r"[bcdlps-][rwxStTs-]{9}[ +]?\n?", marker
    ) is None:
        raise PreimageUnsettled("ACL_UNKNOWN")
    return marker.rstrip("\n").endswith("+")


class PrincipalAdapter:
    def lookup(self, name: str) -> dict[str, Any] | None:
        if name not in PRINCIPALS:
            raise PreimageRefusal("PRINCIPAL_MISMATCH")
        try:
            user = pwd.getpwnam(name)
            group = grp.getgrnam(name)
        except KeyError:
            return None
        return {
            "name": name,
            "uid": user.pw_uid,
            "gid": user.pw_gid,
            "group_gid": group.gr_gid,
            "home": user.pw_dir,
            "shell": user.pw_shell,
        }


def _collect_preimage_facts(
    *,
    expected_release_sha: str,
    expected_tree_sha: str,
    filesystem: Any,
    commands: Any,
    principals: Any,
    clock: Callable[[], Any],
    platform: str,
    uid: int,
    euid: int,
) -> dict[str, Any]:
    """Collect the fixed public preimage without authorizing any later effect."""

    if not _SHA_RE.fullmatch(expected_release_sha) or not _SHA_RE.fullmatch(expected_tree_sha):
        raise PreimageRefusal("INVALID_ARGUMENTS")
    if platform != "darwin":
        raise PreimageRefusal("PLATFORM_REFUSED")
    if euid != 0:
        raise PreimageRefusal("ROOT_REQUIRED")

    observed = clock()
    if isinstance(observed, datetime):
        if observed.tzinfo is None:
            raise PreimageRefusal("INVALID_RECEIPT")
        observed_at = observed.astimezone(timezone.utc).isoformat()
    elif isinstance(observed, str):
        observed_at = observed
    else:
        raise PreimageRefusal("INVALID_RECEIPT")

    release_root = f"{SYSTEM_ROOT}/releases/{expected_release_sha}"
    manifest_path = f"{release_root}/.executive-release-manifest.json"
    fixed_metadata = (*CONTENT_PATHS, *METADATA_PATHS, release_root, manifest_path)
    metadata = [filesystem.metadata(path) for path in fixed_metadata]
    principal_facts = {name: principals.lookup(name) for name in PRINCIPALS}
    present = [item for item in metadata if item.get("exists")]

    reason_codes: set[str] = set()
    unsafe = any(_metadata_is_unsafe(item) for item in present)
    if unsafe:
        reason_codes.add("UNSAFE_METADATA")
    for item in present:
        if item.get("type") in {"symlink", "other"}:
            continue
        if inspect_acl(filesystem, commands, item["path"]):
            unsafe = True
            reason_codes.add("UNSAFE_ACL")

    documents: dict[str, dict[str, Any]] = {}
    content_sizes: list[int] = []
    for item in metadata:
        path = item["path"]
        if not item.get("exists") or path not in (*CONTENT_PATHS, manifest_path):
            continue
        try:
            content_sizes.append(item.get("size"))
            enforce_content_budget(content_sizes)
            payload = filesystem.read(path)
            if len(payload) != item["size"]:
                raise PreimageUnsettled("FILESYSTEM_TORN")
            key, value = parse_content_document(path, payload, manifest_path=manifest_path)
            documents[key] = value
        except PreimageRefusal as exc:
            unsafe = True
            reason_codes.add(exc.code)

    installation = evaluate_installation(documents, expected_release_sha, expected_tree_sha)
    expected_shapes = expected_document_fixture(expected_release_sha, expected_tree_sha)
    for path, value in documents.items():
        expected = expected_shapes.get(path)
        if expected is None:
            unsafe = True
            reason_codes.add("MALFORMED_TRUSTED_DOCUMENT")
            continue
        for key, expected_value in expected.items():
            if key in {"commit_sha", "tree_sha", "proof_base_sha", "release_sha"}:
                continue
            if value.get(key) != expected_value:
                unsafe = True
                reason_codes.add("MALFORMED_TRUSTED_DOCUMENT")

    principals_match = True
    for name, expected in PRINCIPALS.items():
        value = principal_facts[name]
        if value is None:
            principals_match = False
            continue
        if any(value.get(field) != expected[field] for field in ("uid", "gid", "home", "shell")):
            principals_match = False
            unsafe = True
            reason_codes.add("PRINCIPAL_MISMATCH")
        if value.get("group_gid") != expected["gid"]:
            principals_match = False
            unsafe = True
            reason_codes.add("PRINCIPAL_MISMATCH")

    services: list[dict[str, Any]] = []
    disabled_result = commands.run(("/bin/launchctl", "print-disabled", "system"))
    disabled = parse_disabled_state(disabled_result["stdout"])
    for label in LABELS:
        try:
            result = commands.run(("/bin/launchctl", "print", f"system/{label}"))
        except PreimageUnsettled as exc:
            if exc.code == "COMMAND_NONZERO":
                services.append(
                    {"label": label, "active": False, "disabled": disabled[label], "owned": True}
                )
                continue
            raise
        if result.get("status") == "absent":
            services.append(
                {"label": label, "active": False, "disabled": disabled[label], "owned": True}
            )
            continue
        state_value = parse_launchd_state(result["stdout"])
        service = {"label": label, **state_value, "disabled": disabled[label], "owned": True}
        if state_value["active"]:
            process = commands.run(
                ("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", str(state_value["pid"]))
            )
            identity = parse_process_identity(process["stdout"], expected_pid=state_value["pid"])
            service["process"] = identity
            plist_path = PLISTS[LABELS.index(label)]
            service["owned"] = service_owned(label, documents.get(plist_path), identity)
        services.append(service)

    snapshot = {
        "unsafe": unsafe,
        "effect_unknown": installation["effect_unknown"],
        "surface_present": bool(present)
        or any(value is not None for value in principal_facts.values()),
        "matching_installation": installation["matching_installation"] and principals_match,
        "coherent_stale_installation": installation["coherent_stale_installation"],
        "services": services,
    }
    classification = classify_preimage(snapshot)
    return {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "expected_release_sha": expected_release_sha,
        "expected_tree_sha": expected_tree_sha,
        "state": "FACTS",
        "classification": classification,
        "reason_codes": sorted(reason_codes),
        "facts": {
            "documents": documents,
            "metadata": metadata,
            "principals": principal_facts,
            "services": services,
            "invoking_uid": uid,
        },
        "probe_counts": {
            "content_limit": len(CONTENT_PATHS),
            "metadata": len(metadata),
            "principals": len(principal_facts),
            "services": len(services),
        },
        "source_limits": {
            "content_file_bytes": MAX_CONTENT_BYTES,
            "content_total_bytes": MAX_AGGREGATE_BYTES,
            "command_output_bytes": MAX_COMMAND_BYTES,
            "live_host_executed_by_source_wave": False,
        },
        "mutation_count": 0,
    }


def _observed_at(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise PreimageRefusal("INVALID_RECEIPT")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise PreimageRefusal("INVALID_RECEIPT") from None
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise PreimageRefusal("INVALID_RECEIPT")
        return parsed.astimezone(timezone.utc).isoformat()
    raise PreimageRefusal("INVALID_RECEIPT")


def _failure_value(
    *,
    expected_release_sha: str,
    expected_tree_sha: str,
    observed_at: str,
    state: str,
    code: str,
    classification: str = "UNKNOWN",
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "expected_release_sha": expected_release_sha,
        "expected_tree_sha": expected_tree_sha,
        "state": state,
        "classification": classification,
        "reason_codes": [code],
        "facts": {},
        "probe_counts": {},
        "source_limits": {
            "content_file_bytes": MAX_CONTENT_BYTES,
            "content_total_bytes": MAX_AGGREGATE_BYTES,
            "command_output_bytes": MAX_COMMAND_BYTES,
        },
        "mutation_count": 0,
    }


def collect_preimage(
    *,
    expected_release_sha: str,
    expected_tree_sha: str,
    filesystem: Any,
    commands: Any,
    principals: Any,
    clock: Callable[[], Any],
    platform: str,
    uid: int,
    euid: int,
) -> dict[str, Any]:
    observed = clock()
    try:
        observed_at = _observed_at(observed)
        return _collect_preimage_facts(
            expected_release_sha=expected_release_sha,
            expected_tree_sha=expected_tree_sha,
            filesystem=filesystem,
            commands=commands,
            principals=principals,
            clock=lambda: observed_at,
            platform=platform,
            uid=uid,
            euid=euid,
        )
    except PreimageUnsettled as exc:
        return _failure_value(
            expected_release_sha=expected_release_sha,
            expected_tree_sha=expected_tree_sha,
            observed_at=_observed_at(observed),
            state="UNSETTLED",
            code=exc.code,
        )
    except PreimageRefusal as exc:
        unsafe_codes = {
            "CONTENT_AGGREGATE_OVERSIZED",
            "CONTENT_OVERSIZED",
            "MALFORMED_TRUSTED_DOCUMENT",
            "PATH_ESCAPE",
            "UNSAFE_ACL",
            "UNSAFE_ANCESTOR",
            "UNSAFE_METADATA",
            "UNSUPPORTED_TYPE",
        }
        return _failure_value(
            expected_release_sha=expected_release_sha,
            expected_tree_sha=expected_tree_sha,
            observed_at=_observed_at(observed),
            state="FACTS" if exc.code in unsafe_codes else "REFUSED",
            code=exc.code,
            classification="UNSAFE" if exc.code in unsafe_codes else "UNKNOWN",
        )
    except OSError:
        return _failure_value(
            expected_release_sha=expected_release_sha,
            expected_tree_sha=expected_tree_sha,
            observed_at=_observed_at(observed),
            state="DEGRADED",
            code="FILESYSTEM_DENIED",
        )


class _ClosedParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PreimageRefusal("INVALID_ARGUMENTS")


def _describe() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "states": sorted(STATES),
        "classifications": sorted(CLASSIFICATIONS),
        "labels": list(LABELS),
        "content_paths": list(CONTENT_PATHS),
        "metadata_paths": list(METADATA_PATHS),
        "command_allowlist": [
            "/bin/launchctl print-disabled system",
            "/bin/launchctl print system/<frozen-label>",
            "/bin/ps -o uid=,gid=,pid=,ppid= -p <positive-pid>",
            "/usr/bin/stat -f %Sp <frozen-path>",
        ],
        "mutation_count": 0,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    _platform: str | None = None,
    _uid: int | None = None,
    _euid: int | None = None,
) -> int:
    parser = _ClosedParser(add_help=False)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--expected-release-sha")
    parser.add_argument("--expected-tree-sha")
    try:
        args = parser.parse_args(argv)
        if args.describe:
            if args.expected_release_sha is not None or args.expected_tree_sha is not None:
                raise PreimageRefusal("INVALID_ARGUMENTS")
            sys.stdout.buffer.write(canonical_receipt(_describe()))
            return 0
        if not _SHA_RE.fullmatch(args.expected_release_sha or "") or not _SHA_RE.fullmatch(
            args.expected_tree_sha or ""
        ):
            raise PreimageRefusal("INVALID_ARGUMENTS")
        platform_value = sys.platform if _platform is None else _platform
        uid_value = os.getuid() if _uid is None else _uid
        euid_value = os.geteuid() if _euid is None else _euid
        if platform_value != "darwin" or euid_value != 0:
            raise PreimageRefusal(
                "PLATFORM_REFUSED" if platform_value != "darwin" else "ROOT_REQUIRED"
            )
    except PreimageRefusal:
        return 64

    try:
        receipt = collect_preimage(
            expected_release_sha=args.expected_release_sha,
            expected_tree_sha=args.expected_tree_sha,
            filesystem=FilesystemAdapter(),
            commands=CommandAdapter(),
            principals=PrincipalAdapter(),
            clock=lambda: datetime.now(timezone.utc),
            platform=platform_value,
            uid=uid_value,
            euid=euid_value,
        )
    except PreimageUnsettled as exc:
        receipt = _failure_receipt(args, "UNSETTLED", exc.code)
    except PreimageRefusal as exc:
        receipt = _failure_receipt(args, "REFUSED", exc.code)
    sys.stdout.buffer.write(canonical_receipt(receipt))
    return {"FACTS": 0, "DEGRADED": 2, "REFUSED": 2, "UNSETTLED": 3}[receipt["state"]]


def _failure_receipt(args: Any, state: str, code: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "expected_release_sha": args.expected_release_sha,
        "expected_tree_sha": args.expected_tree_sha,
        "state": state,
        "classification": "UNKNOWN",
        "reason_codes": [code],
        "facts": {},
        "probe_counts": {},
        "source_limits": {
            "content_file_bytes": MAX_CONTENT_BYTES,
            "content_total_bytes": MAX_AGGREGATE_BYTES,
            "command_output_bytes": MAX_COMMAND_BYTES,
        },
        "mutation_count": 0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
