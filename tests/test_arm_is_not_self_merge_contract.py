"""Bounded source-law regression: arming one's own qualified PR is not self-merge.

Read-only static contract. It grants no runtime, writer, lease, review or
release authority, and it does not approve any specific change.

The instruction entrypoints forbid two things and only two things:

* self-approval -- an author casting the `APPROVED` review on their own PR;
* self-merge    -- merging protected `master` directly, by admin bypass, or
                  around the enforced checks/review/queue path.

They do not forbid the assigned session enrolling its own qualified Ready PR
in the native protected auto-merge / merge queue controller, which
docs/SESSION_LOCAL_REVIEW_POLICY.md and docs/DELIVERY_WORKFLOW.md already
require as the ordinary release path. This module pins that disambiguation so
a later edit cannot silently reintroduce a blanket "no self-arming" reading.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- MMX_RESPONSIBILITY_CONTINUITY_BEGIN -->"
END = "<!-- MMX_RESPONSIBILITY_CONTINUITY_END -->"

FORBIDDEN_PHRASE = "Never self-approve or self-merge."

PERMITTED_CLAUSES = (
    "Self-approve means an author-cast `APPROVED` review",
    "self-merge means a direct or admin-bypassed merge of protected `master`",
    "Enrolling one's own qualified Ready PR in native auto-merge or the merge queue",
    "is the permitted normal release path, not self-merging",
)


def _extract_contract(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise AssertionError(f"{path.name}: expected exactly one continuity block")
    _, tail = text.split(BEGIN, 1)
    body, _ = tail.split(END, 1)
    return body.strip("\n")


class ArmIsNotSelfMergeContractTests(unittest.TestCase):
    def test_entrypoint_blocks_remain_identical(self) -> None:
        self.assertEqual(
            _extract_contract(ROOT / "AGENTS.md"),
            _extract_contract(ROOT / "CLAUDE.md"),
        )

    def test_both_entrypoints_keep_the_blanket_forbiddance_verbatim(self) -> None:
        for name in ("AGENTS.md", "CLAUDE.md"):
            with self.subTest(f=name):
                self.assertIn(FORBIDDEN_PHRASE, _extract_contract(ROOT / name))

    def test_both_entrypoints_keep_the_ordinary_release_clarification(self) -> None:
        for name in ("AGENTS.md", "CLAUDE.md"):
            contract = " ".join(_extract_contract(ROOT / name).split())
            for clause in PERMITTED_CLAUSES:
                with self.subTest(f=name, clause=clause):
                    self.assertIn(clause, contract)

    def test_clarification_does_not_authorize_direct_protected_merge(self) -> None:
        for name in ("AGENTS.md", "CLAUDE.md"):
            contract = _extract_contract(ROOT / name).lower()
            self.assertIn("never push directly to protected", contract)
            self.assertIn("never self-approve", contract)


if __name__ == "__main__":
    unittest.main()
