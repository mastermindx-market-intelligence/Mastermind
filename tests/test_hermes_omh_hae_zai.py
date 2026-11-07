from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"integrations/hermes_omh/{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

m = module("hae_zai_extension")
build = module("stage_hae_zai")

class ZaiContractTests(unittest.TestCase):
    def test_documented_direct_origins_and_only_real_levels(self):
        for url in ["https://api.z.ai/api/paas/v4", "https://api.z.ai/api/coding/paas/v4",
                    "https://api.z.ai:443/api/coding/paas/v4/"]:
            with self.subTest(url=url):
                self.assertEqual(m.direct_zai_levels("zai", "glm-5.3", "chat_completions", url),
                                 ("low", "high", "max"))

    def test_neither_proxy_nor_url_tricks_gain_a_route(self):
        for url in [None, "", "http://api.z.ai/api/paas/v4", "https://api.z.ai.evil.test/api/paas/v4",
                    "https://api.z.ai:444/api/paas/v4", "https://u:p@api.z.ai/api/paas/v4",
                    "https://api.z.ai/api/paas/v4?key=secret", "https://api.z.ai/api/paas/v4#x",
                    "https://api.z.ai/v1", "https://api.z.ai:bad/api/paas/v4",
                    "https://api.z.ai/api/../api/paas/v4", " https://api.z.ai/api/paas/v4",
                    "https://proxy.example/api/paas/v4"]:
            with self.subTest(url=url):
                self.assertEqual(m.direct_zai_levels("zai", "glm-5.3", "chat_completions", url), ())

    def test_neither_alias_nor_adjacent_model_nor_api_is_assumed(self):
        for route in [("custom", "glm-5.3", "chat_completions"),
                      ("zai", "glm-5.3-flash", "chat_completions"),
                      ("zai", "zai/glm-5.3", "chat_completions"),
                      ("zai", "glm-5.3", "codex_responses")]:
            with self.subTest(route=route):
                self.assertEqual(m.direct_zai_levels(*route, "https://api.z.ai/api/paas/v4"), ())

    def test_per_request_endpoint_guard_preserves_other_families(self):
        self.assertTrue(m.direct_zai_request_allowed("zai", "glm-5.3", "chat_completions",
                                                    "https://api.z.ai/api/paas/v4"))
        self.assertFalse(m.direct_zai_request_allowed("zai", "glm-5.3", "chat_completions",
                                                     "https://relay.example/v1"))
        self.assertTrue(m.direct_zai_request_allowed("custom", "unrelated", "chat_completions",
                                                    "https://relay.example/v1"))

    def test_changed_middleware_refused_before_patch(self):
        with self.assertRaisesRegex(ValueError, "REVISION_MISMATCH"):
            build.patched_middleware(b"unknown newer source")

    def test_changed_source_refused_before_patch(self):
        with self.assertRaisesRegex(ValueError, "REVISION_MISMATCH"):
            build.patched_effort(b"unrelated or newer source")

    def test_existing_output_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            source, output = Path(d) / "source", Path(d) / "output"
            source.mkdir(); output.mkdir()
            marker = output / "keep"
            marker.write_text("original")
            with self.assertRaises(ValueError):
                build.stage(source, output)
            self.assertEqual(marker.read_text(), "original")

    def test_profile_data_is_not_a_build_input(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source"; source.mkdir()
            (source / ".env").write_text("private")
            with self.assertRaisesRegex(ValueError, "PROFILE_DATA"):
                build.stage(source, Path(d) / "stage")
            self.assertFalse((Path(d) / "stage").exists())

    def test_cannot_stage_into_a_live_profile_plugin_directory(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source"; source.mkdir()
            profile = Path(d) / "profile"; profile.mkdir()
            (profile / "config.yaml").write_text("{}")
            (profile / "plugins").mkdir()
            with self.assertRaisesRegex(ValueError, "HERMES_PROFILE"):
                build.stage(source, profile / "plugins" / "candidate")

    def test_source_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source"; source.mkdir()
            (source / "link").symlink_to("/tmp")
            with self.assertRaisesRegex(ValueError, "SYMLINK"):
                build.stage(source, Path(d) / "stage")

if __name__ == "__main__":
    unittest.main()
