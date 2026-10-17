"""Pure W1 consumer tests; unittest runs without full-app dependencies."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from brain import sovereign_auction_context as SAC

FIX = Path(__file__).parent / "fixtures/sovereign_auction_context"
NOW = "2026-10-08T23:00:00Z"


def fixture(name="event_calendar.json"):
    return json.loads((FIX / name).read_text())["sovereign_auction_context"]


class SovereignAuctionContextTests(unittest.TestCase):
    def test_real_w1_shared_fixture_and_decimal_units(self):
        original = fixture()
        untouched = copy.deepcopy(original)
        actual = SAC.validate_context(original, now=NOW)
        self.assertEqual(original, untouched)
        self.assertEqual(len(actual["events"]), 3)
        self.assertEqual(actual["events"][0]["offering_amount_usd"], original["events"][0]["offering_amount_usd"])
        self.assertIsInstance(actual["events"][0]["offering_amount_usd"], str)
        self.assertEqual(actual["source_health"], original["source_health"])
        self.assertEqual(actual["freshness_label"], "Freshness unassessed")
        self.assertTrue(all(row["result"] is None for row in actual["events"]))
        self.assertEqual(actual["coverage"]["known_upcoming_count"], 3)

    def test_real_single_bill_future_deadline_is_allowed(self):
        context = fixture("bill_event_calendar.json")
        actual = SAC.validate_context(context, now=NOW)["events"][0]
        self.assertEqual(actual["episode_id"], "auction:912797SU2:2026-10-13")
        self.assertEqual(actual["competitive_deadline_utc"], "2026-10-13T17:00:00+00:00")
        self.assertEqual(actual["offering_amount_usd"], "95000000000")
        self.assertEqual(actual["normalized_class"], "Bill")
        self.assertIsNone(actual["result"])
        self.assertEqual(actual["result_evidence_fields"], [])

    def test_explicit_class_facts_cannot_contradict_each_other(self):
        for raw_type, normalized, flags in (
                ("Note", "Note", {}),  # two agreeing labels cannot erase raw Bill
                ("Bill", "Bill", {"tips": "Yes"}),
                ("TIPS", "TIPS", {"tips": "Yes"}),  # TIPS cannot have Bill base
                ("CMB", "CMB", {"cashManagementBillCMB": "No"}),
                ("CMB", "CMB", {"cashManagementBillCMB": "Yes", "tips": "Yes"})):
            context = fixture(); row = context["events"][0]
            row["raw_type"] = raw_type; row["normalized_class"] = normalized
            row["raw_class_flags"].update(flags)
            with self.subTest(raw_type=raw_type, flags=flags), self.assertRaisesRegex(SAC.InvalidContext, "instrument_class_conflict"):
                SAC.validate_context(context, now=NOW)
        context = fixture(); row = context["events"][0]
        row["raw_type"] = row["normalized_class"] = "CMB"
        row["raw_class_flags"]["cashManagementBillCMB"] = "Yes"
        self.assertEqual(SAC.validate_context(context, now=NOW)["events"][0]["normalized_class"], "CMB")
        # Missing schedule flags remain unknown; they are never coerced false.
        context = fixture(); row = context["events"][0]
        row["raw_type"] = ""; row["raw_class_flags"]["cashManagementBillCMB"] = None
        self.assertEqual(SAC.validate_context(context, now=NOW)["events"][0]["normalized_class"], "Bill")

    def test_wrong_schema_and_exact_authority_fail_closed(self):
        for field, values in {"schema_version": ["v2", None], "is_context_only": [1, False, "true"],
                              "forecast_authority": ["LIVE", None], "probabilities": [{}, 0],
                              "importance": ["HIGH", 0]}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    context = fixture(); context[field] = value
                    with self.assertRaises(SAC.InvalidContext):
                        SAC.validate_context(context, now=NOW)
        context = fixture(); del context["probabilities"]
        with self.assertRaises(SAC.InvalidContext):
            SAC.validate_context(context, now=NOW)

    def test_row_authority_is_exact(self):
        for field, bad in (("is_context_only", 1), ("forecast_authority", "TRADE"), ("probabilities", {}), ("importance", "HIGH")):
            context = fixture(); context["events"][0][field] = bad
            with self.subTest(field=field), self.assertRaises(SAC.InvalidContext):
                SAC.validate_context(context, now=NOW)

    def test_future_evidence_is_rejected_without_rejecting_future_calendar(self):
        for location, key in (("root", "source_observed_at"), ("event", "known_at"),
                              ("event", "first_observed_at"), ("health", "latest_attempt_at"),
                              ("health", "last_valid_observation_at"), ("health", "last_successful_body_receipt_at"),
                              ("health", "latest_failure_at"),
                              ("state", "observed_at"), ("receipt", "observed_at"), ("version", "known_at")):
            context = fixture()
            target = {"root": context, "event": context["events"][0], "health": context["source_health"][0],
                      "state": context["source_states"][0], "receipt": context["observation_receipts"][0],
                      "version": context["events"][0]["observation_versions"][0]}[location]
            target[key] = "2026-10-08T22:16:00Z"  # past now, but AFTER producer cutoff
            with self.subTest(location=location, key=key), self.assertRaises(SAC.InvalidContext):
                SAC.validate_context(context, now=NOW)
        with self.assertRaises(SAC.InvalidContext):
            SAC.validate_context(fixture(), now="2026-10-08T22:00:00Z")

    def test_clock_requires_exact_aware_iso(self):
        for bad in ("2026-10-08T22:15:00", "20261008T221500Z", "2026-10-08", 123, True):
            context = fixture(); context["events"][0]["known_at"] = bad
            with self.subTest(bad=bad), self.assertRaises(SAC.InvalidContext):
                SAC.validate_context(context, now=NOW)
        context = fixture(); context["as_of"] = "2026-10-08T22:14:00Z"
        with self.assertRaises(SAC.InvalidContext):
            SAC.validate_context(context, now=NOW)

    def test_numbers_reject_boolean_nonfinite_negative_amounts(self):
        for bad in (True, False, "NaN", "Infinity", float("inf"), float("nan"), "-1", {}, ""):
            context = fixture(); context["events"][0]["offering_amount_usd"] = bad
            with self.subTest(bad=bad), self.assertRaises(SAC.InvalidContext):
                SAC.validate_context(context, now=NOW)
        context = fixture(); context["events"][0]["offering_amount_usd"] = None
        self.assertIsNone(SAC.validate_context(context, now=NOW)["events"][0]["offering_amount_usd"])

    def test_official_https_source_links_only(self):
        for bad in ("javascript:alert(1)", "http://www.treasurydirect.gov/x", "https://evil.test/x",
                    "https://www.treasurydirect.gov.evil.test/x", "https://user@www.treasurydirect.gov/x",
                    "https://www.treasurydirect.gov:444/x", "https://www.treasurydirect.gov/\nx"):
            context = fixture(); context["events"][0]["source_url"] = bad
            with self.subTest(bad=bad), self.assertRaises(SAC.InvalidContext):
                SAC.validate_context(context, now=NOW)

    def test_unknown_risk_fields_are_not_served_at_any_depth(self):
        context = fixture(); context.update({"band": "critical", "stressed": True, "auction_stress": {"stressed": True}})
        context["events"][0].update({"band": "high", "stressed": True})
        context["source_health"][0]["band"] = "high"
        projected = SAC.validate_context(context, now=NOW)
        for forbidden in ('"band"', '"stressed"', '"auction_stress"', '"treasury_auctions"'):
            self.assertNotIn(forbidden, json.dumps(projected))

    def test_source_failure_retains_observation_and_failure_separately(self):
        context = fixture(); context["status"] = "degraded"
        source = context["source_health"][0]
        source.update({"latest_attempt_at": "2026-10-08T22:14:00Z", "latest_attempt_status": "unavailable",
                       "latest_attempt_states": ["unavailable"], "latest_failure_at": "2026-10-08T22:14:00Z",
                       "latest_failure_reasons": ["upstream_503"]})
        actual = SAC.validate_context(context, now=NOW)
        self.assertTrue(actual["available"])
        self.assertEqual(actual["source_health"], context["source_health"])
        self.assertEqual(actual["source_observed_at"], context["source_observed_at"])
        self.assertEqual(actual["freshness_label"], "Freshness unassessed")
        context["source_health"][0]["stale_after_seconds"] = 86400
        with self.assertRaises(SAC.InvalidContext):
            SAC.validate_context(context, now=NOW)

    def test_source_health_clock_order_and_cutoff_age_are_consistent(self):
        for key, bad in (("latest_attempt_at", "2026-10-08T22:00:00Z"),
                         ("last_successful_body_receipt_at", "2026-10-08T22:13:00Z"),
                         ("last_valid_observation_age_seconds", 0),
                         ("last_valid_observation_age_seconds", None)):
            context = fixture(); context["source_health"][0][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(SAC.InvalidContext):
                SAC.validate_context(context, now=NOW)
        # A later page read cannot refresh the source age or claim it is fresh.
        context = fixture()
        later = SAC.validate_context(context, now="2026-10-09T23:00:00Z")
        self.assertEqual(later["source_health"], context["source_health"])
        self.assertEqual(later["freshness_label"], "Freshness unassessed")

    def test_body_arrival_can_precede_valid_observation(self):
        context = fixture(); source = context["source_health"][0]
        body_at = "2026-10-08T22:12:22.400000+00:00"
        source["last_successful_body_receipt_at"] = body_at
        actual = SAC.validate_context(context, now=NOW)
        self.assertEqual(actual["source_health"][0]["last_successful_body_receipt_at"], body_at)
        self.assertEqual(actual["source_health"][0]["last_valid_observation_at"], "2026-10-08T22:12:22.414829+00:00")
        self.assertEqual(actual["source_health"], context["source_health"])
        self.assertEqual(actual["source_observed_at"], context["source_observed_at"])

    def test_legacy_availability_bound_does_not_invent_body_arrival(self):
        context = fixture(); source = context["source_health"][0]
        source["last_successful_body_receipt_at"] = None
        actual = SAC.validate_context(context, now=NOW)
        self.assertTrue(actual["available"])
        self.assertIsNone(actual["source_health"][0]["last_successful_body_receipt_at"])
        self.assertEqual(actual["source_health"][0]["last_valid_observation_at"], source["last_valid_observation_at"])
        self.assertEqual([row["known_at"] for row in actual["events"]], [row["known_at"] for row in context["events"]])
        self.assertEqual(actual["source_observed_at"], context["source_observed_at"])
        self.assertEqual(actual["freshness_label"], "Freshness unassessed")

    def test_later_malformed_body_does_not_refresh_older_valid_observation(self):
        context = fixture(); before = SAC.validate_context(context, now=NOW)
        context["status"] = "degraded"
        source = context["source_health"][0]
        source.update({"latest_attempt_at": "2026-10-08T22:14:00Z", "latest_attempt_status": "degraded",
                       "latest_attempt_states": ["degraded"],
                       "last_successful_body_receipt_at": "2026-10-08T22:13:59.900000+00:00"})
        context["source_states"].append({"source_kind": source["source_kind"], "source_url": source["source_url"],
                                         "observed_at": source["latest_attempt_at"], "status": "degraded",
                                         "receipt_status": "available", "reason": "synthetic_malformed_received_body"})
        actual = SAC.validate_context(context, now=NOW)
        self.assertTrue(actual["available"])
        self.assertEqual(actual["status"], "degraded")
        self.assertEqual(actual["source_health"][0]["last_successful_body_receipt_at"], "2026-10-08T22:13:59.900000+00:00")
        self.assertEqual(actual["source_health"][0]["last_valid_observation_at"], before["source_health"][0]["last_valid_observation_at"])
        self.assertEqual(actual["source_health"][0]["last_valid_observation_age_seconds"], before["source_health"][0]["last_valid_observation_age_seconds"])
        self.assertEqual(actual["source_observed_at"], before["source_observed_at"])
        self.assertEqual(actual["events"], before["events"])

    def test_first_observation_cannot_follow_selected_vintage(self):
        context = fixture(); context["events"][0]["first_observed_at"] = "2026-10-08T22:14:00Z"
        with self.assertRaisesRegex(SAC.InvalidContext, "first_observation_after_selected_vintage"):
            SAC.validate_context(context, now=NOW)
        context = fixture(); context["events"][0]["known_at"] = "2026-10-08T22:14:00Z"
        with self.assertRaisesRegex(SAC.InvalidContext, "row_evidence_after_source_observation"):
            SAC.validate_context(context, now=NOW)

    def test_lifecycle_labels_must_match_the_producer_cutoff(self):
        for bad in ("AWAITING_RESULT", "TENTATIVE"):
            context = fixture(); context["events"][0]["physical_state"] = bad
            with self.subTest(bad=bad), self.assertRaisesRegex(SAC.InvalidContext, "physical_state_cutoff_mismatch"):
                SAC.validate_context(context, now=NOW)
        context = fixture(); context["events"][0]["issue_calendar_state"] = "ISSUE_DATE_PASSED"
        with self.assertRaisesRegex(SAC.InvalidContext, "issue_calendar_state_mismatch"):
            SAC.validate_context(context, now=NOW)
        context = fixture(); context["events"][0]["issue_date"] = "2026-10-07"
        with self.assertRaisesRegex(SAC.InvalidContext, "issue_before_auction"):
            SAC.validate_context(context, now=NOW)

    def test_null_deadline_result_and_unknown_reasons_stay_null(self):
        context = fixture(); row = context["events"][0]
        row["competitive_deadline_utc"] = None; row["time_et"] = None
        row["null_reasons"] = ["missing_competitive_deadline"]
        row["auction_date"] = row["date"] = "2026-10-07"
        row["physical_state"] = "AWAITING_RESULT"
        actual = SAC.validate_context(context, now=NOW)["events"][0]
        self.assertIsNone(actual["competitive_deadline_utc"])
        self.assertIsNone(actual["result"])
        self.assertEqual(actual["physical_state"], "AWAITING_RESULT")
        self.assertEqual(actual["null_reasons"], row["null_reasons"])

    def test_result_requires_observed_evidence_and_finite_numbers(self):
        context = fixture(); row = context["events"][0]
        row["source_state"] = row["physical_state"] = "RESULT_OBSERVED"
        row["auction_date"] = row["date"] = "2026-10-01"
        row["competitive_deadline_utc"] = "2026-10-01T17:00:00Z"
        row["result_evidence_fields"] = ["competitiveAccepted"]
        row["result"] = {"competitive_accepted_usd": "100.5", "real_yield_pct": "-0.5", "bidder_shares": None}
        actual = SAC.validate_context(context, now=NOW)["events"][0]["result"]
        self.assertEqual(actual["competitive_accepted_usd"], "100.5")
        self.assertEqual(actual["real_yield_pct"], "-0.5")
        row["result"]["competitive_accepted_usd"] = True
        with self.assertRaises(SAC.InvalidContext):
            SAC.validate_context(context, now=NOW)

    def test_future_scheduled_row_cannot_claim_results_already_observed(self):
        context = fixture(); row = context["events"][0]
        row["source_state"] = row["physical_state"] = "RESULT_OBSERVED"
        row["result_evidence_fields"] = ["competitiveAccepted"]
        row["result"] = {"competitive_accepted_usd": "100", "bidder_shares": None}
        with self.assertRaises(SAC.InvalidContext):
            SAC.validate_context(context, now=NOW)

    def test_fresh_request_read_and_explicit_off_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event_calendar.json"
            self.assertFalse(SAC.read_context(path, now=NOW)["available"])
            path.write_text((FIX / "event_calendar.json").read_text())
            self.assertTrue(SAC.read_context(path, now=NOW)["available"])
            path.write_text('{}')
            actual = SAC.read_context(path, now=NOW)
            self.assertFalse(actual["available"])
            self.assertEqual(actual["note"], "sovereign_auction_context_not_published")
            path.write_text('not JSON')
            self.assertFalse(SAC.read_context(path, now=NOW)["available"])

    def test_bounds_horizon_counts_and_fresh_projection(self):
        for bad in (True, 0, 366, "30"):
            context = fixture(); context["coverage"]["horizon_days"] = bad
            with self.subTest(bad=bad), self.assertRaises(SAC.InvalidContext):
                SAC.validate_context(context, now=NOW)
        context = fixture(); context["coverage"]["known_upcoming_count"] = True
        with self.assertRaises(SAC.InvalidContext):
            SAC.validate_context(context, now=NOW)
        context = fixture(); actual = SAC.validate_context(context, now=NOW)
        actual["events"][0]["null_reasons"].append("mutated")
        self.assertNotIn("mutated", context["events"][0]["null_reasons"])


if __name__ == '__main__':
    unittest.main()
