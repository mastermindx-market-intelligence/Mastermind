"""Pure, fail-closed retry-safety classifier coverage for AD-RETRY1."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.executive_retry_safety import (
    RetrySafety,
    RetrySafetyDecision,
    RetrySafetyEvidence,
    classify_retry_safety,
)


_PROVENANCE_DIGEST = "a" * 64


def _evidence(**overrides: object) -> RetrySafetyEvidence:
    """Return independently specified evidence for a known safe pre-effect failure."""

    value: dict[str, object] = {
        "retry_safety": RetrySafety.SAFE_PRE_EFFECT_INFRASTRUCTURE,
        "terminal_status": "LOST",
        "job_id": "JOB-1",
        "attempt_id": "ATTEMPT-1",
        "attempt_job_id": "JOB-1",
        "current_attempt_id": "ATTEMPT-1",
        "provenance_digest": _PROVENANCE_DIGEST,
        "retry_lineage_available": True,
        "effect_unknown": False,
        "writer_or_provider_generation_live": False,
        "candidate_present": False,
        "result_present": False,
        "seal_present": False,
        "effective_grant_non_modifying": False,
    }
    value.update(overrides)
    return RetrySafetyEvidence(**value)  # type: ignore[arg-type]


def test_exact_proven_pre_effect_infrastructure_evidence_is_safe_to_requeue() -> None:
    evidence = _evidence()

    assert classify_retry_safety(evidence) is RetrySafetyDecision.SAFE_REQUEUE


def test_exact_non_modifying_quota_rollover_evidence_is_safe_to_requeue() -> None:
    decision = classify_retry_safety(
        _evidence(
            retry_safety=RetrySafety.SAFE_NON_MODIFYING_QUOTA_ROLLOVER,
            terminal_status="RATE_LIMITED",
            effective_grant_non_modifying=True,
        )
    )

    assert decision is RetrySafetyDecision.SAFE_REQUEUE


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            {"retry_safety": RetrySafety.GENERIC_FAILED, "terminal_status": "RATE_LIMITED"},
            RetrySafetyDecision.NEEDS_SOL,
        ),
        (
            {"retry_safety": "provider says retry me"},
            RetrySafetyDecision.NEEDS_SOL,
        ),
        (
            {"retry_safety": "SAFE_PRE_EFFECT_INFRASTRUCTURE"},
            RetrySafetyDecision.NEEDS_SOL,
        ),
        (
            {"retry_safety": RetrySafety.EFFECT_UNKNOWN},
            RetrySafetyDecision.NEEDS_RECONCILIATION,
        ),
        ({"effect_unknown": True}, RetrySafetyDecision.NEEDS_RECONCILIATION),
        (
            {"current_attempt_id": "ATTEMPT-OTHER"},
            RetrySafetyDecision.NEEDS_RECONCILIATION,
        ),
        ({"provenance_digest": None}, RetrySafetyDecision.NEEDS_SOL),
        (
            {
                "retry_safety": RetrySafety.SAFE_NON_MODIFYING_QUOTA_ROLLOVER,
                "terminal_status": "RATE_LIMITED",
                "effective_grant_non_modifying": False,
            },
            RetrySafetyDecision.NEEDS_RECONCILIATION,
        ),
        (
            {"writer_or_provider_generation_live": True},
            RetrySafetyDecision.NEEDS_RECONCILIATION,
        ),
        ({"candidate_present": True}, RetrySafetyDecision.NEEDS_RECONCILIATION),
        ({"result_present": True}, RetrySafetyDecision.NEEDS_RECONCILIATION),
        ({"seal_present": True}, RetrySafetyDecision.NEEDS_RECONCILIATION),
        (
            {"retry_safety": RetrySafety.UNKNOWN},
            RetrySafetyDecision.NEEDS_SOL,
        ),
        (
            {"retry_safety": RetrySafety.SEMANTIC_FAILED},
            RetrySafetyDecision.NEEDS_SOL,
        ),
        ({"retry_lineage_available": False}, RetrySafetyDecision.TERMINAL_NO_RETRY),
    ],
)
def test_unsafe_or_ambiguous_evidence_never_auto_requeues(
    mutation: dict[str, object], expected: RetrySafetyDecision
) -> None:
    decision = classify_retry_safety(_evidence(**mutation))

    assert decision is expected
    assert decision is not RetrySafetyDecision.SAFE_REQUEUE


def test_safe_evidence_digest_is_deterministic_and_changes_when_evidence_changes() -> None:
    evidence = _evidence()

    assert evidence.evidence_digest == evidence.evidence_digest
    assert dataclasses.replace(evidence, terminal_status="FAILED").evidence_digest != (
        evidence.evidence_digest
    )
