"""tests.test_operation_assurance_a2_compiler — OLS-A2 pure source compiler.

Covers control_plane.operation_assurance_compiler: Steward composition is
mandatory and real, freshness is always UNKNOWN, wave/dependency mapping,
per-element source_refs, and the mechanized SOUND_OVERAPPROXIMATION fidelity
ceiling (design Sections 2 and 5).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.operation_assurance_compiler import CompilerError, compile_operation_assurance_model
from control_plane.operation_assurance_sources import gather_agent_os_source_facts

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "operation_assurance_a2"
REV = "a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4"


def _facts(name: str, **overrides):
    kwargs = dict(repo="mastermindx-market-intelligence/macro", revision=REV, observed_at="2026-09-02T00:00:00Z")
    kwargs.update(overrides)
    return gather_agent_os_source_facts(FIXTURES / name, **kwargs)


def _compile(name: str, **overrides):
    return compile_operation_assurance_model(_facts(name, **overrides))


def _edit_target_payload(facts, mutate, *, target_key: str = "OPERATION-ASSURANCE"):
    """Apply an in-memory, one-lawful-edit mutation to the accepted target
    workstream fact's already-parsed payload, leaving every other fact
    untouched — the same pattern the FIX-1-repro test above uses."""
    import dataclasses

    from control_plane.operation_assurance_sources import STATUS_OK

    new_facts = []
    for fact in facts.facts:
        if fact.status == STATUS_OK and fact.payload and fact.payload.get("key") == target_key:
            payload = dict(fact.payload)
            mutate(payload)
            fact = dataclasses.replace(fact, payload=payload)
        new_facts.append(fact)
    return dataclasses.replace(facts, facts=tuple(new_facts))


# ---------------------------------------------------------------------------
# Refusals mirror the adapter's SOURCE_* states 1:1 (design Section 9: fail
# closed, never an apparently healthy compilation)
# ---------------------------------------------------------------------------


def test_missing_target_refuses_with_source_missing() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("missing")
    assert exc.value.reason_code == "SOURCE_MISSING"


def test_conflicted_target_refuses_with_source_conflicted() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("conflict")
    assert exc.value.reason_code == "SOURCE_CONFLICTED"


def test_malformed_target_refuses_with_source_partial() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("malformed")
    assert exc.value.reason_code == "SOURCE_PARTIAL"


def test_truncated_target_refuses_with_source_truncated() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("truncated")
    assert exc.value.reason_code == "SOURCE_TRUNCATED"


# ---------------------------------------------------------------------------
# Mandatory proof ceiling (design Section 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["hostile", "corrected", "black_hole", "wait_gate"])
def test_abstraction_contract_is_always_sound_overapproximation_never_declared_exact(name: str) -> None:
    model = _compile(name)
    assert model.abstraction_contract.kind == "SOUND_OVERAPPROXIMATION"
    assert model.abstraction_contract.kind != "DECLARED_EXACT"


@pytest.mark.parametrize("name", ["hostile", "corrected", "black_hole", "wait_gate"])
def test_source_snapshot_freshness_is_always_unknown_never_current_or_fresh(name: str) -> None:
    model = _compile(name)
    assert model.source_snapshot.sources, "expected at least one disclosed source"
    for record in model.source_snapshot.sources:
        assert record.freshness == "UNKNOWN"


@pytest.mark.parametrize("name", ["hostile", "corrected", "black_hole", "wait_gate"])
def test_known_model_gaps_disclose_the_unsupported_property_subset(name: str) -> None:
    model = _compile(name)
    gap_ids = {g.gap_id for g in model.known_model_gaps}
    assert "unsupported_starvation_and_fairness_realizability" in gap_ids
    assert "unsupported_recurring_progress_validity" in gap_ids
    for gap in model.known_model_gaps:
        assert gap.load_bearing is True


def test_compiler_invocation_mode_is_authored_input() -> None:
    # forced by the protected A1 parser regardless of gather-vs-facts mode
    model = _compile("hostile")
    assert model.compiler.invocation_mode == "AUTHORED_INPUT"
    assert model.compiler.name


# ---------------------------------------------------------------------------
# Wave -> state mapping (design Section 5)
# ---------------------------------------------------------------------------


def test_hostile_compiles_nine_wave_variables_with_closed_marking_domain() -> None:
    model = _compile("hostile")
    domains = model.domains_dict()
    assert len(domains) == 9  # R0, A1..A8
    for values in domains.values():
        assert set(values) == {"PENDING", "ACTIVE", "DONE", "DROPPED"}
    initial = model.initial_state_dict()
    assert initial["wave_r0"] == "DONE"
    assert initial["wave_a1"] == "DONE"
    assert initial["wave_a2"] == "ACTIVE"  # in_progress
    assert initial["wave_a3"] == "PENDING"  # todo


def test_depends_on_becomes_a_gating_transition_guard() -> None:
    model = _compile("hostile")
    start_a3 = next(t for t in model.transitions if t.transition_id == "start_a3")
    variables_guarded = {g.variable for g in start_a3.guards}
    assert "wave_a3" in variables_guarded
    assert "wave_a2" in variables_guarded
    dep_guard = next(g for g in start_a3.guards if g.variable == "wave_a2")
    assert dep_guard.op == "IN"
    assert set(dep_guard.value) == {"DONE", "DROPPED"}


def test_next_action_becomes_an_obligation_owned_by_the_derived_seat() -> None:
    model = _compile("hostile")
    obligation = next(o for o in model.obligations if o.obligation_id == "next_action_a2")
    assert obligation.state_variable == "wave_a2"
    assert obligation.owner_or_authority == "COO"
    assert "DONE" in obligation.discharged_values
    assert obligation.source_refs


def test_black_hole_wave_has_zero_outgoing_transitions() -> None:
    model = _compile("black_hole")
    # STUCK never appears as an EFFECT (nothing ever writes its variable);
    # it may still appear as a GUARD on a downstream dependent's transition
    # (that dependent's own required transition is exactly the
    # NO_DEAD_REQUIRED_TRANSITION witness this fixture exists to produce).
    stuck_effect_transitions = [t for t in model.transitions if any(e.variable == "wave_stuck" for e in t.effects)]
    assert stuck_effect_transitions == []
    assert "next_action_stuck" not in {o.obligation_id for o in model.obligations}


def test_wait_mapping_produces_a_typed_external_gate() -> None:
    model = _compile("wait_gate")
    assert len(model.external_gates) == 1
    gate = model.external_gates[0]
    assert gate.disposition == "EXTERNAL_GATE"
    assert gate.owner_or_authority == "COO"
    finish = next(t for t in model.transitions if gate.gate_id in t.gate_refs)
    assert finish.required_reachable is False


def test_terminal_outcome_requires_every_wave_resolved() -> None:
    model = _compile("hostile")
    outcome = model.terminal_outcomes[0]
    guarded_vars = {g.variable for g in outcome.guards}
    assert guarded_vars == set(model.domains_dict().keys())


# ---------------------------------------------------------------------------
# source_refs: every compiler-authored element must carry at least one, and
# the full un-abbreviated repo@revision:path#sha256:digest string is
# recorded verbatim somewhere in the model for full-fidelity disclosure
# (design Section 3 "content-bound source receipts"; DEVIATIONS explains why
# the per-element token itself is a compact, schema-legal encoding instead).
# ---------------------------------------------------------------------------


def test_every_compiled_element_carries_nonempty_source_refs() -> None:
    model = _compile("hostile")
    for t in model.transitions:
        assert t.source_refs, t.transition_id
    for o in model.obligations:
        assert o.source_refs, o.obligation_id
    for outcome in model.terminal_outcomes:
        assert outcome.source_refs


def test_full_fidelity_source_string_is_recorded_verbatim_in_notes() -> None:
    # REPAIR B4: notes now read "<alias> = repo@revision:path#sha256:digest"
    # — the alias is the exact token used on every model element's own
    # source_refs, so the mapping is directly correlatable.
    facts = _facts("hostile")
    model = compile_operation_assurance_model(facts)
    ws_fact = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    expected_tail = f"{ws_fact.repo}@{ws_fact.revision}:{ws_fact.path}#sha256:{ws_fact.content_digest}"
    matching = [n for n in model.abstraction_contract.notes if n.endswith(expected_tail)]
    assert len(matching) == 1
    alias = matching[0].split(" = ", 1)[0]
    assert alias.startswith("oasrc_")
    assert any(alias in t.source_refs for t in model.transitions)


# ---------------------------------------------------------------------------
# Determinism (design "byte-identical output across runs and under input
# key permutation")
# ---------------------------------------------------------------------------


def test_compile_is_deterministic_across_repeated_calls() -> None:
    facts = _facts("hostile")
    m1 = compile_operation_assurance_model(facts)
    m2 = compile_operation_assurance_model(facts)
    assert m1.model_hash == m2.model_hash
    assert m1.to_dict() == m2.to_dict()


def test_compile_is_deterministic_under_fact_list_permutation() -> None:
    import dataclasses

    facts = _facts("hostile")
    reversed_facts = dataclasses.replace(facts, facts=tuple(reversed(facts.facts)))
    m1 = compile_operation_assurance_model(facts)
    m2 = compile_operation_assurance_model(reversed_facts)
    assert m1.model_hash == m2.model_hash


# ---------------------------------------------------------------------------
# REPAIR FIX 1 (adversarial review, coordinator REQUEST_REPAIR): a wave whose
# own recorded status is already non-PENDING (in_progress/awaiting_ci) must
# never get a `start_<id>` transition guarded on `var EQ PENDING` — that
# guard is unsatisfiable from the initial state, so a required_reachable
# transition built on it is permanently dead: a FALSE
# NO_DEAD_REQUIRED_TRANSITION witness naming a perfectly healthy record.
# Chosen repair: when initial marking != PENDING, do not emit the start
# transition at all — the record's own status field is authoritative for
# CURRENT position (design Section 5's own compiler-template-grounded-in-
# exact-fields principle), so `depends_on` only gates a genuine PENDING->
# ACTIVE move; an already-ACTIVE wave has, by the record's own assertion,
# already cleared that gate.
# ---------------------------------------------------------------------------


def test_probe_p10_shaped_active_wave_with_deps_yields_zero_fails() -> None:
    from control_plane.operation_assurance_checker import run_checker

    model = _compile("active_with_deps")
    report = run_checker(model, generated_at="2026-09-02T00:00:00Z")
    fails = [r.property_id for r in report.property_results if r.status == "FAIL"]
    assert fails == []


def test_probe_p10_shaped_wave_has_no_start_transition_at_all() -> None:
    model = _compile("active_with_deps")
    transition_ids = {t.transition_id for t in model.transitions}
    assert "start_w2" not in transition_ids
    finish = next(t for t in model.transitions if t.transition_id == "finish_w2")
    assert finish.required_reachable is True
    assert all(g.value != "PENDING" or g.variable != "wave_w2" for g in finish.guards)


def test_corrected_fixture_with_one_lawful_edit_wave_a3_in_progress_yields_zero_fails() -> None:
    """The reviewer's exact repro: flip A3's status todo->in_progress on the
    already-accepted `corrected` fixture (one lawful, in-memory edit to the
    already-parsed payload — no new fixture bytes needed) and recompile."""
    import dataclasses

    from control_plane.operation_assurance_checker import run_checker
    from control_plane.operation_assurance_sources import STATUS_OK

    facts = _facts("corrected")
    new_facts = []
    for fact in facts.facts:
        if fact.status == STATUS_OK and fact.payload and fact.payload.get("key") == "OPERATION-ASSURANCE":
            payload = dict(fact.payload)
            waves = [dict(w) for w in payload["waves"]]
            for wave in waves:
                if wave["id"] == "A3":
                    wave["status"] = "in_progress"
            payload["waves"] = waves
            fact = dataclasses.replace(fact, payload=payload)
        new_facts.append(fact)
    edited = dataclasses.replace(facts, facts=tuple(new_facts))

    model = compile_operation_assurance_model(edited)
    report = run_checker(model, generated_at="2026-09-02T00:00:00Z")
    fails = [r.property_id for r in report.property_results if r.status == "FAIL"]
    assert fails == []


# ---------------------------------------------------------------------------
# REPAIR FIX 2: derive_seat_token must require the RAW match count to be
# exactly one, before any case-insensitive dedup — two identical (or
# same-seat-different-case) tokens are "multiple matches", not "one seat
# mentioned twice", per the protected design's own words: "zero or multiple
# matches make the record an explicit SOURCE_PARTIAL fact."
# ---------------------------------------------------------------------------


def test_two_identical_seat_tokens_is_source_partial_not_a_lawful_single_seat() -> None:
    from control_plane.operation_assurance_sources import derive_seat_token

    assert derive_seat_token("(COO seat) and also (COO seat) again") is None
    assert derive_seat_token("(COO seat) and (coo Seat)") is None


# ---------------------------------------------------------------------------
# REPAIR FIX 4: the wait sub-mapping must validate its OWN closed field set
# {kind, review_after, condition} — an unknown key inside `wait: {...}`
# must refuse the record (SOURCE_PARTIAL), matching the module's own
# closed-field-set claim (probe p12: `wait: {kind: ..., on: ..., evil_field: pwned}`
# was previously accepted).
# ---------------------------------------------------------------------------


def test_wait_mapping_with_unknown_field_is_source_partial() -> None:
    from control_plane.operation_assurance_sources import parse_workstream_frontmatter

    text = """---
schema: agentos.workstream.v1
key: OPERATION-ASSURANCE
title: probe p12
objective: unknown wait field must refuse
status: active
program: p
repos: [mastermind]
owner: Fable (COO seat)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - {id: w1, title: A, status: todo, wait: {kind: EXTERNAL_GATE, on: sol, evil_field: pwned}}
next_action: x
---
body
"""
    from control_plane.operation_assurance_sources import _RecordParseError

    try:
        parse_workstream_frontmatter(text)
    except _RecordParseError:
        return
    raise AssertionError("expected an unknown wait field to be refused")


# ---------------------------------------------------------------------------
# REPAIR FIX 3: a truncated record's digest is a prefix digest (of only the
# bytes actually read), not the digest of the real full record — it must
# never be presentable as an ordinary content_digest that a digest-keyed
# supersession contract could mistake for the whole file's hash.
# ---------------------------------------------------------------------------


def test_truncated_record_digest_is_marked_as_a_prefix_not_a_full_digest() -> None:
    facts = _facts("truncated")
    fact = facts.facts[0]
    assert fact.content_digest.startswith("prefix-sha256:")
    # a truncated target still refuses compilation (behavior unchanged);
    # this only pins the wire-level marking on the fact itself.
    with pytest.raises(CompilerError) as exc:
        compile_operation_assurance_model(facts)
    assert exc.value.reason_code == "SOURCE_TRUNCATED"


def test_truncated_target_digest_prefix_marker_is_pinned_at_the_adapter_level() -> None:
    # a truncated TARGET never reaches source_snapshot at all — see
    # test_truncated_target_refuses_with_source_truncated above, which pins
    # the SOURCE_TRUNCATED refusal; the digest-prefix marker itself is
    # pinned directly against the adapter in
    # tests/test_operation_assurance_a2_sources.py.
    from control_plane.operation_assurance_sources import STATUS_SOURCE_TRUNCATED

    facts = _facts("truncated")
    fact = facts.facts[0]
    assert fact.status == STATUS_SOURCE_TRUNCATED
    assert fact.content_digest.startswith("prefix-sha256:")


def test_non_target_sibling_workstream_fact_is_excluded_from_source_snapshot_and_notes() -> None:
    """REPAIR FIX 7 (coordinator REQUEST_REPAIR, real-gather proof):
    source_snapshot.sources and abstraction_contract.notes carry ONLY
    derivation-relevant sources — the target workstream record plus
    same-key handoffs. An unrelated sibling workstream record (even a
    truncated one) must be scoped OUT of both, never crash compilation, and
    still be reflected (bounded, not per-record) via the family census
    notes."""
    import dataclasses

    from control_plane.operation_assurance_sources import STATUS_SOURCE_TRUNCATED, SourceFact

    facts = _facts("hostile")
    sibling = SourceFact(
        source_owner="AGENT_OS",
        repo=facts.repo,
        revision=facts.revision,
        path="agentos/workstreams/WS-SIBLING.md",
        record_schema="agentos.workstream.v1",
        content_digest="prefix-sha256:" + "ab" * 32,
        observed_at=facts.observed_at,
        status=STATUS_SOURCE_TRUNCATED,
        reason="record exceeds MAX_FILE_BYTES",
        payload=None,
        conflict="NONE",
    )
    with_sibling = dataclasses.replace(facts, facts=facts.facts + (sibling,))
    model = compile_operation_assurance_model(with_sibling)
    assert not any(s.source_identity == sibling.path for s in model.source_snapshot.sources)
    assert not any(sibling.path in note for note in model.abstraction_contract.notes)


# ---------------------------------------------------------------------------
# REPAIR FIX 6: populating Steward source_failures must never crash on the
# QueryStatus.DEGRADED-with-data=None path (executive_steward.get_responsibility
# returns this when there are zero matching facts AND non-empty source
# issues) — it must refuse typed instead.
# ---------------------------------------------------------------------------


def test_sibling_source_missing_fact_does_not_crash_compile_and_is_scoped_out() -> None:
    import dataclasses

    from control_plane.operation_assurance_sources import STATUS_SOURCE_MISSING, SourceFact

    facts = _facts("hostile")
    sibling = SourceFact(
        source_owner="AGENT_OS",
        repo=facts.repo,
        revision=facts.revision,
        path="agentos/workstreams/WS-SIBLING.md",
        record_schema="agentos.workstream.v1",
        content_digest="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        observed_at=facts.observed_at,
        status=STATUS_SOURCE_MISSING,
        reason="synthetic sibling for FIX 6 coverage",
        payload=None,
        conflict="NONE",
    )
    with_sibling = dataclasses.replace(facts, facts=facts.facts + (sibling,))
    model = compile_operation_assurance_model(with_sibling)  # must not crash
    # FIX 7: a non-target sibling (even one registered as a Steward
    # SourceFailure per FIX 6) is scoped OUT of the materialized snapshot —
    # it is not derivation-relevant to the compiled WS:OPERATION-ASSURANCE
    # model.
    assert not any(s.source_identity == sibling.path for s in model.source_snapshot.sources)


# ---------------------------------------------------------------------------
# REPAIR FIX 7: family-wide census moves to bounded per-family counts, never
# one note per record.
# ---------------------------------------------------------------------------


def test_family_census_notes_report_bounded_per_family_counts() -> None:
    model = _compile("hostile")
    census_notes = [n for n in model.abstraction_contract.notes if n.startswith("family census ")]
    assert len(census_notes) == 2  # workstream family + handoff family, never per-record
    ws_note = next(n for n in census_notes if "agentos.workstream.v1" in n)
    ho_note = next(n for n in census_notes if "agentos.handoff.v1" in n)
    assert "attempted=1" in ws_note and "ok=1" in ws_note
    assert "attempted=1" in ho_note and "ok=1" in ho_note


def test_notes_stay_within_the_protected_parser_ceiling_for_a_wide_family() -> None:
    """A synthetic stand-in for the real-tree proof: hundreds of sibling
    workstream/handoff facts (none matching the target) must never expand
    notes past the protected model's per-collection ceiling."""
    import dataclasses

    from control_plane.operation_assurance_sources import STATUS_OK, SourceFact

    facts = _facts("hostile")
    extra = []
    for i in range(500):
        extra.append(
            SourceFact(
                source_owner="AGENT_OS",
                repo=facts.repo,
                revision=facts.revision,
                path=f"agentos/handoffs/OTHER-{i:04d}-2026-01-01.md",
                record_schema="agentos.handoff.v1",
                content_digest="ab" * 32,
                observed_at=facts.observed_at,
                status=STATUS_OK,
                reason=None,
                payload={
                    "schema": "agentos.handoff.v1",
                    "workstream": "WS:SOME-OTHER-KEY",
                    "session": "s",
                    "model": "sonnet",
                    "ended_because": "complete",
                    "mission": "m",
                    "state_before": "b",
                    "changed": [],
                    "verified": [],
                    "unverified": [],
                    "unresolved": [],
                    "next_actions": [],
                    "do_not_redo": [],
                    "danger_areas": [],
                },
                conflict="NONE",
            )
        )
    wide = dataclasses.replace(facts, facts=facts.facts + tuple(extra))
    model = compile_operation_assurance_model(wide)  # must not raise COLLECTION_TOO_LARGE
    assert len(model.abstraction_contract.notes) < 256
    assert len(model.source_snapshot.sources) < 256


def test_target_entirely_missing_refuses_typed_even_with_source_failures_populated() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("missing")
    assert exc.value.reason_code == "SOURCE_MISSING"


# ---------------------------------------------------------------------------
# REPAIR B3 (Sol pre-review): workstream `status` is mechanized against the
# compiled wave markings, not merely a note. Both adversarial disagreement
# shapes must produce a real, checked FAIL through the PROTECTED checker —
# never a silently healthy compile.
# ---------------------------------------------------------------------------


def _all_status_wave_conflict_ids():
    from control_plane.operation_assurance_compiler import (
        STATUS_WAVE_CONFLICT_GAP_ID,
        STATUS_WAVE_CONFLICT_PROPERTY_ID,
    )

    return STATUS_WAVE_CONFLICT_PROPERTY_ID, STATUS_WAVE_CONFLICT_GAP_ID


def test_status_and_wave_markings_agreeing_never_adds_the_conflict_property() -> None:
    # sanity: the real "hostile"/"corrected" fixtures (status=active with a
    # genuinely non-terminal wave) must NEVER trip this — agreement is the
    # normal, silent case.
    property_id, gap_id = _all_status_wave_conflict_ids()
    for name in ("hostile", "corrected", "black_hole"):
        model = _compile(name)
        assert property_id not in {p.property_id for p in model.safety_properties}
        assert gap_id not in {g.gap_id for g in model.known_model_gaps}


def test_b3_false_closure_status_done_but_wave_active_fails_through_the_checker() -> None:
    """Adversarial case 1: status=done while a wave is still active/todo —
    FALSE CLOSURE. Must compile to a declared safety property that FAILs,
    never a silently "complete" model."""
    from control_plane.operation_assurance_checker import run_checker

    property_id, gap_id = _all_status_wave_conflict_ids()

    def mutate(payload: dict) -> None:
        payload["status"] = "done"
        # leave the waves exactly as the corrected fixture declares them —
        # A2/A3 are genuinely non-terminal, so this is a real disagreement.

    facts = _edit_target_payload(_facts("corrected"), mutate)
    model = compile_operation_assurance_model(facts)
    assert property_id in {p.property_id for p in model.safety_properties}
    assert gap_id in {g.gap_id for g in model.known_model_gaps}
    gap = next(g for g in model.known_model_gaps if g.gap_id == gap_id)
    assert gap.load_bearing is True

    report = run_checker(model, generated_at="2026-09-02T00:00:00Z")
    result = next(r for r in report.property_results if r.property_id == property_id)
    assert result.status == "FAIL"
    assert result.source_refs, "the conflict witness must be source-attributed"


def test_b3_false_ongoing_status_active_but_all_waves_done_fails_through_the_checker() -> None:
    """Adversarial case 2: status=active while every wave already carries a
    terminal marking — FALSE ONGOING STATE. Must also compile to a declared
    FAILing safety property, never a silently "still working" model."""
    from control_plane.operation_assurance_checker import run_checker

    property_id, gap_id = _all_status_wave_conflict_ids()

    def mutate(payload: dict) -> None:
        payload["status"] = "active"
        waves = [dict(w) for w in payload["waves"]]
        for wave in waves:
            wave["status"] = "done"
            wave.pop("next_action", None)
            wave.pop("depends_on", None)
        payload["waves"] = waves

    facts = _edit_target_payload(_facts("corrected"), mutate)
    model = compile_operation_assurance_model(facts)
    assert property_id in {p.property_id for p in model.safety_properties}
    assert gap_id in {g.gap_id for g in model.known_model_gaps}

    report = run_checker(model, generated_at="2026-09-02T00:00:00Z")
    result = next(r for r in report.property_results if r.property_id == property_id)
    assert result.status == "FAIL"
    assert result.source_refs


def test_b3_status_killed_groups_with_done_terminal_class() -> None:
    def mutate(payload: dict) -> None:
        payload["status"] = "killed"

    property_id, _ = _all_status_wave_conflict_ids()
    facts = _edit_target_payload(_facts("corrected"), mutate)
    model = compile_operation_assurance_model(facts)
    # corrected fixture has genuinely non-terminal waves -> killed+non-terminal disagrees
    assert property_id in {p.property_id for p in model.safety_properties}


# ---------------------------------------------------------------------------
# REPAIR B4 (Sol pre-review): per-element source refs are a content-addressed
# alias over the FULL (repo, revision, path, digest) tuple — changing ANY
# one dimension changes every affected element's alias.
# ---------------------------------------------------------------------------


def test_b4_alias_changes_when_only_revision_changes() -> None:
    facts_a = _facts("hostile")
    facts_b = _facts("hostile", revision="b" * 40)
    model_a = compile_operation_assurance_model(facts_a)
    model_b = compile_operation_assurance_model(facts_b)
    refs_a = {t.transition_id: t.source_refs for t in model_a.transitions}
    refs_b = {t.transition_id: t.source_refs for t in model_b.transitions}
    assert refs_a.keys() == refs_b.keys()
    for tid in refs_a:
        assert refs_a[tid] != refs_b[tid], f"{tid} alias did not change when only revision changed"


def test_b4_alias_changes_when_only_digest_changes() -> None:
    import dataclasses

    from control_plane.operation_assurance_sources import STATUS_OK

    facts = _facts("hostile")
    mutated_facts = tuple(
        dataclasses.replace(f, content_digest="b" * 64) if f.status == STATUS_OK and f.path.endswith("WS-OPERATION-ASSURANCE.md") else f
        for f in facts.facts
    )
    mutated = dataclasses.replace(facts, facts=mutated_facts)

    model_a = compile_operation_assurance_model(facts)
    model_b = compile_operation_assurance_model(mutated)
    refs_a = {t.transition_id: t.source_refs for t in model_a.transitions}
    refs_b = {t.transition_id: t.source_refs for t in model_b.transitions}
    for tid in refs_a:
        assert refs_a[tid] != refs_b[tid], f"{tid} alias did not change when only the digest changed"


def test_b4_alias_is_schema_legal_and_full_sha256() -> None:
    import re

    model = _compile("hostile")
    ref_re = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:/_@-]{0,127}$")
    for t in model.transitions:
        for ref in t.source_refs:
            assert ref.startswith("oasrc_")
            assert len(ref) == len("oasrc_") + 64  # full sha256 hex, never truncated
            assert ref_re.match(ref)


def test_b4_alias_is_deterministic_and_never_drops_the_revision() -> None:
    # same fixture compiled twice -> identical aliases (determinism); and
    # the full tuple recorded in notes must show a non-abbreviated revision.
    model_a = _compile("hostile")
    model_b = _compile("hostile")
    assert model_a.transitions[0].source_refs == model_b.transitions[0].source_refs
    assert any(REV in note for note in model_a.abstraction_contract.notes)


# ---------------------------------------------------------------------------
# REPAIR R2 (Sol CONTINUE): the compiled model must carry a machine-readable
# LOAD-BEARING SOURCE_ATTESTATION_UNAVAILABLE-class gap through the
# EXISTING known_model_gaps contract whenever the invocation could not
# establish GIT_HEAD_VERIFIED — including when a forged/serialized JSON
# claims it — such that forged JSON can never suppress the gap or mint
# verification.
# ---------------------------------------------------------------------------


def _has_attestation_gap(model) -> bool:
    from control_plane.operation_assurance_compiler import SOURCE_ATTESTATION_UNAVAILABLE_GAP_ID

    return any(g.gap_id == SOURCE_ATTESTATION_UNAVAILABLE_GAP_ID and g.load_bearing for g in model.known_model_gaps)


def test_r2_ordinary_gather_no_git_carries_the_load_bearing_attestation_gap() -> None:
    # every existing fixture gathers from a bare directory (no .git) -> the
    # gap must be present on all of them, always.
    for name in ("hostile", "corrected", "black_hole", "wait_gate"):
        model = _compile(name)
        assert _has_attestation_gap(model), name


def test_r2_forged_from_facts_without_a_root_still_carries_the_gap() -> None:
    import json

    from control_plane.operation_assurance_sources import SourceFacts

    facts = _facts("hostile")
    doc = json.loads(json.dumps(facts.to_dict()))
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"  # forged
    ingested = SourceFacts.from_dict(doc)  # downgraded on ingest (R2 sources-level)
    model = compile_operation_assurance_model(ingested)
    assert _has_attestation_gap(model)


def test_r2_live_matching_root_reestablishment_removes_the_gap(tmp_path) -> None:
    import dataclasses
    import shutil

    from control_plane.operation_assurance_sources import gather_agent_os_source_facts, reestablish_revision_binding

    dest = tmp_path / "checkout"
    shutil.copytree(FIXTURES / "hostile", dest)
    sha = "e6" + "0" * 38
    (dest / ".git").mkdir()
    (dest / ".git" / "HEAD").write_text(sha + "\n", encoding="utf-8")

    facts = gather_agent_os_source_facts(dest, repo="r", revision=sha, observed_at="2026-09-02T00:00:00Z")
    assert facts.revision_binding == "GIT_HEAD_VERIFIED"
    model = compile_operation_assurance_model(facts)
    assert not _has_attestation_gap(model)

    # and the round trip through a forged-then-reestablished document also
    # ends up gap-free, proving reestablishment is the one lawful path back.
    doc = facts.to_dict()
    doc["revision_binding"] = "CALLER_ASSERTED_UNVERIFIED"  # simulate a caller who serialized honestly
    ingested = dataclasses.replace(facts, revision_binding="CALLER_ASSERTED_UNVERIFIED")
    reestablished = reestablish_revision_binding(ingested, dest)
    model2 = compile_operation_assurance_model(reestablished)
    assert not _has_attestation_gap(model2)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc["facts"].sort(key=lambda f: f["path"]),  # reordering facts
        lambda doc: doc["coverage"].reverse(),  # reordering coverage entries
        lambda doc: doc["facts"][0].update({"reason": doc["facts"][0]["reason"]}),  # no-op field touch
    ],
)
def test_r2_gap_survives_arbitrary_serialized_mutation_when_no_root_supplied(mutate) -> None:
    import json

    from control_plane.operation_assurance_sources import SourceFacts

    facts = _facts("hostile")
    doc = json.loads(json.dumps(facts.to_dict()))
    doc["revision_binding"] = "GIT_HEAD_VERIFIED"
    mutate(doc)
    ingested = SourceFacts.from_dict(doc)
    model = compile_operation_assurance_model(ingested)
    assert _has_attestation_gap(model)
