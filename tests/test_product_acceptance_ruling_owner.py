"""Runtime-backed qualification and final parent return with a simulated Relay.

These tests assert composition and rejection boundaries, not authenticated
installed delivery or real principal judgment.
"""

import asyncio
import copy
import dataclasses
from pathlib import Path

import pytest

from integrations.product_acceptance_ruling_owner import (
    ProductAcceptanceRulingOwner,
    AGGREGATE,
)
from integrations.product_acceptance_request_owner import (
    ProductAcceptanceRequestUnavailable,
)
from integrations.mastermind_company_mcp.adapter import CompanyDialogueGateway
from integrations.mastermind_company_mcp.principal_adapter import (
    PrincipalCompanyDialogueGateway,
)
from integrations.mastermind_company_principal_runtime_fence import (
    PrincipalDialogueRuntimeCommitOwner,
)
from tests.test_product_acceptance_request_owner import programme, prepare
from tests.test_product_acceptance_basis_continuity import restamp
from tests.test_mastermind_company_mcp import _StaticResolver
from tests import test_executive_os_phase1fc as phase


class RelayFixture:
    def __init__(self, request):
        self.request = request
        self.reply = None
        self.calls = []
        self.authority = {
            "disposition": "CONTINUE",
            "executable": True,
            "selected_option": "opt-product-accept",
            "canonical_ref": None,
        }

    async def __call__(self, path, request):
        self.calls.append(copy.deepcopy(request))
        operation = request["operation"]
        if operation == "read_thread":
            return {
                "ok": True,
                "result": {
                    "thread_ts": request["args"]["thread_ts"],
                    "historical_messages": [],
                    "mutated_count": 0,
                    "messages": [
                        {"message": m, "duplicate_timestamps": []}
                        for m in (self.request, self.reply)
                        if m
                    ],
                },
            }
        if operation == "wait_for_reply":
            assert request["args"]["max_attempts"] == 1
            return {
                "ok": True,
                "result": {
                    "reply": self.reply,
                    "authority": self.authority,
                    "transport": {
                        "primary_ts": "1787896130.625239",
                        "duplicate_timestamps": [],
                    },
                },
            }
        raise AssertionError("qualification may not send")


def ready(tmp_path, monkeypatch, *, commit=True):
    runtime, requester, binding, target, basis = programme(tmp_path, monkeypatch)
    prepared = prepare(requester, binding, target)
    principal_binding = dataclasses.replace(
        binding,
        actor_ref={
            "kind": "executive_principal",
            "seat": "coo",
            "reasoning_surface": "claude-agent-sdk",
            "principal_binding_digest": "1" * 64,
            "mission_authority_ref": "authority:fixture",
            "authority_generation_digest": "2" * 64,
            "capability_profile_digest": "3" * 64,
            "root_job_id": requester._test_root.job_id,
        },
        allowed_message_types=("RULING", "CONTINUE", "STOP"),
        reply_to_message_key=prepared.message["message_key"],
    )
    resolver = _StaticResolver(principal_binding)
    relay = RelayFixture(prepared.message)
    principal = PrincipalDialogueRuntimeCommitOwner(
        runtime,
        resolver,
        socket_path=Path("/private/tmp/product-fixture.sock"),
        service_call=relay,
    )
    gateway = PrincipalCompanyDialogueGateway(
        resolver,
        socket_path=principal.socket_path,
        service_call=relay,
        before_commit=principal.before_commit,
        utc_now=lambda: "2026-10-13T14:01:00Z",
    )
    context = gateway._binding_context(principal_binding)
    relay.reply = gateway._message(
        "ruling",
        {
            "authority_class": "WITHIN_COMMISSION",
            "selected_option": "opt-product-accept",
            "decision": "Accept the exact tested fixture outcome.",
            "rationale": "Fixture evidence meets every declared requirement.",
            "canonical_ref": None,
            "evidence_refs": [],
        },
        principal_binding,
        context,
    )
    if commit:
        principal.before_commit(
            gateway._commit_intent(principal_binding, context, relay.reply)
        )
    owner = ProductAcceptanceRulingOwner(requester, principal)
    requester.ruling_owner = owner
    return runtime, requester, binding, target, basis, prepared, owner, relay, resolver


def qualify(values):
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = (
        values
    )
    return asyncio.run(
        owner.qualify(binding=binding, message_key=prepared.message["message_key"])
    )


def complete_parent(runtime, requester, digests, *, issuer_digests=None):
    root = requester._test_root
    issuer = requester._test_issuer_dispatch
    job = runtime.jobs.get_job(issuer.attempt.job_id)
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": job.plan_attempt_id,
        "plan_digest": job.plan_digest,
        "plan_step_id": job.plan_step_id,
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": digests if issuer_digests is None else issuer_digests,
    }
    phase._complete_ohf_role(runtime, issuer, work_body, identity_seed=3386)
    sibling = requester._test_sibling
    sibling_dispatch = runtime.attempts.dispatch_cycle_job(
        sibling.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{sibling.job_id}:attempt:1",
        worker_id="worker-c",
        quota_class="codex-hf1q-step",
    )
    phase._complete_ohf_role(
        runtime,
        sibling_dispatch,
        {**work_body, "plan_step_id": sibling.plan_step_id, "evidence_digests": []},
        identity_seed=3387,
    )
    assert requester._test_cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    parent_dispatch = runtime.attempts.dispatch_cycle_job(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{root.job_id}:attempt:1",
        worker_id="worker-a",
        quota_class="codex-hf1q-step",
    )
    requester._test_parent_dispatch = parent_dispatch
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    revision_keys = (
        "ordinal",
        "plan_step_id",
        "current_job_id",
        "current_attempt_id",
        "current_result_digest",
        "repair_round",
        "review_required",
        "qualifying_review_job_id",
        "qualifying_review_attempt_id",
        "qualifying_review_result_digest",
    )
    body = {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": root.job_id,
        **{
            key: handoff[key]
            for key in (
                "handoff_digest",
                "policy_sha",
                "plan_attempt_id",
                "plan_digest",
            )
        },
        "revisions": [
            {key: row[key] for key in revision_keys} for row in handoff["revisions"]
        ],
        "aggregate_summary": "The original parent consumed the exact fixture ruling.",
        "evidence_digests": digests,
    }
    phase._complete_ohf_role(runtime, parent_dispatch, body, identity_seed=3388)


def test_ruling_is_pending_until_original_terminal_parent_includes_exact_receipt(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = (
        values
    )
    qualified = qualify(values)
    assert qualified["state"] == "RULING_QUALIFIED_PARENT_RETURN_PENDING"
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_PARENT_RETURN_UNVERIFIED"
    ):
        owner.observe_acceptance(prepared.message["message_key"])
    complete_parent(runtime, requester, [qualified["evidence_digest"]])
    accepted = owner.observe_acceptance(prepared.message["message_key"])
    assert accepted["state"] == "PRODUCT_ACCEPTED"
    assert (
        accepted["parent_attempt_id"]
        == requester._test_parent_dispatch.attempt.attempt_id
    )
    assert accepted["subject_job_id"] == target.job_id
    assert len(runtime.events.list_events(aggregate_type=AGGREGATE)) == 1
    assert all(
        call["operation"] in {"read_thread", "wait_for_reply"} for call in relay.calls
    )


def test_parent_summary_cannot_replace_consumption_of_the_qualified_receipt(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    qualify(values)
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = (
        values
    )
    complete_parent(runtime, requester, [])
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_PARENT_CONSUMPTION_UNPROVEN"
    ):
        owner.observe_acceptance(prepared.message["message_key"])


def test_visible_ruling_without_original_principal_commit_is_not_qualified(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch, commit=False)
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_RULING_COMMIT_UNCONFIRMED"
    ):
        qualify(values)
    assert values[0].events.list_events(aggregate_type=AGGREGATE) == []


def test_current_principal_generation_must_match_the_committed_ruling(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    resolver = values[-1]
    resolver.binding = dataclasses.replace(
        resolver.binding,
        actor_ref={
            **resolver.binding.actor_ref,
            "authority_generation_digest": "f" * 64,
        },
    )
    with pytest.raises(
        ProductAcceptanceRequestUnavailable,
        match="PRODUCT_PRINCIPAL_GENERATION_CHANGED",
    ):
        qualify(values)
    assert values[0].events.list_events(aggregate_type=AGGREGATE) == []


def test_relay_authority_floor_cannot_be_replaced_by_an_accept_word(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    values[-2].authority["executable"] = False
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_RULING_NOT_ACCEPTED"
    ):
        qualify(values)
    assert values[0].events.list_events(aggregate_type=AGGREGATE) == []


def test_existing_gateway_request_returns_qualified_digest_without_another_send(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = (
        values
    )
    gateway = CompanyDialogueGateway(
        _StaticResolver(binding),
        socket_path=Path("/private/tmp/product-fixture.sock"),
        service_call=relay,
        product_acceptance_owner=requester,
    )
    result = asyncio.run(
        gateway.call(
            "request_decision",
            {"purpose": "PRODUCT_ACCEPTANCE", "subject_job_id": target.job_id},
        )
    )
    assert result["ok"] is True and result["server_version"] == "1.1.0", result
    assert result["data"]["state"] == "RULING_QUALIFIED_PARENT_RETURN_PENDING"
    assert all(call["operation"] != "send_message" for call in relay.calls)


def test_parent_receipt_alone_cannot_replace_exact_worker_consumption(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    qualified = qualify(values)
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = (
        values
    )
    complete_parent(
        runtime, requester, [qualified["evidence_digest"]], issuer_digests=[]
    )
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_PARENT_CONSUMPTION_UNPROVEN"
    ):
        owner.observe_acceptance(prepared.message["message_key"])


def test_corrected_requirement_invalidates_acceptance_after_both_returns(
    tmp_path, monkeypatch
):
    from control_plane.agentos_product_acceptance_basis import (
        ProductAcceptanceBasisUnavailable,
    )

    values = ready(tmp_path, monkeypatch)
    qualified = qualify(values)
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = (
        values
    )
    complete_parent(runtime, requester, [qualified["evidence_digest"]])
    basis.entry["current_intent_revision"] = "chairman-correction-v2"
    restamp(basis.entry)
    with pytest.raises(
        ProductAcceptanceBasisUnavailable,
        match="SOURCE_REVISION_RECONCILIATION_REQUIRED",
    ):
        owner.observe_acceptance(prepared.message["message_key"])


def test_duplicate_qualification_reuses_one_original_receipt(tmp_path, monkeypatch):
    values = ready(tmp_path, monkeypatch)
    first = qualify(values)
    second = qualify(values)
    assert first == second
    assert len(values[0].events.list_events(aggregate_type=AGGREGATE)) == 1
    assert all(call["operation"] != "send_message" for call in values[-2].calls)


def test_changed_request_bytes_require_original_delivery_reconciliation(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    values[-2].request = copy.deepcopy(values[-2].request)
    values[-2].request["summary"] = "Another request with a copied identity"
    with pytest.raises(
        ProductAcceptanceRequestUnavailable,
        match="PRODUCT_REQUEST_DELIVERY_UNCONFIRMED",
    ):
        qualify(values)
    assert values[0].events.list_events(aggregate_type=AGGREGATE) == []


def test_host_projection_uses_exact_existing_owner_and_is_read_only(
    tmp_path, monkeypatch
):
    from integrations.mastermind_company_principal_host import (
        PrincipalCompanyDialogueHost,
        build_principal_company_dialogue_host,
    )

    values = ready(tmp_path, monkeypatch)
    qualified = qualify(values)
    runtime, requester, binding, target, basis, prepared, owner, relay, resolver = (
        values
    )
    complete_parent(runtime, requester, [qualified["evidence_digest"]])
    host = build_principal_company_dialogue_host(
        runtime=runtime,
        binding_resolver=resolver,
        socket_path=Path("/private/tmp/product-fixture.sock"),
        service_call=relay,
        request_binding_resolver=_StaticResolver(binding),
        product_acceptance_macro_root=tmp_path,
    )
    before = runtime.events.list_events(aggregate_type=AGGREGATE)
    assert (
        host.observe_product_acceptance(prepared.message["message_key"])["state"]
        == "PRODUCT_ACCEPTED"
    )
    assert runtime.events.list_events(aggregate_type=AGGREGATE) == before
    ordinary = PrincipalCompanyDialogueHost(
        gateway=None, commit_owner=owner.principal_owner
    )
    with pytest.raises(ValueError, match="not composed"):
        ordinary.observe_product_acceptance(prepared.message["message_key"])
