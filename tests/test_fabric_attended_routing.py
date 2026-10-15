"""Inert catalogue/plan projection checks; no Worker registration or launch."""
import copy
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane import fabric_attended_routing as attended
from control_plane import worker_adapter
from control_plane.executive_runtime import (
    StateConflict, _normalise_constraints, _normalise_work_placement_union,
    _project_work_placement, _capacity_matches_route,
)
from control_plane.model_router import ModelRouter, RoutingPolicyError

ROOT = Path(__file__).resolve().parents[1]
BINDING = "minimax-token-plan.claude-code-anthropic"


@pytest.fixture
def router(tmp_path, monkeypatch):
    # A future independently qualified composition is simulated only here.
    # The real descriptor and active capability registry remain unarmed.
    descriptor = worker_adapter.ADAPTER_DESCRIPTORS["attended-fabric"]
    monkeypatch.setitem(worker_adapter.ADAPTER_DESCRIPTORS, "attended-fabric",
                        dataclasses.replace(descriptor, implemented=True))
    capabilities = json.loads((ROOT / "config/executive_agent_capabilities.json").read_text())
    proposal = json.loads((ROOT / "integrations/session_bridge/proposals/attended_claude_profile.json").read_text())
    capabilities["profiles"][proposal["profile_id"]] = dict(proposal["profile"], enabled=True)
    capabilities["policy_version"] = "fixture.attended.v1"
    caps = tmp_path / "capabilities.json"
    caps.write_text(json.dumps(capabilities))
    routes = json.loads((ROOT / "config/executive_worker_routes.json").read_text())
    routes["providers"]["minimax"] = dict(adapter_id="attended-fabric", enabled=True, autonomous_allowed=False)
    routes["model_aliases"]["minimax.attended"] = dict(
        provider_alias="minimax", execution_profile_id=proposal["profile_id"],
        model="MiniMax-M3", effort="medium", cost_class="small",
        capabilities=["research"], worker_eligible=False)
    path = tmp_path / "routing.json"
    path.write_text(json.dumps(routes))
    return ModelRouter.load(path, capability_policy_path=caps)


def member(router):
    return attended.placement_member(router, attended.AttendedWorkPlacement(
        "minimax.attended", BINDING, "minimax-read"))


def test_attended_resolution_never_enters_autonomous_alias_resolver(router):
    alias = router.resolve_attended_model_alias("minimax.attended", BINDING)
    assert alias.model == "MiniMax-M3" and not alias.worker_eligible
    with pytest.raises(RoutingPolicyError, match="not worker eligible"):
        router.resolve_model_alias("minimax.attended")
    assert router.resolve_model_alias("coo.sealed").worker_eligible


def test_real_descriptor_and_active_registry_stay_unarmed():
    assert worker_adapter.ADAPTER_DESCRIPTORS["attended-fabric"].implemented is False
    real = ModelRouter.load()
    assert real.capability_registry.resolve(attended.CONTRACT_NAME).write_capable is False
    assert real.providers["minimax"].enabled is False
    with pytest.raises(RoutingPolicyError):
        real.resolve_attended_model_alias("minimax.attended", BINDING)


def test_closed_member_replaces_inherited_codex_identity(router):
    selected = member(router)
    root = {"work_placement_union": [selected]}
    inherited = dict(provider="codex", model="gpt-5.6-sol", effort="xhigh",
                     execution_profile_id="sealed.worker.write.no-extensions.v1",
                     cost_class="small", preferred_model_aliases=["coo.sealed"])
    projected = _project_work_placement(inherited, root,
        {"provider_realm": "minimax", "quota_class": "minimax-read"}, raw_root_constraints=root)
    normalized = _normalise_constraints(projected)
    assert normalized["execution_profile_id"] == attended.CONTRACT_NAME
    assert normalized["preferred_model_aliases"] == ["minimax.attended"]
    assert normalized["attended_route"] == selected["attended_route"]
    assert normalized["model"] == "minimax-m3"
    assert _normalise_work_placement_union([selected]) == [selected]
    assert inherited["provider"] == "codex"


@pytest.mark.parametrize("field", ["model", "execution_profile_digest", "harness_binding_id",
                                   "subscription_catalog_digest", "capability_policy_digest"])
def test_capacity_cannot_match_another_attended_catalogue(router, field):
    selected = member(router)
    root = {"work_placement_union": [selected]}
    constraints = _project_work_placement({}, root,
        {"provider_realm": "minimax", "quota_class": "minimax-read"}, raw_root_constraints=root)
    metadata = {k: v for k, v in constraints.items() if k not in ("provider", "eligible_quota_classes")}
    metadata["model_alias"] = "minimax.attended"
    # Model a full physical quota row, not only untrusted catalogue
    # metadata. The broker must refuse mismatched registered worker identity.
    row = dict(worker_id="fixture-worker", metadata_json=json.dumps(metadata),
               provider="minimax", worker_provider="minimax",
               worker_type="attended-fabric", model="minimax-m3",
               effort="medium", cost_class="small")
    assert _capacity_matches_route(row, constraints)
    metadata["attended_route"] = dict(metadata["attended_route"], **{field: "foreign"})
    row["metadata_json"] = json.dumps(metadata)
    assert not _capacity_matches_route(row, constraints)


@pytest.mark.parametrize("damage", ["omit", "extra", "digest", "profile"])
def test_malformed_host_member_refuses(router, damage):
    selected = member(router)
    route = selected["attended_route"]
    if damage == "omit":
        route.pop("harness_binding_id")
    elif damage == "extra":
        route["attendance_confirmed"] = "true"
    elif damage == "digest":
        route["subscription_catalog_digest"] = "incorrect"
    else:
        route["execution_profile_id"] = "sealed.worker.write.no-extensions.v1"
    with pytest.raises(StateConflict):
        _normalise_work_placement_union([selected])


def test_model_override_cannot_escape_exact_attended_binding(router):
    root = {"work_placement_union": [member(router)]}
    with pytest.raises(StateConflict, match="exact catalogue model"):
        _project_work_placement({}, root,
            dict(provider_realm="minimax", quota_class="minimax-read", model="other"),
            raw_root_constraints=root, plan_schema_version="mastermind.execution_plan/v4")


@pytest.mark.parametrize("mutation", ["autonomy", "implementation", "model", "worker_eligible"])
def test_resolver_refuses_changed_provider_or_alias(router, monkeypatch, mutation):
    if mutation == "autonomy":
        monkeypatch.setitem(router.providers, "minimax", dataclasses.replace(router.providers["minimax"], autonomous_allowed=True))
    elif mutation == "implementation":
        d = worker_adapter.ADAPTER_DESCRIPTORS["attended-fabric"]
        monkeypatch.setitem(worker_adapter.ADAPTER_DESCRIPTORS, "attended-fabric", dataclasses.replace(d, implemented=False))
    else:
        a = router.model_aliases["minimax.attended"]
        change = {mutation: "moving-model" if mutation == "model" else True}
        monkeypatch.setitem(router.model_aliases, "minimax.attended", dataclasses.replace(a, **change))
    with pytest.raises(RoutingPolicyError):
        router.resolve_attended_model_alias("minimax.attended", BINDING)


def test_catalogue_policy_changes_are_not_ignored(router, monkeypatch):
    profiles = copy.deepcopy(attended.load_profiles())
    profiles["profiles"]["minimax-token-plan"]["usage_policy"]["unattended_background_allowed"] = True
    monkeypatch.setattr(attended, "load_profiles", lambda: profiles)
    with pytest.raises(RoutingPolicyError):
        router.resolve_attended_model_alias("minimax.attended", BINDING)


def test_host_composition_keeps_ordinary_planner_and_adds_exact_paid_member(router, tmp_path, monkeypatch):
    from tests.test_executive_service import _config, _service
    monkeypatch.setattr(ModelRouter, "load", classmethod(lambda cls, *a, **kw: router))
    selected = attended.AttendedWorkPlacement("minimax.attended", BINDING, "minimax-read")
    config = _config(tmp_path, coo_attended_work_placements=(selected,))
    service, _ = _service(tmp_path, config=config)
    binding = service._load_coo_execution_binding()
    assert binding["provider"] == "codex"
    assert binding["operator_execution_profile_id"] == "operator.appserver.readonly.docs-mcp.native-helper.v1"
    assert member(router) in binding["work_placement_union"]
    assert len(binding["work_placement_union"]) == 3


def test_host_configuration_refuses_untyped_json_placement(tmp_path):
    from tests.test_executive_service import _config
    with pytest.raises(ValueError, match="bounded host configuration"):
        _config(tmp_path, coo_attended_work_placements=({"model_alias": "minimax.attended"},))


def test_attended_cost_replaces_inherited_cost_and_refuses_later_drift(router):
    root = {"work_placement_union": [member(router)]}
    projected = _project_work_placement({"cost_class": "default"}, root,
        {"provider_realm": "minimax", "quota_class": "minimax-read"}, raw_root_constraints=root)
    assert projected["cost_class"] == "small"
    projected["cost_class"] = "default"
    with pytest.raises(StateConflict, match="cost_class"):
        _normalise_constraints(projected)


@pytest.mark.parametrize("stage", ["member", "projection"])
def test_foreign_provider_cannot_relabel_an_attended_route(router, stage):
    selected = member(router)
    selected["provider_realm"] = "codex"
    with pytest.raises(StateConflict, match="provider"):
        if stage == "member":
            _normalise_work_placement_union([selected])
        else:
            root = {"work_placement_union": [selected]}
            _project_work_placement({}, root, {"provider_realm": "codex", "quota_class": "minimax-read"},
                                    raw_root_constraints=root)


@pytest.fixture
def attended_launch(router, tmp_path):
    """Real local Runtime claim and Supervisor compiler, with no adapter START."""
    from control_plane.executive_runtime import Runtime
    from tests.test_executive_supervisor import _supervisor, FakeAdapter, FakeInspector

    selected = member(router)
    route = selected["attended_route"]
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker("minimax-fixture", provider="minimax",
        account_label="inert-fixture", worker_type="attended-fabric", capabilities=["research"],
        quota_classes={"minimax-read": dict(provider="minimax", model=route["model"],
            effort=route["effort"], cost_class=route["cost_class"], capabilities=["research"],
            metadata=dict(route, attended_route=route))})
    workspace = tmp_path / "workspaces" / "assigned"
    workspace.mkdir(parents=True, mode=0o700)
    root = {"work_placement_union": [selected]}
    constraints = _project_work_placement({}, root,
        {"provider_realm": "minimax", "quota_class": "minimax-read"}, raw_root_constraints=root)
    job = runtime.jobs.create_job("Inspect the assigned source", worktree=str(workspace),
        requested_authorities=["READ"], constraints=constraints)
    supervisor = _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()))
    lease = runtime.attempts.claim_job(job.job_id, lease_owner=supervisor.instance_id)
    assert lease is not None
    job = runtime.jobs.get_job(job.job_id)
    quota = runtime.workers.get_quota_class(lease.attempt.worker_id, lease.attempt.quota_class)
    assert quota.model == job.constraints["model"] == "minimax-m3"
    run_dir = supervisor._run_dir(lease.attempt.attempt_id)
    schema = run_dir / "input" / "result.schema.json"
    schema.parent.mkdir(parents=True, mode=0o700)
    schema.write_text("{}")
    return supervisor, job, lease, schema, quota


def test_exact_catalogue_model_survives_runtime_normalization_into_harness(attended_launch):
    from control_plane.fabric_attended_claude import prepare_attended_claude_launch
    from tests.test_fabric_attended_claude import _binary
    supervisor, job, lease, schema, _quota = attended_launch
    spec = supervisor._launch_spec(job, lease, schema)
    assert spec.model == "MiniMax-M3"
    prepared = prepare_attended_claude_launch(spec=spec, binary=_binary(),
        binding=attended.get_binding(BINDING), profile=attended.get_profile("minimax-token-plan"),
        model_class="routine", max_turns=2, result_schema={"type": "object"})
    assert prepared.environment["ANTHROPIC_MODEL"] == "MiniMax-M3"


@pytest.mark.parametrize("drift", ["model", "catalogue", "provider"])
def test_attended_launch_refuses_claimed_quota_drift(attended_launch, monkeypatch, drift):
    from control_plane.executive_supervisor import SupervisorError
    supervisor, job, lease, schema, quota = attended_launch
    if drift == "catalogue":
        metadata = copy.deepcopy(quota.metadata)
        metadata["attended_route"]["subscription_catalog_digest"] = "f" * 64
        quota = dataclasses.replace(quota, metadata=metadata)
    else:
        quota = dataclasses.replace(quota, **{drift: "foreign"})
    monkeypatch.setattr(supervisor.runtime.workers, "get_quota_class", lambda *args: quota)
    with pytest.raises(SupervisorError, match="attended launch"):
        supervisor._launch_spec(job, lease, schema)
