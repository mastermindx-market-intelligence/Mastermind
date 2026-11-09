"""Enforce the common reuse-first instruction entrypoints without new runtime policy."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = "docs/REUSE_FIRST_ENGINEERING.md"


class ReuseFirstInstructionsTest(unittest.TestCase):
    def test_policy_and_entrypoints(self):
        policy = (ROOT / POLICY).read_text(encoding="utf-8")
        for term in ("maintained", "adapter", "incumbent", "quant", "consumer"):
            self.assertIn(term, policy.lower())
        for path in (
            "AGENTS.md",
            "CLAUDE.md",
            "docs/NATIVE_EXECUTION_BRIEF.md",
            "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md",
            "docs/sol_skills/INDEX.md",
            "docs/sol_skills/ACTIVE_EXECUTION.md",
            "docs/sol_skills/BOOTSTRAP_KERNEL.md",
            "skills/mastermind-worker-bootstrap/SKILL.md",
            ".cursor/rules/reuse-first.mdc",
        ):
            with self.subTest(path=path):
                self.assertIn(POLICY, (ROOT / path).read_text(encoding="utf-8"))

    def test_project_kernel_export_and_budget(self):
        source = (ROOT / "docs/sol_skills/BOOTSTRAP_KERNEL.md").read_text(encoding="utf-8")
        block = re.search(r"```text\n(.*?)\n```", source, re.DOTALL)
        self.assertIsNotNone(block)
        exported = block.group(1) + "\n"
        self.assertLessEqual(len(exported.encode("utf-8")), 8000)
        self.assertEqual(
            exported,
            (ROOT / "docs/evidence/2026-11-07-reuse-first-project-instructions.txt").read_text(encoding="utf-8"),
        )
        self.assertIn("REUSE FIRST", exported)


if __name__ == "__main__":
    unittest.main()
