"""Security and drift tests for the no-write Claude Executive auth preflight."""
from __future__ import annotations

from copy import deepcopy

from scripts.claude_executive_auth_preflight import COO_SCOPE, READ_SCOPE, evaluate


def good():
    resource = "https://mcp.example.test/mcp"
    issuer = "https://issuer.example.test/"
    metadata = "https://mcp.example.test/.well-known/oauth-protected-resource/mcp"
    read = {"resource": resource, "issuer": issuer,
            "resource_metadata_url": metadata, "required_scopes": [READ_SCOPE]}
    coo = {**read, "required_scopes": [COO_SCOPE, READ_SCOPE]}
    installed = {"executive_mcp_profile": "web_ceo_v3",
                 "policies": {"read": read},
                 "coo": {"policy": coo, "binding": {}}}
    claude = {"mcpServers": {"mastermind-executive": {
        "type": "http", "url": "http://127.0.0.1:8444/mcp",
        "oauth": {"clientId": "public-id-never-log",
                  "callbackPort": 8774,
                  "scopes": COO_SCOPE + " " + READ_SCOPE}}}}
    adapter = 'const UPSTREAM_COO_PATH = "/mcp/coo"; const cooPolicy = true;'
    upstream = {"status": 401, "coo_challenge": True}
    local = {"status": 200, "json": {
        "resource": "http://127.0.0.1:8444/mcp",
        "scopes_supported": [READ_SCOPE, COO_SCOPE]}}
    auth = {"status": 200, "json": {
        "authorization_endpoint": "https://issuer.example.test/authorize"}}
    return installed, claude, adapter, upstream, local, auth


def result(args):
    return evaluate(*args)


def test_positive_is_a_canary_ready_not_a_false_connected_claim():
    output = result(good())
    assert output["status"] == "READY_FOR_INTERACTIVE_AUTH_CANARY"
    assert not output["production_authenticated"]
    assert output["no_auth_attempt"] and output["no_config_mutation"]
    assert output["problems"] == []


def test_real_m2_failure_signature_is_fully_identified_without_secrets():
    args = list(good())
    del args[0]["coo"]
    args[1]["mcpServers"]["mastermind-executive"].pop("oauth")
    args[2] = "const UPSTREAM_CEO_PATH = '/mcp';"
    args[3] = {"status": 404, "coo_challenge": False}
    args[4]["json"]["scopes_supported"] = [READ_SCOPE, "mastermind.executive.intent.submit"]
    args[5]["json"]["authorization_endpoint"] = "http://127.0.0.1:8444/authorize"
    output = result(args)
    assert output["status"] == "BLOCKED"
    assert set(output["problems"]) == {
        "INSTALLED_COO_POLICY_MISSING",
        "CLAUDE_PUBLIC_OAUTH_CLIENT_NOT_ENROLLED",
        "INSTALLED_ADAPTER_IS_LEGACY_CEO_ROUTE",
        "UPSTREAM_COO_ROUTE_NOT_EXPOSED",
        "LOCAL_MCP_ROLE_SCOPES_INVALID",
        "BROWSER_AUTHORIZATION_ENDPOINT_NOT_HTTPS",
    }
    assert "public-id-never-log" not in str(output)
    assert "mastermind.executive.intent.submit" not in str(output)


def test_issuer_resource_and_role_mismatch_fail_closed():
    args = list(good())
    args[0]["coo"]["policy"]["resource"] = "https://wrong.example.test/mcp"
    args[0]["coo"]["policy"]["required_scopes"] = [READ_SCOPE, "mastermind.executive.intent.submit"]
    args[0]["coo"].pop("binding")
    args[1]["mcpServers"]["mastermind-executive"]["oauth"]["callbackPort"] = 8775
    args[1]["mcpServers"]["mastermind-executive"]["oauth"]["scopes"] = READ_SCOPE
    args[1]["mcpServers"]["mastermind-executive"]["oauth"]["clientSecret"] = "never-log"
    failures = set(result(args)["problems"])
    assert {"COO_RESOURCE_ISSUER_MISMATCH", "COO_SCOPE_CONTRACT_INVALID",
            "COO_PRINCIPAL_BINDING_MISSING", "CLAUDE_NATIVE_CALLBACK_MISMATCH",
            "CLAUDE_NATIVE_COO_SCOPES_MISSING",
            "CLAUDE_PUBLIC_CLIENT_HAS_UNEXPECTED_SECRET_FIELD"} <= failures
    assert "never-log" not in str(result(args))


def test_non_json_metadata_and_partial_scopes_refuse():
    args = list(good())
    args[4] = {"status": 200, "json": None}
    args[5] = {"status": 200, "json": {"authorization_endpoint": None}}
    output = result(args)
    assert "LOCAL_MCP_RESOURCE_METADATA_INVALID" in output["problems"]
    assert "BROWSER_AUTHORIZATION_ENDPOINT_NOT_HTTPS" in output["problems"]


def test_missing_files_and_unavailable_port_are_uncertain_not_success():
    args = list(good())
    args[0] = args[1] = args[2] = None
    args[3] = {"status": None, "coo_challenge": False}
    args[4] = args[5] = {"status": None, "json": None}
    output = result(args)
    assert "INSTALLED_CONFIG_UNREADABLE" in output["problems"]
    assert "CLAUDE_CONFIG_UNREADABLE" in output["problems"]
    assert "INSTALLED_ADAPTER_UNREADABLE" in output["problems"]
    assert "UPSTREAM_COO_AUTH_CHALLENGE_UNPROVEN" in output["problems"]
    assert "LOCAL_OAUTH_DISCOVERY_UNAVAILABLE" in output["problems"]
    assert output["status"] == "BLOCKED"


def test_untrusted_scope_values_do_not_crash_or_claim_readiness():
    args = list(good())
    args[0]["coo"]["policy"]["required_scopes"] = [{"unexpected": "object"}, READ_SCOPE]
    args[4]["json"]["scopes_supported"] = [{"unexpected": "object"}]
    output = result(args)
    assert output["status"] == "BLOCKED"
    assert "COO_SCOPE_CONTRACT_INVALID" in output["problems"]
    assert "LOCAL_MCP_ROLE_SCOPES_INVALID" in output["problems"]


def test_foreign_https_authorize_host_is_not_approved():
    args = list(good())
    args[5]["json"]["authorization_endpoint"] = "https://foreign.example.test/authorize"
    output = result(args)
    assert "BROWSER_AUTHORIZATION_ENDPOINT_UNTRUSTED_HOST" in output["problems"]
    assert output["status"] == "BLOCKED"


def test_probe_does_not_fetch_arbitrary_targets():
    from scripts.claude_executive_auth_preflight import _loopback_probe
    import pytest
    with pytest.raises(ValueError, match="fixed loopback allowlist"):
        _loopback_probe("https://evil.example.test/steal")
