"""Render one inert native Claude Worker Broker LaunchDaemon artifact.

This compiler reuses the existing capacity broker plist renderer and native-slot
projection. It does not install, enable, bootstrap, kickstart, or contact a
provider.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ops.executive_os.capacity_broker_topology import (
    _slot_paths,
    canonical_json,
    render_worker_plist,
)
from ops.executive_os.provider_worker_slots import native_slot_from_config
from scripts import executive_os_phase1c_worker as worker

SCHEMA = "mastermind.native_claude_worker_service_artifact/v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class NativeClaudeServiceArtifactError(ValueError):
    """The native service artifact cannot be rendered safely."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def render_service(
    config: dict[str, Any],
    *,
    config_sha256: str,
    release_root: Path,
    expected_release_sha: str,
    template_bytes: bytes,
) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(config_sha256, str) or _SHA256_RE.fullmatch(config_sha256) is None:
        raise NativeClaudeServiceArtifactError("config digest is invalid")
    if not isinstance(expected_release_sha, str) or _SHA_RE.fullmatch(expected_release_sha) is None:
        raise NativeClaudeServiceArtifactError("release SHA is invalid")
    root = Path(release_root)
    if (
        not root.is_absolute()
        or root.name != expected_release_sha
        or root.parent != Path("/Library/Application Support/MastermindExecutive/releases")
    ):
        raise NativeClaudeServiceArtifactError("release root is not the canonical installed coordinate")
    if (
        config.get("schema_version") != worker.SEALED_NATIVE_CONFIG_SCHEMA_VERSION
        or config.get("native_provider") != "claude"
        or config.get("operator_harness_armed") is not False
    ):
        raise NativeClaudeServiceArtifactError("config is not the sealed native Claude lane")
    config_bytes = canonical_json(config)
    if _digest(config_bytes) != config_sha256:
        raise NativeClaudeServiceArtifactError("config digest differs from canonical v7 bytes")
    try:
        slot = native_slot_from_config(config)
    except Exception as exc:
        raise NativeClaudeServiceArtifactError("native slot projection refused") from exc
    paths = _slot_paths(slot.slot_id)
    plist = render_worker_plist(
        template_bytes,
        slot=slot,
        paths=paths,
        release_root=root,
    )
    receipt = {
        "schema_version": SCHEMA,
        "slot_id": slot.slot_id,
        "worker_user": slot.worker_user,
        "worker_uid": slot.worker_uid,
        "worker_gid": slot.worker_gid,
        "release_sha": expected_release_sha,
        "release_root": str(root),
        "config_path": str(paths["config"]),
        "config_sha256": config_sha256,
        "plist_path": str(paths["plist"]),
        "plist_sha256": _digest(plist),
        "socket_path": str(paths["socket"]),
        "launchd_label": f"com.mastermind.executive.worker.{slot.slot_id}",
        "launchd_state": "disabled_unloaded",
        "socket_node_state": "absent",
    }
    return plist, receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render one inert native Claude worker LaunchDaemon artifact."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--plist-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = worker._load_config(args.config.resolve(), require_root_owner=False)
        plist, receipt = render_service(
            config,
            config_sha256=args.expected_config_sha256,
            release_root=args.release_root,
            expected_release_sha=args.expected_release_sha,
            template_bytes=args.template.read_bytes(),
        )
        args.plist_out.write_bytes(plist)
        args.receipt_out.write_bytes(canonical_json(receipt))
        return 0
    except (
        NativeClaudeServiceArtifactError,
        worker.WorkerConfigError,
        OSError,
        ValueError,
    ):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
