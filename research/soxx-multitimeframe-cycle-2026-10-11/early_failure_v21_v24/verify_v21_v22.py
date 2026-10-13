#!/usr/bin/env python3
"""Independent accounting and causal-time checks for v21/v22 research artifacts."""
from pathlib import Path
import collections,csv,hashlib,json,math,statistics,sys
ROOT=Path(__file__).resolve().parent

def read(name):
    with (ROOT/name).open() as f:return list(csv.DictReader(f))

def audit():
    v21=json.loads((ROOT/"RESULTS_V21.json").read_text())
    v22=json.loads((ROOT/"RESULTS_V22.json").read_text())
    spec21=json.loads((ROOT/"SPECIFICATION_V21.json").read_text())
    spec22=json.loads((ROOT/"SPECIFICATION_V22.json").read_text())
    assert spec21["predeclared_before_stage_evaluation"] and spec22["predeclared_before_model_fitting"]
    assert spec21["no_auth_vendor_calls"] and spec22["NO_NEW_VENDOR_CALLS"]
    assert v21["v20_oracle_3h_reproduced"]
    event=read("DECISION_TIMING_EVENT_DIAGNOSTICS_V21.csv")
    pred=read("WALK_FORWARD_DECISIONS_V22.csv")
    assert len(event)==91*6*3 and len(pred)==91*2
    by_key={}
    for row in event:
        key=(row["symbol"],row["episode"],float(row["checkpoint_h"]),row["mode"])
        assert key not in by_key
        by_key[key]=row
        if row["status"]=="resolved":
            d=float(row["delta_pp"])
            if row["mode"]=="force":
                assert row["eligible"]=="True" or abs(d)<1e-8
                assert abs(float(row["oracle_gain_pp"])-max(0,d))<1e-8
            else:
                raw=by_key.get((row["symbol"],row["episode"],float(row["checkpoint_h"]),"force"))
                # depends on event loop order; record subsequent check below
    compared=0
    for row in event:
        if row["status"]!="resolved" or row["mode"]=="force":continue
        key=(row["symbol"],row["episode"],float(row["checkpoint_h"]),"force")
        forced=by_key[key]
        expected=float(forced["delta_pp"]) if row["signal"]=="True" else 0.
        assert abs(float(row["delta_pp"])-expected)<.000002,(row["symbol"],row["episode"],row["checkpoint_h"],row["mode"])
        if row["mode"]=="below_entry" and row["eligible"]=="True":
            assert (row["signal"]=="True")==(float(row["check_close_pct"])<0)
        if row["mode"]=="half_peak" and row["eligible"]=="True":
            assert (row["signal"]=="True")==(
                float(row["peak_gain_pct"])>0 and float(row["check_close_pct"])<.5*float(row["peak_gain_pct"]))
        compared+=1
    scored=0;skips=0;act=0
    for row in pred:
        key=(row["symbol"],row["episode"],float(row["checkpoint_h"]),"force")
        prior=by_key[key]
        active=row["forecastable"]=="True"
        sold=row["model_decision_exit"]=="True"
        if not active:
            assert not sold and abs(float(row["realized_economic_lift_pp"]))<1e-9
            skips+=1
        else:
            assert row["status"]=="eligible" and prior["status"]=="resolved" and prior["eligible"]=="True"
            assert sold==(float(row["model_predicted_advantage_pp"])>.25)
            expected=float(prior["delta_pp"]) if sold else 0.
            assert abs(float(row["realized_economic_lift_pp"])-expected)<.000002
            naive_expected=float(prior["delta_pp"]) if float(prior["check_close_pct"])<0 else 0.
            assert abs(float(row["naive_below_entry_lift_pp"])-naive_expected)<.000002
            assert int(row["prior_training_weeks"])>=6
            scored+=1
            act+=sold
    # Aggregates are derived from these exact per-episode ledgers.
    a21=read("DECISION_TIMING_AGGREGATES_V21.csv")
    for row in a21:
        if row["group"]!="all":continue
        subt=[r for r in event if r["mode"]==row["mode"] and r["checkpoint_h"]==row["checkpoint_h"]]
        assert len(subt)==91
        assert sum(r["eligible"]=="True" for r in subt)==int(row["eligible"])
        observed=[float(r["delta_pp"]) for r in subt if r["status"]=="resolved"]
        assert abs(statistics.mean(observed)-float(row["mean_incremental_return_pp"]))<.000002
    a22=read("WALK_FORWARD_AGGREGATES_V22.csv")
    for row in a22:
        if row["group"]!="all":continue
        subset=[r for r in pred if r["checkpoint_h"]==row["checkpoint_h"] and r["forecastable"]=="True"]
        assert len(subset)==int(row["forecastable_eligible"])
        assert sum(r["model_decision_exit"]=="True" for r in subset)==int(row["trades_exited_by_model"])
        assert abs(statistics.mean(float(r["realized_economic_lift_pp"]) for r in subset)-
                   float(row["model_economic_lift_on_test_episodes_pp"]))<.000002
    proof=dict(schema="soxx.v21_v22.honest_derived_ledger_verification.v1",
         v21_records=len(event),v21_rule_accounting_verifications=compared,
         v22_episode_stage_records=len(pred),walkforward_eligible_later_cases=scored,
         walkforward_action_count=act,walkforward_no_prior_training_cases=skips,
         source_SHA_v21=hashlib.sha256((ROOT/"RESULTS_V21.json").read_bytes()).hexdigest(),
         source_SHA_v22=hashlib.sha256((ROOT/"RESULTS_V22.json").read_bytes()).hexdigest(),
         true_tick_historical_fill_proven=False,unseen_market_history_proven=False,
         model_decision_not_accepted_for_trading=True)
    path=ROOT/"VALIDATION_V21_V22.json"
    assert not path.exists()
    path.write_text(json.dumps(proof,indent=2))
    print("VALIDATED",json.dumps(proof),flush=True)
if __name__=="__main__":audit()