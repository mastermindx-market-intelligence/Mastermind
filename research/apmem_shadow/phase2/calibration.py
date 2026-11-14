"""Sequential calibration diagnostics, not financial coverage guarantees."""
from __future__ import annotations
import numpy as np
from scipy.special import xlogy
from scipy.stats import chi2, norm
from .targets import FLOOR, future_mean


def wilson(k: int,n: int,z: float = 1.959963984540054) -> list[float]:
    if n < 1 or not 0 <= k <= n:
        raise ValueError("invalid binomial counts")
    p = k/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    delta = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [float(center-delta),float(center+delta)]


def coverage_diagnostics(actual: np.ndarray,quantile: np.ndarray,alpha: float) -> dict:
    actual,quantile = np.asarray(actual,float),np.asarray(quantile,float)
    if actual.ndim != 1 or actual.shape != quantile.shape or not 0 < alpha < 1:
        raise ValueError("invalid coverage inputs")
    mask = np.isfinite(actual)&np.isfinite(quantile)
    r,q = actual[mask],quantile[mask]
    if not len(r):
        return {"n":0}
    hit = r < q
    n,k = len(hit),int(hit.sum())
    p = k/n
    ll_null = xlogy(k,alpha)+xlogy(n-k,1-alpha)
    ll_fit = xlogy(k,p)+xlogy(n-k,1-p)
    lr = max(0.0,float(2*(ll_fit-ll_null)))
    # Do not bridge missing forecasts in the dependence diagnostic.
    adj = mask[:-1]&mask[1:]
    hfull = np.zeros(len(mask),bool)
    hfull[mask] = hit
    a,b = hfull[:-1][adj],hfull[1:][adj]
    n00,n01 = int((~a&~b).sum()),int((~a&b).sum())
    n10,n11 = int((a&~b).sum()),int((a&b).sum())
    lr_ind,ind_p = None,None
    if n00+n01 and n10+n11:
        p01,p11 = n01/(n00+n01),n11/(n10+n11)
        pooled = (n01+n11)/(n00+n01+n10+n11)
        lli = (xlogy(n00,1-pooled)+xlogy(n01,pooled)+xlogy(n10,1-pooled)+xlogy(n11,pooled))
        llm = (xlogy(n00,1-p01)+xlogy(n01,p01)+xlogy(n10,1-p11)+xlogy(n11,p11))
        lr_ind = max(0.0,float(2*(llm-lli)))
        ind_p = float(chi2.sf(lr_ind,1))
    residual = r-q
    loss = np.where(residual >= 0,alpha*residual,(alpha-1)*residual)
    return {"n":n,"alpha":alpha,"violations":k,"violation_fraction":p,
            "wilson_interval_iid_reference_only":wilson(k,n),
            "mean_pinball_loss":float(loss.mean()),"mean_quantile":float(q.mean()),
            "kupiec_lr":lr,"kupiec_asymptotic_p":float(chi2.sf(lr,1)),
            "transition_counts":[n00,n01,n10,n11],"independence_lr":lr_ind,
            "independence_asymptotic_p":ind_p,"formal_validity_under_shift":False}


def return_quantiles(r: np.ndarray,forecast: np.ndarray,*,alpha: float,
                     window: int = 504,minimum: int = 252) -> dict[str,np.ndarray]:
    """q[t] predicts r[t+1]; residuals use origins at most t-1."""
    r,f = np.asarray(r,float),np.asarray(forecast,float)
    if r.ndim != 1 or r.shape != f.shape or not 0 < alpha < .5 or minimum > window:
        raise ValueError("invalid calibration settings")
    n = len(r)
    residuals = np.full(n,np.nan)
    valid = np.isfinite(f[:-1])&(f[:-1] > 0)&np.isfinite(r[1:])
    ids = np.where(valid)[0]
    residuals[ids] = r[ids+1]/np.sqrt(f[ids])
    empirical,gaussian,historical = (np.full(n,np.nan) for _ in range(3))
    for t in range(n):
        past = r[max(0,t-window+1):t+1]
        past = past[np.isfinite(past)]
        if len(past) >= minimum:
            historical[t] = np.quantile(past,alpha,method="linear")
        if not np.isfinite(f[t]) or f[t] <= 0:
            continue
        gaussian[t] = norm.ppf(alpha)*np.sqrt(f[t])
        z = residuals[max(0,t-window):t]
        z = z[np.isfinite(z)]
        if len(z) >= minimum:
            empirical[t] = np.quantile(z,alpha,method="linear")*np.sqrt(f[t])
    return {"filtered_historical":empirical,"gaussian":gaussian,"unscaled_historical":historical}


def variance_upper(v: np.ndarray,forecast: np.ndarray,horizon: int,*,
                   probability: float = .9,window: int = 504,minimum: int = 252) -> np.ndarray:
    if not 0 < probability < 1 or minimum > window:
        raise ValueError("invalid envelope settings")
    y,f = future_mean(v,horizon),np.asarray(forecast,float)
    if y.shape != f.shape:
        raise ValueError("envelope shape mismatch")
    out = np.full(len(f),np.nan)
    for t in range(len(f)):
        if not np.isfinite(f[t]) or f[t] <= 0:
            continue
        ids = np.arange(max(0,t-horizon-window+1),t-horizon+1)
        ids = ids[np.isfinite(y[ids])&np.isfinite(f[ids])&(f[ids] > 0)]
        if len(ids) >= minimum:
            out[t] = f[t]*np.quantile(np.maximum(y[ids],FLOOR)/f[ids],probability,method="linear")
    return out
