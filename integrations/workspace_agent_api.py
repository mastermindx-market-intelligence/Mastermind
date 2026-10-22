"""Mastermind Workspace Agent trigger-acceptance observation only.

Current official OpenAI sources are not fully aligned on the baseline HTTP 202
body shape, and the developer trigger documentation separately exposes opt-in
beta run-status polling. Mastermind's accepted production contract deliberately
does not request that beta contract: a 202 is queue acceptance only, any success
body is ignored, and the agent answer is not retrieved through the trigger API.

The RunObservation/decode_run/read_run_once names remain as fail-closed
compatibility surfaces for older callers. They perform no run-status network
request and report RUN_OBSERVATION_NOT_ADMITTED after identifier validation.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Callable

HOST = "api.chatgpt.com"
MAX_BODY_BYTES = 65_536
_ID_SUFFIX = r"[A-Za-z0-9_-]{1,192}"
_CHANNEL = re.compile(r"agtch_" + _ID_SUFFIX + r"\Z", re.ASCII)
_RUN = re.compile(r"apirun_" + _ID_SUFFIX + r"\Z", re.ASCII)


class InvalidObservation(ValueError):
    """Only fixed diagnostic codes cross this boundary, never provider prose."""


@dataclass(frozen=True)
class TriggerObservation:
    # Provider HTTP acceptance, NOT company admission, execution, or acceptance.
    disposition: str
    reason: str
    run_id: str | None = None
    conversation_url: str | None = None
    correlation_available: bool = False


@dataclass(frozen=True)
class RunObservation:
    """Compatibility projection for run status not admitted by Mastermind."""

    channel_id: str
    run_id: str
    available: bool
    reason: str
    provider_state: str | None = None
    provider_terminal: bool | None = None
    provider_created_at: int | None = None
    observed_at: int | None = None
    conversation_url: str | None = None
    failure_code: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _identifier(value: str, pattern: re.Pattern) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise InvalidObservation("INVALID_IDENTIFIER")
    return value


def validate_channel_id(value: str) -> str:
    return _identifier(value, _CHANNEL)


def _timestamp(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise InvalidObservation("INVALID_TIMESTAMP")
    return value


def decode_trigger(status: int | None, body: bytes) -> TriggerObservation:
    """Classify one already-received trigger response without trusting a body.

    The supported contract gives no correlation body.  Even if an intermediary or
    older endpoint supplies bytes, they are intentionally ignored and can never
    manufacture a run id, conversation identity, completion, result, or Wake ACK.
    """

    if type(body) is not bytes:
        raise InvalidObservation("BODY_SIZE_OR_TYPE")
    if type(status) is int and status == 202:
        return TriggerObservation("accepted", "ACCEPTED_UNCORRELATED")
    if type(status) is int and status in {401, 403, 404, 409}:
        return TriggerObservation("rejected", f"PROVIDER_REJECTED_{status}")
    return TriggerObservation("unknown", "TRIGGER_EFFECT_UNKNOWN")


def decode_run(
    status: int | None,
    body: bytes,
    *,
    channel_id: str,
    run_id: str,
    observed_at: int,
    expected_conversation_url: str | None = None,
) -> RunObservation:
    """Fail closed because beta run observation is not admitted by Mastermind."""

    del status, body, expected_conversation_url
    channel = validate_channel_id(channel_id)
    run = _identifier(run_id, _RUN)
    observed = _timestamp(observed_at)
    return RunObservation(
        channel_id=channel,
        run_id=run,
        available=False,
        reason="RUN_OBSERVATION_NOT_ADMITTED",
        observed_at=observed,
    )


def read_run_once(
    *,
    channel_id: str,
    run_id: str,
    token: str = "",
    timeout_seconds: float = 10.0,
    expected_conversation_url: str | None = None,
    connection_factory: Callable | None = None,
    clock: Callable[[], float] = time.time,
) -> RunObservation:
    """Compatibility shim that performs zero network I/O and refuses run polling."""

    del token, timeout_seconds, expected_conversation_url, connection_factory
    channel = validate_channel_id(channel_id)
    run = _identifier(run_id, _RUN)
    observed = _timestamp(int(clock()))
    return RunObservation(
        channel_id=channel,
        run_id=run,
        available=False,
        reason="RUN_OBSERVATION_NOT_ADMITTED",
        observed_at=observed,
    )


__all__ = [
    "HOST",
    "MAX_BODY_BYTES",
    "InvalidObservation",
    "RunObservation",
    "TriggerObservation",
    "decode_run",
    "decode_trigger",
    "read_run_once",
    "validate_channel_id",
]
