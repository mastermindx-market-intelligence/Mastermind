#!/usr/bin/env python3
"""Offline Cursor CLI stream-json evidence classifier.

A CLI process exit of 0, a Task tool call or Plan-mode interaction cannot prove
subagent START, an actual billed child model, plan completion, Fabric execution,
or authoritative acceptance. This parser creates no events or lifecycle store.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import stat
from typing import Iterable

MAX_TRACE_BYTES = 4 * 1024 * 1024
MAX_LINES = 10000
KNOWN = frozenset(("system", "user", "thinking", "assistant", "result", "tool_call", "interaction_query"))


class TraceRefused(ValueError):
    pass


def inspect_lines(lines: Iterable[str]) -> dict[str, object]:
    types: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    lines_seen = invalid_lines = terminal = task_denials = 0
    task_started = task_completed = plan_started = plan_completed = 0
    interactive_queries = 0
    terminal_success = False
    for line in lines:
        lines_seen += 1
        if lines_seen > MAX_LINES:
            raise TraceRefused("trace line budget exceeded")
        if len(line) > MAX_TRACE_BYTES:
            raise TraceRefused("single event exceeds trace budget")
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, UnicodeError, TypeError):
            invalid_lines += 1
            continue
        if not isinstance(event, dict):
            invalid_lines += 1
            continue
        kind = event.get("type")
        if kind not in KNOWN:
            # Do not promote arbitrary event types to execution receipts.
            invalid_lines += 1
            continue
        types[kind] += 1
        if kind == "interaction_query":
            interactive_queries += 1
        if kind == "result":
            terminal += 1
            terminal_success |= event.get("subtype") == "success" and event.get("is_error") is False
        if kind == "tool_call":
            t = event.get("tool_call") or {}
            if not isinstance(t, dict):
                invalid_lines += 1
                continue
            kinds = [k for k in t if k.endswith("ToolCall") and len(k) < 80]
            for name in kinds:
                tools[name] += 1
                if name == "taskToolCall":
                    if event.get("subtype") == "started":
                        task_started += 1
                    if event.get("subtype") == "completed":
                        task_completed += 1
                        detail = t.get(name)
                        if isinstance(detail, dict):
                            result = detail.get("result")
                            if isinstance(result, dict) and (
                                "error" in result or result.get("isError") is True
                            ):
                                task_denials += 1
                if name == "createPlanToolCall":
                    if event.get("subtype") == "started":
                        plan_started += 1
                    if event.get("subtype") == "completed":
                        plan_completed += 1
    if task_denials:
        state = "NATIVE_TASK_TOOL_REFUSED"
    elif interactive_queries:
        state = "INTERACTION_REQUIRED_NO_ACCEPTED_PLAN"
    elif task_started or task_completed:
        state = "NATIVE_TASK_CALL_OBSERVED_NOT_CHILD_START"
    elif terminal_success:
        state = "ROOT_RESPONSE_SUCCEEDED_NOT_DELIVERY_PROOF"
    else:
        state = "NO_ACCEPTED_TERMINAL_RESULT"
    return {
        "schema": "mastermind.cursor_trace_evidence.v1",
        "state": state,
        "event_types": dict(sorted(types.items())),
        "tool_names": sorted(tools),
        "invalid_or_unrecognized_lines": invalid_lines,
        "terminal_result_events": terminal,
        "terminal_process_success_observed": terminal_success,
        "interaction_queries": interactive_queries,
        "native_task_call_started": task_started,
        "native_task_call_completed": task_completed,
        "native_task_refusals": task_denials,
        "create_plan_started": plan_started,
        "create_plan_completed": plan_completed,
        "actual_child_model_proven": False,
        "native_child_start_proven": False,
        "fabric_admission_proven": False,
        "plan_accepted_proven": False,
        "authoritative_acceptance_proven": False,
    }


def inspect_file(path: Path) -> dict[str, object]:
    if path.is_symlink():
        raise TraceRefused("refuse trace symlink")
    try:
        info = path.lstat()
    except OSError as exc:
        raise TraceRefused("trace not available") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TRACE_BYTES:
        raise TraceRefused("trace must be bounded regular file")
    try:
        with path.open(encoding="utf-8", errors="strict") as source:
            return inspect_lines(source)
    except (OSError, UnicodeError) as exc:
        raise TraceRefused("trace unavailable or invalid utf8") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect_file(args.trace)
    except TraceRefused as exc:
        print(json.dumps({"schema": "mastermind.cursor_trace_evidence.v1",
                          "state": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
