"""THE BOOK LIFECYCLE (brain.book_lifecycle) — W6 / T2.

The problem this kills: the US books are one bet wearing four hats and nothing measures or polices
book orthogonality. This suite guards the honest-at-paper-n discipline the architecture mandates:

  · per-book grade math on fixtures (active-return means + max-drawdown),
  · the orthogonality matrix (pairwise active-return correlation; the noisy-mirror flag),
  · INSUFFICIENT-N HONESTY (below the effective_n gate → 'insufficient-n', never a recommendation),
  · the probation triggers (2 consecutive HAC-significant losing reviews OR the noisy-mirror flag),
  · the CONSTITUTIONAL SELF-DIRECTED EXEMPTION (never killed — the yardstick),
  · agenda emission ({owner: fable-review}).

All inputs are INJECTED (fixture review_history + book_curves) — nothing pins a live market state.
"""
from __future__ import annotations

import math
import sys
import types
import unittest
from unittest.mock import patch

import pytest

import bot  # noqa: F401 — bootstraps vendor/macro (for the Newey-West helper)
from brain import book_lifecycle as BL


# ─────────────────────────────────────────────────────────────────────────────
# fixture builders — a review_history is oldest-first per-review increments
# ─────────────────────────────────────────────────────────────────────────────
def _hist(n: int, *, book_ret: dict, bogey_ret: dict, start="2026-05-01") -> list[dict]:
    """n weekly reviews; each book/bogey gets a CONSTANT per-review return from its dict (a clean,
    deterministic series so the HAC sign/magnitude is unambiguous)."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    out = []
    for i in range(n):
        out.append({
            "date": (d0 + timedelta(days=7 * i)).isoformat(),
            "books": {b: r for b, r in book_ret.items()},
            "bogeys": {g: r for g, r in bogey_ret.items()},
        })
    return out


def _hist_series(*, books: dict, bogeys: dict, start="2026-05-01") -> list[dict]:
    """review_history from per-book / per-bogey LISTS of per-review returns (all same length)."""
    from datetime import date, timedelta
    n = max(len(v) for v in list(books.values()) + list(bogeys.values()))
    d0 = date.fromisoformat(start)
    out = []
    for i in range(n):
        out.append({
            "date": (d0 + timedelta(days=7 * i)).isoformat(),
            "books": {b: v[i] for b, v in books.items() if i < len(v)},
            "bogeys": {g: v[i] for g, v in bogeys.items() if i < len(v)},
        })
    return out


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(BL, "_OUT", tmp_path / "lifecycle")
    monkeypatch.setattr(BL, "_BENCH_DIR", tmp_path / "benchmark")
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# grade math
# ─────────────────────────────────────────────────────────────────────────────
def test_grade_active_means_and_max_drawdown():
    # 10 reviews: flagship +0.4%/wk vs SPY +0.1%/wk, defensive +0.6%/wk, regime_max = defensive here
    hist = _hist(10, book_ret={"flagship": 0.004},
                 bogey_ret={"spy": 0.001, "defensive": 0.006, "regime_max": 0.006})
    curves = {"flagship": {"d1": 1.0, "d2": 1.1, "d3": 0.99, "d4": 1.05}}  # peak 1.1 → trough 0.99
    g = BL.grade_book("flagship", hist, book_curves=curves)
    assert g["active_vs_spy"] == pytest.approx(0.003, abs=1e-9)          # 0.004 − 0.001
    assert g["active_vs_defensive"] == pytest.approx(-0.002, abs=1e-9)   # 0.004 − 0.006
    assert g["graded_vs"] == "regime_max"                               # uses the regime-conditional bogey
    # max-drawdown: (1.1 − 0.99)/1.1 = 0.1
    assert g["max_drawdown"] == pytest.approx(0.1, abs=1e-6)
    assert g["max_drawdown_watch"] is False                             # 0.10 < 0.20 watch


def test_max_drawdown_watch_fires_on_deep_drawdown():
    hist = _hist(10, book_ret={"autonomous": 0.0}, bogey_ret={"spy": 0.0, "regime_max": 0.0})
    curves = {"autonomous": {"d1": 1.0, "d2": 1.2, "d3": 0.9}}          # (1.2−0.9)/1.2 = 0.25
    g = BL.grade_book("autonomous", hist, book_curves=curves)
    assert g["max_drawdown"] == pytest.approx(0.25, abs=1e-6)
    assert g["max_drawdown_watch"] is True


# ─────────────────────────────────────────────────────────────────────────────
# the orthogonality matrix + the noisy-mirror flag
# ─────────────────────────────────────────────────────────────────────────────
def test_orthogonality_matrix_flags_the_noisy_mirror():
    # autonomous active returns MIRROR flagship's (identical vs SPY) → corr ~1.0 → noisy mirror.
    # etf is anti-correlated → orthogonal (no flag).
    n = 10
    flag = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.015, -0.005, 0.025, -0.015]
    auto = [x + 0.001 for x in flag]                                    # near-identical to flagship
    etf = [-x for x in flag]                                            # anti-correlated
    spy = [0.0] * n                                                     # active = book return
    hist = _hist_series(books={"flagship": flag, "autonomous": auto, "etf": etf,
                               "heavyweight": [0.0] * n},
                        bogeys={"spy": spy, "defensive": spy, "regime_max": spy})
    ortho = BL.orthogonality_matrix(hist)
    cell = ortho["matrix"]["autonomous"]["flagship"]
    assert cell["status"] == "scoring"
    assert cell["corr"] is not None and cell["corr"] >= 0.8
    flagged = {f["book"] for f in ortho["noisy_mirror_flags"]}
    assert "autonomous" in flagged
    # etf is orthogonal / anti-correlated — NOT a noisy mirror
    assert "etf" not in flagged
    # flagship is the reference — never flagged against itself
    assert "flagship" not in flagged


def test_orthogonality_insufficient_pairs_is_not_a_flag():
    # only 3 overlapping reviews (< noisy_mirror_min_pairs=6) → insufficient-n, NEVER a flag
    flag = [0.01, -0.02, 0.03]
    hist = _hist_series(books={"flagship": flag, "autonomous": flag, "heavyweight": [0.0] * 3,
                               "etf": [0.0] * 3},
                        bogeys={"spy": [0.0] * 3})
    ortho = BL.orthogonality_matrix(hist)
    cell = ortho["matrix"]["autonomous"]["flagship"]
    assert cell["status"] == "insufficient-n"
    assert cell["corr"] is None
    assert ortho["noisy_mirror_flags"] == []


# ─────────────────────────────────────────────────────────────────────────────
# insufficient-n honesty (the load-bearing paper-n discipline)
# ─────────────────────────────────────────────────────────────────────────────
def test_loss_test_below_effective_n_is_insufficient_n():
    # 5 losing reviews < min_effective_n=8 → 'insufficient-n', NOT a recommendation
    hist = _hist(5, book_ret={"autonomous": -0.02}, bogey_ret={"spy": 0.0, "regime_max": 0.0})
    g = BL.grade_book("autonomous", hist)
    lt = g["loss_test"]
    assert lt["status"] == "insufficient-n"
    assert lt["significant"] is False
    assert lt["effective_n"] == 5


def test_review_makes_no_recommendation_at_insufficient_n(sandbox):
    # every US book losing but only 5 reviews → zero recommendations, honest banner
    hist = _hist(5, book_ret={b: -0.02 for b in BL.US_BOOKS},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    rep = BL.review(hist, states={})
    assert rep["recommendations"] == []
    assert rep["paper_n"]["insufficient_n_books"] == len(BL.US_BOOKS)
    assert rep["paper_n"]["scored_books"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# probation triggers
# ─────────────────────────────────────────────────────────────────────────────
def test_probation_on_consecutive_hac_significant_losing_reviews(sandbox):
    # a book losing a clean, reliable −2%/review vs its regime bogey over 12 reviews → HAC-significant
    # loss. Two consecutive such reviews (the streak carried in state) → probation.
    hist = _hist(12, book_ret={"autonomous": -0.02},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    g = BL.grade_book("autonomous", hist)
    assert g["loss_test"]["status"] == "scoring"
    assert g["loss_test"]["losing"] is True
    assert g["loss_test"]["significant"] is True                        # HAC |t| over threshold, mean<0

    # first review: streak 0→1 (active, no rec yet); second: streak 1→2 → probation
    states = {}
    r1 = BL.review(hist, states=states, asof=__import__("datetime").date(2026, 6, 1))
    st1 = r1["states"]["autonomous"]
    assert st1["losing_streak"] == 1
    assert st1["state"] == BL.STATE_ACTIVE
    assert not any(x["book"] == "autonomous" for x in r1["recommendations"])

    r2 = BL.review(hist, states=r1["states"], asof=__import__("datetime").date(2026, 6, 8))
    st2 = r2["states"]["autonomous"]
    assert st2["losing_streak"] == 2
    assert st2["state"] == BL.STATE_PROBATION
    rec = next(x for x in r2["recommendations"] if x["book"] == "autonomous")
    assert rec["recommend"] == BL.STATE_PROBATION


def test_probation_on_noisy_mirror_flag(sandbox):
    # autonomous is a near-perfect mirror of flagship (winning book, so NO losing trigger) — the ONLY
    # trigger is the orthogonality flag. It should still land on probation.
    n = 10
    flag = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.015, -0.005, 0.025, -0.015]
    auto = [x + 0.0005 for x in flag]
    spy = [0.0] * n
    hist = _hist_series(books={"flagship": flag, "autonomous": auto,
                               "heavyweight": [0.001] * n, "etf": [-x for x in flag]},
                        bogeys={"spy": spy, "defensive": spy, "regime_max": spy})
    rep = BL.review(hist, states={})
    # autonomous winning vs regime bogey → not a losing trigger, but flagged noisy
    g_auto = next(g for g in rep["grades"] if g["book"] == "autonomous")
    assert g_auto["loss_test"].get("losing") in (False, None)
    assert "autonomous" in {f["book"] for f in rep["orthogonality"]["noisy_mirror_flags"]}
    rec = next(x for x in rep["recommendations"] if x["book"] == "autonomous")
    assert rec["recommend"] == BL.STATE_PROBATION
    assert any("noisy-mirror" in r for r in rec["reasons"])


def test_probation_escalates_to_retirement_recommendation(sandbox):
    hist = _hist(12, book_ret={"autonomous": -0.02},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    # seed the book already ON probation with a 2-review losing streak → next failing review retires
    states = {"autonomous": {"state": BL.STATE_PROBATION, "losing_streak": 2, "since": "2026-05-01"}}
    rep = BL.review(hist, states=states, asof=__import__("datetime").date(2026, 6, 15))
    assert rep["states"]["autonomous"]["state"] == BL.STATE_RETIRE_REC
    rec = next(x for x in rep["recommendations"] if x["book"] == "autonomous")
    assert rec["recommend"] == BL.STATE_RETIRE_REC


def test_clean_review_clears_the_losing_streak(sandbox):
    # a book that WAS on a 1-streak but now WINS resets to 0 (no persecution for one good review)
    winning = _hist(12, book_ret={"autonomous": 0.02},
                    bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    states = {"autonomous": {"state": BL.STATE_ACTIVE, "losing_streak": 1, "since": "2026-05-01"}}
    rep = BL.review(winning, states=states)
    assert rep["states"]["autonomous"]["losing_streak"] == 0
    assert rep["states"]["autonomous"]["state"] == BL.STATE_ACTIVE


# ─────────────────────────────────────────────────────────────────────────────
# the constitutional Self-Directed exemption
# ─────────────────────────────────────────────────────────────────────────────
def test_self_directed_is_hard_coded_exempt():
    assert "self_directed" in BL.EXEMPT_BOOKS


def test_self_directed_never_recommended_even_when_losing(sandbox):
    # self_directed losing hard for 12 reviews — it must NEVER be put on probation or retired.
    hist = _hist(12, book_ret={"self_directed": -0.05, "autonomous": 0.0},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    rep = BL.review(hist, states={})
    assert not any(x["book"] == "self_directed" for x in rep["recommendations"])
    assert rep["states"]["self_directed"]["state"] == BL.STATE_ACTIVE
    assert rep["states"]["self_directed"]["exempt"] is True
    # it IS graded for display (exempt flag on the card)
    g = next(g for g in rep["grades"] if g["book"] == "self_directed")
    assert g["exempt"] is True


def test_self_directed_never_in_noisy_mirror_flags(sandbox):
    # even if self_directed perfectly mirrors flagship it is never a retirement candidate
    n = 10
    flag = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.015, -0.005, 0.025, -0.015]
    spy = [0.0] * n
    # self_directed is not in US_BOOKS, so it's not even a matrix column — assert the flags exclude it
    hist = _hist_series(books={"flagship": flag, "self_directed": flag,
                               "autonomous": [0.0] * n, "heavyweight": [0.0] * n, "etf": [0.0] * n},
                        bogeys={"spy": spy, "defensive": spy, "regime_max": spy})
    ortho = BL.orthogonality_matrix(hist)
    assert "self_directed" not in {f["book"] for f in ortho["noisy_mirror_flags"]}
    assert "self_directed" not in ortho["books"]


# ─────────────────────────────────────────────────────────────────────────────
# agenda emission + cio summary
# ─────────────────────────────────────────────────────────────────────────────
def test_agenda_items_emitted_for_probation_with_fable_owner(sandbox):
    hist = _hist(12, book_ret={"autonomous": -0.02},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    states = {"autonomous": {"state": BL.STATE_ACTIVE, "losing_streak": 1, "since": "2026-05-01"}}
    rep = BL.review(hist, states=states)
    items = BL.agenda_items(rep)
    assert items, "expected a lifecycle agenda item"
    it = next(i for i in items if i["book"] == "autonomous")
    assert it["owner"] == "fable-review"                    # kill/promote = human decision (P8)
    assert it["id"] == "lifecycle:autonomous"
    assert it["evidence"]                                   # P3 — never an item without evidence


def test_agenda_items_empty_when_nothing_to_recommend(sandbox):
    hist = _hist(12, book_ret={b: 0.02 for b in BL.US_BOOKS},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    rep = BL.review(hist, states={})
    assert BL.agenda_items(rep) == []                       # P2 no-op


def test_lifecycle_summary_shape(sandbox):
    hist = _hist(10, book_ret={b: 0.0 for b in BL.US_BOOKS},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    rep = BL.review(hist, states={})
    summ = BL.lifecycle_summary(rep)
    assert set(summ) >= {"states", "recommendations", "noisy_mirror_flags",
                         "scored_books", "insufficient_n_books", "n_reviews"}
    assert summ["n_reviews"] == 10


# ─────────────────────────────────────────────────────────────────────────────
# persistence + degradation
# ─────────────────────────────────────────────────────────────────────────────
def test_write_persists_and_loads(sandbox):
    hist = _hist(12, book_ret={"autonomous": -0.02},
                 bogey_ret={"spy": 0.0, "defensive": 0.0, "regime_max": 0.0})
    from datetime import date
    res = BL.write(hist, asof=date(2026, 6, 20))
    assert res["ok"]
    loaded = BL.load("2026-06-20")
    assert loaded["as_of"] == "2026-06-20"
    assert BL.latest()["as_of"] == "2026-06-20"


def test_review_degrades_on_empty_history(sandbox):
    rep = BL.review([], states={})
    assert rep["recommendations"] == []
    assert rep["n_reviews"] == 0
    # every US book is insufficient-n (0 reviews), none scored, no crash
    assert rep["paper_n"]["scored_books"] == 0


def test_history_from_ledgers_differences_cumulative(sandbox):
    # two ledger snapshots with cumulative returns → per-review increments
    ledgers = [
        {"as_of": "2026-05-01", "leaderboard": [
            {"id": "flagship", "kind": "book", "return_pct": 1.0},
            {"id": "spy", "kind": "bogey", "return_pct": 0.5}]},
        {"as_of": "2026-05-08", "leaderboard": [
            {"id": "flagship", "kind": "book", "return_pct": 3.0},
            {"id": "spy", "kind": "bogey", "return_pct": 1.5}]},
    ]
    hist = BL.history_from_ledgers(ledgers)
    assert len(hist) == 2
    # second review increment: flagship 3.0−1.0 = 2.0% → 0.02; spy 1.5−0.5 = 1.0% → 0.01
    assert hist[1]["books"]["flagship"] == pytest.approx(0.02, abs=1e-9)
    assert hist[1]["bogeys"]["spy"] == pytest.approx(0.01, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Fix-2: _regional_review_history never-raises guarantee — malformed row guard
# ─────────────────────────────────────────────────────────────────────────────
def test_regional_review_history_tolerates_malformed_leaderboard_rows():
    """A ledger whose 'leaderboard' contains non-dict rows (e.g. a string annotation or None
    injected by a corrupt write) must NOT raise AttributeError.  Before the fix the dict-
    comprehension `{r.get('id'): r for r in leaderboard}` would blow up on r.get() when r is
    not a dict.  The function is documented Never raises — this guards that contract."""
    malformed_ledgers = [
        # leaderboard mixes valid dict rows with a stray string + a None
        {"as_of": "2026-05-01",
         "leaderboard": [
             {"id": "china", "kind": "book", "return_pct": 2.0},
             {"id": "regional", "kind": "bogey", "return_pct": 1.0},
             "stray_annotation",   # non-dict — must not raise
             None,                 # None — must not raise
         ]},
    ]
    # _regional_review_history is a module-private function; reach it via regional_review()
    # which calls it internally and is also documented Never raises.
    result = BL.regional_review(cn_ledgers=malformed_ledgers, hk_ledgers=[])
    # the call must complete without AttributeError and return a well-formed dict
    assert isinstance(result, dict), "regional_review must return a dict on malformed input"
    assert "grades" in result


# Missing observations must not count as lifecycle evidence, with or without vendor.
class BookLifecycleMissingValues(unittest.TestCase):
    def setUp(self):
        self.defaults = patch.object(BL, "_cfg", return_value={})
        self.defaults.start()
        self.addCleanup(self.defaults.stop)

    def test_forced_fallback_ignores_missing_values(self):
        # Force the optional engine to be absent even in a vendored CI checkout.
        with patch.dict(sys.modules, {"engine": None, "engine.validation": None}):
            for n in (2, 7, 8, 12):
                for lag in (0, 3, 50):
                    clean = [-0.01 - (i % 4) * 0.005 for i in range(n)]
                    missing = clean[:1] + [None, float("nan")] + clean[1:]
                    with self.subTest(n=n, lag=lag):
                        actual = BL._hac(missing, lag)
                        self.assertEqual(actual, BL._hac(clean, lag))
                        self.assertEqual(actual["n"], n)
                        self.assertEqual(actual["lags"], min(lag, n-1) if n >= 8 else None)

    def test_consumer_does_not_count_missing_review(self):
        with patch.dict(sys.modules, {"engine": None, "engine.validation": None}):
            for n in (7, 8):
                with self.subTest(valid_reviews=n):
                    clean = [-0.02] * n
                    actual = BL._loss_significance(clean + [float("nan")])
                    self.assertEqual(actual, BL._loss_significance(clean))
                    self.assertEqual(actual["effective_n"], n)
                    self.assertEqual(actual["reviews_remaining"], max(0, 8-n))
                    self.assertEqual(actual["status"], "insufficient-n" if n < 8 else "scoring")

    def test_reachable_history_nan_is_not_an_eighth_review(self):
        history = [{"books": {"autonomous": -0.02}, "bogeys": {"spy": 0.0}} for _ in range(7)]
        history.append({"books": {"autonomous": float("nan")}, "bogeys": {"spy": 0.0}})
        active = BL._active_series(history, "autonomous", "spy")
        self.assertTrue(math.isnan(active[-1]))
        with patch.dict(sys.modules, {"engine": None, "engine.validation": None}):
            actual = BL._loss_significance(active)
        self.assertEqual(actual["effective_n"], 7)
        self.assertEqual(actual["reviews_remaining"], 1)
        self.assertEqual(actual["status"], "insufficient-n")
        self.assertFalse(actual["significant"])

    def test_existing_short_result_shape_is_preserved(self):
        with patch.dict(sys.modules, {"engine": None, "engine.validation": None}):
            for sample in ([], [None], [-0.02], [None, -0.02]):
                clean = [x for x in sample if x is not None]
                with self.subTest(sample=sample):
                    self.assertEqual(BL._hac(sample, 3), {
                        "n": len(clean), "mean": clean[0] if clean else None, "t": 0.0, "se": None,
                    })


    def test_preferred_helper_receives_only_valid_samples(self):
        engine = types.ModuleType("engine")
        validation = types.ModuleType("engine.validation")
        calls = []
        expected = {"mean": -0.02, "se": 0.002, "t": -10.0, "p": 0.0,
                    "n": 8, "lags": 7, "lags_requested": 50}

        def helper(samples, *, lags):
            calls.append((samples, lags))
            return expected

        validation.newey_west_tstat = helper
        engine.validation = validation
        with patch.dict(sys.modules, {"engine": engine, "engine.validation": validation}):
            actual = BL._hac([-0.02] * 4 + [None, float("nan")] + [-0.02] * 4, 50)
        self.assertIs(actual, expected)
        self.assertEqual(calls, [([-0.02] * 8, 50)])

    def test_grade_book_missing_history_keeps_the_real_loss_gate(self):
        for helper_present in (False, True):
            for n in (7, 8):
                calls = []
                engine = types.ModuleType("engine")
                validation = types.ModuleType("engine.validation")

                def helper(samples, *, lags):
                    calls.append((samples, lags))
                    self.assertEqual(samples, [-0.02] * 8)
                    return {"mean": -0.02, "se": 0.002, "t": -10.0, "p": 0.0,
                            "n": 8, "lags": 3, "lags_requested": lags}

                validation.newey_west_tstat = helper
                engine.validation = validation
                modules = {"engine": engine, "engine.validation": validation} if helper_present else {
                    "engine": None, "engine.validation": None,
                }
                history = [{"books": {"autonomous": -0.02},
                            "bogeys": {"spy": 0.0, "regime_max": 0.0}} for _ in range(n)]
                history.extend([
                    {"books": {"autonomous": None}, "bogeys": {"spy": 0.0, "regime_max": 0.0}},
                    {"books": {"autonomous": float("nan")},
                     "bogeys": {"spy": 0.0, "regime_max": 0.0}},
                ])
                with self.subTest(helper_present=helper_present, valid_reviews=n):
                    active = BL._active_series(history, "autonomous", "regime_max")
                    self.assertEqual(len(active), n + 1)
                    self.assertTrue(math.isnan(active[-1]))
                    with patch.dict(sys.modules, modules):
                        grade = BL.grade_book("autonomous", history, book_curves={})
                    loss = grade["loss_test"]
                    self.assertEqual(loss["effective_n"], n)
                    self.assertEqual(loss["reviews_remaining"], max(0, 8 - n))
                    self.assertEqual(grade["reviews_remaining"], max(0, 8 - n))
                    self.assertEqual(loss["status"], "insufficient-n" if n < 8 else "scoring")
                    self.assertEqual(loss["mean"], -0.02)
                    self.assertEqual(loss["losing"], n >= 8)
                    self.assertEqual(loss["significant"], n >= 8)
                    self.assertEqual(len(calls), 1 if helper_present and n >= 8 else 0)

    def test_zero_and_infinity_are_not_missing_observations(self):
        with patch.dict(sys.modules, {"engine": None, "engine.validation": None}):
            self.assertEqual(BL._hac([0.0] * 8 + [None, float("nan")], 3), {
                "mean": 0.0, "se": 0.0, "t": 0.0, "p": 1.0,
                "n": 8, "lags": 3, "lags_requested": 3,
            })
            actual = BL._hac([-0.02] * 8 + [float("inf")], 3)
            self.assertEqual(actual["n"], 9)
            self.assertEqual(actual["mean"], float("inf"))
            self.assertTrue(math.isnan(actual["t"]))
            self.assertEqual(BL._loss_significance([-0.02] * 7 + [float("inf")])["effective_n"], 8)

    def test_missing_only_and_single_valid_keep_legacy_shape(self):
        with patch.dict(sys.modules, {"engine": None, "engine.validation": None}):
            for sample, clean in (
                ([None, float("nan")], []),
                ([None, float("nan"), -0.02], [-0.02]),
            ):
                with self.subTest(valid_count=len(clean)):
                    self.assertEqual(BL._hac(sample, 3), {
                        "n": len(clean), "mean": clean[0] if clean else None, "t": 0.0, "se": None,
                    })
