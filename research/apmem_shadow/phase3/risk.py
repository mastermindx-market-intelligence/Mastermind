"""Causal stock-specific volatility context; no directional or sizing authority."""
from __future__ import annotations
import numpy as np
import pandas as pd
from research.apmem_shadow.phase2.forecasts import Settings, qlike
from research.apmem_shadow.phase2.moments import fixed_power_forecasts
from .data import future_mean

PRICE_FEATURES = ('tier_t2', 'relative_momentum', 'distance_high63',
                  'log_variance21', 'overnight_share21')
RISK_FEATURES = PRICE_FEATURES + ('log_mem_h5', 'mem_change5', 'mem_h1_h20', 'stop_noise5')
INTERACTION_FEATURES = RISK_FEATURES + ('t2_x_vol_change', 'relative_x_vol_change')
FEATURE_GROUPS = {'price': PRICE_FEATURES, 'risk': RISK_FEATURES, 'interaction': INTERACTION_FEATURES}


def forecasts(p: pd.DataFrame, config: Settings = Settings()) -> tuple[pd.DataFrame, dict]:
    """The initial row has no observed overnight return and is excluded from fits."""
    if not {'variance', 'return_log'}.issubset(p) or len(p) < 3:
        raise ValueError('missing prepared variance/return observations')
    v = p.variance.iloc[1:].to_numpy(float)
    r = p.return_log.iloc[1:].to_numpy(float)
    mem, records, diagnostics = fixed_power_forecasts(v, r, config)
    result = pd.DataFrame(index=p.index)
    ewma = pd.Series(v).ewm(alpha=.06, adjust=False).mean().to_numpy()
    for j, h in enumerate((1, 5, 20)):
        result[f'mem_h{h}'] = np.r_[np.nan, mem[:, j]]
        result[f'ewma_h{h}'] = np.r_[np.nan, ewma]
        result[f'future_variance_h{h}'] = future_mean(p.variance, h)
        result[f'future_return_square_h{h}'] = future_mean(p.return_log.pow(2), h)
    for record in records:
        record['origin_session'] = str(p.index[record['origin']+1].date())
        record['train_start_session'] = str(p.index[record['train_start']+1].date())
        record['train_end_session'] = str(p.index[record['train_end']+1].date())
    return result, {'model': 'fixed_power_delta1_MEM', 'initial_unobserved_gap_row_excluded': True,
                    'fits': records, 'diagnostics': diagnostics,
                    'may_rank': False, 'may_size': False, 'may_trade': False}


def features(p: pd.DataFrame, predictions: pd.DataFrame,
             benchmark: pd.DataFrame) -> pd.DataFrame:
    if not p.index.equals(predictions.index):
        raise ValueError('prediction and instrument dates differ')
    required = ('mem_h1', 'mem_h5', 'mem_h20', 'ewma_h5')
    if not set(required).issubset(predictions) or 'momentum126_skip21' not in benchmark:
        raise ValueError('missing forecast/benchmark fields')
    out = predictions.copy()
    out['relative_momentum'] = p.momentum126_skip21 - benchmark.momentum126_skip21.reindex(p.index)
    out['distance_high63'] = p.distance_high63
    out['log_variance21'] = np.log(p.variance21)
    out['overnight_share21'] = p.overnight_share21
    out['log_mem_h5'] = np.log(out.mem_h5)
    out['mem_change5'] = np.log(out.mem_h5/out.mem_h5.shift(5))
    out['mem_h1_h20'] = np.log(out.mem_h1/out.mem_h20)
    out['stop_noise5'] = .05/np.sqrt(5*out.mem_h5)
    out['relative_x_vol_change'] = out.relative_momentum*out.mem_change5
    # tier_t2 and its interaction are event-specific, supplied by the event join.
    return out.replace([np.inf, -np.inf], np.nan)


def add_event_features(events: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    if not {'origin', 'family'}.issubset(events):
        raise ValueError('missing event identity')
    dates = pd.to_datetime(events.origin)
    matched = f.reindex(dates).reset_index(drop=True)
    out = events.reset_index(drop=True).copy()
    for col in matched:
        out[col] = matched[col].to_numpy()
    out['tier_t2'] = (out.get('native_tier', pd.Series(index=out.index, dtype=object)) == 'T2').astype(float)
    out['t2_x_vol_change'] = out.tier_t2*out.mem_change5
    out['common_risk_available'] = np.isfinite(out[['mem_h5', 'ewma_h5']]).all(axis=1)
    return out


def matched_forecast_losses(events: pd.DataFrame) -> pd.DataFrame:
    """Uncollapsed paired losses retain date/name dependence for calendar blocking."""
    records = []
    for h in (1, 5, 20):
        for target in ('variance', 'return_square'):
            cols = [f'mem_h{h}', f'ewma_h{h}', f'future_{target}_h{h}']
            good = np.isfinite(events[cols]).all(axis=1) & (events[cols[:2]] > 0).all(axis=1)
            sub = events.loc[good]
            if sub.empty:
                continue
            y = sub[cols[2]].to_numpy(float)
            for model in ('mem', 'ewma'):
                f = sub[f'{model}_h{h}'].to_numpy(float)
                loss = qlike(y, f)
                for i, (_, row) in enumerate(sub.iterrows()):
                    records.append({'event_id': row.event_id, 'ticker': row.ticker,
                                    'origin': row.origin, 'family': row.family,
                                    'horizon': h, 'target': target, 'model': model,
                                    'qlike': float(loss[i]), 'mse': float((y[i]-f[i])**2)})
    return pd.DataFrame(records)
