"""Public COO composition over the installed auth, binding and Unix ingress owners.

All identities and sources are disposable. This exercises the existing edge's
header rewrite and trusted-proxy receiver, not live enrollment or deployment.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from control_plane.executive_agent_capabilities import (
    HERMES_NATIVE_PRINCIPAL_PROFILE_ID,
)
from integrations.business_mcp_auth.contracts import load_resource_policy
from integrations.executive_mcp import server
from integrations.mastermind_executive_app import gateway
from integrations.mastermind_executive_app.coo import CooApp, CooAppSettings
from integrations.mastermind_executive_app.coo_binding import (
    COO_BINDING_SCHEMA_V2, COO_SCOPES, _digest, principal_frame,
)
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from integrations.mastermind_executive_app.gateway import AppPolicies, CeoIngressClient
from ops.executive_os import executive_mcp_entry as entry
from tests import test_hermes_selected_child_ingress as ingress
from tests import test_executive_coo_host as host_fixture
from tests import test_executive_coo_install_binding as install
from tests.test_executive_mcp_web_ceo_v3 import FakeMdm

rsa_key = ingress.rsa_key
PUBLIC = "https://mcp.mastermind-x.com/mcp"
METADATA = "https://mcp.mastermind-x.com/.well-known/oauth-protected-resource/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
PRIMARY = "https://executive.example.test/mcp"
PRIMARY_METADATA = "https://executive.example.test/.well-known/oauth-protected-resource"
NATIVE = HERMES_NATIVE_PRINCIPAL_PROFILE_ID


def _unused(*args, **kwargs):
    raise AssertionError("unrelated CEO handler must not run")


def _builder(settings):
    return server.build_web_ceo_v3_with_coo_mcp_app(
        settings.executive, coo_settings=settings, audit_sink=ingress.app_fixture.Sink(),
        mdm_reader=FakeMdm(), session_target_projector=_unused,
        session_reply_handler=_unused, session_summon_handler=_unused)


async def _public_settings(host, rsa_key):
    old, token = await ingress._installed_app(host, rsa_key, socket_path=host.socket)
    primary = AppPolicies(*(dataclasses.replace(policy, resource=PRIMARY,
        resource_metadata_url=PRIMARY_METADATA)
        for policy in (old.executive.policies.read, old.executive.policies.submit)))
    public = AppPolicies(*(dataclasses.replace(policy, resource=PUBLIC,
        resource_metadata_url=METADATA) for policy in (primary.read, primary.submit)))
    executive = dataclasses.replace(old.executive, policies=primary, public_policies=public)
    coo_policy = dataclasses.replace(old.policy, resource=PUBLIC, resource_metadata_url=METADATA)
    host.authority_config["policy"]["resource_metadata_url"] = METADATA
    native = host.host.source._registry_loader().resolve(NATIVE)
    host.authority_config["missions"][0].update(
        capability_profile_id=NATIVE, capability_profile_digest=native.profile_digest)
    facts = CooFactsClient(host.socket)
    return dataclasses.replace(old, executive=executive, policy=coo_policy,
        authority_provider=facts.authority, mission_provider=facts.mission,
        public_mcp=True), token


@asynccontextmanager
async def _public_control(tmp_path, rsa_key, monkeypatch):
    caches = []
    def public_cache(policy):
        cache = ingress.fixture._FakeJwksCache(rsa_key)
        caches.append((policy.resource, cache))
        return cache
    monkeypatch.setattr(gateway, "_default_jwks_cache", public_cache)
    with tempfile.TemporaryDirectory(prefix="mmx-c39-", dir="/tmp") as directory:
        async with ingress._control(tmp_path, Path(directory), name="native-public-coo") as host:
            settings, token = await _public_settings(host, rsa_key)
            app = _builder(settings)
            # Match the installed uvicorn receiver. Caddy sends loopback Host
            # for MCP POST, public Host for metadata, and a fixed HTTPS scheme.
            receiving = ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"])
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=receiving, client=("127.0.0.1", 43123)),
                    base_url="http://127.0.0.1",
                    headers={"x-forwarded-proto": "https"}) as client:
                    yield host, settings, token, client, caches


def _request(token, *, path="/mcp/coo", headers=None, name="tools/list"):
    actual = {"authorization": "Bearer " + token,
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-06-18"}
    actual.update(headers or {})
    return path, dict(headers=actual,
        json={"jsonrpc": "2.0", "id": 17, "method": name})


def test_signed_native_public_mcp_claims_once_and_reads_its_original(tmp_path, rsa_key, monkeypatch):
    async def exercise():
        async with _public_control(tmp_path, rsa_key, monkeypatch) as (host, settings, token, client, caches):
            assert settings.executive.policies.read.resource == PRIMARY
            assert settings.executive.public_policies.read.resource == PUBLIC
            core = CooApp(settings, ingress.app_fixture.Sink())
            assert core.authenticator._jwks_cache is not settings.executive.jwks_cache
            assert any(resource == PUBLIC and cache is core.authenticator._jwks_cache
                for resource, cache in caches)
            command = ingress._real_command(host.work)
            first = await ingress._mcp_call(client, token, "mmx_delegate",
                {"action": "selected_child_submit", "command": command})
            assert first["state"] in {"ACTIVE", "COMPLETED"}, first
            assert first["job_id"] == host.work.job_id
            assert first["target_digest"] == host.target.material_digest()
            assert first["live_submit"] is True and first["attempt_id"]
            assert host.service.runtime.attempts.get_attempt(first["attempt_id"]).job_id == host.work.job_id
            for action in ("selected_child_status", "selected_child_submit"):
                repeated = await ingress._mcp_call(client, token, "mmx_delegate",
                    {"action": action, "command": command})
                assert repeated["attempt_id"] == first["attempt_id"], repeated
                assert repeated["target_digest"] == first["target_digest"]
                assert host.service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1
            # Closing fresh mission admission keeps authorized original reads.
            host.authority_config["missions"][0]["enabled"] = False
            observed = await ingress._mcp_call(client, token, "mmx_delegate",
                {"action": "selected_child_status", "command": command})
            assert observed["attempt_id"] == first["attempt_id"]
            assert host.service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1
    asyncio.run(exercise())


def test_public_receiver_preserves_exact_role_audience_and_binding(tmp_path, rsa_key, monkeypatch):
    async def exercise():
        async with _public_control(tmp_path, rsa_key, monkeypatch) as (host, settings, token, client, _):
            policy = settings.policy
            claims = dict(scope=" ".join(COO_SCOPES), iss=policy.issuer, aud=PUBLIC,
                sub="c29-selected-child-subject", client_id=ingress.CLIENT)
            faults = [
                {"scope": "mastermind.executive.read"},
                {"scope": "mastermind.executive.read mastermind.executive.intent.submit"},
                {"scope": "mastermind.executive.read mastermind.executive.intent.submit mastermind.executive.coo.act"},
                {"aud": PRIMARY}, {"aud": [PUBLIC]}, {"aud": "https://other.example.test/mcp"},
                {"client_id": "f" * 64}, {"sub": "foreign-native-subject"},
                {"iss": "https://other-issuer.example.test"},
            ]
            for fault in faults:
                bad = ingress.fixture._token(rsa_key, **(claims | fault))
                path, kwargs = _request(bad)
                response = await client.post(path, **kwargs)
                assert response.status_code in (401, 403), (fault, response.text)
            path, kwargs = _request(token)
            assert (await client.post(path, **kwargs)).status_code == 200
            # The COO token is never accepted at the CEO public endpoint.
            path, kwargs = _request(token, path="/mcp")
            assert (await client.post(path, **kwargs)).status_code in (401, 403)
            for path in ("/mcp/coo/", "/mcp/coo?extra=1", "/mcp/%63oo"):
                target, kwargs = _request(token, path=path)
                assert (await client.post(target, **kwargs)).status_code == 404
            assert (await client.get("/mcp/coo")).status_code == 404
            for headers in ({"host": "other.example.test"}, {"origin": "https://other.example.test"}):
                path, kwargs = _request(token, headers=headers)
                assert (await client.post(path, **kwargs)).status_code in (400, 403, 421)
            assert host.service.runtime.jobs.get_job(host.work.job_id).attempt_count == 0
    asyncio.run(exercise())


def test_shared_public_metadata_has_union_without_widening_verifiers(tmp_path, rsa_key, monkeypatch):
    async def exercise():
        async with _public_control(tmp_path, rsa_key, monkeypatch) as (host, settings, token, client, _):
            response = await client.get(METADATA_PATH, headers={"host": "mcp.mastermind-x.com"})
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.json()["resource"] == PUBLIC
            assert set(response.json()["scopes_supported"]) == {
                "mastermind.executive.read", "mastermind.executive.intent.submit",
                "mastermind.executive.coo.act"}
            for headers in (
                {"host": "other.example.test"},
                {"host": "mcp.mastermind-x.com", "origin": "https://other.example.test"},
                {"host": "mcp.mastermind-x.com", "x-forwarded-proto": "http"},
            ):
                assert (await client.get(METADATA_PATH, headers=headers)).status_code == 403
            assert (await client.get(METADATA_PATH, headers=[
                ("host", "mcp.mastermind-x.com"), ("host", "other.example.test")])).status_code == 403
            for path in ("/.well-known/oauth-protected-resource",
                         "/.well-known/oauth-protected-resource/mcp/coo",
                         METADATA_PATH + "?extra=1"):
                assert (await client.get(path, headers={"host": "mcp.mastermind-x.com"})).status_code == 404
            with pytest.raises(ValueError):
                server.build_coo_mcp_app(settings, audit_sink=ingress.app_fixture.Sink())
            with pytest.raises(ValueError):
                server.build_web_ceo_v2_with_coo_mcp_app(settings.executive,
                    coo_settings=settings, audit_sink=ingress.app_fixture.Sink())
            with pytest.raises(ValueError):
                dataclasses.replace(settings, public_mcp=False)
    asyncio.run(exercise())


def test_public_submit_keeps_uncertainty_after_late_binding_revocation(tmp_path, rsa_key, monkeypatch):
    async def exercise():
        async with _public_control(tmp_path, rsa_key, monkeypatch) as (host, settings, token, client, _):
            original = CeoIngressClient.send_frame
            sends = []
            async def revoke(client_owner, path, frame):
                result = await original(client_owner, path, frame)
                if frame.get("schema") == ingress.SELECTED_CHILD_FRAME_SCHEMA:
                    sends.append(frame)
                    binding = settings.load_binding()
                    binding.update(enabled=False, binding=None)
                return result
            monkeypatch.setattr(CeoIngressClient, "send_frame", revoke)
            command = ingress._real_command(host.work)
            result = await ingress._mcp_call(client, token, "mmx_delegate",
                {"action": "selected_child_submit", "command": command})
            assert result["state"] == "EFFECT_UNKNOWN", result
            assert result["live_submit"] is None and result["command_id"] == command
            assert len(sends) == 1
            assert host.service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1
    asyncio.run(exercise())


def test_two_installed_bindings_join_their_own_missions_and_profiles(tmp_path):
    host, raw, first, _ = host_fixture.setup(tmp_path)
    original = copy.deepcopy(raw["binding"]["binding"])
    native = dict(original, client_ref="4" * 64, permission_digest="5" * 64)
    raw["binding"] = {"schema": COO_BINDING_SCHEMA_V2, "enabled": True,
        "bindings": sorted([original, native], key=_digest)}
    registry = host.source._registry_loader()
    raw["missions"].append(dict(raw["missions"][0], work_ref="WS:NATIVE-COO",
        principal_binding_digest=_digest(native), capability_profile_id=NATIVE,
        capability_profile_digest=registry.resolve(NATIVE).profile_digest))
    native_frame = {key: value for key, value in native.items() if key != "permission_digest"}
    assert host.source.for_principal(first, ingress.WORK_REF)[0]["capability_profile_id"] == host_fixture.PRINCIPAL_PROFILE
    assert host.source.for_principal(native_frame, "WS:NATIVE-COO")[0]["capability_profile_id"] == NATIVE
    assert host.source.snapshot("WS:NATIVE-COO")[1].principal_binding_digest == _digest(native)
    for frame, work in ((first, "WS:NATIVE-COO"), (native_frame, ingress.WORK_REF)):
        with pytest.raises(ValueError):
            host.source.for_principal(frame, work)
    with pytest.raises(ValueError):
        host.source.snapshot("WS:NATIVE-COO", principal_binding_digest=_digest(original))
    raw["missions"].append(dict(raw["missions"][-1]))
    with pytest.raises(ValueError):
        host.source.snapshot("WS:NATIVE-COO")


@pytest.mark.parametrize("fault", ["missing", "disabled"])
def test_installed_native_profile_must_be_current_and_enabled(tmp_path, fault):
    host, raw, first, policy_path = host_fixture.setup(tmp_path)
    native = host.source._registry_loader().resolve(NATIVE)
    raw["missions"][0].update(capability_profile_id=NATIVE,
        capability_profile_digest=native.profile_digest)
    policy = json.loads(policy_path.read_text())
    profiles = policy["profiles"]
    if isinstance(profiles, list):
        selected = next(row for row in profiles if row["profile_id"] == NATIVE)
        if fault == "missing":
            profiles.remove(selected)
        else:
            selected["enabled"] = False
    else:
        if fault == "missing":
            del profiles[NATIVE]
        else:
            profiles[NATIVE]["enabled"] = False
    policy_path.write_text(json.dumps(policy))
    with pytest.raises(ValueError):
        host.source.for_principal(first, ingress.WORK_REF)


def test_installed_public_parser_and_settings_use_the_explicit_public_pair(tmp_path):
    host, coo, _, _ = host_fixture.setup(tmp_path)
    raw = install.base_document()
    for policy in raw["policies"].values():
        if isinstance(policy, dict):
            policy.update(resource=PRIMARY, resource_metadata_url=PRIMARY_METADATA)
    coo["policy"]["resource_metadata_url"] = METADATA
    raw.update(coo=coo, executive_mcp_profile="web_ceo_v3", public_mcp_resource=PUBLIC)
    assert entry.validate_document(raw) is raw
    policies = gateway.load_app_policies(raw["policies"])
    from integrations.mastermind_executive_app.app import AppSettings
    executive = AppSettings(policies=policies, mastermind_root=tmp_path,
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=raw["ceo_ingress_socket_path"],
        read_from_ceo_ingress=True, public_policies=entry.build_public_policies(raw, policies))
    configured = entry.build_installed_coo_settings(raw, tmp_path / raw["release_sha"],
        tmp_path / "config.json", executive)
    assert configured.public_mcp is True
    assert configured.policy.resource == PUBLIC
    assert configured.policy.resource_metadata_url == METADATA
    assert configured.executive.policies == policies
    for fault in ("wrong_resource", "wrong_metadata", "wrong_profile"):
        bad = copy.deepcopy(raw)
        if fault == "wrong_resource":
            bad["coo"]["policy"]["resource"] = PRIMARY
        elif fault == "wrong_metadata":
            bad["coo"]["policy"]["resource_metadata_url"] = PRIMARY_METADATA
        else:
            bad["executive_mcp_profile"] = "web_ceo_v2"
        with pytest.raises(ValueError):
            entry.validate_document(bad)
