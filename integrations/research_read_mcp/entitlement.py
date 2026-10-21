"""Closed loader for the Research Read deployment grant.

The grant binds content classes for a subject. It is not an identity, token,
or session store, and it never sees a tool argument.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from typing import Final

from control_plane.principal_projection import NeutralPrincipalProjection


GRANT_SCHEMA: Final[str] = "mastermind.research_read_mcp.grant.v1"
CONTENT_CLASSES: Final[tuple[str, ...]] = (
    "catalog_metadata",
    "report_text",
    "evidence_passage",
    "rio_derived",
)
REQUIRED_CONTENT_CLASS: Final[str] = "catalog_metadata"
MIN_QUOTE_LIMIT_CHARS: Final[int] = 1
MAX_QUOTE_LIMIT_CHARS: Final[int] = 12000
MAX_GRANT_BYTES: Final[int] = 65536
MAX_GRANT_ENTRIES: Final[int] = 256
NOT_ENTITLED: Final[None] = None

# Copied from integrations/business_mcp_auth/contracts.py:43 (_POLICY_ID_RE),
# the pattern _policy_id applies at line 196. Not imported.
_POLICY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REFUSAL: Final[str] = "research grant refused"
_GRANT_KEYS = frozenset({"schema", "grant_id", "policy_id", "entries"})
_ENTRY_KEYS = frozenset({
    "subject_digest",
    "content_classes",
    "quote_limit_chars",
    "expires_at",
})
_CONTENT_CLASS_SET = frozenset(CONTENT_CLASSES)


class GrantRefused(Exception):
    """Single loader refusal. Fixed message; never echoes input bytes, paths or values."""

    def __init__(self) -> None:
        super().__init__(_REFUSAL)


@dataclass(frozen=True, slots=True)
class ResearchGrantEntry:
    subject_digest: str
    content_classes: frozenset[str]
    quote_limit_chars: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class ResearchGrant:
    schema: str
    grant_id: str
    policy_id: str
    entries: tuple[ResearchGrantEntry, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class ResearchEntitlement:
    subject_digest: str
    grant_id: str
    policy_id: str
    content_classes: frozenset[str]
    quote_limit_chars: int
    expires_at: int


def _refuse() -> None:
    raise GrantRefused()


def _closed_object(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _refuse()
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    _refuse()


def _parse_entry(value: object, *, now: int, seen: set[str]) -> ResearchGrantEntry:
    if type(value) is not dict or set(value) != _ENTRY_KEYS:
        _refuse()
    digest = value["subject_digest"]
    if type(digest) is not str or _DIGEST_RE.fullmatch(digest) is None:
        _refuse()
    if digest in seen:
        _refuse()
    seen.add(digest)
    classes = value["content_classes"]
    if type(classes) is not list or not classes:
        _refuse()
    selected: list[str] = []
    for item in classes:
        if type(item) is not str or item not in _CONTENT_CLASS_SET or item in selected:
            _refuse()
        selected.append(item)
    if REQUIRED_CONTENT_CLASS not in selected:
        _refuse()
    quote = value["quote_limit_chars"]
    if type(quote) is not int or quote < MIN_QUOTE_LIMIT_CHARS or quote > MAX_QUOTE_LIMIT_CHARS:
        _refuse()
    expires_at = value["expires_at"]
    if type(expires_at) is not int or expires_at <= now:
        _refuse()
    return ResearchGrantEntry(
        subject_digest=digest,
        content_classes=frozenset(selected),
        quote_limit_chars=quote,
        expires_at=expires_at,
    )


def _parse_research_grant(raw: bytes, *, expected_policy_id: str, now: int) -> ResearchGrant:
    if type(now) is not int:
        _refuse()
    if type(raw) is not bytes:
        _refuse()
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        _refuse()
    try:
        loaded = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except GrantRefused:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError):
        _refuse()
    if type(loaded) is not dict or set(loaded) != _GRANT_KEYS:
        _refuse()
    if loaded.get("schema") != GRANT_SCHEMA:
        _refuse()
    grant_id = loaded.get("grant_id")
    policy_id = loaded.get("policy_id")
    if type(grant_id) is not str or _POLICY_ID_RE.fullmatch(grant_id) is None:
        _refuse()
    if type(policy_id) is not str or _POLICY_ID_RE.fullmatch(policy_id) is None:
        _refuse()
    if type(expected_policy_id) is not str or policy_id != expected_policy_id:
        _refuse()
    entries_raw = loaded.get("entries")
    if type(entries_raw) is not list or not entries_raw or len(entries_raw) > MAX_GRANT_ENTRIES:
        _refuse()
    seen: set[str] = set()
    entries: list[ResearchGrantEntry] = []
    for item in entries_raw:
        entries.append(_parse_entry(item, now=now, seen=seen))
    return ResearchGrant(
        schema=GRANT_SCHEMA,
        grant_id=grant_id,
        policy_id=policy_id,
        entries=tuple(entries),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def parse_research_grant(raw: bytes, *, expected_policy_id: str, now: int) -> ResearchGrant:
    try:
        return _parse_research_grant(raw, expected_policy_id=expected_policy_id, now=now)
    except GrantRefused:
        raise
    except Exception:
        raise GrantRefused() from None


def _read_grant_bytes(path: str, *, expected_owner_uid: int) -> bytes:
    """Secure read copied from integrations/workbench_read_mcp/service.py:270.

    Owner is ``expected_owner_uid`` (deployment default 0), not the process euid.
    """

    if type(path) is not str or not path.startswith("/") or "\x00" in path:
        _refuse()
    if type(expected_owner_uid) is not int:
        _refuse()
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nonblocking = getattr(os, "O_NONBLOCK", 0)
    if not nofollow or not cloexec or not nonblocking:
        _refuse()
    try:
        before = os.lstat(path)
    except OSError:
        _refuse()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != expected_owner_uid
        or stat.S_IMODE(before.st_mode) & 0o022
        or before.st_size > MAX_GRANT_BYTES
    ):
        _refuse()
    descriptor = -1
    close_failed = False
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | cloexec | nonblocking)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != expected_owner_uid
            or stat.S_IMODE(opened.st_mode) & 0o022
            or opened.st_size != before.st_size
            or os.get_inheritable(descriptor)
        ):
            _refuse()
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining > 0:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                _refuse()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _refuse()
        raw = b"".join(chunks)
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                close_failed = True
    if close_failed:
        _refuse()
    try:
        after = os.lstat(path)
    except OSError:
        _refuse()
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_uid != before.st_uid
        or after.st_mode != before.st_mode
        or after.st_nlink != before.st_nlink
        or after.st_size != before.st_size
    ):
        _refuse()
    if len(raw) != before.st_size:
        _refuse()
    return raw


def load_research_grant(
    path: str,
    *,
    expected_policy_id: str,
    now: int,
    expected_owner_uid: int = 0,
    expected_sha256: str | None = None,
) -> ResearchGrant:
    try:
        raw = _read_grant_bytes(path, expected_owner_uid=expected_owner_uid)
        digest = hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and (
            type(expected_sha256) is not str or expected_sha256 != digest
        ):
            _refuse()
        return parse_research_grant(raw, expected_policy_id=expected_policy_id, now=now)
    except GrantRefused:
        raise
    except Exception:
        raise GrantRefused() from None


def _select_entitlement(
    projection: object,
    grants: object,
    now: object,
) -> ResearchEntitlement | None:
    if type(projection) is not NeutralPrincipalProjection:
        return NOT_ENTITLED
    if type(grants) is not ResearchGrant:
        return NOT_ENTITLED
    if type(now) is not int:
        return NOT_ENTITLED
    if projection.policy_id != grants.policy_id:
        return NOT_ENTITLED
    token_expires_at = projection.expires_at
    if type(token_expires_at) is not int or not token_expires_at > now:
        return NOT_ENTITLED
    digest = projection.subject_digest
    if type(digest) is not str or _DIGEST_RE.fullmatch(digest) is None:
        return NOT_ENTITLED
    matched: ResearchGrantEntry | None = None
    for entry in grants.entries:
        if entry.subject_digest == digest:
            if matched is not None:
                return NOT_ENTITLED
            matched = entry
    if matched is None:
        return NOT_ENTITLED
    if not matched.expires_at > now:
        return NOT_ENTITLED
    return ResearchEntitlement(
        subject_digest=digest,
        grant_id=grants.grant_id,
        policy_id=grants.policy_id,
        content_classes=matched.content_classes,
        quote_limit_chars=matched.quote_limit_chars,
        expires_at=min(matched.expires_at, token_expires_at),
    )


def entitlement_for(
    projection: object,
    grants: object,
    *,
    now: object,
) -> ResearchEntitlement | None:
    try:
        return _select_entitlement(projection, grants, now)
    except Exception:
        return None


__all__ = [
    "CONTENT_CLASSES",
    "GRANT_SCHEMA",
    "MAX_GRANT_BYTES",
    "MAX_GRANT_ENTRIES",
    "MAX_QUOTE_LIMIT_CHARS",
    "MIN_QUOTE_LIMIT_CHARS",
    "NOT_ENTITLED",
    "REQUIRED_CONTENT_CLASS",
    "GrantRefused",
    "ResearchEntitlement",
    "ResearchGrant",
    "ResearchGrantEntry",
    "entitlement_for",
    "load_research_grant",
    "parse_research_grant",
]
