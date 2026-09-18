"""Forward-proof readiness watcher — the system tells YOU when to revisit, instead of tracking dates.

Each forward-proof mechanism (calibration, the universe-wide cross-sectional IC, the shadow books)
is gated on DATA ACCRUAL and crosses its "now statistically honest / now readable" threshold months
out. This module checks those thresholds and records the moment one is NEWLY crossed — exactly once
per crossing — so a persistent alert can surface on the dashboard.

It rides the DAILY BUILD (bot.phase2 calls check_and_record at the end), which is the always-on
heartbeat — no Claude session, no 7-day-expiring cron. Cheap reads only (no panel loads); never raises.

Watched thresholds:
  calibration_forge / calibration_sentinel  — agent left cold-start (n >= MIN_N) → confidence self-corrects
  prediction_xsec                            — >= MIN_DATES independent entry-date clusters → cross-sectional IC honest
  shadow_forward                             — shadow books have their first resolved forward outcomes (risk-tilt A/B readable)
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "shadow" / "readiness_state.json"
_ALERTS = _ROOT / "data" / "shadow" / "readiness_alerts.jsonl"
_LOCAL_LOCK = threading.RLock()

_LABELS = {
    "calibration_forge": "Calibration (FORGE) left cold-start — its stated confidence now self-corrects "
                         "to realized reliability. Worth a look at the Track Record / calibration readout.",
    "calibration_sentinel": "Calibration (SENTINEL) left cold-start — the adversary's confidence now "
                            "self-corrects to its realized hit-rate.",
    "prediction_xsec": "Cross-sectional edge is now statistically honest — the prediction log reached "
                       "enough independent date-clusters. Go read the Cross-Sectional Edge panel.",
    "shadow_forward": "Shadow books have their first resolved forward outcomes — the risk-tilt A/B vs "
                      "prod (and the policy leaderboard) is now readable.",
}


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _optional_mapping(path: Path) -> tuple[dict | None, str]:
    """Distinguish first-run absence from existing unreadable readiness evidence."""
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "failed"
    if not isinstance(payload, dict):
        return None, "failed"
    return payload, "ok"


def _read_alert_rows() -> list[dict]:
    """Canonical readiness evidence; missing is empty, malformed is unavailable."""
    if not _ALERTS.exists():
        return []
    rows: list[dict] = []
    for line in _ALERTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("flag"), str):
            raise ValueError("readiness alert row is malformed")
        rows.append(row)
    return rows


def _fsync_parent(path: Path) -> None:
    try:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
        _fsync_parent(path)
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _write_alert_rows(rows: list[dict]) -> None:
    if not all(isinstance(row, dict) and isinstance(row.get("flag"), str) for row in rows):
        raise ValueError("readiness alert rows must be mappings with flags")
    _atomic_write(
        _ALERTS,
        "".join(json.dumps(row, default=str) + "\n" for row in rows),
    )


def _write_state(flags: set[str]) -> None:
    _atomic_write(_STATE, json.dumps({flag: True for flag in sorted(flags)}, indent=2))


def _state_projection_current(flags: set[str]) -> bool:
    if not _STATE.exists():
        return not flags
    try:
        payload = json.loads(_STATE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return False
        projected = {str(key) for key, value in payload.items() if value is True}
        return projected == flags and all(value is True for value in payload.values())
    except Exception:
        return False


def _readiness_lock_path() -> Path:
    return _ALERTS.with_name(".readiness.lock")


@contextmanager
def _readiness_lock():
    with _LOCAL_LOCK:
        _ALERTS.parent.mkdir(parents=True, exist_ok=True)
        with _readiness_lock_path().open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass


def status() -> dict:
    """Current readiness flags + supporting counts, with unavailable sources kept unknown."""
    flags: dict[str, bool | None] = {}
    detail: dict[str, dict] = {}
    failed_sources: list[str] = []

    cal, cal_state = _optional_mapping(_ROOT / "data" / "brain" / "calibration.json")
    if cal_state == "failed":
        failed_sources.append("calibration")
        for who in ("forge", "sentinel"):
            key = f"calibration_{who}"
            flags[key] = None
            detail[key] = {"n": None, "need": None, "read_status": "unavailable"}
    else:
        try:
            agents = (cal or {}).get("agents") or {}
            if not isinstance(agents, dict):
                raise TypeError("calibration agents are malformed")
            minn = (cal or {}).get("min_n", 12)
            if not isinstance(minn, (int, float)) or isinstance(minn, bool):
                raise TypeError("calibration min_n is malformed")
            for who in ("forge", "sentinel"):
                row = agents.get(who) or {}
                if not isinstance(row, dict):
                    raise TypeError("calibration agent row is malformed")
                n = int(row.get("n", 0) or 0)
                key = f"calibration_{who}"
                flags[key] = n >= int(minn)
                detail[key] = {"n": n, "need": int(minn)}
        except Exception:
            if "calibration" not in failed_sources:
                failed_sources.append("calibration")
            for who in ("forge", "sentinel"):
                key = f"calibration_{who}"
                flags[key] = None
                detail[key] = {"n": None, "need": None, "read_status": "unavailable"}

    try:
        from portfolio import predictions as P
        ledger = P._load_ledger()
        if not isinstance(ledger, list) or not all(isinstance(row, dict) for row in ledger):
            raise TypeError("prediction ledger is malformed")
        resolved_dates = sorted({
            row["asof"]
            for row in ledger
            if row.get("status") == "resolved" and row.get("asof")
        })
        independent = len(P._thin_independent([(day, 1) for day in resolved_dates]))
        flags["prediction_xsec"] = independent >= P._MIN_DATES
        detail["prediction_xsec"] = {
            "independent_clusters": independent,
            "need": P._MIN_DATES,
        }
    except Exception:
        failed_sources.append("prediction_xsec")
        try:
            need = P._MIN_DATES
        except Exception:
            need = None
        flags["prediction_xsec"] = None
        detail["prediction_xsec"] = {
            "independent_clusters": None,
            "need": need,
            "read_status": "unavailable",
        }

    leaderboard, leaderboard_state = _optional_mapping(
        _ROOT / "data" / "shadow" / "leaderboard.json"
    )
    if leaderboard_state == "failed":
        failed_sources.append("shadow_forward")
        flags["shadow_forward"] = None
        detail["shadow_forward"] = {
            "max_resolved": None, "need": 5, "read_status": "unavailable"
        }
    else:
        try:
            books = (leaderboard or {}).get("books") or {}
            if not isinstance(books, dict) or not all(
                isinstance(value, dict) for value in books.values()
            ):
                raise TypeError("shadow leaderboard books are malformed")
            n_resolved = max(
                (int((book or {}).get("n_resolved", 0) or 0) for book in books.values()),
                default=0,
            )
            flags["shadow_forward"] = n_resolved >= 5
            detail["shadow_forward"] = {"max_resolved": n_resolved, "need": 5}
        except Exception:
            failed_sources.append("shadow_forward")
            flags["shadow_forward"] = None
            detail["shadow_forward"] = {
                "max_resolved": None, "need": 5, "read_status": "unavailable"
            }

    result: dict = {"flags": flags, "detail": detail}
    if failed_sources:
        result["read_status"] = "unavailable" if len(set(failed_sources)) == 3 else "partial"
        result["failed_sources"] = sorted(set(failed_sources))
    return result


def check_and_record(asof: str | None = None) -> dict:
    """Persist newly crossed readiness thresholds exactly once.

    The alert ledger is canonical durable evidence. ``readiness_state.json`` is only a projection
    and is rebuilt from that ledger, so a lost state write cannot duplicate a crossing later.
    """
    asof = str(asof or date.today().isoformat())[:10]
    st = status()
    flags = st["flags"]
    with _readiness_lock():
        try:
            rows = _read_alert_rows()
        except Exception:
            pending = [key for key, value in flags.items() if value]
            return {
                "new": [],
                "flags": flags,
                "pending_new": pending,
                "persistence_status": "unavailable",
                "error": "readiness_alert_ledger_unavailable",
            }

        recorded = {
            str(row.get("flag"))
            for row in rows
            if isinstance(row.get("flag"), str)
        }
        new = [key for key, value in flags.items() if value and key not in recorded]
        if new:
            additions = [
                {"date": asof, "flag": key, "message": _LABELS.get(key, key)}
                for key in new
            ]
            try:
                _write_alert_rows([*rows, *additions])
            except Exception:
                return {
                    "new": [],
                    "flags": flags,
                    "pending_new": new,
                    "persistence_status": "unavailable",
                    "error": "readiness_alert_write_failed",
                }
            recorded.update(new)

        # State is a rebuildable projection only. Once an alert is durable, state failure must not
        # cause the same crossing to be appended again on the next run.
        try:
            if not _state_projection_current(recorded):
                _write_state(recorded)
        except Exception:
            return {
                "new": new,
                "flags": flags,
                "persistence_status": "partial",
                "state_heal_pending": True,
                "error": "readiness_state_write_failed",
            }

    return {"new": new, "flags": flags}


def alerts(limit: int = 20) -> list:
    """Recorded readiness alerts (most recent last). For the dashboard banner."""
    rows = _read_alert_rows()
    return rows[-limit:]
