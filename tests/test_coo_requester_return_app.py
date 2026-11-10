"""Signed App edge checks; the inert ingress response is not a Runtime proof."""
from __future__ import annotations

import asyncio
import copy
import dataclasses

import pytest

from common import coo_requester_return_contract as wire
from control_plane.executive_service import _selected_child_frame
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.gateway import CeoIngressResponse
from tests import test_hermes_selected_child_ingress as ingress
from tests.test_coo_requester_return_contract import _descriptor, _observation, _publication

rsa_key = ingress.rsa_key


@pytest.mark.parametrize("boundary", [
    "normal", "old_contract", "missing_action", "missing_receipt", "changed_receipt",
    "post_await_revocation", "lost_response",
])
def test_signed_app_ack_is_explicit_granted_digest_bound_and_one_send(rsa_key, boundary):
    settings, current, token = ingress._app_settings(rsa_key, ingress._target())
    original_actions = current["authority"].principal_actions
    if boundary != "missing_action":
        current["authority"] = dataclasses.replace(current["authority"],
            principal_actions=tuple(sorted(set(original_actions) | {wire.ACTION})))
    selected = {"catalogue": wire.CATALOGUE}
    if boundary != "old_contract":
        settings = dataclasses.replace(settings, catalogue_provider=lambda *args: selected["catalogue"])
    app = create_coo_app(settings, audit_sink=ingress.app_fixture.Sink())
    publication = dataclasses.replace(_publication(), command=ingress.COMMAND,
        job_id=ingress.CHILD_JOB, root_job_id=ingress.ROOT_JOB,
        work_ref=ingress.WORK_REF, target_digest=ingress._target().material_digest())
    descriptor = _descriptor(publication)
    request = {"action": wire.ACK_ACTION, "command": ingress.COMMAND, "result": descriptor}
    frames = []
    async def send(path, frame):
        frames.append(copy.deepcopy(frame))
        assert _selected_child_frame(frame) == request
        if boundary == "lost_response":
            raise OSError("PRIVATE transport response lost")
        response = _observation(descriptor, publication, consumed=boundary != "missing_receipt")
        if boundary == "changed_receipt":
            response["requester_return"]["consumption"]["result_envelope_digest"] = "f" * 64
        if boundary == "post_await_revocation":
            current["authority"] = dataclasses.replace(current["authority"], principal_actions=original_actions)
        return CeoIngressResponse("sent_ok", ok=True, result=response)
    app._client.send_frame = send
    response = asyncio.run(ingress._call(app, token, "mmx_delegate", request))
    assert response.status_code == 200, response.text
    body = response.json()
    if boundary in {"old_contract", "missing_action"}:
        assert body["state"] == "REFUSED" and frames == []
    elif boundary == "normal":
        assert body["state"] == "COMPLETED", body
        assert body["requester_return"]["consumption"] is not None
        assert body["requester_return"]["parent_consumed"] is False
        assert frames[0]["request"] == request and len(frames) == 1
    else:
        assert body["state"] == "EFFECT_UNKNOWN", body
        assert body["command_id"] == ingress.COMMAND and len(frames) == 1
        assert "requester_return" not in body and "PRIVATE" not in response.text


@pytest.mark.parametrize("field,value", [
    ("native_origin", {"thread": "model-invented"}), ("grant", "model-invented"),
    ("parent_consumed", True), ("acceptance", "accepted"),
])
def test_model_cannot_add_native_identity_authority_or_acceptance(rsa_key, field, value):
    settings, current, token = ingress._app_settings(rsa_key, ingress._target())
    current["authority"] = dataclasses.replace(current["authority"],
        principal_actions=tuple(sorted(set(current["authority"].principal_actions) | {wire.ACTION})))
    settings = dataclasses.replace(settings, catalogue_provider=lambda *args: wire.CATALOGUE)
    app = create_coo_app(settings, audit_sink=ingress.app_fixture.Sink())
    sends = []
    async def send(*args):
        sends.append(args)
        raise AssertionError("model authority reached ingress")
    app._client.send_frame = send
    publication = dataclasses.replace(_publication(), command=ingress.COMMAND,
        job_id=ingress.CHILD_JOB, root_job_id=ingress.ROOT_JOB, work_ref=ingress.WORK_REF)
    descriptor = _descriptor(publication)
    descriptor[field] = value
    response = asyncio.run(ingress._call(app, token, "mmx_delegate", {
        "action": wire.ACK_ACTION, "command": ingress.COMMAND, "result": descriptor}))
    assert response.status_code == 400 and sends == []
