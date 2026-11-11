#!/usr/bin/env python3
"""v21 predeclared decision-time rescue ceiling; private Terminal RTH only.
Shows *bounds*, not a remotely deployed signal or authorized quote-executable trade.
"""
from __future__ import annotations
import csv,collections,datetime as dt,hashlib,json,random,statistics,sys,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
PARENT=Path("/private/tmp/soxx_terminal_finepivot_20261011_v14")
sys.path.insert(0,str(PARENT))
import no_ignition_eval_v19 as v
import klac_gap_censored_v19b as klac
import parent_delay_controls_v16 as parent
from no_ignition_v19 import TimerOnly

S=json.loads((HERE/"SPECIFICATION_V21.json").read_text())
assert S["predeclared_before_stage_evaluation"] and S["no_reopt"]
STAGES=tuple(S["checkpoints_market_hours"])
COHORT=tuple(S["cohort"])
MODES=("force","below_entry","half_peak")

class CheckAndAct(TimerOnly):
    def __init__(self,target,mode):
        super().__init__(52.)
        if target not in STAGES or mode not in MODES:
            raise ValueError("only precommitted checkpoint and policy permitted")
        self.target=target
        self.mode=mode
        self.checked=False
        self.signal=False
        self.close_pct=None
        self.peak_pct=None
        self.note=None
        self.elapsed=None
        self.bar_end=None
    def __call__(self,st,bar):
        default=super().__call__(st,bar)
        if not self.checked and st["age_hours"]>=self.target-1e-7:
            self.checked=True
            self.elapsed=st["age_hours"]
            self.bar_end=bar["end"]
            close=bar["close"]
            self.close_pct=100*(close/st["px"]-1)
            self.peak_pct=100*(st["peak"]/st["px"]-1)
            if self.mode=="force":
                self.signal=True
            elif self.mode=="below_entry":
                self.signal=close<st["px"]
            elif self.mode=="half_peak":
                self.signal=st["peak"]>st["px"] and close<st["px"]+.5*(st["peak"]-st["px"])
            if self.signal and not default:
                return dict(sell=st["remaining"],reason="v21_"+self.mode+"_at_"+str(self.target))
        return default

def week(stamp):
    d=dt.datetime.fromisoformat(stamp).date()
    return (d-dt.timedelta(days=d.weekday())).isoformat()

def mean(xs):
    return round(statistics.mean(xs),6) if xs else None

def relevant(records,category):
    if category=="all":return records
    if category=="inspected":return [x for x in records if x["symbol"] in ("SOXX","SMH","QQQ","AMD")]
    if category=="new_semis":return [x for x in records if x["symbol"] in ("NVDA","MU","INTC","AMAT","LRCX","KLAC")]
    if category=="sector":return [x for x in records if x["symbol"] in ("XLV","XLE")]
    raise ValueError(category)

def aggregate(records,name,mode,stage):
    rows=[r for r in relevant(records,name) if r["mode"]==mode and r["checkpoint_h"]==stage]
    assert rows
    unknown=sum(r["status"]=="unknown" for r in rows)
    known=[r for r in rows if r["status"]=="resolved"]
    elig=[r for r in known if r["eligible"]]
    affected=[r for r in known if r["rule_actually_changed_economics"]]
    delta=[r["delta_pp"] for r in known]
    good=[r for r in affected if r["delta_pp"]>1e-8]
    bad=[r for r in affected if r["delta_pp"]<-1e-8]
    return dict(group=name,mode=mode,checkpoint_h=stage,total=len(rows),known=len(known),unknown=unknown,
        eligible=len(elig),closed_before_checkpoint=len(known)-len(elig),
        original_winners=sum(r["baseline_net_pct"]>0 for r in known),
        triggering=len([r for r in known if r["signal"]]),
        economic_changes=len(affected),
        improved=len(good),harmed=len(bad),
        original_losers_helped=sum(r["baseline_net_pct"]<=0 for r in good),
        previous_winners_harmed=sum(r["baseline_net_pct"]>0 for r in bad),
        original_winners_helped=sum(r["baseline_net_pct"]>0 for r in good),
        original_losers_harmed=sum(r["baseline_net_pct"]<=0 for r in bad),
        changed_mean_pp=mean([r["delta_pp"] for r in affected]),
        mean_incremental_return_pp=mean(delta),
        net_sum_delta_pp=round(sum(delta),5),
        sum_positive_pp=round(sum(max(0,x) for x in delta),5),
        sum_surrendered_pp=round(-sum(min(0,x) for x in delta),5),
        oracle_maximum_possible_pp_per_original_episode=mean([r["oracle_gain_pp"] for r in known]) if mode=="force" else None,
        oracle_available_fraction=len(elig)/len(known) if known else None)

def bootstrap(records,stage,mode,group="new_semis",n=2000):
    rs=[x for x in relevant(records,group) if x["checkpoint_h"]==stage and x["mode"]==mode and x["status"]=="resolved"]
    grouped=collections.defaultdict(list)
    for r in rs:grouped[r["entry_week"]].append(r["delta_pp"])
    blocks=list(grouped.values())
    if len(blocks)<3:return dict(stage=stage,mode=mode,group=group,market_weeks=len(blocks),interval95=None)
    rnd=random.Random(20261012+int(stage*12)+MODES.index(mode))
    samples=[]
    for _ in range(n):
        batch=[rnd.choice(blocks) for _ in blocks]
        samples.append(sum(sum(z) for z in batch)/sum(len(z) for z in batch))
    samples.sort()
    return dict(stage=stage,mode=mode,group=group,
        market_weeks=len(blocks),
        n=len(rs),
        mean_delta_pp=mean([r["delta_pp"] for r in rs]),
        cluster_block95_pp=[round(samples[int(.025*n)],5),round(samples[int(.975*n)],5)],
        caveat="Exploratory, correlated symbols and repeatedly inspected year")

def run():
    data=[];sources=[];unknowns=[]
    for symbol in COHORT:
        if symbol=="KLAC":
            ctx,fin,missing,qual=klac.source()
        else:
            ctx,q15=v.ctx15(symbol);fin,q5=v.ctx5(symbol,ctx)
            missing=[];qual={**q15,**q5}
        arms=parent.parents(ctx)
        assert len(arms)==len(parent.all_arms(ctx))
        sources.append(dict(symbol=symbol,entries=len(arms),
            source5_sha=qual.get("source5_sha256"),
            source5_missing_5m_intervals=len(missing)))
        for arm in arms:
            orig_at=ctx["raw"][arm["entry"]]["start"]
            idx=fin["_startmap"].get(orig_at)
            if idx is None:
                unknowns.append(dict(symbol=symbol,episode=arm["episode"],why="missing_entry_5m"))
                for h in STAGES:
                    for mode in MODES:
                        data.append(dict(symbol=symbol,episode=arm["episode"],entry_week=week(arm["entry_ET"]),
                            checkpoint_h=h,mode=mode,status="unknown"))
                continue
            if isinstance(idx,dict):idx=idx["idx"]
            px=fin["raw"][idx]["open"];assert math.isclose(px,ctx["raw"][arm["entry"]]["open"],rel_tol=1e-7,abs_tol=1e-3)
            stop=px*.985
            baseline=v.do_policy(fin["raw"],idx,stop,TimerOnly())
            assert baseline is not None
            for h in STAGES:
                for mode in MODES:
                    checker=CheckAndAct(h,mode)
                    intervention=v.do_policy(fin["raw"],idx,stop,checker)
                    status="resolved"
                    if intervention is None:
                        status="unknown"
                    else:
                        after=max(baseline["exit_time"],intervention["exit_time"])
                        if any(orig_at<=t<after for t in missing):status="unknown"
                    if status=="unknown":
                        unknowns.append(dict(symbol=symbol,episode=arm["episode"],checkpoint_h=h,mode=mode,why="path_not_observed"))
                        data.append(dict(symbol=symbol,episode=arm["episode"],entry_week=week(arm["entry_ET"]),
                            checkpoint_h=h,mode=mode,status="unknown"))
                        continue
                    change=intervention["net_pct"]-baseline["net_pct"]
                    if not checker.checked:assert abs(change)<1e-8
                    if checker.signal and checker.checked:
                        # An actionable indicator can be defeated by an opening stop/gap.
                        assert intervention["exit_idx"]<=baseline["exit_idx"]
                    data.append(dict(symbol=symbol,episode=arm["episode"],entry_week=week(arm["entry_ET"]),
                        checkpoint_h=h,mode=mode,status="resolved",
                        eligible=checker.checked,signal=checker.signal,
                        check_age_h=round(checker.elapsed,5) if checker.checked else None,
                        check_close_pct=round(checker.close_pct,5) if checker.checked else None,
                        peak_gain_pct=round(checker.peak_pct,5) if checker.checked else None,
                        baseline_net_pct=round(baseline["net_pct"],6),
                        intervention_net_pct=round(intervention["net_pct"],6),
                        delta_pp=round(change,6),
                        oracle_gain_pp=round(max(0.,change),6) if mode=="force" else None,
                        rule_actually_changed_economics=abs(change)>1e-8,
                        baseline_exit_reason=baseline["reason"],
                        chosen_exit_reason=intervention["reason"],
                        same_path_gap_stop=(baseline["reason"]=="stop_gap" and intervention["reason"]=="stop_gap")))
        print("STUDY_SYMBOL",symbol,"source_entries",len(arms),"new_records",sum(x["symbol"]==symbol for x in data),flush=True)
    assert len(data)==sum(x["entries"] for x in sources)*len(STAGES)*len(MODES)
    # Equivalent force-at-3h oracle must replicate already accepted v20 receipts,
    # preventing silent engine/label drift in new research.
    previous=json.loads((PARENT/"ORACLE_UPPER_BOUND_RESULTS_V20.json").read_text())
    assert previous["original_arms"]==91 and not unknowns
    result=[]
    for h in STAGES:
        for mode in MODES:
            for group in ("all","inspected","new_semis","sector"):
                result.append(aggregate(data,group,mode,h))
    old=next(x for x in previous["groups"] if x["group"]=="all")
    now=next(x for x in result if x["group"]=="all" and x["mode"]=="force" and x["checkpoint_h"]==3.)
    assert now["known"]==old["n"] and now["eligible"]==old["eligible"]
    assert abs(now["oracle_maximum_possible_pp_per_original_episode"]-
               old["oracle_gain_pp_per_original_opportunity"])<.000015
    for grp in ("new_semis","all"):
        o=next(z for z in previous["groups"] if z["group"]==grp)
        n=next(z for z in result if z["group"]==grp and z["mode"]=="force" and z["checkpoint_h"]==3.)
        assert n["known"]==o["n"] and n["eligible"]==o["eligible"]
        assert abs(n["oracle_maximum_possible_pp_per_original_episode"]-
                   o["oracle_gain_pp_per_original_opportunity"])<.000015
    bs=[]
    for h in STAGES:
        for mode in MODES:
            for grp in ("new_semis","all"):
                bs.append(bootstrap(data,h,mode,grp))
    cols=list(data[0])
    with (HERE/"DECISION_TIMING_EVENT_DIAGNOSTICS_V21.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,cols);w.writeheader();w.writerows(data)
    with (HERE/"DECISION_TIMING_AGGREGATES_V21.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,list(result[0]));w.writeheader();w.writerows(result)
    report=dict(schema=S["schema"],spec_sha256=hashlib.sha256((HERE/"SPECIFICATION_V21.json").read_bytes()).hexdigest(),
        original_episodes=sum(x["entries"] for x in sources),stage_opportunity_rows=len(data),
        sources=sources,uncertainties=unknowns,
        summaries=result,bootstrap=bs,
        v20_oracle_3h_reproduced=True,
        future_oracle_is_not_a_strategy=True,
        publication_rights_to_raw_licensed_data=False,
        executable_bid_ask_quote_path_proven=False,
        next_research="Compare first available risk information and precommitted walk-forward expected *incremental* continuation value, not simply win/loss labels.")
    path=HERE/"RESULTS_V21.json"
    assert not path.exists(),"Prior run must be readback-reconciled"
    path.write_text(json.dumps(report,indent=2))
    for h in STAGES:
        out=[v for v in result if v["group"]=="all" and v["checkpoint_h"]==h]
        print("CHECKPOINT",h,[dict(mode=x["mode"],eligible=x["eligible"],
          lift=x["mean_incremental_return_pp"],oracle=x["oracle_maximum_possible_pp_per_original_episode"],
          previous_winners_harmed=x["previous_winners_harmed"],
          original_losers_helped=x["original_losers_helped"]) for x in out],flush=True)
    print("SHA",hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()