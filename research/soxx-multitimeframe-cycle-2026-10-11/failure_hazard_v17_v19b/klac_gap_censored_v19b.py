#!/usr/bin/env python3
"""KLAC gap-censored continuation of the unchanged, predeclared v19 test.
A source gap anywhere between entry and either hypothetical exit makes that
entire paired outcome unknown. No source OHLC values exported to GitHub.
"""
from pathlib import Path
import bisect,collections,csv,datetime as dt,hashlib,json,math
import no_ignition_eval_v19 as prior
from no_ignition_v19 import NoIgnitionOnce,TimerOnly

ROOT=Path(__file__).resolve().parent
UTC=dt.timezone.utc
ET=prior.ET
SPEC=json.loads((ROOT/"KLAC_GAP_CENSOR_SPEC_V19B.json").read_text())
assert SPEC["set_before_running_trade_outcomes"]

def source():
    symbol="KLAC"
    ctx,meta=prior.ctx15(symbol)
    path=ROOT/"KLAC_Terminal_5m_ext0.json"
    j=json.loads(path.read_bytes())
    e=j["source_evidence"]
    assert j["t"]==symbol and j["tf"]=="5m"
    assert e["timestamp_basis"]=="market_local_display_epoch" and e["session"]=="regular"
    assert e["price_adjustment"]=="not_verified" and e["point_in_time_availability"]=="not_verified"
    raw=[];starts=set()
    for epoch,o,h,l,c,v in j["bars"]:
        local=dt.datetime.fromtimestamp(epoch,UTC).replace(tzinfo=ET)
        a=int(local.timestamp());day=local.date().isoformat()
        assert a not in starts;starts.add(a)
        assert 0<l<=min(o,c)<=max(o,c)<=h and v>=0
        raw.append(dict(idx=len(raw),start=a,end=int((local+dt.timedelta(minutes=5)).timestamp()),
             day=day,local=local.isoformat(),open=o,high=h,low=l,close=c,volume=v,complete=True))
    assert len(raw)==20000 and all(a["start"]<b["start"] for a,b in zip(raw,raw[1:]))
    needed=set();source15={}
    for bar in ctx["raw"]:
        if not prior.DATE_START<=bar["day"]<=prior.DATE_END:continue
        source15[bar["start"]]=bar
        needed.update(bar["start"]+j*300 for j in range(3))
    missing=sorted(needed-starts)
    assert len(missing)==7,("unexpected changed snapshot requires new acceptance",len(missing))
    lookup={r["start"]:r for r in raw}
    compared=0;sum_volume_drift=0
    for t,b in source15.items():
        xs=[lookup.get(t+300*k) for k in range(3)]
        if any(x is None for x in xs):continue
        got=(xs[0]["open"],max(x["high"] for x in xs),min(x["low"] for x in xs),xs[-1]["close"])
        assert all(math.isclose(p,b[key],rel_tol=1e-7,abs_tol=1e-3) for p,key in zip(got,("open","high","low","close")))
        compared+=1
        volume=sum(x["volume"] for x in xs)
        sum_volume_drift+=not math.isclose(volume,b["volume"],rel_tol=1e-7,abs_tol=1e-3)
    env=dict(raw=raw,_startmap=lookup,clock=prior.s.n.market_clock(raw))
    meta.update(source5_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                missing_source5_slots=len(missing),evaluated_15m_source_triplets=compared,
                source_volume_precision_drift_count=sum_volume_drift,
                missing_display_ET=[dt.datetime.fromtimestamp(x,ET).isoformat() for x in missing])
    return ctx,env,missing,meta

def run():
    ctx,env,missing,meta=source()
    entries=prior.parent.parents(ctx);arms=prior.parent.all_arms(ctx)
    assert len(entries)==len(arms)
    records=[];unresolved=[]
    for c in entries:
        at=ctx["raw"][c["entry"]]["start"]
        row=env["_startmap"].get(at)
        if row is None:
            unresolved.append(dict(symbol="KLAC",episode=c["episode"],why="no_observed_5m_entry"))
            continue
        en=row["idx"]
        px=row["open"]
        assert math.isclose(px,ctx["raw"][c["entry"]]["open"],rel_tol=1e-7,abs_tol=1e-3)
        check=NoIgnitionOnce()
        a=prior.do_policy(env["raw"],en,px*.985,TimerOnly())
        b=prior.do_policy(env["raw"],en,px*.985,check)
        if a is None or b is None:
            unresolved.append(dict(symbol="KLAC",episode=c["episode"],why="unobserved_future_exit"))
            continue
        upper=max(a["exit_time"],b["exit_time"])
        crosses=[u for u in missing if at<=u<upper]
        if crosses:
            unresolved.append(dict(symbol="KLAC",episode=c["episode"],
                why="source_gap_crosses_any_counterfactual_path",missing_slots=len(crosses)))
            continue
        delta=b["net_pct"]-a["net_pct"]
        assert (b["reason"]=="no_ignition_after_3h") or (abs(delta)<1e-8 and a["exit_idx"]==b["exit_idx"])
        week=dt.datetime.fromisoformat(c["entry_ET"]).date()
        week=(week-dt.timedelta(days=week.weekday())).isoformat()
        records.append(dict(symbol="KLAC",episode=c["episode"],week=week,status="resolved",entry_ET=c["entry_ET"],
            base_net_pct=round(a["net_pct"],5),intervention_net_pct=round(b["net_pct"],5),
            delta_pctpoints=round(delta,5),baseline_reason=a["reason"],intervention_reason=b["reason"],
            check_eligible=check.checked,prior_stop_before_check=not check.checked,
            check_no_ignition_exit=b["reason"]=="no_ignition_after_3h",
            helped_original_loser=a["net_pct"]<0 and delta>1e-8,
            harmed_existing_winner=a["net_pct"]>0 and delta< -1e-8,
            created_winner=a["net_pct"]<=0 and b["net_pct"]>0,
            destroyed_winner=a["net_pct"]>0 and b["net_pct"]<=0,
            buyer_loss_avoided_pct=round(max(0,delta),5) if a["net_pct"]<0 else 0,
            winner_sacrificed_pct=round(max(0,-delta),5) if a["net_pct"]>0 else 0))
    assert len(records)+len(unresolved)==len(arms)
    group=prior.grouped_metrics(records,{"KLAC"},"KLAC_gap_censored")
    out=dict(schema=SPEC["schema"],total_original_arms=len(arms),resolved=len(records),
             unknown=len(unresolved),source_quality=meta,summary=group,
             unresolved_statuses=dict(collections.Counter(x["why"] for x in unresolved)),
             covered_gap_trade_count=sum(x["why"]=="source_gap_crosses_any_counterfactual_path" for x in unresolved),
             conservatively_does_not_impute_trades=True,
             no_overnight_quote_proof=True,
             original_setup_not_tuned=True)
    path=ROOT/"KLAC_GAP_CENSORED_RESULTS_V19B.json"
    assert not path.exists()
    path.write_text(json.dumps(out,indent=2))
    with (ROOT/"KLAC_GAP_CENSORED_PAIR_DATA_V19B.csv").open("w",newline="") as f:
        if records:
            w=csv.DictWriter(f,records[0].keys());w.writeheader();w.writerows(records)
    print("KLAC_GAP_CONTROL",len(missing),"expected minute bars missing",out["total_original_arms"],"arms",
         out["resolved"],"resolved",out["unknown"],"unknown",out["summary"],flush=True)
    print("DIGEST",hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()