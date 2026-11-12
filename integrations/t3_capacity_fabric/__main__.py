"""CLI: python -m integrations.t3_capacity_fabric {status,plan,apply,verify}."""
from __future__ import annotations

import argparse
import json
import sys

from integrations.t3_capacity_fabric.endpoints import default_endpoints
from integrations.t3_capacity_fabric.registration import (
    apply_registration,
    plan_registration,
    verify_registration,
)


def _report(reports) -> dict:
    return [
        {
            "endpoint": r.endpoint_id,
            "instance": r.instance_id,
            "base_url": r.base_url,
            "healthy": r.health["ok"],
            "models": list(r.models),
            "changed": r.changed,
            "refusal": r.refusal,
        }
        for r in reports
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="t3_capacity_fabric")
    parser.add_argument("command", choices=["status", "plan", "apply", "verify"])
    args = parser.parse_args(argv)
    endpoints = default_endpoints()
    if args.command == "status":
        reports = verify_registration(endpoints)
        ok = all(r.health["ok"] for r in reports)
    elif args.command == "plan":
        reports = plan_registration(endpoints)
        ok = all(r.refusal is None for r in reports)
    elif args.command == "apply":
        reports = apply_registration(endpoints)
        ok = all(r.refusal is None for r in reports)
    else:
        reports = verify_registration(endpoints)
        ok = all(r.health["ok"] and r.refusal is None for r in reports)
    print(json.dumps(_report(reports), indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
