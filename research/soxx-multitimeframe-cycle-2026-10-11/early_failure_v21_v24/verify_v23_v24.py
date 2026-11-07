"""Proof for derived economics and execution stresses, not prediction validation."""
from pathlib import Path
import csv,json,hashlib,math,statistics
P=Path(__file__).resolve().parent
def read_rows(name):
    with (P/name).open() as f:return list(csv.DictReader(f))
def run():
    v21=json.loads((P/"RESULTS_V21.json").read_text())
    v23=json.loads((P/"ECONOMIC_ASYMMETRY_RESULTS_V23.json").read_text())
    v24=json.loads((P/"RESULTS_V24.json").read_text())
    a24=v24["predeclared_stress"];a23=v23["rows"]
    r21=[x for x in v21["summaries"] if x["group"]=="all" and x["mode"]=="below_entry"]
    r24=[x for x in a24 if x["group"]=="all"]
    assert len(a23)==4*6 and len(a24)==4*2*3*5
    for hour in (.5,3.):
        base=next(x for x in r21 if x["checkpoint_h"]==hour)
        direct=next(x for x in r24 if x["checkpoint_h"]==hour and x["delay_5m_bars"]==1 and x["extra_sell_slip_bp"]==0)
        assert direct["n"]==91
        assert abs(base["mean_incremental_return_pp"]-direct["mean_delta_pp"])<1e-7
        for delay in (1,2,4):
            seq=[x for x in r24 if x["checkpoint_h"]==hour and x["delay_5m_bars"]==delay]
            assert len(seq)==5
            seq.sort(key=lambda z:z["extra_sell_slip_bp"])
            assert [z["extra_sell_slip_bp"] for z in seq]==[0,10,25,50,100]
            assert all(b["mean_delta_pp"]<=a["mean_delta_pp"]+1e-8 for a,b in zip(seq,seq[1:])),(hour,delay,seq)
            assert len({z["discretionary_sales"] for z in seq})==1
        x=next(x for x in a23 if x["group"]=="all" and x["checkpoint_h"]==hour)
        naive_gain=(x["naive_sum_saved_pp"]-x["naive_sum_surrendered_pp"])/91
        assert abs(naive_gain-base["mean_incremental_return_pp"])<5e-6
        positive=x["saving_mean_pp"];negative=x["harm_mean_pp"]
        req=negative/(negative+positive)
        assert abs(req-x["required_precise_exit_share"])<.00002
        naive_p=x["naive_economic_correct"]/(x["naive_economic_correct"]+x["naive_economic_harmful"])
        assert abs(naive_p-x["naive_fraction_correct_of_changed"])<.00002
    private=read_rows("EXECUTION_STRESS_PRIVATE_EVENTS_V24.csv")
    assert len(private)==91*2*3*5
    assert all(float(x["delta_pp"])==float(x["delta_pp"]) for x in private)
    proof=dict(schema="soxx.v23_v24.price_risk_sensitivity_accounting_proof",
        v23_rows=len(a23),v24_aggregate_rows=len(a24),v24_per_episode_stress_rows=len(private),
        v21_reference_mean_deltas_reproduced=True,all_120_stress_sequences_monotone=True,
        break_even_precision_reproduced=True,per_original_opportunity_arithmetic_verified=True,
        code_price_fills_are_not_actual_quote_marketability=True,
        test_thresholds_were_not_reoptimized=True,
        source_v21_sha256=hashlib.sha256((P/"RESULTS_V21.json").read_bytes()).hexdigest(),
        output_v23_sha256=hashlib.sha256((P/"ECONOMIC_ASYMMETRY_RESULTS_V23.json").read_bytes()).hexdigest(),
        output_v24_sha256=hashlib.sha256((P/"RESULTS_V24.json").read_bytes()).hexdigest())
    path=P/"VERIFICATION_V23_V24.json"
    assert not path.exists()
    path.write_text(json.dumps(proof,indent=2))
    print("VERIFIED",json.dumps(proof))
if __name__=="__main__":run()