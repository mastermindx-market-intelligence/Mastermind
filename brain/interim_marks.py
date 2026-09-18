"""INTERIM MARKS (#11) — day-5 / day-10 trajectory checkpoints for OPEN conviction theses.

The conviction sleeve grades on a 21-business-day falsifier — a long wait before any feedback on a held
name. This logs EARLY checkpoints: each open directional thesis's realized rel-return vs SPY at 5 and 10
business days (leakage-free, reusing brain.outcomes.label_thesis with a horizon override), so the risk
layer gets a mid-flight read (a name deeply underwater at day-5/10 is an early-exit candidate) and a
checkpoint hit-rate accrues weeks before the 21-bday cohort matures.

STRICT DISCIPLINE: an interim mark is early EVIDENCE, NEVER the graded LABEL. The 21-bday resolution
(brain.scorer / brain.outcomes / brain.outcome_ledger) is left untouched — no proxy-as-label leak. The
checkpoint marks live in their own logical append-only JSONL (data/brain/interim_marks.jsonl), KEEP-FIRST
per (thesis_id, checkpoint). Missing price labels remain a normal no-op; corrupt canonical mark/thesis
evidence and failed publication fail closed to the existing scheduler/API boundaries.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from brain.ledger import all_theses

_ROOT = Path(__file__).resolve().parent.parent
_PATH = _ROOT / "data" / "brain" / "interim_marks.jsonl"
_LOCAL_LOCK = threading.RLock()

_CHECKPOINTS = [5, 10]      # business-day trajectory checkpoints (well before the 21-bday final grade)
_UNDERWATER = -0.03         # rel-return below this at a checkpoint → an early-warning (risk layer input)

# WHY data/brain/interim_marks.jsonl MAY BE ABSENT: record() only appends when all_theses()
# returns at least one OPEN thesis whose falsifier.check.kind == 'rel_return' AND whose
# checkpoint window (5 or 10 business days from state_asof) has elapsed by the run date.
# An absent file is not a bug — it means the conviction sleeve has no graduated open theses
# yet (book is new, ledger is empty, or no thesis has aged past the first checkpoint).
# There is no silent swallow on the write path: the outer try/except in record() only catches
# exceptions from all_theses() or outcomes.label_thesis(), not an intentionally empty fresh list.


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lock_path() -> Path:
    return _PATH.with_name(f".{_PATH.name}.lock")


@contextmanager
def _marks_lock():
    """Serialize KEEP-FIRST mark publication across threads and processes."""
    with _LOCAL_LOCK:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock_path().open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except OSError:
                    # A completed atomic replace already decided the data effect.
                    pass


def _load_unlocked() -> list[dict]:
    if not _PATH.exists():
        return []
    rows: list[dict] = []
    for line in _PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("interim-mark row is not a mapping")
        rows.append(row)
    return rows


def _load() -> list[dict]:
    # Atomic writers expose a complete prior or successor file; malformed canonical evidence is
    # unavailable, never equivalent to an empty mark history.
    return _load_unlocked()


def _atomic_write(rows: list[dict]) -> None:
    """Replace interim-mark history atomically; preserve prior bytes on failure."""
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, default=str, ensure_ascii=False) + "\n" for row in rows)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=_PATH.parent,
            prefix=f".{_PATH.name}.", suffix=".tmp", delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, _PATH)
        tmp_name = None
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _mark(thesis: dict, horizon: int, asof: date):
    """Label one thesis's rel-return vs SPY at `horizon` business days (a synthetic falsifier so
    brain.outcomes.label_thesis grades the EARLY window; leakage-free — it caps the price path at asof)."""
    try:
        from brain import outcomes
        subj = ((thesis.get("entry_levels") or {}).get("ticker") or thesis.get("subject") or "").upper()
        entry = str(thesis.get("state_asof") or "")[:10]
        px = (thesis.get("entry_levels") or {}).get("price")
        syn = {"id": f"{thesis.get('id')}-cp{horizon}", "subject": subj, "state_asof": entry,
               "entry_levels": ({"ticker": subj, "price": px} if px else {"ticker": subj}),
               "falsifier": {"check": {"kind": "rel_return", "subject_ticker": subj, "vs": "SPY",
                                       "op": "<", "threshold": -0.05, "horizon_d": int(horizon)}}}
        return outcomes.label_thesis(syn, asof)
    except Exception:  # noqa: BLE001
        return None


def record(asof: str | date | None = None) -> dict:
    """Log elapsed 5d/10d checkpoints exactly once per thesis.

    Price-label unavailability remains a normal no-op through ``_mark``. Canonical thesis/mark
    evidence failures and publication failures propagate to the scheduler's existing failure event
    boundary instead of masquerading as zero marks.
    """
    asof_d = asof if isinstance(asof, date) else date.fromisoformat(str(asof or date.today())[:10])
    initial_rows = _load()
    initial_seen = {(r.get("thesis_id"), r.get("checkpoint")) for r in initial_rows}
    candidates: list[dict] = []
    candidate_seen: set[tuple] = set()
    for thesis in all_theses():
        if thesis.get("status", "open") != "open":
            continue
        chk = (thesis.get("falsifier") or {}).get("check") or {}
        if chk.get("kind") != "rel_return":
            continue
        op, threshold = chk.get("op", "<"), chk.get("threshold", -0.05)
        thesis_id = thesis.get("id")
        for horizon in _CHECKPOINTS:
            key = (thesis_id, horizon)
            if key in initial_seen or key in candidate_seen:
                continue
            lab = _mark(thesis, horizon, asof_d)
            if not (lab and lab.get("resolved") and lab.get("rel_return") is not None):
                continue
            rel = lab["rel_return"]
            falsified = (rel < threshold) if op == "<" else (rel > threshold)
            candidates.append({
                "thesis_id": thesis_id,
                "subject": ((thesis.get("entry_levels") or {}).get("ticker")
                            or thesis.get("subject") or "").upper(),
                "checkpoint": horizon,
                "entry_date": str(thesis.get("state_asof") or "")[:10],
                "rel_return": rel,
                "barrier": lab.get("barrier"),
                "falsified_so_far": bool(falsified),
                "underwater": bool(rel <= _UNDERWATER),
                "prob_correct": thesis.get("prob_correct"),
                "horizon_d": thesis.get("horizon_d"),
                "recorded_at": _now_iso(),
            })
            candidate_seen.add(key)

    with _marks_lock():
        rows = _load_unlocked()
        seen = {(r.get("thesis_id"), r.get("checkpoint")) for r in rows}
        fresh = []
        for row in candidates:
            key = (row.get("thesis_id"), row.get("checkpoint"))
            if key in seen:
                continue
            seen.add(key)
            fresh.append(row)
        if fresh:
            _atomic_write(rows + fresh)
        return {"n_marks": len(rows) + len(fresh), "new": len(fresh)}


def scorecard() -> dict:
    """Per-checkpoint trajectory read over the logged interim marks: n, the falsifier-consistent hit-rate
    (NOT falsified by its own threshold at this early window), avg rel-return, and the count underwater.
    Plus the live EARLY-WARNING list (each open thesis's latest checkpoint that is underwater)."""
    rows = _load()
    by_cp: dict = {}
    for h in _CHECKPOINTS:
        b = [r for r in rows if r.get("checkpoint") == h and r.get("rel_return") is not None]
        if not b:
            by_cp[str(h)] = {"n": 0, "hit_rate": None, "avg_rel": None, "n_underwater": 0}
            continue
        n = len(b)
        by_cp[str(h)] = {
            "n": n,
            "hit_rate": round(sum(1 for r in b if not r.get("falsified_so_far")) / n, 3),
            "avg_rel": round(sum(r["rel_return"] for r in b) / n, 4),
            "n_underwater": sum(1 for r in b if r.get("underwater"))}
    return {"checkpoints": _CHECKPOINTS, "by_checkpoint": by_cp,
            "early_warnings": early_warnings(), "n_marks": len(rows)}


def early_warnings() -> list[dict]:
    """Open theses currently UNDERWATER at their LATEST logged checkpoint — the risk layer's early-exit
    candidates (advisory; never auto-exits). One row per subject, the deepest/most-recent checkpoint."""
    rows = [r for r in _load() if r.get("underwater")]
    by_subj: dict = {}
    for r in rows:
        s = r.get("subject")
        cur = by_subj.get(s)
        if cur is None or (r.get("checkpoint") or 0) > (cur.get("checkpoint") or 0):
            by_subj[s] = r
    out = [{"subject": r.get("subject"), "checkpoint": r.get("checkpoint"),
            "rel_return": r.get("rel_return"), "entry_date": r.get("entry_date")}
           for r in by_subj.values()]
    out.sort(key=lambda r: (r.get("rel_return") if r.get("rel_return") is not None else 0))
    return out


def summary() -> dict:
    return {"scorecard": scorecard(), "checkpoints": _CHECKPOINTS}
