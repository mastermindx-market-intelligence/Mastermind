"""Rendered learning evidence must distinguish read failure from model maturity/absence."""
from __future__ import annotations

import json
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def _closed(payload: dict, code: str) -> None:
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == code
    raw = json.dumps(payload)
    assert "secret" not in raw.lower()
    assert "/Users/private" not in raw


def test_shadow_books_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from portfolio import shadow_books
    monkeypatch.setattr(shadow_books, "load_leaderboard",
                        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/shadows")))
    p = _body(web.api_shadow_books())
    _closed(p, "shadow_books_unavailable")
    assert p["leaderboard"] is None and p["books"] is None and p["policies"] is None


def test_predictions_failure_is_unavailable_not_zero_coverage(monkeypatch):
    from app import web
    from portfolio import predictions
    monkeypatch.setattr(predictions, "summary",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("secret /Users/private/predictions")))
    p = _body(web.api_predictions())
    _closed(p, "predictions_unavailable")
    assert p["coverage"] is None and p["scorecard"] is None


def test_student_failure_is_read_unavailable_not_building(monkeypatch):
    from app import web
    from brain import student
    monkeypatch.setattr(student, "summary",
                        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/student")))
    p = _body(web.api_student())
    _closed(p, "student_unavailable")
    assert p["status"] == "unavailable" and p["top_predicted"] is None


def test_distill_failure_is_read_unavailable_not_building(monkeypatch):
    from app import web
    from brain import distill
    monkeypatch.setattr(distill, "summary",
                        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/distill")))
    p = _body(web.api_distill())
    _closed(p, "distill_unavailable")
    assert p["status"] == "unavailable" and p["top_predicted"] is None


def test_engine_backtest_read_failure_is_distinct_from_no_run(monkeypatch):
    from app import web
    from loop import engine_backtest
    monkeypatch.setattr(engine_backtest, "load",
                        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/engine-bt")))
    p = _body(web.api_engine_backtest())
    _closed(p, "engine_backtest_unavailable")
    assert p["status"] == "unavailable"


def test_factor_zoo_read_failure_is_distinct_from_no_run(monkeypatch):
    from app import web
    from loop import factor_zoo
    monkeypatch.setattr(factor_zoo, "load",
                        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/factor-zoo")))
    p = _body(web.api_factor_zoo())
    _closed(p, "factor_zoo_unavailable")
    assert p["status"] == "unavailable"


def test_fundamentals_read_failure_is_distinct_from_no_run(monkeypatch):
    from app import web
    from loop import fundamentals
    monkeypatch.setattr(fundamentals, "load",
                        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/fundamentals")))
    p = _body(web.api_fundamentals())
    _closed(p, "fundamentals_unavailable")
    assert p["status"] == "unavailable"


def test_learning_ui_consumes_read_unavailable_before_empty_or_no_run():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert "function _learningUnavailable(surface)" in html
    assert "function _learningFetch(url, surface)" in html
    hydrate_start = html.index("function _hydrateShared()")
    hydrate_end = html.index("async function fetchAll", hydrate_start)
    hydrate = html[hydrate_start:hydrate_end]
    for surface in ("shadow_books", "predictions", "engine_backtest", "factor_zoo",
                    "fundamentals", "student", "distill"):
        assert f"_learningFetch('/api/{surface}', '{surface}')" in hydrate

    spans = (
        ("function renderShadowBooks()", "function renderXsec()", "d.read_status === 'unavailable'", "!lb.length"),
        ("function renderXsec()", "function renderEngineBacktest()", "d.read_status === 'unavailable'", "!cov.n_total"),
        ("function renderEngineBacktest()", "function renderFactorZoo()", "d.read_status === 'unavailable'", "d.status !== 'ok'"),
        ("function renderFactorZoo()", "function renderFundamentals()", "d.read_status === 'unavailable'", "d.status !== 'ok'"),
        ("function renderFundamentals()", "function renderFooter()", "d.read_status === 'unavailable'", "d.status !== 'ok'"),
    )
    for start, end, unavailable, ordinary in spans:
        a = html.index(start); b = html.index(end, a); block = html[a:b]
        assert unavailable in block
        assert block.index(unavailable) < block.index(ordinary)

    a = html.index("function _lmCard(")
    b = html.index("function renderLearningModels()", a)
    card = html[a:b]
    assert "d.read_status === 'unavailable'" in card
    assert "Model state unavailable" in card
