"""GBL-4 Paperclip client — the ``GblAskStore`` protocol over issues+comments.

Lane GBL-4 of ``integrations/mmos/gbl/BUILD_PLAN.md``.  This module is ONLY
the persistence mapping documented in ``integrations/mmos/gbl/GBL2_NOTES.md``
("The Paperclip client interface"): one Paperclip issue per ask, opened and
assigned to the "Grok Bridge" bridge service agent; ask events as issue
comments; ``count_asks`` as a scan of that principal's issue rows.  ALL ask
law — admission, mints, duplicate classification, state chain, expiry,
budgets — stays in GBL-1/GBL-2; nothing is restated here.

Boundary law (ADDENDUM §1/§3, BUILD_PLAN GBL-4; repair round 1, panel B):

* the base URL is REQUIRED, ``http`` and LOOPBACK ONLY, with an explicit
  port in range 1..65535; port 3100 (the Chairman's default instance), 3179
  (the known fleet listener) and every implicit default are refused at
  construction — and the loopback law is RE-CHECKED on every request, with
  an opener that never follows a redirect (a 3xx is a typed error, so no
  hop-2 can ever leave the validated base) and never uses a proxy;
* no credential is accepted or sent: the dev instance's local-trusted header
  is the only authorization surface, custom headers MERGE with it, and any
  credential-shaped header name (by word, not by five exact names) is
  refused so no secret can ride a request;
* EFFECT_UNKNOWN (GBL2_NOTES, ARCHITECTURE §6): a create whose outcome is
  lost or ambiguous — transport timeout, unreachable, truncated reply,
  5xx, redirect, or the ambiguous 4xx set (408/409/425/429/499) — raises
  ``GblCreateEffectUnknown`` and is NEVER retried as a second create; the
  caller (the bridge) reconciles by ONE read-back of the deterministic ask
  id.  A definite 4xx refusal is a typed client error, not an unknown
  effect;
* issue ids and comment ids coming FROM the server are untrusted path
  input: they must match a strict charset ([A-Za-z0-9_-]{1,128}) and are
  percent-quoted into every path segment, so no server string can rewrite
  a route; company/agent ids are held to the same charset at construction;
* resolution is by the EXACT stored ask id (the parsed description
  envelope), never by a title substring, and only an exact match is ever
  cached;
* listing is paginated to exhaustion and FAILS CLOSED on any doubt: an
  unknown envelope shape, a server that ignores pagination, a corrupt
  marker-bearing description, or a listing past the page cap is a typed
  error — never a short read that could under-count or hide an ask;
* issue and comment text is UNTRUSTED DATA: read back strictly (marker +
  balanced JSON, ``validate_ask``-checked), never executed, never
  interpreted as instructions.  Parsed events carry their comment's
  provenance (``comment_author``, ``comment_id``, ``comment_created_at``,
  ``comment_order``) — DISPLAY AND ORDERING METADATA ONLY, never a trust
  basis (GBL_REPAIR1_NOTES §2: the plain comments route cannot produce
  agent-attributed rows).  Trust is the host-held HMAC v1 tag: the store
  stamps every appended event with a per-record strictly increasing
  ``seq`` and a tag binding (ask_id, seq, event); on read, an event whose
  tag is absent, malformed, cross-ask or failing verification surfaces
  ``trusted: False`` and the bridge ignores it.  ``create_ask`` is
  CREATE-IF-ABSENT (§1.1): None when created, the existing record when
  the deterministic id is present — never a second issue.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import hmac
import http.client
import json
import os
import pwd
import re
import secrets
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from common.gbl_contract import (
    ASK_ID_RE,
    GBLContractError,
    validate_ask,
)
from integrations.gbl.bridge_service import GblCreateEffectUnknown

__all__ = [
    "GblPaperclipError",
    "GblPaperclipClientError",
    "GblPaperclipServerError",
    "GblPaperclipRedirectError",
    "GblPaperclipTransportError",
    "PRODUCTION_BOARD_FIELD",
    "PRODUCTION_BOARD_PORT",
    "PRODUCTION_BOARD_SPEC_RELPATH",
    "PaperclipAskClient",
    "create_service_agent",
    "validate_paperclip_base_url",
]

# Never targeted, even if free: the Chairman's default Paperclip instance
# (3100) and the other known Paperclip listener on this host (3179) — the
# reserved-port law of tools/mmos_dev/paperclip_dev.sh, restated for this
# client because it must hold at every call site, not only in the controller.
RESERVED_PORTS = frozenset({3100, 3179})

# P0-2 option (a) — principal ruling 2026-11-12 14:13Z, narrow shape: the
# REAL production board is 127.0.0.1:3100, and exactly that port may be
# admitted by an explicit opt-in that only PaperclipAskClient.from_spec can
# make, and only for the ONE canonical production spec file below.  3179 is
# never admitted by anything, opt-in or not.  The opt-in never widens any
# other rule of the base-URL law and never falls back silently: the field in
# a spec at any other path, with any other mode or owner, or with any
# non-true value, is the typed refusal PRODUCTION_BOARD_NOT_ALLOWED_HERE.
PRODUCTION_BOARD_PORT = 3100
PRODUCTION_BOARD_FIELD = "production_board"
PRODUCTION_BOARD_SPEC_RELPATH = (".mastermind", "gbl", "spec.json")

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# A credential-shaped header name is refused BY WORD, not by a fixed list of
# five exact names (panel B L7): anything that smells like a secret riding
# cleartext http is rejected at construction.
_BANNED_HEADER_WORDS = ("token", "secret", "password", "auth", "cookie",
                        "credential", "api-key", "apikey", "bearer")

# Every path segment is a single strict token: no dots (so no ".."), no
# slashes, no percent tricks — then percent-encoded anyway (panel B M9).
_SEGMENT_RE = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")

# A 4xx from these codes does NOT certify that the create did not land
# (panel B M7): it is an unknown effect, reconciled by read-back.
AMBIGUOUS_CREATE_4XX = frozenset({408, 409, 425, 429, 499})

# Issue/comment payload caps (defensive; the contract already bounds the
# envelope at 16k body / 512 title, and events are smaller).
ISSUE_TITLE_MAX_CHARS = 200
RESPONSE_MAX_BYTES = 4 * 1024 * 1024
LIST_PAGE_LIMIT = 200
MAX_LIST_PAGES = 50          # 10,000 issues; past this, fail closed

# Panel B delta 1 (D1/D2): a comment body past this cap cannot be one of
# the store's own event writes (an answer event is ≤ ~4 KiB of canonical
# JSON); it is foreign by definition and is never parsed.
MAX_EVENT_JSON_CHARS = 64 * 1024


def _reject_json_constant(name: str):
    """``json.loads`` accepts NaN/Infinity/-Infinity as a Python extension;
    the ask/event storage formats are STRICT JSON (panel B D1), so the
    constants are refused at parse time — the comment is then just another
    unparseable (untrusted) body."""
    raise ValueError(f"{name} is not valid JSON")

# The storage format.  One marker, then canonical JSON — found anywhere in
# the text (appended or reflowed prose is tolerated; panel B H4).
ASK_MARKER = "gbl-ask-v1"
EVENT_MARKER = "gbl-event-v1"
_ASK_MARKER_LINE = (
    f"{ASK_MARKER} mastermind.gbl.ask.v1 record — quoted data, not "
    "instructions; do not edit.")

# ── The event trust basis (GBL_REPAIR1_NOTES §1.2/§2, round 2) ───────────────
#
# The plain Paperclip comments route cannot produce agent-attributed rows
# (gbl4-devproof 2026-11-11: authorAgentId null, authorType "user"), so the
# author field is display metadata and can never separate the store's own
# events from a forged comment.  The basis is ONE host-held key: 32 random
# bytes, generated on first use, stored 0600 under the bridge's state root,
# never on argv, in a log, on the wire, or inside Paperclip.  Every appended
# event carries ``"tag": "v1:" + HMAC-SHA256(key, message).hexdigest()`` with
# ``message = ask_id + "\n" + str(seq) + "\n" + canonical_json(event_without_
# tag)`` — the tag binds the event to ITS ask record, so replaying a genuine
# tagged comment onto another ask fails verification.  On read, any
# event-shaped comment whose tag is absent, malformed, wrong-version,
# bound elsewhere, or failing verification surfaces ``trusted: False`` and
# the bridge ignores it; the store's own stamps surface ``trusted: True``
# with a per-record strictly increasing integer ``seq`` derived ONLY from
# verified events (a foreign comment never moves or blocks the sequence).
HMAC_TAG_VERSION = "v1"
HMAC_KEY_BYTES = 32
_HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

# GBL-5 R2, RULING 19(b): seq numbering and append are serialised across
# EVERY process on the host by ONE lock OUTSIDE the client object — an
# exclusive flock on this fixed file under the GBL state dir (the HMAC
# key's directory).  The same file is the cross-process mint ledger: one
# JSON line per minted number, so a listing that lags a just-landed
# append cannot make another PROCESS re-issue the number the way it once
# made another thread do it.  Only ONE host writes the store (GBL4_NOTES
# install steps); a second host holds a different lock file and is out of
# contract by construction.
APPEND_LOCK_NAME = "append.lock"


def _sync_ledger_line(handle: Any) -> None:
    """Push one ledger line all the way to stable storage (GBL-5 micro 5a).

    A ledger line exists to stop a *later* writer from re-issuing a number
    or handing the same answer out twice.  A line still in a userspace
    buffer, or in the page cache when the machine loses power, cannot do
    that: the process that produced it has returned and the next writer
    reads the file the kernel never wrote.  So every ledger write is
    followed by ``flush`` → ``os.fsync`` → ``fcntl.F_FULLFSYNC`` where the
    platform has it (macOS; APFS needs the full sync to reach the platter
    and not merely the drive cache).

    ``OSError`` is deliberately NOT caught here: both callers map it to the
    typed ``APPEND_LOCK_UNWRITABLE`` refusal they already own, so a sync
    that cannot be proven refuses the append instead of letting an
    unsynced line decide anything."""
    handle.flush()
    os.fsync(handle.fileno())
    full_sync = getattr(fcntl, "F_FULLFSYNC", None)
    if full_sync is not None:
        fcntl.fcntl(handle.fileno(), full_sync)

# GBL-5 micro 1, RULING 19(a): the keys only the STORE (or this reader) may
# set on a surfaced event.  A comment body can carry any JSON key at all, so
# every one of them is removed from the parsed body BEFORE verification and
# re-attached only by this reader: ``tag``/``trusted`` are the store's stamps,
# ``defect`` is the chain law's own demotion marking (a comment carrying
# ``"defect": "EVENT_SEQ_DUPLICATE"`` must never be counted as a real POST by
# the bridge's nudge-marker view), and the ``comment_*`` keys are provenance
# this client reads from the comment ROW, never from the body.  ``seq`` is
# deliberately NOT listed: it is part of the signed v1 content, and it is
# consulted only for a tag-verified event.
STORE_ONLY_EVENT_KEYS = frozenset({
    "tag", "trusted", "defect",
    "comment_id", "comment_author", "comment_created_at", "comment_order",
})


class GblPaperclipError(Exception):
    """Closed typed failure of the Paperclip mapping; `code` names it."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.status: int | None = None       # HTTP status, when there was one


class GblPaperclipClientError(GblPaperclipError):
    """A definite 4xx refusal by the Paperclip instance."""


class GblPaperclipServerError(GblPaperclipError):
    """A 5xx (or redirect) failure; the request's effect is not certified."""


class GblPaperclipRedirectError(GblPaperclipServerError):
    """A 3xx the client refused to follow (M6); the effect is not certified."""


class GblPaperclipTransportError(GblPaperclipError):
    """Timeout / unreachable / unparseable transport failure."""


def validate_paperclip_base_url(url: str, *,
                                production_board: bool = False) -> str:
    """The base-URL law: required, http, loopback host, explicit port in
    range 1..65535 and not reserved, no userinfo, no query/fragment.
    Returns the normalized URL.

    ``production_board=True`` (P0-2 option (a), principal ruling 2026-11-12)
    admits EXACTLY port 3100 — the real production board — at EXACTLY the
    literal host ``127.0.0.1`` (item 8(a): ``localhost``/``[::1]`` under the
    flag are the typed refusal PRODUCTION_BOARD_NOT_ALLOWED_HERE), and
    changes nothing else; 3179 stays reserved under every flag.  Only
    :meth:`PaperclipAskClient.from_spec` may pass True, and only after
    :func:`_require_canonical_production_spec` has proven the spec file is
    the canonical 0600 uid-owned regular file at
    ``<pwd-home>/.mastermind/gbl/spec.json``.  Every other caller keeps the
    default (False) and keeps refusing both reserved ports."""
    if not isinstance(production_board, bool):
        raise ValueError(
            f"production_board must be a bool, got {type(production_board)}")
    if not isinstance(url, str) or not url:
        raise ValueError("paperclip base url is required")
    if not url.isascii():
        # item 8(b) / LOW-4: fullwidth digits pass isdigit()/int()
        # consistently but the returned base kept the non-ASCII netloc and
        # died untyped (UnicodeEncodeError) at request time — refuse here,
        # typed, under every flag.
        raise GblPaperclipError(
            "BASE_URL_NOT_ASCII",
            "paperclip base url must be pure ASCII (fullwidth digits and "
            "internationalized hosts are refused, never normalized)")
    if "://" not in url:
        raise ValueError(f"not an absolute http url: {url!r}")
    scheme, rest = url.split("://", 1)
    if scheme != "http":
        raise ValueError(f"paperclip base url must be http, got {url!r}")
    if "@" in rest:
        raise ValueError(
            f"paperclip base url must carry no userinfo: {url!r}")
    host_port = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not host_port:
        raise ValueError(f"paperclip base url has no host: {url!r}")
    host, port = _split_host_port(host_port)
    if host.lower() not in _LOOPBACK_HOSTS:
        raise ValueError(
            f"paperclip base url must be loopback, got host {host!r}")
    if production_board and host.lower() != "127.0.0.1":
        # item 8(a) / LOW-3: the opt-in is for the literal production host.
        # ``localhost`` or ``[::1]`` may resolve anywhere the host's
        # resolver says; the flag never inherits their ambiguity.
        raise GblPaperclipError(
            "PRODUCTION_BOARD_NOT_ALLOWED_HERE",
            "the production-board opt-in admits only the literal host "
            f"127.0.0.1, got {host!r}")
    if port is None:
        raise ValueError(
            "paperclip base url must carry an explicit port "
            f"(no implicit default): {url!r}")
    if port in RESERVED_PORTS and not (production_board
                                       and port == PRODUCTION_BOARD_PORT):
        raise ValueError(
            f"paperclip base url port {port} is reserved and never targeted")
    if not 1 <= port <= 65535:
        raise ValueError(
            f"paperclip base url port {port} is out of range 1..65535")
    if "?" in url or "#" in url:
        raise ValueError("paperclip base url carries no query or fragment")
    return url.rstrip("/")


def _split_host_port(host_port: str) -> tuple[str, int | None]:
    if host_port.startswith("["):                      # [::1]:3191
        host, _, port = host_port[1:].partition("]")
        return host, (int(port[1:]) if port.startswith(":") else None)
    host, sep, port = host_port.partition(":")
    return host, (int(port) if sep and port.isdigit() else None)


def _current_uid() -> int:
    """The running uid.  Its own function so tests inject it; production
    code never overrides it."""
    return os.getuid()


def _current_home() -> str:
    """The home directory from the PASSWORD DATABASE for the current uid —
    deliberately NOT ``$HOME``/``os.path.expanduser``: an environment
    variable any caller can set must never steer the production-board gate.
    Its own function so tests inject a temp root; production code never
    overrides it."""
    return pwd.getpwuid(os.getuid()).pw_dir


def _require_canonical_production_spec(spec_path: Path) -> None:
    """The opt-in gate (P0-2 option (a), principal ruling 2026-11-12):
    ``paperclip.production_board: true`` is honored ONLY when the spec file
    IS the one canonical production spec —

    * a REGULAR file that is NOT a symlink;
    * owned by the current uid, mode exactly 0600;
    * whose realpath is exactly ``<home>/.mastermind/gbl/spec.json``, home
      from the password database (:func:`_current_home`), never ``$HOME``.

    Any deviation is the typed refusal ``PRODUCTION_BOARD_NOT_ALLOWED_HERE``.
    There is NO fallback: the flag never silently degrades to the default
    law (which would refuse 3100 with an unrelated error and mask a
    misplaced or tampered production spec)."""
    code = "PRODUCTION_BOARD_NOT_ALLOWED_HERE"
    try:
        info = os.lstat(spec_path)
    except OSError as exc:
        raise GblPaperclipError(
            code, f"cannot state {spec_path}: {type(exc).__name__}") from None
    if stat.S_ISLNK(info.st_mode):
        raise GblPaperclipError(
            code, f"{spec_path} is a symlink; the production spec must be a "
            "regular file at the canonical path")
    if not stat.S_ISREG(info.st_mode):
        raise GblPaperclipError(
            code, f"{spec_path} is not a regular file")
    if info.st_uid != _current_uid():
        raise GblPaperclipError(
            code, f"{spec_path} is not owned by the current uid")
    mode = stat.S_IMODE(info.st_mode)
    if mode != 0o600:
        raise GblPaperclipError(
            code, f"{spec_path} mode is {mode:03o}; the production spec must "
            "be exactly 0600")
    expected = os.path.join(_current_home(), *PRODUCTION_BOARD_SPEC_RELPATH)
    if os.path.realpath(spec_path) != os.path.realpath(expected):
        raise GblPaperclipError(
            code, f"paperclip.{PRODUCTION_BOARD_FIELD} is honored only at "
            f"{expected}; {spec_path} is another path")


def _refuse_stray_production_board_field(spec: Any, spec_path: Path) -> None:
    """Item 8(c) / LOW-2: the FIELD NAME ``production_board`` is honored at
    exactly one place — ``paperclip.production_board``.  The same name
    ANYWHERE else in the spec (top level, a nested block, inside a list
    item), with ANY value, is the typed refusal
    ``PRODUCTION_BOARD_NOT_ALLOWED_HERE``: a stray copy must never sit
    inert beside the honored gate.  This is the runtime mirror of the repo
    hygiene scan.  Fails closed on pathological nesting (RecursionError)."""
    def walk(node: Any, path: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == PRODUCTION_BOARD_FIELD and path != ("paperclip",):
                    where = ".".join(path + (str(key),)) or str(key)
                    raise GblPaperclipError(
                        "PRODUCTION_BOARD_NOT_ALLOWED_HERE",
                        f"spec {spec_path} carries the field name "
                        f"{PRODUCTION_BOARD_FIELD!r} at {where} — honored "
                        "only at paperclip.production_board, whatever the "
                        "stray copy's value")
                walk(value, path + (str(key),))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + (f"[{index}]",))
    try:
        walk(spec, ())
    except RecursionError:
        raise GblPaperclipError(
            "PRODUCTION_BOARD_NOT_ALLOWED_HERE",
            f"spec {spec_path} nests too deeply to scan for stray "
            f"{PRODUCTION_BOARD_FIELD!r} fields — refused, never skipped"
        ) from None


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _load_or_create_hmac_key(path: Path) -> bytes:
    """The host-held key (§2.1): read from ``path`` when present (a REGULAR
    file — never a symlink — of exactly 32 bytes, no group/other permission
    bits; fail closed on anything else), else generated on first use with
    0600 inside the EXISTING state directory (itself refused when group- or
    other-writable).  The key never appears in an error, a log, or an
    exception: only the path and the rule are named."""
    parent = path.parent
    try:
        parent_mode = stat.S_IMODE(parent.stat().st_mode)
    except OSError:
        raise GblPaperclipError(
            "HMAC_KEY_DIR_MISSING",
            f"state dir {parent} does not exist; the install step "
            "creates it — this client never mints directories") from None
    if parent_mode & 0o022:
        # A group-/other-writable state root allows unlink+replace of the
        # anchor (panel B D5); ordinary 0755 roots stay legal — only the
        # WRITE bits are refused.
        raise GblPaperclipError(
            "HMAC_KEY_DIR_MODE_INVALID",
            f"{parent} must not be group- or other-writable "
            f"(found {parent_mode:03o})")
    try:
        info = path.lstat()            # the anchor itself, never the target
    except FileNotFoundError:
        data = secrets.token_bytes(HMAC_KEY_BYTES)
        try:
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            # Lost a first-use race (or the path changed shape under us):
            # ONE bounded read of whatever is there now — never a recursive
            # retry loop (panel B D3).
            try:
                info = path.lstat()
            except OSError as exc:
                raise GblPaperclipError(
                    "HMAC_KEY_UNREADABLE",
                    f"cannot state {path}: {type(exc).__name__}") from None
        except OSError as exc:
            # F3: EACCES/EROFS/ELOOP … at the anchor are a typed local-law
            # error, never a raw escape into the record paths (the open
            # sits inside this handler, out of the outer catch's reach).
            raise GblPaperclipError(
                "HMAC_KEY_UNWRITABLE",
                f"cannot create {path}: {type(exc).__name__}") from None
        else:
            try:
                written = os.write(handle, data)
                if written != len(data):
                    # GBL-5 B3 (panel B old-code #3): os.write may write
                    # short; unchecked, the disk holds a truncated key
                    # while this process returns the full bytes — the next
                    # user fails closed on HMAC_KEY_INVALID with no cause.
                    raise GblPaperclipError(
                        "HMAC_KEY_UNWRITABLE",
                        f"short write to {path}: {written} of "
                        f"{len(data)} bytes")
            except OSError as exc:
                # F3 (ENOSPC family): typed, never a raw escape.  A
                # partial file, if one remains, fails closed on the next
                # use as HMAC_KEY_INVALID.
                raise GblPaperclipError(
                    "HMAC_KEY_UNWRITABLE",
                    f"cannot write {path}: {type(exc).__name__}") from None
            finally:
                try:
                    os.close(handle)
                except OSError:
                    # GBL-5 B4 (panel B old-code #4): the key is already
                    # fully written (a short write raises typed, above) —
                    # a failing close must not escape raw past every
                    # typed guard.
                    pass
            return data
    except OSError as exc:
        raise GblPaperclipError(
            "HMAC_KEY_UNREADABLE",
            f"cannot state {path}: {type(exc).__name__}") from None
    if stat.S_ISLNK(info.st_mode):
        # stat/read FOLLOW symlinks, so a link to a valid 0600 key would
        # otherwise be adopted verbatim (panel B D5): the anchor shape
        # itself is refused.
        raise GblPaperclipError(
            "HMAC_KEY_IS_SYMLINK",
            f"{path} must be a regular file, not a symlink")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise GblPaperclipError(
            "HMAC_KEY_MODE_INVALID",
            f"{path} must carry no group/other permission bits (0600)")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise GblPaperclipError(
            "HMAC_KEY_UNREADABLE",
            f"cannot read {path}: {type(exc).__name__}") from None
    if len(data) != HMAC_KEY_BYTES:
        raise GblPaperclipError(
            "HMAC_KEY_INVALID",
            f"{path} must hold exactly {HMAC_KEY_BYTES} bytes")
    return data


def _event_tag(key: bytes, ask_id: str, seq: int,
               event: Mapping[str, Any]) -> str:
    """The §2.2 v1 tag: HMAC-SHA256 over ``ask_id + "\\n" + str(seq) +
    "\\n" + canonical_json(event_without_tag)`` (sorted keys, compact
    separators, UTF-8)."""
    message = (ask_id + "\n" + str(seq) + "\n"
               + _canonical(event)).encode("utf-8")
    return f"{HMAC_TAG_VERSION}:" + hmac.new(
        key, message, hashlib.sha256).hexdigest()


def _tag_is_wellformed(tag: Any) -> bool:
    return (isinstance(tag, str)
            and tag.startswith(f"{HMAC_TAG_VERSION}:")
            and bool(_HEX64_RE.fullmatch(tag[len(HMAC_TAG_VERSION) + 1:])))


def _parse_ts(value: Any) -> datetime | None:
    """Parse a Paperclip timestamp (Z- or offset-suffixed ISO) to an aware
    UTC datetime; None when unparseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _quote_segment(value: Any, *, what: str, typed: bool) -> str:
    """One path segment: strict charset first, then percent-encoding.  A
    construction-time id raises ValueError; a server-supplied id raises the
    typed ``INVALID_ISSUE_ID`` (fail closed — it is never spliced raw)."""
    if not isinstance(value, str) or not _SEGMENT_RE.fullmatch(value):
        if typed:
            raise GblPaperclipError("INVALID_ISSUE_ID",
                                    f"{what} {str(value)[:60]!r} refused")
        raise ValueError(f"{what} must match [A-Za-z0-9_-]{{1,128}}")
    return urllib.parse.quote(value, safe="")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """A 3xx is never followed (panel B M6): urllib turns it into an
    ``HTTPError`` our caller maps to the typed redirect error."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(
    _NoRedirectHandler, urllib.request.ProxyHandler({}))


class PaperclipAskClient:
    """``GblAskStore`` (bridge_service.py:94) over Paperclip issues+comments.

    Constructed with the resolved dev-instance facts (base URL, company id,
    service-agent id) plus the host-held HMAC key path (§2) — ``from_spec``
    reads them from a GBL-4 roster spec file.  One urllib request per call;
    no retries anywhere (the EFFECT_UNKNOWN law: an unproven create is
    reported, never repeated).
    """

    def __init__(self, base_url: str, company_id: str,
                 service_agent_id: str, *,
                 hmac_key_path: str | Path | None = None,
                 headers: Mapping[str, str] | None = None,
                 timeout_seconds: float = 15.0,
                 target_agents: Mapping[str, str] | None = None,
                 service_agent_name: str | None = None,
                 _production_board: bool = False):
        # _production_board is PRIVATE to from_spec (P0-2 option (a)): it may
        # be True only after _require_canonical_production_spec has proven
        # the spec file is the canonical 0600 uid-owned regular file at
        # <pwd-home>/.mastermind/gbl/spec.json.  No other caller passes it;
        # direct construction keeps refusing 3100 and 3179.
        self._base = validate_paperclip_base_url(
            base_url, production_board=_production_board)
        self._company_seg = _quote_segment(company_id, what="company_id",
                                           typed=False)
        self._agent_id = _quote_segment(service_agent_id,
                                        what="service_agent_id", typed=False)
        # GBL-RETURN: the RAW id (server rows serve it unquoted; the charset
        # gate above makes quote(raw) == raw for every admitted id, and the
        # dispatch payloads/identity checks compare against served rows).
        self._agent_id_value = str(service_agent_id)
        # GBL-RETURN outcome 1: the delegate target table — handle -> board
        # agent id — held ON THIS SERVER (the spec), never caller-supplied.
        targets: dict[str, str] = {}
        for handle, agent in dict(target_agents or {}).items():
            if not isinstance(handle, str) or not handle:
                raise ValueError("target handles must be non-empty strings")
            if not isinstance(agent, str) or not _SEGMENT_RE.fullmatch(agent):
                raise ValueError(
                    f"targets[{handle!r}] must be an agent-id token "
                    "([A-Za-z0-9_-]{1,128})")
            targets[handle] = agent
        self._target_agents = targets
        # GBL-RETURN: the bridge agent's DISPLAY name comes from the spec
        # held on this server (paperclip.agent_name), never from a board
        # read of /api/agents/me — that route requires an AGENT actor and
        # refuses this client's local-trusted header with 401 (no-seam
        # proof 1 finding, dev board 2026-11-12).  Attribution text only;
        # no decision ever keys off it.
        name = str(service_agent_name or "").strip()
        self._agent_name = name[:120] if name else "the Grok bridge"
        if hmac_key_path is not None:
            path = Path(hmac_key_path).expanduser()
            if not path.is_absolute():
                raise ValueError(
                    f"hmac_key_path must be absolute: {hmac_key_path!r}")
            self._hmac_key_path: Path | None = path
        else:
            self._hmac_key_path = None
        self._hmac_key_bytes: bytes | None = None
        supplied = dict(headers or {})
        merged = {"x-instance-role": "local_trusted"}
        for key in supplied:
            if any(word in key.lower() for word in _BANNED_HEADER_WORDS):
                raise ValueError(
                    f"credential-shaped header {key!r} refused — no secret "
                    "rides a Paperclip request")
            merged[key] = supplied[key]
        self._headers = merged
        if not 0.1 <= float(timeout_seconds) <= 120:
            raise ValueError("timeout_seconds out of range")
        self._timeout = float(timeout_seconds)
        split = urllib.parse.urlsplit(self._base)
        self._host = split.hostname or ""
        self._port = split.port
        self._issue_ids: dict[str, str] = {}     # ask_id -> issue_id cache
        # GBL-5 A2: seq allocation and append are ONE atomic step under this
        # lock, and every mint is floored at the highest seq THIS client has
        # already issued for the record — a server listing that lags a
        # just-landed append (proof 1) can never make the store re-issue a
        # number the record has already taken.  GBL-5 micro 3: RE-ENTRANT,
        # because a result-delivery decision holds it and then appends its
        # CONSUMED mark through append_ask_event on the same thread.
        self._append_lock = threading.RLock()
        self._issued_seq: dict[str, int] = {}    # ask_id -> highest minted
        # GBL-5 micro 3: per-thread holder of the host flock, so a delivery
        # decision that appends can re-enter _host_append_lock instead of
        # deadlocking on its own lock (flock is per open file description,
        # so a second open + flock in the same process would block).
        self._host_lock_state = threading.local()

    # -- construction from a roster spec --------------------------------------

    @classmethod
    def from_spec(cls, path: str | Path) -> "PaperclipAskClient":
        """Build the client from a GBL-4 dev roster spec JSON file (the
        ``paperclip`` block: base_url, company_id, agent_id,
        hmac_key_path — the key path is REQUIRED: a spec that omits it
        would configure a trust-absent client, which is refused).

        ``paperclip.production_board: true`` (P0-2 option (a), principal
        ruling 2026-11-12 14:13Z) is the ONLY opt-in to the real board port
        3100, and this method is the ONLY caller that may honor it — after
        :func:`_require_canonical_production_spec` proves the spec file is
        the canonical ``<pwd-home>/.mastermind/gbl/spec.json`` (regular
        file, not a symlink, uid-owned, mode exactly 0600).  The field in a
        spec at any other path, with any other mode or owner, or with any
        non-true value, is the typed refusal
        ``PRODUCTION_BOARD_NOT_ALLOWED_HERE`` — never a silent fallback to
        the default law.  3179 stays refused under every flag."""
        try:
            spec = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read spec {path}: {exc}") from None
        # item 8(c): scan the WHOLE tree before anything else is honored —
        # a stray production_board field is the typed refusal even in a
        # spec that would never reach the paperclip-block gate.
        _refuse_stray_production_board_field(spec, Path(path))
        block = spec.get("paperclip") if isinstance(spec, dict) else None
        if not isinstance(block, dict):
            raise ValueError(f"spec {path} has no paperclip block")
        for field in ("base_url", "company_id", "agent_id",
                      "hmac_key_path"):
            if not block.get(field):
                raise ValueError(f"spec {path} paperclip.{field} is required")
        production = False
        if PRODUCTION_BOARD_FIELD in block:
            if block[PRODUCTION_BOARD_FIELD] is not True:
                raise GblPaperclipError(
                    "PRODUCTION_BOARD_NOT_ALLOWED_HERE",
                    f"spec {path} paperclip.{PRODUCTION_BOARD_FIELD} must be "
                    "the boolean true or absent — no other value opts in and "
                    "nothing falls back silently")
            _require_canonical_production_spec(Path(path))
            production = True
        # GBL-RETURN outcome 1: the delegate target table lives in the spec
        # ON THE SERVER (paperclip.targets: handle -> teammate agent id) —
        # a caller can never name an agent id, only a configured handle.
        targets = block.get("targets", {})
        if not isinstance(targets, dict):
            raise ValueError(f"spec {path} paperclip.targets must be an object")
        name = block.get("agent_name")
        if name is not None and not isinstance(name, str):
            raise ValueError(f"spec {path} paperclip.agent_name must be "
                             "a string")
        return cls(block["base_url"], block["company_id"], block["agent_id"],
                   hmac_key_path=block["hmac_key_path"],
                   target_agents=targets,
                   service_agent_name=name,
                   _production_board=production)

    # -- the GblAskStore interface --------------------------------------------

    def create_ask(self, ask: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """CREATE-IF-ABSENT (GBL_REPAIR1_NOTES §1.1): persist the validated
        ask envelope as ONE issue, assigned to the bridge service agent
        (ADDENDUM §3: the issue IS the record).

        Returns None when it created the record; returns the EXISTING
        record (a fresh copy built by :meth:`read_ask`) when the
        deterministic ask id is already present — no raise, no second
        issue, no mutation of the stored one.  The absence is decided by
        the store itself, so a caller whose earlier read raced can never
        end up with two records.  A lost or ambiguous CREATE outcome still
        raises ``GblCreateEffectUnknown`` — never retried here; a failure
        of the pre-create absence check is NOT an unknown effect (nothing
        began) and propagates as its own typed read error."""
        envelope = validate_ask(ask)      # re-validated; deep copy
        ask_id = envelope["ask_id"]
        existing = self.read_ask(ask_id)  # exact-key resolution; typed errors
        if existing is not None:          # propagate honestly
            return existing
        self._refuse_ambiguous_create(ask_id)
        payload = {
            "title": _issue_title(envelope),
            "description": f"{_ASK_MARKER_LINE}\n{_canonical(envelope)}",
            "assigneeAgentId": self._agent_id,
            "status": "todo",
        }
        try:
            row = self._request("POST",
                                f"/api/companies/{self._company_seg}/issues",
                                payload)
        except GblPaperclipClientError as exc:
            if exc.status in AMBIGUOUS_CREATE_4XX:
                # 408/409/425/429/499 do not certify "not created" (M7):
                # the outcome is unknown and reconciled by read-back.
                raise GblCreateEffectUnknown(
                    f"issue create outcome ambiguous ({exc.code})") from None
            raise                                  # a definite refusal
        except (GblPaperclipTransportError, GblPaperclipServerError) as exc:
            # The create began but its outcome is not certified (transport,
            # 5xx, redirect, truncated reply): unknown effect.  The bridge
            # reconciles by ONE read-back of the deterministic ask id; there
            # is never a second create.
            raise GblCreateEffectUnknown(
                f"issue create outcome unknown ({exc.code})") from None
        issue_id = row.get("id") if isinstance(row, dict) else None
        try:
            self._issue_ids[ask_id] = self._issue_seg(issue_id)
        except GblPaperclipError:
            # The create may have landed; the reply's id is unusable (M9).
            raise GblCreateEffectUnknown(
                "issue create reply carried no usable issue id") from None
        return None

    def read_ask(self, ask_id: str) -> dict[str, Any] | None:
        """The stored record for the ask id, or None.  Found by the
        deterministic id even when the create reply was lost (the only create
        reconciliation path): a direct issue read when known, else a
        paginated scan for the record whose STORED envelope carries exactly
        that id."""
        issue = self._issue_for(ask_id)
        if issue is None:
            return None
        envelope = _parse_ask_envelope(issue.get("description"))
        if envelope is None or envelope.get("ask_id") != ask_id:
            return None
        try:
            record = dict(validate_ask(envelope))
        except GBLContractError as exc:
            raise GblPaperclipError(
                "RECORD_INVALID",
                f"issue {issue.get('id')} failed contract validation: "
                f"{exc.code}") from None
        record["events"] = self._events(self._issue_seg(issue.get("id")),
                                        ask_id)
        return record

    # -- the ONE host-wide append lock (GBL-5 R2, RULING 19b) -------------------

    @contextlib.contextmanager
    def _host_append_lock(self):
        """An exclusive flock on ``append.lock`` in the GBL state dir (the
        HMAC key's directory), held across the WHOLE allocation+append step
        of :meth:`append_ask_event` — and, since GBL-5 micro 3, across the
        read→replay→mark decision of :meth:`result_delivery_lock`.  One
        lock file per host serialises every writer process — the bridge,
        the CLI (over the bridge socket), control intake, nudge/reconcile
        and any ``from_spec`` client — because every append funnels
        through this method.  The kernel releases the flock when the
        holder dies, so a crashed writer never wedges the lane.  The lock
        file doubles as the mint ledger (append-only JSON lines, parsed by
        :meth:`_ledger_floor`); a torn tail line from a crash is ignored
        on read.

        RE-ENTRANT per thread: a holder that appends (the delivery
        decision does exactly that) re-enters and receives the SAME open
        handle instead of a second flock, which would block on the first
        (flock is per open file description, even within one process)."""
        state = self._host_lock_state
        held = getattr(state, "handle", None)
        if held is not None:
            state.depth += 1
            try:
                yield held
            finally:
                state.depth -= 1
            return
        if self._hmac_key_path is None:
            # Unreachable behind append_ask_event's key-first law; kept as
            # an independent fail-closed door with the canonical code.
            raise GblPaperclipError(
                "HMAC_KEY_NOT_CONFIGURED",
                "this client holds no hmac_key_path; a spec always "
                "configures one")
        path = self._hmac_key_path.parent / APPEND_LOCK_NAME
        try:
            handle = open(path, "a+", encoding="utf-8")
        except OSError as exc:
            raise GblPaperclipError(
                "APPEND_LOCK_UNWRITABLE", f"{path}: {exc}") from None
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            state.handle, state.depth = handle, 1
            try:
                yield handle
            finally:
                state.handle = None
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    @contextlib.contextmanager
    def result_delivery_lock(self):
        """GBL-5 micro 3, RULING 19(a)/19(b): the SAME host lock that
        serialises appends, held across a result-delivery decision (read →
        replay → append CONSUMED).

        The mark is permanent, so two callers must never both see
        ANSWERED: ``fetch_result`` re-reads its record INSIDE this lock
        and the second caller therefore sees the first caller's mark.
        Serialising only the appends was not enough — the read-then-decide
        was outside them, and "one connection at a time" is a property of
        today's server, not of this layer.  Lock order is always the
        threading lock first, then the flock, and
        :meth:`append_ask_event` re-enters both: no deadlock."""
        with self._append_lock:
            self._hmac_key()          # key law first: no lock file before it
            with self._host_append_lock():
                yield

    @staticmethod
    def _ledger_floor(handle: Any, ask_id: str) -> int:
        """The highest seq the ledger has EVER minted for the ask — the
        cross-process floor.  Only complete JSON lines count (a torn tail
        line from a crashed writer is skipped); any line that is not a
        ``{"ask_id": …, "seq": int}`` shape is ignored, never fatal: the
        ledger may only RAISE the floor, and a lost line falls back to the
        listing, which reflects whatever POSTs landed."""
        floor = 0
        try:
            handle.seek(0)
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue               # torn tail: skipped, not fatal
                if (isinstance(row, dict) and row.get("ask_id") == ask_id
                        and type(row.get("seq")) is int):
                    floor = max(floor, row["seq"])
        except OSError as exc:
            raise GblPaperclipError(
                "APPEND_LOCK_UNREADABLE",
                f"mint ledger unreadable: {exc}") from None
        return floor

    @staticmethod
    def _ledger_mint(handle: Any, ask_id: str, seq: int) -> None:
        """Record a minted number BEFORE the POST: a number, once minted,
        is never re-issued by any process on this host even when its POST
        then fails (the worst case is a skipped number, never a
        duplicate).  Refuses typed rather than appending outside the
        serialised discipline."""
        try:
            handle.write(json.dumps({"ask_id": ask_id, "seq": seq}) + "\n")
            _sync_ledger_line(handle)
        except OSError as exc:
            raise GblPaperclipError(
                "APPEND_LOCK_UNWRITABLE",
                f"mint ledger write refused: {exc}") from None

    # ── the delivery ledger (GBL-5 micro 4) ─────────────────────────────
    #
    # The result-delivery decision needs a record that cannot lag this
    # host's own writes.  The issue's comment listing can (proof 1's
    # read-your-write lag), and deciding from it hands one answer out
    # twice.  The append ledger FILE, read and written under the same
    # flock as every append, is that record: one JSON line per delivery,
    # written BEFORE the CONSUMED post and consulted FIRST.  A record
    # with no integer ``seq`` is ignored by :meth:`_ledger_floor`, so the
    # mint floor is unaffected.

    @staticmethod
    def _ledger_delivered(handle: Any, ask_id: str) -> str | None:
        """The answer this host has recorded as DELIVERED for the ask.

        ``None`` when no delivery was recorded; the recorded answer id
        (possibly ``""`` for a legacy ANSWERED record with no answer
        event) when one was.  Complete JSON lines only — a torn tail
        line is skipped, never fatal: a lost line can only make the
        layer fall back to the listing, which is today's behaviour."""
        delivered: str | None = None
        try:
            handle.seek(0)
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue               # torn tail: skipped, not fatal
                if (isinstance(row, dict) and row.get("ask_id") == ask_id
                        and row.get("delivered") is True):
                    value = row.get("answer_id")
                    delivered = value if isinstance(value, str) else ""
        except OSError as exc:
            raise GblPaperclipError(
                "APPEND_LOCK_UNREADABLE",
                f"delivery ledger unreadable: {exc}") from None
        return delivered

    @staticmethod
    def _ledger_delivery(handle: Any, ask_id: str, answer_id: str) -> None:
        """Record a delivery BEFORE its CONSUMED post, so a post that
        fails still leaves the answer withheld rather than deliverable
        again.  Refuses typed rather than delivering outside the
        serialised discipline."""
        try:
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps({"ask_id": ask_id,
                                     "answer_id": answer_id,
                                     "delivered": True}) + "\n")
            _sync_ledger_line(handle)
        except OSError as exc:
            raise GblPaperclipError(
                "APPEND_LOCK_UNWRITABLE",
                f"delivery ledger write refused: {exc}") from None

    def delivered_answer_id(self, ask_id: str) -> str | None:
        """The host's own delivery record for the ask (see
        :meth:`_ledger_delivered`), read under the same flock every
        append takes.  ``None`` means this host has delivered nothing."""
        with self._append_lock:
            self._hmac_key()
            with self._host_append_lock() as lock:
                return self._ledger_delivered(lock, ask_id)

    def record_delivery(self, ask_id: str, answer_id: str) -> None:
        """Claim the delivery in the host ledger.  Call under
        :meth:`result_delivery_lock`, BEFORE the CONSUMED post."""
        with self._append_lock:
            self._hmac_key()
            with self._host_append_lock() as lock:
                self._ledger_delivery(lock, ask_id, answer_id)

    def append_ask_event(self, ask_id: str,
                         event: Mapping[str, Any]) -> None:
        """Append ONE comment carrying the event, stamped by the store
        itself with the next per-record ``seq`` and its §2 v1 tag
        (idempotent by core content: a redelivered identical event — or an
        append whose reply was lost and is retried — matches a TRUSTED
        existing core and never duplicates the comment).

        The store is the only stamper: incoming ``seq``/``tag``/``trusted``
        keys are never written through.  ``seq`` is
        ``max(seq of VERIFIED events) + 1`` — derived solely from
        tag-verified events, so a foreign or untrusted comment can never
        move or block the sequence (deputy steer, round 2).

        GBL-5 A2 (proof 1's defect): allocation and append are ONE atomic
        step under the store's own append lock, and every mint is floored
        at the highest seq this client has already issued for the record.
        Two appender threads can never take the same number (the lock), and
        neither can a listing that lags a just-landed append — proof 1's
        1.8 s read lag re-issued seq 3 for the CONSUMED append after the
        nudge had already taken it.  A number, once minted, is never
        re-issued even if its POST then fails (the floor is set at mint
        time, inside the lock); the worst case is a skipped number, never
        a duplicate.

        GBL-5 R2, RULING 19(b) (the H1 residue): the A2 lock and floor were
        per client OBJECT.  Numbering and append are now serialised across
        every PROCESS on this host by ONE flock on ``append.lock`` in the
        GBL state dir, and the floor is also read from that file's mint
        ledger — a second client object, or the same store reached from
        another process (nudge lane, control intake), can no more re-issue
        a taken number than a second thread can.  Only ONE host writes the
        store; a second host holds a different lock file and is out of
        contract by construction."""
        core = {key: value for key, value in dict(event).items()
                if key not in ("seq", "tag", "trusted")}
        with self._append_lock:
            self._hmac_key()   # key law first: no lock file before the key
            with self._host_append_lock() as lock:
                issue = self._issue_for(ask_id)
                if issue is None:
                    raise GblPaperclipError("ASK_ISSUE_NOT_FOUND", ask_id)
                seg = self._issue_seg(issue.get("id"))
                verified = [(event, trusted) for _row, event, trusted
                            in self._chain_verified_events(seg, ask_id)]
                next_seq = 1
                for _event, trusted in verified:
                    if trusted is True and type(_event.get("seq")) is int:
                        next_seq = max(next_seq, _event["seq"] + 1)
                floor = max(self._issued_seq.get(ask_id, 0),
                            self._ledger_floor(lock, ask_id))
                if next_seq <= floor:
                    next_seq = floor + 1
                core_json = _canonical(core)
                for _event, trusted in verified:
                    # Idempotent only on a TRUSTED match: a forged copy of
                    # our core (untrusted) must not suppress the real
                    # append.
                    if trusted is True:
                        stored_core = {k: v for k, v in _event.items()
                                       if k not in ("seq", "trusted")}
                        if _canonical(stored_core) == core_json:
                            return          # already appended; no duplicate
                self._issued_seq[ask_id] = next_seq    # minted in-process…
                self._ledger_mint(lock, ask_id, next_seq)   # …and host-wide
                stamped = {**core, "seq": next_seq}
                tagged = dict(stamped)
                tagged["tag"] = _event_tag(self._hmac_key(), ask_id, next_seq,
                                           stamped)
                body = f"{EVENT_MARKER} {_canonical(tagged)}"
                self._request("POST", f"/api/issues/{seg}/comments",
                              {"clientRequestId": str(uuid.uuid4()),
                               "body": body})

    def count_asks(self, principal: str, since_iso: str) -> int:
        """That principal's asks created at or after ``since_iso`` (UTC ISO),
        for the hourly ceilings.  FAILS CLOSED on any doubt (panel B H2/M5):
        an unknown envelope shape, an unsupported pagination, a corrupt
        marker-bearing record or a listing past the cap raises — it is never
        read as a short count.  A row whose timestamp cannot be parsed is
        counted: failing open there would under-count toward a ceiling."""
        since = _parse_ts(since_iso)
        if since is None:
            raise GblPaperclipError("INVALID_SINCE", since_iso)
        total = 0
        for issue in self._iter_issues():
            envelope = _parse_ask_envelope(issue.get("description"))
            if envelope is None or envelope.get("principal") != principal:
                continue
            created = _parse_ts(issue.get("createdAt"))
            if created is None or created >= since:
                total += 1
        return total

    # -- GBL-RETURN: the delegate dispatch/return capability ------------------
    #
    # The optional GblDelegateDispatchStore arm of this store: a delegate ask
    # is handed to the target teammate THROUGH THE BOARD in the RF carrier's
    # installed ask-child shape (one child of the ask-record issue, assigned
    # to the teammate's agent, parent blocked on it with a self-owned unblock
    # descriptor), and the answer comes back from the bridge's OWN board read
    # of that child — never from waker-supplied text.

    def resolve_target_agent(self, target: str) -> str:
        """The target teammate's board agent id from the spec's target table
        held ON THIS SERVER — never from the caller.  An unknown handle is
        the typed ``TARGET_AGENT_NOT_CONFIGURED`` refusal."""
        agent = self._target_agents.get(str(target))
        if agent is None:
            raise GblPaperclipError(
                "TARGET_AGENT_NOT_CONFIGURED",
                f"target {str(target)[:64]!r} names no row of the spec's "
                "paperclip.targets table")
        return agent

    def _full_issue(self, issue_id: Any) -> dict[str, Any]:
        """GET one issue in FULL — the list projection truncates a long
        description (``descriptionTruncated``) and the ask-marker hash is
        over the SERVED text, so every marker decision reads the whole row."""
        seg = self._issue_seg(issue_id)
        row = self._request("GET", f"/api/issues/{seg}")
        if not isinstance(row, dict):
            raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_ROW", seg)
        return row

    def _children_rows(self, issue_id: Any) -> list[dict[str, Any]]:
        """The parentId-filtered children walk, field-for-field the RF law:
        a SHORT page is not the end (a server may clamp ``limit``), only an
        EMPTY page ends the walk, bounded at ten pages; rows dedupe by id
        (offset paging over a moving list can serve a row twice) and the
        parentId is stamped (the query already filtered on it, so a list
        projection omitting the field cannot strand the return edge)."""
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        offset = 0
        for _page in range(MAX_CHILDREN_PAGES):
            query = urllib.parse.urlencode(
                {"parentId": str(issue_id), "limit": CHILDREN_PAGE_LIMIT,
                 "offset": offset})
            batch = self._request(
                "GET", f"/api/companies/{self._company_seg}/issues?{query}")
            if isinstance(batch, dict):
                # An unrecognised shape is NOT an empty result (RF attack
                # finding 6): {"data": …} or {"error": …} must never read as
                # "no children".
                batch = next((batch[key] for key in ("issues", "children",
                                                     "rows")
                              if isinstance(batch.get(key), list)), None)
            if not isinstance(batch, list):
                raise GblPaperclipTransportError("UNPARSEABLE_CHILDREN_LIST")
            for row in batch:
                if not isinstance(row, dict):
                    raise GblPaperclipTransportError(
                        "UNPARSEABLE_CHILDREN_LIST")
                row = dict(row)
                row.setdefault("parentId", str(issue_id))
                key = str(row.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
            if not batch:
                break
            offset += len(batch)
        return rows

    def _untruncated_children(self, issue_id: Any) -> list[dict[str, Any]]:
        """The children walk, truncation-aware (RF proof 2 / Delta-3 N5):
        every truncated row that could be THIS bridge's is re-read in full
        before any marker test, and a FAILED re-read fails the walk typed —
        a markerless list row would make the family look empty and silently
        strand the return edge.  A truncated row the board attributes to
        another creator is skipped without the re-read (Delta-4 D4-3)."""
        rows: list[dict[str, Any]] = []
        for row in self._children_rows(issue_id):
            if row.get("descriptionTruncated") and row.get("id"):
                owner = row.get("createdByAgentId")
                if owner and owner != self._agent_id_value:
                    continue        # foreign: no marker test of ours uses it
                rows.append(self._full_issue(row["id"]))
            else:
                rows.append(row)
        return rows

    def _is_ask_child_of(self, row: Mapping[str, Any],
                         parent: Mapping[str, Any]) -> bool:
        """The RF identity test: parented on ``parent`` AND ending with
        exactly the marker computed from the parent's SERVED content."""
        if not parent or row.get("parentId") != parent.get("id"):
            return False
        return (_rf_ask_child_marker(row.get("description") or "")
                == _rf_expected_ask_op(parent))

    def _ask_parent_row(self, ask_id: str) -> dict[str, Any]:
        """The ask-record issue for this ask id, FULLY read, still carrying
        exactly this envelope (a foreign edit that swapped the record is the
        typed ASK_RECORD_MISMATCH refusal, never a dispatch on wrong text)."""
        if not ASK_ID_RE.fullmatch(ask_id or ""):
            raise GblPaperclipError("ASK_ID_INVALID", str(ask_id)[:64])
        row = self._issue_for(ask_id)
        if row is None:
            raise GblPaperclipError("ASK_RECORD_MISSING", ask_id)
        full = self._full_issue(row["id"])
        if not self._envelope_is(full, ask_id):
            raise GblPaperclipError("ASK_RECORD_MISMATCH", ask_id)
        return full

    def dispatch_delegate(self, ask: Mapping[str, Any]) -> dict[str, Any]:
        """GBL-RETURN outcome 1 — DELEGATE OUT.  Create-or-reuse the child
        issue of the ask record in the RF carrier's exact shape and leave
        the parent blocked on it, so the target teammate's installed carrier
        wakes on the child and its ``deliver(ask_child=True)`` (status done)
        fires the parent's issue_blockers_resolved wake back at the bridge.

        Idempotent across runs by the RF reuse scan (marker at the
        description END + created by THIS bridge + open + same assignee +
        same sanitised title).  An ambiguous create — transport failure,
        5xx, or the ambiguous 4xx set — is NEVER retried as a second create:
        ONE re-scan reconciles, and a re-scan that finds nothing raises
        ``GblCreateEffectUnknown`` for the bridge to surface.  Not
        team.message, not a running t3; RF files are untouched."""
        envelope = dict(ask)
        ask_id = str(envelope.get("ask_id") or "")
        target_agent = self.resolve_target_agent(
            str(envelope.get("target") or ""))
        parent = self._ask_parent_row(ask_id)
        parent_seg = self._issue_seg(parent["id"])
        ask_op = _rf_expected_ask_op(parent)
        want_title = _rf_strip_markers(envelope.get("title")) or "Asked work"
        description = _rf_strip_markers(envelope.get("body"))
        me_name = self._agent_name

        def find_child(*, open_only: bool) -> dict[str, Any] | None:
            for row in self._untruncated_children(parent["id"]):
                creator = row.get("createdByAgentId")
                # Delta-3 N9: only OUR child is reusable.  A NULL creator
                # still counts as ours: a real board serving this client's
                # local-trusted role stamps createdByAgentId=null on its
                # creates (no-seam dev-board proof, 2026-11-12).  A
                # NON-NULL foreign id is still skipped.
                if creator is not None and creator != self._agent_id_value:
                    continue
                if not self._is_ask_child_of(row, parent):
                    continue
                if open_only and row.get("status") in ("done", "cancelled"):
                    continue        # a finished child is not work in flight
                if row.get("assigneeAgentId") != target_agent:
                    continue
                if (row.get("title") or "") != want_title:
                    continue
                return row
            return None

        child = find_child(open_only=True)
        reused = child is not None
        if child is None:
            payload = {
                "title": want_title,
                "description": (f"{description}\n\n"
                                f"Asked by {me_name} on "
                                f"{parent.get('identifier')}\n[{ask_op}]"),
                "assigneeAgentId": target_agent,
                "parentId": parent["id"],
                "status": "todo",
            }
            try:
                created = self._request(
                    "POST", f"/api/companies/{self._company_seg}/issues",
                    payload)
                if not isinstance(created, dict) or not created.get("id"):
                    raise GblPaperclipTransportError(
                        "UNPARSEABLE_CHILD_ROW", ask_id)
                child = created
            except GblPaperclipClientError as exc:
                if exc.status not in AMBIGUOUS_CREATE_4XX:
                    raise       # a definite 4xx refusal is typed, not unknown
                child = self._reconcile_child_create(
                    ask_id, exc, find_child)
                reused = True
            except (GblPaperclipTransportError,
                    GblPaperclipServerError) as exc:
                child = self._reconcile_child_create(
                    ask_id, exc, find_child)
                reused = True
        child_id = str(child["id"])
        # The blocked-parent relation (RF handle_ask law): a FRESH read
        # decides, the PATCH carries the WHOLE recorded blocker set plus
        # this child, and the unblock owner is SELF — the board refuses an
        # agent naming another owner (403, live 2026-11-10).  Skipped only
        # when the relation is already exactly recorded.
        fresh = self._full_issue(parent["id"])
        descriptor = fresh.get("unblockDescriptor") or {}
        identifier = child.get("identifier")
        if (fresh.get("status") != "blocked"
                or not identifier
                or str(identifier) not in str(descriptor.get("action") or "")):
            blocker_ids = list(dict.fromkeys(
                _rf_recorded_blocker_ids(fresh) + [child_id]))
            try:
                self._request("PATCH", f"/api/issues/{parent_seg}", {
                    "status": "blocked",
                    "blockedByIssueIds": blocker_ids,
                    "unblockDescriptor": {
                        "owner": {"agentId": self._agent_id_value},
                        "action": (f"{envelope.get('target')} completes "
                                   f"{identifier}: {want_title}")}})
            except (GblPaperclipTransportError,
                    GblPaperclipServerError) as exc:
                # The child exists; only the relation is uncertain.  A
                # re-dispatch reconciles by the reuse scan and retries the
                # PATCH — never a second child.
                raise GblCreateEffectUnknown(
                    f"block PATCH for {ask_id} is ambiguous "
                    f"({type(exc).__name__}); the child {child_id} exists — "
                    "re-dispatch reconciles by reuse scan") from None
        return {"child_issue_id": child_id, "child_identifier": identifier,
                "target_agent": target_agent, "reused": reused}

    @staticmethod
    def _reconcile_child_create(ask_id: str, exc: Exception,
                                find_child: Callable[[bool], Any]):
        """The RF R2a finding-6 law: a create whose answer was lost is
        reconciled by ONE re-scan for this ask's own child — and only a
        child of THIS ask (same marker, assignee and title; the create-
        losing scan keeps RF's shape and does not require open status, a
        child may have been finished in the meantime).  Nothing found ⇒ the
        effect stays unknown; never a second create."""
        row = find_child(open_only=False)
        if row is None:
            raise GblCreateEffectUnknown(
                f"child create for {ask_id} is ambiguous "
                f"({type(exc).__name__}) and the re-scan found no child"
            ) from None
        return row

    def read_dispatch_child(self, ask_id: str,
                            child_issue_id: str) -> dict[str, Any]:
        """GBL-RETURN outcomes 2/5 — the child THIS bridge dispatched,
        proven by the whole RF identity law, never by a wake-supplied id
        alone: parented on the ask record, ending with the marker computed
        from the parent's SERVED content, assigned to the spec-resolved
        target agent, created by this bridge (when the board serves the
        creator), and — while the parent still records blockers — inside
        that recorded set (RF handle_return: an EMPTY recorded set falls
        back to the other checks; the board clears the relation when it
        resolves the wake).  Any mismatch is the typed
        ``RETURN_CHILD_NOT_OURS`` refusal: a return for a child the bridge
        did not create never enters the record."""
        parent = self._ask_parent_row(ask_id)
        envelope = _parse_ask_envelope(parent.get("description")) or {}
        try:
            child = self._full_issue(child_issue_id)
        except GblPaperclipClientError as exc:
            if exc.code == "HTTP_404":
                raise GblPaperclipError(
                    "RETURN_CHILD_NOT_OURS",
                    f"child {str(child_issue_id)[:64]} does not exist"
                ) from None
            raise
        blocker_ids = _rf_recorded_blocker_ids(parent)
        checks = (
            ("parent", child.get("parentId") == parent.get("id")),
            ("marker", self._is_ask_child_of(child, parent)),
            ("blocker", (not blocker_ids)
             or str(child_issue_id) in blocker_ids),
            ("assignee", child.get("assigneeAgentId")
             == self.resolve_target_agent(str(envelope.get("target") or ""))),
        )
        creator = child.get("createdByAgentId")
        if creator is not None:
            checks += (("creator", creator == self._agent_id_value),)
        failed = [name for name, ok in checks if not ok]
        if failed:
            raise GblPaperclipError(
                "RETURN_CHILD_NOT_OURS",
                f"child {str(child_issue_id)[:64]} fails: {','.join(failed)}")
        return child

    def read_child_result(self, ask_id: str,
                          child_issue_id: str) -> dict[str, Any]:
        """The child's outcome from the bridge's OWN board read: done +
        the RF result-comment law ⇒ the answer; cancelled ⇒ terminal, no
        answer (RF q1-10: a cancelled child carries nothing back); anything
        else ⇒ not yet.  A failed comments read FAILS typed — it is never
        read as "no answer" (RF R2a finding 17)."""
        child = self.read_dispatch_child(ask_id, child_issue_id)
        status = child.get("status")
        if status == "cancelled":
            return {"done": False, "cancelled": True, "answer": None}
        if status != "done":
            return {"done": False, "cancelled": False, "answer": None}
        return {"done": True, "cancelled": False,
                "answer": self._last_result_comment(child)}

    def _last_result_comment(self, child: Mapping[str, Any]) -> str:
        """The RF result-comment law, field-for-field: the LAST comment
        authored by the child's own assignee (authorType agent, author id =
        the child's assigneeAgentId) that is not a machine comment; else the
        newest non-machine comment under a prefix saying it is NOT the asked
        teammate's own words; else the pointer.  (The installed board may
        serve plain-route comments unattributed — gbl4-devproof 2026-11-11 —
        in which case the disclaimed fallback is the served path, exactly as
        in the RF carrier.)"""
        rows = self._comment_rows(self._issue_seg(child["id"]))
        assignee = child.get("assigneeAgentId")
        if assignee:
            for row in reversed(rows):          # newest first
                body = str(row.get("body") or "").strip()
                if (body and row.get("authorType") == "agent"
                        and row.get("authorAgentId") == assignee
                        and not _rf_is_machine_comment(body)):
                    return body
        for row in reversed(rows):
            body = str(row.get("body") or "").strip()
            if body and not _rf_is_machine_comment(body):
                return ("(the asked teammate's own comment was not found; "
                        "this is the newest comment on the child issue, not "
                        "their answer)\n\n" + body)
        return "(no answer comment on the child issue)"

    def scan_delegate_asks(self) -> list[str]:
        """GBL-RETURN outcome 2 — the bridge's OWN bounded read of open
        delegate asks (the lost-wake recovery source; acceptable because the
        board wake is the primary and this read is capped and read-only).
        Truncation-aware: a list row whose description the projection cut is
        re-read in full before the envelope parse, so a long-bodied delegate
        ask is never misread as corrupt or foreign."""
        found: list[str] = []
        seen: set[str] = set()
        for row in self._iter_issues():
            if len(found) >= SCAN_DELEGATE_ASKS_MAX:
                break
            if row.get("status") in ("done", "cancelled"):
                continue
            if row.get("descriptionTruncated") and row.get("id"):
                row = self._full_issue(row["id"])
            envelope = _parse_ask_envelope(row.get("description"))
            if envelope is None or envelope.get("kind") != "delegate":
                continue
            ask_id = envelope.get("ask_id")
            if (not isinstance(ask_id, str)
                    or not ASK_ID_RE.fullmatch(ask_id)
                    or ask_id in seen):
                continue
            seen.add(ask_id)
            found.append(ask_id)
        return found

    # -- issue resolution (exact key only; panel B M3) -------------------------

    def _issue_seg(self, value: Any) -> str:
        return _quote_segment(value, what="issue_id", typed=True)

    def _refuse_ambiguous_create(self, ask_id: str) -> None:
        """Panel B delta-2 F1: the ask reads as ABSENT, but an issue whose
        TITLE carries the exact ``[ask_id]`` token means the record's marker
        line was removed (a foreign edit) — creating now would mint a
        duplicate whose empty record strands the stored events on the old
        issue.  Refuse, typed; the repair (restore the description) is
        out-of-band.  The bracketed token is exact by construction: ask ids
        are a fixed ``gb-`` + 32-hex shape, so the closing bracket cannot
        belong to a longer id."""
        token = f"[{ask_id}]"
        for row in self._iter_issues():
            title = row.get("title")
            if isinstance(title, str) and token in title:
                raise GblPaperclipError(
                    "AMBIGUOUS_CREATE",
                    f"ask {ask_id} reads absent but issue {row.get('id')} "
                    f"carries its title token — the record's marker was "
                    f"removed; restore the description instead of creating")

    def _issue_for(self, ask_id: str) -> dict[str, Any] | None:
        """The issue whose STORED envelope carries exactly this ask id.
        The parsed description envelope is the only exact key (stronger than
        an exact title token); a title substring never resolves anything,
        and only an exact match is ever cached."""
        if not ASK_ID_RE.fullmatch(ask_id or ""):
            return None
        issue_id = self._issue_ids.get(ask_id)
        if issue_id is not None:
            try:
                row = self._request("GET", f"/api/issues/{issue_id}")
            except GblPaperclipClientError as exc:
                if exc.code != "HTTP_404":
                    raise
            else:
                if self._envelope_is(row, ask_id):
                    return row
            self._issue_ids.pop(ask_id, None)   # stale; resolve again
        for row in self._iter_issues():
            if self._envelope_is(row, ask_id):
                self._issue_ids[ask_id] = str(row["id"])
                return row
        return None

    def _envelope_is(self, row: Mapping[str, Any], ask_id: str) -> bool:
        envelope = _parse_ask_envelope(row.get("description"))
        return envelope is not None and envelope.get("ask_id") == ask_id

    def _iter_issues(self) -> Iterator[dict[str, Any]]:
        """Every company issue row, paginated to exhaustion (panel B H2).
        Fail closed: an unknown envelope shape, junk rows, an unusable id,
        a server that ignores pagination (the same page head twice), or a
        listing past the page cap is a typed error — never a short read."""
        seen: set[str] = set()
        offset = 0
        for _page in range(MAX_LIST_PAGES):
            query = urllib.parse.urlencode(
                {"limit": LIST_PAGE_LIMIT, "offset": offset})
            rows = self._request(
                "GET", f"/api/companies/{self._company_seg}/issues?{query}")
            if isinstance(rows, dict):
                if isinstance(rows.get("issues"), list):
                    rows = rows["issues"]
                elif isinstance(rows.get("rows"), list):
                    rows = rows["rows"]
                else:
                    raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_LIST")
            if not isinstance(rows, list):
                raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_LIST")
            page: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    raise GblPaperclipTransportError("UNPARSEABLE_ISSUE_LIST")
                page.append(row)          # ids validated as used, below
            if page:
                head = str(page[0].get("id"))
                if head in seen:
                    # offset returned the same page head: the server does
                    # not paginate; a partial scan would silently hide asks.
                    raise GblPaperclipError("PAGINATION_UNSUPPORTED",
                                            f"offset {offset} replayed the "
                                            f"page head {head}")
                for row in page:
                    issue_id = str(row.get("id"))
                    if issue_id not in seen:
                        self._issue_seg(issue_id)   # charset gate (M9)
                        seen.add(issue_id)
                        yield row
            if len(page) < LIST_PAGE_LIMIT:
                return
            offset += len(page)
        raise GblPaperclipError(
            "LIST_TOO_LARGE",
            f"exceeded {MAX_LIST_PAGES} pages of {LIST_PAGE_LIMIT}")

    def _comment_rows(self, issue_seg: str) -> list[dict[str, Any]]:
        """The issue's comment rows in stable server order (oldest first).
        Fail closed: an unknown envelope shape or junk row is a typed
        error, never an empty list (panel B M4)."""
        rows = self._request("GET", f"/api/issues/{issue_seg}/comments")
        if isinstance(rows, dict):
            if isinstance(rows.get("comments"), list):
                rows = rows["comments"]
            elif isinstance(rows.get("rows"), list):
                rows = rows["rows"]
            else:
                raise GblPaperclipTransportError("UNPARSEABLE_COMMENTS")
        if not isinstance(rows, list):
            raise GblPaperclipTransportError("UNPARSEABLE_COMMENTS")
        for row in rows:
            if not isinstance(row, dict):
                raise GblPaperclipTransportError("UNPARSEABLE_COMMENTS")

        def order(row: Mapping[str, Any]) -> tuple[str, str]:
            stamp = _parse_ts(row.get("createdAt"))
            return (stamp.isoformat() if stamp else "",
                    str(row.get("id") or ""))

        # The API lists newest first; events replay oldest first, in the
        # total server order (createdAt, then id) the bridge also sees.
        return sorted(rows, key=order)

    def _stored_events(self, issue_seg: str) -> list[dict[str, Any]]:
        """The parsed JSON of every event-shaped comment on the issue, in
        the stable server order (oldest first)."""
        stored: list[dict[str, Any]] = []
        for row in self._comment_rows(issue_seg):
            event = _parse_event_body(str(row.get("body") or ""))
            if event is not None:
                stored.append(event)
        return stored

    def _chain_verified_events(
            self, issue_seg: str,
            ask_id: str) -> list[tuple[dict[str, Any], dict[str, Any], bool]]:
        """The event-shaped comments, oldest first, each verified by tag
        alone and THEN by the GBL-5 R2 chain law (RULING 19(a) + deputy
        MED-1):

        * a tag-verified event whose seq EQUALS an earlier tag-verified
          event's is a re-issued number.  For a NON-state event the LATER
          holder is demoted FOR THAT EVENT (``trusted: False``, typed
          ``defect: EVENT_SEQ_DUPLICATE``) and the first holder stays
          authoritative — the A3 law, unchanged.  For a STATE event (a
          delivery mark) nothing is demoted: whether the result was
          delivered is exactly what the duplicate leaves unclear, so the
          reading refuses typed ``EVENT_ORDER_AMBIGUOUS`` and every
          consumer (the read path, the append path's allocation and
          idempotency check) sees the same refusal — nothing is
          delivered, re-derived or 'healed' forward.
        * a tag-verified seq strictly LOWER than an earlier trusted one
          is a chain anomaly (a delayed or torn append), never a
          duplicate: it refuses ``EVENT_ORDER_AMBIGUOUS`` too.

        Each entry is ``(comment row, event, trusted)``; plain comments
        are not events and never appear."""
        verified: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
        seen_seq: set[int] = set()
        last_seq: int | None = None
        for row in self._comment_rows(issue_seg):
            stored = _parse_event_body(str(row.get("body") or ""))
            if stored is None:
                continue          # a plain comment: not an event at all
            event, trusted = self._verified_event(stored, ask_id)
            if trusted and type(event.get("seq")) is int:
                seq = event["seq"]
                if seq in seen_seq:
                    if event.get("type") == "state":
                        raise GblPaperclipError(
                            "EVENT_ORDER_AMBIGUOUS",
                            f"ask {ask_id}: trusted seq {seq} is held by "
                            f"an earlier event and by a state event "
                            f"({event.get('state')}); whether the result "
                            f"was delivered is unclear — nothing is "
                            f"delivered or re-derived")
                    event["trusted"] = False
                    event["defect"] = "EVENT_SEQ_DUPLICATE"
                    trusted = False
                else:
                    if last_seq is not None and seq < last_seq:
                        raise GblPaperclipError(
                            "EVENT_ORDER_AMBIGUOUS",
                            f"ask {ask_id}: trusted seq {seq} follows "
                            f"trusted seq {last_seq}; the chain order is "
                            f"unclear — nothing is delivered or re-derived")
                    seen_seq.add(seq)
                    last_seq = seq
            verified.append((row, event, trusted))
        return verified

    def _events(self, issue_seg: str,
                ask_id: str) -> list[dict[str, Any]]:
        """The record's events, each stamped with the computed ``trusted``
        flag (§2: verified by the host-held tag — never by an author field
        or a claimed in-JSON ``trusted`` key) and carrying the stored
        ``seq``.  Untrusted events stay visible with ``trusted: False``;
        the bridge ignores them.  GBL-5 A3: a duplicate seq is demoted for
        that event (typed EVENT_SEQ_DUPLICATE) — never a refusal of the
        whole record; proof 1's duplicate-seq record used to fail every
        later read."""
        events: list[dict[str, Any]] = []
        for row, event, _trusted in self._chain_verified_events(issue_seg,
                                                                ask_id):
            _add_comment_provenance(event, row)
            events.append(event)
        return events

    def _verified_event(self, stored: Mapping[str, Any],
                        ask_id: str) -> tuple[dict[str, Any], bool]:
        """One stored event JSON → (surfaced event, trusted).  Trust is
        EXACTLY tag verification (§2.4): the tag must be well-formed v1,
        the seq an integer, and the HMAC must bind (ask_id, seq, event).
        Everything else — no tag, wrong version, cross-ask binding,
        tampered content, a claimed ``trusted`` key — is ``False``.

        EVERY key only the store may set is stripped first
        (:data:`STORE_ONLY_EVENT_KEYS`), so a comment body can never
        supply a stamp the reader would otherwise honour — above all the
        ``defect`` demotion marking the bridge counts as a real POST."""
        event = {key: value for key, value in stored.items()
                 if key not in STORE_ONLY_EVENT_KEYS}
        tag = stored.get("tag")
        trusted = False
        if _tag_is_wellformed(tag):
            seq = event.get("seq")
            if type(seq) is int:
                try:
                    expected = _event_tag(self._hmac_key(), ask_id, seq,
                                          event)
                except (ValueError, RecursionError):
                    # an event that cannot be canonicalised (panel B D1/D2:
                    # a float the strict encoder refuses, depth the dumper
                    # cannot take) is untrusted — never a raw exception
                    expected = None
                trusted = (expected is not None
                           and hmac.compare_digest(expected, str(tag)))
        event["trusted"] = trusted
        return event, trusted

    def _hmac_key(self) -> bytes:
        """The host-held key, loaded once.  A client configured with NO key
        fails closed the moment a key is actually needed (a tagged event is
        proof one exists); it never degrades into silent untrusted reads."""
        if self._hmac_key_bytes is None:
            if self._hmac_key_path is None:
                raise GblPaperclipError(
                    "HMAC_KEY_NOT_CONFIGURED",
                    "this client holds no hmac_key_path; a spec always "
                    "configures one")
            self._hmac_key_bytes = _load_or_create_hmac_key(
                self._hmac_key_path)
        return self._hmac_key_bytes

    # -- one request, no retries, no redirects, the URL law every time ---------

    def _checked_url(self, path: str) -> str:
        """The request URL, with the loopback law re-verified (panel B M6):
        scheme, host and port must still be the validated base's; the path
        is a single rooted, pre-quoted string that cannot escape."""
        if not path.startswith("/") or "//" in path:
            raise GblPaperclipTransportError("PATH_INVALID", path[:120])
        url = f"{self._base}{path}"
        split = urllib.parse.urlsplit(url)
        if (split.scheme != "http" or split.username or split.password
                or split.fragment or not split.hostname
                or split.hostname.lower() not in _LOOPBACK_HOSTS
                or split.port != self._port):
            raise GblPaperclipTransportError("URL_LAW_VIOLATION",
                                             url[:200])
        return url

    def _request(self, method: str, path: str,
                 body: Mapping[str, Any] | None = None) -> Any:
        data = (json.dumps(dict(body)).encode("utf-8")
                if body is not None else None)
        headers = dict(self._headers)
        if data is not None:
            headers["content-type"] = "application/json"
        request = urllib.request.Request(self._checked_url(path), data=data,
                                         method=method, headers=headers)
        try:
            with _OPENER.open(request, timeout=self._timeout) as response:
                raw = response.read(RESPONSE_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(300).decode("utf-8", "replace")
            except Exception:                        # noqa: BLE001
                detail = ""
            error: GblPaperclipError
            if 300 <= exc.code < 400:
                location = ""
                try:
                    location = (exc.headers.get("Location") or "")[:200]
                except Exception:                    # noqa: BLE001
                    location = ""
                error = GblPaperclipRedirectError(
                    f"HTTP_{exc.code}", f"redirect refused: {location}")
            elif 400 <= exc.code < 500:
                error = GblPaperclipClientError(f"HTTP_{exc.code}", detail)
            else:
                error = GblPaperclipServerError(f"HTTP_{exc.code}", detail)
            error.status = exc.code
            raise error from None
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as exc:
            # http.client.HTTPException (IncompleteRead, BadStatusLine, …)
            # is NOT an OSError — it must land here, not escape raw (M8).
            raise GblPaperclipTransportError(
                "TRANSPORT", type(exc).__name__) from None
        if len(raw) > RESPONSE_MAX_BYTES:
            raise GblPaperclipTransportError("RESPONSE_TOO_LARGE", path)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise GblPaperclipTransportError("UNPARSEABLE_BODY", path) from None


# ── Storage format helpers (strict both ways; issue text is untrusted) ──────


def _issue_title(envelope: Mapping[str, Any]) -> str:
    ask_id = envelope["ask_id"]
    title = " ".join(str(envelope.get("title") or "").split())
    budget = ISSUE_TITLE_MAX_CHARS - len(ask_id) - len("GBL [] ")
    if len(title) > budget:
        title = title[:budget - 1] + "…"
    return f"GBL [{ask_id}] {title}"


def _parse_ask_envelope(description: Any) -> dict[str, Any] | None:
    """The ask envelope embedded ANYWHERE in an issue description: the
    ``gbl-ask-v1`` marker, then the first balanced JSON object after it —
    appended or reflowed text around it is tolerated (panel B H4).  No
    marker → None (a foreign issue).  A marker whose payload cannot be
    parsed is NOT read as absence: that raises ``RECORD_INVALID``, because
    "absent" would mint a duplicate create."""
    if not isinstance(description, str):
        return None
    at = description.find(ASK_MARKER)
    if at < 0:
        return None
    brace = description.find("{", at + len(ASK_MARKER))
    if brace < 0:
        raise GblPaperclipError("RECORD_INVALID",
                                "marker without a JSON payload")
    end = _json_object_end(description, brace)
    if end < 0:
        raise GblPaperclipError("RECORD_INVALID", "unterminated JSON payload")
    try:
        value = json.loads(description[brace:end + 1],
                           parse_constant=_reject_json_constant)
    except (ValueError, RecursionError):
        # NaN/Infinity constants are not valid JSON in this format, and a
        # payload nested past the recursion limit is the description-side
        # twin of D2 — both refuse as the typed RECORD_INVALID (panel B
        # H4/D1/D2), never a raw exception.
        raise GblPaperclipError("RECORD_INVALID",
                                "payload is not JSON") from None
    if not isinstance(value, dict):
        raise GblPaperclipError("RECORD_INVALID", "payload is not an object")
    return value


def _json_object_end(text: str, start: int) -> int:
    """Index of the ``}`` closing the object opened at ``start`` (string- and
    escape-aware brace matching); -1 when unterminated."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _parse_event_body(body: str) -> dict[str, Any] | None:
    """Parse one event from a comment body: the event marker, then canonical
    JSON.  Foreign comments (human words, untrusted) → None, never parsed.
    A body that cannot be parsed — NaN/Infinity constants, nesting past the
    interpreter's recursion limit, anything past the size cap, any parse
    error — is ALSO None: an unparseable forgery is ignored (untrusted),
    never raised into the record's read/append paths (panel B D1/D2)."""
    prefix = f"{EVENT_MARKER} "
    if not body.startswith(prefix):
        return None
    payload = body[len(prefix):]
    if len(payload) > MAX_EVENT_JSON_CHARS:
        return None                      # oversized: foreign by definition
    try:
        value = json.loads(payload, parse_constant=_reject_json_constant)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


# ── The RF carrier's ask-child shape (GBL-RETURN outcomes 1/2/5) ────────────
#
# A delegate dispatch must land in the EXACT shape the installed RF carrier
# (tools/mmos_teammate/wake_carrier.py — READ-ONLY; never edited by this
# lane) already wakes on, so the target teammate's own carrier handles the
# child with no RF-side change.  Replicated field-for-field from that module:
# the marker formula (op_id / expected_ask_op), the end-of-description anchor
# (ASK_CHILD_MARKER_RE), the create payload, the blocked-parent PATCH with
# the SELF-owned unblock descriptor (the board refuses any other owner with
# 403), the parentId-filtered children walk (short pages are not the end;
# only an empty page is, bounded at ten), the truncation re-read (the marker
# sits at the very END of a description the list projection cuts at 1200
# chars), and the result-comment law (the assignee's own last non-machine
# comment, else a disclaimed fallback, else a pointer — a failed comments
# read FAILS, it is never "no answer").

RF_ASK_CHILD_MARKER_RE = re.compile(r"\[(pc-[A-Za-z0-9_.-]+-ask)\]\s*$")
RF_PC_MARKER_RE = re.compile(r"\[pc-[^\]\n]*\]")
RF_MACHINE_COMMENT_PREFIXES = ("[coding-job]", "[t2-carrier]")
CHILDREN_PAGE_LIMIT = 1000
MAX_CHILDREN_PAGES = 10
SCAN_DELEGATE_ASKS_MAX = 25      # the bounded lost-wake recovery read


def _rf_op_id(issue_id: Any, content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return f"pc-{issue_id}-{digest}"


def _rf_expected_ask_op(parent: Mapping[str, Any]) -> str:
    """The ask marker the RF carrier computes for a child of ``parent`` —
    the parent's SERVED title+description hashed, with the -ask suffix."""
    content = ((parent.get("title") or "") + "\n"
               + (parent.get("description") or ""))
    return f"{_rf_op_id(parent['id'], content)}-ask"


def _rf_ask_child_marker(text: Any) -> str | None:
    """The ask-child marker at the very END of a description, if any.  A
    ``[pc-…-ask]`` token anywhere else is foreign text (RF R2a finding 3)."""
    match = RF_ASK_CHILD_MARKER_RE.search(str(text or "").rstrip())
    return match.group(1) if match else None


def _rf_strip_markers(text: Any) -> str:
    """Caller text with any complete ``[pc-…]`` token removed, so nothing a
    caller wrote can pose as a carrier marker downstream (RF R2a finding 3)."""
    return RF_PC_MARKER_RE.sub("", str(text or "")).strip()


def _rf_recorded_blocker_ids(issue: Mapping[str, Any]) -> list[str]:
    """The blocker relation the board records for a parent, as a GET serves
    it: ``blockedBy`` summary rows first (the installed board never serves
    ``blockedByIssueIds`` on GET), the id list only as an echo fallback."""
    ids: list[str] = []
    for row in (issue.get("blockedBy") or []):
        if isinstance(row, dict) and row.get("id"):
            ids.append(str(row["id"]))
    ids.extend(str(iid) for iid in (issue.get("blockedByIssueIds") or [])
               if isinstance(iid, str))
    return list(dict.fromkeys(ids))


def _rf_is_machine_comment(body: str) -> bool:
    return body.startswith(RF_MACHINE_COMMENT_PREFIXES)


# ── Comment provenance (panel B M1/M2 client side; GBL lane consumes) ───────


_AUTHOR_KEYS = ("authorAgentId", "agentId", "authorId", "createdBy", "author")


def _add_comment_provenance(event: dict[str, Any],
                            row: Mapping[str, Any]) -> None:
    """Attach the comment's author and a stable total order key to the
    parsed event, so the bridge can trust only the bridge service agent's
    own comments and order events totally even on same-millisecond ties.
    The names follow the GBL lane's in-flight protocol round."""
    author = None
    for key in _AUTHOR_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            author = value
            break
    created = _parse_ts(row.get("createdAt"))
    event["comment_id"] = str(row.get("id") or "")
    event["comment_author"] = author
    event["comment_created_at"] = created.isoformat() if created else None
    event["comment_order"] = f"{event['comment_created_at'] or ''}|" \
                             f"{event['comment_id']}"


# ── The dev roster-entry helper (GBL-4's spec: the service agent) ────────────


def create_service_agent(base_url: str, company_id: str, *, name: str,
                         role: str = "service",
                         adapter_type: str = "process",
                         headers: Mapping[str, str] | None = None,
                         timeout_seconds: float = 15.0) -> dict[str, Any]:
    """Create the bridge service agent inside the given (dev) instance —
    the roster entry of BUILD_PLAN install step 3, in its dev-only shape:
    a process adapter with heartbeat off.  Returns the created row."""
    for label, value in (("name", name), ("role", role)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"agent {label} is required")
    client = PaperclipAskClient(base_url, company_id, "pending-service-agent",
                                headers=headers,
                                timeout_seconds=timeout_seconds)
    return client._request(
        "POST", f"/api/companies/{client._company_seg}/agents", {
            "name": name, "role": role, "adapterType": adapter_type,
            "runtimeConfig": {"heartbeat": {"enabled": False}},
        })
