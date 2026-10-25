#!/usr/bin/env python3
"""Offline-only, fail-closed Hermes *candidate* configuration qualification.

This checker is a pre-execution static guard, NOT a runtime sandbox, authority grant,
model/provider attestation, or replacement for Mastermind receiving-service policy.
It neither starts Hermes nor opens any network connection nor loads .env files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "mastermind.hermes_candidate_preflight.v1"
REQUIRED_DISABLED = frozenset({
    "terminal", "file", "browser", "computer_use", "code_execution",
    "delegation", "cronjob", "memory", "session_search", "skills",
    "messaging", "discord", "discord_admin", "kanban", "image_gen",
    "web", "vision", "tts", "debugging",
})
ALLOWED_ENABLED = frozenset({"clarify"})
ALLOWED_TOP_LEVEL = frozenset({"agent", "model", "auxiliary", "toolsets"})
SECRET_KEY_PATTERN = re.compile(
    r"(^|_)(api_key|access_token|refresh_token|client_secret|password|private_key|bearer|secret|token)($|_)",
    re.IGNORECASE,
)


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) for k in value)


def _list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _secret_paths(node: Any, prefix: str = "") -> list[str]:
    out: list[str] = []
    if _is_mapping(node):
        for key, value in node.items():
            here = f"{prefix}.{key}" if prefix else key
            if SECRET_KEY_PATTERN.search(key) and value not in (None, ""):
                out.append(here)
            else:
                out.extend(_secret_paths(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_secret_paths(value, f"{prefix}[{index}]"))
    return out


def inspect(config: Any, *, sha256: str) -> dict[str, Any]:
    """Inspect decoded YAML; include only structural facts, never input values/secrets."""
    issues: list[str] = []
    observations: dict[str, Any] = {}
    if not _is_mapping(config):
        issues.append("CONFIG_ROOT_NOT_MAPPING")
        config = {}

    # Qualification profile is intentionally minimal: unreviewed top-level
    # options must not silently activate capabilities in a newer Hermes build.
    if set(config) - ALLOWED_TOP_LEVEL:
        issues.append("UNQUALIFIED_TOP_LEVEL_SECTION")
    if any(not isinstance(key, str) for key in config):
        issues.append("INVALID_TOP_LEVEL_KEY")

    secret_paths = _secret_paths(config)
    if secret_paths:
        issues.append("INLINE_SECRET_FIELD")
    observations["inline_secret_field_count"] = len(secret_paths)

    agent = config.get("agent", {})
    if not _is_mapping(agent):
        agent = {}
        issues.append("AGENT_SECTION_INVALID")
    if set(agent) - {"disabled_toolsets"}:
        issues.append("UNQUALIFIED_AGENT_OPTION")
    disabled = agent.get("disabled_toolsets")
    if not _list_of_strings(disabled):
        issues.append("GLOBAL_DISABLED_TOOLSETS_REQUIRED")
        disabled_set: set[str] = set()
    else:
        disabled_set = set(disabled)
        if len(disabled_set) != len(disabled):
            issues.append("DUPLICATE_DISABLED_TOOLSET")
    missing = sorted(REQUIRED_DISABLED - disabled_set)
    if missing:
        issues.append("DANGEROUS_TOOLSET_NOT_GLOBALLY_DISABLED")
    observations["required_disabled_toolsets_count"] = len(REQUIRED_DISABLED)
    observations["missing_disabled_toolsets"] = missing

    toolsets = config.get("toolsets")
    if not _list_of_strings(toolsets) or not toolsets or set(toolsets) - ALLOWED_ENABLED:
        issues.append("EXPLICIT_CLARIFY_ONLY_TOOLSETS_REQUIRED")
    if config.get("platform_toolsets") not in (None, {}):
        issues.append("PLATFORM_TOOLSETS_UNQUALIFIED")
    for forbidden in ("custom_toolsets", "plugins", "mcp_servers", "tools"):
        if config.get(forbidden) not in (None, {}, []):
            issues.append(f"{forbidden.upper()}_NOT_ADMITTED")

    # A disabled toolset does not prove that a remote, custom, or bundled plugin
    # cannot act. The first canary admits no configured MCP/plugin or actor at all.
    if config.get("gateway") not in (None, {}):
        issues.append("GATEWAY_NOT_ADMITTED")
    if config.get("cron") not in (None, {}):
        issues.append("SCHEDULER_NOT_ADMITTED")

    model = config.get("model")
    if not _is_mapping(model) or set(model) - {"provider", "default"} or model.get("provider") != "zai" or model.get("default") not in ("glm-5.3", "glm-5.3-flash"):
        issues.append("UNQUALIFIED_MODEL_ROUTE")
    auxiliary = config.get("auxiliary", {})
    if not _is_mapping(auxiliary) or set(auxiliary) - {"vision"}:
        issues.append("UNQUALIFIED_AUXILIARY_OPTION")
    vision = auxiliary.get("vision", {}) if _is_mapping(auxiliary) else {}
    if not _is_mapping(vision) or set(vision) - {"provider", "model"} or vision.get("provider") != "zai" or vision.get("model") != "glm-5.3-flash":
        issues.append("UNQUALIFIED_VISION_ROUTE")

    # All extensions and dynamic MCP tools remain disallowed; static profiles
    # are not a source of permissions or an assurance of actual tool registration.
    if config.get("profiles") not in (None, {}, []):
        issues.append("NESTED_PROFILES_NOT_ADMITTED")

    result = {
        "schema": SCHEMA,
        "status": "BLOCKED" if issues else "PASS_OFFLINE_POLICY_ONLY",
        "effect_expectation": "NONE",
        "identity_or_authority_granted": False,
        "hermes_started": False,
        "model_or_provider_called": False,
        "actual_registered_tools_verified": False,
        "runtime_security_verified": False,
        "config_sha256": sha256,
        "issues": sorted(set(issues)),
        "observations": observations,
    }
    return result


def inspect_file(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PYYAML_NOT_INSTALLED: use approved local environment; no auto-install") from exc
    data = path.read_bytes()
    # Do not follow arbitrary large files or input streams; this is a local config audit.
    if len(data) > 128 * 1024:
        raise ValueError("CONFIG_TOO_LARGE")
    try:
        parsed = yaml.safe_load(data)
    except yaml.YAMLError as exc:
        raise ValueError("INVALID_SAFE_YAML") from exc
    return inspect(parsed, sha256=hashlib.sha256(data).hexdigest())


def _atomic_new_receipt(path: Path, payload: dict[str, Any]) -> None:
    # Never replace an earlier observation. Private receipt with no source content.
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, sort_keys=True)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
    except BaseException:
        # Preserve a failed/partial receipt for explicit reconciliation;
        # never unlink it here and implicitly permit a blind retry.
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_file(args.config)
        _atomic_new_receipt(args.receipt, result)
    except (OSError, RuntimeError, ValueError) as exc:
        # Do not include parser exception details: errors can contain secrets/paths.
        print(f"PRECHECK_FAILURE:{type(exc).__name__}", file=sys.stderr)
        return 3
    print(json.dumps({"schema": SCHEMA, "status": result["status"], "receipt_written": True}))
    return 0 if result["status"] == "PASS_OFFLINE_POLICY_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
