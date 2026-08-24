"""Closed-wire proofs for the Executive-to-worker Operator Harness bridge."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.operator_harness_contract import (
    AuthRealmFact,
    CapabilityManifest,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    WorkspaceIdentity,
)
from control_plane.operator_harness_wire import (
    OperatorHarnessWireError,
    observed_harness_attestation,
    reconcile_observation,
    requested_execution_profile,
    to_wire,
)


def _profile() -> RequestedExecutionProfile:
    return RequestedExecutionProfile(
        worker_id="codex-01",
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="0.147.0",
        workspace=WorkspaceIdentity(
            "/private/workspaces/job-1", "b" * 40, 1, 2, 451, 451
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash="c" * 64,
    )


def _attestation(profile: RequestedExecutionProfile) -> ObservedHarnessAttestation:
    return ObservedHarnessAttestation(
        served_model=profile.requested_model,
        harness_version=profile.harness_version,
        harness_binary_digest=profile.harness_binary_digest,
        capabilities=(),
        effective_skills=(),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state="read-only",
        approval_state="never",
        network_state="disabled",
        effective_config_digest="d" * 64,
        auth=AuthRealmFact(worker_id="codex-01", provider="openai-codex"),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.FALSE,
    )


def test_profile_and_attestation_round_trip_without_shape_loss() -> None:
    profile = _profile()
    attestation = _attestation(profile)

    assert requested_execution_profile(to_wire(profile)) == profile
    assert observed_harness_attestation(to_wire(attestation)) == attestation
    assert to_wire(requested_execution_profile(to_wire(profile))) == to_wire(profile)


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_profile_wire_refuses_missing_and_unknown_fields(mutation: str) -> None:
    value = to_wire(_profile())
    if mutation == "missing":
        value.pop("worker_id")
    else:
        value["authority_override"] = "write"

    with pytest.raises(OperatorHarnessWireError, match="fields drifted"):
        requested_execution_profile(value)


def test_nested_enum_and_array_shapes_fail_closed() -> None:
    profile = to_wire(_profile())
    profile["native_helper_policy"] = "UNREVIEWED"
    with pytest.raises(OperatorHarnessWireError, match="native helper policy"):
        requested_execution_profile(profile)

    attestation = to_wire(_attestation(_profile()))
    attestation["effective_mcp"] = {"server": "forged"}
    with pytest.raises(OperatorHarnessWireError, match="array"):
        observed_harness_attestation(attestation)


def test_reconcile_observation_preserves_exact_process_and_writer_facts() -> None:
    observation = ReconcileObservation(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        observed_process=ProcessIdentityObservation(701, 701, "start-701", "boot"),
        provider_session_reachable=False,
        provider_writer_state=ProviderWriterState.RELEASED,
        observed_provider_session_id="thread-1",
        observed_config_digest="e" * 64,
    )
    assert reconcile_observation(to_wire(observation)) == observation

    malformed = dataclasses.asdict(observation)
    malformed["process_liveness"] = "MAYBE"
    malformed["provider_writer_state"] = observation.provider_writer_state.value
    with pytest.raises(OperatorHarnessWireError, match="process liveness"):
        reconcile_observation(malformed)


def test_wire_serializer_rejects_non_json_capability_objects() -> None:
    with pytest.raises(OperatorHarnessWireError, match="unsupported"):
        to_wire(object())
