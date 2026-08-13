"""A queued Brain decision becomes FILLED only through its exact durable receipt."""
from __future__ import annotations

import copy
import importlib
import hashlib
import inspect
import json

import pytest


@pytest.mark.parametrize(
    ("portfolio_id", "module_name", "ticker", "benchmark"),
    [
        ("autonomous", "bot.autonomous", "AAPL", "SPY"),
        ("china", "bot.china", "600519.SS", "000300.SS"),
        ("hk", "bot.hk", "0700.HK", "^HSI"),
    ],
)
def test_receipt_reconciles_original_queued_decision_for_all_brains(
    tmp_path, monkeypatch, portfolio_id, module_name, ticker, benchmark
):
    from bot import settle
    from portfolio import fx, paper_account, registry

    module = importlib.import_module(module_name)
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(module, "_warm_live", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(paper_account, "_current_price", lambda symbol: 100.0)
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda pid, symbols, _open_price_fn=None: (
            {symbol: 100.0 for symbol in symbols},
            {symbol: "test_open" for symbol in symbols},
        ),
    )
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )
    submission = {
        "schema": "mastermind.target_book.v2",
        "holdings": [{
            "ticker": ticker,
            "weight": 0.20,
            "action": "add",
            "action_effective": "add",
            "rationale": "accepted and receipt bound",
        }],
        "summary": "queued target",
    }
    module._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target={ticker: 0.20},
    )
    paper_account.save_pending_target(
        {ticker: 0.20}, "2026-08-12", portfolio_id=portfolio_id,
        decision_snapshot=submission,
    )

    result = settle.settle_open(portfolio_id, "2026-08-13")

    assert result["ok"] is True
    assert result["receipt_acknowledged"] is True
    assert result["decision_reconciliation"]["reconciled"] is True
    rows = [
        json.loads(line)
        for line in (registry.data_dir(portfolio_id) / "decisions.jsonl").read_text().splitlines()
        if line
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["asof"] == row["accepted_asof"] == "2026-08-12"
    assert row["settled_asof"] == "2026-08-13"
    assert row["target_status"] == "executed"
    assert row["executed"][0]["ticker"] == ticker
    assert row["executed"][0]["side"] == "buy"
    assert row["executed"][0]["fill_id"]
    assert row["executed"][0]["transaction_id"] == row["settlement_transaction_id"]
    assert paper_account.pending_settlement_receipts(portfolio_id) == []


def _sign_receipt_fills(receipt):
    from portfolio import paper_account

    unsigned = [
        {key: value for key, value in fill.items()
         if key not in {"fill_id", "transaction_id"}}
        for fill in receipt["fills"]
    ]
    before_positions = copy.deepcopy(receipt.get("account_before_positions") or {})
    after_positions = copy.deepcopy(receipt.get("account_after_positions") or {})
    target_hash = paper_account._target_sha256(receipt["target"])
    receipt["target_sha256"] = target_hash
    if isinstance(receipt.get("decision_snapshot"), dict):
        receipt["decision_snapshot"]["target_sha256"] = target_hash
    queued_asof = str(
        (receipt.get("decision_snapshot") or {}).get("accepted_asof")
        or receipt.get("queued_asof")
        or "2026-08-12"
    )
    receipt["queued_asof"] = queued_asof
    before_cash = 1_000_000.0
    signed_cash = sum(
        float(fill["value"]) if fill["side"] == "sell" else -float(fill["value"])
        for fill in unsigned
    )
    account_before = {
        "inception_date": "2026-08-01",
        "starting_nav": 1_000_000.0,
        "cash": before_cash,
        "positions": before_positions,
        "spy_shares": None,
        "spy_inception_price": None,
    }
    account_after = {
        **copy.deepcopy(account_before),
        "cash": round(before_cash + signed_cash, 10),
        "positions": after_positions,
    }
    pending_payload = {
        "target": copy.deepcopy(receipt["target"]),
        "asof": queued_asof,
        "decision_snapshot": copy.deepcopy(receipt.get("decision_snapshot")),
    }
    followup = {
        "kind": "clear_pending_target",
        "filename": "pending_target.json",
        "before_sha256": receipt.get("pending_target_sha256") or ("b" * 64),
        "pending_payload": pending_payload,
        "settlement_prices": copy.deepcopy(receipt["settlement_prices"]),
        "settlement_price_sources": copy.deepcopy(
            receipt.get("settlement_price_sources") or {}
        ),
    }
    identity = {
        "schema": paper_account.PAPER_TRANSACTION_SCHEMA,
        "portfolio_id": receipt["portfolio_id"],
        "asof": receipt["settlement_asof"],
        "account_before_sha256": paper_account._content_sha256(account_before),
        "account_after": account_after,
        "fills": unsigned,
        "followup": followup,
    }
    transaction_id = paper_account._content_sha256(identity)
    receipt["transaction_id"] = transaction_id
    receipt["pending_target_sha256"] = followup["before_sha256"]
    receipt["transaction_identity"] = identity
    receipt["account_before"] = account_before
    for index, fill in enumerate(receipt["fills"]):
        body = {key: value for key, value in fill.items()
                if key not in {"fill_id", "transaction_id"}}
        fill["transaction_id"] = transaction_id
        fill["fill_id"] = hashlib.sha256(paper_account._canonical_json_bytes({
            "transaction_id": transaction_id,
            "index": index,
            "fill": body,
        })).hexdigest()
    return receipt


def _receipt_for(submission, *, target=None, transaction_id="a" * 64):
    from bot import decision_rows

    target = {"AAPL": 0.20} if target is None else target
    target_hash = decision_rows.target_sha256(target)
    fill = {
        "date": "2026-08-13", "ticker": "AAPL", "side": "buy",
        "shares": 2000.0, "price": 100.0, "value": 200_000.0,
        "transaction_id": transaction_id,
    }
    receipt = {
        "schema": "paper_settlement_receipt.v2",
        "transaction_id": transaction_id,
        "portfolio_id": "autonomous",
        "settlement_asof": "2026-08-13",
        "target_sha256": target_hash,
        "target": target,
        "decision_snapshot": {
            "schema_version": "pending_decision.v1",
            "portfolio_id": "autonomous",
            "accepted_asof": "2026-08-12",
            "target_sha256": target_hash,
            "submission": submission,
            "decision_log_required": True,
        },
        "fills": [fill],
        "account_before_positions": {},
        "account_after_positions": {"AAPL": {"shares": 2000.0, "avg_cost": 100.0}},
        "settlement_prices": {**{ticker: 100.0 for ticker in target}, "SPY": 500.0},
        "settlement_price_sources": {**{ticker: "test_open" for ticker in target},
                                     "SPY": "test_open"},
    }
    return _sign_receipt_fills(receipt)


def _seed_account(paper_account, portfolio_id="autonomous"):
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )


def _persist_receipt(paper_account, receipt, portfolio_id="autonomous"):
    account_path = paper_account._paths(portfolio_id)["account"]
    if not account_path.exists():
        state = copy.deepcopy(receipt["transaction_identity"]["account_after"])
        state["last_paper_transaction_id"] = receipt["transaction_id"]
        paper_account._save_account(state, portfolio_id)
    fills_path = paper_account._paths(portfolio_id)["fills"]
    existing = {
        row.get("fill_id")
        for row in paper_account._load_jsonl(fills_path)
        if isinstance(row, dict)
    }
    for fill in receipt.get("fills") or []:
        if fill.get("fill_id") not in existing:
            paper_account._append_jsonl(fills_path, fill)
    path = paper_account._settlement_receipt_path(
        receipt["transaction_id"], portfolio_id
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return path


def test_receipt_validation_accepts_engine_rounding_for_large_low_price_fill():
    """Independent shares/price/value rounding must not reject the engine's own receipt."""
    from portfolio import paper_account

    receipt = _receipt_for({"holdings": [], "summary": "rounding bound"})
    fill = receipt["fills"][0]
    fill.update({
        "ticker": "AAPL",
        "shares": 810_005.184,
        "price": 1.2346,
        "value": 1_000_000.0,
    })
    receipt["account_after_positions"]["AAPL"]["shares"] = 810_005.184
    _sign_receipt_fills(receipt)

    assert paper_account.validated_settlement_receipt_fills(receipt) == receipt["fills"]


def test_receipt_validation_aggregates_signed_fills_to_account_delta():
    """Multiple rows for one ticker are valid only when their signed sum explains state."""
    from portfolio import paper_account

    receipt = _receipt_for({"holdings": [], "summary": "aggregate signed shares"})
    receipt["account_before_positions"] = {
        "AAPL": {"shares": 10.0, "avg_cost": 90.0}
    }
    receipt["account_after_positions"] = {
        "AAPL": {"shares": 12.0, "avg_cost": 95.0}
    }
    receipt["fills"] = [
        {
            "date": "2026-08-13", "ticker": "AAPL", "side": "buy",
            "shares": 5.0, "price": 100.0, "value": 500.0,
            "transaction_id": receipt["transaction_id"],
        },
        {
            "date": "2026-08-13", "ticker": "AAPL", "side": "sell",
            "shares": 3.0, "price": 100.0, "value": 300.0,
            "transaction_id": receipt["transaction_id"],
        },
    ]
    _sign_receipt_fills(receipt)

    assert paper_account.validated_settlement_receipt_fills(receipt) == receipt["fills"]


def test_changed_and_reidentified_fill_cannot_disagree_with_account_delta():
    """Recomputing the deterministic id cannot bless changed share facts."""
    from portfolio import paper_account

    receipt = _receipt_for({"holdings": [], "summary": "re-id adversary"})
    receipt["fills"][0].update({"shares": 1999.0, "value": 199_900.0})
    _sign_receipt_fills(receipt)

    with pytest.raises(
        paper_account.PaperTransactionConflict,
        match="do not explain account share delta",
    ):
        paper_account.validated_settlement_receipt_fills(receipt)


def test_reidentified_fill_cannot_move_to_another_settlement_date():
    from portfolio import paper_account

    receipt = _receipt_for({"holdings": [], "summary": "date-bound receipt"})
    receipt["fills"][0]["date"] = "2026-08-14"
    _sign_receipt_fills(receipt)

    with pytest.raises(
        paper_account.PaperTransactionConflict,
        match="fill date does not match settlement",
    ):
        paper_account.validated_settlement_receipt_fills(receipt)


@pytest.mark.parametrize(
    ("corruption", "error"),
    [
        ("missing_fill", "fill preimage disagrees"),
        ("unexplained_ticker", "bound preimage fields disagree"),
    ],
)
def test_receipt_rejects_every_unexplained_account_share_delta(corruption, error):
    from portfolio import paper_account

    receipt = _receipt_for({"holdings": [], "summary": "complete delta binding"})
    if corruption == "missing_fill":
        receipt["fills"] = []
    else:
        receipt["account_after_positions"]["MSFT"] = {
            "shares": 7.0, "avg_cost": 400.0,
        }

    with pytest.raises(
        paper_account.PaperTransactionConflict,
        match=error,
    ):
        paper_account.validated_settlement_receipt_fills(receipt)


def test_receipt_share_delta_tolerance_is_persisted_precision_bounded():
    """Accept six-decimal representation drift, but never position-size-relative drift."""
    from portfolio import paper_account

    receipt = _receipt_for({"holdings": [], "summary": "bounded share precision"})
    receipt["account_after_positions"]["AAPL"]["shares"] = 2000.00000049
    _sign_receipt_fills(receipt)
    assert paper_account.validated_settlement_receipt_fills(receipt) == receipt["fills"]

    receipt["account_after_positions"]["AAPL"]["shares"] = 2000.000002
    _sign_receipt_fills(receipt)
    with pytest.raises(
        paper_account.PaperTransactionConflict,
        match="do not explain account share delta",
    ):
        paper_account.validated_settlement_receipt_fills(receipt)


def test_reconciliation_matches_exact_identity_without_overwriting_later_day(
    tmp_path, monkeypatch
):
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    original = {
        "holdings": [{"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}],
        "summary": "original",
    }
    later = {
        "holdings": [{"ticker": "MSFT", "weight": 0.10, "action_effective": "add"}],
        "summary": "later",
    }
    autonomous._append_decision_log(
        "2026-08-12", original, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    autonomous._append_decision_log(
        "2026-08-13", later, [], [], {},
        target_status="queued", effective_target={"MSFT": 0.10},
    )
    receipt = _receipt_for(original)
    derived = [{
        "ticker": "AAPL", "side": "buy", "shares": 2000.0,
        "price": 100.0, "value": 200_000.0, "fill_price_source": "test_open",
    }]

    first = decision_rows.reconcile_settlement("autonomous", receipt, derived)
    second = decision_rows.reconcile_settlement("autonomous", receipt, derived)

    assert first["reconciled"] is True
    assert second["deduplicated"] is True
    rows = autonomous.load_decisions()
    by_day = {row["asof"]: row for row in rows}
    assert by_day["2026-08-12"]["target_status"] == "executed"
    assert by_day["2026-08-13"]["target_status"] == "queued"
    assert by_day["2026-08-13"]["summary"] == "later"


def test_reconciliation_accepts_only_a_complete_deterministic_target_lineage(
    tmp_path, monkeypatch
):
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [{"ticker": "AAPL", "weight": 0.20, "action_effective": "hold"}],
        "summary": "accepted before deterministic de-risk",
    }
    original = {"AAPL": 0.20}
    revised = {"AAPL": 0.10}
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target=original,
    )
    receipt = _receipt_for(submission, target=revised)
    receipt["decision_snapshot"]["target_lineage"] = [{
        "from_target_sha256": decision_rows.target_sha256(original),
        "to_target_sha256": decision_rows.target_sha256(revised),
        "rebound_asof": "2026-08-12",
        "reason": "deterministic_risk_rewrite",
    }]
    receipt["fills"][0].update({"shares": 1000.0, "value": 100_000.0})
    receipt["account_after_positions"]["AAPL"]["shares"] = 1000.0
    _sign_receipt_fills(receipt)

    out = decision_rows.reconcile_settlement(
        "autonomous", receipt,
        [{"ticker": "AAPL", "side": "buy", "shares": 1000.0,
          "price": 100.0, "value": 100_000.0}],
    )

    assert out["reconciled"] is True
    row = autonomous.load_decisions()[0]
    assert row["accepted_target_sha256"] == decision_rows.target_sha256(original)
    assert row["target_sha256"] == decision_rows.target_sha256(revised)
    assert row["target_lineage"] == receipt["decision_snapshot"]["target_lineage"]


def test_zero_fill_receipt_still_transitions_queued_decision_to_no_change(
    tmp_path, monkeypatch
):
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [{"ticker": "AAPL", "weight": 0.20, "action_effective": "hold"}],
        "summary": "carry unchanged",
    }
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    receipt = _receipt_for(submission)
    receipt["fills"] = []
    unchanged = {"AAPL": {"shares": 2000.0, "avg_cost": 100.0}}
    receipt["account_before_positions"] = copy.deepcopy(unchanged)
    receipt["account_after_positions"] = copy.deepcopy(unchanged)
    _sign_receipt_fills(receipt)

    out = decision_rows.reconcile_settlement("autonomous", receipt, [])

    assert out["reconciled"] is True
    row = autonomous.load_decisions()[0]
    assert row["target_status"] == "executed"
    assert row["executed"] == []
    assert row["settlement_fill_ids"] == []


def test_receipt_can_finish_binding_an_already_executed_direct_open_row(
    tmp_path, monkeypatch
):
    """A crash after logging fills but before receipt ack must recover idempotently."""
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [{"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}],
        "summary": "direct open execution",
    }
    autonomous._append_decision_log(
        "2026-08-12", submission,
        [{"ticker": "AAPL", "side": "buy", "shares": 2000.0,
          "price": 100.0, "value": 200_000.0}],
        [], {}, target_status="executed", effective_target={"AAPL": 0.20},
    )
    receipt = _receipt_for(submission)

    first = decision_rows.reconcile_settlement("autonomous", receipt, [])
    second = decision_rows.reconcile_settlement("autonomous", receipt, [])

    assert first["reconciled"] is True
    assert second["deduplicated"] is True
    row = autonomous.load_decisions()[0]
    assert row["target_status"] == "executed"
    assert row["settlement_transaction_id"] == receipt["transaction_id"]
    assert row["executed"][0]["fill_id"] == receipt["fills"][0]["fill_id"]


def test_pre_release_v2_queued_row_is_backfilled_from_exact_effective_target(
    tmp_path, monkeypatch
):
    """The live Aug-12 queue predates the new columns but must settle after deployment."""
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [
            {"ticker": "XOM", "weight": 0.10, "action_effective": "add"},
            {"ticker": "AAPL", "weight": 0.04, "action_effective": "hold"},
        ],
        "summary": "live-compatible queued target",
    }
    target = {"XOM": 0.10, "AAPL": 0.04}
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target=target,
    )
    path = registry.data_dir("autonomous") / "decisions.jsonl"
    legacy = json.loads(path.read_text().splitlines()[0])
    expected_decision_id = legacy["decision_id"]
    for key in ("accepted_asof", "submission_sha256", "target_sha256"):
        legacy.pop(key)
    path.write_text(json.dumps(legacy) + "\n")
    receipt = _receipt_for(submission, target=target)
    receipt["decision_snapshot"].pop("decision_log_required")
    receipt["fills"][0].update({
        "ticker": "XOM", "shares": 1000.0, "value": 100_000.0,
    })
    receipt["account_before_positions"] = {
        "AAPL": {"shares": 400.0, "avg_cost": 100.0}
    }
    receipt["account_after_positions"] = {
        "AAPL": {"shares": 400.0, "avg_cost": 100.0},
        "XOM": {"shares": 1000.0, "avg_cost": 100.0},
    }
    _sign_receipt_fills(receipt)

    out = decision_rows.reconcile_settlement(
        "autonomous", receipt,
        [{"ticker": "XOM", "side": "buy", "shares": 1000.0,
          "price": 100.0, "value": 100_000.0}],
    )

    assert out["reconciled"] is True
    row = autonomous.load_decisions()[0]
    assert row["decision_id"] == expected_decision_id
    assert row["target_sha256"] == decision_rows.target_sha256(target)
    assert set(row["settlement_identity_backfilled"]) == {
        "accepted_asof", "submission_sha256", "target_sha256",
    }


@pytest.mark.parametrize("corruption", ["ambiguous", "wrong_hash"])
def test_reconciliation_fails_closed_without_mutating_ledger(
    tmp_path, monkeypatch, corruption
):
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [{"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}],
        "summary": "queued",
    }
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    path = registry.data_dir("autonomous") / "decisions.jsonl"
    row = json.loads(path.read_text().splitlines()[0])
    if corruption == "ambiguous":
        path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
        before = path.read_bytes()
    else:
        row["target_sha256"] = "f" * 64
        path.write_text(json.dumps(row) + "\n")
        before = path.read_bytes()

    with pytest.raises(decision_rows.DecisionSettlementConflict):
        decision_rows.reconcile_settlement(
            "autonomous",
            _receipt_for(submission),
            [{"ticker": "AAPL", "side": "buy", "shares": 2000.0,
              "price": 100.0, "value": 200_000.0}],
        )

    assert (path.read_bytes() if path.exists() else None) == before


def test_zero_weight_is_not_part_of_executable_target_identity(
    tmp_path, monkeypatch
):
    """The decision row and queue must hash the same canonical executable target."""
    from bot import autonomous, decision_rows
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    raw_target = {"aapl": 0.20, "MSFT": 0.0}
    canonical = paper_account.validate_target_weights(
        raw_target, portfolio_id="autonomous"
    )
    assert canonical == {"AAPL": 0.20}
    canonical_hash = paper_account._target_sha256(canonical)
    assert decision_rows.target_sha256(raw_target) == canonical_hash

    submission = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "one executable name",
    }
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target=raw_target,
    )
    paper_account.save_pending_target(
        raw_target,
        "2026-08-12",
        portfolio_id="autonomous",
        decision_snapshot=submission,
    )

    row = autonomous.load_decisions()[0]
    pending = json.loads(
        paper_account._pending_target_path("autonomous").read_text(encoding="utf-8")
    )
    assert pending["target"] == canonical
    assert row["target_sha256"] == canonical_hash
    assert pending["decision_snapshot"]["target_sha256"] == canonical_hash


def test_accepted_all_cash_target_supersedes_stale_same_day_book(
    tmp_path, monkeypatch
):
    """An empty accepted target is substantive execution intent, not a barren stub."""
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    stale = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "hold"}
        ],
        "summary": "stale invested target",
    }
    all_cash = {"holdings": [], "summary": None}
    autonomous._append_decision_log(
        "2026-08-12", stale, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    autonomous._append_decision_log(
        "2026-08-12", all_cash, [], [], {},
        target_status="queued", effective_target={},
    )

    rows = autonomous.load_decisions()
    assert len(rows) == 1
    assert rows[0]["effective_holdings"] == []
    assert rows[0]["target_sha256"] == decision_rows.target_sha256({})
    assert rows[0]["decision_effective"] is True
    assert decision_rows.is_substantive(rows[0]) is True


def test_accepted_post_submission_brain_error_supersedes_stale_same_day_book(
    tmp_path, monkeypatch
):
    """A provider error after deterministic acceptance cannot demote the accepted target."""
    from bot import autonomous
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    stale = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "hold"}
        ],
        "summary": "stale target",
    }
    accepted = {
        "holdings": [
            {"ticker": "MSFT", "weight": 0.15, "action_effective": "add"}
        ],
        "summary": "accepted before adapter cleanup failed",
    }
    autonomous._append_decision_log(
        "2026-08-12", stale, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    autonomous._append_decision_log(
        "2026-08-12", accepted, [], [],
        {"error": "brain.error after submission was accepted"},
        target_status="queued", effective_target={"MSFT": 0.15},
    )

    rows = autonomous.load_decisions()
    assert len(rows) == 1
    assert rows[0]["summary"] == accepted["summary"]
    assert rows[0]["error"] == "brain.error after submission was accepted"
    assert rows[0]["decision_effective"] is True
    assert rows[0]["effective_holdings"][0]["ticker"] == "MSFT"


def test_direct_open_reconciliation_binds_receipt_fills_before_ack(
    tmp_path, monkeypatch
):
    """Direct-open rows bind immutable receipt fill IDs while the outbox still exists."""
    from bot import autonomous, settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    _seed_account(paper_account)
    submission = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "direct open target",
    }
    paper_account.save_pending_target(
        {"AAPL": 0.20},
        "2026-08-12",
        portfolio_id="autonomous",
        decision_snapshot=submission,
    )
    settled = paper_account.settle_target(
        {"AAPL": 100.0, "SPY": 500.0},
        "2026-08-12",
        portfolio_id="autonomous",
        _price_sources={"AAPL": "polygon_open", "SPY": "polygon_open"},
    )
    assert settled == {"AAPL": 0.20}
    receipt = paper_account.pending_settlement_receipts("autonomous")[0]
    executed = [
        {
            "ticker": "AAPL",
            "side": "buy",
            "shares": receipt["fills"][0]["shares"],
            "price": receipt["fills"][0]["price"],
            "value": receipt["fills"][0]["value"],
            "fill_price_source": "polygon_open",
        }
    ]
    autonomous._append_decision_log(
        "2026-08-12", submission, executed, [], {},
        target_status="executed", effective_target={"AAPL": 0.20},
    )

    reconciled = settle.reconcile_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"], executed
    )

    # Reconciliation itself never acknowledges the outbox.  The caller may ACK only afterward.
    assert reconciled["reconciled"] is True
    still_pending = paper_account.pending_settlement_receipts("autonomous")
    assert [item["transaction_id"] for item in still_pending] == [
        receipt["transaction_id"]
    ]
    row = autonomous.load_decisions()[0]
    assert row["settlement_transaction_id"] == receipt["transaction_id"]
    assert row["executed"][0]["fill_id"] == receipt["fills"][0]["fill_id"]
    assert row["executed"][0]["transaction_id"] == receipt["transaction_id"]
    assert paper_account.acknowledge_settlement_receipt(
        receipt["transaction_id"], "autonomous"
    ) is True
    assert paper_account.pending_settlement_receipts("autonomous") == []


@pytest.mark.parametrize(
    "corruption",
    ["tampered_numeric_fact", "forged_fill_id", "duplicate_fill", "malformed_fact"],
)
def test_receipt_fill_corruption_is_rejected_without_ledger_mutation(
    tmp_path, monkeypatch, corruption
):
    """A deterministic ID never licenses inconsistent, duplicated, or malformed facts."""
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "receipt tamper boundary",
    }
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    path = registry.data_dir("autonomous") / "decisions.jsonl"
    before = path.read_bytes()
    receipt = _receipt_for(submission)
    if corruption == "tampered_numeric_fact":
        # Mutation after signing proves the ID covers every numeric fact.
        receipt["fills"][0]["price"] = 101.0
    elif corruption == "forged_fill_id":
        receipt["fills"][0]["fill_id"] = "b" * 64
    elif corruption == "duplicate_fill":
        receipt["fills"].append(copy.deepcopy(receipt["fills"][0]))
    else:
        # Even a correctly re-signed record cannot smuggle a boolean as a share count.
        receipt["fills"][0]["shares"] = True
        receipt["fills"][0]["value"] = 100.0
        _sign_receipt_fills(receipt)

    with pytest.raises(
        decision_rows.DecisionSettlementConflict,
        match="fill lineage is invalid",
    ):
        decision_rows.reconcile_settlement("autonomous", receipt, [])

    assert path.read_bytes() == before


def test_more_than_twenty_target_rewrites_compact_without_breaking_lineage(
    tmp_path, monkeypatch
):
    """Bounded queue metadata still proves the original accepted target through final settle."""
    from bot import autonomous, decision_rows
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "hold"}
        ],
        "summary": "accepted before repeated deterministic de-risking",
    }
    original = {"AAPL": 0.20}
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target=original,
    )
    snapshot = submission
    final_target = original
    for index in range(26):
        final_target = {"AAPL": round(0.20 - (index * 0.004), 6)}
        paper_account.save_pending_target(
            final_target,
            "2026-08-12",
            portfolio_id="autonomous",
            decision_snapshot=snapshot,
            _after_save_locked=(lambda: None) if index == 0 else None,
        )
        payload = json.loads(
            paper_account._pending_target_path("autonomous").read_text(
                encoding="utf-8"
            )
        )
        snapshot = payload["decision_snapshot"]

    lineage = snapshot["target_lineage"]
    assert len(lineage) <= 20
    current_hash = decision_rows.target_sha256(original)
    for transition in lineage:
        assert transition["from_target_sha256"] == current_hash
        current_hash = transition["to_target_sha256"]
    assert current_hash == decision_rows.target_sha256(final_target)
    assert snapshot["accepted_target_sha256"] == decision_rows.target_sha256(original)
    assert snapshot["decision_log_required"] is True

    receipt = _receipt_for(submission, target=final_target)
    receipt["decision_snapshot"] = snapshot
    shares = round(final_target["AAPL"] * 1_000_000.0 / 100.0, 4)
    receipt["fills"][0].update(
        {"shares": shares, "price": 100.0, "value": shares * 100.0}
    )
    receipt["account_after_positions"]["AAPL"]["shares"] = shares
    _sign_receipt_fills(receipt)

    out = decision_rows.reconcile_settlement("autonomous", receipt, [])

    assert out["reconciled"] is True
    row = autonomous.load_decisions()[0]
    assert row["accepted_target_sha256"] == decision_rows.target_sha256(original)
    assert row["target_sha256"] == decision_rows.target_sha256(final_target)
    assert row["target_lineage"] == lineage


def test_receipt_retry_uses_captured_prices_and_original_settlement_date(
    tmp_path, monkeypatch
):
    """Recovery must not refetch quotes or relabel an older committed settlement as today."""
    from bot import autonomous, settle
    from portfolio import autonomous_migration, paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "old committed receipt",
    }
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    receipt = _receipt_for(submission)
    receipt["settlement_price_sources"] = {
        "AAPL": "captured_polygon_open",
        "SPY": "captured_polygon_open",
    }
    _sign_receipt_fills(receipt)
    _persist_receipt(paper_account, receipt)

    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(
        autonomous_migration,
        "persist_settlement_link",
        lambda row: {"ok": True, "applicable": False},
    )
    position_calls = []
    fail_once = {"value": True}

    def position_update(rows, asof, *, portfolio_id=None):
        position_calls.append((copy.deepcopy(rows), asof, portfolio_id))
        if fail_once["value"]:
            fail_once["value"] = False
            raise OSError("retry this projection")

    mark_calls = []
    republish_calls = []
    monkeypatch.setattr(position_log, "update", position_update)
    monkeypatch.setattr(
        paper_account,
        "mark",
        lambda prices, asof, portfolio_id=None, mark_source=None,
        _settlement_receipt_id=None: mark_calls.append(
            (dict(prices), asof, portfolio_id, mark_source, _settlement_receipt_id)
        ),
    )
    monkeypatch.setattr(
        settle,
        "_republish",
        lambda pid, asof, submission=None, settlement_prices=None: (
            republish_calls.append(
                (pid, asof, submission, dict(settlement_prices or {}))
            ),
            {"ok": True},
        )[1],
    )

    def no_quote_refetch(_ticker):
        raise AssertionError("receipt recovery attempted a quote refetch")

    first = settle.settle_open(
        "autonomous", "2026-09-01", _open_price_fn=no_quote_refetch
    )
    second = settle.settle_open(
        "autonomous", "2026-09-02", _open_price_fn=no_quote_refetch
    )

    assert first["skipped"] == "settlement_finalization_pending"
    assert first["receipt_retained"] is True
    assert second["ok"] is True
    assert second["receipt_acknowledged"] is True
    assert second["executed"][0]["fill_price_source"] == "captured_polygon_open"
    assert {asof for _, asof, _ in position_calls} == {"2026-08-13"}
    assert {asof for _, asof, _, _, _ in mark_calls} == {"2026-08-13"}
    assert {asof for _, asof, _, _ in republish_calls} == {"2026-08-13"}
    assert all(
        prices == {"AAPL": 100.0, "SPY": 500.0}
        for _, _, _, prices in republish_calls
    )
    assert all(call[0] == {"AAPL": 100.0, "SPY": 500.0} for call in mark_calls)
    assert all(call[3] == "settlement_receipt" for call in mark_calls)
    assert all(call[4] == receipt["transaction_id"] for call in mark_calls)
    assert paper_account.pending_settlement_receipts("autonomous") == []


def test_consumed_queue_without_receipt_never_infers_another_callers_fills(
    tmp_path, monkeypatch
):
    """A vanished queue without its durable receipt is a no-fill result, even if state moved."""
    from bot import autonomous, settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    _seed_account(paper_account)
    submission = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "concurrent queue",
    }
    autonomous._append_decision_log(
        "2026-08-12", submission, [], [], {},
        target_status="queued", effective_target={"AAPL": 0.20},
    )
    paper_account.save_pending_target(
        {"AAPL": 0.20},
        "2026-08-12",
        portfolio_id="autonomous",
        decision_snapshot=submission,
    )
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(settle, "_held", lambda pid: [])
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda pid, symbols, _open_price_fn=None: (
            {symbol: 100.0 for symbol in symbols},
            {symbol: "captured_open" for symbol in symbols},
        ),
    )

    def consumed_elsewhere(*args, **kwargs):
        paper_account._pending_target_path("autonomous").unlink(missing_ok=True)
        moved = paper_account._load_account_file("autonomous", strict=True)
        moved["positions"] = {"AAPL": {"shares": 2000.0, "avg_cost": 100.0}}
        moved["cash"] = 800_000.0
        paper_account._save_account(moved, "autonomous")
        return None

    monkeypatch.setattr(paper_account, "settle_target", consumed_elsewhere)
    monkeypatch.setattr(
        settle,
        "_diff_trades",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("inferred fills from another caller's state")
        ),
    )

    result = settle.settle_open("autonomous", "2026-08-13")

    assert result == {"ok": False, "skipped": "queue_consumed_concurrently"}
    assert autonomous.load_decisions()[0]["target_status"] == "queued"


def test_manual_legacy_receipt_without_required_decision_row_is_nonblocking(
    tmp_path, monkeypatch
):
    """Operator queues predating decision projection settle without guessing a ledger row."""
    from bot import autonomous, decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    unrelated = {
        "holdings": [
            {"ticker": "MSFT", "weight": 0.10, "action_effective": "add"}
        ],
        "summary": "unrelated prior decision",
    }
    autonomous._append_decision_log(
        "2026-08-11", unrelated, [], [], {},
        target_status="queued", effective_target={"MSFT": 0.10},
    )
    path = registry.data_dir("autonomous") / "decisions.jsonl"
    before = path.read_bytes()
    manual = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "manual legacy queue",
    }
    receipt = _receipt_for(manual)
    receipt["decision_snapshot"].pop("decision_log_required")

    out = decision_rows.reconcile_settlement("autonomous", receipt, [])

    assert out["ok"] is True
    assert out["reconciled"] is False
    assert out["applicable"] is False
    assert out["reason"] == "legacy_snapshot_without_queued_decision_row"
    assert path.read_bytes() == before


def test_required_decision_ledger_missing_retains_receipt(tmp_path, monkeypatch):
    """A modern queue must never downgrade missing decision truth to legacy compatibility."""
    from bot import decision_rows
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "required ledger row",
    })

    with pytest.raises(
        decision_rows.DecisionSettlementConflict,
        match="required queued decision ledger is missing",
    ):
        decision_rows.reconcile_settlement("autonomous", receipt, [])


def test_required_queue_without_durable_decision_row_never_mutates_account_or_fills(
    tmp_path, monkeypatch
):
    """A crash after queue replace but before its callback row is fail-closed pre-trade."""
    from bot import settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    _seed_account(paper_account)
    paper_account.save_pending_target(
        {"AAPL": 0.20},
        "2026-08-12",
        portfolio_id="autonomous",
        decision_snapshot={
            "holdings": [
                {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
            ],
            "summary": "crash-window queue",
        },
        _after_save_locked=lambda: None,
    )
    account_path = registry.data_dir("autonomous") / "account.json"
    before = account_path.read_bytes()
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda *args, **kwargs: (
            {"AAPL": 100.0, "SPY": 500.0},
            {"AAPL": "test_open", "SPY": "test_open"},
        ),
    )

    out = settle.settle_open("autonomous", "2026-08-13")

    assert out["ok"] is False
    assert "required queued decision projection is unavailable" in out["error"]
    assert account_path.read_bytes() == before
    assert not (registry.data_dir("autonomous") / "fills.jsonl").exists()
    assert paper_account.pending_target_file_exists("autonomous") is True


def test_direct_zero_fill_receipt_projects_every_durable_surface_before_ack(
    tmp_path, monkeypatch
):
    """An unchanged book still needs a position-log projection before its receipt can vanish."""
    from bot import decision_rows, settle
    from portfolio import autonomous_migration, paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    submission = {
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "hold"}
        ],
        "summary": "direct open no change",
    }
    receipt = _receipt_for(submission)
    receipt["fills"] = []
    unchanged = {"AAPL": {"shares": 2000.0, "avg_cost": 100.0}}
    receipt["account_before_positions"] = copy.deepcopy(unchanged)
    receipt["account_after_positions"] = copy.deepcopy(unchanged)
    _sign_receipt_fills(receipt)
    _persist_receipt(paper_account, receipt)

    events = []
    projected = []
    monkeypatch.setattr(
        autonomous_migration,
        "persist_settlement_link",
        lambda row: {"ok": True, "applicable": False},
    )

    def project(rows, asof, *, portfolio_id=None):
        events.append("position_log")
        projected.append((copy.deepcopy(rows), asof, portfolio_id))

    monkeypatch.setattr(position_log, "update", project)
    monkeypatch.setattr(
        paper_account,
        "mark",
        lambda *a, **k: events.append("mark"),
    )
    monkeypatch.setattr(
        settle,
        "_republish",
        lambda pid, asof, submission=None, settlement_prices=None: (
            events.append("publish_and_learning"),
            {"ok": True},
        )[1],
    )
    monkeypatch.setattr(
        decision_rows,
        "reconcile_settlement",
        lambda *a, **k: (events.append("decision_reconcile"), {"ok": True})[1],
    )
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("direct finalizer refetched live quotes")
        ),
    )
    original_ack = paper_account.acknowledge_settlement_receipt

    def acknowledge(transaction_id, portfolio_id):
        events.append("ack")
        return original_ack(transaction_id, portfolio_id)

    monkeypatch.setattr(paper_account, "acknowledge_settlement_receipt", acknowledge)

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is True
    assert out["receipt_acknowledged"] is True
    assert out["executed"] == []
    assert events == [
        "position_log", "mark", "publish_and_learning", "decision_reconcile", "ack"
    ]
    assert projected == [([{
        "ticker": "AAPL",
        "sleeve": "brain",
        "weight": 0.1667,
        "entry_price": 100.0,
    }], "2026-08-13", "autonomous")]
    assert paper_account.pending_settlement_receipts("autonomous") == []


def test_zero_fill_target_does_not_create_phantom_position_ledger_holding(
    tmp_path, monkeypatch
):
    """A target row is intent; only receipt-bound account-after lots may remain open."""
    from bot import settle
    from portfolio import paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for(
        {"holdings": [{"ticker": "AAPL", "weight": 0.20}], "summary": "not filled"}
    )
    receipt["decision_snapshot"] = None
    receipt["fills"] = []
    receipt["account_before_positions"] = {}
    receipt["account_after_positions"] = {}
    _sign_receipt_fills(receipt)
    _persist_receipt(paper_account, receipt)
    monkeypatch.setattr(paper_account, "mark", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        settle,
        "_republish",
        lambda *args, **kwargs: {"ok": True},
    )

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is True
    assert out["receipt_acknowledged"] is True
    assert out["executed"] == []
    assert position_log.open_positions("autonomous") == []
    assert paper_account.pending_settlement_receipts("autonomous") == []


@pytest.mark.parametrize(
    ("failure_stage", "error_fragment"),
    [
        ("position_log", "position_log:"),
        ("mark", "mark:"),
        ("publish_or_learning", "republish:"),
        ("decision_reconcile", "decision_reconciliation:"),
    ],
)
def test_direct_receipt_ack_is_gated_by_every_projection(
    tmp_path, monkeypatch, failure_stage, error_fragment
):
    """No projection failure may be swallowed on the direct runner's ACK path."""
    from bot import decision_rows, settle
    from portfolio import autonomous_migration, paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "all projections required",
    })
    _persist_receipt(paper_account, receipt)
    monkeypatch.setattr(
        autonomous_migration,
        "persist_settlement_link",
        lambda row: {"ok": True, "applicable": False},
    )

    def maybe_raise(stage):
        if failure_stage == stage:
            raise OSError(f"{stage} unavailable")

    monkeypatch.setattr(
        position_log,
        "update",
        lambda *a, **k: maybe_raise("position_log"),
    )
    monkeypatch.setattr(
        paper_account,
        "mark",
        lambda *a, **k: maybe_raise("mark"),
    )

    def republish(*args, **kwargs):
        if failure_stage == "publish_or_learning":
            return {"ok": False, "error": "learning_not_durable"}
        return {"ok": True}

    monkeypatch.setattr(settle, "_republish", republish)

    def reconcile(*args, **kwargs):
        if failure_stage == "decision_reconcile":
            return {"ok": False, "error": "ledger unavailable"}
        return {"ok": True}

    monkeypatch.setattr(decision_rows, "reconcile_settlement", reconcile)
    monkeypatch.setattr(
        paper_account,
        "acknowledge_settlement_receipt",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("receipt ACK crossed a failed projection")
        ),
    )

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is False
    assert out["receipt_retained"] is True
    assert any(error_fragment in error for error in out["finalization_errors"])
    assert [r["transaction_id"] for r in paper_account.pending_settlement_receipts(
        "autonomous"
    )] == [receipt["transaction_id"]]


def test_direct_receipt_retry_is_exact_and_idempotent_after_projection_failure(
    tmp_path, monkeypatch
):
    from bot import decision_rows, settle
    from portfolio import autonomous_migration, paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [
            {"ticker": "AAPL", "weight": 0.20, "action_effective": "add"}
        ],
        "summary": "retry exact receipt",
    })
    _persist_receipt(paper_account, receipt)
    monkeypatch.setattr(
        autonomous_migration,
        "persist_settlement_link",
        lambda row: {"ok": True, "applicable": False},
    )
    calls = {"position": 0, "ack": 0}

    def position(*args, **kwargs):
        calls["position"] += 1
        if calls["position"] == 1:
            raise OSError("transient ledger outage")

    monkeypatch.setattr(position_log, "update", position)
    monkeypatch.setattr(paper_account, "mark", lambda *a, **k: None)
    monkeypatch.setattr(settle, "_republish", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(
        decision_rows, "reconcile_settlement", lambda *a, **k: {"ok": True}
    )
    original_ack = paper_account.acknowledge_settlement_receipt

    def acknowledge(transaction_id, portfolio_id):
        calls["ack"] += 1
        return original_ack(transaction_id, portfolio_id)

    monkeypatch.setattr(paper_account, "acknowledge_settlement_receipt", acknowledge)

    first = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )
    second = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert first["ok"] is False and first["receipt_retained"] is True
    assert second["ok"] is True and second["receipt_acknowledged"] is True
    assert calls == {"position": 2, "ack": 1}
    assert paper_account.pending_settlement_receipts("autonomous") == []


@pytest.mark.parametrize(
    ("module_name", "entrypoint"),
    [
        ("bot.autonomous", "run_autonomous"),
        ("bot.china", "run_china"),
        ("bot.hk", "run_hk"),
    ],
)
def test_every_direct_brain_routes_ack_through_shared_receipt_finalizer(
    module_name, entrypoint
):
    source = inspect.getsource(getattr(importlib.import_module(module_name), entrypoint))

    assert "finalize_direct_settlement_receipt" in source
    assert "acknowledge_settlement_receipt" not in source
    assert "position_log.update" not in source
    assert "publish_deferred_to_settlement_receipt" in source
    assert "mark_deferred_to_settlement_receipt" in source
    assert 'if "executed" in ' in source


def test_finalizer_rejects_captured_price_that_contradicts_immutable_fill(
    tmp_path, monkeypatch
):
    from bot import settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [{"ticker": "AAPL", "weight": 0.20}],
        "summary": "tampered settlement mark",
    })
    receipt["settlement_prices"]["AAPL"] = 101.0
    _sign_receipt_fills(receipt)
    _persist_receipt(paper_account, receipt)

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is False
    assert out["receipt_retained"] is True
    assert "price contradicts fill" in out["finalization_errors"][0]


def test_finalizer_rejects_account_drift_before_any_projection(tmp_path, monkeypatch):
    from bot import settle
    from portfolio import paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [{"ticker": "AAPL", "weight": 0.20}],
        "summary": "account drift guard",
    })
    _persist_receipt(paper_account, receipt)
    state = paper_account._load_account_file("autonomous", strict=True)
    state["positions"]["AAPL"]["shares"] += 1.0
    paper_account._save_account(state, "autonomous")
    monkeypatch.setattr(
        position_log,
        "update",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("projection crossed account drift guard")
        ),
    )

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is False
    assert out["finalization_errors"] == ["account_state_drifted_after_settlement"]
    assert out["receipt_retained"] is True


def test_finalizer_rejects_cash_drift_and_cash_yield_waits_for_receipt(
    tmp_path, monkeypatch
):
    from bot import settle
    from portfolio import paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [{"ticker": "AAPL", "weight": 0.20}],
        "summary": "cash-bound receipt",
    })
    _persist_receipt(paper_account, receipt)
    state = paper_account._load_account_file("autonomous", strict=True)
    cash_before = state["cash"]
    assert paper_account.accrue_cash_yield(
        "2026-08-14", portfolio_id="autonomous", annual_rate=0.10
    ) == round(cash_before, 2)
    assert paper_account._load_account_file("autonomous", strict=True)["cash"] == cash_before

    state["cash"] += 1.0
    paper_account._save_account(state, "autonomous")
    monkeypatch.setattr(
        position_log,
        "update",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("projection crossed cash drift guard")
        ),
    )

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is False
    assert out["finalization_errors"] == ["account_state_drifted_after_settlement"]
    assert out["receipt_retained"] is True


def test_zero_fill_receipt_mark_tamper_is_transaction_detected(tmp_path, monkeypatch):
    from bot import settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [{"ticker": "AAPL", "weight": 0.20}],
        "summary": "zero-fill mark binding",
    })
    receipt["fills"] = []
    unchanged = {"AAPL": {"shares": 2000.0, "avg_cost": 100.0}}
    receipt["account_before_positions"] = copy.deepcopy(unchanged)
    receipt["account_after_positions"] = copy.deepcopy(unchanged)
    _sign_receipt_fills(receipt)
    receipt["settlement_prices"]["AAPL"] = 999.0
    _persist_receipt(paper_account, receipt)

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is False
    assert out["receipt_retained"] is True
    assert "bound preimage fields disagree" in out["finalization_errors"][0]


def test_receipt_cannot_ack_when_fill_is_missing_from_trade_history(tmp_path, monkeypatch):
    from bot import settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [{"ticker": "AAPL", "weight": 0.20}],
        "summary": "trade-history binding",
    })
    _persist_receipt(paper_account, receipt)
    paper_account._durable_unlink(paper_account._paths("autonomous")["fills"])

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is False
    assert out["receipt_retained"] is True
    assert "absent from trade history" in out["finalization_errors"][0]


@pytest.mark.parametrize(
    ("portfolio_id", "ticker", "benchmark"),
    [
        ("autonomous", "AAPL", "SPY"),
        ("china", "600519.SS", "000300.SS"),
        ("hk", "0700.HK", "^HSI"),
    ],
)
def test_low_level_settlement_requires_benchmark_before_numeric_mutation(
    tmp_path, monkeypatch, portfolio_id, ticker, benchmark
):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    _seed_account(paper_account, portfolio_id)
    paper_account.save_pending_target(
        {ticker: 0.20}, "2026-08-12", portfolio_id=portfolio_id
    )
    account_path = paper_account._paths(portfolio_id)["account"]
    before = account_path.read_bytes()

    with pytest.raises(paper_account.UnpriceableExitPrices) as stopped:
        paper_account.settle_target(
            {ticker: 100.0}, "2026-08-13", portfolio_id=portfolio_id
        )

    assert benchmark in stopped.value.tickers
    assert account_path.read_bytes() == before
    assert paper_account.pending_target_file_exists(portfolio_id) is True
    assert not paper_account._paths(portfolio_id)["fills"].exists()


def test_invalid_settlement_date_is_rejected_before_queue_or_account_mutation(
    tmp_path, monkeypatch
):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    _seed_account(paper_account)
    paper_account.save_pending_target({}, "2026-08-12", portfolio_id="autonomous")
    account_path = paper_account._paths("autonomous")["account"]
    pending_path = paper_account._pending_target_path("autonomous")
    account_before = account_path.read_bytes()
    pending_before = pending_path.read_bytes()

    with pytest.raises(
        paper_account.PaperTransactionConflict,
        match="settlement asof is not a canonical ISO date",
    ):
        paper_account.settle_target(
            {"SPY": 500.0}, "not-a-date", portfolio_id="autonomous"
        )

    assert account_path.read_bytes() == account_before
    assert pending_path.read_bytes() == pending_before
    assert not paper_account._transaction_path("autonomous").exists()
    assert paper_account.pending_settlement_receipts("autonomous") == []


def test_tiny_full_exit_remains_positive_and_receipt_readable(tmp_path, monkeypatch):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1.0,
            "cash": 0.0,
            "positions": {"AAPL": {"shares": 0.000001, "avg_cost": 1.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    paper_account.save_pending_target({}, "2026-08-12", portfolio_id="autonomous")

    assert paper_account.settle_target(
        {"AAPL": 1.0, "SPY": 500.0},
        "2026-08-13",
        portfolio_id="autonomous",
    ) == {}

    receipt = paper_account.pending_settlement_receipts("autonomous")[0]
    assert receipt["fills"][0]["shares"] == 0.000001
    assert receipt["fills"][0]["value"] == 0.000001
    assert receipt["fills"][0]["value"] > 0.0
    assert paper_account.settlement_receipt_fills_are_durable(
        receipt, "autonomous"
    ) is True


def test_unfinalized_receipt_fences_later_numeric_paper_mutation(tmp_path, monkeypatch):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({
        "holdings": [{"ticker": "AAPL", "weight": 0.20}],
        "summary": "receipt owns account state",
    })
    _persist_receipt(paper_account, receipt)
    before = paper_account._paths("autonomous")["account"].read_bytes()

    with pytest.raises(
        paper_account.PaperTransactionConflict,
        match="unfinalized settlement receipt",
    ):
        paper_account.execute_fill(
            "MSFT",
            "buy",
            shares=10,
            price=100.0,
            asof="2026-08-14",
            portfolio_id="autonomous",
        )

    assert paper_account._paths("autonomous")["account"].read_bytes() == before


def test_legacy_receipt_without_hash_bound_submission_publishes_receipt_only_truth(
    tmp_path, monkeypatch
):
    from bot import settle
    from portfolio import paper_account, position_log, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({"holdings": [], "summary": "discarded scratch"})
    receipt["decision_snapshot"] = None
    _sign_receipt_fills(receipt)
    _persist_receipt(paper_account, receipt)
    monkeypatch.setattr(position_log, "update", lambda *args, **kwargs: None)
    monkeypatch.setattr(paper_account, "mark", lambda *args, **kwargs: None)
    publications = []
    monkeypatch.setattr(
        settle,
        "_republish",
        lambda pid, asof, submission=None, settlement_prices=None: (
            publications.append(copy.deepcopy(submission)),
            {"ok": True},
        )[1],
    )

    out = settle.finalize_direct_settlement_receipt(
        "autonomous", receipt["transaction_id"]
    )

    assert out["ok"] is True
    assert out["receipt_acknowledged"] is True
    assert publications[0]["receipt_only_projection"] is True
    assert publications[0]["settlement_transaction_id"] == receipt["transaction_id"]
    assert "original PM memo was not captured" in publications[0]["summary"]
    assert not paper_account._settlement_receipt_path(
        receipt["transaction_id"], "autonomous"
    ).exists()


def test_zero_fill_receipt_without_exact_settlement_date_is_retained(
    tmp_path, monkeypatch
):
    from bot import settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    receipt = _receipt_for({"holdings": [], "summary": "missing date"})
    receipt["fills"] = []
    receipt["account_before_positions"] = copy.deepcopy(
        receipt["account_after_positions"]
    )
    receipt.pop("settlement_asof")
    path = _persist_receipt(paper_account, receipt)

    out = settle._finalize_settlement_receipt(
        "autonomous", receipt, recovered=True
    )

    assert out["ok"] is False
    assert out["finalization_errors"] == ["receipt_invalid_settlement_date_evidence"]
    assert path.exists()
