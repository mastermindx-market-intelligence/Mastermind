"""Render inert broker definitions for reviewed Codex-backed subscription realms.

This module does not install, bootstrap, start, register, route, admit, or
credential a worker. It renders a closed staging artifact that existing
installation/admission owners may consume only after their own gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.subscription_harness_bindings import get_binding
from ops.executive_os.capacity_broker_topology import (
    CONFIG_ROOT,
    LAUNCHD_ROOT,
    LOG_ROOT,
    RUNTIME_ROOT,
    SOCKET_ROOT,
    SYSTEM_ROOT,
    CODEX_VERSION,
    build_worker_config,
    canonical_json,
    render_worker_plist,
)
from ops.executive_os.provider_worker_slots import subscription_slots


DEFINITIONS_SCHEMA = "mastermind.executive_subscription_broker_definitions/v1"
WORKER_CONFIG_SCHEMA = "mastermind.executive_worker_broker_config/v5"


class SubscriptionBrokerDefinitionError(ValueError):
    """Closed refusal for invalid subscription broker staging input."""


def _slot_paths(slot: Any) -> dict[str, Path]:
    slot_root = RUNTIME_ROOT / "workers" / slot.slot_id
    return {
        "config": CONFIG_ROOT / f"worker-{slot.slot_id}.json",
        "attestation": SYSTEM_ROOT / f"codex-attestation-{CODEX_VERSION}-{slot.slot_id}.json",
        "plist": LAUNCHD_ROOT / f"com.mastermind.executive.worker.{slot.slot_id}.plist",
        "socket": SOCKET_ROOT / f"worker-{slot.slot_id}.sock",
        "workspace": RUNTIME_ROOT / "jobs" / "workspaces",
        "runs": RUNTIME_ROOT / "jobs" / "runs",
        "sweep": slot_root / "state" / "uid-sweep.json",
        "stdout": LOG_ROOT / slot.slot_id / "stdout.log",
        "stderr": LOG_ROOT / slot.slot_id / "stderr.log",
    }


def _reviewed_binding(slot: Any) -> Any:
    binding = get_binding(slot.harness_binding_id)
    if (
        binding.provider != slot.provider
        or binding.profile_id != slot.profile_id
        or binding.adapter_id != "codex-cli"
        or binding.harness_id != "codex-cli"
        or binding.protocol != "responses"
        or binding.implementation_state != "BUILT_NOT_PROVEN"
        or binding.autonomous_allowed is not False
    ):
        raise SubscriptionBrokerDefinitionError("SUBSCRIPTION_BINDING_NOT_HELD")
    return binding


def build_subscription_worker_config(
    *,
    slot: Any,
    paths: Mapping[str, Path],
    allowed_supplementary_gids: Sequence[int],
) -> dict[str, Any]:
    _reviewed_binding(slot)
    if Path(paths["config"]) != slot.worker_config:
        raise SubscriptionBrokerDefinitionError("WORKER_CONFIG_PATH_MISMATCH")
    value = build_worker_config(
        slot=slot,
        paths=paths,
        allowed_supplementary_gids=allowed_supplementary_gids,
    )
    value["schema_version"] = WORKER_CONFIG_SCHEMA
    value["harness_binding_id"] = slot.harness_binding_id
    return value


def _render_held_worker_plist(
    template_bytes: bytes,
    *,
    slot: Any,
    paths: Mapping[str, Path],
    release_root: Path,
) -> bytes:
    rendered = render_worker_plist(
        template_bytes,
        slot=slot,
        paths=paths,
        release_root=release_root,
    )
    try:
        value = plistlib.loads(rendered)
    except plistlib.InvalidFileException as exc:
        raise SubscriptionBrokerDefinitionError("PLIST_RENDER_INVALID") from exc
    if not isinstance(value, dict):
        raise SubscriptionBrokerDefinitionError("PLIST_RENDER_INVALID")
    value["RunAtLoad"] = False
    value["KeepAlive"] = False
    value["Disabled"] = True
    return plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=False)


def build_definitions(
    *,
    release_root: Path,
    template_bytes: bytes,
    supplementary_gids: Mapping[str, Sequence[int]],
) -> tuple[dict[str, Any], dict[str, bytes], dict[str, bytes]]:
    slots = subscription_slots()
    expected_ids = {slot.slot_id for slot in slots}
    if set(supplementary_gids) != expected_ids:
        raise SubscriptionBrokerDefinitionError("SUPPLEMENTARY_GID_KEYS_INVALID")

    configs: dict[str, bytes] = {}
    plists: dict[str, bytes] = {}
    rows: list[dict[str, Any]] = []
    for slot in slots:
        paths = _slot_paths(slot)
        config = build_subscription_worker_config(
            slot=slot,
            paths=paths,
            allowed_supplementary_gids=supplementary_gids[slot.slot_id],
        )
        config_bytes = canonical_json(config, pretty=True)
        plist_bytes = _render_held_worker_plist(
            template_bytes,
            slot=slot,
            paths=paths,
            release_root=release_root,
        )
        configs[slot.slot_id] = config_bytes
        plists[slot.slot_id] = plist_bytes
        rows.append(
            {
                "slot_id": slot.slot_id,
                "provider": slot.provider,
                "profile_id": slot.profile_id,
                "harness_binding_id": slot.harness_binding_id,
                "config_path": str(paths["config"]),
                "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
                "plist_path": str(paths["plist"]),
                "plist_sha256": hashlib.sha256(plist_bytes).hexdigest(),
                "launchd_state": "disabled_unloaded",
                "worker_execution": "held_for_real_canary",
                "autonomous_allowed": False,
            }
        )
    manifest = {
        "schema_version": DEFINITIONS_SCHEMA,
        "release_root": str(release_root),
        "start_authority": False,
        "credential_authority": False,
        "capacity_authority": False,
        "route_authority": False,
        "definitions": rows,
    }
    return manifest, configs, plists


def write_definitions(
    destination: Path,
    *,
    manifest: Mapping[str, Any],
    configs: Mapping[str, bytes],
    plists: Mapping[str, bytes],
) -> None:
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    artifacts: list[tuple[str, bytes]] = [
        ("subscription-broker-definitions.json", canonical_json(manifest, pretty=True))
    ]
    for slot_id in sorted(configs):
        artifacts.extend(
            (
                (f"worker-{slot_id}.json", configs[slot_id]),
                (f"com.mastermind.executive.worker.{slot_id}.plist", plists[slot_id]),
            )
        )
    for name, payload in artifacts:
        descriptor = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render inert reviewed subscription broker definitions"
    )
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--supplementary-gids-json", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        gids = json.loads(args.supplementary_gids_json.read_text(encoding="utf-8"))
        if not isinstance(gids, dict):
            raise SubscriptionBrokerDefinitionError("SUPPLEMENTARY_GIDS_INVALID")
        manifest, configs, plists = build_definitions(
            release_root=args.release_root,
            template_bytes=args.template.read_bytes(),
            supplementary_gids=gids,
        )
        write_definitions(
            args.destination,
            manifest=manifest,
            configs=configs,
            plists=plists,
        )
    except (
        SubscriptionBrokerDefinitionError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        print(
            f"subscription broker definitions refused: {type(exc).__name__}",
            file=os.sys.stderr,
        )
        return 65
    print(hashlib.sha256(canonical_json(manifest)).hexdigest())
    return 0


__all__ = [
    "DEFINITIONS_SCHEMA",
    "WORKER_CONFIG_SCHEMA",
    "SubscriptionBrokerDefinitionError",
    "build_definitions",
    "build_subscription_worker_config",
    "main",
    "write_definitions",
]


if __name__ == "__main__":
    raise SystemExit(main())
