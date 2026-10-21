#!/usr/bin/env python3
"""Inspect, qualify, or renew installed Mastermind Workbench Action bindings."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def _source_root() -> str:
    return str(Path(__file__).resolve().parents[1])


def _module():
    root = _source_root()
    if not sys.path or sys.path[0] != root:
        sys.path.insert(0, root)
    from integrations.workbench_action_mcp import fleet_ops

    return fleet_ops


def _entry(value: str) -> tuple[str, str]:
    alias, sep, path = value.partition("=")
    if not sep or not alias or not path or not path.startswith("/"):
        raise argparse.ArgumentTypeError("entry must be ALIAS=/absolute/config.json")
    return alias, path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", allow_abbrev=False)
    doctor.add_argument(
        "--entry",
        action="append",
        type=_entry,
        required=True,
        help="repeatable ALIAS=/absolute/config.json",
    )
    doctor.add_argument("--expected-source-sha")
    doctor.add_argument("--warn-before-days", type=int, default=7)

    qualify = sub.add_parser("qualify", allow_abbrev=False)
    qualify.add_argument("--alias", required=True)
    qualify.add_argument("--config", required=True)
    qualify.add_argument("--expected-source-sha")

    renew = sub.add_parser("renew", allow_abbrev=False)
    renew.add_argument("--alias", required=True)
    renew.add_argument("--config", required=True)
    renew.add_argument("--expected-source-sha")
    renew.add_argument("--extend-days", type=int, default=30)
    return parser


def _emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    ops = _module()
    try:
        if args.command == "doctor":
            if args.warn_before_days < 1:
                raise ops.FleetOperationError("CONFIGURATION_REFUSED")
            rows = []
            for alias, config in args.entry:
                receipt = ops.doctor(
                    alias=alias,
                    config_path=config,
                    expected_source_sha=args.expected_source_sha,
                    warn_before_ms=args.warn_before_days * 24 * 60 * 60 * 1000,
                )
                rows.append(dataclasses.asdict(receipt))
            state = "READY"
            if any(row["state"] != "READY" for row in rows):
                state = "RENEW_SOON"
            _emit(
                {
                    "schema": "mastermind.workbench_fleet_doctor.v1",
                    "state": state,
                    "count": len(rows),
                    "rows": rows,
                    "tool_contract": list(ops.FINAL_TOOL_NAMES),
                    "modifying_tools": list(ops.MODIFYING_TOOL_NAMES),
                }
            )
            return 0 if state == "READY" else 3

        if args.command == "qualify":
            receipt = ops.qualify(
                alias=args.alias,
                config_path=args.config,
                expected_source_sha=args.expected_source_sha,
            )
            _emit(
                {
                    "schema": "mastermind.workbench_fleet_qualification.v1",
                    "state": "READY",
                    "receipt": dataclasses.asdict(receipt),
                }
            )
            return 0

        if args.extend_days < 1 or args.extend_days > 365:
            raise ops.FleetOperationError("LEASE_RENEWAL_REFUSED")
        receipt = ops.renew(
            alias=args.alias,
            config_path=args.config,
            extend_ms=args.extend_days * 24 * 60 * 60 * 1000,
            expected_source_sha=args.expected_source_sha,
        )
        _emit(
            {
                "schema": "mastermind.workbench_fleet_renewal.v1",
                "state": "READY",
                "receipt": dataclasses.asdict(receipt),
            }
        )
        return 0
    except ops.FleetOperationError as error:
        _emit(
            {
                "schema": "mastermind.workbench_fleet_operator_error.v1",
                "state": "REFUSED",
                "code": error.code,
            }
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
