"""Static regression contract for execution-first Extra High sessions.

These tests validate source policy and adversarial scenario coverage. They do
not prove that a served model loaded the policy or performed live actions.

The original #1342 candidate asserted on two prose blocks this repository no
longer restores: the ``ACTIVE_EXECUTION.md`` and ``SESSION_RELIABILITY.md``
additions that re-declared generic delivery obligations. Those obligations are
already carried by the current canonical owners, so this contract asserts the
*current* sections that own them instead of the superseded wording, and keeps
the PR's unique Paper cleanup guidance as a source contract of its own.

Every family below names the canonical owner of an obligation and the clauses
that together establish it, so dropping one condition is detected instead of
silently narrowing the obligation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "docs" / "sol_skills"
ACTIVE = SKILLS / "ACTIVE_EXECUTION.md"
RELIABILITY = SKILLS / "SESSION_RELIABILITY.md"
PAPER = ROOT / "skills" / "paper-design-workflow" / "SKILL.md"
CORPUS = ROOT / "research" / "fixtures" / "extra_high_execution_first_2026-10-11.json"

CLEANUP_HEADING = "## Non-destructive cross-file cleanup"
SCOPE_ANCHOR = "## Scope the design"

EXPECTED_SCENARIOS = ["EHX01", "EHX02", "EHX03", "EHX04", "EHX05", "EHX06", "EHX07", "EHX08"]


def _raw(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _words(path: Path) -> str:
    return " ".join(_raw(path).split())


def _section_body_from_text(text: str, heading: str) -> str:
    """Normalized body of one unique markdown section, excluding its heading."""
    assert text.count(heading) == 1, f"heading is not unique: {heading!r}"
    start = text.index(heading) + len(heading)
    following = re.search(r"^#{1,6} ", text[start:], re.M)
    end = start + (following.start() if following else len(text) - start)
    return " ".join(text[start:end].split())


def _section_body(path: Path, heading: str) -> str:
    """Normalized body of one unique markdown section, excluding its heading."""
    return _section_body_from_text(_raw(path), heading)


# (family, owner file, canonical section heading or None for whole file, clauses)
FAMILIES: tuple[tuple[str, Path, str | None, tuple[str, ...]], ...] = (
    (
        "execution-before-exit",
        ACTIVE,
        None,
        (
            "Never narrow end-to-end delivery to design after writing a plan.",
            "Execute the next material action in the phase, however many necessary tool operations it takes.",
            "Do not fragment useful depth merely to shorten a turn.",
            "Use its canonical tool/owner and preserve INDEX admission, source custody and one-carrier reconciliation.",
            "Never perform a dummy mutation solely to prove capability",
            "If the truthful classification is `MORE_WORK_EXISTS`, **do not finalize**",
            "advance the highest-value unblocked dependency while healthy",
        ),
    ),
    (
        "accepted-research-only-completion",
        ACTIVE,
        "## Step 1A — Select principal duty without inventing authority",
        (
            "A bounded design commission ends only at its stated acceptance and consumed handoff",
            "Acceptance belongs to the decision owner named by the assignment or current source law.",
            "intended recipient or pickup alone is neither acceptance nor custody transfer",
            "Either principal may finish an actually accepted assignment early; do not pad runtime or turn incidental lifecycle work into polling/relay turns.",
        ),
    ),
    (
        "material-checkpoint-economy",
        RELIABILITY,
        None,
        (
            "**Recovery gap, not run length** is the invariant",
            "Necessary calls/time are not stop triggers.",
            "Apply ACTIVE_EXECUTION 7A/8 after each phase: verify/save, reassess and start the next safe authorized critical-path phase in the same healthy turn.",
            "A task/checkpoint alone is not a stop.",
            "no tool-call counter triggers a checkpoint, authority recap or stop",
            "ACTIVE_EXECUTION recovery-gap law controls milestone saves",
            "A timeout is never permission to replay the command.",
        ),
    ),
    (
        "continuation-gate-is-not-a-timer",
        ACTIVE,
        None,
        (
            "An ordinary clean task/phase/chunk/checkpoint boundary, review request, owner message, pending CI, completed plan or time target cannot end healthy useful work; elapsed time alone never qualifies.",
            "A checkpoint is not itself a reason to stop or claim partial work `PROVEN_OUTCOME`.",
            "start that next phase in the same turn",
        ),
    ),
    (
        "no-routine-signoff",
        ACTIVE,
        "## Start and recover without administrative ceremony",
        (
            "Do not ask the Chairman to re-approve routine in-scope execution or reversible design/build/test/repair.",
            "Gate reserved decisions, material scope/risk/spend/authority expansions and actual platform confirmation/authentication/consent; playbooks add no approval round.",
        ),
    ),
    (
        "denial-and-unknown-effect-fences",
        ACTIVE,
        "## Start and recover without administrative ceremony",
        (
            "A platform refusal is action-scoped until evidence proves otherwise",
            "Action-scoped refusal is not mission-wide refusal.",
            "Independent work must not reproduce the denied/uncertain effect.",
            "The first explicit safety or permission denial ends retry: no rephrasing or tool/carrier/account/model/provider substitution.",
            "`EFFECT_UNKNOWN` must be reconciled at the original target before dependent work.",
            "An explicit permission/safety denial ends retries; an uncertain effect remains frozen on its original carrier.",
            "Do not route around either via another branch/provider/writer.",
        ),
    ),
    (
        "lane-local-blocker",
        ACTIVE,
        "## Step 4 — Treat a blocker as lane-local first",
        (
            "advance the highest-value safe path-disjoint dependency",
            "Lane switching never evades denial or uncertainty through another tool/carrier/device/provider.",
            "With an uncertain effect, continue only work whose safety and result are provably independent of it; otherwise reconcile on the original carrier.",
        ),
    ),
    (
        "escalation-is-reserved-not-routine",
        ACTIVE,
        "## Step 6 — Discover exact action capability, then react to evidence",
        (
            "A worker/COO `BLOCKED`/`DECISION_REQUEST` is evidence, not a self-authenticating gate.",
            "Escalate only a proven boundary or decision reserved by source law.",
        ),
    ),
    (
        "paper-explicit-identity-requirement",
        PAPER,
        CLEANUP_HEADING,
        (
            "not automatically a requirement to preserve their internal page/artboard/node identities",
            "unless the assignment actually requires unchanged internal IDs",
        ),
    ),
    (
        "paper-verified-destination-and-original-preservation",
        PAPER,
        CLEANUP_HEADING,
        (
            "First inspect the exact source and destination files and check whether the user or another admitted writer already copied the destination.",
            "Define acceptance in visible content, component quality, working navigation/references and absence of unwanted duplicates",
            "copy or reconstruct into the verified destination, compare and repair",
            "then retire the old version only after destination verification and an authorized deletion path",
            "Preserve originals and report any cleanup that remains unperformed.",
        ),
    ),
    (
        "paper-cleanup-denial-fence",
        PAPER,
        CLEANUP_HEADING,
        (
            "If the actual catalog supports an authorized direct move, use it.",
            "An unsupported cross-file move is a blocker for that method, not proof that destination inspection, existing-copy verification, in-place editing, reference repair or other in-scope cleanup cannot proceed.",
            "do not invent calls, switch carriers after a denial, or use raw filesystem/UI workarounds against the guarded bridge.",
        ),
    ),
    (
        "paper-carrier-effect-fence",
        PAPER,
        None,
        (
            "A denial is not a fallback invitation",
            "On `EFFECT_UNKNOWN`, stop writes.",
            "never replay the edit through another carrier",
            "Never blindly replay or mint a new ID to retry.",
        ),
    ),
    (
        "paper-no-routine-design-signoff",
        PAPER,
        CLEANUP_HEADING,
        (
            "Do not require another human design-signoff for routine reversible choices already covered by the current assignment.",
            "When one target or operation is genuinely blocked, continue safe, path-disjoint approved Paper work or reference cleanup through its legitimate owner",
            "do not declare the entire commissioned reorganization complete on the strength of an assessment.",
        ),
    ),
    (
        "paper-preview-is-not-completion",
        PAPER,
        "## Preserve capacity and truth",
        (
            "If the assigned outcome is an edit to the Paper canvas, a standalone HTML preview, screenshot mock, or downloadable touch-up package is supporting work, **not completion**.",
            "Do not substitute a preview merely because the Paper carrier was unprobed.",
            "`NOT_APPLIED_TO_PAPER`",
        ),
    ),
)

FAMILY_IDS = [family for family, _rel, _heading, _clauses in FAMILIES]


def _scope(rel: Path, heading: str | None) -> str:
    return _section_body(rel, heading) if heading else _words(rel)


def _family_complete(scope: str, clauses: tuple[str, ...]) -> bool:
    return all(clause in scope for clause in clauses)


@pytest.mark.parametrize(
    "family,rel,heading,clauses", FAMILIES, ids=FAMILY_IDS
)
def test_obligation_family_is_complete_at_its_canonical_owner(
    family: str, rel: Path, heading: str | None, clauses: tuple[str, ...]
) -> None:
    scope = _scope(rel, heading)
    missing = [clause for clause in clauses if clause not in scope]
    where = f"{rel.name} § {heading}" if heading else rel.name
    assert not missing, f"{family}: canonical owner {where} lost {missing}"


@pytest.mark.parametrize(
    "family,rel,heading,clauses", FAMILIES, ids=FAMILY_IDS
)
def test_clause_loss_from_the_canonical_owner_breaks_its_obligation_family(
    family: str, rel: Path, heading: str | None, clauses: tuple[str, ...]
) -> None:
    """Each clause is load-bearing: deleting any one makes the family incomplete."""
    scope = _scope(rel, heading)
    for clause in clauses:
        mutated = scope.replace(clause, "")
        assert clause not in mutated, f"{family}: mutant did not remove {clause!r}"
        assert not _family_complete(mutated, clauses), (
            f"{family}: dropping {clause!r} left the family apparently complete"
        )


def test_paper_cleanup_section_precedes_the_scope_anchor() -> None:
    """The cleanup guidance belongs to the Paper skill, before the scope anchor."""
    text = _raw(PAPER)
    assert text.count(CLEANUP_HEADING) == 1
    assert text.count(SCOPE_ANCHOR) == 1
    assert text.index(CLEANUP_HEADING) < text.index(SCOPE_ANCHOR), (
        "the non-destructive cleanup section must precede the unique scope anchor"
    )


CLEANUP_CONDITIONS = (
    "already copied the destination",
    "unless the assignment actually requires unchanged internal IDs",
    "an authorized deletion path",
    "Preserve originals and report any cleanup that remains unperformed.",
    "switch carriers after a denial",
    "Do not require another human design-signoff",
)


def _require_cleanup_body(text: str, heading: str) -> None:
    body = _section_body_from_text(text, heading)
    assert body.strip(), f"{heading!r} has an empty body"
    for condition in CLEANUP_CONDITIONS:
        assert condition in body, f"{heading!r}: missing local condition {condition!r}"


def test_paper_cleanup_section_keeps_its_own_body() -> None:
    """The composed section carries its conditions; it is not an empty heading."""
    _require_cleanup_body(_raw(PAPER), CLEANUP_HEADING)
    # A heading alone, or a body moved under a different heading, is not recovery.
    with pytest.raises(AssertionError):
        _require_cleanup_body(
            CLEANUP_HEADING + "\n\nUnrelated navigation text.\n", CLEANUP_HEADING
        )
    with pytest.raises(AssertionError):
        _require_cleanup_body(
            CLEANUP_HEADING + "\n\n### Unrelated section\n"
            + _section_body(PAPER, CLEANUP_HEADING),
            CLEANUP_HEADING,
        )


def _scenario_contract_ok(scenarios: list) -> bool:
    if [row["scenario_id"] for row in scenarios] != EXPECTED_SCENARIOS:
        return False
    for row in scenarios:
        if set(row) != {"scenario_id", "prompt", "pass_requires"}:
            return False
        if not (70 <= len(row["prompt"]) <= 1500):
            return False
        if not (80 <= len(row["pass_requires"]) <= 1500):
            return False
        if not row["pass_requires"].startswith("PASS:"):
            return False
        if "FAIL:" not in row["pass_requires"]:
            return False
    corpus = " ".join(row["prompt"] + " " + row["pass_requires"] for row in scenarios)
    return all(
        phrase in corpus
        for phrase in (
            "identity-preserving cross-file move",
            "signoff",
            "checkpoint",
            "permission",
            "EFFECT_UNKNOWN",
            "research-only",
        )
    )


def test_adversarial_extra_high_scenarios_cover_delivery_and_safety():
    scenarios = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert [row["scenario_id"] for row in scenarios] == [
        "EHX01", "EHX02", "EHX03", "EHX04",
        "EHX05", "EHX06", "EHX07", "EHX08",
    ]
    for row in scenarios:
        assert set(row) == {"scenario_id", "prompt", "pass_requires"}
        assert 70 <= len(row["prompt"]) <= 1500
        assert 80 <= len(row["pass_requires"]) <= 1500
        assert row["pass_requires"].startswith("PASS:")
        assert "FAIL:" in row["pass_requires"]
    corpus = " ".join(row["prompt"] + " " + row["pass_requires"] for row in scenarios)
    for phrase in (
        "identity-preserving cross-file move",
        "signoff",
        "checkpoint",
        "permission",
        "EFFECT_UNKNOWN",
        "research-only",
    ):
        assert phrase in corpus


def test_a_dropped_required_scenario_breaks_the_scenario_contract() -> None:
    """Every required EHX scenario is load-bearing for the corpus contract."""
    scenarios = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert _scenario_contract_ok(scenarios)
    for row in scenarios:
        dropped = [other for other in scenarios if other["scenario_id"] != row["scenario_id"]]
        assert not _scenario_contract_ok(dropped), (
            f"dropping {row['scenario_id']!r} left the scenario contract intact"
        )
