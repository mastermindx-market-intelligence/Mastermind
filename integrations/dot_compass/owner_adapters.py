"""Read-only projections of incumbent Executive MCP tools; no host selection."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .gateway import OwnerEvidence

_COMPANY_FIELDS = ("strategic_state", "runtime_counts", "attention_counts", "boot_packet_schema", "inbox_schema", "next_recommended_act")
_ATTENTION_FIELDS = ("attention_id", "kind", "owner_seat", "status", "workstream", "job_id", "root_job_id", "review_required")


def _safe_projection(name: str, raw: Any) -> dict[str, Any]:
    """Do not leak installed host roots, private workspace paths, or raw inbox payloads."""
    if type(raw) is not dict:
        raise ValueError("incumbent Executive data is not an object")
    if name == "executive_state":
        projection = {key: raw[key] for key in _COMPANY_FIELDS if key in raw}
        if not projection:
            raise ValueError("unrecognized Executive company source")
        return projection
    attention = raw.get("attention")
    if type(attention) is not list or len(attention) > 32:
        raise ValueError("incumbent Executive attention cannot be bounded")
    projection = []
    for item in attention:
        if type(item) is not dict or type(item.get("attention_id")) is not str:
            raise ValueError("malformed canonical attention item")
        projection.append({key: item[key] for key in _ATTENTION_FIELDS if key in item})
    return {"attention_count": len(attention), "attention": projection}


def executive_read_port(gateway: Any, name: str) -> Callable[..., Any]:
    """Bind two existing Executive readers without exposing local host coordinates.

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
                             data=_safe_projection(name, response["data"]),
                             issues=("OWNER_DEGRADED",) if degraded else ())

    return reader
