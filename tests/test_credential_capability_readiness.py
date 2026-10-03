from __future__ import annotations

import dataclasses
import json

import pytest

from control_plane.credential_capability_readiness import (
    CredentialBindingState,
    CredentialReadinessError,
    CredentialReadinessObservation,
    augment_credential_readiness,
)
from control_plane.sol_capability_status import (
    Availability,
    CapabilityFact,
    CapabilityState,
    DependencyFact,
    PrivilegeClass,
    project_sol_capability_status,
)

_OBSERVED_AT = "2026-09-15T06:00:00Z"
_PROVEN_AT = "2026-09-15T05:55:00Z"


def _base(*, dependencies: tuple[DependencyFact, ...] = ()) -> CapabilityFact:
    return CapabilityFact(
        name="openai-tunnel-metadata",
        app_id="mastermind-admin-observe",
        app_generation="g1",
        privilege_class=PrivilegeClass.R0_OBSERVE,
        production_armed=False,
        required_scopes=(),
        required_write_scopes=(),
        current_scopes=(),
        confirmation_required=False,
        prepared_action_required=False,
        canonical_owner="openai-tunnel-owner",
        dependencies=dependencies,
        schema_digest="a" * 64,
        source_state=CapabilityState.BUILT_NOT_PROVEN,
        observed_available=True,
        live_proof_current=True,
        write_capable=False,
        last_proven_at=_PROVEN_AT,
        source_refs=("evidence:base-capability",),
        issues=(),
    )


def _observation(
    *,
    capability_name: str = "openai-tunnel-metadata",
    canonical_owner: str = "openai-tunnel-owner",
    state: CredentialBindingState = CredentialBindingState.READY,
    host: str | None = "studio-01",
    credential_generation: str | None = "credential-g7",
    actuator_generation: str | None = "actuator-g3",
    live_proof_current: bool = True,
    source_ref: str = "receipt:credential-readiness",
) -> CredentialReadinessObservation:
    return CredentialReadinessObservation(
        capability_name=capability_name,
        canonical_owner=canonical_owner,
        state=state,
        expected_host_binding="studio-01",
        observed_host_binding=host,
        expected_credential_generation="credential-g7",
        observed_credential_generation=credential_generation,
        expected_actuator_generation="actuator-g3",
        observed_actuator_generation=actuator_generation,
        source_ref=source_ref,
        live_proof_current=live_proof_current,
    )


def _project(observation: CredentialReadinessObservation, *, base: CapabilityFact | None = None):
    fact = augment_credential_readiness(base or _base(), observation)
    envelope = project_sol_capability_status(
        (fact,),
        observed_at=_OBSERVED_AT,
        capability_generation="credential-r2",
    )
    return envelope.capabilities[0]


def _dependencies(status):
    return {dependency.name: dependency for dependency in status.dependencies}


def test_ready_current_binding_preserves_scf_promotion_to_proven_live():
    status = _project(_observation())

    assert status.availability is Availability.AVAILABLE
    assert status.proof_state is CapabilityState.PROVEN_LIVE
    assert status.read_serviceable is True
    dependencies = _dependencies(status)
    assert set(dependencies) == {
        "credential.actuator-binding",
        "credential.binding",
        "credential.host-binding",
    }
    assert all(
        dependency.state is CapabilityState.PROVEN_LIVE
        and dependency.available is True
        for dependency in dependencies.values()
    )


def test_ready_without_current_binding_proof_degrades_without_false_green():
    status = _project(_observation(live_proof_current=False))

    assert status.availability is Availability.DEGRADED
    assert status.proof_state is CapabilityState.PARTIAL
    assert "DEPENDENCY_BUILT_NOT_PROVEN" in status.issues
    assert "CREDENTIAL_LIVE_PROOF_MISSING" in _dependencies(status)[
        "credential.binding"
    ].issues


def test_wrong_host_refuses_capability_without_leaking_host_values():
    status = _project(_observation(host="admin-mini-01"))

    assert status.availability is Availability.UNAVAILABLE
    assert status.proof_state is CapabilityState.DARK_OR_DISCONNECTED
    dependency = _dependencies(status)["credential.host-binding"]
    assert dependency.available is False
    assert dependency.issues == ("HOST_BINDING_MISMATCH",)
    encoded = json.dumps(status.to_dict(), sort_keys=True)
    assert "studio-01" not in encoded
    assert "admin-mini-01" not in encoded


def test_stale_credential_generation_refuses_without_leaking_generations():
    status = _project(_observation(credential_generation="credential-g6"))

    assert status.availability is Availability.UNAVAILABLE
    dependency = _dependencies(status)["credential.binding"]
    assert dependency.state is CapabilityState.DARK_OR_DISCONNECTED
    assert dependency.issues == ("CREDENTIAL_GENERATION_STALE",)
    encoded = json.dumps(status.to_dict(), sort_keys=True)
    assert "credential-g7" not in encoded
    assert "credential-g6" not in encoded


def test_missing_enrollment_is_not_built():
    status = _project(
        _observation(
            state=CredentialBindingState.NOT_ENROLLED,
            credential_generation=None,
        )
    )
    dependency = _dependencies(status)["credential.binding"]

    assert status.availability is Availability.UNAVAILABLE
    assert dependency.state is CapabilityState.NOT_BUILT
    assert dependency.available is False
    assert dependency.issues == ("CREDENTIAL_NOT_ENROLLED",)


def test_human_mfa_is_explicitly_non_autonomous():
    status = _project(
        _observation(state=CredentialBindingState.REQUIRES_HUMAN_MFA)
    )
    dependency = _dependencies(status)["credential.binding"]

    assert status.availability is Availability.UNAVAILABLE
    assert dependency.state is CapabilityState.PARTIAL
    assert dependency.available is False
    assert dependency.issues == ("CREDENTIAL_REQUIRES_HUMAN_MFA",)


def test_actuator_generation_mismatch_refuses_before_capability_use():
    status = _project(_observation(actuator_generation="actuator-g2"))
    dependency = _dependencies(status)["credential.actuator-binding"]

    assert status.availability is Availability.UNAVAILABLE
    assert dependency.state is CapabilityState.DARK_OR_DISCONNECTED
    assert dependency.issues == ("ACTUATOR_GENERATION_MISMATCH",)


def test_invalid_native_session_is_broken_not_silently_reenrolled():
    status = _project(
        _observation(state=CredentialBindingState.NATIVE_SESSION_INVALID)
    )
    dependency = _dependencies(status)["credential.binding"]

    assert status.availability is Availability.UNAVAILABLE
    assert status.proof_state is CapabilityState.BROKEN
    assert dependency.state is CapabilityState.BROKEN
    assert dependency.issues == ("CREDENTIAL_NATIVE_SESSION_INVALID",)


def test_reserved_dependency_name_cannot_be_overwritten():
    base = _base(
        dependencies=(
            DependencyFact(
                "credential.binding",
                CapabilityState.PROVEN_LIVE,
                True,
                True,
                "evidence:existing",
                (),
            ),
        )
    )
    with pytest.raises(CredentialReadinessError, match="reserved credential dependencies"):
        augment_credential_readiness(base, _observation())


def test_secret_shaped_source_reference_is_refused_before_projection():
    with pytest.raises(CredentialReadinessError, match="secret-shaped"):
        augment_credential_readiness(
            _base(),
            _observation(source_ref="receipt:sk-example"),
        )


def test_readiness_contract_has_no_raw_secret_input_fields():
    fields = {field.name for field in dataclasses.fields(CredentialReadinessObservation)}
    forbidden = {
        "secret",
        "token",
        "password",
        "api_key",
        "key",
        "value",
        "cookie",
        "authorization",
        "custody_ref",
        "keychain_service",
        "executable_path",
        "url",
    }
    assert fields.isdisjoint(forbidden)


@pytest.mark.parametrize(
    "state,issue",
    [
        (CredentialBindingState.EXPIRED, "CREDENTIAL_EXPIRED"),
        (CredentialBindingState.REVOKED, "CREDENTIAL_REVOKED"),
        (CredentialBindingState.REQUIRES_USER_UNLOCK, "CREDENTIAL_REQUIRES_USER_UNLOCK"),
        (CredentialBindingState.BACKEND_UNAVAILABLE, "CREDENTIAL_BACKEND_UNAVAILABLE"),
        (CredentialBindingState.HOST_UNREACHABLE, "CREDENTIAL_HOST_UNREACHABLE"),
    ],
)
def test_other_nonready_states_remain_explicit_and_unavailable(state, issue):
    status = _project(_observation(state=state))
    dependency = _dependencies(status)["credential.binding"]

    assert status.availability is Availability.UNAVAILABLE
    assert dependency.available is False
    assert dependency.issues == (issue,)


def test_existing_owner_dependencies_are_composed_not_replaced():
    existing = DependencyFact(
        "provider-runtime",
        CapabilityState.PROVEN_LIVE,
        True,
        True,
        "evidence:provider-runtime",
        (),
    )
    status = _project(_observation(), base=_base(dependencies=(existing,)))

    dependencies = _dependencies(status)
    assert dependencies["provider-runtime"].state is CapabilityState.PROVEN_LIVE
    assert dependencies["provider-runtime"].available is True
    assert len(dependencies) == 4


def test_secret_shaped_binding_identifier_is_refused_before_projection():
    observation = dataclasses.replace(
        _observation(),
        expected_host_binding="sk-example",
    )
    with pytest.raises(CredentialReadinessError, match="secret-shaped"):
        augment_credential_readiness(_base(), observation)


def test_reserved_dependency_collision_is_normalized_before_composition():
    base = _base(
        dependencies=(
            DependencyFact(
                "Credential.Binding",
                CapabilityState.PROVEN_LIVE,
                True,
                True,
                "evidence:existing-mixed-case",
                (),
            ),
        )
    )
    with pytest.raises(CredentialReadinessError, match="reserved credential dependencies"):
        augment_credential_readiness(base, _observation())


def test_observation_cannot_promote_a_different_semantic_capability():
    with pytest.raises(CredentialReadinessError, match="capability_name"):
        augment_credential_readiness(
            _base(),
            _observation(capability_name="claude-headless-subscription"),
        )


def test_observation_cannot_cross_canonical_owner_boundary():
    with pytest.raises(CredentialReadinessError, match="canonical_owner"):
        augment_credential_readiness(
            _base(),
            _observation(canonical_owner="provider-realm-owner"),
        )


def test_headless_auth_readiness_cannot_promote_interactive_provider_capability():
    interactive = dataclasses.replace(
        _base(),
        name="claude-interactive-subscription",
        canonical_owner="claude-provider-realm-owner",
    )
    headless_auth = _observation(
        capability_name="claude-headless-subscription",
        canonical_owner="claude-provider-realm-owner",
    )

    with pytest.raises(CredentialReadinessError, match="capability_name"):
        augment_credential_readiness(interactive, headless_auth)


def _secret_shape(*parts: str) -> str:
    # Keep regression fixtures semantically realistic without committing literal
    # credential-shaped strings that GitHub push protection must reject.
    return "".join(parts)


@pytest.mark.parametrize(
    "secret_shaped",
    [
        _secret_shape("sk_", "live_", "abcdefghijklmnopqrstuvwxyz"),
        _secret_shape("rk_", "live_", "abcdefghijklmnopqrstuvwxyz"),
        _secret_shape("wh", "sec_", "abcdefghijklmnopqrstuvwxyz"),
        _secret_shape("op", "s_", "abcdefghijklmnopqrstuvwxyz"),
        _secret_shape("ak", "ia", "iosfodnn7example"),
        _secret_shape("as", "ia", "iosfodnn7example"),
        _secret_shape("gl", "pat-", "abcdefghijklmnopqrstuvwxyz"),
        _secret_shape("np", "m_", "abcdefghijklmnopqrstuvwxyz"),
        _secret_shape("ya", "29.", "abcdefghijklmnopqrstuvwxyz"),
    ],
)
def test_common_secret_prefixes_are_refused_in_opaque_identifiers(secret_shaped):
    observation = dataclasses.replace(
        _observation(), expected_credential_generation=secret_shaped
    )
    with pytest.raises(CredentialReadinessError, match="secret-shaped"):
        augment_credential_readiness(_base(), observation)


def test_common_secret_prefix_is_refused_in_source_reference():
    with pytest.raises(CredentialReadinessError, match="secret-shaped"):
        augment_credential_readiness(
            _base(), _observation(source_ref="receipt:" + _secret_shape("op", "s_", "abcdefghijklmnopqrstuvwxyz"))
        )


@pytest.mark.parametrize(
    "ordinary_identifier",
    [
        "ops-team",
        "sketch-runtime",
        "asia-region",
        "npm-mirror",
        "credential-g7",
        "studio-01",
    ],
)
def test_secret_prefix_hardening_preserves_ordinary_identifiers(ordinary_identifier):
    observation = dataclasses.replace(
        _observation(), expected_host_binding=ordinary_identifier,
        observed_host_binding=ordinary_identifier,
    )
    augmented = augment_credential_readiness(_base(), observation)
    assert isinstance(augmented, CapabilityFact)
