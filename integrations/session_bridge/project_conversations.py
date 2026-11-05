"""Bounded, original-principal project conversations over existing Runtime.

A conversation is an actual retained native epoch/session, not a reply, target
label, browser login, or guessed thread. Only immutable owned CONTINUE records
establish membership here. Sessions with no such evidence are outside coverage.
The host authenticates each fixed READ operation independently; a context DTO,
opaque selector, catalogue row or process-local constructor is not a grant.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable

from control_plane.native_continuation import _digest
from integrations.slack_agent_dialogue.service import CONTROL_VERSION_V2
from .native_read import NativeReplyReader
from .runtime_return import RuntimeSessionReturn, _principal, _read_matches_original
from .schemas import BridgeError

CATALOGUE_SCHEMA = "mastermind.project_conversation_catalogue.v1"
READ_SCHEMA = "mastermind.project_conversation_read.v1"
_WORK = re.compile(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*")
_READ = re.compile(r"session-reply-[0-9a-f]{64}")
_HEX = re.compile(r"[0-9a-f]{64}")
_PAGE = 8
_TURNS = 4
_RESULT_LIMIT = 32768


def _refused():
    raise BridgeError("conversation_unavailable", "project conversations are unavailable")


def _work(value):
    if type(value) is not str or _WORK.fullmatch(value) is None or not 2 <= len(value[3:]) <= 64:
        _refused()
    return value


def _requests(value):
    if type(value) is not list or not 1 <= len(value) <= _TURNS:
        _refused()
    seen = set()
    for row in value:
        if (type(row) is not dict or set(row) != {"read_ref", "request_revision"}
                or type(row["read_ref"]) is not str or _READ.fullmatch(row["read_ref"]) is None
                or type(row["request_revision"]) is not str or _HEX.fullmatch(row["request_revision"]) is None
                or row["read_ref"] in seen):
            _refused()
        seen.add(row["read_ref"])
    return json.loads(json.dumps(value))


def validate_selection(value):
    if (type(value) is not dict or set(value) != {"work_ref", "conversation_ref", "revision", "requests"}
            or type(value["conversation_ref"]) is not str
            or re.fullmatch(r"conversation-[0-9a-f]{64}", value["conversation_ref"]) is None
            or type(value["revision"]) is not str or _HEX.fullmatch(value["revision"]) is None):
        _refused()
    result = dict(work_ref=_work(value["work_ref"]), conversation_ref=value["conversation_ref"],
                  revision=value["revision"], requests=_requests(value["requests"]))
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 4096:
        _refused()
    return result


def _window_revision(conversation_ref, requests):
    return _digest({"conversation_ref": conversation_ref, "requests": requests})


def _bounded(value):
    packet = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(packet) > _RESULT_LIMIT:
        _refused()
    return json.loads(packet)


class RuntimeProjectConversationsReader:
    """Nominal installed original-request owner; no SQL, discovery or writes.

    ``guard`` is supplied by the authenticated fixed operation's live host
    scope. It is never taken from public JSON. All source calls are incumbent
    bounded Runtime selections or the existing authenticated native reply read.
    """
    def __init__(self, original: RuntimeSessionReturn):
        if type(original) is not RuntimeSessionReturn:
            raise TypeError("canonical RuntimeSessionReturn required")
        self._original = original
        self._runtime = original.runtime
        self._source = (original.socket_path, original.service_call, original._trusted_read_pair)
        self._methods = tuple(getattr(getattr(original, name), "__func__", getattr(original, name)) for name in
            ("session_reply_references", "resolve_read", "_continuation_messages"))

    def _current(self, principal, identity, guard):
        methods = tuple(getattr(self._original, name).__func__ if hasattr(getattr(self._original, name), "__func__")
                        else getattr(self._original, name) for name in
                        ("session_reply_references", "resolve_read", "_continuation_messages"))
        if (not callable(guard) or guard() is not True or self._original.runtime is not self._runtime
                or (self._original.socket_path, self._original.service_call, self._original._trusted_read_pair) != self._source
                or methods != self._methods
                or _principal(principal) != identity):
            _refused()

    def _record(self, principal, identity, work_ref, read_ref, revision, guard):
        self._current(principal, identity, guard)
        with self._runtime.observe_bounded_read() as observation:
            event, value = observation.read_session_original_request_bounded(read_ref=read_ref)
        _ = observation.receipt  # Never publish facts from a failed close.
        if (value["context"]["work_ref"] != work_ref or event.command_id != "session-bridge-continue:" + read_ref[14:]
                or _digest(event.to_dict()) != revision
                or not _read_matches_original(value["principal"], identity, principal,
                    trusted_pair=self._original._trusted_read_pair)):
            _refused()
        # The actual native identity and original physical context must agree
        # across every selected turn. Process restarts do not manufacture a new
        # conversation, while a fork/new epoch remains distinct.
        material = {"work_ref": work_ref, "principal": identity, "root_job_id": value["root_job_id"],
            "job_id": value["job_id"], "session_epoch_id": value["generation"]["session_epoch_id"],
            "native_session_sha256": value["generation"]["native_session_sha256"],
            "session_ref": value["context"]["session_ref"], "carrier": value["carrier"]}
        ref = "conversation-" + _digest(material)
        self._current(principal, identity, guard)
        return event, value, ref

    def catalogue(self, principal, arguments, *, guard: Callable[[], bool]):
        try:
            if type(arguments) is not dict or set(arguments) not in ({"work_ref"}, {"work_ref", "cursor"}):
                _refused()
            work_ref = _work(arguments["work_ref"])
            cursor = arguments.get("cursor")
            if cursor is not None and (type(cursor) is not str or len(cursor) > 2048
                    or re.fullmatch(r"[A-Za-z0-9_=-]+", cursor) is None):
                _refused()
            identity = _principal(principal)
            self._current(principal, identity, guard)
            page = self._original.session_reply_references(principal=principal, work_ref=work_ref,
                cursor=cursor, page_size=_PAGE)
            grouped = {}
            for row in page["references"]:
                event, value, ref = self._record(principal, identity, work_ref,
                    row["read_ref"], row["request_revision"], guard)
                if (row["request_event_id"] != event.event_id or row["requested_at"] != event.created_at
                        or row["root_job_id"] != value["root_job_id"]):
                    _refused()
                grouped.setdefault(ref, []).append((event, value, row))
            conversations = []
            # Original page order is canonical Event order. This is request
            # recency only, not last reply, provider activity, or saved time.
            for ref, records in grouped.items():
                selected = list(reversed(records[:_TURNS]))
                requests = [{"read_ref": row["read_ref"], "request_revision": row["request_revision"]}
                            for _, _, row in selected]
                conversations.append(dict(conversation_ref=ref, revision=_window_revision(ref, requests),
                    root_job_id=records[0][1]["root_job_id"], title=None,
                    last_request_at=records[0][0].created_at, requests=requests))
            self._current(principal, identity, guard)
            return _bounded(dict(schema=CATALOGUE_SCHEMA, work_ref=work_ref, coverage="PARTIAL",
                conversations=conversations, next_cursor=page["next_cursor"], high_water=page["high_water"], can_send=False))
        except Exception:
            _refused()

    async def read(self, principal, arguments, *, guard: Callable[[], bool]):
        try:
            selected = validate_selection(arguments)
            identity = _principal(principal)
            self._current(principal, identity, guard)
            if selected["revision"] != _window_revision(selected["conversation_ref"], selected["requests"]):
                _refused()
            records = []
            for row in selected["requests"]:
                event, value, ref = self._record(principal, identity, selected["work_ref"],
                    row["read_ref"], row["request_revision"], guard)
                if ref != selected["conversation_ref"]:
                    _refused()
                records.append((event, value, row))
            if any(records[i][0].event_id >= records[i+1][0].event_id for i in range(len(records)-1)):
                _refused()
            turns = []
            async def guarded_call(path, payload):
                self._current(principal, identity, guard)
                if path != self._source[0] or payload.get("operation") != "read_thread":
                    _refused()
                result = await self._source[1](path, payload)
                self._current(principal, identity, guard)
                return result

            # A fixed READ facet reuses the genuine Runtime, original policy
            # pair and existing resolver implementation. Its IPC callback is
            # guarded around EVERY await (including resolver-internal reads),
            # rather than checking only after a multi-read reply operation.
            # No public frame supplies these bindings or this policy pairing.
            read_owner = RuntimeSessionReturn(self._runtime, fabric=self._original.fabric,
                codex=self._original.codex, socket_path=self._source[0], service_call=guarded_call)
            read_owner._trusted_read_pair = self._source[2]
            reader = NativeReplyReader(read_owner, socket_path=self._source[0],
                service_call=guarded_call, projected_principal=True)
            async with asyncio.timeout(8):
                for event, value, row in records:
                    self._current(principal, identity, guard)
                    turn = dict(**row, requested_at=event.created_at, instruction=None,
                                stop_condition=None, reply=None, state="UNAVAILABLE")
                    try:
                        reply = await reader(principal, {"read_ref": row["read_ref"]})
                        self._current(principal, identity, guard)
                        carrier = await guarded_call(self._source[0], {
                            "version": CONTROL_VERSION_V2, "operation": "read_thread",
                            "args": {"context": value["context"], "thread_ts": value["thread_ts"]}})
                        if type(carrier) is not dict or carrier.get("ok") is not True:
                            _refused()
                        _, request = self._original._continuation_messages(value, carrier["result"])
                        turn.update(instruction=request["body"]["instruction"],
                            stop_condition=request["body"]["stop_condition"], state="AVAILABLE",
                            reply={key: reply[key] for key in ("text", "next_step", "read_ref",
                                "message_key", "fingerprint", "parent_consumed")})
                    except BridgeError:
                        # Missing/uncommitted/stale native replies remain a gap;
                        # no raw neighboring thread content or fallback body.
                        pass
                    self._current(principal, identity, guard)
                    after, current, ref = self._record(principal, identity, selected["work_ref"],
                        row["read_ref"], row["request_revision"], guard)
                    if after.to_dict() != event.to_dict() or current != value or ref != selected["conversation_ref"]:
                        _refused()
                    turns.append(turn)
            self._current(principal, identity, guard)
            return _bounded(dict(schema=READ_SCHEMA, work_ref=selected["work_ref"],
                conversation_ref=selected["conversation_ref"], revision=selected["revision"],
                root_job_id=records[0][1]["root_job_id"], title=None, coverage="PARTIAL", can_send=False, turns=turns))
        except Exception:
            _refused()


__all__ = ["RuntimeProjectConversationsReader", "validate_selection"]
