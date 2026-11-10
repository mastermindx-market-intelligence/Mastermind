"""Real signed App/SDK -> Unix peer -> original service/input-owner replay.

Collectable in the cloud; execution belongs to the authorized M2 host with
AF_UNIX capability. The original ProjectExecution service and Supervisor that
admitted/froze the input are retained. A temporary listener uses their actual
Control handler and genuine namespace custody. No physical dispatch, provider,
installed enrollment, peer check or private handler is mocked here.
"""
import asyncio
import dataclasses
import json
from pathlib import Path
import tempfile

import pytest

from common import coo_project_help_contract as wire
from control_plane.coo_principal_host import CooHostProvider
from control_plane.project_execution_admission import bind_original_input_reader
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from integrations.session_bridge.installed import build_runtime_session_bridge
from tests import test_t3_project_help_api as api
from tests.test_project_execution_help_read import (
    execution_help, execution_project, qualified_help, full_joined, owner,
    env, isolated_git_env, identity, rsa_key,
)


@pytest.mark.parametrize("boundary", ["current", "revoked_after_original_read"])
def test_actual_original_input_help_reaches_existing_unix_control(
        execution_help, rsa_key, tmp_path, monkeypatch, boundary):
    f = execution_help
    signed = api.signed_help.__wrapped__(f, rsa_key, tmp_path)
    service, runtime = f.service, f.j["runtime"]
    original_supervisor, original_input_owner = service.supervisor, f.input_reader._original_owner
    original_binding = service._ceo_ingress_app_binding
    source, workspace = f.provider.source, f.workspace
    seen, readers = [], []

    async def run():
        with tempfile.TemporaryDirectory(prefix="mmx-input-help-", dir="/tmp") as directory:
            path = Path(directory) / "help.sock"
            bridge = build_runtime_session_bridge(runtime,
                dialogue_socket_path=Path(directory) / "unused-dialogue.sock")

            def facts(actual):
                assert actual is runtime and service.supervisor is original_supervisor
                reader = bind_original_input_reader(service, actual)
                assert reader._original_owner is original_input_owner
                readers.append(reader)
                provider = CooHostProvider(source, workspace, project_execution_input_reader=reader)
                original_read = provider.read_project_help

                async def observed(frame, **options):
                    value = await original_read(frame, **options)
                    seen.append((json.loads(json.dumps(frame)), value["schema"]))
                    if boundary == "revoked_after_original_read":
                        f.coo["missions"][0]["enabled"] = False
                    return value

                provider.read_project_help = observed
                return provider

            def targets(actual):
                assert actual is runtime
                return bridge

            binding = dataclasses.replace(original_binding,
                principal_facts_factory=facts, session_bridge_provider_factory=targets)
            monkeypatch.setattr(service, "_ceo_ingress_app_binding", binding)
            assert service.runtime is runtime and service._ceo_ingress_ready
            assert service._namespace_custody is f.custody
            server = await asyncio.start_unix_server(
                service._handle_ceo_ingress_connection, path=str(path), limit=73728)
            try:
                client = CooFactsClient(path)
                signed.settings = dataclasses.replace(signed.settings,
                    executive=dataclasses.replace(signed.settings.executive, ceo_ingress_socket_path=path),
                    authority_provider=client.authority, mission_provider=client.mission,
                    project_help_context_provider=client.project_help_context,
                    project_help_provider=client.project_help)
                before = api._events(f)
                async with api._session(signed) as (session, _):
                    listed = await session.list_tools()
                    assert wire.TOOL in {tool.name for tool in listed.tools}
                    result = await session.call_tool(wire.TOOL, {"work_ref": f.work})
                body = api._payload(result)
                assert seen and all(schema == wire.EXECUTION_RESULT_SCHEMA for _, schema in seen)
                assert all(frame["schema"] == wire.FRAME_SCHEMA for frame, _ in seen)
                assert all(reader._service is service and reader._runtime is runtime
                    and reader._supervisor is original_supervisor
                    and reader._binding is binding and reader._namespace is f.custody for reader in readers)
                if boundary == "current":
                    assert result.isError is False and body["ok"] is True, body
                    value = body["data"]
                    assert value["schema"] == wire.EXECUTION_RESULT_SCHEMA and value["scope"] == f.scope
                    assert value["original_execution"]["original_source_plan"] == f.source_plan
                    assert value["observation"]["mission"]["mission_read_state"] == "PARTIAL"
                    assert value["execution_authority"] is value["native_origin_attested"] is False
                    assert len(seen) == 2
                else:
                    assert result.isError is True and body.get("data") is None
                    assert len(seen) == 1
                assert api._events(f) == before
                assert signed.token not in json.dumps(body) and signed.second not in json.dumps(body)
            finally:
                server.close()
                await server.wait_closed()
                await service._drain_service_tasks(service._ceo_ingress_tasks)
                assert not service._ceo_ingress_tasks and f.custody._active is None

    asyncio.run(run())
