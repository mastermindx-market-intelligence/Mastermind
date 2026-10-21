"""Unittests for the Stage 00B performance projection leaf artifact.

Every scenario is deterministic: clocks, prices, history and account state are
supplied explicitly, so no test reads a wall clock, a file, or a network.
"""

from __future__ import annotations

import copy
import datetime
import json
import math
import unittest

from portfolio.performance_projection import project_performance

TODAY = "2026-10-17"
INCEPTION = "2026-10-01"

BASE_STATE = {
    "inception_date": INCEPTION,
    "starting_nav": 10000.0,
    "cash": 4000.0,
    "positions": {"EXAMPLE": {"shares": 60.0, "avg_cost": 100.0}},
}

BASE_ROWS = [
    {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0, "invested": 6000.0},
    {"date": "2026-10-02", "nav": 10100.0, "cash": 4000.0},
    {"date": "2026-10-03", "nav": 9900.0, "cash": 4000.0},
    {"date": "2026-10-16", "nav": 10500.0, "cash": 5000.0},
]

BASE_BENCH = [
    ("2026-10-01", 100.0),
    ("2026-10-02", 101.0),
    ("2026-10-03", 100.5),
    ("2026-10-16", 105.0),
    ("2026-10-17", 106.0),
]

RESULT_KEYS = (
    "inception_date",
    "starting_nav",
    "current_nav",
    "cash",
    "invested",
    "total_return_pct",
    "vs_benchmark_pct",
    "vs_spy_pct",
    "benchmark",
    "benchmark_as_of",
    "day_change_pct",
    "max_drawdown_pct",
    "day_change_window",
    "drawdown_window",
    "realized_since",
    "series",
    "availability",
)

AVAILABILITY_KEYS = (
    "status",
    "account_status",
    "history_status",
    "valuation_basis",
    "as_of",
    "issues",
)


_UNSET = object()


def project(state=_UNSET, rows=_UNSET, bench=_UNSET, **kwargs):
    kwargs.setdefault("benchmark", "SPY")
    kwargs.setdefault("today", TODAY)
    return project_performance(
        BASE_STATE if state is _UNSET else state,
        BASE_ROWS if rows is _UNSET else rows,
        BASE_BENCH if bench is _UNSET else bench,
        **kwargs,
    )


def series_by_date(result):
    return {point["date"]: point for point in result["series"]}


class TestDefaultSnapshot(unittest.TestCase):
    def test_snapshot_projection_is_fully_qualified(self):
        result = project()
        self.assertEqual(result["inception_date"], INCEPTION)
        self.assertEqual(result["starting_nav"], 10000.0)
        self.assertEqual(result["current_nav"], 10500.0)
        # The row's own cash (5000, not today's 4000), invested derived from it.
        self.assertEqual(result["cash"], 5000.0)
        self.assertEqual(result["invested"], 5500.0)
        self.assertEqual(result["total_return_pct"], 5.0)
        self.assertAlmostEqual(result["vs_benchmark_pct"], 0.0, places=9)
        self.assertEqual(result["vs_spy_pct"], result["vs_benchmark_pct"])
        self.assertEqual(result["benchmark"], "SPY")
        self.assertEqual(result["benchmark_as_of"], "2026-10-17")
        self.assertAlmostEqual(result["day_change_pct"], 600.0 / 9900.0 * 100.0)
        self.assertAlmostEqual(result["max_drawdown_pct"], -200.0 / 10100.0 * 100.0)
        self.assertEqual(result["realized_since"], "2026-10-01")
        self.assertEqual(
            result["availability"]["status"], "provisional"
        )
        self.assertEqual(
            result["availability"]["valuation_basis"], "last_recorded_nav"
        )
        self.assertEqual(result["availability"]["as_of"], "2026-10-16")
        # No marks were supplied for the held lot, and the snapshot is stale.
        self.assertEqual(
            result["availability"]["issues"],
            ["unpriced_holdings", "stale_valuation"],
        )

    def test_result_and_availability_surface_shape(self):
        result = project()
        self.assertEqual(tuple(result), RESULT_KEYS)
        self.assertEqual(tuple(result["availability"]), AVAILABILITY_KEYS)
        for point in result["series"]:
            self.assertEqual(tuple(sorted(point)), ("date", "kind", "nav", "spy_nav"))

    def test_reversed_rows_do_not_change_latest_row(self):
        ordered = project()
        reversed_rows = list(reversed(BASE_ROWS))
        flipped = project(rows=reversed_rows)
        self.assertEqual(
            {k: v for k, v in ordered.items() if k != "series"},
            {k: v for k, v in flipped.items() if k != "series"},
        )
        self.assertEqual([row["date"] for row in reversed_rows], [
            "2026-10-16",
            "2026-10-03",
            "2026-10-02",
            "2026-10-01",
        ])


class TestAccountQualification(unittest.TestCase):
    def test_absent_account_is_invalid_not_zero(self):
        result = project(state=None)
        availability = result["availability"]
        self.assertEqual(availability["status"], "unavailable")
        self.assertEqual(availability["account_status"], "invalid")
        self.assertIsNone(result["current_nav"])
        self.assertIsNone(result["cash"])
        self.assertIsNone(result["invested"])
        self.assertIsNone(result["total_return_pct"])
        for code in ("account_invalid", "missing_baseline", "invalid_inception"):
            self.assertIn(code, availability["issues"])
        # Independently readable history is retained.
        kinds = {point["kind"] for point in result["series"]}
        self.assertIn("realized", kinds)
        self.assertEqual(result["realized_since"], "2026-10-01")

    def test_zero_cash_empty_account_is_cash_only_and_minus_100(self):
        state = {
            "inception_date": INCEPTION,
            "starting_nav": 10000.0,
            "cash": 0.0,
            "positions": {},
        }
        result = project(state=state, rows=[], bench=[])
        self.assertEqual(result["availability"]["status"], "available")
        self.assertEqual(result["availability"]["valuation_basis"], "cash_only")
        self.assertEqual(result["current_nav"], 0.0)
        self.assertEqual(result["cash"], 0.0)
        self.assertEqual(result["invested"], 0.0)
        self.assertEqual(result["total_return_pct"], -100.0)
        self.assertEqual(result["day_change_pct"], None)
        self.assertNotIn("account_invalid", result["availability"]["issues"])

    def test_all_zero_share_lots_are_cash_only_without_prices(self):
        state = dict(
            BASE_STATE,
            cash=2500.0,
            positions={"EXAMPLE": {"shares": 0.0, "avg_cost": 100.0}},
        )
        result = project(state=state, prices={})
        self.assertEqual(result["availability"]["valuation_basis"], "cash_only")
        self.assertEqual(result["current_nav"], 2500.0)
        self.assertEqual(result["invested"], 0.0)

    def test_signed_cash_is_preserved_not_clamped(self):
        state = dict(BASE_STATE, cash=-500.0, positions={})
        result = project(state=state, rows=[], bench=[])
        self.assertEqual(result["cash"], -500.0)
        self.assertEqual(result["current_nav"], -500.0)
        self.assertEqual(result["total_return_pct"], -105.0)

    def test_bool_and_nonfinite_and_string_cash_are_invalid(self):
        for bad in (True, False, float("nan"), float("inf"), "4000", [4000.0]):
            state = dict(BASE_STATE, cash=bad)
            result = project(state=state, prices={"EXAMPLE": 150.0})
            self.assertEqual(
                result["availability"]["account_status"],
                "invalid",
                msg="cash=%r should be invalid" % (bad,),
            )
            self.assertIsNone(result["current_nav"])
            self.assertIn("account_invalid", result["availability"]["issues"])

    def test_bool_and_nonfinite_and_negative_shares_are_invalid(self):
        for bad in (True, float("nan"), float("-inf"), "60", -1.0, None):
            state = dict(
                BASE_STATE, positions={"EXAMPLE": {"shares": bad, "avg_cost": 100.0}}
            )
            result = project(state=state, prices={"EXAMPLE": 150.0})
            self.assertIn("account_invalid", result["availability"]["issues"])
            self.assertIsNone(result["current_nav"], msg="shares=%r" % (bad,))

    def test_malformed_positions_container_or_key_is_invalid(self):
        cases = [
            "EXAMPLE",
            [1.0],
            {"": {"shares": 1.0}},
            {7: {"shares": 1.0}},
            {"EXAMPLE": 60.0},
            {"EXAMPLE": {"shares": "1.0"}},
        ]
        for positions in cases:
            state = dict(BASE_STATE, positions=positions)
            result = project(state=state, prices={"EXAMPLE": 150.0})
            self.assertIn(
                "account_invalid",
                result["availability"]["issues"],
                msg="positions=%r" % (positions,),
            )

    def test_non_mapping_state_is_invalid(self):
        for bad in (None, "state", 42, [BASE_STATE]):
            result = project(state=bad, prices={"EXAMPLE": 150.0})
            self.assertEqual(result["availability"]["status"], "unavailable")
            self.assertIn("account_invalid", result["availability"]["issues"])

    def test_account_status_gate_keeps_history_readable(self):
        result = project(account_status="unavailable")
        self.assertEqual(result["availability"]["status"], "unavailable")
        self.assertEqual(result["availability"]["account_status"], "unavailable")
        self.assertIsNone(result["current_nav"])
        self.assertIsNone(result["cash"])
        self.assertEqual(result["realized_since"], "2026-10-01")
        self.assertIn("account_unavailable", result["availability"]["issues"])
        self.assertIn("realized", {p["kind"] for p in result["series"]})

    def test_unknown_account_status_word_fails_safe(self):
        result = project(account_status="weird")
        self.assertEqual(result["availability"]["status"], "unavailable")
        self.assertIn("account_unavailable", result["availability"]["issues"])

    def test_missing_baseline_qualifies_returns_but_keeps_valuation(self):
        state = {
            "cash": 4000.0,
            "positions": {"EXAMPLE": {"shares": 60.0, "avg_cost": 100.0}},
        }
        result = project(state=state, prices={"EXAMPLE": 150.0})
        self.assertEqual(result["starting_nav"], None)
        self.assertEqual(result["inception_date"], None)
        self.assertEqual(result["current_nav"], 13000.0)
        self.assertIsNone(result["total_return_pct"])
        self.assertIsNone(result["vs_benchmark_pct"])
        for code in ("missing_baseline", "invalid_inception"):
            self.assertIn(code, result["availability"]["issues"])
        self.assertEqual(result["availability"]["status"], "provisional")

    def test_invalid_starting_nav_never_defaults_to_constant(self):
        for bad in (None, 0, 0.0, -1.0, True, "10000", float("nan"), [10000.0]):
            state = dict(BASE_STATE, starting_nav=bad)
            result = project(state=state)
            self.assertIsNone(result["starting_nav"], msg="nav=%r" % (bad,))
            self.assertIsNone(result["total_return_pct"])
            self.assertIn("missing_baseline", result["availability"]["issues"])

    def test_inception_must_be_real_nonfuture_iso_date(self):
        for bad in ("2026-13-01", "20261001", "2026-02-30", "", 20261001, None):
            state = dict(BASE_STATE, inception_date=bad)
            result = project(state=state)
            self.assertIsNone(result["inception_date"], msg=repr(bad))
            self.assertIsNone(result["total_return_pct"])
            self.assertIn("invalid_inception", result["availability"]["issues"])
        future = dict(BASE_STATE, inception_date="2026-10-18")
        result = project(state=future)
        self.assertEqual(result["inception_date"], "2026-10-18")
        self.assertIsNone(result["total_return_pct"])
        self.assertIsNone(result["vs_benchmark_pct"])
        self.assertIn("future_inception", result["availability"]["issues"])


class TestMarkedValuation(unittest.TestCase):
    def test_complete_marks_value_positions_and_never_avg_cost(self):
        state = dict(
            BASE_STATE,
            positions={"EXAMPLE": {"shares": 60.0, "avg_cost": 999999.0}},
        )
        result = project(state=state, prices={"EXAMPLE": 150.0}, bench=[])
        self.assertEqual(result["availability"]["valuation_basis"], "provided_prices")
        self.assertEqual(result["availability"]["status"], "provisional")
        self.assertIsNone(result["availability"]["as_of"])
        self.assertEqual(result["current_nav"], 4000.0 + 60.0 * 150.0)
        self.assertEqual(result["invested"], 60.0 * 150.0)
        self.assertEqual(result["cash"], 4000.0)
        self.assertEqual(result["total_return_pct"], 30.0)
        self.assertIsNone(result["day_change_pct"])

    def test_one_missing_mark_never_falls_back_to_avg_cost_or_history_confusion(self):
        state = dict(
            BASE_STATE,
            positions={
                "EXAMPLE": {"shares": 60.0, "avg_cost": 999999.0},
                "OTHER": {"shares": 10.0, "avg_cost": 999999.0},
            },
        )
        result = project(state=state, prices={"EXAMPLE": 150.0})
        self.assertNotEqual(result["availability"]["valuation_basis"], "provided_prices")
        self.assertEqual(result["availability"]["valuation_basis"], "last_recorded_nav")
        self.assertEqual(result["current_nav"], 10500.0)
        self.assertEqual(result["cash"], 5000.0)
        self.assertIn("unpriced_holdings", result["availability"]["issues"])

    def test_garbage_avg_cost_never_blocks_a_marked_valuation(self):
        state = dict(
            BASE_STATE,
            positions={"EXAMPLE": {"shares": 60.0, "avg_cost": "nonsense"}},
        )
        result = project(state=state, prices={"EXAMPLE": 150.0}, bench=[])
        self.assertEqual(result["availability"]["valuation_basis"], "provided_prices")
        self.assertEqual(result["current_nav"], 4000.0 + 60.0 * 150.0)

    def test_unpriced_holdings_without_history_keep_cash_and_null_aggregates(self):
        result = project(rows=[], bench=[], prices={"EXAMPLE": 0.0})
        self.assertEqual(result["availability"]["status"], "unavailable")
        self.assertEqual(result["availability"]["valuation_basis"], "unavailable")
        self.assertIsNone(result["current_nav"])
        self.assertIsNone(result["invested"])
        self.assertEqual(result["cash"], 4000.0)
        self.assertIsNone(result["total_return_pct"])
        self.assertIn("unpriced_holdings", result["availability"]["issues"])

    def test_nonpositive_or_nonfinite_prices_are_not_marks(self):
        for bad in (0.0, -150.0, float("nan"), float("inf"), "150", True, None):
            result = project(rows=[], bench=[], prices={"EXAMPLE": bad})
            self.assertEqual(
                result["availability"]["valuation_basis"],
                "unavailable",
                msg="price=%r" % (bad,),
            )
            self.assertIn("unpriced_holdings", result["availability"]["issues"])

    def test_non_mapping_prices_object_is_ignored_safely(self):
        result = project(rows=[], bench=[], prices="EXAMPLE=150")
        self.assertEqual(result["availability"]["valuation_basis"], "unavailable")
        self.assertIn("unpriced_holdings", result["availability"]["issues"])

    def test_missing_cash_blocks_marked_nav_and_reports_missing_cash(self):
        state = {k: v for k, v in BASE_STATE.items() if k != "cash"}
        result = project(state=state, prices={"EXAMPLE": 150.0}, rows=[], bench=[])
        self.assertEqual(result["availability"]["valuation_basis"], "unavailable")
        self.assertIsNone(result["cash"])
        self.assertIn("missing_cash", result["availability"]["issues"])


class TestSnapshotFallback(unittest.TestCase):
    def test_snapshot_cash_comes_from_the_row_not_today(self):
        state = dict(BASE_STATE, cash=7000.0)
        result = project(state=state, prices={})
        self.assertEqual(result["cash"], 5000.0)
        self.assertEqual(result["current_nav"], 10500.0)
        self.assertEqual(result["invested"], 5500.0)
        self.assertEqual(result["availability"]["as_of"], "2026-10-16")
        self.assertEqual(result["availability"]["status"], "provisional")

    def test_row_without_cash_leaves_cash_and_invested_null(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 10100.0},
        ]
        result = project(rows=rows, prices={})
        self.assertIsNone(result["cash"])
        self.assertEqual(result["current_nav"], 10100.0)
        self.assertIsNone(result["invested"])

    def test_inconsistent_stated_invested_is_excluded(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 10100.0, "cash": 5000.0, "invested": 6000.0},
        ]
        result = project(rows=rows, prices={})
        # October 2 components sum to 11000, so that conflicting snapshot is excluded.
        self.assertEqual(result["availability"]["as_of"], "2026-10-01")
        self.assertEqual(result["availability"]["history_status"], "partial")
        self.assertEqual(result["current_nav"], 10000.0)
        self.assertEqual(result["invested"], 6000.0)

    def test_zero_nav_row_is_a_real_observation_not_missing(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 0.0, "cash": 0.0},
        ]
        result = project(rows=rows, prices={})
        self.assertEqual(result["current_nav"], 0.0)
        self.assertEqual(result["cash"], 0.0)
        self.assertEqual(result["invested"], 0.0)
        self.assertEqual(result["max_drawdown_pct"], -100.0)


class TestHistoryQualification(unittest.TestCase):
    def test_single_point_history_gives_null_not_zero(self):
        rows = [{"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0}]
        result = project(rows=rows, prices={})
        self.assertIsNone(result["day_change_pct"])
        self.assertIsNone(result["max_drawdown_pct"])
        self.assertEqual(result["current_nav"], 10000.0)
        self.assertEqual(result["realized_since"], "2026-10-01")

    def test_sparse_history_uses_chronological_pair(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-16", "nav": 10500.0, "cash": 5000.0},
        ]
        result = project(rows=rows, prices={})
        self.assertAlmostEqual(result["day_change_pct"], 5.0)
        self.assertEqual(result["max_drawdown_pct"], 0.0)

    def test_corrupt_rows_are_excluded_and_history_is_partial(self):
        rows = BASE_ROWS + [
            "not-a-row",
            {"date": "nope", "nav": 1.0},
            {"date": "2026-10-20", "nav": 1.0},
            {"date": "2026-10-04", "nav": float("nan")},
            {"date": "2026-10-05", "nav": True},
            {"date": "2026-10-06", "nav": 1.0, "cash": "4000"},
            {"date": "2026-10-07", "nav": 1.0, "invested": "x"},
            {"date": "2026-10-08", "nav": "1.0"},
        ]
        result = project(rows=rows, prices={})
        self.assertEqual(result["availability"]["history_status"], "partial")
        self.assertIn("history_partial", result["availability"]["issues"])
        self.assertIsNone(result["day_change_pct"])
        self.assertIsNone(result["max_drawdown_pct"])
        # The valid rows still project the same snapshot.
        self.assertEqual(result["current_nav"], 10500.0)
        self.assertEqual(result["realized_since"], "2026-10-01")

    def test_conflicting_duplicates_exclude_the_date(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 10100.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 10200.0, "cash": 4000.0},
            {"date": "2026-10-03", "nav": 9900.0, "cash": 4000.0},
        ]
        result = project(rows=rows, prices={})
        self.assertEqual(result["availability"]["history_status"], "partial")
        self.assertIn("history_partial", result["availability"]["issues"])
        self.assertIsNone(result["day_change_pct"])
        realized_dates = [
            point["date"] for point in result["series"] if point["kind"] == "realized"
        ]
        self.assertNotIn("2026-10-02", realized_dates)

    def test_exact_duplicates_collapse_and_history_stays_complete(self):
        row = {"date": "2026-10-02", "nav": 10100.0, "cash": 4000.0}
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            row,
            dict(row),
        ]
        result = project(rows=rows, prices={})
        self.assertEqual(result["availability"]["history_status"], "available")
        self.assertNotIn("history_partial", result["availability"]["issues"])
        self.assertAlmostEqual(result["day_change_pct"], 1.0)

    def test_conflicting_only_in_optional_cash_is_conflict(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 10100.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 10100.0},
        ]
        result = project(rows=rows, prices={})
        self.assertEqual(result["availability"]["history_status"], "partial")
        self.assertIsNone(result["day_change_pct"])

    def test_future_row_is_excluded_not_projected(self):
        rows = BASE_ROWS + [{"date": "2026-10-18", "nav": 99999.0, "cash": 1.0}]
        result = project(rows=rows, prices={})
        self.assertEqual(result["availability"]["history_status"], "partial")
        self.assertEqual(result["current_nav"], 10500.0)
        self.assertNotIn("2026-10-18", series_by_date(result))

    def test_non_sequence_history_container_is_partial(self):
        for bad in ({"2026-10-01": 1.0}, "rows", 5, None):
            result = project(rows=bad, prices={})
            self.assertEqual(result["availability"]["history_status"], "partial")
            self.assertIn("history_partial", result["availability"]["issues"])
            self.assertIsNone(result["realized_since"])

    def test_parent_history_unavailable_is_never_requalified(self):
        result = project(history_status="unavailable", prices={})
        self.assertEqual(result["availability"]["history_status"], "unavailable")
        self.assertIn("history_unavailable", result["availability"]["issues"])
        self.assertIsNone(result["realized_since"])
        self.assertIsNone(result["day_change_pct"])
        self.assertIsNone(result["max_drawdown_pct"])
        self.assertNotIn("realized", {p["kind"] for p in result["series"]})

    def test_parent_history_partial_keeps_rows_but_blocks_statistics(self):
        result = project(history_status="partial", prices={})
        self.assertEqual(result["availability"]["history_status"], "partial")
        self.assertIn("history_partial", result["availability"]["issues"])
        self.assertEqual(result["realized_since"], "2026-10-01")
        self.assertIsNone(result["day_change_pct"])
        self.assertIsNone(result["max_drawdown_pct"])
        self.assertEqual(result["current_nav"], 10500.0)

    def test_unknown_history_status_fails_safe(self):
        result = project(history_status="PARSE_FAILED", prices={})
        self.assertEqual(result["availability"]["history_status"], "unavailable")
        self.assertIn("history_unavailable", result["availability"]["issues"])


class TestDrawdownAndDayChange(unittest.TestCase):
    def test_zero_nav_after_peak_is_full_drawdown(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 12000.0, "cash": 4000.0},
            {"date": "2026-10-03", "nav": 0.0, "cash": 0.0},
        ]
        result = project(rows=rows, bench=[], prices={})
        self.assertEqual(result["max_drawdown_pct"], -100.0)

    def test_unchanged_history_drawdown_is_zero(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-03", "nav": 10000.0, "cash": 4000.0},
        ]
        result = project(rows=rows, bench=[], prices={})
        self.assertEqual(result["max_drawdown_pct"], 0.0)
        self.assertEqual(result["day_change_pct"], 0.0)

    def test_drawdown_measures_from_running_peak(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 12000.0, "cash": 4000.0},
            {"date": "2026-10-03", "nav": 9000.0, "cash": 4000.0},
        ]
        result = project(rows=rows, bench=[], prices={})
        self.assertAlmostEqual(result["max_drawdown_pct"], -25.0)
        self.assertAlmostEqual(result["day_change_pct"], -25.0)

    def test_partial_history_blocks_drawdown_even_with_points(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-02", "nav": 12000.0, "cash": 4000.0},
            {"date": "2026-10-03", "nav": 9000.0, "cash": 4000.0},
        ]
        result = project(rows=rows, bench=[], prices={}, history_status="partial")
        self.assertIsNone(result["max_drawdown_pct"])
        self.assertIsNone(result["day_change_pct"])

    def test_day_change_needs_a_dated_snapshot_not_a_quote(self):
        marked = project(prices={"EXAMPLE": 150.0}, bench=[])
        self.assertIsNone(marked["day_change_pct"])
        cash_only = project(
            state=dict(BASE_STATE, cash=4000.0, positions={}), rows=[], bench=[]
        )
        self.assertIsNone(cash_only["day_change_pct"])


class TestBenchmarkPairing(unittest.TestCase):
    def test_paired_dates_produce_relative_return(self):
        result = project()
        self.assertEqual(result["total_return_pct"], 5.0)
        self.assertAlmostEqual(result["vs_benchmark_pct"], 0.0, places=9)
        self.assertAlmostEqual(result["vs_spy_pct"], 0.0, places=9)
        self.assertNotIn(
            "return_comparison_unavailable", result["availability"]["issues"]
        )

    def test_missing_benchmark_start_date_blocks_comparison(self):
        bench = [entry for entry in BASE_BENCH if entry[0] != INCEPTION]
        result = project(bench=bench)
        self.assertIsNone(result["vs_benchmark_pct"])
        self.assertIsNone(result["vs_spy_pct"])
        self.assertIn(
            "return_comparison_unavailable", result["availability"]["issues"]
        )
        self.assertEqual(result["total_return_pct"], 5.0)
        self.assertEqual(result["benchmark_as_of"], "2026-10-17")

    def test_benchmark_ending_before_snapshot_blocks_comparison(self):
        bench = [entry for entry in BASE_BENCH if entry[0] < "2026-10-16"]
        result = project(bench=bench)
        self.assertIsNone(result["vs_benchmark_pct"])
        self.assertIn(
            "return_comparison_unavailable", result["availability"]["issues"]
        )
        self.assertEqual(result["benchmark_as_of"], "2026-10-03")

    def test_end_equal_to_start_is_never_a_comparison(self):
        rows = [{"date": INCEPTION, "nav": 10500.0, "cash": 5000.0}]
        bench = [(INCEPTION, 105.0)]
        result = project(rows=rows, bench=bench)
        self.assertIsNone(result["vs_benchmark_pct"])
        self.assertIn(
            "return_comparison_unavailable", result["availability"]["issues"]
        )

    def test_undated_valuation_is_never_paired_with_benchmark(self):
        result = project(prices={"EXAMPLE": 150.0}, rows=[])
        self.assertIsNone(result["vs_benchmark_pct"])
        self.assertIn(
            "return_comparison_unavailable", result["availability"]["issues"]
        )
        self.assertIsNotNone(result["current_nav"])

    def test_regional_symbol_is_preserved_not_relabelled(self):
        for symbol in ("000300.SS", "^HSI"):
            result = project(benchmark=symbol)
            self.assertEqual(result["benchmark"], symbol)
            self.assertEqual(result["vs_spy_pct"], result["vs_benchmark_pct"])
            self.assertAlmostEqual(result["vs_benchmark_pct"], 0.0, places=9)

    def test_future_and_malformed_closes_are_filtered(self):
        bench = BASE_BENCH + [
            ("2026-10-18", 200.0),
            ("bad-date", 100.0),
            ("2026-10-02", 0.0),
            ("2026-10-03", -5.0),
            ("2026-10-04", True),
            ("2026-10-05", "100.0"),
            ("2026-10-06",),
            ("2026-10-07", 100.0, "extra"),
        ]
        result = project(bench=bench)
        self.assertEqual(result["availability"]["status"], "provisional")
        self.assertIn("benchmark_partial", result["availability"]["issues"])
        self.assertEqual(result["benchmark_as_of"], "2026-10-17")
        # The retained closes still pair inception 2026-10-01 with snapshot 2026-10-16.
        self.assertAlmostEqual(result["vs_benchmark_pct"], 0.0, places=9)

    def test_conflicting_closes_exclude_the_date_without_winners(self):
        bench = [
            ("2026-10-01", 100.0),
            ("2026-10-02", 101.0),
            ("2026-10-02", 102.0),
            ("2026-10-03", 100.5),
            ("2026-10-16", 105.0),
            ("2026-10-17", 106.0),
        ]
        result = project(bench=bench)
        self.assertIn("benchmark_partial", result["availability"]["issues"])
        # Pairing needs only inception and snapshot dates, so it still lands.
        self.assertAlmostEqual(result["vs_benchmark_pct"], 0.0, places=9)
        conflicted = [p for p in result["series"] if p["date"] == "2026-10-02"]
        self.assertEqual(len(conflicted), 1)
        self.assertIsNone(conflicted[0]["spy_nav"])

    def test_exact_duplicate_closes_collapse(self):
        bench = BASE_BENCH + [("2026-10-17", 106.0)]
        result = project(bench=bench)
        self.assertNotIn("benchmark_partial", result["availability"]["issues"])
        self.assertAlmostEqual(result["vs_benchmark_pct"], 0.0, places=9)

    def test_unreadable_benchmark_container_is_unavailable(self):
        for bad in ("SPY,100", 5, {"2026-10-01": 100.0}, None):
            result = project(bench=bad)
            self.assertIn("benchmark_unavailable", result["availability"]["issues"])
            self.assertIsNone(result["benchmark_as_of"])

    def test_empty_benchmark_history_is_unavailable(self):
        result = project(bench=[])
        self.assertIn("benchmark_unavailable", result["availability"]["issues"])
        self.assertIsNone(result["benchmark_as_of"])
        self.assertIsNone(result["vs_benchmark_pct"])
        # Observed portfolio NAV is not erased by an unavailable benchmark.
        self.assertEqual(result["current_nav"], 10500.0)
        self.assertIn("realized", {p["kind"] for p in result["series"]})

    def test_benchmark_as_of_ignores_only_invalid_entries(self):
        bench = [("2026-10-01", 100.0), ("2026-10-02", "bad"), ("2026-10-16", 105.0)]
        result = project(bench=bench)
        self.assertEqual(result["benchmark_as_of"], "2026-10-16")


class TestSeries(unittest.TestCase):
    def test_missing_post_inception_chart_points_are_null_not_flat(self):
        rows = [
            {"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0},
            {"date": "2026-10-05", "nav": 10500.0, "cash": 5000.0},
        ]
        bench = [
            ("2026-10-01", 100.0),
            ("2026-10-02", 101.0),
            ("2026-10-03", 102.0),
            ("2026-10-04", 103.0),
            ("2026-10-05", 104.0),
        ]
        result = project(rows=rows, bench=bench, prices={})
        by_date = series_by_date(result)
        self.assertEqual(
            [point["date"] for point in result["series"]],
            ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"],
        )
        self.assertEqual(by_date["2026-10-01"]["nav"], 10000.0)
        self.assertEqual(by_date["2026-10-01"]["kind"], "realized")
        for missing in ("2026-10-02", "2026-10-03", "2026-10-04"):
            self.assertIsNone(by_date[missing]["nav"])
            self.assertEqual(by_date[missing]["kind"], "unavailable")
        self.assertEqual(by_date["2026-10-05"]["nav"], 10500.0)
        self.assertEqual(by_date["2026-10-05"]["kind"], "realized")

    def test_pre_inception_reference_uses_starting_nav_only_once_flagged(self):
        bench = [
            ("2026-09-28", 98.0),
            ("2026-09-29", 99.0),
            ("2026-10-01", 100.0),
        ]
        rows = [{"date": "2026-10-01", "nav": 10000.0, "cash": 4000.0}]
        result = project(rows=rows, bench=bench, prices={})
        by_date = series_by_date(result)
        self.assertEqual(by_date["2026-09-28"]["kind"], "pre_inception")
        self.assertEqual(by_date["2026-09-28"]["nav"], 10000.0)
        self.assertEqual(by_date["2026-09-29"]["kind"], "pre_inception")
        self.assertEqual(by_date["2026-10-01"]["kind"], "realized")

    def test_benchmark_reference_normalises_to_starting_nav(self):
        result = project()
        by_date = series_by_date(result)
        self.assertAlmostEqual(by_date["2026-10-01"]["spy_nav"], 10000.0, places=9)
        self.assertAlmostEqual(by_date["2026-10-03"]["spy_nav"], 10050.0, places=9)
        self.assertAlmostEqual(by_date["2026-10-17"]["spy_nav"], 10600.0, places=9)

    def test_spy_nav_is_null_without_baseline(self):
        state = {"cash": 4000.0, "positions": {}}
        rows = [{"date": "2026-10-02", "nav": 4000.0, "cash": 4000.0}]
        result = project(state=state, rows=rows, prices={})
        for point in result["series"]:
            self.assertIsNone(point["spy_nav"])

    def test_series_cap_keeps_most_recent_91_dates(self):
        today = datetime.date(2026, 10, 17)
        bench = [
            ((today - datetime.timedelta(days=offset)).isoformat(), 100.0 + offset)
            for offset in range(99, -1, -1)
        ]
        old_row = [
            {
                "date": (today - datetime.timedelta(days=100)).isoformat(),
                "nav": 1.0,
                "cash": 0.0,
            }
        ]
        result = project(state=BASE_STATE, rows=old_row, bench=bench, prices={})
        self.assertEqual(len(result["series"]), 91)
        dates = [point["date"] for point in result["series"]]
        self.assertNotIn((today - datetime.timedelta(days=100)).isoformat(), dates)
        self.assertEqual(dates[-1], "2026-10-17")
        self.assertEqual(dates[0], (today - datetime.timedelta(days=90)).isoformat())

    def test_series_is_empty_without_any_dated_observations(self):
        result = project(rows=[], bench=[], prices={"EXAMPLE": 150.0})
        self.assertEqual(result["series"], [])


class TestPendingTransaction(unittest.TestCase):
    def test_pending_wal_suppresses_current_headline_only(self):
        result = project(transaction_pending=True)
        availability = result["availability"]
        self.assertEqual(availability["status"], "unavailable")
        self.assertEqual(availability["valuation_basis"], "unavailable")
        self.assertIsNone(availability["as_of"])
        self.assertIn("transaction_pending", availability["issues"])
        self.assertIsNone(result["current_nav"])
        self.assertIsNone(result["cash"])
        self.assertIsNone(result["invested"])
        self.assertIsNone(result["total_return_pct"])
        self.assertIsNone(result["vs_benchmark_pct"])
        self.assertIsNone(result["vs_spy_pct"])
        self.assertIsNone(result["day_change_pct"])
        # Historical rows remain visibly qualified.
        self.assertEqual(availability["history_status"], "available")
        self.assertIn("realized", {p["kind"] for p in result["series"]})
        self.assertEqual(result["realized_since"], "2026-10-01")
        self.assertIsNotNone(result["max_drawdown_pct"])
        self.assertEqual(result["benchmark_as_of"], "2026-10-17")

    def test_pending_with_unavailable_account_stays_unavailable(self):
        result = project(transaction_pending=True, account_status="unavailable")
        self.assertEqual(result["availability"]["status"], "unavailable")
        for code in ("transaction_pending", "account_unavailable"):
            self.assertIn(code, result["availability"]["issues"])


class TestPurity(unittest.TestCase):
    def test_inputs_are_never_mutated(self):
        state = copy.deepcopy(BASE_STATE)
        rows = copy.deepcopy(BASE_ROWS)
        bench = copy.deepcopy(BASE_BENCH)
        prices = {"EXAMPLE": 150.0}
        state_before = copy.deepcopy(state)
        rows_before = copy.deepcopy(rows)
        bench_before = copy.deepcopy(bench)
        prices_before = copy.deepcopy(prices)
        project(
            state=state,
            rows=rows,
            bench=bench,
            prices=prices,
            transaction_pending=True,
            history_status="partial",
            account_status="unavailable",
        )
        self.assertEqual(state, state_before)
        self.assertEqual(rows, rows_before)
        self.assertEqual(bench, bench_before)
        self.assertEqual(prices, prices_before)

    def test_output_does_not_alias_inputs_and_is_finite_json(self):
        state = copy.deepcopy(BASE_STATE)
        rows = copy.deepcopy(BASE_ROWS)
        bench = copy.deepcopy(BASE_BENCH)
        prices = {"EXAMPLE": 150.0}
        result = project(
            state=state, rows=rows, bench=bench, prices=prices, today=TODAY
        )
        self.assertIsNot(result["series"], rows)
        self.assertIsNot(result["availability"]["issues"], RESULT_KEYS)
        encoded = json.dumps(result, allow_nan=False, sort_keys=True)
        self.assertIsInstance(encoded, str)
        # Touching the output must not touch the inputs either.
        result["series"].append({"date": "9999-01-01", "nav": None, "spy_nav": None, "kind": "unavailable"})
        result["availability"]["issues"].append("probe")
        self.assertEqual(rows, copy.deepcopy(BASE_ROWS))
        self.assertNotIn("probe", project()["availability"]["issues"])

    def test_all_numeric_output_is_json_finite(self):
        results = [
            project(),
            project(prices={"EXAMPLE": 150.0}, bench=[]),
            project(rows=[], bench=[]),
            project(state=None),
            project(transaction_pending=True),
            project(bench=[]),
            project(state=dict(BASE_STATE, cash=-500.0, positions={}), rows=[], bench=[]),
        ]
        for result in results:
            json.dumps(result, allow_nan=False)

            def walk(node):
                if isinstance(node, dict):
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for value in node:
                        walk(value)
                elif isinstance(node, float):
                    self.assertTrue(math.isfinite(node))

            walk(result)

    def test_projection_is_deterministic_across_calls(self):
        first = project()
        second = project()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["series"], second["series"])

    def test_invalid_observed_today_fails_safe(self):
        for bad in ("", "2026-10-18T00:00:00", "not-a-date", "2026-02-30", 20261017, None):
            result = project(today=bad, prices={"EXAMPLE": 150.0})
            self.assertEqual(result["availability"]["status"], "unavailable")
            self.assertEqual(result["availability"]["issues"], ["invalid_today"])
            self.assertEqual(result["availability"]["valuation_basis"], "unavailable")
            self.assertIsNone(result["current_nav"])
            self.assertIsNone(result["cash"])
            self.assertIsNone(result["invested"])
            self.assertIsNone(result["benchmark_as_of"])
            self.assertIsNone(result["total_return_pct"])
            self.assertEqual(result["series"], [])
            json.dumps(result, allow_nan=False)

    def test_future_today_relative_to_inception_still_projects(self):
        result = project(today="2025-01-01")
        self.assertIn("future_inception", result["availability"]["issues"])
        self.assertIsNone(result["total_return_pct"])
        self.assertEqual(result["benchmark_as_of"], None)

    def test_benchmark_name_must_be_a_usable_string(self):
        result = project(benchmark="")
        self.assertIsNone(result["benchmark"])
        result = project(benchmark=7)
        self.assertIsNone(result["benchmark"])

    def test_equity_alias_keys_agree(self):
        result = project()
        self.assertEqual(result["vs_benchmark_pct"], result["vs_spy_pct"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestParentCounterexamples(unittest.TestCase):
    def test_absent_account_fields_are_not_an_empty_or_settled_account(self):
        for key in ("positions", "cash"):
            for missing in (True, False):
                value = copy.deepcopy(BASE_STATE)
                if missing:
                    value.pop(key)
                else:
                    value[key] = None
                result = project(state=value)
                self.assertEqual(result["availability"]["account_status"], "invalid")
                self.assertIsNone(result["current_nav"])
                self.assertIsNone(result["day_change_pct"])

    def test_unavailable_account_cannot_publish_a_headline_change(self):
        result = project(account_status="unavailable")
        self.assertIsNone(result["day_change_pct"])
        self.assertTrue(result["series"])

    def test_unknown_account_status_is_not_echoed_as_a_new_status(self):
        result = project(account_status="arbitrary_status")
        self.assertEqual(result["availability"]["account_status"], "unavailable")

    def test_huge_integer_observations_fail_safely_without_losing_json_contract(self):
        huge = 10 ** 400
        cases = [
            {"state": dict(BASE_STATE, starting_nav=huge)},
            {"state": dict(BASE_STATE, cash=huge)},
            {"prices": {"EXAMPLE": huge}},
            {"rows": BASE_ROWS + [{"date": TODAY, "nav": huge}]},
            {"bench": BASE_BENCH + [("2026-10-15", huge)]},
        ]
        for kwargs in cases:
            result = project(**kwargs)
            json.dumps(result, allow_nan=False)

    def test_overflowing_return_does_not_crash_benchmark_comparison(self):
        result = project(state=dict(BASE_STATE, starting_nav=5e-324))
        self.assertIsNone(result["total_return_pct"])
        self.assertIsNone(result["vs_benchmark_pct"])
        json.dumps(result, allow_nan=False)

    def test_inconsistent_snapshot_components_do_not_win_latest_selection(self):
        result = project(rows=BASE_ROWS + [
            {"date": TODAY, "nav": 11000, "cash": 4000, "invested": 1},
        ])
        self.assertEqual(result["current_nav"], 10500)
        self.assertEqual(result["availability"]["history_status"], "partial")
        self.assertIsNone(result["day_change_pct"])
        self.assertIsNone(result["max_drawdown_pct"])

    def test_zero_observations_without_positive_peak_do_not_report_zero_drawdown(self):
        result = project(rows=[
            {"date": INCEPTION, "nav": 0, "cash": 0, "invested": 0},
            {"date": "2026-10-16", "nav": 0, "cash": 0, "invested": 0},
        ])
        self.assertEqual(result["current_nav"], 0)
        self.assertIsNone(result["max_drawdown_pct"])

    def test_calendar_identity_requires_ascii_iso_digits(self):
        result = project(today="２０２６-10-17")
        self.assertIsNone(result["current_nav"])
        self.assertIn("invalid_today", result["availability"]["issues"])
