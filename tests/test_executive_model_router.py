from __future__ import annotations

import dataclasses
import json

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.model_router import (
    DEFAULT_POLICY_PATH,
    ModelRouter,
    ROUTER_SCHEMA_VERSION,
    RouteMode,
    RoutingPolicyError,
    SuitabilityTier,
    WorkRequest,
)
from control_plane.worker_adapter import (
    WorkerExecutionAdapter,
    adapter_descriptor,
)
from scripts.executive_os_phase1b import main as phase1b_main


_V1_EQUIVALENT_FIRST_TIERS = {
    ("implementation", "routine"): (
        "fast.engineering",
        "standard.engineering",
    ),
    ("implementation", "elevated"): ("standard.engineering",),
    ("mechanical", "routine"): ("fast.engineering", "standard.engineering"),
    ("mechanical", "elevated"): ("standard.engineering",),
    ("tests", "routine"): ("fast.engineering", "standard.engineering"),
    ("tests", "elevated"): ("standard.engineering",),
    ("research", "routine"): ("fast.research", "standard.research"),
    ("research", "elevated"): ("standard.research",),
    ("review", "routine"): ("standard.review",),
    ("review", "elevated"): ("standard.review",),
}

_JOB_CONSTRAINT_KEYS = {
    "task_kind",
    "risk",
    "ambiguity",
    "execution_profile_id",
    "execution_profile_digest",
    "capability_policy_version",
    "capability_policy_digest",
    "preferred_model_aliases",
    "required_capabilities",
    "excluded_worker_ids",
    "routing_policy_version",
    "routing_reason_codes",
}


def _v2_policy() -> dict:
    raw = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    raw["policy_version"] = "2026-09-03.rf1-v2"
    if raw["schema_version"] == "mastermind.executive_worker_routes/v1":
        raw["schema_version"] = "mastermind.executive_worker_routes/v2"
        for task_kind, route in raw["routes"].items():
            for risk in ("routine", "elevated"):
                route[risk] = [
                    {
                        "tier_id": f"{task_kind}.{risk}.primary",
                        "model_aliases": route[risk],
                    }
                ]
    else:
        assert raw["schema_version"] == "mastermind.executive_worker_routes/v2"
    return raw


def _load_policy(tmp_path, raw: dict) -> ModelRouter:
    path = tmp_path / "executive_worker_routes.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return ModelRouter.load(path)


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
    assert implementation.capability_policy_version == "2026-08-29.browser-b1"
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
    assert event.payload["routing_policy_version"] == "2026-09-03.rf1-v2"
    assert event.payload["execution_profile_id"] == "sealed.worker.write.no-extensions.v1"
    assert event.payload["execution_profile_digest"] == decision.execution_profile_digest
    assert event.payload["capability_policy_version"] == decision.capability_policy_version
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
    decision = ModelRouter.load().route(WorkRequest("research"))
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
    assert job.constraints["capability_policy_version"] == decision.capability_policy_version
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


def _two_tier_implementation_policy() -> dict:
    raw = _v2_policy()
    raw["routes"]["implementation"]["routine"] = [
        {
            "tier_id": "implementation.routine.primary",
            "model_aliases": ["fast.engineering", "standard.engineering"],
        },
        {
            "tier_id": "implementation.routine.fallback",
            "model_aliases": ["coo.sealed"],
        },
    ]
    return raw


def test_v2_decision_exposes_ordered_suitability_tiers_and_compatibility_projection(
    tmp_path,
):
    router = _load_policy(tmp_path, _two_tier_implementation_policy())

    decision = router.route(WorkRequest("implementation"))
    assert decision.suitability_tiers == (
        SuitabilityTier(
            "implementation.routine.primary",
            ("fast.engineering", "standard.engineering"),
        ),
        SuitabilityTier("implementation.routine.fallback", ("coo.sealed",)),
    )
    assert decision.preferred_model_aliases == (
        "fast.engineering",
        "standard.engineering",
    )
    assert "preferred_model_aliases" in {
        field.name for field in dataclasses.fields(type(decision))
    }
    assert decision.to_dict()["suitability_tiers"] == [
        {
            "tier_id": "implementation.routine.primary",
            "model_aliases": ["fast.engineering", "standard.engineering"],
        },
        {
            "tier_id": "implementation.routine.fallback",
            "model_aliases": ["coo.sealed"],
        },
    ]
    assert decision.to_dict()["preferred_model_aliases"] == [
        "fast.engineering",
        "standard.engineering",
    ]
    constraints = decision.job_constraints()
    assert set(constraints) == _JOB_CONSTRAINT_KEYS
    assert constraints["preferred_model_aliases"] == [
        "fast.engineering",
        "standard.engineering",
    ]
    assert "suitability_tiers" not in constraints


def test_current_v2_policy_preserves_the_complete_v1_codex_route_inventory():
    router = ModelRouter.load()

    assert ROUTER_SCHEMA_VERSION == "mastermind.executive_worker_routes/v2"
    assert router.policy_version == "2026-09-03.rf1-v2"
    for (task_kind, risk), aliases in _V1_EQUIVALENT_FIRST_TIERS.items():
        decision = router.route(WorkRequest(task_kind, risk=risk))
        assert decision.suitability_tiers == (
            SuitabilityTier(f"{task_kind}.{risk}.primary", aliases),
        )
        assert decision.preferred_model_aliases == aliases
        assert decision.to_dict()["preferred_model_aliases"] == list(aliases)
        assert decision.job_constraints()["preferred_model_aliases"] == list(aliases)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("duplicate_tier_id", "duplicate tier_id"),
        ("empty_tier_id", "bounded lowercase identifier"),
        ("invalid_tier_id", "bounded lowercase identifier"),
        ("empty_aliases", "cannot be empty"),
        ("duplicate_alias_inside", "duplicate alias"),
        ("duplicate_alias_across", "duplicate alias"),
        ("unknown_alias", "ineligible alias"),
        ("ineligible_alias", "ineligible alias"),
        ("unknown_tier_key", "unknown keys"),
        ("capability_mismatch", "lacks capabilities"),
        ("unknown_route_key", "unknown keys"),
    ],
)
def test_v2_policy_refuses_closed_tier_grammar_and_unlawful_aliases(
    tmp_path, mutation, match
):
    raw = _v2_policy()
    tiers = raw["routes"]["implementation"]["routine"]

    if mutation == "duplicate_tier_id":
        tiers.append(
            {
                "tier_id": "implementation.routine.primary",
                "model_aliases": ["coo.sealed"],
            }
        )
    elif mutation == "empty_tier_id":
        tiers[0]["tier_id"] = ""
    elif mutation == "invalid_tier_id":
        tiers[0]["tier_id"] = "invalid tier"
    elif mutation == "empty_aliases":
        tiers[0]["model_aliases"] = []
    elif mutation == "duplicate_alias_inside":
        tiers[0]["model_aliases"] = ["fast.engineering", "fast.engineering"]
    elif mutation == "duplicate_alias_across":
        tiers.append(
            {
                "tier_id": "implementation.routine.fallback",
                "model_aliases": ["fast.engineering"],
            }
        )
    elif mutation == "unknown_alias":
        tiers[0]["model_aliases"] = ["unknown.alias"]
    elif mutation == "ineligible_alias":
        tiers[0]["model_aliases"] = ["frontier.orchestrator"]
    elif mutation == "unknown_tier_key":
        tiers[0]["unexpected"] = True
    elif mutation == "capability_mismatch":
        raw["routes"]["implementation"]["required_capabilities"] = ["judgment"]
    elif mutation == "unknown_route_key":
        raw["routes"]["implementation"]["unexpected"] = True
    else:  # pragma: no cover - parameter table is the complete mutation vocabulary.
        raise AssertionError(f"unknown mutation {mutation!r}")

    with pytest.raises(RoutingPolicyError, match=match):
        _load_policy(tmp_path, raw)


def test_v2_tier_identity_precedes_cost_and_provider_dictionary_order(tmp_path):
    raw = _two_tier_implementation_policy()
    raw["model_aliases"]["fast.engineering"]["cost_class"] = "frontier"
    raw["model_aliases"]["standard.engineering"]["cost_class"] = "frontier"
    raw["model_aliases"]["coo.sealed"]["cost_class"] = "small"
    raw["providers"] = dict(reversed(tuple(raw["providers"].items())))

    decision = _load_policy(tmp_path, raw).route(WorkRequest("implementation"))
    assert decision.suitability_tiers[0].tier_id == "implementation.routine.primary"
    assert decision.suitability_tiers[1].tier_id == "implementation.routine.fallback"
    assert decision.preferred_model_aliases == (
        "fast.engineering",
        "standard.engineering",
    )


def test_v2_alias_order_is_inside_a_tier_but_tier_order_sets_precedence(tmp_path):
    baseline = _load_policy(tmp_path, _two_tier_implementation_policy()).route(
        WorkRequest("implementation")
    )

    reordered_aliases = _two_tier_implementation_policy()
    reordered_aliases["routes"]["implementation"]["routine"][0][
        "model_aliases"
    ] = ["standard.engineering", "fast.engineering"]
    same_precedence = _load_policy(tmp_path, reordered_aliases).route(
        WorkRequest("implementation")
    )
    assert tuple(tier.tier_id for tier in same_precedence.suitability_tiers) == tuple(
        tier.tier_id for tier in baseline.suitability_tiers
    )
    assert same_precedence.suitability_tiers[0].tier_id == (
        baseline.suitability_tiers[0].tier_id
    )

    reordered_tiers = _two_tier_implementation_policy()
    reordered_tiers["routes"]["implementation"]["routine"].reverse()
    changed_precedence = _load_policy(tmp_path, reordered_tiers).route(
        WorkRequest("implementation")
    )
    assert changed_precedence.suitability_tiers[0].tier_id == (
        "implementation.routine.fallback"
    )
    assert changed_precedence.suitability_tiers[0].tier_id != (
        baseline.suitability_tiers[0].tier_id
    )


def test_v2_model_provider_identity_does_not_grant_authority_or_re_admit_frontier(
    tmp_path,
):
    raw = _v2_policy()
    raw["model_aliases"]["fast.engineering"]["model"] = "gpt-5.6-sol"
    raw["model_aliases"]["fast.engineering"]["provider_alias"] = "codex"
    router = _load_policy(tmp_path, raw)

    worker = router.route(WorkRequest("implementation"))
    assert worker.mode is RouteMode.WORKER
    assert "owner_seat" not in worker.to_dict()
    assert "authority" not in worker.to_dict()
    assert "owner_seat" not in worker.job_constraints()
    assert "authority" not in worker.job_constraints()

    with pytest.raises(RoutingPolicyError, match="not worker eligible"):
        router.resolve_model_alias("frontier.orchestrator")
    frontier = router.route(WorkRequest("implementation", ambiguity="high"))
    assert frontier.mode is RouteMode.FRONTIER_LEAD
    assert not frontier.worker_eligible
    assert frontier.suitability_tiers == (
        SuitabilityTier("frontier.lead", ("frontier.orchestrator",)),
    )


def test_v2_review_exclusions_survive_structured_tiers_and_claim_projection():
    review = ModelRouter.load().route(
        WorkRequest("review", excluded_worker_ids=("builder-01",))
    )

    assert review.suitability_tiers == (
        SuitabilityTier("review.routine.primary", ("standard.review",)),
    )
    assert review.excluded_worker_ids == ("builder-01",)
    assert review.to_dict()["excluded_worker_ids"] == ["builder-01"]
    assert review.job_constraints()["excluded_worker_ids"] == ["builder-01"]
