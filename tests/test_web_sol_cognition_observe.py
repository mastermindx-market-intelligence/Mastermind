from __future__ import annotations

import copy

import pytest

from integrations.chairman_surfaces import web_sol_protocol as wsp
from tests import test_web_sol_cognition_submit as cognition


SESSION_ALIAS = "EXECUTIVE-CEO-A"
DOCUMENT_EPOCH = "f" * 32


def request(**overrides):
    value = cognition.request(
        action="OBSERVE_COGNITION_RESULT",
        cognition_observe_payload=cognition.cognition._observe(),
        session_alias=SESSION_ALIAS,
    )
    value.pop("cognition_payload")
    value.update(overrides)
    return value


def result_observation(**overrides):
    value = cognition.cognition._ready_observation(
        runtime_binding_id=request()["runtime_binding_id"],
        runtime_binding_generation=1,
        runtime_binding_fingerprint=request()["runtime_binding_fingerprint"],
    )
    value.update(overrides)
    return value


def receipt(req=None, status="COGNITION_RESULT_READY", *, observation=None, **probe):
    req = req or request()
    probe.setdefault(
        "generation_state", "idle" if status == "COGNITION_RESULT_READY" else "unknown"
    )
    value = {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": req["binding_id"],
        "conversation_fingerprint": req["conversation_fingerprint"],
        "binding_fingerprint": req["binding_fingerprint"],
        "action": req["action"],
        "operation_key": req["operation_key"],
        "nonce": req["nonce"],
        "status": status,
        "observed_at": req["issued_at"],
        "observation": cognition.observation(
            generation_state=probe.pop("generation_state", "unknown"),
            **probe,
        ),
        "session_alias": req["session_alias"],
        "runtime_binding_id": req["runtime_binding_id"],
        "runtime_binding_generation": req["runtime_binding_generation"],
        "runtime_binding_fingerprint": req["runtime_binding_fingerprint"],
        "cognition_observation": observation,
    }
    return value


def ready(**overrides):
    observation = overrides.pop("observation", False)
    if observation is False:
        observation = result_observation()
    probe = cognition.observation()
    for field in ("generation_state", "auth_required", "provider_error_present"):
        if field in overrides:
            probe[field] = overrides.pop(field)
    value = receipt(observation=observation, **overrides)
    if isinstance(observation, dict) and "schema" in observation:
        value["observation"] = probe
    return value


def test_observe_cognition_result_is_a_closed_nonmutating_action():
    actions = {item.value for item in wsp.SurfaceAction}
    statuses = {item.value for item in wsp.ReceiptStatus}
    assert "OBSERVE_COGNITION_RESULT" in actions
    assert {
        "COGNITION_RESULT_READY",
        "COGNITION_RESULT_PENDING",
        "COGNITION_RESULT_REFUSED",
    } <= statuses


def test_request_is_closed_validated_and_detached():
    req = request()
    accepted = wsp.validate_request(req)
    assert accepted == req
    assert accepted is not req
    assert accepted["cognition_observe_payload"] is not req["cognition_observe_payload"]
    for forbidden in ("prompt", "message", "text", "selector", "url", "retry"):
        with pytest.raises(wsp.WebSolProtocolError):
            wsp.validate_request({**req, forbidden: "caller-controlled"})


@pytest.mark.parametrize(
    "field",
    ["runtime_binding_id", "runtime_binding_generation", "runtime_binding_fingerprint"],
)
def test_request_requires_inner_outer_runtime_binding_equality(field):
    req = request()
    if field == "runtime_binding_generation":
        req[field] += 1
    elif field == "runtime_binding_id":
        req[field] = "bind-wsx-" + ("f" * 48)
    else:
        req[field] = "f" * 64
    with pytest.raises(wsp.WebSolProtocolError, match=field):
        wsp.validate_request(req)


@pytest.mark.parametrize("role", [[], {}, True, 0, None])
def test_malformed_inner_role_is_a_typed_refusal(role):
    req = request()
    req["cognition_observe_payload"]["role"] = role
    with pytest.raises(wsp.WebSolProtocolError, match="result observe payload refused"):
        wsp.validate_request(req)


@pytest.mark.parametrize("status", ["COGNITION_RESULT_PENDING", "COGNITION_RESULT_REFUSED"])
def test_nonready_observation_transports_no_result(status):
    observation = result_observation(
        status=status,
        provider_native_turn_id=None,
        provider_turn_artifact_digest=None,
        result=None,
        result_digest=None,
        result_byte_length=0,
    )
    accepted = wsp.validate_receipt(ready(status=status, observation=observation))
    assert accepted["status"] == status
    assert accepted["cognition_observation"]["result"] is None
    assert accepted["cognition_observation"]["provider_native_turn_id"] is None


def test_ready_receipt_is_detached_and_requires_idle_healthy_exact_target():
    original = ready()
    accepted = wsp.validate_receipt(original)
    assert accepted["status"] == "COGNITION_RESULT_READY"
    assert accepted["cognition_observation"] is not original["cognition_observation"]
    for field in ("generation_state", "auth_required", "provider_error_present"):
        kwargs = {field: "active" if field == "generation_state" else True}
        with pytest.raises(wsp.WebSolProtocolError, match=field):
            wsp.validate_receipt(ready(**kwargs))


def test_result_statuses_require_a_real_non_null_observation():
    for status in ("COGNITION_RESULT_READY", "COGNITION_RESULT_PENDING", "COGNITION_RESULT_REFUSED"):
        with pytest.raises(wsp.WebSolProtocolError, match="cognition_observation"):
            wsp.validate_receipt(ready(status=status, observation=None))


def test_result_status_and_inner_runtime_binding_must_match_outer():
    value = ready()
    value["cognition_observation"]["status"] = "COGNITION_RESULT_PENDING"
    with pytest.raises(wsp.WebSolProtocolError, match="cognition result observation"):
        wsp.validate_receipt(value)

    value = ready()
    value["runtime_binding_generation"] += 1
    with pytest.raises(wsp.WebSolProtocolError, match="runtime_binding_generation"):
        wsp.validate_receipt(value)


def test_generic_preread_refusals_use_null_observation_without_fabrication():
    for status in ("TARGET_NOT_FOUND", "TARGET_CHANGED", "AUTH_REQUIRED", "PROVIDER_ERROR"):
        observation = cognition.observation()
        if status == "TARGET_NOT_FOUND":
            observation["target_present"] = False
        if status == "TARGET_CHANGED":
            observation["exact_conversation_loaded"] = False
        if status == "AUTH_REQUIRED":
            observation["auth_required"] = True
        if status == "PROVIDER_ERROR":
            observation["provider_error_present"] = True
        value = receipt(status=status, observation=None)
        value["observation"] = observation
        accepted = wsp.validate_receipt(value)
        assert accepted["cognition_observation"] is None


@pytest.mark.parametrize("malformed", [[], {}, True, 0, "observation"])
def test_malformed_observation_is_bounded_and_never_leaks_type_error(malformed):
    with pytest.raises(wsp.WebSolProtocolError, match="cognition result observation"):
        wsp.validate_receipt(ready(observation=malformed))


@pytest.mark.parametrize("malformation", ["nested_extra", "private_field"])
def test_nested_observation_extras_and_private_fields_are_refused(malformation):
    observation = result_observation()
    if malformation == "nested_extra":
        observation["result"]["extra"] = "forbidden"
    else:
        observation["result"]["transcript"] = "private"
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(ready(observation=observation))


def test_self_consistent_forged_canonical_ready_is_refused_by_result_owner():
    observation = result_observation()
    observation["result"]["summary"] = []  # type: ignore[assignment]
    encoded = cognition.cognition._canonical(observation["result"])
    observation["result_digest"] = cognition.cognition._digest(observation["result"])
    observation["result_byte_length"] = len(encoded)
    with pytest.raises(wsp.WebSolProtocolError, match="cognition result observation"):
        wsp.validate_receipt(ready(observation=observation))


@pytest.mark.parametrize("extra", ["document_epoch", "expected_document_epoch"])
def test_epoch_is_observed_by_extension_never_supplied_by_caller(extra):
    req = request()
    assert "document_epoch" not in req
    assert wsp.validate_request(req) == req
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request({**req, extra: "d" * 32})
    answer = ready(observation=result_observation(document_epoch="d" * 32))
    assert wsp.validate_receipt(answer)["cognition_observation"]["document_epoch"] == "d" * 32


@pytest.mark.parametrize("invalid", ["UNKNOWN", [], {}, True, None])
def test_unknown_action_never_leaks_typeerror(invalid):
    req = request(action=invalid)
    req.pop("cognition_observe_payload")
    for field in wsp._COGNITION_BINDING_PAYLOAD_KEYS:
        req.pop(field)
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(req)


@pytest.mark.parametrize("field,value", [
    ("page_responsive", False), ("auth_required", None),
    ("provider_error_present", None),
])
def test_ready_needs_confirmed_healthy_probe(field, value):
    answer = ready()
    answer["observation"][field] = value
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(answer)


@pytest.mark.parametrize("status", sorted(wsp._COGNITION_OBSERVE_REFUSAL_STATUSES))
def test_preread_refusal_has_no_result_data(status):
    answer = ready(status=status)
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(answer)
    answer["cognition_observation"] = None
    if status == "AUTH_REQUIRED":
        answer["observation"]["auth_required"] = True
    if status == "PROVIDER_ERROR":
        answer["observation"]["provider_error_present"] = True
    if status == "TARGET_CHANGED":
        answer["observation"]["exact_conversation_loaded"] = False
    if status == "TARGET_NOT_FOUND":
        answer["observation"]["target_present"] = False
        answer["observation"]["exact_conversation_loaded"] = False
    assert wsp.validate_receipt(answer)["cognition_observation"] is None


def test_submit_receipt_still_validates_runtime_fingerprint():
    req = cognition.request()
    answer = cognition.receipt(req=req, status="COGNITION_NOT_SUBMITTED")
    answer["runtime_binding_fingerprint"] = "not-a-fingerprint"
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(answer)


def test_canonical_review_findings_message_is_narrowly_permitted():
    import hashlib
    import json
    observation = result_observation(role="review")
    result = observation["result"]
    result["role"] = "review"
    role = result["role_result"]
    for field in ("artifacts",):
        role.pop(field)
    role.update(schema_version="mastermind.review_result/v1",
                reviewed_job_id="JOB-REVIEWED", reviewed_attempt_id="ATT-REVIEWED",
                reviewed_result_digest="5" * 64, verdict="approve",
                findings=[{"code":"OBSERVATION", "severity":"info",
                           "message":"A bounded canonical review finding.",
                           "evidence_digests":["8" * 64]}])
    def seal():
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        observation["result_byte_length"] = len(encoded)
        observation["result_digest"] = hashlib.sha256(encoded).hexdigest()
    seal()
    answer = ready(observation=observation)
    assert wsp.validate_receipt(answer)["cognition_observation"]["result"] == result
    for forbidden in ("transcript", "text", "cookie", "prompt"):
        bad = copy.deepcopy(answer)
        bad["cognition_observation"]["result"]["role_result"]["findings"][0][forbidden] = "private"
        with pytest.raises(wsp.WebSolProtocolError):
            wsp.validate_receipt(bad)
    bad = copy.deepcopy(answer)
    bad["cognition_observation"]["message"] = "not a typed review finding"
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(bad)
