"""Hermetic GLM Claude worker SDK model-registration regression tests.

No provider, local broker, network, secrets or Fabric worker is started. The
lease-bound worker is exercised with a synthetic remote admission and a fake
credential-selector module, stopping at the exec callback boundary.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/native_fabric/quota_continuity/source/glm_bound_claude.py"
SPEC = importlib.util.spec_from_file_location("glm_bound_claude_custom_model_test", SOURCE)
assert SPEC is not None and SPEC.loader is not None
glm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(glm)

MODEL_ENV_KEYS = (
    "ANTHROPIC_CUSTOM_MODEL_OPTION",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)


class GLMClaudeCustomModelRegistrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base_env = {
            "POOL_ACCOUNT": "admitted-account",
            "POOL_LEASE_ID": "lease-test",
            "POOL_ORCHESTRATOR_ID": "original-root",
            "REMOTE_SUB_RUN_ID": "new-isolated-test-run",
            "LANE_REMOTE_HOST": "admitted-test-host",
            "LANE_LEASED": "1",
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_CUSTOM_MODEL_OPTION": "inherited-other-model",
            "ANTHROPIC_MODEL": "inherited-other-model",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "inherited-other-model",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "inherited-other-model",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "inherited-other-model",
            "ANTHROPIC_DEFAULT_FABLE_MODEL": "inherited-other-model",
            "CLAUDE_CODE_SUBAGENT_MODEL": "inherited-other-model",
            "GLM_SHIM_TOKEN": "inherited-not-for-claude",
        }
        fake_keys = types.ModuleType("glm_keys")
        fake_keys.selected_account_key = lambda account, accounts: (
            "offline-placeholder-key"
            if account == "admitted-account" and account in accounts
            else (_ for _ in ()).throw(ValueError("unqualified account"))
        )
        self.fake_keys = fake_keys

    def launch(self, model, environ=None, exec_fn=None):
        with mock.patch.dict(sys.modules, {"glm_keys": self.fake_keys}):
            return glm.launch(
                self.temp.name,
                model,
                "offline packet",
                "",
                "{}",
                "2",
                environ=self.base_env if environ is None else environ,
                accounts={"admitted-account": object()},
                exec_fn=exec_fn,
            )

    def test_both_qualified_models_are_registered_exactly(self):
        for model in ("glm-5.3-flash", "glm-5.3"):
            with self.subTest(model=model):
                exec_fn = mock.Mock(side_effect=lambda argv, env: (argv, env))
                original = dict(self.base_env)
                argv, scoped = self.launch(model, exec_fn=exec_fn)
                exec_fn.assert_called_once()
                self.assertEqual(argv[0:2], ["claude", "-p"])
                self.assertEqual(argv[argv.index("--model") + 1], model)
                for key in MODEL_ENV_KEYS:
                    self.assertEqual(scoped[key], model, key)
                self.assertEqual(scoped["ANTHROPIC_AUTH_TOKEN"], "offline-placeholder-key")
                self.assertEqual(scoped["ANTHROPIC_BASE_URL"], original["ANTHROPIC_BASE_URL"])
                self.assertNotIn("GLM_SHIM_TOKEN", scoped)
                self.assertEqual(self.base_env, original, "parent environment must not change")

    def test_unrecognized_model_refused_before_exec(self):
        exec_fn = mock.Mock()
        with self.assertRaisesRegex(glm.BindingRefused, "model refused"):
            self.launch("glm-5.3-fla5h", exec_fn=exec_fn)
        exec_fn.assert_not_called()

    def test_missing_remote_lease_identity_refused_before_exec(self):
        bad_env = dict(self.base_env)
        del bad_env["POOL_LEASE_ID"]
        exec_fn = mock.Mock()
        with self.assertRaisesRegex(glm.BindingRefused, "binding missing"):
            self.launch("glm-5.3-flash", environ=bad_env, exec_fn=exec_fn)
        exec_fn.assert_not_called()

    def test_account_credential_unavailable_refused_before_exec(self):
        self.fake_keys.selected_account_key = mock.Mock(side_effect=ValueError("not admitted"))
        exec_fn = mock.Mock()
        with self.assertRaisesRegex(glm.BindingRefused, "account credential unavailable"):
            self.launch("glm-5.3-flash", exec_fn=exec_fn)
        exec_fn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
