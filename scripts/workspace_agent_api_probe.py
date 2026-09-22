#!/usr/bin/env python3
"""Describe Mastermind's accepted Workspace trigger-observation surface.

Current official OpenAI sources disagree on the baseline 202 body shape, and the
developer docs separately expose beta run-status polling. This probe describes
Mastermind's deliberately narrower production contract: trigger acceptance only,
no beta run observation, no answer retrieval, and zero run-status network I/O.
Legacy run-observation flags remain only as fail-closed compatibility surfaces.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from integrations.workspace_agent_api import (  # noqa: E402
    InvalidObservation,
    MAX_BODY_BYTES,
    decode_run,
    decode_trigger,
    read_run_once,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--describe", action="store_true")
    group.add_argument(
        "--decode-trigger",
        action="store_true",
        help="Decode provider HTTP disposition from stdin; no network.",
    )
    group.add_argument(
        "--decode-run",
        action="store_true",
        help="Compatibility flag: run observation is not admitted by Mastermind and performs no network.",
    )
    group.add_argument(
        "--read-run",
        action="store_true",
        help="Compatibility flag: run polling is unsupported and performs no network.",
    )
    parser.add_argument("--channel")
    parser.add_argument("--run")
    parser.add_argument("--http-status", type=int)
    parser.add_argument("--expected-conversation-url")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    if args.describe:
        result = {
            "capability_state": "BUILT_NOT_PROVEN",
            "operations": [
                "decode_trigger_acceptance",
                "run_observation_not_admitted",
            ],
            "network_methods": [],
            "network_host": None,
            "success_body_consumed": False,
            "beta_run_observation_admitted": False,
            "can_trigger": False,
            "can_retrieve_answer": False,
            "can_ack_wake": False,
            "can_accept_company_work": False,
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
                    result = read_run_once(
                        channel_id=args.channel,
                        run_id=args.run,
                        timeout_seconds=args.timeout,
                    ).to_dict()
                else:
                    if args.http_status is None:
                        raise InvalidObservation("HTTP_STATUS_REQUIRED")
                    body = sys.stdin.buffer.read(MAX_BODY_BYTES + 1)
                    result = decode_run(
                        args.http_status,
                        body,
                        channel_id=args.channel,
                        run_id=args.run,
                        observed_at=int(time.time()),
                        expected_conversation_url=args.expected_conversation_url,
                    ).to_dict()
        except InvalidObservation as exc:
            print(json.dumps({"available": False, "reason": str(exc)}, sort_keys=True))
            return 2

    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 3 if result.get("available") is False or result.get("disposition") == "unknown" else 0


if __name__ == "__main__":
    raise SystemExit(main())
