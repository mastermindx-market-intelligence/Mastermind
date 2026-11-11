from __future__ import annotations

import copy
import hashlib
import itertools
import json

import pytest

from common.agent_dialogue_contract import DialogueContractError, semantic_fingerprint
from common.agent_dialogue_contract_v2 import (
    MESSAGE_SCHEMA_V2,
    PARENT_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    build_message_v2,
    build_parent_v2,
)
from common.agent_dialogue_turn_watcher import (
    ATTENTION_SOURCE_KIND,
    ATTENTION_WAKE_KIND,
    TurnAction,
    TurnRoutingFacts,
    classify_turn,
)


REPO = "example/fixture"
PRINCIPAL = {
    "kind": "executive_principal",
    "seat": "coo",
    "reasoning_surface": "claude",
    "principal_binding_digest": "a" * 64,
    "mission_authority_ref": "mission/example-root-001",
    "authority_generation_digest": "b" * 64,
    "capability_profile_digest": "c" * 64,
    "root_job_id": "JOB-ROOT-001",
}
FOREIGN_ROOT_PRINCIPAL = dict(PRINCIPAL, root_job_id="JOB-ROOT-OTHER")
CEO = {
    "kind": "executive_surface",
    "seat": "ceo",
    "reasoning_surface": "codex",
}
COO = {
    "kind": "executive_surface",
    "seat": "coo",
    "reasoning_surface": "claude",
}
CHAIRMAN = {
    "kind": "executive_surface",
    "seat": "chairman",
    "reasoning_surface": "chatgpt",
}
WORKER = {
    "kind": "worker_attempt",
    "job_id": "JOB-UNIT-001",
    "attempt_id": "ATTEMPT-UNIT-001",
    "worker_id": "worker-unit-a",
}
WORKER_APPLIES_TO = {
    "kind": "executive_attempt",
    "job_id": "JOB-UNIT-001",
    "attempt_id": "ATTEMPT-UNIT-001",
    "worker_id": "worker-unit-a",
}
OTHER_WORKER = {
    "kind": "worker_attempt",
    "job_id": "JOB-UNIT-001",
    "attempt_id": "ATTEMPT-UNIT-002",
    "worker_id": "worker-unit-b",
}
OTHER_WORKER_APPLIES_TO = {
    "kind": "executive_attempt",
    "job_id": "JOB-UNIT-001",
    "attempt_id": "ATTEMPT-UNIT-002",
    "worker_id": "worker-unit-b",
}


def _bodies() -> dict[str, dict[str, object]]:
    return {
        "ACK": {"acknowledged": True},
        "PROGRESS": {
            "stage": "worker",
            "completed": "The bounded stage completed.",
            "next": "Await the existing disposition.",
        },
        "RESULT": {
            "status": "PASS",
            "result": "The bounded worker result.",
        },
        "BLOCKED": {
            "blocker_code": "SOURCE_MOVED",
            "reason": "The protected source moved.",
            "needed_from": "sol",
            "work_paused": True,
        },
        "DECISION_REQUEST": {
            "question": "Which bounded path should continue?",
            "outcome_impact": "The choice affects only the worker attempt.",
            "options": [
                {
                    "id": "opt-continue",
                    "summary": "Continue.",
                    "consequence": "The bounded task continues.",
                    "disposition": "CONTINUE",
                    "authority_effect": "NONE",
                }
            ],
            "recommendation": "opt-continue",
            "work_paused": True,
        },
        "RULING": {
            "authority_class": "WITHIN_COMMISSION",
            "selected_option": "opt-continue",
            "decision": "Continue the bounded path.",
            "rationale": "It preserves the frozen scope.",
            "canonical_ref": None,
        },
        "CONTINUE": {
            "instruction": "Continue within the frozen scope.",
            "stop_condition": "Stop on source movement.",
            "scope_change": False,
        },
        "STOP": {
            "reason": "The bounded outcome is complete.",
            "next_authority": "sol",
        },
    }


def _parent() -> dict[str, object]:
    return build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": {
                "repository": REPO,
                "commit": "a" * 40,
                "path": "docs/fixture.md",
                "content_sha256": "b" * 64,
            },
            "session_ref": "asd-session-principal01",
            "operation_key": "principal-turn-classification-01",
            "watch_mode": TURN_WATCH_MODE_V1,
            "allowed_sol_user_ids": ["U012345678"],
            "created_at": "2026-10-13T00:00:00Z",
        }
    )


def _message(
    message_type: str,
    index: int,
    *,
    reply_to: str | None = None,
    actor: dict[str, object] | None = None,
    applies_to: dict[str, object] | None = None,
    parent: dict[str, object] | None = None,
) -> dict[str, object]:
    thread_parent = _parent() if parent is None else parent
    if actor is None:
        actor = PRINCIPAL
        if applies_to is None:
            applies_to = WORKER_APPLIES_TO
    if applies_to is None:
        applies_to = (
            {
                "kind": "executive_attempt",
                **{
                    key: actor[key]
                    for key in ("job_id", "attempt_id", "worker_id")
                },
            }
            if actor["kind"] == "worker_attempt"
            else {
                "kind": "repository",
                "repository": REPO,
                "head_sha": "a" * 40,
                "pr": f"{REPO}#1",
            }
        )
    return build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": f"asd-principal-{index:08d}",
            "message_type": message_type,
            "work_ref": str(thread_parent["work_ref"]),
            "commission_ref": copy.deepcopy(thread_parent["commission_ref"]),
            "session_ref": str(thread_parent["session_ref"]),
            "actor_ref": copy.deepcopy(actor),
            "reply_to_message_key": reply_to,
            "applies_to": copy.deepcopy(applies_to),
            "summary": "One synthetic principal classification case.",
            "body": copy.deepcopy(_bodies()[message_type]),
            "evidence_refs": [f"https://github.com/{REPO}/pull/{index}"],
            "requires_response": message_type in {"DECISION_REQUEST", "BLOCKED"},
            "created_at": "2026-10-13T00:01:00Z",
        }
    )


def _facts(
    parent: dict[str, object] | None = None,
    *,
    root_job_id: str | None = "JOB-ROOT-001",
    ceo: bool = True,
    coo: bool = True,
) -> TurnRoutingFacts:
    thread_parent = _parent() if parent is None else parent
    return TurnRoutingFacts(
        bound_operation_key=str(thread_parent["operation_key"]),
        bound_commission_fingerprint=str(thread_parent["fingerprint"]),
        root_job_id=root_job_id,
        routing_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_workstream="WS:WORKER-PRESENCE",
        ceo_target_bound=ceo,
        coo_target_bound=coo,
    )


def _decide(
    *messages: dict[str, object],
    parent: dict[str, object] | None = None,
    routing: TurnRoutingFacts | None = None,
):
    thread_parent = _parent() if parent is None else parent
    return classify_turn(
        parent=thread_parent,
        messages=list(messages),
        routing=_facts(thread_parent) if routing is None else routing,
    )


def _expected_source_ref(
    parent: dict[str, object],
    message: dict[str, object],
    target_seat: str,
) -> str:
    identity = {
        "attention_kind": ATTENTION_WAKE_KIND,
        "commission_fingerprint": parent["fingerprint"],
        "message_key": message["message_key"],
        "source_kind": ATTENTION_SOURCE_KIND,
        "target_seat": target_seat,
    }
    payload = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return ATTENTION_SOURCE_KIND + ":" + hashlib.sha256(payload).hexdigest()


def _worker_material(message_type: str, index: int, **kwargs) -> dict[str, object]:
    return _message(
        message_type,
        index,
        actor=WORKER,
        applies_to=WORKER_APPLIES_TO,
        **kwargs,
    )


def test_principal_ruling_of_worker_request_wakes_coo() -> None:
    request = _worker_material("DECISION_REQUEST", 1)
    ruling = _message("RULING", 2, reply_to=str(request["message_key"]))
    parent = _parent()

    decision = _decide(request, ruling, parent=parent)

    assert decision.action is TurnAction.WAKE_COO
    assert decision.reason == "DIALOGUE_TURN_PENDING"
    assert decision.refusal_code is None
    assert decision.attention is not None
    assert decision.attention.message_key == ruling["message_key"]
    assert decision.attention.message_fingerprint == ruling["fingerprint"]
    assert decision.attention.target_seat == "coo"
    assert decision.attention.operation_key == parent["operation_key"]
    assert decision.attention.evidence_refs == tuple(ruling["evidence_refs"])
    assert decision.attention.source_ref == _expected_source_ref(
        parent, ruling, "coo"
    )


def test_principal_continue_of_direct_worker_progress_wakes_coo() -> None:
    progress = _worker_material("PROGRESS", 1)
    continuation = _message(
        "CONTINUE", 2, reply_to=str(progress["message_key"])
    )

    decision = _decide(progress, continuation)

    assert decision.action is TurnAction.WAKE_COO
    assert decision.attention is not None
    assert decision.attention.message_key == continuation["message_key"]
    assert decision.attention.target_seat == "coo"


def test_principal_continue_of_worker_result_wakes_coo() -> None:
    result = _worker_material("RESULT", 1)
    continuation = _message("CONTINUE", 2, reply_to=str(result["message_key"]))

    decision = _decide(result, continuation)

    assert decision.action is TurnAction.WAKE_COO
    assert decision.attention is not None
    assert decision.attention.message_key == continuation["message_key"]


def test_principal_stop_of_worker_result_is_wake_coo_terminal() -> None:
    result = _worker_material("RESULT", 1)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]))

    decision = _decide(result, stop)

    assert decision.action is TurnAction.WAKE_COO_TERMINAL
    assert decision.reason == "DIALOGUE_TURN_PENDING"
    assert decision.attention is not None
    assert decision.attention.message_key == stop["message_key"]
    assert decision.attention.target_seat == "coo"


def test_principal_stop_is_consumed_only_by_the_exact_worker_ack() -> None:
    result = _worker_material("RESULT", 1)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]))
    receipt = _worker_material("ACK", 3, reply_to=str(stop["message_key"]))

    terminal = _decide(result, stop, receipt)

    assert terminal.action is TurnAction.TERMINAL
    assert terminal.attention is None
    assert terminal.reason == "DIALOGUE_STOP_CONSUMED"
    assert terminal.refusal_code is None


def test_worker_ack_of_the_original_return_does_not_consume_a_stop() -> None:
    result = _worker_material("RESULT", 1)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]))
    receipt = _worker_material("ACK", 3, reply_to=str(result["message_key"]))

    decision = _decide(result, stop, receipt)
    reference = _decide(result, stop)

    assert decision == reference
    assert decision.action is TurnAction.WAKE_COO_TERMINAL


def test_principal_stop_rejects_a_different_worker_ack() -> None:
    result = _worker_material("RESULT", 1)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]))
    foreign = _message(
        "ACK",
        3,
        reply_to=str(stop["message_key"]),
        actor=OTHER_WORKER,
        applies_to=OTHER_WORKER_APPLIES_TO,
    )

    decision = _decide(result, stop, foreign)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_stop_rejects_a_coo_surface_ack() -> None:
    result = _worker_material("RESULT", 1)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]))
    receipt = _message("ACK", 3, reply_to=str(stop["message_key"]), actor=COO)

    decision = _decide(result, stop, receipt)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_stop_rejects_a_quiet_leaf_instead_of_a_worker_ack() -> None:
    result = _worker_material("RESULT", 1)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]))
    progress = _worker_material("PROGRESS", 3, reply_to=str(stop["message_key"]))

    decision = _decide(result, stop, progress)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


@pytest.mark.parametrize("quiet", ["ACK", "PROGRESS"])
def test_quiet_worker_annotations_preserve_original_request_lineage(quiet) -> None:
    request = _worker_material("DECISION_REQUEST", 1)
    update = _worker_material(quiet, 2, reply_to=str(request["message_key"]))
    ruling = _message("RULING", 3, reply_to=str(request["message_key"]))
    parent = _parent()

    annotated = _decide(request, update, ruling, parent=parent)
    reference = _decide(request, ruling, parent=parent)

    assert annotated == reference
    assert annotated.action is TurnAction.WAKE_COO
    assert annotated.attention is not None
    assert annotated.attention.message_key == ruling["message_key"]


def test_quiet_chain_before_stop_still_disposes_the_original_return() -> None:
    result = _worker_material("RESULT", 1)
    first = _worker_material("ACK", 2, reply_to=str(result["message_key"]))
    second = _worker_material("PROGRESS", 3, reply_to=str(first["message_key"]))
    stop = _message("STOP", 4, reply_to=str(result["message_key"]))
    receipt = _worker_material("ACK", 5, reply_to=str(stop["message_key"]))

    pending = _decide(result, first, second, stop)
    terminal = _decide(result, first, second, stop, receipt)

    assert pending.action is TurnAction.WAKE_COO_TERMINAL
    assert pending.attention is not None
    assert pending.attention.message_key == stop["message_key"]
    assert terminal.action is TurnAction.TERMINAL


def test_principal_command_may_not_chain_off_a_quiet_annotation() -> None:
    result = _worker_material("RESULT", 1)
    update = _worker_material("PROGRESS", 2, reply_to=str(result["message_key"]))
    ruling = _message("RULING", 3, reply_to=str(update["message_key"]))

    decision = _decide(result, update, ruling)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_root_must_match_trusted_routing_root() -> None:
    request = _worker_material("DECISION_REQUEST", 1)
    ruling = _message("RULING", 2, reply_to=str(request["message_key"]))

    foreign = _decide(
        request, ruling, routing=_facts(root_job_id="JOB-ROOT-OTHER")
    )
    missing = _decide(request, ruling, routing=_facts(root_job_id=None))

    assert foreign.action is TurnAction.REFUSE
    assert foreign.refusal_code == "DIALOGUE_BINDING_MISMATCH"
    assert missing.action is TurnAction.REFUSE
    assert missing.refusal_code == "DIALOGUE_BINDING_MISMATCH"


def test_foreign_principal_actor_root_refuses_even_as_non_leaf() -> None:
    result = _worker_material("RESULT", 1)
    foreign_continuation = _message(
        "CONTINUE", 3, reply_to=str(result["message_key"])
    )
    foreign_continuation["actor_ref"] = dict(FOREIGN_ROOT_PRINCIPAL)
    foreign_continuation["fingerprint"] = semantic_fingerprint(
        foreign_continuation
    )

    decision = _decide(result, foreign_continuation)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "DIALOGUE_BINDING_MISMATCH"


def test_principal_applies_to_must_match_the_worker_return() -> None:
    result = _worker_material("RESULT", 1)
    continuation = _message(
        "CONTINUE",
        2,
        reply_to=str(result["message_key"]),
        applies_to=OTHER_WORKER_APPLIES_TO,
    )

    decision = _decide(result, continuation)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_command_of_a_coo_surface_return_refuses() -> None:
    result = _message("RESULT", 1, actor=COO)
    ruling = _message("RULING", 2, reply_to=str(result["message_key"]))

    decision = _decide(result, ruling)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_ruling_requires_a_valid_selected_option() -> None:
    request = _worker_material("DECISION_REQUEST", 1)
    ruling = _message("RULING", 2, reply_to=str(request["message_key"]))
    ruling["body"] = dict(ruling["body"], selected_option="opt-other")
    ruling["fingerprint"] = semantic_fingerprint(ruling)

    decision = _decide(request, ruling)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


@pytest.mark.parametrize("subject_type", ["PROGRESS", "RESULT", "BLOCKED", "ACK"])
def test_principal_ruling_requires_a_decision_request(subject_type) -> None:
    subject = _worker_material(subject_type, 1)
    ruling = _message("RULING", 2, reply_to=str(subject["message_key"]))

    decision = _decide(subject, ruling)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_continue_cannot_lift_an_external_blocker() -> None:
    blocked = _worker_material("BLOCKED", 1)
    blocked["body"] = dict(blocked["body"], needed_from="external")
    blocked["fingerprint"] = semantic_fingerprint(blocked)
    continuation = _message("CONTINUE", 2, reply_to=str(blocked["message_key"]))

    decision = _decide(blocked, continuation)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_continue_of_a_sol_blocked_worker_is_lawful() -> None:
    blocked = _worker_material("BLOCKED", 1)
    continuation = _message("CONTINUE", 2, reply_to=str(blocked["message_key"]))

    decision = _decide(blocked, continuation)

    assert decision.action is TurnAction.WAKE_COO
    assert decision.attention is not None
    assert decision.attention.message_key == continuation["message_key"]


def test_principal_continue_requires_the_worker_update_family() -> None:
    request = _worker_material("DECISION_REQUEST", 1)
    continuation = _message("CONTINUE", 2, reply_to=str(request["message_key"]))

    decision = _decide(request, continuation)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_principal_vocabulary_stays_command_only() -> None:
    result = _worker_material("RESULT", 1)
    with pytest.raises(DialogueContractError) as caught:
        _message("ACK", 2, reply_to=str(result["message_key"]))

    assert caught.value.code == "MESSAGE_INVALID"


def test_worker_returns_still_wake_ceo_after_a_principal_command() -> None:
    progress = _worker_material("PROGRESS", 1)
    continuation = _message("CONTINUE", 2, reply_to=str(progress["message_key"]))
    result = _worker_material("RESULT", 3, reply_to=str(continuation["message_key"]))

    decision = _decide(progress, continuation, result)

    assert decision.action is TurnAction.WAKE_CEO
    assert decision.attention is not None
    assert decision.attention.target_seat == "ceo"
    assert decision.attention.message_key == result["message_key"]


def test_unbound_coo_target_never_falls_through_to_ceo() -> None:
    result = _worker_material("RESULT", 1)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]))

    decision = _decide(
        result, stop, routing=_facts(ceo=True, coo=False)
    )

    assert decision.action is TurnAction.NO_ACTION
    assert decision.attention is None
    assert decision.reason == "DIALOGUE_WAKE_TARGET_UNBOUND"
    assert decision.refusal_code == "DIALOGUE_WAKE_TARGET_UNBOUND"


def test_two_principal_commands_on_one_return_remain_a_fork() -> None:
    result = _worker_material("RESULT", 1)
    continuation = _message("CONTINUE", 2, reply_to=str(result["message_key"]))
    stop = _message("STOP", 3, reply_to=str(result["message_key"]))

    decision = _decide(result, continuation, stop)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "DIALOGUE_FORKED"


def test_principal_command_and_quiet_annotation_share_one_return() -> None:
    request = _worker_material("DECISION_REQUEST", 1)
    update = _worker_material("PROGRESS", 2, reply_to=str(request["message_key"]))
    ruling = _message("RULING", 3, reply_to=str(request["message_key"]))
    parent = _parent()

    reference = _decide(request, update, ruling, parent=parent)
    assert reference.action is TurnAction.WAKE_COO
    for order in itertools.permutations((request, update, ruling)):
        assert _decide(*order, parent=parent) == reference


def test_invalid_principal_command_leaf_still_refuses() -> None:
    result = _worker_material("RESULT", 1)
    ruling = _message("RULING", 2, reply_to=str(result["message_key"]))

    decision = _decide(result, ruling)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_historical_invalid_principal_successor_reconciliation_is_preserved() -> None:
    result = _worker_material("RESULT", 1)
    invalid_ruling = _message("RULING", 2, reply_to=str(result["message_key"]))
    progress = _worker_material(
        "PROGRESS", 3, reply_to=str(invalid_ruling["message_key"])
    )

    decision = _decide(result, invalid_ruling, progress)

    assert decision.action is TurnAction.NO_ACTION
    assert decision.reason == "DIALOGUE_PROGRESS"
    assert decision.refusal_code is None


def test_legacy_ceo_stop_and_coo_consumption_are_unchanged() -> None:
    result = _message("RESULT", 1, actor=COO)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]), actor=CEO)
    receipt = _message("ACK", 3, reply_to=str(stop["message_key"]), actor=COO)

    pending = _decide(result, stop)
    terminal = _decide(result, stop, receipt)

    assert pending.action is TurnAction.WAKE_COO_TERMINAL
    assert terminal.action is TurnAction.TERMINAL
    assert terminal.reason == "DIALOGUE_STOP_CONSUMED"


def test_worker_ack_still_cannot_consume_a_legacy_ceo_stop() -> None:
    result = _message("RESULT", 1, actor=COO)
    stop = _message("STOP", 2, reply_to=str(result["message_key"]), actor=CEO)
    receipt = _worker_material("ACK", 3, reply_to=str(stop["message_key"]))

    decision = _decide(result, stop, receipt)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "REPLY_LINEAGE_INVALID"


def test_legacy_chairman_sender_still_refuses() -> None:
    result = _worker_material("RESULT", 1)
    ruling = _message(
        "RULING",
        2,
        reply_to=str(result["message_key"]),
        actor=CHAIRMAN,
    )

    decision = _decide(result, ruling)

    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == "DIALOGUE_SENDER_INVALID"


def test_principal_stop_cycle_is_order_independent_and_replay_stable() -> None:
    result = _worker_material("RESULT", 1)
    update = _worker_material("PROGRESS", 2, reply_to=str(result["message_key"]))
    stop = _message("STOP", 3, reply_to=str(result["message_key"]))
    receipt = _worker_material("ACK", 4, reply_to=str(stop["message_key"]))
    parent = _parent()

    reference = _decide(result, update, stop, receipt, parent=parent)
    assert reference.action is TurnAction.TERMINAL
    for order in itertools.permutations((result, update, stop, receipt)):
        assert _decide(*order, parent=parent) == reference

    replay = copy.deepcopy(result)
    replay["created_at"] = "2026-10-13T00:02:00Z"
    assert _decide(replay, update, stop, receipt, parent=parent) == reference
