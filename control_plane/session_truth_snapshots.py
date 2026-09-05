"""Strict, secret-safe normalization for Session Truth external observations.

The normalizers in this module are pure.  They accept caller-supplied snapshot
documents, validate a closed V1 shape, preserve explicit null/unavailable state,
and return deterministically ordered metadata-only observations.  They perform
no network access and no source-system mutation.
"""
from __future__ import annotations

import copy
from datetime import datetime
import json
from pathlib import Path
import re
from collections.abc import Mapping
from typing import Any

from control_plane.session_truth_contract import (
    MAX_JSON_BYTES,
    SessionTruthContractError,
    validate_json_tree,
)


GITHUB_SCHEMA = "mastermind.github_observation.v1"
LINEAR_SCHEMA = "mastermind.linear_observation.v1"
SLACK_SCHEMA = "mastermind.slack_observation.v1"
EXECUTIVE_SCHEMA = "mastermind.executive_observation.v1"
IDENTITY_SCHEMA = "mastermind.identity_observation.v1"

_SECRET_KEYS = frozenset(
    {"token", "access_token", "authorization", "cookie", "secret", "password"}
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
_WS_RE = re.compile(r"^WS:[A-Z0-9][A-Z0-9-]*$")
_MAS_RE = re.compile(r"^MAS-[0-9]+$")
_SLACK_TS_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_OPAQUE_METADATA_MAX_CHARS = 1024

_GITHUB_STATES = frozenset({"open", "closed", "merged"})
_GITHUB_CI = frozenset(
    {
        "success",
        "failure",
        "pending",
        "in_progress",
        "queued",
        "cancelled",
        "skipped",
        "neutral",
        "timed_out",
        "action_required",
        "stale",
        "unavailable",
    }
)
_LINEAR_STATUSES = frozenset(
    {
        "Backlog",
        "Todo",
        "In Progress",
        "In Review",
        "Done",
        "Canceled",
        "Cancelled",
    }
)
_LINEAR_RELATIONS = frozenset(
    {
        "merge_is_done",
        "contributing",
        "architecture_evidence",
        "program_gate",
        "ignored_wrong_id",
    }
)
_SLACK_TRANSPORTS = frozenset(
    {
        "DELIVERY_ONLY",
        "READ_ONLY",
        "VISIBILITY_ONLY",
        "DIALOGUE_ONLY",
        "SOL_STATE",
    }
)
_SLACK_MESSAGE_CLASSES = frozenset(
    {
        "READ_ONLY_COMMISSION",
        "COMMISSION",
        "PICKUP",
        "ACK",
        "RESULT",
        "BUILD_EVENT",
        "SOL_STATE",
        "DIALOGUE",
        "HOLD",
        "VISIBILITY",
        "UNCLASSIFIED",
    }
)
_EXECUTIVE_STATUSES = frozenset(
    {
        "QUEUED",
        "ADMITTED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
        "CANCELLED",
        "REJECTED",
        "BLOCKED",
        "UNKNOWN",
    }
)
_IDENTITY_ROLES = frozenset(
    {
        "chairman",
        "sol_ceo",
        "coo",
        "operator",
        "worker",
        "service_actor",
        "relay",
        "projector",
        "observer",
    }
)

_GITHUB_ROOT_KEYS = frozenset({"schema", "available", "observed_at", "pull_requests"})
_GITHUB_PR_KEYS = frozenset(
    {
        "repository",
        "number",
        "state",
        "draft",
        "head_sha",
        "base_sha",
        "merge_sha",
        "ci",
        "workstream",
        "linear",
        "portfolio_mode",
        "wave",
        "authority",
        "completion",
        "proof_state",
        "operation_key",
        "pickup_head_sha",
    }
)
_LINEAR_ROOT_KEYS = frozenset({"schema", "available", "observed_at", "issues"})
_LINEAR_ISSUE_KEYS = frozenset(
    {
        "id",
        "status",
        "parent_id",
        "workstream",
        "completion",
        "projection_revision",
        "github_relations",
        "updated_at",
    }
)
_LINEAR_RELATION_KEYS = frozenset({"repository", "number", "relation"})
_SLACK_ROOT_KEYS = frozenset(
    {"schema", "available", "observed_at", "channels", "messages"}
)
_SLACK_CHANNEL_KEYS = frozenset({"channel_id", "member_ids"})
_SLACK_MESSAGE_KEYS = frozenset(
    {
        "channel_id",
        "ts",
        "thread_ts",
        "sender_id",
        "operation_key",
        "payload_hash",
        "transport",
        "message_class",
        "target_principal_id",
        "delivered",
        "acked",
        "receiver_eligible",
        "ack_required",
        "created_at",
        "source_law_sha",
        "freeze_at",
    }
)
_EXECUTIVE_ROOT_KEYS = frozenset(
    {
        "schema",
        "available",
        "observed_at",
        "fresh",
        "do_not_submit",
        "grounding_sha",
        "operations",
    }
)
_EXECUTIVE_OPERATION_KEYS = frozenset(
    {"operation_key", "payload_hash", "status", "effect_unknown", "carrier"}
)
_IDENTITY_ROOT_KEYS = frozenset({"schema", "available", "observed_at", "bindings"})
_IDENTITY_BINDING_KEYS = frozenset(
    {
        "seat",
        "slack_principal",
        "github_account",
        "linear_actor",
        "executive_worker",
        "provider_realm",
        "role",
        "service_actor",
    }
)
_UNAVAILABLE_KEYS = frozenset({"schema", "available", "reason"})


def _error(message: str) -> SessionTruthContractError:
    return SessionTruthContractError(message)


def _reject_non_finite_constant(name: str) -> Any:
    """Refuse NaN/Infinity/-Infinity at parse time (owner-record amendment §5)."""

    raise _error(f"snapshot contains forbidden non-finite number {name}")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise _error(f"{label} keys must be strings")
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    keys = set(value)
    unknown = sorted(keys - expected)
    missing = sorted(expected - keys)
    if unknown:
        raise _error(f"unknown key(s) in {label}: {', '.join(unknown)}")
    if missing:
        raise _error(f"missing key(s) in {label}: {', '.join(missing)}")


def _reject_secret_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _error(f"{path} contains a non-string key")
            if key.casefold() in _SECRET_KEYS:
                raise _error(f"secret-bearing key {key!r} is forbidden at {path}")
            _reject_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_keys(item, f"{path}[{index}]")


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise _error(f"{label} must be a boolean")
    return value


def _int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise _error(f"{label} must be an integer >= {minimum}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{label} must be a non-empty string")
    return value


def _nullable_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _nullable_opaque_metadata(value: Any, label: str) -> str | None:
    """Preserve source-owned metadata without owning its value grammar."""

    text = _nullable_string(value, label)
    if text is not None and len(text) > _OPAQUE_METADATA_MAX_CHARS:
        raise _error(f"{label} must be at most 1024 characters")
    return text


def _enum(value: Any, allowed: frozenset[str], label: str) -> str:
    text = _string(value, label)
    if text not in allowed:
        raise _error(f"{label} has unknown enum value {text!r}")
    return text


def _nullable_enum(value: Any, allowed: frozenset[str], label: str) -> str | None:
    if value is None:
        return None
    return _enum(value, allowed, label)


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise _error(f"{label} must be a lowercase 40-hex Git SHA")
    return value


def _nullable_sha(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _sha(value, label)


def _semantic_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise _error(f"{label} must be a sha256:<64 lowercase hex> digest")
    return value


def _nullable_hash(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _semantic_hash(value, label)


def _repository(value: Any, label: str) -> str:
    text = _string(value, label)
    if not _REPO_RE.fullmatch(text):
        raise _error(f"{label} must use owner/name form")
    return text


def _ws(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _WS_RE.fullmatch(value):
        raise _error(f"{label} must be null or use WS:<KEY> form")
    return value


def _mas(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _MAS_RE.fullmatch(value):
        raise _error(f"{label} must be null or use MAS-<digits> form")
    return value


def _timestamp(value: Any, label: str) -> str:
    text = _string(value, label)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise _error(f"{label} must be an offset-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(f"{label} must be an offset-aware ISO-8601 timestamp")
    return text


def _nullable_timestamp(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _timestamp(value, label)


def _slack_ts(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SLACK_TS_RE.fullmatch(value):
        raise _error(f"{label} must be a Slack timestamp string")
    return value


def _nullable_slack_ts(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _slack_ts(value, label)


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(f"{label} must be a list")
    return value


def _unavailable(doc: Mapping[str, Any], schema: str, label: str) -> dict[str, Any] | None:
    available = doc.get("available")
    if type(available) is not bool:
        raise _error(f"{label}.available must be a boolean")
    if available:
        return None
    _exact_keys(doc, _UNAVAILABLE_KEYS, label)
    if doc.get("schema") != schema:
        raise _error(f"{label}.schema must be exactly {schema!r}")
    return {
        "available": False,
        "reason": _string(doc.get("reason"), f"{label}.reason"),
    }


def _prepare(doc: Any, schema: str, label: str) -> Mapping[str, Any]:
    root = _mapping(doc, label)
    validate_json_tree(root, label)
    _reject_secret_keys(root)
    if root.get("schema") != schema:
        raise _error(f"{label}.schema must be exactly {schema!r}")
    return root


def load_snapshot(path: Path | str, expected_schema: str) -> dict[str, Any]:
    """Load one JSON observation file and reject schema/secret drift.

    This loader deliberately performs only file/JSON/schema/secret validation.
    Plane-specific closed-shape validation belongs to the corresponding
    ``normalize_*`` function so normalized fixtures and in-memory adapters share
    exactly the same rules.
    """

    if not isinstance(expected_schema, str) or not expected_schema:
        raise _error("expected_schema must be a non-empty string")
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
    except OSError as exc:
        raise _error(f"snapshot could not be read: {exc}") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise _error(f"snapshot exceeds the maximum size of {MAX_JSON_BYTES} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _error("snapshot is not valid UTF-8") from exc
    try:
        parsed = json.loads(text, parse_constant=_reject_non_finite_constant)
    except (RecursionError, ValueError) as exc:
        raise _error("snapshot is not valid JSON") from exc
    root = _mapping(parsed, "snapshot")
    validate_json_tree(root, "snapshot")
    _reject_secret_keys(root)
    if root.get("schema") != expected_schema:
        raise _error(f"snapshot schema must be exactly {expected_schema!r}")
    return copy.deepcopy(dict(root))


def normalize_github(doc: Mapping[str, Any]) -> dict[str, Any]:
    root = _prepare(doc, GITHUB_SCHEMA, "github")
    unavailable = _unavailable(root, GITHUB_SCHEMA, "github")
    if unavailable is not None:
        return unavailable
    _exact_keys(root, _GITHUB_ROOT_KEYS, "github")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(_list(root["pull_requests"], "github.pull_requests")):
        row = _mapping(raw, f"github.pull_requests[{index}]")
        _exact_keys(row, _GITHUB_PR_KEYS, f"github.pull_requests[{index}]")
        repository = _repository(row["repository"], f"github.pull_requests[{index}].repository")
        number = _int(row["number"], f"github.pull_requests[{index}].number", minimum=1)
        key = (repository, number)
        if key in seen:
            raise _error(f"github.pull_requests duplicates {repository}#{number}")
        seen.add(key)
        rows.append(
            {
                "repository": repository,
                "number": number,
                "state": _enum(
                    row["state"], _GITHUB_STATES, f"github.pull_requests[{index}].state"
                ),
                "draft": _bool(row["draft"], f"github.pull_requests[{index}].draft"),
                "head_sha": _sha(row["head_sha"], f"github.pull_requests[{index}].head_sha"),
                "base_sha": _sha(row["base_sha"], f"github.pull_requests[{index}].base_sha"),
                "merge_sha": _nullable_sha(
                    row["merge_sha"], f"github.pull_requests[{index}].merge_sha"
                ),
                "ci": _enum(row["ci"], _GITHUB_CI, f"github.pull_requests[{index}].ci"),
                "workstream": _ws(
                    row["workstream"], f"github.pull_requests[{index}].workstream"
                ),
                "linear": _mas(row["linear"], f"github.pull_requests[{index}].linear"),
                # These values belong to the source repository's PR-linkage
                # contract.  Session Truth preserves them as structural opaque
                # metadata and never becomes a second authoring grammar.
                "portfolio_mode": _nullable_opaque_metadata(
                    row["portfolio_mode"],
                    f"github.pull_requests[{index}].portfolio_mode",
                ),
                "wave": _nullable_string(
                    row["wave"], f"github.pull_requests[{index}].wave"
                ),
                "authority": _nullable_opaque_metadata(
                    row["authority"],
                    f"github.pull_requests[{index}].authority",
                ),
                "completion": _nullable_opaque_metadata(
                    row["completion"],
                    f"github.pull_requests[{index}].completion",
                ),
                "proof_state": _nullable_opaque_metadata(
                    row["proof_state"],
                    f"github.pull_requests[{index}].proof_state",
                ),
                "operation_key": _nullable_string(
                    row["operation_key"], f"github.pull_requests[{index}].operation_key"
                ),
                "pickup_head_sha": _nullable_sha(
                    row["pickup_head_sha"],
                    f"github.pull_requests[{index}].pickup_head_sha",
                ),
            }
        )
    rows.sort(key=lambda item: (item["repository"], item["number"]))
    return {
        "available": True,
        "observed_at": _timestamp(root["observed_at"], "github.observed_at"),
        "pull_requests": rows,
    }


def normalize_linear(doc: Mapping[str, Any]) -> dict[str, Any]:
    root = _prepare(doc, LINEAR_SCHEMA, "linear")
    unavailable = _unavailable(root, LINEAR_SCHEMA, "linear")
    if unavailable is not None:
        return unavailable
    _exact_keys(root, _LINEAR_ROOT_KEYS, "linear")

    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_list(root["issues"], "linear.issues")):
        issue = _mapping(raw, f"linear.issues[{index}]")
        _exact_keys(issue, _LINEAR_ISSUE_KEYS, f"linear.issues[{index}]")
        issue_id = _mas(issue["id"], f"linear.issues[{index}].id")
        if issue_id is None:
            raise _error(f"linear.issues[{index}].id may not be null")
        if issue_id in seen:
            raise _error(f"linear.issues duplicates {issue_id}")
        seen.add(issue_id)

        relations: list[dict[str, Any]] = []
        relation_seen: set[tuple[str, int, str]] = set()
        for rel_index, raw_relation in enumerate(
            _list(issue["github_relations"], f"linear.issues[{index}].github_relations")
        ):
            relation = _mapping(
                raw_relation,
                f"linear.issues[{index}].github_relations[{rel_index}]",
            )
            _exact_keys(
                relation,
                _LINEAR_RELATION_KEYS,
                f"linear.issues[{index}].github_relations[{rel_index}]",
            )
            repository = _repository(
                relation["repository"],
                f"linear.issues[{index}].github_relations[{rel_index}].repository",
            )
            number = _int(
                relation["number"],
                f"linear.issues[{index}].github_relations[{rel_index}].number",
                minimum=1,
            )
            relation_class = _enum(
                relation["relation"],
                _LINEAR_RELATIONS,
                f"linear.issues[{index}].github_relations[{rel_index}].relation",
            )
            relation_key = (repository, number, relation_class)
            if relation_key in relation_seen:
                raise _error(
                    f"linear.issues[{index}].github_relations contains a duplicate relation"
                )
            relation_seen.add(relation_key)
            relations.append(
                {
                    "repository": repository,
                    "number": number,
                    "relation": relation_class,
                }
            )
        relations.sort(key=lambda item: (item["repository"], item["number"], item["relation"]))

        revision = issue["projection_revision"]
        if revision is not None:
            revision = _int(
                revision, f"linear.issues[{index}].projection_revision", minimum=0
            )
        issues.append(
            {
                "id": issue_id,
                "status": _enum(
                    issue["status"], _LINEAR_STATUSES, f"linear.issues[{index}].status"
                ),
                "parent_id": _mas(issue["parent_id"], f"linear.issues[{index}].parent_id"),
                "workstream": _ws(
                    issue["workstream"], f"linear.issues[{index}].workstream"
                ),
                "completion": _nullable_opaque_metadata(
                    issue["completion"],
                    f"linear.issues[{index}].completion",
                ),
                "projection_revision": revision,
                "github_relations": relations,
                "updated_at": _timestamp(
                    issue["updated_at"], f"linear.issues[{index}].updated_at"
                ),
            }
        )
    issues.sort(key=lambda item: int(item["id"].split("-", 1)[1]))
    return {
        "available": True,
        "observed_at": _timestamp(root["observed_at"], "linear.observed_at"),
        "issues": issues,
    }


def normalize_slack(doc: Mapping[str, Any]) -> dict[str, Any]:
    root = _prepare(doc, SLACK_SCHEMA, "slack")
    unavailable = _unavailable(root, SLACK_SCHEMA, "slack")
    if unavailable is not None:
        return unavailable
    _exact_keys(root, _SLACK_ROOT_KEYS, "slack")

    channels: list[dict[str, Any]] = []
    channel_seen: set[str] = set()
    for index, raw in enumerate(_list(root["channels"], "slack.channels")):
        channel = _mapping(raw, f"slack.channels[{index}]")
        _exact_keys(channel, _SLACK_CHANNEL_KEYS, f"slack.channels[{index}]")
        channel_id = _string(channel["channel_id"], f"slack.channels[{index}].channel_id")
        if channel_id in channel_seen:
            raise _error(f"slack.channels duplicates {channel_id}")
        channel_seen.add(channel_id)
        members_raw = _list(channel["member_ids"], f"slack.channels[{index}].member_ids")
        members = [
            _string(member, f"slack.channels[{index}].member_ids[{member_index}]")
            for member_index, member in enumerate(members_raw)
        ]
        if len(set(members)) != len(members):
            raise _error(f"slack.channels[{index}].member_ids contains duplicates")
        channels.append({"channel_id": channel_id, "member_ids": sorted(members)})
    channels.sort(key=lambda item: item["channel_id"])

    messages: list[dict[str, Any]] = []
    message_seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(_list(root["messages"], "slack.messages")):
        message = _mapping(raw, f"slack.messages[{index}]")
        _exact_keys(message, _SLACK_MESSAGE_KEYS, f"slack.messages[{index}]")
        channel_id = _string(
            message["channel_id"], f"slack.messages[{index}].channel_id"
        )
        ts = _slack_ts(message["ts"], f"slack.messages[{index}].ts")
        key = (channel_id, ts)
        if key in message_seen:
            raise _error(f"slack.messages duplicates {channel_id}@{ts}")
        message_seen.add(key)

        receiver = message["receiver_eligible"]
        if receiver is not None:
            receiver = _bool(receiver, f"slack.messages[{index}].receiver_eligible")
        messages.append(
            {
                "channel_id": channel_id,
                "ts": ts,
                "thread_ts": _nullable_slack_ts(
                    message["thread_ts"], f"slack.messages[{index}].thread_ts"
                ),
                "sender_id": _string(
                    message["sender_id"], f"slack.messages[{index}].sender_id"
                ),
                "operation_key": _nullable_string(
                    message["operation_key"],
                    f"slack.messages[{index}].operation_key",
                ),
                "payload_hash": _nullable_hash(
                    message["payload_hash"], f"slack.messages[{index}].payload_hash"
                ),
                "transport": _enum(
                    message["transport"],
                    _SLACK_TRANSPORTS,
                    f"slack.messages[{index}].transport",
                ),
                "message_class": _enum(
                    message["message_class"],
                    _SLACK_MESSAGE_CLASSES,
                    f"slack.messages[{index}].message_class",
                ),
                "target_principal_id": _nullable_string(
                    message["target_principal_id"],
                    f"slack.messages[{index}].target_principal_id",
                ),
                "delivered": _bool(
                    message["delivered"], f"slack.messages[{index}].delivered"
                ),
                "acked": _bool(message["acked"], f"slack.messages[{index}].acked"),
                "receiver_eligible": receiver,
                "ack_required": _bool(
                    message["ack_required"], f"slack.messages[{index}].ack_required"
                ),
                "created_at": _timestamp(
                    message["created_at"], f"slack.messages[{index}].created_at"
                ),
                "source_law_sha": _nullable_sha(
                    message["source_law_sha"],
                    f"slack.messages[{index}].source_law_sha",
                ),
                "freeze_at": _nullable_timestamp(
                    message["freeze_at"], f"slack.messages[{index}].freeze_at"
                ),
            }
        )
    messages.sort(key=lambda item: (item["channel_id"], item["ts"]))
    return {
        "available": True,
        "observed_at": _timestamp(root["observed_at"], "slack.observed_at"),
        "channels": channels,
        "messages": messages,
    }


def normalize_executive(doc: Mapping[str, Any]) -> dict[str, Any]:
    root = _prepare(doc, EXECUTIVE_SCHEMA, "executive")
    unavailable = _unavailable(root, EXECUTIVE_SCHEMA, "executive")
    if unavailable is not None:
        return unavailable
    _exact_keys(root, _EXECUTIVE_ROOT_KEYS, "executive")

    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_list(root["operations"], "executive.operations")):
        operation = _mapping(raw, f"executive.operations[{index}]")
        _exact_keys(
            operation,
            _EXECUTIVE_OPERATION_KEYS,
            f"executive.operations[{index}]",
        )
        operation_key = _string(
            operation["operation_key"], f"executive.operations[{index}].operation_key"
        )
        if operation_key in seen:
            raise _error(f"executive.operations duplicates {operation_key}")
        seen.add(operation_key)
        operations.append(
            {
                "operation_key": operation_key,
                "payload_hash": _semantic_hash(
                    operation["payload_hash"],
                    f"executive.operations[{index}].payload_hash",
                ),
                "status": _enum(
                    operation["status"],
                    _EXECUTIVE_STATUSES,
                    f"executive.operations[{index}].status",
                ),
                "effect_unknown": _bool(
                    operation["effect_unknown"],
                    f"executive.operations[{index}].effect_unknown",
                ),
                "carrier": _nullable_string(
                    operation["carrier"], f"executive.operations[{index}].carrier"
                ),
            }
        )
    operations.sort(key=lambda item: item["operation_key"])
    return {
        "available": True,
        "observed_at": _timestamp(root["observed_at"], "executive.observed_at"),
        "fresh": _bool(root["fresh"], "executive.fresh"),
        "do_not_submit": _bool(root["do_not_submit"], "executive.do_not_submit"),
        "grounding_sha": _sha(root["grounding_sha"], "executive.grounding_sha"),
        "operations": operations,
    }


def normalize_identities(doc: Mapping[str, Any]) -> dict[str, Any]:
    root = _prepare(doc, IDENTITY_SCHEMA, "identities")
    unavailable = _unavailable(root, IDENTITY_SCHEMA, "identities")
    if unavailable is not None:
        return unavailable
    _exact_keys(root, _IDENTITY_ROOT_KEYS, "identities")

    bindings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_list(root["bindings"], "identities.bindings")):
        binding = _mapping(raw, f"identities.bindings[{index}]")
        _exact_keys(binding, _IDENTITY_BINDING_KEYS, f"identities.bindings[{index}]")
        seat = _string(binding["seat"], f"identities.bindings[{index}].seat")
        if seat in seen:
            raise _error(f"identities.bindings duplicates seat {seat!r}")
        seen.add(seat)
        bindings.append(
            {
                "seat": seat,
                "slack_principal": _nullable_string(
                    binding["slack_principal"],
                    f"identities.bindings[{index}].slack_principal",
                ),
                "github_account": _nullable_string(
                    binding["github_account"],
                    f"identities.bindings[{index}].github_account",
                ),
                "linear_actor": _nullable_string(
                    binding["linear_actor"],
                    f"identities.bindings[{index}].linear_actor",
                ),
                "executive_worker": _nullable_string(
                    binding["executive_worker"],
                    f"identities.bindings[{index}].executive_worker",
                ),
                "provider_realm": _nullable_string(
                    binding["provider_realm"],
                    f"identities.bindings[{index}].provider_realm",
                ),
                "role": _nullable_enum(
                    binding["role"],
                    _IDENTITY_ROLES,
                    f"identities.bindings[{index}].role",
                ),
                "service_actor": _nullable_string(
                    binding["service_actor"],
                    f"identities.bindings[{index}].service_actor",
                ),
            }
        )
    bindings.sort(key=lambda item: item["seat"])
    return {
        "available": True,
        "observed_at": _timestamp(root["observed_at"], "identities.observed_at"),
        "bindings": bindings,
    }
