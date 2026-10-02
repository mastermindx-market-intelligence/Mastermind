"""Pure first-party ChatGPT Desktop provider-identity reducer.

The native wrapper may read the logged-in user's own ChatGPT application log, but
must pass only bounded lines from the exact PID-bound log into this module. This
module recognizes a closed set of OpenAI application identity events and emits no
transcript, credential, cookie, request body, or arbitrary log content.

The Runtime/OHF provider_session_id remains authoritative. Log recency,
frequency, sidebar titles, AX element ids, local hashes, and model prose are never
allowed to select or mint a provider session or turn identity.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Iterable

from .turn import DesktopSnapshot, DesktopTarget, EvidenceError, PreparedTurn

MAX_PROVIDER_LOG_LINES = 20000
MAX_PROVIDER_LOG_LINE_BYTES = 16384

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_UUID_RE = re.compile(rf"^{_UUID}$")
_LOG_NAME_RE = re.compile(
    rf"^codex-desktop-(?P<app_session>{_UUID})-(?P<pid>[1-9][0-9]*)-"
    r"t[0-9]+-i[0-9]+-[0-9]+-[0-9]+\.log$"
)
_TIMESTAMP_RE = re.compile(r"^(?P<timestamp>\S+)")
_ID_FIELD_RE = {
    key: re.compile(rf"(?:^|\s){key}=(?P<value>{_UUID})(?:\s|$)")
    for key in ("conversationId", "threadId", "latestTurnId")
}
_FIXED_FIELD_RE = {
    "documentVisibilityState": re.compile(
        r"(?:^|\s)documentVisibilityState=(?P<value>[A-Za-z_-]+)(?:\s|$)"
    ),
    "assignedStreamRole": re.compile(
        r"(?:^|\s)assignedStreamRole=(?P<value>[A-Za-z_-]+)(?:\s|$)"
    ),
    "hasLatestThreadSettings": re.compile(
        r"(?:^|\s)hasLatestThreadSettings=(?P<value>true|false)(?:\s|$)"
    ),
}

_RESUME_MARKER = "[electron-message-handler] maybe_resume_success"
_THREAD_ITEMS_MARKER = "[AppServerConnection] response_routed"
_THREAD_ITEMS_METHOD = "method=thread/items/list"


@dataclass(frozen=True)
class ProviderLogBinding:
    """Immutable identity of one ChatGPT process-owned provider log."""

    log_name: str
    pid: int
    app_session_id: str

    def __post_init__(self) -> None:
        if type(self.pid) is not int or isinstance(self.pid, bool) or self.pid <= 0:
            raise EvidenceError("provider_log_pid_invalid")
        match = _LOG_NAME_RE.fullmatch(str(self.log_name or ""))
        if match is None:
            raise EvidenceError("provider_log_name_invalid")
        if int(match.group("pid")) != self.pid:
            raise EvidenceError("provider_log_pid_mismatch")
        if match.group("app_session") != self.app_session_id:
            raise EvidenceError("provider_log_app_session_mismatch")
        if _UUID_RE.fullmatch(str(self.app_session_id or "")) is None:
            raise EvidenceError("provider_log_app_session_invalid")


@dataclass(frozen=True)
class NativeThreadIdentity:
    """Provider-owned identity for one bound ChatGPT conversation snapshot."""

    binding: ProviderLogBinding
    observed_at: float
    conversation_id: str
    thread_id: str
    latest_turn_id: str
    document_visibility: str
    assigned_stream_role: str
    has_latest_thread_settings: bool

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ProviderLogBinding):
            raise EvidenceError("provider_log_binding_invalid")
        for value in (self.conversation_id, self.thread_id, self.latest_turn_id):
            if _UUID_RE.fullmatch(str(value or "")) is None:
                raise EvidenceError("provider_native_identity_invalid")
        if self.conversation_id != self.thread_id:
            raise EvidenceError("provider_conversation_thread_mismatch")
        if self.document_visibility != "visible":
            raise EvidenceError("provider_thread_not_visible")
        if self.assigned_stream_role != "owner":
            raise EvidenceError("provider_thread_not_owned")
        if self.has_latest_thread_settings is not True:
            raise EvidenceError("provider_thread_settings_unqualified")
        if type(self.observed_at) not in (int, float) or self.observed_at <= 0:
            raise EvidenceError("provider_identity_time_invalid")


@dataclass(frozen=True)
class ThreadItemsObservation:
    """Content-free native evidence that a bound conversation was read by the app."""

    binding: ProviderLogBinding
    observed_at: float
    conversation_id: str

    def __post_init__(self) -> None:
        if _UUID_RE.fullmatch(str(self.conversation_id or "")) is None:
            raise EvidenceError("provider_native_identity_invalid")
        if type(self.observed_at) not in (int, float) or self.observed_at <= 0:
            raise EvidenceError("provider_identity_time_invalid")


def provider_log_binding(log_name: str, *, expected_pid: int) -> ProviderLogBinding:
    match = _LOG_NAME_RE.fullmatch(str(log_name or ""))
    if match is None:
        raise EvidenceError("provider_log_name_invalid")
    return ProviderLogBinding(
        log_name=log_name,
        pid=expected_pid,
        app_session_id=match.group("app_session"),
    )


def _timestamp(line: str) -> float:
    match = _TIMESTAMP_RE.match(line)
    if match is None:
        raise EvidenceError("provider_log_timestamp_missing")
    raw = match.group("timestamp")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise EvidenceError("provider_log_timestamp_invalid") from None
    if parsed.tzinfo is None:
        raise EvidenceError("provider_log_timestamp_invalid")
    return parsed.astimezone(timezone.utc).timestamp()


def _field(pattern: re.Pattern[str], line: str, code: str) -> str:
    match = pattern.search(line)
    if match is None:
        raise EvidenceError(code)
    return match.group("value")


def _bounded_lines(lines: Iterable[str]) -> tuple[str, ...]:
    if isinstance(lines, (str, bytes)):
        raise EvidenceError("provider_log_lines_invalid")
    result: list[str] = []
    for line in lines:
        if not isinstance(line, str):
            raise EvidenceError("provider_log_line_invalid")
        try:
            size = len(line.encode("utf-8"))
        except UnicodeError:
            raise EvidenceError("provider_log_line_invalid") from None
        if size > MAX_PROVIDER_LOG_LINE_BYTES or "\x00" in line:
            raise EvidenceError("provider_log_line_invalid")
        result.append(line.rstrip("\r\n"))
        if len(result) > MAX_PROVIDER_LOG_LINES:
            raise EvidenceError("provider_log_line_budget_exceeded")
    return tuple(result)


def parse_native_thread_identities(
    binding: ProviderLogBinding,
    lines: Iterable[str],
) -> tuple[NativeThreadIdentity, ...]:
    """Parse only closed maybe_resume_success identity events."""

    if not isinstance(binding, ProviderLogBinding):
        raise EvidenceError("provider_log_binding_invalid")
    observations: list[NativeThreadIdentity] = []
    for line in _bounded_lines(lines):
        if _RESUME_MARKER not in line:
            continue
        conversation = _field(
            _ID_FIELD_RE["conversationId"], line, "provider_conversation_id_missing"
        )
        thread = _field(_ID_FIELD_RE["threadId"], line, "provider_thread_id_missing")
        latest_turn = _field(
            _ID_FIELD_RE["latestTurnId"], line, "provider_latest_turn_id_missing"
        )
        visibility = _field(
            _FIXED_FIELD_RE["documentVisibilityState"],
            line,
            "provider_visibility_missing",
        )
        role = _field(
            _FIXED_FIELD_RE["assignedStreamRole"],
            line,
            "provider_stream_role_missing",
        )
        latest_settings = _field(
            _FIXED_FIELD_RE["hasLatestThreadSettings"],
            line,
            "provider_thread_settings_missing",
        )
        observations.append(
            NativeThreadIdentity(
                binding=binding,
                observed_at=_timestamp(line),
                conversation_id=conversation,
                thread_id=thread,
                latest_turn_id=latest_turn,
                document_visibility=visibility,
                assigned_stream_role=role,
                has_latest_thread_settings=latest_settings == "true",
            )
        )
    return tuple(observations)


def parse_thread_items_observations(
    binding: ProviderLogBinding,
    lines: Iterable[str],
) -> tuple[ThreadItemsObservation, ...]:
    """Parse content-free thread/items/list routing evidence only."""

    if not isinstance(binding, ProviderLogBinding):
        raise EvidenceError("provider_log_binding_invalid")
    observations: list[ThreadItemsObservation] = []
    for line in _bounded_lines(lines):
        if _THREAD_ITEMS_MARKER not in line or _THREAD_ITEMS_METHOD not in line:
            continue
        conversation = _field(
            _ID_FIELD_RE["conversationId"], line, "provider_conversation_id_missing"
        )
        observations.append(
            ThreadItemsObservation(
                binding=binding,
                observed_at=_timestamp(line),
                conversation_id=conversation,
            )
        )
    return tuple(observations)


def qualify_bound_thread(
    target: DesktopTarget,
    binding: ProviderLogBinding,
    lines: Iterable[str],
    *,
    not_before: float | None = None,
) -> NativeThreadIdentity:
    """Select only the Runtime-bound provider conversation, never a recent guess."""

    if not isinstance(target, DesktopTarget):
        raise EvidenceError("provider_identity_target_invalid")
    if binding.pid != target.pid:
        raise EvidenceError("provider_log_pid_mismatch")
    expected = target.intent_target.provider_session_id
    if _UUID_RE.fullmatch(str(expected or "")) is None:
        raise EvidenceError("provider_session_identity_unqualified")
    if not_before is not None and (
        type(not_before) not in (int, float)
        or isinstance(not_before, bool)
        or not_before <= 0
    ):
        raise EvidenceError("provider_identity_time_invalid")

    candidates = [
        event
        for event in parse_native_thread_identities(binding, lines)
        if event.conversation_id == expected
        and (not_before is None or event.observed_at >= not_before)
    ]
    if not candidates:
        raise EvidenceError("provider_bound_thread_not_observed")
    newest_time = max(event.observed_at for event in candidates)
    newest = [event for event in candidates if event.observed_at == newest_time]
    if len(newest) != 1:
        raise EvidenceError("provider_bound_thread_ambiguous")
    return newest[0]


def qualify_new_turn(
    target: DesktopTarget,
    binding: ProviderLogBinding,
    lines: Iterable[str],
    *,
    previous_turn_id: str,
    not_before: float,
) -> NativeThreadIdentity:
    """Require one provider-native successor turn on the same bound conversation."""

    if _UUID_RE.fullmatch(str(previous_turn_id or "")) is None:
        raise EvidenceError("provider_previous_turn_invalid")
    current = qualify_bound_thread(
        target,
        binding,
        lines,
        not_before=not_before,
    )
    if current.latest_turn_id == previous_turn_id:
        raise EvidenceError("provider_turn_not_advanced")
    return current


def bind_native_turn_evidence(
    plan: PreparedTurn,
    snapshot: DesktopSnapshot,
    identity: NativeThreadIdentity,
) -> DesktopSnapshot:
    """Join provider-native turn identity to one exact AX-observed operation turn.

    The operation marker and AX message graph select the user/assistant messages.
    The provider log supplies only the native turn identity. Neither source may
    substitute for the other, and existing conflicting native ids are refused.
    """

    if not isinstance(plan, PreparedTurn) or not isinstance(snapshot, DesktopSnapshot):
        raise EvidenceError("provider_turn_join_input_invalid")
    if not isinstance(identity, NativeThreadIdentity):
        raise EvidenceError("provider_turn_join_identity_invalid")
    if snapshot.target != plan.target:
        raise EvidenceError("provider_turn_join_target_mismatch")
    expected = plan.target.intent_target.provider_session_id
    if (
        identity.binding.pid != plan.target.pid
        or identity.conversation_id != expected
        or identity.thread_id != expected
    ):
        raise EvidenceError("provider_turn_join_session_mismatch")
    if identity.observed_at < plan.prepared_at:
        raise EvidenceError("provider_turn_join_stale_identity")

    marker = plan.wire_text.split("\n", 1)[0] + "\n"
    users = [
        message
        for message in snapshot.messages
        if message.role == "user"
        and message.message_id not in plan.before_message_ids
        and message.text.startswith(marker)
    ]
    if len(users) != 1:
        raise EvidenceError(
            "provider_turn_join_user_ambiguous" if users
            else "provider_turn_join_user_missing"
        )
    user = users[0]
    if user.text != plan.wire_text or user.complete is not True:
        raise EvidenceError("provider_turn_join_user_unverified")
    if user.native_turn_id not in (None, identity.latest_turn_id):
        raise EvidenceError("provider_turn_join_native_id_conflict")

    replies = [
        message
        for message in snapshot.messages
        if message.role == "assistant"
        and message.reply_to_user_id == user.message_id
        and message.message_id not in plan.before_message_ids
    ]
    if len(replies) > 1:
        raise EvidenceError("provider_turn_join_reply_ambiguous")
    reply = replies[0] if replies else None
    if reply is not None and reply.native_turn_id not in (
        None,
        identity.latest_turn_id,
    ):
        raise EvidenceError("provider_turn_join_native_id_conflict")

    rebound = []
    for message in snapshot.messages:
        if message.message_id == user.message_id or (
            reply is not None and message.message_id == reply.message_id
        ):
            rebound.append(
                replace(message, native_turn_id=identity.latest_turn_id)
            )
        else:
            rebound.append(message)
    return replace(snapshot, messages=tuple(rebound))


__all__ = [
    "MAX_PROVIDER_LOG_LINE_BYTES",
    "MAX_PROVIDER_LOG_LINES",
    "NativeThreadIdentity",
    "ProviderLogBinding",
    "ThreadItemsObservation",
    "bind_native_turn_evidence",
    "parse_native_thread_identities",
    "parse_thread_items_observations",
    "provider_log_binding",
    "qualify_bound_thread",
    "qualify_new_turn",
]
