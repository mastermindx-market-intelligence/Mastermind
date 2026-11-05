"""Actual App auth/private syntax/Runtime selection; inert socket boundary.

No provider or physical worker is invoked. The separate Unix App regression
owns kernel-peer coverage. These cases prove the real App's selected CEO is
retained by canonical ingress without extending the public MCP contract.
"""
import asyncio
import copy
import dataclasses
import time

import pytest

from common.session_bridge_private_contract import private_result
from control_plane import ceo_request, executive_ceo_ingress as ingress
from control_plane import foreground_operation
from control_plane.executive_inbox import ceo_intent_provenance
from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_OK
from integrations.session_bridge import http_foreground
from integrations.session_bridge.installed import validate_private_frame
from integrations.session_bridge.native_backends import ExecutiveSummonAdapter
from integrations.session_bridge.schemas import (
    BridgeError, summon_input_schema, validate_installed_summon_arguments,
    validate_tool_arguments,
)
from tests.test_foreground_operation import frame
from tests.test_frontier_selection_custody import _selection
from tests.test_frontier_selection_ingress import setup
from tests.test_mastermind_os_foreground_admission import app_for, post, rsa_key, settings
from tests import test_mastermind_os_executive_transport as web


def test_selected_ceo_crosses_private_app_owner_and_freezes_original_root(tmp_path, settings, rsa_key):
    runtime, public, kwargs, observations = setup(tmp_path)
    seen = []
    async def run():
        class FramingFixture:
            async def send_frame(self, *_):
                pytest.fail("selected CEO fell back to unattended admission")

            async def send_foreground_frame(self, _path, framed):
                tool, _principal, arguments = validate_private_frame(framed)
                assert tool == "session_summon"
                seen.append(copy.deepcopy(arguments))
                source = http_foreground.current_request()
                async with foreground_operation._session_bridge_foreground_dispatch(
                        runtime, framed, source.require_live) as operation:
                    async def submit(parsed):
                        operation.require_arguments(parsed)
                        actual = {**public,
                            "request_ref": ceo_request.app_request_ref(parsed["operation_key"]),
                            "request": {k: v for k, v in parsed.items() if k != "operation_key"}}
                        receipt = await ingress.handle_frame(actual,
                            **kwargs, fresh_admission_observer=operation._bind_admitted_root)
                        if not receipt["duplicate"]:
                            operation.require_root(receipt["job_id"])
                        return receipt
                    result = await ExecutiveSummonAdapter(submit)(arguments)
                    return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
                        result=private_result(tool, data=result))
        now = int(time.time())
        app = app_for(dataclasses.replace(settings, clock=lambda: now), boundary=FramingFixture())
        token = web.fixture._submit_token(rsa_key, iat=now-1, nbf=now-1, exp=now+120)
        arguments = {**public["request"], "operation_key": "app-selected-ceo-foreground"}
        code, first = await post(app, token, arguments)
        assert code == 200 and first["status"] == "accepted", first
        root = first["receipt"]["job_id"]
        provenance, warning = ceo_intent_provenance(runtime, root)
        assert warning is None and provenance["frontier_selection"] == _selection()
        observed = list(observations)
        code, replay = await post(app, token, arguments)
        assert code == 200 and replay["receipt"]["duplicate"] is True
        assert replay["receipt"]["job_id"] == root and observations == observed
        assert len(runtime.jobs.list_jobs()) == 1 and runtime.attempts.list_attempts() == []
        assert len(seen) == 2 and all(value["frontier_model_alias"] == "frontier.orchestrator" for value in seen)
    asyncio.run(run())


def test_private_app_extension_does_not_extend_public_summon():
    arguments = {**frame()["arguments"], "frontier_model_alias": "frontier.orchestrator"}
    assert validate_installed_summon_arguments(arguments)["frontier_model_alias"] == "frontier.orchestrator"
    with pytest.raises(BridgeError):
        validate_tool_arguments("session_summon", arguments)
    assert "frontier_model_alias" not in summon_input_schema()["properties"]


@pytest.mark.parametrize("change", [
    {"execution_profile": "native_research_only"},
    {"execution_profile": "bounded_code_change"},
    {"frontier_model_alias": " frontier.orchestrator"},
    {"provider": "caller-selected"},
])
def test_private_selected_ceo_does_not_expand_profile_or_authority(change):
    arguments = {**frame()["arguments"], "frontier_model_alias": "frontier.orchestrator", **change}
    with pytest.raises(BridgeError):
        validate_installed_summon_arguments(arguments)


def test_original_foreground_source_binds_selected_alias(tmp_path):
    from control_plane.executive_runtime import Runtime
    async def run():
        selected = frame()
        selected["arguments"]["frontier_model_alias"] = "frontier.orchestrator"
        async with foreground_operation._session_bridge_foreground_dispatch(
                Runtime.at(tmp_path), selected, lambda: None) as operation:
            operation.require_arguments(selected["arguments"])
            for changed in ({k: v for k, v in selected["arguments"].items() if k != "frontier_model_alias"},
                            {**selected["arguments"], "frontier_model_alias": "other.alias"}):
                with pytest.raises(foreground_operation.ForegroundOperationRefusal) as error:
                    operation.require_arguments(changed)
                assert error.value.code == "arguments_changed"
    asyncio.run(run())
