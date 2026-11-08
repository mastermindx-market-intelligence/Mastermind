"""Signed v5 tools -> incumbent Workspace -> actual compiler/Events/temp Git.

The private App/Control carrier is explicitly in process. Credential/PR and
host seal seams are the existing inert fixtures. Current DATA and compilation
use the actual issued collector/child; no service, socket or live account runs.
"""
import asyncio
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from common import coo_project_knowledge_contract as wire
from common import coo_discovery_contract as discovery
from common import coo_agentos_context_contract as context
from common import workspace_project_knowledge_read_contract as read_wire
from common import workspace_source_operation_wire as source_wire
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry, HERMES_NATIVE_KNOWLEDGE_PROFILE_ID as PROFILE,
    PRINCIPAL_COO_KNOWLEDGE_MCP_CAPABILITY_ID as GRANT, CapabilityPolicyError)
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.workspace_source_operation_binding import invoke_source_operation
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_mcp import coo as descriptors, server
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
from tests import test_executive_coo_app as app_tests
from tests.test_project_discovery_correction import correction_owner
from tests.test_installed_knowledge_canonical_journey import configured
from tests.test_installed_source_git_identity import identity
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_project_git_publisher import env, isolated_git_env, git, rev_parse

rsa_key = app_tests.rsa_key
ROOT = Path(__file__).parents[1]


def file_request(o):
    return {k: o["request"][k] for k in ("work_ref", "source_commit", "base_revision")} | {
        "schema": wire.FILE_REQUEST_SCHEMA, "request_id": wire.ACTION_PREFIXES[wire.ADD_ACTION] + "b" * 40,
        "file": {"display_name": "Notes.md", "media_type": "text/markdown",
                 "content_utf8": "Retain the original note. 中文\nSecond line.\n"}}


def preference_request(request):
    return {k: request[k] for k in ("work_ref", "source_commit", "base_revision")} | {
        "schema": wire.PREFERENCE_REQUEST_SCHEMA,
        "request_id": wire.ACTION_PREFIXES[wire.PREFERENCE_ACTION] + "c" * 40,
        "expected_preference_revision": None, "value": "Keep replies concise. 保留原文。\nShow source links."}


@pytest.fixture
def signed_knowledge(correction_owner, identity, rsa_key, tmp_path, monkeypatch):
    o = correction_owner
    _, token, state, original = app_tests.setup(rsa_key, tmp_path)
    policy = dataclasses.replace(o["contexts"].policy,
        allowed_subject_digests=tuple(sorted(set(o["contexts"].policy.allowed_subject_digests)
            | set(original.policy.allowed_subject_digests))))
    now = original.executive.clock
    second = app_tests.fixture._token(rsa_key, scope=" ".join(policy.required_scopes), aud=policy.resource)
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=original.executive.jwks_cache)
    who = asyncio.run(authenticator.verify_token(second, now=now()))
    selected = o["bindings"]["profiles"]["member-0"]
    selected["binding"] = {**principal_frame(who), "permission_digest": selected["binding"]["permission_digest"]}
    selected["project_preference_set"] = {"work_ref": "WS:ALPHA", "permission_digest": "4" * 64}
    selected["project_canonical_data_read"] = "6" * 64
    o["who"] = who
    collector, git_owner = configured(o, identity, tmp_path, monkeypatch)
    factory = InstalledWorkspaceSourceOperations(collector=collector, policy=policy,
        load_bindings=lambda: o["bindings"], git_identity=git_owner, runtime_guard=lambda rt: rt is o["runtime"])
    factory._permissions._now = now
    source = factory(o["runtime"], o["private"].supervisor)
    data = factory.canonical_data_owner(o["runtime"])
    authorize, authorize_frame = workspace_authorizers(policy=policy,
        load_bindings=lambda: legacy_workspace_document(o["bindings"], policy))
    cache_owners, clock, cache = cache_fixture(tmp_path / "knowledge-cache")
    document = json.loads(json.dumps(cache_owners[0].state_cache["doc"]).replace("WS:ONE", "WS:ALPHA"))
    document["sources"] = {"macro_sha": o["request"]["source_commit"]}
    cache_owners[0].state_cache["doc"] = document
    from scripts import chairman_control_room as ccr
    with cache_owners[0].state_lock:
        ccr._publish_source_validity(cache_owners[0], document, tuple(clock), tuple(clock))
    reader = WorkspaceReadService(cache=cache, runtime=o["runtime"], authorize=authorize_frame,
        armed={}, runtime_identity={}, canonical_project_data=data.installed_binding(),
        project_knowledge_catalogue_reader=collector.project_knowledge_catalogue_reader(macro_root=collector._macro_root),
        project_knowledge_memory_reader=collector.project_knowledge_memory_reader(macro_root=collector._macro_root),
        project_knowledge_source_reader=collector.project_knowledge_source_reader(macro_root=collector._macro_root))
    frames, after = [], [lambda frame, result: result]
    class Bridge:
        async def request(self, frame):
            frames.append(copy.deepcopy(frame))
            if frame["schema"] == read_wire.FRAME_SCHEMA:
                response = await reader.handle_frame(frame)
            else:
                assert frame["schema"] == source_wire.FRAME_SCHEMA
                response = {"ok": True, "result": await asyncio.to_thread(invoke_source_operation,
                    source, frame, runtime=o["runtime"], supervisor=o["private"].supervisor, host_guard=lambda: True)}
            return after[0](frame, response)
    bridge = Bridge()
    config = WorkspaceAppConfig(authenticator=authenticator, now=now, authorize_principal=authorize,
        client=bridge, source_operation_context=factory._permissions)
    sink = app_tests.Sink()
    verifier = server.MastermindTokenVerifier(authenticator=authenticator, policy=policy, now=now, audit_sink=sink)
    workspace = server.AuditedWorkspaceApp(create_workspace_app(config), verifier,
        authenticator=authenticator, authorize_principal=authorize, fresh_workspace_config=config)
    state["authority"] = dataclasses.replace(state["authority"], work_ref="WS:ALPHA",
        principal_actions=tuple(sorted(wire.REQUIRED_ACTIONS)))
    state["catalogue"] = wire.CATALOGUE
    settings = dataclasses.replace(original, catalogue_provider=lambda *a, **kw: state["catalogue"])
    app = create_coo_app(settings, audit_sink=sink, workspace_app=workspace)
    return dict(o=o, token=token, second=second, state=state, settings=settings, app=app, workspace=workspace,
        config=config, sink=sink, bridge=bridge, frames=frames, after=after, request=file_request(o),
        source=source, factory=factory, data=data, collector=collector, tmp_path=tmp_path)


async def call(s, value, *, tool=wire.AUTHOR_TOOL, headers=None):
    if headers is None:
        headers = [("authorization", "Bearer " + s["token"]),
                   ("x-mastermind-workspace-authorization", "Bearer " + s["second"])]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s["app"]), base_url="http://127.0.0.1") as client:
        response = await client.post("/v1/tools/" + tool, headers=headers, json={"arguments": value})
        assert response.status_code == 200, response.text
        return response.json()


def prepare(s, request=None):
    return asyncio.run(call(s, {"operation": "prepare", "request": request or s["request"]}))


def read(s, mode, **selected):
    return asyncio.run(call(s, {"mode": mode, "work_ref": "WS:ALPHA", **selected}, tool=wire.READ_TOOL))


def land(s, status):
    o = s["o"]
    root = s["tmp_path"] / ("independent-integrator-" + str(o["pr"].create_calls))
    git(s["tmp_path"], "clone", str(o["env"].origin), str(root))
    git(root, "fetch", "origin", status["receipt"]["proposal"]["head_branch"])
    git(root, "merge", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(root, "push", "origin", "main")
    return rev_parse(root, "HEAD")


def test_v5_profile_is_disabled_and_historical_catalogues_keep_their_digests(tmp_path):
    path = ROOT / "config/executive_claude_principal_capabilities.json"
    raw = json.loads(path.read_text())
    registry = ExecutionCapabilityRegistry.load(path)
    profile = registry.profiles[PROFILE]
    assert not profile.enabled and not profile.write_capable
    assert profile.mcp_server_grants[0].capability_id == GRANT
    assert descriptors.COO_KNOWLEDGE_TOOL_SPECS[:-2] == descriptors.COO_DISCOVERY_TOOL_SPECS
    assert descriptors.coo_knowledge_tool_schema_digest() == registry.mcp_servers[GRANT].tool_schema_digest
    assert descriptors.coo_context_tool_schema_digest() == "5fa24aa1d907d66d0ca0a56168617f955e09d063f532cf527fe0d7b923fb50af"
    assert descriptors.coo_current_context_tool_schema_digest() == "41644c90bbd8b5927c5cc7f97f65fef144ba9f9ca6e0277d702d7a8a26fa0da0"
    assert descriptors.coo_discovery_tool_schema_digest() == "94db08906bd04c78565f6172d7a657c13bbe608f3b14dba5649cbedb23deed42"
    for bad in ("wrong_profile", "combined", "write", "transport"):
        value = copy.deepcopy(raw)
        if bad == "wrong_profile":
            value["profiles"]["principal.hermes-native.executive-coo.discovery-correction.v1"]["mcp_servers"] = [GRANT]
        elif bad == "combined":
            value["profiles"][PROFILE]["mcp_servers"].append("mastermind-executive-coo-discovery-correction-v1")
        elif bad == "write":
            value["profiles"][PROFILE]["write_capable"] = True
        else:
            value["mcp_servers"][GRANT]["url"] = "https://example.invalid/mcp"
        target = tmp_path / (bad + ".json")
        target.write_text(json.dumps(value))
        with pytest.raises(CapabilityPolicyError):
            ExecutionCapabilityRegistry.load(target)


@pytest.mark.parametrize("preference", [False, True])
def test_actual_note_or_preference_original_publish_then_current_read(signed_knowledge, preference):
    s = signed_knowledge
    request = preference_request(s["request"]) if preference else s["request"]
    first = prepare(s, request)
    assert first["state"] == "OBSERVED", first
    assert first["catalogue"] == wire.CATALOGUE and first["schema"] == wire.RESULT_SCHEMA
    assert len(first["data"]["preview"]["postimages"]) == 2 and s["o"]["pr"].create_calls == 0
    selected = wire.request_lookup(request)
    assert first["selection"] == selected and len(selected) == 7
    args = {"operation": "submit", "lookup": selected, "preview_witness": first["data"]["preview_witness"]}
    offset = len(s["frames"])
    submitted = asyncio.run(call(s, args))
    assert submitted["state"] == "OBSERVED", submitted
    assert submitted["data"]["receipt"]["kind"] == "PROPOSAL_OBSERVED"
    assert submitted["data"]["receipt"]["sources"] == []
    frames = s["frames"][offset:]
    assert [frame["operation"] for frame in frames] == ["read", "submit"]
    assert frames[0]["request"] == selected
    assert set(frames[1]["request"]) == {"action", "request_id", "work_ref", "preview_witness"}
    assert s["o"]["pr"].create_calls == 1
    repeated = asyncio.run(call(s, args))
    assert repeated == submitted and s["o"]["pr"].create_calls == 1
    data_commit = land(s, submitted["data"])
    settled = asyncio.run(call(s, {"operation": "reconcile", "lookup": selected}))
    assert settled["state"] == "OBSERVED" and settled["data"]["disposition"] == "accepted", settled
    assert len(settled["data"]["receipt"]["sources"]) == 2
    for bad in ("request_hash", "principal", "duplicate_source", "wrong_path", "different_commit"):
        wrong_status = copy.deepcopy(settled["data"])
        sources = wrong_status["receipt"]["sources"]
        if bad == "request_hash":
            wrong_status["request_sha256"] = "f" * 64
        elif bad == "principal":
            wrong_status["owner_context"]["principal_scope"] = "f" * 64
        elif bad == "duplicate_source":
            sources[1] = copy.deepcopy(sources[0])
        elif bad == "wrong_path":
            sources[1]["path"] = "agentos/project-files/WS-OTHER/unrelated.md"
        else:
            sources[1]["commit"] = "f" * 40
        with pytest.raises(ValueError):
            wire.validate_data(wire.AUTHOR_TOOL, {"operation": "reconcile", "lookup": selected},
                wrong_status, workspace_principal=principal_frame(s["o"]["who"]))
    catalogue = read(s, "catalogue")
    assert catalogue["state"] == "OBSERVED", catalogue
    body = catalogue["data"]
    assert body["source"]["commit"] == data_commit != body["code_context"]["executable_macro_commit"]
    assert body["data_observation"]["source_operation"]["request_sha256"] == selected["request_sha256"]
    if preference:
        current = read(s, "memory")["data"]
        assert current["memory"]["value"] == request["value"] and current["availability"] == "AVAILABLE"
        assert current["source"]["revision"] == body["project"]["memory"]["revision"]
        assert current["source"]["content_sha256"] != current["source"]["revision"]
        next_request = {**request, "request_id": wire.ACTION_PREFIXES[wire.PREFERENCE_ACTION] + "d" * 40,
            "source_commit": body["source"]["commit"], "base_revision": body["source"]["workstream_sha256"],
            "expected_preference_revision": current["source"]["content_sha256"], "value": "Updated preference."}
        assert wire.validate_prepare_current(next_request, body, current) == next_request
        later = copy.deepcopy(current)
        later["data_observation"]["canonical_observed_at_ms"] += 1
        assert wire.validate_prepare_current(next_request, body, later) == next_request
        for field in ("reader_closure_sha256", "default_ref"):
            drift = copy.deepcopy(later)
            drift["data_observation"][field] = "f" * 64 if field == "reader_closure_sha256" else "different-ref"
            # Each body is independently well formed; the combined snapshot is not.
            assert read_wire.validate_body(drift, operation="project_knowledge_memory") == drift
            with pytest.raises(ValueError):
                wire.validate_prepare_current(next_request, body, drift)
        assert prepare(s, next_request)["state"] == "OBSERVED"
    else:
        row = next(item for item in body["project"]["files"] if item["display_name"] == request["file"]["display_name"])
        result = read(s, "source", source_ref=row["source_ref"], expected_revision=row["revision"])
        assert result["state"] == "OBSERVED", result
        current = result["data"]
        assert current["document"]["content_utf8"] == request["file"]["content_utf8"]
        assert current["source"]["revision"] == row["revision"] != current["source"]["commit"]
        changed = copy.deepcopy(current)
        changed["document"]["content_utf8"] += "Different bytes."
        digest = hashlib.sha256(changed["document"]["content_utf8"].encode()).hexdigest()
        changed["document"]["content_sha256"] = changed["source"]["content_sha256"] = digest
        assert read_wire.validate_body(changed, operation="project_knowledge_source") == changed
        with pytest.raises(ValueError):
            wire.validate_data(wire.READ_TOOL, {"mode": "source", "work_ref": "WS:ALPHA",
                "source_ref": row["source_ref"], "expected_revision": row["revision"]},
                changed, workspace_principal=principal_frame(s["o"]["who"]))
        wrong = read(s, "source", source_ref=row["source_ref"], expected_revision=current["source"]["commit"])
        assert wrong["state"] != "OBSERVED" or wrong["data"]["availability"] == "UNAVAILABLE"
    assert not s["o"]["runtime"].jobs.list_jobs()
    safe = json.dumps([first, submitted, settled, [dataclasses.asdict(e) for e in s["sink"].events]])
    assert s["token"] not in safe and s["second"] not in safe


@pytest.mark.parametrize("bad", ["source_commit", "base_revision", "preference_revision", "unavailable_memory",
                                 "catalogue_owner", "missing_action", "workspace_grant"])
def test_stale_preconditions_and_missing_grants_preserve_dispatch_evidence(signed_knowledge, bad):
    s = signed_knowledge
    request = preference_request(s["request"]) if bad in {"preference_revision", "unavailable_memory"} else copy.deepcopy(s["request"])
    if bad in {"source_commit", "base_revision"}:
        request[bad] = "f" * len(request[bad])
    elif bad == "preference_revision":
        request["expected_preference_revision"] = "f" * 64
    elif bad == "unavailable_memory":
        def unavailable(frame, response):
            if frame.get("operation") == "project_knowledge_memory":
                from common.workspace_project_knowledge_contract import unavailable_memory
                return {"ok": True, "result": unavailable_memory("WS:ALPHA", "SOURCE_UNAVAILABLE")}
            return response
        s["after"][0] = unavailable
    elif bad == "catalogue_owner":
        s["state"]["catalogue"] = discovery.CATALOGUE
    elif bad == "missing_action":
        s["state"]["authority"] = dataclasses.replace(s["state"]["authority"], principal_actions=(context.CURRENT_ACTION,))
    else:
        s["o"]["bindings"]["profiles"]["member-0"]["project_file_add"] = None
    result = prepare(s, request)
    # The adapter attempted the original POST before Workspace rejected this
    # grant. The private fixture knows no prepare ran; the transport does not.
    expected = "EFFECT_UNKNOWN" if bad == "workspace_grant" else "NOT_DISPATCHED"
    assert result["state"] == expected, result
    if bad == "workspace_grant":
        assert result["selection"] == wire.request_lookup(request)
    assert not any(f["schema"] == source_wire.FRAME_SCHEMA and f["operation"] == "prepare" for f in s["frames"])
    assert s["o"]["pr"].create_calls == 0


def test_prepare_reply_loss_recovers_original_seven_fields_without_second_prepare(signed_knowledge):
    s = signed_knowledge
    def lose(frame, response):
        if frame["schema"] == source_wire.FRAME_SCHEMA and frame["operation"] == "prepare":
            return {"ok": True, "result": {}}
        return response
    s["after"][0] = lose
    lost = prepare(s)
    assert lost["state"] == "EFFECT_UNKNOWN", lost
    assert lost["selection"] == wire.request_lookup(s["request"]) and len(lost["selection"]) == 7
    s["after"][0] = lambda frame, response: response
    seen = asyncio.run(call(s, {"operation": "read", "lookup": lost["selection"]}))
    assert seen["state"] == "OBSERVED" and seen["data"]["receipt"]["kind"] == "INTENT"
    assert sum(f["schema"] == source_wire.FRAME_SCHEMA and f["operation"] == "prepare" for f in s["frames"]) == 1
    assert s["o"]["pr"].create_calls == 0


@pytest.mark.parametrize("change", ["principal", "catalogue", "owner"])
def test_change_after_current_read_cannot_enter_prepare(signed_knowledge, change):
    s = signed_knowledge
    def revoke(frame, response):
        if frame.get("operation") == "project_knowledge_catalogue":
            if change == "principal":
                s["o"]["bindings"]["profiles"]["member-0"]["binding"]["permission_digest"] = "f" * 64
            elif change == "catalogue":
                s["state"]["catalogue"] = discovery.CATALOGUE
            else:
                s["workspace"]._fresh_workspace_config = dataclasses.replace(s["config"])
        return response
    s["after"][0] = revoke
    result = prepare(s)
    assert result["state"] == "NOT_DISPATCHED", result
    assert not any(f["schema"] == source_wire.FRAME_SCHEMA for f in s["frames"])


def test_complete_encoded_note_request_is_bounded_without_truncation(correction_owner):
    request = file_request(correction_owner)
    request["file"]["content_utf8"] = "x" * 32768
    assert wire.arguments(wire.AUTHOR_TOOL, {"operation": "prepare", "request": request})["request"] == request
    request["file"]["content_utf8"] = '"' * 32768
    with pytest.raises(ValueError):
        wire.arguments(wire.AUTHOR_TOOL, {"operation": "prepare", "request": request})
    request["file"]["content_utf8"] = "中" * 10923
    with pytest.raises(ValueError):
        wire.arguments(wire.AUTHOR_TOOL, {"operation": "prepare", "request": request})


@pytest.mark.parametrize("bad", ["path", "preimage", "note_digest", "request_hash", "principal", "witness", "extra_image"])
def test_exact_preview_rejects_wrong_original_inputs(correction_owner, bad):
    o = correction_owner
    request = file_request(o)
    preview = o["service"].prepare(request, o["who"])
    scope = discovery.workspace_scope(principal_frame(o["who"]))
    assert wire.validate_preview(preview, request=request, principal_scope=scope) == preview
    wrong = copy.deepcopy(preview)
    note = next(item for item in wrong["preview"]["postimages"] if "/project-files/" in item["path"])
    if bad == "path": note["path"] = note["path"].replace("WS-ALPHA", "WS-OTHER")
    elif bad == "preimage": note["expected_preimage_sha256"] = "f" * 64
    elif bad == "note_digest": note["content_sha256"] = "f" * 64
    elif bad == "request_hash": wrong["request_sha256"] = "f" * 64
    elif bad == "principal": wrong["owner_context"]["principal_scope"] = "f" * 64
    elif bad == "witness": wrong["preview_witness"]["recipe_fingerprint_sha256"] = "f" * 64
    else: wrong["preview"]["postimages"].append(copy.deepcopy(note))
    with pytest.raises(ValueError):
        wire.validate_preview(wrong, request=request, principal_scope=scope)


def test_real_mcp_v5_catalogue_and_note_prepare_keep_the_original_owner(signed_knowledge):
    s = signed_knowledge
    async def unused(*a, **kw): pytest.fail("unrelated owner")
    app = server.build_web_ceo_v3_with_coo_mcp_app(s["settings"].executive, coo_settings=s["settings"],
        audit_sink=s["sink"], workspace_app=s["workspace"],
        mdm_reader=SimpleNamespace(list_macos_devices=unused, device=unused),
        session_target_projector=unused, session_reply_handler=unused, session_summon_handler=unused)
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                headers = {"authorization": "Bearer " + s["token"],
                    "x-mastermind-workspace-authorization": "Bearer " + s["second"],
                    "accept": "application/json, text/event-stream"}
                listed = await client.post("/mcp/coo", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
                assert tuple(t["name"] for t in listed.json()["result"]["tools"]) == descriptors.COO_KNOWLEDGE_TOOL_NAMES
                response = await client.post("/mcp/coo", headers=headers, json={"jsonrpc": "2.0", "id": 2,
                    "method": "tools/call", "params": {"name": wire.AUTHOR_TOOL,
                        "arguments": {"operation": "prepare", "request": s["request"]}}})
                assert response.status_code == 200, response.text
                envelope = response.json()["result"]
                assert envelope["isError"] is False
                result = json.loads(envelope["content"][0]["text"])
                assert result["state"] == "OBSERVED" and result["catalogue"] == wire.CATALOGUE, result
                assert result["selection"] == wire.request_lookup(s["request"])
                assert s["o"]["pr"].create_calls == 0
    asyncio.run(exercise())
