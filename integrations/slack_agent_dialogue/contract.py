"""Strict Active-Session Dialogue framing and authority contracts.

This module is transport-neutral and development-unarmed. It parses no prose,
executes no command, performs no network request, and persists no state.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

MESSAGE_SCHEMA = "mastermind.agent_dialogue.v1"
PARENT_SCHEMA = "mastermind.agent_dialogue_parent.v1"
MESSAGE_DISCRIMINATOR = "MMX/AGENT_DIALOGUE_V1"
PARENT_DISCRIMINATOR = "MMX/AGENT_DIALOGUE_PARENT_V1"
MAX_FRAME_BYTES = 4500
MAX_SUMMARY_CHARS = 500
MAX_TEXT_CHARS = 900
MAX_EVIDENCE_REFS = 8
MAX_OPTIONS = 3

FABLE_MESSAGE_TYPES = frozenset({"ACK", "DECISION_REQUEST", "BLOCKED", "PROGRESS", "RESULT"})
SOL_MESSAGE_TYPES = frozenset({"RULING", "CONTINUE", "STOP", "AMENDMENT_AVAILABLE"})
MESSAGE_TYPES = FABLE_MESSAGE_TYPES | SOL_MESSAGE_TYPES
AUTHORITY_CLASSES = frozenset({"WITHIN_COMMISSION", "CANONICAL_REF_REQUIRED", "CHAIRMAN_REQUIRED"})
REPLY_DISPOSITIONS = frozenset({"CONTINUE", "STOP", "CANONICAL_REF_REQUIRED", "CHAIRMAN_REQUIRED"})

ERROR_CODES = frozenset(
    {
        "AUTHORITY_REFUSED",
        "FINGERPRINT_MISMATCH",
        "FRAME_INVALID",
        "FRAME_TOO_LARGE",
        "MESSAGE_INVALID",
        "PARENT_INVALID",
        "REPLY_CONTEXT_MISMATCH",
        "TRAILER_REFUSED",
    }
)

_REPOSITORY_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}\Z")
_PATH_RE = re.compile(r"\A[A-Za-z0-9_.\-/]{1,300}\Z")
_SHA40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_WORK_REF_RE = re.compile(r"\AWS:[A-Z0-9][A-Z0-9-]{1,63}\Z")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")
_MESSAGE_KEY_RE = re.compile(r"\Aasd-[a-z0-9][a-z0-9-]{7,95}\Z")
_OPTION_ID_RE = re.compile(r"\Aopt-[a-z0-9][a-z0-9-]{1,31}\Z")
_CODE_RE = re.compile(r"\A[A-Z][A-Z0-9_]{1,63}\Z")
_STAGE_RE = re.compile(r"\A[a-z0-9][a-z0-9_-]{1,63}\Z")
_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_UTC_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_GITHUB_PR_RE = re.compile(
    r"\Ahttps://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)\Z"
)
_GITHUB_COMMIT_RE = re.compile(
    r"\Ahttps://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/commit/([0-9a-f]{40})\Z"
)
_GITHUB_BLOB_RE = re.compile(
    r"\Ahttps://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/blob/([0-9a-f]{40})/([A-Za-z0-9_.\-/]+)\Z"
)
_LINEAR_RE = re.compile(
    r"\Ahttps://linear\.app/mastermindx/issue/(MAS-[1-9][0-9]*)(?:/[A-Za-z0-9-]+)?\Z"
)
_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[abprs]-[A-Za-z0-9-]{10,}|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})"
)
A0_PROVEN_CHATGPT_TRAILER = "*Sent using* <@U0BRGTF1H26|ChatGPT>"

MESSAGE_KEYS = frozenset(
    {
        "schema",
        "message_key",
        "message_type",
        "work_ref",
        "commission_ref",
        "session_ref",
        "seat_ref",
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
PARENT_KEYS = frozenset(
    {
        "schema",
        "work_ref",
        "commission_ref",
        "session_ref",
        "allowed_sol_user_ids",
        "created_at",
        "fingerprint",
    }
)


class DialogueContractError(RuntimeError):
    """One closed contract refusal code."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown dialogue contract error code")
        super().__init__(code)
        self.code = code


class TrustedAuthorityPolicy(Protocol):
    """Canonical commission/policy classification injected outside model text."""

    def minimum_authority(
        self,
        *,
        request: Mapping[str, Any],
        option: Mapping[str, Any],
    ) -> str: ...


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
        raise DialogueContractError("MESSAGE_INVALID") from None


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


def _require_exact_keys(value: Any, keys: frozenset[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise DialogueContractError(code)
    return value


def _require_string(value: Any, *, min_chars: int = 1, max_chars: int = MAX_TEXT_CHARS) -> str:
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


def _require_utc(value: Any) -> str:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise DialogueContractError("MESSAGE_INVALID") from None
    return value


def _validate_repository(value: Any) -> str:
    if not isinstance(value, str) or _REPOSITORY_RE.fullmatch(value) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def _validate_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or _PATH_RE.fullmatch(value) is None
        or value.startswith("/")
        or "//" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def validate_commission_ref(value: Any) -> dict[str, str]:
    item = _require_exact_keys(
        value,
        frozenset({"repository", "commit", "path", "content_sha256"}),
        "MESSAGE_INVALID",
    )
    repository = _validate_repository(item["repository"])
    commit = item["commit"]
    content_sha256 = item["content_sha256"]
    if not isinstance(commit, str) or _SHA40_RE.fullmatch(commit) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    if not isinstance(content_sha256, str) or _SHA64_RE.fullmatch(content_sha256) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    path = _validate_path(item["path"])
    return {
        "repository": repository,
        "commit": commit,
        "path": path,
        "content_sha256": content_sha256,
    }


def validate_applies_to(value: Any) -> dict[str, Any]:
    item = _require_exact_keys(
        value,
        frozenset({"repository", "head_sha", "pr"}),
        "MESSAGE_INVALID",
    )
    repository = _validate_repository(item["repository"])
    head_sha = item["head_sha"]
    pr = item["pr"]
    if head_sha is not None and (
        not isinstance(head_sha, str) or _SHA40_RE.fullmatch(head_sha) is None
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    if pr is not None:
        if not isinstance(pr, str):
            raise DialogueContractError("MESSAGE_INVALID")
        expected_prefix = f"{repository}#"
        if not pr.startswith(expected_prefix):
            raise DialogueContractError("MESSAGE_INVALID")
        try:
            number = int(pr[len(expected_prefix) :])
        except ValueError:
            raise DialogueContractError("MESSAGE_INVALID") from None
        if number <= 0 or head_sha is None:
            raise DialogueContractError("MESSAGE_INVALID")
    return {"repository": repository, "head_sha": head_sha, "pr": pr}


def validate_evidence_ref(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 500:
        raise DialogueContractError("MESSAGE_INVALID")
    parsed = urlsplit(value)
    if parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port:
        raise DialogueContractError("MESSAGE_INVALID")
    if parsed.scheme != "https":
        raise DialogueContractError("MESSAGE_INVALID")
    match = (
        _GITHUB_PR_RE.fullmatch(value)
        or _GITHUB_COMMIT_RE.fullmatch(value)
        or _GITHUB_BLOB_RE.fullmatch(value)
        or _LINEAR_RE.fullmatch(value)
    )
    if match is None:
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def _validate_evidence_refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE_REFS:
        raise DialogueContractError("MESSAGE_INVALID")
    refs = [validate_evidence_ref(item) for item in value]
    if len(refs) != len(set(refs)):
        raise DialogueContractError("MESSAGE_INVALID")
    return refs


def _validate_option(value: Any) -> dict[str, Any]:
    item = _require_exact_keys(
        value,
        frozenset({"id", "summary", "consequence", "disposition", "authority_effect"}),
        "MESSAGE_INVALID",
    )
    option_id = item["id"]
    if not isinstance(option_id, str) or _OPTION_ID_RE.fullmatch(option_id) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    disposition = item["disposition"]
    if disposition not in {"CONTINUE", "STOP"}:
        raise DialogueContractError("MESSAGE_INVALID")
    authority_effect = item["authority_effect"]
    if authority_effect not in {"NONE", "CANONICAL_REF_REQUIRED", "CHAIRMAN_REQUIRED"}:
        raise DialogueContractError("MESSAGE_INVALID")
    return {
        "id": option_id,
        "summary": _require_string(item["summary"], max_chars=400),
        "consequence": _require_string(item["consequence"], max_chars=600),
        "disposition": disposition,
        "authority_effect": authority_effect,
    }


def validate_body(message_type: str, value: Any) -> dict[str, Any]:
    if message_type == "ACK":
        item = _require_exact_keys(value, frozenset({"acknowledged"}), "MESSAGE_INVALID")
        if item["acknowledged"] is not True:
            raise DialogueContractError("MESSAGE_INVALID")
        return {"acknowledged": True}
    if message_type == "DECISION_REQUEST":
        item = _require_exact_keys(
            value,
            frozenset({"question", "outcome_impact", "options", "recommendation", "work_paused"}),
            "MESSAGE_INVALID",
        )
        raw_options = item["options"]
        if not isinstance(raw_options, list) or not 1 <= len(raw_options) <= MAX_OPTIONS:
            raise DialogueContractError("MESSAGE_INVALID")
        options = [_validate_option(option) for option in raw_options]
        option_ids = [option["id"] for option in options]
        if len(option_ids) != len(set(option_ids)):
            raise DialogueContractError("MESSAGE_INVALID")
        recommendation = item["recommendation"]
        if recommendation not in option_ids:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "question": _require_string(item["question"], max_chars=700),
            "outcome_impact": _require_string(item["outcome_impact"], max_chars=700),
            "options": options,
            "recommendation": recommendation,
            "work_paused": _require_bool(item["work_paused"]),
        }
    if message_type == "BLOCKED":
        item = _require_exact_keys(
            value,
            frozenset({"blocker_code", "reason", "needed_from", "work_paused"}),
            "MESSAGE_INVALID",
        )
        code = item["blocker_code"]
        if not isinstance(code, str) or _CODE_RE.fullmatch(code) is None:
            raise DialogueContractError("MESSAGE_INVALID")
        needed_from = item["needed_from"]
        if needed_from not in {"sol", "chairman", "external"}:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "blocker_code": code,
            "reason": _require_string(item["reason"], max_chars=700),
            "needed_from": needed_from,
            "work_paused": _require_bool(item["work_paused"]),
        }
    if message_type == "PROGRESS":
        item = _require_exact_keys(value, frozenset({"stage", "completed", "next"}), "MESSAGE_INVALID")
        stage = item["stage"]
        if not isinstance(stage, str) or _STAGE_RE.fullmatch(stage) is None:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "stage": stage,
            "completed": _require_string(item["completed"], max_chars=700),
            "next": _require_string(item["next"], max_chars=700),
        }
    if message_type == "RESULT":
        item = _require_exact_keys(value, frozenset({"status", "result"}), "MESSAGE_INVALID")
        status = item["status"]
        if status not in {"PASS", "PARTIAL", "BLOCKED", "FAIL"}:
            raise DialogueContractError("MESSAGE_INVALID")
        return {"status": status, "result": _require_string(item["result"], max_chars=900)}
    if message_type == "RULING":
        item = _require_exact_keys(
            value,
            frozenset({"authority_class", "selected_option", "decision", "rationale", "canonical_ref"}),
            "MESSAGE_INVALID",
        )
        authority_class = item["authority_class"]
        if authority_class not in AUTHORITY_CLASSES:
            raise DialogueContractError("MESSAGE_INVALID")
        selected_option = item["selected_option"]
        canonical_ref = item["canonical_ref"]
        if selected_option is not None and (
            not isinstance(selected_option, str) or _OPTION_ID_RE.fullmatch(selected_option) is None
        ):
            raise DialogueContractError("MESSAGE_INVALID")
        if canonical_ref is not None:
            canonical_ref = validate_evidence_ref(canonical_ref)
        if selected_option is None:
            raise DialogueContractError("MESSAGE_INVALID")
        if authority_class == "WITHIN_COMMISSION":
            if canonical_ref is not None:
                raise DialogueContractError("MESSAGE_INVALID")
        elif authority_class == "CANONICAL_REF_REQUIRED":
            if canonical_ref is None:
                raise DialogueContractError("MESSAGE_INVALID")
        elif canonical_ref is not None:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "authority_class": authority_class,
            "selected_option": selected_option,
            "decision": _require_string(item["decision"], max_chars=900),
            "rationale": _require_string(item["rationale"], max_chars=900),
            "canonical_ref": canonical_ref,
        }
    if message_type == "CONTINUE":
        item = _require_exact_keys(
            value,
            frozenset({"instruction", "stop_condition", "scope_change"}),
            "MESSAGE_INVALID",
        )
        if item["scope_change"] is not False:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "instruction": _require_string(item["instruction"], max_chars=900),
            "stop_condition": _require_string(item["stop_condition"], max_chars=700),
            "scope_change": False,
        }
    if message_type == "STOP":
        item = _require_exact_keys(value, frozenset({"reason", "next_authority"}), "MESSAGE_INVALID")
        if item["next_authority"] not in {"sol", "chairman", "canonical_ref"}:
            raise DialogueContractError("MESSAGE_INVALID")
        return {
            "reason": _require_string(item["reason"], max_chars=900),
            "next_authority": item["next_authority"],
        }
    if message_type == "AMENDMENT_AVAILABLE":
        item = _require_exact_keys(value, frozenset({"canonical_ref", "summary"}), "MESSAGE_INVALID")
        return {
            "canonical_ref": validate_evidence_ref(item["canonical_ref"]),
            "summary": _require_string(item["summary"], max_chars=700),
        }
    raise DialogueContractError("MESSAGE_INVALID")


def semantic_fingerprint(document: Mapping[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in document.items()
        if key not in {"created_at", "fingerprint"}
    }
    return hashlib.sha256(_canonical_json(semantic).encode("utf-8")).hexdigest()


def validate_message(value: Any) -> dict[str, Any]:
    item = _require_exact_keys(value, MESSAGE_KEYS, "MESSAGE_INVALID")
    if item["schema"] != MESSAGE_SCHEMA:
        raise DialogueContractError("MESSAGE_INVALID")
    message_key = item["message_key"]
    if not isinstance(message_key, str) or _MESSAGE_KEY_RE.fullmatch(message_key) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    message_type = item["message_type"]
    if message_type not in MESSAGE_TYPES:
        raise DialogueContractError("MESSAGE_INVALID")
    work_ref = item["work_ref"]
    if not isinstance(work_ref, str) or _WORK_REF_RE.fullmatch(work_ref) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    session_ref = item["session_ref"]
    if not isinstance(session_ref, str) or _SESSION_REF_RE.fullmatch(session_ref) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    seat_ref = item["seat_ref"]
    expected_seat = "fable" if message_type in FABLE_MESSAGE_TYPES else "sol"
    if seat_ref != expected_seat:
        raise DialogueContractError("MESSAGE_INVALID")
    reply_to = item["reply_to_message_key"]
    if reply_to is not None and (
        not isinstance(reply_to, str) or _MESSAGE_KEY_RE.fullmatch(reply_to) is None
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    if message_type in SOL_MESSAGE_TYPES and reply_to is None:
        raise DialogueContractError("MESSAGE_INVALID")
    requires_response = _require_bool(item["requires_response"])
    expected_response = message_type in {"DECISION_REQUEST", "BLOCKED"}
    if requires_response is not expected_response:
        raise DialogueContractError("MESSAGE_INVALID")
    fingerprint = item["fingerprint"]
    if not isinstance(fingerprint, str) or _SHA64_RE.fullmatch(fingerprint) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    normalized = {
        "schema": MESSAGE_SCHEMA,
        "message_key": message_key,
        "message_type": message_type,
        "work_ref": work_ref,
        "commission_ref": validate_commission_ref(item["commission_ref"]),
        "session_ref": session_ref,
        "seat_ref": seat_ref,
        "reply_to_message_key": reply_to,
        "applies_to": validate_applies_to(item["applies_to"]),
        "summary": _require_string(item["summary"], max_chars=MAX_SUMMARY_CHARS),
        "body": validate_body(message_type, item["body"]),
        "evidence_refs": _validate_evidence_refs(item["evidence_refs"]),
        "requires_response": requires_response,
        "created_at": _require_utc(item["created_at"]),
        "fingerprint": fingerprint,
    }
    if semantic_fingerprint(normalized) != fingerprint:
        raise DialogueContractError("FINGERPRINT_MISMATCH")
    return normalized


def build_message(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(value)
    if "fingerprint" in raw and raw["fingerprint"] not in {"", None}:
        raise DialogueContractError("MESSAGE_INVALID")
    raw["fingerprint"] = ""
    raw["fingerprint"] = semantic_fingerprint(raw)
    return validate_message(raw)


def validate_parent(value: Any) -> dict[str, Any]:
    item = _require_exact_keys(value, PARENT_KEYS, "PARENT_INVALID")
    if item["schema"] != PARENT_SCHEMA:
        raise DialogueContractError("PARENT_INVALID")
    work_ref = item["work_ref"]
    session_ref = item["session_ref"]
    if not isinstance(work_ref, str) or _WORK_REF_RE.fullmatch(work_ref) is None:
        raise DialogueContractError("PARENT_INVALID")
    if not isinstance(session_ref, str) or _SESSION_REF_RE.fullmatch(session_ref) is None:
        raise DialogueContractError("PARENT_INVALID")
    allowed = item["allowed_sol_user_ids"]
    if not isinstance(allowed, list) or not 1 <= len(allowed) <= 8:
        raise DialogueContractError("PARENT_INVALID")
    if any(
        not isinstance(user_id, str) or _SLACK_USER_ID_RE.fullmatch(user_id) is None
        for user_id in allowed
    ):
        raise DialogueContractError("PARENT_INVALID")
    if allowed != sorted(set(allowed)):
        raise DialogueContractError("PARENT_INVALID")
    fingerprint = item["fingerprint"]
    if not isinstance(fingerprint, str) or _SHA64_RE.fullmatch(fingerprint) is None:
        raise DialogueContractError("PARENT_INVALID")
    normalized = {
        "schema": PARENT_SCHEMA,
        "work_ref": work_ref,
        "commission_ref": validate_commission_ref(item["commission_ref"]),
        "session_ref": session_ref,
        "allowed_sol_user_ids": allowed,
        "created_at": _require_utc(item["created_at"]),
        "fingerprint": fingerprint,
    }
    if semantic_fingerprint(normalized) != fingerprint:
        raise DialogueContractError("FINGERPRINT_MISMATCH")
    return normalized


def build_parent(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(value)
    if "fingerprint" in raw and raw["fingerprint"] not in {"", None}:
        raise DialogueContractError("PARENT_INVALID")
    raw["fingerprint"] = ""
    raw["fingerprint"] = semantic_fingerprint(raw)
    return validate_parent(raw)


def _render_frame(discriminator: str, document: Mapping[str, Any]) -> str:
    text = f"{discriminator}\n{_canonical_json(document)}"
    if len(text.encode("utf-8")) > MAX_FRAME_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")
    return text


def render_message(message: Mapping[str, Any]) -> str:
    return _render_frame(MESSAGE_DISCRIMINATOR, validate_message(dict(message)))


def render_parent(parent: Mapping[str, Any]) -> str:
    return _render_frame(PARENT_DISCRIMINATOR, validate_parent(dict(parent)))


def _parse_frame(
    raw: str | bytes,
    *,
    discriminator: str,
    validator: Any,
    allow_chatgpt_trailer: bool,
) -> dict[str, Any]:
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
    if len(lines) not in ({2, 3} if allow_chatgpt_trailer else {2}):
        raise DialogueContractError("FRAME_INVALID")
    if lines[0] != discriminator or not lines[1]:
        raise DialogueContractError("FRAME_INVALID")
    if len(lines) == 3 and lines[2] != A0_PROVEN_CHATGPT_TRAILER:
        raise DialogueContractError("TRAILER_REFUSED")
    canonical_span = f"{lines[0]}\n{lines[1]}"
    if len(canonical_span.encode("utf-8")) > MAX_FRAME_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")
    document = _strict_loads(lines[1])
    normalized = validator(document)
    if lines[1] != _canonical_json(normalized):
        raise DialogueContractError("FRAME_INVALID")
    return normalized


def parse_message_frame(raw: str | bytes, *, allow_chatgpt_trailer: bool = True) -> dict[str, Any]:
    return _parse_frame(
        raw,
        discriminator=MESSAGE_DISCRIMINATOR,
        validator=validate_message,
        allow_chatgpt_trailer=allow_chatgpt_trailer,
    )


def parse_parent_frame(raw: str | bytes) -> dict[str, Any]:
    return _parse_frame(
        raw,
        discriminator=PARENT_DISCRIMINATOR,
        validator=validate_parent,
        allow_chatgpt_trailer=True,
    )


def same_context(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("work_ref") == right.get("work_ref")
        and left.get("commission_ref") == right.get("commission_ref")
        and left.get("session_ref") == right.get("session_ref")
        and left.get("applies_to") == right.get("applies_to")
    )


def adjudicate_reply(
    request: Mapping[str, Any],
    reply: Mapping[str, Any],
    *,
    authority_policy: TrustedAuthorityPolicy,
) -> dict[str, Any]:
    request_message = validate_message(dict(request))
    reply_message = validate_message(dict(reply))
    if request_message["seat_ref"] != "fable" or reply_message["seat_ref"] != "sol":
        raise DialogueContractError("AUTHORITY_REFUSED")
    if reply_message["reply_to_message_key"] != request_message["message_key"]:
        raise DialogueContractError("REPLY_CONTEXT_MISMATCH")
    if not same_context(request_message, reply_message):
        raise DialogueContractError("REPLY_CONTEXT_MISMATCH")

    message_type = reply_message["message_type"]
    if message_type == "RULING":
        if request_message["message_type"] != "DECISION_REQUEST":
            raise DialogueContractError("AUTHORITY_REFUSED")
        body = reply_message["body"]
        authority_class = body["authority_class"]
        options = {option["id"]: option for option in request_message["body"]["options"]}
        selected = body["selected_option"]
        if selected not in options:
            raise DialogueContractError("AUTHORITY_REFUSED")
        option = options[selected]
        model_escalation_floor = {
            "NONE": "WITHIN_COMMISSION",
            "CANONICAL_REF_REQUIRED": "CANONICAL_REF_REQUIRED",
            "CHAIRMAN_REQUIRED": "CHAIRMAN_REQUIRED",
        }[option["authority_effect"]]
        try:
            trusted_floor = authority_policy.minimum_authority(
                request=request_message,
                option=option,
            )
        except Exception:
            raise DialogueContractError("AUTHORITY_REFUSED") from None
        if trusted_floor not in AUTHORITY_CLASSES:
            raise DialogueContractError("AUTHORITY_REFUSED")
        authority_rank = {
            "WITHIN_COMMISSION": 0,
            "CANONICAL_REF_REQUIRED": 1,
            "CHAIRMAN_REQUIRED": 2,
        }
        minimum_rank = max(
            authority_rank[trusted_floor],
            authority_rank[model_escalation_floor],
        )
        if authority_rank[authority_class] < minimum_rank:
            raise DialogueContractError("AUTHORITY_REFUSED")
        if authority_class == "WITHIN_COMMISSION":
            return {
                "disposition": option["disposition"],
                "executable": True,
                "selected_option": selected,
                "canonical_ref": None,
            }
        if authority_class == "CANONICAL_REF_REQUIRED":
            return {
                "disposition": "CANONICAL_REF_REQUIRED",
                "executable": False,
                "selected_option": selected,
                "canonical_ref": body["canonical_ref"],
            }
        return {
            "disposition": "CHAIRMAN_REQUIRED",
            "executable": False,
            "selected_option": selected,
            "canonical_ref": None,
        }
    if message_type == "CONTINUE":
        if request_message["message_type"] not in {"ACK", "PROGRESS", "BLOCKED"}:
            raise DialogueContractError("AUTHORITY_REFUSED")
        if (
            request_message["message_type"] == "BLOCKED"
            and request_message["body"]["needed_from"] != "sol"
        ):
            raise DialogueContractError("AUTHORITY_REFUSED")
        return {
            "disposition": "CONTINUE",
            "executable": True,
            "selected_option": None,
            "canonical_ref": None,
        }
    if message_type == "STOP":
        return {
            "disposition": "STOP",
            "executable": True,
            "selected_option": None,
            "canonical_ref": None,
        }
    if message_type == "AMENDMENT_AVAILABLE":
        return {
            "disposition": "CANONICAL_REF_REQUIRED",
            "executable": False,
            "selected_option": None,
            "canonical_ref": reply_message["body"]["canonical_ref"],
        }
    raise DialogueContractError("AUTHORITY_REFUSED")


__all__ = [
    "A0_PROVEN_CHATGPT_TRAILER",
    "AUTHORITY_CLASSES",
    "DialogueContractError",
    "ERROR_CODES",
    "FABLE_MESSAGE_TYPES",
    "MAX_FRAME_BYTES",
    "MESSAGE_DISCRIMINATOR",
    "MESSAGE_SCHEMA",
    "MESSAGE_TYPES",
    "PARENT_DISCRIMINATOR",
    "PARENT_SCHEMA",
    "SOL_MESSAGE_TYPES",
    "TrustedAuthorityPolicy",
    "adjudicate_reply",
    "build_message",
    "build_parent",
    "parse_message_frame",
    "parse_parent_frame",
    "render_message",
    "render_parent",
    "same_context",
    "semantic_fingerprint",
    "validate_applies_to",
    "validate_commission_ref",
    "validate_evidence_ref",
    "validate_message",
    "validate_parent",
]
