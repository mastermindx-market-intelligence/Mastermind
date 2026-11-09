"""Pure, read-only multi-asset portfolio what-if comparison (MA-4 pre-forecast slice).

Does not allocate, rank, optimize, rebalance, persist, fetch, notify, modify any
account, or promote a risk observation to capital authority. A caller supplies
fully-funded target alternatives and hypothetical scenario assumptions. Qualified
instrument/FX provenance is a required *declaration*, not an authentication by
this library; real book/policy owners must independently validate those claims.
There is NO import from an active sizing, order, or publisher path.

This is deliberately NOT another firm-level allocator or shadow-book owner.
Existing firms/books retain their identity, mandate, snapshots, and lifecycle.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from numbers import Real
from typing import Any

SCHEMA = "mastermind.portfolio_global_scenario_context/v1"
METHOD = "fully_funded_read_only_counterfactual.v1"
AUTHORITY = {"can_rank": False, "can_gate": False, "can_size": False,
             "can_trade": False, "can_rebalance": False}
_TOL = 1e-9
_MAX_ROWS = 100


class ContractError(ValueError):
    """Malformed caller structure; not a data-backed portfolio verdict."""


def _text(x: Any) -> str | None:
    return x if isinstance(x, str) and 0 < len(x) <= 128 and x.strip() == x else None


def _currency(x: Any) -> bool:
    return isinstance(x, str) and len(x) == 3 and x.isascii() and x.isalpha() and x.isupper()


def _num(x: Any, *, floor: float | None = None, ceiling: float | None = None) -> float | None:
    if isinstance(x, bool) or not isinstance(x, Real):
        return None
    try:
        n = float(x)
        if not math.isfinite(n) or (floor is not None and n < floor) or (ceiling is not None and n > ceiling):
            return None
        return n
    except (TypeError, ValueError, OverflowError):
        return None


def _instant(x: Any) -> datetime | None:
    if not isinstance(x, str):
        return None
    try:
        dt = datetime.fromisoformat(x.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            return None
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def _stamp(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _canonical(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _unavailable(as_of: str, reason: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "method_version": METHOD, "as_of": as_of,
            "status": "UNAVAILABLE", "reasons": [reason], "alternatives": [],
            "authority": dict(AUTHORITY), "display_only": True,
            "hypothetical_only": True, "no_predictive_claim": True}


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _id_map(rows: Any, name: str) -> dict[str, dict] | None:
    if not _sequence(rows) or len(rows) > _MAX_ROWS:
        return None
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not _text(row.get(name)):
            return None
        key = row[name]
        if key in out:
            return None
        out[key] = dict(row)
    return out


def _weights(raw: Any, known: set[str]) -> dict[str, float] | None:
    if not isinstance(raw, Mapping) or len(raw) > _MAX_ROWS:
        return None
    out: dict[str, float] = {}
    for key, value in raw.items():
        if key not in known or not _text(key):
            return None
        weight = _num(value, floor=0, ceiling=1)
        if weight is None:
            return None
        out[key] = weight
    return out


def _clock_eligible(start: Any, end: Any, as_of: datetime) -> bool:
    lo, hi = _instant(start), _instant(end)
    return lo is not None and hi is not None and lo <= as_of < hi


def compare(
    book: Mapping[str, Any], alternatives: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]], *, as_of: str,
) -> dict[str, Any]:
    """Compare caller-specified fully funded allocations against declared scenarios.

    Never derives a target allocation, probability, alpha, optimum, or policy.
    Each scenario's per-instrument return is a *hypothetical base-currency total
    return assumption*. Non-base-currency instruments require a separate declared
    qualified FX ancestry; neither spot quotes nor static FX fallbacks are filled.

    Costs are charged ONCE to traded non-cash notional:
      sum(abs(target_weight - held_weight) * (fee+spread_crossing+impact)_bps / 10000).
    Spread crossing means estimated one-way execution cost per traded notional,
    NOT the quoted full bid-ask spread. Cash weight is not separately charged;
    sell and buy legs are both charged.
    Scenario returns and constraints are assumptions, not empirical forecasts.
    """
    cutoff = _instant(as_of)
    if cutoff is None:
        raise ContractError("aware_as_of_required")
    at = _stamp(cutoff)
    if not isinstance(book, Mapping) or not _sequence(alternatives) or not _sequence(scenarios):
        raise ContractError("mapping_and_bounded_sequences_required")
    if len(alternatives) > 30 or len(scenarios) > 30:
        raise ContractError("too_many_scenarios_or_alternatives")
    if not _text(book.get("book_id")) or not _text(book.get("book_revision")):
        return _unavailable(at, "book_identity_missing")
    base = book.get("base_currency")
    if not _currency(base):
        return _unavailable(at, "book_currency_invalid")
    if not _clock_eligible(book.get("known_at"), book.get("valid_until"), cutoff):
        return _unavailable(at, "book_clock_unqualified")

    universe = _id_map(book.get("universe"), "instrument_id")
    if not universe:
        return _unavailable(at, "instrument_universe_missing_or_ambiguous")
    for key, inst in universe.items():
        if not _currency(inst.get("currency")):
            return _unavailable(at, "instrument_currency_invalid")
        if inst.get("eligibility") != "QUALIFIED" or not _text(inst.get("policy_ref")):
            return _unavailable(at, "instrument_eligibility_unqualified")
        keys = inst.get("risk_keys")
        if not _sequence(keys) or any(not _text(k) for k in keys):
            return _unavailable(at, "risk_exposure_missing")
    positions = _weights(book.get("positions"), set(universe))
    cash = _num(book.get("cash_weight"), floor=0, ceiling=1)
    if positions is None or cash is None or abs(sum(positions.values()) + cash - 1) > _TOL:
        return _unavailable(at, "book_not_fully_funded")
    constraints = book.get("constraints")
    if not isinstance(constraints, Mapping):
        return _unavailable(at, "constraints_missing")
    limits = {}
    for field in ("max_instrument_weight", "max_risk_key_weight", "max_turnover_fraction",
                  "min_cash_fraction"):
        limits[field] = _num(constraints.get(field), floor=0, ceiling=1)
    if any(v is None for v in limits.values()):
        return _unavailable(at, "constraints_unqualified")

    options = _id_map(alternatives, "alternative_id")
    paths = _id_map(scenarios, "scenario_id")
    if not options or not paths:
        return _unavailable(at, "alternatives_or_scenarios_missing_or_duplicate")
    for sid, scenario in paths.items():
        if not _clock_eligible(scenario.get("known_at"), scenario.get("valid_until"), cutoff):
            return _unavailable(at, "scenario_clock_unqualified")
        if not _text(scenario.get("source_ref")):
            return _unavailable(at, "scenario_provenance_missing")
        if not isinstance(scenario.get("returns"), Mapping):
            return _unavailable(at, "scenario_returns_missing")
        if _num(scenario.get("cash_return"), floor=-1) is None:
            return _unavailable(at, "cash_assumption_missing")

    # Canonicalize the bounded, validated input graph before computing. Only
    # identity-based ordering is canonical; never sort alternatives by returns.
    normalized = {
        "as_of": at, "book": {
            "book_id": book["book_id"], "book_revision": book["book_revision"],
            "known_at": _stamp(_instant(book["known_at"])),
            "valid_until": _stamp(_instant(book["valid_until"])),
            "base_currency": base, "cash_weight": cash,
            "positions": {k: positions[k] for k in sorted(positions)},
            "universe": {k: universe[k] for k in sorted(universe)},
            "constraints": {k: limits[k] for k in sorted(limits)},
        },
        "alternatives": {k: options[k] for k in sorted(options)},
        "scenarios": {k: paths[k] for k in sorted(paths)},
    }
    try:
        digest = hashlib.sha256(_canonical(normalized).encode("ascii")).hexdigest()
    except (TypeError, ValueError, UnicodeError, OverflowError):
        return _unavailable(at, "evidence_not_serializable")

    reports: list[dict[str, Any]] = []
    for aid in sorted(options):
        proposal = options[aid]
        target = _weights(proposal.get("positions"), set(universe))
        tcash = _num(proposal.get("cash_weight"), floor=0, ceiling=1)
        costs = proposal.get("costs_bps")
        reasons: list[str] = []
        if target is None or tcash is None or abs(sum((target or {}).values()) + (tcash or 0) - 1) > _TOL:
            reasons.append("alternative_not_fully_funded")
        if not isinstance(costs, Mapping) or set(costs) != {"fee", "spread_crossing", "impact"}:
            reasons.append("cost_components_missing_or_ambiguous")
        else:
            for val in costs.values():
                if _num(val, floor=0, ceiling=10000) is None:
                    reasons.append("cost_component_invalid"); break
        if reasons:
            reports.append({"alternative_id": aid, "status": "UNAVAILABLE",
                            "reasons": sorted(set(reasons)), "scenario_results": []})
            continue
        assert target is not None and tcash is not None and isinstance(costs, Mapping)
        turnover = sum(abs(target.get(k, 0) - positions.get(k, 0)) for k in universe)
        bps = sum(float(x) for x in costs.values())
        fixed_cost = turnover * bps / 10000
        breaches = []
        if tcash + _TOL < limits["min_cash_fraction"]:
            breaches.append("cash_floor")
        if turnover > limits["max_turnover_fraction"] + _TOL:
            breaches.append("turnover_ceiling")
        risk_exposure: dict[str, float] = {}
        for key, weight in target.items():
            if weight > limits["max_instrument_weight"] + _TOL:
                breaches.append("instrument_weight_ceiling")
            for label in sorted(set(universe[key]["risk_keys"])):
                risk_exposure[label] = risk_exposure.get(label, 0.0) + weight
        if any(w > limits["max_risk_key_weight"] + _TOL for w in risk_exposure.values()):
            breaches.append("risk_key_weight_ceiling")

        results = []
        for sid in sorted(paths):
            scen = paths[sid]
            assumed = scen["returns"]
            total = tcash * float(scen["cash_return"])
            missing: list[str] = []
            for key, weight in sorted(target.items()):
                if weight == 0:
                    continue
                datum = assumed.get(key)
                if not isinstance(datum, Mapping):
                    missing.append("instrument_return_missing"); continue
                value = _num(datum.get("base_total_return"), floor=-1)
                if value is None or datum.get("return_currency") != base:
                    missing.append("base_return_unqualified"); continue
                if not _clock_eligible(datum.get("known_at"), datum.get("valid_until"), cutoff):
                    missing.append("return_assumption_clock_unqualified"); continue
                if universe[key]["currency"] != base:
                    if (datum.get("fx_qualified") is not True
                            or not _text(datum.get("fx_source_ref"))):
                        missing.append("fx_ancestry_unqualified"); continue
                total += weight * value
            if missing or not math.isfinite(total) or not math.isfinite(total - fixed_cost):
                results.append({"scenario_id": sid, "status": "UNAVAILABLE",
                                "reasons": sorted(set(missing or ["scenario_arithmetic_invalid"]))})
            else:
                results.append({"scenario_id": sid, "status": "HYPOTHETICAL",
                                "gross_return": total, "one_time_cost": fixed_cost,
                                "net_return": total - fixed_cost,
                                "assumption_ref": scen["source_ref"]})
        eligible_results = [r["net_return"] for r in results if r["status"] == "HYPOTHETICAL"]
        status = ("INELIGIBLE" if breaches else
                  "AVAILABLE" if len(eligible_results) == len(paths) else
                  "PARTIAL" if eligible_results else "UNAVAILABLE")
        reports.append({
            "alternative_id": aid, "status": status,
            "constraints_breached": sorted(set(breaches)),
            "target_cash_fraction": tcash, "traded_notional_fraction": turnover,
            "one_time_cost_fraction": fixed_cost,
            "risk_key_exposures_nonadditive": {k: risk_exposure[k] for k in sorted(risk_exposure)},
            "scenario_results": results,
            "worst_hypothetical_net_return": min(eligible_results) if eligible_results else None,
            "reasons": [] if len(eligible_results) == len(paths) else ["scenario_coverage_incomplete"],
        })
    return {
        "schema": SCHEMA, "method_version": METHOD, "as_of": at,
        "status": ("AVAILABLE" if all(r["status"] == "AVAILABLE" for r in reports)
                   else "PARTIAL" if any(r["status"] in ("AVAILABLE", "INELIGIBLE", "PARTIAL") for r in reports)
                   else "UNAVAILABLE"),
        "book": {"book_id": book["book_id"], "book_revision": book["book_revision"],
                 "base_currency": base, "current_cash_fraction": cash},
        "input_digest": digest, "alternatives": reports,
        "authority": dict(AUTHORITY), "display_only": True,
        "hypothetical_only": True, "no_predictive_claim": True,
        "note": "User-supplied counterfactuals; not calibrated returns or eligible trade targets.",
    }
