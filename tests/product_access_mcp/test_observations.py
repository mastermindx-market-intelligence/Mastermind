"""Owner-contract fixtures; never contact production or use user credentials."""
from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import unittest
from datetime import datetime, timezone

NOW = datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc)
STAMP = "2026-10-09T20:59:00Z"


def pulse():
    return {
        "schema": "intelligence_hub.market_pulse.v1",
        "projection": "intelligence_hub.market_pulse", "snapshot_id": "a" * 16,
        "generated_at": STAMP, "source_owner": "terminal-market-data", "source_view": "regular",
        "state": {"availability": "available", "freshness": "delayed", "session": "regular", "coverage": "complete"},
        "coverage": {"requested": 1, "resolved": 1, "live": 0, "delayed": 1, "stale": 0, "missing": 0},
        "items": [{"symbol": "SPY", "price": 500.0, "change_abs": 0.0, "change_pct": 0.0,
                   "currency": "USD", "session": "regular", "freshness": "delayed",
                   "observed_at": STAMP, "received_at": None, "published_at": STAMP,
                   "regular_session_date": "2026-10-09", "revision": "b" * 16}],
        "errors": [],
    }


class ObservationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("integrations.product_access_mcp.reader"),
                             "ProductReader implementation is absent")
        self.module = importlib.import_module("integrations.product_access_mcp.reader")
        self.contracts = importlib.import_module("integrations.product_access_mcp.contracts")
        self.payloads = {"health": {"status": "ok", "commit": "a" * 7, "checkout": "b" * 40},
                         "status": {"status": "ok", "commit": "a" * 7,
                                    "checks": {"quotes": {"built": STAMP, "age_min": 0, "requested": 0, "resolved": 0},
                                               "terminal_data": {"status": "missing"}}}, "market_pulse": pulse()}
        self.raw = {}
        self.calls = []
        test = self
        class Port:
            async def read(self, endpoint, *, symbols=()):
                test.calls.append((endpoint, symbols))
                body = test.raw.get(endpoint, json.dumps(test.payloads[endpoint]).encode())
                return test.contracts.HttpObservation(status=200, body=body, content_type="application/json")
        self.reader = self.module.ProductReader(transport=Port(), now=lambda: NOW)

    async def test_build_checkout_and_unknown_freshness_are_separate(self):
        result = await self.reader.diagnostics()
        health, status = result["observations"]
        self.assertTrue(health["data"]["checkout_drift"])
        self.assertEqual(health["data"]["process_revision"], "a" * 7)
        self.assertFalse(health["data"]["exact_deployment_verified"])
        quote = status["data"]["checks"]["quotes"]
        self.assertEqual(quote["file_age_minutes"], 0)
        self.assertEqual(quote["counts"]["resolved"], 0)
        self.assertEqual(quote["source_time"]["value"], STAMP)
        self.assertEqual(quote["source_time"]["status"], "observed")
        self.assertEqual(status["data"]["checks"]["terminal_data"]["state"], "missing")
        self.assertEqual(status["data"]["checks"]["terminal_data"]["source_time"]["status"], "unknown")
        self.assertNotIn("fresh", result)

    async def test_abbreviated_prefix_is_not_proof_of_checkout_drift(self):
        self.payloads["health"].update(commit="abcdef0", checkout="abcdef0" + "1" * 33)
        result = await self.reader.diagnostics()
        self.assertIsNone(result["observations"][0]["data"]["checkout_drift"])

    async def test_numeric_json_overflow_is_refused_even_in_unprojected_fields(self):
        self.raw["status"] = b'{"status":"ok","commit":"abcdef0","checks":{},"unprojected":1e9999}'
        result = await self.reader.diagnostics()
        self.assertEqual(result["observations"][1]["state"], "invalid")
        self.assertIsNone(result["observations"][1]["data"])

    async def test_body_digest_is_exact_not_a_reserialized_digest(self):
        self.raw["health"] = b'{ "status": "ok", "commit": "abcdef0", "checkout": "abcdef0" }\n'
        result = await self.reader.diagnostics()
        self.assertEqual(result["observations"][0]["sha256"], hashlib.sha256(self.raw["health"]).hexdigest())

    async def test_unknown_timestamp_boolean_count_and_error_are_not_success(self):
        self.payloads["status"]["checks"]["quotes"] = {"built": "bad", "age_min": True, "resolved": False,
                                                       "error": "Bearer PRIVATE_FAILURE"}
        result = await self.reader.diagnostics()
        row = result["observations"][1]["data"]["checks"]["quotes"]
        self.assertEqual(row["source_time"]["status"], "invalid")
        self.assertIsNone(row["file_age_minutes"])
        self.assertIsNone(row["counts"]["resolved"])
        self.assertEqual(row["state"], "unavailable")
        self.assertNotIn("PRIVATE_FAILURE", json.dumps(result))

    async def test_future_and_timezone_naive_timestamps_are_not_current(self):
        for stamp, status in [("2099-01-01T00:00:00Z", "future"), ("2026-10-09T20:00:00", "invalid"), (None, "unknown")]:
            with self.subTest(stamp=stamp):
                self.payloads["status"]["checks"]["quotes"]["built"] = stamp
                result = await self.reader.diagnostics()
                self.assertEqual(result["observations"][1]["data"]["checks"]["quotes"]["source_time"]["status"], status)

    async def test_market_owner_times_zero_moves_and_revision_survive(self):
        result = await self.reader.market_pulse(["SPY"])
        observation = result["observations"][0]
        self.assertEqual(observation["source_owner"], "terminal-market-data")
        row = observation["data"]["items"][0]
        self.assertEqual(row["change_pct"], 0.0)
        self.assertEqual(row["revision"], "b" * 16)
        self.assertEqual(row["observed_at"]["value"], STAMP)
        self.assertEqual(row["owner_freshness"], "delayed")
        self.assertEqual(observation["access_class"], "public")
        self.assertNotEqual(observation["observed_at"], STAMP)

    async def test_missing_quote_timestamp_is_explicitly_unknown(self):
        self.payloads["market_pulse"]["items"][0]["observed_at"] = None
        result = await self.reader.market_pulse(["SPY"])
        row = result["observations"][0]["data"]["items"][0]
        self.assertEqual(row["observed_at"]["status"], "unknown")
        self.assertFalse(row["timestamp_qualified"])

    async def test_partial_coverage_has_missing_symbols_not_invented_zero_quotes(self):
        value = self.payloads["market_pulse"]
        value["coverage"].update(requested=2, missing=1)
        value["state"]["coverage"] = "partial"
        value["errors"] = [{"symbol": "QQQ", "code": "quote_unavailable"}]
        result = await self.reader.market_pulse(["SPY", "QQQ"])
        data = result["observations"][0]["data"]
        self.assertEqual(data["coverage"]["missing"], 1)
        self.assertEqual(data["errors"], value["errors"])
        self.assertEqual(len(data["items"]), 1)

    async def test_invalid_source_contract_refuses_whole_quote(self):
        mutations = [lambda p: p.update(source_owner="other"), lambda p: p.update(source_view="full"),
                     lambda p: p.update(schema="v2"), lambda p: p["items"][0].update(extPrice=123),
                     lambda p: p["items"][0].update(symbol="QQQ"), lambda p: p["coverage"].update(resolved=3),
                     lambda p: p["items"][0].update(price=True), lambda p: p.update(cookie="PRIVATE_COOKIE")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.payloads["market_pulse"] = pulse()
                mutate(self.payloads["market_pulse"])
                result = await self.reader.market_pulse(["SPY"])
                self.assertEqual(result["observations"][0]["state"], "invalid")
                self.assertIsNone(result["observations"][0]["data"])
                self.assertNotIn("PRIVATE_COOKIE", json.dumps(result))

    async def test_non_json_duplicate_keys_nonfinite_and_oversize_refused(self):
        for body in [b'<html>PRIVATE_LOGIN</html>', b'{"status":"ok","status":"bad"}',
                     b'{"status":"ok","value":NaN}', b' ' * (256 * 1024 + 1)]:
            with self.subTest(length=len(body)):
                self.raw["health"] = body
                result = await self.reader.diagnostics()
                self.assertEqual(result["observations"][0]["state"], "invalid")
                self.assertIsNone(result["observations"][0]["data"])
                self.assertNotIn("PRIVATE_LOGIN", json.dumps(result))

    async def test_invalid_symbols_never_reach_transport(self):
        for symbols in [[], ["SPY", "SPY"], ["spy"], ["SPY&token=x"], ["A"] * 13, "SPY", [True]]:
            with self.subTest(symbols=symbols):
                with self.assertRaises(ValueError):
                    await self.reader.market_pulse(symbols)
        self.assertEqual(self.calls, [])

    async def test_upstream_denial_never_falls_back_or_exposes_body(self):
        test = self
        class Denied:
            async def read(self, endpoint, *, symbols=()):
                test.calls.append(endpoint)
                return test.contracts.HttpObservation(status=403, body=b'PRIVATE_BODY', content_type="text/plain")
        reader = self.module.ProductReader(transport=Denied(), now=lambda: NOW)
        result = await reader.market_pulse(["SPY"])
        self.assertEqual(self.calls, ["market_pulse"])
        self.assertEqual(result["observations"][0]["state"], "unauthorized")
        self.assertNotIn("PRIVATE_BODY", json.dumps(result))

    async def test_unknown_checks_are_counted_not_silently_claimed_complete(self):
        self.payloads["status"]["checks"]["private_new_source"] = {"secret": "PRIVATE"}
        result = await self.reader.diagnostics()
        data = result["observations"][1]["data"]
        self.assertEqual(data["omitted_check_count"], 1)
        self.assertNotIn("PRIVATE", json.dumps(result))
