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

from control_plane.operator_harness_contract import (
    ObservedHarnessAttestation, ObservedCapabilityIdentity, ObservedTriState,
)

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


EXTENSION_V2 = {"schema": "mastermind.dsh.native_prompt_extension.v2",
                "claimMethod": "_mastermind/native_claim", "cancelMethod": "_mastermind/native_cancel",
                "observeMethod": "_mastermind/native_observe"}
EXTENSION_V3 = {**EXTENSION_V2, "schema": "mastermind.dsh.native_prompt_extension.v3",
                "readMethod": "_mastermind/native_read"}
OBSERVATION_REQUEST_SCHEMA = "mastermind.dsh.native_observation_request.v1"
OBSERVATION_SCHEMA = "mastermind.dsh.native_observation.v1"
OBSERVATION_MAX_BYTES = 32 * 1024


def native_extension(value: Any) -> dict[str, str]:
    """Accept one complete negotiated version, never v1 with added authority."""
    if type(value) is not dict or value not in (EXTENSION, EXTENSION_V2, EXTENSION_V3):
        raise NativeProtocolError("NATIVE_EXTENSION_REFUSED")
    return dict(value)



OWNER_OBSERVATION_SCHEMA = "mastermind.dsh.native_owner_observation.v1"


@dataclasses.dataclass(frozen=True)
class NativeAccountFacts:
    inference_origin: str
    user_id: str | None


@dataclasses.dataclass(frozen=True)
class NativeWorkspaceFacts:
    workspace_path: str
    device: int
    inode: int
    uid: int
    gid: int


@dataclasses.dataclass(frozen=True)
class NativeProcessFacts:
    pid: int
    uid: int
    gid: int
    exec_path: str
    node_version: str
    binary_sha256: str


@dataclasses.dataclass(frozen=True)
class NativeSourceFacts:
    entry_path: str
    entry_sha256: str


@dataclasses.dataclass(frozen=True)
class NativeSelectionFacts:
    provider: str
    model: str
    reasoning_effort: str | None


@dataclasses.dataclass(frozen=True)
class NativeOwnerFacts:
    """Actual Node owners only; no canonical Worker, principal or Git base."""
    agent_id: str
    session_cwd: str
    process: NativeProcessFacts
    source: NativeSourceFacts
    selection: NativeSelectionFacts | None
    account: NativeAccountFacts | None
    workspace: NativeWorkspaceFacts | None
    capabilities: tuple[ObservedCapabilityIdentity, ...] | None
    effective_skills: tuple[str, ...] | None
    effective_mcp: tuple[str, ...] | None
    effective_plugins_or_apps: tuple[str, ...] | None
    sandbox_state: str | None
    approval_state: str | None
    network_state: str | None
    effective_config_digest: str | None
    supports_subagent_capability_ceiling: ObservedTriState
    unknown_fields: tuple[str, ...]


def _native_owner_observation(value: Any, session_id: str) -> NativeOwnerFacts:
    from control_plane.operator_harness_wire import observed_capability_identity
    from pathlib import PurePosixPath
    from urllib.parse import urlsplit

    def closed(item, names):
        if type(item) is not dict or set(item) != set(names):
            raise ValueError()
        return item

    def text(item, nullable=False):
        if item is None and nullable:
            return None
        if type(item) is not str or not item or len(item.encode("utf-8")) > OBSERVATION_MAX_BYTES:
            raise ValueError()
        return item

    def path(item):
        text(item)
        p = PurePosixPath(item)
        if not p.is_absolute() or str(p) != item or ".." in p.parts or item.startswith("//"):
            raise ValueError()
        return item

    def digest(item):
        if type(item) is not str or re.fullmatch(r"[0-9a-f]{64}", item) is None:
            raise ValueError()
        return item

    def rows(item, convert, nullable=False):
        if item is None and nullable:
            return None
        if type(item) is not list or len(item) > 4096:
            raise ValueError()
        return tuple(convert(x) for x in item)

    def capability(item):
        names = {field.name for field in dataclasses.fields(ObservedCapabilityIdentity)}
        row = closed(item, names)
        for key, field in row.items():
            text(field, nullable=key not in {"kind", "name"})
        return observed_capability_identity(row)

    try:
        closed(value, ("schema", "sessionId", "facts"))
        if (value["schema"] != OWNER_OBSERVATION_SCHEMA
                or native_id(value["sessionId"]) != native_id(session_id)
                or len(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                  separators=(",", ":")).encode("utf-8")) > OBSERVATION_MAX_BYTES):
            raise ValueError()
        raw = closed(value["facts"], (field.name for field in dataclasses.fields(NativeOwnerFacts)))
        if native_id(raw["agent_id"]) != session_id:
            raise ValueError()
        process = closed(raw["process"], (field.name for field in dataclasses.fields(NativeProcessFacts)))
        for key in ("pid", "uid", "gid"):
            integer(process[key], minimum=1 if key == "pid" else 0)
        path(process["exec_path"])
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", text(process["node_version"])):
            raise ValueError()
        digest(process["binary_sha256"])
        source = closed(raw["source"], ("entry_path", "entry_sha256"))
        path(source["entry_path"]); digest(source["entry_sha256"])
        selection = raw["selection"]
        if selection is not None:
            closed(selection, ("provider", "model", "reasoning_effort"))
            for key, item in selection.items():
                text(item, nullable=key == "reasoning_effort")
            selection = NativeSelectionFacts(**selection)
        account = raw["account"]
        if account is not None:
            closed(account, ("inference_origin", "user_id"))
            origin = urlsplit(text(account["inference_origin"]))
            if (origin.scheme not in {"http", "https"} or not origin.hostname
                    or origin.username or origin.password or origin.query or origin.fragment
                    or origin.path not in {"", "/"}
                    or account["inference_origin"] != origin.scheme + "://" + origin.netloc):
                raise ValueError()
            user_id = text(account["user_id"], nullable=True)
            if user_id is not None and any(x in user_id.lower() for x in ("token", "refresh", "secret", "auth.json", "credential")):
                raise ValueError()
            account = NativeAccountFacts(**account)
        workspace = raw["workspace"]
        if workspace is not None:
            closed(workspace, (field.name for field in dataclasses.fields(NativeWorkspaceFacts)))
            path(workspace["workspace_path"])
            for key in ("device", "inode", "uid", "gid"):
                integer(workspace[key], minimum=1 if key == "inode" else 0)
            workspace = NativeWorkspaceFacts(**workspace)
        fields = {key: text(raw[key], nullable=True)
                  for key in ("sandbox_state", "approval_state", "network_state", "effective_config_digest")}
        if fields["effective_config_digest"] is not None:
            digest(fields["effective_config_digest"])
        return NativeOwnerFacts(
            agent_id=raw["agent_id"], session_cwd=path(raw["session_cwd"]),
            process=NativeProcessFacts(**process), source=NativeSourceFacts(**source),
            selection=selection, account=account, workspace=workspace,
            capabilities=rows(raw["capabilities"], capability, nullable=True),
            effective_skills=rows(raw["effective_skills"], text, nullable=True),
            effective_mcp=rows(raw["effective_mcp"], text, nullable=True),
            effective_plugins_or_apps=rows(raw["effective_plugins_or_apps"], text, nullable=True),
            **fields,
            supports_subagent_capability_ceiling=ObservedTriState(raw["supports_subagent_capability_ceiling"]),
            unknown_fields=rows(raw["unknown_fields"], text),
        )
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
        raise NativeProtocolError("NATIVE_OWNER_OBSERVATION_REFUSED") from None


def native_observation(value: Any, session_id: str) -> ObservedHarnessAttestation | NativeOwnerFacts:
    """Decode the original session's passive OHF facts, preserving explicit nulls."""
    if type(value) is dict and value.get("schema") == OWNER_OBSERVATION_SCHEMA:
        return _native_owner_observation(value, session_id)
    # The general OHF wire also imports native result types from this module.
    from control_plane.operator_harness_wire import observed_harness_attestation
    try:
        if (type(value) is not dict or set(value) != {"schema", "sessionId", "attestation"}
                or value["schema"] != OBSERVATION_SCHEMA
                or native_id(value["sessionId"]) != native_id(session_id)
                or len(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                  separators=(",", ":")).encode("utf-8")) > OBSERVATION_MAX_BYTES):
            raise ValueError()
        raw = value["attestation"]
        observed = observed_harness_attestation(raw)  # existing closed nested OHF codecs
        def text(item, *, nullable=False):
            if item is None and nullable:
                return
            if type(item) is not str or not item:
                raise ValueError()
        for key in ("served_model", "harness_version", "harness_binary_digest",
                    "sandbox_state", "approval_state", "network_state", "effective_config_digest"):
            text(raw[key], nullable=True)
        for key in ("effective_skills", "effective_mcp", "effective_plugins_or_apps", "unknown_fields"):
            for item in raw[key]:
                text(item)
        for capability in raw["capabilities"]:
            for key, item in capability.items():
                text(item, nullable=key not in {"kind", "name"})
        for key, item in raw["auth"].items():
            text(item, nullable=key in {"auth_class", "plan_type", "nonsecret_provider_account_id"})
        if raw["workspace"] is not None:
            for key, item in raw["workspace"].items():
                integer(item) if key in {"device", "inode", "uid", "gid"} else text(item)
        return observed
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
        raise NativeProtocolError("NATIVE_OBSERVATION_REFUSED") from None


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
