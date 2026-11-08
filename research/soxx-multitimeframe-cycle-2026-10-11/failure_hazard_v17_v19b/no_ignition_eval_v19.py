#!/usr/bin/env python3
"""Precommitted 3h no-ignition exit, reusing exact existing Terminal sources.

Hypothesis: after first completed 3H parent momentum turn, if price cannot close
above the actual entry price after precisely 3 observed regular trading hours,
sell the remainder at next available 5m opening. The hard stop always prevails.
No optimizer, external vendor, account data, brokerage or production changes.
"""
from pathlib import Path
import bisect,collections,csv,datetime as dt,hashlib,json,math,random,statistics
import study_v14 as s
import parent_delay_controls_v16 as parent
from engine_v6 import simulate
from no_ignition_v19 import NoIgnitionOnce,TimerOnly

ROOT=Path(__file__).resolve().parent
SPEC=json.loads((ROOT/"NO_IGNITION_3H_SPEC_V19.json").read_text())
UTC=dt.timezone.utc
ET=s.ET
assert SPEC["registered_before_new_cohort_data_read"]
DESIGN=set(SPEC["design_in_sample"])
NEW=set(SPEC["new_test_cohort_semis"])
CTRL=set(SPEC["new_test_controls"])
NAME="no_ignition_3h"
DATE_START,DATE_END="2025-10-09","2026-10-08"
BENCHMARK_SOURCE=ROOT/"SOXX_Terminal_15m_ext0.json"

def mean(v):return round(statistics.mean(v),5) if v else None

def ctx15(symbol):
    p=ROOT/(symbol+"_Terminal_15m_ext0.json")
    x=json.loads(p.read_bytes())
    evidence=x.get("source_evidence",{})
    assert x["t"]==symbol and x["tf"]=="15m"
    assert evidence["timestamp_basis"]=="market_local_display_epoch"
    assert evidence["session"]=="regular" and evidence["point_in_time_availability"]=="not_verified"
    assert evidence["price_adjustment"]=="not_verified"
    raw=[];bydate=collections.defaultdict(list)
    for b in x["bars"]:
        display=dt.datetime.fromtimestamp(b[0],UTC)
        local=display.replace(tzinfo=ET)
        day=local.date().isoformat();start=int(local.timestamp())
        end=int((local+dt.timedelta(minutes=15)).timestamp())
        assert 570<=local.hour*60+local.minute<960 and local.minute%15==0
        assert 0<b[3]<=min(b[1],b[4])<=max(b[1],b[4])<=b[2] and b[5]>=0
        raw.append(dict(idx=len(raw),start=start,end=end,local=local.isoformat(),day=day,
          open=b[1],high=b[2],low=b[3],close=b[4],volume=b[5],complete=True))
        bydate[day].append(raw[-1])
    # Do not pretend partial first warmup session is complete. Remove it only
    # before the evaluation window. Even one missing study-year row fails.
    discarded=[]
    for day,rs in list(bydate.items()):
        if len(rs) in (14,26) and rs[0]["local"][11:16]=="09:30":
            assert all(a["end"]==b["start"] for a,b in zip(rs,rs[1:]))
            continue
        if day==min(bydate) and day<DATE_START:
            discarded.append(dict(day=day,partial_rows=len(rs)))
            del bydate[day]
            continue
        raise ValueError(f"15min source incompleteness in {symbol} at {day}")
    raw=[row for row in raw if row["day"] in bydate]
    for i,r in enumerate(raw):r["idx"]=i
    closes={day:rs[-1]["end"] for day,rs in bydate.items()}
    b15=raw
    high={k:s.n.aggregate_minutes(raw,k,closes) for k in (120,180,240)}
    hf={profile:s.n.enrich(high[minutes],macd,p) for profile,(minutes,macd,p) in s.n.PROFILES.items()}
    lower={15:s.n.aggregate_minutes(raw,15,closes)}
    lf={(15,"fast"):s.n.enrich(lower[15],*s.n.LOWERS["fast"])}
    ctx=dict(raw=raw,closes=closes,rejected={},high=high,hf=hf,lower=lower,lf=lf,
         rawstarts=[z["start"] for z in raw],rawends=[z["end"] for z in raw],
         clock=s.n.market_clock(raw),recent=False,first=raw[0]["day"])
    ref=json.loads(BENCHMARK_SOURCE.read_text())
    expected={dt.datetime.fromtimestamp(z[0],UTC).date().isoformat() for z in ref["bars"]
              if DATE_START<=dt.datetime.fromtimestamp(z[0],UTC).date().isoformat()<=DATE_END}
    got={day for day in bydate if DATE_START<=day<=DATE_END}
    assert got==expected,("Missing evaluation dates",symbol,sorted(expected-got)[:6],sorted(got-expected)[:6])
    return ctx,dict(symbol=symbol,source15_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        source15_rows=len(raw),study_days=len(got),excluded_partial_warmup=discarded)

def ctx5(symbol,ctx15m):
    p=ROOT/(symbol+"_Terminal_5m_ext0.json")
    j=json.loads(p.read_bytes())
    evidence=j.get("source_evidence",{})
    assert j["t"]==symbol and j["tf"]=="5m"
    assert evidence["timestamp_basis"]=="market_local_display_epoch"
    assert evidence["session"]=="regular" and evidence["point_in_time_availability"]=="not_verified"
    assert evidence["price_adjustment"]=="not_verified"
    raw=[];bydate=collections.defaultdict(list)
    for t,o,h,l,c,v in j["bars"]:
        local=dt.datetime.fromtimestamp(t,UTC).replace(tzinfo=ET)
        start=int(local.timestamp());end=int((local+dt.timedelta(minutes=5)).timestamp())
        day=local.date().isoformat()
        assert 570<=local.hour*60+local.minute<960 and local.minute%5==0
        assert 0<l<=min(o,c)<=max(o,c)<=h and v>=0
        raw.append(dict(idx=len(raw),start=start,end=end,day=day,local=local.isoformat(),
          open=o,high=h,low=l,close=c,volume=v,complete=True))
        bydate[day].append(raw[-1])
    assert all(a["start"]<b["start"] for a,b in zip(raw,raw[1:]))
    expected_dates={k for k in ctx15m["closes"] if DATE_START<=k<=DATE_END}
    got_dates={k for k in bydate if DATE_START<=k<=DATE_END}
    assert expected_dates==got_dates,("Missing 5min study days",symbol,sorted(expected_dates-got_dates)[:8])
    for day in sorted(expected_dates):
        rs=bydate[day];coarse_days=[x for x in ctx15m["raw"] if x["day"]==day]
        assert len(rs)==3*len(coarse_days) and len(rs) in (42,78),(symbol,day,len(rs))
        assert rs[0]["start"]==coarse_days[0]["start"]
        assert all(a["end"]==b["start"] for a,b in zip(rs,rs[1:]))
        assert rs[-1]["end"]==coarse_days[-1]["end"]
    pxmap={r["start"]:r for r in raw}
    hist=collections.Counter()
    volume_divergent=0;worst_pct=0.
    for r in ctx15m["raw"]:
        if not DATE_START<=r["day"]<=DATE_END:continue
        xs=[pxmap.get(r["start"]+k*300) for k in range(3)]
        assert all(z is not None for z in xs),(symbol,r["local"],"5min source gap")
        O=xs[0]["open"];H=max(v["high"] for v in xs);L=min(v["low"] for v in xs);C=xs[-1]["close"];V=sum(v["volume"] for v in xs)
        assert all(math.isclose(v,r[k],rel_tol=1e-7,abs_tol=1e-3)
                   for v,k in zip((O,H,L,C),("open","high","low","close"))),("source price mismatch",symbol,r["local"])
        volume_gap=100*abs(V-r["volume"])/max(1,V)
        if volume_gap>1e-7:
            worst_pct=max(worst_pct,volume_gap)
            volume_divergent+=1
        hist["compared_price_bars"]+=1
    assert worst_pct<.01,("large source volume discrepancy",symbol,worst_pct)
    return dict(raw=raw,rawstarts=[z["start"] for z in raw],
                rawends=[z["end"] for z in raw],clock=s.n.market_clock(raw),
                _startmap={z["start"]:i for i,z in enumerate(raw)}),dict(
        source5_rows=len(raw),source5_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        compared_OHLC_price_bars=hist["compared_price_bars"],
        volume_only_disagreement_bars=volume_divergent,
        maximum_volume_discrepancy_pct=round(worst_pct,8),
        covered_days=len(expected_dates),
        exact_history_source_basis_proven=False)

def do_policy(raw,entry,stop,predicate):
    return simulate(raw,entry,stop,horizon=100000,partials=[(2,.25)],
        decision=predicate,cost_bps=5,ambiguity="stop_first")

def resolve(ctx15m,context5,source_symbol):
    signals=parent.parents(ctx15m)
    total_parent_arms=parent.all_arms(ctx15m)
    assert len(signals)==len(total_parent_arms)
    result=[];detail=[]
    for c in signals:
        start=ctx15m["raw"][c["entry"]]["start"]
        j=context5["_startmap"].get(start)
        if j is None:
            detail.append(dict(symbol=source_symbol,entry_ET=c["entry_ET"],status="source_entry_not_covered"))
            continue
        a=context5["raw"][j]
        assert math.isclose(a["open"],ctx15m["raw"][c["entry"]]["open"],rel_tol=1e-7,abs_tol=1e-3)
        stop=a["open"]*.985
        baseline=do_policy(context5["raw"],j,stop,TimerOnly())
        check=NoIgnitionOnce()
        tested=do_policy(context5["raw"],j,stop,check)
        if baseline is None or tested is None:
            detail.append(dict(symbol=source_symbol,entry_ET=c["entry_ET"],status="right_censored"))
            continue
        delta=tested["net_pct"]-baseline["net_pct"]
        if tested["reason"]!= "no_ignition_after_3h":
            assert abs(delta)<1e-8 and tested["exit_idx"]==baseline["exit_idx"],"No-effect candidate must preserve same return"
        else:
            assert check.checked and check.failed_at_check and check.checks==1
            assert tested["exit_idx"]<=baseline["exit_idx"]
            assert tested["hold_hours"]>=3
            # Exit must be at opening of the bar after complete three-hour
            # warning bar. No hindsight backdating to prior low.
            assert tested["exit_time"]==context5["raw"][tested["exit_idx"]]["start"]
        era=dt.datetime.fromisoformat(c["entry_ET"]).date()
        week=(era-dt.timedelta(days=era.weekday())).isoformat()
        r=dict(symbol=source_symbol,episode=c["episode"],week=week,status="resolved",
          entry_ET=c["entry_ET"],base_net_pct=round(baseline["net_pct"],5),
          intervention_net_pct=round(tested["net_pct"],5),
          delta_pctpoints=round(delta,5),baseline_reason=baseline["reason"],
          intervention_reason=tested["reason"],
          hard_stop_baseline=baseline["reason"].startswith("stop"),
          prior_stop_before_check=not check.checked,
          check_eligible=check.checked,
          check_failed=bool(check.failed_at_check),
          check_no_ignition_exit=tested["reason"]=="no_ignition_after_3h",
          buyer_loss_avoided_pct=round(max(0,delta),5) if baseline["net_pct"]<0 else 0.,
          winner_sacrificed_pct=round(max(0,-delta),5) if baseline["net_pct"]>0 else 0.,
          harmed_existing_winner=baseline["net_pct"]>0 and delta<-1e-8,
          helped_original_loser=baseline["net_pct"]<0 and delta>1e-8,
          created_winner=baseline["net_pct"]<=0 and tested["net_pct"]>0,
          destroyed_winner=baseline["net_pct"]>0 and tested["net_pct"]<=0)
        detail.append(r);result.append(r)
    return result,detail,len(total_parent_arms)

def grouped_metrics(rows,universe,label):
    z=[x for x in rows if x["symbol"] in universe]
    ys=[x["base_net_pct"] for x in z];zs=[x["intervention_net_pct"] for x in z]
    ds=[x["delta_pctpoints"] for x in z]
    out=dict(label=label,symbols=sorted(universe),resolved=len(z),
        source_episodes=len(z),mean_base=mean(ys),mean_no_ignition=mean(zs),
        mean_difference=mean(ds),
        median_base=mean(sorted(ys)[max(0,(len(ys)-1)//2):max(1,(len(ys)+1)//2)]) if ys else None,
        average_lift_without_best=mean(sorted(ds)[:-1]) if len(ds)>1 else None,
        check_eligible=sum(x["check_eligible"] for x in z),
        stopped_before_3h=sum(x["prior_stop_before_check"] for x in z),
        no_ignition_exits=sum(x["check_no_ignition_exit"] for x in z),
        earlier_losses_helped=sum(x["helped_original_loser"] for x in z),
        earlier_winners_harmed=sum(x["harmed_existing_winner"] for x in z),
        new_winners=sum(x["created_winner"] for x in z),
        lost_winners=sum(x["destroyed_winner"] for x in z),
        winner_sacrifice_total=round(sum(x["winner_sacrificed_pct"] for x in z),5),
        losers_avoided_total=round(sum(x["buyer_loss_avoided_pct"] for x in z),5))
    weeks=collections.defaultdict(list)
    for x in z:weeks[x["week"]].append(x["delta_pctpoints"])
    rng=random.Random(20261011);w=list(weeks.values());boots=[]
    if w and len(w)>2:
        for i in range(6000):
            chosen=[rng.choice(w) for _ in w]
            boots.append(sum(map(sum,chosen))/sum(map(len,chosen)))
        boots.sort()
    out["week_blocks"]=len(w)
    out["block_bootstrap95"]=[round(boots[int(.025*len(boots))],5),round(boots[int(.975*len(boots))],5)] if boots else None
    return out

def run():
    loaded=[];records=[];balances=[];missing=[]
    all_names=SPEC["design_in_sample"]+SPEC["new_test_cohort_semis"]+SPEC["new_test_controls"]
    for symbol in all_names:
        p15=ROOT/(symbol+"_Terminal_15m_ext0.json")
        p5=ROOT/(symbol+"_Terminal_5m_ext0.json")
        if not p15.is_file() or not p5.is_file():
            missing.append(dict(symbol=symbol,missing_15m=not p15.exists(),missing_5m=not p5.exists()))
            print("UNAVAILABLE",symbol,flush=True)
            continue
        try:
            c,quality15=ctx15(symbol)
            d,quality5=ctx5(symbol,c)
            z,detail,total=resolve(c,d,symbol)
            records.extend(z)
            loaded.extend(detail)
            balances.append(dict(symbol=symbol,original_parent_episodes=total,resolved=len(z),
                omitted_due_to_source_or_right_censor=len(detail)-len(z),
                source15=quality15,source5=quality5))
            changed=[x for x in z if x["check_no_ignition_exit"]]
            print("COHORT_SYMBOL",symbol,"parent_arms",total,"resolved",len(z),
                "eligible_check",sum(r["check_eligible"] for r in z),
                "exit_at_3h",len(changed),
                "mean_lift",mean([r["delta_pctpoints"] for r in z]),
                "winners_harmed",sum(r["harmed_existing_winner"] for r in z),
                "losers_helped",sum(r["helped_original_loser"] for r in z),flush=True)
        except Exception as e:
            missing.append(dict(symbol=symbol,error=type(e).__name__,message=str(e)[:220]))
            print("SOURCE_OR_MODEL_REFUSED",symbol,type(e).__name__,str(e)[:160],flush=True)
    assert balances,"no source accepted"
    groups=[
        ("inspected",SPEC["design_in_sample"]),
        ("unseen_names",SPEC["new_test_cohort_semis"]),
        ("sector_controls",SPEC["new_test_controls"]),
        ("all_including_inspected",all_names)]
    summaries=[grouped_metrics(records,set(n),label) for label,n in groups]
    asset_stats=[grouped_metrics(records,{a["symbol"]},a["symbol"]) for a in balances]
    def emit(file,rs):
        if not rs:return
        fields=list(dict.fromkeys(k for x in rs for k in x))
        with (ROOT/file).open("w",newline="") as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rs)
    emit("NO_IGNITION_AGGREGATES_V19.csv",summaries+asset_stats)
    emit("NO_IGNITION_PAIR_DATA_V19.csv",records)
    # Original licensed OHLCV stays private on mini4; results have no prices.
    report=dict(schema=SPEC["schema"],
        original_precommit=hashlib.sha256((ROOT/"NO_IGNITION_3H_SPEC_V19.json").read_bytes()).hexdigest(),
        source_inventory=balances,unavailable=missing,
        group_summary=summaries,asset_summary=asset_stats,
        all_signal_count=sum(x["original_parent_episodes"] for x in balances),
        all_resolved=len(records),
        PIT_qualified=False,raw_vendor_rows_exported=False,unseen_market_year=False,
        no_winning_threshold_selected_after_test=True,
        reliable_historical_fills_proven=False,
        rights_scope="Existing read-only Terminal consumer, research publication aggregate only")
    final=ROOT/"NO_IGNITION_RESULTS_V19.json"
    assert not final.exists(),"Existing result needs reconciliation before rewrite"
    final.write_text(json.dumps(report,indent=2))
    print("GROUPS",json.dumps(summaries),flush=True)
    print("RESULT_SHA",hashlib.sha256(final.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()