#!/usr/bin/env python3
"""Verify existing Terminal 5m vs stored 15m source consistency for precommitted cohort.
No external reads, purchases, vendor creds, source adjustments or synthetic bars.
"""
from pathlib import Path
import collections,datetime as dt,hashlib,json,math
import study_v14 as s
ROOT=Path(__file__).resolve().parent
UTC=dt.timezone.utc
SPEC=json.loads((ROOT/"FIVE_MINUTE_REPLAY_SPEC_V18.json").read_text())
META=json.loads((ROOT/"FIVE_MINUTE_SOURCE_METADATA_V18.json").read_text())

def load5(symbol):
    path=ROOT/(symbol+"_Terminal_5m_ext0.json")
    r=json.loads(path.read_bytes())
    m=META[symbol]
    assert m.get("source_sha256")==hashlib.sha256(path.read_bytes()).hexdigest()
    assert r["source_evidence"]["timestamp_basis"]=="market_local_display_epoch"
    assert r["source_evidence"]["session"]=="regular"
    assert r["source_evidence"]["price_adjustment"]=="not_verified"
    assert r["source_evidence"]["point_in_time_availability"]=="not_verified"
    assert r["source_evidence"]["source_counts"]["unattributed"]==0
    assert r["t"]==symbol and r["tf"]=="5m"
    return r

def audit(sym):
    fine=load5(sym)["bars"]
    coarse=json.loads((ROOT/(sym+"_Terminal_15m_ext0.json")).read_text())["bars"]
    byday=collections.defaultdict(list)
    for x in fine:
        local=dt.datetime.fromtimestamp(x[0],UTC)
        date=local.date().isoformat()
        byday[date].append(x)
    source_hist=collections.Counter();missing_open=[];gaps=[]
    for day,rows in sorted(byday.items()):
        expected=78 if len(rows)>42 else 42
        source_hist[len(rows)]+=1
        if rows[0][0] not in (int(dt.datetime.fromisoformat(day+"T09:30:00+00:00").timestamp()),):
            missing_open.append(day)
        for x,y in zip(rows,rows[1:]):
            if y[0]-x[0]!=300:
                gaps.append((day,x[0],y[0]))
    byf={x[0]:x for x in fine}
    successes=0;notCovered=0;unequal=[];volume_drift=collections.Counter();largest_volume_pct=0.
    for t,o,h,l,c,v in coarse:
        xs=[byf.get(t+i*300) for i in range(3)]
        day=dt.datetime.fromtimestamp(t,UTC).date().isoformat()
        if any(x is None for x in xs):
            notCovered+=1
            continue
        got=(xs[0][1],max(a[2] for a in xs),min(a[3] for a in xs),xs[-1][4],sum(a[5] for a in xs))
        price_identical=all(math.isclose(z,w,rel_tol=1e-7,abs_tol=1e-3) for z,w in zip(got[:4],(o,h,l,c)))
        if not price_identical:
            if len(unequal)<12:unequal.append(t)
            continue
        successes+=1
        vol_pct=100*abs(got[4]-v)/max(1,got[4])
        if not math.isclose(got[4],v,rel_tol=1e-7,abs_tol=1e-3):
            volume_drift[day]+=1
            largest_volume_pct=max(largest_volume_pct,vol_pct)
            assert vol_pct<.01 and '2026-09-17'<=day<='2026-10-01'
    assert not unequal,("5m OHLC price != 15m source",sym,unequal)
    first_year=[day for day in missing_open if day>="2025-10-09" and day<="2026-10-08"]
    year_gaps=[x for x in gaps if "2025-10-09"<=x[0]<="2026-10-08"]
    assert not first_year
    assert not year_gaps
    return dict(symbol=sym,source_5m=len(fine),source_15m=len(coarse),
       days_5m_complete_source=len(byday),daily_5m_count_hist=dict(source_hist),
       pair_5m_15m_match=successes,bars15m_not_covered_by_5m=notCovered,
       volume_drift_candle_count=sum(volume_drift.values()),
       volume_drift_by_date=dict(sorted(volume_drift.items())),
       volume_drift_max_relative_pct=round(largest_volume_pct,7),
       price_OHLC_matched_exactly=True,volume_matched_exactly=not volume_drift,
       source_first_date=min(byday),source_last_date=max(byday),
       unverified_warmup_missing_opens=missing_open,
       missing_5m_internal_intervals=len(gaps),
       year_missing_intraday=0,source_sha5m=META[sym]["source_sha256"],
       shared_5m_store_content_sha=META[sym]["source_store_reads"][0]["content_sha256"],
       source_adjustment_status="not_verified",
       source_point_in_time_status="not_verified")

def run():
    out={}
    for sym in SPEC["frozen_cohort"]:
        z=audit(sym);out[sym]=z
        print("FINE_SOURCE_5M",sym,"rows",z["source_5m"],"matched15m",z["pair_5m_15m_match"],
            "uncovered15m",z["bars15m_not_covered_by_5m"],
            "missing_open_days",z["unverified_warmup_missing_opens"][:6],
             "gaps",z["missing_5m_internal_intervals"],"volume_drift",z["volume_drift_candle_count"],
             "max_volume_pct",z["volume_drift_max_relative_pct"],flush=True)
    total=sum(v["pair_5m_15m_match"] for v in out.values())
    result=dict(schema=SPEC["schema"],read_only_audit=True,
       source_producer_independent=False,source_state=out,total_verified_15m_candles_rebuilt_from_5m=total,
       venue_quote_fills_proven=False,BOATS_overnight_source_proven=False,
       point_in_time_market_data_proven=False)
    path=ROOT/"FIVE_MINUTE_AUDIT_V18.json"
    assert not path.exists(),"requires readback before editing"
    path.write_text(json.dumps(result,indent=2))
    print("FINE_AUDIT_SHA",hashlib.sha256(path.read_bytes()).hexdigest())
if __name__=="__main__":run()