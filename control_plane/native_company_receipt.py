"""Pure native MCP-result projection; this is neither authority nor consumption.

The adapter supplies its current parent thread/turn and sealed MCP config name.
A later Runtime-owned consumer must join this receipt to exact completed native
turn evidence and revalidate the current caller and answer carrier.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_MAX_RESPONSE_BYTES,
    COMPANY_CONSULTATION_RESULT_SCHEMA,
    COMPANY_CONSULTATION_SERVER_IDENTITY,
    COMPANY_CONSULTATION_SERVER_VERSION,
    canonical_company_consultation_json,
    CompanyConsultationToolError,
)

_REF = re.compile(r"consult-[0-9a-f]{32}\Z")
_ENVELOPE = {"schema", "tool", "ok", "server_identity", "server_version", "data", "error"}


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _nonfinite(_value):
    raise ValueError("nonfinite JSON value")


def project_company_read(
    params: object, *, server_name: str, thread_id: str, turn_id: str,
) -> dict[str, Any] | None:
    """Return only bounded digests/ref for one exact successful native read.

    Accept the pinned App Server camelCase wire, not a lookalike fake protocol.
    Unrelated, ambiguous and malformed notifications yield no receipt. No raw
    tool arguments, answer text, evidence URLs or native item id escape.
    """
    try:
        if (not isinstance(params, dict) or not all(isinstance(v, str) and v
                for v in (server_name, thread_id, turn_id))
                or params.get("threadId") != thread_id or params.get("turnId") != turn_id
                or type(params.get("completedAtMs")) is not int
                or not 0 <= params["completedAtMs"] <= (1 << 63) - 1):
            return None
        item = params.get("item")
        if (not isinstance(item, dict) or item.get("type") != "mcpToolCall"
                or item.get("server") != server_name or item.get("tool") != "company.consultation"
                or item.get("status") != "completed" or item.get("error") is not None
                or not isinstance(item.get("id"), str) or not item["id"]
                or len(item["id"].encode("utf-8")) > 512):
            return None
        arguments = item.get("arguments")
        if (not isinstance(arguments, dict) or set(arguments) != {"consultation_ref"}
                or not isinstance(arguments["consultation_ref"], str)
                or _REF.fullmatch(arguments["consultation_ref"]) is None):
            return None
        result = item.get("result")
        if (not isinstance(result, dict) or not set(result) <= {"content", "structuredContent", "_meta"}
                or not isinstance(result.get("content"), list) or len(result["content"]) != 1):
            return None
        text = result["content"][0]
        if (not isinstance(text, dict) or set(text) != {"type", "text"}
                or text["type"] != "text" or not isinstance(text["text"], str)
                or len(text["text"].encode("utf-8")) > COMPANY_CONSULTATION_MAX_RESPONSE_BYTES):
            return None
        envelope = json.loads(text["text"], object_pairs_hook=_unique_object, parse_constant=_nonfinite)
        if (not isinstance(envelope, dict) or set(envelope) != _ENVELOPE
                or envelope["schema"] != COMPANY_CONSULTATION_RESULT_SCHEMA
                or envelope["tool"] != "company.consultation" or envelope["ok"] is not True
                or envelope["server_identity"] != COMPANY_CONSULTATION_SERVER_IDENTITY
                or envelope["server_version"] != COMPANY_CONSULTATION_SERVER_VERSION
                or envelope["error"] is not None):
            return None
        structured = result.get("structuredContent")
        canonical = canonical_company_consultation_json(envelope)
        if text["text"].encode("utf-8") != canonical:
            return None
        if structured is not None and canonical_company_consultation_json(structured) != canonical:
            return None
        if len(canonical) > COMPANY_CONSULTATION_MAX_RESPONSE_BYTES:
            return None
        data = envelope["data"]
        if (not isinstance(data, dict) or data.get("consultation_ref") != arguments["consultation_ref"]
                or data.get("state") != "ANSWER_AVAILABLE" or data.get("body_status") != "AVAILABLE"
                or "blocker" not in data or data["blocker"] is not None):
            return None
        answer = data.get("answer")
        if (not isinstance(answer, dict) or set(answer) != {"text", "evidence_refs"}
                or not isinstance(answer["text"], str) or not answer["text"]
                or not isinstance(answer["evidence_refs"], list)):
            return None
        result_digest = hashlib.sha256(canonical).hexdigest()
        evidence = {"completedAtMs": params["completedAtMs"], "threadId": thread_id,
                    "turnId": turn_id, "id": item["id"], "server": server_name,
                    "tool": item["tool"], "status": item["status"],
                    "arguments": arguments, "result_sha256": result_digest}
        return {"schema": "mastermind.native_company_read_receipt.v1",
                "consultation_ref": arguments["consultation_ref"],
                "result_sha256": result_digest,
                "native_item_sha256": hashlib.sha256(
                    canonical_company_consultation_json(evidence)).hexdigest()}
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError, CompanyConsultationToolError):
        return None
