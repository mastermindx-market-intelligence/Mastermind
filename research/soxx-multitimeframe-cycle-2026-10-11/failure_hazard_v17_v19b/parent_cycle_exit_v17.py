#!/usr/bin/env python3
"""Unmodified frozen cycle-failure exits on newly qualified parent-turn-only entries.
NO threshold fit, no predictor training, no source write or actual broker order.
"""
from pathlib import Path
import csv,json,collections,datetime as dt,hashlib,statistics,random
import study_v14 as s
import peer_v14 as pe
import parent_delay_controls_v16 as p
ROOT=Path(__file__).resolve().parent
SPEC=json.loads((ROOT/"PARENT_TURN_CYCLE_EXIT_SPEC_V17.json").read_text())
assert SPEC["predeclared_before_evaluation"] and SPEC["research_only"]

def mean(vals):return round(statistics.mean(vals),4) if vals else None
def safe_cum(vals):
    value=1.
    for v in vals:value*=1+v/100
    return round(100*(value-1),4)

def week_key(stamp):
    day=dt.datetime.fromisoformat(stamp).date()
    return (day-dt.timedelta(days=day.weekday())).isoformat()

def quantile(v,numerator=50):
    if not v:return None
    z=sorted(v);i=int((len(z)-1)*numerator/100);return round(z[i],4)

def run():
    modes=SPEC["exit_modes"];freqs=SPEC["lower_observation_minutes"]
    rows=[];summary=[];pairs=[];cohort=[]
    for symbol in SPEC["already_inspected_asset_cohort"]:
        ctx,source_quality=s.raw_context() if symbol=="SOXX" else pe.peer_context(symbol)
        originals=p.all_arms(ctx)
        entries=p.parents(ctx)
        assert len(originals)==len(entries)
        dups={z["episode"] for z in entries};assert len(dups)==len(entries)
        cohort.append(dict(symbol=symbol,extreme_arms=len(originals),
          parent_turn_entries=len(entries),source_15m_bars=len(ctx["raw"]),
          source_adjustment_or_PIT_accepted=False))
        refs={}
        for minutes in freqs:
            for mode in modes:
                settled=[]
                for c in entries:
                    t,_=s.run_exit(ctx,c,mode,minutes)
                    if t is None:
                        r=dict(symbol=symbol,model="parent_turn",lower_detector_min=minutes,exit_mode=mode,
                          episode=c["episode"],entry_ET=c["entry_ET"],status="unknown",net_pct=None)
                    else:
                        r=dict(symbol=symbol,model="parent_turn",lower_detector_min=minutes,exit_mode=mode,
                          episode=c["episode"],entry_ET=c["entry_ET"],status="resolved",
                          net_pct=t["net_pct"],exit_reason=t["reason"],
                          initial_risk_pct=t["initial_risk_pct"],
                          exit_idx=t["exit_idx"],initial_price_rth_confirmed=True,
                          hold_hours=t["hold_hours"],ambiguous_candles=t["ambiguous"],
                          reached2=t["reached2"],
                          worst_bar_close_mark=round(min(x[1] for x in t["marks"]),4) if t["marks"] else None)
                    settled.append(r);rows.append(r)
                refs[minutes,mode]={v["episode"]:v for v in settled}
                known=[t for t in settled if t["status"]=="resolved"]
                arr=[t["net_pct"] for t in known]
                stop=[t for t in known if t["exit_reason"].startswith("stop")]
                summary.append(dict(symbol=symbol,entry="first_completed_3h_turn",exit_mode=mode,
                  lower_detector_min=minutes,parent_episode_opportunities=len(originals),
                  resolved=len(known),unknown=len(settled)-len(known),
                  winners=sum(x>0 for x in arr),wins_pct=round(100*sum(x>0 for x in arr)/len(arr),2) if arr else None,
                  average_net=mean(arr),median_net=quantile(arr),
                  sum_net=round(sum(arr),4),all_discrete_compound_return=safe_cum(arr) if arr else None,
                  mean_excluding_biggest_winner=mean(sorted(arr)[:-1]) if len(arr)>1 else None,
                  worst_net=min(arr) if arr else None,
                  mean_initial_risk_pct=mean([x["initial_risk_pct"] for x in known]),
                  stop_exits=len(stop),stop_within_1_rth_hour=sum(x["hold_hours"]<=1.01 for x in stop),
                  stop_within_3_rth_hours=sum(x["hold_hours"]<=3.01 for x in stop),
                  median_stop_hold_rth_h=quantile([x["hold_hours"] for x in stop]),
                  gap_stop_exits=sum(x["exit_reason"]=="stop_gap" for x in stop),
                  reached_partial_milestone=sum(x["reached2"] for x in known),
                  ambiguous_path_bars=sum(x["ambiguous_candles"] for x in known)))
        # Pair identical entries and note what was sacrificed along with what was saved.
        for minutes in freqs:
            base=refs[minutes,"time52"]
            for mode in modes[1:]:
                for episode,z in refs[minutes,mode].items():
                    ref=base[episode]
                    if z["status"]!="resolved" or ref["status"]!="resolved":continue
                    lift=z["net_pct"]-ref["net_pct"]
                    pairs.append(dict(symbol=symbol,episode=episode,week=week_key(z["entry_ET"]),
                      lower_detector_min=minutes,mode=mode,
                      base=round(ref["net_pct"],4),altered=round(z["net_pct"],4),
                      delta=round(lift,4),
                      loser_saved=ref["net_pct"]<0 and lift>1e-8,
                      winner_harmed=ref["net_pct"]>0 and lift< -1e-8,
                      win_created=ref["net_pct"]<=0 and z["net_pct"]>0,
                      win_destroyed=ref["net_pct"]>0 and z["net_pct"]<=0,
                      delta_positive=lift>1e-8,delta_negative=lift< -1e-8,
                      result_reason=z["exit_reason"],baseline_reason=ref["exit_reason"]))
        print("SOURCE",symbol,"n",len(entries),flush=True)
        for z in summary[-len(modes)*len(freqs):]:
            if z["lower_detector_min"]==15:
                print("  EXIT",z["exit_mode"],"n",z["resolved"],"mean",z["average_net"],
                   "wins",z["winners"],"stopped",z["stop_exits"],flush=True)
    rng=random.Random(1776)
    boot=[]
    for minute in freqs:
        for mode in modes[1:]:
            z=[v for v in pairs if v["lower_detector_min"]==minute and v["mode"]==mode]
            groups=collections.defaultdict(list)
            for t in z:groups[t["week"]].append(t["delta"])
            blocks=list(groups.values());means=[]
            for j in range(5000):
                if not blocks:break
                v=[rng.choice(blocks) for x in blocks]
                means.append(sum(map(sum,v))/sum(map(len,v)))
            means.sort()
            boot.append(dict(mode=mode,minutes=minute,n=len(z),weeks=len(blocks),
              mean_lift=mean([t["delta"] for t in z]),
              winners_harmed=sum(t["winner_harmed"] for t in z),
              losers_saved=sum(t["loser_saved"] for t in z),
              new_winners=sum(t["win_created"] for t in z),
              lost_winners=sum(t["win_destroyed"] for t in z),
              positive=round(sum(max(0,t["delta"]) for t in z),3),
              negative=round(-sum(min(0,t["delta"]) for t in z),3),
              block95=[round(means[int(.025*len(means))],4),round(means[int(.975*len(means))],4)] if means else None))
    for file,values in [("parent_cycle_exit_summary_v17.csv",summary),
      ("parent_cycle_exit_pair_v17.csv",pairs),("parent_cycle_exit_cluster_v17.csv",boot)]:
      s.save_csv(file,values)
    # Private derivations excluded from GitHub.
    (ROOT/"parent_cycle_exit_private_v17.json").write_text(json.dumps(rows,indent=2))
    result=dict(schema=SPEC["schema"],predeclared_before_outcomes=True,
       source_cohort=cohort,policy_summaries=summary,week_bootstrap=boot,
       known_at_trade_source_price_basis=False,
       authentic_BOATS_marketbook=False,unseen_holdout=False,
       early_failure_goal="Loss avoided minus winning continuation prematurely sacrificed, not best win rate")
    (ROOT/"parent_cycle_exit_results_v17.json").write_text(json.dumps(result,indent=2))
    print("WEEK_BOOT",json.dumps(boot),flush=True)
    print("RESULT_SHA",hashlib.sha256((ROOT/"parent_cycle_exit_results_v17.json").read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()