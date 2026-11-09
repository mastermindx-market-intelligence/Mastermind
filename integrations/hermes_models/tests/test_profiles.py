"""Rendered Hermes overlays stay keyless and match the qualification intents."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_models.cli import main  # noqa: E402
from integrations.hermes_models.profile_config import render_profile  # noqa: E402

_OVERLAYS = Path(__file__).resolve().parents[1] / "profiles"


class ProfileTests(unittest.TestCase):
    def test_committed_overlays_match_the_renderer(self):
        for name in ("mmsecretary", "mmmeta"):
            rendered = render_profile(name)
            committed = (_OVERLAYS / f"{name}.hermes-providers.yaml").read_text(encoding="utf-8")
            self.assertEqual(rendered, committed)

    def test_overlays_are_openai_compatible_and_keyless(self):
        secretary = render_profile("mmsecretary")
        meta = render_profile("mmmeta")
        self.assertIn("api_mode: chat_completions", secretary)
        self.assertIn("default: \"glm-5-3-flash-260828\"", secretary)
        self.assertIn("logical_model: glm-5.3-flash", secretary)
        self.assertIn("provider: byteplus-modelark", secretary)
        self.assertIn("default: \"glm-5.3\"", meta)
        self.assertIn("logical_model: glm-5.3", meta)
        self.assertIn("provider: zai-glm", meta)
        for text in (secretary, meta):
            self.assertIn("key_env: BYTEPLUS_MODELARK_API_KEY", text)
            self.assertIn("key_env: ZAI_API_KEY", text)
            self.assertIn("key_env: MINIMAX_TOKEN_PLAN_KEY", text)
            self.assertIn("key_env: CURSOR_API_KEY", text)
            self.assertIn("https://ark.ap-southeast.bytepluses.com/api/v3", text)
            self.assertIn("https://api.z.ai/api/paas/v4", text)
            self.assertIn("https://api.minimax.io/v1", text)
            self.assertIn("MiniMax-M3", text)
            self.assertIn("composer-2.5", text)
            self.assertIn("enabled: false", text)
            self.assertIn("cursor-pool.invalid", text)
            self.assertIn("- clarify", text)
            self.assertIn("- terminal", text)
            self.assertNotIn("fallback_model:", text)
            self.assertNotIn("\nfallback_model\n", text)
            self.assertNotIn("api_key:", text.lower())
            self.assertNotIn("api/coding", text)
            self.assertNotIn("bearer ", text.lower())

    def test_cli_render_refuses_credential_arguments(self):
        canary = "mmx-canary-secret-DO-NOT-LOG-9f3a"
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            self.assertEqual(main(["--api-key", canary]), 2)
            self.assertEqual(main([f"ZAI_API_KEY={canary}"]), 2)
        self.assertNotIn(canary, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
