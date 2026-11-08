#!/usr/bin/env python3
"""Observable accuracy needed to make early SOXX cycle-failure exits worthwhile.
Excludes missed decisions and distinguishes opportunity counts from classifier
conditional accuracy. Historic net-return differences, not feasible future odds.
"""
from pathlib import Path
from collections import defaultdict
import csv,hashlib,json,statistics,math
P=Path(__file__).resolve().parent
SPEC=json.loads((P/"SPECIFICATION_V23.json").read_text())
assert SPEC["predeclared_before_calculation"] is True

def read():
    with (P/"DECISION_TIMING_EVENT_DIAGNOSTICS_V21.csv").open() as f:
        return list(csv.DictReader(f))

def group(rows,k):
    if k=="all":return rows
    if k=="inspected":return [r for r in rows if r["symbol"] in ("SOXX","SMH","QQQ","AMD")]
    if k=="new_semis":return [r for r in rows if r["symbol"] in ("NVDA","MU","INTC","AMAT","LRCX","KLAC")]
    if k=="sector":return [r for r in rows if r["symbol"] in ("XLV","XLE")]
    raise ValueError(k)

def average(xs):
    return round(statistics.mean(xs),5) if xs else None

def evaluate(rows,label,h):
    eligible=[r for r in group(rows,label) if r["mode"]=="force"
              and float(r["checkpoint_h"])==h and r["status"]=="resolved" and r["eligible"]=="True"]
    parent=[r for r in group(rows,label) if r["mode"]=="force" and float(r["checkpoint_h"])==h]
    positives=[float(r["delta_pp"]) for r in eligible if float(r["delta_pp"])>1e-8]
    negatives=[-float(r["delta_pp"]) for r in eligible if float(r["delta_pp"])<-1e-8]
    neutral=[r for r in eligible if abs(float(r["delta_pp"]))<=1e-8]
    good=statistics.mean(positives) if positives else None
    bad=statistics.mean(negatives) if negatives else None
    needed=bad/(bad+good) if good is not None and bad is not None else None
    changed=len(positives)+len(negatives)
    hit_rate=len(positives)/changed if changed else None
    # Report leave-one-entry-week-out variation without treating correlated
    # asset rows as independent confidence units.
    loo=[]
    for week in sorted(set(r["entry_week"] for r in eligible)):
        xs=[r for r in eligible if r["entry_week"]!=week]
        pos=[float(r["delta_pp"]) for r in xs if float(r["delta_pp"])>1e-8]
        neg=[-float(r["delta_pp"]) for r in xs if float(r["delta_pp"])<-1e-8]
        if not pos or not neg:continue
        p=statistics.mean(pos);c=statistics.mean(neg)
        loo.append(c/(p+c))
    # Nontrader price-below-entry signal, matched to force decision for exact
    # same entry. No signal means no action, not a false positive.
    naive=[r for r in group(rows,label) if r["mode"]=="below_entry" and float(r["checkpoint_h"])==h
             and r["status"]=="resolved" and r["eligible"]=="True" and r["signal"]=="True"]
    goodna=[float(r["delta_pp"]) for r in naive if float(r["delta_pp"])>1e-8]
    badna=[-float(r["delta_pp"]) for r in naive if float(r["delta_pp"])<-1e-8]
    zero=sum(abs(float(r["delta_pp"]))<=1e-8 for r in naive)
    return dict(group=label,checkpoint_h=h,original_opportunities=len(parent),
        eligible_to_act=len(eligible),closed_before_checkpoint=len(parent)-len(eligible),
        economic_beneficial_if_force=len(positives),economic_harmful_if_force=len(negatives),
        economically_neutral=len(neutral),
        saving_mean_pp=average(positives),
        harm_mean_pp=average(negatives),
        false_exit_cost_ratio=round(bad/good,3) if good and bad else None,
        required_precise_exit_share=round(needed,5) if needed is not None else None,
        actual_share_beneficial_among_changing=round(hit_rate,5) if hit_rate is not None else None,
        needed_share_leave_week_out_min=round(min(loo),5) if loo else None,
        needed_share_leave_week_out_max=round(max(loo),5) if loo else None,
        loss_avoided_sum_pp=round(sum(positives),4),return_surrendered_sum_pp=round(sum(negatives),4),
        worst_false_exit_harm_pp=round(max(negatives),4) if negatives else None,
        most_costly_false_exit_fraction=round(max(negatives)/sum(negatives),5) if negatives else None,
        naive_close_below_entry_triggers=len(naive),
        naive_economic_correct=len(goodna),
        naive_economic_harmful=len(badna),
        naive_economic_neutral=zero,
        naive_fraction_correct_of_changed=round(len(goodna)/(len(goodna)+len(badna)),5) if goodna or badna else None,
        naive_sum_saved_pp=round(sum(goodna),4),
        naive_sum_surrendered_pp=round(sum(badna),4),
        no_forward_predictive_claim=True)

def main():
    data=read()
    assert len(data)==91*6*3
    results=[evaluate(data,group,h) for group in SPEC["cohort_groups"] for h in SPEC["checkpoints_RTH_hours"]]
    for r in results:
        assert r["original_opportunities"] in (91,34,47,10)
        assert r["eligible_to_act"]+r["closed_before_checkpoint"]==r["original_opportunities"]
        if r["required_precise_exit_share"] is not None:
            assert 0<r["required_precise_exit_share"]<1
    out=P/"ECONOMIC_ASYMMETRY_RESULTS_V23.json"
    assert not out.exists()
    summary=dict(schema=SPEC["schema"],source_prior_v21_sha256=hashlib.sha256((P/"RESULTS_V21.json").read_bytes()).hexdigest(),
        actual_model_not_trained=True,rows=results,
        limitations=["The break-even precision uses the hindsight benefit/harm magnitude mix at each time; it is not a forecast precision requirement transferable across regimes.",
         "A perfect oracle can achieve these payoffs only by seeing the future.",
         "Historical input source PIT and venue quote marketability not admitted.","Same repeated retrospective market year and correlated companies."])
    out.write_text(json.dumps(summary,indent=2))
    cols=list(results[0])
    with (P/"ECONOMIC_ASYMMETRY_V23.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,cols);w.writeheader();w.writerows(results)
    for h in SPEC["checkpoints_RTH_hours"]:
        z=next(r for r in results if r["group"]=="all" and r["checkpoint_h"]==h)
        print("PRECISION_BOUND",h,
            "eligible",z["eligible_to_act"],
            "beneficial",z["economic_beneficial_if_force"],
            "harmful",z["economic_harmful_if_force"],
            "avg_save",z["saving_mean_pp"],"avg_harm",z["harm_mean_pp"],
            "required_precision",z["required_precise_exit_share"],
            "naive_precision",z["naive_fraction_correct_of_changed"],
            "naive_actions",z["naive_close_below_entry_triggers"],flush=True)
    print("RESULTS_SHA",hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=="__main__":main()