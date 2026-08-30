from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import mcp.types as mcp_types
import pytest
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

from integrations.mastermind_surface_probe.probe import HostContextProbeConfig
from integrations.mastermind_surface_probe.schemas import (
    CONTRACT_DIGEST,
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_ANNOTATIONS,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    TOOL_TITLE,
)
from integrations.mastermind_surface_probe.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MCP_PATH,
    RUNTIME_SCHEMA,
    build_mcp_server,
    build_streamable_http_app,
    build_tools,
    describe_runtime,
    initialization_options,
    load_runtime_configuration,
)


ROOT = Path(__file__).resolve().parents[1]
FIXED_NOW = datetime(2026, 8, 30, 4, 30, tzinfo=UTC)
RAW_META = {
    "openai/session": "session-secret-correlate-001",
    "openai/subject": "subject-secret-correlate-001",
    "openai/organization": "organization-secret-correlate-001",
    "openai/locale": "en-US",
    "openai/userAgent": "ChatGPT-Business-Test/1.0",
    "openai/userLocation": {
        "city": "New York",
        "region": "New York",
        "country": "US",
        "timezone": "America/New_York",
    },
}
RAW_VALUES = tuple(
    value
    for value in (
        "session-secret-correlate-001",
        "subject-secret-correlate-001",
        "organization-secret-correlate-001",
        "en-US",
        "ChatGPT-Business-Test/1.0",
        "New York",
        "America/New_York",
    )
)


def _config() -> HostContextProbeConfig:
    return HostContextProbeConfig(
        app_realm="surface",
        app_generation="surface-probe-g1",
        transport_profile="secure-mcp-tunnel-dev",
        fingerprint_key_id="hc0-cohort-a",
        fingerprint_key_version="v1",
        fingerprint_scope="probe-cohort",
        fingerprint_secret=b"0123456789abcdef0123456789abcdef",
    )


def _run(coroutine):
    return asyncio.run(coroutine)


def _call_tool(
    server,
    *,
    arguments: dict[str, object] | None = None,
    meta: object = RAW_META,
):
    request_meta = mcp_types.RequestParams.Meta.model_validate(meta)
    context = RequestContext(
        request_id="test-request",
        meta=request_meta,
        session=object(),
        lifespan_context={},
    )
    token = request_ctx.set(context)
    try:
        request = mcp_types.CallToolRequest(
            params=mcp_types.CallToolRequestParams(
                name=TOOL_NAME,
                arguments=arguments or {},
            )
        )
        wrapped = _run(server.request_handlers[mcp_types.CallToolRequest](request))
        return wrapped.root
    finally:
        request_ctx.reset(token)


def test_tool_census_and_contract_are_exact() -> None:
    tools = build_tools()
    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == TOOL_NAME == "inspect_surface_context"
    assert tool.title == TOOL_TITLE
    assert tool.description == TOOL_DESCRIPTION
    assert tool.inputSchema == INPUT_SCHEMA
    assert tool.outputSchema == OUTPUT_SCHEMA
    assert tool.annotations is not None
    assert tool.annotations.model_dump(exclude_none=True) == {
        "title": TOOL_TITLE,
        **TOOL_ANNOTATIONS,
    }
    assert tool.meta is None
    assert tool.execution is None


def test_low_level_server_exposes_only_ping_list_and_call() -> None:
    server = build_mcp_server(_config(), utc_now=lambda: FIXED_NOW)
    assert set(server.request_handlers) == {
        mcp_types.PingRequest,
        mcp_types.ListToolsRequest,
        mcp_types.CallToolRequest,
    }
    assert server.notification_handlers == {}

    options = initialization_options(server)
    assert options.server_name == SERVER_IDENTITY
    assert options.server_version == SERVER_VERSION
    assert options.capabilities.tools is not None
    assert options.capabilities.resources is None
    assert options.capabilities.prompts is None
    assert options.capabilities.logging is None
    assert options.capabilities.completions is None
    assert options.capabilities.experimental == {}


def test_call_reads_server_request_meta_and_returns_structured_core_result() -> None:
    server = build_mcp_server(_config(), utc_now=lambda: FIXED_NOW)
    result = _call_tool(server)

    assert isinstance(result, mcp_types.CallToolResult)
    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["schema"] == "mastermind.host_context_probe.v1"
    assert result.structuredContent["contract_digest"] == CONTRACT_DIGEST
    assert result.structuredContent["observed_at"] == "2026-08-30T04:30:00Z"
    assert len(result.content) == 1
    assert isinstance(result.content[0], mcp_types.TextContent)
    assert json.loads(result.content[0].text) == result.structuredContent

    rendered = json.dumps(result.model_dump(by_alias=True), sort_keys=True)
    for raw in RAW_VALUES:
        assert raw not in rendered


def test_host_metadata_cannot_be_supplied_as_model_arguments() -> None:
    server = build_mcp_server(_config(), utc_now=lambda: FIXED_NOW)
    result = _call_tool(
        server,
        arguments={"openai/session": "model-selected-session"},
        meta=RAW_META,
    )

    assert isinstance(result, mcp_types.CallToolResult)
    assert result.isError is True
    assert result.structuredContent is None
    rendered = json.dumps(result.model_dump(by_alias=True), sort_keys=True)
    assert "model-selected-session" not in rendered
    assert "session-secret-correlate-001" not in rendered


def test_malformed_request_meta_returns_only_fixed_opaque_error() -> None:
    server = build_mcp_server(_config(), utc_now=lambda: FIXED_NOW)
    malformed = dict(RAW_META)
    malformed["openai/session"] = "raw-secret\nthat-must-not-escape"
    result = _call_tool(server, meta=malformed)

    assert isinstance(result, mcp_types.CallToolResult)
    assert result.isError is True
    assert result.structuredContent is None
    assert len(result.content) == 1
    assert isinstance(result.content[0], mcp_types.TextContent)
    assert result.content[0].text == "INVALID_HOST_METADATA"
    rendered = json.dumps(result.model_dump(by_alias=True), sort_keys=True)
    assert "raw-secret" not in rendered
    assert "session-secret-correlate-001" not in rendered


def test_streamable_http_app_is_stateless_and_mounted_at_exact_path() -> None:
    app = build_streamable_http_app(_config(), utc_now=lambda: FIXED_NOW)
    assert len(app.routes) == 1
    assert app.routes[0].path == MCP_PATH == "/mastermind-surface-probe/mcp"
    assert getattr(app.state, "mastermind_stateless") is True
    assert getattr(app.state, "mastermind_json_response") is True
    assert getattr(app.state, "mastermind_mcp_path") == MCP_PATH


def test_runtime_configuration_is_loopback_only_and_secret_safe() -> None:
    environ = {
        "MASTERMIND_SURFACE_PROBE_APP_REALM": "surface",
        "MASTERMIND_SURFACE_PROBE_APP_GENERATION": "surface-probe-g1",
        "MASTERMIND_SURFACE_PROBE_TRANSPORT_PROFILE": "secure-mcp-tunnel-dev",
        "MASTERMIND_SURFACE_PROBE_HMAC_KEY_ID": "hc0-cohort-a",
        "MASTERMIND_SURFACE_PROBE_HMAC_KEY_VERSION": "v1",
        "MASTERMIND_SURFACE_PROBE_FINGERPRINT_SCOPE": "probe-cohort",
        "MASTERMIND_SURFACE_PROBE_HMAC_KEY": (
            "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"
        ),
    }
    runtime = load_runtime_configuration(environ)
    assert runtime.host == DEFAULT_HOST == "127.0.0.1"
    assert runtime.port == DEFAULT_PORT == 8011
    assert runtime.mcp_path == MCP_PATH
    assert runtime.probe_config.app_generation == "surface-probe-g1"
    assert "MDEyMzQ1" not in repr(runtime)
    assert "0123456789abcdef" not in repr(runtime)

    receipt = describe_runtime(runtime)
    assert receipt == {
        "schema": RUNTIME_SCHEMA,
        "status": "READY_TO_SERVE",
        "server_identity": SERVER_IDENTITY,
        "server_version": SERVER_VERSION,
        "contract_digest": CONTRACT_DIGEST,
        "app_realm": "surface",
        "app_generation": "surface-probe-g1",
        "host": "127.0.0.1",
        "port": 8011,
        "mcp_path": MCP_PATH,
        "stateless": True,
        "json_response": True,
        "oauth_configured": False,
        "production_armed": False,
    }


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",
        "localhost",
        "mcp.example.com",
        "127.0.0.2",
        " 127.0.0.1",
    ],
)
def test_runtime_configuration_refuses_non_exact_loopback_bind(host: str) -> None:
    environ = {
        "MASTERMIND_SURFACE_PROBE_APP_REALM": "surface",
        "MASTERMIND_SURFACE_PROBE_APP_GENERATION": "surface-probe-g1",
        "MASTERMIND_SURFACE_PROBE_TRANSPORT_PROFILE": "secure-mcp-tunnel-dev",
        "MASTERMIND_SURFACE_PROBE_HMAC_KEY_ID": "hc0-cohort-a",
        "MASTERMIND_SURFACE_PROBE_HMAC_KEY_VERSION": "v1",
        "MASTERMIND_SURFACE_PROBE_FINGERPRINT_SCOPE": "probe-cohort",
        "MASTERMIND_SURFACE_PROBE_HMAC_KEY": (
            "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"
        ),
        "MASTERMIND_SURFACE_PROBE_HOST": host,
    }
    with pytest.raises(ValueError, match="INVALID_RUNTIME_CONFIGURATION"):
        load_runtime_configuration(environ)


def test_launcher_is_a_thin_fixed_server_entrypoint() -> None:
    path = ROOT / "scripts/run_mastermind_surface_probe.py"
    source = path.read_text(encoding="utf-8")
    assert "from integrations.mastermind_surface_probe.server import main" in source
    assert "raise SystemExit(main())" in source
    assert "socket" not in source
    assert "subprocess" not in source
    assert "token" not in source.lower()
    assert "secret" not in source.lower()
