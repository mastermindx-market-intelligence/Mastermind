#!/usr/bin/env python3
"""Strict earlier-calendar-week trained economic exit value: not a model release.

One fixed ridge model and threshold, no hyperparameter search, no position sizing.
No genuine point-in-time or historical quote marketability is established.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import csv,datetime as dt,hashlib,json,math,random,statistics,sys
HERE=Path(__file__).resolve().parent
PARENT=Path("/private/tmp/soxx_terminal_finepivot_20261011_v14")
sys.path.insert(0,str(PARENT))
import no_ignition_eval_v19 as v
import klac_gap_censored_v19b as klac
import parent_delay_controls_v16 as parent

SPEC=json.loads((HERE/"SPECIFICATION_V22.json").read_text())
assert SPEC["predeclared_before_model_fitting"] and SPEC["NO_NEW_VENDOR_CALLS"]
TIMES=tuple(SPEC["target_times_RTH_hours"])
TARGET_SHRINK=12.
FEATURES=len(SPEC["features_from_completed5m"])
assert FEATURES==6

def ridge(features,target):
    n=len(target)
    means=[statistics.mean(row[i] for row in features) for i in range(FEATURES)]
    std=[]
    for j in range(FEATURES):
        variance=sum((x[j]-means[j])**2 for x in features)/n
        std.append(max(variance**.5,1.e-8))
    X=[[1.]+[(v-means[j])/std[j] for j,v in enumerate(z)] for z in features]
    # Observed extreme rebounds dominate means. Robustly cap training labels
    # only (not realized returns) at the precommitted +/-10 percentage points.
    Y=[max(-10.,min(10.,float(y))) for y in target]
    k=FEATURES+1
    aug=[[0.]* (k+1) for _ in range(k)]
    for x,y in zip(X,Y):
        for i in range(k):
            aug[i][k]+=x[i]*y
            for j in range(k):aug[i][j]+=x[i]*x[j]
    for i in range(1,k):aug[i][i]+=TARGET_SHRINK
    # Solve fixed low-dimensional ridge normal equations via pivoted Gauss-Jordan
    for i in range(k):
        best=max(range(i,k),key=lambda a:abs(aug[a][i]))
        aug[i],aug[best]=aug[best],aug[i]
        piv=aug[i][i]
        if abs(piv)<1e-10:raise ValueError("unexpected singular ridge fit")
        aug[i]=[z/piv for z in aug[i]]
        for j in range(k):
            if j==i:continue
            factor=aug[j][i]
            aug[j]=[a-factor*b for a,b in zip(aug[j],aug[i])]
    beta=[aug[i][k] for i in range(k)]
    return means,std,beta

def predict(model,feature):
    means,std,beta=model
    return beta[0]+sum(beta[i+1]*(v-means[i])/std[i] for i,v in enumerate(feature))

def safe_features(raw,idx,stage,ledger_close):
    expectedbars=int(stage*12)
    if idx<12 or idx+expectedbars>len(raw):
        return None
    seq=raw[idx:idx+expectedbars]
    assert len(seq)==expectedbars
    for a,b in zip(seq,seq[1:]):
        if a["day"]==b["day"]:
            assert a["end"]==b["start"],"missing five-minute source interval"
    px=raw[idx]["open"]
    c=seq[-1]["close"]
    close_return=100*(c/px-1.)
    assert abs(close_return-ledger_close)<.00011,(close_return,ledger_close)
    prev3=seq[max(0,len(seq)-4)]["close"]
    momentum=100*(c/prev3-1.)
    highest=max(x["high"] for x in seq)
    lowest=min(x["low"] for x in seq)
    peak=100*(highest/px-1.)
    adverse=100*(lowest/px-1.)
    loc=(c-lowest)/(highest-lowest) if highest>lowest else .5
    earlier=raw[idx-12:idx]
    intrabar_ranges=[x["high"]-x["low"] for x in earlier]
    prior_range=100*statistics.mean(intrabar_ranges)/px
    return [close_return,momentum,peak,adverse,loc,prior_range]

def mean(xs):
    return round(statistics.mean(xs),6) if xs else None

def bootstrap(xs,group,stage,policy,seed):
    grouped=defaultdict(list)
    for z in xs:grouped[z["week"]].append(z[policy])
    blocks=list(grouped.values());n=len(blocks)
    if n<3:return None
    rng=random.Random(seed)
    out=[]
    for i in range(4000):
        batches=[rng.choice(blocks) for _ in range(n)]
        out.append(sum(map(sum,batches))/sum(map(len,batches)))
    out.sort()
    return [round(out[100],6),round(out[3900],6)]

def run():
    ledger=list(csv.DictReader((HERE/"DECISION_TIMING_EVENT_DIAGNOSTICS_V21.csv").open()))
    opportunities=[];sources=[]
    # Data roots are private; no prices or exact source records are written to
    # GitHub-facing outputs.
    for symbol in SPEC["cohort"]:
        if symbol=="KLAC":
            c,f,missing,qual=klac.source()
        else:
            c,q15=v.ctx15(symbol);f,q5=v.ctx5(symbol,c)
            missing=[];qual={**q15,**q5}
        lookup={x["episode"]:x for x in parent.parents(c)}
        sources.append(dict(symbol=symbol,episodes=len(lookup),
            source5_sha256=qual.get("source5_sha256"),missing_source5=len(missing)))
        for stage in TIMES:
            records=[r for r in ledger if r["symbol"]==symbol and r["mode"]=="force" and float(r["checkpoint_h"])==stage]
            assert len(records)==len(lookup)
            for r in records:
                if r["status"]!="resolved":
                    opportunities.append(dict(symbol=symbol,week=r["entry_week"],episode=r["episode"],stage=stage,status="unknown"))
                    continue
                if r["eligible"]!="True":
                    # Already stopped or closed. No decision can modify economics.
                    opportunities.append(dict(symbol=symbol,week=r["entry_week"],episode=r["episode"],stage=stage,
                        status="not_actionable",oracle_diff=0.,naive_diff=0.,baseline_return=float(r["baseline_net_pct"])))
                    continue
                arm=lookup[r["episode"]]
                en=f["_startmap"].get(c["raw"][arm["entry"]]["start"])
                if isinstance(en,dict):en=en["idx"]
                assert isinstance(en,int)
                x=safe_features(f["raw"],en,stage,float(r["check_close_pct"]))
                if x is None:
                    opportunities.append(dict(symbol=symbol,week=r["entry_week"],episode=r["episode"],stage=stage,status="unknown"))
                    continue
                delta=float(r["delta_pp"])
                opportunities.append(dict(symbol=symbol,week=r["entry_week"],episode=r["episode"],stage=stage,
                    status="eligible",features=x,target_delta=delta,baseline_return=float(r["baseline_net_pct"]),
                    oracle_diff=max(delta,0.),naive_diff=delta if x[0]<0 else 0.))
    # Strict walk-forward: a model for the current Monday-Sunday stock cohort
    # may learn from earlier weeks only. No current-week crossasset target leaks.
    data=[];summary=[]
    for stage in TIMES:
        cohort=[r for r in opportunities if r["stage"]==stage]
        weeks=sorted(set(r["week"] for r in cohort if r["status"]=="eligible"))
        models={}
        for current in weeks:
            train=[r for r in cohort if r["status"]=="eligible" and r["week"]<current]
            blocks=len(set(x["week"] for x in train))
            if len(train)>=20 and blocks>=6:
                models[current]=ridge([x["features"] for x in train],[x["target_delta"] for x in train])
        for row in cohort:
            forecastable=row["status"]=="eligible" and row["week"] in models
            score=predict(models[row["week"]],row["features"]) if forecastable else None
            do_exit=bool(forecastable and score>.25)
            r=dict(symbol=row["symbol"],week=row["week"],episode=row["episode"],
                checkpoint_h=stage,status=row["status"],forecastable=forecastable,
                prior_training_weeks=len(set(x["week"] for x in cohort if x["week"]<row["week"] and x["status"]=="eligible")) if forecastable else 0,
                model_decision_exit=do_exit,
                model_predicted_advantage_pp=round(score,5) if score is not None else None,
                realized_economic_lift_pp=row.get("target_delta",0.) if do_exit else 0.,
                naive_below_entry_lift_pp=row.get("naive_diff",0.) if forecastable else 0.,
                oracle_hindsight_upper_bound_pp=row.get("oracle_diff",0.) if forecastable else 0.,
                trade_was_originally_winning=row.get("baseline_return",0)>0,
                assisted_loser=bool(do_exit and row.get("baseline_return",0)<0 and row.get("target_delta",0)>0),
                injured_winner=bool(do_exit and row.get("baseline_return",0)>0 and row.get("target_delta",0)<0))
            data.append(r)
        for grouping,group_sym in [
          ("all",set(SPEC["cohort"])),("new_semis",{"NVDA","MU","INTC","AMAT","LRCX","KLAC"}),
          ("inspected",{"SOXX","SMH","QQQ","AMD"}),("sector_controls",{"XLV","XLE"})]:
            group=[x for x in data if x["checkpoint_h"]==stage and x["symbol"] in group_sym]
            subset=[x for x in group if x["forecastable"]]
            actions=[x for x in subset if x["model_decision_exit"]]
            stat=dict(group=grouping,checkpoint_h=stage,all_original_episodes=len(group),
                forecastable_eligible=len(subset),calendar_weeks_with_forecasts=len(set(x["week"] for x in subset)),
                trades_exited_by_model=len(actions),
                helped_original_losers=sum(x["assisted_loser"] for x in actions),
                harmed_original_winners=sum(x["injured_winner"] for x in actions),
                model_economic_lift_on_test_episodes_pp=mean([x["realized_economic_lift_pp"] for x in subset]),
                naive_close_below_entry_same_episodes_pp=mean([x["naive_below_entry_lift_pp"] for x in subset]),
                baseline_always_hold_same_episodes_pp=0.,
                hindsight_oracle_upper_bound_same_episodes_pp=mean([x["oracle_hindsight_upper_bound_pp"] for x in subset]),
                model_economic_lift_per_all_original_opportunities_pp=mean([x["realized_economic_lift_pp"] for x in group]),
                model_leave_biggest_benefit_out_mean=mean(sorted(x["realized_economic_lift_pp"] for x in subset)[:-1]) if len(subset)>1 else None,
                no_forecast_original_opportunities=len(group)-len(subset))
            for label in ("model","naive"):
                col="realized_economic_lift_pp" if label=="model" else "naive_below_entry_lift_pp"
                stat[label+"_week_block95"]=bootstrap(subset,grouping,stage,col,20261012+(0 if label=="model" else 71)+int(stage*10))
            summary.append(stat)
        print("STAGE",stage,
            [(x["group"],x["forecastable_eligible"],x["trades_exited_by_model"],
              x["model_economic_lift_on_test_episodes_pp"],x["naive_close_below_entry_same_episodes_pp"]) for x in summary if x["checkpoint_h"]==stage],flush=True)
    def write_rows(file,values):
        fields=list(dict.fromkeys(k for x in values for k in x))
        with (HERE/file).open("w",newline="") as fp:
            w=csv.DictWriter(fp,fieldnames=fields);w.writeheader();w.writerows(values)
    write_rows("WALK_FORWARD_DECISIONS_V22.csv",data)
    write_rows("WALK_FORWARD_AGGREGATES_V22.csv",summary)
    report=dict(schema=SPEC["schema"],spec_sha256=hashlib.sha256((HERE/"SPECIFICATION_V22.json").read_bytes()).hexdigest(),
        cohort=sources,results=summary,regular_session_only=True,
        training_scope="only earlier market weeks, ≥20 eligible rows and ≥6 distinct earlier weeks",
        source_price_PIT_verified=False,
        model_originated_sizing_allowed=False,
        hindsight_oracle_is_not_tradable=True,
        selection_note="Two predeclared stages are not independently held-out and are highly correlated. No extra model variants selected.")
    target=HERE/"RESULTS_V22.json"
    assert not target.exists()
    target.write_text(json.dumps(report,indent=2))
    print("RESULT_SHA",hashlib.sha256(target.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()