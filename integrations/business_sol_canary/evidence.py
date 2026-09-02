"""H1 — deterministic one-cockpit receipt validator.

Pure, dependency-free (stdlib only) evidence validation for the frozen
contract ``mastermind.business_sol_one_cockpit_receipt.v1``.  This module
performs NO app/account/runtime action of any kind. It does not import an
MCP SDK, call the network, touch the filesystem beyond its own source, read
the process clock, read environment variables, or use randomness. Every
result is a pure function of its arguments.

Authority precedence (frozen at commission time, never re-derived here):

1. protected Skillpack/source law at current master
2. the P5 one-cockpit packet + its completion ruler
3. protected P1 #302 / ``12c2cb8993f78e81c6cb9e9a75a9829f9b194dab``
4. protected A1 #310 / ``524b6dc8071d6ea0b484819630e9de846e1df93e``
5. Executive MCP #64 canary receipt as SAMPLE evidence only, never live-
   production proof.

A retrieved receipt's own text NEVER grants authority — H1 only reports
whether a supplied packet satisfies the frozen contract below. A ``PASS``
verdict grants no Executive/Business/OAuth/deployment/merge/RuntimeBinding/
organizational authority; ``production_acceptance_granted`` is always
``False`` in the output.

Caller contract
----------------
``validate_receipt(packet, *, evaluated_at)`` takes the evidence packet and
a caller-supplied UTC instant string. H1 never calls ``datetime.now()`` (or
any other current-clock, environment, filesystem-discovery, network, or
random source) — every notion of "now" for freshness/staleness checks comes
from ``evaluated_at``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Schema identities
# ---------------------------------------------------------------------------

INPUT_SCHEMA_ID = "mastermind.business_sol_one_cockpit_receipt.v1"
OUTPUT_SCHEMA_ID = "mastermind.business_sol_h1_validation.v1"

#: Priority-3 authority anchor (frozen at commission time; never re-derived
#: from a runtime discovery of any kind).
EXPECTED_P1_COMMIT = "12c2cb8993f78e81c6cb9e9a75a9829f9b194dab"

#: Priority-4 authority anchor. Not itself a required input field (the
#: closed input contract below does not name an A1 commit field) but kept
#: here as the documented authority precedence anchor.
EXPECTED_A1_COMMIT = "524b6dc8071d6ea0b484819630e9de846e1df93e"

VERDICTS = frozenset({"PASS", "FAIL", "UNKNOWN", "REFUSED"})

#: Verdict precedence, highest first. The overall verdict is always the
#: highest-severity issue present; ``PASS`` only when zero issues exist.
_SEVERITY_ORDER = ("REFUSED", "FAIL", "UNKNOWN")
_SEVERITY_RANK = {name: rank for rank, name in enumerate(_SEVERITY_ORDER)}

_REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_id",
        "receipt_id",
        "generation_id",
        "observed_at",
        "is_correction",
        "correction",
        "source_refs",
        "cockpit_selection",
        "personal_cockpit",
        "business_membership_transition",
        "protected_baseline",
        "generation_identities",
        "steward_census",
        "control_room_evidence",
        "executive_admission",
        "rollback",
        "evidence_source_provenance",
    }
)

_ALLOWED_SELECTION_BASIS = frozenset({"opaque"})
_FORBIDDEN_SELECTION_BASIS = frozenset({"account", "title", "recency"})

_ALLOWED_INVENTORY_KINDS = frozenset({"package", "plugin", "tool", "app"})

_ALLOWED_GENERATION_COMPONENTS = ("s1", "executive_app", "control_room", "h1")

_ALLOWED_SOURCE_OWNERS = frozenset(
    {"s1", "executive_app", "control_room", "h1", "steward", "secretary", "business_app"}
)

_ALLOWED_CONTROL_ROOM_SURFACES = ("desktop", "mobile")
_ALLOWED_CONTROL_ROOM_STATES = (
    "normal",
    "stale",
    "degraded",
    "partial",
    "effect_unknown",
    "no_action",
)

_REQUIRED_EXECUTIVE_AUTHORITIES = frozenset({"READ", "RESEARCH"})

_ALLOWED_EVIDENCE_SOURCE_PROVENANCE = frozenset(
    {
        "live_receipt",
        "ci_green",
        "merge_event",
        "slack_delivery",
        "queued_fixture_job",
        "prose_claim",
    }
)

#: Bounded skew for evidence claiming a timestamp after ``evaluated_at``.
MAX_FUTURE_SKEW = timedelta(minutes=5)

#: Bounded staleness window for the receipt's own assembly timestamp.
MAX_RECEIPT_STALENESS = timedelta(hours=24)

_SHA256_HEX_RE = re.compile(r"\A[0-9a-f]{64}\Z")


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, order=True)
class Issue:
    """One deterministic finding against the frozen contract."""

    severity: str
    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "detail": self.detail,
        }


def _issue(issues: list[Issue], severity: str, code: str, path: str, detail: str) -> None:
    if severity not in _SEVERITY_RANK:
        raise ValueError("unknown issue severity")
    issues.append(Issue(severity=severity, code=code, path=path, detail=detail))


# ---------------------------------------------------------------------------
# Canonical JSON + digesting (house idiom — see
# integrations/mastermind_secretary_mcp/schemas.py:canonical_json; this
# package stays dependency-free and does not import that module).
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"value is not canonically JSON-representable: {type(value)!r}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


#: Top-level (dotted) paths whose immediate list value is a SET under the
#: frozen contract — order carries no meaning and must not affect the
#: digest, the verdict, or any issue. Entries are dicts sorted by their own
#: canonical bytes; plain string entries sort lexically.
_SET_LIST_PATHS = frozenset(
    {
        "cockpit_selection.control_refs",
        "source_refs",
        "protected_baseline.package_inventory",
        "protected_baseline.expected_package_inventory",
        "steward_census.tool_names",
        "executive_admission.authorities",
        "executive_admission.write_paths",
        "executive_admission.validation_commands",
        "executive_admission.worker_effects",
    }
)


def _sort_key(item: Any) -> tuple[int, Any]:
    if isinstance(item, str):
        return (0, item)
    return (1, canonical_json(item).decode("utf-8", errors="replace"))


def _normalize_for_digest(value: Any, *, path: str = "") -> Any:
    if isinstance(value, Mapping):
        normalized = {}
        for key in sorted(value, key=str):
            child_path = f"{path}.{key}" if path else str(key)
            normalized[str(key)] = _normalize_for_digest(value[key], path=child_path)
        return normalized
    if isinstance(value, (list, tuple)):
        items = [_normalize_for_digest(item, path=path) for item in value]
        if path in _SET_LIST_PATHS:
            items = sorted(items, key=_sort_key)
        return items
    return value


def canonical_input_digest(packet: Any) -> str:
    """Order-independent sha256 digest of ``packet``.

    Object keys are always order-independent (``canonical_json`` sorts
    them). Array fields the frozen contract treats as sets (see
    ``_SET_LIST_PATHS``) are additionally sorted before digesting, so two
    packets that differ only in key or set-array order digest identically.
    """

    return hashlib.sha256(canonical_json(_normalize_for_digest(packet))).hexdigest()


# ---------------------------------------------------------------------------
# Secret / private-locator screening — never echoes the offending value.
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "SECRET_BEARER_TOKEN",
        re.compile(r"(?i)\bbearer\s+[a-z0-9._\-=]{8,}"),
    ),
    (
        "SECRET_TOKEN_MATERIAL",
        re.compile(
            r"(?:sk-ant-|sk-[a-z0-9]|eyJ[a-z0-9]|ghp_|gho_|ghs_|github_pat_|"
            r"xox[abeprs]-|xapp-|AKIA[0-9A-Z]{4,}|ASIA[0-9A-Z]{4,})[a-z0-9._\-]{6,}",
            re.IGNORECASE,
        ),
    ),
    (
        "SECRET_REFRESH_MATERIAL",
        re.compile(r"(?i)\brefresh[_ -]?token\b\s*[:=]\s*\S+"),
    ),
    (
        "SECRET_TUNNEL_SECRET",
        re.compile(r"(?i)\btunnel[_ -]?secret\b\s*[:=]\s*\S+"),
    ),
    (
        "SECRET_EMAIL_ADDRESS",
        re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    ),
    (
        "SECRET_SESSION_IDENTIFIER",
        re.compile(r"(?i)\b(?:sess|session)[_-][A-Za-z0-9]{12,}\b"),
    ),
    (
        "SECRET_ACCOUNT_NUMBER",
        re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,4}\b"),
    ),
    (
        "SECRET_LOCAL_PATH",
        re.compile(r"(?:/Users/|/home/[a-z0-9_\-]+/|[A-Za-z]:\\\\)\S+"),
    ),
    (
        "SECRET_BROWSER_PROFILE",
        re.compile(r"(?i)\b(?:chrome|firefox|edge)[ _-]?profile[ _-]?\d*\b"),
    ),
    (
        "SECRET_SLACK_COORDINATE",
        re.compile(r"\b[CUGTD][A-Z0-9]{8,10}\b"),
    ),
    (
        "SECRET_MODEL_AUTHORITY_CLAIM",
        re.compile(
            r"(?i)\b(?:i hereby authorize|i grant myself|as the model,? i authorize|"
            r"i am authorized to proceed|granting myself authority)\b"
        ),
    ),
    (
        "SECRET_ERROR_LEAKAGE",
        re.compile(r"Traceback \(most recent call last\)"),
    ),
)


def _iter_string_leaves(value: Any, *, path: str = "$"):
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            yield from _iter_string_leaves(value[key], path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_string_leaves(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        yield path, value


def _scan_for_secrets(packet: Any) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for path, leaf in _iter_string_leaves(packet):
        for code, pattern in _SECRET_PATTERNS:
            if pattern.search(leaf) is not None:
                key = (code, path)
                if key in seen:
                    continue
                seen.add(key)
                _issue(
                    issues,
                    "REFUSED",
                    code,
                    path,
                    "evidence value at this path matches a forbidden secret/"
                    "private-locator pattern; the value itself is withheld",
                )
    return issues


def _is_secret_like(value: str) -> bool:
    """True if ``value`` matches any forbidden secret/private-locator pattern.

    Reuses the exact same pattern table as ``_scan_for_secrets`` so the
    output-redaction path (``_safe_identity`` below) and the REFUSED-issue
    path can never drift apart.
    """

    return any(pattern.search(value) is not None for _, pattern in _SECRET_PATTERNS)


def _safe_identity(value: Any) -> str | None:
    """Return ``value`` unchanged if it is a safe string, else ``None``.

    Used exclusively when projecting packet content into the OUTPUT
    document (``validated_identities``). A value that failed secret
    screening must never be echoed anywhere in the serialized output, not
    only withheld from the issue set — see
    ``test_secret_screened_values_never_appear_in_serialized_output``.
    """

    if not isinstance(value, str):
        return None
    if _is_secret_like(value):
        return None
    return value


# ---------------------------------------------------------------------------
# Small structural helpers
# ---------------------------------------------------------------------------


def _get(mapping: Any, key: str) -> Any:
    if isinstance(mapping, Mapping):
        return mapping.get(key)
    return None


def _require_mapping(
    issues: list[Issue], value: Any, *, path: str, code_prefix: str
) -> Mapping[str, Any] | None:
    if value is None:
        _issue(issues, "UNKNOWN", f"{code_prefix}_MISSING", path, "required section is absent")
        return None
    if not isinstance(value, Mapping):
        _issue(issues, "FAIL", f"{code_prefix}_TYPE_INVALID", path, "expected an object")
        return None
    return value


def _require_str(
    issues: list[Issue], value: Any, *, path: str, code: str, allow_empty: bool = False
) -> str | None:
    if value is None:
        _issue(issues, "UNKNOWN", f"{code}_MISSING", path, "required string is absent")
        return None
    if not isinstance(value, str) or (not allow_empty and value == ""):
        _issue(issues, "FAIL", f"{code}_INVALID", path, "expected a non-empty string")
        return None
    return value


def _require_bool(issues: list[Issue], value: Any, *, path: str, code: str) -> bool | None:
    if value is None:
        _issue(issues, "UNKNOWN", f"{code}_MISSING", path, "required boolean is absent")
        return None
    if not isinstance(value, bool):
        _issue(issues, "FAIL", f"{code}_INVALID", path, "expected a boolean")
        return None
    return value


def _require_int(issues: list[Issue], value: Any, *, path: str, code: str) -> int | None:
    if value is None:
        _issue(issues, "UNKNOWN", f"{code}_MISSING", path, "required integer is absent")
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _issue(issues, "FAIL", f"{code}_INVALID", path, "expected an integer")
        return None
    return value


def _check_unknown_keys(
    issues: list[Issue], value: Mapping[str, Any], *, allowed: frozenset[str], path: str
) -> None:
    for key in value:
        if key not in allowed:
            _issue(
                issues,
                "FAIL",
                "UNRECOGNIZED_FIELD",
                f"{path}.{key}",
                "field is not part of the closed input contract",
            )


# ---------------------------------------------------------------------------
# Timestamp law
# ---------------------------------------------------------------------------


def _parse_utc_instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    if parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(timezone.utc)


def _check_timestamp(
    issues: list[Issue],
    value: Any,
    *,
    path: str,
    evaluated_at: datetime,
    not_after: datetime | None = None,
    not_after_code: str = "TIMESTAMP_ORDER_INVERSION",
) -> datetime | None:
    """Validate one required timestamp field.

    Fail-closed by design: every timestamp this validator asks about is a
    required field, so a missing value is always reported
    (``TIMESTAMP_MISSING``, severity UNKNOWN) rather than silently skipped.
    There is deliberately no ``allow_missing`` escape hatch — a prior
    version defaulted to permissive and every call site had to opt in to
    strictness, which meant a single forgotten call site (top-level
    ``observed_at``, the membership-transition timestamps, both Steward
    read timestamps, and the Control Room per-state timestamps) silently
    turned an absent required timestamp into a false PASS. Absence that
    the contract genuinely allows (e.g. the whole ``post_expiry_read``
    section, or ``latest_attempt`` when ``attempts == 0``) is handled by
    the caller *before* reaching this function, never by parameterizing
    this one.
    """

    if value is None:
        _issue(issues, "UNKNOWN", "TIMESTAMP_MISSING", path, "required timestamp is absent")
        return None
    if not isinstance(value, str):
        _issue(issues, "FAIL", "TIMESTAMP_MALFORMED", path, "timestamp must be a string")
        return None
    parsed = _parse_utc_instant(value)
    if parsed is None:
        _issue(
            issues,
            "FAIL",
            "TIMESTAMP_MALFORMED",
            path,
            "timestamp is not a strict UTC ISO-8601 instant (impossible date, "
            "non-UTC offset, or unparsable)",
        )
        return None
    if parsed > evaluated_at + MAX_FUTURE_SKEW:
        _issue(
            issues,
            "FAIL",
            "TIMESTAMP_FUTURE",
            path,
            "timestamp is beyond the bounded future-skew window",
        )
    if not_after is not None and parsed > not_after + MAX_FUTURE_SKEW:
        _issue(
            issues,
            "FAIL",
            not_after_code,
            path,
            "timestamp is later than a required upper bound (contradictory "
            "clock or event-order inversion)",
        )
    return parsed


def _check_receipt_staleness(
    issues: list[Issue], receipt_observed_at: datetime | None, *, evaluated_at: datetime
) -> None:
    """Enforce the bounded staleness window on the receipt's own timestamp.

    Isolated as its own function (rather than inlined) so it is an
    independently mutable/testable enforcement unit — see the mutation-kill
    matrix in test_business_sol_canary_evidence_mutation.py.
    """

    if receipt_observed_at is not None and receipt_observed_at < evaluated_at - MAX_RECEIPT_STALENESS:
        _issue(
            issues,
            "FAIL",
            "TIMESTAMP_STALE",
            "observed_at",
            "the receipt is older than the bounded staleness window",
        )


# ---------------------------------------------------------------------------
# Section validators
# ---------------------------------------------------------------------------


def _validate_cockpit_selection(
    issues: list[Issue], section: Any, *, path: str
) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="COCKPIT_SELECTION")
    if body is None:
        return
    _check_unknown_keys(
        issues,
        body,
        allowed=frozenset({"selected_ref", "control_refs", "selection_basis"}),
        path=path,
    )
    selected = _require_str(issues, body.get("selected_ref"), path=f"{path}.selected_ref", code="COCKPIT_SELECTED_REF")
    controls_raw = body.get("control_refs")
    controls: list[str] = []
    if controls_raw is None:
        _issue(issues, "UNKNOWN", "COCKPIT_CONTROL_REFS_MISSING", f"{path}.control_refs", "required control refs are absent")
    elif not isinstance(controls_raw, Sequence) or isinstance(controls_raw, (str, bytes)):
        _issue(issues, "FAIL", "COCKPIT_CONTROL_REFS_INVALID", f"{path}.control_refs", "expected an array")
    else:
        controls = [item for item in controls_raw if isinstance(item, str)]
        if len(controls) != len(controls_raw) or len(controls) != 2:
            _issue(
                issues,
                "FAIL",
                "COCKPIT_CONTROL_REFS_CARDINALITY",
                f"{path}.control_refs",
                "exactly two string control-cockpit refs are required",
            )
        if len(set(controls)) != len(controls) and len(controls) > 0:
            _issue(
                issues,
                "FAIL",
                "COCKPIT_CONTROLS_DUPLICATED",
                f"{path}.control_refs",
                "the two control-cockpit refs must be distinct",
            )
        if selected is not None and selected in controls:
            _issue(
                issues,
                "FAIL",
                "COCKPIT_SELECTED_IN_CONTROLS",
                path,
                "the selected cockpit ref must not appear among the controls",
            )
    basis = body.get("selection_basis")
    if basis is None:
        _issue(issues, "UNKNOWN", "COCKPIT_SELECTION_BASIS_MISSING", f"{path}.selection_basis", "required field is absent")
    elif basis in _FORBIDDEN_SELECTION_BASIS or basis not in _ALLOWED_SELECTION_BASIS:
        _issue(
            issues,
            "FAIL",
            "COCKPIT_SELECTION_BASIS_INVALID",
            f"{path}.selection_basis",
            "cockpit selection must be declared opaque; account/title/"
            "recency-based selection is forbidden",
        )


def _validate_personal_cockpit(issues: list[Issue], section: Any, *, path: str) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="PERSONAL_COCKPIT")
    if body is None:
        return
    _check_unknown_keys(
        issues, body, allowed=frozenset({"separately_selectable", "merged_into_business"}), path=path
    )
    separately = _require_bool(
        issues, body.get("separately_selectable"), path=f"{path}.separately_selectable", code="PERSONAL_SEPARATELY_SELECTABLE"
    )
    merged = _require_bool(
        issues, body.get("merged_into_business"), path=f"{path}.merged_into_business", code="PERSONAL_MERGED_INTO_BUSINESS"
    )
    if merged is True:
        _issue(
            issues,
            "FAIL",
            "PERSONAL_MERGED_INTO_BUSINESS",
            path,
            "Personal must never be merged into Business",
        )
    if separately is False:
        _issue(
            issues,
            "FAIL",
            "PERSONAL_NOT_SEPARATELY_SELECTABLE",
            path,
            "Personal must remain separately selectable",
        )


def _validate_membership_transition(
    issues: list[Issue], section: Any, *, path: str, evaluated_at: datetime
) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="MEMBERSHIP_TRANSITION")
    if body is None:
        return
    allowed = frozenset(
        {
            "initial_state",
            "initial_observed_at",
            "transitioned_state",
            "transitioned_observed_at",
            "reverted_state",
            "reverted_observed_at",
            "readback_state",
            "readback_observed_at",
        }
    )
    _check_unknown_keys(issues, body, allowed=allowed, path=path)
    initial = _require_str(issues, body.get("initial_state"), path=f"{path}.initial_state", code="MEMBERSHIP_INITIAL_STATE")
    transitioned = _require_str(
        issues, body.get("transitioned_state"), path=f"{path}.transitioned_state", code="MEMBERSHIP_TRANSITIONED_STATE"
    )
    reverted = _require_str(issues, body.get("reverted_state"), path=f"{path}.reverted_state", code="MEMBERSHIP_REVERTED_STATE")
    readback = _require_str(issues, body.get("readback_state"), path=f"{path}.readback_state", code="MEMBERSHIP_READBACK_STATE")

    t_initial = _check_timestamp(
        issues, body.get("initial_observed_at"), path=f"{path}.initial_observed_at", evaluated_at=evaluated_at
    )
    # Sequence ordering (initial -> transitioned -> reverted -> readback) is
    # enforced explicitly below, not via `_check_timestamp`'s `not_after`.
    t_transitioned = _check_timestamp(
        issues,
        body.get("transitioned_observed_at"),
        path=f"{path}.transitioned_observed_at",
        evaluated_at=evaluated_at,
    )
    t_reverted = _check_timestamp(
        issues, body.get("reverted_observed_at"), path=f"{path}.reverted_observed_at", evaluated_at=evaluated_at
    )
    t_readback = _check_timestamp(
        issues, body.get("readback_observed_at"), path=f"{path}.readback_observed_at", evaluated_at=evaluated_at
    )

    ordered = [
        (t_initial, f"{path}.initial_observed_at"),
        (t_transitioned, f"{path}.transitioned_observed_at"),
        (t_reverted, f"{path}.reverted_observed_at"),
        (t_readback, f"{path}.readback_observed_at"),
    ]
    previous_value: datetime | None = None
    previous_path = ""
    for value, value_path in ordered:
        if value is not None and previous_value is not None and value < previous_value:
            _issue(
                issues,
                "FAIL",
                "TIMESTAMP_ORDER_INVERSION",
                value_path,
                f"must not precede {previous_path}",
            )
        if value is not None:
            previous_value = value
            previous_path = value_path

    if initial is not None and reverted is not None and initial != reverted:
        _issue(
            issues,
            "FAIL",
            "PERSONAL_REVERSIBILITY_INCOMPLETE",
            path,
            "the Business membership transition must revert to the initial "
            "(Personal) state",
        )
    if reverted is not None and readback is not None and reverted != readback:
        _issue(
            issues,
            "FAIL",
            "MEMBERSHIP_READBACK_MISMATCH",
            path,
            "post-revert readback state must match the reverted state",
        )
    if transitioned is not None and initial is not None and transitioned == initial:
        _issue(
            issues,
            "FAIL",
            "MEMBERSHIP_TRANSITION_NOT_APPLIED",
            path,
            "a reversible transition requires an actual state change before reverting",
        )


def _validate_protected_baseline(issues: list[Issue], section: Any, *, path: str) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="PROTECTED_BASELINE")
    if body is None:
        return
    allowed = frozenset(
        {
            "p1_commit",
            "package_inventory",
            "package_inventory_digest",
            "expected_package_inventory",
            "expected_package_inventory_digest",
        }
    )
    _check_unknown_keys(issues, body, allowed=allowed, path=path)

    commit = _require_str(issues, body.get("p1_commit"), path=f"{path}.p1_commit", code="P1_COMMIT")
    if commit is not None and commit != EXPECTED_P1_COMMIT:
        _issue(
            issues,
            "FAIL",
            "P1_COMMIT_MISMATCH",
            f"{path}.p1_commit",
            f"expected the protected P1 commit {EXPECTED_P1_COMMIT}",
        )

    observed_inventory, observed_digest = _validate_inventory(
        issues, body, prefix="package_inventory", path=path
    )
    expected_inventory, expected_digest = _validate_inventory(
        issues, body, prefix="expected_package_inventory", path=path
    )

    if observed_digest is not None and expected_digest is not None:
        if observed_digest != expected_digest:
            _issue(
                issues,
                "FAIL",
                "PACKAGE_INVENTORY_DRIFT",
                path,
                "observed package/plugin inventory digest does not match the "
                "expected inventory digest",
            )
    if observed_inventory is not None and expected_inventory is not None:
        extra = {(entry["name"], entry["kind"]) for entry in observed_inventory} - {
            (entry["name"], entry["kind"]) for entry in expected_inventory
        }
        if extra:
            _issue(
                issues,
                "FAIL",
                "EXTRA_COMPONENT_PRESENT",
                f"{path}.package_inventory",
                "one or more observed package/plugin/tool/app entries are not "
                "in the expected inventory",
            )


def _validate_inventory(
    issues: list[Issue], body: Mapping[str, Any], *, prefix: str, path: str
) -> tuple[list[dict[str, str]] | None, str | None]:
    list_path = f"{path}.{prefix}"
    digest_path = f"{path}.{prefix}_digest"
    raw_list = body.get(prefix)
    raw_digest = body.get(f"{prefix}_digest")

    entries: list[dict[str, str]] | None = None
    if raw_list is None:
        _issue(issues, "UNKNOWN", f"{prefix.upper()}_MISSING", list_path, "required inventory is absent")
    elif not isinstance(raw_list, Sequence) or isinstance(raw_list, (str, bytes)):
        _issue(issues, "FAIL", f"{prefix.upper()}_INVALID", list_path, "expected an array of inventory entries")
    else:
        entries = []
        valid = True
        for index, entry in enumerate(raw_list):
            if (
                not isinstance(entry, Mapping)
                or set(entry) != {"name", "kind"}
                or not isinstance(entry.get("name"), str)
                or not entry.get("name")
                or entry.get("kind") not in _ALLOWED_INVENTORY_KINDS
            ):
                _issue(
                    issues,
                    "FAIL",
                    f"{prefix.upper()}_ENTRY_INVALID",
                    f"{list_path}[{index}]",
                    "each inventory entry requires exactly {name, kind} with a "
                    "kind in package/plugin/tool/app",
                )
                valid = False
                continue
            entries.append({"name": entry["name"], "kind": entry["kind"]})
        if not valid:
            entries = None

    digest: str | None = None
    if raw_digest is None:
        _issue(issues, "UNKNOWN", f"{prefix.upper()}_DIGEST_MISSING", digest_path, "required digest is absent")
    elif not isinstance(raw_digest, str) or _SHA256_HEX_RE.match(raw_digest) is None:
        _issue(issues, "FAIL", f"{prefix.upper()}_DIGEST_INVALID", digest_path, "expected a sha256 hex digest")
    else:
        digest = raw_digest.lower()

    if entries is not None and digest is not None:
        recomputed = hashlib.sha256(
            canonical_json(sorted(entries, key=lambda item: (item["name"], item["kind"])))
        ).hexdigest()
        if recomputed != digest:
            _issue(
                issues,
                "FAIL",
                f"{prefix.upper()}_DIGEST_MISMATCH",
                digest_path,
                "declared digest does not match the digest recomputed from "
                "the declared inventory (internal tamper/drift)",
            )

    return entries, digest


def _validate_generation_identities(
    issues: list[Issue], section: Any, *, path: str, source_owner_by_ref: Mapping[str, str]
) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="GENERATION_IDENTITIES")
    if body is None:
        return
    _check_unknown_keys(issues, body, allowed=frozenset(_ALLOWED_GENERATION_COMPONENTS), path=path)
    for component in _ALLOWED_GENERATION_COMPONENTS:
        component_path = f"{path}.{component}"
        entry = body.get(component)
        entry_body = _require_mapping(issues, entry, path=component_path, code_prefix=f"GENERATION_{component.upper()}")
        if entry_body is None:
            continue
        _check_unknown_keys(
            issues,
            entry_body,
            allowed=frozenset({"expected_id", "observed_id", "source_ref_id"}),
            path=component_path,
        )
        expected_id = _require_str(
            issues, entry_body.get("expected_id"), path=f"{component_path}.expected_id", code="GENERATION_EXPECTED_ID"
        )
        observed_id = _require_str(
            issues, entry_body.get("observed_id"), path=f"{component_path}.observed_id", code="GENERATION_OBSERVED_ID"
        )
        if expected_id is not None and observed_id is not None and expected_id != observed_id:
            _issue(
                issues,
                "FAIL",
                "GENERATION_IDENTITY_MISMATCH",
                component_path,
                f"observed {component} generation identity does not match the "
                "expected identity",
            )
        ref_id = entry_body.get("source_ref_id")
        if ref_id is None:
            _issue(
                issues,
                "UNKNOWN",
                "GENERATION_SOURCE_REF_MISSING",
                f"{component_path}.source_ref_id",
                "required source reference is absent",
            )
        elif not isinstance(ref_id, str) or ref_id not in source_owner_by_ref:
            _issue(
                issues,
                "FAIL",
                "DANGLING_SOURCE_REF",
                f"{component_path}.source_ref_id",
                "source_ref_id does not resolve to a declared source_refs entry",
            )
        elif source_owner_by_ref[ref_id] != component:
            _issue(
                issues,
                "FAIL",
                "SOURCE_OWNER_MISMATCH",
                f"{component_path}.source_ref_id",
                f"referenced source is owned by "
                f"{source_owner_by_ref[ref_id]!r}, expected {component!r}",
            )


def _validate_source_refs(issues: list[Issue], section: Any, *, path: str) -> dict[str, str]:
    owner_by_ref: dict[str, str] = {}
    if section is None:
        _issue(issues, "UNKNOWN", "SOURCE_REFS_MISSING", path, "required source references are absent")
        return owner_by_ref
    if not isinstance(section, Sequence) or isinstance(section, (str, bytes)):
        _issue(issues, "FAIL", "SOURCE_REFS_INVALID", path, "expected an array")
        return owner_by_ref
    if len(section) == 0:
        _issue(issues, "UNKNOWN", "SOURCE_REFS_EMPTY", path, "at least one source reference is required")
    seen_ids: set[str] = set()
    for index, entry in enumerate(section):
        entry_path = f"{path}[{index}]"
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"ref_id", "owner"}
            or not isinstance(entry.get("ref_id"), str)
            or not entry.get("ref_id")
            or entry.get("owner") not in _ALLOWED_SOURCE_OWNERS
        ):
            _issue(
                issues,
                "FAIL",
                "SOURCE_REF_ENTRY_INVALID",
                entry_path,
                "each source ref requires exactly {ref_id, owner} with a "
                "recognized owner",
            )
            continue
        ref_id = entry["ref_id"]
        if ref_id in seen_ids:
            _issue(issues, "FAIL", "DUPLICATE_FIELD_IDENTITY", entry_path, "duplicate source ref_id")
            continue
        seen_ids.add(ref_id)
        owner_by_ref[ref_id] = entry["owner"]
    return owner_by_ref


def _validate_steward_census(
    issues: list[Issue], section: Any, *, path: str, evaluated_at: datetime, receipt_observed_at: datetime | None
) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="STEWARD_CENSUS")
    if body is None:
        return
    _check_unknown_keys(
        issues, body, allowed=frozenset({"tool_names", "initial_read", "post_expiry_read"}), path=path
    )

    tool_names = body.get("tool_names")
    tools_path = f"{path}.tool_names"
    if tool_names is None:
        _issue(issues, "UNKNOWN", "STEWARD_TOOL_NAMES_MISSING", tools_path, "required tool census is absent")
    elif (
        not isinstance(tool_names, Sequence)
        or isinstance(tool_names, (str, bytes))
        or not all(isinstance(item, str) and item for item in tool_names)
    ):
        _issue(issues, "FAIL", "STEWARD_TOOL_NAMES_INVALID", tools_path, "expected an array of tool name strings")
    elif len(set(tool_names)) != 6 or len(tool_names) != 6:
        _issue(
            issues,
            "FAIL",
            "STEWARD_TOOL_CENSUS_CARDINALITY",
            tools_path,
            "the Steward census requires exactly six distinct tools",
        )

    initial = _require_mapping(
        issues, body.get("initial_read"), path=f"{path}.initial_read", code_prefix="STEWARD_INITIAL_READ"
    )
    t_initial: datetime | None = None
    if initial is not None:
        _check_unknown_keys(
            issues,
            initial,
            allowed=frozenset({"observed_at", "authenticated", "token_material_present"}),
            path=f"{path}.initial_read",
        )
        t_initial = _check_timestamp(
            issues,
            initial.get("observed_at"),
            path=f"{path}.initial_read.observed_at",
            evaluated_at=evaluated_at,
            not_after=receipt_observed_at,
            not_after_code="TIMESTAMP_CONTRADICTORY_CLOCK",
        )
        authenticated = _require_bool(
            issues, initial.get("authenticated"), path=f"{path}.initial_read.authenticated", code="STEWARD_INITIAL_AUTHENTICATED"
        )
        if authenticated is False:
            _issue(
                issues,
                "FAIL",
                "STEWARD_INITIAL_READ_NOT_AUTHENTICATED",
                f"{path}.initial_read",
                "the first Steward read must be authenticated",
            )
        token_present = _require_bool(
            issues,
            initial.get("token_material_present"),
            path=f"{path}.initial_read.token_material_present",
            code="STEWARD_INITIAL_TOKEN_FLAG",
        )
        if token_present is True:
            _issue(
                issues,
                "REFUSED",
                "SECRET_TOKEN_MATERIAL",
                f"{path}.initial_read.token_material_present",
                "raw token material must never be carried in evidence",
            )

    post_expiry = body.get("post_expiry_read")
    if post_expiry is None:
        _issue(
            issues,
            "UNKNOWN",
            "STEWARD_POST_EXPIRY_READ_MISSING",
            f"{path}.post_expiry_read",
            "a second authenticated Steward read after token expiry/refresh "
            "is required",
        )
    else:
        post_body = _require_mapping(
            issues, post_expiry, path=f"{path}.post_expiry_read", code_prefix="STEWARD_POST_EXPIRY_READ"
        )
        if post_body is not None:
            _check_unknown_keys(
                issues,
                post_body,
                allowed=frozenset(
                    {"observed_at", "authenticated", "expired_token_used", "refresh_material_present"}
                ),
                path=f"{path}.post_expiry_read",
            )
            _check_timestamp(
                issues,
                post_body.get("observed_at"),
                path=f"{path}.post_expiry_read.observed_at",
                evaluated_at=evaluated_at,
                not_after=receipt_observed_at,
                not_after_code="TIMESTAMP_CONTRADICTORY_CLOCK",
            )
            authenticated = _require_bool(
                issues,
                post_body.get("authenticated"),
                path=f"{path}.post_expiry_read.authenticated",
                code="STEWARD_POST_EXPIRY_AUTHENTICATED",
            )
            if authenticated is False:
                _issue(
                    issues,
                    "FAIL",
                    "STEWARD_POST_EXPIRY_READ_NOT_AUTHENTICATED",
                    f"{path}.post_expiry_read",
                    "the post-expiry Steward read must be authenticated",
                )
            expired_used = _require_bool(
                issues,
                post_body.get("expired_token_used"),
                path=f"{path}.post_expiry_read.expired_token_used",
                code="STEWARD_EXPIRED_TOKEN_FLAG",
            )
            if expired_used is False:
                _issue(
                    issues,
                    "FAIL",
                    "STEWARD_POST_EXPIRY_NOT_AFTER_EXPIRY",
                    f"{path}.post_expiry_read",
                    "the second read must occur after token expiry/refresh",
                )
            refresh_present = _require_bool(
                issues,
                post_body.get("refresh_material_present"),
                path=f"{path}.post_expiry_read.refresh_material_present",
                code="STEWARD_REFRESH_MATERIAL_FLAG",
            )
            if refresh_present is True:
                _issue(
                    issues,
                    "REFUSED",
                    "SECRET_REFRESH_MATERIAL",
                    f"{path}.post_expiry_read.refresh_material_present",
                    "no refresh material may be present for the post-expiry read",
                )
            if (
                t_initial is not None
                and post_body.get("observed_at")
                and isinstance(post_body.get("observed_at"), str)
            ):
                t_post = _parse_utc_instant(post_body["observed_at"])
                if t_post is not None and t_post <= t_initial:
                    _issue(
                        issues,
                        "FAIL",
                        "TIMESTAMP_ORDER_INVERSION",
                        f"{path}.post_expiry_read.observed_at",
                        "must be strictly after the initial read",
                    )


def _validate_control_room_evidence(issues: list[Issue], section: Any, *, path: str, evaluated_at: datetime) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="CONTROL_ROOM_EVIDENCE")
    if body is None:
        return
    _check_unknown_keys(issues, body, allowed=frozenset(_ALLOWED_CONTROL_ROOM_SURFACES), path=path)
    for surface in _ALLOWED_CONTROL_ROOM_SURFACES:
        surface_path = f"{path}.{surface}"
        surface_body = _require_mapping(
            issues, body.get(surface), path=surface_path, code_prefix=f"CONTROL_ROOM_{surface.upper()}"
        )
        if surface_body is None:
            continue
        _check_unknown_keys(issues, surface_body, allowed=frozenset(_ALLOWED_CONTROL_ROOM_STATES), path=surface_path)
        for state in _ALLOWED_CONTROL_ROOM_STATES:
            state_path = f"{surface_path}.{state}"
            state_entry = surface_body.get(state)
            state_body = _require_mapping(
                issues, state_entry, path=state_path, code_prefix="CONTROL_ROOM_STATE"
            )
            if state_body is None:
                continue
            _check_unknown_keys(
                issues,
                state_body,
                allowed=frozenset({"observed_at", "structured_present", "text_fallback_present", "ui_only"}),
                path=state_path,
            )
            _check_timestamp(issues, state_body.get("observed_at"), path=f"{state_path}.observed_at", evaluated_at=evaluated_at)
            structured = _require_bool(
                issues, state_body.get("structured_present"), path=f"{state_path}.structured_present", code="CONTROL_ROOM_STRUCTURED"
            )
            text_fallback = _require_bool(
                issues, state_body.get("text_fallback_present"), path=f"{state_path}.text_fallback_present", code="CONTROL_ROOM_TEXT_FALLBACK"
            )
            ui_only = _require_bool(issues, state_body.get("ui_only"), path=f"{state_path}.ui_only", code="CONTROL_ROOM_UI_ONLY")
            if ui_only is True and structured is False and text_fallback is False:
                _issue(
                    issues,
                    "FAIL",
                    "CONTROL_ROOM_EVIDENCE_UI_ONLY",
                    state_path,
                    "UI-only evidence requires a structured or text fallback",
                )


def _check_executive_dispatched(issues: list[Issue], value: Any, *, path: str) -> bool | None:
    """Enforce ``dispatched == false``.

    Isolated as its own function (rather than inlined) so it is an
    independently mutable/testable enforcement unit — see the
    rule-granular mutation kills in
    test_business_sol_canary_evidence_mutation.py.
    """

    dispatched = _require_bool(issues, value, path=f"{path}.dispatched", code="EXECUTIVE_DISPATCHED")
    if dispatched is True:
        _issue(issues, "FAIL", "EXECUTIVE_DISPATCHED_TRUE", f"{path}.dispatched", "nothing may be dispatched")
    return dispatched


def _check_executive_attempts(issues: list[Issue], value: Any, *, path: str) -> int | None:
    """Enforce ``attempts == 0``. Isolated for rule-granular mutation testing."""

    attempts = _require_int(issues, value, path=f"{path}.attempts", code="EXECUTIVE_ATTEMPTS")
    if attempts is not None and attempts != 0:
        _issue(issues, "FAIL", "EXECUTIVE_ATTEMPTS_NONZERO", f"{path}.attempts", "attempts must be exactly 0")
    return attempts


def _check_executive_latest_attempt(
    issues: list[Issue], body: Mapping[str, Any], *, attempts: int | None, path: str
) -> None:
    """Enforce ``latest_attempt`` absent iff ``attempts == 0``.

    Isolated for rule-granular mutation testing.
    """

    latest_attempt = body.get("latest_attempt")
    if "latest_attempt" not in body:
        _issue(issues, "UNKNOWN", "EXECUTIVE_LATEST_ATTEMPT_MISSING", f"{path}.latest_attempt", "required field is absent")
    elif attempts == 0 and latest_attempt is not None:
        _issue(
            issues,
            "FAIL",
            "EXECUTIVE_WORKER_EFFECT_PRESENT",
            f"{path}.latest_attempt",
            "latest_attempt must be absent/null when attempts==0",
        )
    elif attempts != 0 and latest_attempt is None:
        _issue(
            issues,
            "FAIL",
            "EXECUTIVE_LATEST_ATTEMPT_INCONSISTENT",
            f"{path}.latest_attempt",
            "latest_attempt is required once attempts is non-zero",
        )


def _check_executive_authorities(issues: list[Issue], authorities: Any, *, path: str) -> None:
    """Enforce ``authorities == {READ, RESEARCH}`` exactly (cardinality and
    membership). Isolated for rule-granular mutation testing."""

    auth_path = f"{path}.authorities"
    if authorities is None:
        _issue(issues, "UNKNOWN", "EXECUTIVE_AUTHORITIES_MISSING", auth_path, "required authorities are absent")
    elif (
        not isinstance(authorities, Sequence)
        or isinstance(authorities, (str, bytes))
        or not all(isinstance(item, str) for item in authorities)
    ):
        _issue(issues, "FAIL", "EXECUTIVE_AUTHORITIES_INVALID", auth_path, "expected an array of authority strings")
    elif set(authorities) != _REQUIRED_EXECUTIVE_AUTHORITIES or len(authorities) != len(set(authorities)):
        _issue(
            issues,
            "FAIL",
            "EXECUTIVE_AUTHORITIES_INVALID",
            auth_path,
            "authorities must be exactly {READ, RESEARCH}, no more, no fewer",
        )


def _validate_executive_admission(issues: list[Issue], section: Any, *, path: str, evaluated_at: datetime) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="EXECUTIVE_ADMISSION")
    if body is None:
        return
    allowed = frozenset(
        {
            "operation_key",
            "intent_id",
            "job_id",
            "status",
            "dispatched",
            "attempts",
            "latest_attempt",
            "attempt_limit",
            "authorities",
            "write_paths",
            "validation_commands",
            "worker_effects",
            "wake_effect",
            "runtime_binding_effect",
            "slack_effect",
            "linear_effect",
            "agent_os_effect",
            "submission_count",
            "conflict_on_changed_payload",
            "status_readback",
        }
    )
    _check_unknown_keys(issues, body, allowed=allowed, path=path)

    operation_key = _require_str(issues, body.get("operation_key"), path=f"{path}.operation_key", code="EXECUTIVE_OPERATION_KEY")
    intent_id = _require_str(issues, body.get("intent_id"), path=f"{path}.intent_id", code="EXECUTIVE_INTENT_ID")
    job_id = _require_str(issues, body.get("job_id"), path=f"{path}.job_id", code="EXECUTIVE_JOB_ID")

    identities = [value for value in (operation_key, intent_id, job_id) if value is not None]
    if len(set(identities)) != len(identities):
        _issue(issues, "FAIL", "DUPLICATE_FIELD_IDENTITY", path, "operation_key/intent_id/job_id must be pairwise distinct")

    status = body.get("status")
    if status is None:
        _issue(issues, "UNKNOWN", "EXECUTIVE_STATUS_MISSING", f"{path}.status", "required status is absent")
    elif status != "QUEUED":
        _issue(issues, "FAIL", "EXECUTIVE_STATUS_NOT_QUEUED", f"{path}.status", "the admitted Job must be QUEUED")

    dispatched = _check_executive_dispatched(issues, body.get("dispatched"), path=path)
    attempts = _check_executive_attempts(issues, body.get("attempts"), path=path)
    _check_executive_latest_attempt(issues, body, attempts=attempts, path=path)

    attempt_limit = _require_int(issues, body.get("attempt_limit"), path=f"{path}.attempt_limit", code="EXECUTIVE_ATTEMPT_LIMIT")
    if attempt_limit is not None and attempt_limit != 1:
        _issue(issues, "FAIL", "EXECUTIVE_ATTEMPT_LIMIT_INVALID", f"{path}.attempt_limit", "attempt_limit must be exactly 1")

    _check_executive_authorities(issues, body.get("authorities"), path=path)

    for field, code in (
        ("write_paths", "EXECUTIVE_WRITE_PATH_PRESENT"),
        ("validation_commands", "EXECUTIVE_VALIDATION_COMMAND_PRESENT"),
        ("worker_effects", "EXECUTIVE_WORKER_EFFECT_PRESENT"),
    ):
        field_path = f"{path}.{field}"
        value = body.get(field)
        if value is None:
            _issue(issues, "UNKNOWN", f"{code}_UNDECLARED", field_path, "required field is absent")
        elif not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            _issue(issues, "FAIL", f"{field.upper()}_INVALID", field_path, "expected an array")
        elif len(value) > 0:
            _issue(issues, "FAIL", code, field_path, f"{field} must be empty")

    for field, code in (
        ("wake_effect", "EXECUTIVE_WAKE_EFFECT_PRESENT"),
        ("runtime_binding_effect", "EXECUTIVE_RUNTIME_BINDING_EFFECT_PRESENT"),
        ("slack_effect", "EXECUTIVE_SLACK_EFFECT_PRESENT"),
        ("linear_effect", "EXECUTIVE_LINEAR_EFFECT_PRESENT"),
        ("agent_os_effect", "EXECUTIVE_AGENT_OS_EFFECT_PRESENT"),
    ):
        field_path = f"{path}.{field}"
        value = _require_bool(issues, body.get(field), path=field_path, code=f"{code}_FLAG")
        if value is True:
            _issue(issues, "FAIL", code, field_path, f"{field} must be false")

    submission_count = _require_int(
        issues, body.get("submission_count"), path=f"{path}.submission_count", code="EXECUTIVE_SUBMISSION_COUNT"
    )
    if submission_count is not None and submission_count != 1:
        _issue(
            issues,
            "FAIL",
            "EXECUTIVE_DUPLICATE_SUBMISSION",
            f"{path}.submission_count",
            "exactly one modifying submission is permitted for this operation_key",
        )

    conflict = body.get("conflict_on_changed_payload")
    conflict_path = f"{path}.conflict_on_changed_payload"
    if conflict is None:
        _issue(
            issues,
            "UNKNOWN",
            "EXECUTIVE_CONFLICT_DECLARATION_MISSING",
            conflict_path,
            "the changed-payload conflict declaration is required (null body permitted, "
            "the key itself may not be absent)",
        )
    else:
        conflict_body = _require_mapping(issues, conflict, path=conflict_path, code_prefix="EXECUTIVE_CONFLICT")
        if conflict_body is not None:
            _check_unknown_keys(issues, conflict_body, allowed=frozenset({"detected", "reported"}), path=conflict_path)
            detected = _require_bool(issues, conflict_body.get("detected"), path=f"{conflict_path}.detected", code="EXECUTIVE_CONFLICT_DETECTED")
            reported = _require_bool(issues, conflict_body.get("reported"), path=f"{conflict_path}.reported", code="EXECUTIVE_CONFLICT_REPORTED")
            if detected is True and reported is not True:
                _issue(
                    issues,
                    "FAIL",
                    "EXECUTIVE_CONFLICT_OMITTED",
                    conflict_path,
                    "a detected changed-payload conflict must be reported",
                )

    readback = body.get("status_readback")
    readback_path = f"{path}.status_readback"
    readback_body = _require_mapping(issues, readback, path=readback_path, code_prefix="EXECUTIVE_STATUS_READBACK")
    if readback_body is not None:
        _check_unknown_keys(issues, readback_body, allowed=frozenset({"job_id", "status"}), path=readback_path)
        readback_job = _require_str(issues, readback_body.get("job_id"), path=f"{readback_path}.job_id", code="EXECUTIVE_READBACK_JOB_ID")
        readback_status = _require_str(
            issues, readback_body.get("status"), path=f"{readback_path}.status", code="EXECUTIVE_READBACK_STATUS"
        )
        if job_id is not None and readback_job is not None and job_id != readback_job:
            _issue(
                issues,
                "FAIL",
                "EXECUTIVE_STATUS_READBACK_MISMATCH",
                readback_path,
                "readback job_id does not match the admitted job_id",
            )
        if status is not None and readback_status is not None and status != readback_status:
            _issue(
                issues,
                "FAIL",
                "EXECUTIVE_STATUS_READBACK_MISMATCH",
                readback_path,
                "readback status does not match the admitted status",
            )


def _validate_rollback(issues: list[Issue], section: Any, *, path: str) -> None:
    body = _require_mapping(issues, section, path=path, code_prefix="ROLLBACK")
    if body is None:
        return
    allowed = frozenset(
        {
            "performed",
            "post_rollback_workspace_state",
            "post_rollback_plugin_state",
            "post_rollback_app_state",
            "readback_confirmed",
        }
    )
    _check_unknown_keys(issues, body, allowed=allowed, path=path)
    performed = _require_bool(issues, body.get("performed"), path=f"{path}.performed", code="ROLLBACK_PERFORMED")
    if performed is False:
        _issue(issues, "FAIL", "ROLLBACK_NOT_PERFORMED", path, "a rollback is required")
    for field in ("post_rollback_workspace_state", "post_rollback_plugin_state", "post_rollback_app_state"):
        _require_str(issues, body.get(field), path=f"{path}.{field}", code=f"ROLLBACK_{field.upper()}")
    readback_confirmed = _require_bool(
        issues, body.get("readback_confirmed"), path=f"{path}.readback_confirmed", code="ROLLBACK_READBACK_CONFIRMED"
    )
    if readback_confirmed is False:
        _issue(issues, "FAIL", "ROLLBACK_READBACK_MISSING", path, "post-rollback readback must be confirmed")


def _validate_correction(issues: list[Issue], packet: Mapping[str, Any], *, path: str) -> None:
    is_correction = packet.get("is_correction")
    correction = packet.get("correction")
    if is_correction is None:
        _issue(issues, "UNKNOWN", "CORRECTION_FLAG_MISSING", "is_correction", "required flag is absent")
        return
    if not isinstance(is_correction, bool):
        _issue(issues, "FAIL", "CORRECTION_FLAG_INVALID", "is_correction", "expected a boolean")
        return
    if is_correction is False:
        if correction is not None:
            _issue(
                issues,
                "FAIL",
                "CORRECTION_LINEAGE_UNEXPECTED",
                path,
                "correction lineage must be absent when is_correction is false",
            )
        return
    if correction is None:
        _issue(
            issues,
            "FAIL",
            "CORRECTION_LINEAGE_MISSING",
            path,
            "is_correction is true but no correction lineage was supplied",
        )
        return
    if not isinstance(correction, Mapping):
        _issue(issues, "FAIL", "CORRECTION_LINEAGE_INVALID", path, "expected an object")
        return
    body = correction
    _check_unknown_keys(issues, body, allowed=frozenset({"supersedes_digest"}), path=path)
    supersedes = body.get("supersedes_digest")
    if supersedes is None:
        _issue(issues, "FAIL", "CORRECTION_LINEAGE_MISSING", f"{path}.supersedes_digest", "exact prior digest is required")
    elif not isinstance(supersedes, str) or _SHA256_HEX_RE.match(supersedes) is None:
        _issue(
            issues,
            "FAIL",
            "CORRECTION_LINEAGE_INVALID",
            f"{path}.supersedes_digest",
            "supersedes_digest must be a sha256 hex digest naming the exact prior packet",
        )


# ---------------------------------------------------------------------------
# Verdict aggregation and output projection
# ---------------------------------------------------------------------------


def _aggregate_verdict(issues: Sequence[Issue]) -> str:
    if not issues:
        return "PASS"
    best_rank = min(_SEVERITY_RANK[issue.severity] for issue in issues)
    return _SEVERITY_ORDER[best_rank]


def _capability_state_projection(packet: Mapping[str, Any]) -> dict[str, Any]:
    admission = packet.get("executive_admission")
    admission = admission if isinstance(admission, Mapping) else {}
    rollback = packet.get("rollback")
    rollback = rollback if isinstance(rollback, Mapping) else {}

    def _absent(value: Any) -> str:
        if value is None:
            return "unknown"
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return "absent" if len(value) == 0 else "present"
        if isinstance(value, bool):
            return "absent" if value is False else "present"
        return "unknown"

    return {
        "executive_dispatch": (
            "not_dispatched" if admission.get("dispatched") is False else "unknown"
        ),
        "executive_attempts": "zero" if admission.get("attempts") == 0 else "unknown",
        "worker_effects": _absent(admission.get("worker_effects")),
        "wake_effect": _absent(admission.get("wake_effect")),
        "runtime_binding_effect": _absent(admission.get("runtime_binding_effect")),
        "slack_effect": _absent(admission.get("slack_effect")),
        "linear_effect": _absent(admission.get("linear_effect")),
        "agent_os_effect": _absent(admission.get("agent_os_effect")),
        "write_paths": _absent(admission.get("write_paths")),
        "validation_commands": _absent(admission.get("validation_commands")),
        "rollback_confirmed": (
            "confirmed"
            if rollback.get("performed") is True and rollback.get("readback_confirmed") is True
            else "unknown"
        ),
    }


def _validated_identities(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Project a small set of identity fields into the output.

    Every value projected here is a literal echo of caller-supplied packet
    content, so every one of them is passed through ``_safe_identity``
    first — a value that matches the secret/private-locator screen is
    withheld (``None``) here exactly as it is withheld from the issue set.
    This is deliberate defense in depth: a REFUSED verdict already tells
    the caller the packet is unsafe, but the *serialized output* must
    never carry the offending substring regardless of whether every call
    site remembers to check the verdict first.
    """

    generation_identities = packet.get("generation_identities")
    generation_identities = generation_identities if isinstance(generation_identities, Mapping) else {}
    projected_generation: dict[str, Any] = {}
    for component in _ALLOWED_GENERATION_COMPONENTS:
        entry = generation_identities.get(component)
        observed_id = entry.get("observed_id") if isinstance(entry, Mapping) else None
        projected_generation[component] = _safe_identity(observed_id)

    source_refs = packet.get("source_refs")
    ref_ids: list[str] = []
    if isinstance(source_refs, Sequence) and not isinstance(source_refs, (str, bytes)):
        for entry in source_refs:
            if isinstance(entry, Mapping):
                safe_ref_id = _safe_identity(entry.get("ref_id"))
                if safe_ref_id is not None:
                    ref_ids.append(safe_ref_id)

    return {
        "receipt_id": _safe_identity(packet.get("receipt_id")),
        "generation_id": _safe_identity(packet.get("generation_id")),
        "generation_identities": projected_generation,
        "source_ref_ids": sorted(ref_ids),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_receipt(packet: Any, *, evaluated_at: str) -> dict[str, Any]:
    """Validate ``packet`` against the frozen H1 input contract.

    ``evaluated_at`` is the caller-supplied UTC instant used for every
    freshness/staleness judgment; this function never reads the process
    clock, environment, filesystem, network, or any random source, and it
    never mutates ``packet`` or any historical evidence.

    Returns an ``mastermind.business_sol_h1_validation.v1`` document. Never
    raises for adversarial *content* of ``packet`` — malformed content is
    reported as issues. ``evaluated_at`` itself must be a valid, strict UTC
    ISO-8601 instant string; that is a caller/integration contract and a
    ``TypeError``/``ValueError`` there is a programming error, not evidence.
    """

    if not isinstance(evaluated_at, str):
        raise TypeError("evaluated_at must be a UTC ISO-8601 instant string")
    evaluated_dt = _parse_utc_instant(evaluated_at)
    if evaluated_dt is None:
        raise ValueError("evaluated_at must be a strict UTC ISO-8601 instant")

    issues: list[Issue] = []

    if not isinstance(packet, Mapping):
        _issue(issues, "REFUSED", "INPUT_NOT_MAPPING", "$", "the evidence packet must be a JSON object")
        digest = canonical_input_digest(packet)
        return _build_output(issues, digest, {})

    issues.extend(_scan_for_secrets(packet))

    _check_unknown_keys(issues, packet, allowed=_REQUIRED_TOP_LEVEL_KEYS, path="$")

    schema_id = packet.get("schema_id")
    if schema_id is None:
        _issue(issues, "UNKNOWN", "SCHEMA_IDENTITY_MISSING", "schema_id", "required field is absent")
    elif schema_id != INPUT_SCHEMA_ID:
        _issue(issues, "FAIL", "SCHEMA_IDENTITY_MISMATCH", "schema_id", f"expected {INPUT_SCHEMA_ID!r}")

    _require_str(issues, packet.get("receipt_id"), path="receipt_id", code="RECEIPT_ID")
    _require_str(issues, packet.get("generation_id"), path="generation_id", code="GENERATION_ID")

    receipt_observed_at = _check_timestamp(
        issues, packet.get("observed_at"), path="observed_at", evaluated_at=evaluated_dt
    )
    _check_receipt_staleness(issues, receipt_observed_at, evaluated_at=evaluated_dt)

    provenance = packet.get("evidence_source_provenance")
    if provenance is None:
        _issue(
            issues,
            "UNKNOWN",
            "EVIDENCE_SOURCE_PROVENANCE_MISSING",
            "evidence_source_provenance",
            "required field is absent",
        )
    elif provenance not in _ALLOWED_EVIDENCE_SOURCE_PROVENANCE:
        _issue(
            issues,
            "FAIL",
            "EVIDENCE_SOURCE_PROVENANCE_INVALID",
            "evidence_source_provenance",
            "not a recognized provenance value",
        )
    elif provenance != "live_receipt":
        _issue(
            issues,
            "REFUSED",
            "EVIDENCE_SOURCE_NOT_LIVE_RECEIPT",
            "evidence_source_provenance",
            "green CI, a merge event, Slack delivery, a queued fixture Job, "
            "or a prose claim can never substitute for the live receipt",
        )

    owner_by_ref = _validate_source_refs(issues, packet.get("source_refs"), path="source_refs")

    _validate_cockpit_selection(issues, packet.get("cockpit_selection"), path="cockpit_selection")
    _validate_personal_cockpit(issues, packet.get("personal_cockpit"), path="personal_cockpit")
    _validate_membership_transition(
        issues,
        packet.get("business_membership_transition"),
        path="business_membership_transition",
        evaluated_at=evaluated_dt,
    )
    _validate_protected_baseline(issues, packet.get("protected_baseline"), path="protected_baseline")
    _validate_generation_identities(
        issues,
        packet.get("generation_identities"),
        path="generation_identities",
        source_owner_by_ref=owner_by_ref,
    )
    _validate_steward_census(
        issues,
        packet.get("steward_census"),
        path="steward_census",
        evaluated_at=evaluated_dt,
        receipt_observed_at=receipt_observed_at,
    )
    _validate_control_room_evidence(
        issues, packet.get("control_room_evidence"), path="control_room_evidence", evaluated_at=evaluated_dt
    )
    _validate_executive_admission(
        issues, packet.get("executive_admission"), path="executive_admission", evaluated_at=evaluated_dt
    )
    _validate_rollback(issues, packet.get("rollback"), path="rollback")
    _validate_correction(issues, packet, path="correction")

    digest = canonical_input_digest(packet)
    return _build_output(issues, digest, packet)


def _build_output(issues: list[Issue], digest: str, packet: Mapping[str, Any]) -> dict[str, Any]:
    sorted_issues = sorted(issues)
    return {
        "schema_id": OUTPUT_SCHEMA_ID,
        "verdict": _aggregate_verdict(sorted_issues),
        "issues": [issue.as_dict() for issue in sorted_issues],
        "canonical_input_digest": digest,
        "validated_identities": _validated_identities(packet),
        "capability_state_projection": _capability_state_projection(packet),
        "production_acceptance_granted": False,
    }


__all__ = [
    "INPUT_SCHEMA_ID",
    "OUTPUT_SCHEMA_ID",
    "EXPECTED_P1_COMMIT",
    "EXPECTED_A1_COMMIT",
    "VERDICTS",
    "Issue",
    "canonical_json",
    "canonical_input_digest",
    "validate_receipt",
]
