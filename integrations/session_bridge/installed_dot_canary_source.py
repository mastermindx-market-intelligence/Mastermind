"""Read a Chris-Dot canary through the incumbent peer-authenticated A2 socket.

No Slack token is exported to Executive. This is a single authorized read, not
a poller, new listener, event subscription, or OAuth account bridge. The A2
server must separately opt in to read_dot_canary and uses the original bound
Slack Web API client; the Executive host supplies its *current* closed policy.
"""
from __future__ import annotations

from pathlib import Path
import dataclasses
import re

from integrations.slack_agent_dialogue.dot_canary_event import (
    TrustedCanaryPolicy, VerifiedSlackCanaryMessage, canary_event_definition,
)
from integrations.slack_agent_dialogue.dot_canary_reader import CanarySourceUnavailable
from integrations.slack_agent_dialogue.runtime import AGENT_RELAY_SOCKET_PATH
from integrations.slack_agent_dialogue.service import CONTROL_VERSION_V2, call_service

_TS = re.compile(r"^[0-9]{10,16}\.[0-9]{6}$")


class InstalledA2CanaryReader:
    """The original A2 socket and current Executive selected message policy."""

    def __init__(self, socket_path: Path, policy: TrustedCanaryPolicy, *, transport=None):
        if (Path(socket_path) != AGENT_RELAY_SOCKET_PATH
                or type(policy) is not TrustedCanaryPolicy):
            raise TypeError("fixed enrolled A2 socket and current account policy required")
        canary_event_definition(policy)
        if transport is not None and not callable(transport):
            raise TypeError("call-service test seam must be callable")
        self.socket_path, self.policy = Path(socket_path), policy
        self._transport = transport or call_service

    async def observe(self, *, thread_ts: str, message_ts: str) -> VerifiedSlackCanaryMessage | None:
        if (type(thread_ts) is not str or _TS.fullmatch(thread_ts) is None
                or type(message_ts) is not str or _TS.fullmatch(message_ts) is None):
            raise CanarySourceUnavailable("exact Slack message identity required")
        request = {
            "version": CONTROL_VERSION_V2,
            "operation": "read_dot_canary",
            "args": {
                "thread_ts": thread_ts,
                "message_ts": message_ts,
                "owner_slack_user_id": self.policy.owner_slack_user_id,
                "principal_digest": self.policy.principal_digest,
                "not_before_ts": self.policy.not_before_ts,
            },
        }
        try:
            reply=await self._transport(self.socket_path,request,timeout_seconds=12)
        except Exception:
            raise CanarySourceUnavailable("original A2 peer read unavailable") from None
        if (type(reply) is not dict or set(reply)!={"ok","result"}
                or reply["ok"] is not True or type(reply["result"]) is not dict
                or set(reply["result"])!={"state","message"}):
            raise CanarySourceUnavailable("untrusted A2 peer observation")
        payload=reply["result"]
        if payload["state"]=="NOT_ELIGIBLE" and payload["message"] is None:
            return None
        fields={x.name for x in dataclasses.fields(VerifiedSlackCanaryMessage)}
        if (payload["state"]!="OBSERVED" or type(payload["message"]) is not dict
                or set(payload["message"])!=fields):
            raise CanarySourceUnavailable("unknown A2 canary source")
        try:
            m=VerifiedSlackCanaryMessage(**payload["message"])
            if (m.workspace_id!=self.policy.workspace_id
                    or m.channel_id!=self.policy.channel_id
                    or m.author_user_id!=self.policy.owner_slack_user_id
                    or m.ts!=message_ts
                    or m.thread_ts not in (thread_ts,None)
                    or m.thread_ts is None and m.ts!=thread_ts
                    or m.history_complete is not True
                    or m.mutation_evidence_complete is not True
                    or m.edited is not False or m.deleted is not False
                    or type(m.text) is not str
                    or not m.text.startswith("MMX_CHRIS_DOT_CANARY_V1:")
                    or len(m.text)>360):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise CanarySourceUnavailable("A2 canary data differs from current policy") from None
        return m


__all__=["InstalledA2CanaryReader"]
