from __future__ import annotations

import copy
import hashlib
import json

import pytest

from integrations.chairman_surfaces.web_sol_cognition_transport import (
    ASSIGNMENT_SCHEMA,
    MAX_ASSIGNMENT_BYTES,
    MAX_RESULT_BYTES,
    MAX_TRANSPORT_PAYLOAD_BYTES,
    OBSERVE_PAYLOAD_SCHEMA,
    RESULT_OBSERVATION_SCHEMA,
    SUBMIT_PAYLOAD_SCHEMA,
    WebSolCognitionTransportError,
    build_assignment_submit_payload,
    build_result_observe_payload,
    validate_assignment_submit_payload,
    validate_result_observation,
    validate_result_observe_payload,
)


JOB_ID = "JOB-200"
ATTEMPT_ID = "ATT-200"
WORKER_ID = "web-sol-pro-3"
ROOT_JOB_ID = "JOB-ROOT"
TURN_ID = "ohf-turn-cognition-0001"
BINDING_ID = "bind-wsx-" + ("c" * 48)
BINDING_FINGERPRINT = "d" * 64
ASSIGNMENT_DIGEST = "a" * 64
RESULT_SCHEMA_DIGEST = "b" * 64
CONVERSATION_FP = "e" * 64
DOCUMENT_EPOCH = "f" * 32
PROVIDER_TURN_ID = "provider-turn-200"
PROVIDER_ARTIFACT_DIGEST = "1" * 64


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _result_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "job_id": {"const": JOB_ID},
            "run_id": {"const": ATTEMPT_ID},
            "worker_id": {"const": WORKER_ID},
            "role": {"const": "work"},
            "role_result": {
                "type": "object",
                "properties": {"root_job_id": {"const": ROOT_JOB_ID}},
            },
        },
    }


def _assignment() -> dict:
    schema = _result_schema()
    return {
        "continuation": {
            "schema_version": "mastermind.web_sol_continuation/v1",
            "workstream": "WS:TARGET",
            "agentos_source_sha": "2" * 40,
            "next_action": "Analyze the bounded evidence and return the exact result envelope.",
            "blockers": [],
            "do_not_redo": ["DONE-1"],
            "evidence": [],
        },
        "continuation_digest": "3" * 64,
        "effect_contract": {
            "allowed_write_paths": [],
            "external_effects_allowed": False,
            "requested_authorities": ["READ", "RESEARCH"],
        },
        "job": {
            "attempt_id": ATTEMPT_ID,
            "job_id": JOB_ID,
            "objective": "Analyze the supplied bounded evidence and synthesize the result.",
            "plan_attempt_id": "ATT-PLAN",
            "plan_digest": "4" * 64,
            "plan_step_id": "research-1",
            "quota_class": "chatgpt-pro",
            "repair_round": 0,
            "review_required": True,
            "reviews_job_id": None,
            "role": "work",
            "root_job_id": ROOT_JOB_ID,
            "worker_id": WORKER_ID,
        },
        "result_contract": {
            "schema": schema,
            "schema_digest": _digest(schema),
        },
        "schema_version": ASSIGNMENT_SCHEMA,
        "source": {
            "work_ref": "WS:TARGET",
            "commission_ref": {
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": "5" * 40,
                "path": "research/executive_commissions/COMMISSION.md",
                "content_sha256": "6" * 64,
            },
            "dialogue_source_digest": "7" * 64,
        },
    }


def _submit(**overrides):
    assignment = overrides.pop("assignment", _assignment())
    args = {
        "assignment": assignment,
        "turn_id": TURN_ID,
        "runtime_binding_id": BINDING_ID,
        "runtime_binding_generation": 1,
        "runtime_binding_fingerprint": BINDING_FINGERPRINT,
        "job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "worker_id": WORKER_ID,
        "root_job_id": ROOT_JOB_ID,
        "role": "work",
    }
    args.update(overrides)
    return build_assignment_submit_payload(**args)


def _observe(**overrides):
    submit = _submit()
    args = {
        "turn_id": TURN_ID,
        "assignment_digest": submit["assignment_digest"],
        "result_schema_digest": submit["result_schema_digest"],
        "runtime_binding_id": BINDING_ID,
        "runtime_binding_generation": 1,
        "runtime_binding_fingerprint": BINDING_FINGERPRINT,
        "job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "worker_id": WORKER_ID,
        "root_job_id": ROOT_JOB_ID,
        "role": "work",
    }
    args.update(overrides)
    return build_result_observe_payload(**args)


def _result() -> dict:
    return {
        "current_state": "The bounded analysis is complete.",
        "errors": [],
        "job_id": JOB_ID,
        "next_actions": ["Route implementation to a write-capable worker."],
        "role": "work",
        "role_result": {
            "schema_version": "mastermind.work_result/v1",
            "root_job_id": ROOT_JOB_ID,
            "plan_attempt_id": "ATT-PLAN",
            "plan_digest": "4" * 64,
            "plan_step_id": "research-1",
            "repair_round": 0,
            "artifacts": [],
            "evidence_digests": ["8" * 64],
        },
        "run_id": ATTEMPT_ID,
        "schema_version": "mastermind.executive_orchestration_result/v1",
        "status": "COMPLETED",
        "summary": "Bounded cognition result.",
        "validations": [],
        "worker_id": WORKER_ID,
    }


def _ready_observation(**overrides):
    result = overrides.pop("result", _result())
    observe = _observe()
    value = {
        "schema": RESULT_OBSERVATION_SCHEMA,
        "status": "COGNITION_RESULT_READY",
        "turn_id": TURN_ID,
        "assignment_digest": observe["assignment_digest"],
        "result_schema_digest": observe["result_schema_digest"],
        "runtime_binding_id": BINDING_ID,
        "runtime_binding_generation": 1,
        "runtime_binding_fingerprint": BINDING_FINGERPRINT,
        "job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "worker_id": WORKER_ID,
        "root_job_id": ROOT_JOB_ID,
        "role": "work",
        "document_epoch": DOCUMENT_EPOCH,
        "provider_native_turn_id": PROVIDER_TURN_ID,
        "provider_turn_artifact_digest": PROVIDER_ARTIFACT_DIGEST,
        "result": result,
        "result_digest": _digest(result),
        "result_byte_length": len(_canonical(result)),
    }
    value.update(overrides)
    return value


def test_submit_payload_is_closed_canonical_and_effect_free() -> None:
    payload = _submit()

    assert payload["schema"] == SUBMIT_PAYLOAD_SCHEMA
    assert payload["assignment"]["schema_version"] == ASSIGNMENT_SCHEMA
    assert payload["assignment_digest"] == _digest(payload["assignment"])
    assert payload["result_schema_digest"] == _digest(
        payload["assignment"]["result_contract"]["schema"]
    )
    assert payload["assignment"]["effect_contract"] == {
        "allowed_write_paths": [],
        "external_effects_allowed": False,
        "requested_authorities": ["READ", "RESEARCH"],
    }
    assert len(_canonical(payload["assignment"])) <= MAX_ASSIGNMENT_BYTES
    assert len(_canonical(payload)) <= MAX_TRANSPORT_PAYLOAD_BYTES


@pytest.mark.parametrize("field", ["prompt", "message", "text", "instruction", "transcript"])
def test_submit_payload_rejects_generic_caller_content(field: str) -> None:
    payload = _submit()
    payload[field] = "caller-controlled"

    with pytest.raises(WebSolCognitionTransportError, match="unknown keys"):
        validate_assignment_submit_payload(payload)


def test_submit_payload_rejects_assignment_identity_or_effect_drift() -> None:
    assignment = _assignment()
    assignment["job"]["worker_id"] = "wrong-worker"
    with pytest.raises(WebSolCognitionTransportError, match="worker_id"):
        _submit(assignment=assignment)

    assignment = _assignment()
    assignment["effect_contract"]["external_effects_allowed"] = True
    with pytest.raises(WebSolCognitionTransportError, match="external_effects_allowed"):
        _submit(assignment=assignment)

    assignment = _assignment()
    assignment["effect_contract"]["allowed_write_paths"] = ["src/owned.py"]
    with pytest.raises(WebSolCognitionTransportError, match="allowed_write_paths"):
        _submit(assignment=assignment)


def test_submit_payload_rejects_result_schema_identity_drift() -> None:
    assignment = _assignment()
    assignment["result_contract"]["schema"]["properties"]["run_id"] = {"const": "ATT-OTHER"}
    assignment["result_contract"]["schema_digest"] = _digest(
        assignment["result_contract"]["schema"]
    )

    with pytest.raises(WebSolCognitionTransportError, match="run_id"):
        _submit(assignment=assignment)


def test_submit_payload_rejects_private_transport_fields_inside_assignment() -> None:
    assignment = _assignment()
    assignment["continuation"]["transcript"] = "must never cross"

    with pytest.raises(WebSolCognitionTransportError, match="transcript"):
        _submit(assignment=assignment)


def test_submit_payload_enforces_assignment_budget() -> None:
    assignment = _assignment()
    assignment["job"]["objective"] = "x" * MAX_ASSIGNMENT_BYTES

    with pytest.raises(WebSolCognitionTransportError, match="assignment exceeds"):
        _submit(assignment=assignment)


def test_observe_payload_has_no_assignment_or_generic_text() -> None:
    payload = _observe()

    assert payload["schema"] == OBSERVE_PAYLOAD_SCHEMA
    assert "assignment" not in payload
    assert len(_canonical(payload)) <= MAX_TRANSPORT_PAYLOAD_BYTES

    for forbidden in ("assignment", "prompt", "message", "text", "transcript"):
        tampered = dict(payload)
        tampered[forbidden] = {}
        with pytest.raises(WebSolCognitionTransportError, match="unknown keys"):
            validate_result_observe_payload(tampered)


def test_ready_result_observation_round_trips_canonical_result_object() -> None:
    observation = validate_result_observation(_ready_observation())

    assert observation["status"] == "COGNITION_RESULT_READY"
    assert observation["result_digest"] == _digest(observation["result"])
    assert observation["result_byte_length"] == len(_canonical(observation["result"]))
    assert observation["result"]["role_result"]["root_job_id"] == ROOT_JOB_ID
    assert len(_canonical(observation["result"])) <= MAX_RESULT_BYTES
    assert len(_canonical(observation)) <= MAX_TRANSPORT_PAYLOAD_BYTES


@pytest.mark.parametrize("status", ["COGNITION_RESULT_PENDING", "COGNITION_RESULT_REFUSED"])
def test_nonready_result_observation_carries_no_result_or_provider_turn(status: str) -> None:
    value = _ready_observation(
        status=status,
        provider_native_turn_id=None,
        provider_turn_artifact_digest=None,
        result=None,
        result_digest=None,
        result_byte_length=0,
    )

    accepted = validate_result_observation(value)
    assert accepted["result"] is None
    assert accepted["provider_native_turn_id"] is None


def test_ready_result_observation_refuses_identity_digest_or_private_field_drift() -> None:
    with pytest.raises(WebSolCognitionTransportError, match="root_job_id"):
        validate_result_observation(_ready_observation(root_job_id="JOB-OTHER"))

    bad = _ready_observation()
    bad["result"]["summary"] = "changed after digest"
    with pytest.raises(WebSolCognitionTransportError, match="result_digest"):
        validate_result_observation(bad)

    bad = _ready_observation()
    bad["result"]["role_result"]["transcript"] = "no"
    bad["result_digest"] = _digest(bad["result"])
    bad["result_byte_length"] = len(_canonical(bad["result"]))
    with pytest.raises(WebSolCognitionTransportError, match="transcript"):
        validate_result_observation(bad)


def test_ready_result_observation_enforces_result_budget() -> None:
    result = _result()
    result["summary"] = "x" * MAX_RESULT_BYTES
    value = _ready_observation(result=result)

    with pytest.raises(WebSolCognitionTransportError, match="result exceeds"):
        validate_result_observation(value)


def test_payload_schemas_remain_separate_from_existing_surface_action_schema() -> None:
    assert SUBMIT_PAYLOAD_SCHEMA != "mastermind.web_sol_surface_action.v1"
    assert OBSERVE_PAYLOAD_SCHEMA != "mastermind.web_sol_surface_action.v1"
    assert RESULT_OBSERVATION_SCHEMA != "mastermind.web_sol_surface_receipt.v1"
