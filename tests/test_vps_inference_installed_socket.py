"""Source-only real AF_UNIX transport with host-owned isolated service-peer gate.

No installed OAuth/identity, real provider, completion writer or deployment.
A test-owned process/UID and temporary Runtime stand in for the future
distinct service App OS identity; the incumbent C1/Web App stay separate.
"""
import asyncio
from pathlib import Path
import os

import pytest

from control_plane import executive_inference_ingress as inference
from control_plane import executive_ceo_ingress as ceo
from control_plane.executive_inference_execution import build_execution_binding
from control_plane.executive_runtime import Runtime
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from tests.test_vps_inference_service import GROUND, service_request, rsa_key
from tests import test_mastermind_executive_app_asgi as fixture


@pytest.fixture(autouse=True)
def synthetic_distinct_service_peer(monkeypatch):
    # Test-only kernel UID substitution. Real AF_UNIX transport is exercised,
    # but not the OS security of an installed restricted service identity.
    from control_plane import executive_service as host
    monkeypatch.setattr(host, '_peer_uid', lambda _sock: os.geteuid() + 1001)


async def source_harness(tmp_path, short_socket_root, *, armed=False):
    from control_plane.executive_service import (
        ExecutiveControlService, CeoIngressInferenceBinding,
    )
    service_root = tmp_path / "source-service"
    base = fixture._real_service(
        service_root, socket_root=short_socket_root,
        mastermind_root=tmp_path / "source-mastermind",
        macro_root=tmp_path / "source-macro",
    )
    class Grounding:
        def observe(self): return GROUND

    calls = []
    def host_binding(intent, wire):
        calls.append(("placement", intent, wire.get("task_kind")))
        return build_execution_binding(
            intent_id=intent, workspace_root=base.config.proof_workspace_root,
            base_sha="a" * 40, eligible_quota_classes=("fixture",),
            inference_request=wire,
        )
    def guard(envelope):
        calls.append(("admission", envelope["intent_id"]))
    binding = CeoIngressInferenceBinding(
        peer_uid=os.geteuid()+1001, grounding_provider=Grounding(),
        admission_armed=armed, admission_guard=guard,
        execution_binding_provider=host_binding,
    )
    service = ExecutiveControlService(
        base.config,
        supervisor_factory=lambda runtime: fixture._NoExecutionSupervisor(),
        ceo_ingress_socket_path=short_socket_root / "source-service.sock",
        ceo_ingress_peer_uid=os.geteuid() + 1000,
        ceo_ingress_grounding_provider=Grounding(),
        ceo_ingress_armed=False, ceo_ingress_inference_binding=binding,
    )
    await service.start()
    client = CeoIngressClient(connect_timeout=.2, read_timeout=1.5)
    return service, client, calls


@pytest.fixture
def short_socket_root(tmp_path):
    # The project fixture owns a separate short tmp socket path.
    path = tmp_path / "socket"
    path.mkdir()
    return path


def test_optional_binding_is_default_off_and_rejects_uid_collision():
    from control_plane.executive_service import (
        CeoIngressInferenceBinding, CeoIngressAppBinding, ExecutiveControlService,
    )
    class Ground:
        def observe(self): return GROUND
    with pytest.raises(ValueError):
        CeoIngressInferenceBinding(peer_uid=True, grounding_provider=Ground())
    with pytest.raises(ValueError):
        CeoIngressInferenceBinding(peer_uid=os.geteuid(),
            grounding_provider=Ground(), admission_armed=True)
    valid=CeoIngressInferenceBinding(peer_uid=os.geteuid(),grounding_provider=Ground())
    assert valid.admission_armed is False


def test_larger_service_packet_reaches_existing_sink_without_legacy_8k_gate(tmp_path,short_socket_root):
    async def exercise():
        service, client, calls = await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            ground=await client.send_frame(service._ceo_ingress_socket_path,
                 {"schema":ceo.APP_GROUNDING_SCHEMA})
            assert ground.ok is True and ground.result==GROUND
            from control_plane.executive_inference_io import TASK_REQUEST_SCHEMA
            wire={"schema":TASK_REQUEST_SCHEMA,"system_prompt":"research only",
                  "input_text":"synthetic:"+"x"*20000,
                  "max_output_chars":2048,"task_kind":"comparative_analysis"}
            frame={"schema":inference.SUBMIT_SCHEMA,"request":service_request(
                operation_key="installed-source-wire-canary",request=wire),
                "observed_grounding":GROUND}
            response=await client.send_frame(service._ceo_ingress_socket_path,frame)
            assert response.transport=="sent_ok"
            assert response.ok is True, response.error
            job=service.runtime.jobs.get_job(response.result["job_id"])
            assert job.constraints["risk"]=="elevated"
            assert job.constraints["preferred_model_aliases"]==["standard.research"]
            assert job.status.value=="QUEUED"
            assert not service.runtime.attempts.list_attempts(job_id=job.job_id)
            assert calls[0][0]=="placement" and any(c[0]=="admission" for c in calls)
            status=await client.send_frame(service._ceo_ingress_socket_path,
                {"schema":inference.STATUS_SCHEMA,"operation_key":"installed-source-wire-canary"})
            assert status.ok is True and status.result["receipt"]["job_id"]==job.job_id
            assert status.result["terminal_result_ref"] is None
        finally:
            await service.close()
    asyncio.run(exercise())


def test_disarmed_fresh_service_frame_refuses_without_creating_job(tmp_path,short_socket_root):
    async def exercise():
        service, client, calls = await source_harness(tmp_path,short_socket_root,armed=False)
        try:
            frame={"schema":inference.SUBMIT_SCHEMA,
                   "request":service_request(operation_key="source-disarmed"),
                   "observed_grounding":GROUND}
            response=await client.send_frame(service._ceo_ingress_socket_path,frame)
            assert response.ok is False
            assert len(service.runtime.jobs.list_jobs())==0
        finally:await service.close()
    asyncio.run(exercise())


def test_service_peer_cannot_send_legacy_ceo_intent_or_read_tools(tmp_path,short_socket_root):
    async def exercise():
        service, client, calls = await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            for frame in [{"schema":ceo.STATUS_SCHEMA,"intent_id":"ANY-001"},
                          {"schema":ceo.APP_READ_SCHEMA_V3,"tool":"executive_state","arguments":{}}]:
                response=await client.send_frame(service._ceo_ingress_socket_path,frame)
                assert response.ok is False
                assert (response.error or {}).get("code") in {"peer_denied","invalid_input"}
            assert not service.runtime.jobs.list_jobs()
        finally:await service.close()
    asyncio.run(exercise())


def test_oauth_service_app_to_real_unix_ingress_admits_source_only_job(
    rsa_key, tmp_path, short_socket_root
):
    import dataclasses
    from tests import test_vps_inference_service as service_test
    from control_plane.executive_inference_io import TASK_REQUEST_SCHEMA
    app, token, _ = service_test.setup_app(rsa_key, tmp_path)
    async def exercise():
        service, transport, _ = await source_harness(tmp_path, short_socket_root, armed=True)
        try:
            base = dataclasses.replace(
                app.settings.executive,
                ceo_ingress_socket_path=service._ceo_ingress_socket_path,
            )
            app.settings = dataclasses.replace(app.settings, executive=base)
            wire = {"schema": TASK_REQUEST_SCHEMA, "system_prompt": "Research only",
                    "input_text": "SYNTHETIC:" + "x"*18000,
                    "max_output_chars": 2048, "task_kind": "comparative_analysis"}
            request = service_request("real-app-synthetic-source",request=wire)
            response = await service_test.call(app, token, "submit_service_intent", request)
            assert response.status_code == 200, response.text
            record = response.json()
            assert record["ok"] is True and record["status"] == "accepted"
            job = service.runtime.jobs.get_job(record["receipt"]["job_id"])
            assert job.status.value == "QUEUED"
            assert job.constraints["preferred_model_aliases"] == ["standard.research"]
            assert job.constraints["risk"] == "elevated"
            assert not service.runtime.attempts.list_attempts(job_id=job.job_id)
            status = await service_test.call(app,token,"service_intent_status",
                        {"operation_key": "real-app-synthetic-source"})
            assert status.status_code == 200
            assert status.json()["receipt"]["job_id"] == job.job_id
            assert status.json()["terminal_result_ref"] is None
        finally:
            await service.close()
    asyncio.run(exercise())


def test_disarming_preserves_same_operation_duplicate_reconciliation(
    tmp_path, short_socket_root
):
    import dataclasses
    async def exercise():
        service, client, calls = await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            frame = {"schema": inference.SUBMIT_SCHEMA,
                     "request": service_request("service-dup-after-disarm"),
                     "observed_grounding": GROUND}
            first = await client.send_frame(service._ceo_ingress_socket_path,frame)
            assert first.ok is True
            before = len(calls)
            service._ceo_ingress_inference_binding = dataclasses.replace(
                service._ceo_ingress_inference_binding, admission_armed=False)
            repeated = await client.send_frame(service._ceo_ingress_socket_path,frame)
            assert repeated.ok is True
            assert repeated.result["duplicate"] is True
            assert repeated.result["job_id"] == first.result["job_id"]
            assert len(calls) == before
            assert len(service.runtime.jobs.list_jobs()) == 1
        finally:
            await service.close()
    asyncio.run(exercise())


def test_client_enforces_60k_ceiling_without_transmitting_oversized_service_job(
    tmp_path, short_socket_root
):
    async def exercise():
        service, client, calls = await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            frame={"schema": inference.SUBMIT_SCHEMA,
                   "request": service_request("oversized-service"),
                   "observed_grounding": GROUND,
                   "padding": "x"*inference.MAX_FRAME_BYTES}
            result = await client.send_frame(service._ceo_ingress_socket_path,frame)
            assert result.transport == "not_sent"
            assert service.runtime.jobs.list_jobs() == [] and not calls
        finally:await service.close()
    asyncio.run(exercise())


def test_real_unix_source_read_uses_exact_qualified_reference(tmp_path,short_socket_root):
    from tests.test_vps_inference_runtime_read import synthetic_complete
    from tests.test_vps_inference_runtime_projection import qualified_reader,cleanup
    import dataclasses
    async def exercise():
        service, client, calls = await source_harness(tmp_path,short_socket_root,armed=True)
        binding=None
        try:
            req=service_request("socket-direct-synthetic")
            submitted=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.SUBMIT_SCHEMA,"request":req,"observed_grounding":GROUND})
            assert submitted.ok is True
            ref,document,_=synthetic_complete(service.runtime,submitted.result["job_id"])
            read_runtime,binding=qualified_reader(service.runtime,service.config.runtime_root.parent)
            service._ceo_ingress_inference_binding=dataclasses.replace(
                service._ceo_ingress_inference_binding,
                result_read_runtime_factory=lambda runtime: read_runtime)
            status=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.STATUS_SCHEMA,"operation_key":req["operation_key"]})
            assert status.ok is True and status.result["terminal_result_ref"]==ref
            read=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.DIRECT_RESULT_SCHEMA,
                "operation_key":req["operation_key"],"reference":ref})
            assert read.ok is True,read.error
            assert read.result["document"]==document
            assert read.result["reference"]==ref
            forged=dict(ref,content_sha256="f"*64)
            refused=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.DIRECT_RESULT_SCHEMA,
                "operation_key":req["operation_key"],"reference":forged})
            assert refused.ok is False
            assert "answer" not in str(refused)
        finally:
            if binding is not None:cleanup(binding)
            await service.close()
    asyncio.run(exercise())


def test_authenticated_app_reads_original_completed_reference_over_its_service_socket(
    rsa_key,tmp_path,short_socket_root
):
    import dataclasses
    from tests import test_vps_inference_service as service_test
    from tests.test_vps_inference_runtime_read import synthetic_complete
    from tests.test_vps_inference_runtime_projection import qualified_reader,cleanup
    from brain.fabric_inference_client import FabricInferenceClient

    app, token, _ = service_test.setup_app(rsa_key,tmp_path)
    async def exercise():
        service, client, _ = await source_harness(tmp_path,short_socket_root,armed=True)
        binding=None
        try:
            app.settings = dataclasses.replace(
                app.settings,
                executive=dataclasses.replace(
                    app.settings.executive,
                    ceo_ingress_socket_path=service._ceo_ingress_socket_path,
                ),
            )
            request = service_request("asgi-direct-socket-original")
            submitted = await service_test.call(app,token,"submit_service_intent",request)
            assert submitted.status_code==200,submitted.text
            job_id=submitted.json()["receipt"]["job_id"]
            ref,document,_=synthetic_complete(service.runtime,job_id)
            read_runtime,binding=qualified_reader(service.runtime,service.config.runtime_root.parent)
            service._ceo_ingress_inference_binding=dataclasses.replace(
                service._ceo_ingress_inference_binding,
                result_read_runtime_factory=lambda _:read_runtime)
            calls=[]
            async def authenticated(name,args):
                calls.append(name)
                resp=await service_test.call(app,token,name,args)
                return resp.json()
            result=await FabricInferenceClient(authenticated).answer(
                "asgi-direct-socket-original",request["objective"],request["inference_request"])
            assert calls==["service_intent_status","executive_fabric"]
            assert result["document"]==document
            assert result["reference"]==ref
            assert not service.runtime.attempts.list_attempts(job_id="JOB-999")
            assert service.runtime.jobs.get_job(job_id).status.value=="COMPLETED"
            wrong=dict(ref,content_sha256="f"*64)
            response=await service_test.call(app,token,"executive_fabric",{
                "view":"service_inference","operation_key":"asgi-direct-socket-original",
                "reference":wrong})
            assert response.status_code in (403,503) and "SYNTHETIC ONLY" not in response.text
        finally:
            if binding is not None:cleanup(binding)
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("identity",["c1","foreign"])
def test_nonservice_kernel_peers_cannot_reach_service_intent(
    tmp_path,short_socket_root,monkeypatch,identity
):
    from control_plane import executive_service as owner
    async def exercise():
        service,client,calls=await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            peer=(os.geteuid()+1000 if identity=="c1" else os.geteuid()+9999)
            with monkeypatch.context() as patch:
                patch.setattr(owner,"_peer_uid",lambda _:peer)
                reply=await client.send_frame(service._ceo_ingress_socket_path,{
                    "schema":inference.SUBMIT_SCHEMA,
                    "request":service_request("forbidden-cross-peer"),
                    "observed_grounding":GROUND})
            assert reply.ok is False
            assert (reply.error or {}).get("code")=="peer_denied"
            assert service.runtime.jobs.list_jobs()==[] and not calls
        finally:await service.close()
    asyncio.run(exercise())


def test_qualified_service_reader_carries_more_than_legacy_8k_result(
    tmp_path,short_socket_root
):
    from tests.test_vps_inference_runtime_read import synthetic_complete
    from tests.test_vps_inference_runtime_projection import qualified_reader,cleanup
    import dataclasses
    async def exercise():
        service,client,_=await source_harness(tmp_path,short_socket_root,armed=True)
        binding=None
        try:
            operation="larger-synthetic-direct-result"
            wire={"schema":"mastermind.executive_service_inference_request.v1",
                  "system_prompt":"Research only",
                  "input_text":"Synthetic input","max_output_chars":16384}
            req=service_request(operation,request=wire)
            sub=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.SUBMIT_SCHEMA,"request":req,
                "observed_grounding":GROUND})
            assert sub.ok is True
            # The shared small-answer fixture has a fixed 4 KiB ceiling.
            # Build this larger result only in temporary test-owned SQLite,
            # explicitly NOT as a real Supervisor/provider completion.
            import hashlib
            from control_plane import executive_inference_io as io
            from tests.test_vps_inference_runtime_read import qualified_attempt
            text="SYNTHETIC EVIDENCE ONLY "*500
            attempt=qualified_attempt(service.runtime,sub.result["job_id"])
            result={"schema_version":io.WORKER_RESULT_SCHEMA,
                    "job_id":sub.result["job_id"],"run_id":attempt.attempt_id,
                    "worker_id":attempt.worker_id,"status":"COMPLETED","answer":text}
            ref=io.result_reference(job_id=sub.result["job_id"],
                attempt_id=attempt.attempt_id,worker_id=attempt.worker_id,
                result_sha256="b"*64,
                content_sha256=hashlib.sha256(io.canonical_bytes(result)).hexdigest())
            doc=io.result_document(reference=ref,result=result,
                raw_result_sha256="b"*64,max_output_chars=16384)
            encoded=io.canonical_bytes(doc).decode()
            with service.runtime.store.transaction() as db:
                db.execute("UPDATE attempts SET status='COMPLETED',result_json=?,exit_code=0,"
                           "lease_token=NULL,finished_at_ms=1000,updated_at_ms=1000 WHERE attempt_id=?",
                           (encoded,attempt.attempt_id))
                db.execute("UPDATE jobs SET status='COMPLETED',result_json=? WHERE job_id=?",
                           (encoded,sub.result["job_id"]))
            reader,binding=qualified_reader(service.runtime,service.config.runtime_root.parent)
            service._ceo_ingress_inference_binding=dataclasses.replace(
                service._ceo_ingress_inference_binding,
                result_read_runtime_factory=lambda _:reader)
            response=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.DIRECT_RESULT_SCHEMA,
                "operation_key":operation,"reference":ref})
            assert response.ok is True,response.error
            assert len(str(response.result))>8192
            assert response.result["document"]==doc
        finally:
            if binding is not None:cleanup(binding)
            await service.close()
    asyncio.run(exercise())


def test_read_refuses_missing_host_read_namespace_without_guessing_result(
    tmp_path,short_socket_root
):
    async def exercise():
        service,client,_=await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            submitted=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.SUBMIT_SCHEMA,
                "request":service_request("no-result-reader"),
                "observed_grounding":GROUND})
            assert submitted.ok is True
            attempted=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.DIRECT_RESULT_SCHEMA,
                "operation_key":"no-result-reader",
                "reference":{"schema":"invalid"}})
            assert attempted.ok is False
            assert "answer" not in str(attempted)
            assert len(service.runtime.jobs.list_jobs())==1
        finally:await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("verdict",[False,True,"accepted",{"allow":True}])
def test_host_guard_return_verdict_cannot_be_dropped_at_real_socket(
    tmp_path,short_socket_root,verdict
):
    import dataclasses
    async def exercise():
        service,client,_=await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            service._ceo_ingress_inference_binding=dataclasses.replace(
                service._ceo_ingress_inference_binding,
                admission_guard=lambda _:verdict)
            response=await client.send_frame(service._ceo_ingress_socket_path,{
                "schema":inference.SUBMIT_SCHEMA,
                "request":service_request("forged-guard-verdict"),
                "observed_grounding":GROUND})
            assert response.ok is False
            assert not service.runtime.jobs.list_jobs()
        finally:await service.close()
    asyncio.run(exercise())


def test_async_admission_guard_and_host_factory_are_refused_before_admission():
    from control_plane.executive_service import CeoIngressInferenceBinding
    class Ground:
        def observe(self):return GROUND
    async def asynchronous(*_):
        return None
    with pytest.raises(ValueError):
        CeoIngressInferenceBinding(peer_uid=os.geteuid(),grounding_provider=Ground(),
            admission_armed=True,admission_guard=asynchronous,
            execution_binding_provider=lambda *_:None)
    with pytest.raises(ValueError):
        CeoIngressInferenceBinding(peer_uid=os.geteuid(),grounding_provider=Ground(),
            admission_armed=True,admission_guard=lambda _:None,
            execution_binding_provider=asynchronous)


def test_valid_near_48k_inference_request_crosses_older_release_transport_ceiling(
    tmp_path,short_socket_root
):
    import json
    from control_plane import executive_inference_io as io
    from control_plane import executive_release_ingress as release
    async def exercise():
        service,client,_=await source_harness(tmp_path,short_socket_root,armed=True)
        try:
            chosen=None
            for size in range(48000,49200,25):
                wire={"schema":io.REQUEST_SCHEMA,"system_prompt":"Research only",
                      "input_text":"x"*size,"max_output_chars":2048}
                try:io.normalize_request(wire)
                except io.InferenceIOError:continue
                frame={"schema":inference.SUBMIT_SCHEMA,
                       "request":service_request("valid-near-inference-limit",request=wire),
                       "observed_grounding":GROUND}
                serialized=json.dumps(frame,sort_keys=True).encode()
                if release.MAX_FRAME_BYTES < len(serialized)+1 <= inference.MAX_FRAME_BYTES:
                    chosen=frame
            assert chosen is not None,"fixture must discriminate prior 48KiB ingress ceiling"
            response=await client.send_frame(service._ceo_ingress_socket_path,chosen)
            assert response.transport=="sent_ok" and response.ok is True,response.error
            job=service.runtime.jobs.get_job(response.result["job_id"])
            assert job.status.value=="QUEUED"
            assert len(service.runtime.jobs.list_jobs())==1
        finally:await service.close()
    asyncio.run(exercise())


def test_host_rejects_inference_uid_with_operator_control_authority(tmp_path,short_socket_root):
    from control_plane.executive_service import ExecutiveControlService,CeoIngressInferenceBinding
    class Grounding:
        def observe(self):return GROUND
    base=fixture._real_service(tmp_path/"owner-source",socket_root=short_socket_root,
        mastermind_root=tmp_path/"mastermind",macro_root=tmp_path/"macro")
    binding=CeoIngressInferenceBinding(peer_uid=os.geteuid(),grounding_provider=Grounding())
    with pytest.raises(ValueError,match="privileged"):
        ExecutiveControlService(
            base.config, supervisor_factory=lambda _:fixture._NoExecutionSupervisor(),
            ceo_ingress_socket_path=short_socket_root/"privilege-collision.sock",
            ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_grounding_provider=Grounding(),
            ceo_ingress_inference_binding=binding,
        )


def test_incomplete_service_peer_connection_expires_without_blocking_shutdown(
    tmp_path,short_socket_root
):
    async def exercise():
        service, _client, _ = await source_harness(tmp_path,short_socket_root,armed=False)
        reader,writer=await asyncio.open_unix_connection(
            str(service._ceo_ingress_socket_path))
        try:
            writer.write(b'{"schema":"unfinished service request"')
            await writer.drain()
            # Only the pre-frame interval is bounded. This test must never
            # cancel an accepted durable Job or simulate zero-effect replay.
            response=await asyncio.wait_for(reader.readline(),timeout=3.0)
            assert response, "server silently left an admitted peer pending"
            assert b"ingress_unavailable" in response or b"request_too_large" in response
        finally:
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(service.close(),timeout=4.0)
    asyncio.run(exercise())


def test_named_inference_service_acl_uses_only_its_dedicated_uid_and_existing_socket(
    tmp_path,short_socket_root,monkeypatch
):
    import socket
    import dataclasses
    from types import SimpleNamespace
    from control_plane import executive_service as host
    class Grounding:
        def observe(self):return GROUND
    base=fixture._real_service(tmp_path/"acl-check",socket_root=short_socket_root,
        mastermind_root=tmp_path/"mastermind",macro_root=tmp_path/"macro")
    binding=host.CeoIngressInferenceBinding(
        peer_uid=os.geteuid()+1001,grounding_provider=Grounding(),admission_armed=False)
    service=host.ExecutiveControlService(
        base.config,supervisor_factory=lambda _:fixture._NoExecutionSupervisor(),
        ceo_ingress_socket_path=short_socket_root/"named-inference.sock",
        ceo_ingress_peer_uid=os.geteuid()+1000,
        ceo_ingress_grounding_provider=Grounding(),
        ceo_ingress_inference_binding=binding)
    short_socket_root.chmod(0o700)
    listener=socket.socket(socket.AF_UNIX)
    listener.bind(str(service.ceo_ingress_socket_path))
    service.ceo_ingress_socket_path.chmod(0o600)
    operations=[]
    try:
        with monkeypatch.context() as patch:
            patch.setattr(host.sys,"platform","darwin")
            patch.setattr(host.pwd,"getpwuid",
                lambda uid: SimpleNamespace(pw_name="_mastermind_inference"))
            def command(args,**kwargs):
                operations.append(tuple(args))
                return SimpleNamespace(stdout="")
            patch.setattr(host.subprocess,"run",command)
            service._grant_app_socket_access()
        assert ("/bin/chmod","+a",
                "user:_mastermind_inference allow read,write",
                str(service.ceo_ingress_socket_path)) in operations
        assert ("/bin/chmod","+a",
                "user:_mastermind_inference allow search",
                str(short_socket_root)) in operations
        assert not any("group:" in " ".join(op) or "everyone:" in " ".join(op)
                       for op in operations)
    finally:
        listener.close()


def test_service_principal_root_uid_is_not_a_restricted_identity():
    from control_plane.executive_service import CeoIngressInferenceBinding
    class Grounding:
        def observe(self):return GROUND
    with pytest.raises(ValueError):
        CeoIngressInferenceBinding(peer_uid=0,grounding_provider=Grounding())


def test_large_service_result_backpressure_aborts_delivery_after_transaction():
    from control_plane import executive_service as owner
    from control_plane.executive_inference_contract import MAX_RESULT_BYTES
    # Pure delivery probe: source is already settled, no App/provider/Runtime,
    # no network listener or service task is created in this negative test.
    service=object.__new__(owner.ExecutiveControlService)
    class Transport:
        aborted=False
        def abort(self):self.aborted=True
    class Peer:
        transport=Transport()
        buffer=None
        def write(self,payload):self.buffer=payload
        async def drain(self):await asyncio.Event().wait()
    peer=Peer()
    async def exercise():
        await asyncio.wait_for(service._send_ceo_ingress_response(
            peer,{'ok':True,'result':{'answer':'SYNTHETIC'*16000}},
            response_ceiling=MAX_RESULT_BYTES,delivery_timeout=.05),timeout=1.0)
    asyncio.run(exercise())
    assert peer.transport.aborted
    assert peer.buffer is not None and len(peer.buffer)>100000


def test_quarantine_during_inflight_direct_read_refuses_publication(
    tmp_path, short_socket_root, monkeypatch,
):
    from control_plane import executive_inference_ingress as owner
    async def exercise():
        service,client,_=await source_harness(tmp_path,short_socket_root,armed=True)
        entered=asyncio.Event();release=asyncio.Event()
        secret="SYNTHETIC_CONFIDENTIAL_DIRECT_ANSWER"
        async def held_read(*args,**kwargs):
            entered.set()
            await release.wait()
            # A completed internal result under the pre-quarantine generation
            # cannot be published if canonical service state changed.
            return {"document":{"answer":secret},"reference":"synthetic"}
        try:
            with monkeypatch.context() as patch:
                patch.setattr(owner,"handle_frame",held_read)
                task=asyncio.create_task(client.send_frame(
                    service._ceo_ingress_socket_path,{
                        "schema":owner.STATUS_SCHEMA,
                        "operation_key":"stale-quarantine-read",
                    }))
                await asyncio.wait_for(entered.wait(),timeout=2.0)
                service._service_state="QUARANTINED"
                release.set()
                result=await asyncio.wait_for(task,timeout=3.0)
            assert result.ok is False
            assert (result.error or {}).get("code")=="backend_unavailable"
            assert secret not in repr(result)
        finally:
            release.set()
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("read_kind", ["status", "direct"])
def test_canonical_completed_inference_read_quarantine_refuses_result_publication(
    tmp_path, short_socket_root, monkeypatch, read_kind,
):
    """Real qualified Runtime read with synthetic sealed terminal fixture.

    The backend finishes the existing content-bound read before the test
    changes service state. This exercises the actual source-qualified reader
    and exact direct-result frame, not only the prior mocked status response.
    It never starts a provider, creates a second Runtime or moves capital.
    """
    import dataclasses
    from control_plane import executive_inference_ingress as owner
    from tests.test_vps_inference_runtime_read import synthetic_complete
    from tests.test_vps_inference_runtime_projection import qualified_reader, cleanup

    async def exercise():
        service, client, _ = await source_harness(
            tmp_path, short_socket_root, armed=True
        )
        read_binding = None
        entered = asyncio.Event()
        resume = asyncio.Event()
        secret = "SYNTHETIC_ONLY_QUARANTINE_CONTENT_NEVER_RELEASE"
        operation = "quarantine-qualified-" + read_kind
        try:
            admitted = await client.send_frame(
                service._ceo_ingress_socket_path,
                {
                    "schema": owner.SUBMIT_SCHEMA,
                    "request": service_request(operation),
                    "observed_grounding": GROUND,
                },
            )
            assert admitted.ok is True, admitted.error
            original_job = admitted.result["job_id"]
            ref, document, _ = synthetic_complete(
                service.runtime, original_job, answer=secret
            )
            read_runtime, read_binding = qualified_reader(
                service.runtime, service.config.runtime_root.parent
            )
            service._ceo_ingress_inference_binding = dataclasses.replace(
                service._ceo_ingress_inference_binding,
                result_read_runtime_factory=lambda _original: read_runtime,
            )
            original_read = owner.handle_frame
            confirmed = []

            async def pause_after_real_read(*args, **kwargs):
                selected = await original_read(*args, **kwargs)
                if read_kind == "direct":
                    assert selected["document"] == document
                    assert selected["reference"] == ref
                    assert selected["generation"]["state"] == "SAME"
                else:
                    assert selected["terminal_result_ref"] == ref
                confirmed.append(selected)
                entered.set()
                await resume.wait()
                return selected

            read_frame = {
                "schema": (
                    owner.DIRECT_RESULT_SCHEMA
                    if read_kind == "direct" else owner.STATUS_SCHEMA
                ),
                "operation_key": operation,
            }
            if read_kind == "direct":
                read_frame["reference"] = ref

            with monkeypatch.context() as patch:
                patch.setattr(owner, "handle_frame", pause_after_real_read)
                pending = asyncio.create_task(
                    client.send_frame(service._ceo_ingress_socket_path, read_frame)
                )
                await asyncio.wait_for(entered.wait(), timeout=2.0)
                service._service_state = "QUARANTINED"
                resume.set()
                response = await asyncio.wait_for(pending, timeout=3.0)
            assert len(confirmed) == 1
            assert response.transport == "sent_ok"
            assert response.ok is False
            assert (response.error or {}).get("code") == "backend_unavailable"
            assert secret not in repr(response)
            assert original_job not in repr(response)
            assert len(service.runtime.jobs.list_jobs()) == 1
            assert service.runtime.jobs.get_job(original_job).status.value == "COMPLETED"
        finally:
            resume.set()
            if read_binding is not None:
                cleanup(read_binding)
            await service.close()

    asyncio.run(exercise())
