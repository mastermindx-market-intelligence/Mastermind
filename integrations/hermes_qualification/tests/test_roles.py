from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preflight import REQUIRED_DISABLED, inspect_file


class RoleProfiles(unittest.TestCase):
    def test_both_disarmed_profiles_qualify_independently(self):
        for name in ("mmsecretary", "mmmeta"):
            with self.subTest(name=name):
                path = ROOT / "profiles" / name / "config.yaml"
                result = inspect_file(path)
                self.assertEqual(result["status"], "PASS_OFFLINE_POLICY_ONLY")
                self.assertFalse(result["identity_or_authority_granted"])
                self.assertFalse(result["model_or_provider_called"])
                self.assertFalse(result["actual_registered_tools_verified"])

    def test_exact_role_model_intents_are_distinct_and_tool_fence_identical(self):
        import yaml
        sec = yaml.safe_load((ROOT / "profiles" / "mmsecretary" / "config.yaml").read_text())
        meta = yaml.safe_load((ROOT / "profiles" / "mmmeta" / "config.yaml").read_text())
        self.assertEqual(sec["model"]["default"], "glm-5.3-flash")
        self.assertEqual(meta["model"]["default"], "glm-5.3")
        self.assertEqual(set(sec["agent"]["disabled_toolsets"]), REQUIRED_DISABLED)
        self.assertEqual(sec["agent"]["disabled_toolsets"], meta["agent"]["disabled_toolsets"])
        self.assertEqual(sec["toolsets"], meta["toolsets"])
        self.assertEqual(sec["toolsets"], ["clarify"])

    def test_profiles_have_role_guidance_not_bundled_credentials_or_tools(self):
        for name in ("mmsecretary", "mmmeta"):
            text = (ROOT / "profiles" / name / "SOUL.md").read_text(encoding="utf8")
            self.assertIn("candidate, disarmed", text)
            self.assertIn("only `clarify`", text)
            self.assertIn("Agent OS", text)
            self.assertIn("Executive OS", text)
            self.assertNotIn("sk-zai-", text)


if __name__ == "__main__":
    unittest.main()
