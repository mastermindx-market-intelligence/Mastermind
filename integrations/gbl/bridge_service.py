"""GBL bridge core + loopback socket service (lane GBL-2, BUILD_PLAN).

Two concerns, one module:

* :class:`GblBridge` — the ask-record core.  Its ONLY store is Paperclip
  issues/comments, reached through the injected :class:`GblAskStore`
  interface (GBL-4 implements it over the real Paperclip client; tests use
  a fake with the same interface).  All contract law — the id mint,
  idempotency/duplicate classification, expiry, state monotonicity, budget
  ceilings, the closed-key wake body — is IMPORTED from
  ``common/gbl_contract.py`` (GBL-1) and never restated here.
* :class:`BridgeServer` — the loopback door: an AF_UNIX stream socket that
  admits callers by KERNEL PEER UID only (the Slack-relay service pattern,
  FACTS B14), never by TCP, a header or a source address.  Identity is read
  from the socket before any payload byte is read.

EFFECT_UNKNOWN law (ARCHITECTURE §6, BUILD_PLAN tests): an issue-create
whose effect is unknown is reconciled by reading the deterministic ask id
back — NEVER by a second create.  A redelivered nudge is an ASK_NOT_FOUND
no-op: job creation exists solely behind :meth:`GblBridge.submit_ask` with
its own dedupe.

No transport toward Grok lives here: the nudge hop is
``integrations/gbl/nudge.py`` (wrapping the existing wake fabric), and the
thread send is ``integrations/gbl/message_send.py``.
"""
from __future__ import annotations

import contextlib
import ctypes
import dataclasses
import os
import socket
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from common.gbl_contract import (
    ANSWER_ARGUMENT_KEYS,
    ASK_KINDS,
    DEFAULT_ALLOWLIST,
    GBLContractError,
    MAX_ASKS_PER_HOUR_PER_PRINCIPAL,
    MAX_RENUDGES_PER_ASK,
    advance_ask_state,
    admit_ask_rate,
    build_ask,
    build_wake,
    classify_ask_duplicate,
    decode_gbl_frame,
    encode_gbl_frame,
    is_expired,
    mint_message_id,
    surface_ask_state,
    validate_ask,
    validate_wake,
)
from common.company_consultation_host_contract import HostFrameError
from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeDispatchError,
    WakeEffectUnknownError,
    WakePreSubmitError,
)

# Lane-chosen default (not doc-pinned): one re-nudge per ask per 15-minute
# cooldown, bounded by MAX_RENUDGES_PER_ASK (ARCHITECTURE flow 1 step 10).
RENUDGE_COOLDOWN_SECONDS = 900
# GBL-RETURN outcome 2: the bounded lost-wake recovery scan (the board wake
# is the primary; this read is the capped, read-only backstop).
RETURN_SCAN_MAX = 25

REQUEST_SCHEMA = "mastermind.gbl.request.v1"
RESPONSE_SCHEMA = "mastermind.gbl.response.v1"
OPS = frozenset({"ask", "answer", "result", "question", "status", "reconcile",
                 "return", "return_scan"})


class GblBridgeError(ValueError):
    """Closed typed bridge failure; `code` names the rule."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class GblCreateEffectUnknown(Exception):
    """The store's create call began but its effect is unknown (e.g. a
    transport timeout).  The caller MUST reconcile by read-back of the
    deterministic ask id and must never issue a second create."""


# ── The Paperclip store interface (GBL-4 implements; documented in the note) ─
#
# Record shape returned by read_ask: the validated ask-envelope fields plus
# one extra key "events" — a list of event dicts in append order:
#   {"type": "answer", "answer_id", "idempotency_key", "text"}
#   {"type": "state",  "state"}
#   {"type": "nudge",  "state", "at"}          # at = UTC ISO-8601
#
# Repair-round contract (panel A M6, panel B M1/M2 — exact semantics in
# integrations/mmos/gbl/GBL_REPAIR1_NOTES.md):
#
# * create_ask is CREATE-IF-ABSENT: it returns None when it created the
#   record and the EXISTING record when the deterministic ask id is already
#   present.  Two racing creates can never produce two records.
# * every append_ask_event the STORE performs stamps the event with a
#   per-record strictly-increasing integer "seq" and "trusted": True.  An
#   event whose author is NOT the store (a foreign comment carrying the
#   event marker) is surfaced with "trusted": False — the bridge never
#   treats it as authoritative.
# * legacy events that carry no "trusted" key at all are the store's own
#   pre-contract appends and stay authoritative (ordered by list position).


@runtime_checkable
class GblAskStore(Protocol):
    def create_ask(self, ask: Mapping[str, Any]) -> Mapping[str, Any] | None: ...
    def read_ask(self, ask_id: str) -> Mapping[str, Any] | None: ...
    def append_ask_event(self, ask_id: str, event: Mapping[str, Any]) -> None: ...
    def count_asks(self, principal: str, since_iso: str) -> int: ...


@runtime_checkable
class GblResultDeliveryLockStore(Protocol):
    """OPTIONAL capability of a :class:`GblAskStore`: ONE host-wide lock
    under which a result-delivery decision (read → replay → mark) is
    serialised, the same lock every append takes, plus the host's own
    delivery record that cannot lag its writes.

    GBL-5 micro 3, RULING 19(a): a delivery mark is permanent, so two
    callers must never both observe ANSWERED.

    GBL-5 micro 4: the lock alone is not enough — the record read behind
    it is the issue's comment listing, which can lag a write that has
    already landed.  The store therefore also keeps a delivery record in
    its append ledger (ask id + answer id, written before the CONSUMED
    post, read under the same flock), and ``fetch_result`` consults it
    FIRST.  It is one capability: a store that offers the lock must offer
    both methods.  The Paperclip client does; test doubles are explicitly
    marked (``GBL_TEST_DOUBLE``) and keep the plain read."""

    def result_delivery_lock(self): ...

    def delivered_answer_id(self, ask_id: str) -> str | None: ...

    def record_delivery(self, ask_id: str, answer_id: str) -> None: ...


@runtime_checkable
class GblDelegateDispatchStore(Protocol):
    """OPTIONAL capability of a :class:`GblAskStore` (GBL-RETURN): the
    delegate dispatch/return arm.  A delegate ask is handed to the target
    teammate THROUGH THE BOARD — one child issue of the ask record in the
    RF carrier's installed shape, assigned to the teammate's agent id
    resolved from the spec's target table ON THE SERVER (never from the
    caller) — and the answer is taken from the bridge's OWN board read of
    that child (the carrier's result-comment law), never from waker-
    supplied text.  ``scan_delegate_asks`` is the bounded lost-wake
    recovery read.  It is one capability: a store that offers any of it
    must offer all of it; the Paperclip client does, test doubles are
    explicitly marked (``GBL_TEST_DOUBLE``) and keep the pre-GBL-RETURN
    shapes exactly."""

    def resolve_target_agent(self, target: str) -> str: ...

    def dispatch_delegate(self, ask: Mapping[str, Any]) -> dict[str, Any]: ...

    def read_dispatch_child(self, ask_id: str,
                            child_issue_id: str) -> dict[str, Any]: ...

    def read_child_result(self, ask_id: str,
                          child_issue_id: str) -> dict[str, Any]: ...

    def scan_delegate_asks(self) -> list[str]: ...


# ── Admission (RULING §3/§5: the table is the boundary; v1 ships EMPTY) ─────


@dataclasses.dataclass(frozen=True)
class PrincipalAdmission:
    """One admitted OAuth principal (a Grok account label) with its own
    target set, kind set and hourly ceiling.  The bridge ships with an
    EMPTY table: every principal is refused until the principal (the
    Chairman's act) adds a row."""

    principal: str
    targets: frozenset[str]
    kinds: frozenset[str]
    max_asks_per_hour: int

    def __post_init__(self) -> None:
        if not isinstance(self.principal, str) or not self.principal:
            raise ValueError("admission requires a principal label")
        for name, value in (("targets", self.targets), ("kinds", self.kinds)):
            if not isinstance(value, frozenset) or not value:
                raise ValueError(f"admission {name} must be a non-empty frozenset")
        if not self.kinds <= ASK_KINDS:
            raise ValueError("admission kinds must be a subset of the v1 kinds")
        if any(not isinstance(item, str) or not item for item in self.targets):
            raise ValueError("admission targets must be non-empty strings")
        if (type(self.max_asks_per_hour) is not int
                or not 1 <= self.max_asks_per_hour <= MAX_ASKS_PER_HOUR_PER_PRINCIPAL):
            raise ValueError("admission ceiling exceeds the contract maximum")


DEFAULT_ADMISSION_TABLE: tuple[PrincipalAdmission, ...] = ()


def _record_envelope(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "events"}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ── The bridge core ─────────────────────────────────────────────────────────


class GblBridge:
    """Ask records over Paperclip, admission, idempotency, honest expiry."""

    def __init__(
        self,
        store: GblAskStore,
        *,
        admission_table: tuple[PrincipalAdmission, ...] = DEFAULT_ADMISSION_TABLE,
        nudge_sender: Any = None,
        routine_handle_resolver: Callable[[str], str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._table = tuple(admission_table)
        self._nudge_sender = nudge_sender
        self._resolve_handle = routine_handle_resolver
        self._now = now or (lambda: datetime.now(timezone.utc))

    # -- helpers ------------------------------------------------------------

    def _admission_row(self, principal: str) -> PrincipalAdmission:
        for row in self._table:
            if row.principal == principal:
                return row
        raise GblBridgeError("PRINCIPAL_NOT_ALLOWED", principal or "")

    def _require_ask(self, ask_id: str) -> dict[str, Any]:
        record = self._store.read_ask(ask_id)
        if record is None:
            raise GblBridgeError("ASK_NOT_FOUND", ask_id)
        return dict(record)

    @staticmethod
    def _require_party(record: Mapping[str, Any], principal: str) -> None:
        """M4: both parties of the ask may read the question and act on the
        answer — the creator (record principal) AND the addressee (target).
        Everyone else is refused."""
        if principal not in (record.get("principal"), record.get("target")):
            raise GblBridgeError("ASK_NOT_FOR_PRINCIPAL", principal or "")

    @staticmethod
    def _ordered_events(record: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The authoritative event list: untrusted (foreign-author) events
        are dropped; the store's own stamps must form a strictly increasing
        sequence (panel B M1/M2 — a broken stamp may never silently reorder
        the chain).  Round 2: the ``trusted`` stamp must be an exact bool —
        a truthy 1, a ``"true"`` string or a null is a typed
        EVENT_TRUST_INVALID, never an authoritative event that slips past
        the seq law because ``is True``/``is False`` both miss it.

        GBL-5 A3 + R2, RULING 19(a) (deputy round 2, H2/MED-1): a duplicate
        number is demoted per event ONLY when the later holder is not a
        STATE event — a delivery mark is never demoted, ignored or
        re-derived away by position, so a state event re-issuing a taken
        number refuses typed EVENT_ORDER_AMBIGUOUS and NOTHING is
        delivered.  A trusted seq strictly LOWER than an earlier trusted
        one is a chain anomaly (a delayed or torn append), not a
        duplicate: it refuses the same way instead of vanishing.  A
        trusted event WITHOUT an integer seq keeps its typed
        EVENT_SEQ_INVALID refusal: that is a malformed stamp, not a
        duplicate number."""
        events = list(record.get("events", ()))
        last_seq: int | None = None
        for event in events:
            if "trusted" in event and type(event["trusted"]) is not bool:
                raise GblBridgeError(
                    "EVENT_TRUST_INVALID",
                    f"trusted stamp must be a bool, got "
                    f"{type(event['trusted']).__name__}")
            if event.get("trusted") is False:
                continue                       # foreign author: never authoritative
            if event.get("trusted") is True:
                seq = event.get("seq")
                if type(seq) is not int:
                    raise GblBridgeError("EVENT_SEQ_INVALID",
                                         "trusted event without an integer seq")
                if last_seq is not None and seq == last_seq:
                    if event.get("type") == "state":
                        raise GblBridgeError(
                            "EVENT_ORDER_AMBIGUOUS",
                            f"a state event re-issues trusted seq {seq}; "
                            f"whether the result was delivered is unclear "
                            f"— nothing is delivered")
                    event["trusted"] = False   # non-state duplicate: demote,
                    event["defect"] = "EVENT_SEQ_DUPLICATE"   # never refuse
                    continue
                if last_seq is not None and seq < last_seq:
                    raise GblBridgeError(
                        "EVENT_ORDER_AMBIGUOUS",
                        f"trusted seq {seq} follows trusted seq {last_seq}; "
                        f"the chain order is unclear — nothing is delivered")
                last_seq = seq
        return [event for event in events if event.get("trusted") is not False]

    @classmethod
    def _replay_state(cls, record: Mapping[str, Any]) -> str:
        """Replay the record's authoritative events through the contract
        chain.  Historical events were lawful when appended; expiry is
        enforced at operation time, not on replay.  Repair H2/panel B H1:
        a trusted answer event IS the answered state — a record whose
        ANSWERED state event was lost (the legacy two-append write) is
        repaired by inference, never stranded behind a false OPEN."""
        state = record["state"]
        answered = False
        for event in cls._ordered_events(record):
            if event.get("type") == "state":
                state = advance_ask_state(state, event["state"])
            elif event.get("type") == "answer":
                answered = True
        if answered and state in ("OPEN", "QUESTION_AVAILABLE"):
            state = advance_ask_state(state, "ANSWERED")
        return state

    @classmethod
    def _last_answer(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        answers = [event for event in cls._ordered_events(record)
                   if event.get("type") == "answer"]
        return answers[-1] if answers else {}

    # -- operations ----------------------------------------------------------

    def submit_ask(self, *, principal: str, kind: str, target: str, title: str,
                   body: str, idempotency_key: str,
                   correlation: Mapping[str, Any] | None = None,
                   asker: Mapping[str, Any] | None = None) -> dict[str, Any]:
        row = self._admission_row(principal)
        if kind not in row.kinds:
            raise GblBridgeError("KIND_NOT_ALLOWED", kind)
        if target not in row.targets:
            raise GblBridgeError("TARGET_NOT_ALLOWED", target)
        if kind == "delegate":
            # GBL-RETURN outcome 1: the target resolves against the
            # server-side target table BEFORE any record exists — a
            # delegate ask that could never dispatch must not create an
            # orphan record (typed TARGET_AGENT_NOT_CONFIGURED propagates).
            self._require_dispatch_target(target)
        envelope = build_ask(kind=kind, principal=principal, target=target,
                             title=title, body=body,
                             idempotency_key=idempotency_key,
                             correlation=dict(correlation or {}),
                             asker=dict(asker) if asker else None,
                             now=self._now())
        ask_id = envelope["ask_id"]
        # M2: the idempotency read comes BEFORE the rate gate — a replay of
        # an ask that already exists is IDEMPOTENT, never RATE_LIMITED.
        existing = self._store.read_ask(ask_id)
        if existing is not None:
            return self._classify_existing(existing, envelope)
        now = self._now()
        since = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        asks_last_hour = self._store.count_asks(principal, since)
        admit_ask_rate(asks_last_hour)          # the contract-global ceiling
        if asks_last_hour + 1 > row.max_asks_per_hour:
            raise GblBridgeError("RATE_LIMITED",
                                 f"ceiling {row.max_asks_per_hour}/hour")
        try:
            # M6: create-if-absent — the STORE decides uniqueness, so a
            # lagging read can never produce a second record.
            landed = self._store.create_ask(envelope)
        except GblCreateEffectUnknown:
            # EFFECT_UNKNOWN law: reconcile by read-back of the deterministic
            # ask id; never a second create.
            landed = self._store.read_ask(ask_id)
            if landed is None:
                raise GblBridgeError(
                    "EFFECT_UNKNOWN",
                    "issue create effect unknown; reconcile by ask-id "
                    "read-back") from None
        if landed is not None:
            return self._classify_existing(landed, envelope)
        result: dict[str, Any] = {"status": "CREATED", "ask": dict(envelope)}
        if kind == "delegate":
            # GBL-RETURN outcome 1: DELEGATE OUT — the child issue exists
            # (create-or-reuse) before the caller is told CREATED.  A test
            # double without the capability keeps the pre-GBL-RETURN shape
            # exactly (no "dispatch" key); a production store without it
            # refused typed back in _require_dispatch_target.
            store = self._dispatch_store()
            if store is not None:
                result["dispatch"] = self._ensure_dispatched(
                    dict(envelope), store)
        elif kind == "question":
            # GBL-RETURN outcome 3: a CREATED question ask fires exactly
            # one QUESTION_AVAILABLE nudge from SHIPPED code, under the
            # same budget/cooldown/unknown-effect law as ANSWERED.  A
            # nudge failure is REPORTED, never fatal — the record exists
            # and return_scan/reconcile recover; the ask is never lost
            # because attention failed.
            try:
                result["question_nudge"] = self._nudge_question_once(ask_id)
            except GblBridgeError as exc:
                result["question_nudge"] = {"status": exc.code,
                                            "ask_id": ask_id}
        return result

    def _classify_existing(self, existing: Mapping[str, Any],
                           envelope: Mapping[str, Any]) -> dict[str, Any]:
        verdict = classify_ask_duplicate(_record_envelope(existing), envelope)
        if verdict.value == "IDEMPOTENT":
            result: dict[str, Any] = {"status": "IDEMPOTENT",
                                      "ask": dict(existing)}
            if existing.get("kind") == "delegate":
                # GBL-RETURN outcome 5: a replayed delegate ask is also a
                # dispatch-recovery edge — ensure (never re-create) the
                # child, so a lost wake or a lost dispatch event heals on
                # the next submit.
                store = self._dispatch_store()
                if store is not None:
                    result["dispatch"] = self._ensure_dispatched(existing,
                                                                 store)
            return result
        raise GblBridgeError("CONFLICT",
                             f"key {envelope['idempotency_key']} reused "
                             "with new content")

    def fetch_question(self, *, principal: str, ask_id: str) -> dict[str, Any]:
        record = self._require_ask(ask_id)
        self._require_party(record, principal)
        if is_expired(record, self._now()):
            raise GblBridgeError("EXPIRED", ask_id)
        return {"ask_id": ask_id, "kind": record["kind"],
                "question": record["body"], "expires_at": record["expires_at"]}

    def post_answer(self, *, principal: str, ask_id: str, answer: str,
                    idempotency_key: str) -> dict[str, Any]:
        record = self._require_ask(ask_id)
        self._require_party(record, principal)
        now = self._now()
        if is_expired(record, now):
            raise GblBridgeError("EXPIRED", ask_id)
        for event in self._ordered_events(record):
            if event.get("type") != "answer":
                continue
            if event.get("idempotency_key") == idempotency_key:
                if event.get("text") == answer:
                    return {"status": "IDEMPOTENT",
                            "answer_id": event["answer_id"]}
                raise GblBridgeError("CONFLICT",
                                     "answer key reused with new text")
        if self._last_answer(record):
            raise GblBridgeError("ANSWER_ALREADY_GIVEN", ask_id)
        answer_id = mint_message_id(principal, "answer", ask_id,
                                    idempotency_key, answer)
        state = self._replay_state(record)
        advance_ask_state(state, "ANSWERED", record=record, now=now)
        # H2: ONE event.  The trusted answer event IS the answered state
        # (replay infers it) — there is no second append whose loss could
        # strand the answer behind a false OPEN.
        self._store.append_ask_event(ask_id, {
            "type": "answer", "answer_id": answer_id,
            "idempotency_key": idempotency_key, "text": answer})
        return {"status": "ANSWERED", "answer_id": answer_id}

    def fetch_result(self, *, principal: str, ask_id: str) -> dict[str, Any]:
        """One delivery per answer, host-wide.

        GBL-5 micro 3, RULING 19(a): the read, the replay and the CONSUMED
        append are ONE decision under the store's host lock.  Serialising
        only the appends left the read-then-decide outside them, and "one
        connection at a time" is a property of today's server, not of this
        layer.

        GBL-5 micro 4 (principal's ruling, 10:55Z): the lock alone is not
        enough — the record re-read behind it is the issue's comment
        listing, which can lag a write that has ALREADY landed.  Caller A
        marks CONSUMED and is served ANSWER_UNCONSUMED; caller B takes the
        lock, sees a stale ANSWERED, finds no trusted mark to dedupe
        against, mints the next number and posts a second CONSUMED.  So
        the decision is never taken from a read that can lag the host's
        own writes: under the same lock the delivery (ask id + answer id)
        is recorded in the host ledger BEFORE the CONSUMED post, and that
        record is consulted FIRST.  Recorded ⇒ CONSUMED, whatever the
        listing shows.  If the record lands and the post then fails, the
        answer stays withheld and the caller gets
        ``DELIVERY_MARK_POST_FAILED`` — never a second
        ANSWER_UNCONSUMED."""
        with self._delivery_lock():
            record = self._require_ask(ask_id)     # re-read under the lock
            self._require_party(record, principal)
            now = self._now()
            if is_expired(record, now):
                raise GblBridgeError("EXPIRED", ask_id)   # never silence
            records = self._delivery_records()
            delivered = records[0](ask_id) if records else None
            state = self._replay_state(record)
            answer = self._last_answer(record)
            if delivered is not None:
                # The host's own record cannot lag: this answer was handed
                # over once, so the listing cannot hand it over again.
                return {"status": "CONSUMED", "ask_id": ask_id,
                        "answer": answer.get("text"),
                        "answer_id": answer.get("answer_id") or delivered}
            if state == "CONSUMED":
                return {"status": "CONSUMED", "ask_id": ask_id,
                        "answer": answer.get("text"),
                        "answer_id": answer.get("answer_id")}
            if state == "ANSWERED":
                answer_id = answer.get("answer_id")
                if records is not None:
                    records[1](ask_id,
                               answer_id if isinstance(answer_id, str) else "")
                try:
                    self._store.append_ask_event(
                        ask_id, {"type": "state", "state": "CONSUMED"})
                except Exception as exc:             # noqa: BLE001
                    # The delivery is recorded, so the answer is withheld:
                    # a retry is CONSUMED, never a second hand-over.
                    code = getattr(exc, "code", None) or type(exc).__name__
                    raise GblBridgeError(
                        "DELIVERY_MARK_POST_FAILED",
                        f"{ask_id}: answer recorded as delivered, mark "
                        f"post failed ({code})") from None
                # The honest surfacing: answered but never fetched.
                return {"status": "ANSWER_UNCONSUMED", "ask_id": ask_id,
                        "answer": answer.get("text"),
                        "answer_id": answer.get("answer_id")}
            return {"status": "NOT_YET", "ask_id": ask_id}

    def _delivery_records(self):
        """The store's ``(delivered_answer_id, record_delivery)`` pair,
        or ``None`` for an explicitly marked test double (GBL-5 micro 4).

        A store that offers the host lock MUST offer the whole capability:
        a partial one would decide from the lagging listing again, so it
        refuses typed instead of degrading silently."""
        read = getattr(self._store, "delivered_answer_id", None)
        write = getattr(self._store, "record_delivery", None)
        if read is not None and write is not None:
            return read, write
        if (read is not None or write is not None
                or getattr(self._store, "result_delivery_lock", None)
                is not None):
            raise GblBridgeError("DELIVERY_CAPABILITY_INCOMPLETE",
                                 type(self._store).__name__)
        return None

    def _delivery_lock(self):
        """The store's host-wide result-delivery lock
        (:class:`GblResultDeliveryLockStore`).

        Fails CLOSED: a store that does not offer the capability refuses
        typed unless it is an explicitly marked test double.  A store
        without the lock can hand one answer out twice, so silence here
        would be the defect, not the compatibility."""
        lock = getattr(self._store, "result_delivery_lock", None)
        if lock is None and not getattr(self._store, "GBL_TEST_DOUBLE", False):
            raise GblBridgeError(
                "DELIVERY_LOCK_UNAVAILABLE", type(self._store).__name__)
        return lock() if lock is not None else contextlib.nullcontext()

    def _dispatch_store(self) -> Any:
        """The store's delegate-dispatch arm
        (:class:`GblDelegateDispatchStore`), or ``None`` for an explicitly
        marked test double.

        Fails CLOSED exactly like the delivery lock: a production store
        missing ANY of the five methods refuses typed — silently skipping
        dispatch would leave a delegate ask recorded as created while no
        work ever reached the teammate, which is the defect GBL-RETURN
        exists to remove."""
        store = self._store
        missing = [name for name in
                   ("resolve_target_agent", "dispatch_delegate",
                    "read_dispatch_child", "read_child_result",
                    "scan_delegate_asks")
                   if getattr(store, name, None) is None]
        if not missing:
            return store
        if getattr(store, "GBL_TEST_DOUBLE", False):
            return None
        raise GblBridgeError(
            "DISPATCH_CAPABILITY_UNAVAILABLE",
            f"{type(store).__name__} lacks {','.join(missing)}")

    def _require_dispatch_target(self, target: str) -> None:
        """Pre-create target resolution for a delegate ask: the typed
        TARGET_AGENT_NOT_CONFIGURED refusal (or the fail-closed capability
        refusal) fires BEFORE the record exists, so an undispatchable ask
        never becomes an orphan issue."""
        store = self._dispatch_store()
        if store is not None:
            store.resolve_target_agent(target)

    def _host_delivered(self, ask_id: str) -> bool:
        """True once the HOST's own delivery record exists for the ask.

        GBL-5 micro 5b: the record is written before the CONSUMED post, so
        it is the only source that cannot lag this host's own writes — the
        listing can (``comment_visibility_lag``) and a failed post never
        lands at all.  Read under the same host-wide delivery lock
        ``fetch_result`` decides under, from the store's ledger arm.
        ``False`` from a store that keeps no record (explicitly marked
        ``GBL_TEST_DOUBLE``) preserves its plain listing read."""
        records = self._delivery_records()
        if records is None:
            return False
        with self._delivery_lock():
            return records[0](ask_id) is not None

    def ask_status(self, *, principal: str, ask_id: str) -> dict[str, Any]:
        record = self._require_ask(ask_id)
        self._require_party(record, principal)
        # M3: status and result agree about expiry — a dead ask reports
        # EXPIRED, never a live state it can no longer act in.
        if is_expired(record, self._now()):
            return {"ask_id": ask_id, "state": "EXPIRED", "status": "EXPIRED",
                    "expires_at": record["expires_at"]}
        # GBL-5 micro 5b: the host record wins over the listing.  After a
        # failed CONSUMED post the listing still says ANSWERED while
        # fetch_result — correctly — reports CONSUMED; status must agree.
        if self._host_delivered(ask_id):
            state = "CONSUMED"
            return {"ask_id": ask_id, "state": state,
                    "status": surface_ask_state(state),
                    "expires_at": record["expires_at"]}
        state = self._replay_state(record)
        return {"ask_id": ask_id, "state": state,
                "status": surface_ask_state(state),
                "expires_at": record["expires_at"]}

    def handle_nudge_delivery(self, wake: Mapping[str, Any]) -> dict[str, Any]:
        """The webhook guard: a nudge is attention only.  A redelivered
        nudge whose ask id matches nothing is an ASK_NOT_FOUND no-op; a
        known ask is acknowledged and NO work is created — job creation
        exists solely behind submit_ask with its own dedupe."""
        validate_wake(wake)
        if self._store.read_ask(wake["ask_id"]) is None:
            return {"status": "ASK_NOT_FOUND"}
        return {"status": "OK"}

    @staticmethod
    def _nudge_markers(record: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Every nudge-family row the trusted writer really POSTed: the
        authoritative ones (``trusted``) PLUS rows the GBL-5 R2 duplicate
        law demoted (``defect: EVENT_SEQ_DUPLICATE`` — the tag verified;
        only the number was re-issued).  A POST that happened must count
        for budget, cooldown and settlement however the chain law
        re-numbered it (deputy MED-2); a FOREIGN row counts nothing.

        GBL-5 micro 1, RULING 19(a): the ``defect`` stamp is a marking a
        comment body cannot supply — the store strips EVERY key only it
        may set (``paperclip_client.STORE_ONLY_EVENT_KEYS``) from a stored
        event before verification and re-attaches the stamp itself only
        after the tag verified and the chain law demoted the row.  So the
        two conditions below are exactly "this row is the store's".  The
        same body keys are stripped by the bridge's own in-place demotion
        (:meth:`_ordered_events`), which is the only other writer of it."""
        markers: list[dict[str, Any]] = []
        for event in record.get("events", ()):
            if event.get("type") not in ("nudge", "nudge_attempt",
                                         "nudge_settled"):
                continue
            if (event.get("trusted") is True
                    or event.get("defect") == "EVENT_SEQ_DUPLICATE"):
                markers.append(event)
        return markers

    @staticmethod
    def _marker_time(event: Mapping[str, Any], ask_id: str) -> datetime:
        """A counted marker's ``at`` as an aware datetime.

        GBL-5 micro 2: a counted marker without a usable timestamp used to
        escape as a raw ``KeyError``/``ValueError`` — an untyped
        INTERNAL_ERROR over the socket door, repeated on every later
        re-nudge for the ask.  It is now a TYPED refusal: the layer
        withholds (nothing is sent) and reports exactly why."""
        try:
            return _parse_iso(event["at"])
        except (KeyError, TypeError, ValueError):
            raise GblBridgeError(
                "NUDGE_MARKER_TIMESTAMP_INVALID",
                f"ask {ask_id}: a counted nudge marker carries no usable "
                f"'at'; cooldown and settlement cannot be derived — "
                f"nothing is sent") from None

    def _nudge_law(self, ask_id: str, record: Mapping[str, Any],
                   now: datetime) -> tuple[list[dict[str, Any]],
                                           list[dict[str, Any]]]:
        """The shared decision half of the nudge law.  GBL-RETURN outcome 3
        puts QUESTION_AVAILABLE under EXACTLY the same budget, unsettled-
        attempt and cooldown law as ANSWERED, so both paths derive from
        this one method — one law, two states.

        Returns ``(every counted marker, the delivered-nudge subset)``."""
        self._ordered_events(record)   # chain law enforced on the record
        # Budget, cooldown and settlement count every nudge-family row the
        # trusted writer really POSTed — including a row the duplicate law
        # demoted (deputy MED-2: a demoted nudge or attempt must not
        # silently un-burn budget or re-arm the lane).
        events = self._nudge_markers(record)
        nudges = [event for event in events if event.get("type") == "nudge"]
        attempts = [event for event in events
                    if event.get("type") == "nudge_attempt"]
        if len(nudges) >= MAX_RENUDGES_PER_ASK:
            raise GblBridgeError("RENUDGE_BUDGET_EXHAUSTED", ask_id)
        # Round 2 (the M8 residue): an attempt is SETTLED only by a nudge or
        # nudge_settled event appended after it — by the receipt here (a
        # definite no-start) or by reconcile_nudge (an effect-unknown send).
        # An unsettled attempt blocks re-nudge for good: time never re-arms
        # an effect whose outcome is unknown, because the only lawful next
        # step is reconcile, never a second POST of the same wake.
        settled_after_last_attempt = False
        for event in events:
            if event.get("type") == "nudge_attempt":
                settled_after_last_attempt = False
            elif event.get("type") in ("nudge", "nudge_settled"):
                settled_after_last_attempt = True
        if attempts and not settled_after_last_attempt:
            raise GblBridgeError(
                "NUDGE_ATTEMPT_UNSETTLED",
                "an effect-unknown nudge attempt must be settled by "
                "reconcile before any re-nudge; it is never re-sent")
        # Cooldown counts every marker — delivered nudges, attempts and
        # settlements — so spacing between actual wake POSTs is enforced.
        markers = nudges + attempts + [
            event for event in events
            if event.get("type") == "nudge_settled"]
        if markers:
            last = max(self._marker_time(event, ask_id) for event in markers)
            elapsed = (now - last).total_seconds()
            if elapsed < RENUDGE_COOLDOWN_SECONDS:
                raise GblBridgeError(
                    "RENUDGE_COOLDOWN",
                    f"{int(RENUDGE_COOLDOWN_SECONDS - elapsed)}s remain")
        return events, nudges

    def _nudge_fire(self, ask_id: str, state: str,
                    record: Mapping[str, Any],
                    nudges: list[dict[str, Any]], now: datetime,
                    sent_status: str) -> dict[str, Any]:
        """The shared send half of the nudge law, for either wake state.
        M8: the attempt is persisted BEFORE the send and independent of its
        outcome, so an effect-unknown send can never be repeated blindly —
        reconcile via :meth:`reconcile_nudge`, never resend.  M7: the
        transport receipt is consumed — a definite no-start (pre-submit
        refusal, TARGET_UNAVAILABLE, FAILED) is a typed
        ``NUDGE_NOT_DELIVERED`` that burns no budget, never a false
        success.  ``sent_status`` names a delivered send for the caller's
        path ("RENUDGED" for ANSWERED, "QUESTION_NUDGED" for a question)."""
        if self._nudge_sender is None or self._resolve_handle is None:
            raise GblBridgeError("NUDGE_SENDER_UNAVAILABLE", ask_id)
        native_handle = self._resolve_handle(record["principal"])
        at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Persist first: whatever the send does, the attempt exists.
        self._store.append_ask_event(ask_id, {
            "type": "nudge_attempt", "state": state, "at": at})
        try:
            sent = self._nudge_sender.send(ask_id, state, native_handle)
        except WakeEffectUnknownError:
            return {"status": "NUDGE_EFFECT_UNKNOWN", "ask_id": ask_id}
        except WakePreSubmitError as exc:
            # A definite no-start settles the attempt immediately: nothing
            # unknown remains, so the lane stays usable after cooldown.
            self._store.append_ask_event(ask_id, {
                "type": "nudge_settled", "outcome": "NOT_DELIVERED",
                "state": state, "at": at})
            return {"status": "NUDGE_NOT_DELIVERED", "ask_id": ask_id,
                    "reason_code": str(getattr(exc, "reason_code", ""))}
        except WakeDispatchError as exc:
            raise GblBridgeError("NUDGE_SEND_FAILED",
                                 type(exc).__name__) from None
        receipt = getattr(sent, "receipt", sent)   # unwrap a completion
        outcome = getattr(receipt, "outcome", None)
        if outcome in (TransportOutcome.ACCEPTED, TransportOutcome.DELIVERED):
            self._store.append_ask_event(ask_id, {
                "type": "nudge", "state": state, "at": at})
            return {"status": sent_status, "ask_id": ask_id,
                    "nudge_count": len(nudges) + 1}
        if outcome in (TransportOutcome.TARGET_UNAVAILABLE,
                       TransportOutcome.FAILED):
            self._store.append_ask_event(ask_id, {
                "type": "nudge_settled", "outcome": "NOT_DELIVERED",
                "state": state, "at": at})
            return {"status": "NUDGE_NOT_DELIVERED", "ask_id": ask_id,
                    "reason_code": str(getattr(receipt, "reason_code", ""))}
        raise GblBridgeError("NUDGE_RECEIPT_INVALID",
                             f"unrecognized receipt shape {type(sent).__name__}")

    def maybe_renudge(self, *, ask_id: str) -> dict[str, Any]:
        """One re-nudge per cooldown for an unconsumed answer, bounded by
        the contract budget (MAX_RENUDGES_PER_ASK).  The law itself lives
        in :meth:`_nudge_law` / :meth:`_nudge_fire`, shared verbatim with
        the question nudge (GBL-RETURN outcome 3)."""
        record = self._require_ask(ask_id)
        # GBL-5 micro 5b: a delivered answer owes no reminder, whatever
        # the listing shows.  Before this, a failed CONSUMED post left the
        # listing at ANSWERED and reminders kept going until the budget
        # was gone.  This arm sends nothing and is named for the caller.
        if self._host_delivered(ask_id):
            return {"status": "ALREADY_DELIVERED", "ask_id": ask_id}
        state = self._replay_state(record)
        if state != "ANSWERED":
            return {"status": state, "ask_id": ask_id}
        now = self._now()
        _events, nudges = self._nudge_law(ask_id, record, now)
        return self._nudge_fire(ask_id, "ANSWERED", record, nudges, now,
                                "RENUDGED")

    def reconcile_nudge(self, *, principal: str,
                        ask_id: str) -> dict[str, Any]:
        """M8's settle path: reconcile the last unresolved nudge attempt by
        OBSERVING the transport — never by sending again.  Round 2: the same
        creator-or-addressee party check as every other mutating op, and
        BOTH outcomes settle durably — delivered appends the budget-counting
        nudge event; a definite non-delivery appends a ``nudge_settled``
        marker so the lane re-arms after cooldown without burning budget."""
        record = self._require_ask(ask_id)
        self._require_party(record, principal)
        # GBL-5 micro 5b: reconcile observes the transport for an answer
        # the host has NOT yet handed over.  Once the host record exists,
        # there is nothing to settle and nothing is observed or sent.
        if self._host_delivered(ask_id):
            return {"status": "ALREADY_DELIVERED", "ask_id": ask_id}
        self._ordered_events(record)   # chain law enforced on the record
        # The same POST-really-happened view as maybe_renudge (deputy
        # MED-2): a demoted attempt is still an attempt to reconcile, and
        # a demoted settlement still settles it.
        events = self._nudge_markers(record)
        attempts = [event for event in events
                    if event.get("type") == "nudge_attempt"]
        nudges = [event for event in events if event.get("type") == "nudge"]
        if not attempts:
            raise GblBridgeError("NUDGE_ATTEMPT_NOT_FOUND", ask_id)
        settled_after_last_attempt = False
        for event in events:
            if event.get("type") == "nudge_attempt":
                settled_after_last_attempt = False
            elif event.get("type") in ("nudge", "nudge_settled"):
                settled_after_last_attempt = True
        if settled_after_last_attempt:
            raise GblBridgeError("NUDGE_ALREADY_SETTLED", ask_id)
        # The settlement row reuses the attempt's timestamp AND its state;
        # validate the timestamp BEFORE any transport call so a malformed
        # attempt refuses typed instead of sending a wake whose settlement
        # it could not record.  GBL-RETURN outcome 3: a QUESTION_AVAILABLE
        # attempt settles under the same law — the state is the attempt's
        # own, never assumed (a pre-GBL-RETURN attempt carries "ANSWERED"
        # and keeps settling exactly as before; a legacy row without the
        # key defaults to "ANSWERED", the only state that ever existed).
        self._marker_time(attempts[-1], ask_id)
        attempt_at = attempts[-1]["at"]
        attempt_state = str(attempts[-1].get("state") or "ANSWERED")
        if self._nudge_sender is None or self._resolve_handle is None:
            raise GblBridgeError("NUDGE_SENDER_UNAVAILABLE", ask_id)
        native_handle = self._resolve_handle(record["principal"])
        try:
            settled = self._nudge_sender.reconcile(ask_id, attempt_state,
                                                   native_handle)
        except WakeEffectUnknownError:
            return {"status": "NUDGE_EFFECT_UNKNOWN", "ask_id": ask_id}
        except WakePreSubmitError as exc:
            self._store.append_ask_event(ask_id, {
                "type": "nudge_settled", "outcome": "NOT_DELIVERED",
                "state": attempt_state, "at": attempt_at})
            return {"status": "RECONCILED_NOT_DELIVERED", "ask_id": ask_id,
                    "reason_code": str(getattr(exc, "reason_code", ""))}
        except WakeDispatchError as exc:
            raise GblBridgeError("NUDGE_RECONCILE_FAILED",
                                 type(exc).__name__) from None
        receipt = getattr(settled, "receipt", settled)
        outcome = getattr(receipt, "outcome", None)
        if outcome in (TransportOutcome.ACCEPTED, TransportOutcome.DELIVERED):
            self._store.append_ask_event(ask_id, {
                "type": "nudge", "state": attempt_state,
                "at": attempt_at})
            return {"status": "RECONCILED_DELIVERED", "ask_id": ask_id,
                    "nudge_count": len(nudges) + 1}
        if outcome in (TransportOutcome.TARGET_UNAVAILABLE,
                       TransportOutcome.FAILED):
            self._store.append_ask_event(ask_id, {
                "type": "nudge_settled", "outcome": "NOT_DELIVERED",
                "state": attempt_state, "at": attempt_at})
            return {"status": "RECONCILED_NOT_DELIVERED", "ask_id": ask_id,
                    "reason_code": str(getattr(receipt, "reason_code", ""))}
        raise GblBridgeError("NUDGE_RECEIPT_INVALID",
                             f"unrecognized receipt shape {type(settled).__name__}")

    # -- GBL-RETURN: the delegate dispatch/return edge ------------------------

    def _ensure_dispatched(self, record: Mapping[str, Any],
                           store: Any) -> dict[str, Any]:
        """Create-or-reuse the board child for a delegate ask, exactly once
        per ask.  A TRUSTED ``dispatch`` event is the permanent marker, so
        a replay (a re-sent ask, a return wake, a recovery scan) never
        dispatches a second time; and a lost dispatch event still cannot
        duplicate the child, because the store's dispatch is itself a
        reuse scan under the RF identity law.  The event is deterministic
        (no timestamp): the store's canonical-JSON append idempotency makes
        even a duplicate append a no-op."""
        for event in self._ordered_events(record):
            if event.get("type") == "dispatch" and event.get("child_issue_id"):
                return {"status": "ALREADY_DISPATCHED",
                        "child_issue_id": str(event["child_issue_id"])}
        envelope = _record_envelope(record)
        ask_id = str(envelope.get("ask_id") or "")
        try:
            outcome = store.dispatch_delegate(envelope)
        except GblCreateEffectUnknown:
            # The child may or may not exist and the relation may be half
            # recorded: the effect stays unknown, and the ONLY recovery is
            # a later ensure, which reconciles by the store's reuse scan —
            # never a blind second dispatch.
            return {"status": "DISPATCH_EFFECT_UNKNOWN", "ask_id": ask_id}
        child_id = str(outcome["child_issue_id"])
        self._store.append_ask_event(ask_id, {
            "type": "dispatch", "child_issue_id": child_id,
            "target_agent": str(outcome["target_agent"])})
        return {"status": "REUSED" if outcome.get("reused") else "DISPATCHED",
                "ask_id": ask_id, "child_issue_id": child_id}

    def _nudge_question_once(self, ask_id: str) -> dict[str, Any]:
        """GBL-RETURN outcome 3 — exactly one QUESTION_AVAILABLE nudge for
        a CREATED question ask, from SHIPPED code, under the same
        budget/cooldown/unknown-effect law as ANSWERED (:meth:`_nudge_law`
        + :meth:`_nudge_fire`).

        Exactly-once: ANY question-state marker the trusted writer really
        posted — a delivered nudge, an unsettled attempt or a settlement —
        means the one nudge was already attempted; a wake is never
        re-sent because attention is cheap to duplicate and the record is
        not.  NO state event is appended: the ask stays OPEN (a question
        nudge is attention, not an answer)."""
        record = self._require_ask(ask_id)
        state = self._replay_state(record)
        if state in ("ANSWERED", "CONSUMED"):
            return {"status": "SKIPPED_ANSWERED", "ask_id": ask_id}
        for event in self._nudge_markers(record):
            if event.get("state") == "QUESTION_AVAILABLE":
                return {"status": "NUDGE_ALREADY_ATTEMPTED",
                        "ask_id": ask_id}
        now = self._now()
        _events, nudges = self._nudge_law(ask_id, record, now)
        return self._nudge_fire(ask_id, "QUESTION_AVAILABLE", record,
                                nudges, now, "QUESTION_NUDGED")

    def return_delegate(self, *, ask_id: str) -> dict[str, Any]:
        """GBL-RETURN outcome 2 — DELEGATE BACK.  The bridge takes the
        answer from its OWN board read (its created child, assignee = the
        spec-resolved target agent, the carrier's result comment), never
        from waker-supplied text: a wake carries the ask id and nothing
        else.  This is the board-wake handler AND the scan-recovered path.

        Outcome 5 (ruling 19 delivery law, exactly-once):
        * a duplicate wake no-ops — an answered/consumed/host-delivered
          ask reports ALREADY_ANSWERED and posts nothing;
        * a lost wake is recovered by READ, not a second send — a child
          that is not done reports NOT_YET;
        * a return for a child the bridge did not create refuses typed
          (the store's read_dispatch_child identity law,
          RETURN_CHILD_NOT_OURS) and never enters the record.

        Outcome 4: an ask that is not a delegate (including the bridge's
        own ask-record issue being assigned to the bridge agent) is a
        harmless typed no-op, never an error run."""
        record = self._require_ask(ask_id)
        if record.get("kind") != "delegate":
            return {"status": "NOT_A_DELEGATE", "ask_id": ask_id}
        now = self._now()
        if is_expired(record, now):
            return {"status": "EXPIRED", "ask_id": ask_id}
        state = self._replay_state(record)
        if state in ("ANSWERED", "CONSUMED") or self._host_delivered(ask_id):
            return {"status": "ALREADY_ANSWERED", "ask_id": ask_id,
                    "state": state}
        store = self._dispatch_store()
        if store is None:
            raise GblBridgeError("DISPATCH_CAPABILITY_UNAVAILABLE",
                                 type(self._store).__name__)
        # Recovery re-dispatch: if the dispatch event was lost (or the
        # original dispatch was effect-unknown), ensure reconciles by the
        # store's reuse scan — one child, whatever the history.
        dispatch = self._ensure_dispatched(record, store)
        if dispatch["status"] == "DISPATCH_EFFECT_UNKNOWN":
            return {"status": "DISPATCH_EFFECT_UNKNOWN", "ask_id": ask_id}
        child_id = dispatch["child_issue_id"]
        result = store.read_child_result(ask_id, child_id)
        if result.get("cancelled"):
            return {"status": "CHILD_CANCELLED", "ask_id": ask_id,
                    "child_issue_id": child_id}
        if not result.get("done"):
            return {"status": "NOT_YET", "ask_id": ask_id,
                    "child_issue_id": child_id}
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            # A done child with no usable comment: reported, never posted
            # as an empty answer.  The next wake/scan re-reads.
            return {"status": "NO_ANSWER_COMMENT", "ask_id": ask_id,
                    "child_issue_id": child_id}
        try:
            posted = self.post_answer(
                principal=record["principal"], ask_id=ask_id, answer=answer,
                idempotency_key=f"gbl-board-return-{ask_id}")
        except GblBridgeError as exc:
            if exc.code == "ANSWER_ALREADY_GIVEN":
                return {"status": "ALREADY_ANSWERED", "ask_id": ask_id}
            if exc.code == "EXPIRED":
                return {"status": "EXPIRED", "ask_id": ask_id}
            raise
        # The one ANSWERED nudge (existing intake + attention law).  A
        # nudge failure is reported in the result, never fatal: the answer
        # is durably in the record and reconcile_nudge/return_scan heal
        # the attention edge.
        try:
            nudge = self.maybe_renudge(ask_id=ask_id)
        except GblBridgeError as exc:
            nudge = {"status": exc.code, "ask_id": ask_id}
        return {"status": "RETURNED", "ask_id": ask_id,
                "child_issue_id": child_id,
                "answer_id": posted.get("answer_id"),
                "nudge": nudge}

    def return_scan(self) -> dict[str, Any]:
        """GBL-RETURN outcome 2 — the bridge's own bounded read of open
        delegate asks: the lost-wake recovery source when no board wake
        arrived.  Read-only per ask until a child is actually done; one
        ask's typed failure is reported in its row and never aborts the
        remaining asks."""
        store = self._dispatch_store()
        if store is None:
            return {"status": "SCAN_SKIPPED"}
        results: list[dict[str, Any]] = []
        for ask_id in store.scan_delegate_asks()[:RETURN_SCAN_MAX]:
            try:
                row = self.return_delegate(ask_id=ask_id)
            except GblBridgeError as exc:
                row = {"status": exc.code, "ask_id": ask_id}
            results.append(row)
        return {"status": "SCANNED", "count": len(results),
                "results": results}


# ── The loopback socket door (peer uid only, the B14 service pattern) ───────


@dataclasses.dataclass(frozen=True)
class BridgeServiceConfig:
    socket_path: Path
    allowed_peer_uids: tuple[int, ...]
    request_timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        path = Path(self.socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        object.__setattr__(self, "socket_path", path)
        if (not isinstance(self.allowed_peer_uids, tuple)
                or not self.allowed_peer_uids
                or self.allowed_peer_uids != tuple(sorted(set(self.allowed_peer_uids)))
                or any(type(uid) is not int or uid < 0
                       for uid in self.allowed_peer_uids)):
            raise ValueError(
                "allowed_peer_uids must be sorted unique non-negative integers")
        if not 0.1 <= self.request_timeout_seconds <= 120:
            raise ValueError("request_timeout_seconds out of range")


def _peer_uid(connection: socket.socket) -> int | None:
    """Kernel peer credentials for an AF_UNIX socket connection (the
    Slack-relay service mechanism, FACTS B14).  macOS getpeereid first,
    Linux SO_PEERCRED second; None when the platform cannot prove a peer."""
    getpeereid = getattr(connection, "getpeereid", None)
    if callable(getpeereid):
        uid, _gid = getpeereid()
        return int(uid)
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.getpeereid
        function.argtypes = [ctypes.c_int,
                             ctypes.POINTER(ctypes.c_uint32),
                             ctypes.POINTER(ctypes.c_uint32)]
        function.restype = ctypes.c_int
        uid = ctypes.c_uint32()
        gid = ctypes.c_uint32()
        if function(connection.fileno(), ctypes.byref(uid),
                    ctypes.byref(gid)) != 0:
            return None
        return int(uid.value)
    if hasattr(socket, "SO_PEERCRED"):
        import struct
        size = struct.calcsize("3i")
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        _pid, uid, _gid = struct.unpack("3i", raw)
        return int(uid)
    return None


class BridgeServer:
    """One-request-per-connection AF_UNIX server around a GblBridge (or any
    object with its operation methods).  Admission is the kernel peer uid,
    read from the accepted socket BEFORE any payload byte is read; there is
    no TCP listener, and no header or source address is ever consulted.

    ``open()`` binds the socket AND starts serving on a daemon thread, so a
    client may connect as soon as open returns; ``close()`` stops the loop,
    unlinks the socket and joins the thread.  Connections are served one at
    a time — one logical effect at a time, in arrival order."""

    ACCEPT_TICK_SECONDS = 0.25      # accept poll tick; bounds shutdown lag

    def __init__(self, config: BridgeServiceConfig, bridge: Any) -> None:
        self.config = config
        self.bridge = bridge
        self._socket: socket.socket | None = None
        self._owned_path: Path | None = None
        self._serving = False
        self._thread: threading.Thread | None = None

    # -- lifecycle ------------------------------------------------------------

    def open(self) -> "BridgeServer":
        path = self.config.socket_path
        if path.exists():
            raise GblBridgeError("SOCKET_IN_USE", str(path))
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(8)
        os.chmod(path, 0o600)
        self._socket = server
        self._owned_path = path
        self._serving = True
        self._thread = threading.Thread(target=self._serve_loop,
                                        name="gbl-bridge-socket",
                                        daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        self._serving = False
        server = self._socket
        self._socket = None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        if self._owned_path is not None and self._owned_path.exists():
            self._owned_path.unlink()
            self._owned_path = None

    # -- serving --------------------------------------------------------------

    def _serve_loop(self) -> None:
        """H3: a per-connection failure NEVER ends the loop — only a fatal
        listener injury does, and that exit clears ``_serving``, closes the
        listener and unlinks the socket path so ``open()`` can restart
        cleanly instead of refusing SOCKET_IN_USE forever."""
        try:
            while self._serving:
                try:
                    self.serve_once()
                except OSError:
                    if not self._serving:
                        return          # normal close(): socket closed
                    break               # listener fatally broken
                except GblBridgeError:
                    break               # SERVER_NOT_OPEN / fatal injury
        finally:
            self._serving = False
            server = self._socket
            self._socket = None
            if server is not None:
                try:
                    server.close()
                except OSError:
                    pass
            if self._owned_path is not None:
                try:
                    if self._owned_path.exists():
                        self._owned_path.unlink()
                except OSError:
                    pass
                self._owned_path = None

    def serve_once(self) -> bool:
        """Accept and serve exactly one connection.  False on accept
        timeout (nothing was served); raises OSError once the listener is
        closed.  H3: every per-connection failure — a client hang-up
        mid-reply (EPIPE), a reply that cannot be framed (oversized or
        unencodable) — is contained HERE; the loop keeps serving."""
        if self._socket is None:
            raise GblBridgeError("SERVER_NOT_OPEN")
        self._socket.settimeout(self.ACCEPT_TICK_SECONDS)
        try:
            connection, _ = self._socket.accept()
        except socket.timeout:
            return False
        except OSError:
            if not self._serving:
                return False
            raise
        try:
            try:
                response = self._admit_and_dispatch(connection)
                frame = encode_gbl_frame(response)
            except (HostFrameError, UnicodeError, ValueError):
                # The reply could not be framed: answer with a small typed
                # fallback frame.  Request bytes are never echoed into it.
                frame = encode_gbl_frame(self._error("REPLY_FRAME_REFUSED"))
            try:
                connection.sendall(frame)
            except OSError:
                pass        # client hung up mid-reply: its loss, keep serving
        finally:
            try:
                connection.close()
            except OSError:
                pass
        return True

    # -- request handling -------------------------------------------------------

    def _read_frame(self, connection: socket.socket) -> bytes:
        connection.settimeout(self.config.request_timeout_seconds)
        buffer = b""
        while not buffer.endswith(b"\n"):
            chunk = connection.recv(4096)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > 2 * 1024 * 1024:
                raise GblBridgeError("REQUEST_TOO_LARGE")
        return buffer

    def _admit_and_dispatch(self, connection: socket.socket) -> dict[str, Any]:
        uid = _peer_uid(connection)
        if uid is None or uid not in self.config.allowed_peer_uids:
            return self._error("PEER_NOT_ALLOWED")
        try:
            frame = self._read_frame(connection)
            request = decode_gbl_frame(frame)
        except (HostFrameError, GblBridgeError, OSError):
            return self._error("REQUEST_INVALID")
        # H3b: an unhashable or non-string op is a typed refusal BEFORE the
        # frozenset membership test can raise outside every handler.
        if (set(request) != {"schema", "op", "arguments"}
                or request["schema"] != REQUEST_SCHEMA
                or type(request["op"]) is not str
                or type(request["arguments"]) is not dict):
            return self._error("REQUEST_INVALID")
        if request["op"] not in OPS:
            # H3d: the detail is a bounded sanitized prefix — a ~32 KiB op
            # never overflows the reply frame, and no raw request bytes
            # cross the wire beyond this visible prefix.
            return self._error("UNKNOWN_OP", _safe_detail(request["op"]))
        required, allowed = _OP_ARGUMENTS[request["op"]]
        keys = set(request["arguments"])
        if not keys <= allowed or not required <= keys:
            return self._error("INVALID_ARGUMENTS")
        method = getattr(self.bridge, _OP_METHODS[request["op"]])
        try:
            result = method(**request["arguments"])
        except GblBridgeError as exc:
            return self._error(exc.code, exc.detail)
        except GBLContractError as exc:
            return self._error(exc.code, exc.detail)
        except TypeError:
            return self._error("INVALID_ARGUMENTS")
        except Exception as exc:  # no traceback or payload crosses the wire
            # GBL-5 B2 (panel B old-code #2): the store's typed
            # GblPaperclipError (RECORD_INVALID, AMBIGUOUS_CREATE, …) must
            # reach the caller with ITS code and detail, not be flattened
            # to INTERNAL_ERROR.  The import is local because
            # paperclip_client imports this module at load (a top-level
            # import here would be a load-order cycle); at dispatch time
            # both modules are loaded and this is a sys.modules lookup.
            from integrations.gbl.paperclip_client import GblPaperclipError
            if isinstance(exc, GblPaperclipError):
                return self._error(exc.code, exc.detail)
            return self._error("INTERNAL_ERROR", type(exc).__name__)
        return {"schema": RESPONSE_SCHEMA, "ok": True, "result": result}

    @staticmethod
    def _error(code: str, detail: str = "") -> dict[str, Any]:
        return {"schema": RESPONSE_SCHEMA, "ok": False,
                "error": {"code": code, "detail": detail}}


def _safe_detail(value: str, limit: int = 48) -> str:
    """A bounded, printable-ASCII detail prefix: never enough of a hostile
    request to matter, never unencodable, never oversized."""
    cleaned = "".join(chr(ch) if 32 <= ch < 127 else "?"
                      for ch in value.encode("utf-8", "replace")[:limit])
    return cleaned


# H1: the wire validates the argument keys of every op against the same
# shared schema the MCP edge validates ("answer" IS the contract's
# ANSWER_ARGUMENT_KEYS), so an edge/bridge drift is a typed refusal at the
# door, never a TypeError deep in the core.
_OP_ARGUMENTS = {
    "ask": (frozenset({"principal", "kind", "target", "title", "body",
                       "idempotency_key"}),
            frozenset({"principal", "kind", "target", "title", "body",
                       "idempotency_key", "correlation", "asker"})),
    "answer": (ANSWER_ARGUMENT_KEYS, ANSWER_ARGUMENT_KEYS),
    "result": (frozenset({"principal", "ask_id"}),
               frozenset({"principal", "ask_id"})),
    "question": (frozenset({"principal", "ask_id"}),
                 frozenset({"principal", "ask_id"})),
    "status": (frozenset({"principal", "ask_id"}),
               frozenset({"principal", "ask_id"})),
    "reconcile": (frozenset({"principal", "ask_id"}),
                  frozenset({"principal", "ask_id"})),
    # GBL-RETURN: the wake carries the ask id and NOTHING else (outcome 2)
    # — no answer text, no child id, no caller-supplied target crosses the
    # door.  return_scan takes no arguments at all.
    "return": (frozenset({"ask_id"}), frozenset({"ask_id"})),
    "return_scan": (frozenset(), frozenset()),
}

_OP_METHODS = {
    "ask": "submit_ask",
    "answer": "post_answer",
    "result": "fetch_result",
    "question": "fetch_question",
    "status": "ask_status",
    "reconcile": "reconcile_nudge",
    "return": "return_delegate",
    "return_scan": "return_scan",
}

__all__ = [
    "DEFAULT_ADMISSION_TABLE",
    "OPS",
    "PrincipalAdmission",
    "RENUDGE_COOLDOWN_SECONDS",
    "RETURN_SCAN_MAX",
    "BridgeServer",
    "BridgeServiceConfig",
    "GblAskStore",
    "GblBridge",
    "GblBridgeError",
    "GblCreateEffectUnknown",
    "GblDelegateDispatchStore",
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
]
