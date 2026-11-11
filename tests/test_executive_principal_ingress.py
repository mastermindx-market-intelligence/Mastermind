"""Principal frames on the incumbent ingress; hermetic peer and Runtime proof."""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import json
import os
from pathlib import Path
import runpy
import tempfile
import pytest
from control_plane import executive_ceo_ingress as ingress
from control_plane.coo_principal_envelope import PrincipalAdmissionContext, derive_principal_envelope
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService

GROUNDING = dict(mastermind_sha="a" * 40, macro_sha="b" * 40,
                 boot_packet_schema="mastermind.ceo_boot_packet.v1")
SUBMIT = "mastermind.ceo_ingress.principal_submit.v1"
STATUS = "mastermind.ceo_ingress.principal_status.v1"
CONTEXT = PrincipalAdmissionContext("WS:EXECUTIVE-CAPACITY-FABRIC", "1" * 64,
                                    "authority:principal-ingress", "2" * 64)


class Grounding:
    def __init__(self):
        self.calls = 0
        self.value = dict(GROUNDING)
    def observe(self):
        self.calls += 1
        return dict(self.value)


def frame(root, **changes):
    request = dict(operation_key="principal-ingress-proof", objective="Inspect the assigned mission.",
        department="executive-infrastructure", priority=7, execution_profile="research_only",
        workstream=CONTEXT.work_ref)
    value = derive_principal_envelope(request, context=CONTEXT,
        workspace_root=str(root / "workspaces"), grounding=GROUNDING)
    result = dict(schema=SUBMIT, request_ref=value["request_ref"],
        principal_context=dataclasses.asdict(CONTEXT), observed_grounding=dict(GROUNDING),
        request=request)
    result.update(changes)
    return result


def allow(_value):
    return None


def call(root, value, *, provider=None, peer=True, guard=allow):
    return asyncio.run(ingress.handle_frame(value, runtime=Runtime.at(root / "runtime"),
        grounding_provider=provider or Grounding(), workspace_root=root / "workspaces",
        service_state="READY", principal_peer_authorized=peer,
        principal_admission_guard=guard))


def test_principal_frame_uses_the_existing_sink_and_role_neutral_receipt(tmp_path):
    result = call(tmp_path, frame(tmp_path))
    assert result["schema"] == "mastermind.executive_principal_intent_receipt.v1"
    assert result["status"] == "QUEUED" and result["dispatched"] is False
    assert result["principal"]["seat"] == "coo"


@pytest.mark.parametrize("peer,guard", [(False, allow), (None, allow), (1, allow), (True, None)])
def test_frame_requires_explicit_host_peer_and_guard(tmp_path, peer, guard):
    with pytest.raises(ingress.CeoIngressError):
        call(tmp_path, frame(tmp_path), peer=peer, guard=guard)
    assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []


def test_replay_and_status_do_not_observe_dynamic_grounding_or_guard(tmp_path):
    value = frame(tmp_path)
    original = call(tmp_path, value)
    class Unavailable:
        def observe(self):
            raise AssertionError("replay must not observe new grounding")
    def moved(_):
        raise AssertionError("dynamic mission state moved")
    duplicate = call(tmp_path, value, provider=Unavailable(), guard=moved)
    assert duplicate == dict(original, duplicate=True)
    status = {k: value[k] for k in ("request_ref", "principal_context")}
    status["schema"] = STATUS
    assert call(tmp_path, status, provider=Unavailable(), guard=moved) == original
    status["principal_context"]["principal_binding_digest"] = "3" * 64
    with pytest.raises(ingress.CeoIngressError) as error:
        call(tmp_path, status, provider=Unavailable(), guard=moved)
    assert error.value.code == "operation_conflict"


def test_changed_current_grounding_refuses_before_job_creation(tmp_path):
    provider = Grounding(); provider.value["mastermind_sha"] = "c" * 40
    with pytest.raises(ingress.CeoIngressError) as error:
        call(tmp_path, frame(tmp_path), provider=provider)
    assert error.value.code == "grounding_mismatch"
    assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []


def service(root, socket_root, *, app_peer=True, armed=True, guard=allow):
    fixtures = runpy.run_path(str(Path(__file__).with_name("test_executive_ceo_ingress.py")))
    config = fixtures["_config"](root, socket_root=socket_root, shutdown_grace_seconds=2)
    uid = os.geteuid()
    binding = CeoIngressAppBinding(peer_uid=uid if app_peer else uid + 1,
        armed=False, grounding_provider=Grounding(), principal_admission_armed=armed,
        principal_admission_guard=guard)
    return ExecutiveControlService(config,
        supervisor_factory=lambda _: fixtures["_FakeSupervisor"](),
        ceo_ingress_socket_path=socket_root / "principal.sock",
        ceo_ingress_peer_uid=uid + 1 if app_peer else uid,
        ceo_ingress_grounding_provider=Grounding(), ceo_ingress_armed=False,
        ceo_ingress_app_binding=binding)


async def send(path, value):
    reader, writer = await asyncio.open_unix_connection(path)
    writer.write(json.dumps(value).encode() + b"\n")
    await writer.drain()
    reply = json.loads(await reader.readline())
    writer.close(); await writer.wait_closed()
    return reply


def test_real_app_peer_can_submit_with_ceo_permission_disarmed(tmp_path):
    async def check():
        with tempfile.TemporaryDirectory(prefix="mmx-prin-", dir="/tmp") as temp:
            host = service(tmp_path, Path(temp))
            await host.start()
            try:
                result = await send(Path(temp) / "principal.sock", frame(tmp_path))
                assert result["ok"] is True, result
                assert result["result"]["principal"]["seat"] == "coo"
                assert result["result"]["dispatched"] is False
            finally:
                await host.close()
    asyncio.run(check())


@pytest.mark.parametrize("app_peer,armed,guard,expected", [
    (False, True, allow, "peer_denied"),
    (True, False, allow, "backend_refused"),
    (True, False, None, "peer_denied"),
])
def test_real_socket_refuses_c1_unarmed_and_unconfigured_principals(tmp_path, app_peer, armed, guard, expected):
    async def check():
        with tempfile.TemporaryDirectory(prefix="mmx-prin-", dir="/tmp") as temp:
            host = service(tmp_path, Path(temp), app_peer=app_peer, armed=armed, guard=guard)
            await host.start()
            try:
                result = await send(Path(temp) / "principal.sock", frame(tmp_path))
                assert result["ok"] is False
                assert result["error"]["code"] == expected
                assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []
            finally:
                await host.close()
    asyncio.run(check())


@pytest.mark.parametrize("extra", ["actor", "peer_uid", "principal_peer_authorized", "principal_admission_guard"])
def test_wire_fields_cannot_grant_peer_or_host_authority(tmp_path, extra):
    value = frame(tmp_path); value[extra] = "caller-claim"
    with pytest.raises(ingress.CeoIngressError) as error:
        call(tmp_path, value)
    assert error.value.code == "invalid_input"
    assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []


def test_real_status_and_replay_survive_new_admission_disarm(tmp_path):
    async def check():
        with tempfile.TemporaryDirectory(prefix="mmx-prin-", dir="/tmp") as temp:
            host = service(tmp_path, Path(temp)); await host.start()
            try:
                path = Path(temp) / "principal.sock"; value = frame(tmp_path)
                first = await send(path, value); assert first["ok"] is True
                binding = host._ceo_ingress_app_binding
                host._ceo_ingress_app_binding = dataclasses.replace(binding, principal_admission_armed=False)
                duplicate = await send(path, value)
                assert duplicate["ok"] is True and duplicate["result"]["duplicate"] is True
                assert duplicate["result"]["job_id"] == first["result"]["job_id"]
                status = {k: value[k] for k in ("request_ref", "principal_context")}
                status["schema"] = STATUS
                assert await send(path, status) == first
                changed = copy.deepcopy(value); changed["request"]["objective"] = "Changed semantics"
                conflict = await send(path, changed)
                assert conflict["ok"] is False and conflict["error"]["code"] == "operation_conflict"
                assert len(Runtime.at(tmp_path / "runtime").jobs.list_jobs()) == 1
            finally:
                await host.close()
    asyncio.run(check())


@pytest.mark.parametrize("change", ["binding", "arming", "service_state", "closing"])
def test_state_change_during_host_guard_refuses_before_effect(tmp_path, change):
    async def check():
        with tempfile.TemporaryDirectory(prefix="mmx-prin-", dir="/tmp") as temp:
            holder = {}
            def moving_guard(_):
                host = holder["host"]
                if change == "binding":
                    host._ceo_ingress_app_binding = dataclasses.replace(host._ceo_ingress_app_binding)
                elif change == "arming":
                    host._ceo_ingress_app_binding = dataclasses.replace(
                        host._ceo_ingress_app_binding, principal_admission_armed=False)
                elif change == "service_state":
                    host._service_state = "QUARANTINED"
                else:
                    host._closing = True
            host = service(tmp_path, Path(temp), guard=moving_guard)
            holder["host"] = host; await host.start()
            try:
                result = await send(Path(temp) / "principal.sock", frame(tmp_path))
                assert result["ok"] is False and result["error"]["code"] == "backend_refused"
                assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []
            finally:
                if change == "closing": host._closing = False
                await host.close()
    asyncio.run(check())


def test_socket_disconnect_preserves_the_original_effect_for_status(tmp_path):
    import threading
    entered, release = threading.Event(), threading.Event()
    def guard(_):
        entered.set()
        if not release.wait(timeout=10): raise RuntimeError("test guard not released")
    async def check():
        with tempfile.TemporaryDirectory(prefix="mmx-prin-", dir="/tmp") as temp:
            host = service(tmp_path, Path(temp), guard=guard); await host.start()
            try:
                path = Path(temp) / "principal.sock"; value = frame(tmp_path)
                reader, writer = await asyncio.open_unix_connection(path)
                writer.write(json.dumps(value).encode() + b"\n"); await writer.drain()
                assert await asyncio.to_thread(entered.wait, 5)
                writer.close(); await writer.wait_closed(); release.set()
                async def drained():
                    while host._ceo_ingress_tasks:
                        await asyncio.sleep(0.01)
                await asyncio.wait_for(drained(), timeout=5)
                status = {k: value[k] for k in ("request_ref", "principal_context")}
                status["schema"] = STATUS
                result = await send(path, status)
                assert result["ok"] is True and result["result"]["dispatched"] is False
                assert len(Runtime.at(tmp_path / "runtime").jobs.list_jobs()) == 1
            finally:
                release.set(); await host.close()
    asyncio.run(check())


@pytest.mark.parametrize("fault", ["request_ref", "mission", "binding_shape", "observed_shape"])
def test_principal_frame_identity_drift_refuses_before_grounding(tmp_path, fault):
    value = frame(tmp_path); provider = Grounding()
    if fault == "request_ref": value["request_ref"] = "req-coo-" + "f" * 32
    elif fault == "mission": value["principal_context"]["work_ref"] = "WS:OTHER"
    elif fault == "binding_shape": value["principal_context"]["actor"] = "coo-principal"
    else: value["observed_grounding"]["unexpected"] = True
    with pytest.raises(ingress.CeoIngressError) as error:
        call(tmp_path, value, provider=provider)
    assert error.value.code == "invalid_input" and provider.calls == 0
    assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []


def test_grounding_movement_between_samples_refuses_before_guard(tmp_path):
    class Moving(Grounding):
        def observe(self):
            value = super().observe()
            if self.calls > 1: value["mastermind_sha"] = "c" * 40
            return value
    def must_not_run(_): raise AssertionError("guard must not run on moved grounding")
    with pytest.raises(ingress.CeoIngressError) as error:
        call(tmp_path, frame(tmp_path), provider=Moving(), guard=must_not_run)
    assert error.value.code == "grounding_changed"
    assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []


def test_c1_principal_frame_is_refused_before_admission_dispatch(tmp_path, monkeypatch):
    calls = []
    async def must_not_dispatch(*args, **kwargs):
        calls.append(True)
        raise AssertionError("untrusted peer crossed the service frame gate")
    async def check():
        with tempfile.TemporaryDirectory(prefix="mmx-prin-", dir="/tmp") as temp:
            host = service(tmp_path, Path(temp), app_peer=False); await host.start()
            try:
                monkeypatch.setattr(ingress, "handle_frame", must_not_dispatch)
                result = await send(Path(temp) / "principal.sock", frame(tmp_path))
                assert result["ok"] is False and result["error"]["code"] == "peer_denied"
                assert calls == []
                assert Runtime.at(tmp_path / "runtime").jobs.list_jobs() == []
            finally:
                await host.close()
    asyncio.run(check())
