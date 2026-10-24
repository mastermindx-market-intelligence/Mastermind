"""Fail when an instruction surface tells a session to wait for a named owner.

The Chairman directive of 2026-10-24, reconciled with PR #1842, is one clause:
ownership is a role held by the session doing the work. A stall phrase is allowed
only in the same file as that leadership-takeover clause, or when the same line
negates the stall.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

CLAUSE_MARKERS = (
    "Ownership is a role, not a session",
    "assumes leadership",
    "records the takeover",
    "never self-merge or approve",
)

# Instruction and bootstrap surfaces. Historical research and hash-pinned
# operator overlays are outside this set.
SCAN_ROOTS = (
    "AGENTS.md",
    "CLAUDE.md",
    "MAINTENANCE.md",
    "config/authority_map.yml",
    "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md",
    "docs/CEO_BOOT_PACKET.md",
    "docs/DELIVERY_WORKFLOW.md",
    "docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md",
    "docs/templates",
    "docs/sol_skills",
    "docs/claude_capability_hardening_20261004/EXECUTION_AND_RELEASE.md",
    ".cursor/rules",
    ".codex",
    ".claude",
    "plugins/mastermind-sol/skills",
    "plugins/mastermind-sol/references/authority-boundaries.md",
    "plugins/mastermind-sol/references/codex-agents",
    "control_plane/ceo_boot_packet.py",
    "integrations/session_bridge/paid_operator/fabric_operator_client.py",
)

ENTRYPOINTS = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/sol_skills/BOOTSTRAP_KERNEL.md",
    "docs/sol_skills/ACTIVE_EXECUTION.md",
    "docs/sol_skills/COLD_START.md",
    "docs/sol_skills/WORKER_AVENUE_ROUTING.md",
    "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md",
    ".cursor/rules/leadership-takeover.mdc",
    "control_plane/ceo_boot_packet.py",
)

STALL_RE = re.compile(
    r"(?i)("
    r"held for a separate owner|"
    r"under separate owner|"
    r"awaiting owner(?: acceptance)?|"
    r"\bowner session\b|"
    r"wait for (?:an |the )?owner|"
    r"owner must act|"
    r"owner must accept|"
    r"\bowner acceptance\b|"
    r"do not claim custody"
    r")"
)
NEGATION_RE = re.compile(
    r"(?i)\b(?:never|do not|does not|don't|must not|rather than|not a command)\b"
)
TEXT_SUFFIXES = {".md", ".mdc", ".yml", ".yaml", ".toml", ".txt", ".py"}


def has_takeover_clause(text: str) -> bool:
    return all(marker in text for marker in CLAUSE_MARKERS)


def stall_violations(text: str) -> list[str]:
    """Return stall lines that are neither negated nor covered by the clause."""
    if has_takeover_clause(text):
        return []
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = STALL_RE.search(line)
        if match is None:
            continue
        prefix = line[: match.start()]
        if NEGATION_RE.search(prefix) or NEGATION_RE.search(line):
            continue
        found.append(f"{number}: {line.strip()}")
    return found


def _iter_instruction_files():
    for rel in SCAN_ROOTS:
        path = ROOT / rel
        if path.is_file():
            yield path
            continue
        if not path.is_dir():
            continue
        for child in path.rglob("*"):
            if child.is_file() and child.suffix.lower() in TEXT_SUFFIXES:
                yield child


def test_wait_for_owner_without_clause_fails():
    assert stall_violations("This lane is awaiting owner acceptance.")


def test_same_gate_with_clause_passes():
    text = (
        "This lane is awaiting owner acceptance.\n"
        "Ownership is a role, not a session: never wait on an absent/orphaned owner "
        "or ask the Chairman to find old chats. The current session assumes leadership, "
        "records the takeover in the source-linked handoff, and proceeds. Independent "
        "review is still required; never self-merge or approve."
    )
    assert stall_violations(text) == []


def test_negated_owner_must_act_is_not_a_gate():
    assert stall_violations('do not end with an unbound "owner must act".') == []


def test_instruction_surfaces_do_not_wait_for_a_named_owner():
    violations: list[str] = []
    for path in _iter_instruction_files():
        text = path.read_text(encoding="utf-8")
        for line in stall_violations(text):
            violations.append(f"{path.relative_to(ROOT)}: {line}")
    assert violations == []


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_entrypoint_carries_the_combined_leadership_clause(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert has_takeover_clause(text), rel


def test_compact_project_instruction_stays_within_budget_and_keeps_both_contracts():
    source = (ROOT / "docs/sol_skills/BOOTSTRAP_KERNEL.md").read_text(encoding="utf-8")
    kernel = source.split("```text\n", 1)[1].split("```", 1)[0]
    assert len(kernel) <= 8000
    assert "bootstrap_revision = 2026.10.24.1" in kernel
    for phrase in (
        "Ownership is a role, not a session",
        "assumes leadership",
        "records the takeover",
        "ask the Chairman to find old chats",
        "never self-merge or approve",
        "HANDOFF_SOURCE_LINK_V1",
        "Explicit safety denial ends that action",
        "cross-tool or cross-account retries",
        "versioned GitHub plan, Agent OS link, verified first save",
        "Never delegate a denied effect",
        "system names are not live approvers",
        "actual missing evidence",
        "Handoffs name an executable successor action",
    ):
        assert phrase in kernel, phrase
    outside = source.split("```", 2)[-1]
    assert "Cross-account rollout proof" in outside
    assert "fresh-chat" in outside
