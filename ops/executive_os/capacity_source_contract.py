"""Closed, secret-free CF2-H0 source objects and non-acceptance receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if __package__ in {None, ""} and str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

try:
    from ops.executive_os.provider_worker_slots import all_slots
except ModuleNotFoundError:  # pragma: no cover
    from provider_worker_slots import all_slots  # type: ignore[no-redef]


SOURCE_CONFIG_SCHEMA = "mastermind.executive_capacity_source_config/v1"
HOST_RECEIPT_SCHEMA = "mastermind.executive_capacity_host_preparation/v1"
P0_SOURCE_KIND = "grounded_cf1_git_release"
SOURCE_CONTRACT_ID = "grounded_cf1_git_subprocess/v1"

PRODUCER_REPOSITORY = "mastermindx-market-intelligence/macro"
PRODUCER_COMMIT = "dcdd939c45b23abce5ba04f95e330ac914a3904b"
PRODUCER_MATERIAL_SOURCE_DIGEST = (
    "35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650"
)

SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
SOURCE_ROOT = SYSTEM_ROOT / "capacity-sources" / "macro" / PRODUCER_COMMIT
ENTRYPOINT = SOURCE_ROOT / "scripts" / "build_provider_capacity.py"
RUNTIME_ROOT = SYSTEM_ROOT / "capacity-runtimes" / "cf1-pyyaml-6.0.3-cp312-arm64"
PYTHON_BINARY = RUNTIME_ROOT / "bin" / "python3.12"
BASE_PYTHON_BINARY = Path(
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
)
BASE_PYTHON_VERSION = "3.12.10"
BASE_PYTHON_BINARY_SHA256 = (
    "d4f152f2a753c94e0e7935c8ebbe6b2609979e1df7898422b577d0076383d08b"
)
PYTHON_RUNTIME_RECEIPT = SYSTEM_ROOT / "python-runtime.json"

PYYAML_VERSION = "6.0.3"
PYYAML_WHEEL = "pyyaml-6.0.3-cp312-cp312-macosx_11_0_arm64.whl"
PYYAML_WHEEL_SHA256 = (
    "fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0"
)
PYYAML_RECORD_SHA256 = (
    "715146d21711444bc73c3137d18cffb6e38ace40e8998c5a9dfa69bd7dc46e3e"
)
RUNTIME_TREE_SHA256 = (
    "79e1e4dc67c0fbefc266fcf2c27b98a7e0aeff5048e015fae11b20115ee864ee"
)
ENTRYPOINT_GIT_BLOB = "9b9457c6beb673cbbb08ee00421b2d0718cbec60"
ENTRYPOINT_SHA256 = (
    "6688e6278a8cde7107b4f565d381ca57314a71913f50606f231835bb4e3e20f5"
)

TELEMETRY_ROOT = Path("/var/db/mastermind-provider-control")
AI_COSTS_STATE_ROOT = TELEMETRY_ROOT
METABOLISM_STATE_ROOT = TELEMETRY_ROOT
SOURCE_CONFIG_PATH = SYSTEM_ROOT / "config" / "capacity-source-v1.json"
HOST_RECEIPT_PATH = SYSTEM_ROOT / "config" / "capacity-host-preparation-v1.json"
COMPONENT_ROOT = SYSTEM_ROOT / "config" / "capacity-source-components-v1"

ALLOWED_ENVIRONMENT_NAMES = tuple(
    sorted(
        {
            "AI_COSTS_STATE_ROOT",
            "CODEX_ACCOUNT_HOMES",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_VALUE_0",
            "GIT_OPTIONAL_LOCKS",
            "GIT_TERMINAL_PROMPT",
            "LANG",
            "LC_ALL",
            "METABOLISM_STATE_ROOT",
            "PATH",
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONNOUSERSITE",
        }
    )
)
CAPACITY_CAPABILITY_IDS = ("codex_account", "codex_account_2", "codex_account_3")

TIMEOUT_SECONDS = 10
STDOUT_MAX_BYTES = 262144
STDERR_RETAINED_MAX_BYTES = 4096

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_FIELDS = frozenset(
    {
        "schema_version",
        "p0_source_kind",
        "source_contract_id",
        "source_release_commit",
        "source_executable_identity_digest",
        "source_entrypoint_identity_digest",
        "source_working_directory_identity_digest",
        "allowed_environment_names",
        "inventory_config_digest",
        "telemetry_config_digest",
        "timeout_seconds",
        "stdout_max_bytes",
        "stderr_retained_max_bytes",
        "no_shell",
        "network_denied",
        "write_denied",
    }
)
_COMPONENT_FIELDS = frozenset(
    {
        "source_executable_identity",
        "source_entrypoint_identity",
        "source_working_directory_identity",
        "inventory_config",
        "telemetry_config",
    }
)
_HOST_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "outcome",
        "preparer_source_commit",
        "source_release_commit",
        "producer_material_source_digest",
        "source_config_digest",
        "component_manifest_digest",
        "broker_count",
        "broker_topology_digest",
        "rollback_contract_digest",
        "rollback_drill_receipt_digest",
        "service_state",
        "socket_state",
        "control_state",
        "credential_state",
        "worker_execution_state",
        "cf2_i_state",
    }
)


class CapacitySourceContractError(ValueError):
    """Bounded refusal for closed source/receipt validation."""


def canonical_json(value: Any, *, pretty: bool = False) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=None if pretty else (",", ":"),
            indent=2 if pretty else None,
            allow_nan=False,
        ) + ("\n" if pretty else "")
    except (TypeError, ValueError) as exc:
        raise CapacitySourceContractError("NON_CANONICAL_JSON") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _digest(value: Any) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise CapacitySourceContractError("DIGEST_INVALID")
    return value


def _commit(value: Any) -> str:
    if not isinstance(value, str) or _COMMIT_RE.fullmatch(value) is None:
        raise CapacitySourceContractError("COMMIT_INVALID")
    return value


def _inventory_realms() -> list[dict[str, str]]:
    slots = all_slots()[1:]
    if len(slots) != 3:
        raise CapacitySourceContractError("REALM_INVENTORY_INVALID")
    return [
        {
            "capacity_capability_id": capability_id,
            "slot_id": slot.slot_id,
            "provider_home": str(slot.provider_home),
        }
        for slot, capability_id in zip(slots, CAPACITY_CAPABILITY_IDS, strict=True)
    ]


def build_component_objects(
    *,
    material_source_digest: str,
    pyyaml_record_sha256: str,
    runtime_tree_sha256: str,
) -> dict[str, dict[str, Any]]:
    material_digest = _digest(material_source_digest)
    if material_digest != PRODUCER_MATERIAL_SOURCE_DIGEST:
        raise CapacitySourceContractError("MATERIAL_DIGEST_MISMATCH")
    record_digest = _digest(pyyaml_record_sha256)
    runtime_digest = _digest(runtime_tree_sha256)
    if record_digest != PYYAML_RECORD_SHA256:
        raise CapacitySourceContractError("PYYAML_RECORD_DIGEST_MISMATCH")
    if runtime_digest != RUNTIME_TREE_SHA256:
        raise CapacitySourceContractError("RUNTIME_TREE_DIGEST_MISMATCH")
    return {
        "source_executable_identity": {
            "schema_version": "mastermind.executive_capacity_executable_identity/v1",
            "python_binary": str(PYTHON_BINARY),
            "python_version": BASE_PYTHON_VERSION,
            "python_binary_sha256": BASE_PYTHON_BINARY_SHA256,
            "pyyaml_version": PYYAML_VERSION,
            "pyyaml_wheel": PYYAML_WHEEL,
            "pyyaml_wheel_sha256": PYYAML_WHEEL_SHA256,
            "pyyaml_record_sha256": record_digest,
            "runtime_tree_sha256": runtime_digest,
            "isolated_mode": True,
            "user_site_disabled": True,
        },
        "source_entrypoint_identity": {
            "schema_version": "mastermind.executive_capacity_entrypoint_identity/v1",
            "repository": PRODUCER_REPOSITORY,
            "commit": PRODUCER_COMMIT,
            "entrypoint": str(ENTRYPOINT),
            "entrypoint_git_blob": ENTRYPOINT_GIT_BLOB,
            "entrypoint_sha256": ENTRYPOINT_SHA256,
            "material_source_digest": material_digest,
            "material_sources_match_commit": True,
        },
        "source_working_directory_identity": {
            "schema_version": "mastermind.executive_capacity_working_directory_identity/v1",
            "repository": PRODUCER_REPOSITORY,
            "commit": PRODUCER_COMMIT,
            "working_directory": str(SOURCE_ROOT),
            "git_directory_kind": "direct",
            "checkout_scope": "accepted_cf1_material_only",
            "head_detached": True,
            "worktree_clean": True,
            "remote_count": 0,
            "promisor_state": "offline_no_remote",
            "lazy_fetch_denied": True,
        },
        "inventory_config": {
            "schema_version": "mastermind.executive_capacity_inventory_config/v1",
            "realms": _inventory_realms(),
        },
        "telemetry_config": {
            "schema_version": "mastermind.executive_capacity_telemetry_config/v1",
            "metabolism_state_root": str(TELEMETRY_ROOT),
            "ai_costs_state_root": str(AI_COSTS_STATE_ROOT),
            "source_owner": "macro_shared_ai_provider_control",
            "filesystem_owner": "root:wheel",
            "write_authority": "none_h0_read_only",
            "initial_state": "canonical_empty_absence_witness",
            "absence_semantics": "unknown_not_zero",
        },
    }


def validate_component_objects(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != _COMPONENT_FIELDS:
        raise CapacitySourceContractError("COMPONENT_OBJECTS_FIELDS_INVALID")
    executable = value.get("source_executable_identity")
    entrypoint = value.get("source_entrypoint_identity")
    if not isinstance(executable, Mapping) or not isinstance(entrypoint, Mapping):
        raise CapacitySourceContractError("COMPONENT_OBJECTS_MISMATCH")
    expected = build_component_objects(
        material_source_digest=_digest(entrypoint.get("material_source_digest")),
        pyyaml_record_sha256=_digest(executable.get("pyyaml_record_sha256")),
        runtime_tree_sha256=_digest(executable.get("runtime_tree_sha256")),
    )
    if value != expected:
        raise CapacitySourceContractError("COMPONENT_OBJECTS_MISMATCH")
    return expected


def build_source_config(*, component_objects: Any) -> dict[str, Any]:
    components = validate_component_objects(component_objects)
    return {
        "schema_version": SOURCE_CONFIG_SCHEMA,
        "p0_source_kind": P0_SOURCE_KIND,
        "source_contract_id": SOURCE_CONTRACT_ID,
        "source_release_commit": PRODUCER_COMMIT,
        "source_executable_identity_digest": canonical_digest(
            components["source_executable_identity"]
        ),
        "source_entrypoint_identity_digest": canonical_digest(
            components["source_entrypoint_identity"]
        ),
        "source_working_directory_identity_digest": canonical_digest(
            components["source_working_directory_identity"]
        ),
        "allowed_environment_names": list(ALLOWED_ENVIRONMENT_NAMES),
        "inventory_config_digest": canonical_digest(components["inventory_config"]),
        "telemetry_config_digest": canonical_digest(components["telemetry_config"]),
        "timeout_seconds": TIMEOUT_SECONDS,
        "stdout_max_bytes": STDOUT_MAX_BYTES,
        "stderr_retained_max_bytes": STDERR_RETAINED_MAX_BYTES,
        "no_shell": True,
        "network_denied": True,
        "write_denied": True,
    }


def validate_source_config(value: Any, *, component_objects: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SOURCE_FIELDS:
        raise CapacitySourceContractError("SOURCE_CONFIG_FIELDS_INVALID")
    expected = build_source_config(component_objects=component_objects)
    if value != expected:
        raise CapacitySourceContractError("SOURCE_CONFIG_MISMATCH")
    return expected


def build_host_receipt(
    *,
    source_config: Any,
    component_objects: Any,
    preparer_source_commit: str,
    broker_topology_digest: str,
    rollback_contract_digest: str,
    rollback_drill_receipt_digest: str,
) -> dict[str, Any]:
    components = validate_component_objects(component_objects)
    config = validate_source_config(source_config, component_objects=components)
    return {
        "schema_version": HOST_RECEIPT_SCHEMA,
        "outcome": "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED",
        "preparer_source_commit": _commit(preparer_source_commit),
        "source_release_commit": PRODUCER_COMMIT,
        "producer_material_source_digest": PRODUCER_MATERIAL_SOURCE_DIGEST,
        "source_config_digest": canonical_digest(config),
        "component_manifest_digest": canonical_digest(components),
        "broker_count": 3,
        "broker_topology_digest": _digest(broker_topology_digest),
        "rollback_contract_digest": _digest(rollback_contract_digest),
        "rollback_drill_receipt_digest": _digest(rollback_drill_receipt_digest),
        "service_state": "definitions_installed_labels_disabled_unloaded",
        "socket_state": "definitions_installed_nodes_absent",
        "control_state": "legacy_files_unchanged_services_disabled_unloaded",
        "credential_state": "not_read_copied_or_created",
        "worker_execution_state": "held",
        "cf2_i_state": "held",
    }


def validate_host_receipt(
    value: Any, *, source_config: Any, component_objects: Any
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _HOST_RECEIPT_FIELDS:
        raise CapacitySourceContractError("HOST_RECEIPT_FIELDS_INVALID")
    expected = build_host_receipt(
        source_config=source_config,
        component_objects=component_objects,
        preparer_source_commit=_commit(value.get("preparer_source_commit")),
        broker_topology_digest=_digest(value.get("broker_topology_digest")),
        rollback_contract_digest=_digest(value.get("rollback_contract_digest")),
        rollback_drill_receipt_digest=_digest(value.get("rollback_drill_receipt_digest")),
    )
    if value != expected:
        raise CapacitySourceContractError("HOST_RECEIPT_MISMATCH")
    return expected


def _read_json(source: Path) -> Any:
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapacitySourceContractError("JSON_UNREADABLE") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render or verify closed CF2-H0 objects")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render")
    render.add_argument("--material-source-digest", required=True)
    render.add_argument("--pyyaml-record-sha256", required=True)
    render.add_argument("--runtime-tree-sha256", required=True)
    render.add_argument("--mastermind-commit")
    render.add_argument("--broker-topology-digest")
    render.add_argument("--rollback-contract-digest")
    render.add_argument("--rollback-drill-receipt-digest")
    verify = commands.add_parser("verify")
    verify.add_argument("--components", type=Path, required=True)
    verify.add_argument("--config", type=Path, required=True)
    verify.add_argument("--receipt", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "render":
            components = build_component_objects(
                material_source_digest=args.material_source_digest,
                pyyaml_record_sha256=args.pyyaml_record_sha256,
                runtime_tree_sha256=args.runtime_tree_sha256,
            )
            config = build_source_config(component_objects=components)
            value: dict[str, Any] = {"components": components, "source_config": config}
            if args.mastermind_commit is not None:
                if (
                    args.broker_topology_digest is None
                    or args.rollback_contract_digest is None
                    or args.rollback_drill_receipt_digest is None
                ):
                    raise CapacitySourceContractError("HOST_RECEIPT_DIGESTS_REQUIRED")
                value["host_receipt"] = build_host_receipt(
                    source_config=config,
                    component_objects=components,
                    preparer_source_commit=args.mastermind_commit,
                    broker_topology_digest=args.broker_topology_digest,
                    rollback_contract_digest=args.rollback_contract_digest,
                    rollback_drill_receipt_digest=args.rollback_drill_receipt_digest,
                )
        else:
            components = validate_component_objects(_read_json(args.components))
            config = validate_source_config(
                _read_json(args.config), component_objects=components
            )
            value = {"components": components, "source_config": config}
            if args.receipt is not None:
                value["host_receipt"] = validate_host_receipt(
                    _read_json(args.receipt),
                    source_config=config,
                    component_objects=components,
                )
    except CapacitySourceContractError as exc:
        print(f"capacity source contract refused: {exc}", file=sys.stderr)
        return 65
    sys.stdout.write(canonical_json(value, pretty=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
