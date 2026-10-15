#!/usr/bin/env python3
"""Frozen evidence for dual-timeframe confluence against 'armed' without retuning.

All event state and score decisions are constructed from completed candles.
SOXX and peer cohorts are already inspected: research exploration, not new
out-of-sample acceptance or actual transactions. Does not access any vendor API.
"""
import collections,csv,datetime as dt,hashlib,json,math,statistics
from pathlib import Path
import study_v14 as s
import peer_v14 as peers
from nested_pivots import candidates as parent_candidates
ROOT=Path(__file__).resolve().parent
DATE_BEGIN,DATE_END=s.DATE_BEGIN,s.DATE_END

def mean(v):
    return round(statistics.mean(v),5) if v else None
def build_turn(ctx,minutes,key):
    data=parent_candidates(ctx,"3h_medium",minutes,key,"turn","pivot_turn",1,expiry=s.n.EXPIRY_SECONDS,level=2)
    raw=ctx["raw"]
    out=[]
    for item in data:
        i=item["entry"]
        if not DATE_BEGIN<=raw[i]["day"]<=DATE_END:continue
        assert item["higher_time"]<=item["signal_time"]<=raw[i]["start"]
        assert item["arm_time"]<=item["higher_time"]
        out.append(dict(item,model=f"3h_{minutes}m_turn",entry_ET=raw[i]["local"],
            phase="year",stop=raw[i]["open"]*.985))
    return sorted(out,key=lambda z:z["entry"])
def policy_returns(ctx,cs,mode,minutes):
    mapping={}
    for item in cs:
        t,_=s.run_exit(ctx,item,mode,minutes)
        mapping[item["episode"]]=dict(return_pct=t["net_pct"] if t else None,
            exit_index=t["exit_idx"] if t else None,
            status="resolved" if t else "right_censored",
            reason=t["reason"] if t else None)
    return mapping

def run():
    spec=json.loads((ROOT/"SIMULTANEOUS_SPEC.json").read_text())
    assert spec["predeclared_before_outcomes"] is True
    output=[];pairs=[];source_checks=[]
    for symbol in spec["universe"]:
        ctx,source_check=s.raw_context() if symbol=="SOXX" else peers.peer_context(symbol)
        source_checks.append(dict(symbol=symbol,observed_15m_bars=len(ctx["raw"]),
                                 study_coverage_verified=True))
        for label,minutes,lower in spec["entries"]:
            base=s.candidates(ctx,label,"3h_medium",minutes,lower)
            turn=build_turn(ctx,minutes,lower)
            baseby={x["episode"]:x for x in base}
            turnby={x["episode"]:x for x in turn}
            assert len(baseby)==len(base)
            assert len(turnby)==len(turn)
            assert set(turnby).issubset(baseby),("confluence must be a subset of armed episodes",symbol,label,set(turnby)-set(baseby))
            bcount=len(baseby); tcount=len(turnby)
            for c in turn:
                old=baseby[c["episode"]]
                assert c["entry"]>=old["entry"],("later confluence must not backdate",symbol,label,c["episode"])
            for mode in spec["exit_policies"]:
                earlier=policy_returns(ctx,base,mode,minutes)
                later=policy_returns(ctx,turn,mode,minutes)
                baseline_values=[v["return_pct"] for v in earlier.values() if v["status"]=="resolved"]
                turned_values=[v["return_pct"] for v in later.values() if v["status"]=="resolved"]
                baseline_unresolved=sum(v["status"]!="resolved" for v in earlier.values())
                late_unresolved=sum(v["status"]!="resolved" for v in later.values())
                blocked_winners=0;blocked_losers=0;paired=[];skipped=0;unknown=0
                for episode,item in earlier.items():
                    c=baseby[episode];y=later.get(episode)
                    if y is None:
                        skipped+=1
                        if item["return_pct"] is not None:
                            blocked_winners+=item["return_pct"]>0
                            blocked_losers+=item["return_pct"]<=0
                        continue
                    new=turnby[episode]
                    if item["return_pct"] is None or y["return_pct"] is None:
                        unknown+=1
                        continue
                    old_price=ctx["raw"][c["entry"]]["open"]
                    new_price=ctx["raw"][new["entry"]]["open"]
                    lag=(ctx["clock"][new["entry"]]-ctx["clock"][c["entry"]])/3600
                    delta=y["return_pct"]-item["return_pct"]
                    row=dict(symbol=symbol,model=label,exit_policy=mode,episode=episode,
                        armed_entry_ET=c["entry_ET"],confluence_entry_ET=new["entry_ET"],
                        additional_confirmation_RTH_h=round(lag,3),
                        additional_confirmation_price_disadvantage_pct=round(100*(new_price/old_price-1),4),
                        armed_return_pct=round(item["return_pct"],4),
                        confluence_return_pct=round(y["return_pct"],4),
                        difference_pctpoints=round(delta,4),
                        harmed_winner=item["return_pct"]>0 and delta<-.000001,
                        saved_loser=item["return_pct"]<0 and delta>.000001)
                    paired.append(row);pairs.append(row)
                all_known=([v["return_pct"] for v in later.values() if v["return_pct"] is not None])
                # Missing trade = no position = cash, but right-censored live positions
                # stay unknown rather than being modeled as cash.
                itt=mean(all_known+[0.]*(bcount-tcount)) if not late_unresolved and not baseline_unresolved else None
                output.append(dict(symbol=symbol,model=label,exit_policy=mode,
                    armed_opportunities=bcount,armed_resolved=len(baseline_values),
                    confluence_signals=tcount,confluence_resolved=len(turned_values),
                    confluence_conditional_win=sum(v>0 for v in turned_values),
                    armed_win=sum(v>0 for v in baseline_values),
                    armed_mean_net_pct=mean(baseline_values),
                    turn_mean_net_pct=mean(turned_values),
                    average_per_original_arm_with_skips_cash_pct=itt,
                    no_confluence_count=skipped,skipped_armed_winners=blocked_winners,
                    skipped_armed_losers=blocked_losers,
                    paired_confluence_n=len(paired),mean_later_entry_delay_RTH_h=mean([r["additional_confirmation_RTH_h"] for r in paired]),
                    mean_later_entry_price_disadvantage_pct=mean([r["additional_confirmation_price_disadvantage_pct"] for r in paired]),
                    paired_mean_return_delta=mean([r["difference_pctpoints"] for r in paired]),
                    paired_winners_harmed=sum(r["harmed_winner"] for r in paired),
                    paired_losers_saved=sum(r["saved_loser"] for r in paired),
                    unresolved_armed=baseline_unresolved,unresolved_confluence=late_unresolved))
            z=[p for p in output if p["symbol"]==symbol and p["model"]==label and p["exit_policy"]=="time52"][0]
            print("ENTRY_QUALIFICATION",symbol,label,
                "armed",z["armed_opportunities"],"both_turning",z["confluence_signals"],
                "lost_prior_winners",z["skipped_armed_winners"],
                "armed_mean",z["armed_mean_net_pct"],
                "turn_mean",z["turn_mean_net_pct"],
                "ITT",z["average_per_original_arm_with_skips_cash_pct"],flush=True)
    def write_csv(name,rows):
        if not rows:return
        fields=list(dict.fromkeys(k for item in rows for k in item))
        with (ROOT/name).open("w",newline="") as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    write_csv("simultaneous_turn_summary_v15.csv",output)
    write_csv("simultaneous_turn_matched_events_v15.csv",pairs)
    allstudy=dict(schema=spec["schema"],source="existing public Terminal 15-minute RTH with unverified PIT/adjustment",
        registered_before_outcome=True,model_count=len(output),
        entry_universe=spec["universe"],source_checks=source_checks,
        model_summary=output,raw_prices_disclosed=False,metric_definition="Original HTF armed episodes are denominator; unmatched later confirmation is cash not winning trade; incomplete result remains unknown.",
        passed_condition="Parent must have CLOSED with negative-but-improving MACD histogram, rising K and K>=D when lower confirmed pivot also closes; next observed open only",
        caveat="Retrospective; user hypothesis explored on already observed market cycle. No known historical marketable quotes.")
    (ROOT/"simultaneous_turn_results_v15.json").write_text(json.dumps(allstudy,indent=2))
    print("SOURCE",len(source_checks),"CHECKS",len(output),"EVENTS",len(pairs),
        "DIGEST",hashlib.sha256((ROOT/"simultaneous_turn_results_v15.json").read_bytes()).hexdigest())
if __name__=="__main__":run()