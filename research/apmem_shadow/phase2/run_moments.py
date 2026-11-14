"""Reconstruct numerical repair and test a single exact fixed-power control."""
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from .__main__ import save,digest
from .targets import HORIZONS
from .moments import replay_moments,fixed_power_forecasts,fit_context,moment_projection
from .extensions import window_forecast_scores,window_utility,window_tail_scores,simulate_conditional_variance
from .evaluation import ERAS
from .calibration import variance_upper
from .consumer import research_context
from research.apmem_shadow.model import filter_variance


def reference_comparison(p,records,estimate,lower,upper,start):
    v,r=p.variance.to_numpy(),p.return_log.to_numpy();rows=[]
    first=int(np.where(p.index>=start)[0][0])
    for t in range(first,len(p),252):
        eligible=[rec for rec in records if rec['origin']<=t]
        if not eligible or not eligible[-1]['success']:continue
        rec=eligible[-1];par,state,a=fit_context(v,r,rec);end=rec['train_end']
        begin=rec['train_start'];x=v[begin:end+1]/rec['scale'];mu=filter_variance(x,r[begin:end+1],par,1.)
        eps=x[20:]/mu[:-1][20:];eps/=eps.mean();signs=np.sign(r[begin:end+1][20:])
        if t>end:state=float(filter_variance(v[end+1:t+1]/rec['scale'],r[end+1:t+1],par,state)[-1])
        reference=simulate_conditional_variance(state,par,eps,signs,65536,20261113+t)*rec['scale']
        for j,h in enumerate(HORIZONS):
            rows.append({'origin':str(p.index[t].date()),'horizon':h,'reference_paths':65536,
                         'moment_estimate':float(estimate[t,j]),'conditional_mean_lower':float(lower[t,j]),
                         'conditional_mean_upper':float(upper[t,j]),'simulation_reference':float(reference[j]),
                         'approximation_relative_difference_to_simulation':float(estimate[t,j]/reference[j]-1),
                         'relative_bound_width':float((upper[t,j]-lower[t,j])/estimate[t,j]),
                         'reference_inside_analytic_bounds':bool(lower[t,j]-1e-12<=reference[j]<=upper[t,j]+1e-12),
                         'simulation_reference_is_not_exact_truth':True})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.study_root;out=args.output
    if out.exists():raise SystemExit('output exists; inspect original operation')
    out.mkdir(parents=True);started=datetime.now(timezone.utc).isoformat()
    paths=[]
    for parent in ('results','sector_results'):
        paths.extend((p.parent.name,p.parent,False) for p in (root/parent).glob('*/summary.json'))
    paths.append(('SPY_EARLY',root/'extensions',True))
    all_scores,all_utility,all_tails,all_reference,bounds_summary,fit_summary=[],[],[],[],[],[]
    inputs={}
    for label,directory,early in paths:
        observed=datetime.now(timezone.utc).isoformat()
        file=directory/('early_SPY_prepared_prices.parquet' if early else 'prepared_prices.parquet')
        p=pd.read_parquet(file)
        old=dict(np.load(directory/('early_SPY_predictions.npz' if early else 'predictions.npz')))
        logs=json.loads((directory/('early_SPY_fit_log.json' if early else 'fit_log.json')).read_text())
        records=logs['apmem'];v,r=p.variance.to_numpy(),p.return_log.to_numpy()
        moment,lo,hi,diag=replay_moments(v,r,records)
        valid=np.isfinite(old['apmem'][:,0])&np.isfinite(moment[:,0])
        if not np.allclose(moment[valid,0],old['apmem'][valid,0],rtol=1e-11,atol=1e-14):
            raise ValueError('reconstructed exact H1 differs from original')
        linear,linear_logs,linear_diag=fixed_power_forecasts(v,r)
        pred={'apmem_256':old['apmem'],'apmem_moment':moment,'mem_delta1':linear,
              'equal_256':old['equal_blend'],'equal_moment':(moment+old['ewma94']+old['har_extended'])/3,
              'ewma94':old['ewma94'],'har_extended':old['har_extended']}
        start,end=('1998-01-01','2009-12-31') if early else ('2015-01-01','2026-11-12')
        eras=({'all':(start,end),'1998_2002':(start,'2002-12-31'),'2003_2006':('2003-01-01','2006-12-31'),
               '2007_2009':('2007-01-01',end)} if early else ERAS)
        all_scores.extend({'instrument':label,'comparison':'full_no_options',**x}
                          for x in window_forecast_scores(p,pred,start,end,eras))
        all_utility.extend({'instrument':label,'comparison':'full_no_options',**x}
                          for x in window_utility(p,pred,start,tuple(pred),end=end))
        all_tails.extend({'instrument':label,'comparison':'full_no_options',**x}
                          for x in window_tail_scores(p,pred,start,str(p.index[-3].date()),
                                                      ('apmem_256','apmem_moment','mem_delta1','equal_moment')))
        all_reference.extend({'instrument':label,**x} for x in reference_comparison(p,records,moment,lo,hi,start))
        good=(p.index>=start)&np.isfinite(moment).all(axis=1)
        for j,h in enumerate(HORIZONS):
            width=(hi[good,j]-lo[good,j])/moment[good,j]
            bounds_summary.append({'instrument':label,'horizon':h,'n':len(width),
                'median_relative_bound_width':float(np.median(width)),'p95_relative_bound_width':float(np.quantile(width,.95)),
                'max_relative_bound_width':float(width.max()),'fraction_width_over_10pct':float(np.mean(width>.1)),
                'bounds_are_market_prediction_intervals':False})
        fit_summary.append({'instrument':label,'linear_fits':len(linear_logs),
                            'linear_successful':sum(x['success'] for x in linear_logs),
                            'moment_projection_failures':len(diag['failures']),
                            'moment_fits_with_variance_mean_coefficient_ge1':sum(not x['variance_mean_stationarity_diagnostic'] for x in diag['fit_diagnostics']),
                            'linear_fits_with_mean_coefficient_ge1':sum(not x['variance_mean_stationarity_diagnostic'] for x in linear_diag['fit_diagnostics'])})
        if label in ('QQQ','SPY','IWM'):
            iv=dict(np.load(root/'followup'/(label+'_options_predictions.npz')))['har_iv']
            op={'apmem_256':old['apmem'],'apmem_moment':moment,'mem_delta1':linear,'har_iv':iv,
                'moment_iv_half':(moment+iv)/2,'linear_iv_half':(linear+iv)/2,
                'original_iv_half':(old['apmem']+iv)/2}
            all_scores.extend({'instrument':label,'comparison':'options_common',**x}
                              for x in window_forecast_scores(p,op,start,end,eras))
            all_utility.extend({'instrument':label,'comparison':'options_common',**x}
                              for x in window_utility(p,op,'2021-01-01',tuple(op)))
            all_tails.extend({'instrument':label,'comparison':'options_common',**x}
                              for x in window_tail_scores(p,op,'2021-01-01',end,
                                                          ('original_iv_half','moment_iv_half','linear_iv_half')))
            np.savez_compressed(out/(label+'_options_predictions.npz'),**op)
        np.savez_compressed(out/(label+'_predictions.npz'),**pred,conditional_mean_lower=lo,conditional_mean_upper=hi)
        save(out/(label+'_moments_log.json'),diag);save(out/(label+'_fixed_power_fits.json'),linear_logs)
        inputs[label]={'prepared_prices_sha256':digest(file),'original_fit_log_sha256':digest(directory/('early_SPY_fit_log.json' if early else 'fit_log.json'))}
        if label=='QQQ':
            forecast=pred['equal_moment'][-1]
            upper90=[variance_upper(v,pred['equal_moment'][:,j],h)[-1] for j,h in enumerate(HORIZONS)]
            last_har={h:[x for x in logs['har_extended'] if x['horizon']==h][-1] for h in HORIZONS}
            cutoffs={'apmem':str(p.index[records[-1]['train_end']].date()),
                     **{f'har_h{h}':str(p.index[rec['latest_label_endpoint']].date()) for h,rec in last_har.items()}}
            computed=datetime.now(timezone.utc).isoformat()
            context=research_context(instrument='QQQ',origin_session=str(p.index[-1].date()),forecast=forecast,
                upper90=upper90,decision_at=computed,observed_at=observed,computed_at=computed,source_sha256=digest(file),
                fit_cutoffs=cutoffs,state_last_session=str(p.index[-1].date()))
            context['observed_clock_meaning']='Actual file read in this research run; not historical vendor publication'
            context['numerical_method']='deterministic two-moment approximation plus HAR/EWMA'
            context['current_conditional_mean_approximation_bound_width']=(hi[-1]-lo[-1]).tolist()
            save(out/'QQQ_reconstructed_research_context.json',context)
        print('DETERMINISTIC_REPAIR_COMPLETE',label,fit_summary[-1],flush=True)
    for name,rows in (('forecast_scores',all_scores),('utility',all_utility),('tail_calibration',all_tails),
                      ('numerical_reference',all_reference),('analytic_bound_summary',bounds_summary)):
        pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    save(out/'run_receipt.json',{'schema':'mastermind.volatility_numerical_repair.v1','started_at':started,
        'ended_at':datetime.now(timezone.utc).isoformat(),'inputs':inputs,'fits':fit_summary,
        'source_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
        'original_fits_refitted':False,'fixed_power_new_selected_fits':sum(x['linear_fits'] for x in fit_summary),
        'forecast_score_rows':len(all_scores),'utility_scenarios':len(all_utility),'reference_checks':len(all_reference),
        'exploratory_after_numerical_defect':True,'prospective':False,'may_trade':False})


if __name__=='__main__':main()
