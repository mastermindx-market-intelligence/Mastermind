"""Truthful valuation regressions for the user-controlled Self-Directed book.

The scheduled mark/publication path must never manufacture a market value from cost basis, never
borrow an undated current quote for a historical mark, and never partially advance account provenance
when one held line is still unpriceable.
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from portfolio import self_directed as SD


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "self_directed"
    monkeypatch.setattr(SD, "_DATA", data)
    monkeypatch.setattr(SD, "_ACCOUNT_PATH", data / "account.json")
    monkeypatch.setattr(SD, "_FILLS_PATH", data / "fills.jsonl")
    monkeypatch.setattr(SD, "_PENDING_PATH", data / "pending.json")
    monkeypatch.setattr(SD, "_THESES_PATH", data / "theses.json")
    monkeypatch.setattr(SD, "_NAV_PATH", data / "nav_history.jsonl")
    monkeypatch.setattr(SD, "_PUBLISHED_PATH", tmp_path / "published" / "latest.json")
    SD.set_price_resolver(None)
    yield tmp_path
    SD.set_price_resolver(None)


def _state(*, positions: dict, cash: float = 500_000.0) -> dict:
    return {
        "inception_date": "2026-05-01",
        "starting_nav": 1_000_000.0,
        "cash": cash,
        "positions": positions,
    }


def _position(*, shares=1_000.0, avg_cost=100.0, current=None, current_asof=None) -> dict:
    row = {"shares": shares, "avg_cost": avg_cost}
    if current is not None:
        row["current_price"] = current
    if current_asof is not None:
        row["current_price_asof"] = current_asof
    return row


def test_missing_observation_carries_prior_dated_market_mark_not_avg_cost(sandbox, monkeypatch):
    SD._save_account(_state(positions={
        "AAPL": _position(avg_cost=100.0, current=150.0, current_asof="2026-06-01"),
    }))
    monkeypatch.setattr(SD, "_carry_stale_max_days", lambda: 30)

    row = SD.mark(prices={}, asof="2026-06-02")

    assert row["invested"] == pytest.approx(150_000.0)
    assert row["nav"] == pytest.approx(650_000.0)
    lot = SD._load_account()["positions"]["AAPL"]
    assert lot["current_price"] == 150.0
    assert lot["current_price_asof"] == "2026-06-01"
    assert row["invested"] != pytest.approx(100_000.0)


def test_historical_unpriced_mark_refuses_without_current_quote_or_state_mutation(sandbox, monkeypatch):
    original = _state(positions={"AAPL": _position(avg_cost=100.0)})
    SD._save_account(deepcopy(original))
    monkeypatch.setattr(
        SD,
        "_live_quote",
        lambda _ticker: pytest.fail("historical mark must not use an undated live quote"),
    )
    monkeypatch.setattr(
        SD,
        "_stockdata_price",
        lambda _ticker: pytest.fail("historical mark must not relabel an undated snapshot"),
    )

    with pytest.raises(SD.SelfDirectedMarkUnavailable):
        SD.mark(prices={}, asof="2026-06-01")

    assert SD._load_account() == original
    assert not SD._NAV_PATH.exists()


@pytest.mark.parametrize("mark_asof", ["2026-06-02", "2026-04-01", "not-a-date", None])
def test_future_stale_or_undated_persisted_mark_fails_closed(sandbox, monkeypatch, mark_asof):
    SD._save_account(_state(positions={
        "AAPL": _position(current=150.0, current_asof=mark_asof),
    }))
    monkeypatch.setattr(SD, "_carry_stale_max_days", lambda: 30)

    with pytest.raises(SD.SelfDirectedMarkUnavailable):
        SD.mark(prices={}, asof="2026-06-01")


def test_canonical_resolver_miss_is_authoritative_even_on_same_day(sandbox, monkeypatch):
    SD._save_account(_state(positions={"AAPL": _position()}))
    monkeypatch.setattr(SD, "_today", lambda: "2026-06-01")
    monkeypatch.setattr(
        SD,
        "_live_quote",
        lambda _ticker: pytest.fail("canonical resolver miss must not fall through to live quote"),
    )
    monkeypatch.setattr(
        SD,
        "_stockdata_price",
        lambda _ticker: pytest.fail("canonical resolver miss must not fall through to snapshot"),
    )
    SD.set_price_resolver(lambda _ticker: None)

    with pytest.raises(SD.SelfDirectedMarkUnavailable):
        SD.mark(prices={}, asof="2026-06-01")


def test_one_missing_line_prevents_partial_provenance_update(sandbox):
    original = _state(positions={
        "AAPL": _position(avg_cost=100.0),
        "MSFT": _position(avg_cost=200.0),
    })
    SD._save_account(deepcopy(original))
    SD.set_price_resolver(lambda _ticker: None)

    with pytest.raises(SD.SelfDirectedMarkUnavailable):
        SD.mark(prices={"AAPL": 175.0}, asof="2026-06-01")

    assert SD._load_account() == original
    assert not SD._NAV_PATH.exists()


def test_publish_refusal_preserves_last_truthful_artifact(sandbox):
    SD._save_account(_state(positions={"AAPL": _position(avg_cost=100.0)}))
    SD._PUBLISHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    prior = {"schema": "portfolio.v1", "portfolio_id": "self_directed", "as_of": "2026-05-31", "nav": 612345.0}
    SD._PUBLISHED_PATH.write_text(json.dumps(prior))

    with pytest.raises(SD.SelfDirectedMarkUnavailable):
        SD.publish(prices={}, asof="2026-06-01")

    assert json.loads(SD._PUBLISHED_PATH.read_text()) == prior


def test_publish_uses_bounded_persisted_market_mark_for_weight_and_nav(sandbox, monkeypatch):
    SD._save_account(_state(positions={
        "AAPL": _position(shares=1_000.0, avg_cost=100.0, current=150.0, current_asof="2026-06-01"),
    }))
    monkeypatch.setattr(SD, "_carry_stale_max_days", lambda: 30)

    doc = SD.publish(prices={}, asof="2026-06-02")

    assert doc["nav"] == pytest.approx(650_000.0)
    assert doc["positions"][0]["current_price"] == pytest.approx(150.0)
    assert doc["positions"][0]["market_value"] == pytest.approx(150_000.0)
    assert doc["positions"][0]["weight"] == pytest.approx(150_000.0 / 650_000.0, abs=1e-6)
