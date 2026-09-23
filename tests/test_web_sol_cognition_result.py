from __future__ import annotations

import hashlib
import json

import pytest

from integrations.chairman_surfaces.web_sol_cognition_result import (
    MAX_WEB_SOL_COGNITION_RESULT_BYTES,
    WebSolCognitionResultError,
    build_raw_role_result_observation,
)


def _value() -> dict[str, object]:
    return {
        "schema_version": "mastermind.executive_orchestration_result/v1",
        "job_id": "JOB-200",
        "run_id": "ATT-200",
        "worker_id": "web-sol-pro-3",
        "role": "work",
        "status": "COMPLETED",
        "role_result": {
            "schema_version": "mastermind.work_result/v1",
            "root_job_id": "JOB-ROOT",
            "plan_attempt_id": "ATT-PLAN",
            "plan_digest": "b" * 64,
            "plan_step_id": "research-1",
            "repair_round": 0,
            "artifacts": [],
            "evidence_digests": ["a" * 64],
        },
        "summary": "Read-only Pro research identified the bounded repair and evidence.",
        "current_state": "Research synthesis is complete; implementation remains external.",
        "next_actions": ["Route the accepted repair to a write-capable worker."],
        "errors": [],
        "validations": [],
    }


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _build(text: str, **overrides):
    arguments = {
        "expected_job_id": "JOB-200",
        "expected_run_id": "ATT-200",
        "expected_worker_id": "web-sol-pro-3",
        "expected_role": "work",
        "expected_root_job_id": "JOB-ROOT",
        "session_epoch_id": "epoch-200",
        "process_generation_id": "generation-200",
        "turn_id": "turn-200",
        "provider_session_id": "provider-session-200",
        "provider_native_turn_id": "assistant-turn-200",
        "provider_turn_artifact_digest": "f" * 64,
    }
    arguments.update(overrides)
    return build_raw_role_result_observation(text, **arguments)


def test_builds_existing_raw_role_result_observation_from_exact_canonical_result() -> None:
    text = _canonical(_value())

    observed = _build(text)

    assert observed.schema_version == "mastermind.operator_raw_role_result_observation/v1"
    assert observed.attempt_id == "ATT-200"
    assert observed.provider_native_turn_id == "assistant-turn-200"
    assert observed.canonical_result_json == text
    assert observed.canonical_result_byte_length == len(text.encode("utf-8"))
    assert observed.canonical_result_digest == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert "<private>" in repr(observed)
    assert text not in repr(observed)


def test_refuses_noncanonical_or_wrapped_assistant_text() -> None:
    text = json.dumps(_value(), indent=2)

    with pytest.raises(WebSolCognitionResultError) as excinfo:
        _build(text)

    assert excinfo.value.code == "RESULT_REFUSED"


def test_refuses_exact_outer_identity_drift() -> None:
    value = _value()
    value["worker_id"] = "wrong-worker"

    with pytest.raises(WebSolCognitionResultError) as excinfo:
        _build(_canonical(value))

    assert excinfo.value.code == "RESULT_REFUSED"


def test_refuses_root_job_drift_inside_existing_role_result() -> None:
    value = _value()
    role_result = dict(value["role_result"])
    role_result["root_job_id"] = "JOB-OTHER"
    value["role_result"] = role_result

    with pytest.raises(WebSolCognitionResultError) as excinfo:
        _build(_canonical(value))

    assert excinfo.value.code == "RESULT_REFUSED"


def test_applies_browser_return_budget_before_runtime_ingestion() -> None:
    value = _value()
    value["next_actions"] = [
        f"{index}:" + ("x" * 4000) for index in range(16)
    ]
    text = _canonical(value)
    assert len(text.encode("utf-8")) > MAX_WEB_SOL_COGNITION_RESULT_BYTES

    with pytest.raises(WebSolCognitionResultError) as excinfo:
        _build(text)

    assert excinfo.value.code == "RESULT_TOO_LARGE"


def test_refuses_invalid_provider_metadata_without_reclassifying_the_result() -> None:
    text = _canonical(_value())

    with pytest.raises(WebSolCognitionResultError) as excinfo:
        _build(text, provider_turn_artifact_digest="not-a-digest")

    assert excinfo.value.code == "RESULT_METADATA_REFUSED"


@pytest.mark.parametrize(
    "secret_text",
    [
        "credential sk-ant-abcdefghij",
        "contact operator@example.com",
        "MASTERMIND_AUTH_TOKEN is configured",
        "TOKEN=plainvalue",
    ],
)
def test_native_boundary_rejects_redaction_triggering_result_content(secret_text: str) -> None:
    value = _value()
    value["current_state"] = secret_text

    with pytest.raises(WebSolCognitionResultError) as excinfo:
        _build(_canonical(value))

    assert excinfo.value.code == "RESULT_REFUSED"


def test_native_boundary_rejects_exact_environment_secret_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain_secret = "plainenglishcredential"
    monkeypatch.setenv("WEB_SOL_TEST_TOKEN", plain_secret)
    value = _value()
    value["summary"] = f"provider returned {plain_secret}"

    with pytest.raises(WebSolCognitionResultError) as excinfo:
        _build(_canonical(value))

    assert excinfo.value.code == "RESULT_REFUSED"
