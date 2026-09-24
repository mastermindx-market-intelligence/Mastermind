"""Closed inert three-broker topology for CF2-H0.

H0 installs definitions only.  It never composes the control runtime with
these brokers, adds a broker operation, starts a service, or opens a socket.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if __package__ in {None, ""} and str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

try:
    from ops.executive_os.provider_worker_slots import all_slots
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    from provider_worker_slots import all_slots  # type: ignore[no-redef]


TOPOLOGY_SCHEMA = "mastermind.executive_capacity_broker_topology/v1"
ROLLBACK_SCHEMA = "mastermind.executive_capacity_h0_rollback/v1"
WORKER_CONFIG_SCHEMA = "mastermind.executive_worker_broker_config/v4"
CONTROL_UID = 450
CONTROL_GID = 450
SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
CONFIG_ROOT = SYSTEM_ROOT / "config"
RUNTIME_ROOT = Path("/var/db/mastermind-executive")
LAUNCHD_ROOT = Path("/Library/LaunchDaemons")
SOCKET_ROOT = Path("/var/run/mastermind-executive")
LOG_ROOT = Path("/var/log/mastermind-executive/workers")
CODEX_VERSION = "0.147.0"
CODEX_BINARY = SYSTEM_ROOT / "bin" / f"codex-{CODEX_VERSION}"
PYTHON_BINARY = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12")
TEAM_IDENTIFIER = "2DC432GLL2"
PERSONAL_CAPABILITY_IDS = ("codex_account", "codex_account_2", "codex_account_3")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class CapacityBrokerTopologyError(ValueError):
    """Closed refusal for invalid H0 topology."""


def canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=None if pretty else (",", ":"),
                indent=2 if pretty else None,
                allow_nan=False,
            )
            + ("\n" if pretty else "")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapacityBrokerTopologyError("NON_CANONICAL_JSON") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _slot_paths(slot_id: str) -> dict[str, Path]:
    slot_root = RUNTIME_ROOT / "workers" / slot_id
    return {
        "config": CONFIG_ROOT / f"worker-{slot_id}.json",
        "attestation": SYSTEM_ROOT / f"codex-attestation-{CODEX_VERSION}-{slot_id}.json",
        "plist": LAUNCHD_ROOT / f"com.mastermind.executive.worker.{slot_id}.plist",
        "socket": SOCKET_ROOT / f"worker-{slot_id}.sock",
        "workspace": RUNTIME_ROOT / "jobs" / "workspaces",
        "runs": RUNTIME_ROOT / "jobs" / "runs",
        "sweep": slot_root / "state" / "uid-sweep.json",
        "stdout": LOG_ROOT / slot_id / "stdout.log",
        "stderr": LOG_ROOT / slot_id / "stderr.log",
    }


def build_worker_config(
    *,
    slot: Any,
    paths: Mapping[str, Path],
    allowed_supplementary_gids: Sequence[int],
) -> dict[str, Any]:
    gids = list(allowed_supplementary_gids)
    if (
        gids != sorted(set(gids))
        or any(isinstance(gid, bool) or not isinstance(gid, int) for gid in gids)
        or slot.worker_gid in gids
        or set(gids) not in ({12, 61, 100}, {12, 61, 100, 396})
    ):
        raise CapacityBrokerTopologyError("SUPPLEMENTARY_GIDS_INVALID")
    return {
        "schema_version": WORKER_CONFIG_SCHEMA,
        "control_uid": CONTROL_UID,
        "worker_uid": slot.worker_uid,
        "worker_gid": slot.worker_gid,
        "allowed_supplementary_gids": gids,
        "worker_user": slot.worker_user,
        "worker_id": slot.slot_id,
        "workspace_root": str(paths["workspace"]),
        "run_root": str(paths["runs"]),
        "provider_home": str(slot.provider_home),
        "codex_binary": str(CODEX_BINARY),
        "codex_attestation_receipt": str(paths["attestation"]),
        "allowed_codex_versions": [CODEX_VERSION],
        "required_team_identifier": TEAM_IDENTIFIER,
        "launchd_socket_name": "WorkerBroker",
        "uid_sweep_receipt": str(paths["sweep"]),
        "require_secret_canary": True,
        "operator_harness_armed": False,
    }


def render_worker_plist(
    template_bytes: bytes,
    *,
    slot: Any,
    paths: Mapping[str, Path],
    release_root: Path,
) -> bytes:
    try:
        value = plistlib.loads(template_bytes)
    except plistlib.InvalidFileException as exc:
        raise CapacityBrokerTopologyError("PLIST_TEMPLATE_INVALID") from exc
    if not isinstance(value, dict) or value.get("Label") != "com.mastermind.executive.worker.codex":
        raise CapacityBrokerTopologyError("PLIST_TEMPLATE_MISMATCH")
    label = f"com.mastermind.executive.worker.{slot.slot_id}"
    value["Label"] = label
    value["ProgramArguments"] = [
        str(PYTHON_BINARY),
        "-I",
        "-S",
        "-B",
        str(release_root / "scripts" / "executive_os_phase1c_worker.py"),
        "serve",
        "--config",
        str(paths["config"]),
    ]
    value["WorkingDirectory"] = str(release_root)
    value["UserName"] = slot.worker_user
    value["GroupName"] = slot.worker_group
    value["InitGroups"] = False
    value["EnvironmentVariables"]["HOME"] = str(slot.provider_home)
    socket = value["Sockets"]["WorkerBroker"]
    socket["SockPathName"] = str(paths["socket"])
    socket["SockPathOwner"] = CONTROL_UID
    socket["SockPathGroup"] = CONTROL_GID
    socket["SockPathMode"] = 0o600
    value["StandardOutPath"] = str(paths["stdout"])
    value["StandardErrorPath"] = str(paths["stderr"])
    return plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=False)


def build_topology(
    *,
    release_root: Path,
    template_bytes: bytes,
    supplementary_gids: Mapping[str, Sequence[int]],
    attestation_sha256: str,
    legacy_state_digest: str,
) -> tuple[dict[str, Any], dict[str, bytes], dict[str, bytes]]:
    if _DIGEST_RE.fullmatch(attestation_sha256) is None:
        raise CapacityBrokerTopologyError("ATTESTATION_DIGEST_INVALID")
    if _DIGEST_RE.fullmatch(legacy_state_digest) is None:
        raise CapacityBrokerTopologyError("LEGACY_STATE_DIGEST_INVALID")
    slots = all_slots()[1:]
    if tuple(slot.slot_id for slot in slots) != (
        "codex-pro-01",
        "codex-pro-02",
        "codex-pro-03",
    ) or len(slots) != len(PERSONAL_CAPABILITY_IDS):
        raise CapacityBrokerTopologyError("SLOT_INVENTORY_INVALID")
    configs: dict[str, bytes] = {}
    plists: dict[str, bytes] = {}
    rows: list[dict[str, Any]] = []
    for slot, capability_id in zip(slots, PERSONAL_CAPABILITY_IDS):
        paths = _slot_paths(slot.slot_id)
        config = build_worker_config(
            slot=slot,
            paths=paths,
            allowed_supplementary_gids=supplementary_gids.get(slot.slot_id, ()),
        )
        config_bytes = canonical_json(config, pretty=True)
        plist_bytes = render_worker_plist(
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
                "capacity_capability_id": capability_id,
                "label": f"com.mastermind.executive.worker.{slot.slot_id}",
                "worker_user": slot.worker_user,
                "worker_group": slot.worker_group,
                "worker_uid": slot.worker_uid,
                "worker_gid": slot.worker_gid,
                "provider_home": str(slot.provider_home),
                "workspace_root": str(paths["workspace"]),
                "run_root": str(paths["runs"]),
                "config_path": str(paths["config"]),
                "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
                "attestation_path": str(paths["attestation"]),
                "attestation_sha256": attestation_sha256,
                "plist_path": str(paths["plist"]),
                "plist_sha256": hashlib.sha256(plist_bytes).hexdigest(),
                "socket_path": str(paths["socket"]),
                "socket_owner_uid": CONTROL_UID,
                "socket_group_gid": CONTROL_GID,
                "socket_mode": 0o600,
                "launchd_state": "disabled_unloaded",
                "socket_node_state": "absent",
            }
        )
    topology = {
        "schema_version": TOPOLOGY_SCHEMA,
        "release_root": str(release_root),
        "worker_entrypoint": str(release_root / "scripts" / "executive_os_phase1c_worker.py"),
        "runtime_composition": "held_for_cf2_i_b",
        "worker_execution": "held",
        "legacy_phase1c_state_digest": legacy_state_digest,
        "brokers": rows,
    }
    return topology, configs, plists


def build_rollback_contract(*, topology: Mapping[str, Any]) -> dict[str, Any]:
    rows = topology.get("brokers")
    if not isinstance(rows, list) or len(rows) != 3:
        raise CapacityBrokerTopologyError("TOPOLOGY_INVALID")
    return {
        "schema_version": ROLLBACK_SCHEMA,
        "operation": "shrink_only_h0_topology_rollback",
        "labels": [row["label"] for row in rows],
        "movable_artifacts": sorted(
            path
            for row in rows
            for path in (row["config_path"], row["attestation_path"], row["plist_path"])
        ),
        "preserve": [
            "service_principals",
            "provider_homes",
            "credentials",
            "immutable_releases",
            "capacity_source_release",
            "capacity_runtime",
            "provider_control_telemetry",
            "legacy_phase1c_artifacts",
        ],
        "postcondition": "all_h0_labels_disabled_unloaded_socket_nodes_absent",
        "start_authority": False,
        "delete_authority": False,
    }


def write_rendered_topology(
    destination: Path,
    *,
    topology: Mapping[str, Any],
    configs: Mapping[str, bytes],
    plists: Mapping[str, bytes],
) -> None:
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    artifacts: list[tuple[str, bytes]] = [
        ("broker-topology.json", canonical_json(topology)),
        ("rollback-contract.json", canonical_json(build_rollback_contract(topology=topology))),
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
    parser = argparse.ArgumentParser(description="Render inert CF2-H0 broker topology")
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--attestation-sha256", required=True)
    parser.add_argument("--supplementary-gids-json", type=Path, required=True)
    parser.add_argument("--legacy-state-digest", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        gids = json.loads(args.supplementary_gids_json.read_text(encoding="utf-8"))
        topology, configs, plists = build_topology(
            release_root=args.release_root,
            template_bytes=args.template.read_bytes(),
            supplementary_gids=gids,
            attestation_sha256=args.attestation_sha256,
            legacy_state_digest=args.legacy_state_digest,
        )
        write_rendered_topology(
            args.destination,
            topology=topology,
            configs=configs,
            plists=plists,
        )
    except (CapacityBrokerTopologyError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"capacity broker topology refused: {type(exc).__name__}", file=sys.stderr)
        return 65
    print(canonical_digest(topology))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
