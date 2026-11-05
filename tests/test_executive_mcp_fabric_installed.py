"""Installed Executive App proof for the read-only Fabric view."""
from __future__ import annotations

import asyncio
import json
import os

from control_plane.executive_service import (
    CEO_APP_READ_SCHEMA,
    CEO_WEB_CEO_READ_SCHEMA,
    CeoIngressAppBinding,
    ExecutiveControlService,
)
from integrations.executive_mcp.installed import InstalledExecutiveReaders
from integrations.executive_mcp.web_ceo import WebCeoInstalledExecutiveReaders
from tests.test_executive_ceo_ingress import (
    _FakeGrounding,
    _FakeSupervisor,
    _config,
    _raw_ceo_request,
    _submit_v2_bytes,
)
from tests.test_executive_ceo_ingress import short_socket_root  # noqa: F401


def test_installed_app_fabric_reads_the_admitted_runtime(
    tmp_path, short_socket_root
) -> None:
    async def exercise() -> None:
        config = _config(tmp_path, socket_root=short_socket_root)
        readers = WebCeoInstalledExecutiveReaders(
            repo_root=config.proof_source_repository,
            macro_root=config.proof_source_repository,
            runtime_root=config.runtime_root,
        )
        service = ExecutiveControlService(
            config,
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(),
                armed=True,
                grounding_provider=_FakeGrounding(),
                read_provider=readers,
                read_schema=CEO_WEB_CEO_READ_SCHEMA,
            ),
        )
        await service.start()
        try:
            admitted = await _raw_ceo_request(
                service.ceo_ingress_socket_path, _submit_v2_bytes()
            )
            assert admitted["ok"] is True, admitted
            job_id = admitted["result"]["job_id"]
            frame = {
                "schema": CEO_WEB_CEO_READ_SCHEMA,
                "tool": "executive_fabric",
                "arguments": {"view": "root", "root_job_id": job_id},
            }
            read = await _raw_ceo_request(
                service.ceo_ingress_socket_path,
                (json.dumps(frame) + "\n").encode(),
            )
            assert read["ok"] is True, read
            assert read["result"]["ok"] is True, read
            assert read["result"]["tool"] == "executive_fabric"
            assert read["result"]["data"]["schema"] == "mastermind.fabric_job_view.v1"
            assert read["result"]["data"]["root"]["job_id"] == job_id
            assert (
                read["result"]["data"]["runtime"]["root"]
                == "readonly:installed-executive-runtime"
            )
            assert str(config.runtime_root) not in json.dumps(read, sort_keys=True)
        finally:
            await service.close()
            await readers.aclose()

    asyncio.run(exercise())

def test_legacy_app_read_profile_still_refuses_fabric(
    tmp_path, short_socket_root
) -> None:
    async def exercise() -> None:
        config = _config(tmp_path, socket_root=short_socket_root)
        readers = InstalledExecutiveReaders(
            repo_root=config.proof_source_repository,
            macro_root=config.proof_source_repository,
            runtime_root=config.runtime_root,
        )
        service = ExecutiveControlService(
            config,
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "legacy-ceo.sock",
            ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(),
                armed=True,
                grounding_provider=_FakeGrounding(),
                read_provider=readers,
            ),
        )
        await service.start()
        try:
            frame = {
                "schema": CEO_APP_READ_SCHEMA,
                "tool": "executive_fabric",
                "arguments": {"view": "roots"},
            }
            read = await _raw_ceo_request(
                service.ceo_ingress_socket_path,
                (json.dumps(frame) + "\n").encode(),
            )
            assert read["ok"] is False
            assert read["error"]["code"] == "invalid_input"
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()
            await readers.aclose()

    asyncio.run(exercise())
