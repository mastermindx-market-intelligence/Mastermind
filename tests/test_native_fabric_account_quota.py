"""H2 regression: provider evidence must not turn into invented capacity."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/native_fabric/grok47/quota_billing/quota_remote.py"
SPEC = importlib.util.spec_from_file_location("h2_quota_reader", SOURCE)
q = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = q
SPEC.loader.exec_module(q)
NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
STAMP = NOW.timestamp()
FUTURE = "2026-11-07T13:00:00Z"
ENDPOINT = "https://api.z.ai/api/coding/paas/v4"
GO_ENDPOINT = "https://opencode.ai/inference/go/v1"
BINDING = {"config_generation": "config-a", "endpoint": ENDPOINT}


def states(provider="glm", account="a", reset=FUTURE, remaining=60):
    windows = ("5h", "weekly", "monthly") if provider == "go" else ("5h", "weekly")
    return [q.ProviderQuotaState(
        provider, window, 100 - remaining, 100, remaining, reset,
        "PROVIDER_AUTHORITATIVE", q._iso(NOW), .98, "fixture",
        account=account, config_generation="config-a",
        endpoint=GO_ENDPOINT if provider == "go" else ENDPOINT,
    ) for window in windows]


def view(rows=None, provider="glm", account="a", **kwargs):
    options = {"config_generation": "config-a",
               "endpoint": GO_ENDPOINT if provider == "go" else ENDPOINT,
               "now_ts": STAMP}
    options.update(kwargs)
    return q.account_quota_view(provider, account,
                                states(provider, account) if rows is None else rows,
                                **options)


def go_payload():
    return {"usage": {name: {"status": "ok", "percent": pct, "resetsAt": FUTURE}
                      for name, pct in (("rolling", 10), ("weekly", 40), ("monthly", 80))}}


class AccountQuotaProjectionTests(unittest.TestCase):
    def test_three_go_windows_are_separate_and_all_required(self):
        rows = q.parse_go_usage_payload(go_payload(), NOW, account="a",
                                       config_generation="config-a", endpoint=GO_ENDPOINT)
        result = view(rows, "go")
        self.assertTrue(result["quota_ready"])
        self.assertEqual([w["remaining_pct"] for w in result["windows"]], [90, 60, 20])
        self.assertNotIn("total_remaining_pct", result)
        for required in (("5h",), ("5h", "weekly")):
            with self.assertRaisesRegex(ValueError, "cannot be omitted"):
                view(rows, "go", required_windows=required)
        rows[-1] = replace(rows[-1], remaining_pct=0)
        self.assertFalse(view(rows, "go")["quota_ready"])

    def test_missing_malformed_and_exhausted_go_window_never_ready(self):
        for bad in (None, {}, {"percent": 1}, {"percent": True, "status": "ok"},
                    {"percent": float("nan"), "status": "ok"},
                    {"percent": float("inf"), "status": "ok"},
                    {"percent": -1, "status": "ok"}, {"percent": 101, "status": "ok"},
                    {"percent": 100, "status": "ok"},
                    {"percent": 1, "status": "denied"},
                    {"percent": 1, "status": "ok", "resetsAt": "bad"}):
            with self.subTest(bad=bad):
                payload = go_payload()
                payload["usage"]["monthly"] = bad
                rows = q.parse_go_usage_payload(payload, NOW, account="a",
                                               config_generation="config-a", endpoint=GO_ENDPOINT)
                self.assertFalse(view(rows, "go")["quota_ready"])

    def test_clock_must_be_original_aware_and_not_future(self):
        for stamp in (None, "bad", True, "2026-11-07T12:00:00", STAMP + 1, STAMP - 601):
            with self.subTest(stamp=stamp):
                rows = q.parse_go_usage_payload(go_payload(), stamp, account="a",
                                               config_generation="config-a", endpoint=GO_ENDPOINT)
                self.assertFalse(view(rows, "go")["quota_ready"])
        self.assertEqual(q.parse_go_usage_payload(go_payload(), None, account="a")[0].observed_at, "")

    def test_reset_requires_new_observation_not_elapsed_clock(self):
        old = states(reset=q._iso(STAMP - 1))
        result = view(old)
        self.assertFalse(result["quota_ready"])
        self.assertEqual(result["windows"][0]["reason"], "RESET_REQUIRES_OBSERVATION")
        self.assertFalse(view(states(remaining=0))["quota_ready"])
        renewed = states(reset=FUTURE, remaining=100)
        self.assertTrue(view(renewed)["quota_ready"])
        null_clock = view(states(reset=None))
        self.assertTrue(null_clock["quota_ready"])
        self.assertIsNone(null_clock["windows"][0]["reset_at"])
        self.assertEqual(null_clock["windows"][0]["reset_state"], "UNKNOWN")

    def test_bad_reset_or_confidence_does_not_become_null_clock_success(self):
        for reset in ("bad", True, "2026-11-07T13:00:00"):
            self.assertFalse(view(states(reset=reset))["quota_ready"])
        for confidence in (None, float("nan"), float("inf"), 0, -1, 2):
            rows = [replace(s, confidence=confidence) for s in states()]
            self.assertFalse(view(rows)["quota_ready"])

    def test_accounts_endpoints_and_generations_do_not_inherit(self):
        self.assertFalse(view(states(account="b"))["quota_ready"])
        self.assertFalse(view(config_generation="config-b")["quota_ready"])
        self.assertFalse(view(endpoint="https://other.example/v1")["quota_ready"])
        self.assertFalse(view(account_generation="new-account")["quota_ready"])
        self.assertFalse(view(allowance_scope="physical-shared")["quota_ready"])
        rows = [replace(s, account_generation="generation-2", allowance_scope="shared") for s in states()]
        self.assertTrue(view(rows, account_generation="generation-2", allowance_scope="shared")["quota_ready"])
        self.assertFalse(view(rows + [rows[0]])["quota_ready"])
        self.assertFalse(view([None, {}])["quota_ready"])

    def test_quota_evidence_never_grants_entitlement_or_no_overage(self):
        result = view()
        self.assertTrue(result["quota_ready"])
        for field in ("entitlement", "no_overage", "admission"):
            self.assertEqual(result[field], "NOT_EVALUATED")
        self.assertFalse(view(refresh_error="PROVIDER_REFUSED")["quota_ready"])
        self.assertFalse(view([replace(s, refresh_error="failed") for s in states()])["quota_ready"])

    def test_go_response_allowance_is_debit_not_a_remaining_balance(self):
        usage = {"opencode": {"allowance": .12, "cost": 0, "list_cost": .20, "billing_source": "go"}}
        for payload in (usage, {"usage": usage}, {"usageMetadata": usage}):
            row = q.parse_go_response_allowance(payload, NOW, account="a")
            self.assertEqual(row.used, .12)
            self.assertEqual(row.units, "monthly_allowance_usd")
            self.assertIsNone(row.cap)
            self.assertIsNone(row.remaining_pct)
            self.assertIsNone(row.reset_at)
            self.assertFalse(view([row], "go")["quota_ready"])
        for payload in ({}, {"usage": {"opencode": {"cost": 0}}},
                        {"usage": usage, "usageMetadata": usage}):
            self.assertIsNone(q.parse_go_response_allowance(payload, NOW, account="a").used)

    def test_glm_does_not_guess_window_by_order_or_observation_by_read_time(self):
        payload = {"data": {"limits": [{"type": "TOKENS_LIMIT", "unit": 999, "percentage": 1}]}}
        self.assertEqual(q.parse_glm_payload(payload, NOW), [])
        payload["data"]["limits"][0].update(unit=3, nextResetTime="bad")
        row = q.parse_glm_payload(payload, None)[0]
        self.assertEqual(row.observed_at, "")
        self.assertIsNone(row.remaining_pct)
        self.assertEqual(row.source, "UNKNOWN")

    def test_minimax_malformed_percent_is_not_replaced_by_optimistic_counts(self):
        row = {"model_name": "general", "current_interval_usage_count": 0,
               "current_interval_total_count": 100, "current_interval_remaining_percent": float("nan")}
        result = q.parse_minimax_payload({"model_remains": [row]}, None)
        self.assertIsNone(result[0].remaining_pct)
        self.assertEqual(result[0].observed_at, "")
        self.assertEqual(result[0].units, "provider_usage_count")
        self.assertEqual(q.parse_minimax_payload({"model_remains": [row, row]}, NOW), [])

    def test_provider_wide_flattening_is_ambiguous_and_future_rows_are_invalid(self):
        with patch.object(q, "read_provider", return_value=states(account="a") + states(account="b")):
            self.assertIsNone(q.fresh_authoritative("glm", "5h", now_ts=STAMP))
            self.assertEqual(q.fresh_authoritative("glm", "5h", account="b", now_ts=STAMP).account, "b")
        for row in (replace(states()[0], observed_at=q._iso(STAMP + 1)),
                    replace(states()[0], reset_at="bad"),
                    replace(states()[0], refresh_error="failed")):
            with patch.object(q, "read_provider", return_value=[row]):
                self.assertIsNone(q.fresh_authoritative("glm", "5h", now_ts=STAMP))


class AccountQuotaCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = str(Path(self.tmp.name) / "quota_cache.json")
        self.clock = patch.object(q, "_utc_now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def write_cache(self, rows=None, **extra):
        entry = {"refreshed_at": STAMP, "binding": dict(BINDING),
                 "states": [asdict(s) for s in (states() if rows is None else rows)]}
        entry.update(extra)
        Path(self.cache).write_text(json.dumps({"glm": {"accounts": {"a": entry}}, "unrelated": {"keep": True}}))
        return entry

    def test_cache_reset_crossing_and_invalid_timestamps_trigger_owner_refresh(self):
        entry = self.write_cache()
        self.assertTrue(q._cache_fresh(entry, STAMP, BINDING))
        entry["states"][0]["reset_at"] = q._iso(STAMP)
        self.assertFalse(q._cache_fresh(entry, STAMP, BINDING))
        for timestamp in (STAMP + 1, "bad", float("nan"), None):
            entry = self.write_cache(refreshed_at=timestamp)
            self.assertFalse(q._cache_fresh(entry, STAMP, BINDING))

    def test_key_rotation_changes_generation_without_serializing_or_hashing_key(self):
        config = Path(self.tmp.name) / "glm.json"
        secret = "fixture-key-one-not-real"
        config.write_text(json.dumps({"api_key": secret, "openai_base_url": ENDPOINT}))
        real_sha = q.hashlib.sha256
        seen = []
        def digest(data):
            seen.append(data)
            return real_sha(data)
        with patch.dict(os.environ, {"GLM_CONFIG": str(config)}), patch.object(q.hashlib, "sha256", side_effect=digest):
            first = q._config_binding("glm")
            config.write_text(json.dumps({"api_key": "fixture-key-two-not-real", "openai_base_url": ENDPOINT}))
            second = q._config_binding("glm")
        self.assertNotEqual(first["config_generation"], second["config_generation"])
        self.assertNotIn(secret, json.dumps(first))
        self.assertTrue(all(b"fixture-key" not in data for data in seen))

    def test_changed_generation_and_failed_read_never_reuse_old_positive(self):
        self.write_cache()
        changed = dict(BINDING, config_generation="config-b")
        with patch.object(q, "_config_binding", return_value=changed), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm", side_effect=RuntimeError("offline")) as reader:
            result = q.glm_accounts_state(now_ts=STAMP, cache_path=self.cache)
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(result[0]["states"], [])
        self.assertEqual(result[0]["error"], "REMOTE_READ_FAILED")
        self.assertFalse(view(result[0]["states"], config_generation="config-b")["quota_ready"])

    def test_failed_forced_refresh_remains_failed_on_next_read(self):
        self.write_cache()
        with patch.object(q, "_config_binding", return_value=BINDING), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm", side_effect=RuntimeError("offline")) as reader:
            first = q.glm_accounts_state(now_ts=STAMP, cache_path=self.cache, force=True)
            second = q.glm_accounts_state(now_ts=STAMP + 1, cache_path=self.cache)
        self.assertEqual(reader.call_count, 2)
        for result in (first, second):
            self.assertEqual(result[0]["states"][0].source, "LOCAL_RECONSTRUCTION")
            self.assertFalse(view(result[0]["states"])["quota_ready"])
        retained = json.loads(Path(self.cache).read_text())
        self.assertTrue(retained["unrelated"]["keep"])
        self.assertEqual(retained["glm"]["accounts"]["a"]["refresh_error"], "REMOTE_READ_FAILED")

    def test_terminal_refusal_is_retained_and_force_is_not_permission_to_retry(self):
        self.write_cache()
        with patch.object(q, "_config_binding", return_value=BINDING), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm", side_effect=q.ProviderQuotaRefusal("refused")) as reader:
            q.glm_accounts_state(now_ts=STAMP, cache_path=self.cache, force=True)
            second = q.glm_accounts_state(now_ts=STAMP + 1, cache_path=self.cache, force=True)
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(second[0]["error"], "PROVIDER_REFUSED")
        self.assertFalse(view(second[0]["states"])["quota_ready"])

    def test_http_permission_refusal_does_not_retry_with_raw_key(self):
        for code in (401, 403):
            error = HTTPError(q.GLM_URL, code, "refused", {}, None)
            with patch.object(q, "_json_get", side_effect=error) as remote:
                with self.assertRaises(q.ProviderQuotaRefusal):
                    q._live_glm("a", "fixture-key")
            self.assertEqual(remote.call_count, 1)

    def test_original_refresh_updates_only_that_account_and_preserves_other_provider(self):
        self.write_cache(states(reset=q._iso(STAMP - 1)))
        with patch.object(q, "_config_binding", return_value=BINDING), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm", return_value=states(remaining=100)) as reader:
            result = q.qualified_provider_view("glm", now_ts=STAMP, cache_path=self.cache)
        self.assertEqual(reader.call_count, 1)
        self.assertTrue(result[0]["quota_ready"])
        retained = json.loads(Path(self.cache).read_text())
        self.assertTrue(retained["unrelated"]["keep"])
        self.assertEqual(retained["glm"]["accounts"]["a"]["states"][0]["remaining_pct"], 100)

    def test_binding_changed_during_read_does_not_publish_success(self):
        self.write_cache()
        changed = dict(BINDING, config_generation="config-b")
        with patch.object(q, "_config_binding", side_effect=[BINDING, BINDING, changed]), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm", return_value=states()):
            result = q.glm_accounts_state(now_ts=STAMP, cache_path=self.cache, force=True)
        self.assertEqual(result, [])
        self.assertEqual(json.loads(Path(self.cache).read_text())["glm"]["accounts"]["a"]["binding"], BINDING)

    def test_minimax_uses_same_generation_and_failure_fences(self):
        rows = [replace(s, provider="minimax", account="default") for s in states()]
        entry = {"refreshed_at": STAMP, "binding": BINDING, "states": [asdict(s) for s in rows]}
        Path(self.cache).write_text(json.dumps({"minimax": entry}))
        with patch.object(q, "_config_binding", return_value=BINDING), \
             patch.dict(q.READERS, {"minimax": lambda: (_ for _ in ()).throw(q.ProviderQuotaRefusal())}):
            first = q.read_provider("minimax", force=True, now_ts=STAMP, cache_path=self.cache)
            second = q.read_provider("minimax", force=True, now_ts=STAMP, cache_path=self.cache)
        for result in (first, second):
            self.assertFalse(view(result, provider="minimax", account="default")["quota_ready"])
            self.assertEqual(result[0].refresh_error, "PROVIDER_REFUSED")

    def test_qualified_cli_uses_same_reader_and_reports_no_admission(self):
        with patch.object(q, "qualified_provider_view", return_value=[view()]) as reader, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(q.main(["show", "--provider", "glm", "--qualified"]), 0)
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(json.loads(output.getvalue())[0]["admission"], "NOT_EVALUATED")

    def test_cached_park_cannot_follow_a_reassigned_account_alias(self):
        self.write_cache(states(remaining=2))
        self.assertTrue(q.cached_glm_account_parked("a", now_ts=STAMP,
                         cache_path=self.cache, config_generation="config-a"))
        for generation in (None, "config-b"):
            self.assertFalse(q.cached_glm_account_parked("a", now_ts=STAMP,
                              cache_path=self.cache, config_generation=generation))

    def test_failure_records_attempt_generation_and_does_not_relabel_an_old_denial(self):
        self.write_cache()
        changed = dict(BINDING, config_generation="config-b")
        with patch.object(q, "_config_binding", return_value=changed), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm", side_effect=q.ProviderQuotaRefusal()):
            q.glm_accounts_state(now_ts=STAMP, cache_path=self.cache, force=True)
        retained = json.loads(Path(self.cache).read_text())["glm"]["accounts"]["a"]
        self.assertEqual(retained["binding"], BINDING)
        self.assertEqual(retained["failure_binding"], changed)
        newest = dict(BINDING, config_generation="config-c")
        with patch.object(q, "_config_binding", return_value=newest), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm") as remote:
            result = q.qualified_provider_view("glm", now_ts=STAMP, cache_path=self.cache, force=True)
        remote.assert_not_called()
        self.assertEqual(result[0]["refresh_error"], "PRIOR_GENERATION_REFUSAL_UNRECONCILED")
        self.assertEqual(result[0]["failure_config_generation"], "config-b")
        self.assertEqual(result[0]["config_generation"], "config-c")
        self.assertFalse(result[0]["quota_ready"])

    def test_glm_needs_one_account_with_all_required_headroom(self):
        a, b = states(account="a"), states(account="b")
        a[1] = replace(a[1], remaining_pct=0)
        b[0] = replace(b[0], remaining_pct=0)
        def entry(name, rows):
            return {"name": name, "states": rows, "config_generation": "config-a",
                    "endpoint": ENDPOINT, "source": "PROVIDER_AUTHORITATIVE",
                    "observed_at": q._iso(NOW)}
        entries = [entry("a", a), entry("b", b)]
        with patch.object(q, "glm_accounts_state", return_value=entries):
            result = q.glm_quota_decision(now_ts=STAMP, cache_path=self.cache)
        self.assertEqual(result["state"], "PARKED")
        entries[1] = entry("b", states(account="b", remaining=50))
        with patch.object(q, "glm_accounts_state", return_value=entries):
            result = q.glm_quota_decision(now_ts=STAMP, cache_path=self.cache)
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["best_account"], "b")
        entries[1]["states"] = []
        with patch.object(q, "glm_accounts_state", return_value=entries):
            self.assertEqual(q.glm_quota_decision(now_ts=STAMP)["state"], "UNKNOWN")

    def test_local_reconstruction_does_not_grant_live_glm_headroom(self):
        with patch.object(q, "glm_accounts_state", return_value=[]):
            result = q.glm_quota_decision(now_ts=STAMP, local_estimate={"state": "OK", "pct_5h": 1})
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(result["source"], "LOCAL_RECONSTRUCTION")

    def test_cached_success_is_fenced_again_at_return(self):
        self.write_cache()
        changed = dict(BINDING, config_generation="config-b")
        with patch.object(q, "_config_binding", side_effect=[BINDING, BINDING, changed]), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm") as remote:
            self.assertEqual(q.glm_accounts_state(now_ts=STAMP, cache_path=self.cache), [])
        remote.assert_not_called()

    def test_refusal_persistence_failure_is_visible_and_does_not_retry(self):
        self.write_cache()
        with patch.object(q, "_config_binding", return_value=BINDING), \
             patch.object(q, "_glm_accounts_dict", return_value={"a": {"api_key": "fixture"}}), \
             patch.object(q, "_live_glm", side_effect=q.ProviderQuotaRefusal()) as remote, \
             patch.object(q.os, "replace", side_effect=PermissionError("fixture denial")) as write:
            with self.assertRaises(q.QuotaCacheWriteError):
                q.glm_accounts_state(now_ts=STAMP, cache_path=self.cache, force=True)
        self.assertEqual(remote.call_count, 1)
        self.assertEqual(write.call_count, 1)
        self.assertNotIn("terminal_refusal", json.loads(Path(self.cache).read_text())["glm"]["accounts"]["a"])


if __name__ == "__main__":
    unittest.main()
