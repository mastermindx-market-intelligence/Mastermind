#!/usr/bin/env python3
"""One-shot client for the local Active-Session Dialogue AF_UNIX service."""
from integrations.slack_agent_dialogue.service import client_main


if __name__ == "__main__":
    raise SystemExit(client_main())
