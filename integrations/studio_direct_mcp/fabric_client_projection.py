"""Pure provider projection for the guarded Studio Direct fabric routes.

This module grants no provider, host, Paper, network, process, or lifecycle
authority. It only renders client-native MCP configuration from two already
installed exact HTTPS route URLs. The Studio gateway remains the tool authority:
read and design ceilings are enforced server-side before dispatch.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
from http.client import HTTPS_PORT
from urllib.parse import urlsplit

SERVER_NAME = "mastermindStudio"
READ_PATH = "/studio-fabric"
DESIGN_PATH = "/studio-design"
PROVIDERS = frozenset(("claude", "codex", "grok", "cursor", "opencode"))
_TASK_CLASS = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class FabricClientProjectionError(ValueError):
    """One provider projection cannot be represented safely."""


@dataclasses.dataclass(frozen=True, slots=True)
class FabricClientProjection:
    provider: str
    task_class: str
    route: str
    url: str
    config_format: str
    config_text: str
    cli_args: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "mastermind.studio_fabric_client_projection.v1",
            "provider": self.provider,
            "task_class": self.task_class,
            "route": self.route,
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
                "may_select_paper_target": False,
            },
        }


def _endpoint(value: object, expected_path: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise FabricClientProjectionError("Studio fabric URL is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise FabricClientProjectionError("Studio fabric URL is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or not isinstance(host, str)
        or not host.endswith(".ts.net")
        or len(host) <= len(".ts.net")
        or port not in (None, HTTPS_PORT)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise FabricClientProjectionError(
            f"Studio fabric URL must be exact HTTPS tailnet path {expected_path}"
        )
    canonical = f"https://{host}"
    if port == HTTPS_PORT and parsed.netloc.endswith(f":{HTTPS_PORT}"):
        canonical += f":{HTTPS_PORT}"
    return canonical + expected_path


def select_route(task_class: object) -> str:
    token = str(task_class or "").strip().lower()
    if not _TASK_CLASS.fullmatch(token):
        raise FabricClientProjectionError("task_class is invalid")
    return "design" if token == "design" else "read"


def project_fabric_client(
    provider: object,
    task_class: object,
    *,
    read_url: object,
    design_url: object,
) -> FabricClientProjection:
    provider_name = str(provider or "").strip().lower()
    if provider_name not in PROVIDERS:
        raise FabricClientProjectionError("provider is unsupported")
    task = str(task_class or "").strip().lower()
    route = select_route(task)
    read = _endpoint(read_url, READ_PATH)
    design = _endpoint(design_url, DESIGN_PATH)
    url = design if route == "design" else read

    if provider_name == "claude":
        config = {
            "mcpServers": {
                SERVER_NAME: {
                    "type": "http",
                    "url": url,
                }
            }
        }
        text = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        cli_args = ("--strict-mcp-config", "--mcp-config", text)
        config_format = "claude-mcp-json"
    elif provider_name == "codex":
        text = (
            f"[mcp_servers.{SERVER_NAME}]\n"
            f"url = {json.dumps(url, ensure_ascii=True)}\n"
        )
        cli_args = ()
        config_format = "codex-toml"
    elif provider_name == "grok":
        text = (
            f"[mcp_servers.{SERVER_NAME}]\n"
            f"url = {json.dumps(url, ensure_ascii=True)}\n"
            "enabled = true\n"
        )
        cli_args = ()
        config_format = "grok-toml"
    elif provider_name == "cursor":
        config = {"mcpServers": {SERVER_NAME: {"url": url}}}
        text = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
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
        text = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        cli_args = ()
        config_format = "opencode-json"

    return FabricClientProjection(
        provider=provider_name,
        task_class=task,
        route=route,
        url=url,
        config_format=config_format,
        config_text=text,
        cli_args=cli_args,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    parser.add_argument("--task-class", required=True)
    parser.add_argument("--read-url", required=True)
    parser.add_argument("--design-url", required=True)
    args = parser.parse_args(argv)
    try:
        projection = project_fabric_client(
            args.provider,
            args.task_class,
            read_url=args.read_url,
            design_url=args.design_url,
        )
    except FabricClientProjectionError:
        print("STUDIO_FABRIC_PROJECTION_REFUSED")
        return 2
    print(
        json.dumps(
            projection.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
