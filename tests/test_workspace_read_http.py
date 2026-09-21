"""Signed HTTP -> sibling App -> actual Unix control service -> SQLite owners.

Uses #833's closed test-owned namespace fixture, never installed OS custody.
Requires the isolated App/control/CCR patches and frozen #819/#882 dependencies.
"""
import asyncio
import hashlib
import json

import httpx
import pytest

from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW, ISSUER
from tests.test_workspace_read_socket import control, short_socket_root
from tests.test_workspace_read_service import cache_fixture
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_executive_runtime_bounded_read import observation_fixture
from tests.test_mission_workspace import _owner_observation_inputs
from scripts import chairman_control_room as ccr


def test_real_http_runtime_owner_receipt_and_deny_before_read(
    tmp_path, short_socket_root, observation_fixture, rsa_key, monkeypatch,
):
    root, writer, runtime, namespace, binding, job_id, _ = observation_fixture
    owners, clock, cache = cache_fixture(tmp_path)
    # Publish through the real existing CCR source-validity publisher. Reuse
    # the canonical reducer owner's fixture vocabulary, not a trusted boolean.
    args = _owner_observation_inputs()
    document = json.loads(json.dumps(args["control_room"]).replace("JOB-1", job_id).replace("2026-09-20", "2026-09-21"))
    document["generated_at"] = owners[0].state_cache["doc"]["generated_at"]
    document["autonomy"]["generated_at"] = document["generated_at"]
    document["autonomy"]["responsibilities"][0]["validity"] = owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["validity"]
    owners[0].state_cache["doc"] = document
    owners[0].state_cache.pop("source_validity_bounds", None)
    with owners[0].state_lock:
        ccr._publish_source_validity(owners[0], document, tuple(clock), tuple(clock))
    authenticator = _authenticator(rsa_key)
    token = _workspace_token(rsa_key)
    counters = {"cache": 0, "factory": 0}
    original_snapshot = cache.snapshot
    def snapshot():
        counters["cache"] += 1
        return original_snapshot()
    cache.snapshot = snapshot

    async def run():
        principal = await authenticator.verify_authorization_header("Bearer " + token, now=NOW)
        slots = {"schema": BINDINGS_SCHEMA, "profiles": {
            "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
            "mac": {"enabled": False, "binding": None}}}
        app_authorize, service_authorize = workspace_authorizers(policy=authenticator.policy, load_bindings=lambda: slots)
        def factory(actual):
            assert actual is writer
            counters["factory"] += 1
            return WorkspaceReadService(cache=cache, runtime=actual, authorize=service_authorize,
                                        armed={}, runtime_identity={"db_present": True},
                                        bounded_runtime=lambda owner: runtime if owner is writer else pytest.fail("wrong Runtime owner"))
        svc = control(tmp_path, short_socket_root, factory)
        svc._runtime_factory = lambda path: writer
        await svc.start()
        try:
            workspace = create_workspace_app(WorkspaceAppConfig(authenticator=authenticator, now=lambda: NOW,
                authorize_principal=app_authorize, client=CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)))
            # Exercise the actual existing AppSettings sibling mount as well.
            from integrations.mastermind_executive_app.app import AppSettings, create_app
            from integrations.mastermind_executive_app.gateway import AppPolicies
            from tests.test_mastermind_executive_app_asgi import _read_policy, _submit_policy, _FakeJwksCache
            mounted = create_app(AppSettings(policies=AppPolicies(read=_read_policy(), submit=_submit_policy()),
                mastermind_root=tmp_path, macro_root_flag=None, environ={}, ceo_ingress_socket_path=svc.ceo_ingress_socket_path,
                read_from_ceo_ingress=True, jwks_cache=_FakeJwksCache(rsa_key), clock=lambda: NOW, workspace_app=workspace))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mounted), base_url="http://fixture") as client:
                for bad in (None, _workspace_token(rsa_key, client_id="foreign"),
                            _workspace_token(rsa_key, scope="mastermind.executive.read"),
                            _workspace_token(rsa_key, sub="foreign"), _workspace_token(rsa_key, resource="https://wrong.example.test")):
                    response = await client.get("/workspace/programs/current", headers={} if bad is None else {"Authorization": "Bearer " + bad})
                    assert response.status_code in (401, 403)
                    assert counters == {"cache": 0, "factory": 0}
                headers = {"Authorization": "Bearer " + token}
                programs = await client.get("/workspace/programs/current", headers=headers)
                assert programs.status_code == 200, programs.text
                assert programs.json()["control_room"] == document
                entries = namespace.entries
                from control_plane import executive_runtime as er
                traces = []
                original_connect = er.sqlite3.connect
                def connect(*args, **kwargs):
                    connection = original_connect(*args, **kwargs)
                    connection.set_trace_callback(traces.append)
                    return connection
                monkeypatch.setattr(er.sqlite3, "connect", connect)
                monkeypatch.setattr(runtime.jobs, "list_jobs", lambda *a, **k: pytest.fail("unbounded Jobs"))
                monkeypatch.setattr(runtime.events, "list_events", lambda *a, **k: pytest.fail("legacy Event history"))
                monkeypatch.setattr(runtime.attempts, "list_attempts", lambda *a, **k: pytest.fail("unbounded Attempts"))
                response = await client.get("/workspace/mission/current", params={"work_ref": "WS:ONE", "root_job_id": job_id}, headers=headers)
                assert response.status_code == 200, response.text
                result = response.json()
                assert result["schema"] == "mastermind.mission_workspace.v2"
                assert result["read_state"]["state"] == "CURRENT", result["source"]
                assert result["acceptance"]["state"] == "NOT_PROJECTED"
                assert result["source"]["owner_observation"]["runtime"]["state"] == "SAME"
                assert namespace.entries == entries + 1 and namespace.entries == namespace.exits and not namespace.active
                statements = [s.strip().upper() for s in traces]
                assert statements.count("PRAGMA DATA_VERSION") == 2
                assert len(statements) <= 30, statements
                assert not any(s.startswith(("INSERT", "UPDATE", "DELETE")) for s in statements)
                source_reads = counters.copy()
                malformed = await client.get("/workspace/mission/current?work_ref=WS:ONE&work_ref=WS:TWO&root_job_id=" + job_id, headers=headers)
                assert malformed.status_code == 400 and counters == source_reads
                slots["profiles"]["web"]["enabled"] = False
                refused = await client.get("/workspace/programs/current", headers=headers)
                assert refused.status_code == 403 and counters == source_reads
            await mounted.aclose()
        finally:
            await svc.close()
    asyncio.run(run())
