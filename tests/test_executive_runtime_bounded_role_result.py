"""G8+ bounded role-result selection: fixed admission over the canonical closure.

Contract: ``BoundedRuntimeReadObservation.read_role_result_bounded`` routes the
unchanged canonical recursive completion validators through one private bounded
loader on the fresh observation connection, under fixed statement/row/byte/
node/VM budgets.  Every fixture here is an actual SQLite canonical completion
(OHF operator-harness family and sealed-worker family); nothing is mocked and
no budget is asserted from constants alone.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import pwd
import re
import sqlite3
from pathlib import Path

import pytest

from control_plane import executive_runtime as er
from control_plane.ceo_intent import submit_intent
from control_plane.executive_orchestration_result import (
    canonical_bytes,
    canonical_digest,
    validate_envelope,
)
from control_plane.executive_runtime import Runtime, RuntimeReadBinding, StateConflict
from control_plane.executive_supervisor import ExecutiveSupervisor
from tests.test_executive_os_phase1fc import _register, _v2_intent
from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_executive_supervisor import FakeInspector, FakeProcessController
from tests.test_executive_terminal_return import (
    _PlannerSealedWorkerAdapter,
    _SEALED_WORKER_SECRET_CANARY,
    _completed_planner,
)

from tests.test_executive_os_phase1fc import (
    _cycle_through_completed_work, _review_body, _complete_ohf_role,
)


def complete_maximum_chain(directory: Path):
    runtime, cycle, dispatches, root, planner, current, seal = _cycle_through_completed_work(
        directory, intent_id='CEO-BOUNDED-MAX-CHAIN',
        review_workers=['worker-b', 'worker-b', 'worker-b'],
    )
    plan_digest = str(runtime.jobs.get_job(current.attempt.job_id).plan_digest)
    nodes = [(current.attempt.job_id, current.attempt.attempt_id, seal)]
    for round_number in range(3):
        assert cycle.run_once(root.job_id).action == 'REVIEW_CREATED'
        assert cycle.run_once(root.job_id).action == 'DISPATCHED'
        review = dispatches[-1]
        review_body = _review_body(
            root_id=root.job_id, plan_attempt_id=planner.attempt.attempt_id,
            plan_digest=plan_digest, target_job_id=current.attempt.job_id,
            target_attempt_id=current.attempt.attempt_id,
            target_result_digest=seal['role_result_digest'],
            repair_round=round_number, verdict='approve' if round_number == 2 else 'reject',
        )
        review_seal, _ = _complete_ohf_role(runtime, review, review_body, identity_seed=8400 + round_number * 2)
        nodes.append((review.attempt.job_id, review.attempt.attempt_id, review_seal))
        if round_number == 2:
            break
        assert cycle.run_once(root.job_id).action == 'REPAIR_CREATED'
        assert cycle.run_once(root.job_id).action == 'DISPATCHED'
        repair = dispatches[-1]
        repair_body = {
            'schema_version': 'mastermind.repair_result/v1',
            'root_job_id': root.job_id, 'plan_attempt_id': planner.attempt.attempt_id,
            'plan_digest': plan_digest, 'plan_step_id': 'step-1',
            'repair_round': round_number + 1,
            'supersedes_job_id': current.attempt.job_id,
            'rejected_review_job_id': review.attempt.job_id,
            'rejected_review_result_digest': review_seal['role_result_digest'],
            'artifacts': [], 'evidence_digests': [],
        }
        seal, _ = _complete_ohf_role(runtime, repair, repair_body, identity_seed=8401 + round_number * 2)
        current = repair
        nodes.append((current.attempt.job_id, current.attempt.attempt_id, seal))
    assert len(nodes) == 6
    return runtime, root, nodes


PAD_CELL = 9 * 1024 * 1024   # one guarded cell above the 8 MiB ceiling
PAD_CUM = 7 * 1024 * 1024    # every cell legal, cumulative over 32 MiB


def _db_path(base: Path) -> Path:
    matches = sorted((Path(base) / "data").rglob("*.sqlite3"))
    assert len(matches) == 1, matches
    return matches[0]


def _pad_json(pad: int) -> str:
    return json.dumps({"probe_pad": "A" * pad})


def _with_triggers_dropped(path: Path, names, mutate) -> None:
    """Simulate corrupted durable rows, then restore the exact reviewed DDL."""
    names = [names] if isinstance(names, str) else list(names)
    con = sqlite3.connect(path)
    saved = {
        name: con.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
        ).fetchone()[0]
        for name in names
    }
    for name in names:
        con.execute(f"DROP TRIGGER {name}")
    mutate(con)
    for name in names:
        con.execute(saved[name])
    con.commit()
    con.close()


def _fill_events(path: Path, count: int) -> None:
    con = sqlite3.connect(path)
    con.executemany(
        "INSERT INTO events (aggregate_type,aggregate_id,sequence,event_type,"
        "command_id,actor,payload_json,created_at_ms) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("probe_filler", f"filler-{index}", 1, "PROBE_FILLER",
             f"probe-filler-{index}", "probe", "{}", 1790000000000 + index)
            for index in range(count)
        ],
    )
    con.commit()
    con.close()


def _select_bounded(runtime, root_id, job_id, attempt_id, digest):
    with runtime.observe_bounded_read() as observation:
        return observation.read_role_result_bounded(
            root_id,
            job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=digest,
        )


@pytest.fixture
def max_chain(tmp_path):
    runtime, root, nodes = complete_maximum_chain(tmp_path)
    job_id, attempt_id, _ = nodes[-1]
    expected = runtime.validated_role_completion(job_id, expected_attempt_id=attempt_id)
    return runtime, root, nodes, job_id, attempt_id, expected


# ---------------------------------------------------------------------------
# Frozen contract shape
# ---------------------------------------------------------------------------


def test_snapshot_shape_is_the_frozen_contract():
    snapshot_fields = [
        field.name
        for field in dataclasses.fields(er.BoundedRoleResultSnapshot)
    ]
    assert snapshot_fields == [
        "root_job_id",
        "job_id",
        "attempt_id",
        "result_envelope_digest",
        "completion",
        "root_metadata",
        "observation_source_identity",
    ]
    metadata_fields = [
        field.name
        for field in dataclasses.fields(er.BoundedRoleResultRootMetadata)
    ]
    assert metadata_fields == [
        "job_id",
        "root_job_id",
        "orchestration_role",
        "creation_command_id",
        "work_ref",
        "orchestration_provenance_digest",
        "source_digest",
    ]
    assert er.BoundedRoleResultSnapshot.__dataclass_params__.frozen
    assert er.BoundedRoleResultRootMetadata.__dataclass_params__.frozen
    assert not hasattr(er.BoundedRoleResultSnapshot, "to_dict")
    assert issubclass(er.RuntimeRoleResultOverBudget, er.RuntimeReadUnavailable)
    assert er.RuntimeRoleResultOverBudget.code == "OVER_BUDGET"


# ---------------------------------------------------------------------------
# Authentic success: both receipt families, every role
# ---------------------------------------------------------------------------


def test_maximum_valid_chain_bounded_selection_matches_canonical(max_chain):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    snapshot = _select_bounded(
        runtime, root.job_id, job_id, attempt_id, expected.result_digest
    )
    assert snapshot.completion == expected
    assert snapshot.root_job_id == root.job_id
    assert snapshot.job_id == job_id
    assert snapshot.attempt_id == attempt_id
    assert snapshot.result_envelope_digest == expected.result_digest

    metadata = snapshot.root_metadata
    root_job = runtime.jobs.get_job(root.job_id)
    provenance = root_job.orchestration_provenance
    assert metadata.job_id == metadata.root_job_id == root.job_id
    assert metadata.orchestration_role == "aggregation"
    assert metadata.creation_command_id == "ceo-intent:CEO-BOUNDED-MAX-CHAIN"
    assert metadata.orchestration_provenance_digest == (
        root_job.orchestration_provenance_digest
    )
    assert metadata.source_digest == provenance["source_digest"]
    expected_work_ref = (
        expected.dialogue_source.work_ref
        if expected.dialogue_source is not None
        else None
    )
    assert metadata.work_ref == expected_work_ref
    # Frozen narrow metadata comes from the aggregation self-root, never from
    # the selected child: the deepest review carries none of these values.
    assert metadata.job_id != job_id


def test_every_ohf_role_selects_bounded_equal_to_canonical(max_chain):
    runtime, root, nodes, _job_id, _attempt_id, _expected = max_chain
    roles = ["work", "review", "repair", "review", "repair", "review"]
    for (job_id, attempt_id, _seal), role in zip(nodes, roles):
        expected = runtime.validated_role_completion(
            job_id, expected_attempt_id=attempt_id
        )
        snapshot = _select_bounded(
            runtime, root.job_id, job_id, attempt_id, expected.result_digest
        )
        assert snapshot.completion == expected
        assert snapshot.completion.result_envelope["role"] == role


def test_operator_harness_planner_family_bounded_selection(tmp_path):
    runtime, job, attempt = _completed_planner(tmp_path)
    expected = runtime.validated_role_completion(
        job.job_id, expected_attempt_id=attempt.attempt_id
    )
    assert expected.execution_mode == "OPERATOR_HARNESS"
    snapshot = _select_bounded(
        runtime,
        job.root_job_id,
        job.job_id,
        attempt.attempt_id,
        expected.result_digest,
    )
    assert snapshot.completion == expected
    assert snapshot.root_metadata.job_id == job.root_job_id
    assert snapshot.root_metadata.orchestration_role == "aggregation"
    assert snapshot.root_metadata.creation_command_id == (
        "ceo-intent:CEO-TERMINAL-RETURN-PLANNER"
    )


def test_sealed_worker_supervisor_family_bounded_selection(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime = Runtime.at(runtime_root)
    _register(runtime, "worker-a")
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "planner"
    workspace.mkdir(parents=True, mode=0o700)
    admitted = submit_intent(
        runtime,
        _v2_intent(
            intent_id="CEO-SEALED-WORKER-BOUNDED-ROLE-RESULT",
            execution_contract={
                "requested_authorities": ["READ"],
                "worktree": str(workspace),
                "attempt_limit": 2,
                "constraints": {"base_sha": "b" * 40},
            },
        ),
        workspace_root=workspace_root,
    )
    root = runtime.jobs.get_job(admitted["job_id"])
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    adapter = _PlannerSealedWorkerAdapter(
        FakeInspector(),
        root_job_id=root.job_id,
        provider_home=codex_home,
    )
    uid, gid = os.geteuid(), os.getegid()
    supervisor = ExecutiveSupervisor(
        runtime,
        adapter,
        runs_root=tmp_path / "runs",
        isolation_roots=(workspace_root, tmp_path / "runs"),
        worker_user=pwd.getpwuid(uid).pw_name,
        worker_uid=uid,
        worker_gid=gid,
        heartbeat_interval_seconds=0.01,
        inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,
        require_complete_launch_attestation=True,
        instance_id="supervisor-fixture",
    )
    receipt = asyncio.run(
        supervisor.run_cycle_once(
            planner.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
            ),
        )
    )
    assert receipt.attempt.status.value == "COMPLETED"

    reopened = Runtime.at(runtime_root)
    expected = reopened.validated_role_completion(
        planner.job_id, expected_attempt_id=receipt.attempt.attempt_id
    )
    assert expected.execution_mode == "SEALED_WORKER"
    snapshot = _select_bounded(
        reopened,
        root.job_id,
        planner.job_id,
        receipt.attempt.attempt_id,
        expected.result_digest,
    )
    assert snapshot.completion == expected
    assert snapshot.root_metadata.job_id == root.job_id
    assert snapshot.root_metadata.creation_command_id == (
        "ceo-intent:CEO-SEALED-WORKER-BOUNDED-ROLE-RESULT"
    )


def test_huge_but_admissible_history_still_succeeds(max_chain, tmp_path):
    # Bounds are admission-only: more residual history costs more shared VM
    # budget but never changes canonical validity.
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    _fill_events(_db_path(tmp_path), 2_000)
    reopened = Runtime.at(tmp_path)
    snapshot = _select_bounded(
        reopened, root.job_id, job_id, attempt_id, expected.result_digest
    )
    assert snapshot.completion == expected


# ---------------------------------------------------------------------------
# Real progress-handler exhaustion and byte refusal
# ---------------------------------------------------------------------------


def test_vm_progress_handler_exhaustion_is_typed_refusal(max_chain, tmp_path):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    _fill_events(_db_path(tmp_path), 150_000)
    reopened = Runtime.at(tmp_path)
    legacy = reopened.validated_role_completion(job_id, expected_attempt_id=attempt_id)
    assert legacy.result_digest == expected.result_digest

    with pytest.raises(er.RuntimeRoleResultOverBudget) as info:
        with reopened.observe_bounded_read() as observation:
            observation.read_role_result_bounded(
                root.job_id,
                job_id,
                expected_attempt_id=attempt_id,
                expected_result_envelope_digest=expected.result_digest,
            )
    assert info.value.code == "OVER_BUDGET"
    assert isinstance(info.value, er.RuntimeReadUnavailable)
    # The fixed handler on the fresh private connection actually tripped.
    assert observation._vm_progress.tripped
    assert observation._vm_progress.steps >= er.BOUNDED_ROLE_RESULT_MAX_VM_STEPS
    with pytest.raises(StateConflict):
        _ = observation.receipt


def test_per_cell_byte_refusal_before_decode_jobs(max_chain, tmp_path):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    con = sqlite3.connect(_db_path(tmp_path))
    con.execute(
        "UPDATE jobs SET result_json=? WHERE job_id=?", (_pad_json(PAD_CELL), job_id)
    )
    con.commit()
    con.close()
    reopened = Runtime.at(tmp_path)
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        _select_bounded(
            reopened, root.job_id, job_id, attempt_id, expected.result_digest
        )
    # Legacy admission has no byte budget and fails later, on material law —
    # the bounded read refuses before the payload is returned to Python.
    with pytest.raises(StateConflict):
        reopened.validated_role_completion(job_id, expected_attempt_id=attempt_id)


def test_per_cell_byte_refusal_before_decode_attempts(max_chain, tmp_path):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    con = sqlite3.connect(_db_path(tmp_path))
    attempt_row = con.execute(
        "SELECT attempt_id FROM attempts WHERE job_id=? AND status='COMPLETED'",
        (job_id,),
    ).fetchone()
    con.close()

    def mutate(db):
        db.execute(
            "UPDATE attempts SET result_json=? WHERE attempt_id=?",
            (_pad_json(PAD_CELL), attempt_row[0]),
        )

    _with_triggers_dropped(
        _db_path(tmp_path), "terminal_attempts_are_immutable", mutate
    )
    reopened = Runtime.at(tmp_path)  # exact DDL restored: schema verifies again
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        _select_bounded(
            reopened, root.job_id, job_id, attempt_id, expected.result_digest
        )


def test_cumulative_byte_refusal_with_legal_cells(max_chain, tmp_path):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    con = sqlite3.connect(_db_path(tmp_path))
    # Four closure nodes are projected across five guarded jobs statements:
    # 5 x 7 MiB crosses the 32 MiB cumulative ceiling while every single cell
    # stays below the 8 MiB per-cell ceiling.
    for node, _, _ in (nodes[1], nodes[2], nodes[3], nodes[0]):
        con.execute(
            "UPDATE jobs SET result_json=? WHERE job_id=?", (_pad_json(PAD_CUM), node)
        )
    con.commit()
    con.close()
    reopened = Runtime.at(tmp_path)
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        _select_bounded(
            reopened, root.job_id, job_id, attempt_id, expected.result_digest
        )


# ---------------------------------------------------------------------------
# Genuine duplicate, cycle, identity, current-attempt and digest refusals
# ---------------------------------------------------------------------------


def test_duplicate_root_creation_under_other_command_refuses(max_chain, tmp_path):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    con = sqlite3.connect(_db_path(tmp_path))
    row = con.execute(
        "SELECT * FROM events WHERE event_type='JOB_CREATED' AND job_id=?",
        (root.job_id,),
    ).fetchone()
    columns = [d[0] for d in con.execute("SELECT * FROM events LIMIT 1").description]
    duplicate = dict(zip(columns, row))
    duplicate["event_id"] = None
    duplicate["command_id"] = "ceo-intent:DUPLICATE-UNDER-OTHER-COMMAND"
    duplicate["sequence"] = int(duplicate["sequence"]) + 100
    con.execute(
        f"INSERT INTO events ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
        [duplicate[column] for column in columns],
    )
    con.commit()
    con.close()
    reopened = Runtime.at(tmp_path)
    with pytest.raises(StateConflict, match="cardinality is not exact"):
        _select_bounded(
            reopened, root.job_id, job_id, attempt_id, expected.result_digest
        )


def test_active_validation_cycle_refuses(max_chain, tmp_path):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    repair2, repair2_attempt = nodes[4][0], nodes[4][1]
    review1 = nodes[3][0]

    con = sqlite3.connect(_db_path(tmp_path))
    worker_id = con.execute(
        "SELECT worker_id FROM attempts WHERE attempt_id=?", (repair2_attempt,)
    ).fetchone()[0]
    seal = json.loads(
        con.execute(
            "SELECT payload_json FROM events WHERE command_id=?",
            (f"orchestration-result-seal:{repair2_attempt}",),
        ).fetchone()[0]
    )
    envelope = dict(seal["result_envelope"])
    envelope["role_result"] = dict(envelope["role_result"])
    # A digest-consistent self-referential repair: repair2 supersedes itself,
    # so the canonical closure re-enters repair2 while it is still active.
    envelope["role_result"]["supersedes_job_id"] = repair2
    validated = validate_envelope(
        envelope,
        expected_job_id=repair2,
        expected_run_id=repair2_attempt,
        expected_worker_id=worker_id,
        expected_role="repair",
        expected_root_job_id=root.job_id,
    )
    seal["result_envelope"] = envelope
    seal["role_result_digest"] = canonical_digest(validated["role_result"])
    seal["result_envelope_digest"] = canonical_digest(envelope)

    def reforged(payload_text):
        receipt_payload = json.loads(payload_text)
        receipt_payload["result_envelope"] = envelope
        receipt_payload["result_envelope_digest"] = seal["result_envelope_digest"]
        receipt_payload.pop("terminal_evidence_digest")
        receipt_payload["terminal_evidence_digest"] = canonical_digest(receipt_payload)
        return canonical_bytes(receipt_payload).decode("utf-8")

    attempt_receipt = con.execute(
        "SELECT result_json FROM attempts WHERE attempt_id=?", (repair2_attempt,)
    ).fetchone()[0]
    job_receipt = con.execute(
        "SELECT result_json FROM jobs WHERE job_id=?", (repair2,)
    ).fetchone()[0]
    con.close()

    def mutate_events(db):
        db.execute(
            "UPDATE events SET payload_json=? WHERE command_id=?",
            (
                canonical_bytes(seal).decode("utf-8"),
                f"orchestration-result-seal:{repair2_attempt}",
            ),
        )

    def mutate_attempts(db):
        db.execute(
            "UPDATE attempts SET result_json=? WHERE attempt_id=?",
            (reforged(attempt_receipt), repair2_attempt),
        )

    def mutate_jobs(db):
        db.execute(
            "UPDATE jobs SET result_json=? WHERE job_id=?",
            (reforged(job_receipt), repair2),
        )
        db.execute(
            "UPDATE jobs SET supersedes_job_id=? WHERE job_id=?", (repair2, repair2)
        )
        db.execute(
            "UPDATE jobs SET reviews_job_id=? WHERE job_id=?", (repair2, review1)
        )

    _with_triggers_dropped(_db_path(tmp_path), "events_are_immutable_update", mutate_events)
    _with_triggers_dropped(
        _db_path(tmp_path), "terminal_attempts_are_immutable", mutate_attempts
    )
    _with_triggers_dropped(
        _db_path(tmp_path),
        ["jobs_orchestration_fields_immutable", "jobs_hierarchy_is_immutable"],
        mutate_jobs,
    )
    reopened = Runtime.at(tmp_path)
    with pytest.raises(StateConflict, match="active cycle"):
        _select_bounded(
            reopened, root.job_id, job_id, attempt_id, expected.result_digest
        )


def test_identity_checks_precede_payload_projection(max_chain, tmp_path):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    probes = []
    original = er._validated_role_completion_snapshot

    def spy(*args, **kwargs):
        probes.append(args)
        return original(*args, **kwargs)

    wrong_cases = {
        "wrong_root": (nodes[0][0], job_id, attempt_id),
        "nonexistent_job": (root.job_id, "JOB-DOES-NOT-EXIST", attempt_id),
        "wrong_attempt": (root.job_id, job_id, "ATT-DOES-NOT-EXIST"),
    }
    reopened = Runtime.at(tmp_path)
    for case, (root_id, job, attempt) in wrong_cases.items():
        probes.clear()
        er._validated_role_completion_snapshot = spy
        try:
            with pytest.raises(StateConflict):
                _select_bounded(
                    reopened, root_id, job, attempt, expected.result_digest
                )
            assert not probes, case
        finally:
            er._validated_role_completion_snapshot = original
    probes.clear()
    er._validated_role_completion_snapshot = spy
    try:
        snapshot = _select_bounded(
            reopened, root.job_id, job_id, attempt_id, expected.result_digest
        )
        assert probes and snapshot.completion == expected
    finally:
        er._validated_role_completion_snapshot = original


def test_expected_digest_binds_result_envelope_digest_not_role_digest(max_chain):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    assert expected.role_result_digest != expected.result_digest
    with pytest.raises(StateConflict, match="expected canonical digest"):
        _select_bounded(
            runtime,
            root.job_id,
            job_id,
            attempt_id,
            expected.role_result_digest,
        )


def test_foreign_and_non_root_refusals(max_chain):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    # A work job is not a strict v2 aggregation root.
    with pytest.raises(StateConflict, match="binding is not current"):
        _select_bounded(
            runtime, nodes[0][0], job_id, attempt_id, expected.result_digest
        )
    # Blank or malformed tokens refuse before any SQL.
    with pytest.raises(StateConflict):
        _select_bounded(runtime, "", job_id, attempt_id, expected.result_digest)
    with pytest.raises(StateConflict):
        _select_bounded(
            runtime, root.job_id, job_id, attempt_id, "not-a-digest"
        )
    with pytest.raises(TypeError):
        runtime.observe_bounded_read(before=2)


def test_nonexistent_job_error_matches_legacy(max_chain):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    with pytest.raises(StateConflict) as legacy:
        runtime.validated_role_completion("JOB-NOPE", expected_attempt_id="ATT-NOPE")
    with pytest.raises(StateConflict) as bounded:
        _select_bounded(runtime, root.job_id, "JOB-NOPE", "ATT-NOPE", expected.result_digest)
    assert str(bounded.value) == str(legacy.value)


def test_current_attempt_drift_refusal_matches_legacy_semantics(max_chain):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    with pytest.raises(StateConflict, match="binding is not current"):
        _select_bounded(
            runtime, root.job_id, job_id, "ATT-NOT-CURRENT", expected.result_digest
        )


# ---------------------------------------------------------------------------
# Fixed selection, receipt and namespace law
# ---------------------------------------------------------------------------


def test_one_selection_per_observation(max_chain):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    with runtime.observe_bounded_read() as observation:
        snapshot = observation.read_role_result_bounded(
            root.job_id,
            job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=expected.result_digest,
        )
        assert snapshot.completion == expected
        with pytest.raises(StateConflict):
            observation.read_role_result_bounded(
                root.job_id,
                job_id,
                expected_attempt_id=attempt_id,
                expected_result_envelope_digest=expected.result_digest,
            )
        with pytest.raises(StateConflict):
            observation.read_job_root_bounded(root.job_id)
    with pytest.raises(StateConflict):
        _ = observation.receipt


def test_unbound_writer_receipt_stays_unknown(max_chain):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    with runtime.observe_bounded_read() as observation:
        observation.read_role_result_bounded(
            root.job_id,
            job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=expected.result_digest,
        )
    assert observation.receipt.state == "UNKNOWN"
    assert observation.receipt.source_identity is None


@pytest.fixture
def bound_chain(tmp_path):
    runtime, root, nodes = complete_maximum_chain(tmp_path)
    job_id, attempt_id, _ = nodes[-1]
    expected = runtime.validated_role_completion(job_id, expected_attempt_id=attempt_id)
    keeper = er.sqlite3.connect(runtime.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(runtime.store.path)
    binding = er.RuntimeReadBinding(namespace)
    reader = Runtime.at(tmp_path, create=False, read_binding=binding)
    try:
        yield runtime, reader, namespace, binding, root, job_id, attempt_id, expected
    finally:
        keeper.close()
        if binding._unclosed_connection is not None:
            er.sqlite3.Connection.close(binding._unclosed_connection)
        if binding._retained_namespace is not None:
            binding._retained_namespace.close()


def test_write_during_observation_conflicts_receipt(bound_chain):
    (runtime, reader, _namespace, _binding, root, job_id, attempt_id,
     expected) = bound_chain
    with reader.observe_bounded_read() as observation:
        snapshot = observation.read_role_result_bounded(
            root.job_id,
            job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=expected.result_digest,
        )
        assert snapshot.completion == expected
        with runtime.store.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET objective=? WHERE job_id=?",
                ("changed during observation", root.job_id),
            )
    assert observation.receipt.state == "CONFLICT"
    assert observation.receipt.before != observation.receipt.after


def test_quiet_observation_finalizes_same_receipt(bound_chain):
    (runtime, reader, _namespace, _binding, root, job_id, attempt_id,
     expected) = bound_chain
    with reader.observe_bounded_read() as observation:
        observation.read_role_result_bounded(
            root.job_id,
            job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=expected.result_digest,
        )
    assert observation.receipt.state == "SAME"
    assert observation.receipt.before == observation.receipt.after


@pytest.mark.parametrize("target", ["database", "wal"])
def test_physical_namespace_replacement_never_qualifies(bound_chain, target):
    (runtime, reader, namespace, _binding, root, job_id, attempt_id,
     expected) = bound_chain
    with pytest.raises(er.RuntimeReadUnavailable):
        with reader.observe_bounded_read() as observation:
            observation.read_role_result_bounded(
                root.job_id,
                job_id,
                expected_attempt_id=attempt_id,
                expected_result_envelope_digest=expected.result_digest,
            )
            victim = (
                runtime.store.path
                if target == "database"
                else runtime.store.path.with_name(
                    runtime.store.path.name + "-" + target
                )
            )
            replacement = victim.with_name(victim.name + ".replacement")
            replacement.write_bytes(victim.read_bytes())
            # Deliberately bypass the fixture's exclusion actor.
            replacement.replace(victim)
    with pytest.raises(StateConflict):
        _ = observation.receipt
    assert namespace.exits == 1


def test_physical_close_uncertainty_leaves_no_receipt(bound_chain, monkeypatch):
    (runtime, reader, _namespace, _binding, root, job_id, attempt_id,
     expected) = bound_chain

    def fail(self):
        self._retain_uncertain()
        raise er.RuntimeReadUnavailable("fixture close unknown")

    monkeypatch.setattr(er._BoundReadConnection, "_drain_and_close", fail)
    with pytest.raises(er.RuntimeReadUnavailable):
        with reader.observe_bounded_read() as observation:
            observation.read_role_result_bounded(
                root.job_id,
                job_id,
                expected_attempt_id=attempt_id,
                expected_result_envelope_digest=expected.result_digest,
            )
    with pytest.raises(StateConflict):
        _ = observation.receipt


# ---------------------------------------------------------------------------
# Connection ownership, real SQL shape, measured budgets
# ---------------------------------------------------------------------------


def test_selection_runs_on_fresh_private_connection_with_guard_sql(
    max_chain, monkeypatch
):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    traces, opened = [], []
    original_connect = er.sqlite3.connect

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connection.set_trace_callback(traces.append)
        opened.append(connection)
        return connection

    monkeypatch.setattr(er.sqlite3, "connect", connect)
    monkeypatch.setattr(
        runtime.events, "list_events", lambda **kw: pytest.fail("legacy history")
    )
    with runtime.observe_bounded_read() as observation:
        for name in ("connection", "execute", "cursor", "token", "list_events"):
            assert not hasattr(observation, name)
        snapshot = observation.read_role_result_bounded(
            root.job_id,
            job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=expected.result_digest,
        )
    assert snapshot.completion == expected
    normalized = [" ".join(sql.split()) for sql in traces]
    tokens = [i for i, sql in enumerate(normalized) if sql.upper() == "PRAGMA DATA_VERSION"]
    assert len(tokens) == 2
    assert tokens[0] < normalized.index("BEGIN") < normalized.index("COMMIT") < tokens[1]
    # The size-only predecode projection is real SQLite work on this connection.
    assert any("length(CAST" in sql and "COUNT(*)" in sql for sql in normalized)
    assert len(opened) == 1
    with pytest.raises(er.sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_measured_maximum_chain_stays_within_all_fixed_budgets(
    max_chain, monkeypatch
):
    runtime, root, nodes, job_id, attempt_id, expected = max_chain
    created = []

    class RecordingLoader(er._BoundedRoleResultLoader):
        def __init__(self, connection):
            super().__init__(connection)
            self.begins = 0
            created.append(self)

        def _node_begin(self, job_id):
            self.begins += 1
            return super()._node_begin(job_id)

    monkeypatch.setattr(er, "_BoundedRoleResultLoader", RecordingLoader)
    with runtime.observe_bounded_read() as observation:
        snapshot = observation.read_role_result_bounded(
            root.job_id,
            job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=expected.result_digest,
        )
    assert snapshot.completion == expected
    loader = created[0]
    # Measured, not assumed: the genuine two-repair closure fits every fixed
    # admission budget with the ceiling fully populated (six completed nodes).
    assert loader.begins == er.BOUNDED_ROLE_RESULT_MAX_NODES
    assert len(loader._node_memo) == er.BOUNDED_ROLE_RESULT_MAX_NODES
    assert not loader._active_nodes
    assert 100 <= loader._statements <= er.BOUNDED_ROLE_RESULT_MAX_STATEMENTS
    assert 60 <= loader._rows <= er.BOUNDED_ROLE_RESULT_MAX_ROWS
    assert 100_000 <= loader._total_bytes <= er.BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES
    assert observation._vm_progress.steps <= er.BOUNDED_ROLE_RESULT_MAX_VM_STEPS
    assert not observation._vm_progress.tripped


# Exact observation binding uses the existing Runtime-issued identity.


def test_bound_results_pair_only_with_their_own_finalized_receipt(tmp_path):
    writer, root, nodes = complete_maximum_chain(tmp_path)
    expected = [writer.validated_role_completion(job_id, expected_attempt_id=attempt_id)
                for job_id, attempt_id, _seal in nodes[:2]]
    keeper = sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute('SELECT 1 FROM jobs').fetchone()
    namespace = ObservationNamespace(writer.store.path)
    binding = RuntimeReadBinding(namespace)
    reader = Runtime.at(writer.store.root, create=False, read_binding=binding)
    results = []
    receipts = []
    try:
        for completion in expected:
            with reader.observe_bounded_read() as observation:
                result = observation.read_role_result_bounded(
                    root.job_id, completion.job.job_id,
                    expected_attempt_id=completion.attempt.attempt_id,
                    expected_result_envelope_digest=completion.result_digest,
                )
                with pytest.raises(StateConflict):
                    _ = observation.receipt
            results.append(result)
            receipts.append(observation.receipt)
        for result, receipt in zip(results, receipts):
            assert receipt.state == 'SAME'
            assert re.fullmatch('[0-9a-f]{32}', result.observation_source_identity)
            assert result.observation_source_identity == receipt.source_identity
        assert results[0].observation_source_identity != receipts[1].source_identity
        assert results[1].observation_source_identity != receipts[0].source_identity
    finally:
        keeper.close()


def test_unbound_result_identity_is_none_and_receipt_is_unknown(tmp_path):
    runtime, root, nodes = complete_maximum_chain(tmp_path)
    job_id, attempt_id, _seal = nodes[0]
    completion = runtime.validated_role_completion(job_id, expected_attempt_id=attempt_id)
    with runtime.observe_bounded_read() as observation:
        result = observation.read_role_result_bounded(
            root.job_id, job_id,
            expected_attempt_id=attempt_id,
            expected_result_envelope_digest=completion.result_digest,
        )
    assert result.observation_source_identity is None
    assert observation.receipt.source_identity is None
    assert observation.receipt.state == 'UNKNOWN'


def test_canonical_completed_aggregation_root_is_a_supported_role(tmp_path, monkeypatch):
    from tests import test_executive_os_phase1fc as fixtures

    complete = fixtures._complete_ohf_role
    observed = []

    def observe_completed_aggregation(runtime, dispatch, role_body, **kwargs):
        result = complete(runtime, dispatch, role_body, **kwargs)
        if role_body.get('schema_version') == 'mastermind.aggregation_result/v1':
            job = runtime.jobs.get_job(dispatch.attempt.job_id)
            expected = runtime.validated_role_completion(
                job.job_id, expected_attempt_id=dispatch.attempt.attempt_id,
            )
            assert job.orchestration_role == 'aggregation'
            assert job.root_job_id == job.job_id
            actual = _select_bounded(
                runtime, job.job_id, expected.job.job_id,
                expected.attempt.attempt_id, expected.result_digest,
            )
            assert actual.completion == expected
            observed.append(job.job_id)
        return result

    monkeypatch.setattr(fixtures, '_complete_ohf_role', observe_completed_aggregation)
    fixtures.test_run_once_typed_plan_work_independent_review_and_aggregation_complete(tmp_path)
    assert len(observed) == 1



def test_size_guard_iterator_preserves_every_real_sqlite_row():
    connection = sqlite3.connect(':memory:')
    try:
        loader = er._BoundedRoleResultLoader(connection)
        rows = list(loader.execute('SELECT 1 AS value UNION ALL SELECT 2 UNION ALL SELECT 3'))
        assert rows == [(1,), (2,), (3,)]
        assert loader._statements == 2
        assert loader._rows == 4  # The size-only aggregate is a returned row too.
    finally:
        connection.close()


def test_physical_statement_budget_counts_size_queries_before_execution():
    connection = sqlite3.connect(':memory:')
    statements = []
    connection.set_trace_callback(statements.append)
    try:
        loader = er._BoundedRoleResultLoader(connection)
        for _ in range(128):
            assert loader.execute('SELECT 1 AS value').fetchone() == (1,)
        assert len(statements) == 256
        with pytest.raises(er.RuntimeRoleResultOverBudget):
            loader.execute('SELECT 1 AS value')
        assert len(statements) == 256
    finally:
        connection.close()


def test_real_returned_row_budget_includes_size_metadata():
    connection = sqlite3.connect(':memory:')
    try:
        loader = er._BoundedRoleResultLoader(connection)
        sql = ('WITH RECURSIVE numbers(value) AS '
               '(SELECT 1 UNION ALL SELECT value+1 FROM numbers WHERE value<512) '
               'SELECT value FROM numbers')
        with pytest.raises(er.RuntimeRoleResultOverBudget):
            loader.execute(sql)
        assert loader._rows == 1
    finally:
        connection.close()


def test_legacy_observation_work_does_not_activate_result_vm_budget(max_chain):
    runtime, root, _nodes, _job, _attempt, _expected = max_chain
    with runtime.observe_bounded_read() as observation:
        # Real SQLite work exceeds the result ceiling on the same connection.
        # This is a handler-lifetime regression, not a new public SQL API.
        result = observation._connection.execute(
            'WITH RECURSIVE numbers(value) AS '
            '(SELECT 1 UNION ALL SELECT value+1 FROM numbers WHERE value<30000) '
            'SELECT SUM(value) FROM numbers'
        ).fetchone()[0]
        assert result == 450015000
        observation.read_job_root_bounded(root.job_id)
        assert observation._vm_progress.steps == 0
        assert not observation._vm_progress.tripped
    assert observation.receipt.state == 'UNKNOWN'


def test_unbound_handler_removal_failure_still_physically_closes(max_chain, monkeypatch):
    runtime, root, _nodes, job, attempt, expected = max_chain
    native_connect = sqlite3.connect
    opened = []

    class ObservedConnection(sqlite3.Connection):
        physically_closed = False

        def close(self):
            super().close()
            self.physically_closed = True

    def connect(*args, **kwargs):
        connection = native_connect(*args, factory=ObservedConnection, **kwargs)
        opened.append(connection)
        return connection

    def fail_removal(self, guard):
        raise er.RuntimeReadUnavailable('injected handler removal uncertainty')

    monkeypatch.setattr(sqlite3, 'connect', connect)
    monkeypatch.setattr(er.RuntimeStore, '_remove_read_progress_guard', fail_removal)
    with pytest.raises(er.RuntimeReadUnavailable, match='removal uncertainty'):
        with runtime.observe_bounded_read() as observation:
            observation.read_role_result_bounded(
                root.job_id, job, expected_attempt_id=attempt,
                expected_result_envelope_digest=expected.result_digest,
            )
    assert len(opened) == 1
    assert opened[0].physically_closed
    with pytest.raises(StateConflict):
        _ = observation.receipt


@pytest.mark.parametrize('field,value', [
    ('root', ' JOB-1'), ('job', 'JOB-1 '), ('attempt', 'ATT-\n'),
    ('root', 3), ('job', 'A' * 129), ('digest', 'a' * 64 + ' '),
])
def test_result_identity_inputs_use_existing_closed_tokens(max_chain, field, value):
    runtime, root, _nodes, job, attempt, expected = max_chain
    values = {'root': root.job_id, 'job': job, 'attempt': attempt,
              'digest': expected.result_digest}
    values[field] = value
    with pytest.raises(StateConflict):
        _select_bounded(runtime, values['root'], values['job'],
                        values['attempt'], values['digest'])
