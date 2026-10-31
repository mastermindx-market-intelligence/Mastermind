"""A12 / #1433 — benchmark comparisons happen over ONE shared window, at READ time.

The ledger renormalizes each bogey on ITS OWN inception, so the stored per-inception
``return_pct`` values are not comparable to each other or to a book's since-inception return.
These tests pin the read-time contract:

  * latest-ledger selection ignores the co-located ``_series*.json`` sidecars (both readers —
    brain.benchmark_ledger.latest and portfolio.firm_allocator._latest_benchmark);
  * brain.benchmark_ledger.compare_book_to_ledger recomputes every leg over the cohort's actual
    common dates and WITHHOLDS the delta (absent key, no numbers) when the window is unsupported;
  * the stored ledger ``return_pct`` values are never rewritten;
  * a WITHHELD NAV row is never a curve point (never an endpoint); PROVISIONAL endpoints propagate;
  * the three consumers (web Self-Directed status, improvement agenda, allocation attribution)
    score only on the aligned window and withhold otherwise.

The #1433 falsifier: SPY Oct1=100 → Oct2=200 → Oct3=180 (stored +80%), defensive Oct2=100 →
Oct3=110 (stored +10%). Over the common window Oct2..Oct3 the truth is SPY −10% and defensive
+10% — the stored numbers are each correct over their own window and wrong over the shared one.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from brain import benchmark_ledger as B

# The #1433 falsifier price series (SPY inception 2026-10-01, defensive inception 2026-10-02).
FALSIFIER_SERIES = {
    "SPY": {"2026-10-01": 100.0, "2026-10-02": 200.0, "2026-10-03": 180.0},
    "XLU": {"2026-10-02": 100.0, "2026-10-03": 110.0},
    "XLV": {"2026-10-02": 100.0, "2026-10-03": 110.0},
    "XLF": {"2026-10-02": 100.0, "2026-10-03": 110.0},
    "XLP": {"2026-10-02": 100.0, "2026-10-03": 110.0},
}

# A two-point common window (both bogeys start 2026-10-01) for NAV-row labelling tests.
SHORT_SERIES = {
    "SPY": {"2026-10-01": 100.0, "2026-10-02": 110.0},
    "XLU": {"2026-10-01": 100.0, "2026-10-02": 105.0},
    "XLV": {"2026-10-01": 100.0, "2026-10-02": 105.0},
    "XLF": {"2026-10-01": 100.0, "2026-10-02": 105.0},
    "XLP": {"2026-10-01": 100.0, "2026-10-02": 105.0},
}


def _falsifier_ledger(**kw):
    """Build + persist the #1433 ledger (real writer output) in the redirected _BENCH_DIR."""
    return B.build(FALSIFIER_SERIES, asof="2026-10-03", persist=True, **kw)


def _write_nav(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n")


# ── 1. sidecars are ignored by BOTH latest-ledger readers ────────────────────
def test_sidecars_ignored_by_both_readers(tmp_path):
    from portfolio import firm_allocator as FA
    d = tmp_path / "_benchmark"
    d.mkdir(parents=True, exist_ok=True)
    (d / "_series.json").write_text(json.dumps({"SPY": {"2026-10-03": 180.0}}))
    (d / "_series_meta.json").write_text(json.dumps({"SPY": {"2026-10-03": "yahoo"}}))
    assert B.latest() == {}
    assert FA._latest_benchmark() == {}


def test_dated_ledger_wins_over_sidecars_for_both_readers(tmp_path):
    from portfolio import firm_allocator as FA
    d = tmp_path / "_benchmark"
    d.mkdir(parents=True, exist_ok=True)
    dated = {"as_of": "2026-10-03", "bogeys": {"spy": {"return_pct": 80.0}}}
    (d / "2026-10-03.json").write_text(json.dumps(dated))
    (d / "_series.json").write_text(json.dumps({"SPY": {}}))
    (d / "_series_meta.json").write_text(json.dumps({"SPY": {}}))
    assert B.latest() == dated
    assert FA._latest_benchmark() == dated


# ── 2. the #1433 falsifier, on the helper ────────────────────────────────────
def test_falsifier_1433_shared_window_on_helper():
    _falsifier_ledger()
    led = B.latest()
    # the STORED ledger keeps its per-inception returns, byte-identical semantics
    assert led["bogeys"]["spy"]["return_pct"] == pytest.approx(80.0)
    assert led["bogeys"]["defensive"]["return_pct"] == pytest.approx(10.0)

    hist = {"curve": {"2026-10-01": 1.0, "2026-10-02": 1.0, "2026-10-03": 1.0},
            "status_by_date": {}}
    cmp = B.compare_book_to_ledger("book", hist, led)
    assert cmp["status"] == "descriptive"
    assert (cmp["start"], cmp["end"]) == ("2026-10-02", "2026-10-03")   # the shared window
    assert cmp["common_point_count"] == 2
    ret = cmp["returns_pct"]
    assert ret["spy"] == pytest.approx(-10.0)            # NOT the stored +80
    assert ret["defensive"] == pytest.approx(10.0)
    assert ret["book"] == pytest.approx(0.0)
    deltas = {(d["left_id"], d["right_id"]): d["delta_pp"] for d in cmp["deltas_pp"]}
    assert deltas[("book", "spy")] == pytest.approx(10.0)               # 0 − (−10)
    assert deltas[("book", "defensive")] == pytest.approx(-10.0)        # 0 − (+10)
    # hand-built history with no labels: QUALIFIED is never inferred from an absent label
    assert cmp["endpoint_status"] == "UNLABELLED"


# ── 3. the web Self-Directed row compares on the shared window ───────────────
@pytest.fixture
def sd_web(monkeypatch, tmp_path):
    """Stub the Self-Directed engine so _portfolio_status has a total_return_pct (0.0)."""
    from portfolio import self_directed as sd
    monkeypatch.setattr(sd, "_load_account", lambda: {"positions": {}})
    monkeypatch.setattr(sd, "book", lambda **kw: {
        "nav": 100000.0, "inception_date": "2026-10-01",
        "allocation": {"total_return_pct": 0.0, "cash_pct": 0.0, "n_positions": 0}})
    return sd


def _self_directed_status():
    from app import web
    from portfolio import registry
    return web._portfolio_status(registry.get("self_directed"))["status"]


def test_web_self_directed_vs_spy_on_shared_window(sd_web):
    sd = sd_web
    _write_nav(sd._NAV_PATH, [{"date": "2026-10-01", "nav": 100000},
                              {"date": "2026-10-02", "nav": 100000},
                              {"date": "2026-10-03", "nav": 100000}])
    _falsifier_ledger()
    status = _self_directed_status()
    # the old code produced own_ret − spy_ret = 0 − 80 = −80 (cross-window); the shared window
    # says the flat book beat SPY's −10% by +10 pts
    assert status["vs_spy_pct"] == pytest.approx(10.0)
    assert status["vs_defensive_pct"] == pytest.approx(-10.0)
    assert status["vs_benchmark_pct"] == pytest.approx(10.0)
    assert status["total_return_pct"] == pytest.approx(0.0)      # the book's OWN return, unchanged
    bw = status["benchmark_window"]
    assert (bw["status"], bw["start"], bw["end"], bw["common_point_count"]) == \
        ("descriptive", "2026-10-02", "2026-10-03", 2)
    assert bw["endpoint_status"] == "UNLABELLED"                 # legacy rows carry no nav_status


@pytest.mark.parametrize("rows", [
    [{"date": "2026-10-03", "nav": 100000}],   # a single date → no two common points
    None,                                      # no nav history at all
])
def test_web_self_directed_withholds_unsupported_window(sd_web, rows):
    sd = sd_web
    _falsifier_ledger()
    if rows is not None:
        _write_nav(sd._NAV_PATH, rows)
    status = _self_directed_status()
    assert "vs_spy_pct" not in status
    assert "vs_defensive_pct" not in status
    assert "vs_benchmark_pct" not in status
    bw = status["benchmark_window"]
    assert bw["status"] == "unavailable"
    assert bw["reason"] == "insufficient_common_dates"
    assert bw["endpoint_status"] is None
    assert status["total_return_pct"] == pytest.approx(0.0)      # the book's own return survives


# ── 4. NAV-row labelling: WITHHELD is never an endpoint; bad navs are skipped ─
def test_withheld_row_is_never_an_endpoint():
    _ = B.build(SHORT_SERIES, asof="2026-10-02", persist=True)
    led = B.latest()
    path = B._BENCH_DIR / "nav_rows.jsonl"
    _write_nav(path, [{"date": "2026-10-01", "nav": 100.0},
                      {"date": "2026-10-02", "nav": 110.0},
                      {"date": "2026-10-03", "nav": 120.0, "nav_status": "WITHHELD"}])
    hist = B.read_nav_history(path)
    assert sorted(hist["curve"]) == ["2026-10-01", "2026-10-02"]   # Oct 3 retracted
    assert hist["skipped"] == 1
    cmp = B.compare_book_to_ledger("book", hist, led)
    assert cmp["status"] == "descriptive"
    assert cmp["end"] == "2026-10-02"                              # window ends on the prior date


def test_provisional_endpoint_propagates():
    _ = B.build(SHORT_SERIES, asof="2026-10-02", persist=True)
    led = B.latest()
    path = B._BENCH_DIR / "nav_rows.jsonl"
    _write_nav(path, [{"date": "2026-10-01", "nav": 100.0},
                      {"date": "2026-10-02", "nav": 110.0, "nav_status": "PROVISIONAL"}])
    cmp = B.compare_book_to_ledger("book", B.read_nav_history(path), led)
    assert cmp["status"] == "descriptive"
    assert cmp["endpoint_status"] == "PROVISIONAL"


def test_qualified_endpoints_when_both_rows_labelled():
    _ = B.build(SHORT_SERIES, asof="2026-10-02", persist=True)
    led = B.latest()
    path = B._BENCH_DIR / "nav_rows.jsonl"
    _write_nav(path, [{"date": "2026-10-01", "nav": 100.0, "nav_status": "QUALIFIED"},
                      {"date": "2026-10-02", "nav": 110.0, "nav_status": "QUALIFIED"}])
    cmp = B.compare_book_to_ledger("book", B.read_nav_history(path), led)
    assert cmp["endpoint_status"] == "QUALIFIED"


def test_unusable_nav_rows_are_skipped_and_counted():
    path = B._BENCH_DIR / "bad_rows.jsonl"
    _BENCH = B._BENCH_DIR
    _BENCH.mkdir(parents=True, exist_ok=True)
    rows = [
        '{"date": "2026-10-01", "nav": NaN}\n',          # NaN
        '{"date": "2026-10-01", "nav": true}\n',         # bool
        '{"date": "2026-10-01", "nav": 0}\n',            # non-positive
        '{"date": "2026-10-01", "nav": "100"}\n',        # string
        'not json at all\n',                             # unparseable
        '{"date": "2026-10-01", "nav": 100.0}\n',        # the one usable row
    ]
    path.write_text("".join(rows))
    hist = B.read_nav_history(path)
    assert hist["curve"] == {"2026-10-01": 100.0}
    assert hist["status_by_date"] == {"2026-10-01": "UNLABELLED"}
    assert hist["skipped"] == 5


def test_missing_nav_file_degrades_to_empty():
    hist = B.read_nav_history(B._BENCH_DIR / "does_not_exist.jsonl")
    assert hist == {"curve": {}, "status_by_date": {}, "skipped": 0}


# ── 5. compare_book_to_ledger failure modes never raise ──────────────────────
def test_unavailable_on_ledger_without_canonical_asof():
    hist = {"curve": {"2026-10-02": 1.0, "2026-10-03": 1.0}, "status_by_date": {}}
    for led in ({}, {"as_of": "garbage", "bogeys": {"spy": {"curve": {}}}}):
        cmp = B.compare_book_to_ledger("book", hist, led)
        assert cmp["status"] == "unavailable"
        assert cmp["reason"] == "ledger_asof_invalid"
        assert cmp["returns_pct"] is None and cmp["deltas_pp"] is None
        assert cmp["endpoint_status"] is None


def test_missing_bogey_curve_is_reported_not_raised():
    led = _falsifier_ledger()
    led.pop("bogeys")
    hist = {"curve": {"2026-10-02": 1.0, "2026-10-03": 1.1}, "status_by_date": {}}
    cmp = B.compare_book_to_ledger("book", hist, led)
    assert cmp["status"] == "unavailable"
    assert cmp["reason"] == "missing_curve"


def test_book_id_colliding_with_bogey_is_invalid_config_not_a_raise():
    led = _falsifier_ledger()
    hist = {"curve": {"2026-10-02": 1.0, "2026-10-03": 1.0}, "status_by_date": {}}
    cmp = B.compare_book_to_ledger("spy", hist, led)     # collides with the spy bogey id
    assert cmp["status"] == "unavailable"
    assert cmp["reason"].startswith("invalid_config:")


# ── 6. the improvement agenda scores on the shared window ────────────────────
@pytest.fixture
def agenda_env(monkeypatch, tmp_path):
    """Redirect registry.data_dir to a tmp per-book dir the agenda can read nav histories from."""
    from portfolio import registry
    books = tmp_path / "agenda_books"
    monkeypatch.setattr(registry, "data_dir", lambda pid=None: books / (pid or "flagship"))
    return books / "autonomous"


def test_agenda_one_item_on_shared_window(agenda_env):
    import brain.improvement_agenda as A
    _falsifier_ledger(book_curves={"autonomous": {"2026-10-01": 1.0, "2026-10-02": 1.0,
                                                  "2026-10-03": 0.9}})
    _write_nav(agenda_env / "nav_history.jsonl",
               [{"date": "2026-10-01", "nav": 100000},
                {"date": "2026-10-02", "nav": 100000},
                {"date": "2026-10-03", "nav": 90000}])
    items = A._from_benchmark(date(2026, 10, 3))
    assert len(items) == 1
    it = items[0]
    assert it["id"] == "benchmark:autonomous"
    ev = " ".join(it["evidence"])
    # the evidence states the shared window, its point count and the endpoint status
    assert "2026-10-02..2026-10-03" in ev
    assert "n=2" in ev
    assert "endpoint_status=UNLABELLED" in ev
    # on the window the book (−10%) trails the defensive basket (+10%) — not SPY (also −10%)
    assert it["extra"]["gap_pct"] == pytest.approx(20.0)
    assert "defensive" in it["title"]


def test_agenda_no_item_without_readable_curve(agenda_env):
    import brain.improvement_agenda as A
    _falsifier_ledger(book_curves={"autonomous": {"2026-10-01": 1.0, "2026-10-02": 1.0,
                                                  "2026-10-03": 0.9}})
    assert agenda_env.exists() is False                  # no nav_history.jsonl at all
    assert A._from_benchmark(date(2026, 10, 3)) == []


def test_agenda_falsifier_stored_behind_window_ahead_gives_no_item(agenda_env):
    """THE falsifier: the STORED ledger says the book is 130 pts behind SPY (−50% vs +80%), but on
    the shared window the book is AHEAD of both bogeys. The stored-return comparison would have
    fired an item; the aligned one must not."""
    import brain.improvement_agenda as A
    curve = {"2026-10-01": 1.0, "2026-10-02": 0.4, "2026-10-03": 0.5}
    led = _falsifier_ledger(book_curves={"autonomous": curve})
    row = next(r for r in led["leaderboard"] if r.get("id") == "autonomous")
    assert row["return_pct"] == pytest.approx(-50.0)     # stored: looks far behind SPY's +80
    _write_nav(agenda_env / "nav_history.jsonl",
               [{"date": "2026-10-01", "nav": 100000},
                {"date": "2026-10-02", "nav": 40000},
                {"date": "2026-10-03", "nav": 50000}])   # window Oct2..3: +25% vs SPY −10%
    assert A._from_benchmark(date(2026, 10, 3)) == []


# ── 7. allocation attribution scores only on the aligned window ──────────────
def test_attribution_withholds_return_only_book_row():
    import brain.attribution as ATTR
    _falsifier_ledger(book_curves={"autonomous": {"2026-10-01": 1.0, "2026-10-02": 1.0,
                                                  "2026-10-03": 0.9}})
    block = ATTR.allocation_attribution(date(2026, 10, 3))       # no book_curves supplied
    assert block["status"] == "building"
    assert block["books"] == {}
    assert block["withheld"] == {"autonomous": "no_book_curve"}


def test_attribution_scores_on_aligned_window():
    import brain.attribution as ATTR
    _falsifier_ledger(book_curves={"autonomous": {"2026-10-01": 1.0, "2026-10-02": 1.0,
                                                  "2026-10-03": 0.9}})
    block = ATTR.allocation_attribution(
        date(2026, 10, 3),
        book_curves={"autonomous": {"2026-10-02": 1.0, "2026-10-03": 0.9}})
    assert block["status"] == "scoring"
    assert block["withheld"] == {}
    b = block["books"]["autonomous"]
    # the book and SPY are BOTH −10% over Oct2..Oct3 → zero active return on the aligned window
    assert b["active_return"] == pytest.approx(0.0)
    assert b["reconciled"] is True
    assert b["window"] == {"start": "2026-10-02", "end": "2026-10-03", "common_point_count": 2}
    # the top-level legs stay the ledger-wide (per-inception) returns, as before
    assert block["spy_return"] == pytest.approx(0.8)
    assert block["defensive_return"] == pytest.approx(0.1)


def test_attribution_book_term_is_window_return_not_stored_return_pct():
    """LR-A12B finding 1: the stored per-inception book return (−50%) differs from the book's
    return over the shared window (+5%). Only the window return may reach the active term."""
    import brain.attribution as ATTR
    led = _falsifier_ledger(book_curves={"autonomous": {"2026-10-01": 1.0, "2026-10-02": 2.0,
                                                        "2026-10-03": 0.5}})
    stored = next(r for r in led["leaderboard"] if r.get("id") == "autonomous")["return_pct"]
    assert stored == pytest.approx(-50.0)                   # the fixture really diverges
    block = ATTR.allocation_attribution(
        date(2026, 10, 3),
        book_curves={"autonomous": {"2026-10-02": 1.0, "2026-10-03": 1.05}})
    b = block["books"]["autonomous"]
    # window Oct2..Oct3: book +5%, SPY 200→180 = −10% → active +15% (stored −50% would give −40%)
    assert b["active_return"] == pytest.approx(0.15)
    assert b["window"] == {"start": "2026-10-02", "end": "2026-10-03", "common_point_count": 2}


@pytest.mark.parametrize("start_label,end_label,expected", [
    ("QUALIFIED", None, "UNLABELLED"),          # one endpoint carries no label
    ("QUALIFIED", "ESTIMATED", "UNLABELLED"),   # an unknown label is not a qualification
    ("ESTIMATED", "PROVISIONAL", "PROVISIONAL"),
])
def test_endpoint_status_never_infers_qualified(start_label, end_label, expected):
    _ = B.build(SHORT_SERIES, asof="2026-10-02", persist=True)
    led = B.latest()
    hist = {"curve": {"2026-10-01": 100.0, "2026-10-02": 110.0},
            "status_by_date": {d: lab for d, lab in (("2026-10-01", start_label),
                                                     ("2026-10-02", end_label)) if lab}}
    cmp = B.compare_book_to_ledger("book", hist, led)
    assert cmp["status"] == "descriptive"
    assert cmp["endpoint_status"] == expected
