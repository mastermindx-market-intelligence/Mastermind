#!/usr/bin/env python3
"""Describe or launch one explicitly configured Workbench Action stdio child.

`--describe` is dependency-free. Serving accepts only one absolute owner
config path; the tunnel/organization/workspace binding, project root, audit
location, action token key, credential, and patch target are not CLI inputs.
The fixed channel is the only admission authority on this path; no OAuth
token, verifier, or extra authentication service is created.
"""
from __future__ import annotations

import argparse
import json
import sys


def _run_configured_stdio(path: str) -> int:
    from pathlib import Path

    source_root = str(Path(__file__).resolve().parents[1])
    if not sys.path or sys.path[0] != source_root:
        sys.path.insert(0, source_root)
    from integrations.workbench_action_mcp.tunnel import run_configured_stdio

    return run_configured_stdio(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--config")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.describe:
        print(
            json.dumps(
                {
                    "capability": "BUILT_NOT_PROVEN",
                    "mode": "fixed-channel-stdio",
                    "authority_kind": "secure_mcp_tunnel_channel",
                    "tools": [
                        "workspace_manifest",
                        "read_project_file",
                        "preview_text_replace",
                        "prepare_text_patch",
                        "commit_text_patch",
                        "reconcile_text_patch",
                        "prepare_project_command",
                        "run_project_command",
                        "read_action_result",
                        "reconcile_action",
                    ],
                    "config_schema": "mastermind.workbench_action_tunnel.v1",
                    "scope": "workbench.action",
                    "installed": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.config is None:
        print("TUNNEL_CONFIGURATION_REQUIRED", file=sys.stderr)
        return 2
    return _run_configured_stdio(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
