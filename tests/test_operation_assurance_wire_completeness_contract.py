from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-30-operation-assurance-core.md"
)
REPORT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-assurance-immutable-report-projection-clarification.md"
)
LAW = ROOT / "docs" / "OPERATION_LIVENESS_SOUNDNESS_LAW.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing OLS source artifact: {path.relative_to(ROOT)}"
    return " ".join(path.read_text(encoding="utf-8").split())


def test_a1_freezes_bounded_open_tokens_and_closed_semantic_enums() -> None:
    text = _read(PLAN)
    assert "Bounded canonical-token fields" in text
    for token_field in (
        "transition.kind",
        "transition.actor_class",
        "transition.authority_requirement",
        "transition.progress_tags",
        "obligation.kind",
        "owner_or_authority",
        "source.owner",
        "source.source_kind",
    ):
        assert token_field in text
    for enum_block in (
        "FRESH | STALE | UNKNOWN",
        "NONE | CONFLICT | UNKNOWN",
        "COMPLETE | PARTIAL | UNKNOWN",
        "EXTERNAL_GATE | INTENTIONAL_WAIT",
        "PASS | FAIL | UNKNOWN | NOT_APPLICABLE",
    ):
        assert enum_block in text
    assert "Open tokens carry no checker privilege by their spelling" in text


def test_generic_checker_does_not_duplicate_mastermind_policy() -> None:
    text = _read(PLAN) + " " + _read(LAW)
    assert "Generic mandatory property IDs" in text
    for property_id in (
        "OPTION_TO_COMPLETE",
        "PROPER_COMPLETION",
        "NO_DEAD_REQUIRED_TRANSITION",
        "NO_POST_TERMINAL_TRANSITION",
        "UNIVERSAL_PROGRESS",
        "RECURRING_PROGRESS_VALID",
        "NO_STARVATION_UNDER_DECLARED_FAIRNESS",
        "FAIRNESS_REALIZABLE",
    ):
        assert property_id in text
    assert "NO_EFFECT_UNKNOWN_ESCAPE and ONE_ACTION_AUTHORITY are explicit authored safety property IDs" in text
    assert "The A2 source compiler, not the generic A1 checker, decides which Mastermind policy properties a real operation must contain" in text


def test_exact_nested_report_wire_is_defined() -> None:
    text = _read(REPORT)
    for heading in (
        "### 1.1 Property result",
        "### 1.2 Counterexample",
        "### 1.3 State delta step",
        "### 1.4 Transition-reason snapshot",
        "### 1.5 Repair candidate",
        "### 1.6 Coverage",
        "### 1.7 Assumptions",
        "### 1.8 Exploration receipt and analysis product",
    ):
        assert heading in text
    for field in (
        "analysis_complete",
        "counterexample_id|null",
        "initial_state",
        "shortest_prefix",
        "cycle",
        "state_delta_per_step",
        "enabled_and_disabled_transition_reasons",
        "mandatory_property_ids",
        "authored_property_ids",
        "analysis_products",
        "checker_terminated_normally",
    ):
        assert field in text
    assert "counterexample_id = \"ocx_\" + counterexample_hash[:24]" in text


def test_parser_resource_ceiling_and_json_boundary_are_exact() -> None:
    text = _read(PLAN)
    for marker in (
        "MAX_INPUT_BYTES = 4194304",
        "MAX_JSON_DEPTH = 64",
        "MAX_TEXT_CHARS = 4096",
        "MAX_STATE_VARIABLES = 128",
        "MAX_DOMAIN_VALUES_PER_VARIABLE = 128",
        "MAX_TOP_LEVEL_COLLECTION_ITEMS = 2048",
        "MAX_NESTED_COLLECTION_ITEMS = 256",
        "MAX_GUARDS_PER_OBJECT = 128",
        "MAX_EFFECTS_PER_TRANSITION = 128",
        "MAX_EXPLORATION_STATES = 1000000",
        "MAX_EXPLORATION_DEPTH = 100000",
        "object_pairs_hook",
        "parse_constant",
        "UTF-8 decoding is strict",
    ):
        assert marker in text


def test_normalization_and_bound_semantics_are_deterministic() -> None:
    text = _read(PLAN)
    assert "Semantically unordered collections are normalized" in text
    for marker in (
        "sources by source_identity",
        "transitions by transition_id",
        "outcomes by outcome_id",
        "guards by canonical bytes",
        "effects by variable",
        "property_results by property_id",
        "counterexamples by property_id then counterexample_id",
        "Trace order is never sorted",
        "the initial state is depth 0",
        "a state at max_depth is retained but not expanded",
        "the initial state counts toward max_states",
        "a successor that would exceed max_states is not inserted",
    ):
        assert marker in text


def test_not_applicable_is_narrow_and_cannot_manufacture_proof() -> None:
    text = _read(REPORT)
    assert "NOT_APPLICABLE is legal only" in text
    assert "RECURRING_PROGRESS_VALID when the model declares no recurring outcome" in text
    assert "NO_STARVATION_UNDER_DECLARED_FAIRNESS when the model declares no persistent obligation" in text
    assert "FAIRNESS_REALIZABLE when the model declares no fairness assumption" in text
    assert "Every other mandatory property and every authored safety property must be PASS, FAIL, or UNKNOWN" in text
