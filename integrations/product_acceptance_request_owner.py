"""Single-send product decision requests on the existing Dialogue carrier.

Runtime retains the exact send-start identity before transport. A duplicate
selects reconciliation; it never sends again or invents a new request identity.
A request and an independent review remain distinct from principal acceptance.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from common.product_acceptance_contract import (
    PRODUCT_ACCEPTANCE_ASSOCIATION_SCHEMA,
    ProductAcceptanceContractError,
    require_complete_product_acceptance_review_proof,
)
from control_plane.executive_runtime import Runtime, BoundedProductAcceptanceSubject
from control_plane.agentos_product_acceptance_basis import (
    AgentOsProductAcceptanceBasisReader,
    _canonical_digest,
    reconcile_unchanged_acceptance_basis,
)
from control_plane.product_acceptance_review_owner import (
    read_retained_product_review_input,
)
from integrations.mastermind_company_mcp.adapter import (
    DialogueBinding,
    CompanyDialogueGateway,
)
from integrations.mastermind_company_mcp.schemas import GatewayError
from integrations.slack_agent_dialogue.contract_v2 import (
    build_message_v2,
    MESSAGE_SCHEMA_V2,
)

AGGREGATE = "product_acceptance_request"
EVENT_TYPE = "PRODUCT_ACCEPTANCE_REQUEST_SEND_STARTED"
COMMAND_PREFIX = "product-acceptance-request-send:"
SCHEMA = "mastermind.product_acceptance_request_issuance.v1"


class ProductAcceptanceRequestUnavailable(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        message_key: str | None = None,
        repair_identity: str | None = None,
        repair_kind: str | None = None,
    ) -> None:
        self.code, self.message_key, self.repair_identity, self.repair_kind = (
            code,
            message_key,
            repair_identity,
            repair_kind,
        )
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class PreparedProductAcceptanceRequest:
    context: dict[str, Any]
    thread_ts: str
    message: dict[str, Any]
    durable_ref: str


def _select(
    runtime: Runtime, applies: dict[str, Any], subject_job_id: str
) -> BoundedProductAcceptanceSubject:
    with runtime.observe_bounded_read() as observation:
        selected = observation.read_product_acceptance_subject_bounded(
            issuer_job_id=applies["job_id"],
            issuer_attempt_id=applies["attempt_id"],
            issuer_worker_id=applies["worker_id"],
            subject_job_id=subject_job_id,
        )
    receipt = observation.receipt
    if (
        receipt.before != receipt.after
        or selected.observation_source_identity != receipt.source_identity
    ):
        raise ProductAcceptanceRequestUnavailable("PRODUCT_RUNTIME_CHANGED")
    return selected


def _subject_identity(selected: BoundedProductAcceptanceSubject) -> dict[str, Any]:
    return {
        "root_job_id": selected.root_job_id,
        "issuer_job_id": selected.issuer_job_id,
        "issuer_attempt_id": selected.issuer_attempt_id,
        "issuer_worker_id": selected.issuer_worker_id,
        "root_objective": selected.root_objective,
        "dependency_manifest_digest": selected.dependency_manifest_digest,
        "subject_job_id": selected.subject.job_id,
        "subject_attempt_id": selected.subject.attempt_id,
        "subject_result_envelope_digest": selected.subject.result_envelope_digest,
        "subject_role_result_digest": selected.subject.completion.role_result_digest,
        "reviewer_job_id": selected.reviewer.job_id,
        "reviewer_attempt_id": selected.reviewer.attempt_id,
        "reviewer_result_envelope_digest": selected.reviewer.result_envelope_digest,
        "reviewer_role_result_digest": selected.reviewer.completion.role_result_digest,
    }


class ProductAcceptanceRequestOwner:
    def __init__(
        self,
        runtime: Runtime,
        reader: AgentOsProductAcceptanceBasisReader,
        *,
        principal_owner: Any | None = None,
    ) -> None:
        if (
            type(runtime) is not Runtime
            or type(reader) is not AgentOsProductAcceptanceBasisReader
        ):
            raise TypeError(
                "product request requires the exact Runtime and configured source reader"
            )
        self.runtime, self.reader = runtime, reader
        self.ruling_owner = None
        if principal_owner is not None:
            from integrations.product_acceptance_ruling_owner import (
                ProductAcceptanceRulingOwner,
            )

            self.ruling_owner = ProductAcceptanceRulingOwner(self, principal_owner)

    def prepare(
        self, *, binding: DialogueBinding, subject_job_id: str, created_at: str
    ) -> PreparedProductAcceptanceRequest:
        """Derive and fence one request; caller supplies only its bounded selector."""
        try:
            context = CompanyDialogueGateway._binding_context(binding)
        except GatewayError as exc:
            raise ProductAcceptanceRequestUnavailable(
                "PRODUCT_REQUEST_BINDING_UNAVAILABLE"
            ) from exc
        applies = context["applies_to"]
        actor = context["actor_ref"]
        if (
            type(binding) is not DialogueBinding
            or applies.get("kind") != "executive_attempt"
            or actor
            != {
                "kind": "worker_attempt",
                "job_id": applies.get("job_id"),
                "attempt_id": applies.get("attempt_id"),
                "worker_id": applies.get("worker_id"),
            }
            or "DECISION_REQUEST" not in binding.allowed_message_types
        ):
            raise ProductAcceptanceRequestUnavailable(
                "PRODUCT_REQUEST_BINDING_UNAVAILABLE"
            )
        selected = _select(self.runtime, applies, subject_job_id)
        subject, review = selected.subject.completion, selected.reviewer.completion
        source = subject.dialogue_source
        if (
            source is None
            or review.dialogue_source != source
            or source.work_ref != context["work_ref"]
            or source.commission_ref.to_dict() != context["commission_ref"]
            or source.watch_mode != context["watch_mode"]
        ):
            raise ProductAcceptanceRequestUnavailable(
                "PRODUCT_REQUEST_BINDING_UNAVAILABLE"
            )
        retained = read_retained_product_review_input(
            self.runtime, job=review.job, attempt=review.attempt
        )
        if (
            retained is None
            or retained.root_job_id != selected.root_job_id
            or retained.root_objective != selected.root_objective
            or retained.work_ref != source.work_ref
            or retained.execution_commission_ref != source.commission_ref.to_dict()
        ):
            raise ProductAcceptanceRequestUnavailable(
                "RETAINED_REVIEW_BASIS_UNAVAILABLE"
            )
        current = self.reader.read(
            work_ref=source.work_ref,
            execution_commission_ref=source.commission_ref,
            root_objective=selected.root_objective,
        )
        continuity = reconcile_unchanged_acceptance_basis(retained.basis, current)
        expected = retained.expected
        try:
            proof = require_complete_product_acceptance_review_proof(
                review.result_envelope["role_result"].get("product_acceptance_proof"),
                expected_basis_digest=expected.basis_digest,
                expected_criterion_digests=expected.criterion_digests,
                expected_obligation_digests=expected.obligation_digests,
            )
        except ProductAcceptanceContractError as exc:
            raise ProductAcceptanceRequestUnavailable(
                "PRODUCT_PROOF_INCOMPLETE",
                repair_identity=exc.repair_identity,
                repair_kind=exc.repair_kind,
            ) from exc
        identity = _subject_identity(selected)
        # A changed thread/session binding cannot generate a replacement for an
        # uncertain send of the same current result and issued review basis.
        logical_subject = {
            key: identity[key]
            for key in (
                "root_job_id",
                "subject_job_id",
                "subject_attempt_id",
                "subject_result_envelope_digest",
                "subject_role_result_digest",
                "reviewer_job_id",
                "reviewer_attempt_id",
                "reviewer_result_envelope_digest",
            )
        }
        token = _canonical_digest(
            {"subject": logical_subject, "basis_digest": expected.basis_digest}
        )[:32]
        issuance_ref = "runtime-product-acceptance:" + token
        message_key = "asd-mcp-" + token
        basis = retained.basis.entry
        association = {
            "schema": PRODUCT_ACCEPTANCE_ASSOCIATION_SCHEMA,
            "issuance_ref": issuance_ref,
            **{
                key: identity[key]
                for key in (
                    "root_job_id",
                    "issuer_job_id",
                    "issuer_attempt_id",
                    "subject_job_id",
                    "subject_attempt_id",
                    "subject_result_envelope_digest",
                    "subject_role_result_digest",
                    "reviewer_job_id",
                    "reviewer_attempt_id",
                    "reviewer_result_envelope_digest",
                )
            },
            "acceptance_basis_digest": expected.basis_digest,
            "criteria_objective_sha256": expected.objective_sha256,
            **{
                key: basis[key]
                for key in (
                    "current_intent_revision",
                    "original_intent_ref",
                    "current_intent_ref",
                    "proof_contract_ref",
                )
            },
        }
        body = {
            "question": "Does this exact independently reviewed result satisfy the original intent and every required product outcome?",
            "outcome_impact": "Accept only after inspecting the retained full source basis and evidence. A source merge, passing test, reviewer grade or this request alone does not prove product acceptance.",
            "options": [
                {
                    "id": "opt-product-accept",
                    "summary": "Accept this exact product result.",
                    "consequence": "The assigning parent may consume this ruling after revalidating the same result, source basis and authority generation.",
                    "disposition": "CONTINUE",
                    "authority_effect": "NONE",
                },
                {
                    "id": "opt-product-repair",
                    "summary": "Require repair or further evidence.",
                    "consequence": "Preserve the original result and obligations; continue bounded repair under existing authority.",
                    "disposition": "CONTINUE",
                    "authority_effect": "NONE",
                },
            ],
            "recommendation": "opt-product-repair",
            "work_paused": True,
            "acceptance_request": association,
        }
        message = build_message_v2(
            {
                "schema": MESSAGE_SCHEMA_V2,
                "message_key": message_key,
                "message_type": "DECISION_REQUEST",
                "work_ref": context["work_ref"],
                "commission_ref": context["commission_ref"],
                "session_ref": context["session_ref"],
                "actor_ref": context["actor_ref"],
                "reply_to_message_key": binding.reply_to_message_key,
                "applies_to": applies,
                "summary": "Product acceptance decision requested.",
                "body": body,
                "evidence_refs": [],
                "requires_response": True,
                "created_at": created_at,
            }
        )
        payload = {
            "schema": SCHEMA,
            "context": context,
            "thread_ts": binding.thread_ts,
            "message": message,
            "subject": identity,
            "review_input": retained.to_dict(),
            "proof_digest": _canonical_digest(proof),
            "source_continuity": dataclasses.asdict(continuity),
        }
        # BEGIN IMMEDIATE excludes concurrent Runtime writers. The ordinary
        # bounded reader opens and closes its own read snapshot while that write
        # lock is held, before this transaction changes anything. No raw result
        # lookup or second lifecycle validator replaces the canonical reader.
        with self.runtime.store.transaction() as connection:
            if self.runtime.store.get_event_by_command_id(
                COMMAND_PREFIX + token, connection=connection
            ) or self.runtime.store.list_events(
                aggregate_type=AGGREGATE,
                aggregate_id=issuance_ref,
                connection=connection,
            ):
                raise ProductAcceptanceRequestUnavailable(
                    "PRODUCT_REQUEST_RECONCILIATION_REQUIRED", message_key=message_key
                )
            current_subject = _select(self.runtime, applies, subject_job_id)
            if _subject_identity(current_subject) != identity:
                raise ProductAcceptanceRequestUnavailable("PRODUCT_RUNTIME_CHANGED")
            self.runtime.store.append_event(
                connection,
                aggregate_type=AGGREGATE,
                aggregate_id=issuance_ref,
                event_type=EVENT_TYPE,
                actor="product-acceptance-request-owner",
                job_id=selected.issuer_job_id,
                attempt_id=selected.issuer_attempt_id,
                worker_id=selected.issuer_worker_id,
                payload=payload,
                command_id=COMMAND_PREFIX + token,
            )
            event = self.runtime.store.get_event_by_command_id(
                COMMAND_PREFIX + token, connection=connection
            )
            if event is None or _canonical_digest(event.payload) != _canonical_digest(
                payload
            ):
                raise ProductAcceptanceRequestUnavailable(
                    "PRODUCT_REQUEST_RETAIN_FAILED"
                )
        return PreparedProductAcceptanceRequest(
            context, binding.thread_ts, message, f"runtime-event:{event.event_id}"
        )
