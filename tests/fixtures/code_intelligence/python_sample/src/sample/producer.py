"""Producer corpus: one protocol, one live implementation, one dead sibling.

The dead sibling is deliberately near-identical to the live implementation so
that a name-only text search cannot distinguish them. Only a semantic backend
that understands imports and types can tell which one the consumer actually
uses.
"""

from __future__ import annotations

from typing import Protocol


class Producer(Protocol):
    """The interface the consumer depends on."""

    def produce(self) -> str: ...


class LiveProducer:
    """The implementation that is actually reachable from the consumer."""

    def produce(self) -> str:
        return "live"


class DeadProducer:
    """Deliberately similar dead sibling. Never imported by the consumer."""

    def produce(self) -> str:
        return "dead"


def make_producer() -> Producer:
    """Live wrapper — the only construction path the consumer imports."""
    return LiveProducer()


def make_dead_producer() -> Producer:
    """Dead wrapper — unreferenced outside this module."""
    return DeadProducer()
