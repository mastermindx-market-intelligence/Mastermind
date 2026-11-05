"""Offline boot of the integrated harness. No Slack writes, no live network, no admissions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_harness.doctor import doctor, format_doctor  # noqa: E402
from integrations.hermes_harness.shadow_gate import assert_may_leave_shadow  # noqa: E402
from integrations.hermes_runtime.errors import RuntimeRefusal  # noqa: E402
from integrations.hermes_harness.extensions import extension_names_for  # noqa: E402
from integrations.hermes_harness.stack import boot_stack  # noqa: E402
from integrations.hermes_harness.tick import FIXTURE, routine_tick  # noqa: E402
from integrations.hermes_models.contract import PROVIDERS  # noqa: E402
from integrations.hermes_models.tests.support import ScriptedTransport, ok_body  # noqa: E402
from integrations.hermes_models.client import CompletionRequest, HermesModelClient  # noqa: E402
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA  # noqa: E402
from integrations.hermes_runtime.secrets import clear_child_secret_env  # noqa: E402
from integrations.hermes_runtime.registry import clear_extension_tools  # noqa: E402
from integrations.hermes_runtime.tests._support import TOKEN, http_get, write_secrets  # noqa: E402
from integrations.hermes_delegate.admission import InertExecutiveAdmission  # noqa: E402
from integrations.hermes_delegate.bridge import Bridge  # noqa: E402

CTL = ROOT / "integrations" / "hermes_harness" / "hermesctl"
STUB = ROOT / "integrations" / "hermes_runtime" / "tests" / "fixtures" / "hermes_stub.py"
EXPECTED = Path(__file__).resolve().parent / "expected" / "ping_scan.jsonl"
SECRET = "offline-model-key"


class CountingAdmission(InertExecutiveAdmission):
    def __init__(self) -> None:
        self.calls = []
        self.admitted = 0

    def admit(self, submission):
        self.calls.append(dict(submission))
        decision = super().admit(submission)
        if decision.get("outcome") == "ADMITTED":
            self.admitted += 1
        return decision


class NetworkGuard:
    def __init__(self) -> None:
        self.blocked: list[str] = []
        self._saved = None

    def __enter__(self):
        self._saved = (
            socket.socket.connect,
            socket.socket.connect_ex,
            socket.create_connection,
        )
        real_connect, real_connect_ex, real_create = self._saved

        def check(address):
            host = address[0] if isinstance(address, tuple) else str(address)
            if host not in {"127.0.0.1", "::1", "localhost"}:
                self.blocked.append(host)
                raise AssertionError(f"live network call to {host}")

        def connect(sock, address):
            check(address)
            return real_connect(sock, address)

        def connect_ex(sock, address):
            check(address)
            return real_connect_ex(sock, address)

        def create_connection(address, *args, **kwargs):
            check(address)
            return real_create(address, *args, **kwargs)

        socket.socket.connect = connect
        socket.socket.connect_ex = connect_ex
        socket.create_connection = create_connection
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._saved is not None:
            socket.socket.connect, socket.socket.connect_ex, socket.create_connection = self._saved
        return False


class HarnessEndToEnd(unittest.TestCase):
    def tearDown(self) -> None:
        clear_extension_tools()
        clear_child_secret_env()

    def test_stack_boot_and_one_routine_tick(self) -> None:
        os.chmod(STUB, 0o755)
        os.chmod(CTL, 0o755)
        root = Path("/tmp/hermes-harness-e2e")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        secrets = root / "secrets.env"
        write_secrets(secrets)
        output = root / "would-decisions.jsonl"
        admission = CountingAdmission()
        saved_bot = os.environ.pop("HERMES_SLACK_BOT_USER_ID", None)
        self.addCleanup(lambda: saved_bot is not None and os.environ.__setitem__("HERMES_SLACK_BOT_USER_ID", saved_bot))
        with NetworkGuard() as guard:
            stack = boot_stack(root=root / "boot", secrets_file=secrets, hermes_bin=STUB)
            try:
                self._assert_boot(stack, secrets)
                self._assert_mock_turn(root / "meter")
                tick = routine_tick(
                    mode="ping_scan",
                    fixture=FIXTURE,
                    output=output,
                    bridge=Bridge(admission),
                )
            finally:
                stack.close()
        self.assertEqual(guard.blocked, [])
        self.assertEqual(tick["admitted"], 0)
        self.assertEqual(admission.admitted, 0)
        self.assertGreater(len(admission.calls), 0)
        self.assertEqual(tick["slack_methods"], ["conversations_history", "conversations_replies"])
        text = output.read_text(encoding="utf-8")
        self.assertNotIn("xoxb-not-a-real-token", text)
        self.assertNotIn("chat_postMessage", text)
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["would_post"] is False for row in rows))
        placements = [row for row in rows if row["decision"] == "PLACE_ON_TITLED_WORKER"]
        self.assertGreaterEqual(len(placements), 1)
        for row in placements:
            self.assertEqual(row["delegation"]["tool"], "mmx_delegate")
            self.assertEqual(row["delegation"]["state"], "REFUSED")
            self.assertEqual(row["delegation"]["reason"], "EXECUTIVE_ADMISSION_NOT_BOUND")
            self.assertFalse(row["delegation"]["live_submit"])
            self.assertFalse(row["delegation"]["admitted"])
        for row in rows:
            if row["decision"] != "PLACE_ON_TITLED_WORKER":
                self.assertIsNone(row["delegation"])
        if os.environ.get("HERMES_WRITE_EXPECTED") == "1":
            EXPECTED.parent.mkdir(parents=True, exist_ok=True)
            EXPECTED.write_text(text, encoding="utf-8")
        self.assertEqual(text, EXPECTED.read_text(encoding="utf-8"))
        again = routine_tick(
            mode="ping_scan",
            fixture=FIXTURE,
            output=output,
            bridge=Bridge(admission),
        )
        self.assertEqual(again["count"], 0)
        self.assertEqual(again["admitted"], 0)
        self.assertEqual(output.read_text(encoding="utf-8"), text)

    def test_doctor_lists_every_missing_pointer_on_a_clean_host(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            report = doctor(environ={}, home=Path(raw), systemd_user=False, upstream_attested=False)
        self.assertEqual(report["status"], "MISSING")
        self.assertEqual(report["missing"], _CLEAN_MISSING)
        rendered = format_doctor(report)
        self.assertIn("schema: mastermind.hermes_harness.doctor.v1", rendered)
        self.assertNotIn("offline-model-key", rendered)
        self.assertNotIn("local-test-gateway-token", rendered)
        for item in _CLEAN_MISSING:
            self.assertIn(f"- {item}", rendered)

    def test_doctor_drops_one_agents_slack_pair_when_that_file_has_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            write_secrets(
                home / ".config" / "hermes-runtime" / "mmsecretary.secrets.env",
                extra=(
                    "HERMES_SLACK_BOT_USER_ID=UHERMESSELF1\n"
                    "HERMES_SLACK_BOT_TOKEN=not-a-placeholder-token\n"
                ),
            )
            report = doctor(environ={}, home=home, systemd_user=False, upstream_attested=False)
        rendered = format_doctor(report)
        self.assertNotIn("credential_file:mmsecretary.secrets.env", report["missing"])
        self.assertNotIn("id:hermes-secretary:HERMES_SLACK_BOT_USER_ID", report["missing"])
        self.assertNotIn("credential:hermes-secretary:HERMES_SLACK_BOT_TOKEN", report["missing"])
        self.assertIn("credential_file:mmmeta.secrets.env", report["missing"])
        self.assertIn("id:hermes-metaceo:HERMES_SLACK_BOT_USER_ID", report["missing"])
        self.assertIn("credential:hermes-metaceo:HERMES_SLACK_BOT_TOKEN", report["missing"])
        self.assertNotIn("not-a-placeholder-token", rendered)
        self.assertNotIn("UHERMESSELF1", rendered)
        self.assertNotIn(TOKEN, rendered)

    def test_doctor_marks_a_non_list_agent_roster_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            roster = home / "roster.json"
            roster.write_text('{"hermes_agents": {"name": "hermes-secretary"}}\n', encoding="utf-8")
            report = doctor(
                environ={},
                home=home,
                systemd_user=False,
                upstream_attested=False,
                roster_path=roster,
            )
        self.assertEqual(report["status"], "MISSING")
        self.assertIn("config:hermes_agents:invalid", report["missing"])
        for row in (
            "id:hermes-secretary:HERMES_SLACK_BOT_USER_ID",
            "credential:hermes-secretary:HERMES_SLACK_BOT_TOKEN",
            "id:hermes-metaceo:HERMES_SLACK_BOT_USER_ID",
            "credential:hermes-metaceo:HERMES_SLACK_BOT_TOKEN",
        ):
            self.assertNotIn(row, report["missing"])
        rendered = format_doctor(report)
        self.assertIn("- config:hermes_agents:invalid", rendered)

    def test_harness_refuses_to_leave_shadow_without_a_bot_user_id(self) -> None:
        with self.assertRaises(RuntimeRefusal) as caught:
            assert_may_leave_shadow({})
        self.assertEqual(caught.exception.code, "SHADOW_ID_REQUIRED")
        with self.assertRaises(RuntimeRefusal):
            assert_may_leave_shadow({"HERMES_SLACK_BOT_USER_ID": "not-an-id"})
        self.assertEqual(
            assert_may_leave_shadow({"HERMES_SLACK_BOT_USER_ID": "UHERMESSELF1"}),
            "UHERMESSELF1",
        )

    def test_install_status_uninstall_and_cli(self) -> None:
        os.chmod(STUB, 0o755)
        os.chmod(CTL, 0o755)
        temporary = tempfile.TemporaryDirectory(prefix="hermes-harness-install-")
        self.addCleanup(temporary.cleanup)
        # Unique test custody; resolve macOS /tmp -> /private/tmp once so the
        # exact EnvironmentFile assertion remains meaningful on every host.
        root = Path(temporary.name).resolve()
        state = root / "state"
        unit = root / "config" / "systemd" / "user"
        unit.mkdir(parents=True)
        secrets = root / "secrets.env"
        write_secrets(secrets)
        upstream = root / "upstream"
        upstream.mkdir()
        (upstream / "FIXTURE_UPSTREAM").write_text("fixture\n", encoding="utf-8")
        installed = self._ctl(
            "install",
            "--role", "mmsecretary",
            "--state", str(state),
            "--systemd-user-dir", str(unit),
            "--secrets-file", str(secrets),
            "--hermes-bin", str(STUB),
            "--upstream-source", str(upstream),
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        payload = json.loads(installed.stdout)
        self.assertEqual(payload["status"], "INSTALLED")
        self.assertEqual(payload["overlay_chain"][0], "byteplus-modelark.glm-5.3-flash")
        self.assertEqual(payload["overlay_chain"][-1], "cursor-pool")
        self.assertEqual(payload["vision_chain"], ["minimax.attended", "cursor-pool"])
        overlay = (state / "current" / "hermes-home" / "provider-overlay.yaml").read_text(encoding="utf-8")
        self.assertIn("glm-5-3-flash-260828", overlay)
        self.assertIn("MiniMax-M3", overlay)
        self.assertIn("enabled: false", overlay)
        self.assertNotIn("api_key:", overlay.lower())
        profile_text = (state / "current" / "profile.yaml").read_text(encoding="utf-8")
        # Intended Python shadow extension names are NOT Hermes-native tools.
        for name in extension_names_for("mmsecretary"):
            self.assertNotIn(f"- {name}", profile_text)
        self.assertIn("- clarify\n", profile_text)
        self.assertNotIn("- delegation\n", profile_text)
        self.assertNotIn("- skills\n", profile_text)
        unit_text = (unit / "hermes-runtime-mmsecretary.service").read_text(encoding="utf-8")
        self.assertNotIn("AF_INET6", unit_text)
        self.assertNotIn(TOKEN, unit_text)
        self.assertIn(f"EnvironmentFile={secrets.resolve()}\n", unit_text)
        self.assertEqual(unit_text.count("EnvironmentFile="), 1)
        status = self._ctl("status", "--state", str(state))
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["status"], "INSTALLED")
        shadow_out = root / "shadow.jsonl"
        saved_bot = os.environ.pop("HERMES_SLACK_BOT_USER_ID", None)
        self.addCleanup(lambda: saved_bot is not None and os.environ.__setitem__("HERMES_SLACK_BOT_USER_ID", saved_bot))
        shadow = self._ctl(
            "shadow-run",
            "--fixture", str(FIXTURE),
            "--output", str(shadow_out),
        )
        self.assertEqual(shadow.returncode, 0, shadow.stderr)
        body = json.loads(shadow.stdout)
        self.assertEqual(body["count"], 12)
        self.assertEqual(body["admitted"], 0)
        self.assertFalse(body["would_post"])
        posts = root / "posts.json"
        posts.write_text("[]\n", encoding="utf-8")
        parity = self._ctl(
            "parity-check",
            "--decisions", str(shadow_out),
            "--posts", str(posts),
            "--start", "1761410000.000000",
            "--end", "1761420000.000000",
        )
        self.assertEqual(parity.returncode, 0, parity.stderr)
        report = json.loads(parity.stdout)
        self.assertIn("withheld", report)
        self.assertIn("shadow_only", report)
        removed = self._ctl(
            "uninstall",
            "--state", str(state),
            "--systemd-user-dir", str(unit),
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(json.loads(removed.stdout)["status"], "UNINSTALLED")
        self.assertTrue(secrets.is_file())
        self.assertEqual(stat.S_IMODE(secrets.stat().st_mode), 0o600)
        self.assertFalse(state.exists())

    def _assert_boot(self, stack, secrets: Path) -> None:
        runtime = stack.runtime
        self.assertEqual(runtime.gateway.host, "127.0.0.1")
        code, body = http_get(f"http://127.0.0.1:{runtime.gateway.port}/api/health", TOKEN)
        self.assertEqual(code, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["pinned_sha"], PINNED_UPSTREAM_SHA)
        self.assertEqual(set(payload["allowlist"]), {"clarify"} | set(extension_names_for("mmsecretary")))
        self.assertNotIn("delegation", payload["allowlist"])
        self.assertNotIn("skills", payload["allowlist"])
        self.assertNotIn("terminal", payload["allowlist"])
        env_keys = stack.ready["env_keys"]
        self.assertNotIn("HERMES_GATEWAY_TOKEN", env_keys)
        self.assertNotIn(TOKEN, json.dumps(stack.ready))
        self.assertEqual(stack.chains["mmsecretary"][0], "byteplus-modelark.glm-5.3-flash")
        self.assertEqual(stack.chains["mmsecretary"][-1], "cursor-pool")
        self.assertEqual(stack.chains["mmmeta"], ("zai.glm-5.3", "cursor-pool"))
        self.assertEqual(stack.chains["vision"], ("minimax.attended", "cursor-pool"))
        self.assertIn("glm-5.3", stack.overlays["mmmeta"])
        self.assertNotIn(TOKEN, stack.overlays["mmsecretary"])
        self.assertTrue(secrets.is_file())

    def _assert_mock_turn(self, meter_dir: Path) -> None:
        meter_dir.mkdir()
        spec = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
        transport = ScriptedTransport([ok_body(spec.served_model, content="offline")])
        client = HermesModelClient(
            transport=transport,
            meter_path=meter_dir / "usage.jsonl",
            environ={spec.credential_env: SECRET},
        )
        result = client.complete(CompletionRequest(
            role="secretary",
            turn_id="harness-tick-1",
            messages=({"role": "user", "content": "status"},),
            effect="read_only",
        ))
        self.assertTrue(result.ok)
        self.assertEqual(result.provider_id, spec.provider_id)
        self.assertEqual(len(transport.calls), 1)
        self.assertIn("ark.ap-southeast.bytepluses.com", transport.calls[0]["url"])
        self.assertNotIn("cursor-pool", transport.calls[0]["url"])
        self.assertNotIn(SECRET, (meter_dir / "usage.jsonl").read_text(encoding="utf-8"))
        self.assertFalse(result.executive_admission)
        self.assertFalse(result.capacity_claimed)

    def _ctl(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CTL), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )


_CLEAN_MISSING = [
    "credential:BYTEPLUS_MODELARK_API_KEY",
    "credential:CURSOR_API_KEY",
    "credential:MASTERMIND_STEWARD_ACCESS_TOKEN",
    "credential:MINIMAX_TOKEN_PLAN_KEY",
    "credential:ZAI_API_KEY",
    "credential:hermes-metaceo:HERMES_SLACK_BOT_TOKEN",
    "credential:hermes-secretary:HERMES_SLACK_BOT_TOKEN",
    "credential_file:mmmeta.secrets.env",
    "credential_file:mmsecretary.secrets.env",
    "endpoint:HERMES_CURSOR_POOL_BASE_URL",
    "endpoint:MASTERMIND_STEWARD_MCP_URL",
    "grant:executive_admission",
    "grant:fabric_live_submit",
    "grant:m2studio_computer_use",
    "grant:mac_tcc",
    "grant:pinned_upstream_checkout",
    "grant:ubuntu1_systemd_user_manager",
    "id:DOT_BOT_USER_IDS",
    "id:hermes-metaceo:HERMES_SLACK_BOT_USER_ID",
    "id:hermes-secretary:HERMES_SLACK_BOT_USER_ID",
]


if __name__ == "__main__":
    unittest.main()
