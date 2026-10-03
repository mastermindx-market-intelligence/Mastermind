"""The sole raw W-LIQ.1 -> existing W-LIQ.3 research-envelope adapter.

This validates and copies; it never rebuilds a factor or repairs an input. The
explicit as_of only enforces availability. It does not refresh old data or
replace a future reader's source-age policy. Opaque upstream hashes are identity
references, not independent authentication or proofs of numerical correctness.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
from numbers import Real
from typing import Any, Mapping

from brain.liquidity_lab.contracts import ContractError, PRODUCER_SCHEMA, SourceStateRef, _utc_timestamp

RAW_UNIT = "weekly_change_in_expanding_z_score"
Z_UNIT = "prior_only_expanding_z_score_of_weekly_change_in_expanding_z_score"
STATE_LABELS = frozenset({"expanding", "flat", "contracting", "unknown"})
QUALITY_LABELS = frozenset({"easing", "tightening", "mixed", "unknown"})


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _required(obj: Mapping[str, Any], key: str) -> Any:
    if key not in obj:
        raise ContractError(f"missing required producer field {key}")
    return obj[key]


def _same(left: Any, right: Any, name: str) -> None:
    if left != right:
        raise ContractError(f"inconsistent producer {name}")


def _number(value: Any, name: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ContractError(f"{name} must be a finite JSON number")
    return float(value)


def _available(value: Any, limit: datetime, name: str, *, date_only: bool = False) -> None:
    if date_only and isinstance(value, str) and len(value) == 10:
        value += "T00:00:00Z"
    stamp = _utc_timestamp(name, value)
    if stamp > limit:
        raise ContractError(f"{name} is later than claimed evidence availability")


def _validate_clocks(payload: Mapping[str, Any], event: Mapping[str, Any],
                     cutoff: datetime) -> tuple[datetime, datetime]:
    clocks = _object(event.get("clocks"), "event clocks")
    outer = _object(payload["freshness"].get("clocks"), "freshness clocks")
    _same(clocks, outer, "clock copies")
    _same(clocks.get("adapter_observed_at_field"), "evidence_available_at", "observed clock binding")
    _same(clocks.get("adapter_known_at_field"), "first_known_at", "known clock binding")
    observed = _utc_timestamp("evidence_available_at", clocks.get("evidence_available_at"))
    known = _utc_timestamp("first_known_at", clocks.get("first_known_at"))
    _same(_utc_timestamp("release_at", clocks.get("release_at")), observed, "release alias")
    if not observed <= known <= cutoff:
        raise ContractError("evidence availability <= first_known_at <= as_of is required")
    generated = _utc_timestamp("generated_at", payload["meta"].get("generated_at"))
    if not known <= generated <= cutoff:
        raise ContractError("first_known_at <= generated_at <= as_of is required")
    _available(clocks.get("state_asof"), known, "state_asof")
    _available(clocks.get("monetary_release_at"), observed, "monetary availability")
    contributions = _object(clocks.get("evidence_available_at_contributions"), "clock contributions")
    for key in ("monetary", "usd_funding", "us_liquidity_quality"):
        value = _required(contributions, key)
        if value is not None:
            _available(value, observed, f"{key} evidence availability")
    quality = payload["quality"].get("us_liquidity_quality")
    if quality is not None:
        quality = _object(quality, "US quality")
        _available(quality.get("asof"), observed, "US quality availability", date_only=True)
    return observed, known


def _validate_components(payload: Mapping[str, Any], event: Mapping[str, Any],
                         observed: datetime) -> None:
    components = _object(event.get("component_snapshot"), "component snapshot")
    _same(components, payload["freshness"].get("component_snapshot"), "component snapshot copies")
    required = {
        "monetary": {"fed", "ecb", "boj"},
        "usd_funding": {"broad_dollar", "high_yield_oas", "real_yield_10y"},
    }
    _same(set(components), set(required), "copied component families")
    flat = _object(payload["freshness"].get("components"), "flat component receipts")
    for family, names in required.items():
        rows = _object(components.get(family), family)
        if not names.issubset(rows):
            raise ContractError(f"{family} omits required component receipts")
        flat_rows = _object(flat.get(family), f"flat {family} receipts")
        _same(set(rows), set(flat_rows), f"{family} receipt keys")
        for name, raw in rows.items():
            row = _object(raw, f"{family}.{name}")
            receipt = _object(row.get("receipt"), f"{family}.{name} receipt")
            _same(receipt, flat_rows[name], f"{family}.{name} receipt copies")
            available = _required(receipt, "available_date")
            reference = _required(receipt, "reference_date")
            if available is not None:
                _available(available, observed, f"{family}.{name} availability", date_only=True)
                stamp = str(available)
                if len(stamp) == 10:
                    stamp += "T00:00:00Z"
                if reference is not None:
                    _available(reference, _utc_timestamp("available_date", stamp),
                               f"{family}.{name} reference date", date_only=True)
            if receipt.get("status") == "usable" and (available is None or reference is None):
                raise ContractError(f"usable {family}.{name} lacks reference/availability dates")


def adapt_producer_state(payload: Mapping[str, Any], *, as_of: datetime) -> SourceStateRef | None:
    """Copy a coherent producer event envelope, or None for valid warmup/zero.

    Non-finite, conflicting, backdated or unknown-version evidence fails closed.
    A valid stale observation is retained as stale; the existing eventizer cannot
    admit it. A flat label is not a zero raw delta. Data confidence is never a
    prediction probability. No source age or history is inferred from build time.
    """
    payload = _object(payload, "producer payload")
    for key in ("meta", "state", "quality", "freshness"):
        _object(payload.get(key), key)
    cutoff = _utc_timestamp("as_of", as_of)
    meta, state, quality, freshness = (payload[k] for k in ("meta", "state", "quality", "freshness"))
    event = _object(state.get("event_reference"), "event reference")
    for actual, expected, name in (
        (meta.get("schema"), PRODUCER_SCHEMA, "schema"),
        (event.get("producer_schema"), PRODUCER_SCHEMA, "event schema"),
        (meta.get("authority"), "measurement_only", "authority"),
        (meta.get("contract_scope"), "state_quality_freshness_only", "scope"),
        (event.get("state_family"), "monetary_impulse", "state family"),
        (event.get("shock_type"), "policy_liquidity_impulse", "shock type"),
        (event.get("regional_gates"), {}, "unarmed regional gates"),
    ):
        _same(actual, expected, name)
    for key in ("source_snapshot_hash", "model_version", "data_version"):
        _same(_required(event, key), _required(meta, key), key)
    observed, known = _validate_clocks(payload, event, cutoff)
    _validate_components(payload, event, observed)
    units = _object(state.get("units"), "state units")
    values = {}
    for event_key, state_key, unit in (
        ("magnitude", "monetary_impulse", RAW_UNIT),
        ("magnitude_z", "monetary_impulse_z", Z_UNIT),
    ):
        _same(event.get(event_key + "_field"), "state." + state_key, event_key + " field")
        _same(event.get(event_key + "_unit"), unit, event_key + " unit")
        _same(units.get(state_key), unit, state_key + " unit")
        value = _number(_required(event, event_key), event_key, nullable=True)
        _same(value, _number(_required(state, state_key), state_key, nullable=True), event_key)
        values[event_key] = value

    for key, vocabulary, peer in (("direction_label", STATE_LABELS, state.get("label")),
                                  ("quality", QUALITY_LABELS, quality.get("event_quality"))):
        value = event.get(key)
        if not isinstance(value, str) or value not in vocabulary:
            raise ContractError(f"invalid {key} vocabulary")
        _same(value, peer, key)
    numbers = {key: _number(_required(event, key), key, nullable=key == "breadth")
               for key in ("confidence", "coverage", "breadth")}
    for key, value in numbers.items():
        if value is not None and not 0 <= value <= 1:
            raise ContractError(f"{key} must be in [0, 1]")
    confidence = _object(quality.get("confidence"), "confidence")
    _same(confidence.get("kind"), "data_lineage_and_coverage_only", "confidence semantics")
    _same(numbers["confidence"], _number(confidence.get("value"), "data confidence"), "data confidence")
    _same(numbers["coverage"], _number(freshness.get("monetary_coverage_ratio"), "monetary coverage"), "monetary coverage")
    _same(numbers["breadth"], _number(_required(state, "liquidity_breadth"), "breadth", nullable=True), "breadth")
    conditions = _object(event.get("conditions"), "conditions")
    _same(set(conditions), {"us_liquidity_quality", "usd_funding_impulse"}, "registered conditions")
    funding = _number(conditions["usd_funding_impulse"], "funding context", nullable=True)
    _same(funding, _number(_required(state, "usd_funding_impulse"), "funding state", nullable=True), "funding context")
    us_quality = _required(quality, "us_liquidity_quality")
    expected_label = "unknown" if us_quality is None else _object(us_quality, "US quality").get("label", "unknown")
    if not isinstance(conditions["us_liquidity_quality"], str):
        raise ContractError("US quality context must be a producer label")
    _same(conditions["us_liquidity_quality"], expected_label, "US quality context")
    if not isinstance(event.get("freshness"), str) or event["freshness"] not in {"fresh", "degraded", "stale", "unknown"}:
        raise ContractError("unknown producer freshness state")
    _same(event.get("freshness"), freshness.get("status"), "event freshness")
    _same(meta.get("model_version"), "glt_state.v1", "accepted model version")
    _same(meta.get("producer_version"), "w-liq.1.0", "accepted producer version")
    digest = event["source_snapshot_hash"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ContractError("source_snapshot_hash must be a canonical SHA-256 reference")
    _same(event["data_version"], "glt_data:" + digest[:16], "producer data version")
    raw, z = values["magnitude"], values["magnitude_z"]
    direction = _required(event, "direction")
    if raw is None or raw == 0:
        if direction is not None:
            raise ContractError("null/zero raw magnitude must have null direction")
        return None
    if isinstance(direction, bool) or direction not in (-1, 1) or direction * raw <= 0:
        raise ContractError("direction must copy the raw magnitude sign, not standardized sign")
    if z is None:
        return None
    return SourceStateRef(
        observed_at=observed, known_at=known,
        source_snapshot_hash=event["source_snapshot_hash"],
        model_version=event["model_version"], data_version=event["data_version"],
        state_family=event["state_family"], shock_type=event["shock_type"],
        direction=direction, magnitude_z=z, breadth=numbers["breadth"],
        quality=event["quality"], confidence=numbers["confidence"],
        coverage=numbers["coverage"], freshness=_required(event, "freshness"),
        conditions=deepcopy(_object(event.get("conditions"), "conditions")),
        regional_gates=deepcopy(event["regional_gates"]),
        component_snapshot=deepcopy(event["component_snapshot"]),
    )
