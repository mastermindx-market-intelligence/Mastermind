from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


class HermesSkillFormat(unittest.TestCase):
    def test_each_skill_is_hermes_shaped_and_keeps_its_source(self):
        expected = {
            "chatgpt-browser-session-operator",
            "mastermind-context",
            "mastermind-fabric-secretary-local",
        }
        found = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(found, expected)
        for name in expected:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            description = re.search(r"^description: (.*)$", text, re.M)
            self.assertIsNotNone(description)
            sentence = description.group(1)
            self.assertLessEqual(len(sentence), 60)
            self.assertTrue(sentence.endswith("."))
            self.assertIn(f"name: {name}", text)
            self.assertIn("metadata:", text)
            self.assertIn("hermes:", text)
            self.assertIn("platforms:", text)
            source = SKILLS / name / "references" / "grok-secretary-source.md"
            self.assertGreater(source.stat().st_size, 1000)
            self.assertNotIn("xoxb-", text)
        browser = (SKILLS / "chatgpt-browser-session-operator" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Allow <tool> for this conversation", browser)
        self.assertIn("Always allow", browser)
        self.assertIn("verbatim", browser.lower())
        fabric = (SKILLS / "mastermind-fabric-secretary-local" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("once", fabric)
        self.assertIn("does not execute", fabric)


if __name__ == "__main__":
    unittest.main()
