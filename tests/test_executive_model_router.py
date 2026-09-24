from __future__ import annotations

import dataclasses
import json

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.model_router import (
    DEFAULT_POLICY_PATH,
    ModelRouter,
    ProviderAlias,
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
from scripts.executive_os_phase1c_worker import (  # noqa: E402  (import-order pinned by the existing top-of-file block)
    WorkerConfigError,
    _assert_service_activation_allowed,
)


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

_V1_ROUTING_POLICY_VERSION = "2026-08-24.stage4"

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
    assert implementation.capability_policy_version == "2026-09-18.browser-b1-runtime-r2"
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


def test_policy_has_unarmed_provider_seams_and_codex_and_minimax_are_the_only_eligible_seams():
    router = ModelRouter.load()

    assert router.providers["codex"].enabled
    assert router.providers["codex"].autonomous_allowed
    assert router.providers["minimax"].enabled
    assert router.providers["minimax"].autonomous_allowed
    assert router.providers["minimax"].adapter_id == "codex-cli"
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

    minimax_alias = router.resolve_model_alias("coo.sealed.minimax")
    assert minimax_alias.provider_alias == "minimax"
    assert minimax_alias.adapter_id == "codex-cli"
    assert minimax_alias.worker_eligible

    assert adapter_descriptor("codex-cli").implemented
    assert not adapter_descriptor("openai-compatible").implemented


def test_minimax_alias_resolves_same_sealed_profile_as_codex():
    router = ModelRouter.load()

    codex_sealed = router.resolve_model_alias("coo.sealed")
    minimax_sealed = router.resolve_model_alias("coo.sealed.minimax")

    # Same execution surface — only the provider seam differs.
    assert (
        minimax_sealed.execution_profile_id
        == codex_sealed.execution_profile_id
    )
    assert (
        minimax_sealed.execution_profile_digest
        == codex_sealed.execution_profile_digest
    )
    assert minimax_sealed.capabilities == codex_sealed.capabilities
    assert minimax_sealed.model == codex_sealed.model
    assert minimax_sealed.effort == codex_sealed.effort
    assert minimax_sealed.cost_class == codex_sealed.cost_class
    # Provider seam is the one field that must differ.
    assert minimax_sealed.provider_alias != codex_sealed.provider_alias
    assert minimax_sealed.provider_alias == "minimax"
    assert codex_sealed.provider_alias == "codex"
    # Adapter is identical (both sides honour the Codex-cli review).
    assert minimax_sealed.adapter_id == codex_sealed.adapter_id == "codex-cli"


def test_minimax_alias_is_not_the_host_binding(tmp_path):
    """A worker constrained to the codex-sealed profile cannot byte-match a
    minimax-registered worker today. The two seams diverge on
    ``model_alias`` metadata, so ``_capacity_matches_route`` will refuse a
    minimax worker for a Job constrained to ``coo.sealed``.
    """

    router = ModelRouter.load()
    codex_sealed = router.resolve_model_alias("coo.sealed")
    minimax_sealed = router.resolve_model_alias("coo.sealed.minimax")

    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "codex-sealed-01",
        provider=codex_sealed.provider_alias,
        account_label="account-codex-sealed",
        worker_type=codex_sealed.adapter_id,
        capabilities=list(codex_sealed.capabilities),
        quota_classes={
            "default": {
                "provider": codex_sealed.provider_alias,
                "model": codex_sealed.model,
                "effort": codex_sealed.effort,
                "cost_class": codex_sealed.cost_class,
                "capabilities": list(codex_sealed.capabilities),
                "metadata": {
                    "adapter_id": codex_sealed.adapter_id,
                    "model_alias": codex_sealed.model_alias,
                    "provider_alias": codex_sealed.provider_alias,
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": codex_sealed.execution_profile_id,
                    "execution_profile_digest": codex_sealed.execution_profile_digest,
                    "capability_policy_version": codex_sealed.capability_policy_version,
                    "capability_policy_digest": codex_sealed.capability_policy_digest,
                },
            }
        },
    )
    runtime.workers.register_worker(
        "minimax-sealed-01",
        provider=minimax_sealed.provider_alias,
        account_label="account-minimax-sealed",
        worker_type=minimax_sealed.adapter_id,
        capabilities=list(minimax_sealed.capabilities),
        quota_classes={
            "default": {
                "provider": minimax_sealed.provider_alias,
                "model": minimax_sealed.model,
                "effort": minimax_sealed.effort,
                "cost_class": minimax_sealed.cost_class,
                "capabilities": list(minimax_sealed.capabilities),
                "metadata": {
                    "adapter_id": minimax_sealed.adapter_id,
                    "model_alias": minimax_sealed.model_alias,
                    "provider_alias": minimax_sealed.provider_alias,
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": minimax_sealed.execution_profile_id,
                    "execution_profile_digest": minimax_sealed.execution_profile_digest,
                    "capability_policy_version": minimax_sealed.capability_policy_version,
                    "capability_policy_digest": minimax_sealed.capability_policy_digest,
                },
            }
        },
    )

    decision = router.route(WorkRequest("implementation"))
    constraints = dict(decision.job_constraints())
    # Implementation is cox-sealed-tiered — neither coo.sealed nor
    # coo.sealed.minimax is on the surface for that decision today, and
    # no alias on the implementation path is the minimax seam.
    assert "coo.sealed" not in constraints["preferred_model_aliases"]
    assert "coo.sealed.minimax" not in constraints["preferred_model_aliases"]
    for alias in constraints["preferred_model_aliases"]:
        profile = router.resolve_model_alias(alias)
        assert profile.provider_alias != "minimax"

    implement_job = runtime.jobs.create_job(
        "Sealed work, codex-bound", constraints=constraints
    )
    assert runtime.broker.select_worker(implement_job) is None

    # Now bind an explicit Job to the codex-sealed alias only and prove the
    # codex worker is byte-matched while the minimax worker is not.
    codex_sealed_profile = router.resolve_model_alias("coo.sealed")
    codex_sealed_only = {
        **constraints,
        "preferred_model_aliases": [codex_sealed_profile.model_alias],
    }
    sealed_job = runtime.jobs.create_job(
        "Sealed codex only", constraints=codex_sealed_only
    )
    sealed_selected = runtime.broker.select_worker(sealed_job)
    assert sealed_selected is not None
    assert sealed_selected.worker_id == "codex-sealed-01"
    sealed_lease = runtime.broker.claim(sealed_job.job_id)
    assert sealed_lease is not None
    assert sealed_lease.attempt.worker_id == "codex-sealed-01"


def test_minimax_binding_activation_still_refused():
    """Adding the ``minimax`` provider seam does not arm its subscription
    binding — ``_assert_service_activation_allowed`` keeps refusing it.
    """

    config = {
        "schema_version": "mastermind.executive_worker_broker_config/v5",
        "harness_binding_id": "minimax-token-plan.codex-responses",
    }
    with pytest.raises(WorkerConfigError):
        _assert_service_activation_allowed(config)


def test_openai_compatible_provider_block_remains_refused(tmp_path):
    """The closed rule is unchanged: a provider on the unimplemented
    ``openai-compatible`` adapter cannot be armed even when the alias
    targets it. Pins the refusal so future minimax-shaped provider blocks
    cannot quietly bypass it.
    """

    raw = _v2_policy()
    raw["providers"]["minimax"] = {
        "adapter_id": "openai-compatible",
        "enabled": True,
        "autonomous_allowed": True,
    }
    raw["model_aliases"]["coo.sealed.minimax"] = {
        "provider_alias": "minimax",
        "execution_profile_id": ModelRouter.load()
        .model_aliases["coo.sealed"]
        .execution_profile_id,
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "cost_class": "small",
        "capabilities": ["code", "planning", "research", "review", "tests"],
        "worker_eligible": True,
    }
    path = tmp_path / "openai-compatible-provider.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RoutingPolicyError, match="unimplemented adapter"):
        ModelRouter.load(path)


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


def test_heterogeneous_pair_does_not_arm_general_routing_or_bypass_capacity(tmp_path):
    checked_in = ModelRouter.load()
    pair = _v2_policy()
    pair["providers"]["claude"] = {
        "adapter_id": "openai-compatible",
        "enabled": False,
        "autonomous_allowed": False,
    }
    pair["model_aliases"]["hf1q.claude.fixture"] = {
        "provider_alias": "claude",
        "execution_profile_id": checked_in.model_aliases[
            "fast.engineering"
        ].execution_profile_id,
        "model": "hf1q-fixture-model",
        "effort": "high",
        "cost_class": "small",
        "capabilities": ["code"],
        "worker_eligible": False,
    }
    fixture = _load_policy(tmp_path, pair)

    assert checked_in.providers["codex"].enabled
    assert fixture.providers["claude"] == ProviderAlias(
        "claude",
        "openai-compatible",
        False,
        False,
    )
    assert fixture.model_aliases["hf1q.claude.fixture"].worker_eligible is False
    with pytest.raises(RoutingPolicyError, match="not worker eligible"):
        fixture.resolve_model_alias("hf1q.claude.fixture")

    for provider in ("qwen", "glm", "xai"):
        assert not checked_in.providers[provider].enabled
        assert not checked_in.providers[provider].autonomous_allowed

    bypasses = {
        "enabled only": {
            **pair,
            "providers": {
                **pair["providers"],
                "claude": {**pair["providers"]["claude"], "enabled": True},
            },
        },
        "autonomous only": {
            **pair,
            "providers": {
                **pair["providers"],
                "claude": {**pair["providers"]["claude"], "autonomous_allowed": True},
            },
        },
        "worker alias": {
            **pair,
            "model_aliases": {
                **pair["model_aliases"],
                "hf1q.claude.fixture": {
                    **pair["model_aliases"]["hf1q.claude.fixture"],
                    "worker_eligible": True,
                },
            },
        },
    }
    for name, raw in bypasses.items():
        policy_dir = tmp_path / name.replace(" ", "-")
        policy_dir.mkdir()
        with pytest.raises(
            RoutingPolicyError,
            match="unimplemented adapter|enabled autonomous provider",
        ):
            _load_policy(policy_dir, raw)

    runtime = Runtime.at(tmp_path / "runtime")
    codex = checked_in.resolve_model_alias("fast.engineering")
    runtime.workers.register_worker(
        "hf1q-codex-capacity",
        provider=codex.provider_alias,
        account_label="fixture-account-codex",
        worker_type=codex.adapter_id,
        capabilities=list(codex.capabilities),
        quota_classes={"default": {"provider": codex.provider_alias}},
    )
    decision = checked_in.route(WorkRequest("implementation"))
    job = runtime.jobs.create_job(
        "Policy-scoped fixture job", constraints=decision.job_constraints()
    )
    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.claim(job.job_id) is None
    event_types = [event.event_type for event in runtime.events.list_events()]
    assert "JOB_CLAIMED" not in event_types


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
    assert event.payload["routing_policy_version"] == _V1_ROUTING_POLICY_VERSION
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
        adapter_id = "codex-cli"
        inspector = object()

        async def start(self, spec):
            return None

        async def status(self, ref):
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


def test_current_v2_schema_preserves_the_complete_v1_codex_route_and_policy_contract():
    router = ModelRouter.load()

    assert ROUTER_SCHEMA_VERSION == "mastermind.executive_worker_routes/v2"
    assert router.policy_version == _V1_ROUTING_POLICY_VERSION
    for (task_kind, risk), aliases in _V1_EQUIVALENT_FIRST_TIERS.items():
        decision = router.route(WorkRequest(task_kind, risk=risk))
        assert decision.suitability_tiers == (
            SuitabilityTier(f"{task_kind}.{risk}.primary", aliases),
        )
        assert decision.preferred_model_aliases == aliases
        assert decision.to_dict()["preferred_model_aliases"] == list(aliases)
        assert decision.job_constraints()["preferred_model_aliases"] == list(aliases)
        assert decision.job_constraints()["routing_policy_version"] == (
            _V1_ROUTING_POLICY_VERSION
        )


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
