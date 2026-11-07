"""DeepSeek candidate component proof; no enrollment or provider I/O."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source"),
               str(ROOT / "tests"), str(REPO)]

import application_http_transports as h
from control_plane.codex_provider_realm import (
    CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY,
    DEEPSEEK_COMMERCIAL_API,
    REVIEWED_CODEX_PROVIDER_REALMS,
    ProviderRealmError,
)

ENDPOINT = "https://api.deepseek.com/responses"


def logical(model="deepseek-flash"):
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "Use the supplied evidence."},
            {"role": "user", "content": "Read the current portfolio context."},
            {"role": "assistant", "tool_calls": [
                {"id": "call_context", "type": "function",
                 "function": {"name": "read_context", "arguments": '{"scope":"test"}'}}
            ]},
            {"role": "tool", "tool_call_id": "call_context",
             "content": '{"status":"available","positions":[]}'},
            {"role": "user", "content": "Summarize the returned context."},
        ],
        "tools": [{"type": "function", "function": {
            "name": "read_context", "description": "Read a synthetic context.",
            "parameters": {"type": "object", "properties": {"scope": {"type": "string"}}},
        }}],
        "tool_choice": "auto",
        "max_tokens": 512,
    }


class Spy:
    def __init__(self):
        self.requests = []
        self.response = None
        self.error = None

    def __call__(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.fixture
def component():
    spy = Spy()

    def candidate_fixture(realm_id):
        assert realm_id == DEEPSEEK_COMMERCIAL_API.realm_id
        return DEEPSEEK_COMMERCIAL_API, "responses"

    # This is an explicit component fixture, not a registry promotion or an
    # application admission. The separate test below proves production refusal.
    with mock.patch.object(h, "_shared_realm", side_effect=candidate_fixture):
        driver = h.DeepSeekResponsesDriver(transport=spy, clock=lambda: 1000.0)
    return driver, spy


def response(model="deepseek-flash", output=None, status=200, **fields):
    body = {
        "status": "completed", "model": model,
        "output": output if output is not None else [
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "The context has no positions."}]}
        ],
        "usage": {"input_tokens": 29, "output_tokens": 11},
        **fields,
    }
    return h.TransportResponse(
        status=status, headers={}, body=json.dumps(body).encode(),
        final_url=ENDPOINT, framing_complete=True,
    )


def permit(compiled):
    return h.DispatchPermit(
        dispatch_id="deepseek-component-1", request_digest="a" * 64,
        logical_payload_digest=compiled.logical_payload_digest,
        wire_body_digest=compiled.wire_body_digest, account="deepseek-fixture",
        model=compiled.model, lease_id="lease-fixture", expires_at=1100.0,
        dispatch_permitted=True,
    )


def binding(loader=None):
    return h.AccountBinding(
        account="deepseek-fixture",
        credential_loader=loader or (lambda account: "fixture-credential"),
    )


def test_candidate_does_not_promote_itself_or_construct_in_production():
    realm = DEEPSEEK_COMMERCIAL_API
    assert CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY[realm.realm_id] is realm
    assert realm.realm_id not in REVIEWED_CODEX_PROVIDER_REALMS
    assert realm.base_url == "https://api.deepseek.com"
    assert realm.env_key == "DEEPSEEK_API_KEY"
    assert realm.provider_alias == "deepseek"
    assert realm.commercial_api_only is True
    assert realm.interactive_subscription_only is False
    assert realm.request_max_retries == realm.stream_max_retries == 0
    with pytest.raises(h.TransportRefused, match="realm_owner_unavailable"):
        h.DeepSeekResponsesDriver(transport=Spy())


@pytest.mark.parametrize("change", [
    {"realm_id": "other-commercial"},
    {"provider_alias": "other-provider"},
    {"base_url": "https://example.invalid"},
    {"env_key": "ALIBABA_TOKEN_PLAN_KEY"},
    {"commercial_api_only": False},
    {"interactive_subscription_only": True},
    {"requires_codex_auth_file": True},
    {"request_max_retries": 1},
    {"stream_max_retries": 1},
])
def test_commercial_identity_cannot_be_repurposed(change):
    with pytest.raises(ProviderRealmError):
        replace(DEEPSEEK_COMMERCIAL_API, **change)


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro"])
def test_history_tool_pairing_controls_and_frozen_digests(component, model):
    driver, spy = component
    payload = logical(model)
    payload.update(temperature=0, reasoning_effort="none")
    compiled = driver.prepare_request(payload)
    body = json.loads(compiled.wire_body)
    assert compiled.endpoint == ENDPOINT
    assert compiled.provider == compiled.pool == "deepseek"
    assert compiled.realm_id == "deepseek-commercial-api"
    assert body["model"] == model
    assert body["reasoning"] == {"effort": "none"}
    assert body["temperature"] == 0
    assert body["stream"] is False
    assert body["max_output_tokens"] == 512
    assert [item.get("role", item.get("type")) for item in body["input"]] == [
        "system", "user", "function_call", "function_call_output", "user",
    ]
    assert body["input"][2]["call_id"] == body["input"][3]["call_id"] == "call_context"
    assert body["input"][2]["arguments"] == '{"scope":"test"}'
    assert body["input"][3]["output"] == payload["messages"][3]["content"]
    assert compiled.wire_body_digest == hashlib.sha256(compiled.wire_body).hexdigest()
    assert compiled.logical_payload_digest != compiled.wire_body_digest
    assert driver.prepare_request(copy.deepcopy(payload)) == compiled
    assert spy.requests == []


@pytest.mark.parametrize("field,value", [
    ("top_p", 1), ("parallel_tool_calls", False), ("store", False),
    ("background", False), ("previous_response_id", "prior"),
    ("conversation", "prior"), ("metadata", {}), ("include", []),
    ("response_format", {"type": "json_object"}), ("stream", True),
    ("reasoning", {"effort": "none"}), ("reasoning_effort", "high"),
    ("temperature", True), ("temperature", -0.1), ("temperature", 2.1),
    ("temperature", "0"), ("temperature", float("nan")),
    ("extra_body", {"reasoning": {"effort": "high"}}),
])
def test_unsupported_or_ignored_controls_refuse_before_transport(component, field, value):
    driver, spy = component
    payload = logical()
    payload[field] = value
    with pytest.raises(h.TransportRefused):
        driver.prepare_request(payload)
    assert spy.requests == []


@pytest.mark.parametrize("strict", [True, False, None])
def test_strict_tool_requirement_is_not_silently_lost(component, strict):
    driver, spy = component
    payload = logical()
    payload["tools"][0]["function"]["strict"] = strict
    with pytest.raises(h.TransportRefused, match="deepseek_strict_tools_unsupported"):
        driver.prepare_request(payload)
    assert spy.requests == []


@pytest.mark.parametrize("target", ["declaration", "history"])
def test_unsupported_function_name_is_not_renamed(component, target):
    driver, spy = component
    payload = logical()
    item = (payload["tools"][0] if target == "declaration"
            else payload["messages"][2]["tool_calls"][0])
    item["function"]["name"] = "context.read"
    with pytest.raises(h.TransportRefused, match="deepseek_tool_name_unsupported"):
        driver.prepare_request(payload)
    assert spy.requests == []


@pytest.mark.parametrize("change", [
    {"role": "developer", "content": "Keep this instruction."},
    {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://invalid"}}]},
])
def test_roles_and_modalities_are_never_relabelled(component, change):
    driver, spy = component
    payload = logical()
    payload["messages"][0] = change
    with pytest.raises(h.TransportRefused):
        driver.prepare_request(payload)
    assert spy.requests == []


def test_missing_model_is_not_inferred_and_output_default_is_bounded(component):
    driver, _ = component
    payload = logical()
    del payload["max_tokens"]
    compiled = driver.prepare_request(payload)
    assert compiled.max_output_tokens == 4096
    assert json.loads(compiled.wire_body)["max_output_tokens"] == 4096
    del payload["model"]
    with pytest.raises(h.TransportRefused, match="model_required"):
        driver.prepare_request(payload)


@pytest.mark.parametrize("limit", [0, -1, True, 65537, 2.5, None])
def test_output_limit_cannot_exceed_source_contract(component, limit):
    driver, _ = component
    payload = logical()
    payload["max_tokens"] = limit
    with pytest.raises(h.TransportRefused, match="invalid_max_tokens"):
        driver.prepare_request(payload)


def test_one_post_uses_bound_account_and_refuses_second_effect(component):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    owner = mock.Mock(return_value="fixture-credential")
    spy.response = response()
    observed = driver.send_prepared(compiled, permit(compiled), binding(owner))
    assert len(spy.requests) == 1
    sent = spy.requests[0]
    assert sent.method == "POST" and sent.url == ENDPOINT
    assert sent.body == compiled.wire_body
    assert sent.allow_redirects is False and sent.use_environment_proxy is False
    assert sent.timeout_seconds == 100.0
    owner.assert_called_once_with("deepseek-fixture")
    assert observed.result_status == "ok"
    assert observed.served_model == compiled.model
    assert observed.usage == {"input_tokens": 29, "output_tokens": 11}
    with pytest.raises(h.TransportRefused):
        driver.send_prepared(compiled, permit(compiled), binding(owner))
    assert len(spy.requests) == 1 and owner.call_count == 1


@pytest.mark.parametrize("model", ["another-model", None])
def test_missing_or_wrong_serving_identity_is_evidence_not_an_answer(component, model):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    spy.response = response(model=model)
    observed = driver.send_prepared(compiled, permit(compiled), binding())
    assert observed.result_status == "upstream_protocol_error"
    assert observed.normalized is None
    assert observed.served_model == model
    assert observed.usage == {"input_tokens": 29, "output_tokens": 11}


@pytest.mark.parametrize("call", [
    {"name": "unknown_tool", "arguments": "{}"},
    {"name": "read_context", "arguments": "[]"},
    {"name": "read_context", "arguments": '{"x":1,"x":2}'},
    {"name": "read_context", "arguments": "not-json"},
])
def test_unproven_tool_output_does_not_become_executable(component, call):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    spy.response = response(output=[{"type": "function_call", "call_id": "call_next", **call}])
    observed = driver.send_prepared(compiled, permit(compiled), binding())
    assert observed.result_status == "upstream_protocol_error"
    assert observed.normalized is None
    assert len(spy.requests) == 1


def test_valid_tool_output_is_returned_without_executing_it(component):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    spy.response = response(output=[{"type": "function_call", "call_id": "call_next",
                                    "name": "read_context", "arguments": '{"scope":"test"}'}])
    observed = driver.send_prepared(compiled, permit(compiled), binding())
    assert observed.result_status == "ok"
    assert observed.normalized["tool_calls"][0]["function"]["name"] == "read_context"
    assert len(spy.requests) == 1


@pytest.mark.parametrize("choice,output", [
    ("none", [{"type": "function_call", "call_id": "call_next",
               "name": "read_context", "arguments": "{}"}]),
    ("required", [{"type": "message", "role": "assistant",
                   "content": [{"type": "output_text", "text": "No tool."}]}]),
])
def test_tool_choice_mismatch_is_not_success(component, choice, output):
    driver, spy = component
    payload = logical()
    payload["tool_choice"] = choice
    compiled = driver.prepare_request(payload)
    spy.response = response(output=output)
    observed = driver.send_prepared(compiled, permit(compiled), binding())
    assert observed.result_status == "upstream_protocol_error"
    assert observed.normalized is None


def test_reasoning_output_stays_unproven(component):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    spy.response = response(output=[{"type": "reasoning", "content": []}])
    observed = driver.send_prepared(compiled, permit(compiled), binding())
    assert observed.result_status == "upstream_incomplete_output"
    assert observed.normalized is None


@pytest.mark.parametrize("outcome", ["http_error", "timeout", "partial", "redirect"])
def test_errors_and_uncertain_effects_never_retry_or_rotate(component, outcome):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    spy.response = response(status=503 if outcome == "http_error" else 200)
    if outcome == "timeout":
        spy.error = TimeoutError("fixture")
    elif outcome == "partial":
        spy.response = replace(spy.response, framing_complete=False)
    elif outcome == "redirect":
        spy.response = replace(spy.response, final_url="https://example.invalid/responses")
    observed = driver.send_prepared(compiled, permit(compiled), binding())
    assert len(spy.requests) == 1
    assert observed.disposition == ("complete" if outcome == "http_error" else "unknown")
    assert observed.normalized is None
    with pytest.raises(h.TransportRefused):
        driver.send_prepared(compiled, permit(compiled), binding())
    assert len(spy.requests) == 1


def test_changed_wire_cannot_borrow_original_permit(component):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    changed = compiled.wire_body + b" "
    tampered = replace(compiled, wire_body=changed,
                       wire_body_digest=hashlib.sha256(changed).hexdigest())
    owner = mock.Mock(return_value="fixture-credential")
    with pytest.raises(h.TransportRefused, match="wire_digest_mismatch"):
        driver.send_prepared(tampered, permit(compiled), binding(owner))
    owner.assert_not_called()
    assert spy.requests == []


@pytest.mark.parametrize("missing", ["single", "one_of_parallel"])
def test_every_historical_function_call_requires_its_output(component, missing):
    driver, spy = component
    payload = logical()
    if missing == "single":
        del payload["messages"][3]
    else:
        payload["messages"][2]["tool_calls"].append({
            "id": "call_second", "type": "function",
            "function": {"name": "read_context", "arguments": '{"scope":"second"}'},
        })
    with pytest.raises(h.TransportRefused, match="deepseek_tool_history_unpaired"):
        driver.prepare_request(payload)
    assert spy.requests == []


def test_parallel_history_preserves_all_call_and_output_identities(component):
    driver, _ = component
    payload = logical()
    payload["messages"][2]["tool_calls"].append({
        "id": "call_second", "type": "function",
        "function": {"name": "read_context", "arguments": '{"scope":"second"}'},
    })
    payload["messages"].insert(3, {
        "role": "tool", "tool_call_id": "call_second", "content": '{"scope":"second"}',
    })
    body = json.loads(driver.prepare_request(payload).wire_body)
    calls = [item["call_id"] for item in body["input"] if item.get("type") == "function_call"]
    outputs = [item["call_id"] for item in body["input"] if item.get("type") == "function_call_output"]
    assert calls == ["call_context", "call_second"]
    assert outputs == ["call_second", "call_context"]


@pytest.mark.parametrize("second_arguments,accepted", [('{"scope":"second"}', True), ("[]", False)])
def test_entire_parallel_output_is_validated_before_any_tool_return(component, second_arguments, accepted):
    driver, spy = component
    compiled = driver.prepare_request(logical())
    spy.response = response(output=[
        {"type": "function_call", "call_id": "call_first",
         "name": "read_context", "arguments": '{"scope":"first"}'},
        {"type": "function_call", "call_id": "call_second",
         "name": "read_context", "arguments": second_arguments},
    ])
    observed = driver.send_prepared(compiled, permit(compiled), binding())
    assert len(spy.requests) == 1
    if accepted:
        assert observed.result_status == "ok"
        assert [call["id"] for call in observed.normalized["tool_calls"]] == [
            "call_first", "call_second",
        ]
    else:
        assert observed.result_status == "upstream_protocol_error"
        assert observed.normalized is None


@pytest.mark.parametrize("name,accepted", [
    ("a" * 64, True), ("a" * 65, False), ("_leading", False),
    ("with.dot", False), ("with space", False), ("工具", False),
])
def test_declared_name_subset_remains_the_incumbent_bounded_grammar(component, name, accepted):
    driver, spy = component
    payload = logical()
    payload["tools"][0]["function"]["name"] = name
    payload["messages"][2]["tool_calls"][0]["function"]["name"] = name
    payload["tool_choice"] = {"type": "function", "function": {"name": name}}
    if accepted:
        body = json.loads(driver.prepare_request(payload).wire_body)
        assert body["tool_choice"]["name"] == name
    else:
        with pytest.raises(h.TransportRefused):
            driver.prepare_request(payload)
    assert spy.requests == []
