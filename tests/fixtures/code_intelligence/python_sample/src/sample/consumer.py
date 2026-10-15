"""Consumer corpus: imports only the live wrapper."""

from __future__ import annotations

from sample.producer import make_producer


def consume() -> str:
    producer = make_producer()
    return producer.produce()


def broken_helper() -> str:
    # Planted, deterministic undefined-name diagnostic. Exactly one per corpus.
    return undefined_symbol_for_diagnostics  # noqa: F821
