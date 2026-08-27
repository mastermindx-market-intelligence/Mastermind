"""Worker-aware Active-Session Dialogue V2 contract."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Mapping

from integrations.slack_agent_dialogue.contract import (
    A0_PROVEN_CHATGPT_TRAILER,
    DialogueContractError,
    MAX_FRAME_BYTES,
    semantic_fingerprint,
    validate_commission_ref,
)

MESSAGE_SCHEMA_V2 = "mastermind.agent_dialogue.v2"
MESSAGE_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_V2"
PARENT_SCHEMA_V2 = "mastermind.agent_dialogue_parent.v2"
PARENT_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_PARENT_V2"
TURN_WATCH_MODE_V1 = "turn_watch_v1"

_OPERATION_KEY_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{7,127}\Z")
_WORK_REF_RE = re.compile(r"\AWS:[A-Z0-9][A-Z0-9-]{1,63}\Z")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")
_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_SHA64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_UTC_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,})"
)

PARENT_KEYS_V2 = frozenset(
    {
        "schema",
        "work_ref",
        "commission_ref",
        "session_ref",
        "operation_key",
        "watch_mode",
        "allowed_sol_user_ids",
        "created_at",
        "fingerprint",
    }
)


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise DialogueContractError("FRAME_INVALID") from None


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DialogueContractError("FRAME_INVALID")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise DialogueContractError("FRAME_INVALID")


def _strict_loads(value: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except DialogueContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError):
        raise DialogueContractError("FRAME_INVALID") from None


def _reject_secret_shaped_leaves(value: Any, *, code: str) -> None:
    if isinstance(value, str):
        if _SECRET_SHAPED_RE.search(value) is not None:
            raise DialogueContractError(code)
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            _reject_secret_shaped_leaves(nested, code=code)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _reject_secret_shaped_leaves(nested, code=code)


def _require_utc(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise DialogueContractError(code)
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise DialogueContractError(code) from None
    return value


def validate_parent_v2(value: Any) -> dict[str, Any]:
    """Validate and normalize one closed V2 thread parent."""

    _reject_secret_shaped_leaves(value, code="PARENT_INVALID")
    if not isinstance(value, dict) or set(value) != PARENT_KEYS_V2:
        raise DialogueContractError("PARENT_INVALID")
    if value["schema"] != PARENT_SCHEMA_V2:
        raise DialogueContractError("PARENT_INVALID")

    work_ref = value["work_ref"]
    session_ref = value["session_ref"]
    operation_key = value["operation_key"]
    watch_mode = value["watch_mode"]
    allowed = value["allowed_sol_user_ids"]
    fingerprint = value["fingerprint"]

    if not isinstance(work_ref, str) or _WORK_REF_RE.fullmatch(work_ref) is None:
        raise DialogueContractError("PARENT_INVALID")
    if not isinstance(session_ref, str) or _SESSION_REF_RE.fullmatch(session_ref) is None:
        raise DialogueContractError("PARENT_INVALID")
    if (
        not isinstance(operation_key, str)
        or _OPERATION_KEY_RE.fullmatch(operation_key) is None
    ):
        raise DialogueContractError("PARENT_INVALID")
    if watch_mode is not None and watch_mode != TURN_WATCH_MODE_V1:
        raise DialogueContractError("PARENT_INVALID")
    if not isinstance(allowed, list) or not 1 <= len(allowed) <= 8:
        raise DialogueContractError("PARENT_INVALID")
    if any(
        not isinstance(user_id, str) or _SLACK_USER_ID_RE.fullmatch(user_id) is None
        for user_id in allowed
    ):
        raise DialogueContractError("PARENT_INVALID")
    if allowed != sorted(set(allowed)):
        raise DialogueContractError("PARENT_INVALID")
    if not isinstance(fingerprint, str) or _SHA64_RE.fullmatch(fingerprint) is None:
        raise DialogueContractError("PARENT_INVALID")

    try:
        commission_ref = validate_commission_ref(value["commission_ref"])
    except DialogueContractError:
        raise DialogueContractError("PARENT_INVALID") from None

    normalized = {
        "schema": PARENT_SCHEMA_V2,
        "work_ref": work_ref,
        "commission_ref": commission_ref,
        "session_ref": session_ref,
        "operation_key": operation_key,
        "watch_mode": watch_mode,
        "allowed_sol_user_ids": allowed,
        "created_at": _require_utc(value["created_at"], code="PARENT_INVALID"),
        "fingerprint": fingerprint,
    }
    if semantic_fingerprint(normalized) != fingerprint:
        raise DialogueContractError("FINGERPRINT_MISMATCH")
    return normalized


def build_parent_v2(value: Mapping[str, Any]) -> dict[str, Any]:
    """Build one V2 parent with deterministic semantic identity."""

    raw = dict(value)
    if "fingerprint" in raw and raw["fingerprint"] not in {"", None}:
        raise DialogueContractError("PARENT_INVALID")
    raw["fingerprint"] = ""
    raw["fingerprint"] = semantic_fingerprint(raw)
    return validate_parent_v2(raw)


def render_parent_v2(value: Mapping[str, Any]) -> str:
    parent = validate_parent_v2(dict(value))
    text = f"{PARENT_DISCRIMINATOR_V2}\n{_canonical_json(parent)}"
    if len(text.encode("utf-8")) > MAX_FRAME_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")
    return text


def parse_parent_frame_v2(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise DialogueContractError("FRAME_INVALID") from None
    elif isinstance(raw, str):
        text = raw
    else:
        raise DialogueContractError("FRAME_INVALID")

    lines = text.split("\n")
    if len(lines) not in {2, 3}:
        raise DialogueContractError("FRAME_INVALID")
    if lines[0] != PARENT_DISCRIMINATOR_V2 or not lines[1]:
        raise DialogueContractError("FRAME_INVALID")
    if len(lines) == 3 and lines[2] != A0_PROVEN_CHATGPT_TRAILER:
        raise DialogueContractError("TRAILER_REFUSED")

    canonical_span = f"{lines[0]}\n{lines[1]}"
    if len(canonical_span.encode("utf-8")) > MAX_FRAME_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")
    document = _strict_loads(lines[1])
    normalized = validate_parent_v2(document)
    if lines[1] != _canonical_json(normalized):
        raise DialogueContractError("FRAME_INVALID")
    return normalized
