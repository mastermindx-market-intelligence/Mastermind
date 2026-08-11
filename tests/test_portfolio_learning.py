from __future__ import annotations

import json

import pandas as pd

from brain import portfolio_learning as pl


def test_context_requests_are_typed_and_deduplicated(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    bad = pl.request_context("autonomous", "../../secrets", "need this for a decision")
    assert bad["ok"] is False
    first = pl.request_context("autonomous", "terminal.intraday", "Need verified intraday breadth for timing", "AAPL")
    again = pl.request_context("autonomous", "terminal.intraday", "Need verified intraday breadth for timing", "AAPL")
    assert first["ok"] is True and again == {"ok": True, "deduped": True}
    row = json.loads((tmp_path / "context_requests.jsonl").read_text().strip())
    assert row["authority"] == "request_only"


def test_context_request_ids_do_not_collide_within_one_second(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    first = pl.request_context(
        "autonomous", "terminal.flow", "Need ticker flow for a current exit decision", "AAPL"
    )["request"]
    second = pl.request_context(
        "autonomous", "terminal.options", "Need options structure for a current exit decision", "AAPL"
    )["request"]
    assert first["id"] != second["id"]


def test_context_request_reports_failed_local_append(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    monkeypatch.setattr(pl, "_append_jsonl", lambda path, row: False)
    result = pl.request_context(
        "autonomous", "terminal.flow", "Need verified flow context for an exit review", "AAPL"
    )
    assert result == {"ok": False, "error": "context_request_write_failed"}
    assert pl.context_requests() == []


def test_universal_lessons_share_only_after_two_markets(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    lesson = {"code": "churn_hysteresis", "shareability": "universal", "status": "active",
              "rule": "Require a hard reason for very early reversals.", "evidence": {"n": 20}}
    pl._write_json(tmp_path / "autonomous" / "lessons.json", {"lessons": [{**lesson, "scope": "autonomous"}]})
    assert pl._validated_universal_lessons() == []
    pl._write_json(tmp_path / "china" / "lessons.json", {"lessons": [{**lesson, "scope": "china"}]})
    shared = pl._validated_universal_lessons()
    assert shared[0]["validated_in_books"] == ["autonomous", "china"]


def test_post_sell_summary_measures_opportunity_cost():
    rows = [
        {"sale_kind": "full_exit", "forward": {"21": {"relative_return": 0.08}}},
        {"sale_kind": "full_exit", "forward": {"21": {"relative_return": -0.02}}},
        {"sale_kind": "partial_trim", "forward": {"21": {"relative_return": 0.12}}},
    ]
    summary = pl._post_sell_summary(rows)
    assert summary["n_sales"] == 3
    assert summary["n_exits"] == 2
    assert summary["n_partial_trims"] == 1
    assert summary["by_horizon"]["21"]["full_exits"] == {
        "n": 2, "mean_relative_return": 0.03, "sold_before_outperformance_rate": 0.5}
    assert summary["by_horizon"]["21"]["partial_trims"]["mean_relative_return"] == 0.12


def test_same_session_grade_preserves_fill_price_and_historical_asof_cutoff():
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"])
    stock = pd.Series([90.0, 95.0, 100.0, 110.0], index=idx)
    benchmark = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)

    # Absolute opportunity cost keeps the immutable fill; relative performance uses the shared
    # Jan-2-to-Jan-5 close window for both instruments.
    grade = pl._same_session_grade(
        stock, benchmark, "2026-01-02", 1, fill_price=100.0,
        available_through="2026-01-05",
    )
    assert grade["return"] == -0.05
    assert grade["bar_date"] == grade["benchmark_bar_date"] == "2026-01-05"
    assert grade["stock_session_return"] == round(95.0 / 90.0 - 1.0, 6)
    assert grade["benchmark_return"] == 0.01

    # A historical rerun may not consume a later bar already present in the local store.
    pending = pl._same_session_grade(
        stock, benchmark, "2026-01-02", 2, fill_price=100.0,
        available_through="2026-01-05",
    )
    assert pending["status"] == "pending"
    assert pending["pending_reason"] == "target_after_available_through"
    assert pending["relative_return"] is None


def test_post_sell_ledger_distinguishes_trim_from_full_exit(monkeypatch, tmp_path):
    from portfolio import registry, trade_history

    monkeypatch.setattr(pl, "_DIR", tmp_path)
    monkeypatch.setattr(registry, "benchmark", lambda book: "SPY")
    monkeypatch.setattr(trade_history, "_load_fills", lambda book: [
        {"date": "2026-01-02", "ticker": "AAPL", "side": "buy", "shares": 10,
         "price": 100, "value": 1_000, "_seq": 0},
        {"date": "2026-01-05", "ticker": "AAPL", "side": "sell", "shares": 4,
         "price": 110, "value": 440, "_seq": 1},
        {"date": "2026-01-06", "ticker": "AAPL", "side": "sell", "shares": 6,
         "price": 120, "value": 720, "_seq": 2},
    ])
    monkeypatch.setattr(pl, "_series", lambda ticker: None)

    result = pl.refresh_post_sell("autonomous", asof="2026-01-06")
    assert [row["sale_kind"] for row in result["exits"]] == ["partial_trim", "full_exit"]
    assert result["exits"][0]["fraction_of_position_sold"] == 0.4
    assert result["summary"]["n_exits"] == 1
    assert result["summary"]["n_partial_trims"] == 1


def test_post_sell_relative_return_uses_one_canonical_market_session(monkeypatch, tmp_path):
    from portfolio import registry, trade_history

    monkeypatch.setattr(pl, "_DIR", tmp_path)
    monkeypatch.setattr(pl, "HORIZONS", (2, 3))
    monkeypatch.setattr(registry, "benchmark", lambda book: "SPY")
    monkeypatch.setattr(trade_history, "_load_fills", lambda book: [
        {"date": "2025-12-31", "ticker": "AAPL", "side": "buy", "shares": 10,
         "price": 80, "value": 800, "_seq": 0},
        {"date": "2026-01-02", "ticker": "AAPL", "side": "sell", "shares": 10,
         "price": 100, "value": 1_000, "_seq": 1},
    ])
    stock = pd.Series(
        [90.0, 99.0, 108.0],
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-07"]),
    )
    benchmark = pd.Series(
        [100.0, 105.0, 108.0, 110.0],
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]),
    )
    monkeypatch.setattr(pl, "_series", lambda ticker: stock if ticker == "AAPL" else benchmark)
    monkeypatch.setattr(pl, "_decision_exit", lambda *args: {})

    result = pl.refresh_post_sell("autonomous", asof="2026-01-07")
    grades = result["exits"][0]["forward"]

    # The benchmark's second session is Jan 6. A suspended/missing stock bar must not shift the
    # stock leg to Jan 7 and compare two different windows.
    assert grades["2"]["canonical_target_date"] == "2026-01-06"
    assert grades["2"]["status"] == "pending"
    assert grades["2"]["pending_reason"] == "missing_stock_target_session"
    assert grades["2"]["relative_return"] is None

    # On the shared Jan 7 target, relative return is close-to-close for both legs (20% - 10%).
    # The absolute opportunity cost separately preserves the immutable 100 paper fill (8%).
    assert grades["3"]["bar_date"] == grades["3"]["benchmark_bar_date"] == "2026-01-07"
    assert grades["3"]["return"] == 0.08
    assert grades["3"]["stock_session_return"] == 0.20
    assert grades["3"]["benchmark_return"] == 0.10
    assert grades["3"]["relative_return"] == 0.10
    assert grades["3"]["relative_return_basis"] == "same_session_close_to_close"


def test_prompt_keeps_full_exits_and_partial_trims_separate(monkeypatch, tmp_path):
    monkeypatch.setattr(pl, "_DIR", tmp_path)
    pl._write_json(tmp_path / "autonomous" / "lessons.json", {"metrics": {}, "lessons": []})
    pl._write_json(tmp_path / "autonomous" / "post_sell.json", {"exits": [
        {"ticker": "AAPL", "exit_date": "2026-01-02", "sale_kind": "partial_trim",
         "fraction_of_position_sold": 0.25,
         "forward": {"21": {"relative_return": 0.08, "status": "graded"}}},
        {"ticker": "MSFT", "exit_date": "2026-01-03", "sale_kind": "full_exit",
         "fraction_of_position_sold": 1.0,
         "forward": {"21": {"relative_return": -0.02, "status": "graded"}}},
    ]})

    block = pl.prompt_block("autonomous")

    assert "Recent full-exit audit" in block
    assert '"ticker":"MSFT"' in block and '"sale_kind":"full_exit"' in block
    assert "Recent partial-trim audit" in block
    assert '"ticker":"AAPL"' in block and '"sale_kind":"partial_trim"' in block
    assert '"fraction_sold":0.25' in block
