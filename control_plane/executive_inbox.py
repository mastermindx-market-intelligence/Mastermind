"""control_plane.executive_inbox — the read-only Executive Inbox projection.

The Executive OS runtime (:mod:`control_plane.executive_runtime`) accumulates
hundreds of Job / Attempt / Worker / Event rows.  Almost all of them are routine:
work that queued, ran, and completed exactly as asked.  This module projects that
durable state down to the small set of things a human-or-AI executive seat must
actually look at, and says who each one belongs to.

It is a PROJECTION, not an authority.  The SQLite runtime remains the only
lifecycle authority; the Improvement Agenda remains the company priority queue;
Agent OS remains the knowledge plane.  The inbox identifies ATTENTION.  It never
ranks the roadmap, never decides eligibility, never dispatches, and never writes.

Design laws
-----------
* **No second control plane.**  No new database, table, queue, scheduler, lease,
  registry, or liveness store is created here, and this module writes no file,
  ever.  Everything it emits is derived from rows that already exist.  A durable
  "inbox state" would be exactly the ``constraints.duplicate_control_planes``
  prohibition the strategic state names — so the inbox is recomputed from
  canonical rows on every call and remembers nothing between calls.
* **The runtime is read through its own typed registries.**  ``Runtime.at(root)``
  then ``list_jobs`` / ``list_attempts`` / ``list_workers`` / ``list_events``.  No
  raw SQL lives in this module: a projector that reimplemented the runtime's row
  decoding would silently disagree with it the first time the schema moved.  The
  cost of that choice is visible and deliberate — one undecodable row raises out
  of the registry and hides that registry's whole surface, which lands as a named
  ``degraded`` entry rather than as a quietly shorter list.
* **The database is never created, migrated, or re-moded by a reader.**  The file's
  existence is checked before anything is constructed, and the store is then
  opened with ``Runtime.at(root, create=False)`` — SQLite ``mode=ro``, no
  ``mkdir``, no ``chmod``, no ``journal_mode``/``synchronous`` pragma, no
  migration, and ``transaction()`` refuses.  Existence alone was not enough: a
  0-byte husk, a truncated restore, or a foreign SQLite file would otherwise have
  the FULL Executive OS schema written into it by the reader and then be reported
  as a quiet company.  ``create=False`` verifies the schema is present instead and
  degrades by name when it is not.  The one residue, disclosed rather than
  hidden: opening a **WAL** database — the mode this runtime uses — lets SQLite
  create its ``-wal``/``-shm`` wal-index sidecars.  Those carry no committed
  state, the committed database file stays byte-identical, and a ``delete``-mode
  database gets no sidecar at all.
* **Labels confer no privilege.**  ``target`` is derived from the KIND of the
  problem, never from ``department``, ``priority``, a P0 id, an owner, an actor
  name, or an executive title.  ``Sol`` / ``CEO`` / ``COO`` are provenance labels
  with zero authority attached.  A FAILED job submitted by the CEO seat is still a
  COO operational exception.
* **Fail open, and name the gap.**  An unreadable input becomes an entry in
  ``degraded``; it never becomes a traceback and never becomes a quiet success.
  The CLI always exits 0 once its arguments parse.  The inverse of
  :mod:`control_plane.strategic_state`'s fail-loud contract, for the same reason
  :mod:`control_plane.ceo_boot_packet` states: an executive who cannot read the
  org must be TOLD that, loudly.
* **No invented recommendations.**  ``reason`` is assembled only from canonical
  fields, and ``existing_next_actions`` is copied verbatim from the payload the
  runtime already stored.  The inbox never authors advice.
* **Deterministic.**  Same canonical state plus the same ``now`` produces a
  byte-identical document: every list is sorted by a declared key, every
  ``by_status`` map carries every enum member, and nothing reads a uuid or a
  random source.  The clock is read exactly ONCE per build, and only when ``now``
  was not supplied; that single value serves both ``generated_at`` and the
  ``stale_lease`` lease arithmetic.
* **Import-time stdlib only.**  From ``control_plane`` this module imports exactly
  :mod:`control_plane.executive_runtime` and :mod:`control_plane.ceo_boot_packet`
  — nothing that dispatches, supervises, brokers, or executes.  An AST test in
  ``tests/test_executive_inbox.py`` pins that set.

Usage
-----
    from control_plane.executive_inbox import build_inbox, render_inbox
    inbox = build_inbox()
    print(render_inbox(inbox))
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane import ceo_boot_packet
from control_plane.executive_runtime import (
    Attempt,
    AttemptStatus,
    Job,
    JobPayload,
    JobStatus,
    Runtime,
    RuntimeProofError,
    WorkerStatus,
)

#: Schema version of the document this module emits.  A bump means a migration.
SCHEMA = "mastermind.executive_inbox.v2"

#: The boot-packet contract this projection understands.  Owned by
#: :mod:`control_plane.ceo_boot_packet`; a mismatch is reported, never mapped.
BOOT_PACKET_SCHEMA = ceo_boot_packet.SCHEMA

#: The Agent OS brief contract nested inside the packet, owned by Macro
#: ``scripts/agentos.py``.  A foreign brief is named, never read.
BRIEF_SCHEMA = ceo_boot_packet.BRIEF_SCHEMA

#: Provenance schema of a CEO-submitted job, owned by
#: :mod:`control_plane.ceo_intent` (``INTENT_SCHEMA``).  The literal is repeated
#: rather than imported: the import fence keeps this module free of the write
#: path, and a projector must not gain a code dependency on the submitter.  The
#: ``ceo-intent:`` command-id prefix is a namespace, NOT proof of origin — only
#: this provenance record identifies a CEO intent.
CEO_INTENT_PROVENANCE_SCHEMA = "mastermind.ceo_intent.v1"

#: Family prefix of that contract.  A provenance record on a VERSIONED SIBLING
#: (``…ceo_intent.v2``) is a document this version cannot read — named in
#: ``degraded`` rather than silently ignored, which is how a schema bump would
#: otherwise turn CEO-submitted jobs into anonymous ones without a sound.
CEO_INTENT_SCHEMA_PREFIX = "mastermind.ceo_intent."

#: Location of the durable runtime database, relative to the repository root.
#: Mirrors ``executive_runtime._DB_RELATIVE_PATH``; a drift test pins them equal.
DB_RELATIVE_PATH = Path("data") / "control_plane" / "executive.sqlite3"

#: Wall-clock budget handed to the boot-packet collector.
DEFAULT_TIMEOUT = ceo_boot_packet.DEFAULT_TIMEOUT

#: The executive seats an item can be addressed to.  ``chairman`` is RESERVED:
#: no Phase 1F-A source emits it, and nothing infers a seat from difficulty,
#: priority, department, cost, or title.
TARGETS = ("chairman", "ceo", "coo")
_TARGET_RANK = {name: index for index, name in enumerate(TARGETS)}

#: Where a job that is NOT attention is counted instead of being dropped.  Every
#: job lands in exactly one of these buckets or in exactly one attention item —
#: that arithmetic is asserted in-module (see ``_reconciliation_gap``).
_SUPPRESSION_BY_STATUS = {
    JobStatus.COMPLETED: "clean_completed",
    JobStatus.QUEUED: "queued",
    JobStatus.RUNNING: "running",
    JobStatus.CHECKPOINTED: "checkpointed",
    JobStatus.CANCELLED: "cancelled",
}
_SUPPRESSION_KEYS = ("clean_completed", "queued", "running", "checkpointed", "cancelled")

#: Kinds whose reason gains the "requeue is refused" clause at the attempt limit.
_REQUEUE_REFUSED_KINDS = frozenset(
    {"job_failed", "job_lost", "job_rate_limited", "escalated_exception"}
)

#: This Mastermind checkout — same idiom as :mod:`control_plane.ceo_boot_packet`.
_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Render width for the text form.
_WIDTH = 78


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

def attention_id(
    *,
    target: str,
    kind: str,
    source: str,
    job_id: str | None,
    workstream: str | None,
    reason: str,
    ordinal: int | None = None,
) -> str:
    """Stable id for one attention item, derived only from what it asserts.

    Content-addressed on purpose: the same durable state produces the same id on
    every machine and in every process, with no counter, uuid, or clock involved.
    ``reason`` participates because a changed reason is a changed claim — an item
    whose sentence moved should not silently inherit the old item's identity.

    ``ordinal`` disambiguates rows that are identical in every projected field.
    Runtime items are already unique by ``job_id`` and pass ``None``, which keeps
    their material exactly the documented six-part join; Agent OS items pass their
    source row index, because two genuinely identical ``needs_ceo`` rows are two
    pending rulings and must not collapse into one item.
    """
    parts = [SCHEMA, target, kind, source, job_id or "", workstream or "", reason]
    if ordinal is not None:
        parts.append(str(ordinal))
    return "eia-" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def _evidence(ref: str, field: str, value: Any) -> dict[str, str]:
    return {"ref": str(ref), "field": str(field), "value": str(value)}


def _item(
    *,
    target: str,
    kind: str,
    source: str,
    job_id: str | None,
    workstream: str | None,
    status: str | None,
    reason: str,
    evidence: Sequence[Mapping[str, str]],
    existing_next_actions: Sequence[str],
    ordinal: int | None = None,
    job_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "attention_id": attention_id(
            target=target,
            kind=kind,
            source=source,
            job_id=job_id,
            workstream=workstream,
            reason=reason,
            ordinal=ordinal,
        ),
        "target": target,
        "kind": kind,
        "source": source,
        "job_id": job_id,
        "workstream": workstream,
        "status": status,
        "reason": reason,
        "evidence": [dict(entry) for entry in evidence],
        "existing_next_actions": [str(entry) for entry in existing_next_actions],
    }
    if job_fields is not None:
        item.update({str(key): value for key, value in job_fields.items()})
    return item


# ---------------------------------------------------------------------------
# the clock seam
# ---------------------------------------------------------------------------

def parse_now(value: str) -> datetime:
    """ISO-8601 (with or without a trailing ``Z``) to an aware UTC datetime.

    Raises ``ValueError`` on anything else.  The inbox refuses an unparseable
    ``now`` rather than falling back to the wall clock: a caller that froze the
    clock and silently got the real one would compare leases against a different
    instant than the document claims, and the disagreement would be invisible.
    """
    text = str(value).strip()
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    parsed = datetime.fromisoformat(candidate)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _parse_stamp(value: str | None) -> datetime | None:
    """Best-effort parse of a runtime ISO stamp; None when it cannot be read."""
    if not value:
        return None
    try:
        return parse_now(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# job classification
# ---------------------------------------------------------------------------

def _payload_or_error(value: Any) -> tuple[JobPayload | None, str | None]:
    """``(payload, None)`` | ``(None, first_line_of_error)`` | ``(None, None)``.

    Validation is delegated to ``JobPayload.from_value`` — the runtime's OWN
    validator, run against exactly what the runtime persisted (``checkpoint_job``,
    ``complete_job``, ``fail_job``, and ``checkpoint_attempt`` all store
    ``JobPayload.from_value(payload).to_dict()`` with no wrapping envelope, so the
    stored object is the payload itself).  Using a second, local notion of
    "well-formed" here would let the inbox call healthy state malformed.
    """
    if value is None:
        return None, None
    try:
        return JobPayload.from_value(value), None
    except (RuntimeProofError, ValueError, TypeError, KeyError) as exc:
        return None, str(exc).splitlines()[0]


def _lost_cause(last_attempt: Attempt | None) -> tuple[str, str | None]:
    """How the runtime came to mark a job LOST, read off the attempt's error.

    Two different operational stories share one status.  ``mark_lost`` writes
    ``verified_process_absent`` after a supervisor PROVED the invocation gone;
    ``reconcile_expired`` writes ``reason: lease_expired`` when a lease ran out
    with nobody heart-beating.  The first says a worker died; the second says
    nobody was watching.  Collapsing them into one sentence would hand the COO the
    wrong repair.
    """
    error = last_attempt.error if last_attempt is not None else None
    if not isinstance(error, Mapping):
        return "the runtime marked it LOST", None
    reason = error.get("reason")
    reason = reason if isinstance(reason, str) and reason else None
    if reason == "lease_expired":
        return (
            "its attempt lease expired without a heartbeat and reconciliation "
            "swept it"
        ), reason
    if error.get("verified_process_absent") is True:
        return "the runtime verified its invocation was absent", reason
    return "the runtime marked it LOST", reason


def _is_independent_approval(
    candidate: Job,
    child: Job,
    attempts_by_job: Mapping[str, Attempt],
) -> bool:
    if candidate.reviews_job_id != child.job_id or candidate.status is not JobStatus.COMPLETED:
        return False
    payload, error = _payload_or_error(candidate.result)
    candidate_attempt = attempts_by_job.get(candidate.job_id)
    child_attempt = attempts_by_job.get(child.job_id)
    return (
        error is None
        and payload is not None
        and payload.verdict == "approve"
        and candidate_attempt is not None
        and child_attempt is not None
        and candidate_attempt.worker_id != child_attempt.worker_id
    )


def classify_job(
    job: Job,
    *,
    last_attempt: Attempt | None = None,
    provenance: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    children: Sequence[Job] = (),
    reviewed_attempt: Attempt | None = None,
    attempts_by_job: Mapping[str, Attempt] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(attention_item, None)`` or ``(None, suppression_bucket)``.

    First match wins and a job yields AT MOST ONE item: an inbox that listed the
    same job three times would be a worse instrument than the ledger it projects.
    Runtime items stay ``target="coo"`` unless the durable ``escalation_target``
    column already declares ``ceo`` or ``chairman`` on a terminal exception —
    never because of department, priority, impact, or provenance labels.

    ``now`` enables the one clock-dependent rule, ``stale_lease``.  Passing None
    disables it rather than inventing an instant: a lease comparison against an
    unstated clock is not evidence.
    """
    used, limit = int(job.attempt_count), int(job.attempt_limit)
    exhausted = used >= limit
    status = job.status
    job_ref = f"job:{job.job_id}"

    result, result_error = _payload_or_error(job.result)
    checkpoint, checkpoint_error = _payload_or_error(job.checkpoint)
    attempts_by_job = attempts_by_job or {}

    job_fields = {
        "parent_job_id": job.parent_job_id,
        "root_job_id": job.root_job_id,
        "depth": job.depth,
        "owner_seat": job.owner_seat,
        "escalation_target": job.escalation_target,
        "business_impact": job.business_impact,
        "review_required": job.review_required,
        "reviews_job_id": job.reviews_job_id,
    }

    kind: str | None = None
    reason = ""
    attempt_evidence = False
    extra: list[dict[str, str]] = []
    target = "coo"

    if status is JobStatus.FAILED:
        kind = "job_failed"
        reason = f"{job.job_id} is FAILED after {used} of {limit} attempt(s)"
        attempt_evidence = True
    elif status is JobStatus.LOST:
        kind = "job_lost"
        cause, cause_code = _lost_cause(last_attempt)
        reason = f"{job.job_id} is LOST after {used} of {limit} attempt(s) — {cause}"
        attempt_evidence = True
        if cause_code is not None and last_attempt is not None:
            extra.append(
                _evidence(
                    f"attempt:{last_attempt.attempt_id}", "error.reason", cause_code
                )
            )
    elif status is JobStatus.RATE_LIMITED:
        kind = "job_rate_limited"
        reason = (
            f"{job.job_id} is RATE_LIMITED after {used} of {limit} attempt(s) — its "
            f"worker quota class was rate limited"
        )
        attempt_evidence = True
    elif status is JobStatus.CANCEL_REQUESTED:
        kind = "cancel_requested"
        reason = (
            f"{job.job_id} is CANCEL_REQUESTED — a cancel was requested and the "
            f"attempt has not acknowledged it"
        )
        attempt_evidence = True
    elif (
        status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CHECKPOINTED)
        and children
        and (
            any(child.status not in {
                JobStatus.RATE_LIMITED,
                JobStatus.FAILED,
                JobStatus.LOST,
                JobStatus.COMPLETED,
                JobStatus.CANCELLED,
            } for child in children)
            or any(
                child.review_required
                and not any(
                    _is_independent_approval(candidate, child, attempts_by_job)
                    for candidate in children
                )
                for child in children
            )
        )
    ):
        kind = "aggregation_blocked"
        living = [
            child.job_id
            for child in children
            if child.status not in {
                JobStatus.RATE_LIMITED,
                JobStatus.FAILED,
                JobStatus.LOST,
                JobStatus.COMPLETED,
                JobStatus.CANCELLED,
            }
        ]
        if living:
            reason = f"{job.job_id} cannot aggregate while child job(s) are living: {', '.join(living)}"
        else:
            reason = (
                f"{job.job_id} cannot aggregate: a review-required child lacks "
                "an independent completed approval"
            )
        attempt_evidence = True
    elif status is JobStatus.QUEUED and exhausted:
        # A wedge, not a queue position: `claim_job` refuses at the attempt limit,
        # and `requeue_job` refuses too, so nothing in the runtime can move this
        # row without an operator.  It would otherwise sit in the QUEUED bucket
        # looking like ordinary pending work forever.
        kind = "attempts_exhausted"
        reason = (
            f"{job.job_id} is QUEUED with {used} of {limit} attempt(s) used — "
            f"permanently unclaimable, because claim refuses at the attempt limit"
        )
        attempt_evidence = True
    elif status is JobStatus.COMPLETED and job.result is None:
        kind = "malformed_result_evidence"
        reason = f"{job.job_id} is COMPLETED but stores no result payload"
        extra.append(_evidence(job_ref, "result", "absent"))
    elif (
        status is JobStatus.COMPLETED
        and job.reviews_job_id
        and last_attempt is not None
        and reviewed_attempt is not None
        and last_attempt.worker_id == reviewed_attempt.worker_id
    ):
        kind = "review_not_independent"
        reason = (
            f"{job.job_id} is a completed review of {job.reviews_job_id}, but the "
            f"review worker {last_attempt.worker_id} also completed the reviewed job"
        )
        extra.append(
            _evidence(
                f"attempt:{last_attempt.attempt_id}",
                "review.status",
                "VOID",
            )
        )
        extra.append(
            _evidence(
                f"job:{job.reviews_job_id}",
                "review_not_independent",
                last_attempt.worker_id,
            )
        )
    elif result_error is not None:
        kind = "malformed_result_evidence"
        reason = (
            f"{job.job_id} stores a result payload the runtime's own validator "
            f"rejects: {result_error}"
        )
        extra.append(_evidence(job_ref, "result", "rejected by JobPayload.from_value"))
    elif checkpoint_error is not None:
        kind = "malformed_result_evidence"
        reason = (
            f"{job.job_id} stores a checkpoint payload the runtime's own validator "
            f"rejects: {checkpoint_error}"
        )
        extra.append(
            _evidence(job_ref, "checkpoint", "rejected by JobPayload.from_value")
        )
    elif status is JobStatus.COMPLETED and result is not None and result.errors:
        kind = "completed_with_errors"
        reason = (
            f"{job.job_id} is COMPLETED and its result records "
            f"{len(result.errors)} error(s)"
        )
        extra.append(_evidence(job_ref, "result.errors", len(result.errors)))
    elif status is JobStatus.COMPLETED and result is not None and result.next_actions:
        kind = "unresolved_next_actions"
        reason = (
            f"{job.job_id} is COMPLETED and its result records "
            f"{len(result.next_actions)} unresolved next action(s)"
        )
        extra.append(
            _evidence(job_ref, "result.next_actions", len(result.next_actions))
        )
    elif (
        status in (JobStatus.RUNNING, JobStatus.CHECKPOINTED)
        and now is not None
        and last_attempt is not None
        and last_attempt.attempt_id == job.current_attempt_id
        and (expiry := _parse_stamp(last_attempt.lease_expires_at)) is not None
        and expiry < now
    ):
        # The canonical supervisor-death signature.  Nothing in the runtime moves a
        # job out of RUNNING on its own — `reconcile_expired` has to be RUN — so an
        # active attempt whose lease ran out sits in the "running" bucket looking
        # like healthy work indefinitely.  This is arithmetic on two canonical
        # timestamps, not an inference about liveness.
        kind = "stale_lease"
        reason = (
            f"{job.job_id} is {status.value} but its attempt's lease expired at "
            f"{last_attempt.lease_expires_at}; reconciliation has not swept it"
        )
        attempt_ref = f"attempt:{last_attempt.attempt_id}"
        extra.append(
            _evidence(attempt_ref, "lease_expires_at", last_attempt.lease_expires_at)
        )
        extra.append(_evidence(attempt_ref, "heartbeat_at", last_attempt.heartbeat_at))
    else:
        # Routine.  Counted, never listed — and never silently dropped: the
        # reconciliation check proves suppression + attention == every job.
        return None, _SUPPRESSION_BY_STATUS.get(status)

    if (
        kind in {"job_failed", "job_lost", "job_rate_limited"}
        and job.escalation_target in {"ceo", "chairman"}
    ):
        # Contract §5: the durable column is a declaration, never a projector
        # verdict.  Department/priority/impact still cannot retarget a seat.
        kind = "escalated_exception"
        target = job.escalation_target
        reason = f"the job DECLARES escalation_target: {job.escalation_target}"
        extra.append(_evidence(job_ref, "escalation_target", job.escalation_target))
        if provenance is not None:
            schema = provenance.get("schema")
            if isinstance(schema, str) and schema:
                extra.append(
                    _evidence(
                        f"event:{job.job_id}:JOB_CREATED",
                        "provenance.schema",
                        schema,
                    )
                )

    if kind in _REQUEUE_REFUSED_KINDS and exhausted:
        reason += f"; attempts exhausted ({used}/{limit}) — requeue is refused"

    evidence = [_evidence(job_ref, "status", status.value)]
    if attempt_evidence:
        evidence.append(_evidence(job_ref, "attempt_count", used))
        evidence.append(_evidence(job_ref, "attempt_limit", limit))
    evidence.extend(extra)
    evidence.append(_evidence(job_ref, "updated_at", job.updated_at))

    if last_attempt is not None:
        attempt_ref = f"attempt:{last_attempt.attempt_id}"
        evidence.append(_evidence(attempt_ref, "status", last_attempt.status.value))
        evidence.append(
            _evidence(
                attempt_ref,
                "exit_code",
                "not recorded" if last_attempt.exit_code is None else last_attempt.exit_code,
            )
        )

    workstream: str | None = None
    if provenance is not None:
        event_ref = f"event:{job.job_id}:JOB_CREATED"
        actor = provenance.get("actor")
        if isinstance(actor, str) and actor:
            evidence.append(_evidence(event_ref, "provenance.actor", actor))
        intent_id = provenance.get("intent_id")
        if isinstance(intent_id, str) and intent_id:
            evidence.append(_evidence(event_ref, "provenance.intent_id", intent_id))
        recorded_ws = provenance.get("workstream")
        if isinstance(recorded_ws, str) and recorded_ws:
            workstream = recorded_ws

    # Verbatim, never authored.  The result outranks the checkpoint: it is the
    # later and more final of the two records the runtime keeps.
    next_actions: list[str] = []
    if result is not None and result.next_actions:
        next_actions = list(result.next_actions)
    elif checkpoint is not None and checkpoint.next_actions:
        next_actions = list(checkpoint.next_actions)

    return (
        _item(
            target=target,
            kind=kind,
            source="runtime",
            job_id=job.job_id,
            workstream=workstream,
            status=status.value,
            reason=reason,
            evidence=evidence,
            existing_next_actions=next_actions,
            job_fields=job_fields,
        ),
        None,
    )


def ceo_intent_provenance(
    runtime: Runtime, job_id: str
) -> tuple[Mapping[str, Any] | None, str | None]:
    """``(provenance, warning)`` for a job's ``JOB_CREATED`` event.

    A CEO-submitted job is recognizable ONLY here.  ``ceo_intent`` records the
    provenance inside the creation event's payload and changes no job column, so
    a job row alone cannot answer the question — and the ``ceo-intent:`` command-id
    prefix is a namespace any caller could type, not proof of origin.

    A record on a versioned SIBLING of the pinned schema returns a warning rather
    than nothing: after a ``ceo_intent`` schema bump, silently dropping the
    evidence would turn every CEO-submitted job anonymous without a sound.
    """
    events = runtime.events.list_events(job_id=job_id)
    for event in events:
        if event.event_type != "JOB_CREATED":
            continue
        payload = event.payload if isinstance(event.payload, Mapping) else {}
        provenance = payload.get("provenance")
        if not isinstance(provenance, Mapping):
            return None, None
        found = provenance.get("schema")
        if found == CEO_INTENT_PROVENANCE_SCHEMA:
            return dict(provenance), None
        if found == "mastermind.ceo_intent.v2":
            if sum(candidate.event_type == "JOB_CREATED" for candidate in events) != 1:
                return None, (
                    f"{job_id} provenance schema {found!r} unrecognized (this build reads "
                    f"{CEO_INTENT_PROVENANCE_SCHEMA!r}); intent evidence not attached"
                )
            intent_id = provenance.get("intent_id")
            actor = provenance.get("actor")
            fingerprint = provenance.get("fingerprint")
            grounding = provenance.get("grounding")
            workstream = provenance.get("workstream")
            command_id = (
                f"ceo-intent:{intent_id}" if isinstance(intent_id, str) else ""
            )
            job = runtime.jobs.get_job(job_id)
            cycle = job.orchestration_provenance if job is not None else None
            valid = (
                event.job_id == job_id
                and event.aggregate_type == "job"
                and event.aggregate_id == job_id
                and event.command_id == command_id
                and isinstance(intent_id, str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", intent_id)
                is not None
                and isinstance(actor, str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}", actor)
                is not None
                and isinstance(fingerprint, str)
                and re.fullmatch(r"[0-9a-f]{64}", fingerprint) is not None
                and isinstance(grounding, Mapping)
                and (
                    "workstream" not in provenance
                    or (
                        isinstance(workstream, str)
                        and re.fullmatch(
                            r"WS:[A-Z0-9][A-Za-z0-9._-]{1,63}", workstream
                        )
                        is not None
                    )
                )
                and job is not None
                and job.job_id == job_id
                and job.parent_job_id is None
                and job.root_job_id == job_id
                and job.orchestration_role == "aggregation"
                and isinstance(job.orchestration_provenance_digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", job.orchestration_provenance_digest)
                is not None
                and isinstance(cycle, Mapping)
                and set(cycle)
                == {
                    "schema_version",
                    "creator",
                    "source_id",
                    "source_digest",
                    "command_id",
                    "job_id",
                    "parent_job_id",
                    "root_job_id",
                    "role",
                }
                and cycle.get("schema_version")
                == "mastermind.executive_orchestration_provenance/v1"
                and cycle.get("creator") == "ceo_intent"
                and cycle.get("source_id") == intent_id
                and cycle.get("source_digest") == fingerprint
                and cycle.get("command_id") == command_id
                and cycle.get("job_id") == job_id
                and cycle.get("parent_job_id") is None
                and cycle.get("root_job_id") == job_id
                and cycle.get("role") == "aggregation"
                and payload.get("orchestration_role") == job.orchestration_role
                and payload.get("orchestration_provenance_digest")
                == job.orchestration_provenance_digest
            )
            if valid:
                projected = {
                    key: provenance[key]
                    for key in (
                        "schema",
                        "intent_id",
                        "actor",
                        "fingerprint",
                        "grounding",
                        "workstream",
                    )
                    if key in provenance
                }
                return projected, None
        if isinstance(found, str) and found.startswith(CEO_INTENT_SCHEMA_PREFIX):
            return None, (
                f"{job_id} provenance schema {found!r} unrecognized (this build reads "
                f"{CEO_INTENT_PROVENANCE_SCHEMA!r}); intent evidence not attached"
            )
        return None, None
    return None, None


# ---------------------------------------------------------------------------
# runtime projection
# ---------------------------------------------------------------------------

def _first_line(exc: BaseException) -> str:
    return str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__


def _counts(values: Sequence[Any], enum_type: type) -> dict[str, Any]:
    """``{"total": n, "by_status": {every member: count}}`` — zeros included.

    Every enum member is present whether or not it occurs: a status that
    disappears from the map is indistinguishable from a status that dropped to
    zero, and an executive surface must never make "none of these" look like
    "this state no longer exists".
    """
    by_status = {member.value: 0 for member in enum_type}
    for value in values:
        key = getattr(value.status, "value", str(value.status))
        by_status[key] = by_status.get(key, 0) + 1
    return {"total": len(values), "by_status": by_status}


class _RuntimeProjection:
    """Everything the inbox needs from the runtime, plus what it could not read."""

    def __init__(self) -> None:
        self.attention: list[dict[str, Any]] = []
        self.counts: dict[str, Any] | None = None
        self.suppressed: dict[str, int] | None = None
        self.degraded: list[str] = []


def _last_attempt_by_job(attempts: Sequence[Attempt]) -> dict[str, Attempt]:
    latest: dict[str, Attempt] = {}
    for attempt in attempts:
        current = latest.get(attempt.job_id)
        if current is None or attempt.attempt_number >= current.attempt_number:
            latest[attempt.job_id] = attempt
    return latest


def _reconciliation_gap(
    suppressed: Mapping[str, int], attention_count: int, total: int
) -> str | None:
    """Audit arithmetic: every job is either suppressed once or listed once."""
    accounted = sum(suppressed.values()) + attention_count
    if accounted == total:
        return None
    return (
        f"internal reconciliation mismatch: {sum(suppressed.values())} suppressed + "
        f"{attention_count} attention item(s) = {accounted}, but the runtime holds "
        f"{total} job(s)"
    )


def project_runtime(root: Path, now: datetime | None = None) -> _RuntimeProjection:
    """Read the durable runtime and project it; never raises, never writes."""
    projection = _RuntimeProjection()
    db_path = root / DB_RELATIVE_PATH

    # BEFORE constructing anything: a default `RuntimeStore` would CREATE the
    # directory, the database, and the schema.  A projector that did that would
    # manufacture an empty runtime and then report it as a quiet company.
    if not db_path.is_file():
        projection.degraded.append(
            f"executive runtime database missing at {db_path}; runtime not projected"
        )
        return projection

    try:
        # `create=False`: read-only, no migration, no chmod, no journal-mode write,
        # and `transaction()` refuses.  Existence alone was NOT enough — a 0-byte
        # husk, a truncated restore, or a foreign SQLite file passes `is_file()`
        # and would otherwise be handed the whole Executive OS schema by its own
        # reader, then reported as a company with nothing running.
        runtime = Runtime.at(root, create=False)
    except (RuntimeProofError, OSError, ValueError, KeyError) as exc:
        projection.degraded.append(f"{_first_line(exc)}; runtime not projected")
        return projection

    jobs: list[Job] | None = None
    try:
        jobs = runtime.jobs.list_jobs()
    except (RuntimeProofError, ValueError, KeyError) as exc:
        # One undecodable row hides this registry's whole surface.  That is the
        # documented, VISIBLE degradation: the alternative — raw SQL that skipped
        # the runtime's own decoding — was rejected, because a projector with its
        # own row reader disagrees with the authority the first time either moves.
        projection.degraded.append(f"runtime jobs unreadable: {_first_line(exc)}")

    attempts: list[Attempt] | None = None
    try:
        attempts = runtime.attempts.list_attempts()
    except (RuntimeProofError, ValueError, KeyError) as exc:
        projection.degraded.append(f"runtime attempts unreadable: {_first_line(exc)}")

    workers: list[Any] | None = None
    try:
        workers = runtime.workers.list_workers()
    except (RuntimeProofError, ValueError, KeyError) as exc:
        projection.degraded.append(f"runtime workers unreadable: {_first_line(exc)}")

    projection.counts = {
        "jobs": _counts(jobs, JobStatus) if jobs is not None else None,
        "attempts": _counts(attempts, AttemptStatus) if attempts is not None else None,
        "workers": _counts(workers, WorkerStatus) if workers is not None else None,
    }

    if jobs is None:
        return projection

    latest = _last_attempt_by_job(attempts or [])
    children_by_parent: dict[str, list[Job]] = {}
    for candidate in jobs:
        if candidate.parent_job_id:
            children_by_parent.setdefault(candidate.parent_job_id, []).append(candidate)
    suppressed = {key: 0 for key in _SUPPRESSION_KEYS}
    events_closed = False

    for job in jobs:
        last_attempt = latest.get(job.job_id)
        item, bucket = classify_job(
            job,
            last_attempt=last_attempt,
            now=now,
            children=children_by_parent.get(job.job_id, ()),
            reviewed_attempt=latest.get(job.reviews_job_id) if job.reviews_job_id else None,
            attempts_by_job=latest,
        )
        if item is None:
            if bucket is not None:
                suppressed[bucket] = suppressed.get(bucket, 0) + 1
            continue

        # Events are read ONLY for jobs already selected as attention — the
        # bounded read.  A per-job event scan across a whole runtime would grow
        # with the ledger; the attention list does not.
        if not events_closed:
            try:
                provenance, warning = ceo_intent_provenance(runtime, job.job_id)
            except (RuntimeProofError, ValueError, KeyError) as exc:
                projection.degraded.append(
                    f"runtime events unreadable: {_first_line(exc)}; CEO-intent "
                    f"provenance not projected"
                )
                events_closed = True
            else:
                if warning is not None:
                    projection.degraded.append(warning)
                if provenance is not None:
                    # Re-classify with the provenance in hand: it contributes the
                    # workstream and two evidence refs, and the identity hash
                    # covers both.  Classification is pure, so this cannot diverge
                    # from the decision just made.
                    item = classify_job(
                        job,
                        last_attempt=last_attempt,
                        provenance=provenance,
                        now=now,
                        children=children_by_parent.get(job.job_id, ()),
                        reviewed_attempt=latest.get(job.reviews_job_id) if job.reviews_job_id else None,
                        attempts_by_job=latest,
                    )[0]
        if item is not None:
            projection.attention.append(item)

    projection.suppressed = suppressed
    gap = _reconciliation_gap(
        suppressed, len(projection.attention), projection.counts["jobs"]["total"]
    )
    if gap is not None:
        projection.degraded.append(gap)
    return projection


# ---------------------------------------------------------------------------
# Agent OS / boot-packet projection
# ---------------------------------------------------------------------------

def project_needs_ceo(
    packet: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """CEO attention from ``brief.needs_ceo`` — the only 1F-A ``ceo`` source.

    Returns ``(items, degraded)``.  The question travels VERBATIM: a pending
    ruling is the CEO's own words in the Agent OS record, and re-phrasing it here
    would put an unreviewed sentence in front of a decision.
    """
    items: list[dict[str, Any]] = []
    degraded: list[str] = []

    brief = packet.get("brief")
    if brief is None:
        # `build_packet` emits `brief: null` whenever the Macro checkout does not
        # resolve or the agentos brief fails.  Returning quietly here would render
        # a healthy-looking "0 CEO" out of a read that never happened — the exact
        # shape of a silent lane.
        return items, [
            "boot packet carries no Agent OS brief; CEO attention not projected"
        ]
    if not isinstance(brief, Mapping):
        return items, [
            f"boot packet brief is a {type(brief).__name__}, not an object; "
            f"CEO attention not projected"
        ]

    found = brief.get("schema")
    if found != BRIEF_SCHEMA:
        # Agent OS owns this contract.  A foreign brief may put `needs_ceo` to a
        # different use entirely, so it is named and left unread.
        return items, [
            f"boot packet brief schema is {found!r}, expected {BRIEF_SCHEMA!r} "
            f"— not read; CEO attention not projected"
        ]

    rows = brief.get("needs_ceo") or []
    if not isinstance(rows, (list, tuple)):
        return items, [
            f"boot packet needs_ceo is a {type(rows).__name__}, not a list; "
            f"CEO attention not projected"
        ]

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            # Never silently dropped: an unreadable pending ruling is exactly the
            # thing that must not vanish from an executive surface.
            degraded.append(
                f"boot packet needs_ceo[{index}] is not an object "
                f"({type(row).__name__}); no CEO attention projected from it"
            )
            continue
        raw_ws = row.get("workstream")
        workstream = str(raw_ws) if isinstance(raw_ws, str) and raw_ws else None
        raw_question = row.get("question")
        reason = (
            str(raw_question)
            if isinstance(raw_question, str) and raw_question
            else "question not recorded"
        )
        evidence = [
            _evidence("agentos:needs_ceo", "workstream", workstream or "not recorded"),
            _evidence("boot_packet", "schema", BOOT_PACKET_SCHEMA),
        ]
        items.append(
            _item(
                target="ceo",
                kind="ceo_decision_pending",
                source="agent_os",
                job_id=None,
                workstream=workstream,
                status=None,
                reason=reason,
                evidence=evidence,
                # The row may carry a `recommendation`; it is NOT copied here.
                # `existing_next_actions` is the runtime's own stored next_actions
                # field, and re-rendering an Agent OS recommendation as an
                # executive next action would be the inbox authoring advice.
                existing_next_actions=[],
                # Two byte-identical pending rulings are two rulings.  Without the
                # source row ordinal their content-addressed ids would collide and
                # the second would silently disappear from the CEO's lane.
                ordinal=index,
            )
        )
    return items, degraded


def load_boot_packet_file(path: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a saved boot packet from disk.  ``(packet, None)`` or ``(None, why)``."""
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"boot packet file unreadable at {target}: {_first_line(exc)}"
    try:
        packet = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return None, f"boot packet file at {target} is not JSON: {_first_line(exc)}"
    if not isinstance(packet, dict):
        return None, (
            f"boot packet file at {target} is a {type(packet).__name__}, not an object"
        )
    return packet, None


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def _sort_key(item: Mapping[str, Any]) -> tuple[int, str, str, str]:
    return (
        _TARGET_RANK.get(str(item.get("target")), len(TARGETS)),
        str(item.get("source") or ""),
        str(item.get("job_id") or item.get("workstream") or ""),
        str(item.get("kind") or ""),
    )


def build_inbox(
    *,
    repo_root: Path | str | None = None,
    boot_packet: Mapping[str, Any] | None = None,
    include_boot_packet: bool = True,
    boot_packet_file: str | Path | None = None,
    macro_root_flag: str | None = None,
    environ: Mapping[str, str] | None = None,
    now: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Assemble the ``mastermind.executive_inbox.v1`` document.

    Never raises on a degraded environment: a missing runtime database, an
    unreadable registry, an uncollectable boot packet, or a boot packet on an
    unknown schema each land as a string in ``degraded`` and the document is still
    returned whole.

    The ONE exception is ``now``: an unparseable value raises ``ValueError``,
    because a frozen clock that silently became the wall clock would date the
    document one way and compare leases another.  The CLI rejects it at argument
    parsing, before the always-exit-0 contract begins.

    The boot packet is resolved by a fixed ladder — an injected ``boot_packet``
    (tests, offline), then ``boot_packet_file``, then collection via
    :func:`control_plane.ceo_boot_packet.build_packet`, then nothing.
    """
    # Resolved so `grounding.mastermind.root` names the same path the store does.
    root = Path(repo_root).resolve() if repo_root is not None else _REPO_ROOT
    environ = os.environ if environ is None else environ
    degraded: list[str] = []

    # The only clock read, and only when the caller did not state one.
    if now is None:
        now_dt = datetime.now(timezone.utc).replace(microsecond=0)
        generated_at = now_dt.isoformat().replace("+00:00", "Z")
    else:
        now_dt = parse_now(now)
        generated_at = now

    packet: Mapping[str, Any] | None = None
    if boot_packet is not None:
        packet = boot_packet
    elif boot_packet_file is not None:
        packet, file_error = load_boot_packet_file(boot_packet_file)
        if file_error is not None:
            degraded.append(file_error)
    elif include_boot_packet:
        try:
            packet = ceo_boot_packet.build_packet(
                repo_root=root,
                macro_root_flag=macro_root_flag,
                environ=environ,
                now=now,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 — fail open by contract
            # The collector is fail-open by its own contract, but it shells out to
            # another repository's CLI and reads YAML on the way.  An inbox that
            # died because orientation was unavailable would defeat its purpose.
            degraded.append(
                f"boot packet collection failed: {exc.__class__.__name__}: "
                f"{_first_line(exc)}"
            )
    else:
        degraded.append(
            "boot packet not collected (--no-boot-packet); CEO/Agent OS attention "
            "not projected"
        )

    macro_root: str | None = None
    macro_sha: str | None = None
    packet_schema: str | None = None
    ceo_items: list[dict[str, Any]] = []

    if packet is not None:
        # Bubbled with a prefix so a boot-packet problem is never mistaken for an
        # inbox problem, and never hidden either.  Bubbling happens BEFORE the
        # schema check: whatever a foreign document is, its self-reported failures
        # are still worth showing.
        packet_degraded = packet.get("degraded")
        if isinstance(packet_degraded, (list, tuple)):
            degraded.extend(f"boot_packet: {entry}" for entry in packet_degraded)
        elif packet_degraded is not None:
            # A string here would iterate character by character, and dropping it
            # would discard the packet's own account of what it could not read.
            degraded.append(
                f"boot packet degraded field is a {type(packet_degraded).__name__}, "
                f"not a list; its warnings were not bubbled"
            )
        found = packet.get("schema")
        if found != BOOT_PACKET_SCHEMA:
            # Never silently map an unknown contract: the grounding stays null and
            # no attention is projected from a document this version cannot read.
            degraded.append(
                f"boot packet schema is {found!r}, expected {BOOT_PACKET_SCHEMA!r} "
                f"— not read; CEO/Agent OS attention not projected"
            )
        else:
            packet_schema = BOOT_PACKET_SCHEMA
            macro = packet.get("macro")
            if isinstance(macro, Mapping):
                raw_root, raw_sha = macro.get("root"), macro.get("sha")
                macro_root = str(raw_root) if isinstance(raw_root, str) else None
                macro_sha = str(raw_sha) if isinstance(raw_sha, str) else None
            ceo_items, packet_degraded = project_needs_ceo(packet)
            degraded.extend(packet_degraded)

    runtime = project_runtime(root, now_dt)
    degraded.extend(runtime.degraded)

    attention = sorted(ceo_items + runtime.attention, key=_sort_key)

    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "grounding": {
            "mastermind": {
                "root": os.fspath(root),
                "sha": ceo_boot_packet.git_sha(root),
                "branch": ceo_boot_packet.git_branch(root),
            },
            "macro": {"root": macro_root, "sha": macro_sha},
            "boot_packet_schema": packet_schema,
            "runtime_db": {
                "path": os.fspath(root / DB_RELATIVE_PATH),
                "present": (root / DB_RELATIVE_PATH).is_file(),
            },
        },
        "attention": attention,
        "runtime_counts": runtime.counts,
        "suppressed": runtime.suppressed,
        "degraded": degraded,
    }


# ---------------------------------------------------------------------------
# text rendering
# ---------------------------------------------------------------------------

def _wrap(text: str, width: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "?"


def _evidence_line(item: Mapping[str, Any]) -> str:
    cells: list[str] = []
    for entry in item.get("evidence") or []:
        if not isinstance(entry, Mapping):
            continue
        ref, field = str(entry.get("ref", "")), str(entry.get("field", ""))
        label = f"attempt.{field}" if ref.startswith("attempt:") else field
        cells.append(f"{label}={entry.get('value')}")
    return " · ".join(cells)


def _fleet_line(counts: Any) -> str:
    """Totals plus the WORKER status breakdown.

    The worker roll-call is on the default surface on purpose: a fleet that is
    entirely ERROR or OFFLINE produces no failed jobs — nothing can fail if
    nothing can be claimed — so a dead fleet is invisible in the attention list
    and would otherwise read as a quiet, healthy company.
    """
    if not isinstance(counts, Mapping):
        return "runtime: not projected"

    def _total(section: str) -> str:
        value = counts.get(section)
        return str(value.get("total")) if isinstance(value, Mapping) else "?"

    workers = counts.get("workers")
    breakdown = ""
    if isinstance(workers, Mapping):
        by_status = workers.get("by_status") or {}
        # Declaration order, not dict order — deterministic and readable.
        shown = [
            f"{by_status[member.value]} {member.value}"
            for member in WorkerStatus
            if by_status.get(member.value)
        ]
        if shown:
            breakdown = f" ({' · '.join(shown)})"
    return (
        f"runtime: {_total('jobs')} jobs · {_total('attempts')} attempts · "
        f"{_total('workers')} workers{breakdown}"
    )


def render_inbox(inbox: Mapping[str, Any]) -> str:
    """Human-readable form of an inbox.

    DEGRADED is never suppressed and the counts line is always present: an
    executive surface that quietly omitted what it could not read would be worse
    than no surface at all.
    """
    grounding = inbox.get("grounding") or {}
    mastermind = grounding.get("mastermind") or {}
    macro = grounding.get("macro") or {}
    runtime_db = grounding.get("runtime_db") or {}
    attention = list(inbox.get("attention") or [])

    macro_cell = _short(macro.get("sha")) if macro.get("root") else "UNRESOLVED"
    db_cell = "present" if runtime_db.get("present") else "MISSING"

    out: list[str] = [
        f"EXECUTIVE INBOX — {inbox.get('generated_at', '?')}",
        f"mastermind {_short(mastermind.get('sha'))} "
        f"({mastermind.get('branch') or '?'}) · macro {macro_cell} · "
        f"runtime db {db_cell}",
        f"schema {inbox.get('schema', '?')}",
    ]

    by_target = {name: 0 for name in TARGETS}
    for item in attention:
        key = str(item.get("target"))
        by_target[key] = by_target.get(key, 0) + 1
    # Iterate observed targets UNION the vocabulary, so a target this build does
    # not know about is still counted and still printed rather than vanishing.
    labels = {"ceo": "CEO", "coo": "COO"}
    out.append(
        " · ".join(
            f"{by_target[name]} {labels.get(name, name)}"
            for name in list(TARGETS) + [n for n in sorted(by_target) if n not in TARGETS]
        )
    )
    out.append(_fleet_line(inbox.get("runtime_counts")))

    suppressed = inbox.get("suppressed")
    if not isinstance(suppressed, Mapping):
        out.append("suppressed: runtime not projected")
    else:
        running = int(suppressed.get("running", 0)) + int(
            suppressed.get("checkpointed", 0)
        )
        out.append(
            f"suppressed: {suppressed.get('clean_completed', 0)} clean completions · "
            f"{suppressed.get('queued', 0)} queued · {running} running/checkpointed · "
            f"{suppressed.get('cancelled', 0)} cancelled"
        )
    out.append("")

    degraded = list(inbox.get("degraded") or [])
    if degraded:
        out.append(f"⚠ DEGRADED ({len(degraded)})")
        for entry in degraded:
            for index, segment in enumerate(_wrap(entry, _WIDTH - 4)):
                out.append(("  - " if index == 0 else "    ") + segment)
        out.append("")

    for target in list(TARGETS) + [
        name for name in sorted(by_target) if name not in TARGETS
    ]:
        rows = [item for item in attention if item.get("target") == target]
        if not rows:
            continue
        out.append(target.upper())
        for item in rows:
            subject = str(item.get("job_id") or item.get("workstream") or "—")
            reason = str(item.get("reason", ""))
            # The JSON `reason` is a standalone sentence and usually opens with the
            # subject; don't print the subject twice in the same line.
            head = (
                f"[{item.get('kind', '?')}] {reason}"
                if reason.startswith(subject)
                else f"[{item.get('kind', '?')}] {subject} — {reason}"
            )
            for index, segment in enumerate(_wrap(head, _WIDTH - 4)):
                out.append(("  " if index == 0 else "      ") + segment)
            out.append(f"      ({item.get('attention_id', '?')})")
            evidence = _evidence_line(item)
            if evidence:
                for index, segment in enumerate(
                    _wrap(f"evidence: {evidence}", _WIDTH - 8)
                ):
                    out.append(("      " if index == 0 else "        ") + segment)
            for action in item.get("existing_next_actions") or []:
                for index, segment in enumerate(
                    _wrap(f"next actions on file: {action}", _WIDTH - 8)
                ):
                    out.append(("      " if index == 0 else "        ") + segment)
        out.append("")

    if not attention:
        out.append("no attention items — see DEGRADED for anything not read")
        out.append("")

    return "\n".join(out).rstrip("\n") + "\n"


__all__ = [
    "BOOT_PACKET_SCHEMA",
    "BRIEF_SCHEMA",
    "CEO_INTENT_PROVENANCE_SCHEMA",
    "CEO_INTENT_SCHEMA_PREFIX",
    "DB_RELATIVE_PATH",
    "DEFAULT_TIMEOUT",
    "SCHEMA",
    "TARGETS",
    "attention_id",
    "build_inbox",
    "ceo_intent_provenance",
    "classify_job",
    "load_boot_packet_file",
    "parse_now",
    "project_needs_ceo",
    "project_runtime",
    "render_inbox",
]
