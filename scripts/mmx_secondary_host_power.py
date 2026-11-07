#!/usr/bin/env python3
"""Non-root ceremony client for the fixed secondary-host power action."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

_RELEASE_ROOT = Path(__file__).resolve().parents[1]
if str(_RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(_RELEASE_ROOT))

from control_plane.executive_privileged_action import REQUEST_SCHEMA, validate_request
from control_plane.executive_privileged_broker import BrokerTrustError
from scripts import mmx_admin

ACTION = "executive.host.prepare_secondary_power_policy"


def build_request(argv: Sequence[str]) -> dict[str, object]:
    parser = argparse.ArgumentParser(
        description="Apply the reviewed secondary-host charger power policy"
    )
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args(list(argv))
    return validate_request(
        {
            "schema": REQUEST_SCHEMA,
            "request_id": args.request_id,
            "action": ACTION,
            "args": {},
        }
    ).to_dict()


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    request = build_request(values)
    sys.stderr.write(f"mmx-secondary-host-power request_id={request['request_id']}\n")
    sys.stderr.flush()
    try:
        response = mmx_admin.send_request(
            request,
            socket_path=mmx_admin.DEFAULT_SOCKET,
        )
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"mmx-secondary-host-power transport failure: {exc}\n")
        return 69
    try:
        exit_code = mmx_admin._effect_exit_code(response, request)
    except (BrokerTrustError, RuntimeError) as exc:
        sys.stderr.write(
            f"mmx-secondary-host-power response refused or invalid: {exc}\n"
        )
        return 1
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
