"""C0 falsifier — B2: the deterministic decision ruler.

No decision may be reached by anything except this law. The tests below are the
falsifiers for it: a candidate that was never really exercised cannot win, a
candidate with a hard failure cannot win, latency never beats correctness, and a
tie goes to the lower-surface candidate rather than to whoever ran first.
"""

from __future__ import annotations

import pytest

from experiments.code_intelligence.decision import (
    MATERIALITY_BAND,
    REQUIRED_CASES,
    REQUIRED_LANGUAGES,
    REQUIRED_PHASES,
    decide,
    summarize_candidate,
)


def _trials(*, correct: bool = True, synthetic: bool = False, languages=None,
            cases=None, phases=None, latency: int = 10, include_terminal: bool = True):
    languages = languages or REQUIRED_LANGUAGES
    cases = cases or REQUIRED_CASES
    phases = phases or REQUIRED_PHASES
    trials = [
        {
            "case": case, "corpus_id": f"{language}_sample",
            "language": language, "phase": phase,
            "correct": correct, "expected": [], "actual": [],
            "latency_ms": latency, "synthetic": synthetic, "error": None,
        }
        for language in languages
        for case in cases
        for phase in phases
    ]
    if include_terminal and "typescript" in languages:
        trials.extend(
            {
                "case": "terminal_migrate_legacy",
                "corpus_id": "terminal_migrate_legacy",
                "language": "typescript",
                "phase": phase,
                "correct": correct,
                "expected": [],
                "actual": [],
                "latency_ms": latency,
                "synthetic": synthetic,
                "error": None,
            }
            for phase in phases
        )
    return trials


def _candidate(kind, *, trials=None, hard_failures=None, status="EXERCISED"):
    return {
        "kind": kind, "status": status,
        "trials": trials if trials is not None else _trials(),
        "hard_failures": hard_failures or [],
        "identity_complete": True,
        "identity_failures": [],
    }


class TestCoverage:
    def test_full_coverage_is_recognised(self) -> None:
        summary = summarize_candidate(_candidate("direct_lsp"))
        assert summary["complete"] is True
        assert summary["missing"] == []
        assert summary["correctness"] == 1.0

    def test_missing_language_is_incomplete(self) -> None:
        summary = summarize_candidate(
            _candidate("direct_lsp", trials=_trials(languages=("python",)))
        )
        assert summary["complete"] is False
        assert any("typescript" in item for item in summary["missing"])

    def test_missing_phase_is_incomplete(self) -> None:
        summary = summarize_candidate(
            _candidate("direct_lsp", trials=_trials(phases=("cold",)))
        )
        assert summary["complete"] is False

    def test_missing_case_is_incomplete(self) -> None:
        summary = summarize_candidate(
            _candidate("direct_lsp", trials=_trials(cases=REQUIRED_CASES[:2]))
        )
        assert summary["complete"] is False

    def test_synthetic_trials_do_not_count_as_coverage(self) -> None:
        summary = summarize_candidate(
            _candidate("direct_lsp", trials=_trials(synthetic=True))
        )
        assert summary["complete"] is False
        assert summary["non_synthetic_trials"] == 0


class TestNoUnearnedDecision:
    def test_synthetic_only_cannot_decide(self) -> None:
        outcome = decide([
            _candidate("direct_lsp", trials=_trials(synthetic=True)),
            _candidate("serena", trials=_trials(synthetic=True)),
        ])
        assert outcome.state == "NON_DECISION"
        assert outcome.decision is None
        assert outcome.blocking_reason

    def test_one_real_one_synthetic_cannot_decide(self) -> None:
        outcome = decide([
            _candidate("direct_lsp"),
            _candidate("serena", trials=_trials(synthetic=True)),
        ])
        assert outcome.state == "NON_DECISION"
        assert outcome.decision is None

    def test_unexercised_candidate_cannot_decide(self) -> None:
        outcome = decide([
            _candidate("direct_lsp"),
            _candidate("serena", trials=[], status="UNEXERCISED_MISSING_BUNDLE",
                       hard_failures=["SERENA_BUNDLE_UNAVAILABLE"]),
        ])
        assert outcome.state == "NON_DECISION"
        assert outcome.decision is None

    def test_missing_terminal_matrix_is_a_typed_nondecision(self) -> None:
        outcome = decide([
            _candidate("direct_lsp", trials=_trials(include_terminal=False)),
            _candidate("serena", trials=_trials(include_terminal=False)),
        ])
        assert outcome.state == "NON_DECISION"
        assert outcome.decision is None
        assert any("terminal_migrate_legacy" in item for summary in outcome.summaries
                   for item in summary["missing"])

    def test_identity_incomplete_blocks_even_a_complete_semantic_matrix(self) -> None:
        candidates = [
            _candidate("direct_lsp"),
            _candidate("serena"),
        ]
        for candidate in candidates:
            candidate["identity_complete"] = False
            candidate["identity_failures"] = ["PACKAGE_CLOSURE_MISSING"]
        outcome = decide(candidates)
        assert outcome.state == "NON_DECISION"
        assert outcome.decision is None
        assert "identity" in outcome.blocking_reason.lower()


class TestSafetyDominates:
    def test_hard_failure_disqualifies_even_a_perfect_candidate(self) -> None:
        outcome = decide([
            _candidate("direct_lsp", hard_failures=["CANDIDATE_TREE_WRITE_DETECTED"]),
            _candidate("serena"),
        ])
        assert outcome.state == "DECIDED"
        assert outcome.decision == "SERENA"
        assert "hard failure" in outcome.tie_break.lower() or outcome.gates

    def test_both_unsafe_is_no_safe_backend(self) -> None:
        outcome = decide([
            _candidate("direct_lsp", hard_failures=["CANDIDATE_TREE_WRITE_DETECTED"]),
            _candidate("serena", hard_failures=["SERENA_TOOL_SURFACE_WIDENED"]),
        ])
        assert outcome.state == "DECIDED"
        assert outcome.decision == "NO_SAFE_BACKEND"

    def test_an_incorrect_candidate_loses_to_a_correct_one(self) -> None:
        outcome = decide([
            _candidate("direct_lsp", trials=_trials(correct=False)),
            _candidate("serena"),
        ])
        assert outcome.decision == "SERENA"

    def test_both_incorrect_is_no_safe_backend(self) -> None:
        outcome = decide([
            _candidate("direct_lsp", trials=_trials(correct=False)),
            _candidate("serena", trials=_trials(correct=False)),
        ])
        assert outcome.decision == "NO_SAFE_BACKEND"


class TestMaterialityAndTieBreak:
    def test_tie_goes_to_the_lower_surface_candidate(self) -> None:
        outcome = decide([_candidate("direct_lsp"), _candidate("serena")])
        assert outcome.decision == "DIRECT_LSP"
        assert "surface" in outcome.tie_break.lower()

    def test_latency_never_beats_correctness(self) -> None:
        slow_but_right = _candidate("serena", trials=_trials(latency=5000))
        fast_but_wrong = _candidate("direct_lsp", trials=_trials(correct=False, latency=1))
        assert decide([fast_but_wrong, slow_but_right]).decision == "SERENA"

    def test_latency_does_not_break_a_correctness_tie(self) -> None:
        # Both perfect; Serena far faster. The lower-surface rule still wins.
        outcome = decide([
            _candidate("direct_lsp", trials=_trials(latency=9000)),
            _candidate("serena", trials=_trials(latency=1)),
        ])
        assert outcome.decision == "DIRECT_LSP"

    def test_material_advantage_beats_the_surface_preference(self) -> None:
        weak = _trials()
        for row in weak[: int(len(weak) * 0.6)]:
            row["correct"] = False
        outcome = decide([
            _candidate("direct_lsp", trials=weak),
            _candidate("serena"),
        ])
        assert outcome.decision == "SERENA"

    def test_band_is_a_declared_constant(self) -> None:
        assert 0 < MATERIALITY_BAND < 1


class TestDeterminism:
    def test_result_is_independent_of_candidate_order(self) -> None:
        a = _candidate("direct_lsp")
        b = _candidate("serena")
        assert decide([a, b]).decision == decide([b, a]).decision

    def test_duplicate_kinds_are_refused(self) -> None:
        with pytest.raises(ValueError):
            decide([_candidate("serena"), _candidate("serena")])

    def test_missing_kind_is_refused(self) -> None:
        with pytest.raises(ValueError):
            decide([_candidate("serena")])


class TestMaterialityBandIsReachable:
    """The band must actually be exercisable, or its rule is dead code."""

    def _mixed(self, kind: str, *, secondary_correct: bool):
        trials = _trials()
        for row in trials:
            if row["case"] not in (
                "O1_definition_live_implementation",
                "W1_references_across_files",
                "A3_implementations_of_protocol",
            ):
                row["correct"] = secondary_correct
        return _candidate(kind, trials=trials)

    def test_material_secondary_advantage_beats_the_surface_preference(self) -> None:
        # Both useful on primary cases; serena materially better on secondary.
        outcome = decide([
            self._mixed("direct_lsp", secondary_correct=False),
            self._mixed("serena", secondary_correct=True),
        ])
        assert outcome.state == "DECIDED"
        assert outcome.decision == "SERENA"
        assert "materiality band" in outcome.tie_break.lower()

    def test_latency_cannot_substitute_for_that_advantage(self) -> None:
        slow_better = self._mixed("serena", secondary_correct=True)
        for row in slow_better["trials"]:
            row["latency_ms"] = 9999
        fast_worse = self._mixed("direct_lsp", secondary_correct=False)
        for row in fast_worse["trials"]:
            row["latency_ms"] = 1
        assert decide([fast_worse, slow_better]).decision == "SERENA"

    def test_failing_a_primary_case_fails_the_usefulness_floor(self) -> None:
        trials = _trials()
        for row in trials:
            if row["case"] == "O1_definition_live_implementation":
                row["correct"] = False
        outcome = decide([_candidate("direct_lsp", trials=trials), _candidate("serena")])
        assert outcome.decision == "SERENA"
        assert any("usefulness floor" in gate for gate in outcome.gates)
