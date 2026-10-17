"""Tests for the Stage 00A decision availability selector."""

import copy
import datetime
import math
import unittest

from app.decision_availability_selection import select_decision_records

BOOK = "book-alpha"
OTHER_BOOK = "book-beta"
OBSERVED = "2026-10-17T00:00:00+00:00"

ACCEPTED_OCT9 = {
    "asof": "2026-10-09",
    "ts": "2026-10-09T23:13:48+00:00",
    "decision_id": "decision.v1.ad22d1f6456abcca4a4c0845",
    "run_id": "2026-10-09T23-10-09-296Z00-00",
    "target_status": "queued",
    "decision_effective": True,
    "holdings": [],
    "summary": "Deliberate all-cash",
}

FAILURE_OCT15 = {
    "asof": "2026-10-15",
    "ts": "2026-10-15T23:10:17+00:00",
    "run_id": "2026-10-15T23-10-11-457Z00-00",
    "target_status": "rejected_no_submission",
    "decision_effective": False,
    "holdings": [],
    "error": "provider failure",
}


def bound(row):
    item = dict(row)
    item["portfolio_id"] = BOOK
    return item


def foreign(row, book=OTHER_BOOK):
    item = dict(row)
    item["portfolio_id"] = book
    return item


class BaseCase(unittest.TestCase):
    def select(self, rows=(), attempts=None, **kwargs):
        return select_decision_records(
            BOOK, rows, observed_at=OBSERVED, bound_attempts=attempts, **kwargs
        )

    def assertIssue(self, result, code):
        self.assertIn(code, result["issues"], result["issues"])


class ShapeCase(BaseCase):
    def test_result_shape_is_fixed(self):
        result = self.select([ACCEPTED_OCT9])
        self.assertEqual(
            sorted(result),
            sorted(
                [
                    "last_valid",
                    "latest_attempt",
                    "latest_attempt_kind",
                    "coverage_status",
                    "attempt_coverage",
                    "issues",
                    "origin_lineage_status",
                ]
            ),
        )
        self.assertEqual(result["attempt_coverage"], "partial")

    def test_verified_empty_history_is_not_missing(self):
        empty = self.select([])
        missing = select_decision_records(
            BOOK, [], observed_at=OBSERVED, history_status="missing"
        )
        self.assertEqual(empty["coverage_status"], "available")
        self.assertEqual(empty["issues"], ["empty_history"])
        self.assertIsNone(empty["last_valid"])
        self.assertEqual(empty["latest_attempt_kind"], "unknown")
        self.assertEqual(missing["coverage_status"], "missing")
        self.assertEqual(missing["origin_lineage_status"], "unavailable")

    def test_none_rows_and_bad_shapes(self):
        result = select_decision_records(BOOK, None, observed_at=OBSERVED)
        self.assertEqual(result["coverage_status"], "missing")
        self.assertIssue(result, "rows_missing")
        scalar = self.select("not-a-list")
        self.assertEqual(scalar["coverage_status"], "invalid")
        self.assertIssue(scalar, "rows_shape_invalid")
        mixed = self.select([ACCEPTED_OCT9, 42])
        self.assertIssue(mixed, "row_shape_invalid")
        self.assertEqual(mixed["coverage_status"], "partial")

    def test_observed_at_contract(self):
        for bad in (
            "2026-10-17T00:00:00",
            "not-a-time",
            123,
            "2026-10-17",
        ):
            with self.assertRaises(ValueError):
                select_decision_records(BOOK, [], observed_at=bad)
        with self.assertRaises(ValueError):
            select_decision_records("", [], observed_at=OBSERVED)
        with self.assertRaises(ValueError):
            select_decision_records(BOOK, [], observed_at=OBSERVED, history_status=7)


class AcceptanceCase(BaseCase):
    def test_all_cash_acceptance(self):
        result = self.select([ACCEPTED_OCT9])
        self.assertEqual(result["last_valid"], ACCEPTED_OCT9)
        self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
        self.assertEqual(result["latest_attempt_kind"], "accepted")
        self.assertEqual(result["coverage_status"], "available")
        # run_id present, submission/target hashes absent -> partial lineage.
        self.assertEqual(result["origin_lineage_status"], "partial")

    def test_complete_lineage_requires_hashes(self):
        row = dict(ACCEPTED_OCT9)
        row["submission_sha256"] = "a" * 64
        row["target_sha256"] = "b" * 64
        result = self.select([row])
        self.assertEqual(result["origin_lineage_status"], "complete")

    def test_summary_and_copied_holdings_never_validate(self):
        row = dict(ACCEPTED_OCT9)
        row["decision_id"] = "decision.v1.ZZZZ"
        result = self.select([row])
        self.assertIsNone(result["last_valid"])
        self.assertIssue(result, "invalid_decision_fields")

        row2 = dict(ACCEPTED_OCT9)
        row2["decision_effective"] = 1
        result2 = self.select([row2])
        self.assertIsNone(result2["last_valid"])
        self.assertIssue(result2, "invalid_decision_fields")

        row3 = dict(ACCEPTED_OCT9)
        row3["holdings"] = "[]"
        result3 = self.select([row3])
        self.assertIsNone(result3["last_valid"])

        row4 = dict(ACCEPTED_OCT9)
        del row4["decision_effective"]
        result4 = self.select([row4])
        self.assertIsNone(result4["last_valid"])
        self.assertIssue(result4, "invalid_decision_fields")

    def test_accepted_then_adapter_error_stays_accepted(self):
        row = dict(ACCEPTED_OCT9)
        row["error"] = "adapter post-bookkeeping failure"
        result = self.select([row])
        self.assertEqual(result["last_valid"], row)
        self.assertEqual(result["latest_attempt_kind"], "accepted_with_error")

    def test_bare_executed_empty_holdings_is_accepted_not_no_trade(self):
        row = dict(ACCEPTED_OCT9)
        row["target_status"] = "executed"
        result = self.select([row])
        self.assertEqual(result["latest_attempt_kind"], "accepted")
        self.assertEqual(result["last_valid"], row)

    def test_failed_stub_does_not_replace_accepted_intent(self):
        result = self.select([ACCEPTED_OCT9, FAILURE_OCT15])
        self.assertEqual(result["last_valid"], ACCEPTED_OCT9)
        self.assertEqual(result["latest_attempt"], FAILURE_OCT15)
        self.assertEqual(result["latest_attempt_kind"], "failed")
        self.assertEqual(result["coverage_status"], "available")


class BindingCase(BaseCase):
    def test_same_day_journal_accepted_with_later_bound_failure(self):
        expected = bound(FAILURE_OCT15)
        result = self.select([ACCEPTED_OCT9], attempts=[expected])
        self.assertEqual(result["last_valid"], ACCEPTED_OCT9)
        self.assertEqual(result["latest_attempt"], expected)
        self.assertEqual(result["latest_attempt_kind"], "failed")
        self.assertEqual(result["coverage_status"], "available")

    def test_unbound_newer_attempt_cannot_win(self):
        result = self.select([ACCEPTED_OCT9], attempts=[FAILURE_OCT15])
        self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
        self.assertEqual(result["latest_attempt_kind"], "accepted")
        self.assertIssue(result, "attempt_unbound")
        self.assertEqual(result["coverage_status"], "partial")

    def test_foreign_newer_run_cannot_affect_selection(self):
        newer = dict(ACCEPTED_OCT9)
        newer["asof"] = "2026-10-16"
        newer["ts"] = "2026-10-16T10:00:00+00:00"
        newer["run_id"] = "2026-10-16T10-00-00-000Z00-00"
        result = self.select([ACCEPTED_OCT9, foreign(newer)])
        self.assertEqual(result["last_valid"], ACCEPTED_OCT9)
        self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
        self.assertIssue(result, "foreign_book_row")
        self.assertEqual(result["coverage_status"], "partial")

    def test_book_alias_without_canonical_portfolio_id_does_not_bind_attempt(self):
        attempt = dict(FAILURE_OCT15)
        attempt["book"] = BOOK
        result = self.select([ACCEPTED_OCT9], attempts=[attempt])
        self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
        self.assertIssue(result, "attempt_unbound")

    def test_same_run_id_across_books_is_identity_conflict(self):
        result = self.select(
            [ACCEPTED_OCT9], attempts=[foreign(FAILURE_OCT15 | {"run_id": ACCEPTED_OCT9["run_id"]})]
        )
        self.assertIssue(result, "identity_conflict")
        self.assertIsNone(result["last_valid"])
        self.assertIsNone(result["latest_attempt"])
        self.assertEqual(result["coverage_status"], "partial")

    def test_contradictory_binding_metadata(self):
        row = dict(ACCEPTED_OCT9)
        row["portfolio_id"] = BOOK
        row["book"] = OTHER_BOOK
        result = self.select([row])
        self.assertIssue(result, "binding_contradiction")
        self.assertIsNone(result["last_valid"])
        row2 = dict(ACCEPTED_OCT9)
        row2["portfolio_id"] = 123
        result2 = self.select([row2])
        self.assertIssue(result2, "row_binding_malformed")


class OrderingCase(BaseCase):
    def test_malformed_future_and_nonfinite_clocks(self):
        malformed = dict(FAILURE_OCT15, ts="not-a-time")
        future = dict(
            FAILURE_OCT15,
            run_id="2026-10-20T00-00-00-000Z00-00",
            ts="2026-10-20T00:00:00+00:00",
            asof="2026-10-20",
        )
        nonfinite = dict(FAILURE_OCT15, run_id="r-nan", note=float("nan"))
        result = self.select([ACCEPTED_OCT9, malformed, future, nonfinite])
        self.assertEqual(result["last_valid"], ACCEPTED_OCT9)
        self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
        self.assertIssue(result, "row_ts_malformed")
        self.assertIssue(result, "row_future_event")
        self.assertIssue(result, "row_nonfinite")
        self.assertEqual(result["coverage_status"], "partial")

    def test_date_only_and_missing_clocks(self):
        date_only = {
            "asof": "2026-10-12",
            "run_id": "2026-10-12T00-00-00-000Z00-00",
            "target_status": "rejected_no_submission",
            "decision_effective": False,
            "holdings": [],
        }
        bad_asof = dict(date_only, run_id="r-bad", asof="10/12/2026")
        no_clock = {"run_id": "r-noclock", "target_status": "unknown"}
        result = self.select([ACCEPTED_OCT9, date_only, bad_asof, no_clock])
        self.assertEqual(result["latest_attempt"], date_only)
        self.assertEqual(result["latest_attempt_kind"], "failed")
        self.assertIssue(result, "row_asof_malformed")
        self.assertIssue(result, "row_clock_missing")

    def test_tied_date_only_conflict_not_resolved_by_order(self):
        early = {
            "asof": "2026-10-15",
            "run_id": "run-early",
            "target_status": "rejected_no_submission",
            "decision_effective": False,
            "holdings": [],
        }
        late = dict(early, run_id="run-late")
        forward = self.select([ACCEPTED_OCT9, early, late])
        reversed_rows = self.select([late, early, ACCEPTED_OCT9])
        self.assertIsNone(forward["latest_attempt"])
        self.assertIsNone(reversed_rows["latest_attempt"])
        self.assertEqual(forward, reversed_rows)
        self.assertIssue(forward, "ambiguous_latest_tie")
        self.assertEqual(forward["coverage_status"], "partial")
        self.assertEqual(forward["last_valid"], ACCEPTED_OCT9)

    def test_date_only_same_day_as_instant_is_ambiguous(self):
        carry = {
            "asof": "2026-10-15",
            "run_id": "run-carry",
            "target_status": "frozen_held_quote_fallback",
            "decision_effective": False,
            "holdings": [],
        }
        instant = dict(FAILURE_OCT15)  # 2026-10-15T23:10:17+00:00
        result = self.select([ACCEPTED_OCT9, carry, instant])
        self.assertIsNone(result["latest_attempt"])
        self.assertIssue(result, "ambiguous_latest_tie")
        self.assertEqual(result["coverage_status"], "partial")
        self.assertEqual(result["last_valid"], ACCEPTED_OCT9)

    def test_tied_instant_acceptance_conflict(self):
        other = dict(ACCEPTED_OCT9)
        other["run_id"] = "2026-10-09T23-10-09-999Z00-00"
        other["decision_id"] = "decision.v1.bb22d1f6456abcca4a4c0845"
        result = self.select([ACCEPTED_OCT9, other])
        self.assertIsNone(result["last_valid"])
        self.assertIsNone(result["latest_attempt"])
        self.assertIssue(result, "ambiguous_latest_tie")


class DuplicateCase(BaseCase):
    def test_exact_duplicates_dedupe(self):
        result = self.select([ACCEPTED_OCT9, copy.deepcopy(ACCEPTED_OCT9)])
        self.assertEqual(result["last_valid"], ACCEPTED_OCT9)
        self.assertNotIn("identity_conflict", result["issues"])
        self.assertEqual(result["coverage_status"], "available")

    def test_conflicting_duplicate_identity(self):
        conflict = dict(ACCEPTED_OCT9)
        conflict["target_status"] = "rejected_no_submission"
        conflict["decision_effective"] = False
        result = self.select([ACCEPTED_OCT9, conflict])
        self.assertIssue(result, "identity_conflict")
        self.assertIsNone(result["last_valid"])
        self.assertIsNone(result["latest_attempt"])
        self.assertEqual(result["coverage_status"], "partial")


class ClassificationCase(BaseCase):
    def test_explicit_protective_carry_evidence(self):
        carry = {
            "asof": "2026-10-14",
            "run_id": "run-carry",
            "target_status": "frozen_held_quote_fallback",
            "decision_effective": False,
            "holdings": [],
        }
        result = self.select([ACCEPTED_OCT9, carry])
        self.assertEqual(result["latest_attempt"], carry)
        self.assertEqual(result["latest_attempt_kind"], "protective_carry")

    def test_prose_only_carry_is_unknown(self):
        prose = {
            "asof": "2026-10-14",
            "run_id": "run-prose",
            "target_status": "deferred",
            "decision_effective": False,
            "holdings": [],
            "summary": "protective carry requested",
        }
        result = self.select([ACCEPTED_OCT9, prose])
        self.assertEqual(result["latest_attempt"], prose)
        self.assertEqual(result["latest_attempt_kind"], "unknown")

    def test_malformed_history_status(self):
        result = self.select(
            [ACCEPTED_OCT9], history_status="mysterious"
        )
        self.assertEqual(result["coverage_status"], "unknown")
        self.assertIssue(result, "history_unknown_status")
        partial = self.select([ACCEPTED_OCT9], history_status="partial")
        self.assertEqual(partial["coverage_status"], "partial")
        self.assertEqual(partial["last_valid"], ACCEPTED_OCT9)
        corrupt = self.select([ACCEPTED_OCT9], history_status="corrupt")
        self.assertEqual(corrupt["coverage_status"], "invalid")
        self.assertEqual(corrupt["origin_lineage_status"], "unavailable")


class PurityCase(BaseCase):
    def test_inputs_not_mutated_and_outputs_not_aliased(self):
        rows = [ACCEPTED_OCT9, FAILURE_OCT15]
        attempts = [
            bound(
                dict(
                    FAILURE_OCT15,
                    run_id="2026-10-16T01-00-00-000Z00-00",
                    asof="2026-10-16",
                    ts="2026-10-16T01:00:00+00:00",
                )
            )
        ]
        snapshot = copy.deepcopy((rows, attempts))
        result = select_decision_records(
            BOOK, rows, observed_at=OBSERVED, bound_attempts=attempts
        )
        self.assertEqual((rows, attempts), snapshot)
        self.assertIsNot(result["last_valid"], ACCEPTED_OCT9)
        self.assertIsNot(result["latest_attempt"], FAILURE_OCT15)
        rows.append({"asof": "2026-10-16"})
        self.assertIsNotNone(result["latest_attempt"])

    def test_row_reordering_preserves_semantics(self):
        rows = [
            ACCEPTED_OCT9,
            FAILURE_OCT15,
            dict(
                FAILURE_OCT15,
                asof="2026-10-12",
                run_id="2026-10-12T00-00-00-000Z00-00",
                ts=None,
            ),
        ]
        forward = self.select(rows)
        backward = self.select(list(reversed(rows)))
        shuffled = self.select([rows[1], rows[2], rows[0]])
        self.assertEqual(forward, backward)
        self.assertEqual(forward, shuffled)
        self.assertEqual(forward["last_valid"], ACCEPTED_OCT9)
        self.assertEqual(forward["latest_attempt"], FAILURE_OCT15)
        self.assertEqual(forward["issues"], sorted(forward["issues"]))



class ParentReviewRegressionCase(BaseCase):
    """Counterexamples found in parent review of the delivered selector."""

    def test_unhashable_statuses_are_qualified_instead_of_crashing(self):
        for status in ({}, [], ["queued"], {"status": "queued"}):
            with self.subTest(status=status):
                row = dict(ACCEPTED_OCT9, target_status=status)
                result = self.select([row])
                self.assertIsNone(result["last_valid"])
                self.assertIssue(result, "invalid_decision_fields")
                self.assertEqual(result["latest_attempt_kind"], "unknown")

    def test_lineage_requires_real_hashes_and_full_decision_identity(self):
        for bad in ("x", "G" * 64, "a" * 64 + "\n", ""):
            with self.subTest(hash=bad):
                row = dict(ACCEPTED_OCT9, submission_sha256=bad, target_sha256="b" * 64)
                self.assertEqual(self.select([row])["origin_lineage_status"], "partial")
        row = dict(ACCEPTED_OCT9, decision_id=ACCEPTED_OCT9["decision_id"] + "\n")
        self.assertIsNone(self.select([row])["last_valid"])

    def test_guessed_carry_flags_cannot_claim_a_canonical_protective_freeze(self):
        for fields in ({"freeze": True}, {"carry": True}, {"protective_carry": True},
                       {"target_status": "frozen"}, {"target_status": "protective_carry"}):
            row = dict(FAILURE_OCT15, target_status="unknown", **{
                key: value for key, value in fields.items() if key != "target_status"})
            row["target_status"] = fields.get("target_status", "unknown")
            self.assertEqual(self.select([row])["latest_attempt_kind"], "unknown")
        row["target_status"] = "frozen_held_quote_fallback"
        self.assertEqual(self.select([row])["latest_attempt_kind"], "protective_carry")

    def test_supplied_null_or_malformed_ts_cannot_silently_use_asof(self):
        for bad in (None, "", "bad", 0, False):
            row = dict(FAILURE_OCT15, ts=bad)
            result = self.select([ACCEPTED_OCT9, row])
            self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
            self.assertIssue(result, "row_ts_malformed")

    def test_midnight_point_overlaps_date_only_day(self):
        point = dict(FAILURE_OCT15, ts="2026-10-15T00:00:00+00:00")
        interval = dict(FAILURE_OCT15, run_id="different-run")
        interval.pop("ts")
        result = self.select([ACCEPTED_OCT9, point, interval])
        self.assertIsNone(result["latest_attempt"])
        self.assertIssue(result, "ambiguous_latest_tie")

    def test_contradictory_declared_binding_poisoning_same_run_is_visible(self):
        conflicting = dict(ACCEPTED_OCT9, portfolio_id=BOOK, book=OTHER_BOOK)
        result = self.select([ACCEPTED_OCT9], attempts=[conflicting])
        self.assertIssue(result, "identity_conflict")
        self.assertIsNone(result["last_valid"])

    def test_conflicting_decision_identity_across_runs_is_not_latest_wins(self):
        conflict = dict(ACCEPTED_OCT9, run_id="different-run", asof="2026-10-15",
                        ts="2026-10-15T01:00:00+00:00")
        result = self.select([ACCEPTED_OCT9, conflict])
        self.assertIssue(result, "identity_conflict")
        self.assertIsNone(result["last_valid"])

    def test_invalid_source_status_is_retained(self):
        result = self.select(None, history_status="invalid")
        self.assertEqual(result["coverage_status"], "invalid")

    def test_non_json_cycles_and_overflowing_times_fail_safely(self):
        cyclic = dict(FAILURE_OCT15)
        cyclic["cycle"] = cyclic
        bad = dict(FAILURE_OCT15, ts="0001-01-01T00:00:00+01:00")
        object_row = dict(FAILURE_OCT15, unsupported=object())
        result = self.select([ACCEPTED_OCT9, cyclic, bad, object_row])
        self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
        self.assertIssue(result, "row_shape_invalid")
        self.assertIssue(result, "row_ts_malformed")

    def test_future_asof_cannot_hide_behind_past_ts(self):
        row = dict(FAILURE_OCT15, asof="2099-01-01")
        result = self.select([ACCEPTED_OCT9, row])
        self.assertEqual(result["latest_attempt"], ACCEPTED_OCT9)
        self.assertIssue(result, "row_future_event")

if __name__ == "__main__":
    unittest.main()
