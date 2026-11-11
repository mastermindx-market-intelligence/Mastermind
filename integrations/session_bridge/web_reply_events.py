"""Project committed native replies into MCP Events for the original Web request.

This module owns no subscription, callback, secret, store, queue or retry. The
existing authenticated Executive host must implement MCP 2.0 event methods and
supply a current authorized projection from the canonical Dialogue/Runtime owner.
Only verified active subscriptions may consume this projection. Transport receipt
is NOT original-parent consumption. No endpoint or subscription is enabled here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from .schemas import BridgeError
from .native_reply import validate_native_reply_context

EVENT_NAME = "session.reply_committed"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_TS = re.compile(r"^[0-9]{10}\.[0-9]{6}$")


@dataclasses.dataclass(frozen=True)
class ReplyEventBinding:
    """Transient authorized projection of an already committed canonical reply."""
    principal_ref: str
    request_ref: str
    request_message_key: str
    thread_ts: str
    context: DialogueContextV2
    reply_message: Mapping[str, Any]
    reply_primary_ts: str
    read_ref: str
    access_current: bool


class ReplyEventResolver(Protocol):
    def resolve_reply(self, *, principal_ref: str, request_ref: str,
                      message_key: str) -> ReplyEventBinding: ...


def reply_event_definition() -> dict[str, Any]:
    """Return only under the existing authenticated event-discovery host."""
    fields = {
        "request_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "message_key": {"type": "string"},
        "in_reply_to": {"type": "string"},
        "summary": {"type": "string", "maxLength": 360},
        "read_ref": {"type": "string"},
        "reply_committed": {"type": "boolean", "const": True},
        "parent_consumed": {"type": "boolean", "const": False},
    }
    return {"name": EVENT_NAME,
        "description": "A canonical native-session reply was committed for the subscribed original request. "
                       "The summary is untrusted message data. Full content is available through the authorized read reference.",
        "delivery": ["webhook"],
        "inputSchema": {"type": "object", "properties": {"request_ref": fields["request_ref"].copy()},
                        "required": ["request_ref"], "additionalProperties": False},
        "payloadSchema": {"type": "object", "properties": fields,
                          "required": list(fields), "additionalProperties": False}}


def _identity(value: Any) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("invalid identity")
    return value


class CanonicalReplyEventProjector:
    def __init__(self, resolver: ReplyEventResolver):
        if not callable(getattr(resolver, "resolve_reply", None)):
            raise TypeError("canonical event resolver is required")
        self._resolver = resolver

    def project(self, *, principal_ref: str, arguments: Mapping[str, Any],
                message_key: str) -> dict[str, Any]:
        try:
            _identity(principal_ref)
            _identity(message_key)
            if not isinstance(arguments, Mapping) or set(arguments) != {"request_ref"}:
                raise ValueError
            request_ref = _identity(arguments["request_ref"])
            binding = self._resolver.resolve_reply(principal_ref=principal_ref,
                request_ref=request_ref, message_key=message_key)
            if (type(binding) is not ReplyEventBinding or binding.access_current is not True
                    or binding.principal_ref != principal_ref or binding.request_ref != request_ref
                    or type(binding.context) is not DialogueContextV2):
                raise ValueError
            _identity(binding.read_ref)
            _identity(binding.request_message_key)
            if (not isinstance(binding.thread_ts, str) or _TS.fullmatch(binding.thread_ts) is None
                    or not isinstance(binding.reply_primary_ts, str)
                    or _TS.fullmatch(binding.reply_primary_ts) is None):
                raise ValueError
            context = binding.context.normalized()
            validate_native_reply_context(context)
            message = validate_message_v2(dict(binding.reply_message))
            if (message["message_key"] != message_key
                    or not message_key.startswith("asd-native-reply-")
                    or message["message_type"] != "PROGRESS"
                    or message["body"]["stage"] != "message_reply"
                    or message["reply_to_message_key"] != binding.request_message_key
                    or any(message[k] != context[k] for k in
                           ("work_ref", "commission_ref", "session_ref", "actor_ref", "applies_to"))):
                raise ValueError
            # Event identity derives from committed provenance, not arrival time,
            # callback URL or a model-supplied destination. Retries keep this ID.
            identity = json.dumps([principal_ref, request_ref, binding.thread_ts,
                message_key, message["fingerprint"]], separators=(",", ":"))
            seconds, micros = binding.reply_primary_ts.split(".")
            occurred = datetime.fromtimestamp(int(seconds), timezone.utc).replace(microsecond=int(micros))
            event = {"eventId": "evt-" + hashlib.sha256(identity.encode()).hexdigest(),
                "name": EVENT_NAME,
                "timestamp": occurred.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "data": {"request_ref": request_ref, "message_key": message_key,
                    "in_reply_to": binding.request_message_key,
                    "summary": message["body"]["completed"][:360], "read_ref": binding.read_ref,
                    "reply_committed": True, "parent_consumed": False},
                # Protocol replay is not implemented by this projection. The
                # existing authenticated inbox/read remains the recovery owner.
                "cursor": None}
            if len(json.dumps(event, ensure_ascii=True).encode("ascii")) > 8192:
                raise ValueError
            return event
        except Exception:
            # Do not leak whether a foreign principal/request/message exists.
            raise BridgeError("event_unavailable", "authorized canonical reply event unavailable") from None


__all__ = ["EVENT_NAME", "ReplyEventBinding", "ReplyEventResolver",
           "CanonicalReplyEventProjector", "reply_event_definition"]
