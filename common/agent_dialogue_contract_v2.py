"""Worker-aware Active-Session Dialogue V2 contract."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Mapping

from common.agent_dialogue_contract import (
    A0_PROVEN_CHATGPT_TRAILER,
    FABLE_MESSAGE_TYPES,
    MESSAGE_TYPES,
    SOL_MESSAGE_TYPES,
    DialogueContractError,
    MAX_EVIDENCE_REFS,
    MAX_FRAME_BYTES,
    MAX_SUMMARY_CHARS,
    semantic_fingerprint,
    validate_applies_to,
    validate_body,
    validate_commission_ref,
    validate_evidence_ref,
)

MESSAGE_SCHEMA_V2 = "mastermind.agent_dialogue.v2"
MESSAGE_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_V2"
PARENT_SCHEMA_V2 = "mastermind.agent_dialogue_parent.v2"
PARENT_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_PARENT_V2"
TURN_WATCH_MODE_V1 = "turn_watch_v1"

_OPERATION_KEY_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{7,127}\Z")
_WORK_REF_RE = re.compile(r"\AWS:[A-Z0-9][A-Z0-9-]{1,63}\Z")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")
_MESSAGE_KEY_RE = re.compile(r"\Aasd-[a-z0-9][a-z0-9-]{7,95}\Z")
_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_SHA64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_UTC_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,})"
)
_SLACK_MENTION_SHAPED_RE = re.compile(r"<@[UW][A-Z0-9]{8,31}(?:\|[^>\r\n]{1,80})?>")

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
MESSAGE_KEYS_V2 = frozenset(
    {
        "schema",
        "message_key",
        "message_type",
        "work_ref",
        "commission_ref",
        "session_ref",
        "actor_ref",
        "reply_to_message_key",
        "applies_to",
        "summary",
        "body",
        "evidence_refs",
        "requires_response",
        "created_at",
        "fingerprint",
    }
)
_EXECUTIVE_ACTOR_KEYS = frozenset({"kind", "seat", "reasoning_surface"})
_WORKER_ACTOR_KEYS = frozenset({"kind", "job_id", "attempt_id", "worker_id"})
_REPOSITORY_APPLICABILITY_KEYS = frozenset(
    {"kind", "repository", "head_sha", "pr"}
)
_EXECUTIVE_APPLICABILITY_KEYS = frozenset(
    {"kind", "job_id", "attempt_id", "worker_id"}
)
_EXECUTIVE_SEATS = frozenset({"chairman", "ceo", "coo"})


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
        if (
            _SECRET_SHAPED_RE.search(value) is not None
            or "\u2028" in value
            or "\u2029" in value
            or _SLACK_MENTION_SHAPED_RE.search(value) is not None
        ):
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


def _require_identity_string(value: Any, *, max_chars: int = 200) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= max_chars:
        raise DialogueContractError("MESSAGE_INVALID")
    if (
        value.strip() != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or _SECRET_SHAPED_RE.search(value) is not None
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def _require_text(
    value: Any,
    *,
    min_chars: int = 1,
    max_chars: int = 900,
) -> str:
    if not isinstance(value, str) or not min_chars <= len(value) <= max_chars:
        raise DialogueContractError("MESSAGE_INVALID")
    if (
        value.strip() != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or _SECRET_SHAPED_RE.search(value) is not None
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def _require_bool(value: Any) -> bool:
    if type(value) is not bool:
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def _validate_evidence_refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE_REFS:
        raise DialogueContractError("MESSAGE_INVALID")
    refs = [validate_evidence_ref(item) for item in value]
    if len(refs) != len(set(refs)):
        raise DialogueContractError("MESSAGE_INVALID")
    return refs


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


def validate_actor_ref(value: Any) -> dict[str, Any]:
    """Validate one trusted structured dialogue actor reference."""

    _reject_secret_shaped_leaves(value, code="MESSAGE_INVALID")
    if not isinstance(value, dict):
        raise DialogueContractError("MESSAGE_INVALID")

    kind = value.get("kind")
    if kind == "executive_surface":
        if set(value) != _EXECUTIVE_ACTOR_KEYS:
            raise DialogueContractError("MESSAGE_INVALID")
        seat = value["seat"]
        if seat not in _EXECUTIVE_SEATS:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "kind": "executive_surface",
            "seat": seat,
            "reasoning_surface": _require_identity_string(
                value["reasoning_surface"],
                max_chars=100,
            ),
        }

    if kind == "worker_attempt":
        if set(value) != _WORKER_ACTOR_KEYS:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "kind": "worker_attempt",
            "job_id": _require_identity_string(value["job_id"]),
            "attempt_id": _require_identity_string(value["attempt_id"]),
            "worker_id": _require_identity_string(value["worker_id"]),
        }

    raise DialogueContractError("MESSAGE_INVALID")


def validate_applies_to_v2(value: Any) -> dict[str, Any]:
    """Validate one typed V2 repository or Executive Attempt applicability."""

    _reject_secret_shaped_leaves(value, code="MESSAGE_INVALID")
    if not isinstance(value, dict):
        raise DialogueContractError("MESSAGE_INVALID")

    kind = value.get("kind")
    if kind == "repository":
        if set(value) != _REPOSITORY_APPLICABILITY_KEYS:
            raise DialogueContractError("MESSAGE_INVALID")
        repository = validate_applies_to(
            {
                "repository": value["repository"],
                "head_sha": value["head_sha"],
                "pr": value["pr"],
            }
        )
        return {"kind": "repository", **repository}

    if kind == "executive_attempt":
        if set(value) != _EXECUTIVE_APPLICABILITY_KEYS:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "kind": "executive_attempt",
            "job_id": _require_identity_string(value["job_id"]),
            "attempt_id": _require_identity_string(value["attempt_id"]),
            "worker_id": _require_identity_string(value["worker_id"]),
        }

    raise DialogueContractError("MESSAGE_INVALID")


def _allowed_message_types(actor_ref: Mapping[str, Any]) -> frozenset[str]:
    if actor_ref["kind"] == "worker_attempt":
        return FABLE_MESSAGE_TYPES
    seat = actor_ref["seat"]
    if seat == "coo":
        return FABLE_MESSAGE_TYPES
    if seat == "ceo":
        return MESSAGE_TYPES
    if seat == "chairman":
        return SOL_MESSAGE_TYPES
    raise DialogueContractError("MESSAGE_INVALID")


def _validate_worker_attempt_join(
    actor_ref: Mapping[str, Any],
    applies_to: Mapping[str, Any],
) -> None:
    if actor_ref["kind"] != "worker_attempt":
        return
    if applies_to["kind"] != "executive_attempt":
        raise DialogueContractError("MESSAGE_INVALID")
    for key in ("job_id", "attempt_id", "worker_id"):
        if actor_ref[key] != applies_to[key]:
            raise DialogueContractError("MESSAGE_INVALID")


def validate_message_v2(value: Any) -> dict[str, Any]:
    """Validate and normalize one closed worker-aware V2 dialogue message."""

    _reject_secret_shaped_leaves(value, code="MESSAGE_INVALID")
    if not isinstance(value, dict) or set(value) != MESSAGE_KEYS_V2:
        raise DialogueContractError("MESSAGE_INVALID")
    if value["schema"] != MESSAGE_SCHEMA_V2:
        raise DialogueContractError("MESSAGE_INVALID")

    message_key = value["message_key"]
    if (
        not isinstance(message_key, str)
        or _MESSAGE_KEY_RE.fullmatch(message_key) is None
    ):
        raise DialogueContractError("MESSAGE_INVALID")

    message_type = value["message_type"]
    if message_type not in MESSAGE_TYPES:
        raise DialogueContractError("MESSAGE_INVALID")

    work_ref = value["work_ref"]
    if not isinstance(work_ref, str) or _WORK_REF_RE.fullmatch(work_ref) is None:
        raise DialogueContractError("MESSAGE_INVALID")

    session_ref = value["session_ref"]
    if (
        not isinstance(session_ref, str)
        or _SESSION_REF_RE.fullmatch(session_ref) is None
    ):
        raise DialogueContractError("MESSAGE_INVALID")

    reply_to = value["reply_to_message_key"]
    if reply_to is not None and (
        not isinstance(reply_to, str)
        or _MESSAGE_KEY_RE.fullmatch(reply_to) is None
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    if message_type in SOL_MESSAGE_TYPES and reply_to is None:
        raise DialogueContractError("MESSAGE_INVALID")

    actor_ref = validate_actor_ref(value["actor_ref"])
    if message_type not in _allowed_message_types(actor_ref):
        raise DialogueContractError("MESSAGE_INVALID")
    applies_to = validate_applies_to_v2(value["applies_to"])
    _validate_worker_attempt_join(actor_ref, applies_to)

    requires_response = _require_bool(value["requires_response"])
    if requires_response is not (message_type in {"DECISION_REQUEST", "BLOCKED"}):
        raise DialogueContractError("MESSAGE_INVALID")

    fingerprint = value["fingerprint"]
    if not isinstance(fingerprint, str) or _SHA64_RE.fullmatch(fingerprint) is None:
        raise DialogueContractError("MESSAGE_INVALID")

    normalized = {
        "schema": MESSAGE_SCHEMA_V2,
        "message_key": message_key,
        "message_type": message_type,
        "work_ref": work_ref,
        "commission_ref": validate_commission_ref(value["commission_ref"]),
        "session_ref": session_ref,
        "actor_ref": actor_ref,
        "reply_to_message_key": reply_to,
        "applies_to": applies_to,
        "summary": _require_text(
            value["summary"],
            max_chars=MAX_SUMMARY_CHARS,
        ),
        "body": validate_body(message_type, value["body"]),
        "evidence_refs": _validate_evidence_refs(value["evidence_refs"]),
        "requires_response": requires_response,
        "created_at": _require_utc(
            value["created_at"],
            code="MESSAGE_INVALID",
        ),
        "fingerprint": fingerprint,
    }
    if semantic_fingerprint(normalized) != fingerprint:
        raise DialogueContractError("FINGERPRINT_MISMATCH")
    return normalized


def build_message_v2(value: Mapping[str, Any]) -> dict[str, Any]:
    """Build one V2 message with deterministic semantic identity."""

    raw = dict(value)
    if "fingerprint" in raw and raw["fingerprint"] not in ("", None):
        raise DialogueContractError("MESSAGE_INVALID")
    raw["fingerprint"] = ""
    raw["fingerprint"] = semantic_fingerprint(raw)
    return validate_message_v2(raw)


def render_message_v2(value: Mapping[str, Any]) -> str:
    message = validate_message_v2(dict(value))
    text = f"{MESSAGE_DISCRIMINATOR_V2}\n{_canonical_json(message)}"
    if len(text.encode("utf-8")) > MAX_FRAME_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")
    return text


def parse_message_frame_v2(raw: str | bytes) -> dict[str, Any]:
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
    if lines[0] != MESSAGE_DISCRIMINATOR_V2 or not lines[1]:
        raise DialogueContractError("FRAME_INVALID")
    if len(lines) == 3 and lines[2] != A0_PROVEN_CHATGPT_TRAILER:
        raise DialogueContractError("TRAILER_REFUSED")

    canonical_span = f"{lines[0]}\n{lines[1]}"
    if len(canonical_span.encode("utf-8")) > MAX_FRAME_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")
    document = _strict_loads(lines[1])
    normalized = validate_message_v2(document)
    if len(lines) == 3:
        actor = normalized["actor_ref"]
        if not (
            actor["kind"] == "executive_surface"
            and actor["seat"] in {"ceo", "chairman"}
            and actor["reasoning_surface"].lower() == "chatgpt"
        ):
            raise DialogueContractError("TRAILER_REFUSED")
    if lines[1] != _canonical_json(normalized):
        raise DialogueContractError("FRAME_INVALID")
    return normalized


def presentation_label(actor_ref: Mapping[str, Any]) -> str:
    """Derive one non-human, non-authoritative Slack presentation label."""

    actor = validate_actor_ref(dict(actor_ref))
    if actor["kind"] == "worker_attempt":
        suffix = hashlib.sha256(
            actor["worker_id"].encode("utf-8")
        ).hexdigest()[:10].upper()
        return f"Mastermind · Worker {suffix}"

    seat = actor["seat"]
    surface = actor["reasoning_surface"].lower()
    if seat == "ceo":
        if surface == "codex":
            return "Mastermind · Sol/Codex"
        if surface == "chatgpt":
            return "Mastermind · Sol/ChatGPT"
        return "Mastermind · Sol/Other"
    if seat == "coo":
        if surface == "claude":
            return "Mastermind · Fable"
        return "Mastermind · COO/Other"
    return "Mastermind · Executive"