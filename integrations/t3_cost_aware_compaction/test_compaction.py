import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("compaction.py")
spec = importlib.util.spec_from_file_location("adaptive_t3_compaction", MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def usage(input_tokens=10, cache_read=0, cache_write=0, output=2):
    return {"input_tokens": input_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "output_tokens": output}


class T3AdaptiveCompactionTests(unittest.TestCase):
    def test_models_are_explicit_and_unknown_fails_closed(self):
        self.assertEqual(m.family("claude-fable-5-2"), "fable")
        self.assertEqual(m.family("claude-fable-5.2"), "fable")
        self.assertEqual(m.family("claude-opus-5-5"), "opus")
        self.assertEqual(m.family("glm-5.3"), "economical")
        self.assertEqual(m.family("claude-fable-5.2:free"), "economical")
        self.assertIsNone(m.family("fabric/frontier"))

    def test_principal_defaults_preserve_200k_and_250k(self):
        missing = m.stats([], None)
        self.assertEqual(m.target_window("claude-fable-5-2", missing)[0], 200000)
        self.assertEqual(m.target_window("claude-opus-5-5", missing)[0], 250000)
        self.assertEqual(m.target_window("glm-5.3", missing)[0], 900000)
        self.assertEqual(m.target_window("claude-opus-4-6", missing)[0], 180000)

    def test_high_cache_hit_can_extend_but_is_bounded(self):
        rates = {"input_cost_per_token": 0.00001,
                 "cache_read_input_token_cost": 0.00000025,
                 "cache_creation_input_token_cost": 0.0000125}
        evidence = m.stats([usage(2, 190000, 900)] * 8, rates)
        self.assertEqual(m.target_window("claude-fable-5-2", evidence),
                         (300000, "high-cache-reuse-low-input-cost"))
        self.assertEqual(m.step_limit(200000, 300000, "fable"), 250000)
        self.assertEqual(m.step_limit(160000, 300000, "fable"), 200000)

    def test_bad_cache_reuse_and_expensive_miss_compacts_earlier(self):
        rates = {"input_cost_per_token": 0.00001,
                 "cache_read_input_token_cost": 0.00000025,
                 "cache_creation_input_token_cost": 0.0000125}
        s = m.stats([usage(90000, 1000, 90000)] * 8, rates)
        self.assertEqual(m.target_window("claude-fable-5-1", s),
                         (175000, "high-cache-miss-cost"))
        self.assertEqual(m.target_window("claude-opus-5-5", s),
                         (225000, "high-cache-miss-cost"))

    def test_missing_prices_never_pushes_above_baseline(self):
        s = m.stats([usage(2, 250000, 300)] * 12, None)
        self.assertEqual(m.target_window("claude-fable-5-2", s)[0], 200000)

    def test_provider_settings_are_preserved_and_disabled_remains_untouched(self):
        orig = {"extraKnownMarketplaces": {"private": {"token": "secret-sentinel"}},
                "enabledPlugins": {"sample": True},
                "modelSettings": {"unrelated-model": {"autoCompactWindow": 700000},
                                  "claude-fable-5-2": {"autoCompactWindow": 160000,
                                                        "enableSomething": True}}}
        altered, records = m.snapshot_profile("fabric-unified-router", True, orig, {}, {})
        self.assertEqual(altered["extraKnownMarketplaces"], orig["extraKnownMarketplaces"])
        self.assertEqual(altered["modelSettings"]["unrelated-model"],
                         {"autoCompactWindow": 700000})
        self.assertEqual(altered["modelSettings"]["claude-fable-5-2"]["enableSomething"],
                         True)
        self.assertEqual(altered["modelSettings"]["claude-fable-5-2"]["autoCompactWindow"],
                         200000)
        self.assertEqual(orig["modelSettings"]["claude-fable-5-2"]["autoCompactWindow"],
                         160000)
        unchanged, no_actions = m.snapshot_profile("fabric-unified-router", False, orig, {}, {})
        self.assertEqual(unchanged, orig)
        self.assertFalse(no_actions)
        self.assertGreater(len(records), 0)

    def test_sample_deduplication_and_no_transcript_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "chat.jsonl"
            entry = {"type": "assistant", "message": {"id": "m1", "model": "claude-opus-5-5",
                "usage": usage(10, 10000, 250), "content": "PRIVATE CONVERSATION"}}
            path.write_text("\n".join([json.dumps(entry), json.dumps(entry)]) + "\n")
            found = list(m.tail_records(path))
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0][0], "claude-opus-5-5")
            self.assertNotIn("PRIVATE", str(found))

    def test_atomic_write_and_readback_rejects_concurrent_change(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "settings.json"
            p.write_text('{"modelSettings":{"x":1},"enabledPlugins":{"p":true}}\n')
            initial = p.read_bytes()
            modified = json.loads(initial)
            modified["modelSettings"]["x"] = 2
            self.assertTrue(m.atomic_json_update(p, initial, modified))
            self.assertEqual(json.loads(p.read_text())["modelSettings"]["x"], 2)
            self.assertTrue(list(Path(temp).glob("settings.json.bak-adaptive-compaction-*")))
            with self.assertRaises(RuntimeError):
                m.atomic_json_update(p, initial, {"modelSettings":{"x":3}})
            self.assertEqual(json.loads(p.read_text())["modelSettings"]["x"], 2)

    def test_stale_files_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "projects" / "project"
            root.mkdir(parents=True)
            recent = root / "new.jsonl"
            stale = root / "old.jsonl"
            recent.write_text('{"type":"assistant"}\n')
            stale.write_text('{"type":"assistant"}\n')
            now = time.time()
            os.utime(stale, (now - 8*3600, now - 8*3600))
            self.assertEqual(m.recent_files(Path(temp) / "projects", now), [recent])


if __name__ == "__main__":
    unittest.main(verbosity=2)