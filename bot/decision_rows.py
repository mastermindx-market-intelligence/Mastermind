"""Shared decision-log row semantics for the Brain books (hk / china / etf / autonomous /
heavyweight).

Every Brain book keeps ``decisions.jsonl`` idempotent per ``asof``: a re-run for a date drops
the existing row(s) for that date and appends the new one. That rule is right for a *better*
re-run and catastrophic for a *failed* one.

2026-07-24, HK: the 09:00 UTC scheduled run produced a real book (10 holdings, packet
``ed5dd3359d9dbe53``). At 14:20 the ``watch_asia_overnight`` job re-ran the same brain in
OVERNIGHT REVIEW mode; the LLM call died on ``"You've hit your session limit"``, and the error
stub it wrote for the same ``asof`` **erased that day's book** — the successful run left no
trace in ``decisions.jsonl``. The book looked "not fired since the 22nd" when it had in fact
fired and been overwritten.

The rule here: **a barren row may never supersede a substantive one for the same date.** A
failed re-run is a non-event for the ledger — the failure is already recorded in the run log
(``brain.runlog`` / ``run_events.jsonl``), which is where errors belong. A substantive re-run
still supersedes freely, so a genuinely better book replaces an earlier one as before.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


_LESSON_LINK_KEYS = {
    "lesson_presentation_id",
    "lesson_trace_cohort",
    "lesson_trace_status",
    "planned_decision_id",
    "planned_lesson_application_id",
    "lesson_ids_planned",
    "lesson_application_ids",
    "lesson_ids_cited",
}


class DecisionSettlementConflict(RuntimeError):
    """A committed settlement cannot be bound to exactly one queued decision row."""


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def submission_sha256(submission: dict | None) -> str:
    """Stable accepted-submission identity, excluding its attached lesson pointer."""
    clean = dict(submission or {})
    clean.pop("_lesson_trace", None)
    return _canonical_sha256(clean)


def decision_id(
    portfolio_id: str,
    accepted_asof: str,
    submission: dict | None,
) -> str:
    """Return the trusted lesson decision id or a deterministic no-lesson equivalent."""
    trace = (submission or {}).get("_lesson_trace")
    if isinstance(trace, dict):
        trusted = str(trace.get("decision_id") or "")
        suffix = trusted.removeprefix("decision.v1.")
        if (
            trusted.startswith("decision.v1.")
            and len(suffix) == 24
            and all(char in "0123456789abcdef" for char in suffix)
        ):
            return trusted
    digest = _canonical_sha256([
        str(portfolio_id),
        str(accepted_asof or "")[:10],
        submission_sha256(submission),
    ])
    return f"decision.v1.{digest[:24]}"


def target_sha256(target: dict[str, float] | None) -> str | None:
    """Canonical identity for the complete accepted target, if one exists."""
    if not isinstance(target, dict):
        return None
    clean: dict[str, float] = {}
    for raw_ticker, raw_weight in target.items():
        ticker = str(raw_ticker).upper().strip()
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        if ticker and math.isfinite(weight) and weight > 0.0:
            clean[ticker] = weight
    return _canonical_sha256(clean)


def accepted_identity_fields(
    portfolio_id: str,
    accepted_asof: str,
    submission: dict | None,
    effective_target: dict[str, float] | None,
    target_status: str,
) -> dict[str, str]:
    """Immutable identity needed to reconcile a queued row to its exact receipt."""
    if target_status not in {"queued", "executed"} or not isinstance(effective_target, dict):
        return {}
    return {
        "accepted_asof": str(accepted_asof or "")[:10],
        "submission_sha256": submission_sha256(submission),
        "decision_id": decision_id(portfolio_id, accepted_asof, submission),
        "target_sha256": str(target_sha256(effective_target)),
    }


def validate_queued_decision_snapshot(
    portfolio_id: str,
    decision_snapshot: dict | None,
) -> dict:
    """Prove a required executable queue has exactly one durable decision-ledger partner.

    The queue file is written before the callback-created ledger row. A process crash in that tiny
    window cannot be rolled back in Python, so settlement must perform this validation before any
    account/fill mutation. Legacy snapshots without the explicit requirement remain compatible.
    """
    from portfolio import registry

    if not isinstance(decision_snapshot, dict):
        return {"ok": True, "required": False, "reason": "no_decision_snapshot"}
    if decision_snapshot.get("decision_log_required") is not True:
        return {"ok": True, "required": False, "reason": "legacy_snapshot"}
    submission = decision_snapshot.get("submission")
    accepted_asof = str(decision_snapshot.get("accepted_asof") or "")[:10]
    expected_target = str(decision_snapshot.get("target_sha256") or "")
    if (
        decision_snapshot.get("portfolio_id") != portfolio_id
        or not isinstance(submission, dict)
        or not accepted_asof
        or not _is_sha256(expected_target)
    ):
        raise DecisionSettlementConflict("required queued decision snapshot is invalid")
    expected_decision = decision_id(portfolio_id, accepted_asof, submission)
    expected_submission = submission_sha256(submission)
    path = registry.data_dir(portfolio_id) / "decisions.jsonl"
    if not path.exists():
        raise DecisionSettlementConflict("required queued decision ledger is missing")
    rows = read_rows(path)
    exact = [
        row
        for row in rows
        if str(row.get("accepted_asof") or row.get("asof") or "")[:10] == accepted_asof
        and row.get("decision_id") == expected_decision
        and row.get("submission_sha256") == expected_submission
        and row.get("target_status") == "queued"
        and _target_lineage_matches(
            decision_snapshot, _row_target_sha256(row), expected_target
        )
    ]
    if len(exact) != 1:
        raise DecisionSettlementConflict(
            "required executable queue did not match exactly one queued decision row"
        )
    return {
        "ok": True,
        "required": True,
        "decision_id": expected_decision,
        "target_sha256": expected_target,
    }


def _target_lineage_matches(
    decision_snapshot: dict,
    row_target_hash: str,
    receipt_target_hash: str,
) -> bool:
    """Prove a deterministic queued-target rewrite from the logged hash to the receipt hash."""
    if row_target_hash == receipt_target_hash:
        return True
    lineage = decision_snapshot.get("target_lineage")
    if not isinstance(lineage, list) or not row_target_hash:
        return False
    current = row_target_hash
    for transition in lineage:
        if not isinstance(transition, dict):
            return False
        source = str(transition.get("from_target_sha256") or "")
        destination = str(transition.get("to_target_sha256") or "")
        if source != current or not _is_sha256(source) or not _is_sha256(destination):
            return False
        current = destination
    return current == receipt_target_hash


def _row_target_sha256(row: dict) -> str:
    """Read a modern hash or derive the exact positive target from a pre-release v2 row."""
    persisted = str(row.get("target_sha256") or "")
    if persisted:
        return persisted
    holdings = row.get("effective_holdings")
    if not isinstance(holdings, list):
        return ""
    target: dict[str, float] = {}
    for holding in holdings:
        if not isinstance(holding, dict):
            return ""
        ticker = str(holding.get("ticker") or "").upper().strip()
        raw_weight = holding.get("weight")
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            return ""
        if not ticker or ticker in target or not math.isfinite(weight) or weight <= 0.0:
            return ""
        target[ticker] = weight
    return str(target_sha256(target))


def _atomic_write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "\n".join(json.dumps(row, default=str, ensure_ascii=False) for row in rows) + "\n"
    ).encode("utf-8")
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def is_substantive(row: Any) -> bool:
    """True when a decision row actually carries a book, rather than an error/no-op stub.

    Barren = the brain errored, or it produced neither holdings nor a summary. Note an
    ``error`` row is barren EVEN IF it carries holdings: the error stubs copy forward
    surrounding fields, and a stub must never outrank a clean book.
    """
    if not isinstance(row, dict):
        return False
    if (
        row.get("decision_effective") is True
        and row.get("target_status") in {"queued", "executed"}
        and _is_sha256(row.get("target_sha256"))
        and str(row.get("decision_id") or "").startswith("decision.v1.")
    ):
        # Accepted execution intent outranks a stale same-day narrative even for an all-cash
        # target or when the model adapter reported a non-authoritative post-submission error.
        return True
    if row.get("error"):
        return False
    # A frozen/rejected proposal is valuable audit evidence but is not an accepted target and
    # must never replace a successfully executed/queued decision from the same session date.
    if row.get("decision_effective") is False:
        return False
    return bool(row.get("holdings")) or bool(row.get("summary"))


def replace_for_asof(existing: list[dict], entry: dict, asof: str) -> list[dict]:
    """The rows to persist after ``entry`` is recorded for ``asof`` (idempotent per date).

    Rows for other dates are preserved in order. For ``asof`` itself: normally ``entry``
    supersedes whatever was there; but when ``entry`` is barren and something substantive
    already exists for that date, the existing row(s) are KEPT and ``entry`` is dropped —
    a failed re-run cannot destroy a good book.
    """
    kept = [r for r in existing if r.get("asof") != asof]
    same_day = [r for r in existing if r.get("asof") == asof]
    if same_day and not is_substantive(entry) and any(is_substantive(r) for r in same_day):
        return kept + same_day
    return kept + [entry]


def reconcile_settlement(
    portfolio_id: str,
    receipt: dict,
    executed: list[dict],
    *,
    _locked: bool = False,
) -> dict:
    """Durably advance one exact queued decision through its committed receipt.

    The receipt is the crash-safe outbox.  A missing, ambiguous, or conflicting row is therefore
    an error: settlement finalization must retain the receipt and retry instead of guessing from a
    date or ticker set.  A retry of the same receipt is idempotent.
    """
    from portfolio import paper_account, registry

    if not _locked:
        with paper_account._paper_transaction_lock(portfolio_id):
            return reconcile_settlement(
                portfolio_id, receipt, executed, _locked=True
            )

    transaction_id = str(receipt.get("transaction_id") or "")
    receipt_target_hash = str(receipt.get("target_sha256") or "")
    decision = receipt.get("decision_snapshot")
    submission = decision.get("submission") if isinstance(decision, dict) else None
    accepted_asof = str(
        (decision or {}).get("accepted_asof")
        if isinstance(decision, dict)
        else ""
    )[:10]
    if (
        receipt.get("portfolio_id") != portfolio_id
        or not _is_sha256(transaction_id)
        or not _is_sha256(receipt_target_hash)
        or receipt_target_hash != target_sha256(receipt.get("target"))
        or not isinstance(decision, dict)
        or not isinstance(submission, dict)
        or decision.get("target_sha256") != receipt_target_hash
        or not accepted_asof
    ):
        raise DecisionSettlementConflict("invalid settlement decision lineage")

    expected_decision_id = decision_id(portfolio_id, accepted_asof, submission)
    expected_submission_hash = submission_sha256(submission)
    path = registry.data_dir(portfolio_id) / "decisions.jsonl"
    if not path.exists():
        # Low-level/manual compatibility queues predate the public decision log.  They still settle
        # through the exact receipt, but there is no user-facing queued claim to transition.
        if decision.get("decision_log_required") is True:
            raise DecisionSettlementConflict(
                "required queued decision ledger is missing"
            )
        return {
            "ok": True,
            "reconciled": False,
            "applicable": False,
            "reason": "no_queued_decision_row",
            "transaction_id": transaction_id,
        }
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            raise DecisionSettlementConflict("queued decision ledger is malformed") from exc
        if not isinstance(row, dict):
            raise DecisionSettlementConflict("queued decision ledger contains a non-object row")
        rows.append(row)

    exact = [
        index
        for index, row in enumerate(rows)
        if str(row.get("accepted_asof") or row.get("asof") or "")[:10] == accepted_asof
        # Compatibility for rows queued by the immediately preceding v2 release: it already
        # persisted the trusted lesson decision id and/or exact effective target, but not the new
        # generic identity columns.  Missing identity may be backfilled only after every available
        # field agrees and exactly one row survives the complete target check below.
        and row.get("decision_id") in {None, "", expected_decision_id}
        and row.get("submission_sha256") in {None, "", expected_submission_hash}
        and _target_lineage_matches(
            decision, _row_target_sha256(row), receipt_target_hash
        )
    ]
    if not exact and decision.get("decision_log_required") is not True:
        return {
            "ok": True,
            "reconciled": False,
            "applicable": False,
            "reason": "legacy_snapshot_without_queued_decision_row",
            "transaction_id": transaction_id,
        }
    if len(exact) != 1:
        raise DecisionSettlementConflict(
            "settlement did not match exactly one queued decision row"
        )

    index = exact[0]
    current = rows[index]
    original_target_hash = _row_target_sha256(current)
    try:
        receipt_fills = paper_account.validated_settlement_receipt_fills(receipt)
    except Exception as exc:
        raise DecisionSettlementConflict("settlement receipt fill lineage is invalid") from exc
    prior_transaction = str(current.get("settlement_transaction_id") or "")
    if prior_transaction:
        if (
            prior_transaction != transaction_id
            or current.get("target_status") != "executed"
            or current.get("target_sha256") != receipt_target_hash
        ):
            raise DecisionSettlementConflict("queued decision has conflicting settlement lineage")
        return {
            "ok": True,
            "reconciled": False,
            "deduplicated": True,
            "decision_id": expected_decision_id,
            "transaction_id": transaction_id,
        }
    if current.get("target_status") not in {"queued", "executed"}:
        raise DecisionSettlementConflict("matched decision is not accepted")

    normalized_executed = [
        {
            key: fill.get(key)
            for key in (
                "ticker", "side", "shares", "price", "value", "fill_price_source",
                "transaction_id", "fill_id",
            )
            if fill.get(key) is not None
        }
        for fill in receipt_fills
    ]
    # The receipt is the authority for immutable fill identity.  The caller's derived diff may add
    # a price-source annotation.  Numeric facts always remain the immutable receipt values; this
    # also avoids false conflicts when a display diff rounds fractional sells more coarsely.
    source_by_trade = {
        (str(derived.get("ticker") or ""), str(derived.get("side") or "")):
            derived.get("fill_price_source")
        for derived in (executed or [])
        if isinstance(derived, dict) and derived.get("fill_price_source")
    }
    for row in normalized_executed:
        source = source_by_trade.get((str(row.get("ticker") or ""), str(row.get("side") or "")))
        if source is not None:
            row["fill_price_source"] = source
    receipt_sha = _canonical_sha256(receipt)
    refreshed_links: dict = {}
    try:
        from brain import portfolio_learning
        refreshed_links = portfolio_learning.trace_links(
            submission, target_status="executed"
        )
    except Exception:
        refreshed_links = {}
    base = {key: value for key, value in current.items() if key not in _LESSON_LINK_KEYS}
    returned_decision_id = refreshed_links.get("decision_id")
    if returned_decision_id not in {None, expected_decision_id}:
        raise DecisionSettlementConflict("lesson links contain a conflicting decision id")
    rows[index] = {
        **base,
        "accepted_asof": accepted_asof,
        "submission_sha256": expected_submission_hash,
        "decision_id": expected_decision_id,
        "target_sha256": receipt_target_hash,
        "target_status": "executed",
        "decision_effective": True,
        "executed": normalized_executed,
        "settled_asof": str(receipt.get("settlement_asof") or "")[:10],
        "settlement_transaction_id": transaction_id,
        "settlement_receipt_sha256": receipt_sha,
        "settlement_fill_ids": [str(fill["fill_id"]) for fill in receipt_fills],
        **refreshed_links,
    }
    identity_backfilled = [
        key for key in ("accepted_asof", "submission_sha256", "decision_id", "target_sha256")
        if not current.get(key)
    ]
    if identity_backfilled:
        rows[index]["settlement_identity_backfilled"] = identity_backfilled
    if original_target_hash != receipt_target_hash:
        rows[index]["accepted_target_sha256"] = original_target_hash
        rows[index]["target_lineage"] = list(decision.get("target_lineage") or [])
    _atomic_write_rows(path, rows)
    return {
        "ok": True,
        "reconciled": True,
        "deduplicated": False,
        "decision_id": expected_decision_id,
        "transaction_id": transaction_id,
        "settlement_receipt_sha256": receipt_sha,
    }


def refresh_lesson_links(
    portfolio_id: str,
    accepted_asof: str,
    submission: dict | None,
    *,
    target_status: str,
) -> dict:
    """Refresh one accepted row after its durable learning application is recorded."""
    from portfolio import paper_account, registry

    if target_status not in {"queued", "executed"} or not isinstance(submission, dict):
        return {"ok": True, "applicable": False}
    expected_id = decision_id(portfolio_id, accepted_asof, submission)
    expected_submission = submission_sha256(submission)
    path = registry.data_dir(portfolio_id) / "decisions.jsonl"
    with paper_account._paper_transaction_lock(portfolio_id):
        rows = read_rows(path)
        matches = [
            index for index, row in enumerate(rows)
            if str(row.get("accepted_asof") or row.get("asof") or "")[:10]
            == str(accepted_asof)[:10]
            and row.get("decision_id") == expected_id
            and row.get("submission_sha256") == expected_submission
            and row.get("target_status") == target_status
        ]
        if len(matches) != 1:
            raise DecisionSettlementConflict(
                "lesson application did not match exactly one accepted decision row"
            )
        try:
            from brain import portfolio_learning
            links = portfolio_learning.trace_links(
                submission, target_status=target_status
            )
        except Exception as exc:
            raise DecisionSettlementConflict("lesson links are unavailable") from exc
        returned_decision_id = links.get("decision_id")
        if returned_decision_id not in {None, expected_id}:
            raise DecisionSettlementConflict("lesson links contain a conflicting decision id")
        index = matches[0]
        rows[index] = {
            **{key: value for key, value in rows[index].items()
               if key not in _LESSON_LINK_KEYS},
            **links,
        }
        write_rows(path, rows)
    return {"ok": True, "updated": True, "decision_id": expected_id}


def read_rows(path: Path) -> list[dict]:
    """Strictly read a decision JSONL ledger for serialized read-modify-write callers."""
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("decision ledger row must be an object")
        rows.append(row)
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    """Atomically persist a complete decision ledger while the caller holds its book lock."""
    _atomic_write_rows(path, rows)
