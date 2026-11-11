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

# Lane-chosen default (not doc-pinned): one re-nudge per ask per 15-minute
# cooldown, bounded by MAX_RENUDGES_PER_ASK (ARCHITECTURE flow 1 step 10).
RENUDGE_COOLDOWN_SECONDS = 900

REQUEST_SCHEMA = "mastermind.gbl.request.v1"
RESPONSE_SCHEMA = "mastermind.gbl.response.v1"
OPS = frozenset({"ask", "answer", "result", "question", "status"})


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


@runtime_checkable
class GblAskStore(Protocol):
    def create_ask(self, ask: Mapping[str, Any]) -> None: ...
    def read_ask(self, ask_id: str) -> Mapping[str, Any] | None: ...
    def append_ask_event(self, ask_id: str, event: Mapping[str, Any]) -> None: ...
    def count_asks(self, principal: str, since_iso: str) -> int: ...


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
    def _require_principal(record: Mapping[str, Any], principal: str) -> None:
        if record.get("principal") != principal:
            raise GblBridgeError("ASK_NOT_FOR_PRINCIPAL", principal or "")

    @staticmethod
    def _replay_state(record: Mapping[str, Any]) -> str:
        """Replay the record's state events through the contract chain.
        Historical events were lawful when appended; expiry is enforced at
        operation time, not on replay."""
        state = record["state"]
        for event in record.get("events", ()):
            if event.get("type") == "state":
                state = advance_ask_state(state, event["state"])
        return state

    def _last_answer(self, record: Mapping[str, Any]) -> dict[str, Any]:
        answers = [event for event in record.get("events", ())
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
        now = self._now()
        since = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        asks_last_hour = self._store.count_asks(principal, since)
        admit_ask_rate(asks_last_hour)          # the contract-global ceiling
        if asks_last_hour + 1 > row.max_asks_per_hour:
            raise GblBridgeError("RATE_LIMITED",
                                 f"ceiling {row.max_asks_per_hour}/hour")
        envelope = build_ask(kind=kind, principal=principal, target=target,
                             title=title, body=body,
                             idempotency_key=idempotency_key,
                             correlation=dict(correlation or {}),
                             asker=dict(asker) if asker else None, now=now)
        ask_id = envelope["ask_id"]
        existing = self._store.read_ask(ask_id)
        if existing is not None:
            verdict = classify_ask_duplicate(
                _record_envelope(existing), envelope)
            if verdict.value == "IDEMPOTENT":
                return {"status": "IDEMPOTENT", "ask": dict(existing)}
            raise GblBridgeError("CONFLICT",
                                 f"key {idempotency_key} reused with new content")
        try:
            self._store.create_ask(envelope)
        except GblCreateEffectUnknown:
            # EFFECT_UNKNOWN law: reconcile by read-back of the deterministic
            # ask id; never a second create.
            landed = self._store.read_ask(ask_id)
            if landed is not None:
                return {"status": "IDEMPOTENT", "ask": dict(landed)}
            raise GblBridgeError(
                "EFFECT_UNKNOWN",
                "issue create effect unknown; reconcile by ask-id read-back") from None
        return {"status": "CREATED", "ask": dict(envelope)}

    def fetch_question(self, *, principal: str, ask_id: str) -> dict[str, Any]:
        record = self._require_ask(ask_id)
        self._require_principal(record, principal)
        if is_expired(record, self._now()):
            raise GblBridgeError("EXPIRED", ask_id)
        return {"ask_id": ask_id, "kind": record["kind"],
                "question": record["body"], "expires_at": record["expires_at"]}

    def post_answer(self, *, principal: str, ask_id: str, answer: str,
                    idempotency_key: str) -> dict[str, Any]:
        record = self._require_ask(ask_id)
        self._require_principal(record, principal)
        now = self._now()
        if is_expired(record, now):
            raise GblBridgeError("EXPIRED", ask_id)
        for event in record.get("events", ()):
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
        self._store.append_ask_event(ask_id, {
            "type": "answer", "answer_id": answer_id,
            "idempotency_key": idempotency_key, "text": answer})
        self._store.append_ask_event(ask_id, {"type": "state",
                                              "state": "ANSWERED"})
        return {"status": "ANSWERED", "answer_id": answer_id}

    def fetch_result(self, *, principal: str, ask_id: str) -> dict[str, Any]:
        record = self._require_ask(ask_id)
        self._require_principal(record, principal)
        now = self._now()
        if is_expired(record, now):
            raise GblBridgeError("EXPIRED", ask_id)   # never silence
        state = self._replay_state(record)
        answer = self._last_answer(record)
        if state == "CONSUMED":
            return {"status": "CONSUMED", "ask_id": ask_id,
                    "answer": answer.get("text"),
                    "answer_id": answer.get("answer_id")}
        if state == "ANSWERED":
            # The honest surfacing: answered but never fetched.
            self._store.append_ask_event(ask_id, {"type": "state",
                                                  "state": "CONSUMED"})
            return {"status": "ANSWER_UNCONSUMED", "ask_id": ask_id,
                    "answer": answer.get("text"),
                    "answer_id": answer.get("answer_id")}
        return {"status": "NOT_YET", "ask_id": ask_id}

    def ask_status(self, *, principal: str, ask_id: str) -> dict[str, Any]:
        record = self._require_ask(ask_id)
        self._require_principal(record, principal)
        state = self._replay_state(record)
        return {"ask_id": ask_id, "state": state,
                "status": surface_ask_state(state)}

    def handle_nudge_delivery(self, wake: Mapping[str, Any]) -> dict[str, Any]:
        """The webhook guard: a nudge is attention only.  A redelivered
        nudge whose ask id matches nothing is an ASK_NOT_FOUND no-op; a
        known ask is acknowledged and NO work is created — job creation
        exists solely behind submit_ask with its own dedupe."""
        validate_wake(wake)
        if self._store.read_ask(wake["ask_id"]) is None:
            return {"status": "ASK_NOT_FOUND"}
        return {"status": "OK"}

    def maybe_renudge(self, *, ask_id: str) -> dict[str, Any]:
        """One re-nudge per cooldown for an unconsumed answer, bounded by
        the contract budget (MAX_RENUDGES_PER_ASK).  A nudge whose send
        effect is unknown propagates WakeEffectUnknown — reconcile, never
        resend."""
        record = self._require_ask(ask_id)
        state = self._replay_state(record)
        if state != "ANSWERED":
            return {"status": state, "ask_id": ask_id}
        now = self._now()
        nudges = [event for event in record.get("events", ())
                  if event.get("type") == "nudge"]
        if len(nudges) >= MAX_RENUDGES_PER_ASK:
            raise GblBridgeError("RENUDGE_BUDGET_EXHAUSTED", ask_id)
        if nudges:
            last = _parse_iso(nudges[-1]["at"])
            elapsed = (now - last).total_seconds()
            if elapsed < RENUDGE_COOLDOWN_SECONDS:
                raise GblBridgeError(
                    "RENUDGE_COOLDOWN",
                    f"{int(RENUDGE_COOLDOWN_SECONDS - elapsed)}s remain")
        if self._nudge_sender is None or self._resolve_handle is None:
            raise GblBridgeError("NUDGE_SENDER_UNAVAILABLE", ask_id)
        native_handle = self._resolve_handle(record["principal"])
        self._nudge_sender.send(ask_id, "ANSWERED", native_handle)
        self._store.append_ask_event(ask_id, {
            "type": "nudge", "state": "ANSWERED",
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")})
        return {"status": "RENUDGED", "ask_id": ask_id,
                "nudge_count": len(nudges) + 1}


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
        while self._serving:
            try:
                self.serve_once()
            except (OSError, GblBridgeError):
                return                  # listener closed or fatally broken

    def serve_once(self) -> bool:
        """Accept and serve exactly one connection.  False on accept
        timeout (nothing was served); raises OSError once the listener is
        closed."""
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
            response = self._admit_and_dispatch(connection)
            connection.sendall(encode_gbl_frame(response))
        finally:
            connection.close()
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
        if (set(request) != {"schema", "op", "arguments"}
                or request["schema"] != REQUEST_SCHEMA
                or type(request["arguments"]) is not dict):
            return self._error("REQUEST_INVALID")
        if request["op"] not in OPS:
            return self._error("UNKNOWN_OP", str(request["op"]))
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
            return self._error("INTERNAL_ERROR", type(exc).__name__)
        return {"schema": RESPONSE_SCHEMA, "ok": True, "result": result}

    @staticmethod
    def _error(code: str, detail: str = "") -> dict[str, Any]:
        return {"schema": RESPONSE_SCHEMA, "ok": False,
                "error": {"code": code, "detail": detail}}


_OP_METHODS = {
    "ask": "submit_ask",
    "answer": "post_answer",
    "result": "fetch_result",
    "question": "fetch_question",
    "status": "ask_status",
}

__all__ = [
    "DEFAULT_ADMISSION_TABLE",
    "OPS",
    "PrincipalAdmission",
    "RENUDGE_COOLDOWN_SECONDS",
    "BridgeServer",
    "BridgeServiceConfig",
    "GblAskStore",
    "GblBridge",
    "GblBridgeError",
    "GblCreateEffectUnknown",
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
]
