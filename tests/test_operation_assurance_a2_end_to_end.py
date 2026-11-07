"""tests.test_operation_assurance_a2_end_to_end — OLS-A2 through the
PROTECTED, UNCHANGED OLS-A1 engine.

Proves the three end-to-end behaviors the OLS-A2 packet commissions (design
Section 6 + implementation-wave FROZEN SPEC end-to-end item):
    1. hostile fixture (real byte-exact capture at Agent OS revision
       a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4) -> compiled model parses
       under the protected A1 parser -> checker runs -> report shows
       non-current applicability, SOUND_OVERAPPROXIMATION, and never PROVEN.
    2. black-hole fixture -> the compiled model detects a real,
       source-attributed no-progress witness. See DEVIATIONS in the return
       packet for why the top-level verdict is INCONCLUSIVE_MODEL_GAP, not
       UNSAFE_COUNTEREXAMPLE — that value is MECHANICALLY unreachable once
       abstraction_contract.kind is SOUND_OVERAPPROXIMATION
       (control_plane.operation_assurance_checker._fidelity_proof_eligible),
       which this vertical is required to always emit and never override.
    3. corrected fixture -> a valid, degraded-but-coherent compilation with
       zero FAIL property results.

This module NEVER imports operation_assurance_sources/compiler production
internals to fake a result — every model here is produced by the real
gather -> Steward -> compile pipeline and then handed unmodified to the
PROTECTED control_plane.operation_assurance_checker/model/report modules.
"""
from __future__ import annotations

from pathlib import Path

from control_plane.operation_assurance_checker import run_checker
from control_plane.operation_assurance_compiler import compile_operation_assurance_model
from control_plane.operation_assurance_model import parse_model_bytes
from control_plane.operation_assurance_sources import gather_agent_os_source_facts

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "operation_assurance_a2"
REV = "a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4"
OBSERVED_AT = "2026-09-02T00:00:00Z"
REPO = "mastermindx-market-intelligence/macro"


HOSTILE_WORKSTREAM_SHA256 = "6562c148d9248970ef95917896421c19013b97990a8acf2795435736f7e13ed4"


def test_hostile_fixture_is_the_exact_pinned_revision() -> None:
    facts = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    ws = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    assert ws.revision == REV
    # pinned true digest of the byte-exact captured record (not a
    # passthrough-of-the-caller's-assertion check): if this fixture file's
    # bytes ever drift, this must fail even though `revision` still matches.
    assert ws.content_digest == HOSTILE_WORKSTREAM_SHA256


def test_1_hostile_end_to_end_through_the_protected_a1_engine() -> None:
    import json

    facts = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model = compile_operation_assurance_model(facts)

    # the model really does round-trip through the protected parser's own
    # bytes-in entry point (not just constructed and trusted in-process).
    raw = json.dumps(model.to_dict()).encode("utf-8")
    reparsed = parse_model_bytes(raw)
    assert reparsed.model_hash == model.model_hash

    report = run_checker(reparsed, generated_at=OBSERVED_AT)

    assert report.abstraction_contract.kind == "SOUND_OVERAPPROXIMATION"
    assert report.model_analysis_verdict != "PROVEN_WITHIN_FINITE_MODEL"
    assert report.source_applicability_at_generation != "AUTHOR_DECLARED_ONLY"  # non-current, never "healthy"
    assert report.source_applicability_at_generation == "UNKNOWN"


def test_2_black_hole_fixture_yields_a_real_source_attributed_witness() -> None:
    import json

    facts = gather_agent_os_source_facts(FIXTURES / "black_hole", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model = compile_operation_assurance_model(facts)
    raw = json.dumps(model.to_dict()).encode("utf-8")
    reparsed = parse_model_bytes(raw)
    report = run_checker(reparsed, generated_at=OBSERVED_AT)

    assert report.progress_disposition == "NO_PROGRESS"
    dead_transition = next(r for r in report.property_results if r.property_id == "NO_DEAD_REQUIRED_TRANSITION")
    assert dead_transition.status == "FAIL"
    cx = next(c for c in report.counterexamples if c.counterexample_id == dead_transition.counterexample_id)
    assert cx.source_refs, "the witness must name the offending wave's record"
    ws_fact = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    # REPAIR B4: source_refs are now opaque content-addressed aliases (never
    # a raw path substring) — resolve the alias back to the record it names
    # via the model's own notes, where the full repo/revision/path/digest
    # tuple is recorded verbatim.
    notes_by_alias = {n.split(" = ", 1)[0]: n for n in model.abstraction_contract.notes if " = " in n}
    resolved = [notes_by_alias.get(ref, "") for ref in cx.source_refs]
    assert any(ws_fact.path in note for note in resolved)

    # MECHANIZED, not a design-doc opinion: UNSAFE_COUNTEREXAMPLE is
    # unreachable whenever abstraction_contract.kind != DECLARED_EXACT (see
    # control_plane.operation_assurance_checker._fidelity_proof_eligible and
    # _run_checker_inner's "elif any_fail and not fidelity_ok:" branch,
    # which unconditionally routes to INCONCLUSIVE_MODEL_GAP and downgrades
    # every counterexample's realizability to POTENTIALLY_SPURIOUS). Since
    # this vertical's abstraction_contract.kind is ALWAYS
    # SOUND_OVERAPPROXIMATION by mandate, UNSAFE_COUNTEREXAMPLE can never be
    # this vertical's verdict for ANY fixture — pinned here so a future
    # change to either module is caught rather than silently drifting.
    assert report.model_analysis_verdict == "INCONCLUSIVE_MODEL_GAP"
    assert cx.realizability == "POTENTIALLY_SPURIOUS"


def test_3_corrected_fixture_is_a_valid_degraded_but_coherent_compilation() -> None:
    import json

    facts = gather_agent_os_source_facts(FIXTURES / "corrected", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model = compile_operation_assurance_model(facts)
    raw = json.dumps(model.to_dict()).encode("utf-8")
    reparsed = parse_model_bytes(raw)
    report = run_checker(reparsed, generated_at=OBSERVED_AT)

    fails = [r for r in report.property_results if r.status == "FAIL"]
    assert fails == []
    assert report.model_analysis_verdict == "INCONCLUSIVE_MODEL_GAP"  # capped: load-bearing gaps + SOUND_OVERAPPROXIMATION
    assert report.model_analysis_verdict != "PROVEN_WITHIN_FINITE_MODEL"
    assert report.progress_disposition in ("AUTONOMOUSLY_LIVE", "EXTERNALLY_GATED", "INTENTIONAL_WAIT", "RECURRING_SERVICE")


def test_determinism_byte_identical_output_across_runs() -> None:
    facts_a = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    facts_b = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model_a = compile_operation_assurance_model(facts_a)
    model_b = compile_operation_assurance_model(facts_b)
    assert model_a.to_dict() == model_b.to_dict()
    assert model_a.model_hash == model_b.model_hash

    report_a = run_checker(model_a, generated_at=OBSERVED_AT)
    report_b = run_checker(model_b, generated_at=OBSERVED_AT)
    assert report_a.to_dict() == report_b.to_dict()


# ---------------------------------------------------------------------------
# REPAIR FIX 7 (coordinator REQUEST_REPAIR, real-gather proof): compiling
# against the real macro agentos tree (57+ workstreams, ~398 handoffs)
# refused with COLLECTION_TOO_LARGE on abstraction_contract.notes, because
# the compiler used to materialize one note (and one source_snapshot entry)
# per GATHERED fact — the whole family census — instead of scoping to what
# the model actually derives from. This generates a REAL-TREE-SHAPED fixture
# (>=60 workstream + >=300 handoff records spread across many DIFFERENT
# keys, one of them the target) on disk and proves the full
# gather -> compile -> protected-parse -> check pipeline succeeds within
# every A1 ceiling.
# ---------------------------------------------------------------------------

_WAVE_STATUS_CYCLE = ("done", "todo", "in_progress", "done", "todo")


def _write_workstream(root: Path, key: str, *, target: bool) -> None:
    if target:
        waves = (
            "  - {id: R0, title: \"Recover canonical truth\", status: done, pr: 279}\n"
            "  - {id: A1, title: \"Deterministic engine\", status: done, pr: 324}\n"
            "  - {id: A2, title: \"Source compiler seam\", status: in_progress, "
            "next_action: \"land the A2 implementation\"}\n"
            "  - {id: A3, title: \"Applicability\", status: todo, depends_on: [A2]}\n"
        )
    else:
        status = _WAVE_STATUS_CYCLE[hash(key) % len(_WAVE_STATUS_CYCLE)]
        na = "" if status == "done" else ", next_action: \"keep going\""
        waves = f'  - {{id: w1, title: "wave one", status: {status}{na}}}\n'
    text = f"""---
schema: agentos.workstream.v1
key: {key}
title: Synthetic real-tree-shaped workstream {key}
objective: >
  A synthetic record shaped like a real agentos workstream, for the OLS-A2
  real-tree-scale proof (REPAIR FIX 7).
status: active
program: cross-repo-contract-governance
repos: [mastermind]
owner: Fable principal (COO seat)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
{waves}next_action: >
  synthetic next action for {key}.
do_not_redo:
  - "nothing yet"
landmines:
  - "none"
---

# {key}
"""
    path = root / "agentos" / "workstreams" / f"WS-{key}.md"
    path.write_text(text, encoding="utf-8")


def _write_handoff(root: Path, key: str, index: int) -> None:
    text = f"""---
schema: agentos.handoff.v1
workstream: "WS:{key}"
session: synthetic-session-{index:04d}
model: sonnet
ended_because: complete
mission: >
  synthetic mission {index}.
state_before: >
  synthetic state before {index}.
changed:
  - {{path: "some/path-{index}.py", what: "synthetic change {index}"}}
verified:
  - {{claim: "it works", command: "pytest", result: "passed"}}
unverified: []
unresolved: []
next_actions:
  - "keep going"
do_not_redo:
  - "nothing yet"
danger_areas:
  - "none"
---

# handoff {index} for {key}
"""
    path = root / "agentos" / "handoffs" / f"{key}-2026-01-{(index % 28) + 1:02d}-{index:04d}.md"
    path.write_text(text, encoding="utf-8")


def _generate_real_tree_shaped_fixture(root: Path, *, workstream_count: int, handoff_count: int, target_key: str) -> None:
    (root / "agentos" / "workstreams").mkdir(parents=True, exist_ok=True)
    (root / "agentos" / "handoffs").mkdir(parents=True, exist_ok=True)
    keys = [f"SYN-{i:03d}" for i in range(workstream_count - 1)] + [target_key]
    for key in keys:
        _write_workstream(root, key, target=(key == target_key))
    for i in range(handoff_count):
        _write_handoff(root, keys[i % len(keys)], i)


def test_repair_fix7_real_tree_shaped_gather_compile_check_succeeds_within_a1_ceilings(tmp_path: Path) -> None:
    workstream_count = 62
    handoff_count = 320
    target_key = "OPERATION-ASSURANCE"
    _generate_real_tree_shaped_fixture(
        tmp_path, workstream_count=workstream_count, handoff_count=handoff_count, target_key=target_key
    )

    facts = gather_agent_os_source_facts(
        tmp_path, repo=REPO, revision=REV, observed_at=OBSERVED_AT, target_workstream_key=target_key
    )
    ws_coverage = next(c for c in facts.coverage if c.record_schema == "agentos.workstream.v1")
    ho_coverage = next(c for c in facts.coverage if c.record_schema == "agentos.handoff.v1")
    assert ws_coverage.attempted == workstream_count
    assert ho_coverage.attempted == handoff_count

    model = compile_operation_assurance_model(facts, target_workstream_key=target_key)

    # only the target workstream + its own same-key handoffs materialize —
    # never the whole (workstream_count + handoff_count)-record family.
    assert len(model.source_snapshot.sources) < 20
    assert len(model.abstraction_contract.notes) < 20

    # round-trips through the PROTECTED parser (this is where the real probe
    # refused with COLLECTION_TOO_LARGE before the repair).
    import json

    raw = json.dumps(model.to_dict()).encode("utf-8")
    reparsed = parse_model_bytes(raw)
    assert reparsed.model_hash == model.model_hash

    report = run_checker(reparsed, generated_at=OBSERVED_AT)
    assert report.model_analysis_verdict in (
        "UNSAFE_COUNTEREXAMPLE",
        "BOUNDED_NO_COUNTEREXAMPLE",
        "INCONCLUSIVE_MODEL_GAP",
    )

    # the family-wide census is still visible, as BOUNDED per-family counts.
    census_notes = [n for n in model.abstraction_contract.notes if n.startswith("family census ")]
    assert len(census_notes) == 2
    ws_note = next(n for n in census_notes if "agentos.workstream.v1" in n)
    ho_note = next(n for n in census_notes if "agentos.handoff.v1" in n)
    assert f"attempted={workstream_count}" in ws_note
    assert f"attempted={handoff_count}" in ho_note
    assert f"ok={handoff_count}" in ho_note  # every generated handoff parses OK, none refused

    # at least one same-key handoff really did materialize (not just the
    # target workstream record alone) — proves point (1) positively, not
    # merely "stayed under budget".
    handoff_sources = [s for s in model.source_snapshot.sources if "/handoffs/" in s.source_identity]
    assert handoff_sources
    assert all(target_key in s.source_identity for s in handoff_sources)


def test_repair_fix7_real_tree_shaped_conflict_detection_still_survives(tmp_path: Path) -> None:
    """Point (3): the family-wide scan for conflict detection must be
    UNCHANGED — only the materialized snapshot/notes are scoped. A second
    workstream file declaring the same target key, buried among 60+ other
    unrelated records, must still refuse SOURCE_CONFLICTED."""
    workstream_count = 61
    target_key = "OPERATION-ASSURANCE"
    _generate_real_tree_shaped_fixture(tmp_path, workstream_count=workstream_count, handoff_count=50, target_key=target_key)
    # a SECOND file, buried among 60+ unrelated records, declaring the same
    # target key with disagreeing content — a genuine source-layer conflict.
    duplicate_path = tmp_path / "agentos" / "workstreams" / f"WS-{target_key}-DUPLICATE.md"
    original = (tmp_path / "agentos" / "workstreams" / f"WS-{target_key}.md").read_text(encoding="utf-8")
    duplicate_path.write_text(original.replace("status: in_progress", "status: todo", 1), encoding="utf-8")

    facts = gather_agent_os_source_facts(
        tmp_path, repo=REPO, revision=REV, observed_at=OBSERVED_AT, target_workstream_key=target_key
    )
    from control_plane.operation_assurance_compiler import CompilerError

    try:
        compile_operation_assurance_model(facts, target_workstream_key=target_key)
        raise AssertionError("expected SOURCE_CONFLICTED to be refused")
    except CompilerError as exc:
        assert exc.reason_code == "SOURCE_CONFLICTED"
