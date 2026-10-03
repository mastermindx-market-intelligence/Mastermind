"""Public current-pin domain creation, replay and refusal controls; no provider work."""
from __future__ import annotations

import json

import pytest

from control_plane.ceo_intent import CeoIntentError, submit_intent
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, DEFAULT_CAPABILITY_POLICY_PATH, ExecutionCapabilityRegistry,
)
from control_plane.executive_runtime import COO_DOMAIN_EXECUTION_PROFILE, Runtime, StateConflict

ROOT_PROFILE = "sealed.worker.write.no-extensions.v1"
OPERATOR_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.v1"


def _v2_intent(intent_id="CEO-R120-CREATION"):
    return {
        "schema": "mastermind.ceo_intent.v2", "intent_id": intent_id,
        "actor": "ceo-sol", "objective": "R120 causal domain creation control.",
        "department": "executive-infrastructure", "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
        "intent_kind": "executive_coo_cycle", "business_impact": "material",
    }


def _binding_for(registry, *, root_profile=COO_DOMAIN_EXECUTION_PROFILE,
                 operator_profile=COO_DOMAIN_EXECUTION_PROFILE, armed=True):
    profile = registry.profiles[root_profile]
    operator = registry.profiles[operator_profile]
    return {
        "eligible_quota_classes": ["codex-coo", "codex-coo-default"],
        "provider": "codex", "model": "gpt-test", "effort": "low",
        "cost_class": "small", "base_sha": "a" * 40,
        "routing_policy_version": "test-routing",
        "execution_profile_id": root_profile,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "operator_eligible_quota_classes": ["codex-coo-operator"],
        "operator_provider": "codex", "operator_model": "gpt-operator-test",
        "operator_effort": "low", "operator_cost_class": "small",
        "operator_routing_policy_version": "test-operator-routing",
        "operator_execution_profile_id": operator_profile,
        "operator_execution_profile_digest": operator.profile_digest,
        "operator_capability_policy_version": registry.policy_version,
        "operator_capability_policy_digest": registry.policy_digest,
        "operator_harness_binary_digest": "a" * 64,
        "operator_harness_version": "0.147.0", "operator_harness_armed": armed,
    }


def _registry(tmp_path, real_loader, *, enabled=True, change=None, name="current"):
    # Call the saved real loader, even after production loading is redirected.
    raw = json.loads(DEFAULT_CAPABILITY_POLICY_PATH.read_bytes())
    raw["profiles"][COO_DOMAIN_EXECUTION_PROFILE]["enabled"] = enabled
    if change is not None:
        change(raw)
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(raw), encoding="utf-8")
    return real_loader(path)


def _use_registry(monkeypatch, registry):
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load",
                        classmethod(lambda cls, *args, **kwargs: registry))


def _root(tmp_path, registry, monkeypatch, *, binding=None):
    _use_registry(monkeypatch, registry)
    runtime = Runtime.at(tmp_path / "runtime")
    receipt = submit_intent(runtime, _v2_intent(), execution_binding=binding)
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    return runtime, root


def _inventory(runtime):
    """All durable rows, including Events, reservations and charge ledgers."""
    with runtime.store.read() as connection:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
        return {name: sorted((tuple(row) for row in connection.execute(
            'SELECT * FROM "' + name.replace('"', '""') + '"'
        )), key=repr) for name in names}


def _create(runtime, root):
    return runtime.jobs.create_cycle_domain(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-domain:0",
    )


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("separate_profiles", [False, True])
@pytest.mark.parametrize("armed", [False, True])
def test_current_public_binding_creates_one_conserved_domain_and_exact_replay(
    tmp_path, monkeypatch, enabled, separate_profiles, armed,
):
    canonical = DEFAULT_CAPABILITY_POLICY_PATH.read_bytes()
    loader = ExecutionCapabilityRegistry.load
    registry = _registry(tmp_path, loader, enabled=enabled)
    binding = _binding_for(
        registry, root_profile=ROOT_PROFILE if separate_profiles else COO_DOMAIN_EXECUTION_PROFILE,
        operator_profile=OPERATOR_PROFILE if separate_profiles else COO_DOMAIN_EXECUTION_PROFILE,
        armed=armed,
    )
    runtime, root = _root(tmp_path, registry, monkeypatch, binding=binding)
    before = _inventory(runtime)
    domain = _create(runtime, root)
    after = _inventory(runtime)
    assert runtime.jobs.get_job(root.job_id) == root
    assert domain.parent_job_id == domain.root_job_id == root.job_id
    assert root.depth == 0 and domain.depth == 1
    assert domain.requested_authorities == ["READ"]
    assert domain.allowed_write_paths == domain.validation_commands == []
    assert domain.attempt_limit <= root.attempt_limit
    assert domain.constraints["remaining_depth"] == 1
    assert domain.constraints["execution_profile_id"] == COO_DOMAIN_EXECUTION_PROFILE
    assert domain.constraints["execution_profile_digest"] == registry.profiles[COO_DOMAIN_EXECUTION_PROFILE].profile_digest
    assert domain.constraints["capability_policy_digest"] == root.constraints["capability_policy_digest"]
    assert domain.constraints["capability_policy_version"] == root.constraints["capability_policy_version"]
    for key in ("provider", "model", "effort", "cost_class", "routing_policy_version", "eligible_quota_classes"):
        assert domain.constraints[key] == root.constraints[("operator_" if armed else "") + key]
    assert domain.constraints["base_sha"] == root.constraints["base_sha"]
    if armed:
        assert domain.constraints["harness_binary_digest"] == root.constraints["operator_harness_binary_digest"]
        assert domain.constraints["harness_version"] == root.constraints["operator_harness_version"]
    assert len(after["jobs"]) == len(before["jobs"]) + 1
    assert len(after["events"]) == len(before["events"]) + 2
    assert {k for k in after if after[k] != before[k]} == {"jobs", "events", "sqlite_sequence"}
    budget = [e for e in runtime.events.list_events(job_id=root.job_id)
              if e.event_type == "COO_PROVIDER_WORK_BUDGET_RESERVED"]
    assert len(budget) == 1
    assert budget[0].payload["root_job_id"] == root.job_id
    assert budget[0].payload["domain_job_id"] == domain.job_id
    assert budget[0].payload["max_provider_work_units_per_root"] == 32
    assert budget[0].payload["reserved_domain_consumption_units"] == 1
    assert budget[0].payload["available_provider_work_units"] == 31
    assert budget[0].payload["spent_provider_work_units"] == 0
    assert budget[0].payload["reservation_status"] == "reservation_only"
    assert _create(runtime, root).job_id == domain.job_id
    assert _inventory(runtime) == after  # no Event, budget or identity reset
    if not enabled:
        with pytest.raises(CapabilityPolicyError, match="is disabled"):
            registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)
    assert DEFAULT_CAPABILITY_POLICY_PATH.read_bytes() == canonical
    assert json.loads(canonical)["production_armed"] is False
    assert json.loads(canonical)["profiles"][COO_DOMAIN_EXECUTION_PROFILE]["enabled"] is False


@pytest.mark.parametrize("created", [False, True])
@pytest.mark.parametrize("change_kind", ["version", "whole-policy", "selected-profile"])
def test_real_policy_changed_after_public_root_refuses_without_any_effect(
    tmp_path, monkeypatch, created, change_kind,
):
    loader = ExecutionCapabilityRegistry.load
    initial = _registry(tmp_path, loader)
    binding = _binding_for(initial, root_profile=ROOT_PROFILE, operator_profile=OPERATOR_PROFILE)
    runtime, root = _root(tmp_path, initial, monkeypatch, binding=binding)
    if created:
        _create(runtime, root)
    before = _inventory(runtime)
    def change(raw):
        if change_kind == "version":
            raw["policy_version"] += ".r120-drift"
        elif change_kind == "whole-policy":
            raw["profiles"]["sealed.worker.readonly.no-extensions.v1"]["enabled"] = False
        else:
            raw["profiles"][ROOT_PROFILE]["enabled"] = False
    changed = _registry(tmp_path, loader, change=change, name="changed")
    assert initial.policy_digest != changed.policy_digest
    if change_kind == "selected-profile":
        assert initial.profiles[ROOT_PROFILE].profile_digest != changed.profiles[ROOT_PROFILE].profile_digest
    _use_registry(monkeypatch, changed)
    for _ in range(2):
        with pytest.raises(StateConflict, match="capability policy pin is no longer current"):
            _create(runtime, root)
        assert _inventory(runtime) == before
        assert runtime.jobs.get_job(root.job_id) == root


@pytest.mark.parametrize("prefix", ["", "operator_"])
@pytest.mark.parametrize("field", ["capability_policy_version", "capability_policy_digest", "execution_profile_id", "execution_profile_digest"])
def test_public_stale_selected_or_policy_pin_refuses_before_child_derivation(
    tmp_path, monkeypatch, prefix, field,
):
    registry = _registry(tmp_path, ExecutionCapabilityRegistry.load)
    binding = _binding_for(registry, root_profile=ROOT_PROFILE, operator_profile=OPERATOR_PROFILE)
    key = prefix + field
    binding[key] = "f" * 64 if field.endswith("digest") else "r120-stale-identity"
    runtime, root = _root(tmp_path, registry, monkeypatch, binding=binding)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="capability policy pin|selected profile"):
        _create(runtime, root)
    assert _inventory(runtime) == before
    assert runtime.jobs.get_job(root.job_id) == root


@pytest.mark.parametrize("missing_key", [
    "operator_eligible_quota_classes", "operator_provider", "operator_model",
    "operator_effort", "operator_cost_class", "operator_routing_policy_version",
    "operator_execution_profile_id", "operator_execution_profile_digest",
    "operator_capability_policy_version", "operator_capability_policy_digest",
    "operator_harness_binary_digest", "operator_harness_version", "base_sha",
])
def test_incomplete_armed_host_binding_refuses_at_public_root_no_fallback(
    tmp_path, monkeypatch, missing_key,
):
    registry = _registry(tmp_path, ExecutionCapabilityRegistry.load)
    _use_registry(monkeypatch, registry)
    binding = _binding_for(registry)
    del binding[missing_key]
    runtime = Runtime.at(tmp_path / "runtime")
    before = _inventory(runtime)
    with pytest.raises(CeoIntentError, match="binding fields are incomplete"):
        submit_intent(runtime, _v2_intent(), execution_binding=binding)
    assert _inventory(runtime) == before


@pytest.mark.parametrize("enabled", [False, True])
def test_unbound_legacy_root_is_only_compatible_with_disarmed_metadata(
    tmp_path, monkeypatch, enabled,
):
    registry = _registry(tmp_path, ExecutionCapabilityRegistry.load, enabled=enabled)
    runtime, root = _root(tmp_path, registry, monkeypatch)
    before = _inventory(runtime)
    assert "execution_profile_id" not in root.constraints
    if enabled:
        with pytest.raises(StateConflict, match="complete immutable capability binding"):
            _create(runtime, root)
        assert _inventory(runtime) == before
    else:
        domain = _create(runtime, root)
        assert domain.depth == 1
        with pytest.raises(CapabilityPolicyError, match="is disabled"):
            registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)
    assert runtime.jobs.get_job(root.job_id) == root


def test_wrong_domain_command_refuses_without_any_durable_effect(tmp_path, monkeypatch):
    registry = _registry(tmp_path, ExecutionCapabilityRegistry.load)
    runtime, root = _root(tmp_path, registry, monkeypatch, binding=_binding_for(registry))
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="not exact-root deterministic"):
        runtime.jobs.create_cycle_domain(root.job_id, command_id="r120-wrong-command")
    assert _inventory(runtime) == before
