"""EVAL-R0: Mastermind-native agent-evaluation evidence core.

Production-inert per the accepted architecture and implementation plan:

- docs/superpowers/specs/2026-08-31-agent-evaluation-fabric-design.md
- docs/superpowers/plans/2026-08-31-agent-evaluation-r0.md
- docs/superpowers/specs/2026-09-01-agent-evaluation-r0-environment-free-secret-safety-amendment.md

This package implements only ``SHAPE_VALID`` and ``EVALUATION_GRAPH_VERIFIED``.
It never claims ``EVIDENCE_CONTENT_VERIFIED``, never asserts a runner
pass/fail, winner, route, policy, approval, acceptance, or production action,
and performs no network, process, environment, or credential read.

This module intentionally imports no submodule at package-init time so that
importing ``scripts.agent_eval`` alone never triggers any submodule's own
import-time behavior.
"""
from __future__ import annotations

#: Truthful post-wave capability state (see the plan's stated outcome).
CAPABILITY_STATE = "BUILT_NOT_PROVEN / PRODUCTION_INERT"

#: Exact canonical artifact size bound (design/plan §5.7, binding 2026-09-01).
MAX_CANONICAL_ARTIFACT_BYTES = 4 * 1024 * 1024
