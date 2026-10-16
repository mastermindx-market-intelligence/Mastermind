"""Pure activation plan for the existing Executive release-owner registration.

This module cannot publish or enable anything on a host. It accepts only the
canonical disabled registration already consumed by the protected factory and
returns immutable expected-preimage/postimage bytes where exactly enabled
changes from false to true.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from control_plane import executive_release_factory as factory
from ops.executive_os.release_owner_resident_inputs import canonical_file_bytes


class RegistrationActivationError(ValueError):
    """Closed activation-plan refusal."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class RegistrationActivationPlan:
    """Detached bytes only; not publication authority or evidence of effect."""

    before_bytes: bytes
    after_bytes: bytes
    before_sha256: str
    after_sha256: str


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def compile_registration_activation(
    registration_bytes: bytes,
) -> RegistrationActivationPlan:
    """Compile one disabled-to-enabled postimage without ambient effects."""

    try:
        before = factory.registration(factory.file_document(registration_bytes))
    except (factory.FactoryInputError, TypeError, ValueError):
        raise RegistrationActivationError(
            "ACTIVATION_REGISTRATION_INVALID"
        ) from None

    if before["enabled"] is not False:
        raise RegistrationActivationError(
            "ACTIVATION_PREIMAGE_NOT_DISABLED"
        )

    after = dict(before)
    after["enabled"] = True
    try:
        validated_after = factory.registration(after)
        before_bytes = canonical_file_bytes(before)
        after_bytes = canonical_file_bytes(validated_after)
    except (factory.FactoryInputError, TypeError, ValueError):
        raise RegistrationActivationError(
            "ACTIVATION_REGISTRATION_INVALID"
        ) from None

    if before_bytes != registration_bytes:
        raise RegistrationActivationError(
            "ACTIVATION_REGISTRATION_NONCANONICAL"
        )

    # The protected parser owns field/type validity. This fence makes the
    # activation semantic explicit: no identity or generation may rotate.
    for name, value in before.items():
        if name == "enabled":
            continue
        if type(validated_after[name]) is not type(value):
            raise RegistrationActivationError("ACTIVATION_IDENTITY_CHANGED")
        if validated_after[name] != value:
            raise RegistrationActivationError("ACTIVATION_IDENTITY_CHANGED")
    if validated_after["enabled"] is not True:
        raise RegistrationActivationError("ACTIVATION_POSTIMAGE_NOT_ENABLED")

    return RegistrationActivationPlan(
        before_bytes=bytes(before_bytes),
        after_bytes=bytes(after_bytes),
        before_sha256=_digest(before_bytes),
        after_sha256=_digest(after_bytes),
    )


__all__ = [
    "RegistrationActivationError",
    "RegistrationActivationPlan",
    "compile_registration_activation",
]
