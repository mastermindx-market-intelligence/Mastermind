"""Adapter projection joins exact native evidence without consuming an answer."""
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest

from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.operator_harness_contract import (
    CapabilityIdentity, ObservedCapabilityIdentity, TurnRef,
)
from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_SERVER_IDENTITY, COMPANY_CONSULTATION_SERVER_VERSION,
    COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
)
from tests.test_native_company_receipt import (
    SERVER, THREAD, TURN, SENTINEL_ANSWER, SENTINEL_EVIDENCE,
    make_params, make_item, make_data, make_envelope, result_for,
)


def _subject():
    fields = dict(kind="mcp_server", name=SERVER,
        mcp_server_identity=COMPANY_CONSULTATION_SERVER_IDENTITY,
        mcp_server_version=COMPANY_CONSULTATION_SERVER_VERSION,
        tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        mcp_auth_status="unsupported")
    required = CapabilityIdentity(**fields, harness_binary_digest="a" * 64)
    observed = ObservedCapabilityIdentity(**fields)
    state = SimpleNamespace(
        requested=SimpleNamespace(capabilities=SimpleNamespace(required=(required,))),
        attestation=SimpleNamespace(capabilities=(observed,), effective_mcp=(SERVER,)),
        turn_subordinates={}, turns={"logical-turn": TURN}, visible_turns=set(),
        provider_session_id=THREAD, events=[],
    )
    adapter = object.__new__(CodexOperatorAdapter)
    adapter.native_helper_grant = None
    adapter.skill_canary_binding = None
    turn = TurnRef("logical-turn", "epoch-1", "generation-1", "attempt-1")
    return adapter, state, turn


def _receipts(state):
    return [event.payload_redacted["company_read_receipt"] for event in state.events
            if "company_read_receipt" in event.payload_redacted]


def test_adapter_attested_exact_parent_read_is_redacted_and_turn_bound():
    adapter, state, turn = _subject()
    params = make_params(item=make_item(result=result_for(make_envelope(data=make_data(
        answer={"text": SENTINEL_ANSWER, "evidence_refs": [SENTINEL_EVIDENCE]},
    )))))
    adapter._ingest_turn_notifications(state, turn, [
        {"method": "item/completed", "params": params},
        {"method": "turn/completed", "params": {"threadId": THREAD, "turn": {"id": TURN}}},
    ])
    assert len(_receipts(state)) == 1
    assert state.events[0].turn_id == turn.turn_id
    assert state.events[1].kind == "turn/completed"
    blob = json.dumps(state.events[0].payload_redacted)
    assert SENTINEL_ANSWER not in blob and SENTINEL_EVIDENCE not in blob


@pytest.mark.parametrize("fault", [
    "missing-request", "duplicate-request", "missing-observation", "duplicate-observation",
    "not-effective", "schema", "identity", "version", "auth", "wrong-native-turn",
    "unfinished-item", "failed-item",
])
def test_adapter_no_receipt_for_unattested_or_uncompleted_read(fault):
    adapter, state, turn = _subject()
    params = make_params()
    required = state.requested.capabilities
    attestation = state.attestation
    if fault == "missing-request":
        required.required = ()
    elif fault == "duplicate-request":
        required.required *= 2
    elif fault == "missing-observation":
        attestation.capabilities = ()
    elif fault == "duplicate-observation":
        attestation.capabilities *= 2
    elif fault == "not-effective":
        attestation.effective_mcp = ()
    elif fault in {"schema", "identity", "version", "auth"}:
        key = {"schema": "tool_schema_digest", "identity": "mcp_server_identity",
               "version": "mcp_server_version", "auth": "mcp_auth_status"}[fault]
        attestation.capabilities = (replace(attestation.capabilities[0], **{key: "wrong"}),)
    elif fault == "wrong-native-turn":
        params["turnId"] = "different-turn"
    else:
        params["item"]["status"] = "inProgress" if fault == "unfinished-item" else "failed"
    adapter._ingest_turn_notifications(state, turn, [{"method": "item/completed", "params": params}])
    assert _receipts(state) == []


@pytest.mark.parametrize("mode", ["same-batch", "later-batch", "generation-only", "item-started"])
def test_adapter_closed_or_unrelated_notifications_never_gain_consumption_evidence(mode):
    adapter, state, turn = _subject()
    completed = {"method": "turn/completed", "params": {"threadId": THREAD, "turn": {"id": TURN}}}
    item = {"method": "item/completed", "params": make_params()}
    if mode == "same-batch":
        adapter._ingest_turn_notifications(state, turn, [completed, item])
    elif mode == "later-batch":
        adapter._ingest_turn_notifications(state, turn, [completed])
        adapter._ingest_turn_notifications(state, turn, [item])
    elif mode == "generation-only":
        adapter._ingest_turn_notifications(state, turn, [item], generation_only=True)
    else:
        adapter._ingest_turn_notifications(state, turn, [{**item, "method": "item/started"}])
    assert _receipts(state) == []
