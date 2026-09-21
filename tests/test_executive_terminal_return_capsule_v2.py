from __future__ import annotations

import hashlib
import json

import pytest

from control_plane.executive_runtime import ExecutiveDialogueSource
from control_plane.executive_terminal_return import (
    TerminalReturnCandidate,
    TerminalReviewFinding,
)
from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
    _build_message,
)


def _candidate(
    *,
    role: str = "review",
    summary: str = "Independent review found two bounded issues.",
    next_actions: tuple[str, ...] = ("Repair both findings.",),
    findings: tuple[TerminalReviewFinding, ...] = (
        TerminalReviewFinding(
            code="MISSING_DATA",
            severity="blocking",
            message="Missing data can overstate confidence.",
        ),
        TerminalReviewFinding(
            code="LANG_PARITY",
            severity="warning",
            message="English and Chinese states diverge.",
        ),
    ),
) -> TerminalReturnCandidate:
    terminal_digest = "a" * 64
    return TerminalReturnCandidate(
        job_id="JOB-002",
        attempt_id="ATT-002",
        worker_id="worker-a",
        root_job_id="JOB-001",
        role=role,
        operation_key="exec-job-002",
        session_ref="asd-session-exec-job-002",
        runtime_status="COMPLETED",
        result_status="RESULT",
        result_envelope_digest="b" * 64,
        terminal_evidence_digest=terminal_digest,
        artifact_receipt_digest="c" * 64,
        validation_receipt_digest="d" * 64,
        effective_grant_digest="e" * 64,
        terminal_at="2026-09-21T09:00:00Z",
        message_key=f"asd-exec-result-{terminal_digest}",
        summary=summary,
        review_verdict="reject" if role == "review" else None,
        next_actions=next_actions,
        review_findings=findings if role == "review" else (),
        dialogue_source=ExecutiveDialogueSource(
            schema_version="mastermind.executive_dialogue_source/v1",
            work_ref="WS:WORKER-PRESENCE",
            commission_ref={
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": "c" * 40,
                "path": "research/commission.md",
                "content_sha256": "d" * 64,
            },
            watch_mode="turn_watch_v1",
        ),
    )


def _context(candidate: TerminalReturnCandidate) -> dict[str, object]:
    attempt_ref = {
        "kind": "worker_attempt",
        "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id,
        "worker_id": candidate.worker_id,
    }
    return {
        "work_ref": "WS:WORKER-PRESENCE",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "c" * 40,
            "path": "research/commission.md",
            "content_sha256": "d" * 64,
        },
        "session_ref": candidate.session_ref,
        "actor_ref": attempt_ref,
        "applies_to": {
            "kind": "executive_attempt",
            "job_id": candidate.job_id,
            "attempt_id": candidate.attempt_id,
            "worker_id": candidate.worker_id,
        },
    }


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_enriched_candidate_keeps_v1_wire_until_host_selects_v2() -> None:
    candidate = _candidate()

    message = _build_message(candidate, _context(candidate))
    payload = json.loads(message["body"]["result"])

    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v1"
    assert payload["result_envelope_digest"] == candidate.result_envelope_digest
    assert "review" not in payload
    assert "next" not in payload


def test_v2_capsule_preserves_two_findings_and_next_action_without_transcript() -> None:
    candidate = _candidate()

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert message["body"]["status"] == "FAIL"
    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v2"
    assert payload["summary"] == candidate.summary
    assert payload["next"] == ["Repair both findings."]
    assert payload["digests"] == {
        "result": "b" * 64,
        "terminal": "a" * 64,
        "artifact": "c" * 64,
        "validation": "d" * 64,
        "grant": "e" * 64,
    }
    assert payload["review"] == {
        "verdict": "reject",
        "counts": {"blocking": 1, "warning": 1, "info": 0},
        "findings": [
            {
                "code": "MISSING_DATA",
                "severity": "blocking",
                "message": "Missing data can overstate confidence.",
            },
            {
                "code": "LANG_PARITY",
                "severity": "warning",
                "message": "English and Chinese states diverge.",
            },
        ],
    }
    assert len(message["body"]["result"]) <= 900
    assert "provider" not in message["body"]["result"].lower()
    assert "transcript" not in message["body"]["result"].lower()


def test_v2_capsule_degrades_oversize_text_to_counts_and_digests_without_slicing() -> None:
    blocking = "blocking:" + ("b" * 900)
    warning = "warning:" + ("w" * 900)
    action = "action:" + ("a" * 900)
    candidate = _candidate(
        summary="summary:" + ("s" * 900),
        next_actions=(action,),
        findings=(
            TerminalReviewFinding("BLOCK", "blocking", blocking),
            TerminalReviewFinding("WARN", "warning", warning),
        ),
    )

    first = _build_message(candidate, _context(candidate), synopsis_version="v2")
    second = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(first["body"]["result"])

    assert second == first
    assert first["body"]["status"] == "FAIL"
    assert "summary" not in payload
    assert payload["summary_sha256"] == hashlib.sha256(
        candidate.summary.encode("utf-8")
    ).hexdigest()
    assert payload["next_count"] == 1
    assert payload["next_sha256"] == _digest([action])
    assert payload["review"]["counts"] == {
        "blocking": 1,
        "warning": 1,
        "info": 0,
    }
    full_findings = [
        {
            "code": "BLOCK",
            "severity": "blocking",
            "message": blocking,
            "evidence_digests": [],
        },
        {
            "code": "WARN",
            "severity": "warning",
            "message": warning,
            "evidence_digests": [],
        },
    ]
    assert payload["review"]["findings_sha256"] == _digest(full_findings)
    assert "findings" not in payload["review"]
    assert blocking not in first["body"]["result"]
    assert warning not in first["body"]["result"]
    assert action not in first["body"]["result"]
    assert len(first["body"]["result"]) <= 900


def test_v2_nonreview_next_action_has_no_review_block() -> None:
    candidate = _candidate(
        role="work",
        summary="Work completed; verification remains.",
        next_actions=("Run bounded verification.",),
        findings=(),
    )

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert message["body"]["status"] == "PASS"
    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v2"
    assert payload["next"] == ["Run bounded verification."]
    assert "review" not in payload


# ---------------------------------------------------------------------------
# Canonical candidate root_job_id locator (F1 repair)
# ---------------------------------------------------------------------------
# Every new v2 RESULT synopsis must carry the exact canonical candidate
# ``root_job_id`` so a C pull can authenticate the root from the public
# message.  The locator is the unconstrained Runtime-attested root identifier
# (it is not hashed or summarized away) so the canonical identity of every
# new v2 differs from the pre-repair v2 by exactly that one field, and v1
# remains byte-identical across the repair.


def test_v2_capsule_carries_canonical_root_job_id_locator() -> None:
    candidate = _candidate()

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert payload["root_job_id"] == candidate.root_job_id
    assert payload["root_job_id"] == "JOB-001"


def test_v2_capsule_root_job_id_locator_survives_oversize_summary_degradation() -> None:
    """Locator must survive whole-field degradation, not be sliced with text."""

    candidate = _candidate(summary="summary:" + ("s" * 900))

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert payload["root_job_id"] == candidate.root_job_id
    assert payload["root_job_id"] == "JOB-001"
    assert "summary" not in payload
    assert "summary_sha256" in payload
    assert len(message["body"]["result"]) <= 900


def test_v2_capsule_root_job_id_locator_survives_finding_degradation() -> None:
    """Locator must survive finding-mode degradation."""

    blocking = "blocking:" + ("b" * 900)
    warning = "warning:" + ("w" * 900)
    candidate = _candidate(
        summary="summary:" + ("s" * 900),
        next_actions=("action:" + ("a" * 900),),
        findings=(
            TerminalReviewFinding("BLOCK", "blocking", blocking),
            TerminalReviewFinding("WARN", "warning", warning),
        ),
    )

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert payload["root_job_id"] == candidate.root_job_id
    assert payload["review"]["counts"] == {"blocking": 1, "warning": 1, "info": 0}
    assert "findings" not in payload["review"]
    assert "findings_sha256" in payload["review"]
    assert len(message["body"]["result"]) <= 900


def test_v2_capsule_root_job_id_locator_survives_next_action_degradation() -> None:
    """Locator must survive next-action degradation."""

    action = "action:" + ("a" * 900)
    candidate = _candidate(
        role="work",
        summary="summary:" + ("s" * 900),
        next_actions=(action,),
    )

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert payload["root_job_id"] == candidate.root_job_id
    assert "next" not in payload
    assert payload["next_count"] == 1
    assert payload["next_sha256"] == _digest([action])
    assert len(message["body"]["result"]) <= 900


def test_v2_capsule_preserves_actor_and_applies_to_with_root_locator() -> None:
    """Adding the root locator must not perturb actor_ref/applies_to identity."""

    candidate = _candidate()
    context = _context(candidate)

    message = _build_message(candidate, context, synopsis_version="v2")

    assert message["actor_ref"] == context["actor_ref"]
    assert message["applies_to"] == context["applies_to"]
    assert message["actor_ref"]["job_id"] == candidate.job_id
    assert message["actor_ref"]["attempt_id"] == candidate.attempt_id
    assert message["applies_to"]["job_id"] == candidate.job_id
    assert message["applies_to"]["attempt_id"] == candidate.attempt_id


def test_v2_capsule_preserves_exact_result_envelope_digest_with_root_locator() -> None:
    """Adding the root locator must keep ``digests.result`` byte-identical."""

    candidate = _candidate()

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert payload["digests"]["result"] == candidate.result_envelope_digest
    assert payload["digests"]["terminal"] == candidate.terminal_evidence_digest
    assert payload["digests"]["artifact"] == candidate.artifact_receipt_digest
    assert payload["digests"]["validation"] == candidate.validation_receipt_digest
    assert payload["digests"]["grant"] == candidate.effective_grant_digest


def test_v1_capsule_remains_byte_identical_after_root_locator_repair() -> None:
    """v1 body must stay unchanged: no root_job_id, identical canonical identity."""

    candidate = _candidate()

    message = _build_message(candidate, _context(candidate), synopsis_version="v1")
    payload = json.loads(message["body"]["result"])

    assert "root_job_id" not in payload
    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v1"
    assert payload["role"] == candidate.role
    assert payload["outcome"] == "FAIL"
    assert payload["result_envelope_digest"] == candidate.result_envelope_digest
    assert payload["summary"] == candidate.summary


def test_v1_and_v2_share_message_key_after_root_locator_repair() -> None:
    """``message_key`` derives solely from ``terminal_evidence_digest``."""

    candidate = _candidate()

    v1 = _build_message(candidate, _context(candidate), synopsis_version="v1")
    v2 = _build_message(candidate, _context(candidate), synopsis_version="v2")

    assert v1["message_key"] == v2["message_key"] == candidate.message_key


@pytest.mark.parametrize(
    "root_job_id",
    [
        pytest.param("JOB-001", id="canonical-short"),
        pytest.param("JOB-9999999", id="seven-digit"),
        pytest.param("JOB-" + ("9" * 10), id="ten-digits"),
    ],
)
def test_v2_capsule_root_job_id_locator_stays_within_900_budget(
    root_job_id: str,
) -> None:
    """Canonical and long-but-realistic root IDs must keep every fallback within 900 chars."""

    terminal_digest = "a" * 64
    candidate = TerminalReturnCandidate(
        job_id="JOB-002",
        attempt_id="ATT-002",
        worker_id="worker-a",
        root_job_id=root_job_id,
        role="work",
        operation_key="exec-job-002",
        session_ref="asd-session-exec-job-002",
        runtime_status="COMPLETED",
        result_status="RESULT",
        result_envelope_digest="b" * 64,
        terminal_evidence_digest=terminal_digest,
        artifact_receipt_digest="c" * 64,
        validation_receipt_digest="d" * 64,
        effective_grant_digest="e" * 64,
        terminal_at="2026-09-21T09:00:00Z",
        message_key=f"asd-exec-result-{terminal_digest}",
        summary="Work completed; verification remains.",
        review_verdict=None,
        next_actions=("Run bounded verification.",),
        review_findings=(),
        dialogue_source=ExecutiveDialogueSource(
            schema_version="mastermind.executive_dialogue_source/v1",
            work_ref="WS:WORKER-PRESENCE",
            commission_ref={
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": "c" * 40,
                "path": "research/commission.md",
                "content_sha256": "d" * 64,
            },
            watch_mode="turn_watch_v1",
        ),
    )

    first = _build_message(candidate, _context(candidate), synopsis_version="v2")
    second = _build_message(candidate, _context(candidate), synopsis_version="v2")

    payload = json.loads(first["body"]["result"])
    assert second == first
    assert payload["root_job_id"] == root_job_id
    assert len(first["body"]["result"]) <= 900


def test_v2_capsule_pathological_long_root_id_refuses_without_slicing() -> None:
    """A pathologically long root ID exceeds even digest-only mode; refusal is the bound."""

    from control_plane.executive_terminal_return import (
        TerminalReturnProjectionError,
    )

    terminal_digest = "a" * 64
    candidate = TerminalReturnCandidate(
        job_id="JOB-002",
        attempt_id="ATT-002",
        worker_id="worker-a",
        root_job_id="JOB-" + ("9" * 200),
        role="review",
        operation_key="exec-job-002",
        session_ref="asd-session-exec-job-002",
        runtime_status="COMPLETED",
        result_status="RESULT",
        result_envelope_digest="b" * 64,
        terminal_evidence_digest=terminal_digest,
        artifact_receipt_digest="c" * 64,
        validation_receipt_digest="d" * 64,
        effective_grant_digest="e" * 64,
        terminal_at="2026-09-21T09:00:00Z",
        message_key=f"asd-exec-result-{terminal_digest}",
        summary="Independent review found two bounded issues.",
        review_verdict="reject",
        next_actions=("Repair both findings.",),
        review_findings=(
            TerminalReviewFinding(
                code="MISSING_DATA",
                severity="blocking",
                message="Missing data can overstate confidence.",
            ),
            TerminalReviewFinding(
                code="LANG_PARITY",
                severity="warning",
                message="English and Chinese states diverge.",
            ),
        ),
        dialogue_source=ExecutiveDialogueSource(
            schema_version="mastermind.executive_dialogue_source/v1",
            work_ref="WS:WORKER-PRESENCE",
            commission_ref={
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": "c" * 40,
                "path": "research/commission.md",
                "content_sha256": "d" * 64,
            },
            watch_mode="turn_watch_v1",
        ),
    )
    with pytest.raises(TerminalReturnProjectionError) as refused:
        _build_message(candidate, _context(candidate), synopsis_version="v2")
    assert refused.value.code == "DIALOGUE_REFUSED"


def test_v2_capsule_locator_and_counts_survive_oversize_digest_only_mode() -> None:
    """Even in the final digest-only mode, locator + counts + digests survive."""

    blocking = "blocking:" + ("b" * 900)
    warning = "warning:" + ("w" * 900)
    action = "action:" + ("a" * 900)
    candidate = _candidate(
        summary="summary:" + ("s" * 900),
        next_actions=(action,),
        findings=(
            TerminalReviewFinding("BLOCK", "blocking", blocking),
            TerminalReviewFinding("WARN", "warning", warning),
        ),
    )

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    # Locator, counts, digests all preserved under degradation.
    assert payload["root_job_id"] == candidate.root_job_id
    assert payload["review"]["counts"] == {"blocking": 1, "warning": 1, "info": 0}
    assert "findings_sha256" in payload["review"]
    assert payload["digests"]["result"] == candidate.result_envelope_digest
    # No model-text leakage.
    assert blocking not in message["body"]["result"]
    assert warning not in message["body"]["result"]
    assert action not in message["body"]["result"]
    assert candidate.summary not in message["body"]["result"]
    assert len(message["body"]["result"]) <= 900


def test_v2_capsule_oversize_summary_digest_keeps_locator_unhashed() -> None:
    """When summary degrades to ``summary_sha256``, the root locator is unhashed."""

    candidate = _candidate(summary="summary:" + ("s" * 900))

    message = _build_message(candidate, _context(candidate), synopsis_version="v2")
    payload = json.loads(message["body"]["result"])

    assert "summary" not in payload
    assert "summary_sha256" in payload
    assert payload["root_job_id"] == candidate.root_job_id
    # Locator is the exact value, not a hash.
    assert len(payload["root_job_id"]) == 7


# ---------------------------------------------------------------------------
# Golden pins: the exact committed historical wires this projector must keep
# reusable.  ``input/golden_messages.json`` captured the pristine v1 and the
# pre-root-locator v2 RESULT for this same candidate identity; the repair may
# not move either byte.  A genuinely new v2 keeps the canonical root locator.
# ---------------------------------------------------------------------------

GOLDEN_V1_FINGERPRINT = (
    "dbea0651f399b262e1ce716b21693b8c1d35b5dd4b4d524ca33efd9342217108"
)
GOLDEN_PRE_ROOT_V2_FINGERPRINT = (
    "dbe881a5377290fc826fbcf48568a680eb1094a0561ba71571acff3027fb1761"
)
GOLDEN_CURRENT_V2_FINGERPRINT = (
    "607b7d41e2300004b5fb87f4028869f40a23ced4ae168886410ec9c822fe58a3"
)


def test_golden_v1_rebuild_is_byte_identical_to_the_committed_wire() -> None:
    candidate = _candidate()

    message = _build_message(candidate, _context(candidate))

    assert message["fingerprint"] == GOLDEN_V1_FINGERPRINT
    assert message["message_key"] == candidate.message_key
    assert len(message["body"]["result"]) == 617
    payload = json.loads(message["body"]["result"])
    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v1"
    assert "root_job_id" not in payload
    assert payload["summary"] == candidate.summary


def test_golden_pre_root_v2_rebuild_is_byte_identical_to_the_committed_wire() -> None:
    """The historical pre-locator v2 wire must stay rebuildable byte-for-byte."""

    candidate = _candidate()

    message = _build_message(
        candidate,
        _context(candidate),
        synopsis_version="v2",
        include_root_job_id=False,
    )

    assert message["fingerprint"] == GOLDEN_PRE_ROOT_V2_FINGERPRINT
    assert message["message_key"] == candidate.message_key
    assert len(message["body"]["result"]) == 860
    payload = json.loads(message["body"]["result"])
    assert payload["schema"] == "mastermind.executive_terminal_result_synopsis/v2"
    assert "root_job_id" not in payload
    assert payload["summary"] == candidate.summary
    assert payload["next"] == ["Repair both findings."]
    assert payload["review"]["verdict"] == "reject"


def test_golden_current_v2_rebuild_carries_the_canonical_root_locator() -> None:
    candidate = _candidate()

    message = _build_message(
        candidate,
        _context(candidate),
        synopsis_version="v2",
        include_root_job_id=True,
    )

    assert message["fingerprint"] == GOLDEN_CURRENT_V2_FINGERPRINT
    assert message["message_key"] == candidate.message_key
    payload = json.loads(message["body"]["result"])
    assert payload["root_job_id"] == candidate.root_job_id
    assert payload["root_job_id"] == "JOB-001"
    assert len(message["body"]["result"]) <= 900


def test_golden_all_three_supported_shapes_rebuild_under_one_key() -> None:
    """Every supported synopsis shape shares the key and stays rebuildable."""

    from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
        _committed_message_variants,
    )

    candidate = _candidate()
    variants = _committed_message_variants(candidate, _context(candidate))

    fingerprints = {variant["fingerprint"] for variant in variants}
    assert fingerprints == {
        GOLDEN_V1_FINGERPRINT,
        GOLDEN_PRE_ROOT_V2_FINGERPRINT,
        GOLDEN_CURRENT_V2_FINGERPRINT,
    }
    assert all(
        variant["message_key"] == candidate.message_key for variant in variants
    )
    # v1 stays byte-identical: its wire never carries the locator.
    for variant in variants:
        payload = json.loads(variant["body"]["result"])
        if payload["schema"].endswith("/v1"):
            assert "root_job_id" not in payload
