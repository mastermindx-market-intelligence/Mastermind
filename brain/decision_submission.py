"""Trusted normalization for regional Brain target-book submissions.

The reasoning model selects names and expresses ordinal intent.  This boundary
owns every numeric target, preserves positions when a decision is ambiguous,
and records requested actions separately from actions that may actually reach
the paper-account rebalance.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_EXIT_ACTIONS = {"exit", "sell", "close"}
_HOLDING_ACTIONS = {"add", "hold", "trim"}
_TRIM_FACTORS = {"light": 0.80, "standard": 0.60, "deep": 0.35}
_EARLY_EXIT_CODES = {
    "hard_falsifier",
    "technical_break",
    "material_thesis_change",
    "risk_limit",
    "fraud_or_delisting",
    "stop_breach",
    "legacy_instrument_migration",
}
_MEMO_FIELDS = (
    "market_frame",
    "candidate_funnel",
    "selected",
    "rejected",
    "changes",
    "timing",
    "risk_deliberation",
    "alternatives",
    "lessons_applied",
    "context_gaps",
    "delegation_summary",
)
_TOP_FIELDS = (
    "mandate",
    "falsifiers",
    "evidence_planes",
    "source_provenance",
    "liquidity_notes",
    "expected_failure_mode",
    "cash_rationale",
    "risk_posture",
    "decision_memo",
)
_HOLDING_LOG_FIELDS = (
    "ticker",
    "venue",
    "weight",
    "prior_target_weight",
    "proposed_weight",
    "weight_source",
    "conviction",
    "action_requested",
    "action_effective",
    "trim_intensity",
    "trim_anchor_weight",
    "rationale",
    "why_now",
    "falsifier",
    "evidence",
    "source_provenance",
    "expected_horizon",
    "exit_plan",
    "carried_forward",
    "carry_reason",
    "quarantined",
    "quarantine_reason",
    "identity_status",
    "holding_mark_source",
)
ACCEPTED_TARGET_STATUSES = frozenset({"executed", "queued"})


class DecisionBoundaryFreeze(RuntimeError):
    """The current book cannot be reconstructed safely; preserve it unchanged."""


def enhance_schema(schema: dict) -> dict:
    """Upgrade a regional desk schema with the shared audited action contract."""
    out = json.loads(json.dumps(schema))
    props = out.setdefault("properties", {})
    item = props.setdefault("holdings", {}).setdefault("items", {})
    hp = item.setdefault("properties", {})
    hp.update(
        {
            "action": {
                "type": "string",
                "enum": ["add", "hold", "trim"],
                "description": "Ordinal intent. The trusted allocator, not this payload, owns size.",
            },
            "trim_intensity": {
                "type": "string",
                "enum": ["light", "standard", "deep"],
                "description": "Required in practice for TRIM; converted to a deterministic reduction.",
            },
            "why_now": {"type": "string"},
            "falsifier": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "source_provenance": {"type": "array", "items": {"type": "string"}},
            "expected_horizon": {"type": "string"},
            "exit_plan": {"type": "string"},
        }
    )
    if "weight" in hp:
        hp["weight"]["description"] = (
            "Optional advisory fraction recorded for audit only; deterministic sizing ignores it."
        )
    required = [r for r in list(item.get("required") or []) if r != "weight"]
    item["required"] = list(
        dict.fromkeys(
            required
            + [
                "action",
                "conviction",
                "why_now",
                "falsifier",
                "evidence",
                "source_provenance",
                "expected_horizon",
                "exit_plan",
            ]
        )
    )
    props.update(
        {
            "exit_decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "action": {"type": "string", "enum": ["exit"]},
                        "reason": {"type": "string"},
                        "reason_code": {
                            "type": "string",
                            "enum": sorted(_EARLY_EXIT_CODES | {"thesis_change"}),
                        },
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "falsifier": {"type": "string"},
                        "why_now": {"type": "string"},
                    },
                    "required": [
                        "ticker",
                        "action",
                        "reason",
                        "reason_code",
                        "evidence",
                        "why_now",
                    ],
                },
            },
            "source_provenance": {"type": "array", "items": {"type": "string"}},
            "liquidity_notes": {"type": "string"},
            "risk_posture": {"type": "string", "enum": ["normal", "caution", "crash"]},
            "cash_rationale": {"type": "string"},
            "decision_memo": {
                "type": "object",
                "properties": {k: {} for k in _MEMO_FIELDS},
            },
        }
    )
    out["required"] = list(
        dict.fromkeys(
            list(out.get("required") or [])
            + [
                "exit_decisions",
                "falsifiers",
                "evidence_planes",
                "source_provenance",
                "expected_failure_mode",
                "risk_posture",
                "cash_rationale",
                "decision_memo",
            ]
        )
    )
    return out


def _clean_text(value: Any, limit: int = 4000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _json_value(value: Any, max_chars: int = 12000) -> Any:
    """Keep JSON-safe structured evidence bounded without flattening it to prose."""
    try:
        encoded = json.dumps(value, default=str, ensure_ascii=False)
        if len(encoded) <= max_chars:
            return json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError):
        pass
    return _clean_text(value, max_chars)


def _latest_holdings(book: str) -> dict[str, dict]:
    """Reconstruct the actual account book, using average cost when quotes are down.

    The account is the position authority.  Published rows only enrich its rationale.
    If even a conservative mark is unavailable for one held line, normalization freezes
    instead of accidentally treating the line as absent.
    """
    from portfolio import fx, paper_account, registry

    published: dict[str, dict] = {}
    prior_targets: dict[str, dict] = {}
    try:
        data_dir = registry.data_dir(book)
        payload = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
        for rec in payload.get("positions") or []:
            ticker = str(rec.get("ticker") or "").upper().strip()
            if ticker:
                published[ticker] = rec
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        pass
    try:
        lines = (
            (registry.data_dir(book) / "decisions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        for line in reversed(lines):
            record = json.loads(line)
            if (
                not isinstance(record, dict)
                or record.get("decision_effective") is not True
                or record.get("target_status") not in ACCEPTED_TARGET_STATUSES
                or not isinstance(record.get("effective_holdings"), list)
            ):
                continue
            for rec in record["effective_holdings"]:
                ticker = str((rec or {}).get("ticker") or "").upper().strip()
                if ticker and isinstance(rec, dict):
                    prior_targets[ticker] = rec
            if prior_targets:
                break
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        pass

    try:
        state = paper_account._load_account(book)
    except Exception as exc:
        raise DecisionBoundaryFreeze(f"account_unavailable:{book}") from exc
    held = state.get("positions")
    if not isinstance(held, dict):
        raise DecisionBoundaryFreeze(f"account_positions_invalid:{book}")
    if not held:
        return {}
    try:
        cash = float(state.get("cash") or 0.0)
    except (TypeError, ValueError) as exc:
        raise DecisionBoundaryFreeze(f"account_cash_invalid:{book}") from exc

    marked: dict[str, tuple[dict, float, float, str]] = {}
    currency = str(registry.currency(book) or "USD").upper()
    for raw_ticker, raw_rec in held.items():
        ticker = str(raw_ticker or "").upper().strip()
        if not ticker or not isinstance(raw_rec, dict):
            raise DecisionBoundaryFreeze(f"account_position_invalid:{raw_ticker}")
        try:
            shares = float(raw_rec.get("shares") or 0.0)
        except (TypeError, ValueError) as exc:
            raise DecisionBoundaryFreeze(f"account_shares_invalid:{ticker}") from exc
        if shares <= 0:
            continue
        price = None
        try:
            price = paper_account._current_price(ticker)
        except Exception:  # noqa: BLE001 - average cost is the conservative fallback
            price = None
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        if price is not None and currency != "USD":
            try:
                price = fx.usd_to(price, currency)
            except (AttributeError, TypeError, ValueError):
                price = None
        try:
            avg_cost = float(raw_rec.get("avg_cost"))
        except (TypeError, ValueError):
            avg_cost = 0.0
        mark_source = "live_quote"
        if price is None or not math.isfinite(price) or price <= 0:
            price = avg_cost
            mark_source = "account_avg_cost_fallback"
        if not math.isfinite(price) or price <= 0:
            raise DecisionBoundaryFreeze(f"unpriceable_held_position:{ticker}")
        marked[ticker] = (raw_rec, shares, price, mark_source)

    nav = cash + sum(shares * mark for _, shares, mark, _ in marked.values())
    if not math.isfinite(nav) or nav <= 0:
        raise DecisionBoundaryFreeze(f"conservative_nav_invalid:{book}")

    rows: dict[str, dict] = {}
    for ticker, (_, shares, mark, mark_source) in marked.items():
        old = prior_targets.get(ticker) or published.get(ticker) or {}
        actual_weight = shares * mark / nav
        prior_target_weight = old.get("weight")
        try:
            prior_target_weight = float(prior_target_weight)
        except (TypeError, ValueError):
            prior_target_weight = actual_weight
        if not math.isfinite(prior_target_weight) or prior_target_weight <= 0:
            prior_target_weight = actual_weight
        row = {
            "ticker": ticker,
            "weight": actual_weight,
            "prior_target_weight": prior_target_weight,
            "rationale": old.get("rationale")
            or (old.get("thesis_full") or {}).get("summary")
            or "Carried forward pending an explicit reviewed exit.",
            "conviction": old.get("conviction") or "medium",
            "holding_mark_source": mark_source,
        }
        for key in _HOLDING_LOG_FIELDS:
            if key not in row and old.get(key) is not None:
                row[key] = old.get(key)
        if old.get("venue"):
            row["venue"] = old.get("venue")
        rows[ticker] = row
    return rows


def _instrument_identity(ticker: str) -> dict[str, Any]:
    """Shared US instrument identity used by reasoning and execution boundaries."""
    from portfolio import instrument_policy

    return instrument_policy.classify_us_instrument(ticker)


def _mandate_migration_exit(ticker: str, identity: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, auditable exit for inherited ETFs in the stock-only US book."""
    status = _clean_text(identity.get("status"), 200) or "verified_etf"
    return {
        "ticker": ticker,
        "action": "exit",
        "reason": "Inherited ETF violates the US Brain common-stock-only mandate.",
        "reason_code": "legacy_instrument_migration",
        "evidence": [f"instrument_policy:{status}", "operator_directive:etfs_prohibited"],
        "falsifier": "None; ETF eligibility is prohibited by portfolio mandate.",
        "why_now": "Remove inherited pre-v2 ETF inventory at the next priceable paper session.",
        "authority": "deterministic_stock_only_mandate",
        "identity_status": status,
    }


def _held_sessions(
    book: str, ticker: str, asof: date | str | None = None
) -> int | None:
    """Count exchange sessions in the current open-position lifecycle, inclusive."""
    from portfolio import market_calendar, trade_history

    try:
        end = (
            date.fromisoformat(asof)
            if isinstance(asof, str)
            else (asof or datetime.now(UTC).date())
        )
        net = 0.0
        opened: date | None = None
        for fill in trade_history._load_fills(book):
            if str(fill.get("ticker") or "").upper().strip() != ticker.upper():
                continue
            shares = float(fill.get("shares") or 0.0)
            side = str(fill.get("side") or "").lower()
            fill_date = date.fromisoformat(str(fill.get("date")))
            if side == "buy" and shares > 0:
                if net <= 1e-9:
                    opened = fill_date
                net += shares
            elif side == "sell" and shares > 0:
                net = max(0.0, net - shares)
                if net <= 1e-9:
                    opened = None
        if opened is None or net <= 1e-9 or opened > end:
            return None
        count = 0
        cursor = opened
        while cursor <= end:
            if market_calendar.is_trading_day(cursor):
                count += 1
            cursor += timedelta(days=1)
        return count or None
    except (AttributeError, ImportError, KeyError, OSError, TypeError, ValueError):
        return None


def _clean_evidence(value: Any) -> Any:
    return _json_value(value if isinstance(value, list) else [])


def _has_evidence(value: Any) -> bool:
    return isinstance(value, list) and any(_clean_text(v, 500) for v in value)


def _sizing_policy(book: str, posture: str) -> dict[str, Any]:
    if book == "autonomous":
        return {
            "name": "deterministic_conviction_allocator.v2",
            "target_gross": {"normal": 0.80, "caution": 0.60, "crash": 0.25}[posture],
            "max_single": 0.15,
            "conviction_caps": {"high": 0.15, "medium": 0.10, "low": 0.05},
        }
    return {
        "name": "deterministic_incremental_regional_allocator.v1",
        "target_gross": {"normal": 0.85, "caution": 0.65, "crash": 0.30}[posture],
        "max_single": 0.18,
        "conviction_caps": {"high": 0.18, "medium": 0.12, "low": 0.06},
    }


def _quantize_executable_weights(
    holdings: list[dict], *, digits: int = 6
) -> dict[str, Any]:
    """Quantize a complete target without manufacturing leverage.

    Independently rounding every row can turn a valid nearly fully-invested book
    into an invalid one (for example, six 16.66666% HOLDs become 100.0002%).
    Use largest-remainder apportionment against the *floored aggregate* instead:
    this keeps the result deterministic and close to the original ratios while
    guaranteeing that quantization never increases gross exposure.  Sub-micro
    positive rows retain their original value rather than becoming accidental
    zero-weight exits.
    """
    scale = 10**digits
    rows: list[tuple[int, dict, float]] = []
    for index, rec in enumerate(holdings):
        try:
            weight = float(rec.get("weight") or 0.0)
        except (TypeError, ValueError) as exc:
            raise DecisionBoundaryFreeze("non_numeric_normalized_weight") from exc
        if not math.isfinite(weight) or weight < 0.0:
            raise DecisionBoundaryFreeze("invalid_normalized_weight")
        rows.append((index, rec, weight))

    raw_gross = math.fsum(weight for _, _, weight in rows)
    if raw_gross > 1.0 + 1e-6:
        raise DecisionBoundaryFreeze(f"normalized_book_over_leverage:{raw_gross:.9f}")

    # Account reconstruction can land a few floating-point ulps above one even
    # though the underlying long-only book is fully invested. Bring that narrow
    # tolerance back to exactly one before integer apportionment; a material
    # over-gross target was rejected above.
    if raw_gross > 1.0:
        factor = 1.0 / raw_gross
        rows = [
            (index, rec, weight * factor)
            for index, rec, weight in rows
        ]
        for _, rec, weight in rows:
            rec["weight"] = weight

    # A sub-micro row cannot be represented at this precision without either
    # deleting it or increasing it. Preserve it exactly; apportion the remaining
    # representable rows around that protected dust.
    dust = [(index, rec, weight) for index, rec, weight in rows if 0.0 < weight < 1 / scale]
    regular = [(index, rec, weight) for index, rec, weight in rows if weight >= 1 / scale]
    dust_gross = math.fsum(weight for _, _, weight in dust)
    gross_cap = min(1.0, raw_gross)
    available = max(0.0, gross_cap - dust_gross)

    apportioned: list[tuple[int, dict, int, float]] = []
    for index, rec, weight in regular:
        exact_units = weight * scale
        floor_units = math.floor(exact_units)
        apportioned.append((index, rec, floor_units, exact_units - floor_units))

    base_units = sum(units for _, _, units, _ in apportioned)
    target_units = max(base_units, math.floor(available * scale))
    target_units = min(target_units, scale)
    extra_units = max(0, target_units - base_units)
    order = sorted(
        range(len(apportioned)),
        key=lambda pos: (
            -apportioned[pos][3],
            str(apportioned[pos][1].get("ticker") or ""),
            apportioned[pos][0],
        ),
    )
    awarded = set(order[:extra_units])
    for pos, (_, rec, units, _) in enumerate(apportioned):
        rec["weight"] = (units + (1 if pos in awarded else 0)) / scale
    for _, rec, weight in dust:
        rec["weight"] = weight
    for _, rec, weight in rows:
        if weight == 0.0:
            rec["weight"] = 0.0

    quantized_gross = math.fsum(float(rec.get("weight") or 0.0) for rec in holdings)
    if quantized_gross > gross_cap + 1e-12 or quantized_gross > 1.0 + 1e-12:
        raise DecisionBoundaryFreeze(
            f"weight_quantization_overgross:{quantized_gross:.12f}"
        )
    return {
        "digits": digits,
        "raw_gross": raw_gross,
        "quantized_gross": quantized_gross,
        "gross_increased": False,
    }


def _allocate_deterministically(book: str, holdings: list[dict], posture: str) -> dict:
    policy = _sizing_policy(book, posture)
    scores = {"high": 3.0, "medium": 2.0, "low": 1.0}
    protected_gross = sum(float(h.get("_protected_weight") or 0.0) for h in holdings)
    if protected_gross > 1.000001:
        raise DecisionBoundaryFreeze(
            f"protected_book_over_leverage:{protected_gross:.6f}"
        )
    room = max(0.0, min(1.0, float(policy["target_gross"])) - protected_gross)
    add_rows = [h for h in holdings if h.get("action_effective") == "add"]
    available: dict[int, float] = {}
    allocations: dict[int, float] = {}
    for rec in add_rows:
        key = id(rec)
        base = float(rec.get("_protected_weight") or 0.0)
        cap = float(policy["conviction_caps"].get(str(rec.get("conviction")), 0.10))
        cap = max(base, min(cap, float(policy["max_single"])))
        available[key] = max(0.0, cap - base)
        allocations[key] = 0.0

    remaining = [h for h in add_rows if available[id(h)] > 1e-9]
    remaining_room = room
    while remaining and remaining_room > 1e-9:
        total_score = sum(scores.get(str(h.get("conviction")), 2.0) for h in remaining)
        consumed = 0.0
        next_remaining: list[dict] = []
        for rec in remaining:
            key = id(rec)
            share = (
                remaining_room
                * scores.get(str(rec.get("conviction")), 2.0)
                / total_score
            )
            add = min(available[key], share)
            allocations[key] += add
            available[key] -= add
            consumed += add
            if available[key] > 1e-9:
                next_remaining.append(rec)
        if consumed <= 1e-9:
            break
        remaining_room -= consumed
        if len(next_remaining) == len(remaining):
            break
        remaining = next_remaining

    for rec in holdings:
        base = float(rec.get("_protected_weight") or 0.0)
        if rec.get("action_effective") == "add":
            rec["weight"] = base + allocations.get(id(rec), 0.0)
            rec["weight_source"] = policy["name"]
        else:
            rec["weight"] = base
            rec.setdefault("weight_source", "deterministic_preservation.v1")
    return {
        "policy": policy["name"],
        "posture_target_gross": policy["target_gross"],
        "max_single_weight": policy["max_single"],
        "conviction_caps": policy["conviction_caps"],
        "protected_gross": round(protected_gross, 6),
        "model_weight_is_advisory_only": True,
        "no_forced_marginal_names": True,
    }


def normalize(
    book: str,
    args: dict,
    *,
    venue_of: Callable[[str], str] | None = None,
    allowed_venues: set[str] | None = None,
    stock_only: bool = False,
    early_exit_hysteresis: bool = False,
    deterministic_sizing: bool = False,
    decision_asof: date | str | None = None,
) -> tuple[dict, dict]:
    """Return a trusted ``(payload, audit)`` for a regional Brain proposal."""
    args = args if isinstance(args, dict) else {}
    prior = _latest_holdings(book)

    exits: dict[str, dict] = {}
    requested_exits: list[dict] = []
    invalid_exits: list[dict] = []
    for raw in args.get("exit_decisions") or []:
        if not isinstance(raw, dict):
            continue
        ticker = str(raw.get("ticker") or "").upper().strip()
        action = str(raw.get("action") or "exit").lower().strip()
        reason = _clean_text(raw.get("reason"), 1200)
        why_now = _clean_text(raw.get("why_now"), 800)
        evidence = _clean_evidence(raw.get("evidence"))
        if (
            not ticker
            or action not in _EXIT_ACTIONS
            or not reason
            or not why_now
            or not _has_evidence(raw.get("evidence"))
        ):
            invalid_exits.append(
                {"ticker": ticker or None, "reason": "incomplete_exit_evidence"}
            )
            continue
        rec = {
            "ticker": ticker,
            "action": "exit",
            "reason": reason,
            "reason_code": str(raw.get("reason_code") or "thesis_change")
            .lower()
            .strip(),
            "evidence": evidence,
            "falsifier": _clean_text(raw.get("falsifier"), 800),
            "why_now": why_now,
        }
        exits[ticker] = rec
    requested_exits = list(exits.values())

    cleaned: list[dict] = []
    seen: set[str] = set()
    rejected: list[dict] = []
    blocked_actions: list[dict] = []
    quarantined: list[dict] = []
    identity_audit: list[dict] = []
    mandatory_migrations: list[dict] = []
    mandatory_exit_tickers: set[str] = set()

    for raw in args.get("holdings") or []:
        if not isinstance(raw, dict):
            continue
        ticker = str(raw.get("ticker") or "").upper().strip()
        rationale = _clean_text(raw.get("rationale"), 2400)
        if not ticker or ticker in seen or not rationale:
            continue
        venue = venue_of(ticker) if venue_of else None
        if allowed_venues and venue not in allowed_venues:
            rejected.append({"ticker": ticker, "reason": "off_venue"})
            continue
        old = prior.get(ticker)
        identity = (
            _instrument_identity(ticker)
            if stock_only
            else {
                "kind": "common_stock",
                "status": "venue_contract",
                "verified": True,
            }
        )
        identity_audit.append({"ticker": ticker, **identity})
        if stock_only and identity["kind"] != "common_stock":
            if old:
                if identity.get("kind") == "etf" and identity.get("verified") is True:
                    mandatory_exit_tickers.add(ticker)
                    mandatory_migrations.append(
                        {
                            "ticker": ticker,
                            "reason": identity.get("status"),
                            "authority": "deterministic_stock_only_mandate",
                            "requested_action": _clean_text(raw.get("action"), 40).lower()
                            or None,
                        }
                    )
                    seen.add(ticker)
                    continue
                raise DecisionBoundaryFreeze(
                    f"held_instrument_identity_unverified:{ticker}:{identity.get('status')}"
                )
            else:
                rejected.append({"ticker": ticker, "reason": identity["status"]})
            continue

        requested_action = (
            str(raw.get("action") or ("hold" if old else "add")).lower().strip()
        )
        if requested_action not in _HOLDING_ACTIONS:
            rejected.append({"ticker": ticker, "reason": "invalid_holding_action"})
            continue
        if not old and requested_action != "add":
            rejected.append(
                {
                    "ticker": ticker,
                    "reason": f"{requested_action}_requires_existing_position",
                }
            )
            continue
        proposed_weight = None
        try:
            candidate_weight = float(raw.get("weight"))
            if math.isfinite(candidate_weight):
                proposed_weight = max(0.0, min(candidate_weight, 1.0))
        except (TypeError, ValueError):
            pass
        conviction = str(raw.get("conviction") or "medium").lower().strip()
        conviction = conviction if conviction in {"high", "medium", "low"} else "medium"
        rec = {
            "ticker": ticker,
            "weight": float((old or {}).get("weight") or 0.0),
            "proposed_weight": proposed_weight,
            "rationale": rationale,
            "conviction": conviction,
            "action_requested": requested_action,
            "action_effective": requested_action,
            "falsifier": _clean_text(raw.get("falsifier"), 1000),
            "why_now": _clean_text(raw.get("why_now"), 1000),
            "evidence": _clean_evidence(raw.get("evidence")),
            "source_provenance": _json_value(raw.get("source_provenance") or []),
            "expected_horizon": _clean_text(raw.get("expected_horizon"), 400),
            "exit_plan": _clean_text(raw.get("exit_plan"), 1000),
            "identity_status": identity["status"],
        }
        if old and old.get("holding_mark_source"):
            rec["holding_mark_source"] = old.get("holding_mark_source")
        if venue:
            rec["venue"] = venue
        prior_weight = float((old or {}).get("weight") or 0.0)
        if requested_action == "trim":
            intensity = str(raw.get("trim_intensity") or "standard").lower().strip()
            intensity = intensity if intensity in _TRIM_FACTORS else "standard"
            rec["trim_intensity"] = intensity
            if not rec["why_now"] or not _has_evidence(raw.get("evidence")):
                rec["action_effective"] = "hold"
                rec["weight"] = prior_weight
                rec["weight_source"] = "blocked_trim_preserve.v1"
                blocked_actions.append(
                    {
                        "ticker": ticker,
                        "requested_action": "trim",
                        "effective_action": "hold",
                        "reason": "trim_requires_why_now_and_evidence",
                    }
                )
            else:
                target_anchor = float(
                    (old or {}).get("prior_target_weight") or prior_weight
                )
                trim_anchor = min(prior_weight, target_anchor)
                rec["trim_anchor_weight"] = trim_anchor
                rec["weight"] = trim_anchor * _TRIM_FACTORS[intensity]
                rec["weight_source"] = "deterministic_trim.v1"
        elif requested_action == "hold":
            rec["weight"] = prior_weight
            rec["weight_source"] = "deterministic_existing_hold.v1"
        else:
            rec["weight"] = prior_weight
        rec["_protected_weight"] = float(rec["weight"])
        cleaned.append(rec)
        seen.add(ticker)

    carried: list[dict] = []
    blocked_early: list[str] = []
    blocked_exits: list[dict] = []
    effective_exits: list[dict] = [
        _mandate_migration_exit(ticker, next(
            row for row in identity_audit if row.get("ticker") == ticker
        ))
        for ticker in sorted(mandatory_exit_tickers)
    ]

    for ticker, old in prior.items():
        if ticker in mandatory_exit_tickers:
            continue
        if ticker in seen:
            if ticker in exits:
                blocked_exits.append(
                    {
                        "ticker": ticker,
                        "reason": "conflicting_holding_and_exit",
                        "requested_action": "exit",
                        "effective_action": next(
                            (
                                h.get("action_effective")
                                for h in cleaned
                                if h.get("ticker") == ticker
                            ),
                            "hold",
                        ),
                    }
                )
            continue
        exit_rec = exits.get(ticker)
        identity = (
            _instrument_identity(ticker)
            if stock_only
            else {
                "kind": "common_stock",
                "status": "venue_contract",
                "verified": True,
            }
        )
        if stock_only and identity["kind"] != "common_stock":
            identity_audit.append({"ticker": ticker, **identity})
            if identity.get("kind") == "etf" and identity.get("verified") is True:
                effective_exits.append(_mandate_migration_exit(ticker, identity))
                mandatory_migrations.append(
                    {
                        "ticker": ticker,
                        "reason": identity.get("status"),
                        "authority": "deterministic_stock_only_mandate",
                        "requested_action": (
                            exit_rec.get("action") if isinstance(exit_rec, dict) else None
                        ),
                    }
                )
                seen.add(ticker)
                continue
            raise DecisionBoundaryFreeze(
                f"held_instrument_identity_unverified:{ticker}:{identity.get('status')}"
            )

        allow_exit = exit_rec is not None
        carry_reason = "missing_explicit_exit_decision"
        if (
            allow_exit
            and early_exit_hysteresis
            and exit_rec.get("reason_code") not in _EARLY_EXIT_CODES
        ):
            sessions = _held_sessions(book, ticker, decision_asof)
            if sessions is None or sessions <= 3:
                allow_exit = False
                blocked_early.append(ticker)
                carry_reason = (
                    "early_exit_hysteresis_missing_age"
                    if sessions is None
                    else "early_exit_hysteresis"
                )
                blocked_exits.append(
                    {
                        "ticker": ticker,
                        "reason": carry_reason,
                        "held_sessions": sessions,
                        "requested_action": "exit",
                        "effective_action": "hold",
                    }
                )
        if allow_exit and exit_rec:
            effective_exits.append(dict(exit_rec))
            continue
        rec = dict(old)
        rec.update(
            {
                "weight": float(old.get("weight") or 0.0),
                "proposed_weight": None,
                "weight_source": "omission_carry.v1",
                "action_requested": "exit" if exit_rec else None,
                "action_effective": "hold",
                "carried_forward": True,
                "carry_reason": carry_reason,
                "_protected_weight": float(old.get("weight") or 0.0),
            }
        )
        cleaned.append(rec)
        seen.add(ticker)
        carried.append({"ticker": ticker, "reason": carry_reason})

    ignored_exits = [
        {"ticker": ticker, "reason": "ticker_not_currently_held"}
        for ticker in exits
        if ticker not in prior
    ]

    posture = str(args.get("risk_posture") or "normal").lower().strip()
    posture = posture if posture in {"normal", "caution", "crash"} else "normal"
    if deterministic_sizing:
        sizing_audit = _allocate_deterministically(book, cleaned, posture)
    else:
        # Compatibility-only path for non-desk callers.  Holds, carries and trims
        # remain protected; only ADD increments may consume an advisory weight.
        for rec in cleaned:
            base = float(rec.get("_protected_weight") or 0.0)
            if (
                rec.get("action_effective") == "add"
                and rec.get("proposed_weight") is not None
            ):
                rec["weight"] = max(base, float(rec["proposed_weight"]))
                rec["weight_source"] = "legacy_advisory_add_passthrough"
            else:
                rec["weight"] = base
        sizing_audit = {
            "policy": "legacy_advisory_add_passthrough",
            "model_weight_is_advisory_only": False,
        }

    unallocated_adds = [
        {"ticker": rec.get("ticker"), "reason": "no_deterministic_allocation_room"}
        for rec in cleaned
        if rec.get("action_effective") == "add"
        and float(rec.get("weight") or 0.0) <= 1e-9
    ]
    cleaned = [
        rec
        for rec in cleaned
        if not (
            rec.get("action_effective") == "add"
            and float(rec.get("weight") or 0.0) <= 1e-9
        )
    ]

    # If a compatibility caller proposes an over-gross book, the trusted
    # positions remain byte-for-byte unchanged.  Only the ADD increment is scaled.
    protected_gross = sum(float(rec.get("_protected_weight") or 0.0) for rec in cleaned)
    if protected_gross > 1.000001:
        raise DecisionBoundaryFreeze(
            f"protected_book_over_leverage:{protected_gross:.6f}"
        )
    gross = sum(float(rec.get("weight") or 0.0) for rec in cleaned)
    scaled = gross > 1.0 + 1e-9
    if scaled:
        discretionary = gross - protected_gross
        if discretionary <= 0:
            raise DecisionBoundaryFreeze(f"unscalable_overgross_book:{gross:.6f}")
        scale = max(0.0, 1.0 - protected_gross) / discretionary
        for rec in cleaned:
            protected = float(rec.get("_protected_weight") or 0.0)
            increment = max(0.0, float(rec.get("weight") or 0.0) - protected)
            rec["weight"] = protected + increment * scale
        gross = sum(float(rec.get("weight") or 0.0) for rec in cleaned)

    quantization = _quantize_executable_weights(cleaned)
    sizing_audit["weight_quantization"] = quantization
    for rec in cleaned:
        rec.pop("_protected_weight", None)
    gross = float(quantization["quantized_gross"])

    cash_rationale = _clean_text(args.get("cash_rationale"), 1600)
    memo_in = (
        args.get("decision_memo") if isinstance(args.get("decision_memo"), dict) else {}
    )
    memo = {
        key: _json_value(memo_in.get(key))
        for key in _MEMO_FIELDS
        if memo_in.get(key) is not None
    }
    audit = {
        "carried": carried,
        "blocked_early_exits": blocked_early,
        "blocked_exits": blocked_exits,
        "blocked_actions": blocked_actions,
        "invalid_exit_requests": invalid_exits,
        "ignored_exit_requests": ignored_exits,
        "rejected": rejected,
        "quarantined": quarantined,
        "mandatory_instrument_migrations": mandatory_migrations,
        "identity": identity_audit,
        "unallocated_adds": unallocated_adds,
        "quote_fallback_holdings": sorted(
            rec.get("ticker")
            for rec in cleaned
            if rec.get("holding_mark_source") == "account_avg_cost_fallback"
        ),
        "sizing": sizing_audit,
    }
    payload: dict[str, Any] = {
        "schema": "mastermind.target_book.v2",
        "holdings": cleaned,
        "summary": _clean_text(args.get("summary"), 5000),
        "sold_note": _clean_text(args.get("sold_note"), 2400),
        "gross": round(gross, 4),
        "scaled_to_no_leverage": scaled,
        "risk_posture": posture,
        "cash_rationale": cash_rationale,
        "requested_exit_decisions": requested_exits,
        "exit_decisions": effective_exits,
        "decision_memo": memo,
        "submission_audit": audit,
    }
    for key in _TOP_FIELDS:
        if key not in payload and args.get(key) is not None:
            payload[key] = _json_value(args.get(key))
    payload["allocation_review"] = {
        "cash": round(max(0.0, 1.0 - gross), 4),
        "cash_rationale_required": gross < 0.60,
        "cash_rationale_present": bool(cash_rationale),
        "note": (
            "Low gross is permitted only as deliberate judgment; the allocator never invents "
            "marginal names merely to fill a target."
        ),
    }
    return payload, audit


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, path)


def holding_audit_fields(holding: dict | None) -> dict:
    """Rich, stable per-name governance copied into each durable daily log."""
    src = holding if isinstance(holding, dict) else {}
    return {key: _json_value(src.get(key)) for key in _HOLDING_LOG_FIELDS if key in src}


def target_status_fields(target_status: str) -> dict:
    """Durable execution-state marker for a proposed target book."""
    status = _clean_text(target_status, 80) or "rejected_unspecified"
    return {
        "target_status": status,
        "decision_effective": status in ACCEPTED_TARGET_STATUSES,
    }


def effective_holding_audit(
    submission: dict | None,
    effective_target: dict[str, float] | None,
    target_status: str,
) -> list[dict]:
    """Rationale-bearing target rows that were actually executed or durably queued.

    Proposed/rejected holdings remain in ``holdings`` for review, but may never become the
    next run's numeric trim anchor.  This projection records only the post-rail target that
    reached the paper-account boundary.
    """
    if target_status not in ACCEPTED_TARGET_STATUSES or effective_target is None:
        return []
    proposed = {
        str(row.get("ticker") or "").upper().strip(): row
        for row in ((submission or {}).get("holdings") or [])
        if isinstance(row, dict) and row.get("ticker")
    }
    rows: list[dict] = []
    for ticker, raw_weight in sorted(effective_target.items()):
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        if not ticker or not math.isfinite(weight) or weight <= 0:
            continue
        row = holding_audit_fields(proposed.get(str(ticker).upper()) or {"ticker": ticker})
        row.update({"ticker": str(ticker).upper(), "weight": weight})
        rows.append(row)
    return rows


def effective_narrative_fields(submission: dict | None, target_status: str) -> dict:
    """Separate an unapplied proposal's prose from the currently effective book narrative."""
    src = submission if isinstance(submission, dict) else {}
    status = target_status_fields(target_status)
    if status["target_status"] == "executed":
        return {
            **status,
            "summary": src.get("summary"),
            "sold_note": src.get("sold_note"),
        }
    if status["target_status"] == "queued":
        return {
            **status,
            "summary": "Decision accepted and queued for the next eligible open; no fills yet.",
            "sold_note": None,
            "proposed_summary": src.get("summary"),
            "proposed_sold_note": src.get("sold_note"),
        }
    return {
        **status,
        "summary": (
            f"Proposed decision was not applied ({status['target_status']}); "
            "the current paper book was carried unchanged."
        ),
        "sold_note": None,
        "proposed_summary": src.get("summary"),
        "proposed_sold_note": src.get("sold_note"),
    }


def audit_fields(submission: dict | None) -> dict:
    """Stable detailed-memo fields copied into daily logs and API responses."""
    src = submission if isinstance(submission, dict) else {}
    keys = (
        "schema",
        "decision_memo",
        "requested_exit_decisions",
        "exit_decisions",
        "falsifiers",
        "evidence_planes",
        "source_provenance",
        "liquidity_notes",
        "expected_failure_mode",
        "risk_posture",
        "cash_rationale",
        "allocation_review",
        "submission_audit",
    )
    return {key: _json_value(src.get(key)) for key in keys if src.get(key) is not None}
