from __future__ import annotations

import copy

import pytest

from control_plane.operator_continuation import (
    CONTINUATION_SCHEMA,
    ContinuationContractError,
    build_operator_continuation,
    canonical_continuation_bytes,
)


def _material() -> dict[str, object]:
    return {
        "root_job_id": "job-root-001",
        "job_id": "job-plan-001",
        "source_attempt_id": "attempt-plan-001",
        "target_attempt_id": "attempt-plan-002",
        "operation_key": "operator-continuity-ocr3-contract-20260828-sol-001",
        "target_seat": "coo",
        "session_alias": "EXECUTIVE-COO-A",
        "effective_grant_digest": "a" * 64,
        "prior_attempt_receipt": {
            "status": "RATE_LIMITED",
            "terminal_event_id": "event-terminal-001",
            "checkpoint_digest": "b" * 64,
        },
        "authority_sources": [
            {
                "owner": "github",
                "repository": "mastermindx-market-intelligence/Mastermind",
                "revision": "c" * 40,
                "path": "docs/superpowers/specs/operator-continuity.md",
                "sha256": "d" * 64,
            },
            {
                "owner": "agent_os",
                "repository": "mastermindx-market-intelligence/macro",
                "revision": "e" * 40,
                "path": "agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md",
                "sha256": "f" * 64,
            },
        ],
        "github_work_state": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "base_ref": "master",
            "branch": "sol/operator-continuity-ocr3-contract-20260828",
            "head_sha": "1" * 40,
            "pull_request_number": 0,
        },
        "dialogue_state": {
            "workspace_id": "T0123456789",
            "channel_id": "C0123456789",
            "thread_ts": "1787890000.123456",
            "last_ruling_ts": "1787890100.123456",
        },
        "exact_next_action": "Continue the same read-only Fable planning Job on the newly claimed Attempt.",
        "known_unknowns": ["provider capacity reset time remains unknown"],
    }


def test_builds_one_closed_canonical_capsule_without_caller_identity_or_clock() -> None:
    capsule = build_operator_continuation(**_material())

    assert set(capsule) == {
        "schema",
        "capsule_id",
        "root_job_id",
        "job_id",
        "source_attempt_id",
        "target_attempt_id",
        "operation_key",
        "target_seat",
        "session_alias",
        "effective_grant_digest",
        "prior_attempt_receipt",
        "authority_sources",
        "github_work_state",
        "dialogue_state",
        "exact_next_action",
        "known_unknowns",
    }
    assert capsule["schema"] == CONTINUATION_SCHEMA
    assert capsule["capsule_id"].startswith("ocap_")
    assert len(capsule["capsule_id"]) == len("ocap_") + 64
    assert "prepared_at" not in capsule
    assert "provider_session_id" not in capsule
    assert "transcript" not in capsule


def test_capsule_identity_is_order_independent_and_byte_stable() -> None:
    first_material = _material()
    second_material = copy.deepcopy(first_material)
    second_material["prior_attempt_receipt"] = {
        "checkpoint_digest": "b" * 64,
        "terminal_event_id": "event-terminal-001",
        "status": "RATE_LIMITED",
    }
    second_material["github_work_state"] = {
        "pull_request_number": 0,
        "head_sha": "1" * 40,
        "branch": "sol/operator-continuity-ocr3-contract-20260828",
        "base_ref": "master",
        "repository": "mastermindx-market-intelligence/Mastermind",
    }

    first = build_operator_continuation(**first_material)
    second = build_operator_continuation(**second_material)

    assert first == second
    assert canonical_continuation_bytes(first) == canonical_continuation_bytes(second)


def test_semantic_change_changes_capsule_identity() -> None:
    first = build_operator_continuation(**_material())
    changed = _material()
    changed["exact_next_action"] = "Return to Sol because the target source revision changed."
    second = build_operator_continuation(**changed)

    assert first["capsule_id"] != second["capsule_id"]


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("source_attempt_id", "attempt-plan-002", "ATTEMPT_IDENTITY_INVALID"),
        ("target_seat", "provider_account", "TARGET_SEAT_INVALID"),
        ("effective_grant_digest", "not-a-digest", "DIGEST_INVALID"),
        ("authority_sources", [], "AUTHORITY_SOURCES_INVALID"),
        ("known_unknowns", ["Bearer " + "x" * 40], "SECRET_SHAPED_VALUE"),
    ],
)
def test_refuses_ambiguous_or_privileged_material(
    field: str, replacement: object, reason: str
) -> None:
    material = _material()
    material[field] = replacement

    with pytest.raises(ContinuationContractError, match=reason):
        build_operator_continuation(**material)


def test_refuses_provider_native_transcript_or_session_material() -> None:
    material = _material()
    material["github_work_state"] = {
        **material["github_work_state"],
        "provider_session_id": "claude-session-secret",
    }
    with pytest.raises(ContinuationContractError, match="GITHUB_WORK_STATE_INVALID"):
        build_operator_continuation(**material)

    material = _material()
    material["prior_attempt_receipt"] = {
        **material["prior_attempt_receipt"],
        "transcript": "copied provider-native conversation",
    }
    with pytest.raises(ContinuationContractError, match="PRIOR_ATTEMPT_RECEIPT_INVALID"):
        build_operator_continuation(**material)


def test_refuses_duplicate_or_noncanonical_authority_sources() -> None:
    material = _material()
    material["authority_sources"] = [
        material["authority_sources"][0],
        copy.deepcopy(material["authority_sources"][0]),
    ]
    with pytest.raises(ContinuationContractError, match="AUTHORITY_SOURCES_INVALID"):
        build_operator_continuation(**material)

    material = _material()
    material["authority_sources"] = list(reversed(material["authority_sources"]))
    capsule = build_operator_continuation(**material)
    assert capsule["authority_sources"] == sorted(
        capsule["authority_sources"],
        key=lambda row: (row["owner"], row["repository"], row["path"], row["revision"]),
    )


def test_public_canonicalizer_revalidates_capsule_id() -> None:
    capsule = build_operator_continuation(**_material())
    tampered = copy.deepcopy(capsule)
    tampered["capsule_id"] = "ocap_" + "0" * 64

    with pytest.raises(ContinuationContractError, match="CAPSULE_ID_MISMATCH"):
        canonical_continuation_bytes(tampered)
