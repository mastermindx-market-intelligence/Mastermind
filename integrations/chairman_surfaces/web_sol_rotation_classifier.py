"""Pure Web-Sol conversation-health classification for exact bound sessions.

This module owns no browser, lifecycle, retry loop, history store, RuntimeBinding,
or provider session. Callers supply the current closed Web-Sol probe and the
consecutive terminal turn-failure evidence already owned by their runtime.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from integrations.chairman_surfaces import web_sol_protocol as wsp


REPEATED_FAILURE_THRESHOLD = 3
MAX_FAILURE_EVIDENCE = 8
_TURN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_FAILURE_KEYS = frozenset(
    {
        "turn_id",
        "conversation_fingerprint",
        "observed_at",
        "provider_error_present",
        "generation_state",
        "composer_available",
        "page_responsive",
    }
)


class WebSolRotationClassifierError(ValueError):
    """Closed Web-Sol health evidence is malformed or contradictory."""


class SessionHealth(str, Enum):
    SESSION_HEALTHY = "SESSION_HEALTHY"
    ROTATION_SUSPECTED = "ROTATION_SUSPECTED"
    ROTATION_REQUIRED = "ROTATION_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    PROVIDER_TRANSIENT = "PROVIDER_TRANSIENT"
    SURFACE_UNUSABLE = "SURFACE_UNUSABLE"
    UNKNOWN = "UNKNOWN"


class RotationReason(str, Enum):
    MANUAL_RETIREMENT = "MANUAL_RETIREMENT"
    CONTEXT_LIMIT_SUSPECTED = "CONTEXT_LIMIT_SUSPECTED"
    REPEATED_TERMINAL_GENERATION_FAILURE = "REPEATED_TERMINAL_GENERATION_FAILURE"
    SURFACE_UNUSABLE = "SURFACE_UNUSABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TerminalGenerationFailure:
    turn_id: str
    conversation_fingerprint: str
    observed_at: datetime
    provider_error_present: bool
    generation_state: str
    composer_available: bool | None
    page_responsive: bool


@dataclass(frozen=True)
class RotationClassification:
    state: SessionHealth
    reason: RotationReason | None
    distinct_terminal_failures: int
    exact_conversation_loaded: bool
    page_responsive: bool
    composer_available: bool | None
    generation_state: str
    auth_required: bool | None
    provider_error_present: bool | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "mastermind.web_sol_rotation_classification/v1",
            "state": self.state.value,
            "reason": self.reason.value if self.reason else None,
            "distinct_terminal_failures": self.distinct_terminal_failures,
            "exact_conversation_loaded": self.exact_conversation_loaded,
            "page_responsive": self.page_responsive,
            "composer_available": self.composer_available,
            "generation_state": self.generation_state,
            "auth_required": self.auth_required,
            "provider_error_present": self.provider_error_present,
        }


def _parse_zulu(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise WebSolRotationClassifierError(f"{field} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise WebSolRotationClassifierError(
            f"{field} must be an ISO-8601 UTC timestamp"
        ) from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise WebSolRotationClassifierError(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _terminal_failure(value: Mapping[str, Any]) -> TerminalGenerationFailure:
    if not isinstance(value, Mapping) or set(value) != _FAILURE_KEYS:
        raise WebSolRotationClassifierError("terminal failure evidence has invalid fields")
    turn_id = value["turn_id"]
    fingerprint = value["conversation_fingerprint"]
    if not isinstance(turn_id, str) or _TURN_RE.fullmatch(turn_id) is None:
        raise WebSolRotationClassifierError("turn_id is not a bounded opaque token")
    if not isinstance(fingerprint, str) or _HEX64_RE.fullmatch(fingerprint) is None:
        raise WebSolRotationClassifierError("conversation_fingerprint must be lowercase hex64")
    if value["provider_error_present"] is not True:
        raise WebSolRotationClassifierError("terminal failure must carry provider_error_present=true")
    if value["generation_state"] != "idle":
        raise WebSolRotationClassifierError("terminal failure must be observed after generation stops")
    if type(value["page_responsive"]) is not bool:
        raise WebSolRotationClassifierError("page_responsive must be boolean")
    composer = value["composer_available"]
    if composer is not None and type(composer) is not bool:
        raise WebSolRotationClassifierError("composer_available must be boolean or null")
    return TerminalGenerationFailure(
        turn_id=turn_id,
        conversation_fingerprint=fingerprint,
        observed_at=_parse_zulu(value["observed_at"], field="observed_at"),
        provider_error_present=True,
        generation_state="idle",
        composer_available=composer,
        page_responsive=value["page_responsive"],
    )


def _validated_failures(
    values: Iterable[Mapping[str, Any]], *, conversation_fingerprint: str
) -> tuple[TerminalGenerationFailure, ...]:
    rows = tuple(_terminal_failure(value) for value in values)
    if len(rows) > MAX_FAILURE_EVIDENCE:
        raise WebSolRotationClassifierError("terminal failure evidence exceeds bounded history")
    if any(row.conversation_fingerprint != conversation_fingerprint for row in rows):
        raise WebSolRotationClassifierError("terminal failure evidence crosses conversation identity")
    timestamps = [row.observed_at for row in rows]
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise WebSolRotationClassifierError("terminal failure evidence must be strictly chronological")
    return rows


def _result(
    state: SessionHealth,
    reason: RotationReason | None,
    failures: int,
    probe: Mapping[str, Any],
) -> RotationClassification:
    return RotationClassification(
        state=state,
        reason=reason,
        distinct_terminal_failures=failures,
        exact_conversation_loaded=probe["exact_conversation_loaded"],
        page_responsive=probe["page_responsive"],
        composer_available=probe["composer_available"],
        generation_state=probe["generation_state"],
        auth_required=probe["auth_required"],
        provider_error_present=probe["provider_error_present"],
    )


def classify_session_health(
    *,
    current_probe: Mapping[str, Any],
    conversation_fingerprint: str,
    consecutive_terminal_failures: Iterable[Mapping[str, Any]] = (),
    manual_retirement: bool = False,
    supported_context_limit: bool = False,
    surface_recovery_exhausted: bool = False,
) -> RotationClassification:
    """Classify one exact bound ChatGPT conversation without performing effects.

    ``consecutive_terminal_failures`` contains one closed record per failed
    provider/model turn since the last successful turn. When Executive OHF owns
    the caller, this identity is its canonical ``TurnRef.turn_id``; it is never
    the Executive ``attempt_id``. Repeated polling of one failed turn
    must reuse its turn_id; duplicate turn ids therefore cannot inflate the
    rotation threshold.
    """

    if not isinstance(conversation_fingerprint, str) or _HEX64_RE.fullmatch(
        conversation_fingerprint
    ) is None:
        raise WebSolRotationClassifierError("conversation_fingerprint must be lowercase hex64")
    for name, flag in (
        ("manual_retirement", manual_retirement),
        ("supported_context_limit", supported_context_limit),
        ("surface_recovery_exhausted", surface_recovery_exhausted),
    ):
        if type(flag) is not bool:
            raise WebSolRotationClassifierError(f"{name} must be boolean")

    try:
        probe = wsp.validate_probe(dict(current_probe))
    except wsp.WebSolProtocolError as exc:
        raise WebSolRotationClassifierError("current probe is not a valid closed Web-Sol probe") from exc

    failures = _validated_failures(
        consecutive_terminal_failures,
        conversation_fingerprint=conversation_fingerprint,
    )
    distinct_failures = len({row.turn_id for row in failures})

    if manual_retirement:
        return _result(
            SessionHealth.ROTATION_REQUIRED,
            RotationReason.MANUAL_RETIREMENT,
            distinct_failures,
            probe,
        )
    if probe["auth_required"] is True:
        return _result(SessionHealth.AUTH_REQUIRED, None, distinct_failures, probe)
    if supported_context_limit:
        return _result(
            SessionHealth.ROTATION_REQUIRED,
            RotationReason.CONTEXT_LIMIT_SUSPECTED,
            distinct_failures,
            probe,
        )
    if surface_recovery_exhausted:
        return _result(
            SessionHealth.SURFACE_UNUSABLE,
            RotationReason.SURFACE_UNUSABLE,
            distinct_failures,
            probe,
        )
    if not probe["target_present"] or not probe["exact_conversation_loaded"]:
        return _result(SessionHealth.UNKNOWN, RotationReason.UNKNOWN, distinct_failures, probe)
    if not probe["page_responsive"] or probe["generation_state"] == "unknown":
        return _result(SessionHealth.UNKNOWN, RotationReason.UNKNOWN, distinct_failures, probe)
    if probe["generation_state"] == "active":
        return _result(SessionHealth.SESSION_HEALTHY, None, distinct_failures, probe)

    if probe["provider_error_present"] is True:
        corroborated = all(
            row.page_responsive and row.composer_available is True for row in failures
        )
        if distinct_failures >= REPEATED_FAILURE_THRESHOLD and corroborated:
            return _result(
                SessionHealth.ROTATION_REQUIRED,
                RotationReason.REPEATED_TERMINAL_GENERATION_FAILURE,
                distinct_failures,
                probe,
            )
        if distinct_failures >= 2:
            return _result(
                SessionHealth.ROTATION_SUSPECTED,
                RotationReason.REPEATED_TERMINAL_GENERATION_FAILURE,
                distinct_failures,
                probe,
            )
        return _result(
            SessionHealth.PROVIDER_TRANSIENT,
            RotationReason.UNKNOWN,
            distinct_failures,
            probe,
        )

    if probe["composer_available"] is True and probe["generation_state"] == "idle":
        return _result(SessionHealth.SESSION_HEALTHY, None, distinct_failures, probe)
    return _result(SessionHealth.UNKNOWN, RotationReason.UNKNOWN, distinct_failures, probe)
