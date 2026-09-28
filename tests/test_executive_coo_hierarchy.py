"""Narrow regressions for COO policy pin selection and root/planner creation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path

import pytest

from control_plane.ceo_intent import (
    INTENT_SCHEMA_V2,
    RECEIPT_SCHEMA_V2,
    submit_intent,
)
from control_plane.executive_coo_policy import (
    EXPECTED_POLICY_SHA256,
    EXPECTED_V1_POLICY_SHA256,
    CooCyclePolicy,
    load_pinned_coo_cycle_policy,
)
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_runtime import (
    COO_DOMAIN_EXECUTION_PROFILE,
    ExecutionCapabilityRegistry,
    _coo_domain_admitted,
    _coo_domain_row,
    _normalise_constraints,
    orchestration_digest,
)
from control_plane.executive_authority import ExecutiveAuthorityPolicy


_MALFORMED_DELEGATION_DIGESTS = [
    None,
    True,
    False,
    1,
    0,
    1.5,
    [],
    {},
    "",
    "A" * 64,
    "a" * 63,
    "a" * 65,
    "a" * 64 + " ",
    " " + "a" * 64,
    "a" * 64 + "\n",
    "g" * 64,
    "z" * 64,
    "0" * 63 + "-",
]


def _expected_delegation_scope_digest(root_job_id: str) -> str:
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    return orchestration_digest(
        {
            "schema_version": "mastermind.coo_domain_delegation/v1",
            "root_job_id": root_job_id,
            "authority_policy_sha256": ExecutiveAuthorityPolicy.load().sha256,
            "execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
            "execution_profile_digest": profile.profile_digest,
            "capability_policy_sha256": registry.policy_digest,
            "remaining_depth": 1,
        }
    )


def _v2_intent(**overrides):
    value = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-R3A-HIERARCHY-001",
        "actor": "ceo-sol",
        "objective": "Create one inert aggregation root and planner.",
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


def _source(source_id: str) -> dict[str, str]:
    return {
        "schema_version": "mastermind.executive_orchestration_provenance_source/v1",
        "creator": "coo_cycle",
        "source_id": source_id,
        "source_digest": hashlib.sha256(source_id.encode()).hexdigest(),
    }


def test_new_root_and_planner_create_before_admission_use_canonical_policy(tmp_path):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(runtime, _v2_intent())
    root = runtime.jobs.get_job(receipt["job_id"])
    canonical = CooCyclePolicy.load()

    assert receipt["schema"] == RECEIPT_SCHEMA_V2
    assert root is not None
    assert root.orchestration_role == "aggregation"
    assert root.parent_job_id is None and root.root_job_id == root.job_id
    assert root.depth == 0
    assert canonical.schema_version == 2
    assert canonical.max_depth == 2
    assert canonical.policy_sha256 == EXPECTED_POLICY_SHA256
    assert [
        event
        for event in runtime.events.list_events(job_id=root.job_id)
        if event.event_type == "COO_PLAN_ADMITTED"
    ] == []

    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    assert planner.orchestration_role == "plan"
    assert planner.parent_job_id == root.job_id
    assert planner.depth == 1
    assert planner.attempt_limit == min(
        root.attempt_limit, canonical.max_attempts_per_orchestration_job
    )
    assert [
        event
        for event in runtime.events.list_events(job_id=root.job_id)
        if event.event_type == "COO_PLAN_ADMITTED"
    ] == []


def test_planner_create_does_not_demand_nonexistent_admission(tmp_path):
    runtime = Runtime.at(tmp_path)
    receipt = submit_intent(
        runtime, _v2_intent(intent_id="CEO-R3A-HIERARCHY-PLANNER")
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    with pytest.raises(StateConflict, match="command-aware COO cycle"):
        runtime.jobs.create_job(
            "forged planner",
            parent_job_id=root.job_id,
            requested_authorities=["READ"],
            constraints={"cost_class": "small"},
            attempt_limit=2,
            command_id=f"coo-cycle:{root.job_id}:create-planner:forged",
            orchestration_role="plan",
            orchestration_provenance=_source("planner-forged"),
        )
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    replay = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    assert replay.job_id == planner.job_id
    assert [
        event
        for event in runtime.events.list_events(job_id=root.job_id)
        if event.event_type == "COO_PLAN_ADMITTED"
    ] == []


def test_admitted_v1_pin_remains_exact_under_installed_v2_source():
    policy = load_pinned_coo_cycle_policy(
        1, policy_sha256=EXPECTED_V1_POLICY_SHA256
    )
    current = CooCyclePolicy.load()
    assert current.schema_version == 2
    assert current.max_depth == 2
    assert policy.schema_version == 1
    assert policy.max_depth == 1
    assert policy.policy_sha256 == EXPECTED_V1_POLICY_SHA256
    assert policy.policy_sha256 != current.policy_sha256
    assert policy.source_sha256 == current.source_sha256
    assert policy.allowed_child_cost_classes == current.allowed_child_cost_classes


class TestCycleDomainCreationAndConsumptionSealBehavior:
    """Behavioral coverage for domain creation ancestry and fail-closed seal."""

    def test_create_cycle_domain_has_root_domain_ancestry_without_attribute_error(
        self, tmp_path
    ):
        runtime = Runtime.at(tmp_path)
        receipt = submit_intent(
            runtime, _v2_intent(intent_id="CEO-R4C-DOMAIN-CREATE")
        )
        root = runtime.jobs.get_job(receipt["job_id"])
        assert root is not None
        # Must not raise the inherited ExecutiveAuthorityPolicy AttributeError.
        domain = runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
        assert domain.job_id != root.job_id
        assert domain.orchestration_role == "plan"
        assert domain.parent_job_id == root.job_id
        assert domain.root_job_id == root.job_id
        assert domain.depth == 1
        assert domain.owner_seat == "coo"
        # The delegation envelope must survive constraint normalization and be
        # observable back through the admitted-domain lookup; ancestry alone is
        # not evidence that the domain is usable.
        expected_digest = _expected_delegation_scope_digest(root.job_id)
        with runtime.store.read() as connection:
            root_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()
            domain_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (domain.job_id,)
            ).fetchone()
            admitted = _coo_domain_row(connection, root_row, required=True)
        persisted = json.loads(str(domain_row["constraints_json"]))
        assert persisted["delegation_scope_digest"] == expected_digest
        assert admitted["job_id"] == domain.job_id
        assert _coo_domain_admitted(domain_row, allow_disabled=True) is True

    @staticmethod
    def _event_count(runtime) -> int:
        with runtime.store.transaction() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    @staticmethod
    def _sealed_count(runtime) -> int:
        with runtime.store.transaction() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM events "
                    "WHERE event_type='COO_DOMAIN_CONSUMPTION_SEALED'"
                ).fetchone()[0]
            )

    def test_parent_only_seal_refuses_with_matching_candidate_evidence(
        self, tmp_path
    ):
        runtime = Runtime.at(tmp_path)
        receipt = submit_intent(
            runtime, _v2_intent(intent_id="CEO-R4C-SEAL-REFUSE")
        )
        root = runtime.jobs.get_job(receipt["job_id"])
        assert root is not None
        runtime.jobs.create_cycle_domain(
            root.job_id,
            command_id=f"coo-cycle:{root.job_id}:create-domain:0",
        )
        fabricated_attempt_id = "ATT-" + "0" * 32
        # Fabricated matching OHF candidate evidence for the exact attempt the
        # caller reports.  Inserted outside the runtime's FK-checked writer so
        # the adversarial evidence exists regardless of attempt lifecycle.
        connection = sqlite3.connect(str(runtime.store.path))
        try:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute(
                "INSERT INTO events("
                "aggregate_type,aggregate_id,sequence,event_type,command_id,"
                "actor,job_id,attempt_id,payload_json,created_at_ms"
                ") VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    "attempt",
                    fabricated_attempt_id,
                    1,
                    "OHF_CANDIDATE_RESULT_RECORDED",
                    f"fabricated-candidate:{fabricated_attempt_id}",
                    "coo",
                    root.job_id,
                    fabricated_attempt_id,
                    '{"schema_version":"mastermind.ohf_candidate/v1"}',
                    runtime.store.now_ms(),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        with runtime.store.transaction() as probe:
            assert (
                int(
                    probe.execute(
                        "SELECT COUNT(*) FROM events "
                        "WHERE event_type='OHF_CANDIDATE_RESULT_RECORDED' "
                        "AND attempt_id=?",
                        (fabricated_attempt_id,),
                    ).fetchone()[0]
                )
                == 1
            )
        before = self._event_count(runtime)
        with pytest.raises(
            StateConflict,
            match="observed subsequent domain-consumption turn integration",
        ):
            runtime.jobs.seal_cycle_domain_consumption(
                root.job_id,
                domain_attempt_id=fabricated_attempt_id,
                observation={
                    "schema_version": "mastermind.executive_coo_domain_consumption/v1",
                    "root_job_id": root.job_id,
                    "domain_job_id": "JOB-002",
                    "domain_attempt_id": fabricated_attempt_id,
                    "consumption_projection_digest": "a" * 64,
                    "consumed_result": "caller text",
                },
                command_id=(
                    f"coo-cycle:{root.job_id}:domain-consumption:"
                    f"{fabricated_attempt_id}"
                ),
            )
        assert self._event_count(runtime) == before
        assert self._sealed_count(runtime) == 0


class TestDomainDelegationDigestPersistence:
    """R4F: the created domain's delegation envelope must persist and reload."""

    def test_persisted_delegation_digest_survives_reopen_lookup_and_replay(
        self, tmp_path
    ):
        runtime = Runtime.at(tmp_path)
        receipt = submit_intent(
            runtime, _v2_intent(intent_id="CEO-R4F-DOMAIN-PERSIST")
        )
        root = runtime.jobs.get_job(receipt["job_id"])
        assert root is not None
        command_id = f"coo-cycle:{root.job_id}:create-domain:0"
        domain = runtime.jobs.create_cycle_domain(
            root.job_id, command_id=command_id
        )

        expected_digest = _expected_delegation_scope_digest(root.job_id)
        assert re.fullmatch(r"[0-9a-f]{64}", expected_digest) is not None
        assert domain.job_id != root.job_id

        with runtime.store.read() as connection:
            domain_row = connection.execute(
                "SELECT constraints_json FROM jobs WHERE job_id=?",
                (domain.job_id,),
            ).fetchone()
        persisted = json.loads(str(domain_row["constraints_json"]))
        # Exact closed-material identity, not merely a well-shaped digest.
        registry = ExecutionCapabilityRegistry.load()
        profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
        assert persisted["delegation_scope_digest"] == expected_digest
        assert persisted["remaining_depth"] == 1
        assert persisted["execution_profile_id"] == profile.profile_id
        assert persisted["execution_profile_digest"] == profile.profile_digest
        assert persisted["capability_policy_version"] == registry.policy_version
        assert persisted["capability_policy_digest"] == registry.policy_digest

        # Reopen the same DB: the persisted envelope must still admit the domain.
        reopened = Runtime.at(tmp_path)
        with reopened.store.read() as connection:
            root_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()
            admitted = _coo_domain_row(connection, root_row, required=True)
            domain_rows = connection.execute(
                "SELECT job_id FROM jobs WHERE root_job_id=? AND job_id<>? "
                "AND depth=1 AND orchestration_role='plan'",
                (root.job_id, root.job_id),
            ).fetchall()
        assert len(domain_rows) == 1
        assert admitted["job_id"] == domain.job_id
        assert _coo_domain_admitted(admitted, allow_disabled=True) is True
        reloaded = json.loads(str(admitted["constraints_json"]))
        assert reloaded["delegation_scope_digest"] == expected_digest

        # Idempotent replay on the reopened DB returns the same Job, no duplicate.
        replay = reopened.jobs.create_cycle_domain(
            root.job_id, command_id=command_id
        )
        assert replay.job_id == domain.job_id
        with reopened.store.read() as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=? "
                    "AND job_id<>? AND depth=1 AND orchestration_role='plan'",
                    (root.job_id, root.job_id),
                ).fetchone()[0]
            )
        assert count == 1

    def test_absent_delegation_digest_leaves_legacy_jobs_unchanged(self, tmp_path):
        normalized = _normalise_constraints({"cost_class": "small"})
        assert "delegation_scope_digest" not in normalized

        runtime = Runtime.at(tmp_path)
        job = runtime.jobs.create_job(
            "legacy job without a delegation envelope",
            constraints={"cost_class": "small"},
            command_id="r4f-legacy-absent-delegation",
        )
        with runtime.store.read() as connection:
            row = connection.execute(
                "SELECT constraints_json FROM jobs WHERE job_id=?", (job.job_id,)
            ).fetchone()
        persisted = json.loads(str(row["constraints_json"]))
        assert "delegation_scope_digest" not in persisted

    def test_valid_delegation_digest_is_preserved_exactly(self):
        digest = "0123456789abcdef" * 4
        normalized = _normalise_constraints({"delegation_scope_digest": digest})
        assert normalized["delegation_scope_digest"] == digest

    @pytest.mark.parametrize(
        "value", _MALFORMED_DELEGATION_DIGESTS, ids=repr
    )
    def test_malformed_present_delegation_digest_is_refused(self, value):
        with pytest.raises(StateConflict, match="delegation_scope_digest"):
            _normalise_constraints({"delegation_scope_digest": value})


# ---------------------------------------------------------------------------
# R6A: actual active-domain plan admission seam (test-only fixtures).
#
# These helpers mirror the test-only domain admission used by
# ``tests/test_executive_operator_supervisor.py`` but seed the admitted domain
# child via ``create_cycle_domain`` (so it carries a genuine
# ``delegation_scope_digest`` and provenance), not via ``create_cycle_planner``
# with an overridden operator profile.  The supervisor fixture in
# ``test_executive_operator_supervisor.py`` is intentionally renamed-planner
# scope; these helpers narrow the seam so the Runtime seam is exercised against
# the actual domain child the production API mints.
# ---------------------------------------------------------------------------


from control_plane.executive_agent_capabilities import (  # noqa: E402
    ExecutionCapabilityRegistry as _ExecutionCapabilityRegistry,
)
from control_plane.executive_orchestration_result import (  # noqa: E402
    RESULT_SCHEMA as _RESULT_SCHEMA,
    RawRoleResultObservation as _RawRoleResultObservation,
    canonical_bytes as _canonical_bytes,
)
from control_plane.executive_operator_harness_port import (  # noqa: E402
    CandidateResult as _CandidateResult,
)
from control_plane.operator_harness_contract import (  # noqa: E402
    AuthRealmFact as _AuthRealmFact,
    AuthRealmRequirement as _AuthRealmRequirement,
    CapabilityManifest as _CapabilityManifest,
    CheckpointObservation as _CheckpointObservation,
    EventCursor as _EventCursor,
    NativeHelperPolicy as _NativeHelperPolicy,
    NormalizedEvent as _NormalizedEvent,
    ObservedCapabilityIdentity as _ObservedCapabilityIdentity,
    ObservedHarnessAttestation as _ObservedHarnessAttestation,
    ObservedTriState as _ObservedTriState,
    ProcessIdentityObservation as _ProcessIdentityObservation,
    ProcessLiveness as _ProcessLiveness,
    ProfileValidation as _ProfileValidation,
    ProviderWriterState as _ProviderWriterState,
    ReconcileObservation as _ReconcileObservation,
    RequestedExecutionProfile as _RequestedExecutionProfile,
    SessionStartObservation as _SessionStartObservation,
    TurnRef as _TurnRef,
    TurnStartObservation as _TurnStartObservation,
    WorkspaceIdentity as _WorkspaceIdentity,
)
from control_plane.executive_operator_supervisor import (  # noqa: E402
    ExecutiveOperatorSupervisor as _ExecutiveOperatorSupervisor,
)
from control_plane.executive_orchestration_principal import (  # noqa: E402
    OSProcessCredentialObservation as _OSProcessCredentialObservation,
    ProviderHomeIdentityObservation as _ProviderHomeIdentityObservation,
)
from control_plane.executive_runtime import AttemptStatus as _AttemptStatus  # noqa: E402


class _R6AAdmittingRegistry:
    """Test-only proxy that admits the disabled COO domain profile shape.

    NOT production admission proof: production ``.resolve`` stays fail-closed
    and the shipped profile remains ``enabled=false``.  This proxy exists only
    so the typed supervisor fake can drive a real ``create_cycle_domain`` child
    through ``start_cycle_job`` for the post-claim admission seam.
    """

    def __init__(self, real: _ExecutionCapabilityRegistry) -> None:
        self._real = real
        self.profiles = real.profiles
        self.policy_version = real.policy_version
        self.policy_digest = real.policy_digest

    def resolve(self, profile_id: str):
        if profile_id == COO_DOMAIN_EXECUTION_PROFILE:
            return self.profiles[profile_id]
        return self._real.resolve(profile_id)

    def validate_disabled_profile_shape(self, profile_id: str) -> None:
        return self._real.validate_disabled_profile_shape(profile_id)


class _R6AFakeRegistryLoader:
    @staticmethod
    def load(*_args, **_kwargs):
        return _R6AAdmittingRegistry(_ExecutionCapabilityRegistry.load())


class _R6APromptSource:
    def _prompt(self, *_args):
        return "Produce the bounded execution plan."


def _r6a_setup_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "codex/r6a-domain"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "fixture@mastermind.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Mastermind Fixture"],
        cwd=workspace,
        check=True,
    )
    (workspace / "README.md").write_text("R6A fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True
    )
    return workspace


def _r6a_runtime_with_operator(runtime_path: Path) -> Runtime:
    runtime = Runtime.at(runtime_path)
    registry = _ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    runtime.workers.register_worker(
        "worker-r6a",
        provider="codex",
        account_label="worker-r6a@company",
        worker_type="fixture",
        capabilities=[],
        quota_classes={
            "codex-coo-operator": {
                "provider": "codex",
                "model": "gpt-test",
                "effort": "low",
                "cost_class": "small",
                "capabilities": [],
                "metadata": {
                    "routing_policy_version": "test-routing",
                    "execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
                    "execution_profile_digest": profile.profile_digest,
                    "capability_policy_version": registry.policy_version,
                    "capability_policy_digest": registry.policy_digest,
                    "harness_binary_digest": "a" * 64,
                    "harness_version": "0.147.0",
                },
            }
        },
    )
    return runtime


def _r6a_domain_envelope(job, attempt) -> str:
    """Canonical typed plan envelope used by the test-only domain adapter."""

    body = {
        "schema_version": _RESULT_SCHEMA,
        "job_id": job.job_id,
        "run_id": attempt.attempt_id,
        "worker_id": attempt.worker_id,
        "role": "plan",
        "status": "COMPLETED",
        "role_result": {
            "schema_version": "mastermind.execution_plan/v1",
            "root_job_id": job.root_job_id,
            "plan_attempt_id": attempt.attempt_id,
            "steps": [
                {
                    "ordinal": 0,
                    "step_id": "r6a-step-1",
                    "objective": "Perform one bounded read-only follow-up.",
                    "business_impact": "routine",
                    "review_required": False,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                }
            ],
        },
        "summary": "R6A seeded typed plan.",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
    return _canonical_bytes(body).decode("utf-8")


def _r6a_attestation(profile) -> _ObservedHarnessAttestation:
    """Typed observed attestation mirroring an accepted launch for ``profile``."""

    observed_capabilities = tuple(
        _ObservedCapabilityIdentity(
            kind=item.kind,
            name=item.name,
            skill_content_digest=item.skill_content_digest,
            tool_schema_digest=item.tool_schema_digest,
            mcp_server_identity=item.mcp_server_identity,
            mcp_server_version=item.mcp_server_version,
            mcp_auth_status=item.mcp_auth_status,
            resource_contract_digest=item.resource_contract_digest,
        )
        for item in profile.capabilities.required
    )
    return _ObservedHarnessAttestation(
        served_model=profile.requested_model,
        harness_version=profile.harness_version,
        harness_binary_digest=profile.harness_binary_digest,
        capabilities=observed_capabilities,
        effective_skills=(),
        effective_mcp=tuple(
            item.name for item in observed_capabilities if item.kind == "mcp_server"
        ),
        effective_plugins_or_apps=(),
        sandbox_state=profile.sandbox_policy,
        approval_state=profile.approval_policy,
        network_state=profile.network_policy,
        effective_config_digest=profile.expected_config_digest or "d" * 64,
        auth=_AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=(
            _ObservedTriState.VERIFIED
            if profile.native_helper_policy
            is _NativeHelperPolicy.PARENT_READ_ONLY_CEILING
            else _ObservedTriState.FALSE
        ),
    )


class _R6ADomainAdapter:
    """Typed fake that mimics the supervisor's external-effect surface."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.provider_session_id = "SESSION-R6A-DOMAIN"
        self.native_turn_id = "NATIVE-R6A-DOMAIN"
        self.process = _ProcessIdentityObservation(
            4101, 4101, "start-4101", "boot-test"
        )
        self.begin_turn_calls = 0
        self.checkpoint_calls = 0
        self.requested: _RequestedExecutionProfile | None = None

    def _canonical_result(self, turn) -> str:
        attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
        assert attempt is not None
        job = self.runtime.jobs.get_job(attempt.job_id)
        assert job is not None
        return _r6a_domain_envelope(job, attempt)

    def start_session(self, **_kwargs):
        return _SessionStartObservation(self.provider_session_id, self.process)

    def observe_process_credentials(self, _generation):
        return _OSProcessCredentialObservation(
            {
                "pid": self.process.pid,
                "pgid": self.process.pgid,
                "process_start_identity": self.process.process_start_identity,
                "boot_id": self.process.boot_id,
            },
            "fixture-principal",
            os.getuid(),
        )

    def observe_provider_home_identity(self, _generation):
        return _ProviderHomeIdentityObservation(
            {
                "path": "/tmp/mastermind-r6a-provider-home",
                "device": 5,
                "inode": 6,
                "uid": os.getuid(),
                "gid": os.getgid(),
                "mode": 0o700,
            }
        )

    def validate_requested_profile(self, requested):
        self.requested = requested
        return _ProfileValidation(requested, True, ())

    def observed_attestation(self, _generation):
        assert self.requested is not None
        return _r6a_attestation(self.requested)

    def begin_turn(self, *, turn, **_kwargs):
        self.begin_turn_calls += 1
        return _TurnStartObservation(self.native_turn_id, True)

    def read_events(self, cursor, *, timeout_seconds):
        assert timeout_seconds > 0 and cursor.turn_id
        return (
            (
                _NormalizedEvent(
                    cursor.attempt_id,
                    cursor.session_epoch_id,
                    cursor.process_generation_id,
                    cursor.turn_id,
                    "turn.completed",
                    payload_redacted={"status": "complete"},
                ),
            ),
            _EventCursor(
                cursor.attempt_id,
                cursor.session_epoch_id,
                cursor.process_generation_id,
                local_sequence=1,
                turn_id=cursor.turn_id,
            ),
        )

    def collect_candidate_result(self, turn):
        attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
        assert attempt is not None
        value = self._canonical_result(turn)
        return _CandidateResult(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            "e" * 64,
            value,
        )

    def observe_raw_role_result(self, turn):
        value = self._canonical_result(turn)
        return _RawRoleResultObservation(
            attempt_id=turn.attempt_id,
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            turn_id=turn.turn_id,
            provider_session_id=self.provider_session_id,
            provider_native_turn_id=self.native_turn_id,
            provider_turn_artifact_digest="e" * 64,
            canonical_result_json=value,
            canonical_result_digest=hashlib.sha256(value.encode()).hexdigest(),
            canonical_result_byte_length=len(value.encode()),
        )

    def checkpoint(self, *, operation_id, generation):
        self.checkpoint_calls += 1
        return _CheckpointObservation(
            checkpoint_candidate={"sealed": "initial-plan", "phase": "postclaim"}
        )

    def graceful_stop(self, _generation, **_kwargs):
        return _ReconcileObservation(
            _ProcessLiveness.PROVEN_DEAD,
            self.process,
            False,
            _ProviderWriterState.RELEASED,
            self.provider_session_id,
            "d" * 64,
        )

    def cancel(self, _generation, **_kwargs):
        return _ReconcileObservation(
            _ProcessLiveness.PROVEN_DEAD,
            self.process,
            False,
            _ProviderWriterState.RELEASED,
            self.provider_session_id,
            "d" * 64,
        )

    def reconcile(self, _generation):
        return _ReconcileObservation(
            _ProcessLiveness.ALIVE,
            self.process,
            True,
            _ProviderWriterState.HELD,
            self.provider_session_id,
            "d" * 64,
        )


def _r6a_submit_domain_root(
    tmp_path: Path,
) -> tuple[Runtime, "type[object]", "type[object]", Path]:
    """Submit a strict-v2 root and create its real COO domain child.

    Returns (runtime, root, domain, workspace) with the domain parent
    created but not yet dispatched (no active Attempt / plan seal).
    """

    workspace = _r6a_setup_workspace(tmp_path)
    runtime = _r6a_runtime_with_operator(tmp_path / "runtime")
    registry = _ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    binding = {
        "eligible_quota_classes": ["codex-coo", "codex-coo-default"],
        "provider": "codex",
        "model": "gpt-test",
        "effort": "low",
        "cost_class": "small",
        "base_sha": base_sha,
        "routing_policy_version": "test-routing",
        "execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "operator_eligible_quota_classes": ["codex-coo-operator"],
        "operator_provider": "codex",
        "operator_model": "gpt-test",
        "operator_effort": "low",
        "operator_cost_class": "small",
        "operator_routing_policy_version": "test-routing",
        "operator_execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
        "operator_execution_profile_digest": profile.profile_digest,
        "operator_capability_policy_version": registry.policy_version,
        "operator_capability_policy_digest": registry.policy_digest,
        "operator_harness_binary_digest": "a" * 64,
        "operator_harness_version": "0.147.0",
        "operator_harness_armed": True,
    }
    intent = _v2_intent(intent_id="CEO-R6A-DOMAIN-ADMISSION")
    intent["grounding"] = {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40}
    intent["execution_contract"] = {
        "requested_authorities": ["READ"],
        "branch": "codex/r6a-domain",
        "worktree": str(workspace),
        "attempt_limit": 2,
    }
    receipt = submit_intent(
        runtime,
        intent,
        workspace_root=workspace.parent,
        execution_binding=binding,
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    domain = runtime.jobs.create_cycle_domain(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-domain:0",
    )


    return runtime, root, domain, workspace


def _r6a_seed_active_domain(
    tmp_path: Path, *, monkeypatch
) -> tuple[
    Runtime,
    "type[object]",
    "type[object]",
    _R6ADomainAdapter,
    str,
]:
    """Submit intent → create real domain → dispatch via supervisor (typed fake).

    Returns (runtime, root, domain, adapter, dispatch_command_id).  The
    domain Attempt is in CHECKPOINTED state with a sealed plan envelope.
    """

    import control_plane.executive_operator_supervisor as operator_supervisor_module

    runtime, root, domain, _workspace = _r6a_submit_domain_root(tmp_path)

    monkeypatch.setattr(
        operator_supervisor_module,
        "ExecutionCapabilityRegistry",
        _R6AFakeRegistryLoader,
    )
    adapters: list[_R6ADomainAdapter] = []

    def factory(loader):
        adapter = _R6ADomainAdapter(runtime)
        adapters.append(adapter)
        return adapter

    supervisor = _ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,
        prompt_source=_R6APromptSource(),
    )
    dispatch_command_id = (
        f"coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1"
    )
    outcome = asyncio.run(
        supervisor.start_cycle_job(domain.job_id, command_id=dispatch_command_id)
    )
    assert outcome.outcome == "ACTIVE"
    attempt = runtime.attempts.get_attempt(outcome.attempt.attempt_id)
    assert attempt is not None and attempt.status is _AttemptStatus.CHECKPOINTED
    # Refetch so the returned Job carries the dispatched (nonterminal)
    # current_attempt_id rather than the pre-dispatch snapshot.
    active_domain = runtime.jobs.get_job(domain.job_id)
    assert active_domain is not None
    assert active_domain.current_attempt_id == outcome.attempt.attempt_id
    return runtime, root, active_domain, adapters[0], dispatch_command_id


class TestActiveDomainPlanAdmissionSeam:
    """R6A: admit an actually-dispatched, nonterminal COO domain plan.

    The supervisor is independently APPROVED (23 supervisor tests).  These
    regressions exercise the Runtime seam that admits its observed nonterminal
    domain plan into the exact root's initial depth2 work wave without
    resurrecting the domain or minting a terminal receipt.
    """

    def test_actual_domain_plan_admission_creates_depth2_leaves_with_root_unchanged(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        runtime, root, domain, adapter, dispatch_command_id = _r6a_seed_active_domain(
            tmp_path, monkeypatch=monkeypatch
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        with runtime.store.read() as connection:
            root_before = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()
            domain_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (domain.job_id,)
            ).fetchone()
            domain_attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (domain_attempt_id,)
            ).fetchone()
            epoch_before = connection.execute(
                "SELECT * FROM harness_session_epochs WHERE attempt_id=?",
                (domain_attempt_id,),
            ).fetchone()
            generation_before = connection.execute(
                """
                SELECT g.* FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE e.attempt_id=?
                """,
                (domain_attempt_id,),
            ).fetchone()
        attempt_fence_before = int(domain_attempt["fence_generation"])
        epoch_id_before = epoch_before["session_epoch_id"]
        generation_id_before = generation_before["process_generation_id"]
        root_cancel_before = root_before["cancel_requested_at_ms"]

        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        leaves = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)

        assert len(leaves) == 1
        leaf = leaves[0]
        # A depth-2 work child sits directly under the admitted COO domain
        # (which remains the root's sole direct child), never under the root.
        assert leaf.parent_job_id == domain.job_id
        assert leaf.root_job_id == root.job_id
        assert leaf.orchestration_role == "work"
        assert leaf.depth == 2
        assert leaf.plan_attempt_id == domain_attempt_id
        assert leaf.plan_digest != ""
        assert leaf.requested_authorities == ["READ"]

        # Domain remains the sole root parent and is unchanged.
        with runtime.store.read() as connection:
            root_after = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()
            domain_after = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (domain.job_id,)
            ).fetchone()
            domain_attempt_after = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (domain_attempt_id,)
            ).fetchone()
            epoch_after = connection.execute(
                "SELECT * FROM harness_session_epochs WHERE attempt_id=?",
                (domain_attempt_id,),
            ).fetchone()
            generation_after = connection.execute(
                """
                SELECT g.* FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE e.attempt_id=?
                """,
                (domain_attempt_id,),
            ).fetchone()
            plan_admitted = connection.execute(
                "SELECT 1 FROM events WHERE event_type='COO_PLAN_ADMITTED' "
                "AND job_id=?",
                (root.job_id,),
            ).fetchone()

        # Root wide state preserved; no fresh budget or terminal fabrication.
        assert root_after["status"] == root.status
        assert root_after["attempt_count"] == root.attempt_count
        assert root_after["current_attempt_id"] == root.current_attempt_id
        assert root_after["cancel_requested_at_ms"] == root_cancel_before

        # Domain attempt: same identity, same fence, same epoch/generation.
        assert int(domain_attempt_after["fence_generation"]) == attempt_fence_before
        assert domain_after["status"] == domain.status
        assert domain_after["current_attempt_id"] == domain_attempt_id
        assert domain_after["status"] in {"RUNNING", "CHECKPOINTED"}
        assert epoch_after["session_epoch_id"] == epoch_id_before
        assert generation_after["process_generation_id"] == generation_id_before
        assert plan_admitted is not None

    def test_actual_domain_plan_admission_replay_returns_same_children_no_extra_events(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        runtime, root, domain, adapter, dispatch_command_id = _r6a_seed_active_domain(
            tmp_path, monkeypatch=monkeypatch
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None

        def _count(runtime) -> int:
            with runtime.store.transaction() as connection:
                return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])

        def _depth2_count(runtime) -> int:
            with runtime.store.read() as connection:
                return int(
                    connection.execute(
                        "SELECT COUNT(*) FROM jobs WHERE root_job_id=? "
                        "AND orchestration_role='work' AND depth=2",
                        (root.job_id,),
                    ).fetchone()[0]
                )

        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        first = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        events_after_first = _count(runtime)
        depth2_after_first = _depth2_count(runtime)

        second = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        events_after_second = _count(runtime)
        depth2_after_second = _depth2_count(runtime)

        # Replay must not create additional children, events, or provider turns.
        assert [leaf.job_id for leaf in second] == [leaf.job_id for leaf in first]
        assert events_after_second == events_after_first
        assert depth2_after_second == depth2_after_first
        assert adapter.begin_turn_calls == 1
        assert adapter.checkpoint_calls == 1

    def test_disabled_profile_domain_admission_remains_refused_for_ordinary_root(
        self, tmp_path: Path
    ) -> None:
        """Production refuse: ordinary runtime (no fake admission) cannot
        dispatch a disabled-profile domain, so admit_cycle_plan never sees
        one and the seal_cycle_domain_consumption refusal stays intact.
        """

        runtime = Runtime.at(tmp_path)
        receipt = submit_intent(runtime, _v2_intent(intent_id="CEO-R6A-REFUSE"))
        root = runtime.jobs.get_job(receipt["job_id"])
        assert root is not None
        # No domain child exists yet: the root has no children, so the existing
        # ``exactly one planner`` invariant refuses plan admission for it.
        with pytest.raises(StateConflict, match="exactly one planner"):
            runtime.jobs.admit_cycle_plan(
                root.job_id,
                command_id=f"coo-cycle:{root.job_id}:admit-plan:att-x",
            )

        # seal_cycle_domain_consumption remains unconditionally refused.
        with pytest.raises(
            StateConflict, match="domain consumption seal requires observed"
        ):
            runtime.jobs.seal_cycle_domain_consumption(
                root.job_id,
                domain_attempt_id="att-x",
                observation={"schema_version": "x"},
                command_id=f"coo-cycle:{root.job_id}:domain-consumption:att-x",
            )

    def test_actual_domain_plan_admission_readback_passes_validated_plan(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        runtime, root, domain, adapter, dispatch_command_id = _r6a_seed_active_domain(
            tmp_path, monkeypatch=monkeypatch
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)

        # Readback of the immutable admission must succeed against the same
        # active domain Attempt (no terminal fabrication in between).
        from control_plane.executive_runtime import _validated_plan_admission
        with runtime.store.read() as connection:
            root_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()
            admission, plan_body = _validated_plan_admission(connection, root_row)
        assert admission["root_job_id"] == root.job_id
        assert admission["plan_attempt_id"] == domain_attempt_id
        assert plan_body["plan_attempt_id"] == domain_attempt_id
        assert len(plan_body["steps"]) == 1
        assert plan_body["steps"][0]["step_id"] == "r6a-step-1"

    def test_actual_domain_plan_admission_refuses_wrong_command_and_absent_seal(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        runtime, root, domain, adapter, dispatch_command_id = _r6a_seed_active_domain(
            tmp_path, monkeypatch=monkeypatch
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None

        def _work_count() -> int:
            with runtime.store.read() as connection:
                return int(
                    connection.execute(
                        "SELECT COUNT(*) FROM jobs WHERE root_job_id=? "
                        "AND orchestration_role='work'",
                        (root.job_id,),
                    ).fetchone()[0]
                )

        def _event_count() -> int:
            with runtime.store.read() as connection:
                return int(
                    connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                )

        # A non-deterministic command_id must refuse before any child/effect.
        with pytest.raises(StateConflict, match="command_id is not deterministic"):
            runtime.jobs.admit_cycle_plan(
                root.job_id,
                command_id=f"coo-cycle:{root.job_id}:admit-plan:bogus",
            )
        assert _work_count() == 0
        assert adapter.begin_turn_calls == 1

        # DB evidence only (NOT missing-seal coverage): the one-seal-per-attempt
        # unique index itself refuses a second seal, before any Runtime guard.
        seal_before = _event_count()
        with pytest.raises(
            StateConflict, match="UNIQUE constraint failed: events.attempt_id"
        ):
            with runtime.store.transaction() as connection:
                connection.execute(
                    "INSERT INTO events("
                    "aggregate_type,aggregate_id,sequence,event_type,command_id,"
                    "actor,attempt_id,payload_json,created_at_ms"
                    ") VALUES('attempt',?,?,?,?,'coo',?,'{}',?)",
                    (
                        domain_attempt_id,
                        9001,
                        "ORCHESTRATION_ROLE_RESULT_SEALED",
                        f"r6b-duplicate-seal:{domain_attempt_id}",
                        domain_attempt_id,
                        1,
                    ),
                )
        assert _event_count() == seal_before

        # Genuine missing-seal coverage: an otherwise-valid *active* domain
        # whose exact result seal is absent.  Events are append-only, so this
        # isolated fixture lifts the delete guard only long enough to remove
        # this single seal, then reinstates it; every other identity row
        # (job, attempt, epoch, generation, admission) is left untouched.
        with runtime.store.transaction() as connection:
            delete_guard = str(
                connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type='trigger' "
                    "AND name='events_are_immutable_delete'"
                ).fetchone()[0]
            )
            connection.execute("DROP TRIGGER events_are_immutable_delete")
            connection.execute(
                "DELETE FROM events WHERE event_type="
                "'ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?",
                (domain_attempt_id,),
            )
            connection.execute(delete_guard)
            absent_seal_rows = int(
                connection.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type="
                    "'ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?",
                    (domain_attempt_id,),
                ).fetchone()[0]
            )
        assert absent_seal_rows == 0

        events_before = _event_count()
        turns_before = adapter.begin_turn_calls
        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        with pytest.raises(StateConflict, match="exact result seal"):
            runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        assert _work_count() == 0
        assert _event_count() == events_before
        assert adapter.begin_turn_calls == turns_before

    def test_actual_domain_plan_admission_refuses_stale_writer_generation(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        runtime, root, domain, adapter, dispatch_command_id = _r6a_seed_active_domain(
            tmp_path, monkeypatch=monkeypatch
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        with runtime.store.transaction() as connection:
            generation = connection.execute(
                """
                SELECT g.process_generation_id FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE e.attempt_id=?
                """,
                (domain_attempt_id,),
            ).fetchone()
            assert generation is not None
            connection.execute(
                "UPDATE process_generations SET ended_at_ms=1 "
                "WHERE process_generation_id=?",
                (generation["process_generation_id"],),
            )
        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        with pytest.raises(StateConflict, match="CURRENT writer generation"):
            runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        with runtime.store.read() as connection:
            work = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE root_job_id=? "
                "AND orchestration_role='work'",
                (root.job_id,),
            ).fetchone()[0]
            admitted = connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='COO_PLAN_ADMITTED' "
                "AND job_id=?",
                (root.job_id,),
            ).fetchone()[0]
        assert int(work) == 0
        assert int(admitted) == 0


# ---------------------------------------------------------------------------
# R7A: actual reviewed-leaf consumption projection (single executable slice).
#
# Reuses the R6A active-domain fixture (typed Supervisor fake + plan seal) but
# adjusts the typed plan to ``review_required=True`` BEFORE the adapter emits
# its sealed observation, dispatches the depth-2 work + review through the
# public OHF/worker APIs (no SQL-injected positive events), and asserts the
# exact reviewed consumption projection.  Refusals cover live work, live
# review, missing review, and same-principal review; each refusal path proves
# no new provider turn / child / event is minted.
# ---------------------------------------------------------------------------


from tests.test_executive_os_phase1fc import (  # noqa: E402
    _complete_ohf_role as _r7a_complete_ohf_role,
    _orchestration_profile as _r7a_orchestration_profile,
    _orchestration_attestation as _r7a_orchestration_attestation,
    _review_body as _r7a_review_body,
)


def _r7a_domain_envelope_review_required(job, attempt) -> str:
    """Canonical typed plan envelope with the single step marked review-required.

    Mirrors ``_r6a_domain_envelope`` exactly except for the closed
    ``review_required`` boolean on the typed step.  This is the smallest
    admissible variation that lets the depth-2 work/review wave reach an
    independent approval (root ``business_impact`` is ``material`` so v2
    admission would already require review; this keeps the wire explicit).
    """

    body = {
        "schema_version": _RESULT_SCHEMA,
        "job_id": job.job_id,
        "run_id": attempt.attempt_id,
        "worker_id": attempt.worker_id,
        "role": "plan",
        "status": "COMPLETED",
        "role_result": {
            "schema_version": "mastermind.execution_plan/v1",
            "root_job_id": job.root_job_id,
            "plan_attempt_id": attempt.attempt_id,
            "steps": [
                {
                    "ordinal": 0,
                    "step_id": "r6a-step-1",
                    "objective": "Perform one bounded read-only follow-up.",
                    "business_impact": "routine",
                    "review_required": True,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                }
            ],
        },
        "summary": "R7A seeded typed plan (review-required).",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
    return _canonical_bytes(body).decode("utf-8")


class _R7ADomainAdapter(_R6ADomainAdapter):
    """Typed Supervisor fake whose sealed plan carries ``review_required=True``."""

    def _canonical_result(self, turn):
        attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
        assert attempt is not None
        job = self.runtime.jobs.get_job(attempt.job_id)
        assert job is not None
        return _r7a_domain_envelope_review_required(job, attempt)


def _r7a_runtime_with_work_and_review_workers(
    runtime: Runtime, *, work_quota_class: str = "codex-coo"
) -> None:
    """Register distinct bounded work + review workers (no domain quota reuse).

    The operator ``worker-r6a`` already holds ``codex-coo-operator`` for the
    domain Attempt; this helper adds two further workers whose quota classes
    are drawn from the root's ``eligible_quota_classes`` and whose account
    labels, OS principals, and provider homes are disjoint — every dimension
    the independent-review probe requires later.  Their metadata mirrors the
    root constraint's execution/capability profile digests so the
    ``_capacity_matches_route`` admission probe admits them under the same
    strict-v2 binding the domain was created with.
    """

    registry = ExecutionCapabilityRegistry.load()
    profile = registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    route_metadata = {
        "routing_policy_version": "test-routing",
        "execution_profile_id": COO_DOMAIN_EXECUTION_PROFILE,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
    }
    runtime.workers.register_worker(
        "worker-r6a-work",
        provider="codex",
        account_label="worker-r6a-work@company",
        worker_type="fixture",
        capabilities=[],
        quota_classes={
            work_quota_class: {
                "provider": "codex",
                "model": "gpt-test",
                "effort": "low",
                "cost_class": "small",
                "capabilities": [],
                "metadata": dict(route_metadata),
            }
        },
    )
    runtime.workers.register_worker(
        "worker-r6a-review",
        provider="codex",
        account_label="worker-r6a-review@company",
        worker_type="fixture",
        capabilities=[],
        quota_classes={
            work_quota_class: {
                "provider": "codex",
                "model": "gpt-test",
                "effort": "low",
                "cost_class": "small",
                "capabilities": [],
                "metadata": dict(route_metadata),
            }
        },
    )


def _r7a_seed_active_domain_with_review(
    tmp_path: Path, *, monkeypatch
) -> tuple[
    Runtime,
    "type[object]",
    "type[object]",
    _R7ADomainAdapter,
    str,
]:
    """Submit intent → create real domain → dispatch typed review-required plan.

    Identical wiring to ``_r6a_seed_active_domain`` except the typed fake is
    the ``_R7ADomainAdapter`` variant so the sealed plan carries
    ``review_required=True``.  Returns (runtime, root, domain, adapter,
    dispatch_command_id) with the domain Attempt CHECKPOINTED and its initial
    turn + seal intact.
    """

    import control_plane.executive_operator_supervisor as operator_supervisor_module

    runtime, root, domain, _workspace = _r6a_submit_domain_root(tmp_path)

    monkeypatch.setattr(
        operator_supervisor_module,
        "ExecutionCapabilityRegistry",
        _R6AFakeRegistryLoader,
    )
    adapters: list[_R7ADomainAdapter] = []

    def factory(loader):
        adapter = _R7ADomainAdapter(runtime)
        adapters.append(adapter)
        return adapter

    supervisor = _ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,
        prompt_source=_R6APromptSource(),
    )
    dispatch_command_id = (
        f"coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1"
    )
    outcome = asyncio.run(
        supervisor.start_cycle_job(domain.job_id, command_id=dispatch_command_id)
    )
    assert outcome.outcome == "ACTIVE"
    attempt = runtime.attempts.get_attempt(outcome.attempt.attempt_id)
    assert attempt is not None and attempt.status is _AttemptStatus.CHECKPOINTED
    active_domain = runtime.jobs.get_job(domain.job_id)
    assert active_domain is not None
    assert active_domain.current_attempt_id == outcome.attempt.attempt_id
    return runtime, root, active_domain, adapters[0], dispatch_command_id


def _r7a_plan_digest_for_domain(
    runtime: Runtime, root_job_id: str, domain_attempt_id: str
) -> str:
    """Compute the canonical closed-wire plan digest for the admitted domain."""

    from control_plane.executive_orchestration_result import (
        canonical_digest as _result_digest,
    )

    with runtime.store.read() as connection:
        root_row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (root_job_id,)
        ).fetchone()
        from control_plane.executive_runtime import _validated_plan_admission

        admission, plan_body = _validated_plan_admission(connection, root_row)
    assert admission["plan_attempt_id"] == domain_attempt_id
    return _result_digest(plan_body)


def _r7a_dispatch_cycle_work(
    runtime: Runtime,
    *,
    root_job_id: str,
    work_job_id: str,
    worker_id: str,
    quota_class: str,
) -> "type[OrchestrationDispatchOutcome]":
    """Claim the exact work Job through ``dispatch_cycle_job`` and return outcome."""

    command_id = (
        f"coo-cycle:{root_job_id}:dispatch:{work_job_id}:attempt:1"
    )
    outcome = runtime.attempts.dispatch_cycle_job(
        work_job_id,
        command_id=command_id,
        worker_id=worker_id,
        quota_class=quota_class,
    )
    assert outcome is not None
    assert outcome.outcome == "ACTIVE"
    return outcome


def _r7a_complete_work(
    runtime: Runtime,
    work_outcome,
    *,
    plan_attempt_id: str,
    plan_digest: str,
    identity_seed: int,
) -> dict:
    """Seal the bounded work role for the admitted plan step."""

    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": work_outcome.attempt.job_id,  # placeholder, replaced below
        "plan_attempt_id": plan_attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "r6a-step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    job = runtime.jobs.get_job(work_outcome.attempt.job_id)
    assert job is not None
    work_body["root_job_id"] = job.root_job_id
    seal, _terminal = _r7a_complete_ohf_role(
        runtime, work_outcome, work_body, identity_seed=identity_seed
    )
    return seal


def _r7a_complete_review(
    runtime: Runtime,
    review_outcome,
    *,
    plan_attempt_id: str,
    plan_digest: str,
    reviewed_job_id: str,
    reviewed_attempt_id: str,
    reviewed_result_digest: str,
    identity_seed: int,
    verdict: str = "approve",
) -> dict:
    """Seal the bounded review role for the admitted plan step."""

    review_body = _r7a_review_body(
        root_id=runtime.jobs.get_job(review_outcome.attempt.job_id).root_job_id,
        plan_attempt_id=plan_attempt_id,
        plan_digest=plan_digest,
        target_job_id=reviewed_job_id,
        target_attempt_id=reviewed_attempt_id,
        target_result_digest=reviewed_result_digest,
        repair_round=0,
        verdict=verdict,
        plan_step_id="r6a-step-1",
    )
    seal, _terminal = _r7a_complete_ohf_role(
        runtime, review_outcome, review_body, identity_seed=identity_seed
    )
    return seal


def _r7a_capture_proof(payload: dict) -> None:
    """Test-only proof capture of executed IDs/digests.

    Silent unless ``R7B_PROOF_PATH`` is set, so ordinary test runs never touch
    the filesystem; when set, writes only the requested R7B-PROOF.json report
    from the exact material observed during a real executed test.
    """

    target = os.environ.get("R7B_PROOF_PATH")
    if not target:
        return
    Path(target).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _r7a_review_replay_counts(runtime: Runtime, root_job_id: str) -> tuple[int, int]:
    with runtime.store.read() as connection:
        event_count = int(
            connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )
        child_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                (root_job_id,),
            ).fetchone()[0]
        )
    return event_count, child_count


def test_current_depth2_review_create_replays_before_dispatch(
    tmp_path: Path, monkeypatch
) -> None:
    runtime, root, domain, adapter, _dispatch = _r7a_seed_active_domain_with_review(
        tmp_path, monkeypatch=monkeypatch
    )
    _r7a_runtime_with_work_and_review_workers(runtime)
    domain_attempt_id = domain.current_attempt_id
    leaves = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}",
    )
    work = leaves[0]
    plan_digest = _r7a_plan_digest_for_domain(runtime, root.job_id, domain_attempt_id)
    work_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=work.job_id,
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    work_seal = _r7a_complete_work(
        runtime,
        work_dispatch,
        plan_attempt_id=domain_attempt_id,
        plan_digest=plan_digest,
        identity_seed=9101,
    )
    assert adapter.begin_turn_calls == 1
    assert work_seal["role_result_digest"]
    command_id = f"coo-cycle:{root.job_id}:create-review:{work.job_id}:1"
    review = runtime.jobs.create_cycle_review(
        root.job_id, work.job_id, command_id=command_id
    )
    before = _r7a_review_replay_counts(runtime, root.job_id)
    replay = runtime.jobs.create_cycle_review(
        root.job_id, work.job_id, command_id=command_id
    )
    assert replay.job_id == review.job_id
    assert _r7a_review_replay_counts(runtime, root.job_id) == before
    assert adapter.begin_turn_calls == 1


def test_current_depth2_review_create_replays_after_completion(
    tmp_path: Path, monkeypatch
) -> None:
    runtime, root, domain, adapter, _dispatch = _r7a_seed_active_domain_with_review(
        tmp_path, monkeypatch=monkeypatch
    )
    _r7a_runtime_with_work_and_review_workers(runtime)
    domain_attempt_id = domain.current_attempt_id
    leaves = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}",
    )
    work = leaves[0]
    plan_digest = _r7a_plan_digest_for_domain(runtime, root.job_id, domain_attempt_id)
    work_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=work.job_id,
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    work_seal = _r7a_complete_work(
        runtime,
        work_dispatch,
        plan_attempt_id=domain_attempt_id,
        plan_digest=plan_digest,
        identity_seed=9101,
    )
    assert adapter.begin_turn_calls == 1
    command_id = f"coo-cycle:{root.job_id}:create-review:{work.job_id}:1"
    review = runtime.jobs.create_cycle_review(
        root.job_id, work.job_id, command_id=command_id
    )
    review_dispatch = runtime.attempts.dispatch_cycle_job(
        review.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1",
        worker_id="worker-r6a-review",
        quota_class="codex-coo",
    )
    _r7a_complete_review(
        runtime,
        review_dispatch,
        plan_attempt_id=domain_attempt_id,
        plan_digest=plan_digest,
        reviewed_job_id=work.job_id,
        reviewed_attempt_id=work_dispatch.attempt.attempt_id,
        reviewed_result_digest=work_seal["role_result_digest"],
        identity_seed=9102,
    )
    before = _r7a_review_replay_counts(runtime, root.job_id)
    replay = runtime.jobs.create_cycle_review(
        root.job_id, work.job_id, command_id=command_id
    )
    assert replay.job_id == review.job_id
    assert _r7a_review_replay_counts(runtime, root.job_id) == before
    assert adapter.begin_turn_calls == 1


class TestReviewedLeafConsumptionProjection:
    """R7A: completed depth-2 work + independent depth-2 review → projection."""

    def test_active_domain_completed_work_and_independent_review_projects_exact_reviewed_consumption(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # Seed the active domain with the review-required typed plan and the
        # exact R6A admission-shaped fixture (no source edits to runtime).
        runtime, root, domain, adapter, dispatch_command_id = (
            _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        # Register distinct bounded workers for work + review (separate
        # capacity, separate principals, separate provider homes).
        _r7a_runtime_with_work_and_review_workers(runtime)

        # Capture pre-admission event count for the no-new-events assertion.
        with runtime.store.read() as connection:
            events_before = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            domain_turn_count_before = int(
                connection.execute(
                    "SELECT COUNT(*) FROM events WHERE attempt_id=? "
                    "AND event_type IN ('OHF_BEGIN_TURN','OHF_TURN_COMPLETED')",
                    (domain_attempt_id,),
                ).fetchone()[0]
            )

        # Admit the typed plan; depth-2 work leaf appears under the domain.
        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        leaves = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        assert len(leaves) == 1
        work_leaf = leaves[0]
        assert work_leaf.parent_job_id == domain.job_id
        assert work_leaf.root_job_id == root.job_id
        assert work_leaf.orchestration_role == "work"
        assert work_leaf.depth == 2
        plan_digest = _r7a_plan_digest_for_domain(
            runtime, root.job_id, domain_attempt_id
        )
        assert work_leaf.plan_digest == plan_digest
        assert work_leaf.review_required is True

        # Dispatch + complete the work on ``worker-r6a-work`` (separate quota
        # and principal from the domain's held quota).
        work_outcome = _r7a_dispatch_cycle_work(
            runtime,
            root_job_id=root.job_id,
            work_job_id=work_leaf.job_id,
            worker_id="worker-r6a-work",
            quota_class="codex-coo",
        )
        assert work_outcome.attempt.worker_id == "worker-r6a-work"
        assert work_outcome.attempt.quota_class == "codex-coo"
        work_seal = _r7a_complete_work(
            runtime,
            work_outcome,
            plan_attempt_id=domain_attempt_id,
            plan_digest=plan_digest,
            identity_seed=7411,
        )
        work_completed_job = runtime.jobs.get_job(work_leaf.job_id)
        assert work_completed_job is not None
        assert work_completed_job.status == "COMPLETED"

        # Reserve + dispatch the review on a distinct worker + principal.
        review_job = runtime.jobs.create_cycle_review(
            root.job_id,
            work_leaf.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:create-review:"
                f"{work_leaf.job_id}:1"
            ),
        )
        assert review_job.orchestration_role == "review"
        assert review_job.reviews_job_id == work_leaf.job_id
        review_dispatch = runtime.attempts.dispatch_cycle_job(
            review_job.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:{review_job.job_id}:attempt:1"
            ),
            worker_id="worker-r6a-review",
            quota_class="codex-coo",
        )
        assert review_dispatch is not None
        assert review_dispatch.outcome == "ACTIVE"
        assert review_dispatch.attempt.worker_id == "worker-r6a-review"
        review_seal = _r7a_complete_review(
            runtime,
            review_dispatch,
            plan_attempt_id=domain_attempt_id,
            plan_digest=plan_digest,
            reviewed_job_id=work_leaf.job_id,
            reviewed_attempt_id=work_outcome.attempt.attempt_id,
            reviewed_result_digest=work_seal["role_result_digest"],
            identity_seed=7412,
            verdict="approve",
        )
        review_completed = runtime.jobs.get_job(review_job.job_id)
        assert review_completed is not None
        assert review_completed.status == "COMPLETED"

        # No second domain turn / child / event beyond the captured baseline.
        with runtime.store.read() as connection:
            events_after_workflow = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            domain_turn_count_after = int(
                connection.execute(
                    "SELECT COUNT(*) FROM events WHERE attempt_id=? "
                    "AND event_type IN ('OHF_BEGIN_TURN','OHF_TURN_COMPLETED')",
                    (domain_attempt_id,),
                ).fetchone()[0]
            )
            adapter_begin_turns = adapter.begin_turn_calls
            adapter_checkpoints = adapter.checkpoint_calls

        assert adapter_begin_turns == 1
        assert adapter_checkpoints == 1
        # The domain has exactly one initial turn (the supervisor's single
        # typed plan turn) and never gains a second OHF turn.
        assert domain_turn_count_before == 0
        assert domain_turn_count_after == domain_turn_count_before == 0
        assert events_after_workflow > events_before

        # Reach the exact reviewed consumption projection and bind every
        # required ID + digest to the material we just sealed.
        projection = runtime.jobs.project_cycle_domain_consumption(
            root.job_id, domain_attempt_id=domain_attempt_id
        )
        assert projection["schema_version"] == (
            "mastermind.executive_coo_domain_consumption_projection/v1"
        )
        assert projection["root_job_id"] == root.job_id
        assert projection["domain_job_id"] == domain.job_id
        assert projection["domain_attempt_id"] == domain_attempt_id
        assert projection["plan_attempt_id"] == domain_attempt_id
        assert projection["plan_digest"] == plan_digest
        revisions = projection["revisions"]
        assert len(revisions) == 1
        revision = revisions[0]
        assert revision["plan_step_id"] == "r6a-step-1"
        assert revision["review_required"] is True
        assert revision["current_job_id"] == work_leaf.job_id
        assert revision["current_attempt_id"] == work_outcome.attempt.attempt_id
        assert revision["current_result_digest"] == work_seal["role_result_digest"]
        assert revision["qualifying_review_job_id"] == review_job.job_id
        assert (
            revision["qualifying_review_attempt_id"]
            == review_dispatch.attempt.attempt_id
        )
        assert (
            revision["qualifying_review_result_digest"]
            == review_seal["role_result_digest"]
        )

        # Digest is the canonical orchestration_digest recomputed over every
        # bound field except the digest itself, so this recomputation proves
        # the exact canonical binding rather than merely a 64-hex shape.
        expected_projection_digest = orchestration_digest(
            {
                key: value
                for key, value in projection.items()
                if key != "consumption_projection_digest"
            }
        )
        assert re.fullmatch(r"[0-9a-f]{64}", expected_projection_digest) is not None
        assert (
            projection["consumption_projection_digest"]
            == expected_projection_digest
        )

        # Domain remains CHECKPOINTED with its initial turn + seal intact.
        with runtime.store.read() as connection:
            domain_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (domain.job_id,)
            ).fetchone()
            domain_attempt_row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (domain_attempt_id,),
            ).fetchone()
        assert domain_row["current_attempt_id"] == domain_attempt_id
        # No later domain consumption was invented: the domain stays paused on
        # its single sealed initial turn (CHECKPOINTED), not advanced.
        assert domain_row["status"] == "CHECKPOINTED"
        assert domain_attempt_row["status"] == "CHECKPOINTED"

        # Test-only capture of the actual executed IDs/digests (no invented
        # values); silent unless R7B_PROOF_PATH is set.
        _r7a_capture_proof(
            {
                "source_test_only": True,
                "domain_turn_count": 1,
                "later_turn_implemented": False,
                "root_job_id": root.job_id,
                "domain_job_id": domain.job_id,
                "domain_attempt_id": domain_attempt_id,
                "plan_attempt_id": projection["plan_attempt_id"],
                "plan_digest": plan_digest,
                "plan_step_id": revision["plan_step_id"],
                "work_job_id": work_leaf.job_id,
                "work_attempt_id": work_outcome.attempt.attempt_id,
                "work_result_digest": work_seal["role_result_digest"],
                "review_job_id": review_job.job_id,
                "review_attempt_id": review_dispatch.attempt.attempt_id,
                "review_result_digest": review_seal["role_result_digest"],
                "revision": revision,
                "consumption_projection_digest": projection[
                    "consumption_projection_digest"
                ],
            }
        )

    def test_consumption_projection_refuses_live_work_without_any_child_or_event(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """While the depth-2 work is still live (CHECKPOINTED), the projection
        refuses and asserts that no new provider turn, child, or event has
        been minted.  Uses the actual public refusal path that
        ``_current_orchestration_tree_material`` raises.
        """

        runtime, root, domain, _adapter, _cid = (
            _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        _r7a_runtime_with_work_and_review_workers(runtime)

        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        leaves = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        assert len(leaves) == 1
        work_leaf = leaves[0]

        # Dispatch the work (it is now CHECKPOINTED, never completed).
        work_outcome = _r7a_dispatch_cycle_work(
            runtime,
            root_job_id=root.job_id,
            work_job_id=work_leaf.job_id,
            worker_id="worker-r6a-work",
            quota_class="codex-coo",
        )
        live = runtime.jobs.get_job(work_leaf.job_id)
        assert live is not None
        assert live.status in {"RUNNING", "CHECKPOINTED"}

        # Capture the event count immediately BEFORE the projection refusal
        # so the assertion proves the refusal itself minted nothing.
        with runtime.store.read() as connection:
            events_before_refusal = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            children_before_refusal = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )

        with pytest.raises(
            StateConflict, match="aggregation handoff refuses living child Jobs"
        ):
            runtime.jobs.project_cycle_domain_consumption(
                root.job_id, domain_attempt_id=domain_attempt_id
            )

        with runtime.store.read() as connection:
            events_after = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            children_after = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )
        assert events_after == events_before_refusal
        assert children_after == children_before_refusal

    def test_consumption_projection_refuses_live_review_without_turn_child_or_event(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Work COMPLETED, review ACTUALLY dispatched but still live.

        ``project_cycle_domain_consumption`` must refuse (the review is a still
        living child) and the refusal itself must mint no provider turn, child,
        or event.
        """

        runtime, root, domain, _adapter, _cid = (
            _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        _r7a_runtime_with_work_and_review_workers(runtime)

        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        leaves = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        work_leaf = leaves[0]
        plan_digest = _r7a_plan_digest_for_domain(
            runtime, root.job_id, domain_attempt_id
        )

        work_outcome = _r7a_dispatch_cycle_work(
            runtime,
            root_job_id=root.job_id,
            work_job_id=work_leaf.job_id,
            worker_id="worker-r6a-work",
            quota_class="codex-coo",
        )
        _r7a_complete_work(
            runtime,
            work_outcome,
            plan_attempt_id=domain_attempt_id,
            plan_digest=plan_digest,
            identity_seed=7441,
        )
        work_completed = runtime.jobs.get_job(work_leaf.job_id)
        assert work_completed is not None
        assert work_completed.status == "COMPLETED"

        # Create and ACTUALLY dispatch the review; leave it live (never seal).
        review_job = runtime.jobs.create_cycle_review(
            root.job_id,
            work_leaf.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:create-review:{work_leaf.job_id}:1"
            ),
        )
        review_dispatch = runtime.attempts.dispatch_cycle_job(
            review_job.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:{review_job.job_id}:attempt:1"
            ),
            worker_id="worker-r6a-review",
            quota_class="codex-coo",
        )
        assert review_dispatch is not None
        assert review_dispatch.outcome == "ACTIVE"
        live_review = runtime.jobs.get_job(review_job.job_id)
        assert live_review is not None
        assert live_review.status in {"RUNNING", "CHECKPOINTED"}

        with runtime.store.read() as connection:
            events_before_refusal = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            children_before_refusal = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )
            turns_before_refusal = int(
                connection.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type IN "
                    "('OHF_BEGIN_TURN','OHF_TURN_COMPLETED')"
                ).fetchone()[0]
            )

        with pytest.raises(
            StateConflict, match="aggregation handoff refuses living child Jobs"
        ):
            runtime.jobs.project_cycle_domain_consumption(
                root.job_id, domain_attempt_id=domain_attempt_id
            )

        with runtime.store.read() as connection:
            events_after = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            children_after = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )
            turns_after = int(
                connection.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type IN "
                    "('OHF_BEGIN_TURN','OHF_TURN_COMPLETED')"
                ).fetchone()[0]
            )
        assert events_after == events_before_refusal
        assert children_after == children_before_refusal
        assert turns_after == turns_before_refusal

    def test_consumption_projection_refuses_unreviewed_with_no_qualifying_review(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Work completed but no review reserved: projection refuses and the
        refusal path proves no new child/event was added (no fabricated
        terminal review).  Uses the actual public refusal path that
        ``_accepted_current_step_revision`` raises for a required step.
        """

        runtime, root, domain, _adapter, _cid = (
            _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        _r7a_runtime_with_work_and_review_workers(runtime)

        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        leaves = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        work_leaf = leaves[0]
        plan_digest = _r7a_plan_digest_for_domain(
            runtime, root.job_id, domain_attempt_id
        )

        work_outcome = _r7a_dispatch_cycle_work(
            runtime,
            root_job_id=root.job_id,
            work_job_id=work_leaf.job_id,
            worker_id="worker-r6a-work",
            quota_class="codex-coo",
        )
        _r7a_complete_work(
            runtime,
            work_outcome,
            plan_attempt_id=domain_attempt_id,
            plan_digest=plan_digest,
            identity_seed=7421,
        )

        # Capture baseline immediately BEFORE the projection refusal so the
        # assertion proves the refusal itself minted nothing.
        with runtime.store.read() as connection:
            events_before_refusal = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            children_before_refusal = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )
            review_count_before = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=? "
                    "AND orchestration_role='review'",
                    (root.job_id,),
                ).fetchone()[0]
            )

        # Intentionally do NOT create the review Job: exercise the unreviewed
        # refusal path.  No children beyond the one admitted work leaf, no
        # review Job, no extra events.
        with pytest.raises(
            StateConflict,
            match="current revision lacks a qualifying independent approval",
        ):
            runtime.jobs.project_cycle_domain_consumption(
                root.job_id, domain_attempt_id=domain_attempt_id
            )

        with runtime.store.read() as connection:
            events_after = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            review_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=? "
                    "AND orchestration_role='review'",
                    (root.job_id,),
                ).fetchone()[0]
            )
            children_after = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )
        assert events_after == events_before_refusal
        assert review_count == review_count_before == 0
        assert children_after == children_before_refusal

    def test_consumption_projection_refuses_same_principal_review(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Review sealed from the same principal as the work: the independent
        review probe must reject and the projection must refuse, proving no
        new child or event was minted.
        """

        runtime, root, domain, _adapter, _cid = (
            _r7a_seed_active_domain_with_review(tmp_path, monkeypatch=monkeypatch)
        )
        domain_attempt_id = domain.current_attempt_id
        assert domain_attempt_id is not None
        _r7a_runtime_with_work_and_review_workers(runtime)

        command_id = f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}"
        leaves = runtime.jobs.admit_cycle_plan(root.job_id, command_id=command_id)
        work_leaf = leaves[0]
        plan_digest = _r7a_plan_digest_for_domain(
            runtime, root.job_id, domain_attempt_id
        )

        work_outcome = _r7a_dispatch_cycle_work(
            runtime,
            root_job_id=root.job_id,
            work_job_id=work_leaf.job_id,
            worker_id="worker-r6a-work",
            quota_class="codex-coo",
        )
        work_seal = _r7a_complete_work(
            runtime,
            work_outcome,
            plan_attempt_id=domain_attempt_id,
            plan_digest=plan_digest,
            identity_seed=7431,
        )

        # Reach the work Attempt's sealed principal snapshot and reuse ONLY its
        # shared OS-principal / provider-home dimensions for the review, while
        # the review keeps its own distinct worker, attempt, session, process
        # and OHF operation identities (seed 7432) so no global OHF start
        # command collides.  This is the exact "same principal" condition the
        # independence probe must adjudicate on.
        with runtime.store.read() as connection:
            shared_principal = json.loads(
                connection.execute(
                    "SELECT execution_principal_snapshot_json FROM attempts "
                    "WHERE attempt_id=?",
                    (work_outcome.attempt.attempt_id,),
                ).fetchone()[0]
            )

        import tests.test_executive_os_phase1fc as _phase1fc_module

        _real_principal_observation = _phase1fc_module.OperatorPrincipalObservation

        class _SharedPrincipalObservation:
            """Test-only hook: forces the OS principal + provider home to the
            work Attempt's observed values, leaving every other identity
            (attempt, worker, process generation, session) distinct.
            """

            def __new__(cls, **kwargs):
                kwargs["os_principal_name"] = shared_principal["os_principal_name"]
                kwargs["os_principal_uid"] = shared_principal["os_principal_uid"]
                kwargs["provider_home_identity"] = dict(
                    shared_principal["provider_home_identity"]
                )
                return _real_principal_observation(**kwargs)

        monkeypatch.setattr(
            _phase1fc_module,
            "OperatorPrincipalObservation",
            _SharedPrincipalObservation,
        )

        review_job = runtime.jobs.create_cycle_review(
            root.job_id,
            work_leaf.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:create-review:{work_leaf.job_id}:1"
            ),
        )
        # Dispatch the review to the DISTINCT ``worker-r6a-review`` worker with
        # a DISTINCT attempt/session/process/OHF-operation identity, but an
        # intentionally shared OS principal + provider home.  The independent
        # review probe must therefore adjudicate on principal independence and
        # refuse -- not on any operation-identity collision.
        review_dispatch = runtime.attempts.dispatch_cycle_job(
            review_job.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:{review_job.job_id}:attempt:1"
            ),
            worker_id="worker-r6a-review",
            quota_class="codex-coo",
        )
        assert review_dispatch is not None
        assert review_dispatch.outcome == "ACTIVE"
        assert review_dispatch.attempt.worker_id == "worker-r6a-review"
        assert (
            review_dispatch.attempt.attempt_id
            != work_outcome.attempt.attempt_id
        )
        _r7a_complete_review(
            runtime,
            review_dispatch,
            plan_attempt_id=domain_attempt_id,
            plan_digest=plan_digest,
            reviewed_job_id=work_leaf.job_id,
            reviewed_attempt_id=work_outcome.attempt.attempt_id,
            reviewed_result_digest=work_seal["role_result_digest"],
            identity_seed=7432,  # distinct operation/session/process identity
            verdict="approve",
        )
        review_completed = runtime.jobs.get_job(review_job.job_id)
        assert review_completed is not None
        assert review_completed.status == "COMPLETED"

        # Capture baseline immediately BEFORE the projection refusal so the
        # assertion proves the refusal itself minted nothing.
        with runtime.store.read() as connection:
            events_before_refusal = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            children_before_refusal = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )

        with pytest.raises(
            StateConflict,
            match="current revision lacks a qualifying independent approval",
        ):
            runtime.jobs.project_cycle_domain_consumption(
                root.job_id, domain_attempt_id=domain_attempt_id
            )

        with runtime.store.read() as connection:
            events_after = int(
                connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            )
            children_after = int(
                connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE root_job_id=?",
                    (root.job_id,),
                ).fetchone()[0]
            )
        assert events_after == events_before_refusal
        assert children_after == children_before_refusal
