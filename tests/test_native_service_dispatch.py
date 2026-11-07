"""Installed service callers on real Runtime/OHF; provider/ACK/carrier are fixtures.

These are reachability and custody checks, never installed native acceptance.
Canonical ACK ingress and atomic carrier COMMIT have their own composed tests.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_service import ExecutiveControlService, ServiceConfig
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_runtime import JobStatus, StateConflict, Runtime
from control_plane.native_continuation import _EVENT, _ACTOR
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.schemas import BridgeError
from integrations.company_consultation_host import CompanyConsultationHost
from tests.test_native_retained_runtime import _NativeAdapter
from tests.test_executive_operator_supervisor import _PromptSource
from tests.test_executive_service import _config, _coo_intent


def service_case(tmp_path,monkeypatch):
    config=_config(tmp_path,worker_id="worker-a",worker_account_label="worker-a@company",
        worker_type="fixture",coo_autonomy_armed=True,coo_operator_harness_armed=True,
        coo_operator_model_alias="coo.operator.native-return",operator_harness_binary_digest="a"*64,
        operator_harness_version="0.147.0")
    service=ExecutiveControlService(config,autonomy_guard=lambda:None)
    runtime=Runtime.at(config.runtime_root)
    service.runtime=runtime
    service._register_worker()
    submitted=service._submit_service_intent(_coo_intent(config,"native-return"))
    root=runtime.jobs.get_job(submitted["job_id"])
    adapters=[]
    def factory(loader):
        adapter=_NativeAdapter(runtime,loader,cancel_during_collect=False)
        adapters.append(adapter)
        return adapter
    service.operator_supervisor=ExecutiveOperatorSupervisor(runtime,adapter_factory=factory,prompt_source=_PromptSource())
    service._company_consultation_host=CompanyConsultationHost(runtime=runtime,
        repository_root=tmp_path,worker_uid=451,relay_socket_path=tmp_path/"relay.sock",
        workspace_id="T0000000001",channel_id="C0000000001",native_return_armed=True)
    service._company_consultation_ready=True
    service._company_consultation_binding=object()
    service._ceo_ingress_app_binding=SimpleNamespace(armed=True,session_bridge_provider_factory=lambda r:None)
    # Current v3 root, registered quotas and workspace qualification are real.
    # Ambient host capabilities and provider/ACK/carrier are fixture boundaries.
    return service,runtime,root,adapters


def test_installed_company_owner_composes_the_native_source_without_core_imports(tmp_path,monkeypatch):
    service,runtime,root,adapters=service_case(tmp_path,monkeypatch)
    before=runtime.events.list_events()
    source=service._native_return_source(root)
    assert type(source) is RuntimeSessionReturn and source.runtime is runtime
    assert runtime.events.list_events()==before and not adapters


@pytest.mark.parametrize("invalid",["unarmed","missing_factory","foreign_runtime"])
def test_native_source_composition_refuses_missing_or_foreign_installed_owner(tmp_path,monkeypatch,invalid):
    service,runtime,root,adapters=service_case(tmp_path,monkeypatch)
    before=runtime.events.list_events()
    host=service._company_consultation_host
    if invalid=="unarmed":
        host.native_return_armed=False
    elif invalid=="missing_factory":
        service._company_consultation_host=SimpleNamespace(runtime=runtime,native_return_armed=True)
    else:
        source=host.native_continuation_source()
        source.runtime=object()
        monkeypatch.setattr(host,"native_continuation_source",lambda:source)
    with pytest.raises(StateConflict,match="native.*(armed|composition)"):
        service._native_return_source(root)
    assert runtime.events.list_events()==before and not adapters


@pytest.mark.parametrize("reply_committed",[True,False])
@pytest.mark.parametrize("early_ack",[False,True])
def test_existing_cycle_and_wake_edge_reach_one_native_turn_then_exact_cleanup(tmp_path,monkeypatch,reply_committed,early_ack):
    async def scenario():
        service,runtime,root,adapters=service_case(tmp_path,monkeypatch)
        created=await service._run_coo_cycle_once(root.job_id)
        assert created.action=="PLANNER_CREATED" and not adapters
        job=runtime.jobs.get_job(created.selected_job_id)
        fabric=RuntimeFabricTargetProjector(runtime)
        source=RuntimeSessionReturn(runtime,fabric=fabric,
            codex=RuntimeCodexTargetProjector(fabric,owner_configured=lambda:True),socket_path=tmp_path/"relay.sock")
        state={"ack":False,"reply_reads":0}
        async def read(**kwargs):
            current=runtime.jobs.get_job(job.job_id)
            facts=runtime.current_harness_binding_source(current.current_attempt_id)
            return {"event":{"event_id":123},"request":{"job_id":job.job_id,"attempt_id":facts.attempt_id,
                "worker_id":facts.worker_id,"operation_key":"original-operation",
                "carrier":{"workspace_id":"T-FIXTURE","channel_id":"C-FIXTURE"}},
                "message":{"message_key":"continue-fixture","body":{"instruction":"Return one useful source finding.",
                    "stop_condition":"Commit the exact native reply."}}}
        monkeypatch.setattr(source,"read_continuation_source",read)
        monkeypatch.setattr(source,"resolve",lambda **kwargs:"exact-fixture-binding")
        def ack(*args,**kwargs):
            if not state["ack"]:raise StateConflict("no authenticated ACK fixture")
            return "exact-ack-fixture"
        monkeypatch.setattr(source,"require_native_ack",ack)
        async def committed(**kwargs):
            state["reply_reads"]+=1
            if not reply_committed:raise BridgeError("reply_unavailable","missing canonical reply")
            return {"message_key":"canonical-fixture"}
        monkeypatch.setattr(source,"require_committed_native_reply",committed)
        # Only external source/attention/carrier boundaries are fixtures.
        # Service locks, dispatch occupancy, Runtime claim and OHF turns are real.
        monkeypatch.setattr(service,"_native_return_source",lambda _:source)
        def publish(retained):
            with runtime.store.transaction() as conn:
                runtime.store.append_event(conn,aggregate_type="session_bridge_continue",aggregate_id="fixture",
                    event_type=_EVENT,actor=_ACTOR,job_id=job.job_id,attempt_id=retained.session.attempt_id,
                    worker_id=retained.lease.attempt.worker_id,command_id="fixture-continue",
                    payload={"operation_key":"original-operation","request_message_key":"continue-fixture",
                        "read_ref":"fixture-read","carrier":{"workspace_id":"T-FIXTURE","channel_id":"C-FIXTURE"}})
        if early_ack:
            original_start=service.operator_supervisor.start_retained_native_job
            async def start_and_receive(*args,**kwargs):
                retained=await original_start(*args,**kwargs)
                state.update(retained=retained,task=service._dispatch_tasks[job.job_id])
                publish(retained)
                state["ack"]=True
                assert service._native_operator_dispatch.retained is None
                await service._signal_native_continuation()
                assert not service._native_operator_dispatch.continuation.done()
                return retained
            monkeypatch.setattr(service.operator_supervisor,"start_retained_native_job",start_and_receive)
        outcome=await service._run_coo_cycle_once(root.job_id)
        assert outcome.action=="DISPATCHED"
        task=state["task"] if early_ack else service._dispatch_tasks[job.job_id]
        retained=state["retained"] if early_ack else service._native_operator_dispatch.retained
        seal=runtime.events.get_event_by_command_id(f"orchestration-result-seal:{retained.session.attempt_id}")
        if not early_ack:
            assert adapters[0].begin_turn_calls==1 and adapters[0].stop_calls==0
            publish(retained)
            await service._signal_native_continuation()
            assert not service._native_operator_dispatch.continuation.done()
            no_action=await service._run_coo_cycle_once(root.job_id)
            assert no_action.action=="NO_ACTION" and adapters[0].begin_turn_calls==1
            state["ack"]=True
            await service._signal_native_continuation()
            await service._signal_native_continuation()
        await asyncio.wait_for(task,timeout=2)
        assert adapters[0].begin_turn_calls==2
        assert state["reply_reads"]==1
        assert runtime.events.get_event_by_command_id(seal.command_id)==seal
        assert not service._dispatch_tasks and service._native_operator_dispatch is None
        assert len(runtime.jobs.list_jobs())==2
        assert runtime.jobs.get_job(root.job_id).status is JobStatus.QUEUED
        assert runtime.jobs.get_job(job.job_id).status is (JobStatus.COMPLETED if reply_committed else JobStatus.FAILED)
        assert service.service_state==("READY" if reply_committed else "QUARANTINED")
        with pytest.raises(StateConflict):runtime.current_harness_binding_source(retained.session.attempt_id)
    asyncio.run(scenario())


def test_unarmed_native_host_refuses_before_retained_provider_or_capacity(tmp_path,monkeypatch):
    async def scenario():
        service,runtime,root,adapters=service_case(tmp_path,monkeypatch)
        service._company_consultation_host.native_return_armed=False
        before=runtime.events.list_events()
        with pytest.raises(StateConflict,match="not armed"):
            await service._run_coo_cycle_once(root.job_id)
        assert not adapters and not runtime.attempts.list_attempts()
        assert runtime.events.list_events()==before
    asyncio.run(scenario())
