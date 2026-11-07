#!/usr/bin/env python3
"""Predeclared pivot-consistent entry risk on SOXX/SMH/QQQ/AMD.
No model calibration: same 3H arm and lower pivots; denies counted as opportunities.
"""
from pathlib import Path
import csv,json,collections,statistics,hashlib
from dataclasses import dataclass
import study_v14 as s
import peer_v14 as peer
from coherent_cycle import assess_entry

ROOT=Path(__file__).resolve().parent
METRICS=["time52","structural_cycle"]
MAP={"3h_60fast":("3h_medium",60,"fast"),
     "3h_30fast":("3h_medium",30,"fast"),
     "3h_15fast":("3h_medium",15,"fast")}

def mean(values):
 return round(statistics.mean(values),4) if values else None

def evaluate():
 spec=json.loads((ROOT/"STRUCTURE_ADMISSION_SPEC.json").read_text())
 assert spec["predeclared_before_outcomes"] and spec["research_only"]
 entries=[];summaries=[];all_stats=collections.Counter()
 for symbol,models in spec["entry_models"].items():
  ctx,provenance=s.raw_context() if symbol=="SOXX" else peer.peer_context(symbol)
  for label in models:
   profile,minutes,lp=MAP[label]
   cs=s.candidates(ctx,label,profile,minutes,lp)
   for c in cs:
    px=ctx["raw"][c["entry"]]["open"]
    # Condition must be independently observed at the original decision,
    # before any knowledge about subsequent profit or loss.
    x=assess_entry(px,c["anchor"],c["atr"],max_risk_pct=1.5,min_risk_pct=.3,buffer_atr=.1)
    if c.get("anchor_kind")!="confirmed_pivot":
     raise ValueError("requires explicit confirmed price pivot, not five-bar fallback")
    original={}
    for policy in METRICS:
     t,_=s.run_exit(ctx,c,policy,minutes)
     original[policy]=t["net_pct"] if t else None
    entry=dict(symbol=symbol,model=label,origin=c["entry_ET"],episode=c["episode"],
       decision_level="confirmed_price_pivot",source_held_RTH=True,
       status="accepted" if x["accepted"] else x["reason"],
       entry_above_pivot=px>c["anchor"],
       original_risk_pct=1.5,structural_risk_pct=round(x["risk_pct"],5),
       pivot_distance_pct=round(c["pivot_distance_pct"],5),
       arm_shortened=c["arm_shortened"],lower_shortened=c["lower_shortened"])
    for policy in METRICS:
     entry["original_"+policy+"_pct"]=original[policy]
     if x["accepted"]:
      new=dict(c,stop=x["stop"],admission="confirmed_pivot_1p5_risk")
      out,_=s.run_exit(ctx,new,policy,minutes)
      entry["structure_"+policy+"_pct"]=out["net_pct"] if out else None
      entry["structure_"+policy+"_reason"]=out["reason"] if out else "unresolved"
     else:
      entry["structure_"+policy+"_pct"]=0.0
      entry["structure_"+policy+"_reason"]="not_admitted"
    entries.append(entry)
   z=[x for x in entries if x["symbol"]==symbol and x["model"]==label]
   allowed=[r for r in z if r["status"]=="accepted"]
   rejected=[r for r in z if r["status"]!="accepted"]
   for policy in METRICS:
    original=[r["original_"+policy+"_pct"] for r in z if r["original_"+policy+"_pct"] is not None]
    accepted=[r["structure_"+policy+"_pct"] for r in allowed if r["structure_"+policy+"_reason"]!="unresolved"]
    skipped_winners=sum(r["original_"+policy+"_pct"] is not None and r["original_"+policy+"_pct"]>0 for r in rejected)
    skipped_losers=sum(r["original_"+policy+"_pct"] is not None and r["original_"+policy+"_pct"]<=0 for r in rejected)
    resolved=len(accepted)
    summaries.append(dict(symbol=symbol,model=label,policy=policy,
      total_opportunities=len(z),accepted=len(allowed),resolved=resolved,
      rejected=len(rejected),reject_reasons=dict(collections.Counter(r["status"] for r in rejected)),
      skipped_winners=skipped_winners,skipped_losers=skipped_losers,
      original_resolved=len(original),original_mean=mean(original),
      original_win=sum(x>0 for x in original),accepted_mean=mean(accepted),
      accepted_win=sum(x>0 for x in accepted),
      structural_stop_mean_pct=mean([r["structural_risk_pct"] for r in allowed]),
      skipped_nonfill_zero_mean=mean(accepted+[0.]*(len(z)-len(accepted))) if resolved==len(allowed) else None,
      unresolved_accepted=len(allowed)-resolved,
      raw_source_version="Terminal_15m_2026-10-11"))
   print("ADMISSION",symbol,label,"total",len(z),"allowed",len(allowed),
     "rejected_counts",dict(collections.Counter(r["status"] for r in rejected)),
     "mean_struct_risk",mean([r["structural_risk_pct"] for r in allowed]),flush=True)
 s.save_csv("structured_admission_trades_v14.csv",entries)
 s.save_csv("structured_admission_summary_v14.csv",summaries)
 report=dict(schema="soxx.pivot-consistent-fail-closed.v14",
   prepared_before_outcomes=True,
   data_source="public Terminal 15/30-minute OHLC, no BOATS, adjustment not verified",
   model_count=len(summaries),opportunity_count=len(entries),
   accepted_count=sum(e["status"]=="accepted" for e in entries),
   summary=summaries,
   trade_projections_are_hypothetical=True,
   kept_deniers_in_denominator=True,
   licensed_raw_prices_exported=False)
 (ROOT/"structured_admission_results_v14.json").write_text(json.dumps(report,indent=2))
 print("SOURCE_OUTCOME_SUMMARY",[(x["symbol"],x["model"],x["policy"],x["total_opportunities"],x["accepted"],x["skipped_winners"],x["original_mean"],x["accepted_mean"],x["skipped_nonfill_zero_mean"]) for x in summaries if x["policy"]=="time52"])
 print("DIGEST",hashlib.sha256((ROOT/"structured_admission_results_v14.json").read_bytes()).hexdigest())
if __name__=="__main__":evaluate()