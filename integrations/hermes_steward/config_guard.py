#!/usr/bin/env python3
"""Static guard for the Hermes Steward read-only MCP consumer config.

The admitted shape is the pinned Hermes ``mcp_servers`` document at
NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18:
one remote server, ``tools.include`` as the whitelist, and
``tools.resources`` / ``tools.prompts`` disabled. Authorization is an
environment reference, never a literal token. This module does not start
Hermes, interpolate environment variables, or contact Steward.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from integrations.hermes_steward.client import ALLOWED_TOOLS, REQUIRED_SCOPE

SCHEMA = "mastermind.hermes_steward_mcp_config.v1"
HERMES_PIN = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
SERVER_NAME = "mastermind_steward"
_SERVER_KEYS = frozenset({"url", "headers", "tools", "timeout", "enabled"})
_TOOL_KEYS = frozenset({"include", "resources", "prompts"})
_ENV_REF = re.compile(r"^\$\{[A-Z][A-Z0-9_]+\}$")
_BEARER_ENV_REF = re.compile(r"^Bearer \$\{[A-Z][A-Z0-9_]+\}$")
_SECRET_KEY = re.compile(
    r"(^|_)(api_key|access_token|refresh_token|client_secret|password|private_key|bearer|secret|token)($|_)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/=-]{8,}|sk-[A-Za-z0-9]|xox[baprs]-|github_pat_|ghp_|eyJ[A-Za-z0-9_-]{8,})"
)
_WRITE_NAME = re.compile(
    r"(?i)(?:^|[._/-])(?:write|submit|create|update|delete|mutate|approve|"
    r"enqueue|dispatch|execute|post|put|patch)(?:$|[._/-])"
    r"|(?:write|submit|delete|mutate)"
)


def _preflight():
    path = (
        Path(__file__).resolve().parents[1]
        / "hermes_qualification"
        / "preflight.py"
    )
    spec = importlib.util.spec_from_file_location(
        "hermes_qualification_preflight", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("HERMES_QUALIFICATION_PREFLIGHT_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _secret_key_count(node: Any) -> int:
    count = 0
    if _is_mapping(node):
        for key, value in node.items():
            if _SECRET_KEY.search(key) and value not in (None, ""):
                count += 1
            else:
                count += _secret_key_count(value)
    elif isinstance(node, list):
        for item in node:
            count += _secret_key_count(item)
    return count


def _literal_secret_value(node: Any) -> bool:
    if isinstance(node, str):
        if _ENV_REF.fullmatch(node) or _BEARER_ENV_REF.fullmatch(node):
            return False
        return _SECRET_VALUE.search(node) is not None
    if _is_mapping(node):
        return any(_literal_secret_value(value) for value in node.values())
    if isinstance(node, list):
        return any(_literal_secret_value(item) for item in node)
    return False


def _load_unique_yaml(data: bytes) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PYYAML_NOT_INSTALLED: use the approved local environment; no auto-install"
        ) from exc
    if len(data) > 128 * 1024:
        raise ValueError("CONFIG_TOO_LARGE")
    try:
        for token in yaml.scan(data):
            if isinstance(
                token,
                (yaml.tokens.AnchorToken, yaml.tokens.AliasToken, yaml.tokens.TagToken),
            ):
                raise ValueError("YAML_ALIAS_ANCHOR_OR_TAG_NOT_ADMITTED")
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValueError("INVALID_YAML_TOKEN_STREAM") from exc

    class UniqueKeySafeLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):  # type: ignore[no-untyped-def]
            if not isinstance(node, yaml.MappingNode):
                raise yaml.constructor.ConstructorError(
                    None, None, "expected mapping", node.start_mark
                )
            result: dict[str, Any] = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise yaml.constructor.ConstructorError(
                        None, None, "non-string mapping key", key_node.start_mark
                    )
                if key in result:
                    raise yaml.constructor.ConstructorError(
                        None, None, "duplicate mapping key", key_node.start_mark
                    )
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        return yaml.load(data, Loader=UniqueKeySafeLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValueError("INVALID_UNIQUE_SAFE_YAML") from exc


def _mcp_issues(servers: Any) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    observations: dict[str, Any] = {
        "server_count": 0,
        "allowlist_count": 0,
        "extra_tool_count": 0,
        "missing_tools": list(ALLOWED_TOOLS),
        "write_tool_configured": False,
        "required_scope": REQUIRED_SCOPE,
    }
    if not _is_mapping(servers) or not servers:
        issues.append("MCP_SERVER_REQUIRED")
        return issues, observations
    observations["server_count"] = len(servers)
    if set(servers) != {SERVER_NAME}:
        issues.append("MCP_SERVER_NAME_REFUSED")
        return issues, observations
    entry = servers[SERVER_NAME]
    if not _is_mapping(entry):
        issues.append("MCP_SERVER_ENTRY_INVALID")
        return issues, observations
    if set(entry) - _SERVER_KEYS:
        issues.append("UNQUALIFIED_MCP_SERVER_KEY")
    if "command" in entry or "args" in entry or "env" in entry:
        issues.append("STDIO_COMMAND_NOT_ADMITTED")
    url = entry.get("url")
    if not isinstance(url, str) or _ENV_REF.fullmatch(url) is None:
        issues.append("MCP_URL_MUST_BE_ENV_REFERENCE")
    headers = entry.get("headers")
    if (
        not _is_mapping(headers)
        or set(headers) != {"Authorization"}
        or not isinstance(headers.get("Authorization"), str)
        or _BEARER_ENV_REF.fullmatch(headers.get("Authorization", "")) is None
    ):
        issues.append("AUTHORIZATION_MUST_BE_BEARER_ENV_REFERENCE")
    if "enabled" in entry and entry.get("enabled") is not True:
        issues.append("MCP_SERVER_DISABLED_OR_INVALID")
    timeout = entry.get("timeout", 30)
    if type(timeout) is not int or not 1 <= timeout <= 60:
        issues.append("MCP_TIMEOUT_REFUSED")
    tools = entry.get("tools")
    if not _is_mapping(tools) or set(tools) != _TOOL_KEYS:
        issues.append("MCP_TOOL_FILTER_INVALID")
        return issues, observations
    if tools.get("resources") is not False or tools.get("prompts") is not False:
        issues.append("MCP_RESOURCES_OR_PROMPTS_ENABLED")
    include = tools.get("include")
    if not isinstance(include, list) or any(not isinstance(name, str) for name in include):
        issues.append("TOOL_ALLOWLIST_MISMATCH")
        return issues, observations
    observations["allowlist_count"] = len(include)
    missing = [name for name in ALLOWED_TOOLS if name not in include]
    extra = [name for name in include if name not in ALLOWED_TOOLS]
    observations["missing_tools"] = missing
    observations["extra_tool_count"] = len(extra)
    if include != list(ALLOWED_TOOLS) or len(include) != len(set(include)):
        issues.append("TOOL_ALLOWLIST_MISMATCH")
    if any(_WRITE_NAME.search(name) for name in include):
        observations["write_tool_configured"] = True
        issues.append("WRITE_TOOL_CONFIGURED")
    return issues, observations


def inspect(config: Any, *, sha256: str) -> dict[str, Any]:
    """Inspect one decoded Hermes config. Values and secrets are not returned."""

    issues: list[str] = []
    observations: dict[str, Any] = {
        "hermes_pin": HERMES_PIN,
        "inline_secret_field_count": 0,
        "write_tool_configured": False,
        "allowlist": list(ALLOWED_TOOLS),
    }
    if not _is_mapping(config):
        issues.append("CONFIG_ROOT_NOT_MAPPING")
        config = {}
    if "mcp_servers" not in config:
        issues.append("MCP_SERVER_REQUIRED")
    secret_fields = _secret_key_count(config)
    observations["inline_secret_field_count"] = secret_fields
    if secret_fields:
        issues.append("INLINE_SECRET_FIELD")
    if _literal_secret_value(config):
        issues.append("LITERAL_SECRET_VALUE")

    base = {key: value for key, value in config.items() if key != "mcp_servers"}
    base_result = _preflight().inspect(base, sha256=sha256)
    issues.extend(base_result["issues"])
    mcp_issues, mcp_observations = _mcp_issues(config.get("mcp_servers"))
    issues.extend(mcp_issues)
    observations.update(
        {
            "server_count": mcp_observations["server_count"],
            "allowlist_count": mcp_observations["allowlist_count"],
            "extra_tool_count": mcp_observations["extra_tool_count"],
            "missing_tools": mcp_observations["missing_tools"],
            "write_tool_configured": mcp_observations["write_tool_configured"],
            "required_scope": REQUIRED_SCOPE,
            "base_status": base_result["status"],
        }
    )
    blocked = bool(issues) or observations["write_tool_configured"]
    return {
        "schema": SCHEMA,
        "status": "BLOCKED" if blocked else "PASS_OFFLINE_STEWARD_READ_CONFIG",
        "effect_expectation": "NONE",
        "identity_or_authority_granted": False,
        "hermes_started": False,
        "model_or_provider_called": False,
        "write_path_admitted": False,
        "runtime_security_verified": False,
        "network_contacted": False,
        "config_sha256": sha256,
        "issues": sorted(set(issues)),
        "observations": observations,
    }


def inspect_file(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    parsed = _load_unique_yaml(data)
    return inspect(parsed, sha256=hashlib.sha256(data).hexdigest())


# The CLI is a public boundary, not a generic dump of an internal inspector.
# New fields/reasons require an explicit review of this closed output contract.
_PUBLIC_ISSUES = frozenset({
    "CONFIG_ROOT_NOT_MAPPING", "MCP_SERVER_REQUIRED", "MCP_SERVER_NAME_REFUSED",
    "MCP_SERVER_ENTRY_INVALID", "UNQUALIFIED_MCP_SERVER_KEY", "STDIO_COMMAND_NOT_ADMITTED",
    "MCP_URL_MUST_BE_ENV_REFERENCE", "AUTHORIZATION_MUST_BE_BEARER_ENV_REFERENCE",
    "MCP_SERVER_DISABLED_OR_INVALID", "MCP_TIMEOUT_REFUSED", "MCP_TOOL_FILTER_INVALID",
    "MCP_RESOURCES_OR_PROMPTS_ENABLED", "TOOL_ALLOWLIST_MISMATCH", "WRITE_TOOL_CONFIGURED",
    "INLINE_SECRET_FIELD", "LITERAL_SECRET_VALUE", "UNQUALIFIED_TOP_LEVEL_SECTION",
    "INVALID_TOP_LEVEL_KEY", "AGENT_SECTION_INVALID", "UNQUALIFIED_AGENT_OPTION",
    "GLOBAL_DISABLED_TOOLSETS_REQUIRED", "DUPLICATE_DISABLED_TOOLSET",
    "UNRECOGNIZED_DISABLED_TOOLSET", "DANGEROUS_TOOLSET_NOT_GLOBALLY_DISABLED",
    "EXPLICIT_CLARIFY_ONLY_TOOLSETS_REQUIRED", "PLATFORM_TOOLSETS_UNQUALIFIED",
    "CUSTOM_TOOLSETS_NOT_ADMITTED", "PLUGINS_NOT_ADMITTED", "MCP_SERVERS_NOT_ADMITTED",
    "TOOLS_NOT_ADMITTED", "GATEWAY_NOT_ADMITTED", "SCHEDULER_NOT_ADMITTED",
    "UNQUALIFIED_MODEL_ROUTE", "UNQUALIFIED_AUXILIARY_OPTION",
    "UNQUALIFIED_VISION_ROUTE", "NESTED_PROFILES_NOT_ADMITTED",
})
_PUBLIC_FALSE_FLAGS = frozenset({
    "identity_or_authority_granted", "hermes_started", "model_or_provider_called",
    "write_path_admitted", "runtime_security_verified", "network_contacted",
})
_PUBLIC_TOP_KEYS = _PUBLIC_FALSE_FLAGS | {
    "schema", "status", "effect_expectation", "config_sha256", "issues", "observations",
}
_PUBLIC_COUNTS = frozenset({
    "inline_secret_field_count", "server_count", "allowlist_count", "extra_tool_count",
})
_PUBLIC_OBSERVATION_KEYS = _PUBLIC_COUNTS | {
    "hermes_pin", "write_tool_configured", "allowlist", "missing_tools",
    "required_scope", "base_status",
}


def public_report(result: Any) -> dict[str, Any]:
    """Validate and reconstruct only the public structural evidence fields.

    No raw config, free-form message, endpoint, environment value or future
    inspector field can reach stdout. A changed internal shape fails closed.
    """
    invalid = "PUBLIC_REPORT_CONTRACT_INVALID"
    if type(result) is not dict or set(result) != _PUBLIC_TOP_KEYS:
        raise ValueError(invalid)
    if (result["schema"] != SCHEMA or result["effect_expectation"] != "NONE"
            or any(result[key] is not False for key in _PUBLIC_FALSE_FLAGS)):
        raise ValueError(invalid)
    obs = result["observations"]
    if type(obs) is not dict or set(obs) != _PUBLIC_OBSERVATION_KEYS:
        raise ValueError(invalid)
    if (obs["hermes_pin"] != HERMES_PIN or obs["required_scope"] != REQUIRED_SCOPE
            or type(obs["allowlist"]) is not list or obs["allowlist"] != list(ALLOWED_TOOLS)
            or type(obs["write_tool_configured"]) is not bool):
        raise ValueError(invalid)
    for name in _PUBLIC_COUNTS:
        if type(obs[name]) is not int or not 0 <= obs[name] <= 128 * 1024:
            raise ValueError(invalid)
    missing = obs["missing_tools"]
    issues = result["issues"]
    if (type(missing) is not list or len(missing) > len(ALLOWED_TOOLS)
            or any(type(name) is not str or name not in ALLOWED_TOOLS for name in missing)
            or len(missing) != len(set(missing))
            or type(issues) is not list or len(issues) > len(_PUBLIC_ISSUES)
            or any(type(code) is not str or code not in _PUBLIC_ISSUES for code in issues)
            or len(issues) != len(set(issues))):
        raise ValueError(invalid)
    digest = result["config_sha256"]
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError(invalid)
    if obs["base_status"] == "BLOCKED":
        base_status = "BLOCKED"
    elif obs["base_status"] == "PASS_OFFLINE_POLICY_ONLY":
        base_status = "PASS_OFFLINE_POLICY_ONLY"
    else:
        raise ValueError(invalid)
    blocked = bool(issues) or obs["write_tool_configured"] is True
    status = "BLOCKED" if blocked else "PASS_OFFLINE_STEWARD_READ_CONFIG"
    if result["status"] != status:
        raise ValueError(invalid)
    return {
        "schema": SCHEMA,
        "status": status,
        "effect_expectation": "NONE",
        "identity_or_authority_granted": False,
        "hermes_started": False,
        "model_or_provider_called": False,
        "write_path_admitted": False,
        "runtime_security_verified": False,
        "network_contacted": False,
        "config_sha256": digest,
        "issues": sorted(code for code in _PUBLIC_ISSUES if code in issues),
        "observations": {
            "hermes_pin": HERMES_PIN,
            "inline_secret_field_count": int(obs["inline_secret_field_count"]),
            "write_tool_configured": obs["write_tool_configured"] is True,
            "allowlist": list(ALLOWED_TOOLS),
            "server_count": int(obs["server_count"]),
            "allowlist_count": int(obs["allowlist_count"]),
            "extra_tool_count": int(obs["extra_tool_count"]),
            "missing_tools": [name for name in ALLOWED_TOOLS if name in missing],
            "required_scope": REQUIRED_SCOPE,
            "base_status": base_status,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Hermes Steward MCP config guard")
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = public_report(inspect_file(args.config))
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "INPUT_REFUSED", "reason": type(exc).__name__}))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS_OFFLINE_STEWARD_READ_CONFIG" else 2


if __name__ == "__main__":
    sys.exit(main())
