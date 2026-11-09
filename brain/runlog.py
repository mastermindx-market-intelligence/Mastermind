"""Run-scoped logger — DEEP, granular trace of every bot session.

Every call, result, reasoning chunk, and trade step is written as a JSON-lines
row to data/brain/runs/<run_id>.jsonl.  An index file (index.jsonl) is kept
separately so list_runs() is O(n_runs) not O(n_steps).

Thread/process safety: each step append is a single write()+flush(); the index
update renames an atomic temp file.  Crashes between lines leave an incomplete
.jsonl but never corrupt existing data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import stat
from contextlib import contextmanager
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "brain" / "runs"
_INDEX = _RUNS_DIR / "index.jsonl"
_LOCK = threading.RLock()          # index writes are rare; single lock is fine
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}")


def validate_run_id(run_id: object) -> str:
    """Boundary allowlist for run ids (API query params land here).

    Plain token only: alnum first, then alnum/`_`/`.`/`:`/`-`, max 96 chars,
    never `..` — same charset as ``portfolio_id`` so ids stay compatible.
    Raises ``ValueError`` (fixed text, no caller data) on anything else.
    """
    if type(run_id) is not str or not _RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
        raise ValueError("invalid run_id")
    return run_id


def _run_path(run_id: str) -> Path:
    # Validation lives here, at the filesystem boundary, so every caller
    # (read_run, log_step, start_run, ...) is covered — not just the API.
    run_id = validate_run_id(run_id)
    base = os.path.normpath(str(_RUNS_DIR))
    candidate = os.path.normpath(os.path.join(base, f"{run_id}.jsonl"))
    # Containment guard: the normalized candidate must sit directly inside the
    # runs directory. Redundant with the allowlist by construction, kept as the
    # explicit check so the join can never escape even if the charset changes.
    if not candidate.startswith(base + os.sep) or os.path.dirname(candidate) != base:
        raise ValueError("invalid run_id")
    return Path(candidate)


def _ensure_dir():
    _RUNS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def start_run(kind: str, title: str = "") -> str:
    """Open a new run; return its run_id (timestamp-based, sortable)."""
    _ensure_dir()
    ts = _now()
    # run_id = UTC timestamp without colons/dots so it's a safe filename
    run_id = ts.replace(":", "-").replace(".", "-").replace("+", "Z")
    meta = {"run_id": run_id, "ts": ts, "kind": kind, "title": title or kind,
            "n_steps": 0, "cost_usd": None, "summary": ""}
    # write seed row to the run file (makes the file exist even if no steps follow)
    with portfolio_lock():
        path = _run_path(run_id)
        # Timestamp collision must never truncate an existing selected original.
        with path.open("x", encoding="utf-8") as fh:
            fh.write(json.dumps({"_meta": meta}) + "\n")
    return run_id


def log_step(run_id: str, type: str, title: str, detail: str, **extra) -> None:  # noqa: A002
    """Append one step to the run file.  Never raises — errors are swallowed."""
    try:
        step: dict[str, Any] = {"ts": _now(), "type": type, "title": title,
                                 "detail": detail[:4000], **extra}
        line = json.dumps(step, default=str) + "\n"
        path = _run_path(run_id)
        with portfolio_lock():
            if _has_portfolio_protocol(path):
                return
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
    except Exception:
        pass   # logging must never break the session


def end_run(run_id: str, summary: str = "", cost_usd: float | None = None) -> None:
    """Finalise a run: count its steps, write a summary, update the index."""
    try:
        _ensure_dir()
        path = _run_path(run_id)
        n_steps = 0
        ts = _now()
        kind = "daily"
        title = run_id

        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            for raw in lines:
                try:
                    obj = json.loads(raw)
                    if "_meta" in obj:
                        ts = obj["_meta"].get("ts", ts)
                        kind = obj["_meta"].get("kind", kind)
                        title = obj["_meta"].get("title", title)
                    else:
                        n_steps += 1
                except Exception:
                    pass

        entry = {"run_id": run_id, "ts": ts, "kind": kind, "title": title,
                 "n_steps": n_steps, "cost_usd": cost_usd, "summary": summary}

        with portfolio_lock():
            if _has_portfolio_protocol(path):
                return
            rows = [row for row in _portfolio_index() if row.get("run_id") != run_id]
            old_index = strict_read(_INDEX, absent=True)
            rows.append(entry)
            durable_replace(_INDEX, b"".join(canonical(row) + b"\n" for row in rows),
                            expected=old_index)
    except Exception:
        pass   # never breaks the caller


# ---------------------------------------------------------------------------
# readers
# ---------------------------------------------------------------------------

def list_runs() -> list[dict]:
    """Selected summaries come from their validated original run revision."""
    try:
        with portfolio_lock():
            rows = [_portfolio_public_read(row) if "_fabric_portfolio" in row
                    else {key: value for key, value in row.items() if not key.startswith("_")}
                    for row in _portfolio_index()]
        rows.sort(key=lambda row: row.get("ts") or "", reverse=True)
        return [{key: value for key, value in row.items() if key != "steps"} for row in rows]
    except Exception:
        return []


def read_run(run_id: str | None = None) -> dict:
    """Return {run_id, ts, kind, steps:[...]} for the given run (or the latest)."""
    try:
        if run_id is None:
            idx = list_runs()
            if not idx:
                return {"run_id": None, "ts": None, "kind": None, "steps": []}
            run_id = idx[0]["run_id"]

        try:
            run_id = validate_run_id(run_id)
        except ValueError:
            # Rejected at the boundary; the id is attacker data — not echoed.
            return {"run_id": None, "ts": None, "kind": None, "steps": [],
                    "error": "invalid run_id"}

        with portfolio_lock():
            entry = next((row for row in _portfolio_index()
                          if row.get("run_id") == run_id and "_fabric_portfolio" in row), None)
            if entry is not None:
                return _portfolio_public_read(entry)
        path = _run_path(run_id)
        if not path.exists():
            return {"run_id": run_id, "ts": None, "kind": None, "steps": [],
                    "error": "run file not found"}

        ts, kind, title = None, None, run_id
        steps = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(raw)
                if "_meta" in obj:
                    ts = obj["_meta"].get("ts")
                    kind = obj["_meta"].get("kind")
                    title = obj["_meta"].get("title", run_id)
                elif "_fabric_portfolio" not in obj:
                    steps.append(obj)
            except Exception:
                pass
        return {"run_id": run_id, "ts": ts, "kind": kind, "title": title, "steps": steps}
    except Exception:
        # Never surface exception text: this dict is the /api/runlog response
        # body. Detail stays server-side only (stack-trace-exposure guard).
        _log.exception("runlog read failed")
        return {"run_id": run_id, "ts": None, "kind": None, "steps": [],
                "error": "runlog read failed"}


# ---------------------------------------------------------------------------
# Strict selected US session protocol in the incumbent runs/index owners.
# Legacy traces remain compatible; none of their best-effort writes are receipts.
# ---------------------------------------------------------------------------

_PORTFOLIO_SCHEMA = "mastermind.runlog.portfolio.v1"
_PORTFOLIO_INDEX_SCHEMA = "mastermind.runlog.portfolio_index.v1"
_PROTOCOL_LIMIT = 16 * 1024 * 1024
_PROTOCOL_LOCK_ROOT = Path(__file__).resolve().parent.parent


class PortfolioRunError(RuntimeError):
    pass


def portfolio_book(value: str = "autonomous") -> str:
    """Closed active-book identity; model arguments never choose an owner."""
    if type(value) is not str or value not in ("autonomous", "china", "hk"):
        raise PortfolioRunError("fabric_portfolio_book_invalid")
    return value


def portfolio_title(book: str) -> str:
    return {"autonomous": "US portfolio Fabric", "china": "China portfolio Fabric",
            "hk": "Hong Kong portfolio Fabric"}[portfolio_book(book)]


def portfolio_id(value: str) -> str:
    if (type(value) is not str or value == "error"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", value)
            or ".." in value):
        raise PortfolioRunError("fabric_run_identity_invalid")
    return value


def strict_json(raw: str | bytes):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise PortfolioRunError("fabric_duplicate_json_key")
            out[key] = value
        return out
    def nonfinite(_value):
        raise PortfolioRunError("fabric_nonfinite_json")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
        canonical(value)  # JSON exponent overflow (1e999) must also refuse.
        return value
    except (ValueError, UnicodeError, TypeError) as exc:
        raise PortfolioRunError("fabric_json_invalid") from exc


def canonical(value) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PortfolioRunError("fabric_json_invalid") from exc


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sync_directory(path: Path) -> None:
    """Create/sync the actual directory chain, rejecting redirected ancestors."""
    path = Path(path).absolute()
    chain = list(reversed([path, *path.parents]))
    for parent in chain:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            parent.mkdir(mode=0o700)
            info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise PortfolioRunError("fabric_directory_invalid")
    # The created entry and every ancestor are durable before the next effect.
    for parent in reversed(chain):
        fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _read_parent(path: Path) -> int:
    """Open each real directory without following a redirected ancestor."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path.anchor, flags)
    try:
        for component in path.parent.parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def strict_read(path: Path, *, absent: bool = False,
                limit: int = _PROTOCOL_LIMIT) -> bytes | None:
    path = Path(os.path.abspath(path))
    parent_fd = fd = current_parent_fd = None
    try:
        parent_fd = _read_parent(path)
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise PortfolioRunError("fabric_receipt_file_invalid")
        fd = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        actual = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) != (before.st_dev, before.st_ino):
            raise PortfolioRunError("fabric_receipt_file_changed")
        with os.fdopen(fd, "rb", closefd=False) as fh:
            raw = fh.read(limit + 1)
        after = os.fstat(fd)
        # Rewalk the current pathname without symlinks, rather than trusting the
        # still-open old parent after a concurrent directory rename.
        current_parent_fd = _read_parent(path)
        current = os.stat(path.name, dir_fd=current_parent_fd, follow_symlinks=False)
        current_parent, original_parent = os.fstat(current_parent_fd), os.fstat(parent_fd)
        expected = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if (len(raw) > limit
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != expected
                or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != expected
                or (current_parent.st_dev, current_parent.st_ino) !=
                    (original_parent.st_dev, original_parent.st_ino)):
            raise PortfolioRunError("fabric_receipt_file_changed")
        return raw
    except FileNotFoundError:
        if absent and fd is None:
            return None
        raise PortfolioRunError("fabric_receipt_missing") from None
    except OSError as exc:
        raise PortfolioRunError("fabric_receipt_file_invalid") from exc
    finally:
        for opened in (current_parent_fd, fd, parent_fd):
            if opened is not None:
                os.close(opened)


def strict_rows(path: Path, *, absent: bool = False) -> list[dict]:
    raw = strict_read(path, absent=absent)
    if raw is None or raw == b"":
        return []
    if not raw.endswith(b"\n"):
        raise PortfolioRunError("fabric_partial_receipt")
    rows = [strict_json(line) for line in raw.splitlines()]
    if any(type(row) is not dict for row in rows):
        raise PortfolioRunError("fabric_receipt_rows_invalid")
    return rows


def durable_replace(path: Path, raw: bytes, *, expected: bytes | None) -> None:
    """Caller owns the incumbent lock; readback is part of this receipt."""
    path = Path(path)
    if type(raw) is not bytes or len(raw) > _PROTOCOL_LIMIT:
        raise PortfolioRunError("fabric_receipt_limit")
    sync_directory(path.parent)
    if strict_read(path, absent=True) != expected:
        raise PortfolioRunError("fabric_receipt_cas_conflict")
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
        if strict_read(path) != raw:
            raise PortfolioRunError("fabric_receipt_readback_failed")
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


@contextmanager
def portfolio_lock():
    """Use the incumbent advisory-lock owner for short runs/index transactions."""
    from control_plane import locks
    with _LOCK:
        lock = locks.acquire("global:brain_runlog", root=_PROTOCOL_LOCK_ROOT)
        if lock is None:
            raise PortfolioRunError("fabric_runlog_busy")
        with lock:
            yield


def _has_portfolio_protocol(path: Path) -> bool:
    raw = strict_read(path, absent=True)
    # Even a damaged selected row is fenced from permissive legacy mutation.
    if raw is not None and b'"_fabric_portfolio"' in raw:
        return True
    return any(row.get("run_id") == path.stem and "_fabric_portfolio" in row
               for row in _portfolio_index())


def _portfolio_index() -> list[dict]:
    rows = strict_rows(_INDEX, absent=True)
    owned = [row for row in rows if "_fabric_portfolio" in row]
    ids = []
    for row in owned:
        value = row["_fabric_portfolio"]
        if (type(value) is not dict
                or set(value) != {"schema", "book", "request_digest"}
                or value["schema"] != _PORTFOLIO_INDEX_SCHEMA
                or type(value["book"]) is not str or value["book"] not in ("autonomous", "china", "hk")
                or not re.fullmatch(r"[0-9a-f]{64}", str(value["request_digest"]))):
            raise PortfolioRunError("fabric_run_index_invalid")
        ids.append(portfolio_id(row.get("run_id")))
    if len(ids) != len(set(ids)):
        raise PortfolioRunError("fabric_run_index_duplicate")
    return rows


def _portfolio_projection(doc: dict, anchor: dict) -> dict:
    """Closed public fields only; an intent is not proof of provider execution."""
    state = doc["state"]
    public_steps, models = [], set()
    for index, step in enumerate(state["steps"]):
        observation = step.get("observation") or {}
        model = observation.get("serving_model")
        pool = (observation.get("routing") or {}).get("pool")
        if model is not None:
            models.add(model)
        public_steps.append({
            "type": "model", "title": f"Fabric inference {index + 1}",
            "detail": "Original request " + step["state"], "status": step["state"],
            "model": model, "pool": pool})
        for effect in state["tools"]:
            if effect["request_id"] == step["request_id"]:
                public_steps.append({
                    "type": "tool", "title": effect["name"], "status": effect["state"],
                    "detail": "Handler returned" if effect["state"] == "complete" else "Original tool intent"})
    for ordinal, step in enumerate(public_steps, 1):
        step["ordinal"] = ordinal
    out = state.get("out") or {}
    decision = (out.get("target_status") if out.get("decision_effective") is True
                and out.get("target_status") in {"queued", "executed"} else "unaccepted")
    phase = state["phase"]
    return {
        "run_id": state["run_id"], "ts": anchor["ts"], "kind": state["book"],
        "title": portfolio_title(state["book"]), "projection_revision": doc["revision"],
        "status": phase, "n_steps": len(public_steps), "cost_usd": None,
        "summary": (f'{len(state["steps"])} inference intents; {len(state["tools"])} tool intents; '
                    f'{phase}; decision {decision}'),
        "model": next(iter(models)) if len(models) == 1 else None,
        "models": sorted(models), "decision_status": decision, "steps": public_steps}


def _portfolio_public_read(entry: dict) -> dict:
    """Caller owns portfolio_lock; invalid originals never expose raw private rows."""
    try:
        return _portfolio_projection(_portfolio_read(entry), entry)
    except Exception:
        return {"run_id": entry.get("run_id"), "ts": entry.get("ts"),
                "kind": entry["_fabric_portfolio"]["book"],
                "title": portfolio_title(entry["_fabric_portfolio"]["book"]), "status": "unavailable", "n_steps": None,
                "cost_usd": None, "summary": "Original run record is unavailable",
                "model": None, "models": [], "decision_status": "unknown", "steps": []}


def _portfolio_read(entry: dict) -> dict:
    rows = strict_rows(_run_path(portfolio_id(entry["run_id"])))
    if len(rows) != 2 or set(rows[0]) != {"_meta"} or set(rows[1]) != {"_fabric_portfolio"}:
        raise PortfolioRunError("fabric_run_protocol_invalid")
    envelope = rows[1]["_fabric_portfolio"]
    if (type(envelope) is not dict
            or set(envelope) != {"schema", "revision", "state", "digest"}
            or envelope["schema"] != _PORTFOLIO_SCHEMA
            or type(envelope["revision"]) is not int or envelope["revision"] < 0
            or type(envelope["state"]) is not dict
            or digest(envelope["state"]) != envelope["digest"]):
        raise PortfolioRunError("fabric_run_protocol_invalid")
    state = envelope["state"]
    if (state.get("run_id") != entry["run_id"]
            or state.get("book") != entry["_fabric_portfolio"]["book"]
            or digest(state.get("request")) != entry["_fabric_portfolio"]["request_digest"]
            or rows[0]["_meta"].get("run_id") != entry["run_id"]):
        raise PortfolioRunError("fabric_run_protocol_identity_conflict")
    doc = {"revision": envelope["revision"], "state": copy.deepcopy(state)}
    from brain.fabric_portfolio import _validate
    _validate(doc)  # Semantic custody is checked before phase can mean complete.
    if rows[0]["_meta"] != _portfolio_projection(doc, entry):
        raise PortfolioRunError("fabric_run_public_projection_conflict")
    return doc


def portfolio_original_locked(run_id: str, *, book: str = "autonomous") -> dict | None:
    """Read this exact anchored original; caller owns portfolio_lock."""
    run_id, book = portfolio_id(run_id), portfolio_book(book)
    for entry in _portfolio_index():
        if entry.get("run_id") != run_id or "_fabric_portfolio" not in entry:
            continue
        if entry["_fabric_portfolio"]["book"] != book:
            raise PortfolioRunError("fabric_run_book_conflict")
        return _portfolio_read(entry)
    return None


def portfolio_lookup(run_id: str | None = None, *, book: str = "autonomous") -> dict | None:
    """Recover this book's original; explicit foreign IDs always conflict."""
    book = portfolio_book(book)
    if run_id is not None:
        portfolio_id(run_id)
    with portfolio_lock():
        rows = _portfolio_index()
        for row in rows:
            if (row.get("run_id") == run_id and "_fabric_portfolio" in row
                    and row["_fabric_portfolio"]["book"] != book):
                raise PortfolioRunError("fabric_run_book_conflict")
        records = [_portfolio_read(row) for row in rows if "_fabric_portfolio" in row
                   and row["_fabric_portfolio"]["book"] == book]
        pending = [doc for doc in records if doc["state"].get("phase") != "complete"]
        if len(pending) > 1:
            raise PortfolioRunError("fabric_multiple_unsettled_originals")
        if pending:
            return pending[0]
        if run_id is not None:
            return next((doc for doc in records if doc["state"]["run_id"] == run_id), None)
        return None


def portfolio_claim(state: dict) -> dict:
    """Anchor identity before its run file; a missing anchored file remains held."""
    run_id = portfolio_id(state.get("run_id"))
    book = portfolio_book(state.get("book"))
    if type(state.get("request")) is not dict:
        raise PortfolioRunError("fabric_run_claim_invalid")
    with portfolio_lock():
        rows = _portfolio_index()
        for row in rows:
            if row.get("run_id") == run_id:
                raise PortfolioRunError("fabric_original_already_owned")
            if ("_fabric_portfolio" in row and row["_fabric_portfolio"]["book"] == book
                    and _portfolio_read(row)["state"].get("phase") != "complete"):
                raise PortfolioRunError("fabric_original_already_owned")
        if strict_read(_run_path(run_id), absent=True) is not None:
            raise PortfolioRunError("fabric_run_identity_conflict")
        meta = {"run_id": run_id, "ts": _now(), "kind": book,
                "title": portfolio_title(book), "n_steps": 0, "cost_usd": None, "summary": ""}
        entry = {**meta, "_fabric_portfolio": {"schema": _PORTFOLIO_INDEX_SCHEMA,
                 "book": book, "request_digest": digest(state["request"])}}
        old_index = strict_read(_INDEX, absent=True)
        durable_replace(_INDEX, b"".join(canonical(row) + b"\n" for row in [*rows, entry]),
                        expected=old_index)
        doc = {"revision": 0, "state": copy.deepcopy(state)}
        envelope = {"schema": _PORTFOLIO_SCHEMA, **doc, "digest": digest(doc["state"])}
        meta = _portfolio_projection(doc, entry)
        durable_replace(_run_path(run_id), canonical({"_meta": meta}) + b"\n"
                        + canonical({"_fabric_portfolio": envelope}) + b"\n", expected=None)
        if _portfolio_read(entry) != doc:
            raise PortfolioRunError("fabric_run_claim_readback_failed")
        return doc


def portfolio_save(doc: dict) -> None:
    """Compare the durable revision; never recover a lost acknowledgement by retry."""
    state = doc["state"]
    with portfolio_lock():
        entry = next((row for row in _portfolio_index()
                      if row.get("run_id") == state["run_id"] and "_fabric_portfolio" in row), None)
        if entry is None:
            raise PortfolioRunError("fabric_run_anchor_missing")
        old = _portfolio_read(entry)
        if old["revision"] != doc["revision"]:
            raise PortfolioRunError("fabric_run_revision_conflict")
        if (state.get("book") != entry["_fabric_portfolio"]["book"]
                or digest(state["request"]) != entry["_fabric_portfolio"]["request_digest"]):
            raise PortfolioRunError("fabric_run_request_changed")
        if ("entry_context" in old["state"]
                and state.get("entry_context") != old["state"]["entry_context"]):
            raise PortfolioRunError("fabric_run_entry_changed")
        if "local_gate" in old["state"] and state.get("local_gate") != old["state"]["local_gate"]:
            raise PortfolioRunError("fabric_run_gate_changed")
        from brain.fabric_portfolio import _validate
        _validate(doc)
        path = _run_path(state["run_id"])
        raw = strict_read(path)
        next_doc = {"revision": doc["revision"] + 1, "state": copy.deepcopy(state)}
        meta = {"_meta": _portfolio_projection(next_doc, entry)}
        envelope = {"schema": _PORTFOLIO_SCHEMA, **next_doc, "digest": digest(state)}
        durable_replace(path, canonical(meta) + b"\n"
                        + canonical({"_fabric_portfolio": envelope}) + b"\n", expected=raw)
        if _portfolio_read(entry) != next_doc:
            raise PortfolioRunError("fabric_run_readback_failed")
        doc["revision"] = next_doc["revision"]


def portfolio_pending_locked(book: str = "autonomous") -> dict | None:
    """Internal per-book guard; the caller already holds portfolio_lock."""
    book = portfolio_book(book)
    records = [_portfolio_read(row) for row in _portfolio_index() if "_fabric_portfolio" in row
               and row["_fabric_portfolio"]["book"] == book]
    pending = [doc for doc in records if doc["state"].get("phase") != "complete"]
    if len(pending) > 1:
        raise PortfolioRunError("fabric_multiple_unsettled_originals")
    return pending[0] if pending else None


def durable_existing(path: Path, expected: bytes) -> None:
    """Reconcile a visible original whose final sync/readback may have failed."""
    if strict_read(path) != expected:
        raise PortfolioRunError("fabric_receipt_readback_failed")
    path = Path(os.path.abspath(path))
    parent_fd = _read_parent(path)
    try:
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        fd = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or
                    (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) !=
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
                raise PortfolioRunError("fabric_receipt_file_changed")
            with os.fdopen(fd, "rb", closefd=False) as fh:
                if fh.read(_PROTOCOL_LIMIT + 1) != expected:
                    raise PortfolioRunError("fabric_receipt_readback_failed")
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)
    sync_directory(path.parent)
    if strict_read(path) != expected:
        raise PortfolioRunError("fabric_receipt_readback_failed")
