"""Finite read-only proof reader for one CEO-offline Executive delivery."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane.executive_runtime import JobStatus, Runtime, RuntimeProofError, StateConflict
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository


RECEIPT_SCHEMA = "mastermind.web_ceo_offline_delivery_canary/v1"
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
        for event in runtime.events.list_events(job_id=root_job_id)
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

    terminal_events = [
        event
        for event in runtime.events.list_events(
            aggregate_type="terminal_return_projection",
            aggregate_id=material.attempt.attempt_id,
        )
    ]
    event_types = [event.event_type for event in terminal_events]
    applied_count = event_types.count("EXECUTIVE_TERMINAL_RETURN_APPLIED")
    if applied_count > 1:
        raise CanaryReaderError("TERMINAL_PROJECTION_AMBIGUOUS")
    projection = (
        "APPLIED"
        if "EXECUTIVE_TERMINAL_RETURN_APPLIED" in event_types
        else "EFFECT_UNKNOWN"
        if "EXECUTIVE_TERMINAL_RETURN_EFFECT_UNKNOWN" in event_types
        else "ATTEMPTED"
        if "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED" in event_types
        else "NOT_ATTEMPTED"
    )
    if projection == "APPLIED":
        projection_state = "DELIVERED_NOT_CONSUMED"
    elif projection == "EFFECT_UNKNOWN":
        raise CanaryReaderError("EFFECT_UNKNOWN_UNRESOLVED")
    else:
        projection_state = "PENDING_UNCONSUMED"

    wake_records = []
    for persisted in WakeLedgerRepository(runtime).list_wake_events():
        obligation = persisted.record.obligation
        if obligation is None:
            continue
        if (
            obligation.root_job_id == root_job_id
            and obligation.job_id == root_job_id
            and obligation.attempt_id == material.attempt.attempt_id
        ):
            wake_records.append(persisted.record)
    if wake_records:
        phases = {record.phase for record in wake_records}
        if LedgerPhase.TARGET_ACKNOWLEDGED in phases:
            projection_state = "CONSUMED"
        elif LedgerPhase.DELIVERED not in phases:
            raise CanaryReaderError("EFFECT_UNKNOWN_UNRESOLVED")

    return {
        "schema": RECEIPT_SCHEMA,
        "release_sha": expected_release_sha,
        "root_job_id": root_job_id,
        "plan_digest": str(material.job.plan_digest or aggregation_body["plan_digest"]),
        "work_revisions": work,
        "review_revisions": reviews,
        "repair_revisions": repairs,
        "aggregation_result_digest": material.role_result_digest,
        "web_sol_turns_between_admission_and_handoff": 0,
        "manual_continue_edges": 0,
        "parent_consumption_state": projection_state,
        "production_acceptance_state": "PENDING",
        "effect_uncertainty": "NONE",
        "source_evidence": {
            "aggregation_terminal": "RUNTIME_VALIDATED",
            "independent_review": "QUALIFIED",
            "terminal_projection": projection,
            "wake_delivery": (
                "REQUESTED_DELIVERED" if wake_records else "NOT_REQUESTED"
            ),
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
