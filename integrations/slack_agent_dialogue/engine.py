"""Storeless, injected-client Active-Session Dialogue engine."""
from __future__ import annotations

import asyncio
import dataclasses
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence

from integrations.slack_agent_dialogue.contract import (
    FABLE_MESSAGE_TYPES,
    MESSAGE_DISCRIMINATOR,
    PARENT_DISCRIMINATOR,
    SOL_MESSAGE_TYPES,
    DialogueContractError,
    TrustedAuthorityPolicy,
    adjudicate_reply,
    parse_message_frame,
    parse_parent_frame,
    render_message,
    validate_message,
)

ERROR_CODES = frozenset(
    {
        "MESSAGE_KEY_CONFLICT",
        "PARENT_SEND_EFFECT_UNKNOWN",
        "PARENT_MESSAGE_INVALID",
        "REPLY_AMBIGUOUS",
        "REPLY_NOT_FOUND",
        "SEND_EFFECT_UNKNOWN",
        "THREAD_BINDING_AMBIGUOUS",
        "THREAD_CONTEXT_MISMATCH",
        "THREAD_HISTORY_INCOMPLETE",
        "THREAD_MESSAGE_INVALID",
        "THREAD_RECONCILIATION_INCOMPLETE",
        "TRANSPORT_UNAVAILABLE",
        "WAIT_TIMEOUT",
        "WRITE_RESULT_INVALID",
    }
)

_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_CHANNEL_ID_RE = re.compile(r"\A[CG][A-Z0-9]{8,31}\Z")
_WORKSPACE_ID_RE = re.compile(r"\AT[A-Z0-9]{8,31}\Z")
_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")


class DialogueEngineError(RuntimeError):
    """One fixed engine refusal code."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown dialogue engine error code")
        super().__init__(code)
        self.code = code


class SlackEffectUnknown(RuntimeError):
    """The Slack method may have committed but no trustworthy reply was received."""


class SlackTransportUnavailable(RuntimeError):
    """The Slack method definitely did not produce a usable result."""


@dataclass(frozen=True)
class SlackMessage:
    ts: str
    author_user_id: str
    text: str
    thread_ts: str | None = None
    edited: bool = False
    deleted: bool = False
    created_text: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.ts, str) or _TS_RE.fullmatch(self.ts) is None:
            raise ValueError("invalid Slack timestamp")
        if not isinstance(self.author_user_id, str) or _SLACK_USER_ID_RE.fullmatch(
            self.author_user_id
        ) is None:
            raise ValueError("invalid Slack author user id")
        if not isinstance(self.text, str):
            raise ValueError("Slack message text must be a string")
        if self.thread_ts is not None and (
            not isinstance(self.thread_ts, str)
            or _TS_RE.fullmatch(self.thread_ts) is None
        ):
            raise ValueError("invalid Slack thread timestamp")
        if type(self.edited) is not bool or type(self.deleted) is not bool:
            raise ValueError("edited/deleted flags must be booleans")
        if self.created_text is not None and not isinstance(self.created_text, str):
            raise ValueError("created_text must be a string or None")
        if not (self.edited or self.deleted) and self.created_text not in {None, self.text}:
            raise ValueError("unmutated message cannot carry different created_text")


@dataclass(frozen=True)
class HistoryPage:
    messages: tuple[SlackMessage, ...]
    complete: bool
    mutation_evidence_complete: bool

    def __post_init__(self) -> None:
        if type(self.complete) is not bool:
            raise ValueError("complete must be boolean")
        if type(self.mutation_evidence_complete) is not bool:
            raise ValueError("mutation_evidence_complete must be boolean")
        if not isinstance(self.messages, tuple) or any(
            not isinstance(message, SlackMessage) for message in self.messages
        ):
            raise ValueError("messages must be a tuple of SlackMessage")


class SlackDialogueClient(Protocol):
    async def fetch_channel_history(
        self, *, channel_id: str, limit: int
    ) -> HistoryPage: ...

    async def fetch_thread(
        self, *, channel_id: str, thread_ts: str, limit: int
    ) -> HistoryPage: ...

    async def post_parent(
        self, *, channel_id: str, text: str
    ) -> SlackMessage: ...

    async def post_reply(
        self, *, channel_id: str, thread_ts: str, text: str
    ) -> SlackMessage: ...


@dataclass(frozen=True)
class DialoguePolicy:
    workspace_id: str
    channel_id: str
    relay_bot_user_id: str
    allowed_sol_user_ids: tuple[str, ...]
    allowed_parent_user_ids: tuple[str, ...]
    max_channel_history: int = 100
    max_thread_history: int = 100
    max_wait_attempts: int = 20
    poll_interval_seconds: float = 1.0
    method_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if _WORKSPACE_ID_RE.fullmatch(self.workspace_id) is None:
            raise ValueError("invalid workspace_id")
        if _CHANNEL_ID_RE.fullmatch(self.channel_id) is None:
            raise ValueError("invalid channel_id")
        if _SLACK_USER_ID_RE.fullmatch(self.relay_bot_user_id) is None:
            raise ValueError("invalid relay_bot_user_id")
        for field_name in ("allowed_sol_user_ids", "allowed_parent_user_ids"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, tuple)
                or not value
                or value != tuple(sorted(set(value)))
                or any(_SLACK_USER_ID_RE.fullmatch(item) is None for item in value)
            ):
                raise ValueError(f"invalid {field_name}")
        if self.relay_bot_user_id in self.allowed_sol_user_ids:
            raise ValueError("relay bot cannot be an eligible Sol sender")
        if not 1 <= self.max_channel_history <= 1000:
            raise ValueError("max_channel_history out of range")
        if not 1 <= self.max_thread_history <= 1000:
            raise ValueError("max_thread_history out of range")
        if not 1 <= self.max_wait_attempts <= 120:
            raise ValueError("max_wait_attempts out of range")
        if not 0 <= self.poll_interval_seconds <= 60:
            raise ValueError("poll_interval_seconds out of range")
        if not 0.1 <= self.method_timeout_seconds <= 60:
            raise ValueError("method_timeout_seconds out of range")


@dataclass(frozen=True)
class DialogueContext:
    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    applies_to: Mapping[str, Any]

    def normalized(self) -> dict[str, Any]:
        probe = {
            "schema": "mastermind.agent_dialogue.v1",
            "message_key": "asd-context-probe",
            "message_type": "ACK",
            "work_ref": self.work_ref,
            "commission_ref": dict(self.commission_ref),
            "session_ref": self.session_ref,
            "seat_ref": "fable",
            "reply_to_message_key": None,
            "applies_to": dict(self.applies_to),
            "summary": "Context validation.",
            "body": {"acknowledged": True},
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2000-01-01T00:00:00Z",
            "fingerprint": "",
        }
        from integrations.slack_agent_dialogue.contract import semantic_fingerprint

        probe["fingerprint"] = semantic_fingerprint(probe)
        validated = validate_message(probe)
        return {
            "work_ref": validated["work_ref"],
            "commission_ref": validated["commission_ref"],
            "session_ref": validated["session_ref"],
            "applies_to": validated["applies_to"],
        }


@dataclass(frozen=True)
class BoundThread:
    thread_ts: str
    parent_author_user_id: str
    parent_fingerprint: str


@dataclass(frozen=True)
class ParentEnsureReceipt(BoundThread):
    action: str

    def __post_init__(self) -> None:
        if self.action not in {"POSTED", "RECOVERED", "REUSED"}:
            raise ValueError("invalid parent ensure action")


@dataclass(frozen=True)
class MessageReceipt:
    action: str
    message_key: str
    fingerprint: str
    message_ts: str
    duplicate_timestamps: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadMessage:
    message: Mapping[str, Any]
    primary_ts: str
    duplicate_timestamps: tuple[str, ...]


@dataclass(frozen=True)
class ThreadRead:
    thread_ts: str
    messages: tuple[ReadMessage, ...]
    historical_messages: tuple[ReadMessage, ...]
    ineligible_count: int
    mutated_count: int


def _ts_order(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise DialogueEngineError("THREAD_MESSAGE_INVALID") from None


def _context_matches(message: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    return (
        message.get("work_ref") == context["work_ref"]
        and message.get("commission_ref") == context["commission_ref"]
        and message.get("session_ref") == context["session_ref"]
        and message.get("applies_to") == context["applies_to"]
    )


def _thread_identity_matches(
    message: Mapping[str, Any], context: Mapping[str, Any]
) -> bool:
    return (
        message.get("work_ref") == context["work_ref"]
        and message.get("commission_ref") == context["commission_ref"]
        and message.get("session_ref") == context["session_ref"]
    )


class DialogueEngine:
    """One stateless engine over one fixed Slack workspace/channel policy."""

    def __init__(
        self,
        policy: DialoguePolicy,
        client: SlackDialogueClient,
        *,
        authority_policy: TrustedAuthorityPolicy,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self.policy = policy
        self.client = client
        self.authority_policy = authority_policy
        self._sleep = sleep

    async def bind_or_verify_thread(self, context: DialogueContext) -> BoundThread:
        normalized = context.normalized()
        try:
            page = await asyncio.wait_for(
                self.client.fetch_channel_history(
                    channel_id=self.policy.channel_id,
                    limit=self.policy.max_channel_history,
                ),
                timeout=self.policy.method_timeout_seconds,
            )
        except Exception:
            raise DialogueEngineError("TRANSPORT_UNAVAILABLE") from None
        if not isinstance(page, HistoryPage):
            raise DialogueEngineError("THREAD_HISTORY_INCOMPLETE")
        if not page.complete:
            raise DialogueEngineError("THREAD_HISTORY_INCOMPLETE")
        if not page.mutation_evidence_complete:
            raise DialogueEngineError("THREAD_RECONCILIATION_INCOMPLETE")
        matches: list[tuple[SlackMessage, Mapping[str, Any]]] = []
        for transport in page.messages:
            is_top_level = transport.thread_ts in {None, transport.ts}
            if not is_top_level:
                continue
            if transport.author_user_id not in self.policy.allowed_parent_user_ids:
                continue
            raw_text = transport.text
            if transport.deleted or transport.edited:
                if transport.created_text is None:
                    raise DialogueEngineError("THREAD_RECONCILIATION_INCOMPLETE")
                raw_text = transport.created_text
            if not raw_text.startswith(PARENT_DISCRIMINATOR):
                continue
            try:
                parent = parse_parent_frame(raw_text)
            except DialogueContractError:
                raise DialogueEngineError("PARENT_MESSAGE_INVALID") from None
            if (
                parent["work_ref"] == normalized["work_ref"]
                and parent["commission_ref"] == normalized["commission_ref"]
                and parent["session_ref"] == normalized["session_ref"]
            ):
                if tuple(parent["allowed_sol_user_ids"]) != self.policy.allowed_sol_user_ids:
                    raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
                matches.append((transport, parent))
        if len(matches) != 1:
            raise DialogueEngineError("THREAD_BINDING_AMBIGUOUS")
        transport, parent = matches[0]
        return BoundThread(
            thread_ts=transport.ts,
            parent_author_user_id=transport.author_user_id,
            parent_fingerprint=parent["fingerprint"],
        )

    async def _history(
        self, *, thread_ts: str, context: DialogueContext
    ) -> ThreadRead:
        if _TS_RE.fullmatch(thread_ts) is None:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        bound = await self.bind_or_verify_thread(context)
        if bound.thread_ts != thread_ts:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        try:
            page = await asyncio.wait_for(
                self.client.fetch_thread(
                    channel_id=self.policy.channel_id,
                    thread_ts=thread_ts,
                    limit=self.policy.max_thread_history,
                ),
                timeout=self.policy.method_timeout_seconds,
            )
        except Exception:
            raise DialogueEngineError("TRANSPORT_UNAVAILABLE") from None
        if not isinstance(page, HistoryPage) or not page.complete:
            raise DialogueEngineError("THREAD_HISTORY_INCOMPLETE")
        if not page.mutation_evidence_complete:
            raise DialogueEngineError("THREAD_RECONCILIATION_INCOMPLETE")

        normalized_context = context.normalized()
        eligible: dict[str, list[tuple[SlackMessage, Mapping[str, Any]]]] = {}
        ineligible_count = 0
        mutated_count = 0
        for transport in page.messages:
            if transport.ts == thread_ts or transport.thread_ts != thread_ts:
                continue
            sender_is_known = (
                transport.author_user_id == self.policy.relay_bot_user_id
                or transport.author_user_id in self.policy.allowed_sol_user_ids
            )
            if not sender_is_known:
                if transport.text.startswith(MESSAGE_DISCRIMINATOR) or (
                    transport.created_text is not None
                    and transport.created_text.startswith(MESSAGE_DISCRIMINATOR)
                ):
                    ineligible_count += 1
                continue
            raw_text = transport.text
            if transport.deleted or transport.edited:
                mutated_count += 1
                if transport.created_text is None:
                    raise DialogueEngineError("THREAD_RECONCILIATION_INCOMPLETE")
                raw_text = transport.created_text
            if not raw_text.startswith(MESSAGE_DISCRIMINATOR):
                continue
            try:
                message = parse_message_frame(raw_text)
            except DialogueContractError:
                raise DialogueEngineError("THREAD_MESSAGE_INVALID") from None
            if not _thread_identity_matches(message, normalized_context):
                raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
            is_fable = message["message_type"] in FABLE_MESSAGE_TYPES
            sender_eligible = (
                transport.author_user_id == self.policy.relay_bot_user_id
                if is_fable
                else transport.author_user_id in self.policy.allowed_sol_user_ids
            )
            if not sender_eligible:
                ineligible_count += 1
                continue
            eligible.setdefault(message["message_key"], []).append((transport, message))

        output: list[ReadMessage] = []
        historical_output: list[ReadMessage] = []
        for entries in eligible.values():
            fingerprints = {entry[1]["fingerprint"] for entry in entries}
            if len(fingerprints) != 1:
                raise DialogueEngineError("MESSAGE_KEY_CONFLICT")
            entries.sort(key=lambda entry: _ts_order(entry[0].ts))
            primary_transport, primary_message = entries[0]
            read_message = ReadMessage(
                message=primary_message,
                primary_ts=primary_transport.ts,
                duplicate_timestamps=tuple(
                    transport.ts for transport, _message in entries[1:]
                ),
            )
            if _context_matches(primary_message, normalized_context):
                output.append(read_message)
            else:
                historical_output.append(read_message)
        output.sort(key=lambda item: _ts_order(item.primary_ts))
        historical_output.sort(key=lambda item: _ts_order(item.primary_ts))
        return ThreadRead(
            thread_ts=thread_ts,
            messages=tuple(output),
            historical_messages=tuple(historical_output),
            ineligible_count=ineligible_count,
            mutated_count=mutated_count,
        )

    async def read_thread(
        self, *, thread_ts: str, context: DialogueContext
    ) -> ThreadRead:
        return await self._history(thread_ts=thread_ts, context=context)

    @staticmethod
    def _find_key(
        read: ThreadRead, *, message_key: str, fingerprint: str
    ) -> ReadMessage | None:
        matches = [item for item in read.messages if item.message["message_key"] == message_key]
        if not matches:
            return None
        if len(matches) != 1:
            raise DialogueEngineError("MESSAGE_KEY_CONFLICT")
        candidate = matches[0]
        if candidate.message["fingerprint"] != fingerprint:
            raise DialogueEngineError("MESSAGE_KEY_CONFLICT")
        return candidate

    def _validate_outbound(
        self, message: Mapping[str, Any], *, context: DialogueContext
    ) -> dict[str, Any]:
        try:
            validated = validate_message(dict(message))
        except DialogueContractError:
            raise DialogueEngineError("THREAD_MESSAGE_INVALID") from None
        if validated["message_type"] not in FABLE_MESSAGE_TYPES:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        if not _context_matches(validated, context.normalized()):
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        return validated

    @staticmethod
    def _validate_write_result(
        result: Any,
        *,
        thread_ts: str,
        expected_text: str,
        expected_author_user_id: str,
    ) -> SlackMessage:
        if (
            not isinstance(result, SlackMessage)
            or result.author_user_id != expected_author_user_id
            or result.thread_ts != thread_ts
            or result.text != expected_text
            or result.edited
            or result.deleted
        ):
            raise DialogueEngineError("WRITE_RESULT_INVALID")
        return result

    async def _reconcile_post_effect(
        self,
        *,
        thread_ts: str,
        context: DialogueContext,
        message_key: str,
        fingerprint: str,
    ) -> ReadMessage | None:
        try:
            read = await self._history(thread_ts=thread_ts, context=context)
            return self._find_key(
                read,
                message_key=message_key,
                fingerprint=fingerprint,
            )
        except DialogueEngineError:
            raise DialogueEngineError("SEND_EFFECT_UNKNOWN") from None

    async def send_message(
        self,
        *,
        thread_ts: str,
        context: DialogueContext,
        message: Mapping[str, Any],
    ) -> MessageReceipt:
        validated = self._validate_outbound(message, context=context)
        text = render_message(validated)
        existing = self._find_key(
            await self._history(thread_ts=thread_ts, context=context),
            message_key=validated["message_key"],
            fingerprint=validated["fingerprint"],
        )
        if existing is not None:
            return MessageReceipt(
                action="DUPLICATE",
                message_key=validated["message_key"],
                fingerprint=validated["fingerprint"],
                message_ts=existing.primary_ts,
                duplicate_timestamps=existing.duplicate_timestamps,
            )

        for attempt in range(2):
            invalid_receipt = False
            transport: SlackMessage | None = None
            try:
                result = await asyncio.wait_for(
                    self.client.post_reply(
                        channel_id=self.policy.channel_id,
                        thread_ts=thread_ts,
                        text=text,
                    ),
                    timeout=self.policy.method_timeout_seconds,
                )
            except (SlackEffectUnknown, asyncio.TimeoutError):
                pass
            except Exception:
                raise DialogueEngineError("TRANSPORT_UNAVAILABLE") from None
            else:
                try:
                    transport = self._validate_write_result(
                        result,
                        thread_ts=thread_ts,
                        expected_text=text,
                        expected_author_user_id=self.policy.relay_bot_user_id,
                    )
                except DialogueEngineError:
                    invalid_receipt = True

            recovered = await self._reconcile_post_effect(
                thread_ts=thread_ts,
                context=context,
                message_key=validated["message_key"],
                fingerprint=validated["fingerprint"],
            )
            if recovered is not None:
                action = (
                    "POSTED"
                    if transport is not None
                    and transport.ts
                    in {recovered.primary_ts, *recovered.duplicate_timestamps}
                    else "RECOVERED"
                )
                return MessageReceipt(
                    action=action,
                    message_key=validated["message_key"],
                    fingerprint=validated["fingerprint"],
                    message_ts=recovered.primary_ts,
                    duplicate_timestamps=recovered.duplicate_timestamps,
                )
            if attempt == 0:
                continue
            if invalid_receipt:
                raise DialogueEngineError("WRITE_RESULT_INVALID")
            raise DialogueEngineError("SEND_EFFECT_UNKNOWN")
        raise DialogueEngineError("SEND_EFFECT_UNKNOWN")

    async def wait_for_reply(
        self,
        *,
        thread_ts: str,
        context: DialogueContext,
        request_message_key: str,
        expected_types: Sequence[str],
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        expected = tuple(expected_types)
        if (
            not expected
            or len(expected) != len(set(expected))
            or any(message_type not in SOL_MESSAGE_TYPES for message_type in expected)
        ):
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        attempts = self.policy.max_wait_attempts if max_attempts is None else max_attempts
        if not isinstance(attempts, int) or not 1 <= attempts <= self.policy.max_wait_attempts:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        for index in range(attempts):
            read = await self._history(thread_ts=thread_ts, context=context)
            request_matches = [
                item
                for item in read.messages
                if item.message["message_key"] == request_message_key
                and item.message["message_type"] in FABLE_MESSAGE_TYPES
            ]
            if len(request_matches) != 1:
                raise DialogueEngineError("REPLY_NOT_FOUND")
            request = request_matches[0].message
            request_ts = _ts_order(request_matches[0].primary_ts)
            replies = [
                item
                for item in read.messages
                if item.message["reply_to_message_key"] == request_message_key
                and item.message["message_type"] in expected
                and _ts_order(item.primary_ts) > request_ts
            ]
            if len(replies) > 1:
                raise DialogueEngineError("REPLY_AMBIGUOUS")
            if len(replies) == 1:
                reply = replies[0]
                try:
                    authority = adjudicate_reply(
                        request,
                        reply.message,
                        authority_policy=self.authority_policy,
                    )
                except DialogueContractError:
                    raise DialogueEngineError("THREAD_CONTEXT_MISMATCH") from None
                return {
                    "reply": dict(reply.message),
                    "transport": {
                        "primary_ts": reply.primary_ts,
                        "duplicate_timestamps": list(reply.duplicate_timestamps),
                    },
                    "authority": authority,
                }
            if index + 1 < attempts:
                await self._sleep(self.policy.poll_interval_seconds)
        raise DialogueEngineError("WAIT_TIMEOUT")

    def status(self) -> dict[str, Any]:
        return {
            "schema": "mastermind.agent_dialogue_status.v1",
            "status": "DEVELOPMENT_UNARMED",
            "workspace_id": self.policy.workspace_id,
            "channel_id": self.policy.channel_id,
            "relay_bot_user_id": self.policy.relay_bot_user_id,
            "sol_sender_count": len(self.policy.allowed_sol_user_ids),
            "method_timeout_seconds": self.policy.method_timeout_seconds,
            "persistent_state": False,
            "production_token_installed": False,
        }


def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


__all__ = [
    "BoundThread",
    "DialogueContext",
    "DialogueEngine",
    "DialogueEngineError",
    "DialoguePolicy",
    "ERROR_CODES",
    "HistoryPage",
    "MessageReceipt",
    "ParentEnsureReceipt",
    "ReadMessage",
    "SlackDialogueClient",
    "SlackEffectUnknown",
    "SlackMessage",
    "SlackTransportUnavailable",
    "ThreadRead",
    "jsonable",
]
