"""Additive Web CEO v3 profile with read-only MDM telemetry.

Legacy, web_ceo_v1 and web_ceo_v2 contracts remain unchanged.  V3 adds one
sensor-only tool; it does not add lifecycle, placement, retry or MDM command
authority.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from integrations.executive_mcp import schemas as legacy
from integrations.executive_mcp import web_ceo as v2

WEB_CEO_V3_PROFILE = "web_ceo_v3"
WEB_CEO_V3_SERVER_NAME = legacy.SERVER_NAME
WEB_CEO_V3_SERVER_VERSION = "1.3.0"
MDM_TOOL_NAME = "executive_mdm"

MDM_TOOL_SPEC = legacy.ToolSpec(
    name=MDM_TOOL_NAME,
    description=(
        "Read-only external MDM telemetry from the configured Mosyle Business "
        "sensor. view=fleet returns the bounded macOS inventory; view=device "
        "selects exactly one Mac by serial_number or hostname. This tool does "
        "not dispatch, restart, wipe, lock, update, assign, install, or mutate "
        "any Mac or Executive OS state. Mosyle unavailability is telemetry "
        "unavailability and must never be interpreted as a Mac being offline."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "view": {"type": "string", "enum": ["fleet", "device"]},
            "serial_number": {"type": "string", "minLength": 1, "maxLength": 128},
            "hostname": {"type": "string", "minLength": 1, "maxLength": 256},
        },
        "required": ["view"],
        "additionalProperties": False,
        "oneOf": [
            {
                "properties": {
                    "view": {"const": "fleet"},
                    "serial_number": False,
                    "hostname": False,
                }
            },
            {
                "properties": {"view": {"const": "device"}},
                "oneOf": [
                    {"required": ["serial_number"], "properties": {"hostname": False}},
                    {"required": ["hostname"], "properties": {"serial_number": False}},
                ],
            },
        ],
    },
    output_description=(
        "mastermind.executive_mcp_result.v1 envelope containing a bounded "
        "mastermind.mosyle_fleet_snapshot.v1 or mastermind.mosyle_device.v1 "
        "observation. Credentials and non-allowlisted Mosyle fields are absent."
    ),
    read_only=True,
)

if v2.WEB_CEO_V2_TOOL_SPECS[-1].name != legacy.MODIFYING_TOOL:
    raise RuntimeError("Web CEO v2 modifying-tool position changed")

WEB_CEO_V3_TOOL_SPECS = (
    v2.WEB_CEO_V2_TOOL_SPECS[:-1] + (MDM_TOOL_SPEC,) + v2.WEB_CEO_V2_TOOL_SPECS[-1:]
)
_BY_NAME = {spec.name: spec for spec in WEB_CEO_V3_TOOL_SPECS}


def web_ceo_v3_tool_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in WEB_CEO_V3_TOOL_SPECS)


def web_ceo_v3_tool_spec(name: str) -> legacy.ToolSpec:
    spec = _BY_NAME.get(name)
    if spec is None:
        raise legacy.GatewayError("not_found", f"unknown tool {name!r}")
    return spec


def validate_web_ceo_v3_tool_arguments(
    tool_name: str, arguments: Any
) -> dict[str, Any]:
    if tool_name != MDM_TOOL_NAME:
        return v2.validate_web_ceo_v2_tool_arguments(tool_name, arguments)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise legacy.GatewayError("invalid_input", "arguments must be an object")
    raw = legacy.canonical_json({"arguments": arguments})
    if len(raw) > legacy.MAX_REQUEST_BYTES:
        raise legacy.GatewayError(
            "invalid_input",
            f"request is {len(raw)} bytes, over the {legacy.MAX_REQUEST_BYTES}-byte ceiling",
        )
    legacy._exact_keys(
        arguments,
        "arguments",
        frozenset({"view"}),
        frozenset({"serial_number", "hostname"}),
    )
    view = legacy._plain_text(arguments["view"], "view", max_chars=6)
    if view == "fleet":
        if "serial_number" in arguments or "hostname" in arguments:
            raise legacy.GatewayError(
                "invalid_input", "device selectors are valid only when view=device"
            )
        return {"view": "fleet"}
    if view != "device":
        raise legacy.GatewayError("invalid_input", "view must be 'fleet' or 'device'")
    has_serial = "serial_number" in arguments
    has_hostname = "hostname" in arguments
    if has_serial == has_hostname:
        raise legacy.GatewayError(
            "invalid_input",
            "view=device requires exactly one of serial_number or hostname",
        )
    if has_serial:
        return {
            "view": "device",
            "serial_number": legacy._plain_text(
                arguments["serial_number"], "serial_number", max_chars=128
            ),
        }
    return {
        "view": "device",
        "hostname": legacy._plain_text(
            arguments["hostname"], "hostname", max_chars=256
        ),
    }


def web_ceo_v3_schema_snapshot() -> dict[str, Any]:
    return {
        "server_name": WEB_CEO_V3_SERVER_NAME,
        "server_version": WEB_CEO_V3_SERVER_VERSION,
        "result_schema": legacy.RESULT_SCHEMA,
        "profile": WEB_CEO_V3_PROFILE,
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "output_description": spec.output_description,
                "annotations": spec.annotations,
                "read_only": spec.read_only,
            }
            for spec in WEB_CEO_V3_TOOL_SPECS
        ],
    }


def web_ceo_v3_schema_snapshot_sha256() -> str:
    return hashlib.sha256(
        legacy.canonical_json(web_ceo_v3_schema_snapshot())
    ).hexdigest()


# Filled from the deterministic snapshot by the implementation test.
WEB_CEO_V3_SCHEMA_SNAPSHOT_SHA256 = "07be259eaf9df920bd68b542b0e38793c606d14f89736ca11b928d621b34e333"


def validate_installed_mcp_profile_current(value: Any = "legacy") -> str:
    """Current installed selector; older v2 validator remains frozen."""
    if type(value) is str and value in {
        v2.INSTALLED_MCP_PROFILE_LEGACY,
        v2.WEB_CEO_V2_PROFILE,
        WEB_CEO_V3_PROFILE,
    }:
        return value
    raise ValueError("installed Executive MCP profile is invalid")
