#!/usr/bin/env python3
"""Read-only Claude Executive MCP/Auth0 readiness check on the installed Mac.

No tokens, client IDs, browser sessions, Auth0 mutations, login attempts, or
service changes. The result is a *preflight*, never proof of authenticated use.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

COO_SCOPE = "mastermind.executive.coo.act"
READ_SCOPE = "mastermind.executive.read"
EXPECTED_SCOPES = {COO_SCOPE, READ_SCOPE}
CONFIG_PATH = Path("/Library/Application Support/MastermindExecutive/config/executive-mcp.json")
ADAPTER_PATH = Path.home() / ".local/lib/mastermind/claude-executive-mcp/adapter.mjs"
CLAUDE_PATH = Path.home() / ".claude.json"
COO_URL = "http://127.0.0.1:8443/mcp/coo"
RESOURCE_URL = "http://127.0.0.1:8444/.well-known/oauth-protected-resource"
AUTH_URL = "http://127.0.0.1:8444/.well-known/oauth-authorization-server"
MAX_BYTES = 65536
MCP_INITIALIZE = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18",
               "clientInfo": {"name": "executive-readiness-check", "version": "1"},
               "capabilities": {}},
}).encode()


def _load_json(path: Path) -> dict | None:
    """Never return config contents to the display/logging layer."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if type(data) is dict else None
    except (OSError, ValueError, UnicodeError):
        return None


def _read_adapter(path: Path) -> str | None:
    try:
        if path.stat().st_size > 131072:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


class _DenyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _loopback_probe(url: str, *, post: bool = False) -> dict:
    """Fixed loopback-only, unauthenticated request; no proxy or credential use."""
    if url not in (COO_URL, RESOURCE_URL, AUTH_URL):
        raise ValueError("probe URL not in fixed loopback allowlist")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _DenyRedirect())
    headers = {"Accept": "application/json, text/event-stream"}
    data = MCP_INITIALIZE if post else None
    if post:
        headers["Content-Type"] = "application/json"
        headers["MCP-Protocol-Version"] = "2025-06-18"
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if post else "GET")
    response = None
    try:
        response = opener.open(request, timeout=3)
    except urllib.error.HTTPError as err:
        response = err
    except (OSError, ValueError, TimeoutError):
        return {"status": None, "json": None, "coo_challenge": False}
    try:
        status = response.status
        challenge = response.headers.get("WWW-Authenticate", "")
        is_coo_challenge = ("bearer" in challenge.lower()
                            and COO_SCOPE in challenge
                            and "resource_metadata=" in challenge)
        body = response.read(MAX_BYTES + 1)
        parsed = None
        if status == 200 and len(body) <= MAX_BYTES:
            try:
                candidate = json.loads(body.decode("utf-8"))
                if type(candidate) is dict:
                    parsed = candidate
            except (UnicodeError, ValueError):
                pass
        return {"status": status, "json": parsed,
                "coo_challenge": is_coo_challenge}
    except (OSError, ValueError, TimeoutError):
        return {"status": None, "json": None, "coo_challenge": False}
    finally:
        response.close()


def evaluate(installed: dict | None, claude: dict | None,
             adapter_source: str | None, upstream: dict,
             resource: dict, auth: dict) -> dict:
    """Pure, bounded diagnostic without any host or credential access."""
    problems: list[str] = []

    if installed is None:
        problems.append("INSTALLED_CONFIG_UNREADABLE")
    else:
        if installed.get("executive_mcp_profile") != "web_ceo_v3":
            problems.append("EXECUTIVE_V3_PROFILE_NOT_ACTIVE")
        policies = installed.get("policies") or {}
        coo = installed.get("coo")
        if type(coo) is not dict or type(coo.get("policy")) is not dict:
            problems.append("INSTALLED_COO_POLICY_MISSING")
        else:
            policy = coo["policy"]
            scopes = policy.get("required_scopes")
            if (type(scopes) is not list or len(scopes) != 2 or
                    any(type(scope) is not str for scope in scopes)
                    or set(scopes) != EXPECTED_SCOPES):
                problems.append("COO_SCOPE_CONTRACT_INVALID")
            read = policies.get("read") if type(policies) is dict else None
            if type(read) is not dict or (policy.get("resource") != read.get("resource")
                    or policy.get("issuer") != read.get("issuer")
                    or policy.get("resource_metadata_url") != read.get("resource_metadata_url")):
                problems.append("COO_RESOURCE_ISSUER_MISMATCH")
            if type(coo.get("binding")) is not dict:
                problems.append("COO_PRINCIPAL_BINDING_MISSING")

    if adapter_source is None:
        problems.append("INSTALLED_ADAPTER_UNREADABLE")
    elif 'const UPSTREAM_COO_PATH = "/mcp/coo"' not in adapter_source or "const cooPolicy" not in adapter_source:
        problems.append("INSTALLED_ADAPTER_IS_LEGACY_CEO_ROUTE")

    if claude is None:
        problems.append("CLAUDE_CONFIG_UNREADABLE")
    else:
        servers = claude.get("mcpServers")
        server = servers.get("mastermind-executive") if type(servers) is dict else None
        if type(server) is not dict or server.get("type") != "http" or server.get("url") != "http://127.0.0.1:8444/mcp":
            problems.append("CLAUDE_EXECUTIVE_REGISTRATION_MISSING_OR_DRIFTED")
        else:
            oauth = server.get("oauth")
            if type(oauth) is not dict or not isinstance(oauth.get("clientId"), str) or not oauth.get("clientId"):
                problems.append("CLAUDE_PUBLIC_OAUTH_CLIENT_NOT_ENROLLED")
            else:
                if oauth.get("callbackPort") != 8774:
                    problems.append("CLAUDE_NATIVE_CALLBACK_MISMATCH")
                scopes = oauth.get("scopes")
                if type(scopes) is not str or len(scopes.split()) != 2 or set(scopes.split()) != EXPECTED_SCOPES:
                    problems.append("CLAUDE_NATIVE_COO_SCOPES_MISSING")
                if "clientSecret" in oauth or "client_secret" in oauth:
                    problems.append("CLAUDE_PUBLIC_CLIENT_HAS_UNEXPECTED_SECRET_FIELD")

    if upstream.get("status") != 401 or not upstream.get("coo_challenge"):
        problems.append(
            "UPSTREAM_COO_ROUTE_NOT_EXPOSED" if upstream.get("status") == 404
            else "UPSTREAM_COO_AUTH_CHALLENGE_UNPROVEN"
        )
    metadata = resource.get("json") if resource.get("status") == 200 else None
    if type(metadata) is not dict or metadata.get("resource") != "http://127.0.0.1:8444/mcp":
        problems.append("LOCAL_MCP_RESOURCE_METADATA_INVALID")
    else:
        scopes = metadata.get("scopes_supported")
        if (type(scopes) is not list or len(scopes) != 2
                or any(type(scope) is not str for scope in scopes)
                or set(scopes) != EXPECTED_SCOPES):
            problems.append("LOCAL_MCP_ROLE_SCOPES_INVALID")
    as_metadata = auth.get("json") if auth.get("status") == 200 else None
    if type(as_metadata) is not dict:
        problems.append("LOCAL_OAUTH_DISCOVERY_UNAVAILABLE")
    else:
        endpoint = as_metadata.get("authorization_endpoint")
        if type(endpoint) is not str or urlsplit(endpoint).scheme != "https":
            problems.append("BROWSER_AUTHORIZATION_ENDPOINT_NOT_HTTPS")
        else:
            read = installed.get("policies", {}).get("read", {}) if type(installed) is dict else {}
            issuer = read.get("issuer") if type(read) is dict else None
            approved = urlsplit(issuer).hostname if type(issuer) is str else None
            endpoint_host = urlsplit(endpoint).hostname
            if not approved or endpoint_host not in {approved, "localhost", "127.0.0.1"}:
                problems.append("BROWSER_AUTHORIZATION_ENDPOINT_UNTRUSTED_HOST")

    return {
        "schema": "mastermind.claude_executive_auth_preflight.v1",
        "status": "BLOCKED" if problems else "READY_FOR_INTERACTIVE_AUTH_CANARY",
        "problems": sorted(set(problems)),
        "no_auth_attempt": True,
        "no_config_mutation": True,
        "production_authenticated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-probes", action="store_true",
                        help="Inspect local files only; probe statuses stay unknown")
    args = parser.parse_args()
    unavailable = {"status": None, "json": None, "coo_challenge": False}
    upstream = _loopback_probe(COO_URL, post=True) if not args.no_probes else unavailable
    resource = _loopback_probe(RESOURCE_URL) if not args.no_probes else unavailable
    auth = _loopback_probe(AUTH_URL) if not args.no_probes else unavailable
    result = evaluate(_load_json(CONFIG_PATH), _load_json(CLAUDE_PATH),
                      _read_adapter(ADAPTER_PATH), upstream, resource, auth)
    print(json.dumps(result, sort_keys=True))
    return 0 if not result["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
