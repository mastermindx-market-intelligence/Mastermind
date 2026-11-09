"""Verified Slack event -> governed Hermes role/session request, default OFF.

This is an ingress adapter, not a Slack listener or Hermes launcher. An already
installed Executive Relay HTTP/Socket Mode owner must verify and ACK envelopes,
then use this adapter with its original authenticated native-session resolver.
No request here creates a session, Wake obligation, queue, message ledger or Slack
post. Current Runtime/Agent Dialogue alone can bind, admit, dedup and deliver a
model turn, and the incumbent reply writer owns the same-thread result.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

MAX_EVENT_BYTES = 65536
MAX_TEXT_BYTES = 4096
MAX_SKEW_SECONDS = 300
_USER = re.compile(r"U[A-Z0-9]{8,31}\Z")
_BOT = re.compile(r"U[A-Z0-9]{8,31}\Z")
_CHANNEL = re.compile(r"[CGD][A-Z0-9]{8,31}\Z")
_TEAM = re.compile(r"T[A-Z0-9]{8,31}\Z")
_APP = re.compile(r"A[A-Z0-9]{8,31}\Z")
_TS = re.compile(r"[1-9][0-9]{9,15}\.[0-9]{6}\Z")
_EVENT_ID = re.compile(r"Ev[A-Z0-9]{8,60}\Z")
_ROLE_HANDLE = re.compile(r"\A\s*(?:#)?([a-z][a-z0-9-]{1,39})\s*:\s*(.*)\Z", re.I | re.S)
_SECRET = re.compile(r"(?i)(?:xox[baprs]-[A-Za-z0-9-]+|sk-[A-Za-z0-9_-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_-]?key|password|token)\s*[:=]\s*\S+)")


class IngressRefusal(ValueError):
    """Fixed code; never reflect Slack content, signing secrets or model text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _reject(code: str) -> None:
    raise IngressRefusal(code)


def _no_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            _reject("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _no_constant(_value: str) -> None:
    _reject("INVALID_JSON_CONSTANT")


def verify_signed_event(
    body: bytes,
    headers: Mapping[str, str],
    *,
    signing_secret: bytes,
    now: int | None = None,
) -> dict[str, Any]:
    """Validate original raw Slack HTTP request BEFORE JSON parsing/ACK.

    The signing secret stays with the already-authorized Slack ingress owner.
    This function is not a new HTTPS server or token store. Verification of a
    request does not authorize its sender, role, or subsequent model admission.
    """
    if type(body) is not bytes or not 0 < len(body) <= MAX_EVENT_BYTES:
        _reject("EVENT_BODY_INVALID")
    if type(signing_secret) is not bytes or not signing_secret:
        _reject("SIGNING_SECRET_UNAVAILABLE")
    if not isinstance(headers, Mapping):
        _reject("SIGNATURE_MISSING")
    try:
        clean_headers = {str(k).lower(): v for k, v in headers.items()}
        timestamp = clean_headers["x-slack-request-timestamp"]
        signature = clean_headers["x-slack-signature"]
    except (KeyError, AttributeError, TypeError):
        _reject("SIGNATURE_MISSING")
    if (type(timestamp) is not str or not re.fullmatch(r"[0-9]{10,12}", timestamp)
            or type(signature) is not str or not re.fullmatch(r"v0=[0-9a-f]{64}", signature)):
        _reject("SIGNATURE_INVALID")
    observed_now = int(time.time()) if now is None else now
    if type(observed_now) is not int or abs(observed_now - int(timestamp)) > MAX_SKEW_SECONDS:
        _reject("SIGNATURE_EXPIRED")
    base = b"v0:" + timestamp.encode("ascii") + b":" + body
    digest = "v0=" + hmac.new(signing_secret, base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        _reject("SIGNATURE_INVALID")
    try:
        payload = json.loads(body.decode("utf-8", "strict"), object_pairs_hook=_no_duplicates,
                             parse_constant=_no_constant)
    except IngressRefusal:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        _reject("EVENT_JSON_INVALID")
    if type(payload) is not dict:
        _reject("EVENT_JSON_INVALID")
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class CurrentThread:
    """Already-current binding read from the native owner, not Slack content."""

    workspace_id: str
    channel_id: str
    thread_ts: str
    role: str
    target_ref: str
    session_generation: str


@dataclasses.dataclass(frozen=True, slots=True)
class CurrentTarget:
    """An enrolled native Hermes role selected by the authenticated host."""

    role: str
    target_ref: str
    session_generation: str


@dataclasses.dataclass(frozen=True, slots=True)
class SlackTurn:
    """Correlation only. Delivery/admission/consumption are other owners."""

    event_id: str
    source_ref: str
    workspace_id: str
    channel_id: str
    sender_user_id: str
    source_ts: str
    thread_ts: str
    role: str
    target_ref: str
    session_generation: str
    message: str
    action: str  # NEW, CONTINUE, or HANDOFF_REQUIRES_AUTHORIZATION


def _reference(team: str, channel: str, ts: str) -> str:
    # Identical logical Slack message delivered through app_mention/message
    # maps to one reference; Executive/Dialogue owns durable de-duplication.
    data = "mastermind.hermes.slack-source.v1\n" + team + "\n" + channel + "\n" + ts
    return "slack-source-" + hashlib.sha256(data.encode("ascii")).hexdigest()


class SlackHermesIngress:
    """Parse one signed, host-authorized event against current native bindings.

    Construct only in the existing authenticated Executive Relay owner. A
    response is a proposed session-send input, not permission to send or post.
    The host must admit it under the original canonical Runtime/session owner.
    """

    def __init__(
        self,
        *,
        workspace_id: str,
        app_id: str,
        relay_bot_user_id: str,
        allowed_channel_ids: frozenset[str],
        role_handles: Mapping[str, str],
        channel_defaults: Mapping[str, str],
        principal_for: Callable[[str, str], str | None],
        thread_binding: Callable[[str, str, str], CurrentThread | None],
        current_target: Callable[[str, str], CurrentTarget | None],
    ) -> None:
        if (_TEAM.fullmatch(workspace_id or "") is None
                or _APP.fullmatch(app_id or "") is None
                or _BOT.fullmatch(relay_bot_user_id or "") is None
                or type(allowed_channel_ids) is not frozenset
                or not allowed_channel_ids
                or any(_CHANNEL.fullmatch(ch) is None for ch in allowed_channel_ids)
                or not isinstance(role_handles, Mapping) or not role_handles
                or any(type(k) is not str or _ROLE_HANDLE.fullmatch(k + ": x") is None
                       or type(v) is not str or not v for k, v in role_handles.items())
                or not isinstance(channel_defaults, Mapping)
                or any(ch not in allowed_channel_ids or role not in role_handles.values()
                       for ch, role in channel_defaults.items())
                or not callable(principal_for)
                or not callable(thread_binding)
                or not callable(current_target)):
            _reject("INGRESS_CONFIGURATION_INVALID")
        self.workspace_id = workspace_id
        self.app_id = app_id
        self.relay_bot_user_id = relay_bot_user_id
        self.allowed_channel_ids = allowed_channel_ids
        self.role_handles = {k.casefold(): v for k, v in role_handles.items()}
        if len(self.role_handles) != len(role_handles):
            _reject("INGRESS_ALIAS_CONFLICT")
        self.channel_defaults = dict(channel_defaults)
        self.principal_for = principal_for
        self.thread_binding = thread_binding
        self.current_target = current_target

    def route_verified(self, envelope: Mapping[str, Any]) -> SlackTurn | None:
        """Only accepts input *already* checked by verify_signed_event.

        Message text cannot name RuntimeBinding, credentials, destination,
        native provider, host or account. Native targets come from the trusted
        current resolver, and an existing bound thread cannot be silently moved.
        """
        if type(envelope) is not dict or envelope.get("type") != "event_callback":
            _reject("EVENT_NOT_CALLBACK")
        if (envelope.get("team_id") != self.workspace_id
                or envelope.get("api_app_id") != self.app_id):
            _reject("WRONG_SLACK_INSTALLATION")
        event_id = envelope.get("event_id")
        event = envelope.get("event")
        if type(event_id) is not str or _EVENT_ID.fullmatch(event_id) is None or type(event) is not dict:
            _reject("EVENT_IDENTITY_INVALID")
        kind = event.get("type")
        if kind not in {"app_mention", "message"}:
            return None
        # Unlike an existing conversation, a bot-authored cross-agent Slack
        # post is not an independent authorization to trigger another agent.
        if event.get("subtype") is not None or "bot_id" in event or "app_id" in event:
            return None
        user = event.get("user")
        channel = event.get("channel")
        ts = event.get("ts")
        thread_ts = event.get("thread_ts", ts)
        raw_text = event.get("text")
        if (type(user) is not str or _USER.fullmatch(user) is None
                or user == self.relay_bot_user_id or type(channel) is not str
                or _CHANNEL.fullmatch(channel) is None
                or channel not in self.allowed_channel_ids
                or type(ts) is not str or _TS.fullmatch(ts) is None
                or type(thread_ts) is not str or _TS.fullmatch(thread_ts) is None
                or type(raw_text) is not str or not raw_text.strip()
                or len(raw_text.encode("utf-8", "strict")) > MAX_TEXT_BYTES
                or _SECRET.search(raw_text)):
            _reject("UNAUTHORIZED_OR_INVALID_MESSAGE")
        # Message events in channel/DM and app_mention may overlap. The former
        # may enter only with a *real* direct mention, existing thread binding,
        # or an allowed DM. A channel message with an incidental alias is inert.
        mentioned = f"<@{self.relay_bot_user_id}>" in raw_text
        is_dm = channel.startswith("D")
        if kind == "app_mention" and (is_dm or not mentioned):
            _reject("MENTION_EVENT_MISMATCH")
        if kind == "message" and event.get("channel_type") == "im" and not is_dm:
            _reject("CHANNEL_TYPE_MISMATCH")
        try:
            principal = self.principal_for(self.workspace_id, user)
        except Exception:
            _reject("PRINCIPAL_RESOLUTION_UNAVAILABLE")
        if type(principal) is not str or not principal:
            _reject("SLACK_SENDER_NOT_AUTHORIZED")
        try:
            bound = self.thread_binding(self.workspace_id, channel, thread_ts)
        except Exception:
            _reject("THREAD_RESOLUTION_UNAVAILABLE")
        if bound is not None and (type(bound) is not CurrentThread
                or bound.workspace_id != self.workspace_id
                or bound.channel_id != channel or bound.thread_ts != thread_ts
                or bound.role not in self.role_handles.values()
                or not bound.target_ref or not bound.session_generation):
            _reject("THREAD_BINDING_INVALID")
        if not (mentioned or is_dm or bound is not None):
            return None
        mention_text = raw_text.split(f"<@{self.relay_bot_user_id}>", 1)[1] if mentioned else raw_text
        matched = _ROLE_HANDLE.fullmatch(mention_text)
        requested = None
        if matched:
            requested = self.role_handles.get(matched.group(1).casefold())
            if requested is None:
                _reject("UNKNOWN_ROLE_HANDLE")
            message = matched.group(2).strip()
        else:
            message = mention_text.strip()
        if not message:
            _reject("EMPTY_REQUEST")
        if bound is not None:
            if requested is not None and requested != bound.role:
                # Authorization for cross-agent handoffs is a separate
                # incumbent admission, not a router selection side effect.
                action = "HANDOFF_REQUIRES_AUTHORIZATION"
                role = requested
            else:
                action = "CONTINUE"
                role = bound.role
        else:
            if not (mentioned or is_dm):
                return None
            role = requested or self.channel_defaults.get(channel)
            if role is None:
                _reject("ROLE_SELECTION_REQUIRED")
            action = "NEW"
        try:
            target = self.current_target(principal, role)
        except Exception:
            _reject("NATIVE_TARGET_RESOLUTION_UNAVAILABLE")
        if (type(target) is not CurrentTarget or target.role != role
                or not target.target_ref or not target.session_generation):
            _reject("ROLE_NOT_CURRENTLY_ENROLLED")
        if action == "CONTINUE" and (bound.role != target.role
                or bound.target_ref != target.target_ref
                or bound.session_generation != target.session_generation):
            _reject("THREAD_NATIVE_BINDING_CHANGED")
        return SlackTurn(
            event_id=event_id,
            source_ref=_reference(self.workspace_id, channel, ts),
            workspace_id=self.workspace_id,
            channel_id=channel,
            sender_user_id=user,
            source_ts=ts,
            thread_ts=thread_ts,
            role=role,
            target_ref=target.target_ref,
            session_generation=target.session_generation,
            message=message,
            action=action,
        )
