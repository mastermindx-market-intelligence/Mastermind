#!/usr/bin/env python3
"""Terminal SOXX 15/30-minute nested-pivot falsification.
Frozen models documented in SPECIFICATION.json before reading outcomes.
NO vendor access, secrets, raw data publication, trading or model selection.
"""
from __future__ import annotations
import bisect,collections,csv,datetime as dt,hashlib,json,math,statistics,sys
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path(__file__).resolve().parent
UP=Path("/private/tmp/soxx_coherent_cycle_20261010_v10")
sys.path.insert(0,str(UP))
import nested_pivots as n
import research_v2 as b
import frozen_audit as fa
import study_cycle as cy
from cycle_failure import make_cycle_panels
from engine_v6 import simulate
from policies_v6 import make_panels
UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")
DATE_BEGIN="2025-10-09"
DATE_END="2026-10-08"

def read_data(name):
    path=BASE/name
    source=json.loads(path.read_bytes())
    assert source["t"]=="SOXX" and source["tf"] in ("15m","30m")
    evidence=source["source_evidence"]
    assert evidence["timestamp_basis"]=="market_local_display_epoch"
    assert evidence["session"]=="regular" and evidence["authority"]=="descriptive_only"
    assert evidence["price_adjustment"]=="not_verified"
    assert evidence["point_in_time_availability"]=="not_verified"
    return source

def raw_context():
    source=read_data("SOXX_Terminal_15m_ext0.json")
    old30=read_data("SOXX_Terminal_30m_ext0.json")
    spec=json.loads((BASE/"SPECIFICATION.json").read_text())
    assert hashlib.sha256((BASE/"SOXX_Terminal_15m_ext0.json").read_bytes()).hexdigest()==spec["source_15m_sha256"]
    assert hashlib.sha256((BASE/"SOXX_Terminal_30m_ext0.json").read_bytes()).hexdigest()==spec["source_30m_sha256"]
    assert spec["prepared_before_outcome"] is True and spec["do_not_optimize"] is True
    raw=[];closes={};day_source=collections.defaultdict(list)
    for epoch,o,h,l,c,v in source["bars"]:
        naive=dt.datetime.fromtimestamp(epoch,UTC)
        assert (naive.hour*60+naive.minute)>=570 and naive.hour*60+naive.minute<960
        assert naive.second==0 and naive.minute%15==0 if naive.hour!=9 else naive.minute==30 or naive.minute==45
        aware=naive.replace(tzinfo=ET)
        start=int(aware.timestamp())
        end=int((aware+dt.timedelta(minutes=15)).timestamp())
        assert 0<l<=min(o,c)<=max(o,c)<=h and v>=0
        day=aware.date().isoformat()
        row=dict(idx=len(raw),start=start,end=end,day=day,local=aware.isoformat(),
                 open=o,high=h,low=l,close=c,volume=v,complete=True)
        raw.append(row);day_source[day].append(row)
    assert len(raw)==8596
    assert all(y["start"]>x["start"] for x,y in zip(raw,raw[1:]))
    for day,rows in day_source.items():
        assert len(rows) in (14,26)
        assert rows[0]["local"][11:16]=="09:30"
        assert all(x["end"]==y["start"] for x,y in zip(rows,rows[1:]))
        z=dt.datetime.fromtimestamp(rows[-1]["end"],ET)
        assert (z.hour,z.minute)==((13,0) if len(rows)==14 else (16,0))
        closes[day]=rows[-1]["end"]
    # Invariant: every directly served 30m source bar matches two 15m underlying candles.
    pairs={raw[i]["start"]:raw[i:i+2] for i in range(0,len(raw),2)}
    assert len(old30["bars"])==len(pairs)==4298
    for display,o,h,l,c,v in old30["bars"]:
        aware=dt.datetime.fromtimestamp(display,UTC).replace(tzinfo=ET)
        a=int(aware.timestamp())
        xs=pairs[a]
        assert len(xs)==2 and xs[0]["end"]==xs[1]["start"]
        got=(xs[0]["open"],max(x["high"] for x in xs),min(x["low"] for x in xs),xs[-1]["close"],sum(x["volume"] for x in xs))
        assert all(math.isclose(x,y,rel_tol=1e-7,abs_tol=1e-3) for x,y in zip(got,(o,h,l,c,v)))
    hb={m:n.aggregate_minutes(raw,m,closes) for m in [120,180,240]}
    hf={name:n.enrich(hb[h],m,p) for name,(h,m,p) in n.PROFILES.items()}
    # Pre-specified equal-duration MACD and Stoch lookback stress:
    # conventional RSI(14) remains 14 bars; do not claim perfect time equivalence.
    n.LOWERS=dict(n.LOWERS,scaled30=((10,26,8),14),scaled15=((20,52,16),28))
    lower={m:n.aggregate_minutes(raw,m,closes) for m in [15,30,60]}
    lf={(m,key):n.enrich(lower[m],params[0],params[1])
        for m in lower for key,params in n.LOWERS.items()
        if not (m==15 and key=="scaled30" or m==30 and key=="scaled15" or m==60 and key.startswith("scaled"))}
    ctx=dict(raw=raw,closes=closes,rejected={},high=hb,hf=hf,lower=lower,lf=lf,
        clock=n.market_clock(raw),rawends=[x["end"] for x in raw],rawstarts=[x["start"] for x in raw],
        recent=False,first=raw[0]["day"])
    ctx["_panels"]=make_panels(ctx)
    gap=fa.source_audit(ctx)
    # This tests only source-observed dates; Terminal itself does NOT prove market calendar completeness.
    assert gap["missing_intervals"]==0
    return ctx,dict(source_15m=len(raw),source_30m=len(old30["bars"]),
             halfdays=[d for d,rs in day_source.items() if len(rs)==14],
             all_30m_consistent=True,day_count=len(day_source),source_evidence=source["source_evidence"],
             gaps_on_observed_dates=gap["missing_intervals"])

def candidates(ctx,label,profile,minutes,lp):
    cs=n.candidates(ctx,profile,minutes,lp,"armed","pivot_turn",1,
                    expiry=n.EXPIRY_SECONDS,level=2)
    results=[]
    for c in cs:
        raw=ctx["raw"];start=raw[c["entry"]]["start"]
        if not DATE_BEGIN<=raw[c["entry"]]["day"]<=DATE_END:continue
        assert start>=c["signal_time"]>=c["higher_time"]>=c["arm_time"]
        c=dict(c,model=label,entry_ET=raw[c["entry"]]["local"],phase="year",
            stop=raw[c["entry"]]["open"]*.985,
            original_stop=raw[c["entry"]]["open"]*.985)
        c["admission_observed"]=raw[c["entry"]]["open"]>c["anchor"]
        c["pivot_distance_pct"]=100*(raw[c["entry"]]["open"]-c["anchor"])/raw[c["entry"]]["open"]
        results.append(c)
    assert len({c["episode"] for c in results})==len(results),"Episode duplicated within model"
    return sorted(results,key=lambda x:(x["entry"],x["episode"]))

def run_exit(ctx,c,exit_kind,minutes,frac=.25):
    cache=ctx.setdefault("_cycle_cache",{})
    if minutes not in cache:cache[minutes]=make_cycle_panels(ctx,lower_minutes=minutes)
    ctx["_cycle"]=cache[minutes]
    if exit_kind=="time52":mode="time"
    elif exit_kind=="finite_guard":mode="old_guard"
    else:mode=exit_kind
    p,mon=cy.make_policy(ctx,c,mode,clock=52,buffer=.1)
    t=simulate(ctx["raw"],c["entry"],c["stop"],horizon=100000,
        partials=[(2,frac)],decision=p,cost_bps=5,
        ambiguity="stop_first")
    return t,mon

def stats(rows):
    z=[r for r in rows if r.get("status")=="resolved"]
    vals=[r["net_pct"] for r in z]
    out=dict(n=len(rows),resolved=len(vals),wins=sum(v>0 for v in vals),
        losses=sum(v<=0 for v in vals),
        win_pct=round(100*sum(v>0 for v in vals)/len(vals),2) if vals else None,
        mean=round(statistics.mean(vals),4) if vals else None,
        median=round(statistics.median(vals),4) if vals else None,
        largest_win=round(max(vals),4) if vals else None,
        worst=round(min(vals),4) if vals else None,
        time_exit=sum(r.get("reason")=="scheduled_next_open" for r in z),
        gap_stop=sum(r.get("reason")=="stop_gap" for r in z),
        unknown=len(rows)-len(vals))
    return out

def evaluate_model(ctx,label,cs,minutes):
    policies=("time52","finite_guard","fast_weak_control","structural_cycle","momentum_reset")
    results={};trades=[];summary=[];paired=[]
    for policy in policies:
        alltrades=[]
        for c in cs:
            t,_=run_exit(ctx,c,policy,minutes)
            if t is None:
                row=dict(model=label,exit_policy=policy,entry_ET=c["entry_ET"],episode=c["episode"],
                    status="right_censored",entry_index=c["entry"],exit_index=None,net_pct=None)
            else:
                row=dict(model=label,exit_policy=policy,entry_ET=c["entry_ET"],episode=c["episode"],
                    status="resolved",entry_index=c["entry"],exit_index=t["exit_idx"],
                    net_pct=t["net_pct"],reason=t["reason"],entry_valid=c["admission_observed"],
                    pivot_distance_pct=c["pivot_distance_pct"],hold_hours=t["hold_hours"],ambiguous=t["ambiguous"],
                    exit_index_ref=t["exit_idx"],initial_risk_pct=t["initial_risk_pct"],
                    trigger_time=c["signal_time"],model_minutes=minutes)
            # Higher entry setup must be known at close before next observable opening.
            assert c["signal_time"]<=ctx["raw"][c["entry"]]["start"]
            alltrades.append(row);trades.append(row)
        results[policy]=alltrades
        summary.append(dict(model=label,exit_policy=policy,**stats(alltrades),
            candidates=len(cs),original_pivot_lost_at_entry=sum(not c["admission_observed"] for c in cs),
            truncated_parent_arms=sum(c["arm_shortened"] for c in cs)))
    reference={r["episode"]:r for r in results["time52"]}
    for policy in policies[1:]:
        for r in results[policy]:
            ref=reference[r["episode"]]
            if r["status"]!="resolved" or ref["status"]!="resolved":continue
            lift=r["net_pct"]-ref["net_pct"]
            paired.append(dict(model=label,exit_policy=policy,episode=r["episode"],entry_ET=r["entry_ET"],
               baseline=ref["net_pct"],test=r["net_pct"],lift=lift,
               saved_loser=(ref["net_pct"]<0 and lift>1e-6),
               harmed_winner=(ref["net_pct"]>0 and lift< -1e-6),
               net_trade_improved=lift>1e-6,net_trade_harmed=lift< -1e-6))
    # Actual single-position portfolio logic can suppress overlapping opportunities.
    portfolio=[]
    for policy in policies:
        last=-1;realized=[];skipped=0
        for c in cs:
            if c["entry"]<=last:skipped+=1;continue
            r=next(z for z in results[policy] if z["episode"]==c["episode"])
            if r["status"]=="resolved":
                last=r["exit_index"];realized.append(r)
            else:last=len(ctx["raw"])-1;realized.append(r)
        portfolio.append(dict(model=label,exit_policy=policy,
            emitted_signals=len(cs),skipped_overlap=skipped,**stats(realized)))
    return summary,portfolio,paired,trades

def source_price_pair(ctx):
    prior=fa.context_from_source(UP/"inputs/rth_original.json")
    prior_set,_=fa.v7.prepared(prior,"3H_1H_pivot")
    newraw=ctx["raw"];look={r["start"]:r for r in newraw}
    rows=[]
    for c in prior_set:
        if c["phase"]!="year":continue
        a=prior["raw"][c["entry"]]
        b=look.get(a["start"])
        rows.append(dict(old_entry_ET=a["local"],available=b is not None,
           relative_open_price_pct=100*(b["open"]/a["open"]-1) if b else None,
           prior_anchor_valid=a["open"]>c["anchor"],prior_ledger_stop_pct=100*(1-c["stop"]/a["open"])))
    return rows

def episode_compare(ctx,by_model):
    reference={x["episode"]:x for x in by_model["3h_60fast"]}
    results=[];summary=[]
    for candidate in ("3h_30fast","3h_15fast","3h_30duration","3h_15duration"):
        paired=[]
        for c in by_model[candidate]:
            old=reference.get(c["episode"])
            if old is None:continue
            elapsed=(ctx["clock"][old["entry"]]-ctx["clock"][c["entry"]])/3600
            price_gain=100*(ctx["raw"][old["entry"]]["open"]/ctx["raw"][c["entry"]]["open"]-1)
            record=dict(model=candidate,episode=c["episode"],earlier_rth_h=elapsed,
                price_advantage_pct=price_gain,earlier=elapsed>0,lower=price_gain>0)
            paired.append(record);results.append(record)
        summary.append(dict(model=candidate,pair_n=len(paired),earlier=sum(x["earlier"] for x in paired),
            cheaper=sum(x["lower"] for x in paired),
            average_hours_earlier=round(statistics.mean(x["earlier_rth_h"] for x in paired),4) if paired else None,
            average_price_advantage=round(statistics.mean(x["price_advantage_pct"] for x in paired),4) if paired else None))
    return summary,results

def save_csv(path,rows):
    if not rows:return
    cols=list(dict.fromkeys(k for r in rows for k in r))
    with (BASE/path).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)

def main():
    spec=json.loads((BASE/"SPECIFICATION.json").read_text())
    ctx,check=raw_context()
    by_model={};summaries=[];portfolios=[];pairs=[];trades=[]
    for label,profile,minutes,lower in spec["comparisons"]:
        cs=candidates(ctx,label,profile,minutes,lower)
        by_model[label]=cs
        sm,pf,pair,rows=evaluate_model(ctx,label,cs,minutes)
        summaries.extend(sm);portfolios.extend(pf);pairs.extend(pair);trades.extend(rows)
        print("MODEL",label,"signals",len(cs),"time",next((v["mean"],v["win_pct"]) for v in sm if v["exit_policy"]=="time52"),"guard",next((v["mean"],v["win_pct"]) for v in sm if v["exit_policy"]=="finite_guard"),flush=True)
    comp,paired_entries=episode_compare(ctx,by_model)
    price_pair=source_price_pair(ctx)
    # No private vendor OHLCV is written to public-ready result files.
    for f,rows in (("summary_v14.csv",summaries),("portfolio_v14.csv",portfolios),
                   ("paired_exits_v14.csv",pairs),("paired_episodes_v14.csv",paired_entries),
                   ("paired_episode_summary_v14.csv",comp),("source_price_parity_v14.csv",price_pair)):
        save_csv(f,rows)
    # Detailed returns and entries retained on private mini4 as read-only research observations;
    # any GitHub publication requires licensed-data boundary review.
    (BASE/"private_derived_trades_v14.json").write_text(json.dumps(trades,indent=2,default=str))
    findings=dict(schema=spec["schema"],timestamp_basis="ET wall displayed as UTC; restored to aware America/New_York",
       source_consistency=check,model_spec_count=len(by_model),
       entry_counts={x:len(y) for x,y in by_model.items()},
       nested_match=comp,
       earlier_yahoo_entry_compare=dict(n=len(price_pair),matches=sum(x["available"] for x in price_pair),
         worst_abs_open_price_deviation=round(max(abs(x["relative_open_price_pct"]) for x in price_pair if x["available"]),4) if price_pair else None),
       original_full_session_BOATS_proven=False,
       point_in_time_source_qualified=False,
       executable_quote_fills_proven=False,
       honest_limitations=["15m and 30m derive from same stored-5m input and live-tail quotes, not independent replications",
         "Provider adjustment and historical availability not verified",
         "Regular-session source weeks reused after extensive tuning; no untouched holdout",
         "No actual bid-ask or overnight print execution",
         "Calendar completeness only verified for source-observed dates, not exchange-calendar missing whole days"])
    (BASE/"results_v14.json").write_text(json.dumps(findings,indent=2,default=str))
    print("RESULT_DIGEST",hashlib.sha256((BASE/"results_v14.json").read_bytes()).hexdigest(),flush=True)
    print("DATA_CHECK",json.dumps({k:v for k,v in check.items() if k!="source_evidence"}),flush=True)
    print("EPISODE_SUMMARY",json.dumps(comp),flush=True)
    print("OLD_SOURCE_PARITY",findings["earlier_yahoo_entry_compare"],flush=True)
if __name__=="__main__":main()