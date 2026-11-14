"""Fixed candidate utility and earlier-regime checks; no retrospective promotion."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import norm
from research.apmem_shadow.model import Parameters,filter_variance
from .targets import HORIZONS,future_mean
from .forecasts import qlike
from .followup import execution_quantiles
from .calibration import coverage_diagnostics
from .evaluation import portfolio,base_exposures,delayed_weights


def common_execution_end(p,predictions,names):
    common=np.ones(len(p),bool)
    for name in names:common &= np.isfinite(predictions[name][:,1])&(predictions[name][:,1]>0)
    eligible=np.where(common&(np.arange(len(p))+2<len(p)))[0]
    if not len(eligible):raise ValueError('no supported next-open holding interval')
    return int(eligible[-1]+2),common


def window_utility(p,predictions,start,names,end=None):
    end_index,common=common_execution_end(p,predictions,names)
    if end is not None:
        choices=np.where(p.index<=end)[0]
        if not len(choices):raise ValueError('evaluation end precedes source')
        end_index=min(end_index,int(choices[-1]))
    ids=np.where((p.index>=start)&(np.arange(len(p))<=end_index))[0]
    if len(ids)<20:raise ValueError('insufficient utility evaluation rows')
    first=int(ids[0]);stop=end_index+1
    train=(p.index<start)&common
    if train.sum()<252:raise ValueError('insufficient prior exposure-calibration rows')
    o,d,dates=p.open.to_numpy()[first:stop],p.distributions.to_numpy()[first:stop],p.index[first:stop]
    rows=[]
    for base_name,base in base_exposures(p).items():
        base_common=base*common
        signals={'unmanaged':base,'common_input_unmanaged':base_common}
        meta={k:{'kind':k,'model':None,'target_vol':None} for k in signals}
        for target in (.10,.15):
            for name in names:
                mult=np.zeros(len(p));mult[common]=np.minimum(1,target/np.sqrt(252*predictions[name][common,1]))
                dynamic=base*mult;label=f'{name}_vol{int(target*100)}'
                signals[label]=dynamic;meta[label]={'kind':'dynamic','model':name,'target_vol':target}
                for kind,mask in (('train_static',train),('hindsight_static',None)):
                    if kind=='train_static':ratio=float(dynamic[mask].mean()/base_common[mask].mean())
                    else:
                        dw=delayed_weights(dynamic,1)[first:stop-1]
                        bw=delayed_weights(base_common,1)[first:stop-1]
                        ratio=float(dw.mean()/bw.mean())
                    signals[label+'_'+kind]=base_common*ratio
                    meta[label+'_'+kind]={'kind':kind,'model':name,'target_vol':target,'multiplier':ratio}
        for label,signal in signals.items():
            scenarios=([(.0005,1,0.)] if meta[label]['kind'].endswith('static') else
                       [(c,delay,rf) for c in (.0005,.002) for delay in (1,2) for rf in (0.,.03)])
            for cost,delay,rf in scenarios:
                weights=delayed_weights(signal,delay)[first:stop]
                result=portfolio(o,d,dates,weights,cost=cost,cash_rate=rf)
                rows.append({'base_strategy':base_name,'policy':label,'delay':delay,**meta[label],**result['metrics'],
                             'missing_common_forecast_origins':int((~common[first:stop]).sum()),
                             'exploratory_extension':True})
    return rows


def window_forecast_scores(p,predictions,start,end,eras):
    rows=[]
    for target in ('variance','return_square'):
        for j,h in enumerate(HORIZONS):
            y=future_mean(p[target],h);common=np.isfinite(y)&(p.index>=start)&(p.index<=end)
            for a in predictions.values():common &= np.isfinite(a[:,j])&(a[:,j]>0)
            for era,(lo,hi) in eras.items():
                ids=np.where(common&(p.index>=lo)&(p.index<=hi))[0]
                if not len(ids):continue
                yy=y[ids];cutoff=np.quantile(yy,.99);tail=yy>=cutoff
                for model,a in predictions.items():
                    f=a[ids,j]
                    rows.append({'target':target,'horizon':h,'era':era,'model':model,'n':len(ids),
                                 'qlike':float(qlike(yy,f).mean()),'variance_mse':float(np.mean((yy-f)**2)),
                                 'annualized_vol_mae_pp':float(np.mean(np.abs(np.sqrt(252*yy)-np.sqrt(252*f)))*100),
                                 'underpredict_2x_fraction':float(np.mean(yy>2*f)),
                                 'worst1pct_target_mean_forecast_ratio':float(np.mean(f[tail]/yy[tail])),
                                 'worst1pct_target_group_is_ex_post':True,'exploratory_extension':True})
    return rows


def window_tail_scores(p,predictions,start,end,names):
    rows=[]
    for alpha in (.05,.01):
        values={m:execution_quantiles(p,predictions[m][:,1],alpha) for m in names}
        common=(p.index>=start)&(p.index<=end)
        for y,q,hist in values.values():common &= np.isfinite(y)&np.isfinite(q)&np.isfinite(hist)
        for model,(y,q,hist) in values.items():
            gauss=norm.ppf(alpha)*np.sqrt(predictions[model][:,1])
            for method,a in (('filtered_historical',q),('unscaled_historical',hist),('gaussian',gauss)):
                rows.append({'model':model,'method':method,**coverage_diagnostics(np.where(common,y,np.nan),
                             np.where(common,a,np.nan),alpha),'scale_horizon':5,'holding_clock':'open_t1_to_open_t2',
                             'exploratory_extension':True})
    return rows


def simulate_conditional_variance(state,parameters,eps,signs,paths,seed):
    if paths<1 or len(eps)!=len(signs) or not len(eps) or state<=0:
        raise ValueError('invalid simulation inputs')
    rng=np.random.default_rng(seed);mu=np.full(paths,state);means=[state];p=parameters
    for _ in range(1,20):
        ids=rng.integers(0,len(eps),size=paths)
        shock=mu*eps[ids]
        mu=(p.omega+p.alpha*(shock*(1-p.gamma*signs[ids]))**p.delta+p.beta*mu**p.delta)**(1/p.delta)
        means.append(float(mu.mean()))
    return np.array([np.mean(means[:h]) for h in HORIZONS])


def numerical_precision(p,records,predictions,start='2015-01-01'):
    v,r=p.variance.to_numpy(),p.return_log.to_numpy();rows=[]
    first=np.where(p.index>=start)[0][0]
    for t in range(first,len(p),252):
        eligible=[x for x in records if x['origin']<=t and x['success']]
        if not eligible:continue
        rec=eligible[-1];par=Parameters(**rec['parameters']);begin,end=rec['train_start'],rec['train_end']
        x=v[begin:end+1]/rec['scale'];mu=filter_variance(x,r[begin:end+1],par,1.)
        eps=x[20:]/mu[:-1][20:];eps=eps/eps.mean();signs=np.sign(r[begin:end+1][20:]);state=float(mu[-1])
        if t>end:state=float(filter_variance(v[end+1:t+1]/rec['scale'],r[end+1:t+1],par,state)[-1])
        reference=simulate_conditional_variance(state,par,eps,signs,16384,20261113+t)*rec['scale']
        draws=np.stack([simulate_conditional_variance(state,par,eps,signs,256,20261113+t+rep*100003)
                        *rec['scale'] for rep in range(8)])
        if not np.allclose(draws[0],predictions[t],rtol=1e-12,atol=1e-15):
            raise ValueError('simulation reconstruction differs from original forecast')
        for j,h in enumerate(HORIZONS):
            rows.append({'origin':str(p.index[t].date()),'horizon':h,'reference_paths':16384,
                         'original_paths':256,'seed_repetitions':8,
                         'seed_coefficient_of_variation':float(draws[:,j].std(ddof=1)/draws[:,j].mean()),
                         'max_absolute_relative_difference_to_reference':float(np.max(np.abs(draws[:,j]/reference[j]-1))),
                         'original_absolute_relative_difference_to_reference':float(abs(draws[0,j]/reference[j]-1)),
                         'not_market_prediction_interval':True})
    return rows
