"""Operator inspection and change preview over existing routing configuration.

Run: python -m ops.executive_os.model_pool_control inspect
No listener, credentials, provider call, runtime reload or publication is created.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from control_plane.model_router_configuration import (
    ConfigurationError, load_configuration, preview_configuration_paths,
)


_ERROR_CODES = frozenset({
    "DUPLICATE_CONFIGURATION_KEY", "NONFINITE_CONFIGURATION_VALUE",
    "CONFIGURATION_CHANGED_DURING_READ", "CONFIGURATION_SOURCE_UNAVAILABLE",
    "CONFIGURATION_SOURCE_INVALID", "CONFIGURATION_SOURCE_OVER_BUDGET",
    "CONFIGURATION_ROOT_INVALID", "CONFIGURATION_SHAPE_OVER_BUDGET",
    "NONPUBLIC_CONFIGURATION_VALUE", "CONFIGURATION_LIST_INVALID",
    "CONFIGURATION_OUTPUT_OVER_BUDGET", "VALIDATED_ROUTER_REQUIRED",
    "CONFIGURATION_ROW_BOUND_EXCEEDED", "CONFIGURATION_DIGEST_INVALID",
    "CAPABILITY_POLICY_SOURCE_INVALID", "CAPABILITY_POLICY_CHANGED_DURING_READ",
    "OWNER_CONFIGURATION_REFUSED", "EXPECTED_CONFIGURATION_REVISION_REQUIRED",
    "STALE_CONFIGURATION_REVISION",
})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect existing ModelRouter configuration or preview an exact revision change.")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Read configured logical providers/models; not live capacity")
    inspect.add_argument("--policy", type=Path)
    inspect.add_argument("--capabilities", type=Path)
    inspect.add_argument("--summary", action="store_true", help="Only counts, revision and owner boundary")
    preview = sub.add_parser("preview", help="Validate both existing-owner policies without applying changes")
    preview.add_argument("--policy", type=Path)
    preview.add_argument("--capabilities", type=Path)
    preview.add_argument("--candidate", type=Path, required=True)
    preview.add_argument("--candidate-capabilities", type=Path)
    preview.add_argument("--expected-revision", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            document = load_configuration(args.policy,
                                          capability_policy_path=args.capabilities)
            if args.summary:
                document = {key: document[key] for key in (
                    "schema", "owner", "scope", "revision", "policy_version",
                    "capability_policy_version", "capability_policy_digest",
                    "physical_account_pools", "live_capacity", "admission_authorized",
                    "writes_applied", "credential_resolution_performed",
                )} | {
                    "provider_alias_count": len(document["providers"]),
                    "model_alias_count": len(document["models"]),
                    "workload_route_count": len(document["routes"]),
                }
        else:
            document = preview_configuration_paths(
                args.candidate, expected_revision=args.expected_revision,
                current_path=args.policy, capability_policy_path=args.capabilities,
                candidate_capability_path=args.candidate_capabilities)
        print(json.dumps(document, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False))
        return 0
    except ConfigurationError as exc:
        code = str(exc)
        print(json.dumps({"schema": "mastermind.model_pool_control_refusal.v1",
                          "code": code if code in _ERROR_CODES else "OWNER_CONFIGURATION_REFUSED",
                          "writes_applied": False, "credential_resolution_performed": False}), file=sys.stderr)
        return 2
    except Exception:
        # A backend/parser exception must not copy paths, secrets or source data
        # into the public command receipt. No automatic alternate/retry path.
        print('{"schema":"mastermind.model_pool_control_refusal.v1",'
              '"code":"OWNER_CONFIGURATION_REFUSED","writes_applied":false,'
              '"credential_resolution_performed":false}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
