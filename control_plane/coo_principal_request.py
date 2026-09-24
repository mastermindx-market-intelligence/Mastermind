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
import re
from collections.abc import Mapping
from typing import Any

from control_plane import ceo_request


REQUEST_REF_PREFIX = "req-coo-"
INTENT_ID_PREFIX = "coo-"
_REQUEST_REF_DOMAIN = b"mastermind.executive_coo_principal.operation.v1\x00"
_INTENT_ID_DOMAIN = b"mastermind.executive_coo_principal.request_ref.v1\x00"
REQUEST_REF_RE = re.compile(r"^req-coo-[0-9a-f]{32}$")
INTENT_ID_RE = re.compile(r"^coo-[0-9a-f]{32}$")

MAX_ATTEMPT_LIMIT = 2
DEFAULT_ATTEMPT_LIMIT = 2

_REQUIRED = ceo_request.REQUIRED_FIELDS | frozenset({"workstream"})
_OPTIONAL = ceo_request.OPTIONAL_FIELDS - frozenset({"workstream"})


class CooPrincipalRequestError(ValueError):
    """The high-level COO request or its mission binding was refused."""


def _exact_public_keys(payload: object) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise CooPrincipalRequestError("request must be an object")
    keys = set(payload)
    missing = sorted(_REQUIRED - keys)
    unexpected = sorted(keys - _REQUIRED - _OPTIONAL)
    if missing:
        raise CooPrincipalRequestError(
            f"request is missing required field(s): {missing}"
        )
    if unexpected:
        raise CooPrincipalRequestError(
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
        raise CooPrincipalRequestError("expected_work_ref is invalid")

    try:
        normalized = ceo_request.normalize_high_level_request(dict(raw))
    except ceo_request.CeoRequestError as exc:
        raise CooPrincipalRequestError(exc.message) from exc

    work_ref = normalized.get("workstream")
    if work_ref != expected_work_ref:
        raise CooPrincipalRequestError(
            "workstream must equal the exact selected Mission Workspace work_ref"
        )

    attempt_limit = normalized.get("attempt_limit", DEFAULT_ATTEMPT_LIMIT)
    if type(attempt_limit) is not int or not 1 <= attempt_limit <= MAX_ATTEMPT_LIMIT:
        raise CooPrincipalRequestError(
            "attempt_limit must be between 1 and 2 for a COO principal root"
        )
    normalized["attempt_limit"] = attempt_limit
    return normalized


def principal_request_ref(normalized_request: Mapping[str, Any]) -> str:
    """Return the stable COO request identity for work_ref + operation_key."""

    if not isinstance(normalized_request, Mapping):
        raise CooPrincipalRequestError("normalized request must be an object")
    work_ref = normalized_request.get("workstream")
    operation_key = normalized_request.get("operation_key")
    if not isinstance(work_ref, str) or not isinstance(operation_key, str):
        raise CooPrincipalRequestError(
            "normalized request requires workstream and operation_key"
        )
    canonical = normalize_principal_request(
        dict(normalized_request), expected_work_ref=work_ref
    )
    if canonical != dict(normalized_request):
        raise CooPrincipalRequestError(
            "normalized request differs from the canonical COO request"
        )
    material = (work_ref + "\n" + operation_key).encode("utf-8")
    digest = hashlib.sha256(_REQUEST_REF_DOMAIN + material).hexdigest()
    request_ref = REQUEST_REF_PREFIX + digest[:32]
    if REQUEST_REF_RE.fullmatch(request_ref) is None:
        raise RuntimeError("derived COO request_ref is invalid")
    return request_ref


def principal_intent_id(request_ref: str) -> str:
    """Return the sink-compatible, separately namespaced COO intent id."""

    if not isinstance(request_ref, str) or REQUEST_REF_RE.fullmatch(request_ref) is None:
        raise CooPrincipalRequestError("request_ref is invalid")
    digest = hashlib.sha256(
        _INTENT_ID_DOMAIN + request_ref.encode("ascii")
    ).hexdigest()
    intent_id = INTENT_ID_PREFIX + digest[:32]
    if INTENT_ID_RE.fullmatch(intent_id) is None:
        raise RuntimeError("derived COO intent_id is invalid")
    return intent_id


__all__ = [
    "DEFAULT_ATTEMPT_LIMIT",
    "INTENT_ID_PREFIX",
    "INTENT_ID_RE",
    "MAX_ATTEMPT_LIMIT",
    "REQUEST_REF_PREFIX",
    "REQUEST_REF_RE",
    "CooPrincipalRequestError",
    "normalize_principal_request",
    "principal_intent_id",
    "principal_request_ref",
]
