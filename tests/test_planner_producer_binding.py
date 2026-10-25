"""Durable native planner selection through real Runtime and inert OHF adapters."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from control_plane.claude_operator_helper_protocol import native_plan_contract_for_version
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError,
)
from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
    canonical_bytes, canonical_digest,
)
from control_plane.executive_runtime import (
    AttemptLease, AttemptStatus, OrchestrationDispatchOutcome, Runtime, StateConflict,
)
from test_executive_operator_supervisor import (
    _ActiveAdapter, _Clock, _CommissionPromptSource, _PromptSource,
    _seed_dispatchable_operator_planner,
)

VERSIONS = (PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5)


def _created(runtime, planner):
    with runtime.store.read() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM events WHERE event_type='JOB_CREATED' AND job_id=?",
            (planner.job_id,),
        ).fetchall()
    assert len(rows) == 1
    return json.loads(rows[0]["payload_json"])


def _replace_created(runtime, planner, payload):
    # Model a corrupt retained fixture while restoring the exact production
    # immutability trigger before commit; no application mutation path is added.
    with runtime.store.transaction() as connection:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='events_are_immutable_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_type='JOB_CREATED' AND job_id=?",
            (canonical_bytes(payload).decode(), planner.job_id),
        )
        connection.execute(trigger)


def _claim(runtime, root, planner):
    outcome = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert isinstance(outcome, OrchestrationDispatchOutcome) and outcome.lease_token
    return AttemptLease(outcome.attempt, outcome.lease_token)


@pytest.mark.parametrize("version", VERSIONS)
def test_creation_and_reopen_retain_exact_selected_producer(tmp_path, version):
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, plan_schema_version=version,
    )
    payload = _created(runtime, planner)
    binding = payload["planner_producer_binding"]
    assert set(binding) == {
        "schema_version", "root_job_id", "coordinator_job_id", "planner_job_id",
        "plan_schema_version", "native_result_contract", "execution_binding_digest",
    }
    assert binding["root_job_id"] == binding["coordinator_job_id"] == root.job_id
    assert binding["planner_job_id"] == planner.job_id
    assert binding["plan_schema_version"] == version
    assert binding["native_result_contract"] == native_plan_contract_for_version(version)
    assert binding["execution_binding_digest"] == canonical_digest(planner.constraints)
    assert payload["planner_producer_binding_digest"] == canonical_digest(binding)

    reopened = Runtime.at(tmp_path / "runtime")
    assert reopened.jobs.get_planner_producer_binding(planner.job_id) == binding
    replay = reopened.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    assert replay.job_id == planner.job_id
    assert _created(reopened, planner) == payload
    replacement = PLAN_SCHEMA_V3 if version != PLAN_SCHEMA_V3 else PLAN_SCHEMA_V4
    with pytest.raises(StateConflict, match="replace or add"):
        reopened.jobs.create_cycle_planner(
            root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
            plan_schema_version=replacement,
        )
    assert len(reopened.jobs.list_jobs()) == 2
    assert reopened.jobs.get_planner_producer_binding(planner.job_id) == binding


def test_legacy_planner_does_not_adopt_new_constructor_default(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    assert runtime.jobs.get_planner_producer_binding(planner.job_id) is None
    with pytest.raises(StateConflict, match="replace or add"):
        runtime.jobs.create_cycle_planner(
            root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
            plan_schema_version=PLAN_SCHEMA_V3,
        )
    lease = _claim(runtime, root, planner)
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=lambda *a, **k: SimpleNamespace(plan_contract="executive-plan-v1"),
        prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V4,
    )
    assert supervisor._planner_schema(planner) == PLAN_SCHEMA_V1
    prompt = supervisor._prompt(planner, lease)
    assert '"const": "mastermind.execution_plan/v1"' in prompt
    assert '"const": "mastermind.execution_plan/v4"' not in prompt
    assert runtime.jobs.get_planner_producer_binding(planner.job_id) is None


@pytest.mark.parametrize("change", [
    "binding_missing", "digest_missing", "null", "extra", "wrong_root",
    "wrong_coordinator", "wrong_job", "wrong_contract", "wrong_execution",
])
def test_partial_or_relabelled_creation_binding_never_falls_back(tmp_path, change):
    runtime, _root, planner = _seed_dispatchable_operator_planner(
        tmp_path, plan_schema_version=PLAN_SCHEMA_V3,
    )
    payload = _created(runtime, planner)
    if change == "binding_missing":
        del payload["planner_producer_binding"]
    elif change == "digest_missing":
        del payload["planner_producer_binding_digest"]
    elif change == "null":
        payload["planner_producer_binding"] = None
    else:
        binding = payload["planner_producer_binding"]
        if change == "extra":
            binding["provider_permission"] = True
        elif change == "wrong_root":
            binding["root_job_id"] = "JOB-900"
        elif change == "wrong_coordinator":
            binding["coordinator_job_id"] = "JOB-901"
        elif change == "wrong_job":
            binding["planner_job_id"] = "JOB-902"
        elif change == "wrong_contract":
            binding["native_result_contract"] = native_plan_contract_for_version(PLAN_SCHEMA_V4)
        elif change == "wrong_execution":
            binding["execution_binding_digest"] = "b" * 64
        payload["planner_producer_binding_digest"] = canonical_digest(binding)
    _replace_created(runtime, planner, payload)
    with pytest.raises(StateConflict, match="producer"):
        Runtime.at(tmp_path / "runtime").jobs.get_planner_producer_binding(planner.job_id)


def test_competing_versions_have_one_atomic_winner(tmp_path):
    runtime, root, _ = _seed_dispatchable_operator_planner(tmp_path, create_planner=False)
    barrier = threading.Barrier(2)
    def create(version):
        barrier.wait(timeout=10)
        try:
            return runtime.jobs.create_cycle_planner(
                root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0",
                plan_schema_version=version,
            )
        except StateConflict as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create, value) for value in (PLAN_SCHEMA_V3, PLAN_SCHEMA_V4)]
        results = [future.result(timeout=30) for future in futures]
    winners = [result for result in results if not isinstance(result, Exception)]
    assert len(winners) == 1
    assert sum(isinstance(result, StateConflict) for result in results) == 1
    reopened = Runtime.at(tmp_path / "runtime")
    assert len(reopened.jobs.list_jobs()) == 2
    assert reopened.jobs.get_planner_producer_binding(winners[0].job_id)["plan_schema_version"] in (
        PLAN_SCHEMA_V3, PLAN_SCHEMA_V4,
    )


@pytest.mark.parametrize("version", [PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5])
def test_adapter_gate_and_prompt_use_retained_selection_after_restart(tmp_path, version):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path, plan_schema_version=version)
    reopened = Runtime.at(tmp_path / "runtime")
    lease = _claim(reopened, root, planner)
    calls = []
    def factory(current, requested, loader, *, recovery):
        calls.append(current.attempt_id)
        return SimpleNamespace(plan_contract=native_plan_contract_for_version(version)["name"])
    supervisor = ExecutiveOperatorSupervisor(
        reopened, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
        plan_schema_version=PLAN_SCHEMA_V1,
    )
    requested = supervisor._requested_profile(planner, lease)
    supervisor._adapter_for_attempt(lease, requested, lambda _turn: "inert", recovery=False)
    assert calls == [lease.attempt.attempt_id]
    prompt = supervisor._prompt(planner, lease)
    assert f'"const": "{version}"' in prompt
    if version == PLAN_SCHEMA_V5:
        assert f'"const": "{root.job_id}"' in prompt
    assert reopened.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CLAIMED


def test_bound_requested_profile_mismatch_refuses_before_factory(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path, plan_schema_version=PLAN_SCHEMA_V3)
    lease = _claim(runtime, root, planner)
    calls = []
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=lambda *a, **k: calls.append(True),
        prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V3,
    )
    requested = supervisor._requested_profile(planner, lease)
    wrong = dataclasses.replace(requested, requested_model="unadmitted-model")
    with pytest.raises(ExecutiveOperatorSupervisorError, match="requested profile"):
        supervisor._adapter_for_attempt(lease, wrong, lambda _turn: "", recovery=False)
    assert calls == []
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0


class _VersionedAdapter(_ActiveAdapter):
    """Inert test adapter with an explicitly declared native producer contract."""
    def __init__(self, runtime, loader, version, *, returned_version=None, delegation=None):
        super().__init__(runtime, loader, cancel_during_collect=False)
        self.version = version
        self.returned_version = returned_version or version
        self.plan_contract = native_plan_contract_for_version(version)["name"]
        self.start_calls = 0
        self.delegation = delegation

    def start_session(self, **kwargs):
        self.start_calls += 1
        return super().start_session(**kwargs)

    def _canonical_result(self, turn):
        envelope = json.loads(super()._canonical_result(turn))
        body = envelope["role_result"]
        body["schema_version"] = self.returned_version
        if self.returned_version in (PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5):
            for step in body["steps"]:
                step["prerequisite_step_ids"] = []
                if self.returned_version == PLAN_SCHEMA_V3:
                    step["placement"] = {"provider_realm": "codex", "quota_class": "codex-coo"}
                if self.returned_version == PLAN_SCHEMA_V5:
                    step["delegation"] = self.delegation
        if self.returned_version == PLAN_SCHEMA_V5:
            attempt = self.runtime.attempts.get_attempt(turn.attempt_id)
            job = self.runtime.jobs.get_job(attempt.job_id)
            body["coordinator_job_id"] = job.parent_job_id
        return canonical_bytes(envelope).decode()


@pytest.mark.parametrize("version", [PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5])
def test_real_supervisor_runtime_result_admission_and_terminal_replay(tmp_path, version):
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, plan_schema_version=version, routing_capacity=True,
    )
    adapters = []
    def factory(_attempt, _requested, loader, *, recovery):
        assert recovery is False
        adapter = _VersionedAdapter(runtime, loader, version)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
        plan_schema_version=version,
    )
    command = f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
    outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id, command_id=command))
    assert outcome.outcome == "TERMINAL"
    admission_command = f"coo-cycle:{root.job_id}:admit-plan:{outcome.attempt.attempt_id}"
    children = runtime.jobs.admit_cycle_plan(root.job_id, command_id=admission_command)
    assert len(children) == 1 and children[0].parent_job_id == root.job_id
    assert adapters[0].start_calls == adapters[0].begin_turn_calls == 1
    assert adapters[0].stop_calls == 1
    reopened = Runtime.at(tmp_path / "runtime")
    def unavailable(*args, **kwargs):
        pytest.fail("terminal replay reached a fresh adapter")
    replay_supervisor = ExecutiveOperatorSupervisor(
        reopened, claimed_adapter_factory=unavailable, prompt_source=_PromptSource(),
        plan_schema_version=PLAN_SCHEMA_V1,
    )
    replay = asyncio.run(replay_supervisor.start_cycle_job(planner.job_id, command_id=command))
    assert replay.attempt.attempt_id == outcome.attempt.attempt_id
    assert [job.job_id for job in reopened.jobs.admit_cycle_plan(
        root.job_id, command_id=admission_command,
    )] == [job.job_id for job in children]
    assert adapters[0].start_calls == adapters[0].begin_turn_calls == 1


class _CrashAfterSeal(BaseException):
    """Simulate process loss, outside the ordinary Exception cleanup path."""


def _seed_bound_sealed(tmp_path, monkeypatch, version=PLAN_SCHEMA_V3, *, frontier_selection=None):
    clock = _Clock()
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, clock=clock, plan_schema_version=version, routing_capacity=True,
        commission_content=b"# Retained planner commission\nProduce one bounded plan.\n",
        frontier_selection=frontier_selection,
    )
    adapters, retained = [], {}
    def factory(_attempt, _requested, loader, *, recovery):
        assert not recovery
        adapter = _VersionedAdapter(runtime, loader, version)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_CommissionPromptSource(),
        plan_schema_version=version,
    )
    def interrupt(**kwargs):
        retained.update(kwargs)
        raise _CrashAfterSeal()
    monkeypatch.setattr(supervisor, "_complete_after_stop", interrupt)
    with pytest.raises(_CrashAfterSeal):
        asyncio.run(supervisor.start_cycle_job(
            planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        ))
    attempt = runtime.attempts.get_attempt(retained["lease"].attempt.attempt_id)
    assert attempt.status is AttemptStatus.RUNNING
    assert runtime.events.get_event_by_command_id(f"orchestration-result-seal:{attempt.attempt_id}")
    assert adapters[0].start_calls == adapters[0].begin_turn_calls == 1
    assert adapters[0].stop_calls == 0
    clock.advance(1000)
    return clock, runtime, root, planner, attempt, retained


@pytest.mark.parametrize("version", [PLAN_SCHEMA_V3, PLAN_SCHEMA_V5])
@pytest.mark.parametrize("corrupt_binding", [False, True])
def test_sealed_restart_contains_original_session_without_fresh_producer_admission(
    tmp_path, monkeypatch, version, corrupt_binding,
):
    from control_plane.executive_supervisor import ReconcileStatus
    clock, runtime, root, planner, attempt, retained = _seed_bound_sealed(tmp_path, monkeypatch, version)
    original_binding = runtime.jobs.get_planner_producer_binding(planner.job_id)
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET model=? WHERE worker_id=? AND quota_class=?",
            ("changed-current-default", attempt.worker_id, attempt.quota_class),
        )
    if corrupt_binding:
        payload = _created(runtime, planner)
        payload["planner_producer_binding"]["execution_binding_digest"] = "b" * 64
        payload["planner_producer_binding_digest"] = canonical_digest(payload["planner_producer_binding"])
        _replace_created(runtime, planner, payload)
    reopened = Runtime.at(tmp_path / "runtime", clock=clock)
    def unavailable_commission(*args, **kwargs):
        pytest.fail("sealed recovery attempted fresh commission verification")
    monkeypatch.setattr(
        "control_plane.executive_operator_supervisor.verify_commission_for_job", unavailable_commission,
    )
    adapters = []
    def factory(current, requested, loader, *, recovery):
        assert recovery and current.attempt_id == attempt.attempt_id
        assert requested == retained["session"].launch.requested
        with pytest.raises(ExecutiveOperatorSupervisorError, match="containment recovery"):
            loader(None)
        # Deliberately a different current producer. Only the recorded session
        # is reconciled/stopped, so this contract cannot authorize a new turn.
        adapter = _VersionedAdapter(reopened, loader, PLAN_SCHEMA_V1)
        adapter.profile = requested
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        reopened, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
        plan_schema_version=PLAN_SCHEMA_V1,
    )
    outcomes = supervisor.reconcile_restart()
    assert [item.status for item in outcomes] == [
        ReconcileStatus.IDENTITY_AMBIGUOUS if corrupt_binding else ReconcileStatus.OPERATOR_RECOVERED,
    ]
    assert len(adapters) == 1
    adapter = adapters[0]
    assert adapter.start_calls == adapter.resume_calls == adapter.begin_turn_calls == adapter.read_calls == 0
    assert adapter.stop_calls == 1
    current = reopened.attempts.get_attempt(attempt.attempt_id)
    assert (current.status is AttemptStatus.COMPLETED) is (not corrupt_binding)
    with reopened.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 1
        assert connection.execute("SELECT state FROM harness_session_epochs").fetchone()[0] == "ABANDONED"
        assert connection.execute("SELECT COUNT(*) FROM process_generations WHERE executive_writer_held=1").fetchone()[0] == 0
    if not corrupt_binding:
        assert reopened.jobs.get_planner_producer_binding(planner.job_id) == original_binding
        children = reopened.jobs.admit_cycle_plan(
            root.job_id, command_id=f"coo-cycle:{root.job_id}:admit-plan:{attempt.attempt_id}",
        )
        assert len(children) == 1


def test_recovery_refuses_changed_seal_before_adapter_construction(tmp_path, monkeypatch):
    from control_plane.executive_supervisor import ReconcileStatus
    clock, _runtime, _root, _planner, attempt, _retained = _seed_bound_sealed(tmp_path, monkeypatch)
    reopened = Runtime.at(tmp_path / "runtime", clock=clock)
    calls = []
    supervisor = ExecutiveOperatorSupervisor(
        reopened, claimed_adapter_factory=lambda *a, **k: calls.append(True), prompt_source=_PromptSource(),
    )
    original = supervisor._sealed_role_result_json
    reads = []
    def changed(job, lease):
        result = original(job, lease)
        reads.append(result)
        return result if len(reads) == 1 else None
    monkeypatch.setattr(supervisor, "_sealed_role_result_json", changed)
    assert [item.status for item in supervisor.reconcile_restart()] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    assert calls == [] and len(reads) == 2
    assert reopened.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.RUNNING


def test_bound_wrong_returned_version_refuses_sealing_and_children(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, plan_schema_version=PLAN_SCHEMA_V3, routing_capacity=True,
    )
    adapters = []
    def factory(_attempt, _requested, loader, *, recovery):
        adapter = _VersionedAdapter(runtime, loader, PLAN_SCHEMA_V3, returned_version=PLAN_SCHEMA_V4)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V3,
    )
    from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrationError
    with pytest.raises(OperatorHarnessOrchestrationError, match="could not be sealed") as failure:
        asyncio.run(supervisor.start_cycle_job(
            planner.job_id, command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        ))
    assert isinstance(failure.value.__cause__, StateConflict)
    assert "producer binding" in str(failure.value.__cause__)
    assert adapters[0].start_calls == adapters[0].begin_turn_calls == adapters[0].stop_calls == 1
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED'").fetchone()[0] == 0
    assert runtime.jobs.get_job(planner.job_id).status.value != "COMPLETED"
    assert len(runtime.jobs.list_jobs()) == 2


@pytest.mark.parametrize("mismatch", ["served_model", "initialized_contract"])
def test_initialized_producer_mismatch_never_begins_useful_turn(tmp_path, mismatch):
    from control_plane.operator_harness_orchestrator import OperatorStartRefused
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path, plan_schema_version=PLAN_SCHEMA_V3)
    class MismatchedAdapter(_VersionedAdapter):
        def observed_attestation(self, generation):
            attestation = super().observed_attestation(generation)
            if mismatch == "served_model":
                return dataclasses.replace(attestation, served_model="different-served-model")
            self.plan_contract = "executive-plan-v4"
            return attestation
    adapters = []
    def factory(_attempt, _requested, loader, *, recovery):
        adapter = MismatchedAdapter(runtime, loader, PLAN_SCHEMA_V3)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V3,
    )
    with pytest.raises((OperatorStartRefused, ExecutiveOperatorSupervisorError)):
        asyncio.run(supervisor.start_cycle_job(
            planner.job_id, command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        ))
    assert len(adapters) == 1 and adapters[0].start_calls == 1
    assert adapters[0].begin_turn_calls == adapters[0].read_calls == 0
    assert adapters[0].stop_calls == 1
    assert len(runtime.jobs.list_jobs()) == 2


def test_nested_v5_native_planner_keeps_original_root_and_immediate_coordinator(tmp_path):
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, plan_schema_version=PLAN_SCHEMA_V5, routing_capacity=True,
    )
    adapters = []
    def factory(attempt, _requested, loader, *, recovery):
        job = runtime.jobs.get_job(attempt.job_id)
        adapter = _VersionedAdapter(runtime, loader, PLAN_SCHEMA_V5, delegation=(
            {"descendant_limit": 8, "max_depth": 3} if job.parent_job_id == root.job_id else None
        ))
        adapter.provider_session_id = f"SESSION-{attempt.attempt_id}"
        adapter.native_turn_id = f"TURN-{attempt.attempt_id}"
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V5,
    )
    first = asyncio.run(supervisor.start_cycle_job(
        planner.job_id, command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
    ))
    coordinator, = runtime.jobs.admit_cycle_plan(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:admit-plan:{first.attempt.attempt_id}",
    )
    CooCycle(runtime, planner_plan_schema_version=PLAN_SCHEMA_V5).run_once(coordinator.job_id)
    nested, = [job for job in runtime.jobs.list_jobs()
               if job.parent_job_id == coordinator.job_id and job.orchestration_role == "plan"]
    binding = runtime.jobs.get_planner_producer_binding(nested.job_id)
    assert binding["root_job_id"] == root.job_id
    assert binding["coordinator_job_id"] == coordinator.job_id
    assert binding["plan_schema_version"] == PLAN_SCHEMA_V5
    second = asyncio.run(supervisor.start_cycle_job(
        nested.job_id, command_id=f"coo-cycle:{coordinator.job_id}:dispatch:{nested.job_id}:attempt:1",
    ))
    leaf, = runtime.jobs.admit_cycle_plan(
        coordinator.job_id, command_id=f"coo-cycle:{coordinator.job_id}:admit-plan:{second.attempt.attempt_id}",
    )
    assert leaf.root_job_id == root.job_id and leaf.parent_job_id == coordinator.job_id
    assert coordinator.depth == 1 and nested.depth == leaf.depth == 2
    assert all(adapter.start_calls == adapter.begin_turn_calls == adapter.stop_calls == 1 for adapter in adapters)
    assert f'"const": "{coordinator.job_id}"' in adapters[1].prompts[0]



def test_sealed_recovery_keeps_ambiguous_physical_identity_fenced(tmp_path, monkeypatch):
    from control_plane.executive_supervisor import ReconcileStatus
    clock, _runtime, _root, _planner, attempt, _retained = _seed_bound_sealed(tmp_path, monkeypatch)
    reopened = Runtime.at(tmp_path / "runtime", clock=clock)
    adapters = []
    def factory(_attempt, requested, loader, *, recovery):
        adapter = _VersionedAdapter(reopened, loader, PLAN_SCHEMA_V1)
        adapter.profile = requested
        adapter.process = dataclasses.replace(adapter.process, pid=9999, pgid=9999)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        reopened, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
    )
    assert [item.status for item in supervisor.reconcile_restart()] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    assert len(adapters) == 1
    adapter = adapters[0]
    assert adapter.start_calls == adapter.resume_calls == adapter.begin_turn_calls == adapter.read_calls == adapter.stop_calls == 0
    assert reopened.attempts.get_attempt(attempt.attempt_id).status is AttemptStatus.RUNNING
    with reopened.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM process_generations WHERE executive_writer_held=1").fetchone()[0] == 1
