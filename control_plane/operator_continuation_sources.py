"""Source-grounded builder for OCR-3 operator continuation drafts.

This module reads typed Executive Runtime records and caller-supplied canonical
references only. It writes no state, mints no identity/timestamp, and creates no
second memory, lifecycle, or retry plane.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from control_plane.executive_runtime import AttemptStatus, Runtime, StateConflict
from control_plane.operator_continuation import OperatorContinuationDraft


_TERMINAL = frozenset(
    {
        AttemptStatus.RATE_LIMITED,
        AttemptStatus.FAILED,
        AttemptStatus.LOST,
        AttemptStatus.COMPLETED,
        AttemptStatus.CANCELLED,
    }
)
_ACTIVE = frozenset(
    {
        AttemptStatus.CLAIMED,
        AttemptStatus.RUNNING,
        AttemptStatus.CHECKPOINTED,
        AttemptStatus.CANCEL_REQUESTED,
    }
)
_MAX_TEXT = 512


@dataclasses.dataclass(frozen=True)
class ContinuationExternalRefs:
    operation_key: str
    target_seat: str
    session_alias: str
    source_authority_refs: tuple[str, ...]
    agentos_refs: tuple[str, ...]
    github_state: Mapping[str, Any]
    slack_dialogue_ref: Mapping[str, Any] | None
    accepted_ruling_refs: tuple[str, ...]
    source_revisions: Mapping[str, str]


def _bounded_text(value: object, *, fallback: str) -> str:
    text = str(value or "").strip() or fallback
    return text[:_MAX_TEXT]


def _checkpoint_material(checkpoint: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if checkpoint is None:
        return None
    # Re-materialize only JobPayload-shaped keys.  Unknown provider/error fields
    # never become continuation memory merely because they happened to be stored.
    allowed = (
        "summary",
        "completed_steps",
        "current_state",
        "artifacts",
        "next_actions",
        "errors",
        "verdict",
    )
    return {key: checkpoint[key] for key in allowed if key in checkpoint}


def build_current_continuation_draft(
    runtime: Runtime,
    *,
    source_attempt_id: str,
    target_attempt_id: str,
    refs: ContinuationExternalRefs,
) -> OperatorContinuationDraft:
    """Build one semantic draft from current typed canonical sources.

    The builder is intentionally pre-PREPARE and non-durable.  Re-running it
    after a source fact changes is expected to produce a different semantic
    draft; PREPARE later owns immutability/idempotency.
    """

    source = runtime.attempts.get_attempt(source_attempt_id)
    target = runtime.attempts.get_attempt(target_attempt_id)
    if source is None or target is None:
        raise StateConflict("continuation source and target attempts must exist")
    if source.attempt_id == target.attempt_id:
        raise StateConflict("continuation source and target attempts must differ")
    if source.job_id != target.job_id:
        raise StateConflict("continuation attempts must belong to the same job")
    if source.status not in _TERMINAL:
        raise StateConflict("continuation source attempt must be terminal")
    if target.status not in _ACTIVE:
        raise StateConflict("continuation target attempt must be current and active")

    job = runtime.jobs.get_job(target.job_id)
    if job is None or job.current_attempt_id != target.attempt_id:
        raise StateConflict("continuation target is not the job's current attempt")
    if target.effective_grant_digest is None or target.effective_grant is None:
        raise StateConflict("continuation target lacks an effective grant")

    source_worker = runtime.workers.get_worker(source.worker_id)
    target_worker = runtime.workers.get_worker(target.worker_id)
    if source_worker is None or target_worker is None:
        raise StateConflict("continuation worker identity is unavailable")
    same_realm = (
        source_worker.provider == target_worker.provider
        and source_worker.account_label == target_worker.account_label
    )
    if same_realm:
        raise StateConflict("continuation requires a cross-realm claim")

    checkpoint = _checkpoint_material(source.checkpoint)
    next_actions = [] if checkpoint is None else list(checkpoint.get("next_actions") or [])
    errors = [] if checkpoint is None else list(checkpoint.get("errors") or [])
    next_action = _bounded_text(
        next_actions[0] if next_actions else None,
        fallback=f"Continue job {job.job_id}: {job.objective}",
    )
    known_unknowns = tuple(_bounded_text(item, fallback="unknown") for item in errors[:16])

    prior_attempt_receipt = {
        "attempt_id": source.attempt_id,
        "status": source.status.value,
        "terminal": True,
        "worker_id": source.worker_id,
        "quota_class": source.quota_class,
        "checkpoint_sequence": source.checkpoint_sequence,
    }

    return OperatorContinuationDraft(
        root_job_id=job.root_job_id or job.job_id,
        job_id=job.job_id,
        source_attempt_id=source.attempt_id,
        target_attempt_id=target.attempt_id,
        operation_key=refs.operation_key,
        target_seat=refs.target_seat,
        session_alias=refs.session_alias,
        effective_grant_digest=target.effective_grant_digest,
        source_authority_refs=refs.source_authority_refs,
        agentos_refs=refs.agentos_refs,
        github_state=dict(refs.github_state),
        prior_attempt_receipt=prior_attempt_receipt,
        checkpoint=checkpoint,
        slack_dialogue_ref=(
            None if refs.slack_dialogue_ref is None else dict(refs.slack_dialogue_ref)
        ),
        accepted_ruling_refs=refs.accepted_ruling_refs,
        next_action=next_action,
        known_unknowns=known_unknowns,
        source_revisions=dict(refs.source_revisions),
    )


__all__ = ["ContinuationExternalRefs", "build_current_continuation_draft"]
