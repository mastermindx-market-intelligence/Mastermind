"""Existing malformed Self-Directed state must fail closed before any mutation."""
from __future__ import annotations

import json

import pytest

from control_plane import run_events
from portfolio import self_directed as SD

@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "self_directed"
    data.mkdir()
    monkeypatch.setattr(run_events, "append", lambda *args, **kwargs: None)
    monkeypatch.setattr(SD, "_DATA", data)
    monkeypatch.setattr(SD, "_ACCOUNT_PATH", data / "account.json")
    monkeypatch.setattr(SD, "_FILLS_PATH", data / "fills.jsonl")
    monkeypatch.setattr(SD, "_PENDING_PATH", data / "pending.json")
    monkeypatch.setattr(SD, "_THESES_PATH", data / "theses.json")
    monkeypatch.setattr(SD, "_NAV_PATH", data / "nav_history.jsonl")
    monkeypatch.setattr(SD, "_PUBLISHED_PATH", tmp_path / "published" / "latest.json")
    monkeypatch.setattr(SD, "_today", lambda: "2026-09-16")
    yield tmp_path


def _seed_account() -> dict:
    state = {
        "inception_date": "2026-09-01", "starting_nav": 1_000_000.0,
        "cash": 900_000.0,
        "positions": {"AAPL": {"shares": 1_000.0, "avg_cost": 100.0}},
    }
    SD._save_account(state)
    return state


def test_missing_state_is_still_legitimate_first_run(sandbox):
    account = SD._load_account()
    assert account["cash"] == 1_000_000.0
    assert account["positions"] == {}
    assert SD._load_pending() == []
    assert SD._load_theses() == {}
    assert SD._load_fills() == []


def test_corrupt_account_refuses_order_without_overwrite(sandbox):
    SD._ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = '{"cash":900000,"positions":'
    SD._ACCOUNT_PATH.write_text(old)

    with pytest.raises(SD.SelfDirectedAccountInvalid):
        SD.place_order("AAPL", "buy", shares=1.0, price=100.0, market_open=True)

    assert SD._ACCOUNT_PATH.read_text() == old


def test_corrupt_pending_queue_refuses_new_order_without_erasing_queue(sandbox):
    _seed_account()
    old = '[{"order_id":"keep-me"}'
    SD._PENDING_PATH.write_text(old)

    with pytest.raises(SD.SelfDirectedStateCorrupt, match="pending"):
        SD.place_order("MSFT", "buy", shares=1.0, market_open=False)

    assert SD._PENDING_PATH.read_text() == old


def test_corrupt_theses_refuse_save_without_erasing_notes(sandbox):
    _seed_account()
    old = '{"AAPL":{"note":"keep"}'
    SD._THESES_PATH.write_text(old)

    with pytest.raises(SD.SelfDirectedStateCorrupt, match="theses"):
        SD.set_thesis("MSFT", "new note")

    assert SD._THESES_PATH.read_text() == old


def test_corrupt_nav_history_refuses_mark_before_account_provenance_changes(sandbox):
    original = _seed_account()
    old_nav = '{"date":"2026-09-15","nav":1040000}\n{"date":'
    SD._NAV_PATH.write_text(old_nav)

    with pytest.raises(SD.SelfDirectedStateCorrupt, match="nav_history"):
        SD.mark(prices={"AAPL": 160.0, "SPY": 510.0}, asof="2026-09-16")

    assert SD._NAV_PATH.read_text() == old_nav
    assert SD._load_account() == original


def test_corrupt_fill_log_refuses_open_order_before_account_mutation(sandbox):
    original = _seed_account()
    old_fills = '{"date":"2026-09-15","ticker":"AAPL"}\n{"date":'
    SD._FILLS_PATH.write_text(old_fills)

    with pytest.raises(SD.SelfDirectedStateCorrupt, match="fills"):
        SD.place_order("MSFT", "buy", shares=1.0, price=200.0, market_open=True)

    assert SD._load_account() == original
    assert SD._FILLS_PATH.read_text() == old_fills


def test_corrupt_fill_log_blocks_history_settlement_before_any_state_change(sandbox):
    original = _seed_account()
    pending = [{
        "order_id": "queued-1", "ticker": "MSFT", "side": "buy",
        "shares": 1.0, "placed_at": "2026-09-15T20:00:00+00:00", "status": "pending",
    }]
    SD._save_pending(pending)
    old_fills = '{"date":'
    SD._FILLS_PATH.write_text(old_fills)

    with pytest.raises(SD.SelfDirectedStateCorrupt, match="fills"):
        SD.history(prices={"MSFT": 200.0}, market_open=True)

    assert SD._load_account() == original
    assert SD._load_pending() == pending
    assert SD._FILLS_PATH.read_text() == old_fills


def test_wrong_shape_existing_state_is_corruption_not_empty(sandbox):
    SD._ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SD._ACCOUNT_PATH.write_text(json.dumps({"cash": "not-a-number", "positions": []}))
    SD._PENDING_PATH.write_text(json.dumps({"not": "a-list"}))
    SD._THESES_PATH.write_text(json.dumps(["not", "a-dict"]))

    with pytest.raises(SD.SelfDirectedAccountInvalid):
        SD._load_account()
    with pytest.raises(SD.SelfDirectedStateCorrupt, match="pending"):
        SD._load_pending()
    with pytest.raises(SD.SelfDirectedStateCorrupt, match="theses"):
        SD._load_theses()


@pytest.mark.parametrize("literal", ["true", "false", "1e309", "-1e309", "NaN", "9" * 400])
def test_invalid_cash_refuses_order_and_preserves_state(sandbox, literal):
    account = SD._ACCOUNT_PATH
    original = ('{"cash":' + literal + ',"positions":{}}').encode()
    account.write_bytes(original)

    with pytest.raises(SD.SelfDirectedAccountInvalid):
        SD.place_order("AAPL", "buy", shares=1.0, price=100.0, market_open=True)

    assert account.read_bytes() == original
    assert not SD._FILLS_PATH.exists()


@pytest.mark.parametrize("cash", [0, 12.5, -2])
def test_finite_cash_retains_its_value(sandbox, cash):
    account = SD._ACCOUNT_PATH
    account.write_text(json.dumps({"cash": cash, "positions": {}}))
    assert SD._load_account()["cash"] == cash


@pytest.mark.parametrize("bad_order", [
    None, {"shares": "bad"}, {"notional": False}, {"shares": float("inf")},
    {"shares": -1}, {}, {"shares": 1, "notional": 100},
    {"ticker": 7, "shares": 1}, {"ticker": " ", "shares": 1},
    {"side": "unknown", "shares": 1},
])
def test_malformed_later_pending_row_preserves_prior_fill_and_account(sandbox, bad_order):
    original = _seed_account()
    pending = [
        {"order_id": "queued-1", "ticker": "MSFT", "side": "buy", "shares": 1.0},
        {"ticker": "AAPL", "side": "sell", **bad_order} if bad_order is not None else None,
    ]
    snapshot = json.dumps(pending)
    SD._PENDING_PATH.write_text(snapshot)

    for _ in range(2):
        with pytest.raises(SD.SelfDirectedStateCorrupt, match="pending"):
            SD.settle_pending(market_open=True, prices={"MSFT": 200.0, "AAPL": 100.0})
    assert SD._PENDING_PATH.read_text() == snapshot

    assert SD._load_account() == original
    assert json.loads(SD._PENDING_PATH.read_text()) == pending
    assert not SD._FILLS_PATH.exists()


@pytest.mark.parametrize("sizing", [{"shares": 0.0}, {"notional": 0, "shares": None}])
def test_legacy_rounded_zero_order_settles_without_fill(sandbox, sizing):
    _seed_account()
    SD._save_pending([{"ticker": "MSFT", "side": "buy", **sizing}])
    settled = SD.settle_pending(market_open=True, prices={"MSFT": 200.0})
    assert [order["status"] for order in settled] == ["cancelled"]
    assert not SD._FILLS_PATH.exists()


@pytest.mark.parametrize("field", ["shares", "notional"])
def test_nonfinite_sizing_cannot_create_unreadable_pending_order(sandbox, field):
    result = SD.place_order("MSFT", "buy", **{field: float("inf")}, market_open=False)
    assert result["ok"] is False
    assert not SD._PENDING_PATH.exists()
