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


class CompilerError(ValueError):
    """The whole compile call is refused. Carries a stable reason code."""

    def __init__(self, reason_code: str, message: str):
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _seat_source_owner(seat: str) -> Seat:
    return Seat(seat.lower())


def _wave_var(wave_id: str) -> str:
    return f"wave_{wave_id.lower()}"


def _compact_source_ref(repo: str, path: str, digest: str) -> str:
    """Compact, schema-legal per-element source ref.

    See DEVIATIONS in the OLS-A2 packet: the FROZEN SPEC's illustrative
    ``<repo>@<revision>:<path>#sha256:<digest>`` template cannot satisfy the
    PROTECTED (unmodifiable) A1 model's ``_SOURCE_REF_RE``
    (``^[A-Za-z0-9][A-Za-z0-9.:/_@-]{0,127}$`` — no ``#``) and 128-char
    ceiling for any repo+revision+path+digest of realistic length; the exact
    full-fidelity string (including the un-abbreviated revision) is instead
    recorded verbatim in ``abstraction_contract.notes`` for every source.
    """
    return f"{repo}:{path}:{digest[:16]}"


def _full_source_note(fact: SourceFact) -> str:
    return f"source: {fact.repo}@{fact.revision}:{fact.path}#sha256:{fact.content_digest}"


def _build_steward_snapshot(facts: SourceFacts) -> tuple[ExecutiveStewardSnapshot, dict[str, SourceFact]]:
    """Present every OK workstream fact to the EXISTING Steward composition.

    Handoff records are never presented (design Section 2: they are
    evidence-only). Returns the snapshot plus a lookup from the compact
    source-ref token back to the originating SourceFact, so the compiler can
    read wave detail from exactly the record the Steward accepted without
    reimplementing any Steward join logic.
    """
    responsibilities: list[ResponsibilityFact] = []
    by_ref: dict[str, SourceFact] = {}
    for fact in facts.facts:
        if fact.record_schema != WORKSTREAM_SCHEMA or fact.status != STATUS_OK:
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
        source_ref_token = _compact_source_ref(fact.repo, fact.path, fact.content_digest)
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
    snapshot = ExecutiveStewardSnapshot(responsibilities=tuple(responsibilities))
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
        if deps:
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
            # once gated, the record only ever declares the wave ACTIVE for
            # the purpose of a finish transition below.
            current_marking = "ACTIVE" if marking == "PENDING" else marking

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
                    "release_condition": str(wait.get("on") or "external release recorded through exact carrier"),
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


def _build_source_snapshot(facts: SourceFacts) -> dict:
    sources = []
    for fact in facts.facts:
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

    responsibility: ResponsibilityFact = result.data
    fact = by_ref.get(responsibility.source.ref)
    if fact is None:  # pragma: no cover - defense in depth, unreachable via the adapter
        raise CompilerError("INVALID_SOURCE_BUNDLE", "accepted responsibility has no traceable source fact")

    payload = fact.payload or {}
    waves = payload.get("waves") or []
    seat_token = responsibility.accountable_seat.value.upper()
    ws_source_ref = _compact_source_ref(fact.repo, fact.path, fact.content_digest)

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

    notes = [_full_source_note(f) for f in sorted(facts.facts, key=lambda f: f.path)]
    notes.append(f"workstream status (source-declared organizational classification): {payload.get('status')}")
    notes.append(
        "compiler-template state machine grounded in exact wave/dependency/next_action/wait "
        "fields of the accepted Agent OS record; never presented as owner-attested runtime fact "
        "or current operational proof (design Section 5)"
    )

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
        "source_snapshot": _build_source_snapshot(facts),
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
        "safety_properties": [],
        "property_set": PROPERTY_SET,
        "exploration_limits": {"max_states": 50_000, "max_depth": 5_000},
        "known_model_gaps": known_model_gaps,
    }

    try:
        return parse_model_text(json.dumps(doc))
    except Exception as exc:  # noqa: BLE001 - re-raise as a compiler-owned refusal
        raise CompilerError("INVALID_SOURCE_BUNDLE", f"compiled document was refused by the protected A1 parser: {exc}") from exc
