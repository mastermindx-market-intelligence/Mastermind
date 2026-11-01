"""Model-scoped credential transport tests: pure source, no Hermes start.

Fake fixture secrets only. No model/provider request or host credential accessed.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import tempfile
import unittest

from integrations.hermes_harness.native_byok import render_disarmed_native_byok
from integrations.hermes_harness.native_model_credential import primary_model_env
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
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

    def _runtime(self, role="mmsecretary", extras="", dashboard_password="distinct-dashboard-only-fixture-123456"):
        dashboard_line = (
            "" if dashboard_password is None
            else "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=" + dashboard_password + "\n"
        )
        self.secret.write_text(
            "HERMES_GATEWAY_TOKEN=" + TOKEN + "\n" + dashboard_line + extras,
            encoding="utf-8",
        )
        self.secret.chmod(0o600)
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
            dashboard_password=None,
        )
        self.assertEqual(rt.secrets.dashboard_password, rt.secrets.token)
        with self.assertRaises(RuntimeRefusal) as exc:
            rt._model_child_env()
        self.assertEqual(exc.exception.code, "NATIVE_GATEWAY_PASSWORD_ALIAS_REFUSED")

    def test_model_key_must_not_be_reused_as_gateway_or_dashboard_key(self) -> None:
        rt = self._runtime(
            extras="BYTEPLUS_MODELARK_API_KEY=" + FAKE_BYTEPLUS + "\n",
            dashboard_password=FAKE_BYTEPLUS,
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

    def test_uninstalled_shadow_profile_cannot_request_key(self) -> None:
        p = compose_profile("mmsecretary", state_dir=self.state, secrets_file=self.secret)
        with self.assertRaises(RuntimeRefusal) as exc:
            primary_model_env(p, {"BYTEPLUS_MODELARK_API_KEY": FAKE_BYTEPLUS})
        self.assertEqual(exc.exception.code, "NATIVE_EXTENSION_NOT_INSTALLED")


if __name__ == "__main__":
    unittest.main()
