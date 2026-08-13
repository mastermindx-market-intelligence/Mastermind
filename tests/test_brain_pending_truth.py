"""Receipt-honest /api/trades projection for complete Brain target queues."""
from __future__ import annotations

import json

import pytest


_NEXT_OPEN = "2026-08-13T09:30:00-04:00"


@pytest.fixture
def trades_env(monkeypatch):
    """Keep route tests local and deterministic; only the pending-target helper is under test."""
    from app import web
    from portfolio import market_calendar, paper_account, position_log, trade_history

    state: dict = {
        "account": {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
        },
        "prices": {},
        "target": None,
        "target_exists": False,
        "legacy": [],
    }
    monkeypatch.setattr(web, "_account_tickers", lambda portfolio_id=None: list(
        state["account"]["positions"]
    ))
    monkeypatch.setattr(
        web,
        "_live_prices",
        lambda tickers, refresh=None: dict(state["prices"]),
    )
    monkeypatch.setattr(web, "_attach_security_names", lambda rows: None)
    monkeypatch.setattr(
        trade_history,
        "history",
        lambda prices, portfolio_id=None, account_state=None: [],
    )
    monkeypatch.setattr(position_log, "open_positions", lambda portfolio_id=None: [])
    monkeypatch.setattr(position_log, "closed_positions", lambda portfolio_id=None: [])
    monkeypatch.setattr(paper_account, "load_pending", lambda portfolio_id=None: list(
        state["legacy"]
    ))
    monkeypatch.setattr(
        paper_account,
        "load_pending_target",
        lambda portfolio_id=None: state["target"],
    )
    monkeypatch.setattr(
        paper_account,
        "pending_target_file_exists",
        lambda portfolio_id=None: bool(state["target_exists"]),
    )
    monkeypatch.setattr(
        paper_account,
        "_load_account_file",
        lambda portfolio_id=None, strict=False: state["account"],
    )
    monkeypatch.setattr(
        paper_account,
        "_transaction_path",
        lambda portfolio_id=None: type("NoWal", (), {"exists": lambda self: False})(),
    )
    monkeypatch.setattr(
        market_calendar,
        "status",
        lambda: {
            "open": False,
            "asof_et": "2026-08-12T19:18:15-04:00",
            "next_open": _NEXT_OPEN,
            "next_open_day": "2026-08-13",
        },
    )
    return state


def _target(weights: dict[str, float]) -> dict:
    return {
        "schema_version": "pending_target.v2",
        "engine_version": "us_brain_v2",
        "portfolio_id": "autonomous",
        "target": weights,
        "asof": "2026-08-12",
        "queued_at": "2026-08-12T23:18:15+00:00",
    }


def _response():
    from app import web

    response = web.api_trades("autonomous")
    assert response.status_code == 200
    return json.loads(response.body)


def test_aug12_full_target_surfaces_three_unfilled_buys_and_a_carried_holding(trades_env):
    # AAPL is exactly 4% of the live account NAV.  It is a carry, not a fourth purchase.
    trades_env["account"] = {
        "inception_date": "2026-07-31",
        "starting_nav": 1_000_000.0,
        "cash": 960_000.0,
        "positions": {"AAPL": {"shares": 400.0, "avg_cost": 101.0}},
    }
    trades_env["prices"] = {
        "AAPL": 100.0, "XOM": 100.0, "COP": 100.0, "CVX": 100.0,
    }
    trades_env["target"] = _target({
        "XOM": 0.10,
        "COP": 0.10,
        "CVX": 0.05,
        "AAPL": 0.04,
    })
    trades_env["target_exists"] = True
    trades_env["legacy"] = [{
        "ticker": "LEGACY", "side": "buy", "shares": 2.0, "status": "pending"
    }]

    data = _response()

    target_rows = {row["ticker"]: row for row in data["pending_target"]["rows"]}
    assert data["pending_target"] == {
        "portfolio": "autonomous",
        "status": "queued",
        "rows": [target_rows[ticker] for ticker in sorted(target_rows)],
        "asof": "2026-08-12",
        "queued_at": "2026-08-12T23:18:15+00:00",
        "schema_version": "pending_target.v2",
        "engine_version": "us_brain_v2",
        "fill_after": _NEXT_OPEN,
        "comparison_status": "current_weights_available",
    }
    assert target_rows["AAPL"]["action"] == "hold"
    assert target_rows["AAPL"]["side"] == "hold"
    assert target_rows["AAPL"]["current_weight"] == pytest.approx(0.04)
    assert {
        ticker: (target_rows[ticker]["action"], target_rows[ticker]["side"])
        for ticker in ("XOM", "COP", "CVX")
    } == {
        "XOM": ("buy", "buy"),
        "COP": ("buy", "buy"),
        "CVX": ("buy", "buy"),
    }

    # Existing share-sized queues survive unchanged; full-target carries do not masquerade as
    # orders, and target intent never fabricates shares, prices, values, or fills.
    assert data["pending"][0] == trades_env["legacy"][0]
    projected_orders = [row for row in data["pending"] if row.get("source") == "pending_target"]
    assert {row["ticker"] for row in projected_orders} == {"XOM", "COP", "CVX"}
    assert all(row["status"] == "queued" for row in projected_orders)
    assert all(row["fill_after"] == _NEXT_OPEN for row in projected_orders)
    assert all(
        key not in row
        for row in target_rows.values()
        for key in ("shares", "est_price", "est_value", "price", "fill_price", "filled_at")
    )


def test_projection_distinguishes_add_trim_and_target_zero_exit(trades_env):
    trades_env["account"] = {
        "inception_date": "2026-08-01",
        "starting_nav": 10_000.0,
        "cash": 4_000.0,
        "positions": {
            "ADD": {"shares": 10.0, "avg_cost": 90.0},
            "TRIM": {"shares": 30.0, "avg_cost": 90.0},
            "EXIT": {"shares": 20.0, "avg_cost": 90.0},
        },
    }
    trades_env["prices"] = {"ADD": 100.0, "TRIM": 100.0, "EXIT": 100.0}
    trades_env["target"] = _target({"ADD": 0.20, "TRIM": 0.20})
    trades_env["target_exists"] = True

    data = _response()
    rows = {row["ticker"]: row for row in data["pending_target"]["rows"]}

    assert (rows["ADD"]["action"], rows["ADD"]["side"], rows["ADD"]["current_weight"]) == (
        "add", "buy", 0.1
    )
    assert (rows["TRIM"]["action"], rows["TRIM"]["side"], rows["TRIM"]["current_weight"]) == (
        "trim", "sell", 0.3
    )
    assert (rows["EXIT"]["action"], rows["EXIT"]["side"]) == ("exit", "sell")
    assert rows["EXIT"]["target_weight"] == 0.0
    assert {
        (row["ticker"], row["action"], row["side"])
        for row in data["pending"]
    } == {
        ("ADD", "add", "buy"),
        ("TRIM", "trim", "sell"),
        ("EXIT", "exit", "sell"),
    }


def test_unchanged_target_is_auditable_but_not_an_order(trades_env):
    trades_env["account"] = {
        "inception_date": "2026-08-01",
        "starting_nav": 10_000.0,
        "cash": 8_000.0,
        "positions": {"AAPL": {"shares": 20.0, "avg_cost": 90.0}},
    }
    trades_env["prices"] = {"AAPL": 100.0}
    trades_env["target"] = _target({"AAPL": 0.20})
    trades_env["target_exists"] = True

    data = _response()

    assert data["pending"] == []
    assert data["pending_target"]["rows"][0]["action"] == "hold"
    assert data["pending_target"]["rows"][0]["side"] == "hold"


@pytest.mark.parametrize(
    ("target_weight", "expected_action", "expected_side", "is_actionable"),
    [
        (0.209999, "hold", "hold", False),
        (0.21, "add", "buy", True),
        (0.190001, "hold", "hold", False),
        (0.19, "trim", "sell", True),
    ],
)
def test_continuing_position_respects_allocator_no_trade_band_boundary(
    trades_env,
    monkeypatch,
    target_weight,
    expected_action,
    expected_side,
    is_actionable,
):
    from portfolio import paper_account

    # Current weight is exactly 20%; the allocator's band is 1% of NAV.  Deltas inside the band
    # carry, while the exact +/-1% boundary is executable just as rebalance() specifies.
    monkeypatch.setattr(paper_account, "_no_trade_band_frac", lambda: 0.01)
    trades_env["account"] = {
        "inception_date": "2026-08-01",
        "starting_nav": 10_000.0,
        "cash": 8_000.0,
        "positions": {"AAPL": {"shares": 20.0, "avg_cost": 90.0}},
    }
    trades_env["prices"] = {"AAPL": 100.0}
    trades_env["target"] = _target({"AAPL": target_weight})
    trades_env["target_exists"] = True

    data = _response()
    row = data["pending_target"]["rows"][0]

    assert (row["action"], row["side"]) == (expected_action, expected_side)
    assert bool(data["pending"]) is is_actionable


def test_malformed_or_incompatible_queue_fails_closed_without_quarantine(trades_env, monkeypatch):
    from portfolio import paper_account

    trades_env["target"] = None
    trades_env["target_exists"] = True
    forbidden_calls: list[str] = []

    def forbidden(name):
        def _fail(*args, **kwargs):
            forbidden_calls.append(name)
            raise AssertionError(f"GET invoked mutating queue path: {name}")
        return _fail

    monkeypatch.setattr(paper_account, "preflight_pending_target", forbidden("preflight"))
    monkeypatch.setattr(paper_account, "quarantine_pending_target", forbidden("quarantine"))
    monkeypatch.setattr(paper_account, "recover_paper_transaction", forbidden("recovery"))
    monkeypatch.setattr(paper_account, "_load_account", forbidden("account_recovery"))

    data = _response()

    assert data["pending_target"] == {
        "portfolio": "autonomous", "status": "invalid", "rows": []
    }
    assert data["pending"] == []
    assert forbidden_calls == []


def test_account_read_failure_keeps_target_auditable_without_inventing_actions(
    trades_env, monkeypatch
):
    from portfolio import paper_account, trade_history

    trades_env["target"] = _target({"XOM": 0.10})
    trades_env["target_exists"] = True
    trades_env["prices"] = {"XOM": 100.0}

    def unavailable(*args, **kwargs):
        raise paper_account.PaperTransactionConflict("unreadable account")

    monkeypatch.setattr(paper_account, "_load_account_file", unavailable)
    observed_accounts: list[dict] = []

    def history(prices, portfolio_id=None, account_state=None):
        # None positions intentionally makes the FIFO reader degrade to fill-ledger truth instead
        # of treating every open BUY as closed (which an empty mapping would do).
        observed_accounts.append(account_state)
        return [{"ticker": "OLD", "action": "buy", "still_open": True}]

    monkeypatch.setattr(trade_history, "history", history)

    data = _response()

    assert data["snapshot_status"] == "account_unavailable"
    assert observed_accounts == [{"positions": None}]
    assert data["history"][0]["still_open"] is True
    assert data["pending"] == []
    assert data["pending_target"]["status"] == "queued"
    assert data["pending_target"]["comparison_status"] == "account_unavailable"
    assert data["pending_target"]["rows"] == [{
        "ticker": "XOM",
        "action": "comparison_unavailable",
        "target_weight": 0.10,
        "status": "queued",
        "source": "pending_target",
    }]


def test_unknown_authoritative_positions_do_not_close_fill_derived_open_buy(monkeypatch):
    from portfolio import trade_history

    monkeypatch.setattr(trade_history, "_load_fills", lambda portfolio_id=None: [{
        "date": "2026-08-01", "ticker": "AAPL", "side": "buy",
        "shares": 10.0, "price": 100.0, "value": 1000.0,
    }])

    rows = trade_history.history(
        {"AAPL": 110.0},
        portfolio_id="autonomous",
        account_state={"positions": None},
    )

    assert rows[0]["still_open"] is True
    assert rows[0]["open_shares"] == 10.0
    assert rows[0]["unrealized_pnl"] == 100.0


def test_outstanding_wal_returns_explicit_unavailable_snapshot_without_recovery(
    trades_env, monkeypatch
):
    from portfolio import paper_account, trade_history

    calls: list[str] = []
    monkeypatch.setattr(
        paper_account,
        "_transaction_path",
        lambda portfolio_id=None: type("Wal", (), {"exists": lambda self: True})(),
    )
    monkeypatch.setattr(
        paper_account,
        "recover_paper_transaction",
        lambda *args, **kwargs: calls.append("recover"),
    )
    monkeypatch.setattr(
        trade_history,
        "history",
        lambda *args, **kwargs: calls.append("history"),
    )

    data = _response()

    assert data["snapshot_status"] == "transaction_pending"
    assert data["pending_target"] == {
        "portfolio": "autonomous",
        "status": "unavailable",
        "comparison_status": "transaction_pending",
        "rows": [],
    }
    assert data["history"] == [] and data["pending"] == []
    assert calls == []


def test_new_position_minimum_and_buy_dust_match_allocator(trades_env, monkeypatch):
    from portfolio import paper_account

    monkeypatch.setattr(paper_account, "_min_position_frac", lambda: 0.005)
    monkeypatch.setattr(paper_account, "_min_trade_frac", lambda: 0.001)
    trades_env["account"] = {
        "inception_date": "2026-08-01",
        "starting_nav": 10_000.0,
        "cash": 10_000.0,
        "positions": {},
    }
    trades_env["prices"] = {"TOOSMALL": 10.0, "DUST": 1000.0, "OK": 10.0}
    trades_env["target"] = _target({"TOOSMALL": 0.0049, "DUST": 0.005, "OK": 0.01})
    trades_env["target_exists"] = True

    data = _response()
    rows = {row["ticker"]: row for row in data["pending_target"]["rows"]}

    assert rows["TOOSMALL"]["suppressed_by"] == "minimum_position"
    # $50 desired at a $1000 share price floors to zero shares before the notional test.
    assert rows["DUST"]["suppressed_by"] == "buy_dust"
    assert (rows["OK"]["action"], rows["OK"]["side"]) == ("buy", "buy")
    assert {row["ticker"] for row in data["pending"]} == {"OK"}


def test_preserve_existing_shares_constraint_never_projects_resize(trades_env, monkeypatch):
    from portfolio import paper_account

    trades_env["account"] = {
        "inception_date": "2026-08-01",
        "starting_nav": 10_000.0,
        "cash": 9_000.0,
        "positions": {"AAPL": {"shares": 10.0, "avg_cost": 90.0}},
    }
    trades_env["prices"] = {"AAPL": 100.0}
    target = _target({"AAPL": 0.50})
    target["execution_constraints"] = {
        "schema": "execution_constraints.v1",
        "mode": "preserve_existing_shares",
        "tickers": ["AAPL"],
        "target_sha256": "a" * 64,
        "positions_sha256": paper_account.positions_sha256(trades_env["account"]["positions"]),
    }
    trades_env["target"] = target
    trades_env["target_exists"] = True

    data = _response()
    row = data["pending_target"]["rows"][0]

    assert (row["action"], row["side"]) == ("hold", "hold")
    assert row["suppressed_by"] == "preserve_existing_shares"
    assert data["pending"] == []


def test_decision_api_uses_settlement_day_for_pnl_and_marks_receipt_truth(monkeypatch):
    from app import web
    from portfolio import registry, trade_history

    transaction_id = "a" * 64
    fill_id = "b" * 64
    row = {
        "asof": "2026-08-12",
        "accepted_asof": "2026-08-12",
        "settled_asof": "2026-08-13",
        "target_status": "executed",
        "decision_id": "decision.v1." + "d" * 24,
        "submission_sha256": "e" * 64,
        "target_sha256": "f" * 64,
        "settlement_transaction_id": transaction_id,
        "settlement_receipt_sha256": "c" * 64,
        "settlement_fill_ids": [fill_id],
        "executed": [{
            "ticker": "AAPL", "side": "sell", "shares": 5.0,
            "price": 110.0, "value": 550.0,
            "transaction_id": transaction_id, "fill_id": fill_id,
        }],
        "holdings": [],
    }
    monkeypatch.setattr(
        web,
        "_brain_book_module",
        lambda portfolio: type("Brain", (), {"load_decisions": staticmethod(lambda limit: [row])}),
    )
    observed: list[str] = []

    def realized(portfolio_id=None):
        observed.append(portfolio_id)
        return {("2026-08-13", "AAPL"): {
            "realized_pnl": 50.0, "realized_pct": 10.0, "pct_of_position": 0.5,
        }}

    monkeypatch.setattr(trade_history, "sell_realized", realized)
    monkeypatch.setattr(web, "_attach_security_names", lambda rows: None)
    monkeypatch.setattr(web, "_cached_zh", lambda value: None)
    monkeypatch.setattr(registry, "get", lambda portfolio: {"status": "active"})
    monkeypatch.setattr(registry, "is_archived", lambda portfolio: False)

    data = json.loads(web.api_decisions("autonomous").body)
    decision = data["decisions"][0]

    assert observed == ["autonomous"]
    assert decision["execution_evidence_status"] == "receipt_verified"
    assert decision["executed"][0]["realized_pnl"] == 50.0
    assert decision["executed"][0]["pct_of_position"] == 0.5


def test_decision_api_labels_legacy_execution_unverified_even_if_audit_pnl_backfills(monkeypatch):
    from app import web
    from portfolio import registry, trade_history

    row = {
        "asof": "2026-08-12",
        "target_status": "executed",
        "executed": [{"ticker": "AAPL", "side": "sell", "shares": 5.0}],
        "holdings": [],
    }
    monkeypatch.setattr(
        web,
        "_brain_book_module",
        lambda portfolio: type("Brain", (), {"load_decisions": staticmethod(lambda limit: [row])}),
    )
    monkeypatch.setattr(
        trade_history,
        "sell_realized",
        lambda portfolio_id=None: {("2026-08-12", "AAPL"): {"realized_pnl": 999.0}},
    )
    monkeypatch.setattr(web, "_attach_security_names", lambda rows: None)
    monkeypatch.setattr(web, "_cached_zh", lambda value: None)
    monkeypatch.setattr(registry, "get", lambda portfolio: {"status": "active"})
    monkeypatch.setattr(registry, "is_archived", lambda portfolio: False)

    decision = json.loads(web.api_decisions("autonomous").body)["decisions"][0]

    assert decision["execution_evidence_status"] == "legacy_unverified"
    # FIFO audit enrichment remains backward compatible, but the presentation gate prevents this
    # legacy summary from becoming a fill chip or FILLED badge.
    assert decision["executed"][0]["realized_pnl"] == 999.0


def test_valid_projection_is_read_only_and_exactly_portfolio_scoped(
    tmp_path, trades_env, monkeypatch
):
    from portfolio import paper_account, registry, trade_history

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    book = registry.data_dir("autonomous")
    book.mkdir(parents=True)
    (book / "pending_target.json").write_text("sentinel pending bytes", encoding="utf-8")
    (book / "account.json").write_text("sentinel account bytes", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in book.iterdir()}

    trades_env["target"] = _target({"AAPL": 0.10})
    trades_env["target_exists"] = True
    calls: list[tuple[str, str | None]] = []
    history_accounts: list[dict] = []

    def load_target(portfolio_id=None):
        calls.append(("target", portfolio_id))
        return trades_env["target"]

    def load_account(portfolio_id=None, strict=False):
        calls.append(("account", portfolio_id))
        assert strict is True
        return trades_env["account"]

    def forbidden(*args, **kwargs):
        raise AssertionError("GET attempted transaction recovery or portfolio mutation")

    def history(prices, portfolio_id=None, account_state=None):
        assert portfolio_id == "autonomous"
        assert account_state is trades_env["account"]
        history_accounts.append(account_state)
        return []

    monkeypatch.setattr(paper_account, "load_pending_target", load_target)
    monkeypatch.setattr(paper_account, "_load_account_file", load_account)
    monkeypatch.setattr(paper_account, "preflight_pending_target", forbidden)
    monkeypatch.setattr(paper_account, "quarantine_pending_target", forbidden)
    monkeypatch.setattr(paper_account, "recover_paper_transaction", forbidden)
    monkeypatch.setattr(paper_account, "_load_account", forbidden)
    monkeypatch.setattr(trade_history, "history", history)

    data = _response()

    assert data["pending_target"]["status"] == "queued"
    assert calls == [("account", "autonomous"), ("target", "autonomous")]
    assert history_accounts == [trades_env["account"]]
    after = {
        path.name: path.read_bytes()
        for path in book.iterdir()
        if path.name != ".paper_transaction.lock"
    }
    assert after == before
    # Taking a shared serialization lock may materialize the empty lock inode; executable/runtime
    # payloads remain byte-identical and no recovery or quarantine occurs.
    lock = book / ".paper_transaction.lock"
    assert not lock.exists() or lock.read_bytes() == b""
