from __future__ import annotations

from dataclasses import replace

import pytest

import control_plane.sol_capability_status as capability_status_module
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.sol_capability_status import (
    MAX_CAPABILITIES,
    MAX_DEPENDENCIES,
    MAX_ISSUES,
    MAX_SCOPES,
    MAX_SOURCE_REFS,
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
        "required_write_scopes": (),
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


def _project(*facts: CapabilityFact, observed_at: str = OBSERVED_AT):
    return project_sol_capability_status(
        facts,
        observed_at=observed_at,
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


def test_future_dated_live_proof_cannot_promote_or_arm_write() -> None:
    status = _project(
        _fact(
            name="submit-pr-review",
            privilege_class=PrivilegeClass.W1_ROUTINE,
            production_armed=True,
            write_capable=True,
            required_scopes=("contents:read", "pull_requests:write"),
            required_write_scopes=("pull_requests:write",),
            current_scopes=("contents:read", "pull_requests:write"),
            live_proof_current=True,
            last_proven_at="2026-08-30T20:00:01Z",
        )
    ).capabilities[0]
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN
    assert status.availability is Availability.READ_ONLY
    assert status.read_serviceable is True
    assert status.write_serviceable is False
    assert "LIVE_PROOF_FUTURE" in status.issues
    assert "LIVE_PROOF_MISSING" in status.issues


def test_future_dated_claimed_proven_live_is_downgraded() -> None:
    status = _project(
        _fact(
            source_state=CapabilityState.PROVEN_LIVE,
            live_proof_current=True,
            last_proven_at="2026-08-31T00:00:00Z",
        )
    ).capabilities[0]
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN
    assert status.availability is Availability.AVAILABLE
    assert "LIVE_PROOF_FUTURE" in status.issues


def test_write_capability_with_broad_scope_but_production_disarmed_is_read_only() -> None:
    fact = _fact(
        name="merge-expected-head",
        privilege_class=PrivilegeClass.W2_CONSEQUENTIAL,
        production_armed=False,
        confirmation_required=True,
        prepared_action_required=True,
        required_scopes=("contents:read", "pull_requests:write"),
        required_write_scopes=("pull_requests:write",),
        current_scopes=("contents:read", "pull_requests:write"),
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
        required_write_scopes=("pull_requests:write",),
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


def test_scope_role_is_explicit_and_not_inferred_from_name() -> None:
    status = _project(
        _fact(
            name="repo-write",
            privilege_class=PrivilegeClass.W1_ROUTINE,
            production_armed=True,
            write_capable=True,
            required_scopes=("pull_requests:read", "repo"),
            required_write_scopes=("repo",),
            current_scopes=("pull_requests:read",),
            live_proof_current=True,
            last_proven_at="2026-08-30T19:59:00Z",
        )
    ).capabilities[0]
    assert status.required_read_scopes == ("pull_requests:read",)
    assert status.required_write_scopes == ("repo",)
    assert status.missing_scopes == ("repo",)
    assert status.availability is Availability.READ_ONLY
    assert status.read_serviceable is True
    assert status.write_serviceable is False


def test_write_like_scope_name_is_read_critical_without_explicit_role() -> None:
    status = _project(
        _fact(
            name="opaque-scope-contract",
            privilege_class=PrivilegeClass.W1_ROUTINE,
            production_armed=True,
            write_capable=True,
            required_scopes=("contents:read", "pull_requests:write"),
            required_write_scopes=(),
            current_scopes=("contents:read",),
            live_proof_current=True,
            last_proven_at="2026-08-30T19:59:00Z",
        )
    ).capabilities[0]
    assert status.availability is Availability.UNAVAILABLE
    assert status.read_serviceable is False
    assert status.write_serviceable is False
    assert "READ_SCOPE_MISSING" in status.issues


def test_required_write_scope_contract_fails_closed_on_invalid_shape() -> None:
    with pytest.raises(CapabilityProjectionError, match="subset of required_scopes"):
        _project(_fact(required_write_scopes=("repo",)))
    with pytest.raises(CapabilityProjectionError, match="write_capable=true"):
        _project(
            _fact(
                required_scopes=("contents:read", "repo"),
                required_write_scopes=("repo",),
                write_capable=False,
            )
        )


def test_excess_ambient_scope_is_visible_without_granting_or_removing_serviceability() -> None:
    status = _project(
        _fact(
            current_scopes=(
                "contents:read",
                "organization:admin",
                "pull_requests:read",
            )
        )
    ).capabilities[0]
    assert status.excess_scopes == ("organization:admin",)
    assert "EXCESS_SCOPE_PRESENT" in status.issues
    assert status.availability is Availability.AVAILABLE
    assert status.read_serviceable is True
    assert status.write_serviceable is False
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN


def test_excess_scope_changes_canonical_digest() -> None:
    baseline = _project(_fact())
    widened = _project(
        _fact(current_scopes=("contents:read", "pull_requests:read", "repo:admin"))
    )
    assert baseline.canonical_digest != widened.canonical_digest


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


def test_required_rejected_dependency_preserves_constitutional_refusal() -> None:
    dependency = DependencyFact(
        name="generic-shell",
        state=CapabilityState.REJECTED_BY_DESIGN,
        required=True,
        available=True,
        source_ref="policy:generic-shell",
    )
    status = _project(
        _fact(
            dependencies=(dependency,),
            source_state=CapabilityState.NOT_BUILT,
        )
    ).capabilities[0]
    assert status.availability is Availability.REFUSED
    assert status.proof_state is CapabilityState.REJECTED_BY_DESIGN
    assert status.read_serviceable is False
    assert status.write_serviceable is False
    assert "DEPENDENCY_REJECTED_BY_DESIGN" in status.issues


def test_optional_rejected_dependency_remains_visible_but_does_not_refuse_parent() -> None:
    dependency = DependencyFact(
        name="optional-generic-shell",
        state=CapabilityState.REJECTED_BY_DESIGN,
        required=False,
        available=False,
        source_ref="policy:optional-generic-shell",
    )
    status = _project(_fact(dependencies=(dependency,))).capabilities[0]
    assert status.availability is Availability.AVAILABLE
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN
    assert status.read_serviceable is True
    assert status.dependencies[0].state is CapabilityState.REJECTED_BY_DESIGN


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


@pytest.mark.parametrize(
    "privilege_class",
    (PrivilegeClass.W2_CONSEQUENTIAL, PrivilegeClass.A3_ADMIN),
)
def test_consequential_write_requires_prepared_action(
    privilege_class: PrivilegeClass,
) -> None:
    with pytest.raises(CapabilityProjectionError, match="prepared_action_required"):
        _project(
            _fact(
                name=f"{privilege_class.value.lower()}-write",
                privilege_class=privilege_class,
                write_capable=True,
                production_armed=False,
                required_scopes=("contents:read", "repo"),
                required_write_scopes=("repo",),
                current_scopes=("contents:read", "repo"),
                prepared_action_required=False,
                confirmation_required=(
                    privilege_class is PrivilegeClass.A3_ADMIN
                ),
            )
        )


def test_admin_write_requires_confirmation() -> None:
    with pytest.raises(CapabilityProjectionError, match="confirmation_required"):
        _project(
            _fact(
                name="admin-write",
                privilege_class=PrivilegeClass.A3_ADMIN,
                write_capable=True,
                production_armed=False,
                required_scopes=("contents:read", "org:admin"),
                required_write_scopes=("org:admin",),
                current_scopes=("contents:read", "org:admin"),
                prepared_action_required=True,
                confirmation_required=False,
            )
        )


def test_nonwrite_family_cannot_be_production_armed() -> None:
    with pytest.raises(
        CapabilityProjectionError,
        match="production_armed requires write_capable=true",
    ):
        _project(
            _fact(
                privilege_class=PrivilegeClass.W1_ROUTINE,
                production_armed=True,
                write_capable=False,
            )
        )


@pytest.mark.parametrize(
    "source_state",
    (
        CapabilityState.NOT_BUILT,
        CapabilityState.SPEC_ONLY,
        CapabilityState.REJECTED_BY_DESIGN,
    ),
)
def test_nonexistent_spec_or_refused_source_cannot_be_production_armed(
    source_state: CapabilityState,
) -> None:
    with pytest.raises(CapabilityProjectionError, match="cannot be production_armed"):
        _project(
            _fact(
                name=f"armed-{source_state.value.lower()}",
                privilege_class=PrivilegeClass.W1_ROUTINE,
                source_state=source_state,
                write_capable=True,
                production_armed=True,
                required_scopes=("contents:read", "repo"),
                required_write_scopes=("repo",),
                current_scopes=("contents:read", "repo"),
            )
        )


@pytest.mark.parametrize(
    ("privilege_class", "confirmation_required"),
    (
        (PrivilegeClass.W2_CONSEQUENTIAL, False),
        (PrivilegeClass.A3_ADMIN, True),
    ),
)
def test_disarmed_spec_only_write_family_is_representable(
    privilege_class: PrivilegeClass,
    confirmation_required: bool,
) -> None:
    status = _project(
        _fact(
            name=f"future-{privilege_class.value.lower()}",
            privilege_class=privilege_class,
            source_state=CapabilityState.SPEC_ONLY,
            observed_available=False,
            write_capable=True,
            production_armed=False,
            required_scopes=("contents:read", "repo"),
            required_write_scopes=("repo",),
            current_scopes=(),
            prepared_action_required=True,
            confirmation_required=confirmation_required,
        )
    ).capabilities[0]
    assert status.availability is Availability.UNAVAILABLE
    assert status.write_serviceable is False
    assert status.proof_state is CapabilityState.SPEC_ONLY


@pytest.mark.parametrize(
    ("privilege_class", "prepared_action_required", "confirmation_required"),
    (
        (PrivilegeClass.W2_CONSEQUENTIAL, False, False),
        (PrivilegeClass.A3_ADMIN, True, False),
    ),
)
def test_private_projection_seam_requires_privilege_guards_for_write_serviceability(
    privilege_class: PrivilegeClass,
    prepared_action_required: bool,
    confirmation_required: bool,
) -> None:
    raw_fact = _fact(
        name=f"raw-{privilege_class.value.lower()}",
        privilege_class=privilege_class,
        source_state=CapabilityState.BUILT_NOT_PROVEN,
        write_capable=True,
        production_armed=True,
        required_scopes=("contents:read", "repo"),
        required_write_scopes=("repo",),
        current_scopes=("contents:read", "repo"),
        prepared_action_required=prepared_action_required,
        confirmation_required=confirmation_required,
        live_proof_current=True,
        last_proven_at="2026-08-30T19:59:00Z",
    )
    status = capability_status_module._project(
        raw_fact,
        capability_status_module._instant(OBSERVED_AT, "observed_at"),
    )
    assert status.write_serviceable is False


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
            required_write_scopes=("workspace:write",),
            current_scopes=("workspace:read", "workspace:write"),
            prepared_action_required=True,
            write_capable=profile.write_capable,
            live_proof_current=False,
            source_refs=(f"capability-policy:{registry.policy_digest}",),
        )
    ).capabilities[0]

    assert status.availability is Availability.READ_ONLY
    assert status.write_serviceable is False
    assert status.proof_state is CapabilityState.BUILT_NOT_PROVEN


@pytest.mark.parametrize(
    "overrides",
    (
        {"write_capable": True},
        {"production_armed": True},
        {"confirmation_required": True},
        {"prepared_action_required": True},
        {
            "required_scopes": ("contents:read", "repo"),
            "required_write_scopes": ("repo",),
            "write_capable": True,
        },
    ),
)
def test_r0_observe_rejects_every_effect_bearing_fact(overrides: dict[str, object]) -> None:
    with pytest.raises(CapabilityProjectionError, match="R0_OBSERVE must be zero-effect"):
        _project(_fact(**overrides))


def test_capability_iterable_stops_at_closed_ceiling() -> None:
    def facts():
        for index in range(MAX_CAPABILITIES + 1):
            yield _fact(
                name=f"capability-{index:03d}",
                source_refs=(f"source:{index}",),
            )

    with pytest.raises(CapabilityProjectionError, match="at most"):
        project_sol_capability_status(
            facts(),
            observed_at=OBSERVED_AT,
            capability_generation="scf-cap1.v1",
        )


def test_scope_collections_have_closed_ceiling() -> None:
    scopes = tuple(f"scope:{index}" for index in range(MAX_SCOPES + 1))
    with pytest.raises(CapabilityProjectionError, match="at most"):
        _project(
            _fact(
                required_scopes=scopes,
                current_scopes=scopes,
            )
        )


def test_dependency_collection_has_closed_ceiling() -> None:
    dependencies = tuple(
        DependencyFact(
            name=f"dependency-{index:03d}",
            state=CapabilityState.PROVEN_LIVE,
            required=True,
            available=True,
            source_ref=f"dependency:{index}",
        )
        for index in range(MAX_DEPENDENCIES + 1)
    )
    with pytest.raises(CapabilityProjectionError, match="at most"):
        _project(_fact(dependencies=dependencies))


def test_source_and_issue_collections_have_closed_ceilings() -> None:
    with pytest.raises(CapabilityProjectionError, match="at most"):
        _project(
            _fact(
                source_refs=tuple(
                    f"source:{index}" for index in range(MAX_SOURCE_REFS + 1)
                )
            )
        )
    with pytest.raises(CapabilityProjectionError, match="at most"):
        _project(
            _fact(
                issues=tuple(
                    f"ISSUE_{index:03d}" for index in range(MAX_ISSUES + 1)
                )
            )
        )


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
        "required_read_scopes",
        "required_write_scopes",
        "current_scopes",
        "missing_scopes",
        "excess_scopes",
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


def test_required_spec_only_dependency_is_never_serviceable_even_if_available() -> None:
    dependency = DependencyFact(
        name="future-runtime-owner",
        state=CapabilityState.SPEC_ONLY,
        required=True,
        available=True,
        source_ref="runtime:future-owner",
    )
    status = _project(
        _fact(
            dependencies=(dependency,),
            live_proof_current=True,
            last_proven_at="2026-08-30T19:59:00Z",
        )
    ).capabilities[0]
    assert status.availability is Availability.UNAVAILABLE
    assert status.proof_state is CapabilityState.SPEC_ONLY
    assert status.read_serviceable is False
    assert status.write_serviceable is False
    assert "DEPENDENCY_SPEC_ONLY" in status.issues
    assert status.dependencies[0].state is CapabilityState.SPEC_ONLY


@pytest.mark.parametrize(
    "dependency_state",
    (CapabilityState.NOT_BUILT, CapabilityState.DARK_OR_DISCONNECTED),
)
def test_definitive_disconnected_dependency_precedes_unknown_availability(
    dependency_state: CapabilityState,
) -> None:
    dependency = DependencyFact(
        name=f"missing-{dependency_state.value.lower()}",
        state=dependency_state,
        required=True,
        available=None,
        source_ref="runtime:missing-owner",
    )
    status = _project(_fact(dependencies=(dependency,))).capabilities[0]
    assert status.availability is Availability.UNAVAILABLE
    assert status.proof_state is CapabilityState.DARK_OR_DISCONNECTED
    assert status.read_serviceable is False
    assert status.write_serviceable is False
    assert f"DEPENDENCY_{dependency_state.value}" in status.issues


@pytest.mark.parametrize(
    "timestamp",
    (
        "2026-08-30 20:00:00Z",
        "20260830T200000Z",
        "2026-W35-7T20:00:00Z",
        "2026-08-30T20:00:00+0000",
        "2026-08-30T20:00:00,123Z",
        "2026-08-30T20:00:00+00:00:30",
        "2026-08-30t20:00:00+00:00",
    ),
)
def test_non_rfc3339_timestamp_forms_are_rejected(timestamp: str) -> None:
    with pytest.raises(
        CapabilityProjectionError,
        match="observed_at must be an RFC3339 timestamp",
    ):
        _project(_fact(), observed_at=timestamp)


def test_timestamp_length_is_bounded_before_permissive_parsing() -> None:
    over_bound = "2026-08-30T20:00:00." + ("1" * 100) + "Z"
    with pytest.raises(
        CapabilityProjectionError,
        match="observed_at must be an RFC3339 timestamp",
    ):
        _project(_fact(), observed_at=over_bound)


def test_malformed_timestamp_is_not_echoed_anywhere_in_exception_chain() -> None:
    opaque = "not-rfc3339-opaque-value"
    with pytest.raises(CapabilityProjectionError) as raised:
        _project(_fact(), observed_at=opaque)
    chain: list[str] = []
    current: BaseException | None = raised.value
    while current is not None:
        chain.append(str(current))
        current = current.__cause__ or current.__context__
    assert opaque not in "\n".join(chain)


def test_equivalent_timestamp_offsets_have_one_output_and_digest_identity() -> None:
    utc = _project(
        _fact(
            live_proof_current=True,
            last_proven_at="2026-08-30T19:59:00Z",
        ),
        observed_at="2026-08-30T20:00:00Z",
    )
    offset = _project(
        _fact(
            live_proof_current=True,
            last_proven_at="2026-08-30T15:59:00-04:00",
        ),
        observed_at="2026-08-30T16:00:00-04:00",
    )
    assert utc.observed_at == offset.observed_at == "2026-08-30T20:00:00Z"
    assert utc.capabilities[0].last_proven_at == "2026-08-30T19:59:00Z"
    assert offset.capabilities[0].last_proven_at == "2026-08-30T19:59:00Z"
    assert utc.to_dict() == offset.to_dict()
    assert utc.canonical_digest == offset.canonical_digest


def test_timestamp_length_bound_precedes_grammar_evaluation(monkeypatch) -> None:
    class GrammarTrap:
        def fullmatch(self, value: str) -> None:
            raise AssertionError("timestamp grammar was consulted")

    monkeypatch.setattr(capability_status_module, "_RFC3339", GrammarTrap())
    over_bound = "0" * (capability_status_module.MAX_TIMESTAMP_LENGTH + 1)
    with pytest.raises(
        CapabilityProjectionError,
        match="observed_at must be an RFC3339 timestamp",
    ):
        _project(_fact(), observed_at=over_bound)


def test_semantically_invalid_timestamp_has_no_hidden_exception_context() -> None:
    invalid = "2026-02-29T20:00:00Z"
    with pytest.raises(CapabilityProjectionError) as raised:
        _project(_fact(), observed_at=invalid)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert invalid not in str(raised.value)
