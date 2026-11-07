"""Current native original-result reader through the existing public projection.

Stored session owners are doubles. The native reader, metadata validators,
request contracts and Session Bridge projection are real; no provider runs.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import native_continuation as nc
from integrations.hermes_runtime import native_session_control as native
from integrations.hermes_runtime.tests.test_native_session_control import (
    original_terminal, observation_document,
)
from integrations.session_bridge import hermes_native as bridge
from integrations.session_bridge.schemas import BridgeError
from test_hermes_session_continuation import (
    BINDING, NATIVE_TARGET, build_request, request_event,
)


@pytest.fixture(params=nc.HERMES_KINDS)
def primary_return(original_terminal, request, monkeypatch):
    state = original_terminal
    family = nc.hermes_family(request.param)
    role = {"hermes_secretary": "mmsecretary", "hermes_meta": "mmmeta"}[family.kind]
    binding = {**BINDING, "schema": family.binding_schema,
               "profile_id": state.params["profile_id"],
               "session_id": state.params["session_id"],
               "principal_id": state.row["principal_id"]}
    target = {**NATIVE_TARGET, **{key: binding[key] for key in (
        "profile_id", "session_id", "principal_id")},
        "authority_epoch": state.row["owner_epoch"],
        "execution_generation": state.row["generation"]}
    payload = build_request(binding=binding, native_target=target)
    event = request_event(payload)
    submits = []

    def forbidden_submit(*args, **kwargs):
        submits.append((args, kwargs))
        raise AssertionError("original result projection must never submit")

    monkeypatch.setattr(native, "_submit", forbidden_submit)

    def read():
        return native._read_original(Path(state.params["profile_id"]), state.params,
                                     state.row["principal_id"], role=role)

    def project(result):
        return bridge.public_result(event, payload, commit_started=True, native_result=result)

    def observation():
        result = observation_document(state)
        result["scope"]["role"] = role
        return result

    return SimpleNamespace(state=state, family=family, role=role, payload=payload,
                           event=event, read=read, project=project,
                           observation=observation, submits=submits)


@pytest.mark.parametrize("outcome", ["completed", "failed", "missing_answer", "missing_result"])
def test_current_original_reader_preserves_answer_and_identity(primary_return, outcome):
    case = primary_return
    if outcome == "failed":
        case.state.saved["result"]["failed"] = True
        case.state.row["outcome"] = "failed"
    elif outcome == "missing_answer":
        case.state.saved["result"].pop("final_response")
    elif outcome == "missing_result":
        case.state.saved.pop("result")
    result = case.read()
    before = deepcopy(result)
    projected = case.project(result)
    assert projected == bridge.validate_public_result(projected)
    assert projected["schema"] == case.family.result_schema
    assert projected["target_ref"] == case.payload["target_ref"]
    assert projected["operation_key"] == case.payload["operation_key"]
    assert projected["read_ref"] == case.payload["read_ref"]
    assert projected["request_ref"] == case.event.command_id
    assert projected["native_input_sha256"] == case.payload["native_input_sha256"]
    assert projected["admission"]["admission_id"] == result["admission"]["admission_id"]
    assert projected["parent_consumed"] is False
    assert projected["answer"] == result.get("answer")
    assert projected["successful"] == result.get("successful")
    assert not set(projected) & bridge._TERMINAL_EXTENSIONS
    assert result == before
    assert case.state.stored_reads == ["original-admission"]
    assert case.state.closes == 1 and len(case.state.lookups) == 1
    assert case.submits == []


def test_legacy_terminal_result_keeps_the_same_public_contract(primary_return):
    case = primary_return
    current = case.read()
    legacy = {key: value for key, value in current.items()
              if key not in bridge._TERMINAL_EXTENSIONS}
    assert case.project(current) == case.project(legacy)


@pytest.mark.parametrize("mode", ["valid", "owner_error", "no_answer"])
def test_original_observation_or_error_does_not_hide_answer(primary_return, mode):
    case = primary_return
    doc = case.observation()
    if mode == "owner_error":
        doc["scope"]["admission_id"] = "foreign-admission"
    elif mode == "no_answer":
        case.state.saved["result"].pop("final_response")
    case.state.saved["mastermind_request_observation"] = doc
    result = case.read()
    if mode == "owner_error":
        assert result["request_observation_error"] == "INVALID_RETAINED_OBSERVATION"
        assert "request_observation" not in result
    else:
        assert result["request_observation"] == doc
        assert doc["scope"]["instance_id"] == "historical-instance"
    legacy = {key: value for key, value in result.items()
              if key not in bridge._TERMINAL_EXTENSIONS}
    assert case.project(result) == case.project(legacy)
    assert case.submits == []


@pytest.mark.parametrize("mutation", [
    "schema", "claim", "extra", "reported_extra", "flag", "counter_bool",
    "counter_large", "counter_float", "label_bytes", "label_control", "label_surrogate",
    "invalid_extra", "invalid_duplicate", "invalid_retained", "output_digest",
    "output_count", "output_bool", "output_extra", "missing_output",
])
def test_malformed_terminal_metadata_remains_closed(primary_return, mutation):
    result = primary_return.read()
    data = result["terminal_metadata"]
    if mutation == "schema": data["schema"] = "future-schema"
    elif mutation == "claim": data["model_identity_verified"] = True
    elif mutation == "extra": data["account"] = "must-not-be-promoted"
    elif mutation == "reported_extra": data["reported"]["served_model"] = "not-proof"
    elif mutation == "flag": data["reported"]["completed"] = 1
    elif mutation == "counter_bool": data["reported"]["api_calls"] = True
    elif mutation == "counter_large": data["reported"]["api_calls"] = 2**53
    elif mutation == "counter_float": data["reported"]["api_calls"] = 2.0
    elif mutation == "label_bytes": data["reported"]["model"] = "é" * 129
    elif mutation == "label_control": data["reported"]["model"] = "bad\x7f"
    elif mutation == "label_surrogate": data["reported"]["model"] = "bad\ud800"
    elif mutation == "invalid_extra": data["invalid_fields"] = ["account"]
    elif mutation == "invalid_duplicate": data["invalid_fields"] = ["response_reused"] * 2
    elif mutation == "invalid_retained": data["invalid_fields"] = ["model"]
    elif mutation == "output_digest": data["output"]["sha256"] = "f" * 64
    elif mutation == "output_count": data["output"]["utf8_bytes"] += 1
    elif mutation == "output_bool": data["output"]["utf8_bytes"] = True
    elif mutation == "output_extra": data["output"]["raw"] = result["answer"]
    elif mutation == "missing_output": data["output"] = None
    with pytest.raises((ValueError, UnicodeError)):
        primary_return.project(result)


def test_native_invalid_field_projection_stays_valid(primary_return):
    case = primary_return
    case.state.saved["result"].update(api_calls=True, model="bad\nlabel", partial="unknown")
    result = case.read()
    assert result["terminal_metadata"]["invalid_fields"] == ["partial", "model", "api_calls"]
    assert case.project(result)["answer"] == result["answer"]


@pytest.mark.parametrize("mutation", ["role", "session", "admission", "epoch", "generation",
                                     "claim", "extra", "event_limit", "ambiguous"])
def test_observation_uses_the_original_full_admission(primary_return, mutation):
    case = primary_return
    result = case.read()
    doc = case.observation()
    result["request_observation"] = doc
    if mutation == "role": doc["scope"]["role"] = "mmmeta" if case.role == "mmsecretary" else "mmsecretary"
    elif mutation == "session": doc["scope"]["session_id"] = "foreign-session"
    elif mutation == "admission": doc["scope"]["admission_id"] = "foreign-admission"
    elif mutation == "epoch": doc["scope"]["authority_epoch"] += 1
    elif mutation == "generation": doc["scope"]["execution_generation"] += 1
    elif mutation == "claim": doc["provider_dispatch_proven"] = True
    elif mutation == "extra": doc["raw_headers"] = {}
    elif mutation == "event_limit": doc["observations"] *= 9
    elif mutation == "ambiguous": result["request_observation_error"] = "INVALID_RETAINED_OBSERVATION"
    with pytest.raises(ValueError):
        case.project(result)


@pytest.mark.parametrize("status", ["queued", "started", "unknown"])
def test_extensions_never_make_a_nonterminal_result_terminal(primary_return, status):
    case = primary_return
    terminal = case.read()
    case.state.row["status"] = status
    pending = case.read()
    assert case.project(pending)["answer"] is None
    pending["terminal_metadata"] = terminal["terminal_metadata"]
    with pytest.raises(ValueError):
        case.project(pending)


def test_extensions_cannot_expand_other_result_shapes(primary_return):
    case = primary_return
    result = case.read()
    for extra in ({"arbitrary": {}}, {"request_observation_error": "UNKNOWN_REASON"}):
        with pytest.raises(ValueError):
            case.project({**result, **extra})
    result["status"] = "ADMITTED"
    with pytest.raises(ValueError):
        case.project(result)


def test_foreign_native_session_is_refused_before_observation_projection(primary_return, monkeypatch):
    case = primary_return
    result = case.read()
    result["request_observation"] = case.observation()
    result["admission"]["ref"]["session_id"] = "foreign-session"
    calls = []
    monkeypatch.setattr(native, "_request_observation", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ValueError):
        case.project(result)
    assert calls == []


def test_private_extensions_do_not_expand_public_output_limit(primary_return):
    case = primary_return
    case.state.saved["result"]["final_response"] = "x" * bridge.MAX_PUBLIC_RESULT_BYTES
    result = case.read()
    with pytest.raises(BridgeError, match="original answer exceeds"):
        case.project(result)
    assert case.submits == []
