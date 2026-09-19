#!/usr/bin/env python3
"""Fail closed if the read-only Slack archive app manifest widens."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

SCHEMA = "mastermind.slack_drive_archive_manifest_check.v1"
_EXPECTED_ROOT_KEYS = {"_metadata", "display_information", "oauth_config", "settings"}
_EXPECTED_METADATA = {"major_version": 2, "minor_version": 1}
_EXPECTED_DISPLAY = {
    "name": "Mastermind Slack Archive",
    "description": "Read-only retention archive of accessible Slack history and files to Google Drive.",
}
_EXPECTED_USER_SCOPES = [
    "channels:history",
    "channels:read",
    "groups:history",
    "groups:read",
    "im:history",
    "im:read",
    "mpim:history",
    "mpim:read",
    "files:read",
]
_EXPECTED_SETTINGS = {
    "org_deploy_enabled": False,
    "socket_mode_enabled": False,
    "token_rotation_enabled": False,
    "is_hosted": False,
}


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def check_manifest(path: Path) -> str | None:
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError, TypeError):
        return "MANIFEST_INVALID"
    if not isinstance(document, dict):
        return "MANIFEST_INVALID"
    if set(document) != _EXPECTED_ROOT_KEYS:
        return "MANIFEST_SURFACE_REFUSED"
    if document.get("_metadata") != _EXPECTED_METADATA:
        return "MANIFEST_SURFACE_REFUSED"
    if document.get("display_information") != _EXPECTED_DISPLAY:
        return "MANIFEST_SURFACE_REFUSED"
    oauth = document.get("oauth_config")
    if oauth != {"scopes": {"user": _EXPECTED_USER_SCOPES}}:
        return "MANIFEST_SCOPE_REFUSED"
    if len(_EXPECTED_USER_SCOPES) != len(set(_EXPECTED_USER_SCOPES)):
        return "MANIFEST_SCOPE_REFUSED"
    if document.get("settings") != _EXPECTED_SETTINGS:
        return "MANIFEST_SURFACE_REFUSED"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    error = check_manifest(args.manifest)
    payload = {"schema": SCHEMA, "status": "ERROR" if error else "PASS"}
    if error:
        payload["error"] = error
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 2 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
