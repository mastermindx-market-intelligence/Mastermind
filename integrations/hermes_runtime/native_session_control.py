"""Finite Secretary operations on the existing native private control socket.

GatewayRunner owns this listener, executor, event loop, SessionAuthority,
tickets and persisted admissions. No TCP source bind, viewer daemon, retry,
session registry or replacement admission store is introduced here.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import threading

from .errors import RuntimeRefusal

VERB = "mastermind-secretary-v1"
SCHEMA = "mastermind.hermes_secretary_native_control/v1"
MAX_INPUT_BYTES = 16 * 1024
MAX_ANSWER_BYTES = 64 * 1024
MAX_WIRE_BYTES = 512 * 1024
_TARGET = frozenset({"profile_id", "session_id", "principal_id", "instance_id",
                     "authority_epoch", "revision", "execution_generation"})


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def input_digest(text: str) -> str:
    if (type(text) is not str or not text.strip()
            or len(text.encode("utf-8")) > MAX_INPUT_BYTES):
        raise RuntimeRefusal("NATIVE_SECRETARY_INPUT_INVALID")
    return hashlib.sha256(_canonical({"text": text, "finite": True})).hexdigest()


def _id(value):
    if (type(value) is not str or not value or len(value) > 1024
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise RuntimeRefusal("NATIVE_SECRETARY_ID_INVALID")
    return value


def validate_target(value) -> dict:
    if type(value) is not dict or set(value) != _TARGET:
        raise RuntimeRefusal("NATIVE_SECRETARY_TARGET_INVALID")
    for key in ("profile_id", "session_id", "principal_id", "instance_id"):
        _id(value[key])
    for key in ("authority_epoch", "revision", "execution_generation"):
        if type(value[key]) is not int or value[key] < (1 if key == "authority_epoch" else 0):
            raise RuntimeRefusal("NATIVE_SECRETARY_TARGET_INVALID")
    return dict(value)


def _result(status: str, **fields):
    return {"schema": SCHEMA, "status": status, **fields}


def _db(home: Path):
    from hermes_state import SessionDB
    return SessionDB(db_path=home / "state.db", read_only=True)


def _session(home: Path, session_id: str, principal: str):
    from hermes_state_local import local_receipt
    db = _db(home)
    try:
        row = db._read_one(
            "SELECT s.id,s.source,s.user_id,s.runtime_revision,s.runtime_generation,"
            "e.epoch AS authority_epoch FROM sessions s JOIN runtime_epoch e "
            "ON e.singleton=1 WHERE s.id=?", (session_id,))
        receipt = local_receipt(db, session_id)
        if row is None or type(receipt) is not dict:
            raise RuntimeRefusal("NATIVE_SECRETARY_SESSION_UNAVAILABLE")
        row = dict(row)
        if (row["id"] != session_id or row["user_id"] != principal
                or receipt.get("profile_id") != str(home)
                or receipt.get("session_id") != session_id
                or receipt.get("principal_id") != principal
                or (receipt.get("policy") or {}).get("source") == "acp"):
            raise RuntimeRefusal("NATIVE_SECRETARY_SESSION_MISMATCH")
        for key in ("runtime_revision", "runtime_generation", "authority_epoch"):
            if type(row[key]) is not int or row[key] < (1 if key == "authority_epoch" else 0):
                raise RuntimeRefusal("NATIVE_SECRETARY_SESSION_INVALID")
        return row
    finally:
        db.close()


def _target(runner, home: Path, session_id: str, principal: str):
    descriptor = runner.session_runtime_descriptor
    if descriptor.get("state") != "ready" or runner._draining:
        raise RuntimeRefusal("NATIVE_SECRETARY_NOT_READY")
    row = _session(home, session_id, principal)
    if row["authority_epoch"] != descriptor.get("authority_epoch"):
        raise RuntimeRefusal("NATIVE_SECRETARY_EPOCH_CHANGED")
    return dict(profile_id=str(home), session_id=session_id, principal_id=principal,
                instance_id=descriptor["instance_id"], authority_epoch=row["authority_epoch"],
                revision=row["runtime_revision"], execution_generation=row["runtime_generation"])


def _admission(row, home: Path, session_id: str, *, stored=False):
    if stored:
        result = {"admission_id": row["admission_id"],
                  "ref": {"profile_id": str(home), "session_id": row["target_session_id"]},
                  "sequence": row["seq"], "status": row["status"], "outcome": row["outcome"],
                  "authority_epoch": row["owner_epoch"], "execution_generation": row["generation"]}
    else:
        keys = {"admission_id", "ref", "sequence", "status", "outcome",
                "authority_epoch", "execution_generation"}
        if type(row) is not dict or not keys <= set(row):
            raise RuntimeRefusal("NATIVE_SECRETARY_RECEIPT_INVALID")
        result = {key: row[key] for key in keys}
    if (result["ref"] != {"profile_id": str(home), "session_id": session_id}
            or result["status"] not in {"queued", "started", "unknown", "terminal"}
            or type(result["sequence"]) is not int or result["sequence"] < 1
            or type(result["authority_epoch"]) is not int or result["authority_epoch"] < 1
            or (result["execution_generation"] is not None
                and (type(result["execution_generation"]) is not int or result["execution_generation"] < 0))
            or (result["outcome"] is not None and type(result["outcome"]) is not str)):
        raise RuntimeRefusal("NATIVE_SECRETARY_RECEIPT_MISMATCH")
    _id(result["admission_id"])
    return result


def _read_original(home: Path, params, principal: str):
    from hermes_state_runtime import find_session_admission, get_session_admission
    from gateway.session_results import admission_result
    required = {"operation", "profile_id", "session_id", "submission_id", "input_sha256", "admission_id"}
    if set(params) != required or params["profile_id"] != str(home):
        raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
    sid, submission = _id(params["session_id"]), _id(params["submission_id"])
    db = _db(home)
    try:
        if params["admission_id"] is None:
            row = find_session_admission(db, principal_id=principal, session_id=sid, request_id=submission)
        else:
            row = get_session_admission(db, admission_id=_id(params["admission_id"]))
        if row is None:
            # Active-row absence is not proof of nonexecution or permission to resend.
            return _result("EFFECT_UNKNOWN")
        if (row.get("principal_id") != principal or row.get("target_session_id") != sid
                or row.get("request_id") != submission or row.get("intent") != "queue"
                or type(row.get("payload")) is not dict or set(row["payload"]) != {"text", "finite"}
                or row["payload"].get("finite") is not True
                or input_digest(row["payload"].get("text")) != params["input_sha256"]):
            raise RuntimeRefusal("NATIVE_SECRETARY_ORIGINAL_MISMATCH")
        receipt = _admission(row, home, sid, stored=True)
        result = _result("OBSERVED", admission=receipt)
        saved = admission_result(db, receipt["admission_id"])
        if saved is not None and receipt["status"] == "terminal":
            value = saved.get("result")
            answer = value.get("final_response") if type(value) is dict else None
            if (type(answer) is str and len(answer.encode("utf-8")) <= MAX_ANSWER_BYTES
                    and not any(ord(c) < 32 and c not in "\n\r\t" for c in answer)):
                result["answer"] = answer
                result["successful"] = not any(value.get(key) for key in ("failed", "error", "interrupted"))
        return result
    finally:
        db.close()


class _ReceiptStream:
    """Capped ephemeral sink for native events; results stay in native storage.

    StdioTransport supplies serialization and the caller supplies its lock.
    No transcript is retained or acknowledged as a product/UI delivery.
    """

    def __init__(self):
        self.bytes = 0
        self.closed = False

    def write(self, text):
        size = len(text.encode("utf-8"))
        if self.closed or self.bytes + size > MAX_WIRE_BYTES:
            self.closed = True
            raise BrokenPipeError("receipt transport closed")
        self.bytes += size
        return len(text)

    def flush(self):
        if self.closed:
            raise BrokenPipeError("receipt transport closed")

    def close(self):
        self.closed = True


class _AdmissionRefused(RuntimeRefusal):
    """The existing native transaction refused before any new admission."""


def _admission_guard(authority, actor, target):
    frozen = validate_target(target)

    def authorize(conn):
        # Called inside the incumbent native admission transaction. No new
        # connection, lock, queue, network operation, or external side effect.
        from hermes_state_mutation_guards import require_idle
        from hermes_state_mutation_prepared import local_snapshot
        try:
            if (authority.profile_id != frozen["profile_id"]
                    or authority.instance_id != frozen["instance_id"]
                    or authority.epoch != frozen["authority_epoch"]
                    or actor.subject != frozen["principal_id"]):
                raise ValueError("authority changed")
            row = conn.execute(
                "SELECT user_id,runtime_revision,runtime_generation FROM sessions WHERE id=?",
                (frozen["session_id"],)).fetchone()
            if (row is None or row["user_id"] != frozen["principal_id"]
                    or row["runtime_revision"] != frozen["revision"]
                    or row["runtime_generation"] != frozen["execution_generation"]):
                raise ValueError("session changed")
            snapshot = local_snapshot(authority.db, conn, frozen["session_id"])
            receipt = snapshot["receipt"]
            if (snapshot["target"] != frozen["session_id"]
                    or receipt.get("profile_id") != frozen["profile_id"]
                    or receipt.get("session_id") != frozen["session_id"]
                    or receipt.get("principal_id") != frozen["principal_id"]
                    or (receipt.get("policy") or {}).get("source") == "acp"):
                raise ValueError("native lineage changed")
            # Includes native admissions, workers, transcript leases and
            # compression. The incumbent owner supplies all busy semantics.
            require_idle(authority.db, conn, [frozen["session_id"]])
        except Exception:
            raise _AdmissionRefused("NATIVE_SECRETARY_ADMISSION_FENCE") from None

    return authorize


async def _submit(runner, home, params, principal):
    from gateway.session_controls import AuthorityConnection
    from gateway.run_api import _embedded_chat_enabled
    from gateway.session_authorities import owner_scope
    from gateway.run_idle_exit import attached_client
    from tui_gateway.transport import StdioTransport, bind_transport, reset_transport
    try:
        target = validate_target(params["target"])
        observed = await asyncio.to_thread(_target, runner, home, target["session_id"], principal)
    except (RuntimeRefusal, OSError, ValueError, KeyError):
        return _result("REFUSED", reason="TARGET_UNAVAILABLE")
    if target != observed or not _embedded_chat_enabled():
        return _result("REFUSED", reason="TARGET_UNAVAILABLE")
    try:
        grant = runner.session_ticket_store.redeem(params["ticket"], profile_id=str(home), purpose="interactive")
    except PermissionError:
        return _result("REFUSED", reason="TICKET_REFUSED")
    if (grant.get("subject") != principal or grant.get("scope") != "profile"
            or grant.get("instance_id") != target["instance_id"]):
        return _result("REFUSED", reason="TICKET_MISMATCH")
    identity = {"user_id": grant["subject"], "provider": "local", "profile_id": grant["profile_id"],
                "instance_id": grant["instance_id"], "capabilities": grant["capabilities"],
                "native_bootstrap": True, "profile_scope": "profile"}
    stream, lock = _ReceiptStream(), threading.Lock()
    transport = StdioTransport(lambda: stream, lock)
    with owner_scope(runner.session_authority), attached_client(runner):
        token = bind_transport(transport)
        connection = None
        try:
            connection = AuthorityConnection(runner.session_authority, transport, identity, operator=False)
            async with asyncio.timeout(20):
                resumed = await connection.dispatch({"jsonrpc": "2.0", "id": 1, "method": "session.resume",
                                                     "params": {"session_id": target["session_id"]}})
                value = resumed.get("result", {})
                if ("error" in resumed or value.get("session_id") != target["session_id"]
                        or value.get("stored_session_id") != target["session_id"]
                        or value.get("authority_epoch") != target["authority_epoch"]
                        or value.get("revision") != target["revision"]
                        or value.get("execution_generation") != target["execution_generation"]):
                    return _result("NOT_SUBMITTED", reason="TARGET_CHANGED_AFTER_RESUME")
                from dataclasses import asdict
                from gateway.session_contract import SessionRef
                ref = SessionRef(connection.actor.profile_id, target["session_id"])
                submission = connection.submission(ref, {
                    "session_id": target["session_id"], "submission_id": params["submission_id"],
                    "text": params["text"], "finite": True})
                # Use the native finite-admission API with its transactional
                # guard. Interactive voice-stop shortcuts do not apply here.
                receipt = await connection.authority.submit(
                    connection.actor, submission,
                    _authorize_write=_admission_guard(connection.authority, connection.actor, target),
                    queue_while_restarting=False)
                return _result("ADMITTED", admission=_admission(asdict(receipt), home, target["session_id"]))
        except _AdmissionRefused:
            return _result("NOT_SUBMITTED", reason="TARGET_CHANGED_BEFORE_ADMISSION")
        except Exception:
            return _result("EFFECT_UNKNOWN")
        finally:
            try:
                if connection is not None:
                    # Native detach only: no session close/cancel/end_reason.
                    await connection.close()
            finally:
                with lock:
                    stream.close()
                transport.close()
                reset_transport(token)


def install_private_control(runner, home: Path, role: str) -> None:
    if role != "mmsecretary":
        return
    server = runner.session_control_server
    if VERB in server.private_handlers:
        raise RuntimeRefusal("NATIVE_SECRETARY_CONTROL_ALREADY_INSTALLED")
    loop = asyncio.get_running_loop()

    def handle(params, peer_subject):
        if peer_subject != f"uid:{os.getuid()}" or type(params) is not dict:
            return _result("REFUSED", reason="PEER_REFUSED")
        operation = params.get("operation")
        try:
            if operation == "observe":
                if set(params) != {"operation", "profile_id", "session_id"} or params["profile_id"] != str(home):
                    raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
                return _result("TARGET", target=_target(runner, home, _id(params["session_id"]), peer_subject))
            if operation == "read_original":
                return _read_original(home, params, peer_subject)
            if operation != "submit" or set(params) != {"operation", "target", "submission_id", "text", "ticket"}:
                raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
            _id(params["submission_id"])
            input_digest(params["text"])
            if type(params["ticket"]) is not str or not 1 <= len(params["ticket"]) <= 256:
                raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
        except Exception:
            return _result("UNAVAILABLE" if operation in {"observe", "read_original"} else "REFUSED")
        # This is the native control server's existing executor. The native
        # loop owns the bounded coroutine; never create a new event loop.
        coroutine = _submit(runner, home, params, peer_subject)
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except Exception:
            coroutine.close()
            return _result("REFUSED", reason="OWNER_LOOP_UNAVAILABLE")
        try:
            return future.result(timeout=25)
        except Exception:
            # Do not cancel/replay an admission when the control response is lost.
            return _result("EFFECT_UNKNOWN")

    server.private_handlers[VERB] = handle


class NativeSecretaryClient:
    """Actual selected same-UID native client; each operation sends once."""

    def __init__(self, home: Path, *, expected_pid: int | None = None):
        self.home = home.resolve(strict=True)
        if expected_pid is not None and (type(expected_pid) is not int or expected_pid <= 0):
            raise RuntimeRefusal("NATIVE_SECRETARY_OWNER_INVALID")
        self.expected_pid = expected_pid

    def _identify(self):
        from hermes_cli.gateway_runtime_discovery import query_identify
        from hermes_cli.gateway_runtime import _endpoint
        payload = query_identify(self.home, timeout=2)
        if self.expected_pid is not None and (
                type(payload) is not dict or type(payload.get("pid")) is not int
                or payload["pid"] != self.expected_pid or payload.get("hermes_home") != str(self.home)):
            raise RuntimeRefusal("NATIVE_SECRETARY_OWNER_CHANGED")
        return _endpoint(payload, self.home)

    def dispatch(self, request: dict):
        """Closed role-gateway consumer; no native ticket is accepted on HTTP."""
        if type(request) is not dict:
            raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
        operation = request.get("operation")
        if operation == "observe" and set(request) == {"operation", "session_id"}:
            return self.observe(request["session_id"])
        if operation == "submit" and set(request) == {"operation", "target", "submission_id", "text"}:
            return self.submit(request["target"], request["submission_id"], request["text"])
        if operation == "read_original" and set(request) == {
            "operation", "session_id", "submission_id", "input_sha256", "admission_id"
        }:
            digest = request["input_sha256"]
            if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
            if request["admission_id"] is not None:
                _id(request["admission_id"])
            return self.read_original(**{key: value for key, value in request.items() if key != "operation"})
        raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")

    def _call(self, params):
        from hermes_cli.gateway_runtime_discovery import connect_private
        if self.expected_pid is not None:
            observed = self._identify()
            if observed.state != "ready" or observed.endpoint is None:
                raise RuntimeRefusal("NATIVE_SECRETARY_OWNER_CHANGED")
        request = _canonical({"protocol": 1, "id": 1, "verb": VERB, "params": params}) + b"\n"
        if len(request) > 64 * 1024:
            raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_TOO_LARGE")
        deadline = time.monotonic() + 30
        with connect_private(self.home, 5) as peer:
            peer.sendall(request)
            raw = bytearray()
            while b"\n" not in raw:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                peer.settimeout(remaining)
                data = peer.recv(min(65536, MAX_WIRE_BYTES + 1 - len(raw)))
                if not data or len(raw) + len(data) > MAX_WIRE_BYTES:
                    raise RuntimeRefusal("NATIVE_SECRETARY_RESPONSE_INVALID")
                raw.extend(data)
        response = json.loads(raw)
        value = response.get("result")
        if (response.get("ok") is not True or response.get("protocol") != 1 or response.get("id") != 1
                or type(value) is not dict or value.get("schema") != SCHEMA):
            raise RuntimeRefusal("NATIVE_SECRETARY_RESPONSE_INVALID")
        return value

    def observe(self, session_id: str):
        return self._call({"operation": "observe", "profile_id": str(self.home), "session_id": _id(session_id)})

    def submit(self, target: dict, submission_id: str, text: str):
        input_digest(text)
        target = validate_target(target)
        _id(submission_id)
        from hermes_cli.gateway_client import _session_ticket
        observed = self._identify()
        endpoint = observed.endpoint
        if (observed.state != "ready" or endpoint is None or type(target) is not dict
                or set(target) != _TARGET or endpoint.profile_id != target["profile_id"]
                or endpoint.instance_id != target["instance_id"]
                or endpoint.authority_epoch != target["authority_epoch"]):
            return _result("REFUSED", reason="TARGET_CHANGED")
        ticket = _session_ticket(self.home, endpoint)
        try:
            return self._call({"operation": "submit", "target": target,
                               "submission_id": _id(submission_id), "text": text, "ticket": ticket})
        except Exception:
            return _result("EFFECT_UNKNOWN")

    def read_original(self, *, session_id, submission_id, input_sha256, admission_id=None):
        return self._call({"operation": "read_original", "profile_id": str(self.home),
                           "session_id": _id(session_id), "submission_id": _id(submission_id),
                           "input_sha256": input_sha256, "admission_id": admission_id})
