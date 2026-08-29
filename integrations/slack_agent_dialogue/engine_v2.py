"""Storeless worker-aware Active-Session Dialogue V2 engine.

WP-1 keeps Slack transport, bounded history, and authority policy injection in
existing owners. This module adds only V2 dialogue context/thread semantics;
it creates no persistence, watcher, Wake source, provider path, or Slack client.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from integrations.slack_agent_dialogue.contract import (
    AUTHORITY_CLASSES,
    FABLE_MESSAGE_TYPES,
    SOL_MESSAGE_TYPES,
    DialogueContractError,
    TrustedAuthorityPolicy,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_DISCRIMINATOR_V2,
    PARENT_DISCRIMINATOR_V2,
    build_parent_v2,
    parse_message_frame_v2,
    parse_parent_frame_v2,
    render_message_v2,
    validate_actor_ref,
    validate_applies_to_v2,
    validate_message_v2,
)
from integrations.slack_agent_dialogue.engine import (
    BoundThread,
    DialogueEngineError,
    DialoguePolicy,
    HistoryPage,
    MessageReceipt,
    ReadMessage,
    SlackDialogueClient,
    SlackEffectUnknown,
    SlackMessage,
    ThreadRead,
)

_CONTEXT_PROBE_SOL = "U00000000"
_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")


@dataclass(frozen=True)
class DialogueContextV2:
    """Trusted immutable V2 dialogue context; never derived from Slack prose."""

    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    operation_key: str
    watch_mode: str | None
    actor_ref: Mapping[str, Any]
    applies_to: Mapping[str, Any]

    def normalized(self) -> dict[str, Any]:
        """Normalize through the accepted V2 contracts without transport state."""

        try:
            parent = build_parent_v2(
                {
                    "schema": "mastermind.agent_dialogue_parent.v2",
                    "work_ref": self.work_ref,
                    "commission_ref": dict(self.commission_ref),
                    "session_ref": self.session_ref,
                    "operation_key": self.operation_key,
                    "watch_mode": self.watch_mode,
                    "allowed_sol_user_ids": [_CONTEXT_PROBE_SOL],
                    "created_at": "2000-01-01T00:00:00Z",
                }
            )
            actor = validate_actor_ref(dict(self.actor_ref))
            applies_to = validate_applies_to_v2(dict(self.applies_to))
        except (DialogueContractError, TypeError, ValueError):
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH") from None

        if actor["kind"] == "worker_attempt":
            if applies_to["kind"] != "executive_attempt" or any(
                actor[key] != applies_to[key]
                for key in ("job_id", "attempt_id", "worker_id")
            ):
                raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")

        return {
            "work_ref": parent["work_ref"],
            "commission_ref": parent["commission_ref"],
            "session_ref": parent["session_ref"],
            "operation_key": parent["operation_key"],
            "watch_mode": parent["watch_mode"],
            "actor_ref": actor,
            "applies_to": applies_to,
        }


def _parent_identity(parent: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        parent.get("work_ref"),
        parent.get("commission_ref"),
        parent.get("session_ref"),
        parent.get("operation_key"),
        parent.get("watch_mode"),
    )


def _context_parent_identity(context: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        context["work_ref"],
        context["commission_ref"],
        context["session_ref"],
        context["operation_key"],
        context["watch_mode"],
    )


def _one_field_different(left: tuple[Any, ...], right: tuple[Any, ...]) -> bool:
    return sum(a != b for a, b in zip(left, right, strict=True)) == 1


def _ts_order(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise DialogueEngineError("THREAD_MESSAGE_INVALID") from None


def _message_matches_history_parent(
    message: Mapping[str, Any], context: Mapping[str, Any]
) -> bool:
    return (
        message.get("work_ref") == context["work_ref"]
        and message.get("commission_ref") == context["commission_ref"]
        and message.get("session_ref") == context["session_ref"]
    )


def _message_matches_current_context(
    message: Mapping[str, Any], context: Mapping[str, Any]
) -> bool:
    return (
        _message_matches_history_parent(message, context)
        and message.get("applies_to") == context["applies_to"]
    )


def _messages_share_reply_lineage(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    return all(
        left.get(key) == right.get(key)
        for key in ("work_ref", "commission_ref", "session_ref")
    )


def _reply_direction_is_valid(
    request: Mapping[str, Any], reply: Mapping[str, Any]
) -> bool:
    """Keep Sol reply authority on the opposite, lawful side of a contributor turn."""

    request_actor = request["actor_ref"]
    reply_actor = reply["actor_ref"]
    if (
        reply_actor["kind"] != "executive_surface"
        or reply_actor["seat"] not in {"ceo", "chairman"}
    ):
        return False
    if request_actor["kind"] == "worker_attempt":
        return True
    if request_actor["kind"] != "executive_surface":
        return False
    if request_actor["seat"] == "coo":
        return True
    if request_actor["seat"] == "ceo":
        return reply_actor["seat"] == "chairman"
    return False


def _adjudicate_ruling_v2(
    request: Mapping[str, Any],
    reply: Mapping[str, Any],
    *,
    authority_policy: TrustedAuthorityPolicy,
) -> dict[str, Any]:
    """Apply the accepted RULING authority floor to validated V2 envelopes."""

    try:
        request_message = validate_message_v2(dict(request))
        reply_message = validate_message_v2(dict(reply))
    except DialogueContractError:
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH") from None

    if (
        request_message["message_type"] != "DECISION_REQUEST"
        or reply_message["message_type"] != "RULING"
        or reply_message["reply_to_message_key"] != request_message["message_key"]
        or not _messages_share_reply_lineage(request_message, reply_message)
    ):
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")

    body = reply_message["body"]
    options = {option["id"]: option for option in request_message["body"]["options"]}
    selected = body["selected_option"]
    if selected not in options:
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
    option = options[selected]

    model_escalation_floor = {
        "NONE": "WITHIN_COMMISSION",
        "CANONICAL_REF_REQUIRED": "CANONICAL_REF_REQUIRED",
        "CHAIRMAN_REQUIRED": "CHAIRMAN_REQUIRED",
    }[option["authority_effect"]]
    try:
        trusted_floor = authority_policy.minimum_authority(
            request=request_message,
            option=option,
        )
    except Exception:
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH") from None
    if trusted_floor not in AUTHORITY_CLASSES:
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")

    authority_rank = {
        "WITHIN_COMMISSION": 0,
        "CANONICAL_REF_REQUIRED": 1,
        "CHAIRMAN_REQUIRED": 2,
    }
    authority_class = body["authority_class"]
    minimum_rank = max(
        authority_rank[trusted_floor],
        authority_rank[model_escalation_floor],
    )
    if authority_rank[authority_class] < minimum_rank:
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")

    if authority_class == "WITHIN_COMMISSION":
        return {
            "disposition": option["disposition"],
            "executable": True,
            "selected_option": selected,
            "canonical_ref": None,
        }
    if authority_class == "CANONICAL_REF_REQUIRED":
        return {
            "disposition": "CANONICAL_REF_REQUIRED",
            "executable": False,
            "selected_option": selected,
            "canonical_ref": body["canonical_ref"],
        }
    return {
        "disposition": "CHAIRMAN_REQUIRED",
        "executable": False,
        "selected_option": selected,
        "canonical_ref": None,
    }


def _adjudicate_reply_v2(
    request: Mapping[str, Any],
    reply: Mapping[str, Any],
    *,
    authority_policy: TrustedAuthorityPolicy,
) -> dict[str, Any]:
    """Apply V1-equivalent Sol reply-family semantics to validated V2 envelopes."""

    try:
        request_message = validate_message_v2(dict(request))
        reply_message = validate_message_v2(dict(reply))
    except DialogueContractError:
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH") from None

    if (
        reply_message["reply_to_message_key"] != request_message["message_key"]
        or not _messages_share_reply_lineage(request_message, reply_message)
        or not _reply_direction_is_valid(request_message, reply_message)
    ):
        raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")

    message_type = reply_message["message_type"]
    if message_type == "RULING":
        return _adjudicate_ruling_v2(
            request_message,
            reply_message,
            authority_policy=authority_policy,
        )
    if message_type == "CONTINUE":
        if request_message["message_type"] not in {
            "ACK",
            "PROGRESS",
            "BLOCKED",
            "RESULT",
        }:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        if (
            request_message["message_type"] == "BLOCKED"
            and request_message["body"]["needed_from"] != "sol"
        ):
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        try:
            allowed = authority_policy.allows_continuation(
                request=request_message,
                reply=reply_message,
            )
        except Exception:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH") from None
        if allowed is not True:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        return {
            "disposition": "CONTINUE",
            "executable": True,
            "selected_option": None,
            "canonical_ref": None,
        }
    if message_type == "STOP":
        return {
            "disposition": "STOP",
            "executable": True,
            "selected_option": None,
            "canonical_ref": None,
        }
    if message_type == "AMENDMENT_AVAILABLE":
        return {
            "disposition": "CANONICAL_REF_REQUIRED",
            "executable": False,
            "selected_option": None,
            "canonical_ref": reply_message["body"]["canonical_ref"],
        }
    raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")


class DialogueEngineV2:
    """One production-inert V2 engine over the existing injected Slack client."""

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

    async def bind_or_verify_thread(self, context: DialogueContextV2) -> BoundThread:
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

        if not isinstance(page, HistoryPage) or not page.complete:
            raise DialogueEngineError("THREAD_HISTORY_INCOMPLETE")
        if not page.mutation_evidence_complete:
            raise DialogueEngineError("THREAD_RECONCILIATION_INCOMPLETE")

        matches: list[tuple[SlackMessage, Mapping[str, Any]]] = []
        near_matches: list[Mapping[str, Any]] = []
        wanted = _context_parent_identity(normalized)

        for transport in page.messages:
            if transport.thread_ts not in {None, transport.ts}:
                continue
            if transport.author_user_id not in self.policy.allowed_parent_user_ids:
                continue

            raw_text = transport.text
            if transport.deleted or transport.edited:
                if transport.created_text is None:
                    raise DialogueEngineError("THREAD_RECONCILIATION_INCOMPLETE")
                raw_text = transport.created_text
            if not raw_text.startswith(PARENT_DISCRIMINATOR_V2):
                continue

            try:
                parent = parse_parent_frame_v2(raw_text)
            except DialogueContractError:
                raise DialogueEngineError("PARENT_MESSAGE_INVALID") from None

            observed = _parent_identity(parent)
            if observed == wanted:
                if tuple(parent["allowed_sol_user_ids"]) != self.policy.allowed_sol_user_ids:
                    raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
                matches.append((transport, parent))
            elif _one_field_different(observed, wanted):
                near_matches.append(parent)

        if len(matches) == 1:
            transport, parent = matches[0]
            return BoundThread(
                thread_ts=transport.ts,
                parent_author_user_id=transport.author_user_id,
                parent_fingerprint=parent["fingerprint"],
            )
        if len(matches) > 1:
            raise DialogueEngineError("THREAD_BINDING_AMBIGUOUS")
        if near_matches:
            raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
        raise DialogueEngineError("THREAD_BINDING_AMBIGUOUS")

    def _sender_is_eligible(
        self, transport: SlackMessage, message: Mapping[str, Any]
    ) -> bool:
        # The Relay bot may project any already-validated logical actor; Slack
        # transport identity never becomes Executive/Worker authority.
        if transport.author_user_id == self.policy.relay_bot_user_id:
            return True
        if transport.author_user_id not in self.policy.allowed_sol_user_ids:
            return False
        actor = message["actor_ref"]
        return (
            actor["kind"] == "executive_surface"
            and actor["seat"] in {"ceo", "chairman"}
        )

    async def _history(
        self, *, thread_ts: str, context: DialogueContextV2
    ) -> ThreadRead:
        if not isinstance(thread_ts, str) or _TS_RE.fullmatch(thread_ts) is None:
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

            raw_text = transport.text
            if transport.deleted or transport.edited:
                mutated_count += 1
                if transport.created_text is None:
                    raise DialogueEngineError("THREAD_RECONCILIATION_INCOMPLETE")
                raw_text = transport.created_text

            if not raw_text.startswith(MESSAGE_DISCRIMINATOR_V2):
                continue

            # Unknown Slack identities are transport-ineligible even when their
            # text happens to be a valid V2 frame. Actor identity comes from the
            # validated frame, not from the Slack member/app identity.
            sender_known = (
                transport.author_user_id == self.policy.relay_bot_user_id
                or transport.author_user_id in self.policy.allowed_sol_user_ids
            )
            if not sender_known:
                ineligible_count += 1
                continue

            try:
                message = parse_message_frame_v2(raw_text)
            except DialogueContractError:
                raise DialogueEngineError("THREAD_MESSAGE_INVALID") from None

            if not _message_matches_history_parent(message, normalized_context):
                raise DialogueEngineError("THREAD_CONTEXT_MISMATCH")
            if not self._sender_is_eligible(transport, message):
                ineligible_count += 1
                continue

            eligible.setdefault(message["message_key"], []).append((transport, message))

        output: list[ReadMessage] = []
        for entries in eligible.values():
            fingerprints = {entry[1]["fingerprint"] for entry in entries}
            if len(fingerprints) != 1:
                raise DialogueEngineError("MESSAGE_KEY_CONFLICT")
            entries.sort(key=lambda entry: _ts_order(entry[0].ts))
            primary_transport, primary_message = entries[0]
            output.append(
                ReadMessage(
                    message=primary_message,
                    primary_ts=primary_transport.ts,
                    duplicate_timestamps=tuple(
                        transport.ts for transport, _message in entries[1:]
                    ),
                )
            )

        output.sort(key=lambda item: _ts_order(item.primary_ts))
        return ThreadRead(
            thread_ts=thread_ts,
            messages=tuple(output),
            historical_messages=(),
            ineligible_count=ineligible_count,
            mutated_count=mutated_count,
        )

    async def read_thread(
        self, *, thread_ts: str, context: DialogueContextV2
    ) -> ThreadRead:
        return await self._history(thread_ts=thread_ts, context=context)

    @staticmethod
    def _find_key(
        read: ThreadRead, *, message_key: str, fingerprint: str
    ) -> ReadMessage | None:
        matches = [
            item for item in read.messages if item.message["message_key"] == message_key
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise DialogueEngineError("MESSAGE_KEY_CONFLICT")
        candidate = matches[0]
        if candidate.message["fingerprint"] != fingerprint:
            raise DialogueEngineError("MESSAGE_KEY_CONFLICT")
        return candidate

    def _validate_outbound(
        self, message: Mapping[str, Any], *, context: DialogueContextV2
    ) -> dict[str, Any]:
        try:
            validated = validate_message_v2(dict(message))
        except DialogueContractError:
            raise DialogueEngineError("THREAD_MESSAGE_INVALID") from None
        normalized = context.normalized()
        if (
            not _message_matches_current_context(validated, normalized)
            or validated["actor_ref"] != normalized["actor_ref"]
        ):
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
        context: DialogueContextV2,
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
        context: DialogueContextV2,
        message: Mapping[str, Any],
    ) -> MessageReceipt:
        validated = self._validate_outbound(message, context=context)
        text = render_message_v2(validated)
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
        context: DialogueContextV2,
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

        normalized = context.normalized()
        for index in range(attempts):
            read = await self._history(thread_ts=thread_ts, context=context)
            request_matches = [
                item
                for item in read.messages
                if item.message["message_key"] == request_message_key
                and item.message["message_type"] in FABLE_MESSAGE_TYPES
                and item.message["actor_ref"] == normalized["actor_ref"]
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
                authority = _adjudicate_reply_v2(
                    request,
                    reply.message,
                    authority_policy=self.authority_policy,
                )
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
            "schema": "mastermind.agent_dialogue_status.v2",
            "status": "DEVELOPMENT_UNARMED",
            "workspace_id": self.policy.workspace_id,
            "channel_id": self.policy.channel_id,
            "relay_bot_user_id": self.policy.relay_bot_user_id,
            "sol_sender_count": len(self.policy.allowed_sol_user_ids),
            "method_timeout_seconds": self.policy.method_timeout_seconds,
            "persistent_state": False,
            "production_token_installed": False,
            "production_armed": False,
        }


__all__ = ["DialogueContextV2", "DialogueEngineV2"]
