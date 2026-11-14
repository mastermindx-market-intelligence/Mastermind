"""Pure research-context consumer; no registry, scheduler, rank or trade effects."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
import re
from typing import Any

SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class SourceObservation:
    instrument: str
    economic_session: date
    observed_through: datetime | None
    first_observed_at: datetime
    sha256: str
    source_id: str
    units: str
    reconstructed: bool = False


@dataclass(frozen=True)
class ModelObservation:
    instrument: str
    train_through: datetime | None
    completed_at: datetime
    input_sha256: tuple[str, ...]
    version: str
    next_daily_variance: float | None


def aware(t: datetime) -> bool:
    return isinstance(t, datetime) and t.tzinfo is not None and t.utcoffset() is not None


def shadow_context(*, instrument: str, decision_at: datetime,
                   price: SourceObservation | None, options: SourceObservation | None,
                   fit: ModelObservation | None, expected_options_session: date,
                   max_age: timedelta = timedelta(days=4)) -> dict[str, Any]:
    """Validate supplied facts, not authenticate them or confer trading authority.

    The caller must supply real capture/fit receipts. Historical simulations
    cannot backdate first_observed_at. Unknown earlier publication is harmless
    for a PRESENT decision only if actual capture already proves availability.
    """
    if not aware(decision_at) or not isinstance(expected_options_session, date):
        raise ValueError("aware decision clock and expected economic session required")
    if not timedelta(0) < max_age <= timedelta(days=7):
        raise ValueError("staleness bound must be positive and at most seven days")
    reasons: list[str] = []
    sources: dict[str, Any] = {}
    for label, source, units in (("PRICE", price, "raw_ohlc"),
                                  ("OPTIONS", options, "gex_bn_iv_annual_decimal")):
        if source is None:
            reasons.append(label+"_MISSING")
            continue
        if source.instrument != instrument:
            reasons.append(label+"_INSTRUMENT_MISMATCH")
        if source.units != units:
            reasons.append(label+"_UNITS_MISMATCH")
        if not isinstance(source.sha256, str) or not SHA256.fullmatch(source.sha256):
            reasons.append(label+"_DIGEST_INVALID")
        date_ok = type(source.economic_session) is date
        if not source.source_id or not date_ok:
            reasons.append(label+"_IDENTITY_MISSING")
        elif decision_at.date()-source.economic_session > max_age:
            reasons.append(label+"_STALE")
        elif source.economic_session > decision_at.date():
            reasons.append(label+"_FUTURE_SESSION")
        clock_ok = aware(source.observed_through) and aware(source.first_observed_at)
        if not clock_ok:
            reasons.append(label+"_CLOCK_UNKNOWN")
        else:
            if source.observed_through > source.first_observed_at:
                reasons.append(label+"_CLOCK_ORDER_INVALID")
            if source.first_observed_at > decision_at:
                reasons.append(label+"_NOT_YET_AVAILABLE")
            if decision_at-source.observed_through > max_age:
                reasons.append(label+"_STALE")
            if source.observed_through > decision_at:
                reasons.append(label+"_FUTURE_OBSERVATION")
        sources[label.lower()] = {"source_id": source.source_id, "sha256": source.sha256,
                                  "economic_session": source.economic_session.isoformat() if date_ok else None,
                                  "reconstructed": source.reconstructed}
    if options is not None and options.economic_session != expected_options_session:
        reasons.append("OPTIONS_SESSION_MISMATCH")
    if price is not None and type(price.economic_session) is date and expected_options_session >= price.economic_session:
        reasons.append("OPTIONS_LAG_CONTRACT_INVALID")
    if fit is None:
        reasons.append("FIT_MISSING")
    else:
        if fit.instrument != instrument:
            reasons.append("FIT_INSTRUMENT_MISMATCH")
        if not fit.version:
            reasons.append("MODEL_VERSION_MISSING")
        if not aware(fit.train_through) or not aware(fit.completed_at):
            reasons.append("FIT_CLOCK_UNKNOWN")
        else:
            if fit.train_through > fit.completed_at or fit.completed_at > decision_at:
                reasons.append("FIT_CLOCK_ORDER_INVALID")
            if price is not None and aware(price.observed_through) and fit.train_through > price.observed_through:
                reasons.append("FIT_USES_FUTURE_PRICE")
            if price is not None and aware(price.first_observed_at) and price.first_observed_at > fit.completed_at:
                reasons.append("FIT_PRECEDES_INPUT_CAPTURE")
        digests_ok = isinstance(fit.input_sha256, tuple) and len(fit.input_sha256) > 0
        if price is not None and (not digests_ok or price.sha256 not in fit.input_sha256):
            reasons.append("FIT_SOURCE_MISMATCH")
        if not digests_ok or not all(isinstance(h, str) and SHA256.fullmatch(h) for h in fit.input_sha256):
            reasons.append("FIT_DIGEST_INVALID")
        if (fit.next_daily_variance is None or not isinstance(fit.next_daily_variance, (int, float))
                or isinstance(fit.next_daily_variance, bool)
                or not math.isfinite(fit.next_daily_variance*252) or fit.next_daily_variance <= 0):
            reasons.append("FORECAST_UNAVAILABLE")
    reasons = sorted(set(reasons))
    return {"schema": "mastermind.apmem_shadow_context.v1", "instrument": instrument,
            "decision_at": decision_at.astimezone(timezone.utc).isoformat(),
            "status": "ABSTAIN" if reasons else "CONTEXT_ONLY",
            "reason_codes": reasons, "sources": sources,
            "forecast_annualized_percent": None if reasons else math.sqrt(fit.next_daily_variance*252)*100,
            "model_version": fit.version if fit is not None else None,
            "evidence_maturity": "unqualified_research",
            "may_rank": False, "may_size": False, "may_trade": False,
            "note": "Capture/fit receipts require external provenance. This pure validator does not authenticate them."}
