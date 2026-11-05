"""H1 — the deterministic one-cockpit receipt validator package.

This package validates evidence only. It performs no Business account,
workspace, app, plugin, OAuth, credential, Executive, RuntimeBinding,
Agent-OS, Slack, Linear, or deployment action of any kind, and it never
reads the process clock, the environment, the filesystem (beyond its own
source), the network, or a random source. See ``evidence.py`` for the full
contract and ``docs/runbooks/business-sol-one-cockpit-evidence.md`` for the
operator-facing runbook.
"""

from __future__ import annotations

from .evidence import (
    EXPECTED_A1_COMMIT,
    EXPECTED_P1_COMMIT,
    INPUT_SCHEMA_ID,
    OUTPUT_SCHEMA_ID,
    VERDICTS,
    Issue,
    canonical_input_digest,
    canonical_json,
    validate_receipt,
)

__all__ = [
    "EXPECTED_A1_COMMIT",
    "EXPECTED_P1_COMMIT",
    "INPUT_SCHEMA_ID",
    "OUTPUT_SCHEMA_ID",
    "VERDICTS",
    "Issue",
    "canonical_input_digest",
    "canonical_json",
    "validate_receipt",
]
