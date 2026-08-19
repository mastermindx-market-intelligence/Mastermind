"""Zero-Executive-write Codex provider-readiness canary.

Login status is not readiness. This probe runs one inert ``codex exec`` turn
as the dedicated worker principal against the pinned production binary and
``CODEX_HOME``. It never starts Executive services, never opens the control
SQLite, and never writes into production workspaces or runs.

Pinned Codex 0.147.0 exposes no login/exec workspace-selection flag. The
config key ``forced_chatgpt_workspace_id`` exists but is not applied here:
the intended workspace id is an operator binding, not a silent default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = "mastermind.executive_provider_inference_canary/v1"
PINNED_CODEX_VERSION = "0.147.0"
PINNED_CODEX_TEAM_ID = "2DC432GLL2"
PINNED_CODEX_SHA256 = "19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"
INSTALLED_CODEX_BINARY = (
    "/Library/Application Support/MastermindExecutive/bin/codex-0.147.0"
)
WORKER_USER = "_mastermind_worker"
WORKER_GROUP = "_mastermind_worker"
WORKER_UID = 451
WORKER_GID = 451
PROVIDER_HOME = "/var/db/mastermind-executive/workers/codex-01/provider-home"
PRODUCTION_MODEL = "gpt-5.6-sol"
PRODUCTION_REASONING_EFFORT = "xhigh"
PYTHON_BINARY = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
EXECUTIVE_DATABASE = (
    "/var/db/mastermind-executive/control/db/data/control_plane/executive.sqlite3"
)
PRODUCTION_WORKSPACES = "/var/db/mastermind-executive/jobs/workspaces"
PRODUCTION_RUNS = "/var/db/mastermind-executive/jobs/runs"
CONTROL_ROOT = "/var/db/mastermind-executive/control"
CANARY_ID_RE = re.compile(r"^canary-[0-9a-f]{12}$")
_INVALID_WORKSPACE_MARKER = "invalid_workspace_selected"
_JSONL_TERMINAL_EVENTS = frozenset({"turn.completed", "turn.failed", "error"})
_DISABLED_FEATURES = (
    "hooks",
    "apps",
    "plugins",
    "plugin_sharing",
    "browser_use",
    "computer_use",
    "image_generation",
    "memories",
    "multi_agent",
    "remote_plugin",
)
INERT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean", "const": True}},
}
INERT_PROMPT = (
    "This is an Executive OS provider-readiness canary. Do not use tools. "
    'Return only the JSON object {"ok": true}.'
)
EVENT_CLASSES = frozenset(
    {
        "turn_completed",
        "invalid_workspace_selected",
        "malformed_provider_response",
        "timeout",
        "process_failed",
        "result_invalid",
        "isolation_violation",
        "configuration_invalid",
    }
)


class ProviderCanaryError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProviderCanaryConfig:
    canary_id: str
    worker_user: str
    worker_uid: int
    worker_gid: int
    provider_home: Path
    installed_codex_binary: Path
    expected_codex_version: str
    expected_codex_sha256: str
    expected_codex_team: str
    model: str
    reasoning_effort: str
    probe_root: Path
    executive_database: Path
    production_workspaces: Path
    production_runs: Path
    control_root: Path
    operator_home: Path
    timeout_seconds: float = 180.0


@dataclass(frozen=True)
class CodexInvocation:
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    stdin: bytes
    workspace: Path
    schema_path: Path
    result_path: Path
    home: Path
    tmp: Path


@dataclass(frozen=True)
class CodexRunResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


CodexRunner = Callable[[CodexInvocation], CodexRunResult]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_canary_id() -> str:
    value = f"canary-{secrets.token_hex(6)}"
    if CANARY_ID_RE.fullmatch(value) is None:
        raise ProviderCanaryError("configuration_invalid")
    return value


def production_config(*, probe_root: Path, operator_home: Path) -> ProviderCanaryConfig:
    return ProviderCanaryConfig(
        canary_id=new_canary_id(),
        worker_user=WORKER_USER,
        worker_uid=WORKER_UID,
        worker_gid=WORKER_GID,
        provider_home=Path(PROVIDER_HOME),
        installed_codex_binary=Path(INSTALLED_CODEX_BINARY),
        expected_codex_version=PINNED_CODEX_VERSION,
        expected_codex_sha256=PINNED_CODEX_SHA256,
        expected_codex_team=PINNED_CODEX_TEAM_ID,
        model=PRODUCTION_MODEL,
        reasoning_effort=PRODUCTION_REASONING_EFFORT,
        probe_root=probe_root,
        executive_database=Path(EXECUTIVE_DATABASE),
        production_workspaces=Path(PRODUCTION_WORKSPACES),
        production_runs=Path(PRODUCTION_RUNS),
        control_root=Path(CONTROL_ROOT),
        operator_home=operator_home,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def forbidden_write_roots(config: ProviderCanaryConfig) -> tuple[Path, ...]:
    return (
        config.executive_database.parent if config.executive_database.name else config.executive_database,
        config.production_workspaces,
        config.production_runs,
        config.control_root,
        config.operator_home,
        config.provider_home,
    )


def build_exec_argv(
    config: ProviderCanaryConfig,
    *,
    workspace: Path,
    schema_path: Path,
    result_path: Path,
    home: Path,
    tmp: Path,
) -> list[str]:
    profile = "mastermind_provider_canary"
    filesystem = {
        json.dumps(str(workspace)): json.dumps("write"),
        json.dumps(str(home)): json.dumps("write"),
        json.dumps(str(tmp)): json.dumps("write"),
    }
    for denied in forbidden_write_roots(config):
        filesystem[json.dumps(str(denied))] = json.dumps("deny")
    rendered = ",".join(f"{key}={value}" for key, value in filesystem.items())
    shell_set = {
        "HOME": str(home),
        "USER": config.worker_user,
        "LOGNAME": config.worker_user,
        "SHELL": "/usr/bin/false",
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "TMPDIR": str(tmp) + "/",
        "NO_COLOR": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    shell_values = ",".join(
        f"{key}={json.dumps(value)}" for key, value in shell_set.items()
    )
    shell_allowlist = ",".join(json.dumps(key) for key in shell_set)
    shell_policy = (
        '{inherit="none",ignore_default_excludes=false,'
        f"include_only=[{shell_allowlist}],set={{{shell_values}}}}}"
    )
    argv = [
        str(config.installed_codex_binary),
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--skip-git-repo-check",
        "--model",
        config.model,
        "--color",
        "never",
        "-C",
        str(workspace),
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(result_path),
        "-c",
        f"model_reasoning_effort={json.dumps(config.reasoning_effort)}",
        "-c",
        'approval_policy="never"',
        "-c",
        "agents.enabled=false",
        "-c",
        'web_search="disabled"',
        "-c",
        'cli_auth_credentials_store="file"',
        "-c",
        (
            "projects={"
            f"{json.dumps(str(workspace))}={{trust_level=\"untrusted\"}}"
            "}"
        ),
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        "project_doc_fallback_filenames=[]",
        "-c",
        "mcp_servers={}",
        "-c",
        f"shell_environment_policy={shell_policy}",
        "-c",
        f"default_permissions={json.dumps(profile)}",
        "-c",
        f"permissions.{profile}.description={json.dumps('Provider readiness canary')}",
        "-c",
        f"permissions.{profile}.extends={json.dumps(':read-only')}",
        "-c",
        f"permissions.{profile}.filesystem={{{rendered}}}",
        "-c",
        f"permissions.{profile}.network.enabled=false",
    ]
    for feature in _DISABLED_FEATURES:
        argv.extend(["--disable", feature])
    argv.append("-")
    return argv


def build_worker_env(config: ProviderCanaryConfig, *, home: Path, tmp: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "USER": config.worker_user,
        "LOGNAME": config.worker_user,
        "SHELL": "/usr/bin/false",
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "TMPDIR": str(tmp) + "/",
        "CODEX_HOME": str(config.provider_home),
        "NO_COLOR": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _strip_json_deny_paths(argv: Sequence[str], denied: Sequence[Path]) -> str:
    text = "\x00".join(argv)
    for path in denied:
        text = text.replace(json.dumps(str(path)), "")
    return text


def assert_invocation_isolation(
    config: ProviderCanaryConfig, invocation: CodexInvocation
) -> None:
    denied = forbidden_write_roots(config)
    remainder = _strip_json_deny_paths(invocation.argv, denied)
    for path in (*denied, config.executive_database):
        token = str(path)
        if token and token in remainder:
            raise ProviderCanaryError("isolation_violation")
    for key, value in invocation.env.items():
        for path in (*denied, config.executive_database, config.operator_home):
            token = str(path)
            if not token or token not in value:
                continue
            allowed_codex_home = (
                key == "CODEX_HOME" and value == str(config.provider_home)
            )
            if not allowed_codex_home:
                raise ProviderCanaryError("isolation_violation")
    if not _is_relative_to(invocation.cwd, config.probe_root):
        raise ProviderCanaryError("isolation_violation")
    if not _is_relative_to(invocation.workspace, config.probe_root):
        raise ProviderCanaryError("isolation_violation")
    if not _is_relative_to(invocation.home, config.probe_root):
        raise ProviderCanaryError("isolation_violation")
    if invocation.env.get("CODEX_HOME") != str(config.provider_home):
        raise ProviderCanaryError("isolation_violation")
    if invocation.env.get("HOME") != str(invocation.home):
        raise ProviderCanaryError("isolation_violation")
    for key in ("OPENAI_API_KEY", "CODEX_ACCESS_TOKEN", "CODEX_API_KEY"):
        if key in invocation.env:
            raise ProviderCanaryError("isolation_violation")
    if "--with-api-key" in invocation.argv or "--with-access-token" in invocation.argv:
        raise ProviderCanaryError("isolation_violation")
    if any(item in {"remote", "login", "logout"} for item in invocation.argv):
        raise ProviderCanaryError("isolation_violation")
    if "forced_chatgpt_workspace_id" in remainder:
        raise ProviderCanaryError("isolation_violation")


def classify_provider_streams(
    *,
    stdout: bytes,
    stderr: bytes,
    result: bytes | None,
    exit_code: int,
    timed_out: bool,
) -> dict[str, Any]:
    combined = stdout + b"\n" + stderr
    if timed_out:
        return {
            "passed": False,
            "terminal_event_class": "timeout",
            "result_valid": False,
        }
    if _INVALID_WORKSPACE_MARKER.encode("ascii") in combined:
        return {
            "passed": False,
            "terminal_event_class": "invalid_workspace_selected",
            "result_valid": False,
        }
    events: list[str] = []
    malformed = False
    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed = True
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            malformed = True
            continue
        events.append(str(payload["type"]))
    result_valid = False
    if result:
        try:
            parsed = json.loads(result.decode("utf-8"))
            result_valid = parsed == {"ok": True}
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed = True
    if malformed and "turn.completed" not in events:
        return {
            "passed": False,
            "terminal_event_class": "malformed_provider_response",
            "result_valid": False,
        }
    if exit_code != 0:
        return {
            "passed": False,
            "terminal_event_class": "process_failed",
            "result_valid": False,
        }
    if "turn.completed" not in events:
        if any(event in _JSONL_TERMINAL_EVENTS for event in events):
            return {
                "passed": False,
                "terminal_event_class": "process_failed",
                "result_valid": False,
            }
        return {
            "passed": False,
            "terminal_event_class": "malformed_provider_response",
            "result_valid": False,
        }
    if not result_valid:
        return {
            "passed": False,
            "terminal_event_class": "result_invalid",
            "result_valid": False,
        }
    return {
        "passed": True,
        "terminal_event_class": "turn_completed",
        "result_valid": True,
    }


def evaluate_provider_preflight(
    *, login_status_ok: bool, canary: Mapping[str, Any]
) -> dict[str, Any]:
    canary_passed = canary.get("passed") is True
    event_class = canary.get("terminal_event_class")
    if event_class not in EVENT_CLASSES and event_class is not None:
        canary_passed = False
        event_class = "malformed_provider_response"
    passed = bool(login_status_ok) and canary_passed
    refusal: str | None = None
    if not login_status_ok:
        refusal = "login_status_failed"
    elif not canary_passed:
        refusal = str(event_class or "provider_canary_failed")
    return {
        "passed": passed,
        "login_status_ok": bool(login_status_ok),
        "canary_passed": canary_passed,
        "refusal": refusal,
    }


def _receipt(
    config: ProviderCanaryConfig,
    *,
    classification: Mapping[str, Any],
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
    binary_sha256: str,
    observed_version: str,
    workspace_capability: str,
) -> dict[str, Any]:
    readiness = evaluate_provider_preflight(
        login_status_ok=True, canary=classification
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "canary_id": config.canary_id,
        "observed_at": now_iso(),
        "codex_version": observed_version,
        "codex_sha256": binary_sha256,
        "model": config.model,
        "exit_code": int(exit_code),
        "timed_out": classification.get("terminal_event_class") == "timeout",
        "terminal_event_class": classification["terminal_event_class"],
        "result_valid": bool(classification["result_valid"]),
        "stdout_sha256": _sha256_bytes(stdout),
        "stderr_sha256": _sha256_bytes(stderr),
        "workspace_capability_outcome": workspace_capability,
        "workspace_selection_mechanism": "none",
        "forced_chatgpt_workspace_id_applied": False,
        "passed": bool(readiness["passed"]),
        "refusal": readiness["refusal"],
    }


def prepare_probe(config: ProviderCanaryConfig) -> CodexInvocation:
    if CANARY_ID_RE.fullmatch(config.canary_id) is None:
        raise ProviderCanaryError("configuration_invalid")
    probe = config.probe_root / config.canary_id
    if probe.exists():
        raise ProviderCanaryError("configuration_invalid")
    workspace = probe / "workspace"
    home = probe / "home"
    tmp = probe / "tmp"
    workspace.mkdir(parents=True, mode=0o700)
    home.mkdir(mode=0o700)
    tmp.mkdir(mode=0o700)
    schema_path = probe / "schema.json"
    result_path = probe / "result.json"
    schema_path.write_text(
        json.dumps(INERT_SCHEMA, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(schema_path, 0o600)
    argv = build_exec_argv(
        config,
        workspace=workspace,
        schema_path=schema_path,
        result_path=result_path,
        home=home,
        tmp=tmp,
    )
    env = build_worker_env(config, home=home, tmp=tmp)
    invocation = CodexInvocation(
        argv=tuple(argv),
        env=env,
        cwd=workspace,
        stdin=INERT_PROMPT.encode("utf-8"),
        workspace=workspace,
        schema_path=schema_path,
        result_path=result_path,
        home=home,
        tmp=tmp,
    )
    assert_invocation_isolation(config, invocation)
    return invocation


def _scrub_probe_secrets(invocation: CodexInvocation) -> None:
    for path in (invocation.result_path, invocation.schema_path):
        if path.exists():
            path.unlink()
    for directory in (invocation.workspace, invocation.home, invocation.tmp):
        if directory.exists():
            shutil.rmtree(directory)


def run_canary(
    config: ProviderCanaryConfig,
    *,
    runner: CodexRunner,
    binary_sha256: str,
    observed_version: str,
) -> dict[str, Any]:
    invocation = prepare_probe(config)
    try:
        result = runner(invocation)
        result_bytes = None
        if invocation.result_path.exists() and invocation.result_path.is_file():
            result_bytes = invocation.result_path.read_bytes()
        classification = classify_provider_streams(
            stdout=result.stdout,
            stderr=result.stderr,
            result=result_bytes,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
        )
        receipt = _receipt(
            config,
            classification=classification,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            binary_sha256=binary_sha256,
            observed_version=observed_version,
            workspace_capability="inert_untrusted_workspace",
        )
        receipt_path = config.probe_root / config.canary_id / "receipt.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        os.chmod(receipt_path, 0o600)
        return receipt
    finally:
        _scrub_probe_secrets(invocation)


def subprocess_runner(invocation: CodexInvocation, *, timeout_seconds: float) -> CodexRunResult:
    try:
        completed = subprocess.run(
            list(invocation.argv),
            cwd=os.fspath(invocation.cwd),
            env=invocation.env,
            input=invocation.stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CodexRunResult(
            exit_code=124,
            stdout=exc.stdout or b"",
            stderr=exc.stderr or b"",
            timed_out=True,
        )
    return CodexRunResult(
        exit_code=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )


def live_worker_runner(
    config: ProviderCanaryConfig, invocation: CodexInvocation
) -> CodexRunResult:
    probe = config.probe_root / config.canary_id
    for path in (probe, invocation.workspace, invocation.home, invocation.tmp, invocation.schema_path):
        os.chown(path, config.worker_uid, config.worker_gid)
    env_args: list[str] = []
    for key, value in invocation.env.items():
        env_args.append(f"{key}={value}")
    argv = [
        "/usr/bin/sudo",
        "-n",
        "-u",
        config.worker_user,
        "-g",
        WORKER_GROUP,
        "/usr/bin/env",
        "-i",
        *env_args,
        *invocation.argv,
    ]
    inner = CodexInvocation(
        argv=tuple(argv),
        env={},
        cwd=invocation.cwd,
        stdin=invocation.stdin,
        workspace=invocation.workspace,
        schema_path=invocation.schema_path,
        result_path=invocation.result_path,
        home=invocation.home,
        tmp=invocation.tmp,
    )
    return subprocess_runner(inner, timeout_seconds=config.timeout_seconds)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executive Codex provider-inference canary")
    parser.add_argument("--probe-root", type=Path, required=True)
    parser.add_argument("--receipt-path", type=Path)
    parser.add_argument("--operator-home", type=Path, default=Path("/var/empty"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if sys.platform != "darwin" or os.geteuid() != 0:
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "passed": False,
            "terminal_event_class": "configuration_invalid",
            "result_valid": False,
            "refusal": "live_canary_requires_darwin_root",
        }
        json.dump(receipt, sys.stdout, sort_keys=True, indent=2)
        sys.stdout.write("\n")
        return 2
    probe_root = Path(args.probe_root)
    if not probe_root.is_absolute() or probe_root.is_symlink() or not probe_root.is_dir():
        raise ProviderCanaryError("configuration_invalid")
    config = production_config(
        probe_root=probe_root, operator_home=Path(args.operator_home)
    )
    binary = config.installed_codex_binary
    info = binary.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ProviderCanaryError("configuration_invalid")
    binary_sha256 = _sha256_file(binary)
    if binary_sha256 != config.expected_codex_sha256:
        raise ProviderCanaryError("configuration_invalid")
    if sys.platform == "darwin":
        verify = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", str(binary)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if verify.returncode != 0:
            raise ProviderCanaryError("configuration_invalid")
        team = subprocess.run(
            ["/usr/bin/codesign", "-dv", "--verbose=4", str(binary)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        ).stderr
        observed_team = ""
        for line in team.splitlines():
            if line.startswith("TeamIdentifier="):
                observed_team = line.split("=", 1)[1]
        if observed_team != PINNED_CODEX_TEAM_ID:
            raise ProviderCanaryError("configuration_invalid")
    version = subprocess.run(
        [str(binary), "--version"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    ).stdout.strip()
    observed_version = ""
    for token in version.split():
        if token == PINNED_CODEX_VERSION or token.startswith(PINNED_CODEX_VERSION):
            observed_version = PINNED_CODEX_VERSION
            break
    if observed_version != PINNED_CODEX_VERSION:
        raise ProviderCanaryError("configuration_invalid")

    def runner(invocation: CodexInvocation) -> CodexRunResult:
        return live_worker_runner(config, invocation)

    receipt = run_canary(
        config,
        runner=runner,
        binary_sha256=binary_sha256,
        observed_version=observed_version,
    )
    if args.receipt_path is not None:
        Path(args.receipt_path).write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        os.chmod(args.receipt_path, 0o600)
    json.dump(receipt, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0 if receipt.get("passed") is True else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProviderCanaryError as exc:
        json.dump(
            {
                "schema_version": SCHEMA_VERSION,
                "passed": False,
                "terminal_event_class": exc.code,
                "result_valid": False,
                "refusal": exc.code,
            },
            sys.stdout,
            sort_keys=True,
            indent=2,
        )
        sys.stdout.write("\n")
        raise SystemExit(2)
