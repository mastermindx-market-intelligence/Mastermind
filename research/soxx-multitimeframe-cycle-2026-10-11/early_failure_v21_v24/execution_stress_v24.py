#!/usr/bin/env python3
"""v24 exact same frozen below-entry exit with additional execution delays and
theoretical quote-slip stresses. Requires no API or future signal value.
"""
from pathlib import Path
import csv,collections,datetime as dt,hashlib,json,random,statistics,sys,math
ROOT=Path(__file__).resolve().parent
PARENT=Path("/private/tmp/soxx_terminal_finepivot_20261011_v14")
sys.path.insert(0,str(PARENT))
import no_ignition_eval_v19 as v
import klac_gap_censored_v19b as klac
import parent_delay_controls_v16 as parent
from no_ignition_v19 import TimerOnly
from engine_v6 import simulate
from decision_timing_v21 import CheckAndAct

SPEC=json.loads((ROOT/"SPECIFICATION_V24.json").read_text())
assert SPEC["predeclared_before_outcome_test"] and SPEC["no_vendor_calls"]
READER=ROOT/"DECISION_TIMING_EVENT_DIAGNOSTICS_V21.csv"

def mean(xs):return round(statistics.mean(xs),6) if xs else None
def group(symbol):
    if symbol in ("SOXX","SMH","QQQ","AMD"):return "inspected"
    if symbol in ("NVDA","MU","INTC","AMAT","LRCX","KLAC"):return "new_semis"
    return "sector"

def week(t):
    d=dt.datetime.fromisoformat(t).date()
    return (d-dt.timedelta(days=d.weekday())).isoformat()

def run():
    with READER.open() as f:orig=list(csv.DictReader(f))
    refs={(r["symbol"],r["episode"],float(r["checkpoint_h"])):r for r in orig if r["mode"]=="below_entry"}
    observed=[];source=[]
    for symbol in SPEC["cohort"]:
        if symbol=="KLAC":
            c,env,missing,qual=klac.source()
        else:
            c,q15=v.ctx15(symbol);env,q5=v.ctx5(symbol,c);missing=[];qual={**q15,**q5}
        arms=parent.parents(c)
        source.append(dict(symbol=symbol,count=len(arms),source5_sha256=qual.get("source5_sha256"),source_unknown=0))
        for arm in arms:
            init=env["_startmap"].get(c["raw"][arm["entry"]]["start"])
            if isinstance(init,dict):init=init["idx"]
            assert isinstance(init,int)
            px=env["raw"][init]["open"]
            assert math.isclose(px,c["raw"][arm["entry"]]["open"],rel_tol=1e-7,abs_tol=1e-3)
            stop=px*.985
            baseline=v.do_policy(env["raw"],init,stop,TimerOnly())
            assert baseline is not None
            for hour in SPEC["checkpoints"]:
                reference=refs[symbol,arm["episode"],hour]
                for delay in SPEC["signal_to_market_order_open_delay_in_five_minute_bars"]:
                    checker=CheckAndAct(hour,"below_entry")
                    trades=simulate(env["raw"],init,stop,
                        horizon=100000,partials=[(2,.25)],decision=checker,
                        cost_bps=5,ambiguity="stop_first",delay=delay)
                    if trades is None:
                        source[-1]["source_unknown"]+=1;continue
                    last=max(baseline["exit_time"],trades["exit_time"])
                    if any(c["raw"][arm["entry"]]["start"]<=missing_time<last for missing_time in missing):
                        source[-1]["source_unknown"]+=1;continue
                    if delay==1:
                        assert abs(trades["net_pct"]-float(reference["intervention_net_pct"]))<.000002
                        assert (checker.checked)==(reference["eligible"]=="True")
                    why="v21_below_entry_at_"+str(hour)
                    triggers=[f for f in trades["fills"] if f["reason"]==why]
                    assert len(triggers)<=1
                    q=triggers[0]["q"] if triggers else 0.
                    sale_price=triggers[0]["price"] if triggers else None
                    if checker.signal and q==0 and trades["reason"]!=why:
                        # A hard stop at a new opening may supersede the pending exit.
                        pass
                    observed.append(dict(symbol=symbol,group=group(symbol),entry_week=week(arm["entry_ET"]),
                        episode=arm["episode"],checkpoint_h=hour,extra_signal_delay_5m_bars=delay,
                        tested_net_pct=trades["net_pct"],baseline_net_pct=baseline["net_pct"],
                        delta_no_extra_slippage=trades["net_pct"]-baseline["net_pct"],
                        status="resolved",eligible_at_check=checker.checked,
                        check_flagged=checker.signal,actual_discretionary_share_fraction=q,
                        discretionary_fill_ratio=sale_price/px if sale_price else 0.,
                        original_winner=baseline["net_pct"]>0,
                        original_loser=baseline["net_pct"]<=0))
        print("REPLAYED",symbol,len(arms),'source_unknown',source[-1]["source_unknown"],flush=True)
    # A pessimistic slip penalty includes only the remaining fraction sold at
    # the discretionary opening. Initial stop and partial order are untouched.
    summary=[];data=[]
    for row in observed:
        for extra in SPEC["additional_adverse_market_sell_slippage_bps"]:
            amt=row["actual_discretionary_share_fraction"]*row["discretionary_fill_ratio"]*extra/100
            change=row["delta_no_extra_slippage"]-amt
            data.append(dict(symbol=row["symbol"],group=row["group"],week=row["entry_week"],
                checkpoint_h=row["checkpoint_h"],extra_signal_delay_5m_bars=row["extra_signal_delay_5m_bars"],
                adverse_discretionary_slippage_bps=extra,
                delta_pp=round(change,6),discretionary_shares=row["actual_discretionary_share_fraction"],
                original_winner=row["original_winner"],original_loser=row["original_loser"]))
    for stage in SPEC["checkpoints"]:
        for delay in SPEC["signal_to_market_order_open_delay_in_five_minute_bars"]:
            for slip in SPEC["additional_adverse_market_sell_slippage_bps"]:
                for g in ("all","inspected","new_semis","sector"):
                    a=[x for x in data if x["checkpoint_h"]==stage and x["extra_signal_delay_5m_bars"]==delay
                       and x["adverse_discretionary_slippage_bps"]==slip and (g=="all" or x["group"]==g)]
                    if not a:continue
                    vals=[x["delta_pp"] for x in a]
                    summary.append(dict(group=g,checkpoint_h=stage,delay_5m_bars=delay,
                        extra_sell_slip_bp=slip,n=len(a),
                        discretionary_sales=sum(x["discretionary_shares"]>0 for x in a),
                        mean_delta_pp=mean(vals),
                        saved_original_losers=sum(x["delta_pp"]>0 and x["original_loser"] for x in a),
                        harmed_original_winners=sum(x["delta_pp"]<0 and x["original_winner"] for x in a),
                        biggest_positive_delta=max(vals),biggest_negative_delta=min(vals)))
    def csv_save(name,rows):
        fields=list(dict.fromkeys(k for row in rows for k in row))
        with (ROOT/name).open("w",newline="") as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    csv_save("EXECUTION_STRESS_V24.csv",summary)
    # Large outcome ledger stays private, not GitHub.
    csv_save("EXECUTION_STRESS_PRIVATE_EVENTS_V24.csv",data)
    result=dict(schema=SPEC["schema"],spec_sha256=hashlib.sha256((ROOT/"SPECIFICATION_V24.json").read_bytes()).hexdigest(),
        input_source_inventory=source,
        copied_5m_data_outside_archival_owner=False,
        raw_quote_price_fills_proven=False,branch_production_change=False,
        predeclared_stress=summary,
        NO_AUTHENTIC_BOATS_HISTORY=True)
    f=ROOT/"RESULTS_V24.json";assert not f.exists()
    f.write_text(json.dumps(result,indent=2))
    for stage in SPEC["checkpoints"]:
        print("STRESS_STAGE",stage,[(r["delay_5m_bars"],r["extra_sell_slip_bp"],r["mean_delta_pp"],r["discretionary_sales"])
             for r in summary if r["group"]=="all" and r["checkpoint_h"]==stage],flush=True)
    print("DIGEST",hashlib.sha256(f.read_bytes()).hexdigest())
if __name__=="__main__":run()