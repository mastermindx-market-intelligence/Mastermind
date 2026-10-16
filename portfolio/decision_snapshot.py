"""portfolio.decision_snapshot — compose and persist immutable V3 Decision Snapshots.

Composes one closed, correction-safe snapshot from a Task 2 capture bundle, derives its
coverage/correction state, and persists it as a create-once, content-addressed file below
``data/shadow/decision_snapshots/<book>/``. No caller-supplied path/root/url ever reaches a
filesystem expression: the storage root and the fixed book allowlist are closed constants,
and every snapshot identity is a ``sha256:<64hex>`` content digest over its own canonical
bytes (reusing ``control_plane.wake_events.canonical_json_bytes`` — no second serializer).

Every read verifies canonical bytes, closed-schema shape, and the snapshot digest before any
manifest row or section page is projected from it; a corrupt sibling file is never silently
hidden by a list/latest read. Persistence is create-once (``O_EXCL``) with symlink/non-regular
refusal on every read; an existing file's bytes are never replaced, only verified.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.wake_events import canonical_json_bytes
from portfolio import decision_snapshot_contracts as c
from portfolio import decision_snapshot_sources as sources

_ROOT = Path(__file__).resolve().parent.parent
_BOOK_ID = "autonomous"
_SNAPSHOT_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SNAPSHOT_FILENAME_RE = re.compile(r"^[0-9a-f]{64}\.json$")
_MAX_LIST_LIMIT = 100
_GAP_SORT_FIELDS = ("code", "source_id", "section_id", "owner", "detail")

# The fixed literal path, one component at a time, from ``_ROOT`` to the snapshot leaf
# directory. Every component is a closed constant — never caller input — and is opened
# descriptor-relative to its already-contained parent, so a symlink substituted for *any*
# component (not just the leaf) is refused before it can be traversed.
_SNAPSHOT_DIR_COMPONENTS = ("data", "shadow", "decision_snapshots", _BOOK_ID)


class DecisionSnapshotError(Exception):
    """Base error for the Decision Snapshot composer and store."""


class SnapshotNotFound(DecisionSnapshotError):
    """Raised when a requested snapshot does not exist."""


class SnapshotCorrupt(DecisionSnapshotError):
    """Raised when persisted or supplied snapshot bytes fail verification."""


class SnapshotInvalidRequest(DecisionSnapshotError):
    """Raised when caller input violates the closed request/capture contract."""


# ---------------------------------------------------------------------------
# Storage identity
# ---------------------------------------------------------------------------

def snapshot_dir(book: str) -> Path:
    if book != _BOOK_ID:
        raise SnapshotInvalidRequest(f"unknown book {book!r}")
    # The validated caller value is never interpolated into the path — only the closed
    # literal is, so a filesystem expression here can never carry caller-controlled text
    # even though the two are proven equal above.
    return _ROOT / "data" / "shadow" / "decision_snapshots" / _BOOK_ID


def _snapshot_filename(snapshot_id: str) -> str:
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise SnapshotInvalidRequest(f"invalid snapshot_id {snapshot_id!r}")
    return f"{snapshot_id.split(':', 1)[1]}.json"


def _snapshot_path(book: str, snapshot_id: str) -> Path:
    return snapshot_dir(book) / _snapshot_filename(snapshot_id)


# ---------------------------------------------------------------------------
# Bounded, descriptor-relative, symlink-refusing byte reads
#
# No caller-supplied path is ever joined and handed to lstat/open/scandir. Every access
# below is proven contained beneath the fixed snapshot root before it happens: the
# directory is opened once (refusing a symlinked or non-directory leaf), and every file
# within it is then read only through that directory descriptor, by a filename either
# enumerated straight off the filesystem (never a caller string) or, for a brand-new
# create-once write, a filename built purely from characters a closed regex already proved
# safe. There is no path join between caller input and an lstat/open/scandir call anywhere
# in this module.
# ---------------------------------------------------------------------------

def _open_dir_relative(parent_fd: int, name: str, *, create: bool) -> int | None:
    """Open literal component ``name`` beneath ``parent_fd``, descriptor-relative, refusing
    to follow a symlink or open anything but a directory.

    With ``create=False``, an absent component returns ``None``. With ``create=True``, an
    absent component is ``mkdir``'d first (descriptor-relative) and then reopened the same
    no-follow way; a create race against a concurrent writer is resolved by reopening, never
    by trusting the unverified path, and a race that lands a symlink or non-directory in the
    component's place still fails the reopen and fails closed. Any other symlinked or
    non-directory component — created or pre-existing — is corrupt storage and raises
    ``SnapshotCorrupt`` rather than being silently followed.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            return None
        try:
            os.mkdir(name, 0o777, dir_fd=parent_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise SnapshotCorrupt(f"unable to create {name!r}: {exc}") from exc
        try:
            return os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise SnapshotCorrupt(f"unable to open {name!r} after creation: {exc}") from exc
    except OSError as exc:
        raise SnapshotCorrupt(f"{name!r} is not a plain directory: {exc}") from exc


def _open_snapshot_directory(*, create: bool = False) -> int | None:
    """Open the fixed snapshot leaf directory by walking every literal path component from
    ``_ROOT``, descriptor-relative, refusing a symlink or non-directory at any step.

    No caller-supplied path or root ever reaches this function — every component in
    ``_SNAPSHOT_DIR_COMPONENTS`` is a closed literal — and containment is structural, not a
    resolve-then-check race: each ``open`` is relative to the already-opened, already-proven
    parent descriptor, so a symlink substituted for any intermediate component (not merely
    the leaf) can never redirect the walk outside ``_ROOT``.

    With ``create=False`` (reads/scans), returns ``None`` as soon as any component is
    absent — the store has never persisted a snapshot for this book. With ``create=True``
    (writes), an absent component is created in place before the walk continues.
    """
    root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = os.open(str(_ROOT), root_flags)
    except OSError as exc:
        raise SnapshotCorrupt(f"unable to open snapshot storage root {_ROOT}: {exc}") from exc
    for name in _SNAPSHOT_DIR_COMPONENTS:
        try:
            next_fd = _open_dir_relative(fd, name, create=create)
        finally:
            os.close(fd)
        if next_fd is None:
            return None
        fd = next_fd
    return fd


def _find_regular_entry(dir_fd: int, expected_name: str) -> tuple[str, os.stat_result] | None:
    """Find ``expected_name`` among the directory's real entries, returning the matched
    entry's own name and lstat — never the caller's ``expected_name`` string itself — so a
    subsequent open reads a filesystem-sourced value, not a caller-constructed path."""
    with os.scandir(dir_fd) as entries:
        for entry in entries:
            if entry.name != expected_name:
                continue
            return entry.name, entry.stat(follow_symlinks=False)
    return None


def _read_regular_entry_bytes(dir_fd: int, name: str, entry_stat: os.stat_result) -> bytes | None:
    """Read ``name``'s bytes via a descriptor-relative open beneath ``dir_fd``, refusing
    symlinks and non-regular files. Returns ``None`` only if the entry vanished between
    enumeration and open; every other failure mode raises ``SnapshotCorrupt``."""
    if stat.S_ISLNK(entry_stat.st_mode) or not stat.S_ISREG(entry_stat.st_mode):
        raise SnapshotCorrupt(f"{name} is not a regular file")
    # Refuse before opening, not after reading: a sibling may be arbitrarily large (a
    # sparse file advertises an enormous st_size while occupying almost no blocks), and a
    # snapshot can never lawfully exceed this ceiling, so reading one to discover it is
    # corrupt would allocate attacker-chosen memory for no evidentiary gain.
    if entry_stat.st_size > c.MAX_SNAPSHOT_BYTES:
        raise SnapshotCorrupt(f"{name} exceeds the {c.MAX_SNAPSHOT_BYTES}-byte snapshot limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SnapshotCorrupt(f"unable to open {name!r}: {exc}") from exc
    try:
        post = os.fstat(fd)
        if post.st_dev != entry_stat.st_dev or post.st_ino != entry_stat.st_ino:
            raise SnapshotCorrupt(f"{name} identity changed between stat and open")
        # Re-check against the opened descriptor: the pre-open stat is advisory, and the
        # read below is sized from st_size.
        if post.st_size > c.MAX_SNAPSHOT_BYTES:
            raise SnapshotCorrupt(
                f"{name} exceeds the {c.MAX_SNAPSHOT_BYTES}-byte snapshot limit"
            )
        chunks: list[bytes] = []
        remaining = post.st_size
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    return raw


def _verify_and_load(raw: bytes) -> dict[str, Any]:
    """Verify canonical bytes, closed schema, and content digest before returning a payload."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SnapshotCorrupt("snapshot file is not ASCII") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotCorrupt("snapshot file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SnapshotCorrupt("snapshot file is not a JSON object")
    if canonical_json_bytes(payload) != raw:
        raise SnapshotCorrupt("snapshot file is not canonical bytes")
    try:
        c.validate_snapshot(payload)
        c.verify_snapshot(payload)
    except c.DecisionSnapshotContractError as exc:
        raise SnapshotCorrupt(str(exc)) from exc
    return payload


# ---------------------------------------------------------------------------
# Create-once persistence
# ---------------------------------------------------------------------------

def _write_all(fd: int, data: bytes) -> None:
    """Write every byte of ``data`` to ``fd``, looping past short writes.

    A short or zero-length ``os.write`` is a hard error here — a partially written file
    would otherwise silently poison its content address forever, since this store never
    replaces an existing path.
    """
    view = memoryview(data)
    total = len(view)
    written = 0
    while written < total:
        n = os.write(fd, view[written:])
        if n <= 0:
            raise OSError("os.write returned no bytes; snapshot write stalled")
        written += n


def _sanitize_snapshot_filename(filename: str) -> str:
    """Recompute ``filename`` through ``os.path.basename`` — a path-component sanitizer
    static analysis recognizes as a barrier — and assert the sanitized component still
    equals the strict closed ``<64hex>.json`` form before it is allowed anywhere near
    ``os.open``/``os.unlink``. Any divergence (a path separator, a hidden ``..`` segment,
    anything not exactly 64 lowercase hex characters plus ``.json``) is corrupt input.
    """
    sanitized = os.path.basename(filename)
    if sanitized != filename or not _SNAPSHOT_FILENAME_RE.fullmatch(sanitized):
        raise SnapshotCorrupt(f"unsafe snapshot filename component {filename!r}")
    return sanitized


def _create_once(dir_fd: int, filename: str, encoded: bytes) -> bool:
    """Create ``filename`` beneath ``dir_fd`` with O_EXCL, refusing to follow a symlink.

    ``filename`` is composed purely of the 64 hex characters a closed regex already proved
    safe plus a fixed ``.json`` suffix — never a caller string joined onto a path — and is
    opened relative to the already-contained ``dir_fd``, never via a constructed ``Path``.
    It is re-sanitized immediately below, right beside the ``os.open``/``os.unlink`` calls,
    so neither sink is ever reached by anything but a freshly re-verified basename.
    """
    filename = _sanitize_snapshot_filename(filename)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(filename, flags, 0o600, dir_fd=dir_fd)
    except FileExistsError:
        return False
    try:
        _write_all(fd, encoded)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        # O_EXCL just created this exact entry, so it is never pre-existing: safe to unlink.
        try:
            os.unlink(filename, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
        try:
            os.fsync(dir_fd)
        except OSError:
            pass  # best-effort durability for the cleanup; the original error still wins.
        raise
    else:
        os.close(fd)
    os.fsync(dir_fd)
    return True


def persist_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    c.validate_snapshot(snapshot)
    c.verify_snapshot(snapshot)
    book = snapshot["book"]
    # ``verify_snapshot`` above already proved ``snapshot["snapshot_id"] ==
    # content_digest(unsealed)``; recompute that same digest here rather than reading the
    # id back off the caller's mapping, so the filename this module derives never traces
    # back to a caller-supplied string — only to bytes this function itself just hashed.
    recomputed_id = c.content_digest({k: v for k, v in snapshot.items() if k != "snapshot_id"})
    directory = snapshot_dir(book)
    filename = _snapshot_filename(recomputed_id)
    encoded = canonical_json_bytes(snapshot)
    if len(encoded) > c.MAX_SNAPSHOT_BYTES:
        raise SnapshotInvalidRequest("snapshot exceeds max size")
    dir_fd = _open_snapshot_directory(create=True)
    if dir_fd is None:
        raise SnapshotCorrupt(f"unable to open snapshot directory {directory} after creation")
    try:
        created = _create_once(dir_fd, filename, encoded)
        if not created:
            # The O_EXCL create reported an existing entry: locate it through the directory
            # scan and open the filesystem-sourced name, exactly like load_snapshot — never
            # reopen by the caller-derived ``filename`` string directly.
            match = _find_regular_entry(dir_fd, filename)
            existing = (
                _read_regular_entry_bytes(dir_fd, match[0], match[1])
                if match is not None else None
            )
            if existing is None or existing != encoded:
                raise SnapshotCorrupt(
                    f"existing snapshot at {directory / filename} does not match canonical bytes"
                )
    finally:
        os.close(dir_fd)
    return {"created": created, "path": str(directory / filename), "snapshot": dict(snapshot)}


# ---------------------------------------------------------------------------
# Verified reads
# ---------------------------------------------------------------------------

def load_snapshot(book: str, snapshot_id: str) -> dict[str, Any]:
    # Both inputs are fully validated — and the directory resolved to its closed literal
    # form — before any lstat/open/scandir call is made.
    directory = snapshot_dir(book)
    expected_name = _snapshot_filename(snapshot_id)
    dir_fd = _open_snapshot_directory()
    if dir_fd is None:
        raise SnapshotNotFound(f"snapshot {snapshot_id!r} not found for book {book!r}")
    try:
        match = _find_regular_entry(dir_fd, expected_name)
        if match is None:
            raise SnapshotNotFound(f"snapshot {snapshot_id!r} not found for book {book!r}")
        name, entry_stat = match
        raw = _read_regular_entry_bytes(dir_fd, name, entry_stat)
    finally:
        os.close(dir_fd)
    if raw is None:
        raise SnapshotNotFound(f"snapshot {snapshot_id!r} not found for book {book!r}")
    payload = _verify_and_load(raw)
    if payload.get("snapshot_id") != snapshot_id or payload.get("book") != book:
        raise SnapshotCorrupt("snapshot identity does not match requested book/snapshot_id")
    return payload


def _scan_verified_snapshots(book: str) -> list[dict[str, Any]]:
    snapshot_dir(book)  # validates ``book`` against the closed literal before any fs call
    dir_fd = _open_snapshot_directory()
    if dir_fd is None:
        return []
    try:
        candidates: list[tuple[str, os.stat_result]] = []
        with os.scandir(dir_fd) as entries:
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                candidates.append((entry.name, entry.stat(follow_symlinks=False)))
        out: list[dict[str, Any]] = []
        for name, entry_stat in sorted(candidates, key=lambda item: item[0]):
            raw = _read_regular_entry_bytes(dir_fd, name, entry_stat)
            if raw is None:
                continue
            out.append(_verify_and_load(raw))
        return out
    finally:
        os.close(dir_fd)


def _manifest_row(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "book": snapshot["book"],
        "snapshot_id": snapshot["snapshot_id"],
        "decision_cutoff": snapshot["decision_cutoff"],
        "recorded_at": snapshot["recorded_at"],
        "state": snapshot["state"],
        "coverage_state": snapshot["coverage_state"],
        "summary": dict(snapshot["summary"]),
        "correction": dict(snapshot["correction"]),
    }


def list_snapshots(book: str, *, limit: int = 20) -> list[dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise SnapshotInvalidRequest("limit must be an integer")
    bounded_limit = max(1, min(limit, _MAX_LIST_LIMIT))
    manifests = [_manifest_row(s) for s in _scan_verified_snapshots(book)]
    manifests.sort(
        key=lambda m: (m["decision_cutoff"], m["recorded_at"], m["snapshot_id"]),
        reverse=True,
    )
    return manifests[:bounded_limit]


def latest_snapshot(book: str) -> dict[str, Any] | None:
    snaps = _scan_verified_snapshots(book)
    if not snaps:
        return None
    snaps.sort(
        key=lambda s: (s["decision_cutoff"], s["recorded_at"], s["snapshot_id"]),
        reverse=True,
    )
    return snaps[0]


def _same_cutoff_prior_snapshots(book: str, cutoff: str) -> list[dict[str, Any]]:
    snaps = [s for s in _scan_verified_snapshots(book) if s["decision_cutoff"] == cutoff]
    snaps.sort(key=lambda s: (s["recorded_at"], s["snapshot_id"]))
    return snaps


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def _coverage_state(sections: Mapping[str, Mapping[str, Any]]) -> str:
    values = {row["coverage_state"] for row in sections.values()}
    if "BLOCKED" in values:
        return "BLOCKED"
    if values == {"COMPLETE"}:
        return "COMPLETE"
    return "PARTIAL"


def _gap_sort_key(gap: Mapping[str, Any]) -> tuple:
    return tuple(gap.get(field) or "" for field in _GAP_SORT_FIELDS)


def _seal_gaps(gaps: Sequence[Any]) -> list[str]:
    for gap in gaps:
        if not isinstance(gap, Mapping):
            raise SnapshotInvalidRequest("capture gap entries must be mappings")
    ordered = sorted(gaps, key=_gap_sort_key)
    return [canonical_json_bytes(gap).decode("ascii") for gap in ordered]


def compose_snapshot(
    book: str,
    *,
    decision_cutoff: str,
    recorded_at: str,
    capture: Mapping[str, Any],
    same_cutoff_prior_snapshot_ids: Sequence[str],
) -> dict[str, Any]:
    if book != _BOOK_ID:
        raise SnapshotInvalidRequest(f"unknown book {book!r}")
    cutoff = c.parse_utc_timestamp(decision_cutoff, field="decision_cutoff")
    recorded = c.parse_utc_timestamp(recorded_at, field="recorded_at")
    if recorded < cutoff:
        raise SnapshotInvalidRequest("recorded_at must not precede decision_cutoff")

    if not isinstance(capture, Mapping) or set(capture.keys()) != {"sources", "sections", "gaps"}:
        raise SnapshotInvalidRequest("capture must have exactly {sources, sections, gaps}")

    sources_in = capture["sources"]
    sections_in = capture["sections"]
    gaps_in = capture["gaps"]
    if (
        not isinstance(sources_in, Sequence)
        or isinstance(sources_in, (str, bytes))
    ):
        raise SnapshotInvalidRequest("capture.sources must be a sequence")
    if not isinstance(sections_in, Mapping):
        raise SnapshotInvalidRequest("capture.sections must be a mapping")
    if not isinstance(gaps_in, Sequence) or isinstance(gaps_in, (str, bytes)):
        raise SnapshotInvalidRequest("capture.gaps must be a sequence")

    if set(sections_in.keys()) != set(c.SECTION_IDS):
        raise SnapshotInvalidRequest(
            "capture.sections must contain exactly the closed SECTION_IDS"
        )
    for section_id, section in sections_in.items():
        if not isinstance(section, Mapping):
            raise SnapshotInvalidRequest(f"capture.sections[{section_id!r}] must be a mapping")
        if section.get("section_id") != section_id:
            raise SnapshotInvalidRequest(
                f"capture.sections[{section_id!r}].section_id mismatch"
            )

    seen_source_ids: set[str] = set()
    for receipt in sources_in:
        if not isinstance(receipt, Mapping):
            raise SnapshotInvalidRequest("capture.sources entries must be mappings")
        sid = receipt.get("source_id")
        if not isinstance(sid, str) or not sid:
            raise SnapshotInvalidRequest("capture.sources[].source_id must be a non-empty string")
        if sid in seen_source_ids:
            raise SnapshotInvalidRequest(f"duplicate source_id {sid!r} in capture.sources")
        seen_source_ids.add(sid)

    sorted_sources = sorted(sources_in, key=lambda r: r["source_id"])
    for receipt in sorted_sources:
        c.validate_source_receipt(receipt)

    generation_entries = sorted(
        (
            {"source_id": r["source_id"], "correction_generation": r["correction_generation"]}
            for r in sorted_sources
        ),
        key=lambda entry: entry["source_id"],
    )

    sealed_sections: dict[str, dict[str, Any]] = {}
    for section_id in c.SECTION_IDS:
        section = sections_in[section_id]
        sealed_section = {**section, "gaps": _seal_gaps(section.get("gaps", []))}
        c.validate_section(sealed_section)
        sealed_sections[section_id] = sealed_section

    coverage_state = _coverage_state(sealed_sections)

    sources_total = len(sorted_sources)
    sources_available = sum(1 for r in sorted_sources if r.get("status") == "AVAILABLE")
    domains_complete = sum(
        1 for s in sealed_sections.values() if s["coverage_state"] == "COMPLETE"
    )
    domains_partial = sum(
        1 for s in sealed_sections.values() if s["coverage_state"] == "PARTIAL"
    )
    domains_blocked = sum(
        1 for s in sealed_sections.values() if s["coverage_state"] == "BLOCKED"
    )
    summary = {
        "sources_total": sources_total,
        "sources_available": sources_available,
        "domains_complete": domains_complete,
        "domains_partial": domains_partial,
        "domains_blocked": domains_blocked,
    }

    prior_ids: list[str] = []
    for pid in same_cutoff_prior_snapshot_ids or []:
        if not isinstance(pid, str) or not pid:
            raise SnapshotInvalidRequest("same_cutoff_prior_snapshot_ids must be non-empty strings")
        prior_ids.append(pid)

    if prior_ids:
        state = "CORRECTED_GENERATION_AVAILABLE"
        correction_status = "CORRECTED"
    else:
        state = coverage_state
        correction_status = "ORIGINAL"

    unsealed = {
        "schema": c.SNAPSHOT_SCHEMA,
        "book": book,
        "decision_cutoff": cutoff,
        "recorded_at": recorded,
        "state": state,
        "coverage_state": coverage_state,
        "summary": summary,
        "source_generation_set": generation_entries,
        "sources": sorted_sources,
        "sections": sealed_sections,
        "gaps": _seal_gaps(list(gaps_in)),
        "correction": {
            "status": correction_status,
            "same_cutoff_prior_snapshot_ids": prior_ids,
        },
        "authority": {
            "write_permitted": False,
            "execution_authority": False,
            "numeric_target_authority": False,
        },
    }
    return c.seal_snapshot(unsealed)


def create_snapshot(book: str, *, decision_cutoff: str, recorded_at: str) -> dict[str, Any]:
    cutoff = c.parse_utc_timestamp(decision_cutoff, field="decision_cutoff")
    recorded = c.parse_utc_timestamp(recorded_at, field="recorded_at")

    prior_snapshots = _same_cutoff_prior_snapshots(book, cutoff)
    capture = sources.capture_all(book, decision_cutoff=cutoff, recorded_at=recorded)
    new_generation_set = sorted(
        (
            {"source_id": r["source_id"], "correction_generation": r["correction_generation"]}
            for r in capture["sources"]
        ),
        key=lambda entry: entry["source_id"],
    )

    # ``prior_snapshots`` is ascending by (recorded_at, snapshot_id); the first exact
    # generation-set match — original or a later correction — is the one to reuse. Only
    # when none match at all does this become a new correction over every prior ID.
    for existing in prior_snapshots:
        if existing["source_generation_set"] == new_generation_set:
            return {**existing, "created": False}
    prior_ids = [s["snapshot_id"] for s in prior_snapshots]

    composed = compose_snapshot(
        book,
        decision_cutoff=cutoff,
        recorded_at=recorded,
        capture=capture,
        same_cutoff_prior_snapshot_ids=prior_ids,
    )
    result = persist_snapshot(composed)
    return {**result["snapshot"], "created": result["created"]}


# ---------------------------------------------------------------------------
# Section paging / projection
# ---------------------------------------------------------------------------

def section_page(
    snapshot: Mapping[str, Any], section_id: str, *, offset: int, limit: int
) -> dict[str, Any]:
    if section_id not in c.SECTION_IDS:
        raise SnapshotInvalidRequest(f"unknown section_id {section_id!r}")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise SnapshotInvalidRequest("offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= c.MAX_SECTION_ROWS):
        raise SnapshotInvalidRequest("limit must be an integer between 1 and 100")

    sections = snapshot.get("sections")
    if not isinstance(sections, Mapping) or section_id not in sections:
        raise SnapshotInvalidRequest(f"snapshot has no section {section_id!r}")
    section = sections[section_id]
    rows = section.get("rows")
    if not isinstance(rows, list):
        raise SnapshotCorrupt(f"section {section_id!r} rows is not a list")

    page_rows = rows[offset:offset + limit]
    next_offset = offset + limit if offset + limit < len(rows) else None
    page = {
        "schema": section.get("schema"),
        "section_id": section_id,
        "coverage_state": section.get("coverage_state"),
        "source_ids": list(section.get("source_ids", [])),
        "rows_total": section.get("rows_total"),
        "rows_returned": len(page_rows),
        "omitted_rows": section.get("omitted_rows"),
        "gaps": list(section.get("gaps", [])),
        "rows": page_rows,
        "next_offset": next_offset,
    }
    if len(canonical_json_bytes(page)) > c.MAX_SECTION_RESPONSE_BYTES:
        raise SnapshotInvalidRequest("section page exceeds max response size")
    return page


def read_projection(
    book: str,
    *,
    snapshot_id: str | None,
    section_id: str | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    if snapshot_id is None:
        snapshot = latest_snapshot(book)
        if snapshot is None:
            raise SnapshotNotFound(f"no snapshot exists for book {book!r}")
    else:
        snapshot = load_snapshot(book, snapshot_id)

    if section_id is None:
        return {"snapshot": {k: v for k, v in snapshot.items() if k != "sections"}}

    page = section_page(snapshot, section_id, offset=offset, limit=limit)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "book": snapshot["book"],
        "decision_cutoff": snapshot["decision_cutoff"],
        "recorded_at": snapshot["recorded_at"],
        "state": snapshot["state"],
        "coverage_state": snapshot["coverage_state"],
        "correction": snapshot["correction"],
        "section": page,
    }
