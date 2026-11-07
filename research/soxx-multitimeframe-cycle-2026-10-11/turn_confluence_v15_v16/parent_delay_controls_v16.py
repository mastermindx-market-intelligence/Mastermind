#!/usr/bin/env python3
"""Parent-turn only vs causal nested-pivot confluence, frozen RTH source and exit.
No model tuning; all original extreme episodes are counted. Zero means no trade;
right censored remains unknown, never imputed as a profitable outcome.
"""
from pathlib import Path
import bisect,collections,csv,datetime as dt,hashlib,json,random,statistics
import study_v14 as s
import peer_v14 as peers

ROOT=Path(__file__).resolve().parent
SPEC=json.loads((ROOT/"PARENT_ONLY_AND_DELAY_CONTROLS_SPEC_V16.json").read_text())
assert SPEC["pre_specified_before_outcomes"] is True
DELAY=[0.,1.,2.,4.,8.]
CONFLUENCE=("turn_pivot_15","turn_pivot_30")

def mean(xs):return round(statistics.mean(xs),4) if xs else None
def median(xs):return round(statistics.median(xs),4) if xs else None
def arm_clock(ctx,ep):
    hb=ctx["high"][180];arm=ep["arm"];at=hb[arm]["end"]
    ai=bisect.bisect_left(ctx["rawends"],at)
    if ai>=len(ctx["raw"]):return None
    return ctx["clock"][ai+1] if ctx["raw"][ai]["end"]==at else ctx["clock"][ai]

def parents(ctx):
    hb=ctx["high"][180];hf=ctx["hf"]["3h_medium"]
    raw,clock=ctx["raw"],ctx["clock"]
    records=[]
    for ep in s.n.b.setup_episodes(hb,hf,side=1,level=2):
        ar=ep["arm"];armat=hb[ar]["end"]
        if not s.DATE_BEGIN<=hb[ar]["day"]<=s.DATE_END:continue
        ac=arm_clock(ctx,ep)
        if ac is None:continue
        for hi in range(ar,len(hb)):
            q=hb[hi];at=q["end"]
            if at<armat:continue
            en=bisect.bisect_left(ctx["rawstarts"],at)
            if en>=len(raw):break
            if clock[en]-ac>s.n.EXPIRY_SECONDS:break
            if not q["complete"] or not s.n.higher_state(hf,hi,1,"turn"):continue
            lowerhi=s.n.asof([x["end"] for x in ctx["lower"][15]],at)
            if lowerhi<3:continue
            lv=ctx["lower"][15][lowerhi]
            anchor=min(x["low"] for x in ctx["lower"][15][max(0,lowerhi-4):lowerhi+1])
            atr=ctx["lf"][15,"fast"]["atr"][lowerhi]
            if not atr or atr<=0:continue
            assert raw[en]["start"]>=at and q["end"]<=raw[en]["start"]
            record=dict(profile="3h_medium",episode=f'3h_medium:{ep["episode"]}',
                entry=en,entry_ET=raw[en]["local"],phase="year",state="turn",
                arm_time=armat,arm_day=hb[ar]["day"],signal_time=at,higher_time=at,
                signal_idx=s.n.asof(ctx["rawends"],at),anchor=anchor,anchor_kind="fallback_prior_15m_range",
                atr=atr,lower_minutes=15,stop=raw[en]["open"]*.985)
            records.append(record);break
    assert len({z["episode"] for z in records})==len(records)
    return records

def all_arms(ctx):
    hb=ctx["high"][180];out=[]
    for ep in s.n.b.setup_episodes(hb,ctx["hf"]["3h_medium"],side=1,level=2):
        if s.DATE_BEGIN<=hb[ep["arm"]]["day"]<=s.DATE_END:
            out.append(f'3h_medium:{ep["episode"]}')
    return out

def delay_entry(ctx,c,delay):
    clock=ctx["clock"];raw=ctx["raw"];armtime=c["arm_time"]
    ac=clock[c["entry"]]
    target=ac+delay*3600
    k=bisect.bisect_left(clock,target)
    if k>=len(raw) or clock[k]-arm_clock_of(c,ctx)>s.n.EXPIRY_SECONDS:return None
    if raw[k]["start"]<c["signal_time"]:return None
    z=dict(c,entry=k,entry_ET=raw[k]["local"],stop=raw[k]["open"]*.985)
    return z

def arm_clock_of(c,ctx):
    i=bisect.bisect_left(ctx["rawends"],c["arm_time"])
    return ctx["clock"][i+1] if i<len(ctx["raw"]) and ctx["raw"][i]["end"]==c["arm_time"] else ctx["clock"][i]

def simulate(ctx,c):
    if c is None:return None
    t,_=s.run_exit(ctx,c,"time52",15)
    return t

def upper_child_candidates(ctx):
    candidates={}
    for m in (15,30):
        name=f'turn_pivot_{m}'
        cs=s.simultaneous_child(ctx,m) if hasattr(s,"simultaneous_child") else None
        if cs is None:
            cs=s.n.candidates(ctx,"3h_medium",m,"fast","turn","pivot_turn",1,expiry=s.n.EXPIRY_SECONDS,level=2)
        ans={}
        for x in cs:
            if not s.DATE_BEGIN<=ctx["raw"][x["entry"]]["day"]<=s.DATE_END:continue
            episode=x["episode"]
            ans[episode]=dict(x,stop=ctx["raw"][x["entry"]]["open"]*.985,
                entry_ET=ctx["raw"][x["entry"]]["local"],phase="year")
        candidates[name]=ans
    return candidates

def summarise(values,zero_if_skipped=True):
    successes=[x for x in values if x["status"]=="resolved"]
    vals=[x["return_pct"] for x in successes]
    missing=sum(x["status"]=="unknown" for x in values)
    skipped=sum(x["status"]=="no_trigger" for x in values)
    den=[(x["return_pct"] if x["status"]=="resolved" else 0.) for x in values if x["status"]!="unknown"]
    return dict(parent_arm_opportunities=len(values),resolved=len(vals),
        no_trigger=skipped,unknown=missing,winners=sum(x>0 for x in vals),
        win_pct=round(100*sum(x>0 for x in vals)/len(vals),2) if vals else None,
        mean_conditional=mean(vals),median_conditional=median(vals),
        mean_per_arm_cash_nonfills=mean(den) if not missing else None,
        best=round(max(vals),4) if vals else None,
        worst=round(min(vals),4) if vals else None,
        mean_without_largest_winner=mean(sorted(vals)[:-1]) if len(vals)>1 else None,
        stop_count=sum(x.get("exit_reason","").startswith("stop") for x in successes))

def run():
    rows=[];summary=[];same=[];quality=[];policy_names=["parent_only",*CONFLUENCE]+["parent_delay_"+str(int(z)) for z in DELAY[1:]]
    for symbol in ("SOXX","SMH","QQQ","AMD"):
        ctx,source_quality=s.raw_context() if symbol=="SOXX" else peers.peer_context(symbol)
        armset=all_arms(ctx)
        pts={x["episode"]:x for x in parents(ctx)}
        children=upper_child_candidates(ctx)
        assert set(pts).issubset(armset)
        assert all(set(xs).issubset(armset) for xs in children.values())
        quality.append(dict(symbol=symbol,all_extreme_arms=len(armset),
            parent_turn_trigger=len(pts),turn_15m=len(children["turn_pivot_15"]),
            turn_30m=len(children["turn_pivot_30"])))
        book={}
        for arm in armset:
            variants=dict(parent_only=pts.get(arm),
                turn_pivot_15=children["turn_pivot_15"].get(arm),
                turn_pivot_30=children["turn_pivot_30"].get(arm))
            for delta in DELAY[1:]:
                variants["parent_delay_"+str(int(delta))]=delay_entry(ctx,pts[arm],delta) if arm in pts else None
            for strategy,c in variants.items():
                t=simulate(ctx,c) if c else None
                if c is None:status="no_trigger"
                elif t is None:status="unknown"
                else:status="resolved"
                data=dict(symbol=symbol,arm=arm,policy=strategy,status=status,
                    entry_ET=c["entry_ET"] if c else None,
                    entry_index=c["entry"] if c else None,
                    return_pct=t["net_pct"] if t else None,
                    exit_reason=t["reason"] if t else None,
                    stop_age_RTH_h=t["hold_hours"] if t and t["reason"].startswith("stop") else None,
                    time_from_original_parent_open_RTH_h=(ctx["clock"][c["entry"]]-ctx["clock"][pts[arm]["entry"]])/3600
                        if c and arm in pts else None)
                rows.append(data);book[arm,strategy]=data
        for policy in policy_names:
            x=[r for r in rows if r["symbol"]==symbol and r["policy"]==policy]
            assert len(x)==len(armset)
            summary.append(dict(symbol=symbol,policy=policy,**summarise(x)))
        for arm in armset:
            base=book[arm,"parent_only"]
            for policy in ("turn_pivot_15","turn_pivot_30",*["parent_delay_"+str(int(x)) for x in DELAY[1:]]):
                x=book[arm,policy]
                if x["status"]!="resolved" or base["status"]!="resolved":continue
                change=x["return_pct"]-base["return_pct"]
                day=dt.datetime.fromisoformat(x["entry_ET"]).date();week=(day-dt.timedelta(days=day.weekday())).isoformat()
                same.append(dict(symbol=symbol,arm=arm,week=week,policy=policy,
                    parent_return_pct=round(base["return_pct"],4),conditional_return_pct=round(x["return_pct"],4),
                    paired_return_change_pctpoints=round(change,4),
                    entry_delay_RTH_hours=x["time_from_original_parent_open_RTH_h"],
                    parent_winner_harmed=base["return_pct"]>0 and change<-.000001,
                    parent_loser_saved=base["return_pct"]<0 and change>.000001))
        print("SOURCE",symbol,"arms",len(armset),"parent_turns",len(pts),
           "conjunctions",[(x,len(children[x])) for x in CONFLUENCE],flush=True)
        for policy in policy_names:
            x=summary[-len(policy_names):]
            row=next(v for v in x if v["policy"]==policy)
            print("  STRATEGY",policy,"trades",row["resolved"],"wins",row["winners"],
                "avg",row["mean_conditional"],"ITT",row["mean_per_arm_cash_nonfills"],
                "withoutbest",row["mean_without_largest_winner"],flush=True)
    # Shared SEMI sector shock week clustering. This is a diagnostic not a pristine test.
    rng=random.Random(1602);cluster=[]
    for policy in [*CONFLUENCE, "parent_delay_1","parent_delay_2","parent_delay_4","parent_delay_8"]:
        x=[r for r in same if r["policy"]==policy]
        groups=collections.defaultdict(list)
        for row in x:groups[row["week"]].append(row["paired_return_change_pctpoints"])
        weeks=list(groups.values());boots=[]
        for _ in range(4000):
            if not weeks:break
            chosen=[rng.choice(weeks) for k in weeks]
            boots.append(sum(map(sum,chosen))/sum(map(len,chosen)))
        boots.sort()
        cluster.append(dict(policy=policy,pair_n=len(x),weeks=len(weeks),
            mean_lift=mean([r["paired_return_change_pctpoints"] for r in x]),
            benefited=sum(r["paired_return_change_pctpoints"]>1e-6 for r in x),
            harmed=sum(r["paired_return_change_pctpoints"]<-1e-6 for r in x),
            winner_harmed=sum(r["parent_winner_harmed"] for r in x),
            loser_helped=sum(r["parent_loser_saved"] for r in x),
            week_block95=[round(boots[int(.025*len(boots))],4),round(boots[int(.975*len(boots))],4)] if boots else None))
    for file,records in [("parent_delay_summary_v16.csv",summary),("parent_delay_same_arms_v16.csv",same),
                         ("parent_delay_cluster_v16.csv",cluster)]:
        s.save_csv(file,records)
    (ROOT/"parent_delay_private_ledger_v16.json").write_text(json.dumps(rows,indent=2))
    outcome=dict(schema=SPEC["schema"],predeclared_before_outcome=True,
       original_extreme_arm_denominator=sum(x["all_extreme_arms"] for x in quality),
       source_quality=quality,strategies=summary,peer_week_block=cluster,
       raw_prices_exported=False,points_in_time_claims=False,
       decision_rule="Next observed RTH 15m open after confirmed higher frame close; no future bars in parent condition",
       note="No original SOXX year is untouched; cross asset shocks are correlated.")
    (ROOT/"parent_delay_results_v16.json").write_text(json.dumps(outcome,indent=2))
    print("BLOCKS",json.dumps(cluster),flush=True)
    print("RESULT",hashlib.sha256((ROOT/"parent_delay_results_v16.json").read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()