"""Pure physical-source identity for Agent Dialogue Wake reconciliation.

This module owns canonical values only.  It performs no Slack, Runtime, ledger,
provider, or lifecycle I/O.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Mapping

from control_plane.wake_events import mint_obligation_id


PHYSICAL_SOURCE_SCHEMA = "mastermind.dialogue_physical_source/v2"
SOURCE_OBSERVATION_SCHEMA = "mastermind.dialogue_source_observation/v1"
SOURCE_SNAPSHOT_SCHEMA = "mastermind.dialogue_source_snapshot/v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_WORKSPACE = re.compile(r"^T[A-Z0-9]{8,31}$")
_CHANNEL = re.compile(r"^[CG][A-Z0-9]{8,31}$")
_THREAD = re.compile(r"^[1-9][0-9]{9,15}\.[0-9]{6}$")
_MESSAGE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_WAKE_ID = re.compile(r"^WAKE-[0-9a-f]{32}$")
_SOURCE_REF = re.compile(r"^agent_dialogue_attention:[0-9a-f]{64}$")
_CANDIDATE_KEYS = frozenset(
    {"mode", "root_job_id", "job_id", "attempt_id", "worker_id", "evidence_digest"}
)


class DialogueSourceResolutionError(ValueError):
    """A physical-source assertion is malformed or internally contradictory."""


def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise DialogueSourceResolutionError("source identity is not canonical JSON") from None


def _text(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise DialogueSourceResolutionError(f"{name} is malformed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class DialogueSourceCandidate:
    mode: str
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    evidence_digest: str

    def to_dict(self) -> dict[str, str]:
        return {field.name: getattr(self, field.name) for field in dataclasses.fields(self)}


def _candidate(value: Mapping[str, Any] | DialogueSourceCandidate) -> DialogueSourceCandidate:
    if isinstance(value, DialogueSourceCandidate):
        raw = value.to_dict()
    elif type(value) is dict and set(value) == _CANDIDATE_KEYS:
        raw = value
    else:
        raise DialogueSourceResolutionError("candidate fields drifted")
    result = {key: _text(raw[key], f"candidate.{key}", _TOKEN) for key in _CANDIDATE_KEYS}
    _text(result["evidence_digest"], "candidate.evidence_digest", _DIGEST)
    if result["mode"] not in {"ACTIVE_CURRENT_WORKER", "TERMINAL_RESULT"}:
        raise DialogueSourceResolutionError("candidate.mode is unknown")
    return DialogueSourceCandidate(**result)


def parse_source_candidate(
    value: Mapping[str, Any] | DialogueSourceCandidate,
) -> DialogueSourceCandidate:
    return _candidate(value)


def attention_source_ref(*, parent_fingerprint: str, message_key: str, target_seat: str) -> str:
    """Reuse the canonical watcher identity without creating an import cycle."""

    _text(parent_fingerprint, "parent_fingerprint", _DIGEST)
    _text(message_key, "message_key", _MESSAGE_KEY)
    if target_seat not in {"ceo", "coo"}:
        raise DialogueSourceResolutionError("target_seat is unknown")
    # Lazy by design: turn_observer imports this module while turn_watcher owns
    # the frozen v1 identity algorithm.
    from integrations.slack_agent_dialogue.turn_watcher import _canonical_identity

    material = _canonical_identity(
        commission_fingerprint=parent_fingerprint,
        message_key=message_key,
        target_seat=target_seat,
    )
    return "agent_dialogue_attention:" + hashlib.sha256(material).hexdigest()


def correlated_source_ref(
    *, attention_source_ref: str, parent_fingerprint: str,
    operation_key: str, candidate: Mapping[str, Any],
) -> str:
    _text(attention_source_ref, "attention_source_ref", _SOURCE_REF)
    _text(parent_fingerprint, "parent_fingerprint", _DIGEST)
    _text(operation_key, "operation_key", _TOKEN)
    material = {
        "schema": "mastermind.dialogue_observation_identity/v1",
        "attention_source_ref": attention_source_ref,
        "parent_fingerprint": parent_fingerprint,
        "operation_key": operation_key,
        "candidate": _candidate(candidate).to_dict(),
    }
    return "agent_dialogue_attention:" + hashlib.sha256(canonical_bytes(material)).hexdigest()


@dataclasses.dataclass(frozen=True, slots=True)
class DialogueSourceObservation:
    workspace_id: str
    channel_id: str
    thread_ts: str
    predecessor_message_key: str
    predecessor_message_fingerprint: str

    def __post_init__(self) -> None:
        _text(self.workspace_id, "workspace_id", _WORKSPACE)
        _text(self.channel_id, "channel_id", _CHANNEL)
        _text(self.thread_ts, "thread_ts", _THREAD)
        _text(self.predecessor_message_key, "predecessor_message_key", _MESSAGE_KEY)
        _text(
            self.predecessor_message_fingerprint,
            "predecessor_message_fingerprint", _DIGEST,
        )

    @classmethod
    def from_dict(cls, value: Any) -> "DialogueSourceObservation":
        fields = {field.name for field in dataclasses.fields(cls)}
        if type(value) is not dict or set(value) != fields:
            raise DialogueSourceResolutionError("source_observation fields drifted")
        return cls(**value)

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalDialogueSourceIdentity:
    schema: str
    logical_source_ref: str
    obligation_id: str
    workspace_id: str
    channel_id: str
    thread_ts: str
    parent_fingerprint: str
    operation_key: str
    predecessor_message_key: str
    predecessor_message_fingerprint: str
    target_seat: str
    candidate: DialogueSourceCandidate | Mapping[str, str]
    digest: str

    def __post_init__(self) -> None:
        if self.schema != PHYSICAL_SOURCE_SCHEMA:
            raise DialogueSourceResolutionError("physical source schema is unknown")
        _text(self.logical_source_ref, "logical_source_ref", _SOURCE_REF)
        _text(self.obligation_id, "obligation_id", _WAKE_ID)
        observation = DialogueSourceObservation(
            self.workspace_id, self.channel_id, self.thread_ts,
            self.predecessor_message_key, self.predecessor_message_fingerprint,
        )
        del observation
        _text(self.parent_fingerprint, "parent_fingerprint", _DIGEST)
        _text(self.operation_key, "operation_key", _TOKEN)
        if self.target_seat not in {"ceo", "coo"}:
            raise DialogueSourceResolutionError("target_seat is unknown")
        candidate = _candidate(self.candidate)
        object.__setattr__(self, "candidate", candidate)
        attention = attention_source_ref(
            parent_fingerprint=self.parent_fingerprint,
            message_key=self.predecessor_message_key,
            target_seat=self.target_seat,
        )
        expected_logical = correlated_source_ref(
            attention_source_ref=attention,
            parent_fingerprint=self.parent_fingerprint,
            operation_key=self.operation_key,
            candidate=candidate.to_dict(),
        )
        if self.logical_source_ref != expected_logical:
            raise DialogueSourceResolutionError("physical logical source disagrees")
        expected_oid = mint_obligation_id(
            source_kind="agent_dialogue_attention",
            source_ref=expected_logical,
            wake_kind="dialogue_turn_pending",
        )
        if self.obligation_id != expected_oid:
            raise DialogueSourceResolutionError("physical obligation identity disagrees")
        material = self._material()
        expected = hashlib.sha256(canonical_bytes(material)).hexdigest()
        if self.digest != expected:
            raise DialogueSourceResolutionError("physical source digest disagrees")

    def _material(self) -> dict[str, Any]:
        material = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name != "digest"
        }
        material["candidate"] = self.candidate.to_dict()
        return material

    @classmethod
    def create(
        cls, *, logical_source_ref: str, obligation_id: str,
        observation: DialogueSourceObservation, parent_fingerprint: str,
        operation_key: str, target_seat: str, candidate: Mapping[str, Any],
    ) -> "PhysicalDialogueSourceIdentity":
        material = {
            "schema": PHYSICAL_SOURCE_SCHEMA,
            "logical_source_ref": logical_source_ref,
            "obligation_id": obligation_id,
            **observation.to_dict(),
            "parent_fingerprint": parent_fingerprint,
            "operation_key": operation_key,
            "target_seat": target_seat,
            "candidate": _candidate(candidate).to_dict(),
        }
        return cls(**material, digest=hashlib.sha256(canonical_bytes(material)).hexdigest())

    @classmethod
    def from_dict(cls, value: Any) -> "PhysicalDialogueSourceIdentity":
        fields = {field.name for field in dataclasses.fields(cls)}
        if type(value) is not dict or set(value) != fields:
            raise DialogueSourceResolutionError("physical source fields drifted")
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "digest": self.digest}


class DialogueSourceReconciler(ABC):
    """Nominal source-aware carrier capability; structural lookalikes do not qualify."""

    @abstractmethod
    async def reconcile_dialogue_sources(self, snapshot: object) -> object:
        raise NotImplementedError


class DialogueSourceState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_RESOLUTION_REQUIRED = "NO_RESOLUTION_REQUIRED"
    ACK_REQUIRED = "ACK_REQUIRED"
    CARRIER_IDENTITY_UNAVAILABLE = "CARRIER_IDENTITY_UNAVAILABLE"
    RECORDED = "RECORDED"
    UNKNOWN = "UNKNOWN"


@dataclasses.dataclass(frozen=True, slots=True)
class DialogueSourceMessage:
    """One immutable canonical created-message document."""

    canonical_json: str

    def __post_init__(self) -> None:
        if type(self.canonical_json) is not str or not 2 <= len(self.canonical_json) <= 16_384:
            raise DialogueSourceResolutionError("source message is malformed")
        try:
            value = json.loads(self.canonical_json)
        except (TypeError, ValueError):
            raise DialogueSourceResolutionError("source message is malformed") from None
        if type(value) is not dict or canonical_bytes(value).decode("ascii") != self.canonical_json:
            raise DialogueSourceResolutionError("source message is not canonical")

    @classmethod
    def create(cls, value: Mapping[str, Any]) -> "DialogueSourceMessage":
        return cls(canonical_bytes(dict(value)).decode("ascii"))

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        assert type(value) is dict
        return value


@dataclasses.dataclass(frozen=True, slots=True)
class DialogueSourceSnapshot:
    workspace_id: str
    channel_id: str
    thread_ts: str
    parent_fingerprint: str
    operation_key: str
    messages: tuple[DialogueSourceMessage, ...]
    complete: bool = True

    def __post_init__(self) -> None:
        _text(self.workspace_id, "snapshot.workspace_id", _WORKSPACE)
        _text(self.channel_id, "snapshot.channel_id", _CHANNEL)
        _text(self.thread_ts, "snapshot.thread_ts", _THREAD)
        _text(self.parent_fingerprint, "snapshot.parent_fingerprint", _DIGEST)
        _text(self.operation_key, "snapshot.operation_key", _TOKEN)
        if type(self.complete) is not bool or not self.complete:
            raise DialogueSourceResolutionError("source snapshot is incomplete")
        if type(self.messages) is not tuple or len(self.messages) > 64:
            raise DialogueSourceResolutionError("source snapshot edge bound exceeded")
        if any(type(item) is not DialogueSourceMessage for item in self.messages):
            raise DialogueSourceResolutionError("source snapshot message is malformed")
        keys = [item.to_dict().get("message_key") for item in self.messages]
        if len(keys) != len(set(keys)):
            raise DialogueSourceResolutionError("source snapshot has duplicate keys")

    @classmethod
    def from_dict(cls, value: Any) -> "DialogueSourceSnapshot":
        fields = {field.name for field in dataclasses.fields(cls)}
        if type(value) is not dict or set(value) != fields or type(value.get("messages")) is not list:
            raise DialogueSourceResolutionError("source snapshot fields drifted")
        return cls(**{
            **value,
            "messages": tuple(DialogueSourceMessage.create(item) for item in value["messages"]),
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "channel_id": self.channel_id,
            "thread_ts": self.thread_ts,
            "parent_fingerprint": self.parent_fingerprint,
            "operation_key": self.operation_key,
            "messages": [item.to_dict() for item in self.messages],
            "complete": self.complete,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.to_dict())).hexdigest()


__all__ = [
    "DialogueSourceObservation", "DialogueSourceReconciler",
    "DialogueSourceCandidate",
    "DialogueSourceMessage", "DialogueSourceSnapshot", "DialogueSourceState",
    "DialogueSourceResolutionError", "PHYSICAL_SOURCE_SCHEMA",
    "PhysicalDialogueSourceIdentity", "SOURCE_OBSERVATION_SCHEMA",
    "attention_source_ref", "canonical_bytes", "correlated_source_ref",
    "parse_source_candidate",
]
