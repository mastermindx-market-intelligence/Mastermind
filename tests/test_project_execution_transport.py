"""Signed project execution requests across HTTP, the private socket and Runtime.

Provider dispatch and repository observations are inert fixture seams. This tests
the actual JWT/resource policies, nominal App owner, peer and request lifetime;
it does not claim an installed provider START.
"""
import asyncio
import copy
import dataclasses
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time

import httpx
import jwt
import pytest

from common import project_execution_private_contract as wire
from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp.server import AuditedWorkspaceApp
from integrations.mastermind_executive_app.direct_native import DirectNativeResultClient
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from integrations.mastermind_executive_app.os_transport import OsExecutiveTransportApp
from test_mastermind_executive_app_asgi import rsa_key, _FakeJwksCache, KID
from tests.test_project_execution_factory import fixture


class Audit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def composition(tmp_path, monkeypatch, key):
    factory, principal, args, armed, prepared = fixture(tmp_path, monkeypatch)
    planning = factory.planning
    clock = [int(time.time())]
    planning.clock = lambda: clock[0]
    audit = Audit()

    def pair(policy):
        auth = JwtAuthenticator(policy=policy, jwks_cache=_FakeJwksCache(key))
        verifier = MastermindTokenVerifier(
            authenticator=auth, policy=policy, now=lambda: clock[0], audit_sink=audit)
        return auth, verifier

    auth, verifier = pair(planning.policies.submit)
    wauth, wverifier = pair(planning.workspace_policy)

    async def inner(*_):
        raise AssertionError("no generic forwarding")

    workspace = AuditedWorkspaceApp(inner, wverifier, authenticator=wauth,
        authorize_principal=planning._authorize_workspace)
    app = dataclasses.replace(factory.app_binding,
        project_execution_provider_factory=lambda runtime:
            wire.ProjectExecutionIngressOwner(factory.handle_frame))
    planning.app_binding = factory.app_binding = app
    factory.service._ceo_ingress_app_binding = app

    def bearer(policy, **overrides):
        claims = dict(iss=policy.issuer, sub="inert-chairman", aud=policy.resource,
            client_id="inert-client", scope=" ".join(policy.required_scopes),
            iat=clock[0]-5, nbf=clock[0]-5, exp=clock[0]+600)
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID, "typ": "at+jwt"})

    return factory, args, clock, audit, prepared, auth, verifier, workspace, bearer, armed


async def exercise(parts, action):
    factory, args, clock, audit, prepared, auth, verifier, workspace, bearer, _ = parts
    runtime = factory.service.runtime
    directory = runtime.store.path.parent
    lock = directory / "executive-service.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker = directory / "executive-service.running"
    marker.write_text(json.dumps(dict(instance_id="planning-test", pid=os.getpid())))
    marker.chmod(0o600)
    custody = ServiceRuntimeNamespaceCustody(runtime=runtime, service_lock_fd=fd,
        lock_path=lock, marker_path=marker, instance_id="planning-test")
    custody.start()
    factory.service._namespace_custody = custody
    with tempfile.TemporaryDirectory(prefix="mm-exec-", dir="/tmp") as short:
        sock = Path(short) / "ceo.sock"
        server = await asyncio.start_unix_server(
            factory.service._handle_ceo_ingress_connection, path=str(sock), limit=73728)
        edge = OsExecutiveTransportApp(lambda *args: None, submit_authenticator=auth,
            submit_verifier=verifier, clock=lambda: clock[0], workspace_app=workspace,
            direct_result_client=DirectNativeResultClient(sock, CeoIngressClient(read_timeout=5)))
        tokens = (bearer(factory.planning.policies.submit), bearer(factory.planning.workspace_policy))
        headers = [("authorization", "Bearer " + tokens[0]),
            ("x-mastermind-workspace-authorization", "Bearer " + tokens[1])]
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=edge),
                    base_url="https://mcp.mastermind-x.com") as client:
                await action(client, headers, copy.deepcopy(args), tokens)
        finally:
            server.close()
            await server.wait_closed()
            tasks = list(factory.service._ceo_ingress_tasks)
            if tasks:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
            custody.close()
            os.close(fd)


def test_signed_preview_submit_and_status_preserve_one_original_operation(tmp_path, monkeypatch, rsa_key):
    parts = composition(tmp_path, monkeypatch, rsa_key)
    factory = parts[0]

    async def action(client, headers, args, tokens):
        preview = {key: args[key] for key in ("work_ref", "expected_context")}
        preview["operation_key"] = "mmos-project-preview-" + "b" * 40
        response = await client.post("/os/executive/project-execution/preview",
            headers=headers, json={"arguments": preview})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["execution_state"] == "WORK_CAPABLE"
        assert factory.service.runtime.jobs.list_jobs() == [] and parts[4] == []
        first = await client.post("/os/executive/project-execution/submit",
            headers=headers, json={"arguments": args})
        assert first.status_code == 200, first.text
        root = first.json()["data"]["receipt"]["job_id"]
        original = {key: args[key] for key in ("operation_key", "work_ref")}
        status = await client.post("/os/executive/project-execution/status",
            headers=headers, json={"arguments": original})
        assert status.status_code == 200, status.text
        assert status.json()["data"]["receipt"]["job_id"] == root
        again = await client.post("/os/executive/project-execution/submit",
            headers=headers, json={"arguments": args})
        assert again.status_code == 200, again.text
        assert again.json()["data"]["receipt"]["job_id"] == root
        assert parts[4] == [root] and len(factory.service.runtime.jobs.list_jobs()) == 1
        assert factory.service.runtime.attempts.list_attempts() == []
        public = repr(factory.service.runtime.store.list_events())
        assert args["handoff_text"] not in public and args["objective"] not in public
        for token in tokens:
            assert token not in first.text + status.text + again.text + public + repr(parts[3].events)

    asyncio.run(exercise(parts, action))


@pytest.mark.parametrize("change", [
    "missing-second", "duplicate-second", "duplicate-first", "wrong-resource",
    "cross-account", "cross-client", "expired-second", "no-send", "denied-read", "unarmed",
])
def test_unqualified_resources_never_admit_a_root(tmp_path, monkeypatch, rsa_key, change):
    parts = composition(tmp_path, monkeypatch, rsa_key)
    factory = parts[0]

    async def action(client, headers, args, tokens):
        if change == "missing-second":
            headers = headers[:1]
        if change == "duplicate-second":
            headers += [headers[1]]
        if change == "duplicate-first":
            headers += [headers[0]]
        overrides = {
            "wrong-resource": dict(aud=factory.planning.policies.submit.resource),
            "cross-account": dict(sub="another-account"),
            "cross-client": dict(client_id="another-client"),
            "expired-second": dict(iat=parts[2][0]-800, nbf=parts[2][0]-800, exp=parts[2][0]-100),
        }
        if change in overrides:
            token = parts[8](factory.planning.workspace_policy, **overrides[change])
            headers = [headers[0], (headers[1][0], "Bearer " + token)]
        if change == "no-send":
            token = parts[8](factory.planning.policies.submit, scope="executive.read")
            headers = [(headers[0][0], "Bearer " + token), headers[1]]
        if change == "denied-read":
            factory.planning._test_bindings[0]["profiles"]["member-0"]["enabled"] = False
        if change == "unarmed":
            parts[9][0] = False
        response = await client.post("/os/executive/project-execution/submit",
            headers=headers, json={"arguments": args})
        assert response.status_code in (401, 403, 503), response.text
        assert parts[4] == [] and factory.service.runtime.jobs.list_jobs() == []
        for token in tokens:
            assert token not in response.text + repr(parts[3].events)

    asyncio.run(exercise(parts, action))


def test_closed_http_arguments_reject_before_socket_admission(tmp_path, monkeypatch, rsa_key):
    parts = composition(tmp_path, monkeypatch, rsa_key)

    async def action(client, headers, args, _):
        cases = []
        bad = copy.deepcopy(args)
        bad["endpoint"] = "https://foreign.example"
        cases.append({"arguments": bad})
        bad = copy.deepcopy(args)
        bad["expected_context"]["record_source"]["path"] = "agentos/workstreams/WS-OTHER.md"
        cases.append({"arguments": bad})
        bad = copy.deepcopy(args)
        bad["handoff_text"] = "界" * 10923
        cases.append({"arguments": bad})
        cases.append({"arguments": args, "principal": {"forged": True}})
        cases.append({"arguments": {"operation_key": args["operation_key"], "work_ref": args["work_ref"]}})
        for body in cases:
            response = await client.post("/os/executive/project-execution/submit",
                headers=headers, json=body)
            assert response.status_code == 400, response.text
        response = await client.post("/os/executive/project-execution/retry",
            headers=headers, json={"arguments": args})
        assert response.status_code == 404
        assert parts[4] == [] and parts[0].service.runtime.jobs.list_jobs() == []

    asyncio.run(exercise(parts, action))


def test_control_requalifies_original_workspace_expiry_before_creation(tmp_path, monkeypatch, rsa_key):
    parts = composition(tmp_path, monkeypatch, rsa_key)

    async def action(client, headers, args, _):
        token = parts[8](parts[0].planning.workspace_policy, exp=parts[2][0]+1)
        headers = [headers[0], (headers[1][0], "Bearer " + token)]
        parts[0].planning.clock = lambda: parts[2][0]+2
        response = await client.post("/os/executive/project-execution/submit",
            headers=headers, json={"arguments": args})
        assert response.status_code == 403, response.text
        assert parts[4] == [] and parts[0].service.runtime.jobs.list_jobs() == []

    asyncio.run(exercise(parts, action))


def test_post_commit_failure_returns_unknown_and_reconciles_without_replaying(tmp_path, monkeypatch, rsa_key):
    parts = composition(tmp_path, monkeypatch, rsa_key)
    calls = []

    async def failed(root, operation):
        operation.require_root(root.job_id)
        calls.append(root.job_id)
        raise RuntimeError("private unavailable carrier detail")

    monkeypatch.setattr(parts[0], "_prepare_workspace", failed)

    async def action(client, headers, args, _):
        first = await client.post("/os/executive/project-execution/submit",
            headers=headers, json={"arguments": args})
        assert first.status_code == 202 and first.json()["error"]["code"] == "effect_unknown", first.text
        assert "private unavailable" not in first.text and len(calls) == 1
        status = await client.post("/os/executive/project-execution/status", headers=headers,
            json={"arguments": {key: args[key] for key in ("operation_key", "work_ref")}})
        assert status.status_code == 200 and status.json()["data"]["receipt"]["job_id"] == calls[0], status.text
        again = await client.post("/os/executive/project-execution/submit",
            headers=headers, json={"arguments": args})
        assert again.status_code == 200 and again.json()["data"]["receipt"]["job_id"] == calls[0], again.text
        assert len(calls) == 1 and len(parts[0].service.runtime.jobs.list_jobs()) == 1

    asyncio.run(exercise(parts, action))


def test_workspace_revocation_after_commit_retains_unknown_original(tmp_path, monkeypatch, rsa_key):
    parts = composition(tmp_path, monkeypatch, rsa_key)
    original = parts[0]._prepare_workspace

    async def revoke(root, operation):
        await original(root, operation)
        parts[0].planning._test_bindings[0]["profiles"]["member-0"]["enabled"] = False

    monkeypatch.setattr(parts[0], "_prepare_workspace", revoke)

    async def action(client, headers, args, _):
        first = await client.post("/os/executive/project-execution/submit",
            headers=headers, json={"arguments": args})
        assert first.status_code == 202 and first.json()["error"]["code"] == "effect_unknown", first.text
        assert len(parts[0].service.runtime.jobs.list_jobs()) == 1 and len(parts[4]) == 1
        parts[0].planning._test_bindings[0]["profiles"]["member-0"]["enabled"] = True
        status = await client.post("/os/executive/project-execution/status", headers=headers,
            json={"arguments": {key: args[key] for key in ("operation_key", "work_ref")}})
        assert status.status_code == 200 and status.json()["data"]["receipt"]["job_id"] == parts[4][0], status.text
        assert len(parts[4]) == 1

    asyncio.run(exercise(parts, action))
