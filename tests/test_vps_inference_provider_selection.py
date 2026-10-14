"""Test-owned original service to existing Capacity/ModelRouter provider parity.

This file is staged OUTSIDE the reviewed source files until the independent
source review returns. No worker process, Fabric queue or provider execution.
"""
import asyncio

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.model_router import ModelRouter
from control_plane.executive_inference_execution import build_execution_binding
from control_plane import executive_inference_ingress as service
from tests.test_vps_inference_service import GROUND, service_request
from tests.test_vps_inference_task_fit import request
from tests.test_service_capacity_provider_identity import register_claimable_worker


class Grounding:
    def observe(self):
        return GROUND


@pytest.mark.parametrize("purpose,selected_alias", [
    ("evidence_extraction", "fast.research"),
    ("comparative_analysis", "standard.research"),
])
def test_actual_service_job_claim_refuses_cross_provider_alias_then_selects_real_policy_match(
    tmp_path, purpose, selected_alias,
):
    runtime=Runtime.at(tmp_path/"runtime")
    wire=request(purpose)
    operation="capacity-exact-service-"+purpose.replace("_","-")
    created=asyncio.run(service.handle_frame(
        {"schema":service.SUBMIT_SCHEMA,
         "request":service_request(operation_key=operation,request=wire),
         "observed_grounding":GROUND},
        runtime=runtime, grounding_provider=Grounding(), workspace_root=tmp_path,
        admission_guard=lambda _: None,
        execution_binding_provider=lambda identity: build_execution_binding(
            intent_id=identity, workspace_root=tmp_path, base_sha="a"*40,
            eligible_quota_classes=("fixture",), inference_request=wire),
    ))
    job=runtime.jobs.get_job(created["job_id"])
    assert job.status.value=="QUEUED"
    router=ModelRouter.load()
    profile=router.resolve_model_alias(selected_alias)

    # This pool holds external slots, NOT the configured Codex model.
    register_claimable_worker(
        runtime,router,profile,worker_id="aaa-glm-not-qualified",
        provider="glm",adapter_id="openai-compatible")
    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.claim(job.job_id,lease_owner="synthetic-nonexecuting") is None
    assert not runtime.attempts.list_attempts(job_id=job.job_id)

    # Register a second, exact physical quota under the same original Job.
    # The original job and identity remain untouched.
    register_claimable_worker(
        runtime,router,profile,worker_id="zzz-codex-qualified")
    preview=runtime.broker.select_worker(job)
    assert preview is not None
    assert preview.worker_id=="zzz-codex-qualified"
    claimed=runtime.broker.claim(job.job_id,lease_owner="synthetic-nonexecuting")
    assert claimed is not None
    assert claimed.attempt.worker_id=="zzz-codex-qualified"
    assert len(runtime.attempts.list_attempts(job_id=job.job_id))==1
    assert runtime.jobs.get_job(job.job_id).status.value=="RUNNING"
    assert claimed.attempt.status.value=="CLAIMED"
    # A test-owned claim creates no model process, answer, capital authority
    # or remotely paid Fabric run.


def test_physical_adapter_cannot_claim_codex_alias_by_metadata_only(tmp_path):
    runtime=Runtime.at(tmp_path/"adapter-source")
    router=ModelRouter.load()
    decision=router.route(__import__("control_plane.model_router",fromlist=["WorkRequest"]).WorkRequest(
        "research",risk="routine",required_capabilities=("research",)))
    constraints=decision.job_constraints()
    constraints["eligible_quota_classes"]=["fixture"]
    job=runtime.jobs.create_job("Synthetic review input",constraints=constraints,
                                requested_authorities=["READ","RESEARCH"])
    profile=router.resolve_model_alias("fast.research")
    register_claimable_worker(
        runtime,router,profile,worker_id="codex-name-wrong-adapter",
        provider="codex",adapter_id="openai-compatible")
    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.claim(job.job_id) is None
    assert runtime.attempts.list_attempts(job_id=job.job_id)==[]
