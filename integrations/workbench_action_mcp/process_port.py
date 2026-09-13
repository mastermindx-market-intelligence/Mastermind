"""Durable bounded attended-process owner for Workbench Action.

This owner starts only exact, preconfigured validation recipes. Start intent is
durably marked before the runner is spawned; the runner writes child/terminal
receipts and output to a private state directory so a lost HTTP response or
ordinary Workbench service restart can reconcile the original command without
blind replay. No shell string, cwd, executable, environment or PID is model input.
"""
from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .contracts import ActionCaller, ActionScope, ProjectActionBinding
from .patch_port import (
    ActionBindingResolver,
    ActionExecutor,
    ProjectActionRefused,
    _binding_key,
    _current_binding,
)
from .process_contracts import (
    COMMAND_TOKEN_SCHEMA,
    MAX_COMMAND_TTL_MS,
    CommandTokenCodec,
    PreparedCommand,
    ProcessContractError,
    ValidationRecipe,
    prepared_matches_authority,
    validate_prepared_command,
    validate_recipe_set,
)

_START_SCHEMA = "mastermind.workbench_process_start.v1"
_READY_SCHEMA = "mastermind.workbench_process_ready.v1"
_CHILD_SCHEMA = "mastermind.workbench_process_child.v1"
_TERMINAL_SCHEMA = "mastermind.workbench_process_terminal.v1"
_MAX_STATE_JSON_BYTES = 8192
_MAX_READ_PAGE_BYTES = 65536
_EFFECTS = frozenset({"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
_PROCESS_STATES = frozenset(
    {
        "NOT_STARTED",
        "STARTING",
        "RUNNING",
        "START_FAILED",
        "EXITED",
        "TIMED_OUT",
        "CANCELLED",
        "OUTPUT_LIMIT",
        "RUNNER_FAILED",
        "OWNER_LOST",
    }
)


class ProcessActionRefused(Exception):
    _CODES = frozenset(
        {
            "PROCESS_ACTION_REFUSED",
            "PROCESS_BINDING_CHANGED",
            "PROCESS_COMMAND_INVALID",
            "PROCESS_COMMAND_EXPIRED",
            "PROCESS_RECIPE_CHANGED",
            "PROCESS_START_EFFECT_UNKNOWN",
            "PROCESS_STATE_UNAVAILABLE",
            "PROCESS_RESULT_UNVERIFIED",
        }
    )

    def __init__(self, code: str = "PROCESS_ACTION_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown process action refusal")
        self.code = code
        super().__init__(code)


RecipeList = Callable[[ActionCaller, str], Awaitable[Mapping[str, Any]]]
CommandPrepare = Callable[[ActionCaller, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]
CommandStart = Callable[[ActionCaller, object], Awaitable[Mapping[str, Any]]]
CommandReconcile = Callable[[ActionCaller, object], Awaitable[Mapping[str, Any]]]
ProcessRead = Callable[[ActionCaller, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


@dataclasses.dataclass(frozen=True)
class AttendedProcessPorts:
    list_recipes: RecipeList
    prepare: CommandPrepare
    start: CommandStart
    reconcile_start: CommandReconcile
    read: ProcessRead


def _now(clock_ms: Callable[[], int]) -> int:
    try:
        value = clock_ms()
    except Exception as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    if type(value) is not int or not 0 <= value < 2**63:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    return value


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        result[key] = value
    return result


def _state_root(fd: int) -> os.stat_result:
    try:
        value = os.fstat(fd)
    except OSError as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o700
        or os.get_inheritable(fd)
    ):
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    return value


def _open_state_dir(root_fd: int, command_id: str, *, create: bool) -> int | None:
    _state_root(root_fd)
    if len(command_id) != 32 or any(c not in "0123456789abcdef" for c in command_id):
        raise ProcessActionRefused("PROCESS_COMMAND_INVALID")
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not directory or not nofollow or not cloexec or os.open not in os.supports_dir_fd:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    if create:
        try:
            os.mkdir(command_id, 0o700, dir_fd=root_fd)
            os.fsync(root_fd)
        except FileExistsError:
            pass
        except OSError as error:
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    try:
        fd = os.open(
            command_id,
            os.O_RDONLY | directory | nofollow | cloexec,
            dir_fd=root_fd,
        )
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    try:
        value = os.fstat(fd)
        if (
            not stat.S_ISDIR(value.st_mode)
            or value.st_uid != os.geteuid()
            or stat.S_IMODE(value.st_mode) != 0o700
            or os.get_inheritable(fd)
        ):
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_file(state_fd: int, name: str, flags: int, *, create: bool = False) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    selected = flags | nofollow | cloexec
    if create:
        selected |= os.O_CREAT
    try:
        fd = os.open(name, selected, 0o600, dir_fd=state_fd)
    except OSError as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    try:
        value = os.fstat(fd)
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != os.geteuid()
            or stat.S_IMODE(value.st_mode) != 0o600
            or value.st_nlink != 1
            or os.get_inheritable(fd)
        ):
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_json(state_fd: int, name: str) -> dict[str, Any] | None:
    try:
        fd = _open_file(state_fd, name, os.O_RDONLY)
    except ProcessActionRefused as error:
        try:
            os.stat(name, dir_fd=state_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError:
            raise error
        raise
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            raw = os.read(fd, min(4096, _MAX_STATE_JSON_BYTES + 1 - total))
            if not raw:
                break
            total += len(raw)
            if total > _MAX_STATE_JSON_BYTES:
                raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
            chunks.append(raw)
    finally:
        os.close(fd)
    try:
        value = json.loads(
            b"".join(chunks).decode("ascii", errors="strict"),
            object_pairs_hook=_closed_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
            ),
        )
    except ProcessActionRefused:
        raise
    except Exception as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    if type(value) is not dict:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    return value


def _write_json(state_fd: int, name: str, document: Mapping[str, Any]) -> None:
    try:
        raw = json.dumps(
            dict(document),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii") + b"\n"
    except Exception as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    if len(raw) > _MAX_STATE_JSON_BYTES:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    temp = f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    fd = -1
    try:
        fd = _open_file(
            state_fd,
            temp,
            os.O_WRONLY | os.O_EXCL,
            create=True,
        )
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                raise OSError("short state write")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.rename(temp, name, src_dir_fd=state_fd, dst_dir_fd=state_fd)
        os.fsync(state_fd)
    except ProcessActionRefused:
        raise
    except OSError as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(temp, dir_fd=state_fd)
        except OSError:
            pass


def _liveness_held(state_fd: int) -> bool | None:
    try:
        fd = _open_file(state_fd, "liveness.lock", os.O_RDWR)
    except ProcessActionRefused:
        try:
            os.stat("liveness.lock", dir_fd=state_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError:
            return None
        raise
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
    finally:
        os.close(fd)


def _validate_receipt_identity(document: Mapping[str, Any], command_id: str) -> None:
    if document.get("command_id") != command_id:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")


def _inspect(state_root_fd: int, prepared: PreparedCommand) -> dict[str, Any]:
    state_fd = _open_state_dir(state_root_fd, prepared.command_id, create=False)
    if state_fd is None:
        return {
            "effect_state": "NOT_APPLIED",
            "process_state": "NOT_STARTED",
            "exit_code": None,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
        }
    try:
        start = _read_json(state_fd, "start.json")
        ready = _read_json(state_fd, "ready.json")
        child = _read_json(state_fd, "child.json")
        terminal = _read_json(state_fd, "terminal.json")
        if start is None:
            return {
                "effect_state": "NOT_APPLIED",
                "process_state": "NOT_STARTED",
                "exit_code": None,
                "stdout_bytes": 0,
                "stderr_bytes": 0,
            }
        _validate_receipt_identity(start, prepared.command_id)
        if start.get("schema") != _START_SCHEMA or start.get("recipe_digest") != prepared.recipe_digest:
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        if start.get("state") == "START_FAILED":
            return {
                "effect_state": "NOT_APPLIED",
                "process_state": "START_FAILED",
                "exit_code": None,
                "stdout_bytes": 0,
                "stderr_bytes": 0,
            }
        if start.get("state") != "STARTING":
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        if ready is not None:
            _validate_receipt_identity(ready, prepared.command_id)
            if ready.get("schema") != _READY_SCHEMA:
                raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        if child is not None:
            _validate_receipt_identity(child, prepared.command_id)
            if child.get("schema") != _CHILD_SCHEMA or type(child.get("child_pid")) is not int:
                raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        if terminal is not None:
            _validate_receipt_identity(terminal, prepared.command_id)
            state = terminal.get("terminal_state")
            exit_code = terminal.get("exit_code")
            if (
                terminal.get("schema") != _TERMINAL_SCHEMA
                or state not in {"EXITED", "TIMED_OUT", "CANCELLED", "OUTPUT_LIMIT", "RUNNER_FAILED"}
                or (exit_code is not None and type(exit_code) is not int)
                or type(terminal.get("stdout_bytes")) is not int
                or type(terminal.get("stderr_bytes")) is not int
            ):
                raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
            effect = "APPLIED" if child is not None else "NOT_APPLIED"
            return {
                "effect_state": effect,
                "process_state": state,
                "exit_code": exit_code,
                "stdout_bytes": terminal["stdout_bytes"],
                "stderr_bytes": terminal["stderr_bytes"],
            }
        held = _liveness_held(state_fd)
        if child is not None:
            if held is True:
                return {
                    "effect_state": "APPLIED",
                    "process_state": "RUNNING",
                    "exit_code": None,
                    "stdout_bytes": _output_size(state_fd, "stdout.log"),
                    "stderr_bytes": _output_size(state_fd, "stderr.log"),
                }
            return {
                "effect_state": "EFFECT_UNKNOWN",
                "process_state": "OWNER_LOST",
                "exit_code": None,
                "stdout_bytes": _output_size(state_fd, "stdout.log"),
                "stderr_bytes": _output_size(state_fd, "stderr.log"),
            }
        return {
            "effect_state": "EFFECT_UNKNOWN",
            "process_state": "STARTING" if held is True or ready is not None else "OWNER_LOST",
            "exit_code": None,
            "stdout_bytes": _output_size(state_fd, "stdout.log"),
            "stderr_bytes": _output_size(state_fd, "stderr.log"),
        }
    finally:
        os.close(state_fd)


def _output_size(state_fd: int, name: str) -> int:
    try:
        value = os.stat(name, dir_fd=state_fd, follow_symlinks=False)
    except FileNotFoundError:
        return 0
    except OSError as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o600
        or value.st_nlink != 1
        or value.st_size < 0
    ):
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    return value.st_size


def _read_output_page(state_fd: int, name: str, offset: int, maximum: int) -> dict[str, Any]:
    if type(offset) is not int or offset < 0 or type(maximum) is not int or not 1 <= maximum <= _MAX_READ_PAGE_BYTES:
        raise ProcessActionRefused("PROCESS_COMMAND_INVALID")
    try:
        fd = _open_file(state_fd, name, os.O_RDONLY)
    except ProcessActionRefused:
        try:
            os.stat(name, dir_fd=state_fd, follow_symlinks=False)
        except FileNotFoundError:
            return {
                "offset_start": 0,
                "offset_end": 0,
                "retained_start": 0,
                "retained_end": 0,
                "content": "",
                "truncated": False,
                "next_offset": None,
            }
        raise
    try:
        size = os.fstat(fd).st_size
        start = min(offset, size)
        os.lseek(fd, start, os.SEEK_SET)
        raw = os.read(fd, min(maximum, size - start))
    finally:
        os.close(fd)
    # Process output is evidence, not an instruction stream. Preserve arbitrary
    # bytes losslessly without OCR/locale assumptions.
    content = raw.decode("utf-8", errors="replace")
    end = start + len(raw)
    return {
        "offset_start": start,
        "offset_end": end,
        "retained_start": 0,
        "retained_end": size,
        "content": content,
        "truncated": end < size,
        "next_offset": end if end < size else None,
    }


def _runner_identity(path: str) -> str:
    selected = Path(path)
    try:
        before = selected.lstat()
        raw = selected.read_bytes()
        after = selected.lstat()
    except OSError as error:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) & 0o022
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) > 1024 * 1024
    ):
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    return hashlib.sha256(raw).hexdigest()


def _start_sync(
    *,
    state_root_fd: int,
    scope: ActionScope,
    prepared: PreparedCommand,
    recipe: ValidationRecipe,
    runner_path: str,
    runner_digest: str,
    python_executable: str,
    clock_ms: Callable[[], int],
) -> dict[str, Any]:
    existing = _inspect(state_root_fd, prepared)
    if existing["process_state"] != "NOT_STARTED":
        return existing
    state_fd = _open_state_dir(state_root_fd, prepared.command_id, create=True)
    if state_fd is None:
        raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
    start_lock_fd = -1
    try:
        # One file lock is the same-command start linearization point across
        # concurrent tool calls and ordinary service restart.
        start_lock_fd = _open_file(
            state_fd, "start.lock", os.O_RDWR, create=True
        )
        fcntl.flock(start_lock_fd, fcntl.LOCK_EX)
        # Re-inspect after acquiring the deterministic directory lock. Another
        # same-ref call may have populated it while this call was waiting.
        current_start = _read_json(state_fd, "start.json")
        if current_start is not None:
            os.close(state_fd)
            state_fd = -1
            return _inspect(state_root_fd, prepared)
        now_ms = _now(clock_ms)
        _write_json(
            state_fd,
            "start.json",
            {
                "schema": _START_SCHEMA,
                "command_id": prepared.command_id,
                "state": "STARTING",
                "recipe_digest": prepared.recipe_digest,
                "runner_digest": runner_digest,
                "requested_at_ms": now_ms,
            },
        )
        root_dup = os.dup(scope.root_fd)
        state_dup = os.dup(state_fd)
        try:
            command = [
                python_executable,
                runner_path,
                "--root-fd",
                str(root_dup),
                "--state-fd",
                str(state_dup),
                "--timeout-seconds",
                str(prepared.timeout_seconds),
                "--max-output-bytes",
                str(prepared.max_output_bytes),
                "--command-id",
                prepared.command_id,
                "--",
                *recipe.argv,
            ]
            try:
                subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={
                        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                        "HOME": "/var/empty",
                        "LC_ALL": "C",
                        "LANG": "C",
                        "PYTHONNOUSERSITE": "1",
                    },
                    close_fds=True,
                    pass_fds=(root_dup, state_dup),
                    start_new_session=True,
                )
            except (OSError, ValueError, subprocess.SubprocessError):
                _write_json(
                    state_fd,
                    "start.json",
                    {
                        "schema": _START_SCHEMA,
                        "command_id": prepared.command_id,
                        "state": "START_FAILED",
                        "recipe_digest": prepared.recipe_digest,
                        "runner_digest": runner_digest,
                        "requested_at_ms": now_ms,
                    },
                )
                return {
                    "effect_state": "NOT_APPLIED",
                    "process_state": "START_FAILED",
                    "exit_code": None,
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                }
        finally:
            os.close(root_dup)
            os.close(state_dup)
    finally:
        if start_lock_fd >= 0:
            try:
                fcntl.flock(start_lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(start_lock_fd)
        if state_fd >= 0:
            os.close(state_fd)

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        observed = _inspect(state_root_fd, prepared)
        if observed["process_state"] not in {"STARTING", "OWNER_LOST"}:
            return observed
        # OWNER_LOST can be a micro-race before runner acquires its flock.
        time.sleep(0.02)
    return _inspect(state_root_fd, prepared)


def _binding_for_prepared(
    prepared: PreparedCommand,
    caller: ActionCaller,
    resolve_binding: ActionBindingResolver,
    clock_ms: Callable[[], int],
) -> ProjectActionBinding:
    binding = _current_binding(
        caller=caller,
        project_ref=prepared.project_ref,
        resolve_binding=resolve_binding,
        clock_ms=clock_ms,
    )
    if not prepared_matches_authority(prepared, caller, binding.scope, binding.project_ref):
        raise ProcessActionRefused("PROCESS_BINDING_CHANGED")
    return binding


def _decode(codec: CommandTokenCodec, token: object, clock_ms: Callable[[], int]) -> PreparedCommand:
    try:
        return codec.decode(token, now_ms=_now(clock_ms))
    except ProcessContractError as error:
        message = str(error).lower()
        code = "PROCESS_COMMAND_EXPIRED" if "expired" in message else "PROCESS_COMMAND_INVALID"
        raise ProcessActionRefused(code) from error


def _recipe_for(prepared: PreparedCommand, recipes: Mapping[str, ValidationRecipe]) -> ValidationRecipe:
    recipe = recipes.get(prepared.recipe_id)
    if recipe is None or recipe.digest != prepared.recipe_digest:
        raise ProcessActionRefused("PROCESS_RECIPE_CHANGED")
    if prepared.timeout_seconds > recipe.timeout_seconds or prepared.max_output_bytes > recipe.max_output_bytes:
        raise ProcessActionRefused("PROCESS_RECIPE_CHANGED")
    return recipe


def _public_state(prepared: PreparedCommand, observed: Mapping[str, Any]) -> dict[str, Any]:
    effect = observed.get("effect_state")
    state = observed.get("process_state")
    if effect not in _EFFECTS or state not in _PROCESS_STATES:
        raise ProcessActionRefused("PROCESS_RESULT_UNVERIFIED")
    return {
        "status": "OK",
        "effect_state": effect,
        "process_state": state,
        "process_ref": "command:" + prepared.command_id,
        "project_ref": prepared.project_ref,
        "responsibility_ref": prepared.responsibility_ref,
        "operation_ref": prepared.operation_ref,
        "recipe_id": prepared.recipe_id,
        "exit_code": observed.get("exit_code"),
        "stdout_bytes": int(observed.get("stdout_bytes", 0)),
        "stderr_bytes": int(observed.get("stderr_bytes", 0)),
    }


def create_attended_process_ports(
    *,
    resolve_binding: ActionBindingResolver,
    clock_ms: Callable[[], int],
    run_io: ActionExecutor,
    token_codec: CommandTokenCodec,
    recipes: tuple[ValidationRecipe, ...],
    command_ttl_ms: int,
    process_directory_fd: int,
    runner_path: str | None = None,
    python_executable: str | None = None,
) -> AttendedProcessPorts:
    if not all(callable(value) for value in (resolve_binding, clock_ms, run_io)):
        raise TypeError("explicit binding, clock and bounded I/O owner required")
    if not isinstance(token_codec, CommandTokenCodec):
        raise TypeError("explicit command token codec required")
    selected_recipes = validate_recipe_set(recipes)
    if type(command_ttl_ms) is not int or not 1000 <= command_ttl_ms <= MAX_COMMAND_TTL_MS:
        raise ValueError("command TTL is invalid")
    _state_root(process_directory_fd)
    recipe_map = {recipe.recipe_id: recipe for recipe in selected_recipes}
    if runner_path is None:
        runner_path = str(
            Path(__file__).resolve().parents[2] / "scripts" / "mastermind_workbench_process_runner.py"
        )
    if python_executable is None:
        python_executable = sys.executable
    if type(runner_path) is not str or not runner_path.startswith("/"):
        raise ValueError("runner path must be absolute")
    if type(python_executable) is not str or not python_executable.startswith("/"):
        raise ValueError("python executable must be absolute")
    runner_digest = _runner_identity(runner_path)

    async def list_recipes(caller: ActionCaller, project_ref: str) -> Mapping[str, Any]:
        try:
            _current_binding(
                caller=caller,
                project_ref=project_ref,
                resolve_binding=resolve_binding,
                clock_ms=clock_ms,
            )
        except ProjectActionRefused as error:
            raise ProcessActionRefused("PROCESS_BINDING_CHANGED") from error
        return {
            "status": "OK",
            "project_ref": project_ref,
            "recipes": [
                {
                    "recipe_id": recipe.recipe_id,
                    "description": recipe.description,
                    "timeout_seconds": recipe.timeout_seconds,
                    "max_output_bytes": recipe.max_output_bytes,
                    "recipe_digest": recipe.digest,
                }
                for recipe in selected_recipes
            ],
        }

    async def prepare(caller: ActionCaller, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            request = dict(arguments)
        except Exception as error:
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID") from error
        if set(request) - {"project_ref", "recipe_id", "timeout_seconds", "max_output_bytes"}:
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID")
        project_ref = request.get("project_ref")
        recipe_id = request.get("recipe_id")
        if type(project_ref) is not str or type(recipe_id) is not str:
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID")
        recipe = recipe_map.get(recipe_id)
        if recipe is None:
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID")
        timeout = request.get("timeout_seconds", recipe.timeout_seconds)
        maximum = request.get("max_output_bytes", recipe.max_output_bytes)
        if (
            type(timeout) is not int
            or not 1 <= timeout <= recipe.timeout_seconds
            or type(maximum) is not int
            or not 1024 <= maximum <= recipe.max_output_bytes
        ):
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID")
        try:
            binding = _current_binding(
                caller=caller,
                project_ref=project_ref,
                resolve_binding=resolve_binding,
                clock_ms=clock_ms,
            )
        except ProjectActionRefused as error:
            raise ProcessActionRefused("PROCESS_BINDING_CHANGED") from error
        now_ms = _now(clock_ms)
        expiry = min(
            now_ms + command_ttl_ms,
            binding.scope.expires_at_ms,
            caller.expires_at * 1000,
        )
        if expiry <= now_ms:
            raise ProcessActionRefused("PROCESS_BINDING_CHANGED")
        prepared = PreparedCommand(
            schema=COMMAND_TOKEN_SCHEMA,
            command_id=secrets.token_hex(16),
            subject_digest=caller.subject_digest,
            client_ref=caller.client_ref,
            resource=caller.resource,
            project_ref=project_ref,
            context_ref=binding.scope.context_ref,
            responsibility_ref=binding.scope.responsibility_ref,
            operation_ref=binding.scope.operation_ref,
            owner_ref=binding.scope.owner_ref,
            generation=binding.scope.generation,
            root_device=binding.scope.root_device,
            root_inode=binding.scope.root_inode,
            committed_head=binding.scope.committed_head,
            recipe_id=recipe.recipe_id,
            recipe_digest=recipe.digest,
            timeout_seconds=timeout,
            max_output_bytes=maximum,
            issued_at_ms=now_ms,
            expires_at_ms=expiry,
        )
        try:
            command_ref = token_codec.encode(prepared)
        except ProcessContractError as error:
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID") from error
        return {
            "status": "PREPARED",
            "command_ref": command_ref,
            "process_ref": "command:" + prepared.command_id,
            "project_ref": project_ref,
            "responsibility_ref": prepared.responsibility_ref,
            "operation_ref": prepared.operation_ref,
            "recipe_id": prepared.recipe_id,
            "recipe_digest": prepared.recipe_digest,
            "timeout_seconds": prepared.timeout_seconds,
            "max_output_bytes": prepared.max_output_bytes,
            "expires_at_ms": prepared.expires_at_ms,
        }

    async def start(caller: ActionCaller, token: object) -> Mapping[str, Any]:
        prepared = _decode(token_codec, token, clock_ms)
        binding = _binding_for_prepared(prepared, caller, resolve_binding, clock_ms)
        recipe = _recipe_for(prepared, recipe_map)
        original_key = _binding_key(binding)
        operation = lambda: _start_sync(
            state_root_fd=process_directory_fd,
            scope=binding.scope,
            prepared=prepared,
            recipe=recipe,
            runner_path=runner_path,
            runner_digest=runner_digest,
            python_executable=python_executable,
            clock_ms=clock_ms,
        )
        try:
            pending = run_io(operation)
            if not inspect.isawaitable(pending):
                raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
            observed = await pending
        except ProcessActionRefused:
            raise
        except Exception as error:
            raise ProcessActionRefused("PROCESS_START_EFFECT_UNKNOWN") from error
        try:
            current = _binding_for_prepared(prepared, caller, resolve_binding, clock_ms)
            if _binding_key(current) != original_key:
                if observed.get("effect_state") == "NOT_APPLIED":
                    raise ProcessActionRefused("PROCESS_BINDING_CHANGED")
                observed = dict(observed)
                observed["effect_state"] = "EFFECT_UNKNOWN"
        except ProcessActionRefused:
            if observed.get("effect_state") == "NOT_APPLIED":
                raise
            observed = dict(observed)
            observed["effect_state"] = "EFFECT_UNKNOWN"
        return _public_state(prepared, observed)

    async def reconcile_start(caller: ActionCaller, token: object) -> Mapping[str, Any]:
        prepared = _decode(token_codec, token, clock_ms)
        _binding_for_prepared(prepared, caller, resolve_binding, clock_ms)
        _recipe_for(prepared, recipe_map)
        pending = run_io(lambda: _inspect(process_directory_fd, prepared))
        if not inspect.isawaitable(pending):
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        try:
            observed = await pending
        except Exception as error:
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
        return _public_state(prepared, observed)

    async def read(caller: ActionCaller, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            request = dict(arguments)
        except Exception as error:
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID") from error
        if set(request) - {"command_ref", "stdout_offset", "stderr_offset", "max_bytes"}:
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID")
        prepared = _decode(token_codec, request.get("command_ref"), clock_ms)
        _binding_for_prepared(prepared, caller, resolve_binding, clock_ms)
        _recipe_for(prepared, recipe_map)
        stdout_offset = request.get("stdout_offset", 0)
        stderr_offset = request.get("stderr_offset", 0)
        maximum = request.get("max_bytes", 32768)
        if (
            type(stdout_offset) is not int
            or stdout_offset < 0
            or type(stderr_offset) is not int
            or stderr_offset < 0
            or type(maximum) is not int
            or not 1 <= maximum <= _MAX_READ_PAGE_BYTES
        ):
            raise ProcessActionRefused("PROCESS_COMMAND_INVALID")

        def observe() -> dict[str, Any]:
            state = _inspect(process_directory_fd, prepared)
            state_fd = _open_state_dir(process_directory_fd, prepared.command_id, create=False)
            if state_fd is None:
                stdout_page = _read_output_page_placeholder()
                stderr_page = _read_output_page_placeholder()
            else:
                try:
                    stdout_page = _read_output_page(state_fd, "stdout.log", stdout_offset, maximum)
                    stderr_page = _read_output_page(state_fd, "stderr.log", stderr_offset, maximum)
                finally:
                    os.close(state_fd)
            return {"state": state, "stdout": stdout_page, "stderr": stderr_page}

        pending = run_io(observe)
        if not inspect.isawaitable(pending):
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE")
        try:
            result = await pending
        except ProcessActionRefused:
            raise
        except Exception as error:
            raise ProcessActionRefused("PROCESS_STATE_UNAVAILABLE") from error
        public = _public_state(prepared, result["state"])
        public["stdout"] = result["stdout"]
        public["stderr"] = result["stderr"]
        return public

    return AttendedProcessPorts(
        list_recipes=list_recipes,
        prepare=prepare,
        start=start,
        reconcile_start=reconcile_start,
        read=read,
    )


def _read_output_page_placeholder() -> dict[str, Any]:
    return {
        "offset_start": 0,
        "offset_end": 0,
        "retained_start": 0,
        "retained_end": 0,
        "content": "",
        "truncated": False,
        "next_offset": None,
    }


__all__ = [
    "AttendedProcessPorts",
    "CommandPrepare",
    "CommandReconcile",
    "CommandStart",
    "ProcessActionRefused",
    "ProcessRead",
    "RecipeList",
    "create_attended_process_ports",
]
