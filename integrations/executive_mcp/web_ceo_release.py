"""Opt-in composition of the unchanged v2 and release-control tool contracts."""
from __future__ import annotations

from typing import Any

from integrations.executive_mcp.release_control import (
    RELEASE_CONTROL_TOOL_SPECS, validate_release_tool_arguments,
)
from integrations.executive_mcp.web_ceo import (
    WEB_CEO_V2_SERVER_NAME, WEB_CEO_V2_SERVER_VERSION, WEB_CEO_V2_TOOL_SPECS,
    validate_web_ceo_v2_tool_arguments,
)

WEB_CEO_RELEASE_PROFILE = "web_ceo_release_v1"
WEB_CEO_RELEASE_SERVER_NAME = WEB_CEO_V2_SERVER_NAME
WEB_CEO_RELEASE_SERVER_VERSION = WEB_CEO_V2_SERVER_VERSION
WEB_CEO_RELEASE_TOOL_SPECS = WEB_CEO_V2_TOOL_SPECS + RELEASE_CONTROL_TOOL_SPECS
_RELEASE_NAMES = frozenset(spec.name for spec in RELEASE_CONTROL_TOOL_SPECS)
_NAMES = tuple(spec.name for spec in WEB_CEO_RELEASE_TOOL_SPECS)
if len(_NAMES) != len(set(_NAMES)):
    raise RuntimeError("combined Executive profile contains duplicate tool names")


def validate_web_ceo_release_tool_arguments(name: str, arguments: Any) -> dict[str, Any]:
    """Use the existing closed validator belonging to each statically named tool."""
    if name in _RELEASE_NAMES:
        return validate_release_tool_arguments(name, arguments)
    return validate_web_ceo_v2_tool_arguments(name, arguments)
