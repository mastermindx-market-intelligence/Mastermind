#!/usr/bin/env python3
"""Offline CI expectations over canonical Claude MCP projections; never admission.

The registry/package owners remain authority and claude_mcp_client_projection
remains the sole projector. This checker performs no provider, network, process,
credential, installation, or runtime operation. It never rewrites its manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.claude_mcp_client_projection import (  # noqa: E402
    ClaudeMcpProjectionError, project_claude_mcp_client,
)
from control_plane.executive_agent_capabilities import (  # noqa: E402
    CapabilityPolicyError, ExecutionCapabilityProfile, ExecutionCapabilityRegistry,
    is_sealed_worker_execution_surface,
)

SCHEMA = "mastermind.claude_mcp_projection_parity/v1"
SCOPE = "static_mcp_configuration_only_not_native_admission"
POLICY = "config/executive_agent_capabilities.json"
PROJECTOR = "control_plane/claude_mcp_client_projection.py"
MANIFEST = "config/claude_mcp_projection_parity.json"
SURFACES = ("cli", "agent-sdk", "desktop-local", "inline-subagent")
STATUSES = frozenset({"configuration_supported", "deferred", "unsupported"})


class ParityError(ValueError):
    """A declared generation or classification needs explicit requalification."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _exact(value: Any, keys: set[str], location: str) -> None:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ParityError(f"{location}: missing or unexpected fields")


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ParityError("repository-relative file required")
    result = (root / relative).resolve(strict=True)
    if not result.is_relative_to(root.resolve(strict=True)) or not result.is_file():
        raise ParityError("file must remain inside the source repository")
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ParityError("duplicate manifest field")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ParityError("manifest must be an object")
    return value


def profile_expectation(
    registry: ExecutionCapabilityRegistry, profile: ExecutionCapabilityProfile,
) -> dict[str, Any]:
    """Consume existing canonical digests; do not mint capability identities."""
    package_ids = {g.package_capability_id for g in profile.skill_grants}
    return {
        "profile_digest": profile.profile_digest,
        "package_generation_digests": {
            key: registry.capability_packages[key].package_generation_digest
            for key in sorted(package_ids)
        },
    }


def projection_expectation(
    profile: ExecutionCapabilityProfile, surface: str,
) -> dict[str, Any]:
    """Snapshot the existing projector's static output, not a tools/list receipt."""
    if (not profile.enabled or is_sealed_worker_execution_surface(profile.execution_surface)
            or not profile.mcp_server_grants):
        raise ParityError("disabled, sealed or MCP-empty profiles cannot claim MCP support")
    if surface not in ("cli", "agent-sdk"):
        raise ParityError("this slice only qualifies CLI and Agent SDK static configuration")
    projection = project_claude_mcp_client(profile, surface=surface)
    if projection.production_armed is not False:
        raise ParityError("projection must not arm production")
    return {
        "configuration_sha256": _digest(projection.configuration()),
        "source_profile_id": projection.source_profile_id,
        "source_profile_digest": projection.source_profile_digest,
        "source_grant_digests": list(projection.source_grant_digests),
        "source_tool_schema_digests": list(projection.source_tool_schema_digests),
        "enabled_tools": list(projection.enabled_tools),
        "auto_approved_tools": list(projection.auto_approved_tools),
        "denied_tools": list(projection.denied_tools),
        "cli_arguments_sha256": _digest(list(projection.cli_arguments())) if surface == "cli" else None,
        "production_armed": False,
    }


def validate_manifest(manifest: Mapping[str, Any], *, source_root: Path = ROOT) -> dict[str, Any]:
    # Imported owner code and inspected source must be the same checkout. A
    # different --source-root must not attest code this process did not import.
    if source_root.resolve(strict=True) != ROOT.resolve(strict=True):
        raise ParityError("run the checker from the checkout being qualified")
    _exact(manifest, {
        "schema_version", "claim_scope", "policy_path", "policy_schema_version",
        "projection_source_sha256", "production_armed", "profiles",
    }, "manifest")
    if manifest["schema_version"] != SCHEMA or manifest["claim_scope"] != SCOPE:
        raise ParityError("unsupported schema or authority claim scope")
    if manifest["production_armed"] is not False:
        raise ParityError("manifest cannot grant production admission")
    if manifest["policy_path"] != POLICY:
        raise ParityError("manifest must consume the canonical production policy, not a fixture")
    registry = ExecutionCapabilityRegistry.load(
        _inside(source_root, POLICY), source_root=source_root,
    )
    if manifest["policy_schema_version"] != registry.schema_version:
        raise ParityError("canonical policy schema changed: requalify")
    projector_sha = hashlib.sha256(_inside(source_root, PROJECTOR).read_bytes()).hexdigest()
    if manifest["projection_source_sha256"] != projector_sha:
        raise ParityError("Claude projector source changed: requalify")
    rows = manifest["profiles"]
    if not isinstance(rows, Mapping) or set(rows) != set(registry.profiles):
        raise ParityError("canonical profile inventory changed: classify every profile explicitly")
    counts = {status: 0 for status in sorted(STATUSES)}
    for profile_id, profile in registry.profiles.items():
        row = rows[profile_id]
        _exact(row, {"profile_digest", "package_generation_digests", "surfaces"}, profile_id)
        expected = profile_expectation(registry, profile)
        if any(row[key] != value for key, value in expected.items()):
            raise ParityError(f"{profile_id}: canonical profile or package generation drift")
        surfaces = row["surfaces"]
        if not isinstance(surfaces, Mapping) or set(surfaces) != set(SURFACES):
            raise ParityError(f"{profile_id}: every Claude surface needs an explicit classification")
        for surface in SURFACES:
            entry = surfaces[surface]
            if not isinstance(entry, Mapping):
                raise ParityError(f"{profile_id}/{surface}: classification must be an object")
            status = entry.get("status")
            if not isinstance(status, str) or status not in STATUSES:
                raise ParityError(f"{profile_id}/{surface}: unsupported classification")
            fields = {"status", "reason"}
            if status == "configuration_supported":
                fields.add("projection")
            _exact(entry, fields, f"{profile_id}/{surface}")
            reason = entry["reason"]
            if not isinstance(reason, str) or not reason.strip():
                raise ParityError(f"{profile_id}/{surface}: an explicit reason is required")
            if status == "configuration_supported":
                expected_projection = projection_expectation(profile, surface)
                # Python equates False and 0; canonical JSON must distinguish
                # their types when comparing an exact security declaration.
                if _digest(entry["projection"]) != _digest(expected_projection):
                    raise ParityError(f"{profile_id}/{surface}: shipped projection drift")
            counts[status] += 1
    return {
        "schema_version": SCHEMA, "ok": True, "claim_scope": SCOPE,
        "profile_count": len(rows), "surface_counts": counts,
        "policy_digest": registry.policy_digest, "production_armed": False,
        "native_admission_proven": False, "observed_tool_catalog_attested": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--manifest", default=MANIFEST, help="repository-relative expectation file")
    args = parser.parse_args(argv)
    try:
        report = validate_manifest(
            load_manifest(_inside(args.source_root, args.manifest)), source_root=args.source_root,
        )
    except (ParityError, CapabilityPolicyError, ClaudeMcpProjectionError, OSError,
            UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "production_armed": False}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
