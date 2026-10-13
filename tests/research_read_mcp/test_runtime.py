"""Deployment refusal and current-grant composition proof, without a listener."""
from __future__ import annotations

from dataclasses import replace
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import httpx
import pytest

from integrations.research_read_mcp import CONTRACT
from integrations.research_read_mcp.contracts import ContractViolation
from integrations.research_read_mcp.runtime import (
    CurrentGrantOwner, DEPLOYMENT_SCHEMA, READ_PORT_CONTRACT, RuntimeRefused,
    compose_runtime, load_deployment, parse_deployment, read_secure_json,
    verify_git_release,
)
from tests.research_read_mcp.test_app import CLOCK, Harness, KNOWN_REPORT, _assert_error, _result


def document():
    return {
        "schema": DEPLOYMENT_SCHEMA, "mode": "production",
        "mastermind_release": "/opt/mastermind-research/releases/" + "a" * 40,
        "mastermind_commit": "a" * 40, "mastermind_tree": "b" * 40,
        "macro_release": "/opt/macro-research/releases/" + "c" * 40,
        "macro_commit": "c" * 40, "macro_tree": "d" * 40,
        "bind_host": "127.0.0.1", "bind_port": 8767,
        "policy_path": "/etc/mastermind/research-policy.json",
        "grant_path": "/etc/mastermind/research-grant.json",
        "policy_id": "mastermind-research-read-v1",
        "server_contract": CONTRACT, "read_port_contract": READ_PORT_CONTRACT,
        "allowed_hosts": ["127.0.0.1", "127.0.0.1:8767"], "allowed_origins": [],
    }


def parsed(**changes):
    data = document()
    data.update(changes)
    return parse_deployment(json.dumps(data).encode())


@pytest.mark.parametrize("changes", [
    {"unknown": True}, {"bind_port": True}, {"bind_port": 0}, {"bind_port": 65536},
    {"bind_host": "0.0.0.0"}, {"bind_host": "[::]"}, {"mode": "local"},
    {"mastermind_commit": "A" * 40}, {"macro_tree": "a" * 39},
    {"macro_release": "/opt/macro"}, {"grant_path": "relative"},
    {"policy_path": "/etc/mastermind/../policy.json"},
    {"allowed_hosts": []}, {"allowed_hosts": ["*.example.com"]},
    {"allowed_origins": ["http://example.com"]}, {"allowed_hosts": ["x", "x"]},
    {"read_port_contract": "wrong"}, {"server_contract": "wrong"},
])
def test_closed_deployment_refuses(changes):
    with pytest.raises(RuntimeRefused, match="^RUNTIME_CONFIG_REFUSED$"):
        parsed(**changes)


def test_duplicate_nonfinite_and_record():
    assert parsed().bind_port == 8767
    raw = json.dumps(document())
    for bad in (raw.replace('"bind_port": 8767', '"bind_port": 8767,"bind_port": 8767'),
                raw.replace('"bind_port": 8767', '"bind_port": NaN'), "[]"):
        with pytest.raises(RuntimeRefused):
            parse_deployment(bad.encode())


def test_runtime_import_does_not_open_spawn_or_connect():
    script = """
import os, subprocess, socket
def forbidden(*args, **kwargs):
    raise AssertionError('import attempted an effect')
os.open = forbidden
subprocess.run = forbidden
socket.socket = forbidden
import integrations.research_read_mcp.runtime
import integrations.research_read_mcp.release_identity
"""
    subprocess.run([sys.executable, "-B", "-c", script], check=True, capture_output=True,
                   cwd=Path(__file__).resolve().parents[2], timeout=15)


def test_secure_config_owner_mode_symlink_size_and_identity(tmp_path):
    root = tmp_path.resolve()
    path = root / "deployment.json"
    path.write_text(json.dumps(document()))
    path.chmod(0o600)
    assert load_deployment(str(path), expected_owner_uid=os.geteuid()).macro_commit == "c" * 40
    path.chmod(0o640)
    with pytest.raises(RuntimeRefused):
        read_secure_json(str(path), expected_owner_uid=os.geteuid())
    path.chmod(0o600)
    with pytest.raises(RuntimeRefused):
        read_secure_json(str(path), expected_owner_uid=os.geteuid() + 1)
    link = root / "link"
    link.symlink_to(path)
    with pytest.raises(RuntimeRefused):
        read_secure_json(str(link), expected_owner_uid=os.geteuid())
    with pytest.raises(RuntimeRefused):
        read_secure_json(str(path), expected_owner_uid=os.geteuid(), maximum=4)
    real_read = os.read

    def replace_during_read(fd, size):
        raw = real_read(fd, size)
        replacement = root / "replacement"
        replacement.write_bytes(raw)
        replacement.chmod(0o600)
        replacement.replace(path)
        return raw

    with patch("integrations.research_read_mcp.runtime.os.read", side_effect=replace_during_read):
        with pytest.raises(RuntimeRefused):
            read_secure_json(str(path), expected_owner_uid=os.geteuid())


def test_checkout_pin_and_dirty_or_dotenv_refusal(tmp_path):
    # Production identity checks are real Git calls against a synthetic checkout.
    root = tmp_path.resolve() / ("a" * 40)
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "fixture"],
                   check=True)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).decode().strip()
    final = root.with_name(commit)
    root.rename(final)
    with patch.dict(os.environ, {"GIT_DIR": "/nonexistent-fixture-dir"}):
        verify_git_release(str(final), commit, tree)
    for wrong_commit, wrong_tree in (("e" * 40, tree), (commit, "f" * 40)):
        with pytest.raises(RuntimeRefused, match="RELEASE_IDENTITY_REFUSED"):
            verify_git_release(str(final), wrong_commit, wrong_tree)
    (final / "dirty").write_text("fixture")
    with pytest.raises(RuntimeRefused):
        verify_git_release(str(final), commit, tree)
    (final / "dirty").unlink()
    (final / ".env").write_text("synthetic")
    with pytest.raises(RuntimeRefused):
        verify_git_release(str(final), commit, tree)


def grant_document(policy_id, digest, *, quote=100, expires=CLOCK + 100):
    return {"schema": "mastermind.research_read_mcp.grant.v1", "grant_id": "grant.fixture",
            "policy_id": policy_id, "entries": [{"subject_digest": digest,
            "content_classes": ["catalog_metadata", "report_text", "evidence_passage"],
            "quote_limit_chars": quote, "expires_at": expires}]}


def write_grant(path, policy_id, digest, **changes):
    path.write_text(json.dumps(grant_document(policy_id, digest, **changes)))
    path.chmod(0o600)


def test_same_secure_owner_observes_quote_change_revocation_and_caller(tmp_path):
    path = tmp_path.resolve() / "grant.json"
    digest = hashlib.sha256(b"synthetic-principal").hexdigest()
    write_grant(path, document()["policy_id"], digest)
    owner = CurrentGrantOwner(parsed(grant_path=str(path)), clock=lambda: CLOCK, owner_uid=os.geteuid())
    assert owner.quote_limit(digest) == 100
    write_grant(path, document()["policy_id"], digest, quote=7)
    assert owner.quote_limit(digest) == 7
    with pytest.raises(ContractViolation) as refusal:
        owner.quote_limit("f" * 64)
    assert refusal.value.code == "NOT_ENTITLED"
    write_grant(path, document()["policy_id"], digest, expires=CLOCK)
    with pytest.raises(ContractViolation):
        owner.quote_limit(digest)


def test_composes_actual_app_routes_and_current_grant(tmp_path):
    asyncio.run(_compose_app_routes_and_current_grant(tmp_path))


async def _compose_app_routes_and_current_grant(tmp_path):
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    def mount_health_routes(app, health, ready):
        async def health_endpoint(_request):
            body, status = health()
            return JSONResponse(body, status_code=status)

        async def ready_endpoint(_request):
            body, status = ready()
            return JSONResponse(body, status_code=status)

        app.router.routes.extend([Route("/healthz", health_endpoint), Route("/readyz", ready_endpoint)])

    harness = Harness()
    grant_path = tmp_path.resolve() / "grant.json"
    write_grant(grant_path, harness.policy.policy_id, harness.subjects["reader"])
    deployment = parsed(grant_path=str(grant_path), policy_id=harness.policy.policy_id)
    pins = []
    ready_state = [False]
    app = compose_runtime(
        deployment, release_verifier=lambda *identity: pins.append(identity),
        policy_loader=lambda _path: harness.policy,
        authenticator_factory=lambda _policy: harness.auth,
        read_service_factory=lambda _config: harness,
        adapter_factory=lambda service, quote, _config: service._port,
        context_factory=harness._context, readiness=lambda _service: ready_state[0],
        mount_health_routes=mount_health_routes,
        audit_sink=harness.audit, clock=lambda: CLOCK, owner_uid=os.geteuid(),
    )
    assert len(pins) == 2
    assert {route.path for route in app.routes} >= {"/healthz", "/readyz", "/mcp/research/v1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        assert (await client.get("/healthz")).json() == {"ok": True}
        response = await client.get("/readyz")
        assert response.status_code == 503 and response.json() == {"ready": False}
        ready_state[0] = True
        assert (await client.get("/readyz")).json() == {"ready": True}
        assert (await client.post("/mcp/research/v1", json={})).status_code == 401
    # Real principal projection comes from the existing verified authenticator.
    principal = await harness.auth.verify_authorization_header("Bearer " + harness.token(), now=CLOCK)
    from integrations.business_mcp_auth.principal_projection import principal_projection
    projection = principal_projection(principal)
    owner = app.state.research_grant_owner
    assert owner.entitlement(projection).quote_limit_chars == 100
    harness.app = app
    await harness.start()
    try:
        for tool, arguments in (
            ("research_status", {}), ("research_search", {"query": "rates"}),
            ("research_fetch", {"report_id": KNOWN_REPORT}),
            ("research_find_evidence", {"claim": "rates", "report_ids": [KNOWN_REPORT]}),
        ):
            payload = _result(await harness.call(tool, arguments, token=harness.token()))
            assert payload["isError"] is False
        assert harness.port_calls == 4
        write_grant(grant_path, harness.policy.policy_id, harness.subjects["reader"], expires=CLOCK)
        _assert_error(await harness.call("research_fetch", {"report_id": KNOWN_REPORT},
                                         token=harness.token()), "NOT_ENTITLED")
        assert harness.port_calls == 4
    finally:
        await harness.stop()
    write_grant(grant_path, harness.policy.policy_id, harness.subjects["reader"], expires=CLOCK)
    assert owner.entitlement(projection) is None
    with pytest.raises(RuntimeRefused):
        compose_runtime(replace(deployment, bind_host="0.0.0.0"),
                        authenticator_factory=lambda _: harness.auth,
                        read_service_factory=lambda _: harness, adapter_factory=lambda *_: harness._port,
                        context_factory=harness._context, readiness=lambda _: True,
                        mount_health_routes=mount_health_routes,
                        audit_sink=harness.audit, clock=lambda: CLOCK, owner_uid=os.geteuid())
