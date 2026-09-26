"""Source-contract checks; no simulated or measured human acceptance is claimed."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def section(text, heading, next_heading):
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


class HumanFirstDesignGuidanceTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_claude_and_agents_share_one_intake_contract(self):
        blocks = [section(self.read(path), "## Human-first product work", "## Executive contract")
                  for path in ("AGENTS.md", "CLAUDE.md")]
        self.assertEqual(blocks[0], blocks[1])
        self.assertIn("docs/DESIGN_DOCTRINE.md", blocks[0])
        self.assertIn("research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md", blocks[0])
        self.assertIn("beyond Paper and beyond Sector Intelligence", blocks[0])

    def test_reading_depth_and_honest_proof_remain_together(self):
        text = self.read("AGENTS.md")
        self.assertIn("3–4-second orientation", text)
        self.assertIn("preserved analytical depth", text)
        self.assertIn("not yet tested", text)
        self.assertIn("(append-only ledger)", text)

    def test_paper_loads_same_owner_without_forking_source_pins(self):
        text = self.read("skills/paper-design-workflow/SKILL.md")
        self.assertIn("docs/DESIGN_DOCTRINE.md", text)
        self.assertIn("separately from the Sol Skillpack", text)
        self.assertIn("A candidate PR is not", text)
        self.assertIn("`APPLIED_RESPONSE_OBSERVED` is not design acceptance", text)

    def test_paper_transport_and_effect_fences_survive(self):
        text = self.read("skills/paper-design-workflow/SKILL.md")
        for phrase in ("INDEPENDENT_RDC_AUTHORIZATION", "A denial is not a fallback invitation",
                       "On `EFFECT_UNKNOWN`", "one designer assigned"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
