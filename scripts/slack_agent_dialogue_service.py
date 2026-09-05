#!/usr/bin/env python3
"""Private long-running Agent Relay entrypoint."""
import sys
from pathlib import Path


# launchd uses Python isolated mode, which intentionally omits the script's
# parent from sys.path. Bind imports to this reviewed release tree explicitly.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integrations.slack_agent_dialogue.runtime import main


if __name__ == "__main__":
    raise SystemExit(main())
