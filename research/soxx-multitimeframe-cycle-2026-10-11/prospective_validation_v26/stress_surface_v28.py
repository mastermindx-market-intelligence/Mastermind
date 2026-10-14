"""Pinned, research-only audit of *published V24 summary rows*, never market data.

No collector, order, model, strategy selection, calendar, vendor API, or raw rows.
Six pre-existing checkpoint/delay arms are audited together, not ranked/optimized.
The inspected 2025-26 window can never count as an independent holdout.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path

V24_SHA256 = "4622211616c99d6f3a68d14250cf85b35e981f1ab8f459962d57fff78473549e"
FILE = Path(__file__).resolve().parent.parent / "early_failure_v21_v24" / "EXECUTION_STRESS_V24.csv"
GROUPS = ("all", "inspected", "new_semis", "sector")
CHECKPOINTS = (0.5, 3.)
DELAYS = (1, 2, 4)
COSTS = (0, 10, 25, 50, 100)
DENOMINATORS = {"all": 91, "inspected": 34, "new_semis": 47, "sector": 10}
EXPECTED = {(group, cp, delay, cost) for group in GROUPS
            for cp in CHECKPOINTS for delay in DELAYS for cost in COSTS}
EPS = 0.000003   # V24's CSV values are rounded to SIX decimal places.


def _int(value: str, name: str) -> int:
    try:
        num = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if str(num) != value.strip():
        raise ValueError(f"{name} has noncanonical integer encoding")
    return num


def _number(value: str, name: str) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} is not numeric") from exc
    if not math.isfinite(num):
        raise ValueError(f"{name} is not finite")
    return num


def audit_surface_text(text: str) -> dict:
    """Audit CSV structural and accounting properties; not source authentication.

    Use load_verified_v24() for immutable-source hash enforcement. Even a valid
    CSV does not establish independent profit, actual fills or temporal sampling.
    """
    if not isinstance(text, str):
        raise ValueError("expected UTF-8 CSV string")
    reader = csv.DictReader(io.StringIO(text))
    required = {"group", "checkpoint_h", "delay_5m_bars", "extra_sell_slip_bp",
                "n", "discretionary_sales", "mean_delta_pp",
                "saved_original_losers", "harmed_original_winners",
                "biggest_positive_delta", "biggest_negative_delta"}
    if reader.fieldnames is None or set(reader.fieldnames) != required:
        raise ValueError("V24 frozen aggregate schema mismatch")

    grid = {}
    for index, row in enumerate(reader, start=2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError("malformed V24 CSV cell")
        group = row["group"]
        cp = _number(row["checkpoint_h"], "checkpoint")
        delay = _int(row["delay_5m_bars"], "delay")
        cost = _int(row["extra_sell_slip_bp"], "extra cost")
        key = (group, cp, delay, cost)
        if key not in EXPECTED:
            raise ValueError(f"unregistered checkpoint/cost/group in CSV row {index}")
        if key in grid:
            raise ValueError("duplicate frozen checkpoint/cost/group cell")
        n = _int(row["n"], "parent denominator")
        sales = _int(row["discretionary_sales"], "discretionary sales")
        saved = _int(row["saved_original_losers"], "saved loser count")
        harmed = _int(row["harmed_original_winners"], "harmed winner count")
        if n != DENOMINATORS[group] or not 0 <= sales <= n:
            raise ValueError("mismatched original episode denominator or sale count")
        if not 0 <= saved <= n or not 0 <= harmed <= n:
            raise ValueError("invalid historical diagnostic count")
        grid[key] = {
            "n": n, "sales": sales, "saved": saved, "harmed": harmed,
            "mean": _number(row["mean_delta_pp"], "economic mean"),
            "worst": _number(row["biggest_negative_delta"], "worst delta"),
            "best": _number(row["biggest_positive_delta"], "best delta"),
        }
    if set(grid) != EXPECTED:
        raise ValueError(f"incomplete frozen stress grid: {len(grid)} of {len(EXPECTED)} cells")

    for cp in CHECKPOINTS:
        for delay in DELAYS:
            for cost in COSTS:
                all_row = grid[("all", cp, delay, cost)]
                subset = [grid[(g, cp, delay, cost)] for g in GROUPS[1:]]
                if sum(r["n"] for r in subset) != all_row["n"]:
                    raise ValueError("nonpartitioned original parent population")
                if sum(r["sales"] for r in subset) != all_row["sales"]:
                    raise ValueError("nonpartitioned discretionary sale count")
                for field in ("saved", "harmed"):
                    if sum(r[field] for r in subset) != all_row[field]:
                        raise ValueError("historical diagnostics do not partition by original group")
                if abs(max(r["best"] for r in subset) - all_row["best"]) > EPS:
                    raise ValueError("nonpartitioned best episode diagnostic")
                if abs(min(r["worst"] for r in subset) - all_row["worst"]) > EPS:
                    raise ValueError("nonpartitioned worst episode diagnostic")
                weighted = math.fsum(r["mean"] * r["n"] for r in subset) / all_row["n"]
                if abs(weighted - all_row["mean"]) > EPS:
                    raise ValueError("aggregate mean does not reconcile with original cohorts")

    for group in GROUPS:
        for cp in CHECKPOINTS:
            for delay in DELAYS:
                path = [grid[(group, cp, delay, c)] for c in COSTS]
                if len({r["n"] for r in path}) != 1 or len({r["sales"] for r in path}) != 1:
                    raise ValueError("changing population or decisions across fixed cost stresses")
                baseline = path[0]["mean"]
                terminal = path[-1]["mean"]
                for cost, r in zip(COSTS, path):
                    if r["mean"] > baseline + EPS:
                        raise ValueError("adverse sell cost appeared to improve economic effect")
                    interpolated = baseline + (terminal - baseline) * cost / COSTS[-1]
                    if abs(r["mean"] - interpolated) > EPS:
                        raise ValueError("nonlinear fixed-decision additional cost stress")
                    if r["worst"] > r["best"]:
                        raise ValueError("reversed worst/best diagnostics")
                for before, after in zip(path, path[1:]):
                    if after["mean"] > before["mean"] + EPS:
                        raise ValueError("adverse sell cost improved economic effect")

    summary = {}
    for cp in CHECKPOINTS:
        cp_name = "30m" if cp == .5 else "3h"
        for group in GROUPS:
            sign_counts = {cost: sum(grid[(group, cp, delay, cost)]["mean"] > 0.
                                     for delay in DELAYS) for cost in COSTS}
            summary[f"{group}:{cp_name}"] = {
                "parent_episodes_not_independent_trials": DENOMINATORS[group],
                "positive_delay_arms": sign_counts,
                "frozen_arm_means_pp": {
                    f"d{delay}": {f"bp{cost}": grid[(group, cp, delay, cost)]["mean"]
                                  for cost in COSTS}
                    for delay in DELAYS
                },
            }
    return {
        "evidence_claim": "INSPECTED_DEVELOPMENT_AGGREGATE_ONLY_NO_INDEPENDENT_EDGE",
        "market_rows_reloaded": False,
        "new_backtest": False,
        "trusted_market_fill_source": False,
        "production_or_trading_accepted": False,
        "original_parent_episodes": DENOMINATORS["all"],
        "expected_cells": len(EXPECTED),
        "subgroup_denominators": dict(DENOMINATORS),
        "summary": summary,
        "limitations": "The old 91 episodes overlap across time/names; recorded 30m/3h scenarios are not interchangeable independent trials, and no delay is selected after viewing the old year.",
    }


def load_verified_v24(path: Path = FILE) -> dict:
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != V24_SHA256:
        raise ValueError("frozen published V24 aggregate SHA256 mismatch")
    result = audit_surface_text(raw.decode("utf-8"))
    result["V24_csv_sha256"] = V24_SHA256
    return result


if __name__ == "__main__":
    print(json.dumps(load_verified_v24(), sort_keys=True, indent=2))
