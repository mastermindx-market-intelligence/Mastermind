"""Closed native-operation boundaries with explicit native owner doubles.

These do not execute Hermes, a provider, a Linux service, or an Office path.
The wire test uses a real AF_UNIX stream; native authority effects are doubles.
"""
import asyncio
import copy
from contextlib import contextmanager
from dataclasses import make_dataclass
import hashlib
import sqlite3
import json
from pathlib import Path
import socket
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime.errors import RuntimeRefusal


def module(monkeypatch, name, **members):
    value = ModuleType(name)
    value.__dict__.update(members)
    monkeypatch.setitem(sys.modules, name, value)
    return value


@pytest.fixture
def native(monkeypatch, tmp_path):
    home = tmp_path.resolve()
    target = dict(profile_id=str(home), session_id="owned-session", principal_id="uid:994",
                  instance_id="owner-1", authority_epoch=7, revision=3, execution_generation=2)
    receipt = dict(admission_id="native-admission", ref=dict(profile_id=str(home), session_id="owned-session"),
                   sequence=1, status="queued", outcome=None, authority_epoch=7, execution_generation=None)
    calls, scopes = [], []
    state = SimpleNamespace(changed=False, lose=False, closed=False, transport=None)

    @contextmanager
    def scope(value):
        scopes.append(value)
        try:
            yield
        finally:
            scopes.pop()

    class Transport:
        def __init__(self, stream_getter, lock):
            self.stream_getter, self.lock = stream_getter, lock

        def write(self, obj):
            with self.lock:
                try:
                    self.stream_getter().write(json.dumps(obj))
                    return True
                except BrokenPipeError:
                    return False

        def close(self):
            pass

    class Connection:
        def __init__(self, authority, transport, identity, *, operator):
            assert not operator and identity["user_id"] == target["principal_id"]
            assert identity["profile_scope"] == "profile" and len(scopes) == 2
            assert transport is state.transport
            self.transport = transport
            self.authority = authority
            self.actor = SimpleNamespace(profile_id=target["profile_id"], subject=target["principal_id"])

        def submission(self, ref, params):
            assert ref.session_id == target["session_id"] and ref.profile_id == target["profile_id"]
            return params

        async def dispatch(self, request):
            calls.append(request)
            assert self.transport.write({"event": "native-ownership-test"})
            if request["method"] == "session.resume":
                value = {k: target[k] for k in ("session_id", "authority_epoch", "revision", "execution_generation")}
                value["stored_session_id"] = target["session_id"]
                if state.changed:
                    value["revision"] += 1
                return {"result": value}
            raise AssertionError("only resume uses the generic dispatcher")

        async def close(self):
            state.closed = True

    def bind(value):
        state.transport = value
        return "original-token"

    def reset(token):
        assert token == "original-token"
        state.reset = True

    grant = dict(subject=target["principal_id"], scope="profile", instance_id=target["instance_id"],
                 profile_id=str(home), capabilities=["session:read", "session:submit"])
    Receipt = make_dataclass("Receipt", list(receipt))
    async def submit(actor, request, *, _authorize_write, queue_while_restarting):
        assert actor.subject == target["principal_id"] and callable(_authorize_write)
        assert queue_while_restarting is False
        calls.append({"method": "authority.submit", "params": request})
        if state.lose:
            raise TimeoutError("admission response lost")
        return Receipt(**receipt)
    authority = SimpleNamespace(submit=submit)
    runner = SimpleNamespace(session_authority=authority,
                             session_ticket_store=SimpleNamespace(redeem=lambda *a, **k: grant))
    module(monkeypatch, "gateway.session_contract",
           SessionRef=make_dataclass("SessionRef", ["profile_id", "session_id"]))
    module(monkeypatch, "gateway.session_controls", AuthorityConnection=Connection)
    module(monkeypatch, "gateway.run_api", _embedded_chat_enabled=lambda: True)
    module(monkeypatch, "gateway.session_authorities", owner_scope=scope)
    module(monkeypatch, "gateway.run_idle_exit", attached_client=scope)
    module(monkeypatch, "tui_gateway.transport", StdioTransport=Transport,
           bind_transport=bind, reset_transport=reset)
    monkeypatch.setattr(control, "_target", lambda *a: dict(target))
    params = dict(target=dict(target), submission_id="operation-1", text="Explain this mission.", ticket="private-ticket")
    return SimpleNamespace(home=home, target=target, receipt=receipt, params=params,
                           runner=runner, calls=calls, state=state, scopes=scopes)


def test_one_native_admission_preserves_receipt_and_cleans_viewer(native):
    result = asyncio.run(control._submit(native.runner, native.home, native.params, "uid:994"))
    assert result == dict(schema=control.SCHEMA, status="ADMITTED", admission=native.receipt)
    assert [call["method"] for call in native.calls] == ["session.resume", "authority.submit"]
    assert native.calls[-1]["params"] == dict(session_id="owned-session", submission_id="operation-1",
                                             text="Explain this mission.", finite=True)
    assert native.state.closed and native.state.reset and not native.scopes
    assert native.state.transport.write({"late": "native event"}) is False


def test_changed_resume_never_submits(native):
    native.state.changed = True
    result = asyncio.run(control._submit(native.runner, native.home, native.params, "uid:994"))
    assert result["status"] == "NOT_SUBMITTED"
    assert [call["method"] for call in native.calls] == ["session.resume"]
    assert native.state.closed


def test_lost_admission_response_is_unknown_and_never_replayed(native):
    native.state.lose = True
    result = asyncio.run(control._submit(native.runner, native.home, native.params, "uid:994"))
    assert result["status"] == "EFFECT_UNKNOWN"
    assert sum(call["method"] == "authority.submit" for call in native.calls) == 1
    assert native.state.closed and native.state.reset


def test_receipt_stream_has_a_byte_budget_and_no_retained_transcript():
    stream = control._ReceiptStream()
    stream.write("x" * control.MAX_WIRE_BYTES)
    with pytest.raises(BrokenPipeError):
        stream.write("é")
    assert stream.closed and stream.bytes == control.MAX_WIRE_BYTES
    assert set(vars(stream)) == {"bytes", "closed"}


def test_read_original_missing_is_unknown_and_wrong_principal_refuses(monkeypatch, tmp_path):
    db = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(control, "_db", lambda home: db)
    state = SimpleNamespace(row=None)
    module(monkeypatch, "hermes_state_runtime", find_session_admission=lambda *a, **k: state.row,
           get_session_admission=lambda *a, **k: state.row)
    module(monkeypatch, "gateway.session_results", admission_result=lambda *a: None)
    params = dict(operation="read_original", profile_id=str(tmp_path), session_id="s", submission_id="op",
                  input_sha256=control.input_digest("question"), admission_id=None)
    assert control._read_original(tmp_path, params, "uid:994")["status"] == "EFFECT_UNKNOWN"
    state.row = dict(principal_id="uid:993", target_session_id="s", request_id="op")
    with pytest.raises(RuntimeRefusal, match="NATIVE_SECRETARY_ORIGINAL_MISMATCH"):
        control._read_original(tmp_path, params, "uid:994")


def test_private_wire_uses_one_existing_socket_request(monkeypatch, tmp_path):
    left, right = socket.socketpair()
    requests = []
    def serve():
        with right:
            raw = bytearray()
            while b"\n" not in raw:
                raw.extend(right.recv(65536))
            requests.append(json.loads(raw))
            right.sendall(json.dumps(dict(protocol=1, id=1, ok=True,
                result=dict(schema=control.SCHEMA, status="EFFECT_UNKNOWN"))).encode() + b"\n")
    worker = threading.Thread(target=serve)
    worker.start()
    module(monkeypatch, "hermes_cli.gateway_runtime_discovery", connect_private=lambda *a: left)
    result = control.NativeSecretaryClient(tmp_path).read_original(
        session_id="s", submission_id="op", input_sha256=control.input_digest("question"))
    worker.join(timeout=2)
    assert not worker.is_alive() and result["status"] == "EFFECT_UNKNOWN"
    assert len(requests) == 1 and requests[0]["verb"] == control.VERB
    assert requests[0]["params"]["operation"] == "read_original"


@pytest.fixture
def original_terminal(monkeypatch, tmp_path):
    """Stored-owner doubles, reached through the real original-result reader."""
    state = SimpleNamespace(
        row=dict(admission_id="original-admission", principal_id="uid:994",
                 target_session_id="owned-session", request_id="original-submission",
                 intent="queue", payload={"text": "question", "finite": True},
                 seq=4, status="terminal", outcome="completed", owner_epoch=7, generation=3),
        saved={"result": {"final_response": "  café\n回答\t", "completed": True,
                           "failed": False, "partial": False, "interrupted": False,
                           "api_calls": 2, "session_id": "physical-session",
                           "model": "configured-model", "requested_model": "requested-route",
                           "provider": "configured-provider", "turn_exit_reason": "completed",
                           "response_transformed": True}},
        stored_reads=[], lookups=[], closes=0,
    )
    def close():
        state.closes += 1
    db = SimpleNamespace(close=close)
    monkeypatch.setattr(control, "_db", lambda home: db)
    def lookup(_db, **kwargs):
        assert _db is db
        state.lookups.append(kwargs)
        return state.row
    def stored(_db, admission_id):
        assert _db is db
        state.stored_reads.append(admission_id)
        return state.saved
    module(monkeypatch, "hermes_state_runtime", find_session_admission=lookup,
           get_session_admission=lookup)
    module(monkeypatch, "gateway.session_results", admission_result=stored)
    state.params = dict(operation="read_original", profile_id=str(tmp_path),
                        session_id="owned-session", submission_id="original-submission",
                        input_sha256=control.input_digest("question"), admission_id=None)
    state.read = lambda: control._read_original(tmp_path, state.params, "uid:994")
    return state


def test_original_terminal_projection_preserves_bytes_and_does_not_qualify_model(original_terminal):
    source = copy.deepcopy(original_terminal.saved)
    result = original_terminal.read()
    metadata = result["terminal_metadata"]
    raw = source["result"]["final_response"].encode("utf-8")
    assert result["answer"].encode("utf-8") == raw
    assert metadata["output"] == {
        "stage": "retained_redacted_final_response",
        "sha256": hashlib.sha256(raw).hexdigest(), "utf8_bytes": len(raw),
    }
    assert metadata["schema"] == "mastermind.hermes_native_terminal_metadata/v1"
    assert metadata["reported"]["completed"] is True
    assert metadata["reported"]["partial"] is False
    assert metadata["reported"]["api_calls"] == 2
    assert metadata["reported"]["session_id"] == "physical-session"
    assert result["admission"]["ref"]["session_id"] == "owned-session"
    assert metadata["model_identity_verified"] is False
    assert metadata["invalid_fields"] == []
    assert original_terminal.saved == source
    assert original_terminal.stored_reads == ["original-admission"]
    assert original_terminal.closes == 1


@pytest.mark.parametrize("flag", ["completed", "failed", "partial", "interrupted",
                                   "response_transformed", "response_previewed", "response_reused"])
def test_terminal_false_missing_and_invalid_remain_distinct(original_terminal, flag):
    value = original_terminal.saved["result"]
    value[flag] = False
    assert original_terminal.read()["terminal_metadata"]["reported"][flag] is False
    del value[flag]
    missing = original_terminal.read()["terminal_metadata"]
    assert flag not in missing["reported"] and flag not in missing["invalid_fields"]
    value[flag] = 0
    invalid = original_terminal.read()["terminal_metadata"]
    assert flag not in invalid["reported"] and flag in invalid["invalid_fields"]


@pytest.mark.parametrize("value", [True, -1, 1.5, float("nan"), float("inf"), "2", 2**53])
def test_terminal_counter_never_coerces_bad_observations(original_terminal, value):
    original_terminal.saved["result"]["api_calls"] = value
    result = original_terminal.read()
    assert "api_calls" not in result["terminal_metadata"]["reported"]
    assert "api_calls" in result["terminal_metadata"]["invalid_fields"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field", ["session_id", "model", "requested_model", "provider", "turn_exit_reason"])
@pytest.mark.parametrize("bad", ["é" * 129, "bad\nlabel", "bad\x7flabel", "bad\ud800", {"model": "nested"}])
def test_terminal_labels_are_bounded_and_malformed_fields_do_not_hide_answer(original_terminal, field, bad):
    original_terminal.saved["result"][field] = bad
    result = original_terminal.read()
    assert result["answer"] == "  café\n回答\t"
    assert field not in result["terminal_metadata"]["reported"]
    assert field in result["terminal_metadata"]["invalid_fields"]
    assert len(control._canonical(result["terminal_metadata"])) < 4 * 1024


def test_terminal_projection_omits_sensitive_and_ambiguous_unselected_fields(original_terminal):
    value = original_terminal.saved["result"]
    sentinel = "PRIVATE-RETAINED-SENTINEL"
    for key in ("last_reasoning", "messages", "tools", "error", "pre_transform_response",
                "served_model", "usage", "account", "extra_metadata"):
        value[key] = sentinel
    original_terminal.saved["usage"] = {"session_cost": sentinel}
    result = original_terminal.read()
    assert sentinel not in json.dumps(result)
    assert result["successful"] is False
    assert result["terminal_metadata"]["model_identity_verified"] is False


@pytest.mark.parametrize("answer", [None, "bad\ud800", "bad\x00", "é" * (control.MAX_ANSWER_BYTES // 2 + 1)])
def test_invalid_or_absent_answer_still_exposes_actual_failure_metadata(original_terminal, answer):
    original_terminal.saved["result"].update(final_response=answer, completed=False, failed=True)
    result = original_terminal.read()
    assert "answer" not in result and "successful" not in result
    assert result["terminal_metadata"]["reported"]["completed"] is False
    assert result["terminal_metadata"]["reported"]["failed"] is True
    assert result["terminal_metadata"]["output"] is None


@pytest.mark.parametrize("saved", [None, [], {}, {"result": None}, {"result": []}])
def test_absent_or_malformed_retained_result_does_not_create_metadata(original_terminal, saved):
    original_terminal.saved = saved
    result = original_terminal.read()
    assert result["status"] == "OBSERVED"
    assert "terminal_metadata" not in result and "answer" not in result
    assert original_terminal.stored_reads == ["original-admission"]


@pytest.mark.parametrize("status", ["queued", "started", "unknown"])
def test_unsettled_admission_never_publishes_terminal_metadata(original_terminal, status):
    original_terminal.row["status"] = status
    result = original_terminal.read()
    assert "terminal_metadata" not in result and "answer" not in result


@pytest.mark.parametrize("field,bad", [
    ("principal_id", "uid:foreign"), ("target_session_id", "foreign-session"),
    ("request_id", "foreign-submission"), ("intent", "other"),
    ("payload", {"text": "changed", "finite": True}),
    ("payload", {"text": "question", "finite": False}),
])
def test_terminal_metadata_never_bypasses_original_operation_join(original_terminal, field, bad):
    original_terminal.saved["mastermind_request_observation"] = observation_document(original_terminal)
    original_terminal.row[field] = bad
    with pytest.raises(RuntimeRefusal, match="NATIVE_SECRETARY_ORIGINAL_MISMATCH"):
        original_terminal.read()
    assert original_terminal.stored_reads == []
    assert original_terminal.closes == 1


def test_legacy_result_keeps_missing_completion_and_existing_answer_contract(original_terminal):
    original_terminal.saved = {"result": {"final_response": "legacy answer"}}
    result = original_terminal.read()
    assert result["answer"] == "legacy answer" and result["successful"] is True
    assert result["terminal_metadata"]["reported"] == {}
    assert result["terminal_metadata"]["model_identity_verified"] is False


def test_terminal_metadata_flows_over_the_existing_single_private_request(original_terminal, monkeypatch, tmp_path):
    original_terminal.saved["mastermind_request_observation"] = observation_document(original_terminal)
    left, right = socket.socketpair()
    requests = []
    def serve():
        with right:
            raw = bytearray()
            while b"\n" not in raw:
                raw.extend(right.recv(65536))
            request = json.loads(raw)
            requests.append(request)
            result = control._read_original(tmp_path, request["params"], "uid:994")
            right.sendall(json.dumps(dict(protocol=1, id=1, ok=True, result=result)).encode() + b"\n")
    worker = threading.Thread(target=serve)
    worker.start()
    module(monkeypatch, "hermes_cli.gateway_runtime_discovery", connect_private=lambda *a: left)
    result = control.NativeSecretaryClient(tmp_path).read_original(
        session_id="owned-session", submission_id="original-submission",
        input_sha256=control.input_digest("question"), admission_id="original-admission")
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert len(requests) == 1 and requests[0]["params"]["operation"] == "read_original"
    assert original_terminal.lookups == [{"admission_id": "original-admission"}]
    assert original_terminal.stored_reads == ["original-admission"]
    assert result["terminal_metadata"]["output"]["sha256"] == hashlib.sha256(result["answer"].encode()).hexdigest()
    assert result["request_observation"] == original_terminal.saved["mastermind_request_observation"]


def observation_document(state):
    content = {"messages": [{"role": "user", "content": "question"}]}
    raw = control._canonical(content)
    return {"schema": "mastermind.hermes_request_observation/v1",
        "stage": "assembled_content_after_pre_request_hooks",
        "scope": {"role": "mmsecretary", "session_id": state.row["target_session_id"],
            "admission_id": state.row["admission_id"], "authority_epoch": state.row["owner_epoch"],
            "execution_generation": state.row["generation"], "instance_id": "historical-instance"},
        "observations": [{"fields": ["messages"], "content_sha256": hashlib.sha256(raw).hexdigest(),
            "content_bytes": len(raw), "canonicalization": "json_sorted_keys_utf8_no_spaces_v1",
            "turn_id": "turn-1", "api_request_id": "request-1", "agent_session_id": "different-physical-session",
            "api_call_count": 1, "retry_count": 0}],
        "errors": [], "overflow": False, "coverage": "assembly_hooks_only",
        "provider_dispatch_proven": False, "model_identity_verified": False}


def test_original_outer_observation_is_detached_and_remains_historical(original_terminal):
    doc = observation_document(original_terminal)
    original_terminal.saved["mastermind_request_observation"] = copy.deepcopy(doc)
    result = original_terminal.read()
    assert result["request_observation"] == doc
    assert result["request_observation"]["scope"]["instance_id"] == "historical-instance"
    assert result["request_observation"]["observations"][0]["agent_session_id"] != result["admission"]["ref"]["session_id"]
    assert result["request_observation"]["provider_dispatch_proven"] is False
    assert result["request_observation"]["model_identity_verified"] is False
    assert "implementation_sha" not in result["request_observation"]
    result["request_observation"]["observations"][0]["fields"].clear()
    assert original_terminal.saved["mastermind_request_observation"] == doc
    assert original_terminal.stored_reads == ["original-admission"]


def test_inner_observation_is_not_promoted_and_legacy_absence_is_ordinary(original_terminal):
    original_terminal.saved["result"]["mastermind_request_observation"] = observation_document(original_terminal)
    result = original_terminal.read()
    assert "request_observation" not in result and "request_observation_error" not in result
    assert result["successful"] is True and result["answer"] == original_terminal.saved["result"]["final_response"]


@pytest.mark.parametrize("field,value", [
    ("role", "mmmeta"), ("session_id", "foreign"), ("admission_id", "another"),
    ("authority_epoch", 8), ("execution_generation", 4),
    ("authority_epoch", True), ("execution_generation", False),
])
def test_observation_scope_mismatch_closes_evidence_only(original_terminal, field, value):
    expected = original_terminal.read()
    doc = observation_document(original_terminal)
    doc["scope"][field] = value
    original_terminal.saved["mastermind_request_observation"] = doc
    actual = original_terminal.read()
    assert actual.pop("request_observation_error") == "INVALID_RETAINED_OBSERVATION"
    assert actual == expected


@pytest.mark.parametrize("case", [
    "outer_extra", "schema", "stage", "provider_claim", "model_claim", "false_integer", "scope_extra",
    "instance_control", "instance_utf8", "instance_bytes", "too_many_events", "event_extra", "wrong_fields",
    "duplicate_fields", "digest", "bytes_bool", "bytes_limit", "canonicalization", "identifier_control",
    "identifier_utf8", "identifier_bytes", "counter_bool", "counter_limit", "unknown_invalid_field",
    "empty_invalid_fields", "duplicate_invalid_fields", "retained_invalid_field", "unknown_error",
    "duplicate_error", "unsorted_errors", "coverage", "overflow_count", "overflow_type",
])
def test_malformed_retained_observation_never_changes_native_result(original_terminal, case):
    baseline = original_terminal.read()
    doc = observation_document(original_terminal)
    event = doc["observations"][0]
    if case == "outer_extra": doc["raw_prompt"] = "must never be forwarded"
    elif case == "schema": doc["schema"] = "future-schema"
    elif case == "stage": doc["stage"] = "provider_dispatched"
    elif case == "provider_claim": doc["provider_dispatch_proven"] = True
    elif case == "model_claim": doc["model_identity_verified"] = True
    elif case == "false_integer": doc["provider_dispatch_proven"] = 0
    elif case == "scope_extra": doc["scope"]["implementation_sha"] = "a" * 40
    elif case == "instance_control": doc["scope"]["instance_id"] = "bad\x7f"
    elif case == "instance_utf8": doc["scope"]["instance_id"] = "\ud800"
    elif case == "instance_bytes": doc["scope"]["instance_id"] = "Ω" * 129
    elif case == "too_many_events": doc["observations"] *= 9
    elif case == "event_extra": event["raw_headers"] = {"Authorization": "private"}
    elif case == "wrong_fields": event["fields"] = ["system", "messages"]
    elif case == "duplicate_fields": event["fields"] = ["messages", "messages"]
    elif case == "digest": event["content_sha256"] = "F" * 64
    elif case == "bytes_bool": event["content_bytes"] = True
    elif case == "bytes_limit": event["content_bytes"] = 4 * 1024 * 1024 + 1
    elif case == "canonicalization": event["canonicalization"] = "rfc8785"
    elif case == "identifier_control": event["turn_id"] = "a\n"
    elif case == "identifier_utf8": event["api_request_id"] = "\ud800"
    elif case == "identifier_bytes": event["agent_session_id"] = "Ω" * 129
    elif case == "counter_bool": event["api_call_count"] = True
    elif case == "counter_limit": event["retry_count"] = 2**53
    elif case == "unknown_invalid_field": event["invalid_fields"] = ["provider"]
    elif case == "empty_invalid_fields": event["invalid_fields"] = []
    elif case == "duplicate_invalid_fields": event.pop("turn_id"); event["invalid_fields"] = ["turn_id", "turn_id"]
    elif case == "retained_invalid_field": event["invalid_fields"] = ["turn_id"]
    elif case == "unknown_error": doc["errors"] = ["private error content"]
    elif case == "duplicate_error": doc["errors"] = ["content_limit", "content_limit"]
    elif case == "unsorted_errors": doc["errors"] = ["unsupported_content", "content_limit"]
    elif case == "coverage": doc["coverage"] = "complete_prompt"
    elif case == "overflow_count": doc["overflow"] = True
    elif case == "overflow_type": doc["overflow"] = 0
    original_terminal.saved["mastermind_request_observation"] = doc
    result = original_terminal.read()
    assert result.pop("request_observation_error") == "INVALID_RETAINED_OBSERVATION"
    assert result == baseline


@pytest.mark.parametrize("case", ["empty", "errors", "invalid_fields", "repeated", "content_empty", "optional_absent"])
def test_legitimate_instrumentation_limits_remain_visible(original_terminal, case):
    doc = observation_document(original_terminal)
    event = doc["observations"][0]
    if case == "empty": doc.update(observations=[], coverage="no_assembly_observation")
    elif case == "errors": doc["errors"] = ["content_limit", "observation_failed", "unbound_or_stale_agent", "unsupported_content"]
    elif case == "invalid_fields":
        event.pop("turn_id"); event.pop("retry_count")
        event["invalid_fields"] = ["turn_id", "retry_count"]
    elif case == "repeated": doc["observations"] = [copy.deepcopy(event) for _ in range(8)]; doc["overflow"] = True
    elif case == "content_empty": event.update(fields=[], content_bytes=2, content_sha256=hashlib.sha256(b"{}").hexdigest())
    elif case == "optional_absent":
        for key in ("turn_id", "api_request_id", "agent_session_id", "api_call_count", "retry_count"): event.pop(key)
    original_terminal.saved["mastermind_request_observation"] = copy.deepcopy(doc)
    result = original_terminal.read()
    assert result["request_observation"] == doc and "request_observation_error" not in result


@pytest.mark.parametrize("outcome", ["failed", "partial", "interrupted", "missing_answer", "missing_result"])
def test_observation_does_not_invent_success_or_require_an_answer(original_terminal, outcome):
    if outcome == "missing_answer": original_terminal.saved["result"].pop("final_response")
    elif outcome == "missing_result": original_terminal.saved.pop("result")
    else:
        original_terminal.saved["result"][outcome] = True
        original_terminal.row["outcome"] = outcome
    baseline = original_terminal.read()
    doc = observation_document(original_terminal)
    original_terminal.saved["mastermind_request_observation"] = doc
    result = original_terminal.read()
    assert result.pop("request_observation") == doc and result == baseline


@pytest.mark.parametrize("status", ["queued", "started", "unknown", "missing"])
def test_unsettled_original_has_no_observation_projection(original_terminal, status):
    original_terminal.saved["mastermind_request_observation"] = observation_document(original_terminal)
    if status == "missing": original_terminal.row = None
    else: original_terminal.row["status"] = status
    result = original_terminal.read()
    assert "request_observation" not in result and "request_observation_error" not in result
    if status == "missing": assert result["status"] == "EFFECT_UNKNOWN" and original_terminal.stored_reads == []


def test_huge_closed_container_is_refused_without_traversing_values(original_terminal):
    class Uninspectable:
        def __str__(self): raise AssertionError("must not stringify arbitrary retained values")
        def __repr__(self): raise AssertionError("must not stringify arbitrary retained values")
    original_terminal.saved["mastermind_request_observation"] = {str(i): Uninspectable() for i in range(10000)}
    result = original_terminal.read()
    assert result["request_observation_error"] == "INVALID_RETAINED_OBSERVATION"
    assert "request_observation" not in result and result["successful"] is True


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_same_original_reader_preserves_selected_role_contract(original_terminal, tmp_path, role):
    doc = observation_document(original_terminal)
    doc["scope"]["role"] = role
    original_terminal.saved["mastermind_request_observation"] = doc
    result = control._read_original(tmp_path, original_terminal.params, "uid:994", role=role)
    assert result["schema"] == control.conversation_contract(role).native_schema
    assert result["request_observation"] == doc


@pytest.mark.parametrize("field", ["authority_epoch", "revision", "execution_generation"])
def test_boolean_cannot_match_native_integer_identity(native, field):
    native.target[field] = 1
    native.params["target"][field] = True
    result = asyncio.run(control._submit(native.runner, native.home, native.params, "uid:994"))
    assert result["status"] == "REFUSED"
    assert native.calls == []


@pytest.mark.parametrize("payload", [
    {"operation": "observe", "session_id": "s", "ticket": "external-ticket"},
    {"operation": "submit", "target": {}, "submission_id": "s", "text": "q"},
    {"operation": "read_original", "session_id": "s", "submission_id": "op",
     "input_sha256": "G" * 64, "admission_id": None},
])
def test_role_dispatch_rejects_unqualified_input_before_wire(monkeypatch, tmp_path, payload):
    client = control.NativeSecretaryClient(tmp_path)
    monkeypatch.setattr(client, "_call", lambda *args: pytest.fail("invalid request reached native socket"))
    with pytest.raises(RuntimeRefusal):
        client.dispatch(payload)


def test_admission_fence_uses_same_transaction_and_native_busy_owner(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sessions (id TEXT, user_id TEXT, runtime_revision INTEGER, runtime_generation INTEGER)")
    conn.execute("INSERT INTO sessions VALUES ('s','uid:994',3,2)")
    conn.execute("CREATE TABLE pending (session_id TEXT)")
    target = dict(profile_id="/native/home", session_id="s", principal_id="uid:994",
                  instance_id="owner", authority_epoch=7, revision=3, execution_generation=2)
    authority = SimpleNamespace(profile_id=target["profile_id"], instance_id="owner", epoch=7, db=object())
    actor = SimpleNamespace(subject="uid:994")
    checks = []
    def snapshot(db, actual_conn, sid):
        assert db is authority.db and actual_conn is conn and sid == "s"
        checks.append("lineage")
        return {"target": "s", "receipt": dict(profile_id=target["profile_id"],
                    session_id="s", principal_id="uid:994", policy={"source": "cli"})}
    def idle(db, actual_conn, sids):
        assert db is authority.db and actual_conn is conn and sids == ["s"]
        checks.append("idle")
        if conn.execute("SELECT 1 FROM pending WHERE session_id='s'").fetchone():
            raise RuntimeError("native owner reports busy")
    module(monkeypatch, "hermes_state_mutation_prepared", local_snapshot=snapshot)
    module(monkeypatch, "hermes_state_mutation_guards", require_idle=idle)
    guard = control._admission_guard(authority, actor, target)
    with conn:
        guard(conn)
        conn.execute("INSERT INTO pending VALUES ('s')")
    with pytest.raises(control._AdmissionRefused):
        with conn:
            guard(conn)
    assert checks == ["lineage", "idle", "lineage", "idle"]
    conn.execute("DELETE FROM pending")
    conn.execute("UPDATE sessions SET runtime_generation=3")
    with pytest.raises(control._AdmissionRefused):
        guard(conn)
    assert checks == ["lineage", "idle", "lineage", "idle"]
    conn.close()


def test_explicit_original_admission_mismatch_refuses_before_result_read(original_terminal):
    original_terminal.params["admission_id"] = "different-original"
    with pytest.raises(RuntimeRefusal, match="NATIVE_SECRETARY_ORIGINAL_MISMATCH"):
        original_terminal.read()
    assert original_terminal.stored_reads == []
