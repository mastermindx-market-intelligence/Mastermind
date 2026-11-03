"""Pure native-client projection for the separate Mastermind Browser MCP service.

This module grants no browser, provider, host, profile, process, credential,
placement or lifecycle authority. It only renders client-native MCP
configuration for one already-installed exact HTTPS Browser route.
"""
from __future__ import annotations

from dataclasses import dataclass
from http.client import HTTPS_PORT
import json
from urllib.parse import urlsplit

SERVER_NAME = "mastermindBrowser"
BROWSER_PATH = "/browser-fabric"
PROVIDERS = frozenset(("claude", "codex", "grok", "cursor", "opencode", "openclaw"))


class BrowserClientProjectionError(ValueError):
    """One Browser client projection cannot be represented safely."""


@dataclass(frozen=True, slots=True)
class BrowserClientProjection:
    provider: str
    url: str
    config_format: str
    config_text: str
    cli_args: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "mastermind.browser_client_projection.v1",
            "provider": self.provider,
            "url": self.url,
            "server_name": SERVER_NAME,
            "config_format": self.config_format,
            "config_text": self.config_text,
            "cli_args": list(self.cli_args),
            "authority": {
                "client_config_is_authority": False,
                "gateway_tool_ceiling_authoritative": True,
                "may_start_process": False,
                "may_select_host": False,
                "may_select_profile": False,
                "may_mint_browser_grant": False,
            },
        }


def _endpoint(value: object) -> str:
    if type(value) is not str or not value or len(value) > 2048:
        raise BrowserClientProjectionError("Browser MCP URL is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise BrowserClientProjectionError("Browser MCP URL is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or type(host) is not str
        or not host.endswith(".ts.net")
        or len(host) <= len(".ts.net")
        or port not in (None, HTTPS_PORT)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != BROWSER_PATH
    ):
        raise BrowserClientProjectionError(
            f"Browser MCP URL must be exact HTTPS tailnet path {BROWSER_PATH}"
        )
    canonical = f"https://{host}"
    if port == HTTPS_PORT and parsed.netloc.endswith(f":{HTTPS_PORT}"):
        canonical += f":{HTTPS_PORT}"
    return canonical + BROWSER_PATH


def project_browser_client(
    provider: object,
    *,
    browser_url: object,
) -> BrowserClientProjection:
    provider_name = str(provider or "").strip().lower()
    if provider_name not in PROVIDERS or type(provider) is not str:
        raise BrowserClientProjectionError("Browser MCP provider is unsupported")
    return _render_client(provider_name, _endpoint(browser_url))


def _render_client(provider_name: str, url: str) -> BrowserClientProjection:
    if provider_name == "claude":
        config = {
            "mcpServers": {
                SERVER_NAME: {
                    "type": "http",
                    "url": url,
                }
            }
        }
        config_text = json.dumps(
            config, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        cli_args = ("--strict-mcp-config", "--mcp-config", config_text)
        config_format = "claude-mcp-json"
    elif provider_name == "codex":
        config_text = (
            f"[mcp_servers.{SERVER_NAME}]\n"
            f"url = {json.dumps(url, ensure_ascii=True)}\n"
        )
        cli_args = ()
        config_format = "codex-toml"
    elif provider_name == "grok":
        config_text = (
            f"[mcp_servers.{SERVER_NAME}]\n"
            f"url = {json.dumps(url, ensure_ascii=True)}\n"
            "enabled = true\n"
        )
        cli_args = ()
        config_format = "grok-toml"
    elif provider_name == "openclaw":
        config = {"mcp": {"servers": {SERVER_NAME: {
            "url": url, "transport": "streamable-http", "auth": "oauth",
            "connectionTimeoutMs": 30000, "requestTimeoutMs": 90000,
            "supportsParallelToolCalls": True,
        }}}}
        config_text = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        cli_args = ()
        config_format = "openclaw-json"
    elif provider_name == "cursor":
        config = {"mcpServers": {SERVER_NAME: {"url": url}}}
        config_text = json.dumps(
            config, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        cli_args = ("--approve-mcps",)
        config_format = "cursor-mcp-json"
    else:
        config = {
            "mcp": {
                SERVER_NAME: {
                    "type": "remote",
                    "url": url,
                }
            }
        }
        config_text = json.dumps(
            config, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        cli_args = ()
        config_format = "opencode-json"

    return BrowserClientProjection(
        provider=provider_name,
        url=url,
        config_format=config_format,
        config_text=config_text,
        cli_args=cli_args,
    )


WEB_CLIENTS = frozenset(("chatgpt-web", "claude-web", "grok-bot", "grok-web"))
PUBLIC_CLIENTS = PROVIDERS | WEB_CLIENTS


@dataclass(frozen=True, slots=True)
class BrowserPublicClientProjection:
    provider: str
    url: str
    config_format: str
    config_text: str | None
    cli_args: tuple[str, ...]
    setup_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "mastermind.browser_public_client_projection.v1",
            "provider": self.provider, "url": self.url, "server_name": SERVER_NAME,
            "transport": "streamable-http", "authentication": "client_owned_oauth",
            "config_format": self.config_format, "config_text": self.config_text,
            "cli_args": list(self.cli_args), "setup_steps": list(self.setup_steps),
            "connection_proven": False, "installation_performed": False,
            "authority": {"client_config_is_authority": False,
                          "may_mint_browser_grant": False, "may_start_process": False},
        }


def project_public_browser_client(provider: object, *, ingress_plan) -> BrowserPublicClientProjection:
    """Render reviewed setup only; user OAuth remains with each native client."""
    from .ingress import BrowserIngressPlan, build_browser_ingress_plan
    if type(provider) is not str or provider not in PUBLIC_CLIENTS:
        raise BrowserClientProjectionError("Browser public client is unsupported")
    if type(ingress_plan) is not BrowserIngressPlan:
        raise BrowserClientProjectionError("Qualified Browser ingress plan required")
    try:
        expected = build_browser_ingress_plan(
            public_resource_url=ingress_plan.public_resource_url,
            internal_upstream_url=ingress_plan.internal_upstream_url)
        if ingress_plan != expected:
            raise ValueError("ingress plan changed")
    except (TypeError, ValueError) as error:
        raise BrowserClientProjectionError("Browser ingress plan invalid") from error
    url = expected.public_resource_url
    if provider in PROVIDERS:
        native = _render_client(provider, url)
        if provider == "openclaw":
            steps = (
                "Merge the named MCP server into the installed OpenClaw configuration.",
                "Run openclaw mcp login mastermindBrowser using OpenClaw's own OAuth flow.",
                "Run openclaw mcp doctor mastermindBrowser --probe to verify the connection.",
            )
        else:
            steps = (
                "Merge the named MCP server into this client's existing configuration.",
                "Use the client's native MCP OAuth sign-in and renewal flow.",
                "Discover the seven Browser tools and verify browser_fleet before selecting a browser.",
            )
        return BrowserPublicClientProjection(
            provider, url, native.config_format, native.config_text, native.cli_args, steps)
    if provider == "chatgpt-web":
        steps = (
            "Add a custom MCP connection in ChatGPT's connection management using this exact HTTPS URL.",
            "Use OAuth authorization code with PKCE; obtain the exact callback URL from that connection's settings.",
            "Enroll the selected OAuth client at the authorization server, then sign in through ChatGPT.",
            "Verify the Browser catalog and browser_fleet in a new admitted session.",
        )
    elif provider == "claude-web":
        steps = (
            "Add this URL as a custom remote connector in Claude Customize > Connectors.",
            "Use Claude's OAuth sign-in; enroll its documented callback and the selected OAuth client.",
            "Verify the Browser catalog and browser_fleet in an admitted Claude session.",
        )
    elif provider == "grok-bot":
        steps = (
            "Open the intended Grok Bot's Setup > Plugins and add a custom MCP server using Remote HTTPS.",
            "Enter this exact URL and use each person's OAuth sign-in for their browser authority.",
            "Verify the Browser catalog and browser_fleet in the intended Bot conversation.",
        )
    else:
        steps = (
            "In Grok's connector settings choose New Connector > Custom and enter this exact URL.",
            "Complete the native OAuth sign-in under the applicable organization connector policy.",
            "Verify the Browser catalog and browser_fleet in the intended Grok session.",
        )
    # Hosted products document a URL/sign-in workflow, not an importable JSON
    # schema. Do not mislabel a Grok Build or Claude Code file as web setup.
    return BrowserPublicClientProjection(provider, url, "manual-oauth-setup", None, (), steps)
