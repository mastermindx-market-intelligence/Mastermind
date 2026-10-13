"""Partial published weights must not masquerade as complete concentration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio import forward_evaluation, registry


DAY = "2026-08-13"
METRICS = ("top_1_weight_pct", "top_3_weight_pct", "position_hhi")


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def isolated_book(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(forward_evaluation, "_utc_today", lambda: DAY)
    forward_evaluation.initialize_start("a" * 40, "2026-08-11")
    forward_evaluation.finalize_start("a" * 40)
    return tmp_path


def _seed(book, bad_row, account):
    base = registry.data_dir(book)
    _write_json(base / "nav_history.jsonl", {
        "date": DAY, "nav": 1000, "cash": 200, "invested": 800,
    })
    _write_json(base / "latest.json", {
        "as_of": DAY,
        "positions": [{"ticker": "AAA", "weight": 0.3}, bad_row],
    })
    if account is not None:
        _write_json(base / "account.json", account)


@pytest.mark.parametrize("book", forward_evaluation.ACTIVE_BOOKS)
@pytest.mark.parametrize("bad_row", [None, "unavailable", [], 0])
def test_partial_published_weights_use_complete_account_marks(isolated_book, book, bad_row):
    _seed(book, bad_row, {"positions": {
        "AAA": {"shares": 3, "current_price": 100},
        "BBB": {"shares": 5, "current_price": 100},
    }})

    snapshot = forward_evaluation.evaluate(book, DAY)

    assert snapshot["inputs"]["latest"]["status"] == "partial"
    assert snapshot["inputs"]["account"]["status"] == "available"
    for name, value in zip(METRICS, [50.0, 80.0, 0.34], strict=True):
        assert snapshot["metrics"][name] == {
            "value": value, "sample_n": 2, "status": "available", "missing_reason": None,
        }
    served = forward_evaluation.status(book, DAY)
    assert served["snapshot"] == snapshot
    assert served["metric_status_counts"] == snapshot["metric_status_counts"]


@pytest.mark.parametrize("account", [
    None,
    {"positions": {"AAA": {"shares": 3, "current_price": 100},
                   "BBB": {"shares": 5, "avg_cost": 100}}},
])
def test_partial_published_weights_without_complete_marks_stay_unknown(isolated_book, account):
    _seed("autonomous", None, account)

    snapshot = forward_evaluation.evaluate("autonomous", DAY)

    assert snapshot["inputs"]["latest"]["status"] == "partial"
    for name in METRICS:
        metric = snapshot["metrics"][name]
        assert metric["value"] is None
        assert metric["status"] == "partial"
        assert metric["missing_reason"] == "some_current_positions_lack_durable_weight_or_mark"
    assert forward_evaluation.status("autonomous")["snapshot"] == snapshot


def test_complete_same_day_published_weights_keep_existing_precedence(isolated_book):
    _seed("autonomous", {"ticker": "BBB", "weight": 0.5}, None)

    snapshot = forward_evaluation.evaluate("autonomous", DAY)

    assert snapshot["inputs"]["latest"]["status"] == "available"
    for name, value in zip(METRICS, [50.0, 80.0, 0.34], strict=True):
        assert snapshot["metrics"][name]["value"] == value
        assert snapshot["metrics"][name]["status"] == "available"


def test_complete_cash_only_portfolio_preserves_known_zero(isolated_book):
    base = registry.data_dir("autonomous")
    _write_json(base / "nav_history.jsonl", {
        "date": DAY, "nav": 1000, "cash": 1000, "invested": 0,
    })
    _write_json(base / "latest.json", {"as_of": DAY, "positions": []})
    _write_json(base / "account.json", {"positions": {}})

    snapshot = forward_evaluation.evaluate("autonomous", DAY)

    for name in METRICS:
        assert snapshot["metrics"][name] == {
            "value": 0.0, "sample_n": 0, "status": "available", "missing_reason": None,
        }


def test_partial_weights_do_not_bypass_historical_account_guard(isolated_book):
    _seed("autonomous", None, {"positions": {
        "AAA": {"shares": 3, "current_price": 100},
        "BBB": {"shares": 5, "current_price": 100},
    }})
    nav_path = registry.data_dir("autonomous") / "nav_history.jsonl"
    with nav_path.open("a", encoding="utf-8") as stream:
        stream.write("\n" + json.dumps({
            "date": "2026-08-14", "nav": 1100, "cash": 200, "invested": 900,
        }))

    snapshot = forward_evaluation.evaluate("autonomous", DAY)

    for name in METRICS:
        assert snapshot["metrics"][name] == {
            "value": None, "sample_n": 0, "status": "missing",
            "missing_reason": "current_account_is_not_point_in_time_for_historical_asof",
        }
