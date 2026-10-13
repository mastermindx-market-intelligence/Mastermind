"""Closed product-acceptance request association, without issuance authority.

These values identify the exact retained request and reviewed result. Validation
does not establish that an owner issued the request or accepted the result.
The Runtime owner must independently join the retained issuance and ruling.
"""

from __future__ import annotations

import re
from typing import Any

from common.commission_ref import CommissionRefError, normalize_commission_ref

PRODUCT_ACCEPTANCE_ASSOCIATION_SCHEMA = "mastermind.product_acceptance_association.v1"
_IDENTIFIER = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")
_ISSUANCE = re.compile(r"\Aruntime-product-acceptance:[0-9a-f]{32}\Z")
_IDENTIFIERS = frozenset(
    {
        "root_job_id",
        "issuer_job_id",
        "issuer_attempt_id",
        "subject_job_id",
        "subject_attempt_id",
        "reviewer_job_id",
        "reviewer_attempt_id",
        "current_intent_revision",
    }
)
_DIGESTS = frozenset(
    {
        "subject_result_envelope_digest",
        "subject_role_result_digest",
        "reviewer_result_envelope_digest",
        "acceptance_basis_digest",
        "criteria_objective_sha256",
    }
)
_REFS = frozenset({"original_intent_ref", "current_intent_ref", "proof_contract_ref"})
PRODUCT_ACCEPTANCE_ASSOCIATION_FIELDS = (
    _IDENTIFIERS | _DIGESTS | _REFS | {"schema", "issuance_ref"}
)


class ProductAcceptanceContractError(ValueError):
    """Malformed association; no transport or authority side effect."""

    def __init__(
        self,
        message: str,
        *,
        repair_identity: str | None = None,
        repair_kind: str | None = None,
    ) -> None:
        self.repair_identity = repair_identity
        self.repair_kind = repair_kind
        super().__init__(message)


def validate_product_acceptance_association(value: Any) -> dict[str, Any]:
    """Return a detached, closed association; never infer missing identities."""
    if (
        type(value) is not dict
        or set(value) != PRODUCT_ACCEPTANCE_ASSOCIATION_FIELDS
        or value["schema"] != PRODUCT_ACCEPTANCE_ASSOCIATION_SCHEMA
    ):
        raise ProductAcceptanceContractError(
            "product acceptance association is invalid"
        )
    for field, pattern in (
        *((field, _IDENTIFIER) for field in _IDENTIFIERS),
        *((field, _DIGEST) for field in _DIGESTS),
        ("issuance_ref", _ISSUANCE),
    ):
        if type(value[field]) is not str or pattern.fullmatch(value[field]) is None:
            raise ProductAcceptanceContractError(
                "product acceptance association is invalid"
            )
    normalized = {key: value[key] for key in value if key not in _REFS}
    try:
        for field in _REFS:
            normalized[field] = normalize_commission_ref(value[field]).to_dict()
    except CommissionRefError as exc:
        raise ProductAcceptanceContractError(
            "product acceptance association is invalid"
        ) from exc
    return normalized


PRODUCT_ACCEPTANCE_REVIEW_PROOF_SCHEMA = "mastermind.product_acceptance_review_proof.v1"
_PROOF_STATES = frozenset({"SATISFIED", "UNSATISFIED", "UNPROVEN"})


def _proof_digest(value: Any) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ProductAcceptanceContractError("product acceptance proof is invalid")
    return value


def _proof_rows(value: Any, *, identity: str, maximum: int) -> list[dict[str, Any]]:
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise ProductAcceptanceContractError("product acceptance proof is invalid")
    rows = []
    seen = set()
    for row in value:
        if type(row) is not dict or set(row) != {identity, "state", "evidence_digests"}:
            raise ProductAcceptanceContractError("product acceptance proof is invalid")
        digest = _proof_digest(row[identity])
        state, evidence = row["state"], row["evidence_digests"]
        if (
            digest in seen
            or type(state) is not str
            or state not in _PROOF_STATES
            or type(evidence) is not list
            or len(evidence) > 64
        ):
            raise ProductAcceptanceContractError("product acceptance proof is invalid")
        evidence = [_proof_digest(item) for item in evidence]
        if len(set(evidence)) != len(evidence) or (
            state == "SATISFIED" and not evidence
        ):
            raise ProductAcceptanceContractError("product acceptance proof is invalid")
        seen.add(digest)
        rows.append({identity: digest, "state": state, "evidence_digests": evidence})
    return rows


def validate_product_acceptance_review_proof(value: Any) -> dict[str, Any]:
    """Validate explicit sealed-review data, not the truth of product evidence.

    A model-provided grade cannot issue a request, establish independent review
    eligibility, or substitute for an actual canonical principal RULING.
    """
    if (
        type(value) is not dict
        or set(value)
        != {"schema", "acceptance_basis_digest", "criteria", "obligations"}
        or value["schema"] != PRODUCT_ACCEPTANCE_REVIEW_PROOF_SCHEMA
    ):
        raise ProductAcceptanceContractError("product acceptance proof is invalid")
    return {
        "schema": PRODUCT_ACCEPTANCE_REVIEW_PROOF_SCHEMA,
        "acceptance_basis_digest": _proof_digest(value["acceptance_basis_digest"]),
        "criteria": _proof_rows(
            value["criteria"], identity="criterion_digest", maximum=6
        ),
        "obligations": _proof_rows(
            value["obligations"], identity="obligation_digest", maximum=64
        ),
    }


def require_complete_product_acceptance_review_proof(
    value: Any,
    *,
    expected_basis_digest: str,
    expected_criterion_digests: tuple[str, ...],
    expected_obligation_digests: tuple[str, ...],
) -> dict[str, Any]:
    """Require complete source-derived coverage, without returning a verdict.

    The existing owner must acquire expected values from the actual compiler
    and sole criteria parser. Public digests or constructor DTOs do not prove
    issuance. Even a complete, sealed, independent review needs the principal's
    exact committed ruling before acceptance may be projected.
    """
    proof = validate_product_acceptance_review_proof(value)
    if proof["acceptance_basis_digest"] != _proof_digest(expected_basis_digest):
        raise ProductAcceptanceContractError("product acceptance proof basis changed")
    for rows, expected, identity, maximum in (
        (proof["criteria"], expected_criterion_digests, "criterion_digest", 6),
        (proof["obligations"], expected_obligation_digests, "obligation_digest", 64),
    ):
        if type(expected) is not tuple or not 1 <= len(expected) <= maximum:
            raise ProductAcceptanceContractError(
                "product acceptance expected proof is invalid"
            )
        expected = tuple(_proof_digest(item) for item in expected)
        if len(set(expected)) != len(expected):
            raise ProductAcceptanceContractError(
                "product acceptance expected proof is invalid"
            )
        actual = tuple(row[identity] for row in rows)
        if actual != expected:
            missing = next(
                (digest for digest in expected if digest not in actual), None
            )
            extra = next((digest for digest in actual if digest not in expected), None)
            out_of_order = next(
                (
                    wanted
                    for observed, wanted in zip(actual, expected)
                    if observed != wanted
                ),
                None,
            )
            raise ProductAcceptanceContractError(
                "product acceptance must-have proof is incomplete",
                repair_identity=missing or extra or out_of_order,
                repair_kind=(
                    "MISSING_REQUIRED_PROOF"
                    if missing
                    else "UNEXPECTED_PROOF" if extra else "PROOF_ORDER_CHANGED"
                ),
            )
        failed = next((row for row in rows if row["state"] != "SATISFIED"), None)
        if failed is not None:
            raise ProductAcceptanceContractError(
                "product acceptance must-have proof is incomplete",
                repair_identity=failed[identity],
                repair_kind=failed["state"],
            )
    return proof
