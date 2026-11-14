"""Training-only multi-horizon forecasts with fixed, bounded combinations."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import numpy as np
from scipy.optimize import minimize
from scipy.special import softmax
from research.apmem_shadow.model import fit_qml, filter_variance
from .targets import FLOOR, HORIZONS, causal_features, future_mean


@dataclass(frozen=True)
class Settings:
    minimum: int = 504
    window: int = 1260
    refit: int = 21
    apmem_refit: int = 63
    ridge: float = .001
    paths: int = 256
    seed: int = 20261113

    def validate(self) -> None:
        vals = (self.minimum, self.window, self.refit, self.apmem_refit, self.paths, self.seed)
        if (any(not isinstance(v, int) for v in vals) or self.minimum < 64
                or self.window < self.minimum or self.refit < 1 or self.apmem_refit < 1
                or self.paths < 16 or self.seed < 0 or not np.isfinite(self.ridge) or self.ridge < 0):
            raise ValueError("invalid forecast settings")


def qlike(y: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Normalized QLIKE; common small floor only for zero outcome proxies."""
    y, f = np.asarray(y, float), np.asarray(f, float)
    if y.shape != f.shape or (y < 0).any() or (f <= 0).any():
        raise ValueError("invalid QLIKE shapes or signs")
    if not (np.isfinite(y).all() and np.isfinite(f).all()):
        raise ValueError("nonfinite QLIKE input")
    ratio = np.maximum(y, FLOOR)/f
    return ratio - np.log(ratio) - 1


def loglink_fit(x: np.ndarray, y: np.ndarray, ridge: float) -> dict:
    """Convex log-link QLIKE regression, fixed standardized slope regularization."""
    if (x.ndim != 2 or y.ndim != 1 or len(x) != len(y) or len(y) < 32
            or not np.isfinite(x).all() or not np.isfinite(y).all() or (y <= 0).any()
            or not np.isfinite(ridge) or ridge < 0):
        raise ValueError("invalid regression training data")
    center, spread = x.mean(axis=0), x.std(axis=0)
    spread = np.where(spread > 1e-10, spread, 1.0)
    z = np.column_stack([np.ones(len(x)), np.clip((x-center)/spread, -8, 8)])
    scale = float(y.mean())
    scaled = y/scale

    def objective(b: np.ndarray) -> tuple[float, np.ndarray]:
        eta = z@b
        with np.errstate(over="ignore", invalid="ignore"):
            ratio = scaled*np.exp(-eta)
            score = np.mean(eta+ratio) + ridge*.5*np.sum(b[1:]**2)
            grad = z.T@(1-ratio)/len(y)+np.r_[0.0, ridge*b[1:]]
        return float(score), grad

    result = minimize(objective, np.zeros(z.shape[1]), jac=True, method="L-BFGS-B",
                      bounds=[(-15, 15)]+[(-4, 4)]*x.shape[1],
                      options={"maxiter":300,"ftol":1e-10,"gtol":1e-6,"maxls":40})
    ok = bool(result.success and np.isfinite(result.fun) and np.isfinite(result.x).all())
    return {"success":ok,"beta":result.x,"center":center,"spread":spread,
            "scale":scale,"objective":float(result.fun),"iterations":int(result.nit),
            "message":str(result.message),
            "coefficient_boundary":bool(np.any(np.abs(result.x[1:]) >= 3.9999))}


def loglink_predict(fit: dict, x: np.ndarray) -> tuple[np.ndarray, int]:
    z0 = (x-fit["center"])/fit["spread"]
    z = np.column_stack([np.ones(len(x)), np.clip(z0, -8, 8)])
    with np.errstate(over="ignore", invalid="ignore"):
        pred = fit["scale"]*np.exp(z@fit["beta"])
    return pred, int(np.sum(np.any(np.abs(z0) > 8, axis=1)))


def direct_har(features: np.ndarray, v: np.ndarray, horizon: int,
               config: Settings) -> tuple[np.ndarray, list[dict]]:
    """A fit at t admits direct-horizon training origins only through t-h."""
    config.validate()
    if features.ndim != 2 or len(features) != len(v) or horizon not in HORIZONS:
        raise ValueError("invalid direct forecast inputs")
    n = len(v)
    y, out = future_mean(v, horizon), np.full(n, np.nan)
    logs = []
    last_attempt, fit = -config.refit, None
    finite_x = np.isfinite(features).all(axis=1)
    for t in range(config.minimum+horizon-1, n):
        if t-last_attempt >= config.refit:
            end = t-horizon
            ids = np.arange(max(0,end-config.window+1),end+1)
            ids = ids[finite_x[ids] & np.isfinite(y[ids]) & (y[ids] > 0)]
            if len(ids) >= config.minimum:
                last_attempt = t
                fit = loglink_fit(features[ids], y[ids], config.ridge)
                logs.append({"origin":t,"horizon":horizon,"rows":len(ids),
                             "first_train_origin":int(ids[0]),"last_train_origin":int(ids[-1]),
                             "latest_label_endpoint":int(ids[-1]+horizon),
                             **{k:fit[k] for k in ("success","objective","iterations","message","coefficient_boundary")},
                             "prediction_feature_clips":0})
        if fit is not None and fit["success"] and finite_x[t]:
            pred, clips = loglink_predict(fit, features[t:t+1])
            logs[-1]["prediction_feature_clips"] += clips
            if np.isfinite(pred[0]) and pred[0] > 0:
                out[t] = pred[0]
    return out, logs


def apmem_paths(v: np.ndarray, r: np.ndarray, config: Settings
                ) -> tuple[np.ndarray, list[dict]]:
    """Nonlinear multi-step simulation with training-only innovation/sign pairs.

    H1 is exact conditional mean. Later horizons average simulated conditional
    variances. Paired empirical innovations are normalized to mean one, preserving
    their observed dependence with return signs. This is not a tail guarantee.
    """
    config.validate()
    n = len(v)
    if len(r) != n or not np.isfinite(np.r_[v,r]).all() or (v <= 0).any():
        raise ValueError("invalid APMEM observations")
    out = np.full((n,len(HORIZONS)),np.nan)
    records, fit, state, eps, signs = [], None, None, None, None
    for t in range(config.minimum-1,n):
        if (t-(config.minimum-1)) % config.apmem_refit == 0:
            start = max(0,t-config.window+1)
            fit = fit_qml(v[start:t+1],r[start:t+1])
            rec = {"origin":t,"train_start":start,"train_end":t,**fit.record()}
            records.append(rec)
            if fit.success:
                x = v[start:t+1]/fit.scale
                mu = filter_variance(x,r[start:t+1],fit.parameters,1.0)
                state = float(mu[-1])
                eps = x[20:]/mu[:-1][20:]
                rec["empirical_innovation_mean_before_normalization"] = float(eps.mean())
                eps = eps/eps.mean()
                signs = np.sign(r[start:t+1][20:])
            else:
                state = None
        elif fit is not None and fit.success and state is not None:
            try:
                state = float(filter_variance([v[t]/fit.scale],[r[t]],fit.parameters,state)[-1])
            except ValueError:
                state = None
                records[-1]["filter_failure_at"] = t
        if fit is None or not fit.success or state is None:
            continue
        p = fit.parameters
        rng = np.random.default_rng(config.seed+t)
        simulated, means = np.full(config.paths,state), [state]
        for _ in range(1,max(HORIZONS)):
            ids = rng.integers(0,len(eps),size=config.paths)
            with np.errstate(over="ignore",invalid="ignore"):
                shock = simulated*eps[ids]
                simulated = (p.omega+p.alpha*(shock*(1-p.gamma*signs[ids]))**p.delta
                             +p.beta*simulated**p.delta)**(1/p.delta)
            means.append(float(simulated.mean()))
        for j,h in enumerate(HORIZONS):
            value = np.mean(means[:h])*fit.scale
            if np.isfinite(value) and value > 0:
                out[t,j] = value
            else:
                records[-1]["nonfinite_simulation_origins"] = records[-1].get("nonfinite_simulation_origins",0)+1
    return out, records


def combine(predictions: dict[str,np.ndarray], v: np.ndarray,
            components: tuple[str,...] = ("ewma94","har_extended","apmem"),
            lookback: int = 252, minimum: int = 63) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    f = np.stack([predictions[k] for k in components],axis=2)
    n, nh, nc = f.shape
    eq, ada = np.full((n,nh),np.nan), np.full((n,nh),np.nan)
    weights = np.full((n,nh,nc),np.nan)
    for j,h in enumerate(HORIZONS):
        y = future_mean(v,h)
        for t in range(n):
            if not np.isfinite(f[t,j]).all() or (f[t,j] <= 0).any():
                continue
            w = np.full(nc,1/nc)
            ids = np.arange(max(0,t-h-lookback+1),t-h+1)
            if len(ids):
                ids = ids[np.isfinite(f[ids,j]).all(axis=1) & np.isfinite(y[ids])]
                if len(ids) >= minimum:
                    loss = np.column_stack([qlike(y[ids],f[ids,j,k]) for k in range(nc)])
                    means = loss.mean(axis=0)
                    w = .5/nc+.5*softmax(-2*(means-means.min()))
            eq[t,j], ada[t,j], weights[t,j] = f[t,j].mean(),f[t,j]@w,w
    return eq,ada,weights


def forecast_all(p, config: Settings = Settings(), options=None, instrument=None):
    config.validate()
    v,r = p.variance.to_numpy(),p.return_log.to_numpy()
    predictions = {}
    for name,series in (("incumbent",p.incumbent_variance),
                        ("mean20",p.variance.rolling(20).mean()),
                        ("ewma94",p.variance.ewm(alpha=.06,adjust=False).mean()),
                        ("ewma97",p.variance.ewm(alpha=.03,adjust=False).mean())):
        predictions[name] = np.repeat(series.to_numpy()[:,None],len(HORIZONS),axis=1)
    predictions["apmem"],records = apmem_paths(v,r,config)
    logs = {"settings":asdict(config),"apmem":records}
    for name,features in causal_features(p,options,instrument).items():
        out,records = np.full((len(p),len(HORIZONS)),np.nan),[]
        for j,h in enumerate(HORIZONS):
            out[:,j],rec = direct_har(features,v,h,config)
            records.extend(rec)
        predictions[name],logs[name] = out,records
    predictions["equal_blend"],predictions["adaptive_blend"],weights = combine(predictions,v)
    logs["adaptive_weights_mean"] = np.nanmean(weights,axis=0).tolist()
    logs["adaptive_weights_last"] = weights[-1].tolist()
    logs["coverage"] = {k:np.isfinite(a).sum(axis=0).tolist() for k,a in predictions.items()}
    return predictions,logs
