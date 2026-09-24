#!/usr/bin/env python3
"""EVAL-R0 CLI entry point. See ``scripts/agent_eval/cli.py`` for commands.

Truthful capability state: BUILT_NOT_PROVEN / PRODUCTION_INERT. This tool
proves SHAPE_VALID and EVALUATION_GRAPH_VERIFIED only; it never claims
EVIDENCE_CONTENT_VERIFIED and never produces a runner pass/fail, winner,
route, policy, approval, acceptance, or production action.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.agent_eval.cli import main  # noqa: E402  (path bootstrap must run first)

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
