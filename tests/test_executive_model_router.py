from __future__ import annotations

import json

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.model_router import (
    DEFAULT_POLICY_PATH,
    ModelRouter,
    RouteMode,
    RoutingPolicyError,
    WorkRequest,
)
from control_plane.worker_adapter import (
    WorkerExecutionAdapter,
    adapter_descriptor,
)
from scripts.executive_os_phase1b import main as phase1b_main


def test_economical_workers_handle_bounded_work_and_frontier_keeps_judgment():
    router = ModelRouter.load()

    implementation = router.route(WorkRequest("implementation"))
    assert implementation.mode is RouteMode.WORKER
    assert implementation.preferred_model_aliases == (
        "fast.engineering",
        "standard.engineering",
    )
    assert implementation.required_capabilities == ("code",)
    assert implementation.execution_profile_id == "sealed.worker.write.no-extensions.v1"
    assert len(implementation.execution_profile_digest) == 64
    assert implementation.capability_policy_version == "2026-08-24.g0"
    assert len(implementation.capability_policy_digest) == 64

    elevated = router.route(WorkRequest("implementation", risk="elevated"))
    assert elevated.preferred_model_aliases == ("standard.engineering",)

    research = router.route(WorkRequest("research"))
    assert research.preferred_model_aliases == (
        "fast.research",
        "standard.research",
    )

    review = router.route(
        WorkRequest("review", excluded_worker_ids=("builder-01",))
    )
    assert review.preferred_model_aliases == ("standard.review",)
    assert review.excluded_worker_ids == ("builder-01",)
    assert "review_worker_exclusion" in review.reason_codes

    for request in (
        WorkRequest("planning"),
        WorkRequest("judgment"),
        WorkRequest("escalation"),
        WorkRequest("implementation", risk="critical"),
        WorkRequest("implementation", ambiguity="high"),
    ):
        decision = router.route(request)
        assert decision.mode is RouteMode.FRONTIER_LEAD
        assert decision.preferred_model_aliases == ("frontier.orchestrator",)
        assert decision.execution_profile_id == "operator.appserver.readonly.v1"
        with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
            decision.job_constraints()


def test_policy_has_unarmed_provider_seams_and_only_codex_is_currently_eligible():
    router = ModelRouter.load()

    assert router.providers["codex"].enabled
    assert router.providers["codex"].autonomous_allowed
    for provider in ("qwen", "glm", "xai"):
        assert not router.providers[provider].enabled
        assert not router.providers[provider].autonomous_allowed
        assert router.providers[provider].adapter_id == "openai-compatible"

    luna = router.resolve_model_alias("fast.engineering")
    assert luna.model == "gpt-5.6-luna"
    assert luna.adapter_id == "codex-cli"
    assert luna.worker_eligible
    terra = router.resolve_model_alias("standard.review")
    assert terra.model == "gpt-5.6-terra"
    assert terra.execution_profile_id == "sealed.worker.readonly.no-extensions.v1"

    assert adapter_descriptor("codex-cli").implemented
    assert not adapter_descriptor("openai-compatible").implemented


def test_policy_refuses_production_arming_or_an_unimplemented_live_provider(tmp_path):
    raw = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    raw["production_armed"] = True
    armed = tmp_path / "armed.json"
    armed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RoutingPolicyError, match="production_armed=false"):
        ModelRouter.load(armed)

    raw["production_armed"] = False
    raw["providers"]["qwen"]["enabled"] = True
    raw["providers"]["qwen"]["autonomous_allowed"] = True
    unimplemented = tmp_path / "unimplemented.json"
    unimplemented.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RoutingPolicyError, match="unimplemented adapter"):
        ModelRouter.load(unimplemented)


def _register_alias_worker(
    runtime: Runtime,
    *,
    worker_id: str,
    model_alias: str,
) -> None:
    profile = ModelRouter.load().resolve_model_alias(model_alias)
    runtime.workers.register_worker(
        worker_id,
        provider=profile.provider_alias,
        account_label=f"account-{worker_id}",
        worker_type=profile.adapter_id,
        capabilities=list(profile.capabilities),
        quota_classes={
            "default": {
                "provider": profile.provider_alias,
                "model": profile.model,
                "effort": profile.effort,
                "cost_class": profile.cost_class,
                "capabilities": list(profile.capabilities),
                "metadata": {
                    "adapter_id": profile.adapter_id,
                    "model_alias": profile.model_alias,
                    "provider_alias": profile.provider_alias,
                    "routing_policy_version": ModelRouter.load().policy_version,
                    "execution_profile_id": profile.execution_profile_id,
                    "execution_profile_digest": profile.execution_profile_digest,
                    "capability_policy_version": profile.capability_policy_version,
                    "capability_policy_digest": profile.capability_policy_digest,
                },
            }
        },
    )


def test_runtime_claim_honors_alias_order_before_worker_id_and_records_receipt(tmp_path):
    runtime = Runtime.at(tmp_path)
    # The fallback sorts first lexically.  Route order must still pick Luna.
    _register_alias_worker(
        runtime, worker_id="aaa-terra", model_alias="standard.engineering"
    )
    _register_alias_worker(
        runtime, worker_id="zzz-luna", model_alias="fast.engineering"
    )
    decision = ModelRouter.load().route(WorkRequest("implementation"))
    job = runtime.jobs.create_job("Implement a bounded module", constraints=decision.job_constraints())

    selected = runtime.broker.select_worker(job)
    assert selected is not None and selected.worker_id == "zzz-luna"

    lease = runtime.broker.claim(job.job_id)
    assert lease is not None
    assert lease.attempt.worker_id == "zzz-luna"
    event = runtime.events.list_events(job_id=job.job_id)[-1]
    assert event.event_type == "JOB_CLAIMED"
    assert event.payload["selected_model_alias"] == "fast.engineering"
    assert event.payload["preferred_model_aliases"] == [
        "fast.engineering",
        "standard.engineering",
    ]
    assert event.payload["routing_policy_version"] == "2026-08-24.stage2"
    assert event.payload["execution_profile_id"] == "sealed.worker.write.no-extensions.v1"
    assert event.payload["execution_profile_digest"] == decision.execution_profile_digest
    assert event.payload["capability_policy_version"] == "2026-08-24.g0"
    assert event.payload["capability_policy_digest"] == decision.capability_policy_digest


def test_review_route_excludes_builder_worker_at_claim(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register_alias_worker(
        runtime, worker_id="review-a", model_alias="standard.review"
    )
    _register_alias_worker(
        runtime, worker_id="review-b", model_alias="standard.review"
    )
    decision = ModelRouter.load().route(
        WorkRequest("review", excluded_worker_ids=("review-a",))
    )
    job = runtime.jobs.create_job("Review bounded work", constraints=decision.job_constraints())

    selected = runtime.broker.select_worker(job)
    assert selected is not None and selected.worker_id == "review-b"
    lease = runtime.broker.claim(job.job_id)
    assert lease is not None and lease.attempt.worker_id == "review-b"


def test_runtime_refuses_worker_capacity_from_a_stale_routing_policy(tmp_path):
    runtime = Runtime.at(tmp_path)
    profile = ModelRouter.load().resolve_model_alias("fast.engineering")
    runtime.workers.register_worker(
        "luna-stale",
        provider=profile.provider_alias,
        account_label="account-luna-stale",
        worker_type=profile.adapter_id,
        capabilities=list(profile.capabilities),
        quota_classes={
            "default": {
                "provider": profile.provider_alias,
                "model": profile.model,
                "effort": profile.effort,
                "cost_class": profile.cost_class,
                "capabilities": list(profile.capabilities),
                "metadata": {
                    "adapter_id": profile.adapter_id,
                    "model_alias": profile.model_alias,
                    "provider_alias": profile.provider_alias,
                    "routing_policy_version": "2026-08-15.stale",
                    "execution_profile_id": profile.execution_profile_id,
                    "execution_profile_digest": profile.execution_profile_digest,
                    "capability_policy_version": profile.capability_policy_version,
                    "capability_policy_digest": profile.capability_policy_digest,
                },
            }
        },
    )
    decision = ModelRouter.load().route(WorkRequest("implementation"))
    job = runtime.jobs.create_job(
        "Do not claim stale capacity", constraints=decision.job_constraints()
    )

    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.claim(job.job_id) is None


def test_runtime_refuses_capacity_with_a_different_capability_profile_digest(tmp_path):
    runtime = Runtime.at(tmp_path)
    router = ModelRouter.load()
    profile = router.resolve_model_alias("fast.engineering")
    runtime.workers.register_worker(
        "luna-wrong-grant",
        provider=profile.provider_alias,
        account_label="account-luna-wrong-grant",
        worker_type=profile.adapter_id,
        capabilities=list(profile.capabilities),
        quota_classes={
            "default": {
                "provider": profile.provider_alias,
                "model": profile.model,
                "effort": profile.effort,
                "cost_class": profile.cost_class,
                "capabilities": list(profile.capabilities),
                "metadata": {
                    "adapter_id": profile.adapter_id,
                    "model_alias": profile.model_alias,
                    "provider_alias": profile.provider_alias,
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": profile.execution_profile_id,
                    "execution_profile_digest": "0" * 64,
                    "capability_policy_version": profile.capability_policy_version,
                    "capability_policy_digest": profile.capability_policy_digest,
                },
            }
        },
    )
    decision = router.route(WorkRequest("implementation"))
    job = runtime.jobs.create_job(
        "Do not claim capacity attested for another tool grant",
        constraints=decision.job_constraints(),
    )

    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.claim(job.job_id) is None


def test_cli_preview_is_read_only_and_alias_registration_is_policy_derived(
    tmp_path, capsys
):
    root = tmp_path / "runtime"
    assert phase1b_main(
        ["--root", str(root), "route", "implementation"]
    ) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["mode"] == "worker"
    assert preview["preferred_model_aliases"][0] == "fast.engineering"
    assert not (root / "data" / "control_plane" / "executive.sqlite3").exists()

    assert phase1b_main(
        [
            "--root",
            str(root),
            "register-worker",
            "luna-01",
            "--account-label",
            "codex-worker-account-01",
            "--model-alias",
            "fast.engineering",
        ]
    ) == 0
    capsys.readouterr()
    runtime = Runtime.at(root)
    worker = runtime.workers.get_worker("luna-01")
    assert worker is not None
    quota = runtime.workers.get_quota_class("luna-01", "default")
    assert quota is not None
    assert quota.model == "gpt-5.6-luna"
    assert quota.effort == "high"
    assert quota.metadata["model_alias"] == "fast.engineering"
    assert quota.metadata["execution_profile_id"] == "sealed.worker.write.no-extensions.v1"
    assert len(quota.metadata["execution_profile_digest"]) == 64
    assert worker.metadata["stage1_production_armed"] is False


def test_cli_routed_job_persists_semantics_without_raw_provider_selection(
    tmp_path, capsys
):
    root = tmp_path / "runtime"
    assert phase1b_main(
        [
            "--root",
            str(root),
            "create-job",
            "Research a bounded source set",
            "--task-kind",
            "research",
            "--risk",
            "routine",
        ]
    ) == 0
    capsys.readouterr()
    job = Runtime.at(root).jobs.list_jobs()[0]
    assert job.constraints["task_kind"] == "research"
    assert job.constraints["preferred_model_aliases"] == [
        "fast.research",
        "standard.research",
    ]
    assert job.constraints["execution_profile_id"] == "sealed.worker.readonly.no-extensions.v1"
    assert len(job.constraints["execution_profile_digest"]) == 64
    assert job.constraints["capability_policy_version"] == "2026-08-24.g0"
    assert len(job.constraints["capability_policy_digest"]) == 64
    assert "provider" not in job.constraints
    assert "model" not in job.constraints


def test_common_worker_adapter_protocol_is_provider_neutral():
    class FakeAdapter:
        inspector = object()

        async def start(self, spec):
            return None

        async def collect_result(self, ref):
            return None

        async def cancel(self, ref, reason):
            return None

        async def run_validation_argv(self, spec, argv, *, timeout_seconds=300.0):
            return None

    assert isinstance(FakeAdapter(), WorkerExecutionAdapter)
