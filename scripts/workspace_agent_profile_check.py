#!/usr/bin/env python3
"""Read-only preflight CLI for Workspace Agent profile/activation contracts.

This command never reads a Workspace token, publishes an agent, opens a network
connection, triggers a run, writes state or grants authority. It turns reviewed
catalog/economic inputs into deterministic digests and a validated activation
binding for the real effect owner to re-check.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from integrations.workspace_agent_profiles import (
    WorkspaceProfileError,
    activation_binding_digest,
    build_activation_binding,
    catalog_digest,
    profile_digest,
    validate_activation_binding,
    validate_profile_catalog,
)

MAX_INPUT_BYTES = 128 * 1024


class CliRefusal(ValueError):
    pass


def _read_json(path: str) -> dict[str, Any]:
    candidate = Path(path)
    try:
        if not candidate.is_file():
            raise CliRefusal
        raw = candidate.read_bytes()
    except (OSError, ValueError):
        raise CliRefusal("INPUT_UNAVAILABLE") from None
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise CliRefusal("INPUT_UNAVAILABLE")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise CliRefusal("INVALID_JSON") from None
    if not isinstance(value, dict):
        raise CliRefusal("INVALID_JSON")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Workspace Agent profile and activation inputs only."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog")
    catalog.add_argument("--catalog", required=True)

    activation = sub.add_parser("activation")
    activation.add_argument("--catalog", required=True)
    activation.add_argument("--economic-envelope", required=True)
    activation.add_argument("--profile-id", required=True)
    activation.add_argument("--channel-id", required=True)
    activation.add_argument("--agent-version-ref", required=True)
    activation.add_argument("--return-subject-digest", required=True)
    activation.add_argument("--now-ms", required=True, type=int)
    return parser


def run(argv: list[str]) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    catalog = validate_profile_catalog(_read_json(args.catalog))
    if args.command == "catalog":
        return {
            "ok": True,
            "schema": "mastermind.workspace_agent_profile_preflight.v1",
            "publication_state": catalog["publication_state"],
            "catalog_revision": catalog["catalog_revision"],
            "catalog_digest": catalog_digest(catalog),
            "profiles": [
                {
                    "profile_id": profile["profile_id"],
                    "revision": profile["revision"],
                    "profile_digest": profile_digest(profile),
                    "required_app_bindings": list(profile["required_app_bindings"]),
                }
                for profile in catalog["profiles"]
            ],
        }

    economic = _read_json(args.economic_envelope)
    binding = build_activation_binding(
        catalog=catalog,
        profile_id=args.profile_id,
        provider_channel_ref=args.channel_id,
        agent_version_ref=args.agent_version_ref,
        return_subject_digest=args.return_subject_digest,
        economic_envelope=economic,
    )
    validated = validate_activation_binding(
        binding,
        catalog=catalog,
        now_ms=args.now_ms,
    )
    return {
        "ok": True,
        "schema": "mastermind.workspace_agent_activation_preflight.v1",
        "activation_binding": validated,
        "activation_digest": activation_binding_digest(
            validated,
            catalog=catalog,
            now_ms=args.now_ms,
        ),
        "provider_effect_performed": False,
        "authority_granted": False,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(list(sys.argv[1:] if argv is None else argv))
    except (CliRefusal, WorkspaceProfileError, SystemExit):
        result = {
            "ok": False,
            "schema": "mastermind.workspace_agent_profile_preflight.v1",
            "error": "PREFLIGHT_REFUSED",
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
