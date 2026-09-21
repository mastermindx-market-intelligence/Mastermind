from __future__ import annotations

import hashlib
import json

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
