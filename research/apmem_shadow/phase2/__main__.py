"""Run frozen research from explicitly supplied licensed snapshots, offline."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import platform
from pathlib import Path
import time
import numpy as np
import pandas as pd
import scipy
from .targets import prepare_prices,future_mean,HORIZONS
from .forecasts import forecast_all,Settings
from .calibration import return_quantiles,coverage_diagnostics,variance_upper
from .evaluation import forecast_scores,utility_study,era_utility,holm,ERAS
from .consumer import research_context


def clean(value):
    if isinstance(value,dict):
        return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value,(np.integer,)):
        return int(value)
    if isinstance(value,(np.bool_,)):
        return bool(value)
    if isinstance(value,(float,np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def save(path,value):
    path.write_text(json.dumps(clean(value),indent=2,allow_nan=False)+"\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calibration_study(p,predictions):
    rows,envelopes,latest=[],[],{}
    names=("incumbent","ewma94","apmem","har_extended","equal_blend","adaptive_blend")
    actual=np.r_[p.return_log.to_numpy()[1:],np.nan]
    for alpha in (.05,.01):
        quantiles={name:return_quantiles(p.return_log.to_numpy(),predictions[name][:,0],alpha=alpha)
                   for name in names}
        common=np.isfinite(actual)&(p.index >= "2015-01-01")
        for q in quantiles.values():
            for a in q.values():
                common &= np.isfinite(a)
        for era,(lo,hi) in ERAS.items():
            mask=common&(p.index >= lo)&(p.index <= hi)
            a=np.where(mask,actual,np.nan)
            for name,q in quantiles.items():
                for method,array in q.items():
                    rows.append({"model":name,"method":method,"era":era,
                                 **coverage_diagnostics(a,np.where(mask,array,np.nan),alpha)})
        latest[str(alpha)]={name:{method:float(a[-1]) for method,a in q.items()}
                            for name,q in quantiles.items()}
    for j,h in enumerate(HORIZONS):
        y=future_mean(p.variance,h)
        bands={name:variance_upper(p.variance.to_numpy(),predictions[name][:,j],h) for name in names}
        common=np.isfinite(y)&(p.index >= "2015-01-01")
        for band in bands.values():
            common &= np.isfinite(band)
        for name,band in bands.items():
            for era,(lo,hi) in ERAS.items():
                ids=np.where(common&(p.index >= lo)&(p.index <= hi))[0]
                if len(ids):
                    envelopes.append({"model":name,"horizon":h,"era":era,"n":len(ids),"nominal_coverage":.9,
                                      "observed_coverage":float(np.mean(y[ids]<=band[ids])),
                                      "mean_upper_variance":float(np.mean(band[ids])),
                                      "mean_realized_variance":float(np.mean(y[ids])),
                                      "prospective":False})
    return rows,envelopes,latest


def protection_diagnostics(retained):
    out=[]
    for base in ("fully_invested","trend200","contrarian5"):
        unmanaged=retained[base+"/unmanaged"]
        ordered=np.argsort(unmanaged["asset_returns"])
        bad,best=ordered[:20],ordered[-20:]
        for label,result in retained.items():
            if not label.startswith(base+"/"):
                continue
            r=result["net_returns"]
            out.append({"policy":label,"worst20_asset_days_mean_return":float(r[bad].mean()),
                        "best20_asset_days_mean_return":float(r[best].mean()),
                        "worst20_days_mean_equity_weight":float(result["weights"][bad].mean()),
                        "best20_days_mean_equity_weight":float(result["weights"][best].mean()),
                        "selection_is_ex_post_diagnostic":True})
    return out


def run_one(symbol,price_path,options_path,outdir):
    raw=pd.read_parquet(price_path)
    raw=raw.loc[(raw.index >= "2010-01-01")&(raw.index <= "2026-11-12")].copy()
    p=prepare_prices(raw)
    options=pd.read_parquet(options_path) if options_path and options_path.exists() else None
    if options is not None:
        options=options.loc[options.index <= "2026-11-12"]
    predictions,logs=forecast_all(p,options=options,instrument=symbol)
    scores,pairs=forecast_scores(p,predictions)
    utility,retained=utility_study(p,predictions)
    quantiles,envelopes,latest_quantiles=calibration_study(p,predictions)
    price_sha=digest(price_path)
    receipt={"instrument":symbol,"price_sha256":price_sha,"price_rows":len(raw),
             "first":str(raw.index[0].date()),"last":str(raw.index[-1].date()),
             "options_sha256":digest(options_path) if options is not None else None,
             "options_rows":len(options) if options is not None else 0,
             "nonzero_distribution_days":int((p.distributions>0).sum()),
             "historical_first_availability":None,"dataset_vintage":"current_snapshot",
             "python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"scipy":scipy.__version__}
    latest={k:(np.sqrt(v[-1]*252)*100).tolist() for k,v in predictions.items()}
    upper=[variance_upper(p.variance.to_numpy(),predictions["equal_blend"][:,j],h)[-1] for j,h in enumerate(HORIZONS)]
    context=research_context(instrument=symbol,origin_session=str(p.index[-1].date()),
        forecast=predictions["equal_blend"][-1],upper90=upper,
        decision_at=datetime.now(timezone.utc).isoformat(),source_sha256=price_sha)
    outdir.mkdir(parents=True,exist_ok=False)
    save(outdir/"source_receipt.json",receipt)
    save(outdir/"fit_log.json",logs)
    save(outdir/"research_context.json",context)
    summary={"source":receipt,"forecast_scores":scores,"paired_forecast_tests":pairs,
             "utility":utility,"era_utility":era_utility(p,retained),"calibration":quantiles,
             "variance_envelopes":envelopes,"protection":protection_diagnostics(retained),
             "latest_forecast_annualized_percent":latest,"latest_return_quantiles":latest_quantiles,
             "model_coverage":logs["coverage"],"fit_summary":{k:{"fits":len(v),"successful":sum(x["success"] for x in v)}
                 for k,v in logs.items() if k in ("apmem","har","har_extended","har_options")}}
    save(outdir/"summary.json",summary)
    # Private recomputation inputs/paths; never automatically published.
    np.savez_compressed(outdir/"predictions.npz",**predictions)
    p.to_parquet(outdir/"prepared_prices.parquet")
    np.savez_compressed(outdir/"utility_paths.npz",**{k:np.column_stack([r["net_returns"],r["weights"],r["turnover"]])
                       for k,r in retained.items()})
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices-root",type=Path,required=True)
    parser.add_argument("--options-root",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--symbols",nargs="+",default=["QQQ","SPY","IWM"])
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit("output exists; inspect original run rather than overwriting")
    args.output.mkdir(parents=True)
    started=datetime.now(timezone.utc).isoformat()
    all_pairs,completed,failed=[],[],{}
    for symbol in args.symbols:
        t=time.monotonic()
        price=args.prices_root/(symbol+"_yahoo_raw.parquet")
        options=args.options_root/(symbol+"_gex.parquet") if args.options_root else None
        try:
            result=run_one(symbol,price,options,args.output/symbol)
        except (ValueError,FileNotFoundError,KeyError) as exc:
            failed[symbol]={"type":type(exc).__name__,"reason":str(exc)}
            save(args.output/"failures.json",failed)
            print(json.dumps({"symbol":symbol,"status":"INPUT_OR_CONTRACT_REFUSED",**failed[symbol]}),flush=True)
            continue
        completed.append(symbol)
        all_pairs.extend({"instrument":symbol,**r} for r in result["paired_forecast_tests"])
        print(json.dumps({"symbol":symbol,"status":"RETROSPECTIVE_RESEARCH_COMPLETE",
                          "seconds":round(time.monotonic()-t,2),"price_rows":result["source"]["price_rows"],
                          "fit_summary":result["fit_summary"],"utility_scenarios":len(result["utility"])}),flush=True)
    if all_pairs:
        adjusted=holm(np.array([r["centered_bootstrap_two_sided_p"] for r in all_pairs]))
        for r,p in zip(all_pairs,adjusted):
            r["holm_adjusted_p_full_completed_family"]=float(p)
        save(args.output/"paired_tests_holm.json",all_pairs)
    save(args.output/"run_receipt.json",{"schema":"mastermind.volatility_phase2_run.v1","started_at":started,
        "ended_at":datetime.now(timezone.utc).isoformat(),"completed":completed,"failed":failed,
        "multiplicity_family_size":len(all_pairs),"prospective":False,"may_trade":False,
        "source_sha256":{str(p.relative_to(Path(__file__).parent)):digest(p) for p in Path(__file__).parent.glob("*.py")}})


if __name__ == "__main__":
    main()
