"""Tiny stdio fixture for the private raw-turn transport containment tests."""
from __future__ import annotations

import json
import os
import sys

SECRET = "sk-raw-turn-fixture-ABCDEFGHIJKLMNOPQRSTUVWXYZ"

for raw in sys.stdin.buffer:
    request = json.loads(raw)
    request_id = request.get("id")
    mode = os.environ.get("OHF_RAW_FIXTURE_MODE", "normal")
    if mode == "invalid_utf8":
        sys.stdout.buffer.write(b"\xff\xfe\n")
        sys.stdout.buffer.flush()
        continue
    if mode == "malformed":
        sys.stdout.buffer.write(b"{not-json\n")
        sys.stdout.buffer.flush()
        continue
    if mode == "oversized":
        response = {"id": request_id, "result": {"padding": "x" * 4096}}
    else:
        response = {
            "id": request_id,
            "result": {
                "data": [
                    {
                        "id": "TURN-RAW",
                        "items": [
                            {
                                "type": "agent_message",
                                "phase": "final_answer",
                                "text": SECRET,
                            }
                        ],
                    }
                ],
                "nextCursor": None,
            },
        }
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    sys.stdout.flush()
