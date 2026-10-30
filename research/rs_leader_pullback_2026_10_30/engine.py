from __future__ import annotations
from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import date, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
NY = ZoneInfo("America/New_York")
@dataclass(frozen=True)
class Rules:
    timeframe_minutes: int = 30
    min_red: int = 3
    pivot_valid_bars: int = 2
    hybrid_lookback_bars: int = 3
    rsi_oversold: float = 40.0
    rs_top_fraction: float = 0.20
    min_universe: int = 100
    coverage_floor: float = 0.95
    min_close: float = 5.0
    min_adv_dollars: float = 20_000_000.0
    hold_sessions: int = 5
    target_r: float = 2.0
    tick: float = 0.01
    cost_bps_per_side: float = 5.0
    def __post_init__(self):
        if not 1 <= self.timeframe_minutes <= 390 or self.timeframe_minutes > 390:
            raise ValueError("invalid timeframe")
        if self.min_red < 1 or self.pivot_valid_bars < 1 or self.hybrid_lookback_bars < 1:
            raise ValueError("invalid signal window")
        if not 0 < self.rs_top_fraction <= 1 or not 0 < self.coverage_floor <= 1:
            raise ValueError("invalid RS/coverage fraction")
        if self.min_universe < 1 or self.hold_sessions < 1 or self.target_r <= 0:
            raise ValueError("invalid universe/hold/target")
        if self.tick <= 0 or self.cost_bps_per_side < 0:
            raise ValueError("invalid execution assumptions")
def _strict_bool(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        if values.isna().any():
            raise ValueError("missing boolean value")
        return values.astype(bool)
    translated = values.map(lambda x: {"true": True, "false": False,
                                       "1": True, "0": False}.get(str(x).strip().lower()))
    if translated.isna().any():
        raise ValueError("boolean column must be true/false/1/0")
    return translated.astype(bool)
def validate_bars(raw: pd.DataFrame, rules: Rules) -> pd.DataFrame:
    required = {"timestamp_utc", "symbol", "open", "high", "low", "close", "volume"}
    if required - set(raw.columns):
        raise ValueError(f"missing bar columns: {sorted(required - set(raw.columns))}")
    b = raw.copy()
    b["timestamp_utc"] = pd.to_datetime(b["timestamp_utc"], utc=True, errors="raise")
    if b["timestamp_utc"].isna().any() or b["symbol"].isna().any():
        raise ValueError("missing timestamp or symbol")
    for col in ("open", "high", "low", "close", "volume"):
        b[col] = pd.to_numeric(b[col], errors="coerce")
    arr = b[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(arr).all() or (arr[:, :4] <= 0).any() or (arr[:, 4] < 0).any():
        raise ValueError("invalid OHLCV")
    if ((b["high"] < b[["open", "close", "low"]].max(axis=1)) |
            (b["low"] > b[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("inconsistent high/low")
    if "session" in b and (b["session"] != "RTH").any():
        raise ValueError("this experiment accepts only RTH; qualified BOATS requires a separate experiment")
    if "final" in b and not _strict_bool(b["final"]).all():
        raise ValueError("incomplete bars are not tradable")
    b["local_end"] = b["timestamp_utc"].dt.tz_convert(NY)
    b["session_date"] = b["local_end"].dt.date
    mins = (b["local_end"].dt.hour * 60 + b["local_end"].dt.minute - 570)
    valid = ((mins > 0) & (mins <= 390) & (mins % rules.timeframe_minutes == 0) &
             (b["local_end"].dt.weekday < 5) &
             (b["local_end"].dt.second == 0))
    if not valid.all():
        raise ValueError("misanchored/incomplete RTH bar or weekend")
    b = b.sort_values(["symbol", "timestamp_utc"]).reset_index(drop=True)
    if b.duplicated(["symbol", "timestamp_utc"]).any():
        raise ValueError("duplicate bar")
    for _, g in b.groupby(["symbol", "session_date"], sort=False):
        minute = (g["local_end"].dt.hour * 60 + g["local_end"].dt.minute - 570)
        if len(minute) > 1 and not (minute.diff().iloc[1:] == rules.timeframe_minutes).all():
            raise ValueError("missing within-session RTH bar; fail closed")
    return b
def leader_panel(daily: pd.DataFrame, memberships: pd.DataFrame, rules: Rules) -> dict[date, dict[str, Any]]:
    dcols = {"date", "symbol", "close", "volume"}
    mcols = {"symbol", "start_date", "end_date"}
    if dcols - set(daily.columns) or mcols - set(memberships.columns):
        raise ValueError("missing daily or PIT membership columns")
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"], errors="raise").dt.date
    for col in ("close", "volume"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    if d.duplicated(["date", "symbol"]).any():
        raise ValueError("duplicate daily row")
    m = memberships.copy()
    m["start_date"] = pd.to_datetime(m["start_date"], errors="raise").dt.date
    m["end_date"] = pd.to_datetime(m["end_date"], errors="coerce").map(
        lambda x: x.date() if pd.notna(x) else None)
    if d["date"].isna().any() or m["start_date"].isna().any():
        raise ValueError("invalid as-of date")
    spy = d[d.symbol == "SPY"].set_index("date").sort_index()["close"]
    if spy.empty or spy.isna().any():
        raise ValueError("complete SPY daily calendar required")
    dates = spy.index.tolist()
    if dates != sorted(set(dates)):
        raise ValueError("duplicate benchmark date")
    br20 = spy / spy.shift(20) - 1
    br60 = spy / spy.shift(60) - 1
    nonspy = d[d.symbol != "SPY"].copy()
    pieces = []
    for symbol, rows in nonspy.groupby("symbol", sort=False):
        s = rows.set_index("date").reindex(dates)
        close, vol = s["close"], s["volume"]
        good = (close.notna() & (close > 0) & vol.notna() & (vol >= 0))
        full = good.rolling(61, min_periods=61).sum() == 61
        ema21 = close.ewm(span=21, adjust=False, min_periods=21).mean()
        frame = pd.DataFrame({
            "date": dates, "symbol": symbol, "present": good.to_numpy(),
            "close": close.to_numpy(), "adv": (close * vol).rolling(20, min_periods=20).mean().to_numpy(),
            "trend": (close > ema21).to_numpy(), "full": full.to_numpy(),
            "rs20": (close / close.shift(20) - 1 - br20).to_numpy(),
            "rs60": (close / close.shift(60) - 1 - br60).to_numpy(),
        })
        pieces.append(frame)
    if not pieces:
        raise ValueError("no candidate stock histories")
    allrows = pd.concat(pieces, ignore_index=True)
    out = {}
    for day, rows in allrows.groupby("date", sort=True):
        active = m[(m.start_date <= day) & (m.end_date.isna() | (m.end_date >= day))]
        expected = set(active.symbol) - {"SPY"}
        if not expected:
            out[day] = {"leaders": set(), "coverage": 0.0, "expected": 0, "qualified": 0}
            continue
        selected = rows[rows.symbol.isin(expected)]
        present = set(selected.loc[selected.present, "symbol"])
        coverage = len(present) / len(expected)
        qualified = selected[
            selected.full & selected.trend & (selected.close >= rules.min_close) &
            (selected.adv >= rules.min_adv_dollars) &
            (selected.rs20 > 0) & (selected.rs60 > 0)
        ].copy()
        if coverage < rules.coverage_floor or len(present) < rules.min_universe or qualified.empty:
            leaders = set()
        else:
            qualified["score"] = (qualified.rs20 + qualified.rs60) / 2
            valid = selected[selected.full & (selected.close >= rules.min_close) &
                             (selected.adv >= rules.min_adv_dollars)].copy()
            valid["score"] = (valid.rs20 + valid.rs60) / 2
            rank = valid["score"].rank(method="average", pct=True)
            top = set(valid.loc[rank >= 1 - rules.rs_top_fraction, "symbol"])
            leaders = set(qualified.symbol) & top
        out[day] = {"leaders": leaders, "coverage": coverage,
                    "expected": len(expected), "qualified": len(qualified),
                    "observed": len(present)}
    return out
def _oscillator(b: pd.DataFrame, rules: Rules) -> pd.DataFrame:
    b = b.copy()
    if {"osc_fast", "osc_slow", "osc_oversold"}.issubset(b.columns):
        a = pd.to_numeric(b.osc_fast, errors="coerce")
        z = pd.to_numeric(b.osc_slow, errors="coerce")
        flag = _strict_bool(b.osc_oversold)
    else:
        close = b.close.astype(float)
        fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
        slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
        a = fast - slow
        z = a.ewm(span=9, adjust=False, min_periods=9).mean()
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        rsi = rsi.where(loss != 0, 100)
        flag = rsi <= rules.rsi_oversold
    b["osc_cross"] = ((a.shift(1) <= z.shift(1)) & (a > z) &
                      (a < 0) & (z < 0) & flag).fillna(False)
    return b
def _fill_trade(b: pd.DataFrame, entry_i: int, base_entry: float, stop: float,
                rules: Rules, strategy: str, signal_i: int, method: str) -> dict[str, Any]:
    gross_entry = base_entry * (1 + rules.cost_bps_per_side / 10000)
    if not (np.isfinite(gross_entry) and np.isfinite(stop) and gross_entry > stop > 0):
        raise ValueError("entry/stop risk invalid")
    risk = gross_entry - stop
    target = gross_entry + rules.target_r * risk
    highs, lows = [], []
    sessions = []
    exit_px = None
    reason = "CENSORED"
    exit_i = None
    for j in range(entry_i, len(b)):
        bar = b.iloc[j]
        day = bar.session_date
        if day not in sessions:
            sessions.append(day)
        highs.append(float(bar.high))
        lows.append(float(bar.low))
        if j > entry_i and float(bar.open) <= stop:
            exit_px, reason, exit_i = float(bar.open), "STOP_GAP", j
        elif float(bar.low) <= stop:
            exit_px, reason, exit_i = stop, "STOP", j
        elif float(bar.high) >= target:
            exit_px, reason, exit_i = target, "TARGET", j
        elif len(sessions) >= rules.hold_sessions and (j + 1 == len(b) or
              b.iloc[j + 1].session_date != day):
            if j + 1 < len(b):
                exit_px, reason, exit_i = float(bar.close), "TIME", j
        if exit_i is not None:
            break
    record = {"symbol": str(b.iloc[entry_i].symbol), "strategy": strategy,
              "signal_close_utc": b.iloc[signal_i].timestamp_utc.isoformat(),
              "entry_bar_end_utc": b.iloc[entry_i].timestamp_utc.isoformat(),
              "entry_method": method, "entry_px_after_cost": float(gross_entry),
              "raw_stop": float(stop), "target": float(target), "exit_reason": reason,
              "exit_bar_end_utc": None if exit_i is None else b.iloc[exit_i].timestamp_utc.isoformat(),
              "exit_px_after_cost": None, "net_return": None, "net_r": None,
              "mfe_r": None if not highs else (max(highs) - gross_entry) / risk,
              "mae_r": None if not lows else (min(lows) - gross_entry) / risk}
    if exit_i is not None:
        received = exit_px * (1 - rules.cost_bps_per_side / 10000)
        record.update(exit_px_after_cost=float(received),
                      net_return=float(received / gross_entry - 1),
                      net_r=float((received - gross_entry) / risk))
    return record
def evaluate(bars: pd.DataFrame, leaders: dict[date, dict[str, Any]], rules: Rules) -> dict[str, Any]:
    b = validate_bars(bars, rules)
    days = sorted(leaders)
    result = {k: [] for k in ("pivot", "macd_rsi_proxy", "hybrid")}
    diagnostics = {k: {"candidate_count": 0, "skipped_no_leader": 0,
                       "skipped_overlap": 0, "censored": 0} for k in result}
    for symbol, raw in b.groupby("symbol", sort=False):
        g = _oscillator(raw.reset_index(drop=True), rules)
        n = len(g)
        eligible = []
        for i in range(n):
            day = g.iloc[i].session_date
            j = bisect_left(days, day) - 1
            eligible.append(j >= 0 and day in leaders and
                            symbol in leaders[days[j]]["leaders"])
        cross = g.osc_cross.to_numpy(dtype=bool)
        candidates = {k: [] for k in result}
        red = 0
        for i in range(n):
            bar = g.iloc[i]
            if bar.close < bar.open:
                red += 1
            else:
                if bar.close > bar.open and red >= rules.min_red:
                    trigger = float(bar.high) + rules.tick
                    stop = float(bar.low) - rules.tick
                    for j in range(i + 1, min(n, i + 1 + rules.pivot_valid_bars)):
                        nxt = g.iloc[j]
                        if float(nxt.open) <= stop:
                            break
                        if float(nxt.high) >= trigger:
                            price = max(trigger, float(nxt.open))
                            candidate = (i, j, price, stop, "stop_above_pivot_high")
                            candidates["pivot"].append(candidate)
                            lo = max(0, i - rules.hybrid_lookback_bars + 1)
                            if bool(cross[lo:i + 1].any()):
                                candidates["hybrid"].append(candidate)
                            break
                        if float(nxt.low) <= stop:
                            break
                red = 0
            if cross[i] and i + 1 < n:
                stop = float(g.iloc[max(0, i - 4):i + 1].low.min()) - rules.tick
                candidates["macd_rsi_proxy"].append((i, i + 1, float(g.iloc[i + 1].open),
                                                      stop, "next_bar_open"))
        for strategy, rows in candidates.items():
            diagnostics[strategy]["candidate_count"] += len(rows)
            next_available = 0
            for sig, ent, px, stop, method in sorted(rows, key=lambda c: (c[1], c[0])):
                if not eligible[sig]:
                    diagnostics[strategy]["skipped_no_leader"] += 1
                    continue
                if ent < next_available:
                    diagnostics[strategy]["skipped_overlap"] += 1
                    continue
                if px <= stop:
                    continue
                rec = _fill_trade(g, ent, px, stop, rules, strategy, sig, method)
                result[strategy].append(rec)
                if rec["exit_bar_end_utc"] is None:
                    diagnostics[strategy]["censored"] += 1
                    next_available = n
                else:
                    ex_time = pd.Timestamp(rec["exit_bar_end_utc"])
                    ex_idx = int(g.timestamp_utc.searchsorted(ex_time, side="right"))
                    next_available = max(ent + 1, ex_idx)
    return {"schema": "rs_pullback_event_study.v1", "rules": asdict(rules),
            "performance_is_empirically_validated": False,
            "analysis_type": "event_study_not_funded_portfolio",
            "osc_source": ("supplied_precomputed_columns" if
                           {"osc_fast", "osc_slow", "osc_oversold"}.issubset(b.columns)
                           else "standard_MACD12_26_9_plus_Wilder_RSI14_proxy"),
            "events": result, "diagnostics": diagnostics,
            "metrics": {k: summarise(v) for k, v in result.items()}}
def summarise(events: list[dict[str, Any]]) -> dict[str, Any]:
    known = [x for x in events if x["net_r"] is not None]
    if not known:
        return {"total_entries": len(events), "resolved": 0, "censored": len(events),
                "win_rate": None, "mean_net_r": None, "mean_net_return": None}
    return {"total_entries": len(events), "resolved": len(known),
            "censored": len(events) - len(known),
            "win_rate": sum(x["net_r"] > 0 for x in known) / len(known),
            "mean_net_r": float(np.mean([x["net_r"] for x in known])),
            "mean_net_return": float(np.mean([x["net_return"] for x in known])),
            "stopped": sum(x["exit_reason"].startswith("STOP") for x in known)}
