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
PROVIDERS = frozenset(("claude", "codex", "grok", "cursor", "opencode"))


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
    url = _endpoint(browser_url)

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
