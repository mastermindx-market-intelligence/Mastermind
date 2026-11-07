"""A1-ARM private finite control context, arm receipt, and historical status.

Everything here runs against actual SQLite through the real Runtime
boundaries.  The canonical read-only fixture bodies (``_v2_intent``,
``_register``, ``_register_placement_union``, ``_v3_execution_binding``,
``_complete_ohf_role``) are copies of the pointers named in the accepted
A1-ARM contract; the v2 armed binding is derived from the v3 fixture the
way the existing phase1fc compatibility test derives it.  The private
composition producer is used here explicitly as a test fixture: it is not
a wire, sandbox, or installation proof.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

import control_plane.executive_runtime as executive_runtime
from control_plane.ceo_intent import (
    INTENT_SCHEMA_V2,
    intent_fingerprint,
    submit_intent,
    validate_intent,
)
from control_plane.executive_authority import ExecutiveAuthorityPolicy
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
)
from control_plane.executive_orchestration_result import (
    RESULT_SCHEMA,
    RawRoleResultObservation,
    canonical_bytes as result_canonical_bytes,
    canonical_digest as result_digest,
)
from control_plane.executive_runtime import (
    FiniteControlContext,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
    finite_host_binding_digest,
)
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    TurnStartObservation,
    WorkspaceIdentity,
)

TEST_CONFIG_PIN = hashlib.sha256(
    b"a1-arm-labelled-test-config-snapshot"
).hexdigest()
TEST_SOURCE_RELEASE_PIN = hashlib.sha256(
    b"a1-arm-labelled-test-source-release-manifest"
).hexdigest()
TEST_BINDING_PIN = hashlib.sha256(
    b"a1-arm-labelled-test-composition-binding"
).hexdigest()
ATTESTATION_A = hashlib.sha256(b"a1-arm-test-attestation-one").hexdigest()
ATTESTATION_B = hashlib.sha256(b"a1-arm-test-attestation-two").hexdigest()

FINITE_EVENT_SCHEMA = "mastermind.coo_finite_drive/v1"
STABLE_PIN_KEYS = (
    "intent_id",
    "intent_fingerprint",
    "config_snapshot_sha256",
    "source_release_sha256",
    "authority_policy_sha256",
    "coo_policy_sha256",
    "binding_digest_sha256",
    "host_binding_digest_sha256",
)
PROJECTION_KEYS = (
    "schema_version",
    "root_job_id",
    *STABLE_PIN_KEYS,
    "max_total_attempts",
    "expires_at_ms",
)
PAYLOAD_KEYS = frozenset(
    (
        "schema_version",
        "root_job_id",
        *STABLE_PIN_KEYS,
        "max_total_attempts",
        "expires_at_ms",
        "control_attestation_digest",
        "policy_digest",
        "command_id",
    )
)
STATUS_KEYS = frozenset(
    (
        "schema_version",
        "root_job_id",
        "max_total_attempts",
        "expires_at_ms",
        "spent",
        "remaining",
        "expired",
        "exhausted",
        "halt_reason",
        "command_id",
        "arm_event_id",
        "policy",
    )
)


class MutableClock:
    def __init__(self, value: int = 1_800_000_000_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += seconds * 1_000


def _canonical(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _table_counts(database: Path) -> dict[str, int]:
    connection = sqlite3.connect(database)
    try:
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in (
                "jobs",
                "attempts",
                "events",
                "workers",
                "worker_quota_classes",
                "harness_session_epochs",
                "process_generations",
            )
        }
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# canonical read-only fixture copies (phase1fc pointers)
# ---------------------------------------------------------------------------


def _v2_intent(**overrides):
    value = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-FINITE-ARM-001",
        "actor": "ceo-sol",
        "objective": "Run one inert deterministic COO cycle.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {
            "mastermind_sha": "a" * 40,
            "macro_sha": "b" * 40,
        },
        "execution_contract": {
            "requested_authorities": ["READ"],
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }
    value.update(overrides)
    return value


def _register(runtime: Runtime, worker_id: str = "worker-1") -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}@company",
        worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={
            "default": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
            }
        },
    )


def _register_placement_union(runtime: Runtime) -> None:
    runtime.workers.register_worker(
        "worker-a",
        provider="codex",
        account_label="worker-a@company",
        worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={
            "codex-hf1q-step": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "metadata": {
                    "routing_policy_version": "fph0-routing",
                    "execution_profile_id": "fph0-execution",
                    "execution_profile_digest": "b" * 64,
                    "capability_policy_version": "fph0-capability",
                    "capability_policy_digest": "c" * 64,
                },
            },
            "codex-operator": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "metadata": {
                    "routing_policy_version": "fph0-routing",
                    "execution_profile_id": "fph0-execution",
                    "execution_profile_digest": "b" * 64,
                    "capability_policy_version": "fph0-capability",
                    "capability_policy_digest": "c" * 64,
                },
            },
        },
    )
    runtime.workers.register_worker(
        "worker-b",
        provider="claude-compatible-subscription",
        account_label="worker-b@company",
        worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={
            "claude-hf1q-step": {
                "provider": "claude-compatible-subscription",
                "capabilities": ["read", "research"],
                "cost_class": "small",
            }
        },
    )


def _v3_execution_binding():
    return {
        "eligible_quota_classes": ["codex-hf1q-step"],
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "cost_class": "small",
        "base_sha": "a" * 40,
        "routing_policy_version": "fph0-routing",
        "execution_profile_id": "fph0-execution",
        "execution_profile_digest": "b" * 64,
        "capability_policy_version": "fph0-capability",
        "capability_policy_digest": "c" * 64,
        "operator_eligible_quota_classes": ["codex-operator"],
        "operator_provider": "codex",
        "operator_model": "gpt-5.6-sol",
        "operator_effort": "xhigh",
        "operator_cost_class": "small",
        "operator_routing_policy_version": "fph0-routing",
        "operator_execution_profile_id": "fph0-execution",
        "operator_execution_profile_digest": "b" * 64,
        "operator_capability_policy_version": "fph0-capability",
        "operator_capability_policy_digest": "c" * 64,
        "operator_harness_binary_digest": "d" * 64,
        "operator_harness_version": "fph0-harness",
        "operator_harness_armed": False,
        "host_execution_binding_version": (
            "mastermind.host_execution_binding/v3"
        ),
        "work_placement_union": [
            {"provider_realm": "codex", "quota_class": "codex-hf1q-step"},
            {
                "provider_realm": "claude-compatible-subscription",
                "quota_class": "claude-hf1q-step",
            },
        ],
    }


def _armed_v2_binding():
    """COPY of the v3 fixture minus v3-only fields, armed for the fixture."""

    binding = _v3_execution_binding()
    binding.pop("work_placement_union", None)
    binding.pop("host_execution_binding_version", None)
    binding["operator_harness_armed"] = True
    return binding


def _orchestration_profile(dispatch: OrchestrationDispatchOutcome):
    attempt = dispatch.attempt
    return RequestedExecutionProfile(
        worker_id=str(attempt.worker_id),
        provider="codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity("/tmp/work", "b" * 40, 1, 2, 0, 0),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=str(attempt.authority_policy_hash),
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _orchestration_attestation(profile: RequestedExecutionProfile):
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


def _complete_ohf_role(
    runtime: Runtime,
    dispatch: OrchestrationDispatchOutcome,
    role_result: dict,
    *,
    identity_seed: int,
) -> tuple[dict, dict]:
    """Complete one typed role entirely through inert OHF Runtime boundaries."""

    assert dispatch.lease_token is not None
    attempt = dispatch.attempt
    job = runtime.jobs.get_job(attempt.job_id)
    assert job is not None and job.orchestration_role
    harness = runtime.operator_harness
    profile = _orchestration_profile(dispatch)
    sealed = harness.seal_operator_harness_attempt(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start = OperationId(f"ohf-op:complete-{identity_seed}-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(
        identity_seed, identity_seed, f"start-{identity_seed}", "boot-test"
    )
    provider_session = f"SESSION-{identity_seed}"
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id=provider_session,
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id=str(sealed.worker_id),
        process_generation_id=generation.process_generation_id,
        provider_session_id=provider_session,
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name=f"fixture-principal-{identity_seed}",
        os_principal_uid=identity_seed,
        provider_home_identity={
            "path": f"/tmp/phase1fc-codex-home-{identity_seed}",
            "device": identity_seed,
            "inode": identity_seed + 1,
            "uid": identity_seed,
            "gid": identity_seed,
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_orchestration_attestation(profile),
        principal_observation=principal,
    )
    turn_op = OperationId(f"ohf-op:complete-{identity_seed}-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=turn_op,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    native_turn = f"NATIVE-{identity_seed}"
    harness.acknowledge_turn(
        turn=turn,
        operation_id=turn_op,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        observation=TurnStartObservation(native_turn, True),
    )
    artifact_digest = hashlib.sha256(f"artifact-{identity_seed}".encode()).hexdigest()
    harness.record_candidate_evidence(
        turn=turn,
        candidate=CandidateResult(
            attempt.attempt_id,
            epoch.session_epoch_id,
            generation.process_generation_id,
            artifact_digest,
            "typed fixture candidate",
        ),
        events=(),
        cursor=EventCursor(
            attempt.attempt_id,
            epoch.session_epoch_id,
            generation.process_generation_id,
            turn_id=turn.turn_id,
        ),
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    envelope = {
        "schema_version": RESULT_SCHEMA,
        "job_id": job.job_id,
        "run_id": attempt.attempt_id,
        "worker_id": str(attempt.worker_id),
        "role": job.orchestration_role,
        "status": "COMPLETED",
        "role_result": role_result,
        "summary": "bounded typed fixture result",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
    canonical = result_canonical_bytes(envelope).decode("utf-8")
    observation = RawRoleResultObservation(
        attempt_id=attempt.attempt_id,
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        turn_id=turn.turn_id,
        provider_session_id=provider_session,
        provider_native_turn_id=native_turn,
        provider_turn_artifact_digest=artifact_digest,
        canonical_result_json=canonical,
        canonical_result_digest=hashlib.sha256(canonical.encode()).hexdigest(),
        canonical_result_byte_length=len(canonical.encode()),
    )
    seal = harness.seal_orchestration_role_result(
        turn=turn,
        observation=observation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    death = ReconcileObservation(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        observed_process=process,
        provider_session_reachable=True,
        provider_writer_state=ProviderWriterState.RELEASED,
        observed_provider_session_id=provider_session,
    )
    harness.record_graceful_stop(
        generation=generation,
        observation=death,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.abandon_epoch(
        epoch=epoch,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    terminal = {
        "schema_version": "mastermind.orchestration_terminal_receipt/v1",
        "status": "COMPLETED",
        "job_id": job.job_id,
        "attempt_id": attempt.attempt_id,
        "orchestration_role": job.orchestration_role,
        "execution_mode": "OPERATOR_HARNESS",
        "result_seal_command_id": f"orchestration-result-seal:{attempt.attempt_id}",
        "result_evidence": None,
        "result_envelope": envelope,
        "result_envelope_digest": result_digest(envelope),
        "artifact_receipt_digest": result_digest([]),
        "validation_receipt_digest": result_digest([]),
        "effective_grant_digest": attempt.effective_grant_digest,
    }
    terminal["terminal_evidence_digest"] = result_digest(terminal)
    runtime.attempts.complete_attempt(
        attempt.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        payload=terminal,
    )
    return seal, terminal


# ---------------------------------------------------------------------------
# finite control helpers
# ---------------------------------------------------------------------------


def _finite_root(runtime: Runtime, intent_id: str):
    envelope = _v2_intent(intent_id=intent_id)
    receipt = submit_intent(
        runtime, envelope, execution_binding=_armed_v2_binding()
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    return envelope, root


def _bound_definition(
    root,
    envelope,
    *,
    cap: int = 340,
    attestation: str = ATTESTATION_A,
    expires_at_ms: int | None = None,
    runtime: Runtime | None = None,
    overrides: dict | None = None,
) -> dict:
    now = runtime.store.now_ms() if runtime is not None else 0
    value = {
        "schema_version": executive_runtime.FINITE_CONTROL_CONTEXT_SCHEMA,
        "mode": "manual_finite",
        "phase": "bound",
        "intent_id": envelope["intent_id"],
        "intent_fingerprint": intent_fingerprint(validate_intent(envelope)),
        "config_snapshot_sha256": TEST_CONFIG_PIN,
        "source_release_sha256": TEST_SOURCE_RELEASE_PIN,
        "authority_policy_sha256": ExecutiveAuthorityPolicy.load().sha256,
        "coo_policy_sha256": CooCyclePolicy.load().policy_sha256,
        "binding_digest_sha256": TEST_BINDING_PIN,
        "host_binding_digest_sha256": finite_host_binding_digest(root.constraints),
        "control_attestation_digest": attestation,
        "root_job_id": root.job_id,
        "max_total_attempts": cap,
        "expires_at_ms": (
            int(expires_at_ms) if expires_at_ms is not None else now + 3_600_000
        ),
    }
    if overrides:
        value.update(overrides)
    return value


def _admission_definition(root, envelope, **kwargs) -> dict:
    value = _bound_definition(root, envelope, **kwargs)
    value["phase"] = "admission_only"
    for key in ("root_job_id", "max_total_attempts", "expires_at_ms"):
        value.pop(key)
    return value


def _issue(definition: dict) -> FiniteControlContext:
    return executive_runtime._issue_finite_control_context(
        definition,
        _producer_capability=(
            executive_runtime._FINITE_CONTROL_COMPOSITION_PRODUCER
        ),
    )


def _arm(runtime: Runtime, context: FiniteControlContext):
    return runtime.jobs.arm_finite_cycle(
        context.definition["root_job_id"], owner_issued_policy=context
    )


def _projection(payload: dict) -> dict:
    return {key: payload[key] for key in PROJECTION_KEYS}


# ---------------------------------------------------------------------------
# 1. real strict-v2 full-binding arm, status, replay, reopen, cutoff
# ---------------------------------------------------------------------------


def test_finite_arm_positive_lifecycle_replay_reopen_and_cutoff(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-001")
    fingerprint = intent_fingerprint(validate_intent(envelope))
    assert root.orchestration_provenance is not None
    assert root.orchestration_provenance["source_digest"] == fingerprint
    assert root.orchestration_provenance["source_id"] == "CEO-FINITE-ARM-001"

    definition = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )
    context = _issue(definition)
    runtime.store.bind_finite_control_context(context)

    before = _table_counts(runtime.store.path)
    event = _arm(runtime, context)
    after = _table_counts(runtime.store.path)
    assert after["events"] == before["events"] + 1
    for key in (
        "jobs",
        "attempts",
        "workers",
        "worker_quota_classes",
        "harness_session_epochs",
        "process_generations",
    ):
        assert after[key] == before[key]

    assert event.event_type == "COO_FINITE_DRIVE_ARMED"
    assert event.aggregate_type == "job"
    assert event.aggregate_id == root.job_id
    assert event.job_id == root.job_id
    assert event.actor == "executive-control-service"
    assert event.attempt_id is None
    assert event.worker_id is None
    assert event.quota_class is None

    payload = event.payload
    assert set(payload) == PAYLOAD_KEYS
    assert payload["schema_version"] == FINITE_EVENT_SCHEMA
    for key in STABLE_PIN_KEYS:
        assert payload[key] == definition[key]
    assert payload["max_total_attempts"] == 340
    assert payload["expires_at_ms"] == clock.value + 3_600_000
    assert payload["control_attestation_digest"] == ATTESTATION_A
    projection = _projection(payload)
    policy_digest = hashlib.sha256(
        _canonical(projection).encode("utf-8")
    ).hexdigest()
    assert payload["policy_digest"] == policy_digest
    assert event.command_id == f"arm-coo-root:{root.job_id}:{policy_digest}"
    assert payload["command_id"] == event.command_id

    with runtime.store.read() as connection:
        index_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND name='events_one_coo_finite_drive_arm_per_root'"
        ).fetchone()
        armed_rows = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='COO_FINITE_DRIVE_ARMED'"
        ).fetchone()[0]
        stored_payload_json = connection.execute(
            "SELECT payload_json FROM events WHERE command_id=?",
            (event.command_id,),
        ).fetchone()[0]
    assert index_row is not None
    assert int(armed_rows) == 1
    assert _canonical(json.loads(str(stored_payload_json))) == str(
        stored_payload_json
    )

    status = runtime.jobs.finite_cycle_status(root.job_id)
    assert status is not None
    assert set(status) == STATUS_KEYS
    assert status["schema_version"] == FINITE_EVENT_SCHEMA
    assert status["root_job_id"] == root.job_id
    assert status["max_total_attempts"] == 340
    assert status["expires_at_ms"] == clock.value + 3_600_000
    assert status["spent"] == 0
    assert status["remaining"] == 340
    assert status["expired"] is False
    assert status["exhausted"] is False
    assert status["halt_reason"] is None
    assert status["command_id"] == event.command_id
    assert status["arm_event_id"] == event.event_id
    assert set(status["policy"]) == set(STABLE_PIN_KEYS) | {
        "control_attestation_digest"
    }
    for key in status["policy"]:
        assert status["policy"][key] == definition[key]

    replay = _arm(runtime, context)
    assert replay == event

    # A newly qualified process (fresh store, new attestation, equal stable
    # pins) replays the original event and retains its original attestation.
    fresh = Runtime.at(tmp_path, clock=clock)
    context_b = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            attestation=ATTESTATION_B,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    fresh.store.bind_finite_control_context(context_b)
    replay_b = _arm(fresh, context_b)
    assert replay_b == event
    assert replay_b.payload["control_attestation_digest"] == ATTESTATION_A

    # A fresh restarted store reads the same historical status unbound.
    reader = Runtime.at(tmp_path, clock=clock)
    unbound_status = reader.jobs.finite_cycle_status(root.job_id)
    assert unbound_status is not None
    assert unbound_status["arm_event_id"] == event.event_id
    assert unbound_status["policy"]["control_attestation_digest"] == (
        ATTESTATION_A
    )

    # Exact replay and status after cutoff stay readable with zero writes.
    clock.advance(seconds=7_200)
    cutoff_before = _table_counts(runtime.store.path)
    cutoff_status = runtime.jobs.finite_cycle_status(root.job_id)
    cutoff_replay = _arm(runtime, context)
    cutoff_after = _table_counts(runtime.store.path)
    assert cutoff_replay == event
    assert cutoff_after == cutoff_before
    assert cutoff_status is not None
    assert cutoff_status["expired"] is True
    assert cutoff_status["exhausted"] is False
    assert cutoff_status["halt_reason"] == "expired"
    assert cutoff_status["spent"] == 0
    assert cutoff_status["remaining"] == 340


# ---------------------------------------------------------------------------
# 2. drift / identity / binding refusals with zero mutation
# ---------------------------------------------------------------------------


def test_finite_arm_refuses_verifiable_pin_drift_before_any_arm(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-DRIFT-001")
    other_envelope, other_root = _finite_root(
        runtime, "CEO-FINITE-ARM-DRIFT-002"
    )
    baseline = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )
    drifts = {
        "intent_id": "CEO-FINITE-ARM-DRIFT-002",
        "intent_fingerprint": "0" * 64,
        "authority_policy_sha256": "0" * 64,
        "coo_policy_sha256": "0" * 64,
        "host_binding_digest_sha256": "0" * 64,
    }
    before = _table_counts(runtime.store.path)
    for key, value in drifts.items():
        context = _issue(
            _bound_definition(
                root,
                envelope,
                runtime=runtime,
                expires_at_ms=clock.value + 3_600_000,
                overrides={key: value},
            )
        )
        # each changed context needs its own fresh store over the same
        # database: a binding never retargets once exercised or not
        fresh = Runtime.at(tmp_path, clock=clock)
        fresh.store.bind_finite_control_context(context)
        with pytest.raises(StateConflict):
            _arm(fresh, context)
    # a context bound to another root refuses on this root
    other_context = _issue(
        _bound_definition(
            other_root,
            other_envelope,
            runtime=runtime,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    other_store = Runtime.at(tmp_path, clock=clock)
    other_store.store.bind_finite_control_context(other_context)
    with pytest.raises(StateConflict):
        other_store.jobs.arm_finite_cycle(
            root.job_id, owner_issued_policy=other_context
        )
    assert _table_counts(runtime.store.path) == before
    assert runtime.jobs.finite_cycle_status(root.job_id) is None


def test_finite_arm_refuses_every_stable_drift_after_first_arm(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-SECOND-001")
    context = _issue(
        _bound_definition(
            root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
        )
    )
    runtime.store.bind_finite_control_context(context)
    event = _arm(runtime, context)

    drifts = {
        "intent_fingerprint": "0" * 64,
        "config_snapshot_sha256": "1" * 64,
        "source_release_sha256": "1" * 64,
        "authority_policy_sha256": "1" * 64,
        "coo_policy_sha256": "1" * 64,
        "binding_digest_sha256": "1" * 64,
        "host_binding_digest_sha256": "1" * 64,
    }
    before = _table_counts(runtime.store.path)
    for key, value in drifts.items():
        drifted = _issue(
            _bound_definition(
                root,
                envelope,
                runtime=runtime,
                expires_at_ms=clock.value + 3_600_000,
                overrides={key: value},
            )
        )
        fresh = Runtime.at(tmp_path, clock=clock)
        fresh.store.bind_finite_control_context(drifted)
        with pytest.raises(StateConflict):
            _arm(fresh, drifted)
    for cap, expiry in ((339, clock.value + 3_600_000), (340, clock.value + 3_601_000)):
        drifted = _issue(
            _bound_definition(
                root,
                envelope,
                runtime=runtime,
                cap=cap,
                expires_at_ms=expiry,
            )
        )
        fresh = Runtime.at(tmp_path, clock=clock)
        fresh.store.bind_finite_control_context(drifted)
        with pytest.raises(StateConflict):
            _arm(fresh, drifted)
    # explicit old command with a changed definition refuses
    with pytest.raises(StateConflict):
        runtime.jobs.arm_finite_cycle(
            root.job_id, owner_issued_policy=context, command_id="arm-coo-root:x:y"
        )
    assert _table_counts(runtime.store.path) == before
    with runtime.store.read() as connection:
        rows = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='COO_FINITE_DRIVE_ARMED'"
        ).fetchone()[0]
    assert int(rows) == 1
    assert runtime.jobs.finite_cycle_status(root.job_id)["arm_event_id"] == (
        event.event_id
    )


def test_finite_arm_refuses_wrong_root_child_and_forged_policy_objects(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-IDENT-001")
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    context = _issue(
        _bound_definition(
            root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
        )
    )
    runtime.store.bind_finite_control_context(context)
    before = _table_counts(runtime.store.path)

    # child (planner) is not the aggregation root
    with pytest.raises(StateConflict):
        runtime.jobs.arm_finite_cycle(
            planner.job_id, owner_issued_policy=context
        )
    # unknown root
    with pytest.raises(StateConflict):
        runtime.jobs.arm_finite_cycle("JOB-999", owner_issued_policy=context)
    # plain dict lookalike
    with pytest.raises(StateConflict):
        runtime.jobs.arm_finite_cycle(
            root.job_id, owner_issued_policy=dict(context.definition)
        )
    # subclass lookalike
    class _Lookalike(FiniteControlContext):
        pass

    with pytest.raises(StateConflict):
        runtime.jobs.arm_finite_cycle(
            root.job_id,
            owner_issued_policy=_Lookalike(
                context._definition_json,
                executive_runtime._FINITE_CONTROL_COMPOSITION_PRODUCER,
            ),
        )
    # foreign producer token
    with pytest.raises(StateConflict):
        runtime.jobs.arm_finite_cycle(
            root.job_id,
            owner_issued_policy=FiniteControlContext(
                context._definition_json, object()
            ),
        )
    # foreign issue capability
    with pytest.raises(StateConflict):
        executive_runtime._issue_finite_control_context(
            context.definition, _producer_capability=object()
        )
    # unbound store
    unbound = Runtime.at(tmp_path, clock=clock)
    with pytest.raises(StateConflict):
        _arm(unbound, context)
    # mismatched bound context
    mismatched = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            cap=339,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    with pytest.raises(StateConflict):
        runtime.jobs.arm_finite_cycle(root.job_id, owner_issued_policy=mismatched)
    # admission-only context issues but must refuse arm
    admission = _issue(
        _admission_definition(
            root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
        )
    )
    assert set(admission.definition) == set(STABLE_PIN_KEYS) | {
        "schema_version",
        "mode",
        "phase",
        "control_attestation_digest",
    }
    admission_store = Runtime.at(tmp_path, clock=clock)
    admission_store.store.bind_finite_control_context(admission)
    with pytest.raises(StateConflict):
        admission_store.jobs.arm_finite_cycle(
            root.job_id, owner_issued_policy=admission
        )
    assert _table_counts(runtime.store.path) == before
    assert runtime.jobs.finite_cycle_status(root.job_id) is None


def test_finite_control_malformed_definitions_refuse_at_issue(tmp_path):
    clock = MutableClock(1_800_000_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-SHAPE-001")
    good = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )

    def mutate(key, value):
        value_dict = dict(good)
        value_dict[key] = value
        return value_dict

    bad_definitions = [
        mutate("schema_version", "mastermind.coo_finite_drive_context/v2"),
        mutate("mode", "automatic_finite"),
        mutate("mode", None),
        mutate("phase", "armed"),
        mutate("phase", ["bound"]),
        mutate("phase", {"bound": True}),
        mutate("phase", None),
        {**good, "unexpected_key": "x"},
        {key: value for key, value in good.items() if key != "binding_digest_sha256"},
        mutate("intent_id", "AB"),
        mutate("intent_id", 42),
        mutate("intent_fingerprint", "A" * 64),
        mutate("intent_fingerprint", 42),
        mutate("intent_fingerprint", ["a" * 64]),
        mutate("control_attestation_digest", None),
        mutate("config_snapshot_sha256", "0" * 63),
        mutate("root_job_id", "not a job id"),
        mutate("max_total_attempts", True),
        mutate("max_total_attempts", 0),
        mutate("max_total_attempts", -1),
        mutate("max_total_attempts", 341),
        mutate("max_total_attempts", 20.0),
        mutate("max_total_attempts", "340"),
        mutate("expires_at_ms", 0),
        mutate("expires_at_ms", -1),
        mutate("expires_at_ms", 2**63),
        mutate("expires_at_ms", 1.5),
        mutate("expires_at_ms", True),
        {**_admission_definition(root, envelope, runtime=runtime),
         "root_job_id": root.job_id},
        ["not", "a", "mapping"],
    ]
    for bad in bad_definitions:
        with pytest.raises(StateConflict):
            _issue(bad)

    # a definition that is not even a mapping refuses
    with pytest.raises(StateConflict):
        executive_runtime._issue_finite_control_context(
            good, _producer_capability=None
        )
    # direct construction with the genuine token but non-canonical bytes refuses
    with pytest.raises(StateConflict):
        FiniteControlContext(json.dumps(good, indent=2), None)
    issued = _issue(good)
    with pytest.raises(StateConflict):
        FiniteControlContext(_canonical(dict(good, phase="armed")), None)


# ---------------------------------------------------------------------------
# 3. two independent SQLite connections racing
# ---------------------------------------------------------------------------


def _race(tmp_path, definitions) -> list:
    results: list = []
    barrier = threading.Barrier(len(definitions))

    def worker(definition: dict) -> None:
        try:
            runtime = Runtime.at(tmp_path)
            context = _issue(definition)
            runtime.store.bind_finite_control_context(context)
            barrier.wait(timeout=60)
            results.append(
                ("ok", _arm(runtime, context))
            )
        except BaseException as exc:  # collected, re-raised by the assertions
            results.append(("err", exc))

    threads = [
        threading.Thread(target=worker, args=(definition,))
        for definition in definitions
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    return results


def test_finite_arm_independent_connection_race(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register_placement_union(runtime)
    envelope_a, root_a = _finite_root(runtime, "CEO-FINITE-ARM-RACE-001")
    envelope_b, root_b = _finite_root(runtime, "CEO-FINITE-ARM-RACE-002")

    different = _race(
        tmp_path,
        [
            _bound_definition(root_a, envelope_a, runtime=runtime, cap=340),
            _bound_definition(root_a, envelope_a, runtime=runtime, cap=339),
        ],
    )
    winners = [item for item in different if item[0] == "ok"]
    losers = [item for item in different if item[0] == "err"]
    assert len(winners) == 1
    assert len(losers) == 1
    assert isinstance(losers[0][1], StateConflict)
    with runtime.store.read() as connection:
        armed = int(
            connection.execute(
                "SELECT COUNT(*) FROM events "
                "WHERE event_type='COO_FINITE_DRIVE_ARMED' AND job_id=?",
                (root_a.job_id,),
            ).fetchone()[0]
        )
    assert armed == 1
    assert runtime.jobs.finite_cycle_status(root_a.job_id) is not None

    identical_source = _bound_definition(
        root_b, envelope_b, runtime=runtime, cap=340
    )
    identical = _race(
        tmp_path,
        [dict(identical_source), dict(identical_source)],
    )
    assert [item[0] for item in identical] == ["ok", "ok"]
    first, second = identical[0][1], identical[1][1]
    assert first.event_id == second.event_id
    assert first == second
    with runtime.store.read() as connection:
        armed = int(
            connection.execute(
                "SELECT COUNT(*) FROM events "
                "WHERE event_type='COO_FINITE_DRIVE_ARMED' AND job_id=?",
                (root_b.job_id,),
            ).fetchone()[0]
        )
    assert armed == 1


# ---------------------------------------------------------------------------
# 4. dispatched-child custody, resolved history counts, cap law
# ---------------------------------------------------------------------------


def test_finite_arm_history_custody_and_cap_laws(tmp_path):
    clock = MutableClock(1_800_100_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    _register_placement_union(runtime)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-HIST-001")
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
        ),
        worker_id="worker-a",
    )
    assert isinstance(dispatch, OrchestrationDispatchOutcome)

    context = _issue(
        _bound_definition(
            root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
        )
    )
    runtime.store.bind_finite_control_context(context)
    unresolved_before = _table_counts(runtime.store.path)
    with pytest.raises(StateConflict, match="unresolved"):
        _arm(runtime, context)
    assert runtime.jobs.finite_cycle_status(root.job_id) is None

    plan_body = {
        "schema_version": "mastermind.execution_plan/v2",
        "root_job_id": root.job_id,
        "plan_attempt_id": dispatch.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-0",
                "objective": "FPH0 trusted placement 0.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
                "placement": {
                    "provider_realm": "codex",
                    "quota_class": "codex-hf1q-step",
                },
            }
        ],
    }
    historical_owner = Runtime.at(tmp_path, clock=clock)
    _complete_ohf_role(historical_owner, dispatch, plan_body, identity_seed=8101)
    completed = runtime.jobs.get_job(planner.job_id)
    assert completed is not None and completed.status.value == "COMPLETED"
    still_root = runtime.jobs.get_job(root.job_id)
    assert still_root is not None and still_root.status.value == "QUEUED"

    released_before = _table_counts(runtime.store.path)
    spent = released_before["attempts"]
    assert spent == 1

    # cap <= spent refuses; each changed budget binds its own fresh store
    # over the same real database (a binding never retargets)
    exhausted_context = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            cap=1,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    exhausted_store = Runtime.at(tmp_path, clock=clock)
    exhausted_store.store.bind_finite_control_context(exhausted_context)
    with pytest.raises(StateConflict, match="cap"):
        _arm(exhausted_store, exhausted_context)
    assert _table_counts(runtime.store.path)["events"] == released_before["events"]

    # cap > spent arms and preserves the counted history
    counting_context = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            cap=2,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    counting_store = Runtime.at(tmp_path, clock=clock)
    counting_store.store.bind_finite_control_context(counting_context)
    event = _arm(counting_store, counting_context)
    status = runtime.jobs.finite_cycle_status(root.job_id)
    assert status is not None
    assert status["arm_event_id"] == event.event_id
    assert status["spent"] == 1
    assert status["remaining"] == 1
    assert status["exhausted"] is False
    assert status["expired"] is False
    assert status["halt_reason"] is None

    # a cancelled (terminal) root cannot be armed, and arming never
    # resurrects it; the already armed root still replays its exact event
    # through the store bound to that context.
    terminal_owner = Runtime.at(tmp_path, clock=clock)
    terminal_envelope, terminal_root = _finite_root(
        terminal_owner, "CEO-FINITE-ARM-TERM-001"
    )
    terminal_owner.jobs.cancel_job(terminal_root.job_id)
    terminal_context = _issue(
        _bound_definition(
            terminal_root,
            terminal_envelope,
            runtime=terminal_owner,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    terminal_store = Runtime.at(tmp_path, clock=clock)
    terminal_store.store.bind_finite_control_context(terminal_context)
    with pytest.raises(StateConflict, match="terminal"):
        _arm(terminal_store, terminal_context)
    cancelled_before = _table_counts(runtime.store.path)
    replay_after_terminal = _arm(counting_store, counting_context)
    assert replay_after_terminal == event
    assert _table_counts(runtime.store.path) == cancelled_before
    final_status = runtime.jobs.finite_cycle_status(root.job_id)
    assert final_status is not None
    assert final_status["spent"] == 1
    assert final_status["policy"]["control_attestation_digest"] == ATTESTATION_A


# ---------------------------------------------------------------------------
# 5. stored payload / event identity tamper refuses on load and replay
# ---------------------------------------------------------------------------


def _armed_runtime(tmp_path: Path, clock: MutableClock):
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-TAMPER-001")
    definition = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )
    context = _issue(definition)
    runtime.store.bind_finite_control_context(context)
    event = _arm(runtime, context)
    return runtime, envelope, root, definition, event


def _tampered_copy(base: Path, name: str, mutate) -> Path:
    target = base.parent / f"tampered-{name}"
    shutil.copytree(base, target)
    connection = sqlite3.connect(target / "data" / "control_plane" / "executive.sqlite3")
    try:
        # The immutable-events triggers are production law and stay intact in
        # every real database.  Only inside this disposable copied database
        # are they suspended to construct the corrupt row, and the EXACT
        # original trigger DDL is restored before any Runtime opens it, so
        # schema verification still sees the genuine guards.
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='events'"
        ).fetchall()
        for trigger_name, trigger_sql in triggers:
            connection.execute(f'DROP TRIGGER "{trigger_name}"')
        try:
            mutate(connection)
        finally:
            for _, trigger_sql in triggers:
                connection.execute(trigger_sql)
        connection.commit()
    finally:
        connection.close()
    return target


def test_finite_arm_stored_event_tamper_refuses_on_load_and_replay(tmp_path):
    base = tmp_path / "armed"
    base.mkdir()
    clock = MutableClock(1_800_200_000_000)
    runtime, envelope, root, definition, event = _armed_runtime(base, clock)
    command_id = event.command_id

    def rewrite_payload(mutator):
        def mutate(connection):
            row = connection.execute(
                "SELECT payload_json FROM events WHERE command_id=?",
                (command_id,),
            ).fetchone()
            payload = json.loads(row[0])
            mutator(payload)
            connection.execute(
                "UPDATE events SET payload_json=? WHERE command_id=?",
                (_canonical(payload), command_id),
            )

        return mutate

    def set_column(column: str, value):
        def mutate(connection):
            connection.execute(
                f"UPDATE events SET {column}=? WHERE command_id=?",
                (value, command_id),
            )

        return mutate

    cases = {
        "payload-pin": rewrite_payload(
            lambda payload: payload.update(intent_fingerprint="0" * 64)
        ),
        "payload-policy-pin": rewrite_payload(
            lambda payload: payload.update(coo_policy_sha256="0" * 64)
        ),
        "payload-root": rewrite_payload(
            lambda payload: payload.update(root_job_id="JOB-999")
        ),
        "payload-cap": rewrite_payload(
            lambda payload: payload.update(max_total_attempts=339)
        ),
        "payload-expiry": rewrite_payload(
            lambda payload: payload.update(expires_at_ms=clock.value + 1)
        ),
        "payload-policy-digest": rewrite_payload(
            lambda payload: payload.update(policy_digest="0" * 64)
        ),
        "payload-command": rewrite_payload(
            lambda payload: payload.update(command_id="arm-coo-root:x:y")
        ),
        "payload-schema": rewrite_payload(
            lambda payload: payload.update(schema_version="mastermind.coo_finite_drive/v2")
        ),
        "payload-extra-key": rewrite_payload(
            lambda payload: payload.update(extra="x")
        ),
        "payload-noncanonical": lambda connection: connection.execute(
            "UPDATE events SET payload_json=? WHERE command_id=?",
            (json.dumps(event.payload, indent=1), command_id),
        ),
        "column-command": set_column("command_id", "arm-coo-root:rewritten:0"),
        "column-aggregate": set_column("aggregate_id", "JOB-999"),
        "column-job": set_column("job_id", "JOB-999"),
        "column-actor": set_column("actor", "operator"),
        "column-attempt": set_column("attempt_id", "ATT-0001"),
    }

    for name, mutate in cases.items():
        target = _tampered_copy(base, name, mutate)
        reader = Runtime.at(target, clock=clock)
        with pytest.raises(StateConflict):
            reader.jobs.finite_cycle_status(root.job_id)
        replayer = Runtime.at(target, clock=clock)
        replay_context = _issue(definition)
        replayer.store.bind_finite_control_context(replay_context)
        with pytest.raises(StateConflict):
            _arm(replayer, replay_context)

    # exact unarmed status control
    clean = Runtime.at(base, clock=clock)
    assert clean.jobs.finite_cycle_status(root.job_id) is not None
    unarmed_envelope, unarmed_root = _finite_root(
        clean, "CEO-FINITE-ARM-UNARMED-001"
    )
    assert clean.jobs.finite_cycle_status(unarmed_root.job_id) is None

    # legacy Runtime behavior control: ordinary jobs keep working and never arm
    _register(clean)
    legacy = clean.jobs.create_job("legacy ordinary job")
    assert legacy.orchestration_role is None
    legacy_context = _issue(
        _bound_definition(
            unarmed_root,
            unarmed_envelope,
            runtime=clean,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    clean.store.bind_finite_control_context(legacy_context)
    with pytest.raises(StateConflict):
        clean.jobs.arm_finite_cycle(legacy.job_id, owner_issued_policy=legacy_context)
    assert clean.jobs.finite_cycle_status(legacy.job_id) is None
    assert clean.jobs.get_job(legacy.job_id) is not None


# ---------------------------------------------------------------------------
# 6. frozen context and store binding laws
# ---------------------------------------------------------------------------


def test_finite_control_context_freeze_and_store_binding_laws(tmp_path):
    clock = MutableClock(1_800_300_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-FREEZE-001")
    definition = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )
    context = _issue(definition)

    # input mapping mutation cannot rewrite the frozen context
    mutated_input = dict(definition)
    mutated_input["max_total_attempts"] = 1
    mutated_input["phase"] = "admission_only"
    assert _canonical(context.definition) == _canonical(definition)
    exposed = context.definition
    exposed["max_total_attempts"] = 1
    exposed["control_attestation_digest"] = "0" * 64
    assert _canonical(context.definition) == _canonical(definition)

    # equality follows the complete frozen definition
    assert context == _issue(definition)
    assert context != _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            cap=339,
            expires_at_ms=clock.value + 3_600_000,
        )
    )

    runtime.store.bind_finite_control_context(context)
    # idempotent rebind of the exact complete definition
    runtime.store.bind_finite_control_context(_issue(definition))
    # rebinding a different observation refuses on the same store
    with pytest.raises(StateConflict):
        runtime.store.bind_finite_control_context(
            _issue(
                _bound_definition(
                    root,
                    envelope,
                    runtime=runtime,
                    attestation=ATTESTATION_B,
                    expires_at_ms=clock.value + 3_600_000,
                )
            )
        )
    # rebinding a different phase refuses on the same store
    with pytest.raises(StateConflict):
        runtime.store.bind_finite_control_context(
            _issue(
                _admission_definition(
                    root, envelope, runtime=runtime,
                    expires_at_ms=clock.value + 3_600_000,
                )
            )
        )
    # rebinding a non-context object refuses
    with pytest.raises(StateConflict):
        runtime.store.bind_finite_control_context(dict(definition))

    # the frozen definition still arms through the same bound store
    event = _arm(runtime, context)
    assert event.payload["max_total_attempts"] == 340

    # a fresh restarted store may bind a newly issued qualified context
    fresh = Runtime.at(tmp_path, clock=clock)
    renewed = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            attestation=ATTESTATION_B,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    fresh.store.bind_finite_control_context(renewed)
    replay = _arm(fresh, renewed)
    assert replay == event


# ---------------------------------------------------------------------------
# 7. narrow correction regressions: phase shape, binding law, deadline clock
# ---------------------------------------------------------------------------


def test_finite_control_phase_selects_the_exact_closed_shape(tmp_path):
    """The closed key set follows the declared phase at issue time."""

    clock = MutableClock(1_800_400_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-PHASE-001")
    bound = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )

    # admission_only plus the three bound-only keys is drift, not admission
    admission_with_bound_keys = dict(bound)
    admission_with_bound_keys["phase"] = "admission_only"
    with pytest.raises(StateConflict):
        _issue(admission_with_bound_keys)

    # bound missing all three bound-only keys is drift, not a lean bound wire
    bound_missing_bound_keys = {
        key: value
        for key, value in _admission_definition(
            root, envelope, runtime=runtime
        ).items()
    }
    bound_missing_bound_keys["phase"] = "bound"
    with pytest.raises(StateConflict):
        _issue(bound_missing_bound_keys)

    # the two exact phase shapes still issue
    admission = _issue(
        _admission_definition(
            root, envelope, runtime=runtime,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    assert admission.definition["phase"] == "admission_only"
    assert set(admission.definition) == (
        set(STABLE_PIN_KEYS)
        | {"schema_version", "mode", "phase", "control_attestation_digest"}
    )
    assert _issue(bound).definition["phase"] == "bound"


@pytest.mark.parametrize("success", [False, True])
def test_finite_control_binding_never_retargets_after_arm_attempt(tmp_path, success):
    """A store binding refuses a different definition after any attempt."""

    clock = MutableClock(1_800_500_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-BIND-001")
    definition = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )
    context = _issue(definition)
    runtime.store.bind_finite_control_context(context)

    if success:
        event = _arm(runtime, context)
        assert event.payload["control_attestation_digest"] == ATTESTATION_A
    else:
        # even a refused attempt (wrong root) exercises the binding
        with pytest.raises(StateConflict):
            runtime.jobs.arm_finite_cycle("WRONG", owner_issued_policy=context)

    before = _table_counts(runtime.store.path)
    changed_observation = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            attestation=ATTESTATION_B,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    with pytest.raises(StateConflict):
        runtime.store.bind_finite_control_context(changed_observation)
    changed_budget = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            cap=339,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    with pytest.raises(StateConflict):
        runtime.store.bind_finite_control_context(changed_budget)
    # the exact complete definition still rebinds idempotently
    runtime.store.bind_finite_control_context(_issue(definition))
    assert _table_counts(runtime.store.path) == before

    # a fresh store over the same database may bind the new observation
    fresh = Runtime.at(tmp_path, clock=clock)
    fresh.store.bind_finite_control_context(changed_observation)
    if success:
        # stable-equal replay returns the original event and attestation
        replay = _arm(fresh, changed_observation)
        assert replay.payload["control_attestation_digest"] == ATTESTATION_A


def test_finite_arm_replay_requires_the_context_bound_to_that_store(tmp_path):
    """Exact replay refuses an old context on a store bound to a new one."""

    clock = MutableClock(1_800_600_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-RCTX-001")
    definition = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )
    context = _issue(definition)
    runtime.store.bind_finite_control_context(context)
    event = _arm(runtime, context)

    renewed = _issue(
        _bound_definition(
            root,
            envelope,
            runtime=runtime,
            attestation=ATTESTATION_B,
            expires_at_ms=clock.value + 3_600_000,
        )
    )
    fresh = Runtime.at(tmp_path, clock=clock)
    fresh.store.bind_finite_control_context(renewed)
    # the old context must refuse even though the command already exists
    with pytest.raises(StateConflict):
        _arm(fresh, context)
    # the historical arm is untouched and replays via the bound context
    status = fresh.jobs.finite_cycle_status(root.job_id)
    assert status is not None and status["arm_event_id"] == event.event_id
    assert status["policy"]["control_attestation_digest"] == ATTESTATION_A
    replay = _arm(fresh, renewed)
    assert replay == event
    assert replay.payload["control_attestation_digest"] == ATTESTATION_A


def test_finite_arm_deadline_sampled_inside_the_write_transaction(tmp_path):
    """Cutoff crossed during lock acquisition refuses with zero writes."""

    clock = MutableClock(1_800_700_000_000)
    runtime = Runtime.at(tmp_path, clock=clock)
    envelope, root = _finite_root(runtime, "CEO-FINITE-ARM-DEAD-001")
    definition = _bound_definition(
        root, envelope, runtime=runtime, expires_at_ms=clock.value + 3_600_000
    )
    context = _issue(definition)
    runtime.store.bind_finite_control_context(context)

    transaction = runtime.store.transaction

    @contextmanager
    def delayed():
        with transaction() as connection:
            # the clock crosses the cutoff only AFTER the genuine write
            # transaction has acquired its SQLite lock
            clock.value = definition["expires_at_ms"]
            yield connection

    runtime.store.transaction = delayed
    before = _table_counts(runtime.store.path)
    with pytest.raises(StateConflict):
        _arm(runtime, context)
    assert _table_counts(runtime.store.path) == before
    assert runtime.jobs.finite_cycle_status(root.job_id) is None

    # the same wrapper cannot age out an exact replay: restore the clock,
    # arm without the wrapper, then replay across the delayed boundary
    clock.value = 1_800_700_000_000
    runtime.store.transaction = transaction
    event = _arm(runtime, context)
    runtime.store.transaction = delayed
    replay = _arm(runtime, context)
    assert replay == event
    runtime.store.transaction = transaction
