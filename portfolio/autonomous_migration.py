"""One-time, paper-only removal of legacy ETFs from the US Brain account.

The US Brain's executable universe is common stock only.  This module does not
invent a replacement book and it does not edit paper state directly: it builds
an evidenced ``legacy_instrument_migration`` decision, sends that decision
through the same trusted normalizer as the nightly PM, and routes the resulting
complete target through :func:`bot.settle.execute_or_queue`.

The operator entry point is deliberately dry-run by default.  ``apply=True`` is
required before any pending target, paper fill, or audit record can be written.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any

PORTFOLIO_ID = "autonomous"
MIGRATION_SCHEMA = "autonomous_legacy_etf_migration.v1"
AUDIT_FILE = "legacy_etf_migration.jsonl"
SOURCE_ARTIFACT = "scripts/migrate_autonomous_etfs.py"


class MigrationFreeze(RuntimeError):
    """The account cannot be converted into a safe ETF-only exit instruction."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_account_snapshot() -> tuple[dict[str, Any], str]:
    """Read account.json without triggering transaction recovery or another write."""
    from portfolio import paper_account

    transaction = paper_account._transaction_path(PORTFOLIO_ID)
    if transaction.exists():
        raise MigrationFreeze("unresolved_paper_transaction")
    path = paper_account._paths(PORTFOLIO_ID)["account"]
    if not path.exists():
        account = paper_account._fresh_account()
        return account, _sha256(account)
    try:
        raw = path.read_bytes()
        account = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationFreeze("account_unreadable") from exc
    if not isinstance(account, dict):
        raise MigrationFreeze("account_not_object")
    if not isinstance(account.get("positions"), dict):
        raise MigrationFreeze("account_positions_invalid")
    if isinstance(account.get("cash"), bool) or not isinstance(
        account.get("cash"), (int, float)
    ):
        raise MigrationFreeze("account_cash_invalid")
    if not math.isfinite(float(account["cash"])) or float(account["cash"]) < 0.0:
        raise MigrationFreeze("account_cash_invalid")
    return account, hashlib.sha256(raw).hexdigest()


def _held_lots(account: dict[str, Any]) -> dict[str, dict[str, float]]:
    held: dict[str, dict[str, float]] = {}
    for raw_ticker, raw_lot in (account.get("positions") or {}).items():
        ticker = str(raw_ticker or "").upper().strip()
        if not ticker or not isinstance(raw_lot, dict):
            raise MigrationFreeze(f"invalid_held_lot:{raw_ticker}")
        if raw_ticker != ticker:
            raise MigrationFreeze(f"noncanonical_held_ticker:{raw_ticker}")
        if ticker in held:
            raise MigrationFreeze(f"duplicate_held_ticker:{ticker}")
        try:
            shares = float(raw_lot.get("shares") or 0.0)
            avg_cost = float(raw_lot.get("avg_cost") or 0.0)
        except (TypeError, ValueError) as exc:
            raise MigrationFreeze(f"invalid_held_lot:{ticker}") from exc
        if not math.isfinite(shares) or shares < 0.0:
            raise MigrationFreeze(f"invalid_held_shares:{ticker}")
        if shares <= 1e-9:
            continue
        if not math.isfinite(avg_cost) or avg_cost <= 0.0:
            raise MigrationFreeze(f"invalid_held_cost_basis:{ticker}")
        held[ticker] = {"shares": shares, "avg_cost": avg_cost}
    return held


def _classify_held(held: dict[str, dict[str, float]]) -> dict[str, Any]:
    from portfolio import instrument_policy

    common: list[str] = []
    etfs: list[str] = []
    identities: dict[str, dict[str, Any]] = {}
    blocked: list[dict[str, Any]] = []
    for ticker in sorted(held):
        try:
            raw_identity = instrument_policy.classify_us_instrument(ticker)
            identity = dict(raw_identity) if isinstance(raw_identity, dict) else {}
        except Exception as exc:  # noqa: BLE001 - identity failure can never authorize a sale
            identity = {
                "ticker": ticker,
                "kind": "unknown",
                "status": f"identity_lookup_failed:{type(exc).__name__}",
                "verified": False,
            }
        identities[ticker] = identity
        verified = identity.get("verified") is True
        kind = identity.get("kind")
        if verified and kind == "common_stock":
            common.append(ticker)
        elif verified and kind == "etf":
            etfs.append(ticker)
        else:
            blocked.append(
                {
                    "ticker": ticker,
                    "kind": kind or "unknown",
                    "status": identity.get("status") or "unverified_identity",
                }
            )
    return {
        "common_stocks": common,
        "legacy_etfs": etfs,
        "identities": identities,
        "blocked": blocked,
    }


def _proposal(
    *,
    common_stocks: list[str],
    legacy_etfs: list[str],
    identities: dict[str, dict[str, Any]],
    account_sha256: str,
    asof: str,
) -> dict[str, Any]:
    account_evidence = f"autonomous/account.json sha256:{account_sha256}"
    mandate_evidence = "operator directive: US Brain ETFs are prohibited"
    holdings = []
    for ticker in common_stocks:
        identity = identities[ticker]
        holdings.append(
            {
                "ticker": ticker,
                "action": "hold",
                "rationale": (
                    "Preserve this positively verified common-stock holding while the "
                    "one-time mandate migration removes only inherited ETFs."
                ),
                "conviction": "medium",
                "why_now": "The migration is operational and supplies no new stock-selection view.",
                "falsifier": "Any migration-generated common-stock fill is a correctness breach.",
                "evidence": [
                    account_evidence,
                    f"portfolio.instrument_policy:{identity.get('status')}",
                ],
                "source_provenance": [
                    "portfolio.instrument_policy",
                    "portfolio.paper_account",
                ],
                "expected_horizon": "Carry into the next accountable nightly PM review.",
                "exit_plan": "No exit is authorized by this ETF-only migration.",
            }
        )
    exits = []
    for ticker in legacy_etfs:
        identity = identities[ticker]
        exits.append(
            {
                "ticker": ticker,
                "action": "exit",
                "reason": (
                    "Remove an inherited ETF from the common-stock-only US Brain; "
                    "the proceeds remain cash for the next accountable stock-selection turn."
                ),
                "reason_code": "legacy_instrument_migration",
                "evidence": [
                    mandate_evidence,
                    account_evidence,
                    f"portfolio.instrument_policy:{identity.get('status')}",
                ],
                "falsifier": "The instrument is proven to be a common stock before settlement.",
                "why_now": "The strict stock-only mandate was clarified and must hold at execution.",
            }
        )
    return {
        "holdings": holdings,
        "summary": (
            "One-time, paper-only mandate migration: retain every verified common stock "
            f"and submit explicit exits for {', '.join(legacy_etfs)}."
        ),
        "sold_note": (
            "ETF exits are authorized intent only until the paper settlement reports fills; "
            "no replacement security is selected by this migration."
        ),
        "exit_decisions": exits,
        "mandate": "US Brain executable holdings are verified US common stocks only.",
        "falsifiers": [
            "Any ETF remains after a priceable open settlement.",
            "Any common-stock position is opened or closed by this migration.",
        ],
        "evidence_planes": ["paper_account", "instrument_policy"],
        "source_provenance": [
            account_evidence,
            "portfolio.instrument_policy",
            SOURCE_ARTIFACT,
        ],
        "liquidity_notes": "Settlement requires a trusted price for every explicit ETF exit.",
        "risk_posture": "normal",
        "cash_rationale": (
            "ETF sale proceeds stay in cash until the nightly PM deliberately selects "
            "verified common stocks; this migration has no buy authority."
        ),
        "expected_failure_mode": (
            "A missing ETF exit quote retains the complete target for retry with zero paper fills."
        ),
        "decision_memo": {
            "market_frame": "Not an investment view; strict mandate correction.",
            "candidate_funnel": {"reviewed_actual_holdings": common_stocks + legacy_etfs},
            "selected": common_stocks,
            "rejected": legacy_etfs,
            "changes": {"explicit_legacy_etf_exits": legacy_etfs},
            "timing": "Queue off-hours; settle only in an open session with complete prices.",
            "risk_deliberation": "No new positions and no discretionary reallocation.",
            "alternatives": "Silent deletion and invented fills were rejected.",
            # This operator correction does not claim a scored portfolio-learning
            # citation; a free-text item here would incorrectly require an
            # applications-ledger transition before receipt acknowledgement.
            "lessons_applied": [],
            "context_gaps": [],
            "delegation_summary": "Deterministic operator migration; no LLM invoked.",
        },
        "operator_migration_requested_asof": asof,
    }


def _pending_payload() -> dict[str, Any] | None:
    from portfolio import paper_account

    return paper_account._read_pending_target_payload(PORTFOLIO_ID)


def is_pending_migration() -> bool:
    """Whether the autonomous queue carries this operator migration authority.

    This is a read-only overwrite fence, not a settlement validator.  Once the
    marker is present, nightly, overnight, and de-risk writers must leave the
    file untouched so the paper-account preflight can either execute or
    quarantine the exact hash-bound instruction.
    """
    pending = _pending_payload()
    if not isinstance(pending, dict) or pending.get("portfolio_id") != PORTFOLIO_ID:
        return False
    decision = pending.get("decision_snapshot")
    submission = decision.get("submission") if isinstance(decision, dict) else None
    migration = submission.get("operator_migration") if isinstance(submission, dict) else None
    return bool(
        isinstance(migration, dict)
        and migration.get("schema") == MIGRATION_SCHEMA
        and migration.get("paper_only") is True
    )


def _equivalent_pending(pending: dict[str, Any] | None, plan: dict[str, Any]) -> bool:
    if (
        not isinstance(pending, dict)
        or pending.get("target") != plan.get("target")
        or pending.get("execution_constraints") != plan.get("execution_constraints")
    ):
        return False
    decision = pending.get("decision_snapshot")
    submission = decision.get("submission") if isinstance(decision, dict) else None
    migration = submission.get("operator_migration") if isinstance(submission, dict) else None
    return bool(
        isinstance(migration, dict)
        and migration.get("schema") == MIGRATION_SCHEMA
        and migration.get("migration_id") == plan.get("migration_id")
    )


def _current_prices(tickers: list[str]) -> tuple[dict[str, float], dict[str, str]]:
    from portfolio import paper_account

    prices: dict[str, float] = {}
    sources: dict[str, str] = {}
    for ticker in tickers:
        try:
            price = paper_account._current_price(ticker)
            price = float(price) if price is not None else None
        except Exception:  # noqa: BLE001 - a missing observation remains an explicit gap
            price = None
        if price is not None and math.isfinite(price) and price > 0.0:
            prices[ticker] = price
            sources[ticker] = "current_price"
    return prices, sources


def build_plan(asof: str | None = None) -> dict[str, Any]:
    """Build a read-only, normalized migration plan from the actual paper account."""
    from brain import decision_submission

    asof = asof or date.today().isoformat()
    try:
        if date.fromisoformat(asof).isoformat() != asof:
            raise ValueError(asof)
    except (TypeError, ValueError):
        return {
            "schema": MIGRATION_SCHEMA,
            "portfolio_id": PORTFOLIO_ID,
            "paper_only": True,
            "asof": asof,
            "apply": False,
            "ok": False,
            "status": "blocked_invalid_asof",
        }
    try:
        account, account_sha = _read_account_snapshot()
        held = _held_lots(account)
        classified = _classify_held(held)
        from portfolio import paper_account
        positions_digest = paper_account.positions_sha256(held)
    except MigrationFreeze as exc:
        return {
            "schema": MIGRATION_SCHEMA,
            "portfolio_id": PORTFOLIO_ID,
            "paper_only": True,
            "asof": asof,
            "apply": False,
            "ok": False,
            "status": "blocked_account_contract",
            "error": str(exc),
        }
    base: dict[str, Any] = {
        "schema": MIGRATION_SCHEMA,
        "portfolio_id": PORTFOLIO_ID,
        "paper_only": True,
        "asof": asof,
        "apply": False,
        "account_sha256": account_sha,
        "positions_sha256": positions_digest,
        "common_stocks": classified["common_stocks"],
        "legacy_etfs": classified["legacy_etfs"],
        "instrument_identities": classified["identities"],
        "blocked_instruments": classified["blocked"],
    }
    if classified["blocked"]:
        return {**base, "ok": False, "status": "blocked_unknown_held_instrument"}
    if not classified["legacy_etfs"]:
        return {**base, "ok": True, "status": "already_complete", "target": None}

    proposal = _proposal(
        common_stocks=classified["common_stocks"],
        legacy_etfs=classified["legacy_etfs"],
        identities=classified["identities"],
        account_sha256=account_sha,
        asof=asof,
    )
    try:
        # ``paper_account._load_account`` normally acquires the paper transaction
        # lock and may create its zero-byte lock file.  An operator dry run must be
        # byte-for-byte read-only, so bind the normalizer to the already validated,
        # hash-bound snapshot in this short-lived operator process.  The executable
        # apply path re-reads the real file and the settlement boundary owns locking.
        from unittest.mock import patch

        with patch.object(
            __import__("portfolio.paper_account", fromlist=["_load_account"]),
            "_load_account",
            lambda portfolio_id=None: deepcopy(account)
            if portfolio_id == PORTFOLIO_ID
            else (_ for _ in ()).throw(
                MigrationFreeze(f"unexpected_account_scope:{portfolio_id}")
            ),
        ):
            submission, audit = decision_submission.normalize(
                PORTFOLIO_ID,
                proposal,
                stock_only=True,
                early_exit_hysteresis=True,
                deterministic_sizing=True,
                decision_asof=asof,
            )
    except decision_submission.DecisionBoundaryFreeze as exc:
        return {
            **base,
            "ok": False,
            "status": "blocked_normalization_freeze",
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - operator migration fails closed
        return {
            **base,
            "ok": False,
            "status": "blocked_normalization_error",
            "error": f"{type(exc).__name__}:{exc}"[:240],
        }

    target = {
        str(row.get("ticker") or "").upper(): float(row.get("weight") or 0.0)
        for row in submission.get("holdings") or []
        if float(row.get("weight") or 0.0) > 0.0
    }
    expected_common = set(classified["common_stocks"])
    effective_exits = {
        str(row.get("ticker") or "").upper()
        for row in submission.get("exit_decisions") or []
        if row.get("reason_code") == "legacy_instrument_migration"
    }
    normalization_error = None
    if set(target) != expected_common:
        normalization_error = "normalized_target_did_not_preserve_common_stock_set"
    elif effective_exits != set(classified["legacy_etfs"]):
        normalization_error = "normalized_exit_set_mismatch"
    elif audit.get("blocked_exits") or audit.get("invalid_exit_requests"):
        normalization_error = "migration_exit_blocked_by_normalizer"
    if normalization_error:
        return {
            **base,
            "ok": False,
            "status": "blocked_normalization_contract",
            "error": normalization_error,
            "normalization_audit": audit,
        }

    migration_id = _sha256(
        {
            "schema": MIGRATION_SCHEMA,
            "account_sha256": account_sha,
            "positions_sha256": positions_digest,
            "legacy_etfs": classified["legacy_etfs"],
            "target": target,
        }
    )
    execution_constraints = {
        "schema": "execution_constraints.v1",
        "mode": "preserve_existing_shares",
        "tickers": sorted(classified["common_stocks"]),
        "target_sha256": paper_account._target_sha256(target),
        "positions_sha256": positions_digest,
    }
    submission["operator_migration"] = {
        "schema": MIGRATION_SCHEMA,
        "migration_id": migration_id,
        "account_sha256": account_sha,
        "positions_sha256": positions_digest,
        "legacy_etfs": classified["legacy_etfs"],
        "preserved_common_stocks": classified["common_stocks"],
        "paper_only": True,
        "execution_constraints": deepcopy(execution_constraints),
        "execution_semantics": (
            "Hash-bound preserve_existing_shares pins every verified common-stock lot "
            "to its exact pre-settlement share count even after extreme queued price drift."
        ),
    }
    prices, price_sources = _current_prices(sorted(held))
    pending = _pending_payload()
    equivalent_pending = _equivalent_pending(
        pending,
        {
            "target": target,
            "migration_id": migration_id,
            "execution_constraints": execution_constraints,
        },
    )
    pending_path = paper_account._pending_target_path(PORTFOLIO_ID)
    pending_exists = pending_path.exists()
    result = {
        **base,
        "ok": True,
        "status": "ready",
        "migration_id": migration_id,
        "target": target,
        "execution_constraints": execution_constraints,
        "submission": submission,
        "normalization_audit": audit,
        "observed_prices": prices,
        "price_sources": price_sources,
        "missing_prices": sorted(set(held) - set(prices)),
        "equivalent_pending": equivalent_pending,
    }
    if pending_exists and not equivalent_pending:
        try:
            pending_sha256 = hashlib.sha256(pending_path.read_bytes()).hexdigest()
        except OSError:
            pending_sha256 = None
        result.update(
            {
                "ok": False,
                "status": "blocked_non_equivalent_pending_target",
                "existing_pending_sha256": pending_sha256,
                "existing_pending_asof": (
                    pending.get("asof") if isinstance(pending, dict) else None
                ),
                "note": (
                    "An existing queued stock decision has independent authority. "
                    "The ETF migration will not replace it implicitly."
                ),
            }
        )
    return result


def _append_audit(record: dict[str, Any]) -> None:
    from portfolio import paper_account, registry

    paper_account._append_jsonl(registry.data_dir(PORTFOLIO_ID) / AUDIT_FILE, record)


def persist_settlement_link(receipt: dict[str, Any]) -> dict[str, Any]:
    """Durably link a committed migration receipt to its paper fills before ack.

    Called by the shared settlement outbox finalizer.  Non-migration receipts are
    a no-op.  A retry with the same immutable receipt deduplicates; a conflicting
    record or any common-stock fill fails closed so the receipt remains available
    for operator investigation.
    """
    if not isinstance(receipt, dict):
        raise MigrationFreeze("settlement_receipt_not_object")
    decision = receipt.get("decision_snapshot")
    submission = decision.get("submission") if isinstance(decision, dict) else None
    migration = submission.get("operator_migration") if isinstance(submission, dict) else None
    if not (
        isinstance(migration, dict)
        and migration.get("schema") == MIGRATION_SCHEMA
    ):
        return {"ok": True, "applicable": False}
    if receipt.get("portfolio_id") != PORTFOLIO_ID:
        raise MigrationFreeze("migration_receipt_portfolio_mismatch")

    transaction_id = str(receipt.get("transaction_id") or "")
    migration_id = str(migration.get("migration_id") or "")
    if len(transaction_id) != 64 or any(c not in "0123456789abcdef" for c in transaction_id):
        raise MigrationFreeze("migration_transaction_id_invalid")
    if len(migration_id) != 64 or any(c not in "0123456789abcdef" for c in migration_id):
        raise MigrationFreeze("migration_id_invalid")
    migration_constraints = migration.get("execution_constraints") or {}
    if receipt.get("target_sha256") != migration_constraints.get("target_sha256"):
        raise MigrationFreeze("migration_receipt_target_hash_mismatch")
    if receipt.get("execution_constraints") != migration_constraints:
        raise MigrationFreeze("migration_receipt_constraint_mismatch")

    legacy_etfs = sorted(
        {str(ticker or "").upper().strip() for ticker in migration.get("legacy_etfs") or []}
        - {""}
    )
    preserved = sorted(
        {
            str(ticker or "").upper().strip()
            for ticker in migration.get("preserved_common_stocks") or []
        }
        - {""}
    )
    bounded_fills: list[dict[str, Any]] = []
    fill_ids: list[str] = []
    for raw in receipt.get("fills") or []:
        if not isinstance(raw, dict):
            raise MigrationFreeze("migration_fill_not_object")
        ticker = str(raw.get("ticker") or "").upper().strip()
        side = str(raw.get("side") or "").lower().strip()
        fill_id = str(raw.get("fill_id") or "")
        fill_transaction = str(raw.get("transaction_id") or "")
        if ticker in preserved:
            raise MigrationFreeze(f"preserved_common_stock_fill:{ticker}")
        if ticker not in legacy_etfs or side != "sell":
            raise MigrationFreeze(f"unexpected_migration_fill:{ticker}:{side}")
        if len(fill_id) != 64 or any(c not in "0123456789abcdef" for c in fill_id):
            raise MigrationFreeze(f"migration_fill_id_invalid:{ticker}")
        if fill_transaction != transaction_id:
            raise MigrationFreeze(f"migration_fill_transaction_mismatch:{ticker}")
        fill_ids.append(fill_id)
        bounded_fills.append(
            {
                key: raw.get(key)
                for key in (
                    "ticker",
                    "side",
                    "shares",
                    "price",
                    "value",
                    "fill_id",
                    "transaction_id",
                )
            }
        )
    if len(fill_ids) != len(set(fill_ids)):
        raise MigrationFreeze("duplicate_migration_fill_id")
    if {str(row.get("ticker") or "").upper() for row in bounded_fills} != set(
        legacy_etfs
    ):
        raise MigrationFreeze("migration_exit_fill_set_mismatch")
    receipt_sha256 = _sha256(receipt)
    from portfolio import registry

    path = registry.data_dir(PORTFOLIO_ID) / AUDIT_FILE
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("non-object audit row")
                    existing.append(row)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise MigrationFreeze("migration_audit_unreadable") from exc
    prior = next(
        (
            row
            for row in existing
            if row.get("event") == "migration_settlement_committed"
            and row.get("transaction_id") == transaction_id
        ),
        None,
    )
    if prior is not None:
        if (
            prior.get("migration_id") != migration_id
            or prior.get("receipt_sha256") != receipt_sha256
            or sorted(prior.get("fill_ids") or []) != sorted(fill_ids)
        ):
            raise MigrationFreeze("migration_settlement_link_conflict")
        return {
            "ok": True,
            "applicable": True,
            "deduplicated": True,
            "migration_id": migration_id,
            "transaction_id": transaction_id,
            "fill_ids": sorted(fill_ids),
        }

    record = {
        "schema": MIGRATION_SCHEMA,
        "event": "migration_settlement_committed",
        "linked_at": datetime.now(UTC).isoformat(),
        "portfolio_id": PORTFOLIO_ID,
        "paper_only": True,
        "migration_id": migration_id,
        "transaction_id": transaction_id,
        "target_sha256": receipt.get("target_sha256"),
        "receipt_sha256": receipt_sha256,
        "settlement_asof": receipt.get("settlement_asof"),
        "legacy_etfs": legacy_etfs,
        "preserved_common_stocks": preserved,
        "fill_ids": sorted(fill_ids),
        "fills": bounded_fills[:50],
    }
    _append_audit(record)
    return {
        "ok": True,
        "applicable": True,
        "deduplicated": False,
        "migration_id": migration_id,
        "transaction_id": transaction_id,
        "fill_ids": sorted(fill_ids),
    }


def _governance_event(plan: dict[str, Any], attempt_id: str) -> str | None:
    try:
        from control_plane import governance
        from portfolio import registry

        return governance.append(
            {
                "event_type": "legacy_instrument_migration_authorized",
                "target": PORTFOLIO_ID,
                "actor": "operator-script",
                "reason": (
                    "Strict US Brain common-stock-only mandate; explicitly exit inherited "
                    f"ETFs {plan['legacy_etfs']} without selecting replacements."
                ),
                "before": {
                    "account_sha256": plan["account_sha256"],
                    "legacy_etfs": plan["legacy_etfs"],
                    "common_stocks": plan["common_stocks"],
                },
                "after": {
                    "attempt_id": attempt_id,
                    "target_sha256": _sha256(plan["target"]),
                    "settlement": "queued_or_priceable_open_only",
                },
                "rollback": "Paper-only: inspect the hash-bound decision and add a new explicit reviewed target; never rewrite fills.",
                "source_artifact": SOURCE_ARTIFACT,
            },
            root=registry._ROOT,
        )
    except Exception:  # noqa: BLE001 - the book-local durable ledger is authoritative here
        return None


def _publish_accepted_migration(
    plan: dict[str, Any],
    result: dict[str, Any],
    *,
    target_status: str,
    attempt_id: str,
    execution_prices: dict[str, float],
    finalization: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project accepted migration intent into the US decision and dashboard contracts."""
    brain = {
        "text": (
            "Deterministic operator migration. Positively identified inherited ETFs, "
            "preserved verified common stocks, and authorized no replacement buys."
        ),
        "run_id": attempt_id,
        "tools_used": [
            "portfolio.instrument_policy",
            "brain.decision_submission.normalize",
            "bot.settle.execute_or_queue",
        ],
        "cost_usd": 0.0,
        "model": "deterministic_operator_migration",
        "error": None,
    }
    skipped = list(result.get("unpriceable_targets") or [])
    projection: dict[str, Any] = {
        "decision_log_ok": False,
        "published_ok": False,
    }
    try:
        from bot import autonomous
        from bridge import build_portfolio
    except Exception as exc:  # noqa: BLE001 - executable intent remains independently durable
        projection["projection_import_error"] = repr(exc)[:240]
        return projection
    try:
        autonomous._append_decision_log(
            plan["asof"],
            plan["submission"],
            result.get("executed") or [],
            skipped,
            brain,
            target_status=target_status,
            effective_target=plan["target"],
        )
        projection["decision_log_ok"] = True
    except Exception as exc:  # noqa: BLE001 - pending/receipt remains the execution authority
        projection["decision_log_error"] = repr(exc)[:240]

    try:
        payload = autonomous._build_payload(
            plan["asof"],
            plan["submission"],
            execution_prices,
            result.get("executed") or [],
            skipped,
            brain,
            target_status=target_status,
        )
        pending = target_status == "queued"
        pending_reason = (
            "trusted_exit_price_missing"
            if result.get("skipped") == "unpriceable_exit_prices"
            else "next_market_open"
        )
        migration_status = {
            "schema": MIGRATION_SCHEMA,
            "migration_id": plan["migration_id"],
            "attempt_id": attempt_id,
            "status": "pending" if pending else "settled",
            "paper_only": True,
            "legacy_etfs": plan["legacy_etfs"],
            "preserved_common_stocks": plan["common_stocks"],
            "pending_reason": pending_reason if pending else None,
            "settlement_receipt_id": result.get("settlement_receipt_id"),
            "receipt_finalized": bool(
                finalization and finalization.get("receipt_acknowledged")
            ),
            "note": (
                "Actual ETF lots remain visible until priceable paper settlement; "
                "they are explicit migration exits, not active stock selections."
                if pending
                else "The explicit paper ETF exits settled; no replacement buys were authorized."
            ),
        }
        payload["legacy_etf_migration"] = migration_status
        payload.setdefault("decisions", []).insert(
            0,
            {
                "subject": "Legacy ETF mandate migration",
                "lean": migration_status["note"],
                "thesis": f"Explicit exits: {', '.join(plan['legacy_etfs'])}",
                "logged_at": datetime.now(UTC).isoformat(),
            },
        )
        if pending:
            exit_set = set(plan["legacy_etfs"])
            for position in payload.get("positions") or []:
                ticker = str(position.get("ticker") or "").upper()
                if ticker not in exit_set:
                    continue
                rationale = (
                    "Legacy ETF — explicit stock-only mandate exit is queued. "
                    "This actual paper lot remains visible until a trusted fill is recorded."
                )
                position.update(
                    {
                        "verdict": "exit_pending",
                        "action": "exit",
                        "rationale": rationale,
                        "migration_status": "legacy_etf_exit_pending",
                        "pending_reason": pending_reason,
                        "thesis_full": {
                            "summary": rationale,
                            "why_now": "Strict US Brain common-stock-only mandate.",
                            "bull": [],
                            "bear": [],
                        },
                    }
                )
        projection["paths"] = build_portfolio.write(
            payload, portfolio_id=PORTFOLIO_ID
        )
        projection["published_ok"] = True
    except Exception as exc:  # noqa: BLE001 - surface the projection gap without inventing state
        projection["publish_error"] = repr(exc)[:240]
    return projection


def migrate(
    asof: str | None = None,
    *,
    apply: bool = False,
    market_open: bool | None = None,
    prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Plan or apply the explicit legacy-ETF exit.

    Dry-run is the default and writes nothing.  Apply is queue-only even during
    market hours: only the scheduled open-settlement path may source trusted
    Polygon/Yahoo/open marks and create simulated fills.
    """
    from bot import settle

    plan = build_plan(asof)
    plan["apply"] = bool(apply)
    if not apply or not plan.get("ok") or plan.get("status") == "already_complete":
        return plan

    if market_open is None:
        market_open = settle.is_open(PORTFOLIO_ID)
    plan["observed_market_open"] = bool(market_open)
    plan["operator_execution_mode"] = "queue_only"

    # Re-read executable queue authority after planning and immediately before
    # durable authorization.  A nightly/overnight writer may have created a
    # valid stock target in that gap; this operator action must never replace it.
    from portfolio import paper_account

    current_pending_path = paper_account._pending_target_path(PORTFOLIO_ID)
    if current_pending_path.exists():
        current_pending = _pending_payload()
        if _equivalent_pending(current_pending, plan):
            return {**plan, "status": "already_queued", "queued": True, "executed": []}
        try:
            current_pending_sha256 = hashlib.sha256(
                current_pending_path.read_bytes()
            ).hexdigest()
        except OSError:
            current_pending_sha256 = None
        return {
            **plan,
            "ok": False,
            "status": "blocked_non_equivalent_pending_target",
            "existing_pending_sha256": current_pending_sha256,
            "existing_pending_asof": (
                current_pending.get("asof")
                if isinstance(current_pending, dict)
                else None
            ),
            "pending_recheck_stage": "pre_authorization",
            "note": (
                "Executable queue authority changed after migration planning; "
                "the new target was preserved byte-for-byte."
            ),
        }

    # Re-read immediately before granting executable authority.  Planning itself is
    # read-only; any concurrent account transition invalidates the plan.
    try:
        current_account, current_sha = _read_account_snapshot()
        current_held = _held_lots(current_account)
        current_positions_sha256 = paper_account.positions_sha256(current_held)
    except MigrationFreeze as exc:
        return {**plan, "ok": False, "status": "blocked_account_changed", "error": str(exc)}
    except paper_account.InvalidExecutionConstraints as exc:
        return {
            **plan,
            "ok": False,
            "status": "blocked_positions_changed",
            "error": exc.reason,
        }
    if current_positions_sha256 != plan["positions_sha256"]:
        return {
            **plan,
            "ok": False,
            "status": "blocked_positions_changed",
            "observed_positions_sha256": current_positions_sha256,
            "positions_recheck_stage": "pre_authorization",
        }
    if current_sha != plan["account_sha256"]:
        return {
            **plan,
            "ok": False,
            "status": "blocked_account_changed",
            "observed_account_sha256": current_sha,
        }

    now = datetime.now(UTC).isoformat()
    attempt_id = _sha256(
        {
            "migration_id": plan["migration_id"],
            "authorized_at": now,
            "account_sha256": plan["account_sha256"],
        }
    )
    authorization = {
        "schema": MIGRATION_SCHEMA,
        "event": "migration_authorized",
        "attempt_id": attempt_id,
        "migration_id": plan["migration_id"],
        "authorized_at": now,
        "portfolio_id": PORTFOLIO_ID,
        "paper_only": True,
        "account_sha256": plan["account_sha256"],
        "target_sha256": _sha256(plan["target"]),
        "execution_constraints": plan["execution_constraints"],
        "legacy_etfs": plan["legacy_etfs"],
        "preserved_common_stocks": plan["common_stocks"],
        "observed_market_open": bool(market_open),
        "operator_execution_mode": "queue_only",
    }
    try:
        _append_audit(authorization)
    except Exception as exc:  # noqa: BLE001 - no executable action without durable authorization
        return {
            **plan,
            "ok": False,
            "status": "blocked_audit_write_failed",
            "error": repr(exc)[:240],
        }
    governance_event_id = _governance_event(plan, attempt_id)

    execution_prices = dict(plan.get("observed_prices") or {})
    if prices is not None:
        execution_prices = {
            str(ticker).upper().strip(): float(value)
            for ticker, value in prices.items()
            if not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) > 0.0
        }

    # Last possible operator-side check before the queue write.  The lower
    # settlement boundary independently enforces the same digest, so a later
    # race remains non-executable rather than silently resizing a changed book.
    try:
        final_account, _ = _read_account_snapshot()
        final_positions_sha256 = paper_account.positions_sha256(
            _held_lots(final_account)
        )
    except (MigrationFreeze, paper_account.InvalidExecutionConstraints) as exc:
        final_positions_sha256 = None
        final_positions_error = str(exc)
    else:
        final_positions_error = None
    if final_positions_sha256 != plan["positions_sha256"]:
        aborted = {
            "schema": MIGRATION_SCHEMA,
            "event": "migration_aborted",
            "attempt_id": attempt_id,
            "migration_id": plan["migration_id"],
            "recorded_at": datetime.now(UTC).isoformat(),
            "portfolio_id": PORTFOLIO_ID,
            "paper_only": True,
            "status": "blocked_positions_changed",
            "expected_positions_sha256": plan["positions_sha256"],
            "observed_positions_sha256": final_positions_sha256,
            "error": final_positions_error,
            "positions_recheck_stage": "immediate_pre_save",
        }
        try:
            _append_audit(aborted)
        except Exception:  # noqa: BLE001 - queue remains untouched either way
            pass
        return {
            **plan,
            "ok": False,
            "status": "blocked_positions_changed",
            "attempt_id": attempt_id,
            "governance_event_id": governance_event_id,
            "observed_positions_sha256": final_positions_sha256,
            "positions_recheck_stage": "immediate_pre_save",
            "error": final_positions_error,
        }
    result = settle.execute_or_queue(
        PORTFOLIO_ID,
        plan["target"],
        execution_prices,
        plan["asof"],
        # Operator scripts never choose a paper fill mark.  Persist the exact
        # instruction even if invoked during an open session; settle_open owns
        # the next trusted open-price observation and simulated fill.
        market_open=False,
        decision_snapshot=plan["submission"],
        execution_constraints=plan["execution_constraints"],
        require_pending_absent=True,
    )
    cas_conflict = result.get("skipped") == "pending_target_cas_conflict"
    outcome_status = "queued" if result.get("queued") else "executed"
    if cas_conflict:
        outcome_status = "blocked"
    elif result.get("skipped") or result.get("error"):
        outcome_status = "retained_for_retry" if result.get("pending_retained") else "blocked"
    target_status = None
    if result.get("queued") or (result.get("pending_retained") and not cas_conflict):
        target_status = "queued"
    elif not result.get("skipped") and not result.get("error"):
        target_status = "executed"

    projection = None
    if target_status in {"queued", "executed"}:
        projection = _publish_accepted_migration(
            plan,
            result,
            target_status=target_status,
            attempt_id=attempt_id,
            execution_prices=execution_prices,
            finalization=None,
        )
    finalization = None
    outcome = {
        "schema": MIGRATION_SCHEMA,
        "event": "migration_outcome",
        "attempt_id": attempt_id,
        "migration_id": plan["migration_id"],
        "recorded_at": datetime.now(UTC).isoformat(),
        "portfolio_id": PORTFOLIO_ID,
        "paper_only": True,
        "status": outcome_status,
        "queued": bool(result.get("queued")),
        "pending_retained": bool(result.get("pending_retained")),
        "executed": result.get("executed") or [],
        "skipped": result.get("skipped"),
        "error": result.get("error"),
        "target_status": target_status,
        "decision_log_ok": (projection or {}).get("decision_log_ok"),
        "published_ok": (projection or {}).get("published_ok"),
        "settlement_finalization": finalization,
    }
    try:
        _append_audit(outcome)
        audit_outcome_recorded = True
    except Exception:  # noqa: BLE001 - decision snapshot/fills remain durable provenance
        audit_outcome_recorded = False
    return {
        **plan,
        "status": outcome_status,
        "attempt_id": attempt_id,
        "governance_event_id": governance_event_id,
        "audit_outcome_recorded": audit_outcome_recorded,
        "target_status": target_status,
        "projection": projection,
        "settlement_finalization": finalization,
        **result,
    }
