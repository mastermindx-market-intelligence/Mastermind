"""Compare supplied scenarios with the unchanged held book, without ranking.

All valuation, costs, eligibility and constraint calculations remain in the
existing global_scenario_context.compare. This consumer joins its results by
scenario identity. It owns no forecast, account, policy, persistence or action.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from portfolio import global_scenario_context as core

_BASELINE_ID = "__held_book_baseline__"


def _usable(row: Any) -> bool:
    if not isinstance(row, Mapping) or row.get("status") != "HYPOTHETICAL":
        return False
    for key in ("gross_return", "one_time_cost", "net_return"):
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            if not math.isfinite(value):
                return False
        except (TypeError, ValueError, OverflowError):
            return False
    return True


def compare_with_hold_baseline(
    book: Mapping[str, Any], alternatives: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]], *, as_of: str,
) -> dict[str, Any]:
    """Append net-versus-held differences; do not recommend a winning scenario.

    A caller naming an alternative 'hold' cannot replace the baseline. It is
    derived from the supplied actual book using the original core, outside the
    caller's alternative list. Existing concentration breaches remain visible.
    Positive deltas mean improvement under that *assumption*, not a forecast.
    """
    result = core.compare(book, alternatives, scenarios, as_of=as_of)
    if "book" not in result:
        return {**result, "hold_baseline": {
            "status": "UNAVAILABLE", "source": "unchanged_supplied_book",
            "scenario_results": [], "constraints_breached": [],
            "reasons": ["qualified_book_unavailable"], "one_time_cost_fraction": None,
        }}
    hold = {"alternative_id": _BASELINE_ID, "positions": dict(book["positions"]),
            "cash_weight": book["cash_weight"],
            "costs_bps": {"fee": 0, "spread_crossing": 0, "impact": 0}}
    baseline = core.compare(book, [hold], scenarios, as_of=as_of)
    baseline_row = next(iter(baseline.get("alternatives", [])), {})
    baseline_rows = {row["scenario_id"]: row
                     for row in baseline_row.get("scenario_results", [])}
    scenario_ids = sorted(row["scenario_id"] for row in scenarios)
    reports = []
    for original in result["alternatives"]:
        candidates = {row["scenario_id"]: row for row in original.get("scenario_results", [])}
        paired = []
        for sid in scenario_ids:
            candidate, incumbent = candidates.get(sid), baseline_rows.get(sid)
            if not _usable(candidate) or not _usable(incumbent):
                paired.append({"scenario_id": sid, "status": "UNAVAILABLE",
                               "reason": "candidate_or_hold_scenario_unavailable"})
                continue
            try:
                delta = candidate["net_return"] - incumbent["net_return"]
                valid = math.isfinite(delta)
            except (ArithmeticError, TypeError, ValueError):
                valid = False
            if not valid:
                paired.append({"scenario_id": sid, "status": "UNAVAILABLE",
                               "reason": "comparison_arithmetic_invalid"})
                continue
            paired.append({
                "scenario_id": sid, "status": "HYPOTHETICAL",
                "candidate_net_return": candidate["net_return"],
                "hold_net_return": incumbent["net_return"], "net_return_delta": delta,
                "candidate_one_time_cost": candidate["one_time_cost"],
            })
        count = sum(row["status"] == "HYPOTHETICAL" for row in paired)
        reports.append({**original, "relative_to_hold": {
            "status": "AVAILABLE" if count == len(scenario_ids) else "PARTIAL" if count else "UNAVAILABLE",
            "paired_scenarios": count, "requested_scenarios": len(scenario_ids), "scenarios": paired,
        }})
    return {**result, "alternatives": reports, "hold_baseline": {
        "status": baseline_row.get("status", "UNAVAILABLE"),
        "source": "unchanged_supplied_book",
        "scenario_results": baseline_row.get("scenario_results", []),
        "constraints_breached": baseline_row.get("constraints_breached", []),
        "reasons": baseline_row.get("reasons", baseline.get("reasons", [])),
        "one_time_cost_fraction": baseline_row.get("one_time_cost_fraction"),
    }}
