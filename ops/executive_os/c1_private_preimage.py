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
import selectors
import stat
import subprocess
import sys
import time
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
        "COMMAND_OUTPUT_INVALID",
        "COMMAND_REFUSED",
        "COMMAND_SPAWN_FAILED",
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
PYTHON_BINARY = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
CODEX_BINARY = (
    "/opt/homebrew/lib/node_modules/@openai/codex/node_modules/"
    "@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex"
)
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

    def __init__(self, code: str, *, facts: dict[str, Any] | None = None) -> None:
        if code not in REASON_CODES:
            raise ValueError("unknown preimage unsettled code")
        super().__init__(code)
        self.code = code
        self.facts = facts or {}


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
    if snapshot.get("surface_present"):
        return "EFFECT_UNKNOWN"
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


class _UniquePlistDict(dict):
    def __setitem__(self, key: Any, value: Any) -> None:
        if key in self:
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
        super().__setitem__(key, value)


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
        value = plistlib.loads(payload, fmt=None, dict_type=_UniquePlistDict)
    except PreimageRefusal:
        raise
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
    if len(argv) == 5 and argv[:4] == (
        "/bin/ps",
        "-o",
        "uid=,gid=,pid=,ppid=",
        "-p",
    ):
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
    def __init__(
        self,
        *,
        runner: Callable[..., Any] | None = None,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        selector_factory: Callable[[], Any] = selectors.DefaultSelector,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runner = runner
        self._popen_factory = popen_factory
        self._selector_factory = selector_factory
        self._monotonic = monotonic

    def run(self, argv: Sequence[str]) -> dict[str, str]:
        command = tuple(argv)
        if not _allowed_command(command):
            raise PreimageRefusal("COMMAND_REFUSED")
        if self._runner is not None:
            return self._run_injected_completed(command)
        return self._run_bounded_child(command)

    def _run_injected_completed(self, command: tuple[str, ...]) -> dict[str, str]:
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
            raise PreimageUnsettled(
                "COMMAND_TIMEOUT",
                facts={"timed_out": True, "reaped": False, "partial_output_bytes": 0},
            ) from None
        return self._finish_completed(command, completed)

    @staticmethod
    def _finish_completed(command: tuple[str, ...], completed: Any) -> dict[str, str]:
        if len(completed.stdout) > MAX_COMMAND_BYTES or len(completed.stderr) > MAX_COMMAND_BYTES:
            raise PreimageUnsettled(
                "COMMAND_OUTPUT_OVERSIZED",
                facts={
                    "timed_out": False,
                    "reaped": True,
                    "partial_output_bytes": MAX_COMMAND_BYTES,
                },
            )
        if (
            completed.returncode == 113
            and len(command) == 3
            and command[:2] == ("/bin/launchctl", "print")
        ):
            label = command[2].removeprefix("system/")
            try:
                stderr = completed.stderr.decode("utf-8")
            except UnicodeDecodeError:
                raise PreimageUnsettled("COMMAND_OUTPUT_INVALID") from None
            absent = re.fullmatch(
                r'(?:Bad request\.\n)?Could not find service "'
                + re.escape(label)
                + r'" in domain for system\n?',
                stderr,
            )
            if completed.stdout or absent is None:
                raise PreimageUnsettled("COMMAND_NONZERO")
            return {"status": "absent", "stdout": ""}
        if completed.returncode != 0:
            raise PreimageUnsettled("COMMAND_NONZERO")
        try:
            output = completed.stdout.decode("utf-8")
        except UnicodeDecodeError:
            raise PreimageUnsettled("COMMAND_OUTPUT_INVALID") from None
        return {"status": "ok", "stdout": output}

    def _run_bounded_child(self, command: tuple[str, ...]) -> dict[str, Any]:
        started = self._monotonic()
        execution_deadline = started + 4.0
        final_deadline = started + 5.0
        try:
            child = self._popen_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
                bufsize=0,
            )
        except OSError:
            raise PreimageUnsettled("COMMAND_SPAWN_FAILED") from None
        try:
            child_pid = int(child.pid)
            if child_pid <= 0:
                raise ValueError
        except Exception:
            child_pid = None
        facts = {
            "child_pid": child_pid,
            "timed_out": False,
            "terminated": False,
            "reaped": False,
            "partial_output_bytes": 0,
        }
        if child_pid is None:
            facts["child_identity_unknown"] = True
        output = {"stdout": bytearray(), "stderr": bytearray()}
        selector = None
        failure: PreimageUnsettled | None = None
        try:
            if self._monotonic() > final_deadline:
                facts["timed_out"] = True
                raise PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
            selector = self._selector_factory()
            for name, stream in (("stdout", child.stdout), ("stderr", child.stderr)):
                if stream is None:
                    raise PreimageUnsettled("COMMAND_SPAWN_FAILED", facts=facts)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, data=name)
            while selector.get_map():
                remaining = execution_deadline - self._monotonic()
                if remaining <= 0:
                    facts["timed_out"] = True
                    raise PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
                events = selector.select(timeout=min(remaining, 0.1))
                if self._monotonic() > execution_deadline:
                    facts["timed_out"] = True
                    raise PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
                for key, _events in events:
                    target = output[key.data]
                    acquisition_limit = MAX_COMMAND_BYTES - len(target) + 1
                    chunk = os.read(
                        key.fileobj.fileno(), min(16 * 1024, acquisition_limit)
                    )
                    target.extend(chunk)
                    facts["partial_output_bytes"] += len(chunk)
                    if len(target) > MAX_COMMAND_BYTES:
                        raise PreimageUnsettled("COMMAND_OUTPUT_OVERSIZED", facts=facts)
                    if self._monotonic() > execution_deadline:
                        facts["timed_out"] = True
                        raise PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
            remaining = execution_deadline - self._monotonic()
            if remaining <= 0:
                facts["timed_out"] = True
                raise PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
            returncode = child.wait(timeout=remaining)
            facts["reaped"] = True
            if self._monotonic() > final_deadline:
                facts["timed_out"] = True
                raise PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
        except Exception as exc:
            if isinstance(exc, subprocess.TimeoutExpired):
                facts["timed_out"] = True
                failure = PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
            elif isinstance(exc, PreimageUnsettled):
                failure = exc
            else:
                failure = PreimageUnsettled("COMMAND_NONZERO", facts=facts)
            self._settle_owned_child(child, facts, final_deadline)
            if self._monotonic() > final_deadline:
                facts["timed_out"] = True
                failure = PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
        self._close_probe_resources(selector, child, facts)
        if facts.get("cleanup_unknown") and failure is None:
            failure = PreimageUnsettled("COMMAND_NONZERO", facts=facts)
        if self._monotonic() > final_deadline:
            facts["timed_out"] = True
            failure = PreimageUnsettled("COMMAND_TIMEOUT", facts=facts)
        if failure is not None:
            failure.facts = dict(facts)
            raise failure from None
        completed = type(
            "BoundedCompleted",
            (),
            {
                "returncode": returncode,
                "stdout": bytes(output["stdout"]),
                "stderr": bytes(output["stderr"]),
            },
        )()
        try:
            result = self._finish_completed(command, completed)
        except PreimageUnsettled as exc:
            exc.facts = dict(facts)
            raise
        result["probe"] = facts
        return result

    def _settle_owned_child(
        self, child: Any, facts: dict[str, Any], final_deadline: float
    ) -> None:
        if facts["reaped"]:
            return
        try:
            running = child.poll() is None
        except Exception:
            running = True
            facts["reap_unknown"] = True
        if running:
            try:
                child.kill()
                facts["terminated"] = True
            except Exception:
                facts["termination_unknown"] = True
        try:
            settlement = max(0.0, final_deadline - self._monotonic())
            child.wait(timeout=settlement)
            facts["reaped"] = True
            facts.pop("reap_unknown", None)
        except Exception:
            facts["reaped"] = False
            facts["reap_unknown"] = True

    @staticmethod
    def _close_probe_resources(
        selector: Any | None, child: Any, facts: dict[str, Any]
    ) -> None:
        if selector is not None:
            try:
                selector.close()
            except Exception:
                facts["cleanup_unknown"] = True
        streams = []
        for name in ("stdout", "stderr"):
            try:
                streams.append(getattr(child, name, None))
            except Exception:
                facts["cleanup_unknown"] = True
        for stream in streams:
            if stream is None:
                continue
            try:
                stream.close()
            except Exception:
                facts["cleanup_unknown"] = True


def parse_launchd_state(
    output: str,
    *,
    expected_program: str | None = None,
    expected_arguments: Sequence[str] | None = None,
) -> dict[str, Any]:
    states = re.findall(r"(?m)^\s*state\s*=\s*([a-z]+)\s*$", output)
    pids = re.findall(r"(?m)^\s*pid\s*=\s*([^\s]+)\s*$", output)
    programs = re.findall(r"(?m)^\s*program\s*=\s*(\S+)\s*$", output)
    argument_blocks = re.findall(
        r"(?ms)^\s*arguments\s*=\s*\{\s*\n(.*?)^\s*\}\s*$", output
    )
    if len(states) != 1 or len(pids) > 1:
        raise PreimageUnsettled("MALFORMED_LAUNCHD")
    state_value = states[0]
    if state_value not in {"running", "waiting", "exited"}:
        raise PreimageUnsettled("MALFORMED_LAUNCHD")
    active = state_value == "running"
    pid: int | None = None
    if pids:
        if not pids[0].isdigit() or int(pids[0]) <= 0:
            raise PreimageUnsettled("MALFORMED_LAUNCHD")
        pid = int(pids[0])
    if active and pid is None:
        raise PreimageUnsettled("MALFORMED_LAUNCHD")
    if not active and pid is not None:
        raise PreimageUnsettled("MALFORMED_LAUNCHD")
    result: dict[str, Any] = {"active": active, "pid": pid, "state": state_value}
    if active and expected_program is not None:
        if len(programs) != 1:
            raise PreimageUnsettled("MALFORMED_LAUNCHD")
        result["program_matches"] = programs[0] == expected_program
    if active and expected_arguments is not None:
        if len(argument_blocks) != 1:
            raise PreimageUnsettled("MALFORMED_LAUNCHD")
        loaded_arguments = [
            line.strip() for line in argument_blocks[0].splitlines() if line.strip()
        ]
        if not loaded_arguments:
            raise PreimageUnsettled("MALFORMED_LAUNCHD")
        result["arguments_match"] = loaded_arguments == list(expected_arguments)
    return result


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
    label: str,
    plist: dict[str, Any] | None,
    process: dict[str, int],
    *,
    program_matches: bool,
    arguments_match: bool,
    release_matches: bool,
) -> bool:
    expected = SERVICE_OWNERS.get(label)
    if expected is None or plist is None:
        return False
    username, uid, gid = expected
    return bool(
        plist.get("Label") == label
        and plist.get("UserName") == username
        and program_matches
        and arguments_match
        and release_matches
        and process.get("uid") == uid
        and process.get("gid") == gid
        and process.get("pid", 0) > 0
        and process.get("ppid") == 1
    )


def expected_program_arguments(label: str, release_sha: str) -> list[str]:
    release = f"{SYSTEM_ROOT}/releases/{release_sha}"
    values = {
        "com.mastermind.executive.control": [
            PYTHON_BINARY,
            "-I",
            "-S",
            "-B",
            f"{release}/scripts/executive_os_phase1c_control_wrapper.py",
            "--config",
            CONTROL_CONFIG,
            "--sentinel-file",
            f"{SYSTEM_ROOT}/config/control-env-canary",
            "--attestation",
            f"{RUNTIME_ROOT}/control/canaries/control-environment-attestation.json",
            "--release-root",
            release,
        ],
        "com.mastermind.executive.worker.codex": [
            PYTHON_BINARY,
            "-I",
            "-S",
            "-B",
            f"{release}/scripts/executive_os_phase1c_worker.py",
            "serve",
            "--config",
            WORKER_CONFIG,
        ],
        "com.mastermind.executive.backup": [
            "/bin/bash",
            f"{release}/ops/executive_os/run_nightly_backup.sh",
            "--python-binary",
            PYTHON_BINARY,
            "--release-root",
            release,
            "--config",
            CONTROL_CONFIG,
            "--key-file",
            f"{SYSTEM_ROOT}/config/executive-dr-key.b64",
            "--receipts-dir",
            f"{RUNTIME_ROOT}/control/dr-receipts",
            "--transport",
            "github",
            "--repo",
            "mastermindx-market-intelligence/executive-dr-vault",
            "--token-file",
            f"{RUNTIME_ROOT}/control/dr/executive-dr-token",
        ],
        "com.mastermind.executive.sol-state-relay": [
            PYTHON_BINARY,
            "-I",
            "-S",
            "-B",
            f"{release}/scripts/c1_sol_state_relay.py",
            "--config",
            f"{SYSTEM_ROOT}/config/sol-state-relay.json",
        ],
    }
    if label not in values:
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    return values[label]


def expected_loaded_program(label: str, release_sha: str) -> str:
    if label == "com.mastermind.executive.agent-relay":
        return PYTHON_BINARY
    return expected_program_arguments(label, release_sha)[0]


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
            "control_uid": 450,
            "worker_uid": 451,
            "worker_gid": 451,
            "shared_run_gid": 451,
            "proof_source_repository": (
                f"{RUNTIME_ROOT}/control/admin-checkout/{release_sha}"
            ),
            "proof_workspace_root": f"{RUNTIME_ROOT}/jobs/workspaces",
            "worker_runs_root": f"{RUNTIME_ROOT}/jobs/runs",
            "worker_provider_home": (
                f"{RUNTIME_ROOT}/workers/codex-01/provider-home"
            ),
            "secret_canary_receipt_path": (
                f"{RUNTIME_ROOT}/control/canaries/secret-canary.json"
            ),
            "operator_harness_version": "0.147.0",
            "operator_harness_binary_digest": (
                "19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"
            ),
        },
        WORKER_CONFIG: {
            "schema_version": "mastermind.executive_worker_broker_config/v4",
            "control_uid": 450,
            "worker_uid": 451,
            "worker_gid": 451,
            "worker_user": "_mastermind_worker",
            "worker_id": "codex-01",
            "workspace_root": f"{RUNTIME_ROOT}/jobs/workspaces",
            "run_root": f"{RUNTIME_ROOT}/jobs/runs",
            "provider_home": f"{RUNTIME_ROOT}/workers/codex-01/provider-home",
            "codex_binary": CODEX_BINARY,
            "codex_attestation_receipt": CODEX_ATTESTATION,
            "allowed_codex_versions": ["0.147.0"],
            "required_team_identifier": "2DC432GLL2",
            "launchd_socket_name": "WorkerBroker",
        },
        PYTHON_PROVENANCE: {
            "schema_version": "mastermind.executive_python_runtime/v1",
            "python_version": "3.12.10",
            "runtime_root": "/Library/Frameworks/Python.framework/Versions/3.12",
            "python_binary": PYTHON_BINARY,
            "team_identifier": "BMM5U3QVKW",
            "package_sha256": "8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4",
            "python_binary_sha256": (
                "d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
            ),
            "python_framework_sha256": (
                "14e61fb22a897d238248dfd8fe3b472b4541338c293368b4747803055b8bb3aa"
            ),
        },
        CODEX_ATTESTATION: {
            "schema_version": "mastermind.executive_codex_attestation/v1",
            "path": CODEX_BINARY,
            "version": "0.147.0",
            "team_identifier": "2DC432GLL2",
            "sha256": "19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37",
        },
    }
    for label, path in zip(LABELS, PLISTS, strict=True):
        documents[path] = {
            "Label": label,
            "UserName": SERVICE_OWNERS[label][0],
            "GroupName": SERVICE_OWNERS[label][0],
            "WorkingDirectory": f"{SYSTEM_ROOT}/releases/{release_sha}",
            "release_sha": release_sha,
        }
    return documents


def evaluate_installation(
    documents: dict[str, dict[str, Any]], expected_release_sha: str, expected_tree_sha: str
) -> dict[str, bool]:
    required = set(expected_document_fixture(expected_release_sha, expected_tree_sha))
    core = required - {"release_manifest"}
    if frozenset(documents) not in {frozenset(required), frozenset(core)}:
        return {
            "matching_installation": False,
            "coherent_stale_installation": False,
            "effect_unknown": bool(documents),
        }
    manifest = documents.get("release_manifest")
    release_values = {
        documents[CONTROL_CONFIG].get("proof_base_sha"),
        *(documents[path].get("release_sha") for path in PLISTS),
    }
    if manifest is not None:
        release_values.add(manifest.get("commit_sha"))
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
    if installed_sha != expected_release_sha and manifest is None:
        return {
            "matching_installation": False,
            "coherent_stale_installation": True,
            "effect_unknown": False,
        }
    if manifest is None:
        return {
            "matching_installation": False,
            "coherent_stale_installation": False,
            "effect_unknown": True,
        }
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


def _valid_agent_arguments(arguments: list[Any], release_sha: str) -> bool:
    release = f"{SYSTEM_ROOT}/releases/{release_sha}"
    fixed = {
        0: PYTHON_BINARY,
        1: "-I",
        2: "-S",
        3: "-B",
        4: f"{release}/scripts/slack_agent_dialogue_service.py",
        5: "--socket-path",
        6: "/var/run/mastermind-agent-relay/agent-relay.sock",
        7: "--token-file",
        8: f"{SYSTEM_ROOT}/config/agent-relay.token",
        9: "--workspace-id",
        10: "T0BRD2AQXQV",
        11: "--channel-id",
        12: "C0BSBM78V1N",
        13: "--bot-user-id",
        15: "--allowed-peer-uid",
        16: "450",
        17: "--allowed-sol-user-id",
        18: "U0BRETDUAS2",
        19: "--allowed-sol-user-id",
        20: "U0BSB73JWNL",
        21: "--allowed-parent-user-id",
        22: "U0BRETDUAS2",
        23: "--dialogue-coordination-socket-path",
        24: "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
    }
    return bool(
        len(arguments) in {25, 26}
        and all(isinstance(value, str) for value in arguments)
        and all(arguments[index] == value for index, value in fixed.items())
        and re.fullmatch(r"[UW][A-Z0-9]{8,14}", arguments[14])
        and (len(arguments) == 25 or arguments[25] == "--enable-w3c")
    )


def _validated_json_document(
    path: str,
    payload: bytes,
    *,
    expected_release_sha: str,
    expected_tree_sha: str,
    manifest_path: str,
) -> tuple[str, dict[str, Any]]:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except PreimageRefusal:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT") from None
    if not isinstance(value, dict):
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    key = "release_manifest" if path == manifest_path else path
    if key == "release_manifest":
        commit_sha = value.get("commit_sha")
        tree_sha = value.get("tree_sha")
        if (
            value.get("schema_version")
            != "mastermind.executive_release_manifest/v1"
            or not isinstance(commit_sha, str)
            or _SHA_RE.fullmatch(commit_sha) is None
            or not isinstance(tree_sha, str)
            or _SHA_RE.fullmatch(tree_sha) is None
        ):
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
        return key, {
            "schema_version": "mastermind.executive_release_manifest/v1",
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
        }
    identity_sha = expected_release_sha
    if path == CONTROL_CONFIG:
        identity_sha = value.get("proof_base_sha")
        if not isinstance(identity_sha, str) or _SHA_RE.fullmatch(identity_sha) is None:
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    expected = expected_document_fixture(identity_sha, expected_tree_sha)
    required = expected.get(key)
    if required is None or any(value.get(name) != item for name, item in required.items()):
        raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    if path == PYTHON_PROVENANCE:
        prior = value.get("prior_runtime_archive")
        prior_receipt = value.get("prior_runtime_receipt_archive")
        if (
            not isinstance(prior, str)
            or not isinstance(prior_receipt, str)
            or (
                prior
                and not prior.startswith(
                    f"{SYSTEM_ROOT}/python-archive/prior-3.12-"
                )
            )
            or (
                prior_receipt
                and not prior_receipt.startswith(
                    f"{SYSTEM_ROOT}/python-archive/prior-receipt-3.12-"
                )
            )
        ):
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    if path == CODEX_ATTESTATION:
        identity = value.get("identity")
        identity_fields = {
            "device",
            "inode",
            "size",
            "mode",
            "uid",
            "gid",
            "mtime_ns",
            "ctime_ns",
        }
        if (
            not isinstance(value.get("recorded_at"), str)
            or not isinstance(identity, dict)
            or set(identity) != identity_fields
            or any(type(identity[name]) is not int for name in identity_fields)
        ):
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
    return key, dict(required)


def parse_content_document(
    path: str,
    payload: bytes,
    *,
    manifest_path: str,
    expected_release_sha: str,
    expected_tree_sha: str,
) -> tuple[str, dict[str, Any]]:
    if path in PLISTS:
        value = parse_projected_plist(
            payload,
            fields={
                "Label": str,
                "UserName": str,
                "GroupName": str,
                "WorkingDirectory": str,
                "ProgramArguments": list,
            },
        )
        label = LABELS[PLISTS.index(path)]
        working = value.get("WorkingDirectory")
        match = re.fullmatch(
            re.escape(f"{SYSTEM_ROOT}/releases/") + r"([0-9a-f]{40})",
            working,
        )
        if match is None:
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
        installed_sha = match.group(1)
        release = f"{SYSTEM_ROOT}/releases/{installed_sha}"
        arguments = value.pop("ProgramArguments")
        if label == "com.mastermind.executive.agent-relay":
            arguments_match = _valid_agent_arguments(arguments, installed_sha)
        else:
            arguments_match = arguments == expected_program_arguments(label, installed_sha)
        expected = expected_document_fixture(installed_sha, expected_tree_sha)[path]
        if (
            not arguments_match
            or value.get("Label") != label
            or value.get("UserName") != SERVICE_OWNERS[label][0]
            or value.get("GroupName") != SERVICE_OWNERS[label][0]
            or value.get("WorkingDirectory") != release
        ):
            raise PreimageRefusal("MALFORMED_TRUSTED_DOCUMENT")
        normalized = dict(expected)
        normalized["_program_arguments"] = list(arguments)
        return path, normalized
    return _validated_json_document(
        path,
        payload,
        expected_release_sha=expected_release_sha,
        expected_tree_sha=expected_tree_sha,
        manifest_path=manifest_path,
    )


def _metadata_contract(path: str) -> dict[str, int | str | None]:
    file_contracts = {
        **{path: (0, 0, 0o644) for path in PLISTS},
        CONTROL_CONFIG: (0, 450, 0o440),
        WORKER_CONFIG: (0, 451, 0o440),
        PYTHON_PROVENANCE: (0, 0, 0o400),
        CODEX_ATTESTATION: (0, 451, 0o440),
        f"{SYSTEM_ROOT}/config/sol-state-relay.json": (0, 452, 0o440),
        f"{SYSTEM_ROOT}/config/sol-state-relay.token": (452, 452, 0o400),
        f"{SYSTEM_ROOT}/config/agent-relay.json": (457, 457, 0o400),
        f"{SYSTEM_ROOT}/config/agent-relay.token": (457, 457, 0o400),
        f"{SYSTEM_ROOT}/config/executive-dr-key.b64": (450, 450, 0o400),
        f"{SYSTEM_ROOT}/config/control-env-canary": (0, 450, 0o440),
        f"{RUNTIME_ROOT}/control/dr/executive-dr-token": (450, 450, 0o400),
        f"{RUNTIME_ROOT}/control/canaries/secret-canary.json": (450, 450, 0o400),
        f"{RUNTIME_ROOT}/control/canaries/control-environment-attestation.json": (
            450,
            450,
            0o400,
        ),
        f"{RUNTIME_ROOT}/workers/codex-01/provider-home/auth.json": (451, 451, 0o600),
    }
    if path in file_contracts:
        uid, gid, mode = file_contracts[path]
        return {
            "type": "file",
            "uid": uid,
            "gid": gid,
            "mode": mode,
            "required_mode": 0,
            "forbidden_mode": 0,
            "link_count": 1,
        }
    directory_contracts = {
        f"{RUNTIME_ROOT}/jobs/workspaces": (450, 451, 0o710),
        f"{RUNTIME_ROOT}/jobs/runs": (450, 451, 0o710),
        f"{RUNTIME_ROOT}/control/launch-receipts": (450, 450, 0o700),
        f"{RUNTIME_ROOT}/control/backups": (450, 450, 0o700),
        f"{RUNTIME_ROOT}/control/dr-receipts": (450, 450, 0o700),
    }
    if path in directory_contracts:
        uid, gid, mode = directory_contracts[path]
        return {
            "type": "directory",
            "uid": uid,
            "gid": gid,
            "mode": mode,
            "required_mode": 0,
            "forbidden_mode": 0,
            "link_count": None,
        }
    socket_contracts = {
        "/var/run/mastermind-executive/ceo-ingress.sock": (450, 452, 0o660),
        "/var/run/mastermind-dialogue-observation/dialogue-observation.sock": (
            450,
            457,
            0o660,
        ),
        "/var/run/mastermind-agent-relay/agent-relay.sock": (457, 457, 0o660),
    }
    if path in socket_contracts:
        uid, gid, mode = socket_contracts[path]
        return {
            "type": "socket",
            "uid": uid,
            "gid": gid,
            "mode": mode,
            "required_mode": 0,
            "forbidden_mode": 0,
            "link_count": None,
        }
    if re.fullmatch(
        re.escape(f"{SYSTEM_ROOT}/releases/") + r"[0-9a-f]{40}", path
    ):
        return {
            "type": "directory",
            "uid": 0,
            "gid": 0,
            "mode": None,
            "required_mode": 0o055,
            "forbidden_mode": 0o022,
            "link_count": None,
        }
    if re.fullmatch(
        re.escape(f"{SYSTEM_ROOT}/releases/")
        + r"[0-9a-f]{40}/\.executive-release-manifest\.json",
        path,
    ):
        return {
            "type": "file",
            "uid": 0,
            "gid": 0,
            "mode": 0o444,
            "required_mode": 0,
            "forbidden_mode": 0,
            "link_count": 1,
        }
    raise PreimageRefusal("PATH_ESCAPE")


def _metadata_is_unsafe(item: dict[str, Any]) -> bool:
    if not item.get("exists"):
        return False
    try:
        contract = _metadata_contract(item.get("path"))
    except (PreimageRefusal, TypeError):
        return True
    mode = item.get("mode")
    exact_mode = contract["mode"]
    required_mode = contract["required_mode"]
    forbidden_mode = contract["forbidden_mode"]
    expected_link_count = contract["link_count"]
    return bool(
        item.get("type") != contract["type"]
        or item.get("uid") != contract["uid"]
        or item.get("gid") != contract["gid"]
        or not isinstance(mode, int)
        or (exact_mode is not None and mode != exact_mode)
        or (isinstance(required_mode, int) and mode & required_mode != required_mode)
        or (isinstance(forbidden_mode, int) and mode & forbidden_mode)
        or (
            expected_link_count is not None
            and item.get("link_count") != expected_link_count
        )
    )


def _public_document_facts(
    documents: dict[str, dict[str, Any]],
    *,
    expected_release_sha: str,
    expected_tree_sha: str,
) -> dict[str, dict[str, bool]]:
    result: dict[str, dict[str, bool]] = {}
    for path, value in documents.items():
        fact = {"validated": True}
        release_sha = value.get("commit_sha") or value.get("proof_base_sha") or value.get(
            "release_sha"
        )
        if release_sha is not None:
            fact["release_matches"] = release_sha == expected_release_sha
        if "tree_sha" in value:
            fact["tree_matches"] = value["tree_sha"] == expected_tree_sha
        result[path] = fact
    return result


class FilesystemAdapter:
    """Production filesystem adapter; it never exposes mutating operations."""

    def __init__(self, *, expected_release_sha: str) -> None:
        if _SHA_RE.fullmatch(expected_release_sha or "") is None:
            raise PreimageRefusal("INVALID_ARGUMENTS")
        self._manifest_path = (
            f"{SYSTEM_ROOT}/releases/{expected_release_sha}/"
            ".executive-release-manifest.json"
        )

    def metadata(self, path: str) -> dict[str, Any]:
        if not _is_frozen_path(path):
            raise PreimageRefusal("PATH_ESCAPE")
        ancestors = self._validate_ancestors(path)
        try:
            result = project_metadata(path, os.lstat(path))
        except FileNotFoundError:
            result = {"path": path, "exists": False}
        except PermissionError:
            raise PreimageUnsettled("FILESYSTEM_DENIED") from None
        if ancestors != self._validate_ancestors(path):
            raise PreimageUnsettled("FILESYSTEM_TORN")
        return result

    def read(self, path: str, *, expected: dict[str, Any] | None = None) -> bytes:
        if path not in CONTENT_PATHS and path != self._manifest_path:
            raise PreimageRefusal("PATH_ESCAPE")
        ancestors = self._validate_ancestors(path)
        payload = _read_anchored_content(path, expected=expected)
        if ancestors != self._validate_ancestors(path):
            raise PreimageUnsettled("FILESYSTEM_TORN")
        return payload

    @staticmethod
    def _validate_ancestors(path: str) -> tuple[tuple[str, int, int, int, int], ...]:
        required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
        if any(not hasattr(os, name) for name in required):
            raise PreimageRefusal("UNSAFE_ANCESTOR")
        flags = (
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | os.O_CLOEXEC
            | os.O_NONBLOCK
        )
        current = Path("/")
        identities: list[tuple[str, int, int, int, int]] = []
        for part in Path(path).parts[1:-1]:
            current /= part
            try:
                info = os.lstat(current)
            except FileNotFoundError:
                return tuple(identities)
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
                    physical = Path("/private/var")
                else:
                    raise PreimageRefusal("UNSAFE_ANCESTOR")
            else:
                physical = (
                    Path("/private/var", *current.parts[2:])
                    if current.parts[:2] == ("/", "var")
                    else current
                )
                if not stat.S_ISDIR(info.st_mode):
                    raise PreimageRefusal("UNSAFE_ANCESTOR")
            try:
                descriptor = os.open(physical, flags)
                try:
                    bound = os.fstat(descriptor)
                finally:
                    os.close(descriptor)
            except PermissionError:
                raise PreimageUnsettled("FILESYSTEM_DENIED") from None
            except OSError:
                raise PreimageUnsettled("FILESYSTEM_TORN") from None
            if not stat.S_ISDIR(bound.st_mode):
                raise PreimageRefusal("UNSAFE_ANCESTOR")
            if current != Path("/var") and (bound.st_dev, bound.st_ino) != (
                info.st_dev,
                info.st_ino,
            ):
                raise PreimageUnsettled("FILESYSTEM_TORN")
            if bound.st_uid not in {0, 450, 451, 452, 457} or stat.S_IMODE(
                bound.st_mode
            ) & 0o022:
                raise PreimageRefusal("UNSAFE_ANCESTOR")
            identities.append(
                (
                    os.fspath(current),
                    bound.st_dev,
                    bound.st_ino,
                    bound.st_mtime_ns,
                    bound.st_ctime_ns,
                )
            )
        return tuple(identities)


def _content_contract(path: str) -> tuple[int, int, int]:
    if path in PLISTS:
        return 0, 0, 0o644
    if path == CONTROL_CONFIG:
        return 0, 450, 0o440
    if path == WORKER_CONFIG:
        return 0, 451, 0o440
    if path == PYTHON_PROVENANCE:
        return 0, 0, 0o400
    if path == CODEX_ATTESTATION:
        return 0, 451, 0o440
    if re.fullmatch(
        re.escape(f"{SYSTEM_ROOT}/releases/")
        + r"[0-9a-f]{40}/\.executive-release-manifest\.json",
        path,
    ):
        return 0, 0, 0o444
    raise PreimageRefusal("PATH_ESCAPE")


def _read_anchored_content(
    path: str, *, expected: dict[str, Any] | None
) -> bytes:
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required):
        raise PreimageRefusal("UNSAFE_METADATA")
    directory_flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | os.O_CLOEXEC
        | os.O_NONBLOCK
    )
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    lexical_parts = list(Path(path).parts[1:])
    if lexical_parts and lexical_parts[0] == "var":
        try:
            target = os.readlink("/var")
        except OSError:
            raise PreimageUnsettled("FILESYSTEM_TORN") from None
        if target not in ("private/var", "/private/var"):
            raise PreimageRefusal("PATH_ESCAPE")
        parts = ["private", "var", *lexical_parts[1:]]
    else:
        parts = lexical_parts
    if not parts:
        raise PreimageRefusal("PATH_ESCAPE")

    directory_fds: list[int] = []
    descriptor: int | None = None
    try:
        directory_fds.append(os.open("/", directory_flags))
        ancestor_identities: list[tuple[int, int, int, int]] = []
        for component in parts[:-1]:
            child_fd = os.open(component, directory_flags, dir_fd=directory_fds[-1])
            directory_fds.append(child_fd)
            info = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in {0, 450, 451, 452, 457}
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                raise PreimageRefusal("UNSAFE_ANCESTOR")
            ancestor_identities.append(
                (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
            )
        final_name = parts[-1]
        named_before = os.stat(
            final_name, dir_fd=directory_fds[-1], follow_symlinks=False
        )
        if stat.S_ISLNK(named_before.st_mode):
            raise PreimageRefusal("PATH_ESCAPE")
        if not stat.S_ISREG(named_before.st_mode):
            raise PreimageRefusal("UNSUPPORTED_TYPE")
        if named_before.st_size > MAX_CONTENT_BYTES:
            raise PreimageRefusal("CONTENT_OVERSIZED")
        descriptor = os.open(final_name, file_flags, dir_fd=directory_fds[-1])
        descriptor_before = os.fstat(descriptor)
        if _identity(named_before) != _identity(descriptor_before):
            raise PreimageUnsettled("FILESYSTEM_TORN")
        uid, gid, mode = _content_contract(path)
        if (
            not stat.S_ISREG(descriptor_before.st_mode)
            or descriptor_before.st_uid != uid
            or descriptor_before.st_gid != gid
            or stat.S_IMODE(descriptor_before.st_mode) != mode
            or descriptor_before.st_nlink != 1
        ):
            raise PreimageRefusal("UNSAFE_METADATA")
        if expected is not None and (
            expected.get("device"),
            expected.get("inode"),
            expected.get("size"),
            expected.get("mtime_ns"),
            expected.get("ctime_ns"),
        ) != _identity(descriptor_before):
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
        named_after = os.stat(
            final_name, dir_fd=directory_fds[-1], follow_symlinks=False
        )
        if len(
            {
                _identity(named_before),
                _identity(descriptor_before),
                _identity(descriptor_after),
                _identity(named_after),
            }
        ) != 1:
            raise PreimageUnsettled("FILESYSTEM_TORN")
        for ancestor_fd, identity in zip(
            directory_fds[1:], ancestor_identities, strict=True
        ):
            info = os.fstat(ancestor_fd)
            if (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns) != identity:
                raise PreimageUnsettled("FILESYSTEM_TORN")
        if len(payload) > MAX_CONTENT_BYTES:
            raise PreimageRefusal("CONTENT_OVERSIZED")
        return payload
    except FileNotFoundError:
        raise PreimageUnsettled("FILESYSTEM_TORN") from None
    except PermissionError:
        raise PreimageUnsettled("FILESYSTEM_DENIED") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_bounded_file(
    path: str,
    *,
    expected: dict[str, Any] | None = None,
    enforce_contract: bool = False,
) -> bytes:
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
    required = ("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required):
        raise PreimageRefusal("UNSAFE_METADATA")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    try:
        descriptor = os.open(lexical, flags)
        try:
            descriptor_before = os.fstat(descriptor)
            if (descriptor_before.st_dev, descriptor_before.st_ino) != (
                info_before.st_dev,
                info_before.st_ino,
            ):
                raise PreimageUnsettled("FILESYSTEM_TORN")
            if enforce_contract:
                uid, gid, mode = _content_contract(path)
                if (
                    not stat.S_ISREG(descriptor_before.st_mode)
                    or descriptor_before.st_uid != uid
                    or descriptor_before.st_gid != gid
                    or stat.S_IMODE(descriptor_before.st_mode) != mode
                    or descriptor_before.st_nlink != 1
                ):
                    raise PreimageRefusal("UNSAFE_METADATA")
            if expected is not None and (
                expected.get("device"),
                expected.get("inode"),
                expected.get("size"),
                expected.get("mtime_ns"),
                expected.get("ctime_ns"),
            ) != _identity(descriptor_before):
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
        _identity(value)
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
    raw_principals = {name: principals.lookup(name) for name in PRINCIPALS}
    principal_facts: dict[str, dict[str, Any]] = {}
    for name, expected in PRINCIPALS.items():
        value = raw_principals[name]
        matches = bool(
            value is not None
            and all(value.get(field) == expected[field] for field in expected)
            and value.get("group_gid") == expected["gid"]
        )
        principal_facts[name] = {
            "present": value is not None,
            "matches": matches,
            **(dict(expected) if matches else {}),
        }
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
            payload = filesystem.read(path, expected=item)
            if len(payload) != item["size"]:
                raise PreimageUnsettled("FILESYSTEM_TORN")
            key, value = parse_content_document(
                path,
                payload,
                manifest_path=manifest_path,
                expected_release_sha=expected_release_sha,
                expected_tree_sha=expected_tree_sha,
            )
            documents[key] = value
        except PreimageRefusal as exc:
            unsafe = True
            reason_codes.add(exc.code)

    installation = evaluate_installation(documents, expected_release_sha, expected_tree_sha)
    principals_match = True
    for name in PRINCIPALS:
        value = principal_facts[name]
        if not value["present"]:
            principals_match = False
            continue
        if not value["matches"]:
            principals_match = False
            unsafe = True
            reason_codes.add("PRINCIPAL_MISMATCH")

    services: list[dict[str, Any]] = []
    disabled_result = commands.run(("/bin/launchctl", "print-disabled", "system"))
    disabled = parse_disabled_state(disabled_result["stdout"])
    for label in LABELS:
        result = commands.run(("/bin/launchctl", "print", f"system/{label}"))
        if result.get("status") == "absent":
            services.append(
                {
                    "label": label,
                    "active": False,
                    "loaded": False,
                    "disabled": disabled[label],
                    "owned": True,
                }
            )
            continue
        plist_path = PLISTS[LABELS.index(label)]
        plist_document = documents.get(plist_path)
        expected_program = None
        expected_arguments = None
        if plist_document is not None:
            installed_sha = plist_document.get("release_sha")
            if isinstance(installed_sha, str):
                expected_program = expected_loaded_program(label, installed_sha)
            internal_arguments = plist_document.get("_program_arguments")
            if isinstance(internal_arguments, list):
                expected_arguments = internal_arguments
        state_value = parse_launchd_state(
            result["stdout"],
            expected_program=expected_program,
            expected_arguments=expected_arguments,
        )
        service = {
            "label": label,
            **state_value,
            "loaded": True,
            "disabled": disabled[label],
            "owned": True,
        }
        if state_value["active"]:
            process = commands.run(
                ("/bin/ps", "-o", "uid=,gid=,pid=,ppid=", "-p", str(state_value["pid"]))
            )
            identity = parse_process_identity(process["stdout"], expected_pid=state_value["pid"])
            service["process"] = identity
            service["owned"] = service_owned(
                label,
                plist_document,
                identity,
                program_matches=state_value.get("program_matches") is True,
                arguments_match=state_value.get("arguments_match") is True,
                release_matches=(
                    plist_document is not None
                    and plist_document.get("release_sha") == expected_release_sha
                ),
            )
        services.append(service)

    release_root_present = next(
        item["exists"] for item in metadata if item["path"] == release_root
    )
    manifest_present = next(
        item["exists"] for item in metadata if item["path"] == manifest_path
    )
    socket_residual = any(
        item.get("exists")
        and item["path"]
        in {
            "/var/run/mastermind-executive/ceo-ingress.sock",
            "/var/run/mastermind-dialogue-observation/dialogue-observation.sock",
            "/var/run/mastermind-agent-relay/agent-relay.sock",
        }
        for item in metadata
    )
    snapshot = {
        "unsafe": unsafe,
        "effect_unknown": installation["effect_unknown"]
        or release_root_present != manifest_present
        or (socket_residual and not any(service["active"] for service in services))
        or any(
            not service["active"]
            and (service["loaded"] or not service["disabled"])
            for service in services
        ),
        "surface_present": bool(present)
        or any(value["present"] for value in principal_facts.values()),
        "matching_installation": installation["matching_installation"] and principals_match,
        "coherent_stale_installation": (
            installation["coherent_stale_installation"] and principals_match
        ),
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
            "documents": _public_document_facts(
                documents,
                expected_release_sha=expected_release_sha,
                expected_tree_sha=expected_tree_sha,
            ),
            "metadata": metadata,
            "principals": principal_facts,
            "services": services,
            "invoking_uid": uid,
        },
        "probe_counts": {
            "fixed_public_documents": len(CONTENT_PATHS),
            "release_manifests": 1,
            "content_paths_total": len(CONTENT_PATHS) + 1,
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
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "expected_release_sha": expected_release_sha,
        "expected_tree_sha": expected_tree_sha,
        "state": state,
        "classification": classification,
        "reason_codes": [code],
        "facts": {"probe_settlement": facts} if facts else {},
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
            facts=exc.facts,
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
            filesystem=FilesystemAdapter(
                expected_release_sha=args.expected_release_sha
            ),
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
