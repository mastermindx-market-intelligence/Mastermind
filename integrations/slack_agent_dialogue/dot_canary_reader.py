"""Command-scoped Chris-Dot canary observation using the EXISTING A2 Slack client.

The relay's fixed channel, workspace, bot and token must already be enrolled.
No new Slack app, Slack listener, Events API, Socket Mode, poller, OAuth grant,
scheduler or event queue. A trusted owner invokes one explicit thread read;
incomplete history, mutation uncertainty, and foreign sender data refuse.
This reader itself never sends an MCP event.
"""
from __future__ import annotations

import dataclasses
import re

from integrations.slack_agent_dialogue.dot_canary_event import (
    MARKER, TrustedCanaryPolicy, VerifiedSlackCanaryMessage, canary_event_definition,
)
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient

_TS = re.compile(r"^[0-9]{10,16}\.[0-9]{6}$")
MAX_THREAD_MESSAGES = 64


class CanarySourceUnavailable(ValueError):
    """No authenticated complete Slack canary evidence; nothing may be sent."""


class ExistingA2CanaryReader:
    """Injected only by the incumbent A2 client owner; no token access granted."""

    def __init__(self, client: SlackWebApiDialogueClient, policy: TrustedCanaryPolicy):
        if type(client) is not SlackWebApiDialogueClient or type(policy) is not TrustedCanaryPolicy:
            raise TypeError("existing enrolled A2 Slack client and policy required")
        canary_event_definition(policy)
        if (client._workspace_id != policy.workspace_id
                or client._channel_id != policy.channel_id
                or client._bot_user_id != policy.relay_bot_user_id):
            raise CanarySourceUnavailable("A2 channel or bot identity differs")
        self.client, self.policy = client, policy

    async def observe(self, *, thread_ts: str, message_ts: str) -> VerifiedSlackCanaryMessage | None:
        """Return only a complete owner-authored, unmodified, marked observation."""
        if (type(thread_ts) is not str or _TS.fullmatch(thread_ts) is None
                or type(message_ts) is not str or _TS.fullmatch(message_ts) is None):
            raise CanarySourceUnavailable("exact canonical Slack thread/message required")
        try:
            page = await self.client.fetch_thread(
                channel_id=self.policy.channel_id,
                thread_ts=thread_ts,
                limit=MAX_THREAD_MESSAGES,
            )
        except Exception:
            raise CanarySourceUnavailable("original A2 Slack read unavailable") from None
        if (page.complete is not True or page.mutation_evidence_complete is not True):
            raise CanarySourceUnavailable("Slack thread is incomplete or mutation-ambiguous")
        matches = [message for message in page.messages if message.ts == message_ts]
        if len(matches) != 1:
            raise CanarySourceUnavailable("unique current Slack message not proven")
        m = matches[0]
        if (m.thread_ts not in (thread_ts, None)
                or m.thread_ts is None and m.ts != thread_ts
                or m.edited is True or m.deleted is True
                or m.author_user_id != self.policy.owner_slack_user_id
                or not m.text.startswith(MARKER)):
            return None
        return VerifiedSlackCanaryMessage(
            workspace_id=self.policy.workspace_id,
            channel_id=self.policy.channel_id,
            ts=m.ts,
            author_user_id=m.author_user_id,
            text=m.text,
            thread_ts=m.thread_ts,
            history_complete=True,
            mutation_evidence_complete=True,
            edited=False,
            deleted=False,
        )


__all__ = ["ExistingA2CanaryReader", "CanarySourceUnavailable"]
