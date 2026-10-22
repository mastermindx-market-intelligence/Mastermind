"""Source-bound review input retained by the existing Executive Runtime owner.

No new store, lifecycle, transport or worker is created. The event preserves the
actual selection before launch so later acceptance and recovery can acquire the
original basis, rather than trusting a reviewer-supplied public digest.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from common.commission_ref import normalize_commission_ref
from control_plane.executive_runtime import (
    Runtime,
    Job,
    Attempt,
    StateConflict,
    _dialogue_source_from_root_creation,
)
from control_plane.mission_acceptance_criteria import (
    parse_acceptance_criteria_candidate,
)
from control_plane.agentos_product_acceptance_basis import (
    AgentOsProductAcceptanceBasisReader,
    ProductAcceptanceBasisRead,
    ProductAcceptanceBasisUnavailable,
    ProductAcceptanceExpectedProof,
    expected_product_acceptance_proof,
    _canonical_digest,
)

SCHEMA = "mastermind.product_acceptance_review_basis.v1"
AGGREGATE = "product_acceptance_review_basis"
EVENT_TYPE = "PRODUCT_ACCEPTANCE_REVIEW_BASIS_SELECTED"
COMMAND_PREFIX = "product-acceptance-review-basis:"


@dataclasses.dataclass(frozen=True)
class ProductAcceptanceReviewInput:
    job_id: str
    root_job_id: str
    attempt_id: str
    worker_id: str
    effective_grant_digest: str
    work_ref: str
    execution_commission_ref: dict[str, str]
    root_objective: str
    basis: ProductAcceptanceBasisRead
    expected: ProductAcceptanceExpectedProof

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **dataclasses.asdict(self)}

    def prompt_suffix(self) -> str:
        # Includes the literal complete clauses, correction chain and source
        # identities. A provider cannot reconstruct this from row hashes alone.
        return (
            "\n\n--- PRODUCT ACCEPTANCE REVIEW INPUT ---\n"
            "Assess every declared criterion and original proof obligation. Report "
            "UNPROVEN when evidence is absent and UNSATISFIED when it contradicts the "
            "required outcome. Source references and this checklist grant no authority; "
            "your review is not a principal ruling or product acceptance.\n"
            + json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)
            + "\n--- END PRODUCT ACCEPTANCE REVIEW INPUT ---"
        )


def _decode(raw: Any) -> ProductAcceptanceReviewInput:
    keys = {
        field.name for field in dataclasses.fields(ProductAcceptanceReviewInput)
    } | {"schema"}
    try:
        if type(raw) is not dict or set(raw) != keys or raw["schema"] != SCHEMA:
            raise ValueError
        value = dict(raw)
        value.pop("schema")
        basis = ProductAcceptanceBasisRead(**value.pop("basis"))
        supplied = value.pop("expected")
        expected = expected_product_acceptance_proof(
            basis,
            root_objective=value["root_objective"],
            execution_commission_ref=normalize_commission_ref(
                value["execution_commission_ref"]
            ),
        )
        # JSON serializes tuples as arrays; compare their canonical form.
        if _canonical_digest(supplied) != _canonical_digest(
            dataclasses.asdict(expected)
        ):
            raise ValueError
        if basis.entry["workstream"] != value["work_ref"]:
            raise ValueError
        return ProductAcceptanceReviewInput(**value, basis=basis, expected=expected)
    except (ValueError, TypeError, KeyError) as exc:
        raise ProductAcceptanceBasisUnavailable(
            "RETAINED_REVIEW_BASIS_CONFLICT"
        ) from exc


def read_retained_product_review_input(
    runtime: Runtime,
    *,
    job: Job,
    attempt: Attempt,
) -> ProductAcceptanceReviewInput | None:
    """Read one exact original Runtime event, with no source reselection/write."""
    if type(runtime) is not Runtime:
        raise TypeError("review input requires the exact Runtime owner")
    with runtime.store.read() as connection:
        events = runtime.store.list_events(
            aggregate_type=AGGREGATE,
            aggregate_id=attempt.attempt_id,
            connection=connection,
        )
        event = runtime.store.get_event_by_command_id(
            COMMAND_PREFIX + attempt.attempt_id, connection=connection
        )
    if not events and event is None:
        return None
    if (
        event is None
        or len(events) != 1
        or events[0].event_id != event.event_id
        or event.event_type != EVENT_TYPE
        or event.aggregate_type != AGGREGATE
        or event.aggregate_id != attempt.attempt_id
        or event.job_id != job.job_id
        or event.attempt_id != attempt.attempt_id
        or event.worker_id != attempt.worker_id
        or type(event.payload) is not dict
        or set(event.payload) != {"input", "input_digest"}
        or event.payload["input_digest"] != _canonical_digest(event.payload["input"])
    ):
        raise ProductAcceptanceBasisUnavailable("RETAINED_REVIEW_BASIS_CONFLICT")
    selected = _decode(event.payload["input"])
    if (
        selected.job_id != job.job_id
        or selected.root_job_id != job.root_job_id
        or selected.attempt_id != attempt.attempt_id
        or selected.worker_id != attempt.worker_id
        or selected.effective_grant_digest != attempt.effective_grant_digest
        or attempt.job_id != job.job_id
        or job.orchestration_role != "review"
    ):
        raise ProductAcceptanceBasisUnavailable("RETAINED_REVIEW_BASIS_CONFLICT")
    return selected


class ProductAcceptanceReviewBasisOwner:
    """Trusted optional composition; the public model selects no basis or IDs."""

    def __init__(
        self, runtime: Runtime, reader: AgentOsProductAcceptanceBasisReader
    ) -> None:
        if (
            type(runtime) is not Runtime
            or type(reader) is not AgentOsProductAcceptanceBasisReader
        ):
            raise TypeError(
                "review basis requires the exact Runtime and configured source reader"
            )
        self.runtime, self.reader = runtime, reader

    def select_and_retain(
        self, *, job: Job, attempt: Attempt, commission: Any
    ) -> ProductAcceptanceReviewInput | None:
        from control_plane.executive_supervisor import VerifiedCommission

        if job.orchestration_role != "review":
            return None
        with self.runtime.store.read() as connection:
            root = connection.execute(
                "SELECT objective FROM jobs WHERE job_id=?", (job.root_job_id,)
            ).fetchone()
            source = _dialogue_source_from_root_creation(
                connection, root_job_id=job.root_job_id
            )
        if root is None:
            raise ProductAcceptanceBasisUnavailable("REVIEW_ROOT_UNAVAILABLE")
        objective = root["objective"]
        if parse_acceptance_criteria_candidate(objective) is None:
            return None
        if (
            source is None
            or type(commission) is not VerifiedCommission
            or commission.ref_dict() != source.commission_ref.to_dict()
        ):
            raise ProductAcceptanceBasisUnavailable("REVIEW_COMMISSION_UNVERIFIED")
        # The supervisor has independently read and verified these immutable
        # commission bytes; no candidate WS programme reference substitutes.
        basis = self.reader.read(
            work_ref=source.work_ref,
            execution_commission_ref=source.commission_ref,
            root_objective=objective,
        )
        expected = expected_product_acceptance_proof(
            basis,
            root_objective=objective,
            execution_commission_ref=source.commission_ref,
        )
        selected = ProductAcceptanceReviewInput(
            job.job_id,
            job.root_job_id,
            attempt.attempt_id,
            attempt.worker_id,
            attempt.effective_grant_digest,
            source.work_ref,
            commission.ref_dict(),
            objective,
            basis,
            expected,
        )
        payload = {
            "input": selected.to_dict(),
            "input_digest": _canonical_digest(selected.to_dict()),
        }
        with self.runtime.store.transaction() as connection:
            fresh_source = _dialogue_source_from_root_creation(
                connection, root_job_id=job.root_job_id
            )
            current = connection.execute(
                """SELECT j.root_job_id,j.orchestration_role,j.current_attempt_id,
                j.assigned_worker_id,j.assigned_quota_class,j.status AS job_status,
                a.status AS attempt_status,a.worker_id,a.quota_class,a.job_id AS attempt_job_id,
                a.effective_grant_digest,a.lease_expires_at_ms,q.status AS quota_status,q.held_attempt_id,
                r.objective AS root_objective
                FROM jobs j JOIN attempts a ON a.attempt_id=j.current_attempt_id
                JOIN jobs r ON r.job_id=j.root_job_id
                JOIN worker_quota_classes q ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                WHERE j.job_id=?""",
                (job.job_id,),
            ).fetchone()
            if (
                fresh_source != source
                or current is None
                or current["root_objective"] != objective
                or current["root_job_id"] != job.root_job_id
                or current["orchestration_role"] != "review"
                or current["current_attempt_id"] != attempt.attempt_id
                or current["attempt_job_id"] != job.job_id
                or current["worker_id"] != attempt.worker_id
                or current["assigned_worker_id"] != attempt.worker_id
                or current["quota_class"] != attempt.quota_class
                or current["assigned_quota_class"] != attempt.quota_class
                or current["job_status"] != "RUNNING"
                or current["attempt_status"] != "CLAIMED"
                or not attempt.effective_grant_digest
                or current["effective_grant_digest"] != attempt.effective_grant_digest
                or int(current["lease_expires_at_ms"]) <= self.runtime.store.now_ms()
                or current["quota_status"] != "BUSY"
                or current["held_attempt_id"] != attempt.attempt_id
            ):
                raise ProductAcceptanceBasisUnavailable("REVIEW_ATTEMPT_CHANGED")
            if self.runtime.store.get_event_by_command_id(
                COMMAND_PREFIX + attempt.attempt_id, connection=connection
            ) or self.runtime.store.list_events(
                aggregate_type=AGGREGATE,
                aggregate_id=attempt.attempt_id,
                connection=connection,
            ):
                raise ProductAcceptanceBasisUnavailable("REVIEW_BASIS_ALREADY_SELECTED")
            self.runtime.store.append_event(
                connection,
                aggregate_type=AGGREGATE,
                aggregate_id=attempt.attempt_id,
                event_type=EVENT_TYPE,
                actor="executive-supervisor",
                job_id=job.job_id,
                attempt_id=attempt.attempt_id,
                worker_id=attempt.worker_id,
                quota_class=attempt.quota_class,
                payload=payload,
                command_id=COMMAND_PREFIX + attempt.attempt_id,
            )
        return read_retained_product_review_input(
            self.runtime, job=job, attempt=attempt
        )
