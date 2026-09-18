"""Outcome ledger for portfolio held-risk alerts (W3, masterplan §9).

Nightly appender: for each alert in alerts.jsonl older than 5 (and 21) sessions
without an outcome row, computes forward return from alert-day close to t+5/t+21
and appends to outcomes.jsonl.

Descriptive only (PRD-R10). No signals, no thresholds tuned from this data.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger("mastermind.pfolio.outcomes")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ALERTS_PATH = _REPO_ROOT / "data" / "portfolio_watch" / "alerts.jsonl"
_OUTCOMES_PATH = _REPO_ROOT / "data" / "portfolio_watch" / "outcomes.jsonl"
_LOCAL_LOCK = threading.RLock()
_HORIZONS = [5, 21]  # sessions


def _trading_days_between(start: date, end: date) -> int:
    """Approximate count of NYSE trading sessions in (start, end] exclusive of start.

    Uses simple Mon-Fri approximation for speed; good enough for 5/21-day horizons.
    """
    count = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count


def _load_jsonl(path: Path) -> list[dict]:
    """Strict canonical JSONL read; missing file is the only empty-state shortcut."""
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"canonical JSONL row is not a mapping: {path.name}")
        rows.append(row)
    return rows


def _lock_path() -> Path:
    return _OUTCOMES_PATH.with_name(f".{_OUTCOMES_PATH.name}.lock")


@contextmanager
def _outcomes_lock():
    """Serialize held-risk outcome KEEP-FIRST publication across processes."""
    with _LOCAL_LOCK:
        _OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock_path().open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except OSError:
                    # A completed atomic replace already decided the data effect.
                    pass


def _atomic_write_outcomes(rows: list[dict]) -> None:
    """Atomically replace the outcome ledger, preserving prior complete bytes on failure."""
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("held-risk outcome rows must be mappings")
    _OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, default=str) + "\n" for row in rows)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=_OUTCOMES_PATH.parent,
            prefix=f".{_OUTCOMES_PATH.name}.", suffix=".tmp", delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, _OUTCOMES_PATH)
        tmp_name = None
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _get_ohlcv_series(ticker: str, vendor_root: Path | None = None):
    """Return (idx_strs, closes_values) tuple from OHLCV, or (None, None) on failure.

    idx_strs: list of date strings 'YYYY-MM-DD' in index order
    closes_values: list of float close prices in matching order
    """
    try:
        from portfolio.held_risk import _load_ohlcv, VENDOR_DEFAULT
        vr = vendor_root or VENDOR_DEFAULT
        df = _load_ohlcv(ticker, vr)
        if df is None or df.empty:
            return None, None
        closes = df["close"].dropna()
        if closes.empty:
            return None, None
        try:
            idx_strs = [str(i.date()) if hasattr(i, "date") else str(i)[:10] for i in closes.index]
        except Exception:
            idx_strs = [str(i)[:10] for i in closes.index]
        return idx_strs, list(closes.values)
    except Exception:
        return None, None


def _get_price_at(ticker: str, as_of: date, vendor_root: Path | None = None) -> float | None:
    """Get close price for ticker on or before as_of date (for ref_close lookups only).

    Used only for the reference bar lookup. Forward prices are computed by
    bar-index offset via _grade_outcome() to avoid calendar-date approximation.
    """
    idx_strs, values = _get_ohlcv_series(ticker, vendor_root)
    if idx_strs is None:
        return None
    as_of_str = str(as_of)
    valid_pairs = [(s, v) for s, v in zip(idx_strs, values) if s <= as_of_str]
    if not valid_pairs:
        return None
    return float(valid_pairs[-1][1])


def _grade_outcome(
    ticker: str,
    alert_date: date,
    horizon: int,
    vendor_root: Path | None = None,
) -> tuple[float | None, float | None, bool]:
    """Compute (ref_close, fwd_close, deferred) using bar-count semantics.

    Steps:
      1. Find ref_idx = last bar index at-or-before alert_date
      2. fwd_idx = ref_idx + horizon (exact bar count, no calendar arithmetic)
      3. If fwd_idx >= len(series) → deferred=True (bar not yet available; never skip by back-filling)
      4. Return (ref_close, fwd_close, False) if both bars exist; (None, None, True) if deferred

    Returns:
        (ref_close, fwd_close, deferred) where deferred=True means the forward bar
        does not yet exist and this outcome should be skipped until a later run.
    """
    idx_strs, values = _get_ohlcv_series(ticker, vendor_root)
    if idx_strs is None or not values:
        return None, None, False  # missing data, not a deferral

    as_of_str = str(alert_date)
    # Find the last bar at-or-before alert_date
    ref_idx = None
    for i, s in enumerate(idx_strs):
        if s <= as_of_str:
            ref_idx = i
        else:
            break

    if ref_idx is None:
        return None, None, False  # no ref bar available

    fwd_idx = ref_idx + horizon
    if fwd_idx >= len(idx_strs):
        # Forward bar does not yet exist → defer (do not back-fill)
        return None, None, True

    ref_close = float(values[ref_idx])
    fwd_close = float(values[fwd_idx])
    return ref_close, fwd_close, False


def append_outcomes(today: date | None = None, vendor_root: Path | None = None) -> int:
    """Compute and persist matured held-risk outcomes exactly once.

    Missing/unavailable forward price bars remain a normal no-op. Canonical alert/outcome corruption
    and publication failure propagate to the already-existing best-effort caller boundary in
    ``scripts/run_portfolio_risk.py`` rather than masquerading as zero newly graded outcomes.
    """
    today_d = today or date.today()

    alerts = _load_jsonl(_ALERTS_PATH)
    if not alerts:
        return 0

    # The first read avoids unnecessary price I/O for outcomes already graded. KEEP-FIRST is
    # re-checked under the mutation lock below, so concurrent runs cannot both publish a row.
    prior_outcomes = _load_jsonl(_OUTCOMES_PATH)
    prior_graded = {
        (row.get("alert_id"), row.get("horizon"))
        for row in prior_outcomes
        if row.get("alert_id") is not None and row.get("horizon") is not None
    }
    candidates: list[dict] = []
    candidate_keys: set[tuple] = set()

    for alert in alerts:
        alert_id = alert.get("alert_id")
        ticker = (alert.get("ticker") or "").upper()
        ts = alert.get("ts") or alert.get("alert_date")
        if not alert_id or not ticker or not ts:
            continue

        try:
            alert_date = date.fromisoformat(str(ts)[:10])
        except ValueError:
            continue

        sessions_elapsed = _trading_days_between(alert_date, today_d)
        for horizon in _HORIZONS:
            key = (alert_id, horizon)
            if key in prior_graded or key in candidate_keys:
                continue
            if sessions_elapsed < horizon:
                continue

            # Bar-count grading: forward close is the bar EXACTLY `horizon` positions after the
            # ref bar. Missing/late bars remain retryable by producing no candidate this run.
            ref_close, fwd_close, deferred = _grade_outcome(
                ticker, alert_date, horizon, vendor_root
            )
            if deferred or ref_close is None or fwd_close is None or ref_close <= 0:
                continue

            fwd_return_pct = (fwd_close - ref_close) / ref_close * 100
            candidates.append({
                "alert_id": alert_id,
                "ticker": ticker,
                "role": alert.get("type"),
                "alert_date": str(alert_date),
                "horizon": horizon,
                "fwd_return_pct": round(fwd_return_pct, 4),
                "ref_close": round(ref_close, 4),
                "fwd_close": round(fwd_close, 4),
                "graded_at": str(today_d),
            })
            candidate_keys.add(key)

    if not candidates:
        return 0

    with _outcomes_lock():
        existing = _load_jsonl(_OUTCOMES_PATH)
        graded = {
            (row.get("alert_id"), row.get("horizon"))
            for row in existing
            if row.get("alert_id") is not None and row.get("horizon") is not None
        }
        fresh: list[dict] = []
        for row in candidates:
            key = (row["alert_id"], row["horizon"])
            if key in graded:
                continue
            graded.add(key)
            fresh.append(row)
        if not fresh:
            return 0
        _atomic_write_outcomes(existing + fresh)

    log.info("outcome ledger: %d new rows appended", len(fresh))
    return len(fresh)
