#!/usr/bin/env python3
"""Verify one Slack bot identity/scope receipt without exposing its token."""
from integrations.slack_agent_dialogue.metadata_verifier import main


if __name__ == "__main__":
    raise SystemExit(main())
