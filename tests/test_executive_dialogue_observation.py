from __future__ import annotations

import dataclasses
import json

import pytest

from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
)

from control_plane.executive_dialogue_observation import (
    ACTIVE_CURRENT_WORKER,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    ActiveObservationFacts,
    DialogueObservationFacts,
    DialogueObservationProtocolError,
    PublicRuntimeBindingFacts,
    TerminalObservationFacts,
    TerminalProjectionReceiptFacts,
    parse_observation_request,
    reduce_dialogue_observation,
)
from tests.test_company_dialogue_runtime_binding import parent as valid_parent
from tests.test_slack_agent_dialogue_executive_terminal_return_projector import (
    _candidate as terminal_candidate,
)


def _request(parent: dict | None = None) -> bytes:
    return json.dumps(
        {
            "schema": REQUEST_SCHEMA,
            "parent": parent or valid_parent(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _active(parent: dict | None = None) -> ActiveObservationFacts:
    dialogue_parent = parent or valid_parent()
    return ActiveObservationFacts(
        root_job_id="JOB-100",
        job_id="JOB-101",
        attempt_id="ATT-201",
        worker_id="worker-01",
        attempt_status="RUNNING",
        worker_status="BUSY",
        execution_profile_id="profile-readonly",
        execution_profile_digest="1" * 64,
        capability_policy_digest="2" * 64,
        runtime_binding=PublicRuntimeBindingFacts(
            session_alias="MM-COO-SEAT",
            binding_id="bind-observation-0001",
            binding_generation=7,
            reasoning_surface="codex",
        ),
        parent_fingerprint=dialogue_parent["fingerprint"],
        company_dialogue_server_identity=SERVER_IDENTITY,
        company_dialogue_server_version=SERVER_VERSION,
        company_dialogue_tool_schema_digest=TOOL_SCHEMA_DIGEST,
        company_dialogue_attested=True,
    )


def _terminal(parent: dict | None = None) -> TerminalObservationFacts:
    dialogue_parent = parent or valid_parent()
    candidate = terminal_candidate()
    candidate = dataclasses.replace(
        candidate,
        operation_key=dialogue_parent["operation_key"],
        session_ref=dialogue_parent["session_ref"],
        dialogue_source=dataclasses.replace(
            candidate.dialogue_source,
            work_ref=dialogue_parent["work_ref"],
            commission_ref=dialogue_parent["commission_ref"],
            watch_mode=dialogue_parent["watch_mode"],
        ),
    )
    receipt = TerminalProjectionReceiptFacts(
        action="POSTED",
        message_key=candidate.message_key,
        fingerprint="4" * 64,
        message_ts="1787961600.000002",
        duplicate_timestamps=(),
        thread_ts="1787961600.000001",
        parent_author_user_id="U0RELAY001",
        parent_fingerprint=dialogue_parent["fingerprint"],
    )
    return TerminalObservationFacts(
        candidate=candidate,
        projection_receipt=receipt,
        projection_effect="APPLIED",
        binding_revalidated=True,
    )


def test_strict_request_reuses_canonical_v2_parent_parser() -> None:
    parsed = parse_observation_request(_request())
    assert parsed.parent == valid_parent()

    duplicate = _request().decode("utf-8").replace(
        '"schema":"mastermind.dialogue_observation_request/v1"',
        '"schema":"mastermind.dialogue_observation_request/v1",'
        '"schema":"mastermind.dialogue_observation_request/v1"',
        1,
    )
    hostile = (
        duplicate.encode("utf-8"),
        b'{"schema":NaN}',
        _request()[:-1] + b',"root_job_id":"JOB-999"}',
        _request() + b"\n{}",
        b"\xff",
    )
    for payload in hostile:
        with pytest.raises(DialogueObservationProtocolError) as exc:
            parse_observation_request(payload)
        assert exc.value.code == "REQUEST_REFUSED"
        assert "JOB-999" not in str(exc.value)


def test_active_reducer_exposes_only_public_current_worker_facts() -> None:
    parent = valid_parent()
    response = reduce_dialogue_observation(
        parent=parent,
        facts=DialogueObservationFacts(active=(_active(parent),)),
    )
    assert response["schema"] == RESPONSE_SCHEMA
    assert response["state"] == "RESOLVED"
    assert response["mode"] == ACTIVE_CURRENT_WORKER
    assert response["observation"]["runtime_binding"] == {
        "session_alias": "MM-COO-SEAT",
        "binding_id": "bind-observation-0001",
        "binding_generation": 7,
        "reasoning_surface": "codex",
    }
    encoded = json.dumps(response, sort_keys=True)
    for forbidden in (
        "native_handle",
        "account_label",
        "provider_home",
        "credential_home",
        "token",
        "local_path",
    ):
        assert forbidden not in encoded
    assert response["action_authoritative"] is False
    assert response["provider_action_authorized"] is False
    assert response["wake_write_authorized"] is False
    assert response["lifecycle_write_authorized"] is False


@pytest.mark.parametrize(
    ("change", "state", "reason"),
    [
        ({"attempt_status": "COMPLETED"}, "UNAVAILABLE", "CURRENT_ATTEMPT_INACTIVE"),
        ({"worker_status": "AVAILABLE"}, "UNAVAILABLE", "CURRENT_WORKER_INACTIVE"),
        ({"company_dialogue_attested": False}, "HELD", "CAPABILITY_NOT_ATTESTED"),
        ({"parent_fingerprint": "f" * 64}, "HELD", "DIALOGUE_PARENT_STALE"),
    ],
)
def test_active_reducer_fails_closed_without_leaking_fact_payload(
    change: dict[str, object], state: str, reason: str
) -> None:
    response = reduce_dialogue_observation(
        parent=valid_parent(),
        facts=DialogueObservationFacts(active=(dataclasses.replace(_active(), **change),)),
    )
    assert response == {"schema": RESPONSE_SCHEMA, "state": state, "reason": reason}


def test_terminal_requires_one_applied_revalidated_receipt() -> None:
    parent = valid_parent()
    resolved = reduce_dialogue_observation(
        parent=parent,
        facts=DialogueObservationFacts(terminal=(_terminal(parent),)),
    )
    assert resolved["state"] == "RESOLVED"
    assert resolved["mode"] == "TERMINAL_RESULT"
    assert resolved["observation"]["projection_effect"] == "APPLIED"

    for change, state, reason in (
        ({"projection_effect": "EFFECT_UNKNOWN"}, "UNKNOWN", "R2_EFFECT_UNKNOWN"),
        ({"projection_effect": "ATTEMPTED"}, "HELD", "R2_RECEIPT_MISSING"),
        ({"projection_effect": "PROVEN_NO_EFFECT"}, "HELD", "R2_RECEIPT_MISSING"),
        ({"binding_revalidated": False}, "HELD", "R2_BINDING_UNAVAILABLE"),
    ):
        response = reduce_dialogue_observation(
            parent=parent,
            facts=DialogueObservationFacts(
                terminal=(dataclasses.replace(_terminal(parent), **change),)
            ),
        )
        assert response == {"schema": RESPONSE_SCHEMA, "state": state, "reason": reason}

    @dataclasses.dataclass(frozen=True)
    class LookalikeReceipt:
        parent_fingerprint: str

    wrong_shape = reduce_dialogue_observation(
        parent=parent,
        facts=DialogueObservationFacts(
            terminal=(
                dataclasses.replace(
                    _terminal(parent),
                    projection_receipt=LookalikeReceipt(parent["fingerprint"]),
                ),
            )
        ),
    )
    assert wrong_shape == {
        "schema": RESPONSE_SCHEMA,
        "state": "HELD",
        "reason": "TERMINAL_FACTS_INVALID",
    }


def test_mode_cardinality_is_closed_and_non_interchangeable() -> None:
    parent = valid_parent()
    for facts, reason in (
        (DialogueObservationFacts(active=(_active(), _active())), "MULTIPLE_ACTIVE_BINDINGS"),
        (
            DialogueObservationFacts(active=(_active(),), terminal=(_terminal(),)),
            "OBSERVATION_MODE_CONFLICT",
        ),
        (
            DialogueObservationFacts(terminal=(_terminal(), _terminal())),
            "MULTIPLE_TERMINAL_BINDINGS",
        ),
    ):
        response = reduce_dialogue_observation(parent=parent, facts=facts)
        assert response == {
            "schema": RESPONSE_SCHEMA,
            "state": "CONFLICT",
            "reason": reason,
        }

    assert reduce_dialogue_observation(
        parent=parent,
        facts=DialogueObservationFacts(complete=False),
    ) == {
        "schema": RESPONSE_SCHEMA,
        "state": "UNKNOWN",
        "reason": "OBSERVATION_SCAN_INCOMPLETE",
    }
