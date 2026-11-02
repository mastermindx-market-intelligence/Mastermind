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
