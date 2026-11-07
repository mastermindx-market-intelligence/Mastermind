#!/usr/bin/env python3
"""Fail-closed *CLI-observation* classifier for the Hermes toolset registry.

Input must be captured from the actual immutable Hermes CLI as:
  hermes tools list --platform cli
Never claims process isolation, server-side authorization, TCC, app surfaces,
or source attestation from an output string. Does not launch a process or network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from preflight import REQUIRED_DISABLED, _atomic_new_receipt

SCHEMA = "mastermind.hermes_cli_toolset_observation.v1"
UPSTREAM_OBSERVATION_SHA = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TOOL_LINE = re.compile(r"^\s*([✓✗])\s+(enabled|disabled)\s+([a-z][a-z0-9_-]{0,63})(?:\s|$)")
HEADINGS = {"Built-in toolsets (cli):": "builtins", "Plugin toolsets (cli):": "plugins"}
BUILTIN_EXPECTED = REQUIRED_DISABLED - {"a2a"} | {"clarify"}
PLUGIN_EXPECTED = frozenset({"a2a"})


def inspect(text: str, stderr_text: str | None = None) -> dict:
    issues: set[str] = set()
    if stderr_text is None:
        issues.add("STDERR_NOT_OBSERVED")
    elif stderr_text.strip():
        issues.add("RUNTIME_CONFIG_OR_TOOL_WARNING_PRESENT")
    seen: dict[str, dict[str, bool]] = {"builtins": {}, "plugins": {}}
    section: str | None = None
    for raw in ANSI.sub("", text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in HEADINGS:
            section = HEADINGS[line]
            continue
        if section is None:
            issues.add("UNEXPECTED_OUTPUT_PREAMBLE")
            continue
        match = TOOL_LINE.fullmatch(line) or TOOL_LINE.match(line)
        if not match:
            issues.add("UNRECOGNIZED_TOOL_ROW_OR_SECTION")
            continue
        icon, state, name = match.groups()
        if (icon == "✓") != (state == "enabled"):
            issues.add("INCONSISTENT_TOOL_STATUS")
        if name in seen[section]:
            issues.add("DUPLICATE_TOOLSET")
        seen[section][name] = state == "enabled"
        if name not in (BUILTIN_EXPECTED if section == "builtins" else PLUGIN_EXPECTED):
            issues.add("UPSTREAM_TOOLSET_DRIFT")

    for section_name, expected in (("builtins", BUILTIN_EXPECTED), ("plugins", PLUGIN_EXPECTED)):
        if expected - set(seen[section_name]):
            issues.add("INCOMPLETE_TOOLSET_REGISTRY")
    if not seen["builtins"].get("clarify", False):
        issues.add("EXPECTED_CLARIFY_NOT_ENABLED")
    enabled = [(group, name) for group, items in seen.items() for name, active in items.items() if active]
    if enabled != [("builtins", "clarify")]:
        issues.add("EXTRA_ACTUATING_TOOLSET_ENABLED")
    return {
        "schema": SCHEMA,
        "status": "BLOCKED" if issues else "PASS_CLI_REGISTRY_OBSERVATION_ONLY",
        "scope": "cli_toolsets_only",
        "stderr_observed_and_empty": stderr_text == "",
        "effect_expectation": "NONE",
        "actual_agent_turn_started": False,
        "remote_or_desktop_tools_qualified": False,
        "receiving_service_policy_verified": False,
        "source_pin_assertion": UPSTREAM_OBSERVATION_SHA,
        "source_or_binary_attested_by_this_report": False,
        "observation_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "issues": sorted(issues),
        "seen_builtin_count": len(seen["builtins"]),
        "seen_plugin_count": len(seen["plugins"]),
        "enabled_count": len(enabled),
        "enabled_only_clarify": enabled == [("builtins", "clarify")],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-list", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = args.tool_list.read_bytes()
        if len(data) > 96 * 1024:
            raise ValueError("OUTPUT_TOO_LARGE")
        err_data = args.stderr.read_bytes()
        if len(err_data) > 96 * 1024:
            raise ValueError("STDERR_TOO_LARGE")
        result = inspect(data.decode("utf-8", errors="strict"), err_data.decode("utf-8", errors="strict"))
        _atomic_new_receipt(args.receipt, result)
    except (OSError, ValueError, UnicodeError):
        print("REGISTRY_OBSERVATION_INPUT_OR_OUTPUT_FAILURE", file=sys.stderr)
        return 3
    print(json.dumps({"schema": SCHEMA, "status": result["status"], "receipt_written": True}))
    return 0 if result["status"] == "PASS_CLI_REGISTRY_OBSERVATION_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
