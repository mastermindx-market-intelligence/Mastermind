from __future__ import annotations

import copy

import pytest

from control_plane.operator_continuation import (
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
            "pull_request_number": None,
        },
        "dialogue_state": None,
        "exact_next_action": "Continue the same read-only Fable planning Job on the newly claimed Attempt.",
        "known_unknowns": [
            "provider capacity reset time remains unknown",
            "target Slack thread is not yet bound",
        ],
    }


def test_contract_does_not_require_slack_or_a_pull_request() -> None:
    capsule = build_operator_continuation(**_material())

    assert capsule["dialogue_state"] is None
    assert capsule["github_work_state"]["pull_request_number"] is None


def test_zero_is_not_a_fake_pull_request_null_sentinel() -> None:
    material = _material()
    material["github_work_state"] = {
        **material["github_work_state"],
        "pull_request_number": 0,
    }

    with pytest.raises(ContinuationContractError, match="GITHUB_WORK_STATE_INVALID"):
        build_operator_continuation(**material)


def test_dialogue_last_ruling_is_nullable_but_thread_identity_is_closed() -> None:
    material = _material()
    material["dialogue_state"] = {
        "workspace_id": "T0123456789",
        "channel_id": "C0123456789",
        "thread_ts": "1787890000.123456",
        "last_ruling_ts": None,
    }
    capsule = build_operator_continuation(**material)
    assert capsule["dialogue_state"]["last_ruling_ts"] is None

    material["dialogue_state"] = {
        **material["dialogue_state"],
        "provider_session_id": "claude-session-001",
    }
    with pytest.raises(ContinuationContractError, match="DIALOGUE_STATE_INVALID"):
        build_operator_continuation(**material)


def test_transport_sources_cannot_be_laundered_into_authority() -> None:
    material = _material()
    material["authority_sources"] = [
        {
            "owner": "slack",
            "repository": "mastermindx-market-intelligence/Mastermind",
            "revision": "c" * 40,
            "path": "transport/thread.txt",
            "sha256": "d" * 64,
        }
    ]

    with pytest.raises(ContinuationContractError, match="AUTHORITY_SOURCES_INVALID"):
        build_operator_continuation(**material)


def test_known_unknown_order_is_semantically_irrelevant() -> None:
    first = build_operator_continuation(**_material())
    reversed_material = _material()
    reversed_material["known_unknowns"] = list(
        reversed(reversed_material["known_unknowns"])
    )
    second = build_operator_continuation(**reversed_material)

    assert first == second
    assert canonical_continuation_bytes(first) == canonical_continuation_bytes(second)


@pytest.mark.parametrize(
    "leak",
    [
        "provider account is private.person@example.com",
        "worker home is /Users/private-person/.claude",
    ],
)
def test_capsule_refuses_provider_account_pii_and_private_home_paths(leak: str) -> None:
    material = _material()
    material["known_unknowns"] = [leak]

    with pytest.raises(ContinuationContractError, match="PII_OR_PRIVATE_PATH"):
        build_operator_continuation(**material)


def test_semantic_nulls_remain_byte_stable() -> None:
    first = build_operator_continuation(**_material())
    second = build_operator_continuation(**copy.deepcopy(_material()))
    assert canonical_continuation_bytes(first) == canonical_continuation_bytes(second)
