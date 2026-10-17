"""Positions-ledger INTEGRITY — corruption semantics + cross-process serialization.

The canonical lifecycle ledger (``portfolio/position_log.py``) is not dashboard decoration: it is
the held-risk evidence that ``bot/derisk.py`` reads before deciding whether the book is flat. Two
defect classes are reproduced here, then locked:

  (A) CORRUPT-AS-EMPTY.  ``_load()`` swallowed every read exception and returned ``{}``, making
      four distinct states indistinguishable — genuinely-empty, absent/uninitialized,
      unreadable/corrupt, and structurally-invalid.  A risk consumer that reads ``[]`` concludes
      "no held risk" and skips the de-risk cut; a WRITER that reads ``{}`` silently destroys every
      open position's lifecycle history (entry price, opened_at, time-stop clock) on its next save.

  (B) LOST UPDATE.  ``_save()`` is atomic (tmp + fsync + ``os.replace``), but ``update()`` /
      ``record_manual()`` / ``close_position()`` are independent READ → MODIFY → REPLACE
      operations.  Atomic replacement is NOT lost-update protection: two processes that read
      version N and each atomically replace it lose one of two legitimate lifecycle mutations —
      including a risk EXIT.

The serialization claims are proven with REAL subprocesses on a REAL file, driven through a
barrier schedule that pins the interleaving.  Calling the functions sequentially in one process
would prove nothing about cross-process behaviour.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

# The barrier schedule is cooperative; these bound a hung worker rather than pace a healthy one.
_BARRIER_TIMEOUT = 20.0
# How long the driver waits to see whether the SECOND writer can enter the critical section while
# the first still holds it.  Under a correct lock it never can, so this is spent in full, once.
_OVERLAP_PROBE = 2.0


# ────────────────────────────────────────────────────────────────────────────────────────────────
# barrier-driven two-process writer harness
# ────────────────────────────────────────────────────────────────────────────────────────────────

_WORKER = r'''
"""One ledger writer, instrumented to pause INSIDE its read-modify-write transaction.

The barriers wrap ``_load``/``_save``, which sit inside whatever critical section the module
establishes.  So a writer that cannot start its ``_load`` is a writer that blocked on the lock —
which is exactly the property under test.
"""
import json, os, sys, time
from pathlib import Path

repo, ledger, barrier_dir, name, op_json = sys.argv[1:6]
sys.path.insert(0, repo)

barrier = Path(barrier_dir)
op = json.loads(op_json)

from portfolio import position_log as pl

pl._LEDGER_PATH = Path(ledger)

_orig_load, _orig_save = pl._load, pl._save


def _load(*a, **k):
    out = _orig_load(*a, **k)
    (barrier / f"{name}.loaded").write_text("1")      # "I am inside the critical section"
    return out


def _save(*a, **k):
    deadline = time.time() + 60
    while not (barrier / f"{name}.go").exists():      # hold the section open for the driver
        if time.time() > deadline:
            raise SystemExit(f"{name}: go-barrier timeout")
        time.sleep(0.01)
    return _orig_save(*a, **k)


pl._load, pl._save = _load, _save

kind = op.pop("op")
if kind == "record_manual":
    pl.record_manual(**op)
elif kind == "close_position":
    pl.close_position(**op)
elif kind == "update":
    pl.update(op["positions"], op["asof_iso"])
else:
    raise SystemExit(f"unknown op {kind!r}")

(barrier / f"{name}.done").write_text("1")
'''


def _wait_for(path: Path, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.01)
    return path.exists()


def _spawn(worker: Path, ledger: Path, barrier: Path, name: str, op: dict) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    return subprocess.Popen(
        [sys.executable, str(worker), str(_REPO), str(ledger), str(barrier), name,
         json.dumps(op)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _run_interleaved(tmp_path: Path, ledger: Path, op_a: dict, op_b: dict) -> dict:
    """Force the classic lost-update schedule and report what actually happened.

    Schedule::

        A: load ──────────────────────────── save
        B:      load(?) ──────────────────────────── save

    ``b_entered_while_a_held`` is the discriminator: True means both writers read the SAME base
    version concurrently (the lost-update precondition); False means the second writer was
    serialized behind the first, i.e. the lock covers the whole transaction and not merely the
    final ``os.replace``.
    """
    worker = tmp_path / "ledger_worker.py"
    worker.write_text(_WORKER)
    barrier = tmp_path / "barriers"
    barrier.mkdir(exist_ok=True)

    proc_a = _spawn(worker, ledger, barrier, "a", dict(op_a))
    assert _wait_for(barrier / "a.loaded", _BARRIER_TIMEOUT), (
        f"writer A never entered its transaction: {proc_a.communicate()}")

    proc_b = _spawn(worker, ledger, barrier, "b", dict(op_b))
    # Probe: can B enter its read-modify-write while A is still inside its own?
    b_entered_while_a_held = _wait_for(barrier / "b.loaded", _OVERLAP_PROBE)

    (barrier / "a.go").write_text("1")                      # let A commit and release
    out_a = proc_a.communicate(timeout=_BARRIER_TIMEOUT)
    assert proc_a.returncode == 0, f"writer A failed: {out_a}"

    # B either already read the stale base (unserialized) or is only now able to read A's commit.
    assert _wait_for(barrier / "b.loaded", _BARRIER_TIMEOUT), (
        f"writer B never entered its transaction: {proc_b.communicate()}")
    (barrier / "b.go").write_text("1")
    out_b = proc_b.communicate(timeout=_BARRIER_TIMEOUT)
    assert proc_b.returncode == 0, f"writer B failed: {out_b}"

    return {
        "b_entered_while_a_held": b_entered_while_a_held,
        "ledger": json.loads(ledger.read_text()),
    }


def _seed(ledger: Path, entries: dict) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(entries, indent=2))


def _open_entry(ticker: str, sleeve: str = "conviction", weight: float = 0.05) -> dict:
    return {
        "ticker": ticker, "sleeve": sleeve,
        "opened_at": "2026-01-01T00:00:00+00:00", "open_as_of": "2026-01-01",
        "closed_at": None, "close_as_of": None, "still_open": True,
        "last_seen": "2026-01-01T00:00:00+00:00",
        "entry_weight": weight, "entry_price": 100.0, "current_weight": weight,
        "thesis_id": None, "time_stop_by": None,
        "history": [{"event": "open", "ts": "2026-01-01T00:00:00+00:00",
                     "as_of": "2026-01-01", "weight": weight, "price": 100.0}],
    }


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    """A real on-disk ledger, wired into the module the way every consumer reads it."""
    from portfolio import position_log as pl
    path = tmp_path / "portfolio" / "positions_ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pl, "_LEDGER_PATH", path)
    return path


# ════════════════════════════════════════════════════════════════════════════════════════════════
# (B) LOST UPDATE — two legitimate concurrent lifecycle mutations
# ════════════════════════════════════════════════════════════════════════════════════════════════

def test_concurrent_manual_opens_do_not_lose_each_other(tmp_path, ledger):
    """Two processes open two DIFFERENT names from the same base version. Both must survive.

    RED (pre-fix): B reads the base while A holds it, then B's atomic replace overwrites A's —
    ``conviction:AAA`` is gone and no error is raised anywhere.
    """
    _seed(ledger, {})

    res = _run_interleaved(
        tmp_path, ledger,
        {"op": "record_manual", "ticker": "AAA", "sleeve": "conviction",
         "event": "open", "weight": 0.05, "price": 10.0, "asof_iso": "2026-02-02"},
        {"op": "record_manual", "ticker": "BBB", "sleeve": "conviction",
         "event": "open", "weight": 0.04, "price": 20.0, "asof_iso": "2026-02-02"},
    )

    assert res["b_entered_while_a_held"] is False, (
        "the second writer read the ledger while the first was still inside its own "
        "read-modify-write: serialization does not cover the transaction")
    assert set(res["ledger"]) == {"conviction:AAA", "conviction:BBB"}, (
        f"lost update — surviving keys: {sorted(res['ledger'])}")


def test_concurrent_closes_do_not_lose_a_risk_exit(tmp_path, ledger):
    """The highest-stakes lost update: two risk EXITS race and one is silently un-recorded.

    A closes AAA (hard veto), B closes BBB (risk-officer exit). Losing either leaves a name the
    engine believes it exited still marked open in the canonical ledger.
    """
    _seed(ledger, {
        "conviction:AAA": _open_entry("AAA"),
        "conviction:BBB": _open_entry("BBB"),
    })

    res = _run_interleaved(
        tmp_path, ledger,
        {"op": "close_position", "sleeve": "conviction", "ticker": "AAA",
         "asof_iso": "2026-02-02", "reason": "hard_exit_sweep"},
        {"op": "close_position", "sleeve": "conviction", "ticker": "BBB",
         "asof_iso": "2026-02-02", "reason": "risk_officer_exit"},
    )

    assert res["b_entered_while_a_held"] is False
    assert res["ledger"]["conviction:AAA"]["still_open"] is False, "AAA's risk exit was lost"
    assert res["ledger"]["conviction:BBB"]["still_open"] is False, "BBB's risk exit was lost"
    assert (res["ledger"]["conviction:AAA"]["history"][-1]["reason_code"] == "hard_veto")
    assert (res["ledger"]["conviction:BBB"]["history"][-1]["reason_code"] == "risk_officer_exit")


def test_concurrent_update_and_close_preserve_both_effects(tmp_path, ledger):
    """A whole-book reconcile races a single-name hard exit. Neither may erase the other.

    A: ``update()`` reconciles the book to {AAA, CCC} — opening CCC, closing nothing else.
    B: ``close_position()`` exits BBB on the gate-closed hard-exit sweep.
    """
    _seed(ledger, {
        "conviction:AAA": _open_entry("AAA"),
        "conviction:BBB": _open_entry("BBB"),
    })

    res = _run_interleaved(
        tmp_path, ledger,
        {"op": "update", "asof_iso": "2026-02-02", "positions": [
            {"ticker": "AAA", "sleeve": "conviction", "weight": 0.05, "entry_price": 100.0},
            {"ticker": "BBB", "sleeve": "conviction", "weight": 0.05, "entry_price": 100.0},
            {"ticker": "CCC", "sleeve": "conviction", "weight": 0.03, "entry_price": 50.0},
        ]},
        {"op": "close_position", "sleeve": "conviction", "ticker": "BBB",
         "asof_iso": "2026-02-02", "reason": "hard_exit_sweep"},
    )

    assert res["b_entered_while_a_held"] is False
    led = res["ledger"]
    assert "conviction:CCC" in led, "the reconcile's new position was lost"
    assert led["conviction:AAA"]["still_open"] is True
    assert led["conviction:BBB"]["still_open"] is False, "the hard exit was lost"


# ════════════════════════════════════════════════════════════════════════════════════════════════
# (A) CORRUPT MUST NEVER READ AS EMPTY
# ════════════════════════════════════════════════════════════════════════════════════════════════

def test_corrupt_ledger_read_refuses_instead_of_reporting_no_positions(ledger):
    """RED (pre-fix): ``open_positions()`` returned ``[]`` — indistinguishable from a flat book."""
    from portfolio import position_log as pl

    ledger.write_text("{INVALID JSON!!!")

    with pytest.raises(pl.LedgerUnavailable):
        pl.open_positions()
    with pytest.raises(pl.LedgerUnavailable):
        pl.closed_positions()
    with pytest.raises(pl.LedgerUnavailable):
        pl.get_entry_info("conviction", "AAA")


def test_corrupt_ledger_writes_refuse_and_preserve_the_bytes(ledger):
    """A writer must never "start fresh" over an unreadable ledger.

    Starting fresh fabricates a brand-new lifecycle for every held name (held_days 0, entry price
    lost, time-stop clock reset) AND destroys the forensic evidence needed to repair it.
    """
    from portfolio import position_log as pl

    corrupt = '{"conviction:AAA": {"ticker": "AAA", trunc'
    ledger.write_text(corrupt)

    with pytest.raises(pl.LedgerUnavailable):
        pl.update([{"ticker": "SMH", "sleeve": "leadership", "weight": 0.125}], "2026-01-01")
    with pytest.raises(pl.LedgerUnavailable):
        pl.record_manual("AAA", "conviction", event="open", weight=0.05)
    with pytest.raises(pl.LedgerUnavailable):
        pl.close_position("conviction", "AAA", "2026-01-01")

    assert ledger.read_text() == corrupt, "the corrupt ledger was overwritten — evidence destroyed"


def test_status_distinguishes_all_four_ledger_states(tmp_path, ledger):
    """The smallest typed distinction the risk plane needs, and it never raises."""
    from portfolio import position_log as pl

    # 1. missing / uninitialized
    assert pl.status()["state"] == "missing"

    # 2. available-empty
    _seed(ledger, {})
    assert pl.status()["state"] == "empty"
    assert pl.open_positions() == []

    # 3. available-populated
    _seed(ledger, {"conviction:AAA": _open_entry("AAA")})
    st = pl.status()
    assert st["state"] == "populated"
    assert st["open_count"] == 1

    # 4. unavailable / corrupt
    ledger.write_text("not json")
    st = pl.status()
    assert st["state"] == "unavailable"
    assert st["open_count"] is None
    assert st["detail"], "an unavailable ledger must say why"


def test_missing_and_empty_ledger_remain_fully_supported(ledger):
    """Control: a genuinely healthy empty lifecycle is NOT an error and writes normally."""
    from portfolio import position_log as pl

    assert pl.open_positions() == []          # absent file
    assert pl.closed_positions() == []
    assert pl.get_entry_info("conviction", "AAA") == {}

    pl.update([{"ticker": "SMH", "sleeve": "leadership", "weight": 0.125,
                "entry_price": 200.0}], "2026-01-01")
    assert [p["ticker"] for p in pl.open_positions()] == ["SMH"]

    _seed(ledger, {})                          # explicitly-empty file
    assert pl.open_positions() == []
    pl.record_manual("AAA", "conviction", event="open", weight=0.05)
    assert [p["ticker"] for p in pl.open_positions()] == ["AAA"]


@pytest.mark.parametrize("bad, why", [
    ('{"conviction:AAA": "not-an-entry"}', "entry is not a mapping"),
    ('{"conviction:AAA": {"sleeve": "conviction", "still_open": true}}', "entry has no ticker"),
    ('["conviction:AAA"]', "ledger root is not a mapping"),
    ('null', "ledger root is null"),
])
def test_structurally_invalid_records_are_unavailable_not_silently_dropped(ledger, bad, why):
    """EXPLICIT per-record policy: a record that cannot be read as a lifecycle entry may be an
    OPEN position. Dropping it understates held risk, so the ledger reads as unavailable and
    writers refuse — rather than the arbitrary broad swallowing this replaces."""
    from portfolio import position_log as pl

    ledger.write_text(bad)

    st = pl.status()
    assert st["state"] == "unavailable", why
    with pytest.raises(pl.LedgerUnavailable):
        pl.open_positions()
    with pytest.raises(pl.LedgerUnavailable):
        pl.update([], "2026-01-01")
    assert ledger.read_text() == bad, "writer overwrote a structurally-invalid ledger"


def test_quarantined_keys_are_named_for_deterministic_recovery(ledger):
    """Recovery must be deterministic: the operator is told exactly which records to repair."""
    from portfolio import position_log as pl

    _seed(ledger, {
        "conviction:AAA": _open_entry("AAA"),
        "conviction:BAD": "not-an-entry",
        "conviction:ALSOBAD": {"sleeve": "conviction"},
    })

    st = pl.status()
    assert st["state"] == "unavailable"
    assert sorted(st["quarantined"]) == ["conviction:ALSOBAD", "conviction:BAD"]


def test_recovery_after_repair_is_deterministic(ledger):
    """Restart semantics: repair the file and the ledger resumes with history intact."""
    from portfolio import position_log as pl

    good = {"conviction:AAA": _open_entry("AAA")}
    _seed(ledger, good)
    ledger.write_text(json.dumps(good)[:-8])                     # truncate → corrupt

    with pytest.raises(pl.LedgerUnavailable):
        pl.open_positions()

    _seed(ledger, good)                                          # operator restores
    assert pl.status()["state"] == "populated"
    assert [p["ticker"] for p in pl.open_positions()] == ["AAA"]

    pl.close_position("conviction", "AAA", "2026-02-02", reason="hard_exit_sweep")
    closed = pl.closed_positions()
    assert [c["ticker"] for c in closed] == ["AAA"]
    assert closed[0]["reason_code"] == "hard_veto"
    # the pre-corruption open event survived the round trip
    assert json.loads(ledger.read_text())["conviction:AAA"]["history"][0]["event"] == "open"


# ════════════════════════════════════════════════════════════════════════════════════════════════
# RISK CONSUMER — unreadable lifecycle evidence must not read as "flat"
# ════════════════════════════════════════════════════════════════════════════════════════════════

def _derisk_module():
    from bot import derisk
    return derisk


def test_flagship_derisk_does_not_report_flat_on_an_unreadable_ledger(ledger, monkeypatch,
                                                                      tmp_path):
    """The headline defect: a corrupt ledger suppressed the de-risk cut as ``skipped: flat``
    while the paper account still held real positions."""
    derisk = _derisk_module()
    monkeypatch.setattr(derisk, "_ARTIFACTS", tmp_path / "artifacts")
    monkeypatch.setattr(derisk, "enabled", lambda: True)
    monkeypatch.setattr(derisk, "_archived_noop", lambda pid, asof: None)
    ledger.write_text("{corrupt")

    res = derisk.derisk_flagship("2026-02-02", regime={}, force=True)

    assert res.get("skipped") != "flat", (
        "unreadable held-risk evidence was reported as a flat book")
    assert res.get("skipped") == "positions_ledger_unavailable"
    assert res.get("ledger_unavailable") is True
    assert res.get("error")


def test_heavyweight_derisk_does_not_report_flat_on_an_unreadable_ledger(tmp_path, monkeypatch):
    """Same invariant on the Heavyweight arm, which reads its own portfolio_id."""
    from portfolio import position_log as pl
    derisk = _derisk_module()

    hw_dir = tmp_path / "heavyweight"
    hw_dir.mkdir(parents=True, exist_ok=True)
    (hw_dir / "positions_ledger.json").write_text("{corrupt")
    monkeypatch.setattr(pl, "_ledger_path",
                        lambda portfolio_id=None: hw_dir / "positions_ledger.json")
    monkeypatch.setattr(derisk, "_ARTIFACTS", tmp_path / "artifacts")
    monkeypatch.setattr(derisk, "enabled", lambda: True)
    monkeypatch.setattr(derisk, "_archived_noop", lambda pid, asof: None)

    res = derisk.derisk_heavyweight("2026-02-02", regime={}, force=True)

    assert res.get("skipped") != "flat"
    assert res.get("skipped") == "positions_ledger_unavailable"


def test_distribution_escalation_reports_unavailability_instead_of_no_tells(ledger, monkeypatch):
    """``_distribution_escalation`` is SHRINK-ONLY, so an unreadable ledger silently withholds a
    severity bump — under-reaction is risk suppression too. It must say so rather than return a
    bare ``(0, "")`` that is indistinguishable from "the book is not distributing"."""
    derisk = _derisk_module()
    ledger.write_text("{corrupt")

    bump, reason, unavailable = derisk._distribution_escalation("flagship")

    assert unavailable is True
    assert bump == 0, "no tells can be computed from an unreadable book — never fabricate a bump"
    assert "unavailable" in reason.lower()


def test_tripwire_surfaces_ledger_unavailability_in_its_reasons(ledger, monkeypatch):
    """The tripwire never raises, so unavailability has to travel as evidence in the result."""
    derisk = _derisk_module()
    monkeypatch.setattr(derisk, "_regime", lambda: {})
    ledger.write_text("{corrupt")

    tw = derisk.tripwire("flagship", "2026-02-02", regime={})

    assert tw["ledger_unavailable"] is True
    assert any("ledger" in r.lower() for r in tw["reasons"])


def test_healthy_empty_ledger_still_reports_flat(ledger, monkeypatch, tmp_path):
    """Control: a genuinely flat book keeps its existing ``skipped: flat`` contract."""
    derisk = _derisk_module()
    monkeypatch.setattr(derisk, "_ARTIFACTS", tmp_path / "artifacts")
    monkeypatch.setattr(derisk, "enabled", lambda: True)
    monkeypatch.setattr(derisk, "_archived_noop", lambda pid, asof: None)
    _seed(ledger, {})

    res = derisk.derisk_flagship("2026-02-02", regime={}, force=True)

    assert res.get("skipped") == "flat"
    assert res.get("ledger_unavailable") is not True


# ════════════════════════════════════════════════════════════════════════════════════════════════
# OBSERVATIONAL CONSUMER — the dashboard keeps its envelope, but stops claiming a flat book
# ════════════════════════════════════════════════════════════════════════════════════════════════

def _live_dashboard_book() -> str:
    """The dashboard's archived branch never reads this ledger (it serves frozen rows), so the
    degradation contract has to be exercised on a book that is still live."""
    from portfolio import registry
    for pid in ("autonomous", "china", "hk"):
        try:
            if not registry.is_archived(pid):
                return pid
        except Exception:  # noqa: BLE001
            continue
    pytest.skip("no live (non-archived) book available to exercise the dashboard read")


@pytest.fixture()
def dashboard_ledger(tmp_path, monkeypatch):
    """Pin every portfolio_id's ledger to one real file, so the route reads what the test wrote."""
    from portfolio import position_log as pl
    path = tmp_path / "dash" / "positions_ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pl, "_ledger_path", lambda portfolio_id=None: path)
    return path


def test_dashboard_trades_read_reports_the_outage_rather_than_a_flat_book(dashboard_ledger):
    """``/api/trades`` already wraps its body in ``except Exception`` and returns an ``error``
    field, so an unavailable ledger travels the EXISTING degraded envelope — the route shape is
    unchanged and the dashboard does not 500. What changes is that the payload now carries the
    outage instead of silently presenting an empty book as the truth."""
    from app import web

    dashboard_ledger.write_text("{corrupt")

    data = json.loads(web.api_trades(portfolio=_live_dashboard_book()).body)

    assert data["open"] == [] and data["closed"] == []       # envelope shape preserved
    assert "unavailable" in str(data.get("error", "")).lower(), (
        f"the outage never reached the dashboard payload: {data.get('error')!r}")


def test_dashboard_trades_read_is_unchanged_on_a_healthy_ledger(dashboard_ledger):
    """Control: a healthy ledger keeps the ordinary, error-free dashboard contract."""
    from app import web

    _seed(dashboard_ledger, {"conviction:AAA": _open_entry("AAA")})

    data = json.loads(web.api_trades(portfolio=_live_dashboard_book()).body)

    assert not data.get("error"), data.get("error")
    assert [row["ticker"] for row in data["open"]] == ["AAA"]
