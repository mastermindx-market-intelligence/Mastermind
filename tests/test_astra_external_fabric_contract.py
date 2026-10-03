from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
from typing import Any

import pytest

from control_plane import ceo_request
from control_plane import executive_ceo_ingress as ceo_ingress
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.executive_mcp.schemas import GatewayError, validate_tool_arguments
from integrations.mastermind_executive_app import admission
from integrations.mastermind_executive_app.gateway import (
    READ_SCOPE,
    SUBMIT_SCOPE,
    CeoIngressResponse,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
)

VALID = {
    "operation_key": "astra-external-fabric-contract-001",
    "objective": "Read the bounded source and return the requested evidence.",
    "department": "executive-infrastructure",
    "priority": 10,
    "execution_profile": "research_only",
}
GROUNDING = {
    "mastermind_sha": "1" * 40,
    "macro_sha": "2" * 40,
    "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
}


def _principal() -> VerifiedPrincipal:
    return VerifiedPrincipal(
        policy_id="mastermind-executive-app-submit-example",
        issuer="https://issuer.mastermind.example.com",
        issuer_digest="a" * 64,
        resource="https://executive-app.mastermind.example.com/mcp",
        subject_digest="b" * 64,
        client_ref="c" * 64,
        scopes=(READ_SCOPE, SUBMIT_SCOPE),
        issued_at=1_788_000_000,
        expires_at=1_788_000_600,
        jti_digest=None,
    )


def _accepted_response() -> CeoIngressResponse:
    return CeoIngressResponse(
        transport=TRANSPORT_SENT_OK,
        ok=True,
        result={"dispatched": False, "job_id": "JOB-000001"},
    )


@dataclasses.dataclass
class RecordingClient:
    responses: list[CeoIngressResponse]
    frames: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    async def send_frame(self, _path: Any, frame: Any) -> CeoIngressResponse:
        self.frames.append(dict(frame))
        if not self.responses:
            raise AssertionError("no scripted response remains")
        return self.responses.pop(0)


def _request(client: RecordingClient) -> admission.AdmissionRequest:
    return admission.AdmissionRequest(
        payload=VALID,
        principal=_principal(),
        ceo_ingress_socket_path=Path("/tmp/ceo-ingress.sock"),
        mastermind_root=Path("."),
        macro_root_flag=None,
        environ={},
        client=client,
    )


@pytest.fixture(autouse=True)
def _fixed_grounding(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        admission,
        "observe_trusted_grounding",
        lambda **_kwargs: dict(GROUNDING),
    )


def test_frozen_submit_shape_refuses_physical_routing_fields():
    forbidden_fields = (
        "provider",
        "model",
        "account",
        "provider_home",
        "endpoint",
        "host",
        "worker_id",
        "socket_path",
    )
    for forbidden in forbidden_fields:
        payload = dict(VALID)
        payload[forbidden] = "attacker-choice"
        with pytest.raises(GatewayError):
            validate_tool_arguments("submit_ceo_intent", payload)


def test_app_request_ref_is_stable_and_domain_owned():
    first = ceo_request.app_request_ref(VALID["operation_key"])
    second = ceo_request.app_request_ref(VALID["operation_key"])
    assert first == second
    assert first.startswith("req-")
    assert ceo_request.AUTOMATED_REQUEST_REF_RE.fullmatch(first) is not None


def test_app_turns_five_tool_submit_into_v2_automated_frame():
    client = RecordingClient([_accepted_response()])
    outcome = asyncio.run(admission.compose_admission(_request(client)))
    assert outcome.request_ref == ceo_request.app_request_ref(VALID["operation_key"])
    assert outcome.receipt is not None
    assert outcome.receipt["dispatched"] is False
    assert len(client.frames) == 1
    frame = client.frames[0]
    assert frame["schema"] == ceo_ingress.SUBMIT_SCHEMA_V2
    assert frame["request_ref"] == outcome.request_ref
    assert frame["observed_grounding"] == GROUNDING
    assert "operation_key" not in frame["request"]
    assert frame["request"]["objective"] == VALID["objective"]


def test_effect_unknown_reconciles_same_request_without_second_submit():
    client = RecordingClient(
        [
            CeoIngressResponse(
                transport=TRANSPORT_SENT_UNKNOWN,
                detail="response lost after send",
            ),
            _accepted_response(),
        ]
    )
    outcome = asyncio.run(admission.compose_admission(_request(client)))
    assert outcome.status == admission.STATUS_EFFECT_UNKNOWN
    assert len(client.frames) == 1
    assert client.frames[0]["schema"] == ceo_ingress.SUBMIT_SCHEMA_V2
    reconciled = asyncio.run(
        admission.reconcile_by_request_ref(
            client,
            socket_path=Path("/tmp/ceo-ingress.sock"),
            request_ref=outcome.request_ref,
        )
    )
    assert reconciled.status == admission.STATUS_ACCEPTED
    assert len(client.frames) == 2
    assert [frame["schema"] for frame in client.frames] == [
        ceo_ingress.SUBMIT_SCHEMA_V2,
        ceo_ingress.STATUS_SCHEMA_V2,
    ]
    assert client.frames[1]["request_ref"] == outcome.request_ref
    assert sum(
        frame["schema"] == ceo_ingress.SUBMIT_SCHEMA_V2
        for frame in client.frames
    ) == 1
