"""Qualify the existing principal ruling and observe exact parent consumption.

A qualified ruling is not acceptance. Acceptance is projected only after the
original assigning parent's canonical terminal aggregation includes the exact
qualified receipt digest, and the current source declaration still agrees.
No new queue, message, grant, lifecycle transition or replay is introduced.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from common.product_acceptance_contract import (
    require_complete_product_acceptance_review_proof,
)
from control_plane.executive_runtime import RuntimeProofError
from control_plane.agentos_product_acceptance_basis import (
    _canonical_digest,
    reconcile_unchanged_acceptance_basis,
)
from control_plane.product_acceptance_review_owner import _decode
from integrations.product_acceptance_request_owner import (
    ProductAcceptanceRequestOwner,
    ProductAcceptanceRequestUnavailable,
    AGGREGATE as REQUEST_AGGREGATE,
    EVENT_TYPE as REQUEST_EVENT,
    COMMAND_PREFIX as REQUEST_COMMAND,
    SCHEMA as REQUEST_SCHEMA,
    _select,
    _subject_identity,
)
from integrations.mastermind_company_mcp.adapter import (
    CompanyDialogueGateway,
    DialogueBinding,
)
from integrations.mastermind_company_mcp.principal_adapter import (
    PrincipalCompanyDialogueGateway,
)
from integrations.mastermind_company_principal_runtime_fence import (
    PrincipalDialogueRuntimeCommitOwner,
    PrincipalCommitObservationState,
)
from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2
from integrations.slack_agent_dialogue.service import CONTROL_VERSION_V2

AGGREGATE = "product_acceptance_ruling"
EVENT_TYPE = "PRODUCT_ACCEPTANCE_RULING_QUALIFIED"
COMMAND_PREFIX = "product-acceptance-ruling:"
SCHEMA = "mastermind.product_acceptance_qualified_ruling.v1"
_REQUEST_KEY = re.compile(r"\Aasd-mcp-[0-9a-f]{32}\Z")


def _unavailable(code: str) -> ProductAcceptanceRequestUnavailable:
    return ProductAcceptanceRequestUnavailable(code)


def _qualified_result(message_key: str, ruling_key: str, digest: str) -> dict[str, Any]:
    return {
        "state": "RULING_QUALIFIED_PARENT_RETURN_PENDING",
        "request_message_key": message_key,
        "ruling_message_key": ruling_key,
        "evidence_digest": digest,
        "next": "Preserve this digest in the existing evidence_digests of this commissioned work result, and return it to the original parent for inclusion in its aggregate evidence_digests. Acceptance remains pending until both exact terminal returns are validated.",
    }


class ProductAcceptanceRulingReceiptReader:
    """Read owner-issued receipts without holding any principal COMMIT authority."""

    def __init__(self, request_owner: ProductAcceptanceRequestOwner) -> None:
        if type(request_owner) is not ProductAcceptanceRequestOwner:
            raise TypeError("product receipt requires the exact request owner")
        self.request_owner = request_owner
        self.runtime = request_owner.runtime

    def _request(self, message_key: str) -> dict[str, Any]:
        if type(message_key) is not str or _REQUEST_KEY.fullmatch(message_key) is None:
            raise _unavailable("PRODUCT_REQUEST_UNAVAILABLE")
        token = message_key[len("asd-mcp-") :]
        issuance = "runtime-product-acceptance:" + token
        with self.runtime.store.read() as connection:
            event = self.runtime.store.get_event_by_command_id(
                REQUEST_COMMAND + token, connection=connection
            )
            rows = self.runtime.store.list_events(
                aggregate_type=REQUEST_AGGREGATE,
                aggregate_id=issuance,
                connection=connection,
            )
        if (
            event is None
            or len(rows) != 1
            or rows[0].event_id != event.event_id
            or event.event_type != REQUEST_EVENT
            or event.aggregate_type != REQUEST_AGGREGATE
            or event.aggregate_id != issuance
            or event.actor != "product-acceptance-request-owner"
        ):
            raise _unavailable("PRODUCT_REQUEST_UNAVAILABLE")
        raw = event.payload
        if (
            type(raw) is not dict
            or set(raw)
            != {
                "schema",
                "context",
                "thread_ts",
                "message",
                "subject",
                "review_input",
                "proof_digest",
                "source_continuity",
            }
            or raw["schema"] != REQUEST_SCHEMA
        ):
            raise _unavailable("PRODUCT_REQUEST_CONFLICT")
        message = validate_message_v2(raw["message"])
        subject = raw["subject"]
        retained = _decode(raw["review_input"])
        association = message["body"].get("acceptance_request", {})
        if (
            message["message_key"] != message_key
            or message["message_type"] != "DECISION_REQUEST"
            or association.get("issuance_ref") != issuance
            or association.get("acceptance_basis_digest")
            != retained.expected.basis_digest
            or subject["root_job_id"] != retained.root_job_id
            or subject["reviewer_job_id"] != retained.job_id
            or subject["reviewer_attempt_id"] != retained.attempt_id
            or event.job_id != subject["issuer_job_id"]
            or event.attempt_id != subject["issuer_attempt_id"]
            or event.worker_id != subject["issuer_worker_id"]
        ):
            raise _unavailable("PRODUCT_REQUEST_CONFLICT")
        return raw

    def _current_request(
        self, *, binding: DialogueBinding, message_key: str
    ):
        raw = self._request(message_key)
        if (
            CompanyDialogueGateway._binding_context(binding) != raw["context"]
            or binding.thread_ts != raw["thread_ts"]
        ):
            raise _unavailable("PRODUCT_PARENT_BINDING_CHANGED")
        selected = _select(
            self.runtime, raw["context"]["applies_to"], raw["subject"]["subject_job_id"]
        )
        if _subject_identity(selected) != raw["subject"]:
            raise _unavailable("PRODUCT_RUNTIME_CHANGED")
        retained = _decode(raw["review_input"])
        current = self.request_owner.reader.read(
            work_ref=retained.work_ref,
            execution_commission_ref=selected.subject.completion.dialogue_source.commission_ref,
            root_objective=selected.root_objective,
        )
        continuity = reconcile_unchanged_acceptance_basis(retained.basis, current)
        expected = retained.expected
        proof = require_complete_product_acceptance_review_proof(
            selected.reviewer.completion.result_envelope["role_result"].get(
                "product_acceptance_proof"
            ),
            expected_basis_digest=expected.basis_digest,
            expected_criterion_digests=expected.criterion_digests,
            expected_obligation_digests=expected.obligation_digests,
        )
        if _canonical_digest(proof) != raw["proof_digest"]:
            raise _unavailable("PRODUCT_REVIEW_CHANGED")
        return raw, selected, expected, continuity

    def _qualified_receipt(self, message_key: str):
        raw = self._request(message_key)
        subject = raw["subject"]
        with self.runtime.store.read() as connection:
            event = self.runtime.store.get_event_by_command_id(
                COMMAND_PREFIX + message_key, connection=connection
            )
            rows = self.runtime.store.list_events(
                aggregate_type=AGGREGATE,
                aggregate_id=message_key,
                connection=connection,
            )
        if (
            event is None
            or len(rows) != 1
            or rows[0].event_id != event.event_id
            or event.event_type != EVENT_TYPE
            or event.aggregate_type != AGGREGATE
            or event.aggregate_id != message_key
            or event.actor != "product-acceptance-ruling-owner"
            or event.job_id != subject["issuer_job_id"]
            or event.attempt_id != subject["issuer_attempt_id"]
            or event.worker_id != subject["issuer_worker_id"]
            or type(event.payload) is not dict
            or set(event.payload) != {"receipt", "receipt_digest", "source_continuity"}
            or type(event.payload["receipt"]) is not dict
            or set(event.payload["receipt"])
            != {
                "schema",
                "request_message_key",
                "request_fingerprint",
                "subject",
                "ruling_message_key",
                "ruling_fingerprint",
                "principal_actor",
                "commit_observation",
                "acceptance_basis_digest",
                "proof_digest",
            }
            or event.payload["receipt"].get("schema") != SCHEMA
            or event.payload["receipt"].get("request_message_key") != message_key
            or event.payload["receipt"].get("request_fingerprint")
            != raw["message"]["fingerprint"]
            or event.payload["receipt"].get("acceptance_basis_digest")
            != raw["review_input"]["expected"]["basis_digest"]
            or event.payload["receipt"].get("proof_digest") != raw["proof_digest"]
            or event.payload.get("receipt_digest")
            != _canonical_digest(event.payload.get("receipt"))
            or event.payload["receipt"].get("subject") != subject
        ):
            raise _unavailable("PRODUCT_RULING_UNQUALIFIED")
        return raw, event

    def observe_qualified(self, *, binding: DialogueBinding, message_key: str) -> dict[str, Any]:
        # Revalidate this live requester, terminal subject/review, retained basis
        # and complete current proof before exposing the existing receipt digest.
        # This reader never observes Relay, creates a ruling or appends an event.
        current, _selected, _expected, _continuity = self._current_request(
            binding=binding, message_key=message_key,
        )
        raw, event = self._qualified_receipt(message_key)
        if raw != current or _subject_identity(_select(
            self.runtime, raw["context"]["applies_to"], raw["subject"]["subject_job_id"]
        )) != raw["subject"]:
            raise _unavailable("PRODUCT_REQUEST_CONFLICT")
        return _qualified_result(message_key,
            event.payload["receipt"]["ruling_message_key"], event.payload["receipt_digest"])

    def observe_acceptance(self, message_key: str) -> dict[str, Any]:
        """Read-only projection; only a canonical parent terminal return consumes."""
        raw, event = self._qualified_receipt(message_key)
        subject = raw["subject"]
        digest = event.payload["receipt_digest"]
        try:
            issuer = self.runtime.validated_role_completion(
                subject["issuer_job_id"],
                expected_attempt_id=subject["issuer_attempt_id"],
            )
            root = self.runtime.jobs.get_job(subject["root_job_id"])
            if root is None or root.current_attempt_id is None:
                raise _unavailable("PRODUCT_PARENT_RETURN_UNVERIFIED")
            parent = self.runtime.validated_role_completion(
                root.job_id, expected_attempt_id=root.current_attempt_id
            )
        except RuntimeProofError as exc:
            raise _unavailable("PRODUCT_PARENT_RETURN_UNVERIFIED") from exc
        body = parent.result_envelope["role_result"]
        revisions = [
            row
            for row in body["revisions"]
            if row["current_job_id"] == subject["subject_job_id"]
        ]
        consumers = [
            row
            for row in body["revisions"]
            if row["current_job_id"] == subject["issuer_job_id"]
        ]
        if (
            issuer.job.orchestration_role != "work"
            or issuer.job.parent_job_id != parent.job.job_id
            or issuer.attempt.worker_id != subject["issuer_worker_id"]
            or digest not in issuer.result_envelope["role_result"]["evidence_digests"]
            or parent.job.orchestration_role != "aggregation"
            or parent.job.job_id != subject["root_job_id"]
            or parent.job.objective != subject["root_objective"]
            or digest not in body["evidence_digests"]
            or len(consumers) != 1
            or consumers[0]["current_attempt_id"] != issuer.attempt.attempt_id
            or consumers[0]["current_result_digest"] != issuer.role_result_digest
            or len(revisions) != 1
            or any(
                revisions[0][key] != subject[value]
                for key, value in (
                    ("current_attempt_id", "subject_attempt_id"),
                    ("current_result_digest", "subject_role_result_digest"),
                    ("qualifying_review_job_id", "reviewer_job_id"),
                    ("qualifying_review_attempt_id", "reviewer_attempt_id"),
                    ("qualifying_review_result_digest", "reviewer_role_result_digest"),
                )
            )
        ):
            raise _unavailable("PRODUCT_PARENT_CONSUMPTION_UNPROVEN")
        retained = _decode(raw["review_input"])
        source = parent.dialogue_source
        if (
            source is None
            or source.commission_ref.to_dict() != retained.execution_commission_ref
        ):
            raise _unavailable("PRODUCT_PARENT_CONSUMPTION_UNPROVEN")
        current = self.request_owner.reader.read(
            work_ref=retained.work_ref,
            execution_commission_ref=source.commission_ref,
            root_objective=parent.job.objective,
        )
        continuity = reconcile_unchanged_acceptance_basis(retained.basis, current)
        return {
            "state": "PRODUCT_ACCEPTED",
            "subject_job_id": subject["subject_job_id"],
            "subject_result_envelope_digest": subject["subject_result_envelope_digest"],
            "ruling_message_key": event.payload["receipt"]["ruling_message_key"],
            "qualified_ruling_digest": digest,
            "parent_job_id": parent.job.job_id,
            "parent_attempt_id": parent.attempt.attempt_id,
            "parent_result_envelope_digest": parent.result_digest,
            "source_continuity": dataclasses.asdict(continuity),
        }


class ProductAcceptanceRulingOwner(ProductAcceptanceRulingReceiptReader):
    def __init__(
        self,
        request_owner: ProductAcceptanceRequestOwner,
        principal_owner: PrincipalDialogueRuntimeCommitOwner,
    ) -> None:
        if (
            type(request_owner) is not ProductAcceptanceRequestOwner
            or type(principal_owner) is not PrincipalDialogueRuntimeCommitOwner
            or request_owner.runtime is not principal_owner.runtime
        ):
            raise TypeError(
                "product acceptance requires the same exact Runtime and existing principal owner"
            )
        super().__init__(request_owner)
        self.principal_owner = principal_owner

    async def qualify_committed_request(self) -> dict[str, Any]:
        """Join this actual principal reply to its already-issued worker request.

        The reply target comes from the host's current principal binding. The
        retained worker context is used only for qualification reads, with no
        message grant. It cannot originate or replay a worker request.
        """
        principal = self.principal_owner.binding_resolver.resolve()
        message_key = principal.reply_to_message_key
        raw = self._request(message_key)
        context = raw["context"]
        binding = DialogueBinding(
            **context, thread_ts=raw["thread_ts"], allowed_message_types=(),
        )
        return await self.qualify(binding=binding, message_key=message_key)

    async def _service(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        response = await self.principal_owner.service_call(
            self.principal_owner.socket_path,
            {"version": CONTROL_VERSION_V2, "operation": operation, "args": args},
        )
        if (
            type(response) is not dict
            or response.get("ok") is not True
            or type(response.get("result")) is not dict
        ):
            raise _unavailable("PRODUCT_RULING_UNAVAILABLE")
        return response["result"]

    def _principal(self, raw: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:
        binding = self.principal_owner.binding_resolver.resolve()
        context = PrincipalCompanyDialogueGateway._binding_context(binding)
        if (
            binding.thread_ts != raw["thread_ts"]
            or binding.reply_to_message_key != raw["message"]["message_key"]
            or reply["actor_ref"] != context["actor_ref"]
            or context["actor_ref"]["root_job_id"] != raw["subject"]["root_job_id"]
            or any(
                context[name] != raw["context"][name]
                for name in (
                    "work_ref",
                    "commission_ref",
                    "session_ref",
                    "operation_key",
                    "watch_mode",
                    "applies_to",
                )
            )
        ):
            raise _unavailable("PRODUCT_PRINCIPAL_GENERATION_CHANGED")
        return context

    async def qualify(
        self, *, binding: DialogueBinding, message_key: str
    ) -> dict[str, Any]:
        raw, selected, expected, continuity = self._current_request(
            binding=binding, message_key=message_key
        )
        # Verify the exact request bytes were present, including a previously
        # lost send response. This read never retries the original send.
        history = await self._service(
            "read_thread", {"context": raw["context"], "thread_ts": raw["thread_ts"]}
        )
        if (
            history.get("thread_ts") != raw["thread_ts"]
            or history.get("historical_messages") != []
            or type(history.get("mutated_count")) is not int
            or history["mutated_count"] != 0
            or type(history.get("messages")) is not list
            or len(history["messages"]) > 256
        ):
            raise _unavailable("PRODUCT_REQUEST_DELIVERY_UNCONFIRMED")
        matches = [
            item
            for item in history["messages"]
            if type(item) is dict
            and type(item.get("message")) is dict
            and item["message"].get("message_key") == message_key
        ]
        if (
            len(matches) != 1
            or matches[0]["message"] != raw["message"]
            or matches[0].get("duplicate_timestamps", []) != []
        ):
            raise _unavailable("PRODUCT_REQUEST_DELIVERY_UNCONFIRMED")
        # Existing Relay policy owns reply direction, order, uniqueness and the
        # authority floor. A parsed model RULING alone never substitutes.
        returned = await self._service(
            "wait_for_reply",
            {
                "context": raw["context"],
                "thread_ts": raw["thread_ts"],
                "request_message_key": message_key,
                "expected_types": ["RULING"],
                "max_attempts": 1,
            },
        )
        reply = validate_message_v2(returned.get("reply"))
        authority = returned.get("authority")
        if (
            reply["message_type"] != "RULING"
            or reply["reply_to_message_key"] != message_key
            or reply["body"]["selected_option"] != "opt-product-accept"
            or reply["body"]["authority_class"] != "WITHIN_COMMISSION"
            or authority
            != {
                "disposition": "CONTINUE",
                "executable": True,
                "selected_option": "opt-product-accept",
                "canonical_ref": None,
            }
            or type(returned.get("transport")) is not dict
            or returned["transport"].get("duplicate_timestamps") != []
        ):
            raise _unavailable("PRODUCT_RULING_NOT_ACCEPTED")
        committed = await self.principal_owner.read_committed_message(
            reply["message_key"]
        )
        if (
            committed.observation.state is not PrincipalCommitObservationState.APPLIED
            or committed.message != reply
        ):
            raise _unavailable("PRODUCT_RULING_COMMIT_UNCONFIRMED")
        principal = self._principal(raw, reply)
        receipt = {
            "schema": SCHEMA,
            "request_message_key": message_key,
            "request_fingerprint": raw["message"]["fingerprint"],
            "subject": raw["subject"],
            "ruling_message_key": reply["message_key"],
            "ruling_fingerprint": reply["fingerprint"],
            "principal_actor": principal["actor_ref"],
            "commit_observation": committed.observation.to_dict(),
            "acceptance_basis_digest": expected.basis_digest,
            "proof_digest": raw["proof_digest"],
        }
        digest = _canonical_digest(receipt)
        with self.runtime.store.transaction() as connection:
            if (
                _subject_identity(
                    _select(
                        self.runtime,
                        raw["context"]["applies_to"],
                        raw["subject"]["subject_job_id"],
                    )
                )
                != raw["subject"]
            ):
                raise _unavailable("PRODUCT_RUNTIME_CHANGED")
            if self._principal(raw, reply) != principal:
                raise _unavailable("PRODUCT_PRINCIPAL_GENERATION_CHANGED")
            old = self.runtime.store.get_event_by_command_id(
                COMMAND_PREFIX + message_key, connection=connection
            )
            rows = self.runtime.store.list_events(
                aggregate_type=AGGREGATE,
                aggregate_id=message_key,
                connection=connection,
            )
            if old is not None or rows:
                if (
                    old is None
                    or len(rows) != 1
                    or rows[0].event_id != old.event_id
                    or old.event_type != EVENT_TYPE
                    or old.payload.get("receipt") != receipt
                    or old.payload.get("receipt_digest") != digest
                ):
                    raise _unavailable("PRODUCT_RULING_CONFLICT")
            else:
                self.runtime.store.append_event(
                    connection,
                    aggregate_type=AGGREGATE,
                    aggregate_id=message_key,
                    event_type=EVENT_TYPE,
                    actor="product-acceptance-ruling-owner",
                    job_id=selected.issuer_job_id,
                    attempt_id=selected.issuer_attempt_id,
                    worker_id=selected.issuer_worker_id,
                    command_id=COMMAND_PREFIX + message_key,
                    payload={
                        "receipt": receipt,
                        "receipt_digest": digest,
                        "source_continuity": dataclasses.asdict(continuity),
                    },
                )
        return _qualified_result(message_key, reply["message_key"], digest)
