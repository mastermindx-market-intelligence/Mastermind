"""Leakage-safe research harness for trend-persistence experiments.

Isolated from live ranking, sizing and gates. Reuses the survivorship-safe breadth panel
and tests whether path-quality features add information conditional on vanilla momentum.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any
from brain import trend_persistence as tp

DEFAULT_HORIZONS = (5, 20, 60)
MIN_NAMES_PER_DATE = 20
MIN_INDEPENDENT_DATES = 8
_BASELINE = ("persistence.momentum.ret_20d","persistence.momentum.ret_60d","persistence.momentum.ret_120d","persistence.momentum.ret_252d")
_INCREMENTAL = (
 "persistence.path_quality.efficiency_20d","persistence.path_quality.efficiency_60d","persistence.path_quality.efficiency_120d",
 "persistence.path_quality.positive_day_fraction_20d","persistence.path_quality.positive_day_fraction_60d","persistence.path_quality.positive_day_fraction_120d",
 "persistence.gain_retention.retained_20d","persistence.gain_retention.retained_60d","persistence.gain_retention.retained_120d",
 "persistence.drawdown.20d.max_drawdown","persistence.drawdown.60d.max_drawdown","persistence.drawdown.120d.max_drawdown",
)

def _finite(v: Any):
    try:
        import math
        x=float(v); return x if math.isfinite(x) else None
    except (TypeError, ValueError): return None

def _forward_label(subject, benchmark, pos: int, horizon: int):
    try:
        p0,b0=float(subject.iloc[pos]),float(benchmark.iloc[pos])
        if p0<=0 or b0<=0 or pos+horizon>=len(subject): return None
        path=subject.iloc[pos:pos+horizon+1].astype(float); bp=benchmark.iloc[pos:pos+horizon+1].astype(float)
        ret=float(path.iloc[-1]/p0-1.0); bret=float(bp.iloc[-1]/b0-1.0)
        dd=path/path.cummax()-1.0
        return {"forward_return":ret,"forward_rel":ret-bret,"forward_max_drawdown":float(dd.min())}
    except Exception: return None

def build_panel(prices: dict, benchmark, *, horizons=DEFAULT_HORIZONS, formation_step: int=5, min_history: int=253):
    try:
        b=benchmark.astype(float).dropna(); b=b[b>0].sort_index()
    except Exception: return []
    horizons=tuple(sorted({int(h) for h in horizons if int(h)>0})); max_h=max(horizons) if horizons else 0
    out=[]
    for ticker,raw in (prices or {}).items():
        try:
            s=raw.astype(float).dropna(); s=s[s>0].sort_index(); common=s.index.intersection(b.index)
            s=s.reindex(common); bb=b.reindex(common)
        except Exception: continue
        if len(s)<=min_history+max_h: continue
        for pos in range(min_history-1,len(s)-max_h,max(1,int(formation_step))):
            asof=s.index[pos]; features=tp.flatten(tp.extract(s,benchmark=bb,asof=asof))
            for h in horizons:
                label=_forward_label(s,bb,pos,h)
                if label is not None: out.append({"asof":str(asof)[:10],"ticker":str(ticker).upper(),"horizon_d":h,**features,**label})
    return out

def _thin(pairs, horizon):
    try:
        import numpy as np, pandas as pd
        kept=[]; last=None
        for d,v in sorted(pairs):
            ts=pd.Timestamp(d)
            if last is None or int(np.busday_count(last.date(),ts.date()))>=int(horizon): kept.append(float(v)); last=ts
        return kept
    except Exception: return []

def _summary(values):
    if not values: return {"n_dates":0,"mean":None,"positive_fraction":None}
    return {"n_dates":len(values),"mean":round(sum(values)/len(values),5),"positive_fraction":round(sum(v>0 for v in values)/len(values),3)}

def evaluate(panel, *, horizons=DEFAULT_HORIZONS):
    try:
        import numpy as np, pandas as pd
        from engine.validation import rank_ic
    except Exception as exc: return {"status":"unavailable","error":str(exc)}
    result={"schema":1,"status":"building","horizons":{}}
    for horizon in sorted({int(h) for h in horizons}):
        rows=[r for r in panel if int(r.get("horizon_d") or 0)==horizon]; by_date=defaultdict(list)
        for r in rows: by_date[str(r.get("asof"))].append(r)
        hr={"n_rows":len(rows),"n_dates":len(by_date),"features":{}}
        for feature in _INCREMENTAL:
            raw_pairs=[]; cond_pairs=[]
            for d,rs in by_date.items():
                pairs=[(_finite(r.get(feature)),_finite(r.get("forward_rel"))) for r in rs]; pairs=[p for p in pairs if None not in p]
                if len(pairs)>=MIN_NAMES_PER_DATE:
                    ic=rank_ic(pd.Series([p[0] for p in pairs]),pd.Series([p[1] for p in pairs]))
                    if ic==ic: raw_pairs.append((d,float(ic)))
                complete=[]
                for r in rs:
                    vals=[_finite(r.get(feature)),_finite(r.get("forward_rel"))]+[_finite(r.get(k)) for k in _BASELINE]
                    if all(v is not None for v in vals): complete.append(vals)
                if len(complete)<MIN_NAMES_PER_DATE: continue
                a=np.asarray(complete,float); x,y,z=a[:,0],a[:,1],a[:,2:]; design=np.column_stack([np.ones(len(z)),z])
                try:
                    xr=x-design@np.linalg.lstsq(design,x,rcond=None)[0]; yr=y-design@np.linalg.lstsq(design,y,rcond=None)[0]
                    ic=rank_ic(pd.Series(xr),pd.Series(yr))
                    if ic==ic: cond_pairs.append((d,float(ic)))
                except Exception: pass
            raw=_thin(raw_pairs,horizon); cond=_thin(cond_pairs,horizon)
            hr["features"][feature]={"raw_ic":_summary(raw),"conditional_ic":_summary(cond)}
        hr["effective_n"]=max([v["conditional_ic"]["n_dates"] for v in hr["features"].values()] or [0]); hr["ready"]=hr["effective_n"]>=MIN_INDEPENDENT_DATES
        result["horizons"][str(horizon)]=hr
    if any(v.get("ready") for v in result["horizons"].values()): result["status"]="scoring"
    return result

def run_existing_panel(*, horizons=DEFAULT_HORIZONS, formation_step=5):
    try:
        from portfolio import predictions
        prices=predictions._load_panel() or {}; spy=predictions._spy_series()
        if not prices or spy is None: return {"status":"unavailable","reason":"price_panel_missing"}
        rows=build_panel(prices,spy,horizons=horizons,formation_step=formation_step); out=evaluate(rows,horizons=horizons)
        out["panel_rows"]=len(rows); out["universe_names"]=len(prices); return out
    except Exception as exc: return {"status":"unavailable","error":str(exc)}