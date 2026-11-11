"""Independent v16 chronology & accounting proof, including alternative intrabar route.
This is *software verification*, not a predictive backtest acceptance.
"""
from pathlib import Path
import csv,json,hashlib,collections,statistics,datetime as dt
import parent_delay_controls_v16 as p
import study_v14 as s
import peer_v14 as pe
from intrabar_audit import replay
ROOT=Path(__file__).resolve().parent
def csvread(f):return list(csv.DictReader((ROOT/f).open()))
def run():
    spec=json.loads((ROOT/"PARENT_ONLY_AND_DELAY_CONTROLS_SPEC_V16.json").read_text())
    assert spec["pre_specified_before_outcomes"] and spec["NO_PIT"]
    summary=csvread("parent_delay_summary_v16.csv")
    # code flag NO_PIT represents never claiming PIT, not a failure.
    ledger=json.loads((ROOT/"parent_delay_private_ledger_v16.json").read_text())
    pairs=csvread("parent_delay_same_arms_v16.csv")
    assert len(summary)==4*7
    output=dict(schema="soxx.parent_v16.verified.replay",algorithm="frozen",
        original_parent_arms=34,source_instruments=4,sidecar_snapshot_SHA256={},
        accounted_event_pairs=0,source_bar_prefixes=0,
        baseline_independent_route_replays=0,opposite_intrabar_returns_differ=0,
        warnings=["OHLC is not historical executable quotes","Market-data source adjustment/PIT unverified"])
    for sym in ("SOXX","SMH","QQQ","AMD"):
        ctx,q=s.raw_context() if sym=="SOXX" else pe.peer_context(sym)
        x=p.parents(ctx);parent={c["episode"]:c for c in x}
        arms=p.all_arms(ctx)
        assert len(parent)==len(arms)
        assert set(parent)==set(arms)
        hb=ctx["high"][180];hf=ctx["hf"]["3h_medium"];ends=[b["end"] for b in hb]
        for c in x:
            hi=s.n.asof(ends,c["signal_time"])
            assert hb[hi]["end"]==c["signal_time"]
            assert s.n.higher_state(hf,hi,1,"turn")
            assert ctx["raw"][c["entry"]]["start"]>=c["signal_time"]
            assert c["higher_time"]==c["signal_time"]
            before=[j for j in range(hi) if hb[j]["end"]>=c["arm_time"] and
                hb[j]["complete"] and s.n.higher_state(hf,j,1,"turn")]
            assert before==[],(sym,c["entry_ET"],before)
            assert 0<=ctx["clock"][c["entry"]]-p.arm_clock_of(c,ctx)<=26*3600
        rows=[z for z in ledger if z["symbol"]==sym]
        assert len(rows)==len(arms)*7
        for name in ["parent_only","turn_pivot_15","turn_pivot_30","parent_delay_1","parent_delay_2","parent_delay_4","parent_delay_8"]:
            zs=[z for z in rows if z["policy"]==name]
            rep=next(r for r in summary if r["symbol"]==sym and r["policy"]==name)
            assert len(zs)==int(rep["parent_arm_opportunities"])
            active=[v["return_pct"] for v in zs if v["status"]=="resolved"]
            assert len(active)==int(rep["resolved"])
            assert len(zs)-len(active)==int(rep["no_trigger"])+int(rep["unknown"])
            assert sum(t>0 for t in active)==int(rep["winners"])
            if active:assert abs(statistics.mean(active)-float(rep["mean_conditional"]))<.0001
            if int(rep["unknown"])==0:
                assert abs(statistics.mean(active+[0]*int(rep["no_trigger"]))-float(rep["mean_per_arm_cash_nonfills"]))<.0001
        # Independent alternate OHLC replay of the parent-only row with the
        # exact 52-RTH-hour TimedDecision, no benefit of future candle extreme.
        ctx["_panels"]=s.make_panels(ctx)
        for c in x:
            v=next(z for z in rows if z["arm"]==c["episode"] and z["policy"]=="parent_only")
            t,_=s.run_exit(ctx,c,"time52",15)
            assert t and abs(t["net_pct"]-v["return_pct"])<1e-10
            qdec,_=s.cy.make_policy(ctx,c,"time",clock=52,buffer=.1)
            alt=replay(ctx["raw"],c["entry"],c["stop"],decision=qdec,partial=.25,
                fee=5,horizon=100000,order="OHLC")
            assert alt and alt["exit_idx"]==t["exit_idx"]
            if abs(alt["net_pct"]-t["net_pct"])>1e-8:output["opposite_intrabar_returns_differ"]+=1
            output["baseline_independent_route_replays"]+=1
        output["source_bar_prefixes"]+=len(ctx["raw"])
        for tf in ("15m","30m"):
            source=ROOT/(sym+"_Terminal_"+tf+"_ext0.json")
            output["sidecar_snapshot_SHA256"][sym+"_"+tf]=hashlib.sha256(source.read_bytes()).hexdigest()
    for r in pairs:
        old=float(r["parent_return_pct"]);z=float(r["conditional_return_pct"]);delta=float(r["paired_return_change_pctpoints"])
        assert abs((z-old)-delta)<.00015
        assert float(r["entry_delay_RTH_hours"])>=0
    output["accounted_event_pairs"]=len(pairs)
    assert output["baseline_independent_route_replays"]==34
    assert output["accounted_event_pairs"]>=40
    result=ROOT/"PARENT_V16_VERIFICATION.json"
    assert not result.exists(),"Research proof must be read back before overwrite"
    result.write_text(json.dumps(output,indent=2))
    print("VERIFY_PARENT",json.dumps({k:v for k,v in output.items() if k!="sidecar_snapshot_SHA256"}))
    print("SHA",hashlib.sha256(result.read_bytes()).hexdigest())
if __name__=="__main__":run()