"""Read-only adapters to incumbent Executive MCP tools; no network or host selection."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .gateway import OwnerEvidence


def executive_read_port(gateway: Any, name: str) -> Callable[..., Any]:
    """Bind exact Executive tools to an already-authenticated host-provisioned reader.

    Only executive_state and executive_inbox are projected. No submit path exists.
    A live host MUST independently authenticate/authorize every incoming Dot call;
    providing an ExecutiveMcpGateway object is not itself an authority receipt.
    """
    if name not in ("executive_state", "executive_inbox"):
        raise ValueError("only two existing Executive read tools may be adapted")
    if not callable(getattr(gateway, "call", None)):
        raise TypeError("existing Executive gateway required")

    async def reader(args: dict[str, str]) -> OwnerEvidence:
        if args:
            raise ValueError("Executive reader has zero input fields")
        response = await gateway.call(name, {})
        if type(response) is not dict or response.get("schema") != "mastermind.executive_mcp_result.v1" or response.get("tool") != name:
            raise ValueError("unverified Executive read result")
        if not response.get("ok") or response.get("mode") != "readonly":
            raise ValueError("incumbent Executive read not admitted")
        grounding = response.get("grounding")
        if type(grounding) is not dict or type(grounding.get("mastermind")) is not dict:
            raise ValueError("missing Executive source grounding")
        master_sha = grounding["mastermind"].get("sha")
        if type(master_sha) is not str or len(master_sha) != 40 or any(c not in "0123456789abcdef" for c in master_sha):
            raise ValueError("missing immutable Executive source")
        source_refs = ("mastermind@" + master_sha,)
        macro = grounding.get("macro")
        if type(macro) is dict and type(macro.get("sha")) is str and len(macro["sha"]) == 40 and all(c in "0123456789abcdef" for c in macro["sha"]):
            source_refs += ("macro@" + macro["sha"],)
        degraded = response.get("degraded")
        if type(degraded) is not list:
            raise ValueError("invalid Executive degraded evidence")
        return OwnerEvidence(owner="executive", observed_at=response["generated_at"],
                             source_refs=source_refs,
                             capability_state="PARTIAL" if degraded else "BUILT_NOT_PROVEN",
                             data=response["data"],
                             issues=("OWNER_DEGRADED",) if degraded else ())

    return reader
