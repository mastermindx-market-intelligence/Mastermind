"""Trend Persistence, Wave C: sector group persistence.

The instrument of ``research/TREND_PERSISTENCE_PREREG_C1.md`` (pinned below by sha256). Two
parts share one document: C1 is a development pass scored once on the formation dates V2 and B2
already used, and is a claim about nothing; C2 is a confirmation read on formation dates after
the freeze commit, with every construction, gate and constant fixed in that document and the
one unknown constant — the forward read size — produced here by a rule.

What this module adds to the family: a sector label at *t* from the Wave C-0 point-in-time
sector snapshot (macro ``data/breadth/sp1500_pit_sectors.parquet``; labels are as-of-now and
the artifact says so), seven group features and five sector-level baseline descriptors, each one
number per sector-date ranked across the sectors present, three unlabelled-member treatments
(primary labelled-only, Bracket NI, Bracket CM), the gating baseline B*, the models of §5, the
selection rule of §7.1, the power rule of §6 and the closed-list C2 constants block.

What it reuses, unedited: the repaired panel and its loaders (``trend_persistence_substrate``,
``trend_persistence_panel``), B2's volatility descriptors, its exact model-B2 column set and
its test of a mean (``trend_persistence_walkforward``). The reproduction of B2's two committed
means runs before any group feature is computed and stops the instrument if it fails.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd

from research import trend_persistence_panel as tpp
from research import trend_persistence_walkforward as wf

SCHEMA = 1
PREREG_FILE = "TREND_PERSISTENCE_PREREG_C1.md"
PREREG_SHA256 = "f22b0cee218c381dd3fd078d67301c985eb9415faa0e75ffdc57d520374bf4cc"
B2_RESULT_FILE = os.path.join("data", "trend_persistence_b2_result.json")
B2_RESULT_SHA256 = "e0b177cb51dececc173e67817e76356f201d498626022440487cce0a3a2ba443"
V2_PANEL_SHA256 = "48cb5e76269b3a503d2973aecdd04733a2d8b88434db06de8367a224ba4ef178"
SECTOR_SNAPSHOT_SHA256 = "cba7fc07da53a6230122fec5797b15163bbe3b31f78918839f5722e885c00de3"
COVERAGE_SHA256 = "ce5c692075dc14b1a830c611565b4ba7c48e637fcfaa2a53690829a4ed0ff34c"
MEMBERSHIP_SHA256 = "7b34316c0561619ba052f02036ec1fbe7fff3d00dcda3e7acb7dffda10582eca"
B2_MEANS = {20: (0.49461154432499976, 194), 60: (0.5337496007208158, 186)}   # §5, /horizons/h/models/B2/ic
REPRODUCTION_TOL = 1e-9

ATTEMPT_FILE = os.path.join("data", "trend_persistence_c1_attempt.json")
RESULT_FILE = os.path.join("data", "trend_persistence_c1_result.json")
CONSTANTS_FILE = os.path.join("data", "trend_persistence_c2_constants.json")
INTERIM_FILE = os.path.join("data", "trend_persistence_c2_interim.json")
C2_RESULT_FILE = os.path.join("data", "trend_persistence_c2_result.json")
CODE_FILES = ("trend_persistence_group.py", "trend_persistence_walkforward.py",
              "trend_persistence_panel.py", "trend_persistence_substrate.py")

HORIZONS = (5, 20, 60)
GATE_HORIZONS = (20, 60)
STEP = tpp.FORMATION_STEP                    # labels at h span ceil(h / STEP) formation dates
BLOCKS = (("T1", "2022-07-06", "2022-12-31"), ("T2", "2023-01-01", "2023-12-31"),
          ("T3", "2024-01-01", "2024-12-31"), ("T4", "2025-01-01", "2025-12-31"),
          ("T5", "2026-01-01", "2026-12-31"))
EARLY_BLOCKS = (("E1", "2019-01-01", "2019-12-31"), ("E2", "2020-01-01", "2020-12-31"),
                ("E3", "2021-01-01", "2021-12-31"))
EMBARGO_EXIT = "2026-06-02"                  # every C1 label exits on or before this session
TRAIN_START = "2013-01-02"
BRACKET_TRAIN_START = "2019-01-02"
MIN_TRAIN_DATES = 100
MIN_CASES = tpp.MIN_NAMES_PER_DATE           # 100 complete cases per date
MIN_SECTOR_MEMBERS = 25                      # group date: every sector has at least this many
SECTORS = ("Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy",
           "Financials", "Health Care", "Industrials", "Information Technology", "Materials",
           "Real Estate", "Utilities")
TIERS = ("sp500", "sp400", "sp600")
HISTORY = 120                                # sessions of valid returns a contributing member needs
SMA_WINDOW = 50
BLOCK_LEN = 5                                # non-overlapping 5-session blocks: 24 in 120 sessions
Z_WINDOW = 252
SECTOR_VOL = ("grp_dispersion_60", "grp_vol_60", "grp_medvol_60", "grp_te_120")
GROUP_FEATURES = ("grp_rs_60", "grp_rs_120", "grp_rs_consistency_120", "grp_participation_50",
                  "grp_hit_20", "grp_leader_retention_60x60", "grp_coherence_60")
REDUNDANCY_RHO = 0.80
MARKET_TERMS = ("beta_x_spy_ret_20", "beta_x_spy_ret_60", "beta_x_spy_ret_120",
                "vol60_x_spy_vol_20")
SPLIT_PARTS = ("between_60", "within_60", "between_120", "within_120")
MODELS = ("G", "B", "Bstar", "A", "I", "BstarD", "SPLIT")
BRACKET_MODELS = ("Bstar", "A", "I")
LOGIT_MODELS = ("Bstar", "A")                # the reported drawdown event, §9
DIFFERENCES = (("A", "Bstar"), ("A", "B"), ("I", "A"), ("I", "Bstar"), ("G", None),
               ("BstarD", "Bstar"), ("SPLIT", "Bstar"))
CELLS = (("rel_spy", 20, "A", "Bstar"), ("rel_spy", 60, "A", "Bstar"), ("rel_spy", 20, "I", "A"))
PRIMARY = CELLS[0]
SEQUENCE = ((1, CELLS[0], None), (2, CELLS[1], 96), (3, CELLS[2], None))   # step, cell, n_read floor
SELECT_MEAN_MIN = 0.010                      # (i)  V2's development floor G2
SELECT_P_MAX = 0.10                          # (ii)
SELECT_BLOCKS_MIN = 4                        # (iii) of 5
P_GATE = 0.025                               # C2 W1 and the power rule's level
W2_BLOCKS, W2_MIN = 4, 3
W3_FLOOR = {20: 0.0025, 60: 0.0050}
POWER_TARGET = 0.80
DELTA_FLOOR = 0.008
N_READ_SET = (48, 96, 144)
INTERIM_DAYS = 182
EVENT_FRACTION = 0.10                        # the worst tenth of forward drawdowns (B2)
FLAG_FRACTION = 0.10
SPREAD_FRACTION = 0.10                       # top tenth minus bottom tenth of scores

_HERE = os.path.dirname(os.path.abspath(__file__))


class GroupRefused(RuntimeError):
    """A pin, a reproduction or a rule of the pre-registration refused the run."""


# ---- pins and files -------------------------------------------------------------------------
def _sha256(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def canonical_sha256(obj: Any) -> str:
    """sha256 of the canonical JSON form (sorted keys, no spaces) of a JSON-able object."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def prereg_sha256() -> str | None:
    return _sha256(os.path.join(_HERE, PREREG_FILE))


def pinned_prereg() -> str:
    got = prereg_sha256()
    if got != PREREG_SHA256:
        raise tpp.PreregDrift(f"{PREREG_FILE} hashes to {got}, not the pinned {PREREG_SHA256}; "
                              "the C1 instrument does not run")
    return PREREG_SHA256


def pinned_b2_result(path: str | None = None) -> dict[str, Any]:
    path = path or os.path.join(_HERE, B2_RESULT_FILE)
    got = _sha256(path)
    if got != B2_RESULT_SHA256:
        raise tpp.PreregDrift(f"{B2_RESULT_FILE} hashes to {got}, not the pinned {B2_RESULT_SHA256}")
    with open(path) as fh:
        return json.load(fh)


def code_sha256() -> str:
    digest = hashlib.sha256()
    for name in CODE_FILES:
        with open(os.path.join(_HERE, name), "rb") as fh:
            digest.update(name.encode())
            digest.update(fh.read())
    return digest.hexdigest()


def load_sector_snapshot(path: str, expected_sha256: str | None = SECTOR_SNAPSHOT_SHA256) -> dict:
    """The C-0 sector snapshot: one row per ticker, as-of-now labels, with its own honesty columns."""
    got = _sha256(path)
    if expected_sha256 and got != expected_sha256:
        raise tpp.PreregDrift(f"sector snapshot {path} hashes to {got}, not {expected_sha256}")
    f = pd.read_parquet(path)
    need = {"ticker", "sector", "is_leaver", "label_asof", "era_correct"}
    if not need <= set(f.columns):
        raise GroupRefused(f"sector snapshot lacks {sorted(need - set(f.columns))}")
    if f["ticker"].duplicated().any():
        raise GroupRefused("sector snapshot carries a ticker twice")
    sector = {t: (s if isinstance(s, str) and s in SECTORS else None)
              for t, s in zip(f["ticker"], f["sector"])}
    unknown = sorted({s for s in f["sector"].dropna().unique() if s not in SECTORS})
    if unknown:
        raise GroupRefused(f"sector snapshot carries sectors outside the eleven: {unknown}")
    return {"sector": sector, "current": {t: not bool(l) for t, l in zip(f["ticker"], f["is_leaver"])},
            "label_asof": pd.Timestamp(f["label_asof"].iloc[0]), "sha256": got, "path": path,
            "era_correct_any": bool(f["era_correct"].any()), "n_rows": int(len(f))}


def choose_snapshot(formation_date, snapshots, fallback: Mapping[str, Any]) -> dict[str, Any]:
    """§3: the earliest digest-pinned snapshot whose ``label_asof`` is on or after the date.

    ``snapshots`` are mappings with ``label_asof`` and ``sha256``; dates before the first
    prospective snapshot use the fallback (the C-0 snapshot).
    """
    d = pd.Timestamp(formation_date)
    eligible = [s for s in snapshots if pd.Timestamp(s["label_asof"]) >= d]
    if not eligible:
        return dict(fallback)
    return dict(min(eligible, key=lambda s: pd.Timestamp(s["label_asof"])))


def freeze_info(prereg_path: str | None = None) -> dict[str, Any]:
    """§3: the freeze is the first commit on the current history that carries the pinned file.

    Returns the commit, its UTC committer date and the derived interim date. The run that
    writes the constants block must be made from a tree whose history contains master's
    squash-merge of the pre-registration, so this is master's commit, found from here.
    """
    path = prereg_path or os.path.join(_HERE, PREREG_FILE)
    root = os.path.dirname(_HERE)
    rel = os.path.relpath(path, root)

    def git(*args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                              check=True).stdout
    out = git("log", "--format=%H %cI", "--diff-filter=A", "--", rel).strip().splitlines()
    if not out:
        raise GroupRefused(f"{rel} has no adding commit in this history; no freeze date")
    commit, stamp = out[-1].split()                       # oldest adding commit
    blob = git("show", f"{commit}:{rel}")
    if hashlib.sha256(blob.encode()).hexdigest() != PREREG_SHA256:
        raise GroupRefused(f"{rel} at its adding commit {commit[:12]} is not the pinned text")
    when = datetime.datetime.fromisoformat(stamp).astimezone(datetime.timezone.utc)
    freeze = when.date()
    return {"commit": commit, "committer_utc": when.isoformat(timespec="seconds"),
            "freeze_date": freeze.isoformat(),
            "interim_date": (freeze + datetime.timedelta(days=INTERIM_DAYS)).isoformat(),
            "first_confirmatory_rule": "first formation-calendar date strictly after freeze_date; "
                                       "calendar = every fifth session from index 252 of a panel "
                                       "whose first session is 2002-01-02",
            "read_rule": "once, on the first session on which the n_read-th confirmatory "
                         "formation date has a complete label at the longest live horizon; the "
                         "first n_read confirmatory dates per live horizon; no re-read"}


def git_state() -> dict[str, Any]:
    def git(*args):
        return subprocess.run(["git", "-C", _HERE, *args], capture_output=True, text=True,
                              check=True).stdout
    dirty = [ln for ln in git("status", "--porcelain").splitlines()
             if not ln.endswith(os.path.basename(ATTEMPT_FILE))]
    return {"head": git("rev-parse", "HEAD").strip(), "clean": not dirty}


# ---- substrate: sectors, tiers, market state -------------------------------------------------
def tier_codes(index: pd.DatetimeIndex, names, mem: pd.DataFrame) -> np.ndarray:
    """(T, N) int8: 0 sp500, 1 sp400, 2 sp600 from the membership span covering each session, else -1."""
    out = np.full((len(index), len(names)), -1, np.int8)
    col = {n: j for j, n in enumerate(names)}
    last = index[-1]
    for t, s, e, src in zip(mem["ticker"], mem["start_date"], mem["end_date"], mem["src"]):
        j = col.get(t)
        if j is None or src not in TIERS:
            continue
        a = int(index.searchsorted(pd.Timestamp(s), side="left"))
        b = int(index.searchsorted(last if pd.isna(e) else pd.Timestamp(e), side="right"))
        out[a:b, j] = TIERS.index(src)
    return out


def sector_codes(names, snapshot: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Sector index 0..10 per name (-1 unlabelled) and the current-member flag per name."""
    sec = np.array([SECTORS.index(snapshot["sector"][n]) if snapshot["sector"].get(n) else -1
                    for n in names], int)
    cur = np.array([bool(snapshot["current"].get(n, False)) for n in names], bool)
    return sec, cur


def market_state(spy: np.ndarray) -> dict[str, np.ndarray]:
    """§4(d): SPY trailing returns and 20-session volatility, each standardised over the
    trailing 252 sessions ending at the session (its own mean and standard deviation)."""
    L = np.log(np.asarray(spy, float))
    r = pd.Series(np.r_[np.nan, np.diff(L)])
    raw = {f"spy_ret_{w}": pd.Series(L).diff(w) for w in (20, 60, 120)}
    raw["spy_vol_20"] = r.rolling(20, min_periods=20).std(ddof=0)
    out = {}
    for k, x in raw.items():
        mu = x.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
        sd = x.rolling(Z_WINDOW, min_periods=Z_WINDOW).std(ddof=0)
        out[f"z_{k}"] = ((x - mu) / sd.where(sd > 0)).to_numpy(float)
    out["spy_ret_60_sign"] = np.sign(raw["spy_ret_60"].to_numpy(float))
    return out


def _ranks_across(values: np.ndarray) -> np.ndarray:
    """§4: (r - 0.5) / K - 0.5 across the K finite entries, average ranks on ties; NaN stays NaN."""
    out = np.full(len(values), np.nan)
    ok = np.isfinite(values)
    k = int(ok.sum())
    if k:
        out[ok] = (tpp._rank(values[ok]) - 0.5) / k - 0.5
    return out


def group_inputs(closes: pd.DataFrame, observed: pd.DataFrame, panel: dict, sec: np.ndarray,
                 tier: np.ndarray, current: np.ndarray, *, members: str = "labelled") -> dict:
    """§4(b), (c), (e), (f) and the SPLIT parts, at every formation row of the panel.

    One value per sector-date for each sector-level variable, from the eligible labelled
    members whose last 120 daily returns are all quoted (``members="labelled"``), or from those
    still in the index at the snapshot (``members="current"``, Bracket CM). A sector-date is
    valid only with at least MIN_SECTOR_MEMBERS contributing members and a finite value of
    every variable; a date is a group date only if all eleven sectors are valid.
    """
    names = panel["names"]
    index = pd.DatetimeIndex(closes.index)
    P = closes[names].to_numpy(float)
    quoted = (observed.reindex(index=closes.index, columns=names).fillna(False).to_numpy(bool)
              & np.isfinite(P))
    Pq = np.where(quoted, P, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        L = np.log(Pq)
        Ls = np.log(closes["SPY"].to_numpy(float))
    r = np.full(P.shape, np.nan)
    r[1:] = L[1:] - L[:-1]
    rs = np.full(len(Ls), np.nan)
    rs[1:] = Ls[1:] - Ls[:-1]
    rows = np.asarray(panel["rows"], int)
    F, N, K = len(rows), len(names), len(SECTORS)
    nb = HISTORY // BLOCK_LEN
    vol60 = panel["controls"]["vol_60d"]
    sector_vars = tuple(SECTOR_VOL) + ("grp_size",) + tuple(GROUP_FEATURES)
    out = {k: np.full((F, K), np.nan) for k in sector_vars}
    counts = np.zeros((F, K), int)
    valid = np.zeros((F, N), bool)
    split = {k: np.full((F, N), np.nan) for k in SPLIT_PARTS}
    tier_at = np.full((F, N), -1, np.int8)
    use_current = members == "current"
    for i, t in enumerate(rows):
        if t < HISTORY:
            continue
        win = r[t - HISTORY + 1:t + 1]                      # (120, N) daily log returns ending at t
        ok = np.isfinite(win).all(axis=0) & quoted[t]
        valid[i] = ok
        tier_at[i] = tier[t]
        contrib = panel["eligible"][i] & (sec >= 0) & ok
        if use_current:
            contrib &= current
        if not contrib.any():
            continue
        ret20, ret60, ret120 = L[t] - L[t - 20], L[t] - L[t - 60], L[t] - L[t - 120]
        first60 = L[t - 60] - L[t - 120]
        sma = Pq[t - SMA_WINDOW + 1:t + 1].mean(axis=0)
        above = Pq[t] > sma
        blk = win.reshape(nb, BLOCK_LEN, N).sum(axis=1)   # (24, N) non-overlapping block returns
        spy_blk = rs[t - HISTORY + 1:t + 1].reshape(nb, BLOCK_LEN).sum(axis=1)
        ew_blk_all = blk[:, contrib].mean(axis=1)
        tier_ew60 = np.full(len(TIERS), np.nan)
        tier_ew120 = np.full(len(TIERS), np.nan)
        for c in range(len(TIERS)):
            m = contrib & (tier[t] == c)
            if m.any():
                tier_ew60[c], tier_ew120[c] = ret60[m].mean(), ret120[m].mean()
        tt = tier[t].astype(int)
        own60 = np.where(tt >= 0, tier_ew60[np.clip(tt, 0, None)], np.nan)
        own120 = np.where(tt >= 0, tier_ew120[np.clip(tt, 0, None)], np.nan)
        rs60, rs120 = ret60 - own60, ret120 - own120
        last60 = win[-60:]
        for k in range(K):
            m = contrib & (sec == k)
            n = int(m.sum())
            counts[i, k] = n
            if n < MIN_SECTOR_MEMBERS:
                continue
            ew_daily = last60[:, m].mean(axis=1)
            sec_blk = blk[:, m].mean(axis=1)
            v60 = vol60[i][m]
            v60 = v60[np.isfinite(v60)]
            out["grp_dispersion_60"][i, k] = ret60[m].std()
            out["grp_vol_60"][i, k] = ew_daily.std()
            out["grp_medvol_60"][i, k] = float(np.median(v60)) if len(v60) else np.nan
            out["grp_te_120"][i, k] = (sec_blk - spy_blk).std()
            out["grp_size"][i, k] = n
            out["grp_rs_60"][i, k] = np.nanmean(rs60[m]) if np.isfinite(rs60[m]).any() else np.nan
            out["grp_rs_120"][i, k] = np.nanmean(rs120[m]) if np.isfinite(rs120[m]).any() else np.nan
            out["grp_rs_consistency_120"][i, k] = float((sec_blk > ew_blk_all).mean())
            out["grp_participation_50"][i, k] = float(above[m].mean())
            out["grp_hit_20"][i, k] = float((ret20[m] > 0).mean())
            n_top = n // 3
            top1 = set(np.argsort(-first60[m], kind="stable")[:n_top].tolist())
            top2 = set(np.argsort(-ret60[m], kind="stable")[:n_top].tolist())
            out["grp_leader_retention_60x60"][i, k] = len(top1 & top2) / n_top if n_top else np.nan
            X = last60[:, m]
            Xc = X - X.mean(axis=0)
            ec = ew_daily - ew_daily.mean()
            den = np.sqrt((Xc * Xc).sum(axis=0) * float(ec @ ec))
            with np.errstate(invalid="ignore", divide="ignore"):
                corr = (Xc.T @ ec) / den
            out["grp_coherence_60"][i, k] = np.nanmean(corr) if np.isfinite(corr).any() else np.nan
            between60, between120 = ret60[m].mean(), ret120[m].mean()
            lab = sec == k                                  # every labelled name of the sector
            split["between_60"][i, lab] = between60
            split["within_60"][i, lab] = ret60[lab] - between60
            split["between_120"][i, lab] = between120
            split["within_120"][i, lab] = ret120[lab] - between120
    finite = np.ones((F, K), bool)
    for k in sector_vars:
        finite &= np.isfinite(out[k])
    sector_ok = finite & (counts >= MIN_SECTOR_MEMBERS)
    ms = market_state(closes["SPY"].to_numpy(float))
    with np.errstate(invalid="ignore"):
        Pff = pd.DataFrame(P).ffill().to_numpy(float)
    return {"sector": out, "counts": counts, "sector_ok": sector_ok,
            "group_date": sector_ok.all(axis=1), "valid": valid, "split": split,
            "tier_at": tier_at, "members": members,
            "z": np.column_stack([ms[k][rows] for k in ("z_spy_ret_20", "z_spy_ret_60",
                                                        "z_spy_ret_120", "z_spy_vol_20")]),
            "spy_sign": ms["spy_ret_60_sign"][rows],
            "Pff": Pff, "spy": closes["SPY"].to_numpy(float), "names": list(names),
            "sec": sec, "current": current, "n_names": N}


def redundancy(gi: Mapping[str, Any], panel: dict, blocks=BLOCKS) -> dict[str, Any]:
    """§4(e) frozen redundancy rule: median over the T1-T5 group dates of the per-date Spearman
    correlation across sectors between each pair of features; |median| > 0.80 drops the
    later-numbered feature. Uses no label; deterministic; printed."""
    dates = panel["index"][np.asarray(panel["rows"], int)]
    in_blocks = np.zeros(len(dates), bool)
    for _, lo, hi in blocks:
        in_blocks |= (dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi))
    use = np.flatnonzero(in_blocks & gi["group_date"])
    names = list(GROUP_FEATURES)
    n = len(names)
    rho = np.full((n, n), np.nan)
    per_date = np.full((len(use), n, n), np.nan)
    for a in range(n):
        for b in range(n):
            if a == b:
                per_date[:, a, b] = 1.0
                continue
            for j, i in enumerate(use):
                x, y = gi["sector"][names[a]][i], gi["sector"][names[b]][i]
                per_date[j, a, b] = wf._spearman(x, y)
    if len(use):
        rho = np.nanmedian(per_date, axis=0)
    dropped = []
    for a in range(n):
        for b in range(a + 1, n):
            if np.isfinite(rho[a, b]) and abs(rho[a, b]) > REDUNDANCY_RHO and names[b] not in dropped:
                dropped.append(names[b])
    surviving = tuple(f for f in names if f not in dropped)
    return {"median_rho": {names[a]: {names[b]: (None if not np.isfinite(rho[a, b]) else float(rho[a, b]))
                                      for b in range(n)} for a in range(n)},
            "n_dates": int(len(use)), "dropped": dropped, "surviving": surviving,
            "threshold": REDUNDANCY_RHO}


# ---- assembly ---------------------------------------------------------------------------------
_CONTROLS = tuple(tpp.design_of("v2").controls)
N_C, N_D, N_P = len(_CONTROLS), len(wf.DESCRIPTORS), 2 * len(wf.PRODUCT_WINDOWS)
_B2_END = 2 * N_C + 2 * N_D + N_P                          # B2's fifty regressors, in B2's order
INTERACTIONS = ("wr120", "wr120_x_grp_rs_120", "wr120_x_grp_participation_50")


def _layout() -> tuple[str, ...]:
    cols = [f"c:{c}" for c in _CONTROLS] + [f"c2:{c}" for c in _CONTROLS]
    cols += [f"d:{k}" for k in wf.DESCRIPTORS] + [f"d2:{k}" for k in wf.DESCRIPTORS]
    cols += [f"p:{w}:{kind}" for w in wf.PRODUCT_WINDOWS for kind in ("rv", "r2v")]
    cols += list(SECTOR_VOL) + ["grp_size"] + [f"tier:{t}" for t in TIERS] + list(MARKET_TERMS)
    cols += list(GROUP_FEATURES) + list(INTERACTIONS)
    cols += [f"sector:{s}" for s in SECTORS] + list(SPLIT_PARTS) + [f"{p}_sq" for p in SPLIT_PARTS]
    return tuple(cols)


COLUMNS = _layout()
IDX = {n: i for i, n in enumerate(COLUMNS)}
_SECTOR_LEVEL = ([IDX[k] for k in SECTOR_VOL] + [IDX["grp_size"]] + [IDX[k] for k in GROUP_FEATURES]
                 + [IDX[f"sector:{s}"] for s in SECTORS])


def column_map(surviving=GROUP_FEATURES) -> dict[str, list[int]]:
    """§5: the regressor columns of every model. B is B2's model B2 exactly (the first fifty)."""
    B = list(range(_B2_END))
    Bstar = (B + [IDX[k] for k in SECTOR_VOL] + [IDX["grp_size"]]
             + [IDX[f"tier:{t}"] for t in TIERS] + [IDX[k] for k in MARKET_TERMS])
    G = [IDX[k] for k in surviving]
    A = Bstar + G
    I = A + [IDX[k] for k in INTERACTIONS]
    BstarD = Bstar + [IDX[f"sector:{s}"] for s in SECTORS]
    drop = {IDX["c:ret_60d"], IDX["c:ret_120d"], IDX["c2:ret_60d"], IDX["c2:ret_120d"]}
    SPLIT = ([c for c in Bstar if c not in drop] + [IDX[p] for p in SPLIT_PARTS]
             + [IDX[f"{p}_sq"] for p in SPLIT_PARTS])
    return {"G": G, "B": B, "Bstar": Bstar, "A": A, "I": I, "BstarD": BstarD, "SPLIT": SPLIT}


def _block_of(date, blocks) -> str | None:
    for name, lo, hi in blocks:
        if pd.Timestamp(lo) <= date <= pd.Timestamp(hi):
            return name
    return None


def embargo_mask(exit_dates, cutoff: str | None = EMBARGO_EXIT) -> np.ndarray:
    """§3: True where a label exits on or before the embargo session (kept); False is dropped."""
    exits = pd.DatetimeIndex(exit_dates)
    if cutoff is None:
        return np.ones(len(exits), bool)
    return np.asarray(exits <= pd.Timestamp(cutoff), bool)


def assemble_group(panel: dict, inputs: dict, gi: Mapping[str, Any], horizon: int, *,
                   bracket: str = "primary", surviving=GROUP_FEATURES,
                   embargo: str | None = EMBARGO_EXIT, start: str = TRAIN_START) -> dict[str, Any]:
    """Every complete case at one horizon as centred within-date ranks, one block per date.

    ``bracket``: "primary" (labelled cases, labelled aggregates), "NI" (all eligible cases;
    an unlabelled case carries 0 in every sector-level column and interaction and no indicator)
    or "CM" (labelled cases with aggregates passed in through ``gi`` built from current members).
    The label is the log return from the close of t+lag to the close of t+lag+h minus SPY's;
    ``rel_sector`` subtracts the equal-weight log return of the labelled cases of the sector.
    """
    h, lag = int(horizon), int(panel["lag"])
    lab = panel["labels"][h]
    rows, index = np.asarray(panel["rows"], int), panel["index"]
    sec, Pff, spy = gi["sec"], gi["Pff"], gi["spy"]
    K = len(SECTORS)
    Z_all = np.stack([panel["controls"][c] for c in _CONTROLS], axis=2)
    D_all = np.stack([inputs["descriptors"][k] for k in wf.DESCRIPTORS], axis=2)
    Y_mdd = lab["forward_max_drawdown"]
    stored = panel.get("store_sourced")
    start_ts = pd.Timestamp(start)
    i_beta, i_vol60 = _CONTROLS.index("beta_252d"), _CONTROLS.index("vol_60d")
    i_r120 = _CONTROLS.index("ret_120d")
    labelled_only = bracket != "NI"
    sector_vars = tuple(SECTOR_VOL) + ("grp_size",) + tuple(GROUP_FEATURES)
    R, y_spy, raw_spy, y_sec, raw_sec, mdd_l, event, sec_l, aud_l = [], [], [], [], [], [], [], [], []
    form, exit_row, dates, block, n_unl, spy_sign, start_off = [], [], [], [], [], [], [0]
    embargoed, group_failures, skipped = [], [], []
    with np.errstate(invalid="ignore", divide="ignore"):
        LPff, Lspy = np.log(Pff), np.log(spy)
    observable = np.flatnonzero(lab["observable"])
    keep = embargo_mask(index[lab["exit_rows"][observable]], embargo)
    for i, kept in zip(observable, keep):
        t = int(rows[i])
        form_date = index[t]
        if form_date < start_ts:
            continue
        if not kept:
            embargoed.append(str(form_date.date()))
            continue
        if not gi["group_date"][i]:
            group_failures.append({"date": str(form_date.date()),
                                   "sectors": [SECTORS[k] for k in np.flatnonzero(~gi["sector_ok"][i])]})
            continue
        if not np.isfinite(gi["z"][i]).all():
            skipped.append({"date": str(form_date.date()), "why": "market state not yet defined"})
            continue
        xr = int(lab["exit_rows"][i])
        en = t + lag
        lr = LPff[xr] - LPff[en]
        rel = lr - (Lspy[xr] - Lspy[en])
        tier_i = gi["tier_at"][i].astype(int)
        base = (panel["eligible"][i] & np.isfinite(rel) & np.isfinite(Z_all[i]).all(axis=1)
                & np.isfinite(D_all[i]).all(axis=1) & (tier_i >= 0) & np.isfinite(Y_mdd[i]))
        if labelled_only:
            sp = np.column_stack([gi["split"][p][i] for p in SPLIT_PARTS])
            cases = base & (sec >= 0) & np.isfinite(sp).all(axis=1)
        else:
            cases = base
        n = int(cases.sum())
        if n < MIN_CASES:
            skipped.append({"date": str(form_date.date()), "why": f"{n} complete cases"})
            continue
        idx = np.flatnonzero(cases)
        s_case = sec[idx]
        lab_case = s_case >= 0
        Zr = wf._centred_ranks(Z_all[i][idx])
        Dr = wf._centred_ranks(D_all[i][idx])
        M = np.zeros((n, len(COLUMNS)))
        M[:, :N_C] = Zr
        M[:, N_C:2 * N_C] = Zr * Zr
        M[:, 2 * N_C:2 * N_C + N_D] = Dr
        M[:, 2 * N_C + N_D:2 * N_C + 2 * N_D] = Dr * Dr
        M[:, 2 * N_C + 2 * N_D:_B2_END] = wf._products(Zr, _CONTROLS)
        safe = np.clip(s_case, 0, None)
        for name in sector_vars:
            rk = _ranks_across(gi["sector"][name][i])
            M[:, IDX[name]] = np.where(lab_case, rk[safe], 0.0)
        tc = tier_i[idx]
        for c, tname in enumerate(TIERS):
            M[:, IDX[f"tier:{tname}"]] = (tc == c)
        z = gi["z"][i]
        M[:, IDX["beta_x_spy_ret_20"]] = Zr[:, i_beta] * z[0]
        M[:, IDX["beta_x_spy_ret_60"]] = Zr[:, i_beta] * z[1]
        M[:, IDX["beta_x_spy_ret_120"]] = Zr[:, i_beta] * z[2]
        M[:, IDX["vol60_x_spy_vol_20"]] = Zr[:, i_vol60] * z[3]
        wr = np.zeros(n)
        r120 = Z_all[i][idx][:, i_r120]
        for k in range(K):
            m = s_case == k
            nk = int(m.sum())
            if nk:
                wr[m] = (tpp._rank(r120[m]) - 0.5) / nk - 0.5
        M[:, IDX["wr120"]] = wr
        M[:, IDX["wr120_x_grp_rs_120"]] = wr * M[:, IDX["grp_rs_120"]]
        M[:, IDX["wr120_x_grp_participation_50"]] = wr * M[:, IDX["grp_participation_50"]]
        for k, sname in enumerate(SECTORS):
            M[:, IDX[f"sector:{sname}"]] = (s_case == k)
        for k in range(K):                                # §4: zero within-sector variance, asserted
            m = s_case == k
            if m.any() and np.ptp(M[m][:, _SECTOR_LEVEL], axis=0).any():
                raise GroupRefused(f"a sector-level regressor varies inside sector {SECTORS[k]} on {form_date.date()}")
        if labelled_only:
            spr = wf._centred_ranks(sp[idx])
            for j, p in enumerate(SPLIT_PARTS):
                M[:, IDX[p]] = spr[:, j]
                M[:, IDX[f"{p}_sq"]] = spr[:, j] ** 2
        raw = rel[idx]
        lr_case = lr[idx]
        rsec = np.full(n, np.nan)
        for k in range(K):
            m = s_case == k
            if m.any():
                rsec[m] = lr_case[m] - lr_case[m].mean()
        R.append(M)
        y_spy.append(wf._centred_ranks(raw))
        raw_spy.append(raw)
        y_sec.append(wf._centred_ranks(rsec) if lab_case.all() else np.full(n, np.nan))
        raw_sec.append(rsec)
        mdd_l.append(Y_mdd[i][idx])
        event.append(wf._deepest(Y_mdd[i][idx], EVENT_FRACTION).astype(float))
        sec_l.append(s_case)
        aud_l.append(~stored[idx] if stored is not None else np.ones(n, bool))
        form.append(t)
        exit_row.append(xr)
        dates.append(form_date)
        block.append(_block_of(form_date, BLOCKS + EARLY_BLOCKS))
        n_unl.append(int((~lab_case).sum()))
        spy_sign.append(float(gi["spy_sign"][i]))
        start_off.append(start_off[-1] + n)
    if not R:
        return {"n_dates": 0, "horizon": h, "bracket": bracket, "embargoed": embargoed,
                "group_failures": group_failures, "skipped": skipped}
    blk = np.asarray(block, object)
    t_names = {b[0] for b in BLOCKS}
    e_names = {b[0] for b in EARLY_BLOCKS}
    return {
        "n_dates": len(form), "R": np.vstack(R), "y_spy": np.concatenate(y_spy),
        "raw_spy": np.concatenate(raw_spy), "y_sec": np.concatenate(y_sec),
        "raw_sec": np.concatenate(raw_sec), "mdd": np.concatenate(mdd_l),
        "event": np.concatenate(event), "sec": np.concatenate(sec_l),
        "audited": np.concatenate(aud_l), "start": np.asarray(start_off),
        "form": np.asarray(form), "exit": np.asarray(exit_row), "dates": pd.DatetimeIndex(dates),
        "block": blk, "is_test": np.array([b in t_names for b in blk], bool),
        "is_early": np.array([b in e_names for b in blk], bool),
        "n_cases": np.diff(np.asarray(start_off)), "n_unlabelled": np.asarray(n_unl),
        "spy_sign": np.asarray(spy_sign), "horizon": h, "bracket": bracket,
        "surviving": tuple(surviving), "columns": COLUMNS, "embargoed": embargoed,
        "group_failures": group_failures, "skipped": skipped,
    }


# ---- fitting and scoring -----------------------------------------------------------------------
def _train_rows(data: Mapping[str, Any], date_mask: np.ndarray) -> np.ndarray:
    start = data["start"]
    parts = [np.arange(start[d], start[d + 1]) for d in np.flatnonzero(date_mask)]
    return np.concatenate(parts) if parts else np.zeros(0, int)


def _gram_rows(R: np.ndarray, rows: np.ndarray, ys, chunk: int = 1 << 17):
    """Gram matrix with an intercept over every column, and cross-products with each y."""
    p = R.shape[1] + 1
    G = np.zeros((p, p))
    b = [np.zeros(p) for _ in ys]
    for a in range(0, len(rows), chunk):
        idx = rows[a:a + chunk]
        A = np.empty((len(idx), p))
        A[:, 0] = 1.0
        A[:, 1:] = R[idx]
        G += A.T @ A
        for j, y in enumerate(ys):
            yy = y[idx]
            ok = np.isfinite(yy)
            b[j] += A[ok].T @ yy[ok] if not ok.all() else A.T @ yy
    return G, b


def fit_block(data: Mapping[str, Any], cols: Mapping[str, list[int]], train_rows: np.ndarray,
              models, logit_models=(), warm: dict | None = None,
              fit_sector: bool = True) -> dict[str, Any]:
    """Every model's rank-linear fit for ``rel_spy`` (and ``rel_sector``), and the logistic fit
    of the drawdown event for ``logit_models``, all on the identical training rows."""
    R = data["R"]
    ys = [data["y_spy"]] + ([data["y_sec"]] if fit_sector else [])
    sector_ok = fit_sector and bool(np.isfinite(data["y_sec"][train_rows]).all())
    G, b = _gram_rows(R, train_rows, ys)
    out: dict[str, Any] = {"ols_spy": {}, "ols_sec": {}, "logit": {}}
    for m in models:
        cidx = [0] + [c + 1 for c in cols[m]]
        Gm = G[np.ix_(cidx, cidx)]
        out["ols_spy"][m] = np.linalg.lstsq(Gm, b[0][cidx], rcond=None)[0]
        if sector_ok:
            out["ols_sec"][m] = np.linalg.lstsq(Gm, b[1][cidx], rcond=None)[0]
    warm = warm if warm is not None else {}
    for m in logit_models:
        A = wf._with_intercept(R[train_rows][:, cols[m]])
        out["logit"][m] = wf.fit_logit(A, data["event"][train_rows], warm.get(m))
        del A
    return out


def _score(Rt: np.ndarray, cols: list[int], beta: np.ndarray) -> np.ndarray:
    return Rt[:, cols] @ beta[1:] + beta[0]


def _spread(s: np.ndarray, raw: np.ndarray) -> float:
    top = wf._deepest(s, SPREAD_FRACTION, largest=True)
    bot = wf._deepest(s, SPREAD_FRACTION)
    if not (top.any() and bot.any()):
        return float("nan")
    return float(raw[top].mean() - raw[bot].mean())


METRICS = ("ic_spy", "spread_spy", "ic_sec", "spread_sec", "ic_spy_audited", "capture", "brier")
LOSO_PAIRS = (("A", "Bstar"), ("I", "A"))


def score_group(data: Mapping[str, Any], cols: Mapping[str, list[int]], blocks, *, models=MODELS,
                logit_models=(), train_start: str = TRAIN_START, loso_pairs=LOSO_PAIRS,
                fit_sector: bool = True) -> dict[str, Any]:
    """§3/§5/§6: fit each model once before each block on every formation date from
    ``train_start`` whose label exits before the block's first test date, then score the
    block's dates. Per date and model: rank IC and top-minus-bottom-tenth spread on
    ``rel_spy`` and ``rel_sector``; for the logistic models capture and Brier score; for the
    LOSO pairs the IC difference with each sector's cases removed, without refitting."""
    if data.get("n_dates", 0) == 0:
        return {"n_dates": 0, "blocks": []}
    R, start, dates = data["R"], data["start"], data["dates"]
    form, exit_, sec = data["form"], data["exit"], data["sec"]
    K = len(SECTORS)
    per_date = {m: {k: [] for k in METRICS} for m in models}
    pooled = {m: {"p": [], "e": []} for m in logit_models}
    loso_pairs = tuple(p for p in loso_pairs if p[0] in models and p[1] in models)
    loso = {pair: [] for pair in loso_pairs}
    out_dates, out_block, out_sign, out_n, out_unl, info, fits_by_block = [], [], [], [], [], [], {}
    warm: dict[str, np.ndarray] = {}
    for name, lo, hi in blocks:
        in_block = (dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi))
        test = np.flatnonzero(in_block)
        if not len(test):
            info.append({"block": name, "n_dates": 0})
            continue
        train_mask = (dates >= pd.Timestamp(train_start)) & (exit_ < form[test[0]])
        if int(train_mask.sum()) < MIN_TRAIN_DATES:
            info.append({"block": name, "n_dates": int(len(test)), "skipped": "short_training",
                         "train_dates": int(train_mask.sum())})
            continue
        if np.flatnonzero(train_mask).max() >= test[0]:
            raise ValueError("a training date is not before the block")
        tr = _train_rows(data, train_mask)
        fits = fit_block(data, cols, tr, models, logit_models, warm, fit_sector)
        warm.update(fits["logit"])
        fits_by_block[name] = {kind: {m: [float(v) for v in beta] for m, beta in d.items()}
                               for kind, d in fits.items()}
        info.append({"block": name, "n_dates": int(len(test)), "first": str(dates[test[0]])[:10],
                     "last": str(dates[test[-1]])[:10], "train_dates": int(train_mask.sum()),
                     "train_rows": int(len(tr)),
                     "train_first": str(dates[np.flatnonzero(train_mask)[0]])[:10],
                     "train_last": str(dates[np.flatnonzero(train_mask)[-1]])[:10]})
        for t in test:
            sl = slice(int(start[t]), int(start[t + 1]))
            Rt, y, raw = R[sl], data["y_spy"][sl], data["raw_spy"][sl]
            ysec, rawsec, ev, sec_t, aud = (data["y_sec"][sl], data["raw_sec"][sl],
                                            data["event"][sl], sec[sl], data["audited"][sl])
            sector_ok = bool(np.isfinite(ysec).all()) and bool(fits["ols_sec"])
            scores = {}
            for m in models:
                s = _score(Rt, cols[m], fits["ols_spy"][m])
                scores[m] = s
                pdm = per_date[m]
                pdm["ic_spy"].append(wf._spearman(s, y))
                pdm["spread_spy"].append(_spread(s, raw))
                if sector_ok:
                    ss = _score(Rt, cols[m], fits["ols_sec"][m])
                    pdm["ic_sec"].append(wf._spearman(ss, ysec))
                    pdm["spread_sec"].append(_spread(ss, rawsec))
                else:
                    pdm["ic_sec"].append(np.nan)
                    pdm["spread_sec"].append(np.nan)
                pdm["ic_spy_audited"].append(wf._spearman(s[aud], y[aud])
                                             if int(aud.sum()) >= MIN_CASES else np.nan)
                if m in logit_models:
                    p = wf._sigmoid(_score(Rt, cols[m], fits["logit"][m]))
                    flag = wf._deepest(p, FLAG_FRACTION, largest=True)
                    pdm["capture"].append(float(ev[flag].mean()) if flag.any() else np.nan)
                    pdm["brier"].append(float(((p - ev) ** 2).mean()))
                    pooled[m]["p"].append(p)
                    pooled[m]["e"].append(ev)
                else:
                    pdm["capture"].append(np.nan)
                    pdm["brier"].append(np.nan)
            for m1, m2 in loso_pairs:
                row = []
                for k in range(K):
                    keep = sec_t != k
                    if int(keep.sum()) >= MIN_CASES // 2:
                        row.append(wf._spearman(scores[m1][keep], y[keep])
                                   - wf._spearman(scores[m2][keep], y[keep]))
                    else:
                        row.append(np.nan)
                loso[(m1, m2)].append(row)
            out_dates.append(dates[t])
            out_block.append(name)
            out_sign.append(float(data["spy_sign"][t]))
            out_n.append(int(data["n_cases"][t]))
            out_unl.append(int(data["n_unlabelled"][t]))
    return {"n_dates": len(out_dates),
            "per_date": {m: {k: np.asarray(v, float) for k, v in d.items()} for m, d in per_date.items()},
            "pooled": {m: {k: (np.concatenate(v) if v else np.zeros(0)) for k, v in d.items()}
                       for m, d in pooled.items()},
            "loso": {pair: np.asarray(v, float).reshape(-1, K) for pair, v in loso.items()},
            "dates": pd.DatetimeIndex(out_dates), "block": np.asarray(out_block, object),
            "spy_sign": np.asarray(out_sign), "n_cases": np.asarray(out_n),
            "n_unlabelled": np.asarray(out_unl), "blocks": info, "fits": fits_by_block}


# ---- the test of a mean, validity, power -------------------------------------------------------
def lr_variance(s: np.ndarray, horizon: int, step: int = STEP) -> tuple[float, int]:
    """B2 §6's cosine long-run variance with the family's degrees of freedom (imported rule)."""
    s = np.asarray(s, float)
    n = len(s)
    df = wf.ewc_df(n, horizon, step)
    grid = (np.arange(1, n + 1) - 0.5) / n
    lam = math.sqrt(2.0 / n) * (np.cos(np.pi * np.outer(np.arange(1, df + 1), grid)) @ s)
    return float((lam ** 2).mean()), df


def valid_gate(n: int, horizon: int, step: int = STEP) -> bool:
    """§6: a cell may gate only where floor(n / (2q)) >= 4, q = ceil(h / step)."""
    q = max(1, math.ceil(horizon / step))
    return n // (2 * q) >= wf.EWC_MIN_DF


def series_summary(s: np.ndarray, horizon: int, block_labels=None, block_order=()) -> dict[str, Any]:
    s = np.asarray(s, float)
    ok = np.isfinite(s)
    s = s[ok]
    n = int(len(s))
    out: dict[str, Any] = {"n": n, "mean": None, "sd": None, "t": None, "df": None,
                           "p_one_sided": None, "sigma_lr": None, "valid_gate": valid_gate(n, horizon),
                           "blocks": {}, "blocks_positive": 0, "blocks_scored": 0}
    if n < 2:
        return out
    t, df, p = wf.ewc_test(s, horizon, STEP)
    omega, _ = lr_variance(s, horizon)
    out.update({"mean": float(s.mean()), "sd": float(s.std()), "t": t, "df": int(df),
                "p_one_sided": p, "sigma_lr": math.sqrt(omega) if omega > 0 else None})
    if block_labels is not None:
        bl = np.asarray(block_labels, object)[ok]
        for name in block_order:
            m = bl == name
            if m.any():
                mean = float(s[m].mean())
                out["blocks"][name] = {"n": int(m.sum()), "mean": mean, "positive": mean > 0}
        out["blocks_scored"] = len(out["blocks"])
        out["blocks_positive"] = sum(1 for v in out["blocks"].values() if v["positive"])
    return out


def _phi(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def t_quantile(q: float, df: int) -> float:
    """Inverse of Student's t upper tail: the x with P(T > x) = 1 - q, by bisection."""
    lo, hi = 0.0, 1.0
    while wf.student_t_sf(hi, df) > 1.0 - q:
        hi *= 2.0
        if hi > 1e6:
            raise ValueError("t quantile out of range")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if wf.student_t_sf(mid, df) > 1.0 - q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def nct_cdf(t: float, df: int, delta: float, tol: float = 1e-13, max_terms: int = 20000) -> float:
    """P(T <= t) for the noncentral t (Lenth 1989, AS 243), with the incomplete beta already in
    the family's walk-forward module; no scipy."""
    if t < 0:
        return 1.0 - nct_cdf(-t, df, -delta, tol, max_terms)
    if t == 0:
        return _phi(-delta)
    x = t * t / (t * t + df)
    lam = 0.5 * delta * delta
    total = 0.0
    log_lam = math.log(lam) if lam > 0 else -math.inf
    for j in range(max_terms):
        lp = -lam + (j * log_lam if lam > 0 else (0.0 if j == 0 else -math.inf)) - math.lgamma(j + 1)
        lq = -lam + (j * log_lam if lam > 0 else (0.0 if j == 0 else -math.inf)) - math.lgamma(j + 1.5)
        pj = math.exp(lp) if lp > -745 else 0.0
        qj = (delta / math.sqrt(2.0)) * (math.exp(lq) if lq > -745 else 0.0)
        term = pj * wf._betainc(j + 0.5, 0.5 * df, x) + qj * wf._betainc(j + 1.0, 0.5 * df, x)
        total += term
        if j > lam and abs(term) < tol:
            break
    return min(1.0, max(0.0, _phi(-delta) + 0.5 * total))


def power_at(n: int, horizon: int, delta: float, sigma_lr: float, level: float = P_GATE) -> float:
    """Power of the family's one-sided test at ``level`` with ν(n) degrees of freedom against a
    true mean ``delta`` when the per-date series has long-run standard deviation ``sigma_lr``."""
    df = wf.ewc_df(n, horizon, STEP)
    crit = t_quantile(1.0 - level, df)
    return 1.0 - nct_cdf(crit, df, delta * math.sqrt(n) / sigma_lr)


def n_read_for(dev_mean: float, sigma_lr: float, horizon: int) -> dict[str, Any]:
    """§6 power rule: δ* = max(0.008, 0.5 × development mean); the smallest n in {48, 96, 144}
    with power >= 0.80; futile otherwise (with the n it would have needed, for the readout)."""
    delta = max(DELTA_FLOOR, 0.5 * dev_mean)
    power = {n: power_at(n, horizon, delta, sigma_lr) for n in N_READ_SET}
    for n in N_READ_SET:
        if power[n] >= POWER_TARGET:
            return {"delta_star": delta, "sigma_lr": sigma_lr, "power": power, "n_read": n,
                    "futile": False}
    needed = None
    for n in range(N_READ_SET[-1] + STEP, 5000, STEP):
        if power_at(n, horizon, delta, sigma_lr) >= POWER_TARGET:
            needed = n
            break
    return {"delta_star": delta, "sigma_lr": sigma_lr, "power": power, "n_read": None,
            "futile": True, "n_needed": needed}


# ---- summaries, selection, decision --------------------------------------------------------------
def _diff(scored: Mapping[str, Any], m1: str, m2: str | None, metric: str) -> np.ndarray:
    a = scored["per_date"][m1][metric]
    return a - (scored["per_date"][m2][metric] if m2 else 0.0)


def summarise(scored: Mapping[str, Any], horizon: int, which: str = "test",
              pairs=DIFFERENCES) -> dict[str, Any]:
    """Per-model means and per-difference summaries over the gated blocks (``which="test"``)
    or the early blocks (``"early"``); every number is DEVELOPMENT."""
    if scored.get("n_dates", 0) == 0:
        return {"n_dates": 0}
    names = {b[0] for b in (BLOCKS if which == "test" else EARLY_BLOCKS)}
    order = [b[0] for b in (BLOCKS if which == "test" else EARLY_BLOCKS)]
    m = np.array([b in names for b in scored["block"]], bool)
    if not m.any():
        return {"n_dates": 0}
    bl = scored["block"][m]
    out: dict[str, Any] = {"n_dates": int(m.sum()), "first": str(scored["dates"][m][0])[:10],
                           "last": str(scored["dates"][m][-1])[:10],
                           "mean_cases": float(scored["n_cases"][m].mean()),
                           "unlabelled_share": float((scored["n_unlabelled"][m] / scored["n_cases"][m]).mean()),
                           "models": {}, "pairs": {}, "loso": {}, "spy_sign_split": {}}
    for model, d in scored["per_date"].items():
        out["models"][model] = {k: (None if not np.isfinite(v[m]).any() else float(np.nanmean(v[m])))
                                for k, v in d.items()}
        if model in scored["pooled"] and len(scored["pooled"][model]["p"]):
            pm = np.array([b in names for b in scored["block"]], bool)
            # pooled arrays are concatenated per date; rebuild the mask per case
            counts = scored["n_cases"]
            case_mask = np.repeat(pm, counts)
            p, e = scored["pooled"][model]["p"], scored["pooled"][model]["e"]
            if len(case_mask) == len(p):
                out["models"][model]["calibration"] = wf._calibration(p[case_mask], e[case_mask])
    for m1, m2 in pairs:
        if m1 not in scored["per_date"] or (m2 is not None and m2 not in scored["per_date"]):
            continue
        key = f"{m1}-{m2}" if m2 else f"{m1}-0"
        out["pairs"][key] = {
            "ic": series_summary(_diff(scored, m1, m2, "ic_spy")[m], horizon, bl, order),
            "spread": series_summary(_diff(scored, m1, m2, "spread_spy")[m], horizon, bl, order),
            "ic_sector_label": series_summary(_diff(scored, m1, m2, "ic_sec")[m], horizon, bl, order),
            "ic_audited": series_summary(_diff(scored, m1, m2, "ic_spy_audited")[m], horizon, bl, order),
        }
        if m1 in scored["per_date"] and m2 in scored["per_date"] and "capture" in scored["per_date"][m1]:
            cap = _diff(scored, m1, m2, "capture")[m]
            if np.isfinite(cap).any():
                out["pairs"][key]["capture"] = series_summary(cap, horizon, bl, order)
                out["pairs"][key]["brier"] = series_summary(_diff(scored, m1, m2, "brier")[m], horizon, bl, order)
    for (m1, m2), arr in scored["loso"].items():
        a = arr[m]
        means = np.nanmean(a, axis=0) if len(a) else np.full(len(SECTORS), np.nan)
        full = _diff(scored, m1, m2, "ic_spy")[m]
        out["loso"][f"{m1}-{m2}"] = {
            "removed": {SECTORS[k]: (None if not np.isfinite(means[k]) else float(means[k]))
                        for k in range(len(SECTORS))},
            "all_positive": bool(np.isfinite(means).all() and (means > 0).all()),
            "contribution": {SECTORS[k]: (None if not np.isfinite(means[k])
                                          else float(np.nanmean(full) - means[k]))
                             for k in range(len(SECTORS))}}
    sign = scored["spy_sign"][m]
    d = _diff(scored, "A", "Bstar", "ic_spy")[m] if "A" in scored["per_date"] and "Bstar" in scored["per_date"] else None
    if d is not None:
        for label, sel in (("spy_up", sign > 0), ("spy_down", sign <= 0)):
            out["spy_sign_split"][label] = {"n": int(sel.sum()),
                                            "mean_A_minus_Bstar": (float(d[sel].mean()) if sel.any() else None)}
    return out


def cell_key(cell) -> str:
    label, h, m1, m2 = cell
    return f"{label}_{h}:{m1}-{m2}"


def select_cells(primary: Mapping[int, Any], ni: Mapping[int, Any]) -> dict[str, Any]:
    """§7.1: the five conditions per cell on the T1-T5 dates; a cell is carried on all five
    and on the validity rule of §6. ``primary[h]`` / ``ni[h]`` are ``summarise`` outputs."""
    out = {}
    for cell in CELLS:
        label, h, m1, m2 = cell
        key = f"{m1}-{m2}"
        S = primary.get(h, {}).get("pairs", {}).get(key, {}).get("ic")
        L = primary.get(h, {}).get("loso", {}).get(key)
        B = ni.get(h, {}).get("pairs", {}).get(key, {}).get("ic")
        if not S or S.get("mean") is None:
            out[cell_key(cell)] = {"carried": False, "why": "no development series", "cell": list(cell)}
            continue
        cond = {
            "i_mean": S["mean"] >= SELECT_MEAN_MIN,
            "ii_p": S["p_one_sided"] is not None and S["p_one_sided"] <= SELECT_P_MAX,
            "iii_blocks": S["blocks_positive"] >= SELECT_BLOCKS_MIN,
            "iv_bracket_ni_sign": bool(B and B.get("mean") is not None and (B["mean"] > 0) == (S["mean"] > 0)),
            "v_leave_one_sector_out": bool(L and L["all_positive"]),
            "valid_gate": bool(S["valid_gate"]),
        }
        out[cell_key(cell)] = {"cell": list(cell), "conditions": cond, "carried": all(cond.values()),
                               "mean": S["mean"], "p_one_sided": S["p_one_sided"], "n": S["n"],
                               "blocks_positive": S["blocks_positive"], "blocks_scored": S["blocks_scored"],
                               "sigma_lr": S["sigma_lr"],
                               "bracket_ni_mean": (B or {}).get("mean"),
                               "loso_removed": (L or {}).get("removed")}
    return out


def power_rule(selection: Mapping[str, Any]) -> dict[str, Any]:
    """§6: n_read per carried cell; the read size is the primary's."""
    out: dict[str, Any] = {"cells": {}, "n_read": None, "primary_futile": None}
    for key, sel in selection.items():
        if not sel.get("carried"):
            continue
        h = sel["cell"][1]
        if sel.get("sigma_lr") is None:
            out["cells"][key] = {"futile": True, "why": "no long-run variance"}
            continue
        out["cells"][key] = n_read_for(sel["mean"], sel["sigma_lr"], h)
    pk = cell_key(PRIMARY)
    if pk in out["cells"]:
        out["n_read"] = out["cells"][pk]["n_read"]
        out["primary_futile"] = bool(out["cells"][pk]["futile"])
    return out


NULL_WORDING = ("The family stops at Wave C for the eleven-sector, as-of-now-labelled constructions "
                "of section 4 on this universe and these horizons. GICS industry-group or industry, "
                "basket and dynamic-theme constructions are untested and not closed.")
SCOPE_SENTENCE = ("Scope: eleven GICS sectors; as-of-now labels (era_correct False on every row); a "
                  "survivor-tilted labelled universe; these seven features, horizons 20 and 60 "
                  "sessions, and the rank-linear form.")
CREDIT_SENTENCE = ("Group information already contained in a member's own trailing returns and "
                   "volatility is not group persistence; this design credits only what is left "
                   "after B*.")
UNDERPOWERED_SENTENCE = ("Under the family's own test, the effect seen in development cannot be "
                         "confirmed in a forward window of at most 144 formation dates; it is "
                         "neither confirmed nor refuted.")


def decide(selection: Mapping[str, Any], power: Mapping[str, Any]) -> dict[str, Any]:
    """§8 C1 outcomes. None is a claim; every number upstream is DEVELOPMENT."""
    pk = cell_key(PRIMARY)
    primary = selection.get(pk, {})
    carried = [k for k, v in selection.items() if v.get("carried")]
    if not primary.get("carried"):
        return {"outcome": "C1-NULL", "carried": carried, "n_read": None,
                "wording": [NULL_WORDING, SCOPE_SENTENCE, CREDIT_SENTENCE]}
    if power.get("primary_futile"):
        return {"outcome": "C1-UNDERPOWERED", "carried": carried, "n_read": None,
                "wording": [NULL_WORDING, UNDERPOWERED_SENTENCE, SCOPE_SENTENCE, CREDIT_SENTENCE]}
    live = []
    for step, cell, floor in SEQUENCE:
        key = cell_key(cell)
        if key in carried and not power["cells"][key]["futile"] and (floor is None or power["n_read"] >= floor):
            live.append({"step": step, "cell": key})
    return {"outcome": "C1-CARRY", "carried": carried, "n_read": power["n_read"], "sequence": live,
            "wording": ["Development only. The constants block is written; the forward wait begins."]}


CONSTANTS_KEYS = ("schema", "carried_cells", "n_read", "surviving_group_features", "c1_result_sha256",
                  "freeze", "frozen_coefficients_sha256", "appended")


def constants_block(decision: Mapping[str, Any], power: Mapping[str, Any], selection: Mapping[str, Any],
                    surviving, c1_result_sha256: str, freeze: Mapping[str, Any],
                    frozen_coefficients_sha256: str) -> dict[str, Any]:
    """§6: the closed-list C2 constants block. Anything else voids the gating read."""
    cells = {}
    for item in decision.get("sequence", []):
        key = item["cell"]
        p = power["cells"][key]
        cells[key] = {"step": item["step"], "development_mean": selection[key]["mean"],
                      "sigma_lr": p["sigma_lr"], "delta_star": p["delta_star"], "n_read_cell": p["n_read"]}
    return {"schema": SCHEMA, "carried_cells": cells, "n_read": decision["n_read"],
            "surviving_group_features": list(surviving), "c1_result_sha256": c1_result_sha256,
            "freeze": {k: freeze[k] for k in ("commit", "committer_utc", "freeze_date", "interim_date",
                                              "first_confirmatory_rule", "read_rule")},
            "frozen_coefficients_sha256": frozen_coefficients_sha256, "appended": []}


def check_constants_block(block: Mapping[str, Any]) -> list[str]:
    """Violations of the closed list; an empty list means the block may gate."""
    bad = [f"unexpected key {k!r}" for k in block if k not in CONSTANTS_KEYS]
    bad += [f"missing key {k!r}" for k in CONSTANTS_KEYS if k not in block]
    for key, cell in (block.get("carried_cells") or {}).items():
        extra = set(cell) - {"step", "development_mean", "sigma_lr", "delta_star", "n_read_cell"}
        if extra:
            bad.append(f"cell {key}: unexpected {sorted(extra)}")
    for item in block.get("appended") or []:
        extra = set(item) - {"when", "membership_sha256", "sector_snapshot_sha256", "panel_sha256",
                             "coverage_sha256", "coverage"}
        if extra:
            bad.append(f"appended item: unexpected {sorted(extra)}")
    return bad


# ---- reproduction, the measurement, the one run ---------------------------------------------------
def reproduce_b2(panel: dict, inputs: dict, b2_result: Mapping[str, Any]) -> dict[str, Any]:
    """§5: rebuild B2's model B2 with B2's own assembly and scoring and stop unless the mean
    per-date rank IC equals the committed value to 1e-9 at both horizons."""
    out = {}
    for h, (want_mean, want_n) in B2_MEANS.items():
        committed = b2_result["horizons"][str(h)]["models"]["B2"]["ic"]
        if committed["mean"] != want_mean or committed["n_dates"] != want_n:
            raise tpp.PreregDrift(f"the pinned B2 result disagrees with the frozen constants at h={h}")
        data = wf.assemble(panel, inputs, h)
        scored = wf.score_blocks(data, h, wf.BLOCKS, models=("B2",))
        ic = scored["per_date"]["B2"]["ic"]
        mean, n = float(np.mean(ic)), int(len(ic))
        if n != want_n or abs(mean - want_mean) > REPRODUCTION_TOL:
            raise GroupRefused(f"B2 model B2 at h={h} reproduces {mean!r} over {n} dates, not the "
                               f"committed {want_mean!r} over {want_n}; nothing further is reported")
        out[str(h)] = {"mean": mean, "n_dates": n, "committed_mean": want_mean, "tolerance": REPRODUCTION_TOL}
        del data, scored
    return out


def frozen_coefficients(data: Mapping[str, Any], cols: Mapping[str, list[int]], models=MODELS,
                        logit_models=LOGIT_MODELS, train_start: str = TRAIN_START) -> dict[str, Any]:
    """§6 item 6: every model fitted once on every development formation date from
    ``train_start``. Every C1 label exits on or before the embargo session, which precedes the
    freeze commit, so no training label can overlap a confirmatory formation date."""
    if data.get("n_dates", 0) == 0:
        return {}
    mask = np.asarray(data["dates"] >= pd.Timestamp(train_start), bool)
    tr = _train_rows(data, mask)
    fits = fit_block(data, cols, tr, models, logit_models, None, True)
    return {"train_dates": int(mask.sum()), "train_rows": int(len(tr)),
            "columns": {m: [COLUMNS[c] for c in cols[m]] for m in models},
            "ols_spy": {m: [float(v) for v in b] for m, b in fits["ols_spy"].items()},
            "ols_sec": {m: [float(v) for v in b] for m, b in fits["ols_sec"].items()},
            "logit": {m: [float(v) for v in b] for m, b in fits["logit"].items()}}


def _coverage(gi: Mapping[str, Any], panel: dict) -> dict[str, Any]:
    names = panel["names"]
    sec = gi["sec"]
    return {"names": len(names), "labelled": int((sec >= 0).sum()), "unlabelled": int((sec < 0).sum()),
            "current": int(gi["current"].sum()), "group_dates": int(gi["group_date"].sum()),
            "formation_rows": int(len(panel["rows"])),
            "sector_fail_counts": {SECTORS[k]: int((~gi["sector_ok"][:, k]).sum()) for k in range(len(SECTORS))}}


def measure(panel: dict, inputs: dict, closes: pd.DataFrame, observed: pd.DataFrame,
            snapshot: Mapping[str, Any], mem: pd.DataFrame, b2_result: Mapping[str, Any], *,
            horizons=HORIZONS, brackets: bool = True) -> dict[str, Any]:
    """The whole C1 development pass. Order is the pre-registration's: reproduce B2, then
    group inputs, the redundancy rule, the primary at every horizon, the brackets at the gated
    horizons, the selection rule, the power rule, the decision, the frozen coefficients."""
    reproduction = reproduce_b2(panel, inputs, b2_result)
    sec, cur = sector_codes(panel["names"], snapshot)
    tier = tier_codes(panel["index"], panel["names"], mem)
    gi = group_inputs(closes, observed, panel, sec, tier, cur)
    red = redundancy(gi, panel)
    cols = column_map(red["surviving"])
    gi_cm = group_inputs(closes, observed, panel, sec, tier, cur, members="current") if brackets else None
    result: dict[str, Any] = {"schema": SCHEMA, "label": "DEVELOPMENT - C1 is a claim about nothing",
                              "reproduction": reproduction, "redundancy": red,
                              "coverage": _coverage(gi, panel), "horizons": {}, "frozen_coefficients": {}}
    primary_summaries, ni_summaries = {}, {}
    for h in horizons:
        data = assemble_group(panel, inputs, gi, h, surviving=red["surviving"])
        logit = LOGIT_MODELS if h in GATE_HORIZONS else ()
        scored = score_group(data, cols, BLOCKS + EARLY_BLOCKS, models=MODELS, logit_models=logit)
        rec: dict[str, Any] = {
            "n_dates": data.get("n_dates", 0), "embargoed_first": (data.get("embargoed") or [None])[0],
            "embargoed_count": len(data.get("embargoed") or []),
            "last_scored": (str(scored["dates"][-1])[:10] if scored.get("n_dates") else None),
            "group_failures": data.get("group_failures", []), "skipped": data.get("skipped", []),
            "blocks": scored.get("blocks", []),
            "test": summarise(scored, h, "test"), "early": summarise(scored, h, "early"),
            "brackets": {}}
        primary_summaries[h] = rec["test"]
        if h in GATE_HORIZONS:
            result["frozen_coefficients"][str(h)] = frozen_coefficients(data, cols)
        if brackets and h in GATE_HORIZONS:
            d_ni = assemble_group(panel, inputs, gi, h, bracket="NI", surviving=red["surviving"])
            s_ni = score_group(d_ni, cols, BLOCKS, models=BRACKET_MODELS, fit_sector=False)
            rec["brackets"]["NI"] = summarise(s_ni, h, "test", pairs=(("A", "Bstar"), ("I", "A")))
            ni_summaries[h] = rec["brackets"]["NI"]
            del d_ni, s_ni
            d_cm = assemble_group(panel, inputs, gi_cm, h, bracket="CM", surviving=red["surviving"])
            s_cm = score_group(d_cm, cols, BLOCKS, models=BRACKET_MODELS, fit_sector=False)
            rec["brackets"]["CM"] = summarise(s_cm, h, "test", pairs=(("A", "Bstar"), ("I", "A")))
            del d_cm, s_cm
            s_19 = score_group(data, cols, BLOCKS, models=BRACKET_MODELS, train_start=BRACKET_TRAIN_START,
                               fit_sector=False)
            rec["brackets"]["train_from_2019"] = summarise(s_19, h, "test", pairs=(("A", "Bstar"), ("I", "A")))
            del s_19
        result["horizons"][str(h)] = rec
        del data, scored
    selection = select_cells(primary_summaries, ni_summaries)
    power = power_rule(selection)
    decision = decide(selection, power)
    result.update({"selection": selection, "power": power, "decision": decision,
                   "frozen_coefficients_sha256": canonical_sha256(result["frozen_coefficients"]),
                   "surviving_group_features": list(red["surviving"])})
    return result


def load_real(breadth_dir: str | None, store_dir: str | None):
    """V2's repaired panel through the family's loaders; refuses any other panel or membership."""
    from research import trend_persistence_substrate as substrate
    closes, observed, printed, mem, provenance = substrate.load_repaired_panel(breadth_dir, store_dir)
    panel = tpp.build_panel(closes, mem, observed=observed, printed=printed,
                            store_sourced=provenance["store"]["names"])
    if panel["digest"] != V2_PANEL_SHA256:
        raise tpp.PreregDrift("the panel is not the one V2 was scored on; C1 was not run")
    mem_path = os.path.join(provenance["breadth_dir"], "sp1500_pit_membership.parquet")
    got = _sha256(mem_path)
    if got != MEMBERSHIP_SHA256:
        raise tpp.PreregDrift(f"membership {mem_path} hashes to {got}, not the pinned {MEMBERSHIP_SHA256}")
    return panel, wf.price_inputs(panel, closes, observed), closes, observed, mem, provenance


def run(*, breadth_dir: str | None = None, store_dir: str | None = None, sector_snapshot: str,
        coverage: str | None = None, retry_reason: str | None = None) -> dict[str, Any]:
    """The one C1 run, to its one fixed path. Refuses a second run, an uncommitted tree, a drifted
    pin, and records the attempt before any label is read (§6)."""
    pinned_prereg()
    b2 = pinned_b2_result()
    result_path = os.path.join(_HERE, RESULT_FILE)
    attempt_path = os.path.join(_HERE, ATTEMPT_FILE)
    if os.path.exists(result_path):
        raise tpp.HoldoutLocked(f"{RESULT_FILE} exists: C1 has been run and is not run again")
    attempts = []
    if os.path.exists(attempt_path):
        with open(attempt_path) as fh:
            attempts = json.load(fh)["attempts"]
        if not (retry_reason and retry_reason.strip()):
            raise tpp.HoldoutLocked(f"{ATTEMPT_FILE} records an attempt that left no result; another "
                                    "attempt needs a stated reason and is reported as a deviation")
    git = git_state()
    if not git["clean"]:
        raise tpp.PreregDrift("the tree has uncommitted changes; C1 runs from a commit")
    freeze = freeze_info()
    snapshot = load_sector_snapshot(sector_snapshot)
    if coverage is not None and _sha256(coverage) != COVERAGE_SHA256:
        raise tpp.PreregDrift(f"coverage receipt {coverage} is not the pinned {COVERAGE_SHA256}")
    code = code_sha256()
    attempts.append({"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                     "git_head": git["head"], "code_sha256": code, "prereg_sha256": PREREG_SHA256,
                     "b2_result_sha256": B2_RESULT_SHA256, "sector_snapshot_sha256": snapshot["sha256"],
                     "retry_reason": retry_reason.strip() if retry_reason else None})
    with open(attempt_path, "w") as fh:
        json.dump({"attempts": attempts}, fh, indent=1)
    panel, inputs, closes, observed, mem, provenance = load_real(breadth_dir, store_dir)
    out = measure(panel, inputs, closes, observed, snapshot, mem, b2)
    out.update({"universe": "sp1500_pit", "universe_names": len(panel["names"]), "provenance": provenance,
                "panel_sha256": panel["digest"], "prereg_sha256": PREREG_SHA256,
                "b2_result_sha256": B2_RESULT_SHA256, "membership_sha256": MEMBERSHIP_SHA256,
                "sector_snapshot": {k: snapshot[k] for k in ("sha256", "path", "n_rows", "era_correct_any")}
                | {"label_asof": str(snapshot["label_asof"])[:10]},
                "code_sha256": code, "git_head": git["head"], "freeze": freeze, "attempts": attempts})
    with open(result_path + ".tmp", "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    os.replace(result_path + ".tmp", result_path)
    if out["decision"]["outcome"] == "C1-CARRY":
        block = constants_block(out["decision"], out["power"], out["selection"], out["surviving_group_features"],
                                _sha256(result_path), freeze, out["frozen_coefficients_sha256"])
        bad = check_constants_block(block)
        if bad:
            raise GroupRefused(f"constants block is not the closed list: {bad}")
        with open(os.path.join(_HERE, CONSTANTS_FILE), "w") as fh:
            json.dump(block, fh, indent=1, sort_keys=True)
    return out


def readout(result: Mapping[str, Any]) -> str:
    """A short development readout; every line is DEVELOPMENT."""
    lines = [f"C1 {result['decision']['outcome']}  (DEVELOPMENT - a claim about nothing)"]
    lines += [f"  {w}" for w in result["decision"]["wording"]]
    red = result["redundancy"]
    lines.append(f"redundancy: dropped {red['dropped'] or 'none'}; surviving {list(red['surviving'])}")
    for key, sel in result["selection"].items():
        c = sel.get("conditions", {})
        lines.append(f"cell {key}: carried={sel.get('carried')} mean={sel.get('mean')} p={sel.get('p_one_sided')} "
                     f"n={sel.get('n')} blocks+={sel.get('blocks_positive')}/{sel.get('blocks_scored')} "
                     f"NI_mean={sel.get('bracket_ni_mean')} conditions={c}")
    for key, p in result["power"].get("cells", {}).items():
        lines.append(f"power {key}: delta*={p.get('delta_star')} sigma_lr={p.get('sigma_lr')} n_read={p.get('n_read')} "
                     f"futile={p.get('futile')} power={p.get('power')}")
    for h, rec in result["horizons"].items():
        t = rec["test"]
        pairs = t.get("pairs", {})
        ab = pairs.get("A-Bstar", {}).get("ic", {})
        lines.append(f"h={h}: dates={t.get('n_dates')} last_scored={rec['last_scored']} embargoed={rec['embargoed_count']} "
                     f"group_failures={len(rec['group_failures'])} A-B* ic mean={ab.get('mean')} p={ab.get('p_one_sided')} "
                     f"G-0 mean={pairs.get('G-0', {}).get('ic', {}).get('mean')} A-B mean={pairs.get('A-B', {}).get('ic', {}).get('mean')}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--breadth-dir", default=None)
    ap.add_argument("--store-dir", default=None)
    ap.add_argument("--sector-snapshot", required=True, help="path to sp1500_pit_sectors.parquet (pinned)")
    ap.add_argument("--coverage", default=None, help="path to _sp1500_pit_sectors_coverage.json (pinned)")
    ap.add_argument("--retry-reason", default=None)
    a = ap.parse_args(argv)
    out = run(breadth_dir=a.breadth_dir, store_dir=a.store_dir, sector_snapshot=a.sector_snapshot,
              coverage=a.coverage, retry_reason=a.retry_reason)
    print(readout(out), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
