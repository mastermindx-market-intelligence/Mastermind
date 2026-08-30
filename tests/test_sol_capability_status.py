from __future__ import annotations

from dataclasses import replace

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.sol_capability_status import (
    Availability,
    CapabilityFact,
    CapabilityProjectionError,
    CapabilityState,
    DependencyFact,
    PrivilegeClass,
    project_sol_capability_status,
)


OBSERVED_AT = "2026-08-30T20:00:00Z"
DIGEST = "a" * 64


def _fact(**overrides) -> CapabilityFact:
    values = {
        "name": "github-release-assessment",
        "app_id": "mastermind-github",
        "app_generation": "v1",
        "privilege_class": PrivilegeClass.R0_OBSERVE,
        "production_armed": False,
        "required_scopes": ("contents:read", "pull_requests:read"),
        "current_scopes": ("contents:read", "pull_requests:read"),
        "confirmation_required": False,
        "prepared_action_required": False,
        "canonical_owner": "github",
        "dependencies": (),
        "schema_digest": DIGEST,
        "source_state": CapabilityState.BUILT_NOT_PROVEN,
        "observed_available": True,
        "live_proof_current": False,
        "write_capable": False,
        "last_proven_at": None,
        "source_refs": ("github:repo:mastermind",),
        "issues": (),
    }
    values.update(overrides)
    return CapabilityFact(**values)


def _project(*facts: CapabilityFact):
    return project_sol_capability_status(
        facts,
        observed_at=OBSERVED_AT,
        capability_generation="scf-cap1.v1",
    )


def test_built_source_without_live_proof_stays_built_not_proven() -> None:
    result = _project(_fact())
    status = result.capabilities[0]
    assert result.schema == "mastermind.sol_capability_status.v1"
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN
    assert status.availability is Availability.AVAILABLE
    assert status.read_serviceable is True
    assert status.write_serviceable is False
    assert "LIVE_PROOF_MISSING" in status.issues


def test_current_live_read_capability_can_be_proven_without_write_arming() -> None:
    result = _project(
        _fact(
            source_state=CapabilityState.BUILT_NOT_PROVEN,
            live_proof_current=True,
            last_proven_at="2026-08-30T19:59:00Z",
        )
    )
    status = result.capabilities[0]
    assert status.proof_state is CapabilityState.PROVEN_LIVE
    assert status.availability is Availability.AVAILABLE
    assert status.read_serviceable is True
    assert status.write_serviceable is False


def test_write_capability_with_broad_scope_but_production_disarmed_is_read_only() -> None:
    fact = _fact(
        name="merge-expected-head",
        privilege_class=PrivilegeClass.W2_CONSEQUENTIAL,
        production_armed=False,
        confirmation_required=True,
        prepared_action_required=True,
        live_proof_current=True,
        last_proven_at="2026-08-30T19:59:00Z",
        write_capable=True,
    )
    status = _project(fact).capabilities[0]
    assert status.availability is Availability.READ_ONLY
    assert status.read_serviceable is True
    assert status.write_serviceable is False
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN
    assert "PRODUCTION_DISARMED" in status.issues


def test_missing_required_scope_keeps_write_unavailable_and_explicit() -> None:
    fact = _fact(
        name="submit-pr-review",
        privilege_class=PrivilegeClass.W1_ROUTINE,
        production_armed=True,
        write_capable=True,
        required_scopes=("contents:read", "pull_requests:write"),
        current_scopes=("contents:read",),
        live_proof_current=True,
        last_proven_at="2026-08-30T19:59:00Z",
    )
    status = _project(fact).capabilities[0]
    assert status.availability is Availability.READ_ONLY
    assert status.missing_scopes == ("pull_requests:write",)
    assert status.write_serviceable is False
    assert status.proof_state is CapabilityState.PARTIAL
    assert "REQUIRED_SCOPE_MISSING" in status.issues


def test_missing_required_dependency_is_dark_or_disconnected() -> None:
    dependency = DependencyFact(
        name="github-native-connector",
        state=CapabilityState.NOT_BUILT,
        required=True,
        available=False,
        source_ref="github:connector:current",
    )
    status = _project(_fact(dependencies=(dependency,))).capabilities[0]
    assert status.availability is Availability.UNAVAILABLE
    assert status.proof_state is CapabilityState.DARK_OR_DISCONNECTED
    assert "DEPENDENCY_NOT_BUILT" in status.issues
    assert status.dependencies[0].state is CapabilityState.NOT_BUILT


def test_degraded_required_dependency_keeps_partial_state_visible() -> None:
    dependency = DependencyFact(
        name="steward-current-source",
        state=CapabilityState.PARTIAL,
        required=True,
        available=True,
        source_ref="steward:capability:current",
        issues=("SOURCE_PARTIAL",),
    )
    status = _project(
        _fact(
            dependencies=(dependency,),
            live_proof_current=True,
            last_proven_at="2026-08-30T19:59:00Z",
        )
    ).capabilities[0]
    assert status.availability is Availability.DEGRADED
    assert status.proof_state is CapabilityState.PARTIAL
    assert "DEPENDENCY_PARTIAL" in status.issues
    assert "SOURCE_PARTIAL" in status.dependencies[0].issues


def test_unobserved_availability_is_unknown_not_false_green() -> None:
    status = _project(_fact(observed_available=None)).capabilities[0]
    assert status.availability is Availability.UNKNOWN
    assert status.read_serviceable is False
    assert status.write_serviceable is False
    assert "AVAILABILITY_UNKNOWN" in status.issues


def test_rejected_by_design_capability_is_refused() -> None:
    status = _project(
        _fact(
            name="generic-shell",
            source_state=CapabilityState.REJECTED_BY_DESIGN,
            observed_available=True,
            live_proof_current=True,
        )
    ).capabilities[0]
    assert status.availability is Availability.REFUSED
    assert status.proof_state is CapabilityState.REJECTED_BY_DESIGN
    assert status.read_serviceable is False
    assert status.write_serviceable is False


def test_duplicate_capability_name_or_generation_conflicts_fail_closed() -> None:
    first = _fact()
    with pytest.raises(CapabilityProjectionError, match="duplicate capability name"):
        _project(first, replace(first, app_generation="v2"))


def test_duplicate_dependency_name_conflicts_fail_closed() -> None:
    dependency = DependencyFact(
        name="github",
        state=CapabilityState.PROVEN_LIVE,
        required=True,
        available=True,
        source_ref="github:one",
    )
    with pytest.raises(CapabilityProjectionError, match="duplicate dependency"):
        _project(_fact(dependencies=(dependency, replace(dependency, source_ref="github:two"))))


def test_projection_is_permutation_stable_and_sorted() -> None:
    first = _fact(name="zeta-capability", source_refs=("github:zeta",))
    second = _fact(name="alpha-capability", source_refs=("github:alpha",))
    left = _project(first, second)
    right = _project(second, first)
    assert [row.name for row in left.capabilities] == ["alpha-capability", "zeta-capability"]
    assert left.canonical_digest == right.canonical_digest
    assert left.to_dict() == right.to_dict()


def test_secret_shaped_source_or_issue_is_rejected_before_projection() -> None:
    with pytest.raises(CapabilityProjectionError, match="secret-shaped"):
        _project(_fact(source_refs=("github_pat_deadbeef",)))
    with pytest.raises(CapabilityProjectionError, match="secret-shaped"):
        _project(_fact(issues=("authorization=Bearer abc",)))


def test_current_execution_registry_remains_source_owner_and_unarmed() -> None:
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.resolve("sealed.worker.write.no-extensions.v1")
    assert registry.production_armed is False
    assert profile.write_capable is True

    status = _project(
        _fact(
            name=profile.profile_id,
            app_id="executive-capability-registry",
            app_generation=registry.policy_version,
            canonical_owner="executive-os",
            privilege_class=PrivilegeClass.W2_CONSEQUENTIAL,
            production_armed=registry.production_armed,
            required_scopes=("workspace:read", "workspace:write"),
            current_scopes=("workspace:read", "workspace:write"),
            write_capable=profile.write_capable,
            live_proof_current=False,
            source_refs=(f"capability-policy:{registry.policy_digest}",),
        )
    ).capabilities[0]

    assert status.availability is Availability.READ_ONLY
    assert status.write_serviceable is False
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN


def test_output_is_secret_free_and_carries_required_contract_fields() -> None:
    result = _project(_fact())
    payload = result.to_dict()
    row = payload["capabilities"][0]
    assert payload["schema"] == "mastermind.sol_capability_status.v1"
    for field in (
        "name",
        "app_id",
        "app_generation",
        "privilege_class",
        "availability",
        "production_armed",
        "required_scopes",
        "current_scopes",
        "missing_scopes",
        "confirmation_required",
        "prepared_action_required",
        "canonical_owner",
        "dependencies",
        "schema_digest",
        "proof_state",
        "issues",
    ):
        assert field in row
    rendered = repr(payload).lower()
    assert "github_pat_" not in rendered
    assert "bearer " not in rendered
    assert "-----begin" not in rendered
