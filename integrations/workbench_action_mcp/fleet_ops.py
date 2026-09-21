"""Host operator for an installed Workbench Action tunnel fleet.

This module is deliberately thin.  It reads the existing Workbench Action
owner config, asks tunnel-client for the existing managed-runtime truth, and
performs a bounded lease-refresh ceremony.  It owns no lifecycle, registry,
credential, retry loop, scheduler, project selection, or action identity.

The caller supplies one alias/config pair at a time (or a finite list for
doctor).  Live account/tunnel/workspace identifiers therefore remain in the
existing owner configuration and tunnel-client state rather than source.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import stat
import subprocess
import time
from collections.abc import Callable, Sequence
from typing import Any

from integrations.workbench_action_mcp.tunnel import (
    TUNNEL_SCHEMA,
    TunnelConfig,
    TunnelConfigurationError,
    load_tunnel_config,
    parse_tunnel_config,
)

FINAL_TOOL_NAMES = (
    "workspace_manifest",
    "read_project_file",
    "preview_text_replace",
    "prepare_text_patch",
    "commit_text_patch",
    "reconcile_text_patch",
    "prepare_project_command",
    "run_project_command",
    "read_action_result",
    "reconcile_action",
)
MODIFYING_TOOL_NAMES = ("commit_text_patch", "run_project_command")
DEFAULT_WARN_BEFORE_MS = 7 * 24 * 60 * 60 * 1000
MAX_OPERATOR_JSON_BYTES = 2 * 1024 * 1024
_ARTIFACT = re.compile(
    r"^(?P<action>[0-9a-f]{32})\.(?P<kind>claim|process|result|stdout|stderr)$"
)
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


class FleetOperationError(RuntimeError):
    """Closed host-operator refusal."""

    _CODES = frozenset(
        {
            "ALIAS_STATUS_UNAVAILABLE",
            "ALIAS_NOT_READY",
            "CHANNEL_BINDING_MISMATCH",
            "CONFIGURATION_REFUSED",
            "CONFIG_CHANGED_DURING_CEREMONY",
            "CONFIG_PATH_REFUSED",
            "LEASE_EXPIRED",
            "LEASE_RENEWAL_REFUSED",
            "PROJECT_HEAD_MISMATCH",
            "RUNTIME_AUTH_REF_UNAVAILABLE",
            "RUNTIME_RECONNECT_FAILED",
            "RUNTIME_STOP_FAILED",
            "SOURCE_RELEASE_MISMATCH",
            "TARGET_REFUSED",
            "TOOL_CONTRACT_MISMATCH",
            "UNRESOLVED_ACTION_EVIDENCE",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("unknown fleet operation error")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class ArtifactEvidence:
    unresolved_action_ids: tuple[str, ...]
    completed_action_count: int


@dataclasses.dataclass(frozen=True)
class DoctorReceipt:
    alias: str
    config_path: str
    state: str
    tunnel_id: str
    organization_id: str
    workspace_id: str
    project_ref: str
    committed_head: str | None
    lease_expires_at_ms: int
    lease_remaining_ms: int
    source_release_sha: str | None
    runtime_state: str
    healthy: bool
    ready: bool
    process_running: bool
    completed_action_count: int
    unresolved_action_ids: tuple[str, ...]
    warnings: tuple[str, ...]


Runner = Callable[[Sequence[str]], dict[str, Any]]
ToolProbe = Callable[[Sequence[str]], None]
HeadProbe = Callable[[str], str]


def _run_json(argv: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise FleetOperationError("ALIAS_STATUS_UNAVAILABLE")
    try:
        value = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise FleetOperationError("ALIAS_STATUS_UNAVAILABLE") from None
    if not isinstance(value, dict):
        raise FleetOperationError("ALIAS_STATUS_UNAVAILABLE")
    return value


def _same_euid_private_regular(path: str, *, exact_mode: int | None = None) -> os.stat_result:
    selected = Path(path)
    if not selected.is_absolute():
        raise FleetOperationError("CONFIG_PATH_REFUSED")
    try:
        before = selected.lstat()
    except OSError:
        raise FleetOperationError("CONFIG_PATH_REFUSED") from None
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_nlink != 1
    ):
        raise FleetOperationError("CONFIG_PATH_REFUSED")
    mode = stat.S_IMODE(before.st_mode)
    if exact_mode is None:
        if mode & 0o022:
            raise FleetOperationError("CONFIG_PATH_REFUSED")
    elif mode != exact_mode:
        raise FleetOperationError("CONFIG_PATH_REFUSED")
    return before


def _trusted_pinned_executable(path: str) -> os.stat_result:
    selected = Path(path)
    if not selected.is_absolute():
        raise FleetOperationError("TARGET_REFUSED")
    try:
        before = selected.lstat()
    except OSError:
        raise FleetOperationError("TARGET_REFUSED") from None
    mode = stat.S_IMODE(before.st_mode)
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid not in {0, os.geteuid()}
        or before.st_nlink != 1
        or mode & 0o022
        or not os.access(selected, os.X_OK)
    ):
        raise FleetOperationError("TARGET_REFUSED")
    return before


def _load_config(path: str) -> TunnelConfig:
    try:
        return load_tunnel_config(path)
    except (OSError, TunnelConfigurationError):
        raise FleetOperationError("CONFIGURATION_REFUSED") from None


def _bounded_json_file(path: Path, maximum: int) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > maximum:
            raise ValueError
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE") from None
    if not isinstance(value, dict):
        raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE")
    return value


def inspect_artifact_evidence(directory: str) -> ArtifactEvidence:
    """Conservatively classify the store before a lease-generation ceremony.

    A claim/process without a durable result, malformed result, one-sided
    result, or explicit EFFECT_UNKNOWN blocks renewal.  Completed APPLIED or
    NOT_APPLIED results are safe historical evidence and remain untouched.
    """

    root = Path(directory)
    try:
        info = root.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE")
        entries = tuple(root.iterdir())
    except OSError:
        raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE") from None

    actions: dict[str, set[str]] = {}
    for entry in entries:
        match = _ARTIFACT.fullmatch(entry.name)
        if match is None:
            raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE")
        try:
            opened = entry.lstat()
        except OSError:
            raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE") from None
        if (
            stat.S_ISLNK(opened.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) & 0o022
        ):
            raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE")
        actions.setdefault(match.group("action"), set()).add(match.group("kind"))

    unresolved: list[str] = []
    completed = 0
    for action_id, kinds in sorted(actions.items()):
        # Any observed action bytes require the durable claim/result pair.  This
        # deliberately treats orphan stdout/stderr as uncertainty too: command
        # output without its exact claim/result can be evidence of an interrupted
        # modifying action and must never be ignored by a renewal ceremony.
        if "claim" not in kinds or "result" not in kinds:
            unresolved.append(action_id)
            continue

        claim = _bounded_json_file(root / f"{action_id}.claim", 4096)
        result = _bounded_json_file(root / f"{action_id}.result", 16 * 1024)
        claim_identity = claim.get("identity")
        result_identity = result.get("identity")
        claimed_at = claim.get("claimed_at_ms")
        completed_at = result.get("completed_at_ms")
        purpose = claim_identity.get("purpose") if isinstance(claim_identity, dict) else None
        qualified = (
            claim.get("schema") == "mastermind.workbench_action_claim.v1"
            and claim.get("phase") == "claimed"
            and isinstance(claim_identity, dict)
            and claim_identity.get("action_id") == action_id
            and purpose in {"text_patch", "closed_command"}
            and result.get("schema") == "mastermind.workbench_action_result.v1"
            and result.get("durability") == "durable"
            and result.get("effect_state") in {"APPLIED", "NOT_APPLIED"}
            and result_identity == claim_identity
            and type(claimed_at) is int
            and type(completed_at) is int
            and completed_at >= claimed_at
        )

        # Process/output evidence, when present, must belong to a closed-command
        # action.  A process record must carry the identical immutable identity;
        # stdout/stderr without that process identity is never called complete.
        process = None
        if "process" in kinds:
            process = _bounded_json_file(root / f"{action_id}.process", 4096)
            qualified = qualified and (
                purpose == "closed_command"
                and process.get("schema") == "mastermind.workbench_command_process.v1"
                and process.get("identity") == claim_identity
            )
        if "stdout" in kinds or "stderr" in kinds:
            qualified = qualified and purpose == "closed_command" and process is not None
        if purpose == "text_patch" and kinds - {"claim", "result"}:
            qualified = False

        if not qualified:
            unresolved.append(action_id)
            continue
        completed += 1

    return ArtifactEvidence(tuple(unresolved), completed)


def _status(alias: str, runner: Runner) -> dict[str, Any]:
    if not alias or any(c.isspace() for c in alias):
        raise FleetOperationError("ALIAS_STATUS_UNAVAILABLE")
    return runner(("tunnel-client", "runtimes", "status", alias, "--json"))


def _remote(status: dict[str, Any]) -> dict[str, Any]:
    value = status.get("remote") or status.get("tunnel")
    if not isinstance(value, dict):
        raise FleetOperationError("CHANNEL_BINDING_MISMATCH")
    return value


def _validate_binding(config: TunnelConfig, status: dict[str, Any]) -> None:
    remote = _remote(status)
    if (
        remote.get("id") != config.channel.tunnel_id
        or remote.get("organization_ids") != [config.channel.organization_id]
        or remote.get("workspace_ids") != [config.channel.workspace_id]
    ):
        raise FleetOperationError("CHANNEL_BINDING_MISMATCH")


def _read_json_line(
    process: subprocess.Popen[bytes], buffer: bytes, *, timeout: float
) -> tuple[dict[str, Any], bytes]:
    if process.stdout is None:
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    deadline = time.monotonic() + timeout
    while b"\n" not in buffer:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        ready, _, _ = select.select([process.stdout], [], [], remaining)
        if not ready:
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        chunk = os.read(process.stdout.fileno(), 65536)
        if not chunk:
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        buffer += chunk
        if len(buffer) > MAX_OPERATOR_JSON_BYTES:
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    line, remainder = buffer.split(b"\n", 1)
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, UnicodeError, ValueError):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH") from None
    if not isinstance(value, dict):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    return value, remainder


def _send_json_line(process: subprocess.Popen[bytes], value: object) -> None:
    if process.stdin is None:
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    try:
        process.stdin.write(json.dumps(value, separators=(",", ":")).encode() + b"\n")
        process.stdin.flush()
    except OSError:
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH") from None


def _validate_listed_tools(value: dict[str, Any]) -> None:
    result = value.get("result")
    if not isinstance(result, dict):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    tools = result.get("tools")
    if not isinstance(tools, list) or len(tools) != len(FINAL_TOOL_NAMES):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    by_name: dict[str, dict[str, Any]] = {}
    for row in tools:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        name = row["name"]
        if name in by_name:
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        by_name[name] = row
    if set(by_name) != set(FINAL_TOOL_NAMES):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    for name in FINAL_TOOL_NAMES:
        row = by_name[name]
        annotations = row.get("annotations")
        input_schema = row.get("inputSchema")
        output_schema = row.get("outputSchema")
        if not all(isinstance(item, dict) for item in (annotations, input_schema, output_schema)):
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        modifying = name in MODIFYING_TOOL_NAMES
        if (
            annotations.get("readOnlyHint") is modifying
            or annotations.get("destructiveHint") is not modifying
            or annotations.get("idempotentHint") is not True
            or annotations.get("openWorldHint") is not False
            or input_schema.get("additionalProperties") is not False
            or output_schema.get("additionalProperties") is not False
        ):
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")


def _probe_tool_contract(command: Sequence[str]) -> None:
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            list(command),
            cwd="/",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONUNBUFFERED": "1",
            },
        )
        buffer = b""
        _send_json_line(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "workbench-fleet-doctor", "version": "1"},
                },
            },
        )
        initialized, buffer = _read_json_line(process, buffer, timeout=20.0)
        if initialized.get("id") != 1 or "result" not in initialized:
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        _send_json_line(
            process,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        _send_json_line(
            process,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        while True:
            listed, buffer = _read_json_line(process, buffer, timeout=5.0)
            if listed.get("id") == 2:
                _validate_listed_tools(listed)
                break
            if listed.get("method") == "ping" and "id" in listed:
                _send_json_line(
                    process,
                    {"jsonrpc": "2.0", "id": listed["id"], "result": {}},
                )
                continue
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
        if process.stdin is not None:
            process.stdin.close()
        if process.wait(timeout=10) != 0:
            raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    except FleetOperationError:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        raise
    except (OSError, subprocess.SubprocessError):
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH") from None
    finally:
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is None or stream.closed:
                    continue
                try:
                    stream.close()
                except OSError:
                    pass


def _probe_describe_contract(command: Sequence[str]) -> None:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH") from None
    if completed.returncode != 0:
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")
    try:
        value = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH") from None
    if (
        not isinstance(value, dict)
        or value.get("mode") != "fixed-channel-stdio"
        or value.get("config_schema") != TUNNEL_SCHEMA
        or value.get("scope") != "workbench.action"
        or value.get("tools") != list(FINAL_TOOL_NAMES)
    ):
        raise FleetOperationError("TOOL_CONTRACT_MISMATCH")


def _git_head(project_root: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", project_root, "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise FleetOperationError("PROJECT_HEAD_MISMATCH") from None
    selected = completed.stdout.strip()
    if completed.returncode != 0 or _HEX40.fullmatch(selected) is None:
        raise FleetOperationError("PROJECT_HEAD_MISMATCH")
    return selected


def _validate_project_head(config: TunnelConfig, head_probe: HeadProbe) -> None:
    expected = config.lease.committed_head
    if expected is None:
        return
    if _HEX40.fullmatch(expected) is None or head_probe(config.project_root) != expected:
        raise FleetOperationError("PROJECT_HEAD_MISMATCH")


def _target_release_sha(
    status: dict[str, Any],
    config: TunnelConfig,
    config_path: str,
    tool_probe: ToolProbe,
) -> str | None:
    process = status.get("process")
    if not isinstance(process, dict):
        raise FleetOperationError("TARGET_REFUSED")
    target = process.get("target_value")
    if not isinstance(target, str) or not target.startswith("/"):
        raise FleetOperationError("TARGET_REFUSED")
    _same_euid_private_regular(target)
    try:
        raw = Path(target).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise FleetOperationError("TARGET_REFUSED") from None
    if len(raw.encode("utf-8")) > 16 * 1024:
        raise FleetOperationError("TARGET_REFUSED")
    lines = raw.splitlines()
    if len(lines) != 2 or lines[0] != "#!/bin/sh":
        raise FleetOperationError("TARGET_REFUSED")
    try:
        argv = shlex.split(lines[1], posix=True)
    except ValueError:
        raise FleetOperationError("TARGET_REFUSED") from None
    if (
        len(argv) != 5
        or argv[0] != "exec"
        or argv[3] != "--config"
        or argv[4] != config_path
    ):
        raise FleetOperationError("TARGET_REFUSED")
    python_executable = argv[1]
    launcher = argv[2]
    if not python_executable.startswith("/") or not launcher.startswith("/"):
        raise FleetOperationError("TARGET_REFUSED")
    selected_python = os.path.realpath(python_executable)
    configured_python = os.path.realpath(config.python_executable)
    if selected_python != configured_python:
        raise FleetOperationError("TARGET_REFUSED")
    _trusted_pinned_executable(selected_python)
    try:
        observed_python_sha = hashlib.sha256(Path(selected_python).read_bytes()).hexdigest()
    except OSError:
        raise FleetOperationError("TARGET_REFUSED") from None
    if observed_python_sha != config.python_sha256:
        raise FleetOperationError("TARGET_REFUSED")
    _same_euid_private_regular(launcher)
    if Path(launcher).name != "mastermind_workbench_action_stdio.py":
        raise FleetOperationError("TARGET_REFUSED")
    match = re.search(r"/releases/([0-9a-f]{40})/scripts/mastermind_workbench_action_stdio\.py$", launcher)
    if match is None:
        raise FleetOperationError("TARGET_REFUSED")
    tool_probe((python_executable, launcher, "--describe"))
    return match.group(1)


def doctor(
    *,
    alias: str,
    config_path: str,
    expected_source_sha: str | None = None,
    warn_before_ms: int = DEFAULT_WARN_BEFORE_MS,
    now_ms: int | None = None,
    runner: Runner = _run_json,
    tool_probe: ToolProbe = _probe_describe_contract,
    head_probe: HeadProbe = _git_head,
) -> DoctorReceipt:
    _same_euid_private_regular(config_path)
    config = _load_config(config_path)
    if config.schema != TUNNEL_SCHEMA:
        raise FleetOperationError("CONFIGURATION_REFUSED")
    evidence = inspect_artifact_evidence(config.artifact_directory)
    _validate_project_head(config, head_probe)
    status = _status(alias, runner)
    _validate_binding(config, status)

    healthy = status.get("healthy") is True
    ready = status.get("ready") is True
    process_running = status.get("process_running") is True
    runtime_state = status.get("runtime_state")
    if not isinstance(runtime_state, str):
        runtime_state = "unknown"
    if not (healthy and ready and process_running and runtime_state == "ready"):
        raise FleetOperationError("ALIAS_NOT_READY")

    release_sha = _target_release_sha(status, config, config_path, tool_probe)
    if expected_source_sha is not None:
        if _HEX40.fullmatch(expected_source_sha) is None:
            raise FleetOperationError("SOURCE_RELEASE_MISMATCH")
        if release_sha != expected_source_sha:
            raise FleetOperationError("SOURCE_RELEASE_MISMATCH")

    selected_now = int(time.time() * 1000) if now_ms is None else now_ms
    remaining = config.lease.lease_expires_at_ms - selected_now
    if remaining <= 0:
        raise FleetOperationError("LEASE_EXPIRED")
    if evidence.unresolved_action_ids:
        raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE")

    warnings: list[str] = []
    state = "READY"
    if remaining <= warn_before_ms:
        state = "RENEW_SOON"
        warnings.append("LEASE_RENEWAL_DUE")

    return DoctorReceipt(
        alias=alias,
        config_path=config_path,
        state=state,
        tunnel_id=config.channel.tunnel_id,
        organization_id=config.channel.organization_id,
        workspace_id=config.channel.workspace_id,
        project_ref=config.lease.project_ref,
        committed_head=config.lease.committed_head,
        lease_expires_at_ms=config.lease.lease_expires_at_ms,
        lease_remaining_ms=remaining,
        source_release_sha=release_sha,
        runtime_state=runtime_state,
        healthy=healthy,
        ready=ready,
        process_running=process_running,
        completed_action_count=evidence.completed_action_count,
        unresolved_action_ids=evidence.unresolved_action_ids,
        warnings=tuple(warnings),
    )


@dataclasses.dataclass(frozen=True)
class ConfigSnapshot:
    document: dict[str, Any]
    config: TunnelConfig
    fingerprint: tuple[int, int, int, int, int, int, int, str]


def _config_stat_fingerprint(info: os.stat_result, raw: bytes) -> tuple[int, int, int, int, int, int, int, str]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        stat.S_IMODE(info.st_mode),
        info.st_nlink,
        info.st_mtime_ns,
        info.st_ctime_ns,
        hashlib.sha256(raw).hexdigest(),
    )


def _secure_config_snapshot(path: str) -> ConfigSnapshot:
    before = _same_euid_private_regular(path)
    try:
        raw = Path(path).read_bytes()
        if not raw or len(raw) > 64 * 1024:
            raise ValueError
        after = Path(path).lstat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_uid,
            stat.S_IMODE(before.st_mode),
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_uid,
            stat.S_IMODE(after.st_mode),
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError
        value = json.loads(raw.decode("ascii"))
        if not isinstance(value, dict):
            raise ValueError
        config = _load_config(path)
        final = Path(path).lstat()
        if (
            after.st_dev,
            after.st_ino,
            after.st_uid,
            stat.S_IMODE(after.st_mode),
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            final.st_dev,
            final.st_ino,
            final.st_uid,
            stat.S_IMODE(final.st_mode),
            final.st_nlink,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ):
            raise ValueError
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise FleetOperationError("CONFIGURATION_REFUSED") from None
    return ConfigSnapshot(
        document=value,
        config=config,
        fingerprint=_config_stat_fingerprint(final, raw),
    )


def _assert_config_unchanged(path: str, expected: ConfigSnapshot) -> None:
    observed = _secure_config_snapshot(path)
    if observed.fingerprint != expected.fingerprint or observed.config != expected.config:
        raise FleetOperationError("CONFIG_CHANGED_DURING_CEREMONY")


def _atomic_replace_config(
    path: str,
    document: dict[str, Any],
    *,
    expected_preimage: ConfigSnapshot,
) -> None:
    selected = Path(path)
    parent = selected.parent
    payload = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("ascii")
    temporary = parent / f".{selected.name}.renew.{os.getpid()}"
    fd = -1
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        _assert_config_unchanged(path, expected_preimage)
        os.replace(temporary, selected)
        os.chmod(selected, 0o600)
        dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except FleetOperationError:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    except OSError:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temporary.unlink()
        except OSError:
            pass
        raise FleetOperationError("LEASE_RENEWAL_REFUSED") from None
    _same_euid_private_regular(path, exact_mode=0o600)
    _load_config(path)


@dataclasses.dataclass(frozen=True)
class RuntimeRoute:
    profile_name: str
    profile_dir: str
    target: str
    auth_ref: str


def _runtime_route(status: dict[str, Any]) -> RuntimeRoute:
    process = status.get("process")
    if not isinstance(process, dict):
        raise FleetOperationError("RUNTIME_AUTH_REF_UNAVAILABLE")
    profile_name = process.get("profile_name")
    profile_dir = process.get("profile_dir")
    target = process.get("target_value")
    if not all(isinstance(v, str) and v for v in (profile_name, profile_dir, target)):
        raise FleetOperationError("RUNTIME_AUTH_REF_UNAVAILABLE")
    if not str(target).startswith("/"):
        raise FleetOperationError("TARGET_REFUSED")
    auth_ref = status.get("remote_lookup_auth_ref")
    if not isinstance(auth_ref, str) or not (
        auth_ref.startswith("file:") or auth_ref.startswith("env:")
    ):
        raise FleetOperationError("RUNTIME_AUTH_REF_UNAVAILABLE")
    return RuntimeRoute(str(profile_name), str(profile_dir), str(target), auth_ref)


def _connect_route(
    *,
    alias: str,
    config: TunnelConfig,
    route: RuntimeRoute,
    runner: Runner,
) -> None:
    connected = runner(
        (
            "tunnel-client",
            "runtimes",
            "connect",
            "--alias",
            alias,
            "--profile",
            route.profile_name,
            "--profile-dir",
            route.profile_dir,
            "--tunnel-id",
            config.channel.tunnel_id,
            "--mcp-command",
            route.target,
            "--runtime-api-key",
            route.auth_ref,
            "--json",
        )
    )
    if (
        connected.get("healthy") is not True
        or connected.get("ready") is not True
        or connected.get("runtime_state") != "ready"
    ):
        raise FleetOperationError("RUNTIME_RECONNECT_FAILED")


def _stop_and_probe(
    *,
    alias: str,
    config_path: str,
    snapshot: ConfigSnapshot,
    status: dict[str, Any],
    runner: Runner,
    native_probe: ToolProbe,
) -> RuntimeRoute:
    config = snapshot.config
    _assert_config_unchanged(config_path, snapshot)
    _validate_binding(config, status)
    if not (
        status.get("healthy") is True
        and status.get("ready") is True
        and status.get("process_running") is True
        and status.get("runtime_state") == "ready"
    ):
        raise FleetOperationError("ALIAS_NOT_READY")
    route = _runtime_route(status)
    stopped = runner(("tunnel-client", "runtimes", "stop", alias, "--json"))
    if stopped.get("process_running") is True or stopped.get("runtime_state") not in {
        "stopped",
        None,
    }:
        raise FleetOperationError("RUNTIME_STOP_FAILED")
    _assert_config_unchanged(config_path, snapshot)
    try:
        native_probe((route.target,))
        _assert_config_unchanged(config_path, snapshot)
    except FleetOperationError as error:
        try:
            _assert_config_unchanged(config_path, snapshot)
        except FleetOperationError:
            raise FleetOperationError("CONFIG_CHANGED_DURING_CEREMONY") from error
        _connect_route(alias=alias, config=config, route=route, runner=runner)
        raise
    return route


def _require_source(release_sha: str | None, expected_source_sha: str | None) -> None:
    if expected_source_sha is None:
        return
    if (
        _HEX40.fullmatch(expected_source_sha) is None
        or release_sha != expected_source_sha
    ):
        raise FleetOperationError("SOURCE_RELEASE_MISMATCH")


def qualify(
    *,
    alias: str,
    config_path: str,
    expected_source_sha: str | None = None,
    runner: Runner = _run_json,
    tool_probe: ToolProbe = _probe_describe_contract,
    native_probe: ToolProbe = _probe_tool_contract,
) -> DoctorReceipt:
    """Prove the actual stopped stdio tool surface, then restore the same route."""

    snapshot = _secure_config_snapshot(config_path)
    before_receipt = doctor(
        alias=alias,
        config_path=config_path,
        expected_source_sha=expected_source_sha,
        runner=runner,
        tool_probe=tool_probe,
    )
    _assert_config_unchanged(config_path, snapshot)
    config = snapshot.config
    route = _stop_and_probe(
        alias=alias,
        config_path=config_path,
        snapshot=snapshot,
        status=_status(alias, runner),
        runner=runner,
        native_probe=native_probe,
    )
    _assert_config_unchanged(config_path, snapshot)
    _connect_route(alias=alias, config=config, route=route, runner=runner)
    _assert_config_unchanged(config_path, snapshot)
    after = doctor(
        alias=alias,
        config_path=config_path,
        expected_source_sha=expected_source_sha,
        runner=runner,
        tool_probe=tool_probe,
    )
    if (
        after.tunnel_id != before_receipt.tunnel_id
        or after.organization_id != before_receipt.organization_id
        or after.workspace_id != before_receipt.workspace_id
        or after.project_ref != before_receipt.project_ref
    ):
        raise FleetOperationError("CHANNEL_BINDING_MISMATCH")
    return after


def renew(
    *,
    alias: str,
    config_path: str,
    extend_ms: int,
    expected_source_sha: str | None = None,
    now_ms: int | None = None,
    runner: Runner = _run_json,
    tool_probe: ToolProbe = _probe_describe_contract,
    native_probe: ToolProbe = _probe_tool_contract,
) -> DoctorReceipt:
    """Refresh one stopped/reconnected alias without changing its channel identity.

    The operation refuses unresolved action evidence before stopping the runtime.
    Only lease_expires_at_ms changes in the owner document.  The same local
    alias/profile/target/tunnel/runtime-key reference is then reconnected.
    """

    if type(extend_ms) is not int or extend_ms < 60_000:
        raise FleetOperationError("LEASE_RENEWAL_REFUSED")
    _same_euid_private_regular(config_path)
    snapshot = _secure_config_snapshot(config_path)
    config = snapshot.config
    evidence = inspect_artifact_evidence(config.artifact_directory)
    if evidence.unresolved_action_ids:
        raise FleetOperationError("UNRESOLVED_ACTION_EVIDENCE")

    before = _status(alias, runner)
    _validate_binding(config, before)
    release_sha = _target_release_sha(before, config, config_path, tool_probe)
    _require_source(release_sha, expected_source_sha)
    route = _stop_and_probe(
        alias=alias,
        config_path=config_path,
        snapshot=snapshot,
        status=before,
        runner=runner,
        native_probe=native_probe,
    )

    selected_now = int(time.time() * 1000) if now_ms is None else now_ms
    document = json.loads(json.dumps(snapshot.document))
    lease = document.get("lease")
    if not isinstance(lease, dict):
        _connect_route(alias=alias, config=config, route=route, runner=runner)
        raise FleetOperationError("LEASE_RENEWAL_REFUSED")
    new_expiry = selected_now + extend_ms
    lease["lease_expires_at_ms"] = new_expiry
    expected = dataclasses.replace(
        config,
        lease=dataclasses.replace(config.lease, lease_expires_at_ms=new_expiry),
    )
    try:
        updated = parse_tunnel_config(document)
    except TunnelConfigurationError:
        _connect_route(alias=alias, config=config, route=route, runner=runner)
        raise FleetOperationError("LEASE_RENEWAL_REFUSED") from None
    if updated != expected:
        _connect_route(alias=alias, config=config, route=route, runner=runner)
        raise FleetOperationError("LEASE_RENEWAL_REFUSED")
    try:
        _atomic_replace_config(
            config_path, document, expected_preimage=snapshot
        )
    except FleetOperationError as error:
        # Only an unchanged old preimage is safe to reconnect automatically.
        try:
            observed = _secure_config_snapshot(config_path)
        except FleetOperationError:
            raise error
        if observed.fingerprint == snapshot.fingerprint and observed.config == config:
            _connect_route(alias=alias, config=config, route=route, runner=runner)
        raise error

    _connect_route(alias=alias, config=config, route=route, runner=runner)

    return doctor(
        alias=alias,
        config_path=config_path,
        expected_source_sha=expected_source_sha,
        now_ms=selected_now,
        runner=runner,
        tool_probe=tool_probe,
    )
