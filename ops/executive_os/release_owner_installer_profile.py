"""Pure fixed installer-profile producer for Executive release staging.

This module chooses no target, principal, credential, release SHA, or effect.
It only closes the static Product-owned profile fields around the two actions
and two source modes already accepted by the release contract.
"""
from __future__ import annotations

import hashlib

from control_plane import executive_release_contract as contract


_SCHEMA = "mastermind.executive_release_installer_profile/v1"
_PROFILE_ID = "mastermind-executive-darwin-arm64"
_PROFILE_VERSION = 1
_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
_PLATFORM = "darwin"
_ARCHITECTURE = "arm64"
_ACTIONS = frozenset(
    {"executive.release.rollback", "executive.release.upgrade"}
)
_SOURCE_MODES = frozenset(
    {"exact_protected_master", "frozen_accepted_ancestor"}
)



class InstallerProfileError(ValueError):
    """Closed profile compiler refusal."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _profile(*, action: str, source_policy_mode: str) -> dict[str, object]:
    if type(action) is not str or action not in _ACTIONS:
        raise InstallerProfileError("INSTALLER_PROFILE_ACTION")
    if (
        type(source_policy_mode) is not str
        or source_policy_mode not in _SOURCE_MODES
    ):
        raise InstallerProfileError("INSTALLER_PROFILE_SOURCE_MODE")
    return {
        "schema": _SCHEMA,
        "profile_id": _PROFILE_ID,
        "profile_version": _PROFILE_VERSION,
        "repository": _REPOSITORY,
        "platform": _PLATFORM,
        "architecture": _ARCHITECTURE,
        "source_policy_mode": source_policy_mode,
        "action": action,
    }


def compile_installer_profile(
    *, action: str, source_policy_mode: str
) -> bytes:
    """Return canonical profile bytes plus one LF; perform no ambient IO."""

    document = _profile(
        action=action,
        source_policy_mode=source_policy_mode,
    )
    return contract.canonical_release_bytes(document) + b"\n"


def installer_profile_digest(
    *, action: str, source_policy_mode: str
) -> str:
    """Return the exact digest consumed by release policy/factory joins."""

    document = _profile(
        action=action,
        source_policy_mode=source_policy_mode,
    )
    return hashlib.sha256(contract.canonical_release_bytes(document)).hexdigest()


__all__ = [
    "InstallerProfileError",
    "compile_installer_profile",
    "installer_profile_digest",
]
