"""Durable receipt inspection must not turn plausible IDs into verified evidence."""
from __future__ import annotations

import copy
import importlib
import json

import pytest

BOOKS = {
    "autonomous": ("AAPL", "SPY", "USD", "bot.autonomous"),
    "china": ("600519.SS", "000300.SS", "CNY", "bot.china"),
    "hk": ("0700.HK", "^HSI", "HKD", "bot.hk"),
}


def _fixture_capture(prices, sources, currency, observations=None):
    """Synthetic v1 wire sample; actual producer/decoder is a composition gate."""
    quotes = {}
    for ticker, price in sorted(prices.items()):
        observation = {
            "schema": "mastermind.price_read.v1", "ticker": ticker,
            "stage": "decision_input", "source": sources[ticker], "price": price,
            "currency": currency, "read_status": "returned", "upstream": None,
            "upstream_status": "unavailable", "upstream_reason": "not_captured",
            "source_bar_label": None, "source_bar_label_kind": None,
            "source_text_sha256": None, "attempts": [],
            "market_observed_at": None, "execution_qualification": "not_checked",
        } if observations is None else copy.deepcopy(observations[ticker])
        quotes[ticker] = {
            "price": price, "source": sources[ticker], "binding_status": "matched",
            "reason": None, "observation": observation,
        }
    return {
        "schema": "mastermind.settlement_price_evidence.v1", "currency": currency,
        "quotes": quotes, "omitted_quote_count": 0,
        "market_observed_at": None, "execution_qualification": "not_checked",
    }


def _fixture_validate_capture(prices, sources, currency, captured):
    """Synthetic decoder seam; actual owner validation is a composition gate."""
    rebuilt = _fixture_capture(prices, sources, currency, {
        ticker: quote.get("observation") for ticker, quote in captured["quotes"].items()
    })
    if rebuilt != captured:
        raise ValueError("synthetic captured binding mismatch")
    return rebuilt


@pytest.fixture(params=[(book, weight) for book in BOOKS for weight in (0.20, 1e-9)])
def receipt_case(request, tmp_path, monkeypatch):
    from bot import settle, decision_rows
    from portfolio import paper_account as paper, registry

    book, weight, *capture_options = request.param
    capture_kind = capture_options[0] if capture_options else "captured"
    ticker, benchmark, currency, module_name = BOOKS[book]
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    target = {ticker: weight}
    prices = {ticker: 100.0, benchmark: 500.0}
    sources = {symbol: "decision_mark" for symbol in prices}
    paper._save_account({
        "inception_date": "2026-08-01", "starting_nav": 1_000_000.0,
        "cash": 1_000_000.0, "positions": {}, "spy_shares": None, "spy_inception_price": None,
    }, book)
    submission = {
        "schema": "mastermind.target_book.v2",
        "holdings": [{
            "ticker": ticker, "weight": weight, "action": "add",
            "action_effective": "add", "rationale": "original receipt-bound inspection fixture",
        }],
        "summary": "原始投资决策 — preserved Unicode evidence",
    }
    from datetime import datetime, timezone
    class DecisionClock(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    decision_module = importlib.import_module(module_name)
    monkeypatch.setattr(decision_module, "datetime", DecisionClock)
    decision_module._append_decision_log(
        "2026-08-12", submission, [], [], {}, target_status="queued", effective_target=target,
    )
    paper.save_pending_target(target, "2026-08-12", portfolio_id=book, decision_snapshot=submission)
    followup = paper._pending_clear_transition(book, prices=prices, price_sources=sources)
    if capture_kind == "captured":
        followup["settlement_price_evidence"] = _fixture_capture(prices, sources, currency)
    elif capture_kind == "capture_failed":
        followup["settlement_price_evidence"] = {
            "schema": "mastermind.settlement_price_evidence.v1", "currency": None,
            "quotes": {}, "omitted_quote_count": len(prices), "capture_error": "snapshot_failed",
            "market_observed_at": None, "execution_qualification": "not_checked",
        }
    elif capture_kind == "future_schema":
        followup["settlement_price_evidence"] = {"schema": "mastermind.settlement_price_evidence.v9"}
    # The wire sample joins the actual existing transaction owner, not a hand-built
    # account/receipt. The published capture/retention owners are tested in composition.
    paper.rebalance(target, prices, "2026-08-13", portfolio_id=book, _followup=followup)
    receipt, = paper.pending_settlement_receipts(book)
    active = paper._settlement_receipt_path(receipt["transaction_id"], book)
    archive = active.parent / "acknowledged" / active.name
    archive.parent.mkdir()
    raw = active.read_bytes()
    archive.write_bytes(raw)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(settle, "_republish", lambda *a, **k: {"ok": True})
    assert settle.settle_open(book, "2026-08-13")["ok"] is True
    rows = [json.loads(line) for line in (registry.data_dir(book) / "decisions.jsonl").read_text().splitlines() if line]
    row, = [r for r in rows if r.get("settlement_transaction_id") == receipt["transaction_id"]]

    def forbidden(*args, **kwargs):
        raise AssertionError("price inspection must not recover, price or write an account")

    for name in ("_load_account", "_save_account", "_current_price", "recover_paper_transaction", "rebalance"):
        monkeypatch.setattr(paper, name, forbidden)
    return {
        "book": book, "weight": weight, "currency": currency, "prices": prices, "capture_kind": capture_kind,
        "row": row, "receipt": receipt, "raw": raw, "active": active, "archive": archive,
        "base_dir": registry.data_dir(book), "validator": paper.validated_settlement_receipt_prices,
        "fingerprint": decision_rows._canonical_sha256,
    }


def _inspect(case, **kwargs):
    from app.settlement_price_read import read_settlement_price_evidence

    return read_settlement_price_evidence(
        case["book"], kwargs.pop("decision", case["row"]),
        base_dir=case["base_dir"], currency=case["currency"],
        validate_receipt=kwargs.pop("validate_receipt", case["validator"]),
        fingerprint_receipt=case["fingerprint"],
        validate_capture=kwargs.pop("validate_capture", _fixture_validate_capture),
        **kwargs,
    )


def _file_bytes(base):
    return {str(path.relative_to(base)): path.read_bytes() for path in base.rglob("*") if path.is_file()}


def test_real_receipt_linkage_is_inspected_without_writes_and_zero_fills_remain_valid(receipt_case):
    case = receipt_case
    before = _file_bytes(case["base_dir"])
    result = _inspect(case)

    assert result["status"] == "available", result
    assert result["receipt_linkage"] == "matched"
    assert result["context_status"] == "available"
    assert result["receipt_location"] == "acknowledged"
    assert result["fill_count"] == (1 if case["weight"] == 0.20 else 0)
    assert result["selected_price_count"] == len(case["prices"])
    assert result["execution_qualification"] == "not_checked"
    assert _file_bytes(case["base_dir"]) == before


def test_valid_looking_nonexistent_receipt_id_cannot_borrow_another_saved_receipt(receipt_case):
    case = receipt_case
    row = copy.deepcopy(case["row"])
    row["settlement_transaction_id"] = "d" * 64
    for fill in row["executed"]:
        fill["transaction_id"] = row["settlement_transaction_id"]
    before = _file_bytes(case["base_dir"])
    result = _inspect(case, decision=row)

    assert result["status"] == "unavailable"
    assert result["reason"] == "receipt_missing"
    assert result["price_context"] is None
    assert result["fill_count"] is None
    assert _file_bytes(case["base_dir"]) == before


def test_present_active_receipt_remains_provisional_even_with_identical_retained_copy(receipt_case):
    case = receipt_case
    case["active"].write_bytes(case["raw"])
    before = _file_bytes(case["base_dir"])
    result = _inspect(case)

    assert result["status"] == "provisional", result
    assert result["reason"] == "active_receipt_still_present"
    assert result["receipt_location"] == "both"
    assert result["receipt_linkage"] == "matched"
    assert result["execution_qualification"] == "not_checked"
    assert _file_bytes(case["base_dir"]) == before


def test_decision_receipt_fingerprint_keeps_its_original_unicode_convention(receipt_case):
    from bot import decision_rows
    from portfolio import paper_account

    case = receipt_case
    receipt = case["receipt"]
    assert case["row"]["settlement_receipt_sha256"] == decision_rows._canonical_sha256(receipt)
    assert decision_rows._canonical_sha256(receipt) != paper_account._content_sha256(receipt)
    assert receipt["transaction_id"] == paper_account._content_sha256(receipt["transaction_identity"])
    assert _inspect(case)["receipt_linkage"] == "matched"


@pytest.mark.parametrize("variant", ["reference_unchanged", "reference_updated"])
def test_receipt_edit_cannot_bypass_both_fingerprint_and_canonical_validation(receipt_case, variant):
    case = receipt_case
    altered = copy.deepcopy(case["receipt"])
    altered["settlement_prices"][next(iter(case["prices"]))] += 1.0
    case["archive"].write_text(json.dumps(altered, ensure_ascii=False))
    row = copy.deepcopy(case["row"])
    if variant == "reference_updated":
        row["settlement_receipt_sha256"] = case["fingerprint"](altered)
    before = _file_bytes(case["base_dir"])
    result = _inspect(case, decision=row)

    assert result["status"] == "inconsistent"
    assert result["reason"] == (
        "receipt_validation_failed" if variant == "reference_updated"
        else "decision_receipt_fingerprint_mismatch"
    )
    assert result["price_context"] is None
    assert _file_bytes(case["base_dir"]) == before


def test_changed_submission_cannot_borrow_an_unchanged_receipts_price_context(receipt_case):
    case = receipt_case
    row = copy.deepcopy(case["row"])
    row["submission_sha256"] = "a" * 64
    result = _inspect(case, decision=row)

    assert result["status"] == "inconsistent"
    assert result["reason"] == "decision_origin_mismatch"
    assert result["price_context"] is None


def test_decision_fill_vector_and_numeric_facts_must_match_the_actual_receipt(receipt_case):
    case = receipt_case
    row = copy.deepcopy(case["row"])
    if row["executed"]:
        row["executed"][0]["price"] += 1.0
        reason = "decision_fill_facts_mismatch"
    else:
        fill_id = "a" * 64
        row["settlement_fill_ids"] = [fill_id]
        row["executed"] = [{
            "transaction_id": row["settlement_transaction_id"], "fill_id": fill_id,
            "ticker": "AAPL", "side": "buy", "shares": 1.0, "price": 100.0, "value": 100.0,
        }]
        reason = "decision_fill_vector_mismatch"
    result = _inspect(case, decision=row)

    assert result["status"] == "inconsistent"
    assert result["reason"] == reason
    assert result["price_context"] is None


def test_different_active_and_archived_bytes_are_not_silently_normalized_or_chosen(receipt_case):
    case = receipt_case
    case["active"].write_text(json.dumps(case["receipt"], indent=5, ensure_ascii=False))
    assert case["active"].read_bytes() != case["archive"].read_bytes()
    before = _file_bytes(case["base_dir"])
    result = _inspect(case)

    assert result["status"] == "inconsistent"
    assert result["reason"] == "receipt_copies_disagree"
    assert result["price_context"] is None
    assert _file_bytes(case["base_dir"]) == before


def test_source_change_during_validation_withholds_the_price_context(receipt_case):
    case = receipt_case
    case["active"].write_bytes(case["raw"])

    def concurrent_ack(receipt):
        prices = case["validator"](receipt)
        case["active"].unlink()
        return prices

    result = _inspect(case, validate_receipt=concurrent_ack)

    assert result["status"] == "provisional"
    assert result["consistency"] == "changed_during_read"
    assert result["reason"] == "receipt_sources_changed"
    assert result["receipt_linkage"] == "unavailable"
    assert result["price_context"] is None
    assert case["archive"].read_bytes() == case["raw"]


@pytest.mark.parametrize("failure", ["invalid_json", "bounded_size"])
def test_unreadable_receipt_is_never_treated_as_a_complete_empty_record(receipt_case, monkeypatch, failure):
    from app import decision_availability

    case = receipt_case
    if failure == "invalid_json":
        case["archive"].write_text('{"schema": "broken"')
    else:
        monkeypatch.setattr(decision_availability, "_MAX_BYTES", 128)
    result = _inspect(case)

    assert result["status"] == "unavailable"
    assert result["reason"] == "receipt_source_unreadable_or_invalid"
    assert result["fill_count"] is None
    assert result["selected_price_count"] is None
    assert result["price_context"] is None


@pytest.mark.parametrize("failure", ["unavailable", "raised"])
def test_missing_or_failed_decoder_does_not_promote_a_valid_receipt_to_qualified_prices(
    receipt_case, monkeypatch, failure
):
    import sys

    case = receipt_case
    if failure == "unavailable":
        monkeypatch.setitem(sys.modules, "portfolio.price_evidence", None)
        decoder = None
    else:
        def decoder(*args, **kwargs):
            raise RuntimeError("synthetic context decoder failure")
    before = _file_bytes(case["base_dir"])
    result = _inspect(case, validate_capture=decoder)

    assert result["status"] == "partial"
    assert result["receipt_linkage"] == "matched"
    assert result["reason"] == (
        "price_context_decoder_unavailable" if failure == "unavailable"
        else "price_context_decoder_failed"
    )
    assert result["price_context"] is None
    assert result["execution_qualification"] == "not_checked"
    assert _file_bytes(case["base_dir"]) == before


@pytest.mark.parametrize("receipt_case", [
    (book, 0.20, kind) for book in BOOKS for kind in ("legacy", "capture_failed", "future_schema")
], indirect=True)
def test_valid_legacy_failed_and_future_captures_keep_explicit_availability(receipt_case):
    case = receipt_case
    before = _file_bytes(case["base_dir"])
    result = _inspect(case)
    expected = {
        "legacy": ("not_captured", "price_context_not_captured"),
        "capture_failed": ("capture_failed", "price_context_capture_failed"),
        "future_schema": ("unsupported", "price_context_schema_unsupported"),
    }

    assert result["status"] == "partial", result
    assert result["receipt_linkage"] == "matched"
    assert (result["context_status"], result["reason"]) == expected[case["capture_kind"]]
    assert result["fill_count"] == 1
    assert result["selected_price_count"] == len(case["prices"])
    assert result["price_context"] is None
    assert result["execution_qualification"] == "not_checked"
    assert _file_bytes(case["base_dir"]) == before


@pytest.mark.parametrize("book", ["self_directed", "etf", "flagship", "../../autonomous"])
def test_other_books_do_not_inherit_a_brain_receipt_or_read_any_file(monkeypatch, book):
    from app import settlement_price_read as reader

    def forbidden(*args, **kwargs):
        raise AssertionError("non-Brain inspection must not read or validate an artifact")

    monkeypatch.setattr(reader, "_read", forbidden)
    result = reader.read_settlement_price_evidence(
        book, {"target_status": "executed"},
        base_dir=None, currency="USD",
        validate_receipt=forbidden, fingerprint_receipt=forbidden,
    )
    assert result["status"] == "not_applicable"
    assert result["fill_count"] is None


def test_last_valid_receipt_inspection_survives_a_later_failed_pm_attempt(receipt_case):
    from app.decision_availability import read_decision_availability
    from app import web
    from portfolio import paper_account

    case = receipt_case
    failure = {
        "asof": "2026-08-14", "ts": "2026-08-14T20:00:00+00:00",
        "decision_effective": False, "target_status": "rejected_no_submission",
        "summary": None, "holdings": [], "run_id": "later-failed-attempt",
        "error": "CANARY_PRIVATE_PROVIDER_ERROR",
    }
    with (case["base_dir"] / "decisions.jsonl").open("a") as handle:
        handle.write(json.dumps(failure) + "\n")
    before = _file_bytes(case["base_dir"])
    selected = []

    def inspect(row):
        selected.append(row)
        return _inspect(case, decision=row)

    result = read_decision_availability(
        case["book"], base_dir=case["base_dir"], observed_at="2026-08-15T10:00:00+00:00",
        verify_receipt=web._decision_execution_receipt_verified,
        validate_pending=paper_account.pending_target_contract_error,
        inspect_settlement_prices=inspect,
    )
    assert selected == [case["row"]]
    assert result["latest_attempt_kind"] == "failed"
    assert result["last_valid_decision"]["decision_id"] == case["row"]["decision_id"]
    inspection = result["settlement_price_inspection"]
    assert inspection["decision_id"] == result["last_valid_decision"]["decision_id"]
    assert inspection["status"] == "available"
    assert inspection["receipt_linkage"] == "matched"
    assert inspection["book_consistency"] == "observed_stable"
    assert inspection["verification_scope"] == "receipt_preimage_and_decision_reference"
    assert inspection["durable_ledger_status"] == "not_checked"
    assert result["accepted_target"]["execution_verification_scope"] == "decision_row_identity_only"
    assert "CANARY_PRIVATE" not in json.dumps(result)
    assert _file_bytes(case["base_dir"]) == before


@pytest.mark.parametrize("change", ["account_changed", "decision_changed", "transaction_pending"])
def test_parent_source_instability_withholds_price_context(receipt_case, change):
    from app.decision_availability import read_decision_availability
    from app import web
    from portfolio import paper_account

    case = receipt_case

    def inspect(row):
        inspected = _inspect(case, decision=row)
        if change == "transaction_pending":
            (case["base_dir"] / "paper_transaction.json").write_text('{"phase":"prepared"}')
        else:
            name = "account.json" if change == "account_changed" else "decisions.jsonl"
            with (case["base_dir"] / name).open("a") as handle:
                handle.write("\n")
        return inspected

    result = read_decision_availability(
        case["book"], base_dir=case["base_dir"], observed_at="2026-08-15T10:00:00+00:00",
        verify_receipt=web._decision_execution_receipt_verified,
        validate_pending=paper_account.pending_target_contract_error,
        inspect_settlement_prices=inspect,
    )
    inspection = result["settlement_price_inspection"]
    assert inspection["status"] == "provisional"
    assert inspection["book_consistency"] == "changed_during_read"
    assert inspection["context_status"] == "unavailable"
    assert inspection["price_context"] is None
    assert inspection["execution_qualification"] == inspection["durable_ledger_status"] == "not_checked"


def test_real_api_uses_canonical_unicode_reference_without_quotes_recovery_or_cache(
    receipt_case, monkeypatch,
):
    import sys
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import auth, response_cache, web
    from bot import decision_rows
    from portfolio import paper_account as paper

    case = receipt_case
    # Standalone #1572 does not own the decoder. Missing dependency remains explicit;
    # the real producer/decoder is exercised separately in the source composition.
    monkeypatch.setitem(sys.modules, "portfolio.price_evidence", None)
    calls = []
    validator = paper.validated_settlement_receipt_prices
    fingerprint = decision_rows._canonical_sha256

    def validate(receipt):
        calls.append(("validator", receipt["transaction_id"]))
        return validator(receipt)

    def hash_receipt(receipt):
        calls.append(("decision_fingerprint", receipt["transaction_id"]))
        return fingerprint(receipt)

    def forbidden(*args, **kwargs):
        raise AssertionError("API inspection called a writer, quote, recovery or unbounded ledger read")

    monkeypatch.setattr(paper, "validated_settlement_receipt_prices", validate)
    # decision_rows uses this same helper for origin hashes too; the observer records
    # only receipt calls and delegates all other canonical hashes unchanged.
    def observe_hash(value):
        if isinstance(value, dict) and value.get("schema") == "paper_settlement_receipt.v2":
            return hash_receipt(value)
        return fingerprint(value)
    monkeypatch.setattr(decision_rows, "_canonical_sha256", observe_hash)
    for name in ("_load_account_file", "_fresh_account", "mark", "nav", "positions_pnl",
                 "settle_target", "preflight_pending_target", "quarantine_pending_target",
                 "accrue_cash_yield", "_recover_paper_transaction_unlocked",
                 "settlement_receipt_fills_are_durable"):
        monkeypatch.setattr(paper, name, forbidden)
    for name in ("_book_marks", "_book_quote_provenance", "_portfolio_dir"):
        monkeypatch.setattr(web, name, forbidden)
    app = FastAPI()
    app.include_router(web.router)
    response_cache.install(app)
    auth.install(app)
    response_cache.clear()
    monkeypatch.setenv("MASTERMIND_RESP_CACHE_TTL", "30")
    before = _file_bytes(case["base_dir"])
    for _ in range(2):
        response = TestClient(app).get("/api/portfolio", params={
            "portfolio": case["book"], "view": "decision_availability",
        })
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "x-mm-cache" not in response.headers
        result = response.json()
        inspection = result["settlement_price_inspection"]
        assert inspection["decision_id"] == case["row"]["decision_id"]
        assert inspection["receipt_linkage"] == "matched", inspection
        assert inspection["reason"] == "price_context_decoder_unavailable"
        assert inspection["fill_count"] == len(case["row"]["executed"])
        assert inspection["execution_qualification"] == "not_checked"
        assert inspection["durable_ledger_status"] == "not_checked"
    assert calls.count(("validator", case["receipt"]["transaction_id"])) == 2
    assert calls.count(("decision_fingerprint", case["receipt"]["transaction_id"])) == 2
    assert _file_bytes(case["base_dir"]) == before
    assert not response_cache._CACHE
