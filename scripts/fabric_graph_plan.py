"""Foreground planner/evaluation consumer. Prints advice; never submits work."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from control_plane.fabric_graph_planning import METHODS, analyze_plan
from control_plane.executive_coo_policy import CooCyclePolicyError
from control_plane.executive_orchestration_result import MAX_CANONICAL_RESULT_BYTES


def _read_plan(path: str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ValueError("nonfinite JSON number")

    with Path(path).open("rb") as source:
        raw = source.read(MAX_CANONICAL_RESULT_BYTES + 1)
    if len(raw) > MAX_CANONICAL_RESULT_BYTES:
        raise ValueError("candidate exceeds incumbent byte limit")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="list optional graph composition methods")
    plan = commands.add_parser("plan", help="compose and analyze an existing ExecutionPlan candidate")
    plan.add_argument("document")
    plan.add_argument("--root-job-id", required=True)
    plan.add_argument("--plan-attempt-id", required=True)
    plan.add_argument("--method", choices=METHODS, default="custom")
    plan.add_argument("--coordinator-depth", type=int)
    plan.add_argument("--descendant-limit", type=int)
    plan.add_argument("--max-depth", type=int)
    resources = commands.add_parser("resources", help="summarize observed resources from an existing EVAL store")
    resources.add_argument("--root", required=True)
    resources.add_argument("--experiment-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = {"methods": METHODS, "admission_state": "NOT_REQUESTED"}
            code = 0
        elif args.command == "plan":
            result = analyze_plan(_read_plan(args.document), expected_root_job_id=args.root_job_id,
                                  expected_plan_attempt_id=args.plan_attempt_id, method=args.method,
                                  coordinator_depth=args.coordinator_depth,
                                  descendant_limit=args.descendant_limit, max_depth=args.max_depth)
            code = 0 if result["static_status"] == "COMPATIBLE" else 1
        else:
            from scripts.agent_eval.resource_summary import summarize_resources
            result = summarize_resources(args.root, args.experiment_id)
            code = 0
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return code
    except (ValueError, OSError, RecursionError, CooCyclePolicyError) as exc:
        # Keep output bounded and omit attacker-controlled input from diagnostics.
        print(json.dumps({"status": "INVALID_INPUT", "error_type": type(exc).__name__,
                          "admission_state": "NOT_REQUESTED", "runtime_changed": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
