"""Codespace-local attended DevBox runtime.

This module owns provider-local process execution receipts only. It does not
create Executive lifecycle state, choose a target, mint caller authority, write
GitHub, or retry an effect-unknown operation on another backend.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from .contracts import validate_tool_arguments

_REF_RE = re.compile(r"^(target|generation|owner):[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_RECORD_SCHEMA = "mastermind.devbox_process_receipt.v1"
_DEFAULT_TIMEOUT_SECONDS = 300
_DEFAULT_OUTPUT_LIMIT_BYTES = 65536
_START_WAIT_SECONDS = 2.5
_CANCEL_GRACE_SECONDS = 2.0
_SAFE_ENV_NAMES = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "COLORTERM",
)
_FORBIDDEN_ENV_TOKENS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "APIKEY",
    "CREDENTIAL",
    "AUTH",
)


class DevBoxRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


@dataclasses.dataclass(frozen=True)
class CodespaceBinding:
    """Owner-issued immutable target projection; caller/model never authors it."""

    target_ref: str
    generation: str
    owner_ref: str
    repository: str
    committed_head: str

    def __post_init__(self) -> None:
        if any(
            type(value) is not str or _REF_RE.fullmatch(value) is None
            for value in (self.target_ref, self.generation, self.owner_ref)
        ):
            raise ValueError("binding references must be exact opaque references")
        if (
            type(self.repository) is not str
            or not self.repository
            or len(self.repository) > 256
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in self.repository)
        ):
            raise ValueError("repository identity is invalid")
        if type(self.committed_head) is not str or _HEX40.fullmatch(self.committed_head) is None:
            raise ValueError("committed head is invalid")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    data = _canonical_bytes(dict(value)) + b"\n"
    directory = path.parent
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(directory))
    temp = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        dir_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            temp.unlink()
        except OSError:
            pass
        raise


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "process receipt is unavailable") from exc
    if type(value) is not dict or value.get("schema") != _RECORD_SCHEMA:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "process receipt is malformed")
    return value


def _git(repo: Path, *args: str) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DevBoxRuntimeError("BINDING_UNAVAILABLE", "Git observation is unavailable") from exc
    if completed.returncode != 0:
        raise DevBoxRuntimeError("BINDING_UNAVAILABLE", "Git observation is unavailable")
    return completed.stdout.rstrip("\n")


def _lstat_real_directory(path: Path) -> os.stat_result:
    try:
        lexical = path.lstat()
        resolved = path.resolve(strict=True)
        observed = resolved.stat()
    except OSError as exc:
        raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "runtime directory is unavailable") from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(observed.st_mode) or resolved != path.absolute():
        raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "runtime directory must be an exact real directory")
    return observed


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _process_start_identity(pid: int) -> tuple[str, str | None]:
    """Return a stable-enough local identity; production Linux uses procfs starttime."""

    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        raw = proc_stat.read_text(encoding="utf-8")
        # comm may contain spaces and parentheses; field 22 is 20 fields after the closing paren.
        close = raw.rfind(")")
        rest = raw[close + 2 :].split()
        if close > 0 and len(rest) >= 20:
            return f"procfs:{rest[19]}", _boot_id()
    except (OSError, UnicodeError, ValueError):
        pass
    try:
        completed = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
        value = completed.stdout.strip()
        if completed.returncode == 0 and value:
            return f"ps:{value}", None
    except (OSError, subprocess.SubprocessError):
        pass
    raise DevBoxRuntimeError("PROCESS_IDENTITY_UNKNOWN", "process identity is unavailable")


def _boot_id() -> str | None:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _safe_child_env(state_home: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for name in _SAFE_ENV_NAMES:
        value = os.environ.get(name)
        if value and not any(token in name.upper() for token in _FORBIDDEN_ENV_TOKENS):
            env[name] = value
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    env["HOME"] = str(state_home)
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    # Empty helper resets helper lists, including a repository-local helper.
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "credential.helper"
    env["GIT_CONFIG_VALUE_0"] = ""
    return env


def _record_projection(record: Mapping[str, Any], *, reconciled: bool) -> dict[str, Any]:
    return {
        "process_ref": record["process_ref"],
        "effect_state": record["effect_state"],
        "terminal": bool(record.get("terminal", False)),
        "reconciled": reconciled,
    }


class CodespaceDevBoxRuntime:
    def __init__(
        self,
        *,
        repo_root: Path,
        state_root: Path,
        binding: CodespaceBinding,
        shell_path: Path,
        root_identity: tuple[int, int, int],
    ) -> None:
        self.repo_root = repo_root
        self.state_root = state_root
        self.binding = binding
        self.shell_path = shell_path
        self._root_identity = root_identity
        self._operations = state_root / "operations"

    @classmethod
    def open(
        cls,
        *,
        repo_root: Path | str,
        state_root: Path | str,
        binding: CodespaceBinding,
        platform_name: str | None = None,
        shell_path: Path | str = Path("/bin/bash"),
    ) -> "CodespaceDevBoxRuntime":
        selected_platform = sys.platform if platform_name is None else platform_name
        if selected_platform != "linux" or type(binding) is not CodespaceBinding:
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "Codespace V1 requires qualified Linux")
        repo = Path(repo_root).absolute()
        state = Path(state_root).absolute()
        if repo.is_symlink() or state.is_symlink():
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "runtime roots must not be symlinks")
        repo_stat = _lstat_real_directory(repo)
        try:
            repo_real = repo.resolve(strict=True)
        except OSError as exc:
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "repository root is unavailable") from exc
        if state.exists():
            state_stat = _lstat_real_directory(state)
        else:
            try:
                state.mkdir(parents=True, mode=0o700)
                state.chmod(0o700)
            except OSError as exc:
                raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "state root could not be created") from exc
            state_stat = _lstat_real_directory(state)
        state_real = state.resolve(strict=True)
        if _is_relative_to(state_real, repo_real) or _is_relative_to(repo_real, state_real):
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "state and repository roots must be disjoint")
        if state_stat.st_uid != os.geteuid() or stat.S_IMODE(state_stat.st_mode) != 0o700:
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "state root must be owner-private mode 0700")
        shell = Path(shell_path)
        try:
            shell_info = shell.lstat()
        except OSError as exc:
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "qualified shell is unavailable") from exc
        if (
            not shell.is_absolute()
            or stat.S_ISLNK(shell_info.st_mode)
            or not stat.S_ISREG(shell_info.st_mode)
            or not os.access(shell, os.X_OK)
        ):
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "qualified shell is invalid")
        observed_head = _git(repo_real, "rev-parse", "HEAD")
        if observed_head != binding.committed_head:
            raise DevBoxRuntimeError("BINDING_CHANGED", "repository source head differs from binding")
        operations = state_real / "operations"
        operations.mkdir(mode=0o700, exist_ok=True)
        operations.chmod(0o700)
        home = state_real / "home"
        home.mkdir(mode=0o700, exist_ok=True)
        home.chmod(0o700)
        return cls(
            repo_root=repo_real,
            state_root=state_real,
            binding=binding,
            shell_path=shell,
            root_identity=(int(repo_stat.st_dev), int(repo_stat.st_ino), int(repo_stat.st_uid)),
        )

    def _revalidate_binding(self) -> None:
        try:
            current = self.repo_root.lstat()
        except OSError as exc:
            raise DevBoxRuntimeError("BINDING_CHANGED", "repository root is unavailable") from exc
        identity = (int(current.st_dev), int(current.st_ino), int(current.st_uid))
        if not stat.S_ISDIR(current.st_mode) or identity != self._root_identity:
            raise DevBoxRuntimeError("BINDING_CHANGED", "repository root identity changed")
        observed_head = _git(self.repo_root, "rev-parse", "HEAD")
        if observed_head != self.binding.committed_head:
            raise DevBoxRuntimeError("BINDING_CHANGED", "repository source head changed")

    def _op_digest(self, operation_key: str) -> str:
        return hashlib.sha256(
            (self.binding.target_ref + "\0" + self.binding.generation + "\0" + operation_key).encode("utf-8")
        ).hexdigest()

    def _op_dir_from_ref(self, process_ref: str) -> Path:
        digest = process_ref.removeprefix("process:") if hasattr(str, "removeprefix") else process_ref[8:]
        if process_ref != "process:" + digest or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise DevBoxRuntimeError("PROCESS_NOT_FOUND", "process reference is invalid")
        path = self._operations / digest
        if not path.is_dir():
            raise DevBoxRuntimeError("PROCESS_NOT_FOUND", "process reference is not owned here")
        return path

    async def status(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        validate_tool_arguments("devbox_status", dict(arguments))
        self._revalidate_binding()
        observed_head = _git(self.repo_root, "rev-parse", "HEAD")
        dirty = bool(_git(self.repo_root, "status", "--porcelain=v1", "--untracked-files=all"))
        return {
            "target_ref": self.binding.target_ref,
            "generation": self.binding.generation,
            "owner_ref": self.binding.owner_ref,
            "repository": self.binding.repository,
            "committed_head": self.binding.committed_head,
            "observed_head": observed_head,
            "working_tree_dirty": dirty,
            "execution_profile": "ATTENDED_ONLY",
            "provider": "github_codespaces",
        }

    async def start_command(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        request = validate_tool_arguments("start_devbox_command", dict(arguments))
        self._revalidate_binding()
        timeout_seconds = int(request.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS))
        output_limit = int(request.get("output_limit_bytes", _DEFAULT_OUTPUT_LIMIT_BYTES))
        operation_key = str(request["operation_key"])
        digest = self._op_digest(operation_key)
        process_ref = "process:" + digest
        op_dir = self._operations / digest
        request_digest = _sha256(
            {
                "operation_key": operation_key,
                "command_text": request["command_text"],
                "timeout_seconds": timeout_seconds,
                "output_limit_bytes": output_limit,
                "target_ref": self.binding.target_ref,
                "generation": self.binding.generation,
                "committed_head": self.binding.committed_head,
            }
        )
        try:
            op_dir.mkdir(mode=0o700)
            op_dir.chmod(0o700)
            created = True
        except FileExistsError:
            created = False
        if not created:
            record = _load_json(op_dir / "record.json")
            if record.get("request_digest") != request_digest:
                raise DevBoxRuntimeError("OPERATION_CONFLICT", "operation key has a different payload")
            return _record_projection(record, reconciled=True)

        record = {
            "schema": _RECORD_SCHEMA,
            "process_ref": process_ref,
            "request_digest": request_digest,
            "target_ref": self.binding.target_ref,
            "generation": self.binding.generation,
            "owner_ref": self.binding.owner_ref,
            "repository": self.binding.repository,
            "committed_head": self.binding.committed_head,
            "phase": "PREPARED",
            "effect_state": "EFFECT_UNKNOWN",
            "terminal": False,
            "timed_out": False,
            "cancel_requested": False,
            "child_pid": None,
            "child_pgid": None,
            "process_start_identity": None,
            "boot_id": None,
            "exit_code": None,
            "stdout": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
            "stderr": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
        }
        _atomic_json(op_dir / "record.json", record)
        supervisor_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        }
        argv = [
            sys.executable,
            "-m",
            "integrations.devbox_mcp.codespace_runtime",
            "--supervise",
            str(op_dir),
            "--repo-root",
            str(self.repo_root),
            "--state-home",
            str(self.state_root / "home"),
            "--shell",
            str(self.shell_path),
            "--timeout-seconds",
            str(timeout_seconds),
            "--output-limit-bytes",
            str(output_limit),
        ]
        supervisor: subprocess.Popen[bytes] | None = None
        try:
            supervisor = subprocess.Popen(
                argv,
                cwd=str(self.repo_root),
                env=supervisor_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            payload = _canonical_bytes({"command_text": request["command_text"]}) + b"\n"
            if supervisor.stdin is None:
                raise OSError("supervisor stdin unavailable")
            supervisor.stdin.write(payload)
            supervisor.stdin.flush()
            supervisor.stdin.close()
        except BaseException as exc:
            if supervisor is None:
                failed = dict(record)
                failed.update(
                    phase="REFUSED",
                    effect_state="NOT_APPLIED",
                    terminal=True,
                )
                _atomic_json(op_dir / "record.json", failed)
                raise DevBoxRuntimeError("START_REFUSED", "supervisor could not start") from exc
            # A process exists and command delivery may or may not have completed.
            # Never spawn process two; replay must reconcile this same receipt.
            raise DevBoxRuntimeError("EFFECT_UNKNOWN", "command delivery outcome is unknown") from exc

        deadline = time.monotonic() + _START_WAIT_SECONDS
        latest = record
        while time.monotonic() < deadline:
            await asyncio.sleep(0.02)
            latest = _load_json(op_dir / "record.json")
            if latest.get("phase") != "PREPARED":
                break
        return _record_projection(latest, reconciled=False)

    async def read_process(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        request = validate_tool_arguments("read_devbox_process", dict(arguments))
        process_ref = str(request["process_ref"])
        op_dir = self._op_dir_from_ref(process_ref)
        record = _load_json(op_dir / "record.json")
        if record.get("process_ref") != process_ref:
            raise DevBoxRuntimeError("PROCESS_NOT_FOUND", "process receipt does not match reference")
        maximum = int(request.get("max_bytes", _DEFAULT_OUTPUT_LIMIT_BYTES))
        stdout = _read_stream(
            op_dir / "stdout.bin",
            cursor=int(request.get("stdout_cursor", 0)),
            maximum=maximum,
            metadata=record.get("stdout", {}),
        )
        stderr = _read_stream(
            op_dir / "stderr.bin",
            cursor=int(request.get("stderr_cursor", 0)),
            maximum=maximum,
            metadata=record.get("stderr", {}),
        )
        return {
            "process_ref": process_ref,
            "effect_state": record.get("effect_state", "EFFECT_UNKNOWN"),
            "terminal": bool(record.get("terminal", False)),
            "exit_code": record.get("exit_code"),
            "timed_out": bool(record.get("timed_out", False)),
            "cancel_requested": bool(record.get("cancel_requested", False)),
            "stdout": stdout,
            "stderr": stderr,
        }

    async def cancel_process(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        request = validate_tool_arguments("cancel_devbox_process", dict(arguments))
        process_ref = str(request["process_ref"])
        op_dir = self._op_dir_from_ref(process_ref)
        record = _load_json(op_dir / "record.json")
        if record.get("process_ref") != process_ref:
            raise DevBoxRuntimeError("PROCESS_NOT_FOUND", "process receipt does not match reference")
        if record.get("terminal") is True:
            return {
                "process_ref": process_ref,
                "cancel_requested": bool(record.get("cancel_requested", False)),
                "terminal": True,
            }
        if record.get("phase") != "STARTED":
            raise DevBoxRuntimeError("EFFECT_UNKNOWN", "process start has not been reconciled")
        pid = record.get("child_pid")
        pgid = record.get("child_pgid")
        start_identity = record.get("process_start_identity")
        boot_id = record.get("boot_id")
        if type(pid) is not int or pid <= 1 or type(pgid) is not int or pgid <= 1 or type(start_identity) is not str:
            raise DevBoxRuntimeError("PROCESS_IDENTITY_UNKNOWN", "owned process identity is incomplete")
        try:
            observed_pgid = os.getpgid(pid)
            current_start, current_boot = _process_start_identity(pid)
        except (OSError, DevBoxRuntimeError) as exc:
            latest = _load_json(op_dir / "record.json")
            if latest.get("terminal") is True:
                return {
                    "process_ref": process_ref,
                    "cancel_requested": bool(latest.get("cancel_requested", False)),
                    "terminal": True,
                }
            raise DevBoxRuntimeError("PROCESS_IDENTITY_UNKNOWN", "owned process cannot be re-attested") from exc
        if observed_pgid != pgid or current_start != start_identity or current_boot != boot_id:
            raise DevBoxRuntimeError("PROCESS_IDENTITY_UNKNOWN", "owned process identity changed")
        cancel_receipt = {
            "process_ref": process_ref,
            "reason_digest": _sha256(str(request.get("reason", "attended cancel"))),
            "requested_at_ns": time.time_ns(),
        }
        _atomic_json(op_dir / "cancel.json", cancel_receipt)
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            latest = _load_json(op_dir / "record.json")
            if latest.get("terminal") is not True:
                raise DevBoxRuntimeError("PROCESS_IDENTITY_UNKNOWN", "process disappeared before cancellation proof")
        except OSError as exc:
            raise DevBoxRuntimeError("CANCEL_UNCERTAIN", "process signal outcome is uncertain") from exc
        return {"process_ref": process_ref, "cancel_requested": True, "terminal": False}


def _read_stream(path: Path, *, cursor: int, maximum: int, metadata: object) -> dict[str, Any]:
    if type(metadata) is not dict:
        metadata = {}
    try:
        retained = path.stat().st_size if path.exists() else 0
    except OSError as exc:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "stream observation is unavailable") from exc
    selected = min(maximum, max(0, retained - cursor)) if cursor <= retained else 0
    data = b""
    if selected:
        try:
            with path.open("rb") as handle:
                handle.seek(cursor)
                data = handle.read(selected)
        except OSError as exc:
            raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "stream observation is unavailable") from exc
    end = cursor + len(data)
    total_bytes = int(metadata.get("total_bytes", retained)) if type(metadata.get("total_bytes", retained)) is int else retained
    retained_bytes = int(metadata.get("retained_bytes", retained)) if type(metadata.get("retained_bytes", retained)) is int else retained
    dropped_bytes = int(metadata.get("dropped_bytes", max(0, total_bytes - retained_bytes))) if type(metadata.get("dropped_bytes", 0)) is int else max(0, total_bytes - retained_bytes)
    return {
        "text": data.decode("utf-8", errors="replace"),
        "start_cursor": cursor,
        "next_cursor": end,
        "total_bytes": total_bytes,
        "retained_bytes": retained_bytes,
        "dropped_bytes": dropped_bytes,
        "truncated": dropped_bytes > 0,
        "gap_ranges": [[retained_bytes, total_bytes]] if dropped_bytes > 0 else [],
    }


def _pump(stream: Any, output: Path, limit: int, result: dict[str, int], key: str) -> None:
    total = 0
    retained = 0
    with output.open("wb") as handle:
        os.chmod(output, 0o600)
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            total += len(chunk)
            if retained < limit:
                keep = chunk[: max(0, limit - retained)]
                if keep:
                    handle.write(keep)
                    retained += len(keep)
        handle.flush()
        os.fsync(handle.fileno())
    result[key] = total
    result[key + "_retained"] = retained


def _supervise(
    op_dir: Path,
    *,
    repo_root: Path,
    state_home: Path,
    shell: Path,
    timeout_seconds: int,
    output_limit_bytes: int,
) -> int:
    record_path = op_dir / "record.json"
    try:
        record = _load_json(record_path)
    except DevBoxRuntimeError:
        return 70
    try:
        raw = sys.stdin.buffer.readline(65537)
        if not raw or len(raw) > 65536:
            raise ValueError("command frame unavailable")
        message = json.loads(raw.decode("utf-8"))
        if type(message) is not dict or set(message) != {"command_text"}:
            raise ValueError("command frame malformed")
        command = message["command_text"]
        if type(command) is not str or not command or "\x00" in command or len(command) > 16384:
            raise ValueError("command frame malformed")
    except Exception:
        refused = dict(record)
        refused.update(phase="REFUSED", effect_state="NOT_APPLIED", terminal=True)
        _atomic_json(record_path, refused)
        return 64

    env = _safe_child_env(state_home)
    try:
        child = subprocess.Popen(
            [str(shell), "--noprofile", "--norc", "-c", command],
            cwd=str(repo_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        pgid = os.getpgid(child.pid)
        start_identity, boot_id = _process_start_identity(child.pid)
    except BaseException:
        refused = dict(record)
        refused.update(phase="REFUSED", effect_state="NOT_APPLIED", terminal=True)
        _atomic_json(record_path, refused)
        return 71

    started = dict(record)
    started.update(
        phase="STARTED",
        effect_state="APPLIED",
        terminal=False,
        child_pid=child.pid,
        child_pgid=pgid,
        process_start_identity=start_identity,
        boot_id=boot_id,
        started_at_ns=time.time_ns(),
    )
    _atomic_json(record_path, started)

    totals: dict[str, int] = {}
    stdout_thread = threading.Thread(
        target=_pump,
        args=(child.stdout, op_dir / "stdout.bin", output_limit_bytes, totals, "stdout"),
        daemon=False,
    )
    stderr_thread = threading.Thread(
        target=_pump,
        args=(child.stderr, op_dir / "stderr.bin", output_limit_bytes, totals, "stderr"),
        daemon=False,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        child.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=_CANCEL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        # The child is terminal but retained output accounting is incomplete.
        final = _load_json(record_path)
        final.update(
            phase="TERMINAL_OUTPUT_UNCERTAIN",
            effect_state="EFFECT_UNKNOWN",
            terminal=True,
            exit_code=child.returncode,
            timed_out=timed_out,
        )
        _atomic_json(record_path, final)
        return 74

    cancel_requested = (op_dir / "cancel.json").is_file()
    final = _load_json(record_path)
    final.update(
        phase="TERMINAL",
        effect_state="APPLIED",
        terminal=True,
        exit_code=child.returncode,
        timed_out=timed_out,
        cancel_requested=cancel_requested,
        ended_at_ns=time.time_ns(),
        stdout={
            "total_bytes": totals.get("stdout", 0),
            "retained_bytes": totals.get("stdout_retained", 0),
            "dropped_bytes": max(0, totals.get("stdout", 0) - totals.get("stdout_retained", 0)),
        },
        stderr={
            "total_bytes": totals.get("stderr", 0),
            "retained_bytes": totals.get("stderr_retained", 0),
            "dropped_bytes": max(0, totals.get("stderr", 0) - totals.get("stderr_retained", 0)),
        },
    )
    _atomic_json(record_path, final)
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--supervise")
    parser.add_argument("--repo-root")
    parser.add_argument("--state-home")
    parser.add_argument("--shell")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--output-limit-bytes", type=int)
    return parser.parse_args(argv)


def _main(argv: list[str]) -> int:
    args = _parse_args(argv)
    if not args.supervise:
        return 64
    return _supervise(
        Path(args.supervise),
        repo_root=Path(args.repo_root),
        state_home=Path(args.state_home),
        shell=Path(args.shell),
        timeout_seconds=int(args.timeout_seconds),
        output_limit_bytes=int(args.output_limit_bytes),
    )


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))


__all__ = ["CodespaceBinding", "CodespaceDevBoxRuntime", "DevBoxRuntimeError"]
