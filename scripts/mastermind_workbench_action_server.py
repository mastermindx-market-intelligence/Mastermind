#!/usr/bin/env python3
"""Describe or launch one explicitly configured Workbench Action loopback service.

`--describe` is dependency-free. Serving accepts only one absolute owner config
path; host, port, project root, action token key, credential, tunnel authority,
and patch target are not CLI inputs. The service owner performs all admission.
"""
from __future__ import annotations

import argparse
import json
import sys


def _run_configured_service(path: str) -> int:
    from pathlib import Path

    source_root = str(Path(__file__).resolve().parents[1])
    if not sys.path or sys.path[0] != source_root:
        sys.path.insert(0, source_root)
    from integrations.workbench_action_mcp.service import run_configured_service

    return run_configured_service(path)


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
                    "mode": "configured-loopback-service",
                    "tools": [
                        "prepare_text_patch",
                        "commit_text_patch",
                        "reconcile_text_patch",
                    ],
                    "config_schema": "mastermind.workbench_action_service.v1",
                    "scope": "workbench.action",
                    "installed": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.config is None:
        print("SERVICE_CONFIGURATION_REQUIRED", file=sys.stderr)
        return 2
    return _run_configured_service(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
