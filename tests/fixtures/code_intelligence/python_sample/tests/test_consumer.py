"""Corpus test: imports the consumer, giving find_references a third hop."""

from __future__ import annotations

from sample.consumer import consume


def test_consume_returns_live() -> None:
    assert consume() == "live"
