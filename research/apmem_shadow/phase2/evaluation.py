"""Forecast accuracy, dependent-data uncertainty, and separate portfolio utility."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .forecasts import qlike
from .targets import HORIZONS, future_mean

ERAS = {"all":("2015-01-01","2026-11-12"),
        "2015_2019":("2015-01-01","2019-12-31"),
        "2020_2023":("2020-01-01","2023-12-31"),
        "2024_2026":("2024-01-01","2026-11-12")}
MAIN_MODELS = ("incumbent","mean20","ewma94","ewma97","apmem","har", "har_extended","equal_blend","adaptive_blend")


def block_mean_interval(diff: np.ndarray,block: int = 63,resamples: int = 2000,
                        seed: int = 20261113) -> dict:
    """Circular moving blocks, exact length including final partial block."""
    x = np.asarray(diff,float)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or block < 1 or resamples < 20:
        raise ValueError("invalid bootstrap input")
    n = len(x)
    block = min(block,n)
    whole,remainder = divmod(n,block)
    cs = np.r_[0.0,np.cumsum(np.r_[x,x])]
    sums = cs[np.arange(n)+block]-cs[np.arange(n)]
    rng = np.random.default_rng(seed)
    draw = sums[rng.integers(0,n,size=(resamples,whole))].sum(axis=1)
    if remainder:
        partial = cs[np.arange(n)+remainder]-cs[np.arange(n)]
        draw += partial[rng.integers(0,n,size=resamples)]
    means = draw/n
    estimate = float(x.mean())
    p = float((1+np.sum(np.abs(means-estimate) >= abs(estimate)))/(resamples+1))
    return {"n":n,"mean_difference":estimate,"pointwise_95_interval":np.quantile(means,[.025,.975]).tolist(),
            "centered_bootstrap_two_sided_p":p,"block":block,"resamples":resamples,"seed":seed,
            "prospective":False,"stationarity_assumption_not_verified":True}


def holm(pvalues: np.ndarray) -> np.ndarray:
    p = np.asarray(pvalues,float)
    if p.ndim != 1 or not np.isfinite(p).all() or ((p < 0)|(p > 1)).any():
        raise ValueError("invalid p-values")
    order = np.argsort(p)
    adjusted = np.minimum(1,np.maximum.accumulate(p[order]*(len(p)-np.arange(len(p)))))
    out = np.empty_like(p)
    out[order] = adjusted
    return out


def forecast_scores(p,predictions):
    rows,pairs = [],[]
    for target in ("variance","return_square"):
        for j,h in enumerate(HORIZONS):
            y = future_mean(p[target],h)
            common = np.isfinite(y)
            for name in MAIN_MODELS:
                common &= np.isfinite(predictions[name][:,j])&(predictions[name][:,j] > 0)
            for era,(lo,hi) in ERAS.items():
                ids = np.where(common&(p.index >= lo)&(p.index <= hi))[0]
                if not len(ids):
                    continue
                actual = y[ids]
                for name in MAIN_MODELS:
                    f = predictions[name][ids,j]
                    rows.append({"target":target,"horizon":h,"era":era,"model":name,
                                 "n":len(ids),"first":str(p.index[ids[0]].date()),"last":str(p.index[ids[-1]].date()),
                                 "qlike":float(qlike(actual,f).mean()),"variance_mse":float(np.mean((actual-f)**2)),
                                 "annualized_vol_mae_pp":float(np.mean(np.abs(np.sqrt(actual*252)-np.sqrt(f*252)))*100),
                                 "forecast_to_realized_mean":float(f.mean()/actual.mean()),
                                 "underpredict_2x_fraction":float(np.mean(actual > 2*f))})
                if era == "all":
                    for baseline in ("incumbent","ewma94","apmem","har_extended"):
                        d = qlike(actual,predictions["equal_blend"][ids,j])-qlike(actual,predictions[baseline][ids,j])
                        pairs.append({"target":target,"horizon":h,"candidate":"equal_blend","baseline":baseline,
                                      **block_mean_interval(d),"common_row_gaps":int(np.sum(np.diff(ids) > 1))})
            if "har_options" in predictions:
                ids = np.where(common&np.isfinite(predictions["har_options"][:,j])
                               &(predictions["har_options"][:,j] > 0)&(p.index >= "2015-01-01"))[0]
                if len(ids):
                    for name in ("har_extended","har_options","ewma94","equal_blend"):
                        f = predictions[name][ids,j]
                        rows.append({"target":target,"horizon":h,"era":"options_common","model":name,"n":len(ids),
                                     "first":str(p.index[ids[0]].date()),"last":str(p.index[ids[-1]].date()),
                                     "qlike":float(qlike(y[ids],f).mean()),"variance_mse":float(np.mean((y[ids]-f)**2))})
    return rows,pairs


def portfolio(open_prices,distributions,dates,target_weights,*,cost=.0005,cash_rate=0.0):
    """Self-financing open rebalance, dividends as cash, terminal liquidation.

    Dividend at the next ex-date open belongs to the old holder. Turnover uses
    drifted stock weights, including cash dividends, not just target changes.
    """
    o,d,w = (np.asarray(a,float) for a in (open_prices,distributions,target_weights))
    if (o.ndim != 1 or d.shape != o.shape or w.shape != o.shape or len(o) < 3
            or len(dates) != len(o) or not np.isfinite(np.r_[o,d,w]).all() or (o <= 0).any()
            or (d < 0).any() or ((w < 0)|(w > 1)).any()
            or not 0 <= cost < .1 or not 0 <= cash_rate < 1):
        raise ValueError("invalid portfolio inputs")
    if not dates.is_monotonic_increasing or not dates.is_unique:
        raise ValueError("invalid portfolio dates")
    days = np.diff(dates.to_numpy()).astype("timedelta64[D]").astype(int)
    cash = (1+cash_rate)**(days/365.25)-1
    price_growth = o[1:]/o[:-1]
    asset = (o[1:]+d[1:])/o[:-1]-1
    net,turnovers = np.empty(len(o)-1),np.empty(len(o)-1)
    drift = 0.0
    for i in range(len(net)):
        target = w[i]
        c = (cost*(target-drift)/(1+cost*target) if target >= drift
             else cost*(drift-target)/(1-cost*target))
        turnover = abs(target*(1-c)-drift)
        growth = 1+target*asset[i]+(1-target)*cash[i]
        net[i],turnovers[i] = (1-c)*growth-1,turnover
        drift = target*price_growth[i]/growth
    net[-1] = (1+net[-1])*(1-cost*drift)-1
    turnovers[-1] += drift
    equity = np.r_[1.0,np.cumprod(1+net)]
    drawdown = equity/np.maximum.accumulate(equity)-1
    excess = net-cash
    years = (dates[-1]-dates[0]).days/365.25
    vol = np.std(excess,ddof=1)*np.sqrt(252)
    downside = np.sqrt(np.mean(np.minimum(excess,0)**2))*np.sqrt(252)
    tail = np.sort(net)[:max(1,int(np.ceil(.05*len(net))))]
    positive,negative = asset > 0,asset < 0
    upside = float(net[positive].sum()/asset[positive].sum()) if positive.any() else None
    capture = float(net[negative].sum()/asset[negative].sum()) if negative.any() else None
    underwater=0;longest=0
    for dd in drawdown:
        underwater = underwater+1 if dd < -1e-12 else 0
        longest = max(longest,underwater)
    metrics = {"n_intervals":len(net),"total_return":float(equity[-1]-1),"cagr":float(equity[-1]**(1/years)-1),
               "annualized_excess_vol":float(vol),"excess_sharpe":float(excess.mean()*252/vol) if vol else None,
               "sortino":float(excess.mean()*252/downside) if downside else None,"max_open_drawdown":float(drawdown.min()),
               "expected_shortfall_5pct_daily":float(tail.mean()),"worst_day":float(net.min()),
               "ulcer_index":float(np.sqrt(np.mean(drawdown**2))),"upside_capture":upside,"downside_capture":capture,
               "longest_underwater_intervals":longest,"mean_equity_exposure":float(w[:-1].mean()),
               "turnover_per_year":float(turnovers.sum()/years),"one_way_cost":cost,"cash_rate":cash_rate,
               "first_open":str(dates[0].date()),"last_open":str(dates[-1].date())}
    return {"metrics":metrics,"net_returns":net,"cash_returns":cash,"asset_returns":asset,
            "weights":w[:-1],"turnover":turnovers,"equity":equity}


def base_exposures(p):
    total = p.total_index
    return {"fully_invested":np.ones(len(p)),
            "trend200":np.where(total >= total.rolling(200,min_periods=200).mean(),1.0,.25),
            "contrarian5":np.where(total.pct_change(5,fill_method=None) < 0,1.0,.25)}


def delayed_weights(signal_weights,delay):
    if not isinstance(delay,int) or delay < 1:
        raise ValueError("execution must be at least next open")
    a = np.asarray(signal_weights,float)
    if a.ndim != 1 or not np.isfinite(a).all() or ((a < 0)|(a > 1)).any():
        raise ValueError("invalid signal weights")
    out = np.zeros_like(a)
    out[delay:] = a[:-delay]
    return out


def utility_study(p,predictions):
    rows,retained = [],{}
    ids = np.where(p.index >= "2015-01-01")[0]
    if not len(ids):
        return rows,retained
    start = int(ids[0])
    names = ("incumbent","ewma94","apmem","har_extended","equal_blend","adaptive_blend")
    common = np.ones(len(p),bool)
    for name in names:
        common &= np.isfinite(predictions[name][:,1])&(predictions[name][:,1] > 0)
    train = (p.index < "2015-01-01")&common
    if not train.any():
        raise ValueError("no pre-evaluation exposure calibration era")
    o,d,dates = p.open.to_numpy()[start:],p.distributions.to_numpy()[start:],p.index[start:]
    for base_name,base in base_exposures(p).items():
        signals = {"unmanaged":base}
        metadata = {"unmanaged":{"model":"none","target_vol":None,"kind":"unmanaged"}}
        for target in (.10,.15):
            for model in names:
                multiplier = np.zeros(len(p))
                multiplier[common] = np.minimum(1,target/np.sqrt(252*predictions[model][common,1]))
                dynamic = base*multiplier
                label = f"{model}_vol{int(target*100)}"
                signals[label] = dynamic
                metadata[label] = {"model":model,"target_vol":target,"kind":"dynamic",
                                   "missing_forecast_cash_sessions":int((~common[start:]).sum())}
                static = float(dynamic[train].mean()/base[train].mean())
                stat = label+"_train_static"
                signals[stat],metadata[stat] = base*static,{"model":model,"target_vol":target,
                    "kind":"train_exposure_matched","static_multiplier":static}
                # Nonimplementable diagnostic; NEVER label as deployable strategy.
                hindsight = float(dynamic[start:].mean()/base[start:].mean())
                hs = label+"_hindsight_static"
                signals[hs],metadata[hs] = base*hindsight,{"model":model,"target_vol":target,
                    "kind":"hindsight_exposure_matched_diagnostic","static_multiplier":hindsight}
        for label,signal in signals.items():
            kind = metadata[label]["kind"]
            scenarios = ([(.0005,1,0.0)] if kind.endswith("matched") or "diagnostic" in kind
                         else [(c,delay,rf) for c in (.0005,.002) for delay in (1,2) for rf in (0.0,.03)])
            for cost,delay,rf in scenarios:
                weights = delayed_weights(signal,delay)[start:]
                result = portfolio(o,d,dates,weights,cost=cost,cash_rate=rf)
                rows.append({"base_strategy":base_name,"policy":label,"delay":delay,
                             **metadata[label],**result["metrics"]})
                if cost == .0005 and delay == 1 and rf == 0:
                    retained[f"{base_name}/{label}"] = result
    return rows,retained


def era_utility(p,retained):
    dates = p.index[p.index >= "2015-01-01"][1:]
    rows = []
    for key,result in retained.items():
        if key.endswith("static"):
            continue
        for era,(lo,hi) in ERAS.items():
            if era == "all":
                continue
            mask = (dates >= lo)&(dates <= hi)
            r = result["net_returns"][mask]
            if len(r) < 2:
                continue
            eq = np.r_[1,np.cumprod(1+r)]
            dd = eq/np.maximum.accumulate(eq)-1
            sd = r.std(ddof=1)
            rows.append({"policy":key,"era":era,"n":len(r),"total_return":float(eq[-1]-1),
                         "annualized_vol":float(sd*np.sqrt(252)),"zero_cash_sharpe":float(r.mean()/sd*np.sqrt(252)) if sd else None,
                         "max_open_drawdown":float(dd.min()),"es5":float(np.sort(r)[:max(1,int(np.ceil(.05*len(r))))].mean())})
    return rows
