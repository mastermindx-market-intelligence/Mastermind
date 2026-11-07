"""Hermetic JWT -> mounted ASGI -> App peer -> real selector/Runtime read.

Account, Relay, Context and original host target are explicit fixtures. This is
source qualification, never an installed producer or authenticated browser claim.
"""
import asyncio
import os

import httpx
import pytest

from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from control_plane.principal_ruling_target import PrincipalRulingTarget
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.executive_mcp import server
from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config, short_socket_root
from tests.test_product_acceptance_original_selector import anchor, bind_actual_issuer
from tests.test_product_acceptance_read_projection import case
from tests.test_product_acceptance_workspace_read import provider
from tests.test_workspace_read_app import NOW, _authenticator, _workspace_token, rsa_key
from tests.test_workspace_result_mount import settings
import test_executive_mcp_app_composition as existing


@pytest.mark.parametrize("state", ["accepted", "pending_parent", "uncomposed"])
def test_real_mounted_original_owner_acquisition(tmp_path, monkeypatch, short_socket_root, rsa_key, settings, state):
    bind_actual_issuer(monkeypatch)
    with case(tmp_path, monkeypatch, complete=state != "pending_parent") as (
        runtime, owner, _, _, selected, _,
    ):
        obligation = anchor(runtime, owner, selected)
        target = None if state == "uncomposed" else PrincipalRulingTarget(
            selected["work_ref"], obligation.obligation_id, "fixture-host")
        seen = []

        def factory(actual_runtime):
            assert actual_runtime is service.runtime
            bound = service._namespace_custody.bound_runtime(actual_runtime)
            original, _, _ = provider(tmp_path, actual_runtime, owner.reader, selected, bound)
            value = WorkspaceReadService(cache=original.cache, runtime=actual_runtime,
                authorize=original.authorize, armed=original.armed,
                runtime_identity=original.runtime_identity, bounded_runtime=original._bounded_runtime,
                product_acceptance_basis_reader=owner.reader,
                product_acceptance_owner_target=target,
                product_acceptance_read=original._product_acceptance_read,
                product_acceptance_observe=original._product_acceptance_observe)
            seen.append(actual_runtime)
            return value

        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root, runtime_root=runtime.store.root),
            runtime_factory=lambda root: runtime,
            supervisor_factory=lambda actual_runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=_FakeGrounding(), workspace_read_provider_factory=factory),
        )

        async def run():
            await service.start()
            try:
                events = runtime.events.list_events()
                workspace = create_workspace_app(WorkspaceAppConfig(
                    authenticator=_authenticator(rsa_key), now=lambda: NOW,
                    authorize_principal=lambda principal: True,
                    client=CeoIngressWorkspaceClient(service.ceo_ingress_socket_path)))
                app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
                                                     workspace_app=workspace)
                params = {k: selected[k] for k in ("work_ref", "root_job_id")}
                params["read_mode"] = "original_owner"
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                        base_url="https://mcp.mastermind-x.com") as client:
                    route = "/workspace/mission/v4/current"
                    denied = await client.get(route, params=params)
                    assert denied.status_code == 401 and not seen
                    response = await client.get(route, params=params,
                        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
                assert response.headers["Cache-Control"] == "no-store"
                if state == "uncomposed":
                    assert response.status_code == 503, response.text
                    assert "obligation" not in response.text
                else:
                    assert response.status_code == 200, response.text
                    value = response.json()
                    assert value["schema"] == "mastermind.mission_workspace.v4"
                    assert value["mission"]["read_state"]["state"] == "CURRENT"
                    acceptance = value["product_acceptance"]
                    assert acceptance["selection"] == selected
                    assert acceptance["state"] == ("ACCEPTED" if state == "accepted" else "UNAVAILABLE")
                    assert "obligation_id" not in response.text
                assert seen == [service.runtime]
                assert runtime.events.list_events() == events
            finally:
                await service.close()

        asyncio.run(run())
