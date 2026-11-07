"""Closed observations from the original opt-in native ACP lifecycle.

These values correlate original native effects; none grants company authority.
The terminal digest covers these observed facts, never an unobserved transcript.
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
import re
from typing import Any

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}\Z")
CLAIM_SCHEMA = "mastermind.dsh.native_prompt_claim.v1"
TERMINAL_SCHEMA = "mastermind.dsh.native_prompt_terminal.v1"
EXTENSION = {"schema": "mastermind.dsh.native_prompt_extension.v1",
             "claimMethod": "_mastermind/native_claim", "cancelMethod": "_mastermind/native_cancel"}
STOP_REASONS = frozenset({"end_turn", "max_tokens", "max_turn_requests", "refusal", "cancelled"})


class NativeProtocolError(ValueError):
    """A fixed nonsecret observation did not satisfy the native contract."""


def native_id(value: Any) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise NativeProtocolError("NATIVE_ID_REFUSED")
    return value


def integer(value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 2**53 - 1:
        raise NativeProtocolError("NATIVE_COUNTER_REFUSED")
    return value


def request_id(value: Any) -> str | int:
    if type(value) is int:
        return integer(value)
    return native_id(value)


def document(value: Any) -> dict[str, Any]:
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        value = dump(mode="json", by_alias=True, exclude_none=True)
    if type(value) is not dict:
        raise NativeProtocolError("NATIVE_DOCUMENT_REFUSED")
    return value


@dataclasses.dataclass(frozen=True)
class NativeClaim:
    operation_id: str
    request_id: str | int
    session_id: str
    message_id: str
    native_turn: int
    through_seq: int

    def __post_init__(self):
        for value in (self.operation_id, self.session_id, self.message_id):
            native_id(value)
        request_id(self.request_id)
        integer(self.native_turn)
        integer(self.through_seq)

    @classmethod
    def parse(cls, value: Any) -> NativeClaim:
        value = document(value)
        if set(value) != {"schema", "operationId", "requestId", "sessionId", "messageId", "nativeTurn", "throughSeq"} or value["schema"] != CLAIM_SCHEMA:
            raise NativeProtocolError("NATIVE_CLAIM_REFUSED")
        return cls(value["operationId"], value["requestId"], value["sessionId"], value["messageId"], value["nativeTurn"], value["throughSeq"])

    def to_wire(self) -> dict[str, Any]:
        return {"schema": CLAIM_SCHEMA, "operationId": self.operation_id, "requestId": self.request_id,
                "sessionId": self.session_id, "messageId": self.message_id,
                "nativeTurn": self.native_turn, "throughSeq": self.through_seq}


@dataclasses.dataclass(frozen=True)
class NativeTerminal:
    operation_id: str
    request_id: str | int
    claim: NativeClaim | None
    through_seq: int
    observed_last_turn: int | None
    observed_turn_count: int

    def __post_init__(self):
        native_id(self.operation_id)
        request_id(self.request_id)
        integer(self.through_seq, minimum=-1)
        integer(self.observed_turn_count)
        if self.observed_last_turn is not None:
            integer(self.observed_last_turn)
        if self.claim is not None:
            if (not isinstance(self.claim, NativeClaim)
                    or self.claim.operation_id != self.operation_id
                    or type(self.claim.request_id) is not type(self.request_id)
                    or self.claim.request_id != self.request_id
                    or self.through_seq < self.claim.through_seq
                    or self.observed_last_turn is None
                    or self.observed_last_turn < self.claim.native_turn
                    or self.observed_turn_count < 1):
                raise NativeProtocolError("NATIVE_TERMINAL_CLAIM_MISMATCH")
        elif self.observed_turn_count != 0 or self.observed_last_turn is not None:
            raise NativeProtocolError("NATIVE_UNCLAIMED_TURN_REFUSED")

    @classmethod
    def parse(cls, value: Any) -> NativeTerminal:
        value = document(value)
        if set(value) != {"schema", "operationId", "requestId", "claim", "throughSeq", "observedLastTurn", "observedTurnCount"} or value["schema"] != TERMINAL_SCHEMA:
            raise NativeProtocolError("NATIVE_TERMINAL_REFUSED")
        claim = None if value["claim"] is None else NativeClaim.parse(value["claim"])
        return cls(value["operationId"], value["requestId"], claim, value["throughSeq"], value["observedLastTurn"], value["observedTurnCount"])

    def to_wire(self) -> dict[str, Any]:
        return {"schema": TERMINAL_SCHEMA, "operationId": self.operation_id, "requestId": self.request_id,
                "claim": None if self.claim is None else self.claim.to_wire(), "throughSeq": self.through_seq,
                "observedLastTurn": self.observed_last_turn, "observedTurnCount": self.observed_turn_count}


@dataclasses.dataclass(frozen=True)
class NativeResult:
    stop_reason: str
    terminal: NativeTerminal

    def __post_init__(self):
        if self.stop_reason not in STOP_REASONS or not isinstance(self.terminal, NativeTerminal):
            raise NativeProtocolError("NATIVE_RESULT_REFUSED")

    @classmethod
    def parse(cls, value: Any) -> NativeResult:
        value = document(value)
        if set(value) != {"stopReason", "_meta"} or type(value["_meta"]) is not dict or set(value["_meta"]) != {"mastermindNative"}:
            raise NativeProtocolError("NATIVE_RESULT_REFUSED")
        return cls(value["stopReason"], NativeTerminal.parse(value["_meta"]["mastermindNative"]))

    def to_wire(self) -> dict[str, Any]:
        return {"stopReason": self.stop_reason, "_meta": {"mastermindNative": self.terminal.to_wire()}}

    @property
    def artifact_digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_wire(), sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()
