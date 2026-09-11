"""The deterministic C0 decision ruler.

The protected law, in order:

1. **Real evidence first.** A candidate that was not genuinely exercised over the
   complete required matrix cannot participate. If any candidate is missing real
   coverage, no decision is reachable — the outcome is a typed blocked state, not
   a winner and not an unearned ``NO_SAFE_BACKEND``.
2. **Constitutional and security hard failures dominate.** A candidate with a
   hard failure is disqualified regardless of speed or feature count.
3. **Correctness dominates latency.** Latency never selects a winner and never
   breaks a tie.
4. **Materiality band.** Inside the band the candidates are treated as
   equivalent, and the lower authority/supply-chain/runtime/state/operational
   surface wins — which favours direct LSP unless Serena proves a material
   advantage.
5. There is no dual-primary backend and no automatic fallback.

``NO_SAFE_BACKEND`` is a real, successful result — but only when both candidates
were genuinely exercised and neither qualified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "MATERIALITY_BAND",
    "PRIMARY_CASES",
    "REQUIRED_CASES",
    "REQUIRED_LANGUAGES",
    "REQUIRED_PHASES",
    "REQUIRED_TRIAL_KEYS",
    "DecisionOutcome",
    "decide",
    "summarize_candidate",
]

REQUIRED_LANGUAGES = ("python", "typescript")
REQUIRED_CASES = (
    "O1_definition_live_implementation",
    "W1_references_across_files",
    "A3_implementations_of_protocol",
    "overview_single_file",
    "diagnostics_planted_undefined_name",
)
REQUIRED_PHASES = ("cold", "warm")

TERMINAL_CORPUS_ID = "terminal_migrate_legacy"
TERMINAL_CASE = "terminal_migrate_legacy"
REQUIRED_TRIAL_KEYS = tuple(
    (f"{language}_sample", language, case, phase)
    for language in REQUIRED_LANGUAGES
    for case in REQUIRED_CASES
    for phase in REQUIRED_PHASES
) + tuple(
    (TERMINAL_CORPUS_ID, "typescript", TERMINAL_CASE, phase)
    for phase in REQUIRED_PHASES
)

#: The protected acceptance ruler: a backend is "useful" only when it is correct
#: on the primary journeys. Secondary cases contribute to materiality, not to the
#: usefulness floor.
PRIMARY_CASES = (
    "O1_definition_live_implementation",
    "W1_references_across_files",
    "A3_implementations_of_protocol",
)

#: Correctness difference below which the candidates are treated as equivalent.
MATERIALITY_BAND = 0.10

#: Lower number = lower authority/supply-chain/runtime/state/operational surface.
_SURFACE_RANK = {"direct_lsp": 0, "serena": 1}

_REQUIRED_KINDS = ("direct_lsp", "serena")

_DECISION_BY_KIND = {"direct_lsp": "DIRECT_LSP", "serena": "SERENA"}


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    state: str
    decision: str | None
    gates: tuple[str, ...]
    tie_break: str
    blocking_reason: str
    summaries: tuple[Mapping[str, Any], ...]


def summarize_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic per-candidate summary over the required matrix."""
    trials = [t for t in candidate.get("trials", []) if not t.get("synthetic", True)]
    covered = {
        (t.get("corpus_id"), t.get("language"), t.get("case"), t.get("phase"))
        for t in trials
    }
    missing = [
        f"{corpus_id}/{language}/{case}/{phase}"
        for corpus_id, language, case, phase in REQUIRED_TRIAL_KEYS
        if (corpus_id, language, case, phase) not in covered
    ]
    correct = sum(1 for t in trials if t.get("correct"))
    total = len(trials)
    primary = [t for t in trials if t.get("case") in PRIMARY_CASES]
    primary_correct = sum(1 for t in primary if t.get("correct"))
    return {
        "primary_trials": len(primary),
        "primary_correct": primary_correct,
        "useful": bool(primary) and primary_correct == len(primary),
        "kind": candidate["kind"],
        "status": candidate.get("status"),
        "non_synthetic_trials": total,
        "correct": correct,
        "correctness": (correct / total) if total else 0.0,
        "hard_failures": tuple(candidate.get("hard_failures", ())),
        "identity_complete": bool(candidate.get("identity_complete", True)),
        "identity_failures": tuple(candidate.get("identity_failures", ())),
        "complete": not missing and bool(candidate.get("identity_complete", True)),
        "missing": missing,
        "median_latency_ms": (
            sorted(t.get("latency_ms", 0) for t in trials)[total // 2] if total else None
        ),
    }


def decide(candidates: Sequence[Mapping[str, Any]]) -> DecisionOutcome:
    """Apply the frozen law. Never guesses, never prefers by order or speed."""
    kinds = [c["kind"] for c in candidates]
    if sorted(kinds) != sorted(_REQUIRED_KINDS):
        raise ValueError(
            f"exactly one of each of {_REQUIRED_KINDS} is required, got {kinds}"
        )

    summaries = tuple(
        sorted((summarize_candidate(c) for c in candidates), key=lambda s: s["kind"])
    )

    incomplete = [s for s in summaries if not s["complete"]]
    if incomplete:
        detail = "; ".join(
            f"{s['kind']} missing {len(s['missing'])} required trial(s)"
            + (
                f" and incomplete identity {list(s['identity_failures'])}"
                if not s["identity_complete"] else ""
            )
            for s in incomplete
        )
        return DecisionOutcome(
            state="NON_DECISION",
            decision=None,
            gates=("real_evidence_required", "identity_closure_required"),
            tie_break="",
            blocking_reason=(
                "No decision may be published: the required candidate x language x "
                f"corpus x case x phase matrix and executable identity closure were "
                f"not both proven. {detail}. The protected Terminal migrateLegacy "
                "cold+warm case and complete launcher/target/package manifests are "
                "mandatory. "
                "Synthetic stand-in trials prove adapter behaviour and are "
                "categorically ineligible as empirical evidence."
            ),
            summaries=summaries,
        )

    gates: list[str] = []
    eligible = []
    for summary in summaries:
        if summary["hard_failures"]:
            gates.append(
                f"{summary['kind']} disqualified by hard failure(s): "
                f"{list(summary['hard_failures'])}"
            )
            continue
        if not summary["useful"]:
            gates.append(
                f"{summary['kind']} failed the usefulness floor on primary cases "
                f"({summary['primary_correct']}/{summary['primary_trials']})"
            )
            continue
        eligible.append(summary)

    perfect = eligible
    if not perfect:
        return DecisionOutcome(
            state="DECIDED",
            decision="NO_SAFE_BACKEND",
            gates=tuple(gates),
            tie_break=(
                "Both candidates were genuinely exercised and neither cleared the "
                "safety and correctness floor."
            ),
            blocking_reason="",
            summaries=summaries,
        )

    if len(perfect) == 1:
        winner = perfect[0]
        return DecisionOutcome(
            state="DECIDED",
            decision=_DECISION_BY_KIND[winner["kind"]],
            gates=tuple(gates),
            tie_break=(
                f"{winner['kind']} was the only candidate clearing the safety and "
                "correctness floor; the other was excluded by a hard failure or by "
                "primary-task correctness, which dominate latency."
            ),
            blocking_reason="",
            summaries=summaries,
        )

    # Correctness — never latency — is what can beat the surface preference.
    best = max(perfect, key=lambda s: s["correctness"])
    worst = min(perfect, key=lambda s: s["correctness"])
    if best["correctness"] - worst["correctness"] > MATERIALITY_BAND:
        return DecisionOutcome(
            state="DECIDED",
            decision=_DECISION_BY_KIND[best["kind"]],
            gates=tuple(gates),
            tie_break=(
                f"{best['kind']} exceeded {worst['kind']} by more than the "
                f"materiality band ({MATERIALITY_BAND:.0%}) on primary-task correctness."
            ),
            blocking_reason="",
            summaries=summaries,
        )

    winner = min(perfect, key=lambda s: _SURFACE_RANK[s["kind"]])
    return DecisionOutcome(
        state="DECIDED",
        decision=_DECISION_BY_KIND[winner["kind"]],
        gates=tuple(gates),
        tie_break=(
            "Correctness difference is inside the materiality band, so the lower "
            "authority/supply-chain/runtime/state/operational surface wins. Latency "
            f"does not break this tie. Winner: {winner['kind']}."
        ),
        blocking_reason="",
        summaries=summaries,
    )
