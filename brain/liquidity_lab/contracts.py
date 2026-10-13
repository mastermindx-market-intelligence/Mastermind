"""Closed research contracts for W-LIQ.3.

W-LIQ.1 owns liquidity-state semantics and computation.  ``SourceStateRef`` is
therefore an adapter boundary, not a parser for the still-unfrozen producer
payload: a later adapter must copy the canonical producer's already-computed
values into this envelope without re-deriving them here.

Every object in this module is research/shadow evidence only.  None carries a
portfolio action, size, candidacy, Market View vote, or promotion authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping


PRODUCER_SCHEMA = "global_liquidity_transmission.v1"
LAB_SCHEMA = "liquidity_transmission_lab.v1"
HORIZONS_BDAYS = (1, 5, 10, 20, 40, 60, 90, 120)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_HEX_RE = re.compile(r"^[0-9a-f]{16,128}$")
_FRESHNESS = frozenset({"fresh", "degraded", "stale", "unknown"})
_RELATION_STATES = frozenset(
    {"discovered", "shadow", "advisory", "validated", "demoted", "dead"}
)


class ContractError(ValueError):
    """Raised when research evidence is ambiguous or statistically unsafe."""


def _finite(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ContractError(f"{name} must be finite")
    return number


def _unit_interval(name: str, value: Any, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise ContractError(f"{name} must be in [0, 1]")
    return number


def _identifier(name: str, value: Any) -> str:
    text = str(value or "").strip().lower()
    if not _ID_RE.fullmatch(text):
        raise ContractError(f"{name} is not a closed identifier")
    return text


def _snapshot_hash(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not _HEX_RE.fullmatch(text):
        raise ContractError("source_snapshot_hash must be 16-128 lowercase hex characters")
    return text


def _utc_timestamp(name: str, value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ContractError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _jsonable_mapping(name: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    result = {str(key): item for key, item in value.items()}
    try:
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{name} must be canonical-JSON serializable") from exc
    return result


def canonical_hash(payload: Mapping[str, Any]) -> str:
    """Return the stable SHA-256 of a closed JSON object."""

    try:
        encoded = json.dumps(
            dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("payload must be canonical-JSON serializable") from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """Precommitted research target; never an investable-universe grant."""

    target_id: str
    symbol: str
    asset_class: str
    region: str
    hierarchy_parent: str
    role: str = "macro_proxy"
    benchmark: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _identifier("target_id", self.target_id))
        if not str(self.symbol or "").strip():
            raise ContractError("symbol is required")
        object.__setattr__(self, "symbol", str(self.symbol).strip().upper())
        object.__setattr__(self, "asset_class", _identifier("asset_class", self.asset_class))
        object.__setattr__(self, "region", _identifier("region", self.region))
        object.__setattr__(
            self, "hierarchy_parent", _identifier("hierarchy_parent", self.hierarchy_parent)
        )
        if self.role not in {"macro_proxy", "single_name"}:
            raise ContractError("role must be macro_proxy or single_name")
        if self.benchmark is not None:
            object.__setattr__(self, "benchmark", _identifier("benchmark", self.benchmark))


# The first lab universe is deliberately liquid and compact.  A target's presence
# here means "precommitted research measurement", never eligibility to trade.
TARGETS = (
    TargetSpec("btc", "BTC-USD", "crypto", "global", "crypto"),
    TargetSpec("spy", "SPY", "us_equity", "us", "us_broad"),
    TargetSpec("qqq", "QQQ", "us_equity", "us", "us_growth", benchmark="spy"),
    TargetSpec("smh", "SMH", "us_equity", "us", "semis", benchmark="spy"),
    TargetSpec("igv", "IGV", "us_equity", "us", "software", benchmark="spy"),
    TargetSpec("iwm", "IWM", "us_equity", "us", "small_caps", benchmark="spy"),
    TargetSpec("tlt", "TLT", "rates", "us", "duration"),
    TargetSpec("hyg", "HYG", "credit", "us", "high_yield"),
    TargetSpec("lqd", "LQD", "credit", "us", "investment_grade"),
    TargetSpec("gld", "GLD", "commodity", "global", "gold"),
    TargetSpec("slv", "SLV", "commodity", "global", "silver"),
    TargetSpec("dbc", "DBC", "commodity", "global", "commodities"),
    TargetSpec("uso", "USO", "commodity", "global", "oil"),
    TargetSpec("cper", "CPER", "commodity", "global", "copper"),
    TargetSpec("efa", "EFA", "dm_equity", "dm_ex_us", "dm_ex_us", benchmark="spy"),
    TargetSpec("eem", "EEM", "em_equity", "em", "em_broad", benchmark="spy"),
    TargetSpec("fxi", "FXI", "china_equity", "china_hk", "china_broad", benchmark="eem"),
    TargetSpec("mchi", "MCHI", "china_equity", "china_hk", "china_broad", benchmark="eem"),
    TargetSpec("kweb", "KWEB", "china_equity", "china_hk", "china_internet", benchmark="mchi"),
    TargetSpec(
        "baba", "BABA", "china_equity", "china_hk", "china_internet", role="single_name", benchmark="kweb"
    ),
)
TARGET_BY_ID = MappingProxyType({target.target_id: target for target in TARGETS})


@dataclass(frozen=True, slots=True)
class SourceStateRef:
    """Adapter-normalized reference to one W-LIQ.1 state observation.

    ``observed_at`` is the upstream measurement/release timestamp and ``known_at``
    is the first timestamp at which this exact payload was available to the lab.
    The lab may eventize these supplied values; it may not reconstruct them from
    raw central-bank, money, credit, funding, or market series.
    """

    observed_at: datetime
    known_at: datetime
    source_snapshot_hash: str
    model_version: str
    data_version: str
    state_family: str
    shock_type: str
    direction: int
    magnitude_z: float
    breadth: float | None
    quality: str
    confidence: float
    coverage: float
    freshness: str
    conditions: Mapping[str, Any] = field(default_factory=dict)
    regional_gates: Mapping[str, Any] = field(default_factory=dict)
    component_snapshot: Mapping[str, Any] = field(default_factory=dict)
    producer_schema: str = PRODUCER_SCHEMA

    def __post_init__(self) -> None:
        observed_at = _utc_timestamp("observed_at", self.observed_at)
        known_at = _utc_timestamp("known_at", self.known_at)
        if known_at < observed_at:
            raise ContractError("known_at may not precede observed_at")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "known_at", known_at)
        object.__setattr__(self, "source_snapshot_hash", _snapshot_hash(self.source_snapshot_hash))
        object.__setattr__(self, "model_version", _identifier("model_version", self.model_version))
        object.__setattr__(self, "data_version", _identifier("data_version", self.data_version))
        object.__setattr__(self, "state_family", _identifier("state_family", self.state_family))
        object.__setattr__(self, "shock_type", _identifier("shock_type", self.shock_type))
        if self.direction not in (-1, 1):
            raise ContractError("direction must be -1 or 1")
        object.__setattr__(self, "magnitude_z", _finite("magnitude_z", self.magnitude_z))
        object.__setattr__(self, "breadth", _unit_interval("breadth", self.breadth, optional=True))
        object.__setattr__(self, "quality", _identifier("quality", self.quality))
        object.__setattr__(self, "confidence", _unit_interval("confidence", self.confidence))
        object.__setattr__(self, "coverage", _unit_interval("coverage", self.coverage))
        freshness = str(self.freshness or "").strip().lower()
        if freshness not in _FRESHNESS:
            raise ContractError(f"freshness must be one of {sorted(_FRESHNESS)}")
        object.__setattr__(self, "freshness", freshness)
        if self.producer_schema != PRODUCER_SCHEMA:
            raise ContractError(f"producer_schema must be {PRODUCER_SCHEMA}")
        object.__setattr__(
            self, "conditions", MappingProxyType(_jsonable_mapping("conditions", self.conditions))
        )
        object.__setattr__(
            self,
            "regional_gates",
            MappingProxyType(_jsonable_mapping("regional_gates", self.regional_gates)),
        )
        object.__setattr__(
            self,
            "component_snapshot",
            MappingProxyType(_jsonable_mapping("component_snapshot", self.component_snapshot)),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SourceStateRef":
        """Build from the *adapter envelope*, never from the raw producer JSON."""

        if not isinstance(payload, Mapping):
            raise ContractError("source state reference must be an object")
        return cls(**dict(payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_schema": self.producer_schema,
            "observed_at": _iso_utc(self.observed_at),
            "known_at": _iso_utc(self.known_at),
            "source_snapshot_hash": self.source_snapshot_hash,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "state_family": self.state_family,
            "shock_type": self.shock_type,
            "direction": self.direction,
            "magnitude_z": self.magnitude_z,
            "breadth": self.breadth,
            "quality": self.quality,
            "confidence": self.confidence,
            "coverage": self.coverage,
            "freshness": self.freshness,
            "conditions": dict(self.conditions),
            "regional_gates": dict(self.regional_gates),
            "component_snapshot": dict(self.component_snapshot),
        }


@dataclass(frozen=True, slots=True)
class ShockRecord:
    shock_id: str
    first_detected: datetime
    source_observed_at: datetime
    shock_family: str
    shock_type: str
    direction: int
    magnitude_z: float
    breadth: float | None
    quality: str
    confidence: float
    coverage: float
    freshness: str
    source_snapshot_hash: str
    model_version: str
    data_version: str
    conditions: Mapping[str, Any]
    regional_gates: Mapping[str, Any]
    component_snapshot: Mapping[str, Any]
    producer_schema: str = PRODUCER_SCHEMA
    schema: str = LAB_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "shock_id", _identifier("shock_id", self.shock_id))
        first_detected = _utc_timestamp("first_detected", self.first_detected)
        observed_at = _utc_timestamp("source_observed_at", self.source_observed_at)
        if first_detected < observed_at:
            raise ContractError("first_detected may not precede source_observed_at")
        object.__setattr__(self, "first_detected", first_detected)
        object.__setattr__(self, "source_observed_at", observed_at)
        object.__setattr__(self, "shock_family", _identifier("shock_family", self.shock_family))
        object.__setattr__(self, "shock_type", _identifier("shock_type", self.shock_type))
        if self.direction not in (-1, 1):
            raise ContractError("direction must be -1 or 1")
        object.__setattr__(self, "magnitude_z", _finite("magnitude_z", self.magnitude_z))
        object.__setattr__(self, "breadth", _unit_interval("breadth", self.breadth, optional=True))
        object.__setattr__(self, "quality", _identifier("quality", self.quality))
        object.__setattr__(self, "confidence", _unit_interval("confidence", self.confidence))
        object.__setattr__(self, "coverage", _unit_interval("coverage", self.coverage))
        if self.freshness not in _FRESHNESS:
            raise ContractError(f"freshness must be one of {sorted(_FRESHNESS)}")
        object.__setattr__(self, "source_snapshot_hash", _snapshot_hash(self.source_snapshot_hash))
        object.__setattr__(self, "model_version", _identifier("model_version", self.model_version))
        object.__setattr__(self, "data_version", _identifier("data_version", self.data_version))
        object.__setattr__(
            self, "conditions", MappingProxyType(_jsonable_mapping("conditions", self.conditions))
        )
        object.__setattr__(
            self,
            "regional_gates",
            MappingProxyType(_jsonable_mapping("regional_gates", self.regional_gates)),
        )
        object.__setattr__(
            self,
            "component_snapshot",
            MappingProxyType(_jsonable_mapping("component_snapshot", self.component_snapshot)),
        )
        if self.producer_schema != PRODUCER_SCHEMA:
            raise ContractError(f"producer_schema must be {PRODUCER_SCHEMA}")
        if self.schema != LAB_SCHEMA:
            raise ContractError(f"schema must be {LAB_SCHEMA}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "producer_schema": self.producer_schema,
            "shock_id": self.shock_id,
            "first_detected": _iso_utc(self.first_detected),
            "source_observed_at": _iso_utc(self.source_observed_at),
            "shock_family": self.shock_family,
            "shock_type": self.shock_type,
            "direction": self.direction,
            "magnitude_z": self.magnitude_z,
            "breadth": self.breadth,
            "quality": self.quality,
            "confidence": self.confidence,
            "coverage": self.coverage,
            "freshness": self.freshness,
            "source_snapshot_hash": self.source_snapshot_hash,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "conditions": dict(self.conditions),
            "regional_gates": dict(self.regional_gates),
            "component_snapshot": dict(self.component_snapshot),
        }


def build_shock_record(source: SourceStateRef) -> ShockRecord:
    """Create a stable first-detection record from supplied producer evidence."""

    direction_label = "pos" if source.direction > 0 else "neg"
    identity = canonical_hash(
        {
            "known_at": _iso_utc(source.known_at),
            "shock_family": source.state_family,
            "direction": source.direction,
            "model_version": source.model_version,
            "data_version": source.data_version,
        }
    )[:12]
    shock_id = (
        f"liq_{source.known_at.date().isoformat()}_{source.state_family}_{direction_label}_{identity}"
    )
    return ShockRecord(
        shock_id=shock_id,
        first_detected=source.known_at,
        source_observed_at=source.observed_at,
        shock_family=source.state_family,
        shock_type=source.shock_type,
        direction=source.direction,
        magnitude_z=source.magnitude_z,
        breadth=source.breadth,
        quality=source.quality,
        confidence=source.confidence,
        coverage=source.coverage,
        freshness=source.freshness,
        source_snapshot_hash=source.source_snapshot_hash,
        model_version=source.model_version,
        data_version=source.data_version,
        conditions=source.conditions,
        regional_gates=source.regional_gates,
        component_snapshot=source.component_snapshot,
    )


@dataclass(frozen=True, slots=True)
class ForwardForecast:
    """Keep-first shadow forecast for one shock/target/horizon/model tuple."""

    shock_id: str
    target_id: str
    horizon_bdays: int
    model_version: str
    predicted_at: datetime
    relation_id: str
    relation_state: str
    expected_return: float | None
    interval_low: float | None
    interval_high: float | None
    probability_positive: float | None
    effective_n: int
    forecast_state: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "shock_id", _identifier("shock_id", self.shock_id))
        target_id = _identifier("target_id", self.target_id)
        if target_id not in TARGET_BY_ID:
            raise ContractError(f"target_id is not precommitted: {target_id}")
        object.__setattr__(self, "target_id", target_id)
        if self.horizon_bdays not in HORIZONS_BDAYS:
            raise ContractError("horizon_bdays is not precommitted")
        object.__setattr__(self, "model_version", _identifier("model_version", self.model_version))
        object.__setattr__(self, "predicted_at", _utc_timestamp("predicted_at", self.predicted_at))
        object.__setattr__(self, "relation_id", _identifier("relation_id", self.relation_id))
        state = str(self.relation_state or "").strip().lower()
        if state not in _RELATION_STATES:
            raise ContractError("relation_state is not in the closed lifecycle")
        object.__setattr__(self, "relation_state", state)
        if state not in {"discovered", "shadow", "demoted", "dead"}:
            raise ContractError("this W-LIQ.3 substrate may only emit non-authoritative relation states")
        object.__setattr__(self, "forecast_state", _identifier("forecast_state", self.forecast_state))
        if int(self.effective_n) < 0:
            raise ContractError("effective_n may not be negative")
        object.__setattr__(self, "effective_n", int(self.effective_n))
        numeric = {
            "expected_return": self.expected_return,
            "interval_low": self.interval_low,
            "interval_high": self.interval_high,
            "probability_positive": self.probability_positive,
        }
        for name, value in numeric.items():
            if value is not None:
                object.__setattr__(self, name, _finite(name, value))
        if self.probability_positive is not None:
            object.__setattr__(
                self,
                "probability_positive",
                _unit_interval("probability_positive", self.probability_positive),
            )
        bounds = (self.interval_low, self.expected_return, self.interval_high)
        if all(value is not None for value in bounds) and not (
            self.interval_low <= self.expected_return <= self.interval_high
        ):
            raise ContractError("forecast interval must contain expected_return")
        if self.forecast_state == "insufficient":
            if any(
                value is not None
                for value in (
                    self.expected_return,
                    self.interval_low,
                    self.interval_high,
                    self.probability_positive,
                )
            ):
                raise ContractError("insufficient forecasts must not fabricate an estimate")
        else:
            if self.expected_return is None or self.interval_low is None or self.interval_high is None:
                raise ContractError("estimated forecasts require an expected return and interval")
            if self.effective_n < 1:
                raise ContractError("estimated forecasts require positive effective_n")

    @property
    def forecast_key(self) -> str:
        return (
            f"{self.shock_id}:{self.target_id}:{self.horizon_bdays}:{self.model_version}"
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["predicted_at"] = _iso_utc(self.predicted_at)
        payload["forecast_key"] = self.forecast_key
        payload["schema"] = LAB_SCHEMA
        return payload


@dataclass(frozen=True, slots=True)
class ForecastGrade:
    forecast_key: str
    resolved_at: datetime
    realized_return: float
    outcome_source_hash: str

    def __post_init__(self) -> None:
        if len(str(self.forecast_key or "")) > 512 or self.forecast_key.count(":") < 3:
            raise ContractError("forecast_key is malformed")
        object.__setattr__(self, "resolved_at", _utc_timestamp("resolved_at", self.resolved_at))
        object.__setattr__(self, "realized_return", _finite("realized_return", self.realized_return))
        object.__setattr__(self, "outcome_source_hash", _snapshot_hash(self.outcome_source_hash))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LAB_SCHEMA,
            "forecast_key": self.forecast_key,
            "resolved_at": _iso_utc(self.resolved_at),
            "realized_return": self.realized_return,
            "outcome_source_hash": self.outcome_source_hash,
        }


def date_from_timestamp(value: datetime) -> date:
    return _utc_timestamp("timestamp", value).date()
