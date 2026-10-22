#!/usr/bin/env python3
"""Bounded read-only Cursor M2 capability census.

This is NOT a scheduler, worker launcher, model router, admission owner or health daemon.
Never prints Cursor login/email, token material, raw CLI outputs or host secrets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

try:
    from . import install, qualification
except ImportError:
    import install  # type: ignore[no-redef]
    import qualification  # type: ignore[no-redef]

CLI_TIMEOUT_S = 15
MODEL_LINE = re.compile(r"^([a-z0-9][a-z0-9_.-]{0,95}) - ")
SERVER_LINE = re.compile(r"^([a-z][A-Za-z0-9_-]{0,63}): (ready|disabled|error|failed|unavailable)\s*$")
ROLE_MODEL = re.compile(r"(?m)^model: ([a-z0-9][a-z0-9_.-]{0,95}|inherit)$")


def bounded_probe(argv: list[str]) -> tuple[int, str]:
    """Allowlist only non-mutating Cursor CLI catalog commands."""
    allowed = {
        ("agent", "--version"),
        ("agent", "--list-models"),
        ("agent", "mcp", "list"),
        ("agent", "mcp", "list-tools", "mastermindStudio"),
    }
    if tuple(argv) not in allowed:
        raise ValueError("CLI probe command not admitted")
    try:
        cp = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=CLI_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    # No credential-bearing raw output is exposed. Parsers retain allowlisted
    # model IDs, server names/statuses, and typed tool names only.
    if len(cp.stdout) > 256 * 1024:
        return 1, ""
    return cp.returncode, cp.stdout


def advertised_models(stdout: str) -> list[str]:
    return sorted({m.group(1) for line in stdout.splitlines() if (m := MODEL_LINE.match(line))})


def mcp_servers(stdout: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2)
        for line in stdout.splitlines()
        if (m := SERVER_LINE.match(line))
    }


def projected_agent_models(source_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, expected in install.FILES.items():
        if not (key.startswith("agents/") and key.endswith(".md")):
            continue
        data = (source_root / key).read_bytes()
        if install.digest(data) != expected:
            raise install.ProjectionRefused("reviewed agent source digest mismatch")
        text = data.decode("utf-8")
        match = ROLE_MODEL.search(text)
        if not match:
            raise install.ProjectionRefused("source agent lacks a model declaration")
        result[Path(key).stem] = match.group(1)
    return result


def census(workspace: Path) -> dict[str, object]:
    try:
        ready = install.project(workspace, "verify")
        project_state = ready["state"]
    except (install.ProjectionRefused, OSError, ValueError):
        project_state = "PROJECT_PROJECTION_UNQUALIFIED"
    code_version, raw_version = bounded_probe(["agent", "--version"])
    code_models, raw_models = bounded_probe(["agent", "--list-models"])
    code_servers, raw_servers = bounded_probe(["agent", "mcp", "list"])
    code_tools, raw_tools = bounded_probe(
        ["agent", "mcp", "list-tools", "mastermindStudio"]
    )
    version = raw_version.strip()
    if code_version != 0 or len(version) > 80 or not re.fullmatch(r"[0-9A-Za-z._-]+", version):
        version = "UNVERIFIED"
    models = advertised_models(raw_models) if code_models == 0 else []
    servers = mcp_servers(raw_servers) if code_servers == 0 else {}
    fab = qualification.classify(raw_tools, code_tools, "mastermindStudio")
    try:
        requested_roles = projected_agent_models(install.ROOT)
    except (install.ProjectionRefused, OSError):
        requested_roles = {}
    role_models = {
        name: {
            "requested_model": model,
            "advertised": model == "inherit" or model in models,
            "actual_child_model_proven": False,
        }
        for name, model in sorted(requested_roles.items())
    }
    return {
        "schema": "mastermind.cursor_capability_census.v1",
        "inspection": "READ_ONLY_NO_DISPATCH",
        "workspace_project_state": project_state,
        "cursor_cli_version": version,
        "model_catalog_state": "ADVERTISED_ONLY" if models else "NOT_OBSERVED",
        "advertised_model_count": len(models),
        "role_models": role_models,
        "mcp_servers": servers,
        "studio_fabric_tools": fab["fabric_tool_names"],
        "studio_fabric_catalog_state": fab["state"],
        "fabric_dispatch_authorized": False,
        "native_task_started": False,
        "observed_actual_models": False,
        "cloud_worker_admission_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    report = census(args.workspace)
    print(json.dumps(report, sort_keys=True))
    return 0 if (
        report["workspace_project_state"] == "READY"
        and report["model_catalog_state"] == "ADVERTISED_ONLY"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
