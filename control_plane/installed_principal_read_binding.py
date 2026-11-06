"""Private installed OAuth-pair constructor evidence, never a bearer grant."""
from dataclasses import dataclass
from types import FunctionType
from inspect import getattr_static
import hashlib
from control_plane.principal_projection import NeutralPrincipalProjection

READ_SCOPE = "mastermind.executive.read"
SUBMIT_SCOPE = "mastermind.executive.intent.submit"
_IDENTITY = ("policy_id", "issuer_digest", "resource", "subject_digest", "client_ref")
_KEY = object()


@dataclass(frozen=True, slots=True)
class _InstalledReadPair:
    key: object
    owner: object
    read: object
    submit: object
    validator: object
    code: object

    def pair(self, owner):
        if (type(self) is not _InstalledReadPair or self.key is not _KEY
                or owner is not self.owner or owner.read is not self.read or owner.submit is not self.submit
                or type(self.validator) is not FunctionType or self.validator.__code__ is not self.code):
            raise TypeError("trusted read and submit policy pair required")
        return self.validator(owner)


def _issue_installed_read_pair(owner, *, validator):
    # Issuance records only constructor identity. The incumbent policy parser
    # still validates on demand, exactly when an owner selects this READ pair.
    if type(validator) is not FunctionType:
        raise TypeError("trusted read and submit policy pair required")
    return _InstalledReadPair(_KEY, owner, owner.read, owner.submit, validator, validator.__code__)


def trusted_read_pair(owner):
    if owner is None:
        return None
    binding = getattr_static(owner, "_installed_read_pair", None)
    if type(binding) is not _InstalledReadPair:
        raise TypeError("trusted read and submit policy pair required")
    return binding.pair(owner)


def read_matches_original(original: dict, current: dict,
                           principal: NeutralPrincipalProjection, *, trusted_pair) -> bool:
    """Preserve SEND provenance; admit only its explicitly paired READ policy.

    The original immutable request identifies its admitted submit policy; an
    independent READ grant may be exercised only when the *current trusted host*
    explicitly configures that same submit policy and its exact read counterpart.
    No caller-supplied policy, scope, or identity can manufacture this pairing.
    """
    if original == current:
        return True
    if trusted_pair is None or type(principal) is not NeutralPrincipalProjection:
        return False
    read, submit = trusted_pair
    return (
        tuple(principal.scopes) == (READ_SCOPE,)
        and isinstance(original, dict) and set(original) == set(_IDENTITY)
        and original.get("policy_id") == submit.policy_id
        and current.get("policy_id") == read.policy_id
        and original.get("resource") == read.resource
        and original.get("issuer_digest") == hashlib.sha256(read.issuer.encode("utf-8")).hexdigest()
        and original.get("subject_digest") in read.allowed_subject_digests
        and all(original.get(key) == current.get(key)
                for key in _IDENTITY if key != "policy_id")
    )
