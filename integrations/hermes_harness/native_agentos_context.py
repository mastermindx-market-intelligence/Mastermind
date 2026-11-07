"""One adopted Agent OS read on the already captured native MCP owner.

No client, token, connection, local compiler fallback, retry, authority store
or model-selected scope is created here. The original SDK result is decoded
as the single reviewed text result emitted by the incumbent COO server.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from common import coo_agentos_context_contract as wire
from integrations.executive_mcp.schemas import MAX_RESPONSE_BYTES, RESULT_SCHEMA
from integrations.hermes_runtime.errors import RuntimeRefusal
from .agentos_memory_provider import AgentOsBinding, DEFAULT_BUDGET
from .native_executive_consumer import (
    CONTEXT_TOOLS_SCHEMA_DIGEST, CURRENT_CONTEXT_TOOLS_SCHEMA_DIGEST, DISCOVERY_TOOLS_SCHEMA_DIGEST,
    ExecutiveContextConsumerPublication, _NativeMcpCaller, workspace_principal_frame)

MAX_MCP_RESULT_BYTES = MAX_RESPONSE_BYTES - 4096
_E1_KEYS = frozenset({"schema", "tool", "ok", "server_version", "mode", "generated_at",
                      "grounding", "data", "degraded", "bounded", "error"})


def _refuse():
    raise RuntimeRefusal("NATIVE_AGENTOS_CONTEXT_UNAVAILABLE")


def expected_context(publication):
    if type(publication) is not ExecutiveContextConsumerPublication:
        _refuse()
    return {name: getattr(publication, name) for name in (
        "work_ref", "principal_binding_digest", "mission_authority_ref", "authority_generation_digest")}


def _no_extras(value):
    extra = value.model_extra
    return extra is None or (type(extra) is dict and not extra)


def decode_native_tool_result(raw, *, limit=MAX_MCP_RESULT_BYTES, sdk_types=None):
    """One complete, bounded native SDK text result; no transport or owner."""
    if sdk_types is None:
        from mcp import types as sdk_types
    try:
        if type(raw) is not sdk_types.CallToolResult or not _no_extras(raw):
            _refuse()
        fields = set(sdk_types.CallToolResult.model_fields)
        if fields == {"meta", "content", "isError", "structuredContent"}:
            is_error, structured = raw.isError, raw.structuredContent
        elif fields == {"meta", "content", "is_error", "structured_content", "result_type"}:
            # MCP 2.3 moved the Python names while preserving wire aliases.
            # Only a complete result qualifies; pending/input-required results
            # cannot silently become a current context acquisition.
            if raw.result_type != "complete":
                _refuse()
            is_error, structured = raw.is_error, raw.structured_content
        else:
            _refuse()
        if (is_error is not False or raw.meta is not None or structured is not None
                or type(raw.content) is not list or len(raw.content) != 1):
            _refuse()
        block = raw.content[0]
        if (type(block) is not sdk_types.TextContent or not _no_extras(block)
                or block.type != "text" or block.meta is not None or block.annotations is not None
                or type(block.text) is not str or not 0 < len(block.text) <= limit):
            _refuse()
        encoded = block.text.encode("utf-8", "strict")
        if len(encoded) > limit:
            _refuse()
        # The outer bound includes SDK text escaping and the real result fields.
        # All fields/extras have been checked before invoking the serializer.
        if len(raw.model_dump_json(by_alias=True).encode("utf-8", "strict")) > limit:
            _refuse()
        return wire.decode(encoded, limit=limit)
    except RuntimeRefusal:
        raise
    except Exception:
        _refuse()


def decode_context_result(raw, publication, *, sdk_types=None):
    """Accept only the actual reviewed SDK producer shape; retain raw bytes.

    SDK parsing has already consumed the outer JSON-RPC framing. Duplicate
    keys are proved absent in the surviving text and decoded bundle, not in
    outer framing that the SDK may have discarded before this boundary.
    """
    if sdk_types is None:
        from mcp import types as sdk_types
    try:
        if type(publication) is not ExecutiveContextConsumerPublication:
            _refuse()
        current = publication.workspace_principal is not None
        tool = wire.CURRENT_TOOL if current else wire.TOOL
        value = decode_native_tool_result(raw, sdk_types=sdk_types)
        if (type(value) is not dict or set(value) != _E1_KEYS
                or value["schema"] != RESULT_SCHEMA
                or value["tool"] != tool or value["ok"] is not True
                or publication.mcp.server_version != "1.0.0"
                or value["server_version"] != publication.mcp.server_version
                or value["mode"] != "readonly" or type(value["grounding"]) is not dict
                or value["grounding"] or type(value["degraded"]) is not list or value["degraded"]
                or type(value["bounded"]) is not list or value["bounded"] or value["error"] is not None):
            _refuse()
        generated = value["generated_at"]
        if type(generated) is not str or not 0 < len(generated) <= 64 or not generated.endswith("Z"):
            _refuse()
        parsed = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            _refuse()
        if current:
            validator = wire.validate_discovery_result if publication.discovery else wire.validate_current_result
            return validator(value["data"], expected_context=expected_context(publication),
                capability_profile_digest=publication.capability_profile_digest,
                expected_workspace_principal=workspace_principal_frame(publication))
        return wire.validate_result(value["data"], expected_context=expected_context(publication),
                                    capability_profile_digest=publication.capability_profile_digest)
    except RuntimeRefusal:
        raise
    except Exception:
        _refuse()


class NativeAgentOsContextRead:
    """A stable read port for one publication and original native connection.

    The provider separately guards its live claim around acquisition/delivery.
    This port is stable across claims; it never captures the first claim as a
    substitute for the host's subsequent native ownership checks.
    """

    def __init__(self, *, publication: ExecutiveContextConsumerPublication,
                 server: Any, session: Any, loop: Any, currentness: Callable[[], bool],
                 binding_current: Callable[[AgentOsBinding], bool] | None = None):
        if (type(publication) is not ExecutiveContextConsumerPublication
                or publication.tools_schema_digest != (DISCOVERY_TOOLS_SCHEMA_DIGEST if publication.discovery else CURRENT_CONTEXT_TOOLS_SCHEMA_DIGEST
                    if publication.workspace_principal is not None else CONTEXT_TOOLS_SCHEMA_DIGEST)
                or not callable(currentness)):
            _refuse()
        self.publication = publication
        self.currentness = currentness
        self.binding_current = binding_current
        self.caller = _NativeMcpCaller(server=server, session=session, loop=loop,
                                      timeout=30.0, currentness=currentness, wait_for_lock=False)

    def read(self, binding: AgentOsBinding, *, budget: int):
        if (type(binding) is not AgentOsBinding or binding.owner_root is not None
                or binding.workstream != self.publication.work_ref
                or type(budget) is not int or budget != DEFAULT_BUDGET
                or self.currentness() is not True):
            _refuse()
        options = {} if self.binding_current is None else {
            "currentness": lambda: self.binding_current(binding) is True}
        tool = wire.CURRENT_TOOL if self.publication.workspace_principal is not None else wire.TOOL
        raw = self.caller.call(tool, {"work_ref": self.publication.work_ref}, **options)
        result = decode_context_result(raw, self.publication)
        if (self.currentness() is not True
                or (self.binding_current is not None and self.binding_current(binding) is not True)):
            _refuse()
        return result
