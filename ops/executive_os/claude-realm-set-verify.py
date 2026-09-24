"""Pure verification of an explicitly supplied set of Claude preflight receipts.

The verifier deliberately has no discovery, provider, filesystem, process, or
persistence behavior at call time.  It only revalidates the canonical closed
preflight receipt wire and derives a closed, sanitised realm-set result.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "mastermind.claude_realm_set_verification.v1"
MAX_RECEIPT_AGE = timedelta(minutes=5)
_CONFIDENCE_RANK = {"SLOT_ONLY": 0, "PROVIDER_REPORTED": 1}


class RealmSetVerificationError(RuntimeError):
    """Fail-closed refusal for a realm-set claim that cannot be proven."""


def _refuse(code: str) -> None:
    raise RealmSetVerificationError(code)


def _load_preflight_contract() -> Any:
    """Load the canonical preflight validator once, outside the verifier call."""

    path = Path(__file__).with_name("claude-worker-preflight.py")
    spec = importlib.util.spec_from_file_location(
        "_claude_worker_preflight_contract", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical Claude preflight contract is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_PREFLIGHT = _load_preflight_contract()


def _parse_utc(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _refuse(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _refuse(code)
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        _refuse(code)
    return parsed.astimezone(UTC)


def _validate_current_receipt(value: Any, *, verified_time: datetime) -> dict[str, Any]:
    try:
        receipt = _PREFLIGHT.validate_receipt(value)
    except _PREFLIGHT.PreflightError as exc:
        _refuse(str(exc) or "RECEIPT_INVALID")

    realm_label = receipt["realm_label"]
    if not isinstance(realm_label, str) or realm_label != realm_label.strip():
        _refuse("RECEIPT_INVALID")
    if not receipt["auth_ready"]:
        _refuse("PRELIGHT_NOT_ACCEPTED")
    if receipt["auth_method"] != "claudeai" or receipt["api_provider"] != "first_party":
        _refuse("NATIVE_AUTH_NOT_SELECTED")
    if receipt["macos_credential_isolation_basis"] == "UNKNOWN":
        _refuse("IDENTITY_CONFIDENCE_UNPROVEN")
    if receipt["auth_identity_confidence"] not in _CONFIDENCE_RANK:
        _refuse("IDENTITY_CONFIDENCE_UNPROVEN")

    observed_time = _parse_utc(receipt["observed_at"], code="OBSERVATION_TIME_INVALID")
    if observed_time > verified_time:
        _refuse("OBSERVATION_TIME_FUTURE_INCOHERENT")
    if verified_time - observed_time > MAX_RECEIPT_AGE:
        _refuse("RECEIPT_STALE")
    return receipt


def verify_realm_set(
    receipts: Sequence[Mapping[str, Any]], *, verified_at: str
) -> dict[str, Any]:
    """Prove only what closed, current native preflight receipts support.

    ``verified_at`` is supplied by the caller so this function neither reads a
    clock nor reaches outside the supplied receipt set.
    """

    if isinstance(receipts, (str, bytes)) or not isinstance(receipts, Sequence):
        _refuse("RECEIPT_COUNT_OUT_OF_RANGE")
    if not 1 <= len(receipts) <= 7:
        _refuse("RECEIPT_COUNT_OUT_OF_RANGE")
    verified_time = _parse_utc(verified_at, code="VERIFIED_AT_INVALID")

    validated = [
        _validate_current_receipt(receipt, verified_time=verified_time)
        for receipt in receipts
    ]
    realm_labels = sorted(receipt["realm_label"] for receipt in validated)
    if len(set(realm_labels)) != len(realm_labels):
        _refuse("DUPLICATE_REALM_LABEL")

    pairs = {(receipt["host_ref"], receipt["os_principal_ref"]) for receipt in validated}
    if len(pairs) != len(validated):
        _refuse("REALM_COLLISION")

    worker_ready_labels = sorted(
        receipt["realm_label"]
        for receipt in validated
        if receipt["execution_context"] == "WORKER_BROKER"
        and receipt["verdict"] == "WORKER_CONTEXT_AUTH_READY"
    )
    confidence_floor = min(
        (receipt["auth_identity_confidence"] for receipt in validated),
        key=_CONFIDENCE_RANK.__getitem__,
    )
    worker_ready = len(worker_ready_labels)
    return {
        "schema": SCHEMA,
        "verified_at": verified_at,
        "observed_realm_count": len(validated),
        "worker_ready_realm_count": worker_ready,
        "realm_labels": realm_labels,
        "worker_ready_realm_labels": worker_ready_labels,
        "unique_host_principal_pairs": len(pairs),
        "identity_confidence_floor": confidence_floor,
        "verdict": (
            "DISTINCT_NATIVE_REALMS"
            if worker_ready
            else "EXECUTION_CONTEXT_UNPROVEN"
        ),
        "reason_codes": [] if worker_ready else ["EXECUTION_CONTEXT_UNPROVEN"],
    }
