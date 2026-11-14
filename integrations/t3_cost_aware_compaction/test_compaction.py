import importlib.util
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_apply_refuses_before_any_read_or_write_and_preserves_other_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "settings.json"
            other_writer = b'{"enabledPlugins":{"new-owner-edit":true}}\n'
            p.write_bytes(other_writer)
            stderr = io.StringIO()
            with patch.object(sys, "argv", ["compaction.py", "--apply", "--json"]), \
                 patch.object(m.Path, "read_text", side_effect=AssertionError("settings read")), \
                 patch.object(m.Path, "read_bytes", side_effect=AssertionError("settings read")), \
                 patch.object(m.Path, "mkdir", side_effect=AssertionError("directory write")), \
                 contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as refused:
                m.main()
            self.assertEqual(refused.exception.code, 2)
            self.assertIn("settings owner", stderr.getvalue())
            self.assertEqual(p.read_bytes(), other_writer)
            self.assertEqual(list(Path(temp).iterdir()), [p])

    def test_final_recommendations_respect_bounds_even_for_out_of_range_old_values(self):
        for group, policy in m.POLICY.items():
            for old in (None, 100000, 160000, policy["minimum"], policy["base"],
                        policy["maximum"], 1000000):
                for target in (policy["minimum"], policy["base"], policy["maximum"]):
                    with self.subTest(group=group, old=old, target=target):
                        result = m.step_limit(old, target, group)
                        self.assertGreaterEqual(result, policy["minimum"])
                        self.assertLessEqual(result, policy["maximum"])
                        if old is not None and policy["minimum"] <= old <= policy["maximum"]:
                            self.assertLessEqual(abs(result - old), 50000)
        self.assertEqual(m.step_limit(1000000, 200000, "fable"), 350000)
        self.assertEqual(m.step_limit(100000, 175000, "fable"), 175000)

    def test_disabled_missing_or_malformed_settings_are_unchanged(self):
        for data in ({}, {"modelSettings": None}, {"modelSettings": []},
                     {"modelSettings": "owner-data", "enabledPlugins": {"x": True}}):
            with self.subTest(data=data):
                result, decisions = m.snapshot_profile("fabric-unified-router", False, data, {}, {})
                self.assertEqual(result, data)
                self.assertEqual(decisions, [])

    def test_non_object_catalogs_use_baseline_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rates.json"
            with patch.object(m, "RATE_FILE", path):
                for value in ([], None, True, 42, "catalog", {"document": []}, {"document": None}):
                    with self.subTest(value=value):
                        path.write_text(json.dumps(value))
                        self.assertEqual(m.price_catalog(), {})
                path.write_text('{"document":{"model":{"rate":1}}}')
                self.assertEqual(m.price_catalog(), {"model": {"rate": 1}})

    def test_nonfinite_boolean_or_overflowing_rates_are_unknown(self):
        keys = ("input_cost_per_token", "cache_read_input_token_cost", "cache_creation_input_token_cost")
        for invalid in (float("inf"), float("-inf"), float("nan"), True, -1, 10**400):
            for key in keys:
                with self.subTest(value=invalid, key=key):
                    record = dict.fromkeys(keys, 0.001)
                    record[key] = invalid
                    price, source = m.rate_for("claude-opus-5-5", {"claude-opus-5-5": record})
                    self.assertIsNone(price)
                    self.assertEqual(source, "unknown")
                    self.assertEqual(m.target_window("claude-opus-5-5", m.stats([usage()] * 6, price))[0], 250000)

    def test_finite_price_arithmetic_overflow_falls_back_without_nonfinite_output(self):
        price = dict.fromkeys(("input_cost_per_token", "cache_read_input_token_cost", "cache_creation_input_token_cost"), 1e308)
        sample_stats = m.stats([usage()] * 6, price)
        self.assertIsNone(sample_stats["mean_input_usd"])
        self.assertEqual(m.target_window("claude-fable-5-2", sample_stats)[0], 200000)
        json.dumps(sample_stats, allow_nan=False)

    def test_context_average_uses_integer_arithmetic_for_large_valid_counters(self):
        huge = 10**400
        sample_stats = m.stats([usage(huge), usage(huge + 1)], None)
        self.assertEqual(sample_stats["mean_context_tokens"], huge)
        self.assertEqual(sample_stats["cache_ratio"], 0)
        json.dumps(sample_stats, allow_nan=False)

    def test_report_preserves_disabled_and_enabled_settings_without_filesystem_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            userdata = root / "userdata"
            userdata.mkdir()
            (userdata / "settings.json").write_text(json.dumps({"providerInstances": {
                "capacity_fabric": {"enabled": True}, "fabric_claude": {"enabled": False}}}))
            enabled = root / "providers" / "fabric-unified-router" / "settings.json"
            disabled = root / "providers" / "fabric-anthropic-oauth" / "settings.json"
            for p in (enabled, disabled):
                p.parent.mkdir(parents=True)
            enabled.write_text('{"enabledPlugins":{"secret-sentinel":true}}')
            disabled.write_text('not-json: disabled owner data')
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            stdout = io.StringIO()
            with patch.object(m, "T3", root), patch.object(m, "RATE_FILE", userdata / "absent-rates.json"), \
                 patch.object(sys, "argv", ["compaction.py", "--json"]), contextlib.redirect_stdout(stdout):
                self.assertEqual(m.main(), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["mode"], "dry_run")
            self.assertEqual(report["application_status"], "held-settings-owner-unqualified")
            self.assertTrue(report["provider_records"]["capacity_fabric"]["would_change"])
            self.assertFalse(report["provider_records"]["fabric_claude"]["would_change"])
            self.assertFalse(any(v["applied"] for v in report["provider_records"].values()))
            self.assertNotIn("secret-sentinel", stdout.getvalue())
            self.assertEqual({p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)
            self.assertFalse((root / "tools").exists())

    def test_installer_refuses_without_creating_or_starting_anything(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, HOME=temp)
            result = subprocess.run(["/bin/sh", str(MODULE.with_name("install.sh"))],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("settings writer is not qualified", result.stderr)
            self.assertEqual(list(Path(temp).iterdir()), [])

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
