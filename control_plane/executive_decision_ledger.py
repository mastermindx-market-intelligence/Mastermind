"""WO-17: the shared decision ledger and the correlated Hermes JSONL.

The canonical admitted decision/assignment is the ``ExecutionBinding.v1`` the
sole placement authority (``broker.claim_job``, WO-14) attached to the
Attempt's ``JOB_CLAIMED`` record.  This module projects that record into the
one shared decision/event schema (WO-02 ``DecisionEvent``), attaches it to the
existing Executive Job/Attempt records by id, and defines how the Hermes
``mmx-router`` JSONL line is correlated to it.

The JSONL is NOT a second placement ledger and NOT a retry owner.  It stays
what it is today — an explanation/export stream — and gains only correlation
references; placement truth lives exclusively in the Executive records.

Correlation contract (Rev 4 §S3.E l.295, §S5 l.331)
---------------------------------------------------

A ``mmx-router`` JSONL line is correlated to exactly one Executive decision
record when every key in :data:`JSONL_CORRELATION_KEYS` matches the Executive
record's value for that key:

=========================  ==============================================  ====
JSONL key                  Executive field                                 set by
=========================  ==============================================  ====
``root_run_ref``           binding ``root_run_ref``                        router
``immediate_parent_run_ref`` binding ``immediate_parent_run_ref``          router
``logical_child_key``      binding ``logical_child_key``                   router
``preview_id``             admitted request's ``preview_id`` (may be       router
                           empty — a preview is advisory and optional)
``decision_id``            :func:`decision_id_for_binding` of the          BOTH*
                           Executive record — minted deterministically,
                           so the router copies, never re-derives
``attempt_ref``            binding ``attempt_ref`` (Executive Attempt id)  Executive→router
``fence_counter``          binding ``fence_counter``                       Executive→router
``request_digest``         binding ``request_digest`` (sha256, 64-hex)     router
=========================  ==============================================  ====

\* the router learns ``decision_id``/``attempt_ref``/``fence_counter`` from the
admission/binding response (WO-12/WO-13) and echoes them on the line; it never
mints them.  Legacy lines without the correlation keys are uncorrelated by
definition — they stay advisory explanations, never placement evidence.
Router base fields map as: ``requested``/``served`` option names →
``requested_complexity``/``effective_complexity`` (canonical long names),
``task_class`` shorthand, ``downgraded``, ``note`` → ``reason``, ``witness`` →
``witness``, ``route`` → provider/model (placement is never carried by the
JSONL).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from control_plane.child_execution_contracts import (
    DECISION_EVENT_SCHEMA, DecisionEvent, ExecutionBinding, RoutingDecision,
)

__all__ = [
    "DECISION_LEDGER_AGGREGATE",
    "DECISION_LEDGER_EVENT",
    "DECISION_LEDGER_OWNER",
    "JSONL_CORRELATION_KEYS",
    "decision_id_for_binding",
    "decision_event_from_claim",
    "record_claim_decision",
    "decision_for_attempt",
    "decisions_for_job",
    "hermes_jsonl_line",
    "correlation_report",
]

#: WO-14 pattern: the decision rides its own aggregate so Job event-chain
#: invariants are untouched; it is attached to the Job/Attempt records by id.
DECISION_LEDGER_AGGREGATE = "job_execution_decision"
DECISION_LEDGER_EVENT = "JOB_EXECUTION_DECISION"
DECISION_LEDGER_OWNER = "executive-decision-ledger"

#: The correlation keys a mmx-router JSONL line must carry to be correlated.
JSONL_CORRELATION_KEYS = (
    "root_run_ref",
    "immediate_parent_run_ref",
    "logical_child_key",
    "preview_id",
    "decision_id",
    "attempt_ref",
    "fence_counter",
    "request_digest",
)

#: The mmx-router line's own (pre-WO-17) base fields, kept verbatim.
JSONL_BASE_KEYS = ("t", "requested", "served", "task_class", "witness", "witness_problem",
                   "downgraded", "note", "capacity", "route", "profile")


def decision_id_for_binding(binding: ExecutionBinding) -> str:
    """The canonical decision id of an admitted assignment.

    Deterministic over the binding's placement identity + admitted digest +
    fence, so the Executive record, the Hermes router and any replay agree
    without a second minting authority.  Distinct by construction from
    ``preview_id`` and ``attempt_ref`` (they are different identity spaces).
    """
    identity = {
        "schema": DECISION_EVENT_SCHEMA,
        "root_run_ref": binding.root_run_ref,
        "immediate_parent_run_ref": binding.immediate_parent_run_ref,
        "logical_child_key": binding.logical_child_key,
        "request_digest": binding.request_digest,
        "effective_complexity": binding.effective_complexity,
        "job_ref": binding.job_ref,
        "attempt_ref": binding.attempt_ref,
        "assignment_generation": binding.assignment_generation,
        "fence_counter": binding.fence_counter,
        "decision_ref": binding.decision_ref,
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "mmx-decision-" + hashlib.sha256(payload).hexdigest()[:32]


def decision_event_from_claim(
    *, job_id: str, claim_payload: Mapping[str, Any], occurred_at: str = "",
    preview_id: str = "", routing_decision: RoutingDecision | None = None,
    spec: Mapping[str, Any] | None = None,
) -> DecisionEvent:
    """Project the JOB_CLAIMED record's binding into the shared decision schema.

    ``claim_payload`` is the payload of the Attempt's existing ``JOB_CLAIMED``
    event; its ``execution_binding`` is the canonical assignment.  ``spec`` is
    the Job's ``child_placement`` constraints (the claim owner has them in the
    same transaction) and supplies the admitted request's ``preview_id`` and
    ``requested_complexity``.  No binding, no decision record — a legacy claim
    stays legacy.
    """
    raw = claim_payload.get("execution_binding")
    if not isinstance(raw, Mapping):
        raise ValueError(f"job {job_id} claim carries no ExecutionBinding")
    binding = ExecutionBinding.from_dict(raw)
    request = claim_payload.get("child_execution_request")
    if not isinstance(request, Mapping) and isinstance(spec, Mapping):
        request = spec.get("child_execution_request")
    if preview_id == "" and isinstance(request, Mapping):
        preview_id = str(request.get("preview_id") or "")
    requested_complexity = ""
    if isinstance(request, Mapping):
        requested_complexity = str(request.get("requested_complexity") or "")
    return DecisionEvent(
        event_id=decision_id_for_binding(binding),
        event_kind="binding_issued",
        occurred_at=occurred_at,
        root_run_ref=binding.root_run_ref,
        immediate_parent_run_ref=binding.immediate_parent_run_ref,
        logical_child_key=binding.logical_child_key,
        preview_id=preview_id,
        decision_id=decision_id_for_binding(binding),
        attempt_ref=binding.attempt_ref,
        fence_counter=binding.fence_counter,
        request_digest=binding.request_digest,
        task_kind=binding.task_kind,
        requested_complexity=requested_complexity,
        effective_complexity=binding.effective_complexity,
        downgraded=False,
        witness_problem=None,
        reason="",
        witness="",
        policy_revision=binding.policy_revision,
        routing_decision=routing_decision,
    )


def record_claim_decision(
    store: Any, connection: Any, *, job_id: str, claim_payload: Mapping[str, Any],
    timestamp: int | None = None, spec: Mapping[str, Any] | None = None,
) -> DecisionEvent:
    """Attach the canonical decision record to the Job/Attempt records.

    Called by the claim owner inside its transaction (WO-13/WO-14/WO-18
    integration); idempotent by ``decision_id`` — a replay appends nothing.
    ``spec`` is the Job's ``child_placement`` constraints.  The record lives on
    the :data:`DECISION_LEDGER_AGGREGATE` aggregate (aggregate_id = job_id,
    with job_id/attempt_id columns set) so existing Job/Attempt event-chain
    invariants are untouched.
    """
    event = decision_event_from_claim(job_id=str(job_id), claim_payload=claim_payload,
                                      spec=spec)
    existing = connection.execute(
        "SELECT payload_json FROM events WHERE aggregate_type=? AND aggregate_id=? "
        "AND event_type=? ORDER BY sequence DESC",
        (DECISION_LEDGER_AGGREGATE, str(job_id), DECISION_LEDGER_EVENT),
    ).fetchall()
    for row in existing:
        prior = json.loads(row[0])
        if prior.get("decision_id") == event.decision_id:
            if prior != event.to_dict():
                raise ValueError(
                    f"decision {event.decision_id} replay differs from its record")
            return event
    store.append_event(
        connection, aggregate_type=DECISION_LEDGER_AGGREGATE,
        aggregate_id=str(job_id), event_type=DECISION_LEDGER_EVENT,
        actor=DECISION_LEDGER_OWNER, job_id=str(job_id),
        attempt_id=event.attempt_ref or None,
        payload=event.to_dict(),
        command_id=f"decision-ledger:{event.decision_id}",
        timestamp_ms=timestamp,
    )
    return event


def decision_for_attempt(store: Any, attempt_id: str) -> DecisionEvent | None:
    """The canonical decision record attached to this Attempt, if any."""
    with store.read() as connection:
        row = connection.execute(
            "SELECT payload_json FROM events WHERE aggregate_type=? AND event_type=? "
            "AND attempt_id=? ORDER BY sequence DESC LIMIT 1",
            (DECISION_LEDGER_AGGREGATE, DECISION_LEDGER_EVENT, str(attempt_id)),
        ).fetchone()
    return DecisionEvent.from_dict(json.loads(row[0])) if row is not None else None


def decisions_for_job(store: Any, job_id: str) -> tuple[DecisionEvent, ...]:
    """Every canonical decision record attached to this Job, in order."""
    with store.read() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM events WHERE aggregate_type=? AND aggregate_id=? "
            "AND event_type=? ORDER BY sequence",
            (DECISION_LEDGER_AGGREGATE, str(job_id), DECISION_LEDGER_EVENT),
        ).fetchall()
    return tuple(DecisionEvent.from_dict(json.loads(row[0])) for row in rows)


# --- the correlated Hermes mmx-router JSONL line --------------------------------

def hermes_jsonl_line(
    event: DecisionEvent, *, t: str = "", requested: str = "", served: str = "",
    task_class: str = "", witness: str | None = None, witness_problem: str | None = None,
    downgraded: bool = False, note: str | None = None, capacity: str = "",
    route: str = "", profile: str = "",
) -> str:
    """One mmx-router JSONL line correlated to ``event``.

    The router's own base fields are kept verbatim (legacy consumers unaffected);
    the correlation keys are the ONLY structural addition.  The line carries no
    placement authority: it explains, it never places.
    """
    line: dict[str, Any] = {
        "t": t, "requested": requested, "served": served, "task_class": task_class,
        "witness": witness, "witness_problem": witness_problem,
        "downgraded": downgraded, "note": note, "capacity": capacity,
        "route": route, "profile": profile,
    }
    line.update(event.to_dict())
    return json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def correlation_report(executive: DecisionEvent, jsonl_line: str | Mapping[str, Any]
                       ) -> dict[str, dict[str, Any]]:
    """Per-key correlation verdict between the Executive record and a JSONL line.

    Returns ``{key: {"executive": …, "jsonl": …, "match": bool}}`` for every
    :data:`JSONL_CORRELATION_KEYS` entry.  A line missing a key is
    ``{"jsonl": None, "match": False}`` — uncorrelated, never placement truth.
    """
    if isinstance(jsonl_line, str):
        line = json.loads(jsonl_line)
    else:
        line = dict(jsonl_line)
    report: dict[str, dict[str, Any]] = {}
    for key in JSONL_CORRELATION_KEYS:
        left = getattr(executive, key)
        right = line.get(key)
        report[key] = {
            "executive": left,
            "jsonl": right,
            "match": left == right,
        }
    return report
