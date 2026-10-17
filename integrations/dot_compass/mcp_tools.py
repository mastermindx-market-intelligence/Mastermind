"""MCP presentation adapters for existing authenticated app hosts only.

No standalone server, socket, tunnel, identity provider, or request-router path.
The host must derive `principal()` from its verified current MCP request and
install one fixed profile with an independently scoped ResourcePolicy.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .gateway import DotReadGateway


def build_tools(gateway: DotReadGateway) -> list[Any]:
    if type(gateway) is not DotReadGateway:
        raise TypeError("DotReadGateway required")
    import mcp.types as types
    return [types.Tool(name=item["name"], description=item["description"],
                       inputSchema=item["inputSchema"],
                       annotations=types.ToolAnnotations(**item["annotations"]))
            for item in gateway.tool_definitions()]


def build_handlers(gateway: DotReadGateway, *, principal: Callable[[], Any]) -> dict[str, Callable[..., Any]]:
    if type(gateway) is not DotReadGateway or not callable(principal):
        raise TypeError("fixed gateway and host principal resolver required")

    async def handle(tool: str, arguments: Any) -> dict[str, Any]:
        # Refuse before owner entry when the host fails to supply an actual
        # authenticated request-bound principal; no caller value is accepted.
        current_principal = principal()
        if current_principal is None:
            return gateway._error(tool, "authority_refused")
        return await gateway.call(tool, arguments, principal=current_principal)

    return {name: (lambda args, _name=name: handle(_name, args))
            for name in gateway.tool_names}


def build_mcp_server(_gateway: DotReadGateway) -> Any:
    raise RuntimeError("standalone Dot MCP is refused; authenticated owner host composition required")
