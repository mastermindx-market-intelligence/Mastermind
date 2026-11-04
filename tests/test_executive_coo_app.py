"""Real signed-JWT COO edge tests; no real credentials or installed Runtime."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
    import test_coo_principal_mandate as mandate_fixture
finally:
    sys.path.pop(0)

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.gateway import AppPolicies, CeoIngressResponse
from integrations.mastermind_executive_app.coo_binding import (
    BINDING_SCHEMA, COO_SCOPES, principal_frame,
)
from integrations.mastermind_executive_app.coo import CooAppSettings, create_coo_app
from integrations.executive_mcp.coo import COO_TOOL_NAMES, validate_coo_tool_arguments

rsa_key = fixture.rsa_key


class Sink:
    def __init__(self):
        self.events = []
    def emit(self, event):
        self.events.append(event)


def setup(rsa_key, tmp_path):
    policy = fixture._read_policy(policy_id="executive-coo", required_scopes=list(COO_SCOPES))
    cache = fixture._FakeJwksCache(rsa_key)
    token = fixture._token(rsa_key, scope=" ".join(COO_SCOPES))
    principal = asyncio.run(JwtAuthenticator(policy=policy, jwks_cache=cache).verify_token(token, now=fixture.NOW))
    current = {"binding": {"schema": BINDING_SCHEMA, "enabled": True,
               "binding": {**principal_frame(principal), "permission_digest": "a" * 64}}}
    base = AppSettings(policies=AppPolicies(fixture._read_policy(), fixture._submit_policy()),
        mastermind_root=tmp_path, macro_root_flag=None, environ={},
        ceo_ingress_socket_path=tmp_path / "absent.sock", read_from_ceo_ingress=True,
        jwks_cache=cache, clock=lambda: fixture.NOW)
    authority = mandate_fixture.authority(work_ref="WS:ONE")
    current["authority"] = authority
    current["mission"] = mandate_fixture._real_owner_mission()
    settings = CooAppSettings(executive=base, policy=policy,
        load_binding=lambda: current["binding"],
        authority_provider=lambda p, work: current["authority"],
        mission_provider=lambda p, work: current["mission"])
    app = create_coo_app(settings, audit_sink=Sink())
    return app, token, current, settings


async def request(app, token, tool, arguments):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        return await client.post("/v1/tools/" + tool,
            headers={"authorization": "Bearer " + token}, json={"arguments": arguments})


def test_static_surface_is_six_role_correct_tools():
    assert COO_TOOL_NAMES == ("executive_mandate", "executive_state", "executive_inbox",
                             "executive_fabric", "submit_principal_intent", "principal_intent_status")
    assert "submit_ceo_intent" not in COO_TOOL_NAMES


def test_real_signed_coo_token_reads_owner_mandate(rsa_key, tmp_path):
    app, token, current, _ = setup(rsa_key, tmp_path)
    result = asyncio.run(request(app, token, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 200, result.text
    assert result.json()["data"]["new_effect_gate"] == "OPEN"
    assert result.json()["data"]["mission"]["work_ref"] == "WS:ONE"


@pytest.mark.parametrize("scope", ["mastermind.executive.read", "mastermind.executive.read mastermind.executive.intent.submit"])
def test_reader_and_ceo_scope_cannot_become_coo(rsa_key, tmp_path, scope):
    app, _, _, _ = setup(rsa_key, tmp_path)
    token = fixture._token(rsa_key, scope=scope)
    result = asyncio.run(request(app, token, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 403
    assert result.json()["error"]["code"] == "scope_refused"


@pytest.mark.parametrize("fault", ["disabled", "client", "subject", "expired", "issuer", "resource"])
def test_unenrolled_or_invalid_signed_principal_is_refused(rsa_key, tmp_path, fault):
    app, token, current, _ = setup(rsa_key, tmp_path)
    changes = {"client": {"client_id": "other-client"}, "subject": {"sub": "other-user"},
               "expired": {"iat": fixture.NOW - 600, "nbf": fixture.NOW - 600, "exp": fixture.NOW - 60},
               "issuer": {"iss": "https://other.invalid"}, "resource": {"aud": "https://other.invalid/mcp"}}
    if fault == "disabled":
        current["binding"] = {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
    else:
        token = fixture._token(rsa_key, scope=" ".join(COO_SCOPES), **changes[fault])
    result = asyncio.run(request(app, token, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code in (401, 403), result.text
    assert "data" not in result.json()


@pytest.mark.parametrize("field", ["actor", "seat", "provider", "principal_binding_digest", "authority_level", "guard"])
def test_model_fields_cannot_supply_principal_authority(field):
    payload = {"operation_key": "test-coo-request", "objective": "Read the assigned source.",
        "department": "executive", "priority": 1, "execution_profile": "research_only", "workstream": "WS:ONE"}
    payload[field] = "caller-claim"
    with pytest.raises(Exception, match="invalid COO"):
        validate_coo_tool_arguments("submit_principal_intent", payload)


def test_missing_real_authority_provider_has_no_default(rsa_key, tmp_path):
    _, _, _, settings = setup(rsa_key, tmp_path)
    with pytest.raises(ValueError, match="explicit installed"):
        dataclasses.replace(settings, authority_provider=None)


def test_authority_provider_cannot_select_a_different_mission(rsa_key, tmp_path):
    app, token, current, _ = setup(rsa_key, tmp_path)
    current["authority"] = dataclasses.replace(current["authority"], work_ref="WS:OTHER")
    result = asyncio.run(request(app, token, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 403


def test_revocation_during_owner_read_withholds_data(rsa_key, tmp_path):
    _, token, current, settings = setup(rsa_key, tmp_path)
    def mission(principal, work_ref):
        current["binding"] = {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
        return current["mission"]
    app = create_coo_app(dataclasses.replace(settings, mission_provider=mission), audit_sink=Sink())
    result = asyncio.run(request(app, token, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 403 and "data" not in result.json()


def test_credential_and_provider_errors_are_not_returned(rsa_key, tmp_path):
    _, token, _, settings = setup(rsa_key, tmp_path)
    def broken(*args):
        raise RuntimeError("PRIVATE_CANARY_SECRET /Users/private/credential")
    app = create_coo_app(dataclasses.replace(settings, authority_provider=broken), audit_sink=Sink())
    result = asyncio.run(request(app, token, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 403
    assert "PRIVATE_CANARY" not in result.text and "/Users" not in result.text


def payload():
    return {"operation_key": "test-coo-request", "objective": "Read the assigned source.",
        "department": "executive", "priority": 1, "execution_profile": "research_only", "workstream": "WS:ONE"}


def test_bounded_submit_requires_current_action_grant_before_ingress(rsa_key, tmp_path):
    app, token, current, _ = setup(rsa_key, tmp_path)
    current["authority"] = dataclasses.replace(
        current["authority"],
        principal_actions=("governed_orchestration",),
    )
    calls = []

    async def send(path, frame):
        calls.append((path, frame))
        raise AssertionError("ungranted bounded intent reached Executive ingress")

    app._client.send_frame = send
    result = asyncio.run(
        request(app, token, "submit_principal_intent", payload())
    )
    assert result.status_code == 403
    assert result.json()["error"]["code"] == "authority_refused"
    assert calls == []


@pytest.mark.parametrize("outcome", ["lost", "raised", "wrong_receipt", "unknown_refusal", "not_sent"])
def test_single_send_preserves_uncertainty_and_original_identity(rsa_key, tmp_path, outcome):
    app, token, _, _ = setup(rsa_key, tmp_path)
    calls = []
    async def send(path, frame):
        calls.append(frame)
        if frame["schema"].endswith("grounding.v1"):
            return CeoIngressResponse("sent_ok", ok=True, result={"mastermind_sha": "1" * 40,
                "macro_sha": "2" * 40, "boot_packet_schema": "mastermind.ceo_boot_packet.v1"})
        if outcome == "raised":
            raise RuntimeError("PRIVATE_POST_SEND_FAILURE")
        if outcome == "wrong_receipt":
            return CeoIngressResponse("sent_ok", ok=True, result={"dispatched": False})
        if outcome == "unknown_refusal":
            return CeoIngressResponse("sent_ok", ok=False, error={"code": "PRIVATE_ERROR"})
        return CeoIngressResponse("not_sent" if outcome == "not_sent" else "sent_effect_unknown")
    app._client.send_frame = send
    result = asyncio.run(request(app, token, "submit_principal_intent", payload()))
    assert result.status_code == (503 if outcome == "not_sent" else 202), result.text
    assert result.json()["request_ref"].startswith("req-coo-")
    assert len(calls) == 2
    assert "PRIVATE" not in result.text


@pytest.mark.parametrize("code", ["backend_unavailable", "internal_error", "response_too_large", "backend_refused"])
def test_post_send_backend_failure_does_not_claim_no_effect(rsa_key, tmp_path, code):
    app, token, _, _ = setup(rsa_key, tmp_path)
    async def send(path, frame):
        if frame["schema"].endswith("grounding.v1"):
            return CeoIngressResponse("sent_ok", ok=True, result={"mastermind_sha": "1" * 40,
                "macro_sha": "2" * 40, "boot_packet_schema": "mastermind.ceo_boot_packet.v1"})
        return CeoIngressResponse("sent_ok", ok=False, error={"code": code, "message": "private"})
    app._client.send_frame = send
    result = asyncio.run(request(app, token, "submit_principal_intent", payload()))
    assert result.status_code == 202, result.text
    assert result.json()["status"] == "effect_unknown"


def test_direct_app_audits_invalid_oauth_refusal(rsa_key, tmp_path):
    app, _, _, _ = setup(rsa_key, tmp_path)
    result = asyncio.run(request(app, "invalid-token", "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 401
    assert app._audit_sink.events and app._audit_sink.events[-1].accepted is False


other_rsa_key = fixture.other_rsa_key


def test_signature_not_just_claim_shape_is_verified(rsa_key, other_rsa_key, tmp_path):
    app, _, _, _ = setup(rsa_key, tmp_path)
    forged = fixture._token(other_rsa_key, scope=" ".join(COO_SCOPES))
    result = asyncio.run(request(app, forged, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 401
    assert result.json()["error"]["code"] == "token_signature_refused"


def test_audit_failure_refuses_before_owner_read(rsa_key, tmp_path):
    app, token, _, _ = setup(rsa_key, tmp_path)
    def broken(event):
        raise RuntimeError("PRIVATE_AUDIT_FAILURE")
    app._audit_sink.emit = broken
    result = asyncio.run(request(app, token, "executive_mandate", {"work_ref": "WS:ONE"}))
    assert result.status_code == 500 and "PRIVATE_AUDIT" not in result.text


@pytest.mark.parametrize("limit", [True, 0, 3, "2"])
def test_principal_attempt_limit_cannot_be_widened(limit):
    with pytest.raises(Exception):
        validate_coo_tool_arguments("submit_principal_intent", {**payload(), "attempt_limit": limit})


def test_submit_requires_explicit_workstream():
    request = payload(); del request["workstream"]
    with pytest.raises(Exception):
        validate_coo_tool_arguments("submit_principal_intent", request)


@pytest.mark.parametrize("field,value", [("job_id", ""), ("status", "MADE_UP"), ("fingerprint", "bad"),
                                         ("created_at_ms", True), ("grounding", {}), ("authority", {}), ("unexpected", "private")])
def test_malformed_matching_receipt_is_not_reported_accepted(rsa_key, tmp_path, field, value):
    from control_plane import ceo_intent
    from control_plane.coo_principal_envelope import derive_principal_envelope
    from control_plane.executive_runtime import Runtime
    app, token, current, _ = setup(rsa_key, tmp_path)
    _, stamp = asyncio.run(app.authorize_token(token))
    authority = current["authority"]
    context = PrincipalAdmissionContext("WS:ONE", stamp, authority.mission_authority_ref, authority.authority_generation_digest)
    grounding = {"mastermind_sha": "1" * 40, "macro_sha": "2" * 40, "boot_packet_schema": "mastermind.ceo_boot_packet.v1"}
    bundle = derive_principal_envelope(payload(), context=context, workspace_root=str(tmp_path / "workspaces"), grounding=grounding)
    receipt = ceo_intent.submit_intent(Runtime.at(tmp_path / "runtime"), bundle["envelope"],
        workspace_root=tmp_path / "workspaces", principal_context=context,
        principal_request_ref=bundle["request_ref"], principal_admission_guard=lambda _: None)
    receipt[field] = value
    async def send(path, frame):
        if frame["schema"].endswith("grounding.v1"):
            return CeoIngressResponse("sent_ok", ok=True, result=grounding)
        return CeoIngressResponse("sent_ok", ok=True, result=receipt)
    app._client.send_frame = send
    result = asyncio.run(request(app, token, "submit_principal_intent", payload()))
    assert result.status_code == 202, result.text
    assert result.json()["status"] == "effect_unknown"


def test_binding_is_checked_before_existing_read_owner(rsa_key, tmp_path):
    app, token, current, _ = setup(rsa_key, tmp_path)
    current["binding"] = {"schema": BINDING_SCHEMA, "enabled": False, "binding": None}
    calls = []
    async def read(name, arguments):
        calls.append(name)
        raise AssertionError("unbound principal reached the reader")
    app._read_gateway.call = read
    result = asyncio.run(request(app, token, "executive_state", {}))
    assert result.status_code == 403 and calls == []


@pytest.mark.parametrize("change", ["resource", "scope", "policy_id"])
def test_role_policy_cannot_drift_from_existing_executive_resource(rsa_key, tmp_path, change):
    _, _, _, settings = setup(rsa_key, tmp_path)
    changes = {"resource": {"resource": settings.policy.resource + "/other"},
        "scope": {"required_scopes": ("mastermind.executive.read",)},
        "policy_id": {"policy_id": settings.executive.policies.read.policy_id}}
    with pytest.raises(ValueError):
        dataclasses.replace(settings, policy=dataclasses.replace(settings.policy, **changes[change]))
