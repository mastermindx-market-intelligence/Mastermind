"""Append-only thesis ledger (data/brain/theses.jsonl) — the accountability spine.

Interval-gated against double-counting (one open thesis per subject), mirroring the
ai_desk ledger discipline. Resolved outcomes are graded by brain/scorer.py.

The logical lifecycle remains append/open -> close. Physical persistence is a locked,
atomic whole-file replacement so a concurrent append cannot race the one-open-subject
check and a failed append/close cannot leave a torn JSONL accountability record.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

_LEDGER = Path(__file__).resolve().parent.parent / "data" / "brain" / "theses.jsonl"
_LOCAL_LOCK = threading.RLock()


def _lock_path() -> Path:
    # Derive from _LEDGER at call time so tests/alternate roots that monkeypatch the canonical
    # ledger automatically share the matching lock instead of a stale module-level path.
    return _LEDGER.with_name(f".{_LEDGER.name}.lock")


@contextmanager
def _ledger_lock():
    """Serialize ledger mutations across both threads and processes."""
    with _LOCAL_LOCK:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        lock = _lock_path().open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except OSError:
                    # The data effect, if any, was already decided by atomic os.replace below.
                    pass
        finally:
            try:
                lock.close()
            except OSError:
                # Cleanup must preserve the committed result or the original operation error.
                pass


def _read_unlocked() -> list[dict]:
    try:
        _LEDGER.lstat()
    except FileNotFoundError:
        return []
    # Deliberately fail closed on malformed historical evidence. This owner does not silently
    # discard or quarantine accountability rows; callers must repair corrupt evidence explicitly.
    rows = [json.loads(line) for line in _LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("thesis ledger rows must be mappings")
    return rows


def _read() -> list[dict]:
    # Writers publish via atomic replace, so an unlocked reader sees either the complete prior file
    # or the complete successor. It never needs to wait on the mutation lock for a partial temp file.
    return _read_unlocked()


def _atomic_write(rows: list[dict]) -> None:
    """Replace the ledger atomically; on exception the previous canonical bytes stay intact."""
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, default=str) + "\n" for row in rows)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=_LEDGER.parent,
            prefix=f".{_LEDGER.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, _LEDGER)
        tmp_name = None
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def open_subjects() -> set[str]:
    return {t["subject"] for t in _read() if t.get("status", "open") == "open"}


def _require_thesis_id(row: dict) -> str:
    """Require an exact canonical identity without coercion, trimming or fallback."""
    thesis_id = row.get("id")
    if not isinstance(thesis_id, str) or not thesis_id.strip():
        raise ValueError("thesis id must be a nonblank string")
    return thesis_id


def append_receipt(doc: dict) -> dict:
    """Append once or identify the single canonical open thesis for this subject.

    Invalid or ambiguous identity is an error, not a deduplication receipt.
    """
    record = dict(doc)
    thesis_id = _require_thesis_id(record)
    subject = record["subject"]
    with _ledger_lock():
        rows = _read_unlocked()
        matching = [
            row for row in rows
            if row.get("status", "open") == "open" and row["subject"] == subject
        ]
        if len(matching) > 1:
            raise ValueError("multiple open theses for subject")
        if matching:
            return {
                "appended": False,
                "thesis_id": _require_thesis_id(matching[0]),
                "reason": "open_subject_exists",
            }
        rows.append({**record, "status": "open"})
        _atomic_write(rows)
        return {"appended": True, "thesis_id": thesis_id, "reason": None}


def append(doc: dict) -> bool:
    """Compatibility API: append unless an open thesis exists; return appended?"""
    return append_receipt(doc)["appended"]


def close(subject: str, resolution: str = "closed", *, outcome: int | None = None,
          realized: float | None = None) -> int:
    """Mark every OPEN thesis on `subject` closed (rewriting the JSONL). Returns the count closed.

    Without this the append-only ledger keeps a name's first thesis 'open' forever: append() refuses
    a new thesis while one is open (the dedup lock), so a name that left and re-entered the book
    could never get a refreshed thesis, and the open-thesis set (which feeds the conviction candidate
    pool) accreted stale names indefinitely.
    """
    with _ledger_lock():
        rows = _read_unlocked()
        n = 0
        for t in rows:
            if t.get("subject") == subject and t.get("status", "open") == "open":
                t["status"] = resolution
                if outcome is not None:
                    t["outcome"] = outcome
                if realized is not None:
                    t["realized"] = realized
                n += 1
        if n:
            _atomic_write(rows)
        return n


def all_theses() -> list[dict]:
    return _read()
