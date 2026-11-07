"""Supervise the pinned Hermes child and restart it after a crash.

systemd --user is the outer supervisor (Restart=on-failure in the unit).
This loop is the inner one the acceptance test can kill without a host bus.
"""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import threading
import time

from .constants import HEALTH_SCHEMA, LOOPBACK_HOST, PINNED_UPSTREAM_SHA
from .egress import ROLE_PROXY_HOST
from .hermes_config import render_hermes_config
from .errors import RuntimeRefusal
from .gateway import Gateway, reserve_loopback_port
from .memory import HighWaterLog, read_rss_kib
from .profile import RuntimeProfile
from .registry import assert_registered_tools_exact, extension_tools_for
from .secrets import Secrets, child_env, assert_no_supervisor_notification_env
from .role_status_publisher import PUBLICATION_INTERVAL_SECONDS, RoleStatusPublisher

_UNSAFE = set(" \n\r\t\"'`$")


def _backend_health_ready(port: int, host: str = LOOPBACK_HOST) -> bool:
    """Check native Hermes health identity, not only a local HTTP status.

    Pinned Hermes /api/health includes ok and its booted Git commit. A
    different/unstamped executable or another loopback server returning 200
    must never be promoted to healthy, even if the child PID is still alive.
    No credential, redirect, public interface or model call is used.
    """
    if (isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535
            or host not in (LOOPBACK_HOST, *ROLE_PROXY_HOST.values())):
        return False
    conn = http.client.HTTPConnection(host, port, timeout=0.25)
    try:
        conn.request("GET", "/api/health")
        response = conn.getresponse()
        if response.status != 200:
            return False
        body = response.read(4097)
        if len(body) > 4096:
            return False
        identity = json.loads(body.decode("utf-8", errors="strict"))
        return (
            type(identity) is dict
            and identity.get("ok") is True
            and identity.get("commit") == PINNED_UPSTREAM_SHA
        )
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        conn.close()


def _safe_path(path: Path) -> str:
    text = str(path)
    if any(ch in text for ch in _UNSAFE):
        raise RuntimeRefusal("UNSAFE_PATH")
    return text


def build_tools_argv(hermes_bin: Path, role: str) -> list[str]:
    return [_safe_path(hermes_bin), "-p", role, "tools", "list", "--platform", "cli"]


def build_serve_argv(hermes_bin: Path, role: str, backend_port: int, host: str = LOOPBACK_HOST) -> list[str]:
    if isinstance(backend_port, bool) or not isinstance(backend_port, int):
        raise RuntimeRefusal("INVALID_BACKEND_PORT")
    if not 1024 <= backend_port <= 65535:
        raise RuntimeRefusal("INVALID_BACKEND_PORT")
    if host not in (LOOPBACK_HOST, ROLE_PROXY_HOST.get(role)):
        raise RuntimeRefusal("NON_LOOPBACK_BIND_REFUSED")
    argv = [
        _safe_path(hermes_bin),
        "-p",
        role,
        "serve",
        "--host",
        host,
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
        role_status_publisher: RoleStatusPublisher | None = None,
    ):
        self.profile = profile
        self.secrets = secrets
        self.hermes_bin = Path(hermes_bin)
        self.extra_child_env = extra_child_env or {}
        self.restart_count = 0
        self.child_starts = 0
        self.child_pid: int | None = None
        self._backend_ready = False
        self.failed = False
        self.refusal_code = ""
        self.gateway: Gateway | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._child: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self.memory: HighWaterLog | None = None
        self._role_status_publisher = role_status_publisher
        self._next_role_status_publication = 0.0

    def start(self) -> None:
        # Check native BYOK/alias policy before *any* Hermes subprocess,
        # including the tools-list census. A failed preflight starts nothing.
        self._model_child_env()
        if self._role_status_publisher is not None:
            self._publish_role_status_if_due(time.monotonic())
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
        self._thread = threading.Thread(target=self._loop_guarded, name="hermes-runtime-supervisor", daemon=True)
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
            backend_ready = running and self._backend_ready
            if self.failed:
                status = "failed"
            elif backend_ready:
                status = "ok"
            elif running:
                status = "starting"
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
                "backend_ready": backend_ready,
                # A verified pinned local HTTP health response is NOT a
                # provider-authenticated text turn or a Slack role delivery.
                # Until an authorized host attaches canonical proof, expose
                # those capabilities explicitly as unverified at all times.
                "provider_authenticated": False,
                "native_model_turn_verified": False,
                "network_egress_policy_verified": False,
                "slack_roundtrip_verified": False,
                "child_pid": self.child_pid,
                "memory_high_water_kib": 0 if self.memory is None else self.memory.high_water,
                "loopback": True,
                "gateway_host": self.profile.gateway_host,
                "allowlist": sorted(self.profile.tool_allowlist),
                "upstream_attested": False,
            }
        return (200 if status == "ok" else 503), payload

    def _env(self) -> dict[str, str]:
        # CLI/tool census receives no model provider credential.
        return child_env(self.secrets, home=self.profile.hermes_home, extra=self.extra_child_env)

    def _registry_env(self) -> dict[str, str]:
        """Tool discovery receives no dashboard, Slack or provider bearer.

        Keep the existing child-env validation for synthetic stub inputs, but
        pass only paths, locale and approved stub metadata to the census.
        """
        source = self._env()
        required = {"PATH", "HOME", "HERMES_HOME", "LANG"}
        return {
            key: value for key, value in source.items()
            if key in required or key.startswith("HERMES_STUB_")
        }

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
            # load_secrets historically defaults dashboard Basic-Auth password
            # to the gateway token. The model child receives that password;
            # refusing this alias prevents disclosure under a *different*
            # environment name. The operator must provision two real,
            # independently revocable credentials, not rely on the fallback.
            if self.secrets.dashboard_password == self.secrets.token:
                raise RuntimeRefusal("NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")
            from integrations.hermes_harness.native_model_credential import primary_model_env
            model_keys = primary_model_env(self.profile, self.secrets.values)
            # Slack bot authority must not travel to the model-serving child
            # under a different credential name, including dashboard Basic Auth
            # (which the native Hermes child necessarily receives).
            protected_values = {self.secrets.token, self.secrets.dashboard_password}
            slack_bot_token = self.secrets.values.get("HERMES_SLACK_BOT_TOKEN", "")
            if slack_bot_token:
                if slack_bot_token in protected_values:
                    raise RuntimeRefusal("NATIVE_SLACK_BOT_AUTH_ALIAS_REFUSED")
                protected_values.add(slack_bot_token)
            if any(value in protected_values for value in model_keys.values()):
                raise RuntimeRefusal("NATIVE_MODEL_KEY_REUSE_REFUSED")
            env.update(model_keys)
            # The model child may reach external HTTPS only through an
            # operator-enrolled role-private localhost CONNECT proxy. A
            # missing or malformed proxy refuses startup before subprocess.
            # Never copy an ambient shell HTTPS_PROXY to the child.
            from .egress import native_egress_child_env
            env.update(native_egress_child_env(self.profile.role, self.secrets.values))
        assert_no_supervisor_notification_env(env)
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
        if (self.profile.native_provider_id is None
                and raw == render_hermes_config(self.profile).encode("utf-8")):
            return None
        # The built-in WP1 package remains independent for non-integrated
        # installs; this optional consumer is loaded only for the specific
        # reviewed disabled native config.
        from integrations.hermes_harness.native_mcp import render_disarmed_native_config
        from integrations.hermes_steward.client import ALLOWED_TOOLS

        if self.profile.extension_allowlist:
            raise RuntimeRefusal("NATIVE_EXTENSION_NOT_INSTALLED")
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        allowed_native = {render_disarmed_native_byok(self.profile).encode("utf-8")}
        # An explicit persisted selection cannot downgrade to a legacy or
        # model-less config. Only selector-free historical profiles retain
        # the earlier source-compatible config forms.
        if self.profile.native_provider_id is None:
            allowed_native.add(render_disarmed_native_config(self.profile).encode("utf-8"))
        if raw not in allowed_native:
            raise RuntimeRefusal("RUNTIME_NATIVE_CONFIG_DRIFT")
        return {"mastermind_steward": tuple(ALLOWED_TOOLS)}

    def _check_registry(self) -> None:
        expected_disabled_mcp = self._expected_disabled_mcp()
        try:
            proc = subprocess.run(
                build_tools_argv(self.hermes_bin, self.profile.role),
                capture_output=True,
                env=self._registry_env(),
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

    def _loop_guarded(self) -> None:
        """Convert unexpected inner-loop exceptions into observable failure.

        Otherwise a daemon thread can die silently while the foreground
        supervisor stays alive indefinitely and systemd sees no failure.
        """
        try:
            self._loop()
            return
        except RuntimeRefusal as exc:
            code = exc.code
        except Exception:
            # Never log exception text: third-party exceptions can contain
            # credential material or full environment values.
            code = "RUNTIME_SUPERVISOR_EXCEPTION"
        with self._lock:
            child = self._child
            self.refusal_code = code
            self.failed = True
        if child is not None:
            try:
                _terminate(child)
            except (OSError, subprocess.SubprocessError):
                pass
        with self._lock:
            self._child = None
            self.child_pid = None
            self._backend_ready = False

    def _publish_role_status_if_due(self, now: float) -> None:
        # One due-time check in the incumbent loop, independent of the profile's
        # 0.01–300 second memory cadence. No timer, thread or cached document.
        if self._role_status_publisher is None or now < self._next_role_status_publication:
            return
        self._next_role_status_publication = now + PUBLICATION_INTERVAL_SECONDS
        try:
            self._role_status_publisher.publish()
        except Exception:
            # Optional status failure must not enter the child-failure path.
            pass

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
            port = self.profile.backend_port or reserve_loopback_port(self.profile.gateway_host)
            try:
                argv = build_serve_argv(self.hermes_bin, self.profile.role, port, self.profile.gateway_host)
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
                self._backend_ready = False
            next_memory_sample = 0.0
            poll_sec = min(0.25, self.profile.memory_sample_interval_sec)
            while not self._stop.is_set() and proc.poll() is None:
                backend_ready = _backend_health_ready(port, self.profile.gateway_host)
                with self._lock:
                    if self._child is proc:
                        self._backend_ready = backend_ready
                now = time.monotonic()
                if now >= next_memory_sample:
                    rss = read_rss_kib(proc.pid)
                    if rss is not None:
                        self.memory.record(proc.pid, rss)
                    next_memory_sample = now + self.profile.memory_sample_interval_sec
                self._publish_role_status_if_due(now)
                self._stop.wait(poll_sec)
            if self._stop.is_set():
                _terminate(proc)
                with self._lock:
                    self._child = None
                    self.child_pid = None
                    self._backend_ready = False
                return
            _reap(proc)
            with self._lock:
                self._child = None
                self.child_pid = None
                self._backend_ready = False
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
