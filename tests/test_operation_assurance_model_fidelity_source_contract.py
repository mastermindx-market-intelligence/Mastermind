from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md"
)


def _text() -> str:
    assert AMENDMENT.is_file()
    return AMENDMENT.read_text(encoding="utf-8")


def test_abstraction_fidelity_is_a_required_truth_axis() -> None:
    text = _text()
    for marker in (
        "DECLARED_EXACT",
        "SOUND_OVERAPPROXIMATION",
        "TRACE_BACKED_UNDERAPPROXIMATION",
        "HEURISTIC_ABSTRACTION",
        "UNKNOWN_FIDELITY",
        "abstraction_contract",
    ):
        assert marker in text

    assert "A finite-model proof remains exactly that" in text
    assert "not automatically a proof" in text


def test_counterexamples_cannot_hide_spuriousness_or_replay_scope() -> None:
    text = _text()
    for marker in (
        "DECLARED_MODEL_ONLY",
        "SOURCE_CONTRACT_VALIDATED",
        "RUNTIME_REPLAY_CONFIRMED",
        "POTENTIALLY_SPURIOUS",
        "INVALIDATED",
        "invalidating_gap_ids",
    ):
        assert marker in text

    assert "Runtime Observability logs, metrics or traces may enrich replay evidence" in text
    assert "cannot alone create\n  `RUNTIME_REPLAY_CONFIRMED`" in text


def test_model_analysis_and_current_source_applicability_remain_separate() -> None:
    text = _text()
    for marker in (
        "model_analysis_verdict",
        "source_applicability",
        "current_projection_verdict",
        "AUTHOR_DECLARED_ONLY",
        "CURRENT_SOURCE_ATTESTED",
        "STALE",
        "CONFLICTED",
        "INCOMPLETE",
    ):
        assert marker in text

    assert "prevents a later correction from erasing what the old model actually showed" in text


def test_gap_relevance_controls_counterexample_certainty() -> None:
    text = _text()
    for marker in (
        "affects_property_ids",
        "affects_transition_ids",
        "affects_variable_ids",
        "trace/property-specific relevance",
        "An unrelated non-load-bearing gap does not hide",
        "A gap that\ncan invalidate the trace or checked property does",
    ):
        assert marker in text


def test_ols_a1_cannot_recommend_operational_proceed() -> None:
    text = _text()
    assert "OLS-A1 never emits REPORT_ONLY_PROCEED" in text
    assert "REPORT_ONLY_NO_RECOMMENDATION" in text
    assert "REPORT_ONLY_PROCEED` is first eligible in OLS-A2/A5" in text
    assert "source_applicability = CURRENT_SOURCE_ATTESTED" in text


def test_liveness_analysis_is_not_limited_to_closed_sccs() -> None:
    text = _text()
    assert "A universal progress violation does not require a closed SCC" in text
    assert "all reachable cyclic SCCs" in text
    assert "no fairness for `finish`" in text
    assert "weak fairness for continuously enabled `finish`" in text
    assert "strong fairness remains outside OLS-A1" in text


def test_descriptive_gate_without_modeled_return_is_not_valid() -> None:
    text = _text()
    assert "A descriptive gate object alone is not a modeled return path" in text
    assert "release_transition_ids" in text
    assert "EXTERNAL_GATE_INCOMPLETE" in text
    assert "Free-form text such as “wait for Chairman” cannot make a dead state valid" in text


def test_exact_corrected_wire_examples_are_present() -> None:
    text = _text()
    for marker in (
        '"kind": "STATE_FORBIDDEN"',
        '"kind": "TRANSITION_FORBIDDEN"',
        '"kind": "WEAK"',
        '"disposition": "EXTERNAL_GATE"',
        '"kind": "TERMINAL_SUCCESS"',
        '"kind": "EXTERNAL_EVENT_MAY_OCCUR"',
    ):
        assert marker in text


def test_fidelity_amendment_is_an_ols_f0_release_blocker() -> None:
    text = _text()
    assert "This amendment is a release blocker for OLS-F0" in text
    assert "OLS-A1 must implement it from its first parser/report\ncommit" in text
