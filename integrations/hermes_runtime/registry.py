"""Enabled Hermes tools must equal the profile allowlist, and stderr must be empty.

Disabled rows are part of the census so a truncated listing cannot hide an
enabled tool. They are not registered. Extension names come from in-process
sibling registrars and must equal the allowlist entries that are not Hermes
built-ins. This process-local table is not a company tool authority.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re

from .constants import (
    ADMITTED_HERMES_TOOLSETS,
    KNOWN_HERMES_TOOLSETS,
    REFUSED_HERMES_TOOLSETS,
    REGISTRY_SCHEMA,
)
from .errors import RuntimeRefusal
from .profile import RuntimeProfile

ANSI = re.compile(r"\x1b\[[0-9;]*m")
TOOL_LINE = re.compile(r"^\s*([✓✗])\s+(enabled|disabled)\s+([a-z][a-z0-9_-]{0,63})(?:\s|$)")
HEADINGS = {"Built-in toolsets (cli):": "builtins", "Plugin toolsets (cli):": "plugins"}
MCP_HEADER = "MCP servers:"
MCP_ROW = re.compile(r"^([a-z][a-z0-9_]{0,63})  \[include only: (.+)\]$")

_REGISTRARS: dict[str, Callable[[RuntimeProfile], frozenset[str]]] = {}


def register_extension_tools(source: str, provider: Callable[[RuntimeProfile], frozenset[str]]) -> None:
    if not isinstance(source, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,32}", source):
        raise RuntimeRefusal("EXTENSION_SOURCE_INVALID")
    if source in _REGISTRARS:
        raise RuntimeRefusal("DUPLICATE_EXTENSION_SOURCE")
    if not callable(provider):
        raise RuntimeRefusal("EXTENSION_SOURCE_INVALID")
    _REGISTRARS[source] = provider


def clear_extension_tools() -> None:
    _REGISTRARS.clear()


def extension_tools_for(profile: RuntimeProfile) -> frozenset[str]:
    found: set[str] = set()
    for provider in _REGISTRARS.values():
        try:
            names = provider(profile)
        except RuntimeRefusal:
            raise
        except Exception:
            raise RuntimeRefusal("EXTENSION_SOURCE_FAILED") from None
        if not isinstance(names, frozenset) or not all(isinstance(name, str) for name in names):
            raise RuntimeRefusal("EXTENSION_SOURCE_FAILED")
        if names & KNOWN_HERMES_TOOLSETS:
            raise RuntimeRefusal("EXTENSION_TOOL_COLLIDES_WITH_HERMES")
        overlap = found & set(names)
        if overlap:
            raise RuntimeRefusal("DUPLICATE_EXTENSION_TOOL")
        found.update(names)
    return frozenset(found)


def inspect_tool_registry(
    tool_list: str,
    stderr: str | bytes | None,
    allowlist: Iterable[str],
    extension_tools: Iterable[str] = (),
    *,
    expected_disabled_mcp: Mapping[str, tuple[str, ...]] | None = None,
) -> dict:
    issues: set[str] = set()
    stderr_empty = False
    if stderr is None:
        issues.add("STDERR_NOT_OBSERVED")
    elif isinstance(stderr, bytes):
        stderr_empty = stderr == b""
        if not stderr_empty:
            issues.add("STDERR_NOT_EMPTY")
    elif isinstance(stderr, str):
        stderr_empty = stderr == ""
        if not stderr_empty:
            issues.add("STDERR_NOT_EMPTY")
    else:
        issues.add("STDERR_NOT_OBSERVED")

    if not isinstance(tool_list, str):
        issues.add("TOOL_LIST_NOT_TEXT")
        tool_list = ""

    enabled, observed, parse_issues = _parse_enabled(tool_list, expected_disabled_mcp)
    issues.update(parse_issues)
    allow = frozenset(allowlist)
    extensions = frozenset(extension_tools)
    hermes_allow = allow & KNOWN_HERMES_TOOLSETS
    extension_allow = allow - KNOWN_HERMES_TOOLSETS
    if enabled != hermes_allow:
        issues.add("ALLOWLIST_REGISTERED_MISMATCH")
    if extensions != extension_allow:
        issues.add("EXTENSION_ALLOWLIST_MISMATCH")
    if observed != KNOWN_HERMES_TOOLSETS:
        if observed - KNOWN_HERMES_TOOLSETS:
            issues.add("UPSTREAM_TOOLSET_DRIFT")
        if KNOWN_HERMES_TOOLSETS - observed:
            issues.add("INCOMPLETE_TOOLSET_REGISTRY")
    if enabled & REFUSED_HERMES_TOOLSETS:
        issues.add("REFUSED_TOOLSET_ENABLED")
    if hermes_allow - ADMITTED_HERMES_TOOLSETS:
        issues.add("REFUSED_TOOLSET")

    registered = enabled | extensions
    return {
        "schema": REGISTRY_SCHEMA,
        "status": "BLOCKED" if issues else "PASS_REGISTRY_EXACT",
        "issues": sorted(issues),
        "registered": sorted(registered),
        "allowlist": sorted(allow),
        "stderr_empty": stderr_empty,
        "effect_expectation": "NONE",
        "upstream_attested": False,
        "receiving_service_policy_verified": False,
    }


def assert_registered_tools_exact(
    tool_list: str,
    stderr: str | bytes | None,
    allowlist: Iterable[str],
    extension_tools: Iterable[str] = (),
    *,
    expected_disabled_mcp: Mapping[str, tuple[str, ...]] | None = None,
) -> dict:
    result = inspect_tool_registry(tool_list, stderr, allowlist, extension_tools,
                                   expected_disabled_mcp=expected_disabled_mcp)
    if result["status"] != "PASS_REGISTRY_EXACT":
        raise RuntimeRefusal(",".join(result["issues"]) or "REGISTRY_BLOCKED")
    if set(result["registered"]) != set(result["allowlist"]) or not result["stderr_empty"]:
        raise RuntimeRefusal("ALLOWLIST_REGISTERED_MISMATCH")
    return result


def _parse_enabled(
    text: str,
    expected_disabled_mcp: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[set[str], set[str], set[str]]:
    issues: set[str] = set()
    enabled: set[str] = set()
    observed: set[str] = set()
    section: str | None = None
    seen: dict[str, set[str]] = {"builtins": set(), "plugins": set()}
    seen_mcp: set[str] = set()
    saw_mcp_heading = False
    for raw in ANSI.sub("", text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in HEADINGS:
            if section == "mcp":
                issues.add("TOOLSET_AFTER_MCP_SECTION")
            section = HEADINGS[line]
            continue
        if line == MCP_HEADER:
            if saw_mcp_heading or section != "plugins":
                issues.add("UNEXPECTED_MCP_SECTION")
            saw_mcp_heading = True
            section = "mcp"
            continue
        if section == "mcp":
            match = MCP_ROW.fullmatch(line)
            if match is None or expected_disabled_mcp is None:
                issues.add("UNQUALIFIED_MCP_SUMMARY")
                continue
            name, tools = match.groups()
            if name in seen_mcp:
                issues.add("DUPLICATE_MCP_SERVER")
            seen_mcp.add(name)
            expected = expected_disabled_mcp.get(name)
            if expected is None or tools != ", ".join(expected):
                issues.add("MCP_SERVER_SUMMARY_MISMATCH")
            continue
        if section is None:
            issues.add("UNEXPECTED_OUTPUT_PREAMBLE")
            continue
        match = TOOL_LINE.match(line)
        if not match:
            issues.add("UNRECOGNIZED_TOOL_ROW_OR_SECTION")
            continue
        icon, state, name = match.groups()
        if (icon == "✓") != (state == "enabled"):
            issues.add("INCONSISTENT_TOOL_STATUS")
        if name in seen[section]:
            issues.add("DUPLICATE_TOOLSET")
        seen[section].add(name)
        observed.add(name)
        if state == "enabled":
            enabled.add(name)
    if not seen["builtins"] or not seen["plugins"]:
        issues.add("INCOMPLETE_TOOLSET_REGISTRY")
    if expected_disabled_mcp is None:
        if saw_mcp_heading:
            issues.add("UNEXPECTED_MCP_SECTION")
    elif not saw_mcp_heading or seen_mcp != set(expected_disabled_mcp):
        issues.add("INCOMPLETE_MCP_SUMMARY")
    return enabled, observed, issues
