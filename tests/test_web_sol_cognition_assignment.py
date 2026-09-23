from __future__ import annotations

import dataclasses
import json

import pytest

from common.commission_ref import CommissionRef
from control_plane.executive_runtime import (
    Attempt,
    AttemptStatus,
    ExecutiveDialogueSource,
    Job,
    JobStatus,
)
from control_plane.web_sol_cognition_assignment import (
    ASSIGNMENT_SCHEMA,
    MAX_RENDERED_ASSIGNMENT_BYTES,
    WebSolCognitionAssignmentError,
    build_web_sol_cognition_assignment,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
NATIVE_FRAME_BYTES = 64 * 1024
FRAME_RESERVE_BYTES = 16 * 1024


def _agentos() -> dict:
    return {
        "available": True,
        "source_sha": "c" * 40,
        "state": {
            "schema": "agent_os_state.v1",
            "workstreams": [
                {
                    "key": "TARGET",
                    "status": "active",
                    "program": "program-a",
                    "owner": "ceo-sol",
                    "p0": "EXECUTIVE_OS",
                    "next_action": "Research the current failure and return evidence.",
                    "blocked_by": [],
                    "wait": None,
                    "needs_ceo": None,
                    "claim": None,
                    "collisions": [],
                    "source": "agentos/workstreams/WS-TARGET.md",
                    "wave_detail": [
                        {
                            "id": "DONE-1",
                            "status": "done",
                            "depends_on": [],
                            "deps_satisfied": True,
                            "next_action": "done",
                            "prs": [1],
                            "wait": None,
                        },
                        {
                            "id": "W2",
                            "status": "in_progress",
                            "depends_on": ["DONE-1"],
                            "deps_satisfied": True,
                            "next_action": "Inspect evidence and synthesize a repair brief.",
                            "prs": [2],
                            "wait": None,
                        },
                    ],
                }
            ],
        },
        "contexts": [
            {
                "schema": "context_bundle.v1",
                "generated_at": "2026-09-23T09:00:00Z",
                "source_records_digest": "sha256:" + "d" * 64,
                "target": {"workstream": "WS:TARGET"},
                "sections": [
                    {
                        "id": "workstream",
                        "items": [
                            {
                                "kind": "workstream",
                                "key": "WS:TARGET",
                                "path": "agentos/workstreams/WS-TARGET.md",
                                "locator": "agentos/workstreams/WS-TARGET.md#frontmatter",
                                "authority_class": "A4",
                                "status": "active",
                                "updated": "2026-09-23",
                                "excerpt": "private raw context that must not cross",
                                "why_included": "private raw context that must not cross",
                            }
                        ],
                    }
                ],
            }
        ],
        "warnings": [],
    }


def _source() -> ExecutiveDialogueSource:
    return ExecutiveDialogueSource(
        schema_version="mastermind.executive_dialogue_source/v1",
        work_ref="WS:TARGET",
        commission_ref=CommissionRef(
            repository="mastermindx-market-intelligence/Mastermind",
            commit="e" * 40,
            path="research/executive_commissions/COMMISSION.md",
            content_sha256="f" * 64,
        ),
        watch_mode=None,
    )


def _job(*, role: str = "work", authorities: list[str] | None = None) -> Job:
    return Job(
        job_id="JOB-200",
        objective="Research the exact Web-Sol failure and produce an evidence-backed repair brief.",
        department="executive",
        priority=50,
        status=JobStatus.RUNNING,
        assigned_worker_id="web-sol-pro-3",
        assigned_quota_class="chatgpt-pro",
        authority_level="bounded",
        branch=None,
        worktree=None,
        checkpoint=None,
        result=None,
        created_at="2026-09-23T09:00:00Z",
        updated_at="2026-09-23T09:00:00Z",
        current_attempt_id="ATT-200",
        requested_authorities=(
            list(authorities)
            if authorities is not None
            else (["READ"] if role == "review" else ["READ", "RESEARCH"])
        ),
        authority_policy_hash=DIGEST_A,
        allowed_write_paths=[],
        validation_commands=[],
        parent_job_id="JOB-ROOT",
        root_job_id="JOB-ROOT",
        depth=1,
        owner_seat="ceo",
        escalation_target="ceo",
        business_impact="material",
        review_required=(role == "work"),
        reviews_job_id="JOB-REVIEW" if role == "review" else None,
        orchestration_role=role,
        orchestration_provenance={"schema": "fixture"},
        orchestration_provenance_digest=DIGEST_B,
        plan_attempt_id="ATT-PLAN",
        plan_digest=DIGEST_A,
        plan_step_id="research-1",
        repair_round=0,
    )


def _attempt(*, status: AttemptStatus = AttemptStatus.CLAIMED) -> Attempt:
    return Attempt(
        attempt_id="ATT-200",
        job_id="JOB-200",
        attempt_number=1,
        worker_id="web-sol-pro-3",
        quota_class="chatgpt-pro",
        status=status,
        fence_generation=1,
        lease_owner="fixture",
        lease_expires_at="2026-09-23T09:05:00Z",
        heartbeat_at="2026-09-23T09:00:00Z",
        checkpoint_sequence=0,
        checkpoint=None,
        result=None,
        error=None,
        started_at="2026-09-23T09:00:00Z",
        finished_at="",
        version=1,
        authority_policy_hash=DIGEST_A,
        pid=None,
        pgid=None,
        process_start_identity=None,
        boot_id=None,
        provider_session_id="chatgpt-session-200",
        stdout_path=None,
        stderr_path=None,
        result_path=None,
        exit_code=None,
        launch_metadata={},
    )


def _build(**kwargs):
    args = {
        "job": _job(),
        "attempt": _attempt(),
        "dialogue_source": _source(),
        "agentos": _agentos(),
        "workstream": "WS:TARGET",
    }
    args.update(kwargs)
    return build_web_sol_cognition_assignment(**args)


def test_declared_prompt_ceiling_survives_worst_case_native_frame_escaping() -> None:
    assert (2 * MAX_RENDERED_ASSIGNMENT_BYTES) + FRAME_RESERVE_BYTES <= NATIVE_FRAME_BYTES


def test_builds_bounded_deterministic_assignment_without_raw_context() -> None:
    first = _build()
    second = _build()

    assert first.assignment_digest == second.assignment_digest
    assert first.rendered_prompt == second.rendered_prompt
    assert first.rendered_prompt_bytes <= MAX_RENDERED_ASSIGNMENT_BYTES
    assert (2 * first.rendered_prompt_bytes) + FRAME_RESERVE_BYTES <= NATIVE_FRAME_BYTES
    assert first.document["schema_version"] == ASSIGNMENT_SCHEMA
    assert first.document["job"]["job_id"] == "JOB-200"
    assert first.document["job"]["attempt_id"] == "ATT-200"
    assert first.document["job"]["worker_id"] == "web-sol-pro-3"
    assert first.document["source"]["work_ref"] == "WS:TARGET"
    assert first.document["continuation"]["do_not_redo"] == ["DONE-1"]
    assert first.document["effect_contract"] == {
        "allowed_write_paths": [],
        "external_effects_allowed": False,
        "requested_authorities": ["READ", "RESEARCH"],
    }
    rendered = first.rendered_prompt
    assert "private raw context that must not cross" not in rendered
    assert '"excerpt"' not in rendered
    assert '"why_included"' not in rendered
    assert "Do not perform writes" in rendered
    assert "no Markdown fence" in rendered


def test_result_schema_is_exactly_bound_to_attempt_identity() -> None:
    assignment = _build()
    schema = assignment.document["result_contract"]["schema"]
    props = schema["properties"]

    assert props["job_id"] == {"const": "JOB-200"}
    assert props["run_id"] == {"const": "ATT-200"}
    assert props["worker_id"] == {"const": "web-sol-pro-3"}
    assert props["role"] == {"const": "work"}
    assert props["role_result"]["properties"]["root_job_id"] == {"const": "JOB-ROOT"}


def test_canonical_assignment_json_round_trips_exactly() -> None:
    assignment = _build()
    parsed = json.loads(assignment.canonical_json)
    encoded = json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert encoded == assignment.canonical_json


def test_refuses_any_write_or_test_authority_surface() -> None:
    base = _job()
    with pytest.raises(WebSolCognitionAssignmentError, match="JOB_NOT_RESEARCH_ONLY"):
        _build(job=dataclasses.replace(base, requested_authorities=["READ", "WRITE_BRANCH"]))
    with pytest.raises(WebSolCognitionAssignmentError, match="JOB_NOT_RESEARCH_ONLY"):
        _build(job=dataclasses.replace(base, allowed_write_paths=["src/owned.py"]))
    with pytest.raises(WebSolCognitionAssignmentError, match="JOB_NOT_RESEARCH_ONLY"):
        _build(job=dataclasses.replace(base, validation_commands=[["pytest", "-q"]]))


def test_refuses_stale_or_started_runtime_identity() -> None:
    with pytest.raises(WebSolCognitionAssignmentError, match="ATTEMPT_NOT_PRESTART_CLAIMED"):
        _build(attempt=_attempt(status=AttemptStatus.RUNNING))
    with pytest.raises(WebSolCognitionAssignmentError, match="RUNTIME_IDENTITY_MISMATCH"):
        _build(job=dataclasses.replace(_job(), current_attempt_id="ATT-OTHER"))
    with pytest.raises(WebSolCognitionAssignmentError, match="RUNTIME_IDENTITY_MISMATCH"):
        _build(attempt=dataclasses.replace(_attempt(), worker_id="other-worker"))


def test_refuses_wrong_workstream_or_untrusted_continuation_source() -> None:
    with pytest.raises(
        WebSolCognitionAssignmentError,
        match="DIALOGUE_SOURCE_WORKSTREAM_MISMATCH",
    ):
        _build(workstream="WS:OTHER")
    unavailable = _agentos()
    unavailable["available"] = False
    with pytest.raises(WebSolCognitionAssignmentError, match="CONTINUATION_REFUSED"):
        _build(agentos=unavailable)


def test_role_surface_is_deliberately_narrow() -> None:
    review = _build(job=_job(role="review"))
    assert review.document["job"]["role"] == "review"
    assert review.document["effect_contract"]["requested_authorities"] == ["READ"]
    assert review.document["result_contract"]["schema"]["properties"]["role"] == {
        "const": "review"
    }

    with pytest.raises(WebSolCognitionAssignmentError, match="JOB_NOT_RESEARCH_ONLY"):
        _build(job=_job(role="review", authorities=["READ", "RUN_TESTS"]))

    with pytest.raises(WebSolCognitionAssignmentError, match="ROLE_NOT_COGNITION_ASSIGNABLE"):
        _build(job=_job(role="plan"))
