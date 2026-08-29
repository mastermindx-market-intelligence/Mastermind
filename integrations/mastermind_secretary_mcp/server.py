"""SDK-free, production-inert tools-only Secretary contract facade."""

from __future__ import annotations

import copy

from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway
from integrations.mastermind_secretary_mcp.schemas import TOOL_SPECS

STATIC_CAPABILITIES = {
    "tools": True,
    "resources": False,
    "prompts": False,
    "roots": False,
    "sampling": False,
    "elicitation": False,
    "dynamic_registration": False,
}


def build_tools() -> list[dict[str, object]]:
    """Return the immutable six-tool advertisement as plain JSON-compatible rows."""

    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": copy.deepcopy(spec.input_schema),
            "outputSchema": copy.deepcopy(spec.output_schema),
            "annotations": copy.deepcopy(spec.annotations),
        }
        for spec in TOOL_SPECS
    ]


class SecretaryGroundingContractServer:
    """Expose only static tool listing and bounded calls over an injected gateway."""

    def __init__(self, gateway: SecretaryGroundingGateway) -> None:
        self._gateway = gateway
        self._tools = build_tools()

    def list_tools(self) -> list[dict[str, object]]:
        return copy.deepcopy(self._tools)

    async def call_tool(self, name: str, arguments: object) -> dict[str, object]:
        return await self._gateway.call(name, arguments)


__all__ = [
    "STATIC_CAPABILITIES",
    "SecretaryGroundingContractServer",
    "build_tools",
]
