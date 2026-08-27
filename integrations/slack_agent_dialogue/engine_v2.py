"""Storeless worker-aware Active-Session Dialogue V2 engine.

WP-1 keeps Slack transport, bounded history, and authority policy injection in
existing owners. This module adds only V2 dialogue context/thread semantics;
it creates no persistence, watcher, Wake source, provider path, or Slack client.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping

from integrations.slack_agent_dialogue.contract import (
    DialogueContractError,
    TrustedAuthorityPolicy,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    PARENT_DISCRIMINATOR_V2,
    build_parent_v2,
    parse_parent_frame_v2,
    validate_actor_ref,
    validate_applies_to_v2,
)
from integrations.slack_agent_dialogue.engine import (
    BoundThread,
    DialogueEngineError,
    DialoguePolicy,
    HistoryPage,
    SlackDialogueClient,
)

_CONTEXT_PROBE_SOL = "U00000000"


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

        matches: list[tuple[Any, Mapping[str, Any]]] = []
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


__all__ = ["DialogueContextV2", "DialogueEngineV2"]
