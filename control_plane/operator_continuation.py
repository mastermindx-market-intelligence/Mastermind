"""Pure, deterministic operator-continuation capsule contract.

The capsule is a derived launch artifact for a fresh Executive Attempt.  It is
not a lifecycle, session, transcript, memory, retry, placement, or authority
store.  Executive OS remains the owner of Job/Attempt/Worker/Event state; the
later PREPARE integration is responsible for recording at most one immutable
capsule per target Attempt.

Provider-native conversation/session material is deliberately excluded.  A
cross-realm continuation starts a fresh provider session and carries only exact
canonical company/work evidence needed to resume the same logical
responsibility.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any


CONTINUATION_SCHEMA = "mastermind.operator_continuation.v1"
_CAPSULE_PREFIX = "ocap_"

_CAPSULE_KEYS = frozenset(
    {
        "schema",
        "capsule_id",
        "root_job_id",
        "job_id",
        "source_attempt_id",
        "target_attempt_id",
        "operation_key",
        "target_seat",
        "session_alias",
        "effective_grant_digest",
        "prior_attempt_receipt",
        "authority_sources",
        "github_work_state",
        "dialogue_state",
        "exact_next_action",
        "known_unknowns",
    }
)
_SEMANTIC_KEYS = _CAPSULE_KEYS - {"capsule_id"}
_PRIOR_RECEIPT_KEYS = frozenset(
    {"status", "terminal_event_id", "checkpoint_digest"}
)
_AUTHORITY_SOURCE_KEYS = frozenset(
    {"owner", "repository", "revision", "path", "sha256"}
)
_GITHUB_WORK_STATE_KEYS = frozenset(
    {"repository", "base_ref", "branch", "head_sha", "pull_request_number"}
)
_DIALOGUE_STATE_KEYS = frozenset(
    {"workspace_id", "channel_id", "thread_ts", "last_ruling_ts"}
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_OPERATION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,159}$")
_SESSION_ALIAS_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,95}$")
_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SLACK_WORKSPACE_RE = re.compile(r"^T[A-Z0-9]{8,15}$")
_SLACK_CHANNEL_RE = re.compile(r"^[CDG][A-Z0-9]{8,15}$")
_SLACK_TS_RE = re.compile(r"^[0-9]{10,16}\.[0-9]{6}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_RE = re.compile(
    r"(?i)(?:"
    r"Bearer\s+[A-Za-z0-9._~+/-]{16,}|"
    r"xox[a-z]-[A-Za-z0-9-]{10,}|"
    r"xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"(?:api|auth|access|refresh|oauth)[_-]?(?:token|key)\s*[:=]\s*\S+"
    r")"
)

_TARGET_SEATS = frozenset({"ceo", "cto", "coo", "worker"})
_AUTHORITY_OWNERS = frozenset(
    {"github", "agent_os", "executive_os", "slack"}
)
_TERMINAL_ATTEMPT_STATUSES = frozenset(
    {
        "COMPLETED",
        "FAILED",
        "LOST",
        "RATE_LIMITED",
        "TIMED_OUT",
        "CANCELLED",
    }
)


class ContinuationContractError(ValueError):
    """Closed refusal for malformed or unsafe continuation material."""


def _fail(code: str) -> None:
    raise ContinuationContractError(code)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContinuationContractError("NON_CANONICAL_JSON") from exc


def _reject_secret_shaped(value: object) -> None:
    if isinstance(value, str):
        if _SECRET_RE.search(value):
            _fail("SECRET_SHAPED_VALUE")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_secret_shaped(str(key))
            _reject_secret_shaped(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_secret_shaped(item)


def _text(value: object, *, code: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(code)
    token = value.strip()
    if not token or len(token.encode("utf-8")) > maximum or _CONTROL_RE.search(token):
        _fail(code)
    _reject_secret_shaped(token)
    return token


def _identifier(value: object, *, code: str) -> str:
    token = _text(value, code=code, maximum=128)
    if _ID_RE.fullmatch(token) is None:
        _fail(code)
    return token


def _digest(value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("DIGEST_INVALID")
    return value


def _git_sha(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _GIT_SHA_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _repository(value: object, *, code: str) -> str:
    token = _text(value, code=code, maximum=201)
    if _REPOSITORY_RE.fullmatch(token) is None:
        _fail(code)
    return token


def _relative_path(value: object, *, code: str) -> str:
    token = _text(value, code=code, maximum=512)
    path = PurePosixPath(token)
    if path.is_absolute() or token.startswith("./") or ".." in path.parts:
        _fail(code)
    return token


def _closed_mapping(
    value: object,
    *,
    keys: frozenset[str],
    code: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _fail(code)
    return value


def _normalize_prior_attempt_receipt(value: object) -> dict[str, object]:
    row = _closed_mapping(
        value,
        keys=_PRIOR_RECEIPT_KEYS,
        code="PRIOR_ATTEMPT_RECEIPT_INVALID",
    )
    status = _text(
        row["status"], code="PRIOR_ATTEMPT_RECEIPT_INVALID", maximum=32
    )
    if status not in _TERMINAL_ATTEMPT_STATUSES:
        _fail("PRIOR_ATTEMPT_RECEIPT_INVALID")
    terminal_event_id = _identifier(
        row["terminal_event_id"], code="PRIOR_ATTEMPT_RECEIPT_INVALID"
    )
    checkpoint_digest = _digest(row["checkpoint_digest"])
    return {
        "status": status,
        "terminal_event_id": terminal_event_id,
        "checkpoint_digest": checkpoint_digest,
    }


def _normalize_authority_sources(value: object) -> list[dict[str, str]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not 1 <= len(value) <= 32
    ):
        _fail("AUTHORITY_SOURCES_INVALID")

    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in value:
        row = _closed_mapping(
            raw,
            keys=_AUTHORITY_SOURCE_KEYS,
            code="AUTHORITY_SOURCES_INVALID",
        )
        owner = _text(row["owner"], code="AUTHORITY_SOURCES_INVALID", maximum=32)
        if owner not in _AUTHORITY_OWNERS:
            _fail("AUTHORITY_SOURCES_INVALID")
        repository = _repository(
            row["repository"], code="AUTHORITY_SOURCES_INVALID"
        )
        revision = _git_sha(row["revision"], code="AUTHORITY_SOURCES_INVALID")
        path = _relative_path(row["path"], code="AUTHORITY_SOURCES_INVALID")
        sha256 = _digest(row["sha256"])
        identity = (owner, repository, path, revision)
        if identity in seen:
            _fail("AUTHORITY_SOURCES_INVALID")
        seen.add(identity)
        normalized.append(
            {
                "owner": owner,
                "repository": repository,
                "revision": revision,
                "path": path,
                "sha256": sha256,
            }
        )
    normalized.sort(
        key=lambda row: (
            row["owner"],
            row["repository"],
            row["path"],
            row["revision"],
        )
    )
    return normalized


def _normalize_github_work_state(value: object) -> dict[str, object]:
    row = _closed_mapping(
        value,
        keys=_GITHUB_WORK_STATE_KEYS,
        code="GITHUB_WORK_STATE_INVALID",
    )
    repository = _repository(
        row["repository"], code="GITHUB_WORK_STATE_INVALID"
    )
    base_ref = _text(row["base_ref"], code="GITHUB_WORK_STATE_INVALID", maximum=128)
    branch = _text(row["branch"], code="GITHUB_WORK_STATE_INVALID", maximum=256)
    if (
        base_ref.startswith("-")
        or branch.startswith("-")
        or ".." in base_ref
        or ".." in branch
        or _CONTROL_RE.search(base_ref)
        or _CONTROL_RE.search(branch)
    ):
        _fail("GITHUB_WORK_STATE_INVALID")
    head_sha = _git_sha(row["head_sha"], code="GITHUB_WORK_STATE_INVALID")
    pull_request_number = row["pull_request_number"]
    if (
        isinstance(pull_request_number, bool)
        or not isinstance(pull_request_number, int)
        or not 0 <= pull_request_number <= 2_147_483_647
    ):
        _fail("GITHUB_WORK_STATE_INVALID")
    return {
        "repository": repository,
        "base_ref": base_ref,
        "branch": branch,
        "head_sha": head_sha,
        "pull_request_number": pull_request_number,
    }


def _normalize_dialogue_state(value: object) -> dict[str, str]:
    row = _closed_mapping(
        value,
        keys=_DIALOGUE_STATE_KEYS,
        code="DIALOGUE_STATE_INVALID",
    )
    workspace_id = _text(
        row["workspace_id"], code="DIALOGUE_STATE_INVALID", maximum=16
    )
    channel_id = _text(
        row["channel_id"], code="DIALOGUE_STATE_INVALID", maximum=16
    )
    thread_ts = _text(row["thread_ts"], code="DIALOGUE_STATE_INVALID", maximum=32)
    last_ruling_ts = _text(
        row["last_ruling_ts"], code="DIALOGUE_STATE_INVALID", maximum=32
    )
    if (
        _SLACK_WORKSPACE_RE.fullmatch(workspace_id) is None
        or _SLACK_CHANNEL_RE.fullmatch(channel_id) is None
        or _SLACK_TS_RE.fullmatch(thread_ts) is None
        or _SLACK_TS_RE.fullmatch(last_ruling_ts) is None
    ):
        _fail("DIALOGUE_STATE_INVALID")
    return {
        "workspace_id": workspace_id,
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "last_ruling_ts": last_ruling_ts,
    }


def _normalize_known_unknowns(value: object) -> list[str]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) > 32
    ):
        _fail("KNOWN_UNKNOWNS_INVALID")
    normalized: list[str] = []
    for raw in value:
        item = _text(raw, code="KNOWN_UNKNOWNS_INVALID", maximum=512)
        if item in normalized:
            _fail("KNOWN_UNKNOWNS_INVALID")
        normalized.append(item)
    return normalized


def _normalize_semantic_material(value: Mapping[str, object]) -> dict[str, object]:
    if set(value) != _SEMANTIC_KEYS:
        _fail("CAPSULE_KEYS_INVALID")
    if value.get("schema") != CONTINUATION_SCHEMA:
        _fail("SCHEMA_INVALID")

    root_job_id = _identifier(value["root_job_id"], code="JOB_IDENTITY_INVALID")
    job_id = _identifier(value["job_id"], code="JOB_IDENTITY_INVALID")
    source_attempt_id = _identifier(
        value["source_attempt_id"], code="ATTEMPT_IDENTITY_INVALID"
    )
    target_attempt_id = _identifier(
        value["target_attempt_id"], code="ATTEMPT_IDENTITY_INVALID"
    )
    if source_attempt_id == target_attempt_id:
        _fail("ATTEMPT_IDENTITY_INVALID")

    operation_key = _text(
        value["operation_key"], code="OPERATION_KEY_INVALID", maximum=160
    )
    if _OPERATION_KEY_RE.fullmatch(operation_key) is None:
        _fail("OPERATION_KEY_INVALID")

    target_seat = _text(value["target_seat"], code="TARGET_SEAT_INVALID", maximum=16)
    if target_seat not in _TARGET_SEATS:
        _fail("TARGET_SEAT_INVALID")

    session_alias = _text(
        value["session_alias"], code="SESSION_ALIAS_INVALID", maximum=96
    )
    if _SESSION_ALIAS_RE.fullmatch(session_alias) is None:
        _fail("SESSION_ALIAS_INVALID")

    effective_grant_digest = _digest(value["effective_grant_digest"])
    prior_attempt_receipt = _normalize_prior_attempt_receipt(
        value["prior_attempt_receipt"]
    )
    authority_sources = _normalize_authority_sources(value["authority_sources"])
    github_work_state = _normalize_github_work_state(value["github_work_state"])
    dialogue_state = _normalize_dialogue_state(value["dialogue_state"])
    exact_next_action = _text(
        value["exact_next_action"], code="EXACT_NEXT_ACTION_INVALID", maximum=2048
    )
    known_unknowns = _normalize_known_unknowns(value["known_unknowns"])

    normalized = {
        "schema": CONTINUATION_SCHEMA,
        "root_job_id": root_job_id,
        "job_id": job_id,
        "source_attempt_id": source_attempt_id,
        "target_attempt_id": target_attempt_id,
        "operation_key": operation_key,
        "target_seat": target_seat,
        "session_alias": session_alias,
        "effective_grant_digest": effective_grant_digest,
        "prior_attempt_receipt": prior_attempt_receipt,
        "authority_sources": authority_sources,
        "github_work_state": github_work_state,
        "dialogue_state": dialogue_state,
        "exact_next_action": exact_next_action,
        "known_unknowns": known_unknowns,
    }
    _reject_secret_shaped(normalized)
    _canonical_bytes(normalized)
    return normalized


def _capsule_id(semantic: Mapping[str, object]) -> str:
    return _CAPSULE_PREFIX + hashlib.sha256(_canonical_bytes(semantic)).hexdigest()


def build_operator_continuation(
    *,
    root_job_id: str,
    job_id: str,
    source_attempt_id: str,
    target_attempt_id: str,
    operation_key: str,
    target_seat: str,
    session_alias: str,
    effective_grant_digest: str,
    prior_attempt_receipt: Mapping[str, object],
    authority_sources: Sequence[Mapping[str, object]],
    github_work_state: Mapping[str, object],
    dialogue_state: Mapping[str, object],
    exact_next_action: str,
    known_unknowns: Sequence[str],
) -> dict[str, object]:
    """Build one immutable semantic capsule with deterministic identity.

    Caller-authored timestamps, random IDs, provider-session handles, transcripts,
    credentials, and placement decisions are intentionally absent.  Later
    Executive PREPARE logic owns action-time event identity and one-capsule-per-
    target-Attempt idempotency.
    """

    semantic = _normalize_semantic_material(
        {
            "schema": CONTINUATION_SCHEMA,
            "root_job_id": root_job_id,
            "job_id": job_id,
            "source_attempt_id": source_attempt_id,
            "target_attempt_id": target_attempt_id,
            "operation_key": operation_key,
            "target_seat": target_seat,
            "session_alias": session_alias,
            "effective_grant_digest": effective_grant_digest,
            "prior_attempt_receipt": prior_attempt_receipt,
            "authority_sources": authority_sources,
            "github_work_state": github_work_state,
            "dialogue_state": dialogue_state,
            "exact_next_action": exact_next_action,
            "known_unknowns": known_unknowns,
        }
    )
    return {
        "schema": semantic["schema"],
        "capsule_id": _capsule_id(semantic),
        **{key: value for key, value in semantic.items() if key != "schema"},
    }


def canonical_continuation_bytes(value: Mapping[str, object]) -> bytes:
    """Validate a complete capsule and return its canonical wire bytes."""

    if not isinstance(value, Mapping) or set(value) != _CAPSULE_KEYS:
        _fail("CAPSULE_KEYS_INVALID")
    capsule_id = value.get("capsule_id")
    if (
        not isinstance(capsule_id, str)
        or not capsule_id.startswith(_CAPSULE_PREFIX)
        or _SHA256_RE.fullmatch(capsule_id[len(_CAPSULE_PREFIX) :]) is None
    ):
        _fail("CAPSULE_ID_INVALID")
    semantic = _normalize_semantic_material(
        {key: value[key] for key in _SEMANTIC_KEYS}
    )
    if capsule_id != _capsule_id(semantic):
        _fail("CAPSULE_ID_MISMATCH")
    normalized = {
        "schema": semantic["schema"],
        "capsule_id": capsule_id,
        **{key: item for key, item in semantic.items() if key != "schema"},
    }
    return _canonical_bytes(normalized)
