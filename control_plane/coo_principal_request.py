"""Pure high-level COO principal request normalization and identity.

This module reuses the existing ceo_request semantic normalization law. It does
not create Jobs, open Runtime, authenticate OAuth, select providers, read a
clock, persist state, or widen worker authority.

The COO layer adds only:
- workstream is mandatory and must equal the selected Mission Workspace work_ref;
- strict COO roots use attempt_limit 1..2 (default 2);
- request identity is separately namespaced and derives only from
  work_ref + operation_key, so semantic payload changes reconcile/conflict under
  one stable logical operation instead of minting a second operation.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from control_plane import ceo_intent, ceo_request


REQUEST_REF_PREFIX = "req-coo-"
INTENT_ID_PREFIX = "coo-"
_REQUEST_REF_DOMAIN = b"mastermind.executive_coo_principal.operation.v1\x00"
_INTENT_ID_DOMAIN = b"mastermind.executive_coo_principal.request_ref.v1\x00"
REQUEST_REF_RE = re.compile(r"^req-coo-[0-9a-f]{32}$")
INTENT_ID_RE = re.compile(r"^coo-[0-9a-f]{32}$")

BOUNDED_ACTION_KIND = "bounded_intent"
ORCHESTRATION_ACTION_KIND = "governed_orchestration"
_ACTION_FINGERPRINT_DOMAIN = b"mastermind.executive_coo_principal.action.v1\x00"
ORCHESTRATION_BUSINESS_IMPACTS = frozenset({"routine", "material", "critical"})
ORCHESTRATION_REQUIRED_FIELDS = frozenset(
    {
        "operation_key",
        "objective",
        "department",
        "priority",
        "workstream",
        "business_impact",
    }
)

MAX_ATTEMPT_LIMIT = 2
DEFAULT_ATTEMPT_LIMIT = 2

_REQUIRED = ceo_request.REQUIRED_FIELDS | frozenset({"workstream"})
_OPTIONAL = ceo_request.OPTIONAL_FIELDS - frozenset({"workstream"})


class CooPrincipalRequestError(ValueError):
    """Base typed refusal for COO request normalization/derivation."""

    def __init__(self, message: str, *, caller_fault: bool) -> None:
        super().__init__(message)
        self.message = message
        self.caller_fault = caller_fault


class CooPrincipalRequestInvalid(CooPrincipalRequestError):
    """Caller-authored business fields or mission binding are invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, caller_fault=True)


class CooPrincipalRequestInternalError(CooPrincipalRequestError):
    """Trusted derivation/policy is inconsistent; never a caller mistake."""

    def __init__(self, message: str = "COO request policy is internally inconsistent") -> None:
        super().__init__(message, caller_fault=False)


def _exact_public_keys(payload: object) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise CooPrincipalRequestInvalid("request must be an object")
    keys = set(payload)
    missing = sorted(_REQUIRED - keys)
    unexpected = sorted(keys - _REQUIRED - _OPTIONAL)
    if missing:
        raise CooPrincipalRequestInvalid(
            f"request is missing required field(s): {missing}"
        )
    if unexpected:
        raise CooPrincipalRequestInvalid(
            f"request has unexpected field(s): {unexpected}"
        )
    return payload


def normalize_principal_request(
    payload: object,
    *,
    expected_work_ref: str,
) -> dict[str, Any]:
    """Normalize one public COO request through the existing shared law.

    The caller can author objective/department/priority/profile/workstream and
    the existing bounded path/validation/attempt fields only. Actor, seat,
    authority, branch, worktree, provider/model/account/host/realm, release,
    dispatch, credential, service and session fields remain outside the exact
    public key set and are refused by construction.
    """

    raw = _exact_public_keys(payload)
    if not isinstance(expected_work_ref, str) or not expected_work_ref:
        raise CooPrincipalRequestInvalid("expected_work_ref is invalid")

    try:
        normalized = ceo_request.normalize_high_level_request(dict(raw))
    except ceo_request.CeoRequestInvalid as exc:
        raise CooPrincipalRequestInvalid(exc.message) from exc
    except ceo_request.CeoRequestInternalError as exc:
        raise CooPrincipalRequestInternalError() from exc

    work_ref = normalized.get("workstream")
    if work_ref != expected_work_ref:
        raise CooPrincipalRequestInvalid(
            "workstream must equal the exact selected Mission Workspace work_ref"
        )

    attempt_limit = normalized.get("attempt_limit", DEFAULT_ATTEMPT_LIMIT)
    if type(attempt_limit) is not int or not 1 <= attempt_limit <= MAX_ATTEMPT_LIMIT:
        raise CooPrincipalRequestInvalid(
            "attempt_limit must be between 1 and 2 for a COO principal root"
        )
    normalized["attempt_limit"] = attempt_limit
    return normalized


def normalize_principal_orchestration_request(
    payload: object,
    *,
    expected_work_ref: str,
) -> dict[str, Any]:
    """Normalize one role-correct governed-orchestration request.

    This public shape is intentionally narrower than `normalize_principal_request`.
    The principal supplies business intent only. Execution profile, write/test scope,
    attempt budget, worktree/branch, placement and provider identities belong to the
    existing host/Router/Capacity owners and are therefore not accepted here.
    """

    if not isinstance(payload, Mapping):
        raise CooPrincipalRequestInvalid("request must be an object")
    keys = set(payload)
    missing = sorted(ORCHESTRATION_REQUIRED_FIELDS - keys)
    unexpected = sorted(keys - ORCHESTRATION_REQUIRED_FIELDS)
    if missing:
        raise CooPrincipalRequestInvalid(
            f"orchestration request is missing required field(s): {missing}"
        )
    if unexpected:
        raise CooPrincipalRequestInvalid(
            f"orchestration request has unexpected field(s): {unexpected}"
        )
    if not isinstance(expected_work_ref, str) or not expected_work_ref:
        raise CooPrincipalRequestInvalid("expected_work_ref is invalid")

    # Reuse the accepted shared validators for the common business fields.
    # `research_only` is an internal validation surrogate only; it is never
    # returned from this function and grants no orchestration execution profile.
    validation_payload = {
        "operation_key": payload["operation_key"],
        "objective": payload["objective"],
        "department": payload["department"],
        "priority": payload["priority"],
        "execution_profile": "research_only",
        "workstream": payload["workstream"],
    }
    try:
        shared = ceo_request.normalize_high_level_request(validation_payload)
    except ceo_request.CeoRequestInvalid as exc:
        raise CooPrincipalRequestInvalid(exc.message) from exc
    except ceo_request.CeoRequestInternalError as exc:
        raise CooPrincipalRequestInternalError() from exc

    if shared.get("workstream") != expected_work_ref:
        raise CooPrincipalRequestInvalid(
            "workstream must equal the exact selected Mission Workspace work_ref"
        )

    impact = payload["business_impact"]
    if not isinstance(impact, str) or impact not in ORCHESTRATION_BUSINESS_IMPACTS:
        raise CooPrincipalRequestInvalid(
            "business_impact must be routine, material, or critical"
        )

    return {
        "operation_key": shared["operation_key"],
        "objective": shared["objective"],
        "department": shared["department"],
        "priority": shared["priority"],
        "workstream": shared["workstream"],
        "business_impact": impact,
    }


def _stable_request_ref(*, work_ref: str, operation_key: str) -> str:
    material = (work_ref + "\n" + operation_key).encode("utf-8")
    digest = hashlib.sha256(_REQUEST_REF_DOMAIN + material).hexdigest()
    request_ref = REQUEST_REF_PREFIX + digest[:32]
    if (
        REQUEST_REF_RE.fullmatch(request_ref) is None
        or ceo_request.AUTOMATED_REQUEST_REF_RE.fullmatch(request_ref) is None
    ):
        raise CooPrincipalRequestInternalError()
    return request_ref


def _action_fingerprint(
    normalized_request: Mapping[str, Any],
    *,
    action_kind: str,
) -> str:
    try:
        payload = json.dumps(
            {
                "action_kind": action_kind,
                "request": dict(normalized_request),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CooPrincipalRequestInvalid(
            "normalized request is not canonical JSON data"
        ) from exc
    return hashlib.sha256(_ACTION_FINGERPRINT_DOMAIN + payload).hexdigest()


def principal_request_fingerprint(
    normalized_request: Mapping[str, Any],
) -> str:
    """Fingerprint one canonical bounded-worker request with its action kind."""

    if not isinstance(normalized_request, Mapping):
        raise CooPrincipalRequestInvalid("normalized request must be an object")
    work_ref = normalized_request.get("workstream")
    if not isinstance(work_ref, str):
        raise CooPrincipalRequestInvalid("normalized request requires workstream")
    canonical = normalize_principal_request(
        dict(normalized_request), expected_work_ref=work_ref
    )
    if canonical != dict(normalized_request):
        raise CooPrincipalRequestInvalid(
            "normalized request differs from the canonical COO request"
        )
    return _action_fingerprint(canonical, action_kind=BOUNDED_ACTION_KIND)


def orchestration_request_ref(
    normalized_request: Mapping[str, Any],
) -> str:
    """Return the same logical-operation identity used by bounded COO work."""

    if not isinstance(normalized_request, Mapping):
        raise CooPrincipalRequestInvalid("normalized request must be an object")
    work_ref = normalized_request.get("workstream")
    operation_key = normalized_request.get("operation_key")
    if not isinstance(work_ref, str) or not isinstance(operation_key, str):
        raise CooPrincipalRequestInvalid(
            "normalized request requires workstream and operation_key"
        )
    canonical = normalize_principal_orchestration_request(
        dict(normalized_request), expected_work_ref=work_ref
    )
    if canonical != dict(normalized_request):
        raise CooPrincipalRequestInvalid(
            "normalized request differs from the canonical COO orchestration request"
        )
    return _stable_request_ref(work_ref=work_ref, operation_key=operation_key)


def orchestration_request_fingerprint(
    normalized_request: Mapping[str, Any],
) -> str:
    """Fingerprint one canonical orchestration request with a distinct action kind."""

    if not isinstance(normalized_request, Mapping):
        raise CooPrincipalRequestInvalid("normalized request must be an object")
    work_ref = normalized_request.get("workstream")
    if not isinstance(work_ref, str):
        raise CooPrincipalRequestInvalid("normalized request requires workstream")
    canonical = normalize_principal_orchestration_request(
        dict(normalized_request), expected_work_ref=work_ref
    )
    if canonical != dict(normalized_request):
        raise CooPrincipalRequestInvalid(
            "normalized request differs from the canonical COO orchestration request"
        )
    return _action_fingerprint(canonical, action_kind=ORCHESTRATION_ACTION_KIND)


def principal_request_ref(normalized_request: Mapping[str, Any]) -> str:
    """Return the stable COO request identity for work_ref + operation_key."""

    if not isinstance(normalized_request, Mapping):
        raise CooPrincipalRequestInvalid("normalized request must be an object")
    work_ref = normalized_request.get("workstream")
    operation_key = normalized_request.get("operation_key")
    if not isinstance(work_ref, str) or not isinstance(operation_key, str):
        raise CooPrincipalRequestInvalid(
            "normalized request requires workstream and operation_key"
        )
    canonical = normalize_principal_request(
        dict(normalized_request), expected_work_ref=work_ref
    )
    if canonical != dict(normalized_request):
        raise CooPrincipalRequestInvalid(
            "normalized request differs from the canonical COO request"
        )
    material = (work_ref + "\n" + operation_key).encode("utf-8")
    digest = hashlib.sha256(_REQUEST_REF_DOMAIN + material).hexdigest()
    request_ref = REQUEST_REF_PREFIX + digest[:32]
    if (
        REQUEST_REF_RE.fullmatch(request_ref) is None
        or ceo_request.AUTOMATED_REQUEST_REF_RE.fullmatch(request_ref) is None
    ):
        raise CooPrincipalRequestInternalError()
    return request_ref


def principal_intent_id(request_ref: str) -> str:
    """Return the sink-compatible, separately namespaced COO intent id."""

    if not isinstance(request_ref, str) or REQUEST_REF_RE.fullmatch(request_ref) is None:
        raise CooPrincipalRequestInvalid("request_ref is invalid")
    digest = hashlib.sha256(
        _INTENT_ID_DOMAIN + request_ref.encode("ascii")
    ).hexdigest()
    intent_id = INTENT_ID_PREFIX + digest[:32]
    if (
        INTENT_ID_RE.fullmatch(intent_id) is None
        or ceo_intent.INTENT_ID_RE.fullmatch(intent_id) is None
    ):
        raise CooPrincipalRequestInternalError()
    return intent_id


__all__ = [
    "BOUNDED_ACTION_KIND",
    "DEFAULT_ATTEMPT_LIMIT",
    "INTENT_ID_PREFIX",
    "INTENT_ID_RE",
    "MAX_ATTEMPT_LIMIT",
    "ORCHESTRATION_ACTION_KIND",
    "ORCHESTRATION_BUSINESS_IMPACTS",
    "ORCHESTRATION_REQUIRED_FIELDS",
    "REQUEST_REF_PREFIX",
    "REQUEST_REF_RE",
    "CooPrincipalRequestError",
    "CooPrincipalRequestInvalid",
    "CooPrincipalRequestInternalError",
    "normalize_principal_orchestration_request",
    "normalize_principal_request",
    "orchestration_request_fingerprint",
    "orchestration_request_ref",
    "principal_intent_id",
    "principal_request_fingerprint",
    "principal_request_ref",
]
