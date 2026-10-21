"""Immutable Portfolio V3 evidence storage; never a portfolio or runtime writer.

Publication uses a fully synced private temporary inode and a no-replace link.
Readers cannot see a half-written final snapshot. Only this store's temporary
files are removed; historical evidence is never replaced or pruned here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any

from control_plane.wake_events import canonical_json_bytes
from portfolio import decision_snapshot_contracts as c

_ROOT = Path(__file__).resolve().parent.parent
_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FILENAME = re.compile(r"[0-9a-f]{64}\.json\Z")
MAX_SCAN_FILES = 4096
MAX_SCAN_BYTES = 67_108_864


class DecisionSnapshotError(ValueError):
    """Snapshot operation failed without granting any other authority."""


class SnapshotNotFound(DecisionSnapshotError):
    pass


class SnapshotCorrupt(DecisionSnapshotError):
    pass


class SnapshotInvalidRequest(DecisionSnapshotError):
    pass


class SnapshotWriteUncertain(DecisionSnapshotError):
    """Read back the same identity; do not mint a replacement operation."""


def _book(book: str) -> None:
    if book != "autonomous":
        raise SnapshotInvalidRequest("only the autonomous evidence store is supported")


def _identity(snapshot_id: str) -> None:
    if not isinstance(snapshot_id, str) or _ID.fullmatch(snapshot_id) is None:
        raise SnapshotInvalidRequest("invalid snapshot identity")


def snapshot_dir(book: str) -> Path:
    _book(book)
    return _ROOT / "data" / "shadow" / "decision_snapshots" / "autonomous"


def _snapshot_path(book: str, snapshot_id: str) -> Path:
    _identity(snapshot_id)
    return snapshot_dir(book) / (snapshot_id[7:] + ".json")


@contextmanager
def _directory(book: str, *, create: bool = False):
    _book(book)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current = None
    try:
        current = os.open(_ROOT, flags)
        for part in ("data", "shadow", "decision_snapshots", "autonomous"):
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                    # A synced leaf alone does not durably link newly created
                    # ancestors. Sync each parent before publishing beneath it.
                    os.fsync(current)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        yield current
    except FileNotFoundError as exc:
        raise SnapshotNotFound("snapshot directory or record not found") from exc
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise SnapshotCorrupt("symlink or non-directory in snapshot path") from exc
        raise DecisionSnapshotError("snapshot filesystem operation failed") from exc
    finally:
        if current is not None:
            os.close(current)


def _checked(snapshot: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    try:
        raw = c._json_bytes(snapshot)
        value = json.loads(raw)
        c.verify_snapshot(value)
        if set(value['sections']) != set(c.SECTION_IDS):
            raise c.DecisionSnapshotContractError('stored evidence must describe all twelve domains')
        return value, raw
    except (c.DecisionSnapshotContractError, TypeError, ValueError) as exc:
        raise SnapshotCorrupt("snapshot contract or digest verification failed") from exc


def compose_snapshot(book: str, *, decision_cutoff: str, recorded_at: str,
                     capture: Mapping[str, Any],
                     same_cutoff_prior_snapshot_ids: Sequence[str]) -> dict[str, Any]:
    _book(book)
    try:
        cutoff = c.parse_utc_timestamp(decision_cutoff, field="decision_cutoff")
        recorded = c.parse_utc_timestamp(recorded_at, field="recorded_at")
        bundle = json.loads(c._json_bytes(capture))
        if set(bundle) != {"sources", "sections", "gaps"}:
            raise SnapshotInvalidRequest("capture has unknown or missing fields")
        if set(bundle["sections"]) != set(c.SECTION_IDS):
            raise SnapshotInvalidRequest("capture must describe all twelve domains")
        sources = sorted(bundle["sources"], key=lambda row: row["source_id"])
        gaps = sorted(bundle["gaps"], key=lambda row: tuple(str(row.get(k, "")) for k in ("code", "source_id", "owner", "detail")))
        sections = {key: bundle["sections"][key] for key in c.SECTION_IDS}
        states = [s["coverage_state"] for s in sections.values()]
        coverage = "BLOCKED" if "BLOCKED" in states else ("COMPLETE" if set(states) == {"COMPLETE"} and not gaps else "PARTIAL")
        if isinstance(same_cutoff_prior_snapshot_ids, (str, bytes)):
            raise SnapshotInvalidRequest("predecessors must be an identity sequence")
        prior = sorted(same_cutoff_prior_snapshot_ids)
        correction = "CORRECTED_GENERATION_AVAILABLE" if prior else "ORIGINAL"
        payload = {
            "schema": c.SNAPSHOT_SCHEMA, "book": book, "decision_cutoff": cutoff,
            "recorded_at": recorded, "state": correction if prior else coverage,
            "coverage_state": coverage,
            "summary": {"sources_total": len(sources), "sources_available": sum(r["status"] == "AVAILABLE" for r in sources),
                        "domains_complete": states.count("COMPLETE"), "domains_partial": states.count("PARTIAL") + states.count("UNKNOWN"),
                        "domains_blocked": states.count("BLOCKED")},
            "source_generation_set": [{"source_id": r["source_id"], "correction_generation": r["correction_generation"]} for r in sources],
            "sources": sources, "sections": sections, "gaps": gaps,
            "correction": {"status": correction, "same_cutoff_prior_snapshot_ids": prior},
            "authority": {"write_permitted": False, "execution_authority": False, "numeric_target_authority": False},
        }
        return c.seal_snapshot(payload)
    except (c.DecisionSnapshotContractError, KeyError, TypeError, AttributeError) as exc:
        raise SnapshotInvalidRequest("invalid capture, clocks or correction lineage") from exc


def _read_at(directory: int, filename: str) -> tuple[dict[str, Any], bytes]:
    handle = None
    try:
        handle = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(handle)
        if not stat.S_ISREG(before.st_mode) or before.st_size > c.MAX_SNAPSHOT_BYTES:
            raise SnapshotCorrupt("snapshot is non-regular or oversized")
        chunks = []; remaining = c.MAX_SNAPSHOT_BYTES + 1
        while remaining:
            chunk = os.read(handle, min(remaining, 65_536))
            if not chunk:
                break
            chunks.append(chunk); remaining -= len(chunk)
        raw = b"".join(chunks); after = os.fstat(handle)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise SnapshotCorrupt("snapshot changed during read")
        if len(raw) > c.MAX_SNAPSHOT_BYTES:
            raise SnapshotCorrupt("snapshot exceeds byte limit")
        value, canonical = _checked(json.loads(raw))
        if raw != canonical or value["snapshot_id"][7:] + ".json" != filename:
            raise SnapshotCorrupt("snapshot bytes or address disagree")
        return value, raw
    except FileNotFoundError as exc:
        raise SnapshotNotFound("snapshot not found") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotCorrupt("snapshot is not valid JSON") from exc
    except OSError as exc:
        raise SnapshotCorrupt("snapshot cannot be safely read") from exc
    finally:
        if handle is not None:
            os.close(handle)


def persist_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    value, raw = _checked(snapshot)
    path = _snapshot_path(value["book"], value["snapshot_id"])
    # Referential integrity belongs at this I/O boundary, not the pure seal.
    # Check before creating any directory or publishing the corrected record.
    for predecessor_id in value["correction"]["same_cutoff_prior_snapshot_ids"]:
        try:
            predecessor = load_snapshot(value["book"], predecessor_id)
        except SnapshotNotFound as exc:
            raise SnapshotInvalidRequest("correction predecessor does not exist") from exc
        if predecessor["decision_cutoff"] != value["decision_cutoff"]:
            raise SnapshotInvalidRequest("correction predecessor has a different decision cutoff")
    temporary = None
    with _directory(value["book"], create=True) as directory:
        try:
            existing, existing_raw = _read_at(directory, path.name)
        except SnapshotNotFound:
            existing = None
        if existing is not None:
            if existing_raw != raw:
                raise SnapshotCorrupt("existing content address differs; refusing overwrite")
            return {"snapshot_id": value["snapshot_id"], "created": False, "path": str(path)}
        temporary = ".snapshot-" + secrets.token_hex(16) + ".tmp"
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        linked = False
        try:
            try:
                view = memoryview(raw)
                while view:
                    written = os.write(handle, view)
                    if written <= 0:
                        raise OSError("short snapshot write")
                    view = view[written:]
                os.fsync(handle)
            finally:
                os.close(handle)
            try:
                os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                linked = True
            except FileExistsError:
                _, existing_raw = _read_at(directory, path.name)
                if existing_raw != raw:
                    raise SnapshotCorrupt("racing content address differs; refusing overwrite")
            os.fsync(directory)
        except OSError as exc:
            if linked:
                raise SnapshotWriteUncertain("publication durability unknown; read back " + value["snapshot_id"]) from exc
            raise DecisionSnapshotError("snapshot publication failed before final link") from exc
        finally:
            active_error = sys.exc_info()[1]
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=directory)
                    os.fsync(directory)
                except OSError as cleanup_error:
                    if active_error is not None:
                        active_error.add_note("Snapshot temporary-file cleanup/durability also failed; preserve the original result and identity.")
                    elif linked:
                        raise SnapshotWriteUncertain("publication cleanup durability unknown; read back " + value["snapshot_id"]) from cleanup_error
                    else:
                        raise DecisionSnapshotError("snapshot temporary-file cleanup failed") from cleanup_error
        return {"snapshot_id": value["snapshot_id"], "created": linked, "path": str(path)}


def load_snapshot(book: str, snapshot_id: str) -> dict[str, Any]:
    path = _snapshot_path(book, snapshot_id)
    with _directory(book) as directory:
        return _read_at(directory, path.name)[0]


def _page_args(offset: int, limit: int) -> None:
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise SnapshotInvalidRequest("offset and limit must be bounded non-Boolean integers")


def _manifest(p: Mapping[str, Any]) -> dict[str, Any]:
    return {key: p[key] for key in ("snapshot_id", "schema", "book", "decision_cutoff", "recorded_at", "state", "coverage_state", "summary", "correction", "authority")}


def list_snapshots(book: str, *, limit: int = 20) -> list[dict[str, Any]]:
    _book(book); _page_args(0, limit)
    manifests = []; observed = 0; read_bytes = 0
    try:
        with _directory(book) as directory:
            with os.scandir(directory) as entries:
                for entry in entries:
                    observed += 1
                    if observed > MAX_SCAN_FILES:
                        raise DecisionSnapshotError("snapshot directory scan limit exceeded")
                    if not entry.name.endswith(".json"):
                        continue
                    if _FILENAME.fullmatch(entry.name) is None or not entry.is_file(follow_symlinks=False):
                        raise SnapshotCorrupt("invalid file in snapshot directory")
                    try:
                        p, raw = _read_at(directory, entry.name)
                    except SnapshotNotFound as exc:
                        raise SnapshotCorrupt("snapshot disappeared during manifest scan") from exc
                    read_bytes += len(raw)
                    if read_bytes > MAX_SCAN_BYTES:
                        raise DecisionSnapshotError("snapshot scan byte limit exceeded")
                    manifests.append(_manifest(p))
    except SnapshotNotFound:
        return []
    manifests.sort(key=lambda row: (row["decision_cutoff"], row["recorded_at"], row["snapshot_id"]), reverse=True)
    return manifests[:limit]


def latest_snapshot(book: str) -> dict[str, Any] | None:
    rows = list_snapshots(book, limit=1)
    return load_snapshot(book, rows[0]["snapshot_id"]) if rows else None


def section_page(snapshot: Mapping[str, Any], section_id: str, *, offset: int, limit: int) -> dict[str, Any]:
    _page_args(offset, limit)
    if not isinstance(section_id, str) or section_id not in c.SECTION_IDS:
        raise SnapshotInvalidRequest("unknown section identity")
    p, _ = _checked(snapshot)
    if section_id not in p["sections"]:
        raise SnapshotInvalidRequest("snapshot does not contain requested section")
    source = p["sections"][section_id]; rows = source["rows"][offset:offset + limit]
    result = {**source, "snapshot_id": p["snapshot_id"], "offset": offset,
              "rows": rows, "rows_returned": len(rows), "stored_rows": len(source["rows"]),
              "next_offset": offset + len(rows) if offset + len(rows) < len(source["rows"]) else None}
    try:
        c._json_bytes(result, limit=c.MAX_SECTION_RESPONSE_BYTES)
    except c.DecisionSnapshotContractError as exc:
        raise SnapshotInvalidRequest("section response exceeds limit") from exc
    return result


def read_projection(book: str, *, snapshot_id: str | None, section_id: str | None,
                    offset: int, limit: int) -> dict[str, Any]:
    """Inspect existing evidence only; neither absent state nor reads create files.

    Without an explicit identity, return the latest manifest and up to ``limit``
    recent manifests. An exact identity reads only that record. Raw section rows
    are returned only when the caller explicitly names a bounded section.
    """
    _book(book)
    _page_args(offset, limit)
    if snapshot_id is not None:
        _identity(snapshot_id)
    if section_id is not None and (not isinstance(section_id, str) or section_id not in c.SECTION_IDS):
        raise SnapshotInvalidRequest('unknown section identity')
    if section_id is None and offset != 0:
        raise SnapshotInvalidRequest('offset requires an explicit section')
    if snapshot_id is None:
        manifests = list_snapshots(book, limit=limit)
        selected = load_snapshot(book, manifests[0]['snapshot_id']) if manifests else None
    else:
        selected = load_snapshot(book, snapshot_id)
        manifests = [_manifest(selected)]
    result = {
        'book': book,
        'status': 'AVAILABLE' if selected is not None else 'ABSENT',
        'snapshot': _manifest(selected) if selected is not None else None,
        'snapshots': manifests,
        'section': section_page(selected, section_id, offset=offset, limit=limit)
            if selected is not None and section_id is not None else None,
        'authority': {'write_permitted': False, 'execution_authority': False, 'numeric_target_authority': False},
    }
    try:
        c._json_bytes(result)
    except c.DecisionSnapshotContractError as exc:
        raise SnapshotInvalidRequest('projection response exceeds its closed JSON bounds') from exc
    return result
