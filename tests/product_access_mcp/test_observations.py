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

    async def test_date_only_field_must_match_json_schema_wire_grammar(self):
        from jsonschema import Draft202012Validator, FormatChecker
        from integrations.product_access_mcp.schemas import TOOL_SPECS
        spec = next(x for x in TOOL_SPECS if x["name"] == "product_market_pulse")
        validator = Draft202012Validator(spec["outputSchema"], format_checker=FormatChecker())
        for day in ("2026-10- 1", "2026-W41-5", "2026-02-30", "2026/10/09", "2026-10-9"):
            with self.subTest(invalid_day=day):
                self.payloads["market_pulse"] = pulse()
                self.payloads["market_pulse"]["items"][0]["regular_session_date"] = day
                result = await self.reader.market_pulse(["SPY"])
                self.assertEqual(result["observations"][0]["state"], "invalid")
                self.assertIsNone(result["observations"][0]["data"])
                validator.validate(result)
        for day in ("2026-10-09", "2024-02-29"):
            with self.subTest(valid_day=day):
                self.payloads["market_pulse"] = pulse()
                self.payloads["market_pulse"]["items"][0]["regular_session_date"] = day
                result = await self.reader.market_pulse(["SPY"])
                self.assertEqual(result["observations"][0]["state"], "observed")
                validator.validate(result)

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


PROJECTION_NOW = datetime(2026, 10, 10, 0, 10, tzinfo=timezone.utc)


def overlay_payload(**changes):
    return {
        "schema": "live.overlay.v2", "built": "2026-10-10 00:05:00 UTC",
        "quote_ts_max": "2026-10-10T00:04:59Z",
        "n": 3, "n_fresh": 2, "n_quotes": 3, "delayed_min": 15, "realtime": False,
        "market": {"SPY": {"price": 620.5, "stale": False, "data_frozen": True,
                           "data_state": "current", "session_state": "closed",
                           "access_token": "PRIVATE_VENDOR_KEY"},
                   "VIX": {"price": 17.3, "band": "normal", "stale": False}},
        "sessions": {"us": {"state": "closed", "calendar_verified": True, "data_frozen": True},
                     "cn": {"state": "closed", "calendar_verified": True}},
        "tickers": {"PRIVATE_RAW_TAPE": {"trade_id": "never-forward"}},
        **changes,
    }


def risk_payload(**changes):
    return {
        "schema": "market_risk/v1", "verdict": "MIXED", "score": 58, "asof": "2026-10-09",
        "built": "2026-10-10T00:08:00Z", "stale_after": "2026-10-10T02:00:00Z",
        "stale": False, "is_display_only": True, "source_basis": "settled",
        "freshness": {"qualified": True, "reasons": []}, **changes,
    }


class PublicProjectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from integrations.product_access_mcp import contracts, projections, schemas
        from jsonschema import Draft202012Validator, FormatChecker
        self.contracts, self.projections = contracts, projections
        self.validators = {
            row["name"]: Draft202012Validator(row["outputSchema"], format_checker=FormatChecker())
            for row in schemas.TOOL_SPECS
        }
        self.payloads = {"macro_overlay": overlay_payload(), "market_risk": risk_payload()}
        self.raw, self.responses, self.calls = {}, {}, []
        test = self
        class Port:
            async def read(self, endpoint, *, symbols=()):
                test.calls.append((endpoint, symbols))
                if endpoint in test.responses:
                    return test.responses[endpoint]
                body = test.raw.get(endpoint, json.dumps(test.payloads[endpoint]).encode())
                return contracts.HttpObservation(status=200, body=body, content_type="application/json")
        from integrations.product_access_mcp.reader import ProductReader
        self.reader = ProductReader(transport=Port(), now=lambda: PROJECTION_NOW)

    async def observe(self, endpoint):
        result = await getattr(self.reader, endpoint)()
        self.validators["product_" + endpoint].validate(result)
        self.projections.validate_projection_result(result)
        return result

    async def test_overlay_is_delayed_unqualified_context_without_prices_or_tape(self):
        result = await self.observe("macro_overlay")
        row = result["observations"][0]
        data = row["data"]
        self.assertEqual(row["source_owner"], "macro-api")
        self.assertEqual(self.calls, [("macro_overlay", ())])
        self.assertEqual(data["built"]["value"], "2026-10-10T00:05:00Z")
        self.assertEqual(data["built"]["age_seconds"], 300)
        self.assertEqual(data["market"]["SPY"]["data_state"], "current")
        self.assertTrue(data["sessions"]["cn"]["calendar_verified"])
        self.assertEqual(data["freshness"]["state"], "partial")
        self.assertFalse(data["freshness"]["qualified"])
        self.assertIn("reported_delayed_feed", data["freshness"]["reasons"])
        for secret in ("price", "PRIVATE_RAW_TAPE", "PRIVATE_VENDOR_KEY", "access_token"):
            self.assertNotIn(secret, json.dumps(result))

    async def test_overlay_delay_realtime_conflict_remains_explicit(self):
        self.payloads["macro_overlay"].update(realtime=True, n_fresh=0)
        data = (await self.observe("macro_overlay"))["observations"][0]["data"]
        self.assertIn("reported_delay_realtime_conflict", data["freshness"]["reasons"])
        self.assertIn("no_fresh_quote_claim", data["freshness"]["reasons"])
        self.assertFalse(data["freshness"]["qualified"])

    async def test_overlay_context_strings_are_closed_and_unknown_calendar_is_not_verified(self):
        self.payloads["macro_overlay"]["market"]["SPY"].update(
            data_state="PRIVATE_INSTRUCTION", band="PRIVATE_BAND", data_through="20261009")
        self.payloads["macro_overlay"]["sessions"]["us"].update(
            state="PRIVATE_SESSION", calendar_verified="yes", expected_session="2026-W41-5")
        data = (await self.observe("macro_overlay"))["observations"][0]["data"]
        self.assertEqual(data["market"]["SPY"]["data_state"], "other")
        self.assertIsNone(data["market"]["SPY"]["data_through"])
        self.assertIsNone(data["sessions"]["us"]["calendar_verified"])
        self.assertNotIn("PRIVATE_", json.dumps(data))

    async def test_overlay_shape_and_noncanonical_builds_fail_without_data(self):
        for changes in ({"schema": "other"}, {"built": None}, {"built": "2026-10-10 00:11:00 UTC"},
                        {"built": "20261010T000500Z"}, {"built": "2026-W41-6T00:05:00Z"},
                        {"built": "2026-10-10 00:05:00+00:00"}, {"built": "2026-10-10T00:05:00+00:60"},
                        {"n": True}, {"n_fresh": 4}, {"n_quotes": -1},
                        {"delayed_min": False}, {"realtime": "true"}, {"sessions": None}, {"market": None}):
            with self.subTest(changes=changes):
                self.payloads["macro_overlay"] = overlay_payload(**changes)
                row = (await self.observe("macro_overlay"))["observations"][0]
                self.assertEqual(row["state"], "invalid")
                self.assertIsNone(row["data"])

    async def test_projection_caps_apply_in_decoder_and_do_not_widen_old_tools(self):
        self.payloads["macro_overlay"]["ignored"] = "x" * (256 * 1024 + 100)
        row = (await self.observe("macro_overlay"))["observations"][0]
        self.assertEqual(row["state"], "observed")
        self.assertGreater(row["body_bytes"], 256 * 1024)
        self.assertLess(len(json.dumps(row)), 16384)
        for endpoint, cap in (("macro_overlay", 512 * 1024), ("market_risk", 64 * 1024)):
            with self.subTest(endpoint=endpoint):
                self.raw[endpoint] = b"x" * (cap + 1)
                row = (await self.observe(endpoint))["observations"][0]
                self.assertEqual(row["state"], "invalid")
                self.assertEqual(row["representation"], "not_observed")
                self.assertIsNone(row["sha256"])
                self.assertIsNone(row["body_bytes"])
        with self.assertRaises(ValueError):
            self.contracts.strict_json(b" " * (256 * 1024) + b"{}")

    async def test_empty_and_invalid_complete_bodies_keep_truthful_digest(self):
        for body in (b"", b"null", b"[]", b"{bad", b'{"schema":"x","schema":"y"}',
                     b'{"unused":NaN}', b'{"unused":1e9999}'):
            with self.subTest(body=body):
                self.raw["market_risk"] = body
                row = (await self.observe("market_risk"))["observations"][0]
                self.assertEqual(row["state"], "invalid")
                self.assertIsNone(row["data"])
                self.assertEqual(row["representation"], "complete")
                self.assertEqual(row["body_bytes"], len(body))
                self.assertEqual(row["sha256"], hashlib.sha256(body).hexdigest())

    async def test_transport_refusals_have_no_fabricated_body_evidence(self):
        for response, state in (
            (self.contracts.HttpObservation(200, error="response_too_large"), "invalid"),
            (self.contracts.HttpObservation(302, error="redirect_refused"), "invalid"),
            (self.contracts.HttpObservation(None, error="timeout"), "unavailable"),
            (self.contracts.HttpObservation(403), "unauthorized"),
            (self.contracts.HttpObservation(404), "missing"),
            (self.contracts.HttpObservation(204), "missing"),
        ):
            with self.subTest(response=response):
                self.responses["market_risk"] = response
                row = (await self.observe("market_risk"))["observations"][0]
                self.assertEqual(row["state"], state)
                self.assertEqual(row["representation"], "not_observed")
                self.assertIsNone(row["sha256"])

    async def test_settled_risk_preserves_owner_verdict_with_optional_event_clock(self):
        row = (await self.observe("market_risk"))["observations"][0]
        data = row["data"]
        self.assertEqual(row["source_owner"], "terminal-market-data")
        self.assertEqual(data["verdict"], "MIXED")
        self.assertEqual(data["score"], 58)
        self.assertTrue(data["is_display_only"])
        self.assertEqual(data["source_event_time"]["status"], "unknown")
        self.assertTrue(data["freshness"]["qualified"])
        self.assertEqual(self.calls, [("market_risk", ())])

    async def test_risk_requires_literal_source_display_authority(self):
        for value in (None, False, 1, "true"):
            with self.subTest(value=value):
                self.payloads["market_risk"] = risk_payload(is_display_only=value)
                row = (await self.observe("market_risk"))["observations"][0]
                self.assertEqual(row["state"], "invalid")
                self.assertIsNone(row["data"])

    async def test_missing_risk_score_or_clocks_are_partial_without_invented_values(self):
        for changes, reason in (
            ({"score": None}, "score_unavailable"),
            ({"built": None}, "build_unavailable"),
            ({"stale_after": None}, "unqualified_intraday_expiry"),
            ({"source_basis": None}, "unknown_source_basis"),
            ({"stale": None}, "owner_stale_unknown"),
        ):
            with self.subTest(changes=changes):
                self.payloads["market_risk"] = risk_payload(**changes)
                data = (await self.observe("market_risk"))["observations"][0]["data"]
                self.assertEqual(data["freshness"]["state"], "partial")
                self.assertIn(reason, data["freshness"]["reasons"])
                self.assertFalse(data["freshness"]["qualified"])
                if "score" in changes:
                    self.assertIsNone(data["score"])

    async def test_zero_score_is_observed_and_boolean_score_is_invalid(self):
        for score, state in ((0, "observed"), (False, "invalid"), (-1, "invalid"), (101, "invalid")):
            with self.subTest(score=score):
                self.payloads["market_risk"] = risk_payload(score=score)
                row = (await self.observe("market_risk"))["observations"][0]
                self.assertEqual(row["state"], state)
                if state == "observed":
                    self.assertEqual(row["data"]["score"], 0)

    async def test_owner_refused_missing_or_malformed_freshness_never_becomes_healthy(self):
        for owner in (None, {}, {"qualified": False, "reasons": []},
                      {"qualified": True}, {"qualified": True, "reasons": None},
                      {"qualified": True, "reasons": "PRIVATE_REASON"},
                      {"qualified": True, "reasons": ["invalid_built"]},
                      {"qualified": True, "reasons": ["PRIVATE_REASON"]},
                      {"qualified": True, "reasons": [False]},
                      {"qualified": True, "reasons": ["owner_stale"] * 33},
                      {"qualified": 1, "reasons": []}):
            with self.subTest(owner=owner):
                self.payloads["market_risk"] = risk_payload(freshness=owner)
                data = (await self.observe("market_risk"))["observations"][0]["data"]
                self.assertFalse(data["freshness"]["qualified"])
                self.assertTrue(data["freshness"]["reasons"])
                self.assertNotIn("PRIVATE_REASON", json.dumps(data))

    async def test_literal_stale_future_build_and_expiry_are_distinct_stale_reasons(self):
        for changes, reason in (
            ({"stale": True}, "owner_stale"),
            ({"built": "2026-10-10T00:10:01Z"}, "future_build"),
            ({"source_event_time": "2026-10-10T00:10:01Z"}, "future_source_event"),
            ({"stale_after": "2026-10-10T00:10:00Z"}, "elapsed_expiry"),
        ):
            with self.subTest(changes=changes):
                self.payloads["market_risk"] = risk_payload(**changes)
                data = (await self.observe("market_risk"))["observations"][0]["data"]
                self.assertEqual(data["freshness"]["state"], "stale")
                self.assertIn(reason, data["freshness"]["reasons"])

    async def test_noncanonical_risk_clocks_never_qualify(self):
        for field in ("built", "source_event_time", "stale_after"):
            for value in ("20261010T000500Z", "2026-W41-6T00:05:00Z",
                          "2026-10-10 00:05:00 UTC", "2026-10-10T00:05:00",
                          "2026-10-10T00:05:00+00:60"):
                with self.subTest(field=field, value=value):
                    self.payloads["market_risk"] = risk_payload(**{field: value})
                    data = (await self.observe("market_risk"))["observations"][0]["data"]
                    self.assertEqual(data[field]["status"], "invalid")
                    self.assertFalse(data["freshness"]["qualified"])

    async def test_risk_session_date_is_strict_and_not_future_in_new_york(self):
        for value in ("20261009", "2026-W41-5", "2026-02-30", "2026-10-10", None):
            with self.subTest(value=value):
                self.payloads["market_risk"] = risk_payload(asof=value)
                self.assertEqual((await self.observe("market_risk"))["observations"][0]["state"], "invalid")

    async def test_live_event_uses_new_york_session_and_preserves_pending_band_verdict(self):
        self.payloads["market_risk"] = risk_payload(
            source_basis="live_display", cause_basis="live_score_pending_band",
            source_event_time="2026-10-10T00:05:00Z", asof="2026-10-09", score=95)
        data = (await self.observe("market_risk"))["observations"][0]["data"]
        self.assertTrue(data["freshness"]["qualified"])
        self.assertEqual(data["verdict"], "MIXED")
        self.assertEqual(data["cause_basis"], "live_score_pending_band")
        self.payloads["market_risk"]["asof"] = "2026-10-08"
        data = (await self.observe("market_risk"))["observations"][0]["data"]
        self.assertIn("source_session_mismatch", data["freshness"]["reasons"])

    async def test_live_clock_missing_and_settled_pending_band_cannot_qualify(self):
        for changes, reason in (
            ({"source_basis": "live_display"}, "missing_live_source_clock"),
            ({"cause_basis": "live_score_pending_band"}, "invalid_cause_basis"),
        ):
            with self.subTest(changes=changes):
                self.payloads["market_risk"] = risk_payload(**changes)
                data = (await self.observe("market_risk"))["observations"][0]["data"]
                self.assertFalse(data["freshness"]["qualified"])
                self.assertIn(reason, data["freshness"]["reasons"])

    async def test_final_contract_rejects_forged_qualified_risk(self):
        for changes in ({"score": None}, {"stale": True}, {"stale_after": None},
                        {"freshness": {"qualified": False, "reasons": []}}):
            with self.subTest(changes=changes):
                self.payloads["market_risk"] = risk_payload(**changes)
                result = await self.observe("market_risk")
                result["observations"][0]["data"]["freshness"] = {
                    "state": "qualified", "qualified": True, "reasons": []}
                self.validators["product_market_risk"].validate(result)
                with self.assertRaises(ValueError):
                    self.projections.validate_projection_result(result)

    async def test_final_contract_refuses_clock_and_owner_reason_count_laundering(self):
        result = await self.observe("market_risk")
        for target, value in (("clock", 0), ("reasons", 1)):
            with self.subTest(target=target):
                changed = copy.deepcopy(result)
                data = changed["observations"][0]["data"]
                if target == "clock":
                    data["built"]["age_seconds"] = value
                else:
                    data["owner_freshness"]["reasons"]["count"] = value
                self.validators["product_market_risk"].validate(changed)
                with self.assertRaises(ValueError):
                    self.projections.validate_projection_result(changed)

    async def test_final_closed_schema_refuses_overlay_prices_and_promotions(self):
        from jsonschema import ValidationError
        result = await self.observe("macro_overlay")
        for change in ("price", "qualified"):
            with self.subTest(change=change):
                forged = copy.deepcopy(result)
                data = forged["observations"][0]["data"]
                if change == "price":
                    data["market"]["SPY"]["price"] = 620
                else:
                    data["freshness"] = {"state": "qualified", "qualified": True, "reasons": []}
                with self.assertRaises(ValidationError):
                    self.validators["product_macro_overlay"].validate(forged)

    async def test_empty_body_cannot_be_relabelled_as_an_observed_risk(self):
        from jsonschema import ValidationError
        result = await self.observe("market_risk")
        result["observations"][0].update(body_bytes=0, sha256=hashlib.sha256(b"").hexdigest())
        with self.assertRaises(ValidationError):
            self.validators["product_market_risk"].validate(result)
