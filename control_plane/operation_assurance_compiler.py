"""control_plane.operation_assurance_compiler — OLS-A2 pure source compiler.

Implements the pure (stdlib-only, zero-I/O) half of the bounded gather/
source-compiler seam per
docs/superpowers/specs/2026-09-01-operation-assurance-a2-source-seam-design.md
Sections 2 and 5.

Pipeline (design Section 2, implemented here in full):
    invocation-local ``mastermind.operation_assurance_source_facts.v1``
    -> presented to the EXISTING ``control_plane.executive_steward``
       composition (never copied, subclassed, or reimplemented)
    -> the accepted Steward result + the exact owner-native wave fields of
       the record it accepted
    -> one closed ``mastermind.operation_assurance_model.v1`` document with
       per-element ``source_refs``, run back through the PROTECTED A1
       parser (``control_plane.operation_assurance_model.parse_model_text``)
       so the emitted model is guaranteed to satisfy the exact same closed
       grammar the checker consumes — this module never hand-freezes a
       model_hash or a source_snapshot.snapshot_hash; the protected parser
       computes both.

Purity boundary (no-rebuild law, design Section 8): this module performs
zero network, socket, subprocess, filesystem, or clock I/O. It consumes only
the ``SourceFacts`` value handed to it. It does ZERO identity resolution,
deduplication, conflict election, or source normalization of its own — the
Steward is the only identity/source normalizer, reused as-is.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from control_plane.executive_steward import (
    ExecutiveStewardSnapshot,
    Freshness,
    QueryStatus,
    ResponsibilityFact,
    Seat,
    SourceFailure,
    SourceOwner,
    SourceRef,
)
from control_plane.operation_assurance_model import (
    OperationAssuranceModel,
    canonical_json,
    parse_model_text,
    sha256_hex,
)
from control_plane.operation_assurance_sources import (
    FIRST_TARGET_WORKSTREAM_KEY,
    HANDOFF_SCHEMA,
    REVISION_BINDING_GIT_HEAD_VERIFIED,
    STATUS_OK,
    STATUS_SOURCE_MISSING,
    STATUS_SOURCE_PARTIAL,
    STATUS_SOURCE_TRUNCATED,
    WORKSTREAM_SCHEMA,
    SourceFact,
    SourceFacts,
    derive_seat_token,
)

MODEL_SCHEMA = "mastermind.operation_assurance_model.v1"
PROPERTY_SET = "mastermind.operation_assurance.properties.v1"
SOURCE_SNAPSHOT_SCHEMA = "mastermind.operation_assurance.source_snapshot.v1"
COMPILER_NAME = "ols_a2_source_compiler"
COMPILER_VERSION = "1"

_WAVE_STATUS_TO_MARKING = {
    "todo": "PENDING",
    "in_progress": "ACTIVE",
    "awaiting_ci": "ACTIVE",
    "done": "DONE",
    "dropped": "DROPPED",
}
_NONTERMINAL_MARKINGS = frozenset({"PENDING", "ACTIVE"})
_TERMINAL_MARKINGS = frozenset({"DONE", "DROPPED"})
_WAVE_DOMAIN = ("ACTIVE", "DONE", "DROPPED", "PENDING")

# REPAIR B3 (Sol pre-review): workstream `status` -> operation's declared
# terminal/ongoing classification (design Section 5 bullet 5), mechanized
# as an agreement axis against the compiled wave markings rather than a
# note-only disclosure. `killed` is grouped with `done` (both are a closed
# organizational classification); every other status is "ongoing" —
# `parked` included, since "on hold" is not an assertion of completion.
# These groupings are a compiler-authored, disclosed judgment call (design
# Section 5's own "compiler-template, never owner-attested" principle), not
# a claim the real agentos schema itself makes this exact split.
_STATUS_CLASS_TERMINAL = frozenset({"done", "killed"})
_STATUS_CLASS_ONGOING = frozenset({"proposed", "active", "blocked", "awaiting_ci", "awaiting_review", "parked"})
STATUS_WAVE_CONFLICT_PROPERTY_ID = "WORKSTREAM_STATUS_WAVE_MARKING_CONFLICT"
STATUS_WAVE_CONFLICT_GAP_ID = "workstream_status_wave_marking_conflict"

# REPAIR R2 (Sol CONTINUE): machine-readable, ALWAYS-COMPILER-COMPUTED
# disclosure that the design Section 7 trust ceiling
# (PROVENANCE_CLOSED_UNATTESTED / AUTHOR_DECLARED_ONLY) has NOT been
# independently established for this compile. Because known_model_gaps is
# entirely compiler-authored (never read from the caller-supplied wire),
# this gap can never be suppressed or forged by a crafted
# --from-facts document — the compiler recomputes it fresh, every time,
# from facts.revision_binding alone.
SOURCE_ATTESTATION_UNAVAILABLE_GAP_ID = "source_attestation_unavailable"


class CompilerError(ValueError):
    """The whole compile call is refused. Carries a stable reason code."""

    def __init__(self, reason_code: str, message: str):
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _seat_source_owner(seat: str) -> Seat:
    return Seat(seat.lower())


def _wave_var(wave_id: str) -> str:
    return f"wave_{wave_id.lower()}"


_ALIAS_PREFIX = "oasrc_"


def _content_addressed_alias(repo: str, revision: str, path: str, digest: str) -> str:
    """REPAIR B4 (Sol pre-review): a schema-legal, deterministic,
    content-addressed alias over the FULL four-dimensional source identity
    (repo, revision, path, digest) — never a truncated ref that silently
    drops the revision or shortens the digest.

    The FROZEN SPEC's illustrative ``<repo>@<revision>:<path>#sha256:<digest>``
    template cannot satisfy the PROTECTED (unmodifiable) A1 model's
    ``_SOURCE_REF_RE`` (``^[A-Za-z0-9][A-Za-z0-9.:/_@-]{0,127}$`` — no
    ``#``) and 128-char ceiling for any repo+revision+path+digest of
    realistic length (see DEVIATIONS in the OLS-A2 packet). Rather than
    truncating any one of the four dimensions into the token itself (the
    B4 defect: the prior compact ref dropped the revision entirely and
    truncated the digest to 16 hex chars, both individually collision-prone
    across a re-gather at a new revision or a corrected record), this alias
    is the full sha256 of the canonical JSON of the exact four-tuple —
    collision-resistant over ALL four dimensions, changing whenever ANY one
    of them changes. The full tuple is recorded verbatim in
    ``abstraction_contract.notes``, keyed by this exact alias, so the
    mapping back to repo/revision/path/digest is always disclosed alongside
    the compact token used on every model element's ``source_refs``.
    """
    body = canonical_json([repo, revision, path, digest])
    return _ALIAS_PREFIX + sha256_hex(body)


def _full_source_note(alias: str, fact: SourceFact) -> str:
    return f"{alias} = {fact.repo}@{fact.revision}:{fact.path}#sha256:{fact.content_digest}"


def _build_steward_snapshot(facts: SourceFacts) -> tuple[ExecutiveStewardSnapshot, dict[str, SourceFact]]:
    """Present every OK workstream fact to the EXISTING Steward composition.

    Handoff records are never presented (design Section 2: they are
    evidence-only — SourceFailure disclosure stays scoped to the
    AGENT_OS-workstream family the Steward actually owns here). Returns the
    snapshot plus a lookup from the compact source-ref token back to the
    originating SourceFact, so the compiler can read wave detail from
    exactly the record the Steward accepted without reimplementing any
    Steward join logic.

    REPAIR FIX 6 (coordinator REQUEST_REPAIR, adversarial review): every
    non-OK workstream fact is also registered as a Steward ``SourceFailure``
    (owner=AGENT_OS) so a gather-time failure is visible in the Steward's
    own DEGRADED issues, not silently dropped just because it produced no
    ResponsibilityFact.
    """
    responsibilities: list[ResponsibilityFact] = []
    source_failures: list[SourceFailure] = []
    by_ref: dict[str, SourceFact] = {}
    for fact in facts.facts:
        if fact.record_schema != WORKSTREAM_SCHEMA:
            continue
        if fact.status != STATUS_OK:
            source_failures.append(
                SourceFailure(
                    owner=SourceOwner.AGENT_OS,
                    code=fact.status,
                    explanation=fact.reason or f"{fact.status} at {fact.path}",
                    source_ref=_content_addressed_alias(fact.repo, fact.revision, fact.path, fact.content_digest),
                    observed_at=fact.observed_at,
                )
            )
            continue
        payload = fact.payload or {}
        key = payload.get("key")
        seat_token = derive_seat_token(str(payload.get("owner", "")))
        if key is None or seat_token is None:
            # The adapter already refuses this shape (owner-seat grammar is
            # enforced at gather time); defensive skip only, never reached
            # via the adapter's own output.
            continue
        ref = f"WS:{key}"
        source_ref_token = _content_addressed_alias(fact.repo, fact.revision, fact.path, fact.content_digest)
        by_ref[source_ref_token] = fact
        responsibilities.append(
            ResponsibilityFact(
                responsibility_ref=ref,
                title=payload.get("title", ref),
                accountable_seat=_seat_source_owner(seat_token),
                state=payload.get("status"),
                root_job_id=None,
                source=SourceRef(
                    owner=SourceOwner.AGENT_OS,
                    ref=source_ref_token,
                    observed_at=fact.observed_at,
                    freshness=Freshness.UNKNOWN,
                ),
            )
        )
    snapshot = ExecutiveStewardSnapshot(
        responsibilities=tuple(responsibilities),
        source_failures=tuple(source_failures),
    )
    return snapshot, by_ref


def _target_workstream_facts(facts: SourceFacts, target_key: str) -> list[SourceFact]:
    target_path = f"agentos/workstreams/WS-{target_key}.md"
    out = []
    for fact in facts.facts:
        if fact.record_schema != WORKSTREAM_SCHEMA:
            continue
        if fact.path == target_path:
            out.append(fact)
            continue
        if fact.status == STATUS_OK and fact.payload and fact.payload.get("key") == target_key:
            out.append(fact)
    return out


def _refuse_for_missing_target(facts: SourceFacts, target_key: str) -> CompilerError:
    target_facts = _target_workstream_facts(facts, target_key)
    if any(f.status == STATUS_SOURCE_TRUNCATED for f in target_facts):
        return CompilerError("SOURCE_TRUNCATED", f"WS:{target_key} record was truncated at gather time")
    if any(f.status == STATUS_SOURCE_PARTIAL for f in target_facts):
        return CompilerError("SOURCE_PARTIAL", f"WS:{target_key} record failed frontmatter validation")
    if any(f.status == STATUS_SOURCE_MISSING for f in target_facts):
        return CompilerError("SOURCE_MISSING", f"WS:{target_key} has no record in the gathered source facts")
    return CompilerError("SOURCE_MISSING", f"WS:{target_key} has no record in the gathered source facts")


def _guard(variable: str, op: str, value: Any) -> dict:
    return {"variable": variable, "op": op, "value": value}


def _effect(variable: str, value: str) -> dict:
    return {"variable": variable, "value": value}


def _compile_waves(
    waves: list[dict],
    *,
    seat_token: str,
    ws_source_ref: str,
) -> tuple[dict, dict, list[dict], list[dict], list[dict], list[dict]]:
    """Returns (state_domains, initial_state, transitions, outcomes_guard_parts, obligations, gates)."""
    state_domains: dict[str, list[str]] = {}
    initial_state: dict[str, str] = {}
    transitions: list[dict] = []
    obligations: list[dict] = []
    gates: list[dict] = []
    terminal_guard_parts: list[dict] = []

    var_by_wave = {w["id"]: _wave_var(w["id"]) for w in waves}

    for wave in waves:
        wave_id = wave["id"]
        var = var_by_wave[wave_id]
        state_domains[var] = list(_WAVE_DOMAIN)
        marking = _WAVE_STATUS_TO_MARKING[wave["status"]]
        initial_state[var] = marking
        terminal_guard_parts.append(_guard(var, "IN", ["DONE", "DROPPED"]))

        if marking in _TERMINAL_MARKINGS:
            continue

        deps = wave.get("depends_on") or []
        next_action = wave.get("next_action")
        wait = wave.get("wait")

        current_marking = marking
        if deps and marking == "PENDING":
            # REPAIR FIX 1 (coordinator REQUEST_REPAIR, adversarial review):
            # only author the PENDING->ACTIVE gating transition when the
            # wave's OWN recorded status is still PENDING. When the record
            # already says the wave is ACTIVE (in_progress/awaiting_ci)
            # despite also declaring depends_on, the record's own status
            # field is authoritative for CURRENT position (design Section 5:
            # "compiler-template behavior grounded in exact record fields")
            # — the dependency gate has, by the record's own assertion,
            # already been cleared. A `start_<id>` transition guarded on
            # `var EQ PENDING` would be unsatisfiable from an ACTIVE initial
            # state and, marked required_reachable=True, would be a
            # permanently DEAD required transition: a FALSE
            # NO_DEAD_REQUIRED_TRANSITION witness naming a perfectly healthy
            # record.
            dep_guards = [_guard(var, "EQ", "PENDING")]
            for dep_id in deps:
                dep_guards.append(_guard(var_by_wave[dep_id], "IN", ["DONE", "DROPPED"]))
            transitions.append(
                {
                    "transition_id": f"start_{wave_id.lower()}",
                    "kind": "MODIFY",
                    "actor_class": "WORKER",
                    "authority_requirement": "NONE",
                    "guards": dep_guards,
                    "effects": [_effect(var, "ACTIVE")],
                    "progress_tags": ["PROGRESS"],
                    "source_refs": [ws_source_ref],
                    "fairness_ref": None,
                    "external_assumption_ref": None,
                    "gate_refs": [],
                    "required_reachable": True,
                }
            )
            current_marking = "ACTIVE"

        if wait is not None:
            gate_id = f"gate_{wave_id.lower()}"
            finish_id = f"finish_via_gate_{wave_id.lower()}"
            gate_guard = _guard(var, "EQ", current_marking)
            transitions.append(
                {
                    "transition_id": finish_id,
                    "kind": "MODIFY",
                    "actor_class": "EXTERNAL",
                    "authority_requirement": str(wait.get("kind")),
                    "guards": [gate_guard],
                    "effects": [_effect(var, "DONE")],
                    "progress_tags": ["PROGRESS"],
                    "source_refs": [ws_source_ref],
                    "fairness_ref": None,
                    "external_assumption_ref": None,
                    "gate_refs": [gate_id],
                    "required_reachable": False,
                }
            )
            gates.append(
                {
                    "gate_id": gate_id,
                    "disposition": wait["kind"],
                    "state_guards": [gate_guard],
                    "owner_or_authority": seat_token,
                    "release_condition": str(
                        wait.get("condition") or "external release recorded through exact carrier"
                    ),
                    "release_transition_ids": [finish_id],
                    "return_or_observation_source": "agentos workstream wave record",
                    "wake_or_review_path": "existing Wake or explicit workstream update",
                    "time_contract": "no synthetic TTL; source-owned review boundary",
                    "correction_contract": "a later gather at a new revision supersedes this projection",
                    "escalation_or_close_path": finish_id,
                    "source_refs": [ws_source_ref],
                }
            )
        elif next_action:
            finish_id = f"finish_{wave_id.lower()}"
            transitions.append(
                {
                    "transition_id": finish_id,
                    "kind": "MODIFY",
                    "actor_class": "WORKER",
                    "authority_requirement": "NONE",
                    "guards": [_guard(var, "EQ", current_marking)],
                    "effects": [_effect(var, "DONE")],
                    "progress_tags": ["PROGRESS"],
                    "source_refs": [ws_source_ref],
                    "fairness_ref": None,
                    "external_assumption_ref": None,
                    "gate_refs": [],
                    "required_reachable": True,
                }
            )
            obligations.append(
                {
                    "obligation_id": f"next_action_{wave_id.lower()}",
                    "kind": "NEXT_ACTION_OBLIGATION",
                    "state_variable": var,
                    "pending_values": [current_marking],
                    "discharged_values": ["DONE"],
                    "persistent": False,
                    "owner_or_authority": seat_token,
                    "source_refs": [ws_source_ref],
                }
            )
        # else: no wait and no next_action -> no completion transition is
        # authored for this wave at all. If it also has no depends_on, this
        # is the organizational black hole design Section 5 requires this
        # vertical to detect: zero outgoing transitions, ever.

    return state_domains, initial_state, transitions, terminal_guard_parts, obligations, gates


def _unsupported_scope_gaps(transition_ids: list[str]) -> list[dict]:
    gaps = [
        {
            "gap_id": "unsupported_starvation_and_fairness_realizability",
            "reason": (
                "design Section 5 unsupported subset: a static workstream snapshot authors no "
                "scheduler/fairness assumptions, so starvation-under-declared-fairness and "
                "fairness realizability are out of scope for this vertical"
            ),
            "load_bearing": True,
            "affects_property_ids": ["NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE"],
            "affects_transition_ids": [],
            "affects_variable_ids": [],
            "source_refs": [],
        },
        {
            "gap_id": "unsupported_recurring_progress_validity",
            "reason": (
                "design Section 5 unsupported subset: recurring-progress validity is out of "
                "scope unless a wave declares a recurring wait; none does in this compile"
            ),
            "load_bearing": True,
            "affects_property_ids": ["RECURRING_PROGRESS_VALID"],
            "affects_transition_ids": [],
            "affects_variable_ids": [],
            "source_refs": [],
        },
    ]
    if transition_ids:
        gaps.append(
            {
                "gap_id": "unsupported_retry_effect_unknown_semantics",
                "reason": (
                    "design Section 5 unsupported subset: retry/effect-unknown semantics are "
                    "not modeled; every compiler-authored transition is a single idempotent "
                    "template step, not an owner-attested runtime effect"
                ),
                "load_bearing": True,
                "affects_property_ids": [],
                "affects_transition_ids": sorted(transition_ids),
                "affects_variable_ids": [],
                "source_refs": [],
            }
        )
        gaps.append(
            {
                "gap_id": "unsupported_runtime_lifecycle_conformance",
                "reason": (
                    "design Section 5 unsupported subset: runtime lifecycle conformance "
                    "(attempt/session/binding behavior) is not modeled by a static workstream "
                    "snapshot compile"
                ),
                "load_bearing": True,
                "affects_property_ids": [],
                "affects_transition_ids": sorted(transition_ids),
                "affects_variable_ids": [],
                "source_refs": [],
            }
        )
    return gaps


def _attestation_unavailable_gap(facts: SourceFacts) -> dict | None:
    """REPAIR R2: None only when this exact invocation independently
    established GIT_HEAD_VERIFIED (design Section 4/7's own ceiling —
    gathering with correct receipts still never mints CURRENT_SOURCE_ATTESTED
    on its own, but a live, matching git HEAD is at least the honest
    non-forgeable floor this vertical can establish). Every other case —
    including a forged/serialized claim of GIT_HEAD_VERIFIED, which
    from_dict/from_json_bytes already downgrade before this function ever
    sees it — gets the load-bearing gap. affects_property_ids names
    OPTION_TO_COMPLETE, a GENERIC_MANDATORY property present in every
    compiled model, so the gap always resolves to >=1 real identity
    regardless of how many transitions this specific compile produced.
    """
    if facts.revision_binding == REVISION_BINDING_GIT_HEAD_VERIFIED:
        return None
    return {
        "gap_id": SOURCE_ATTESTATION_UNAVAILABLE_GAP_ID,
        "reason": (
            f"design Section 7 trust ceiling: revision_binding={facts.revision_binding!r} — no accepted "
            "attestation capability establishes CURRENT_SOURCE_ATTESTED for this compile; it stays "
            "PROVENANCE_CLOSED_UNATTESTED / AUTHOR_DECLARED_ONLY. A serialized claim of "
            "GIT_HEAD_VERIFIED on --from-facts ingest is never trusted on its own and cannot suppress "
            "or forge past this gap."
        ),
        "load_bearing": True,
        "affects_property_ids": ["OPTION_TO_COMPLETE"],
        "affects_transition_ids": [],
        "affects_variable_ids": [],
        "source_refs": [],
    }


def _status_wave_agreement_conflict(
    status: str, initial_state: dict[str, str], ws_source_ref: str
) -> tuple[dict | None, dict | None]:
    """REPAIR B3 (Sol pre-review): mechanize the workstream-status/wave-
    marking agreement axis instead of leaving it a note-only disclosure.

    Returns (safety_property, model_gap) — both None when status and wave
    markings AGREE. On DISAGREEMENT, returns a declared STATE_FORBIDDEN
    safety property whose violation_when is pinned to the EXACT initial
    state (the conflict is a compile-time fact, known before any
    exploration — the checker reports it as an immediate FAIL with a
    real, source-attributed witness) plus a load-bearing known_model_gap
    naming it, so neither false closure (status=done while work is still
    open) nor false ongoing state (status=active while every wave has
    already resolved) can compile silently into a clean-looking model.
    """
    all_waves_terminal = all(marking in _TERMINAL_MARKINGS for marking in initial_state.values())
    if status in _STATUS_CLASS_TERMINAL:
        agree = all_waves_terminal
        disagreement = "status is terminal-class (done/killed) but at least one wave is still non-terminal"
    elif status in _STATUS_CLASS_ONGOING:
        agree = not all_waves_terminal
        disagreement = "status is ongoing-class but every wave already carries a terminal marking"
    else:  # pragma: no cover - defense in depth; the adapter's closed status enum forecloses this
        agree = True
        disagreement = ""
    if agree:
        return None, None

    conflict_guards = [_guard(var, "EQ", value) for var, value in sorted(initial_state.items())]
    safety_property = {
        "property_id": STATUS_WAVE_CONFLICT_PROPERTY_ID,
        "kind": "STATE_FORBIDDEN",
        "violation_when": conflict_guards,
        "source_refs": [ws_source_ref],
    }
    model_gap = {
        "gap_id": STATUS_WAVE_CONFLICT_GAP_ID,
        "reason": f"workstream status {status!r} disagrees with the compiled wave markings: {disagreement}",
        "load_bearing": True,
        "affects_property_ids": [STATUS_WAVE_CONFLICT_PROPERTY_ID],
        "affects_transition_ids": [],
        "affects_variable_ids": sorted(initial_state.keys()),
        "source_refs": [ws_source_ref],
    }
    return safety_property, model_gap


def _relevant_facts(facts: SourceFacts, target_fact: SourceFact, ref: str) -> list[SourceFact]:
    """REPAIR FIX 7 (coordinator REQUEST_REPAIR, real-gather proof):
    ``source_snapshot.sources`` and ``abstraction_contract.notes`` must carry
    only the sources the compiled model actually DERIVES FROM — the target
    workstream record, plus the handoff records whose own declared
    ``workstream`` key names this exact target. Against the real macro
    agentos tree (57+ workstreams, ~398 handoffs) presenting the WHOLE
    gathered family blew the protected A1 parser's
    ``MAX_NESTED_COLLECTION_ITEMS`` ceiling on ``abstraction_contract.notes``
    (default 256). The family-wide scan itself is UNCHANGED (identity
    resolution / conflict detection still sees every gathered fact via
    ``_build_steward_snapshot`` above); only what gets MATERIALIZED into the
    model is scoped down. The family-wide census is preserved as bounded
    per-family counts via ``_family_census_notes`` instead of one entry per
    record.
    """
    relevant = [target_fact]
    for fact in facts.facts:
        if fact is target_fact:
            continue
        if fact.record_schema != HANDOFF_SCHEMA or fact.status != STATUS_OK or not fact.payload:
            continue
        if fact.payload.get("workstream") == ref:
            relevant.append(fact)
    relevant.sort(key=lambda f: f.path)
    return relevant


def _family_census_notes(facts: SourceFacts) -> list[str]:
    """Bounded (one line per record FAMILY, never per record) disclosure of
    the whole-tree gather census: records scanned, conflicts found,
    truncations — satisfies "the family-wide census moves to... bounded
    counts" without reintroducing an unbounded per-record note."""
    conflict_counts: dict[str, int] = {}
    for fact in facts.facts:
        if fact.conflict == "CONFLICT":
            conflict_counts[fact.record_schema] = conflict_counts.get(fact.record_schema, 0) + 1
    notes = []
    for cov in sorted(facts.coverage, key=lambda c: c.record_schema):
        notes.append(
            f"family census {cov.record_schema}: attempted={cov.attempted} ok={cov.ok} "
            f"truncated_family={cov.truncated} conflicted_facts={conflict_counts.get(cov.record_schema, 0)}"
        )
    return notes


def _build_source_snapshot(relevant_facts: list[SourceFact]) -> dict:
    sources = []
    for fact in relevant_facts:
        if fact.status == STATUS_OK:
            coverage = "COMPLETE"
        elif fact.status == STATUS_SOURCE_MISSING:
            coverage = "UNKNOWN"
        else:
            coverage = "PARTIAL"
        sources.append(
            {
                "owner": "AGENT_OS",
                "source_kind": "WORKSTREAM_RECORD" if fact.record_schema == WORKSTREAM_SCHEMA else "HANDOFF_RECORD",
                "source_identity": fact.path,
                "schema_version": fact.record_schema,
                "digest": fact.content_digest,
                "effective_at": None,
                "observed_at": fact.observed_at,
                "correction_ref": None,
                "freshness": "UNKNOWN",
                "conflict": fact.conflict,
                "coverage": coverage,
                "truncated": fact.status == STATUS_SOURCE_TRUNCATED,
                "continuation": None,
            }
        )
    sources.sort(key=lambda s: s["source_identity"])
    body = {"schema": SOURCE_SNAPSHOT_SCHEMA, "sources": sources}
    snapshot_hash = sha256_hex(canonical_json(body))
    return {**body, "snapshot_hash": snapshot_hash}


def compile_operation_assurance_model(
    facts: SourceFacts,
    *,
    target_workstream_key: str = FIRST_TARGET_WORKSTREAM_KEY,
) -> OperationAssuranceModel:
    """Pure: compiles gathered ``SourceFacts`` into one closed A1 model.

    Feeds every OK ``agentos.workstream.v1`` fact through the EXISTING
    Steward composition (never a second Steward, never side-read), then
    compiles only the record the Steward accepted for
    ``WS:<target_workstream_key>`` (design Section 5's frozen first target).
    Handoff facts are folded into ``source_snapshot`` for disclosure only —
    they are never presented to the Steward and never drive state/transition
    construction (design Section 2).
    """
    if not isinstance(facts, SourceFacts):
        raise CompilerError("INVALID_SOURCE_BUNDLE", "facts must be a SourceFacts value")

    snapshot, by_ref = _build_steward_snapshot(facts)
    ref = f"WS:{target_workstream_key}"
    result = snapshot.get_responsibility(ref)

    if result.status == QueryStatus.UNKNOWN:
        raise _refuse_for_missing_target(facts, target_workstream_key)
    if result.status == QueryStatus.REFUSED:
        raise CompilerError("SOURCE_CONFLICTED", f"{ref} has more than one candidate Agent OS record")
    if result.data is None:
        # REPAIR FIX 6 (coordinator REQUEST_REPAIR, adversarial review):
        # QueryStatus.DEGRADED with data=None is a real Steward outcome
        # (executive_steward.get_responsibility returns it when there are
        # zero matching responsibility facts AND non-empty source issues —
        # reachable now that non-OK workstream facts are registered as
        # SourceFailure above). Refuse typed instead of crashing on
        # `responsibility.accountable_seat` below.
        raise _refuse_for_missing_target(facts, target_workstream_key)

    responsibility: ResponsibilityFact = result.data
    fact = by_ref.get(responsibility.source.ref)
    if fact is None:  # pragma: no cover - defense in depth, unreachable via the adapter
        raise CompilerError("INVALID_SOURCE_BUNDLE", "accepted responsibility has no traceable source fact")

    payload = fact.payload or {}
    waves = payload.get("waves") or []
    seat_token = responsibility.accountable_seat.value.upper()
    ws_source_ref = _content_addressed_alias(fact.repo, fact.revision, fact.path, fact.content_digest)

    (
        state_domains,
        initial_state,
        transitions,
        terminal_guard_parts,
        obligations,
        gates,
    ) = _compile_waves(waves, seat_token=seat_token, ws_source_ref=ws_source_ref)

    terminal_outcomes = [
        {
            "outcome_id": "all_waves_resolved",
            "kind": "TERMINAL_SUCCESS",
            "guards": terminal_guard_parts,
            "owned_persistent_obligation_ids": [],
            "owned_persistent_resource_ids": [],
            "source_refs": [ws_source_ref],
        }
    ]

    transition_ids = [t["transition_id"] for t in transitions]
    known_model_gaps = _unsupported_scope_gaps(transition_ids)

    # REPAIR B3: mechanize the workstream-status/wave-marking agreement
    # axis. A disagreement adds a declared FAILing safety property plus a
    # load-bearing gap naming it — never a silent, apparently-healthy
    # compile.
    status_conflict_property, status_conflict_gap = _status_wave_agreement_conflict(
        payload.get("status"), initial_state, ws_source_ref
    )
    safety_properties = [status_conflict_property] if status_conflict_property else []
    if status_conflict_gap:
        known_model_gaps.append(status_conflict_gap)

    # REPAIR R2: always compiler-computed from facts.revision_binding alone
    # — never from anything the caller-supplied wire could set directly.
    attestation_gap = _attestation_unavailable_gap(facts)
    if attestation_gap:
        known_model_gaps.append(attestation_gap)

    relevant_facts = _relevant_facts(facts, fact, ref)

    notes = [
        _full_source_note(_content_addressed_alias(f.repo, f.revision, f.path, f.content_digest), f)
        for f in relevant_facts
    ]
    notes.append(f"workstream status (source-declared organizational classification): {payload.get('status')}")
    notes.append(
        "compiler-template state machine grounded in exact wave/dependency/next_action/wait "
        "fields of the accepted Agent OS record; never presented as owner-attested runtime fact "
        "or current operational proof (design Section 5)"
    )
    # REPAIR B2: the revision binding is disclosed on every compile, not
    # just when it is the honest, unverified default — applicability stays
    # capped at UNKNOWN either way; this is disclosure, never a promotion.
    notes.append(f"revision_binding: {facts.revision_binding}")
    notes.extend(_family_census_notes(facts))

    doc = {
        "schema": MODEL_SCHEMA,
        "model_id": f"om_a2_{target_workstream_key.lower().replace('-', '_')}_{fact.revision[:12]}",
        "operation_ref": {
            "operation_key": f"ws_{target_workstream_key.lower().replace('-', '_')}",
            "root_job_id": None,
            "pre_admission_identity": f"{ref}@{fact.repo}@{fact.revision}",
        },
        "compiler": {
            "name": COMPILER_NAME,
            "version": COMPILER_VERSION,
            "invocation_mode": "AUTHORED_INPUT",
        },
        "source_snapshot": _build_source_snapshot(relevant_facts),
        "abstraction_contract": {
            "kind": "SOUND_OVERAPPROXIMATION",
            "concrete_scope": (
                f"compiler-template state machine over the waves of {ref} recorded at "
                f"{fact.repo}@{fact.revision}; mechanically derived from schema-valid "
                "wave/depends_on/next_action/wait fields only — not owner-attested runtime fact"
            ),
            "preserves": ["REACHABLE_COUNTEREXAMPLE"],
            "introduced_behavior": "MAY_EXIST",
            "excluded_behavior": "KNOWN_PRESENT",
            "validation_kind": "AUTHOR_DECLARATION",
            "validation_refs": [ws_source_ref],
            "notes": notes,
        },
        "state_domains": state_domains,
        "initial_state": initial_state,
        "transitions": transitions,
        "terminal_outcomes": terminal_outcomes,
        "recurring_progress_outcomes": [],
        "obligations": obligations,
        "resources": [],
        "external_gates": gates,
        "fairness_assumptions": [],
        "environment_assumptions": [],
        "safety_properties": safety_properties,
        "property_set": PROPERTY_SET,
        "exploration_limits": {"max_states": 50_000, "max_depth": 5_000},
        "known_model_gaps": known_model_gaps,
    }

    try:
        return parse_model_text(json.dumps(doc))
    except Exception as exc:  # noqa: BLE001 - re-raise as a compiler-owned refusal
        raise CompilerError("INVALID_SOURCE_BUNDLE", f"compiled document was refused by the protected A1 parser: {exc}") from exc
