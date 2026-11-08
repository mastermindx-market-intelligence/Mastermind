"""Foreground transport-not-sent provenance at the actual client -> adapter edge.

Only the trusted transport response varies; the installed Session Bridge
client, the foreground request lifetime and the App admission composition are
actual source. The proved-not-sent response alone maps to the incumbent
ingress-unavailable admission with the original request reference and exactly
one send attempt; sent-unknown, generic backend_unavailable errors, malformed
responses and lost post-send replies all remain conservatively effect_unknown.
No provider, network, enrollment or production effect is exercised.
"""
import asyncio
import dataclasses
import time

import pytest

from common.session_bridge_private_contract import private_result
from control_plane import executive_ceo_ingress as ingress
from control_plane.ceo_request import app_request_ref
from control_plane.executive_service import _ForegroundExecution
from integrations.mastermind_executive_app import admission
from integrations.mastermind_executive_app.admission import STATUS_TRANSPORT_UNAVAILABLE
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, CeoIngressResponse,
    TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN,
)
from integrations.session_bridge.installed import InstalledSessionBridgeClient
from integrations.session_bridge.schemas import BridgeError
from tests import test_foreground_fresh_admission as fresh
from tests import test_mastermind_os_executive_transport as web
from tests.test_foreground_operation import frame
from tests.test_foreground_operator_completion import service_at
from tests.test_mastermind_os_foreground_admission import app_for, post
from tests.test_session_bridge_installed import PRINCIPAL

settings = web.settings
rsa_key = web.rsa_key


class TransportFixture:
    """Injects one classified transport response; nothing is ever forwarded."""

    def __init__(self, edge):
        self.edge = edge
        self.frames = []

    async def send_frame(self, *args):
        pytest.fail("App research fell back to unattended one-shot transport")

    async def send_foreground_frame(self, path, framed):
        self.frames.append(framed)
        if self.edge == "not_sent":
            # Trusted transport provenance: the frame provably never reached
            # the installed owner, so zero effect began.
            return CeoIngressResponse(transport=TRANSPORT_NOT_SENT)
        if self.edge == "sent_unknown":
            return CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN)
        if self.edge == "generic_backend":
            # Same public code as not-sent, but the frame was sent and the
            # trusted owner refused it: provenance must stay with the type.
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=private_result(
                "session_summon", code="backend_unavailable",
                message="installed Session Bridge owner is unavailable"))
        if self.edge == "malformed":
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
                result={"schema": "not.the.private.result.schema"})
        raise RuntimeError("inert post-send reply loss")


@pytest.mark.parametrize("edge, expected_status, expected_http", [
    ("not_sent", STATUS_TRANSPORT_UNAVAILABLE, 503),
    ("sent_unknown", "effect_unknown", 202),
    ("generic_backend", "effect_unknown", 202),
    ("malformed", "effect_unknown", 202),
    ("post_send_error", "effect_unknown", 202),
])
def test_foreground_transport_provenance_maps_only_proved_not_sent(
        tmp_path, monkeypatch, settings, rsa_key, edge, expected_status, expected_http):
    async def run():
        service = service_at(tmp_path)
        runtime = service.runtime
        monkeypatch.setattr(service, "_foreground_execution_state",
            lambda **kw: _ForegroundExecution("ORDINARY_OPERATOR", b"{}"))
        monkeypatch.setattr(service, "_coo_binding_for_root",
            lambda _: {"operator_execution_profile_id": "ordinary", "operator_harness_armed": True})
        # Keep the pre-adapter fallback executable but loud: the App research
        # submit must use exactly its foreground owner, once.
        async def legacy_grounding(*_):
            return await ingress._observe_trusted_grounding(fresh.hooks.pr_a._FakeGrounding())
        async def refused_send(_client, _path, framed):
            pytest.fail("App research fell back to unattended transport")
        monkeypatch.setattr(admission, "observe_ingress_grounding", legacy_grounding)
        monkeypatch.setattr(CeoIngressClient, "send_frame", refused_send)

        boundary = TransportFixture(edge)
        now = int(time.time())
        app = app_for(dataclasses.replace(settings, clock=lambda: now), boundary=boundary)
        token = web.fixture._submit_token(rsa_key, iat=now-1, nbf=now-1, exp=now+120)
        arguments = frame("app-source-plan-only")["arguments"]
        status, result = await post(app, token, arguments)
        assert status == expected_http, (status, result)
        assert result["ok"] is False and result["status"] == expected_status, result
        assert result["request_ref"] == app_request_ref(arguments["operation_key"])
        assert len(boundary.frames) == 1, boundary.frames
        assert boundary.frames[0]["arguments"] == {
            **arguments, "allowed_write_paths": [], "attempt_limit": 2, "validation": {}}
        if edge == "not_sent":
            assert result["error"] == {"code": "ingress_unavailable",
                "message": "Executive CEO ingress did not send the original request"}
        else:
            assert result["error"]["code"] == "effect_unknown"
        assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []
        assert service._foreground_cycle_owner is None and not service._coo_action_tasks
    asyncio.run(run())


def test_installed_not_sent_keeps_public_code_for_nonforeground_callers(tmp_path):
    """One-shot (non-foreground) callers keep the incumbent public error code."""
    async def run():
        class NotSentBoundary:
            def __init__(self):
                self.frames = []
            async def send_frame(self, path, framed):
                self.frames.append(framed)
                return CeoIngressResponse(transport=TRANSPORT_NOT_SENT)
        boundary = NotSentBoundary()
        owner = InstalledSessionBridgeClient(tmp_path / "unused-ceo-ingress.sock", client=boundary)
        with pytest.raises(BridgeError) as refused:
            await owner.targets(PRINCIPAL)
        assert refused.value.code == "backend_unavailable"
        assert refused.value.message == "installed Session Bridge owner is unavailable"
        assert len(boundary.frames) == 1
    asyncio.run(run())
