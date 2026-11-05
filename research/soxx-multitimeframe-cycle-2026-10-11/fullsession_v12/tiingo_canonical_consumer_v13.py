#!/usr/bin/env python3
"""Receipt-pinned, credential-free CLI for the EXISTING Macro Data OS reader.

Only reads immutable archived BOATS L0/L1 through read_research_view.
Outputs aggregate source, clock and coverage metadata. NEVER emits market rows,
calls Tiingo, begins a new collector, suggests a fill, or admits PIT backtesting.
Run with PYTHONPATH containing the incumbent Macro source and v13 research module.
"""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
from fullsession import trade_date
from tiingo_l1_v13 import l1_to_bars,audit_overnight_nights,resample_complete_30m

SHA=re.compile(r"^[0-9a-f]{64}$")

def parser():
    p=argparse.ArgumentParser(description="Read existing immutable Tiingo BOATS history receipts (no provider access)")
    p.add_argument("--archive-root",type=Path,required=True)
    p.add_argument("--source-day",required=True)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--symbol",required=True)
    p.add_argument("--observed-before-utc",required=True)
    p.add_argument("--night-start-et",required=True,action="append")
    p.add_argument("--max-rows",type=int,default=2000)
    return p

def run(args):
    if not SHA.fullmatch(args.source_sha):
        raise ValueError("exact lowercase historical source digest required")
    if not isinstance(args.symbol,str) or args.symbol!=args.symbol.upper() or not args.symbol:
        raise ValueError("explicit uppercase historical vendor symbol required")
    if not 1<=args.max_rows<=100_000:
        raise ValueError("bounded existing source read required")
    if len(args.night_start_et)>14:
        raise ValueError("nightly coverage audit cap: 14 exact ET dates")
    # The canonical research source verifies: existing L0 receipt, original SHA,
    # L1 materialization identity and original raw-to-L1 economic equivalence.
    # Its imported module is already the Macro Data OS owner, NOT a new writer.
    from lib.dataos.tiingo_reader import read_research_view
    view=read_research_view(
        "boats-bars",args.source_day,args.source_sha,
        root=args.archive_root,purpose="INSPECTION",max_rows=args.max_rows,
        check_mount=True,
    )
    if view.source!="boats-bars" or not view.rows:
        raise ValueError("exact source receipt has no qualified historical bars")
    receipt=view.rows[0]["source_receipt_id"]
    bars,meta=l1_to_bars(
        list(view.rows),symbol=args.symbol,expected_sha=args.source_sha,
        receipt_id=receipt,observed_before_utc=args.observed_before_utc,
        minutes=1,basis="raw",
    )
    nights=audit_overnight_nights(bars,night_starts_et=args.night_start_et)
    bars30,resampling=resample_complete_30m(bars)
    bynight={}
    for b in bars30:
        # 20:00 day-before and 00:00–04:00 today are one next-day trade_date.
        key=trade_date(b.utc).isoformat()
        bynight[key]=bynight.get(key,0)+1
    return {
        "status":"EXISTING_ARCHIVE_READ_ONLY_CONSUMED",
        "source":"macro-tiingo-dataos-read_research_view",
        "symbol":args.symbol,
        "capture_day_utc":args.source_day,
        "source_sha256":args.source_sha,
        "source_receipt_id":receipt,
        "source_rows":len(view.rows),
        "strict_complete_30m_bars":resampling["complete_30m"],
        "withheld_partial_30m_buckets":resampling["skipped_partial_30m"],
        "by_trading_date_completed_30m":bynight,
        "nightly_coverage":nights,
        "market_data_rows_emitted":0,
        "research_retrospective_only":True,
        "venue_scope":"single_ats",
        "full_24h_eligible":False,
        "point_in_time_eligible":False,
        "redistribution_authorized":False,
        "actual_quote_fills_proven":False,
        "no_duplicate_collector_or_archive":True,
    }

def main(argv=None):
    try:
        result=run(parser().parse_args(argv))
    except (ValueError,TypeError,OSError,KeyError) as exc:
        print("CANONICAL_DATAOS_READ_REFUSED:",str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())