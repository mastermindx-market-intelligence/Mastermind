"""POINT-IN-TIME honesty for a historical ``conviction.build(asof=...)`` — the split-clock guard.

THE DEFECT THESE PIN
--------------------
``build(..., asof=...)`` advertises a historical decision boundary, but every upstream data read
was wired to "now": ``candidates()`` is zero-arg (so ``prophet_feed.candidate_tickers()`` reads the
CURRENT artifact and measures staleness against ``date.today()``), and ``risk_sizing.apply`` had no
``asof`` at all (latest standout board + a realized-vol window taken from the END of whatever price
series exists today). So the same historical build returned different books depending on WHEN the
replay ran.

THE CONTRACT THEY ENFORCE
-------------------------
A historical build may consume only information legitimately available at its ``asof``:

  * PRICE SERIES (date-addressable -> true point-in-time): sliced strictly at ``<= asof``.
  * PROPHET INDEX + MACRO STANDOUT BOARD (a single CURRENT-ONLY file that self-dates): consumable
    only when the artifact's own ``asof``/``as_of`` is ``<= asof``; a later artifact is INERT with
    an explicit unavailable reason. It is NEVER re-interpreted plan-by-plan into a pseudo-history —
    a plan's phase/action/conviction is recomputed at the index's own asof, so filtering by
    ``_signal_date`` would import post-boundary judgment about a pre-boundary plan.
  * ``live=True`` (what ``bot/phase2`` passes) declares the opposite contract — ``asof`` is a LABEL
    and the build uses current evidence — and is byte-identical to the pre-asof behaviour. It has to
    be DECLARED: the live run supplies an ``asof`` too, and that ``asof`` is routinely older than the
    artifacts it must read (the Macro lanes publish on different cadences: regime 2026-09-15 vs the
    Prophet emit 2026-09-16), so any wall-clock guess would silently kill live sources.

These drive the REAL ``conviction.build`` → ``candidates()`` → ``prophet_feed`` → ``risk_sizing``
chain. Only the ARTIFACTS on disk, the price store, and the wall clock are substituted — the
substituted things ARE the variables under test. No method-level stub short-circuits the chain.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

import bot  # noqa: F401
from portfolio import conviction, lenses, prophet_feed, risk_sizing

pd = pytest.importorskip("pandas")

# The historical decision boundary every test in this file replays.
ASOF = "2026-07-20"


# ── fixture builders ─────────────────────────────────────────────────────────
def _plan(asset: str, *, signal_date: str, conviction_score: float = 70.0,
          action: str = "enter", phase: str = "pre_trigger") -> dict:
    """A raw plan in the REAL prophet.index/v1 shape (flat ``targets``, labelled ``profit_plan``,
    underscore-prefixed ``_signal_date`` / ``_conviction_score``)."""
    return {
        "id": f"{asset}-BULL-{signal_date.replace('-', '')}",
        "asset": asset, "direction": "BULL",
        "entry": 100.0, "invalidation": 90.0, "trigger": 101.0,
        "targets": [120.0, 140.0],
        "profit_plan": [{"level": 120.0, "label": "T1", "action": "Scale out 40%", "status": "ACTIVE"},
                        {"level": 140.0, "label": "T2", "action": "Close", "status": "PENDING"}],
        "_r_unit": 10.0, "_conviction_score": conviction_score, "_signal_date": signal_date,
        "phase": phase, "management_confidence": 55.0, "recommended_action": action,
        "thesis": f"{asset} offline fixture",
    }


def _write_prophet(root, *, asof: str, plans: list[dict]) -> None:
    """Write a prophet.index/v1 artifact into a tmp vendor root."""
    p = root / "site" / "prophet"
    p.mkdir(parents=True, exist_ok=True)
    (p / "index.json").write_text(json.dumps({
        "schema": "prophet.index/v1", "asof": asof, "cadence": "nightly-EOD",
        "authority_tier": "display", "gate_go": False,
        "plan_count": len(plans), "plans": plans,
    }))


def _write_standouts(root, *, as_of: str, rows: list[tuple[str, float]],
                     gross_mult: float = 1.0) -> None:
    """Write a us_standouts board carrying per-name ``risk_sizing.size_mult`` + dispersion regime."""
    p = root / "site" / "factordata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "us_standouts.json").write_text(json.dumps({
        "as_of": as_of, "gate_go": True,
        "buy": [{"ticker": t, "risk_sizing": {"size_mult": m}} for t, m in rows],
        "watch": [], "laggards": [],
        "dispersion_regime": {"gross_mult": gross_mult, "state": "neutral"},
    }))


def _series(start: str, closes: list[float]):
    """A date-indexed close Series starting at ``start`` (business-day spaced, like the store)."""
    idx = pd.bdate_range(start=start, periods=len(closes))
    return pd.Series(closes, index=idx)


def _fake_full(_t, kind="name"):
    """Deterministic ``lenses.full`` synthesis — an unambiguous gate PASS. The gate is not the
    variable under test here; the information CLOCK is."""
    return {
        "rows": [{"lens": "trend", "direction": "bull"},
                 {"lens": "sector_rs", "direction": "bull"}],
        "synthesis": {"size_authority": "up", "confluence": 0.60, "vetoes": [],
                      "bull": 3, "bear": 0, "data_degraded": False,
                      "stockdata_present": True, "price_downtrend": False, "divergences": []},
    }


@pytest.fixture
def pit(tmp_path, monkeypatch):
    """Quiesce every candidate source EXCEPT the one under test, and point all three modules at an
    empty tmp vendor root. Returns the root so a test can write the artifact it is probing.

    Only leaf DATA SOURCES are neutralized — ``candidates()``, ``prophet_feed.candidate_tickers()``,
    ``build()`` and ``risk_sizing.apply()`` all run for real."""
    root = tmp_path / "vendor" / "macro"
    (root / "site").mkdir(parents=True, exist_ok=True)

    # W8 entry/context assessors OFF: documented opt-out that restores the pre-W8 buy path exactly.
    # They are orthogonal to the information clock and would otherwise reach the live vendor store.
    monkeypatch.setenv("MASTERMIND_ENTRY_GATE", "0")
    monkeypatch.setenv("MASTERMIND_PROPHET_FEED", "1")

    for mod in (conviction, prophet_feed, risk_sizing):
        monkeypatch.setattr(mod, "_V", root, raising=False)
    monkeypatch.setattr(prophet_feed, "_ARTIFACT_PATH", root / "site" / "prophet" / "index.json")

    # additive sources other than the one under test contribute nothing
    monkeypatch.setattr(conviction, "regime_seed", lambda asof=None: [])
    monkeypatch.setattr(conviction, "nw_universe_scan", lambda asof=None: [])
    import brain.intake as _intake
    import brain.ledger as _ledger
    monkeypatch.setattr(_ledger, "all_theses", lambda *a, **k: [])
    monkeypatch.setattr(_intake, "tickers", lambda *a, **k: [])

    monkeypatch.setattr(lenses, "full", _fake_full)
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    yield root
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()


def _freeze_today(monkeypatch, iso: str) -> None:
    """Move the WALL CLOCK seen by prophet_feed, leaving the artifact and the asof untouched.

    Under the repaired contract the wall clock must not affect a BOUND read at all; these tests move
    it precisely to prove that."""
    real = date

    class _D(real):                     # noqa: D401 — a date whose today() is pinned
        @classmethod
        def today(cls):
            return real.fromisoformat(iso)

    monkeypatch.setattr(prophet_feed, "date", _D)


def _book(**kw):
    """Run a real build and return {ticker: weight}. Bound (point-in-time) unless ``live=True``."""
    sized, _rej = conviction.build(0.30, name_cap=0.08, held=set(), **kw)
    return {p["ticker"]: p["weight"] for p in sized}


def _infotime(**kw):
    """The build's own information-time record (the honest 'what was I allowed to see')."""
    sized, _rej = conviction.build(0.30, name_cap=0.08, held=set(), **kw)
    return (sized.data_health or {}).get("information_time") or {}


# ── 1. a LATER Prophet artifact must not enter a historical candidate set ────────────────────────
def test_future_prophet_artifact_cannot_seed_a_historical_build(pit, monkeypatch):
    """Discriminator 1: a July decision reading a SEPTEMBER artifact must land exactly where a July
    decision reading NO artifact lands — i.e. the later file contributed nothing at all.

    Compared against the no-artifact build rather than against an earlier replay: replacing the
    artifact genuinely DESTROYS the July evidence (there is one file, no dated archive), so the two
    replays face different evidence. What must hold is that the September file contributes zero."""
    _freeze_today(monkeypatch, "2026-09-18")

    prophet_feed._reset_cache()
    no_artifact = _book(asof=ASOF)                        # nothing on disk at all

    _write_prophet(pit, asof="2026-09-16", plans=[_plan("AAAA", signal_date="2026-07-15"),
                                                  _plan("BBBB", signal_date="2026-09-11")])
    prophet_feed._reset_cache()
    with_future = _book(asof=ASOF)

    assert "BBBB" not in with_future, (
        "a plan signed 2026-09-11 entered a 2026-07-20 decision — future Prophet artifact leaked "
        f"into a historical candidate set (book={with_future})")
    assert with_future == no_artifact, (
        f"a post-boundary Prophet artifact changed a historical book: {no_artifact} -> "
        f"{with_future}")


def test_admissible_prophet_artifact_still_seeds_the_same_historical_build(pit, monkeypatch):
    """The mirror of the guard: a PRE-boundary artifact must still be consumed, so the refusal is a
    boundary rule and not a blanket disabling of Prophet under ``asof``."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15")])
    prophet_feed._reset_cache()
    assert "AAAA" in _book(asof=ASOF), (
        "an artifact dated the day BEFORE the decision was refused — the boundary rule has become "
        "a blanket refusal")


def test_build_reports_why_a_source_was_refused(pit, monkeypatch):
    """The refusal is EXPLICIT, not silent: a smaller historical book must be explainable from the
    build's own data_health record."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-09-16", plans=[_plan("BBBB", signal_date="2026-09-11")])
    _write_standouts(pit, as_of="2026-09-14", rows=[("ZZZZ", 1.6)])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()

    rec = _infotime(asof=ASOF)
    assert rec.get("bounded") is True and rec.get("asof") == ASOF
    assert rec["sources"]["prophet"]["reason"] == "future_artifact", rec["sources"]["prophet"]
    assert rec["sources"]["us_standouts"] == {
        "admitted": False, "artifact_asof": "2026-09-14", "reason": "post_dates_asof"}, rec
    # the undated current-only sources say so by name rather than looking like an empty queue
    assert rec["sources"]["thesis_ledger"]["reason"] == "current_only_source_at_past_boundary"
    assert rec["sources"]["neural_web_context"]["admitted"] is False


def test_future_prophet_artifact_is_inert_not_silently_partial(pit, monkeypatch):
    """The refusal must be HONEST: a post-boundary artifact contributes NOTHING (it is not mined
    plan-by-plan for pre-boundary ``_signal_date``s — that would import post-boundary judgment)."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-09-16", plans=[
        _plan("AAAA", signal_date="2026-07-15"),          # signed BEFORE asof — still not admissible
        _plan("BBBB", signal_date="2026-09-11"),
    ])
    prophet_feed._reset_cache()
    assert _book(asof=ASOF) == {}, (
        "an artifact dated after the decision boundary was mined for 'old enough' plans; the plan "
        "STATE in that file is recomputed at the index asof, so no plan in it is point-in-time")


# ── 2. freshness is relative to the BOUND DECISION DATE, not the wall clock ──────────────────────
def test_prophet_staleness_is_measured_against_asof_not_wall_clock(pit, monkeypatch):
    """Discriminator 2: identical artifact, identical ``asof`` — only ``date.today()`` moves.
    A 2026-07-19 artifact is one day old relative to a 2026-07-20 decision, forever."""
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15")])

    _freeze_today(monkeypatch, "2026-07-20")              # replayed the next morning
    prophet_feed._reset_cache()
    same_day = _book(asof=ASOF)

    _freeze_today(monkeypatch, "2026-09-18")              # replayed two months later
    prophet_feed._reset_cache()
    much_later = _book(asof=ASOF)

    assert same_day == much_later, (
        f"the same historical decision changed with the wall clock: {same_day} (replayed "
        f"2026-07-20) vs {much_later} (replayed 2026-09-18)")
    assert "AAAA" in same_day, (
        "a 1-day-old plan was not admissible to the decision it preceded — staleness is being "
        "measured against today() instead of the bound asof")


def test_plan_age_cut_is_measured_against_asof_not_wall_clock(pit, monkeypatch):
    """The per-plan ``_CANDIDATE_MAX_AGE_DAYS`` discovery cut has the same clock bug as the
    top-level staleness gate: a plan 5 days old at the decision is 5 days old forever."""
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15")])
    for wall in ("2026-07-20", "2026-09-18", "2027-01-05"):
        _freeze_today(monkeypatch, wall)
        prophet_feed._reset_cache()
        assert "AAAA" in _book(asof=ASOF), (
            f"plan aged out of a 2026-07-20 decision when replayed on {wall} — the age cut is "
            "keyed on the wall clock, not the decision boundary")


# ── 3. inverse-vol sizing must use no observation after the decision boundary ────────────────────
def test_inverse_vol_sizing_ignores_post_asof_price_observations(pit, monkeypatch):
    """Discriminator 3: two OFF-BOARD names sized by the realized-vol fallback. Append later
    observations that violently flip their relative vol; the historical book must not move."""
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("CALM", signal_date="2026-07-15"),
                                                  _plan("WILD", signal_date="2026-07-15")])
    _write_standouts(pit, as_of="2026-07-19", rows=[])         # both names OFF the board
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    _freeze_today(monkeypatch, "2026-09-18")   # a genuine REPLAY: the boundary is in the past

    # 101 business days from 2026-03-02 lands exactly on 2026-07-20, so the appended tail is
    # strictly AFTER the boundary and the bounded slice is byte-identical in both runs.
    start = "2026-03-02"
    calm = [100.0 + 0.10 * i for i in range(101)]               # smooth drift
    wild = [100.0 + 8.0 * (-1) ** i for i in range(101)]        # violent chop
    # everything at/before 2026-07-20; the appended tail lands strictly AFTER it
    tail_flip_calm = [180.0 + 25.0 * (-1) ** i for i in range(40)]   # CALM becomes the wild one
    tail_flat_wild = [108.0 + 0.05 * i for i in range(40)]           # WILD goes quiet

    def _pit_only(t):
        return {"CALM": _series(start, calm), "WILD": _series(start, wild)}.get(t)

    def _with_future(t):
        return {"CALM": _series(start, calm + tail_flip_calm),
                "WILD": _series(start, wild + tail_flat_wild)}.get(t)

    monkeypatch.setattr(risk_sizing, "_default_price_series", _pit_only)
    truncated = _book(asof=ASOF)

    monkeypatch.setattr(risk_sizing, "_default_price_series", _with_future)
    risk_sizing.reset_cache()
    extended = _book(asof=ASOF)

    assert truncated, "fixture did not produce a sized book — the discriminator would be vacuous"
    assert truncated == extended, (
        f"appending post-{ASOF} observations changed a historical book: {truncated} -> {extended}")


def test_live_build_still_sees_the_latest_price_observations(pit, monkeypatch):
    """Compatibility: with ``asof=None`` the same appended tail MUST still move the book — the
    slice is a historical bound, not a new permanent truncation."""
    _write_prophet(pit, asof=date.today().isoformat(),
                   plans=[_plan("CALM", signal_date=(date.today() - timedelta(days=2)).isoformat()),
                          _plan("WILD", signal_date=(date.today() - timedelta(days=2)).isoformat())])
    _write_standouts(pit, as_of=date.today().isoformat(), rows=[])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()

    start = (date.today() - timedelta(days=200)).isoformat()
    calm = [100.0 + 0.10 * i for i in range(100)]
    wild = [100.0 + 8.0 * (-1) ** i for i in range(100)]

    monkeypatch.setattr(risk_sizing, "_default_price_series",
                        lambda t: {"CALM": _series(start, calm),
                                   "WILD": _series(start, wild)}.get(t))
    base = _book()
    monkeypatch.setattr(risk_sizing, "_default_price_series",
                        lambda t: {"CALM": _series(start, calm + [180.0 + 25.0 * (-1) ** i
                                                                 for i in range(40)]),
                                   "WILD": _series(start, wild + [108.0 + 0.05 * i
                                                                  for i in range(40)])}.get(t))
    risk_sizing.reset_cache()
    moved = _book()
    assert base and moved and base != moved, (
        "a LIVE build stopped responding to new price observations — the asof slice leaked into "
        f"the same-day path (base={base}, moved={moved})")


# ── 4. the latest Macro board cannot masquerade as historical board evidence ─────────────────────
def test_latest_standout_board_cannot_masquerade_as_historical_evidence(pit, monkeypatch):
    """Discriminator 4: hold ``asof`` fixed and swap ONLY the current standout board (its
    membership AND its per-name ``size_mult``). A July decision must not read a September board."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15"),
                                                  _plan("CCCC", signal_date="2026-07-16")])

    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    monkeypatch.setattr(risk_sizing, "_default_price_series", lambda t: None)
    no_board = _book(asof=ASOF)                            # no board on disk at all

    # the nightly emit: different membership, different multipliers, different gross dial — all of
    # it published AFTER the decision being replayed
    _write_standouts(pit, as_of="2026-09-14", rows=[("AAAA", 0.4), ("ZZZZ", 1.6)], gross_mult=0.5)
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    with_future = _book(asof=ASOF)

    assert "ZZZZ" not in with_future, (
        f"a name off the SEPTEMBER buy board entered a July decision (book={with_future})")
    assert with_future == no_board, (
        f"the latest standout board silently re-sized a historical book: {no_board} -> "
        f"{with_future}")


def test_admissible_standout_board_still_sizes_a_historical_build(pit, monkeypatch):
    """Mirror: a board dated BEFORE the decision must still apply its multipliers, so the guard is
    a boundary rule rather than a blanket disabling of the board lens."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15"),
                                                  _plan("CCCC", signal_date="2026-07-16")])
    _write_standouts(pit, as_of="2026-07-19", rows=[("AAAA", 1.5), ("CCCC", 0.5)])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    monkeypatch.setattr(risk_sizing, "_default_price_series", lambda t: None)
    book = _book(asof=ASOF)
    assert book.get("AAAA", 0) > book.get("CCCC", 0), (
        f"a pre-boundary board stopped re-weighting the book: {book}")


# ── 5. the whole-chain determinism property ─────────────────────────────────────────────────────
def test_historical_build_is_reproducible_across_wall_clock_and_current_store(pit, monkeypatch):
    """The acceptance property, end to end: replay the SAME historical decision after the wall
    clock moved AND every current artifact was replaced. Same result, or the same explicit
    unavailable result — never a silently different book."""
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15")])
    _write_standouts(pit, as_of="2026-07-19", rows=[("AAAA", 1.2)])
    _freeze_today(monkeypatch, "2026-07-20")
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    monkeypatch.setattr(risk_sizing, "_default_price_series", lambda t: None)
    first = _book(asof=ASOF)

    for wall in ("2026-09-18", "2026-12-01", "2027-06-30"):
        _freeze_today(monkeypatch, wall)
        prophet_feed._reset_cache()
        risk_sizing.reset_cache()
        assert _book(asof=ASOF) == first, (
            f"the same historical decision, same store, produced a different book when replayed "
            f"on {wall}")


# ── 6. the declared LIVE contract is byte-identical to the pre-asof behaviour ────────────────────
def test_live_contract_still_consumes_current_evidence(pit, monkeypatch):
    """``live=True`` — the shape ``bot/phase2`` actually calls — must keep using CURRENT artifacts
    even when they post-date the ``asof`` label.

    This is the live-path regression that a wall-clock rule would have caused: the daily run labels
    the book with the regime date (2026-09-15) while the nightly Prophet emit is already stamped
    2026-09-16 and the standout board is stamped 2026-09-14. Binding that label would make the feed
    and the board inert in production."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-09-16", plans=[_plan("AAAA", signal_date="2026-09-15")])
    _write_standouts(pit, as_of="2026-09-14", rows=[("AAAA", 1.2)])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    monkeypatch.setattr(risk_sizing, "_default_price_series", lambda t: None)

    live = _book(asof="2026-09-15", live=True)
    assert "AAAA" in live, (
        "the live daily run lost its Prophet candidate because the regime date it labels the book "
        f"with is older than the nightly emit (book={live})")

    # and the same call WITHOUT the declaration is point-in-time: the later Prophet emit is refused
    # while the standout board (2026-09-14, genuinely pre-boundary) is still admitted.
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    rec = _infotime(asof="2026-09-15")
    assert rec["sources"]["prophet"]["reason"] == "future_artifact", rec["sources"]["prophet"]
    assert rec["sources"]["us_standouts"]["admitted"] is True, rec["sources"]["us_standouts"]


def test_live_contract_matches_the_unbounded_build_exactly(pit, monkeypatch):
    """`live=True` with a label and `asof=None` must produce the same book — i.e. the declaration
    removes the bound entirely rather than applying a softer one."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-09-16", plans=[_plan("AAAA", signal_date="2026-09-15"),
                                                  _plan("CCCC", signal_date="2026-09-14")])
    _write_standouts(pit, as_of="2026-09-14", rows=[("AAAA", 1.5), ("CCCC", 0.5)])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    monkeypatch.setattr(risk_sizing, "_default_price_series", lambda t: None)

    labelled = _book(asof="2026-09-15", live=True)
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    unbounded = _book()
    assert labelled == unbounded and labelled, (
        f"live-declared build diverged from the unbounded build: {labelled} vs {unbounded}")


def test_live_build_reports_every_source_as_admitted(pit, monkeypatch):
    """The information-time record must not cry wolf on a live build: with `live=True` nothing is
    bound, so every source reports admitted and `bounded` is False."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-09-16", plans=[_plan("AAAA", signal_date="2026-09-15")])
    _write_standouts(pit, as_of="2026-09-14", rows=[("AAAA", 1.2)])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()

    sized, _rej = conviction.build(0.30, name_cap=0.08, held=set(),
                                   asof="2026-09-15", live=True)
    rec = (sized.data_health or {}).get("information_time") or {}
    assert rec["asof"] == "2026-09-15", rec          # the label is still reported
    assert rec["bounded"] is False, rec              # ... but it did not bind
    assert rec["now_state_admissible"] is True, rec
    assert rec["sources"]["us_standouts"]["admitted"] is True, rec["sources"]["us_standouts"]
    assert rec["sources"]["prophet"]["available"] is True, rec["sources"]["prophet"]
    assert rec["sources"]["thesis_ledger"]["reason"] is None, rec["sources"]["thesis_ledger"]
