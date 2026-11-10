"""Inspect the exact receipt linked to a persisted decision, without recovery or quotes.

The existing availability parser owns bounded/strict file reads. The caller supplies
the canonical receipt validator and decision-receipt fingerprint function; the selected-price producer
owns context interpretation. This module does not create another accounting validator.
An archived copy is retained evidence, not an independent completion attestation.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from app.decision_availability import ACTIVE_BOOKS, _identity, _read, _signature

SCHEMA = "mastermind.bot.settlement_price_inspection.v1"
_CAPTURE_SCHEMA = "mastermind.settlement_price_evidence.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_FILL_REFERENCES = 2048


def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def read_settlement_price_evidence(
    portfolio_id: str,
    decision: dict | None,
    *,
    base_dir: Path,
    currency: str,
    validate_receipt: Callable[[dict], dict],
    fingerprint_receipt: Callable[[dict], str],
    validate_capture: Callable[[dict, dict, str, dict], dict] | None = None,
) -> dict:
    """Read at most the named active and retained copies of one exact receipt.

    A missing historical receipt stays missing. No scan for a convenient replacement,
    account read, transaction recovery, quote read, acknowledgement or writer is used.
    Availability is separate from execution qualification, which remains not checked.
    """
    result = {
        "schema": SCHEMA,
        "portfolio_id": portfolio_id,
        "decision_id": _identity(decision.get("decision_id")) if isinstance(decision, dict) else None,
        "status": "unavailable",
        "reason": "decision_unavailable",
        "transaction_id": None,
        "receipt_sha256": None,
        "receipt_location": "none",
        "receipt_linkage": "unavailable",
        "verification_scope": "receipt_preimage_and_decision_reference",
        "durable_ledger_status": "not_checked",
        "receipt_sources": {},
        "consistency": "not_observed",
        "settlement_asof": None,
        "fill_count": None,
        "selected_price_count": None,
        "context_status": "unavailable",
        "context_validation_scope": "not_checked",
        "context_gap_reason_scope": "recorded_at_capture",
        "price_context": None,
        "execution_qualification": "not_checked",
    }
    if portfolio_id not in ACTIVE_BOOKS:
        result.update(status="not_applicable", reason="book_not_applicable")
        return result
    if not isinstance(decision, dict):
        return result
    if decision.get("target_status") != "executed":
        result["reason"] = "decision_not_recorded_settled"
        return result
    transaction_id = decision.get("settlement_transaction_id")
    expected_hash = decision.get("settlement_receipt_sha256")
    fill_ids = decision.get("settlement_fill_ids")
    executed = decision.get("executed")
    if (
        not _sha(transaction_id) or not _sha(expected_hash)
        or not isinstance(fill_ids, list) or not isinstance(executed, list)
        or len(fill_ids) != len(executed) or len(fill_ids) > _MAX_FILL_REFERENCES
        or not all(_sha(value) for value in fill_ids)
        or len(set(fill_ids)) != len(fill_ids)
    ):
        result["reason"] = "receipt_reference_unavailable"
        return result
    result.update(transaction_id=transaction_id, receipt_sha256=expected_hash)
    root = base_dir / "settlement_receipts"
    paths = {
        "active": root / (transaction_id + ".json"),
        "acknowledged": root / "acknowledged" / (transaction_id + ".json"),
    }
    records, signatures = {}, {}
    for key, path in paths.items():
        records[key], result["receipt_sources"][key], signatures[key] = _read(path)
    present = [key for key, source in result["receipt_sources"].items()
               if source["status"] == "available"]
    result["receipt_location"] = "both" if len(present) == 2 else present[0] if present else "none"

    def finish():
        changed = []
        for key, path in paths.items():
            try:
                if _signature(path) != signatures[key]:
                    changed.append(key)
            except OSError:
                changed.append(key)
        result["consistency"] = "changed_during_read" if changed else "observed_stable"
        if changed:
            result.update(
                status="provisional", reason="receipt_sources_changed",
                receipt_linkage="unavailable", context_status="unavailable", price_context=None,
            )
        elif "active" in present and result["status"] in {"available", "partial"}:
            result.update(status="provisional", reason="active_receipt_still_present")
        return result

    if any(source["status"] not in {"available", "missing"}
           for source in result["receipt_sources"].values()):
        result["reason"] = "receipt_source_unreadable_or_invalid"
        return finish()
    if not present:
        result["reason"] = "receipt_missing"
        return finish()
    if len(present) == 2 and (
        result["receipt_sources"]["active"]["sha256"]
        != result["receipt_sources"]["acknowledged"]["sha256"]
    ):
        result.update(status="inconsistent", reason="receipt_copies_disagree")
        return finish()
    receipt = records[present[0]]
    if receipt.get("schema") != "paper_settlement_receipt.v2":
        result["reason"] = "receipt_schema_unsupported"
        return finish()
    if receipt.get("portfolio_id") != portfolio_id or receipt.get("transaction_id") != transaction_id:
        result.update(status="inconsistent", reason="receipt_identity_mismatch")
        return finish()
    try:
        actual_hash = fingerprint_receipt(receipt)
    except Exception:
        result["reason"] = "receipt_fingerprint_unavailable"
        return finish()
    if not _sha(actual_hash) or actual_hash != expected_hash:
        result.update(status="inconsistent", reason="decision_receipt_fingerprint_mismatch")
        return finish()
    try:
        prices = validate_receipt(receipt)
        if not isinstance(prices, dict) or not prices:
            raise ValueError("receipt validator did not return a price map")
    except Exception:
        result.update(status="inconsistent", reason="receipt_validation_failed")
        return finish()
    fills = receipt.get("fills")
    if not isinstance(fills, list) or len(fills) != len(fill_ids):
        result.update(status="inconsistent", reason="decision_fill_vector_mismatch")
        return finish()
    if [fill.get("fill_id") for fill in fills] != fill_ids:
        result.update(status="inconsistent", reason="decision_fill_vector_mismatch")
        return finish()
    for recorded, filled in zip(executed, fills):
        if not isinstance(recorded, dict) or any(
            recorded.get(key) != filled.get(key)
            for key in ("transaction_id", "fill_id", "ticker", "side", "shares", "price", "value")
        ):
            result.update(status="inconsistent", reason="decision_fill_facts_mismatch")
            return finish()
    snapshot = receipt.get("decision_snapshot")
    submission = snapshot.get("submission") if isinstance(snapshot, dict) else None
    if not isinstance(snapshot, dict) or not isinstance(submission, dict):
        result["reason"] = "decision_origin_unavailable"
        return finish()
    try:
        from bot import decision_rows
        expected_identity = decision_rows.accepted_identity_fields(
            portfolio_id, snapshot.get("accepted_asof"), submission,
            receipt.get("target"), "executed",
        )
    except Exception:
        result["reason"] = "decision_identity_unavailable"
        return finish()
    if (
        not expected_identity
        or any(decision.get(key) != value for key, value in expected_identity.items())
        or snapshot.get("portfolio_id") != portfolio_id
        or snapshot.get("target_sha256") != expected_identity.get("target_sha256")
        or receipt.get("target_sha256") != expected_identity.get("target_sha256")
        or receipt.get("queued_asof") != expected_identity.get("accepted_asof")
        or receipt.get("settlement_asof") != decision.get("settled_asof")
    ):
        result.update(status="inconsistent", reason="decision_origin_mismatch")
        return finish()
    result.update(
        receipt_linkage="matched", status="partial", reason="price_context_not_captured",
        settlement_asof=receipt["settlement_asof"], fill_count=len(fills),
        selected_price_count=len(prices), context_status="not_captured",
    )
    capture = receipt.get("transaction_identity", {}).get("followup", {}).get(
        "settlement_price_evidence"
    )
    if capture is None:
        return finish()
    if not isinstance(capture, dict) or capture.get("schema") != _CAPTURE_SCHEMA:
        result.update(context_status="unsupported", reason="price_context_schema_unsupported")
        return finish()
    if capture.get("capture_error") == "snapshot_failed":
        expected = {
            "schema": _CAPTURE_SCHEMA, "currency": None, "quotes": {},
            "omitted_quote_count": len(prices), "capture_error": "snapshot_failed",
            "market_observed_at": None, "execution_qualification": "not_checked",
        }
        if capture != expected:
            result.update(status="inconsistent", context_status="invalid", reason="price_context_invalid")
        else:
            result.update(context_status="capture_failed", reason="price_context_capture_failed")
        return finish()
    quotes = capture.get("quotes")
    if (
        not isinstance(quotes, dict) or len(quotes) > 128
        or not all(isinstance(value, dict) for value in quotes.values())
    ):
        result.update(status="inconsistent", context_status="invalid", reason="price_context_invalid")
        return finish()
    if validate_capture is None:
        try:
            from portfolio.price_evidence import validated_settlement_snapshot
            validate_capture = validated_settlement_snapshot
        except ImportError:
            result.update(context_status="unavailable", reason="price_context_decoder_unavailable")
            return finish()
    try:
        rebuilt = validate_capture(
            prices, receipt.get("settlement_price_sources") or {}, currency,
            capture,
        )
    except ValueError:
        result.update(status="inconsistent", context_status="invalid", reason="price_context_invalid")
        return finish()
    except Exception:
        result.update(context_status="unavailable", reason="price_context_decoder_failed")
        return finish()
    if not isinstance(rebuilt, dict) or rebuilt != capture:
        result.update(status="inconsistent", context_status="invalid", reason="price_context_invalid")
        return finish()
    result.update(
        status="available", reason=None, context_status="available", price_context=rebuilt,
        context_validation_scope="selected_prices_sources_and_bounded_capture_contract",
    )
    return finish()
