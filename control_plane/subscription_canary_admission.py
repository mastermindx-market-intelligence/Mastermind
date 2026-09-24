"""Root-owned composition validator/factory for subscription canary admission.

This module seals one immutable activation-evidence object from facts already
owned by Capacity and the provider-realm/catalog composition. It does not own
capacity, routing, credentials, or process lifecycle. The existing worker
broker remains the process/lifecycle boundary.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import re
from typing import Any, Mapping

from control_plane.subscription_harness_bindings import (
    HarnessBindingError,
    get_binding,
)
from control_plane.subscription_provider_profiles import ProviderProfileError

SCHEMA = "mastermind.subscription_canary_admission/v1"
_SEAL = object()
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_BOOLEAN_ACTIVATION_KEYS = frozenset(
    {
        "adapter_implemented",
        "provider_realm_enrolled",
        "capacity_known",
        "usage_policy_satisfied",
        "real_canary_passed",
        "autonomous_allowed",
    }
)
_FACTORY_KEYS = frozenset(
    {
        "capacity_fact",
        "realm_receipt",
        "bindings_document",
        "profiles_document",
    }
)


class CanaryAdmissionError(RuntimeError):
    """A canary admission could not be sealed or consumed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _require_token(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or _ID_RE.fullmatch(value) is None:
        raise CanaryAdmissionError(f"{label} is invalid")
    return value


def _require_generation(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise CanaryAdmissionError(f"{label} is invalid")
    return value


def _reject_raw_booleans(kwargs: Mapping[str, Any]) -> None:
    unknown = [key for key in kwargs if key not in _FACTORY_KEYS]
    boolean_keys = [key for key in unknown if key in _BOOLEAN_ACTIVATION_KEYS or type(kwargs.get(key)) is bool]
    if boolean_keys:
        raise CanaryAdmissionError(
            "raw boolean activation input is refused: " + ",".join(sorted(boolean_keys))
        )
    if unknown:
        raise CanaryAdmissionError("unsupported admission input: " + ",".join(sorted(unknown)))


def compose_catalog_digest(
    *,
    bindings_document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> str:
    from control_plane.subscription_catalog import compose_catalog_digest as canonical_digest

    return canonical_digest(
        bindings_document=bindings_document,
        profiles_document=profiles_document,
    )


def _public_fields(admission: "SubscriptionCanaryAdmission") -> dict[str, Any]:
    return {
        "adapter_id": admission.adapter_id,
        "binding_id": admission.binding_id,
        "capacity_generation": admission.capacity_generation,
        "capacity_source": admission.capacity_source,
        "capacity_state": admission.capacity_state,
        "catalog_digest": admission.catalog_digest,
        "execution_mode": admission.execution_mode,
        "implementation_state": admission.implementation_state,
        "profile_id": admission.profile_id,
        "realm_generation": admission.realm_generation,
        "realm_receipt_digest": admission.realm_receipt_digest,
        "realm_receipt_id": admission.realm_receipt_id,
        "schema": SCHEMA,
        "worker_id": admission.worker_id,
    }


def _seal_digest(fields: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(fields)).encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class SubscriptionCanaryAdmission:
    """Immutable construction-time activation evidence for one interactive canary."""

    worker_id: str
    binding_id: str
    profile_id: str
    adapter_id: str
    execution_mode: str
    capacity_state: str
    capacity_source: str
    capacity_generation: int
    realm_receipt_id: str
    realm_receipt_digest: str
    realm_generation: int
    catalog_digest: str
    implementation_state: str
    seal_digest: str
    _seal: object = dataclasses.field(default=None, repr=False, compare=False)
    _capacity_fact: Any = dataclasses.field(default=None, repr=False, compare=False)
    _realm_receipt: Any = dataclasses.field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise CanaryAdmissionError("forged or unsealed canary admission")
        expected = _seal_digest(_public_fields(self))
        if self.seal_digest != expected:
            raise CanaryAdmissionError("forged or unsealed canary admission")


def _require_owner_facts(capacity_fact: Any, realm_receipt: Any) -> None:
    from control_plane.codex_provider_realm import (
        verify_provider_realm_enrollment_receipt,
    )
    from control_plane.model_router import verify_capacity_owner_fact

    from ops.executive_os.capacity_owner_facts import CapacityOwnerFact
    from ops.executive_os.provider_realm_facts import ProviderRealmEnrollmentReceipt

    if type(capacity_fact) is not CapacityOwnerFact:
        raise CanaryAdmissionError(
            "capacity_fact: typed capacity fact exported by the Capacity owner is required"
        )
    if type(realm_receipt) is not ProviderRealmEnrollmentReceipt:
        raise CanaryAdmissionError(
            "realm_receipt: issued provider-realm receipt is required"
        )
    verify_capacity_owner_fact(capacity_fact)
    verify_provider_realm_enrollment_receipt(realm_receipt)


def seal_subscription_canary_admission(
    *,
    capacity_fact: Any = None,
    realm_receipt: Any = None,
    bindings_document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> SubscriptionCanaryAdmission:
    """Seal one admission from owner-minted Capacity and realm facts."""

    _require_owner_facts(capacity_fact, realm_receipt)
    _reject_raw_booleans(kwargs)
    worker = _require_token(capacity_fact.worker_id, "worker_id")
    bound_id = _require_token(realm_receipt.binding_id, "binding_id")
    if capacity_fact.worker_id != worker:
        raise CanaryAdmissionError("capacity fact worker identity does not match")
    if realm_receipt.enrollment_state != "enrolled":
        raise CanaryAdmissionError("provider realm enrollment state is not enrolled")
    try:
        from control_plane.subscription_provider_profiles import (
            load_profiles,
            validate_profiles,
        )

        profiles = (
            validate_profiles(profiles_document)
            if profiles_document is not None
            else load_profiles()
        )
        binding = get_binding(
            bound_id,
            document=bindings_document,
            profiles_document=profiles,
        )
    except (HarnessBindingError, ProviderProfileError) as exc:
        raise CanaryAdmissionError("subscription harness binding is not reviewed") from exc
    if binding.implementation_state == "SPEC_ONLY":
        raise CanaryAdmissionError("implementation_state is SPEC_ONLY")
    if binding.autonomous_allowed is not False:
        raise CanaryAdmissionError("autonomous execution is impossible")
    digest = compose_catalog_digest(
        bindings_document=bindings_document,
        profiles_document=profiles,
    )
    if (
        realm_receipt.binding_id != binding.binding_id
        or realm_receipt.profile_id != binding.profile_id
        or realm_receipt.adapter_id != binding.adapter_id
    ):
        raise CanaryAdmissionError("issued realm receipt identity does not match")
    if realm_receipt.catalog_digest != digest:
        raise CanaryAdmissionError("issued realm receipt digest does not match the binding")
    fields = {
        "adapter_id": binding.adapter_id,
        "binding_id": binding.binding_id,
        "capacity_generation": capacity_fact.generation,
        "capacity_source": capacity_fact.source.value,
        "capacity_state": capacity_fact.state.value,
        "catalog_digest": digest,
        "execution_mode": "interactive_canary",
        "implementation_state": binding.implementation_state,
        "profile_id": binding.profile_id,
        "realm_generation": realm_receipt.generation,
        "realm_receipt_digest": realm_receipt.receipt_digest,
        "realm_receipt_id": realm_receipt.receipt_id,
        "schema": SCHEMA,
        "worker_id": worker,
    }
    return SubscriptionCanaryAdmission(
        worker_id=worker,
        binding_id=binding.binding_id,
        profile_id=binding.profile_id,
        adapter_id=binding.adapter_id,
        execution_mode="interactive_canary",
        capacity_state=capacity_fact.state.value,
        capacity_source=capacity_fact.source.value,
        capacity_generation=capacity_fact.generation,
        realm_receipt_id=realm_receipt.receipt_id,
        realm_receipt_digest=realm_receipt.receipt_digest,
        realm_generation=realm_receipt.generation,
        catalog_digest=digest,
        implementation_state=binding.implementation_state,
        seal_digest=_seal_digest(fields),
        _seal=_SEAL,
        _capacity_fact=capacity_fact,
        _realm_receipt=realm_receipt,
    )


def verify_subscription_canary_admission(
    admission: Any,
    *,
    adapter_id: str,
    bindings_document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> SubscriptionCanaryAdmission:
    """Re-prove a sealed admission against the current catalog and adapter identity."""

    if type(admission) is not SubscriptionCanaryAdmission:
        raise CanaryAdmissionError("canary admission is required")
    if admission._seal is not _SEAL:
        raise CanaryAdmissionError("_seal is not the factory seal")
    expected_digest = _seal_digest(_public_fields(admission))
    if type(admission.seal_digest) is not str or not hmac.compare_digest(
        admission.seal_digest, expected_digest
    ):
        raise CanaryAdmissionError("seal_digest does not cover current public fields")
    _require_owner_facts(admission._capacity_fact, admission._realm_receipt)
    if (
        admission._capacity_fact.worker_id != admission.worker_id
        or admission._capacity_fact.generation != admission.capacity_generation
        or admission._capacity_fact.state.value != admission.capacity_state
        or admission._capacity_fact.source.value != admission.capacity_source
    ):
        raise CanaryAdmissionError("capacity_fact does not match admission")
    if (
        admission._realm_receipt.receipt_id != admission.realm_receipt_id
        or admission._realm_receipt.receipt_digest != admission.realm_receipt_digest
        or admission._realm_receipt.generation != admission.realm_generation
        or admission._realm_receipt.enrollment_state != "enrolled"
    ):
        raise CanaryAdmissionError("realm_receipt does not match admission")
    if admission.adapter_id != adapter_id:
        raise CanaryAdmissionError("admission adapter identity does not match")
    if admission.execution_mode != "interactive_canary":
        raise CanaryAdmissionError("execution mode must be interactive_canary")
    if admission.implementation_state == "SPEC_ONLY":
        raise CanaryAdmissionError("implementation_state is SPEC_ONLY")
    from control_plane.executive_steward import CapacityState, SourceOwner

    if admission.capacity_source != SourceOwner.CAPACITY.value:
        raise CanaryAdmissionError("capacity source owner must be capacity")
    if admission.capacity_state != CapacityState.AVAILABLE.value:
        raise CanaryAdmissionError("capacity is not known")
    digest = compose_catalog_digest(
        bindings_document=bindings_document,
        profiles_document=profiles_document,
    )
    if digest != admission.catalog_digest:
        raise CanaryAdmissionError("catalog digest does not match the reviewed documents")
    try:
        binding = get_binding(
            admission.binding_id,
            document=bindings_document,
            profiles_document=profiles_document,
        )
    except (HarnessBindingError, ProviderProfileError) as exc:
        raise CanaryAdmissionError("subscription harness binding is not reviewed") from exc
    if (
        binding.binding_id != admission.binding_id
        or binding.profile_id != admission.profile_id
        or binding.adapter_id != admission.adapter_id
        or binding.implementation_state != admission.implementation_state
    ):
        raise CanaryAdmissionError("admission binding identity does not match the catalog")
    if binding.implementation_state == "SPEC_ONLY":
        raise CanaryAdmissionError("implementation_state is SPEC_ONLY")
    if admission._realm_receipt.catalog_digest != digest:
        raise CanaryAdmissionError("forged or stale realm receipt digest")
    return admission


__all__ = [
    "SCHEMA",
    "CanaryAdmissionError",
    "SubscriptionCanaryAdmission",
    "compose_catalog_digest",
    "seal_subscription_canary_admission",
    "verify_subscription_canary_admission",
]
