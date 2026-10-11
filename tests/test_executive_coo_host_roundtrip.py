"""Signed App -> incumbent facts/socket/Workspace/Runtime with test-only grants."""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import json
import tempfile
from pathlib import Path
import httpx
import pytest
from control_plane.coo_principal_host import CooHostProvider
from integrations.mastermind_executive_app.coo_binding import _digest
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from integrations.executive_mcp import server
from tests import test_executive_coo_host as host_tests
from tests import test_executive_coo_app as app_tests
from tests import test_executive_coo_mcp as mcp_tests
from tests import test_executive_principal_ingress as ingress_tests
from tests import test_workspace_result_service as workspace_tests
rsa_key = app_tests.rsa_key
result_owner = workspace_tests.result_owner


@pytest.mark.parametrize("assigned", [True, False])
def test_signed_request_uses_host_sources_and_final_guard(rsa_key, tmp_path, result_owner, assigned):
    _, token, current, settings = app_tests.setup(rsa_key, tmp_path)
    host, coo, _, _ = host_tests.setup(tmp_path)
    coo["policy"] = json.loads(json.dumps(dataclasses.asdict(settings.policy)))
    coo["binding"] = current["binding"]
    work_ref = result_owner["selection"]["work_ref"]
    coo["missions"][0].update(work_ref=work_ref, principal_binding_digest=_digest(coo["binding"]["binding"]))
    if assigned:
        owner = result_owner["owners"][0]
        doc = copy.deepcopy(owner.state_cache["doc"])
        row = doc["autonomy"]["responsibilities"][0]
        row["accountable_seat"] = "coo"
        row["owed_turn"]["seat"] = "coo"
        with owner.state_lock:
            owner.state_cache["doc"] = doc
            workspace_tests.ccr._publish_source_validity(owner, doc, tuple(result_owner["clock"]), tuple(result_owner["clock"]))
    provider = CooHostProvider(host.source, workspace_tests.service(result_owner))
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-coo-host-", dir="/tmp") as directory:
            socket_root = Path(directory)
            service = ingress_tests.service(tmp_path, socket_root, guard=provider.guard)
            service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding,
                principal_facts_factory=lambda runtime: provider)
            base = dataclasses.replace(settings.executive, ceo_ingress_socket_path=socket_root / "principal.sock")
            facts = CooFactsClient(base.ceo_ingress_socket_path)
            selected = dataclasses.replace(settings, executive=base, authority_provider=facts.authority,
                mission_provider=facts.mission)
            app = server.build_web_ceo_v2_with_coo_mcp_app(base, coo_settings=selected, audit_sink=app_tests.Sink())
            await service.start()
            try:
                jobs_before = len(result_owner["writer"].jobs.list_jobs())
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                        async def call(tool, arguments):
                            response = await mcp_tests.rpc(client, token, "/mcp/coo", "tools/call",
                                {"name": tool, "arguments": arguments})
                            assert response.status_code == 200, response.text
                            return json.loads(response.json()["result"]["content"][0]["text"])
                        mandate = await call("executive_mandate", {"work_ref": work_ref})
                        assert mandate["ok"] is True, mandate
                        if not assigned:
                            assert mandate["data"]["new_effect_gate"] == "FENCED_NOT_COO_ACCOUNTABLE"
                            refused = await call("submit_principal_intent", dict(app_tests.payload(), workstream=work_ref))
                            assert refused["ok"] is False
                            assert len(result_owner["writer"].jobs.list_jobs()) == jobs_before
                            return
                        assert mandate["data"]["new_effect_gate"] == "OPEN", mandate
                        payload = dict(app_tests.payload(), workstream=work_ref)
                        first = await call("submit_principal_intent", payload)
                        assert first["ok"] is True, first
                        assert first["receipt"]["dispatched"] is False
                        duplicate = await call("submit_principal_intent", payload)
                        assert duplicate["receipt"]["job_id"] == first["receipt"]["job_id"]
                        assert duplicate["receipt"]["duplicate"] is True
                        coo["missions"][0]["enabled"] = False
                        acquisitions = result_owner["namespace"].entries
                        status = await call("principal_intent_status", dict(work_ref=work_ref, request_ref=first["request_ref"]))
                        assert status["receipt"]["job_id"] == first["receipt"]["job_id"]
                        assert result_owner["namespace"].entries == acquisitions
                        fresh = await call("submit_principal_intent", dict(payload, operation_key="new-disabled-work"))
                        assert fresh["ok"] is False
                        unavailable = await call("executive_mandate", {"work_ref": work_ref})
                        assert unavailable["ok"] is False
                        jobs = result_owner["writer"].jobs.list_jobs()
                        assert len(jobs) == jobs_before + 1
                        added = result_owner["writer"].jobs.get_job(first["receipt"]["job_id"])
                        assert added.attempt_count == 0
            finally:
                await service.close()
    asyncio.run(exercise())


def test_c1_cannot_read_principal_facts_or_invoke_the_host_factory(tmp_path):
    host, coo, principal, _ = host_tests.setup(tmp_path)
    calls = []
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-coo-peer-", dir="/tmp") as directory:
            service = ingress_tests.service(tmp_path, Path(directory), app_peer=False)
            service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding,
                principal_facts_factory=lambda runtime: calls.append(runtime) or host)
            await service.start()
            try:
                frame = dict(schema=host_tests.FACT_SCHEMA, operation="authority",
                    work_ref=coo["missions"][0]["work_ref"], principal=principal)
                response = await ingress_tests.send(Path(directory) / "principal.sock", frame)
                assert response["ok"] is False and response["error"]["code"] == "peer_denied"
                assert calls == []
            finally:
                await service.close()
    asyncio.run(exercise())
