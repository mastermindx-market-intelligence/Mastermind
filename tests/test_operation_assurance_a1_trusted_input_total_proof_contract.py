from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLARIFICATION = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md"
)


def _text() -> str:
    assert CLARIFICATION.is_file(), "missing trusted-input and total-proof clarification"
    return " ".join(CLARIFICATION.read_text(encoding="utf-8").split())


def test_authored_input_cannot_self_attest_trusted_evidence() -> None:
    text = _text()
    assert "A1 invocation authority is fixed to AUTHORED_INPUT" in text
    assert "caller-supplied compiler names, freshness values, validation_kind, validation_refs, or source_refs never grant CURRENT_SOURCE_ATTESTED" in text
    assert "never grant SOURCE_CONTRACT_VALIDATED or RUNTIME_REPLAY_CONFIRMED" in text
    assert "trusted evidence upgrades are outside OLS-A1" in text


def test_terminal_outcomes_are_absorbing_and_unambiguous() -> None:
    text = _text()
    assert "NO_POST_TERMINAL_TRANSITION" in text
    assert "no transition may be enabled from a terminal outcome state" in text
    assert "recurring outcomes are not terminal outcomes" in text


def test_proof_requires_every_analysis_to_complete_without_erasing_definite_witnesses() -> None:
    text = _text()
    assert "a complete reachable graph is necessary but not sufficient for proof" in text
    assert "fairness-product, option-to-complete, proper-completion, dead-transition, safety, and starvation analyses must all be complete" in text
    assert "FAIRNESS_PRODUCT_STATE_LIMIT_REACHED" in text
    assert "without a fully materialized definite witness, analysis exhaustion yields BOUNDED_NO_COUNTEREXAMPLE or INCONCLUSIVE_MODEL_GAP, never proof" in text
    assert "resource-bound exhaustion does not erase a fully materialized definite counterexample" in text
    assert "a checker internal exception never upgrades a result and may require bounded report refusal" in text


def test_terminal_gate_boundary_is_machine_represented() -> None:
    text = _text()
    assert "OLS-A1 does not accept a transitionless terminal-boundary claim" in text
    assert "a terminal assessment is represented by a release_transition_id leading to a named terminal outcome" in text
    assert "escalation_or_close_path must name one of the release_transition_ids" in text
