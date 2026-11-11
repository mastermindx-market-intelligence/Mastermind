"""GBL-3 admission — the edge's closed door, in the fixed lane order.

Order (BUILD_PLAN row GBL-3): **principal → targets → kinds → rates →
per-thread allowlist**, as pure typed functions over an immutable table.
The table SHIPS EMPTY: v1 refuses every caller until the principal's act
adds a row (ADDENDUM §4b — environment rows and thread allowlist rows are
the principal's acts; v1 ships none).  Nothing here performs I/O, holds a
count, or creates a second registry: the bridge owns the durable rate
count; this module only enforces the row's ceiling at the door.

The row's identity input is the VERIFIED principal's ``subject_digest``
(sha256 over issuer+subject, minted by business_mcp_auth) — never a
caller-supplied label.  The row maps it to the bridge-side ``principal``
label the edge uses on every bridge call.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Mapping

from common.gbl_contract import (
    ALLOWLIST_ROW_KEYS,
    ASK_KINDS,
    MAX_ASKS_PER_HOUR_PER_PRINCIPAL,
    admit_ask_rate,
    check_thread_allowlist,
)

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class GblAdmissionError(ValueError):
    """Closed typed admission refusal; ``code`` names the gate."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclasses.dataclass(frozen=True)
class PrincipalAdmission:
    """One admitted OAuth principal: what it may ask of the bridge."""

    subject_digest: str                       # the verified principal's digest
    principal: str                            # bridge-side label
    targets: frozenset[str]                   # teammate targets it may name
    kinds: frozenset[str]                     # ⊆ the contract's v1 ask kinds
    max_asks_per_hour: int                    # row ceiling ≤ contract max
    message_allowlist: tuple[dict[str, str], ...] = ()   # (env, thread) rows

    def __post_init__(self) -> None:
        if (not isinstance(self.subject_digest, str)
                or _DIGEST_RE.fullmatch(self.subject_digest) is None):
            raise ValueError("subject_digest must be a sha256 hex digest")
        if not isinstance(self.principal, str) or not self.principal:
            raise ValueError("admission requires a bridge principal label")
        for name, value in (("targets", self.targets), ("kinds", self.kinds)):
            if not isinstance(value, frozenset) or not value:
                raise ValueError(f"admission {name} must be a non-empty frozenset")
        if not self.kinds <= ASK_KINDS:
            raise ValueError("admission kinds must be a subset of the v1 kinds")
        if any(not isinstance(item, str) or not item for item in self.targets):
            raise ValueError("admission targets must be non-empty strings")
        if (type(self.max_asks_per_hour) is not int
                or not 1 <= self.max_asks_per_hour <= MAX_ASKS_PER_HOUR_PER_PRINCIPAL):
            raise ValueError("admission ceiling exceeds the contract maximum")
        rows = tuple(self.message_allowlist)
        for row in rows:
            if (not isinstance(row, Mapping) or set(row) != set(ALLOWLIST_ROW_KEYS)
                    or any(not isinstance(row[key], str) or not row[key]
                           for key in ALLOWLIST_ROW_KEYS)):
                raise ValueError("message_allowlist rows must be exact "
                                 "{environment_id, thread_ref} strings")
        object.__setattr__(self, "message_allowlist",
                           tuple(dict(row) for row in rows))


DEFAULT_ADMISSION_TABLE: tuple[PrincipalAdmission, ...] = ()   # v1 ships EMPTY


def admit_principal(table, subject_digest: str) -> PrincipalAdmission:
    """First gate: the table is non-empty and holds this principal."""
    rows = tuple(table)
    if not rows:
        raise GblAdmissionError("ADMISSION_EMPTY", "the admission table is empty")
    if not isinstance(subject_digest, str):
        raise GblAdmissionError("PRINCIPAL_NOT_ADMITTED", "no verified subject")
    for row in rows:
        if row.subject_digest == subject_digest:
            return row
    raise GblAdmissionError("PRINCIPAL_NOT_ADMITTED", subject_digest[:12])


def admit_target(row: PrincipalAdmission, target: str) -> None:
    if target not in row.targets:
        raise GblAdmissionError("TARGET_NOT_ALLOWED", str(target))


def admit_kind(row: PrincipalAdmission, kind: str) -> None:
    if kind not in row.kinds:
        raise GblAdmissionError("KIND_NOT_ALLOWED", str(kind))


def admit_rate(row: PrincipalAdmission, asks_in_last_hour: int) -> None:
    """The rates gate: the contract-global ceiling, then the row ceiling.

    The count is the bridge's (it owns the store); the edge passes what it
    can prove and the bridge re-enforces the same law authoritatively."""
    try:
        admit_ask_rate(asks_in_last_hour)     # the contract-global maximum
    except Exception as err:
        raise GblAdmissionError("RATE_LIMITED", "contract ceiling") from err
    if type(asks_in_last_hour) is not int or asks_in_last_hour < 0:
        raise GblAdmissionError("RATE_LIMITED", "count unavailable")
    if asks_in_last_hour + 1 > row.max_asks_per_hour:
        raise GblAdmissionError("RATE_LIMITED",
                                f"ceiling {row.max_asks_per_hour}/hour")


def admit_message_thread(row: PrincipalAdmission, environment_id: str,
                         thread_ref: str) -> dict:
    """Last gate: the per-thread allowlist, via the GBL-1 contract law."""
    try:
        return check_thread_allowlist(row.message_allowlist, environment_id,
                                      thread_ref)
    except Exception as err:
        code = getattr(err, "code", "THREAD_NOT_ALLOWED")
        raise GblAdmissionError(code, getattr(err, "detail", "")) from err


def admit_ask(table, *, subject_digest: str, target: str, kind: str,
              asks_in_last_hour: int) -> PrincipalAdmission:
    """The ask gates in the fixed lane order: principal → target → kind →
    rate.  Returns the admitted row (its ``principal`` labels the bridge
    call; the caller never supplies identity)."""
    row = admit_principal(table, subject_digest)
    admit_target(row, target)
    admit_kind(row, kind)
    admit_rate(row, asks_in_last_hour)
    return row


__all__ = [
    "DEFAULT_ADMISSION_TABLE",
    "GblAdmissionError",
    "PrincipalAdmission",
    "admit_ask",
    "admit_kind",
    "admit_message_thread",
    "admit_principal",
    "admit_rate",
    "admit_target",
]
