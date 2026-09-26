"""Vol-managed / risk-parity position sizing for the conviction book — the one
PORTFOLIO upgrade that survived an honest net-of-cost backtest (Moreira-Muir:
+0.10-0.15 Sharpe with ZERO directional alpha; measured SPY 0.64->0.76, equal-weight
1.07->1.22 on the macro side, research/MAGICAL_SIGNALS_ROADMAP.md in the macro repo).

It decides HOW MUCH to own (risk), orthogonal to confluence (WHAT) and the entry gauge
(WHEN): bet LESS on high-volatility names, MORE on calm ones, and take more total gross
when the cross-sectional DISPERSION regime says stock-selection pays.

Reuses the macro engine's already-validated, point-in-time sizing rather than recomputing:
each name on the macro standout board carries `risk_sizing.size_mult` (inverse forecasted
vol x regime), and the board carries `dispersion_regime` (the selection-gross dial), read
from vendor/macro. The board is the PRIMARY (exact-key) size lens. When a name is OFF the
board (the selection/board universe mismatch — the book is AI/semis while the board's BUY
list is defensives/value), we do NOT silently degrade to a neutral 1.0 (that laundered an
inert lever as risk-managed sizing); instead we estimate an inverse-vol multiplier from the
name's own trailing realized-vol price series, clamped to the SAME band. Only a name with NO
price series at all degrades to exactly 1.0 (true fail-closed neutral). Risk lever ONLY: it
re-weights WITHIN the selected book and can never RAISE gross (see NEW-SIZE-1: the renorm
target is capped at the incoming invested total), never changes which names are in it.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_V = Path(__file__).resolve().parent.parent / "vendor" / "macro"
_MULT_CAP, _MULT_FLOOR = 1.6, 0.4      # per-name vol-multiplier clamp
_COVERAGE_FLOOR = 0.5                  # < this fraction of the book on-board => inert-lever diagnostic
_EQW_SHARE = 0.80                      # > this fraction sharing one weight => degenerate-equal-weight probe
_MIN_VOL_OBS = 40                      # a price series needs >= this many returns for a trustworthy vol


def _load(rel: str):
    p = _V / rel
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None


def _board_admissible(board: dict, asof: str | None) -> bool:
    """True iff this standout board may inform a decision bounded at ``asof``.

    ``site/factordata/us_standouts.json`` is a SINGLE CURRENT file that states the instant it
    represents (``as_of``); there is no dated archive of past boards. So the only truthful reading
    is whole-artifact: a board whose own ``as_of`` POST-DATES the decision cannot have been known
    then, and must not silently re-size a historical book. ``asof=None`` (unbounded / live) admits
    the board exactly as before — `asof` here is an ALREADY-RESOLVED binding boundary (the caller
    decides; see ``portfolio.conviction.build``), never inferred from the wall clock.

    A board missing ``as_of`` under a BOUND read is refused: absence of a date cannot prove
    pre-boundary provenance, and guessing would be manufacturing history.
    """
    if asof is None:
        return True
    board_asof = str((board or {}).get("as_of") or "")[:10]
    if not board_asof:
        log.debug("risk_sizing: standout board has no as_of — inadmissible at asof=%s", asof)
        return False
    if board_asof > str(asof)[:10]:
        log.debug("risk_sizing: standout board as_of=%s post-dates asof=%s — inert",
                  board_asof, asof)
        return False
    return True


def _index(asof: str | None = None) -> tuple[dict, dict]:
    """{ticker: size_mult} from the macro standout board + the dispersion regime dict.

    Bounded at ``asof``: a board that post-dates the decision (or carries no date to check)
    contributes NOTHING — an empty lens, which degrades every name to the neutral 1.0 / gross 1.0
    rather than laundering today's board as historical evidence."""
    w = _load("site/factordata/us_standouts.json") or {}
    if not _board_admissible(w, asof):
        return {}, {}
    mult: dict[str, float] = {}
    for sec in ("buy", "watch", "laggards"):
        for r in (w.get(sec) or []):
            rs = r.get("risk_sizing") or {}
            sm = rs.get("size_mult")
            if isinstance(sm, (int, float)) and r.get("ticker"):
                mult[r["ticker"]] = float(sm)
    return mult, (w.get("dispersion_regime") or {})


_CACHE: dict = {}
_ASOF_CACHE: dict[str, tuple[dict, dict]] = {}   # bounded reads, keyed by decision date


def _ensure():
    if "mult" not in _CACHE:
        _CACHE["mult"], _CACHE["regime"] = _index()


def _board(asof: str | None) -> tuple[dict, dict]:
    """(size_mult map, dispersion regime) for the decision boundary ``asof``.

    ``asof=None`` uses the pre-existing module cache untouched (so tests that seed ``_CACHE``
    directly, and the unbounded path, behave exactly as before). A BOUND read gets its own cache
    slot keyed on the date — without the key, a live build and a replay in one process would
    silently share one board."""
    if asof is None:
        _ensure()
        return _CACHE.get("mult") or {}, _CACHE.get("regime") or {}
    key = str(asof)[:10]
    if key not in _ASOF_CACHE:
        _ASOF_CACHE[key] = _index(key)
    return _ASOF_CACHE[key]


def _clamp_mult(x: float) -> float:
    return float(min(_MULT_CAP, max(_MULT_FLOOR, x)))


def vol_mult(ticker: str, asof: str | None = None) -> float:
    """Per-name vol-managed size multiplier (clamped) from the EXACT-key board lookup; 1.0 when the
    board has no row for the name. This is the PRIMARY path. Off-board names are handled by the
    on-the-fly inverse-vol fallback inside apply() (NEW-SIZE-2) — vol_mult() itself stays a pure,
    side-effect-free board reader so its semantics (and the existing golden tests) are unchanged.

    ``asof`` bounds WHICH board is read (see ``_board_admissible``); None is the unbounded read."""
    return _clamp_mult(_board(asof)[0].get(ticker, 1.0))


def on_board(ticker: str, asof: str | None = None) -> bool:
    """True iff the standout board admissible at ``asof`` carries a size_mult for this exact ticker
    key. A board inadmissible at that boundary puts EVERY name off-board, routing them to the
    point-in-time inverse-vol fallback instead of a laundered current multiplier."""
    return ticker in _board(asof)[0]


def selection_gross(asof: str | None = None) -> float:
    """The dispersion-regime gross dial for the whole book; 1.0 when absent. Only ever
    DE-grosses the long-only book (lean_out < 1); a favourable regime keeps full budget,
    it does not lever above it here."""
    g = (_board(asof)[1] or {}).get("gross_mult")
    return min(float(g), 1.0) if isinstance(g, (int, float)) else 1.0


def regime_state(asof: str | None = None) -> str | None:
    return (_board(asof)[1] or {}).get("state")


def reset_cache() -> None:
    _CACHE.clear()
    _ASOF_CACHE.clear()


# ── NEW-SIZE-2: on-the-fly inverse-vol fallback for OFF-BOARD names ──────────────────────────────
def _default_price_series(ticker: str):
    """Default price-series loader = the same vendored store safety.py reads (yahoo ETFs/SPY +
    breadth single-name parquet). Imported lazily + defensively so a missing pandas/vendor lib (or a
    test with no price store) degrades to None -> the caller falls back to the neutral 1.0."""
    try:
        from portfolio import paper_account
        return paper_account._fetch_price_series(ticker)
    except Exception:  # noqa: BLE001 — no price store => no fallback, degrade to neutral
        return None


def _slice_at(series, asof: str | None):
    """A date-indexed close series truncated at the decision boundary (observations AT or BEFORE
    ``asof``). ``asof=None`` returns the series untouched — the unbounded / live read.

    This is the one source in the sizing chain with genuine point-in-time evidence: the store hands
    back a DATE-INDEXED series, so slicing it is a truthful restatement of what was observable,
    not a guess. Mirrors the existing bot/phase2 idiom (``series[series.index <= asof]``). A series
    with no usable index degrades to the untouched series rather than raising."""
    if series is None or asof is None:
        return series
    try:
        return series[series.index <= str(asof)[:10]]
    except Exception:  # noqa: BLE001 — an unindexable series is left alone, never fabricated
        return series


def _realized_vol(series, lookback: int = 60, asof: str | None = None) -> float | None:
    """Trailing realized (std of daily log-ish pct-change) vol from a close series. Returns None when
    the series is absent or too short to trust (< _MIN_VOL_OBS returns) — the caller then degrades to
    the neutral 1.0, matching the invariant (no price -> no lever, never a fabricated one).

    ``asof`` truncates the series FIRST, so the trailing window ends at the decision boundary rather
    than at whatever the store happens to hold today."""
    if series is None:
        return None
    try:
        s = _slice_at(series, asof)
        if s is None:
            return None
        s = s.dropna().astype(float)
        if len(s) < 2:
            return None
        rets = s.pct_change().dropna()
        if len(rets) > lookback:
            rets = rets.iloc[-lookback:]
        if len(rets) < _MIN_VOL_OBS:
            return None
        v = float(rets.std())
        return v if v > 0 else None
    except Exception:  # noqa: BLE001
        return None


def _fallback_size_mults(off_board: list[dict],
                         price_series_fn: Callable[[str], object],
                         asof: str | None = None) -> dict[int, float]:
    """Inverse-vol size multipliers for the OFF-BOARD names, keyed by id(position).

    Inverse-vol vs the book MEDIAN realized vol (a higher-vol name gets a <1 multiplier, a calmer
    name >1), clamped to the SAME [_MULT_FLOOR, _MULT_CAP] band as the board lever. A name whose
    price series is missing/too-short degrades to exactly 1.0 (today's behaviour — true fail-closed
    neutral). This keeps the lever a pure WITHIN-book risk redistribution: NEW-SIZE-1 caps the renorm
    target at incoming gross, so estimating a >1 mult for a calm off-board name can never raise the
    book's gross — it only shifts relative weight away from the wilder names."""
    vols: dict[int, float] = {}
    for p in off_board:
        v = _realized_vol(price_series_fn(p.get("ticker", "")), asof=asof)
        if v is not None:
            vols[id(p)] = v
    if not vols:
        return {}
    # median of the names we COULD measure; the inverse-vol multiplier is normalised to it so the
    # book-median-vol name sits at ~1.0 and the lever is a pure dispersion around it.
    ordered = sorted(vols.values())
    n = len(ordered)
    med = ordered[n // 2] if n % 2 else 0.5 * (ordered[n // 2 - 1] + ordered[n // 2])
    if med <= 0:
        return {}
    out: dict[int, float] = {}
    for p in off_board:
        v = vols.get(id(p))
        out[id(p)] = _clamp_mult(med / v) if v else 1.0    # no series -> neutral 1.0
    return out


def _emit_diag(positions: list, record: dict) -> None:
    """Attach a sizing diagnostic to the book's _SizedBook.data_health (the existing runlog seam)
    and mirror it to the module logger. Best-effort + additive: it never mutates weights and never
    raises into the sizing path. `positions` may be a plain list (no data_health attribute) — then
    the logger mirror is the only surface, which is fine (degrade-to-today)."""
    try:
        log.warning("risk_sizing diagnostic: %s", record)
    except Exception:  # noqa: BLE001
        pass
    try:
        dh = getattr(positions, "data_health", None)
        if isinstance(dh, dict):
            dh.setdefault("risk_sizing_diagnostics", []).append(record)
        else:
            # a plain list: stash on the first position so a runlog consumer can still find it.
            if positions:
                first = positions[0]
                if isinstance(first, dict):
                    first.setdefault("risk_sizing_diagnostics", []).append(record)
    except Exception:  # noqa: BLE001
        pass


def apply(positions: list[dict], budget: float, name_cap: float = 0.08,
          price_series_fn: Callable[[str], object] | None = None,
          asof: str | None = None) -> list[dict]:
    """Re-size positions by risk: weight_i *= vol_mult_i (board lookup, or inverse-vol fallback for
    off-board names), scale the total invested by the selection-gross dial (de-gross in a poor
    selection regime, holding more cash), renormalize to that target, cap per name. Mutates + returns
    the list. Never changes membership — only how much of the budget each name takes.

    `price_series_fn` (DI): an override loader `ticker -> close Series | None` for the off-board
    inverse-vol fallback; defaults to the vendored price store. Injected in tests so no live path is
    referenced at test time.

    `asof` (optional) is the DECISION BOUNDARY and makes this stage point-in-time honest: the
    standout board is admitted only if its own `as_of` is at/before it (else the board lens is inert
    and every name takes the inverse-vol path), and every price series is truncated at it before the
    realized-vol window is measured. `asof=None` is the unbounded read — byte-identical to the
    pre-asof behaviour, which is also what the live daily run gets, since a board published today is
    at/before today and a series truncated at today is the whole series.
    """
    if not positions or budget <= 0:
        return positions
    price_series_fn = price_series_fn or _default_price_series

    # NEW-SIZE-2 part (2): off-board names get an on-the-fly inverse-vol multiplier instead of a
    # silent neutral 1.0. Exact-key board lookup stays the PRIMARY path; the fallback only fills the
    # names the board doesn't cover.
    off_board = [p for p in positions if not on_board(p.get("ticker", ""), asof)]
    fb = _fallback_size_mults(off_board, price_series_fn, asof) if off_board else {}

    def _mult_for(p: dict) -> float:
        tkr = p.get("ticker", "")
        if on_board(tkr, asof):
            return vol_mult(tkr, asof)
        return fb.get(id(p), 1.0)          # off-board: inverse-vol estimate, or neutral 1.0 (no series)

    # NEW-SIZE-2 part (1): coverage diagnostic. If < half the book is on the board, the primary vol
    # lever is largely inert — surface it (VISIBLE) rather than laundering it as neutral sizing.
    n = len(positions)
    n_on = n - len(off_board)
    coverage = (n_on / n) if n else 1.0
    if coverage < _COVERAGE_FLOOR:
        _emit_diag(positions, {
            "kind": "board_coverage_low",
            "coverage": round(coverage, 3),
            "n_on_board": n_on, "n_total": n,
            "n_fallback_estimated": len(fb), "asof": asof,
            "note": ("primary vol lens (macro board) covers <50% of the book; off-board names sized "
                     "by on-the-fly inverse-vol fallback where a price series exists, else neutral"),
        })

    raw = {}
    for p in positions:
        raw[id(p)] = max(0.0, float(p.get("weight", 0.0))) * _mult_for(p)
    tot = sum(raw.values())
    if tot <= 0:
        return positions

    # NEW-SIZE-3: degenerate equal-weight probe. If the vast majority of INPUT names share one
    # identical weight AND the vol multipliers carry ~no dispersion, the book is running pure
    # equal-weight (RC3 uniform-confluence x inert vol lever). We do NOT synthesize artificial
    # dispersion (that would fabricate conviction and violate the subtract-only invariant) — the
    # honest fix is the NEW-SIZE-2 fallback (restores the real vol lever) PLUS surfacing that the book
    # is equal-weight so it isn't mistaken for risk-managed sizing.
    in_weights = [max(0.0, float(p.get("weight", 0.0))) for p in positions]
    mults = [_mult_for(p) for p in positions]
    if n >= 3:
        from collections import Counter
        wshare = max(Counter(round(w, 6) for w in in_weights).values()) / n
        mult_spread = (max(mults) - min(mults)) if mults else 0.0
        if wshare > _EQW_SHARE and mult_spread <= 1e-6:
            _emit_diag(positions, {
                "kind": "degenerate_equal_weight",
                "shared_weight_fraction": round(wshare, 3),
                "vol_mult_spread": round(mult_spread, 6),
                "n_total": n,
                "note": ("book is running equal-weight: >80% of input names share one weight AND vol "
                         "dispersion ~0 — surfaced, not corrected (no synthetic dispersion added)"),
            })

    # ── NEW-SIZE-1: renorm is SCALE-DOWN-ONLY ────────────────────────────────────────────────────
    # The renorm target must never scale the book's gross UP — it may only scale DOWN to fit budget.
    # incoming_gross = the book's invested total BEFORE vol_mult (the sum of the pre-existing weights,
    # which already carry every upstream per-leg brake: the 0.7 initial-size catalyst haircut at
    # conviction.py, and any future ext_mult). Capping `target` at min(incoming_gross, budget)*gross
    # means vol_mult still REDISTRIBUTES weight across names (the risk lever is preserved) and
    # selection_gross can only DE-gross — but a book that arrived at ~0.0315 gross post-haircut stays
    # ~0.0315 and is never inflated back up to fill `budget`. Without this cap, `raw/tot*budget`
    # renormalises the post-haircut RELATIVE weights back up to the full budget, mathematically
    # cancelling the *0.7 (and it would erase ext_mult the same way). Renorm-down-only is the
    # invariant that lets every upstream subtract-only brake SURVIVE this stage.
    incoming_gross = sum(in_weights)
    target = min(incoming_gross, budget) * selection_gross(asof)
    for p in positions:
        w = min(raw[id(p)] / tot * target, name_cap)      # per-name name_cap clamp preserved
        p["weight"] = round(w, 4)
        p["vol_mult"] = round(_mult_for(p), 2)
    return positions
