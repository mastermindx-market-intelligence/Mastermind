"""Deterministic in-memory Slack seam for A1 tests and demonstrations."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from integrations.slack_agent_dialogue.engine import (
    HistoryPage,
    SlackEffectUnknown,
    SlackMessage,
    SlackTransportUnavailable,
)


@dataclass
class InMemorySlackClient:
    relay_bot_user_id: str
    channel_messages: list[SlackMessage] = field(default_factory=list)
    thread_messages: dict[str, list[SlackMessage]] = field(default_factory=dict)
    channel_history_complete: bool = True
    thread_history_complete: bool = True
    channel_mutation_evidence_complete: bool = True
    thread_mutation_evidence_complete: bool = True
    post_behaviors: list[str] = field(default_factory=list)
    post_call_count: int = 0
    next_timestamp: Decimal = Decimal("1787472000.000001")

    async def fetch_channel_history(
        self, *, channel_id: str, limit: int
    ) -> HistoryPage:
        messages = tuple(reversed(self.channel_messages[-limit:]))
        return HistoryPage(
            messages=messages,
            complete=self.channel_history_complete,
            mutation_evidence_complete=self.channel_mutation_evidence_complete,
        )

    async def fetch_thread(
        self, *, channel_id: str, thread_ts: str, limit: int
    ) -> HistoryPage:
        parent = [
            message for message in self.channel_messages if message.ts == thread_ts
        ]
        replies = self.thread_messages.get(thread_ts, [])
        messages = tuple((parent + replies)[-limit:])
        return HistoryPage(
            messages=messages,
            complete=self.thread_history_complete,
            mutation_evidence_complete=self.thread_mutation_evidence_complete,
        )

    async def post_reply(
        self, *, channel_id: str, thread_ts: str, text: str
    ) -> SlackMessage:
        self.post_call_count += 1
        behavior = self.post_behaviors.pop(0) if self.post_behaviors else "success"
        if behavior == "definitive_error":
            raise SlackTransportUnavailable("definitive failure")
        if behavior == "unknown_no_commit":
            raise SlackEffectUnknown("reply lost before commit")
        message = SlackMessage(
            ts=self._mint_ts(),
            author_user_id=self.relay_bot_user_id,
            text=text,
            thread_ts=thread_ts,
        )
        self.thread_messages.setdefault(thread_ts, []).append(message)
        if behavior == "commit_unknown":
            raise SlackEffectUnknown("reply lost after commit")
        if behavior == "wrong_author":
            return SlackMessage(
                ts=message.ts,
                author_user_id="U0000000000",
                text=text,
                thread_ts=thread_ts,
            )
        if behavior == "wrong_text":
            return SlackMessage(
                ts=message.ts,
                author_user_id=message.author_user_id,
                text=text + " drift",
                thread_ts=thread_ts,
            )
        return message

    def _mint_ts(self) -> str:
        value = self.next_timestamp
        self.next_timestamp += Decimal("0.000001")
        whole, fractional = f"{value:.6f}".split(".")
        return f"{whole}.{fractional}"

    def add_parent(self, message: SlackMessage) -> None:
        self.channel_messages.append(message)
        self.thread_messages.setdefault(message.ts, [])

    def add_reply(self, message: SlackMessage) -> None:
        if message.thread_ts is None:
            raise ValueError("reply must have thread_ts")
        self.thread_messages.setdefault(message.thread_ts, []).append(message)

    def mutate_parent(
        self,
        *,
        message_ts: str,
        text: str | None = None,
        edited: bool | None = None,
        deleted: bool | None = None,
    ) -> None:
        for index, message in enumerate(self.channel_messages):
            if message.ts != message_ts:
                continue
            next_edited = message.edited if edited is None else edited
            next_deleted = message.deleted if deleted is None else deleted
            if text is not None and text != message.text and edited is None:
                next_edited = True
            created_text = message.created_text
            if (next_edited or next_deleted) and created_text is None:
                created_text = message.text
            self.channel_messages[index] = SlackMessage(
                ts=message.ts,
                author_user_id=message.author_user_id,
                text=message.text if text is None else text,
                thread_ts=message.thread_ts,
                edited=next_edited,
                deleted=next_deleted,
                created_text=created_text,
            )
            return
        raise KeyError(message_ts)

    def mutate_reply(
        self,
        *,
        thread_ts: str,
        message_ts: str,
        text: str | None = None,
        edited: bool | None = None,
        deleted: bool | None = None,
    ) -> None:
        messages = self.thread_messages.get(thread_ts, [])
        for index, message in enumerate(messages):
            if message.ts != message_ts:
                continue
            next_edited = message.edited if edited is None else edited
            next_deleted = message.deleted if deleted is None else deleted
            if text is not None and text != message.text and edited is None:
                next_edited = True
            created_text = message.created_text
            if (next_edited or next_deleted) and created_text is None:
                created_text = message.text
            messages[index] = SlackMessage(
                ts=message.ts,
                author_user_id=message.author_user_id,
                text=message.text if text is None else text,
                thread_ts=message.thread_ts,
                edited=next_edited,
                deleted=next_deleted,
                created_text=created_text,
            )
            return
        raise KeyError(message_ts)
