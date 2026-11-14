"""Seed-free forecasts, analytic conditional-mean bounds, and a fixed-power control.

Moment bounds concern the assumed empirical recursion, NOT realized market paths.
The fractional-power point estimate is a lognormal two-moment approximation.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from research.apmem_shadow.model import Parameters, Fit, filter_variance, vector
from .targets import HORIZONS
from .forecasts import Settings


def transition_coefficients(parameters, innovations, signs):
    p=parameters;p.validate()
    e,s=vector(innovations,'innovations',positive=True),vector(signs,'signs')
    if len(e)!=len(s) or not np.isin(s,[-1.,0.,1.]).all():
        raise ValueError('invalid empirical innovation/sign pairs')
    with np.errstate(over='ignore',invalid='ignore'):
        a=p.alpha*(e*(1-p.gamma*s))**p.delta+p.beta
    if not np.isfinite(a).all() or (a<=0).any():raise ValueError('invalid transition coefficients')
    return a


def moment_projection(state, parameters, coefficients, horizons=HORIZONS):
    """Return approximation/lower/upper means at declared horizons.

    m1,m2 are exact moments of powered variance under independent empirical
    transitions. Fractional E[X**p] is approximated, with valid moment bounds.
    """
    parameters.validate()
    a=vector(coefficients,'coefficients',positive=True)
    if (not np.isfinite(state) or state<=0 or not .5<=parameters.delta<=2
            or not horizons or any(not isinstance(h,int) or h<1 for h in horizons)):
        raise ValueError('invalid moment forecast arguments')
    power=1/parameters.delta
    la=np.log(a);lmean=float(logsumexp(la)-np.log(len(a)))
    lsecond=float(logsumexp(2*la)-np.log(len(a)))
    lpmean=float(logsumexp(power*la)-np.log(len(a)))
    lw=np.log(parameters.omega)
    lm=parameters.delta*np.log(state);lm2=2*lm
    estimates=[];lower=[];upper=[]
    for step in range(max(horizons)):
        if step:
            old=lm
            lm=float(np.logaddexp(lw,lmean+lm))
            lm2=float(logsumexp([2*lw,np.log(2.)+lw+lmean+old,lsecond+lm2]))
        spread=max(0.,lm2-2*lm)
        if abs(power-1)<1e-12:
            lo=hi=estimate=lm
        elif abs(power-2)<1e-12:
            lo=hi=estimate=lm2
        elif power<1:
            lo=(2-power)*lm-(1-power)*lm2;hi=power*lm
            estimate=power*lm+.5*power*(power-1)*spread
        else:
            lo=power*lm;hi=(2-power)*lm+(power-1)*lm2
            estimate=power*lm+.5*power*(power-1)*spread
        if not lo-1e-12<=estimate<=hi+1e-12:
            raise ValueError('moment approximation violates its analytic bounds')
        estimates.append(estimate);lower.append(lo);upper.append(hi)
    with np.errstate(over='ignore',under='ignore'):
        values=[np.exp([logsumexp(x[:h])-np.log(h) for h in horizons]) for x in (estimates,lower,upper)]
    if not np.isfinite(values).all() or (np.asarray(values)<=0).any():
        raise ValueError('nonfinite moment forecast')
    diag={'power':power,'mean_power_state_coefficient':float(np.exp(lmean)),
          'second_power_state_coefficient':float(np.exp(lsecond)),
          'variance_mean_moment_coefficient':float(np.exp(lpmean)),
          'variance_mean_stationarity_diagnostic':bool(lpmean<0),
          'point_estimate_exact_under_empirical_recursion':bool(abs(power-1)<1e-12 or abs(power-2)<1e-12),
          'bounds_are_market_prediction_intervals':False}
    return values[0],values[1],values[2],diag


def fit_context(v,r,record):
    """Verify original input digest and rebuild the originally fitted filter state."""
    begin,end=record['train_start'],record['train_end']
    if end!=record['origin'] or begin<0 or end>=len(v) or begin>end:
        raise ValueError('invalid saved fit clock')
    data=np.column_stack([v[begin:end+1],r[begin:end+1]]).astype('<f8')
    if hashlib.sha256(data.tobytes()).hexdigest()!=record['input_sha256']:
        raise ValueError('saved fit training-input digest mismatch')
    p=Parameters(**record['parameters']);scale=record['scale']
    x=v[begin:end+1]/scale
    mu=filter_variance(x,r[begin:end+1],p,1.)
    eps=x[20:]/mu[:-1][20:];eps/=eps.mean()
    signs=np.sign(r[begin:end+1][20:])
    return p,float(mu[-1]),transition_coefficients(p,eps,signs)


def replay_moments(v,r,records):
    v,r=vector(v,'variance',positive=True),vector(r,'returns')
    if len(v)!=len(r):raise ValueError('mismatched observations')
    if any(records[i]['origin']>=records[i+1]['origin'] for i in range(len(records)-1)):
        raise ValueError('saved fits not in strictly increasing order')
    by_origin={row['origin']:row for row in records}
    out,lower,upper=(np.full((len(v),3),np.nan) for _ in range(3))
    state=None;p=None;coeff=None;scale=None;diagnostics=[];failures=[]
    for t in range(len(v)):
        if t in by_origin:
            rec=by_origin[t];state=None
            if rec['success']:
                p,state,coeff=fit_context(v,r,rec);scale=rec['scale']
                _,_,_,diag=moment_projection(state,p,coeff)
                diagnostics.append({'origin':t,**diag})
        elif state is not None:
            try:state=float(filter_variance([v[t]/scale],[r[t]],p,state)[-1])
            except ValueError as exc:
                failures.append({'origin':t,'kind':'state','error':str(exc)});state=None
        if state is not None:
            try:
                a,lo,hi,_=moment_projection(state,p,coeff)
                out[t],lower[t],upper[t]=a*scale,lo*scale,hi*scale
            except ValueError as exc:
                failures.append({'origin':t,'kind':'projection','error':str(exc)})
    return out,lower,upper,{'fit_diagnostics':diagnostics,'failures':failures,'original_fits_refitted':False}


def fit_fixed_power(v,r,maxiter=400):
    """Exactly delta=1; four-parameter QML, same training objective and two starts."""
    v,r=vector(v,'variance',positive=True),vector(r,'returns')
    if len(v)!=len(r) or len(v)<64 or maxiter<1:raise ValueError('invalid fixed-power fit data')
    scale=float(v.mean());x=v/scale
    digest=hashlib.sha256(np.column_stack([v,r]).astype('<f8').tobytes()).hexdigest()
    bounds=[(-9.,2.),(1e-5,.6),(1e-5,.995),(-.95,.95)]
    starts=[(np.log(.03),.1,.85,.1),(np.log(.05),.05,.9,.25)]
    def unpack(theta):return Parameters(float(np.exp(theta[0])),*map(float,theta[1:]),1.)
    def objective(theta):
        try:
            mu=filter_variance(x,r,unpack(theta),1.)[:-1]
            value=.5*np.mean(np.log(mu[20:])+x[20:]/mu[20:])
            return float(value) if np.isfinite(value) else 1e100
        except (ValueError,FloatingPointError,OverflowError):return 1e100
    candidates=[];attempts=[]
    for initial in starts:
        result=minimize(objective,initial,method='L-BFGS-B',bounds=bounds,
                        options={'maxiter':maxiter,'ftol':1e-10,'gtol':1e-6,'maxls':40})
        ok=bool(result.success and np.isfinite(result.fun) and result.fun<1e90)
        attempts.append({'success':ok,'message':str(result.message),'iterations':int(result.nit),'evaluations':int(result.nfev)})
        if ok:candidates.append(result)
    if not candidates:return Fit(None,scale,None,False,len(v),digest,tuple(attempts))
    best=min(candidates,key=lambda z:z.fun);p=unpack(best.x)
    mu=filter_variance(x,r,p,1.)[:-1];eps=x[20:]/mu[20:]
    persistence=float(p.alpha*np.mean(eps*(1-p.gamma*np.sign(r[20:])))+p.beta)
    names=('log_omega','alpha','beta','gamma')
    edge=tuple(k for k,z,(lo,hi) in zip(names,best.x,bounds) if min(abs(z-lo),abs(z-hi))<1e-4)
    return Fit(p,scale,float(best.fun),True,len(v),digest,tuple(attempts),persistence,edge)


def fixed_power_forecasts(v,r,config=Settings()):
    config.validate();v,r=vector(v,'variance',positive=True),vector(r,'returns')
    if len(v)!=len(r):raise ValueError('mismatched observations')
    records=[]
    for t in range(config.minimum-1,len(v),config.apmem_refit):
        begin=max(0,t-config.window+1)
        fit=fit_fixed_power(v[begin:t+1],r[begin:t+1])
        records.append({'origin':t,'train_start':begin,'train_end':t,**fit.record(),'power_fixed':1.})
    out,lower,upper,diagnostics=replay_moments(v,r,records)
    good=np.isfinite(out)
    if not (np.array_equal(out[good],lower[good]) and np.array_equal(out[good],upper[good])):
        raise ValueError('fixed-power mean is not exact')
    return out,records,diagnostics
