"""T3 original-run return linkage in the incumbent Executive Runtime event store.

T3 remains the transcript/run owner. This extension stores only account-bound
references and observed-response digests, not messages, credentials, callbacks,
worker lifecycle, or another queue. It launches nothing and never polls. A host
must inject its current authorization and an existing authorized native client;
an account name or caller-provided profile is not an Executive principal.

The existing reply subscription/signature/delivery owners consume these records.
Native-change observation is an explicit producer edge, never a READ side effect.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from control_plane.executive_runtime import Runtime
from control_plane.principal_projection import NeutralPrincipalProjection
from .t3_native_client import Scope, Thread, Run, T3NativeClient, Conflict, Unavailable
from .t3_dot_tools import _public
from .web_reply_event_rpc import _validated_principal
from .web_reply_events import EVENT_NAME
from .web_reply_subscription_owner import OriginalReplyGrant, owner_key

REQUEST_PREFIX = "t3-request-"
READ_PREFIX = "t3-reply-"
RETURN_PREFIX = "t3-return-"
REQUEST_SCHEMA = "mastermind.t3_original_return_binding.v1"
READ_SCHEMA = "mastermind.t3_original_reply_read.v1"
_OBSERVATION_SCHEMA = "mastermind.t3_original_reply_observation.v1"
_BINDING_EVENT = "T3_ORIGINAL_RETURN_BOUND"
_RETURN_EVENT = "T3_ORIGINAL_REPLY_OBSERVED"
_AGGREGATE = "native_session_return"
_ACTOR = "t3_original_return_owner"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,255}\Z")
_PAYLOAD = {"schema", "owner_key", "request_ref", "read_ref", "run", "created_at", "expires_at"}
_OBSERVATION = {"schema", "request_ref", "read_ref", "owner_key", "answer_sha256", "status", "observed_at", "message_key"}
_PUBLIC = {"schema", "request_ref", "read_ref", "environment_id", "project_id", "thread_id", "run_id",
           "status", "answer", "answer_sha256", "redacted", "reply_committed", "parent_consumed"}


class T3ReturnEffectUnknown(RuntimeError):
    """The original Runtime write may exist; reconcile, never launch/replay."""
    def __init__(self, operation, request_ref, read_ref):
        super().__init__("Original T3 return persistence requires reconciliation")
        self.operation, self.request_ref, self.read_ref = operation, request_ref, read_ref
        self.retry_allowed = False


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("ascii")).hexdigest()


def _run(value: Any) -> Run:
    if type(value) is not dict or set(value) != {"thread", "run_id", "request_id", "delivery", "message_id"}:
        raise ValueError("Closed original native run required")
    thread = value["thread"]
    if type(thread) is not dict or set(thread) != {"scope", "thread_id"}:
        raise ValueError("Closed original native thread required")
    scope = thread["scope"]
    if type(scope) is not dict or set(scope) != {field.name for field in dataclasses.fields(Scope)}:
        raise ValueError("Closed original native scope required")
    return Run(Thread(Scope(**scope), thread["thread_id"]), value["run_id"], value["request_id"],
               value["delivery"], value["message_id"])


def _identity(key: str, run: Run) -> str:
    # Original run, not caller title, newest thread turn, or mutable chat summary.
    return _hash({"owner_key": key, "scope": dataclasses.asdict(run.thread.scope),
                  "thread_id": run.thread.thread_id, "run_id": run.run_id})


def is_t3_read_ref(value: Any) -> bool:
    return type(value) is str and value.startswith(READ_PREFIX) and bool(_SHA.fullmatch(value[len(READ_PREFIX):]))


def is_t3_request_ref(value: Any) -> bool:
    return type(value) is str and value.startswith(REQUEST_PREFIX) and bool(_SHA.fullmatch(value[len(REQUEST_PREFIX):]))


def stored_t3_request(runtime: Runtime, read_ref: str):
    """Exact persisted-source validation; no native observation or access grant."""
    if type(runtime) is not Runtime or not is_t3_read_ref(read_ref):
        raise ValueError("Canonical T3 read reference required")
    request_ref = REQUEST_PREFIX + read_ref[len(READ_PREFIX):]
    event = runtime.events.get_event_by_command_id(request_ref)
    if event is None or event.event_type != _BINDING_EVENT:
        raise ValueError("Original T3 binding unavailable")
    value = event.payload
    if (type(value) is not dict or set(value) != _PAYLOAD or value["schema"] != REQUEST_SCHEMA
            or value["request_ref"] != request_ref or value["read_ref"] != read_ref
            or type(value["owner_key"]) is not str or not _SHA.fullmatch(value["owner_key"])
            or type(value["created_at"]) is not int or type(value["expires_at"]) is not int
            or not 0 < value["created_at"] < value["expires_at"] <= value["created_at"] + 86400):
        raise ValueError("Original T3 binding malformed")
    run = _run(value["run"])
    if _identity(value["owner_key"], run) != read_ref[len(READ_PREFIX):]:
        raise ValueError("Original T3 binding identity changed")
    if event.aggregate_type != _AGGREGATE or event.aggregate_id != request_ref or event.actor != _ACTOR:
        raise ValueError("Original T3 binding provenance changed")
    return event, value


def stored_original_reply_request(runtime: Runtime, read_ref: str):
    """Source dispatch for the existing encrypted authorization owner.

    T3 has its own closed namespace and provenance. It cannot impersonate a
    Codex/Claude Agent Dialogue request; that original validator remains intact.
    """
    if is_t3_read_ref(read_ref):
        return stored_t3_request(runtime, read_ref)
    from control_plane.native_continuation import stored_continuation_request
    return stored_continuation_request(runtime, read_ref)


def validate_t3_public_reply(value: Any) -> dict:
    if (type(value) is not dict or set(value) != _PUBLIC or value["schema"] != READ_SCHEMA
            or not is_t3_request_ref(value["request_ref"]) or not is_t3_read_ref(value["read_ref"])
            or value["request_ref"][len(REQUEST_PREFIX):] != value["read_ref"][len(READ_PREFIX):]
            or value["reply_committed"] is not True or value["parent_consumed"] is not False
            or type(value["redacted"]) is not bool or type(value["answer"]) is not str
            or type(value["answer_sha256"]) is not str or not _SHA.fullmatch(value["answer_sha256"])
            or value["status"] not in {"completed", "failed", "interrupted"}):
        raise ValueError("Original T3 reply is unqualified")
    for field in ("environment_id", "project_id", "thread_id", "run_id"):
        if type(value[field]) is not str or not _ID.fullmatch(value[field]):
            raise ValueError("Original T3 reply identity is invalid")
    if len(_json(value).encode()) > 256 * 1024:
        raise ValueError("Original T3 reply exceeds public bound")
    return json.loads(_json(value))


class T3OriginalReplySource:
    """One provider extension to existing Runtime return/event owners.

    native_client(principal, scope) must resolve through the incumbent native
    access owner and enforce exact account/project permission. current(principal)
    is the existing current-token OR retained-policy owner, never a dict parser.
    Constructor injection alone does not enroll this source in production.
    """
    def __init__(self, runtime: Runtime, native_client: Callable, *, current: Callable,
                 clock: Callable[[], int], enabled: bool = False):
        if (type(runtime) is not Runtime or not callable(native_client) or not callable(current)
                or not callable(clock) or type(enabled) is not bool):
            raise TypeError("Existing Runtime, native access and current authorization owners required")
        self.runtime, self.native_client, self.current, self.clock, self.enabled = runtime, native_client, current, clock, enabled

    def _admit(self, principal):
        if not self.enabled:
            raise Unavailable("T3 original replies are not enrolled")
        value = self.current(principal)
        now = self.clock()
        if type(value) is not NeutralPrincipalProjection or not _validated_principal(value, now):
            raise Unavailable("Current original reply principal required")
        return value, owner_key(value), now

    async def _client(self, principal, run: Run):
        client = await self.native_client(principal, run.thread.scope)
        if type(client) is not T3NativeClient or client.scope != run.thread.scope:
            raise Conflict("Original T3 connection/environment/project changed")
        return client

    def _binding(self, principal, request_ref: str):
        projection, key, now = self._admit(principal)
        if not is_t3_request_ref(request_ref):
            raise Unavailable("Original T3 request unavailable")
        event, value = stored_t3_request(self.runtime, READ_PREFIX + request_ref[len(REQUEST_PREFIX):])
        if key != value["owner_key"] or now >= value["expires_at"]:
            raise Unavailable("Original T3 request unavailable")
        return projection, event, value, _run(value["run"])

    async def bind(self, principal, run: Run, *, ttl_seconds: int = 3600) -> dict:
        """Persist a return link AFTER native evidence, never launch or admit work.

        The existing launcher may call this after a successful native receipt.
        An interrupted bind must be reconciled by its deterministic original
        request reference, not by launching the task again.
        """
        projection, key, now = self._admit(principal)
        if type(run) is not Run or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 86400:
            raise ValueError("Bounded exact native run required")
        client = await self._client(projection, run)
        # An exact-run native read must observe the original run before linking.
        await client.wait(run, timeout_ms=1)
        again, again_key, after = self._admit(principal)
        if again_key != key:
            raise Conflict("Original authenticated account changed")
        ident = _identity(key, run)
        request_ref, read_ref = REQUEST_PREFIX + ident, READ_PREFIX + ident
        value = {"schema": REQUEST_SCHEMA, "owner_key": key, "request_ref": request_ref,
                 "read_ref": read_ref, "run": dataclasses.asdict(run), "created_at": after,
                 "expires_at": after + ttl_seconds}
        await self._client(again, run)  # Recheck the incumbent native access grant.
        attempted = False
        try:
            with self.runtime.store.transaction() as connection:
                prior = self.runtime.store.get_event_by_command_id(request_ref, connection=connection)
                if prior is None:
                    attempted = True
                    self.runtime.store.append_event(connection, aggregate_type=_AGGREGATE, aggregate_id=request_ref,
                        event_type=_BINDING_EVENT, actor=_ACTOR, command_id=request_ref, payload=value)
                else:
                    previous = prior.payload
                    if (previous.get("run") != value["run"] or previous.get("owner_key") != key
                            or type(previous.get("expires_at")) is not int or after >= previous["expires_at"]):
                        raise Conflict("Original T3 binding differs or expired")
            event, retained = stored_t3_request(self.runtime, read_ref)
            self._admit(principal)
        except (Exception, asyncio.CancelledError):
            if attempted:
                raise T3ReturnEffectUnknown("bind", request_ref, read_ref) from None
            raise
        return {"request_ref": request_ref, "read_ref": read_ref, "expires_at": retained["expires_at"],
                "request_event_sha256": _hash(event.to_dict()), "native_execution": "NOT_CREATED",
                "subscription": "NOT_CREATED", "parent_consumed": False}

    async def resolve(self, principal, request_ref: str) -> OriginalReplyGrant:
        projection, event, value, run = self._binding(principal, request_ref)
        client = await self._client(projection, run)
        await client.wait(run, timeout_ms=1)
        after, current_event, current_value, _ = self._binding(principal, request_ref)
        if current_event.to_dict() != event.to_dict():
            raise Conflict("Original T3 source changed during authorization")
        return OriginalReplyGrant(owner_key=owner_key(after), request_ref=request_ref,
            read_ref=value["read_ref"], revision=_hash(event.to_dict()), access_current=True,
            expires_at=value["expires_at"])

    async def _answer(self, principal, request_ref: str):
        projection, event, value, run = self._binding(principal, request_ref)
        client = await self._client(projection, run)
        result = await client.original_result(run, max_pages=5)
        if result.run != run or result.complete is not True or type(result.answer) is not str:
            # Nonterminal/partial, permission requests and failed-no-reply are NOT
            # forged reply-committed events. Explicit status/question tools remain.
            raise Unavailable("Original native response is not completely retained")
        if result.status not in {"completed", "failed", "interrupted"}:
            raise Unavailable("Original native response has unqualified terminal state")
        projection, current_event, _, _ = self._binding(principal, request_ref)
        if current_event.to_dict() != event.to_dict():
            raise Conflict("Original source changed during native read")
        await self._client(projection, run)
        return event, value, run, result

    async def observe(self, principal, request_ref: str) -> dict:
        """Native-event producer edge; persist a digest, not the native answer.

        The installed native event listener calls this for an exact subscribed
        original request. No loop, native worker launch, callback or retry occurs.
        Runtime's incumbent commit consumer owns subsequent external delivery.
        """
        _, binding, run, result = await self._answer(principal, request_ref)
        digest = hashlib.sha256(result.answer.encode("utf-8")).hexdigest()
        semantic = {"request_ref": request_ref, "answer_sha256": digest, "status": result.status}
        identity = _hash(semantic)
        command_id = RETURN_PREFIX + identity
        value = {"schema": _OBSERVATION_SCHEMA, "request_ref": request_ref,
                 "read_ref": binding["read_ref"], "owner_key": binding["owner_key"],
                 "answer_sha256": digest, "status": result.status, "observed_at": self.clock(),
                 "message_key": "t3-native-reply-" + identity}
        self._binding(principal, request_ref)
        attempted = False
        try:
            with self.runtime.store.transaction() as connection:
                prior = self.runtime.store.get_event_by_command_id(command_id, connection=connection)
                if prior is None:
                    attempted = True
                    self.runtime.store.append_event(connection, aggregate_type=_AGGREGATE,
                        aggregate_id=request_ref, event_type=_RETURN_EVENT, actor=_ACTOR,
                        command_id=command_id, payload=value)
            observed = self.runtime.events.get_event_by_command_id(command_id)
            if observed is None:
                raise Unavailable("Original T3 reply commit is unobserved")
            self._validate_observation(observed, binding, digest, result.status)
            self._binding(principal, request_ref)
        except (Exception, asyncio.CancelledError):
            if attempted:
                raise T3ReturnEffectUnknown("observe", request_ref, binding["read_ref"]) from None
            raise
        return {"request_ref": request_ref, "read_ref": binding["read_ref"],
                "event_command_id": command_id, "reply_committed": True,
                "delivered": False, "parent_consumed": False}

    @staticmethod
    def _validate_observation(event, binding, digest, status):
        value = event.payload
        identity = _hash({"request_ref": binding["request_ref"], "answer_sha256": digest, "status": status})
        if (event.event_type != _RETURN_EVENT or event.aggregate_type != _AGGREGATE
                or event.aggregate_id != binding["request_ref"] or event.actor != _ACTOR
                or event.command_id != RETURN_PREFIX + identity or type(value) is not dict
                or set(value) != _OBSERVATION or value["schema"] != _OBSERVATION_SCHEMA
                or value["request_ref"] != binding["request_ref"] or value["read_ref"] != binding["read_ref"]
                or value["owner_key"] != binding["owner_key"] or value["answer_sha256"] != digest
                or value["status"] != status or value["message_key"] != "t3-native-reply-" + identity
                or type(value["observed_at"]) is not int
                or not binding["created_at"] <= value["observed_at"] < binding["expires_at"]):
            raise Conflict("Original T3 observed reply provenance changed")
        return value

    async def _committed_answer(self, principal, request_ref):
        _, binding, run, result = await self._answer(principal, request_ref)
        digest = hashlib.sha256(result.answer.encode("utf-8")).hexdigest()
        identity = _hash({"request_ref": request_ref, "answer_sha256": digest, "status": result.status})
        event = self.runtime.events.get_event_by_command_id(RETURN_PREFIX + identity)
        if event is None:
            raise Unavailable("Native response is not committed by the original producer")
        observation = self._validate_observation(event, binding, digest, result.status)
        self._binding(principal, request_ref)
        return binding, run, result, observation

    async def project(self, principal, request_ref):
        """Pure read projection for the incumbent signed delivery owner."""
        from .runtime_reply_delivery import ResolvedReplyEvent
        binding, _, _, observation = await self._committed_answer(principal, request_ref)
        identity = observation["message_key"][len("t3-native-reply-"):]
        event = {"eventId": "evt-" + identity, "name": EVENT_NAME,
            "timestamp": datetime.fromtimestamp(observation["observed_at"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cursor": None,
            "data": {"request_ref": request_ref, "message_key": observation["message_key"],
                "in_reply_to": request_ref, "summary": "The original T3 response is available. Read its canonical result before acting.",
                "read_ref": binding["read_ref"], "reply_committed": True, "parent_consumed": False}}
        return ResolvedReplyEvent(event, binding["read_ref"], binding["owner_key"])

    async def read(self, principal, arguments: dict) -> dict:
        if type(arguments) is not dict or set(arguments) != {"read_ref"} or not is_t3_read_ref(arguments["read_ref"]):
            raise Unavailable("Exact T3 original read reference required")
        request_ref = REQUEST_PREFIX + arguments["read_ref"][len(READ_PREFIX):]
        binding, run, result, observation = await self._committed_answer(principal, request_ref)
        answer, redacted = _public(result.answer)
        return validate_t3_public_reply({"schema": READ_SCHEMA, "request_ref": request_ref,
            "read_ref": binding["read_ref"], "environment_id": run.thread.scope.environment_id,
            "project_id": run.thread.scope.project_id, "thread_id": run.thread.thread_id, "run_id": run.run_id,
            "status": result.status, "answer": answer, "answer_sha256": observation["answer_sha256"],
            "redacted": redacted, "reply_committed": True, "parent_consumed": False})
