"""Guard: EXECUTIVE_TEAM_CONTEXT.md prose enumeration must match the catalog.

The doc's seat enumeration is the only charter surface with no runtime
consumer; without this test it drifts silently (found live 2026-11-08).
"""
import re
from pathlib import Path

from integrations.hermes_leadership import CHARTER_KEYS

_DOC = Path(__file__).resolve().parents[1] / "docs/hermes/EXECUTIVE_TEAM_CONTEXT.md"
_WORDS = {w: n for n, w in enumerate(
    ["one", "two", "three", "four", "five", "six", "seven", "eight",
     "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
     "sixteen", "seventeen", "eighteen", "nineteen", "twenty"], start=1)}


def test_doc_charter_enumeration_count_matches_catalog():
    text = _DOC.read_text(encoding="utf-8")
    match = re.search(r"[Tt]he (\w+) existing charter keys", text)
    assert match is not None, "enumeration sentence missing from doc"
    assert _WORDS[match.group(1)] == len(CHARTER_KEYS), (
        f"doc says {match.group(1)} charter keys, catalog has {len(CHARTER_KEYS)}")
