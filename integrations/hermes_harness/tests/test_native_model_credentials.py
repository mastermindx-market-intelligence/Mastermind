"""Model-scoped credential transport tests: pure source, no Hermes start.

Fake fixture secrets only. No model/provider request or host credential accessed.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.native_byok import render_disarmed_native_byok
from integrations.hermes_harness.native_model_credential import primary_model_env
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.memory import HighWaterLog
from integrations.hermes_runtime.secrets import Secrets, load_secrets
from integrations.hermes_runtime.supervisor import ServiceRuntime
from integrations.hermes_runtime.tests._support import STUB, TOKEN

FAKE_BYTEPLUS = "test-provider-key-local-fixture-not-live-123456"
FAKE_ZAI = "test-zai-key-local-fixture-not-live-123456"


class NativeCredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="mmx-native-key-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.secret = self.root / "private.env"
        self.state = self.root / "state"
        self.home = self.root / "hermes-home"
        self.home.mkdir(mode=0o700)

    def _fixture_extras(self, lines: str) -> str:
        choices = {
            "BYTEPLUS_MODELARK_API_KEY": (FAKE_BYTEPLUS,),
            "ZAI_API_KEY": (FAKE_ZAI,),
            "HERMES_NATIVE_EGRESS_ROLE": ("mmsecretary", "mmmeta"),
            "HERMES_SLACK_BOT_TOKEN": (TOKEN, FAKE_BYTEPLUS, FAKE_ZAI,
                "distinct-dashboard-only-fixture-123456", "slack-token-fake-not-live",
                "synthetic-slack-bearer-123456"),
            "HERMES_SLACK_BOT_USER_ID": ("UPROJECTBOT001",),
            "BYTEPLUS_MODELARK_API_KEY_FILE": (str(self.root / "model-key"),
                str(self.root / "model-key-reused-as-slack-token")),
        }
        canonical = []
        for line in lines.splitlines():
            name, sep, value = line.partition("=")
            if sep != "=" or name not in choices or value not in choices[name]:
                raise ValueError("not a closed synthetic credential fixture")
            # Rebuild from the finite fixture catalog, never caller bytes.
            canonical.append(name + "=" + next(item for item in choices[name] if item == value) + "\n")
        return "".join(canonical)

    def _runtime(self, role="mmsecretary", extras="", dashboard_case="distinct", include_proxy=True):
        if role not in {"mmsecretary", "mmmeta"}:
            raise ValueError("not a synthetic role")
        examples = {
            "distinct": "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=distinct-dashboard-only-fixture-123456\n",
            "missing": "",
            "model_alias": "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=" + FAKE_BYTEPLUS + "\n",
        }
        if dashboard_case not in examples:
            raise ValueError("not a synthetic dashboard scenario")
        if type(include_proxy) is not bool:
            raise ValueError("invalid synthetic proxy selection")
        egress = (
            f"HERMES_NATIVE_EGRESS_ROLE={role}\n"
            f"HERMES_NATIVE_HTTPS_PROXY=http://{'127.0.0.2' if role == 'mmsecretary' else '127.0.0.3'}:{18651 if role == 'mmsecretary' else 18652}\n"
            if include_proxy else ""
        )
        content = "HERMES_GATEWAY_TOKEN=" + TOKEN + "\n" + examples[dashboard_case] + egress + self._fixture_extras(extras)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.secret, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
        profile = replace(
            compose_profile(role, state_dir=self.state, secrets_file=self.secret,
                            hermes_home=self.home, gateway_port=0, backend_port=0),
            tool_allowlist=frozenset({"clarify"}),
        )
        cfg = self.home / "profiles" / role / "config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(render_disarmed_native_byok(profile), encoding="utf-8")
        cfg.chmod(0o600)
        return ServiceRuntime(profile, load_secrets(self.secret), STUB)

    def test_fixture_rejects_arbitrary_values_before_file_creation(self) -> None:
        for kw in ({"extras": "BYTEPLUS_MODELARK_API_KEY=not-in-fixture-catalog\n"},
                   {"dashboard_case": "not-in-fixture-catalog"}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self._runtime(**kw)
            self.assertFalse(self.secret.exists())

    def test_secretary_only_primary_key_and_no_parent_bearer(self) -> None:
        rt = self._runtime(extras=(
            "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
            "ZAI_API_KEY=" + FAKE_ZAI + "\n"
            "HERMES_SLACK_BOT_TOKEN=slack-token-fake-not-live\n"
            "HERMES_SLACK_BOT_USER_ID=UPROJECTBOT001\n"
        ))
        census = rt._env()
        self.assertNotIn("BYTEPLUS_MODELARK_API_KEY", census)
        self.assertNotIn("ZAI_API_KEY", census)
        native = rt._model_child_env()
        self.assertEqual(native["BYTEPLUS_MODELARK_API_KEY"], FAKE_BYTEPLUS)
        self.assertNotIn("ZAI_API_KEY", native)
        self.assertNotIn("HERMES_GATEWAY_TOKEN", native)
        self.assertNotIn("HERMES_SLACK_BOT_TOKEN", native)
        self.assertNotIn(TOKEN, native.values())
        self.assertNotIn(FAKE_ZAI, native.values())
        self.assertEqual(native["HERMES_SLACK_BOT_USER_ID"], "UPROJECTBOT001")
        self.assertEqual(native["HTTPS_PROXY"], "http://127.0.0.2:18651")
        self.assertNotIn("HTTP_PROXY", native)
        self.assertNotIn("ALL_PROXY", native)
        self.assertNotIn("HERMES_NATIVE_HTTPS_PROXY", native)

    def test_meta_ceo_key_is_disjoint_from_secretary(self) -> None:
        rt = self._runtime(role="mmmeta", extras=(
            "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
            "ZAI_API_KEY=" + FAKE_ZAI + "\n"
        ))
        native = rt._model_child_env()
        self.assertEqual(native["ZAI_API_KEY"], FAKE_ZAI)
        self.assertNotIn("BYTEPLUS_MODELARK_API_KEY", native)

    def test_missing_or_bad_file_pointer_fails_closed(self) -> None:
        rt = self._runtime()
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE")

        file = self.root / "model-key"
        file.write_text(FAKE_BYTEPLUS + "\n", encoding="utf-8")
        file.chmod(0o600)
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY_FILE=" + str(file) + "\n")
        self.assertEqual(rt._model_child_env()["BYTEPLUS_MODELARK_API_KEY"], FAKE_BYTEPLUS)
        file.chmod(0o644)
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE")

    def test_missing_role_private_proxy_refuses_even_if_shell_has_proxy(self) -> None:
        rt = self._runtime(extras='BYTEPLUS_MODELARK_API_KEY=' + FAKE_BYTEPLUS + '\nHERMES_NATIVE_EGRESS_ROLE=mmsecretary\n', include_proxy=False)
        with mock.patch.dict(os.environ, {'HTTPS_PROXY': 'http://127.0.0.2:18651'}):
            with self.assertRaises(RuntimeRefusal) as exc:
                rt._model_child_env()
        self.assertEqual(exc.exception.code, 'NATIVE_EGRESS_PROXY_NOT_ENROLLED')

    def test_shell_only_key_cannot_bypass_role_private_secret_file(self) -> None:
        # A systemd unit must not depend on the installing operator's shell.
        rt = self._runtime()
        from unittest import mock
        with mock.patch.dict(os.environ, {
            "BYTEPLUS_MODELARK_API_KEY": FAKE_BYTEPLUS,
            "BYTEPLUS_MODELARK_API_KEY_FILE": "/tmp/not-authorized.key",
        }):
            with self.assertRaises(RuntimeRefusal) as exc:
                rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_CREDENTIAL_UNAVAILABLE")

    def test_mcp_enabled_or_config_drift_blocks_key_material(self) -> None:
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        cfg = rt.profile.hermes_home / "profiles" / rt.profile.role / "config.yaml"
        cfg.write_text(cfg.read_text().replace("enabled: false", "enabled: true"))
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "RUNTIME_NATIVE_CONFIG_DRIFT")

    def test_gateway_token_must_not_be_reused_as_dashboard_password(self) -> None:
        rt = self._runtime(
            extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n",
            dashboard_case="missing",
        )
        self.assertEqual(rt.secrets.dashboard_password, rt.secrets.token)
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")

    def test_model_key_must_not_be_reused_as_gateway_or_dashboard_key(self) -> None:
        rt = self._runtime(
            extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n",
            dashboard_case="model_alias",
        )
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_KEY_REUSE_REFUSED")

    def test_slack_bot_auth_must_not_alias_gateway_or_dashboard(self) -> None:
        for label, slack_token in (
            ("gateway", TOKEN),
            ("dashboard", "distinct-dashboard-only-fixture-123456"),
        ):
            with self.subTest(alias=label):
                rt = self._runtime(extras=(
                    "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
                    "HERMES_SLACK_BOT_TOKEN=" + slack_token + "\n"
                ))
                with self.assertRaises(RuntimeRefusal) as exc:
                    rt._model_child_env()
                self.assertEqual(exc.exception.code, "NATIVE_SLACK_BOT_AUTH_ALIAS_REFUSED")

    def test_model_key_must_not_alias_slack_bot_token_for_either_role(self) -> None:
        for role, env_name, value in (
            ("mmsecretary", "BYTEPLUS_MODELARK_API_KEY", FAKE_BYTEPLUS),
            ("mmmeta", "ZAI_API_KEY", FAKE_ZAI),
        ):
            with self.subTest(role=role):
                rt = self._runtime(role=role, extras=(
                    env_name + "=" + value + "\n"
                    "HERMES_SLACK_BOT_TOKEN=" + value + "\n"
                ))
                with self.assertRaises(RuntimeRefusal) as exc:
                    rt._model_child_env()
                self.assertEqual(exc.exception.code, "NATIVE_MODEL_KEY_REUSE_REFUSED")

    def test_file_pointer_key_must_not_alias_slack_bot_token(self) -> None:
        key_file = self.root / "model-key-reused-as-slack-token"
        key_file.write_text(FAKE_BYTEPLUS + "\n", encoding="utf-8")
        key_file.chmod(0o600)
        rt = self._runtime(extras=(
            "BYTEPLUS_MODELARK_API_KEY_FILE=" + str(key_file) + "\n"
            "HERMES_SLACK_BOT_TOKEN=" + FAKE_BYTEPLUS + "\n"
        ))
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_MODEL_KEY_REUSE_REFUSED")

    def test_byok_alias_refusal_happens_before_any_hermes_subprocess(self) -> None:
        rt = self._runtime(
            extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n",
            dashboard_case="missing",
        )
        with mock.patch(
            "integrations.hermes_runtime.supervisor.subprocess.run",
            side_effect=AssertionError("credential reached tools-list census"),
        ) as census:
            with self.assertRaises(RuntimeRefusal) as refused:
                rt.start()
        self.assertEqual(refused.exception.code, "NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")
        census.assert_not_called()
        self.assertIsNone(rt.gateway)
        self.assertIsNone(rt._thread)
        self.assertEqual(rt.child_starts, 0)

    def test_tool_census_env_contains_no_privileged_bearer(self) -> None:
        rt = self._runtime(extras=(
            "BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n"
            "ZAI_API_KEY=" + FAKE_ZAI + "\n"
            "HERMES_SLACK_BOT_TOKEN=synthetic-slack-bearer-123456\n"
        ))
        env = rt._registry_env()
        self.assertEqual(set(env), {"PATH", "HOME", "HERMES_HOME", "LANG"})
        self.assertNotIn(FAKE_BYTEPLUS, env.values())
        self.assertNotIn(FAKE_ZAI, env.values())
        self.assertNotIn(TOKEN, env.values())
        self.assertNotIn(rt.secrets.dashboard_password, env.values())

    def test_unexpected_supervisor_thread_error_becomes_terminal_failure(self) -> None:
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        with mock.patch.object(rt, "_loop", side_effect=OSError("sensitive synthetic fixture")):
            rt._loop_guarded()
        code, health = rt.health_snapshot()
        self.assertEqual(code, 503)
        self.assertEqual(health["status"], "failed")
        self.assertTrue(rt.failed)
        self.assertEqual(rt.refusal_code, "RUNTIME_SUPERVISOR_EXCEPTION")
        self.assertNotIn("sensitive", repr((health, rt.refusal_code)))
        self.assertIsNone(rt.child_pid)

    def test_subprocess_spawn_failure_marks_supervisor_failed(self) -> None:
        rt = self._runtime(extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n")
        rt.memory = HighWaterLog(self.state / "memory" / "high-water.log")
        # No actual spawn or port bind: test the exact supervised failure path.
        with mock.patch(
            "integrations.hermes_runtime.supervisor.reserve_loopback_port", return_value=19997,
        ), mock.patch(
            "integrations.hermes_runtime.supervisor.build_serve_argv",
            return_value=["/tmp/synthetic-never-executed"],
        ), mock.patch(
            "integrations.hermes_runtime.supervisor.subprocess.Popen",
            side_effect=OSError("synthetic spawn failure"),
        ):
            rt._loop_guarded()
        code, health = rt.health_snapshot()
        self.assertEqual(code, 503)
        self.assertEqual(health["status"], "failed")
        self.assertEqual(rt.refusal_code, "RUNTIME_SUPERVISOR_EXCEPTION")
        self.assertEqual(rt.child_starts, 1)
        self.assertIsNone(rt.child_pid)

    def test_uninstalled_shadow_profile_cannot_request_key(self) -> None:
        p = compose_profile("mmsecretary", state_dir=self.state, secrets_file=self.secret)
        with self.assertRaises(RuntimeRefusal) as exc:
            primary_model_env(p, {"BYTEPLUS_MODELARK_API_KEY": FAKE_BYTEPLUS})
        self.assertEqual(exc.exception.code, "NATIVE_EXTENSION_NOT_INSTALLED")


if __name__ == "__main__":
    unittest.main()
