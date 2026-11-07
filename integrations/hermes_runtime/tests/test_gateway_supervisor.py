"""Loopback binding, auth, kill/restart, and memory high-water."""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from integrations.hermes_runtime.constants import (  # noqa: E402
    DASHBOARD_PASSWORD_ENV,
    GATEWAY_TOKEN_ENV,
    PINNED_UPSTREAM_SHA,
    UPSTREAM_REPOSITORY,
)
from integrations.hermes_runtime.errors import RuntimeRefusal  # noqa: E402
from integrations.hermes_runtime.gateway import Gateway  # noqa: E402
from integrations.hermes_runtime.memory import HighWaterLog, parse_vm_rss_kib, read_rss_kib  # noqa: E402
from integrations.hermes_runtime.profile import load_profile  # noqa: E402
from integrations.hermes_runtime.secrets import clear_child_secret_env, load_secrets  # noqa: E402
from integrations.hermes_runtime.supervisor import ServiceRuntime, _backend_health_ready, build_serve_argv  # noqa: E402
from integrations.hermes_runtime.tests._support import (  # noqa: E402
    CENSUS,
    STUB,
    TOKEN,
    http_get,
    listening_addresses,
    profile_text,
    write_secrets,
)


class MemoryTests(unittest.TestCase):
    def test_high_water_is_monotonic_private_and_survives_reopen(self) -> None:
        path = self._dir() / "high-water.log"
        log = HighWaterLog(path)
        self.assertTrue(log.record(11, 100))
        self.assertFalse(log.record(11, 100))
        self.assertFalse(log.record(11, 90))
        self.assertTrue(log.record(11, 150))
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("high_water_kib="), 2)
        self.assertNotIn(TOKEN, text)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        reopened = HighWaterLog(path)
        self.assertEqual(reopened.high_water, 150)
        self.assertFalse(reopened.record(11, 140))
        self.assertEqual(path.read_text(encoding="utf-8").count("\n"), 2)

    def test_live_proc_rss_parses(self) -> None:
        rss = read_rss_kib(os.getpid())
        self.assertIsNotNone(rss)
        assert rss is not None
        self.assertGreater(rss, 0)
        self.assertEqual(parse_vm_rss_kib("Name:\tpython\nVmRSS:\t   185000 kB\n"), 185000)

    def _dir(self) -> Path:
        root = Path("/tmp/hermes-runtime-memory") / self.id().split(".")[-1]
        if root.exists():
            import shutil
            shutil.rmtree(root)
        root.mkdir(parents=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        return root


class GatewaySupervisorTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_child_secret_env()
        os.environ.pop("SENTINEL_SHOULD_NOT_LEAK", None)

    def test_loopback_only_binding_requires_auth(self) -> None:
        before = set(listening_addresses_for_any())
        with self.assertRaises(RuntimeRefusal) as ctx:
            Gateway("0.0.0.0", 0, TOKEN, lambda: (200, {"status": "ok"}))
        self.assertEqual(ctx.exception.code, "NON_LOOPBACK_BIND_REFUSED")
        self.assertEqual(set(listening_addresses_for_any()), before)

        runtime = self._start()
        try:
            port = runtime.gateway.port
            self.assertEqual(runtime.gateway.host, "127.0.0.1")
            self.assertEqual(listening_addresses(port), ["0100007F"])
            health = f"http://127.0.0.1:{port}/api/health"
            self.assertEqual(http_get(health)[0], 401)
            self.assertNotIn(TOKEN.encode(), http_get(health, "wrong-token-value-xxxx")[1])
            # Readiness is asynchronous: prove the backend answers before
            # requiring HTTP 200; a live PID alone must remain HTTP 503.
            code, body = self._wait_health(runtime)
            self.assertEqual(code, 200)
            payload = json.loads(body)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["backend_ready"])
            # Local pinned backend health is not a remote model inference
            # or role Slack roundtrip, even while this endpoint returns 200.
            self.assertFalse(payload["provider_authenticated"])
            self.assertFalse(payload["native_model_turn_verified"])
            self.assertFalse(payload["network_egress_policy_verified"])
            self.assertFalse(payload["slack_roundtrip_verified"])
            self.assertEqual(payload["pinned_sha"], PINNED_UPSTREAM_SHA)
            self.assertEqual(payload["allowlist"], ["clarify"])
            self.assertTrue(payload["loopback"])
            self.assertNotIn(TOKEN.encode(), body)
            dash_code, dash = http_get(f"http://127.0.0.1:{port}/", TOKEN)
            self.assertEqual(dash_code, 200)
            self.assertIn(b"loopback=127.0.0.1", dash)
            query_code, query_body = http_get(f"http://127.0.0.1:{port}/api/health?access_token={TOKEN}", TOKEN)
            self.assertEqual(query_code, 400)
            self.assertNotIn(TOKEN.encode(), query_body)
            argv = build_serve_argv(STUB, "mmsecretary", 8766)
            self.assertIn("127.0.0.1", argv)
            self.assertNotIn("0.0.0.0", argv)
            self.assertNotIn("--insecure", argv)
        finally:
            runtime.stop()

    def test_two_role_loopback_aliases_preserve_gateway_auth_and_serve_binding(self) -> None:
        for role, own, sibling in (
            ("mmsecretary", "127.0.0.2", "127.0.0.3"),
            ("mmmeta", "127.0.0.3", "127.0.0.2"),
        ):
            with self.subTest(role=role):
                gateway = Gateway(own, 0, TOKEN, lambda: (200, {"status": "ok"}))
                try:
                    url = f"http://{own}:{gateway.port}/api/health"
                    self.assertEqual(http_get(url)[0], 401)
                    self.assertEqual(http_get(url, TOKEN)[0], 200)
                    self.assertEqual(gateway.host, own)
                    argv = build_serve_argv(STUB, role, 8766, own)
                    self.assertEqual(argv[argv.index("--host") + 1], own)
                    with self.assertRaises(RuntimeRefusal):
                        build_serve_argv(STUB, role, 8766, sibling)
                finally:
                    gateway.close()

    def test_live_pid_without_responsive_backend_never_returns_healthy(self) -> None:
        for mode in ("silent", "unhealthy"):
            with self.subTest(mode=mode):
                runtime = self._start(stub_mode=mode)
                try:
                    deadline = time.time() + 4
                    while time.time() < deadline and runtime.child_pid is None:
                        time.sleep(0.02)
                    self.assertIsNotNone(runtime.child_pid)
                    # Both cases keep the process alive; one has no socket,
                    # the other returns non-200 /api/health.
                    time.sleep(0.15)
                    code, body = http_get(
                        f"http://127.0.0.1:{runtime.gateway.port}/api/health",
                        TOKEN,
                    )
                    payload = json.loads(body)
                    self.assertEqual(code, 503)
                    self.assertTrue(payload["child_running"])
                    self.assertFalse(payload["backend_ready"])
                    self.assertEqual(payload["status"], "starting")
                finally:
                    runtime.stop()

    def test_http_200_from_wrong_or_unidentified_backend_is_unready(self) -> None:
        # A healthy-looking local HTTP listener is not Hermes source identity.
        # Unpinned binaries, malformed JSON, and oversized bodies fail closed.
        for mode in ("wrong-commit", "missing-commit", "bad-json", "oversized"):
            with self.subTest(mode=mode):
                runtime = self._start(stub_mode=mode)
                try:
                    deadline = time.time() + 4
                    while time.time() < deadline and runtime.child_pid is None:
                        time.sleep(0.02)
                    self.assertIsNotNone(runtime.child_pid)
                    time.sleep(0.2)
                    code, body = http_get(
                        f"http://127.0.0.1:{runtime.gateway.port}/api/health", TOKEN,
                    )
                    payload = json.loads(body)
                    self.assertEqual(code, 503)
                    self.assertTrue(payload["child_running"])
                    self.assertFalse(payload["backend_ready"])
                    self.assertEqual(payload["status"], "starting")
                finally:
                    runtime.stop()

    def test_backend_probe_is_loopback_only_and_refuses_invalid_ports(self) -> None:
        for port in (0, -1, True, 65536, "7000", None):
            with self.subTest(port=port):
                self.assertFalse(_backend_health_ready(port))

    def test_kill_and_restart_recovery(self) -> None:
        runtime = self._start()
        try:
            first = self._wait_ready(runtime)
            self.assertEqual(first["argv"][first["argv"].index("--host") + 1], "127.0.0.1")
            self.assertNotIn("SENTINEL_SHOULD_NOT_LEAK", first["env_keys"])
            self.assertNotIn(GATEWAY_TOKEN_ENV, first["env_keys"])
            self.assertNotIn("ZAI_API_KEY", first["env_keys"])
            self.assertIn(DASHBOARD_PASSWORD_ENV, first["env_keys"])
            os.kill(first["pid"], 9)
            second = self._wait_ready(runtime, previous=first["pid"])
            self.assertNotEqual(second["pid"], first["pid"])
            code, body = self._wait_health(runtime)
            payload = json.loads(body)
            self.assertEqual(code, 200)
            self.assertGreaterEqual(payload["restart_count"], 1)
            self.assertGreater(payload["memory_high_water_kib"], 0)
            log = runtime.profile.state_dir / "memory" / "high-water.log"
            self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
            self.assertNotIn(TOKEN, log.read_text(encoding="utf-8"))
        finally:
            runtime.stop()

    def test_crash_loop_stops_at_the_burst(self) -> None:
        runtime = self._start(burst=3, stub_mode="exit")
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not runtime.failed:
                time.sleep(0.02)
            self.assertTrue(runtime.failed)
            self.assertEqual(runtime.child_starts, 3)
            code, _body = http_get(
                f"http://127.0.0.1:{runtime.gateway.port}/api/health", TOKEN,
            )
            self.assertEqual(code, 503)
        finally:
            runtime.stop()

    def test_profile_fixture_is_private_before_first_write(self) -> None:
        real_open = os.open
        opened = []

        def observe_open(path, flags, mode=0o777, **kwargs):
            fd = real_open(path, flags, mode, **kwargs)
            if Path(path).name == "profile.yaml":
                info = os.fstat(fd)
                opened.append((stat.S_IMODE(info.st_mode), info.st_size))
            return fd

        previous_umask = os.umask(0)
        try:
            with mock.patch.object(os, "open", side_effect=observe_open):
                with mock.patch.object(ServiceRuntime, "start"):
                    runtime = self._start()
        finally:
            os.umask(previous_umask)
        profile_path = runtime.profile.state_dir.parent / "profile.yaml"
        self.assertEqual(opened, [(0o600, 0)])
        self.assertEqual(stat.S_IMODE(profile_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(profile_path.parent.stat().st_mode), 0o700)
        text = profile_path.read_text(encoding="utf-8")
        self.assertIn(f"secrets_file: {profile_path.parent / 'secrets.env'}\n", text)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("not-a-real-provider-key", text)

    def test_profile_fixture_refuses_existing_file_and_symlink(self) -> None:
        real_temporary = tempfile.TemporaryDirectory
        for kind in ("file", "symlink"):
            with self.subTest(kind=kind):
                paths = {}

                def occupied_directory(*args, **kwargs):
                    temporary = real_temporary(*args, **kwargs)
                    root = Path(temporary.name)
                    target = root / "keep"
                    target.write_text("preserve-fixture-target\n", encoding="utf-8")
                    profile_path = root / "profile.yaml"
                    if kind == "symlink":
                        profile_path.symlink_to(target)
                    else:
                        profile_path.write_text("preserve-existing-profile\n", encoding="utf-8")
                    paths.update(target=target, profile=profile_path)
                    return temporary

                with mock.patch.object(tempfile, "TemporaryDirectory", side_effect=occupied_directory):
                    with mock.patch.object(ServiceRuntime, "start") as start:
                        with self.assertRaises(FileExistsError):
                            self._start()
                start.assert_not_called()
                self.assertEqual(paths["target"].read_text(encoding="utf-8"), "preserve-fixture-target\n")
                if kind == "symlink":
                    self.assertTrue(paths["profile"].is_symlink())
                else:
                    self.assertEqual(paths["profile"].read_text(encoding="utf-8"), "preserve-existing-profile\n")

    def _start(self, *, burst: int = 5, stub_mode: str | None = None) -> ServiceRuntime:
        os.chmod(STUB, 0o755)
        os.environ["SENTINEL_SHOULD_NOT_LEAK"] = "1"
        temporary = tempfile.TemporaryDirectory(prefix="hermes-runtime-gateway-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        state = root / "state"
        state.mkdir()
        home = root / "home"
        home.mkdir()
        secrets = root / "secrets.env"
        write_secrets(secrets, extra="ZAI_API_KEY=not-a-real-provider-key\nUNREGISTERED_SECRET=stay-on-disk\n")
        profile_path = root / "profile.yaml"
        fd = os.open(profile_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(profile_text(
                state=state,
                secrets=secrets,
                sha=PINNED_UPSTREAM_SHA,
                repository=UPSTREAM_REPOSITORY,
                burst=burst,
            ))
        profile = load_profile(profile_path, hermes_home=home)
        ready = root / "ready.json"
        extra = {"HERMES_STUB_TOOLS": str(CENSUS), "HERMES_STUB_READY": str(ready),
                 "HERMES_STUB_COMMIT": PINNED_UPSTREAM_SHA}
        if stub_mode:
            extra["HERMES_STUB_MODE"] = stub_mode
            extra["HERMES_STUB_COUNT"] = str(root / "count")
        runtime = ServiceRuntime(
            profile,
            load_secrets(secrets),
            STUB,
            extra_child_env=extra,
        )
        runtime.start()
        self._ready_path = ready
        return runtime

    def _wait_health(self, runtime: ServiceRuntime) -> tuple[int, bytes]:
        assert runtime.gateway is not None
        url = f"http://127.0.0.1:{runtime.gateway.port}/api/health"
        deadline = time.time() + 5
        last = (0, b"")
        while time.time() < deadline:
            last = http_get(url, TOKEN)
            if last[0] == 200:
                return last
            time.sleep(0.02)
        raise AssertionError(last)

    def _wait_ready(self, runtime: ServiceRuntime, previous: int | None = None) -> dict:
        self._wait_health(runtime)
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._ready_path.exists():
                payload = json.loads(self._ready_path.read_text(encoding="utf-8"))
                if previous is None or payload["pid"] != previous:
                    return payload
            time.sleep(0.02)
        raise AssertionError("child did not become ready")


def listening_addresses_for_any() -> list[int]:
    found: list[int] = []
    path = Path("/proc/net/tcp")
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split()
        local, state = parts[1], parts[3]
        if state != "0A":
            continue
        ip, hexport = local.split(":")
        if ip == "00000000":
            found.append(int(hexport, 16))
    return found


if __name__ == "__main__":
    unittest.main()
