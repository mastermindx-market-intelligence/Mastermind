"""Closed identifiers from the 2026-10-25 Grok Secretary teaching snapshot.

Chris's Slack user id and the Dot bot user ids were not in that snapshot.
They are not guessed here.
"""

from __future__ import annotations

SECRETARY_USER_ID = "U0BTCHX8HMF"

KNOWN_AUTHORS = {
    "U0BRETDUAS2": "ChatGPT1",
    "U0BSB73JWNL": "ChatGPT2",
    "U0BR1GQH7SB": "ChatGPT3/Sol",
    "U0C59APBUN4": "Ryan",
}

CHANNELS = {
    "C0BSBM78V1N": "agent-dispatch",
    "C0BTD5804QK": "mastermind-exec-ops",
    "C0BRDFZPLHK": "ceo-control-room",
    "C0C5FCK1F45": "metaceo",
    "C0CBC6AEAQZ": "dotsandgroksecretary",
    "C0CCNK7JFAL": "chatgpt-web-returns",
}

PING_SCAN_CHANNELS = (
    "C0BSBM78V1N",
    "C0BTD5804QK",
    "C0BRDFZPLHK",
    "C0C5FCK1F45",
    "C0CBC6AEAQZ",
)

# The three rooms the overnight sweep names as the original set.
ORIGINAL_ROOMS = (
    "C0BSBM78V1N",
    "C0BTD5804QK",
    "C0BRDFZPLHK",
)

RETURNS_CHANNEL = "C0CCNK7JFAL"
AGENT_DISPATCH = "C0BSBM78V1N"

SHADOW_SCHEMA = "mastermind.hermes_secretary.shadow_decision.v1"
CATALOG_SCHEMA = "mastermind.hermes_secretary.routine_catalog.v1"
HERMES_PIN = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"

# Single Wake seat these observations may name. Slack text cannot select it.
WAKE_SEAT = "ceo"
