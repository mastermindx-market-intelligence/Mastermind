import json
import pytest

from integrations.mastermind_browser_plugin.client_projection import (
    BrowserClientProjectionError,
    PROVIDERS,
    SERVER_NAME,
    project_browser_client,
)

URL = "https://browser-gateway.tailabc.ts.net/browser-fabric"


def test_browser_projection_uses_distinct_server_name_and_no_authority():
    assert SERVER_NAME == "mastermindBrowser"
    assert SERVER_NAME != "mastermindStudio"
    row = project_browser_client("claude", browser_url=URL)
    value = row.to_dict()
    assert value["url"] == URL
    assert value["server_name"] == "mastermindBrowser"
    assert value["authority"] == {
        "client_config_is_authority": False,
        "gateway_tool_ceiling_authoritative": True,
        "may_start_process": False,
        "may_select_host": False,
        "may_select_profile": False,
        "may_mint_browser_grant": False,
    }


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_every_supported_provider_targets_the_same_exact_browser_service(provider):
    row = project_browser_client(provider, browser_url=URL)
    assert row.provider == provider
    assert row.url == URL
    assert "mastermindBrowser" in row.config_text
    assert "mastermindStudio" not in row.config_text
    assert "browser-fabric" in row.config_text


def test_claude_projection_is_strict_http_mcp_config():
    row = project_browser_client("claude", browser_url=URL)
    parsed = json.loads(row.config_text)
    assert parsed == {
        "mcpServers": {
            "mastermindBrowser": {
                "type": "http",
                "url": URL,
            }
        }
    }
    assert row.cli_args == ("--strict-mcp-config", "--mcp-config", row.config_text)


def test_codex_and_grok_projection_are_remote_url_only():
    codex = project_browser_client("codex", browser_url=URL)
    assert codex.config_format == "codex-toml"
    assert codex.config_text == f'[mcp_servers.mastermindBrowser]\nurl = "{URL}"\n'
    assert codex.cli_args == ()

    grok = project_browser_client("grok", browser_url=URL)
    assert grok.config_format == "grok-toml"
    assert grok.config_text == (
        f'[mcp_servers.mastermindBrowser]\nurl = "{URL}"\nenabled = true\n'
    )
    assert grok.cli_args == ()


def test_cursor_and_opencode_projection_are_closed_json():
    cursor = project_browser_client("cursor", browser_url=URL)
    assert json.loads(cursor.config_text) == {
        "mcpServers": {"mastermindBrowser": {"url": URL}}
    }
    assert cursor.cli_args == ("--approve-mcps",)

    opencode = project_browser_client("opencode", browser_url=URL)
    assert json.loads(opencode.config_text) == {
        "mcp": {
            "mastermindBrowser": {
                "type": "remote",
                "url": URL,
            }
        }
    }
    assert opencode.cli_args == ()


@pytest.mark.parametrize("provider", ["", "studio", "browser", "anthropic", None, True])
def test_unknown_provider_refuses(provider):
    with pytest.raises(BrowserClientProjectionError):
        project_browser_client(provider, browser_url=URL)


@pytest.mark.parametrize(
    "url",
    [
        "http://browser-gateway.tailabc.ts.net/browser-fabric",
        "https://browser-gateway.example.com/browser-fabric",
        "https://browser-gateway.tailabc.ts.net/studio-fabric",
        "https://browser-gateway.tailabc.ts.net/browser-fabric?x=1",
        "https://browser-gateway.tailabc.ts.net/browser-fabric#x",
        "https://user:pass@browser-gateway.tailabc.ts.net/browser-fabric",
        "https://browser-gateway.tailabc.ts.net:444/browser-fabric",
        "https://.ts.net/browser-fabric",
        "",
        None,
    ],
)
def test_browser_url_is_exact_https_tailnet_route(url):
    with pytest.raises(BrowserClientProjectionError):
        project_browser_client("claude", browser_url=url)


def test_explicit_https_443_canonicalizes_without_changing_service_identity():
    row = project_browser_client(
        "claude",
        browser_url="https://browser-gateway.tailabc.ts.net:443/browser-fabric",
    )
    assert row.url == "https://browser-gateway.tailabc.ts.net:443/browser-fabric"


def test_projection_contains_no_host_profile_account_or_credential_input_channel():
    row = project_browser_client("claude", browser_url=URL)
    rendered = json.dumps(row.to_dict(), sort_keys=True)
    for forbidden in (
        "profile_ref",
        "host_ref",
        "account_label",
        "credential",
        "token",
        "api_key",
        "tunnel_id",
        "worker_id",
        "attempt_id",
    ):
        assert forbidden not in rendered
