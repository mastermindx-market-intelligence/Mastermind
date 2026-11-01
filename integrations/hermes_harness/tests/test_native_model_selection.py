"""Explicit BYOK model selection through the real installer, using fixtures only.

No Hermes server, systemd, provider request or company tool is started.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.cli import _install, _models, _status, main
from integrations.hermes_harness.native_byok import render_disarmed_native_byok
from integrations.hermes_harness.native_model_credential import primary_model_env
from integrations.hermes_harness.stack import compose_profile, write_composed_profile
from integrations.hermes_models.contract import native_provider
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import dump_profile, load_profile
from integrations.hermes_runtime.secrets import load_secrets
from integrations.hermes_runtime.supervisor import ServiceRuntime
from integrations.hermes_runtime.tests._support import STUB
from integrations.hermes_steward.config_guard import _load_unique_yaml

DEEPSEEK = "byteplus-modelark.deepseek-v4.1-flash"
GLM_FLASH = "byteplus-modelark.glm-5.3-flash"
FAKE = "synthetic-model-key-selection-test-123456"


class NativeModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-select-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.secret = self.root / "secrets.env"
        self.secret.write_text(
            "HERMES_GATEWAY_TOKEN=synthetic-gateway-distinct-123456\n"
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=synthetic-dashboard-distinct-123456\n"
            "BYTEPLUS_MODELARK_API_KEY=" + FAKE + "\n"
            "ZAI_API_KEY=synthetic-other-role-do-not-forward-123456\n",
            encoding="utf-8",
        )
        self.secret.chmod(0o600)
        self.profile = replace(
            compose_profile("mmsecretary", state_dir=self.root / "state",
                            secrets_file=self.secret, hermes_home=self.root / "home"),
            tool_allowlist=frozenset({"clarify"}),
        )

    def test_role_choices_are_existing_enabled_options_only(self):
        outcome = _models("mmsecretary")
        self.assertEqual([x["provider_id"] for x in outcome["choices"]], [GLM_FLASH, DEEPSEEK])
        self.assertFalse(outcome["credentials_read"])
        self.assertFalse(outcome["provider_called"])
        self.assertFalse(outcome["automatic_fallback"])
        self.assertEqual([x["provider_id"] for x in _models("mmmeta")["choices"]], ["zai.glm-5.3"])

    def test_cli_models_is_keyless_and_does_not_install(self):
        output = io.StringIO()
        with mock.patch("sys.stdout", output), mock.patch(
            "integrations.hermes_models.credentials.load_credential",
            side_effect=AssertionError("model listing must not read a key"),
        ):
            self.assertEqual(main(["models", "--role", "mmsecretary"]), 0)
        self.assertEqual(json.loads(output.getvalue())["choices"][1]["provider_id"], DEEPSEEK)
        self.assertFalse((self.root / "state").exists())

    def test_default_profile_and_explicit_default_render_same_native_bytes(self):
        explicit = replace(self.profile, native_provider_id=GLM_FLASH)
        self.assertEqual(render_disarmed_native_byok(self.profile), render_disarmed_native_byok(explicit))
        self.assertNotIn("native_provider_id", dump_profile(self.profile))

    def test_selected_model_roundtrips_and_uses_only_its_credential(self):
        selected = replace(self.profile, native_provider_id=DEEPSEEK)
        path = self.root / "profile.yaml"
        path.write_text(dump_profile(selected), encoding="utf-8")
        loaded = load_profile(path)
        self.assertEqual(loaded.native_provider_id, DEEPSEEK)
        parsed = _load_unique_yaml(render_disarmed_native_byok(loaded).encode("utf-8"))
        self.assertEqual(parsed["model"]["default"], "deepseek-v4-1-flash-261017")
        self.assertEqual(parsed["model"]["provider"], "byteplus-modelark")
        self.assertFalse(parsed["mcp_servers"]["mastermind_steward"]["enabled"])
        self.assertNotIn("fallback_model", parsed)
        self.assertNotIn("auxiliary", parsed)
        env = primary_model_env(loaded, load_secrets(self.secret).values)
        self.assertEqual(env, {"BYTEPLUS_MODELARK_API_KEY": FAKE})

    def test_disabled_cross_role_unknown_or_empty_selection_refused(self):
        for role, selection in (
            ("mmsecretary", "cursor-pool"), ("mmsecretary", "zai.glm-5.3"),
            ("mmmeta", DEEPSEEK), ("mmsecretary", "minimax.attended"),
            ("mmsecretary", "unknown"), ("mmsecretary", ""),
            ("mmsecretary", True), ("wrong-role", DEEPSEEK),
        ):
            with self.subTest(role=role, selection=selection):
                with self.assertRaises(ValueError):
                    native_provider(role, selection)

    def test_invalid_profile_selector_rejected_on_reload(self):
        path = self.root / "profile.yaml"
        base = dump_profile(self.profile)
        for selection in ("cursor-pool", "null", "true", "['bad']"):
            with self.subTest(selection=selection):
                path.write_text(base.replace("model:\n", "model:\n  native_provider_id: " + selection + "\n"))
                with self.assertRaises(RuntimeRefusal):
                    load_profile(path)

    def test_invalid_install_selector_writes_nothing(self):
        target = self.root / "unexpected-profile.yaml"
        with self.assertRaises(RuntimeRefusal):
            write_composed_profile(
                "mmsecretary", state_dir=self.root / "state", secrets_file=self.secret,
                dest=target, installed_native_only=True, native_provider_id="cursor-pool",
            )
        self.assertFalse(target.exists())
        self.assertFalse((self.root / "state").exists())

    def test_doctor_uses_installed_selection_and_its_actual_secret_file(self):
        from integrations.hermes_harness.doctor import _native_primary_present, _native_primary_source
        home = self.root / "doctor-home"
        installed = home / ".local/state/hermes-runtime-mmsecretary/current/profile.yaml"
        installed.parent.mkdir(parents=True)
        selected = replace(self.profile, native_provider_id=DEEPSEEK)
        installed.write_text(dump_profile(selected))
        spec, path = _native_primary_source(home, "mmsecretary")
        self.assertEqual(spec.provider_id, DEEPSEEK)
        self.assertEqual(path, self.secret)
        self.assertTrue(_native_primary_present(home, "mmsecretary"))
        installed.write_text(dump_profile(selected).replace(DEEPSEEK, "cursor-pool"))
        self.assertFalse(_native_primary_present(home, "mmsecretary"))

    def test_doctor_refuses_installed_role_mismatch_without_default_fallback(self):
        from integrations.hermes_harness.doctor import _native_primary_present
        home = self.root / "doctor-home"
        installed = home / ".local/state/hermes-runtime-mmsecretary/current/profile.yaml"
        installed.parent.mkdir(parents=True)
        meta = replace(compose_profile("mmmeta", state_dir=self.root / "state-meta",
                                       secrets_file=self.secret), tool_allowlist=frozenset({"clarify"}))
        installed.write_text(dump_profile(meta))
        self.assertFalse(_native_primary_present(home, "mmsecretary"))

    def test_install_config_receipt_status_and_child_env_agree(self):
        upstream = self.root / "upstream-fixture"
        upstream.mkdir()
        (upstream / "fixture.txt").write_text("offline fixture only\n")
        state = self.root / "state"
        result = _install(argparse.Namespace(
            role="mmsecretary", state=state, secrets_file=self.secret,
            systemd_user_dir=self.root / "config" / "systemd" / "user",
            hermes_bin=STUB, upstream_source=upstream, fetch=False,
            model_provider=DEEPSEEK,
        ))
        selection = result["native_model_selection"]
        self.assertEqual(selection["provider_id"], DEEPSEEK)
        self.assertFalse(selection["served_model_verified"])
        self.assertFalse(result["provider_called"])
        loaded = load_profile(state / "current" / "profile.yaml")
        native = loaded.hermes_home / "profiles" / loaded.role / "config.yaml"
        parsed = _load_unique_yaml(native.read_bytes())
        overlay = _load_unique_yaml((loaded.hermes_home / "provider-overlay.yaml").read_bytes())
        self.assertEqual(parsed["model"], overlay["model"])
        self.assertEqual(parsed["model"]["default"], selection["requested_model"])
        receipt = json.loads((state / "current" / "install-receipt.json").read_text())
        self.assertEqual(receipt["hermes_config_sha256"], hashlib.sha256(native.read_bytes()).hexdigest())
        self.assertEqual(_status(state)["native_model_selection"], selection)
        # Omitting the selector on a later install is not permission to reset
        # the saved provider or silently choose a fallback.
        upgraded = _install(argparse.Namespace(
            role="mmsecretary", state=state, secrets_file=self.secret,
            systemd_user_dir=self.root / "config" / "systemd" / "user",
            hermes_bin=STUB, upstream_source=upstream, fetch=False,
            model_provider=None,
        ))
        self.assertEqual(upgraded["native_model_selection"], selection)
        loaded = load_profile(state / "current" / "profile.yaml")
        native = loaded.hermes_home / "profiles" / loaded.role / "config.yaml"
        before_profile = (state / "current" / "profile.yaml").read_bytes()
        with self.assertRaises(RuntimeRefusal) as wrong_role:
            _install(argparse.Namespace(
                role="mmmeta", state=state, secrets_file=self.secret,
                systemd_user_dir=self.root / "config" / "systemd" / "user",
                hermes_bin=STUB, upstream_source=upstream, fetch=False,
                model_provider="zai.glm-5.3",
            ))
        self.assertEqual(wrong_role.exception.code, "NATIVE_UPGRADE_ROLE_MISMATCH")
        self.assertEqual((state / "current" / "profile.yaml").read_bytes(), before_profile)
        runtime = ServiceRuntime(loaded, load_secrets(self.secret), STUB)
        self.assertEqual(runtime._model_child_env()["BYTEPLUS_MODELARK_API_KEY"], FAKE)
        self.assertNotIn("ZAI_API_KEY", runtime._model_child_env())
        self.assertEqual(runtime.child_starts, 0)
        # Editing the on-disk native model without updating the exact role profile
        # cannot silently redirect the next model child.
        native.write_text(native.read_text().replace("deepseek-v4-1-flash-261017", "forged-model"))
        with self.assertRaises(RuntimeRefusal):
            runtime._model_child_env()


if __name__ == "__main__":
    unittest.main()
