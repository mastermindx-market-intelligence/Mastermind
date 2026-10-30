"""Supervise the pinned Hermes child and restart it after a crash.

systemd --user is the outer supervisor (Restart=on-failure in the unit).
This loop is the inner one the acceptance test can kill without a host bus.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import stat
import subprocess
import threading

from .constants import HEALTH_SCHEMA, LOOPBACK_HOST
from .hermes_config import render_hermes_config
from .errors import RuntimeRefusal
from .gateway import Gateway, reserve_loopback_port
from .memory import HighWaterLog, read_rss_kib
from .profile import RuntimeProfile
from .registry import assert_registered_tools_exact, extension_tools_for
from .secrets import Secrets, child_env

_UNSAFE = set(" \n\r\t\"'`$")


def _safe_path(path: Path) -> str:
    text = str(path)
    if any(ch in text for ch in _UNSAFE):
        raise RuntimeRefusal("UNSAFE_PATH")
    return text


def build_tools_argv(hermes_bin: Path, role: str) -> list[str]:
    return [_safe_path(hermes_bin), "-p", role, "tools", "list", "--platform", "cli"]


def build_serve_argv(hermes_bin: Path, role: str, backend_port: int) -> list[str]:
    if isinstance(backend_port, bool) or not isinstance(backend_port, int):
        raise RuntimeRefusal("INVALID_BACKEND_PORT")
    if not 1024 <= backend_port <= 65535:
        raise RuntimeRefusal("INVALID_BACKEND_PORT")
    argv = [
        _safe_path(hermes_bin),
        "-p",
        role,
        "serve",
        "--host",
        LOOPBACK_HOST,
        "--port",
        str(backend_port),
        "--skip-build",
        "--isolated",
    ]
    if "0.0.0.0" in argv or "--insecure" in argv:
        raise RuntimeRefusal("NON_LOOPBACK_BIND_REFUSED")
    return argv


class ServiceRuntime:
    def __init__(
        self,
        profile: RuntimeProfile,
        secrets: Secrets,
        hermes_bin: Path,
        *,
        extra_child_env: dict[str, str] | None = None,
    ):
        self.profile = profile
        self.secrets = secrets
        self.hermes_bin = Path(hermes_bin)
        self.extra_child_env = extra_child_env or {}
        self.restart_count = 0
        self.child_starts = 0
        self.child_pid: int | None = None
        self.failed = False
        self.refusal_code = ""
        self.gateway: Gateway | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._child: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self.memory: HighWaterLog | None = None

    def start(self) -> None:
        self._check_registry()
        self.profile.hermes_home.mkdir(parents=True, exist_ok=True)
        os.chmod(self.profile.hermes_home, 0o700)
        self.memory = HighWaterLog(self.profile.state_dir / "memory" / "high-water.log")
        self.gateway = Gateway(
            self.profile.gateway_host,
            self.profile.gateway_port,
            self.secrets.token,
            self.health_snapshot,
        )
        self._thread = threading.Thread(target=self._loop, name="hermes-runtime-supervisor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            child = self._child
        if child is not None:
            _terminate(child)
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self.gateway is not None:
            self.gateway.close()
            self.gateway = None

    def health_snapshot(self) -> tuple[int, dict]:
        with self._lock:
            child = self._child
            running = child is not None and child.poll() is None
            if self.failed:
                status = "failed"
            elif running:
                status = "ok"
            else:
                status = "restarting"
            payload = {
                "schema": HEALTH_SCHEMA,
                "status": status,
                "pinned_sha": self.profile.sha,
                "role": self.profile.role,
                "restart_count": self.restart_count,
                "child_starts": self.child_starts,
                "child_running": running,
                "child_pid": self.child_pid,
                "memory_high_water_kib": 0 if self.memory is None else self.memory.high_water,
                "loopback": True,
                "gateway_host": LOOPBACK_HOST,
                "allowlist": sorted(self.profile.tool_allowlist),
                "upstream_attested": False,
            }
        return (200 if status == "ok" else 503), payload

    def _env(self) -> dict[str, str]:
        # CLI/tool census receives no model provider credential.
        return child_env(self.secrets, home=self.profile.hermes_home, extra=self.extra_child_env)

    def _model_child_env(self) -> dict[str, str]:
        """Forward only the reviewed primary credential to a pinned BYOK child.

        The receiving native config must be exact, owner-private, and have
        its Steward MCP disabled before any key is retrieved or forwarded.
        Legacy WP1 and plain disabled-MCP profiles receive no model key.
        """
        self._expected_disabled_mcp()
        native = self.profile.hermes_home / "profiles" / self.profile.role / "config.yaml"
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        env = self._env()
        if native.is_file() and native.read_bytes() == render_disarmed_native_byok(self.profile).encode("utf-8"):
            from integrations.hermes_harness.native_model_credential import primary_model_env
            env.update(primary_model_env(self.profile, self.secrets.values))
        return env

    def _expected_disabled_mcp(self) -> dict[str, tuple[str, ...]] | None:
        """Require exact on-disk native config before trusting any CLI summary.

        A displayed MCP summary is not a connection or admission receipt.
        The only accepted additional config is the reviewed, *disabled*
        Steward source. No unknown or enabled MCP/server plugin is allowed.
        """
        path = self.profile.hermes_home / "profiles" / self.profile.role / "config.yaml"
        if not path.exists() and not path.is_symlink():
            if (self.profile.state_dir / "install-manifest.json").exists():
                raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_MISSING")
            # Uninstalled stub-runtime tests use a temporary profile without
            # a native config. Real installs must carry that config.
            return None
        if path.is_symlink():
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_SYMLINK")
        try:
            info = path.stat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.geteuid() or info.st_nlink != 1):
                raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_UNSAFE")
            if info.st_size > 64 * 1024:
                raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_TOO_LARGE")
            raw = path.read_bytes()
        except OSError:
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_UNAVAILABLE") from None
        if raw == render_hermes_config(self.profile).encode("utf-8"):
            return None
        # The built-in WP1 package remains independent for non-integrated
        # installs; this optional consumer is loaded only for the specific
        # reviewed disabled native config.
        from integrations.hermes_harness.native_mcp import render_disarmed_native_config
        from integrations.hermes_steward.client import ALLOWED_TOOLS

        if self.profile.extension_allowlist:
            raise RuntimeRefusal("NATIVE_EXTENSION_NOT_INSTALLED")
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        if raw not in {
            render_disarmed_native_config(self.profile).encode("utf-8"),
            render_disarmed_native_byok(self.profile).encode("utf-8"),
        }:
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_DRIFT")
        return {"mastermind_steward": tuple(ALLOWED_TOOLS)}

    def _check_registry(self) -> None:
        expected_disabled_mcp = self._expected_disabled_mcp()
        try:
            proc = subprocess.run(
                build_tools_argv(self.hermes_bin, self.profile.role),
                capture_output=True,
                env=self._env(),
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeRefusal("TOOLS_LIST_TIMEOUT") from None
        try:
            text = proc.stdout.decode("utf-8", errors="strict")
        except UnicodeError:
            raise RuntimeRefusal("TOOLS_LIST_NOT_UTF8") from None
        assert_registered_tools_exact(
            text,
            proc.stderr,
            self.profile.tool_allowlist,
            extension_tools_for(self.profile),
            expected_disabled_mcp=expected_disabled_mcp,
        )
        if proc.returncode != 0:
            raise RuntimeRefusal("TOOLS_LIST_FAILED")

    def _loop(self) -> None:
        assert self.memory is not None
        while not self._stop.is_set():
            if self.child_starts >= self.profile.start_limit_burst:
                self.failed = True
                return
            if self.child_starts > 0:
                try:
                    self._check_registry()
                except RuntimeRefusal as exc:
                    self.refusal_code = exc.code
                    self.failed = True
                    return
            self.child_starts += 1
            port = self.profile.backend_port or reserve_loopback_port()
            try:
                argv = build_serve_argv(self.hermes_bin, self.profile.role, port)
            except RuntimeRefusal as exc:
                self.refusal_code = exc.code
                self.failed = True
                return
            try:
                model_child_env = self._model_child_env()
            except RuntimeRefusal as exc:
                self.refusal_code = exc.code
                self.failed = True
                return
            proc = subprocess.Popen(
                argv,
                env=model_child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            with self._lock:
                self._child = proc
                self.child_pid = proc.pid
            while not self._stop.is_set() and proc.poll() is None:
                rss = read_rss_kib(proc.pid)
                if rss is not None:
                    self.memory.record(proc.pid, rss)
                self._stop.wait(self.profile.memory_sample_interval_sec)
            if self._stop.is_set():
                _terminate(proc)
                with self._lock:
                    self._child = None
                return
            _reap(proc)
            with self._lock:
                self._child = None
                self.child_pid = None
                self.restart_count += 1
            if self.child_starts >= self.profile.start_limit_burst:
                self.failed = True
                return
            if self._stop.wait(self.profile.restart_sec):
                return


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)


def _reap(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        return
    proc.wait(timeout=1)
