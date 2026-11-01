"""Self-Directed book — the THIRD Mastermind portfolio.

DOCTRINE.md frames two consumers of the engine: SELF (the bot's own autonomous paper
book) and OPERATOR (read-only advisories over the user's real holdings). This is the
third and only book the *user* drives directly: you search the name, you size the order,
you write the thesis. The engine here is a dumb, honest executor — no scorer, no gate, no
auto-execution. PAPER ONLY.

Rules (kept consistent with the rest of the system):
  - Long-only, no leverage. Buys are bounded by cash; sells are bounded by shares held.
  - Market OPEN  → the order fills immediately at the live market price.
  - Market CLOSED → the order is queued PENDING and fills at the NEXT session's OPEN price.
  - Pending orders settle lazily: any read (book/history) or new order, while the market is
    open, first sweeps the pending queue and fills it at the day's open (Polygon snapshot
    `day.o`), falling back to the last price if the open isn't published yet.

State (data/portfolio/self_directed/ — fully isolated from the autonomous account.json):
  account.json   — inception_date, starting_nav, cash, positions {TICKER:{shares,avg_cost}}
  fills.jsonl    — one line per executed fill (feeds the Trade History blotter)
  pending.json   — queued orders awaiting the next open
  theses.json    — {TICKER: {note, updated_at}} — your conviction notes

Every external dependency (Polygon, the macro price store, the market clock) is imported
lazily and is optional, so this module imports and unit-tests cleanly with no vendor data —
inject `price`/`prices`/`market_open`/`now` to pin behaviour.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import stat
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, Optional
from uuid import uuid4

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data" / "portfolio" / "self_directed"
_ACCOUNT_PATH = _DATA / "account.json"
_FILLS_PATH = _DATA / "fills.jsonl"
_PENDING_PATH = _DATA / "pending.json"
_THESES_PATH = _DATA / "theses.json"
_NAV_PATH = _DATA / "nav_history.jsonl"      # W-L / L1: this book now advances a NAV history too

_STARTING_NAV = 1_000_000.0


# ---------------------------------------------------------------------------
# persistence helpers
# ---------------------------------------------------------------------------

def _check_book_dir(data_dir: Path) -> tuple[str | None, OSError | None]:
    """Classify a book's data directory WITHOUT creating it (E14 ruling b/c).

    Returns (None, None) for an existing directory, else (problem, exc) with problem one of
    ``data_dir_missing``, ``data_dir_not_directory``, ``data_dir_unreadable:<ExcName>``.
    """
    try:
        st = os.stat(data_dir)
    except FileNotFoundError as exc:
        return "data_dir_missing", exc
    except OSError as exc:
        return f"data_dir_unreadable:{type(exc).__name__}", exc
    if not stat.S_ISDIR(st.st_mode):
        return "data_dir_not_directory", None
    return None, None


def _classify_account_path(account_path: Path) -> tuple[str, str | None, OSError | None]:
    """Classify account.json by stat only (E14 ruling a/b): ("absent"|"present"|"invalid", problem, exc).

    ``absent`` ONLY when the book directory exists and ``os.lstat`` raises FileNotFoundError.
    A dangling symlink is ``invalid``/``dangling_symlink``; any other stat failure is
    ``invalid``/``unreadable:<ExcName>``; a directory problem is ``invalid``/``data_dir_*``.
    """
    problem, exc = _check_book_dir(account_path.parent)
    if problem:
        return "invalid", problem, exc
    try:
        os.lstat(account_path)
    except FileNotFoundError:
        return "absent", None, None
    except OSError as exc:
        return "invalid", f"unreadable:{type(exc).__name__}", exc
    try:
        os.stat(account_path)
    except FileNotFoundError as exc:
        return "invalid", "dangling_symlink", exc
    except OSError as exc:
        return "invalid", f"unreadable:{type(exc).__name__}", exc
    return "present", None, None


def _require_book_dir(*, step: str = "require_book_dir") -> Path:
    """Return the book's existing data dir; fail closed (typed, no write) if it is not usable."""
    problem, exc = _check_book_dir(_DATA)
    if problem:
        _raise_path_invalid(_DATA, [problem], cause=exc, step=step)
    return _DATA


def bootstrap_book_dir() -> Path:
    """EXPLICIT first-ever book creation (E14 ruling c): the book dir and the published-snapshot
    dir, each one level, never parents.  Not reachable from a GET, the scheduler or a sweep."""
    _DATA.mkdir(exist_ok=True)
    _PUBLISHED_PATH.parent.mkdir(exist_ok=True)
    return _DATA


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fresh_account() -> dict[str, Any]:
    return {
        "inception_date": datetime.now(timezone.utc).date().isoformat(),
        "starting_nav": _STARTING_NAV,
        "cash": _STARTING_NAV,
        "positions": {},          # TICKER -> {shares, avg_cost}
    }


class SelfDirectedAccountInvalid(RuntimeError):
    """E13 fail-closed: account.json EXISTS but cannot be trusted (unreadable/unparseable/invalid).

    ``.reason_code`` is the stable discriminator the dashboard routes key on; ``.problems``
    are the sorted problem codes; ``.record`` is the quarantine record (None when nothing was
    quarantined — e.g. refusing to persist an invalid in-memory book).
    """

    def __init__(self, message: str, *, problems: Optional[list[str]] = None,
                 record: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.reason_code = "self_directed_account_invalid"
        self.problems: list[str] = list(problems or [])
        self.record: Optional[dict[str, Any]] = record


def _is_account_number(value: Any) -> bool:
    """Schema-level number for account.json: an int or float, NOT a bool, and finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def validate_account_state(raw: Any) -> list[str]:
    """Pure schema check of one parsed account.json document — no I/O, never raises.

    Returns a SORTED list of problem codes; an empty list means VALID.  Extra keys are allowed
    everywhere (``spy_shares``, ``spy_inception_price`` and the per-position ``current_price*``
    mark metadata among them).  Negative cash or negative shares are economic questions,
    deliberately NOT schema ones: they are VALID here.  ``starting_nav`` and ``inception_date``
    may be ABSENT (the legacy loader defaulted them).
    """
    try:
        if not isinstance(raw, dict):
            return ["not_an_object"]
        problems: list[str] = []
        if not _is_account_number(raw.get("cash")):
            problems.append("cash_invalid")
        if "starting_nav" in raw and (
            not _is_account_number(raw.get("starting_nav")) or raw.get("starting_nav") <= 0
        ):
            problems.append("starting_nav_invalid")
        if "inception_date" in raw and (
            not isinstance(raw.get("inception_date"), str) or not raw.get("inception_date")
        ):
            problems.append("inception_date_invalid")
        positions = raw.get("positions")
        if not isinstance(positions, dict):
            problems.append("positions_invalid")
        else:
            for key, pos in positions.items():
                label = key if isinstance(key, str) else repr(key)
                if not isinstance(key, str) or not key:
                    problems.append(f"position_key_invalid:{key!r}")
                if not isinstance(pos, dict):
                    problems.append(f"position_not_object:{label}")
                    continue
                if not _is_account_number(pos.get("shares")):
                    problems.append(f"position_shares_invalid:{label}")
                if not _is_account_number(pos.get("avg_cost")):
                    problems.append(f"position_avg_cost_invalid:{label}")
        return sorted(problems)
    except Exception:  # noqa: BLE001 — the validator itself must never become the fault it guards
        return ["not_an_object"]


def _classify_account_bytes(raw_bytes: bytes) -> tuple[list[str], Any, Optional[Exception]]:
    """Decode, parse and schema-check raw account.json bytes.  Pure — never raises.

    Returns ``(problems, parsed, parse_error)``; ``problems == []`` means VALID.  Undecodable or
    unparseable bytes (an empty file included) classify as ``["unparseable"]``.
    """
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — one INVALID class for undecodable/unparseable bytes
        return ["unparseable"], None, exc
    return validate_account_state(parsed), parsed, None


def account_file_status(*, path: str | Path | None = None) -> dict[str, Any]:
    """Read-only landing-gate classification of one account.json (probes only).

    NEVER writes, quarantines, alerts or raises.  ``path`` overrides the module's account path
    (resolved at call time).  Returns ``{status, path, sha256, size, problems}`` with status
    MISSING | VALID | INVALID; problems is ``["unreadable:<ExcName>"]``, ``["unparseable"]``,
    a path-level code (``dangling_symlink``, ``data_dir_missing``, ``data_dir_not_directory``,
    ``data_dir_unreadable:<ExcName>``) or the :func:`validate_account_state` codes.
    """
    account_path = Path(path) if path is not None else _ACCOUNT_PATH
    try:
        kind, problem, _exc = _classify_account_path(account_path)
    except Exception as exc:  # noqa: BLE001 — classification must never raise
        kind, problem = "invalid", f"unreadable:{type(exc).__name__}"
    if kind == "absent":
        return {"status": "MISSING", "path": str(account_path), "sha256": None,
                "size": None, "problems": []}
    if kind == "invalid":
        return {"status": "INVALID", "path": str(account_path), "sha256": None,
                "size": None, "problems": [problem]}
    try:
        raw_bytes = account_path.read_bytes()
    except Exception as exc:  # noqa: BLE001 — classification must never raise
        return {"status": "INVALID", "path": str(account_path), "sha256": None,
                "size": None, "problems": [f"unreadable:{type(exc).__name__}"]}
    problems, _parsed, _parse_error = _classify_account_bytes(raw_bytes)
    return {
        "status": "VALID" if not problems else "INVALID",
        "path": str(account_path),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "size": len(raw_bytes),
        "problems": problems,
    }


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Durably replace one runtime-state file without exposing a partial JSON document."""
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # Some filesystems do not permit directory fsync.  The atomic replace still holds.
            pass
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _quarantine_invalid_account(path: Path, raw_bytes: Optional[bytes],
                                problems: list[str]) -> dict[str, Any]:
    """Best-effort quarantine of an invalid EXISTING account.json; never stops the caller's raise.

    Writes a byte-for-byte COPY of the original beside it (idempotent per distinct content).
    The original itself is never moved, renamed, truncated, rewritten or deleted: a moved
    account.json would read as missing on the next load and silently seed a fresh book —
    exactly the defect (E13) this closes.  One ledger row plus one governance event per NEWLY
    written copy (or a failed copy); every detection, repeats included, is logged.  Any failure
    in here is recorded on the returned record and swallowed.
    """
    data_dir = path.parent
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes is not None else None
    record: dict[str, Any] = {
        "event": "account_state_invalid",
        "book": "self_directed",
        "path_name": path.name,
        "source_sha256": source_sha256,
        "size": len(raw_bytes) if raw_bytes is not None else None,
        "problems": list(problems),
        "quarantine_file": None,
        "status": "quarantine_failed",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "recoverable": True,   # the original stays in place; a human repairs or replaces it
    }
    if raw_bytes is not None:
        candidate = data_dir / f"account.quarantine.{source_sha256[:16]}.json"
        record["quarantine_file"] = candidate.name
        if candidate.exists():
            record["status"] = "already_quarantined"
        else:
            try:
                _atomic_write_bytes(candidate, raw_bytes)
                record["status"] = "quarantined"
            except Exception as exc:  # noqa: BLE001 — the caller's raise still happens
                record["quarantine_error"] = repr(exc)[:300]
    if record["status"] in {"quarantined", "quarantine_failed"}:
        try:
            with (data_dir / "account_quarantine.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001 — the shared event below is a second audit sink
            record["audit_ledger_error"] = repr(exc)[:300]
        try:
            from control_plane import run_events  # lazy: keeps this module import-light
            run_events.append({
                "kind": "account_state_invalid",
                "job": "self_directed",
                "book": "self_directed",
                "step": "load_account",
                "status": "error",
                "severity": "HARD_STOP",
                "actor": "deterministic_engine",
                "extra": {
                    "problems": record["problems"],
                    "quarantine_file": record["quarantine_file"],
                    "quarantine_status": record["status"],
                    "source_sha256": record["source_sha256"],
                    "recoverable": record["recoverable"],
                },
            })
        except Exception as exc:  # noqa: BLE001 — event logging never re-enables an invalid book
            record["event_log_error"] = repr(exc)[:300]
    logging.getLogger(__name__).error(
        "self_directed account_state_invalid path=%s problems=%s status=%s",
        path.name, record["problems"], record["status"],
    )
    return record


def _raise_invalid_account(path: Path, raw_bytes: Optional[bytes], problems: list[str],
                           *, cause: Optional[Exception] = None) -> NoReturn:
    """Quarantine an invalid EXISTING account file, then raise SelfDirectedAccountInvalid."""
    record = _quarantine_invalid_account(path, raw_bytes, problems)
    error = SelfDirectedAccountInvalid(
        f"self-directed account state invalid: {problems}",
        problems=problems, record=record,
    )
    if cause is not None:
        raise error from cause
    raise error


def _raise_path_invalid(
    path: Path,
    problems: list[str],
    *,
    cause: Exception | None = None,
    step: str = "load_account",
) -> NoReturn:
    """Fail closed on a path-level problem (dangling symlink, missing/unusable book dir).

    Writes NOTHING: no quarantine copy, no ledger row, no directory.  Emits one best-effort
    HARD_STOP run_event and one log line, then raises SelfDirectedAccountInvalid.
    """
    record: dict[str, Any] = {
        "event": "account_state_invalid",
        "book": "self_directed",
        "path_name": path.name,
        "source_sha256": None,
        "size": None,
        "problems": list(problems),
        "quarantine_file": None,
        "status": "path_invalid",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "recoverable": True,
    }
    try:
        from control_plane import run_events  # lazy: keeps this module import-light
        run_events.append({
            "kind": "account_state_invalid",
            "job": "self_directed",
            "book": "self_directed",
            "step": step,
            "status": "error",
            "severity": "HARD_STOP",
            "actor": "deterministic_engine",
            "extra": {
                "problems": record["problems"],
                "quarantine_file": None,
                "quarantine_status": "path_invalid",
                "source_sha256": None,
                "recoverable": True,
            },
        })
    except Exception as exc:  # noqa: BLE001 — event logging never re-enables an invalid book
        record["event_log_error"] = repr(exc)[:300]
    logging.getLogger(__name__).error(
        "self_directed account_path_invalid path=%s problems=%s",
        path.name, record["problems"],
    )
    error = SelfDirectedAccountInvalid(
        f"self-directed account state invalid: {problems}",
        problems=list(problems), record=record,
    )
    if cause is not None:
        raise error from cause
    raise error


def _raise_for_path_problem(
    account_path: Path,
    problem: str | None,
    exc: OSError | None,
) -> NoReturn:
    """Route one path-classification problem to its fail-closed raise (E14).

    ``unreadable:*`` keeps the E13 quarantine path (best-effort copy + one ledger row + one
    event); every other problem (dangling symlink, unusable book dir) writes NOTHING."""
    problem = problem or "unreadable:Unknown"
    if problem.startswith("unreadable:"):
        _raise_invalid_account(account_path, None, [problem], cause=exc)
    _raise_path_invalid(account_path, [problem], cause=exc)


def _load_account() -> dict[str, Any]:
    """Load account state — fail-closed (E13).

    A MISSING file is still a legitimate new book, but an EXISTING file that cannot be read,
    parsed or schema-validated is quarantined (a byte-for-byte copy beside the original) and
    raises :class:`SelfDirectedAccountInvalid`.  It is NEVER replaced by a fresh book: the old
    any-corruption fallback handed back a fabricated $1M all-cash book and the next save
    silently overwrote the user's real paper positions with it.

    E14: the classification is stat-based — a file that cannot be stat'ed (dangling symlink,
    unreadable path) is INVALID, never absent, and a missing book data directory fails closed
    with ``data_dir_missing`` instead of seeding a fresh book.
    """
    kind, problem, exc = _classify_account_path(_ACCOUNT_PATH)
    if kind == "absent":
        return _fresh_account()
    if kind == "invalid":
        _raise_for_path_problem(_ACCOUNT_PATH, problem, exc)
    try:
        raw_bytes = _ACCOUNT_PATH.read_bytes()
    except FileNotFoundError as read_exc:
        # Re-classify: the file may have vanished between the stat and the read.
        kind, problem, exc = _classify_account_path(_ACCOUNT_PATH)
        if kind == "absent":
            return _fresh_account()
        if kind == "invalid":
            _raise_for_path_problem(_ACCOUNT_PATH, problem, exc)
        _raise_invalid_account(_ACCOUNT_PATH, None, ["unreadable:FileNotFoundError"],
                               cause=read_exc)
    except Exception as exc:
        _raise_invalid_account(_ACCOUNT_PATH, None,
                               [f"unreadable:{type(exc).__name__}"], cause=exc)
    problems, parsed, parse_error = _classify_account_bytes(raw_bytes)
    if problems:
        _raise_invalid_account(_ACCOUNT_PATH, raw_bytes, problems, cause=parse_error)
    parsed.setdefault("starting_nav", _STARTING_NAV)   # legacy loader defaults
    parsed.setdefault("inception_date", _today())
    return parsed


def _save_account(state: dict[str, Any]) -> None:
    # Refuse to PERSIST an invalid in-memory book before anything is written.  The on-disk file
    # is deliberately NOT quarantined for this case: it is still valid and stays untouched.
    state_problems = validate_account_state(state)
    if state_problems:
        raise SelfDirectedAccountInvalid(
            f"self-directed account state invalid: {state_problems}",
            problems=state_problems, record=None,
        )
    kind, problem, exc = _classify_account_path(_ACCOUNT_PATH)
    if kind == "invalid":
        _raise_for_path_problem(_ACCOUNT_PATH, problem, exc)
    if kind == "present":
        # Nothing may overwrite an INVALID book (E13): saving a fresh/valid state over it would
        # silently reset the user's live paper book.  Quarantine the invalid bytes, then fail
        # closed — a human repairs the file directly.
        try:
            raw_bytes = _ACCOUNT_PATH.read_bytes()
        except Exception as exc:  # noqa: BLE001 — unreadable bytes are one INVALID class
            _raise_invalid_account(_ACCOUNT_PATH, None,
                                   [f"unreadable:{type(exc).__name__}"], cause=exc)
        problems, _parsed, parse_error = _classify_account_bytes(raw_bytes)
        if problems:
            _raise_invalid_account(_ACCOUNT_PATH, raw_bytes, problems, cause=parse_error)
    _atomic_write_bytes(_ACCOUNT_PATH,
                        json.dumps(state, indent=2, default=str).encode("utf-8"))


def _append_fill(fill: dict) -> None:
    _require_book_dir()
    with _FILLS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fill, default=str) + "\n")


def _load_fills() -> list[dict]:
    if not _FILLS_PATH.exists():
        return []
    rows: list[dict] = []
    for i, line in enumerate(_FILLS_PATH.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            r["_seq"] = i
            rows.append(r)
        except Exception:
            pass
    rows.sort(key=lambda r: (r.get("date") or "", r.get("_seq", 0)))
    return rows


def _load_pending() -> list[dict]:
    try:
        if _PENDING_PATH.exists():
            data = json.loads(_PENDING_PATH.read_text())
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_pending(orders: list[dict]) -> None:
    _require_book_dir()
    _PENDING_PATH.write_text(json.dumps(orders, indent=2, default=str))


def _load_theses() -> dict[str, dict]:
    try:
        if _THESES_PATH.exists():
            data = json.loads(_THESES_PATH.read_text())
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_theses(theses: dict[str, dict]) -> None:
    _require_book_dir()
    _THESES_PATH.write_text(json.dumps(theses, indent=2, default=str, ensure_ascii=False))


# ---------------------------------------------------------------------------
# price + clock resolution (all lazy / optional)
# ---------------------------------------------------------------------------

def _stockdata_price(ticker: str) -> Optional[float]:
    """Last mark from vendor/macro/site/stockdata/<T>.json — a plain file read, no import."""
    try:
        p = _ROOT / "vendor" / "macro" / "site" / "stockdata" / f"{ticker.upper()}.json"
        if p.exists():
            v = (json.loads(p.read_text()).get("tech") or {}).get("price")
            if v is not None and float(v) > 0:
                return float(v)
    except Exception:
        pass
    return None


def _live_quote(ticker: str) -> Optional[float]:
    try:
        from data_layer import polygon
        px = polygon.quote(ticker)
        if px and float(px) > 0:
            return float(px)
        # delayed/EOD-tier keys: quote() may be empty outside market hours — fall back to the
        # snapshot's best price (down to prior-day close) so any US name is still priceable.
        px = polygon.snapshot_price(ticker)
        if px and float(px) > 0:
            return float(px)
    except Exception:
        return None
    return None


# INJECTION SEAM (W-L / L1) — the ONE marking layer, opt-in.
#
# Historically this book had its OWN price path (live Polygon → stockdata snapshot) that NEVER read
# the vendored parquet store, so any held name with no live quote fell through to avg_cost at the
# call sites → the book showed a phantom ZERO return. The fix is NOT to rewrite this module (its
# open/close-fill mechanics must stay intact); it is to let the daily-mark job route this book's
# marks through `portfolio.marks` (polygon-EOD → yahoo-parquet → last-good-carry, never avg_cost)
# by setting `_price_resolver`. When unset, behaviour is byte-identical to before.
_price_resolver = None  # Optional[Callable[[str], Optional[float]]]


def set_price_resolver(fn) -> None:
    """Install (or clear, with None) the injected mark resolver. `fn(ticker) -> price|None` becomes
    the FIRST source `_current_price` consults; the legacy live/snapshot path is the fallback."""
    global _price_resolver
    _price_resolver = fn


def _current_price(ticker: str) -> Optional[float]:
    """Best available current price. If a mark resolver is injected (the ONE marking layer, L1) it
    is consulted first; otherwise the legacy live Polygon quote → stockdata snapshot path is used.
    NEVER falls back to avg_cost (a missing mark returns None, so callers hold at the prior mark)."""
    if _price_resolver is not None:
        try:
            px = _price_resolver(ticker)
            if px and px > 0:
                return float(px)
        except Exception:
            pass
    return _live_quote(ticker) or _stockdata_price(ticker)


def _open_price(ticker: str) -> Optional[float]:
    """The session's OPEN (for filling queued orders), falling back to last price."""
    try:
        from data_layer import polygon
        o = polygon.day_open(ticker)
        if o and float(o) > 0:
            return float(o)
    except Exception:
        pass
    return _current_price(ticker)


def _market_open(now: datetime | None = None) -> bool:
    try:
        from portfolio import market_clock
        return market_clock.is_open(now)
    except Exception:
        return False


def _market_status() -> dict:
    try:
        from portfolio import market_clock
        return market_clock.status()
    except Exception:
        return {"is_open": False, "session": "closed", "now_et": None, "next_open": None}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# core fill mechanics (mutates the passed account dict; returns a fill or None)
# ---------------------------------------------------------------------------

def _apply_fill(state: dict, ticker: str, side: str, shares: float, px: float,
                asof: str) -> Optional[dict]:
    """Apply ONE long-only fill to `state`. Buys are clamped to cash, sells to shares held.
    Returns the fill record, or None if nothing could transact (no cash / no shares)."""
    ticker = ticker.upper()
    positions = state.setdefault("positions", {})
    pos = positions.get(ticker)

    if side == "buy":
        shares = min(float(shares), state["cash"] / px) if px > 0 else 0.0
        if shares <= 1e-9:
            return None
        value = shares * px
        state["cash"] = max(0.0, state["cash"] - value)
        if pos:
            total = pos["shares"] + shares
            pos["avg_cost"] = (pos["shares"] * pos["avg_cost"] + value) / total
            pos["shares"] = total
        else:
            positions[ticker] = {"shares": shares, "avg_cost": px}
    else:  # sell — bounded by shares held (long-only: no shorting)
        if not pos or pos["shares"] <= 1e-9:
            return None
        shares = min(float(shares), pos["shares"])
        if shares <= 1e-9:
            return None
        value = shares * px
        state["cash"] += value
        pos["shares"] -= shares
        if pos["shares"] <= 1e-9:
            del positions[ticker]

    return {"date": asof, "ticker": ticker, "side": side,
            "shares": round(shares, 6), "price": round(px, 4), "value": round(value, 2)}


# ---------------------------------------------------------------------------
# pending-order settlement
# ---------------------------------------------------------------------------

def settle_pending(*, now: datetime | None = None, market_open: bool | None = None,
                   prices: dict[str, float] | None = None) -> list[dict]:
    """Fill any queued orders at the session OPEN, IF the market is open. No-op otherwise.

    A queued buy with no cash / a queued sell with no shares at open is dropped as
    `cancelled` (it would be a no-op fill). Returns the settled order records."""
    pending = _load_pending()
    if not pending:
        return []
    if market_open is None:
        market_open = _market_open(now)
    if not market_open:
        return []

    state = _load_account()
    asof = _today()
    settled: list[dict] = []
    still_pending: list[dict] = []
    prices = prices or {}

    for o in pending:
        ticker = (o.get("ticker") or "").upper()
        px = prices.get(ticker) or _open_price(ticker)
        if not px or px <= 0:
            still_pending.append(o)          # unpriceable this sweep — keep queued
            continue
        if o.get("shares") is not None:
            req = float(o.get("shares") or 0)
        else:
            req = float(o.get("notional") or 0) / px   # dollars → shares at the open price
        fill = _apply_fill(state, ticker, o.get("side"), req, px, asof)
        if fill:
            fill["order_id"] = o.get("order_id")
            fill["queued"] = True
            _append_fill(fill)
            settled.append({**o, "status": "filled", "filled_price": fill["price"],
                            "filled_at": _now_iso()})
        else:
            settled.append({**o, "status": "cancelled",
                            "reason": "no cash" if o.get("side") == "buy" else "no shares"})

    _save_account(state)
    _save_pending(still_pending)
    return settled


# ---------------------------------------------------------------------------
# the public order API
# ---------------------------------------------------------------------------

def place_order(ticker: str, side: str, shares: float | None = None, *,
                notional: float | None = None, price: float | None = None,
                now: datetime | None = None, market_open: bool | None = None) -> dict:
    """Place a single buy/sell, sized by SHARES or by a DOLLAR amount (`notional` → shares
    at the fill price). Pass exactly one. Returns one of:
      {ok:True, status:'filled', fill:{...}, cash_after}     — executed at market now
      {ok:True, status:'pending', order:{...}}               — queued for the next open
      {ok:False, error:'...'}                                — rejected (bad input / no price / nothing to do)
    """
    ticker = (ticker or "").upper().strip()
    side = (side or "").lower().strip()

    def _pos(v):
        try:
            v = float(v)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    sh = _pos(shares)
    nt = _pos(notional)

    if not ticker:
        return {"ok": False, "error": "ticker required"}
    if side not in ("buy", "sell"):
        return {"ok": False, "error": "side must be 'buy' or 'sell'"}
    if sh is None and nt is None:
        return {"ok": False, "error": "shares or dollar amount must be positive"}

    if market_open is None:
        market_open = _market_open(now)

    # market open → settle any stragglers, then fill this one immediately
    if market_open:
        settle_pending(now=now, market_open=True)
        state = _load_account()
        px = float(price) if (price and float(price) > 0) else _current_price(ticker)
        if not px or px <= 0:
            return {"ok": False, "error": f"no live price available for {ticker}"}
        # pre-flight long-only guards (so the user gets a clear message, not a silent no-op)
        if side == "buy" and state["cash"] <= 0:
            return {"ok": False, "error": "insufficient cash"}
        if side == "sell":
            held = (state.get("positions", {}).get(ticker) or {}).get("shares", 0.0)
            if held <= 1e-9:
                return {"ok": False, "error": f"no {ticker} position to sell"}
        req_shares = sh if sh is not None else (nt / px)   # dollars → shares at the fill price
        fill = _apply_fill(state, ticker, side, req_shares, px, _today())
        if not fill:
            return {"ok": False, "error": "order could not be filled"}
        _save_account(state)
        _append_fill(fill)
        return {"ok": True, "status": "filled", "fill": fill, "cash_after": round(state["cash"], 2)}

    # market closed → queue PENDING (fills at the next open). Reject obvious no-ops up front.
    # E13: read the book BEFORE queueing ANY order, buy or sell — an order must never be
    # accepted against an invalid book (a closed-market buy previously queued without the
    # account ever being read). For a missing/valid file this adds no side effect.
    state = _load_account()
    if side == "sell":
        held = (state.get("positions", {}).get(ticker) or {}).get("shares", 0.0)
        if held <= 1e-9:
            return {"ok": False, "error": f"no {ticker} position to sell"}
    order = {
        "order_id": _gen_order_id(ticker),
        "ticker": ticker,
        "side": side,
        "placed_at": _now_iso(),
        "status": "pending",
    }
    if sh is not None:                       # share-sized order
        order["shares"] = round(sh, 6)
    else:                                    # dollar-sized order — converts at the open price
        order["notional"] = round(nt, 2)
    pending = _load_pending()
    pending.append(order)
    _save_pending(pending)
    return {"ok": True, "status": "pending", "order": order}


def cancel_order(order_id: str) -> bool:
    """Remove a still-pending order. Returns True if one was removed."""
    pending = _load_pending()
    kept = [o for o in pending if o.get("order_id") != order_id]
    if len(kept) == len(pending):
        return False
    _save_pending(kept)
    return True


_order_seq = 0


def _gen_order_id(ticker: str) -> str:
    global _order_seq
    _order_seq += 1
    # monotonic-ish, human-readable; uniqueness within a process is all we need
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{ticker}-{stamp}-{_order_seq}"


# ---------------------------------------------------------------------------
# conviction theses
# ---------------------------------------------------------------------------

def set_thesis(ticker: str, note: str) -> Optional[dict]:
    """Save (or clear, if note is empty) the user's conviction note for a ticker."""
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return None
    theses = _load_theses()
    note = (note or "").strip()
    if note:
        theses[ticker] = {"note": note, "updated_at": _now_iso()}
    else:
        theses.pop(ticker, None)
    _save_theses(theses)
    return theses.get(ticker)


# ---------------------------------------------------------------------------
# NAV history mark (W-L / L1) — the mark seam so this book is graded like the others
# ---------------------------------------------------------------------------

_PUBLISHED_PATH = _ROOT / "data" / "portfolios" / "self_directed" / "latest.json"


def publish(*, prices: dict[str, float] | None = None, asof: str | None = None) -> Optional[dict]:
    """Write data/portfolios/self_directed/latest.json in the firm_exposure latest.json schema.

    This is the PUBLISH SEAM that makes the self-directed book visible to firm_exposure.summary()
    as a named-yardstick row (cluster/name concentration across the whole firm, including the user's
    book, is visible to the firm accountant). firm_exposure's headroom()/clamp_book() deliberately
    EXCLUDE this book from their binding sums — the benchmark book must never mechanically shape the
    books it measures.

    Schema matches paper_account's published format so _load_book() reads it without modification:
    {schema, portfolio_id, as_of, nav, positions:[{ticker, weight, shares, market_value}]}.
    Un-priced names are included at weight derived from avg_cost (an honest approximation tagged in
    the note). Best-effort; never raises; returns the written doc or None on failure."""
    asof_str = str(asof or _today())[:10]
    try:
        state = _load_account()
    except SelfDirectedAccountInvalid:
        # E13: publish is best-effort — an invalid book is never published or saved over.
        return None
    prices_map = {(k or "").upper(): float(v) for k, v in (prices or {}).items() if v and v > 0}
    positions_raw = state.get("positions", {})

    # Mark every position (live price > avg_cost fallback — honest approximation)
    marks: dict[str, float] = {}
    for ticker in positions_raw:
        px = prices_map.get(ticker) or _current_price(ticker)
        if px and px > 0:
            marks[ticker] = float(px)

    invested = sum(
        (pos.get("shares") or 0.0) * marks.get(tk, pos.get("avg_cost") or 0.0)
        for tk, pos in positions_raw.items()
    )
    cash = state.get("cash", 0.0)
    nav = cash + invested

    rows: list[dict] = []
    for ticker, pos in positions_raw.items():
        shares = float(pos.get("shares") or 0.0)
        if shares <= 0:
            continue
        px = marks.get(ticker, pos.get("avg_cost") or 0.0)
        mv = shares * px if px else None
        w = round(mv / nav, 6) if (mv is not None and nav > 0) else None
        rows.append({
            "ticker": ticker,
            "shares": round(shares, 6),
            "current_price": round(marks[ticker], 4) if ticker in marks else None,
            "market_value": round(mv, 2) if mv is not None else None,
            "weight": w,
        })

    doc = {
        "schema": "portfolio.v1",
        "portfolio_id": "self_directed",
        "as_of": asof_str,
        "nav": round(nav, 2),
        "currency": "USD",
        "positions": rows,
        "note": ("Self-directed book published for firm-wide concentration visibility. "
                 "Positions at live mark (avg_cost fallback for unpriced names). "
                 "EXCLUDED from firm headroom/clamp math — the benchmark book must not "
                 "mechanically constrain the books it measures."),
    }
    try:
        if _check_book_dir(_PUBLISHED_PATH.parent)[0] is not None:
            return None   # E14: never create the published dir from a scheduler path
        _PUBLISHED_PATH.write_text(json.dumps(doc, indent=2, default=str))
        return doc
    except Exception:  # noqa: BLE001
        return None


def mark(*, prices: dict[str, float] | None = None, asof: str | None = None,
         benchmark: str = "SPY", mark_source: str = "self_directed_mark") -> Optional[dict]:
    """Snapshot this book's NAV to nav_history.jsonl (idempotent per date), so the CIO review and
    the improvement agenda see it alongside the paper_account books. Uses the SAME price resolution
    as book() (the injected marking layer first, then the legacy accessor) — a held name with no
    mark falls back to its avg_cost for the NAV total ONLY (never written back as a price). The
    benchmark line (spy_nav) initialises its shares on the first mark, mirroring paper_account.mark.
    Best-effort; never raises."""
    asof = str(asof or _today())[:10]
    try:
        state = _load_account()
    except SelfDirectedAccountInvalid:
        # E13: a mark is best-effort — an invalid book gets no NAV row and is never saved over.
        return None
    prices = {(k or "").upper(): v for k, v in (prices or {}).items() if v and v > 0}
    positions = state.get("positions", {})

    invested = 0.0
    stored_mark_changed = False
    for ticker, pos in positions.items():
        observed = prices.get(ticker) or _current_price(ticker)
        try:
            observed = float(observed) if observed is not None else None
        except (TypeError, ValueError):
            observed = None
        if observed is not None and math.isfinite(observed) and observed > 0:
            previous_asof = str(pos.get("current_price_asof") or "")[:10]
            try:
                may_update = not previous_asof or date.fromisoformat(previous_asof) <= date.fromisoformat(asof)
            except (TypeError, ValueError):
                may_update = True
            if may_update:
                pos["current_price"] = round(observed, 4)
                pos["current_price_asof"] = asof
                pos["current_price_source"] = str(mark_source or "self_directed_mark")
                pos["current_price_time_kind"] = "portfolio_mark_date"
                stored_mark_changed = True
        px = observed if observed is not None and observed > 0 else (pos.get("avg_cost") or 0.0)
        invested += (pos.get("shares") or 0.0) * px
    cash = state.get("cash", 0.0)
    nav = cash + invested

    # benchmark shares are pinned on the first mark (back-compat with the paper_account convention)
    spy_px = prices.get(benchmark) or _current_price(benchmark)
    if state.get("spy_shares") is None and spy_px and spy_px > 0:
        state["spy_shares"] = _STARTING_NAV / spy_px
        state["spy_inception_price"] = spy_px
        stored_mark_changed = True
    if stored_mark_changed:
        _save_account(state)
    spy_nav = state.get("spy_shares") * spy_px if (state.get("spy_shares") and spy_px) else None

    row = {"date": asof, "nav": round(nav, 2), "cash": round(cash, 2),
           "invested": round(invested, 2),
           "spy_nav": round(spy_nav, 2) if spy_nav is not None else None}
    try:
        _require_book_dir()
        rows: list[dict] = []
        if _NAV_PATH.exists():
            for line in _NAV_PATH.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("date") != asof:            # idempotent per date
                    rows.append(r)
        rows.append(row)
        _NAV_PATH.write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n")
    except Exception:
        pass
    return row


# ---------------------------------------------------------------------------
# read models — the book + the blotter
# ---------------------------------------------------------------------------

def quote_info(ticker: str) -> dict:
    """Live price + reference name for the order-ticket display. Best-effort."""
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"ticker": "", "price": None}
    name = ""
    try:
        from data_layer import polygon
        det = polygon.ticker_details(ticker)
        if det:
            name = det.get("name") or ""
    except Exception:
        pass
    return {"ticker": ticker, "price": _current_price(ticker), "name": name,
            "market": _market_status()}


def book(*, prices: dict[str, float] | None = None, now: datetime | None = None,
         market_open: bool | None = None, read_only: bool = False,
         resolve_missing_prices: bool = True) -> dict:
    """The Self-Directed book contract for the dashboard.

    Settles pending orders first (if the market is open), then returns positions with live
    marks + weights, the allocation scorecard, the market state, and the pending queue.
    `prices` (TICKER→px) overrides live marks (used by tests / a shared price fetch).

    `read_only=True` skips the settle_pending() side-effect so a GET request does not
    mutate state files.  ``resolve_missing_prices=False`` also prevents per-name live
    network fallbacks; the session-aware dashboard endpoint uses it while markets are
    closed so an unpriced name cannot trigger an overnight quote request.  The scheduled
    mark-sweep and existing interactive routes retain the default live fallback."""
    if not read_only:
        settle_pending(now=now, market_open=market_open, prices=prices)
    state = _load_account()
    theses = _load_theses()
    prices = dict(prices or {})

    positions_raw = state.get("positions", {})
    marks: dict[str, float] = {}
    for ticker, pos in positions_raw.items():
        px = prices.get(ticker)
        if px is None and resolve_missing_prices:
            px = _current_price(ticker)
        if px and px > 0:
            marks[ticker] = float(px)

    invested = 0.0
    for ticker, pos in positions_raw.items():
        px = marks.get(ticker, pos.get("avg_cost") or 0.0)
        invested += pos.get("shares", 0.0) * px
    cash = state.get("cash", 0.0)
    nav = cash + invested

    positions: list[dict] = []
    for ticker, pos in positions_raw.items():
        shares = float(pos.get("shares") or 0.0)
        avg = float(pos.get("avg_cost") or 0.0)
        px = marks.get(ticker)
        mv = shares * px if px else None
        th = theses.get(ticker) or {}
        positions.append({
            "ticker": ticker,
            "shares": round(shares, 6),
            "avg_cost": round(avg, 4) if avg else None,
            "current_price": round(px, 4) if px else None,
            "market_value": round(mv, 2) if mv is not None else None,
            "unrealized_pnl": round((px - avg) * shares, 2) if (px and avg) else None,
            "unrealized_pct": round((px / avg - 1) * 100, 2) if (px and avg) else None,
            "weight": round(mv / nav, 6) if (mv is not None and nav > 0) else None,
            "thesis": th.get("note"),
            "thesis_updated_at": th.get("updated_at"),
        })
    # heaviest weight first; un-priced names sink to the bottom
    positions.sort(key=lambda p: (p["weight"] if p["weight"] is not None else -1), reverse=True)

    weights = [p["weight"] for p in positions if p["weight"] is not None]
    total_unreal = sum(p["unrealized_pnl"] for p in positions if p["unrealized_pnl"] is not None)

    pending = _mark_pending(_load_pending(), prices, resolve_missing=resolve_missing_prices)

    return {
        "starting_nav": state.get("starting_nav", _STARTING_NAV),
        "inception_date": state.get("inception_date"),
        "nav": round(nav, 2),
        "cash": round(cash, 2),
        "invested": round(invested, 2),
        "positions": positions,
        "allocation": {
            "cash_pct": round(cash / nav, 6) if nav > 0 else 1.0,
            "invested_pct": round(invested / nav, 6) if nav > 0 else 0.0,
            "gross": round(invested / nav, 6) if nav > 0 else 0.0,
            "n_positions": len(positions),
            "largest_weight": round(max(weights), 6) if weights else 0.0,
            "total_unrealized_pnl": round(total_unreal, 2),
            "total_return_pct": round((nav - state.get("starting_nav", _STARTING_NAV))
                                      / state.get("starting_nav", _STARTING_NAV) * 100, 4),
        },
        "pending": pending,
        "market": _market_status(),
    }


def _mark_pending(pending: list[dict], prices: dict[str, float],
                  resolve_missing: bool = True) -> list[dict]:
    """Attach an indicative current price + est. shares/value to each queued order for display.
    A share-sized order carries `shares`; a dollar-sized order carries `notional` (with the
    estimated shares it would buy at the indicative price)."""
    out = []
    for o in pending:
        ticker = (o.get("ticker") or "").upper()
        px = prices.get(ticker)
        if px is None and resolve_missing:
            px = _current_price(ticker)
        has_sh = o.get("shares") is not None
        shares = float(o.get("shares") or 0.0) if has_sh else None
        notional = None if has_sh else float(o.get("notional") or 0.0)
        if has_sh:
            est_shares = shares
            est_value = round(shares * px, 2) if px else None
        else:
            est_shares = round(notional / px, 4) if px else None
            est_value = round(notional, 2)
        out.append({
            "order_id": o.get("order_id"),
            "ticker": ticker,
            "side": o.get("side"),
            "shares": round(shares, 6) if shares is not None else None,
            "notional": round(notional, 2) if notional is not None else None,
            "est_shares": est_shares,
            "placed_at": o.get("placed_at"),
            "est_price": round(px, 4) if px else None,
            "est_value": est_value,
        })
    # newest first
    out.sort(key=lambda o: o.get("placed_at") or "", reverse=True)
    return out


def history(*, prices: dict[str, float] | None = None, now: datetime | None = None,
            market_open: bool | None = None) -> dict:
    """Trade-history blotter: every executed fill (FIFO realized P&L on sells, live
    unrealized on open buy remainders) + the pending queue + a realized summary."""
    settle_pending(now=now, market_open=market_open, prices=prices)
    fills = _load_fills()
    live = {(k or "").upper(): v for k, v in (prices or {}).items()}

    lots: dict[str, deque] = defaultdict(deque)
    rows: list[dict] = []
    for f in fills:
        tk = (f.get("ticker") or "").upper()
        side = f.get("side")
        shares = float(f.get("shares") or 0.0)
        px = float(f.get("price") or 0.0)
        row = {
            "date": f.get("date"), "ticker": tk, "action": side,
            "shares": round(shares, 6), "price": round(px, 4), "value": f.get("value"),
            "exit_price": None, "realized_pnl": None, "realized_pct": None,
            "unrealized_pnl": None, "unrealized_pct": None,
            "queued": bool(f.get("queued")), "still_open": False, "open_shares": None,
        }
        if side == "buy":
            lots[tk].append([shares, px, row])
        elif side == "sell":
            remaining, cost_basis, matched = shares, 0.0, 0.0
            q = lots[tk]
            while remaining > 1e-9 and q:
                lot = q[0]
                take = min(lot[0], remaining)
                cost_basis += take * lot[1]
                matched += take
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    q.popleft()
            row["exit_price"] = round(px, 4)
            if matched > 1e-9:
                avg = cost_basis / matched
                row["price"] = round(avg, 4)
                row["realized_pnl"] = round((px - avg) * matched, 2)
                row["realized_pct"] = round((px / avg - 1) * 100, 2) if avg else None
        rows.append(row)

    for tk, q in lots.items():
        live_px = live.get(tk) or _current_price(tk)
        for shares_rem, cost, row in q:
            if shares_rem <= 1e-9:
                continue
            row["still_open"] = True
            row["open_shares"] = round(shares_rem, 6)
            if live_px and cost:
                row["unrealized_pnl"] = round((live_px - cost) * shares_rem, 2)
                row["unrealized_pct"] = round((live_px / cost - 1) * 100, 2)

    rows.reverse()  # newest first
    sells = [r for r in rows if r["action"] == "sell" and r["realized_pnl"] is not None]
    realized_total = round(sum(r["realized_pnl"] for r in sells), 2)
    wins = sum(1 for r in sells if r["realized_pnl"] > 0)
    return {
        "history": rows,
        "pending": _mark_pending(_load_pending(), dict(prices or {})),
        "realized_total": realized_total,
        "n_closed": len(sells),
        "n_buys": sum(1 for r in rows if r["action"] == "buy"),
        "win_rate": round(wins / len(sells), 4) if sells else None,
    }
