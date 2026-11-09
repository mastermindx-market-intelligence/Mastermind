"""Rendered learning evidence must distinguish read failure from model maturity/absence."""
from __future__ import annotations

import copy
import importlib
import json

import pytest
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def _closed(payload: dict, code: str) -> None:
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == code
    raw = json.dumps(payload)
    assert "secret" not in raw.lower()
    assert "/Users/private" not in raw


def _raise_from_reader(monkeypatch, module, name, detail):
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError(detail)

    monkeypatch.setattr(module, name, fail)
    return calls


def _assert_failed_read(response, calls, caplog):
    assert response.status_code == 200
    assert len(calls) == 1
    assert "RuntimeError" in caplog.text
    assert "secret" not in caplog.text.lower()
    assert "/Users/private" not in caplog.text


def _return_from_reader(monkeypatch, module, name, value):
    calls = []

    def read(*args, **kwargs):
        calls.append((args, kwargs))
        return copy.deepcopy(value)

    monkeypatch.setattr(module, name, read)
    return calls


def test_shadow_books_failure_is_unavailable_not_empty(monkeypatch, caplog):
    from app import web
    from portfolio import shadow_books
    calls = _raise_from_reader(monkeypatch, shadow_books, "load_leaderboard", "secret /Users/private/shadows")
    response = web.api_shadow_books()
    _assert_failed_read(response, calls, caplog)
    p = _body(response)
    _closed(p, "shadow_books_unavailable")
    assert p["leaderboard"] is None and p["books"] is None and p["policies"] is None


def test_predictions_failure_is_unavailable_not_zero_coverage(monkeypatch, caplog):
    from app import web
    from portfolio import predictions
    calls = _raise_from_reader(monkeypatch, predictions, "summary", "secret /Users/private/predictions")
    response = web.api_predictions()
    _assert_failed_read(response, calls, caplog)
    p = _body(response)
    _closed(p, "predictions_unavailable")
    assert p["coverage"] is None and p["scorecard"] is None


def test_student_failure_is_read_unavailable_not_building(monkeypatch, caplog):
    from app import web
    from brain import student
    calls = _raise_from_reader(monkeypatch, student, "summary", "secret /Users/private/student")
    response = web.api_student()
    _assert_failed_read(response, calls, caplog)
    p = _body(response)
    _closed(p, "student_unavailable")
    assert p["status"] == "unavailable" and p["top_predicted"] is None


def test_distill_failure_is_read_unavailable_not_building(monkeypatch, caplog):
    from app import web
    from brain import distill
    calls = _raise_from_reader(monkeypatch, distill, "summary", "secret /Users/private/distill")
    response = web.api_distill()
    _assert_failed_read(response, calls, caplog)
    p = _body(response)
    _closed(p, "distill_unavailable")
    assert p["status"] == "unavailable" and p["top_predicted"] is None


def test_engine_backtest_read_failure_is_distinct_from_no_run(monkeypatch, caplog):
    from app import web
    from loop import engine_backtest
    calls = _raise_from_reader(monkeypatch, engine_backtest, "load", "secret /Users/private/engine-bt")
    response = web.api_engine_backtest()
    _assert_failed_read(response, calls, caplog)
    p = _body(response)
    _closed(p, "engine_backtest_unavailable")
    assert p["status"] == "unavailable"


def test_factor_zoo_read_failure_is_distinct_from_no_run(monkeypatch, caplog):
    from app import web
    from loop import factor_zoo
    calls = _raise_from_reader(monkeypatch, factor_zoo, "load", "secret /Users/private/factor-zoo")
    response = web.api_factor_zoo()
    _assert_failed_read(response, calls, caplog)
    p = _body(response)
    _closed(p, "factor_zoo_unavailable")
    assert p["status"] == "unavailable"


def test_fundamentals_read_failure_is_distinct_from_no_run(monkeypatch, caplog):
    from app import web
    from loop import fundamentals
    calls = _raise_from_reader(monkeypatch, fundamentals, "load", "secret /Users/private/fundamentals")
    response = web.api_fundamentals()
    _assert_failed_read(response, calls, caplog)
    p = _body(response)
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


@pytest.mark.parametrize("surface,module_name,reader_name,payload", [
    ("shadow_books", "portfolio.shadow_books", "load_leaderboard", {"as_of": "2026-09-17", "leaderboard": [], "books": {}}),
    ("predictions", "portfolio.predictions", "summary", {"coverage": {"n_total": 3, "n_resolved": 2}, "scorecard": {"status": "ok", "n": 2}, "as_of": "2026-09-17"}),
    ("student", "brain.student", "summary", {"status": "building", "n": 0}),
    ("distill", "brain.distill", "summary", {"status": "building", "n": 0, "n_pos": 0}),
    ("engine_backtest", "loop.engine_backtest", "load", {"status": "unavailable", "note": "No persisted run recorded."}),
    ("factor_zoo", "loop.factor_zoo", "load", {"status": "unavailable", "note": "No persisted run recorded."}),
    ("fundamentals", "loop.fundamentals", "load", {"status": "unavailable", "note": "No persisted run recorded."}),
], ids=("cached-shadow", "populated-predictions", "student-building", "distill-building", "backtest-no-run", "factors-no-run", "fundamentals-no-run"))
def test_successful_reader_results_preserve_ordinary_lifecycle(
    monkeypatch, surface, module_name, reader_name, payload
):
    from app import web
    from datetime import date

    module = importlib.import_module(module_name)
    calls = _return_from_reader(monkeypatch, module, reader_name, payload)
    expected = copy.deepcopy(payload)
    secondary = None
    if surface == "shadow_books":
        secondary = _raise_from_reader(monkeypatch, module, "run", "unexpected simulation")
        expected["policies"] = [
            {"id": p["id"], "label": p["label"], "label_zh": p.get("label_zh"),
             "desc": p.get("desc"), "desc_zh": p.get("desc_zh")}
            for p in module.POLICIES
        ]
    elif surface in {"student", "distill"}:
        predictions = [{"ticker": "FIXTURE", "predicted": 0.25}]
        secondary = _return_from_reader(monkeypatch, module, "predict", predictions)
        expected["top_predicted"] = predictions

    response = getattr(web, "api_" + surface)()
    assert response.status_code == 200
    assert _body(response) == expected
    assert "read_status" not in _body(response)
    assert "error" not in _body(response)
    assert len(calls) == 1
    if surface == "predictions":
        assert len(calls[0][0]) == 1 and calls[0][1] == {}
        date.fromisoformat(calls[0][0][0])
    else:
        assert calls == [((), {})]
    if surface == "shadow_books":
        assert secondary == []
    elif surface in {"student", "distill"}:
        assert secondary == [((), {"top": 12})]


def test_successful_empty_predictions_are_not_a_read_failure(monkeypatch):
    from app import web
    from portfolio import predictions
    from datetime import date

    expected = {"coverage": {"n_total": 0, "n_resolved": 0}, "scorecard": {"status": "building", "n": 0}}
    calls = _return_from_reader(monkeypatch, predictions, "summary", expected)
    response = web.api_predictions()
    assert response.status_code == 200
    assert _body(response) == expected
    assert len(calls) == 1 and len(calls[0][0]) == 1 and calls[0][1] == {}
    date.fromisoformat(calls[0][0][0])


def test_shadow_books_empty_cache_keeps_controlled_fallback(monkeypatch):
    from app import web
    from portfolio import shadow_books
    from datetime import date

    loaded = _return_from_reader(monkeypatch, shadow_books, "load_leaderboard", {})
    fixture = {"as_of": "2026-09-17", "leaderboard": [], "books": {}}
    fallback = _return_from_reader(monkeypatch, shadow_books, "run", fixture)
    response = web.api_shadow_books()
    payload = _body(response)
    assert response.status_code == 200
    assert payload["as_of"] == fixture["as_of"]
    assert payload["leaderboard"] == [] and payload["books"] == {}
    assert isinstance(payload["policies"], list)
    assert "read_status" not in payload and "error" not in payload
    assert loaded == [((), {})]
    assert len(fallback) == 1 and len(fallback[0][0]) == 1 and fallback[0][1] == {}
    date.fromisoformat(fallback[0][0][0])


@pytest.mark.parametrize("surface", ("student", "distill"))
def test_model_prediction_failure_does_not_preserve_partial_healthy_summary(monkeypatch, caplog, surface):
    from app import web

    module = importlib.import_module("brain." + surface)
    summary_calls = _return_from_reader(
        monkeypatch, module, "summary", {"status": "scoring", "n": 12, "partial_summary_marker": True}
    )
    prediction_calls = _raise_from_reader(
        monkeypatch, module, "predict", "secret /Users/private/model-prediction"
    )
    response = getattr(web, "api_" + surface)()
    _assert_failed_read(response, prediction_calls, caplog)
    payload = _body(response)
    _closed(payload, surface + "_unavailable")
    assert payload["status"] == "unavailable" and payload["top_predicted"] is None
    assert "partial_summary_marker" not in payload and "n" not in payload
    assert summary_calls == [((), {})]
    assert prediction_calls == [((), {"top": 12})]


def test_rejections_failure_is_unavailable_not_zero_coverage(monkeypatch, caplog):
    from app import web
    from portfolio import rejections

    calls = _raise_from_reader(
        monkeypatch, rejections, "summary", "secret /Users/private/rejections token=hidden"
    )
    response = web.api_rejections()
    _assert_failed_read(response, calls, caplog)
    payload = _body(response)
    _closed(payload, "rejections_unavailable")
    assert payload["coverage"] is None and payload["scorecard"] is None


@pytest.mark.parametrize("expected", [
    {"coverage": {"n_total": 0, "n_resolved": 0}, "scorecard": {"status": "building", "n_resolved": 0}},
    {"coverage": {"n_total": 3, "n_resolved": 2}, "scorecard": {"status": "building", "n_resolved": 2}},
], ids=("empty", "populated"))
def test_successful_rejections_preserve_ordinary_coverage(monkeypatch, expected):
    from app import web
    from portfolio import rejections
    from datetime import date

    calls = _return_from_reader(monkeypatch, rejections, "summary", expected)
    response = web.api_rejections()
    assert response.status_code == 200
    assert _body(response) == expected
    assert "read_status" not in _body(response) and "error" not in _body(response)
    assert len(calls) == 1 and len(calls[0][0]) == 1 and calls[0][1] == {}
    date.fromisoformat(calls[0][0][0])
