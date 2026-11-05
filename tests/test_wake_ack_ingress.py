"""Contract tests for the provider-neutral exact-session Wake ACK ingress."""
from __future__ import annotations

import dataclasses
from dataclasses import fields
import os
import threading

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.executive_runtime import Runtime
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CapabilityManifest,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessIdentityObservation,
    RequestedExecutionProfile,
    WorkspaceIdentity,
)
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import (
    SCHEMA as TARGET_SCHEMA,
    RuntimeBinding,
    SessionTarget,
    SessionTargetRegistry,
    route_obligation,
)
from control_plane.wake_ack_ingress import (
    TrustedWorkerWakeAckProjection,
    WakeAckClaim,
    WakeAckIngressError,
    acknowledge_consumed_wakes,
)
from control_plane.wake_dispatcher import mint_nudge_id
from control_plane.wake_events import mint_obligation, mint_obligation_id
from control_plane.wake_ledger import (
    LedgerPhase,
    ack_event_payload,
    attempt_record,
    make_delivery_attempt,
    requested_record,
)
from control_plane.wake_persist import WakeLedgerRepository


_OID_A = mint_obligation_id(
    source_kind="executive_inbox_attention",
    source_ref="eia-000000000001",
    wake_kind="job_failed",
)
_OID_B = mint_obligation_id(
    source_kind="executive_inbox_attention",
    source_ref="eia-000000000002",
    wake_kind="job_failed",
)


def test_wake_ack_claim_exposes_only_canonical_opaque_obligation_ids() -> None:
    """Catches adding target, binding, provider, nudge, or authority to the claim."""

    assert [field.name for field in fields(WakeAckClaim)] == ["obligation_ids"]
    claim = WakeAckClaim(obligation_ids=tuple(sorted((_OID_B, _OID_A))))
    assert claim.obligation_ids == tuple(sorted((_OID_A, _OID_B)))


@pytest.mark.parametrize(
    "obligation_ids",
    [
        (),
        (_OID_A, _OID_A),
        (_OID_B, _OID_A),
        (f"{_OID_A}:A1",),
        (f"{_OID_A}:A1:DELIVERED",),
        ("WAKE-not-canonical",),
    ],
)
def test_wake_ack_claim_refuses_empty_duplicate_unsorted_or_command_identities(
    obligation_ids,
) -> None:
    """Catches silent deduplication or accepting an attempt/event command as a claim."""

    with pytest.raises(WakeAckIngressError):
        WakeAckClaim(obligation_ids=obligation_ids)


def _trusted_projection(**overrides) -> TrustedWorkerWakeAckProjection:
    values = {
        "target_attempt_id": "ATT-" + "1" * 32,
        "process_generation_id": "GEN-00000000000000000000000000000001",
        "binding_id": "bind-ack12345",
        "binding_generation": 3,
        "provider_session_id": "PROVIDER-SESSION-1",
        "provider_native_turn_id": "TURN-1",
        "nudge_id": "NUDGE-" + "2" * 32,
        "obligation_ids": (_OID_A,),
        "terminal_ack_trailer": True,
    }
    values.update(overrides)
    return TrustedWorkerWakeAckProjection(**values)


def test_trusted_worker_projection_is_closed_and_validates_exact_identities() -> None:
    """Catches raw model bytes or an incomplete current-writer projection crossing ACK1."""

    assert [field.name for field in fields(TrustedWorkerWakeAckProjection)] == [
        "target_attempt_id",
        "process_generation_id",
        "binding_id",
        "binding_generation",
        "provider_session_id",
        "provider_native_turn_id",
        "nudge_id",
        "obligation_ids",
        "terminal_ack_trailer",
    ]
    projection = _trusted_projection()
    assert dataclasses.asdict(projection)["obligation_ids"] == (_OID_A,)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("target_attempt_id", "ATT-not-canonical"),
        ("process_generation_id", ""),
        ("binding_id", "binding-from-model"),
        ("binding_generation", True),
        ("binding_generation", 0),
        ("provider_session_id", " provider "),
        ("provider_native_turn_id", ""),
        ("nudge_id", "NUDGE-not-canonical"),
        ("obligation_ids", (_OID_A, _OID_A)),
        ("terminal_ack_trailer", False),
    ],
)
def test_trusted_worker_projection_refuses_unsealed_or_malformed_evidence(
    field_name,
    value,
) -> None:
    """Catches trusting a partial, stale-shaped, or nonterminal worker projection."""

    with pytest.raises(WakeAckIngressError):
        _trusted_projection(**{field_name: value})


def _intent() -> dict[str, object]:
    return {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-WAKE-ACK-INGRESS-001",
        "actor": "ceo-sol",
        "objective": "Exercise the inert exact-session Wake ACK ingress.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }


def _profile(dispatch) -> RequestedExecutionProfile:
    attempt = dispatch.attempt
    return RequestedExecutionProfile(
        worker_id=str(attempt.worker_id),
        provider="openai-codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity(
            "/tmp/wake-ack-ingress", "b" * 40, 1, 2, os.getuid(), os.getgid()
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=str(attempt.authority_policy_hash),
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
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
        sandbox_state=profile.sandbox_policy,
        approval_state=profile.approval_policy,
        network_state=profile.network_policy,
        effective_config_digest=None,
        auth=AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )


def _admitted_runtime(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-a",
        provider="openai-codex",
        account_label="account-a",
        worker_type="fixture",
        capabilities=["read"],
        quota_classes={
            "default": {
                "provider": "openai-codex",
                "capabilities": ["read"],
                "cost_class": "small",
            }
        },
    )
    receipt = submit_intent(runtime, _intent())
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert dispatch is not None and dispatch.lease_token is not None
    profile = _profile(dispatch)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    operation = OperationId("ohf-op:wake-ack-ingress-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=operation,
    )
    process = ProcessIdentityObservation(3001, 3001, "start-3001", "boot-fixture")
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="PROVIDER-SESSION-1",
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id="worker-a",
        process_generation_id=generation.process_generation_id,
        provider_session_id="PROVIDER-SESSION-1",
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name="fixture-principal",
        os_principal_uid=os.getuid(),
        provider_home_identity={
            "path": "/tmp/wake-ack-ingress-home",
            "device": 1,
            "inode": 2,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_attestation(profile),
        principal_observation=principal,
    )
    return runtime, sealed, generation


@dataclasses.dataclass(frozen=True)
class _IngressFixture:
    runtime: Runtime
    repo: WakeLedgerRepository
    registry: SessionTargetRegistry
    binding: RuntimeBinding
    target_attempt_id: str
    process_generation_id: str
    obligations: tuple[object, ...]
    nudge_id: str
    trusted: TrustedWorkerWakeAckProjection


def _ingress_fixture(
    tmp_path,
    *,
    obligation_count: int = 1,
    delivered_indices: set[int] | None = None,
    delivery_binding: RuntimeBinding | None = None,
) -> _IngressFixture:
    runtime, sealed, generation = _admitted_runtime(tmp_path)
    target = SessionTarget(
        session_alias="COO-CODEX",
        target_seat="coo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=False,
    )
    registry = SessionTargetRegistry(
        schema=TARGET_SCHEMA,
        lifecycle_authority="executive_os",
        production_armed=False,
        policy_version="wake-ack-test",
        default_alias_by_seat={"coo": target.session_alias},
        workstream_alias_by_seat={},
        root_job_bindings={},
        targets={target.session_alias: target},
    )
    binding = project_runtime_binding(runtime, sealed.attempt_id, target)
    route_binding = delivery_binding or binding
    obligations = tuple(
        mint_obligation(
            wake_kind="job_failed",
            source_kind="executive_inbox_attention",
            source_ref=f"eia-{ordinal + 32:012x}",
            declared_target_seat="coo",
        )
        for ordinal in range(obligation_count)
    )
    routes = tuple(
        route_obligation(obligation, registry, binding=route_binding)
        for obligation in obligations
    )
    base_attempts = tuple(
        make_delivery_attempt(obligation, route, attempt_n=1)
        for obligation, route in zip(obligations, routes, strict=True)
    )
    command_ids = tuple(sorted(item.attempt_command_id for item in base_attempts))
    nudge_id = mint_nudge_id(routes[0].destination_digest, command_ids)
    attempts = tuple(
        dataclasses.replace(
            attempt,
            nudge_id=nudge_id,
            nudge_attempt_command_ids=command_ids,
        )
        for attempt in base_attempts
    )
    delivered = set(range(obligation_count)) if delivered_indices is None else delivered_indices
    items = []
    for ordinal, (obligation, attempt) in enumerate(
        zip(obligations, attempts, strict=True)
    ):
        items.extend(
            (
                (requested_record(obligation), obligation),
                (attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT), obligation),
                (
                    attempt_record(
                        attempt,
                        LedgerPhase.DELIVERED
                        if ordinal in delivered
                        else LedgerPhase.ACCEPTED,
                    ),
                    obligation,
                ),
            )
        )
    repo = WakeLedgerRepository(runtime)
    repo.append_records_atomic(tuple(items))
    trusted = TrustedWorkerWakeAckProjection(
        target_attempt_id=sealed.attempt_id,
        process_generation_id=generation.process_generation_id,
        binding_id=binding.binding_id,
        binding_generation=binding.binding_generation,
        provider_session_id=str(binding.native_handle),
        provider_native_turn_id="TURN-ACK-1",
        nudge_id=nudge_id,
        obligation_ids=tuple(sorted(item.obligation_id for item in obligations)),
        terminal_ack_trailer=True,
    )
    return _IngressFixture(
        runtime=runtime,
        repo=repo,
        registry=registry,
        binding=binding,
        target_attempt_id=sealed.attempt_id,
        process_generation_id=generation.process_generation_id,
        obligations=obligations,
        nudge_id=nudge_id,
        trusted=trusted,
    )


def _ack_rows(fixture: _IngressFixture, obligation_id: str):
    return tuple(
        item
        for item in fixture.repo.list_records(obligation_id)
        if item.record.phase is LedgerPhase.TARGET_ACKNOWLEDGED
    )


def test_exact_delivered_current_binding_persists_one_safe_ack_and_replays(tmp_path) -> None:
    """Catches accepting a receipt without one exact current-binding ACK transaction."""

    fixture = _ingress_fixture(tmp_path)
    claim = WakeAckClaim(fixture.trusted.obligation_ids)
    first = acknowledge_consumed_wakes(
        fixture.runtime,
        fixture.registry,
        claim=claim,
        trusted=fixture.trusted,
    )
    second = acknowledge_consumed_wakes(
        fixture.runtime,
        fixture.registry,
        claim=claim,
        trusted=fixture.trusted,
    )
    assert len(first) == len(second) == 1
    assert first[0].inserted is True
    assert second[0].inserted is False
    oid = fixture.trusted.obligation_ids[0]
    rows = _ack_rows(fixture, oid)
    assert len(rows) == 1
    payload = ack_event_payload(rows[0].record.ack)
    assert payload["delivered_command_id"] == f"{oid}:A1:DELIVERED"
    assert "native_handle" not in payload
    assert "provider_session_id" not in payload
    assert "provider_native_turn_id" not in payload


def test_two_concurrent_consumers_commit_one_ack(tmp_path) -> None:
    """Catches losing BEGIN IMMEDIATE serialization at the ACK compare-and-commit."""

    fixture = _ingress_fixture(tmp_path)
    claim = WakeAckClaim(fixture.trusted.obligation_ids)
    barrier = threading.Barrier(2)
    results = []
    errors: list[BaseException] = []

    def _consume() -> None:
        try:
            runtime = Runtime.at(tmp_path)
            barrier.wait(timeout=5)
            results.append(
                acknowledge_consumed_wakes(
                    runtime,
                    fixture.registry,
                    claim=claim,
                    trusted=fixture.trusted,
                )
            )
        except BaseException as exc:  # noqa: BLE001 - surface thread failures
            errors.append(exc)

    threads = [threading.Thread(target=_consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(result[0].inserted for result in results) == [False, True]
    obligation_id = fixture.trusted.obligation_ids[0]
    assert len(_ack_rows(fixture, obligation_id)) == 1


def test_accepted_only_or_stale_delivery_refuses_without_any_ack(tmp_path) -> None:
    """Catches laundering ACCEPTED or an old binding generation into target ACK."""

    accepted = _ingress_fixture(tmp_path / "accepted", delivered_indices=set())
    with pytest.raises(WakeAckIngressError, match="DELIVERED"):
        acknowledge_consumed_wakes(
            accepted.runtime,
            accepted.registry,
            claim=WakeAckClaim(accepted.trusted.obligation_ids),
            trusted=accepted.trusted,
        )
    assert not _ack_rows(accepted, accepted.trusted.obligation_ids[0])

    current = _ingress_fixture(tmp_path / "binding-source")
    stale_binding = dataclasses.replace(
        current.binding,
        binding_generation=current.binding.binding_generation + 1,
    )
    stale = _ingress_fixture(
        tmp_path / "stale-delivery",
        delivery_binding=stale_binding,
    )
    with pytest.raises(WakeAckIngressError, match="binding"):
        acknowledge_consumed_wakes(
            stale.runtime,
            stale.registry,
            claim=WakeAckClaim(stale.trusted.obligation_ids),
            trusted=stale.trusted,
        )
    assert not _ack_rows(stale, stale.trusted.obligation_ids[0])


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    [
        ("target_attempt_id", "ATT-" + "f" * 32, "target Attempt"),
        (
            "process_generation_id",
            "GEN-00000000000000000000000000000999",
            "process generation",
        ),
        ("binding_id", "bind-other123", "binding"),
        ("binding_generation", 9, "binding"),
        ("provider_session_id", "PROVIDER-SESSION-OTHER", "provider session"),
        ("nudge_id", "NUDGE-" + "9" * 32, "DELIVERED"),
    ],
)
def test_exact_ingress_refuses_mismatched_trusted_identity(
    tmp_path,
    field_name,
    value,
    match,
) -> None:
    """Catches a sealed claim from another Attempt/generation/binding/session/nudge."""

    fixture = _ingress_fixture(tmp_path)
    trusted = dataclasses.replace(fixture.trusted, **{field_name: value})
    with pytest.raises(WakeAckIngressError, match=match):
        acknowledge_consumed_wakes(
            fixture.runtime,
            fixture.registry,
            claim=WakeAckClaim(fixture.trusted.obligation_ids),
            trusted=trusted,
        )
    assert not _ack_rows(fixture, fixture.trusted.obligation_ids[0])


def test_coalesced_claim_is_atomic_and_a_delivered_subset_can_ack(tmp_path) -> None:
    """Catches partial commit when one coalesced obligation lacks exact delivery."""

    partial = _ingress_fixture(
        tmp_path / "partial",
        obligation_count=2,
        delivered_indices={0},
    )
    with pytest.raises(WakeAckIngressError, match="DELIVERED"):
        acknowledge_consumed_wakes(
            partial.runtime,
            partial.registry,
            claim=WakeAckClaim(partial.trusted.obligation_ids),
            trusted=partial.trusted,
        )
    assert all(not _ack_rows(partial, oid) for oid in partial.trusted.obligation_ids)

    complete = _ingress_fixture(tmp_path / "complete", obligation_count=2)
    subset_ids = (complete.trusted.obligation_ids[0],)
    subset = dataclasses.replace(complete.trusted, obligation_ids=subset_ids)
    persisted = acknowledge_consumed_wakes(
        complete.runtime,
        complete.registry,
        claim=WakeAckClaim(subset_ids),
        trusted=subset,
    )
    assert len(persisted) == 1
    assert len(_ack_rows(complete, subset_ids[0])) == 1
    assert not _ack_rows(complete, complete.trusted.obligation_ids[1])
