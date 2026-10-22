"""Provider alias integrity for the EXISTING Executive Capacity/ModelRouter owner.

Temporary SQLite only. A Fabric pool's free slots are NOT equivalent to an
Executive registered worker quota, valid model alias or live provider grant.
"""
import pytest

from control_plane.executive_runtime import Runtime
from control_plane.model_router import ModelRouter, WorkRequest


def decision_and_job(runtime, model_alias="fast.research"):
    router=ModelRouter.load()
    decision=router.route(WorkRequest("research",risk="routine"))
    constraints=decision.job_constraints()
    constraints["eligible_quota_classes"]=["fixture"]
    job=runtime.jobs.create_job("Read bounded synthetic evidence only",
                                constraints=constraints,
                                requested_authorities=["READ","RESEARCH"])
    profile=router.resolve_model_alias(model_alias)
    return router,job,profile


def register_claimable_worker(runtime,router,profile,*,worker_id,
                              provider=None,model=None,effort=None,
                              cost_class=None,adapter_id=None):
    provider=profile.provider_alias if provider is None else provider
    runtime.workers.register_worker(
        worker_id,provider=provider,
        account_label="synthetic-no-real-provider",worker_type=adapter_id or profile.adapter_id,
        capabilities=list(profile.capabilities),
        quota_classes={"fixture":{
            "provider":provider,
            "model":model or profile.model,
            "effort":effort or profile.effort,
            "cost_class":cost_class or profile.cost_class,
            "capabilities":list(profile.capabilities),
            "metadata":{
                "adapter_id":profile.adapter_id,
                "model_alias":profile.model_alias,
                "provider_alias":profile.provider_alias,
                "routing_policy_version":router.policy_version,
                "execution_profile_id":profile.execution_profile_id,
                "execution_profile_digest":profile.execution_profile_digest,
                "capability_policy_version":profile.capability_policy_version,
                "capability_policy_digest":profile.capability_policy_digest,
            },
        }},
    )


def test_exact_codex_research_profile_keeps_original_worker_claim(tmp_path):
    runtime=Runtime.at(tmp_path/"positive")
    router,job,profile=decision_and_job(runtime)
    register_claimable_worker(runtime,router,profile,worker_id="legitimate-codex")
    lease=runtime.broker.claim(job.job_id,lease_owner="fixture-no-provider-start")
    assert lease is not None
    assert lease.attempt.worker_id=="legitimate-codex"


@pytest.mark.parametrize("change",[
    {"provider":"glm","adapter_id":"openai-compatible"},
    {"provider":"qwen","adapter_id":"openai-compatible"},
    {"provider":"xai","adapter_id":"openai-compatible"},
    {"model":"some-unconfigured-model"},
    {"effort":"xhigh"},
    {"cost_class":"frontier"},
])
def test_external_or_wrong_quota_cannot_spoof_codex_policy_alias(tmp_path,change):
    runtime=Runtime.at(tmp_path/"negative")
    router,job,profile=decision_and_job(runtime)
    register_claimable_worker(runtime,router,profile,
                              worker_id="adversarial-capacity",**change)
    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.claim(job.job_id,lease_owner="fixture-no-provider-start") is None
    assert runtime.jobs.get_job(job.job_id).current_attempt_id is None


def test_m2_fabric_capacity_is_not_itself_an_executive_worker_quota(tmp_path):
    runtime=Runtime.at(tmp_path/"empty")
    router,job,profile=decision_and_job(runtime)
    assert router.resolve_model_alias("fast.research").provider_alias=="codex"
    assert router.resolve_model_alias("standard.research").provider_alias=="codex"
    assert runtime.broker.claim(job.job_id) is None
    assert runtime.workers.list_workers()==[]


def test_host_bound_custom_policy_version_keeps_its_exact_registered_quota(tmp_path):
    import json
    from pathlib import Path

    default=Path(__file__).resolve().parents[1]/"config/executive_worker_routes.json"
    document=json.loads(default.read_text())
    document["policy_version"]="2026-10-13.custom-capacity-source-fixture"
    custom=tmp_path/"host-owner-policy.json"
    custom.write_text(json.dumps(document,sort_keys=True))
    router=ModelRouter.load(custom)
    assert router.policy_version!=ModelRouter.load().policy_version

    # No worker/Job may choose this path; only the trusted Runtime host
    # constructs its broker with a specific existing router source.
    runtime=Runtime.at(tmp_path/"custom-runtime",routing_policy_path=custom)
    profile=router.resolve_model_alias("fast.research")
    register_claimable_worker(runtime,router,profile,worker_id="host-custom-policy")
    constraints=router.route(WorkRequest("research",risk="routine")).job_constraints()
    constraints["eligible_quota_classes"]=["fixture"]
    job=runtime.jobs.create_job("Synthetic host-owned research policy",
                                constraints=constraints,
                                requested_authorities=["READ","RESEARCH"])
    assert runtime.broker.select_worker(job) is not None
    # Same queued durable Job, but a default-policy *reader* cannot interpret
    # the custom host's capacity as an independently admitted route.
    fallback=Runtime.at(tmp_path/"custom-runtime")
    assert fallback.broker.select_worker(
        fallback.jobs.get_job(job.job_id)
    ) is None
    assert runtime.jobs.get_job(job.job_id).current_attempt_id is None
    lease=runtime.broker.claim(job.job_id,lease_owner="fixture-no-provider")
    assert lease is not None
    assert lease.attempt.worker_id=="host-custom-policy"


def test_registered_external_pool_metadata_omission_is_not_a_false_refusal(tmp_path):
    # Existing external_pool_binding producer attaches provider and adapter
    # to physical Worker rows, not necessarily redundant quota metadata.
    runtime=Runtime.at(tmp_path/"external-producer")
    router,job,profile=decision_and_job(runtime)
    metadata={
        "model_alias":profile.model_alias,
        "routing_policy_version":router.policy_version,
        "execution_profile_id":profile.execution_profile_id,
        "execution_profile_digest":profile.execution_profile_digest,
        "capability_policy_version":profile.capability_policy_version,
        "capability_policy_digest":profile.capability_policy_digest,
    }
    runtime.workers.register_worker(
        "external-producer-metadata",
        provider=profile.provider_alias,
        account_label="synthetic-no-provider",
        worker_type=profile.adapter_id,
        capabilities=list(profile.capabilities),
        quota_classes={"fixture":{
            "provider":profile.provider_alias,
            "model":profile.model,
            "effort":profile.effort,
            "cost_class":profile.cost_class,
            "capabilities":list(profile.capabilities),
            "metadata":metadata,
        }},
    )
    assert runtime.broker.select_worker(job).worker_id=="external-producer-metadata"
    lease=runtime.broker.claim(job.job_id,lease_owner="fixture-no-provider")
    assert lease is not None and lease.attempt.worker_id=="external-producer-metadata"


def test_policy_changed_between_candidate_scan_and_atomic_claim_cannot_start(tmp_path,monkeypatch):
    import json

    from pathlib import Path
    original=Path(__file__).resolve().parents[1]/"config/executive_worker_routes.json"
    source=json.loads(original.read_text())
    custom=tmp_path/"mutable-host-route.json"
    custom.write_text(json.dumps(source,sort_keys=True))
    runtime=Runtime.at(tmp_path/"mutable-runtime",routing_policy_path=custom)
    router=ModelRouter.load(custom)
    profile=router.resolve_model_alias("fast.research")
    for name in ("one-eligible","two-eligible"):
        register_claimable_worker(runtime,router,profile,worker_id=name)
    constraints=router.route(WorkRequest("research",risk="routine")).job_constraints()
    constraints["eligible_quota_classes"]=["fixture"]
    job=runtime.jobs.create_job("Inspect one synthetic input",
                                constraints=constraints,
                                requested_authorities=["READ","RESEARCH"])
    original_load=ModelRouter.load.__func__
    visits=[]

    def change_between_policy_reads(cls,path=None,*,capability_policy_path=None):
        visits.append(path)
        if len(visits)==2:
            changed=json.loads(custom.read_text())
            changed["policy_version"]="revoked-after-scan-v2"
            custom.write_text(json.dumps(changed,sort_keys=True))
        return original_load(cls,path,capability_policy_path=capability_policy_path)

    with monkeypatch.context() as patch:
        patch.setattr(ModelRouter,"load",classmethod(change_between_policy_reads))
        assert runtime.broker.claim(job.job_id,lease_owner="fixture-no-provider") is None
    assert len(visits)==2
    assert runtime.jobs.get_job(job.job_id).status.value=="QUEUED"
    assert runtime.attempts.list_attempts(job_id=job.job_id)==[]


@pytest.mark.parametrize("command",["workers","jobs","attempts","events"])
def test_legacy_inspection_cli_commands_keep_runtime_without_policy_attribute(
    command,tmp_path,capsys,
):
    # These commands predate policy selection. main() must neither
    # crash on absent argparse field nor try a provider or claim work.
    from scripts.executive_os_phase1b import main
    args=["--root",str(tmp_path/"cli"),command]
    assert main(args)==0
    captured=capsys.readouterr()
    assert captured.err==""
    assert captured.out.strip() in ("[]","{}")


@pytest.mark.parametrize("command",["run-once","reconcile"])
def test_worker_cli_carries_host_selected_policy_for_both_execution_commands(command,tmp_path):
    from scripts.executive_os_phase1b import _parser
    args=[
        "--root",str(tmp_path/"noop"),command,
        "--routing-policy",str(tmp_path/"host-policy.json"),
        "--codex-binary",str(tmp_path/"never-executed-codex"),
        "--codex-home",str(tmp_path/"private-unopened"),
        "--allowed-version","fixture-reviewed",
    ]
    if command=="run-once":args.append("JOB-001")
    parsed=_parser().parse_args(args)
    assert parsed.routing_policy==tmp_path/"host-policy.json"
    assert parsed.command==command
