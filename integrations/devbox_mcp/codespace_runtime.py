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
_BASELINE_SCHEMA = "mastermind.devbox_source_baseline.v1"
_PROGRESS_SCHEMA = "mastermind.devbox_stream_progress.v1"
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


def _volatile_json(path: Path, value: Mapping[str, Any]) -> None:
    """Publish a complete live projection without claiming crash durability."""

    data = _canonical_bytes(dict(value)) + b"\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
        os.replace(temp, path)
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


def _load_source_baseline(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "source baseline is unavailable") from exc
    if type(value) is not dict or value.get("schema") != _BASELINE_SCHEMA:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "source baseline is malformed")
    return value


def _load_stream_progress(path: Path) -> dict[str, int] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "stream progress is unavailable") from exc
    expected = {"schema", "total_bytes", "retained_bytes", "dropped_bytes"}
    if type(value) is not dict or set(value) != expected or value.get("schema") != _PROGRESS_SCHEMA:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "stream progress is malformed")
    total = value.get("total_bytes")
    retained = value.get("retained_bytes")
    dropped = value.get("dropped_bytes")
    if (
        type(total) is not int
        or type(retained) is not int
        or type(dropped) is not int
        or retained < 0
        or total < retained
        or dropped != total - retained
    ):
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "stream progress is malformed")
    return {
        "total_bytes": total,
        "retained_bytes": retained,
        "dropped_bytes": dropped,
    }


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


def _working_tree_snapshot(repo: Path) -> bytes:
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
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=str(repo),
            env=env,
            check=False,
            capture_output=True,
            text=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DevBoxRuntimeError("BINDING_UNAVAILABLE", "Git observation is unavailable") from exc
    if completed.returncode != 0:
        raise DevBoxRuntimeError("BINDING_UNAVAILABLE", "Git observation is unavailable")
    return bytes(completed.stdout)


def _working_tree_digest(snapshot: bytes) -> str:
    return hashlib.sha256(snapshot).hexdigest()


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


def _cancel_receipt_exists(op_dir: Path) -> bool:
    path = op_dir / "cancel.json"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DevBoxRuntimeError(
            "RECEIPT_UNAVAILABLE", "cancellation receipt is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise DevBoxRuntimeError(
            "RECEIPT_UNAVAILABLE", "cancellation receipt identity changed"
        )
    return True


_RECORD_IDENTITY_FIELDS = (
    "schema",
    "process_ref",
    "request_digest",
    "target_ref",
    "generation",
    "owner_ref",
    "repository",
    "committed_head",
)


def _is_exact_empty_private_operation_directory(op_dir: Path) -> bool:
    """Recognize only the pre-effect crash shape that an operator may remove."""

    try:
        info = op_dir.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != stat.S_IRWXU
        ):
            return False
        with os.scandir(op_dir) as entries:
            return next(entries, None) is None
    except OSError:
        return False


def _load_reconciled_record(op_dir: Path) -> dict[str, Any]:
    primary: dict[str, Any] | None = None
    primary_error: DevBoxRuntimeError | None = None
    try:
        primary = _load_json(op_dir / "record.json")
    except DevBoxRuntimeError as exc:
        primary_error = exc

    sidecars: list[dict[str, Any]] = []
    for filename, allowed_phases in (
        ("started.json", frozenset({"STARTED"})),
        ("terminal.json", frozenset({"TERMINAL", "TERMINAL_OUTPUT_UNCERTAIN"})),
    ):
        path = op_dir / filename
        if not path.exists():
            continue
        candidate = _load_json(path)
        if candidate.get("phase") not in allowed_phases:
            raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "process receipt phase changed")
        sidecars.append(candidate)

    if not sidecars:
        if primary is None:
            if _is_exact_empty_private_operation_directory(op_dir):
                raise DevBoxRuntimeError(
                    "PRE_EFFECT_RECEIPT_UNAVAILABLE",
                    "empty pre-effect operation receipt requires operator recovery",
                )
            assert primary_error is not None
            raise primary_error
        return primary

    authority = sidecars[0]
    for candidate in sidecars[1:]:
        if any(
            candidate.get(field) != authority.get(field)
            for field in _RECORD_IDENTITY_FIELDS
        ):
            raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "process receipt identity changed")
        authority = candidate
    if primary is not None and any(
        primary.get(field) != authority.get(field) for field in _RECORD_IDENTITY_FIELDS
    ):
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "process receipt identity changed")
    return authority


def _persist_effect_record(op_dir: Path, record: Mapping[str, Any]) -> None:
    phase = record.get("phase")
    if phase == "STARTED":
        sidecar = op_dir / "started.json"
    elif phase in {"TERMINAL", "TERMINAL_OUTPUT_UNCERTAIN"}:
        sidecar = op_dir / "terminal.json"
    else:
        raise ValueError("effect receipt phase is not reconcilable")
    # The immutable phase sidecar is authoritative if replacement of the mutable
    # projection is interrupted after the effect exists.
    _atomic_json(sidecar, record)
    try:
        _atomic_json(op_dir / "record.json", record)
    except OSError:
        pass


class CodespaceDevBoxRuntime:
    def __init__(
        self,
        *,
        repo_root: Path,
        state_root: Path,
        binding: CodespaceBinding,
        shell_path: Path,
        root_identity: tuple[int, int, int],
        baseline_working_tree_digest: str,
        baseline_working_tree_dirty: bool,
    ) -> None:
        self.repo_root = repo_root
        self.state_root = state_root
        self.binding = binding
        self.shell_path = shell_path
        self._root_identity = root_identity
        self._baseline_working_tree_digest = baseline_working_tree_digest
        self._baseline_working_tree_dirty = baseline_working_tree_dirty
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
        require_clean_baseline: bool = True,
    ) -> "CodespaceDevBoxRuntime":
        selected_platform = sys.platform if platform_name is None else platform_name
        if (
            selected_platform != "linux"
            or type(binding) is not CodespaceBinding
            or type(require_clean_baseline) is not bool
        ):
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
                state.mkdir(parents=True, mode=stat.S_IRWXU)
                state.chmod(stat.S_IRWXU)
            except OSError as exc:
                raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "state root could not be created") from exc
            state_stat = _lstat_real_directory(state)
        state_real = state.resolve(strict=True)
        if _is_relative_to(state_real, repo_real) or _is_relative_to(repo_real, state_real):
            raise DevBoxRuntimeError("RUNTIME_UNQUALIFIED", "state and repository roots must be disjoint")
        if state_stat.st_uid != os.geteuid() or stat.S_IMODE(state_stat.st_mode) != stat.S_IRWXU:
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
        root_identity = (int(repo_stat.st_dev), int(repo_stat.st_ino), int(repo_stat.st_uid))
        baseline_path = state_real / "baseline.json"
        operations = state_real / "operations"
        if baseline_path.exists():
            baseline = _load_source_baseline(baseline_path)
            expected_identity = {
                "target_ref": binding.target_ref,
                "generation": binding.generation,
                "owner_ref": binding.owner_ref,
                "repository": binding.repository,
                "committed_head": binding.committed_head,
                "repo_device": root_identity[0],
                "repo_inode": root_identity[1],
                "repo_uid": root_identity[2],
            }
            if any(baseline.get(key) != value for key, value in expected_identity.items()):
                raise DevBoxRuntimeError("BINDING_CHANGED", "source baseline binding changed")
            baseline_digest = baseline.get("working_tree_digest")
            baseline_dirty = baseline.get("working_tree_dirty")
            if (
                type(baseline_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", baseline_digest) is None
                or type(baseline_dirty) is not bool
            ):
                raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "source baseline is malformed")
            if require_clean_baseline and baseline_dirty:
                raise DevBoxRuntimeError("SOURCE_DIRTY", "repository source was dirty at admission")
        else:
            if operations.exists():
                try:
                    has_operation_state = next(operations.iterdir(), None) is not None
                except OSError as exc:
                    raise DevBoxRuntimeError(
                        "RECEIPT_UNAVAILABLE", "operation state is unavailable"
                    ) from exc
                if has_operation_state:
                    raise DevBoxRuntimeError(
                        "RECEIPT_UNAVAILABLE", "source baseline is missing for existing effects"
                    )
            baseline_snapshot = _working_tree_snapshot(repo_real)
            baseline_dirty = bool(baseline_snapshot)
            if require_clean_baseline and baseline_dirty:
                raise DevBoxRuntimeError("SOURCE_DIRTY", "repository source is not clean at admission")
            baseline_digest = _working_tree_digest(baseline_snapshot)
            _atomic_json(
                baseline_path,
                {
                    "schema": _BASELINE_SCHEMA,
                    "target_ref": binding.target_ref,
                    "generation": binding.generation,
                    "owner_ref": binding.owner_ref,
                    "repository": binding.repository,
                    "committed_head": binding.committed_head,
                    "repo_device": root_identity[0],
                    "repo_inode": root_identity[1],
                    "repo_uid": root_identity[2],
                    "working_tree_digest": baseline_digest,
                    "working_tree_dirty": baseline_dirty,
                },
            )
        operations.mkdir(mode=stat.S_IRWXU, exist_ok=True)
        operations.chmod(stat.S_IRWXU)
        home = state_real / "home"
        home.mkdir(mode=stat.S_IRWXU, exist_ok=True)
        home.chmod(stat.S_IRWXU)
        return cls(
            repo_root=repo_real,
            state_root=state_real,
            binding=binding,
            shell_path=shell,
            root_identity=root_identity,
            baseline_working_tree_digest=baseline_digest,
            baseline_working_tree_dirty=baseline_dirty,
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

    def _owned_effect_exists(self) -> bool:
        try:
            operation_dirs = tuple(self._operations.iterdir())
        except OSError as exc:
            raise DevBoxRuntimeError(
                "BINDING_UNAVAILABLE", "operation state is unavailable"
            ) from exc
        owned_effect = False
        for op_dir in operation_dirs:
            if not op_dir.is_dir():
                raise DevBoxRuntimeError(
                    "RECEIPT_UNAVAILABLE", "operation state is malformed"
                )
            record = _load_reconciled_record(op_dir)
            phase = record.get("phase")
            effect_state = record.get("effect_state")
            if phase in {
                "STARTED",
                "TERMINAL",
                "TERMINAL_OUTPUT_UNCERTAIN",
                "START_RECEIPT_UNAVAILABLE",
            }:
                owned_effect = True
                continue
            if (
                phase == "REFUSED"
                and effect_state == "NOT_APPLIED"
                and record.get("terminal") is True
            ):
                continue
            if phase == "PREPARED" and effect_state == "EFFECT_UNKNOWN":
                raise DevBoxRuntimeError(
                    "EFFECT_UNKNOWN", "prior command effect is unresolved"
                )
            raise DevBoxRuntimeError(
                "RECEIPT_UNAVAILABLE", "operation receipt state is invalid"
            )
        return owned_effect

    async def status(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        validate_tool_arguments("devbox_status", dict(arguments))
        self._revalidate_binding()
        observed_head = _git(self.repo_root, "rev-parse", "HEAD")
        snapshot = _working_tree_snapshot(self.repo_root)
        dirty = bool(snapshot)
        return {
            "target_ref": self.binding.target_ref,
            "generation": self.binding.generation,
            "owner_ref": self.binding.owner_ref,
            "repository": self.binding.repository,
            "committed_head": self.binding.committed_head,
            "observed_head": observed_head,
            "baseline_working_tree_dirty": self._baseline_working_tree_dirty,
            "working_tree_dirty": dirty,
            "working_tree_changed_from_baseline": (
                _working_tree_digest(snapshot) != self._baseline_working_tree_digest
            ),
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
        if not op_dir.exists() and not self._owned_effect_exists():
            snapshot = _working_tree_snapshot(self.repo_root)
            if (
                self._baseline_working_tree_dirty
                or _working_tree_digest(snapshot) != self._baseline_working_tree_digest
            ):
                raise DevBoxRuntimeError(
                    "SOURCE_DIRTY", "repository source changed before the first effect"
                )
        try:
            op_dir.mkdir(mode=stat.S_IRWXU)
            op_dir.chmod(stat.S_IRWXU)
            created = True
        except FileExistsError:
            created = False
        if not created:
            record = _load_reconciled_record(op_dir)
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
        try:
            _atomic_json(op_dir / "record.json", record)
        except OSError as exc:
            try:
                op_dir.rmdir()
            except OSError as cleanup_error:
                raise DevBoxRuntimeError(
                    "PRE_EFFECT_RECEIPT_UNAVAILABLE",
                    "pre-effect receipt failed and cleanup could not be proven",
                ) from cleanup_error
            raise DevBoxRuntimeError(
                "START_REFUSED", "pre-effect receipt could not be persisted"
            ) from exc
        supervisor_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "PYTHONSAFEPATH": "1",
            "PYTHONNOUSERSITE": "1",
        }
        argv = [
            sys.executable,
            "-P",
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
                cwd=str(self.state_root / "home"),
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
            latest = _load_reconciled_record(op_dir)
            if latest.get("phase") != "PREPARED":
                break
        return _record_projection(latest, reconciled=False)

    async def read_process(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        request = validate_tool_arguments("read_devbox_process", dict(arguments))
        process_ref = str(request["process_ref"])
        op_dir = self._op_dir_from_ref(process_ref)
        record = _load_reconciled_record(op_dir)
        if record.get("process_ref") != process_ref:
            raise DevBoxRuntimeError("PROCESS_NOT_FOUND", "process receipt does not match reference")
        maximum = int(request.get("max_bytes", _DEFAULT_OUTPUT_LIMIT_BYTES))
        accounting_complete = (
            record.get("phase") == "TERMINAL"
            and record.get("effect_state") == "APPLIED"
        )
        stdout = _read_stream(
            op_dir / "stdout.bin",
            progress_path=op_dir / "stdout.progress.json",
            cursor=int(request.get("stdout_cursor", 0)),
            maximum=maximum,
            metadata=record.get("stdout", {}),
            accounting_complete=accounting_complete,
        )
        stderr = _read_stream(
            op_dir / "stderr.bin",
            progress_path=op_dir / "stderr.progress.json",
            cursor=int(request.get("stderr_cursor", 0)),
            maximum=maximum,
            metadata=record.get("stderr", {}),
            accounting_complete=accounting_complete,
        )
        return {
            "process_ref": process_ref,
            "effect_state": record.get("effect_state", "EFFECT_UNKNOWN"),
            "terminal": bool(record.get("terminal", False)),
            "exit_code": record.get("exit_code"),
            "timed_out": bool(record.get("timed_out", False)),
            "cancel_requested": bool(record.get("cancel_requested", False))
            or _cancel_receipt_exists(op_dir),
            "stdout": stdout,
            "stderr": stderr,
        }

    async def cancel_process(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        request = validate_tool_arguments("cancel_devbox_process", dict(arguments))
        process_ref = str(request["process_ref"])
        op_dir = self._op_dir_from_ref(process_ref)
        record = _load_reconciled_record(op_dir)
        if record.get("process_ref") != process_ref:
            raise DevBoxRuntimeError("PROCESS_NOT_FOUND", "process receipt does not match reference")
        if record.get("terminal") is True:
            return {
                "process_ref": process_ref,
                "cancel_requested": bool(record.get("cancel_requested", False))
                or _cancel_receipt_exists(op_dir),
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
            latest = _load_reconciled_record(op_dir)
            if latest.get("terminal") is True:
                return {
                    "process_ref": process_ref,
                    "cancel_requested": bool(latest.get("cancel_requested", False))
                    or _cancel_receipt_exists(op_dir),
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
            latest = _load_reconciled_record(op_dir)
            if latest.get("terminal") is not True:
                raise DevBoxRuntimeError("PROCESS_IDENTITY_UNKNOWN", "process disappeared before cancellation proof")
            return {
                "process_ref": process_ref,
                "cancel_requested": bool(latest.get("cancel_requested", False))
                or _cancel_receipt_exists(op_dir),
                "terminal": True,
            }
        except OSError as exc:
            raise DevBoxRuntimeError("CANCEL_UNCERTAIN", "process signal outcome is uncertain") from exc
        return {"process_ref": process_ref, "cancel_requested": True, "terminal": False}


def _read_stream(
    path: Path,
    *,
    progress_path: Path,
    cursor: int,
    maximum: int,
    metadata: object,
    accounting_complete: bool,
) -> dict[str, Any]:
    if type(metadata) is not dict:
        metadata = {}
    try:
        retained = path.stat().st_size if path.exists() else 0
    except OSError as exc:
        raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "stream observation is unavailable") from exc
    progress = _load_stream_progress(progress_path) or {}

    def _counter(source: Mapping[str, Any], name: str, fallback: int) -> int:
        value = source.get(name, fallback)
        return value if type(value) is int and value >= 0 else fallback

    recorded_total = _counter(metadata, "total_bytes", retained)
    progress_total = _counter(progress, "total_bytes", retained)
    total_bytes = max(retained, recorded_total, progress_total)
    recorded_retained = _counter(metadata, "retained_bytes", retained)
    progress_retained = _counter(progress, "retained_bytes", retained)
    total_bytes = max(total_bytes, recorded_retained, progress_retained)
    retained_bytes = retained
    recorded_dropped = _counter(metadata, "dropped_bytes", max(0, total_bytes - retained_bytes))
    progress_dropped = _counter(progress, "dropped_bytes", max(0, total_bytes - retained_bytes))
    dropped_bytes = max(recorded_dropped, progress_dropped, total_bytes - retained_bytes)
    total_bytes = max(total_bytes, retained_bytes + dropped_bytes)

    start_cursor = min(cursor, retained)
    selected = min(maximum, max(0, retained - start_cursor))
    data = b""
    if selected:
        try:
            with path.open("rb") as handle:
                handle.seek(start_cursor)
                data = handle.read(selected)
        except OSError as exc:
            raise DevBoxRuntimeError("RECEIPT_UNAVAILABLE", "stream observation is unavailable") from exc
    end = start_cursor + len(data)
    return {
        "text": data.decode("utf-8", errors="replace"),
        "start_cursor": start_cursor,
        "next_cursor": end,
        "total_bytes": total_bytes,
        "retained_bytes": retained_bytes,
        "dropped_bytes": dropped_bytes,
        "truncated": dropped_bytes > 0,
        "gap_ranges": [[retained_bytes, total_bytes]] if dropped_bytes > 0 else [],
        "accounting_complete": accounting_complete,
    }


def _stream_progress(total: int, retained: int) -> dict[str, Any]:
    return {
        "schema": _PROGRESS_SCHEMA,
        "total_bytes": total,
        "retained_bytes": retained,
        "dropped_bytes": max(0, total - retained),
    }


def _pump(
    stream: Any,
    output: Path,
    progress_path: Path,
    limit: int,
    result: dict[str, int],
    key: str,
) -> None:
    total = 0
    retained = 0
    try:
        _volatile_json(progress_path, _stream_progress(total, retained))
        with output.open("wb", buffering=0) as handle:
            os.chmod(output, 0o600)
            read_available = getattr(stream, "read1", stream.read)
            while True:
                chunk = read_available(65536)
                if not chunk:
                    break
                total += len(chunk)
                keep = b""
                if retained < limit:
                    keep = chunk[: max(0, limit - retained)]
                next_retained = retained + len(keep)
                if keep:
                    handle.write(keep)
                    retained = next_retained
                _volatile_json(progress_path, _stream_progress(total, retained))
            os.fsync(handle.fileno())
        _volatile_json(progress_path, _stream_progress(total, retained))
        result[key] = total
        result[key + "_retained"] = retained
    except BaseException:
        result[key + "_error"] = 1


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
    try:
        _persist_effect_record(op_dir, started)
    except OSError:
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
        uncertain = dict(started)
        uncertain.update(
            phase="START_RECEIPT_UNAVAILABLE",
            effect_state="EFFECT_UNKNOWN",
            terminal=True,
            exit_code=child.returncode,
            ended_at_ns=time.time_ns(),
        )
        try:
            _atomic_json(record_path, uncertain)
        except OSError:
            pass
        return 74

    totals: dict[str, int] = {}
    stdout_thread = threading.Thread(
        target=_pump,
        args=(
            child.stdout,
            op_dir / "stdout.bin",
            op_dir / "stdout.progress.json",
            output_limit_bytes,
            totals,
            "stdout",
        ),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_pump,
        args=(
            child.stderr,
            op_dir / "stderr.bin",
            op_dir / "stderr.progress.json",
            output_limit_bytes,
            totals,
            "stderr",
        ),
        daemon=True,
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
    if (
        stdout_thread.is_alive()
        or stderr_thread.is_alive()
        or totals.get("stdout_error")
        or totals.get("stderr_error")
    ):
        # The child is terminal but retained output accounting is incomplete.
        final = _load_reconciled_record(op_dir)
        final.update(
            phase="TERMINAL_OUTPUT_UNCERTAIN",
            effect_state="EFFECT_UNKNOWN",
            terminal=True,
            exit_code=child.returncode,
            timed_out=timed_out,
            cancel_requested=_cancel_receipt_exists(op_dir),
        )
        _persist_effect_record(op_dir, final)
        return 74

    cancel_requested = _cancel_receipt_exists(op_dir)
    final = _load_reconciled_record(op_dir)
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
    _persist_effect_record(op_dir, final)
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
