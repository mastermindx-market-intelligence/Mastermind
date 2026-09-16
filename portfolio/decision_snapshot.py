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
_MAX_LIST_LIMIT = 100
_GAP_SORT_FIELDS = ("code", "source_id", "section_id", "owner", "detail")


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
    return _ROOT / "data" / "shadow" / "decision_snapshots" / book


def _snapshot_path(book: str, snapshot_id: str) -> Path:
    directory = snapshot_dir(book)
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise SnapshotInvalidRequest(f"invalid snapshot_id {snapshot_id!r}")
    hex_part = snapshot_id.split(":", 1)[1]
    return directory / f"{hex_part}.json"


# ---------------------------------------------------------------------------
# Bounded, symlink-refusing byte reads
# ---------------------------------------------------------------------------

def _read_regular_file_bytes(path: Path) -> bytes | None:
    """Read a snapshot file's bytes, refusing symlinks and non-regular files.

    Returns ``None`` only when the path does not exist; every other failure mode raises
    ``SnapshotCorrupt`` rather than silently disappearing.
    """
    try:
        pre = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(pre.st_mode):
        raise SnapshotCorrupt(f"{path} is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SnapshotCorrupt(f"unable to open {path}: {exc}") from exc
    try:
        post = os.fstat(fd)
        if post.st_dev != pre.st_dev or post.st_ino != pre.st_ino:
            raise SnapshotCorrupt(f"{path} identity changed between stat and open")
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


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    dir_fd = os.open(str(directory), flags)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _create_once(path: Path, encoded: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError:
        return False
    try:
        _write_all(fd, encoded)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        # O_EXCL just created this exact path, so it is never pre-existing: safe to unlink.
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        try:
            _fsync_directory(path.parent)
        except OSError:
            pass  # best-effort durability for the cleanup; the original error still wins.
        raise
    else:
        os.close(fd)
    _fsync_directory(path.parent)
    return True


def persist_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    c.validate_snapshot(snapshot)
    c.verify_snapshot(snapshot)
    book = snapshot["book"]
    snapshot_id = snapshot["snapshot_id"]
    path = _snapshot_path(book, snapshot_id)
    encoded = canonical_json_bytes(snapshot)
    if len(encoded) > c.MAX_SNAPSHOT_BYTES:
        raise SnapshotInvalidRequest("snapshot exceeds max size")
    created = _create_once(path, encoded)
    if not created:
        existing = _read_regular_file_bytes(path)
        if existing is None or existing != encoded:
            raise SnapshotCorrupt(
                f"existing snapshot at {path} does not match canonical bytes"
            )
    return {"created": created, "path": str(path), "snapshot": dict(snapshot)}


# ---------------------------------------------------------------------------
# Verified reads
# ---------------------------------------------------------------------------

def load_snapshot(book: str, snapshot_id: str) -> dict[str, Any]:
    path = _snapshot_path(book, snapshot_id)
    raw = _read_regular_file_bytes(path)
    if raw is None:
        raise SnapshotNotFound(f"snapshot {snapshot_id!r} not found for book {book!r}")
    payload = _verify_and_load(raw)
    if payload.get("snapshot_id") != snapshot_id or payload.get("book") != book:
        raise SnapshotCorrupt("snapshot identity does not match requested book/snapshot_id")
    return payload


def _scan_verified_snapshots(book: str) -> list[dict[str, Any]]:
    directory = snapshot_dir(book)
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        raw = _read_regular_file_bytes(path)
        if raw is None:
            continue
        out.append(_verify_and_load(raw))
    return out


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
