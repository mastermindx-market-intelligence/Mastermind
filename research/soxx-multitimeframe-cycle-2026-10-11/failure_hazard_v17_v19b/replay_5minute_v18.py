#!/usr/bin/env python3
"""Five-minute execution and *diagnostic-only* adverse/favorable excursions.

Keeps prior parent-turn entries, higher-timeframe features, risk and timed policy
unchanged. One minute data has not been seen. No model fitting or signal selection.
All five-minute OHLC source candles are privately retained at Terminal research owner.
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import bisect,collections,csv,hashlib,json,statistics
import study_v14 as s
import peer_v14 as peer
import parent_delay_controls_v16 as turns
from engine_v6 import simulate

ROOT=Path(__file__).resolve().parent
ET=ZoneInfo("America/New_York")
UTC=timezone.utc
LANDMARKS=(.5,1.,2.,3.,6.)

def raw5(sym):
    doc=json.loads((ROOT/(sym+"_Terminal_5m_ext0.json")).read_text())
    assert doc["t"]==sym and doc["tf"]=="5m"
    output=[];daycounts=collections.Counter()
    for stamp,o,h,l,c,v in doc["bars"]:
        display=datetime.fromtimestamp(stamp,UTC)
        et=display.replace(tzinfo=ET)
        start=int(et.timestamp());end=int((et+timedelta(minutes=5)).timestamp())
        assert 0<l<=min(o,c)<=max(o,c)<=h and v>=0
        day=et.date().isoformat();daycounts[day]+=1
        output.append(dict(idx=len(output),start=start,end=end,day=day,local=et.isoformat(),
            open=o,high=h,low=l,close=c,volume=v,complete=True))
    assert all(z["end"]==v["start"] for z,v in zip(output,output[1:]) if z["day"]==v["day"])
    assert all(num in (42,78) for day,num in daycounts.items() if s.DATE_BEGIN<=day<=s.DATE_END)
    assert daycounts.get("2025-10-09")==78 and daycounts.get("2026-10-08")==78
    return output,daycounts

def make_fine(ctx,raw):
    # Same already observed high/low indicators with as-of mapping to new 5m raw ends.
    out=dict(ctx,raw=raw,rawstarts=[x["start"] for x in raw],
        rawends=[x["end"] for x in raw],clock=s.n.market_clock(raw))
    out["_panels"]=s.make_panels(out)
    out["_cycle_cache"]={}
    return out

def remap_fine(ctx_old,ctx5,c):
    lookup=ctx5["_fine_start"]
    at=ctx_old["raw"][c["entry"]]["start"]
    en=lookup.get(at)
    if en is None:return None
    assert ctx5["raw"][en]["open"]==ctx_old["raw"][c["entry"]]["open"]
    signal=s.n.asof(ctx5["rawends"],c["signal_time"])
    assert signal>=0
    assert ctx5["raw"][signal]["end"]==c["signal_time"]
    assert ctx5["raw"][en]["start"]>=ctx5["raw"][signal]["end"]
    z=dict(c,entry=en,entry_ET=ctx5["raw"][en]["local"],signal_idx=signal,
        stop=ctx5["raw"][en]["open"]*.985,original_15m_entry_idx=c["entry"])
    return z

def earlier_than(c,ctx5,x):
    # True whenever position is alive strictly after x market-hours of observed 5m.
    end=ctx5["clock"][c["entry"]]+int(x*3600)
    return bisect.bisect_left(ctx5["clock"],end)

def landmarks(ctx5,c,t):
    idx=c["entry"];raw=ctx5["raw"];duration_index=t["exit_idx"]
    price=raw[idx]["open"]
    out=[]
    for hour in LANDMARKS:
        target=earlier_than(c,ctx5,hour)
        if target>=len(raw):
            out.append(dict(stage_h=hour,status="right_censored"));continue
        end=target-1
        if duration_index<end or duration_index==end and t["reason"] in ("stop","stop_gap","target","partial"):
            out.append(dict(stage_h=hour,status="already_closed",
                 exit_reason=t["reason"],exit_age_hour=t["hold_hours"]))
            continue
        # At exactly target close, decision is now known and next open is only
        # available later. Do not count the future bar in the feature panel.
        chunks=raw[idx:target]
        if not chunks:
            out.append(dict(stage_h=hour,status="not_yet_elapsed"));continue
        high=max(x["high"] for x in chunks);low=min(x["low"] for x in chunks)
        close=chunks[-1]["close"];peak=100*(high/price-1)
        underwater=100*(low/price-1)
        out.append(dict(stage_h=hour,status="alive",
            close_from_entry_pct=round(100*(close/price-1),4),
            adverse_excursion_pct=round(underwater,4),
            favorable_excursion_pct=round(peak,4),
            falling_from_high_pct=round(100*(close/high-1),4),
            original_support_lost=close<c["anchor"],
            net_trade_eventually_positive=t["net_pct"]>0,
            final_model_net_pct=round(t["net_pct"],4)))
    return out

def run():
    spec=json.loads((ROOT/"FIVE_MINUTE_REPLAY_SPEC_V18.json").read_text())
    assert spec["precommitted_before_5m_fetch"]
    original_15m={};replayed=[];landmark_rows=[];summary=[];check=[]
    for sym in spec["frozen_cohort"]:
        ctxold,_=s.raw_context() if sym=="SOXX" else peer.peer_context(sym)
        raw,days=raw5(sym)
        c5=make_fine(ctxold,raw)
        c5["_fine_start"]={x["start"]:x["idx"] for x in raw}
        assert len(c5["_fine_start"])==len(raw)
        entries=turns.parents(ctxold)
        mismatches=[];unknown=[];compare=[]
        for old in entries:
            c=remap_fine(ctxold,c5,old)
            if c is None:
                unknown.append(old["entry_ET"])
                continue
            for mode in ("time52","structural_cycle"):
                oldt,_=s.run_exit(ctxold,old,mode,15)
                assert oldt
                newer,_=s.run_exit(c5,c,mode,15)
                assert newer
                if c5["raw"][newer["exit_idx"]]["day"]<s.DATE_BEGIN:
                    raise ValueError("unexpected early-window reference")
                effect=newer["net_pct"]-oldt["net_pct"]
                if abs(effect)>1e-7:mismatches.append(dict(entry=old["entry_ET"],mode=mode,
                      delta=round(effect,5),old_reason=oldt["reason"],new_reason=newer["reason"]))
                compare.append(dict(symbol=sym,entry_ET=old["entry_ET"],episode=old["episode"],
                    exit_mode=mode,status="resolved",old15_net_pct=round(oldt["net_pct"],5),
                    new5_net_pct=round(newer["net_pct"],5),delta=round(effect,5),
                    old15_reason=oldt["reason"],new5_reason=newer["reason"],
                    old15_hold_h=oldt["hold_hours"],new5_hold_h=newer["hold_hours"],
                    new5_stop_count=newer["ambiguous"],
                    gap_fill=newer["reason"]=="stop_gap"))
                if mode=="time52":
                    landmark_rows.extend(dict(symbol=sym,entry=old["entry_ET"],episode=old["episode"],
                        **land) for land in landmarks(c5,c,newer))
        replayed.extend(compare)
        summary.append(dict(symbol=sym,original_parent_entry_signals=len(entries),
            matched5m_entries=len(entries)-len(unknown),
            missing_fine_entries=len(unknown),
            old_new_source_disagreements=len(mismatches),
            max_abs_return_delta=round(max([abs(x["delta"]) for x in mismatches] or [0]),6),
            stop_first_new_5m_ambiguous_candles=sum(x["new5_stop_count"] for x in compare),
            changes_15m_to_5m=mismatches[:8],
            new_5m_source_days=len(days)))
        print("FIVE_MINUTE_PARENT_REPLAY",sym,summary[-1],flush=True)
    s.save_csv("five_minute_execution_comparison_v18.csv",replayed)
    s.save_csv("five_minute_landmark_episodes_v18.csv",landmark_rows)
    s.save_csv("five_minute_replay_summary_v18.csv",summary)
    grouped=collections.defaultdict(list)
    for r in landmark_rows:
        grouped[r["stage_h"],r["status"]].append(r)
    stage=[]
    for hours in LANDMARKS:
        alive=grouped[hours,"alive"];closed=grouped[hours,"already_closed"]
        winners=[z for z in alive if z["net_trade_eventually_positive"]]
        losers=[z for z in alive if not z["net_trade_eventually_positive"]]
        def med(xs):return round(statistics.median(xs),5) if xs else None
        stage.append(dict(stage_h=hours,
          positions_with_signal=sum(x["original_parent_entry_signals"] for x in summary),
          alive_with_valid_history=len(alive),closed_before_feature=len(closed),
          alive_future_winners=len(winners),alive_future_nonwinners=len(losers),
          winners_below_entry_at_time=sum(z["close_from_entry_pct"]<0 for z in winners),
          losers_above_entry_at_time=sum(z["close_from_entry_pct"]>0 for z in losers),
          winner_median_5m_close_gain_pct=med([x["close_from_entry_pct"] for x in winners]),
          loser_median_5m_close_gain_pct=med([x["close_from_entry_pct"] for x in losers]),
          winner_median_5m_adverse_pct=med([x["adverse_excursion_pct"] for x in winners]),
          loser_median_5m_adverse_pct=med([x["adverse_excursion_pct"] for x in losers]),
          original_support_lost_winners=sum(x["original_support_lost"] for x in winners),
          original_support_lost_losers=sum(x["original_support_lost"] for x in losers)))
    s.save_csv("five_minute_landmark_summary_v18.csv",stage)
    report=dict(schema=spec["schema"],per_symbol=summary,
       landmark_summary=stage,
       test_source="Terminal stored-5m and live-tail price OHLC matches aggregate 15m for full-year overlap; volume differs <0.005pct during selected live-tail days.",
       source_rights_private=True,retrospective_only=True,
       no_actual_quotes=True,BOATS_full_session=False,
       note="5m OHLC intrabar order is unknown, 15m OHLC conditions may differ from finer 5m path. No predictive risk classifier fitted.")
    (ROOT/"FIVE_MINUTE_REPLAY_RESULTS_V18.json").write_text(json.dumps(report,indent=2))
    print("LANDMARK_SUMMARIES",json.dumps(stage),flush=True)
    print("RESULT_SHA",hashlib.sha256((ROOT/"FIVE_MINUTE_REPLAY_RESULTS_V18.json").read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()