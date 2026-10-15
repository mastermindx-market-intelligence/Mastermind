"""Actual Runtime event retention and supervisor composition, with a source fixture.

The Context CLI is separately qualified; this file cannot prove installed reader
availability, reviewer execution, a principal ruling or parent consumption.
"""

import asyncio
import copy
import dataclasses
import hashlib
import json

import pytest

from common.commission_ref import normalize_commission_ref
from control_plane.executive_runtime import AttemptLease
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    VerifiedCommission,
    SupervisorError,
)
from control_plane.agentos_product_acceptance_basis import (
    AgentOsProductAcceptanceBasisReader,
    ProductAcceptanceBasisUnavailable,
)
from control_plane.product_acceptance_review_owner import (
    ProductAcceptanceReviewBasisOwner,
    read_retained_product_review_input,
    AGGREGATE,
)
from tests.test_product_acceptance_basis_continuity import acquired_basis, restamp
from tests.test_executive_supervisor import FakeAdapter, FakeInspector
from tests import test_executive_os_phase1fc as phase


def fixture(tmp_path, monkeypatch):
    basis = acquired_basis()
    content = b"# Exact read-only fixture commission\n"
    ref = copy.deepcopy(basis.entry["execution_commission_refs"][0])
    ref["content_sha256"] = hashlib.sha256(content).hexdigest()
    basis.entry["execution_commission_refs"] = [ref]
    restamp(basis.entry)
    submit = phase.submit_intent
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "review"
    workspace.mkdir(parents=True)

    def source_bound_submit(runtime, intent, **kwargs):
        intent = {
            **intent,
            "objective": basis.entry["criteria_objective"],
            "workstream": basis.entry["workstream"],
            "execution_contract": {
                **intent["execution_contract"],
                "worktree": str(workspace),
            },
        }
        return submit(
            runtime,
            intent,
            dialogue_source={
                "schema_version": "mastermind.executive_dialogue_source/v1",
                "work_ref": basis.entry["workstream"],
                "commission_ref": ref,
                "watch_mode": None,
            },
            require_dialogue_source=True,
            workspace_root=workspace_root,
            **kwargs,
        )

    monkeypatch.setattr(phase, "submit_intent", source_bound_submit)
    runtime, cycle, dispatches, root, planner, work, seal = (
        phase._cycle_through_completed_work(
            tmp_path, intent_id="CEO-PRODUCT-REVIEW-INPUT", review_workers=["worker-b"]
        )
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    attempt = dispatches[-1].attempt
    job = runtime.jobs.get_job(attempt.job_id)
    reader = AgentOsProductAcceptanceBasisReader(macro_root=tmp_path)
    calls = []

    def read(self, **kwargs):
        calls.append(kwargs)
        assert kwargs == {
            "work_ref": basis.entry["workstream"],
            "execution_commission_ref": normalize_commission_ref(ref),
            "root_objective": root.objective,
        }
        return copy.deepcopy(basis)

    monkeypatch.setattr(AgentOsProductAcceptanceBasisReader, "read", read)
    owner = ProductAcceptanceReviewBasisOwner(runtime, reader)
    commission = VerifiedCommission(**ref, content=content)
    supervisor = ExecutiveSupervisor(
        runtime, FakeAdapter(FakeInspector()), runs_root=tmp_path / "runs"
    )
    supervisor._test_cycle = cycle
    supervisor._test_dispatches = dispatches
    supervisor._test_work_seal = seal
    supervisor._test_lease = AttemptLease(
        attempt=attempt, lease_token=dispatches[-1].lease_token
    )
    return runtime, job, attempt, owner, commission, supervisor, basis, calls


def test_supervisor_schema_and_prompt_use_the_original_retained_complete_selection(
    tmp_path, monkeypatch
):
    runtime, job, attempt, owner, commission, supervisor, basis, calls = fixture(
        tmp_path, monkeypatch
    )
    selected = owner.select_and_retain(job=job, attempt=attempt, commission=commission)
    schema_path = supervisor._write_schema(
        tmp_path / "review-input",
        job=job,
        attempt=attempt,
        effective_grant={"fixture": True},
    )
    schema = json.loads(schema_path.read_text())
    body = schema["properties"]["role_result"]
    assert body["properties"]["schema_version"] == {
        "const": "mastermind.review_result/v2"
    }
    assert body["properties"]["product_acceptance_proof"]["properties"][
        "acceptance_basis_digest"
    ] == {"const": selected.expected.basis_digest}
    assert (
        schema["x-mastermind-effective-grant-digest"] == attempt.effective_grant_digest
    )
    prompt = supervisor._prompt(
        job,
        attempt,
        commission=commission.ref_dict(),
        inline_commission=commission.content.decode(),
    )
    assert basis.entry["proof_obligations"][0]["required_outcome"] in prompt
    assert selected.expected.obligation_digests[0] in prompt
    before = runtime.events.list_events(
        aggregate_type=AGGREGATE, aggregate_id=attempt.attempt_id
    )

    # Recovery uses the retained original input. It neither rereads a new source
    # basis nor retroactively selects a shortened set of expected identities.
    def forbidden(*args, **kwargs):
        raise AssertionError("retained recovery reselected source")

    monkeypatch.setattr(AgentOsProductAcceptanceBasisReader, "read", forbidden)
    restarted = ExecutiveSupervisor(runtime, FakeAdapter(FakeInspector()))
    assert (
        restarted._product_acceptance_review_suffix(job, attempt)
        == selected.prompt_suffix()
    )
    assert (
        read_retained_product_review_input(runtime, job=job, attempt=attempt)
        == selected
    )
    assert (
        runtime.events.list_events(
            aggregate_type=AGGREGATE, aggregate_id=attempt.attempt_id
        )
        == before
    )
    assert len(calls) == 1
    assert restarted._product_acceptance_review_owner is None


def test_default_ordinary_review_has_identical_v1_contract_and_no_basis_event(
    tmp_path, monkeypatch
):
    runtime, job, attempt, owner, commission, supervisor, basis, calls = fixture(
        tmp_path, monkeypatch
    )
    path = supervisor._write_schema(
        tmp_path / "legacy-input",
        job=job,
        attempt=attempt,
        effective_grant={"fixture": True},
    )
    assert json.loads(path.read_text())["properties"]["role_result"]["properties"][
        "schema_version"
    ] == {"const": "mastermind.review_result/v1"}
    assert supervisor._product_acceptance_review_suffix(job, attempt) == ""
    assert read_retained_product_review_input(runtime, job=job, attempt=attempt) is None
    assert not calls


def test_verified_commission_required_before_read_or_retention(tmp_path, monkeypatch):
    runtime, job, attempt, owner, commission, supervisor, basis, calls = fixture(
        tmp_path, monkeypatch
    )
    for bad in (
        None,
        commission.ref_dict(),
        dataclasses.replace(commission, commit="f" * 40),
    ):
        with pytest.raises(
            ProductAcceptanceBasisUnavailable, match="REVIEW_COMMISSION_UNVERIFIED"
        ):
            owner.select_and_retain(job=job, attempt=attempt, commission=bad)
    assert not calls
    assert read_retained_product_review_input(runtime, job=job, attempt=attempt) is None


def test_expired_issuer_after_source_read_cannot_retain_or_launch(
    tmp_path, monkeypatch
):
    runtime, job, attempt, owner, commission, supervisor, basis, calls = fixture(
        tmp_path, monkeypatch
    )
    read = AgentOsProductAcceptanceBasisReader.read

    def expired(self, **kwargs):
        result = read(self, **kwargs)
        with runtime.store.transaction() as connection:
            connection.execute(
                "UPDATE attempts SET lease_expires_at_ms=1 WHERE attempt_id=?",
                (attempt.attempt_id,),
            )
        return result

    monkeypatch.setattr(AgentOsProductAcceptanceBasisReader, "read", expired)
    with pytest.raises(
        ProductAcceptanceBasisUnavailable, match="REVIEW_ATTEMPT_CHANGED"
    ):
        owner.select_and_retain(job=job, attempt=attempt, commission=commission)
    assert read_retained_product_review_input(runtime, job=job, attempt=attempt) is None
    assert supervisor.adapter.spec is None


def test_original_selection_is_not_overwritten_by_another_selection(
    tmp_path, monkeypatch
):
    runtime, job, attempt, owner, commission, supervisor, basis, calls = fixture(
        tmp_path, monkeypatch
    )
    first = owner.select_and_retain(job=job, attempt=attempt, commission=commission)
    with pytest.raises(
        ProductAcceptanceBasisUnavailable, match="REVIEW_BASIS_ALREADY_SELECTED"
    ):
        owner.select_and_retain(job=job, attempt=attempt, commission=commission)
    assert (
        read_retained_product_review_input(runtime, job=job, attempt=attempt) == first
    )
    assert (
        len(
            runtime.events.list_events(
                aggregate_type=AGGREGATE, aggregate_id=attempt.attempt_id
            )
        )
        == 1
    )


def test_retained_selection_cannot_be_read_as_another_attempt_or_worker(
    tmp_path, monkeypatch
):
    runtime, job, attempt, owner, commission, supervisor, basis, calls = fixture(
        tmp_path, monkeypatch
    )
    owner.select_and_retain(job=job, attempt=attempt, commission=commission)
    with pytest.raises(
        ProductAcceptanceBasisUnavailable, match="RETAINED_REVIEW_BASIS_CONFLICT"
    ):
        read_retained_product_review_input(
            runtime, job=job, attempt=dataclasses.replace(attempt, worker_id="foreign")
        )


def test_actual_start_selects_verified_basis_before_schema_and_provider(
    tmp_path, monkeypatch
):
    runtime, job, attempt, owner, commission, supervisor, basis, calls = fixture(
        tmp_path, monkeypatch
    )
    supervisor._product_acceptance_review_owner = owner
    seen = []
    monkeypatch.setattr(supervisor, "_validate_execution_profile", lambda *a: None)

    def verified(*args):
        seen.append("verified_commission")
        return commission

    monkeypatch.setattr(supervisor, "verified_commission", verified)

    class StopAtSchema(SupervisorError):
        pass

    def checked_schema(*args, **kwargs):
        selected = read_retained_product_review_input(runtime, job=job, attempt=attempt)
        assert selected is not None and len(selected.expected.obligation_digests) == 1
        seen.append("retained_basis_before_schema")
        raise StopAtSchema("test stops before any provider start")

    monkeypatch.setattr(supervisor, "_write_schema", checked_schema)
    with pytest.raises(StopAtSchema):
        asyncio.run(supervisor._start_claimed_job(job.job_id, supervisor._test_lease))
    assert seen == ["verified_commission", "retained_basis_before_schema"]
    assert len(calls) == 1 and supervisor.adapter.spec is None
