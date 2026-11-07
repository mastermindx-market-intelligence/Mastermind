"""Signed HTTP/MCP -> original source owner -> real compiler/Git/Events.

Disposable JWTs, canonical grants and PR/credential fixtures are explicit.
The App/Control frame bridge is in memory; no socket, installed service,
real account, provider dispatch or product acceptance is claimed.
"""
import asyncio
import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from common import coo_discovery_contract as wire
from common import coo_agentos_context_contract as context_wire
from common import workspace_discovery_correction_contract as correction
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, HERMES_NATIVE_DISCOVERY_PROFILE_ID as PROFILE,
    PRINCIPAL_COO_DISCOVERY_MCP_CAPABILITY_ID as GRANT, CapabilityPolicyError)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_mcp import coo as descriptors, server
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_binding import principal_frame as executive_frame
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
from tests import test_executive_coo_app as app_tests
from tests.test_project_discovery_correction import correction_owner, selection
from tests.test_workspace_project_git_publisher import env, isolated_git_env

rsa_key = app_tests.rsa_key
ROOT = Path(__file__).parents[1]


@pytest.fixture
def signed_discovery(correction_owner, rsa_key, tmp_path):
    o = correction_owner
    _, token, state, original = app_tests.setup(rsa_key, tmp_path)
    # The original unsigned membership fixture uses opaque digest literals.
    # This signed component fixture enrolls its disposable JWT subject before
    # constructing either App, preserving both exact resources and scopes.
    policy = dataclasses.replace(o["contexts"].policy,
        allowed_subject_digests=tuple(sorted(set(o["contexts"].policy.allowed_subject_digests)
            | set(original.policy.allowed_subject_digests))))
    o["contexts"].policy = policy
    now = original.executive.clock
    second = app_tests.fixture._token(rsa_key, scope=" ".join(policy.required_scopes), aud=policy.resource)
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=original.executive.jwks_cache)
    who = asyncio.run(authenticator.verify_token(second, now=now()))
    old_binding = o["bindings"]["profiles"]["member-0"]["binding"]
    o["bindings"]["profiles"]["member-0"]["binding"] = {
        **principal_frame(who), "permission_digest": old_binding["permission_digest"]}
    o["who"] = who
    state["authority"] = dataclasses.replace(state["authority"], work_ref="WS:ALPHA",
        principal_actions=tuple(sorted((context_wire.CURRENT_ACTION, wire.READ_ACTION, wire.CORRECTION_ACTION))))
    state["catalogue"] = wire.CATALOGUE
    source = WorkspaceSourceOperationService(knowledge_owner=o["service"])
    frames, after = [], [lambda frame, result: result]
    class Bridge:
        async def request(self, frame):
            frames.append(copy.deepcopy(frame))
            result = await asyncio.to_thread(source.handle, frame, peer_guard=lambda: True)
            return {"ok": True, "result": after[0](frame, result)}
    bridge = Bridge()
    authorize, _ = workspace_authorizers(policy=policy,
        load_bindings=lambda: legacy_workspace_document(o["bindings"], policy))
    config = WorkspaceAppConfig(authenticator=authenticator, now=now, authorize_principal=authorize,
        client=bridge, source_operation_context=o["contexts"])
    sink = app_tests.Sink()
    verifier = server.MastermindTokenVerifier(authenticator=authenticator, policy=policy, now=now, audit_sink=sink)
    workspace = server.AuditedWorkspaceApp(create_workspace_app(config), verifier,
        authenticator=authenticator, authorize_principal=authorize, fresh_workspace_config=config)
    settings = dataclasses.replace(original, catalogue_provider=lambda *args, **kwargs: state["catalogue"])
    app = create_coo_app(settings, audit_sink=sink, workspace_app=workspace)
    return dict(o=o, token=token, second=second, state=state, settings=settings, app=app,
        workspace=workspace, config=config, sink=sink, bridge=bridge, frames=frames, after=after)


async def request(s, tool, args, *, headers=None):
    if headers is None:
        headers = [("authorization", "Bearer " + s["token"]),
                   ("x-mastermind-workspace-authorization", "Bearer " + s["second"])]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s["app"]), base_url="http://127.0.0.1") as client:
        result = await client.post("/v1/tools/" + tool, headers=headers, json={"arguments": args})
        assert result.status_code == 200, result.text
        return result.json()


def prepare(s):
    return asyncio.run(request(s, wire.CORRECTION_TOOL, {"operation": "prepare", "request": s["o"]["request"]}))


def test_v4_catalogue_is_closed_and_disabled_without_widening_existing_grants(tmp_path):
    path = ROOT / "config/executive_claude_principal_capabilities.json"
    raw = json.loads(path.read_text())
    registry = ExecutionCapabilityRegistry.load(path)
    assert registry.profiles[PROFILE].enabled is False
    assert registry.profiles[PROFILE].write_capable is False
    assert registry.profiles[PROFILE].mcp_server_grants[0].capability_id == GRANT
    assert descriptors.coo_discovery_tool_schema_digest() == registry.mcp_servers[GRANT].tool_schema_digest
    assert descriptors.COO_DISCOVERY_TOOL_SPECS[:-2] == descriptors.COO_CURRENT_CONTEXT_TOOL_SPECS
    assert descriptors.coo_context_tool_schema_digest() == descriptors.COO_CONTEXT_TOOL_SCHEMA_DIGEST
    for change in ("wrong_profile", "combined", "writable"):
        value = copy.deepcopy(raw)
        if change == "wrong_profile":
            value["profiles"]["principal.hermes-native.executive-coo.current-context.v1"]["mcp_servers"] = [GRANT]
        elif change == "combined":
            value["profiles"][PROFILE]["mcp_servers"].append("mastermind-executive-coo-current-context-v1")
        else:
            value["profiles"][PROFILE]["write_capable"] = True
        bad = tmp_path / (change + ".json"); bad.write_text(json.dumps(value))
        with pytest.raises(CapabilityPolicyError): ExecutionCapabilityRegistry.load(bad)


def test_signed_prepare_original_read_submit_and_observe_share_one_owner(signed_discovery):
    s = signed_discovery; o = s["o"]
    result = prepare(s)
    assert result["state"] == "OBSERVED", result
    assert result["data"]["preview"]["state"] == "DRAFT_ONLY" and o["pr"].create_calls == 0
    lookup = correction.request_lookup(o["request"])
    history = asyncio.run(request(s, wire.SOURCE_TOOL, {"mode": "original", "lookup": lookup}))
    assert history["state"] == "OBSERVED" and history["data"]["original"]["content_utf8"] == o["old"]
    payload = {"operation": "submit", "lookup": lookup, "preview_witness": result["data"]["preview_witness"]}
    submitted = asyncio.run(request(s, wire.CORRECTION_TOOL, payload))
    assert submitted["state"] == "OBSERVED" and submitted["data"]["receipt"]["kind"] == "PROPOSAL_OBSERVED", submitted
    assert o["pr"].create_calls == 1
    before = len(s["frames"])
    observed = asyncio.run(request(s, wire.CORRECTION_TOOL, payload))
    assert observed == submitted and o["pr"].create_calls == 1
    assert [frame["operation"] for frame in s["frames"][before:]] == ["read"]
    text = json.dumps([result, history, submitted, [dataclasses.asdict(event) for event in s["sink"].events]])
    assert s["token"] not in text and s["second"] not in text


@pytest.mark.parametrize("bad", ["missing_companion", "duplicate_companion", "executive_bearer", "missing_action", "legacy_catalogue", "workspace_grant"])
def test_distinct_resource_catalogue_and_action_are_required_before_mutation(signed_discovery, bad):
    s = signed_discovery
    headers = [("authorization", "Bearer " + s["token"]),
               ("x-mastermind-workspace-authorization", "Bearer " + s["second"])]
    if bad == "missing_companion": headers.pop()
    elif bad == "duplicate_companion": headers.append(headers[-1])
    elif bad == "executive_bearer": headers[-1] = (headers[-1][0], headers[0][1])
    elif bad == "missing_action": s["state"]["authority"] = dataclasses.replace(s["state"]["authority"], principal_actions=(context_wire.CURRENT_ACTION,))
    elif bad == "legacy_catalogue": s["state"]["catalogue"] = context_wire.CURRENT_CATALOGUE
    else: s["o"]["bindings"]["profiles"]["member-0"]["project_discovery_correct"] = None
    result = asyncio.run(request(s, wire.CORRECTION_TOOL, {"operation": "prepare", "request": s["o"]["request"]}, headers=headers))
    # The outer adapter conservatively retains uncertainty once it entered the
    # existing Workspace App, even if that App refused before its Control call.
    assert result["state"] in {"NOT_DISPATCHED", "EFFECT_UNKNOWN"}
    assert result["data"] is None and not s["frames"] and not s["o"]["calls"]


@pytest.mark.parametrize("change", ["grant", "catalogue", "routing", "bad_result"])
def test_after_real_prepare_failure_retains_exact_original_recovery_lookup(signed_discovery, change):
    s = signed_discovery
    def after(frame, result):
        if change == "grant": s["o"]["bindings"]["profiles"]["member-0"]["project_discovery_correct"] = None
        elif change == "catalogue": s["state"]["catalogue"] = context_wire.CURRENT_CATALOGUE
        elif change == "routing": s["workspace"]._app = object()
        else: return {"malformed": True}
        return result
    s["after"][0] = after
    result = prepare(s)
    assert result["state"] == "EFFECT_UNKNOWN", result
    assert result["selection"] == correction.request_lookup(s["o"]["request"])
    assert result["data"] is None and len(s["frames"]) == 1 and s["o"]["calls"] == ["prepare"]
    assert s["o"]["runtime"].store.list_events() and s["o"]["pr"].create_calls == 0


def test_changed_full_lookup_never_reaches_submit(signed_discovery):
    s = signed_discovery; preview = prepare(s)
    assert preview["state"] == "OBSERVED", preview
    lookup = correction.request_lookup(s["o"]["request"]); lookup["source_commit"] = "f" * 40
    result = asyncio.run(request(s, wire.CORRECTION_TOOL, {"operation": "submit", "lookup": lookup,
        "preview_witness": preview["data"]["preview_witness"]}))
    assert result["state"] == "NOT_DISPATCHED" and s["o"]["pr"].create_calls == 0
    assert [frame["operation"] for frame in s["frames"]] == ["prepare", "read"]


def test_status_and_preview_are_bound_to_original_hash_and_recipe(signed_discovery):
    s = signed_discovery; preview = prepare(s)
    assert preview["state"] == "OBSERVED", preview
    lookup = correction.request_lookup(s["o"]["request"])
    status = s["o"]["service"].read_status(lookup, s["o"]["who"])
    args = {"operation": "submit", "lookup": lookup, "preview_witness": preview["data"]["preview_witness"]}
    for field in ("request_sha256", "recipe_fingerprint_sha256"):
        changed = copy.deepcopy(status); changed[field] = "f" * 64
        with pytest.raises(ValueError): wire.validate_data(wire.CORRECTION_TOOL, args, changed,
            workspace_principal=preview["workspace_principal"])
    invalid = copy.deepcopy(preview["data"]); invalid["preview"]["postimages"][0]["path"] = []
    with pytest.raises(ValueError): correction.validate_preview(invalid, request=s["o"]["request"],
        principal_scope=invalid["owner_context"]["principal_scope"])


@pytest.mark.parametrize("state,reason", [("NOT_DISPATCHED", "ORIGINAL_OUTCOME_UNKNOWN"),
    ("EFFECT_UNKNOWN", "INVALID_INPUT"), ("UNAVAILABLE", "SOURCE_UNAVAILABLE"), ([], "INVALID_INPUT")])
def test_failure_pairs_cannot_launder_uncertainty(correction_owner, state, reason):
    with pytest.raises(ValueError): wire.result(wire.CORRECTION_TOOL,
        {"operation": "prepare", "request": correction_owner["request"]}, state=state, reason=reason)


def test_real_mcp_catalogue_and_prepare_preserve_owner_result(signed_discovery):
    s = signed_discovery
    async def unused(*a, **kw): pytest.fail("unrelated owner")
    app = server.build_web_ceo_v3_with_coo_mcp_app(s["settings"].executive,
        coo_settings=s["settings"], audit_sink=s["sink"], workspace_app=s["workspace"],
        mdm_reader=SimpleNamespace(list_macos_devices=unused, device=unused),
        session_target_projector=unused, session_reply_handler=unused, session_summon_handler=unused)
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                headers = {"authorization": "Bearer " + s["token"], "accept": "application/json, text/event-stream",
                           "x-mastermind-workspace-authorization": "Bearer " + s["second"]}
                listed = await client.post("/mcp/coo", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
                assert listed.status_code == 200, listed.text
                assert tuple(item["name"] for item in listed.json()["result"]["tools"]) == descriptors.COO_DISCOVERY_TOOL_NAMES
                result = await client.post("/mcp/coo", headers=headers, json={"jsonrpc": "2.0", "id": 2,
                    "method": "tools/call", "params": {"name": wire.CORRECTION_TOOL,
                        "arguments": {"operation": "prepare", "request": s["o"]["request"]}}})
                assert result.status_code == 200, result.text
                raw = result.json()["result"]
                assert raw["isError"] is False
                body = json.loads(raw["content"][0]["text"])
                assert body["state"] == "OBSERVED" and body["selection"] == correction.request_lookup(s["o"]["request"]), body
                assert body["data"]["preview"]["state"] == "DRAFT_ONLY"
    asyncio.run(exercise())
