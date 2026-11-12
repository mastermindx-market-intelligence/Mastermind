"""Bounded regression for the 2026-11-02 delivery-procedure compaction candidate.

Proves that the compacted instruction files still (a) carry compatible Sol
Skillpack identity, (b) resolve every owner/source path they reference, and
(c) keep their mandatory load gates and finalization-owner enrollment. These
are static source-contract checks only; they are not fresh-session behavior.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKILLPACK_FILES = {
    "docs/sol_skills/INDEX.md": "index",
    "docs/sol_skills/COLD_START.md": "cold_start",
    "docs/sol_skills/ACTIVE_EXECUTION.md": "active_execution",
    "docs/sol_skills/SESSION_RELIABILITY.md": "session_reliability",
    "docs/sol_skills/WEB_CEO_DELEGATION.md": "web_ceo_delegation",
}

OTHER_TARGETS = (
    "docs/CEO_PROJECT_PLAN_CONTINUITY.md",
    "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md",
)

_ALL_TARGETS = tuple(SKILLPACK_FILES) + OTHER_TARGETS


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_target_files_exist_with_compatible_skillpack_identity() -> None:
    for rel, expected_skill in SKILLPACK_FILES.items():
        match = re.match(r"^---\n(.*?)\n---\n", _read(rel), re.DOTALL)
        assert match, f"{rel}: missing frontmatter"
        meta = dict(
            line.split(":", 1) for line in match.group(1).splitlines() if ":" in line
        )
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        assert meta == {
            "schema": "mastermind.sol_skillpack.v1",
            "skillpack_version": "1.0.1",
            "minimum_bootstrap_major": "1",
            "skill": expected_skill,
        }, f"{rel}: frontmatter drifted: {meta}"
    for rel in OTHER_TARGETS:
        assert (ROOT / rel).is_file(), f"missing target: {rel}"


def test_owner_and_source_links_referenced_by_targets_resolve() -> None:
    pattern = re.compile(r"`((?:docs|skills|config)/[A-Za-z0-9_./-]+\.(?:md|yml|json))`")
    for rel in _ALL_TARGETS:
        text = _read(rel)
        missing = sorted(
            {
                ref
                for ref in pattern.findall(text)
                if not (ROOT / ref).is_file()
            }
        )
        assert not missing, f"{rel}: referenced source links do not resolve: {missing}"


def test_load_gates_remain_mandatory_after_consolidation() -> None:
    index = " ".join(_read("docs/sol_skills/INDEX.md").split())
    assert "## Atomic-load law" in index
    assert "modifying workflow is unavailable" in index
    assert "from **that same commit SHA**" in index
    for marker in (
        "### `COLD_START.md`",
        "### `ACTIVE_EXECUTION.md`",
        "### `SESSION_RELIABILITY.md`",
        "### `WEB_CEO_DELEGATION.md`",
    ):
        assert marker in index, f"INDEX selection entry missing: {marker}"
    assert "Mandatory after current-state recovery" in index
    assert "Mandatory companion" in index
    assert "Mandatory repository-source companion" in index
    active = " ".join(_read("docs/sol_skills/ACTIVE_EXECUTION.md").split())
    assert "Use this skill after current-state recovery" in active
    assert "Mandatory" not in active.split("## Step 1 ")[0].split("## Mission")[0]
    companion = " ".join(_read("docs/sol_skills/WEB_CEO_DELEGATION.md").split())
    assert "Enrolled companion procedure" in companion
    assert "same pinned INDEX" in companion
    plan = _read("docs/CEO_PROJECT_PLAN_CONTINUITY.md")
    assert "docs/sol_skills/INDEX.md" in plan
    addendum = _read("docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md")
    assert "docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md" in addendum
    assert "docs/EXECUTIVE_WORKER_ROUTING.md" in addendum


# ---------------------------------------------------------------------------
# Required-read bundle regressions (2026-11-02 repair).
#
# These inspect the existing markdown load declarations only; there is no
# runtime policy engine. Byte ceilings are measured UTF-8 sizes of the same
# files at protected pin 22c08067ed0f480d1d5324a815fa248661c4ab46, so each
# profile bundle must stay strictly below its pre-compaction size. They are
# not pins on current wording.
_PIN_BYTES = {
    "docs/sol_skills/INDEX.md": 20014,
    "docs/sol_skills/COLD_START.md": 10830,
    "docs/sol_skills/ACTIVE_EXECUTION.md": 56650,
    "docs/sol_skills/SESSION_RELIABILITY.md": 16465,
    "docs/sol_skills/WEB_CEO_DELEGATION.md": 17925,
    "docs/CEO_PROJECT_PLAN_CONTINUITY.md": 20640,
    "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md": 25275,
}


def _bundle_bytes(rels: tuple[str, ...]) -> int:
    return sum(len(_read(rel).encode("utf-8")) for rel in rels)


def test_profile_ordinary_one_phase_source_task_bundle() -> None:
    """One-phase source task: INDEX + COLD_START + ACTIVE_EXECUTION only.

    The conditional companions (SESSION_RELIABILITY, WEB_CEO_DELEGATION,
    CEO_PROJECT_PLAN_CONTINUITY) must keep their conditional INDEX load gates
    so this bundle does not silently grow a fourth mandatory file.
    """
    index = " ".join(_read("docs/sol_skills/INDEX.md").split())
    assert "whenever a session expects more than three tool calls" in index
    assert 'substantial Web CEO principal-duty' in index
    assert "**multi-phase project**" in index
    assert "Tiny one-phase tasks need no new plan" in index
    bundle = (
        "docs/sol_skills/INDEX.md",
        "docs/sol_skills/COLD_START.md",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
    )
    assert _bundle_bytes(bundle) < sum(_PIN_BYTES[rel] for rel in bundle)


def test_profile_multi_phase_delegated_project_bundle() -> None:
    """Multi-phase delegated CEO project adds PLAN, WEB_CEO and the routing addendum."""
    index = " ".join(_read("docs/sol_skills/INDEX.md").split())
    assert "Mandatory repository-source companion" in index
    assert "Mandatory companion to `ACTIVE_EXECUTION.md`" in index
    assert "For every meaningful worker/model delegation" in index
    bundle = (
        "docs/sol_skills/INDEX.md",
        "docs/sol_skills/COLD_START.md",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
        "docs/CEO_PROJECT_PLAN_CONTINUITY.md",
        "docs/sol_skills/WEB_CEO_DELEGATION.md",
        "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md",
    )
    assert _bundle_bytes(bundle) < sum(_PIN_BYTES[rel] for rel in bundle)


def test_profile_error_and_unknown_effect_recovery_bundle() -> None:
    """Recovery law stays present in the two recovery owners after consolidation."""
    active = " ".join(_read("docs/sol_skills/ACTIVE_EXECUTION.md").split())
    for gate in (
        "A platform refusal is action-scoped until evidence proves otherwise",
        "Action-scoped refusal is not mission-wide refusal",
        "TOOL_DEGRADED / EFFECT_NONE",
        "EFFECT_NONE is not retry permission",
        "`EFFECT_UNKNOWN` must be reconciled at the original target",
        "do not enter an identical third loop",
        "`NOT_CANONICALLY_PERSISTED`",
    ):
        assert gate in active, f"recovery gate dropped from ACTIVE_EXECUTION: {gate}"
    reliability = " ".join(_read("docs/sol_skills/SESSION_RELIABILITY.md").split())
    for gate in (
        "`SESSION_HEALTHY`",
        "`ROTATION_SUSPECTED`",
        "`ROTATION_REQUIRED`",
        "`STREAM_ATTACHMENT_UNCERTAIN`",
        "A timeout is never permission to replay the command",
        "`NOT_CANONICALLY_PERSISTED`",
        "A successor must reconcile and persist",
    ):
        assert gate in reliability, f"recovery gate dropped from SESSION_RELIABILITY: {gate}"
    # Missing/ambiguous required-action law must not silently drop: the
    # persistence-failure disposition mapping stays stated at its owner.
    for gate in (
        "`EFFECT_UNKNOWN` only for an ambiguous checkpoint write",
        "`EXACT_HUMAN_GATE` only for a real human/admin ceremony",
        "`MORE_WORK_EXISTS` when safe independent work remains",
    ):
        assert gate in active, f"disposition mapping dropped: {gate}"


# Immutable public navigation baseline, not a second policy source.
import hashlib
import json
import pytest

PUBLIC_HEADING_MANIFEST = ROOT / "tests/fixtures/delivery_compaction_public_headings_22c08067.json"
PUBLIC_HEADING_SHA256 = "c6686d9d5c10737356bfdf6a1d2da6d5e717cd911c489bffbd580edc9f4e7015"
_PUBLIC_BASELINE = json.loads(PUBLIC_HEADING_MANIFEST.read_text())


def _public_headings(text: str) -> list[str]:
    result: list[str] = []
    fence = None
    for line in text.splitlines():
        mark = re.match(r"^\s*(`{3,}|~{3,})", line)
        if mark:
            char = mark.group(1)[0]
            if fence is None:
                fence = char
            elif char == fence:
                fence = None
            continue
        if fence is None and re.match(r"^#{1,6} ", line):
            result.append(line)
    return result


def _require_public_headings(text: str, expected: list[str]) -> None:
    actual = _public_headings(text)
    cursor = 0
    for heading in expected:
        assert actual.count(heading) == expected.count(heading), heading
        assert heading in actual[cursor:], f"missing or reordered: {heading}"
        cursor = actual.index(heading, cursor) + 1


def test_public_heading_manifest_retains_immutable_source_identity() -> None:
    assert hashlib.sha256(PUBLIC_HEADING_MANIFEST.read_bytes()).hexdigest() == PUBLIC_HEADING_SHA256
    assert _PUBLIC_BASELINE["baseline_sha"] == "22c08067ed0f480d1d5324a815fa248661c4ab46"
    assert set(_PUBLIC_BASELINE["files"]) == set(_ALL_TARGETS)


@pytest.mark.parametrize("rel", _ALL_TARGETS)
def test_all_original_public_headings_remain_ordered(rel: str) -> None:
    _require_public_headings(_read(rel), _PUBLIC_BASELINE["files"][rel]["headings"])


@pytest.mark.parametrize("rel,removed", [
    (rel, heading)
    for rel, item in _PUBLIC_BASELINE["files"].items()
    for heading in item["headings"]
])
def test_public_heading_guard_rejects_every_missing_anchor(rel: str, removed: str) -> None:
    # A pinned baseline skeleton makes each mutant independent of other defects.
    expected = _PUBLIC_BASELINE["files"][rel]["headings"]
    text = "\n\n".join(expected)
    _require_public_headings(text, expected)
    mutant = text.replace(removed + "\n", "", 1) if removed != expected[-1] else text[:text.rfind(removed)]
    with pytest.raises(AssertionError):
        _require_public_headings(mutant, expected)


# Each repaired leaf must lead to relevant content, not an empty heading alias.
_LEAF_CONTENT = {
    "docs/sol_skills/ACTIVE_EXECUTION.md": {
        "### A \u2014 local human gate, another lane open": ("HUMAN_AUTH", "unblocked lane"),
        "### B \u2014 GitHub reads observed, write unprobed": ("UNPROBED", "non-mutating permission/preflight"),
        "### B2 \u2014 exact write refusal is proven": ("dummy mutation", "platform-wide write claim"),
        "### C \u2014 protected master moves on unrelated paths": ("bounded compatibility check", "Do not restart"),
        "### D \u2014 artifact substitution": ("NO_DELTA_LOOP", "capability step"),
        "### E \u2014 turn-independent execution claim": ("canonical durable executor", "continue it"),
    },
    "docs/sol_skills/SESSION_RELIABILITY.md": {
        "### Per response": ("8 KiB", "16 KiB", "100 matches"),
        "### Per active turn": ("32 KiB", "no tool-call counter"),
        "### Commands and processes": ("15 seconds", "30 seconds", "PID"),
        "## Conversation-context discipline": ("raw tool history", "Never reconstruct"),
        "### `STREAM_ATTACHMENT_UNCERTAIN`": ("UI/client stream", "Reacquire/read observable state"),
        "### `TURN_EXECUTION_ENDED`": ("same conversation", "Reconcile PID/action/effect"),
        "### `SESSION_UNSTABLE`": ("Persist the frontier", "fresh same-mode chat"),
        "### `WORKSPACE_OR_EFFECT_UNCERTAIN`": ("same-carrier reconciliation", "EFFECT_UNKNOWN"),
        "### Failure inside one tool call": ("tool/host boundary", "carrier"),
        "### First terminal generation failure after a completed tool call": ("at most one bounded recovery", "ROTATION_SUSPECTED"),
        "### Second consecutive terminal generation failure": ("ROTATION_REQUIRED", "REPEATED_TERMINAL_GENERATION_FAILURE"),
        "### Fresh conversation fails before its first tool call": ("unresolved effect", "clean/private browser profile"),
        "### Failure persists across clean environments": ("sanitized support packet", "excluding credentials"),
    },
}


def _leaf_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    assert lines.count(heading) == 1, heading
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if re.match(r"^#{1,6} ", lines[i])), len(lines))
    return " ".join(lines[start:end])


def _require_leaf_content(text: str, heading: str, terms: tuple[str, ...]) -> None:
    body = " ".join(_leaf_body(text, heading).split())
    for term in terms:
        assert term in body, f"{heading}: missing local content {term}"


@pytest.mark.parametrize("rel,heading,terms", [
    (rel, heading, terms) for rel, sections in _LEAF_CONTENT.items() for heading, terms in sections.items()
])
def test_repaired_anchor_has_its_own_meaningful_body(rel: str, heading: str, terms: tuple[str, ...]) -> None:
    text = _read(rel)
    _require_leaf_content(text, heading, terms)
    body = _leaf_body(text, heading)
    assert body.strip()
    # A heading alone, or a body moved under a different heading, is not recovery.
    with pytest.raises(AssertionError):
        _require_leaf_content(heading + "\n\nUnrelated navigation text.\n", heading, terms)
    with pytest.raises(AssertionError):
        _require_leaf_content(heading + "\n\n### Unrelated section\n" + body, heading, terms)


def test_tool_heavy_and_multi_phase_profiles_include_reliability() -> None:
    assert "more than three tool calls" in _read("docs/sol_skills/INDEX.md")
    ordinary = tuple(SKILLPACK_FILES)[:4]
    assert _bundle_bytes(ordinary) < sum(_PIN_BYTES[p] for p in ordinary)
    assert _bundle_bytes(_ALL_TARGETS) < sum(_PIN_BYTES[p] for p in _ALL_TARGETS)



# ---------------------------------------------------------------------------
# Clause-loss regressions for the consolidated delivery procedures (2026-11-02
# second pass).
#
# Each entry names the canonical owner of an obligation family and the distinct
# clauses that together establish it. A family is only complete when every
# clause is still present at that owner, so a consolidation that folds one
# protected condition away is detected instead of silently reducing the
# procedure. The mutant cases below delete a clause from its owner and require
# the family to become incomplete, and two of the families are additionally
# checked against INDEPENDENT guards that already existed in this repository
# (the stop-at-blocker protective contract and the repaired leaf-content
# contract), so a dropped clause is caught by code that is not this table.
CONSOLIDATED_FAMILIES = (
    (
        "denied-effect-unknown",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
        (
            "A platform refusal is action-scoped until evidence proves otherwise",
            "Action-scoped refusal is not mission-wide refusal.",
            "EFFECT_NONE is not retry permission",
            "`EFFECT_UNKNOWN` must be reconciled at the original target",
            "do not enter an identical third loop",
            "verified access restriction",
            'other-account work requires ordinary routing and genuine independence',
            "TOOL_DEGRADED / EFFECT_NONE",
        ),
    ),
    (
        "live-writer-custody",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
        (
            "Responsibility survives a chat; a chat does not own work forever",
            "fresh live claim, source-writer custody and pending effects",
            "unknown is not expired",
            'CAS/fencing',
            'With assignment and no displaced writer/effect',
            'act without a ghost ACK',
            "The active assigned session owns the next recovery action",
        ),
    ),
    (
        "provider-capacity-and-transport",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
        (
            "Preserve provider capacity; do not turn a refusal into filter-probing",
            'Unknown throttling thresholds do not justify blocked-call experiments',
            'no rephrasing or tool/carrier/account/model/provider substitution',
            "Do not contaminate provider-refusal evidence with transport loss",
            'Offline/timeout without explicit safety evidence is transport, not throttling',
            'Cause differs from effect',
            'without explicit safety evidence is transport',
        ),
    ),
    (
        "closure-continuation",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
        (
            "PROVEN_OUTCOME",
            "EXACT_HUMAN_GATE",
            "ALL_SCOPED_LANES_BLOCKED",
            "DURABLE_EXECUTION_RUNNING",
            "CHECKPOINTED_CONTINUATION",
            "`MORE_WORK_EXISTS` when safe independent work remains",
            "`NOT_CANONICALLY_PERSISTED`",
            "MISSION_COMPLETE: false",
        ),
    ),
    (
        "capability-discovery",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
        (
            "`UNKNOWN` / `UNPROBED` is never equivalent to `UNAVAILABLE`",
            "Never perform a dummy mutation solely to prove capability",
            'that state is `MORE_WORK_EXISTS`',
            "Step 6 negative-capability evidence",
            'Online/ping proves neither file/process/browser/desktop/provider readiness',
        ),
    ),
    (
        "session-reliability-budgets",
        "docs/sol_skills/SESSION_RELIABILITY.md",
        (
            "8 KiB or 150 lines",
            "16 KiB",
            "100 matches",
            "32 KiB",
            "15 seconds",
            "30 seconds",
            "12 KiB / 1500 words",
            "A timeout is never permission to replay the command",
        ),
    ),
    (
        "session-reliability-failure-layers",
        "docs/sol_skills/SESSION_RELIABILITY.md",
        (
            "STREAM_ATTACHMENT_UNCERTAIN",
            "TURN_EXECUTION_ENDED",
            "SESSION_UNSTABLE",
            "WORKSPACE_OR_EFFECT_UNCERTAIN",
            "NOT_CANONICALLY_PERSISTED",
            "A successor must reconcile and persist",
        ),
    ),
    (
        "delegation-economics-and-capacity",
        "docs/sol_skills/WEB_CEO_DELEGATION.md",
        (
            "CONCENTRATED_JUDGMENT",
            "SUSTAINED_ORCHESTRATION",
            "OPERATOR_OWNED_DELIVERY",
            "Model Router fixes the first lawful suitability tier",
            'not duration guarantees, model aliases or Runtime roles/admission',
            "ordinary return adjudication",
            'same scarce subscription pool as Astra/Fable',
            "EFFECT_UNKNOWN",
        ),
    ),
    (
        "mode-and-provider-economics",
        "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md",
        (
            "COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT",
            "CHAT_REASONING_MODE: NON_PRO_DEFAULT",
            "CHAT_REASONING_MODE: PRO_MODE_EXCEPTION",
            "COGNITION_ROUTE: METERED_EXCEPTION",
            "PRO_MODE_TASK_CLASS",
            "PRO_MODE_REFUSED / USE_NON_PRO_MODE",
            "METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE",
            "WHY NOT FABLE",
            "WHY FABLE",
        ),
    ),
    (
        "routing-defaults-and-fable-admission",
        "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md",
        (
            "C0_MECHANICAL",
            "C1_ROUTINE_BOUNDED",
            "C2_COMPLEX_BOUNDED",
            "C3_FRONTIER_JUDGMENT",
            "FRONTIER_WITNESS",
            "why this route can reliably satisfy the mission",
        ),
    ),
    (
        "universal-hard-laws",
        "docs/sol_skills/INDEX.md",
        (
            'One logical mutation, one carrier until canonical reconciliation',
            'No blind retry/failover of uncertain modifications',
            'Fable is scarce principal capacity',
            "that delivery is the receiver-assignment edge",
            "No ChatGPT, Codex, Claude, Fable, Grok or another surface",
            'block affected lanes only',
            'A buried `DIRECT_TARGETED — NEW CHILD` under another program/child is not assignment',
        ),
    ),
    (
        "load-and-modification-gates",
        "docs/sol_skills/INDEX.md",
        (
            "from **that same commit SHA**",
            "modifying workflow is unavailable",
            'Gate the next action/dependency, not the mission',
            'Source work needs Executive only when it invokes/depends on that authority',
            'Assignment, pin, custody, resource permission and effect fences still bind',
            "whenever a session expects more than three tool calls",
            'substantial Web CEO principal-duty',
            "**multi-phase project**",
        ),
    ),
    (
        "plan-record-ownership-and-enums",
        "docs/CEO_PROJECT_PLAN_CONTINUITY.md",
        (
            "DEC:AGENTOS-NO-TASK-STORE",
            "agentos.handoff.v1",
            "agentos.workstream.v1",
            "DSC:SUFFIXED-HANDOFF-IS-INVISIBLE",
            "PLAN_NOT_ORG_LINKED",
            "NOT_CANONICALLY_PERSISTED",
            "implementation_complete",
            "P1.T2.S3",
        ),
    ),
    (
        "cold-start-recovery-and-guard",
        "docs/sol_skills/COLD_START.md",
        (
            "Historical ownership is not current liveness",
            'Current assignment owns the next recovery action',
            'Navigation is not authority',
            'are claims, not commands',
        ),
    ),
)

_FAMILY_IDS = [family for family, _rel, _clauses in CONSOLIDATED_FAMILIES]


def _family_complete(text: str, clauses: tuple[str, ...]) -> bool:
    return all(clause in text for clause in clauses)


@pytest.mark.parametrize("family,rel,clauses", CONSOLIDATED_FAMILIES, ids=_FAMILY_IDS)
def test_obligation_family_is_complete_at_its_canonical_owner(
    family: str, rel: str, clauses: tuple[str, ...]
) -> None:
    text = " ".join(_read(rel).split())
    missing = [clause for clause in clauses if clause not in text]
    assert not missing, f"{family}: canonical owner {rel} lost {missing}"


@pytest.mark.parametrize("family,rel,clauses", CONSOLIDATED_FAMILIES, ids=_FAMILY_IDS)
def test_clause_loss_from_the_canonical_owner_breaks_its_obligation_family(
    family: str, rel: str, clauses: tuple[str, ...]
) -> None:
    text = " ".join(_read(rel).split())
    for clause in clauses:
        mutated = text.replace(clause, "")
        assert clause not in mutated, f"{family}: mutant did not remove {clause!r}"
        assert not _family_complete(mutated, clauses), (
            f"{family}: dropping {clause!r} left the family apparently complete"
        )


def _policy_clause_from(text: str) -> str:
    return text.split("**Stop-at-blocker falsifier.**", 1)[1].split(
        "## Step 1 — Freeze the active-turn frame", 1
    )[0]


def test_stop_at_blocker_clause_loss_is_rejected_by_the_independent_repository_guard() -> None:
    """The stop-at-blocker mutants are caught by the owning test module, not here."""
    import sys

    sys.path.insert(0, str(ROOT / "tests"))
    try:
        import test_sol_stop_at_blocker_regression as blocker
    finally:
        sys.path.pop(0)

    clause = _policy_clause_from(_read("docs/sol_skills/ACTIVE_EXECUTION.md"))
    assert blocker._has_protective_contract(clause)
    for deleted in (
        "pre-effect *technical* refusal",
        "explicit permission/safety denial",
        "uncertain effect remains frozen",
        "Do not route around",
        "Step 6 negative-capability evidence",
        "genuinely independent authorized",
    ):
        damaged = clause.replace(deleted, "", 1)
        assert deleted not in damaged, f"mutant did not remove {deleted!r}"
        assert not blocker._has_protective_contract(damaged), (
            f"the owning repository guard accepted a clause missing {deleted!r}"
        )


def test_pressure_case_clause_loss_is_rejected_by_the_independent_leaf_guard() -> None:
    """Deleting a repaired leaf body is caught by the leaf-content contract."""
    heading = "### B2 — exact write refusal is proven"
    terms = ("dummy mutation", "platform-wide write claim")
    text = _read("docs/sol_skills/ACTIVE_EXECUTION.md")
    assert _leaf_body(text, heading).strip()
    start = text.index(heading)
    end = text.index("\n### ", start + len(heading))
    region = text[start:end]
    damaged = text[:start] + region.replace("dummy mutation", "the mutation", 1) + text[end:]
    assert "dummy mutation" not in damaged[start : start + len(region)]
    with pytest.raises(AssertionError):
        _require_leaf_content(damaged, heading, terms)


def test_consolidated_companion_points_at_owners_that_are_mandatory_before_the_action() -> None:
    """The delegation companion names the owners of the rules it no longer repeats."""
    text = " ".join(_read("docs/sol_skills/WEB_CEO_DELEGATION.md").split())
    assert "Canonical owners:" in text
    assert "ACTIVE_EXECUTION (Steps 2A, 2B, 3, 8)" in text
    assert "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md" in text
    assert "mandatory for every meaningful worker/model delegation" in text
    assert "Load those owners from the same pin before the action they constrain" in text
    for owner in ("docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md", "docs/sol_skills/ACTIVE_EXECUTION.md"):
        assert (ROOT / owner).is_file()


# Core seven-file ceiling: +500 bytes for the conditional operations INDEX entry.
# This explicitly adjusts the navigation budget from 100_000 bytes; it does not
# add an eighth corpus member or a universal mandatory load. Keep the original
# 167_799-byte baseline and >=40% reduction invariant below.
def test_original_compaction_goal_is_met_without_changing_the_baseline() -> None:
    total = _bundle_bytes(_ALL_TARGETS)
    baseline = sum(_PIN_BYTES[rel] for rel in _ALL_TARGETS)
    assert baseline == 167_799
    assert total <= 100_500, f"seven-file corpus is {total} bytes"
    assert total * 100 <= baseline * 60, "less than 40% source reduction"


@pytest.mark.parametrize("rels", (
    tuple(SKILLPACK_FILES)[:3],
    tuple(SKILLPACK_FILES)[:4],
    _ALL_TARGETS,
), ids=("short-source", "tool-heavy-source", "delegated-tool-heavy"))
def test_each_actual_required_read_profile_meets_the_original_reduction(rels) -> None:
    # Same file unions, including reliability when its existing trigger applies.
    assert _bundle_bytes(rels) * 100 <= sum(_PIN_BYTES[p] for p in rels) * 60


# The old protected-base composition duplicated this independently added entry.
def _single_current_review_entry(text: str) -> None:
    heading = "### `docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md`"
    assert text.count(heading) == 1, "current review-routing entry must occur once"
    section = text.split(heading, 1)[1].split("\n### ", 1)[0]
    assert "before choosing an avenue" in section
    assert "same" in section and "verified protected Mastermind commit" in section


def test_current_review_routing_entry_is_unique_and_action_gated() -> None:
    _single_current_review_entry(_read("docs/sol_skills/INDEX.md"))


@pytest.mark.parametrize("mutation", ("missing", "duplicate"))
def test_current_review_routing_entry_rejects_missing_or_duplicate(mutation) -> None:
    text = _read("docs/sol_skills/INDEX.md")
    heading = "### `docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md`"
    changed = text.replace(heading, "### missing-review-entry", 1) if mutation == "missing" else text + "\n" + heading + "\n"
    with pytest.raises(AssertionError):
        _single_current_review_entry(changed)
