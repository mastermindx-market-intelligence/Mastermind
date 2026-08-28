#!/usr/bin/env python3
"""Fail closed if the reviewed Agent Relay Slack app manifest widens."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "mastermind.slack_agent_relay_manifest_check.v1"

_EXPECTED_ROOT_KEYS = {
    "_metadata",
    "display_information",
    "features",
    "oauth_config",
    "settings",
}
_EXPECTED_METADATA = {"major_version": 2, "minor_version": 1}
_EXPECTED_DISPLAY = {
    "name": "Mastermind Agent Relay",
    "description": "Governed Slack transport for bounded Sol and COO agent dialogue.",
}
_EXPECTED_FEATURES = {
    "bot_user": {"display_name": "Mastermind Relay", "always_online": False}
}
_EXPECTED_BOT_SCOPES = ["channels:history", "chat:write"]
_EXPECTED_SETTINGS = {
    "org_deploy_enabled": False,
    "socket_mode_enabled": False,
    "token_rotation_enabled": False,
    "is_hosted": False,
}


def _emit(status: str, *, error: str | None = None) -> int:
    receipt: dict[str, str] = {"schema": SCHEMA, "status": status}
    if error is not None:
        receipt["error"] = error
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if status == "PASS" else 2


def _load(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return None


def check_manifest(path: Path) -> str | None:
    document = _load(path)
    if not isinstance(document, dict):
        return "MANIFEST_INVALID"

    oauth = document.get("oauth_config")
    scopes = oauth.get("scopes") if isinstance(oauth, dict) else None
    bot_scopes = scopes.get("bot") if isinstance(scopes, dict) else None
    if (
        not isinstance(scopes, dict)
        or set(scopes) != {"bot"}
        or not isinstance(bot_scopes, list)
        or bot_scopes != _EXPECTED_BOT_SCOPES
        or len(bot_scopes) != len(set(bot_scopes))
    ):
        return "MANIFEST_SCOPE_REFUSED"

    if set(document) != _EXPECTED_ROOT_KEYS:
        return "MANIFEST_SURFACE_REFUSED"
    if document.get("_metadata") != _EXPECTED_METADATA:
        return "MANIFEST_SURFACE_REFUSED"
    if document.get("display_information") != _EXPECTED_DISPLAY:
        return "MANIFEST_SURFACE_REFUSED"
    if document.get("features") != _EXPECTED_FEATURES:
        return "MANIFEST_SURFACE_REFUSED"
    if oauth != {"scopes": {"bot": _EXPECTED_BOT_SCOPES}}:
        return "MANIFEST_SURFACE_REFUSED"
    if document.get("settings") != _EXPECTED_SETTINGS:
        return "MANIFEST_SURFACE_REFUSED"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)

    error = check_manifest(args.manifest)
    if error is not None:
        return _emit("ERROR", error=error)
    return _emit("PASS")


if __name__ == "__main__":
    raise SystemExit(main())
