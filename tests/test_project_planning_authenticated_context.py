"""Authenticated S4 context output through the existing S2 planning consumer.

JWT verification, MCP/App authorization, the collector/compiler and S2 Runtime
are production owners. Enrollment, CF2 custody and the physical worker are
explicit fixtures; the private Control callback stays in process. No Unix
socket, installed service, provider, native memory wiring or new adapter runs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest
import yaml

from common import coo_agentos_context_contract as wire
from control_plane.foreground_operation import ForegroundOperationRefusal
from integrations.executive_mcp import server
from integrations.mastermind_executive_app.coo_binding import principal_frame
from tests import test_executive_coo_agentos_context as authenticated
from tests import test_project_planning_adopted_context as planning
from tests.test_installed_agentos_context import write_record

WORK = planning.WORK
rsa_key = authenticated.rsa_key


def _authenticated_composition(tmp_path, monkeypatch, rsa_key):
    original_bound = authenticated.reader_tests.bound

    def authored_sources(macro, seen):
        # Select the same workstream in the authored source before its actual
        # Git commit/compilation; never relabel a returned bundle or receipt.
        old = seen["record"]
        record = old.with_name("WS-NEW-PROJECT.md")
        record.write_text(old.read_text().replace("key: ONE\n", "key: NEW-PROJECT\n"))
        old.unlink()
        seen["record"] = record
        path = macro / "agentos/decisions/DEC-PLAN.md"
        decision = yaml.safe_load(path.read_text().split("---", 2)[1])
        decision["affects"] = [WORK]
        decision["project_plan_adoption"]["work_ref"] = WORK
        write_record(path, decision)

    def selected_bound(root, patch, **kwargs):
        return original_bound(root, patch, source_changes=authored_sources, **kwargs)

    monkeypatch.setattr(authenticated.reader_tests, "bound", selected_bound)
    monkeypatch.setattr(authenticated, "WORK", WORK)
    auth_root = tmp_path / "authenticated"
    auth_root.mkdir()
    token, _, settings, provider, seen = authenticated.signed_components(
        auth_root, monkeypatch, rsa_key)
    app = server.build_web_ceo_v2_with_coo_mcp_app(
        settings.executive, coo_settings=settings,
        audit_sink=authenticated.app_tests.Sink())

    async def acquire():
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1") as client:
                response = await authenticated.mcp_tests.rpc(
                    client, token, "/mcp/coo", "tools/call",
                    {"name": wire.TOOL, "arguments": {"work_ref": WORK}})
                assert response.status_code == 200, response.text
                result = response.json()["result"]
                assert result.get("isError") is not True
                payload = json.loads(result["content"][0]["text"])
                assert payload["ok"] is True, payload
                return payload["data"]

    value = asyncio.run(acquire())
    principal = asyncio.run(authenticated.app_tests.JwtAuthenticator(
        policy=settings.policy, jwks_cache=settings.executive.jwks_cache
    ).verify_token(token, now=authenticated.app_tests.fixture.NOW))
    frame = authenticated.frame_for(provider, principal_frame(principal), work=WORK)
    raw, receipt = wire.validate_result(
        value, expected_context=frame["principal_context"],
        capability_profile_digest=frame["capability_profile_digest"])
    assert raw == seen["results"][0]["stdout"].encode("utf-8")
    assert json.loads(raw)["target"]["workstream"] == WORK
    assert receipt["bundle_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["execution_authority"] is False
    assert len(seen["results"]) == 1 and len(seen["attests"]) == 2
    return planning._planning_fixture(tmp_path, monkeypatch, raw, receipt, seen)


def test_signed_context_response_reaches_original_planning_prompt_and_reconciles(
        tmp_path, monkeypatch, rsa_key):
    factory, args, _, _, raw, receipt, seen = _authenticated_composition(
        tmp_path, monkeypatch, rsa_key)
    planning._prove_original_planning_input(
        tmp_path, factory, args, raw, receipt, seen)


def test_signed_context_read_cannot_override_withdrawn_planning_admission(
        tmp_path, monkeypatch, rsa_key):
    factory, args, armed, _, _, receipt, seen = _authenticated_composition(
        tmp_path, monkeypatch, rsa_key)
    armed[0] = False
    with pytest.raises((ValueError, ForegroundOperationRefusal)):
        asyncio.run(planning.invocation(
            factory, args, lambda: factory.submit(**args)))
    assert receipt["execution_authority"] is False
    assert factory.service.runtime.jobs.list_jobs() == []
    assert factory.service.runtime.attempts.list_attempts() == []
    assert len(seen["results"]) == 1
