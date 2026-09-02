from __future__ import annotations

import ast
import importlib.util
import inspect
from pathlib import Path

import pytest

from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
)
from integrations.executive_mcp.adapter import ExecutiveMcpGateway, GatewayConfig
from integrations.executive_mcp.schemas import ServerMode
from integrations.mastermind_executive_app.gateway import (
    BusinessExecutiveGateway,
    RESOURCE_SCOPES,
)
from integrations.mastermind_executive_app.http_app import build_authenticated_app


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "integrations" / "mastermind_executive_app"
LAUNCHER = ROOT / "scripts" / "run_mastermind_executive_app.py"
FROZEN_NOW = "2026-09-02T00:00:00Z"


class _ReadonlyBackend(ExecutiveMcpGateway):
    def __init__(self, tmp_path) -> None:
        self.config = GatewayConfig(
            mode=ServerMode.READONLY,
            repo_root=tmp_path,
            now=FROZEN_NOW,
        )

    async def call(self, tool_name: str, arguments: object):
        raise AssertionError(f"unexpected backend call {tool_name}: {arguments!r}")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _load_launcher():
    spec = importlib.util.spec_from_file_location(
        "mastermind_executive_app_launcher", LAUNCHER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _policy():
    return load_resource_policy(
        {
            "schema": AUTH_POLICY_SCHEMA,
            "policy_id": "mastermind-executive-v1",
            "resource": "https://mcp.example.test/mcp/executive/v1",
            "resource_metadata_url": (
                "https://mcp.example.test/.well-known/"
                "oauth-protected-resource/mcp/executive/v1"
            ),
            "issuer": "https://identity.example.test/",
            "authorization_servers": ["https://identity.example.test/"],
            "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
            "required_scopes": list(RESOURCE_SCOPES),
            "allowed_subject_digests": ["a" * 64],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30,
            "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300,
            "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5,
        }
    )


def test_new_package_does_not_create_transport_owner_or_persistent_control_plane():
    forbidden_roots = {
        "aiohttp",
        "fastapi",
        "github",
        "linear",
        "requests",
        "slack_sdk",
        "socket",
        "sqlite3",
        "subprocess",
    }
    for path in PACKAGE.glob("*.py"):
        imports = _imports(path)
        for imported in imports:
            assert not any(
                imported == forbidden or imported.startswith(forbidden + ".")
                for forbidden in forbidden_roots
            ), (path.name, imported)

    assert all(
        not imported.startswith("control_plane")
        for path in PACKAGE.glob("*.py")
        for imported in _imports(path)
    )

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.glob("*.py"))
    )
    for fragment in (
        "create_job",
        "requeue_job",
        "send_message",
        "git push",
        "merge_pull",
        "list_resources(",
        "read_resource(",
        "list_prompts(",
        "get_prompt(",
        "list_roots(",
        "sampling",
        "elicitation",
        "sqlite",
        "session_store",
        "token_store",
        "prepared_action_store",
    ):
        assert fragment not in rendered


def test_only_sdk_edge_modules_import_mcp_and_only_launcher_imports_uvicorn():
    imports = {path.name: _imports(path) for path in PACKAGE.glob("*.py")}
    assert not any(name == "mcp" or name.startswith("mcp.") for name in imports["gateway.py"])
    assert not any(name == "mcp" or name.startswith("mcp.") for name in imports["__init__.py"])
    assert any(name == "mcp" or name.startswith("mcp.") for name in imports["server.py"])
    assert any(name == "mcp" or name.startswith("mcp.") for name in imports["http_app.py"])
    assert not any(
        imported == "uvicorn" or imported.startswith("uvicorn.")
        for values in imports.values()
        for imported in values
    )
    assert "import uvicorn" in LAUNCHER.read_text(encoding="utf-8")


def test_source_surface_has_no_dynamic_registration_or_server_side_tool_chaining():
    source = (PACKAGE / "server.py").read_text(encoding="utf-8")
    assert source.count("@server.list_tools()") == 1
    assert source.count("@server.call_tool()") == 1
    for forbidden in (
        "@server.list_resources()",
        "@server.read_resource()",
        "@server.list_prompts()",
        "@server.get_prompt()",
        "@server.list_roots()",
        "server.call_tool(",
        "gateway.call(",
    ):
        if forbidden == "gateway.call(":
            assert source.count(forbidden) == 1
        else:
            assert forbidden not in source


def test_readonly_owner_can_never_be_constructed_as_fixture_submit_capable(tmp_path):
    backend = _ReadonlyBackend(tmp_path)
    with pytest.raises(ValueError, match="fixture"):
        BusinessExecutiveGateway(
            backend,
            submission_authority=object(),
            enable_fixture_submit=True,
        )


def test_http_builder_has_no_operator_host_or_state_widening_parameters():
    parameters = inspect.signature(build_authenticated_app).parameters
    for forbidden in (
        "extra_allowed_hosts",
        "event_store",
        "session_store",
        "token_store",
        "resume",
        "production_submit_enabled",
    ):
        assert forbidden not in parameters


def test_launcher_refuses_non_loopback_bind_and_production_submit_switch():
    launcher = _load_launcher()
    assert launcher._validated_listener("127.0.0.1", 8767) == (
        "127.0.0.1",
        8767,
    )
    for hostile in ("0.0.0.0", "::", "192.0.2.10", "mcp.example.test"):
        with pytest.raises(SystemExit, match="loopback"):
            launcher._validated_listener(hostile, 8767)
    with pytest.raises(SystemExit, match="port"):
        launcher._validated_listener("127.0.0.1", 0)

    parser = launcher._parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    assert "--enable-submit" not in option_strings
    assert "--production-write" not in option_strings
    assert "--control-socket" not in option_strings


def test_exact_executive_resource_and_scope_policy_is_constructor_enforced(tmp_path):
    # A real token verifier is built in admission tests. This static constructor
    # fence proves the app cannot be pointed at a Steward or single-scope policy.
    policy = _policy()
    signature = inspect.signature(build_authenticated_app)
    assert "policy" in signature.parameters
    assert tuple(policy.required_scopes) == RESOURCE_SCOPES
    assert policy.resource.endswith("/mcp/executive/v1")


def test_restart_state_is_process_local_and_not_resumable_by_construction():
    source = (PACKAGE / "http_app.py").read_text(encoding="utf-8")
    assert "event_store=None" in source
    assert "stateless=True" in source
    assert "mcp_session_id" not in source
    assert "resume" not in source.lower()
    assert "localStorage" not in source
