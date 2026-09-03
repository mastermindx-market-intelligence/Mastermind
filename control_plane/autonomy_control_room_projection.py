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
Fix 3 (adversarial-review repair packet, 2026-09-01) adds one narrow second
exception, in the SAME spirit as the ``source_failures`` one: a bare
existence check of ``snapshot.runtimes`` by ``responsibility_ref``/``seat``,
used only by :func:`_neutral_if_routine_absence`'s ``has_runtime_evidence``
parameter to verify — rather than assume — that a ``root_job_id``-less
responsibility genuinely has no runtime evidence at all, since
``get_current_runtime`` structurally cannot answer that question itself
once ``root_job_id`` is ``None`` (see that function's own docstring for the
full account).  This checks bare presence only — never seat-vs-root
matching, never candidate selection, never any of the join semantics
``get_current_runtime`` itself owns — so it does not duplicate Steward
logic, only answer a question the Steward's own short-circuit cannot.
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
   2) applies here too.  A second, narrower repair packet (2026-09-01,
   Change A) extends :func:`_neutral_if_routine_absence` itself (not
   :data:`_ROUTINE_ABSENCE_ISSUE_CODES`) to also neutralize a
   ``get_current_runtime`` result whose *only* issue is
   ``runtime_root_missing`` — the routine "this Agent-OS-owned
   responsibility has no Executive root job" absence — while leaving that
   issue on the top-level ``issues`` list as a receipt and leaving every
   other REFUSED (``reconciliation_required``/EFFECT_UNKNOWN, every
   ``ambiguous_*`` join, ``runtime_root_mismatch``, or
   ``runtime_root_missing`` alongside any other issue) refusing exactly as
   before.  See that function's docstring for the exact guard.
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

Real-data mapper — ``build_autonomy_snapshot`` (Phase A wiring packet,
2026-09-01)
------------------------------------------------------------------------
:func:`build_autonomy_snapshot` is a second pure public function, added by
the packet that wires this projection to real Chairman Control Room data.
It takes the exact same already-gathered plain-data inputs
:func:`control_plane.chairman_control_room.compose_control_room` itself
receives (``inbox``, ``boot_packet``, ``active_builds``, ``agent_os_state``,
``runtime_jobs``, ``bindings``) and returns one
:class:`~control_plane.executive_steward.ExecutiveStewardSnapshot`.  Same
truthfulness law as the rest of this module: no I/O, no subprocess, no
clock read, no environment read, no randomness, no mutation of inputs — and
a fact is constructed only when every one of its required fields is
genuinely present in the handed input; otherwise it is omitted and, where
the gap is a systemic one rather than a single missing row, recorded as a
:class:`~control_plane.executive_steward.SourceFailure` instead.

:func:`declared_blockers_from_agent_os_state` is a third pure public
function, added by a bug-fix packet (2026-09-01) that removes a false
attribution the prior revision of this mapper committed — see the
"BlockerFact is NEVER built" bullet under point 8 below for the full
account.  It returns plain data (never a Steward fact), keyed by
``responsibility_ref``, meant to be handed to :func:`project_autonomy`'s
``declared_blockers`` parameter so each card can honestly carry a
``declared_blocker`` field alongside — never merged into — the
Steward-owned ``blocker`` field.

Two more documented interpretive decisions (evaluated against the real
input shapes: ``tests/fixtures/chairman_control_room/*.json`` and, for the
one genuinely cross-repo question below, Macro's own
``agentos/workstreams/*.md`` ``owner:`` front matter):

8. **``ResponsibilityFact`` IS constructed here, from
   ``agent_os_state["workstreams"][]`` rows' own structured fields;
   ``BlockerFact`` is NEVER constructed from this source — ``RuntimeFact``
   is still never constructed either (bug-fix packet, 2026-09-01,
   correcting the prior revision of this note, which wrongly claimed a
   ``BlockerFact`` was built here too).**
   Verified against the real compiled artifact this mapper's caller
   actually hands it (Macro's ``data/governance/agent_os_state.json``,
   47 rows as of 2026-09-01) rather than only
   ``tests/fixtures/chairman_control_room/agent_os_state_v1.json`` (whose
   thin three-row shape — ``key``/``title``/``status``/``program``/
   ``next_action`` only — is a test fixture, not evidence the real field
   is absent):
   * ``agent_os_state.v1``'s ``workstreams[]`` rows carry ``owner``
     (closed-ish token in practice, but read here as arbitrary text —
     see below), ``blocked_by`` (a list of structured blocker-reference
     strings), and ``needs_ceo``, in addition to ``key``/``title``/
     ``status``/``generated_at``.  A ``ResponsibilityFact`` is built from
     ``key``/``title``/``status`` plus a seat derived from ``owner``
     through the EXACT, CLOSED, case-sensitive
     :data:`_ACCOUNTABLE_SEAT_BY_OWNER` token map — never a substring,
     regex, lowercase-normalize, strip, or fuzzy match.  Only four literal
     ``owner`` values are recognized (``"chairman"``, ``"ceo-sol"``,
     ``"coo-fable"``, ``"fable"``); every other value — ``"ops"``,
     ``"terminal-platform"``, ``"grok-cn-c"``, a missing/empty owner, and
     free-text sentences such as ``"Eval-OS session (COO Fable lane)"``
     (measured on the real artifact, 2026-09-01: 7 of 47 rows) — is
     deliberately NOT mapped, and NO ``ResponsibilityFact`` is built for
     that row: :func:`_responsibility_facts_from_agent_os_state` instead
     records one bounded, per-row PLAIN-DATA ``unmapped`` entry
     (``reason="owner_not_a_recognized_seat"``, not a ``SourceFailure`` —
     corrected by Fix 4 of the final adversarial review, 2026-09-01; the
     blast-radius repair packet deleted the ``SourceFailure``-per-row
     shape this docstring used to describe, since the Steward folds every
     ``SourceFailure`` into the issues of EVERY query it answers — see
     :func:`_responsibility_facts_from_agent_os_state`'s own docstring,
     "Fix 5"/"blast-radius repair packet" paragraphs, for the full
     account and the measured blast radius) naming the workstream key,
     never the raw owner text — treating an unrecognized-owner sentence
     as seat-shaped prose would be exactly the "derive ... seat ... from
     ... prose" the frozen spec forbids, even where the words "COO" or
     "Fable" happen to appear inside it.
   * A ``BlockerFact`` is NEVER built from ``agent_os_state`` data (bug-fix
     packet, 2026-09-01).  ``BlockerFact.__post_init__``
     (``executive_steward.py``) refuses any ``source.owner`` other than
     ``EXECUTIVE_OS``, ``EXECUTIVE_INBOX`` or ``WAKE`` — never
     ``AGENT_OS`` — so a row's own ``blocked_by`` genuinely cannot be
     represented as a ``BlockerFact`` without stamping it with an owner its
     own ``ref`` string (``agent_os_state.workstreams:<key>.blocked_by``)
     does not support.  The prior revision of this mapper did exactly
     that: it constructed a real ``BlockerFact`` and stamped
     ``source.owner = SourceOwner.EXECUTIVE_OS`` anyway — a false
     attribution, Agent OS data labelled as Executive OS data.  The lawful
     response to a contract that cannot carry a claim honestly is to
     decline the claim under that contract, not to relabel the owner so it
     fits.  :func:`declared_blockers_from_agent_os_state` represents the
     SAME real "workstream is blocked" signal instead, honestly, as plain
     data carrying its own true ``SourceOwner.AGENT_OS`` receipt — for
     :func:`project_autonomy`'s ``declared_blockers`` parameter to fold
     into each card's ``declared_blocker`` field, a field that is
     EXPLICITLY NOT the Steward-owned ``blocker`` field and must never be
     merged into it (different owners, different authority).  Its
     ``target_seat`` is ``"ceo"`` when the row's ``needs_ceo`` is literally
     ``True``; otherwise the SAME closed-token seat this mapper already
     derives for that row's ``owner`` (never re-derived from prose); and
     ``None`` — never guessed — when neither is available.  Unlike the
     deleted ``BlockerFact`` path, an unresolvable ``target_seat`` does NOT
     suppress the ``declared_blocker`` entry itself — only the seat, never
     the fact of the block, is withheld.  Getting that entry in front of the
     Chairman for an UNRECOGNIZED-owner row additionally requires Fix 2
     (adversarial-review repair packet, 2026-09-01): see
     :func:`declared_blockers_from_agent_os_state`'s own docstring for the
     corrected, two-surface account of how the block actually reaches the
     Chairman (a real card's ``declared_blocker`` field when the owner is
     recognized; an ``unmapped_responsibilities`` receipt otherwise).
   * ``ceo_brief.v1``'s ``readiness.records``/``blocked``/``finished`` rows
     (verified against ``_agent_os_workstreams`` and ``tests/fixtures/
     chairman_control_room/boot_packet_v1.json``) still carry no seat, no
     blocker code, no ``EffectState`` — this mapper never reads them for
     responsibility/blocker construction; they are unused here as before.
   * ``runtime_jobs`` rows are exactly ``job_id``/``status``/``workstream``
     (verified against ``control_plane.chairman_control_room.
     _read_runtime_jobs`` and ``_group_jobs_by_ref``) — nowhere near
     ``RuntimeFact``'s required ``attempt_id``/``worker_id``/
     ``session_alias``/``runtime_binding_id``/``binding_generation``/
     ``continuation_state``/``effect_state``/``capacity_state``/
     ``binding_source`` (``SourceOwner.RUNTIME_BINDING`` — a source this
     compositor never reads at all).  ``RuntimeFact`` is still never
     constructed by this mapper; ``current_worker``/``current_sol_target``
     stay genuinely null.
   * ``active_builds`` (open PRs) has no Steward fact type of its own — a
     GitHub PR is not a responsibility, attention, runtime, blocker, or
     surface fact in this vocabulary, and remains unread.
   * ``root_job_id`` on every constructed ``ResponsibilityFact`` is always
     ``None`` — no ``workstreams[]`` row carries any ``JOB-*``-shaped
     field, so there is never a genuine job reference to attach.
   A downstream effect worth naming plainly: because
   :func:`project_autonomy`'s card loop iterates
   ``snapshot.list_responsibilities()`` membership, a real, non-empty
   ``responsibilities`` tuple now means ``project_autonomy`` emits real
   populated cards from this mapper's snapshot, for every workstream row
   whose ``owner`` matched the closed token map.
9. **``SurfaceFact.reviewed_at`` is always ``None``** — deliberately, not
   an oversight.  ``control_plane.surface_bindings`` never emits any field
   matching the Steward's "a human/Chairman accepted this exact reviewed
   destination" review-acceptance concept; it emits only ``observed_at``
   (when the binding was recorded) and ``last_verified_at`` (a
   liveness/reachability check — verified against
   ``control_plane/surface_bindings.py``, which defines no ``reviewed_at``
   concept anywhere).  Treating ``last_verified_at`` as ``reviewed_at``
   would assert a review that never happened.  ``resolve_surface``
   therefore truthfully reports every surface this mapper constructs as
   ``surface_not_reviewed`` — a receipts-only, non-gating outcome (see
   point 5 above), never invented as "reviewed" it was never confirmed to
   be.
10. **Freshness for every constructed fact kind is a genuine, clock-free age
    comparison against an injected reference timestamp** (corrected by the
    adversarial-review repair packet, 2026-09-01, Fix 1 — this point
    previously claimed any non-empty ``observed_at`` reads ``CURRENT``,
    which meant a nine-day-old Agent OS artifact composed today read as
    "current" with zero stale cards; that was the exact failure the
    freshness law exists to prevent).  ``_freshness_for(observed_at,
    reference_at)`` takes the fact's own ``observed_at`` (``inbox[
    "generated_at"]`` for an attention fact; a binding row's own
    ``observed_at`` for a surface fact; ``agent_os_state["generated_at"]``
    for a responsibility fact or a declared blocker) and the caller-
    supplied ``reference_at`` — never a clock read, always
    ``project_autonomy``'s own ``generated_at``, threaded down through
    :func:`build_autonomy_snapshot` and every mapper helper.  ``CURRENT``
    when ``observed_at`` parses and is within :data:`FRESHNESS_BUDGET`
    (48h — two nightly cycles, see that constant) of ``reference_at``;
    ``STALE`` when it parses but is older; ``UNKNOWN`` (never fabricating
    an ``observed_at``... except the raw string is preserved when it
    genuinely exists but is merely unparseable or uncomparable — ``SourceRef``
    permits ``UNKNOWN`` with ``observed_at`` present) when ``observed_at``
    is absent, blank, unparseable, or ``reference_at`` itself cannot be
    parsed.  A further correction, Fix 1 of the FINAL adversarial review
    (2026-09-01): an ``observed_at`` sitting AHEAD of ``reference_at`` by
    more than :data:`FUTURE_SKEW_TOLERANCE` (one hour) also reads
    ``UNKNOWN``, never ``CURRENT`` — the prior revision of this fix bounded
    only the backward (staleness) side, leaving the forward side
    unbounded, so an artifact stamped in the far future (e.g. 2999-01-01)
    read ``CURRENT`` with ``counts["stale"]`` at zero.  Comparing two
    already-supplied timestamps is pure; this module still never reads a
    clock.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from control_plane.executive_steward import (
    AttentionFact,
    BlockerFact,
    EffectState,
    ExecutiveStewardSnapshot,
    Freshness,
    QueryStatus,
    ResponsibilityFact,
    RuntimeFact,
    Seat,
    SourceOwner,
    SourceRef,
    StewardResult,
    SurfaceFact,
)

#: Schema version of the document this module emits.
SCHEMA = "mastermind.autonomy_control_room.v1"

#: Closed set of top-level output keys (frozen spec §2).  ``unmapped_
#: responsibilities`` was added by the blast-radius repair packet,
#: 2026-09-01 (see :func:`unmapped_responsibilities_from_agent_os_state`) —
#: it is plain, bounded, per-row data and never a ``SourceFailure``.
OUTPUT_KEYS = frozenset({
    "schema", "generated_at", "responsibilities", "owed_by_seat",
    "chairman_decisions", "source_failures", "issues", "counts",
    "unmapped_responsibilities",
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


def _neutral_if_routine_absence(
    result: StewardResult,
    *,
    source_failure_codes: frozenset[str],
    has_runtime_evidence: bool,
) -> QueryStatus:
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

    Repair packet (2026-09-01, Change A) — a second, narrowly-scoped
    routine absence: ``get_current_runtime`` REFUSES with issue code
    ``runtime_root_missing`` whenever ``responsibility.root_job_id is
    None`` (``executive_steward.py`` lines ~823-835), unconditionally,
    before it ever looks at a seat's runtime candidates.  For an Agent
    OS-owned responsibility with no Executive root job — the ordinary
    case, since no Agent OS workstream row carries a job reference — that
    is the exact same shape as the routine UNKNOWN above: "no candidate
    and nothing else is wrong", just surfaced as REFUSED instead of
    UNKNOWN because the Steward's join check runs before it would ever
    reach the "no candidates" branch.  It is not a failed read: the
    responsibility, its owner, its state and its declared blocker are all
    read perfectly well by the calls this module makes; only "is there a
    recorded worker/CEO-target runtime" comes back unanswerable, and it is
    unanswerable for the same routine reason every such card is missing a
    runtime fact.  This is reclassified ONLY when it is the sole reason
    the result is not OK: ``result.status`` must be REFUSED, and
    ``result.issues`` must contain EXACTLY one issue, whose ``code`` is
    ``"runtime_root_missing"``.  Any other issue on the same result —
    a genuine source failure appended alongside it, an ambiguous join, a
    root mismatch, or a reconciliation requirement — means this is no
    longer the sole blocking signal, so the guard below leaves the result
    REFUSED exactly as before.  This never touches ``result.data`` (still
    ``None``, so ``current_worker``/``current_sol_target`` still read
    ``null``) and never touches the top-level ``issues`` list (the
    ``runtime_root_missing`` issue still folds in as a receipt via
    :class:`_CardIssues` — unlike :data:`_ROUTINE_ABSENCE_ISSUE_CODES`,
    this code is not added to that frozenset) — only the card's combined
    ``query_status`` (and, downstream, ``is_actionable``) changes.

    Fix 3 (adversarial-review repair packet, 2026-09-01) — tightening the
    ``runtime_root_missing`` guard above: ``executive_steward.py``'s
    ``get_current_runtime`` checks ``responsibility.root_job_id is None``
    UNCONDITIONALLY, before it ever inspects ``self.runtimes`` for a
    matching candidate (lines ~823-835) — so a responsibility with
    ``root_job_id=None`` that nevertheless has a genuine ``RuntimeFact``
    attached (including one whose ``effect_state`` is ``EFFECT_UNKNOWN``,
    which would otherwise REFUSE via ``reconciliation_required``) is
    INVISIBLE to that call: it always REFUSES with the SAME single
    ``runtime_root_missing`` issue as the truly-empty case, and the guard
    above — which cannot tell "genuinely no runtime evidence" apart from
    "a runtime IS attached but the join could not even be attempted" —
    used to neutralize both alike.  Unreachable through today's compositor
    (:func:`build_autonomy_snapshot` always passes ``runtimes=()``, module
    docstring point 8) but ``project_autonomy`` is a public API a future
    caller may hand a populated ``runtimes`` tuple to, so the premise this
    guard depends on ("every such card is genuinely missing a runtime
    fact") must be VERIFIED, not assumed.  ``has_runtime_evidence`` is
    that verification — a bare existence check, by ``responsibility_ref``
    and ``seat``, of whether ``snapshot.runtimes`` contains ANY fact for
    this exact card, computed once per call site in ``project_autonomy``'s
    loop.  This is the one narrow exception (mirroring the already-granted
    ``snapshot.source_failures`` exception, module docstring "Consume,
    never duplicate") to this module's rule against reading
    ``snapshot.runtimes`` directly: it is a plain existence check, never a
    re-implementation of ``get_current_runtime``'s own root-job-id/seat/
    candidate-selection join logic, so it does not duplicate anything the
    Steward already decides — it only answers the one question the
    Steward's own short-circuit structurally cannot: "is there evidence
    here at all". When ``has_runtime_evidence`` is ``True``, the guard
    below no longer neutralizes — the card stays REFUSED, exactly as a
    genuine ``reconciliation_required``/ambiguous-join REFUSED already
    does, because there IS something here that needs a human's attention,
    even though this specific call path cannot say what.

    Fix 4 (same repair packet) — the missing collision guard: this
    function's ``runtime_root_missing`` branch used to compare ONLY
    ``result.issues[0].code``, with no ``code not in source_failure_codes``
    check — unlike :meth:`_CardIssues._is_routine_absence`, which already
    guards its own routine-absence codes exactly that way (module
    docstring point 6's Repair B).  A caller-authored
    ``SourceFailure(code="runtime_root_missing", ...)`` anywhere in the
    snapshot — regardless of owner, regardless of which responsibility it
    is actually about — put that literal string into the snapshot-wide
    ``source_failure_codes`` set; without this guard, a DIFFERENT,
    genuinely root-job-id-less card would still be silently neutralized to
    OK merely because that unrelated string happened to be live somewhere,
    exactly the same class of false-negative Repair B already closed for
    the ``_CardIssues`` routine-absence codes.  Mirrors that guard exactly:
    the branch below now also requires ``"runtime_root_missing" not in
    source_failure_codes``.
    """
    if result.status is QueryStatus.UNKNOWN:
        return QueryStatus.OK
    if (
        result.status is QueryStatus.REFUSED
        and len(result.issues) == 1
        and result.issues[0].code == "runtime_root_missing"
        and "runtime_root_missing" not in source_failure_codes
        and not has_runtime_evidence
    ):
        return QueryStatus.OK
    return result.status


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


def _declared_blocker_card(declared: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Card shape for a plain-data ``declared_blocker`` row, or ``None``.

    ``declared`` is one value from :func:`declared_blockers_from_agent_os_state`'s
    return mapping — never a Steward fact.  Explicitly NOT the Steward-owned
    ``blocker`` card shape (:func:`_blocker_card`) and never merged with it:
    different owners, different authority (see module docstring point 8).
    """
    if declared is None:
        return None
    return {
        "code": declared["code"],
        "explanation": declared["explanation"],
        "target_seat": declared.get("target_seat"),
        "source": _receipt(declared["source"]),
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
    declared_blocker: Mapping[str, Any] | None,
    attention_facts: tuple[AttentionFact, ...],
    current_worker: dict[str, Any] | None,
    current_worker_fact: RuntimeFact | None,
) -> dict[str, Any]:
    """Frozen spec §4.2 — evaluated in order, first match wins.

    Extended by the bug-fix packet (2026-09-01) with one new rung, between
    the Steward-owned blocker and attention: a ``declared_blocker`` — the
    plain-data, honestly Agent-OS-owned "workstream is blocked" signal
    :func:`declared_blockers_from_agent_os_state` produces, since a genuine
    Steward ``BlockerFact`` can never be built from that source (see module
    docstring point 8) — names an owed seat too, when it carries one, under
    its own distinct reason code so it is never confused with a real
    Steward-owned gate.  A ``declared_blocker`` with no ``target_seat``
    (owner unrecognized and ``needs_ceo`` not literally ``True``) must not
    set an owed seat here — it falls through to the next rung exactly as if
    no ``declared_blocker`` existed.
    """
    if blocker is not None and blocker_fact is not None:
        return {
            "seat": blocker_fact.target_seat.value,
            "reason": "blocker_targets_seat",
            "source_refs": _receipts_sorted([blocker_fact.source]),
        }
    if declared_blocker is not None and declared_blocker.get("target_seat"):
        return {
            "seat": declared_blocker["target_seat"],
            "reason": "agent_os_declared_blocker_targets_seat",
            "source_refs": _receipts_sorted([declared_blocker["source"]]),
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
    declared_blockers: Mapping[str, Mapping[str, Any]] | None = None,
    unmapped_responsibilities: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure, deterministic projection of one Executive Steward snapshot.

    No I/O, no subprocess, no clock read, no environment read, no
    randomness.  ``generated_at`` is injected, never read from a clock.
    Calling this twice with the same arguments produces byte-identical
    ``json.dumps(doc, sort_keys=True)`` output.

    ``declared_blockers`` (bug-fix packet, 2026-09-01) is optional plain
    data — keyed by ``responsibility_ref``, one row per key from
    :func:`declared_blockers_from_agent_os_state` — threaded straight
    through to each matching card's ``declared_blocker`` field and into
    :func:`_classify_owed_turn`.  It is never a Steward fact and is never
    merged with the Steward-owned ``blocker`` field.  Defaults to ``None``
    (treated as empty) so every existing caller that does not supply it —
    including every card built from a snapshot with no Agent-OS-declared
    blockers — is unaffected: ``declared_blocker`` reads ``null`` on every
    such card.

    ``unmapped_responsibilities`` (blast-radius repair packet, 2026-09-01)
    is optional plain data — one row per
    :func:`unmapped_responsibilities_from_agent_os_state` entry — threaded
    the exact same way as ``declared_blockers``: a separate keyword-only
    parameter with a safe default, never merged into any card and never a
    ``SourceFailure``.  It is emitted verbatim (sorted for determinism) as
    the top-level ``unmapped_responsibilities`` list and has zero effect on
    any card's ``query_status``, ``is_actionable``, ``actionability_reason``
    or ``freshness`` — those are computed entirely from ``membership``
    (``snapshot.list_responsibilities()``) before this parameter is ever
    consulted.  Defaults to ``None`` (treated as empty) so every existing
    caller that does not supply it is unaffected.

    It DOES affect one thing: ``counts["empty"]`` (repair packet,
    2026-09-01, Change B).  Zero mapped ``responsibilities`` used to read
    ``empty: true`` even when responsibilities were suppressed for this
    exact reason — unrecognized Agent OS owners — reporting "the estate is
    genuinely idle" when the truth is "every workstream was suppressed as
    unmapped".  This is the same law Repair 9 already applies to
    ``membership_suppressed``: "we cannot see"/"was excluded" must never
    read as indistinguishable from "nothing to do".  ``empty`` is now
    false whenever ``unmapped_rows`` is non-empty, in addition to staying
    false whenever ``membership_suppressed`` is true; it reads true only
    for a genuinely idle estate — zero mapped responsibilities, nothing
    suppressed by a Steward-level issue, AND nothing suppressed as
    unmapped.
    """
    source_failure_codes = frozenset(f.code for f in snapshot.source_failures)
    declared_blockers = declared_blockers or {}
    unmapped_rows = sorted(
        (dict(row) for row in (unmapped_responsibilities or ())),
        key=lambda row: (row.get("responsibility_ref") or "", row.get("reason") or ""),
    )

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

        # Plain data, never a Steward fact — explicitly NOT the same field
        # as `blocker` above and never merged with it (module docstring
        # point 8; bug-fix packet, 2026-09-01).
        declared_blocker_data = declared_blockers.get(ref)
        declared_blocker = _declared_blocker_card(declared_blocker_data)

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
        # Repair A1 (Sol review addendum, 2026-09-03): a plain Agent-OS
        # `declared_blocker` can drive `owed_turn.seat == "chairman"`, yet its
        # own SourceRef participated in freshness NOWHERE — so a years-old
        # declared block resolved as fresh evidence and could raise an urgent
        # Chairman call.  It is a contributing source like any other; only its
        # OWNERSHIP is separate (never a BlockerFact, never merged into the
        # Steward blocker), and folding the receipt in changes no attribution.
        if declared_blocker_data is not None:
            declared_source = declared_blocker_data.get("source")
            if declared_source is not None:
                contributing_sources.add(declared_source)

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

        # Fix 3: bare existence check (never a re-implementation of
        # get_current_runtime's own root-job-id/seat/candidate join logic —
        # see _neutral_if_routine_absence's docstring and the module
        # docstring's "Consume, never duplicate" section for the scoped
        # exception this narrowly relies on) of whether the snapshot has
        # ANY RuntimeFact for this exact (ref, seat) — used only to verify,
        # rather than assume, that a root_job_id-less responsibility is
        # genuinely missing runtime evidence before neutralizing its
        # get_current_runtime REFUSED result to OK.
        worker_runtime_evidence_exists = any(
            rt.responsibility_ref == ref and rt.seat is Seat.WORKER
            for rt in snapshot.runtimes
        )
        sol_runtime_evidence_exists = any(
            rt.responsibility_ref == ref and rt.seat is Seat.CEO
            for rt in snapshot.runtimes
        )

        query_status = _combine_status([
            gr.status,
            _neutral_if_routine_absence(
                cw_result,
                source_failure_codes=source_failure_codes,
                has_runtime_evidence=worker_runtime_evidence_exists,
            ),
            _neutral_if_routine_absence(
                st_result,
                source_failure_codes=source_failure_codes,
                has_runtime_evidence=sol_runtime_evidence_exists,
            ),
            _neutral_if_routine_absence(
                bl_result,
                source_failure_codes=source_failure_codes,
                # explain_blocker never emits "runtime_root_missing" — this
                # only matters for the branch that code triggers, so it is
                # inert here regardless of the value passed.
                has_runtime_evidence=False,
            ),
            at_result.status,
        ]).value

        owed_turn = _classify_owed_turn(
            blocker=blocker,
            blocker_fact=blocker_fact,
            declared_blocker=declared_blocker_data,
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
        # Repair A2 (Sol review addendum, 2026-09-03): urgency is a claim about
        # NOW, so it requires evidence that is current.  Without this gate the
        # top-level `chairman_decisions` queue and the UI could render
        # "YOUR CALL / Only you can decide" on a card simultaneously labelled
        # HISTORY / not actionable — exactly the stale-history-as-urgency
        # defect this surface exists to prevent.
        #
        # The gate is FRESHNESS, deliberately NOT general `is_actionable`: a
        # CURRENT canonical EFFECT_UNKNOWN reconciliation blocker is a genuine
        # Chairman decision even though retry/operation actionability is false.
        # `freshness_unknown` is not `current` and therefore cannot be urgent.
        # Nothing is erased: the historical owed_turn, blocker, attention and
        # raw receipts stay on the card for inspection.
        chairman_decision_required = (
            owed_turn["seat"] == "chairman"
            and freshness == Freshness.CURRENT.value
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
            "declared_blocker": declared_blocker,
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
    #
    # Change B (repair packet, 2026-09-01): the same law applies to
    # responsibilities suppressed as UNMAPPED (an unrecognized Agent OS
    # owner — `unmapped_rows`, threaded in verbatim from the caller).  Zero
    # mapped cards plus a non-empty `unmapped_rows` means the estate was
    # NOT idle — every responsibility was read, and every one of them was
    # suppressed for an unrecognized owner — so `empty` must not claim
    # "nothing is being carried".  `empty` is true only when nothing is
    # mapped, nothing was suppressed by a Steward-level issue, AND nothing
    # was suppressed as unmapped.
    membership_suppressed = bool(list_result.issues)
    # Fix 2 (final adversarial review, 2026-09-01): `blocked` stays
    # Steward-owned ONLY (`card["blocker"]`, i.e. a real `BlockerFact`) —
    # that attribution is correct and unchanged.  But rendering it alone
    # under the bare label "gated" let the Chairman read "0 gated" on a
    # real artifact while a visible card (and, on an unrecognized-owner
    # row, an `unmapped_responsibilities` entry) carried an Agent-OS-
    # declared block (`declared_blocker`/`unmapped_rows[i]["declared_
    # blocker"]`) — the summary contradicting the detail directly beneath
    # it.  `declared_blocked` is a separate, deterministic count of every
    # row carrying a declared block, over BOTH surfaces such a declaration
    # can appear on: a mapped card's own `declared_blocker` field, and an
    # unmapped row's `declared_blocker` sub-object (see
    # `_declared_blocker_receipt`) — never merged into `blocked`, so
    # Steward-owned and Agent-OS-declared blocks stay two separately
    # countable numbers, exactly as they stay two separately countable
    # fields on the cards/rows themselves.
    declared_blocked = sum(
        1 for c in responsibilities if c["declared_blocker"] is not None
    ) + sum(1 for row in unmapped_rows if row.get("declared_blocker") is not None)
    counts = {
        "total": len(responsibilities),
        "actionable": sum(1 for c in responsibilities if c["is_actionable"]),
        "stale": sum(1 for c in responsibilities if c["freshness"] == Freshness.STALE.value),
        "blocked": sum(1 for c in responsibilities if c["blocker"] is not None),
        "declared_blocked": declared_blocked,
        "empty": (
            len(responsibilities) == 0
            and not membership_suppressed
            and not unmapped_rows
        ),
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
        "unmapped_responsibilities": unmapped_rows,
    }
    if set(doc.keys()) != OUTPUT_KEYS:
        raise RuntimeError(
            f"project_autonomy produced key set {sorted(doc.keys())}, "
            f"expected {sorted(OUTPUT_KEYS)} — this is a contract "
            "violation, not a degraded-data condition."
        )
    return doc


# ---------------------------------------------------------------------------
# real-data mapper: compositor inputs -> ExecutiveStewardSnapshot
# (module docstring "Real-data mapper" section, points 8-10)
# ---------------------------------------------------------------------------

#: Every literal wire token a Steward ``Seat`` accepts, keyed by that same
#: string — used to recognize a genuine Seat value on a raw compositor
#: input without ever guessing at one that isn't there.
_SEAT_BY_VALUE = {seat.value: seat for seat in Seat}


def _seat_or_none(value: Any) -> Seat | None:
    return _SEAT_BY_VALUE.get(value) if isinstance(value, str) else None


#: Fix 1 (adversarial-review repair packet, 2026-09-01): the Agent OS state
#: artifact — and every other document this mapper reads — is produced by a
#: nightly job, so evidence older than two nightly cycles is stale rather
#: than current.  48 hours, not 24, so a single missed/delayed nightly run
#: does not flap every card stale and back the next morning.  A named,
#: documented module constant rather than a bare number, so the budget is
#: auditable and changeable in one place.
FRESHNESS_BUDGET_HOURS = 48
FRESHNESS_BUDGET = timedelta(hours=FRESHNESS_BUDGET_HOURS)

#: Fix 1 (adversarial-review final-adjudication repair, 2026-09-01): the
#: maximum amount an ``observed_at`` may sit AHEAD of the reference
#: timestamp before this module stops trusting the gap as ordinary clock
#: skew.  Without a bound, a negative ``age`` (``reference_dt -
#: observed_dt``) was unconditionally within :data:`FRESHNESS_BUDGET`
#: (``age <= FRESHNESS_BUDGET`` is trivially true for any negative ``age``,
#: no matter how large in magnitude) — an artifact stamped 2999-01-01 and
#: composed against a 2026 reference read ``CURRENT`` with
#: ``counts["stale"]`` at zero, and could even become actionable, on
#: evidence that has not happened yet.  One hour is a small window
#: genuinely attributable to unsynchronized clocks between the host that
#: stamped the artifact and the host that composed it — not a license to
#: treat an arbitrarily-future timestamp as current.  Beyond this
#: tolerance the timestamp reads ``UNKNOWN`` — never ``CURRENT`` (nothing
#: observed that far ahead has actually happened yet) and never ``STALE``
#: (this module has no basis to claim the artifact is old either) — so a
#: card built from it can never read falsely current and, per
#: :func:`_classify_actionability`, can never become actionable on it.
#: The BACKWARD (ordinary staleness) side of :data:`FRESHNESS_BUDGET` is
#: entirely unchanged by this constant.
FUTURE_SKEW_TOLERANCE_HOURS = 1
FUTURE_SKEW_TOLERANCE = timedelta(hours=FUTURE_SKEW_TOLERANCE_HOURS)


def _parse_iso8601(value: Any) -> datetime | None:
    """Best-effort, defensive ISO-8601 parse — never raises; unparseable -> ``None``.

    Reuses the repo-wide ``datetime.fromisoformat(value.replace("Z",
    "+00:00"))`` idiom already used elsewhere in this codebase (e.g.
    ``control_plane/chairman_cognition.py:1558``,
    ``control_plane/chairman_cognition_sources.py:645/688``) rather than
    inventing a new parsing convention or adding a dependency.  A naive
    (timezone-less) result is treated as UTC — every timestamp this module
    reads is a Zulu-suffixed wire string in practice, and assuming UTC for
    a bare ISO string (rather than refusing it) keeps this defensive
    without silently mis-comparing offsets it was never given.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _freshness_for(observed_at: Any, reference_at: Any) -> tuple[str | None, Freshness]:
    """``(observed_at, freshness)`` — Fix 1, see module docstring point 10.

    ``reference_at`` is the injected, clock-free reference timestamp —
    ``project_autonomy``'s own ``generated_at``, threaded down through
    :func:`build_autonomy_snapshot` into every caller of this helper below.
    Comparing two already-supplied timestamps is pure; this function still
    never reads a clock, never fabricates an ``observed_at``, and never
    reports ``CURRENT`` for a timestamp it cannot actually evaluate.

    - ``observed_at`` absent/blank/non-string -> ``(None, UNKNOWN)``.
    - ``observed_at`` present but unparseable -> ``(observed_at, UNKNOWN)``
      — the raw string is kept as a receipt (``SourceRef`` allows
      ``UNKNOWN`` with ``observed_at`` present) but never trusted as
      current.
    - ``reference_at`` absent/unparseable -> ``(observed_at, UNKNOWN)`` —
      nothing to compare against.
    - ``observed_at`` parses and sits AHEAD of ``reference_at`` by more
      than :data:`FUTURE_SKEW_TOLERANCE` -> ``(observed_at, UNKNOWN)`` —
      Fix 1: an artifact stamped far in the future (e.g. 2999-01-01
      against a 2026 reference) is neither current (it has not happened
      yet) nor stale (this module cannot claim to know it is old either).
      Checked BEFORE the budget comparison below, so an unbounded-forward
      ``age`` can never fall through to ``CURRENT``.
    - ``observed_at`` parses and is within :data:`FRESHNESS_BUDGET` of
      ``reference_at`` (including ``observed_at`` at/after
      ``reference_at`` by up to :data:`FUTURE_SKEW_TOLERANCE` — ordinary
      clock skew, not staleness) -> ``(observed_at, CURRENT)``.
    - ``observed_at`` parses and is older than the budget ->
      ``(observed_at, STALE)``.
    """
    if not isinstance(observed_at, str) or not observed_at:
        return None, Freshness.UNKNOWN
    observed_dt = _parse_iso8601(observed_at)
    if observed_dt is None:
        return observed_at, Freshness.UNKNOWN
    reference_dt = _parse_iso8601(reference_at)
    if reference_dt is None:
        return observed_at, Freshness.UNKNOWN
    age = reference_dt - observed_dt
    # Fix 1: bound the forward (observed_at-in-the-future) side first — an
    # unbounded negative age is otherwise trivially <= FRESHNESS_BUDGET no
    # matter how far in the future observed_at sits.
    if age < -FUTURE_SKEW_TOLERANCE:
        return observed_at, Freshness.UNKNOWN
    if age <= FRESHNESS_BUDGET:
        return observed_at, Freshness.CURRENT
    return observed_at, Freshness.STALE


def _attention_responsibility_ref(item: Mapping[str, Any]) -> str | None:
    """The item's ``workstream`` as a full ``WS:<KEY>`` ref, or ``None``.

    Re-derives the exact asymmetry
    :func:`control_plane.chairman_control_room._normalized_workstream_ref`
    documents, rather than importing that private helper — this module has
    no runtime dependency on ``chairman_control_room``'s private surface,
    which a concurrent sibling PR is editing.  A ``source="runtime"``
    item's ``workstream`` is already the full CEO-intent ``WS:<KEY>`` ref;
    a ``source="agent_os"`` item's ``workstream`` is the bare key from the
    Agent OS brief's own ``needs_ceo[].workstream``.  The Steward's own
    ``WS:<key>`` shape check (starts with ``WS:``, no whitespace) still
    runs inside ``AttentionFact.__post_init__`` when the fact is
    constructed below — this function only normalizes the prefix.
    """
    workstream = item.get("workstream")
    if not isinstance(workstream, str) or not workstream:
        return None
    if item.get("source") == "agent_os":
        return workstream if workstream.startswith("WS:") else f"WS:{workstream}"
    return workstream


def _attention_facts_from_inbox(
    inbox: Mapping[str, Any] | None,
    generated_at: Any = None,
) -> tuple[AttentionFact, ...]:
    """Every genuine ``AttentionFact`` the Executive Inbox document supplies.

    ``generated_at`` (Fix 1) is the injected reference timestamp — threaded
    straight through to :func:`_freshness_for` so a real, aged inbox
    document is honestly reported ``STALE``, never unconditionally
    ``CURRENT``.

    Every item read off ``inbox["attention"]`` is attributed to
    ``SourceOwner.EXECUTIVE_INBOX`` — the whole document is produced by
    :mod:`control_plane.executive_inbox`, regardless of an individual
    item's own internal ``source`` field (``"agent_os"``/``"runtime"``),
    which names an upstream PROVENANCE inside the inbox, not a different
    Steward-owned system.  No ``SourceOwner.WAKE``-owned attention fact is
    ever constructed here: none of the compositor's gathered inputs
    include wake-ledger data — Wake is a different subsystem this
    compositor never reads (see :data:`WAKE_OUTCOME_TOKENS`'s own
    consumer, :func:`_classify_wake_outcome`, which will correctly read
    ``"not_observable"`` for every card as a result).  A malformed row
    (missing/blank required field, or one that fails
    ``AttentionFact.__post_init__``'s own validation) is skipped rather
    than raising — one bad row must never suppress every other genuine
    fact in the same document.
    """
    if not isinstance(inbox, Mapping):
        return ()
    items = inbox.get("attention")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return ()

    observed_at, freshness = _freshness_for(inbox.get("generated_at"), generated_at)

    facts: list[AttentionFact] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        ref = _attention_responsibility_ref(item)
        if ref is None:
            continue
        target_seat = _seat_or_none(item.get("target"))
        if target_seat is None:
            continue
        attention_id = item.get("attention_id")
        kind = item.get("kind")
        reason = item.get("reason")
        if not isinstance(attention_id, str) or not attention_id:
            continue
        if not isinstance(kind, str) or not kind:
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        try:
            fact = AttentionFact(
                attention_id=attention_id,
                responsibility_ref=ref,
                target_seat=target_seat,
                kind=kind,
                reason=reason,
                source=SourceRef(
                    owner=SourceOwner.EXECUTIVE_INBOX,
                    ref=attention_id,
                    observed_at=observed_at,
                    freshness=freshness,
                ),
            )
        except (TypeError, ValueError):
            continue
        facts.append(fact)
    return tuple(facts)


def _surface_facts_from_bindings(
    bindings: Mapping[str, Any] | None,
    generated_at: Any = None,
) -> tuple[SurfaceFact, ...]:
    """Every genuine ``SurfaceFact`` the surface-bindings document supplies.

    See module docstring point 9 for why ``reviewed_at`` is always
    ``None``.  Each row's own ``binding_id`` is used as both the fact's
    ``surface_ref`` and its ``SourceRef.ref`` — it is the source's own
    unique identifier for exactly this reviewed-destination row, not an
    invented locator.  A malformed row is skipped rather than raising, for
    the same reason as :func:`_attention_facts_from_inbox`.  ``generated_at``
    (Fix 1) is the same injected reference timestamp, per row (each binding
    row carries its own ``observed_at``, unlike the single document-level
    timestamp attention/responsibility facts share).
    """
    if not isinstance(bindings, Mapping):
        return ()
    rows = bindings.get("bindings")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return ()

    facts: list[SurfaceFact] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        work_ref = row.get("work_ref")
        role = _seat_or_none(row.get("role"))
        binding_id = row.get("binding_id")
        provider = row.get("provider")
        locator_kind = row.get("locator_kind")
        seat_ref = row.get("seat_ref")
        if not isinstance(work_ref, str) or not work_ref:
            continue
        if role is None:
            continue
        if not isinstance(binding_id, str) or not binding_id:
            continue
        if not isinstance(provider, str) or not provider:
            continue
        if not isinstance(locator_kind, str) or not locator_kind:
            continue
        if seat_ref is not None and not isinstance(seat_ref, str):
            continue
        observed_at, freshness = _freshness_for(row.get("observed_at"), generated_at)
        try:
            fact = SurfaceFact(
                responsibility_ref=work_ref,
                role=role,
                seat_ref=seat_ref,
                surface_ref=binding_id,
                provider=provider,
                locator_kind=locator_kind,
                reviewed_at=None,
                source=SourceRef(
                    owner=SourceOwner.SURFACE_BINDINGS,
                    ref=binding_id,
                    observed_at=observed_at,
                    freshness=freshness,
                ),
            )
        except (TypeError, ValueError):
            continue
        facts.append(fact)
    return tuple(facts)


#: Closed, CASE-SENSITIVE, EXACT map from a ``workstreams[]`` row's raw
#: ``owner`` string to the :class:`Seat` it names — the only lawful way this
#: mapper ever derives a seat from ``owner``.  Nothing outside this map is
#: ever accepted: no substring match, no regex, no lowercase-normalize, no
#: strip, no fuzzy match.  A value not present here — including free-text
#: sentences that happen to *contain* a seat-like word, e.g. ``"Eval-OS
#: session (COO Fable lane)"`` — is unrecognized, full stop (module
#: docstring point 8).
_ACCOUNTABLE_SEAT_BY_OWNER: dict[str, Seat] = {
    "chairman": Seat.CHAIRMAN,
    "ceo-sol": Seat.CEO,
    "coo-fable": Seat.COO,
    "fable": Seat.COO,
}


def _workstream_ref(key: str) -> str:
    """The row's bare ``key`` as a full ``WS:<KEY>`` ref.

    Re-derives the same asymmetry :func:`_attention_responsibility_ref`
    already documents for an ``agent_os``-sourced attention item: a real
    ``agent_os_state.v1`` ``workstreams[].key`` is the bare key, with no
    ``WS:`` prefix (verified against the real compiled artifact).
    """
    return key if key.startswith("WS:") else f"WS:{key}"


def _blocked_by_reasons(row: Mapping[str, Any]) -> list[str]:
    """Every non-blank string in a workstream row's own ``blocked_by`` list.

    Shared by :func:`_responsibility_facts_from_agent_os_state` (Fix 2:
    carries this same signal into an unmapped row's own receipt, see
    :func:`_declared_blocker_receipt`) and
    :func:`declared_blockers_from_agent_os_state`, so the two can never
    silently drift apart on what counts as a genuine block reason.  Never
    invents a reason from any other field.
    """
    blocked_by = row.get("blocked_by")
    if not isinstance(blocked_by, Sequence) or isinstance(blocked_by, (str, bytes)):
        return []
    return [item.strip() for item in blocked_by if isinstance(item, str) and item.strip()]


def _declared_blocker_receipt(row: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    """Fix 2: the same declared-blocker signal, minus the ``source`` SourceRef.

    ``unmapped_responsibilities`` rows are plain, JSON-safe data (no
    ``SourceRef`` object) — see :func:`project_autonomy`'s own
    ``unmapped_responsibilities`` handling, which folds these rows verbatim
    into ``json.dumps(doc, sort_keys=True)``.  ``None`` when the row's own
    ``blocked_by`` is genuinely empty or absent — never fabricated.
    ``target_seat`` is ``"ceo"`` when ``needs_ceo`` is literally ``True``;
    otherwise ``None`` (the row's ``owner`` is, by construction, always
    unrecognized at this call site — that is exactly why the row is
    unmapped — so there is no recognized-seat fallback to try, unlike
    :func:`declared_blockers_from_agent_os_state`).  Never includes the raw
    owner text.
    """
    reasons = _blocked_by_reasons(row)
    if not reasons:
        return None
    target_seat = Seat.CEO.value if row.get("needs_ceo") is True else None
    return {
        "code": "blocked_by",
        "explanation": f"workstream {key} is blocked by: " + "; ".join(reasons),
        "target_seat": target_seat,
    }


def _responsibility_facts_from_agent_os_state(
    agent_os_state: Mapping[str, Any] | None,
    generated_at: Any = None,
) -> tuple[tuple[ResponsibilityFact, ...], dict[str, Seat], tuple[dict[str, Any], ...]]:
    """Real ``ResponsibilityFact`` rows, built only from structured fields.

    ``generated_at`` (Fix 1) is the injected reference timestamp, threaded
    straight through to :func:`_freshness_for` — the exact same argument
    :func:`build_autonomy_snapshot` receives from the compositor's own
    ``generated_at``, so a real, aged Agent OS artifact is honestly
    reported ``STALE`` rather than unconditionally ``CURRENT``.

    Returns ``(facts, seat_by_key, unmapped)``: ``seat_by_key`` is unused by
    ``BlockerFact`` construction any more (that construction was deleted
    outright — see module docstring point 8) but is kept in this return
    shape and reused, the same closed-token way, by
    :func:`declared_blockers_from_agent_os_state`'s owner-seat fallback,
    rather than re-deriving it (or, worse, inventing one) a second time.

    ``unmapped`` is one bounded, per-row plain-data entry — never a
    :class:`SourceFailure` (blast-radius repair packet, 2026-09-01, see
    :func:`unmapped_responsibilities_from_agent_os_state`) — for every row
    whose ``owner`` did not match :data:`_ACCOUNTABLE_SEAT_BY_OWNER`.  A
    ``SourceFailure`` is a global, source-level outage; ``executive_steward.
    ExecutiveStewardSnapshot._source_issues`` folds every ``SourceFailure``
    into the issues of EVERY query the Steward answers (every card consults
    every owner on every call — see module docstring point 7), so a
    per-row condition on a handful of workstreams was contaminating every
    other card's ``query_status``/``actionability_reason`` — measured
    2026-09-01: 7 unrecognized-owner rows made all 40 unrelated cards read
    ``query_status: "refused"``.  ``unmapped`` rows carry the workstream's
    normalized ``responsibility_ref`` and a short machine ``reason`` —
    never the raw owner prose (the exact same "never derive ... seat ...
    from ... prose" discipline point 8 already documents).  Fix 2
    (adversarial-review repair packet, 2026-09-01) adds one more, strictly
    optional key: when the same unrecognized-owner row's own ``blocked_by``
    is genuinely non-empty, the entry also carries a ``declared_blocker``
    sub-object (see :func:`_declared_blocker_receipt`) — this is the ONLY
    place a workstream whose owner cannot be mapped to a seat still tells
    the Chairman it is blocked: :func:`project_autonomy`'s card loop only
    ever consults ``declared_blockers`` for a ``ref`` that has a real
    ``ResponsibilityFact`` in Steward membership, which an unrecognized-
    owner row never gets, so without this the block silently vanished (the
    exact defect the module docstring used to describe as already fixed —
    see :func:`declared_blockers_from_agent_os_state`'s own docstring for
    the corrected account).

    Fix 5 (adversarial-review repair packet, 2026-09-01): a row whose own
    ``key``/``title`` is blank or absent, or whose ``ResponsibilityFact``
    construction raises despite passing those checks (e.g. a ``key``
    containing whitespace, which fails ``SourceRef``/``ResponsibilityFact``'s
    own token-shape validation; or a ``status`` containing whitespace,
    which fails ``_require_text``), is no longer skipped in silence — it
    gets a bounded ``unmapped`` receipt with ``reason: "row_unreadable"``,
    so "we could not read this row" is never indistinguishable from "this
    row does not exist".  ``responsibility_ref`` on that receipt is the
    normalized ref when a genuine, non-blank ``key`` is available (title
    blank, or construction raised) and ``None`` only when even ``key``
    itself could not be read.  A row that is not a ``Mapping`` at all is
    still skipped with no receipt — an entirely absent index into a list is
    not "this one row was unreadable", and every other malformed-row
    helper in this module (:func:`_attention_facts_from_inbox`,
    :func:`_surface_facts_from_bindings`) treats it the same way; Fix 5 is
    scoped to a row that IS a mapping but whose content could not be used.
    """
    if not isinstance(agent_os_state, Mapping):
        return (), {}, ()
    rows = agent_os_state.get("workstreams")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return (), {}, ()

    observed_at, freshness = _freshness_for(agent_os_state.get("generated_at"), generated_at)

    facts: list[ResponsibilityFact] = []
    seat_by_key: dict[str, Seat] = {}
    unmapped: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = row.get("key")
        title = row.get("title")
        key_ok = isinstance(key, str) and bool(key)
        title_ok = isinstance(title, str) and bool(title.strip())
        if not key_ok or not title_ok:
            # Fix 5: unreadable, not nonexistent.
            unmapped.append({
                "responsibility_ref": _workstream_ref(key) if key_ok else None,
                "reason": "row_unreadable",
            })
            continue

        source_ref = f"agent_os_state.workstreams:{key}"
        owner = row.get("owner")
        seat = _ACCOUNTABLE_SEAT_BY_OWNER.get(owner) if isinstance(owner, str) else None
        if seat is None:
            unmapped_entry: dict[str, Any] = {
                "responsibility_ref": _workstream_ref(key),
                "reason": "owner_not_a_recognized_seat",
            }
            # Fix 2: an unmapped-but-blocked workstream still tells the
            # Chairman it is blocked, and why — never the raw owner text.
            declared = _declared_blocker_receipt(row, key)
            if declared is not None:
                unmapped_entry["declared_blocker"] = declared
            unmapped.append(unmapped_entry)
            continue

        status = row.get("status")
        state = status if isinstance(status, str) and status else None
        try:
            fact = ResponsibilityFact(
                responsibility_ref=_workstream_ref(key),
                title=title,
                accountable_seat=seat,
                state=state,
                root_job_id=None,  # no workstreams[] row carries a JOB-* field
                source=SourceRef(
                    owner=SourceOwner.AGENT_OS,
                    ref=source_ref,
                    observed_at=observed_at,
                    freshness=freshness,
                ),
            )
        except (TypeError, ValueError):
            # Fix 5: construction raised despite key/title passing the
            # checks above (e.g. a key or status containing whitespace) —
            # unreadable, not nonexistent.  A real key is always available
            # here (key_ok was required to reach this branch).
            unmapped.append({
                "responsibility_ref": _workstream_ref(key),
                "reason": "row_unreadable",
            })
            continue
        facts.append(fact)
        seat_by_key[key] = seat
    return tuple(facts), seat_by_key, tuple(unmapped)


def unmapped_responsibilities_from_agent_os_state(
    agent_os_state: Mapping[str, Any] | None,
    generated_at: Any = None,
) -> tuple[dict[str, Any], ...]:
    """Bounded, per-row report of workstreams whose ``owner`` is unmapped.

    Blast-radius repair packet, 2026-09-01: this is the third pure public
    function threaded the exact same way
    :func:`declared_blockers_from_agent_os_state` already is — plain data,
    never a Steward fact, never a :class:`SourceFailure`, meant to be
    handed to :func:`project_autonomy`'s ``unmapped_responsibilities``
    parameter.  Each entry names the workstream's normalized
    ``responsibility_ref`` and a short machine ``reason``
    (``"owner_not_a_recognized_seat"`` or, Fix 5, ``"row_unreadable"``) —
    never the raw owner prose — plus, Fix 2, an optional ``declared_blocker``
    sub-object when an unrecognized-owner row is itself genuinely blocked
    (see :func:`_responsibility_facts_from_agent_os_state` for both).  See
    that function for why this must never be a ``SourceFailure``: the
    Steward folds every ``SourceFailure`` into the issues of every query it
    answers, so seven unmappable owner strings were making forty unrelated,
    correctly-read responsibilities unreadable.  ``generated_at`` (Fix 1) is
    the same injected reference timestamp threaded through the mapper's
    other public functions — unused by this function's own OUTPUT (an
    unmapped row carries no freshness), but required to reach
    :func:`_responsibility_facts_from_agent_os_state`, which needs it to
    freshness-stamp the ``ResponsibilityFact``s it also builds.  Sorted by
    ``responsibility_ref`` for determinism — a ``row_unreadable`` entry
    whose own ``key`` could not be read at all sorts by the empty string
    (``responsibility_ref`` is ``None`` in that one case; every entry still
    carries the key so the sort never raises on a ``None``/``str``
    comparison).
    """
    _, _, unmapped = _responsibility_facts_from_agent_os_state(agent_os_state, generated_at)
    return tuple(sorted(unmapped, key=lambda row: row["responsibility_ref"] or ""))


def declared_blockers_from_agent_os_state(
    agent_os_state: Mapping[str, Any] | None,
    generated_at: Any = None,
) -> dict[str, dict[str, Any]]:
    """Plain-data, honestly Agent-OS-owned blocker signal, by ``responsibility_ref``.

    Bug-fix packet, 2026-09-01: replaces the deleted ``_blocker_facts_from_
    agent_os_state``, which built a real ``BlockerFact`` from this same
    ``blocked_by``/``needs_ceo`` data and stamped it ``source.owner =
    SourceOwner.EXECUTIVE_OS`` — a false attribution, since
    ``BlockerFact.__post_init__`` never accepts ``SourceOwner.AGENT_OS`` and
    the fact's own ``ref`` string (``agent_os_state.workstreams:<key>.
    blocked_by``) names Agent OS, not Executive OS, as its true source.  The
    lawful response to a contract that cannot carry a claim honestly is to
    decline the claim, not relabel the owner — so this function returns
    plain data instead, carrying its own true ``SourceOwner.AGENT_OS``
    receipt, for :func:`project_autonomy`'s ``declared_blockers`` parameter
    to fold into each card's ``declared_blocker`` field.  That field is
    EXPLICITLY NOT the Steward-owned ``blocker`` field and must never be
    merged into it — different owners, different authority.

    Never invents a blocker from ``warnings``, ``stale_days``, or any other
    prose field — only a genuinely non-empty ``blocked_by`` list produces an
    entry.  ``target_seat`` is ``"ceo"`` when the row's ``needs_ceo`` is
    literally ``True``; otherwise the SAME closed-token seat
    :func:`_responsibility_facts_from_agent_os_state` already derives for
    that row's ``owner`` (never re-derived from prose here — this function
    calls that one to obtain its ``seat_by_key`` return, the single source
    of truth for the mapping, rather than re-implementing the lookup).  When
    neither is available — ``needs_ceo`` is not literally ``True`` AND the
    row's ``owner`` was unrecognized — ``target_seat`` is ``None``, never
    guessed.  Unlike the deleted ``BlockerFact`` path, an unresolvable
    ``target_seat`` does NOT suppress THIS function's own entry: it always
    exists in the returned mapping whenever ``blocked_by`` is genuinely
    non-empty, whether or not the row's owner was recognized.

    Correction (Fix 2, adversarial-review repair packet, 2026-09-01): this
    docstring used to stop there and claim "the Chairman is still told the
    workstream is blocked even when nobody can be named as accountable for
    it" — true of THIS function's own return value in isolation, but false
    end-to-end as actually composed: :func:`project_autonomy`'s card loop
    only ever reads ``declared_blockers`` for a ``responsibility_ref`` that
    has a real ``ResponsibilityFact`` in Steward membership, and an
    unrecognized-owner row never gets one (see module docstring point 8) —
    so a blocked-but-unmapped workstream's entry here was computed
    correctly and then silently never read.  The actual guarantee now spans
    two surfaces: a recognized-owner row's block reaches the Chairman via
    this function into a real card's ``declared_blocker`` field (unchanged);
    an unrecognized-owner row's block reaches the Chairman via
    :func:`_responsibility_facts_from_agent_os_state`'s own
    ``unmapped_responsibilities`` receipt instead (see
    :func:`_declared_blocker_receipt`), since that is the only surface such
    a row ever appears on.  An entry is omitted from THIS function's return
    value only when ``blocked_by`` itself is genuinely empty or absent —
    unchanged.  ``generated_at`` (Fix 1) is the injected reference
    timestamp threaded through to :func:`_freshness_for`, exactly as
    :func:`_responsibility_facts_from_agent_os_state` uses it.
    """
    if not isinstance(agent_os_state, Mapping):
        return {}
    rows = agent_os_state.get("workstreams")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return {}

    _, seat_by_key, _ = _responsibility_facts_from_agent_os_state(agent_os_state, generated_at)
    observed_at, freshness = _freshness_for(agent_os_state.get("generated_at"), generated_at)

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = row.get("key")
        if not isinstance(key, str) or not key:
            continue
        reasons = _blocked_by_reasons(row)
        if not reasons:
            continue

        if row.get("needs_ceo") is True:
            target_seat: str | None = Seat.CEO.value
        else:
            owner_seat = seat_by_key.get(key)
            target_seat = owner_seat.value if owner_seat is not None else None

        out[_workstream_ref(key)] = {
            "code": "blocked_by",
            "explanation": (
                f"workstream {key} is blocked by: " + "; ".join(reasons)
            ),
            "target_seat": target_seat,
            "source": SourceRef(
                owner=SourceOwner.AGENT_OS,
                ref=f"agent_os_state.workstreams:{key}.blocked_by",
                observed_at=observed_at,
                freshness=freshness,
            ),
        }
    return out


# ---------------------------------------------------------------------------
# dispatch-consumption projection (AD-CR1A commissioning packet, 2026-09-03)
#
# A pure, read-only SECOND pass over already-produced responsibility cards
# (``project_autonomy``'s own ``responsibilities`` output, or any mapping
# carrying the same two identity fields).  Answers exactly one question the
# rest of this module never asks: was a dispatched piece of work actually
# picked up and started, or sent into a void?  An unacknowledged delivery
# must never read as active/executing — that is the single most dangerous
# falsehood this projection exists to prevent (an unconsumed dispatch that
# LOOKS like progress is never re-sent).
#
# Real owners this state machine is *informed by* but never calls (all three
# require a Runtime/sqlite connection or live outside control_plane's
# importable surface, so calling them here would violate purity):
#   - control_plane.wake_ledger.reconstruct_status(...) -> ObligationStatus
#     (NOT_SEEN, PENDING_RETRYABLE, ATTEMPTED, RECONCILIATION_REQUIRED,
#     ACCEPTED, DELIVERED_UNACKNOWLEDGED, TARGET_ACKNOWLEDGED,
#     SOURCE_RESOLVED).
#   - control_plane.sol_action_target.resolve_sol_action_target(...) ->
#     ActionTargetState (RESOLVED, UNAVAILABLE, CONFLICT, UNKNOWN) and
#     BindingEvidenceState (CURRENT, UNKNOWN).
#   - control_plane.operator_continuity_projection's AttemptState (CLAIMED,
#     RUNNING, CHECKPOINTED, CANCEL_REQUESTED, RATE_LIMITED, FAILED, LOST,
#     COMPLETED, CANCELLED).
#   - The Agent Dialogue owner (TurnDecision/ObservationReceipt,
#     integrations/slack_agent_dialogue/) is not importable from
#     control_plane at all — RETURNED/CONTINUED/STOPPED evidence is
#     therefore *only* ever supplied plain data (``sol_decision``,
#     ``sol_decision_carrier_ref``); this module invents none of it.
#
# ``project_dispatch_consumption``'s ``dispatch_evidence`` parameter is
# threaded exactly like ``project_autonomy``'s ``declared_blockers``/
# ``unmapped_responsibilities``: optional plain data, defaulting to "not
# supplied", never a Steward fact.  Each row is matched to a card by the
# EXACT join Law 1 names — ``responsibility_ref`` AND ``root_job_id``
# together, never title, provider label, newest timestamp, or recency —
# and an unmatched, duplicate/ambiguous, or wholly absent input renders
# every affected card ``UNKNOWN`` with a named reason, never a fabricated
# success stage.
# ---------------------------------------------------------------------------

#: Closed dispatch-consumption vocabulary (frozen by the commissioning
#: authority, 2026-09-03).  Ordered happy path first, then the five
#: non-happy states — every one of the twelve renders explicitly and is
#: never silently collapsed into a neighbour.
DISPATCH_STATES = frozenset({
    "WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT",
    "PICKUP_ACKNOWLEDGED", "STARTED", "RETURNED", "CONTINUED", "STOPPED",
    "DELIVERY_UNCONSUMED", "WATCH_UNPROVEN",
    "RUNTIME_BINDING_RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN", "UNKNOWN",
})

#: Schema version of the document :func:`project_dispatch_consumption` emits.
DISPATCH_SCHEMA = "mastermind.autonomy_dispatch_consumption.v1"

#: ``ObligationStatus`` wire values (``wake_ledger.py``) that mean a delivery
#: was attempted/landed but no valid receiver ACK was ever recorded — Law 2:
#: "A delivery with no valid exact receiver ACK is DELIVERY_UNCONSUMED,
#: never active/executing."  ``ATTEMPTED`` (a FAILED or TARGET_UNAVAILABLE
#: ledger phase) is folded in here too: a failed attempt has, if anything,
#: LESS claim to being consumed than a landed-but-unacknowledged one, and
#: the closed vocabulary has no separate "delivery failed" token.
_OBLIGATION_NO_ACK = frozenset({"DELIVERED_UNACKNOWLEDGED", "ATTEMPTED"})

#: ``ObligationStatus`` values meaning pickup was acknowledged but NOT that
#: work started (Law 3: PICKUP_ACKNOWLEDGED "remains DISTINCT from
#: STARTED").  ``SOURCE_RESOLVED`` (the wake obligation's own terminal
#: ledger phase) is folded in here too — it closes the *wake* obligation,
#: never the Attempt itself, so it carries no more START authority than a
#: bare TARGET_ACKNOWLEDGED (Law 4: pickup "cannot imply" STARTED).
_OBLIGATION_PICKUP_ACK = frozenset({"TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED"})

#: ``ObligationStatus`` values meaning "not yet delivered" — combined below
#: with ``action_target_state`` per the mission's given rule (NOT_SEEN with
#: no receiver -> WAITING_CAPACITY).  ``PENDING_RETRYABLE`` is folded in
#: here rather than treated as DELIVERY_SENT: ``wake_ledger.reconstruct_
#: status`` returns it both when no destination is even known yet and as a
#: non-terminal fallback, so it never proves a delivery landed — treating
#: it identically to NOT_SEEN for placement purposes is the conservative
#: reading (never claims DELIVERY_SENT prematurely).
_OBLIGATION_NOT_YET_DELIVERED = frozenset({None, "NOT_SEEN", "PENDING_RETRYABLE"})

#: ``AttemptState`` wire values (``operator_continuity_projection.py``)
#: meaning the Attempt is still open/in flight.
_ATTEMPT_IN_PROGRESS = frozenset({
    "CLAIMED", "RUNNING", "CHECKPOINTED", "CANCEL_REQUESTED", "RATE_LIMITED",
})

#: ``AttemptState`` wire values meaning the Attempt has concluded — the
#: precondition for even asking whether a RETURNED/CONTINUED/STOPPED
#: transition happened (still gated by WATCH_PROVEN, Law 6).
_ATTEMPT_TERMINAL = frozenset({"COMPLETED", "FAILED", "LOST", "CANCELLED"})

#: Review 5103135217 BLOCKER 4: "Require validated exact child + operation +
#: carrier + mechanism + handled-baseline evidence."  Extends the original
#: four-field Law 6 proof with ``watch_operation`` — the fifth field the
#: adversarial review named — so a forged/duplicated watcher receipt for the
#: WRONG operation on the same child/carrier can no longer pass.  All five
#: must be present as non-blank strings — Watcher evidence with any one
#: missing "grants no authority".
_WATCH_PROOF_FIELDS = (
    "watch_child_ref", "watch_operation", "watch_carrier_ref",
    "watch_mechanism", "watch_baseline_receipt",
)

#: Review 5103135217 BLOCKER 3: the closed Observer/Dialogue return-kind
#: vocabulary — the SAME three tokens ``sol_watcher_contract.py``'s
#: ACTION_AUTHORITATIVE role contract already names verbatim ("For an
#: in-scope BLOCKED, DECISION_REQUEST, or RESULT ...").  Reused here as a
#: plain string set rather than importing that module (which owns prompt
#: CONTRACT validation, not runtime dispatch evidence) — exactly the same
#: "reuse the literal wire values, never the module" idiom this file already
#: uses for ``obligation_status``/``WAKE_OUTCOME_TOKENS`` elsewhere.
_RETURN_KINDS = frozenset({"BLOCKED", "DECISION_REQUEST", "RESULT"})

#: Fields Blocker 3 requires on a genuine return receipt, over and above the
#: base watch proof: a closed ``return_kind``, the observed edge/reference,
#: and an observation time.  ``return_child_ref`` / ``return_operation`` /
#: ``return_carrier_ref`` are validated by EQUALITY against the matching
#: ``watch_*`` field (see :func:`_return_receipt_proven`) rather than mere
#: non-blankness — "exact child"/"exact operation"/carrier identity means
#: the receipt must name the SAME child/operation/carrier the watcher was
#: actually bound to, not merely carry some non-blank string.
_RETURN_RECEIPT_NONBLANK_FIELDS = (
    "return_child_ref", "return_operation", "return_carrier_ref",
    "return_edge_ref",
)


def _dispatch_nonblank(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _watch_proven(row: Mapping[str, Any]) -> bool:
    """Law 6 + Blocker 4: exact child + operation + carrier + mechanism +
    baseline receipt, all five, as non-blank strings.  This is necessary but
    not sufficient for a genuine RETURNED transition — see
    :func:`_return_receipt_proven` for the full Blocker 3 gate."""
    return all(_dispatch_nonblank(row.get(field)) for field in _WATCH_PROOF_FIELDS)


def _return_receipt_proven(row: Mapping[str, Any], generated_at: str) -> bool:
    """Blocker 3: "one validated exact-child Observer return receipt
    carrying a closed return kind (BLOCKED / DECISION_REQUEST / RESULT),
    exact operation + carrier/root identity, the observed edge/reference,
    and an observation time.  Attempt terminality ALONE is never a worker
    return."

    Requires (all of):
      - the base 5-field watch proof (:func:`_watch_proven`);
      - ``return_kind`` in the closed :data:`_RETURN_KINDS` vocabulary;
      - ``return_child_ref`` / ``return_operation`` / ``return_carrier_ref``
        each present AND byte-EQUAL to the corresponding ``watch_*`` field
        (the receipt must name the exact same child/operation/carrier the
        watcher was actually bound to — never merely "some" non-blank
        value, which is exactly BLOCKER 4's forgeability complaint);
      - ``return_edge_ref`` present and non-blank (the observed edge itself);
      - ``return_observed_at`` a parseable timestamp (the observation time).
    """
    if not _watch_proven(row):
        return False
    if row.get("return_kind") not in _RETURN_KINDS:
        return False
    for field in _RETURN_RECEIPT_NONBLANK_FIELDS:
        if not _dispatch_nonblank(row.get(field)):
            return False
    if row.get("return_child_ref") != row.get("watch_child_ref"):
        return False
    if row.get("return_operation") != row.get("watch_operation"):
        return False
    if row.get("return_carrier_ref") != row.get("watch_carrier_ref"):
        return False
    receipt_at = _parse_iso8601(row.get("return_observed_at"))
    if receipt_at is None:
        return False
    # Forward-bound it exactly as `_freshness_for` bounds `observed_at`
    # (review follow-up, 2026-09-03).  Parseability alone let a receipt
    # stamped 2999 read as a genuine return AND permanently foreclose
    # CONTINUED/STOPPED for that row, since no real decision can ever
    # postdate it.  Evidence from the future is not evidence.
    reference_at = _parse_iso8601(generated_at)
    if reference_at is not None and (receipt_at - reference_at) > FUTURE_SKEW_TOLERANCE:
        return False
    return True


def _dispatch_decision_within_skew(decision_dt: Any, generated_at: str) -> bool:
    """A decision timestamped beyond the forward skew tolerance is not evidence."""
    reference_at = _parse_iso8601(generated_at)
    if reference_at is None or decision_dt is None:
        return False
    return (decision_dt - reference_at) <= FUTURE_SKEW_TOLERANCE


def _dispatch_binding_unresolved(action_target_state: Any, binding_evidence_state: Any) -> tuple[bool, str | None]:
    """Law 7: "Missing/ambiguous/stale RuntimeBinding becomes RUNTIME_BINDING_
    RECONCILIATION_REQUIRED, not receiver selection by recency."  Returns
    ``(unresolved, reason)`` — never ``True`` with no named reason.

    - ambiguous: ``ActionTargetState.CONFLICT``.
    - missing:   ``ActionTargetState.UNAVAILABLE`` (the target resolver
      could not name a root target/runtime at all).
    - stale:     ``BindingEvidenceState.UNKNOWN`` (the binding snapshot
      itself carries no current evidence — see
      ``sol_action_target.RuntimeBindingSnapshot``).
    - genuinely unresolved: ``ActionTargetState.UNKNOWN`` (the resolver
      could not even classify the target) — treated the same conservative
      way; this module never guesses a receiver was validly selected from
      an unclassifiable target state.
    """
    if action_target_state == "CONFLICT":
        return True, "runtime_binding_conflict"
    if action_target_state == "UNAVAILABLE":
        return True, "runtime_binding_missing"
    if binding_evidence_state == "UNKNOWN":
        return True, "runtime_binding_evidence_unknown"
    if action_target_state == "UNKNOWN":
        return True, "runtime_binding_state_unknown"
    return False, None


def _dispatch_binding_absent(action_target_state: Any, binding_evidence_state: Any) -> bool:
    """True when the row carries NO binding evidence either way.

    Distinct from the declared problems above, and deliberately weaker.
    Declaring ``UNKNOWN`` was demoted while OMITTING the same two fields
    sailed through as a resolved, current binding — so a row that said
    nothing was trusted more than one that honestly said it did not know.
    That mattered in production: the gather omits exactly these fields when
    ``session_targets``/``sol_action_target`` are unavailable, which is the
    degraded release the optional-import machinery exists for, so the
    degraded reader rendered STARTED/RETURNED where the complete reader
    rendered RUNTIME_BINDING_RECONCILIATION_REQUIRED.  A degraded reader
    must never be more optimistic than a complete one.

    Scope is narrower than a declared problem, on purpose.  Absence blocks
    only ATTEMPT-derived progress (STARTED and everything past it), because
    those states claim a live runtime binding.  It does NOT overwrite
    delivery-derived states: a delivery is observed through the wake ledger
    and is true whether or not a RuntimeBinding was ever resolved, so
    demoting "delivered, never picked up" to a binding problem would
    replace one honest adverse state with a less informative one.
    """
    return action_target_state is None or binding_evidence_state is None


def _classify_dispatch_row(row: Mapping[str, Any], generated_at: str) -> tuple[str, str, bool]:
    """``(dispatch_state, reason, historical)`` for one matched evidence row.

    Pure: reads only ``row`` and the injected ``generated_at`` (via
    :func:`_freshness_for`, never a clock).  ``historical`` is Law 9's
    "stale/unknown contributing source" signal — computed from the row's own
    ``observed_at`` against ``generated_at``, independent of which state was
    derived, so a stale RETURNED reads exactly as historical as a stale
    DELIVERY_SENT.
    """
    _observed_at, freshness = _freshness_for(row.get("observed_at"), generated_at)
    historical = freshness is not Freshness.CURRENT

    # Law 8: "EFFECT_UNKNOWN outranks optimistic progress and disables every
    # actuator" — checked first, ahead of every other signal on the row.
    if row.get("effect_state") == "effect_unknown":
        return "EFFECT_UNKNOWN", "effect_unknown_reported", historical

    obligation_status = row.get("obligation_status")
    action_target_state = row.get("action_target_state")
    binding_evidence_state = row.get("binding_evidence_state")
    attempt_state = row.get("attempt_state")

    has_delivery_progress = obligation_status not in (None, "NOT_SEEN")
    has_attempt_progress = attempt_state is not None

    # A direct wake-ledger reconciliation signal always wins, regardless of
    # binding/attempt state (mission-suggested mapping, verified: this is
    # the module's own literal RECONCILIATION_REQUIRED code, reused as a
    # plain string exactly as WAKE_OUTCOME_TOKENS already reuses this
    # sibling module's literal wire values without importing it).
    if obligation_status == "RECONCILIATION_REQUIRED":
        return (
            "RUNTIME_BINDING_RECONCILIATION_REQUIRED",
            "wake_ledger_reconciliation_required",
            historical,
        )

    binding_unresolved, binding_reason = _dispatch_binding_unresolved(
        action_target_state, binding_evidence_state
    )
    if action_target_state == "CONFLICT":
        # An active conflict is always worth flagging, even pre-dispatch —
        # "post-START contradictory rebind": attempt evidence may still say
        # RUNNING/COMPLETED, but a rebind conflict must demote it every time.
        return "RUNTIME_BINDING_RECONCILIATION_REQUIRED", binding_reason, historical
    if binding_unresolved and (has_delivery_progress or has_attempt_progress):
        # Only a reconciliation problem once something is actually in
        # flight — an unresolved/unknown target with NO delivery/attempt
        # evidence yet is just "not dispatched", handled below.
        return "RUNTIME_BINDING_RECONCILIATION_REQUIRED", binding_reason, historical

    if has_attempt_progress and _dispatch_binding_absent(
        action_target_state, binding_evidence_state
    ):
        # Attempt evidence claims a live runtime binding, so it may not be
        # believed when the row carries no binding evidence at all.
        return (
            "RUNTIME_BINDING_RECONCILIATION_REQUIRED",
            "runtime_binding_evidence_absent",
            historical,
        )

    if has_attempt_progress:
        # Law 4: STARTED requires separate current start/Attempt evidence —
        # reached here only with a resolved, current binding (the gate
        # above already excluded every unresolved-binding case).
        if attempt_state in _ATTEMPT_IN_PROGRESS:
            return "STARTED", f"attempt_in_progress:{attempt_state}", historical
        if attempt_state in _ATTEMPT_TERMINAL:
            if not _return_receipt_proven(row, generated_at):
                # Blocker 3: "Attempt terminality ALONE is never a worker
                # return" — a terminal Attempt with no validated exact-child
                # Observer return receipt (closed return_kind + exact
                # operation/carrier identity + observed edge + observation
                # time) can never advance past this; RETURNED/CONTINUED/
                # STOPPED are all unavailable.
                return "WATCH_UNPROVEN", "watch_evidence_incomplete", historical
            return_dt = _parse_iso8601(row.get("return_observed_at"))
            decision = row.get("sol_decision")
            decision_carrier = row.get("sol_decision_carrier_ref")
            decision_child = row.get("sol_decision_child_ref")
            decision_operation = row.get("sol_decision_operation")
            decision_dt = _parse_iso8601(row.get("sol_decision_at"))
            carrier = row.get("watch_carrier_ref")
            child = row.get("watch_child_ref")
            operation = row.get("watch_operation")
            # Blocker 4: "CONTINUED/STOPPED must bind the SAME exact return
            # and a decision edge causally AFTER it."  A decision is trusted
            # only when it names the exact same child, operation and carrier
            # the proven return receipt named (never merely "a" same-carrier
            # decision — Law 5's original check, extended here to child +
            # operation too) AND its own timestamp parses and sits STRICTLY
            # after the return's own observation time.  A stale/at-or-before
            # decision, a wrong child/operation/carrier, or an unparseable
            # timestamp on either side all fail this and leave RETURNED
            # standing — never silently closing the dialogue.
            valid_decision = (
                decision in ("CONTINUE", "STOP")
                and _dispatch_nonblank(decision_carrier) and decision_carrier == carrier
                and _dispatch_nonblank(decision_child) and decision_child == child
                and _dispatch_nonblank(decision_operation) and decision_operation == operation
                and decision_dt is not None
                and return_dt is not None
                and decision_dt > return_dt
                # Forward-bounded exactly like `return_observed_at`
                # (review follow-up, 2026-09-03).  The earlier repair bounded
                # only the receipt, leaving this half of the same symmetric
                # hole open — and this is the WORSE half: `decision_dt >
                # return_dt` is the edge that moves a row OFF the only
                # actionable state, so a decision stamped in the future
                # silently discharged an owed Chairman decision. Fixing one
                # timestamp and not its sibling is how a closed finding stays
                # open.
                and _dispatch_decision_within_skew(decision_dt, generated_at)
            )
            if valid_decision and decision == "CONTINUE":
                return "CONTINUED", "sol_continue_same_carrier", historical
            if valid_decision and decision == "STOP":
                return "STOPPED", "sol_stop_same_carrier", historical
            return "RETURNED", "awaiting_sol_decision", historical
        return "UNKNOWN", f"unrecognized_attempt_state:{attempt_state}", historical

    # No Attempt evidence at all: Law 4 forbids inferring STARTED from
    # delivery/pickup evidence alone, so the ceiling here is
    # PICKUP_ACKNOWLEDGED.
    if obligation_status in _OBLIGATION_NO_ACK:
        return "DELIVERY_UNCONSUMED", f"obligation_status:{obligation_status}", historical
    if obligation_status in _OBLIGATION_PICKUP_ACK:
        return "PICKUP_ACKNOWLEDGED", f"obligation_status:{obligation_status}", historical
    if obligation_status == "ACCEPTED":
        return "DELIVERY_SENT", "obligation_status:ACCEPTED", historical
    if obligation_status in _OBLIGATION_NOT_YET_DELIVERED:
        if action_target_state == "RESOLVED":
            return "RECEIVER_SELECTED", "action_target_resolved_no_delivery_yet", historical
        return "WAITING_CAPACITY", "no_receiver_selected", historical
    return "UNKNOWN", f"unrecognized_obligation_status:{obligation_status}", historical


# ---------------------------------------------------------------------------
# Blocker 2 (review 5103135217): a closed, bounded, secret-safe validator in
# front of ``dispatch_evidence``.  ``project_dispatch_consumption`` used to
# accept caller-controlled mappings, assume ``.get``, copy arbitrary values
# into ``dispatch.evidence`` verbatim, and could echo unrecognized values in
# ``reason`` strings.  Every row now passes through
# :func:`_validate_dispatch_row` first: an exact closed key set, exact
# string-or-absent typing, closed token vocabularies where the field has
# one, bounded byte lengths, and a path/secret-shape refusal.  A row that
# fails ANY of those closes to the fixed, NON-ECHOING
# ``_DISPATCH_EVIDENCE_REJECTED`` reason — the offending key/value is never
# placed in any output string, and the ``evidence`` a caller sees is always
# rebuilt strictly from the validated/canonical fields, never from the raw
# input mapping.
# ---------------------------------------------------------------------------

#: The two mandatory join fields plus every optional data field this module
#: understands.  Anything outside this closed set fails the whole row
#: closed (Blocker 2: "unknown key").
_DISPATCH_JOIN_FIELDS = ("responsibility_ref", "root_job_id")
_DISPATCH_DATA_FIELDS = (
    "observed_at", "obligation_status", "action_target_state",
    "action_target_reason", "binding_evidence_state", "attempt_state",
    "effect_state", "watch_child_ref", "watch_operation", "watch_carrier_ref",
    "watch_mechanism", "watch_baseline_receipt", "return_kind",
    "return_child_ref", "return_operation", "return_carrier_ref",
    "return_edge_ref", "return_observed_at", "sol_decision",
    "sol_decision_carrier_ref", "sol_decision_child_ref",
    "sol_decision_operation", "sol_decision_at",
)
_DISPATCH_ALL_FIELDS = frozenset(_DISPATCH_JOIN_FIELDS + _DISPATCH_DATA_FIELDS)

#: Closed token vocabularies for fields whose value space is itself closed
#: (an owner enum's exact wire values, reused as plain strings — the same
#: "literal value, never the module" idiom this file already uses for
#: ``obligation_status`` elsewhere).  A field absent from this mapping is
#: still required to be a bounded, non-secret-shaped string, just not from a
#: closed vocabulary.
_DISPATCH_CLOSED_VOCAB: dict[str, frozenset[str]] = {
    "obligation_status": frozenset({
        "NOT_SEEN", "PENDING_RETRYABLE", "ATTEMPTED", "RECONCILIATION_REQUIRED",
        "ACCEPTED", "DELIVERED_UNACKNOWLEDGED", "TARGET_ACKNOWLEDGED",
        "SOURCE_RESOLVED",
    }),
    "action_target_state": frozenset({"RESOLVED", "UNAVAILABLE", "CONFLICT", "UNKNOWN"}),
    "action_target_reason": frozenset({
        "EXACT_RUNTIME_BINDING", "ACTOR_OBSERVER_ONLY", "ROOT_JOB_ID_MALFORMED",
        "ROOT_TARGET_MISSING", "ROOT_TARGET_CONFLICT", "BINDING_EVIDENCE_UNKNOWN",
        "TARGET_RUNTIME_UNAVAILABLE", "RUNTIME_BINDING_CONFLICT",
        "RUNTIME_BINDING_SURFACE_UNKNOWN", "RUNTIME_BINDING_SURFACE_CONFLICT",
    }),
    "binding_evidence_state": frozenset({"CURRENT", "UNKNOWN"}),
    "attempt_state": frozenset({
        "CLAIMED", "RUNNING", "CHECKPOINTED", "CANCEL_REQUESTED", "RATE_LIMITED",
        "FAILED", "LOST", "COMPLETED", "CANCELLED",
    }),
    "effect_state": frozenset({"none", "applied", "effect_unknown"}),
    "return_kind": frozenset(_RETURN_KINDS),
    "sol_decision": frozenset({"CONTINUE", "STOP"}),
}

#: Bounded lengths (bytes, UTF-8).  A join field is bounded tighter — it is
#: an identity, never free text.
_DISPATCH_JOIN_MAX_BYTES = 256
_DISPATCH_FIELD_MAX_BYTES = 512

#: Fixed, non-echoing rejection reason — Blocker 2: "No rejected input may
#: appear in any output string."
_DISPATCH_EVIDENCE_REJECTED = "dispatch_evidence_rejected"

#: Best-effort path/secret-shape refusal.  Deliberately conservative (a
#: handful of well-known shapes) rather than an attempted-exhaustive secret
#: scanner — this module's job is to refuse an evidence row that carries a
#: filesystem path or an obvious credential, not to be a general-purpose
#: secrets linter.
_DISPATCH_SECRET_OR_PATH_RE = re.compile(
    r"(?i)(^/|~/|\\|/etc/|/private/|/Users/|/home/|\.ssh|password|passwd"
    r"|secret|api[_-]?key|access[_-]?token|bearer\s|authorization\s*:"
    r"|-----BEGIN|AKIA[0-9A-Z]{16}"
    # Live-token prefixes an independent review proved were accepted and then
    # echoed verbatim into the rendered document (`sk-live-...` reached
    # `evidence.watch_mechanism` and the UI).  The earlier set matched only
    # `api_key`-style NAMES, so a leak test using a named key passed while a
    # bare token walked straight through.
    r"|sk-[A-Za-z0-9_-]{8,}|xox[abprs]-[A-Za-z0-9-]{8,}"
    r"|ghp_[A-Za-z0-9]{16,}|gho_[A-Za-z0-9]{16,}|glpat-[A-Za-z0-9_-]{16,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    # Google API keys and OAuth tokens, two more named families.
    r"|AIza[A-Za-z0-9_-]{10,}|ya29\.[A-Za-z0-9_.-]{10,}"
    # STRUCTURAL, not another named family.  Enumerating credential
    # prefixes is a losing shape: each round of "add the ones we missed"
    # still missed the next.  These fields carry identifiers, refs and
    # receipts, and no legitimate value of that kind contains a URL
    # scheme, an authority separator or an at-sign — so refusing those two
    # characters kills credential URLs (`postgres://user:pass@host`) and
    # e-mail addresses structurally, whatever their shape.
    r"|://|@)"
)


def _dispatch_looks_secret_or_path(value: str) -> bool:
    return bool(_DISPATCH_SECRET_OR_PATH_RE.search(value))


def _dispatch_safe_join_value(value: Any) -> bool:
    """True when usable as a join-key component: ``None`` (a card's own
    ``root_job_id`` is legitimately ``None`` for an unbound responsibility —
    Law 1 reuses whatever type the join key naturally is, it does not
    narrow it), or a bounded, non-blank, non-secret-shaped string.  A blank
    string is never a legitimate identity and is treated the same as a
    malformed one."""
    if value is None:
        return True
    return _dispatch_safe_str(value, max_bytes=_DISPATCH_JOIN_MAX_BYTES)


def _dispatch_safe_str(
    value: Any, *, max_bytes: int, vocab: frozenset[str] | None = None
) -> bool:
    """Exact type, bounded length, non-secret-shape, and (if closed) vocabulary."""
    if not isinstance(value, str) or isinstance(value, bool):
        return False
    if not value:
        return False
    try:
        encoded_len = len(value.encode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False
    if encoded_len == 0 or encoded_len > max_bytes:
        return False
    if _dispatch_looks_secret_or_path(value):
        return False
    if vocab is not None and value not in vocab:
        return False
    return True


def _dispatch_safe_keys(raw: Any) -> tuple[Any, ...] | None:
    """``raw.keys()`` without trusting caller-supplied ``Mapping`` code.

    ``_validate_dispatch_row`` documents "never raises", but a ``dict``
    subclass whose ``keys()`` raises would propagate straight out of the
    projection and take the whole document down — and unlike the
    ``placement_selection`` block beside it, the autonomy block is not
    wrapped.  An unreadable key set is simply an invalid row.
    """
    try:
        return tuple(raw.keys())
    except Exception:  # noqa: BLE001 - caller-supplied object, fail closed
        # None, NOT () — an unreadable key set is not an empty one.  Returning
        # () made the row look like it carried no unknown keys, so a mapping
        # whose keys() raised was ACCEPTED as a valid empty row and rendered
        # WAITING_CAPACITY.  A validator that cannot read the input cannot
        # attest to it.
        return None


def _validate_dispatch_row(
    raw: Any,
) -> tuple[Any, Any, dict[str, Any] | None]:
    """Never raises — enforced here, not merely documented.

    The previous revision said "never raises" while calling ``raw.keys()``,
    ``raw[field]``, ``field not in raw`` and ``raw.get(...)`` on
    caller-supplied objects; a mapping that raised in any of those took the
    whole document down, because unlike ``placement_selection`` the autonomy
    block is not wrapped.  Guarding one of the four was not enough: a
    docstring promise is only worth the boundary that enforces it.
    """
    try:
        return _validate_dispatch_row_inner(raw)
    except Exception:  # noqa: BLE001 - caller-supplied object, fail closed
        return None, None, None


def _validate_dispatch_row_inner(
    raw: Any,
) -> tuple[Any, Any, dict[str, Any] | None]:
    """Validate one caller-supplied evidence row.  Never raises.

    Returns ``(responsibility_ref, root_job_id, canonical_row_or_None)``.

    - A non-mapping row, or one whose join identity itself is unsafe/
      malformed (wrong type, blank, oversized, secret/path-shaped), cannot
      be attributed to any card at all: returns ``(None, None, None)`` —
      structurally equivalent to "this row was never sent" (it still
      cannot silently impersonate an existing card's join key).
    - A row whose join identity validates but carries an unknown key, a
      wrong-typed/oversized/secret-shaped/out-of-vocabulary data value
      closes to ``(ref, root_job_id, None)`` — the caller (``project_
      dispatch_consumption``) renders this card's dispatch state as
      ``UNKNOWN``/``_DISPATCH_EVIDENCE_REJECTED`` rather than silently
      treating it as absent, and the rejected value is dropped entirely
      (never copied into ``canonical_row``, so it can never reach
      ``evidence`` or any ``reason`` string).
    - A fully valid row returns ``(ref, root_job_id, canonical_row)`` where
      ``canonical_row`` contains ONLY the closed field set, each value
      already validated — the sole source ``evidence``/classification ever
      read from.
    """
    if not isinstance(raw, Mapping):
        return None, None, None

    keys = _dispatch_safe_keys(raw)
    if keys is None:
        # Explicit, not incidental: without this the `set(None)` below still
        # fails closed via the outer wrapper, but by accident of an exception
        # rather than by intent. A fail-closed path should say so.
        return None, None, None
    unknown_keys = set(keys) - _DISPATCH_ALL_FIELDS
    ref = raw.get("responsibility_ref")
    root_job_id = raw.get("root_job_id")
    if not _dispatch_safe_join_value(ref):
        return None, None, None
    if not _dispatch_safe_join_value(root_job_id):
        return None, None, None

    valid = not unknown_keys
    canonical: dict[str, Any] = {"responsibility_ref": ref, "root_job_id": root_job_id}
    for field in _DISPATCH_DATA_FIELDS:
        if field not in raw:
            continue
        value = raw[field]
        if value is None:
            continue
        if not _dispatch_safe_str(
            value,
            max_bytes=_DISPATCH_FIELD_MAX_BYTES,
            vocab=_DISPATCH_CLOSED_VOCAB.get(field),
        ):
            valid = False
            continue
        canonical[field] = value

    if not valid:
        return ref, root_job_id, None
    return ref, root_job_id, canonical


def project_dispatch_consumption(
    cards: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
    dispatch_evidence: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure, deterministic dispatch-consumption projection, one row per card.

    No I/O, no subprocess, no clock read, no environment read, no
    randomness, no mutation of ``cards``/``dispatch_evidence``.  Same
    arguments in -> byte-identical ``json.dumps(doc, sort_keys=True)`` out.

    ``cards`` is any sequence of mappings carrying ``responsibility_ref``
    and ``root_job_id`` — in practice :func:`project_autonomy`'s own
    ``responsibilities`` output, never re-derived here (Law 1: this module
    reuses that exact join key, it does not invent a second one).

    ``dispatch_evidence`` (optional, keyword-only, threaded exactly like
    ``project_autonomy``'s ``declared_blockers``/``unmapped_
    responsibilities``) is a sequence of already-gathered plain-data rows —
    one per ``(responsibility_ref, root_job_id)`` pair a caller has
    resolved via the real owners (``wake_ledger.reconstruct_status``,
    ``sol_action_target.resolve_sol_action_target``, an operator-continuity
    Attempt fact, an Agent Dialogue return receipt) — never fetched by this
    function itself.  Each row is validated (Blocker 2, see
    :func:`_validate_dispatch_row`) before anything else touches it and may
    carry: ``observed_at``, ``obligation_status``, ``action_target_state``,
    ``action_target_reason``, ``binding_evidence_state``, ``attempt_state``,
    ``effect_state``, ``watch_child_ref``, ``watch_operation``,
    ``watch_carrier_ref``, ``watch_mechanism``, ``watch_baseline_receipt``,
    ``return_kind``, ``return_child_ref``, ``return_operation``,
    ``return_carrier_ref``, ``return_edge_ref``, ``return_observed_at``,
    ``sol_decision``, ``sol_decision_carrier_ref``, ``sol_decision_child_ref``,
    ``sol_decision_operation``, ``sol_decision_at``.

    Absent, empty, unmatched, ambiguous (more than one row sharing the same
    exact join key), or REJECTED (a row that failed :func:`_validate_
    dispatch_row`) evidence renders that card's ``dispatch_state`` as
    ``"UNKNOWN"`` with a named, fixed, non-echoing ``reason`` — never a
    fabricated success stage (mission WHY: an absent/ambiguous/invalid fact
    must render as ignorance, never as progress) — AND always
    ``historical`` (Blocker 5: unknown/unmatched/ambiguous evidence carries
    unknown freshness, never the CURRENT-implying ``False`` default).

    Each output card carries:
      - ``dispatch_state``: one of :data:`DISPATCH_STATES`.
      - ``reason``: a short machine token naming the cause.
      - ``actionable``: ``True`` only for a fresh ``"RETURNED"`` card — the
        one state where a decision is genuinely owed to Sol AND the
        evidence backing it is current.  Never ``True`` for any of the
        five unsafe states, and never ``True`` when ``historical`` is
        ``True`` (Law 8's "disables every actuator" + Law 9's
        "non-actionable" apply identically here).
      - ``historical``: ``True`` whenever the row's own ``observed_at`` is
        stale or unknown relative to ``generated_at`` (Law 9), OR the
        evidence itself was absent/unmatched/ambiguous/rejected (Blocker 5)
        — computed independently of ``dispatch_state`` itself.
      - ``watch_proven``: Law 6/Blocker 4's five-field proof, always
        computed (even when irrelevant to the derived state) so a caller
        can inspect it.
      - ``evidence``: the matched row's validated, canonical, non-``None``
        fields — never the raw caller-supplied mapping — for forensic
        inspection.  ``None`` when no row was matched or the matched row
        was rejected (Blocker 2: a rejected value never reaches any
        output).

    ``counts`` is a closed histogram over every :data:`DISPATCH_STATES`
    token, always present (zero-filled), so a caller never has to guess
    whether a missing key means "zero" or "not computed".
    """
    try:
        # A caller-supplied iterable whose __iter__ raises must fail closed
        # like every other hostile input, not abort the document.
        try:
            evidence_rows = tuple(dispatch_evidence) if dispatch_evidence else ()
        except Exception:  # noqa: BLE001 - caller-supplied iterable, fail closed
            evidence_rows = ()
    except TypeError:
        evidence_rows = ()

    #: One list of ``canonical_row_or_None`` per exact join key.  ``None``
    #: entries mark a REJECTED row (Blocker 2) — kept in the list (rather
    #: than dropped) so a lone rejected row for an otherwise-unseen key
    #: still reads as "evidence was sent but refused", not silently as "no
    #: evidence was ever sent"; a rejected row alongside others still
    #: participates in ambiguity counting like any other row.
    lookup: dict[tuple[Any, Any], list[dict[str, Any] | None]] = {}
    for raw_row in evidence_rows:
        ref, root_job_id, canonical = _validate_dispatch_row(raw_row)
        if ref is None and root_job_id is None:
            continue  # join identity itself unsafe/malformed -> unattributable
        lookup.setdefault((ref, root_job_id), []).append(canonical)

    out_cards: list[dict[str, Any]] = []
    counts = {state: 0 for state in sorted(DISPATCH_STATES)}

    for card in cards:
        ref = card.get("responsibility_ref")
        root_job_id = card.get("root_job_id")
        matches = lookup.get((ref, root_job_id), [])

        if not evidence_rows:
            state, reason, historical = "UNKNOWN", "dispatch_evidence_not_supplied", True
            evidence: dict[str, Any] | None = None
            watch_proven = False
        elif len(matches) == 0:
            state, reason, historical = "UNKNOWN", "no_exact_join_match", True
            evidence = None
            watch_proven = False
        elif len(matches) > 1:
            state, reason, historical = "UNKNOWN", "ambiguous_dispatch_evidence", True
            evidence = None
            watch_proven = False
        elif matches[0] is None:
            state, reason, historical = "UNKNOWN", _DISPATCH_EVIDENCE_REJECTED, True
            evidence = None
            watch_proven = False
        else:
            row = matches[0]
            state, reason, historical = _classify_dispatch_row(row, generated_at)
            evidence = {k: v for k, v in sorted(row.items()) if v is not None}
            watch_proven = _watch_proven(row)

        actionable = state == "RETURNED" and not historical

        out_cards.append({
            "responsibility_ref": ref,
            "root_job_id": root_job_id,
            "dispatch_state": state,
            "reason": reason,
            "actionable": actionable,
            "historical": historical,
            "watch_proven": watch_proven,
            "evidence": evidence,
        })
        counts[state] += 1

    out_cards.sort(key=lambda c: (c["responsibility_ref"] or "", c["root_job_id"] or ""))

    return {
        "schema": DISPATCH_SCHEMA,
        "generated_at": generated_at,
        "cards": out_cards,
        "counts": counts,
    }


def attach_dispatch_consumption(
    autonomy: Mapping[str, Any],
    dispatch: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach each dispatch row to its card on the EXACT join key.

    Pure and non-mutating: returns a new document, leaves both inputs
    untouched.  The join is ``(responsibility_ref, root_job_id)`` and nothing
    else (Law 1) — a row whose pair matches no card is dropped rather than
    attached by title, provider label or recency, and a card with no matching
    row simply carries no ``dispatch`` field, which the UI renders as absence
    rather than as a successful stage.

    Kept here, beside the projection, rather than in the compositor: the join
    key belongs to this module and the compositor must not acquire a second
    copy of it.
    """
    rows = {
        (row.get("responsibility_ref"), row.get("root_job_id")): row
        for row in dispatch.get("cards", ())
    }
    cards: list[dict[str, Any]] = []
    for card in autonomy.get("responsibilities", ()):
        merged = dict(card)
        row = rows.get((card.get("responsibility_ref"), card.get("root_job_id")))
        if row is not None:
            merged["dispatch"] = dict(row)
        cards.append(merged)
    out = dict(autonomy)
    out["responsibilities"] = cards
    return out


def build_autonomy_snapshot(
    *,
    inbox: dict[str, Any] | None,
    boot_packet: dict[str, Any] | None,
    active_builds: dict[str, Any] | None,
    agent_os_state: dict[str, Any] | None,
    runtime_jobs: list[dict[str, Any]] | None,
    bindings: dict[str, Any] | None,
    generated_at: str | None = None,
) -> ExecutiveStewardSnapshot:
    """Pure mapping from the compositor's already-gathered inputs to a snapshot.

    Takes exactly the same plain-data arguments
    :func:`control_plane.chairman_control_room.compose_control_room` itself
    receives (this signature mirrors that function's parameter names and
    types on purpose) and returns one
    :class:`~control_plane.executive_steward.ExecutiveStewardSnapshot`.
    Gathers nothing on its own: no file I/O, no subprocess, no clock read,
    no environment read, no randomness, and no mutation of any argument.
    Same inputs in → an equal snapshot out, every time.

    ``generated_at`` (Fix 1, adversarial-review repair packet, 2026-09-01)
    is the same injected, clock-free reference timestamp
    :func:`project_autonomy` itself receives — the compositor's own
    ``generated_at`` (see ``control_plane.chairman_control_room.
    compose_control_room``), threaded straight through to every fact-
    construction helper below so a real, aged Agent OS/inbox/bindings
    document is honestly reported ``STALE`` rather than unconditionally
    ``CURRENT``.  Defaults to ``None`` (no reference — every constructed
    fact reads ``Freshness.UNKNOWN`` rather than guessing) so an existing
    caller that has not yet adopted this parameter degrades safely instead
    of silently asserting currency it cannot back up.

    ``active_builds`` and ``boot_packet`` are accepted (matching the
    compositor's own call signature and to keep this function
    forward-extensible) but not read: a GitHub open PR has no corresponding
    Steward fact type in this vocabulary, and ``ResponsibilityFact``
    construction is driven entirely by ``agent_os_state``'s own structured
    ``workstreams[]`` fields — see module docstring point 8 for the full
    evidence, and point 9 for why every constructed surface's
    ``reviewed_at`` is ``None``.  ``RuntimeFact`` is still never
    constructed (``runtime_jobs`` carries none of its required fields), and
    — bug-fix packet, 2026-09-01 — ``BlockerFact`` is never constructed by
    this function either: ``blockers`` on the returned snapshot is always
    ``()``.  ``agent_os_state``'s ``blocked_by``/``needs_ceo`` signal is
    real and is still surfaced, but honestly — call
    :func:`declared_blockers_from_agent_os_state` separately (same
    ``agent_os_state`` argument) and pass its result to
    :func:`project_autonomy`'s ``declared_blockers`` parameter.  This
    function's own return type stays exactly
    :class:`~control_plane.executive_steward.ExecutiveStewardSnapshot` —
    never a tuple, never a wrapper — so it remains a drop-in replacement
    for its own prior revision at every existing call site.

    ``source_failures`` on the returned snapshot is always ``()``
    (blast-radius repair packet, 2026-09-01): an unrecognized-owner row is
    a per-row mapping gap, not a genuine source-level outage, and a
    :class:`SourceFailure` is exactly the wrong container for it — the
    Steward folds every ``SourceFailure`` into the issues of every query it
    answers, so a handful of unmappable owner strings previously
    contaminated every other, correctly-read responsibility card.  Call
    :func:`unmapped_responsibilities_from_agent_os_state` separately (same
    ``agent_os_state`` argument) and pass its result to
    :func:`project_autonomy`'s ``unmapped_responsibilities`` parameter —
    the exact same shape of thread ``declared_blockers`` already uses.
    """
    del active_builds, boot_packet, runtime_jobs  # documented: unused (point 8)

    attention_facts = _attention_facts_from_inbox(inbox, generated_at)
    surface_facts = _surface_facts_from_bindings(bindings, generated_at)
    responsibility_facts, _seat_by_key, _unmapped = (
        _responsibility_facts_from_agent_os_state(agent_os_state, generated_at)
    )

    return ExecutiveStewardSnapshot(
        responsibilities=responsibility_facts,
        attention=attention_facts,
        runtimes=(),
        blockers=(),  # bug-fix packet, 2026-09-01: never fabricated here
        surfaces=surface_facts,
        # Blast-radius repair packet, 2026-09-01: an unrecognized owner is
        # never a SourceFailure any more — see
        # unmapped_responsibilities_from_agent_os_state.
        source_failures=(),
    )


__all__ = [
    "SCHEMA",
    "OUTPUT_KEYS",
    "WAKE_OUTCOME_TOKENS",
    "DISPATCH_SCHEMA",
    "DISPATCH_STATES",
    "project_autonomy",
    "project_dispatch_consumption",
    "build_autonomy_snapshot",
    "declared_blockers_from_agent_os_state",
    "unmapped_responsibilities_from_agent_os_state",
]
