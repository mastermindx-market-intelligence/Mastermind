#!/usr/bin/env python3
"""Read-only reproduction of Prophet Global Upgrade pass 02.

This is a research probe, not a scorer, grader, model, or production integration.
Reads immutable public repository artifacts. It never imports a live producer,
advances a ledger, trains a model, or writes to a production path.
Dependencies: Python 3.10+, pandas, numpy.
Run: python reproduce.py --fossil-ranks
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PIN = "11485597cc53b3137346084aae4623cceed28a3f"
BASE = f"https://raw.githubusercontent.com/mastermindx-market-intelligence/macro/{PIN}/"
FOSSIL_HASH = "0b58bb38d292ec34737d2886134b1d32177493912171e35889ee4931c0b5fed4"
MAX_ARTIFACT_BYTES = 30_000_000
MAX_FOSSIL_BYTES = 80_000_000


def fetch(path: str) -> bytes:
    request = urllib.request.Request(BASE + path, headers={"User-Agent": "ProphetResearchReadOnly/1"})
    with urllib.request.urlopen(request, timeout=40) as response:
        data = response.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"Artifact exceeds bounded read: {path}")
    return data


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def reproduce(fossil_ranks: bool) -> dict[str, Any]:
    evidence = json.loads(Path(__file__).with_name("evidence.json").read_text())
    require(evidence["macro_pin"] == PIN, "Evidence/source pin mismatch")
    ledgers = {}
    for market in ("us", "cn", "hk", "ca"):
        path = f"site/factordata/{market}_track_ledger.json"
        raw = fetch(path)
        require(hashlib.sha256(raw).hexdigest() == evidence["source_sha256"][path],
                f"Source hash mismatch: {path}")
        ledgers[market] = json.loads(raw)
        require(ledgers[market]["meta"]["truncated"] == 0, f"Truncated ledger: {market}")

    us = pd.DataFrame(ledgers["us"]["rows"])
    v3 = us[(us["bd"] == "us_prophet_v3") & us["m"].eq(True)].copy()
    result: dict[str, Any] = {"source_pin": PIN, "status": "RESEARCH_ONLY_NO_PROMOTION"}
    result["us_v3"] = {
        "matured_episodes": len(v3), "positive_outcomes": int(v3["st"].eq("up").sum()),
        "origin_dates": int(v3["d"].nunique()), "unique_tickers": int(v3["t"].nunique()),
        "win_pct": 100.0 * float(v3["st"].eq("up").mean()),
        "mean_pnl_pct_from_rounded_rows": float(v3["p"].mean()),
        "mean_excess_pct_from_rounded_rows": float(v3["x"].mean()),
    }
    require((len(v3), result["us_v3"]["positive_outcomes"], v3["d"].nunique()) == (209, 73, 8),
            "US v3 diagnostic changed at immutable pin")
    result["us_matured_definitions"] = us[us["m"].eq(True)]["bd"].value_counts().to_dict()
    require(len(result["us_matured_definitions"]) == 5, "US mixture no longer matches")

    suspension_source = fetch("engine/board_ledger.py")
    require(hashlib.sha256(suspension_source).hexdigest() ==
            evidence["source_sha256"]["engine/board_ledger.py"], "Suspension source hash mismatch")
    module = ast.parse(suspension_source.decode())
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "_is_suspended")
    # Execute ONLY the already-inspected pure function, never the producer module.
    namespace: dict[str, Any] = {"pd": pd, "SUSPENSION_SESSIONS": 5}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "pinned_pure_function", "exec"), namespace)
    fill = pd.Timestamp("2026-09-10")
    probes = {
        "fresh_one_day": pd.Series([100, 101], index=pd.to_datetime(["2026-09-10", "2026-09-11"])),
        "month_gap_then_five_prints": pd.Series(
            [100, 90, 91, 92, 93, 94], index=pd.to_datetime([
                "2026-09-10", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"])),
        "five_nan_rows": pd.Series([100, np.nan, np.nan, np.nan, np.nan, np.nan],
                                   index=pd.bdate_range("2026-09-10", periods=6)),
    }
    result["suspension_probes"] = {k: namespace["_is_suspended"](v, fill) for k, v in probes.items()}
    require(result["suspension_probes"] == {"fresh_one_day": True,
            "month_gap_then_five_prints": False, "five_nan_rows": False}, "Pure probe mismatch")
    result["suspension_flag_counts"] = {}
    for market, expected in (("hk", 81), ("ca", 87)):
        rows = ledgers[market]["rows"]
        count = sum("susp" in row.get("fl", []) for row in rows)
        result["suspension_flag_counts"][market] = count
        require(count == expected, f"Flag count mismatch: {market}")

    # This is a bounded calendar calculation, not a new general exchange calendar.
    # TSX official 2026 holiday calendar: Labour Day, September 7.
    sessions = pd.bdate_range("2026-08-19", "2026-09-30").difference(pd.DatetimeIndex(["2026-09-07"]))
    endpoint = str(sessions[22].date())  # signal index 0, next-bar fill index 1, endpoint fill+21
    observed = int(((sessions > sessions[1]) & (sessions <= pd.Timestamp("2026-09-11"))).sum())
    result["canada_clock"] = {"earliest_h21_endpoint": endpoint, "observed_through_sep11": observed}
    require((endpoint, observed) == ("2026-09-21", 15), "Canada horizon clock mismatch")
    require(ledgers["ca"]["summary"]["n_matured"] == 0, "Canada maturity snapshot mismatch")

    if fossil_ranks:
        wanted = set(v3["d"])
        metadata: dict[tuple[str, str], int] = {}
        total, n_lines, digest = 0, 0, hashlib.sha256()
        with urllib.request.urlopen(BASE + "data/us_board_ledger/snapshots.jsonl", timeout=50) as response:
            for raw in response:
                total += len(raw)
                n_lines += 1
                require(total <= MAX_FOSSIL_BYTES and n_lines <= 500, "Fossil read bound exceeded")
                digest.update(raw)
                if not raw.strip():
                    continue
                board = json.loads(raw)
                date = board.get("as_of")
                if date in wanted:
                    # Owner _board_to_record uses zero-based original lane order.
                    # Raw fossils contain buy[], not the owner's normalized rows[].
                    for position, row in enumerate(board.get("buy") or []):
                        metadata[(date, row["ticker"])] = position
        require(digest.hexdigest() == FOSSIL_HASH, "Fossil hash mismatch")
        found = [row for row in v3.to_dict("records") if (row["d"], row["t"]) in metadata]
        different = sum(row["rk"] != metadata[(row["d"], row["t"])] for row in found)
        require((len(found), different) == (209, 149), "Origin metadata reconciliation mismatch")
        result["fossil_rank_reconciliation"] = {
            "matched": len(found), "different_rank": different, "source_bytes": total,
            "source_sha256": digest.hexdigest(), "snapshot_lines": n_lines,
        }
    else:
        result["fossil_rank_reconciliation"] = {"status": "NOT_RUN", "required_flag": "--fossil-ranks"}
    result["verification"] = "PASS"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fossil-ranks", action="store_true", help="Read bounded 57 MB original board fossils")
    args = parser.parse_args()
    try:
        result = reproduce(args.fossil_ranks)
    except (OSError, ValueError, KeyError, StopIteration, urllib.error.URLError) as exc:
        print(json.dumps({"verification": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
