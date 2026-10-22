"""Source-only installed Control composition for a DEFAULT-OFF inference peer.

The only object being installed in this test is a temporary in-process
Executive service with mock launchd sockets. It cannot issue Auth0 credentials,
start a provider, submit a new service Job or mutate production configuration.
"""
import asyncio
import os
import socket
from pathlib import Path
from dataclasses import replace

import pytest

from control_plane.executive_service import CeoIngressInferenceBinding, ServiceError
from tests.test_executive_mcp_installed_fabric_composition import (
    _raw_for_factory, _patch_composition, _listening,
)


def compose(tmp_path, monkeypatch, overrides=None):
    socket_root=tmp_path / "socket"
    socket_root.mkdir(exist_ok=True)
    raw=_raw_for_factory(tmp_path,socket_root,profile="web_ceo_v2")
    raw.update(overrides or {})
    sockets={
        "Operator":_listening(Path(raw["control_socket_path"])),
        "CeoIngress":_listening(Path(raw["ceo_ingress_socket_path"])),
    }
    cli=_patch_composition(monkeypatch,sockets)
    try:
        service=cli._service_from_config(raw)
    except BaseException:
        for sock in sockets.values():sock.close()
        raise
    return cli,service,raw,sockets


def close_without_execution(service,sockets):
    async def shutdown():
        await service.close()
    try:asyncio.run(shutdown())
    finally:
        for sock in sockets.values():sock.close()


def test_original_install_without_new_fields_remains_disabled(tmp_path,monkeypatch):
    _cli,service,raw,sockets=compose(tmp_path,monkeypatch)
    try:
        assert service._ceo_ingress_inference_binding is None
        assert service._ceo_ingress_app_binding is not None
        assert service._ceo_ingress_armed is False
    finally:close_without_execution(service,sockets)


def test_distinct_inference_uid_is_staged_but_not_mounted_without_enrollment(tmp_path,monkeypatch):
    uid=os.geteuid()+31
    cli,service,raw,sockets=compose(tmp_path,monkeypatch,{
        "ceo_ingress_inference_peer_uid":uid,
        "ceo_ingress_inference_armed":False,
    })
    try:
        # Source configuration records a distinct candidate UID only. Until
        # the existing installed service-enrollment owner proves the real
        # dedicated identity, it MUST NOT create a socket ACL/read capability.
        assert service._ceo_ingress_inference_binding is None
        assert service._ceo_ingress_socket_path==raw["ceo_ingress_socket_path"]
        assert set(sockets)=={"Operator","CeoIngress"}
        assert service._ceo_ingress_app_binding.peer_uid==raw["ceo_ingress_app_peer_uid"]
        assert service._ceo_ingress_armed is False
    finally:close_without_execution(service,sockets)


@pytest.mark.parametrize("one",[
    {"ceo_ingress_inference_peer_uid":530},
    {"ceo_ingress_inference_armed":False},
    {"ceo_ingress_inference_peer_uid":530,"ceo_ingress_inference_armed":True},
    {"ceo_ingress_inference_peer_uid":530,"ceo_ingress_inference_armed":1},
    {"ceo_ingress_inference_peer_uid":530,"ceo_ingress_inference_armed":"false"},
])
def test_incomplete_or_armed_inference_config_refuses_before_service(tmp_path,monkeypatch,one):
    with pytest.raises((ServiceError,ValueError)):
        compose(tmp_path,monkeypatch,one)


@pytest.mark.parametrize("kind",[
    "root","control","operator","web","worker","allowed","bool","negative",
])
def test_restricted_service_uid_cannot_alias_other_registered_identities(
    tmp_path,monkeypatch,kind,
):
    euid=os.geteuid()
    values={
        "root":0, "control":euid+20, "operator":euid+1000,
        "web":euid, "worker":euid+1, "allowed":euid+20,
        "bool":True, "negative":-4,
    }
    with pytest.raises((ServiceError,ValueError)):
        compose(tmp_path,monkeypatch,{
            "ceo_ingress_inference_peer_uid":values[kind],
            "ceo_ingress_inference_armed":False,
        })


def test_no_new_service_credential_or_provider_selection_field(tmp_path,monkeypatch):
    with pytest.raises((ServiceError,ValueError)):
        compose(tmp_path,monkeypatch,{
            "ceo_ingress_inference_peer_uid":os.geteuid()+31,
            "ceo_ingress_inference_armed":False,
            "ceo_ingress_inference_provider":"grok",
        })


def test_root_control_config_loader_accepts_only_exact_inert_service_pair(tmp_path):
    from scripts import executive_os_phase1c as cli
    from tests.test_c1_ceo_ingress_composition import _raw, _write_config
    raw=_raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid()+10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path/"macro",
        ceo_ingress_inference_peer_uid=os.geteuid()+31,
        ceo_ingress_inference_armed=False,
    )
    loaded=cli.load_control_config(_write_config(tmp_path,raw))
    assert loaded["ceo_ingress_inference_peer_uid"]==os.geteuid()+31
    assert loaded["ceo_ingress_inference_armed"] is False
    assert loaded["ceo_ingress_socket_path"]==tmp_path/"ceo-ingress.sock"


@pytest.mark.parametrize("change",[
    {"ceo_ingress_inference_armed":True},
    {"ceo_ingress_inference_armed":1},
    {"ceo_ingress_inference_peer_uid":False},
    {"ceo_ingress_inference_peer_uid":0},
    {"ceo_ingress_inference_peer_uid":-1},
    {"ceo_ingress_inference_provider":"grok"},
])
def test_control_loader_refuses_arming_and_caller_selected_provider(tmp_path,change):
    from scripts import executive_os_phase1c as cli
    from tests.test_c1_ceo_ingress_composition import _raw, _write_config
    raw=_raw(tmp_path)
    raw.update(
        ceo_ingress_app_peer_uid=os.geteuid()+10,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=tmp_path/"macro",
        ceo_ingress_inference_peer_uid=os.geteuid()+31,
        ceo_ingress_inference_armed=False,
    )
    raw.update(change)
    with pytest.raises((ServiceError,ValueError)):
        cli.load_control_config(_write_config(tmp_path,raw))


def test_unenrolled_staged_uid_cannot_read_existing_operation_or_submit(
    tmp_path,monkeypatch,
):
    from control_plane import executive_service as host, executive_inference_ingress as ingress
    from control_plane.executive_inference_execution import build_execution_binding
    from integrations.mastermind_executive_app.gateway import CeoIngressClient
    from tests.test_vps_inference_service import GROUND,service_request
    uid=os.geteuid()+31
    cli,service,raw,sockets=compose(tmp_path,monkeypatch,{
        "ceo_ingress_inference_peer_uid":uid,
        "ceo_ingress_inference_armed":False,
    })
    class Ground:
        def observe(self):return GROUND
    operation="staged-install-readonly-origin"
    async def exercise():
        try:
            # No service UID registration is performed. Neither ACL commands
            # nor enrollment verification are simulated by this negative test.
            await service.start()
            created=await ingress.handle_frame(
                {"schema":ingress.SUBMIT_SCHEMA,
                 "request":service_request(operation),
                 "observed_grounding":GROUND},
                runtime=service._require_runtime(),
                grounding_provider=Ground(),
                workspace_root=service.config.proof_workspace_root,
                admission_guard=lambda _:None,
                execution_binding_provider=lambda identity: build_execution_binding(
                    intent_id=identity, workspace_root=service.config.proof_workspace_root,
                    base_sha="a"*40, eligible_quota_classes=("test-only",),
                    inference_request=service_request(operation)["inference_request"],
                ),
            )
            assert service._require_runtime().jobs.get_job(created["job_id"]).status.value=="QUEUED"
            client=CeoIngressClient(connect_timeout=.2,read_timeout=2.0)
            with monkeypatch.context() as patch:
                patch.setattr(host,"_peer_uid",lambda _:uid)
                status=await client.send_frame(raw["ceo_ingress_socket_path"],{
                    "schema":ingress.STATUS_SCHEMA,"operation_key":operation,
                })
                direct=await client.send_frame(raw["ceo_ingress_socket_path"],{
                    "schema":ingress.DIRECT_RESULT_SCHEMA,
                    "operation_key":operation,"reference":{"schema":"forged"},
                })
                refused=await client.send_frame(raw["ceo_ingress_socket_path"],{
                    "schema":ingress.SUBMIT_SCHEMA,
                    "request":service_request("never-submit-when-staged"),
                    "observed_grounding":GROUND,
                })
            assert status.ok is False and (status.error or {}).get("code")=="peer_denied"
            assert direct.ok is False and (direct.error or {}).get("code")=="peer_denied"
            assert refused.ok is False and (refused.error or {}).get("code")=="peer_denied"
            assert "receipt" not in str(status) and "answer" not in str(direct)
            assert len(service._require_runtime().jobs.list_jobs())==1
            assert service._require_runtime().attempts.list_attempts(job_id=created["job_id"])==[]
        finally:
            await service.close()
    try:asyncio.run(exercise())
    finally:
        for sock in sockets.values():sock.close()


def test_dormant_inference_and_native_capacity_staging_remain_inert(
    tmp_path, monkeypatch,
):
    from control_plane.native_capacity_acquisition import NativeCapacitySource

    def forbidden(*_args, **_kwargs):
        pytest.fail("combined dormant staging attempted native acquisition")

    monkeypatch.setattr(NativeCapacitySource, "from_startup", classmethod(forbidden))
    monkeypatch.setattr(NativeCapacitySource, "acquire", forbidden)
    uid = os.geteuid() + 31
    # Shape-valid dormant selectors do not construct an installed source owner.
    # The existing fixture substitutes sockets/clients and never starts Runtime.
    cli, service, raw, sockets = compose(tmp_path, monkeypatch, {
        "ceo_ingress_inference_peer_uid": uid,
        "ceo_ingress_inference_armed": False,
        "fabric_bindings_path": str(tmp_path / "bindings.json"),
        "fabric_bindings_sha256": "a" * 64,
        "fabric_attended_probe": {
            "worker_config_path": str(tmp_path / "worker.json"),
        },
        "native_capacity_v2": {
            "macro_release": "b" * 40,
            "producer_sha256": "c" * 64,
        },
        "coo_autonomy_armed": False,
        "coo_operator_harness_armed": False,
        "coo_foreground_only": False,
        "ceo_submit_armed": False,
        "fabric_bridge_armed": False,
    })
    try:
        assert service._ceo_ingress_inference_binding is None
        assert service._attended_worker_registration is None
        assert service.runtime is None
        assert not Path(raw["runtime_root"]).exists()
        assert service._ceo_ingress_app_binding is not None
        assert service._ceo_ingress_app_binding.peer_uid == raw["ceo_ingress_app_peer_uid"]
        assert service._ceo_ingress_socket_path == raw["ceo_ingress_socket_path"]
        assert service._ceo_ingress_armed is False
        assert set(sockets) == {"Operator", "CeoIngress"}
    finally:
        close_without_execution(service, sockets)
