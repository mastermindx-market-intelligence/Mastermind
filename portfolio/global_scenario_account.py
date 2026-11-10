"""Read-only adapter from a supplied native paper account to hypothetical scenarios.

Registry, instrument identity and paper-account valuation retain their ownership.
The caller must already be authorized to read this account and provide its exact
snapshot receipt, mandate, price observations and risk grouping evidence. This
module is NOT an account-authentication endpoint, book reader/writer, allocator,
quote collector, FX converter or policy activator. No absent value is imputed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any

from portfolio import global_scenario_context, global_scenario_summary, instrument_policy, paper_account, registry

SCHEMA = "mastermind.global_scenario_account/v1"
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,19}\Z")
_MAX_ROWS = 100
_LIMITS = ("max_instrument_weight", "max_risk_key_weight", "max_turnover_fraction", "min_cash_fraction")


def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 128 and value.strip() == value


def _number(value: Any, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and (result > 0 if positive else result >= 0) else None
    except (ValueError, OverflowError):
        return None


def _clock(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _window(value: Mapping, now: datetime) -> tuple[datetime, datetime] | None:
    known, expiry = _clock(value.get("known_at")), _clock(value.get("valid_until"))
    return (known, expiry) if known is not None and expiry is not None and known <= now < expiry else None


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    if len(payload) > 2_000_000:
        raise ValueError("bounded_evidence_required")
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _result(reason: str, at: str) -> dict:
    return {"schema": SCHEMA, "as_of": at, "status": "UNAVAILABLE", "reasons": [reason],
            "comparison": None, "display_only": True, "hypothetical_only": True,
            "authority": dict(global_scenario_context.AUTHORITY), "no_predictive_claim": True}


def compare_account(*, portfolio_id: str, account: Mapping[str, Any],
                    prices: Mapping[str, Any], price_evidence: Mapping[str, Any],
                    snapshot: Mapping[str, Any], mandate: Mapping[str, Any],
                    universe: Sequence[Mapping[str, Any]],
                    alternatives: Sequence[Mapping[str, Any]],
                    scenarios: Sequence[Mapping[str, Any]], as_of: str) -> dict:
    """Value explicit held shares/cash through the native owner, then compare what-ifs.

    This first native adapter supports the active single-name-equity paper books
    (USD, CNY and HKD separately). No static FX or cross-currency mark is assumed.
    The existing identity policy refuses pooled products for these books even if
    a descriptive Risk Radar shows an attractive ETF return. Scenarios, costs and
    risk groupings remain caller-declared assumptions, never forecasts/approvals.

    snapshot: book_id, account_sha256 (canonical JSON), source_revision,
      valuation_session (YYYY-MM-DD), known_at, valid_until.
    mandate: book_id, revision, currency, known_at, valid_until, constraints
      containing the four explicit ceilings understood by the scenario core.
    universe rows: instrument_id, currency, risk_keys, risk_source_ref.
    held price evidence: source, source_revision, currency, observed_asof,
      price, price_basis='unadjusted_close', close_qualified=True,
      known_at, valid_until; native carry flags still apply.
    Every scenario explicitly supplies the same period_start / period_end, with
    period_start equal to as_of and period_end later. No horizon is guessed.
    """
    now = _clock(as_of)
    if now is None:
        raise global_scenario_context.ContractError("aware_as_of_required")
    at = now.isoformat().replace("+00:00", "Z")
    missing = lambda reason: _result(reason, at)
    if any(not isinstance(value, Mapping) for value in (account, prices, price_evidence, snapshot, mandate)):
        return missing("mapping_inputs_required")
    if (not isinstance(universe, (list, tuple)) or len(universe) > _MAX_ROWS
            or not isinstance(scenarios, (list, tuple)) or not scenarios or len(scenarios) > 30
            or not isinstance(alternatives, (list, tuple)) or len(alternatives) > 30):
        return missing("bounded_scenario_inputs_required")
    try:
        pid = registry.canonical_id(portfolio_id)
    except (ValueError, TypeError):
        return missing("book_identity_unqualified")
    if not registry.is_active(pid) or registry.asset_policy(pid) != instrument_policy.POLICY_NAME:
        return missing("native_book_policy_unsupported")
    currency = registry.currency(pid)
    if snapshot.get("book_id") != pid or mandate.get("book_id") != pid:
        return missing("book_receipt_mismatch")
    if mandate.get("currency") != currency:
        return missing("mandate_currency_mismatch")
    if not _text(snapshot.get("source_revision")) or not _text(mandate.get("revision")):
        return missing("source_revision_missing")
    windows = [_window(snapshot, now), _window(mandate, now)]
    if any(window is None for window in windows):
        return missing("book_or_mandate_clock_unqualified")
    session = snapshot.get("valuation_session")
    try:
        session_day = date.fromisoformat(session)
        if session_day.isoformat() != session or session_day > now.date():
            return missing("valuation_session_invalid")
    except (ValueError, TypeError):
        return missing("valuation_session_invalid")
    if paper_account.validate_account_state(account):
        return missing("native_account_schema_invalid")
    positions = account["positions"]
    if len(positions) > _MAX_ROWS or _number(account["cash"]) is None:
        return missing("fully_funded_long_only_required")
    try:
        account_digest = _hash(account)
    except (ValueError, TypeError, RecursionError):
        return missing("account_evidence_invalid")
    if snapshot.get("account_sha256") != account_digest:
        return missing("account_revision_mismatch")
    constraints = mandate.get("constraints")
    if not isinstance(constraints, Mapping) or any(
            _number(constraints.get(k)) is None or constraints[k] > 1 for k in _LIMITS):
        return missing("explicit_mandate_limits_required")

    native_universe, identities, seen = [], {}, set()
    for row in universe:
        if not isinstance(row, Mapping):
            return missing("instrument_metadata_invalid")
        key = row.get("instrument_id")
        if not isinstance(key, str) or not _SYMBOL.fullmatch(key) or key in seen:
            return missing("instrument_identity_ambiguous")
        seen.add(key)
        if row.get("currency") != currency:
            return missing("cross_currency_mark_not_supported")
        groups = row.get("risk_keys")
        if (not isinstance(groups, (list, tuple)) or not groups or len(groups) > 16
                or not all(_text(group) for group in groups) or not _text(row.get("risk_source_ref"))):
            return missing("risk_group_evidence_missing")
        identity = instrument_policy.classify_instrument(pid, key)
        if (not isinstance(identity, dict) or identity.get("ticker") != key
                or identity.get("kind") != "common_stock" or identity.get("verified") is not True
                or (pid in {"china", "hk"} and identity.get("market") != pid)):
            return missing("native_instrument_policy_unqualified")
        identities[key] = identity
        native_universe.append({"instrument_id": key, "currency": currency,
                                "eligibility": "QUALIFIED", "policy_ref": instrument_policy.POLICY_VERSION,
                                "risk_keys": sorted(set(groups))})

    held_prices, held_evidence = {}, {}
    for key, position in positions.items():
        if not isinstance(key, str) or not _SYMBOL.fullmatch(key) or _number(position["shares"]) is None:
            return missing("fully_funded_long_only_required")
        if position["shares"] == 0:
            continue
        if key not in seen:
            return missing("held_instrument_metadata_missing")
        price, evidence = _number(prices.get(key), positive=True), price_evidence.get(key)
        if price is None or not isinstance(evidence, Mapping):
            return missing("held_price_evidence_missing")
        if (_number(evidence.get("price"), positive=True) != price
                or evidence.get("currency") != currency or evidence.get("observed_asof") != session
                or evidence.get("close_qualified") is not True
                or evidence.get("price_basis") != "unadjusted_close"
                or not _text(evidence.get("source")) or not _text(evidence.get("source_revision"))):
            return missing("held_price_basis_unqualified")
        window = _window(evidence, now)
        if window is None:
            return missing("held_price_clock_unqualified")
        windows.append(window)
        held_prices[key], held_evidence[key] = price, dict(evidence)

    horizon = None
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            return missing("scenario_shape_invalid")
        start, end = _clock(scenario.get("period_start")), _clock(scenario.get("period_end"))
        if start != now or end is None or end <= start:
            return missing("explicit_scenario_horizon_required")
        if horizon is not None and horizon != (start, end):
            return missing("scenario_horizon_mismatch")
        horizon = (start, end)

    # This native function is pure when state is supplied. Never call its mark,
    # load-account, recovery or account-creation paths from a what-if request.
    valuation = paper_account.valuation(held_prices, session, pid,
                                       price_evidence=held_evidence, state=copy.deepcopy(dict(account)))
    if (valuation.get("nav_status") != "QUALIFIED"
            or _number(valuation.get("nav"), positive=True) is None):
        return missing("native_valuation_not_qualified")
    nav = valuation["nav"]
    weights = {key: line["value"] / nav for key, line in valuation["lines"].items()}
    cash_weight = valuation["cash"] / nav
    known = max(window[0] for window in windows)
    valid_until = min(window[1] for window in windows)
    try:
        revision = _hash({"account": account_digest, "snapshot": dict(snapshot), "mandate": dict(mandate),
                          "universe": sorted((dict(row) for row in universe), key=lambda row: row["instrument_id"]),
                          "identities": identities, "prices": held_prices, "price_evidence": held_evidence})
    except (ValueError, TypeError, RecursionError):
        return missing("book_evidence_invalid")
    book = {"book_id": pid, "book_revision": revision, "base_currency": currency,
            "known_at": known.isoformat(), "valid_until": valid_until.isoformat(),
            "positions": weights, "cash_weight": cash_weight,
            "universe": sorted(native_universe, key=lambda row: row["instrument_id"]),
            "constraints": {k: constraints[k] for k in _LIMITS}}
    comparison = global_scenario_summary.compare_with_hold_baseline(book, alternatives, scenarios, as_of=at)
    return {"schema": SCHEMA, "as_of": at, "status": comparison["status"],
            "reasons": comparison.get("reasons", []), "comparison": comparison,
            "valuation_session": session, "valuation_status": "QUALIFIED",
            "valuation_owner": "portfolio.paper_account.valuation", "held_positions": len(weights),
            "base_currency": currency, "instrument_policy": instrument_policy.POLICY_VERSION,
            "scenario_window": {"start": horizon[0].isoformat(), "end": horizon[1].isoformat()},
            "display_only": True, "hypothetical_only": True, "no_predictive_claim": True,
            "authority": dict(global_scenario_context.AUTHORITY)}
