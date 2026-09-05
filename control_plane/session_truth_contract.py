"""Deterministic contracts for the read-only Session Truth Receipt.

This module deliberately owns no acquisition, lifecycle, projection, transport, or
persistence.  It validates the bounded observation envelope and provides canonical
serialization/hashing used by the pure reconciliation layer.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any


INPUT_SCHEMA = "mastermind.session_truth_inputs.v1"
RECEIPT_SCHEMA = "mastermind.session_truth_receipt.v1"
ADMISSION_MODES = {
    "GROUNDING_COMPLETE",
    "GROUNDING_PARTIAL",
    "DIALOGUE_ONLY",
    "MODIFICATION_REFUSED",
}
FINDING_SEVERITIES = {"FATAL", "BLOCKING", "WARNING", "INFO"}

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema",
        "scope",
        "skillpack",
        "agentos",
        "github",
        "linear",
        "slack",
        "executive",
        "identities",
    }
)
_SCOPE_KEYS = frozenset(
    {"workstreams", "linear", "repositories", "operation_key", "requires_executive"}
)
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_WS_RE = re.compile(r"^WS:[A-Z0-9][A-Z0-9-]*$")
_MAS_RE = re.compile(r"^MAS-[0-9]+$")
_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
RECORDS_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# These are input-safety ceilings, not business-data truncation limits.  The
# largest accepted R1 proof observed before this contract was about 1.1 MiB,
# 17,718 JSON values and depth 10.  The limits retain ample headroom while
# making parser/copy/hash work finite and deterministic.
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_JSON_NODES = 250_000


class SessionTruthContractError(ValueError):
    """Raised when an observation envelope violates the frozen R1 contract."""


def valid_source_records_digest(value: object) -> bool:
    """True only for an exact owner-produced ``sha256:<64 lowercase hex>`` digest."""

    return isinstance(value, str) and bool(RECORDS_DIGEST_RE.fullmatch(value))


def validate_json_tree(value: object, label: str = "value") -> None:
    """Iteratively bound a value to finite, acyclic strict-JSON content.

    Invalid mapping keys or non-JSON values fail through the typed R1 error path
    instead of being coerced by the serializer (amendment §5: no coercion to
    null/string/zero).  Containers at exactly ``MAX_JSON_DEPTH`` and trees at
    exactly ``MAX_JSON_NODES`` are accepted; the next value is refused.
    """

    # Each frame retains only an iterator over one active container.  Siblings
    # are never all enqueued, so traversal memory is bounded by depth rather than
    # by the product of depth and a wide, aliased input graph.
    stack: list[tuple[object, object, str, int, bool]] = []
    active_containers: set[int] = set()
    nodes = 0
    current: tuple[object, str, int] | None = (value, label, 1)
    while current is not None or stack:
        if current is not None:
            item, path, depth = current
            current = None
            nodes += 1
            if nodes > MAX_JSON_NODES:
                raise SessionTruthContractError(
                    f"{label} exceeds the maximum JSON node count of {MAX_JSON_NODES}"
                )
            if depth > MAX_JSON_DEPTH:
                raise SessionTruthContractError(
                    f"{label} exceeds the maximum JSON depth of {MAX_JSON_DEPTH}"
                )

            if isinstance(item, Mapping) or isinstance(item, list):
                marker = id(item)
                if marker in active_containers:
                    raise SessionTruthContractError(
                        f"{label} contains a container cycle"
                    )
                active_containers.add(marker)
                children = iter(item.items()) if isinstance(item, Mapping) else enumerate(item)
                stack.append((item, children, path, depth, isinstance(item, Mapping)))
            elif isinstance(item, str):
                try:
                    item.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise SessionTruthContractError(
                        f"{path} contains text that is not valid UTF-8"
                    ) from exc
            elif isinstance(item, float):
                if not math.isfinite(item):
                    raise SessionTruthContractError(
                        f"{path} contains a forbidden non-finite number"
                    )
            elif item is not None and not isinstance(item, (int, bool)):
                raise SessionTruthContractError(
                    f"{path} contains a non-JSON value of type {type(item).__name__}"
                )
            continue

        container, children, path, depth, is_mapping = stack[-1]
        try:
            key, child = next(children)  # type: ignore[arg-type]
        except StopIteration:
            stack.pop()
            active_containers.remove(id(container))
            continue
        if is_mapping:
            if not isinstance(key, str):
                raise SessionTruthContractError(
                    f"{path} contains a non-string mapping key: {key!r}"
                )
            try:
                key.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise SessionTruthContractError(
                    f"{path} contains a mapping key that is not valid UTF-8"
                ) from exc
            child_path = f"{path}.{key}"
        else:
            child_path = f"{path}[{key}]"
        current = (child, child_path, depth + 1)


def canonical_json(value: object) -> str:
    """Return stable compact JSON suitable for semantic hashing.

    Serialization is strict: non-finite numbers, non-string mapping keys and
    non-JSON values raise :class:`SessionTruthContractError` rather than being
    coerced or emitted as non-RFC JSON.
    """

    validate_json_tree(value, "value")
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (RecursionError, TypeError, ValueError) as exc:
        raise SessionTruthContractError(
            f"value is not strict-JSON serializable: {exc}"
        ) from exc


def semantic_hash(value: object) -> str:
    """Return the SHA-256 digest of canonical JSON with an explicit algorithm prefix."""

    try:
        encoded = canonical_json(value).encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:  # defensive if the encoder contract changes
        raise SessionTruthContractError("value contains text that is not valid UTF-8") from exc
    digest = hashlib.sha256(encoded).hexdigest()
    return f"sha256:{digest}"


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionTruthContractError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    keys = set(value)
    unknown = sorted(keys - expected)
    missing = sorted(expected - keys)
    if unknown:
        qualifier = "top-level " if label == "input" else ""
        raise SessionTruthContractError(
            f"unknown {qualifier}key(s) in {label}: {', '.join(unknown)}"
        )
    if missing:
        raise SessionTruthContractError(
            f"missing key(s) in {label}: {', '.join(missing)}"
        )


def _bool(value: Mapping[str, Any], key: str, label: str) -> bool:
    if key not in value or type(value[key]) is not bool:
        raise SessionTruthContractError(f"{label}.{key} must be a boolean")
    return bool(value[key])


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise SessionTruthContractError(f"{label} must be a 40-hex Git SHA")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SessionTruthContractError(f"{label} must be a list of strings")
    return value


def _availability(source: Mapping[str, Any], label: str) -> bool:
    available = _bool(source, "available", label)
    if not available:
        reason = source.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise SessionTruthContractError(
                f"{label}.reason is required when {label}.available is false"
            )
    return available


def _validate_scope(raw: Any) -> None:
    scope = _mapping(raw, "scope")
    _exact_keys(scope, _SCOPE_KEYS, "scope")

    workstreams = _string_list(scope["workstreams"], "scope.workstreams")
    for key in workstreams:
        if not _WS_RE.fullmatch(key):
            raise SessionTruthContractError(
                f"scope.workstreams entry must use WS:<KEY> form: {key!r}"
            )

    linear = _string_list(scope["linear"], "scope.linear")
    for issue in linear:
        if not _MAS_RE.fullmatch(issue):
            raise SessionTruthContractError(
                f"scope.linear entry must use MAS-<digits> form: {issue!r}"
            )

    repositories = _string_list(scope["repositories"], "scope.repositories")
    for repository in repositories:
        if not _REPO_RE.fullmatch(repository):
            raise SessionTruthContractError(
                f"scope.repositories entry must use owner/name form: {repository!r}"
            )

    operation_key = scope["operation_key"]
    if operation_key is not None and (
        not isinstance(operation_key, str) or not operation_key.strip()
    ):
        raise SessionTruthContractError(
            "scope.operation_key must be null or a non-empty string"
        )
    _bool(scope, "requires_executive", "scope")


def _validate_skillpack(raw: Any) -> None:
    skillpack = _mapping(raw, "skillpack")
    available = _availability(skillpack, "skillpack")
    if "sha" not in skillpack:
        raise SessionTruthContractError("skillpack.sha is required")
    _sha(skillpack["sha"], "skillpack.sha")
    if not available:
        return

    required = ("repository", "schema", "version", "minimum_bootstrap_major")
    for key in required:
        if key not in skillpack:
            raise SessionTruthContractError(f"skillpack.{key} is required")
    if skillpack["repository"] != "mastermindx-market-intelligence/Mastermind":
        raise SessionTruthContractError("skillpack.repository is not canonical")
    if skillpack["schema"] != "mastermind.sol_skillpack.v1":
        raise SessionTruthContractError("skillpack.schema is incompatible")
    version = skillpack["version"]
    if not isinstance(version, str) or not version.strip():
        raise SessionTruthContractError("skillpack.version must be a non-empty string")
    minimum = skillpack["minimum_bootstrap_major"]
    if type(minimum) is not int or minimum < 1:
        raise SessionTruthContractError(
            "skillpack.minimum_bootstrap_major must be a positive integer"
        )


def _records_digest(value: Any, label: str) -> None:
    if not valid_source_records_digest(value):
        raise SessionTruthContractError(
            f"{label} must be an exact sha256:<64 lowercase hex> digest"
        )


def _validate_source(raw: Any, label: str) -> None:
    source = _mapping(raw, label)
    available = _availability(source, label)
    if label == "agentos":
        source_sha = source.get("source_sha")
        if available and source_sha is None:
            raise SessionTruthContractError("agentos.source_sha is required when available")
        if source_sha is not None:
            _sha(source_sha, "agentos.source_sha")
        # Agent OS interior values are owner passthrough: bound them to strict
        # JSON up front and validate any present owner record digest exactly.
        state = source.get("state")
        validate_json_tree(state, "agentos.state")
        if isinstance(state, Mapping) and "source_records_digest" in state:
            _records_digest(
                state["source_records_digest"], "agentos.state.source_records_digest"
            )
        contexts = source.get("contexts")
        validate_json_tree(contexts, "agentos.contexts")
        if isinstance(contexts, list):
            for index, context in enumerate(contexts):
                if isinstance(context, Mapping) and "source_records_digest" in context:
                    _records_digest(
                        context["source_records_digest"],
                        f"agentos.contexts[{index}].source_records_digest",
                    )


def validate_input_document(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and defensively copy one Session Truth input envelope.

    Validation is intentionally structural at this layer.  Plane-specific schemas are
    normalized and validated by ``session_truth_snapshots`` before entering this envelope.
    No source is defaulted to available or healthy.
    """

    root = _mapping(doc, "input")
    validate_json_tree(root, "input")
    _exact_keys(root, _TOP_LEVEL_KEYS, "input")
    if root["schema"] != INPUT_SCHEMA:
        raise SessionTruthContractError(
            f"schema must be exactly {INPUT_SCHEMA!r}"
        )

    _validate_scope(root["scope"])
    _validate_skillpack(root["skillpack"])
    for label in ("agentos", "github", "linear", "slack", "executive", "identities"):
        _validate_source(root[label], label)

    return copy.deepcopy(dict(root))
