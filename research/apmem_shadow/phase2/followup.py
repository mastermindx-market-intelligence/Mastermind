"""Exploratory falsification diagnostics; original frozen outcomes are retained.

These functions create no collection service, runtime, strategy or promotion gate.
Options ablations are AFTER the initial joint-options result, not a holdout.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .targets import HORIZONS, causal_features, future_mean
from .forecasts import Settings, direct_har, qlike
from .calibration import coverage_diagnostics
from .evaluation import ERAS, block_mean_interval, portfolio, base_exposures, delayed_weights


def options_ablation(p, options, instrument, original, config=Settings()):
    full=causal_features(p,options,instrument)["har_options"]
    lag2=full.copy();lag2[:1,-2:]=np.nan;lag2[1:,-2:]=full[:-1,-2:]
    feature_sets={"har_iv":full[:,:-1],"har_gex":np.column_stack([full[:,:6],full[:,-1]]),
                  "har_options_lag2":lag2}
    pred={name:original[name] for name in ("apmem","har_extended","har_options","equal_blend")}
    logs={}
    for name,features in feature_sets.items():
        out=np.full((len(p),3),np.nan);records=[]
        for j,h in enumerate(HORIZONS):
            out[:,j],rec=direct_har(features,p.variance.to_numpy(),h,config);records.extend(rec)
        pred[name],logs[name]=out,records
    pred["apmem_iv_half"]=(pred["apmem"]+pred["har_iv"])/2
    rows,pairs=[],[]
    for target in ("variance","return_square"):
        for j,h in enumerate(HORIZONS):
            y=future_mean(p[target],h)
            common=np.isfinite(y)&(p.index>="2015-01-01")
            for a in pred.values():common &= np.isfinite(a[:,j])&(a[:,j]>0)
            for era,(lo,hi) in ERAS.items():
                ids=np.where(common&(p.index>=lo)&(p.index<=hi))[0]
                if not len(ids):continue
                for name,a in pred.items():
                    rows.append({"instrument":instrument,"target":target,"horizon":h,"era":era,
                                 "model":name,"n":len(ids),"qlike":float(qlike(y[ids],a[ids,j]).mean()),
                                 "exploratory_post_primary":True})
                if era=="all":
                    for name,baseline in (("har_iv","har_extended"),("har_gex","har_extended"),
                                          ("har_options","har_iv"),("har_options_lag2","har_options"),
                                          ("apmem_iv_half","apmem")):
                        diff=qlike(y[ids],pred[name][ids,j])-qlike(y[ids],pred[baseline][ids,j])
                        pairs.append({"instrument":instrument,"target":target,"horizon":h,
                            "candidate":name,"baseline":baseline,**block_mean_interval(diff),
                            "exploratory_post_primary":True})
    return pred,logs,rows,pairs


def scale_calibrate(v, forecast, horizon, window=504, minimum=252):
    """QLIKE-optimal scalar from matured trailing errors; no fit to future labels."""
    y=future_mean(v,horizon);f=np.asarray(forecast,float);out=np.full(len(f),np.nan)
    if f.shape!=y.shape or minimum<1 or window<minimum:raise ValueError("invalid scalar calibration")
    for t in range(len(f)):
        if not np.isfinite(f[t]) or f[t]<=0:continue
        end=t-horizon;ids=np.arange(max(0,end-window+1),end+1)
        ids=ids[np.isfinite(y[ids])&np.isfinite(f[ids])&(f[ids]>0)]
        if len(ids)>=minimum:out[t]=f[t]*np.mean(y[ids]/f[ids])
    return out


def open_interval_labels(p):
    """At close t, the next-open holding interval ends at open t+2."""
    y=np.full(len(p),np.nan);o=p.open.to_numpy();d=p.distributions.to_numpy()
    y[:-2]=np.log((o[2:]+d[2:])/o[1:-1])
    return y


def execution_quantiles(p, forecast, alpha, window=504, minimum=252):
    """Historical residual ending by t only; never use the still-open t+1 label."""
    if not 0<alpha<.5 or minimum<1 or window<minimum:raise ValueError("invalid tail settings")
    y=open_interval_labels(p);f=np.asarray(forecast,float)
    if f.shape!=y.shape:raise ValueError("execution forecast shape mismatch")
    residual=np.full(len(f),np.nan);valid=np.isfinite(y)&np.isfinite(f)&(f>0)
    residual[valid]=y[valid]/np.sqrt(f[valid])
    out=np.full(len(f),np.nan);hist=np.full(len(f),np.nan)
    for t in range(len(f)):
        end=t-2;ids=np.arange(max(0,end-window+1),end+1)
        known=y[ids];known=known[np.isfinite(known)]
        if len(known)>=minimum:hist[t]=np.quantile(known,alpha)
        z=residual[ids];z=z[np.isfinite(z)]
        if len(z)>=minimum and np.isfinite(f[t]) and f[t]>0:
            out[t]=np.quantile(z,alpha)*np.sqrt(f[t])
    return y,out,hist


def execution_calibration_study(p,predictions):
    rows=[]
    for h in (1,5):
        j=HORIZONS.index(h)
        for alpha in (.05,.01):
            vals={m:execution_quantiles(p,predictions[m][:,j],alpha)
                  for m in ("ewma94","apmem","equal_blend")}
            common=p.index>="2015-01-01"
            for y,q,hist in vals.values():common &= np.isfinite(y)&np.isfinite(q)&np.isfinite(hist)
            for era,(lo,hi) in ERAS.items():
                mask=common&(p.index>=lo)&(p.index<=hi)
                for model,(y,q,hist) in vals.items():
                    for method,a in (("filtered_historical",q),("unscaled_historical",hist)):
                        rows.append({"model":model,"scale_horizon":h,"era":era,"method":method,
                                     **coverage_diagnostics(np.where(mask,y,np.nan),np.where(mask,a,np.nan),alpha),
                                     "origin_to_label_end_sessions":2,"exploratory":True})
    return rows


def exact_static_and_decomposition(p,predictions,retained):
    """Corrected hindsight comparator, explicitly NOT an executable learned rule."""
    start=np.where(p.index>="2015-01-01")[0][0]
    o,d,dates=p.open.to_numpy()[start:],p.distributions.to_numpy()[start:],p.index[start:]
    rows=[]
    for base_name,base in base_exposures(p).items():
        bw=delayed_weights(base,1)[start:-1]
        for target in (10,15):
            key=f"{base_name}/equal_blend_vol{target}";dynamic=retained[key]
            rw=dynamic[:,1];ratio=float(rw.mean()/bw.mean())
            weights=np.r_[bw*ratio,bw[-1]*ratio]
            static=portfolio(o,d,dates,weights,cost=.0005,cash_rate=0.)
            market=static["asset_returns"];weight_delta=rw-static["weights"]
            exposure_effect=weight_delta*market
            actual_delta=dynamic[:,0]-static["net_returns"]
            negative=market<0;positive=market>0
            rows.append({"policy":key,"comparison":"exact_hindsight_exposure_matched_static",
                         "not_prospective":True,"static_multiplier":ratio,
                         "dynamic_mean_exposure":float(rw.mean()),
                         "static_mean_exposure":float(static["weights"].mean()),
                         "static_metrics":static["metrics"],
                         "arithmetic_exposure_effect_on_negative_days":float(exposure_effect[negative].sum()),
                         "arithmetic_exposure_effect_on_positive_days":float(exposure_effect[positive].sum()),
                         "arithmetic_residual_cost_effect":float((actual_delta-exposure_effect).sum()),
                         "arithmetic_total_return_difference":float(actual_delta.sum()),
                         "not_compounded_wealth_attribution":True})
    return rows


def disagreement_diagnostic(p,predictions):
    f=np.column_stack([predictions[m][:,1] for m in ("ewma94","apmem","har_extended")])
    disagreement=pd.Series(np.std(np.log(f),axis=1),index=p.index)
    rank=disagreement.rolling(252,min_periods=252).rank(pct=True).to_numpy()
    y=future_mean(p.variance,5);forecast=predictions["equal_blend"][:,1]
    valid=np.isfinite(rank)&np.isfinite(y)&np.isfinite(forecast)&(p.index>="2015-01-01")
    rows=[]
    for name,mask in (("bottom_quintile",rank<=.2),("middle_three_quintiles",(rank>.2)&(rank<=.8)),("top_quintile",rank>.8)):
        ids=np.where(valid&mask)[0]
        if len(ids):
            rows.append({"causal_disagreement_group":name,"n":len(ids),
                         "qlike":float(qlike(y[ids],forecast[ids]).mean()),
                         "realized_above_twice_forecast_fraction":float(np.mean(y[ids]>2*forecast[ids])),
                         "descriptive_not_promoted_gate":True})
    return rows
