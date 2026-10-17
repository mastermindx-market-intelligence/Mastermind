"""Read-only availability of persisted Brain decisions and paper-account facts.

This is a display projection, not a new decision/target/account lifecycle. It never
recovers a transaction, obtains a quote, repairs an artifact, or calls a model.
Each source is bounded and read strictly; absence is not an empty/fresh account.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.decision_availability_selection import select_decision_records

SCHEMA = "mastermind.bot.decision_availability.v1"
ACTIVE_BOOKS = frozenset({"autonomous", "china", "hk"})
_MAX_BYTES = 16_000_000
_MAX_ROWS = 2_048
_MAX_SUMMARY = 12_000
_ID = re.compile(r"[A-Za-z0-9_.:+-]{1,160}\Z")
_TICKER = re.compile(r"[A-Z0-9.-]{1,16}\Z")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (OverflowError, ValueError):
        return None


def _day(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return value if date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _identity(value: Any) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("nonfinite_json_number")


def _parse(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_strict_object,
                      parse_constant=_invalid_constant)


def _signature(path: Path) -> tuple | None:
    try:
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    except FileNotFoundError:
        return None


def _read(path: Path, *, lines: bool = False) -> tuple[Any, dict, tuple | None]:
    """Never skip a bad row without qualifying the source that remains."""
    source: dict = {"file": path.name, "status": "missing", "sha256": None,
                    "modified_at": None, "issues": []}
    signature = None
    try:
        signature = _signature(path)
        if signature is None:
            return (None, source, None)
        if signature[2] > _MAX_BYTES:
            source.update(status="invalid", issues=["source_too_large"])
            return (None, source, signature)
        with path.open("rb") as handle:
            raw = handle.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            source.update(status="invalid", issues=["source_too_large"])
            return (None, source, signature)
        source.update(
            sha256=hashlib.sha256(raw).hexdigest(),
            modified_at=datetime.fromtimestamp(signature[3] / 1e9, timezone.utc).isoformat(),
        )
        if lines:
            nonempty = [line for line in raw.splitlines() if line.strip()]
            if len(nonempty) > _MAX_ROWS:
                source.update(status="invalid", issues=["source_too_many_rows"])
                return (None, source, signature)
            rows = []
            bad = False
            for line in nonempty:
                try:
                    value = _parse(line)
                    if not isinstance(value, dict):
                        raise ValueError("row_not_object")
                    rows.append(value)
                except (ValueError, UnicodeError, RecursionError):
                    bad = True
            source.update(status=("partial" if rows else "invalid") if bad else "available",
                          issues=["invalid_rows"] if bad else [], row_count=len(rows))
            return (rows, source, signature)
        value = _parse(raw)
        if not isinstance(value, dict):
            raise ValueError("source_not_object")
        source["status"] = "available"
        return (value, source, signature)
    except (ValueError, UnicodeError, RecursionError):
        source.update(status="invalid", issues=["invalid_json"])
    except OSError:
        source.update(status="unavailable", issues=["source_unreadable"])
    return (None, source, signature)


def _decision(row: dict | None) -> dict | None:
    """Publish an allowlist; raw adapter errors, brain traces, and prompts stay private."""
    if row is None:
        return None
    summary = row.get("summary")
    summary_zh = row.get("summary_zh")
    result = {key: _identity(row.get(key)) for key in
              ("decision_id", "run_id", "target_status", "submission_sha256", "target_sha256")}
    result.update(
        asof=_day(row.get("asof")),
        ts=row.get("ts") if isinstance(row.get("ts"), str) and len(row["ts"]) <= 64 else None,
        decision_effective=row.get("decision_effective") is True,
        summary=summary[:_MAX_SUMMARY] if isinstance(summary, str) else None,
        summary_zh=summary_zh[:_MAX_SUMMARY] if isinstance(summary_zh, str) else None,
        summary_truncated=any(isinstance(text, str) and len(text) > _MAX_SUMMARY
                              for text in (summary, summary_zh)),
        submitted_holding_count=len(row["holdings"]) if isinstance(row.get("holdings"), list) else None,
        error_present=bool(row.get("error")),
    )
    return result


def _account(raw: dict | None, status: str, *, today: str) -> dict:
    result: dict = {"status": status, "cash": None, "positions": [],
                    "position_count": None, "effective_at": None,
                    "state_time_status": "unavailable", "issues": [],
                    "valuation": {"status": "unavailable", "nav": None, "invested": None,
                                  "gross_exposure": None, "cash_weight": None,
                                  "price_date_from": None, "price_date_through": None,
                                  "missing_tickers": [], "basis": "persisted_lot_marks"}}
    if raw is None:
        return result
    cash = _number(raw.get("cash"))
    positions = raw.get("positions")
    if cash is None:
        result["issues"].append("cash_invalid")
    elif cash < 0:
        result["issues"].append("cash_negative")
    result["cash"] = cash
    if not isinstance(positions, dict):
        result.update(status="invalid", issues=result["issues"] + ["positions_invalid"])
        return result
    complete = True
    priced = True
    prices_dates: list[str] = []
    values: list[float] = []
    for ticker, lot in sorted(positions.items()):
        if not _TICKER.fullmatch(ticker) or not isinstance(lot, dict):
            complete = False
            continue
        shares = _number(lot.get("shares"))
        if shares is None or shares < 0:
            complete = False
            continue
        if shares == 0:
            continue
        row = {"ticker": ticker, "shares": shares, "price": None,
               "price_asof": None, "price_source": None, "market_value": None}
        price = _number(lot.get("current_price"))
        asof = _day(lot.get("current_price_asof"))
        source = _identity(lot.get("current_price_source"))
        kind = lot.get("current_price_time_kind")
        value = shares * price if price is not None else None
        if (price is not None and price > 0 and asof and asof <= today and source
                and kind == "portfolio_mark_date" and value is not None and math.isfinite(value)):
            row.update(price=price, price_asof=asof, price_source=source, market_value=value)
            prices_dates.append(asof)
            values.append(value)
        else:
            priced = False
            result["valuation"]["missing_tickers"].append(ticker)
        result["positions"].append(row)
    result["position_count"] = len(result["positions"]) if complete else None
    if not complete:
        result["issues"].append("position_rows_invalid")
    result["status"] = "available" if cash is not None and cash >= 0 and complete else "partial"
    if complete and priced and cash is not None and cash >= 0:
        try:
            invested = math.fsum(values)
            nav = cash + invested
            if not math.isfinite(nav):
                raise OverflowError
            result["valuation"].update(
                status="provisional" if prices_dates else "cash_only",
                nav=nav, invested=invested,
                gross_exposure=invested / nav if nav > 0 else None,
                cash_weight=cash / nav if nav > 0 else None,
                price_date_from=min(prices_dates) if prices_dates else None,
                price_date_through=max(prices_dates) if prices_dates else None,
            )
        except OverflowError:
            result["issues"].append("valuation_overflow")
    return result


def _recorded_nav(rows: list | None, status: str, *, today: str, portfolio_id: str) -> dict:
    result: dict = {"status": status, "date": None, "nav": None, "cash": None,
                    "invested": None, "account_binding": "unavailable", "issues": []}
    if rows is None:
        return result
    by_date: dict[str, list[dict]] = {}
    for row in rows:
        if any(row.get(key) not in (None, portfolio_id) for key in ("portfolio_id", "book")):
            result["issues"].append("nav_portfolio_identity_mismatch")
            continue
        day = _day(row.get("date"))
        nav = _number(row.get("nav"))
        if not day or day > today or nav is None or nav < 0:
            result["issues"].append("invalid_or_future_nav_row")
            continue
        selected = {key: _number(row.get(key)) for key in ("nav", "cash", "invested")}
        selected["date"] = day
        group = by_date.setdefault(day, [])
        if selected not in group:
            group.append(selected)
    if not by_date:
        result["status"] = "invalid" if rows else status
        return result
    latest = by_date[max(by_date)]
    if len(latest) != 1:
        result.update(status="partial", issues=["ambiguous_latest_nav"])
        return result
    result.update(latest[0], status="provisional")
    if result["cash"] is None or result["invested"] is None:
        result["issues"].append("nav_components_missing")
    elif abs(result["cash"] + result["invested"] - result["nav"]) > 0.03:
        result["issues"].append("nav_components_mismatch")
    result["issues"] = sorted(set(result["issues"]))
    # This historical mark has no digest binding it to the current account bytes.
    # Never promote it to the current account valuation or an execution receipt.
    return result


def _weights(row: dict | None) -> dict | None:
    """Only the persisted deterministic effective target supplies numeric weights."""
    holdings = row.get("effective_holdings") if row else None
    if not isinstance(holdings, list):
        return None
    target = {}
    for holding in holdings:
        if not isinstance(holding, dict):
            return None
        ticker = holding.get("ticker")
        weight = _number(holding.get("weight"))
        if (not isinstance(ticker, str) or not _TICKER.fullmatch(ticker) or ticker in target
                or weight is None or not 0 <= weight <= 1):
            return None
        target[ticker] = weight
    return target if math.fsum(target.values()) <= 1 else None


def _target(row: dict | None, pending: dict | None, pending_status: str, *,
            portfolio_id: str, observed: datetime,
            verify_receipt: Callable, validate_pending: Callable) -> dict:
    weights = _weights(row)
    result: dict = {
        "decision_id": _identity(row.get("decision_id")) if row else None,
        "target_status": _identity(row.get("target_status")) if row else None,
        "weights": weights, "weights_status": "available" if weights is not None else "unavailable",
        "gross_exposure": math.fsum(weights.values()) if weights is not None else None,
        "execution_evidence": "unavailable", "settled_asof": None,
        "execution_verification_scope": "decision_row_identity_only",
        "durable_ledger_status": "not_checked",
        "settlement_transaction_id": None, "fill_count": None,
        "pending": {"status": "none" if pending_status == "missing" else pending_status,
                    "lineage_status": "unavailable", "clock_status": "unavailable",
                    "target": None, "queued_at": None,
                    "asof": None, "decision_id": None},
    }
    if row:
        if row.get("target_status") == "queued":
            result["execution_evidence"] = "not_settled"
        elif verify_receipt(row):
            result.update(
                execution_evidence="receipt_identity_verified", settled_asof=_day(row.get("settled_asof")),
                settlement_transaction_id=_identity(row.get("settlement_transaction_id")),
                fill_count=len(row["settlement_fill_ids"]),
            )
        else:
            result["execution_evidence"] = "unverified"
    if pending is None:
        return result
    if any(pending.get(key) not in (None, portfolio_id) for key in ("portfolio_id", "book")):
        result["pending"]["status"] = "invalid"
        return result
    try:
        error = validate_pending(pending, portfolio_id)
    except Exception:  # A failed read/validator is unavailable, not proof of an invalid queue.
        result["pending"]["status"] = "unavailable"
        return result
    if error:
        result["pending"]["status"] = "invalid"
        return result
    snapshot = pending.get("decision_snapshot") or {}
    if not isinstance(snapshot, dict):
        result["pending"]["status"] = "invalid"
        return result
    queue = result["pending"]
    queue.update(status="queued", target=dict(sorted(pending["target"].items())),
                 queued_at=pending.get("queued_at") if isinstance(pending.get("queued_at"), str)
                 and len(pending["queued_at"]) <= 64 else None,
                 asof=_day(pending.get("asof")),
                 decision_id=_identity(snapshot.get("decision_id")))
    queued_time = _instant(pending.get("queued_at"))
    queue_day = _day(pending.get("asof"))
    if (("queued_at" in pending and (queued_time is None or queued_time > observed))
            or ("asof" in pending and (queue_day is None
                or queue_day > observed.astimezone(timezone.utc).date().isoformat()))):
        queue["clock_status"] = "invalid"
    else:
        queue["clock_status"] = "available" if queued_time and queue_day else "partial"
    pairs = [(snapshot.get("decision_id"), row.get("decision_id") if row else None),
             (snapshot.get("target_sha256"), row.get("target_sha256") if row else None)]
    if any(a and b and a != b for a, b in pairs):
        queue["lineage_status"] = "conflict"
    elif all(a and b and a == b for a, b in pairs):
        queue["lineage_status"] = "matched"
    else:
        queue["lineage_status"] = "partial"
    return result


def read_decision_availability(
    portfolio_id: str, *, base_dir: Path, observed_at: str,
    verify_receipt: Callable[[dict], bool],
    validate_pending: Callable[[dict, str], str | None],
) -> dict:
    """Read canonical book files, retaining independent clocks and coverage."""
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must include timezone")
    today = observed.astimezone(timezone.utc).date().isoformat()
    if portfolio_id not in ACTIVE_BOOKS:
        return {"schema": SCHEMA, "portfolio_id": portfolio_id, "observed_at": observed_at,
                "status": "not_applicable"}
    sources = {}
    signatures = {}
    data = {}
    for key, filename, lines in (
        ("decisions", "decisions.jsonl", True),
        ("account", "account.json", False),
        ("pending_target", "pending_target.json", False),
        ("nav_history", "nav_history.jsonl", True),
    ):
        data[key], sources[key], signatures[key] = _read(base_dir / filename, lines=lines)
    wal_path = base_dir / "paper_transaction.json"
    try:
        wal_signature = _signature(wal_path)
        transaction_status = "present" if wal_signature else "absent"
    except OSError:
        wal_signature = None
        transaction_status = "unavailable"
    selection = select_decision_records(
        portfolio_id, data["decisions"], observed_at=observed_at,
        history_status=sources["decisions"]["status"],
    )
    account_raw = data["account"]
    if account_raw and any(account_raw.get(key) not in (None, portfolio_id)
                           for key in ("portfolio_id", "book")):
        account_raw = None
        sources["account"].update(status="invalid", issues=["portfolio_identity_mismatch"])
    account = _account(account_raw, sources["account"]["status"], today=today)
    account["last_recorded_nav"] = _recorded_nav(
        data["nav_history"], sources["nav_history"]["status"], today=today, portfolio_id=portfolio_id)
    target = _target(selection["last_valid"], data["pending_target"],
                     sources["pending_target"]["status"], portfolio_id=portfolio_id, observed=observed,
                     verify_receipt=verify_receipt, validate_pending=validate_pending)
    issues = set(selection["issues"])
    issues.update("account_" + issue for issue in account["issues"])
    issues.update("nav_" + issue for issue in account["last_recorded_nav"]["issues"])
    if target["pending"]["status"] == "invalid":
        issues.add("pending_target_invalid")
    if target["pending"]["clock_status"] == "invalid":
        issues.add("pending_target_clock_invalid")
    if target["target_status"] == "queued" and target["pending"]["status"] == "none":
        issues.add("queued_decision_without_pending_target")
    changed = []
    for key, signature in signatures.items():
        try:
            if _signature(base_dir / sources[key]["file"]) != signature:
                changed.append(key)
        except OSError:
            changed.append(key)
    try:
        if _signature(wal_path) != wal_signature:
            changed.append("paper_transaction")
    except OSError:
        changed.append("paper_transaction")
    if changed:
        issues.add("sources_changed_during_read")
    if transaction_status == "present":
        issues.add("paper_transaction_pending")
    elif transaction_status == "unavailable":
        issues.add("paper_transaction_status_unavailable")
    consistency = ("changed_during_read" if changed else
                   "transaction_pending" if transaction_status == "present" else
                   "unknown" if transaction_status == "unavailable" else "observed_stable")
    if consistency != "observed_stable" and account["status"] == "available":
        account["status"] = "provisional"
    if target["pending"]["lineage_status"] == "conflict":
        issues.add("pending_decision_lineage_conflict")
    for key, source in sources.items():
        if source["status"] not in {"available", "missing"}:
            issues.add(key + "_source_" + source["status"])
    return {
        "schema": SCHEMA, "portfolio_id": portfolio_id, "observed_at": observed_at,
        "status": "partial" if issues or selection["attempt_coverage"] != "complete" else "available",
        "history_status": selection["coverage_status"],
        "attempt_coverage": selection["attempt_coverage"],
        "origin_lineage_status": selection["origin_lineage_status"],
        "last_valid_decision": _decision(selection["last_valid"]),
        "latest_attempt": _decision(selection["latest_attempt"]),
        "latest_attempt_kind": selection["latest_attempt_kind"],
        "expected_opportunity": {"status": "unknown", "reason": "scheduler_evidence_not_bound"},
        "accepted_target": target, "account": account, "sources": sources,
        "consistency": {"status": consistency, "transaction": transaction_status,
                        "changed_sources": sorted(changed)},
        "issues": sorted(issues),
    }
