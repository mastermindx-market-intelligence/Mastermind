"""Path labels with explicit next-open fills, splits, dividends and gap losses.

These are future OUTCOMES, never signal inputs. All label classes use the full
registered horizon as their maturity clock, including trades that exit early.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExitRule:
    name: str
    horizon: int
    stop: float | None = None
    target: float | None = None
    trailing_close: bool = False


RULES = {
    'time21': ExitRule('time21', 21),
    'stop21': ExitRule('stop21', 21, .05),
    'barrier21': ExitRule('barrier21', 21, .05, .08),
    'trail63': ExitRule('trail63', 63, trailing_close=True),
}


def barrier_fill(open_price: float, high: float, low: float,
                 stop: float | None, target: float | None,
                 *, order: str = 'stop_first') -> tuple[float | None, str | None, bool, bool]:
    values = [open_price, high, low] + [x for x in (stop, target) if x is not None]
    if not np.isfinite(values).all() or min(values) <= 0 or low > open_price or high < open_price:
        raise ValueError('invalid barrier bar')
    if order not in ('stop_first', 'target_first') or (stop is not None and target is not None and stop >= target):
        raise ValueError('invalid barrier order/levels')
    if stop is not None and open_price <= stop:
        return open_price, 'stop', False, True
    if target is not None and open_price >= target:
        return open_price, 'target', False, True
    hit_stop = stop is not None and low <= stop
    hit_target = target is not None and high >= target
    ambiguous = bool(hit_stop and hit_target)
    if hit_stop and (not hit_target or order == 'stop_first'):
        return stop, 'stop', ambiguous, False
    if hit_target:
        return target, 'target', ambiguous, False
    return None, None, False, False


def evaluate_path(prices: pd.DataFrame, origin: int, *, rule: str = 'barrier21',
                  delay: int = 0, cost: float = .0005, order: str = 'stop_first') -> dict:
    if rule not in RULES or type(origin) is not int or origin < 0 or type(delay) is not int or delay < 0:
        raise ValueError('invalid path origin/rule/delay')
    if not np.isfinite(cost) or not 0 <= cost < .1:
        raise ValueError('invalid one-way cost')
    specification = RULES[rule]
    entry = origin + 1 + delay
    final = entry + specification.horizon - 1
    if entry >= len(prices) or final >= len(prices):
        return {'status': 'CENSORED', 'origin_pos': origin, 'rule': rule}
    columns = ['open', 'high', 'low', 'close', 'dividend', 'split']
    if not set(columns).issubset(prices) or not prices.index.is_unique or not prices.index.is_monotonic_increasing:
        raise ValueError('invalid path schema or index')
    a = prices.iloc[entry:final+1][columns].to_numpy(float)
    if (not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4] < 0).any()
            or (a[:, 5] <= 0).any() or (a[:, 1] < a[:, [0, 2, 3]].max(axis=1)).any()
            or (a[:, 2] > a[:, [0, 1, 3]].min(axis=1)).any()):
        raise ValueError('invalid/missing realized path')
    if specification.trailing_close and 'signal_close' not in prices:
        raise ValueError('trailing rule requires causal signal-close basis')
    trail = (prices.signal_close.shift(1).rolling(20, min_periods=20).min()
             if specification.trailing_close else None)
    initial = float(a[0, 0])
    stop = initial*(1-specification.stop) if specification.stop is not None else None
    target = initial*(1+specification.target) if specification.target is not None else None
    shares, cash = 1.0, 0.0
    exit_price = exit_value = exit_cash = exit_shares = None
    exit_offset = None
    exit_kind = None
    ambiguous = gap = False
    pending_trailing = False
    full_low, full_high, full_close = [], [], []
    for j, (o, h, l, c, dividend, split) in enumerate(a):
        if j:
            shares *= split
            cash += shares*dividend
            stop = stop/split if stop is not None else None
            target = target/split if target is not None else None
        # A buyer at the ex-date open has no claim to that day's distribution.
        full_low.append((shares*l+cash)/initial-1)
        full_high.append((shares*h+cash)/initial-1)
        full_close.append((shares*c+cash)/initial-1)
        if exit_offset is not None:
            continue
        if pending_trailing:
            fill, kind, both, through_gap = o, 'trailing_next_open', False, False
        else:
            fill, kind, both, through_gap = barrier_fill(o,h,l,stop,target,order=order)
        if fill is not None:
            exit_price, exit_cash, exit_shares = float(fill), float(cash), float(shares)
            exit_value = shares*fill + cash
            exit_offset, exit_kind, ambiguous, gap = j, kind, both, through_gap
        elif j == len(a)-1:
            exit_price, exit_cash, exit_shares = float(c), float(cash), float(shares)
            exit_value = shares*c + cash
            exit_offset, exit_kind = j, 'timeout'
        elif specification.trailing_close:
            threshold = trail.iloc[entry+j]
            pending_trailing = bool(pd.notna(threshold) and prices.signal_close.iloc[entry+j] < threshold)
    gross = exit_value/initial - 1
    net = (exit_shares*exit_price*(1-cost)+exit_cash)/(initial*(1+cost))-1
    return {'status': 'COMPLETE', 'origin_pos': origin, 'entry_pos': entry,
            'exit_pos': entry+exit_offset, 'label_end_pos': final,
            'origin': str(prices.index[origin].date()), 'entry_date': str(prices.index[entry].date()),
            'exit_date': str(prices.index[entry+exit_offset].date()),
            'label_end': str(prices.index[final].date()), 'rule': rule,
            'exit_kind': exit_kind, 'class_id': 0 if exit_kind == 'stop' else 1 if exit_kind == 'target' else 2,
            'days_held': int(exit_offset+1), 'entry_price': initial, 'exit_price': exit_price,
            'exit_share_factor': exit_shares, 'dividend_cash': exit_cash,
            'gross_return': float(gross), 'net_return': float(net),
            'hold_to_horizon_return': float(full_close[-1]),
            'full_horizon_mae': float(min(full_low)), 'full_horizon_mfe': float(max(full_high)),
            'full_horizon_underwater_sessions': int(np.sum(np.asarray(full_close) < 0)),
            'stop_then_recovered': bool(exit_kind == 'stop' and full_close[-1] > 0),
            'ambiguous_exit_bar': bool(ambiguous), 'gap_exit': bool(gap),
            'barrier_order': order, 'one_way_cost': float(cost), 'extra_session_delay': delay}
