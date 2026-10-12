#!/usr/bin/env python3
"""Economically valid *hindsight upper bound* for 3-hour early exit decision.

All 5m source OHLC is private. No model fit, thresholds searched, trade sizing
or live trading. Exits at next source open, emergency stop continues to dominate.
"""
from pathlib import Path
import collections,csv,datetime as dt,hashlib,json,math,random,statistics
import no_ignition_eval_v19 as v
import klac_gap_censored_v19b as klac
from no_ignition_v19 import TimerOnly,NoIgnitionOnce
ROOT=Path(__file__).resolve().parent
SPEC=json.loads((ROOT/"ORACLE_VALUE_SPEC_V20.json").read_text())
assert SPEC["predeclared_before_evaluation"]

class ForceAtThreeHours(TimerOnly):
    def __init__(self):
        super().__init__(52.)
        self.checked=False
        self.close_pct=None
        self.status=None
        self.triage_bar_close_utc=None
        self.triage_age=None
    def __call__(self,st,bar):
        r=super().__call__(st,bar)
        if not self.checked and st["age_hours"]>=3.:
            self.checked=True
            self.close_pct=100*(bar["close"]/st["px"]-1.)
            self.status="below_entry" if bar["close"]<st["px"] else "at_or_above_entry"
            self.triage_bar_close_utc=bar["end"]
            self.triage_age=st["age_hours"]
            if not r:
                return dict(sell=st["remaining"],reason="oracle_probe_3h_next_open")
        return r

def average(xs):return round(statistics.mean(xs),6) if xs else None
def med(xs):return round(statistics.median(xs),6) if xs else None
def wkey(entry):
    d=dt.datetime.fromisoformat(entry).date()
    return (d-dt.timedelta(days=d.weekday())).isoformat()
def auc(scores,labels):
    # pairwise equivalent to Mann-Whitney U; score HIGH means exit-at-3h is better.
    ones=[x for x,z in zip(scores,labels) if z]
    zeros=[x for x,z in zip(scores,labels) if not z]
    if not ones or not zeros:return None
    pairs=[1 if x>y else .5 if x==y else 0 for x in ones for y in zeros]
    return round(sum(pairs)/len(pairs),5)

def group(name,rows,check_coverage=True):
    z=list(rows);eligible=[r for r in z if r["eligible"]]
    gagn=[r["oracle_gain_pp"] for r in z]
    forced=[r["force_delta_pp"] for r in z]
    useful=[r for r in eligible if r["oracle_gain_pp"]>1e-8]
    harmful=[r for r in eligible if r["force_delta_pp"]< -1e-8]
    below=[r for r in eligible if r["check_below_entry"]]
    above=[r for r in eligible if not r["check_below_entry"]]
    # false positive: below-entry check would cut a trade whose continuation is better
    falseexit=sum(r["force_delta_pp"]< -1e-8 for r in below)
    trueexit=sum(r["force_delta_pp"]>1e-8 for r in below)
    falsehold=sum(r["force_delta_pp"]>1e-8 for r in above)
    truehold=sum(r["force_delta_pp"]< -1e-8 for r in above)
    return dict(group=name,n=len(z),eligible=len(eligible),
      stopped_or_closed_before_three_hour_checkpoint=len(z)-len(eligible),
      oracle_gain_pp_per_original_opportunity=average(gagn),
      oracle_gain_pp_per_eligible_trade=average([r["oracle_gain_pp"] for r in eligible]),
      unconditional_three_hour_exit_lift_per_opportunity=average(forced),
      maximal_theoretical_gain_sum_pp=round(sum(gagn),4),
      oracle_beneficial_decisions=len(useful),oracle_harmful_if_forced=len(harmful),
      number_with_three_hour_close_below_entry=len(below),
      number_with_three_hour_close_at_or_above_entry=len(above),
      below_entry_beneficial_to_exit=trueexit,below_entry_would_harm_to_exit=falseexit,
      above_entry_beneficial_to_exit=falsehold,above_entry_would_harm_to_exit=truehold,
      rank_auc_for_negative_three_hour_return=auc([-r["close_at_check_pct"] for r in eligible],
           [r["force_delta_pp"]>1e-8 for r in eligible]),
      median_close_gain_when_oracle_exit_better=med([r["close_at_check_pct"] for r in useful]),
      median_close_gain_when_hold_better=med([r["close_at_check_pct"] for r in harmful]),
      future_gains_sacrificed_by_naive_below_entry=round(sum(-min(0,r["force_delta_pp"]) for r in below),5),
      future_losses_avoided_by_naive_below_entry=round(sum(max(0,r["force_delta_pp"]) for r in below),5),
      zero_delta_due_to_same_gap_fill=sum(r["force_delta_pp"]==0 and r["eligible"] for r in eligible))

def run():
    symbols=SPEC["scope"].split("previously qualified historical parent turn entries ")[-1] if False else [
        "SOXX","SMH","QQQ","AMD","NVDA","MU","INTC","AMAT","LRCX","KLAC","XLV","XLE"]
    records=[];unresolved=[];inventory=[]
    for symbol in symbols:
        if symbol=="KLAC":
            c,e,missing,quality=klac.source()
        else:
            c,quality15=v.ctx15(symbol)
            e,quality5=v.ctx5(symbol,c)
            quality={**quality15,**quality5};missing=[]
        arms=v.parent.parents(c)
        assert len(arms)==len(v.parent.all_arms(c))
        count=0
        for event in arms:
            at=c["raw"][event["entry"]]["start"]
            ref=e["_startmap"].get(at)
            if ref is None:
                unresolved.append(dict(symbol=symbol,episode=event["episode"],why="entry_source_gap"))
                continue
            idx=ref["idx"] if isinstance(ref,dict) else ref
            px=e["raw"][idx]["open"]
            assert math.isclose(px,c["raw"][event["entry"]]["open"],rel_tol=1e-7,abs_tol=1e-3)
            stop=px*.985
            baseline=v.do_policy(e["raw"],idx,stop,TimerOnly())
            checker=ForceAtThreeHours()
            force=v.do_policy(e["raw"],idx,stop,checker)
            if baseline is None or force is None:
                unresolved.append(dict(symbol=symbol,episode=event["episode"],why="right_censored"))
                continue
            last=max(baseline["exit_time"],force["exit_time"])
            if any(at<=stamp<last for stamp in missing):
                unresolved.append(dict(symbol=symbol,episode=event["episode"],why="missing_5min_during_counterfactual"))
                continue
            # independent replay of the separately developed fixed v19 rule,
            # including exact same 5min stop/partial execution.
            no=v.do_policy(e["raw"],idx,stop,NoIgnitionOnce())
            assert no is not None
            if checker.checked and checker.status=="below_entry":
                assert abs(force["net_pct"]-no["net_pct"])<1e-7 and force["exit_idx"]==no["exit_idx"]
            else:
                assert abs(baseline["net_pct"]-no["net_pct"])<1e-7
            delta=force["net_pct"]-baseline["net_pct"]
            if not checker.checked:assert abs(delta)<1e-7
            if checker.checked:assert checker.triage_age>=3 and force["exit_idx"]<=baseline["exit_idx"]
            row=dict(symbol=symbol,episode=event["episode"],week=wkey(event["entry_ET"]),
               entry_ET=event["entry_ET"],eligible=checker.checked,
               close_at_check_pct=round(checker.close_pct,6) if checker.checked else None,
               check_below_entry=checker.checked and checker.status=="below_entry",
               original_return_pct=round(baseline["net_pct"],6),
               force_3h_exit_return_pct=round(force["net_pct"],6),
               force_delta_pp=round(delta,6),
               oracle_gain_pp=round(max(0.,delta),6),
               final_baseline_loss=baseline["net_pct"]<=0,
               final_baseline_win=baseline["net_pct"]>0,
               initial_stop_before_3h=not checker.checked,
               current_exit_reason=force["reason"],
               baseline_reason=baseline["reason"])
            records.append(row);count+=1
        inventory.append(dict(symbol=symbol,arms=len(arms),resolved=count,
           unknown=len(arms)-count,source5_missing_spans=len(missing),
           hash_source5=quality.get("source5_sha256")))
        print("ORACLE_DATA",symbol,'original_arms',len(arms),'resolved',count,
             'decision_eligible',sum(x["eligible"] for x in records if x["symbol"]==symbol),flush=True)
    assert len(records)==91 and not unresolved
    membership={
      'inspected':{"SOXX","SMH","QQQ","AMD"},
      'new_semis':{"NVDA","MU","INTC","AMAT","LRCX","KLAC"},
      'sector_controls':{"XLV","XLE"},
      'all':set(symbols)}
    groups=[group(key,[r for r in records if r["symbol"] in xs]) for key,xs in membership.items()]
    by_asset=[group(x,[r for r in records if r["symbol"]==x]) for x in symbols]
    rng=random.Random(20261011)
    diagnostics=[]
    for item in membership:
        rs=[r for r in records if r["symbol"] in membership[item]]
        by_week=collections.defaultdict(list)
        for r in rs:by_week[r["week"]].append(r)
        blocks=list(by_week.values());boots=[]
        if blocks:
            for i in range(5000):
                sam=[rng.choice(blocks) for x in blocks]
                bs=[r for block in sam for r in block]
                boots.append(sum(v["oracle_gain_pp"] for v in bs)/len(bs))
            boots.sort()
        diagnostics.append(dict(group=item,blocks=len(blocks),
            bootstrap95_oracle_upper_bound_pp=[
                round(boots[int(.025*len(boots))],5),round(boots[int(.975*len(boots))],5)] if boots else None,
            note="Not a confidence interval for a tradeable strategy; perfect hindsight labels."))
    cols=list(records[0])
    with (ROOT/"ORACLE_EVENT_DIAGNOSTICS_V20.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,cols);w.writeheader();w.writerows(records)
    result=dict(schema=SPEC["schema"],spec_sha256=hashlib.sha256((ROOT/"ORACLE_VALUE_SPEC_V20.json").read_bytes()).hexdigest(),
        original_arms=len(records),all_source_covered=True,inventory=inventory,
        groups=groups,asset_groups=by_asset,interval_diagnostics=diagnostics,
        oracle_only_not_tradeable=True,raw_source_data_exported=False,
        result_uncertainty="Previously inspected year/ correlated risk regimes; historical spread and volume book unavailable.",
        baseline="Fixed 52 RTH hours/stop 1.5% plus25% at +2%",
        decision="Forced all-remaining sale at 3h next observed 5m open, except original emergency stop precedence",
        counterfactual_label="Only lookahead benchmark chooses per-entry max(forced-exit,hold); not a feasible predictor.")
    out=ROOT/"ORACLE_UPPER_BOUND_RESULTS_V20.json"
    assert not out.exists()
    out.write_text(json.dumps(result,indent=2))
    print("ORACLE_GROUPS",json.dumps(groups),flush=True)
    print("SHA",hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":run()