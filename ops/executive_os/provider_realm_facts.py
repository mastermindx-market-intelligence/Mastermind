"""Typed, issued receipts exported by the existing provider-realm owner."""

from __future__ import annotations

import dataclasses

_SEAL = object()
_VALID_ENROLLMENT_STATES = frozenset({"enrolled", "unenrolled"})


class ProviderRealmFactError(ValueError):
    """The provider-realm owner refused to issue or consume a receipt."""


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderRealmEnrollmentReceipt:
    receipt_id: str
    receipt_digest: str
    binding_id: str
    profile_id: str
    adapter_id: str
    generation: int
    enrollment_state: str
    _seal: object = dataclasses.field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise ProviderRealmFactError("realm receipt must be issued by the provider-realm owner")


def issue_provider_realm_enrollment_receipt(
    *,
    binding_id: str,
    bindings_document=None,
    profiles_document=None,
    generation: int,
    enrollment_state: str,
) -> ProviderRealmEnrollmentReceipt:
    from control_plane.subscription_canary_admission import compose_catalog_digest
    from control_plane.subscription_harness_bindings import get_binding

    if enrollment_state not in _VALID_ENROLLMENT_STATES:
        raise ProviderRealmFactError("realm enrollment state is invalid")
    if type(generation) is not int or generation < 1:
        raise ProviderRealmFactError("realm generation is invalid")
    binding = get_binding(
        binding_id,
        document=bindings_document,
        profiles_document=profiles_document,
    )
    digest = compose_catalog_digest(
        bindings_document=bindings_document,
        profiles_document=profiles_document,
    )
    receipt_id = f"provider-realm:{binding.binding_id}:{generation}"
    receipt_digest = compose_realm_receipt_digest(
        receipt_id=receipt_id,
        binding_id=binding.binding_id,
        profile_id=binding.profile_id,
        adapter_id=binding.adapter_id,
        generation=generation,
        catalog_digest=digest,
    )
    return ProviderRealmEnrollmentReceipt(
        receipt_id=receipt_id,
        receipt_digest=receipt_digest,
        binding_id=binding.binding_id,
        profile_id=binding.profile_id,
        adapter_id=binding.adapter_id,
        generation=generation,
        enrollment_state=enrollment_state,
        _seal=_SEAL,
    )


def compose_realm_receipt_digest(
    *,
    receipt_id: str,
    binding_id: str,
    profile_id: str,
    adapter_id: str,
    generation: int,
    catalog_digest: str,
) -> str:
    import hashlib
    import json

    value = json.dumps(
        {
            "adapter_id": adapter_id,
            "binding_id": binding_id,
            "catalog_digest": catalog_digest,
            "generation": generation,
            "profile_id": profile_id,
            "receipt_id": receipt_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "ProviderRealmEnrollmentReceipt",
    "ProviderRealmFactError",
    "issue_provider_realm_enrollment_receipt",
]
