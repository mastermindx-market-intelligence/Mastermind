"""control_plane.fabric_job_view — versioned truthful Fabric projections.

One **read-only** projector family renders a single Executive Runtime root —
parent Job → child Jobs and Attempts → review → repair → result state — using
ONLY existing Executive read paths and explicit unknowns wherever the system
has no producer.

``mastermind.fabric_job_view.v1`` remains the historical contract.
``mastermind.fabric_job_view.v2`` separates execution completion from product
acceptance: Runtime ``COMPLETED`` stays ``COMPLETED`` and acceptance is
``NOT_PROJECTED`` until a real acceptance owner exists. The v2 root-list
projection also treats ``ceo_submit_armed=false`` only as new-submission
unavailability; it never claims that an earlier admitted Job cannot exist.

The projection never fabricates production state, product acceptance, or an
empty company when an input is missing. Fixture data remains fixture data.

It is not a write path, not an arm, not an install, and not an edit to the
Control Room document (that document's key set is closed and asserted at
``control_plane/chairman_control_room.py:1190``, under another lane's
custody — this is a NEW projector that consumes the same reads).

Shape (mirrors the Control Room's own split, ``chairman_control_room.py:11``)
--------------------------------------------------------------------------
* :func:`compose_fabric_view` — PURE.  No I/O, no clock beyond the optional
  ``generated_at``.  Every document key is derived from its arguments, which
  is what makes D5 (fixture data can never wear production labels) testable.
* :func:`read_fabric_view` — the thin gather layer.  It opens the runtime
  READ-ONLY, reads, and hands raw values to the compositor.
* :func:`list_roots` — a bounded enumerator (seat ruling R2) so an operator
  can find a root id without a fleet roll-up.
* :func:`describe_capability` — the A16 capability object with
  ``installed: false`` and **no runtime access at all** (``--describe``).

Historical v1 reads
-------------------
``executive_runtime.Runtime.at(runtime_root, create=False)``; ``runtime.jobs.
get_job(job_id)``; ``runtime.jobs.list_jobs()``; ``runtime.attempts.
list_attempts(job_id)``; ``runtime.events.list_events(job_id=…)``.  No MCP
server is started, no socket is opened, no ``launchctl``, no network.

The v2 gather path instead uses only the fixed Runtime owner discovery/root
snapshot methods and one validated command-id Event point read per eligible
Job. Its acquisition receipt separates truncation, provenance completeness and
currentness. A digest alone never qualifies currentness. Legacy provenance with
no durable command join stays PARTIAL without acquiring Event history.

DEVIATION 1 — a sixth read function, adjudicated (ORCH-WB1, binding).
    :func:`read_fabric_view` also calls ``control_plane.executive_inbox.
    ceo_intent_provenance(runtime, job_id)``.  That function is a *pure
    composition* of two already-allowed reads (``runtime.events.
    list_events(job_id=…)`` and ``runtime.jobs.get_job(job_id)``); it writes
    nothing.  The frozen spec's (b) list names five runtime functions, but a
    CEO-submitted job is recognizable ONLY through this function (``Job`` has
    no ``workstream`` and no ``ceo_intent_provenance`` attribute), so
    re-implementing its v1/v2 schema-version logic here would duplicate
    control-plane law in a viewer.  The Control Room's call shape
    (``chairman_control_room.py:1268-1280``) is mirrored, but NOT its bare
    ``continue``: dropping a provenance-less job is exactly hazard D4, so
    every job the view cannot join is counted and named instead.

DEVIATION 2 — compositor/gather signature extension.
    The spec sketches ``compose_fabric_view(*, root_job, jobs,
    attempts_by_job, runtime_identity, armed, degraded)``.  This module keeps
    all of those and adds the narrow inputs the frozen *document* requires but
    the sketch cannot supply from those six: ``root_job_id``,
    ``joined_job_ids`` (the D4 join result), ``read_failed`` and
    ``generated_at``.  Nothing is defaulted by reading the filesystem, so the
    compositor stays pure.

DEVIATION 3 — the spec's second no-regression witness does not exist.
    The spec names ``tests/test_executive_runtime.py``; at BASE ``19b61118``
    no such file exists.  The actual guard for ``control_plane/
    executive_runtime.py`` is ``tests/test_executive_os_sqlite.py``, which is
    what the lane ran UNEDITED alongside ``tests/test_chairman_control_room.
    py``.

DEVIATION 4 — ``review.reviews_job_id`` direction (schema truth).
    The DB stores the review pointer on the REVIEW job (``j.reviews_job_id``
    names the job being reviewed: ``executive_runtime.py:9157``, ``:9194``,
    and the ``create_job`` sibling rule at ``:10386-10405``).  A job card's
    ``review`` block renders the review OF that job: ``reviews_job_id`` is the
    reviewer's id (reverse-resolved from the same full scan), ``verdict`` is
    that reviewer's recorded verdict, and a job that is itself a review job
    additionally renders its OWN verdict.  Both directions stay visible; a
    review that has not happened is never rendered as a verdict (D3).

Every unknown is typed, never guessed: an absent database refuses the whole
call; an unreadable one degrades by name; a job with no Attempt is
``NOT_STARTED``; an undecided review is ``NOT_YET`` plus a ``MISSING_PRODUCER``
fact; an unjoined job is counted; an absent ``control.json`` leaves every arm
``null`` rather than asserting ``false``; and the consultation/Wake return
path is never rendered (it is disarmed, and here ``EXCLUDED``).

The one shape the spec fixes that deserves saying plainly: ``children`` holds
the child Jobs the view could JOIN to a CEO-intent workstream, and
``unjoined_job_count`` / ``unjoined_job_ids`` hold every other job in scope.
Nothing is hidden — a job the view cannot join is counted by total, named once
in ``degraded``, and its id is listed — and the two sets are disjoint, so
``len(children) + unjoined_job_count`` is the size of the scope.  That is the
D4 identity; a viewer that rendered only the joined subset WITHOUT the count
is the ``chairman_control_room.py:1274-1280`` hazard, and it is a red test.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane import executive_inbox

SCHEMA = "mastermind.fabric_job_view.v1"
SCHEMA_V2 = "mastermind.fabric_job_view.v2"
ROOT_LIST_SCHEMA = "mastermind.fabric_job_root_list.v1"
ROOT_LIST_SCHEMA_V2 = "mastermind.fabric_job_root_list.v2"

#: Closed document key set, asserted by the compositor (A14's idiom).
OUTPUT_KEYS = frozenset(
    {
        "schema",
        "generated_at",
        "runtime",
        "armed",
        "root",
        "children",
        "unjoined_job_count",
        "unjoined_job_ids",
        "degraded",
        "missingness",
        "capability",
    }
)
JOB_CARD_KEYS = frozenset(
    {
        "job_id",
        "status",
        "parent_job_id",
        "root_job_id",
        "depth",
        "orchestration_role",
        "plan_step_id",
        "attempt_count",
        "attempt_limit",
        "current_attempt_id",
        "attempts",
        "latest_attempt",
        "review",
        "repair",
        "result",
    }
)
JOB_CARD_KEYS_V2 = JOB_CARD_KEYS | {"acceptance"}
ACCEPTANCE_KEYS = frozenset({"state", "producer_owner", "reason"})
ATTEMPT_CARD_KEYS = frozenset(
    {
        "attempt_id",
        "attempt_number",
        "status",
        "started_at",
        "finished_at",
        "exit_code",
        "has_result",
        "error",
    }
)
ROOT_ROW_KEYS = frozenset(
    {"job_id", "status", "depth", "parent_job_id", "orchestration_role"}
)
ROOT_LIST_KEYS = frozenset(
    {"schema", "generated_at", "runtime", "roots", "count", "total", "truncated", "degraded"}
)

#: A16 vocabularies.  Never invent a member.
MISSINGNESS_CLASSES = frozenset(
    {"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"}
)
CAPABILITY_STATES = ("PROVEN", "PARTIAL", "UNSUPPORTED", "NOT_INSTALLED")
PROVEN, PARTIAL, UNSUPPORTED, NOT_INSTALLED = CAPABILITY_STATES

#: Mirrors ``executive_inbox.DB_RELATIVE_PATH`` (executive_inbox.py:128).
DB_RELATIVE_PATH = Path("data") / "control_plane" / "executive.sqlite3"

#: Mirrors ``executive_mcp.schemas.PRODUCTION_CONTROL_CONFIG``
#: (``integrations/executive_mcp/schemas.py:176``).  Importing that package
#: from a viewer is forbidden (D6), so the operator-visible default is named
#: here rather than imported.
DEFAULT_CONTROL_CONFIG = Path(
    "/Library/Application Support/MastermindExecutive/config/control.json"
)

#: ``armed`` reads: only these five bits, and ``source`` as the discriminator.
ARM_KEYS = (
    "ceo_submit_armed",
    "coo_autonomy_armed",
    "ceo_ingress_app_armed",
    "dialogue_bridge_armed",
    "terminal_return_armed",
)

#: Seat ruling R3 / R2 bounds.
UNJOINED_JOB_ID_LIMIT = 50
LIST_ROOTS_LIMIT = 50

_MAX_DETAIL_CHARS = 512

_TERMINAL_RESULT_STATES = {
    "COMPLETED": "ACCEPTED",
    "CANCELLED": "CANCELLED",
    "FAILED": "FAILED",
    "LOST": "LOST",
    "RATE_LIMITED": "RATE_LIMITED",
}
_TERMINAL_EXECUTION_STATES_V2 = {
    "COMPLETED": "COMPLETED",
    "CANCELLED": "CANCELLED",
    "FAILED": "FAILED",
    "LOST": "LOST",
    "RATE_LIMITED": "RATE_LIMITED",
}
_VERDICTS = ("approve", "reject")

_UNARMED_ENTRY = (
    "ceo_submit_armed: false; no Chairman-authenticated admitted job can exist yet"
)
_UNARMED_ENTRY_V2 = (
    "ceo_submit_armed: false; new CEO submissions are unavailable through this arm"
)


# ---------------------------------------------------------------------------
# small shared shapes
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _enum_value(status: Any) -> str:
    """The Control Room's own idiom: an enum renders as its literal value."""

    return getattr(status, "value", None) or str(status)


def _bounded(text: Any) -> str:
    lines = str(text).splitlines()
    first = lines[0].strip() if lines else ""
    return first[:_MAX_DETAIL_CHARS]


def _failure_first_line(exc: BaseException) -> str:
    return _bounded(exc) or type(exc).__name__


def _fact(
    missingness_class: str,
    target_field: str,
    producer_owner: str | None,
    reason: str,
) -> dict[str, Any]:
    if missingness_class not in MISSINGNESS_CLASSES:
        raise ValueError(f"unknown missingness_class {missingness_class!r}")
    return {
        "missingness_class": missingness_class,
        "target_field": target_field,
        "producer_owner": producer_owner,
        "reason": reason,
    }


def _return_path_fact() -> dict[str, Any]:
    # A20/census §7.3: the return path is disarmed and its delivered/consumed/
    # never-delivered mapping is COULD-NOT-DETERMINE, so v1 does not render it.
    return _fact(
        "EXCLUDED",
        "return_path",
        "wake",
        "return path disarmed; production_armed=false",
    )


def _runtime_identity_fact() -> dict[str, Any]:
    # No in-tree runtime identity artifact is readable by a read-only viewer;
    # the installed release manifest is a host artifact this view may not read.
    return _fact(
        "NULL_BY_DESIGN",
        "runtime.identity",
        "executive_os",
        "no in-tree runtime identity artifact is readable by this view",
    )


def _dedupe_facts(facts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for fact in facts:
        key = (
            str(fact["missingness_class"]),
            str(fact["target_field"]),
            str(fact["producer_owner"] or ""),
            str(fact["reason"]),
        )
        unique.setdefault(key, dict(fact))
    return sorted(
        unique.values(),
        key=lambda fact: (
            fact["missingness_class"],
            fact["target_field"],
            fact["producer_owner"] or "",
            fact["reason"],
        ),
    )


def describe_capability() -> dict[str, Any]:
    """The A16 capability object for ``--describe``; opens nothing at all."""

    return {
        "state": NOT_INSTALLED,
        "installed": False,
        "version": None,
        "detail": (
            "fabric job view is a read-only library + CLI; nothing is installed "
            "by it and --describe opens no runtime"
        ),
    }


def _capability(*, db_present: bool, read_failed: bool, root_present: bool) -> dict[str, Any]:
    """Derived ONLY from observed facts — never hardcoded (D5).

    ``installed`` means "an Executive runtime database is present here", which
    is the only installation fact this reader can observe.
    """

    if not db_present:
        return {
            "state": NOT_INSTALLED,
            "installed": False,
            "version": None,
            "detail": "no executive runtime database is present at this root",
        }
    if read_failed:
        return {
            "state": UNSUPPORTED,
            "installed": True,
            "version": None,
            "detail": "the executive runtime database is present but unreadable by this view",
        }
    if not root_present:
        return {
            "state": PARTIAL,
            "installed": True,
            "version": None,
            "detail": "the executive runtime database was read; the requested root job is not in it",
        }
    return {
        "state": PROVEN,
        "installed": True,
        "version": None,
        "detail": "the executive runtime database was read; the requested root job was found",
    }


# ---------------------------------------------------------------------------
# pure composition
# ---------------------------------------------------------------------------

def _job_sort_key(job: Any) -> tuple[int, str, str]:
    return (
        int(getattr(job, "depth", 0) or 0),
        str(getattr(job, "created_at", "") or ""),
        str(getattr(job, "job_id", "") or ""),
    )


def _children_of(jobs: Sequence[Any], root_job_id: str) -> list[Any]:
    return sorted(
        (
            job
            for job in jobs
            if str(getattr(job, "root_job_id", "") or "") == root_job_id
            and str(getattr(job, "job_id", "") or "") != root_job_id
        ),
        key=_job_sort_key,
    )


def _partition(jobs, *, root_job, root_job_id, joined_job_ids):
    """Split the root's rendered scope into (rendered children, unjoined members).

    ``jobs`` is the FULL table scan (``list_jobs()`` takes no arguments and
    cannot be filtered), so the root filter happens here, in Python.

    D4 contract: ``children`` are the child Jobs this view could JOIN to a
    CEO-intent workstream, and every other member of the scope (root included)
    is returned as ``unjoined`` — counted, id-exposed (R3) and named once in
    ``degraded``.  The rendered tree is therefore never a silent subset:
    ``len(children) + unjoined_job_count`` equals the number of Jobs in scope,
    which is exactly the identity D4 asserts.  Dropping ``unjoined`` here (the
    Control Room's bare ``continue``, A15) is the hazard this function exists
    to refuse.
    """

    child_jobs = _children_of(jobs, root_job_id)
    scope = ([root_job] if root_job is not None else []) + child_jobs
    joined = {str(job.job_id) for job in scope if str(job.job_id) in joined_job_ids}
    rendered = [job for job in child_jobs if str(job.job_id) in joined]
    unjoined = [job for job in scope if str(job.job_id) not in joined]
    return rendered, unjoined


def _attempt_card(attempt: Any) -> dict[str, Any]:
    error = getattr(attempt, "error", None)
    return {
        "attempt_id": str(getattr(attempt, "attempt_id", "") or ""),
        "attempt_number": int(getattr(attempt, "attempt_number", 0) or 0),
        "status": _enum_value(getattr(attempt, "status", "")),
        "started_at": getattr(attempt, "started_at", None),
        "finished_at": getattr(attempt, "finished_at", None),
        "exit_code": getattr(attempt, "exit_code", None),
        "has_result": getattr(attempt, "result", None) is not None,
        "error": None if error is None else _bounded(error),
    }


def _payload_str(payload: Any, key: str) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _payload_list(payload: Any, key: str) -> list[str]:
    if not isinstance(payload, Mapping):
        return []
    value = payload.get(key)
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


def _result_state(job: Any, attempts: Sequence[Any]) -> str:
    """Admitted-but-never-claimed is NOT_STARTED — never RUNNING, never FAILED.

    Admission creates a Job; the Attempt is created by ``claim_job`` (HET1 A5).
    """

    status = _enum_value(getattr(job, "status", ""))
    if status in _TERMINAL_RESULT_STATES:
        return _TERMINAL_RESULT_STATES[status]
    if (
        not attempts
        and not getattr(job, "current_attempt_id", None)
        and not int(getattr(job, "attempt_count", 0) or 0)
    ):
        return "NOT_STARTED"
    return "IN_PROGRESS"


def _result_state_v2(job: Any, attempts: Sequence[Any]) -> str:
    """Execution state only; never aliases completion to product acceptance."""

    status = _enum_value(getattr(job, "status", ""))
    if status in _TERMINAL_EXECUTION_STATES_V2:
        return _TERMINAL_EXECUTION_STATES_V2[status]
    if (
        not attempts
        and not getattr(job, "current_attempt_id", None)
        and not int(getattr(job, "attempt_count", 0) or 0)
    ):
        return "NOT_STARTED"
    return "IN_PROGRESS"


def _acceptance_v2() -> tuple[dict[str, Any], dict[str, Any]]:
    """No product-acceptance producer exists in the current Fabric owner."""

    reason = "product acceptance has no producer in this projection"
    return (
        {"state": "NOT_PROJECTED", "producer_owner": None, "reason": reason},
        _fact("MISSING_PRODUCER", "acceptance.state", None, reason),
    )


def _reviewers_by_subject(jobs: Sequence[Any]) -> dict[str, Any]:
    """subject job id -> the review Job that reviews it.

    The pointer lives on the REVIEW job (``reviews_job_id`` names the reviewed
    job).  First writer wins, over a deterministic order.
    """

    reviewers: dict[str, Any] = {}
    for job in sorted(jobs, key=_job_sort_key):
        pointer = getattr(job, "reviews_job_id", None)
        if isinstance(pointer, str) and pointer:
            reviewers.setdefault(pointer, job)
    return reviewers


def _verdict_of(review_job: Any) -> tuple[str, str]:
    """``(verdict_literal, raw)`` for one review Job.

    An undecided review persists a payload with the ``verdict`` key ABSENT
    (``JobPayload.to_dict`` drops an empty verdict), so both absent and ``""``
    are NOT_YET — never ``reject``, never ``false``.
    """

    payload = getattr(review_job, "result", None)
    if not isinstance(payload, Mapping):
        payload = getattr(review_job, "checkpoint", None)
    raw = ""
    if isinstance(payload, Mapping):
        raw = str(payload.get("verdict") or "").strip().lower()
    return (raw if raw in _VERDICTS else "NOT_YET"), raw


def _review_block(job: Any, reviewers_by_subject: Mapping[str, Any]):
    job_id = str(job.job_id)
    required = bool(getattr(job, "review_required", False))
    reviewer = reviewers_by_subject.get(job_id)
    if reviewer is not None:
        reviews_job_id = str(reviewer.job_id)
        verdict, raw = _verdict_of(reviewer)
    else:
        own_pointer = getattr(job, "reviews_job_id", None)
        reviews_job_id = (
            str(own_pointer) if isinstance(own_pointer, str) and own_pointer else None
        )
        verdict, raw = _verdict_of(job) if reviews_job_id is not None else ("NOT_YET", "")

    facts: list[dict[str, Any]] = []
    if reviewer is not None and verdict == "NOT_YET":
        facts = facts + [
            _fact(
                "MISSING_PRODUCER",
                "review.verdict",
                str(reviewer.job_id),
                "no completed independent review",
            )
        ]
    elif reviewer is None and required:
        facts = facts + [
            _fact(
                "MISSING_PRODUCER",
                "review.reviews_job_id",
                None,
                "review required but no review job recorded",
            )
        ]
    if raw and verdict == "NOT_YET":
        facts = facts + [
            _fact(
                "DEGRADED",
                "review.verdict",
                str(reviewer.job_id) if reviewer is not None else reviews_job_id,
                f"unrecognized review verdict {raw!r}",
            )
        ]
    return {"required": required, "reviews_job_id": reviews_job_id, "verdict": verdict}, facts


def _job_card(
    job: Any,
    attempts: Sequence[Any],
    reviewers_by_subject,
    *,
    contract_version: int = 1,
):
    attempt_cards = [_attempt_card(attempt) for attempt in attempts]
    review, facts = _review_block(job, reviewers_by_subject)
    status = _enum_value(getattr(job, "status", ""))
    result = getattr(job, "result", None)
    state = (
        _result_state_v2(job, attempts)
        if contract_version == 2
        else _result_state(job, attempts)
    )
    result_block = {
        "state": state,
        "summary": _payload_str(result, "summary"),
        "artifacts": _payload_list(result, "artifacts"),
        "errors": _payload_list(result, "errors"),
        "next_actions": _payload_list(result, "next_actions"),
    }
    if status == "COMPLETED" and not (isinstance(result, Mapping) and result):
        reason = (
            "COMPLETED job carries no result payload"
            if contract_version == 2
            else "COMPLETED job carries no accepted result payload"
        )
        facts = facts + [
            _fact("DEGRADED", "result.summary", str(job.job_id), reason)
        ]
    card = {
        "job_id": str(job.job_id),
        "status": status,
        "parent_job_id": getattr(job, "parent_job_id", None),
        "root_job_id": getattr(job, "root_job_id", None),
        "depth": int(getattr(job, "depth", 0) or 0),
        "orchestration_role": getattr(job, "orchestration_role", None),
        "plan_step_id": getattr(job, "plan_step_id", None),
        "attempt_count": int(getattr(job, "attempt_count", 0) or 0),
        "attempt_limit": int(getattr(job, "attempt_limit", 0) or 0),
        "current_attempt_id": getattr(job, "current_attempt_id", None),
        "attempts": attempt_cards,
        "latest_attempt": attempt_cards[-1] if attempt_cards else None,
        "review": review,
        "repair": {
            "repair_round": getattr(job, "repair_round", None),
            "supersedes_job_id": getattr(job, "supersedes_job_id", None),
        },
        "result": result_block,
    }
    if contract_version == 2:
        acceptance, missing = _acceptance_v2()
        card["acceptance"] = acceptance
        facts = facts + [missing]
        assert set(acceptance.keys()) == ACCEPTANCE_KEYS
        assert set(card.keys()) == JOB_CARD_KEYS_V2
    else:
        assert set(card.keys()) == JOB_CARD_KEYS
    return card, facts


def _compose_fabric_view(
    *,
    root_job_id: str,
    root_job: Any,
    jobs: Sequence[Any],
    attempts_by_job: Mapping[str, Sequence[Any]],
    joined_job_ids: Iterable[str],
    runtime_identity: Mapping[str, Any],
    armed: Mapping[str, Any],
    degraded: Iterable[str],
    read_failed: bool = False,
    generated_at: str | None = None,
    schema: str,
    contract_version: int,
    unarmed_entry: str,
) -> dict[str, Any]:
    """PURE: render one root's truthful view document.  No I/O whatsoever."""

    joined = {str(job_id) for job_id in joined_job_ids}
    children, unjoined = _partition(
        jobs, root_job=root_job, root_job_id=str(root_job_id), joined_job_ids=joined
    )
    reviewers = _reviewers_by_subject(jobs)

    cards: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = [_return_path_fact(), _runtime_identity_fact()]
    for job in ([root_job] if root_job is not None else []) + children:
        card, card_facts = _job_card(
            job,
            attempts_by_job.get(str(job.job_id), []),
            reviewers,
            contract_version=contract_version,
        )
        cards = cards + [card]
        facts = facts + card_facts

    db_present = bool(runtime_identity.get("db_present"))
    entries = [str(entry) for entry in degraded]

    if not db_present:
        facts = facts + [
            _fact(
                "MISSING_PRODUCER",
                "runtime.jobs",
                "executive_runtime",
                "runtime database absent; no job truth is available",
            )
        ]
    elif read_failed:
        facts = facts + [
            _fact(
                "MISSING_PRODUCER",
                "runtime.jobs",
                "executive_runtime",
                "runtime unreadable; no job truth is available",
            )
        ]
    elif root_job is None:
        facts = facts + [
            _fact(
                "MISSING_PRODUCER",
                "root",
                "executive_runtime",
                f"no job {str(root_job_id)!r} in the runtime",
            )
        ]
        entries = entries + [
            f"root job {str(root_job_id)!r} is not present in the executive runtime"
        ]

    if unjoined:
        entries = entries + [
            f"unjoined jobs: {len(unjoined)} job(s) under root {str(root_job_id)!r} "
            "carry no CEO-intent workstream provenance"
        ]

    if armed.get("ceo_submit_armed") is False:
        entries = entries + [unarmed_entry]

    root_card = cards[0] if root_job is not None and cards else None
    child_cards = cards[1:] if root_job is not None and cards else cards

    doc = {
        "schema": schema,
        "generated_at": generated_at or _utc_now(),
        "runtime": {
            "root": runtime_identity.get("root"),
            "db_present": db_present,
            "identity": runtime_identity.get("identity"),
        },
        "armed": {
            **{key: armed.get(key) for key in ARM_KEYS},
            "source": armed.get("source"),
        },
        "root": root_card,
        "children": child_cards,
        "unjoined_job_count": len(unjoined),
        "unjoined_job_ids": sorted(str(job.job_id) for job in unjoined)[
            :UNJOINED_JOB_ID_LIMIT
        ],
        "degraded": sorted(set(entries)),
        "missingness": _dedupe_facts(facts),
        "capability": _capability(
            db_present=db_present,
            read_failed=bool(read_failed),
            root_present=root_job is not None,
        ),
    }
    assert set(doc.keys()) == OUTPUT_KEYS  # self-check: closed set, like A14
    return doc


def compose_fabric_view(
    *,
    root_job_id: str,
    root_job: Any,
    jobs: Sequence[Any],
    attempts_by_job: Mapping[str, Sequence[Any]],
    joined_job_ids: Iterable[str],
    runtime_identity: Mapping[str, Any],
    armed: Mapping[str, Any],
    degraded: Iterable[str],
    read_failed: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Historical v1 projection; retained byte-semantically for old consumers."""

    return _compose_fabric_view(
        root_job_id=root_job_id,
        root_job=root_job,
        jobs=jobs,
        attempts_by_job=attempts_by_job,
        joined_job_ids=joined_job_ids,
        runtime_identity=runtime_identity,
        armed=armed,
        degraded=degraded,
        read_failed=read_failed,
        generated_at=generated_at,
        schema=SCHEMA,
        contract_version=1,
        unarmed_entry=_UNARMED_ENTRY,
    )


def compose_fabric_view_v2(
    *,
    root_job_id: str,
    root_job: Any,
    jobs: Sequence[Any],
    attempts_by_job: Mapping[str, Sequence[Any]],
    joined_job_ids: Iterable[str],
    runtime_identity: Mapping[str, Any],
    armed: Mapping[str, Any],
    degraded: Iterable[str],
    read_failed: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Truthful v2: execution completion and product acceptance stay separate."""

    return _compose_fabric_view(
        root_job_id=root_job_id,
        root_job=root_job,
        jobs=jobs,
        attempts_by_job=attempts_by_job,
        joined_job_ids=joined_job_ids,
        runtime_identity=runtime_identity,
        armed=armed,
        degraded=degraded,
        read_failed=read_failed,
        generated_at=generated_at,
        schema=SCHEMA_V2,
        contract_version=2,
        unarmed_entry=_UNARMED_ENTRY_V2,
    )


# ---------------------------------------------------------------------------
# the gather layer
# ---------------------------------------------------------------------------

def _read_armed(control_config_path: Path | None):
    """Read the five arm bits; never raises, never asserts a fact it lacks."""

    path = (
        Path(control_config_path)
        if control_config_path is not None
        else DEFAULT_CONTROL_CONFIG
    )
    absent = {key: None for key in ARM_KEYS}
    absent["source"] = "absent"
    if not path.is_file():
        return absent, [f"control.json missing at {path}"]
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return absent, [f"control.json unreadable: {_failure_first_line(exc)}"]
    try:
        loaded = json.loads(raw)
    except ValueError as exc:
        return absent, [f"control.json unreadable: {_failure_first_line(exc)}"]
    if not isinstance(loaded, Mapping):
        return absent, [f"control.json unreadable: {path}: not a JSON object"]
    armed = {key: (loaded.get(key) if isinstance(loaded.get(key), bool) else None) for key in ARM_KEYS}
    armed["source"] = "control.json"
    return armed, []


def _open_runtime(runtime_root: Path, db_path: Path):
    """Open the Executive runtime READ-ONLY.  ``create=False`` is load-bearing.

    ``Runtime.at`` defaults ``create=True``: a bare call on an absent root
    manufactures an empty database and then reports a quiet, job-free company
    (census §4.3).  The constructor is therefore ALWAYS called, with
    ``create=False``, and is what fails closed: ``Runtime.at`` refuses an
    absent or unopenable store with :class:`PersistenceError`.  The file check
    below no longer gates the call — it only CHOOSES THE MESSAGE, telling a
    genuinely absent runtime apart from a present-but-unreadable one.
    """

    from control_plane import executive_runtime

    try:
        runtime = executive_runtime.Runtime.at(runtime_root, create=False)
    except (executive_runtime.RuntimeProofError, OSError) as exc:
        if not db_path.is_file():
            return None, False, [f"executive_runtime: database missing at {db_path}"]
        return None, True, [f"jobs unreadable: {_failure_first_line(exc)}"]
    return runtime, True, []


def _gathered(
    *,
    root_job: Any = None,
    jobs: Sequence[Any] = (),
    attempts_by_job: Mapping[str, Sequence[Any]] | None = None,
    joined_job_ids: Iterable[str] = (),
    degraded: Iterable[str] = (),
    read_failed: bool = False,
    db_present: bool = False,
) -> dict[str, Any]:
    return {
        "root_job": root_job,
        "jobs": list(jobs),
        "attempts_by_job": dict(attempts_by_job or {}),
        "joined_job_ids": set(joined_job_ids),
        "degraded": list(degraded),
        "read_failed": read_failed,
        "db_present": db_present,
    }


def _gather_jobs(runtime_root: str | Path, root_job_id: str) -> dict[str, Any]:
    """Read the runtime; a typed refusal on any failure.  Writes nothing."""

    from control_plane import executive_runtime

    runtime_root = Path(runtime_root)
    db_path = runtime_root / DB_RELATIVE_PATH
    try:
        runtime, db_present, open_degraded = _open_runtime(runtime_root, db_path)
        if runtime is None:
            # A store that exists but will not open is a FAILED READ, not an
            # absent runtime: report the file as present AND the read as failed.
            return _gathered(
                degraded=open_degraded,
                read_failed=bool(db_present),
                db_present=db_present,
            )

        all_jobs = runtime.jobs.list_jobs()
        root_job = runtime.jobs.get_job(str(root_job_id))
        scope = ([root_job] if root_job is not None else []) + _children_of(
            all_jobs, str(root_job_id)
        )

        attempts_by_job: dict[str, Sequence[Any]] = {}
        joined: set[str] = set()
        notes: list[str] = []
        for job in scope:
            job_key = str(job.job_id)
            attempts_by_job[job_key] = runtime.attempts.list_attempts(job_key)
            try:
                provenance, warning = executive_inbox.ceo_intent_provenance(
                    runtime, job_key
                )
            except (executive_runtime.RuntimeProofError, ValueError, KeyError) as exc:
                # Counted as unjoined below AND named here — never dropped.
                notes = notes + [
                    f"provenance unreadable: {job_key}: {_failure_first_line(exc)}"
                ]
                continue
            workstream = (
                provenance.get("workstream") if isinstance(provenance, Mapping) else None
            )
            if isinstance(workstream, str) and workstream.strip():
                joined.add(job_key)
            elif warning:
                notes = notes + [f"provenance warning: {_bounded(warning)}"]
    except (executive_runtime.RuntimeProofError, OSError, ValueError, KeyError) as exc:
        return _gathered(
            degraded=[f"jobs unreadable: {_failure_first_line(exc)}"],
            read_failed=True,
            db_present=db_path.is_file(),
        )

    return _gathered(
        root_job=root_job,
        jobs=all_jobs,
        attempts_by_job=attempts_by_job,
        joined_job_ids=joined,
        degraded=notes,
        db_present=db_present,
    )


def _read_fabric_view(
    runtime_root: str | Path,
    root_job_id: str,
    *,
    control_config_path: str | Path | None,
    composer,
) -> dict[str, Any]:
    armed, armed_degraded = _read_armed(
        None if control_config_path is None else Path(control_config_path)
    )
    gathered = _gather_jobs(runtime_root, str(root_job_id))
    return composer(
        root_job_id=str(root_job_id),
        root_job=gathered["root_job"],
        jobs=gathered["jobs"],
        attempts_by_job=gathered["attempts_by_job"],
        joined_job_ids=gathered["joined_job_ids"],
        runtime_identity={
            "root": str(runtime_root),
            "db_present": gathered["db_present"],
            "identity": None,
        },
        armed=armed,
        degraded=list(armed_degraded) + list(gathered["degraded"]),
        read_failed=gathered["read_failed"],
    )


def read_fabric_view(
    runtime_root: str | Path,
    root_job_id: str,
    *,
    control_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Gather one root and render historical v1. Read-only."""

    return _read_fabric_view(
        runtime_root,
        root_job_id,
        control_config_path=control_config_path,
        composer=compose_fabric_view,
    )


def _bounded_provenance(runtime, job):
    """Validate durable routing before one Event point read and owner validation.

    The adapter supplies only the immutable Job already in the bounded snapshot
    and its unique command-id Event. The historical validator receives no real
    registry, so its compatibility list interface cannot acquire Event history.
    """
    from control_plane.executive_runtime import orchestration_digest

    cycle = getattr(job, "orchestration_provenance", None)
    digest = getattr(job, "orchestration_provenance_digest", None)
    keys = {"schema_version", "creator", "source_id", "source_digest", "command_id",
            "job_id", "parent_job_id", "root_job_id", "role"}
    if not isinstance(cycle, Mapping) or set(cycle) != keys:
        return None, "durable CEO-intent provenance not projected"
    source_id = cycle.get("source_id")
    if not (
        cycle.get("schema_version") == "mastermind.executive_orchestration_provenance/v1"
        and cycle.get("creator") == "ceo_intent"
        and isinstance(source_id, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", source_id)
        and cycle.get("command_id") == f"ceo-intent:{source_id}"
        and isinstance(cycle.get("source_digest"), str)
        and re.fullmatch(r"[0-9a-f]{64}", cycle["source_digest"])
        and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        and digest == orchestration_digest(cycle)
        and cycle.get("job_id") == job.job_id
        and cycle.get("parent_job_id") is None and job.parent_job_id is None
        and cycle.get("root_job_id") == job.job_id == job.root_job_id
        and cycle.get("role") == job.orchestration_role == "aggregation"
    ):
        return None, "durable CEO-intent provenance invalid or unsupported"
    event = runtime.events.get_event_by_command_id(cycle["command_id"])
    if event is None or event.event_type != "JOB_CREATED":
        return None, "durable CEO-intent creation Event unavailable"
    # Only v2 carries the durable cycle needed to prove this bounded join.
    provenance = event.payload.get("provenance") if isinstance(event.payload, Mapping) else None
    if not isinstance(provenance, Mapping) or provenance.get("schema") != "mastermind.ceo_intent.v2":
        return None, "durable CEO-intent creation Event schema unsupported"
    adapter = SimpleNamespace(
        jobs=SimpleNamespace(get_job=lambda job_id: job if job_id == job.job_id else None),
        events=SimpleNamespace(list_events=lambda *, job_id: (event,) if job_id == job.job_id else ()),
    )
    return executive_inbox.ceo_intent_provenance(adapter, str(job.job_id))


def _acquisition_receipt(*, kind, root_job_id=None, snapshot=None, unjoined=(), projection=False):
    return {
        "schema": "mastermind.fabric_runtime_acquisition.v1",
        "query": {"kind": kind, "root_job_id": root_job_id},
        "owner": "executive_runtime",
        "snapshot_digest": getattr(snapshot, "snapshot_digest", None),
        "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                    "attempts_total": 340, "creation_events_per_job": 1},
        "truncation": {
            "jobs": bool(getattr(snapshot, "jobs_truncated", False)),
            "attempt_job_ids": list(getattr(snapshot, "attempts_truncated_job_ids", ())),
            "roots": bool(getattr(snapshot, "truncated", False)),
            "projection": projection,
        },
        "provenance": {"state": "PARTIAL" if unjoined or snapshot is None else "COMPLETE",
                       "unjoined_job_ids": sorted(unjoined)},
        "generation": {"state": "UNKNOWN", "source_identity": None,
                       "before": None, "after": None,
                       "reason": "Runtime owner generation seam not yet supplied"},
    }


def read_fabric_view_v2(
    runtime_root: str | Path,
    root_job_id: str,
    *,
    control_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Finite v2 acquisition; no fallback to historical population reads."""
    from control_plane import executive_runtime

    runtime_root = Path(runtime_root)
    root_job_id = str(root_job_id)
    armed, notes = _read_armed(None if control_config_path is None else Path(control_config_path))
    db_path = runtime_root / DB_RELATIVE_PATH
    runtime, present, open_notes = _open_runtime(runtime_root, db_path)
    notes += open_notes
    snapshot = None
    jobs, joined, unjoined = [], set(), []
    attempts_by_job = {}
    failed = runtime is None and present
    try:
        if runtime is not None:
            snapshot = runtime.read_job_root_bounded(root_job_id)
            jobs = list(snapshot.jobs)
            if (snapshot.root_job_id != root_job_id or not jobs
                    or jobs[0].job_id != root_job_id or len(jobs) > 17
                    or len(snapshot.attempts) > 340):
                raise ValueError("bounded Runtime snapshot identity or budget invalid")
            ids = {job.job_id for job in jobs}
            if len(ids) != len(jobs) or any(job.root_job_id != root_job_id for job in jobs):
                raise ValueError("bounded Runtime snapshot membership invalid")
            for attempt in snapshot.attempts:
                if attempt.job_id not in ids:
                    raise ValueError("bounded Runtime Attempt membership invalid")
                attempts_by_job[attempt.job_id] = attempts_by_job.get(attempt.job_id, []) + [attempt]
            if any(len(attempts) > 20 for attempts in attempts_by_job.values()):
                raise ValueError("bounded Runtime Attempt budget invalid")
            for job in jobs:
                provenance, warning = _bounded_provenance(runtime, job)
                if isinstance(provenance, Mapping) and provenance.get("workstream"):
                    joined.add(job.job_id)
                else:
                    unjoined = unjoined + [job.job_id]
                    notes = notes + [f"provenance not projected: {job.job_id}: {warning or 'workstream unavailable'}"]
            if snapshot.jobs_truncated:
                notes = notes + ["bounded Runtime Job snapshot truncated"]
            if snapshot.attempts_truncated_job_ids:
                notes = notes + ["bounded Runtime Attempt snapshot truncated"]
    except (executive_runtime.RuntimeProofError, OSError, ValueError, KeyError, AttributeError) as exc:
        notes = notes + [f"bounded acquisition unavailable: {_failure_first_line(exc)}"]
        failed = True
        snapshot, jobs, attempts_by_job, joined, unjoined = None, [], {}, set(), []
    doc = compose_fabric_view_v2(
        root_job_id=root_job_id, root_job=jobs[0] if jobs else None,
        jobs=jobs, attempts_by_job=attempts_by_job, joined_job_ids=joined,
        runtime_identity={"root": str(runtime_root), "db_present": present, "identity": None},
        armed=armed, degraded=notes, read_failed=failed,
    )
    receipt = _acquisition_receipt(kind="root_detail", root_job_id=root_job_id,
                                   snapshot=snapshot, unjoined=unjoined)
    doc["runtime"]["acquisition"] = receipt
    if snapshot is not None and (unjoined or snapshot.jobs_truncated or snapshot.attempts_truncated_job_ids):
        doc["capability"]["state"] = PARTIAL
        doc["capability"]["detail"] = "bounded snapshot has omitted rows or unavailable provenance"
        facts = []
        if unjoined:
            facts = facts + [_fact("MISSING_PRODUCER", "runtime.acquisition.provenance", "executive_runtime",
                               "durable CEO-intent workstream join unavailable for included Jobs")]
        if snapshot.jobs_truncated or snapshot.attempts_truncated_job_ids:
            facts = facts + [_fact("OMITTED", "runtime.acquisition.truncation", "executive_runtime",
                               "owner acquisition budget omits Jobs or Attempts")]
        doc["missingness"] = _dedupe_facts(doc["missingness"] + facts)
    return doc


def _list_roots(
    runtime_root: str | Path,
    *,
    limit: int,
    control_config_path: str | Path | None,
    schema: str,
    unarmed_entry: str,
) -> dict[str, Any]:
    """Historical acquisition path shared by versioned root-list semantics."""

    from control_plane import executive_runtime

    bounded = int(limit)
    if bounded <= 0:
        raise ValueError("limit must be positive")
    armed, armed_degraded = _read_armed(
        None if control_config_path is None else Path(control_config_path)
    )
    runtime_root = Path(runtime_root)
    db_path = runtime_root / DB_RELATIVE_PATH
    entries = list(armed_degraded)
    if armed.get("ceo_submit_armed") is False:
        entries = entries + [unarmed_entry]
    try:
        runtime, db_present, open_degraded = _open_runtime(runtime_root, db_path)
        if runtime is None:
            if not db_present:
                entries = entries + [
                    "jobs unreadable: runtime database absent; no root can be enumerated"
                ]
            return {
                "schema": schema,
                "generated_at": _utc_now(),
                "runtime": {"root": str(runtime_root), "db_present": db_present, "identity": None},
                "roots": [],
                "count": 0,
                "total": 0,
                "truncated": False,
                "degraded": sorted(set(entries + list(open_degraded))),
            }
        all_jobs = runtime.jobs.list_jobs()
        roots = [
            job
            for job in all_jobs
            if str(job.root_job_id) == str(job.job_id)
        ]
        page = roots[:bounded]
        rows = [
            {
                "job_id": str(job.job_id),
                "status": _enum_value(job.status),
                "depth": int(job.depth or 0),
                "parent_job_id": job.parent_job_id,
                "orchestration_role": job.orchestration_role,
            }
            for job in page
        ]
        for row in rows:
            assert set(row.keys()) == ROOT_ROW_KEYS
        document = {
            "schema": schema,
            "generated_at": _utc_now(),
            "runtime": {"root": str(runtime_root), "db_present": db_present, "identity": None},
            "roots": rows,
            "count": len(rows),
            "total": len(roots),
            "truncated": len(roots) > len(rows),
            "degraded": sorted(set(entries)),
        }
    except (executive_runtime.RuntimeProofError, OSError, ValueError, KeyError) as exc:
        document = {
            "schema": schema,
            "generated_at": _utc_now(),
            "runtime": {
                "root": str(runtime_root),
                "db_present": db_path.is_file(),
                "identity": None,
            },
            "roots": [],
            "count": 0,
            "total": 0,
            "truncated": False,
            "degraded": sorted(
                set(entries + [f"jobs unreadable: {_failure_first_line(exc)}"])
            ),
        }
    assert set(document.keys()) == ROOT_LIST_KEYS
    return document

def list_roots(
    runtime_root: str | Path,
    *,
    limit: int = LIST_ROOTS_LIMIT,
    control_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Historical v1 root enumeration; retained for old consumers."""

    return _list_roots(
        runtime_root,
        limit=limit,
        control_config_path=control_config_path,
        schema=ROOT_LIST_SCHEMA,
        unarmed_entry=_UNARMED_ENTRY,
    )


def list_roots_v2(
    runtime_root: str | Path,
    *,
    limit: int = LIST_ROOTS_LIMIT,
    control_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Discover roots within the fixed Runtime owner budget."""
    from control_plane import executive_runtime

    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")
    runtime_root = Path(runtime_root)
    armed, notes = _read_armed(None if control_config_path is None else Path(control_config_path))
    if armed.get("ceo_submit_armed") is False:
        notes = notes + [_UNARMED_ENTRY_V2]
    runtime, present, open_notes = _open_runtime(runtime_root, runtime_root / DB_RELATIVE_PATH)
    notes += open_notes
    snapshot, rows, total, truncated, projection = None, [], None, False, False
    try:
        if runtime is not None:
            snapshot = runtime.discover_job_roots_bounded()
            roots = snapshot.roots
            if len(roots) > 64 or any(job.root_job_id != job.job_id for job in roots):
                raise ValueError("bounded Runtime discovery identity or budget invalid")
            total = None if snapshot.truncated else len(roots)
            projection = len(roots) > limit
            truncated = bool(snapshot.truncated or projection)
            rows = [{"job_id": str(job.job_id), "status": _enum_value(job.status),
                     "depth": int(job.depth or 0), "parent_job_id": job.parent_job_id,
                     "orchestration_role": job.orchestration_role} for job in roots[:limit]]
            if truncated:
                notes = notes + ["bounded root discovery truncated; omitted roots are not counted"]
    except (executive_runtime.RuntimeProofError, OSError, ValueError, KeyError, AttributeError) as exc:
        notes = notes + [f"bounded acquisition unavailable: {_failure_first_line(exc)}"]
        snapshot, rows, total, truncated, projection = None, [], None, False, False
    return {
        "schema": ROOT_LIST_SCHEMA_V2, "generated_at": _utc_now(),
        "runtime": {"root": str(runtime_root), "db_present": present, "identity": None,
                    "acquisition": _acquisition_receipt(kind="root_discovery", snapshot=snapshot, projection=projection)},
        "roots": rows, "count": len(rows), "total": total,
        "truncated": truncated, "degraded": sorted(set(notes)),
    }
