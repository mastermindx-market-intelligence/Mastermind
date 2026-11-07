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

from .constants import conversation_contract


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


def _result(status: str, *, role: str = "mmsecretary", **fields):
    return {"schema": conversation_contract(role).native_schema, "status": status, **fields}


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


def _terminal_metadata(value: dict, answer: str | None) -> dict:
    """Bounded projection of the original stored result, not EVAL qualification.

    Omitted fields stay omitted; false is not confused with missing. Model
    labels are configured/reported labels, never proof of the serving model.
    Do not forward reasoning, history, raw errors, tools or served_model:
    upstream's latter field can contain a proxy address or a fallback hint.
    """
    reported, invalid = {}, []
    for key in ("completed", "failed", "partial", "interrupted",
                "response_transformed", "response_previewed", "response_reused"):
        if key in value:
            if type(value[key]) is bool:
                reported[key] = value[key]
            else:
                invalid.append(key)
    for key in ("session_id", "model", "requested_model", "provider", "turn_exit_reason"):
        if key not in value:
            continue
        item = value[key]
        if item is None:
            reported[key] = None
            continue
        valid = (type(item) is str and len(item) <= 256
                 and not any(ord(c) < 32 or ord(c) == 127 for c in item))
        if valid:
            try:
                valid = len(item.encode("utf-8")) <= 256
            except UnicodeEncodeError:
                valid = False
        if valid:
            reported[key] = item
        else:
            invalid.append(key)
    if "api_calls" in value:
        count = value["api_calls"]
        if type(count) is int and 0 <= count <= 2**53 - 1:
            reported["api_calls"] = count
        else:
            invalid.append("api_calls")
    output = None
    if answer is not None:
        raw = answer.encode("utf-8")
        output = {"stage": "retained_redacted_final_response",
                  "sha256": hashlib.sha256(raw).hexdigest(), "utf8_bytes": len(raw)}
    return {"schema": "mastermind.hermes_native_terminal_metadata/v1",
            "reported": reported, "invalid_fields": invalid, "output": output,
            "model_identity_verified": False}


def _request_observation(value, *, receipt: dict, role: str) -> dict:
    """Project one whole retained outer document after the original receipt join.

    This validates bounded owner metadata, not the original content digest,
    provider delivery, historical process attestation or model identity.
    """
    from .native_request_observation import (
        SCHEMA as observation_schema, PREVIOUS_SCHEMA, LEGACY_SCHEMA, STAGE, CONTENT_FIELDS,
        TOOLS_STAGE, TOOL_COVERAGE, TOOL_IDENTIFIERS, TOOL_ERRORS, CANONICALIZATION,
        MAX_CONTENT_BYTES, MAX_EVENTS, MAX_TOOL_EVENTS, MAX_METADATA_BYTES,
    )

    def refuse():
        raise ValueError("INVALID_RETAINED_OBSERVATION")

    def shape(item, required, optional=()):
        if type(item) is not dict or not len(required) <= len(item) <= len(required) + len(optional):
            refuse()
        allowed = set(required) | set(optional)
        if any(type(key) is not str or key not in allowed for key in item) or not set(required) <= item.keys():
            refuse()

    def text(item):
        if (type(item) is not str or not 0 < len(item) <= 256
                or any(ord(char) < 32 or ord(char) == 127 for char in item)):
            refuse()
        if len(item.encode("utf-8", "strict")) > 256:
            refuse()
        return item

    def integer(item, minimum=0):
        if type(item) is not int or not minimum <= item <= 2**53 - 1:
            refuse()
        return item

    def literal(item, expected):
        return type(item) is str and item == expected

    def digest_text(item):
        if type(item) is not str or len(item) != 64 or any(char not in "0123456789abcdef" for char in item):
            refuse()
        return item

    def tools_projection(item):
        if type(item) is not dict:
            refuse()
        status = item.get("status")
        if literal(status, "absent"):
            shape(item, ("status",))
            return {"status": status}
        if literal(status, "unavailable"):
            shape(item, ("status", "reason"))
            if type(item["reason"]) is not str or item["reason"] not in {
                    "content_limit", "unsupported_content", "observation_failed"}:
                refuse()
            return dict(item)
        shape(item, ("status", "kind", "sha256", "bytes", "canonicalization"))
        if (not literal(status, "observed") or type(item["kind"]) is not str
                or item["kind"] not in {"null", "boolean", "number", "string", "array", "object"}
                or not literal(item["canonicalization"], CANONICALIZATION)
                or not 1 <= integer(item["bytes"]) <= MAX_CONTENT_BYTES):
            refuse()
        return dict(item, sha256=digest_text(item["sha256"]))

    fields = ("schema", "stage", "scope", "observations", "errors", "overflow", "coverage",
              "provider_dispatch_proven", "model_identity_verified")
    v3 = type(value) is dict and literal(value.get("schema"), observation_schema)
    v2 = v3 or type(value) is dict and literal(value.get("schema"), PREVIOUS_SCHEMA)
    if v2:
        fields += ("tools_stage", "tool_coverage", "executions", "commits", "tool_overflow", "metadata_overflow")
    if v3:
        fields += ("transport",)
    shape(value, fields)
    selected_schema = observation_schema if v3 else PREVIOUS_SCHEMA if v2 else LEGACY_SCHEMA
    if (not literal(value["schema"], selected_schema) or not literal(value["stage"], STAGE)
            or value["provider_dispatch_proven"] is not False or value["model_identity_verified"] is not False
            or type(value["overflow"]) is not bool):
        refuse()
    source_scope = value["scope"]
    scope_fields = ("role", "session_id", "admission_id", "authority_epoch", "execution_generation", "instance_id")
    shape(source_scope, scope_fields)
    scope = {key: text(source_scope[key]) for key in ("role", "session_id", "admission_id", "instance_id")}
    scope["authority_epoch"] = integer(source_scope["authority_epoch"], 1)
    scope["execution_generation"] = integer(source_scope["execution_generation"])
    if (scope["role"] != role or scope["session_id"] != receipt["ref"]["session_id"]
            or scope["admission_id"] != receipt["admission_id"]
            or scope["authority_epoch"] != receipt["authority_epoch"]
            or scope["execution_generation"] != receipt["execution_generation"]):
        refuse()
    # instance_id describes the original producer. Never join it to today's
    # process or replace it with the implementation serving this historical read.
    source_events = value["observations"]
    if type(source_events) is not list or len(source_events) > MAX_EVENTS:
        refuse()
    events = []
    required = ("fields", "content_sha256", "content_bytes", "canonicalization")
    if v2:
        required += ("tools",)
    identifiers = ("turn_id", "api_request_id", "agent_session_id")
    counters = ("api_call_count", "retry_count")
    optional = (*identifiers, *counters, "invalid_fields")
    for source in source_events:
        shape(source, required, optional)
        selected = source["fields"]
        if (type(selected) is not list or len(selected) > len(CONTENT_FIELDS)
                or any(type(key) is not str or key not in CONTENT_FIELDS for key in selected)
                or selected != [key for key in CONTENT_FIELDS if key in selected]):
            refuse()
        digest, size = source["content_sha256"], source["content_bytes"]
        if (type(digest) is not str or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
                or type(size) is not int or not 2 <= size <= MAX_CONTENT_BYTES
                or not literal(source["canonicalization"], "json_sorted_keys_utf8_no_spaces_v1")):
            refuse()
        event = {"fields": list(selected), "content_sha256": digest, "content_bytes": size,
                 "canonicalization": "json_sorted_keys_utf8_no_spaces_v1"}
        if v2:
            event["tools"] = tools_projection(source["tools"])
        for key in identifiers:
            if key in source: event[key] = text(source[key])
        for key in counters:
            if key in source: event[key] = integer(source[key])
        if "invalid_fields" in source:
            invalid = source["invalid_fields"]
            if (type(invalid) is not list or not 1 <= len(invalid) <= len(identifiers) + len(counters)
                    or any(type(key) is not str or key not in (*identifiers, *counters) or key in source for key in invalid)
                    or len(set(invalid)) != len(invalid)):
                refuse()
            event["invalid_fields"] = list(invalid)
        events.append(event)
    errors = value["errors"]
    allowed_errors = ("unbound_or_stale_agent", "content_limit", "unsupported_content", "observation_failed")
    if v2:
        allowed_errors += TOOL_ERRORS
    if (type(errors) is not list or len(errors) > len(allowed_errors)
            or any(type(error) is not str or error not in allowed_errors for error in errors)
            or errors != sorted(set(errors))
            or not literal(value["coverage"], "assembly_hooks_only" if events else "no_assembly_observation")
            or not v2 and value["overflow"] and len(events) != MAX_EVENTS):
        refuse()
    projected = {"schema": selected_schema, "stage": STAGE, "scope": scope,
        "observations": events, "errors": list(errors), "overflow": value["overflow"],
        "coverage": value["coverage"], "provider_dispatch_proven": False, "model_identity_verified": False}
    transport = None
    if v3:
        from .native_transport_observation import validate_document
        transport = validate_document(value["transport"])
        projected["transport"] = transport
    if v2:
        if (not literal(value["tools_stage"], TOOLS_STAGE) or not literal(value["tool_coverage"], TOOL_COVERAGE)
                or type(value["tool_overflow"]) is not bool or type(value["metadata_overflow"]) is not bool
                or value["metadata_overflow"] and not (value["overflow"] or value["tool_overflow"]
                    or transport is not None and transport["overflow"])
                or value["overflow"] and not value["metadata_overflow"] and len(events) != MAX_EVENTS):
            refuse()

        sequences = set()
        def tool_records(source_records, *, commit):
            if type(source_records) is not list or len(source_records) > MAX_TOOL_EVENTS:
                refuse()
            output, previous = [], 0
            for source in source_records:
                required = ("sequence", "identity", "invalid_fields", "state")
                optional = ()
                if commit:
                    required += ("correlation",)
                    optional = ("blocked", "is_error", "reported_effect_disposition")
                shape(source, required, optional)
                sequence = integer(source["sequence"], 1)
                if sequence > 2 * MAX_TOOL_EVENTS or sequence <= previous or sequence in sequences:
                    refuse()
                sequences.add(sequence)
                previous = sequence
                identity = source["identity"]
                shape(identity, (), TOOL_IDENTIFIERS)
                identity = {key: text(item) for key, item in identity.items()}
                states = ({"pending", "commit_tuple_returned", "commit_none_returned", "raised", "unrecognized_return"}
                          if commit else {"entered", "returned", "raised"})
                if type(source["state"]) is not str or source["state"] not in states:
                    refuse()
                invalid = source["invalid_fields"]
                invalid_names = (*TOOL_IDENTIFIERS, *optional)
                if (type(invalid) is not list or len(invalid) > len(invalid_names)
                        or any(type(key) is not str or key not in invalid_names for key in invalid)
                        or len(set(invalid)) != len(invalid)
                        or any(key in identity or key in source for key in invalid)):
                    refuse()
                record = {"sequence": sequence, "identity": identity, "invalid_fields": list(invalid), "state": source["state"]}
                if commit:
                    for key in ("blocked", "is_error"):
                        if key in source:
                            if type(source[key]) is not bool:
                                refuse()
                            record[key] = source[key]
                        elif key not in invalid:
                            refuse()
                    key = "reported_effect_disposition"
                    if key in source:
                        item = source[key]
                        if item is not None and (type(item) is not str or item not in {"none", "unknown"}):
                            refuse()
                        record[key] = item
                    elif key not in invalid:
                        refuse()
                    correlation = source["correlation"]
                    shape(correlation, ("status",), ("execution_sequence",))
                    status = correlation["status"]
                    if type(status) is not str or status not in {"incomplete_identity", "coverage_limited",
                            "ambiguous_identity", "callback_not_observed", "invalid_order", "unique_identity_match"}:
                        refuse()
                    if (status == "unique_identity_match") != ("execution_sequence" in correlation):
                        refuse()
                    record["correlation"] = {"status": status}
                    if "execution_sequence" in correlation:
                        record["correlation"]["execution_sequence"] = integer(correlation["execution_sequence"], 1)
                output.append(record)
            return output

        executions = tool_records(value["executions"], commit=False)
        commits = tool_records(value["commits"], commit=True)
        if (sequences != set(range(1, len(sequences) + 1)) or value["tool_overflow"]
                and not value["metadata_overflow"] and max(len(executions), len(commits)) != MAX_TOOL_EVENTS):
            refuse()
        def key(record):
            identity = record["identity"]
            return tuple(identity[name] for name in TOOL_IDENTIFIERS) if set(identity) == set(TOOL_IDENTIFIERS) else None
        limited = (value["tool_overflow"] or value["metadata_overflow"]
                   or bool(set(errors) & {*TOOL_ERRORS, "unbound_or_stale_agent"})
                   or any(key(record) is None for record in (*executions, *commits)))
        for commit in commits:
            identity = key(commit)
            matches = [record for record in executions if identity is not None and key(record) == identity]
            repeated = [record for record in commits if identity is not None and key(record) == identity]
            if identity is None:
                expected = "incomplete_identity"
            elif limited:
                expected = "coverage_limited"
            elif len(matches) > 1 or len(repeated) > 1:
                expected = "ambiguous_identity"
            elif not matches:
                expected = "callback_not_observed"
            elif matches[0]["sequence"] >= commit["sequence"]:
                expected = "invalid_order"
            else:
                expected = "unique_identity_match"
            if commit["correlation"]["status"] != expected:
                refuse()
            if expected == "unique_identity_match" and commit["correlation"]["execution_sequence"] != matches[0]["sequence"]:
                refuse()
        projected.update(tools_stage=TOOLS_STAGE, tool_coverage=TOOL_COVERAGE, executions=executions,
                         commits=commits, tool_overflow=value["tool_overflow"], metadata_overflow=value["metadata_overflow"])
    if len(json.dumps(projected, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_METADATA_BYTES:
        refuse()
    return projected


def _read_original(home: Path, params, principal: str, *, role: str = "mmsecretary"):
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
            return _result("EFFECT_UNKNOWN", role=role)
        if (row.get("principal_id") != principal or row.get("target_session_id") != sid
                or (params["admission_id"] is not None and row.get("admission_id") != params["admission_id"])
                or row.get("request_id") != submission or row.get("intent") != "queue"
                or type(row.get("payload")) is not dict or set(row["payload"]) != {"text", "finite"}
                or row["payload"].get("finite") is not True
                or input_digest(row["payload"].get("text")) != params["input_sha256"]):
            raise RuntimeRefusal("NATIVE_SECRETARY_ORIGINAL_MISMATCH")
        receipt = _admission(row, home, sid, stored=True)
        result = _result("OBSERVED", role=role, admission=receipt)
        saved = admission_result(db, receipt["admission_id"])
        if type(saved) is dict and receipt["status"] == "terminal":
            value = saved.get("result")
            answer = value.get("final_response") if type(value) is dict else None
            valid_answer = (type(answer) is str and len(answer) <= MAX_ANSWER_BYTES
                            and not any(ord(c) < 32 and c not in "\n\r\t" for c in answer))
            if valid_answer:
                try:
                    valid_answer = len(answer.encode("utf-8")) <= MAX_ANSWER_BYTES
                except UnicodeEncodeError:
                    valid_answer = False
            if valid_answer:
                result["answer"] = answer
                result["successful"] = not any(value.get(key) for key in ("failed", "error", "interrupted"))
            if type(value) is dict:
                result["terminal_metadata"] = _terminal_metadata(value, answer if valid_answer else None)
            if "mastermind_request_observation" in saved:
                try:
                    result["request_observation"] = _request_observation(
                        saved["mastermind_request_observation"], receipt=receipt, role=role)
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    # Close only the evidence projection. Preserve the original
                    # answer, native outcome and existing terminal metadata.
                    result["request_observation_error"] = "INVALID_RETAINED_OBSERVATION"
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


async def _submit(runner, home, params, principal, *, role: str = "mmsecretary"):
    def result(status, **fields):
        return _result(status, role=role, **fields)
    from gateway.session_controls import AuthorityConnection
    from gateway.run_api import _embedded_chat_enabled
    from gateway.session_authorities import owner_scope
    from gateway.run_idle_exit import attached_client
    from tui_gateway.transport import StdioTransport, bind_transport, reset_transport
    try:
        target = validate_target(params["target"])
        observed = await asyncio.to_thread(_target, runner, home, target["session_id"], principal)
    except (RuntimeRefusal, OSError, ValueError, KeyError):
        return result("REFUSED", reason="TARGET_UNAVAILABLE")
    if target != observed or not _embedded_chat_enabled():
        return result("REFUSED", reason="TARGET_UNAVAILABLE")
    try:
        grant = runner.session_ticket_store.redeem(params["ticket"], profile_id=str(home), purpose="interactive")
    except PermissionError:
        return result("REFUSED", reason="TICKET_REFUSED")
    if (grant.get("subject") != principal or grant.get("scope") != "profile"
            or grant.get("instance_id") != target["instance_id"]):
        return result("REFUSED", reason="TICKET_MISMATCH")
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
                    return result("NOT_SUBMITTED", reason="TARGET_CHANGED_AFTER_RESUME")
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
                return result("ADMITTED", admission=_admission(asdict(receipt), home, target["session_id"]))
        except _AdmissionRefused:
            return result("NOT_SUBMITTED", reason="TARGET_CHANGED_BEFORE_ADMISSION")
        except Exception:
            return result("EFFECT_UNKNOWN")
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



ENROLLMENT_SCHEMA = "mastermind.hermes_secretary_session_enrollment/v1"
ENROLLMENT_RESULT_SCHEMA = "mastermind.hermes_secretary_enrollment_result/v1"
_ENROLLMENT_STATUSES = frozenset({"ENROLLED", "ABSENT", "REFUSED", "UNAVAILABLE", "EFFECT_UNKNOWN"})

# The one native extension tool the qualified consumer may install. It is a
# model-facing tool of the plugin, not an MCP server tool: the raw Executive
# tools of that server stay non-model-facing.
CONSUMER_EXTENSION_TOOL = "mmx_delegate"

# The process-local held-release owner identity. It is bound exactly once, by
# the native gateway entry that entered this process through the held
# release, and it is what the plugin loader checks the owner-private
# consumer slot against. It is never replaced and never derived from a role
# label.
_RUNTIME_OWNER: str | None = None
_RUNTIME_OWNER_LOCK = threading.Lock()


def install_runtime_owner(implementation_sha: str) -> str:
    """Bind this process's held-release owner identity, exactly once."""
    global _RUNTIME_OWNER
    value = _implementation(implementation_sha)
    with _RUNTIME_OWNER_LOCK:
        if _RUNTIME_OWNER is None:
            _RUNTIME_OWNER = value
        elif _RUNTIME_OWNER != value:
            raise RuntimeRefusal("NATIVE_RUNTIME_OWNER_CONFLICT")
    return _RUNTIME_OWNER


def current_runtime_owner() -> str | None:
    """The held-release owner identity of this process, when it is bound."""
    return _RUNTIME_OWNER


def _callable_identity(value) -> str | None:
    """A stable identity for one registered callable, never its source."""
    if value is None:
        return None
    module = getattr(value, "__module__", None)
    name = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
    if type(module) is not str or type(name) is not str:
        return None
    return f"{module}:{name}"


def _consumer_extension(runner, home: Path) -> dict:
    """Prove this slot's exact C28 registration in the live native scope."""
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    from integrations.hermes_harness.native_executive_consumer import (
        CONSUMER_SLOT_ATTRIBUTE, CONSUMER_PLUGIN_NAME, ConsumerSlot,
        NativeConsumerCurrentness, schema_digest, selected_child_publication)
    from integrations.hermes_harness.native_tool_registration import NATIVE_TOOL_SCHEMA
    descriptor = runner.session_runtime_descriptor
    if descriptor.get("state") != "ready" or runner._draining:
        raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_NOT_READY")
    manager = get_plugin_manager()
    slot = getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None)
    if not isinstance(slot, ConsumerSlot):
        raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")
    with slot._lock:
        registration = slot.registration
        binding = slot.delegate_binding
        loaded = getattr(manager, "_plugins", {}).get(CONSUMER_PLUGIN_NAME)
        if (slot.manager is not manager or slot.scope != manager.scope_key
                or slot.owner != current_runtime_owner() or str(slot.scope) != str(home)
                or slot.load_outcome != "REGISTERED" or slot.registration_error is not None
                or registration is None or binding is None
                or loaded is not slot.loader_record or loaded is None
                or getattr(loaded, "enabled", None) is not True
                or getattr(loaded, "error", None) is not None
                or getattr(slot.registration_context, "_manager", None) is not manager):
            raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")
    guard = binding.currentness_guard
    publication = selected_child_publication(slot.publication)
    if publication is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")
    if (not isinstance(guard, NativeConsumerCurrentness) or guard() is not True
            or guard.session_id != binding.session_id
            or guard.instance_id != descriptor.get("instance_id")
            or guard.authority_epoch != descriptor.get("authority_epoch")
            or registration.scope != slot.scope
            or registration.profile_id != binding.profile_id
            or registration.profile_id != slot.profile_id
            or registration.session_id != binding.session_id
            or registration.command != publication.command
            or registration.job_id != publication.job_id):
        raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")

    def matches(entry):
        return (entry is not None and entry.handler is registration.handler
                and entry.check_fn is registration.check_fn
                and entry.toolset == registration.toolset
                and entry.schema == NATIVE_TOOL_SCHEMA)
    if not matches(registry.snapshot_registration(CONSUMER_EXTENSION_TOOL, scope=slot.scope)):
        raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")
    if guard() is not True or registration.check_fn() is not True:
        raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")
    with slot._lock:
        if (slot.registration is not registration or slot.delegate_binding is not binding
                or slot.load_outcome != "REGISTERED"
                or getattr(manager, "_plugins", {}).get(CONSUMER_PLUGIN_NAME) is not loaded
                or getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None) is not slot):
            raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")
    if not matches(registry.snapshot_registration(CONSUMER_EXTENSION_TOOL, scope=slot.scope)):
        raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_UNAVAILABLE")
    return {
        "tool": CONSUMER_EXTENSION_TOOL, "scope": slot.scope, "profile_id": str(home),
        "present": True, "toolset": registration.toolset,
        "schema_sha256": schema_digest(NATIVE_TOOL_SCHEMA),
        "implementation_sha": slot.owner,
        "instance_id": guard.instance_id, "authority_epoch": guard.authority_epoch,
        "enrollment_request_id": publication.session.request_id,
        "principal_id": publication.session.principal_id, "session_id": binding.session_id,
        "command_id": publication.command, "job_id": publication.job_id,
        "target_digest": publication.target_digest,
        "principal_binding_digest": publication.principal_binding_digest,
        "authority_generation_digest": publication.authority_generation_digest,
        "capability_profile_digest": publication.capability_profile_digest,
        "plugin_sha256": publication.plugin.digest,
        "mcp_tools_schema_sha256": publication.tools_schema_digest,
    }



def _consumer_capabilities(runner, home: Path) -> dict:
    """Read v2 capability stages from this same native process and enrollment."""
    from hermes_cli.plugins import get_plugin_manager
    from integrations.hermes_harness.native_executive_consumer import (
        CONSUMER_SLOT_ATTRIBUTE, ConsumerSlot, ExecutiveContextConsumerPublication,
        selected_child_publication)
    from .native_agentos_memory import NativeAgentOsMemoryFactory, validate_consumer_readback
    manager = get_plugin_manager()
    slot = getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None)
    descriptor = runner.session_runtime_descriptor
    if (not isinstance(slot, ConsumerSlot) or type(slot.publication) is not ExecutiveContextConsumerPublication
            or type(slot.memory_factory) is not NativeAgentOsMemoryFactory
            or slot.manager is not manager or slot.owner != current_runtime_owner()
            or str(slot.scope) != str(home) or descriptor.get("state") != "ready" or runner._draining):
        raise RuntimeRefusal("NATIVE_AGENTOS_READBACK_UNAVAILABLE")
    publication = slot.publication
    def enrollment():
        value = read_enrolled_session(runner, home, slot.owner, publication.session.request_id,
                                      publication.session.principal_id, role=publication.session.role)
        if value["status"] != "ENROLLED":
            raise RuntimeRefusal("NATIVE_AGENTOS_READBACK_UNAVAILABLE")
        return value["target"]
    before = enrollment()
    expected = {"implementation_sha": slot.owner,
        "publication_sha256": slot.memory_factory.publication_sha256, "profile_id": str(home),
        "instance_id": before["instance_id"], "authority_epoch": before["authority_epoch"],
        "enrollment_request_id": publication.session.request_id,
        "principal_id": publication.session.principal_id, "session_id": before["session_id"]}
    if (expected["instance_id"] != descriptor.get("instance_id")
            or expected["authority_epoch"] != descriptor.get("authority_epoch")):
        raise RuntimeRefusal("NATIVE_AGENTOS_READBACK_UNAVAILABLE")
    value = slot.memory_factory.readback()
    if selected_child_publication(publication) is not None:
        value["selected_child"] = _consumer_extension(runner, home)
    if (enrollment() != before or getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None) is not slot
            or not slot.memory_factory.registered_current()):
        raise RuntimeRefusal("NATIVE_AGENTOS_READBACK_UNAVAILABLE")
    return validate_consumer_readback(value, publication=publication, expected_binding=expected)


def _implementation(value):
    if (type(value) is not str or len(value) != 40
            or any(c not in "0123456789abcdef" for c in value)):
        raise RuntimeRefusal("NATIVE_ENROLLMENT_IMPLEMENTATION_INVALID")
    return value


def _enrollment_id(value):
    if (type(value) is not str or not 1 <= len(value) <= 256
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise RuntimeRefusal("NATIVE_ENROLLMENT_ID_INVALID")
    try:
        value.encode("utf-8", "strict")
    except UnicodeError:
        raise RuntimeRefusal("NATIVE_ENROLLMENT_ID_INVALID") from None
    return value


def validate_enrollment_capability(value, *, role: str = "mmsecretary"):
    schema = conversation_contract(role).enrollment_schema
    if (type(value) is not dict or set(value) != {"schema", "request_id"}
            or value["schema"] != schema):
        raise RuntimeRefusal("NATIVE_ENROLLMENT_CAPABILITY_INVALID")
    return {"schema": schema, "request_id": _enrollment_id(value["request_id"])}


def validate_enrollment_result(value, *, implementation_sha=None, request_id=None,
                               profile_id=None, principal_id=None, role: str = "mmsecretary"):
    schema = conversation_contract(role).enrollment_result_schema
    if (type(value) is not dict
            or set(value) != {"schema", "implementation_sha", "request_id", "status", "target"}
            or value["schema"] != schema
            or type(value["status"]) is not str or value["status"] not in _ENROLLMENT_STATUSES):
        raise RuntimeRefusal("NATIVE_ENROLLMENT_RESULT_INVALID")
    _implementation(value["implementation_sha"])
    _enrollment_id(value["request_id"])
    if ((implementation_sha is not None and value["implementation_sha"] != implementation_sha)
            or (request_id is not None and value["request_id"] != request_id)):
        raise RuntimeRefusal("NATIVE_ENROLLMENT_RESULT_MISMATCH")
    target = value["target"]
    if value["status"] == "ENROLLED":
        target = validate_target(target)
        if ((profile_id is not None and target["profile_id"] != profile_id)
                or (principal_id is not None and target["principal_id"] != principal_id)):
            raise RuntimeRefusal("NATIVE_ENROLLMENT_RESULT_MISMATCH")
    elif target is not None:
        raise RuntimeRefusal("NATIVE_ENROLLMENT_RESULT_INVALID")
    result = dict(value, target=target)
    try:
        if len(_canonical(result)) > 16 * 1024:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise RuntimeRefusal("NATIVE_ENROLLMENT_RESULT_INVALID") from None
    return result


def enrollment_result(implementation_sha, request_id, status, target=None, *, role: str = "mmsecretary"):
    return validate_enrollment_result({
        "schema": conversation_contract(role).enrollment_result_schema, "implementation_sha": implementation_sha,
        "request_id": request_id, "status": status, "target": target}, role=role)


def _inspect_enrollment(runner, home, implementation_sha, request_id, principal, *, own_task=None,
                        route_out=None, role: str = "mmsecretary"):
    """Read one bounded native snapshot; never restore or create."""
    from hermes_state_keys import local_identity
    from hermes_state_local import POLICY_PREFIX, same_create_retry
    from hermes_state_local_lineage import validate_local_lineage
    from hermes_state_mutation_retirement import retired_in
    from hermes_state_runtime import _epoch
    from gateway.session import SessionEntry
    from gateway.session_local_recovery import local_source
    from gateway.session_runtime_workers import mutation_tasks

    def result(status, target=None):
        return enrollment_result(implementation_sha, request_id, status, target, role=role)

    try:
        authority = runner.session_authority
        descriptor = runner.session_runtime_descriptor
        if (authority.profile_id != str(home) or descriptor.get("state") != "ready"
                or runner._draining or descriptor.get("instance_id") != authority.instance_id
                or type(descriptor.get("authority_epoch")) is not int
                or descriptor["authority_epoch"] != authority.epoch):
            return result("UNAVAILABLE")
        sid = local_identity(str(home), principal, request_id)
        source = local_source(authority, sid, principal)
        route = runner.session_store._generate_session_key(source)
        with authority.db._read_ctx(reopen=False) as conn:
            # Native pooled-reader acquisition alone is not a snapshot.
            # Own only this read transaction and release it before any await.
            if conn.in_transaction:
                return result("UNAVAILABLE")
            conn.execute("BEGIN")
            try:
                _epoch(conn, authority.epoch)
                epoch = conn.execute(
                    "SELECT epoch,instance_id FROM runtime_epoch WHERE singleton=1").fetchone()
                if (epoch is None or type(epoch["epoch"]) is not int
                        or epoch["epoch"] != authority.epoch
                        or epoch["instance_id"] != authority.instance_id):
                    return result("UNAVAILABLE")
                receipt_row = conn.execute(
                    "SELECT CASE WHEN length(CAST(value AS BLOB))<=65536 THEN value END "
                    "FROM state_meta WHERE key=?", (POLICY_PREFIX + sid,)).fetchone()
                row = conn.execute(
                    "SELECT id,source,user_id,session_key,chat_id,runtime_revision,runtime_generation "
                    "FROM sessions WHERE id=?", (sid,)).fetchone()
                route_row = conn.execute(
                    "SELECT CASE WHEN length(CAST(entry_json AS BLOB))<=65536 THEN entry_json END "
                    "FROM gateway_routing WHERE scope='' AND session_key=?", (route,)).fetchone()
                if retired_in(conn, sid):
                    return result("REFUSED")
                if receipt_row is None:
                    if row is not None or route_row is not None:
                        return result("REFUSED")
                    if any(task is not own_task for task in mutation_tasks(authority)):
                        return result("EFFECT_UNKNOWN")
                    return result("ABSENT")
                # Parse the exact bounded value; no helper may reopen its receipt.
                receipt = json.loads(receipt_row[0])
                if (type(receipt) is not dict or "legacy_session_id" in receipt
                        or any(receipt.get(k) != v for k, v in {
                            "profile_id": str(home), "principal_id": principal, "request_id": request_id,
                            "session_id": sid, "route": route}.items())
                        or type(receipt.get("policy")) is not dict
                        or receipt["policy"].get("source") != "tool"
                        or not same_create_retry(receipt["policy"], '{"source":"tool"}', {})):
                    return result("REFUSED")
                if (row is None or row["id"] != sid or row["source"] != "tool"
                        or row["user_id"] != principal or row["session_key"] != route
                        or row["chat_id"] != sid or route_row is None):
                    return result("REFUSED")
                lineage = receipt.get("lineage", [sid])
                if type(lineage) is not list or not lineage:
                    return result("UNAVAILABLE")
                # Bound the native lineage helper's auxiliary JSON reads in the
                # same snapshot. Its own identity/rotation rules remain native.
                for node in lineage:
                    _id(node)
                    bounded = conn.execute(
                        "SELECT length(CAST(COALESCE(model_config,'') AS BLOB))<=65536 "
                        "AND length(CAST(COALESCE(end_reason,'') AS BLOB))<=256 "
                        "AND length(CAST(COALESCE(parent_session_id,'') AS BLOB))<=1024 "
                        "FROM sessions WHERE id=?", (node,)).fetchone()
                    if bounded is None or bounded[0] != 1:
                        return result("UNAVAILABLE")
                tip = validate_local_lineage(conn, receipt)
                physical = conn.execute(
                    "SELECT session_key,chat_id,user_id FROM sessions WHERE id=?", (tip,)).fetchone()
                if physical is None or tuple(physical) != (route, sid, principal):
                    return result("REFUSED")
                for captured in (receipt["entry"], json.loads(route_row[0])):
                    entry = SessionEntry.from_dict(captured)
                    if "profile" not in captured["origin"]:
                        entry.origin.profile = source.profile
                    if (entry.session_id != tip or entry.session_key != route
                            or entry.origin.to_dict() != source.to_dict()):
                        return result("REFUSED")
                target = validate_target({
                    "profile_id": str(home), "session_id": sid, "principal_id": principal,
                    "instance_id": epoch["instance_id"], "authority_epoch": epoch["epoch"],
                    "revision": row["runtime_revision"], "execution_generation": row["runtime_generation"]})
                if route_out is not None:
                    # The route key the native owner bound to this session. It
                    # is read from the same bounded snapshot, never recomputed.
                    route_out["route"] = route
                return result("ENROLLED", target)
            finally:
                conn.rollback()
    except Exception:
        # Corruption, storage failure and unknown native state are never absence.
        return result("UNAVAILABLE")

def read_enrolled_session(runner, home: Path, implementation_sha, request_id,
                          principal, *, role: str = "mmsecretary") -> dict:
    """The bounded ENROLLED facts of the original native session.

    This reads the same bounded snapshot the enrollment result uses. It never
    creates, restores or resumes a session: an absent enrollment is ABSENT,
    and anything unknown is UNAVAILABLE, never absence.
    """
    route_out: dict = {}
    outcome = _inspect_enrollment(runner, home, implementation_sha, request_id,
                                   principal, route_out=route_out, role=role)
    if outcome["status"] != "ENROLLED":
        return {"status": outcome["status"], "target": None, "route": None}
    return {"status": "ENROLLED", "target": outcome["target"],
            "route": route_out.get("route")}


async def _create_enrollment(runner, home, params, principal, *, role: str = "mmsecretary"):
    """The existing authority creates once and owns all work through detach."""
    from gateway.session_controls import AuthorityConnection
    from gateway.run_api import _embedded_chat_enabled
    from gateway.session_authorities import owner_scope
    from gateway.run_idle_exit import attached_client
    from tui_gateway.transport import StdioTransport, bind_transport, reset_transport
    implementation_sha, request_id = params["implementation_sha"], params["request_id"]
    own_task = asyncio.current_task()

    def inspect():
        return _inspect_enrollment(runner, home, implementation_sha, request_id,
                                   principal, own_task=own_task, role=role)

    prior = inspect()
    if prior["status"] != "ABSENT":
        return prior
    if not _embedded_chat_enabled():
        return enrollment_result(implementation_sha, request_id, "REFUSED", role=role)
    try:
        grant = runner.session_ticket_store.redeem(
            params["ticket"], profile_id=str(home), purpose="interactive")
    except PermissionError:
        return enrollment_result(implementation_sha, request_id, "REFUSED", role=role)
    if (grant.get("subject") != principal or grant.get("scope") != "profile"
            or grant.get("profile_id") != str(home)
            or grant.get("instance_id") != runner.session_authority.instance_id):
        return enrollment_result(implementation_sha, request_id, "REFUSED", role=role)
    identity = {"user_id": grant["subject"], "provider": "local", "profile_id": grant["profile_id"],
                "instance_id": grant["instance_id"], "capabilities": grant["capabilities"],
                "native_bootstrap": True, "profile_scope": "profile"}
    stream, lock = _ReceiptStream(), threading.Lock()
    transport = StdioTransport(lambda: stream, lock)
    explicit_refusal = False
    with owner_scope(runner.session_authority), attached_client(runner):
        token = bind_transport(transport)
        connection = None
        try:
            connection = AuthorityConnection(runner.session_authority, transport, identity, operator=False)
            reply = await connection.dispatch({
                "jsonrpc": "2.0", "id": 1, "method": "session.create",
                "params": {"request_id": request_id, "source": "tool"}})
            explicit_refusal = type(reply) is dict and "error" in reply
        except Exception:
            pass
        finally:
            try:
                if connection is not None:
                    await connection.close()
            finally:
                with lock:
                    stream.close()
                transport.close()
                reset_transport(token)
    observed = inspect()
    if observed["status"] == "ENROLLED":
        return observed
    if explicit_refusal and observed["status"] in {"ABSENT", "REFUSED"}:
        return enrollment_result(implementation_sha, request_id, "REFUSED", role=role)
    return enrollment_result(implementation_sha, request_id, "EFFECT_UNKNOWN", role=role)


async def _enrollment_operation(runner, home, params, principal, *, consumer_transition=None,
                                role: str = "mmsecretary"):
    if params["operation"] == "inspect_enrollment":
        return _inspect_enrollment(runner, home, params["implementation_sha"], params["request_id"], principal, role=role)
    from gateway.session_runtime_workers import track_mutation
    # The native task set covers create, resume and cleanup. A private response
    # deadline cannot cancel it or make another observer infer absence.
    task = track_mutation(runner.session_authority, _create_enrollment(runner, home, params, principal, role=role))
    result = await asyncio.shield(task)
    if result.get("status") == "ENROLLED" and consumer_transition is not None:
        try:
            consumer_transition(runner)
        except Exception:
            pass  # Consumer qualification cannot rewrite native enrollment truth.
    return result


def install_private_control(runner, home: Path, role: str, *,
                            implementation_sha: str | None = None,
                            session_enrollment: dict | None = None,
                            consumer_transition=None) -> None:
    if type(role) is not str or role not in {"mmsecretary", "mmmeta"}:
        return
    contract = conversation_contract(role)
    server = runner.session_control_server
    if any(conversation_contract(selected).native_verb in server.private_handlers
           for selected in ("mmsecretary", "mmmeta")):
        raise RuntimeRefusal("NATIVE_SECRETARY_CONTROL_ALREADY_INSTALLED")
    def role_result(status, **fields):
        return _result(status, role=role, **fields)

    loop = asyncio.get_running_loop()
    import contextvars
    owner_context = contextvars.copy_context()
    frozen = None
    if session_enrollment is not None:
        _implementation(implementation_sha)
        frozen = validate_enrollment_capability(session_enrollment, role=role)

    def enrollment(params, peer_subject):
        # V1 has no enrollment capability. The native server, not caller input,
        # supplies the held implementation and original request identity.
        try:
            _implementation(implementation_sha)
            request_id = _enrollment_id(params.get("request_id"))
        except RuntimeRefusal:
            return role_result("REFUSED")
        refused = enrollment_result(implementation_sha, request_id, "REFUSED", role=role)
        keys = {"operation", "profile_id", "implementation_sha", "request_id"}
        modifying = params["operation"] == "enroll_session"
        if modifying:
            keys.add("ticket")
        if (peer_subject != f"uid:{os.getuid()}" or set(params) != keys
                or params["profile_id"] != str(home)
                or params["implementation_sha"] != implementation_sha
                or frozen is None or request_id != frozen["request_id"]
                or (modifying and (type(params["ticket"]) is not str
                                   or not 1 <= len(params["ticket"]) <= 256))):
            return refused
        options = {"role": role}
        if consumer_transition is not None:
            options["consumer_transition"] = consumer_transition
        coroutine = _enrollment_operation(runner, home, dict(params), peer_subject, **options)
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except Exception:
            coroutine.close()
            return refused
        try:
            return future.result(timeout=25)
        except Exception:
            # No cancel: the original native mutation remains tracked.
            return enrollment_result(implementation_sha, request_id,
                                     "EFFECT_UNKNOWN" if modifying else "UNAVAILABLE", role=role)

    def handle(params, peer_subject):
        if type(params) is dict and params.get("operation") in {"inspect_enrollment", "enroll_session"}:
            return enrollment(params, peer_subject)
        if peer_subject != f"uid:{os.getuid()}" or type(params) is not dict:
            return role_result("REFUSED", reason="PEER_REFUSED")
        operation = params.get("operation")
        try:
            if operation == "observe":
                if set(params) != {"operation", "profile_id", "session_id"} or params["profile_id"] != str(home):
                    raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
                return role_result("TARGET", target=_target(runner, home, _id(params["session_id"]), peer_subject))
            if operation == "read_original":
                return _read_original(home, params, peer_subject, role=role)
            if operation in {"consumer_extension", "consumer_capabilities"}:
                # A finite read-only qualification of the serving process. The
                # caller selects no target and no route: the profile is the
                # one this private socket belongs to.
                if set(params) != {"operation", "profile_id"} or params["profile_id"] != str(home):
                    raise RuntimeRefusal("NATIVE_CONSUMER_EXTENSION_REQUEST_INVALID")
                async def observe_extension():
                    if operation == "consumer_capabilities":
                        return role_result("OBSERVED", consumer=_consumer_capabilities(runner, home))
                    return role_result("OBSERVED", extension=_consumer_extension(runner, home))
                coroutine = observe_extension()
                try:
                    future = owner_context.copy().run(
                        asyncio.run_coroutine_threadsafe, coroutine, loop)
                except Exception:
                    coroutine.close()
                    return role_result("UNAVAILABLE")
                try:
                    return future.result(timeout=5)
                except Exception:
                    from integrations.hermes_harness.native_executive_consumer import _consume_future_result
                    future.add_done_callback(_consume_future_result)
                    return role_result("UNAVAILABLE")
            if operation != "submit" or set(params) != {"operation", "target", "submission_id", "text", "ticket"}:
                raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
            _id(params["submission_id"])
            input_digest(params["text"])
            if type(params["ticket"]) is not str or not 1 <= len(params["ticket"]) <= 256:
                raise RuntimeRefusal("NATIVE_SECRETARY_REQUEST_INVALID")
        except Exception:
            return role_result("UNAVAILABLE" if operation in {
                "observe", "read_original", "consumer_extension", "consumer_capabilities"} else "REFUSED")
        # This is the native control server's existing executor. The native
        # loop owns the bounded coroutine; never create a new event loop.
        coroutine = _submit(runner, home, params, peer_subject, role=role)
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except Exception:
            coroutine.close()
            return role_result("REFUSED", reason="OWNER_LOOP_UNAVAILABLE")
        try:
            return future.result(timeout=25)
        except Exception:
            # Do not cancel/replay an admission when the control response is lost.
            return role_result("EFFECT_UNKNOWN")

    server.private_handlers[contract.native_verb] = handle


class NativeSecretaryClient:
    """Actual selected same-UID native client; each operation sends once."""

    def __init__(self, home: Path, *, expected_pid: int | None = None,
                 role: str = "mmsecretary"):
        self._contract = conversation_contract(role)
        self._role = self._contract.role
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
        if operation == "consumer_extension" and set(request) == {"operation"}:
            return self.consumer_extension()
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

    def _call(self, params, *, result_schema=None):
        if result_schema is None:
            result_schema = self._contract.native_schema
        if result_schema not in {self._contract.native_schema, self._contract.enrollment_result_schema}:
            raise RuntimeRefusal("NATIVE_CONVERSATION_SCHEMA_INVALID")
        from hermes_cli.gateway_runtime_discovery import connect_private
        if self.expected_pid is not None:
            observed = self._identify()
            if observed.state != "ready" or observed.endpoint is None:
                raise RuntimeRefusal("NATIVE_SECRETARY_OWNER_CHANGED")
        request = _canonical({"protocol": 1, "id": 1, "verb": self._contract.native_verb, "params": params}) + b"\n"
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
                or type(value) is not dict or value.get("schema") != result_schema):
            raise RuntimeRefusal("NATIVE_SECRETARY_RESPONSE_INVALID")
        if result_schema == self._contract.enrollment_result_schema:
            return validate_enrollment_result(
                value, implementation_sha=params["implementation_sha"], request_id=params["request_id"],
                profile_id=str(self.home), principal_id=f"uid:{os.getuid()}", role=self._role)
        return value

    def inspect_enrollment(self, implementation_sha: str, request_id: str):
        _implementation(implementation_sha)
        _enrollment_id(request_id)
        if self.expected_pid is None:
            raise RuntimeRefusal("NATIVE_ENROLLMENT_QUALIFIED_OWNER_REQUIRED")
        try:
            return self._call({
                "operation": "inspect_enrollment", "profile_id": str(self.home),
                "implementation_sha": implementation_sha, "request_id": request_id},
                result_schema=self._contract.enrollment_result_schema)
        except Exception:
            return enrollment_result(implementation_sha, request_id, "UNAVAILABLE", role=self._role)

    def enroll_session(self, implementation_sha: str, request_id: str):
        _implementation(implementation_sha)
        _enrollment_id(request_id)
        if self.expected_pid is None:
            raise RuntimeRefusal("NATIVE_ENROLLMENT_QUALIFIED_OWNER_REQUIRED")
        from hermes_cli.gateway_client import _session_ticket
        try:
            observed = self._identify()
            if observed.state != "ready" or observed.endpoint is None:
                return enrollment_result(implementation_sha, request_id, "UNAVAILABLE", role=self._role)
            ticket = _session_ticket(self.home, observed.endpoint)
        except Exception:
            return enrollment_result(implementation_sha, request_id, "UNAVAILABLE", role=self._role)
        try:
            return self._call({
                "operation": "enroll_session", "profile_id": str(self.home),
                "implementation_sha": implementation_sha, "request_id": request_id, "ticket": ticket},
                result_schema=self._contract.enrollment_result_schema)
        except Exception:
            return enrollment_result(implementation_sha, request_id, "EFFECT_UNKNOWN", role=self._role)

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
            return _result("REFUSED", role=self._role, reason="TARGET_CHANGED")
        ticket = _session_ticket(self.home, endpoint)
        try:
            return self._call({"operation": "submit", "target": target,
                               "submission_id": _id(submission_id), "text": text, "ticket": ticket})
        except Exception:
            return _result("EFFECT_UNKNOWN", role=self._role)

    def read_original(self, *, session_id, submission_id, input_sha256, admission_id=None):
        return self._call({"operation": "read_original", "profile_id": str(self.home),
                           "session_id": _id(session_id), "submission_id": _id(submission_id),
                           "input_sha256": input_sha256, "admission_id": admission_id})

    def consumer_extension(self):
        """Read the serving process's actual scoped native extension entry.

        This is the serving-process extension proof. It is a finite read-only
        observation over the existing same-UID private socket: it starts no
        owner, creates no session and mutates nothing.
        """
        return self._call({"operation": "consumer_extension", "profile_id": str(self.home)})

    def consumer_capabilities(self):
        """Private v2 capability observation; not a role HTTP dispatch verb."""
        return self._call({"operation": "consumer_capabilities", "profile_id": str(self.home)})
