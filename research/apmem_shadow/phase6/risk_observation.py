"""Bind the previously tested exact-power volatility model to a fresh observation.

The source is imported unchanged from the pinned phase2 dependency. Exact refers
only to its empirical moment recursion, never certainty about market outcomes.
"""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd


class FixedRiskOwner:
    def __init__(self,root):
        self.root=Path(root).resolve();manifest=json.loads((self.root/'SOURCE_MANIFEST.json').read_text())
        if manifest['ref']!='f7f7dcb381c7cf1b19ceb1af6b367818268d9155':raise ValueError('Unexpected volatility source revision')
        for path,info in manifest['files'].items():
            if hashlib.sha256((self.root/path).read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Volatility source drift')
        sys.path.insert(0,str(self.root))
        from research.apmem_shadow.phase2 import targets,moments
        from research.apmem_shadow import model
        for module in [targets,moments,model]:
            if not Path(module.__file__).resolve().is_relative_to(self.root):raise ValueError('Unexpected volatility import owner')
        self.targets=targets;self.moments=moments;self.manifest=manifest
    def observe(self,prices,origin,window=504):
        if window!=504:raise ValueError('Frozen fit-window changed')
        if str(prices.index[-1].date())!=origin:raise ValueError('Volatility origin mismatch')
        prepared=self.targets.prepare_prices(prices)
        if len(prepared)<window:raise ValueError('Insufficient fixed-model history')
        training=prepared.iloc[-window:];v=training.variance.to_numpy(float);r=training.return_log.to_numpy(float)
        fit=self.moments.fit_fixed_power(v,r)
        record=fit.record();record.update(origin=len(v)-1,train_start=0,train_end=len(v)-1)
        result={'source_revision':self.manifest['ref'],'model':'fixed_power_MEM_delta1_empirical_moments',
          'origin':origin,'training_start':str(training.index[0].date()),'training_end':str(training.index[-1].date()),
          'training_rows':len(training),'target':'daily_range_plus_distribution_adjusted_overnight_variance',
          'variance_units':'squared_daily_return','volatility_units':'annualized_decimal_252_sessions',
          'fit':record,'status':'FIT_FAILED','forecasts':None,'bounds_are_prediction_intervals':False,
          'historical_accuracy_claimed_for_new_roster':False,'may_rank':False,'may_size':False,'may_trade':False}
        # Fixed EWMA forecast is a comparator on the SAME measured target.
        ew=float(v[0])
        for value in v[1:]:ew=.94*ew+.06*float(value)
        result['comparator']={'model':'EWMA_0.94','horizons':[1,5,20],
          'mean_daily_variance':[ew]*3,'annualized_volatility':[float(np.sqrt(252*ew))]*3}
        if not fit.success:return result
        p,state,coefficients=self.moments.fit_context(v,r,record)
        estimated,lower,upper,diagnostic=self.moments.moment_projection(state,p,coefficients)
        means=estimated*fit.scale
        if not np.isfinite(means).all() or (means<=0).any():raise ValueError('Invalid risk forecast')
        result.update(status='RECORDED_RESEARCH',forecasts={'horizons':[1,5,20],
          'mean_daily_variance':means.tolist(),'annualized_volatility':np.sqrt(252*means).tolist()},
          diagnostics=diagnostic,point_mean_exact_under_empirical_recursion=bool(np.array_equal(estimated,lower) and np.array_equal(estimated,upper)))
        return result


def validate_risk_record(record,origin):
    if record.get('origin')!=origin or record.get('training_end')!=origin:raise ValueError('Risk clock mismatch')
    if any(record.get(k) is not False for k in ['may_rank','may_size','may_trade']):raise ValueError('Forecast cannot grant capital authority')
    if record.get('bounds_are_prediction_intervals') is not False:raise ValueError('False loss-coverage claim')
    if record.get('variance_units')!='squared_daily_return' or record.get('volatility_units')!='annualized_decimal_252_sessions':raise ValueError('Ambiguous risk units')
    if record.get('status') not in ('FIT_FAILED','RECORDED_RESEARCH'):raise ValueError('Unknown forecast state')
    if record.get('status')=='FIT_FAILED':
        if record.get('forecasts') is not None:raise ValueError('Failed fit contains fabricated prediction')
        return
    forecast=record.get('forecasts',{})
    if forecast.get('horizons')!=[1,5,20]:raise ValueError('Unexpected risk horizon')
    variance=np.asarray(forecast.get('mean_daily_variance'),float);vol=np.asarray(forecast.get('annualized_volatility'),float)
    if variance.shape!=(3,) or vol.shape!=(3,) or not np.isfinite(variance).all() or (variance<=0).any():raise ValueError('Malformed variance')
    if not np.allclose(vol,np.sqrt(252*variance),rtol=1e-10,atol=1e-12):raise ValueError('Volatility convention mismatch')
