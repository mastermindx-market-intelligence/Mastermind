"""Authenticated selected-child ingress: MCP -> App -> Control -> C17.

The App and the Control each prove the request independently. Only the
existing Unix ingress, the existing Control service, the real Runtime and
the repaired C17 composition are exercised. No installed target, no live
provider, no credential and no publication is involved.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_executive_coo_app as app_fixture
finally:
    sys.path.pop(0)

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.executive_runtime import AttemptStatus, Runtime
from control_plane.executive_service import (
    SELECTED_CHILD_FRAME_SCHEMA, CeoIngressAppBinding, ExecutiveControlService,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_mcp import server
from integrations.executive_mcp.coo import (
    COO_TOOL_NAMES, COO_TOOL_SCHEMA_DIGEST, coo_tool_schema_digest,
    validate_coo_tool_arguments,
)
from integrations.hermes_delegate.executive import (
    ExecutiveChildSelection,
    ExecutiveSelectedChild,
    ExecutiveSelectedChildTarget,
)
from integrations.hermes_delegate.schema import (
    SELECTED_CHILD_FRAME_SCHEMA as INTEGRATION_FRAME_SCHEMA,
    SubmissionError,
    parse_selected_child,
)
from integrations.hermes_delegate.executive import (
    SELECTED_CHILD_FRAME_SCHEMA as INTEGRATION_FRAME_SCHEMA,
)
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.coo import CooApp, CooAppSettings, create_coo_app
from integrations.mastermind_executive_app.coo_binding import (
    BINDING_SCHEMA, COO_SCOPES, principal_frame,
)
from integrations.mastermind_executive_app.gateway import AppPolicies, CeoIngressResponse
from tests.test_executive_coo_hierarchy_service import _complete, _plan_body
from tests.test_executive_coo_ready_frontier_service import _register_peer
from tests.test_executive_os_phase1fc import _complete_ohf_role
from tests.test_executive_service import (
    _capture_projection, _config, _coo_intent, _request, _FakeSupervisor,
)

fixture = app_fixture.fixture
mandate_fixture = app_fixture.mandate_fixture
rsa_key = app_fixture.rsa_key

WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"
CLIENT = "2" * 64
ROOT_JOB = "JOB-001"
CHILD_JOB = "JOB-003"
COMMAND = f"coo-cycle:{ROOT_JOB}:dispatch:{CHILD_JOB}:attempt:1"


# ---------------------------------------------------------------------------
# The frozen target
# ---------------------------------------------------------------------------


def _selection(job_id=CHILD_JOB, root_job_id=ROOT_JOB) -> ExecutiveChildSelection:
    return ExecutiveChildSelection(
        root_job_id=root_job_id, parent_job_id=root_job_id, job_id=job_id,
        plan_attempt_id="attempt-plan-0001", plan_digest="a" * 64,
        plan_step_id="STEP-ONE", repair_round=0,
        expected_current_attempt_id=None,
    )


def _target(*, work_ref=WORK_REF, guard=None, children=None) -> ExecutiveSelectedChildTarget:
    return ExecutiveSelectedChildTarget(
        work_ref=work_ref,
        children=children if children is not None else (
            ExecutiveSelectedChild(selection=_selection(), attempt_ordinal=1),),
        currentness_guard=guard if guard is not None else (lambda: None),
    )


def _frozen_selection(job) -> ExecutiveChildSelection:
    return ExecutiveChildSelection(
        root_job_id=job.root_job_id, parent_job_id=job.parent_job_id,
        job_id=job.job_id, plan_attempt_id=job.plan_attempt_id,
        plan_digest=job.plan_digest, plan_step_id=job.plan_step_id,
        repair_round=job.repair_round,
        expected_current_attempt_id=job.current_attempt_id,
    )


# ---------------------------------------------------------------------------
# The real signed-JWT App edge
# ---------------------------------------------------------------------------


def _app_settings(rsa_key, target, *, client_id=CLIENT, token_holder=None):
    """Build the real COO App over the incumbent signed disposable JWT."""

    policy = fixture._read_policy(policy_id="executive-coo",
                                  required_scopes=list(COO_SCOPES))
    cache = fixture._FakeJwksCache(rsa_key)
    token = fixture._token(rsa_key, scope=" ".join(COO_SCOPES), client_id=client_id)
    principal = asyncio.run(
        JwtAuthenticator(policy=policy, jwks_cache=cache).verify_token(
            token, now=fixture.NOW))
    current = {
        "binding": {"schema": BINDING_SCHEMA, "enabled": True,
                    "binding": {**principal_frame(principal),
                                "permission_digest": "a" * 64}},
        "authority": mandate_fixture.authority(work_ref=WORK_REF),
        "mission": mandate_fixture._real_owner_mission(),
    }
    base = AppSettings(
        policies=AppPolicies(fixture._read_policy(), fixture._submit_policy()),
        mastermind_root=Path(tempfile.mkdtemp(prefix="mmx-c29-root-", dir="/tmp")),
        macro_root_flag=None, environ={},
        ceo_ingress_socket_path=Path(tempfile.mkdtemp(prefix="mmx-c29-sock-", dir="/tmp"))
        / "absent.sock",
        read_from_ceo_ingress=True, jwks_cache=cache, clock=lambda: fixture.NOW)
    settings = CooAppSettings(
        executive=base, policy=policy,
        load_binding=lambda: current["binding"],
        authority_provider=lambda p, work: current["authority"],
        mission_provider=lambda p, work: current["mission"],
        selected_child_target=target)
    if token_holder is not None:
        token_holder.update({"token": token, "principal": principal,
                             "current": current, "policy": policy})
    return settings, current, token


async def _call(app, token, tool, arguments):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://127.0.0.1") as client:
        return await client.post("/v1/tools/" + tool,
                                 headers={"authorization": "Bearer " + token},
                                 json={"arguments": arguments})


# ---------------------------------------------------------------------------
# 1. The default unbound target refuses without an ingress send
# ---------------------------------------------------------------------------


def test_default_unbound_target_refuses_without_an_ingress_send(rsa_key):
    settings, _current, token = _app_settings(rsa_key, None)
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    sends = []

    async def send(path, frame):
        sends.append(frame)
        raise AssertionError("an unbound target reached the Executive ingress")

    app._client.send_frame = send
    for action in ("selected_child_submit", "selected_child_status"):
        result = asyncio.run(_call(app, token, "mmx_delegate",
                                   {"action": action, "command": COMMAND}))
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["schema"] == "mastermind.hermes_delegate.selected_child/v1"
        assert body["state"] == "REFUSED", body
        assert body["reason"] == "EXECUTIVE_SELECTED_CHILD_NOT_BOUND", body
        assert body["command_id"] == COMMAND, body
        assert body["live_submit"] is False, body
    assert sends == []


# ---------------------------------------------------------------------------
# 2. The model cannot select, name or extend a child
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arguments", [
    {"action": "selected_child_submit", "command": COMMAND, "work_ref": WORK_REF},
    {"action": "selected_child_submit", "command": COMMAND, "job_id": CHILD_JOB},
    {"action": "selected_child_submit", "command": COMMAND, "root_id": ROOT_JOB},
    {"action": "selected_child_submit", "command": COMMAND, "idempotency_key": "model-key-0001"},
    {"action": "selected_child_submit", "command": COMMAND, "principal": {"role": "coo"}},
    {"action": "selected_child_submit", "command": COMMAND, "attempt_id": "attempt-0001"},
    {"action": "selected_child_cancel", "command": COMMAND},
    {"action": "submit", "command": COMMAND},
    {"action": [], "command": COMMAND},
    {"action": {}, "command": COMMAND},
    {"action": "selected_child_submit", "command": "JOB-003"},
    {"action": "selected_child_submit", "command": "coo-cycle:JOB-001:dispatch:JOB-003"},
    {"action": "selected_child_submit", "command": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:0"},
])
def test_model_arguments_never_reach_the_ingress(arguments, rsa_key):
    settings, _current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    sends = []

    async def send(path, frame):
        sends.append(frame)
        raise AssertionError("an invalid selected-child request reached the ingress")

    app._client.send_frame = send
    with pytest.raises(Exception):
        validate_coo_tool_arguments("mmx_delegate", arguments)
    result = asyncio.run(_call(app, token, "mmx_delegate", arguments))
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "invalid_input"
    assert sends == []


def test_an_unknown_frozen_command_is_refused_before_the_ingress(rsa_key):
    settings, _current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    sends = []

    async def send(path, frame):
        sends.append(frame)
        raise AssertionError("an unfrozen command reached the Executive ingress")

    app._client.send_frame = send
    unknown = "coo-cycle:JOB-001:dispatch:JOB-999:attempt:1"
    result = asyncio.run(_call(app, token, "mmx_delegate",
                               {"action": "selected_child_submit", "command": unknown}))
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "REFUSED", body
    assert body["reason"] == "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND", body
    assert body["command_id"] == unknown, body
    assert sends == []


# ---------------------------------------------------------------------------
# 3. Wrong scope, client or subject never reaches the ingress
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault", ["scope", "client", "subject"])
def test_unenrolled_principal_never_reaches_the_ingress(fault, rsa_key):
    settings, _current, _token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    sends = []

    async def send(path, frame):
        sends.append(frame)
        raise AssertionError("an unenrolled principal reached the Executive ingress")

    app._client.send_frame = send
    changes = {"client": {"client_id": "other-client"}, "subject": {"sub": "other-user"}}
    token = fixture._token(rsa_key, scope=" ".join(COO_SCOPES), **changes.get(fault, {}))
    if fault == "scope":
        token = fixture._token(rsa_key, scope="mastermind.executive.read")
    result = asyncio.run(_call(app, token, "mmx_delegate",
                               {"action": "selected_child_submit", "command": COMMAND}))
    assert result.status_code in (401, 403), result.text
    assert sends == []


# ---------------------------------------------------------------------------
# 4. The App keeps the original command across the transport boundary
# ---------------------------------------------------------------------------


def test_a_lost_post_send_response_keeps_the_original_command_as_unknown(rsa_key):
    settings, _current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    sends = []

    async def send(path, frame):
        sends.append(frame)
        raise RuntimeError("PRIVATE_POST_SEND_FAILURE")

    app._client.send_frame = send
    result = asyncio.run(_call(app, token, "mmx_delegate",
                               {"action": "selected_child_submit", "command": COMMAND}))
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "EFFECT_UNKNOWN", body
    assert body["command_id"] == COMMAND, body
    assert body["live_submit"] is None, body
    assert "PRIVATE" not in result.text
    # One send only: no retry, no resubmit, no alternative carrier.
    assert len(sends) == 1


@pytest.mark.parametrize("outcome", [
    "malformed", "foreign_command", "foreign_job", "oversized",
    "missing_live_submit", "missing_digest", "wrong_digest",
    "active_without_attempt", "false_live_attempt", "unhashable_state",
])
def test_a_malformed_post_send_return_keeps_the_original_command_as_unknown(outcome, rsa_key):
    settings, _current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    sends = []

    async def send(path, frame):
        sends.append(frame)
        if outcome == "malformed":
            return CeoIngressResponse("sent_ok", ok=True, result={"schema": "wrong.v1"})
        body = {
            "schema": "mastermind.hermes_delegate.selected_child/v1",
            "state": "ACTIVE", "reason": None,
            "command_id": COMMAND, "job_id": CHILD_JOB, "attempt_id": "attempt-0001",
            "attempt_status": "CLAIMED", "job_status": "RUNNING",
            "live_submit": True, "target_digest": frame["target_digest"],
        }
        if outcome == "foreign_command":
            body["command_id"] = "coo-cycle:JOB-001:dispatch:JOB-999:attempt:1"
        elif outcome == "foreign_job":
            body["job_id"] = "JOB-999"
        elif outcome == "oversized":
            body["reason"] = "x" * 300000
        elif outcome == "missing_live_submit":
            body.pop("live_submit")
        elif outcome == "missing_digest":
            body.pop("target_digest")
        elif outcome == "wrong_digest":
            body["target_digest"] = "0" * 64
        elif outcome == "active_without_attempt":
            body["attempt_id"] = None
            body["attempt_status"] = None
        elif outcome == "false_live_attempt":
            body["live_submit"] = False
        else:
            body["state"] = []
        return CeoIngressResponse("sent_ok", ok=True, result=body)

    app._client.send_frame = send
    result = asyncio.run(_call(app, token, "mmx_delegate",
                               {"action": "selected_child_submit", "command": COMMAND}))
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "EFFECT_UNKNOWN", body
    assert body["command_id"] == COMMAND, body
    assert len(sends) == 1


def test_a_failed_status_observation_is_unavailable_with_the_original_command(rsa_key):
    settings, _current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())

    async def send(path, frame):
        return CeoIngressResponse("sent_ok", ok=False,
                                   error={"code": "internal_error", "message": "private"})

    app._client.send_frame = send
    result = asyncio.run(_call(app, token, "mmx_delegate",
                               {"action": "selected_child_status", "command": COMMAND}))
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "UNAVAILABLE", body
    assert body["command_id"] == COMMAND, body
    assert body["live_submit"] is None, body


def test_a_proven_not_sent_transport_is_a_refusal_not_an_effect(rsa_key):
    settings, _current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())

    async def send(path, frame):
        return CeoIngressResponse("not_sent")

    app._client.send_frame = send
    result = asyncio.run(_call(app, token, "mmx_delegate",
                               {"action": "selected_child_submit", "command": COMMAND}))
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "REFUSED", body
    assert body["reason"] == "EXECUTIVE_SELECTED_CHILD_NOT_SENT", body
    assert body["live_submit"] is False, body


def test_the_private_frame_carries_only_host_authority(rsa_key):
    settings, current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    frames = []

    async def send(path, frame):
        frames.append(frame)
        return CeoIngressResponse("sent_ok", ok=True, result={
            "schema": "mastermind.hermes_delegate.selected_child/v1",
            "state": "NOT_CLAIMED", "reason": "EXECUTIVE_SELECTED_CHILD_NOT_CLAIMED",
            "command_id": COMMAND, "job_id": CHILD_JOB, "attempt_id": None,
            "attempt_status": None, "job_status": "QUEUED", "live_submit": False,
            "target_digest": frame["target_digest"]})

    app._client.send_frame = send
    result = asyncio.run(_call(app, token, "mmx_delegate",
                               {"action": "selected_child_status", "command": COMMAND}))
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "NOT_CLAIMED"
    frame = frames[0]
    assert frame["schema"] == INTEGRATION_FRAME_SCHEMA
    assert frame["request"] == {"action": "selected_child_status", "command": COMMAND}
    assert frame["principal"] == principal_frame(
        asyncio.run(app.authorize_token(token))[0])
    assert set(frame["principal_context"]) == {
        "work_ref", "principal_binding_digest", "mission_authority_ref",
        "authority_generation_digest"}
    assert frame["target_digest"] == _target().material_digest()
    assert frame["capability_profile_digest"] == \
        current["authority"].capability_profile_digest
    assert "idempotency_key" not in frame


# ---------------------------------------------------------------------------
# 5. The real Control path
# ---------------------------------------------------------------------------


class _SealingSupervisor(_FakeSupervisor):
    """Seal the real role result; only the provider process is inert."""

    async def finish_job(self, active):
        if self.finish_gate is not None:
            await self.finish_gate.wait()
        dispatch_receipt = SimpleNamespace(
            attempt=active.lease.attempt, lease_token=active.lease.lease_token)
        job = self.runtime.jobs.get_job(dispatch_receipt.attempt.job_id)
        body = {
            "schema_version": "mastermind.work_result/v1",
            "root_job_id": job.root_job_id,
            "plan_attempt_id": job.plan_attempt_id,
            "plan_digest": job.plan_digest,
            "plan_step_id": job.plan_step_id,
            "repair_round": job.repair_round,
            "artifacts": [], "evidence_digests": [],
        }
        return _complete_ohf_role(
            self.runtime, dispatch_receipt, body,
            identity_seed=61000 + int(job.job_id.split("-")[1]),
        )


def _admit_work_child(service, root):
    runtime = service.runtime
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id=service.config.worker_id,
    )
    _complete(runtime, dispatch, _plan_body(dispatch, root))
    children = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}",
    )
    return children[0]


async def _send_frame(path, value):
    reader, writer = await asyncio.open_unix_connection(path)
    writer.write(json.dumps(value).encode() + b"\n")
    await writer.drain()
    reply = json.loads(await reader.readline())
    writer.close()
    await writer.wait_closed()
    return reply


@asynccontextmanager
async def _control(tmp_path, socket_root, *, name, armed=True, guard=None):
    """A real Control service with the real App peer on the existing ingress."""

    from tests.test_executive_coo_host import (
        MISSION_AUTHORITY_VERSION, setup as host_setup,
    )
    from tests.test_coo_principal_mandate import mission_doc

    config = _config(tmp_path, socket_root=socket_root, coo_autonomy_armed=True,
                     coo_tick_interval_seconds=3600.0)
    holder = {"finish_gate": asyncio.Event()}

    def factory(runtime: Runtime):
        supervisor = _SealingSupervisor(runtime, finish_gate=holder["finish_gate"])
        holder["supervisor"] = supervisor
        return supervisor

    uid = os.geteuid()
    binding = CeoIngressAppBinding(
        peer_uid=uid, armed=False,
        grounding_provider=SimpleNamespace(observe=lambda: {}),
        principal_admission_armed=armed,
        principal_admission_guard=guard or (lambda _value: None))
    service = ExecutiveControlService(
        config, supervisor_factory=factory, autonomy_guard=(lambda: None),
        terminal_return_projector=lambda candidate: _capture_projection([], candidate),
        ceo_ingress_socket_path=socket_root / "selected-child.sock",
        ceo_ingress_peer_uid=uid + 1,
        ceo_ingress_grounding_provider=SimpleNamespace(observe=lambda: {}),
        ceo_ingress_armed=False, ceo_ingress_app_binding=binding)
    await service.start()
    try:
        assert (await _request(service, "register-worker"))["ok"] is True
        _register_peer(service)
        intent = _coo_intent(config, name)
        receipt = service._submit_service_intent(intent)
        root = service.runtime.jobs.get_job(receipt["job_id"])
        work = _admit_work_child(service, root)
        authority_dir = tmp_path / "selected-child-authority"
        authority_dir.mkdir()
        with pytest.MonkeyPatch.context() as patch:
            host, authority_config, _principal, _path = host_setup(authority_dir)
            authority_config["missions"][0].update(
                authority_version=MISSION_AUTHORITY_VERSION,
                principal_actions=["bounded_intent", "governed_orchestration"])
            document = json.loads(
                json.dumps(mission_doc()).replace('"JOB-100"', json.dumps(root.job_id)))
            patch.setattr(host.workspace, "read_mission_for_work_ref",
                          lambda work_ref: document)
            target = ExecutiveSelectedChildTarget(
                work_ref=WORK_REF,
                children=(ExecutiveSelectedChild(
                    selection=_frozen_selection(work), attempt_ordinal=1),),
                currentness_guard=lambda: None)
            service._ceo_ingress_app_binding = dataclasses.replace(
                service._ceo_ingress_app_binding,
                principal_facts_factory=lambda runtime: host,
                selected_child_target=target)
            yield SimpleNamespace(
                service=service, root=root, work=work, target=target,
                host=host, authority_config=authority_config, document=document,
                socket=socket_root / "selected-child.sock",
                finish_gate=holder["finish_gate"])
    finally:
        await service.close()


def _real_command(work) -> str:
    """The canonical command the host froze for this real child."""

    return f"coo-cycle:{work.root_job_id}:dispatch:{work.job_id}:attempt:1"


def _control_context(host) -> dict:
    """The frame's authority material, taken from the installed host facts."""

    row, fact, authority = host.host.source.snapshot(WORK_REF)
    return {
        "principal": {
            "policy_id": fact.policy_id, "issuer_digest": fact.issuer_digest,
            "subject_digest": fact.subject_digest, "client_ref": fact.client_ref,
            "resource": fact.resource_ref, "scopes": list(fact.scopes)},
        "principal_context": dataclasses.asdict(PrincipalAdmissionContext(
            row["work_ref"], fact.principal_binding_digest,
            authority.mission_authority_ref, authority.authority_generation_digest)),
        "capability_profile_digest": authority.capability_profile_digest,
        "target_digest": host.target.material_digest(),
    }


def _frame_for(context, *, command=COMMAND, action="selected_child_submit",
               principal=None, target_digest=None, capability_digest=None,
               work_ref=WORK_REF):
    return {
        "schema": SELECTED_CHILD_FRAME_SCHEMA,
        "request": {"action": action, "command": command},
        "target_digest": target_digest if target_digest is not None
        else context["target_digest"],
        "principal": principal if principal is not None else context["principal"],
        "principal_context": context["principal_context"],
        "capability_profile_digest": capability_digest
        if capability_digest is not None else context["capability_profile_digest"],
    }


async def _mcp_call(client, token, name, arguments):
    """One real signed MCP tool call over the static COO route."""

    headers = {"authorization": "Bearer " + token,
               "accept": "application/json, text/event-stream",
               "mcp-protocol-version": "2025-06-18"}
    response = await client.post("/mcp/coo", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    reply = body["result"]
    assert reply["isError"] is False, reply
    return json.loads(reply["content"][0]["text"])


async def _installed_app(host, rsa_key, *, socket_path):
    """The real App over the installed principal facts and the Control's target.

    The App and the Control read the same installed binding and the same
    frozen target. Neither derives a child from the model.
    """

    from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
    from integrations.mastermind_executive_app.coo_binding import _digest
    from tests.test_executive_coo_install_binding import policy as install_policy

    subject = "c29-selected-child-subject"
    raw = install_policy("executive-coo", list(COO_SCOPES))
    digest = subject_digest(issuer=raw["issuer"], subject=subject)
    raw["allowed_subject_digests"] = [digest]
    read_raw = install_policy("executive-read", ["mastermind.executive.read"])
    read_raw["allowed_subject_digests"] = [digest]
    submit_raw = install_policy("executive-submit", [
        "mastermind.executive.intent.submit", "mastermind.executive.read"])
    submit_raw["allowed_subject_digests"] = [digest]
    cache = fixture._FakeJwksCache(rsa_key)
    token = fixture._token(rsa_key, scope=" ".join(COO_SCOPES), iss=raw["issuer"],
                           aud=raw["resource"], sub=subject, client_id=CLIENT)
    coo_policy = load_resource_policy(raw)
    principal = await JwtAuthenticator(
        policy=coo_policy, jwks_cache=cache).verify_token(token, now=fixture.NOW)
    binding = {"schema": BINDING_SCHEMA, "enabled": True,
               "binding": {**principal_frame(principal), "permission_digest": "a" * 64}}
    # Both receivers enroll the same signed disposable principal under
    # the same exact policy; neither bypasses subject/binding validation.
    host.authority_config["policy"] = dict(raw)
    host.authority_config["binding"] = binding
    host.authority_config["missions"][0]["principal_binding_digest"] = \
        _digest(binding["binding"])
    base = AppSettings(
        policies=AppPolicies(load_resource_policy(read_raw),
                             load_resource_policy(submit_raw)),
        mastermind_root=Path(tempfile.mkdtemp(prefix="mmx-c29-root-", dir="/tmp")),
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=socket_path,
        read_from_ceo_ingress=True, jwks_cache=cache, clock=lambda: fixture.NOW)
    settings = CooAppSettings(
        executive=base, policy=coo_policy, load_binding=lambda: binding,
        authority_provider=lambda p, work: host.host.source.snapshot(work)[2],
        mission_provider=lambda p, work: host.host.workspace.read_mission_for_work_ref(work),
        selected_child_target=host.target)
    return settings, token


def test_a_signed_mcp_request_reaches_the_control_and_claims_one_frozen_child(
        tmp_path, rsa_key):
    """The real MCP edge, the real Unix socket and the real C17 composition."""

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root,
                                name="selected-child-ingress") as host:
                service = host.service
                command = _real_command(host.work)
                settings, token = await _installed_app(host, rsa_key,
                                                       socket_path=host.socket)
                app = server.build_web_ceo_v2_with_coo_mcp_app(
                    settings.executive, coo_settings=settings,
                    audit_sink=app_fixture.Sink())
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://127.0.0.1") as client:
                        envelope = await _mcp_call(client, token, "mmx_delegate", {
                            "action": "selected_child_submit", "command": command})
                        assert envelope["schema"] == \
                            "mastermind.hermes_delegate.selected_child/v1", envelope
                        assert envelope["state"] in {"ACTIVE", "COMPLETED"}, envelope
                        assert envelope["command_id"] == command, envelope
                        assert envelope["job_id"] == host.work.job_id, envelope
                        assert envelope["target_digest"] == host.target.material_digest()
                        attempt_id = envelope["attempt_id"]
                        assert isinstance(attempt_id, str) and attempt_id
                        assert envelope["live_submit"] is True, envelope
                        assert service.runtime.jobs.get_job(
                            host.work.job_id).attempt_count == 1
                        # The Runtime really owns that one canonical Attempt.
                        claimed = service.runtime.attempts.get_attempt(attempt_id)
                        assert claimed is not None
                        assert claimed.job_id == host.work.job_id
                        assert claimed.status is AttemptStatus.CLAIMED
                        host.finish_gate.set()
                        await asyncio.sleep(0.05)
                        # The same original command is observed. It never
                        # starts a second child and never recomputes an ordinal.
                        observed = await _mcp_call(client, token, "mmx_delegate", {
                            "action": "selected_child_status", "command": command})
                        assert observed["attempt_id"] == attempt_id, observed
                        assert observed["command_id"] == command, observed
                        assert observed["target_digest"] == host.target.material_digest()
                        assert service.runtime.jobs.get_job(
                            host.work.job_id).attempt_count == 1

    asyncio.run(exercise())


def test_an_app_target_that_differs_from_the_control_target_refuses(tmp_path, rsa_key):
    """The App and the Control must hold the same frozen material."""

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root,
                                name="selected-child-mismatch") as host:
                service = host.service
                command = _real_command(host.work)
                settings, token = await _installed_app(host, rsa_key,
                                                       socket_path=host.socket)
                # The App holds a different frozen material than the Control.
                original_child = host.target.children[0]
                other_child = dataclasses.replace(
                    original_child,
                    selection=dataclasses.replace(
                        original_child.selection, plan_digest="f" * 64))
                other = ExecutiveSelectedChildTarget(
                    work_ref=WORK_REF, children=(other_child,),
                    currentness_guard=lambda: None)
                assert other_child.command_id == command
                assert other.material_digest() != host.target.material_digest()
                settings = dataclasses.replace(settings, selected_child_target=other)
                app = server.build_web_ceo_v2_with_coo_mcp_app(
                    settings.executive, coo_settings=settings,
                    audit_sink=app_fixture.Sink())
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://127.0.0.1") as client:
                        envelope = await _mcp_call(client, token, "mmx_delegate", {
                            "action": "selected_child_submit", "command": command})
                        # A generic post-send error cannot prove a no-effect
                        # result at the App, even when this fixture proves it.
                        assert envelope["state"] == "EFFECT_UNKNOWN", envelope
                        assert envelope["live_submit"] is None, envelope
                        assert service.runtime.jobs.get_job(
                            host.work.job_id).attempt_count == 0

    asyncio.run(exercise())


def test_private_selected_child_frame_reaches_control_and_claims_one_child(tmp_path):
    """The private Unix ingress and the real C17 composition."""

    from tests.test_executive_coo_host import setup as host_setup

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root, name="selected-child-ingress") as host:
                service = host.service
                binding = service._ceo_ingress_app_binding
                target = host.target
                # The installed source that owns the principal's real facts.
                source = host.host
                context = _control_context(host)
                command = _real_command(host.work)
                frame = _frame_for(context, command=command)
                reply = await _send_frame(host.socket, frame)
                assert reply["ok"] is True, reply
                envelope = reply["result"]
                assert envelope["schema"] == "mastermind.hermes_delegate.selected_child/v1"
                assert envelope["state"] in {"ACTIVE", "COMPLETED"}, envelope
                assert envelope["command_id"] == command, envelope
                assert envelope["job_id"] == host.work.job_id, envelope
                assert envelope["target_digest"] == host.target.material_digest()
                attempt_id = envelope["attempt_id"]
                assert isinstance(attempt_id, str) and attempt_id
                assert service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1
                host.finish_gate.set()
                await asyncio.sleep(0.05)
                # The same original command is observed, never a second child.
                status = await _send_frame(
                    host.socket,
                    _frame_for(context, command=command, action="selected_child_status"))
                assert status["ok"] is True, status
                assert status["result"]["attempt_id"] == attempt_id, status
                assert service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["digest", "principal", "context", "capability", "command"])
def test_a_forged_private_frame_never_dispatches(tmp_path, fault):
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root, name="selected-child-forged") as host:
                service = host.service
                source = host.host
                context = _control_context(host)
                command = _real_command(host.work)
                frame = _frame_for(context, command=command)
                if fault == "digest":
                    frame["target_digest"] = "0" * 64
                elif fault == "principal":
                    frame["principal"] = dict(frame["principal"],
                                              subject_digest="f" * 64)
                elif fault == "context":
                    frame["principal_context"] = dict(frame["principal_context"],
                                                      authority_generation_digest="f" * 64)
                elif fault == "capability":
                    frame["capability_profile_digest"] = "f" * 64
                else:
                    frame["request"] = {"action": "selected_child_submit",
                                         "command": "coo-cycle:JOB-001:dispatch:JOB-999:attempt:1"}
                    assert frame["request"]["command"] != command
                reply = await _send_frame(host.socket, frame)
                assert reply["ok"] is False, reply
                assert reply["error"]["code"] in {
                    "invalid_input", "authority_refused", "ingress_unavailable"}, reply
                assert service.runtime.jobs.get_job(host.work.job_id).attempt_count == 0

    asyncio.run(exercise())


def test_a_moved_currentness_guard_refuses_before_any_claim(tmp_path):
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root, name="selected-child-current") as host:
                service = host.service
                source = host.host
                context = _control_context(host)
                command = _real_command(host.work)
                moved = ExecutiveSelectedChildTarget(
                    work_ref=WORK_REF, children=host.target.children,
                    currentness_guard=lambda: (_ for _ in ()).throw(
                        ValueError("the installed generation moved")))
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding, selected_child_target=moved)
                reply = await _send_frame(host.socket, _frame_for(context, command=command))
                assert reply["ok"] is False, reply
                assert service.runtime.jobs.get_job(host.work.job_id).attempt_count == 0

    asyncio.run(exercise())


def test_a_revoked_principal_at_the_claim_boundary_produces_no_attempt(tmp_path):
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root, name="selected-child-revoked") as host:
                service = host.service
                source = host.host
                context = _control_context(host)
                # The principal is revoked before the fresh claim boundary.
                host.authority_config["missions"][0]["enabled"] = False
                reply = await _send_frame(
                    host.socket, _frame_for(context, command=_real_command(host.work)))
                assert reply["ok"] is True, reply
                envelope = reply["result"]
                assert envelope["state"] == "REFUSED", envelope
                assert envelope["attempt_id"] is None, envelope
                assert envelope["live_submit"] is False, envelope
                assert service.runtime.jobs.get_job(host.work.job_id).attempt_count == 0

    asyncio.run(exercise())


def test_status_reports_the_original_without_a_fresh_new_effect_grant(tmp_path):
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root, name="selected-child-replay") as host:
                service = host.service
                source = host.host
                context = _control_context(host)
                command = _real_command(host.work)
                first = await _send_frame(host.socket, _frame_for(context, command=command))
                assert first["ok"] is True, first
                attempt_id = first["result"]["attempt_id"]
                # The fresh new-effect admission is withdrawn. The original
                # command stays observable; no second child is started.
                host.authority_config["missions"][0]["enabled"] = False
                replay = await _send_frame(
                    host.socket,
                    _frame_for(context, command=command, action="selected_child_status"))
                assert replay["ok"] is True, replay
                assert replay["result"]["attempt_id"] == attempt_id, replay
                assert service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("action,state", [
    ("selected_child_submit", "EFFECT_UNKNOWN"),
    ("selected_child_status", "UNAVAILABLE"),
])
@pytest.mark.parametrize("fault", ["authority_refused", "invalid_input", "internal_error"])
def test_generic_post_send_errors_never_prove_no_effect(action, state, fault, rsa_key):
    settings, _current, token = _app_settings(rsa_key, _target())
    app = create_coo_app(settings, audit_sink=app_fixture.Sink())
    sends = []

    async def send(path, frame):
        sends.append(frame)
        return CeoIngressResponse("sent_ok", ok=False,
                                  error={"code": fault, "message": "PRIVATE"})

    app._client.send_frame = send
    response = asyncio.run(_call(
        app, token, "mmx_delegate", {"action": action, "command": COMMAND}))
    body = response.json()
    assert body["state"] == state
    assert body["command_id"] == COMMAND
    assert body["live_submit"] is None
    assert body["attempt_id"] is None
    assert "target_digest" not in body
    assert "PRIVATE" not in response.text
    assert len(sends) == 1


@pytest.mark.parametrize("action,state", [
    ("selected_child_submit", "EFFECT_UNKNOWN"),
    ("selected_child_status", "UNAVAILABLE"),
])
@pytest.mark.parametrize("fault", ["malformed", "http_failure"])
def test_mcp_lost_app_reply_preserves_possible_effect(
        tmp_path, rsa_key, monkeypatch, action, state, fault):
    from starlette.responses import JSONResponse

    calls = []
    original = CooApp._selected_child

    async def lose_reply(self, request, authenticated, validated):
        calls.append(validated["command"])
        reply = await original(self, request, authenticated, validated)
        if fault == "http_failure":
            return JSONResponse(json.loads(reply.body), status_code=503)
        return JSONResponse({"schema": "wrong.v1"})

    monkeypatch.setattr(CooApp, "_selected_child", lose_reply)

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c38-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="selected-lost-app") as host:
                command = _real_command(host.work)
                settings, token = await _installed_app(host, rsa_key, socket_path=host.socket)
                if action == "selected_child_status":
                    seeded = await _send_frame(
                        host.socket, _frame_for(_control_context(host), command=command))
                    assert seeded["ok"] is True
                    assert seeded["result"]["attempt_id"]
                app = server.build_web_ceo_v2_with_coo_mcp_app(
                    settings.executive, coo_settings=settings, audit_sink=app_fixture.Sink())
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(
                            transport=httpx.ASGITransport(app=app),
                            base_url="http://127.0.0.1") as client:
                        result = await _mcp_call(client, token, "mmx_delegate",
                                                 {"action": action, "command": command})
                assert result["state"] == state
                assert result["command_id"] == command
                assert result["live_submit"] is None
                assert result["attempt_id"] is None
                assert "target_digest" not in result
                assert host.service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1
                assert calls == [command]

    asyncio.run(exercise())


@pytest.mark.parametrize("action,state", [
    ("selected_child_submit", "EFFECT_UNKNOWN"),
    ("selected_child_status", "UNAVAILABLE"),
])
@pytest.mark.parametrize("movement", ["binding_generation", "principal_revoked", "authority_context"])
def test_control_rechecks_read_authority_after_await_before_disclosure(
        tmp_path, rsa_key, action, state, movement):
    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c38-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="selected-late-read") as host:
                service = host.service
                command = _real_command(host.work)
                settings, token = await _installed_app(host, rsa_key, socket_path=host.socket)
                seeded = await _send_frame(
                    host.socket, _frame_for(_control_context(host), command=command))
                assert seeded["ok"] is True
                attempt_id = seeded["result"]["attempt_id"]
                assert attempt_id
                entered, release = asyncio.Event(), asyncio.Event()
                original_status = service.selected_child_status
                original_response = service._send_ceo_ingress_response
                private_replies = []

                async def paused_status(**kwargs):
                    result = await original_status(**kwargs)
                    entered.set()
                    await release.wait()
                    return result

                async def capture_response(writer, body):
                    private_replies.append(body)
                    return await original_response(writer, body)

                service.selected_child_status = paused_status
                service._send_ceo_ingress_response = capture_response
                app = server.build_web_ceo_v2_with_coo_mcp_app(
                    settings.executive, coo_settings=settings, audit_sink=app_fixture.Sink())
                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(
                            transport=httpx.ASGITransport(app=app),
                            base_url="http://127.0.0.1") as client:
                        task = asyncio.create_task(_mcp_call(
                            client, token, "mmx_delegate", {"action": action, "command": command}))
                        try:
                            await asyncio.wait_for(entered.wait(), timeout=5)
                            if movement == "binding_generation":
                                service._ceo_ingress_app_binding = dataclasses.replace(
                                    service._ceo_ingress_app_binding)
                            elif movement == "principal_revoked":
                                # Replace the Control's binding; the App keeps
                                # its original object, isolating the late guard.
                                host.authority_config["binding"] = {
                                    "schema": BINDING_SCHEMA, "enabled": False, "binding": None}
                            else:
                                host.authority_config["missions"][0]["mission_authority_ref"] = \
                                    "mission-authority:replacement"
                        finally:
                            release.set()
                        result = await asyncio.wait_for(task, timeout=5)
                # Assert the private boundary too: an App-side recheck must
                # not conceal a missing Control-side currentness check.
                assert len(private_replies) == 1
                assert private_replies[0]["ok"] is False
                assert private_replies[0]["error"]["code"] == "internal_error"
                assert "result" not in private_replies[0]
                assert result["state"] == state
                assert result["command_id"] == command
                assert result["attempt_id"] is None
                assert result["live_submit"] is None
                assert "target_digest" not in result
                assert service.runtime.jobs.get_job(host.work.job_id).attempt_count == 1
                assert service.runtime.attempts.get_attempt(attempt_id) is not None

    asyncio.run(exercise())


@pytest.mark.parametrize("code", [
    "authorization_missing", "token_expired", "token_signature_refused",
    "issuer_refused", "resource_refused", "subject_refused",
    "jwks_unavailable", "scope_refused",
])
def test_mcp_preserves_inner_authentication_preflight_and_challenge(rsa_key, monkeypatch, code):
    from starlette.responses import JSONResponse

    settings, _current, token = _app_settings(rsa_key, None)
    challenge = 'Bearer resource_metadata="https://example.test/protected-resource"'

    async def refuse_inner(self, request):
        return JSONResponse(
            {"ok": False, "error": {"code": code, "message": "Authorization required"}},
            status_code=403 if code == "scope_refused" else 401,
            headers={"www-authenticate": challenge})

    monkeypatch.setattr(CooApp, "_auth", refuse_inner)

    async def exercise():
        app = server.build_web_ceo_v2_with_coo_mcp_app(
            settings.executive, coo_settings=settings, audit_sink=app_fixture.Sink())
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1") as client:
                response = await client.post("/mcp/coo", headers={
                    "authorization": "Bearer " + token,
                    "accept": "application/json, text/event-stream",
                    "mcp-protocol-version": "2025-06-18",
                }, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "mmx_delegate", "arguments": {
                             "action": "selected_child_submit", "command": COMMAND}}})
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["isError"] is True
        assert result["_meta"]["mcp/www_authenticate"] == [challenge]
        payload = json.loads(result["content"][0]["text"])
        assert payload["error"]["code"] == code
        assert payload["ok"] is False
        assert "target_digest" not in payload

    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# 6. The tool projection and the capability sources agree
# ---------------------------------------------------------------------------


def test_the_tool_projection_and_capability_digests_agree():
    from common.claude_principal_capability_contract import (
        EXECUTIVE_COO_MCP_ENABLED_TOOLS, EXECUTIVE_COO_MCP_TOOL_SCHEMA_DIGEST,
    )

    assert COO_TOOL_SCHEMA_DIGEST == coo_tool_schema_digest()
    assert EXECUTIVE_COO_MCP_TOOL_SCHEMA_DIGEST == COO_TOOL_SCHEMA_DIGEST
    assert EXECUTIVE_COO_MCP_ENABLED_TOOLS == tuple(sorted(COO_TOOL_NAMES))
    assert "mmx_delegate" in COO_TOOL_NAMES
    assert len(COO_TOOL_NAMES) == 7


def test_the_control_and_integration_frame_literals_are_identical():
    assert SELECTED_CHILD_FRAME_SCHEMA == INTEGRATION_FRAME_SCHEMA
    assert SELECTED_CHILD_FRAME_SCHEMA == "mastermind.ceo_ingress.selected_child.v1"


def test_the_parse_grammar_refuses_unhashable_scalars_normally():
    for value in ([], {}, 3, None, True):
        with pytest.raises(SubmissionError):
            parse_selected_child({"action": value, "command": COMMAND})


def test_the_control_never_imports_the_integration_package():
    import ast

    root = Path(__file__).resolve().parents[1]
    for path in sorted((root / "control_plane").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("integrations") for alias in node.names), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("integrations"), path


# ---------------------------------------------------------------------------
# 7. WO-13: the child-request admission lane on the private ingress
# ---------------------------------------------------------------------------


def test_child_request_admit_action_is_core_private_not_model_facing():
    """The admit action rides the private App-to-Control frame only.

    The core frame validator accepts it; the model-facing parser refuses
    it, so the pinned MCP tool surface is unchanged and the envelope
    never travels through the model.
    """

    from control_plane.executive_service import (
        SELECTED_CHILD_FRAME_SCHEMA as CORE_SCHEMA,
        _SELECTED_CHILD_ACTIONS as CORE_ACTIONS,
    )
    from integrations.hermes_delegate.schema import (
        SELECTED_CHILD_ACTIONS as MODEL_ACTIONS,
    )

    assert "selected_child_admit" in CORE_ACTIONS
    assert "selected_child_admit" not in MODEL_ACTIONS
    assert "selected_child_submit" in CORE_ACTIONS & MODEL_ACTIONS
    frame = {
        "schema": SELECTED_CHILD_FRAME_SCHEMA,
        "request": {"action": "selected_child_admit",
                    "command": "child-request:" + "0" * 64},
        "target_digest": "a" * 64,
        "principal": {"policy_id": "p", "issuer_digest": "i", "subject_digest": "s",
                      "client_ref": "c", "resource": "r", "scopes": ["a"]},
        "principal_context": {"work_ref": WORK_REF,
                              "principal_binding_digest": "a" * 64,
                              "mission_authority_ref": "mission-authority-01",
                              "authority_generation_digest": "a" * 64},
        "capability_profile_digest": "a" * 64,
    }
    from control_plane.executive_service import _selected_child_frame
    parsed = _selected_child_frame(frame)
    assert parsed == {"action": "selected_child_admit",
                      "command": "child-request:" + "0" * 64}
    assert CORE_SCHEMA == INTEGRATION_FRAME_SCHEMA


def _admission_material(root_ref, parent_ref, key, *, brief_digest="a" * 64):
    """The host-frozen envelope plus the command minted from its triple."""

    from control_plane.child_execution_contracts import ChildExecutionRequest
    from control_plane.child_request_admission import admission_command_id

    request = ChildExecutionRequest(
        root_ref=root_ref, immediate_parent_run_ref=parent_ref,
        logical_child_key=key, task_kind="research",
        requested_complexity="C2_COMPLEX_BOUNDED", brief_digest=brief_digest,
    )
    return admission_command_id(request), request.to_dict()


def test_private_child_request_admit_replay_and_digest_conflict(tmp_path):
    """The real Unix ingress: idempotent admission, conflict on drift."""

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root,
                                name="child-request-admit") as host:
                service = host.service
                context = _control_context(host)
                command, envelope = _admission_material(
                    host.root.job_id, host.root.job_id, "ingress-key-0001")
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={command: envelope})

                frame = _frame_for(context, command=command,
                                   action="selected_child_admit")
                reply = await _send_frame(host.socket, frame)
                assert reply["ok"] is True, reply
                admitted = reply["result"]
                assert admitted["schema"] == "mastermind.child_request_admission/v1"
                assert admitted["state"] == "ADMITTED", admitted
                job_id = admitted["job_id"]
                assert isinstance(job_id, str) and job_id

                # The same frozen command replays to the same Job handle.
                replay = await _send_frame(host.socket, frame)
                assert replay["ok"] is True, replay
                assert replay["result"]["state"] == "REPLAY", replay
                assert replay["result"]["job_id"] == job_id

                # An unfrozen admission command never reaches admission.
                unfrozen = await _send_frame(host.socket, _frame_for(
                    context, command="child-request:" + "e" * 64,
                    action="selected_child_admit"))
                assert unfrozen["ok"] is False, unfrozen
                assert unfrozen["error"]["code"] == "invalid_input", unfrozen

                # The host re-freezes the SAME key with a different goal
                # digest: a precise conflict, never a second Job.
                _, drifted = _admission_material(
                    host.root.job_id, host.root.job_id, "ingress-key-0001",
                    brief_digest="c" * 64)
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={command: drifted})
                conflict = await _send_frame(host.socket, frame)
                assert conflict["ok"] is False, conflict
                assert conflict["error"]["code"] == "conflict", conflict
                with service.runtime.store.read() as connection:
                    count = int(connection.execute(
                        "SELECT COUNT(*) FROM events e JOIN jobs j"
                        " ON j.job_id=e.job_id"
                        " WHERE e.event_type='JOB_CREATED'"
                        " AND json_extract(e.payload_json,"
                        " '$.provenance.child_request.schema')"
                        " = 'ChildExecutionRequest.v1'"
                    ).fetchone()[0])
                assert count == 1
                assert service.runtime.jobs.get_job(job_id).attempt_count == 0

    asyncio.run(exercise())


def test_private_child_request_admit_queue_full_wait_reason(
        tmp_path, monkeypatch):
    """A full ready queue returns precise backpressure, not a retry."""

    async def exercise():
        monkeypatch.setenv("MMOS_CHILD_ROOT_READY_LIMIT", "1")
        with tempfile.TemporaryDirectory(prefix="mmx-c29-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with _control(tmp_path, socket_root,
                                name="child-request-wait") as host:
                service = host.service
                context = _control_context(host)
                first_command, first = _admission_material(
                    host.root.job_id, host.root.job_id, "wait-key-0001")
                second_command, second = _admission_material(
                    host.root.job_id, host.root.job_id, "wait-key-0002")
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={
                        first_command: first, second_command: second})

                admitted = await _send_frame(host.socket, _frame_for(
                    context, command=first_command,
                    action="selected_child_admit"))
                assert admitted["ok"] is True, admitted
                assert admitted["result"]["state"] == "ADMITTED", admitted

                # The per-root cap (configured at one) sends the second
                # request back to the parent planner with a precise
                # reason.  Nothing was created; there is no retry loop.
                wait = await _send_frame(host.socket, _frame_for(
                    context, command=second_command,
                    action="selected_child_admit"))
                assert wait["ok"] is True, wait
                assert wait["result"]["state"] == "WAIT", wait
                assert wait["result"]["wait_reason"] == "CHILD_QUEUE_ROOT_READY_FULL"
                assert wait["result"]["wait_detail"]["root_ready"] == 1
                assert wait["result"]["wait_detail"]["root_limit"] == 1
                assert wait["result"]["job_id"] is None

                job_id = admitted["result"]["job_id"]
                assert service.runtime.jobs.get_job(job_id).attempt_count == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("fault", [
    "principal", "context", "capability", "root", "command", "governed",
    "closed_fresh",
])
def test_child_request_private_admission_reproves_host_authority(tmp_path, fault):
    from tests.test_hermes_selected_child_dispatch import _child_request_job_count

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-admit-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="admission-authority") as host:
                service = host.service
                if fault == "governed":
                    host.authority_config["missions"][0]["principal_actions"] = [
                        "bounded_intent"]
                context = _control_context(host)
                command, envelope = _admission_material(
                    "ROOT-FOREIGN" if fault == "root" else host.root.job_id,
                    host.root.job_id, "authority-key")
                if fault == "command":
                    command = "child-request:" + "f" * 64
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={command: envelope},
                    principal_admission_armed=fault != "closed_fresh")
                frame = _frame_for(
                    context, command=command, action="selected_child_admit")
                if fault == "principal":
                    frame["principal"] = dict(frame["principal"],
                                              subject_digest="f" * 64)
                elif fault == "context":
                    frame["principal_context"] = dict(
                        frame["principal_context"], authority_generation_digest="f" * 64)
                elif fault == "capability":
                    frame["capability_profile_digest"] = "f" * 64
                response = await _send_frame(host.socket, frame)
                assert response["ok"] is False, response
                assert "result" not in response
                assert _child_request_job_count(service.runtime) == 0

    asyncio.run(exercise())


@pytest.mark.parametrize("gate", ["armed", "mission"])
def test_child_request_replay_remains_readable_after_fresh_disarm(tmp_path, gate):
    from tests.test_hermes_selected_child_dispatch import _child_request_job_count

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-admit-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="admission-replay") as host:
                service = host.service
                context = _control_context(host)
                first, envelope = _admission_material(
                    host.root.job_id, host.root.job_id, "original")
                second, fresh = _admission_material(
                    host.root.job_id, host.root.job_id, "fresh")
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={first: envelope, second: fresh})
                frame = _frame_for(context, command=first, action="selected_child_admit")
                admitted = await _send_frame(host.socket, frame)
                assert admitted["ok"] is True, admitted
                assert admitted["result"]["state"] == "ADMITTED"
                if gate == "armed":
                    service._ceo_ingress_app_binding = dataclasses.replace(
                        service._ceo_ingress_app_binding, principal_admission_armed=False)
                else:
                    host.authority_config["missions"][0]["enabled"] = False
                replay = await _send_frame(host.socket, frame)
                assert replay["ok"] is True, replay
                assert replay["result"]["state"] == "REPLAY"
                assert replay["result"]["job_id"] == admitted["result"]["job_id"]
                refused = await _send_frame(host.socket, _frame_for(
                    context, command=second, action="selected_child_admit"))
                assert refused["ok"] is False, refused
                assert _child_request_job_count(service.runtime) == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("movement", ["principal", "material"])
def test_child_request_post_insert_movement_rolls_back_admission(
        tmp_path, monkeypatch, movement):
    from control_plane.child_execution_contracts import ChildExecutionRequest
    from tests.test_hermes_selected_child_dispatch import _child_request_job_count

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-admit-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="admission-rollback") as host:
                service = host.service
                context = _control_context(host)
                command, envelope = _admission_material(
                    host.root.job_id, host.root.job_id, "rollback")
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={command: envelope})
                original_insert = service.runtime.jobs._create_job_in_transaction
                inserted = []

                def insert_then_move(*args, **kwargs):
                    result = original_insert(*args, **kwargs)
                    inserted.append(True)
                    if movement == "principal":
                        host.authority_config["binding"] = {
                            "schema": BINDING_SCHEMA, "enabled": False, "binding": None}
                    else:
                        changed = dict(envelope)
                        changed.pop("request_digest")
                        changed["brief_digest"] = "b" * 64
                        replacement = ChildExecutionRequest.from_dict(changed).to_dict()
                        envelope.clear()
                        envelope.update(replacement)
                    return result

                monkeypatch.setattr(
                    service.runtime.jobs, "_create_job_in_transaction", insert_then_move)
                with service.runtime.store.read() as connection:
                    before = tuple(connection.execute(
                        "SELECT (SELECT COUNT(*) FROM jobs),"
                        " (SELECT COUNT(*) FROM events)").fetchone())
                response = await _send_frame(host.socket, _frame_for(
                    context, command=command, action="selected_child_admit"))
                assert inserted == [True]
                assert response["ok"] is False, response
                assert _child_request_job_count(service.runtime) == 0
                with service.runtime.store.read() as connection:
                    after = tuple(connection.execute(
                        "SELECT (SELECT COUNT(*) FROM jobs),"
                        " (SELECT COUNT(*) FROM events)").fetchone())
                assert after == before

    asyncio.run(exercise())


def test_child_request_rechecks_read_authority_before_replay_disclosure(
        tmp_path, monkeypatch):
    from tests.test_hermes_selected_child_dispatch import _child_request_job_count

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-admit-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="admission-readback") as host:
                service = host.service
                context = _control_context(host)
                command, envelope = _admission_material(
                    host.root.job_id, host.root.job_id, "readback")
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={command: envelope})
                frame = _frame_for(context, command=command, action="selected_child_admit")
                admitted = await _send_frame(host.socket, frame)
                assert admitted["ok"] is True, admitted
                original_admit = service.runtime.jobs.admit_child_execution_request

                def observe_then_revoke(*args, **kwargs):
                    result = original_admit(*args, **kwargs)
                    assert result.state == "REPLAY"
                    host.authority_config["binding"] = {
                        "schema": BINDING_SCHEMA, "enabled": False, "binding": None}
                    return result

                monkeypatch.setattr(
                    service.runtime.jobs, "admit_child_execution_request",
                    observe_then_revoke)
                response = await _send_frame(host.socket, frame)
                assert response["ok"] is False, response
                assert response["error"]["code"] == "internal_error"
                assert "result" not in response
                assert _child_request_job_count(service.runtime) == 1
                assert service.runtime.jobs.get_job(admitted["result"]["job_id"]) is not None

    asyncio.run(exercise())


@pytest.mark.parametrize("retained", [False, True])
def test_child_request_private_legacy_key_only_observes_retained_work(tmp_path, retained):
    from hashlib import sha256
    from control_plane.child_execution_contracts import ChildExecutionRequest
    from tests.test_hermes_selected_child_dispatch import (
        _child_request_job_count, _seed_legacy_child_admission,
    )

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-admit-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="admission-legacy") as host:
                service = host.service
                context = _control_context(host)
                canonical, envelope = _admission_material(
                    host.root.job_id, host.root.job_id + "\x1fP", "K")
                request = ChildExecutionRequest.from_dict(envelope)
                legacy = "child-request:" + sha256(
                    "\x1f".join(request.idempotency_key()).encode()).hexdigest()
                assert canonical != legacy
                original_job = None
                if retained:
                    original_job, original_command = _seed_legacy_child_admission(
                        service.runtime, request)
                    assert original_command == legacy
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={legacy: envelope, canonical: envelope},
                    principal_admission_armed=not retained)
                response = await _send_frame(host.socket, _frame_for(
                    context, command=legacy, action="selected_child_admit"))
                if retained:
                    assert response["ok"] is True, response
                    assert response["result"]["state"] == "REPLAY"
                    assert response["result"]["command_id"] == legacy
                    assert response["result"]["job_id"] == original_job.job_id
                else:
                    assert response["ok"] is False, response
                    assert _child_request_job_count(service.runtime) == 0
                    admitted = await _send_frame(host.socket, _frame_for(
                        context, command=canonical, action="selected_child_admit"))
                    assert admitted["ok"] is True, admitted
                    assert admitted["result"]["state"] == "ADMITTED"
                    replay = await _send_frame(host.socket, _frame_for(
                        context, command=legacy, action="selected_child_admit"))
                    assert replay["ok"] is True, replay
                    assert replay["result"]["state"] == "REPLAY"
                    assert replay["result"]["command_id"] == canonical
                    assert replay["result"]["job_id"] == admitted["result"]["job_id"]
                assert _child_request_job_count(service.runtime) == 1

    asyncio.run(exercise())


def test_child_request_notes_change_does_not_change_admission_identity(
        tmp_path, monkeypatch):
    from tests.test_hermes_selected_child_dispatch import _child_request_job_count

    async def exercise():
        with tempfile.TemporaryDirectory(prefix="mmx-admit-", dir="/tmp") as directory:
            async with _control(tmp_path, Path(directory), name="admission-notes") as host:
                service = host.service
                context = _control_context(host)
                command, envelope = _admission_material(
                    host.root.job_id, host.root.job_id, "notes")
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={command: envelope})
                original_insert = service.runtime.jobs._create_job_in_transaction

                def insert_then_annotate(*args, **kwargs):
                    result = original_insert(*args, **kwargs)
                    envelope["notes"] = "A nonsemantic host annotation."
                    return result

                monkeypatch.setattr(
                    service.runtime.jobs, "_create_job_in_transaction", insert_then_annotate)
                response = await _send_frame(host.socket, _frame_for(
                    context, command=command, action="selected_child_admit"))
                assert response["ok"] is True, response
                assert response["result"]["state"] == "ADMITTED"
                assert response["result"]["request_digest"] == envelope["request_digest"]
                assert _child_request_job_count(service.runtime) == 1

    asyncio.run(exercise())
