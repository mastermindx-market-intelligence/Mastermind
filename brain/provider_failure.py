"""Typed provider-failure records for the Claude/Codex reasoning bridges.

The Claude Agent SDK surfaces a failed turn as ``Exception("Claude Code returned
an error result: success")`` — a label that reads as success and carries no
cause — while the actual cause rode the earlier ``AssistantMessage.error``
literal (e.g. ``"authentication_failed"``).  This module TYPES such failures
from evidence the handler already sees and nothing else.

EVIDENCE ONLY.  ``classify`` is pure: no I/O, no logging, no imports from
brain/bot/app, and its records must NEVER be read by any retry, failover,
key-cooling or submission decision (failover-on-typed-failure is a reserved
seat decision).  Records never carry response text, prompt text, exception
reprs, stderr, token counts or credential material — only one allowlisted
needle literal, small ints/bools, and bounded subtype words.
"""
from __future__ import annotations

import re

SCHEMA = "mastermind.bot.provider_failure.v1"

KINDS = ("credential", "quota", "availability", "transport", "tool_contract", "schema",
         "stale_evidence", "deadline", "application", "unclassified")

# The SDK's AssistantMessageError literal set — exact strings.
SDK_ASSISTANT_ERRORS = {
    "authentication_failed": "credential",
    "billing_error": "quota",
    "rate_limit": "quota",
    "server_error": "availability",
    "invalid_request": "schema",
    "unknown": "unclassified",
}

_RESULT_SUBTYPE_RE = re.compile(r"^[a-z_]{1,40}$")

# Error-text needles, evaluated in group order; first match wins.  Numeric
# needles only match on word boundaries so "4012" never reads as a 401.
_NUMERIC_NEEDLES = frozenset({"401", "429", "529"})
_NEEDLE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("credential", (
        "401", "revoked", "authentication_failed", "failed to authenticate",
        "invalid api key", "unauthorized", "access token could not be refreshed",
    )),
    ("quota", (
        "weekly limit", "session limit", "usage limit", "rate_limit", "rate limit", "429",
    )),
    ("availability", (
        "all pool keys cooling", "all pool keys dead", "overloaded", "529",
        "no shared codex or claude oauth provider is available",
        "shared provider waterfall exhausted",
    )),
    ("transport", ("timeout", "timed out", "connection reset", "cliconnectionerror")),
    ("tool_contract", ("failed write tool call",)),
)

_EVIDENCE_CAP = 80


def sdk_assistant_error_literal(value) -> str | None:
    """The literal when ``value`` is a str exactly in the SDK error set, else None."""
    return value if isinstance(value, str) and value in SDK_ASSISTANT_ERRORS else None


def _default_record() -> dict:
    return {
        "schema": SCHEMA,
        "kind": "unclassified",
        "evidence": None,
        "source": None,
        "sdk_assistant_error": None,
        "sdk_result_subtype": None,
        "sdk_result_is_error": None,
        "api_error_status": None,
        "label_misleading": False,
        "tool_activity_observed": None,
        "provider": None,
        "key_id": None,
    }


def _match_needle(needle: str, text: str) -> bool:
    if needle in _NUMERIC_NEEDLES:
        return re.search(rf"\b{needle}\b", text) is not None
    return needle in text


def _classify_text(text: str) -> tuple[str, str] | None:
    for kind, needles in _NEEDLE_GROUPS:
        for needle in needles:
            if _match_needle(needle, text):
                return kind, needle[:_EVIDENCE_CAP]
    return None


def classify(*, error=None, evidence=None, provider=None, key_id=None, tools_used=None) -> dict:
    """Type one provider failure.  Always returns the full record; never raises."""
    record = _default_record()
    try:
        box = evidence if isinstance(evidence, dict) else {}
        text = "" if error is None else str(error)

        # Independent descriptive fields (computed from inputs whatever kind wins).
        literal = sdk_assistant_error_literal(box.get("assistant_error"))
        record["sdk_assistant_error"] = literal
        _subtype = box.get("result_subtype")
        if isinstance(_subtype, str) and _RESULT_SUBTYPE_RE.fullmatch(_subtype):
            record["sdk_result_subtype"] = _subtype
        _is_error = box.get("result_is_error")
        if isinstance(_is_error, bool):
            record["sdk_result_is_error"] = _is_error
        _status = box.get("api_error_status")
        if isinstance(_status, int) and not isinstance(_status, bool):
            record["api_error_status"] = _status
        _tool_seen = box.get("tool_activity_observed")
        if isinstance(_tool_seen, bool):
            record["tool_activity_observed"] = _tool_seen
        elif isinstance(tools_used, list) and tools_used:
            record["tool_activity_observed"] = True
        if isinstance(provider, str):
            record["provider"] = provider
        if isinstance(key_id, str):
            record["key_id"] = key_id
        record["label_misleading"] = (
            "error result: success" in text.lower()
            or (box.get("result_is_error") is True and box.get("result_subtype") == "success")
        )

        # Kind: first match wins.
        matched: tuple[str, str, str] | None = None
        if literal is not None and literal != "unknown":
            matched = (SDK_ASSISTANT_ERRORS[literal],
                       f"sdk_assistant_error:{literal}", "sdk_assistant_error")
        if matched is None:
            status = record["api_error_status"]
            if status is not None:
                kind = {401: "credential", 403: "credential", 429: "quota",
                        500: "availability", 502: "availability", 503: "availability",
                        529: "availability", 400: "schema"}.get(status)
                if kind is not None:
                    matched = (kind, f"api_error_status:{status}", "api_error_status")
        if matched is None and record["sdk_result_subtype"] == "error_max_turns":
            matched = ("deadline", "sdk_result_subtype:error_max_turns", "sdk_result_subtype")
        if matched is None:
            text_match = _classify_text(text.lower())
            if text_match is not None:
                matched = (text_match[0], text_match[1], "error_text")
        if matched is not None:
            record["kind"], record["evidence"], record["source"] = matched
        return record
    except Exception:
        return _default_record()
