#!/usr/bin/env python3
"""Verify one Slack bot identity/scope receipt without exposing its token."""
import sys
from pathlib import Path

# Direct operator invocation places ``scripts/`` rather than the repository
# root on sys.path. Resolve the invoked wrapper path and bootstrap only that
# parent before importing the existing credential-safe verifier.
_REPO_ROOT = Path(sys.argv[0]).resolve().parents[1]
_repo_root = str(_REPO_ROOT)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from integrations.slack_agent_dialogue.metadata_verifier import main


if __name__ == "__main__":
    raise SystemExit(main())
