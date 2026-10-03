"""Trend Persistence — repaired price substrate (design v2).

The audited deep+delisted panel prices almost every current S&P 1500 member but few of the
names that have left the index, and after mid-2021 it prices almost none of the leavers. A
cross-section built from it is conditioned on survival, which is the wrong universe for a test
about drawdowns.

This module repairs the part that can be repaired. For point-in-time members the audited panel
has no column for, it reads closes from the whole-market daily store (raw, unadjusted, first
session 2021-07-06), back-adjusts them for splits from a committed vendor reference, keeps the
one contiguous listing that matches the membership, and cleans the block with the audited
sanitizer. Audited columns are loaded by the audited loader and are not touched.

It also returns the quoted-price mask for every column: True where the cleaned panel holds a
real close and not a filled one. The sanitizer fills the gaps inside a name's life, and
whether a day is "inside" depends on whether the name trades again later, so the cleaned panel
alone cannot say what was knowable on the day. The mask can.

And it returns the close exactly as it printed, unadjusted, for every member the store has a
file for. A back-adjusted price is divided by splits that had not happened yet, so a $1 or $5
threshold tested on it lets the future decide who is eligible. From the store's first session
the thresholds are tested on the printed close.

What this does not repair, and the pre-registration says so: members that left before the
store begins; dividends and spin-offs in store-sourced names (only splits are adjusted, so a
spin-off or liquidating distribution reads as a price drop); ticker changes are not linked
(the old symbol stops, the new one starts).

Prices and membership only. Nothing here computes a feature or a label.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any

import numpy as np
import pandas as pd

STORE_START = "2021-07-06"     # first session of the whole-market daily store
SEGMENT_GAP_DAYS = 30          # a longer silence separates two listings of one symbol
_HERE = os.path.dirname(os.path.abspath(__file__))
SPLIT_REFERENCE_PATH = os.path.join(_HERE, "data", "trend_persistence_split_reference.csv")


def load_split_reference(path: str | None = None) -> pd.DataFrame:
    """Vendor split events: before ``execution_date`` one old share is ``split_to/split_from`` new."""
    ref = pd.read_csv(path or SPLIT_REFERENCE_PATH, dtype={"ticker": str})
    ref["execution_date"] = pd.to_datetime(ref["execution_date"])
    ref = ref.drop_duplicates()
    if ref.duplicated(["ticker", "execution_date"]).any():
        raise ValueError("split reference holds conflicting rows for one ticker and date")
    if not ((ref["split_from"] > 0) & (ref["split_to"] > 0)).all():
        raise ValueError("split reference holds a non-positive ratio")
    return ref.sort_values(["ticker", "execution_date"]).reset_index(drop=True)


def split_adjust(close: pd.Series, splits: pd.DataFrame) -> pd.Series:
    """Back-adjust raw closes: every price before a split is put on the post-split share basis."""
    out = close.astype(float).copy()
    for when, a, b in zip(splits["execution_date"], splits["split_from"], splits["split_to"]):
        out[out.index < when] *= float(a) / float(b)
    return out


def member_segment(close: pd.Series, spans, gap_days: int = SEGMENT_GAP_DAYS) -> pd.Series:
    """Keep the one contiguous listing that the membership refers to.

    A symbol can be reused by a different company. Runs of prices separated by more than
    ``gap_days`` calendar days are treated as different listings; the run with the most sessions
    inside the membership spans is kept (the later run on a tie). A file whose prices never
    fall inside a membership span is not the member and yields nothing.
    """
    if close.empty:
        return close
    days = close.index.to_series().diff().dt.days.fillna(0).to_numpy()
    run = np.cumsum(days > gap_days)
    inside = np.zeros(len(close), bool)
    for start, end in spans:
        inside |= (close.index >= start) & (True if pd.isna(end) else close.index < end)
    counts = np.bincount(run, weights=inside.astype(float))
    if counts.max() <= 0:
        return close.iloc[0:0]
    best = int(np.flatnonzero(counts == counts.max())[-1])
    return close[run == best]


def store_window_members(mem: pd.DataFrame) -> list[str]:
    """Members with a membership span reaching into the store window."""
    ends = pd.to_datetime(mem["end_date"])
    live = mem[ends.isna() | (ends > pd.Timestamp(STORE_START))]
    return sorted(set(live["ticker"].astype(str)))


def store_candidates(mem: pd.DataFrame, have) -> list[str]:
    """Members with a span reaching into the store window and no audited price column."""
    return sorted(set(store_window_members(mem)) - set(map(str, have)))


def _read_store_close(store_dir: str, ticker: str) -> pd.Series | None:
    """One symbol's raw closes from the store, by day; None when the store has no file."""
    path = os.path.join(store_dir, f"{ticker}.parquet")
    if "/" in ticker or not os.path.exists(path):
        return None
    raw = pd.read_parquet(path, columns=["close"])["close"]
    raw.index = pd.to_datetime(raw.index)
    raw = raw[~raw.index.duplicated()].sort_index().astype(float)
    return raw[np.isfinite(raw) & (raw > 0)]


def load_printed(tickers, index: pd.DatetimeIndex, store_dir: str):
    """Closes as printed (unadjusted) for ``tickers`` on ``index``; NaN where the store has none.

    Read by symbol and day: the membership names a symbol on a day, and the store prints that
    symbol on that day, so no listing has to be chosen and nothing later is consulted.
    """
    cols: dict[str, pd.Series] = {}
    absent: list[str] = []
    for t in tickers:
        raw = _read_store_close(store_dir, t)
        if raw is None:
            absent.append(t)
            continue
        cols[t] = raw.reindex(index)
    return pd.DataFrame(cols, index=index, dtype=float), absent


def default_store_dir() -> str:
    from loop import factor_experiment as fx
    return os.environ.get("TREND_PERSISTENCE_STORE_DIR") or os.path.join(
        fx.MACRO, "data", "massive_stock_day")


def build_store_block(tickers, mem: pd.DataFrame, index: pd.DatetimeIndex,
                      splits: pd.DataFrame, store_dir: str):
    """Split-adjusted closes of ``tickers`` on ``index``, before cleaning, plus a report."""
    starts, ends = pd.to_datetime(mem["start_date"]), pd.to_datetime(mem["end_date"])
    names = mem["ticker"].astype(str)
    cols: dict[str, pd.Series] = {}
    report: dict[str, Any] = {"no_file": [], "not_the_member": [], "listings_trimmed": [],
                              "splits_applied": 0}
    for t in tickers:
        raw = _read_store_close(store_dir, t)
        if raw is None:
            report["no_file"].append(t)
            continue
        mine = splits[splits["ticker"] == t]
        adj = split_adjust(raw, mine)
        which = (names == t).to_numpy()
        seg = member_segment(adj, list(zip(starts[which], ends[which])))
        if seg.empty:
            report["not_the_member"].append(t)
            continue
        if len(seg) < len(adj):
            report["listings_trimmed"].append(t)
        report["splits_applied"] += int(((mine["execution_date"] > seg.index[0])
                                         & (mine["execution_date"] <= seg.index[-1])).sum())
        cols[t] = seg.reindex(index)
    block = pd.DataFrame(cols, index=index, dtype=float)
    return block, report


def _raw_audited(breadth: str, floor: pd.Timestamp) -> pd.DataFrame:
    """The audited loader's raw union, before cleaning — only to read which closes were quoted."""
    deep = pd.read_parquet(os.path.join(breadth, "_closes_deep.parquet"))
    deli = pd.read_parquet(os.path.join(breadth, "_closes_delisted.parquet"))
    raw = pd.concat([deep, deli], axis=1)
    raw = raw.loc[:, ~raw.columns.duplicated()]
    raw.index = pd.to_datetime(raw.index)
    raw = raw.sort_index()
    return raw[raw.index >= floor]


def load_repaired_panel(breadth_dir: str | None = None, store_dir: str | None = None):
    """Audited panel + store-sourced members, with the quoted-price mask and printed closes.

    Returns (closes, observed, printed, mem, provenance). ``closes`` has SPY first, then the
    audited columns exactly as the audited loader returns them, then the store-sourced columns.
    ``printed`` has the same columns: the unadjusted close where the store prints one, else NaN.
    ``observed`` is True where the cleaned panel holds a real close and, where a printed close
    is known, that printed close is at least $1.
    """
    from loop import factor_experiment as fx
    from research import trend_persistence_panel as panel

    closes, mem, provenance = panel.load_audited_panel(breadth_dir)
    index = pd.DatetimeIndex(closes.index)
    raw = _raw_audited(fx.BREADTH, fx.PANEL_START)
    audited = [c for c in closes.columns if c != "SPY"]
    observed = (raw.reindex(index=index, columns=audited) >= fx.MIN_PRICE)
    observed.insert(0, "SPY", closes["SPY"].notna().to_numpy())

    store_dir = store_dir or default_store_dir()
    splits = load_split_reference()
    block, report = build_store_block(store_candidates(mem, closes.columns), mem, index,
                                      splits, store_dir)
    clean = fx.sanitize_panel(block)
    digest = hashlib.sha256()
    digest.update("|".join(block.columns).encode())
    digest.update(np.ascontiguousarray(block.to_numpy(float)).tobytes())
    first = block.notna().idxmax() if block.shape[1] else pd.Series(dtype="datetime64[ns]")
    provenance = dict(provenance)
    provenance["store"] = {
        "dir": store_dir, "names": list(block.columns), "n_names": int(block.shape[1]),
        "first_session": str(first.min())[:10] if len(first) else None,
        "no_file": report["no_file"], "not_the_member": report["not_the_member"],
        "listings_trimmed": report["listings_trimmed"],
        "splits_applied": report["splits_applied"],
        "n_clamped": int(clean.attrs.get("n_clamped", 0)),
        "block_sha256_16": digest.hexdigest()[:16],
        "split_reference": panel._file_stamp(SPLIT_REFERENCE_PATH),
    }
    closes = pd.concat([closes, clean], axis=1)
    observed = pd.concat([observed, block >= fx.MIN_PRICE], axis=1)

    window = set(store_window_members(mem))
    printed, absent = load_printed([c for c in closes.columns if c in window], index, store_dir)
    printed = printed.reindex(columns=closes.columns)
    known = printed.notna()
    observed = observed & (~known | (printed >= fx.MIN_PRICE))
    digest = hashlib.sha256()
    digest.update("|".join(map(str, printed.columns)).encode())
    digest.update(np.ascontiguousarray(printed.to_numpy(float)).tobytes())
    first = known.any(axis=1)
    provenance["printed"] = {
        "n_names": int(known.any(axis=0).sum()), "no_file": absent,
        "first_session": str(index[first.to_numpy().argmax()])[:10] if bool(first.any()) else None,
        "sha256_16": digest.hexdigest()[:16],
    }
    provenance["n_columns"] = int(closes.shape[1])
    return closes, observed, printed, mem, provenance
