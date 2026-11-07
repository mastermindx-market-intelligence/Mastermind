"""Corpus module: imports the consumer, giving find_references a third hop.

Deliberately NOT named ``test_*.py``. The repository gate discovers with
``rglob("test_*.py")`` and passes each hit to pytest explicitly, and pytest's
ignore contract does not apply to explicitly-passed paths — so a conftest hook
cannot keep corpus data out of the repository suite. The name is the guard.
"""

from __future__ import annotations

from sample.consumer import consume


def test_consume_returns_live() -> None:
    assert consume() == "live"
