from __future__ import annotations

from pathlib import Path

import yaml

from scripts.check_slack_drive_archive_app_manifest import check_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "slack_drive_archive_app_manifest.yaml"


def test_exact_read_only_archive_manifest_passes() -> None:
    assert check_manifest(MANIFEST) is None


def test_archive_manifest_refuses_slack_write_scope(tmp_path: Path) -> None:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    document["oauth_config"]["scopes"]["user"].append("chat:write")
    candidate = tmp_path / "manifest.yaml"
    candidate.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    assert check_manifest(candidate) == "MANIFEST_SCOPE_REFUSED"


def test_archive_manifest_refuses_events_or_socket_mode(tmp_path: Path) -> None:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    document["event_subscriptions"] = {"user_events": ["message.channels"]}
    candidate = tmp_path / "manifest.yaml"
    candidate.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    assert check_manifest(candidate) == "MANIFEST_SURFACE_REFUSED"

    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    document["settings"]["socket_mode_enabled"] = True
    candidate.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    assert check_manifest(candidate) == "MANIFEST_SURFACE_REFUSED"
