"""Persistent positions ledger — tracks open/close timestamps across book builds.

Keyed by "<sleeve>:<ticker>" in data/portfolio/positions_ledger.json. This is the ONE canonical
positions-lifecycle plane; nothing here may be mirrored into a second store.

AVAILABILITY CONTRACT
---------------------
This ledger is held-risk evidence, not decoration: ``bot/derisk.py`` reads it to decide whether the
book is flat. Four states are therefore kept DISTINCT rather than collapsed to ``{}``:

    missing      — no file yet (uninitialized). Reads give []; writers may create it.
    empty        — a file holding {}. A genuinely flat lifecycle. Reads give [].
    populated    — a readable file with at least one entry.
    unavailable  — the file exists but cannot be read as a lifecycle ledger (unparseable bytes,
                   a non-mapping root, or any record that is not a lifecycle entry).

``unavailable`` raises :class:`LedgerUnavailable` from every read and every write. It is NEVER
reported as an empty ledger, because a consumer that sees [] concludes "no held risk" and a writer
that sees {} silently fabricates a brand-new lifecycle over the real one — destroying entry prices,
``opened_at``, and the time-stop clock for every held name, plus the bytes needed to repair them.
Writers therefore PRESERVE-AND-FREEZE: they refuse and leave the damaged file untouched, so recovery
is the operator repairing the file, after which reads and writes resume deterministically. Lifecycle
history is never reconstructed from the paper account — the account proves what is held now, not
when it was opened or at what price. :func:`status` reports the state and never raises.

CONCURRENCY CONTRACT
--------------------
``_save`` is atomic (tmp + fsync + ``os.replace``), but atomic replacement is NOT lost-update
protection: ``update`` / ``record_manual`` / ``close_position`` are READ → MODIFY → REPLACE
transactions, and two processes that each read version N and each atomically replace it lose one of
two legitimate lifecycle mutations — including a risk EXIT, silently. Every mutation therefore holds
:func:`_ledger_lock` across the WHOLE transaction, reusing the sidecar-``.lock`` + blocking
``fcntl.flock`` pattern already accepted in ``portfolio/paper_account.py`` and
``portfolio/advisor_trade.py`` (a blocking lock, not ``control_plane.locks``' non-blocking
skip-on-conflict — a lifecycle mutation must queue, never be dropped).

READS DELIBERATELY TAKE NO LOCK. ``os.replace`` is atomic, so a reader always observes one complete
committed version. This also keeps the lock ordering one-way: ``app/web.py`` and
``bot/derisk.derisk_brain`` already read this ledger while holding
``paper_account._paper_transaction_lock``, and no path here ever calls back into ``paper_account``,
so paper→ledger is the only nesting that exists and no cycle is possible.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_ROOT = Path(__file__).resolve().parent.parent
_LEDGER_PATH = _ROOT / "data" / "portfolio" / "positions_ledger.json"
_WEIGHT_CHANGE_THRESHOLD = 0.01   # 1 percentage point = material weight change

# ── CLOSE-REASON TAXONOMY (observability only — never gates sizing/trading) ──────────────────
# A CLOSED enum of machine-readable close reasons so a nightly rebuild ROTATION is distinguishable
# from a deliberate risk EXIT. The human-readable `reason` string is kept alongside (unchanged);
# `reason_code` is the structured companion. Any close event MAY carry a reason_code; a close event
# written before this field existed (or with no code supplied) has NO reason_code key — legacy reads
# stay byte-valid. Unknown/unsupplied → "unspecified".
REASON_CODES: frozenset[str] = frozenset({
    "rebuild_dropped",    # (1) reconciliation: a held name absent from the freshly-built book
    "hard_veto",          # (2) hard-exit sweep: parabolic / distress / confirmed downtrend
    "time_stop_d5",       # (3) D5 dead-capital time-stop exit
    "cap_trim",           # (4) leadership / name / macro cap trimmed the name to zero
    "risk_officer_exit",  # (5a) Risk Officer thesis-broken exit
    "judgment_exit",      # (5b) Flagship judgment / PM-layer discretionary exit
    "manual",             # (6) operator / advisor-chat ad-hoc close
    "unspecified",        # unknown — the byte-compatible default
})

# Map the legacy free-text `reason` strings that close_position() already receives to a code, so an
# existing caller that passes only the string still lands the RIGHT structured code with no call-site
# change required. Anything unrecognised falls through to "unspecified".
_REASON_STRING_TO_CODE: dict[str, str] = {
    "hard_exit": "hard_veto",
    "hard_exit_sweep": "hard_veto",
    "risk_officer_exit": "risk_officer_exit",
    "macro_risk_cap": "cap_trim",
    "manual": "manual",
}


def _normalize_code(reason_code: str | None, reason: str | None = None) -> str:
    """Resolve a close event's structured reason_code.

    Precedence: an explicit VALID reason_code wins; else infer from the legacy `reason` string via
    the known-string map; else "unspecified". Never raises — an unknown reason_code is coerced to
    "unspecified" rather than admitting an out-of-taxonomy value into the ledger."""
    if reason_code and reason_code in REASON_CODES:
        return reason_code
    if reason and reason in _REASON_STRING_TO_CODE:
        return _REASON_STRING_TO_CODE[reason]
    return "unspecified"


def _ledger_path(portfolio_id: str | None = None) -> Path:
    """Resolve the ledger file. None/default → the legacy module-global (kept patchable
    for the test fixtures); any other id → data/portfolios/<id>/positions_ledger.json."""
    from portfolio import registry
    if not portfolio_id or portfolio_id == registry.DEFAULT_ID:
        return _LEDGER_PATH
    return registry.data_dir(portfolio_id) / "positions_ledger.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _held_days(opened_at: str, closed_at: str | None = None) -> int | None:
    """Days between open and close (or now). Returns None if opened_at is missing."""
    if not opened_at:
        return None
    try:
        t0 = datetime.fromisoformat(opened_at)
        t1 = datetime.fromisoformat(closed_at) if closed_at else datetime.now(timezone.utc)
        return max(0, (t1 - t0).days)
    except Exception:
        return None


class LedgerUnavailable(RuntimeError):
    """The positions ledger exists but cannot be read as a lifecycle ledger.

    Raised instead of returning an empty ledger, so a consumer can never mistake LOST AUTHORITY over
    the lifecycle for ZERO EXPOSURE. Carries everything recovery needs: the resolved ``path``, the
    ``kind`` of damage, and the ``quarantined`` record keys when specific entries are the problem.
    """

    def __init__(self, detail: str, *, path: Path | None = None, kind: str = "unreadable",
                 quarantined: tuple[str, ...] | list[str] = ()) -> None:
        # Self-describing on purpose: consumers such as /api/trades surface a bare ``str(exc)`` in a
        # generic error envelope, and that string has to name the STATE ("unavailable"), not only
        # the parse detail — otherwise the outage reaches the UI without saying what it is.
        super().__init__(f"positions ledger unavailable ({kind}): {detail}")
        self.detail = detail
        self.path = path
        self.kind = kind
        self.quarantined: tuple[str, ...] = tuple(quarantined)


def _is_lifecycle_entry(entry: Any) -> bool:
    """A record is readable as a lifecycle entry only if it is a mapping carrying a ticker.

    ``ticker`` is the one field every reader dereferences unconditionally (``open_positions`` and
    ``closed_positions`` both do ``e["ticker"]``), so a record without one cannot be reported at
    all — and a record that cannot be reported is a record whose ``still_open`` risk is invisible.
    """
    return isinstance(entry, dict) and bool(str(entry.get("ticker") or "").strip())


def _read_ledger(path: Path) -> dict[str, Any]:
    """Read + validate the ledger at ``path``.

    Returns {} ONLY for a genuinely absent file (uninitialized) or a file holding {}. Any other
    failure raises :class:`LedgerUnavailable` rather than degrading to an empty ledger.

    PER-RECORD POLICY (explicit, in place of the broad swallow this replaces): a record that is not
    a lifecycle entry is QUARANTINED BY NAME and makes the whole ledger unavailable. It is not
    dropped. Dropping it would understate held risk (an unreadable record may be an OPEN position),
    and letting a writer proceed would erase it from the next atomic replace — so the one damaged
    record freezes the plane until an operator repairs it, and every other record stays intact.
    """
    try:
        if not path.exists():
            return {}
        raw = path.read_text()
    except OSError as exc:
        raise LedgerUnavailable(f"{exc!r}"[:240],
                                path=path, kind="unreadable") from exc
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise LedgerUnavailable(f"not valid JSON: {exc!r}"[:240],
                                path=path, kind="unparseable") from exc
    if not isinstance(parsed, dict):
        raise LedgerUnavailable(
            f"root is {type(parsed).__name__}, expected a mapping of "
            f"'<sleeve>:<ticker>' -> lifecycle entry", path=path, kind="malformed_root")
    bad = sorted(str(key) for key, entry in parsed.items() if not _is_lifecycle_entry(entry))
    if bad:
        raise LedgerUnavailable(
            f"{len(bad)} record(s) are not lifecycle entries: "
            f"{', '.join(bad[:8])}{' …' if len(bad) > 8 else ''}",
            path=path, kind="malformed_records", quarantined=bad)
    return parsed


def _load(portfolio_id: str | None = None) -> dict[str, Any]:
    """Load the ledger. {} for missing/empty; raises LedgerUnavailable when it cannot be read."""
    return _read_ledger(_ledger_path(portfolio_id))


def status(portfolio_id: str | None = None) -> dict[str, Any]:
    """Report which of the four ledger states holds, WITHOUT raising.

    This is the typed distinction a risk consumer needs in order to tell an empty healthy book from
    lost lifecycle authority. ``state`` is one of ``missing`` / ``empty`` / ``populated`` /
    ``unavailable``; ``open_count`` is None exactly when the ledger is unavailable.
    """
    path = _ledger_path(portfolio_id)
    base: dict[str, Any] = {"path": str(path), "open_count": None, "quarantined": [],
                            "kind": None, "detail": ""}
    try:
        exists = path.exists()
    except OSError as exc:
        return {**base, "state": "unavailable", "kind": "unreadable", "detail": repr(exc)[:240]}
    if not exists:
        return {**base, "state": "missing", "open_count": 0,
                "detail": "positions ledger not initialized"}
    try:
        ledger = _read_ledger(path)
    except LedgerUnavailable as exc:
        return {**base, "state": "unavailable", "kind": exc.kind,
                "quarantined": list(exc.quarantined), "detail": exc.detail}
    return {**base,
            "state": "populated" if ledger else "empty",
            "open_count": sum(1 for e in ledger.values() if e.get("still_open")),
            "detail": ""}


# Same-thread reentrancy, mirroring paper_account._paper_transaction_lock: a nested boundary inside
# one thread must not deadlock against the flock it already holds.
_LEDGER_LOCK_STATE = threading.local()


@contextmanager
def _ledger_lock(portfolio_id: str | None = None):
    """Serialize one book's ENTIRE read-modify-write transaction across processes.

    Held from before ``_load`` until after ``_save`` returns — covering the whole transaction, not
    merely the final ``os.replace``. Blocking (``LOCK_EX`` without ``LOCK_NB``) on purpose: a
    lifecycle mutation must queue behind a concurrent one, never be skipped. The sidecar lock file
    sits beside the ledger, so each portfolio_id serializes independently.
    """
    path = _ledger_path(portfolio_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    key = str(lock_path)
    depths = getattr(_LEDGER_LOCK_STATE, "depths", None)
    if depths is None:
        depths = {}
        _LEDGER_LOCK_STATE.depths = depths
    if depths.get(key, 0):
        depths[key] += 1
        try:
            yield
        finally:
            depths[key] -= 1
        return
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        depths[key] = 1
        try:
            yield
        finally:
            depths.pop(key, None)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _save(ledger: dict[str, Any], portfolio_id: str | None = None) -> None:
    path = _ledger_path(portfolio_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(ledger, indent=2, default=str, ensure_ascii=False).encode("utf-8")
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
            # Atomic replacement still prevents a partial ledger where directory fsync is absent.
            pass
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def update(positions: list[dict], asof_iso: str, portfolio_id: str | None = None,
           close_reasons: dict[str, str] | None = None,
           reason_codes: dict[str, str] | None = None) -> None:
    """Call once per book build to reconcile the ledger with the current positions.

    positions:     the assembled book list (each dict must have 'ticker' and 'sleeve' at minimum,
                   plus optional 'weight', 'entry_price').
    asof_iso:      the date string from the regime (used as the 'as_of' watermark).
    close_reasons: optional {ticker: reason_string} mapping. When a position leaves the book this
                   build the matching reason (if any) is stamped on the close history event, matching
                   the behaviour of close_position() which always carries a reason. Absent from the
                   mapping or None → reason field omitted (backwards-compatible with legacy reads).
    reason_codes:  optional {ticker: reason_code} mapping — the STRUCTURED companion to close_reasons
                   (see REASON_CODES). Stamped as `reason_code` on the close event so a rebuild
                   rotation is machine-distinguishable from a risk exit. Absent → no reason_code key
                   (byte-compatible legacy read). An out-of-taxonomy value is coerced to "unspecified".
    """
    # ONE serialized transaction: load → reconcile → save. Two builds that each read the same
    # base version and atomically replaced it would lose one reconcile entirely.
    with _ledger_lock(portfolio_id):
        now = _now_iso()
        ledger = _load(portfolio_id)

        # build a set of keys currently in the book
        current_keys: dict[str, dict] = {}
        for p in positions:
            key = f"{p.get('sleeve', 'unknown')}:{p['ticker']}"
            current_keys[key] = p

        # --- handle currently-in-book positions ---
        for key, p in current_keys.items():
            weight = p.get("weight")
            _levels = p.get("entry_levels") or {}
            price = _levels.get("price") or p.get("entry_price")
            ticker = p["ticker"]
            sleeve = p.get("sleeve", "unknown")
            # PUBLISHED entry-risk levels (P-NEW-3) — the dashboard's per-name stop / buy_zone /
            # entry_grade, read from the book row's entry_levels. Persist-only: NONE when the name
            # carried no published entry_signal (degrades to today's ledger row byte-for-byte).
            published_stop = _levels.get("stop")
            buy_zone = _levels.get("buy_zone")
            entry_grade = _levels.get("entry_grade")

            if key not in ledger:
                # new entry
                ledger[key] = {
                    "ticker": ticker,
                    "sleeve": sleeve,
                    "opened_at": now,
                    "open_as_of": asof_iso,
                    "closed_at": None,
                    "close_as_of": None,
                    "still_open": True,
                    "last_seen": now,
                    "entry_weight": weight,
                    "entry_price": price,
                    "current_weight": weight,
                    "thesis_id": p.get("thesis_id"),
                    "time_stop_by": p.get("time_stop_by"),
                    "published_stop": published_stop,
                    "buy_zone": buy_zone,
                    "entry_grade": entry_grade,
                    "history": [{"event": "open", "ts": now, "as_of": asof_iso,
                                 "weight": weight, "price": price}],
                }
            else:
                entry = ledger[key]
                # backfill the published entry-risk levels onto an already-open entry that predates them
                # (add-only; never overwrite a persisted non-null stop with a later miss — invariant:
                # a data gap must never erase the stop we already recorded at entry).
                if published_stop is not None and entry.get("published_stop") is None:
                    entry["published_stop"] = published_stop
                if buy_zone and entry.get("buy_zone") is None:
                    entry["buy_zone"] = buy_zone
                if entry_grade and entry.get("entry_grade") is None:
                    entry["entry_grade"] = entry_grade
                # IDEMPOTENT PER BUILD DATE: a trade event is logged at most once per `as_of`. The book
                # may be rebuilt many times intra-day (dev runs, event interrupts); those rebuilds
                # update the weight silently — they are NOT each a new ADD/TRIM. Without this guard the
                # activity feed shows phantom ADD/TRIM churn (e.g. AVGO ADD 4.8% / TRIM 3.5% / ADD 4.8%
                # within a minute) from successive same-day rebuilds.
                logged_today = (entry.get("history") or [{}])[-1].get("as_of") == asof_iso

                if not entry.get("still_open"):
                    # re-opened position — restart
                    entry["opened_at"] = now
                    entry["open_as_of"] = asof_iso
                    entry["closed_at"] = None
                    entry["close_as_of"] = None
                    entry["still_open"] = True
                    entry["entry_weight"] = weight
                    entry["entry_price"] = price
                    entry["time_stop_by"] = p.get("time_stop_by")
                    # a re-open is a fresh entry — adopt the freshly-published stop when present, but a
                    # miss must not blank an existing stop (degrade-never-raise: keep the prior level).
                    if published_stop is not None:
                        entry["published_stop"] = published_stop
                    if buy_zone:
                        entry["buy_zone"] = buy_zone
                    if entry_grade:
                        entry["entry_grade"] = entry_grade
                    if not logged_today:
                        entry["history"].append({"event": "open", "ts": now, "as_of": asof_iso,
                                                 "weight": weight, "price": price})
                        logged_today = True
                # backfill the time-stop clock for an already-open entry that predates this field
                elif entry.get("time_stop_by") is None and p.get("time_stop_by"):
                    entry["time_stop_by"] = p.get("time_stop_by")

                # track material weight changes — one rebalance event per build date, not per rebuild
                prior_weight = entry.get("current_weight") or 0.0
                if weight is not None and prior_weight is not None and not logged_today:
                    delta = abs((weight or 0.0) - (prior_weight or 0.0))
                    if delta > _WEIGHT_CHANGE_THRESHOLD:
                        event = "add" if (weight or 0) > (prior_weight or 0) else "trim"
                        entry["history"].append({"event": event, "ts": now, "as_of": asof_iso,
                                                 "weight": weight, "price": price})

                entry["last_seen"] = now
                entry["current_weight"] = weight

        # --- handle positions that have left the book (close once per build date) ---
        for key, entry in ledger.items():
            if entry.get("still_open") and key not in current_keys:
                entry["still_open"] = False
                entry["closed_at"] = now
                entry["close_as_of"] = asof_iso
                if (entry.get("history") or [{}])[-1].get("as_of") != asof_iso:
                    ticker = entry.get("ticker", "")
                    # Stamp the close reason when the caller supplies one (mirrors close_position()).
                    # Absent from the mapping → reason key omitted so legacy reads stay valid.
                    _close_event: dict = {"event": "close", "ts": now, "as_of": asof_iso,
                                          "weight": 0, "price": None}
                    if close_reasons and ticker and ticker in close_reasons:
                        _close_event["reason"] = close_reasons[ticker]
                    # Structured companion: stamp reason_code only when supplied for this ticker, so a
                    # build that passes no codes writes a byte-identical (code-free) close event.
                    if reason_codes and ticker and ticker in reason_codes:
                        _close_event["reason_code"] = _normalize_code(reason_codes[ticker],
                                                                      close_reasons.get(ticker) if close_reasons else None)
                    entry["history"].append(_close_event)

        _save(ledger, portfolio_id)


def record_manual(ticker: str, sleeve: str, *, event: str, weight: float | None = None,
                  price: float | None = None, asof_iso: str | None = None,
                  portfolio_id: str | None = None) -> None:
    """Upsert ONE ledger entry without reconciling the rest of the book.

    update() reconciles against the WHOLE book (anything missing is closed), so it must
    never be called with a partial list. This touches only this one key — used by the
    advisor chat's ad-hoc trades. event: "open"/"add"/"trim"/"close".
    """
    # ONE serialized transaction — an advisor upsert must not be lost to a concurrent build.
    with _ledger_lock(portfolio_id):
        now = _now_iso()
        asof_iso = asof_iso or now[:10]
        ledger = _load(portfolio_id)
        key = f"{sleeve}:{ticker.upper()}"
        entry = ledger.get(key)
        closing = event == "close"
        if entry is None:
            entry = {
                "ticker": ticker.upper(), "sleeve": sleeve,
                "opened_at": now, "open_as_of": asof_iso, "closed_at": None,
                "close_as_of": None, "still_open": not closing, "last_seen": now,
                "entry_weight": weight, "entry_price": price, "current_weight": weight,
                "thesis_id": None, "source": "advisor", "history": [],
            }
            ledger[key] = entry
        if closing:
            entry["still_open"] = False
            entry["closed_at"] = now
            entry["close_as_of"] = asof_iso
            entry["current_weight"] = 0
        else:
            if not entry.get("still_open"):                # re-open
                entry["opened_at"] = now
                entry["open_as_of"] = asof_iso
                entry["closed_at"] = None
                entry["close_as_of"] = None
                entry["entry_weight"] = weight
                entry["entry_price"] = price
            entry["still_open"] = True
            entry["last_seen"] = now
            if weight is not None:
                entry["current_weight"] = weight
        _manual_event: dict = {"event": event, "ts": now, "as_of": asof_iso, "weight": weight, "price": price}
        # An ad-hoc advisor close is a MANUAL exit — tag it structurally (only the close event; adds/trims
        # carry no reason_code, byte-identical to before).
        if closing:
            _manual_event["reason_code"] = "manual"
        entry.setdefault("history", []).append(_manual_event)
        _save(ledger, portfolio_id)


def open_positions(portfolio_id: str | None = None) -> list[dict]:
    """Return open positions shaped for /api/trades 'open' array."""
    ledger = _load(portfolio_id)
    out = []
    for key, e in ledger.items():
        if not e.get("still_open"):
            continue
        out.append({
            "ticker": e["ticker"],
            "sleeve": e["sleeve"],
            "opened_at": e.get("opened_at"),
            "held_days": _held_days(e.get("opened_at")),
            "entry_weight": e.get("entry_weight"),
            "current_weight": e.get("current_weight"),
            "entry_price": e.get("entry_price"),
            "time_stop_by": e.get("time_stop_by"),
            "thesis_id": e.get("thesis_id"),
            # published entry-risk levels (P-NEW-3) — echoed so the audit/API + the stop-breach
            "published_stop": e.get("published_stop"),   # surfacing pass can read them. None on legacy.
            "buy_zone": e.get("buy_zone"),
        })
    # newest first (most recently opened)
    out.sort(key=lambda x: x.get("opened_at") or "", reverse=True)
    return out


def closed_positions(portfolio_id: str | None = None) -> list[dict]:
    """Return closed positions shaped for /api/trades 'closed' array.

    exit_reason is derived from the close history event's 'reason' field when present (stamped
    by either close_position() or update(..., close_reasons=...) — both now write it). Falls back
    to the generic 'removed from book' string so legacy ledger rows (written before this field
    was added) continue to deserialise cleanly.
    """
    ledger = _load(portfolio_id)
    out = []
    for key, e in ledger.items():
        if e.get("still_open"):
            continue
        # Find the most-recent close event to read its reason (if any).
        history = e.get("history") or []
        _last_close = next(
            (ev for ev in reversed(history) if ev.get("event") == "close"),
            None,
        )
        _close_reason = (_last_close or {}).get("reason")
        # Structured code — echoed alongside the human string so the API/audit can machine-filter
        # rotations vs stops. Legacy rows (no reason_code in history) degrade to "unspecified".
        _close_code = (_last_close or {}).get("reason_code") or "unspecified"
        out.append({
            "ticker": e["ticker"],
            "sleeve": e["sleeve"],
            "opened_at": e.get("opened_at"),
            "closed_at": e.get("closed_at"),
            "held_days": _held_days(e.get("opened_at"), e.get("closed_at")),
            "exit_reason": _close_reason or "removed from book",
            "reason_code": _close_code,
        })
    out.sort(key=lambda x: x.get("closed_at") or "", reverse=True)
    return out


def close_position(sleeve: str, ticker: str, asof_iso: str, reason: str = "hard_exit",
                   portfolio_id: str | None = None, reason_code: str | None = None) -> bool:
    """Close a SINGLE open position without touching any other (unlike update(), which closes every
    open key absent from the passed book). Used by the gate-closed hard-exit sweep so a parabolic /
    distress / downtrend name can be exited on a carried-forward day. Returns True if it closed an
    open position.

    reason_code: optional STRUCTURED close code (see REASON_CODES). When omitted it is INFERRED from
    the legacy `reason` string (e.g. 'hard_exit_sweep' → 'hard_veto', 'macro_risk_cap' → 'cap_trim'),
    so existing callers that pass only `reason` still land the correct code without a call-site change.
    An unrecognised string with no explicit code → 'unspecified'. Always additive to the close event."""
    # ONE serialized transaction — a risk EXIT is the costliest mutation to lose.
    with _ledger_lock(portfolio_id):
        ledger = _load(portfolio_id)
        key = f"{sleeve}:{ticker}"
        entry = ledger.get(key)
        if not entry or not entry.get("still_open"):
            return False
        now = _now_iso()
        entry["still_open"] = False
        entry["closed_at"] = now
        entry["close_as_of"] = asof_iso
        entry["current_weight"] = 0
        entry.setdefault("history", []).append(
            {"event": "close", "ts": now, "as_of": asof_iso, "weight": 0, "price": None,
             "reason": reason, "reason_code": _normalize_code(reason_code, reason)})
        _save(ledger, portfolio_id)
        return True


def get_entry_info(sleeve: str, ticker: str, portfolio_id: str | None = None) -> dict:
    """Return {opened_at, held_days, entry_price} for a given position key, or {} if not found."""
    ledger = _load(portfolio_id)
    key = f"{sleeve}:{ticker}"
    e = ledger.get(key)
    if not e:
        return {}
    return {
        "opened_at": e.get("opened_at"),
        "held_days": _held_days(e.get("opened_at")),
        "entry_price": e.get("entry_price"),
        "time_stop_by": e.get("time_stop_by"),
    }
