"""Reviewed stock Playwright-extension broker plan for shared human Chrome.

This module performs no install, browser connection, profile selection, token
read, process launch, admission, placement, grant issuance, or effect. It pins
only the already-reviewed Playwright MCP generation and verifies that extension
mode exposes the exact same Browser tool schemas used by the incumbent owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

from control_plane.executive_agent_capabilities import (
    observed_mcp_tool_schema_digest,
)

EXPECTED_MCP_VERSION = "0.0.79"
EXPECTED_TOOL_SCHEMA_DIGEST = (
    "ea956fcbb62baedc543f0e8bf299b0a59bdaa30f7c5808faf1ca32a5e9094730"
)
EXTENSION_ID = "mmlmfjhmonkocbjadbfplnigmagldckm"

ALLOWED_TOOLS = frozenset(
    {
        "browser_click",
        "browser_close",
        "browser_console_messages",
        "browser_fill_form",
        "browser_hover",
        "browser_navigate",
        "browser_network_requests",
        "browser_press_key",
        "browser_select_option",
        "browser_snapshot",
        "browser_tabs",
        "browser_take_screenshot",
        "browser_type",
        "browser_wait_for",
    }
)


class ExtensionModeError(ValueError):
    """The reviewed Playwright extension-mode contract does not match."""


def _absolute(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not value.startswith("/")
        or value == "/"
        or "\x00" in value
    ):
        raise ExtensionModeError(f"{field} is invalid")
    path = PurePosixPath(value)
    if "." in path.parts or ".." in path.parts or str(path) != value.rstrip("/"):
        raise ExtensionModeError(f"{field} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class ExtensionBrokerPlan:
    node_executable: str
    mcp_cli_path: str
    output_dir: str
    argv: tuple[str, ...]
    mcp_version: str
    extension_id: str
    expected_tool_schema_digest: str
    requires_user_approval: bool = True
    one_broker_connection_per_profile: bool = True
    requires_single_enrolled_profile_per_host: bool = True

    @property
    def is_admission(self) -> bool:
        return False

    @property
    def is_installation(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "mastermind.browser_playwright_extension_plan.v1",
            "command": self.node_executable,
            "argv": list(self.argv),
            "mcp_version": self.mcp_version,
            "extension_id": self.extension_id,
            "expected_tool_schema_digest": self.expected_tool_schema_digest,
            "requires_user_approval": True,
            "one_broker_connection_per_profile": True,
            "requires_single_enrolled_profile_per_host": True,
            "is_admission": False,
            "is_installation": False,
            "authority": {
                "plan_is_authority": False,
                "may_install_extension": False,
                "may_choose_profile": False,
                "may_choose_tab": False,
                "may_read_extension_token": False,
                "may_mint_tab_grant": False,
                "may_start_browser_effect": False,
            },
        }


@dataclass(frozen=True, slots=True)
class ExtensionCatalogAttestation:
    tool_schema_digest: str
    allowed_tools: tuple[str, ...]

    @property
    def is_admission(self) -> bool:
        return False


def build_extension_broker_plan(
    *,
    node_executable: object,
    mcp_cli_path: object,
    output_dir: object,
    installed_mcp_version: object,
) -> ExtensionBrokerPlan:
    node = _absolute(node_executable, "node_executable")
    cli = _absolute(mcp_cli_path, "mcp_cli_path")
    output = _absolute(output_dir, "output_dir")
    if not cli.endswith("/node_modules/@playwright/mcp/cli.js"):
        raise ExtensionModeError("mcp_cli_path is not the reviewed Playwright MCP entrypoint")
    if type(installed_mcp_version) is not str or installed_mcp_version != EXPECTED_MCP_VERSION:
        raise ExtensionModeError("Playwright MCP version is not reviewed")

    # Initial shared-human enrollment deliberately uses Playwright's visible
    # connection approval + tab picker. Pinned 0.0.79 has no profile selector
    # or extension-token binding, so the host owner may grant this mode only
    # when exactly one Chrome profile on that host is extension-enrolled. One
    # long-lived broker client then multiplexes separately authorized Mastermind
    # callers above the selected tab group. Multiple enrolled profiles on one
    # host require a later reviewed runtime with exact profile selection.
    argv = (
        cli,
        "--browser",
        "chrome",
        "--extension",
        "--output-dir",
        output,
    )
    return ExtensionBrokerPlan(
        node_executable=node,
        mcp_cli_path=cli,
        output_dir=output,
        argv=argv,
        mcp_version=EXPECTED_MCP_VERSION,
        extension_id=EXTENSION_ID,
        expected_tool_schema_digest=EXPECTED_TOOL_SCHEMA_DIGEST,
    )


def attest_extension_catalog(value: object) -> ExtensionCatalogAttestation:
    if type(value) is not dict or set(value) != {"tools"}:
        raise ExtensionModeError("extension catalog is invalid")
    rows = value["tools"]
    if type(rows) is not list or not rows:
        raise ExtensionModeError("extension catalog is invalid")
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ExtensionModeError("extension catalog is invalid")
        name = row.get("name")
        schema = row.get("inputSchema")
        if (
            type(name) is not str
            or name in by_name
            or not isinstance(schema, Mapping)
        ):
            raise ExtensionModeError("extension catalog is invalid")
        by_name[name] = dict(row)
    if not ALLOWED_TOOLS <= set(by_name):
        raise ExtensionModeError("extension catalog lacks a reviewed tool")
    selected = {
        "tools": {name: by_name[name] for name in sorted(ALLOWED_TOOLS)}
    }
    digest = observed_mcp_tool_schema_digest(selected)
    if digest != EXPECTED_TOOL_SCHEMA_DIGEST:
        raise ExtensionModeError("extension tool schema drift")
    return ExtensionCatalogAttestation(
        tool_schema_digest=digest,
        allowed_tools=tuple(sorted(ALLOWED_TOOLS)),
    )


__all__ = [
    "ALLOWED_TOOLS",
    "EXPECTED_MCP_VERSION",
    "EXPECTED_TOOL_SCHEMA_DIGEST",
    "EXTENSION_ID",
    "ExtensionBrokerPlan",
    "ExtensionCatalogAttestation",
    "ExtensionModeError",
    "attest_extension_catalog",
    "build_extension_broker_plan",
]
