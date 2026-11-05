"""Canonical terminal proof to single-send request; no installed or acceptance claim."""

import asyncio
import copy
import dataclasses
import hashlib
from pathlib import Path

import pytest

from control_plane.agentos_product_acceptance_basis import (
    AgentOsProductAcceptanceBasisReader,
)
from integrations.product_acceptance_request_owner import (
    ProductAcceptanceRequestOwner,
    ProductAcceptanceRequestUnavailable,
    AGGREGATE,
)
from integrations.mastermind_company_mcp.adapter import (
    CompanyDialogueGateway,
    DialogueBinding,
)
from tests.test_product_acceptance_basis_continuity import acquired_basis, restamp
from tests import test_executive_coo_ready_frontier as frontier
from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import VerifiedCommission
from control_plane.product_acceptance_review_owner import (
    ProductAcceptanceReviewBasisOwner,
)
from common.commission_ref import normalize_commission_ref
from tests.test_mastermind_company_mcp import _StaticResolver, _RecordingService
from tests import test_executive_os_phase1fc as phase


def programme(
    tmp_path,
    monkeypatch,
    *,
    state="SATISFIED",
    retain=True,
    proof_transform=None,
    basis_value=None,
):
    basis = acquired_basis() if basis_value is None else copy.deepcopy(basis_value)
    content = b"# Exact dependency-consumer fixture commission\n"
    ref = copy.deepcopy(basis.entry["execution_commission_refs"][0])
    ref["content_sha256"] = hashlib.sha256(content).hexdigest()
    basis.entry["execution_commission_refs"] = [ref]
    restamp(basis.entry)
    submit = frontier.submit_intent

    def bound_submit(runtime, intent, **kwargs):
        return submit(
            runtime,
            {
                **intent,
                "objective": basis.entry["criteria_objective"],
                "workstream": basis.entry["workstream"],
            },
            dialogue_source={
                "schema_version": "mastermind.executive_dialogue_source/v1",
                "work_ref": basis.entry["workstream"],
                "commission_ref": ref,
                "watch_mode": None,
            },
            require_dialogue_source=True,
            **kwargs,
        )

    monkeypatch.setattr(frontier, "submit_intent", bound_submit)
    # This fixture uses admitted Codex capacity for all three existing steps;
    # the reused frontier helper's Claude sibling is deliberately unqualified.
    monkeypatch.setattr(frontier, "_CLAUDE", frontier._CODEX)
    runtime = Runtime.at(tmp_path)
    root, planner, plan, by_step = frontier._admitted_v3_chain(
        runtime, prerequisite_review_required=True
    )
    work, seal = frontier._complete_v3_prerequisite(
        runtime, root, planner, plan, by_step["step-0"]
    )
    cycle = phase.CooCycle(runtime)
    review = runtime.jobs.create_cycle_review(
        root.job_id,
        work.attempt.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-review:{work.attempt.job_id}:1",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        review.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1",
        worker_id="worker-c",
        quota_class="codex-hf1q-step",
    )
    review = runtime.jobs.get_job(review.job_id)

    def read(self, **kwargs):
        assert kwargs == {
            "work_ref": basis.entry["workstream"],
            "execution_commission_ref": normalize_commission_ref(ref),
            "root_objective": root.objective,
        }
        return copy.deepcopy(basis)

    monkeypatch.setattr(AgentOsProductAcceptanceBasisReader, "read", read)
    reader = AgentOsProductAcceptanceBasisReader(macro_root=tmp_path)
    if retain:
        selected = ProductAcceptanceReviewBasisOwner(runtime, reader).select_and_retain(
            job=review,
            attempt=dispatch.attempt,
            commission=VerifiedCommission(**ref, content=content),
        )
    target = runtime.jobs.get_job(work.attempt.job_id)
    body = phase._review_body(
        root_id=root.job_id,
        plan_attempt_id=review.plan_attempt_id,
        plan_digest=review.plan_digest,
        target_job_id=target.job_id,
        target_attempt_id=target.current_attempt_id,
        target_result_digest=seal["role_result_digest"],
        repair_round=0,
        verdict="approve",
        plan_step_id=review.plan_step_id,
    )
    if retain:
        body["schema_version"] = "mastermind.review_result/v2"
        body["product_acceptance_proof"] = {
            "schema": "mastermind.product_acceptance_review_proof.v1",
            "acceptance_basis_digest": selected.expected.basis_digest,
            "criteria": [
                {
                    "criterion_digest": d,
                    "state": "SATISFIED",
                    "evidence_digests": ["8" * 64],
                }
                for d in selected.expected.criterion_digests
            ],
            "obligations": [
                {"obligation_digest": d, "state": state, "evidence_digests": ["9" * 64]}
                for d in selected.expected.obligation_digests
            ],
        }
        if proof_transform is not None:
            proof_transform(body["product_acceptance_proof"])
    phase._complete_ohf_role(runtime, dispatch, body, identity_seed=3355)
    manifest = runtime.jobs.project_cycle_work_dependency_manifest(
        root.job_id, "step-2"
    )
    consumer = runtime.jobs.create_cycle_work(
        root.job_id,
        "step-2",
        dependency_manifest=manifest,
        command_id=f"coo-cycle:{root.job_id}:create-work:step-2:{manifest['dependency_manifest_digest']}",
    )
    assert consumer.plan_step_id == "step-2"
    issuer_dispatch = runtime.attempts.dispatch_cycle_job(
        consumer.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{consumer.job_id}:attempt:1",
        worker_id="worker-a",
        quota_class="codex-hf1q-step",
    )
    issuer = issuer_dispatch.attempt
    binding = DialogueBinding(
        actor_ref={
            "kind": "worker_attempt",
            "job_id": issuer.job_id,
            "attempt_id": issuer.attempt_id,
            "worker_id": issuer.worker_id,
        },
        work_ref=basis.entry["workstream"],
        commission_ref=ref,
        session_ref="asd-session-productfixture01",
        operation_key="product-acceptance-fixture",
        watch_mode=None,
        applies_to={
            "kind": "executive_attempt",
            "job_id": issuer.job_id,
            "attempt_id": issuer.attempt_id,
            "worker_id": issuer.worker_id,
        },
        thread_ts="1787896128.625239",
        allowed_message_types=("DECISION_REQUEST",),
    )
    requester = ProductAcceptanceRequestOwner(runtime, reader)
    requester._test_issuer_dispatch = issuer_dispatch
    requester._test_review_dispatch = dispatch
    requester._test_root = root
    requester._test_cycle = cycle
    requester._test_sibling = by_step["step-1"]
    return runtime, requester, binding, target, basis


def prepare(owner, binding, target):
    return owner.prepare(
        binding=binding, subject_job_id=target.job_id, created_at="2026-10-13T14:00:00Z"
    )


def test_actual_current_independent_review_retains_one_typed_request(
    tmp_path, monkeypatch
):
    runtime, owner, binding, target, basis = programme(tmp_path, monkeypatch)
    prepared = prepare(owner, binding, target)
    message = prepared.message
    association = message["body"]["acceptance_request"]
    assert association["root_job_id"] == owner._test_root.job_id
    assert association["issuer_job_id"] == binding.applies_to["job_id"]
    assert association["root_job_id"] != association["issuer_job_id"]
    assert association["subject_job_id"] == target.job_id
    assert (
        association["acceptance_basis_digest"] == basis.entry["acceptance_basis_digest"]
    )
    assert message["body"]["recommendation"] == "opt-product-repair"
    assert (
        len(
            runtime.events.list_events(
                aggregate_type=AGGREGATE, aggregate_id=association["issuance_ref"]
            )
        )
        == 1
    )
    with pytest.raises(
        ProductAcceptanceRequestUnavailable,
        match="PRODUCT_REQUEST_RECONCILIATION_REQUIRED",
    ) as error:
        prepare(owner, binding, target)
    assert error.value.message_key == message["message_key"]


@pytest.mark.parametrize("state", ["UNSATISFIED", "UNPROVEN"])
def test_missing_must_have_proof_returns_exact_repair_identity_without_send_start(
    tmp_path, monkeypatch, state
):
    runtime, owner, binding, target, basis = programme(
        tmp_path, monkeypatch, state=state
    )
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_PROOF_INCOMPLETE"
    ) as error:
        prepare(owner, binding, target)
    assert error.value.repair_kind == state
    assert error.value.repair_identity == basis.entry["proof_obligation_digests"][0]
    assert runtime.events.list_events(aggregate_type=AGGREGATE) == []


@pytest.mark.parametrize(
    "kind", ["MISSING_REQUIRED_PROOF", "UNEXPECTED_PROOF", "PROOF_ORDER_CHANGED"]
)
def test_gateway_preserves_canonical_missing_extra_and_order_repair_identity(
    tmp_path, monkeypatch, kind
):
    from control_plane.agentos_product_acceptance_basis import _canonical_digest

    basis = acquired_basis()
    second = {**basis.entry["proof_obligations"][0], "label": "Original parent return"}
    basis.entry["proof_obligations"].append(second)
    basis.entry["proof_obligation_digests"].append(_canonical_digest(second))
    restamp(basis.entry)

    def transform(proof):
        rows = proof["obligations"]
        if kind == "MISSING_REQUIRED_PROOF":
            rows.pop()
        elif kind == "UNEXPECTED_PROOF":
            rows.append({**rows[0], "obligation_digest": "0" * 64})
        else:
            rows.reverse()

    runtime, owner, binding, target, retained = programme(
        tmp_path, monkeypatch, proof_transform=transform, basis_value=basis
    )
    service = _RecordingService()
    gateway = CompanyDialogueGateway(
        _StaticResolver(binding),
        socket_path=Path("/private/tmp/product-fixture.sock"),
        service_call=service,
        product_acceptance_owner=owner,
    )
    result = asyncio.run(
        gateway.call(
            "request_decision",
            {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": target.job_id},
        )
    )
    expected_identity = (
        retained.entry["proof_obligation_digests"][1]
        if kind == "MISSING_REQUIRED_PROOF"
        else (
            "0" * 64
            if kind == "UNEXPECTED_PROOF"
            else retained.entry["proof_obligation_digests"][0]
        )
    )
    assert result["ok"] is False
    assert result["error"]["detail_code"] == "PRODUCT_PROOF_INCOMPLETE"
    assert result["data"] == {"repair_identity": expected_identity, "repair_kind": kind}
    assert service.calls == []
    assert runtime.events.list_events(aggregate_type=AGGREGATE) == []


def test_old_generic_review_cannot_be_promoted_by_a_current_checklist(
    tmp_path, monkeypatch
):
    runtime, owner, binding, target, basis = programme(
        tmp_path, monkeypatch, retain=False
    )
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="RETAINED_REVIEW_BASIS_UNAVAILABLE"
    ):
        prepare(owner, binding, target)
    assert runtime.events.list_events(aggregate_type=AGGREGATE) == []


def test_actual_gateway_lost_response_has_one_send_and_same_reconciliation_key(
    tmp_path, monkeypatch
):
    runtime, owner, binding, target, basis = programme(tmp_path, monkeypatch)
    service = _RecordingService(error=ConnectionError("fixture lost response"))
    gateway = CompanyDialogueGateway(
        _StaticResolver(binding),
        socket_path=Path("/private/tmp/product-fixture.sock"),
        service_call=service,
        product_acceptance_owner=owner,
        utc_now=lambda: "2026-10-13T14:00:00Z",
    )
    args = {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": target.job_id}
    first = asyncio.run(gateway.call("request_decision", args))
    second = asyncio.run(gateway.call("request_decision", args))
    assert not first["ok"] and not second["ok"]
    assert len(service.calls) == 1
    assert first["data"]["message_key"] == second["data"]["message_key"]
    assert second["error"]["detail_code"] == "PRODUCT_REQUEST_RECONCILIATION_REQUIRED"


def test_request_binding_cannot_recast_another_worker_as_live_issuer(
    tmp_path, monkeypatch
):
    runtime, owner, binding, target, basis = programme(tmp_path, monkeypatch)
    changed = dataclasses.replace(
        binding, actor_ref={**binding.actor_ref, "worker_id": "foreign-worker"}
    )
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_REQUEST_BINDING_UNAVAILABLE"
    ):
        prepare(owner, changed, target)
    assert runtime.events.list_events(aggregate_type=AGGREGATE) == []


def test_new_session_cannot_replay_an_uncertain_send(tmp_path, monkeypatch):
    runtime, owner, binding, target, basis = programme(tmp_path, monkeypatch)
    prepared = prepare(owner, binding, target)
    replacement = dataclasses.replace(
        binding, session_ref="asd-session-productfixture02"
    )
    with pytest.raises(
        ProductAcceptanceRequestUnavailable,
        match="PRODUCT_REQUEST_RECONCILIATION_REQUIRED",
    ) as error:
        prepare(owner, replacement, target)
    assert error.value.message_key == prepared.message["message_key"]
    assert len(runtime.events.list_events(aggregate_type=AGGREGATE)) == 1


@pytest.mark.parametrize("state", ["UNSATISFIED", "UNPROVEN"])
def test_actual_gateway_returns_the_exact_requirement_to_repair(
    tmp_path, monkeypatch, state
):
    runtime, owner, binding, target, basis = programme(
        tmp_path, monkeypatch, state=state
    )
    service = _RecordingService()
    gateway = CompanyDialogueGateway(
        _StaticResolver(binding),
        socket_path=Path("/private/tmp/product-fixture.sock"),
        service_call=service,
        product_acceptance_owner=owner,
    )
    result = asyncio.run(
        gateway.call(
            "request_decision",
            {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": target.job_id},
        )
    )
    assert result["ok"] is False
    assert result["error"]["detail_code"] == "PRODUCT_PROOF_INCOMPLETE"
    assert result["data"] == {
        "repair_identity": basis.entry["proof_obligation_digests"][0],
        "repair_kind": state,
    }
    assert service.calls == []
    assert runtime.events.list_events(aggregate_type=AGGREGATE) == []
