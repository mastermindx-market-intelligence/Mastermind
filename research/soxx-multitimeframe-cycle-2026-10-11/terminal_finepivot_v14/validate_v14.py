"""Independent chronology/exit/summary validation of the frozen Terminal fine pivots.
Reads private OHLC on research host only. Outputs safe aggregate receipts, no raw prices.
"""
from pathlib import Path
import bisect,collections,csv,datetime as dt,hashlib,json,math,statistics
import study_v14 as s
import peer_v14 as peers
import structure_admission_v14 as admission
from intrabar_audit import replay
ROOT=Path(__file__).resolve().parent

def load(name):return list(csv.DictReader((ROOT/name).open()))
def check_source():
    c,quality=s.raw_context()
    assert quality["all_30m_consistent"] and quality["gaps_on_observed_dates"]==0
    spec=json.loads((ROOT/"SPECIFICATION.json").read_text())
    assert spec["source_15m_sha256"]==hashlib.sha256((ROOT/"SOXX_Terminal_15m_ext0.json").read_bytes()).hexdigest()
    for sym in ("SMH","QQQ","AMD"):
        x,q=peers.peer_context(sym)
        assert q["source_rth_year_missing_days"]==0
        if sym=="QQQ":assert q["source_warmup_first_day_head_gaps"]==["2025-07-14"]
        else:assert q["observed_calendar_gaps"]==0
    return c,dict(source_15m=quality["source_15m"],source_30m=quality["source_30m"],
        QQQ_warmup_head_missing_minutes=30,year_intraday_source_gaps=0)

def ctx_prefix(full,cut):
    raw=[dict(x) for x in full["raw"] if x["day"]<=cut]
    assert len(raw)>0 and raw[-1]["day"]==cut
    ends={day:end for day,end in full["closes"].items() if day<=cut}
    high={m:s.n.aggregate_minutes(raw,m,ends) for m in [120,180,240]}
    hf={name:s.n.enrich(high[minutes],params,p) for name,(minutes,params,p) in s.n.PROFILES.items()}
    lower={m:s.n.aggregate_minutes(raw,m,ends) for m in [15,30,60]}
    lf={(m,k):s.n.enrich(lower[m],*s.n.LOWERS[k]) for m in lower for k in ["fast"]}
    return dict(raw=raw,closes=ends,rejected={},high=high,hf=hf,lower=lower,lf=lf,
      rawstarts=[x["start"] for x in raw],rawends=[x["end"] for x in raw],
      clock=s.n.market_clock(raw),recent=False,first=raw[0]["day"])

def prefix():
    ctx=s.raw_context()[0]
    check=0
    for name,profile,minutes,lp in [("3h_15fast","3h_medium",15,"fast"),
                                    ("3h_60fast","3h_medium",60,"fast")]:
        full=s.candidates(ctx,name,profile,minutes,lp)
        for cut in ("2025-12-31","2026-03-31","2026-06-30","2026-09-30"):
            sub=ctx_prefix(ctx,cut)
            xs=s.candidates(sub,name,profile,minutes,lp)
            observed=[(x["episode"],x["entry_ET"]) for x in xs]
            expected=[(x["episode"],x["entry_ET"]) for x in full if x["entry_ET"][:10]<=cut]
            assert observed==expected,(name,cut,observed,expected)
            check+=len(expected)+1
    return check

def replay_checks(ctx):
    # Exercise independent 15min OHLC execution engine for same entries,
    # including opposite OHLC price-path order when stop and target coexist.
    tested=0;maxdiff=0.;ambiguity=0;highfirst_changes=0;status={}
    for label,minutes in (("3h_60fast",60),("3h_30fast",30),("3h_15fast",15)):
        cs=s.candidates(ctx,label,"3h_medium",minutes,"fast")
        ctx.setdefault("_cycle_cache",{})[minutes]=s.make_cycle_panels(ctx,lower_minutes=minutes)
        ctx["_cycle"]=ctx["_cycle_cache"][minutes]
        for c in cs:
            for mode in ("time52","finite_guard","structural_cycle"):
                direct,_=s.run_exit(ctx,c,mode,minutes)
                if direct is None:continue
                kind="time" if mode=="time52" else "old_guard" if mode=="finite_guard" else mode
                dp,monitor=s.cy.make_policy(ctx,c,kind,clock=52,buffer=.1)
                p=replay(ctx["raw"],c["entry"],c["stop"],decision=dp,partial=.25,horizon=100000,order="OLHC",fee=5)
                assert p is not None
                diff=abs(p["net_pct"]-direct["net_pct"])
                maxdiff=max(maxdiff,diff)
                assert diff<1e-8,(label,mode,c["entry_ET"],p["net_pct"],direct["net_pct"])
                assert p["exit_idx"]==direct["exit_idx"]
                dp,_=s.cy.make_policy(ctx,c,kind,clock=52,buffer=.1)
                alternate=replay(ctx["raw"],c["entry"],c["stop"],decision=dp,partial=.25,horizon=100000,order="OHLC",fee=5)
                assert alternate is not None
                if abs(alternate["net_pct"]-direct["net_pct"])>1e-8:highfirst_changes+=1
                ambiguity+=direct["ambiguous"]
                tested+=1
    return dict(independent_OHLC_replays=tested,largest_return_difference=maxdiff,
        ambiguous_stop_and_partial_candles=ambiguity,
        high_first_vs_low_first_economic_differences=highfirst_changes)

def aggregate_proof():
    ledger=json.loads((ROOT/"private_derived_trades_v14.json").read_text())
    summaries=load("summary_v14.csv")
    details=load("paired_exits_v14.csv")
    checked=0
    for row in summaries:
        xs=[x["net_pct"] for x in ledger if x["model"]==row["model"] and x["exit_policy"]==row["exit_policy"] and x["status"]=="resolved"]
        assert len(xs)==int(row["resolved"])
        assert sum(x>0 for x in xs)==int(row["wins"])
        if xs:assert abs(statistics.mean(xs)-float(row["mean"]))<5.1e-5
        checked+=1
    for model in ("3h_60fast","3h_30fast","3h_15fast"):
        x=[r for r in summaries if r["model"]==model]
        mean={r["exit_policy"]:float(r["mean"]) for r in x}
        for mode in ("structural_cycle","finite_guard","fast_weak_control"):
            ds=[float(z["lift"]) for z in details if z["model"]==model and z["exit_policy"]==mode]
            if len(ds)==int(next(r["resolved"] for r in x if r["exit_policy"]==mode)):
                assert abs(statistics.mean(ds)-(mean[mode]-mean["time52"]))<.00011
    admissions=load("structured_admission_summary_v14.csv")
    ledger2=load("structured_admission_trades_v14.csv")
    for z in admissions:
        r=[x for x in ledger2 if x["model"]==z["model"] and x["symbol"]==z["symbol"]]
        assert len(r)==int(z["total_opportunities"])
        assert sum(x["status"]=="accepted" for x in r)==int(z["accepted"])
        assert sum(x["status"]!="accepted" for x in r)==int(z["rejected"])
        checked+=1
    peer=load("peer_summary_v14.csv")
    assert all(x["symbol"] in ("SMH","QQQ","AMD") for x in peer)
    return dict(aggregate_stat_rows_recomputed=checked,
      source_year_peer_instruments=sorted(set(x["symbol"] for x in peer)),
      first_year_15m_entry_count=int(next(x["resolved"] for x in summaries if x["model"]=="3h_15fast" and x["exit_policy"]=="time52")))

if __name__=="__main__":
    ctx,src=check_source()
    p=prefix()
    path=replay_checks(ctx)
    aggregates=aggregate_proof()
    proof=dict(validation_schema="soxx.terminal_finepivot_validation.v14",source_quality=src,
          no_future_prefix_cases=p,**path,**aggregates,
          source_data_published=False,
          independent_business_calendar_coverage_proven=False,
          trade_execution_proven=False,
          entire_dataset_was_previously_touched=True)
    out=ROOT/"VALIDATION_V14.json"
    assert not out.exists(),"Existing proof requires reconciliation before rewriting"
    out.write_text(json.dumps(proof,indent=2,sort_keys=True))
    print("PASS",json.dumps(proof),flush=True)
    print("VALIDATION_SHA",hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)