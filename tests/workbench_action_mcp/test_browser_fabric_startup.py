from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path
import sys
import time

import httpx
import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa

import integrations.workbench_action_mcp.service as service
from integrations.business_mcp_auth.contracts import subject_digest
from integrations.business_mcp_auth.audit import DurableAuthAuditSink
from integrations.mastermind_browser_plugin.ingress import INTERNAL_METADATA_PATH
from tests.test_business_mcp_auth_integration import _jwks, _rsa_jwk
from tests.workbench_action_mcp.test_browser_service_composition import _browser_block
from tests.workbench_action_mcp.test_service import _document

RESOURCE = "https://browser.example/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
SUBJECT = "browser-startup-fixture"


def _v3_document(tmp_path: Path):
    document, _, _ = _document(tmp_path)
    document["schema"] = service.SERVICE_SCHEMA_V3
    block = _browser_block(tmp_path)
    root = Path(__file__).resolve().parents[2]
    block["source_root"] = str(root)
    block["python_executable"] = sys.executable
    block["tool_catalog_file"] = str(
        root / "research" / "evidence" / "claude_browser_mcp_tools_0_0_79.json"
    )
    document["browser"] = block
    policy = json.loads(Path(document["policy_file"]).read_text())
    policy.update(
        policy_id="fixture.browser.startup",
        resource=RESOURCE,
        resource_metadata_url="https://browser.example" + METADATA_PATH,
        required_scopes=["browser.control"],
        allowed_subject_digests=[subject_digest(issuer=policy["issuer"], subject=SUBJECT)],
    )
    policy_path = tmp_path / "browser-policy.json"
    policy_path.write_text(json.dumps(policy))
    os.chmod(policy_path, 0o600)
    document["browser_fabric_policy_file"] = str(policy_path)
    browser_audit = tmp_path / "browser-audit"
    browser_audit.mkdir(mode=0o700)
    document["browser_fabric_audit_directory"] = str(browser_audit)
    return document, policy


def test_v3_requires_explicit_closed_policy_configuration(tmp_path):
    document, _ = _v3_document(tmp_path)
    config = service.parse_service_config(document)
    assert config.browser_fabric_policy_file == document["browser_fabric_policy_file"]
    for invalid in (
        {k: v for k, v in document.items() if k != "browser_fabric_policy_file"},
        {**document, "browser_fabric_policy_file": "relative.json"},
        {**document, "browser_fabric_policy_file": None},
        {**document, "anonymous_browser": True},
        {k: v for k, v in document.items() if k != "browser_fabric_audit_directory"},
        {**document, "browser_fabric_audit_directory": document["audit_directory"]},
        {**document, "schema": service.SERVICE_SCHEMA_V2},
        {k: v for k, v in document.items() if k != "browser"},
    ):
        with pytest.raises(service.ServiceConfigurationError):
            service.parse_service_config(invalid)


@pytest.mark.parametrize("change", [
    {"required_scopes": ["workbench.action"]},
    {"resource": "https://workbench-action.example/mcp"},
    {"resource_metadata_url": "https://other.example" + METADATA_PATH},
    {"resource_metadata_url": "https://browser.example/mcp"},
])
def test_v3_refuses_wrong_audience_scope_or_metadata_composition(tmp_path, change):
    document, policy = _v3_document(tmp_path)
    policy.update(change)
    Path(document["browser_fabric_policy_file"]).write_text(json.dumps(policy))
    config = service.parse_service_config(document)

    async def exercise():
        runtime = await service.create_runtime(config)
        try:
            with pytest.raises(service.ServiceConfigurationError):
                service.build_service_app(runtime, config, service.ServiceState())
        finally:
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_configured_auth_cannot_be_replaced_by_embedding_hook(tmp_path):
    document, _ = _v3_document(tmp_path)
    config = service.parse_service_config(document)

    async def exercise():
        runtime = await service.create_runtime(config)
        try:
            with pytest.raises(service.ServiceConfigurationError):
                service.build_service_app(
                    runtime,
                    config,
                    service.ServiceState(),
                    browser_fabric_authenticate=lambda request: None,
                    browser_fabric_auth_challenge="Bearer fixture",
                )
        finally:
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_actual_startup_composes_oauth_metadata_and_browser_mcp(tmp_path, monkeypatch):
    document, policy = _v3_document(tmp_path)
    config = service.parse_service_config(document)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    keys = _jwks(_rsa_jwk(private_key, kid="browser-fixture"))
    fetched = []
    audit_events = []
    emit = DurableAuthAuditSink.emit

    def record_audit(sink, event):
        audit_events.append((event.code, event.accepted))
        return emit(sink, event)

    monkeypatch.setattr(DurableAuthAuditSink, "emit", record_audit)

    class Fetcher:
        def __init__(self, selected):
            self.policy = selected

        async def fetch(self, *, url, timeout_seconds, max_bytes):
            assert url == policy["jwks_uri"]
            fetched.append(url)
            return keys

    monkeypatch.setattr(service, "HttpxJwksFetcher", Fetcher)
    reserve = service.reserve_loopback_socket
    monkeypatch.setattr(
        service, "reserve_loopback_socket",
        lambda selected: reserve(
            dataclasses.replace(selected, bind_port=0), _allow_ephemeral_for_test=True
        ),
    )
    now = int(time.time())

    def bearer(audience=RESOURCE, scope="browser.control"):
        return "Bearer " + jwt.encode(
            {
                "iss": policy["issuer"], "sub": SUBJECT, "aud": audience,
                "iat": now, "nbf": now, "exp": now + 300,
                "scope": scope, "client_id": "browser-startup-fixture",
            },
            private_key, algorithm="RS256",
            headers={"kid": "browser-fixture", "typ": "at+jwt"},
        )

    observed = []

    async def exercise_server(server, sockets):
        assert len(sockets) == 1
        app = server.config.app
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=f"http://{config.incoming_authority}",
            ) as client:
                assert (await client.get("/readyz")).status_code == 200
                workbench_metadata = await client.get(METADATA_PATH)
                assert workbench_metadata.status_code == 200
                assert workbench_metadata.json()["resource"] == "https://workbench-action.example/mcp"
                assert workbench_metadata.json()["scopes_supported"] == ["workbench.action"]
                metadata = await client.get(INTERNAL_METADATA_PATH)
                assert metadata.status_code == 200
                assert metadata.json() == {
                    "resource": RESOURCE,
                    "authorization_servers": policy["authorization_servers"],
                    "scopes_supported": ["browser.control"],
                }
                assert (
                    await client.get(INTERNAL_METADATA_PATH, headers={"Host": "evil.example"})
                ).status_code == 421
                assert (
                    await client.get(INTERNAL_METADATA_PATH, headers={"Origin": "https://evil.example"})
                ).status_code == 403
                init = {
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25", "capabilities": {},
                        "clientInfo": {"name": "browser-startup-fixture", "version": "1"},
                    },
                }
                denied = await client.post("/browser-fabric", json=init)
                assert denied.status_code == 401
                assert denied.headers["www-authenticate"] == (
                    'Bearer resource_metadata="https://browser.example' + METADATA_PATH + '"'
                )
                headers = {
                    "Accept": "application/json, text/event-stream",
                    "Authorization": bearer(),
                }
                for invalid in (
                    "Bearer bad.token.value",
                    bearer("https://workbench-action.example/mcp"),
                    bearer(scope="workbench.action"),
                ):
                    refused = await client.post(
                        "/browser-fabric", json=init,
                        headers={**headers, "Authorization": invalid},
                    )
                    assert refused.status_code == 401
                initialized = await client.post("/browser-fabric", json=init, headers=headers)
                assert initialized.status_code == 200, audit_events
                assert initialized.json()["result"]["serverInfo"]["name"] == "mastermind-browser"
                tools = await client.post(
                    "/browser-fabric", headers=headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                )
                assert len(tools.json()["result"]["tools"]) == 7
                fleet = await client.post(
                    "/browser-fabric", headers=headers,
                    json={
                        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "browser_fleet", "arguments": {"limit": 10}},
                    },
                )
                result = fleet.json()["result"]["structuredContent"]
                assert result["is_error"] is False, result
                assert result["data"]["browsers"] == []
                observed.append("authenticated-fleet")

    failures = []

    async def checked_serve(server, sockets):
        try:
            await exercise_server(server, sockets)
        except BaseException as error:
            failures.append(error)
            raise

    monkeypatch.setattr(uvicorn.Server, "serve", checked_serve)
    code = asyncio.run(service.run_service(config))
    if failures:
        raise failures[0]
    assert code == 0
    assert observed == ["authenticated-fleet"]
    assert fetched == [policy["jwks_uri"]]
    browser_events = [
        json.loads(line) for line in
        (Path(document["browser_fabric_audit_directory"]) / "auth-audit.jsonl").read_text().splitlines()
    ]
    assert browser_events
    assert {event["policy_id"] for event in browser_events} == {"fixture.browser.startup"}
    assert any(event["accepted"] for event in browser_events)
    assert (Path(document["audit_directory"]) / "auth-audit.jsonl").read_text() == ""
