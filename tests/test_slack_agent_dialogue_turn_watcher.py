from __future__ import annotations

import ast
import copy
import hashlib
import json
from dataclasses import asdict, fields
from pathlib import Path

import pytest

from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    build_message_v2,
    build_parent_v2,
)
from integrations.slack_agent_dialogue.turn_watcher import (
    ATTENTION_SCHEMA,
    ATTENTION_SOURCE_KIND,
    ATTENTION_WAKE_KIND,
    AgentDialogueAttention,
    TurnAction,
    TurnDecision,
    TurnRoutingFacts,
    classify_turn,
)


REPO = "mastermindx-market-intelligence/Mastermind"
EVIDENCE = f"https://github.com/{REPO}/pull/177"
APPLIES_TO = {
    "kind": "repository",
    "repository": REPO,
    "head_sha": "a" * 40,
    "pr": f"{REPO}#177",
}
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
WORKER = {
    "kind": "worker_attempt",
    "job_id": "JOB-001",
    "attempt_id": "ATTEMPT-001",
    "worker_id": "worker-01",
}
WORKER_APPLIES_TO = {
    "kind": "executive_attempt",
    "job_id": "JOB-001",
    "attempt_id": "ATTEMPT-001",
    "worker_id": "worker-01",
}


def _commission(*, content_sha256: str = "b" * 64) -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "c" * 40,
        "path": "research/commission.md",
        "content_sha256": content_sha256,
    }


def _parent(
    *,
    watch_mode: object = TURN_WATCH_MODE_V1,
    operation_key: str = "worker-presence-dialogue-wptw1-20260829-001",
    commission_content_sha256: str = "b" * 64,
) -> dict[str, object]:
    return build_parent_v2(
        {
            "schema": "mastermind.agent_dialogue_parent.v2",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(
                content_sha256=commission_content_sha256
            ),
            "session_ref": "asd-session-turnwatch0001",
            "operation_key": operation_key,
            "watch_mode": watch_mode,
            "allowed_sol_user_ids": ["U0BRETDUAS2"],
            "created_at": "2026-08-29T00:00:00Z",
        }
    )


def _body(message_type: str) -> dict[str, object]:
    return {
        "ACK": {"acknowledged": True},
        "DECISION_REQUEST": {
            "question": "Which bounded path should continue?",
            "outcome_impact": "The choice affects only WP-TW1.",
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
        "BLOCKED": {
            "blocker_code": "SOURCE_MOVED",
            "reason": "The protected source moved.",
            "needed_from": "sol",
            "work_paused": True,
        },
        "PROGRESS": {
            "stage": "classifier",
            "completed": "The pure table is implemented.",
            "next": "Run focused tests.",
        },
        "RESULT": {
            "status": "PASS",
            "result": "The bounded classifier passed.",
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
        "AMENDMENT_AVAILABLE": {
            "canonical_ref": f"https://github.com/{REPO}/commit/" + "d" * 40,
            "summary": "A canonical amendment is available.",
        },
    }[message_type]


def _message(
    message_type: str,
    *,
    key: str,
    reply_to: str | None = None,
    actor: dict[str, object] | None = None,
    applies_to: dict[str, object] | None = None,
    parent: dict[str, object] | None = None,
    summary: str = "One accepted dialogue event.",
    created_at: str = "2026-08-29T00:01:00Z",
) -> dict[str, object]:
    thread_parent = _parent() if parent is None else parent
    if actor is None:
        actor = CEO if message_type in {
            "RULING",
            "CONTINUE",
            "STOP",
            "AMENDMENT_AVAILABLE",
        } else COO
    if applies_to is None:
        applies_to = WORKER_APPLIES_TO if actor == WORKER else APPLIES_TO
    return build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": key,
            "message_type": message_type,
            "work_ref": thread_parent["work_ref"],
            "commission_ref": copy.deepcopy(thread_parent["commission_ref"]),
            "session_ref": thread_parent["session_ref"],
            "actor_ref": copy.deepcopy(actor),
            "reply_to_message_key": reply_to,
            "applies_to": copy.deepcopy(applies_to),
            "summary": summary,
            "body": copy.deepcopy(_body(message_type)),
            "evidence_refs": [EVIDENCE],
            "requires_response": message_type in {"BLOCKED", "DECISION_REQUEST"},
            "created_at": created_at,
        }
    )


def _routing(
    *,
    parent: dict[str, object] | None = None,
    ceo: bool = True,
    coo: bool = True,
) -> TurnRoutingFacts:
    thread_parent = _parent() if parent is None else parent
    return TurnRoutingFacts(
        bound_operation_key=str(thread_parent["operation_key"]),
        bound_commission_fingerprint=str(thread_parent["fingerprint"]),
        root_job_id="JOB-001",
        routing_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_workstream="WS:WORKER-PRESENCE",
        ceo_target_bound=ceo,
        coo_target_bound=coo,
    )


def _decision(
    *messages: dict[str, object],
    parent: dict[str, object] | None = None,
    routing: TurnRoutingFacts | None = None,
) -> TurnDecision:
    thread_parent = _parent() if parent is None else parent
    return classify_turn(
        parent=thread_parent,
        messages=list(messages),
        routing=_routing(parent=thread_parent) if routing is None else routing,
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


def test_contract_vocabulary_and_shapes_are_closed() -> None:
    assert [action.value for action in TurnAction] == [
        "NO_ACTION",
        "WAKE_CEO",
        "WAKE_COO",
        "WAKE_COO_TERMINAL",
        "TERMINAL",
        "REFUSE",
    ]
    assert ATTENTION_SCHEMA == "mastermind.agent_dialogue_attention.v1"
    assert ATTENTION_SOURCE_KIND == "agent_dialogue_attention"
    assert ATTENTION_WAKE_KIND == "dialogue_turn_pending"
    assert [field.name for field in fields(TurnRoutingFacts)] == [
        "bound_operation_key",
        "bound_commission_fingerprint",
        "root_job_id",
        "routing_workstream",
        "source_workstream",
        "ceo_target_bound",
        "coo_target_bound",
    ]
    assert [field.name for field in fields(AgentDialogueAttention)] == [
        "schema",
        "source_kind",
        "source_ref",
        "source_dialogue_schema",
        "message_key",
        "message_fingerprint",
        "commission_fingerprint",
        "operation_key",
        "target_seat",
        "attention_kind",
        "root_job_id",
        "routing_workstream",
        "source_workstream",
        "evidence_refs",
    ]


def test_watch_disabled_is_no_action() -> None:
    disabled = _decision(parent=_parent(watch_mode=None))
    assert disabled == TurnDecision(
        action=TurnAction.NO_ACTION,
        attention=None,
        reason="WATCH_DISABLED",
        refusal_code=None,
    )


def test_bound_initial_commission_projects_parent_attention_to_coo() -> None:
    from integrations.slack_agent_dialogue.contract_v2 import PARENT_SCHEMA_V2

    parent = _parent()
    result = _decision(parent=parent)
    expected_key = f"asd-initial-{parent['fingerprint']}"
    expected_identity = {
        "attention_kind": ATTENTION_WAKE_KIND,
        "commission_fingerprint": parent["fingerprint"],
        "message_key": expected_key,
        "source_kind": ATTENTION_SOURCE_KIND,
        "target_seat": "coo",
    }
    expected_source_ref = ATTENTION_SOURCE_KIND + ":" + hashlib.sha256(
        json.dumps(
            expected_identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()

    assert result.action is TurnAction.WAKE_COO
    assert result.reason == "DIALOGUE_TURN_PENDING"
    assert result.refusal_code is None
    assert result.attention is not None
    assert result.attention.source_dialogue_schema == PARENT_SCHEMA_V2
    assert result.attention.message_key == expected_key
    assert result.attention.message_fingerprint == parent["fingerprint"]
    assert result.attention.commission_fingerprint == parent["fingerprint"]
    assert result.attention.target_seat == "coo"
    assert result.attention.evidence_refs == ()
    assert result.attention.source_ref == expected_source_ref


def test_unbound_initial_commission_is_no_action_without_fallback() -> None:
    result = _decision(routing=_routing(ceo=True, coo=False))

    assert result == TurnDecision(
        action=TurnAction.NO_ACTION,
        attention=None,
        reason="DIALOGUE_WAKE_TARGET_UNBOUND",
        refusal_code="DIALOGUE_WAKE_TARGET_UNBOUND",
    )


def test_replacement_parent_operation_key_cannot_rebind_unchanged_messages() -> None:
    original_parent = _parent()
    message = _message(
        "RESULT",
        key="asd-result-00000001",
        parent=original_parent,
    )
    replacement_parent = _parent(
        operation_key="worker-presence-dialogue-wptw1-20260829-002"
    )

    result = _decision(
        message,
        parent=replacement_parent,
        routing=_routing(parent=original_parent),
    )

    assert result.action is TurnAction.REFUSE
    assert result.attention is None
    assert result.refusal_code == "DIALOGUE_BINDING_MISMATCH"


def test_replacement_parent_fingerprint_refuses_before_history_classification() -> None:
    original_parent = _parent()
    message = _message(
        "RESULT",
        key="asd-result-00000001",
        parent=original_parent,
    )
    replacement_parent = _parent(commission_content_sha256="d" * 64)

    result = _decision(
        message,
        parent=replacement_parent,
        routing=_routing(parent=original_parent),
    )

    assert result.action is TurnAction.REFUSE
    assert result.attention is None
    assert result.refusal_code == "DIALOGUE_BINDING_MISMATCH"


@pytest.mark.parametrize(
    ("message_type", "expected_action", "expected_reason"),
    [
        ("ACK", TurnAction.NO_ACTION, "DIALOGUE_ACKNOWLEDGED"),
        ("PROGRESS", TurnAction.NO_ACTION, "DIALOGUE_PROGRESS"),
        ("BLOCKED", TurnAction.WAKE_CEO, "DIALOGUE_TURN_PENDING"),
        ("DECISION_REQUEST", TurnAction.WAKE_CEO, "DIALOGUE_TURN_PENDING"),
        ("RESULT", TurnAction.WAKE_CEO, "DIALOGUE_TURN_PENDING"),
    ],
)
def test_contributor_classification_table(
    message_type: str,
    expected_action: TurnAction,
    expected_reason: str,
) -> None:
    parent = _parent()
    message = _message(
        message_type,
        key=f"asd-{message_type.lower().replace('_', '-')}-00000001",
        parent=parent,
    )
    result = _decision(message, parent=parent)
    assert result.action is expected_action
    assert result.reason == expected_reason
    if expected_action is TurnAction.WAKE_CEO:
        assert result.attention is not None
        assert result.attention.target_seat == "ceo"
        assert result.attention.source_ref == _expected_source_ref(
            parent, message, "ceo"
        )
        assert result.attention.evidence_refs == (EVIDENCE,)
    else:
        assert result.attention is None


@pytest.mark.parametrize(
    ("message_type", "request_type", "expected_action"),
    [
        ("RULING", "DECISION_REQUEST", TurnAction.WAKE_COO),
        ("CONTINUE", "PROGRESS", TurnAction.WAKE_COO),
        ("AMENDMENT_AVAILABLE", "RESULT", TurnAction.WAKE_COO),
        ("STOP", "RESULT", TurnAction.WAKE_COO_TERMINAL),
    ],
)
def test_ceo_classification_table(
    message_type: str,
    request_type: str,
    expected_action: TurnAction,
) -> None:
    parent = _parent()
    request = _message(
        request_type,
        key="asd-request-00000001",
        parent=parent,
    )
    reply = _message(
        message_type,
        key=f"asd-{message_type.lower().replace('_', '-')}-00000001",
        reply_to=str(request["message_key"]),
        parent=parent,
    )
    result = _decision(request, reply, parent=parent)
    assert result.action is expected_action
    assert result.reason == "DIALOGUE_TURN_PENDING"
    assert result.attention is not None
    assert result.attention.target_seat == "coo"
    assert result.attention.source_ref == _expected_source_ref(
        parent, reply, "coo"
    )


def test_current_lineage_result_can_receive_a_lawful_continue() -> None:
    parent = _parent()
    result = _message(
        "RESULT",
        key="asd-result-00000001",
        parent=parent,
    )
    continuation = _message(
        "CONTINUE",
        key="asd-continue-00000001",
        reply_to=str(result["message_key"]),
        parent=parent,
    )

    decision = _decision(result, continuation, parent=parent)

    assert decision.action is TurnAction.WAKE_COO
    assert decision.reason == "DIALOGUE_TURN_PENDING"
    assert decision.refusal_code is None
    assert decision.attention is not None
    assert decision.attention.message_key == continuation["message_key"]
    assert decision.attention.target_seat == "coo"


def test_same_parent_lineage_allows_current_attempt_applicability_to_advance() -> None:
    parent = _parent()
    p1_progress = _message(
        "PROGRESS",
        key="asd-progress-00000001",
        actor=WORKER,
        applies_to=WORKER_APPLIES_TO,
        parent=parent,
    )
    p2_worker = {
        "kind": "worker_attempt",
        "job_id": "JOB-001",
        "attempt_id": "ATTEMPT-002",
        "worker_id": "worker-02",
    }
    p2_applies_to = {
        "kind": "executive_attempt",
        "job_id": "JOB-001",
        "attempt_id": "ATTEMPT-002",
        "worker_id": "worker-02",
    }
    p2_result = _message(
        "RESULT",
        key="asd-result-00000002",
        reply_to=str(p1_progress["message_key"]),
        actor=p2_worker,
        applies_to=p2_applies_to,
        parent=parent,
    )

    decision = _decision(p1_progress, p2_result, parent=parent)

    assert decision.action is TurnAction.WAKE_CEO
    assert decision.reason == "DIALOGUE_TURN_PENDING"
    assert decision.refusal_code is None
    assert decision.attention is not None
    assert decision.attention.message_key == p2_result["message_key"]
    assert decision.attention.target_seat == "ceo"


@pytest.mark.parametrize(
    ("message_type", "ceo_bound", "coo_bound"),
    [("RESULT", False, True), ("STOP", True, False)],
)
def test_unbound_target_never_falls_through_to_other_seat(
    message_type: str,
    ceo_bound: bool,
    coo_bound: bool,
) -> None:
    parent = _parent()
    request = _message("PROGRESS", key="asd-request-00000001", parent=parent)
    messages = [request]
    if message_type == "RESULT":
        messages = [_message("RESULT", key="asd-result-00000001", parent=parent)]
    else:
        messages.append(
            _message(
                "STOP",
                key="asd-stop-00000001",
                reply_to=str(request["message_key"]),
                parent=parent,
            )
        )
    result = _decision(
        *messages,
        parent=parent,
        routing=_routing(ceo=ceo_bound, coo=coo_bound),
    )
    assert result.action is TurnAction.NO_ACTION
    assert result.attention is None
    assert result.reason == "DIALOGUE_WAKE_TARGET_UNBOUND"
    assert result.refusal_code == "DIALOGUE_WAKE_TARGET_UNBOUND"


def test_stop_requires_exact_later_coo_consumption_to_be_terminal() -> None:
    parent = _parent()
    request = _message("RESULT", key="asd-result-00000001", parent=parent)
    stop = _message(
        "STOP",
        key="asd-stop-00000001",
        reply_to=str(request["message_key"]),
        parent=parent,
    )
    first = _decision(request, stop, parent=parent)
    repeated = _decision(
        copy.deepcopy(request),
        copy.deepcopy(stop),
        parent=copy.deepcopy(parent),
    )
    assert first == repeated
    assert first.action is TurnAction.WAKE_COO_TERMINAL

    unrelated_ack = _message("ACK", key="asd-ack-00000001", parent=parent)
    refused = _decision(request, stop, unrelated_ack, parent=parent)
    assert refused.action is TurnAction.REFUSE
    assert refused.refusal_code == "DIALOGUE_FORKED"

    consumed = _message(
        "ACK",
        key="asd-ack-00000002",
        reply_to=str(stop["message_key"]),
        parent=parent,
    )
    terminal = _decision(request, stop, consumed, parent=parent)
    assert terminal.action is TurnAction.TERMINAL
    assert terminal.attention is None
    assert terminal.reason == "DIALOGUE_STOP_CONSUMED"


def test_worker_ack_cannot_launder_terminal_coo_consumption() -> None:
    parent = _parent()
    request = _message("RESULT", key="asd-result-00000001", parent=parent)
    stop = _message(
        "STOP",
        key="asd-stop-00000001",
        reply_to=str(request["message_key"]),
        parent=parent,
    )
    worker_ack = _message(
        "ACK",
        key="asd-worker-ack-00000001",
        reply_to=str(stop["message_key"]),
        actor=WORKER,
        applies_to=WORKER_APPLIES_TO,
        parent=parent,
    )
    result = _decision(request, stop, worker_ack, parent=parent)
    assert result.action is TurnAction.REFUSE
    assert result.refusal_code == "REPLY_LINEAGE_INVALID"


def test_duplicate_delivery_collapses_but_changed_payload_conflicts() -> None:
    parent = _parent()
    result = _message("RESULT", key="asd-result-00000001", parent=parent)
    duplicate = copy.deepcopy(result)
    duplicate["created_at"] = "2026-08-29T00:02:00Z"
    assert _decision(result, duplicate, parent=parent) == _decision(
        result, parent=parent
    )

    changed = _message(
        "RESULT",
        key="asd-result-00000001",
        parent=parent,
        summary="Changed semantic payload under the same key.",
    )
    conflict = _decision(result, changed, parent=parent)
    assert conflict.action is TurnAction.REFUSE
    assert conflict.refusal_code == "MESSAGE_KEY_CONFLICT"


def test_competing_semantic_leaves_refuse_instead_of_choosing_newest_time() -> None:
    parent = _parent()
    request = _message(
        "DECISION_REQUEST",
        key="asd-request-00000001",
        parent=parent,
    )
    ruling = _message(
        "RULING",
        key="asd-ruling-00000001",
        reply_to=str(request["message_key"]),
        parent=parent,
        created_at="2026-08-29T00:10:00Z",
    )
    stop = _message(
        "STOP",
        key="asd-stop-00000001",
        reply_to=str(request["message_key"]),
        parent=parent,
        created_at="2026-08-29T00:20:00Z",
    )
    forked = _decision(request, ruling, stop, parent=parent)
    assert forked.action is TurnAction.REFUSE
    assert forked.refusal_code == "DIALOGUE_FORKED"


@pytest.mark.parametrize(
    ("reply_type", "request_type"),
    [("RULING", "PROGRESS"), ("CONTINUE", "DECISION_REQUEST")],
)
def test_actionable_ceo_reply_requires_exact_current_lineage(
    reply_type: str,
    request_type: str,
) -> None:
    parent = _parent()
    request = _message(
        request_type,
        key="asd-request-00000001",
        parent=parent,
    )
    reply = _message(
        reply_type,
        key="asd-reply-00000001",
        reply_to=str(request["message_key"]),
        parent=parent,
    )
    result = _decision(request, reply, parent=parent)
    assert result.action is TurnAction.REFUSE
    assert result.refusal_code == "REPLY_LINEAGE_INVALID"


def test_cross_thread_or_invalid_message_applicability_refuses() -> None:
    parent = _parent()
    result = _message("RESULT", key="asd-result-00000001", parent=parent)

    changed_parent = copy.deepcopy(parent)
    changed_parent["session_ref"] = "asd-session-turnwatch0002"
    invalid_parent = _decision(result, parent=changed_parent)
    assert invalid_parent.action is TurnAction.REFUSE
    assert invalid_parent.refusal_code == "FINGERPRINT_MISMATCH"

    invalid_scope = _message(
        "ACK",
        key="asd-ack-00000001",
        reply_to=str(result["message_key"]),
        parent=parent,
    )
    invalid_scope["actor_ref"] = copy.deepcopy(WORKER)
    context = _decision(result, invalid_scope, parent=parent)
    assert context.action is TurnAction.REFUSE
    assert context.refusal_code == "MESSAGE_INVALID"


def test_attention_identity_excludes_routing_destination_and_is_restart_stable() -> None:
    parent = _parent()
    result = _message("RESULT", key="asd-result-00000001", parent=parent)
    first = _decision(result, parent=parent, routing=_routing())
    rotated = _decision(
        copy.deepcopy(result),
        parent=copy.deepcopy(parent),
        routing=TurnRoutingFacts(
            bound_operation_key=str(parent["operation_key"]),
            bound_commission_fingerprint=str(parent["fingerprint"]),
            root_job_id="JOB-ROTATED",
            routing_workstream="WS:ROTATED-ROUTE",
            source_workstream="WS:ROTATED-SOURCE",
            ceo_target_bound=True,
            coo_target_bound=True,
        ),
    )
    assert first.attention is not None
    assert rotated.attention is not None
    assert first.attention.source_ref == rotated.attention.source_ref
    assert asdict(first) == asdict(
        _decision(
            copy.deepcopy(result),
            parent=copy.deepcopy(parent),
            routing=copy.deepcopy(_routing()),
        )
    )


def test_attention_shape_contains_no_transport_provider_or_session_authority() -> None:
    result = _decision(_message("RESULT", key="asd-result-00000001"))
    assert result.attention is not None
    forbidden = {
        "slack_ts",
        "event_id",
        "retry_count",
        "provider",
        "model",
        "account",
        "native_handle",
        "runtime_binding_generation",
        "session_alias",
        "display_name",
    }
    assert forbidden.isdisjoint(asdict(result.attention))


def test_module_has_only_pure_imports_and_no_control_plane_or_write_surface() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "common"
        / "agent_dialogue_turn_watcher.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports <= {
        "__future__",
        "dataclasses",
        "enum",
        "hashlib",
        "json",
        "typing",
        "common.agent_dialogue_contract",
        "common.agent_dialogue_contract_v2",
    }
    forbidden_fragments = {
        "sqlite3",
        "asyncio",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "slack_sdk",
        "socket",
        "subprocess",
        "control_plane",
        "open(",
        "pathlib",
        "threading",
        "browser",
    }
    assert not any(fragment in source for fragment in forbidden_fragments)


# Pending-obligation public-entry regression extension. Synthetic identities only.
import copy
import itertools
from dataclasses import asdict, replace
import pytest
from common.agent_dialogue_contract import semantic_fingerprint
from common.agent_dialogue_contract_v2 import MESSAGE_SCHEMA_V2, PARENT_SCHEMA_V2, TURN_WATCH_MODE_V1, build_message_v2, build_parent_v2, parse_message_frame_v2, parse_parent_frame_v2, render_message_v2, render_parent_v2
from common.agent_dialogue_turn_watcher import TurnAction, TurnRoutingFacts, classify_turn
_PENDING_REPO = 'example/fixture'
_PENDING_COO = {'kind': 'executive_surface', 'seat': 'coo', 'reasoning_surface': 'claude'}
_PENDING_CEO = {'kind': 'executive_surface', 'seat': 'ceo', 'reasoning_surface': 'chatgpt'}
_PENDING_WORKER = {'kind': 'worker_attempt', 'job_id': 'JOB-UNIT', 'attempt_id': 'ATTEMPT-UNIT', 'worker_id': 'worker-unit'}

def _pending_parent():
    raw = build_parent_v2({'schema': PARENT_SCHEMA_V2, 'work_ref': 'WS:CHAIRMAN-CONTROL-ROOM', 'commission_ref': {'repository': _PENDING_REPO, 'commit': 'a' * 40, 'path': 'docs/fixture.md', 'content_sha256': 'b' * 64}, 'session_ref': 'asd-session-public0001', 'operation_key': 'pending-obligation-public-20260907', 'watch_mode': TURN_WATCH_MODE_V1, 'allowed_sol_user_ids': ['U012345678'], 'created_at': '2026-09-07T00:00:00Z'})
    return parse_parent_frame_v2(render_parent_v2(raw).encode())

def _pending_msg(kind, index, previous=None, *, actor=None, **body_change):
    source = _pending_parent()
    actor = actor or (_PENDING_CEO if kind in {'CONTINUE', 'RULING', 'STOP', 'AMENDMENT_AVAILABLE'} else _PENDING_COO)
    bodies = {'ACK': {'acknowledged': True}, 'PROGRESS': {'stage': 'verify', 'completed': 'Evidence retained.', 'next': 'Await the existing parent decision.'}, 'RESULT': {'status': 'PASS', 'result': 'Prepared fixture result.'}, 'BLOCKED': {'blocker_code': 'SOURCE_MOVED', 'reason': 'Fixture source changed.', 'needed_from': 'sol', 'work_paused': True}, 'DECISION_REQUEST': {'question': 'Inspect the corrected inventory?', 'outcome_impact': 'One required ID is absent.', 'options': [{'id': 'opt-repair', 'summary': 'Inspect repair.', 'consequence': 'Check restored IDs.', 'disposition': 'CONTINUE', 'authority_effect': 'NONE'}], 'recommendation': 'opt-repair', 'work_paused': True}, 'RULING': {'authority_class': 'WITHIN_COMMISSION', 'selected_option': 'opt-repair', 'decision': 'Inspect the repair.', 'rationale': 'Preserve the declared inventory.', 'canonical_ref': None}, 'CONTINUE': {'instruction': 'Inspect the evidence.', 'stop_condition': 'Stop after the next result.', 'scope_change': False}, 'STOP': {'reason': 'Fixture child completed.', 'next_authority': 'sol'}, 'AMENDMENT_AVAILABLE': {'canonical_ref': f'https://github.com/{_PENDING_REPO}/commit/' + 'c' * 40, 'summary': 'Read the existing amendment.'}}
    applies = {'kind': 'executive_attempt', **{k: actor[k] for k in ('job_id', 'attempt_id', 'worker_id')}} if actor['kind'] == 'worker_attempt' else {'kind': 'repository', 'repository': _PENDING_REPO, 'head_sha': 'a' * 40, 'pr': _PENDING_REPO + '#1'}
    value = build_message_v2({'schema': MESSAGE_SCHEMA_V2, 'message_key': f'asd-public-{index:08d}', 'message_type': kind, 'work_ref': source['work_ref'], 'commission_ref': source['commission_ref'], 'session_ref': source['session_ref'], 'actor_ref': copy.deepcopy(actor), 'reply_to_message_key': previous['message_key'] if previous else None, 'applies_to': applies, 'summary': 'Synthetic public classifier case.', 'body': bodies[kind] | body_change, 'evidence_refs': [f'https://github.com/{_PENDING_REPO}/pull/{index}'], 'requires_response': kind in {'DECISION_REQUEST', 'BLOCKED'}, 'created_at': '2026-09-07T00:01:00Z'})
    wire = render_message_v2(value)
    parsed = parse_message_frame_v2(wire.encode())
    assert parsed == value
    return parsed

def _pending_facts(p=None, *, ceo=True, coo=True):
    p = _pending_parent() if p is None else p
    return TurnRoutingFacts(p['operation_key'], p['fingerprint'], 'JOB-UNIT', p['work_ref'], p['work_ref'], ceo, coo)

def _pending_decide(*history, routing=None, p=None):
    p = _pending_parent() if p is None else p
    return classify_turn(parent=p, messages=list(history), routing=_pending_facts(p) if routing is None else routing)

@pytest.mark.parametrize('kind', ['RESULT', 'BLOCKED', 'DECISION_REQUEST'])
@pytest.mark.parametrize('quiet', ['ACK', 'PROGRESS'])
@pytest.mark.parametrize('actor', [_PENDING_COO, _PENDING_WORKER], ids=['coo', 'worker'])
def test_public_quiet_update_preserves_original_pending_identity(kind, quiet, actor):
    material = _pending_msg(kind, 1, actor=actor)
    update = _pending_msg(quiet, 2, material, actor=actor)
    original = _pending_decide(material)
    assert original.action is TurnAction.WAKE_CEO
    assert _pending_decide(material, update) == original
    assert original.attention.message_key == material['message_key']
    assert original.attention.message_fingerprint == material['fingerprint']
    assert original.attention.evidence_refs == tuple(material['evidence_refs'])

def test_public_quiet_update_from_different_worker_identity_refuses():
    material = _pending_msg('RESULT', 41, actor=_PENDING_WORKER)
    other = _PENDING_WORKER | {
        'attempt_id': 'ATTEMPT-SECOND',
        'worker_id': 'worker-second',
    }
    update = _pending_msg('PROGRESS', 42, material, actor=other)
    decision = _pending_decide(material, update)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_first_quiet_coo_identity_drift_with_exact_original_target_refuses():
    material = _pending_msg('RESULT', 43, actor=_PENDING_COO)
    update = _pending_msg('PROGRESS', 44, material, actor=_PENDING_COO)
    update['actor_ref'] = _PENDING_COO | {'reasoning_surface': 'codex'}
    assert update['actor_ref'] != material['actor_ref']
    assert update['applies_to'] == material['applies_to']
    update['fingerprint'] = semantic_fingerprint(update)
    decision = _pending_decide(material, update)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_later_quiet_coo_identity_drift_with_exact_original_target_refuses():
    material = _pending_msg('RESULT', 45, actor=_PENDING_COO)
    first = _pending_msg('ACK', 46, material, actor=_PENDING_COO)
    second = _pending_msg('PROGRESS', 47, first, actor=_PENDING_COO)
    second['actor_ref'] = _PENDING_COO | {'reasoning_surface': 'codex'}
    assert second['actor_ref'] != material['actor_ref']
    assert second['applies_to'] == material['applies_to']
    second['fingerprint'] = semantic_fingerprint(second)
    decision = _pending_decide(material, first, second)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_quiet_update_with_changed_coo_repository_target_refuses():
    material = _pending_msg('RESULT', 51, actor=_PENDING_COO)
    update = _pending_msg('PROGRESS', 52, material, actor=_PENDING_COO)
    update['applies_to'] = {
        'kind': 'repository',
        'repository': _PENDING_REPO,
        'head_sha': 'd' * 40,
        'pr': _PENDING_REPO + '#2',
    }
    update['fingerprint'] = semantic_fingerprint(update)
    decision = _pending_decide(material, update)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_later_quiet_identity_drift_refuses():
    material = _pending_msg('RESULT', 61, actor=_PENDING_WORKER)
    first = _pending_msg('ACK', 62, material, actor=_PENDING_WORKER)
    other = _PENDING_WORKER | {
        'attempt_id': 'ATTEMPT-SECOND',
        'worker_id': 'worker-second',
    }
    second = _pending_msg('PROGRESS', 63, first, actor=other)
    decision = _pending_decide(material, first, second)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_later_quiet_repository_target_drift_refuses():
    material = _pending_msg('RESULT', 71, actor=_PENDING_COO)
    first = _pending_msg('ACK', 72, material, actor=_PENDING_COO)
    second = _pending_msg('PROGRESS', 73, first, actor=_PENDING_COO)
    second['applies_to'] = {
        'kind': 'repository',
        'repository': _PENDING_REPO,
        'head_sha': 'e' * 40,
        'pr': _PENDING_REPO + '#3',
    }
    second['fingerprint'] = semantic_fingerprint(second)
    decision = _pending_decide(material, first, second)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_direct_command_does_not_launder_foreign_worker_quiet_branch():
    material = _pending_msg('RESULT', 75, actor=_PENDING_WORKER)
    other = _PENDING_WORKER | {
        'attempt_id': 'ATTEMPT-SECOND',
        'worker_id': 'worker-second',
    }
    update = _pending_msg('PROGRESS', 76, material, actor=other)
    command = _pending_msg('CONTINUE', 77, material)
    decision = _pending_decide(material, update, command)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_direct_command_does_not_launder_retargeted_coo_quiet_branch():
    material = _pending_msg('RESULT', 78, actor=_PENDING_COO)
    update = _pending_msg('PROGRESS', 79, material, actor=_PENDING_COO)
    update['applies_to'] = {
        'kind': 'repository',
        'repository': _PENDING_REPO,
        'head_sha': 'f' * 40,
        'pr': _PENDING_REPO + '#4',
    }
    update['fingerprint'] = semantic_fingerprint(update)
    command = _pending_msg('CONTINUE', 80, material)
    decision = _pending_decide(material, update, command)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_exact_worker_quiet_chain_preserves_original_pending_identity():
    material = _pending_msg('RESULT', 81, actor=_PENDING_WORKER)
    first = _pending_msg('ACK', 82, material, actor=_PENDING_WORKER)
    second = _pending_msg('PROGRESS', 83, first, actor=_PENDING_WORKER)
    assert _pending_decide(material, first, second) == _pending_decide(material)


@pytest.mark.parametrize('request_kind,reply', [('RESULT', 'CONTINUE'), ('BLOCKED', 'CONTINUE'), ('DECISION_REQUEST', 'RULING'), ('RESULT', 'STOP'), ('RESULT', 'AMENDMENT_AVAILABLE')])
def test_public_direct_responses_keep_their_existing_shape(request_kind, reply):
    first = _pending_msg(request_kind, 1)
    command = _pending_msg(reply, 2, first)
    result = _pending_decide(first, command)
    assert result.action is (TurnAction.WAKE_COO_TERMINAL if reply == 'STOP' else TurnAction.WAKE_COO)
    assert result.attention.message_key == command['message_key']

def test_public_full_decision_cycle_is_order_independent_and_terminal():
    question = _pending_msg('DECISION_REQUEST', 1)
    ruling = _pending_msg('RULING', 2, question)
    progress = _pending_msg('PROGRESS', 3, ruling)
    result = _pending_msg('RESULT', 4, progress)
    assert _pending_decide(question, ruling, progress).action is TurnAction.NO_ACTION
    reference = _pending_decide(question, ruling, progress, result)
    assert reference.attention.message_key == result['message_key']
    for order in itertools.permutations((question, ruling, progress, result)):
        assert _pending_decide(*order) == reference
    stop = _pending_msg('STOP', 5, result)
    receipt = _pending_msg('ACK', 6, stop)
    assert _pending_decide(question, ruling, progress, result, stop).action is TurnAction.WAKE_COO_TERMINAL
    assert _pending_decide(question, ruling, progress, result, stop, receipt).action is TurnAction.TERMINAL

def test_public_linear_quiet_leaf_preserves_successor_validation_boundary():
    # Source reconciliation validates the direct successor separately.  A
    # later quiet contributor leaf must preserve the legacy leaf result rather
    # than collapsing SOURCE_SUCCESSOR_REFUSED into SOURCE_SEMANTICS_REFUSED.
    result = _pending_msg('RESULT', 1)
    invalid_ruling = _pending_msg('RULING', 2, result)
    progress = _pending_msg('PROGRESS', 3, invalid_ruling)
    decision = _pending_decide(result, invalid_ruling, progress)
    assert decision.action is TurnAction.NO_ACTION
    assert decision.reason == 'DIALOGUE_PROGRESS'
    assert decision.refusal_code is None


@pytest.mark.parametrize('reply', ['RULING', 'CONTINUE', 'STOP', 'AMENDMENT_AVAILABLE'])
def test_public_quiet_link_never_becomes_false_consumable_parent_reply(reply):
    first = _pending_msg('DECISION_REQUEST' if reply == 'RULING' else 'RESULT', 1)
    update = _pending_msg('PROGRESS', 2, first)
    command = _pending_msg(reply, 3, update)
    assert _pending_decide(first, update, command).refusal_code == 'REPLY_LINEAGE_INVALID'

def test_public_invalid_stop_cannot_be_laundered_by_terminal_ack():
    first = _pending_msg('RESULT', 1)
    quiet = _pending_msg('PROGRESS', 2, first)
    invalid_stop = _pending_msg('STOP', 3, quiet)
    receipt = _pending_msg('ACK', 4, invalid_stop)
    decision = _pending_decide(first, quiet, invalid_stop, receipt)
    assert decision.action is TurnAction.REFUSE
    assert decision.refusal_code == 'REPLY_LINEAGE_INVALID'


@pytest.mark.parametrize('tail', ['ACK', 'PROGRESS', 'RESULT'])
def test_public_terminal_history_does_not_reopen(tail):
    first = _pending_msg('RESULT', 1)
    stop = _pending_msg('STOP', 2, first)
    receipt = _pending_msg('ACK', 3, stop)
    extra = _pending_msg(tail, 4, receipt)
    assert _pending_decide(first, stop, receipt, extra).refusal_code == 'REPLY_LINEAGE_INVALID'

def test_public_pending_routing_stays_unbound_without_fallback():
    first = _pending_msg('RESULT', 1)
    update = _pending_msg('PROGRESS', 2, first)
    result = _pending_decide(first, update, routing=_pending_facts(ceo=False))
    assert result.action is TurnAction.NO_ACTION
    assert result.refusal_code == 'DIALOGUE_WAKE_TARGET_UNBOUND'
    assert result.attention is None

@pytest.mark.parametrize('mutation,code', [(lambda x: x.pop('summary'), 'MESSAGE_INVALID'), (lambda x: x.__setitem__('fingerprint', '0' * 64), 'FINGERPRINT_MISMATCH'), (lambda x: x.__setitem__('requires_response', 1), 'MESSAGE_INVALID')])
def test_public_validation_still_refuses_before_semantic_fold(mutation, code):
    first = _pending_msg('RESULT', 1)
    mutation(first)
    assert _pending_decide(first).refusal_code == code

def test_public_parent_and_binding_validation_are_retained():
    p = _pending_parent()
    old = _pending_facts(p)
    p['operation_key'] = 'pending-obligation-another-operation'
    p['fingerprint'] = semantic_fingerprint(p)
    assert _pending_decide(_pending_msg('RESULT', 1), p=p, routing=old).refusal_code == 'DIALOGUE_BINDING_MISMATCH'
    p['fingerprint'] = '0' * 64
    assert _pending_decide(_pending_msg('RESULT', 1), p=p).action is TurnAction.REFUSE

def test_public_disabled_and_empty_parent_controls():
    assert _pending_decide().action is TurnAction.WAKE_COO
    p = _pending_parent()
    p['watch_mode'] = None
    p['fingerprint'] = semantic_fingerprint(p)
    assert _pending_decide(p=p).reason == 'WATCH_DISABLED'

def test_public_exact_replay_ignores_transport_timestamp_without_new_attention():
    first = _pending_msg('RESULT', 1)
    update = _pending_msg('PROGRESS', 2, first)
    replay = copy.deepcopy(first)
    replay['created_at'] = '2026-09-07T00:02:00Z'
    assert _pending_decide(first, update, replay) == _pending_decide(first)

def test_public_wrong_selected_option_is_not_valid_ruling():
    request = _pending_msg('DECISION_REQUEST', 1)
    reply = _pending_msg('RULING', 2, request, selected_option='opt-other')
    assert _pending_decide(request, reply).refusal_code == 'REPLY_LINEAGE_INVALID'

def test_public_external_blocker_is_not_lowered_by_progress():
    blocked = _pending_msg('BLOCKED', 1, needed_from='external')
    update = _pending_msg('PROGRESS', 2, blocked)
    command = _pending_msg('CONTINUE', 3, update)
    assert _pending_decide(blocked, update, command).refusal_code == 'REPLY_LINEAGE_INVALID'

def test_public_different_attempt_can_report_when_no_material_return_is_pending():
    progress = _pending_msg('PROGRESS', 1, actor=_PENDING_WORKER)
    other = _PENDING_WORKER | {'attempt_id': 'ATTEMPT-SECOND', 'worker_id': 'worker-second'}
    result = _pending_msg('RESULT', 2, progress, actor=other)
    assert _pending_decide(progress, result).attention.message_key == result['message_key']

def test_public_second_unanswered_material_return_is_visible_refusal_not_replacement():
    first = _pending_msg('DECISION_REQUEST', 1)
    later = _pending_msg('RESULT', 2, first)
    assert _pending_decide(first, later).refusal_code == 'REPLY_LINEAGE_INVALID'

def test_public_worker_receipt_never_substitutes_for_terminal_coo_ack():
    first = _pending_msg('RESULT', 1)
    stop = _pending_msg('STOP', 2, first)
    worker_ack = _pending_msg('ACK', 3, stop, actor=_PENDING_WORKER)
    assert _pending_decide(first, stop, worker_ack).refusal_code == 'REPLY_LINEAGE_INVALID'

def test_public_continue_never_replaces_a_direct_question_ruling():
    request_message = _pending_msg('DECISION_REQUEST', 1)
    command = _pending_msg('CONTINUE', 2, request_message)
    assert _pending_decide(request_message, command).refusal_code == 'REPLY_LINEAGE_INVALID'

@pytest.mark.parametrize('needed', ['chairman', 'external'])
def test_public_direct_external_blocker_is_not_a_sol_continuation(needed):
    first = _pending_msg('BLOCKED', 1, needed_from=needed)
    command = _pending_msg('CONTINUE', 2, first)
    assert _pending_decide(first, command).refusal_code == 'REPLY_LINEAGE_INVALID'

def test_public_changed_semantic_replay_conflicts_without_losing_original():
    first = _pending_msg('RESULT', 1)
    changed = _pending_msg('RESULT', 1, result='Different content with the same key.')
    assert _pending_decide(first, changed).refusal_code == 'MESSAGE_KEY_CONFLICT'

# Direct-disposition after quiet-annotation regression extension.
@pytest.mark.parametrize('quiet', ['ACK', 'PROGRESS'])
def test_public_direct_ruling_after_quiet_annotation_is_actionable(quiet):
    request = _pending_msg('DECISION_REQUEST', 101)
    update = _pending_msg(quiet, 102, request)
    ruling = _pending_msg('RULING', 103, request)
    decision = _pending_decide(request, update, ruling)
    assert decision.action is TurnAction.WAKE_COO
    assert decision.attention.message_key == ruling['message_key']


def test_public_multiple_quiet_annotations_can_precede_direct_ruling():
    request = _pending_msg('DECISION_REQUEST', 111)
    first = _pending_msg('ACK', 112, request)
    second = _pending_msg('PROGRESS', 113, first)
    ruling = _pending_msg('RULING', 114, request)
    reference = _pending_decide(request, first, second, ruling)
    assert reference.action is TurnAction.WAKE_COO
    assert reference.attention.message_key == ruling['message_key']
    for order in itertools.permutations((request, first, second, ruling)):
        assert _pending_decide(*order) == reference


@pytest.mark.parametrize('request_kind,command_kind', [
    ('RESULT', 'CONTINUE'),
    ('RESULT', 'STOP'),
    ('RESULT', 'AMENDMENT_AVAILABLE'),
    ('BLOCKED', 'CONTINUE'),
])
def test_public_direct_command_after_quiet_annotation_preserves_attention(
    request_kind, command_kind
):
    request = _pending_msg(request_kind, 121)
    update = _pending_msg('PROGRESS', 122, request)
    command = _pending_msg(command_kind, 123, request)
    decision = _pending_decide(request, update, command)
    expected = (
        TurnAction.WAKE_COO_TERMINAL
        if command_kind == 'STOP'
        else TurnAction.WAKE_COO
    )
    assert decision.action is expected
    assert decision.attention.message_key == command['message_key']


def test_public_direct_command_cycle_advances_after_quiet_side_branch():
    request = _pending_msg('DECISION_REQUEST', 131)
    update = _pending_msg('PROGRESS', 132, request)
    ruling = _pending_msg('RULING', 133, request)
    acknowledged = _pending_msg('ACK', 134, ruling)
    result = _pending_msg('RESULT', 135, acknowledged)
    decision = _pending_decide(request, update, ruling, acknowledged, result)
    assert decision.action is TurnAction.WAKE_CEO
    assert decision.attention.message_key == result['message_key']


def test_public_two_parent_commands_remain_a_fork_after_quiet_annotation():
    request = _pending_msg('DECISION_REQUEST', 141)
    update = _pending_msg('PROGRESS', 142, request)
    ruling = _pending_msg('RULING', 143, request)
    stop = _pending_msg('STOP', 144, request)
    assert _pending_decide(request, update, ruling, stop).refusal_code == 'DIALOGUE_FORKED'


def test_public_two_quiet_side_branches_remain_a_fork():
    request = _pending_msg('DECISION_REQUEST', 151)
    first = _pending_msg('ACK', 152, request)
    second = _pending_msg('PROGRESS', 153, request)
    ruling = _pending_msg('RULING', 154, request)
    assert _pending_decide(request, first, second, ruling).refusal_code == 'DIALOGUE_FORKED'


def test_public_material_side_branch_is_not_downgraded_to_annotation():
    request = _pending_msg('DECISION_REQUEST', 161)
    result = _pending_msg('RESULT', 162, request)
    ruling = _pending_msg('RULING', 163, request)
    assert _pending_decide(request, result, ruling).refusal_code == 'DIALOGUE_FORKED'


def test_public_wrong_direct_ruling_remains_invalid_after_quiet_annotation():
    request = _pending_msg('DECISION_REQUEST', 171)
    update = _pending_msg('PROGRESS', 172, request)
    ruling = _pending_msg('RULING', 173, request, selected_option='opt-other')
    assert _pending_decide(request, update, ruling).refusal_code == 'REPLY_LINEAGE_INVALID'


def test_public_external_blocker_is_not_lowered_by_direct_continue_after_quiet():
    request = _pending_msg('BLOCKED', 181, needed_from='external')
    update = _pending_msg('PROGRESS', 182, request)
    continuation = _pending_msg('CONTINUE', 183, request)
    assert _pending_decide(request, update, continuation).refusal_code == 'REPLY_LINEAGE_INVALID'
