#!/usr/bin/env python3
"""Precommitted terminal peer falsification for frozen SOXX 3H/15m and 3H/1H.
No parameter search, credential read, publisher write, broker command, raw rows exported.
"""
from pathlib import Path
import json,csv,hashlib,datetime as dt,statistics,collections,random,math
from zoneinfo import ZoneInfo
import study_v14 as s
BASE=Path(__file__).resolve().parent
UTC=dt.timezone.utc
ET=ZoneInfo("America/New_York")


def _is_rth_15m_start(et):
    """Frozen v14 ET clock rule, expressed as clock values rather than minute IDs.

    This does not add a calendar, alter early-close handling, or strengthen the
    original subminute validation; the existing source checks remain in place.
    """
    return dt.time(9, 30) <= et.time() < dt.time(16, 0) and et.minute % 15 == 0


def _save_episode_pairs(name, rows):
    """Serialize compound episode keys as strings; keep numbers numeric.

    The records and field order are the same as study_v14.save_csv. Explicit
    nonnumeric quoting prevents a string key's bar offsets being read as code.
    """
    if not rows:
        return
    cols = list(dict.fromkeys(k for row in rows for k in row))
    with (BASE / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=cols, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        writer.writerows(rows)

def source_data(symbol,tf):
    path=BASE/f"{symbol}_Terminal_{tf}_ext0.json"
    result=json.loads(path.read_bytes())
    assert result.get("t")==symbol and result.get("tf")==tf
    ev=result["source_evidence"]
    assert ev["session"]=="regular" and ev["timestamp_basis"]=="market_local_display_epoch"
    assert ev["price_adjustment"]=="not_verified" and ev["point_in_time_availability"]=="not_verified"
    assert ev["source_counts"]["unattributed"]==0
    return result,hashlib.sha256(path.read_bytes()).hexdigest()

def peer_context(symbol):
    a,sha15=source_data(symbol,"15m");b,sha30=source_data(symbol,"30m")
    raw=[];days=collections.defaultdict(list);closes={}
    for ep,o,h,l,c,v in a["bars"]:
        et=dt.datetime.fromtimestamp(ep,UTC).replace(tzinfo=ET)
        assert _is_rth_15m_start(et)
        start=int(et.timestamp());end=int((et+dt.timedelta(minutes=15)).timestamp())
        assert 0<l<=min(o,c)<=max(o,c)<=h and v>=0
        row=dict(idx=len(raw),start=start,end=end,day=et.date().isoformat(),local=et.isoformat(),
            open=o,high=h,low=l,close=c,volume=v,complete=True)
        raw.append(row);days[row["day"]].append(row)
    assert len(raw)>3000 and len(b["bars"])*2==len(raw)
    source_head_gaps=[]
    for day,rs in days.items():
        full=len(rs) in (14,26) and rs[0]["local"][11:16]=="09:30"
        if not full:
            # QQQ's FIRST observed 2025-07-14 day has only 10:00-16:00.
            # Keep the missing 09:30-10:00 source slot visible as an unobserved
            # warmup gap; never silently substitute a normal complete session.
            assert symbol=="QQQ" and day==min(days) and len(rs)==24 and rs[0]["local"][11:16]=="10:00"
            assert day<s.DATE_BEGIN,"missing in evaluation year cannot be excused"
            source_head_gaps.append(day)
        assert all(x["end"]==y["start"] for x,y in zip(rs,rs[1:]))
        et=dt.datetime.fromtimestamp(rs[-1]["end"],ET)
        assert (et.hour,et.minute)==((13,0) if len(rs)==14 else (16,0))
        closes[day]=rs[-1]["end"]
    pairs={raw[i]["start"]:raw[i:i+2] for i in range(0,len(raw),2)}
    for ep,o,h,l,c,v in b["bars"]:
        when=dt.datetime.fromtimestamp(ep,UTC).replace(tzinfo=ET)
        xs=pairs[int(when.timestamp())]
        value=(xs[0]["open"],max(t["high"] for t in xs),min(t["low"] for t in xs),
               xs[-1]["close"],sum(t["volume"] for t in xs))
        assert all(math.isclose(q,w,rel_tol=1e-7,abs_tol=1e-3) for q,w in zip(value,(o,h,l,c,v)))
    hb={m:s.n.aggregate_minutes(raw,m,closes) for m in (120,180,240)}
    hf={label:s.n.enrich(hb[m],mac,p) for label,(m,mac,p) in s.n.PROFILES.items()}
    lower={m:s.n.aggregate_minutes(raw,m,closes) for m in (15,30,60)}
    lf={(m,"fast"):s.n.enrich(lower[m],*s.n.LOWERS["fast"]) for m in lower}
    ctx=dict(raw=raw,closes=closes,rejected={},high=hb,hf=hf,lower=lower,lf=lf,
        clock=s.n.market_clock(raw),rawends=[z["end"] for z in raw],rawstarts=[z["start"] for z in raw],
        recent=False,first=raw[0]["day"])
    ctx["_panels"]=s.make_panels(ctx)
    audit=s.fa.source_audit(ctx)
    if audit["missing_intervals"]:
        assert len(audit["gaps"])==len(source_head_gaps),"unexpected intraday gap"
        assert all(g["day"] in source_head_gaps and g["kind"]=="session_head"
                   and g["day"]<s.DATE_BEGIN for g in audit["gaps"])
    ref=json.loads((BASE/"SOXX_Terminal_15m_ext0.json").read_text())
    reference_days={dt.datetime.fromtimestamp(t[0],UTC).date().isoformat() for t in ref["bars"]}
    missing_year=[d for d in sorted(reference_days-set(days)) if s.DATE_BEGIN<=d<=s.DATE_END]
    assert not missing_year,"missing expected regular-session dates during year"
    return ctx,dict(symbol=symbol,source_15m_sha256=sha15,source_30m_sha256=sha30,
        source_15m_bars=len(raw),rth_days=len(days),observed_calendar_gaps=audit["missing_intervals"],
        source_warmup_first_day_head_gaps=source_head_gaps,source_rth_year_missing_days=0,
        source_price_basis="not_verified",point_in_time_admission=False)

def week(entry_et):
    date=dt.datetime.fromisoformat(entry_et).date()
    return (date-dt.timedelta(days=date.weekday())).isoformat()

def run():
    spec=json.loads((BASE/"PEER_SPEC.json").read_text());assert spec["registered_before_fetch"]
    results=[];portfolios=[];pairs=[];audit=[]
    byasset={}
    for symbol in spec["cohort"]:
        ctx,quality=peer_context(symbol)
        audit.append(quality)
        rows=[]
        for label,profile,minutes,lp in spec["models"]:
            cs=s.candidates(ctx,label,profile,minutes,lp)
            sm,pf,pr,detail=s.evaluate_model(ctx,label,cs,minutes)
            for x in sm:results.append(dict(symbol=symbol,**x))
            for x in pf:portfolios.append(dict(symbol=symbol,**x))
            for x in pr:pairs.append(dict(symbol=symbol,week=week(x["entry_ET"]),**x))
            rows.append((label,len(cs),[(x["exit_policy"],x["resolved"],x["mean"],x["win_pct"]) for x in sm if x["exit_policy"] in ("time52","structural_cycle","finite_guard")]))
        byasset[symbol]=rows
        print("PEER_MODEL",symbol,"n",quality["source_15m_bars"],"entries",rows,flush=True)
    # These are simultaneously correlated market episodes; week blocking keeps
    # all common shocks together, but an interval here is not robust OOS proof.
    rng=random.Random(20261011);cluster=[]
    for model in [x[0] for x in spec["models"]]:
        for policy in ("structural_cycle","finite_guard"):
            z=[x for x in pairs if x["model"]==model and x["exit_policy"]==policy]
            grouped=collections.defaultdict(list)
            for x in z:grouped[x["week"]].append(float(x["lift"]))
            blocks=list(grouped.values())
            means=[]
            if blocks:
                for _ in range(3000):
                    sample=[rng.choice(blocks) for i in blocks]
                    means.append(sum(map(sum,sample))/sum(map(len,sample)))
            means.sort()
            cluster.append(dict(model=model,policy=policy,n=len(z),weeks=len(blocks),
                assets=len({t["symbol"] for t in z}),mean_delta=round(statistics.mean(t["lift"] for t in z),4) if z else None,
                saved_losers=sum(t["saved_loser"] for t in z),
                harmed_winners=sum(t["harmed_winner"] for t in z),
                positive_deltas=sum(t["net_trade_improved"] for t in z),
                negative_deltas=sum(t["net_trade_harmed"] for t in z),
                interval95=[round(means[int(.025*len(means))],4),round(means[int(.975*len(means))],4)] if means else None))
    for n,z in [("peer_summary_v14.csv",results),("peer_portfolio_v14.csv",portfolios),("peer_pairs_v14.csv",pairs),
                ("peer_block_stress_v14.csv",cluster)]:
        if n == "peer_pairs_v14.csv":
            _save_episode_pairs(n, z)
        else:
            s.save_csv(n, z)
    provenance=dict(sample="historical 2025-10-09 to2026-10-08",
       source="Terminal's public existing intraday consumer; privately cached price bars not republished",
       predeclared_cohort=spec["cohort"],data_checks=audit,
       inference="Retrospective, models originated from inspected SOXX. Correlated peer stocks not pristine SOXX holdout.",
       model_results=cluster,source_24h_BOATS=False,proven_quoted_market_prices=False)
    (BASE/"peer_results_v14.json").write_text(json.dumps(provenance,indent=2))
    print("PEER_CLUSTER",json.dumps(cluster),flush=True)
    print("PEER_RESULT_SHA",hashlib.sha256((BASE/"peer_results_v14.json").read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()