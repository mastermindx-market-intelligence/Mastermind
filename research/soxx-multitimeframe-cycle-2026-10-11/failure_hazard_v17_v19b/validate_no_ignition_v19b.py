"""Independent v19+KLAC source/result arithmetic, no market row publication."""
from pathlib import Path
import csv,collections,json,hashlib,statistics,math
import no_ignition_eval_v19 as model
ROOT=Path(__file__).resolve().parent

def source():
    m=json.loads((ROOT/"M1_SOURCE_MANIFEST_V19.json").read_text())
    assert len(m)==9
    for x in m:
        filename=f"{x['sym']}_Terminal_{x['tf']}_ext0.json"
        local=ROOT/filename
        assert local.exists() and hashlib.sha256(local.read_bytes()).hexdigest()==x["raw_sha256"]
        print("SOURCE_SHA_MATCH",filename,x["raw_sha256"][:12])
    v14=json.loads((ROOT/"VALIDATION_V14.json").read_text())
    assert v14["independent_OHLC_replays"]==84 and v14["largest_return_difference"]==0
    v18=json.loads((ROOT/"FIVE_MINUTE_AUDIT_V18.json").read_text())
    assert len(v18["source_state"])==4
    for key,value in v18["source_state"].items():
        assert value["price_OHLC_matched_exactly"] and value["bars15m_not_covered_by_5m"]>=0
    return dict(M1_SHA_verified=len(m),v14_independent_replay=84,v18_source_audited=4)

def parse_rows(path):
    raw=list(csv.DictReader(path.open()))
    fixed=[]
    for x in raw:
        y=dict(x)
        for field in ("base_net_pct","intervention_net_pct","delta_pctpoints","buyer_loss_avoided_pct","winner_sacrificed_pct"):
            y[field]=float(x[field])
        for field in ("check_eligible","prior_stop_before_check","check_no_ignition_exit",
                      "helped_original_loser","harmed_existing_winner","created_winner","destroyed_winner"):
            assert x[field] in ("True","False")
            y[field]=x[field]=="True"
        assert abs(y["base_net_pct"]+y["delta_pctpoints"]-y["intervention_net_pct"])<.00004
        assert (not y["check_no_ignition_exit"] or y["check_eligible"])
        assert (y["check_eligible"] or y["prior_stop_before_check"])
        assert not (y["check_eligible"] and y["prior_stop_before_check"])
        if not y["check_no_ignition_exit"]:assert abs(y["delta_pctpoints"])<1e-6
        fixed.append(y)
    return fixed

def run():
    output=ROOT/"NO_IGNITION_COHORT_ALL_V19B.json"
    assert not output.exists()
    qc=source()
    a=parse_rows(ROOT/"NO_IGNITION_PAIR_DATA_V19.csv")
    b=parse_rows(ROOT/"KLAC_GAP_CENSORED_PAIR_DATA_V19B.csv")
    assert len(a)==81 and len(b)==10
    own=json.loads((ROOT/"NO_IGNITION_RESULTS_V19.json").read_text())
    kl=json.loads((ROOT/"KLAC_GAP_CENSORED_RESULTS_V19B.json").read_text())
    assert own["all_resolved"]==81 and kl["resolved"]==10 and kl["unknown"]==0
    oldgroups=own["group_summary"]
    old_new=next(x for x in oldgroups if x["label"]=="unseen_names")
    assert old_new["resolved"]==37
    extra=model.grouped_metrics(a+b,model.NEW|{"KLAC"},"six_additional_semiconductor_stocks")
    combined=model.grouped_metrics(a+b,model.DESIGN|model.NEW|model.CTRL|{"KLAC"},"all_exploratory_assets_including_original")
    ctr=model.grouped_metrics(a+b,model.CTRL,"sector_controls_recomputed")
    assert ctr["resolved"]==10
    assert extra["resolved"]==47 and combined["resolved"]==91
    assert extra["earlier_winners_harmed"]==1 and extra["earlier_losses_helped"]==7
    assert abs(extra["mean_difference"]-round(sum(x["delta_pctpoints"] for x in a+b if x["symbol"] in model.NEW|{"KLAC"})/47,5))<=1e-5
    loo={}
    for sym in sorted({x["symbol"] for x in a+b if x["symbol"] in model.NEW|{"KLAC"}}):
        x=[r["delta_pctpoints"] for r in a+b if r["symbol"] in model.NEW|{"KLAC"} and r["symbol"]!=sym]
        loo[sym]=dict(n=len(x),mean_lift=round(statistics.mean(x),4))
    src=dict(checks=qc,gap_controls=dict(KLAC_missing_5m_expected_slots=kl["source_quality"]["missing_source5_slots"],
                KLAC_episode_count=kl["total_original_arms"],KLAC_censored=kl["unknown"]),
             original_v19_sha256=hashlib.sha256((ROOT/"NO_IGNITION_RESULTS_V19.json").read_bytes()).hexdigest(),
             KLAC_addendum_sha256=hashlib.sha256((ROOT/"KLAC_GAP_CENSORED_RESULTS_V19B.json").read_bytes()).hexdigest())
    report=dict(schema="soxx.failure_to_ignite.cumulative_read_only_v19b",source=src,
                extra_six_semis=extra,combined=combined,controls=ctr,
                leave_one_added_semiconductor_out=loo,
                caveats=["AVGO unavailable: no qualified 15m warmup; NOT scored as zero or success",
                         "KLAC 7 missing observed 5m input bars: none of 10 v19b candidate exposure paths crosses one; other source gaps must be independently checked",
                         "historical 15m/5m stored/live basis and adjustments not point-in-time qualified",
                         "all names correlate during one previously inspected market year; so called independent names are NOT independent event-time holdouts",
                         "sample return means and bootstrap uncertainty do not constitute personalized trade sizing"])
    output.write_text(json.dumps(report,indent=2))
    print("VALIDATED",json.dumps({k:report[k] for k in ("extra_six_semis","combined","leave_one_added_semiconductor_out")}))
    print("SHA",hashlib.sha256(output.read_bytes()).hexdigest())
if __name__=="__main__":run()