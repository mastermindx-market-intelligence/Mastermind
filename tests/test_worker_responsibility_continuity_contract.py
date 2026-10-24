"""Source-law regression: Codex and Claude share one anti-deferral contract.

This is deliberately a read-only test. It grants no runtime, writer, lease,
permission, or succession authority.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- MMX_RESPONSIBILITY_CONTINUITY_BEGIN -->"
END = "<!-- MMX_RESPONSIBILITY_CONTINUITY_END -->"

REQUIRED_PHRASES = (
    "A component, service, repository, team, role, provider account, browser tab, or historical session is not a live assignee.",
    "Within an assigned nonterminal job, the current session retains responsibility for the next step",
    "Before deferring because a capability is unavailable, inspect the actual current tool/connector/host surface once",
    "Tool access is capability, not modification authority.",
    'Saying "I take ownership" does not create action-target or source-writer authority.',
    "If another exact live action target or source writer is proven current, continue that target; do not steal the write.",
    'Do not end at "the owner should do it" without an actual handoff or typed gate.',
)

REQUIRED_TOKENS = (
    "WAITING_CAPACITY",
    "PRESTART_REBIND",
    "RUNTIME_BINDING_RECONCILIATION_REQUIRED",
    "EFFECT_UNKNOWN",
    "Chairman/admin gate",
)


def _extract_contract(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise AssertionError(f"{path.name} must contain exactly one responsibility-continuity block")
    _, tail = text.split(BEGIN, 1)
    body, _ = tail.split(END, 1)
    return body.strip("\n")


class WorkerResponsibilityContinuityContractTests(unittest.TestCase):
    def test_worker_bootstraps_share_one_identical_contract(self) -> None:
        agents = _extract_contract(ROOT / "AGENTS.md")
        claude = _extract_contract(ROOT / "CLAUDE.md")
        self.assertEqual(agents, claude)

    def test_contract_forbids_imaginary_owner_deferral_and_self_promotion(self) -> None:
        contract = _extract_contract(ROOT / "AGENTS.md")
        for phrase in REQUIRED_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contract)

    def test_contract_preserves_closed_wait_reconcile_and_human_gates(self) -> None:
        contract = _extract_contract(ROOT / "AGENTS.md")
        for token in REQUIRED_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, contract)
        self.assertIn("no receiver assignment edge", contract)
        self.assertIn("exact live action target", contract)
        self.assertIn("this session is already authorized and capable", contract)

    def test_no_authority_promotion_or_unbound_ghost_handoff(self) -> None:
        contract = _extract_contract(ROOT / "AGENTS.md")
        self.assertIn("never invent an assignee", contract)
        self.assertIn("it never grants this session automatic modifying authority", contract)
        self.assertIn("Perform the required delivery/continuation edge", contract)


if __name__ == "__main__":
    unittest.main()
