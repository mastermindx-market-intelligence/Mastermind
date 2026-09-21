"""Focused verification for the shared pure Fabric role result projector.

Contract: ``control_plane.fabric_result_projection.project_fabric_role_result``
projects the ACTUAL ``BoundedRoleResultSnapshot`` (its real
``ValidatedRoleCompletion``, ``BoundedRoleResultRootMetadata`` and finalized
``RuntimeReadObservationReceipt``) into the frozen
``mastermind.fabric_role_result_view.v1`` document pair.

Every success case here is an actual bounded Runtime selection over a real
canonical completion — the six-node second-repair OHF chain, a sealed-worker
supervisor planner, and an all-severity review chain — read after observation
close through a real ``RuntimeReadBinding``.  Narrow ``dataclasses.replace``
mutations of those actual objects cover the refusal surface; nothing mocks a
validator and no fake Runtime or shadow DTO is ever fed to the projector.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import importlib
import os
import pwd
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

from common.commission_ref import CommissionRef
from control_plane import executive_runtime as er
from control_plane import fabric_result_projection as frp
from control_plane.ceo_intent import submit_intent
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import Runtime, RuntimeReadBinding
from control_plane.executive_supervisor import ExecutiveSupervisor
from tests.test_executive_os_phase1fc import (
    RESULT_SCHEMA,
    _complete_ohf_role,
    _cycle_through_completed_work,
    _register,
    _review_body,
    _v2_intent,
)
from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_executive_runtime_bounded_role_result import complete_maximum_chain
from tests.test_executive_supervisor import FakeInspector, FakeProcessController
from tests.test_executive_terminal_return import (
    _PlannerSealedWorkerAdapter,
    _SEALED_WORKER_SECRET_CANARY,
)

_DOCUMENT_KEYS = [
    "schema", "selection", "role", "execution_status", "acceptance",
    "role_result_digest", "generation", "availability", "content_complete",
    "review", "counts", "content", "omitted",
]
_SELECTION_KEYS = ["root_job_id", "job_id", "attempt_id", "result_envelope_digest"]
_GENERATION_KEYS = ["schema", "state", "source_identity", "before", "after"]
_REVIEW_KEYS = [
    "verdict", "reviewed_job_id", "reviewed_attempt_id",
    "reviewed_result_digest", "latest_revision_currentness",
]
_COUNTS_KEYS = ["findings", "next_actions"]
_FINDING_COUNT_KEYS = ["total", "blocking", "warning", "info"]
_OMITTED = ["role_result", "summary", "next_actions"]


# ---------------------------------------------------------------------------
# actual owner fixtures (bound reads over real canonical completions)
# ---------------------------------------------------------------------------


def _bound_reader(runtime: Runtime):
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    namespace = ObservationNamespace(runtime.store.path)
    binding = RuntimeReadBinding(namespace)
    reader = Runtime.at(runtime.store.root, create=False, read_binding=binding)
    return keeper, namespace, binding, reader


def _release(keeper, binding) -> None:
    keeper.close()
    if binding._unclosed_connection is not None:
        er.sqlite3.Connection.close(binding._unclosed_connection)
    if binding._retained_namespace is not None:
        binding._retained_namespace.close()


def _select_bound(reader: Runtime, root_id: str, completion):
    """One closed observation: select after open, take the receipt after close."""

    with reader.observe_bounded_read() as observation:
        snapshot = observation.read_role_result_bounded(
            root_id,
            completion.job.job_id,
            expected_attempt_id=completion.attempt.attempt_id,
            expected_result_envelope_digest=completion.result_digest,
        )
    return snapshot, observation.receipt


@pytest.fixture(scope="module")
def bound_max_chain():
    # One actual six-node chain and one bound reader serve every focused
    # case in this module; each case opens its own single-selection
    # observation, exactly as the trusted caller would.
    base = Path(tempfile.mkdtemp()).resolve()
    runtime, root, nodes = complete_maximum_chain(base)
    expected = [
        runtime.validated_role_completion(job_id, expected_attempt_id=attempt_id)
        for job_id, attempt_id, _seal in nodes
    ]
    keeper, _namespace, binding, reader = _bound_reader(runtime)
    try:
        yield runtime, root, nodes, expected, reader
    finally:
        _release(keeper, binding)
        shutil.rmtree(base, ignore_errors=True)


def complete_all_severity_chain(directory: Path):
    """One actual OHF chain whose single review rejects with every severity."""

    runtime, cycle, dispatches, root, planner, current, seal = (
        _cycle_through_completed_work(
            directory,
            intent_id="CEO-BOUNDED-ALL-SEVERITY",
            review_workers=["worker-b"],
        )
    )
    plan_digest = str(runtime.jobs.get_job(current.attempt.job_id).plan_digest)
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    body = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=current.attempt.job_id,
        target_attempt_id=current.attempt.attempt_id,
        target_result_digest=seal["role_result_digest"],
        repair_round=0,
        verdict="reject",
    )
    body["findings"] = [
        {"code": "REPAIR_REQUIRED", "severity": "blocking",
         "message": "One repair is required.", "evidence_digests": []},
        {"code": "DOCUMENTATION_DRIFT", "severity": "warning",
         "message": "Documentation drifted.", "evidence_digests": []},
        {"code": "NOTE_ALPHA", "severity": "info",
         "message": "A minor note.", "evidence_digests": []},
        {"code": "NOTE_BETA", "severity": "info",
         "message": "Another minor note.", "evidence_digests": []},
    ]
    _complete_ohf_role(runtime, review, body, identity_seed=8600)
    work_expected = runtime.validated_role_completion(
        current.attempt.job_id, expected_attempt_id=current.attempt.attempt_id
    )
    review_expected = runtime.validated_role_completion(
        review.attempt.job_id, expected_attempt_id=review.attempt.attempt_id
    )
    return runtime, root, work_expected, review_expected


@pytest.fixture
def all_severity_chain(tmp_path, monkeypatch):
    """Actual chain builder with positive outer next_actions in the envelope.

    The encoder wrapper only enriches the fixture's own result envelopes
    before they are sealed; every Runtime boundary, seal, and canonical
    validator then runs unchanged over the enriched content.
    """
    import tests.test_executive_os_phase1fc as fixtures

    original = fixtures.result_canonical_bytes

    def encode_with_next_actions(value):
        if (
            isinstance(value, dict)
            and value.get("schema_version") == RESULT_SCHEMA
            and value.get("next_actions") == []
        ):
            value["next_actions"] = [
                "publish the bounded handoff digest",
                "archive the review evidence",
            ]
        return original(value)

    monkeypatch.setattr(fixtures, "result_canonical_bytes", encode_with_next_actions)
    runtime, root, work_expected, review_expected = complete_all_severity_chain(tmp_path)
    keeper, _namespace, binding, reader = _bound_reader(runtime)
    try:
        yield runtime, root, work_expected, review_expected, reader
    finally:
        _release(keeper, binding)


@pytest.fixture
def bound_sealed_worker_planner(tmp_path):
    """The second terminal family: a real sealed-worker supervisor planner."""

    runtime_root = tmp_path / "runtime"
    runtime = Runtime.at(runtime_root)
    _register(runtime, "worker-a")
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "planner"
    workspace.mkdir(parents=True, mode=0o700)
    admitted = submit_intent(
        runtime,
        _v2_intent(
            intent_id="CEO-SEALED-WORKER-PROJECTOR",
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
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        )
    )
    assert receipt.attempt.status.value == "COMPLETED"
    expected = runtime.validated_role_completion(
        planner.job_id, expected_attempt_id=receipt.attempt.attempt_id
    )
    assert expected.execution_mode == "SEALED_WORKER"
    keeper, _namespace, binding, reader = _bound_reader(runtime)
    try:
        yield runtime, root, expected, reader
    finally:
        _release(keeper, binding)


def _dialogue_source(work_ref: str):
    return er.ExecutiveDialogueSource(
        schema_version=er.EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
        work_ref=work_ref,
        commission_ref=CommissionRef(
            "acme-co/mastermind", "a" * 40, "research/probe.md", "b" * 64
        ),
        watch_mode=None,
    )


# ---------------------------------------------------------------------------
# the actual owner seam (the repaired ACTUAL-OWNER-RED)
# ---------------------------------------------------------------------------


def test_actual_bound_six_node_review_chain_projects(bound_max_chain):
    runtime, root, nodes, expected, reader = bound_max_chain
    completion = expected[-1]
    snapshot, receipt = _select_bound(reader, root.job_id, completion)

    # The exact ACTUAL-OWNER-RED scenario: six-node second-repair chain,
    # selected review JOB-008 under root JOB-001, SAME finalized receipt.
    assert snapshot.job_id == "JOB-008" and snapshot.root_job_id == "JOB-001"
    assert receipt.state == "SAME"
    assert receipt.before == receipt.after
    assert receipt.source_identity == snapshot.observation_source_identity
    assert snapshot.result_envelope_digest == completion.result_digest

    projection = frp.project_fabric_role_result(snapshot, receipt)
    complete, over = projection.complete, projection.content_over_budget

    assert list(complete) == _DOCUMENT_KEYS
    assert complete["schema"] == frp.FABRIC_ROLE_RESULT_VIEW_SCHEMA
    assert complete["selection"] == {
        "root_job_id": root.job_id,
        "job_id": snapshot.job_id,
        "attempt_id": snapshot.attempt_id,
        "result_envelope_digest": completion.result_digest,
    }
    assert list(complete["selection"]) == _SELECTION_KEYS
    assert complete["role"] == "review"
    assert complete["execution_status"] == "COMPLETED"
    assert complete["acceptance"] == "NOT_PROJECTED"
    assert complete["role_result_digest"] == completion.role_result_digest
    assert complete["role_result_digest"] == canonical_digest(
        completion.result_envelope["role_result"]
    )
    assert complete["generation"] == receipt.to_dict()
    assert list(complete["generation"]) == _GENERATION_KEYS
    assert complete["availability"] == "AVAILABLE"
    assert complete["content_complete"] is True

    # The approving review: exact closed tuple, always scoped UNPROVEN, and
    # reviewed_result_digest is the reviewed repair's ROLE RESULT digest —
    # never the envelope selector digest.
    reviewed = expected[-2]
    assert list(complete["review"]) == _REVIEW_KEYS
    assert complete["review"]["verdict"] == "approve"
    assert complete["review"]["reviewed_job_id"] == reviewed.job.job_id
    assert complete["review"]["reviewed_attempt_id"] == reviewed.attempt.attempt_id
    assert complete["review"]["reviewed_result_digest"] == reviewed.role_result_digest
    assert reviewed.role_result_digest != reviewed.result_digest
    assert complete["review"]["latest_revision_currentness"] == "UNPROVEN"

    assert list(complete["counts"]) == _COUNTS_KEYS
    assert complete["counts"]["findings"] == {"total": 0, "blocking": 0, "warning": 0, "info": 0}
    assert list(complete["counts"]["findings"]) == _FINDING_COUNT_KEYS
    assert type(complete["counts"]["next_actions"]) is int
    assert complete["counts"]["next_actions"] == len(completion.result_envelope["next_actions"])
    assert complete["content"]["role_result"] == completion.result_envelope["role_result"]
    assert complete["content"]["summary"] == completion.result_envelope["summary"]
    assert complete["content"]["next_actions"] == completion.result_envelope["next_actions"]
    assert complete["omitted"] == []

    # No raw owner material leaks into the wire document.
    document_text = repr(complete)
    for forbidden in ("launch_metadata", "effective_grant", "placement_snapshot",
                      "provider_session_id", "lease_token", "stdout_path", "checkpoint"):
        assert forbidden not in document_text
    assert "work_ref" not in document_text


def test_every_role_in_actual_chain_projects(bound_max_chain):
    runtime, root, nodes, expected, reader = bound_max_chain
    roles = ["work", "review", "repair", "review", "repair", "review"]
    for completion, role in zip(expected, roles):
        snapshot, receipt = _select_bound(reader, root.job_id, completion)
        assert snapshot.completion == completion
        projection = frp.project_fabric_role_result(snapshot, receipt)
        complete = projection.complete
        assert complete["role"] == role
        assert complete["selection"]["job_id"] == completion.job.job_id
        assert complete["role_result_digest"] == completion.role_result_digest
        assert complete["generation"] == receipt.to_dict()
        if role == "review":
            assert complete["review"] is not None
            assert complete["review"]["verdict"] == completion.result_envelope["role_result"]["verdict"]
            findings = completion.result_envelope["role_result"]["findings"]
            assert complete["counts"]["findings"]["total"] == len(findings)
        else:
            assert complete["review"] is None
            assert complete["counts"]["findings"] is None
        assert complete["counts"]["next_actions"] == len(
            completion.result_envelope["next_actions"]
        )


def test_review_reject_all_severity_counts_and_positive_next_actions(all_severity_chain):
    runtime, root, work_expected, review_expected, reader = all_severity_chain
    snapshot, receipt = _select_bound(reader, root.job_id, review_expected)
    projection = frp.project_fabric_role_result(snapshot, receipt)
    complete, over = projection.complete, projection.content_over_budget

    assert complete["role"] == "review"
    assert complete["review"]["verdict"] == "reject"
    assert complete["counts"]["findings"] == {"total": 4, "blocking": 1, "warning": 1, "info": 2}
    assert complete["counts"]["next_actions"] == 2
    assert complete["content"]["next_actions"] == review_expected.result_envelope["next_actions"]
    assert complete["content"]["role_result"]["findings"][0]["severity"] == "blocking"
    # The fallback document carries the same exact counts — never nulls.
    assert over["counts"] == complete["counts"]
    assert over["counts"]["findings"] == {"total": 4, "blocking": 1, "warning": 1, "info": 2}
    assert type(over["counts"]["next_actions"]) is int
    # The reviewed target is the work node's ROLE RESULT digest.
    assert complete["review"]["reviewed_result_digest"] == work_expected.role_result_digest
    assert work_expected.role_result_digest != work_expected.result_digest


def test_sealed_worker_family_actual_projection(bound_sealed_worker_planner):
    runtime, root, expected, reader = bound_sealed_worker_planner
    snapshot, receipt = _select_bound(reader, root.job_id, expected)
    assert snapshot.completion.execution_mode == "SEALED_WORKER"
    projection = frp.project_fabric_role_result(snapshot, receipt)
    complete = projection.complete
    assert complete["role"] == "plan"
    assert complete["review"] is None
    assert complete["counts"]["findings"] is None
    assert complete["counts"]["next_actions"] == len(expected.result_envelope["next_actions"])
    assert complete["selection"]["root_job_id"] == root.job_id


def test_actual_aggregation_root_completion_projects(tmp_path, monkeypatch):
    from tests import test_executive_os_phase1fc as fixtures

    complete = fixtures._complete_ohf_role
    captured = []

    def observe_completed_aggregation(runtime, dispatch, role_body, **kwargs):
        result = complete(runtime, dispatch, role_body, **kwargs)
        if role_body.get("schema_version") == "mastermind.aggregation_result/v1":
            captured.append(
                (runtime, dispatch.attempt.job_id, dispatch.attempt.attempt_id)
            )
        return result

    monkeypatch.setattr(fixtures, "_complete_ohf_role", observe_completed_aggregation)
    fixtures.test_run_once_typed_plan_work_independent_review_and_aggregation_complete(tmp_path)
    assert len(captured) == 1
    runtime, job_id, attempt_id = captured[0]
    expected = runtime.validated_role_completion(job_id, expected_attempt_id=attempt_id)
    keeper, _namespace, binding, reader = _bound_reader(runtime)
    try:
        snapshot, receipt = _select_bound(reader, expected.job.root_job_id, expected)
        projection = frp.project_fabric_role_result(snapshot, receipt)
    finally:
        _release(keeper, binding)
    complete = projection.complete
    assert complete["role"] == "aggregation"
    assert complete["review"] is None
    assert complete["counts"]["findings"] is None
    assert complete["counts"]["next_actions"] == len(expected.result_envelope["next_actions"])
    assert complete["selection"]["root_job_id"] == expected.job.root_job_id
    assert complete["selection"]["job_id"] == expected.job.job_id


# ---------------------------------------------------------------------------
# exact fallback document law
# ---------------------------------------------------------------------------


def test_over_budget_document_is_the_exact_null_content_fallback(bound_max_chain):
    runtime, root, nodes, expected, reader = bound_max_chain
    completion = expected[1]  # a rejecting review with one blocking finding
    snapshot, receipt = _select_bound(reader, root.job_id, completion)
    projection = frp.project_fabric_role_result(snapshot, receipt)
    complete, over = projection.complete, projection.content_over_budget

    assert list(over) == _DOCUMENT_KEYS
    for field in ("schema", "selection", "role", "execution_status", "acceptance",
                  "role_result_digest", "generation", "review"):
        assert over[field] == complete[field]
    assert over["availability"] == "CONTENT_OVER_BUDGET"
    assert over["content_complete"] is False
    assert over["content"] is None
    assert over["omitted"] == _OMITTED
    assert over["counts"] == complete["counts"]
    assert over["counts"]["findings"] == {"total": 1, "blocking": 1, "warning": 0, "info": 0}
    assert over is not complete


# ---------------------------------------------------------------------------
# narrow mutations of actual inputs: selection, provenance, digests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda s: dataclasses.replace(s, root_job_id="JOB-999"), "selection_invalid"),
        (lambda s: dataclasses.replace(s, job_id="JOB-999"), "selection_invalid"),
        (lambda s: dataclasses.replace(s, attempt_id="ATT-999"), "selection_invalid"),
        (lambda s: dataclasses.replace(s, result_envelope_digest="0" * 64), "digest_mismatch"),
    ],
)
def test_wrong_root_job_attempt_digest_refused(bound_max_chain, mutation, code):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[-1])
    with pytest.raises(frp.FabricResultProjectionError) as info:
        frp.project_fabric_role_result(mutation(snapshot), receipt)
    assert info.value.args[0] == code


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda m: dataclasses.replace(m, job_id="JOB-999"), "selection_invalid"),
        (lambda m: dataclasses.replace(m, root_job_id="JOB-999"), "selection_invalid"),
        (lambda m: dataclasses.replace(m, orchestration_role="work"), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, creation_command_id="coo-cycle:probe"), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, creation_command_id="ceo-intent:"), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, creation_command_id=1), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, creation_command_id=True), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, creation_command_id=["ceo-intent:abc"]), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, creation_command_id={"x": "ceo-intent:abc"}), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, orchestration_provenance_digest="A" * 64), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, source_digest="nothex"), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, source_digest="0" * 63), "root_metadata_invalid"),
        (lambda m: dataclasses.replace(m, work_ref=""), "root_metadata_invalid"),
    ],
)
def test_root_provenance_mutation_refused(bound_max_chain, mutation, code):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[-1])
    snapshot = dataclasses.replace(
        snapshot, root_metadata=mutation(snapshot.root_metadata)
    )
    with pytest.raises(frp.FabricResultProjectionError) as info:
        frp.project_fabric_role_result(snapshot, receipt)
    assert info.value.args[0] == code


def test_work_ref_agreement_with_canonical_dialogue_source(bound_max_chain):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[-1])
    agreeing = dataclasses.replace(
        snapshot,
        completion=dataclasses.replace(
            snapshot.completion, dialogue_source=_dialogue_source("WS:AGREED-1")
        ),
        root_metadata=dataclasses.replace(snapshot.root_metadata, work_ref="WS:AGREED-1"),
    )
    projection = frp.project_fabric_role_result(agreeing, receipt)
    assert "work_ref" not in repr(projection.complete)

    disagreeing = dataclasses.replace(
        agreeing, root_metadata=dataclasses.replace(snapshot.root_metadata, work_ref="WS:OTHER-1")
    )
    with pytest.raises(frp.FabricResultProjectionError) as info:
        frp.project_fabric_role_result(disagreeing, receipt)
    assert info.value.args[0] == "root_metadata_invalid"


@pytest.mark.parametrize(
    "mutate_completion, code",
    [
        (lambda c: dataclasses.replace(c, result_digest="0" * 64), "digest_mismatch"),
        (lambda c: dataclasses.replace(c, role_result_digest="0" * 64), "digest_mismatch"),
        (
            lambda c: dataclasses.replace(
                c, result_envelope={**c.result_envelope, "summary": "tampered"}
            ),
            "digest_mismatch",
        ),
        (
            lambda c: dataclasses.replace(
                c,
                result_envelope={
                    **c.result_envelope,
                    "role_result": {
                        **c.result_envelope["role_result"],
                        "findings": [
                            {**c.result_envelope["role_result"]["findings"][0],
                             "message": "tampered but canonical"},
                        ],
                    },
                },
            ),
            "digest_mismatch",
        ),
        (
            lambda c: dataclasses.replace(
                c,
                result_envelope={
                    **c.result_envelope,
                    "role_result": {**c.result_envelope["role_result"], "verdict": "approve"},
                },
            ),
            "validation_failed",
        ),
        (
            lambda c: dataclasses.replace(
                c, terminal_receipt={**c.terminal_receipt, "result_envelope_digest": "0" * 64}
            ),
            "digest_mismatch",
        ),
        (
            lambda c: dataclasses.replace(
                c, terminal_receipt={**c.terminal_receipt, "attempt_id": "ATT-999"}
            ),
            "digest_mismatch",
        ),
        (
            lambda c: dataclasses.replace(
                c, terminal_receipt={**c.terminal_receipt, "job_id": "JOB-999"}
            ),
            "digest_mismatch",
        ),
        (
            lambda c: dataclasses.replace(
                c, terminal_receipt={**c.terminal_receipt, "status": "FAILED"}
            ),
            "digest_mismatch",
        ),
        (lambda c: dataclasses.replace(c, result_envelope={"schema_version": "nope"}), "validation_failed"),
        (
            lambda c: dataclasses.replace(
                c, terminal_receipt={
                    **c.terminal_receipt,
                    "result_envelope": {**c.result_envelope, "summary": "inconsistent terminal content"},
                }
            ),
            "digest_mismatch",
        ),
        (
            lambda c: dataclasses.replace(
                c, terminal_receipt={**c.terminal_receipt, "result_envelope": None}
            ),
            "digest_mismatch",
        ),
        (
            lambda c: dataclasses.replace(
                c, terminal_receipt={**c.terminal_receipt, "result_envelope": object()}
            ),
            "digest_mismatch",
        ),
    ],
)
def test_digest_and_envelope_mutation_refused(bound_max_chain, mutate_completion, code):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[1])
    snapshot = dataclasses.replace(
        snapshot, completion=mutate_completion(snapshot.completion)
    )
    with pytest.raises(frp.FabricResultProjectionError) as info:
        frp.project_fabric_role_result(snapshot, receipt)
    assert info.value.args[0] == code


# ---------------------------------------------------------------------------
# narrow mutations of actual receipts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("replacement", [False, 0.0])
def test_terminal_envelope_preserves_canonical_numeric_types(bound_max_chain, replacement):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[1])
    terminal = copy.deepcopy(snapshot.completion.terminal_receipt)
    assert type(terminal["result_envelope"]["role_result"]["repair_round"]) is int
    assert terminal["result_envelope"]["role_result"]["repair_round"] == 0
    terminal["result_envelope"]["role_result"]["repair_round"] = replacement
    assert terminal["result_envelope"] == snapshot.completion.result_envelope
    malformed = dataclasses.replace(
        snapshot, completion=dataclasses.replace(snapshot.completion, terminal_receipt=terminal)
    )
    with pytest.raises(frp.FabricResultProjectionError) as info:
        frp.project_fabric_role_result(malformed, receipt)
    assert info.value.args[0] == "digest_mismatch"


@pytest.mark.parametrize(
    "mutate_receipt, code",
    [
        (lambda r: dataclasses.replace(r, schema="mastermind.other.v1"), "receipt_invalid"),
        (lambda r: dataclasses.replace(r, schema=None), "receipt_invalid"),
        (lambda r: dataclasses.replace(r, state="UNKNOWN"), "state_conflict"),
        (lambda r: dataclasses.replace(r, state="CHANGED"), "state_conflict"),
        (lambda r: dataclasses.replace(r, state="CONFLICT", before=2, after=3), "state_conflict"),
        (lambda r: dataclasses.replace(r, before=3), "state_conflict"),
        (lambda r: dataclasses.replace(r, before=True, after=True), "receipt_invalid"),
        (lambda r: dataclasses.replace(r, before=False, after=False), "receipt_invalid"),
        (lambda r: dataclasses.replace(r, after=-1), "receipt_invalid"),
        (lambda r: dataclasses.replace(r, before=2.0, after=2.0), "receipt_invalid"),
        (lambda r: dataclasses.replace(r, source_identity=None), "source_identity_invalid"),
        (lambda r: dataclasses.replace(r, source_identity="F" * 32), "source_identity_invalid"),
        (lambda r: dataclasses.replace(r, source_identity="f" * 33), "source_identity_invalid"),
        (lambda r: dataclasses.replace(r, source_identity="f" * 31), "source_identity_invalid"),
        (lambda r: dataclasses.replace(r, source_identity="0" * 32), "source_identity_mismatch"),
        (lambda r: dataclasses.replace(r, before=None), "receipt_invalid"),
    ],
)
def test_receipt_mutation_refused(bound_max_chain, mutate_receipt, code):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[-1])
    with pytest.raises(frp.FabricResultProjectionError) as info:
        frp.project_fabric_role_result(snapshot, mutate_receipt(receipt))
    assert info.value.args[0] == code


def test_unbound_snapshot_identity_refused(bound_max_chain):
    # The real unbound read yields identity None and an UNKNOWN receipt; a
    # trusted caller never assembles that pair, and the projector refuses it.
    runtime, root, nodes, expected, reader = bound_max_chain
    completion = expected[0]
    with runtime.observe_bounded_read() as observation:
        snapshot = observation.read_role_result_bounded(
            root.job_id,
            completion.job.job_id,
            expected_attempt_id=completion.attempt.attempt_id,
            expected_result_envelope_digest=completion.result_digest,
        )
    unbound_receipt = observation.receipt
    assert snapshot.observation_source_identity is None
    assert unbound_receipt.state == "UNKNOWN"
    assert unbound_receipt.source_identity is None
    for candidate_snapshot, candidate_receipt in (
        (snapshot, unbound_receipt),
        (snapshot, dataclasses.replace(unbound_receipt, state="SAME")),
        (dataclasses.replace(snapshot, observation_source_identity="0" * 32), unbound_receipt),
    ):
        with pytest.raises(frp.FabricResultProjectionError):
            frp.project_fabric_role_result(candidate_snapshot, candidate_receipt)


# ---------------------------------------------------------------------------
# foreign inputs and the removed lookalike DTO shape
# ---------------------------------------------------------------------------


def test_foreign_and_shadow_inputs_refused(bound_max_chain):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[-1])

    class BoundedRoleResultSnapshot:  # a deliberate lookalike shadow
        pass

    class RuntimeReadObservationReceipt:
        pass

    mapping_snapshot = {
        "root_job_id": root.job_id,
        "job_id": snapshot.job_id,
        "attempt_id": snapshot.attempt_id,
        "result_envelope_digest": snapshot.result_envelope_digest,
        "completion": dataclasses.asdict(snapshot.completion),
        "root_metadata": dataclasses.asdict(snapshot.root_metadata),
        "observation_source_identity": snapshot.observation_source_identity,
    }
    for candidate_snapshot, candidate_receipt in (
        (None, receipt),
        (mapping_snapshot, receipt),
        (BoundedRoleResultSnapshot(), receipt),
        (snapshot, None),
        (snapshot, receipt.to_dict()),
        (snapshot, RuntimeReadObservationReceipt()),
        (
            dataclasses.replace(snapshot, completion=mapping_snapshot["completion"]),
            receipt,
        ),
        (
            dataclasses.replace(snapshot, root_metadata=mapping_snapshot["root_metadata"]),
            receipt,
        ),
    ):
        with pytest.raises(frp.FabricResultProjectionError) as info:
            frp.project_fabric_role_result(candidate_snapshot, candidate_receipt)
        assert info.value.args[0] == "input_invalid"


def test_module_owns_no_shadow_dtos_or_fake_runtime_inputs():
    assert frp.BoundedRoleResultSnapshot is er.BoundedRoleResultSnapshot
    assert frp.RuntimeReadObservationReceipt is er.RuntimeReadObservationReceipt
    assert frp.ValidatedRoleCompletion is er.ValidatedRoleCompletion
    assert frp.BoundedRoleResultRootMetadata is er.BoundedRoleResultRootMetadata
    for removed in ("RuntimeReadObservationReceiptView", "BoundedRoleResultSnapshotView"):
        assert not hasattr(frp, removed)
    assert frp.FABRIC_ROLE_RESULT_VIEW_SCHEMA == "mastermind.fabric_role_result_view.v1"
    fields = [field.name for field in dataclasses.fields(frp.FabricRoleResultProjection)]
    assert fields == ["complete", "content_over_budget"]
    assert frp.FabricRoleResultProjection.__dataclass_params__.frozen
    import inspect

    signature = inspect.signature(frp.project_fabric_role_result)
    assert list(signature.parameters) == ["snapshot", "receipt"]


# ---------------------------------------------------------------------------
# independence: deep copies, no aliases, no raw diagnostics
# ---------------------------------------------------------------------------


def test_documents_are_deep_copies_with_no_input_or_cross_aliases(bound_max_chain):
    runtime, root, nodes, expected, reader = bound_max_chain
    completion = expected[1]  # rejecting review: findings present in content
    snapshot, receipt = _select_bound(reader, root.job_id, completion)
    envelope_before = copy.deepcopy(completion.result_envelope)
    receipt_before = receipt.to_dict()

    projection = frp.project_fabric_role_result(snapshot, receipt)
    complete, over = projection.complete, projection.content_over_budget

    assert complete is not over
    for field in ("selection", "generation", "counts", "review"):
        assert complete[field] is not over[field]
    assert complete["content"]["role_result"] is not completion.result_envelope["role_result"]

    complete["selection"]["job_id"] = "JOB-TAMPERED"
    complete["generation"]["before"] = 9999
    complete["counts"]["next_actions"] = 9999
    complete["content"]["next_actions"].append("tampered")
    complete["review"]["verdict"] = "tampered"
    complete["content"]["role_result"]["findings"][0]["severity"] = "tampered"

    assert over["selection"]["job_id"] == snapshot.job_id
    assert over["generation"]["before"] == receipt.before
    assert over["counts"]["next_actions"] == len(envelope_before["next_actions"])
    assert over["review"]["verdict"] == envelope_before["role_result"]["verdict"]
    assert over["counts"]["findings"]["total"] == len(envelope_before["role_result"]["findings"])
    assert completion.result_envelope == envelope_before
    assert receipt.to_dict() == receipt_before


def test_projection_performs_no_io_or_runtime_reentry(bound_max_chain, monkeypatch):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[-1])
    # The module is fully imported; any acquisition attempt during the pure
    # projection call itself is a contract violation.
    import builtins
    import time

    def forbid(*args, **kwargs):
        raise AssertionError("projection attempted an acquisition action")

    monkeypatch.setattr(builtins, "open", forbid)
    monkeypatch.setattr(sqlite3, "connect", forbid)
    monkeypatch.setattr(er, "Runtime", forbid)
    monkeypatch.setattr(time, "time", forbid)
    monkeypatch.setattr(time, "monotonic", forbid)
    projection = frp.project_fabric_role_result(snapshot, receipt)
    assert projection.complete["availability"] == "AVAILABLE"


def test_refusals_carry_closed_messages_without_raw_diagnostics(bound_max_chain):
    runtime, root, nodes, expected, reader = bound_max_chain
    snapshot, receipt = _select_bound(reader, root.job_id, expected[-1])
    tampered = dataclasses.replace(
        snapshot,
        completion=dataclasses.replace(
            snapshot.completion,
            result_envelope={**snapshot.completion.result_envelope, "bogus_key": 1},
        ),
    )
    with pytest.raises(frp.FabricResultProjectionError) as info:
        frp.project_fabric_role_result(tampered, receipt)
    code, message = info.value.args
    assert code == "validation_failed"
    assert message == "canonical envelope validation refused"
    assert "bogus_key" not in message
    assert "OrchestrationResultError" not in message
    assert len(message) < 200


# ---------------------------------------------------------------------------
# import compatibility with older Runtime source
# ---------------------------------------------------------------------------


def test_older_runtime_source_without_the_seam_degrades_to_typed_refusal(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "control_plane.executive_runtime":
            raise ImportError("older source fixture")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    try:
        module = importlib.reload(frp)
        assert module.BoundedRoleResultSnapshot is None
        assert module.RuntimeReadObservationReceipt is None
        with pytest.raises(module.FabricResultProjectionError) as info:
            module.project_fabric_role_result(object(), object())
        assert info.value.args == ("input_invalid", "snapshot must be a BoundedRoleResultSnapshot")
    finally:
        monkeypatch.undo()
        importlib.reload(frp)
    assert frp.BoundedRoleResultSnapshot is er.BoundedRoleResultSnapshot
