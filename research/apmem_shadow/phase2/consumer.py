"""Research-context projection only; no signal/ranking/sizing/trading API."""
from __future__ import annotations
from datetime import datetime
import re
import numpy as np


def _utc(value):
    if not isinstance(value,str):
        raise ValueError("missing clock")
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone required")
    return d


def research_context(*,instrument,origin_session,forecast,upper90,decision_at,
                     observed_at=None,fit_completed_at=None,source_sha256=None,
                     fit_last_session=None,max_age_days=4):
    """Pure contract checker. Supplied clocks require independent provenance."""
    reasons=[]
    try:
        decision=_utc(decision_at)
        origin=datetime.fromisoformat(origin_session).date()
        if str(origin)!=origin_session:
            raise ValueError("noncanonical origin")
    except (ValueError,TypeError):
        raise ValueError("invalid decision/origin clock")
    if not isinstance(instrument,str) or not re.fullmatch(r"[A-Z]{1,8}",instrument):
        raise ValueError("invalid instrument")
    if not isinstance(source_sha256,str) or not re.fullmatch(r"[a-f0-9]{64}",source_sha256):
        reasons.append("SOURCE_DIGEST_UNVERIFIED")
    clocks={}
    for key,value in (("observed",observed_at),("fit",fit_completed_at)):
        try:
            clocks[key]=_utc(value)
        except (ValueError,TypeError):
            reasons.append(key.upper()+"_CLOCK_UNKNOWN")
    if any(d>decision for d in clocks.values()):
        reasons.append("FUTURE_AVAILABILITY")
    if "observed" in clocks and "fit" in clocks and clocks["fit"]<clocks["observed"]:
        reasons.append("FIT_PRECEDES_CAPTURE")
    if fit_last_session!=origin_session:
        reasons.append("FIT_SESSION_MISMATCH")
    age=(decision.date()-origin).days
    if age<0:
        reasons.append("FUTURE_ORIGIN")
    if age>max_age_days:
        reasons.append("STALE_ORIGIN")
    f,u=np.asarray(forecast,float),np.asarray(upper90,float)
    if f.shape!=(3,) or not np.isfinite(f).all() or (f<=0).any():
        reasons.append("FORECAST_UNAVAILABLE")
    if u.shape!=(3,) or not np.isfinite(u).all() or (u<=0).any():
        reasons.append("ENVELOPE_UNAVAILABLE")
    valid=not reasons
    return {"schema":"mastermind.volatility_research_context.v2","instrument":instrument,
            "origin_session":origin_session,"decision_at":decision_at,
            "status":"RESEARCH_ONLY" if valid else "ABSTAIN","reason_codes":sorted(set(reasons)),
            "horizons_sessions":[1,5,20],"annualized_vol_percent":(np.sqrt(f*252)*100).tolist() if valid else None,
            "upper90_variance":u.tolist() if valid else None,
            "source_sha256":source_sha256,"point_in_time_historical_validation":False,
            "may_rank":False,"may_size":False,"may_trade":False,
            "note":"Historical research, not certified coverage or a production trading instruction."}
