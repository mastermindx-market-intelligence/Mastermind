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
from typing import Any, Mapping

from integrations.slack_agent_dialogue.contract import (
    DialogueContractError,
    TrustedAuthorityPolicy,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_DISCRIMINATOR_V2,
    PARENT_DISCRIMINATOR_V2,
    build_parent_v2,
    parse_message_frame_v2,
    parse_parent_frame_v2,
    validate_actor_ref,
    validate_applies_to_v2,
)
from integrations.slack_agent_dialogue.engine import (
    BoundThread,
    DialogueEngineError,
    DialoguePolicy,
    HistoryPage,
    ReadMessage,
    SlackDialogueClient,
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


def _message_context_matches(
    message: Mapping[str, Any], context: Mapping[str, Any]
) -> bool:
    return (
        message.get("work_ref") == context["work_ref"]
        and message.get("commission_ref") == context["commission_ref"]
        and message.get("session_ref") == context["session_ref"]
        and message.get("applies_to") == context["applies_to"]
    )


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

            if not _message_context_matches(message, normalized_context):
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


__all__ = ["DialogueContextV2", "DialogueEngineV2"]
