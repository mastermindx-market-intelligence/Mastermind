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
    index = _read("docs/sol_skills/INDEX.md")
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
    index = _read("docs/sol_skills/INDEX.md")
    assert "whenever a session expects more than three tool calls" in index
    assert "substantial Web CEO work" in index
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
    index = _read("docs/sol_skills/INDEX.md")
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
