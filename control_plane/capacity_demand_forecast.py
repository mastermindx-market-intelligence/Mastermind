"""Rev5 D9/§3F advisory demand/reset forecast over the quota preview.

The forecast answers one question — *how much of the constrained pool's
near-term demand is caused by quota, and what should be done first* — and
answers it **only** from numbers that were observed.  It is presented
inside existing Capacity reporting (Rev5 D9 "Forecasting and subscription
recommendations", §5 l.309–327).

Law embedded here:

* **Advisory only, never an actor.**  ``authority`` is
  ``ADVISORY_PREVIEW_ONLY`` and the document states in terms that no
  purchase, order, checkout, billing change or account change is executed
  or proposed for execution.  Live pricing and entitlement changes need
  fresh evidence at the moment a purchasing decision is actually
  requested, so this module never carries a price or a purchase field at
  all.
* **Unknown stays unknown.**  A pool whose quota was not measured gets
  ``insufficient_observation`` with the exact reasons — never a fabricated
  percentage, never a generic token count converted into a subscription
  fraction.  A ``remaining_quota`` is echoed with its ``basis``; it is
  never re-derived into a different unit.
* **A range only where a rate was measured.**  An exhaustion *time* range
  needs a consumption rate: either a provider-supplied burn-rate bracket
  or two or more observed quota samples.  Without one the module still
  reports the observed headroom and the demand pressure as a bounded
  *slot* range, and records ``CONSUMPTION_RATE_NOT_OBSERVED`` as a data
  gap.  Occupancy is never silently converted into a depletion rate.
* **Cheap fixes outrank purchases.**  A host bottleneck, a writer
  bottleneck or an already-eligible spare route is recommended before any
  subscription change; a subscription change is the last action and only
  when demand is waiting and no eligible spare route exists.
* **Provenance is part of the answer.**  Every input document is digested
  (canonical JSON sha256) and every forwarded field says which document
  it came from; the preview's own ``observed_at``/``reset_at`` are
  forwarded, not recomputed.

The module is a pure function: no clock read, no filesystem access, no
network, no persistence, no mutation of any input mapping.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

__all__ = [
    "AUTHORITY",
    "SCHEMA",
    "POLICY_REVISION",
    "FORECAST_LIFETIME_SECONDS",
    "BOTTLENECK_HOST",
    "BOTTLENECK_WRITER",
    "BOTTLENECK_PROVIDER_QUOTA",
    "BOTTLENECK_UNKNOWN",
    "ACTION_REALLOCATE",
    "ACTION_FIX_HOST",
    "ACTION_FIX_WRITER",
    "ACTION_SUBSCRIPTION_LAST",
    "CapacityDemandForecastError",
    "canonical_digest",
    "produce_capacity_demand_forecast",
]

SCHEMA = "mastermind.capacity_demand_forecast/v1"
AUTHORITY = "ADVISORY_PREVIEW_ONLY"
POLICY_REVISION = "rev5-d9-advisory-forecast-1"

#: Default forecast lifetime when the preview carries no usable expiry.
#: Matches the 900s consumer freshness bound of the quota preview.
FORECAST_LIFETIME_SECONDS = 900
MAX_RESOURCES = 256
MAX_REASON_CODES = 12
MAX_ALTERNATIVES = 32

#: Observed remaining quota at or below this basis-percent is "near
#: exhausted".  A *reporting* threshold only; it never becomes a number in
#: the output.
NEAR_EXHAUSTED_PERCENT = 10.0

BOTTLENECK_HOST = "host"
BOTTLENECK_WRITER = "workspace_writer"
BOTTLENECK_PROVIDER_QUOTA = "provider_quota"
BOTTLENECK_UNKNOWN = "unknown"

ACTION_REALLOCATE = "reallocate_to_spare_route"
ACTION_FIX_HOST = "fix_host_bottleneck"
ACTION_FIX_WRITER = "fix_writer_bottleneck"
ACTION_SUBSCRIPTION_LAST = "subscription_change_LAST"

_ACTION_ORDER = {
    ACTION_FIX_HOST: 0,
    ACTION_FIX_WRITER: 0,
    ACTION_REALLOCATE: 1,
    ACTION_SUBSCRIPTION_LAST: 2,
}

EXHAUSTION_BOUNDED = "bounded_estimate"
EXHAUSTION_INSUFFICIENT = "insufficient_observation"

_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

#: Wait-reason vocabulary, matched as lowercase substrings.  Writer after
#: host is deliberate: a serialized checkout is a workspace/writer
#: constraint even when the registry calls the pool "capacity".
_HOST_WAIT_TOKENS = (
    "host_saturated",
    "host_capacity",
    "host_concurrency",
    "host_full",
    "host_bottleneck",
    "host_ready_full",
)
_WRITER_WAIT_TOKENS = (
    "workspace_writer",
    "writer_lock",
    "write_lock",
    "workspace_lock",
    "serialized_checkout",
    "checkout_serialized",
    "scratch_contention",
)
_QUOTA_WAIT_TOKENS = (
    "quota",
    "cooldown",
    "admission_wait",
    "resource_admission",
    "rate_limit",
    "429",
    "provider_cap",
    "window_exhausted",
)


class CapacityDemandForecastError(ValueError):
    """A forecast input is malformed.  The forecast is never guessed."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _refuse(code: str, detail: str | None = None) -> None:
    raise CapacityDemandForecastError(code, detail)


def canonical_digest(value: Mapping[str, Any] | Sequence[Any]) -> str:
    """sha256 over canonical JSON (sorted keys, no whitespace, ASCII).

    The digest is an identity of the *observed document*, so a consumer can
    prove which preview/ready-counts/broker read the forecast was built
    from.  Non-serialisable input refuses instead of being coerced.
    """

    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        _refuse("FORECAST_INPUT_NOT_CANONICAL")
    return hashlib.sha256(payload).hexdigest()


def _utc(value: object, *, code: str) -> datetime:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        _refuse(code)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _refuse(code)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _maybe_utc(value: object) -> datetime | None:
    """Best-effort parse of an owner-recorded timestamp; ``None`` if absent.

    Never invents a time: unparsable or redacted values stay unknown.
    """

    if type(value) is not str or not value or "<REDACTED" in value:
        return None
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: object) -> float | int | None:
    if type(value) in (int, float) and -1e15 < value < 1e15:
        return value
    return None


def _round(value: float, places: int = 4) -> float:
    return round(float(value), places)


def _reason_codes(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    codes = [str(item) for item in value if isinstance(item, str) and item]
    return codes[:MAX_REASON_CODES]


# --------------------------------------------------------------------------
# Ready-queue normalization
# --------------------------------------------------------------------------


def _normalize_ready_counts(
    ready_counts: Mapping[str, Any] | None, *, observed_at: datetime
) -> dict[str, Any]:
    """Normalize the ready-queue observation into counts we can attribute.

    Accepted shapes (all optional except the mapping itself)::

        {
          "observed_at": "<ISO Z>",
          "per_root":  {root_ref: ready_count},          # alias: "roots"
          "fleet_total": <int>,                          # alias: "fleet_ready"
          "wait_reason_counts": {
             "<resource_or_pool_ref>": {root_ref: count}  # counts only
             | {"roots": {root_ref: count},               # + typed reasons
                "reasons": {"<WAIT_REASON>": count}}
          }
        }

    A wait entry keyed by a resource ref or a pool ref is both accepted; a
    resource key is attributed to that resource, a pool key to its pool.
    Ready counts with no wait attribution stay fleet-level: this module
    never guesses which quota bucket a queued root belongs to.
    """

    normalized: dict[str, Any] = {
        "present": False,
        "observed_at": None,
        "per_root": {},
        "fleet_total": None,
        "waits": {},
        "unattributed_wait_requests": None,
    }
    if ready_counts is None:
        return normalized
    if not isinstance(ready_counts, Mapping):
        _refuse("FORECAST_READY_COUNTS_INVALID")

    normalized["present"] = True
    stamp = ready_counts.get("observed_at")
    if stamp is not None:
        parsed = _maybe_utc(stamp)
        if parsed is None:
            _refuse("FORECAST_READY_COUNTS_OBSERVED_AT_INVALID")
        if parsed > observed_at:
            _refuse("FORECAST_READY_COUNTS_IN_FUTURE")
        normalized["observed_at"] = _iso(parsed)

    per_root_raw = ready_counts.get("per_root", ready_counts.get("roots"))
    if per_root_raw is not None:
        if not isinstance(per_root_raw, Mapping):
            _refuse("FORECAST_READY_COUNTS_INVALID")
        for root, count in per_root_raw.items():
            if type(count) is not int or count < 0:
                _refuse("FORECAST_READY_COUNTS_INVALID", f"root {root!r}")
            if count:
                normalized["per_root"][str(root)] = int(count)

    fleet_raw = ready_counts.get("fleet_total", ready_counts.get("fleet_ready"))
    if fleet_raw is not None:
        if type(fleet_raw) is not int or fleet_raw < 0:
            _refuse("FORECAST_READY_COUNTS_INVALID", "fleet_total")
        normalized["fleet_total"] = int(fleet_raw)

    waits_raw = ready_counts.get("wait_reason_counts")
    if waits_raw is not None:
        if not isinstance(waits_raw, Mapping):
            _refuse("FORECAST_READY_COUNTS_INVALID", "wait_reason_counts")
        for ref, entry in waits_raw.items():
            if not isinstance(entry, Mapping):
                _refuse("FORECAST_READY_COUNTS_INVALID", f"wait entry {ref!r}")
            roots_raw = entry.get("roots", entry)
            if not isinstance(roots_raw, Mapping):
                _refuse("FORECAST_READY_COUNTS_INVALID", f"wait roots {ref!r}")
            roots: dict[str, int] = {}
            for root, count in roots_raw.items():
                if root == "reasons":
                    continue
                if type(count) is not int or count < 0:
                    _refuse("FORECAST_READY_COUNTS_INVALID", f"wait count {ref!r}")
                if count:
                    roots[str(root)] = int(count)
            reasons_raw = entry.get("reasons")
            reasons: dict[str, int] = {}
            if isinstance(reasons_raw, Mapping):
                for reason, count in reasons_raw.items():
                    if type(count) is not int or count < 0:
                        _refuse(
                            "FORECAST_READY_COUNTS_INVALID", f"wait reason {ref!r}"
                        )
                    if count:
                        reasons[str(reason)] = int(count)
            # A typed reason that names its own root (the admission
            # WAIT shape) is accepted too and adds one request.
            if not roots and type(entry.get("count")) is int and entry["count"] > 0:
                roots[str(entry.get("root_ref", "unattributed_root"))] = int(
                    entry["count"]
                )
            normalized["waits"][str(ref)] = {
                "roots": roots,
                "reasons": reasons,
            }

    unattributed = ready_counts.get("unattributed_wait_requests")
    if type(unattributed) is int and unattributed >= 0:
        normalized["unattributed_wait_requests"] = int(unattributed)
    return normalized


def _classify_wait_reasons(reasons: Mapping[str, int]) -> dict[str, int]:
    """Bucket observed wait-reason codes into host / writer / quota / unknown.

    Matching is on the reason token only — the module never infers a
    bottleneck from a pool name or from a registry label.
    """

    buckets = {
        BOTTLENECK_HOST: 0,
        BOTTLENECK_WRITER: 0,
        BOTTLENECK_PROVIDER_QUOTA: 0,
        BOTTLENECK_UNKNOWN: 0,
    }
    for reason, count in reasons.items():
        token = reason.lower()
        if any(marker in token for marker in _WRITER_WAIT_TOKENS):
            buckets[BOTTLENECK_WRITER] += count
        elif any(marker in token for marker in _HOST_WAIT_TOKENS):
            buckets[BOTTLENECK_HOST] += count
        elif any(marker in token for marker in _QUOTA_WAIT_TOKENS):
            buckets[BOTTLENECK_PROVIDER_QUOTA] += count
        else:
            buckets[BOTTLENECK_UNKNOWN] += count
    return buckets


# --------------------------------------------------------------------------
# Per-resource observation passthrough
# --------------------------------------------------------------------------


def _broker_counts(
    broker_observation: Mapping[str, Any] | None, row: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Broker lease counters for one resource, strictly as read.

    ``read_broker_observation`` publishes ``active_by_quota_scope`` keyed by
    quota scope (the ``shared_quota_resource_ref``) and
    ``reserved_by_pool_account`` keyed ``pool:account``.  Both are matched
    literally; no fuzzy join is performed.
    """

    if not isinstance(broker_observation, Mapping):
        return None
    resource_ref = str(row.get("shared_quota_resource_ref") or "")
    active = broker_observation.get("active_by_quota_scope")
    reserved = broker_observation.get("reserved_by_pool_account")
    active_count = None
    reserved_count = None
    if isinstance(active, Mapping) and resource_ref in active:
        value = active[resource_ref]
        if type(value) is int and value >= 0:
            active_count = value
    if isinstance(reserved, Mapping) and resource_ref in reserved:
        value = reserved[resource_ref]
        if type(value) is int and value >= 0:
            reserved_count = value
    cooldown_until = None
    cooldowns = broker_observation.get("cooldowns")
    if isinstance(cooldowns, Sequence) and not isinstance(cooldowns, (str, bytes)):
        for entry in cooldowns:
            if not isinstance(entry, Mapping):
                continue
            if str(entry.get("scope") or "") != resource_ref:
                continue
            parsed = _maybe_utc(entry.get("until"))
            if parsed is not None:
                cooldown_until = _iso(parsed)
    return {
        "active_leases": active_count,
        "reserved_leases": reserved_count,
        "cooldown_until": cooldown_until,
        "generation": broker_observation.get("generation"),
        "matched_by": "shared_quota_resource_ref",
    }


def _observation_series(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Optional provider_api observation samples: ``quota_observations``.

    A v2 preview may append live provider_api samples with the same
    envelope.  Each sample must carry ``observed_at`` and
    ``remaining_quota`` in the resource's own ``remaining_quota_basis``;
    anything else is dropped rather than repaired.
    """

    raw = row.get("quota_observations")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    samples: list[tuple[datetime, float]] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        at = _maybe_utc(entry.get("observed_at"))
        remaining = _number(entry.get("remaining_quota"))
        if at is None or remaining is None:
            continue
        samples.append((at, float(remaining)))
    samples.sort(key=lambda item: item[0])
    out: list[dict[str, Any]] = []
    for at, remaining in samples:
        if out and out[-1]["observed_at"] == _iso(at):
            out[-1]["remaining_quota"] = remaining
            continue
        out.append({"observed_at": _iso(at), "remaining_quota": remaining})
    return out


def _measured_rate_bracket(
    row: Mapping[str, Any], *, observed_at: datetime
) -> dict[str, Any] | None:
    """Lower/upper consumption rate, only from measured evidence.

    Two admissible sources, both measured elsewhere and merely forwarded:

    1. ``observed_consumption_rate_per_hour`` — a provider_api burn-rate
       bracket (``{"lower": x, "upper": y}``) in the basis' own unit.
    2. ``quota_observations`` — two or more samples; consecutive segment
       rates give the observed bracket.

    No other derivation is attempted: a single sample is headroom, not a
    rate.
    """

    declared = row.get("observed_consumption_rate_per_hour")
    if isinstance(declared, Mapping):
        lower = _number(declared.get("lower"))
        upper = _number(declared.get("upper"))
        if lower is not None and upper is not None and 0 <= lower <= upper:
            return {
                "rate_lower": float(lower),
                "rate_upper": float(upper),
                "source": "provider_api_burn_rate",
                "sample_count": None,
                "segments": [],
            }

    samples = _observation_series(row)
    if len(samples) < 2:
        return None
    segments: list[dict[str, Any]] = []
    for previous, current in zip(samples, samples[1:]):
        start = _maybe_utc(previous["observed_at"])
        end = _maybe_utc(current["observed_at"])
        if start is None or end is None:
            continue
        hours = (end - start).total_seconds() / 3600.0
        if hours <= 0:
            continue
        consumed = previous["remaining_quota"] - current["remaining_quota"]
        if consumed < 0:
            # A reset or a top-up between samples: the segment is not a
            # consumption measurement and is excluded, not clamped to 0.
            segments.append(
                {
                    "from": previous["observed_at"],
                    "to": current["observed_at"],
                    "hours": _round(hours, 4),
                    "consumed": _round(consumed, 4),
                    "rate": None,
                    "excluded_reason": "NEGATIVE_CONSUMPTION_RESET_OR_TOPUP",
                }
            )
            continue
        rate = consumed / hours
        segments.append(
            {
                "from": previous["observed_at"],
                "to": current["observed_at"],
                "hours": _round(hours, 4),
                "consumed": _round(consumed, 4),
                "rate": _round(rate, 6),
                "excluded_reason": None,
            }
        )
    usable = [item["rate"] for item in segments if item["rate"] is not None]
    if not usable:
        return None
    return {
        "rate_lower": min(usable),
        "rate_upper": max(usable),
        "source": "observation_series",
        "sample_count": len(samples),
        "segments": segments,
    }


def _exhaustion_forecast(
    *,
    row: Mapping[str, Any],
    observed: Mapping[str, Any],
    observed_at: datetime,
    cap: int | None,
    occupied_lower: int | None,
    occupied_upper: int | None,
    waiting_requests: int,
    data_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bounded exhaustion estimate, or an explicit honest unknown."""

    resource_ref = observed["shared_quota_resource_ref"]
    remaining = observed["remaining_quota"]
    basis = observed["remaining_quota_basis"]
    quota_observed = observed["quota_knowledge"] == "observed"
    reset = _maybe_utc(observed["reset_at"])
    quota_at = _maybe_utc(observed["quota_observed_at"])

    insufficient: list[str] = []
    if not quota_observed:
        insufficient.append("QUOTA_NOT_OBSERVED")
    if remaining is None:
        insufficient.append("REMAINING_QUOTA_NOT_OBSERVED")
    if basis is None:
        insufficient.append("REMAINING_QUOTA_BASIS_NOT_OBSERVED")
    if quota_at is None:
        insufficient.append("QUOTA_OBSERVED_AT_NOT_OBSERVED")

    if insufficient:
        data_gaps.append(
            {
                "code": "RESOURCE_QUOTA_UNOBSERVED",
                "resource_ref": resource_ref,
                "detail": "no measured quota; no rate or percentage is projected",
                "reason_codes": insufficient,
            }
        )
        return {
            "state": EXHAUSTION_INSUFFICIENT,
            "label": EXHAUSTION_INSUFFICIENT,
            "range": None,
            "percentages": None,
            "derivation_basis": None,
            "reason_codes": insufficient,
            "confidence": "none",
            "source": None,
            "provenance": {
                "quota_knowledge": observed["quota_knowledge"],
                "quota_source": observed["quota_source"],
                "quota_observed_at": observed["quota_observed_at"],
            },
        }

    assert remaining is not None and basis is not None and quota_at is not None
    reset_in_future = reset is not None and reset > observed_at
    if reset is not None and not reset_in_future:
        data_gaps.append(
            {
                "code": "RESET_AT_NOT_FUTURE",
                "resource_ref": resource_ref,
                "detail": "observed reset_at is not after the forecast instant",
            }
        )

    seconds_to_reset = (
        int((reset - observed_at).total_seconds()) if reset_in_future else None
    )
    if reset is None:
        data_gaps.append(
            {
                "code": "RESET_WINDOW_NOT_OBSERVED",
                "resource_ref": resource_ref,
                "detail": "no reset_at on the observed resource",
            }
        )

    # Observed slot pressure — measured occupancy, never a depletion rate.
    free_lower = None
    free_upper = None
    if cap is not None and cap > 0:
        free_lower = max(cap - (occupied_upper if occupied_upper is not None else 0), 0)
        free_upper = max(cap - (occupied_lower if occupied_lower is not None else 0), 0)

    rate = _measured_rate_bracket(row, observed_at=observed_at)
    if rate is None:
        data_gaps.append(
            {
                "code": "CONSUMPTION_RATE_NOT_OBSERVED",
                "resource_ref": resource_ref,
                "detail": (
                    "no provider_api burn-rate bracket and fewer than two "
                    "observed quota samples"
                ),
            }
        )

    forecast: dict[str, Any] = {
        "state": EXHAUSTION_BOUNDED,
        "label": "estimate",
        "unit": basis,
        "observed_remaining_quota": remaining,
        "reset_window": {
            "reset_at": observed["reset_at"],
            "quota_observed_at": observed["quota_observed_at"],
            "seconds_to_reset": seconds_to_reset,
            "reset_in_future": reset_in_future,
        },
        "slot_pressure": {
            "configured_concurrency_cap": cap,
            "occupied_slots_lower": occupied_lower,
            "occupied_slots_upper": occupied_upper,
            "free_slots_lower": free_lower,
            "free_slots_upper": free_upper,
            "waiting_requests_attributable": waiting_requests,
            "demand_exceeds_free_slots": (
                None
                if free_lower is None
                else bool(waiting_requests > free_lower)
            ),
        },
        "rate_bracket": None,
        "range": None,
        "reason_codes": [],
        "confidence": "low",
        "source": None,
        "provenance": {
            "quota_source": observed["quota_source"],
            "quota_observed_at": observed["quota_observed_at"],
            "quota_knowledge": observed["quota_knowledge"],
            "remaining_quota_basis": basis,
        },
    }

    if rate is not None:
        rate_lower = rate["rate_lower"]
        rate_upper = rate["rate_upper"]
        forecast["rate_bracket"] = {
            "lower_per_hour": _round(rate_lower, 6),
            "upper_per_hour": _round(rate_upper, 6),
            "unit": f"{basis}_per_hour",
            "source": rate["source"],
            "sample_count": rate["sample_count"],
            "segments": rate["segments"],
        }
        forecast["source"] = rate["source"]
        if rate_upper > 0 and reset_in_future and remaining > 0:
            seconds_lower = (remaining / rate_upper) * 3600.0
            seconds_upper = (
                (remaining / rate_lower) * 3600.0 if rate_lower > 0 else None
            )
            clamped = False
            if seconds_lower > seconds_to_reset:
                seconds_lower = float(seconds_to_reset)
                clamped = True
            if seconds_upper is not None and seconds_upper > seconds_to_reset:
                seconds_upper = float(seconds_to_reset)
                clamped = True
            forecast["range"] = {
                "kind": "seconds_to_exhaustion",
                "lower": int(round(seconds_lower)),
                "upper": None if seconds_upper is None else int(round(seconds_upper)),
                "upper_unbounded_reason": (
                    None if seconds_upper is not None else "OBSERVED_RATE_LOWER_BOUND_IS_ZERO"
                ),
                "clamped_at_reset": clamped,
                "exhausts_before_reset": bool(seconds_lower < seconds_to_reset),
            }
            forecast["confidence"] = (
                "medium"
                if rate["source"] == "provider_api_burn_rate"
                or (rate["sample_count"] or 0) >= 3
                else "low"
            )
            forecast["derivation_basis"] = {
                "formula": "seconds_to_exhaustion = remaining_quota / rate_per_hour",
                "rate_source": rate["source"],
                "rate_unit": f"{basis}_per_hour",
                "assumptions": [
                    "forward_shipped_rate_bracket_holds_for_the_rest_of_the_window",
                    "remaining_quota_basis_is_unchanged_between_samples",
                ],
            }
    else:
        forecast["reason_codes"].append("CONSUMPTION_RATE_NOT_OBSERVED")
        forecast["derivation_basis"] = {
            "formula": (
                "free_slots = configured_concurrency_cap - occupied_slots; "
                "demand = ready-queue requests attributed to this resource"
            ),
            "rate_source": None,
            "rate_unit": None,
            "assumptions": [
                "observed occupancy is a slot count, not a depletion rate",
                "no token-to-subscription conversion is performed",
            ],
        }
    if not reset_in_future:
        forecast["reason_codes"].append("RESET_WINDOW_STALE_OR_ABSENT")
        forecast["confidence"] = "low"
    return forecast


# --------------------------------------------------------------------------
# Recommendation assembly
# --------------------------------------------------------------------------


def _observed_spare_slots(row: Mapping[str, Any], broker: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Observed spare concurrency for one resource, or ``None`` if unknown.

    Spare capacity is advertised only when the cap was configured *and* the
    occupancy was observed on this preview row or by the broker read.
    """

    cap = _number(row.get("configured_concurrency_cap"))
    if cap is None or cap <= 0:
        return None
    preview_active = _number(row.get("active_slots"))
    preview_reserved = _number(row.get("reserved_slots"))
    if preview_active is None or preview_reserved is None:
        return None
    occupied_preview = int(preview_active + preview_reserved)
    occupied = occupied_preview
    source = "quota_preview"
    if broker is not None:
        broker_active = broker.get("active_leases")
        broker_reserved = broker.get("reserved_leases")
        broker_total = int((broker_active or 0) + (broker_reserved or 0))
        if broker_total > occupied:
            occupied = broker_total
            source = "broker_observation"
    return {
        "configured_concurrency_cap": int(cap),
        "occupied_slots": occupied,
        "spare_slots": max(int(cap) - occupied, 0),
        "occupancy_source": source,
        "broker_active_leases": None if broker is None else broker.get("active_leases"),
        "broker_reserved_leases": None if broker is None else broker.get("reserved_leases"),
    }


def _alternative_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """An eligible alternative, ranked only by observed facts."""

    if row.get("admission_eligibility") is not True:
        return None
    spare = _observed_spare_slots(row, None)
    if spare is None or spare["spare_slots"] <= 0:
        return None
    if row.get("quota_knowledge") != "observed":
        return None
    remaining = _number(row.get("remaining_quota"))
    if remaining is None:
        return None
    # A route that is itself near exhausted is not spare capacity, even when
    # the registry still marks it eligible.
    if (
        row.get("remaining_quota_basis") == "percent_of_window_remaining"
        and float(remaining) <= NEAR_EXHAUSTED_PERCENT
    ):
        return None
    return {
        "shared_quota_resource_ref": row.get("shared_quota_resource_ref"),
        "pool_ref": row.get("pool_ref"),
        "provider_ref": row.get("provider_ref"),
        "observed_spare_slots": spare["spare_slots"],
        "configured_concurrency_cap": spare["configured_concurrency_cap"],
        "occupied_slots": spare["occupied_slots"],
        "remaining_quota": row.get("remaining_quota"),
        "remaining_quota_basis": row.get("remaining_quota_basis"),
        "quota_source": row.get("quota_source"),
        "quota_observed_at": row.get("quota_observed_at"),
        "readiness_state": row.get("readiness_state"),
        "admission_eligibility": True,
        "ranking_basis": "observed_spare_slots_then_remaining_quota",
    }


def _eligible_without_observed_headroom(row: Mapping[str, Any]) -> bool:
    """Eligible, but its headroom was never measured — never ranked numerically."""

    return (
        row.get("admission_eligibility") is True
        and (row.get("quota_knowledge") != "observed"
             or _number(row.get("remaining_quota")) is None)
    )


def _expected_benefit(
    action: str,
    *,
    alternatives: Sequence[Mapping[str, Any]],
    waiting_requests: int,
    waiting_roots: Sequence[str],
    bottleneck: str,
) -> dict[str, Any]:
    spare_total = sum(int(item["observed_spare_slots"]) for item in alternatives)
    if action == ACTION_REALLOCATE and alternatives:
        statement = (
            f"{len(alternatives)} already-eligible route(s) show "
            f"{spare_total} observed spare slot(s) while {waiting_requests} "
            f"request(s) from {len(waiting_roots)} root(s) wait on the "
            f"constrained pool"
        )
    elif action == ACTION_FIX_HOST:
        statement = (
            f"{waiting_requests} request(s) wait on a host-saturated reason; "
            "freeing the host path is independent of quota headroom"
        )
    elif action == ACTION_FIX_WRITER:
        statement = (
            f"{waiting_requests} request(s) wait on a workspace/writer "
            "serialization reason; the pool has no spare writer slot to buy"
        )
    else:
        statement = (
            f"{waiting_requests} request(s) wait with no eligible route showing "
            "observed spare capacity; a subscription change is the last resort "
            "and is not executed here"
        )
    return {
        "kind": action,
        "observed_spare_slots_total": spare_total if alternatives else None,
        "waiting_requests_attributable": waiting_requests,
        "affected_root_count": len(waiting_roots),
        "bottleneck_kind": bottleneck,
        "statement": statement,
        "measured": bool(alternatives) or waiting_requests > 0,
    }


def _uncertainty(
    *,
    forecast: Mapping[str, Any],
    alternatives_without_headroom: Sequence[str],
    waiting_attributed: bool,
    bottleneck: str,
) -> dict[str, Any]:
    codes: list[str] = []
    if forecast.get("state") == EXHAUSTION_INSUFFICIENT:
        codes.append("QUOTA_NOT_OBSERVED")
    if forecast.get("rate_bracket") is None:
        codes.append("CONSUMPTION_RATE_NOT_OBSERVED")
    if forecast.get("reset_window", {}).get("seconds_to_reset") is None:
        codes.append("RESET_WINDOW_NOT_OBSERVED")
    if not waiting_attributed:
        codes.append("WAIT_ATTRIBUTION_NOT_OBSERVED")
    if alternatives_without_headroom:
        codes.append("ALTERNATIVE_HEADROOM_NOT_OBSERVED")
    if bottleneck == BOTTLENECK_UNKNOWN:
        codes.append("BOTTLENECK_KIND_NOT_OBSERVED")
    return {
        "codes": codes,
        "statement": (
            "Advisory only: no purchase, order, entitlement or account change "
            "is executed; live pricing needs fresh evidence at decision time. "
            "Uncertainty items are listed rather than estimated."
        ),
    }


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def produce_capacity_demand_forecast(
    *,
    quota_preview: Mapping[str, Any],
    ready_counts: Mapping[str, Any] | None,
    broker_observation: Mapping[str, Any] | None,
    observed_at: str,
    policy_revision: str = POLICY_REVISION,
) -> dict[str, Any]:
    """Compose the advisory demand/reset forecast for a quota preview.

    Every number in the result is either forwarded from an input document
    (with provenance) or computed from forwarded numbers by a formula named
    in ``derivation_basis``.  Unknown inputs produce a data gap, never a
    number.
    """

    if not isinstance(quota_preview, Mapping):
        _refuse("FORECAST_QUOTA_PREVIEW_INVALID")
    if broker_observation is not None and not isinstance(broker_observation, Mapping):
        _refuse("FORECAST_BROKER_OBSERVATION_INVALID")
    instant = _utc(observed_at, code="FORECAST_OBSERVED_AT_INVALID")
    if type(policy_revision) is not str or not policy_revision:
        _refuse("FORECAST_POLICY_REVISION_INVALID")

    resources_raw = quota_preview.get("resources")
    if not isinstance(resources_raw, Sequence) or isinstance(resources_raw, (str, bytes)):
        _refuse("FORECAST_QUOTA_PREVIEW_INVALID", "resources")
    if len(resources_raw) > MAX_RESOURCES:
        _refuse("FORECAST_QUOTA_PREVIEW_INVALID", "too many resources")

    data_gaps: list[dict[str, Any]] = []

    # ---- provenance -----------------------------------------------------
    preview_digest = canonical_digest(quota_preview)
    ready_digest = canonical_digest(ready_counts) if ready_counts is not None else None
    broker_digest = (
        canonical_digest(broker_observation)
        if broker_observation is not None
        else None
    )

    # ---- expiry ---------------------------------------------------------
    preview_expires = _maybe_utc(quota_preview.get("expires_at"))
    if preview_expires is not None and preview_expires > instant:
        expires_at = _iso(preview_expires)
        expiry_basis = "quota_preview_expires_at"
    else:
        expires_at = _iso(instant + timedelta(seconds=FORECAST_LIFETIME_SECONDS))
        expiry_basis = "forecast_default_lifetime"
        data_gaps.append(
            {
                "code": "PREVIEW_EXPIRES_AT_NOT_OBSERVED",
                "resource_ref": None,
                "detail": (
                    "preview carries no future expires_at; the "
                    f"{FORECAST_LIFETIME_SECONDS}s forecast lifetime applies"
                ),
            }
        )

    # ---- ready queue ----------------------------------------------------
    ready = _normalize_ready_counts(ready_counts, observed_at=instant)
    if not ready["present"]:
        data_gaps.append(
            {
                "code": "READY_COUNTS_ABSENT",
                "resource_ref": None,
                "detail": (
                    "no ready-queue observation supplied; quota-caused waiting "
                    "is unknown (not zero) and no demand figure is reported"
                ),
            }
        )
    elif not ready["waits"]:
        data_gaps.append(
            {
                "code": "WAIT_ATTRIBUTION_NOT_OBSERVED",
                "resource_ref": None,
                "detail": (
                    "ready counts carry no resource/pool wait attribution; "
                    "fleet demand stays unattributed to a quota bucket"
                ),
            }
        )
    if broker_observation is None:
        data_gaps.append(
            {
                "code": "BROKER_OBSERVATION_ABSENT",
                "resource_ref": None,
                "detail": "no broker lease read; occupancy uses preview slots only",
            }
        )

    # ---- per-resource rows ---------------------------------------------
    resource_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    by_ref: dict[str, dict[str, Any]] = {}
    for raw in resources_raw:
        if not isinstance(raw, Mapping):
            _refuse("FORECAST_QUOTA_PREVIEW_INVALID", "resource row")
        resource_ref = raw.get("shared_quota_resource_ref")
        if type(resource_ref) is not str or not resource_ref:
            _refuse("FORECAST_QUOTA_PREVIEW_INVALID", "resource ref")
        if resource_ref in by_ref:
            _refuse("FORECAST_QUOTA_PREVIEW_INVALID", f"duplicate ref {resource_ref}")
        raw_rows.append(dict(raw))
        by_ref[resource_ref] = dict(raw)

    for raw in raw_rows:
        resource_ref = str(raw["shared_quota_resource_ref"])
        pool_ref = raw.get("pool_ref")
        pool_key = str(pool_ref) if isinstance(pool_ref, str) and pool_ref else None
        broker = _broker_counts(broker_observation, raw)

        wait = ready["waits"].get(resource_ref)
        wait_key = resource_ref
        if wait is None and pool_key is not None:
            wait = ready["waits"].get(pool_key)
            wait_key = pool_key
        wait_roots = dict(wait["roots"]) if wait else {}
        wait_reason_counts = dict(wait["reasons"]) if wait else {}
        waiting_requests = sum(wait_roots.values())
        buckets = _classify_wait_reasons(wait_reason_counts)

        cap = _number(raw.get("configured_concurrency_cap"))
        cap_int = int(cap) if cap is not None else None
        preview_active = _number(raw.get("active_slots"))
        preview_reserved = _number(raw.get("reserved_slots"))
        occupied_lower = (
            int(preview_active + preview_reserved)
            if preview_active is not None and preview_reserved is not None
            else None
        )
        occupied_upper = occupied_lower
        if broker is not None and occupied_lower is not None:
            broker_total = int(
                (broker.get("active_leases") or 0) + (broker.get("reserved_leases") or 0)
            )
            if broker_total > occupied_upper:
                occupied_upper = broker_total

        cooldown = _maybe_utc(raw.get("cooldown_until"))
        cooldown_state = None
        if cooldown is not None:
            cooldown_state = "active" if cooldown > instant else "elapsed"

        observed = {
            "shared_quota_resource_ref": resource_ref,
            "pool_ref": pool_ref,
            "provider_ref": raw.get("provider_ref"),
            "quota_knowledge": raw.get("quota_knowledge"),
            "quota_source": raw.get("quota_source"),
            "quota_observed_at": raw.get("quota_observed_at"),
            "reset_at": raw.get("reset_at"),
            "cooldown_until": raw.get("cooldown_until"),
            "cooldown_state": cooldown_state,
            "remaining_quota": _number(raw.get("remaining_quota")),
            "remaining_quota_basis": raw.get("remaining_quota_basis"),
            "configured_concurrency_cap": cap_int,
            "active_slots": None if preview_active is None else int(preview_active),
            "reserved_slots": None if preview_reserved is None else int(preview_reserved),
            "occupied_slots_lower": occupied_lower,
            "occupied_slots_upper": occupied_upper,
            "admission_eligibility": raw.get("admission_eligibility") is True,
            "readiness_state": raw.get("readiness_state"),
            "reason_codes": _reason_codes(raw.get("reason_codes")),
            "provenance": {
                "quota_fields": "quota_preview.resources[]",
                "preview_digest": preview_digest,
                "broker": broker,
                "broker_digest": broker_digest,
                "observed_at": quota_preview.get("observed_at")
                or quota_preview.get("as_of"),
            },
        }

        forecast = _exhaustion_forecast(
            row=raw,
            observed=observed,
            observed_at=instant,
            cap=cap_int,
            occupied_lower=occupied_lower,
            occupied_upper=occupied_upper,
            waiting_requests=waiting_requests,
            data_gaps=data_gaps,
        )

        remaining = observed["remaining_quota"]
        near_exhausted = (
            remaining is not None
            and observed["remaining_quota_basis"] == "percent_of_window_remaining"
            and float(remaining) <= NEAR_EXHAUSTED_PERCENT
        )
        saturated = (
            cap_int is not None
            and occupied_upper is not None
            and occupied_upper >= cap_int
        )
        constraint_reasons: list[str] = []
        if waiting_requests > 0:
            constraint_reasons.append("QUOTA_ATTRIBUTED_WAITING")
        if cooldown_state == "active":
            constraint_reasons.append("COOLDOWN_ACTIVE")
        if near_exhausted:
            constraint_reasons.append("REMAINING_BELOW_THRESHOLD")
        if saturated:
            constraint_reasons.append("CONCURRENCY_SATURATED")
        constrained = bool(constraint_reasons)

        resource_rows.append(
            {
                "shared_quota_resource_ref": resource_ref,
                "pool_ref": pool_ref,
                "provider_ref": raw.get("provider_ref"),
                "observed": observed,
                "constrained": constrained,
                "constraint_reasons": constraint_reasons,
                "quota_caused_waiting": {
                    "roots": wait_roots,
                    "requests": waiting_requests,
                    "attribution_ref": wait_key if wait else None,
                    "attribution_source": "ready_counts.wait_reason_counts" if wait else None,
                    "wait_reason_counts": wait_reason_counts,
                    "bottleneck_buckets": buckets,
                },
                "exhaustion_forecast": forecast,
                "confidence": {
                    "quota_knowledge": observed["quota_knowledge"] or "unknown",
                    "reset_window": (
                        "observed"
                        if forecast.get("reset_window", {}).get("reset_in_future")
                        else "unknown_or_stale"
                    ),
                    "consumption_rate": (
                        "measured"
                        if forecast.get("rate_bracket") is not None
                        else "not_observed"
                    ),
                    "occupancy": (
                        "observed"
                        if occupied_upper is not None
                        else "not_observed"
                    ),
                    "overall": forecast["confidence"],
                },
            }
        )

    # ---- alternatives (observed spare capacity only) --------------------
    if broker_observation is not None and not any(
        row["observed"]["provenance"]["broker"]
        and (
            row["observed"]["provenance"]["broker"]["active_leases"] is not None
            or row["observed"]["provenance"]["broker"]["reserved_leases"] is not None
        )
        for row in resource_rows
    ):
        data_gaps.append(
            {
                "code": "BROKER_SCOPE_MATCHED_NOTHING",
                "resource_ref": None,
                "detail": (
                    "the broker read returned no lease counter for any preview "
                    "resource ref; broker occupancy stays unknown, not zero"
                ),
            }
        )
    alternatives_all: list[dict[str, Any]] = []
    unknown_headroom: list[str] = []
    for row in raw_rows:
        alternative = _alternative_row(row)
        if alternative is not None:
            alternatives_all.append(alternative)
            continue
        if _eligible_without_observed_headroom(row):
            unknown_headroom.append(str(row["shared_quota_resource_ref"]))
    alternatives_all.sort(
        key=lambda item: (
            -int(item["observed_spare_slots"]),
            -float(item["remaining_quota"]),
            str(item["shared_quota_resource_ref"]),
        )
    )
    alternatives_all = alternatives_all[:MAX_ALTERNATIVES]

    # ---- recommendations, grouped by constrained pool -------------------
    constrained_rows = [row for row in resource_rows if row["constrained"]]
    pools: dict[str, list[dict[str, Any]]] = {}
    for row in constrained_rows:
        key = str(row["pool_ref"]) if row["pool_ref"] else str(
            row["shared_quota_resource_ref"]
        )
        pools.setdefault(key, []).append(row)

    recommendations: list[dict[str, Any]] = []
    constrained_without_action: list[dict[str, Any]] = []
    for pool_key in sorted(pools):
        rows = pools[pool_key]
        refs = [str(row["shared_quota_resource_ref"]) for row in rows]
        roots: dict[str, int] = {}
        buckets = {
            BOTTLENECK_HOST: 0,
            BOTTLENECK_WRITER: 0,
            BOTTLENECK_PROVIDER_QUOTA: 0,
            BOTTLENECK_UNKNOWN: 0,
        }
        # One ready-count observation may be attributed to a whole pool.  Each
        # distinct attribution is counted exactly once, so a pool-scoped entry
        # seen through several resources is never multiplied.
        seen_attribution: set[str] = set()
        for row in rows:
            waiting = row["quota_caused_waiting"]
            attribution = waiting["attribution_ref"]
            if attribution is None or attribution in seen_attribution:
                continue
            seen_attribution.add(str(attribution))
            for root, count in waiting["roots"].items():
                roots[root] = roots.get(root, 0) + count
            for kind, count in waiting["bottleneck_buckets"].items():
                buckets[kind] += count
        waiting_requests = sum(roots.values())

        if buckets[BOTTLENECK_HOST] > 0:
            bottleneck = BOTTLENECK_HOST
        elif buckets[BOTTLENECK_WRITER] > 0:
            bottleneck = BOTTLENECK_WRITER
        elif buckets[BOTTLENECK_PROVIDER_QUOTA] > 0:
            bottleneck = BOTTLENECK_PROVIDER_QUOTA
        else:
            bottleneck = BOTTLENECK_UNKNOWN

        alternatives = [
            item for item in alternatives_all
            if str(item["shared_quota_resource_ref"]) not in refs
        ][:8]

        # Action law: local fix first, then an already-eligible spare
        # route, and a subscription change only when demand is waiting and
        # no eligible route shows observed spare capacity.
        if bottleneck == BOTTLENECK_HOST:
            action = ACTION_FIX_HOST
        elif bottleneck == BOTTLENECK_WRITER:
            action = ACTION_FIX_WRITER
        elif alternatives:
            action = ACTION_REALLOCATE
        elif waiting_requests > 0:
            action = ACTION_SUBSCRIPTION_LAST
        else:
            constrained_without_action.append(
                {
                    "pool_ref": pool_key,
                    "constrained_resource_refs": refs,
                    "constraint_reasons": sorted(
                        {reason for row in rows for reason in row["constraint_reasons"]}
                    ),
                    "reason": "NO_OBSERVED_DEMAND_AND_NO_ELIGIBLE_SPARE_ROUTE",
                }
            )
            continue

        primary = rows[0]
        forecast = primary["exhaustion_forecast"]
        recommendation_body = {
            "pool_ref": pool_key,
            "constrained_resource_refs": refs,
            "action": action,
            "waiting_requests": waiting_requests,
            "alternatives": [
                item["shared_quota_resource_ref"] for item in alternatives
            ],
        }
        recommendations.append(
            {
                "recommendation_id": "rec:"
                + canonical_digest(recommendation_body)[:16],
                "constrained_pool_window": {
                    "pool_ref": pool_key,
                    "constrained_resource_refs": refs,
                    "reset_at": primary["observed"]["reset_at"],
                    "cooldown_until": primary["observed"]["cooldown_until"],
                    "cooldown_state": primary["observed"]["cooldown_state"],
                    "quota_observed_at": primary["observed"]["quota_observed_at"],
                    "remaining_quota": primary["observed"]["remaining_quota"],
                    "remaining_quota_basis": primary["observed"][
                        "remaining_quota_basis"
                    ],
                },
                "affected_roots": sorted(roots),
                "quota_caused_waiting_requests": waiting_requests,
                "forecast_range": {
                    "state": forecast["state"],
                    "label": forecast.get("label"),
                    "range": forecast.get("range"),
                    "unit": forecast.get("unit"),
                    "reset_window": forecast.get("reset_window"),
                    "slot_pressure": forecast.get("slot_pressure"),
                    "confidence": forecast["confidence"],
                    "source": forecast.get("source"),
                    "reason_codes": list(forecast.get("reason_codes") or []),
                },
                "forecast_confidence": forecast["confidence"],
                "forecast_source": forecast.get("source"),
                "eligible_unused_alternatives": alternatives,
                "eligible_alternatives_without_observed_headroom": [
                    ref for ref in unknown_headroom if ref not in refs
                ],
                "bottleneck_kind": bottleneck,
                "bottleneck_evidence": {
                    "host_wait_requests": buckets[BOTTLENECK_HOST],
                    "writer_wait_requests": buckets[BOTTLENECK_WRITER],
                    "quota_wait_requests": buckets[BOTTLENECK_PROVIDER_QUOTA],
                    "unclassified_wait_requests": buckets[BOTTLENECK_UNKNOWN],
                    "source": (
                        "ready_counts.wait_reason_counts"
                        if any(buckets.values())
                        else None
                    ),
                },
                "proposed_action": action,
                "expected_benefit": _expected_benefit(
                    action,
                    alternatives=alternatives,
                    waiting_requests=waiting_requests,
                    waiting_roots=sorted(roots),
                    bottleneck=bottleneck,
                ),
                "remaining_uncertainty": _uncertainty(
                    forecast=forecast,
                    alternatives_without_headroom=unknown_headroom,
                    waiting_attributed=bool(roots),
                    bottleneck=bottleneck,
                ),
                "advisory_only": True,
            }
        )

    recommendations.sort(
        key=lambda item: (
            _ACTION_ORDER[item["proposed_action"]],
            item["constrained_pool_window"]["pool_ref"] or "",
        )
    )

    # ---- honest bookkeeping ---------------------------------------------
    unknown_quota_refs = [
        row["shared_quota_resource_ref"]
        for row in resource_rows
        if row["exhaustion_forecast"]["state"] == EXHAUSTION_INSUFFICIENT
    ]
    if unknown_quota_refs:
        data_gaps.append(
            {
                "code": "QUOTA_UNOBSERVED_RESOURCES",
                "resource_ref": None,
                "detail": f"{len(unknown_quota_refs)} resource(s) with no measured quota",
            }
        )

    knowledge_summary = quota_preview.get("knowledge_summary")
    if not any(
        isinstance(raw.get("usage_by_class", raw.get("class_usage")), Mapping)
        for raw in raw_rows
    ):
        data_gaps.append(
            {
                "code": "CLASS_SPECIFIC_USAGE_NOT_OBSERVED",
                "resource_ref": None,
                "detail": (
                    "the preview carries no per-complexity-class usage; demand is "
                    "reported per pool, not per class"
                ),
            }
        )
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "policy_revision": policy_revision,
        "advisory_only": True,
        "observed_at": _iso(instant),
        "expires_at": expires_at,
        "expiry_basis": expiry_basis,
        "purchases_executed": False,
        "account_changes_executed": False,
        "automatic_actions": False,
        "pricing": {
            "state": "NOT_EVALUATED",
            "reason": (
                "live pricing and entitlement changes require fresh evidence at "
                "the moment a purchasing decision is requested"
            ),
        },
        "input_provenance": {
            "quota_preview": {
                "sha256": preview_digest,
                "schema": quota_preview.get("schema"),
                "authority": quota_preview.get("authority"),
                "observed_at": quota_preview.get("observed_at")
                or quota_preview.get("as_of"),
                "resource_count": len(resource_rows),
                "knowledge_summary": knowledge_summary,
            },
            "ready_counts": {
                "sha256": ready_digest,
                "present": ready["present"],
                "observed_at": ready["observed_at"],
                "per_root_roots": sorted(ready["per_root"]),
                "fleet_total": ready["fleet_total"],
                "attributed_refs": sorted(ready["waits"]),
            },
            "broker_observation": {
                "sha256": broker_digest,
                "present": broker_observation is not None,
                "generation": (
                    broker_observation.get("generation")
                    if isinstance(broker_observation, Mapping)
                    else None
                ),
            },
        },
        "demand_observation": {
            "fleet_ready_total": ready["fleet_total"],
            "per_root_ready": ready["per_root"],
            "attributed_wait_requests": sum(
                sum(entry["roots"].values()) for entry in ready["waits"].values()
            ),
            "unattributed_wait_requests": ready["unattributed_wait_requests"],
            "attribution_state": (
                "observed" if ready["waits"] else ("absent" if not ready["present"] else "unattributed")
            ),
        },
        "data_gaps": _dedupe_gaps(data_gaps),
        "resources": resource_rows,
        "recommendations": recommendations,
        "constrained_without_action": constrained_without_action,
        "counts": {
            "resources": len(resource_rows),
            "observed_quota_resources": sum(
                1 for row in resource_rows if row["observed"]["quota_knowledge"] == "observed"
            ),
            "constrained_resources": len(constrained_rows),
            "recommendations": len(recommendations),
            "eligible_alternatives_with_observed_headroom": len(alternatives_all),
        },
    }


def _dedupe_gaps(gaps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for gap in gaps:
        key = (str(gap.get("code")), str(gap.get("resource_ref")))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(gap))
    return out
