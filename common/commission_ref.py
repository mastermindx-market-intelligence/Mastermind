"""Transport-neutral immutable commission-reference contract.

This module is the canonical owner of the exact source-byte identity shared by
Executive Runtime and Agent Dialogue.  It intentionally depends on the Python
standard library only and performs no transport, repository, or filesystem I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


COMMISSION_REF_FIELDS = frozenset(
    {"repository", "commit", "path", "content_sha256"}
)

_REPOSITORY_RE = re.compile(
    r"\A[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,100}\Z"
)
_PATH_RE = re.compile(r"\A[A-Za-z0-9_.\-/]{1,300}\Z")
_SHA40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA64_RE = re.compile(r"\A[0-9a-f]{64}\Z")


class CommissionRefError(ValueError):
    """Neutral refusal for a malformed or noncanonical commission reference."""


def _refuse() -> None:
    raise CommissionRefError("commission_ref is invalid")


@dataclass(frozen=True, slots=True)
class CommissionRef:
    """Deeply immutable identity of the exact bytes that grant a commission."""

    repository: str
    commit: str
    path: str
    content_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.repository, str)
            or _REPOSITORY_RE.fullmatch(self.repository) is None
            or not isinstance(self.commit, str)
            or _SHA40_RE.fullmatch(self.commit) is None
            or not isinstance(self.content_sha256, str)
            or _SHA64_RE.fullmatch(self.content_sha256) is None
            or not isinstance(self.path, str)
            or _PATH_RE.fullmatch(self.path) is None
            or self.path.startswith("/")
            or "//" in self.path
            or any(part in {"", ".", ".."} for part in self.path.split("/"))
        ):
            _refuse()

    def to_dict(self) -> dict[str, str]:
        """Return a fresh canonical wire/storage representation."""

        return {
            "repository": self.repository,
            "commit": self.commit,
            "path": self.path,
            "content_sha256": self.content_sha256,
        }


def normalize_commission_ref(value: Any) -> CommissionRef:
    """Validate an exact commission mapping and return immutable canonical form."""

    # Exact type identity is part of the trust boundary.  A subclass can
    # override ``to_dict`` (or expose dynamic attributes) and thereby make an
    # apparently frozen source emit different authority bytes after admission.
    if type(value) is CommissionRef:
        return value
    if not isinstance(value, dict) or set(value) != COMMISSION_REF_FIELDS:
        _refuse()
    return CommissionRef(
        repository=value["repository"],
        commit=value["commit"],
        path=value["path"],
        content_sha256=value["content_sha256"],
    )


# ``validate_commission_ref`` is the neutral validator name.  The integration
# layer retains its own dict-returning function of the same name and translates
# only ``CommissionRefError`` into its closed transport error vocabulary.
validate_commission_ref = normalize_commission_ref


__all__ = [
    "COMMISSION_REF_FIELDS",
    "CommissionRef",
    "CommissionRefError",
    "normalize_commission_ref",
    "validate_commission_ref",
]
