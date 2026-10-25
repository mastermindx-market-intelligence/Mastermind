import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import preflight


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "model": {"provider": "zai", "default": "glm-5.3"},
            "auxiliary": {"vision": {"provider": "zai", "model": "glm-5.3-flash"}},
            "agent": {"disabled_toolsets": sorted(preflight.REQUIRED_DISABLED)},
            "toolsets": ["clarify"],
        }

    def check(self, config=None):
        return preflight.inspect(self.config if config is None else config, sha256="a" * 64)

    def test_valid_candidate_bounded_nonoperational_receipt(self):
        r = self.check()
        self.assertEqual(r["status"], "PASS_OFFLINE_POLICY_ONLY")
        self.assertFalse(r["actual_registered_tools_verified"])
        self.assertFalse(r["runtime_security_verified"])
        self.assertEqual(r["effect_expectation"], "NONE")

    def test_no_model_dispatched_even_on_success(self):
        r = self.check()
        self.assertFalse(r["hermes_started"])
        self.assertFalse(r["model_or_provider_called"])
        self.assertFalse(r["identity_or_authority_granted"])

    def test_missing_disable_rejected(self):
        c = copy.deepcopy(self.config)
        c["agent"]["disabled_toolsets"].remove("terminal")
        r = self.check(c)
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("terminal", r["observations"]["missing_disabled_toolsets"])

    def test_live_observed_toolset_leak_is_prevented(self):
        for exposed in ("todo", "connections"):
            with self.subTest(exposed=exposed):
                c = copy.deepcopy(self.config)
                c["agent"]["disabled_toolsets"].remove(exposed)
                r = self.check(c)
                self.assertEqual(r["status"], "BLOCKED")
                self.assertIn(exposed, r["observations"]["missing_disabled_toolsets"])

    def test_unknown_disabled_key_rejected(self):
        c = copy.deepcopy(self.config)
        c["agent"]["disabled_toolsets"].append("fake_future_toolset")
        self.assertIn("UNRECOGNIZED_DISABLED_TOOLSET", self.check(c)["issues"])

    def test_no_disabled_section_rejected(self):
        c = copy.deepcopy(self.config)
        del c["agent"]
        self.assertIn("GLOBAL_DISABLED_TOOLSETS_REQUIRED", self.check(c)["issues"])

    def test_wildcard_or_default_platform_toolsets_rejected(self):
        for toolsets in [["all"], ["safe"], ["clarify", "terminal"], []]:
            with self.subTest(toolsets=toolsets):
                c = copy.deepcopy(self.config)
                c["toolsets"] = toolsets
                self.assertIn("EXPLICIT_CLARIFY_ONLY_TOOLSETS_REQUIRED", self.check(c)["issues"])

    def test_overriding_platform_tools_rejected(self):
        c = copy.deepcopy(self.config)
        c["platform_toolsets"] = {"hermes-cli": ["terminal"]}
        self.assertIn("PLATFORM_TOOLSETS_UNQUALIFIED", self.check(c)["issues"])

    def test_rejects_unknown_config_and_model_overrides(self):
        for key, value in [("event_hooks", ["any"]), ("mcp_servers", {}), ("auth", {"enabled": True})]:
            with self.subTest(key=key):
                c = copy.deepcopy(self.config)
                c[key] = value
                self.assertIn("UNQUALIFIED_TOP_LEVEL_SECTION", self.check(c)["issues"])
        c = copy.deepcopy(self.config)
        c["model"]["base_url"] = "https://untrusted.example"
        self.assertIn("UNQUALIFIED_MODEL_ROUTE", self.check(c)["issues"])

    def test_no_plugins_or_mcp_even_with_readonly_name(self):
        for key, value in [("mcp_servers", {"mastermind": {"tools": {"include": ["status"]}}}), ("plugins", ["test"]), ("custom_toolsets", {"x": ["clarify"]}), ("tools", {"terminal": False})]:
            with self.subTest(key=key):
                c = copy.deepcopy(self.config)
                c[key] = value
                self.assertEqual(self.check(c)["status"], "BLOCKED")

    def test_gateway_cron_rejected(self):
        for key, value in [("gateway", {"enabled": True}), ("cron", {"jobs": ["x"]})]:
            with self.subTest(key=key):
                c = copy.deepcopy(self.config)
                c[key] = value
                self.assertEqual(self.check(c)["status"], "BLOCKED")

    def test_wrong_model_and_vision_rejected(self):
        c = copy.deepcopy(self.config)
        c["model"]["provider"] = "arbitrary"
        c["auxiliary"]["vision"]["provider"] = "auto"
        self.assertEqual(self.check(c)["status"], "BLOCKED")

    def test_inline_secret_field_is_detected_but_never_leaked(self):
        c = copy.deepcopy(self.config)
        c["env"] = {"API_KEY": "SECRET_SENTINEL_DO_NOT_PRINT"}
        encoded = json.dumps(self.check(c))
        self.assertNotIn("SECRET_SENTINEL", encoded)
        self.assertIn("INLINE_SECRET_FIELD", encoded)

    def test_unusual_scalar_and_nested_secret_detected(self):
        c = copy.deepcopy(self.config)
        c["misc"] = ["ok", {"access_token": "leak"}]
        self.assertEqual(self.check(c)["observations"]["inline_secret_field_count"], 1)

    def test_non_mapping_root_fails(self):
        self.assertEqual(self.check("unexpected")["status"], "BLOCKED")
        self.assertIn("CONFIG_ROOT_NOT_MAPPING", self.check([])["issues"])

    def test_safe_yaml_rejects_object_deserialization(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hostile.yaml"
            path.write_text('x: !!python/object/apply:os.system ["echo inappropriate"]', encoding="utf8")
            with self.assertRaisesRegex(ValueError, "INVALID_SAFE_YAML"):
                preflight.inspect_file(path)

    def test_oversize_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "huge.yaml"
            path.write_bytes(b"x" * (128 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "CONFIG_TOO_LARGE"):
                preflight.inspect_file(path)

    def test_receipt_no_overwrite_and_mode_600(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "receipt.json"
            r = self.check()
            preflight._atomic_new_receipt(path, r)
            self.assertEqual(json.loads(path.read_text())["status"], "PASS_OFFLINE_POLICY_ONLY")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                preflight._atomic_new_receipt(path, {"status": "ALTERED"})
            self.assertEqual(json.loads(path.read_text())["status"], "PASS_OFFLINE_POLICY_ONLY")

    def test_end_to_end_cli_success_and_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            source = ROOT / "example-readonly.config.yaml"
            destination = Path(d) / "ok.json"
            with contextlib.redirect_stdout(io.StringIO()):
                rc = preflight.main(["--config", str(source), "--receipt", str(destination)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(destination.read_text())["status"], "PASS_OFFLINE_POLICY_ONLY")
            reject = Path(d) / "bad.yaml"
            reject.write_text("toolsets: [all]\n", encoding="utf8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = preflight.main(["--config", str(reject), "--receipt", str(Path(d) / "bad.json")])
            self.assertEqual(rc, 2)

    def test_existing_receipt_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as d:
            source = ROOT / "example-readonly.config.yaml"
            destination = Path(d) / "receipt.json"
            destination.write_text("PREEXISTING", encoding="utf8")
            with contextlib.redirect_stderr(io.StringIO()):
                rc = preflight.main(["--config", str(source), "--receipt", str(destination)])
            self.assertEqual(rc, 3)
            self.assertEqual(destination.read_text(), "PREEXISTING")


if __name__ == "__main__":
    unittest.main()
