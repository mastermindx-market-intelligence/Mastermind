#!/usr/bin/env python3
"""Read one published Workspace Agent run, or decode an owner-supplied response.

This does not publish, trigger, retry, cancel, accept work, or grant authority.
No provider token is needed for --describe or --decode-trigger/--decode-run.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from integrations.workspace_agent_api import (  # noqa: E402
    InvalidObservation, MAX_BODY_BYTES, decode_run, decode_trigger, read_run_once,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--describe", action="store_true")
    group.add_argument("--decode-trigger", action="store_true", help="Response body from stdin; no network")
    group.add_argument("--decode-run", action="store_true", help="Response body from stdin; no network")
    group.add_argument("--read-run", action="store_true", help="One read-only GET; no loop or trigger")
    parser.add_argument("--channel")
    parser.add_argument("--run")
    parser.add_argument("--http-status", type=int)
    parser.add_argument("--expected-conversation-url")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    if args.describe:
        result = {
            "capability_state": "BUILT_NOT_PROVEN",
            "operations": ["decode_trigger_response", "decode_run_response", "read_run_once"],
            "network_methods": ["GET"], "network_host": "api.chatgpt.com",
            "can_trigger": False, "can_retrieve_answer": False,
            "can_ack_wake": False, "can_accept_company_work": False,
            "registered_with_executive": False,
        }
    else:
        try:
            if args.decode_trigger:
                if args.http_status is None:
                    raise InvalidObservation("HTTP_STATUS_REQUIRED")
                body = sys.stdin.buffer.read(MAX_BODY_BYTES + 1)
                result = asdict(decode_trigger(args.http_status, body))
            else:
                if not args.channel or not args.run:
                    raise InvalidObservation("CHANNEL_AND_RUN_REQUIRED")
                if args.read_run:
                    token = os.environ.get("WORKSPACE_AGENT_ACCESS_TOKEN", "")
                    if not token:
                        raise InvalidObservation("WORKSPACE_AGENT_ACCESS_TOKEN_MISSING")
                    result = read_run_once(channel_id=args.channel, run_id=args.run, token=token,
                                           timeout_seconds=args.timeout,
                                           expected_conversation_url=args.expected_conversation_url).to_dict()
                else:
                    if args.http_status is None:
                        raise InvalidObservation("HTTP_STATUS_REQUIRED")
                    body = sys.stdin.buffer.read(MAX_BODY_BYTES + 1)
                    result = decode_run(args.http_status, body, channel_id=args.channel,
                                        run_id=args.run, observed_at=int(time.time()),
                                        expected_conversation_url=args.expected_conversation_url).to_dict()
        except InvalidObservation as exc:
            print(json.dumps({"available": False, "reason": str(exc)}, sort_keys=True))
            return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    # Accepted-but-uncorrelated trigger is not an instruction to repeat it.
    return 3 if result.get("available") is False or result.get("disposition") == "unknown" else 0


if __name__ == "__main__":
    raise SystemExit(main())
