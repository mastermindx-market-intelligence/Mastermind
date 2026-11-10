"""Authenticated context through the actual collector, compiler and Control socket.

Disposable JWTs, mission grants and CF2 attestations are explicit test fixtures.
No installed enrollment, service or native memory activation is claimed here.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile

import httpx
import pytest

from common import coo_agentos_context_contract as wire
from control_plane.coo_principal_host import CooHostProvider, MISSION_AUTHORITY_VERSION
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, ExecutionCapabilityRegistry,
    HERMES_NATIVE_CONTEXT_PROFILE_ID as PROFILE,
    PRINCIPAL_COO_CONTEXT_MCP_CAPABILITY_ID as GRANT,
    PRINCIPAL_COO_MCP_CAPABILITY_ID as LEGACY_GRANT,
)
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.executive_mcp import coo as descriptors, server
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_binding import _digest, principal_frame
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from tests import test_executive_coo_app as app_tests
from tests import test_executive_coo_host as host_tests
from tests import test_executive_coo_mcp as mcp_tests
from tests import test_executive_principal_ingress as ingress_tests
from tests import test_installed_agentos_context as reader_tests

ROOT = Path(__file__).resolve().parents[1]
WORK = "WS:ONE"
rsa_key = app_tests.rsa_key


def enrolled(tmp_path, monkeypatch, *, mutate_result=None):
    host, coo, principal, policy = host_tests.setup(tmp_path)
    raw = json.loads(policy.read_bytes())
    raw["profiles"][PROFILE]["enabled"] = True  # Test-only explicit enrollment.
    policy.write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(policy, source_root=ROOT)
    coo["missions"][0].update(work_ref=WORK, capability_profile_id=PROFILE,
        capability_profile_digest=registry.profiles[PROFILE].profile_digest,
        authority_version=MISSION_AUTHORITY_VERSION, principal_actions=[wire.ACTION])
    owner = tmp_path / "owner"
    owner.mkdir()
    collector, seen = reader_tests.bound(owner, monkeypatch, mutate_result=mutate_result)
    reader = collector.agentos_context_reader(macro_root=seen["macro"])
    provider = CooHostProvider(host.source, host.workspace, agentos_context_reader=reader)
    seen.update(coo=coo, provider=provider, collector=collector, policy=policy)
    return provider, principal, seen


def frame_for(provider, principal, work=WORK):
    _, fact, authority = provider.source.for_principal(principal, work)
    return dict(schema=wire.FRAME_SCHEMA, principal=copy.deepcopy(principal),
        principal_context=dict(work_ref=work, principal_binding_digest=fact.principal_binding_digest,
            mission_authority_ref=authority.mission_authority_ref,
            authority_generation_digest=authority.authority_generation_digest),
        capability_profile_digest=authority.capability_profile_digest)


def signed_components(tmp_path, monkeypatch, rsa_key, *, after_read=None, mutate_result=None):
    """Real signed App and compiler owners; private socket is tested separately."""
    _, token, current, settings = app_tests.setup(rsa_key, tmp_path)
    provider, _, seen = enrolled(tmp_path, monkeypatch, mutate_result=mutate_result)
    coo = seen["coo"]
    coo.update(policy=json.loads(json.dumps(dataclasses.asdict(settings.policy))), binding=current["binding"])
    coo["missions"][0]["principal_binding_digest"] = _digest(coo["binding"]["binding"])
    def authority(principal, work_ref):
        return provider.source.for_principal(principal_frame(principal), work_ref)[2]
    def context(principal, context, digest):
        value = provider.read_agentos_context(dict(schema=wire.FRAME_SCHEMA,
            principal=principal_frame(principal), principal_context=dataclasses.asdict(context),
            capability_profile_digest=digest))
        if after_read: after_read(seen)
        return value
    selected = dataclasses.replace(settings, authority_provider=authority,
        agentos_context_provider=context,
        catalogue_provider=lambda principal, work_ref=None: provider.source.catalogue_for_principal(
            principal_frame(principal), work_ref=work_ref))
    return token, current, selected, provider, seen


@pytest.fixture
def actual_result(tmp_path, monkeypatch):
    provider, principal, seen = enrolled(tmp_path, monkeypatch)
    frame = frame_for(provider, principal)
    result = provider.read_agentos_context(frame)
    return frame, result, seen


def test_legacy_catalogue_and_profile_identities_remain_exact():
    registry = ExecutionCapabilityRegistry.load(ROOT / "config/executive_claude_principal_capabilities.json")
    worker = ExecutionCapabilityRegistry.load(ROOT / "config/executive_agent_capabilities.json")
    assert PROFILE not in worker.profiles and GRANT not in worker.mcp_servers
    assert registry.profiles["principal.claude-code.executive-coo.v1"].profile_digest == "5d4a2b7e89c5fee0e34be6a623a4a19e5d91b5d743c7365826ef3384af8bf217"
    assert registry.profiles["principal.hermes-native.executive-coo.v1"].profile_digest == "468554c7ba97df5fe86933f08d6928daa48910a1fba2494cd3a537a417382a3d"
    assert registry.profiles[PROFILE].enabled is False
    assert descriptors.COO_TOOL_SCHEMA_DIGEST == "5cf2a0de4a47686c545d1ee3d9c388ab4dc94c880cb0670140de2eca2e54f550"
    assert descriptors.COO_CONTEXT_TOOL_SCHEMA_DIGEST == "5fa24aa1d907d66d0ca0a56168617f955e09d063f532cf527fe0d7b923fb50af"
    assert descriptors.COO_CONTEXT_TOOL_SPECS[:-1] == descriptors.COO_TOOL_SPECS
    assert registry.mcp_servers[GRANT].config_name == registry.mcp_servers[LEGACY_GRANT].config_name


@pytest.mark.parametrize("bad", ["third_alias", "normalized_alias", "both", "borrow", "disabled_borrow", "name", "url", "version", "auth"])
def test_shared_connection_exception_is_closed(tmp_path, bad):
    raw = json.loads((ROOT / "config/executive_claude_principal_capabilities.json").read_bytes())
    if bad == "third_alias": raw["mcp_servers"]["unreviewed-alias"] = copy.deepcopy(raw["mcp_servers"][GRANT])
    elif bad == "normalized_alias": raw["mcp_servers"][" " + LEGACY_GRANT.upper() + " "] = copy.deepcopy(raw["mcp_servers"][LEGACY_GRANT])
    elif bad == "both": raw["profiles"][PROFILE]["mcp_servers"].append(LEGACY_GRANT)
    elif bad in {"borrow", "disabled_borrow"}:
        raw["profiles"][host_tests.PRINCIPAL_PROFILE]["mcp_servers"] = [GRANT]
        if bad == "disabled_borrow": raw["profiles"][host_tests.PRINCIPAL_PROFILE]["enabled"] = False
    else:
        field, value = {"name": ("config_name", "anotherCoo"), "url": ("url", "https://other.invalid/mcp/coo"),
            "version": ("server_version", "2.0.0"), "auth": ("auth_status", "unsupported")}[bad]
        raw["mcp_servers"][GRANT][field] = value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(CapabilityPolicyError):
        ExecutionCapabilityRegistry.load(path, source_root=ROOT)


def test_catalogue_alternatives_are_independent_of_registry_order(tmp_path):
    raw = json.loads((ROOT / "config/executive_claude_principal_capabilities.json").read_bytes())
    baseline = ExecutionCapabilityRegistry.load(ROOT / "config/executive_claude_principal_capabilities.json")
    raw["mcp_servers"] = dict(reversed(list(raw["mcp_servers"].items())))
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw))
    observed = ExecutionCapabilityRegistry.load(path, source_root=ROOT)
    assert observed.policy_digest == baseline.policy_digest
    assert observed.profiles == baseline.profiles


def test_actual_compiler_result_keeps_bytes_and_binds_receipt(actual_result):
    frame, value, seen = actual_result
    raw, receipt = wire.validate_result(wire.decode(wire.encode(value)),
        expected_context=frame["principal_context"], capability_profile_digest=frame["capability_profile_digest"])
    assert raw == seen["results"][0]["stdout"].encode("utf-8")
    assert receipt["bundle_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["source_mode"] == "ADOPTED_SNAPSHOT"
    assert receipt["execution_authority"] is False
    assert len(seen["results"]) == 1 and len(seen["attests"]) == 2
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("bad", ["unknown", "profile", "context", "encoding", "bad_base64", "extra_padding", "base64_limit", "raw_limit", "hash", "work", "repo", "generated", "budget", "degraded", "omitted", "overflow_float"])
def test_wire_rejects_conflicts_without_rewriting_original_bytes(actual_result, bad):
    frame, original, _ = actual_result
    value = copy.deepcopy(original)
    if bad == "unknown": value["compiler_path"] = "/caller/selected"
    elif bad == "profile": value["capability_profile_digest"] = "f" * 64
    elif bad == "context": value["principal_context"]["authority_generation_digest"] = "f" * 64
    elif bad == "encoding": value["bundle_encoding"] = "utf8"
    elif bad == "bad_base64": value["bundle_base64"] = "%%%"
    elif bad == "extra_padding": value["bundle_base64"] += "="
    elif bad == "base64_limit": value["bundle_base64"] = "A" * (wire.MAX_BASE64_CHARS + 1)
    elif bad == "raw_limit": value["bundle_base64"] = base64.b64encode(b" " * (wire.MAX_BUNDLE_BYTES + 1)).decode()
    elif bad == "hash": value["receipt"]["bundle_sha256"] = "f" * 64
    else:
        bundle = json.loads(base64.b64decode(value["bundle_base64"]))
        if bad == "work": bundle["target"]["workstream"] = "WS:OTHER"
        elif bad == "repo": bundle["repo_sha"] = "f" * 40
        elif bad == "generated": bundle["generated_at"] = "2020-01-01T00:00:00Z"
        elif bad == "budget": bundle["token_budget"] = 3999
        elif bad == "degraded": bundle["degraded"].append("fixture-extra")
        elif bad == "omitted": bundle["omitted_due_to_budget"].append("fixture-extra")
        elif bad == "overflow_float": bundle["source_metric"] = "__overflow__"
        raw = json.dumps(bundle, ensure_ascii=False).encode()
        if bad == "overflow_float": raw = raw.replace(b'"__overflow__"', b'1e999')
        value["bundle_base64"] = base64.b64encode(raw).decode()
        value["receipt"]["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        from control_plane.agentos_context_bundle import validate_context_read
        assert validate_context_read(raw, value["receipt"], work_ref=WORK) == (raw, value["receipt"])
    with pytest.raises((ValueError, RuntimeError)):
        wire.validate_result(value, expected_context=frame["principal_context"],
            capability_profile_digest=frame["capability_profile_digest"])
    assert original != value


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}', b'{"a":-1e999}', b'\xff', b'[' * 2000, b' ' * (wire.MAX_RESPONSE_BYTES + 1)])
def test_strict_decoder_refuses_ambiguous_or_oversized_json(raw):
    with pytest.raises(ValueError): wire.decode(raw)


@pytest.mark.parametrize("bad", ["action", "disabled", "legacy", "profile_digest", "binding", "work", "generation", "reader"])
def test_host_refuses_before_compiler_invocation(tmp_path, monkeypatch, bad):
    provider, principal, seen = enrolled(tmp_path, monkeypatch)
    frame = frame_for(provider, principal)
    row = seen["coo"]["missions"][0]
    if bad == "action": row["principal_actions"] = ["bounded_intent"]
    elif bad == "disabled": row["enabled"] = False
    elif bad == "legacy":
        registry = ExecutionCapabilityRegistry.load(seen["policy"], source_root=ROOT)
        row.update(capability_profile_id=host_tests.PRINCIPAL_PROFILE,
            capability_profile_digest=registry.profiles[host_tests.PRINCIPAL_PROFILE].profile_digest)
    elif bad == "profile_digest": frame["capability_profile_digest"] = "f" * 64
    elif bad == "binding": frame["principal"]["client_ref"] = "f" * 64
    elif bad == "work": frame["principal_context"]["work_ref"] = "WS:FOREIGN"
    elif bad == "generation": frame["principal_context"]["authority_generation_digest"] = "f" * 64
    elif bad == "reader": provider.agentos_context_reader = None
    with pytest.raises((ValueError, RuntimeError)):
        provider.read_agentos_context(frame)
    assert seen["results"] == [] and seen["attests"] == []


@pytest.mark.parametrize("bad", ["disabled", "source", "workspace", "reader"])
def test_host_discards_compiled_result_if_owner_changes(tmp_path, monkeypatch, bad):
    refs = {}
    def mutate(*_):
        provider, seen = refs["provider"], refs["seen"]
        if bad == "disabled": seen["coo"]["missions"][0]["enabled"] = False
        elif bad == "source": provider.source = copy.copy(provider.source)
        elif bad == "workspace": provider.workspace = copy.copy(provider.workspace)
        elif bad == "reader": provider.agentos_context_reader = None
    provider, principal, seen = enrolled(tmp_path, monkeypatch, mutate_result=mutate)
    refs.update(provider=provider, seen=seen)
    frame = frame_for(provider, principal)
    with pytest.raises((ValueError, RuntimeError)):
        provider.read_agentos_context(frame)
    assert len(seen["results"]) == 1 and not seen["child_macro"].exists()


def test_mixed_catalogues_refuse_without_losing_original_disabled_authority(tmp_path, monkeypatch):
    provider, principal, seen = enrolled(tmp_path, monkeypatch)
    source = provider.source
    assert source.catalogue_for_principal(principal) == wire.CATALOGUE
    registry = ExecutionCapabilityRegistry.load(seen["policy"], source_root=ROOT)
    current = seen["coo"]["missions"][0]
    old = copy.deepcopy(current)
    old.update(work_ref="WS:OLD", capability_profile_id=host_tests.PRINCIPAL_PROFILE,
        capability_profile_digest=registry.profiles[host_tests.PRINCIPAL_PROFILE].profile_digest,
        principal_actions=["bounded_intent"])
    seen["coo"]["missions"].append(old)
    seen["coo"]["missions"].sort(key=lambda row: row["work_ref"])
    with pytest.raises(ValueError): source.catalogue_for_principal(principal)
    old["enabled"] = False
    assert source.catalogue_for_principal(principal) == wire.CATALOGUE
    assert source.for_principal(principal, "WS:OLD")[0]["enabled"] is False
    current["enabled"] = False
    assert source.catalogue_for_principal(principal) == wire.LEGACY_CATALOGUE
    assert source.for_principal(principal, WORK)[0]["enabled"] is False
    with pytest.raises(ValueError): source.catalogue_for_principal(principal, work_ref=WORK)
    assert seen["results"] == []


@pytest.mark.parametrize("change", ["disabled", "action", "profile", "binding"])
def test_app_rechecks_selected_mission_after_control_returns(tmp_path, monkeypatch, rsa_key, change):
    def revoke(seen):
        row = seen["coo"]["missions"][0]
        if change == "disabled": row["enabled"] = False
        elif change == "action": row["principal_actions"] = ["bounded_intent"]
        elif change == "profile": row["capability_profile_digest"] = "f" * 64
        elif change == "binding": row["principal_binding_digest"] = "f" * 64
    token, _, settings, provider, seen = signed_components(tmp_path, monkeypatch, rsa_key, after_read=revoke)
    second = copy.deepcopy(seen["coo"]["missions"][0])
    second["work_ref"] = "WS:TWO"
    seen["coo"]["missions"].append(second)
    app = create_coo_app(settings, audit_sink=app_tests.Sink())
    response = asyncio.run(app_tests.request(app, token, wire.TOOL, {"work_ref": WORK}))
    assert response.status_code in (403, 503), response.text
    assert response.json()["ok"] is False and "data" not in response.json()
    assert len(seen["results"]) == 1
    if change == "disabled":
        principal = {k: v for k, v in seen["coo"]["binding"]["binding"].items() if k != "permission_digest"}
        assert provider.source.catalogue_for_principal(principal) == wire.CATALOGUE


@pytest.mark.parametrize("when", ["before", "catalogue", "result"])
def test_app_refuses_equal_policy_settings_replacement(tmp_path, monkeypatch, rsa_key, when):
    refs, invoked = {}, []
    def replace(_=None):
        refs["app"].settings = dataclasses.replace(refs["app"].settings,
            authority_provider=lambda *_: invoked.append("replacement-authority"))
    token, _, settings, _, seen = signed_components(tmp_path, monkeypatch, rsa_key,
        after_read=replace if when == "result" else None)
    if when == "catalogue":
        original = settings.catalogue_provider
        def catalogue(*args):
            result = original(*args)
            replace()
            return result
        settings = dataclasses.replace(settings, catalogue_provider=catalogue)
    app = create_coo_app(settings, audit_sink=app_tests.Sink())
    refs["app"] = app
    if when == "before": replace()
    response = asyncio.run(app_tests.request(app, token, wire.TOOL, {"work_ref": WORK}))
    assert response.status_code in (403, 503) and "data" not in response.json()
    assert invoked == []
    assert len(seen["results"]) == (1 if when == "result" else 0)


@pytest.mark.parametrize("field", ["_load_coo", "_registry_loader"])
def test_context_source_refuses_replacement_callback_before_read(tmp_path, monkeypatch, field):
    provider, principal, seen = enrolled(tmp_path, monkeypatch)
    frame = frame_for(provider, principal)
    old = getattr(provider.source, field)
    calls = []
    def replacement():
        calls.append(True)
        return old()
    setattr(provider.source, field, replacement)
    with pytest.raises(ValueError): provider.read_agentos_context(frame)
    assert calls == [] and seen["results"] == []


@pytest.mark.parametrize("when,change", [("before", "client"), ("before", "socket"), ("during", "client"), ("during", "socket")])
def test_fact_client_context_pins_original_transport(tmp_path, monkeypatch, rsa_key, when, change):
    token, _, settings, provider, seen = signed_components(tmp_path, monkeypatch, rsa_key)
    principal = asyncio.run(app_tests.JwtAuthenticator(policy=settings.policy,
        jwks_cache=settings.executive.jwks_cache).verify_token(token, now=app_tests.fixture.NOW))
    frame = frame_for(provider, principal_frame(principal))
    value = provider.read_agentos_context(frame)
    refs, calls = {}, []
    def changed():
        facts = refs["facts"]
        if change == "client": facts._client = copy.copy(facts._client)
        else: facts._client.socket_path = tmp_path / "different.sock"
    async def transport(self, request):
        calls.append(copy.deepcopy(request))
        if when == "during": changed()
        return {"ok": True, "result": copy.deepcopy(value)}
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    monkeypatch.setattr(CeoIngressWorkspaceClient, "request", transport)
    facts = CooFactsClient(tmp_path / "selected.sock")
    refs["facts"] = facts
    if when == "before": changed()
    with pytest.raises(ValueError, match="transport changed"):
        asyncio.run(facts.agentos_context(principal, wire.context(frame["principal_context"]),
            frame["capability_profile_digest"]))
    assert len(calls) == (0 if when == "before" else 1)


def test_same_mcp_server_keeps_principal_catalogues_separate(tmp_path, monkeypatch, rsa_key):
    token, current, settings, provider, seen = signed_components(tmp_path, monkeypatch, rsa_key)
    from integrations.mastermind_executive_app.coo_binding import COO_BINDING_SCHEMA_V2, COO_SCOPES
    second_token = app_tests.fixture._token(rsa_key, scope=" ".join(COO_SCOPES), client_id="second-enrolled-client")
    second_principal = asyncio.run(app_tests.JwtAuthenticator(policy=settings.policy,
        jwks_cache=settings.executive.jwks_cache).verify_token(second_token, now=app_tests.fixture.NOW))
    second_binding = dict(principal_frame(second_principal), permission_digest="b" * 64)
    bindings = [current["binding"]["binding"], second_binding]
    current["binding"] = dict(schema=COO_BINDING_SCHEMA_V2, enabled=True, bindings=sorted(bindings, key=_digest))
    seen["coo"]["binding"] = current["binding"]
    registry = ExecutionCapabilityRegistry.load(seen["policy"], source_root=ROOT)
    second = copy.deepcopy(seen["coo"]["missions"][0])
    second.update(work_ref="WS:TWO", principal_binding_digest=_digest(second_binding),
        capability_profile_id=host_tests.PRINCIPAL_PROFILE,
        capability_profile_digest=registry.profiles[host_tests.PRINCIPAL_PROFILE].profile_digest,
        principal_actions=["bounded_intent"])
    seen["coo"]["missions"].append(second)
    app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
        coo_settings=settings, audit_sink=app_tests.Sink())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                responses = await asyncio.gather(*(mcp_tests.rpc(client, identity, "/mcp/coo")
                    for identity in (token, second_token, token, second_token)))
                for response, expected in zip(responses, (descriptors.COO_CONTEXT_TOOL_NAMES,
                        descriptors.COO_TOOL_NAMES, descriptors.COO_CONTEXT_TOOL_NAMES, descriptors.COO_TOOL_NAMES)):
                    assert response.status_code == 200, response.text
                    assert tuple(t["name"] for t in response.json()["result"]["tools"]) == expected
                refused = await mcp_tests.rpc(client, second_token, "/mcp/coo", "tools/call",
                    {"name": wire.TOOL, "arguments": {"work_ref": "WS:TWO"}})
                assert refused.json()["result"]["isError"] is True
                assert seen["results"] == []
                response = await mcp_tests.rpc(client, token, "/mcp/coo", "tools/call",
                    {"name": wire.TOOL, "arguments": {"work_ref": WORK}})
                payload = json.loads(response.json()["result"]["content"][0]["text"])
                assert payload["ok"] is True, payload
                assert base64.b64decode(payload["data"]["bundle_base64"]) == seen["results"][0]["stdout"].encode()
    asyncio.run(exercise())


def test_near_limit_original_bytes_survive_final_mcp_serialization(tmp_path, monkeypatch, rsa_key):
    def pad(result, *_):
        # Synthetic whitespace stresses the wire limit around actual compiler
        # JSON; this is a transport boundary test, not natural corpus sizing.
        used = len(result["stdout"].encode("utf-8"))
        result["stdout"] += " " * (wire.MAX_BUNDLE_BYTES - used)
    token, _, settings, _, seen = signed_components(tmp_path, monkeypatch, rsa_key, mutate_result=pad)
    app = server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
        coo_settings=settings, audit_sink=app_tests.Sink())
    async def exercise():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                response = await mcp_tests.rpc(client, token, "/mcp/coo", "tools/call",
                    {"name": wire.TOOL, "arguments": {"work_ref": WORK}})
                assert response.status_code == 200, response.text[:300]
                payload = json.loads(response.json()["result"]["content"][0]["text"])
                assert payload["ok"] is True, payload
                raw = base64.b64decode(payload["data"]["bundle_base64"])
                original = seen["results"][0]["stdout"].encode()
                assert raw == original.ljust(wire.MAX_BUNDLE_BYTES, b" ")
                assert len(response.content) < 262144
    asyncio.run(exercise())


@pytest.mark.parametrize("bad", [None, "duplicate", "profile", "oversize"])
def test_private_client_wire_budget_and_cleanup_with_in_memory_streams(actual_result, monkeypatch, bad):
    """Stream component test only; this opens no Unix socket."""
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    from control_plane.coo_principal_host import FACT_SCHEMA
    frame, value, _ = actual_result
    envelope = {"ok": True, "result": copy.deepcopy(value)}
    if bad == "profile": envelope["result"]["capability_profile_digest"] = "f" * 64
    raw = wire.encode(envelope) + b"\n"
    if bad == "duplicate": raw = b'{"ok":false,' + raw[1:]
    elif bad == "oversize": raw = b" " * (wire.MAX_RESPONSE_BYTES + 1) + b"\n"
    seen = dict(closed=0, sent=[], opens=[], budgets=[])
    class Reader:
        async def readuntil(self, separator):
            assert separator == b"\n"
            return raw
    class Writer:
        def write(self, contents): seen["sent"].append(contents)
        async def drain(self): pass
        def close(self): seen["closed"] += 1
        async def wait_closed(self): pass
    async def open_stream(path, *, limit):
        seen["opens"].append((path, limit))
        return Reader(), Writer()
    original_wait = asyncio.wait_for
    async def wait(awaitable, timeout):
        seen["budgets"].append(timeout)
        return await original_wait(awaitable, timeout)
    monkeypatch.setattr(asyncio, "open_unix_connection", open_stream)
    monkeypatch.setattr(asyncio, "wait_for", wait)
    client = CeoIngressWorkspaceClient("/test-only/context.sock")
    if bad is None:
        response = asyncio.run(client.request(frame))
        assert response == envelope
    else:
        with pytest.raises(ValueError): asyncio.run(client.request(frame))
    assert seen["opens"] == [("/test-only/context.sock", wire.MAX_RESPONSE_BYTES)]
    assert seen["budgets"] == [30, 1.0] and seen["closed"] == 1
    assert wire.decode(seen["sent"][0]) == frame
    if bad is None:
        seen["budgets"].clear()
        legacy = dict(schema=FACT_SCHEMA, operation="authority", work_ref=WORK, principal=frame["principal"])
        asyncio.run(client.request(legacy))
        assert seen["budgets"] == [10]


@pytest.mark.parametrize("armed,has_grant", [(False, True), (False, False), (True, True), (True, False)])
def test_optional_control_source_uses_existing_grant_without_arming(tmp_path, monkeypatch, armed, has_grant):
    from ops.executive_os.coo_principal_host import CooInstalledSource, load_control_coo_source
    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    provider, _, seen = enrolled(tmp_path, monkeypatch)
    if not has_grant: seen["coo"]["missions"][0]["principal_actions"] = ["bounded_intent"]
    original = provider.source
    calls = []
    def installed(cls, path, source, *, expected_uid):
        calls.append((path, source, expected_uid))
        return original
    monkeypatch.setattr(CooInstalledSource, "from_path", classmethod(installed))
    raw = dict(executive_mcp_profile=WEB_CEO_V2_PROFILE, coo_principal_armed=armed,
        workspace_acquisition={}, workspace_resource_policy={}, workspace_control_room={}, ceo_ingress_app_peer_uid=458)
    result = load_control_coo_source(raw, ROOT, expected_uid=458, install_path=tmp_path / "installed.json")
    assert result is (original if armed or has_grant else None)
    assert len(calls) == 1 and raw["coo_principal_armed"] is armed
    assert seen["results"] == []


@pytest.mark.parametrize("missing", ["workspace_acquisition", "workspace_resource_policy", "workspace_control_room", "ceo_ingress_app_peer_uid", "executive_mcp_profile"])
def test_unarmed_source_missing_prerequisite_never_opens_installation(tmp_path, monkeypatch, missing):
    from ops.executive_os.coo_principal_host import CooInstalledSource, load_control_coo_source
    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    calls = []
    monkeypatch.setattr(CooInstalledSource, "from_path", classmethod(lambda *a, **k: calls.append(True)))
    raw = dict(executive_mcp_profile=WEB_CEO_V2_PROFILE, coo_principal_armed=False,
        workspace_acquisition={}, workspace_resource_policy={}, workspace_control_room={}, ceo_ingress_app_peer_uid=458)
    raw.pop(missing)
    assert load_control_coo_source(raw, ROOT, expected_uid=458, install_path=tmp_path / "installed.json") is None
    assert calls == []


@pytest.mark.parametrize("armed", [False, True])
def test_signed_mcp_roundtrip_compiles_exact_context_without_a_job(tmp_path, monkeypatch, rsa_key, armed):
    _, token, current, settings = app_tests.setup(rsa_key, tmp_path)
    provider, _, seen = enrolled(tmp_path, monkeypatch)
    coo = seen["coo"]
    coo.update(policy=json.loads(json.dumps(dataclasses.asdict(settings.policy))), binding=current["binding"])
    coo["missions"][0]["principal_binding_digest"] = _digest(coo["binding"]["binding"])
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-context-", dir="/tmp") as directory:
            socket_root = Path(directory)
            service = ingress_tests.service(tmp_path, socket_root, armed=armed)
            def factory(runtime):
                workspace = WorkspaceReadService(cache=None, runtime=runtime, authorize=None, armed={}, runtime_identity={})
                return CooHostProvider(provider.source, workspace, agentos_context_reader=provider.agentos_context_reader)
            service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding,
                principal_facts_factory=factory)
            base = dataclasses.replace(settings.executive, ceo_ingress_socket_path=socket_root / "principal.sock")
            facts = CooFactsClient(base.ceo_ingress_socket_path)
            selected = dataclasses.replace(settings, executive=base, authority_provider=facts.authority,
                mission_provider=facts.mission, agentos_context_provider=facts.agentos_context,
                catalogue_provider=lambda principal, work_ref=None: provider.source.catalogue_for_principal(
                    principal_frame(principal), work_ref=work_ref))
            app = server.build_web_ceo_v2_with_coo_mcp_app(base, coo_settings=selected, audit_sink=app_tests.Sink())
            await service.start()
            try:
                runtime = service._require_runtime()
                before = runtime.jobs.list_jobs()
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                        listed = await mcp_tests.rpc(client, token, "/mcp/coo")
                        assert listed.status_code == 200, listed.text
                        assert tuple(t["name"] for t in listed.json()["result"]["tools"]) == descriptors.COO_CONTEXT_TOOL_NAMES
                        response = await mcp_tests.rpc(client, token, "/mcp/coo", "tools/call",
                            {"name": wire.TOOL, "arguments": {"work_ref": WORK}})
                        assert response.status_code == 200, response.text
                        envelope = json.loads(response.json()["result"]["content"][0]["text"])
                        assert envelope["ok"] is True, envelope
                        value = envelope["data"]
                        assert base64.b64decode(value["bundle_base64"]) == seen["results"][0]["stdout"].encode()
                        assert value["receipt"]["repo_sha"] == seen["sha"]
                        assert value["receipt"]["execution_authority"] is False
                        assert len(seen["results"]) == 1
                assert runtime.jobs.list_jobs() == before == []
                assert service._ceo_ingress_app_binding.principal_admission_armed is armed
                assert service._ceo_ingress_app_binding.armed is False
            finally:
                await service.close()
    asyncio.run(exercise())


# Actual compiler-backed wire, in-memory streams; no socket or installed effect.
@pytest.mark.parametrize("trigger", ["caller", "request_deadline", "cleanup_error"])
def test_original_context_request_preserves_cancellation_during_cleanup(
        actual_result, monkeypatch, trigger):
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient

    frame, value, _ = actual_result
    envelope = {"ok": True, "result": value}
    raw = wire.encode(envelope) + b"\n"
    seen = {"opens": 0, "writes": [], "closed": 0}

    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()

        class Reader:
            async def readuntil(self, separator):
                assert separator == b"\n"
                return raw

        class Writer:
            def write(self, contents):
                seen["writes"].append(contents)

            async def drain(self):
                pass

            def close(self):
                seen["closed"] += 1

            async def wait_closed(self):
                entered.set()
                if trigger == "cleanup_error":
                    raise OSError("explicit in-memory cleanup failure")
                await release.wait()

        async def open_stream(path, *, limit):
            assert path == "/test-only/context-cancellation.sock"
            assert limit == wire.MAX_RESPONSE_BYTES
            seen["opens"] += 1
            return Reader(), Writer()

        monkeypatch.setattr(asyncio, "open_unix_connection", open_stream)
        client = CeoIngressWorkspaceClient(
            "/test-only/context-cancellation.sock",
            acceptance_timeout_seconds=0.1 if trigger == "request_deadline" else 2)
        task = asyncio.create_task(client.request(frame))
        try:
            await asyncio.wait_for(entered.wait(), timeout=1)
            if trigger == "caller":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            elif trigger == "request_deadline":
                with pytest.raises(ValueError, match="source_unavailable"):
                    await task
            else:
                assert await task == envelope
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert entered.is_set()

    asyncio.run(exercise())
    assert seen["opens"] == seen["closed"] == len(seen["writes"]) == 1
    assert wire.decode(seen["writes"][0]) == frame
