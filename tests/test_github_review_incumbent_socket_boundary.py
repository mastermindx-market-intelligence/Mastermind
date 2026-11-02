"""Current ExecutiveControlService GitHub-review refusal and future default-off guard.

This exercises the incumbent authenticated Unix socket in a hermetic Runtime.
It is intentionally NOT evidence of an installed review-frame dispatch. The
previously safety-denied handler source is never edited by this test.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from control_plane.executive_service import (
    CeoIngressAppBinding, ExecutiveControlService,
)
from control_plane.github_review_intent import review_command_id, review_intent_id
from control_plane.github_review_socket_contract import FRAME_SCHEMA
from tests.test_executive_ceo_ingress import (
    _FakeGrounding, _FakeSupervisor, _config, _raw_ceo_request,
)
from tests.test_executive_ceo_ingress import short_socket_root  # noqa: F401


@pytest.mark.parametrize("generic_app_armed", [False, True])
def test_incumbent_socket_never_infers_review_arm_from_ceo_app(
    tmp_path, short_socket_root, generic_app_armed
):
    async def exercise() -> None:
        app_uid = os.geteuid()
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=app_uid + 1000,
            ceo_ingress_grounding_provider=_FakeGrounding(),
            ceo_ingress_armed=False,
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=app_uid,
                armed=generic_app_armed,
                grounding_provider=_FakeGrounding(),
            ),
        )
        intent = review_intent_id(
            repository="example/repo", pull_number=42, head_sha="a" * 40
        )
        frame = {
            "schema": FRAME_SCHEMA, "action": "status",
            "command_id": review_command_id(intent),
        }
        await service.start()
        try:
            refusal = await _raw_ceo_request(
                service.ceo_ingress_socket_path,
                (json.dumps(frame, separators=(",", ":")) + "\n").encode("ascii"),
            )
            assert refusal == {
                "ok": False,
                "error": {
                    "code": "peer_denied",
                    "message": "frame is not authorized for this peer",
                },
            }
            assert service.runtime.jobs.list_jobs() == []
            assert service.runtime.workers.list_workers() == []
        finally:
            await service.close()

    asyncio.run(exercise())
