"""Typed, immutable provider-realm receipts. Minting is owned by the realm owner."""

from __future__ import annotations

import dataclasses
import hashlib
import json

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
    catalog_digest: str = ""
    _seal: object = dataclasses.field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.enrollment_state not in _VALID_ENROLLMENT_STATES:
            raise ProviderRealmFactError("enrollment_state is invalid")
        if type(self.generation) is not int or self.generation < 1:
            raise ProviderRealmFactError("realm generation is invalid")
        from control_plane.codex_provider_realm import (
            verify_provider_realm_enrollment_receipt,
        )

        verify_provider_realm_enrollment_receipt(self)


def issue_provider_realm_enrollment_receipt(**_kwargs):
    raise ProviderRealmFactError(
        "realm_receipt must be issued by the provider-realm owner "
        "(control_plane.codex_provider_realm.issue_provider_realm_enrollment_receipt)"
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
    """Public SHA-256 over caller inputs. Not an owner seal and not accepted as one."""

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
    "compose_realm_receipt_digest",
    "issue_provider_realm_enrollment_receipt",
]
