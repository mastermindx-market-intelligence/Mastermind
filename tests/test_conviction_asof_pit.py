"""Partial source bounds, explicit whole-decision refusal, and live compatibility.

The original PIT fixture disables entry/context and substitutes a PASS lenses result. It tests
component clocks and current-build mechanics, not a complete historical decision. Bounded
candidate/Prophet/sizing tests below call those actual owners directly. Whole-build tests instead
require typed refusal before any current read; a successful empty book is not acceptable.
Only None is unbounded. Valid dates/timestamps use calendar-day semantics, and malformed evidence
cannot become current evidence. Live=True remains an explicitly labelled current-source build.
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

    Entry/context is disabled and lenses is a PASS stub for LIVE mechanical controls only.
    Bounded component tests call their real owner; this fixture cannot certify historical builds."""
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
    """Run the real live/unbounded build with the explicit mechanical fixture above."""
    sized, _rej = conviction.build(0.30, name_cap=0.08, held=set(), **kw)
    return {p["ticker"]: p["weight"] for p in sized}


def _component_weights(tickers, *, asof):
    """Exercise real sizing on explicit synthetic positions, not a historical decision."""
    positions = [{"ticker": t, "weight": 0.04} for t in tickers]
    result = risk_sizing.apply(positions, 0.30, name_cap=0.08, asof=asof)
    return {p["ticker"]: p["weight"] for p in result}


# ── 1. a LATER Prophet artifact must not enter a historical candidate set ────────────────────────
def test_future_prophet_artifact_cannot_seed_bounded_candidates(pit, monkeypatch):
    """Discriminator 1: a July decision reading a SEPTEMBER artifact must land exactly where a July
    decision reading NO artifact lands — i.e. the later file contributed nothing at all.

    Compared against the no-artifact build rather than against an earlier replay: replacing the
    artifact genuinely DESTROYS the July evidence (there is one file, no dated archive), so the two
    replays face different evidence. What must hold is that the September file contributes zero."""
    _freeze_today(monkeypatch, "2026-09-18")

    prophet_feed._reset_cache()
    no_artifact = conviction.candidates(ASOF)              # nothing on disk at all

    _write_prophet(pit, asof="2026-09-16", plans=[_plan("AAAA", signal_date="2026-07-15"),
                                                  _plan("BBBB", signal_date="2026-09-11")])
    prophet_feed._reset_cache()
    with_future = conviction.candidates(ASOF)

    assert "BBBB" not in with_future, (
        "a plan signed 2026-09-11 entered a 2026-07-20 decision — future Prophet artifact leaked "
        f"into a historical candidate set (book={with_future})")
    assert with_future == no_artifact, (
        f"a post-boundary Prophet artifact changed a historical book: {no_artifact} -> "
        f"{with_future}")


def test_admissible_prophet_artifact_still_seeds_bounded_candidates(pit, monkeypatch):
    """The mirror of the guard: a PRE-boundary artifact must still be consumed, so the refusal is a
    boundary rule and not a blanket disabling of Prophet under ``asof``."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15")])
    prophet_feed._reset_cache()
    assert "AAAA" in conviction.candidates(ASOF), (
        "an artifact dated the day BEFORE the decision was refused — the boundary rule has become "
        "a blanket refusal")


def test_partial_source_diagnostics_report_refusal(pit, monkeypatch):
    """Component unavailability is explicit; it is not a successful historical build."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-09-16", plans=[_plan("BBBB", signal_date="2026-09-11")])
    _write_standouts(pit, as_of="2026-09-14", rows=[("ZZZZ", 1.6)])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()

    rec = conviction._information_time(ASOF, ASOF)
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
    assert conviction.candidates(ASOF) == [], (
        "an artifact dated after the decision boundary was mined for 'old enough' plans; the plan "
        "STATE in that file is recomputed at the index asof, so no plan in it is point-in-time")


# ── 2. freshness is relative to the BOUND DECISION DATE, not the wall clock ──────────────────────
def test_prophet_staleness_is_measured_against_asof_not_wall_clock(pit, monkeypatch):
    """Discriminator 2: identical artifact, identical ``asof`` — only ``date.today()`` moves.
    A 2026-07-19 artifact is one day old relative to a 2026-07-20 decision, forever."""
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15")])

    _freeze_today(monkeypatch, "2026-07-20")              # replayed the next morning
    prophet_feed._reset_cache()
    same_day = conviction.candidates(ASOF)

    _freeze_today(monkeypatch, "2026-09-18")              # replayed two months later
    prophet_feed._reset_cache()
    much_later = conviction.candidates(ASOF)

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
        assert "AAAA" in conviction.candidates(ASOF), (
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
    truncated = _component_weights(["CALM", "WILD"], asof=ASOF)

    monkeypatch.setattr(risk_sizing, "_default_price_series", _with_future)
    risk_sizing.reset_cache()
    extended = _component_weights(["CALM", "WILD"], asof=ASOF)

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
    no_board = _component_weights(["AAAA", "CCCC"], asof=ASOF)

    # the nightly emit: different membership, different multipliers, different gross dial — all of
    # it published AFTER the decision being replayed
    _write_standouts(pit, as_of="2026-09-14", rows=[("AAAA", 0.4), ("ZZZZ", 1.6)], gross_mult=0.5)
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    with_future = _component_weights(["AAAA", "CCCC"], asof=ASOF)

    assert "ZZZZ" not in conviction.candidates(ASOF), (
        f"a name off the SEPTEMBER buy board entered a July decision (book={with_future})")
    assert with_future == no_board, (
        f"the latest standout board silently re-sized a historical book: {no_board} -> "
        f"{with_future}")


def test_admissible_standout_board_still_sizes_bounded_positions(pit, monkeypatch):
    """Mirror: a board dated BEFORE the decision must still apply its multipliers, so the guard is
    a boundary rule rather than a blanket disabling of the board lens."""
    _freeze_today(monkeypatch, "2026-09-18")
    _write_prophet(pit, asof="2026-07-19", plans=[_plan("AAAA", signal_date="2026-07-15"),
                                                  _plan("CCCC", signal_date="2026-07-16")])
    _write_standouts(pit, as_of="2026-07-19", rows=[("AAAA", 1.5), ("CCCC", 0.5)])
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    monkeypatch.setattr(risk_sizing, "_default_price_series", lambda t: None)
    book = _component_weights(["AAAA", "CCCC"], asof=ASOF)
    assert book.get("AAAA", 0) > book.get("CCCC", 0), (
        f"a pre-boundary board stopped re-weighting the book: {book}")


# ── 5. the whole-chain determinism property ─────────────────────────────────────────────────────
def test_bounded_build_refusal_survives_current_store_and_clock_changes(pit, monkeypatch):
    """Later risk/stockdata/price evidence cannot produce a labelled historical decision."""
    reads = []

    def forbidden(*args, **kwargs):
        reads.append((args, kwargs))
        raise AssertionError("current evidence was read before historical refusal")

    monkeypatch.setenv("MASTERMIND_ENTRY_GATE", "1")
    monkeypatch.setattr(conviction, "candidates", forbidden)
    monkeypatch.setattr(lenses, "full", forbidden)
    monkeypatch.setattr(conviction, "_load", forbidden)
    monkeypatch.setattr(risk_sizing, "_default_price_series", forbidden)
    for wall, state, last in (("2026-07-20", "normal", 100),
                              ("2026-09-18", "risk_off", 10),
                              ("2027-06-30", "normal", 500)):
        _freeze_today(monkeypatch, wall)
        for rel, data in (("data/regime/latest.json", {"risk_radar": {"state": state}}),
                          ("site/stockdata/HELD.json", {"last": last})):
            p = pit / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data))
        with pytest.raises(RuntimeError, match="historical_decision_unsupported") as exc:
            conviction.build(0.30, asof=ASOF, held={"HELD"}, extra_candidates=["PROMOTED"])
        assert exc.value.reason == "historical_decision_unsupported"
        assert exc.value.asof == ASOF
    assert reads == []


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

    # Partial-source diagnostics retain their boundary meaning; they cannot certify a whole build.
    prophet_feed._reset_cache()
    risk_sizing.reset_cache()
    rec = conviction._information_time("2026-09-15", "2026-09-15")
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


@pytest.mark.parametrize("gate", ["0", "1"])
@pytest.mark.parametrize("bound", [ASOF, date.today().isoformat(), "2026-07-20T23:59:00+05:30"])
@pytest.mark.parametrize("names", [False, True])
def test_bounded_build_never_returns_successful_empty_targets(monkeypatch, gate, bound, names):
    reads = []

    def forbidden(*args, **kwargs):
        reads.append((args, kwargs))
        raise AssertionError("bounded build reached a current consumer")

    monkeypatch.setenv("MASTERMIND_ENTRY_GATE", gate)
    monkeypatch.setattr(conviction, "candidates", forbidden)
    monkeypatch.setattr(conviction, "_entry_gate_enabled", forbidden)
    monkeypatch.setattr(lenses, "full", forbidden)
    with pytest.raises(RuntimeError, match="historical_decision_unsupported") as exc:
        conviction.build(0.30, asof=bound, held={"HELD"} if names else set(),
                         extra_candidates=["PROMOTED"] if names else [])
    assert exc.value.reason == "historical_decision_unsupported"
    assert exc.value.asof == bound[:10]
    assert reads == []


_BAD_OFFSETS = ["2026-07-20T12:00:00+00:99", "2026-07-20T12:00:00-01:60",
                "2026-07-20T12:00:00+24:00"]
_BAD_BOUNDS = ["", "0", 0, 20260720, False, "2026-02-30", "2026-07-20junk",
               "2026-07-20T25:00:00", " 2026-07-20", "2026-07-20\n"] + _BAD_OFFSETS


@pytest.mark.parametrize("bound", _BAD_BOUNDS)
def test_invalid_build_boundary_is_not_unbounded(monkeypatch, bound):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid boundary reached current reads")

    monkeypatch.setattr(conviction, "_entry_gate_enabled", forbidden)
    monkeypatch.setattr(conviction, "candidates", forbidden)
    with pytest.raises(ValueError, match="invalid_asof"):
        conviction.build(0.30, asof=bound)


@pytest.mark.parametrize("bound", _BAD_BOUNDS)
def test_invalid_bound_cannot_use_current_artifact_or_primed_board_cache(pit, monkeypatch, bound):
    _freeze_today(monkeypatch, ASOF)
    _write_prophet(pit, asof=ASOF, plans=[_plan("AAAA", signal_date=ASOF)])
    _write_standouts(pit, as_of=ASOF, rows=[("AAAA", 1.6)])
    assert risk_sizing.vol_mult("AAAA", ASOF) == 1.6  # prime the valid-date cache
    assert prophet_feed.plan_for("AAAA", ASOF) is not None
    assert prophet_feed.availability(bound)["reason"] == "invalid_asof"
    assert prophet_feed.candidate_tickers(bound) == []
    assert prophet_feed.plan_for("AAAA", bound) is None
    assert conviction._us_standouts(asof=bound) == []
    assert risk_sizing.vol_mult("AAAA", bound) == 1.0
    assert risk_sizing.on_board("AAAA", bound) is False
    # None, in contrast to invalid supplied values, retains the actual live/current path.
    assert prophet_feed.plan_for("AAAA", None) is not None
    assert risk_sizing.vol_mult("AAAA", None) == 1.6


@pytest.mark.parametrize("stamp", [None, "", "0", 0, "2026-02-30", "2026-07-19garbage"] + _BAD_OFFSETS)
def test_unprovable_snapshot_dates_are_unavailable(pit, monkeypatch, stamp):
    _freeze_today(monkeypatch, ASOF)
    _write_prophet(pit, asof=stamp, plans=[_plan("AAAA", signal_date=ASOF)])
    _write_standouts(pit, as_of=stamp, rows=[("AAAA", 1.6)])
    assert prophet_feed.availability(ASOF)["reason"] == "artifact_asof_unparseable"
    assert conviction.candidates(ASOF) == []
    assert risk_sizing.vol_mult("AAAA", ASOF) == 1.0
    rec = conviction._information_time(ASOF, ASOF)
    assert rec["sources"]["us_standouts"]["reason"] == (
        "no_as_of" if stamp is None else "artifact_asof_unparseable")


@pytest.mark.parametrize("stamp", ["2026-07-19", ASOF, "2026-07-20T23:59:59Z",
                                    "2026-07-20 12:34:56.123+05:30"])
def test_valid_calendar_dates_and_timestamps_admit_partial_sources(pit, monkeypatch, stamp):
    _freeze_today(monkeypatch, "2027-01-01")
    _write_prophet(pit, asof=stamp, plans=[_plan("AAAA", signal_date=stamp)])
    _write_standouts(pit, as_of=stamp, rows=[("AAAA", 1.6)])
    assert prophet_feed.availability(ASOF)["available"] is True
    assert prophet_feed.plan_for("AAAA", ASOF) is not None
    assert "AAAA" in conviction.candidates(ASOF)
    assert risk_sizing.vol_mult("AAAA", ASOF) == 1.6


@pytest.mark.parametrize("stamp", [None, "", "0", 0, "2026-02-30", "2026-07-19junk",
                                    "2026-07-21"] + _BAD_OFFSETS)
def test_bounded_plan_geometry_requires_a_provable_signal_date(pit, monkeypatch, stamp):
    _freeze_today(monkeypatch, ASOF)
    plan = _plan("AAAA", signal_date=ASOF)
    plan["_signal_date"] = stamp
    _write_prophet(pit, asof=ASOF, plans=[plan])
    assert prophet_feed.availability(ASOF)["available"] is True
    assert prophet_feed.plans(ASOF) == []
    assert prophet_feed.plan_for("AAAA", ASOF) is None
    # The original current-plan geometry contract is preserved, including unknown age.
    assert prophet_feed.plan_for("AAAA") is not None


@pytest.mark.parametrize("kind", ["numeric", "malformed", "nat", "mixed"])
def test_unprovable_price_index_never_falls_back_to_full_series(kind):
    s = _series("2026-03-02", [100.0 + 8.0 * (-1) ** i for i in range(101)])
    if kind == "numeric":
        s.index = range(len(s))
    elif kind == "malformed":
        s.index = ["2026-07-19junk"] * len(s)
    elif kind == "nat":
        s.index = pd.DatetimeIndex([pd.NaT] * len(s))
    else:
        s.index = [*s.index[:-1], 0]
    assert risk_sizing._slice_at(s, ASOF) is None
    assert risk_sizing._realized_vol(s, asof=ASOF) is None
    assert risk_sizing._slice_at(s, None) is s
    assert risk_sizing._realized_vol(s) is not None


def test_unusable_index_and_selection_are_unavailable():
    class BrokenIndex:
        def __iter__(self):
            raise TypeError("index cannot prove dates")

    class Series:
        index = BrokenIndex()

    assert risk_sizing._slice_at(Series(), ASOF) is None

    class BrokenSelection:
        index = [ASOF]

        def __getitem__(self, key):
            raise TypeError("selection unavailable")

    assert risk_sizing._slice_at(BrokenSelection(), ASOF) is None


def test_dated_price_slice_preserves_calendar_day_and_rejects_bad_bound():
    s = pd.Series([100.0, 101.0, 102.0], index=pd.DatetimeIndex([
        "2026-07-19T23:00:00+02:00", "2026-07-20T23:00:00+02:00", "2026-07-21T00:00:00+02:00"]))
    assert list(risk_sizing._slice_at(s, ASOF)) == [100.0, 101.0]
    for bound in _BAD_BOUNDS:
        assert risk_sizing._slice_at(s, bound) is None


def test_actual_flagship_wrapper_cannot_queue_targets_after_failure():
    """Execute the actual wrapper AST with inert injected imports/run, never the portfolio engine."""
    import ast
    import builtins
    from pathlib import Path
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[1] / "bot" / "phase2.py"
    source = ast.parse(path.read_text())
    fn = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "run_flagship")
    for archived in (False, True):
        calls = []

        def failed_run(**kwargs):
            calls.append("run")
            raise RuntimeError("historical_decision_unsupported")

        def forbidden_pending(*args, **kwargs):
            calls.append("pending_target")
            raise AssertionError("target read after failed decision")

        fixture = SimpleNamespace(
            registry=SimpleNamespace(is_archived=lambda name: archived,
                                     archived_run_result=lambda *args: {"archived": True}),
            paper_account=SimpleNamespace(load_pending_target=forbidden_pending),
        )

        def injected_import(name, *args, **kwargs):
            assert name == "portfolio", name
            return fixture

        scope = {"run": failed_run, "__builtins__": {**vars(builtins), "__import__": injected_import}}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), scope)
        result = scope["run_flagship"](asof=ASOF)
        assert result["decided"] is False and result["queued_for_open"] is False
        assert result["brain"]["ok"] is False and result["holdings"] == 0
        assert calls == ([] if archived else ["run"])
