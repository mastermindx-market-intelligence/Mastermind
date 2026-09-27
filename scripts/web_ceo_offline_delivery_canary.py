"""Finite read-only proof reader for one CEO-offline Executive delivery."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane.executive_dialogue_observation import (
    CanonicalTerminalWakeCandidate,
    DialogueObservationFacts,
    TerminalObservationFacts,
    TerminalProjectionReceiptFacts,
    inspect_terminal_return_history,
    normalize_terminal_return_projection_receipt,
    read_canonical_terminal_wake,
    terminal_return_event_material,
    terminal_return_phase_spec,
)
from control_plane.executive_runtime import JobStatus, Runtime, RuntimeProofError, StateConflict
from control_plane.executive_terminal_return import reduce_terminal_return
from control_plane.wake_ledger import (
    ATTEMPT_PHASES,
    EFFECT_KNOWN_PHASES,
    LedgerPhase,
    assert_causal,
)
from control_plane.wake_persist import WakeLedgerRepository


LEGACY_RECEIPT_SCHEMA = "mastermind.web_ceo_offline_delivery_canary/v1"
RECEIPT_SCHEMA = "mastermind.web_ceo_offline_delivery_canary/v2"
ERROR_SCHEMA = "mastermind.web_ceo_offline_delivery_canary.error/v1"
_SHA1_LENGTH = 40
_JOB_ID_PREFIX = "JOB-"
_JOB_ID_MIN_LENGTH = 5


class CanaryReaderError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _utc(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CanaryReaderError("OBSERVED_AT_INVALID") from exc
    if parsed.utcoffset() is not None and parsed.microsecond == 0:
        return value
    raise CanaryReaderError("OBSERVED_AT_INVALID")


def _material(
    runtime: Runtime,
    root_job_id: str,
) -> tuple[Any, Any]:
    root = runtime.jobs.get_job(root_job_id)
    if root is None or root.current_attempt_id is None:
        raise CanaryReaderError("ROOT_CANONICAL_MATERIAL_INVALID")
    try:
        material = runtime.validated_role_completion(
            root_job_id,
            expected_attempt_id=root.current_attempt_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise CanaryReaderError("ROOT_CANONICAL_MATERIAL_INVALID") from exc
    if (
        material.job.job_id != root_job_id
        or material.job.root_job_id != root_job_id
        or material.job.orchestration_role != "aggregation"
        or material.job.status is not JobStatus.COMPLETED
        or material.attempt.job_id != root_job_id
        or material.attempt.attempt_id != root.current_attempt_id
    ):
        raise CanaryReaderError("ROOT_NOT_AGGREGATION")
    return material, material.result_envelope["role_result"]


def _unmeasured_interventions() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "state": "UNMEASURED",
            "reason": "CANONICAL_EVENT_SOURCE_ABSENT",
            "interval_start": None,
            "interval_end": None,
        }
        for name in (
            "web_sol_turns_between_admission_and_handoff",
            "manual_continue_edges",
        )
    }


def _wake_projection(
    runtime: Runtime,
    *,
    root_job_id: str,
    terminal_candidate: Any,
    projection_receipt: TerminalProjectionReceiptFacts,
) -> tuple[str, str | None]:
    canonical_candidate = CanonicalTerminalWakeCandidate(
        root_job_id=terminal_candidate.root_job_id,
        job_id=terminal_candidate.job_id,
        attempt_id=terminal_candidate.attempt_id,
        worker_id=terminal_candidate.worker_id,
    )

    def facts_provider(_runtime: Any, requested: Any, _connection: Any):
        if requested != canonical_candidate:
            return DialogueObservationFacts(complete=False)
        return DialogueObservationFacts(
            terminal=(
                TerminalObservationFacts(
                    candidate=terminal_candidate,
                    projection_receipt=projection_receipt,
                    projection_effect="APPLIED",
                    binding_revalidated=True,
                ),
            )
        )

    repository = WakeLedgerRepository(runtime)
    with runtime.store.read() as connection:
        canonical = read_canonical_terminal_wake(
            runtime=runtime,
            source_root_job_id=root_job_id,
            candidate=canonical_candidate,
            facts_provider=facts_provider,
            connection=connection,
        )
        if canonical.state == "ABSENT" and canonical.reason == "CORRELATED_WAKE_ABSENT":
            return "NOT_REQUESTED", None
        if canonical.state == "AMBIGUOUS":
            raise CanaryReaderError("WAKE_OBLIGATION_AMBIGUOUS")
        if canonical.reason == "WAKE_EVENT_BUDGET_EXCEEDED":
            raise CanaryReaderError("WAKE_EVENT_BUDGET_EXCEEDED")
        if canonical.reason == "CANONICAL_TERMINAL_UNAVAILABLE":
            raise CanaryReaderError("WAKE_CORRELATION_UNAVAILABLE")
        if (
            canonical.state != "RESOLVED"
            or canonical.wake is None
            or canonical.terminal is None
        ):
            raise CanaryReaderError("WAKE_OBLIGATION_INVALID")

        records = repository.list_ledger_records_on_connection(
            connection, canonical.wake.obligation_id
        )
        requested = [
            record for record in records if record.phase is LedgerPhase.WAKE_REQUESTED
        ]
        if len(requested) != 1 or requested[0].obligation is None:
            raise CanaryReaderError("WAKE_OBLIGATION_INVALID")
        request = requested[0]
        obligation = request.obligation
        physical = request.physical_source
        expected_candidate = {
            "mode": "TERMINAL_RESULT",
            "root_job_id": terminal_candidate.root_job_id,
            "job_id": terminal_candidate.job_id,
            "attempt_id": terminal_candidate.attempt_id,
            "worker_id": terminal_candidate.worker_id,
            "evidence_digest": canonical.terminal.evidence_digest,
        }
        if (
            physical is None
            or physical.logical_source_ref != obligation.source_ref
            or physical.obligation_id != obligation.obligation_id
            or physical.thread_ts != projection_receipt.thread_ts
            or physical.parent_fingerprint != projection_receipt.parent_fingerprint
            or physical.operation_key != terminal_candidate.operation_key
            or physical.predecessor_message_key != terminal_candidate.message_key
            or physical.predecessor_message_fingerprint
            != projection_receipt.fingerprint
            or physical.target_seat != "ceo"
            or obligation.declared_target_seat != "ceo"
            or physical.candidate.to_dict() != expected_candidate
        ):
            raise CanaryReaderError("WAKE_PHYSICAL_SOURCE_INVALID")

        phases_by_attempt: dict[int, set[LedgerPhase]] = {}
        for record in records:
            if record.phase in ATTEMPT_PHASES and record.attempt_n is not None:
                phases_by_attempt.setdefault(record.attempt_n, set()).add(record.phase)
        if any(
            LedgerPhase.DELIVERY_ATTEMPT in phases
            and not (phases & EFFECT_KNOWN_PHASES)
            for phases in phases_by_attempt.values()
        ):
            raise CanaryReaderError("EFFECT_UNKNOWN_UNRESOLVED")
        acknowledgements = [
            record
            for record in records
            if record.phase is LedgerPhase.TARGET_ACKNOWLEDGED
        ]
        if len(acknowledgements) > 1:
            raise CanaryReaderError("WAKE_OBLIGATION_AMBIGUOUS")
        acknowledgement_mode = None
        if acknowledgements:
            acknowledgement = acknowledgements[0].ack
            if acknowledgement is None:
                raise CanaryReaderError("WAKE_OBLIGATION_INVALID")
            acknowledgement_mode = acknowledgement.ack_mode.value
        return records[-1].phase.value, acknowledgement_mode


def _terminal_projection(
    runtime: Runtime,
    material: Any,
) -> tuple[str, Any, TerminalProjectionReceiptFacts | None]:
    try:
        terminal_events = runtime.events.list_events(
            aggregate_type="terminal_return_projection",
            aggregate_id=material.attempt.attempt_id,
        )
        if sum(
            event.event_type == "EXECUTIVE_TERMINAL_RETURN_APPLIED"
            for event in terminal_events
        ) > 1:
            raise CanaryReaderError("TERMINAL_PROJECTION_AMBIGUOUS")
        candidate = reduce_terminal_return(material=material)
        command_base, event_material = terminal_return_event_material(candidate)
        projection_receipt = None
        with runtime.store.read() as connection:
            phase = inspect_terminal_return_history(
                runtime,
                connection,
                candidate=candidate,
                material=event_material,
            )
            if phase == "APPLIED":
                applied_command = terminal_return_phase_spec(command_base)[-1][2]
                applied_event = runtime.store.get_event_by_command_id(
                    applied_command,
                    connection=connection,
                )
                if applied_event is None:
                    raise CanaryReaderError("TERMINAL_PROJECTION_INVALID")
                normalized = normalize_terminal_return_projection_receipt(
                    applied_event.payload.get("projection_receipt"),
                    message_key=candidate.message_key,
                )
                normalized["duplicate_timestamps"] = tuple(
                    normalized["duplicate_timestamps"]
                )
                projection_receipt = TerminalProjectionReceiptFacts(**normalized)
    except CanaryReaderError:
        raise
    except (RuntimeError, TypeError, ValueError) as exc:
        raise CanaryReaderError("TERMINAL_PROJECTION_INVALID") from exc
    if phase in {"ATTEMPTED", "EFFECT_UNKNOWN"}:
        raise CanaryReaderError("EFFECT_UNKNOWN_UNRESOLVED")
    return phase or "NOT_ATTEMPTED", candidate, projection_receipt


def build_receipt(
    runtime: Runtime,
    *,
    root_job_id: str,
    expected_release_sha: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(root_job_id, str)
        or not root_job_id.startswith(_JOB_ID_PREFIX)
        or len(root_job_id) < _JOB_ID_MIN_LENGTH
        or not root_job_id[len(_JOB_ID_PREFIX) :].isdigit()
    ):
        raise CanaryReaderError("ROOT_JOB_ID_INVALID")
    if (
        not isinstance(expected_release_sha, str)
        or len(expected_release_sha) != _SHA1_LENGTH
        or any(char not in "0123456789abcdef" for char in expected_release_sha)
    ):
        raise CanaryReaderError("EXPECTED_RELEASE_INVALID")
    stamp = _utc(observed_at)
    if runtime.jobs.get_job(root_job_id) is None:
        raise CanaryReaderError("ROOT_NOT_FOUND")

    creation_events = [
        event
        for event in runtime.events.list_events(
            job_id=root_job_id,
            aggregate_type="job",
            aggregate_id=root_job_id,
        )
        if event.event_type == "JOB_CREATED"
    ]
    if len(creation_events) != 1:
        raise CanaryReaderError("ROOT_CREATION_NOT_FOUND")
    creation = creation_events[0].payload

    material, aggregation_body = _material(runtime, root_job_id)
    provenance = creation.get("provenance") or {}
    grounding = provenance.get("grounding") or {}
    if grounding.get("mastermind_sha") != expected_release_sha:
        raise CanaryReaderError("EXPECTED_RELEASE_MISMATCH")

    children = [
        job
        for job in runtime.jobs.list_jobs()
        if job.root_job_id == root_job_id
        and job.job_id != root_job_id
        and job.orchestration_role
    ]
    child_roles = {job.orchestration_role for job in children}
    if not child_roles <= {"plan", "work", "review", "repair"}:
        raise CanaryReaderError("CHILD_LINEAGE_INVALID")

    current_ids = {item["current_job_id"] for item in aggregation_body["revisions"]}
    if any(job.attempt_count != 1 for job in children):
        raise CanaryReaderError("REVISION_CURRENT_AMBIGUOUS")
    current_jobs = {
        job.job_id
        for job in children
        if job.orchestration_role in {"work", "repair"} and job.job_id in current_ids
    }
    if len(current_jobs) != len(current_ids):
        raise CanaryReaderError("REVISION_CURRENT_AMBIGUOUS")
    superseded_ids = {
        job.supersedes_job_id
        for job in children
        if job.orchestration_role == "repair" and job.supersedes_job_id is not None
    }
    if current_jobs & superseded_ids:
        raise CanaryReaderError("REVISION_NOT_CURRENT")
    work_revision_ids = {
        job.job_id
        for job in children
        if job.orchestration_role in {"work", "repair"}
    }
    if any(
        job.supersedes_job_id is not None
        and job.supersedes_job_id not in work_revision_ids
        for job in children
    ):
        raise CanaryReaderError("REVISION_CHAIN_INVALID")
    review_jobs = {
        job.job_id: job for job in children if job.orchestration_role == "review"
    }
    if any(
        not isinstance(job.reviews_job_id, str)
        or job.reviews_job_id not in current_jobs | superseded_ids
        for job in review_jobs.values()
    ):
        raise CanaryReaderError("INDEPENDENT_REVIEW_INCOMPLETE")

    revisions: dict[str, list[dict[str, Any]]] = {
        "work": [],
        "review": [],
        "repair": [],
    }
    for job in children:
        if job.current_attempt_id is None or job.status is not JobStatus.COMPLETED:
            raise CanaryReaderError("CHILD_LINEAGE_INCOMPLETE")
        if job.parent_job_id != root_job_id or job.depth != 1:
            raise CanaryReaderError("CHILD_LINEAGE_INVALID")
        if job.orchestration_role == "plan" and any(
            value is not None
            for value in (
                job.plan_attempt_id,
                job.plan_digest,
                job.plan_step_id,
                job.repair_round,
                job.reviews_job_id,
                job.supersedes_job_id,
            )
        ):
            raise CanaryReaderError("CHILD_LINEAGE_INVALID")
        if job.orchestration_role == "work" and (
            job.repair_round != 0
            or job.reviews_job_id is not None
            or job.supersedes_job_id is not None
        ):
            raise CanaryReaderError("CHILD_LINEAGE_INVALID")
        if job.orchestration_role == "repair" and (
            not job.supersedes_job_id or job.reviews_job_id is not None
        ):
            raise CanaryReaderError("CHILD_LINEAGE_INVALID")
        if job.orchestration_role == "review" and (
            not job.reviews_job_id or job.supersedes_job_id is not None
        ):
            raise CanaryReaderError("CHILD_LINEAGE_INVALID")
        if job.orchestration_role == "repair":
            predecessor_ids = {
                item.job_id
                for item in children
                if item.orchestration_role in {"work", "repair"}
                and item.supersedes_job_id is None
            }
            if job.supersedes_job_id not in predecessor_ids:
                raise CanaryReaderError("REVISION_CHAIN_INVALID")
        try:
            child = runtime.validated_role_completion(
                job.job_id,
                expected_attempt_id=str(job.current_attempt_id),
            )
        except (RuntimeError, ValueError) as exc:
            raise CanaryReaderError("LINEAGE_CANONICAL_MATERIAL_INVALID") from exc
        body = child.result_envelope["role_result"]
        if job.orchestration_role in {"work", "repair"}:
            revisions[job.orchestration_role].append(
                {
                    "job_id": job.job_id,
                    "attempt_id": child.attempt.attempt_id,
                    "result_digest": child.role_result_digest,
                }
            )
        elif job.orchestration_role == "review":
            revisions["review"].append(
                {
                    "job_id": job.job_id,
                    "attempt_id": child.attempt.attempt_id,
                    "result_digest": child.role_result_digest,
                    "verdict": body["verdict"],
                }
            )

    qualifying_ids = {
        item["qualifying_review_job_id"] for item in aggregation_body["revisions"]
    }
    work = revisions["work"]
    repairs = revisions["repair"]
    reviews = revisions["review"]
    if (
        not current_ids
        or len(work) != 1
        or not repairs
        or [item["verdict"] for item in reviews] != ["reject", "approve"]
        or reviews[0]["job_id"] in qualifying_ids
        or reviews[1]["job_id"] not in qualifying_ids
        or not current_ids <= {work[0]["job_id"], *(item["job_id"] for item in repairs)}
    ):
        raise CanaryReaderError("INDEPENDENT_REVIEW_INCOMPLETE")

    projection, terminal_candidate, projection_receipt = _terminal_projection(
        runtime, material
    )

    if projection == "APPLIED":
        if projection_receipt is None:
            raise CanaryReaderError("TERMINAL_PROJECTION_INVALID")
        wake_state, wake_acknowledgement_mode = _wake_projection(
            runtime,
            root_job_id=root_job_id,
            terminal_candidate=terminal_candidate,
            projection_receipt=projection_receipt,
        )
    else:
        wake_state, wake_acknowledgement_mode = "NOT_REQUESTED", None
    intervention_measurements = _unmeasured_interventions()
    semantic_parent_action_state = "NOT_OBSERVED"

    return {
        "schema": RECEIPT_SCHEMA,
        "release_sha": expected_release_sha,
        "root_job_id": root_job_id,
        "plan_digest": str(material.job.plan_digest or aggregation_body["plan_digest"]),
        "work_revisions": work,
        "review_revisions": reviews,
        "repair_revisions": repairs,
        "aggregation_result_digest": material.role_result_digest,
        "web_sol_turns_between_admission_and_handoff": None,
        "manual_continue_edges": None,
        "intervention_measurements": intervention_measurements,
        "terminal_return_projection_state": projection,
        "wake_obligation_state": wake_state,
        "wake_acknowledgement_mode": wake_acknowledgement_mode,
        "semantic_parent_action_state": semantic_parent_action_state,
        "production_acceptance_state": "PENDING",
        "stage_promotion_eligible": False,
        "proof_admissibility": {
            "scope": "SOURCE_LINEAGE_ONLY",
            "stage_promotion": "HOLD",
            "legacy_v1": "NON_PROMOTABLE",
        },
        "effect_uncertainty": "NONE",
        "source_evidence": {
            "aggregation_terminal": "RUNTIME_VALIDATED",
            "independent_review": "QUALIFIED",
            "terminal_projection": projection,
            "wake_obligation": wake_state,
            "semantic_parent_action": semantic_parent_action_state,
            "intervention_measurements": "UNMEASURED",
        },
        "observed_at": stamp,
    }


def _error(root_job_id: str, code: str) -> dict[str, str]:
    return {"schema": ERROR_SCHEMA, "error": code, "root_job_id": root_job_id}


class _ClosedParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CanaryReaderError("INPUT_REFUSED")


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedParser(
        prog="web-ceo-offline-delivery-canary",
        description="Read one finite CEO-offline Executive delivery proof.",
    )
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--control-socket", required=True)
    parser.add_argument("--root-job-id", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--observed-at")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    root_job_id = "<unknown>"
    try:
        args = parser.parse_args(argv)
        root_job_id = args.root_job_id
        from control_plane.executive_service import send_control_request
        async def read_installed():
            return await asyncio.wait_for(send_control_request(
                args.control_socket, "offline-delivery-observation", {
                    "runtime_root": args.runtime_root,
                    "root_job_id": root_job_id,
                    "expected_release_sha": args.expected_release_sha,
                    "observed_at": args.observed_at,
                },
            ), timeout=5.0)
        response = asyncio.run(read_installed())
        if response.get("ok") is not True or not isinstance(response.get("result"), dict):
            raise CanaryReaderError("INPUT_REFUSED")
        receipt = response["result"]
    except (
        argparse.ArgumentTypeError,
        CanaryReaderError,
        OSError,
        RuntimeProofError,
        TimeoutError,
        asyncio.IncompleteReadError,
    ):
        json.dump(_error(root_job_id, "INPUT_REFUSED"), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(receipt, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
