"""Pinned Peekaboo data-plane adapter; no daemon, routing, model or fallback.

A host enrolls ONE local CLI or ONE bridge incarnation. Both are supported, but
the choice is immutable for the adapter lifetime. Target observations and input
always use exact PID/window selectors and a fresh native snapshot. The adapter
never invokes --foreground, --web-focus, arbitrary CLI text, shell or AI analysis.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time

from integrations.workbench_action_mcp.action_artifacts import ActionHostBinding
from .contracts import (
    ACTIONS, AppUseRefused, NativeDispatchUnknown, NativeTarget,
    canonical, closed_json, command, digest,
)

MAX_OUTPUT = 1024 * 1024
MAX_STDERR = 16384


@dataclasses.dataclass(frozen=True)
class PeekabooConfig:
    executable: str
    executable_sha256: str
    home_dir: str
    host_binding: ActionHostBinding
    expected_uid: int
    qualified_actions: tuple[str, ...] = ()
    bridge_socket: str | None = None
    timeout_seconds: float = 20.0


def _identity(path: str, *, socket: bool = False) -> tuple:
    info = Path(path).lstat()
    if (not Path(path).is_absolute()
            or (not stat.S_ISSOCK(info.st_mode) if socket else not stat.S_ISREG(info.st_mode))
            or info.st_mode & 0o022
            or info.st_uid not in ({os.getuid()} if socket else {0, os.getuid()})):
        raise AppUseRefused("PINNED_NATIVE_PATH_REQUIRED")
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_size, info.st_mtime_ns)


def _bounded_process(argv: list[str], *, env: dict[str, str], timeout: float,
                     effectful: bool = False) -> dict:
    """Bound both streams while draining; truncation is never parsed as success."""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            start_new_session=True, close_fds=True)
    except OSError as exc:
        # Popen did not create the CLI; this is proven pre-dispatch absence.
        raise AppUseRefused("NATIVE_PROCESS_NOT_STARTED") from exc
    streams = {}
    selector = selectors.DefaultSelector()
    try:
        for stream, maximum in ((process.stdout, MAX_OUTPUT), (process.stderr, MAX_STDERR)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
            streams[stream] = [bytearray(), maximum]
        deadline = time.monotonic() + timeout
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            for key, _ in selector.select(min(remaining, .1)):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output, maximum = streams[key.fileobj]
                output.extend(chunk)
                if len(output) > maximum:
                    raise ValueError("output limit")
        rc = process.wait(timeout=max(.01, deadline - time.monotonic()))
        value = closed_json(bytes(streams[process.stdout][0]), maximum=MAX_OUTPUT)
        if rc != 0 or value.get("success") is not True or type(value.get("data")) is not dict:
            raise ValueError("native response was not successful")
        return value["data"]
    except Exception as exc:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        # Killing the CLI does not cancel a bridge operation already delivered.
        failure = NativeDispatchUnknown if effectful else AppUseRefused
        raise failure("NATIVE_RESULT_UNQUALIFIED:" + type(exc).__name__) from exc
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()


def _boot_id() -> str:
    try:
        output = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=2, check=True,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}).stdout
        value = output.decode("ascii").strip()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise AppUseRefused("MACOS_SESSION_UNAVAILABLE") from exc
    if not value or len(value) > 128:
        raise AppUseRefused("MACOS_SESSION_UNAVAILABLE")
    return value


class PeekabooAdapter:
    def __init__(self, config: PeekabooConfig):
        if (type(config) is not PeekabooConfig
                or type(config.expected_uid) is not int or config.expected_uid != os.getuid()
                or type(config.qualified_actions) is not tuple
                or not set(config.qualified_actions) <= ACTIONS
                or len(set(config.qualified_actions)) != len(config.qualified_actions)
                or isinstance(config.timeout_seconds, bool)
                or not 1 <= config.timeout_seconds <= 20
                or not Path(config.home_dir).is_absolute()):
            raise AppUseRefused("NATIVE_HOST_CONFIG_REQUIRED")
        self.config = config
        self._binary_identity = _identity(config.executable)
        if hashlib.sha256(Path(config.executable).read_bytes()).hexdigest() != config.executable_sha256:
            raise AppUseRefused("NATIVE_BINARY_DIGEST_MISMATCH")
        self._socket_identity = (_identity(config.bridge_socket, socket=True)
                                 if config.bridge_socket is not None else None)
        self._boot = _boot_id()
        if self._boot != config.host_binding.boot_session_id:
            raise AppUseRefused("NATIVE_BOOT_MISMATCH")
        self._console_uid = Path("/dev/console").stat().st_uid
        if self._console_uid != config.expected_uid:
            raise AppUseRefused("NATIVE_CONSOLE_USER_MISMATCH")
        self.session_ref = digest({
            "adapter": "peekaboo", "host": config.host_binding.host_id,
            "boot": self._boot, "uid": self._console_uid,
            "binary": config.executable_sha256, "binary_identity": self._binary_identity,
            "bridge_identity": self._socket_identity, "carrier": self.carrier,
        })
        self.qualified_actions = frozenset(config.qualified_actions)
        self._env = {"HOME": config.home_dir, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                     "LANG": "en_US.UTF-8"}

    @property
    def carrier(self) -> str:
        return "peekaboo-bridge" if self.config.bridge_socket else "peekaboo-local"

    def validate_session(self) -> None:
        if (_identity(self.config.executable) != self._binary_identity
                or _boot_id() != self._boot
                or Path("/dev/console").stat().st_uid != self._console_uid
                or (self.config.bridge_socket is not None and
                    _identity(self.config.bridge_socket, socket=True) != self._socket_identity)):
            raise AppUseRefused("NATIVE_SESSION_CHANGED")

    def _run(self, args: list[str], *, effectful: bool = False) -> dict:
        self.validate_session()
        carrier = (["--bridge-socket", self.config.bridge_socket]
                   if self.config.bridge_socket else ["--no-remote"])
        return _bounded_process([self.config.executable, *args, "--json", *carrier],
            env=self._env, timeout=self.config.timeout_seconds, effectful=effectful)

    def permissions(self) -> dict:
        data = self._run(["permissions", "status"])
        rows = data.get("permissions")
        if type(rows) is not list:
            raise AppUseRefused("NATIVE_PERMISSIONS_UNQUALIFIED")
        result = {row["name"]: row.get("isGranted") is True for row in rows
                  if type(row) is dict and type(row.get("name")) is str}
        return {"source": data.get("source"), "permissions": result,
                "observation_ready": (result.get("Accessibility") is True
                                      and result.get("Screen Recording") is True),
                "screen_recording": result.get("Screen Recording") is True}

    def applications(self) -> dict:
        data = self._run(["app", "list", "--include-hidden", "--include-background"])
        rows = data.get("apps")
        if type(rows) is not list or len(rows) > 1024:
            raise AppUseRefused("NATIVE_INVENTORY_UNQUALIFIED")
        apps = []
        for row in rows:
            if type(row) is not dict:
                continue
            identity = row.get("process_start_identity_decimal")
            # No integer conversion: provider precision is part of identity.
            if (type(row.get("bundle_id")) is str and row["bundle_id"]
                    and type(row.get("pid")) is int and row["pid"] > 0
                    and type(identity) is str and identity.isdecimal()
                    and len(identity) <= 30):
                apps.append({"bundle_id": row["bundle_id"], "pid": row["pid"],
                    "process_start_identity_decimal": identity,
                    "name": str(row.get("name", ""))[:256]})
        return {"applications": apps, "inventory_complete": len(apps) == len(rows)
                and not bool(data.get("warnings"))}

    def windows(self, *, bundle_id: str, pid: int,
                process_start_identity_decimal: str) -> dict:
        apps = self.applications()["applications"]
        if not any(row["bundle_id"] == bundle_id and row["pid"] == pid
                   and row["process_start_identity_decimal"] == process_start_identity_decimal
                   for row in apps):
            raise AppUseRefused("NATIVE_PROCESS_CHANGED")
        data = self._run(["window", "list", "--pid", str(pid)])
        info = data.get("target_application_info")
        rows = data.get("windows")
        if (type(info) is not dict or info.get("pid") != pid
                or info.get("bundle_id") != bundle_id
                or type(rows) is not list or len(rows) > 256):
            raise AppUseRefused("NATIVE_WINDOWS_UNQUALIFIED")
        windows = []
        for row in rows:
            if type(row) is dict and type(row.get("window_id")) is int and row["window_id"] > 0:
                windows.append({
                    "target": NativeTarget(bundle_id, pid, process_start_identity_decimal,
                                           row["window_id"]).wire(),
                    "title": str(row.get("window_title", ""))[:1024],
                    "is_on_screen": row.get("is_on_screen") is True,
                    "is_frontmost": row.get("is_frontmost") is True,
                })
        return {"windows": windows,
                "inventory_complete": data.get("inventory_completeness") == "complete"}

    def validate_target(self, target: NativeTarget) -> None:
        if self.permissions().get("observation_ready") is not True:
            raise AppUseRefused("NATIVE_EXECUTION_CONTEXT_PERMISSION_UNAVAILABLE")
        result = self.windows(bundle_id=target.bundle_id, pid=target.pid,
            process_start_identity_decimal=target.process_start_identity_decimal)
        if sum(row["target"] == target.wire() for row in result["windows"]) != 1:
            raise AppUseRefused("NATIVE_WINDOW_CHANGED")

    def observe(self, target: NativeTarget) -> dict:
        self.validate_target(target)
        data = self._run(["see", "--pid", str(target.pid), "--window-id", str(target.window_id),
                         "--tree", "--no-screenshot", "--max-elements", "120",
                         "--max-children", "40", "--depth", "6", "--timeout", "8s"])
        snapshot = data.get("snapshot_id")
        elements = data.get("ui_elements")
        if (type(snapshot) is not str or not snapshot or snapshot == "latest"
                or type(elements) is not list or len(elements) > 120):
            raise AppUseRefused("NATIVE_OBSERVATION_UNQUALIFIED")
        self.validate_target(target)
        # The tree is untrusted app content. Do not return filesystem paths,
        # debug logs or image references outside the existing artifact owner.
        return {"snapshot_id": snapshot, "content": {
            "window_title": str(data.get("window_title", ""))[:1024],
            "is_dialog": data.get("is_dialog") is True,
            "ui_elements": elements,
            "truncation": data.get("truncation"),
        }}

    def dispatch(self, target: NativeTarget, snapshot_id: str, value: dict) -> dict:
        value = command(value)
        action, args = value["action"], value["arguments"]
        if action not in self.qualified_actions:
            raise AppUseRefused("NATIVE_ACTION_NOT_QUALIFIED")
        if action == "click_element":
            native = ["click", "--on", args["element_id"]]
        elif action == "type_text":
            # Peekaboo interprets backslash sequences; preserve literal text.
            native = ["type", "--text", args["text"].replace("\\", "\\\\")]
        else:
            native = ["press", args["key"]]
        native += ["--snapshot", snapshot_id, "--pid", str(target.pid),
                   "--window-id", str(target.window_id), "--input-strategy", "actionOnly"]
        result = self._run(native, effectful=True)
        return {"carrier": self.carrier, "native_result_sha256": digest(result),
                "native_acknowledged": True, "business_outcome_verified": False}
