"""Point-in-time signal history — the engine's MEMORY (the foundation the learning loop needs).

`vendor/macro/.../latest.json` (the regime + every per-name lens output the engine reasons over) is
OVERWRITTEN IN PLACE on every run. So the engine keeps NO faithful record of what it actually SAW on
any past day — which makes calibration and learning impossible: you cannot grade, or learn from, a
decision whose inputs you can no longer reconstruct. Today the only thing with real history is PRICE;
every lens/conviction/regime value is a same-day snapshot that vanishes at the next run.

This module fixes that at the source. On every daily build it records — KEEP-FIRST per (asof, ticker)
— the lens snapshot + the decision for each name the loop evaluated. Once realized outcomes accrue
(see brain/outcomes / brain/scorer; the first thesis cohort resolves ~2026-07-17), each historical
decision can be joined to its realized result, and the gate can finally LEARN which lenses actually
predicted, in which regime — instead of asserting a probability it has never verified.

KEEP-FIRST: an intra-day rebuild never overwrites the first, PIT-honest read of the day (mirrors the
macro engine's signal_archive discipline). Append-only logical history with atomic whole-file publication. Missing history is a legitimate empty
state; malformed/unreadable canonical history fails closed so it can never be mistaken for "no prior
signals." This is irreversible-if-skipped — every day not recorded is signal history that can never
be reconstructed.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_PATH = _ROOT / "data" / "signal_history" / "signals.jsonl"
_LOCAL_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lock_path() -> Path:
    return _PATH.with_name(f".{_PATH.name}.lock")


@contextmanager
def _history_lock():
    """Serialize KEEP-FIRST publication across threads and processes."""
    with _LOCAL_LOCK:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
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


def _read_unlocked() -> list[dict]:
    if not _PATH.exists():
        return []
    rows: list[dict] = []
    for line in _PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("signal-history row is not a mapping")
        rows.append(row)
    return rows


def _read() -> list[dict]:
    # Atomic writers mean an unlocked reader sees a complete prior or successor file.
    # Corrupt canonical evidence must never become a false empty history.
    return _read_unlocked()


def _atomic_write(rows: list[dict]) -> None:
    """Replace signal history atomically; preserve complete prior bytes on failure."""
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, default=str, ensure_ascii=False) + "\n" for row in rows)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=_PATH.parent,
            prefix=f".{_PATH.name}.", suffix=".tmp", delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, _PATH)
        tmp_name = None
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def seen_keys(asof: str) -> set[str]:
    """The (ticker) set already recorded for `asof` — so KEEP-FIRST can skip same-day re-records."""
    return {r.get("ticker") for r in _read() if r.get("asof") == asof and r.get("ticker")}


def _flatten_lens_dirs(rows: list[dict]) -> dict[str, str]:
    """lens -> direction map from a decision-matrix `rows` list (the heart of the snapshot)."""
    out: dict[str, str] = {}
    for r in rows or []:
        lens = r.get("lens")
        if lens and r.get("direction") is not None:
            out[lens] = r.get("direction")
    return out


def make_record(asof: str, ticker: str, *, sleeve: str, decision: str, regime: dict | None = None,
                synthesis: dict | None = None, rows: list[dict] | None = None,
                verdict: str | None = None, weight: float | None = None,
                size_stage: str | None = None, price: float | None = None,
                time_stop_by: str | None = None, reason: str | None = None,
                extra: dict | None = None) -> dict:
    """Build one flat, queryable PIT record. `decision` in {sized, held, rejected, leadership}."""
    syn = synthesis or {}
    reg = regime or {}
    rec: dict[str, Any] = {
        "asof": asof, "ticker": (ticker or "").upper(), "sleeve": sleeve, "decision": decision,
        "verdict": verdict, "weight": weight, "size_stage": size_stage, "price": price,
        "time_stop_by": time_stop_by, "reason": reason,
        # the engine's read (the learnable substrate)
        "confluence": syn.get("confluence"), "bull": syn.get("bull"), "bear": syn.get("bear"),
        "size_authority": syn.get("size_authority"), "vetoes": syn.get("vetoes") or [],
        "weak_asymmetry": syn.get("weak_asymmetry"), "price_downtrend": syn.get("price_downtrend"),
        "price_falling_fast": syn.get("price_falling_fast"), "leadership_ok": syn.get("leadership_ok"),
        "divergences": [d.get("pattern") if isinstance(d, dict) else d
                        for d in (syn.get("divergences") or [])],
        "lens_dirs": _flatten_lens_dirs(rows or []),
        # the regime context the decision was conditioned on (for regime-conditional calibration)
        "quad": reg.get("quad"), "quad_name": reg.get("quad_name"),
        "liquidity_overlay": reg.get("liquidity_overlay"),
        "macro_risk": (reg.get("macro_risk") or {}).get("score") if isinstance(reg.get("macro_risk"), dict) else None,
        "archived_at": _now_iso(),
    }
    if extra:
        rec.update(extra)
    return rec


def archive(asof: str, records: list[dict]) -> int:
    """Publish records for ``asof`` exactly once per ticker; return rows newly recorded.

    Missing/empty input is a normal no-op. Canonical history read/publish failures raise to the
    existing build caller boundary; they are never rewritten as "nothing new". The function
    argument owns the archived date so stale row metadata cannot escape into another day.
    """
    if not records:
        return 0

    candidates: list[dict] = []
    batch_seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise TypeError("signal-history record is not a mapping")
        ticker = (record.get("ticker") or "").upper()
        if not ticker or ticker in batch_seen:
            continue
        batch_seen.add(ticker)
        row = {**record, "ticker": ticker, "asof": asof}
        row.setdefault("archived_at", _now_iso())
        candidates.append(row)
    if not candidates:
        return 0

    with _history_lock():
        existing = _read_unlocked()
        already = {r.get("ticker") for r in existing if r.get("asof") == asof and r.get("ticker")}
        fresh: list[dict] = []
        for row in candidates:
            ticker = row["ticker"]
            if ticker in already:
                continue
            already.add(ticker)
            fresh.append(row)
        if not fresh:
            return 0
        _atomic_write(existing + fresh)
        return len(fresh)


def load(asof: str | None = None) -> list[dict]:
    """All recorded rows, optionally filtered to one `asof`."""
    rows = _read()
    return [r for r in rows if r.get("asof") == asof] if asof else rows


def load_df():
    """The history as a pandas DataFrame for analysis/calibration. None if pandas is unavailable."""
    try:
        import pandas as pd
        return pd.DataFrame(_read())
    except Exception:
        return None
