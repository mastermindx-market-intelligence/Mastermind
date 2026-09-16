from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib

import pytest

import integrations.mastermind_company_mcp.consultation as consultation_contract

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_runtime import AttemptStatus, WorkerStatus
from control_plane.executive_agent_capabilities import (
    CompanyConsultationGrantProfile,
    build_company_consultation_grant_profile,
)
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.operator_harness_contract import runtime_binding_id_for
from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_CAPABILITY,
    COMPANY_CONSULTATION_ERROR_CODES,
    COMPANY_CONSULTATION_MAX_RESPONSE_BYTES,
    COMPANY_CONSULTATION_RESULT_SCHEMA,
    COMPANY_CONSULTATION_SERVER_IDENTITY,
    COMPANY_CONSULTATION_SERVER_NAME,
    COMPANY_CONSULTATION_SERVER_VERSION,
    COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
    COMPANY_CONSULTATION_TOOL_SPECS,
    CompanyConsultationGateway,
    CompanyConsultationToolError,
    _result,
    canonical_company_consultation_json,
    validate_company_consultation_tool_arguments,
)
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import (
    CompanyConsultationPeerResolver,
    ConsultationPeer,
    ConsultationPeerRefused,
    peer_from_company_dialogue,
)
from control_plane.session_targets import RuntimeBinding
from integrations.slack_agent_dialogue.contract_v2 import (
    PARENT_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    build_parent_v2,
)
from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
)
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    CurrentWorkerDialogueSnapshot,
    WorkerDialogueCaller,
)
from common.agent_dialogue_consultation_contract import (
    CONSULTATION_SCHEMA,
    CONSULTATION_V2_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
    validate_consultation,
)
from integrations.slack_agent_dialogue.contract import DialogueContractError
from tests.test_agent_dialogue_consultation_contract import raw_consultation
from tests.test_runtime_binding_projection import _admitted_runtime, _target


class _Dispatcher:
    def __init__(self, response=None) -> None:
        self.response = response or {"ok": True, "result": {}}
        self.calls = []

    async def __call__(self, operation: str, request: dict) -> dict:
        self.calls.append((operation, copy.deepcopy(request)))
        return copy.deepcopy(self.response)


def _peer(peer_ref: str = "peer-7bdf4a6f9a664bbcf1a93d67a41ba51d") -> ConsultationPeer:
    return ConsultationPeer(
        peer_ref=peer_ref,
        display_name="Peer 7bdf",
        program_ref="JOB-100/agent-fabric-end-to-end-fable-integration",
        actor_ref={
            "kind": "worker_attempt",
            "job_id": "JOB-200",
            "attempt_id": "ATT-200",
            "worker_id": "codex-att-200",
        },
        binding={
            "binding_id": "bind-7bdf4a6f9a664bbcf1a93d67a41ba51d",
            "binding_generation": 1,
            "reasoning_surface": "codex",
        },
    )


def _grok_peer() -> ConsultationPeer:
    return dataclasses.replace(
        _peer("peer-9bdf4a6f9a664bbcf1a93d67a41ba51d"),
        display_name="Grok Bot",
        actor_ref={
            "kind": "worker_attempt",
            "job_id": "JOB-209",
            "attempt_id": "ATT-209",
            "worker_id": "grok-bot",
        },
        binding={
            "binding_id": runtime_binding_id_for("ATT-209", "EPOCH-0209"),
            "binding_generation": 1,
            "reasoning_surface": "grok-bot",
        },
    )


def _artifact() -> dict:
    return {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "path": "integrations/mastermind_company_mcp/consultation.py",
        "commit": "1" * 40,
        "content_sha256": "2" * 64,
    }


def _delegation_identity() -> ExecutiveDelegationIdentity:
    return ExecutiveDelegationIdentity(
        job_id="JOB-200",
        root_job_id="JOB-100",
        operation_key="exec-job-200",
        session_ref="asd-session-exec-job-200",
    )


def _dialogue_parent() -> dict:
    identity = _delegation_identity()
    return build_parent_v2({
        "schema": PARENT_SCHEMA_V2,
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "c" * 40,
            "path": "research/operator-commission.md",
            "content_sha256": "d" * 64,
        },
        "session_ref": identity.session_ref,
        "operation_key": identity.operation_key,
        "watch_mode": TURN_WATCH_MODE_V1,
        "allowed_sol_user_ids": ["U0BRETDUAS2"],
        "created_at": "2026-08-31T22:00:00Z",
    })


def _runtime_binding() -> RuntimeBinding:
    return RuntimeBinding(
        session_alias="EXECUTIVE-COO-A",
        binding_id="bind-worker-runtime-0001",
        binding_generation=3,
        native_handle="provider-private",
        account_label="account-private",
        reasoning_surface="codex",
    )


def _current_snapshot() -> CurrentWorkerDialogueSnapshot:
    return CurrentWorkerDialogueSnapshot(
        root_job_id="JOB-100",
        job_id="JOB-200",
        attempt_id="ATT-0123456789abcdef0123456789abcdef",
        worker_id="codex-worker-01",
        attempt_status=AttemptStatus.RUNNING,
        worker_status=WorkerStatus.BUSY,
        execution_profile_id="operator.appserver.readonly.company-dialogue.v1",
        execution_profile_digest="a" * 64,
        capability_policy_digest="b" * 64,
        runtime_binding=_runtime_binding(),
        parent_fingerprint=_dialogue_parent()["fingerprint"],
        company_dialogue_server_identity=SERVER_IDENTITY,
        company_dialogue_server_version=SERVER_VERSION,
        company_dialogue_tool_schema_digest=TOOL_SCHEMA_DIGEST,
        company_dialogue_attested=True,
    )


def _caller() -> WorkerDialogueCaller:
    return WorkerDialogueCaller(
        attempt_id="ATT-0123456789abcdef0123456789abcdef",
        worker_id="codex-worker-01",
        execution_profile_id="operator.appserver.readonly.company-dialogue.v1",
        execution_profile_digest="a" * 64,
        capability_policy_digest="b" * 64,
        runtime_binding=_runtime_binding(),
    )


def _resolver(peers=None) -> CompanyConsultationPeerResolver:
    return CompanyConsultationPeerResolver(peers or [_peer()])


def _gateway(peers=None, *, digest=None, dispatcher=None) -> tuple[CompanyConsultationGateway, _Dispatcher]:
    sink = dispatcher or _Dispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=_resolver(peers),
        dispatcher=sink,
        observed_tool_schema_digest=digest or COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-14T00:00:00Z",
    )
    return gateway, sink


def _run(coroutine):
    return asyncio.run(coroutine)


def test_consultation_mcp_generation_is_exact_closed_and_literal_digest() -> None:
    assert COMPANY_CONSULTATION_SERVER_NAME == "mastermind-company-consultation"
    assert COMPANY_CONSULTATION_SERVER_IDENTITY == "mastermind-company-consultation-mcp"
    assert COMPANY_CONSULTATION_SERVER_VERSION == "1.0.0"
    assert COMPANY_CONSULTATION_CAPABILITY == "mastermind.company_consultation_mcp.v1"
    assert [spec.name for spec in COMPANY_CONSULTATION_TOOL_SPECS] == [
        "company.peers",
        "company.consult",
        "company.reply",
        "company.consultation",
    ]
    assert len(COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST) == 64
    for spec in COMPANY_CONSULTATION_TOOL_SPECS:
        assert spec.input_schema["additionalProperties"] is False


def test_company_peers_returns_only_opaque_refs_and_display_facts() -> None:
    gateway, sink = _gateway()

    response = _run(gateway.call("company.peers", {}))

    assert response["ok"] is True
    assert response["data"]["peers"] == [
        {"peer_ref": _peer().peer_ref, "display_name": "Peer 7bdf"}
    ]
    assert sink.calls == []


def test_company_peers_returns_two_same_program_public_projections() -> None:
    second = ConsultationPeer(
        peer_ref="peer-8bdf4a6f9a664bbcf1a93d67a41ba51d",
        display_name="Peer 8bdf",
        program_ref="JOB-100/agent-fabric-end-to-end-fable-integration",
        actor_ref={
            "kind": "worker_attempt",
            "job_id": "JOB-201",
            "attempt_id": "ATT-201",
            "worker_id": "codex-att-201",
        },
        binding={
            "binding_id": "bind-8bdf4a6f9a664bbcf1a93d67a41ba51d",
            "binding_generation": 1,
            "reasoning_surface": "codex",
        },
    )
    gateway, sink = _gateway([_peer(), second])

    response = _run(gateway.call("company.peers", {}))

    assert response["ok"] is True
    assert response["error"] is None
    assert response["data"]["peers"] == [
        {"peer_ref": _peer().peer_ref, "display_name": "Peer 7bdf"},
        {"peer_ref": second.peer_ref, "display_name": "Peer 8bdf"},
    ]
    assert sink.calls == []


def test_consult_malformed_to_is_invalid_request() -> None:
    gateway, sink = _gateway()

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": "codex-att-200",
                "question": "What fields are forbidden?",
                "evidence_refs": [],
                "artifact_revisions": [_artifact()],
            },
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"
    assert sink.calls == []
    with pytest.raises(CompanyConsultationToolError) as exc_info:
        validate_company_consultation_tool_arguments(
            "company.consult",
            {
                "to": "Peer 7bdf",
                "question": "?",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    assert exc_info.value.code == "INVALID_REQUEST"


def test_alias_ambiguous_puts_closed_public_facts_in_data() -> None:
    second = dataclasses.replace(
        _peer("peer-8bdf4a6f9a664bbcf1a93d67a41ba51d"),
        display_name="Peer 7bdf",
        actor_ref={
            "kind": "worker_attempt",
            "job_id": "JOB-201",
            "attempt_id": "ATT-201",
            "worker_id": "codex-att-201",
        },
    )
    resolver = CompanyConsultationPeerResolver([_peer(), second])

    with pytest.raises(ConsultationPeerRefused) as exc_info:
        resolver.resolve("Peer 7bdf", program_ref=_peer().program_ref)

    assert exc_info.value.code == "AMBIGUOUS"
    assert exc_info.value.data == {
        "peers": [
            {"peer_ref": _peer().peer_ref, "display_name": "Peer 7bdf"},
            {"peer_ref": second.peer_ref, "display_name": "Peer 7bdf"},
        ]
    }

    class _AmbiguousResolver:
        peers = [_peer(), second]

        def resolve(self, alias: str, *, program_ref: str):
            raise ConsultationPeerRefused(
                "AMBIGUOUS",
                {
                    "peers": [
                        {"peer_ref": _peer().peer_ref, "display_name": "Peer 7bdf"},
                        {"peer_ref": second.peer_ref, "display_name": "Peer 7bdf"},
                    ]
                },
            )

    sink = _Dispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=_AmbiguousResolver(),  # type: ignore[arg-type]
        dispatcher=sink,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-14T00:00:00Z",
    )
    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "?",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "AMBIGUOUS"
    assert response["data"] == {
        "peers": [
            {"peer_ref": _peer().peer_ref, "display_name": "Peer 7bdf"},
            {"peer_ref": second.peer_ref, "display_name": "Peer 7bdf"},
        ]
    }
    assert sink.calls == []


def _synthetic_closed_facts(count: int) -> list[dict[str, str]]:
    return [
        {"peer_ref": f"peer-{index:032x}", "display_name": f"Peer {index:04x}"}
        for index in range(count)
    ]


def test_oversized_ambiguous_error_encodes_within_response_cap() -> None:
    facts = _synthetic_closed_facts(1500)
    uncapped = {
        "schema": COMPANY_CONSULTATION_RESULT_SCHEMA,
        "tool": "company.consult",
        "ok": False,
        "server_identity": COMPANY_CONSULTATION_SERVER_IDENTITY,
        "server_version": COMPANY_CONSULTATION_SERVER_VERSION,
        "data": {"peers": facts},
        "error": {"code": "AMBIGUOUS", "message": "AMBIGUOUS"},
    }
    assert (
        len(canonical_company_consultation_json(uncapped))
        > COMPANY_CONSULTATION_MAX_RESPONSE_BYTES
    )

    class _OversizedAmbiguousResolver:
        peers = []

        def resolve(self, alias: str, *, program_ref: str):
            raise ConsultationPeerRefused("AMBIGUOUS", {"peers": facts})

    sink = _Dispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=_OversizedAmbiguousResolver(),  # type: ignore[arg-type]
        dispatcher=sink,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-14T00:00:00Z",
    )
    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "?",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    )

    encoded = canonical_company_consultation_json(response)
    assert len(encoded) <= COMPANY_CONSULTATION_MAX_RESPONSE_BYTES
    assert response["ok"] is False
    assert response["error"]["code"] in COMPANY_CONSULTATION_ERROR_CODES
    assert sink.calls == []


def test_small_ambiguous_still_carries_closed_facts_in_data() -> None:
    second = dataclasses.replace(
        _peer("peer-8bdf4a6f9a664bbcf1a93d67a41ba51d"),
        display_name="Peer 7bdf",
        actor_ref={
            "kind": "worker_attempt",
            "job_id": "JOB-201",
            "attempt_id": "ATT-201",
            "worker_id": "codex-att-201",
        },
    )
    closed = {
        "peers": [
            {"peer_ref": _peer().peer_ref, "display_name": "Peer 7bdf"},
            {"peer_ref": second.peer_ref, "display_name": "Peer 7bdf"},
        ]
    }

    class _SmallAmbiguousResolver:
        peers = [_peer(), second]

        def resolve(self, alias: str, *, program_ref: str):
            raise ConsultationPeerRefused("AMBIGUOUS", closed)

    sink = _Dispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=_SmallAmbiguousResolver(),  # type: ignore[arg-type]
        dispatcher=sink,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-14T00:00:00Z",
    )
    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "?",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    )

    encoded = canonical_company_consultation_json(response)
    assert len(encoded) <= COMPANY_CONSULTATION_MAX_RESPONSE_BYTES
    assert response["ok"] is False
    assert response["error"]["code"] == "AMBIGUOUS"
    assert response["data"] == closed
    assert sink.calls == []


def test_result_envelope_at_response_byte_boundary_still_passes() -> None:
    overhead = len(
        canonical_company_consultation_json(
            {
                "schema": COMPANY_CONSULTATION_RESULT_SCHEMA,
                "tool": "company.peers",
                "ok": True,
                "server_identity": COMPANY_CONSULTATION_SERVER_IDENTITY,
                "server_version": COMPANY_CONSULTATION_SERVER_VERSION,
                "data": {"pad": ""},
                "error": None,
            }
        )
    )
    pad = COMPANY_CONSULTATION_MAX_RESPONSE_BYTES - overhead
    envelope = _result("company.peers", {"pad": "x" * pad})
    encoded = canonical_company_consultation_json(envelope)
    assert len(encoded) == COMPANY_CONSULTATION_MAX_RESPONSE_BYTES
    assert envelope["ok"] is True
    assert envelope["error"] is None
    assert envelope["data"] == {"pad": "x" * pad}


def test_company_consultation_mcp_server_advertises_only_four_tools() -> None:
    pytest.importorskip("mcp")
    from mcp.server.lowlevel import NotificationOptions

    from integrations.mastermind_company_mcp.server import (
        build_company_consultation_mcp_server,
        build_company_consultation_tools,
    )

    tools = build_company_consultation_tools()
    assert [tool.name for tool in tools] == [
        "company.peers", "company.consult", "company.reply", "company.consultation"
    ]
    server = build_company_consultation_mcp_server(_gateway()[0])
    capabilities = server.get_capabilities(
        notification_options=NotificationOptions(), experimental_capabilities={}
    )
    assert capabilities.tools is not None
    assert capabilities.resources is None


def test_company_consult_valid_input_reaches_hermetic_dispatcher_once() -> None:
    gateway, sink = _gateway()

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "What fields are forbidden?",
                "evidence_refs": [],
                    "artifact_revisions": [_artifact()],
            },
        )
    )

    assert response["ok"] is True
    assert len(sink.calls) == 1
    assert sink.calls[0][1]["peer"]["peer_ref"] == _peer().peer_ref
    assert sink.calls[0][1]["budget"] == {
        "max_answers": 1,
        "max_evidence_reads": 4,
        "max_forward_hops": 0,
        "max_payload_bytes": 32768,
    }


@pytest.mark.parametrize(
    ("peers", "arguments", "code"),
    [
        ([], {"to": "peer-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "question": "?", "evidence_refs": [], "artifact_revisions": []}, "UNAVAILABLE"),
        (
            [_peer(), _peer("peer-8bdf4a6f9a664bbcf1a93d67a41ba51d")],
            {"to": "Peer 7bdf", "question": "?", "evidence_refs": [], "artifact_revisions": []},
            "INVALID_REQUEST",
        ),
        (
            [
                dataclasses.replace(
                    _peer("peer-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
                    actor_ref={"kind": "executive_surface"},
                )
            ],
            {"to": "peer-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "question": "?", "evidence_refs": [], "artifact_revisions": []},
            "BINDING_UNAVAILABLE",
        ),
        (
            [_peer()],
            {
                "to": _peer().peer_ref,
                "question": "?",
                "evidence_refs": [],
                "artifact_revisions": [_artifact()],
                "action": "push",
            },
            "INVALID_REQUEST",
        ),
        (
            [_peer()],
            {"to": _peer().peer_ref, "question": "x" * 32769, "evidence_refs": [], "artifact_revisions": [_artifact()]},
            "INVALID_REQUEST",
        ),
        (
            [_peer()],
            {"to": _peer().peer_ref, "question": "xoxb-not-a-real-token-shaped-value", "evidence_refs": [], "artifact_revisions": [_artifact()]},
            "INVALID_REQUEST",
        ),
    ],
)
def test_refusals_are_typed_and_have_zero_effect(peers, arguments, code) -> None:
    gateway, sink = _gateway(peers)

    response = _run(gateway.call("company.consult", arguments))

    assert response["error"]["code"] == code
    assert sink.calls == []


def test_schema_digest_mismatch_refuses_with_zero_effect() -> None:
    gateway, sink = _gateway(digest="0" * 64)

    response = _run(gateway.call("company.peers", {}))

    assert response["error"]["code"] == "CAPABILITY_NOT_ATTESTED"
    assert sink.calls == []


def test_peer_resolver_rejects_forged_and_cross_program_identity() -> None:
    peer = _peer()
    forged = ConsultationPeer(
        peer_ref=peer.peer_ref,
        display_name="Forged",
        program_ref="JOB-999/other-operation",
        actor_ref=peer.actor_ref,
        binding=peer.binding,
    )
    resolver = CompanyConsultationPeerResolver([forged])

    with pytest.raises(ConsultationPeerRefused) as unavailable:
        resolver.resolve(peer.peer_ref, program_ref=peer.program_ref)
    assert unavailable.value.code == "UNAVAILABLE"


def test_existing_company_dialogue_resolver_derives_only_public_peer_facts() -> None:
    from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
        BindingReason,
        BindingState,
    )

    resolution = peer_from_company_dialogue(
        peer_ref="peer-7bdf4a6f9a664bbcf1a93d67a41ba51d",
        display_name="Peer 7bdf",
        program_ref="JOB-100/agent-fabric-end-to-end-fable-integration",
        delegation_identity=_delegation_identity(),
        dialogue_parent=_dialogue_parent(),
        thread_ts="1787896128.625239",
        current=_current_snapshot(),
        actor=_caller(),
    )

    assert resolution.state is BindingState.RESOLVED
    assert resolution.reason is BindingReason.EXACT_CURRENT_WORKER
    assert resolution.peer.public_projection() == {
        "peer_ref": "peer-7bdf4a6f9a664bbcf1a93d67a41ba51d",
        "display_name": "Peer 7bdf",
    }


def test_real_runtime_binding_composes_through_peer_into_envelope_validator(tmp_path) -> None:
    runtime, _dispatch, sealed, epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path)
    runtime_binding = project_runtime_binding(
        runtime, sealed.attempt_id, _target()
    )
    current = dataclasses.replace(
        _current_snapshot(),
        attempt_id=sealed.attempt_id,
        runtime_binding=runtime_binding,
    )
    actor = dataclasses.replace(
        _caller(),
        attempt_id=sealed.attempt_id,
        runtime_binding=runtime_binding,
    )
    resolution = peer_from_company_dialogue(
        peer_ref="peer-7bdf4a6f9a664bbcf1a93d67a41ba51d",
        display_name="Peer 7bdf",
        program_ref="JOB-100/agent-fabric-end-to-end-fable-integration",
        delegation_identity=_delegation_identity(),
        dialogue_parent=_dialogue_parent(),
        thread_ts="1787896128.625239",
        current=current,
        actor=actor,
    )

    assert resolution.state.value == "RESOLVED"
    assert resolution.peer is not None
    assert resolution.peer.binding["binding_id"] == runtime_binding_id_for(
        sealed.attempt_id, epoch.session_epoch_id
    )
    assert resolution.peer.binding["binding_id"] == runtime_binding.binding_id

    envelope = raw_consultation()
    envelope["recipient_binding"] = resolution.peer.binding
    validated = validate_consultation(envelope)
    assert validated["recipient_binding"] == resolution.peer.binding
    assert validated["schema"] == "mastermind.agent_dialogue_consultation.v1"
    assert validated["response_budget"] == {
        "max_answers": 1,
        "max_evidence_reads": 2,
        "max_forward_hops": 0,
        "max_payload_bytes": 32768,
    }

    canonical_hex = runtime_binding.binding_id.removeprefix("bind-")
    for noncanonical in ("bind-" + "a" * 32, runtime_binding.binding_id + "0"):
        envelope["recipient_binding"] = {
            **resolution.peer.binding,
            "binding_id": noncanonical,
        }
        with pytest.raises(DialogueContractError):
            validate_consultation(envelope)
    assert canonical_hex


def test_stale_generation_or_forged_actor_refuses_before_dispatch() -> None:
    stale = dataclasses.replace(
        _peer(), binding={**_peer().binding, "binding_generation": 2}
    )
    sink = _Dispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=CompanyConsultationPeerResolver(
            [stale],
            expected_actor_ref=dict(_peer().actor_ref),
            expected_binding=dict(_peer().binding),
        ),
        dispatcher=sink,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-14T00:00:00Z",
    )
    response = _run(gateway.call("company.consult", {
        "to": stale.peer_ref,
        "question": "?",
        "evidence_refs": [],
        "artifact_revisions": [],
    }))

    assert response["error"]["code"] == "BINDING_UNAVAILABLE"
    assert sink.calls == []


def test_company_consultation_tool_validator_rejects_privileged_identity_fields() -> None:
    with pytest.raises(CompanyConsultationToolError) as exc_info:
        validate_company_consultation_tool_arguments(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "?",
                "evidence_refs": [],
                "artifact_revisions": [],
                "provider": "codex",
            },
        )
    assert exc_info.value.code == "INVALID_REQUEST"


def test_consultation_registry_profile_is_minimal_and_unarmed() -> None:
    profile = build_company_consultation_grant_profile(
        capability_id="mastermind-company-consultation-v1",
        profile_id="operator.appserver.readonly.company-consultation.v1",
        requester_actor_ref={
            "kind": "worker_attempt",
            "job_id": "JOB-200",
            "attempt_id": "ATT-100",
            "worker_id": "codex-att-100",
        },
        recipient_actor_ref=_peer().actor_ref,
        recipient_peer_ref=_peer().peer_ref,
        recipient_binding=_peer().binding,
        consultation_packet="consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        artifact_revisions=(),
    )

    assert isinstance(profile, CompanyConsultationGrantProfile)
    assert profile.peer_cardinality == 1
    assert profile.forwarding is False
    assert profile.broadcast is False
    assert profile.spawn is False
    assert profile.read_grant == {
        "consultation_packet": "consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        "artifact_revisions": [],
    }
    assert profile.reply_grant == {"max_appends": 1, "correlated": True}
    assert profile.forbidden_authority == (
        "write",
        "source",
        "credential",
        "pr",
        "push",
        "deploy",
        "admin",
    )
    assert len(profile.policy_digest) == 64


def test_grok_peer_derives_v3_without_widening_public_projection() -> None:
    peer = _grok_peer()
    resolved = CompanyConsultationPeerResolver([peer]).resolve(
        peer.peer_ref, program_ref=peer.program_ref
    )

    assert resolved.consultation_schema == GROK_CONSULTATION_SCHEMA
    assert resolved.public_projection() == {
        "peer_ref": peer.peer_ref,
        "display_name": "Grok Bot",
    }


def test_company_consult_derives_schema_from_trusted_peer_binding() -> None:
    codex_gateway, codex_sink = _gateway()
    codex_response = _run(
        codex_gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "Which schema is trusted?",
                "evidence_refs": [],
                "artifact_revisions": [_artifact()],
            },
        )
    )
    assert codex_response["ok"] is True
    assert codex_sink.calls[0][1]["consultation_schema"] == CONSULTATION_SCHEMA

    grok = _grok_peer()
    grok_gateway, grok_sink = _gateway([grok])
    grok_response = _run(
        grok_gateway.call(
            "company.consult",
            {
                "to": grok.peer_ref,
                "question": "Which schema is trusted?",
                "evidence_refs": [],
                "artifact_revisions": [_artifact()],
            },
        )
    )
    assert grok_response["ok"] is True
    assert grok_sink.calls[0][1]["consultation_schema"] == GROK_CONSULTATION_SCHEMA
    assert grok_sink.calls[0][1]["peer"] == grok.public_projection()


def test_company_peers_does_not_expose_consultation_schema() -> None:
    peer = _grok_peer()
    gateway, sink = _gateway([peer])

    response = _run(gateway.call("company.peers", {}))

    assert response["ok"] is True
    assert response["data"]["peers"] == [peer.public_projection()]
    assert "consultation_schema" not in response["data"]["peers"][0]
    assert sink.calls == []


def test_company_consult_refuses_caller_schema_override_before_dispatch() -> None:
    peer = _grok_peer()
    gateway, sink = _gateway([peer])

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": peer.peer_ref,
                "question": "Use this caller schema.",
                "evidence_refs": [],
                "artifact_revisions": [_artifact()],
                "consultation_schema": GROK_CONSULTATION_SCHEMA,
            },
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"
    assert sink.calls == []


def test_peer_resolver_refuses_unmapped_reasoning_surface() -> None:
    peer = dataclasses.replace(
        _grok_peer(),
        binding={**_grok_peer().binding, "reasoning_surface": "gemini"},
    )

    with pytest.raises(ConsultationPeerRefused) as exc_info:
        CompanyConsultationPeerResolver([peer]).resolve(
            peer.peer_ref, program_ref=peer.program_ref
        )

    assert exc_info.value.code == "BINDING_UNAVAILABLE"


def test_company_dialogue_grok_binding_derives_v3_without_public_widening() -> None:
    grok_binding = dataclasses.replace(
        _runtime_binding(),
        reasoning_surface="grok-bot",
    )
    current = dataclasses.replace(_current_snapshot(), runtime_binding=grok_binding)
    caller = dataclasses.replace(_caller(), runtime_binding=grok_binding)

    resolution = peer_from_company_dialogue(
        peer_ref="peer-9bdf4a6f9a664bbcf1a93d67a41ba51d",
        display_name="Grok Bot",
        program_ref="JOB-100/agent-fabric-end-to-end-fable-integration",
        delegation_identity=_delegation_identity(),
        dialogue_parent=_dialogue_parent(),
        thread_ts="1787896128.625239",
        current=current,
        actor=caller,
    )

    assert resolution.peer is not None
    assert resolution.peer.binding["reasoning_surface"] == "grok-bot"
    assert resolution.peer.consultation_schema == GROK_CONSULTATION_SCHEMA
    assert resolution.peer.public_projection() == {
        "peer_ref": "peer-9bdf4a6f9a664bbcf1a93d67a41ba51d",
        "display_name": "Grok Bot",
    }


def test_grok_peer_binding_composes_into_v3_contract() -> None:
    peer = _grok_peer()
    frame = raw_consultation(schema=GROK_CONSULTATION_SCHEMA)
    frame["recipient_actor_ref"] = dict(peer.actor_ref)
    frame["recipient_peer_ref"] = peer.peer_ref
    frame["recipient_binding"] = dict(peer.binding)

    validated = validate_consultation(frame)

    assert validated["schema"] == GROK_CONSULTATION_SCHEMA
    assert validated["recipient_binding"] == peer.binding


def test_company_consult_dispatch_request_has_own_closed_versioned_contract() -> None:
    builder = getattr(
        consultation_contract, "build_company_consult_dispatch_request", None
    )
    validator = getattr(
        consultation_contract, "validate_company_consult_dispatch_request", None
    )
    assert callable(builder), "company.consult needs a dedicated dispatch builder"
    assert callable(validator), "company.consult needs a dedicated dispatch validator"

    request = builder(
        peer=_peer().public_projection(),
        consultation_schema=CONSULTATION_SCHEMA,
        semantic={
            "to": _peer().peer_ref,
            "question": "What fields are frozen?",
            "evidence_refs": [],
            "artifact_revisions": [_artifact()],
        },
        valid_until="2026-09-14T00:00:00Z",
    )

    assert request == {
        "schema": "mastermind.company_consult_dispatch.v1",
        "operation": "consult",
        "consultation_schema": CONSULTATION_SCHEMA,
        "peer": _peer().public_projection(),
        "semantic": {
            "to": _peer().peer_ref,
            "question": "What fields are frozen?",
            "evidence_refs": [],
            "artifact_revisions": [_artifact()],
        },
        "budget": {
            "max_answers": 1,
            "max_evidence_reads": 4,
            "max_forward_hops": 0,
            "max_payload_bytes": 32768,
        },
        "valid_until": "2026-09-14T00:00:00Z",
    }
    assert validator(request) == request


def test_company_consult_gateway_emits_only_the_frozen_dispatch_contract() -> None:
    peer = _grok_peer()
    gateway, sink = _gateway([peer])

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": peer.peer_ref,
                "question": "Use the frozen dispatcher contract.",
                "evidence_refs": [],
                "artifact_revisions": [_artifact()],
            },
        )
    )

    assert response["ok"] is True
    assert len(sink.calls) == 1
    operation, request = sink.calls[0]
    assert operation == "company.consult"
    assert request["schema"] == consultation_contract.COMPANY_CONSULT_DISPATCH_SCHEMA
    assert set(request) == {
        "schema",
        "operation",
        "consultation_schema",
        "peer",
        "semantic",
        "budget",
        "valid_until",
    }
    assert consultation_contract.validate_company_consult_dispatch_request(request) == request


def test_company_consult_dispatch_schema_snapshot_is_frozen_and_separate() -> None:
    snapshot_fn = getattr(
        consultation_contract, "company_consult_dispatch_schema_snapshot", None
    )
    digest_fn = getattr(
        consultation_contract, "company_consult_dispatch_schema_digest", None
    )
    assert callable(snapshot_fn), "dispatch contract needs a frozen schema snapshot"
    assert callable(digest_fn), "dispatch contract needs a deterministic schema digest"

    expected = {
        "type": "object",
        "properties": {
            "schema": {
                "type": "string",
                "const": "mastermind.company_consult_dispatch.v1",
            },
            "operation": {"type": "string", "const": "consult"},
            "consultation_schema": {
                "type": "string",
                "enum": [CONSULTATION_SCHEMA, GROK_CONSULTATION_SCHEMA],
            },
            "peer": {
                "type": "object",
                "properties": {
                    "peer_ref": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 128,
                        "pattern": r"^peer-[0-9a-f]{32}$",
                    },
                    "display_name": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 128,
                    },
                },
                "required": ["peer_ref", "display_name"],
                "additionalProperties": False,
            },
            "semantic": next(
                spec.input_schema
                for spec in COMPANY_CONSULTATION_TOOL_SPECS
                if spec.name == "company.consult"
            ),
            "budget": {
                "type": "object",
                "properties": {
                    "max_answers": {"type": "integer", "const": 1},
                    "max_evidence_reads": {"type": "integer", "const": 4},
                    "max_forward_hops": {"type": "integer", "const": 0},
                    "max_payload_bytes": {"type": "integer", "const": 32768},
                },
                "required": [
                    "max_answers",
                    "max_evidence_reads",
                    "max_forward_hops",
                    "max_payload_bytes",
                ],
                "additionalProperties": False,
            },
            "valid_until": {
                "type": "string",
                "minLength": 20,
                "maxLength": 20,
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            },
        },
        "required": [
            "schema",
            "operation",
            "consultation_schema",
            "peer",
            "semantic",
            "budget",
            "valid_until",
        ],
        "additionalProperties": False,
    }
    snapshot = snapshot_fn()
    assert snapshot == expected
    expected_digest = hashlib.sha256(
        canonical_company_consultation_json(expected)
    ).hexdigest()
    assert digest_fn() == expected_digest
    assert consultation_contract.COMPANY_CONSULT_DISPATCH_SCHEMA_DIGEST == expected_digest
    assert consultation_contract.COMPANY_CONSULT_DISPATCH_SCHEMA_DIGEST == (
        "3efbf163cb5ee674182a82d8d23b1ce522888c634183c141909b2a793eb709b0"
    )
    assert COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST == (
        "f9463e714240c5ac347bb029788b88d5556ad9d77c69eabcec1b7038e210a722"
    )


def test_company_consult_dispatch_builder_freezes_nested_inputs() -> None:
    peer = _peer().public_projection()
    semantic = {
        "to": _peer().peer_ref,
        "question": "Freeze this request.",
        "evidence_refs": [
            "https://github.com/mastermindx-market-intelligence/Mastermind/pull/709"
        ],
        "artifact_revisions": [_artifact()],
    }
    request = consultation_contract.build_company_consult_dispatch_request(
        peer=peer,
        consultation_schema=CONSULTATION_SCHEMA,
        semantic=semantic,
        valid_until="2026-09-14T00:00:00Z",
    )

    peer["display_name"] = "Mutated"
    semantic["evidence_refs"].append(
        "https://github.com/mastermindx-market-intelligence/Mastermind/pull/681"
    )
    semantic["artifact_revisions"][0]["path"] = "mutated.py"

    assert request["peer"]["display_name"] == "Peer 7bdf"
    assert request["semantic"]["evidence_refs"] == [
        "https://github.com/mastermindx-market-intelligence/Mastermind/pull/709"
    ]
    assert request["semantic"]["artifact_revisions"][0]["path"] == (
        "integrations/mastermind_company_mcp/consultation.py"
    )


def test_company_consult_dispatch_refuses_impossible_utc_timestamp() -> None:
    with pytest.raises(CompanyConsultationToolError) as exc_info:
        consultation_contract.build_company_consult_dispatch_request(
            peer=_peer().public_projection(),
            consultation_schema=CONSULTATION_SCHEMA,
            semantic={
                "to": _peer().peer_ref,
                "question": "Reject impossible time.",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
            valid_until="2026-13-40T25:61:61Z",
        )

    assert exc_info.value.code == "INVALID_REQUEST"


def test_company_consult_pre_dispatch_contract_failure_is_definite_internal_error() -> None:
    sink = _Dispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=_resolver(),
        dispatcher=sink,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-13-40T25:61:61Z",
    )

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "Do not claim an unknown effect before dispatch.",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "INTERNAL_ERROR"
    assert sink.calls == []


def test_company_consult_dispatch_validator_refuses_unhashable_schema_as_typed_error() -> None:
    request = consultation_contract.build_company_consult_dispatch_request(
        peer=_peer().public_projection(),
        consultation_schema=CONSULTATION_SCHEMA,
        semantic={
            "to": _peer().peer_ref,
            "question": "Refuse malformed schema.",
            "evidence_refs": [],
            "artifact_revisions": [],
        },
        valid_until="2026-09-14T00:00:00Z",
    )
    request["consultation_schema"] = []

    with pytest.raises(CompanyConsultationToolError) as exc_info:
        consultation_contract.validate_company_consult_dispatch_request(request)

    assert exc_info.value.code == "INVALID_REQUEST"


def test_company_consult_dispatch_binds_semantic_target_to_trusted_peer() -> None:
    with pytest.raises(CompanyConsultationToolError) as exc_info:
        consultation_contract.build_company_consult_dispatch_request(
            peer=_peer().public_projection(),
            consultation_schema=CONSULTATION_SCHEMA,
            semantic={
                "to": "peer-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "question": "Do not allow a second peer identity.",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
            valid_until="2026-09-14T00:00:00Z",
        )

    assert exc_info.value.code == "INVALID_REQUEST"


def test_company_consult_dispatch_budget_source_is_immutable() -> None:
    budget = consultation_contract._COMPANY_CONSULT_DISPATCH_BUDGET

    with pytest.raises(TypeError):
        budget["max_answers"] = 2


def test_company_consult_public_validator_enforces_declared_question_length() -> None:
    gateway, sink = _gateway()

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "x" * 16001,
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"
    assert sink.calls == []


def _valid_company_consult_dispatch_request() -> dict:
    return consultation_contract.build_company_consult_dispatch_request(
        peer=_peer().public_projection(),
        consultation_schema=CONSULTATION_SCHEMA,
        semantic={
            "to": _peer().peer_ref,
            "question": "Validate the closed request.",
            "evidence_refs": [],
            "artifact_revisions": [],
        },
        valid_until="2026-09-14T00:00:00Z",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request.__setitem__(
            "consultation_schema", CONSULTATION_V2_SCHEMA
        ),
        lambda request: request.__setitem__(
            "consultation_schema", "mastermind.agent_dialogue_consultation.v99"
        ),
        lambda request: request.__setitem__("operation", "reply"),
        lambda request: request.__setitem__("unexpected", True),
        lambda request: request["budget"].__setitem__("max_answers", True),
        lambda request: request["budget"].__setitem__("max_forward_hops", False),
    ],
    ids=[
        "v2-response-schema",
        "unknown-schema",
        "wrong-operation",
        "extra-outer-field",
        "bool-answer-budget",
        "bool-forward-budget",
    ],
)
def test_company_consult_dispatch_refuses_closed_contract_mutations(mutate) -> None:
    request = _valid_company_consult_dispatch_request()
    mutate(request)

    with pytest.raises(CompanyConsultationToolError) as exc_info:
        consultation_contract.validate_company_consult_dispatch_request(request)

    assert exc_info.value.code == "INVALID_REQUEST"


@pytest.mark.parametrize(
    "invalid_timestamp",
    [
        "2026-09-14T00:00:00+00:00",
        "2026-02-30T00:00:00Z",
        "2026-09-14T00:00:60Z",
    ],
    ids=["offset", "invalid-calendar-day", "leap-second"],
)
def test_company_consult_dispatch_refuses_noncanonical_or_impossible_time(
    invalid_timestamp: str,
) -> None:
    request = _valid_company_consult_dispatch_request()
    request["valid_until"] = invalid_timestamp

    with pytest.raises(CompanyConsultationToolError) as exc_info:
        consultation_contract.validate_company_consult_dispatch_request(request)

    assert exc_info.value.code == "INVALID_REQUEST"


def test_company_consult_clock_failure_is_definite_pre_dispatch_internal_error() -> None:
    def broken_clock() -> str:
        raise RuntimeError("clock unavailable")

    sink = _Dispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=_resolver(),
        dispatcher=sink,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=broken_clock,
    )

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "Do not claim an effect before the clock resolves.",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "INTERNAL_ERROR"
    assert sink.calls == []


def test_company_consult_dispatch_failure_after_invocation_remains_effect_unknown() -> None:
    class FailingDispatcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def __call__(self, operation: str, request: dict) -> dict:
            self.calls.append((operation, copy.deepcopy(request)))
            raise RuntimeError("provider result lost")

    sink = FailingDispatcher()
    gateway = CompanyConsultationGateway(
        peer_resolver=_resolver(),
        dispatcher=sink,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-14T00:00:00Z",
    )

    response = _run(
        gateway.call(
            "company.consult",
            {
                "to": _peer().peer_ref,
                "question": "Preserve post-effect uncertainty.",
                "evidence_refs": [],
                "artifact_revisions": [],
            },
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "EFFECT_UNKNOWN"
    assert len(sink.calls) == 1


def test_maximum_declared_company_consult_input_fits_dispatch_envelope() -> None:
    evidence_refs = [
        "https://github.com/" + (chr(97 + index) * 469)
        for index in range(4)
    ]
    artifacts = [
        {
            "repository": ("a" * 99) + "/" + (chr(98 + index) * 100),
            "path": chr(97 + index) + ("p" * 254),
            "commit": format(index + 1, "040x"),
            "content_sha256": format(index + 1, "064x"),
        }
        for index in range(8)
    ]
    request = consultation_contract.build_company_consult_dispatch_request(
        peer=_peer().public_projection(),
        consultation_schema=CONSULTATION_SCHEMA,
        semantic={
            "to": _peer().peer_ref,
            "question": "q" * 16000,
            "evidence_refs": evidence_refs,
            "artifact_revisions": artifacts,
        },
        valid_until="2026-09-14T00:00:00Z",
    )

    assert len(canonical_company_consultation_json(request)) <= (
        consultation_contract.COMPANY_CONSULTATION_MAX_REQUEST_BYTES
    )
