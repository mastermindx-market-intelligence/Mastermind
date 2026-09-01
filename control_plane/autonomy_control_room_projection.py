"""control_plane.autonomy_control_room_projection — ``mastermind.autonomy_control_room.v1``.

Phase A of ``ad-cr1a-zero-slack-autonomy-cockpit`` (frozen spec
``PHASE_A_FROZEN_SPEC.md``).  This module projects one deterministic,
read-only document of Autonomy responsibility cards for a Chairman Control
Room — *purely* from an already-composed :class:`control_plane.
executive_steward.ExecutiveStewardSnapshot`.

Pure projection only
---------------------
:func:`project_autonomy` is the ONLY public function.  No file I/O, no
subprocess, no clock read, no environment read, no randomness, and no
mutation of the supplied snapshot.  Same ``snapshot`` + ``generated_at`` in
→ byte-identical ``json.dumps(doc, sort_keys=True)`` out.  Modelled on
:func:`control_plane.chairman_control_room.compose_control_room` (see its
docstring, lines 11-17) and :mod:`control_plane.runtime_binding_projection`.

Consume, never duplicate
-------------------------
Every responsibility/attention/runtime/blocker/surface question this module
answers is answered by calling :class:`control_plane.executive_steward.
ExecutiveStewardSnapshot` methods (:meth:`list_responsibilities`,
:meth:`get_responsibility`, :meth:`get_current_runtime`,
:meth:`explain_blocker`, :meth:`get_attention`, :meth:`resolve_surface`) —
never by reading ``snapshot.responsibilities`` / ``.attention`` / ``.runtimes``
/ ``.blockers`` / ``.surfaces`` directly (``snapshot.source_failures`` is the
one exception: §3 of the frozen spec names it as a direct top-level read).
``SourceRef``, ``Freshness``, ``Seat``, ``EffectState``, ``SourceOwner`` and
``QueryStatus`` are imported from :mod:`control_plane.executive_steward`,
never redefined.  ``CapacityState`` is Law #2's fifth named type but this
module has no capacity-state vocabulary of its own to project (Repair
packet, 2026-09-01 — the invented "capacity code" convention was deleted
outright; see the "corrections to the frozen spec" note below), so it is
not imported.

Documented interpretive decisions (see the commissioning packet's DEVIATIONS
for the full list; each is a place the frozen spec names a rule without a
literal, unambiguous mechanical binding to the Steward's typed API):

1. **wake_outcome** (§3, §4.3): the frozen spec says the wake outcome is
   "supplied on the fact" and cites ``wake_ledger.py:62-64``
   (``ObligationStatus.DELIVERED_UNACKNOWLEDGED`` /
   ``TARGET_ACKNOWLEDGED`` / ``SOURCE_RESOLVED``).  No Steward dataclass has
   a field literally named ``wake_outcome``; the only free-text field a Wake
   source can populate is ``AttentionFact.kind`` (``source.owner ==
   SourceOwner.WAKE`` is an allowed owner — see ``executive_steward.py``
   lines 175-179).  This module reads ``wake_outcome`` off exactly that:
   the smallest-by-``(attention_id, source_key)`` WAKE-owned attention fact
   for the responsibility whose ``kind`` is one of the three literal tokens.
2. **EFFECT_UNKNOWN placement detection** (§4.3 bullet 1) is a genuine
   Steward/spec mismatch, not an assumption: see the docstring of
   :func:`_classify_placement` for the exact citation.  A caller-authored
   ``SourceFailure.code`` that happens to equal the Steward's own
   ``reconciliation_required`` issue code must never be mistaken for the
   real signal — see :func:`_classify_placement` for the guard.
3. **Disagreement (§4.6)** is restricted to the one mechanism the Steward
   API can actually produce without refusing: two distinct ``AttentionFact``
   rows (different ``attention_id``, so ``get_attention`` never treats them
   as an ambiguous identity and returns both), owned by ``SourceOwner.WAKE``
   (the same gate :func:`_classify_wake_outcome` applies), whose ``kind``
   values both fall in ``WAKE_OUTCOME_TOKENS`` but disagree.  Every other
   multi-fact join the Steward exposes (``ambiguous_responsibility_join``,
   ``ambiguous_runtime_join``, ``ambiguous_blocker_join``,
   ``ambiguous_surface_join``) collapses to ``data=None`` plus a generic
   issue naming only *sources*, never the differing field content — there
   is no way to recover "both raw values" for those without reading raw
   facts, which Law #2 forbids.  See DEVIATIONS.
4. **query_status combination**: a card's single ``query_status`` is the
   worst of ``get_responsibility``, ``get_current_runtime(WORKER)``,
   ``get_current_runtime(CEO)``, ``explain_blocker`` and ``get_attention``
   (rank ``ok < degraded < unknown < refused``).  ``resolve_surface`` is
   deliberately excluded from this combination — see point 5.
5. **surfaces are receipts-only**: ``ResponsibilityCard`` has no
   ``surfaces`` key in its closed shape (§2), so ``resolve_surface`` is
   called for informational receipts/issues only ("where available", §3)
   and never gates ``query_status``/``is_actionable`` — a routine "no
   binding exists" ``unknown`` from ``resolve_surface`` would otherwise
   make almost every card administratively "refused".  A second Phase A
   repair packet (2026-09-01) extends this the same way to ``freshness``:
   a ``resolve_surface`` issue (``surface_not_reviewed``,
   ``stale_surface_binding``, or any other code that call raises) never
   contributes to a card's ``freshness`` either — see point 7.  Surfaces
   are navigation receipts (where a Chairman-facing view was last saved),
   never evidence of the responsibility's own work state; a stale or
   unreviewed saved destination must not read as "this card's history is
   stale" when its actual work evidence is current.
6. **a routine, source-issue-free ``UNKNOWN`` from ``get_current_runtime``
   or ``explain_blocker`` does not worsen a card's combined
   ``query_status``**: that shape means only "no candidate and nothing else
   is wrong" (e.g. no CEO target, no blocker) — a normal, common state, not
   a query problem — so it is treated as OK-equivalent when combining.
   Without this, §4.4's ``is_actionable`` would be unreachable for almost
   every real card, since most responsibilities have no CEO target and no
   blocker.  See :func:`_neutral_if_routine_absence`.  The same routine-
   absence codes (``surface_unknown``, ``runtime_unknown``,
   ``blocker_unknown``) are also excluded from the top-level ``issues``
   list, so both consumers of "is this a real problem" agree — see
   :data:`_ROUTINE_ABSENCE_ISSUE_CODES`.  That exclusion is scoped to a
   genuinely routine absence only (Phase A repair packet, Repair B,
   2026-09-01): when a caller-authored ``SourceFailure`` happens to carry
   one of those three codes (e.g. ``SourceFailure(owner=EXECUTIVE_OS,
   code="runtime_unknown", ...)``), the collision must never make a real
   outage vanish from ``issues`` — the same ``code not in
   source_failure_codes`` guard used for the ``EFFECT_UNKNOWN`` fix (point
   2) applies here too.
7. **card freshness folds every Steward-internal issue's sources by
   exclusion, not by an allowlist** (§4.1, amended by the Phase A repair
   packet, Repair A, 2026-09-01): the Steward's ambiguity, mismatch and
   reconciliation checks all run BEFORE its own staleness check on several
   call paths (``reconciliation_required``, ``ambiguous_runtime_join``,
   ``ambiguous_blocker_join``, ``runtime_root_mismatch`` and
   ``ambiguous_attention_identity`` all resolve and return before their
   sibling ``stale_*`` branch is ever reached), so a fixed eight-code
   ``stale_*`` allowlist left exactly those five paths reporting evidence
   that was, in fact, entirely stale as ``freshness: "current"``.  The
   correct rule folds a card's ``contributing_sources`` from EVERY issue
   returned by ``get_responsibility``, both ``get_current_runtime`` seats,
   ``explain_blocker`` and ``get_attention`` EXCEPT (a) an issue whose
   ``code`` also appears in ``source_failure_codes`` — a caller-authored
   echo of a free-text ``SourceFailure.code``, not per-card fact evidence;
   ``SourceFailure.as_source()`` hardcodes ``Freshness.UNKNOWN`` and every
   card consults every owner on every call (point 4's ``_source_issues``
   pattern), so folding those would poison every card's freshness whenever
   any owner fails anywhere, defeating the "bounded" partial-source-
   failure guarantee (frozen spec §6 state 12) — and (b) any issue raised
   by ``resolve_surface`` at all, per point 5's surface carve-out.

Three corrections to the frozen spec (Phase A repair packet, 2026-09-01),
binding over the prose above where they differ:

- **§4.2 rule 3** never asserts the worker runtime is *active* — ``status``
  is unconstrained free text with no canonical terminal/non-terminal
  partition reachable from ``executive_steward.py``, so this module can only
  answer "a current worker runtime is *present*".  The reason code is
  ``worker_runtime_present``, not ``worker_runtime_active``.
- **§4.3 ``WAITING_CAPACITY``** has no invented "capacity code" convention.
  There is no canonical capacity-code producer for ``AttentionFact``/
  ``BlockerFact`` at this base, so ``WAITING_CAPACITY`` is legal ONLY when a
  supplied fact's ``code``/``kind`` literally equals the string
  ``"WAITING_CAPACITY"`` — it lives in ``_NO_PRODUCER_PLACEMENT_TOKENS``
  exactly like the other five no-producer tokens, never inferred from
  runtime absence.
- **§4.1 card freshness** folds every Steward-internal issue source except
  source-failure echoes and except ``resolve_surface``-raised (surface
  binding) issues — see point 7 above.  The frozen spec's original
  eight-code ``stale_*`` allowlist under-folded five residual paths; this
  is the exclusion the second adversarial review pass proved correct.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from control_plane.executive_steward import (
    AttentionFact,
    BlockerFact,
    EffectState,
    ExecutiveStewardSnapshot,
    Freshness,
    QueryStatus,
    RuntimeFact,
    Seat,
    SourceOwner,
    SourceRef,
    StewardResult,
)

#: Schema version of the document this module emits.
SCHEMA = "mastermind.autonomy_control_room.v1"

#: Closed set of top-level output keys (frozen spec §2).
OUTPUT_KEYS = frozenset({
    "schema", "generated_at", "responsibilities", "owed_by_seat",
    "chairman_decisions", "source_failures", "issues", "counts",
})

#: Every legal ``owed_turn.seat`` / ``owed_by_seat`` bucket, including the
#: non-Seat-enum ``"unknown"`` fallback (frozen spec §4.2 rule 4).
_OWED_SEATS = ("chairman", "ceo", "coo", "worker", "unknown")

#: Total order for ``responsibilities`` sorting (frozen spec §5).
_SEAT_RANK = {"chairman": 0, "ceo": 1, "coo": 2, "worker": 3, "unknown": 4}

#: Total order for freshness "weakest wins" (frozen spec §4.1).
_FRESHNESS_RANK = {
    Freshness.UNKNOWN.value: 0,
    Freshness.STALE.value: 1,
    Freshness.CURRENT.value: 2,
}

#: The three ``ObligationStatus`` tokens a Wake-owned attention fact's
#: ``kind`` may literally carry (canonical: ``wake_ledger.py`` lines 62-64;
#: ``LedgerPhase``/``ObligationStatus`` are not redefinitions of anything
#: Law #2 names — they are simply not imported, only their three wire
#: string values are repeated here as plain constants).
WAKE_OUTCOME_TOKENS = frozenset({
    "DELIVERED_UNACKNOWLEDGED", "TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED",
})

#: The six placement tokens the frozen spec (§4.3, as amended by the Phase A
#: repair packet) says have "no canonical producer in the repository at this
#: base" — legal ONLY when an attention/blocker fact literally carries one;
#: never derived, never inferred from an invented convention.
#: ``WAITING_CAPACITY`` lives here (not behind a separate "capacity code"
#: heuristic) — see module docstring "corrections to the frozen spec".
_NO_PRODUCER_PLACEMENT_TOKENS = frozenset({
    "ELIGIBLE_CANDIDATE_OBSERVED",
    "ATTEMPT_WORKER_RUNTIMEBINDING_COMMITTED",
    "ACTIVATION_REQUESTED",
    "ACTIVATION_CONFIRMED",
    "ACTIVATION_REFUSED_PRE_SUBMIT",
    "WAITING_CAPACITY",
})

#: Steward issue codes emitted only when ``fact.effect_state is
#: EffectState.EFFECT_UNKNOWN`` (``get_current_runtime`` lines ~894-907;
#: ``explain_blocker`` lines ~1022-1035).  Shared literal, not imported,
#: because it is not a public constant of ``executive_steward``.
_RECONCILIATION_REQUIRED = "reconciliation_required"

#: Steward issue codes that indicate two *distinct* facts joined the same
#: query and neither could be preferred — see module docstring point 3.
_AMBIGUOUS_ISSUE_FIELD = {
    "ambiguous_responsibility_join": "responsibility",
    "ambiguous_attention_identity": "attention",
    "ambiguous_attention_responsibility_join": "attention",
    "ambiguous_runtime_join": "runtime",
    "ambiguous_blocker_join": "blocker",
    "ambiguous_surface_join": "surface",
}

#: Steward issue codes that mean, on their own, only "no matching fact and
#: nothing else is wrong" — a normal, common state (module docstring point
#: 6), never a real problem worth surfacing on the top-level ``issues`` list.
#: These three are the exact codes ``get_current_runtime`` (WORKER + CEO
#: seats), ``explain_blocker`` and ``resolve_surface`` each emit in their
#: routine-absence branch.
_ROUTINE_ABSENCE_ISSUE_CODES = frozenset({
    "surface_unknown", "runtime_unknown", "blocker_unknown",
})

#: NOTE (Phase A repair packet, Repair A, 2026-09-01): there is
#: deliberately no fixed allowlist of "stale_*" issue codes here any more.
#: The Steward's ambiguity/mismatch/reconciliation checks run BEFORE its
#: own staleness check on several call paths, so an eight-code allowlist
#: of "stale_*" codes under-folded five residual paths (reconciliation_
#: required, ambiguous_runtime_join, ambiguous_blocker_join,
#: runtime_root_mismatch, ambiguous_attention_identity) that report
#: genuinely stale evidence under a non-"stale_*" code.  The freshness fold
#: at the ``project_autonomy`` call site now folds every Steward-internal
#: issue's sources by EXCLUSION instead: skip an issue whose ``code`` is a
#: caller-authored ``SourceFailure`` echo (``code in source_failure_codes``
#: — see module docstring point 7) and skip any issue raised by
#: ``resolve_surface`` (module docstring point 5's surface carve-out).

#: Query-status severity, worst wins (frozen spec §4.4 treats ok/degraded as
#: "fine" and unknown/refused as blocking, so refused is the worst).
_QUERY_RANK = {
    QueryStatus.OK.value: 0,
    QueryStatus.DEGRADED.value: 1,
    QueryStatus.UNKNOWN.value: 2,
    QueryStatus.REFUSED.value: 3,
}


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------

def _source_key(source: SourceRef) -> tuple[str, str, str, str]:
    return (source.owner.value, source.ref, source.observed_at or "", source.freshness.value)


def _receipt(source: SourceRef) -> dict[str, Any]:
    return {
        "owner": source.owner.value,
        "ref": source.ref,
        "observed_at": source.observed_at,
        "freshness": source.freshness.value,
    }


def _receipts_sorted(sources: set[SourceRef] | list[SourceRef]) -> list[dict[str, Any]]:
    return [_receipt(s) for s in sorted(set(sources), key=_source_key)]


def _combine_status(statuses: list[QueryStatus]) -> QueryStatus:
    worst = QueryStatus.OK
    worst_rank = -1
    for status in statuses:
        rank = _QUERY_RANK[status.value]
        if rank > worst_rank:
            worst_rank = rank
            worst = status
    return worst


def _neutral_if_routine_absence(result: StewardResult) -> QueryStatus:
    """Treat a bare, source-issue-free ``UNKNOWN`` as neutral (module docstring point 6).

    ``get_current_runtime`` and ``explain_blocker`` return ``UNKNOWN`` in
    exactly one shape: no matching fact AND no relevant ``source_failures``
    (``executive_steward.py`` — e.g. lines 846-859 / 984-997: "if
    source_issues: DEGRADED else UNKNOWN").  That is a completely routine,
    healthy state — "no blocker exists" / "nobody is the current CEO
    target" — not a query problem.  Genuinely bad situations (an actual
    source failure, an ambiguous join, a reconciliation requirement) are
    already DEGRADED or REFUSED, which this function passes through
    unchanged.  Folding a routine UNKNOWN into the card's combined
    ``query_status`` would make ``is_actionable`` (§4.4) nearly
    unreachable — nearly every real card lacks either a CEO target or a
    blocker — so this module does not.
    """
    return QueryStatus.OK if result.status is QueryStatus.UNKNOWN else result.status


class _CardIssues:
    """Accumulates ``StewardResult.issues`` tagged with a responsibility_ref.

    Routine-absence codes (:data:`_ROUTINE_ABSENCE_ISSUE_CODES`) are dropped
    at the source: they are not real problems (module docstring point 6),
    so the same judgment ``query_status`` already applies to them is applied
    here too, instead of surfacing them as noise on the top-level ``issues``
    list.

    That drop is scoped to a genuinely routine absence only (Phase A repair
    packet, Repair B, 2026-09-01): a caller-authored ``SourceFailure`` whose
    free-text ``code`` happens to collide with one of the three routine-
    absence tokens (e.g. ``SourceFailure(owner=EXECUTIVE_OS,
    code="runtime_unknown", ...)`` echoed back through ``_source_issues``)
    is a real outage, not an absence, and must reach ``issues`` — the same
    ``code not in source_failure_codes`` guard the ``EFFECT_UNKNOWN`` fix
    already uses (module docstring point 2).  ``source_failure_codes`` is
    supplied at construction, once per :func:`project_autonomy` call.
    """

    def __init__(self, source_failure_codes: frozenset[str]) -> None:
        self.rows: list[dict[str, Any]] = []
        self._source_failure_codes = source_failure_codes

    def _is_routine_absence(self, code: str) -> bool:
        return code in _ROUTINE_ABSENCE_ISSUE_CODES and code not in self._source_failure_codes

    def fold(self, ref: str | None, result: StewardResult) -> None:
        for issue in result.issues:
            if self._is_routine_absence(issue.code):
                continue
            self.rows.append({
                "responsibility_ref": ref,
                "code": issue.code,
                "message": issue.message,
                "sources": _receipts_sorted(list(issue.sources)),
            })

    def fold_untagged(self, result: StewardResult) -> None:
        """Fold issues with no explicit call-site ref (snapshot-wide calls).

        ``responsibility_ref`` is always ``None`` here — inferring identity
        from a Steward issue's free-text ``message`` is forbidden outright
        (Steward messages may be caller free text; see ``explain_blocker``
        folding ``SourceFailure.explanation`` verbatim into an issue).
        """
        for issue in result.issues:
            if self._is_routine_absence(issue.code):
                continue
            self.rows.append({
                "responsibility_ref": None,
                "code": issue.code,
                "message": issue.message,
                "sources": _receipts_sorted(list(issue.sources)),
            })


def _issue_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (row.get("responsibility_ref") or "", row["code"], row["message"])


def _dedupe_issue_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop exact-duplicate issue rows (frozen spec repair packet, Repair 7).

    The same caller-authored ``SourceFailure`` is folded once per call site
    that consults its owner (``get_responsibility``, both
    ``get_current_runtime`` seats, ``explain_blocker``, ``get_attention``,
    every ``resolve_surface`` role) — one real problem must read as one row,
    not once per internal call shape.  Two rows are the same problem when
    their ``responsibility_ref``, ``code``, ``message`` and receipts all
    match exactly; a snapshot-wide (``responsibility_ref is None``) row is
    never conflated with a per-card one, since callers legitimately want
    both scopes named.
    """
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row["responsibility_ref"],
            row["code"],
            row["message"],
            tuple(
                (s["owner"], s["ref"], s["observed_at"], s["freshness"])
                for s in row["sources"]
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# runtime -> CurrentWorker / SolTarget shape
# ---------------------------------------------------------------------------

def _runtime_card(fact: RuntimeFact) -> dict[str, Any]:
    return {
        "worker_id": fact.worker_id,
        "attempt_id": fact.attempt_id,
        "status": fact.status,
        "session_alias": fact.session_alias,
        "runtime_binding_id": fact.runtime_binding_id,
        "binding_generation": fact.binding_generation,
        "continuation_state": fact.continuation_state,
        "effect_state": fact.effect_state.value,
        "capacity_state": fact.capacity_state.value,
        "previous_attempt_id": fact.previous_attempt_id,
        "movement_reason_code": fact.movement_reason_code,
    }


def _runtime_sources(fact: RuntimeFact) -> tuple[SourceRef, SourceRef]:
    return (fact.executive_source, fact.binding_source)


def _blocker_card(fact: BlockerFact) -> dict[str, Any]:
    return {
        "code": fact.code,
        "explanation": fact.explanation,
        "target_seat": fact.target_seat.value,
        "effect_state": fact.effect_state.value,
    }


# ---------------------------------------------------------------------------
# classifiers (frozen spec §4)
# ---------------------------------------------------------------------------

def _weakest_freshness(sources: set[SourceRef]) -> str:
    if not sources:
        return Freshness.UNKNOWN.value
    return min(sources, key=lambda s: _FRESHNESS_RANK[s.freshness.value]).freshness.value


def _classify_owed_turn(
    *,
    blocker: dict[str, Any] | None,
    blocker_fact: BlockerFact | None,
    attention_facts: tuple[AttentionFact, ...],
    current_worker: dict[str, Any] | None,
    current_worker_fact: RuntimeFact | None,
) -> dict[str, Any]:
    """Frozen spec §4.2 — evaluated in order, first match wins."""
    if blocker is not None and blocker_fact is not None:
        return {
            "seat": blocker_fact.target_seat.value,
            "reason": "blocker_targets_seat",
            "source_refs": _receipts_sorted([blocker_fact.source]),
        }
    if attention_facts:
        winner = min(
            attention_facts, key=lambda f: (f.attention_id, _source_key(f.source))
        )
        return {
            "seat": winner.target_seat.value,
            "reason": "attention_targets_seat",
            "source_refs": _receipts_sorted([winner.source]),
        }
    if current_worker is not None and current_worker_fact is not None:
        # See module docstring / DEVIATIONS: RuntimeFact.status is
        # unconstrained free text with no canonical terminal/non-terminal
        # partition reachable from executive_steward.py — the Steward
        # exposes no terminal partition for RuntimeFact.status, so this
        # module never asserts the runtime is ACTIVE.  "current worker
        # runtime exists" (the one part of this rule the Steward API can
        # actually answer) is what gates this branch, and the reason code
        # names presence, never activity.
        return {
            "seat": "worker",
            "reason": "worker_runtime_present",
            "source_refs": _receipts_sorted(list(_runtime_sources(current_worker_fact))),
        }
    return {"seat": "unknown", "reason": "no_owed_turn_signal", "source_refs": []}


def _classify_placement(
    *,
    current_worker_cw_result: StewardResult,
    current_worker: dict[str, Any] | None,
    wake_outcome: str,
    blocker_fact: BlockerFact | None,
    attention_facts: tuple[AttentionFact, ...],
    source_failure_codes: frozenset[str],
) -> dict[str, Any]:
    """Frozen spec §4.3 (as amended by the Phase A repair packet).

    EFFECT_UNKNOWN note (genuine Steward/spec mismatch — see DEVIATIONS):
    the spec says this token is derived from "current worker `effect_state
    == effect_unknown`", but ``get_current_runtime`` (executive_steward.py
    lines 894-907) UNCONDITIONALLY returns ``REFUSED`` with ``data=None``
    whenever the matched ``RuntimeFact.effect_state is
    EffectState.EFFECT_UNKNOWN`` — so ``current_worker`` (this module's
    ``CurrentWorker`` field, sourced from that same call's ``.data``) can
    structurally never carry ``effect_state == "effect_unknown"``.  The only
    Steward-API-sanctioned signal that this happened is the call's own
    ``status == REFUSED`` plus a ``reconciliation_required`` issue — both
    read from ``StewardResult.status``/``.issues``, which §3's last table
    row explicitly permits.  This module uses that signal instead of the
    (unreachable) literal field read the spec's prose describes.

    That signal is NOT trustworthy on its own: ``explain_blocker``'s and
    ``get_current_runtime``'s ``_source_issues`` folding
    (``executive_steward.py`` lines 532-537) copies every matching
    caller-authored ``SourceFailure.code`` straight into ``.issues`` — a
    caller whose ``SourceFailure.code`` happens to equal
    ``"reconciliation_required"`` (for a reason unrelated to this exact
    runtime fact) can ride along on any ``REFUSED`` result that appends
    ``source_issues`` (e.g. ``ambiguous_runtime_join``,
    ``runtime_root_mismatch``).  ``source_failure_codes`` — the set of codes
    the caller supplied via ``snapshot.source_failures`` — excludes that
    case: a snapshot containing no fact with ``EffectState.EFFECT_UNKNOWN``
    anywhere must never produce placement ``EFFECT_UNKNOWN``.
    """
    if (
        current_worker is None
        and current_worker_cw_result.status is QueryStatus.REFUSED
        and _RECONCILIATION_REQUIRED not in source_failure_codes
        and any(i.code == _RECONCILIATION_REQUIRED for i in current_worker_cw_result.issues)
    ):
        return {"value": "EFFECT_UNKNOWN", "observable": True, "reason": "worker_effect_unknown"}
    elif current_worker is not None and current_worker["effect_state"] == EffectState.EFFECT_UNKNOWN.value:
        # Structural guarantee documented above: get_current_runtime never
        # hands back a RuntimeFact whose effect_state is EFFECT_UNKNOWN.
        # A contract violation here means the Steward's own invariant broke
        # — never silently continue past it, and never let ``python -O``
        # turn this into a no-op.
        raise RuntimeError(
            "get_current_runtime returned a RuntimeFact with effect_state "
            "== EFFECT_UNKNOWN; this violates the documented Steward "
            "contract this module relies on (see _classify_placement "
            "docstring)."
        )

    if wake_outcome in WAKE_OUTCOME_TOKENS:
        return {"value": wake_outcome, "observable": True, "reason": "wake_outcome_supplied"}

    literal_tokens: list[str] = []
    if blocker_fact is not None and blocker_fact.code in _NO_PRODUCER_PLACEMENT_TOKENS:
        literal_tokens.append(blocker_fact.code)
    literal_tokens.extend(
        f.kind for f in attention_facts if f.kind in _NO_PRODUCER_PLACEMENT_TOKENS
    )
    if literal_tokens:
        return {
            "value": sorted(literal_tokens)[0],
            "observable": True,
            "reason": "fact_literal_token",
        }

    return {"value": "not_observable", "observable": False, "reason": "no_canonical_producer"}


def _classify_wake_outcome(attention_facts: tuple[AttentionFact, ...]) -> str:
    candidates = [
        f for f in attention_facts
        if f.source.owner is SourceOwner.WAKE and f.kind in WAKE_OUTCOME_TOKENS
    ]
    if not candidates:
        return "not_observable"
    winner = min(candidates, key=lambda f: (f.attention_id, _source_key(f.source)))
    return winner.kind


def _classify_disagreements(attention_facts: tuple[AttentionFact, ...]) -> list[dict[str, Any]]:
    """Frozen spec §4.6 — see module docstring point 3 for scope.

    The only Steward-exposed shape where two distinct, independently
    retrievable facts can carry different values for "the same field" on
    one responsibility is two ``AttentionFact`` rows (different
    ``attention_id``) whose ``kind`` both fall in ``WAKE_OUTCOME_TOKENS`` but
    disagree.  This applies the SAME ``SourceOwner.WAKE`` owner gate
    :func:`_classify_wake_outcome` already applies — without it, two
    non-WAKE-owned attention facts could produce a ``wake_outcome``
    disagreement even while ``wake_outcome`` itself reads
    ``"not_observable"`` (only WAKE-owned facts are eligible to populate
    that field at all), which would report a field as simultaneously not
    observable and in dispute.
    """
    matching = [
        f for f in attention_facts
        if f.source.owner is SourceOwner.WAKE and f.kind in WAKE_OUTCOME_TOKENS
    ]
    distinct_values = sorted({f.kind for f in matching})
    if len(distinct_values) > 1:
        return [{
            "field": "wake_outcome",
            "values": distinct_values,
            "sources": _receipts_sorted([f.source for f in matching]),
        }]
    return []


def _classify_actionability(
    *,
    freshness: str,
    query_status: str,
    owed_turn_seat: str,
    card_issue_codes: list[str],
    source_failure_codes: frozenset[str],
) -> tuple[bool, str]:
    """Frozen spec §4.4."""
    is_actionable = (
        freshness == Freshness.CURRENT.value
        and query_status in (QueryStatus.OK.value, QueryStatus.DEGRADED.value)
        and owed_turn_seat != "unknown"
    )
    if is_actionable:
        return True, "actionable"
    if freshness == Freshness.STALE.value:
        return False, "stale_history"
    if freshness == Freshness.UNKNOWN.value:
        return False, "freshness_unknown"
    if query_status in (QueryStatus.REFUSED.value, QueryStatus.UNKNOWN.value):
        if any(code in source_failure_codes for code in card_issue_codes):
            return False, "source_failure"
        return False, "query_refused"
    if owed_turn_seat == "unknown":
        return False, "no_owed_turn_signal"
    return False, "query_refused"  # pragma: no cover - defensive fallback


# ---------------------------------------------------------------------------
# the pure projection
# ---------------------------------------------------------------------------

def project_autonomy(
    snapshot: ExecutiveStewardSnapshot,
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Pure, deterministic projection of one Executive Steward snapshot.

    No I/O, no subprocess, no clock read, no environment read, no
    randomness.  ``generated_at`` is injected, never read from a clock.
    Calling this twice with the same arguments produces byte-identical
    ``json.dumps(doc, sort_keys=True)`` output.
    """
    source_failure_codes = frozenset(f.code for f in snapshot.source_failures)

    issues = _CardIssues(source_failure_codes)

    list_result = snapshot.list_responsibilities()
    issues.fold_untagged(list_result)
    membership = tuple(list_result.data) if list_result.data else ()

    responsibilities: list[dict[str, Any]] = []
    owed_by_seat = {seat: 0 for seat in _OWED_SEATS}

    for fact in membership:
        ref = fact.responsibility_ref

        gr = snapshot.get_responsibility(ref)
        issues.fold(ref, gr)
        # ``ref`` is a member of ``membership`` (list_responsibilities()
        # already resolved it to exactly one candidate), so get_responsibility
        # is guaranteed to answer with that same single fact as `.data`
        # (never None) — see docstring point re: ambiguous refs never
        # reaching membership in the first place.
        identity = gr.data if gr.data is not None else fact

        cw_result = snapshot.get_current_runtime(ref, Seat.WORKER)
        issues.fold(ref, cw_result)
        current_worker_fact = cw_result.data if isinstance(cw_result.data, RuntimeFact) else None
        current_worker = _runtime_card(current_worker_fact) if current_worker_fact else None

        st_result = snapshot.get_current_runtime(ref, Seat.CEO)
        issues.fold(ref, st_result)
        current_sol_target_fact = st_result.data if isinstance(st_result.data, RuntimeFact) else None
        current_sol_target = _runtime_card(current_sol_target_fact) if current_sol_target_fact else None

        bl_result = snapshot.explain_blocker(ref)
        issues.fold(ref, bl_result)
        blocker_fact = bl_result.data if isinstance(bl_result.data, BlockerFact) else None
        blocker = _blocker_card(blocker_fact) if blocker_fact else None

        at_result = snapshot.get_attention(responsibility_ref=ref)
        issues.fold(ref, at_result)
        attention_facts: tuple[AttentionFact, ...] = (
            tuple(at_result.data) if at_result.data else ()
        )

        # surfaces / receipts "where available" — informational only, never
        # gates query_status, is_actionable, or freshness (module docstring
        # points 5 and 7).  A resolve_surface issue is folded into `issues`
        # here (so it still appears as a receipt/problem row) but — unlike
        # gr/cw_result/st_result/bl_result/at_result below — is deliberately
        # NOT retained for the freshness fold: no `surf_results` list is
        # kept, so there is nothing for that loop to accidentally consult.
        surface_sources: list[SourceRef] = []
        for role in (Seat.CHAIRMAN, Seat.CEO, Seat.COO, Seat.WORKER):
            surf_result = snapshot.resolve_surface(ref, role)
            issues.fold(ref, surf_result)
            if surf_result.data is not None:
                surface_sources.append(surf_result.data.source)

        # --- classifiers -----------------------------------------------
        contributing_sources: set[SourceRef] = {identity.source}
        if current_worker_fact is not None:
            contributing_sources.update(_runtime_sources(current_worker_fact))
        if current_sol_target_fact is not None:
            contributing_sources.update(_runtime_sources(current_sol_target_fact))
        if blocker_fact is not None:
            contributing_sources.add(blocker_fact.source)
        contributing_sources.update(f.source for f in attention_facts)
        contributing_sources.update(surface_sources)

        # Stale (or otherwise problem-flagged) evidence a steward call
        # REFUSED/DEGRADED to hand back as `.data` (e.g. `stale_runtime_
        # join`, whose sources are the stale `executive_source`/
        # `binding_source` on a real RuntimeFact; or `reconciliation_
        # required`/`ambiguous_runtime_join`/`ambiguous_blocker_join`/
        # `runtime_root_mismatch`/`ambiguous_attention_identity`, whose
        # ambiguity/mismatch/reconciliation checks all run BEFORE the
        # Steward's own staleness check on that same call path) is still
        # available on that call's own `.issues` — fold it in so
        # `_weakest_freshness` can see it (Repair 2, extended by the Phase A
        # repair packet's Repair A, 2026-09-01: a fixed `stale_*` allowlist
        # left exactly those five ambiguity/mismatch/reconciliation paths
        # reporting genuinely stale evidence as `freshness: "current"`, so
        # the rule is now the complement — fold EVERY issue's sources
        # except two carve-outs).  Excludes:
        #   (a) an issue whose `code` also appears in `source_failure_codes`
        #       — a caller-authored echo of a free-text `SourceFailure.code`
        #       (`SourceFailure.as_source()` hardcodes `Freshness.UNKNOWN`),
        #       never per-card fact evidence.  Every card consults every
        #       owner on every call (`_source_issues`), so folding these
        #       would poison every card's freshness whenever any owner
        #       fails anywhere, defeating the "bounded" partial-source-
        #       failure guarantee (frozen spec §6 state 12).
        #   (b) ANY issue raised by `resolve_surface` (no such result is
        #       retained above, so the loop below has nothing to consult) —
        #       a surface binding is a navigation receipt, not evidence of
        #       the responsibility's own work state (module docstring
        #       point 5); a stale or
        #       unreviewed *saved destination* (`surface_not_reviewed`,
        #       `stale_surface_binding`, ...) must never drive a card whose
        #       actual work evidence is current down to `freshness:
        #       "stale"`.  Surface issues still appear in `issues` and in
        #       `source_receipts` via `issues.fold(ref, surf_result)` above
        #       — just not here.
        for result in (gr, cw_result, st_result, bl_result, at_result):
            for issue in result.issues:
                if issue.code in source_failure_codes:
                    continue
                contributing_sources.update(issue.sources)

        freshness = _weakest_freshness(contributing_sources)

        query_status = _combine_status([
            gr.status,
            _neutral_if_routine_absence(cw_result),
            _neutral_if_routine_absence(st_result),
            _neutral_if_routine_absence(bl_result),
            at_result.status,
        ]).value

        owed_turn = _classify_owed_turn(
            blocker=blocker,
            blocker_fact=blocker_fact,
            attention_facts=attention_facts,
            current_worker=current_worker,
            current_worker_fact=current_worker_fact,
        )

        wake_outcome = _classify_wake_outcome(attention_facts)

        placement_state = _classify_placement(
            current_worker_cw_result=cw_result,
            current_worker=current_worker,
            wake_outcome=wake_outcome,
            blocker_fact=blocker_fact,
            attention_facts=attention_facts,
            source_failure_codes=source_failure_codes,
        )

        disagreements = _classify_disagreements(attention_facts)

        card_issue_codes = [row["code"] for row in issues.rows if row["responsibility_ref"] == ref]
        is_actionable, actionability_reason = _classify_actionability(
            freshness=freshness,
            query_status=query_status,
            owed_turn_seat=owed_turn["seat"],
            card_issue_codes=card_issue_codes,
            source_failure_codes=source_failure_codes,
        )

        # Frozen spec §4.5 (as amended by the Phase A repair packet): the
        # mere PRESENCE of a current_worker is never treated as an
        # automatic actor — a crashed or completed runtime is present too,
        # and the Steward exposes no terminal partition for
        # RuntimeFact.status (see _classify_owed_turn).  The only automatic
        # actor this module can actually prove is a CEO/COO-targeted
        # attention fact on the card; absent that, an owed_turn targeting
        # the Chairman is a Chairman decision.  Under-suppressing here is
        # the safe direction — silently hiding a Chairman decision behind
        # an unprovable "a worker is handling it" is not.
        chairman_decision_required = (
            owed_turn["seat"] == "chairman"
            and not any(f.target_seat in (Seat.CEO, Seat.COO) for f in attention_facts)
        )
        if chairman_decision_required and current_worker is not None:
            # A runtime IS present, but its liveness is unprovable (no
            # terminal/non-terminal partition on RuntimeFact.status) — name
            # that uncertainty explicitly rather than implying nobody is
            # there.
            chairman_decision_reason = (
                "owed_turn_targets_chairman_with_unprovable_runtime_liveness:"
                f"{owed_turn['reason']}"
            )
        elif chairman_decision_required:
            chairman_decision_reason = (
                f"owed_turn_targets_chairman_with_no_automatic_actor:{owed_turn['reason']}"
            )
        else:
            chairman_decision_reason = None

        owed_by_seat[owed_turn["seat"]] += 1

        card = {
            "responsibility_ref": ref,
            "title": identity.title,
            "accountable_seat": identity.accountable_seat.value,
            "state": identity.state,
            "root_job_id": identity.root_job_id,
            "current_worker": current_worker,
            "current_sol_target": current_sol_target,
            "owed_turn": owed_turn,
            "placement_state": placement_state,
            "wake_outcome": wake_outcome,
            "blocker": blocker,
            "freshness": freshness,
            "is_actionable": is_actionable,
            "actionability_reason": actionability_reason,
            "chairman_decision_required": chairman_decision_required,
            "chairman_decision_reason": chairman_decision_reason,
            "disagreements": disagreements,
            "source_receipts": _receipts_sorted(contributing_sources),
            "query_status": query_status,
        }
        responsibilities.append(card)

    responsibilities.sort(
        key=lambda c: (
            0 if c["chairman_decision_required"] else 1,
            0 if c["is_actionable"] else 1,
            _SEAT_RANK[c["owed_turn"]["seat"]],
            c["responsibility_ref"],
        )
    )

    chairman_decisions = sorted(
        c["responsibility_ref"] for c in responsibilities if c["chairman_decision_required"]
    )

    source_failure_rows = sorted(
        (
            {
                "owner": f.owner.value,
                "code": f.code,
                "explanation": f.explanation,
                "source_ref": f.source_ref,
                "observed_at": f.observed_at,
            }
            for f in snapshot.source_failures
        ),
        key=lambda row: (row["owner"], row["code"], row["source_ref"]),
    )

    issue_rows = sorted(_dedupe_issue_rows(issues.rows), key=_issue_sort_key)

    # Repair 9: zero cards means EITHER the organization is genuinely idle
    # OR membership was suppressed (an ambiguous responsibility join, or a
    # total Agent OS outage) — "we cannot see" must never read as
    # indistinguishable from "nothing to do".  `list_result.issues` is
    # non-empty in exactly the suppression case (an ambiguous join excluded
    # from `selected`, or an AGENT_OS `SourceFailure` folded in
    # unconditionally by `_source_issues`) and empty in the genuinely-idle
    # case, so it is the exact signal to gate on.
    membership_suppressed = bool(list_result.issues)
    counts = {
        "total": len(responsibilities),
        "actionable": sum(1 for c in responsibilities if c["is_actionable"]),
        "stale": sum(1 for c in responsibilities if c["freshness"] == Freshness.STALE.value),
        "blocked": sum(1 for c in responsibilities if c["blocker"] is not None),
        "empty": len(responsibilities) == 0 and not membership_suppressed,
    }

    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "responsibilities": responsibilities,
        "owed_by_seat": owed_by_seat,
        "chairman_decisions": chairman_decisions,
        "source_failures": source_failure_rows,
        "issues": issue_rows,
        "counts": counts,
    }
    if set(doc.keys()) != OUTPUT_KEYS:
        raise RuntimeError(
            f"project_autonomy produced key set {sorted(doc.keys())}, "
            f"expected {sorted(OUTPUT_KEYS)} — this is a contract "
            "violation, not a degraded-data condition."
        )
    return doc


__all__ = ["SCHEMA", "OUTPUT_KEYS", "WAKE_OUTCOME_TOKENS", "project_autonomy"]
