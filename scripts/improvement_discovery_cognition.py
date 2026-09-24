#!/usr/bin/env python3
"""Generate one private advisory improvement-proposal draft pass.

The input is an existing improvement-discovery report. Output is JSON on stdout.
Nothing is persisted and this command grants no strategic or execution authority.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Sequence

from brain import improvement_discovery_cognition as cognition


def _invalid() -> dict:
    return {
        "schema": cognition.OUTPUT_SCHEMA,
        "state": "UNAVAILABLE",
        "reason_code": "INPUT_INVALID",
        "source_report_digest": None,
        "proposals": [],
        "hold_reason": None,
        "selected_proposal": None,
        "advisory_only": True,
        "independent_usefulness_proven": False,
        "strategic_options_created": 0,
        "execution_authority_granted": False,
        "jobs_created": 0,
        "persisted": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate private evidence-bound advisory improvement proposals."
    )
    parser.add_argument("report", help="Path to one improvement-discovery report JSON")
    args = parser.parse_args(argv)
    try:
        report = cognition.load_report(args.report)
    except Exception:
        print(json.dumps(_invalid(), sort_keys=True))
        return 2
    result = asyncio.run(cognition.generate(report))
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0 if result.get("state") == "AVAILABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
