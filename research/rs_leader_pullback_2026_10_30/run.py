"""Local CSV entrypoint for the research-only event study (NOT live trading)."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from engine import Rules, evaluate, leader_panel


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Unvalidated source-only RS-leader pullback event study")
    ap.add_argument("--bars", required=True, type=Path, help="UTC-end RTH bar CSV")
    ap.add_argument("--daily", required=True, type=Path, help="PIT historical daily stock and SPY CSV")
    ap.add_argument("--membership", required=True, type=Path, help="PIT index-membership spans")
    ap.add_argument("--out", required=True, type=Path, help="Local JSON report")
    ap.add_argument("--timeframe", type=int, default=30, help="Bar timeframe in minutes")
    ap.add_argument("--min-universe", type=int, default=100)
    ap.add_argument("--min-adv", type=float, default=20_000_000)
    ap.add_argument("--rs-top", type=float, default=0.20)
    args = ap.parse_args(argv)
    rules = Rules(timeframe_minutes=args.timeframe, min_universe=args.min_universe,
                  min_adv_dollars=args.min_adv, rs_top_fraction=args.rs_top)
    hashes = {name: file_digest(getattr(args, name)) for name in ("bars", "daily", "membership")}
    bars = pd.read_csv(args.bars)
    daily = pd.read_csv(args.daily)
    membership = pd.read_csv(args.membership)
    daily_panel = leader_panel(daily, membership, rules)
    result = evaluate(bars, daily_panel, rules)
    result["input_sha256"] = hashes
    result["data_qualification"] = "NOT_VERIFIED: upstream PIT/calendar/adjustments/feed/venue/spread unreviewed"
    result["empirical_strategy_edge_verdict"] = "NOT_ESTABLISHED"
    result["coverage_calendar"] = {
        "dates": len(daily_panel),
        "dates_meeting_coverage_floor": sum(x["coverage"] >= rules.coverage_floor
                                            for x in daily_panel.values()),
        "dates_with_leaders": sum(bool(x["leaders"]) for x in daily_panel.values()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"report": str(args.out), "metrics": result["metrics"],
                      "edge_verdict": result["empirical_strategy_edge_verdict"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
