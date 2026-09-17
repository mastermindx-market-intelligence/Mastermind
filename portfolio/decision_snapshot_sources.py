"""portfolio.decision_snapshot_sources — fixed, clock-honest V3 Decision Snapshot capture.

Bounded, read-only capture of the fixed internal Portfolio book state and the fixed
external Macro context artifacts consumed by the S0 Decision Snapshot. No persistence,
no model/provider/network access, and no caller-supplied path/root/url ever reaches a
filesystem expression — every source is a closed, checked-in literal path or a contract
key resolved through ``control_plane.contracts.contract``.

Two distinct clock laws (Task 2 controller ruling):
  * Internal, first-party canonical Portfolio files may use a *stable* file mtime as
    market-relevant ``known_at`` — proven by a dual-fstat stable read — labeled
    ``clock_basis=FILE_MTIME_FIRST_PARTY_STATE``. ``recorded_at`` (the caller's collector
    observation clock) is echoed onto every receipt as ``observed_at`` regardless.
  * External Macro filesystem mtime is NEVER promoted to market ``known_at``. It is
    recorded only as ``filesystem_observed_at``. A qualified ``known_at`` exists only when
    one of the source's own declared clock fields is present, in which case
    ``clock_basis=DECLARED_SOURCE_FIELD``; otherwise ``known_at=None``,
    ``clock_basis=UNQUALIFIED_EXTERNAL_CLOCK``, ``status=UNQUALIFIED_CLOCK``.

The internal first-party settlement-receipt *directory* is read the same way: a no-follow,
stable, bounded manifest of per-entry names and mtimes. Each entry is independently
partitioned against ``decision_cutoff`` at the same second-precision law the file sources
use: an entry at or before the cutoff is eligible and may enter rows, counts, the artifact
digest, and the correction generation; an entry after the cutoff is completely invisible to
this receipt's bytes — no row, no count, no gap, no coverage effect, no digest or generation
input, and no known_at effect, so adding, editing, or removing a future entry can never
change a snapshot already composed for an earlier cutoff. ``known_at``/
``filesystem_observed_at`` describe only the newest *eligible* entry — never the directory's
own mtime. Zero eligible entries — whether the directory is absent, genuinely empty, or holds
only post-cutoff entries — is one stable optional-absence representation
(``status=ABSENT_OPTIONAL``), never an ``AVAILABLE`` claim founded on the directory's own
mtime. ``status=AVAILABLE`` is a point-in-time claim everywhere — the closed contract refuses
it without a qualified non-null ``known_at``.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from portfolio import decision_snapshot_contracts as c
from portfolio import registry

_ROOT = Path(__file__).resolve().parent.parent
_V = _ROOT / "vendor" / "macro"

MAX_SOURCE_BYTES = c.MAX_SOURCE_BYTES
MAX_JSONL_TAIL_ROWS = c.MAX_JSONL_TAIL_ROWS
MAX_SECTION_ROWS = c.MAX_SECTION_ROWS
MAX_MANIFEST_METADATA_BYTES = c.MAX_MANIFEST_METADATA_BYTES

_EMPTY_DIGEST = "sha256:" + hashlib.sha256(b"").hexdigest()

_CORRECTION_DECLARED_FIELDS = ("revision", "bundle_id", "content_generation")

_EMPTY_PROJECTION_DETAIL = (
    "artifact is present and parseable but declares none of the fields this projection "
    "requires; absent content is not an empty complete source"
)
_PARTIAL_HELD_TICKER_DETAIL = (
    "held-ticker basis is incomplete, so this held-ticker-filtered projection cannot be "
    "reported as a complete view of the book"
)

# Projections whose rows are filtered by the book's derived held tickers. A book that
# could not be fully projected silently narrows every one of them.
_HELD_TICKER_PROJECTIONS = frozenset({
    "factor_betas", "prophet", "neural_web", "portfolio_context", "held_ticker_bundle",
})


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    contract_key: str
    domains: tuple[str, ...]
    required: bool
    authority_class: str
    rights_class: str
    projection: str
    known_at_fields: tuple[str, ...] = ()
    observed_at_fields: tuple[str, ...] = ()
    as_of_fields: tuple[str, ...] = ()
    generated_at_fields: tuple[str, ...] = ()
    schema_fields: tuple[str, ...] = ("schema",)
    definition_fields: tuple[str, ...] = ("definition_id",)


EXTERNAL_SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        "macro.risk_envelope",
        "portfolio-v3-risk-envelope-settled",
        ("risk_truth",),
        True,
        "MARKET_RISK_CONTEXT",
        "FIRST_PARTY_INTERNAL",
        "risk_envelope",
        known_at_fields=("known_at", "available_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at", "produced_at"),
    ),
    SourceSpec(
        "macro.regime",
        "regime-latest",
        ("market_structure",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "regime",
        known_at_fields=("known_at", "available_at", "generated_at"),
        as_of_fields=("as_of", "asof", "date"),
        generated_at_fields=("generated_at", "produced_at"),
    ),
    SourceSpec(
        "macro.sector_rotation",
        "portfolio-v3-sector-central",
        ("market_structure",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "receipt_only_pr548",
        as_of_fields=("as_of",),
    ),
    SourceSpec(
        "macro.r_orth",
        "portfolio-v3-covariance-spine",
        ("independence",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "covariance_spine",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of",),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.factor_betas",
        "portfolio-v3-factor-betas",
        ("factor_risk",),
        False,
        "MEASUREMENT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "factor_betas",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.prophet",
        "portfolio-v3-prophet-index",
        ("candidate_geometry",),
        False,
        "DISPLAY_ONLY",
        "FIRST_PARTY_INTERNAL",
        "prophet",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.neural_web",
        "site-neural-web-mastermind-context",
        ("relationships",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "neural_web",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of",),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.portfolio_context",
        "portfolio-v3-portfolio-context",
        ("fundamental_state", "positioning", "event_state", "priceability"),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "portfolio_context",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.intelligence",
        "site-intelligence-by-ticker",
        ("fundamental_state", "positioning", "event_state"),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.altdata",
        "site-altdata-by-ticker",
        ("positioning",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
    SourceSpec(
        "macro.news",
        "site-news-by-ticker",
        ("event_state",),
        False,
        "CONTEXT_ONLY",
        "FIRST_PARTY_INTERNAL",
        "held_ticker_bundle",
        known_at_fields=("known_at", "generated_at"),
        as_of_fields=("as_of", "asof"),
        generated_at_fields=("generated_at",),
    ),
)

# Fixed internal book-state files, relative to the book's data directory.
# (source_id, relative_path, required, section_id, projection)
_INTERNAL_FILE_SPECS: tuple[tuple[str, str, bool, str, str], ...] = (
    ("book.account", "account.json", True, "book_truth", "account"),
    ("book.latest", "latest.json", False, "book_truth", "latest"),
    ("book.pending_orders", "pending_orders.json", False, "book_truth", "raw_object"),
    ("book.pending_target", "pending_target.json", False, "book_truth", "raw_object"),
    ("book.positions_ledger", "positions_ledger.json", False, "historical_memory", "raw_object"),
)
_INTERNAL_JSONL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("book.decisions", "decisions.jsonl", "historical_memory"),
    ("book.fills", "fills.jsonl", "historical_memory"),
)
_SETTLEMENT_RECEIPTS_SOURCE_ID = "book.settlement_receipts"
_SETTLEMENT_RECEIPTS_DIR = "settlement_receipts"


# ---------------------------------------------------------------------------
# Digests, clocks, gaps
# ---------------------------------------------------------------------------

def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _utc_from_mtime_ns(nanoseconds: int) -> str:
    """Floor an internal first-party ``st_mtime_ns`` to whole seconds in integer space.

    ``nanoseconds`` is a Python int of magnitude ~1.8e18, well beyond float64's ~2^53
    exact-integer range; a float division (``nanoseconds / 1e9``) can round the fractional
    part up across a second boundary before ``int()`` truncates it, so a file written near
    the end of a second can appear to have landed in the next one. Integer floor division
    never loses precision.
    """
    return datetime.fromtimestamp(nanoseconds // 1_000_000_000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _canonical_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return c.parse_utc_timestamp(value, field="declared_clock")
    except c.DecisionSnapshotContractError:
        return None


def _first_declared(payload: Any, fields: tuple[str, ...]) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for name in fields:
        normalized = _canonical_or_none(payload.get(name))
        if normalized is not None:
            return normalized
    return None


def _first_present_str(payload: Any, fields: tuple[str, ...]) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for name in fields:
        value = payload.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _is_usable_declared_generation_value(value: Any) -> bool:
    """True for a scalar the declared-generation rule may hash: a non-empty, printable
    string, an int, or a finite float. Booleans, empty/control-bearing strings, non-finite
    floats, mappings, and sequences are all rejected."""
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value) and value.isprintable()
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _correction_generation(payload: Any, digest: str) -> str:
    """Digest-shaped correction generation. When the source declares a usable scalar
    ``revision``/``bundle_id``/``content_generation``, hash the declared field/value together
    with the current ``artifact_digest`` — so a content change always changes the generation
    even under an unchanged declared revision. Otherwise fall back to the artifact digest."""
    if isinstance(payload, Mapping):
        for name in _CORRECTION_DECLARED_FIELDS:
            if name not in payload:
                continue
            value = payload[name]
            if not _is_usable_declared_generation_value(value):
                continue
            return c.content_digest({
                "declared_field": name,
                "declared_value": value,
                "artifact_digest": digest,
            })
    return digest


def _unavailable_generation(
    *,
    source_id: str,
    status: str,
    error_code: str | None,
    size: int,
    stat_result: Any | None = None,
) -> str:
    """Status-bearing correction generation for a source whose stable bytes are unavailable.

    The generation set is what ``create_snapshot`` compares to decide whether a same-cutoff
    retry may reuse an existing snapshot. A constant placeholder therefore collapses every
    unavailable state onto one identity: an optional source going ABSENT -> OVERSIZE, or a
    required source going MISSING -> INVALID, would reuse the prior snapshot and report
    stale evidence as current.

    Bytes are never read to break that tie (an oversize file must not be hashed). The
    generation is derived from exactly the bounded metadata that *is* trustworthy: the
    status, the error code, the advertised byte count, and — when a stat survived — the
    exact nanosecond mtime and the dev/inode identity. Two materially different unavailable
    states can then never present one generation, while an unchanged unavailable state
    re-derives the same generation on every retry.
    """
    identity: dict[str, Any] = {
        "generation_kind": "SOURCE_UNAVAILABLE",
        "source_id": source_id,
        "status": status,
        "error_code": error_code,
        "bytes": int(size),
        "mtime_ns": None,
        "device": None,
        "inode": None,
    }
    if stat_result is not None:
        identity["mtime_ns"] = int(getattr(stat_result, "st_mtime_ns", 0))
        identity["device"] = int(getattr(stat_result, "st_dev", 0))
        identity["inode"] = int(getattr(stat_result, "st_ino", 0))
    return c.content_digest(identity)


def _gap(
    code: str,
    *,
    source_id: str | None = None,
    section_id: str | None = None,
    owner: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "source_id": source_id,
        "section_id": section_id,
        "owner": owner,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Receipt scaffold
# ---------------------------------------------------------------------------

def _base_receipt(
    *,
    source_id: str,
    domains: Sequence[str],
    producer: str,
    owner: str,
    artifact: str,
    rights_class: str,
    authority_class: str,
    required: bool,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "schema": c.SOURCE_RECEIPT_SCHEMA,
        "source_id": source_id,
        "domains": list(domains),
        "producer": producer,
        "owner": owner,
        "artifact": artifact,
        "source_schema": None,
        "schema_version": None,
        "definition_id": None,
        "artifact_digest": _EMPTY_DIGEST,
        "observed_at": observed_at,
        "known_at": None,
        "as_of": None,
        "generated_at": None,
        "filesystem_observed_at": None,
        "correction_generation": _EMPTY_DIGEST,
        "freshness_state": "UNKNOWN",
        "coverage_state": "UNKNOWN",
        "rights_class": rights_class,
        "authority_class": authority_class,
        "status": "MISSING",
        "required": required,
        "bytes": 0,
        "rows_total": 0,
        "rows_returned": 0,
        "omitted_rows": 0,
        "clock_basis": "UNKNOWN",
        "error_code": None,
    }


def _section(section_id: str, source_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "schema": c.SECTION_SCHEMA,
        "section_id": section_id,
        "coverage_state": "COMPLETE",
        "source_ids": list(source_ids),
        "rows_total": 0,
        "rows_returned": 0,
        "omitted_rows": 0,
        "rows": [],
        "gaps": [],
    }


_COVERAGE_RANK = {"BLOCKED": 3, "PARTIAL": 2, "UNKNOWN": 1, "COMPLETE": 0}


def _worse_coverage(a: str, b: str) -> str:
    return a if _COVERAGE_RANK[a] >= _COVERAGE_RANK[b] else b


def _append_capped(section: dict[str, Any], rows: list[Any]) -> int:
    """Append ``rows`` to ``section["rows"]``, capping at ``MAX_SECTION_ROWS``.

    Returns the number of rows dropped by the cap so the caller can fold that count into
    ``omitted_rows`` — a cap drop must never vanish from coverage.
    """
    combined = section["rows"] + rows
    kept = combined[:MAX_SECTION_ROWS]
    section["rows"] = kept
    return len(combined) - len(kept)


def _merge_into_section(section: dict[str, Any], *, rows: list[Any], coverage_state: str,
                         omitted_rows: int, gaps: list[dict[str, Any]]) -> None:
    """Fold one source's contribution into a section, keeping counts self-consistent.

    ``rows_returned`` and ``rows_total`` are always derived from the section's own row list
    and cumulative omissions — never independently summed — so a section can never carry
    rows its counts deny, or drop rows its counts never report.
    """
    cap_dropped = _append_capped(section, rows)
    section["coverage_state"] = _worse_coverage(section["coverage_state"], coverage_state)
    section["omitted_rows"] += omitted_rows + cap_dropped
    section["rows_returned"] = len(section["rows"])
    section["rows_total"] = section["rows_returned"] + section["omitted_rows"]
    section["gaps"].extend(gaps)


# ---------------------------------------------------------------------------
# Bounded fixed-path readers
# ---------------------------------------------------------------------------

def _read_json_bytes(path: Path) -> tuple[bytes | None, int, str | None, Any | None]:
    """No-follow, single-descriptor bounded read for external (Macro) artifacts.

    Not required to be *stable* (the external producer's write discipline is not this
    module's to enforce), but the reported size, bytes, and stat identity must all describe
    the same open file: one descriptor, opened refusing to follow a final-component symlink
    (closing the check-then-open race against ``_resolve_external_path``'s earlier proof),
    fstat'd for the bounded size check, then read from that same descriptor. Returns
    ``(raw, size, error_code, stat_result)`` — the caller derives ``filesystem_observed_at``
    from ``stat_result``, never from a separate, later stat call.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        return None, 0, "MISSING", None
    except OSError:
        return None, 0, "INVALID", None
    try:
        stat_result = os.fstat(fd)
        size = stat_result.st_size
        if size > MAX_SOURCE_BYTES:
            return None, size, "OVERSIZE", stat_result
        try:
            raw = os.read(fd, size)
        except OSError:
            return None, size, "INVALID", stat_result
        return raw, size, None, stat_result
    finally:
        os.close(fd)


def _stable_first_party_read(path: Path) -> tuple[bytes | None, Any | None, int, str | None]:
    """Dual-fstat stable read for internal, first-party canonical Portfolio files.

    Returns (raw, stat_after, size, error_code). A device/inode/size/mtime_ns mismatch
    between the pre- and post-read fstat means the file changed during the read; no rows
    are ever produced from an unstable read.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except FileNotFoundError:
        return None, None, 0, "MISSING"
    except OSError:
        return None, None, 0, "INVALID"
    try:
        pre = os.fstat(fd)
        size = pre.st_size
        if size > MAX_SOURCE_BYTES:
            return None, pre, size, "OVERSIZE"
        try:
            raw = os.read(fd, size)
        except OSError:
            return None, pre, size, "INVALID"
        post = os.fstat(fd)
        stable = (
            pre.st_dev == post.st_dev
            and pre.st_ino == post.st_ino
            and pre.st_size == post.st_size
            and pre.st_mtime_ns == post.st_mtime_ns
        )
        if not stable:
            return None, post, size, "SOURCE_CHANGED_DURING_READ"
        return raw, post, size, None
    finally:
        os.close(fd)


def _reject_non_finite_constant(token: str) -> float:
    raise ValueError(f"non-finite JSON constant {token!r}")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number {text!r}")
    return value


def _loads_finite(text: str) -> Any:
    """``json.loads`` closed against non-finite numbers.

    Python's decoder accepts bare ``NaN``/``Infinity``/``-Infinity`` by default, and an
    ordinary-looking overflow literal such as ``1e400`` also decodes to ``inf``. The
    canonical serializer this module's output must survive is ``allow_nan=False``, so any
    non-finite value that reaches a projected row raises a bare ``ValueError`` at seal time
    — outside the contract's error type, producing no receipt and no gap, and collapsing
    the whole composition into an opaque failure. A non-finite number is a malformed
    artifact; it is rejected here, at ingestion, where the source law can degrade one
    source to MALFORMED and let composition continue.
    """
    return json.loads(
        text, parse_constant=_reject_non_finite_constant, parse_float=_finite_float
    )


def _parse_json(raw: bytes) -> tuple[Any | None, str | None]:
    try:
        return _loads_finite(raw.decode("utf-8")), None
    except UnicodeDecodeError:
        # A subclass of ValueError, so it must be caught before the broader clause below.
        return None, "MALFORMED"
    except ValueError:
        # json.JSONDecodeError subclasses ValueError, as do the non-finite rejections above.
        return None, "MALFORMED"


_MANIFEST_NAME_OVERHEAD_BYTES = 3  # JSON quoting plus one separator per encoded name


def _stable_directory_manifest(directory: Path, cutoff: str) -> dict[str, Any]:
    """Fixed-path, no-follow, stable, cutoff-partitioned first-party directory-manifest read.

    Returns ``{"entries": sorted_name_mtime_pairs, "dir_mtime_ns": int | None,
    "error_code": str | None}`` — ``entries`` is a list of ``(name, st_mtime_ns)`` tuples
    sorted by name, one per *eligible* ``.json`` entry: every entry whose own mtime is after
    ``cutoff`` is dropped immediately, before either fail-closed check below ever sees it, so
    a post-cutoff entry can be a symlink, a directory, or one of an unbounded flood of names
    with zero effect on this manifest. Only the eligible census is ever checked for
    regular-file refusal or summed against the metadata ceiling — an *eligible* symlink or
    non-regular entry still fails the whole manifest closed, exactly as before.
    ``dir_mtime_ns`` is the directory's own stable mtime, reported only as a stability
    diagnostic — it is never mixed into an entry's mtime, and the caller must never derive a
    ``known_at`` or generation input from it: a directory holding zero eligible entries (be
    it absent, genuinely empty, or holding only post-cutoff entries) is one optional-absence
    state, and the directory's own mtime is not qualified evidence for any of the three.

    ``is_dir()``/``glob()`` follow symlinks, expose no clock, and cannot detect a directory
    mutating underneath the enumeration — so the manifest they produce is neither
    point-in-time nor closed. This read instead:

    * rejects a symlinked or non-directory source before opening anything, then opens the
      directory itself with ``O_DIRECTORY|O_NOFOLLOW`` and enumerates through that fd, so a
      path component swapped mid-read cannot redirect it;
    * lstats every matching entry first (never following it) and drops it before any other
      check the instant its own mtime proves it is after ``cutoff``;
    * refuses any *eligible* entry that is a symlink or not a regular file, failing closed
      rather than returning partial truth about a directory it does not understand;
    * bounds total encoded filename metadata for the eligible census only, failing closed on
      overflow — a manifest is metadata about an unbounded directory, and an unbounded name
      census is not bounded capture;
    * re-fstats the directory afterwards and rejects any identity or mtime change during
      enumeration;
    * captures each eligible entry's own mtime untouched by the directory's mtime — the
      directory's own mtime moves on any add/remove/rename and is never a stand-in for a
      specific receipt's clock.
    """
    def _failed(code: str) -> dict[str, Any]:
        return {"entries": [], "dir_mtime_ns": None, "error_code": code}

    try:
        dir_lstat = os.lstat(str(directory))
    except FileNotFoundError:
        return _failed("MISSING")
    except OSError:
        return _failed("INVALID")
    if stat.S_ISLNK(dir_lstat.st_mode):
        return _failed("SETTLEMENT_DIR_SYMLINK")
    if not stat.S_ISDIR(dir_lstat.st_mode):
        return _failed("SETTLEMENT_DIR_NOT_A_DIRECTORY")

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        dir_fd = os.open(str(directory), flags)
    except FileNotFoundError:
        return _failed("MISSING")
    except OSError:
        return _failed("INVALID")
    try:
        pre = os.fstat(dir_fd)
        entries: list[tuple[str, int]] = []
        encoded_bytes = 0
        with os.scandir(dir_fd) as scanned:
            for entry in scanned:
                if not entry.name.endswith(".json"):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    return _failed("SETTLEMENT_ENTRY_NOT_REGULAR")
                if _utc_from_mtime_ns(info.st_mtime_ns) > cutoff:
                    # Post-cutoff: this entry is completely invisible to the manifest. It
                    # must never reach the type refusal or the metadata ceiling below —
                    # neither may ever be tripped by evidence this cutoff never saw.
                    continue
                if entry.is_symlink() or not stat.S_ISREG(info.st_mode):
                    return _failed("SETTLEMENT_ENTRY_NOT_REGULAR")
                encoded_bytes += len(entry.name.encode("utf-8")) + _MANIFEST_NAME_OVERHEAD_BYTES
                if encoded_bytes > MAX_MANIFEST_METADATA_BYTES:
                    return _failed("SETTLEMENT_MANIFEST_TOO_LARGE")
                entries.append((entry.name, info.st_mtime_ns))
        post = os.fstat(dir_fd)
        if (
            pre.st_dev != post.st_dev
            or pre.st_ino != post.st_ino
            or pre.st_mtime_ns != post.st_mtime_ns
        ):
            return _failed("SOURCE_CHANGED_DURING_READ")
    finally:
        os.close(dir_fd)
    return {
        "entries": sorted(entries, key=lambda item: item[0]),
        "dir_mtime_ns": pre.st_mtime_ns,
        "error_code": None,
    }


def _settlement_generation(*, status: str, eligible: Sequence[Mapping[str, Any]]) -> str:
    """Correction generation for the settlement-receipts manifest.

    Folds ``status`` together with the eligible ``(name, mtime_ns)`` metadata — never a
    future-excluded entry, which must have zero effect on this generation — so a same-cutoff
    retry reuses the prior snapshot exactly when the eligible set is byte-for-byte unchanged:
    an eligible receipt's name or mtime changing always mints a new generation, and a
    post-cutoff receipt appearing, changing, or disappearing never does. The directory's own
    mtime is never an input here either.
    """
    return c.content_digest({
        "generation_kind": "SETTLEMENT_MANIFEST",
        "status": status,
        "eligible": sorted(
            ({"name": entry["name"], "mtime_ns": int(entry["mtime_ns"])} for entry in eligible),
            key=lambda entry: entry["name"],
        ),
    })


def _parse_jsonl_tail(raw: bytes, *, max_rows: int = MAX_JSONL_TAIL_ROWS) -> dict[str, Any]:
    """Parse a bounded JSONL tail from bytes already produced by a single stable read.

    Never re-reads or re-stats the source: rows, the caller's digest, and the caller's
    file-write clock must all describe the exact same bytes. Invalid lines increment
    ``omitted_rows`` rather than vanishing from coverage — including a row carrying a
    non-finite number, which the canonical serializer would refuse at seal time.
    """
    text = raw.decode("utf-8", errors="replace")
    valid: list[Any] = []
    omitted = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = _loads_finite(line)
        except ValueError:
            omitted += 1
            continue
        if not isinstance(obj, dict):
            omitted += 1
            continue
        valid.append(obj)
    tail = valid[-max_rows:] if max_rows else []
    return {
        "rows": tail,
        "rows_total": len(valid) + omitted,
        "rows_returned": len(tail),
        "omitted_rows": omitted + (len(valid) - len(tail)),
    }


# ---------------------------------------------------------------------------
# Internal book-state capture
# ---------------------------------------------------------------------------

def _book_dir(book: str) -> Path:
    """The book's data directory, remapped under this module's own (test-patchable) root.

    ``registry.data_dir`` remains the single source of truth for the book-id allowlist and
    the canonical relative layout; it fails closed (``ValueError``) on an unknown id. This
    module never reads through the absolute path it returns — it strips the real repo root
    registry.py resolves against and re-anchors the same relative subpath under its own
    module-owned ``_ROOT``, which is what tests are allowed to redirect.
    """
    canonical_absolute = registry.data_dir(book)
    registry_root_now = Path(getattr(registry, "_ROOT", _ROOT))
    relative = canonical_absolute.relative_to(registry_root_now)
    return _ROOT / relative


def _project_account(payload: Any) -> tuple[dict[str, Any] | None, int, bool]:
    """Project the account row, returning ``(row, dropped_position_entries, container_malformed)``.

    A position entry whose value is not an object cannot be projected. It is *counted* and
    surfaced by the caller as a bounded gap rather than silently discarded: book truth is
    required evidence, and a position that vanishes both understates the book and narrows
    every held-ticker-filtered external projection derived from it.

    ``positions`` itself must be an explicit mapping — including ``{}`` for a genuinely
    empty book. A missing key, ``null``, a list, a string, a number, or any other unusable
    container is not an implicit empty book: it is an unknown one, so it is never silently
    treated as ``{}``.
    """
    if not isinstance(payload, Mapping):
        return None, 0, False
    row: dict[str, Any] = {}
    if "cash" in payload:
        row["cash"] = payload.get("cash")
    if "starting_nav" in payload:
        row["starting_nav"] = payload.get("starting_nav")
    dropped = 0
    positions = payload.get("positions")
    if isinstance(positions, Mapping):
        projected_positions: dict[str, Any] = {}
        for ticker, pos in positions.items():
            if not isinstance(pos, Mapping):
                dropped += 1
                continue
            projected_positions[ticker] = {
                field: pos[field]
                for field in ("shares", "avg_cost", "identity_status", "holding_mark_source", "weight")
                if field in pos
            }
        row["positions"] = projected_positions
        return row, dropped, False
    return row, dropped, True


def _project_latest(payload: Any) -> tuple[dict[str, Any] | None, int, bool]:
    """Project the latest-marks row, returning ``(row, dropped_position_entries, container_malformed)``.

    An entry that is not an object, or that carries no non-empty ticker, cannot identify a
    holding; it is counted and reported exactly like a malformed account position.

    ``positions`` itself must be an explicit list — including ``[]`` for a genuinely empty
    marks set — for the same honesty reason as the account projection, without promoting
    this optional source to authoritative: a malformed container here degrades this
    source's own coverage, but never substitutes for ``book.account`` as the held-ticker
    basis.
    """
    if not isinstance(payload, Mapping):
        return None, 0, False
    row: dict[str, Any] = {}
    if "as_of" in payload:
        row["as_of"] = payload.get("as_of")
    dropped = 0
    positions = payload.get("positions")
    if isinstance(positions, list):
        projected: list[dict[str, Any]] = []
        for pos in positions:
            if not isinstance(pos, Mapping):
                dropped += 1
                continue
            ticker = pos.get("ticker")
            if not isinstance(ticker, str) or not ticker:
                dropped += 1
                continue
            projected.append({
                field: pos[field]
                for field in ("ticker", "weight", "identity_status", "holding_mark_source")
                if field in pos
            })
        row["positions"] = projected
        return row, dropped, False
    return row, dropped, True


def capture_book_state(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]:
    observed_at = c.parse_utc_timestamp(recorded_at, field="recorded_at")
    cutoff = c.parse_utc_timestamp(decision_cutoff, field="decision_cutoff")
    book_dir = _book_dir(book)

    sources_out: list[dict[str, Any]] = []
    gaps_out: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {
        "book_truth": _section("book_truth", []),
        "historical_memory": _section("historical_memory", []),
    }
    # The canonical held-ticker basis: only ``book.account``/``book.latest`` rows, keyed by
    # source_id. Populated *only* on their own successful projection path below — never
    # from a raw-object row (e.g. pending_orders/pending_target) that happens to carry an
    # unrelated ``positions`` key, and never from a MISSING/MALFORMED/FUTURE_AT_CUTOFF state.
    book_position_rows: list[tuple[str, dict[str, Any]]] = []

    def emit(section_id: str, source_id: str) -> None:
        sections[section_id]["source_ids"].append(source_id)

    for source_id, rel_path, required, section_id, projection in _INTERNAL_FILE_SPECS:
        path = book_dir / rel_path
        receipt = _base_receipt(
            source_id=source_id,
            domains=(section_id,),
            producer="mastermind_portfolio",
            owner="portfolio_desk",
            artifact=f"data/portfolios/{book}/{rel_path}",
            rights_class="FIRST_PARTY_INTERNAL",
            authority_class="BOOK_STATE",
            required=required,
            observed_at=observed_at,
        )
        raw, stat_after, size, error_code = _stable_first_party_read(path)
        receipt["bytes"] = size
        emit(section_id, source_id)

        if error_code == "MISSING":
            receipt["status"] = "ABSENT_OPTIONAL" if not required else "MISSING"
            receipt["coverage_state"] = "COMPLETE" if not required else "PARTIAL"
            receipt["correction_generation"] = _unavailable_generation(
                source_id=source_id, status=receipt["status"], error_code=error_code, size=size,
            )
            if required:
                gaps_out.append(_gap("MISSING_REQUIRED_INTERNAL_SOURCE", source_id=source_id,
                                      section_id=section_id))
                _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                     omitted_rows=0, gaps=[])
            sources_out.append(receipt)
            continue

        if error_code in ("OVERSIZE", "INVALID", "SOURCE_CHANGED_DURING_READ"):
            receipt["status"] = "INVALID" if error_code == "SOURCE_CHANGED_DURING_READ" else error_code
            receipt["error_code"] = error_code
            receipt["coverage_state"] = "BLOCKED"
            receipt["correction_generation"] = _unavailable_generation(
                source_id=source_id, status=receipt["status"], error_code=error_code,
                size=size, stat_result=stat_after,
            )
            if stat_after is not None:
                receipt["filesystem_observed_at"] = _utc_from_mtime_ns(stat_after.st_mtime_ns)
            gaps_out.append(_gap(error_code, source_id=source_id, section_id=section_id))
            _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                 omitted_rows=0,
                                 gaps=[_gap(error_code, source_id=source_id, section_id=section_id)])
            sources_out.append(receipt)
            continue

        # Stable read succeeded.
        mtime_utc = _utc_from_mtime_ns(stat_after.st_mtime_ns)
        receipt["known_at"] = mtime_utc
        receipt["filesystem_observed_at"] = mtime_utc
        receipt["clock_basis"] = "FILE_MTIME_FIRST_PARTY_STATE"
        receipt["artifact_digest"] = _digest(raw)

        if mtime_utc > cutoff:
            receipt["status"] = "FUTURE_AT_CUTOFF"
            receipt["coverage_state"] = "BLOCKED"
            # The clock is the only thing that moved the bytes from eligible to future (or
            # back): a generation keyed on the bare digest is blind to that, so it must also
            # carry the status and the exact mtime that produced it.
            receipt["correction_generation"] = c.content_digest({
                "generation_kind": "SOURCE_BYTES",
                "status": receipt["status"],
                "artifact_digest": receipt["artifact_digest"],
                "mtime_ns": int(stat_after.st_mtime_ns),
            })
            gap = _gap("FUTURE_AT_CUTOFF", source_id=source_id, section_id=section_id)
            gaps_out.append(gap)
            _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                 omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        payload, parse_error = _parse_json(raw)
        if parse_error:
            receipt["status"] = "MALFORMED"
            receipt["error_code"] = parse_error
            receipt["coverage_state"] = "PARTIAL" if not required else "BLOCKED"
            # Stable bytes exist even though they do not parse: the generation must track
            # them and the clock, or two different malformed bodies — or the same malformed
            # body before and after crossing the cutoff — read as one unchanged state.
            receipt["correction_generation"] = c.content_digest({
                "generation_kind": "SOURCE_BYTES",
                "status": receipt["status"],
                "artifact_digest": receipt["artifact_digest"],
                "mtime_ns": int(stat_after.st_mtime_ns),
            })
            gaps_out.append(_gap(parse_error, source_id=source_id, section_id=section_id))
            _merge_into_section(sections[section_id], rows=[], coverage_state=receipt["coverage_state"],
                                 omitted_rows=0,
                                 gaps=[_gap(parse_error, source_id=source_id, section_id=section_id)])
            sources_out.append(receipt)
            continue

        receipt["correction_generation"] = _correction_generation(payload, receipt["artifact_digest"])
        as_of = _first_present_str(payload, ("as_of", "asof"))
        if as_of is not None:
            receipt["as_of"] = as_of
        receipt["status"] = "AVAILABLE"

        dropped_positions = 0
        positions_container_malformed = False
        if projection == "account":
            row, dropped_positions, positions_container_malformed = _project_account(payload)
            content_present = bool(row)
        elif projection == "latest":
            row, dropped_positions, positions_container_malformed = _project_latest(payload)
            content_present = bool(row)
        else:
            # A raw-object projection *is* the whole artifact, so a legitimately present
            # empty object is complete content, not absent content.
            row = payload if isinstance(payload, (Mapping, list)) else {"value": payload}
            content_present = True

        rows = [row] if (content_present and row is not None) else []
        if projection in ("account", "latest") and content_present and row is not None:
            book_position_rows.append((source_id, row))
        coverage = "COMPLETE"
        source_gaps: list[dict[str, Any]] = []
        if not content_present:
            coverage = "PARTIAL"
            source_gaps.append(_gap("EMPTY_PROJECTION", source_id=source_id,
                                     section_id=section_id, detail=_EMPTY_PROJECTION_DETAIL))
        if positions_container_malformed:
            coverage = "PARTIAL"
            # The whole ``positions`` value is unusable (missing, null, wrong type, ...),
            # not merely one bad entry inside a valid mapping — a distinct, more specific
            # code from MALFORMED_POSITION_ENTRY so a consumer can tell "we don't know the
            # book" from "we know most of the book".
            source_gaps.append(_gap(
                "MALFORMED_POSITIONS_CONTAINER", source_id=source_id, section_id=section_id,
                detail="positions is missing or not a usable container: held-ticker basis unknown",
            ))
        if dropped_positions:
            coverage = "PARTIAL"
            source_gaps.append(_gap(
                "MALFORMED_POSITION_ENTRY", source_id=source_id, section_id=section_id,
                # A bounded count and a fixed reason — never the excluded entries' own
                # keys or values, which are arbitrary payload text.
                detail=(
                    f"{dropped_positions} position "
                    f"{'entry' if dropped_positions == 1 else 'entries'} excluded: "
                    "not a usable position object"
                ),
            ))
        receipt["coverage_state"] = coverage
        receipt["rows_total"] = len(rows)
        receipt["rows_returned"] = len(rows)
        gaps_out.extend(source_gaps)
        _merge_into_section(sections[section_id], rows=rows, coverage_state=coverage,
                             omitted_rows=0, gaps=list(source_gaps))
        sources_out.append(receipt)

    for source_id, rel_path, section_id in _INTERNAL_JSONL_SPECS:
        path = book_dir / rel_path
        receipt = _base_receipt(
            source_id=source_id,
            domains=(section_id,),
            producer="mastermind_portfolio",
            owner="portfolio_desk",
            artifact=f"data/portfolios/{book}/{rel_path}",
            rights_class="FIRST_PARTY_INTERNAL",
            authority_class="BOOK_STATE",
            required=False,
            observed_at=observed_at,
        )
        sections.setdefault(section_id, _section(section_id, []))
        emit(section_id, source_id)

        raw, stat_after, size, error_code = _stable_first_party_read(path)
        receipt["bytes"] = size

        if error_code == "MISSING":
            receipt["status"] = "ABSENT_OPTIONAL"
            receipt["coverage_state"] = "COMPLETE"
            receipt["correction_generation"] = _unavailable_generation(
                source_id=source_id, status="ABSENT_OPTIONAL", error_code=error_code, size=size,
            )
            sources_out.append(receipt)
            continue

        if error_code in ("OVERSIZE", "INVALID", "SOURCE_CHANGED_DURING_READ"):
            receipt["status"] = "INVALID" if error_code == "SOURCE_CHANGED_DURING_READ" else error_code
            receipt["error_code"] = error_code
            receipt["coverage_state"] = "BLOCKED"
            receipt["correction_generation"] = _unavailable_generation(
                source_id=source_id, status=receipt["status"], error_code=error_code,
                size=size, stat_result=stat_after,
            )
            if stat_after is not None:
                receipt["filesystem_observed_at"] = _utc_from_mtime_ns(stat_after.st_mtime_ns)
            gaps_out.append(_gap(error_code, source_id=source_id, section_id=section_id))
            _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                 omitted_rows=0,
                                 gaps=[_gap(error_code, source_id=source_id, section_id=section_id)])
            sources_out.append(receipt)
            continue

        # Stable read succeeded — rows, digest, and mtime all come from the same bytes.
        mtime_utc = _utc_from_mtime_ns(stat_after.st_mtime_ns)
        receipt["known_at"] = mtime_utc
        receipt["filesystem_observed_at"] = mtime_utc
        receipt["clock_basis"] = "FILE_MTIME_FIRST_PARTY_STATE"
        receipt["artifact_digest"] = _digest(raw)

        if mtime_utc > cutoff:
            receipt["status"] = "FUTURE_AT_CUTOFF"
            receipt["coverage_state"] = "BLOCKED"
            receipt["correction_generation"] = c.content_digest({
                "generation_kind": "SOURCE_BYTES",
                "status": receipt["status"],
                "artifact_digest": receipt["artifact_digest"],
                "mtime_ns": int(stat_after.st_mtime_ns),
            })
            gap = _gap("FUTURE_AT_CUTOFF", source_id=source_id, section_id=section_id)
            gaps_out.append(gap)
            _merge_into_section(sections[section_id], rows=[], coverage_state="BLOCKED",
                                 omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        tail = _parse_jsonl_tail(raw)
        # Stable bytes exist, so the generation is those bytes. A JSONL tail declares no
        # revision field, so there is nothing else it could lawfully rest on.
        receipt["correction_generation"] = receipt["artifact_digest"]
        receipt["status"] = "AVAILABLE"
        receipt["coverage_state"] = "COMPLETE"
        receipt["rows_total"] = tail["rows_total"]
        receipt["rows_returned"] = tail["rows_returned"]
        receipt["omitted_rows"] = tail["omitted_rows"]
        _merge_into_section(sections[section_id], rows=tail["rows"], coverage_state="COMPLETE",
                             omitted_rows=tail["omitted_rows"], gaps=[])
        sources_out.append(receipt)

    # Settlement receipts: sorted, metadata-bounded directory listing (no content parsing).
    settlement_dir = book_dir / _SETTLEMENT_RECEIPTS_DIR
    receipt = _base_receipt(
        source_id=_SETTLEMENT_RECEIPTS_SOURCE_ID,
        domains=("historical_memory",),
        producer="mastermind_portfolio",
        owner="portfolio_desk",
        artifact=f"data/portfolios/{book}/{_SETTLEMENT_RECEIPTS_DIR}",
        rights_class="FIRST_PARTY_INTERNAL",
        authority_class="BOOK_STATE",
        required=False,
        observed_at=observed_at,
    )
    sections.setdefault("historical_memory", _section("historical_memory", []))
    emit("historical_memory", _SETTLEMENT_RECEIPTS_SOURCE_ID)
    manifest = _stable_directory_manifest(settlement_dir, cutoff)
    manifest_error = manifest["error_code"]
    if manifest_error == "MISSING":
        receipt["status"] = "ABSENT_OPTIONAL"
        receipt["coverage_state"] = "COMPLETE"
        # ``error_code=None`` here, not ``manifest_error``: an absent directory must mint the
        # exact same generation as a genuinely empty one or one holding only post-cutoff
        # entries below — three different real-world states collapsing onto one stable
        # optional-absence identity.
        receipt["correction_generation"] = _unavailable_generation(
            source_id=_SETTLEMENT_RECEIPTS_SOURCE_ID, status="ABSENT_OPTIONAL",
            error_code=None, size=0,
        )
    elif manifest_error is not None:
        receipt["status"] = (
            "OVERSIZE" if manifest_error == "SETTLEMENT_MANIFEST_TOO_LARGE" else "INVALID"
        )
        receipt["error_code"] = manifest_error
        receipt["coverage_state"] = "BLOCKED"
        receipt["correction_generation"] = _unavailable_generation(
            source_id=_SETTLEMENT_RECEIPTS_SOURCE_ID, status=receipt["status"],
            error_code=manifest_error, size=0,
        )
        gap = _gap(manifest_error, source_id=_SETTLEMENT_RECEIPTS_SOURCE_ID,
                   section_id="historical_memory")
        gaps_out.append(gap)
        _merge_into_section(sections["historical_memory"], rows=[], coverage_state="BLOCKED",
                             omitted_rows=0, gaps=[gap])
    else:
        # ``_stable_directory_manifest`` already partitioned every entry independently
        # against the cutoff — never gating the whole directory on one aggregate clock — so
        # ``manifest["entries"]`` here is already the eligible census. A post-cutoff entry
        # was completely invisible to this receipt's bytes from the moment it was read: no
        # row, no count, no gap, no coverage degradation, no digest input, no generation
        # input, and no known_at effect.
        eligible: list[tuple[str, int]] = manifest["entries"]

        if not eligible:
            # Zero eligible evidence is one stable optional-absence representation,
            # regardless of whether the directory is absent, genuinely empty, or holds only
            # post-cutoff entries: none of the three carries any qualified evidence at this
            # cutoff, so none of the three may mint a different receipt or generation than
            # the others. The directory's own mtime — pre- or post-cutoff — is never
            # promoted to an AVAILABLE known_at here.
            receipt["status"] = "ABSENT_OPTIONAL"
            receipt["coverage_state"] = "COMPLETE"
            receipt["correction_generation"] = _unavailable_generation(
                source_id=_SETTLEMENT_RECEIPTS_SOURCE_ID, status="ABSENT_OPTIONAL",
                error_code=None, size=0,
            )
            _merge_into_section(sections["historical_memory"], rows=[], coverage_state="COMPLETE",
                                 omitted_rows=0, gaps=[])
        else:
            eligible_metadata = [
                {"name": name, "mtime_ns": int(mtime_ns)} for name, mtime_ns in eligible
            ]
            eligible_names = [entry["name"] for entry in eligible_metadata]
            newest_eligible_ns = max(entry["mtime_ns"] for entry in eligible_metadata)
            known_at = _utc_from_mtime_ns(newest_eligible_ns)
            receipt["known_at"] = known_at
            receipt["filesystem_observed_at"] = known_at
            receipt["clock_basis"] = "FILE_MTIME_FIRST_PARTY_STATE"
            receipt["status"] = "AVAILABLE"
            receipt["coverage_state"] = "COMPLETE"
            # Digest the entire eligible manifest, not just the displayed tail, keyed on
            # both name and mtime_ns: a change to an omitted eligible name's clock is still
            # a change in the evidence this receipt attests to, even though names alone are
            # unchanged. A future-excluded entry never reaches this digest at all.
            receipt["artifact_digest"] = c.content_digest({"manifest": eligible_metadata})
            bounded = eligible_names[-MAX_SECTION_ROWS:]
            rows = [{"file": name} for name in bounded]
            cap_omitted = len(eligible_names) - len(bounded)
            receipt["rows_total"] = len(eligible_names)
            receipt["rows_returned"] = len(bounded)
            receipt["omitted_rows"] = cap_omitted
            receipt["correction_generation"] = _settlement_generation(
                status="AVAILABLE", eligible=eligible_metadata,
            )
            _merge_into_section(sections["historical_memory"], rows=rows, coverage_state="COMPLETE",
                                 omitted_rows=cap_omitted, gaps=[])
    sources_out.append(receipt)

    return {
        "sources": sources_out,
        "sections": sections,
        "gaps": gaps_out,
        "book_position_rows": book_position_rows,
    }


# ---------------------------------------------------------------------------
# External Macro source capture
# ---------------------------------------------------------------------------

def _resolve_external_path(spec: SourceSpec) -> tuple[Path | None, str | None]:
    """Resolve a contract key to a path *proven* to lie under the vendored Macro root.

    Returns ``(path, None)`` or ``(None, error_code)``. ``config/contracts.yml`` is a shared
    multi-owner registry: an absolute ``path:``, a ``..`` segment, or a symlink pointing out
    of the tree would each silently move this module's read outside the root its docstring
    claims closure over. Containment is enforced here, before any target read, so an
    escaping entry produces a typed contract-unavailable receipt and touches nothing.
    """
    from control_plane import contracts as contracts_module
    entry = contracts_module.contract(spec.contract_key)
    if not isinstance(entry, dict):
        return None, "CONTRACT_UNAVAILABLE"
    rel_path = entry.get("path")
    if not isinstance(rel_path, str) or not rel_path:
        return None, "CONTRACT_UNAVAILABLE"
    candidate = Path(rel_path)
    if candidate.is_absolute():
        return None, "CONTRACT_PATH_ESCAPE"
    resolved_root = _V.resolve()
    # ``resolve()`` collapses ``..`` and follows symlinks, so both escape routes are closed
    # by the single containment check below. It reads link targets, never file content.
    try:
        resolved = (_V / candidate).resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        return None, "CONTRACT_PATH_ESCAPE"
    # Return the path whose containment was actually proven. Returning the unresolved
    # ``_V / candidate`` instead would let a later open/read silently re-walk any
    # intermediate symlink component the check above already resolved away.
    return resolved, None


def _project_risk_envelope(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    allowed = (
        "schema", "definition_id", "known_at", "generated_at", "as_of", "data_state",
        "measured_state", "hazard_summary", "capital_policy", "coherence", "authority",
    )
    return {k: payload[k] for k in allowed if k in payload}


def _project_regime(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    allowed = ("state", "quad", "liquidity", "cycle", "transition", "contradictions", "as_of")
    return {k: payload[k] for k in allowed if k in payload}


def _project_covariance_spine(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    allowed = (
        "schema", "as_of", "data_state", "rates", "factors", "dispersion", "lobes",
        "coverage", "missing_inputs", "authority",
    )
    return {k: payload[k] for k in allowed if k in payload}


def _project_factor_betas(payload: Any, held_tickers: Sequence[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    held = {t.upper() for t in held_tickers}
    row: dict[str, Any] = {k: payload[k] for k in ("schema", "as_of", "generated_at") if k in payload}
    betas = payload.get("betas")
    if isinstance(betas, Mapping):
        row["betas"] = {t: v for t, v in betas.items() if t.upper() in held}
    return row


def _project_prophet(payload: Any, held_tickers: Sequence[str]) -> tuple[list[Any], int, bool]:
    """Held-ticker plans, then the first 50 non-held plans, in producer order within each
    group. A non-Mapping (malformed) plan is never silently dropped from coverage — it
    always counts as an omitted row, exactly like an excess plan beyond either 50-cap.

    The third element reports whether the source declared a usable ``plans`` collection at
    all: a present empty ``plans: []`` is a complete statement that there are no plans,
    while an absent or unusable ``plans`` is missing content wearing the same zero rows.
    """
    if not isinstance(payload, Mapping):
        return [], 0, False
    plans = payload.get("plans")
    if not isinstance(plans, list):
        return [], 0, False
    held = {t.upper() for t in held_tickers}
    held_plans: list[Any] = []
    non_held_plans: list[Any] = []
    malformed = 0
    for plan in plans:
        if not isinstance(plan, Mapping):
            malformed += 1
            continue
        if str(plan.get("ticker", "")).upper() in held:
            held_plans.append(plan)
        else:
            non_held_plans.append(plan)
    selected_held = held_plans[:50]
    selected_non_held = non_held_plans[:50]
    selected = (selected_held + selected_non_held)[:MAX_SECTION_ROWS]
    omitted = (len(plans)) - len(selected)
    return selected, max(omitted, 0), True


def _project_neural_web(payload: Any, held_tickers: Sequence[str]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    held = {t.upper() for t in held_tickers}
    row: dict[str, Any] = {
        k: payload[k] for k in ("authority", "effective_hard_false_fence", "market_summary") if k in payload
    }
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        row["candidates"] = [
            cand for cand in candidates
            if isinstance(cand, Mapping) and str(cand.get("ticker", "")).upper() in held
        ]
    return row


def _project_portfolio_context(
    payload: Any, held_tickers: Sequence[str]
) -> dict[str, tuple[list[Any], int, bool]]:
    """Held-ticker rows per domain, each independently capped at 100. Returns
    ``{domain: (rows, omitted, content_present)}`` — ``omitted`` is the pre-slice
    held-ticker candidate count beyond the 100-row cap, so a cap drop is always counted,
    never silently lost, and ``content_present`` is per-domain: one absent domain key must
    not make the domains that *are* present look incomplete, nor hide itself among them."""
    domains = ("fundamental_state", "positioning", "event_state", "priceability")
    out: dict[str, tuple[list[Any], int, bool]] = {domain: ([], 0, False) for domain in domains}
    if not isinstance(payload, Mapping):
        return out
    held = {t.upper() for t in held_tickers}
    for domain in domains:
        rows_field = payload.get(domain)
        if isinstance(rows_field, list):
            filtered = [
                row for row in rows_field
                if isinstance(row, Mapping) and str(row.get("ticker", "")).upper() in held
            ]
            selected = filtered[:MAX_SECTION_ROWS]
            out[domain] = (selected, len(filtered) - len(selected), True)
    return out


def _project_held_ticker_bundle(
    payload: Any, held_tickers: Sequence[str]
) -> tuple[list[Any], int, bool]:
    """The held-ticker rows from a ``{"tickers": {...}}`` bundle, capped at 100. The same
    ``(rows, omitted, content_present)`` triple is mirrored into every sibling domain this
    source feeds — callers must not multiply the counts by the number of domains.

    ``content_present`` separates a bundle that has no row for any held ticker (a complete
    answer) from one that carries no ``tickers`` map at all (absent content)."""
    if not isinstance(payload, Mapping):
        return [], 0, False
    tickers = payload.get("tickers")
    if not isinstance(tickers, Mapping):
        return [], 0, False
    held = {t.upper() for t in held_tickers}
    filtered = [
        {"ticker": ticker, **record}
        for ticker, record in tickers.items()
        if ticker.upper() in held and isinstance(record, Mapping)
    ]
    selected = filtered[:MAX_SECTION_ROWS]
    return selected, len(filtered) - len(selected), True


# Projections that yield at most one row. An empty row means the artifact declared none of
# the fields the projection names — absent content, not an empty complete source.
# (projection -> (projector, section_id, takes_held_tickers))
_SINGLE_ROW_PROJECTIONS = {
    "risk_envelope": (_project_risk_envelope, "risk_truth", False),
    "regime": (_project_regime, "market_structure", False),
    "covariance_spine": (_project_covariance_spine, "independence", False),
    "factor_betas": (_project_factor_betas, "factor_risk", True),
    "neural_web": (_project_neural_web, "relationships", True),
}


def capture_external_sources(*, held_tickers: Sequence[str], decision_cutoff: str,
                              recorded_at: str, held_tickers_complete: bool = True) -> dict[str, Any]:
    """Capture the fixed external Macro artifacts.

    ``held_tickers_complete`` is the honesty flag for the held-ticker basis. Every
    held-ticker-filtered projection is only as complete as the book it was filtered by, so
    when the caller could not fully project the book, those domains report PARTIAL with an
    explicit gap instead of presenting a silently narrowed view as a complete one.
    """
    observed_at = c.parse_utc_timestamp(recorded_at, field="recorded_at")
    cutoff = c.parse_utc_timestamp(decision_cutoff, field="decision_cutoff")

    section_ids = sorted({domain for spec in EXTERNAL_SOURCE_SPECS for domain in spec.domains})
    sections: dict[str, dict[str, Any]] = {sid: _section(sid, []) for sid in section_ids}
    sources_out: list[dict[str, Any]] = []
    gaps_out: list[dict[str, Any]] = []

    def merge_projection(receipt, spec, section_id, rows, *, omitted=0, content_present):
        """Fold one projected domain into its section, degrading rather than overclaiming."""
        coverage = "COMPLETE"
        section_gaps: list[dict[str, Any]] = []
        if not content_present:
            coverage = "PARTIAL"
            section_gaps.append(_gap("EMPTY_PROJECTION", source_id=spec.source_id,
                                      section_id=section_id, detail=_EMPTY_PROJECTION_DETAIL))
        if not held_tickers_complete and spec.projection in _HELD_TICKER_PROJECTIONS:
            coverage = "PARTIAL"
            section_gaps.append(_gap("PARTIAL_HELD_TICKER_BASIS", source_id=spec.source_id,
                                      section_id=section_id,
                                      detail=_PARTIAL_HELD_TICKER_DETAIL))
        gaps_out.extend(section_gaps)
        _merge_into_section(sections[section_id], rows=rows, coverage_state=coverage,
                             omitted_rows=omitted, gaps=section_gaps)
        receipt["coverage_state"] = _worse_coverage(receipt["coverage_state"], coverage)

    for spec in EXTERNAL_SOURCE_SPECS:
        for domain in spec.domains:
            sections[domain]["source_ids"].append(spec.source_id)

        artifact_path, resolve_error = _resolve_external_path(spec)
        receipt = _base_receipt(
            source_id=spec.source_id,
            domains=spec.domains,
            producer="macro_engine",
            owner="macro_engine",
            artifact=spec.contract_key,
            rights_class=spec.rights_class,
            authority_class=spec.authority_class,
            required=spec.required,
            observed_at=observed_at,
        )

        if artifact_path is None:
            receipt["status"] = "INVALID"
            receipt["error_code"] = resolve_error
            receipt["coverage_state"] = "BLOCKED"
            receipt["correction_generation"] = _unavailable_generation(
                source_id=spec.source_id, status="INVALID", error_code=resolve_error, size=0,
            )
            gaps_out.append(_gap("CONTRACT_UNAVAILABLE", source_id=spec.source_id))
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=_risk_missing_placeholder(spec, domain),
                                     coverage_state="BLOCKED",
                                     omitted_rows=0, gaps=[_gap("CONTRACT_UNAVAILABLE", source_id=spec.source_id)])
            sources_out.append(receipt)
            continue

        raw, size, error_code, fs_stat = _read_json_bytes(artifact_path)
        receipt["bytes"] = size
        if fs_stat is not None:
            # Integer nanosecond floor, never float st_mtime: at these epochs a float64
            # rounds up across a second boundary, sealing an evidentiary timestamp one
            # second late. This is the same law the internal path already proves. Derived
            # from the same fstat the read itself used, never a separate later stat call.
            receipt["filesystem_observed_at"] = _utc_from_mtime_ns(fs_stat.st_mtime_ns)

        if error_code == "MISSING":
            receipt["status"] = "MISSING"
            receipt["coverage_state"] = "PARTIAL"
            receipt["correction_generation"] = _unavailable_generation(
                source_id=spec.source_id, status="MISSING", error_code=error_code, size=size,
            )
            gaps_out.append(_gap("MISSING", source_id=spec.source_id))
            for domain in spec.domains:
                placeholder = _risk_missing_placeholder(spec, domain)
                _merge_into_section(
                    sections[domain], rows=placeholder, coverage_state="PARTIAL",
                    omitted_rows=0,
                    gaps=[_gap("MISSING", source_id=spec.source_id)],
                )
            sources_out.append(receipt)
            continue

        if error_code in ("OVERSIZE", "INVALID"):
            receipt["status"] = error_code
            receipt["error_code"] = error_code
            receipt["coverage_state"] = "PARTIAL"
            # No bytes to hash — an oversize file is never read merely to identify it —
            # so the generation rests on the bounded metadata that is trustworthy.
            receipt["correction_generation"] = _unavailable_generation(
                source_id=spec.source_id, status=error_code, error_code=error_code,
                size=size, stat_result=fs_stat,
            )
            gaps_out.append(_gap(error_code, source_id=spec.source_id))
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0,
                                     gaps=[_gap(error_code, source_id=spec.source_id)])
            sources_out.append(receipt)
            continue

        receipt["artifact_digest"] = _digest(raw)
        payload, parse_error = _parse_json(raw)
        if parse_error:
            receipt["status"] = "MALFORMED"
            receipt["error_code"] = parse_error
            receipt["coverage_state"] = "PARTIAL"
            # Stable bytes exist even though they do not parse: the generation tracks them,
            # so two different malformed bodies are two different states of the world.
            receipt["correction_generation"] = receipt["artifact_digest"]
            gaps_out.append(_gap(parse_error, source_id=spec.source_id))
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0,
                                     gaps=[_gap(parse_error, source_id=spec.source_id)])
            sources_out.append(receipt)
            continue

        receipt["correction_generation"] = _correction_generation(payload, receipt["artifact_digest"])
        receipt["source_schema"] = _first_present_str(payload, spec.schema_fields)
        receipt["definition_id"] = _first_present_str(payload, spec.definition_fields)
        as_of = _first_present_str(payload, spec.as_of_fields)
        if as_of is not None:
            receipt["as_of"] = as_of
        generated_at = _first_present_str(payload, spec.generated_at_fields)
        if generated_at is not None:
            normalized_generated = _canonical_or_none(generated_at)
            if normalized_generated is not None:
                receipt["generated_at"] = normalized_generated

        # PR #548-owned Sector Central: receipt/digest + explicit gap only, never rows.
        if spec.projection == "receipt_only_pr548":
            receipt["status"] = "DEPENDENCY_PARTIAL"
            receipt["coverage_state"] = "PARTIAL"
            gap = _gap(
                "DEPENDENCY_OWNED_ELSEWHERE",
                source_id=spec.source_id,
                owner="Mastermind PR #548",
                detail="non-lossy Sector Central reader is owned by PR #548; S0 captures receipt only",
            )
            gaps_out.append(gap)
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        declared_known_at = _first_declared(payload, spec.known_at_fields)
        if declared_known_at is None:
            receipt["known_at"] = None
            receipt["clock_basis"] = "UNQUALIFIED_EXTERNAL_CLOCK"
            receipt["status"] = "UNQUALIFIED_CLOCK"
            receipt["coverage_state"] = "PARTIAL"
            gap = _gap("UNQUALIFIED_CLOCK", source_id=spec.source_id)
            gaps_out.append(gap)
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="PARTIAL",
                                     omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        receipt["known_at"] = declared_known_at
        receipt["clock_basis"] = "DECLARED_SOURCE_FIELD"

        if declared_known_at > cutoff:
            receipt["status"] = "FUTURE_AT_CUTOFF"
            receipt["coverage_state"] = "BLOCKED"
            gap = _gap("FUTURE_AT_CUTOFF", source_id=spec.source_id)
            gaps_out.append(gap)
            for domain in spec.domains:
                _merge_into_section(sections[domain], rows=[], coverage_state="BLOCKED",
                                     omitted_rows=0, gaps=[gap])
            sources_out.append(receipt)
            continue

        receipt["status"] = "AVAILABLE"
        receipt["coverage_state"] = "COMPLETE"

        if spec.projection in _SINGLE_ROW_PROJECTIONS:
            project, section_id, needs_held = _SINGLE_ROW_PROJECTIONS[spec.projection]
            row = project(payload, held_tickers) if needs_held else project(payload)
            rows = [row] if row else []
            merge_projection(receipt, spec, section_id, rows, content_present=bool(row))
            receipt["rows_total"] = receipt["rows_returned"] = len(rows)
        elif spec.projection == "prophet":
            rows, omitted, present = _project_prophet(payload, held_tickers)
            merge_projection(receipt, spec, "candidate_geometry", rows,
                             omitted=omitted, content_present=present)
            receipt["rows_total"] = len(rows) + omitted
            receipt["rows_returned"] = len(rows)
            receipt["omitted_rows"] = omitted
        elif spec.projection == "portfolio_context":
            by_domain = _project_portfolio_context(payload, held_tickers)
            total_returned = 0
            total_omitted = 0
            for domain, (rows, omitted, present) in by_domain.items():
                merge_projection(receipt, spec, domain, rows,
                                 omitted=omitted, content_present=present)
                total_returned += len(rows)
                total_omitted += omitted
            receipt["rows_returned"] = total_returned
            receipt["omitted_rows"] = total_omitted
            receipt["rows_total"] = total_returned + total_omitted
        elif spec.projection == "held_ticker_bundle":
            rows, omitted, present = _project_held_ticker_bundle(payload, held_tickers)
            for domain in spec.domains:
                merge_projection(receipt, spec, domain, rows,
                                 omitted=omitted, content_present=present)
            receipt["rows_returned"] = len(rows)
            receipt["omitted_rows"] = omitted
            receipt["rows_total"] = len(rows) + omitted

        sources_out.append(receipt)

    return {"sources": sources_out, "sections": sections, "gaps": gaps_out}


def _risk_missing_placeholder(spec: SourceSpec, domain: str) -> list[dict[str, Any]]:
    if spec.source_id == "macro.risk_envelope" and domain == "risk_truth":
        return [{
            "market_risk_state": "UNKNOWN_PROTECTIVE",
            "reason": f"{spec.source_id}:MISSING",
        }]
    return []


# ---------------------------------------------------------------------------
# Combined capture
# ---------------------------------------------------------------------------

def _held_tickers_from_book_position_rows(
    book_position_rows: Sequence[tuple[str, dict[str, Any]]],
) -> list[str]:
    """Harvest held tickers only from ``book.account``/``book.latest`` rows.

    A raw-object first-party source (e.g. pending orders/targets) is never a held-ticker
    basis, even when its own arbitrary payload happens to carry a ``positions`` key: only
    the two rows the caller already scoped to the canonical book state may contribute.
    """
    tickers: list[str] = []
    seen: set[str] = set()
    for _source_id, row in book_position_rows:
        if not isinstance(row, Mapping):
            continue
        positions = row.get("positions")
        if isinstance(positions, Mapping):
            for ticker in positions:
                if ticker not in seen:
                    seen.add(ticker)
                    tickers.append(ticker)
        elif isinstance(positions, list):
            for pos in positions:
                if isinstance(pos, Mapping):
                    ticker = pos.get("ticker")
                    if isinstance(ticker, str) and ticker not in seen:
                        seen.add(ticker)
                        tickers.append(ticker)
    return tickers


def capture_all(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]:
    book_capture = capture_book_state(book, decision_cutoff=decision_cutoff, recorded_at=recorded_at)
    book_position_rows = book_capture["book_position_rows"]
    held_tickers = _held_tickers_from_book_position_rows(book_position_rows)
    # The held-ticker basis is complete only when the *required* canonical source —
    # book.account — is itself AVAILABLE, COMPLETE, and actually carries a valid projected
    # positions mapping. Absence of a MALFORMED_POSITION_ENTRY gap is not enough: a wholly
    # MISSING, MALFORMED, OVERSIZE, or FUTURE_AT_CUTOFF account never emits that gap code
    # either, yet its held-ticker set is exactly as unknown as one that dropped entries.
    account_receipt = next(
        (r for r in book_capture["sources"] if r["source_id"] == "book.account"), None
    )
    account_row = next(
        (row for source_id, row in book_position_rows if source_id == "book.account"), None
    )
    held_tickers_complete = bool(
        account_receipt is not None
        and account_receipt.get("status") == "AVAILABLE"
        and account_receipt.get("coverage_state") == "COMPLETE"
        and isinstance(account_row, Mapping)
        and isinstance(account_row.get("positions"), Mapping)
    )
    external_capture = capture_external_sources(
        held_tickers=held_tickers, decision_cutoff=decision_cutoff, recorded_at=recorded_at,
        held_tickers_complete=held_tickers_complete,
    )

    sections: dict[str, dict[str, Any]] = {}
    for section_id, section in book_capture["sections"].items():
        sections[section_id] = section
    for section_id, section in external_capture["sections"].items():
        if section_id in sections:
            existing = sections[section_id]
            cap_dropped = _append_capped(existing, section["rows"])
            existing["source_ids"] = existing["source_ids"] + section["source_ids"]
            existing["coverage_state"] = _worse_coverage(existing["coverage_state"], section["coverage_state"])
            existing["omitted_rows"] += section["omitted_rows"] + cap_dropped
            existing["rows_returned"] = len(existing["rows"])
            existing["rows_total"] = existing["rows_returned"] + existing["omitted_rows"]
            existing["gaps"] = existing["gaps"] + section["gaps"]
        else:
            sections[section_id] = section

    return {
        "sources": book_capture["sources"] + external_capture["sources"],
        "sections": sections,
        "gaps": book_capture["gaps"] + external_capture["gaps"],
    }
