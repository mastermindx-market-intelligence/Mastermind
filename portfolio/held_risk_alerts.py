"""Alert governor for portfolio held-risk desk (W3).

Deterministic, pure-logic module: reads previous + new risk_state, fires on
TRANSITIONS only (role worsened OR new elevated lane joins), with per-role
cooldowns. Publishes to alerts.jsonl; sends Discord; no advice verbs.

PRD-R4: review language only; no advice verbs (buy/sell/add/trim as imperatives).
PRD-R7: no shares/notional/entry price in alert text.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("mastermind.pfolio.alerts")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ALERT_STATE_PATH = _REPO_ROOT / "data" / "portfolio_watch" / "alert_state.json"
_ALERTS_LOG_PATH = _REPO_ROOT / "data" / "portfolio_watch" / "alerts.jsonl"
_LOCAL_LOCK = threading.RLock()

# Role ladder order (lower index = lower severity; worsening = higher index)
_ROLE_ORDER = ["ok", "info", "monitor", "review", "tighten", "trim_review", "exit_review"]

# Cooldowns in sessions per role
_COOLDOWNS: dict[str, int] = {
    "monitor": 5,
    "review": 3,
    "tighten": 2,
    "trim_review": 2,
    "exit_review": 1,
}

# Role display labels (PRD-R4)
_ROLE_LABELS = {
    "exit_review": "Exit Review",
    "trim_review": "Take-Profit Review",
    "tighten": "Tighten",
    "review": "Review",
    "monitor": "Monitor",
    "info": "Info",
    "ok": "Ok",
}

# Banned advice verbs regex (PRD-R4)
_ADVICE_VERB_RE = re.compile(
    r"\b(buy|sell|add|trim|purchase|exit|close|short|long)\b",
    re.IGNORECASE,
)


def _role_index(role: str) -> int:
    try:
        return _ROLE_ORDER.index(role)
    except ValueError:
        return 0


def _default_alert_state() -> dict:
    return {"as_of": None, "cooldown": {}, "last_roles": {}, "last_lanes": {}}


def _load_alert_state() -> dict:
    try:
        _ALERT_STATE_PATH.lstat()
    except FileNotFoundError:
        return _default_alert_state()
    state = json.loads(_ALERT_STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("alert_state.json must contain a mapping")
    for key in ("cooldown", "last_roles", "last_lanes"):
        value = state.get(key)
        if value is None:
            state[key] = {}
        elif not isinstance(value, dict):
            raise ValueError(f"alert_state.{key} must be a mapping")
    return state


def _load_alert_rows() -> list[dict]:
    try:
        _ALERTS_LOG_PATH.lstat()
    except FileNotFoundError:
        return []
    rows: list[dict] = []
    for line in _ALERTS_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("alerts.jsonl row must be a mapping")
        rows.append(row)
    return rows


def _fsync_parent(path: Path) -> None:
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_replace_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
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


def _save_alert_state(state: dict) -> None:
    if not isinstance(state, dict):
        raise ValueError("alert state must be a mapping")
    _atomic_replace_text(
        _ALERT_STATE_PATH,
        json.dumps(state, indent=2, default=str) + "\n",
    )


def _lock_path() -> Path:
    return _ALERTS_LOG_PATH.with_name(".held_risk_alerts.lock")


@contextmanager
def _governor_lock():
    """Serialize canonical alert-log and cooldown-state decisions across processes."""
    with _LOCAL_LOCK:
        _ALERTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock_path().open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass


def _append_alert_unlocked(record: dict) -> bool:
    if not isinstance(record, dict):
        raise ValueError("alert record must be a mapping")
    rows = _load_alert_rows()
    if _recorded_alert_matches(rows, record):
        return False
    payload = "".join(
        json.dumps(row, default=str) + "\n"
        for row in [*rows, record]
    )
    _atomic_replace_text(_ALERTS_LOG_PATH, payload)
    return True


def _append_alert(record: dict) -> bool:
    """Publish one alert exactly once; False means the exact alert id already exists."""
    with _governor_lock():
        return _append_alert_unlocked(record)


def _send_discord(headline: str) -> None:
    """POST alert headline to Discord webhook. Fail-soft."""
    webhook_url = (
        os.environ.get("DISCORD_WEBHOOK_PORTFOLIO")
        or os.environ.get("DISCORD_WEBHOOK_URL")
    )
    if not webhook_url:
        return
    try:
        payload = json.dumps({"content": headline[:1900]}).encode()
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                log.warning("Discord webhook returned %s", resp.status)
    except Exception as exc:
        log.warning("Discord send failed (fail-soft): %s", exc)


def _make_alert_id(ticker: str, role: str, alert_date: str, lane_names: list[str]) -> str:
    initials = "".join(sorted(n[:2] for n in lane_names)) if lane_names else "xx"
    return f"pfolio:{ticker}:{role}:{alert_date}:{initials}"


def _alert_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be an ISO date") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be an ISO date")
    return parsed


def _recorded_alert_matches(rows: list[dict], record: dict) -> bool:
    """Only the same complete effect identity may satisfy an existing alert id."""
    alert_id = record.get("alert_id")
    matched = False
    for row in rows:
        if alert_id and row.get("alert_id") == alert_id:
            if any(row.get(key) != record.get(key) for key in (
                "source", "ticker", "type", "position_id", "lanes",
            )):
                raise ValueError("alert id has conflicting recorded identity")
            matched = True
    return matched


def _reconcile_alert_cooldowns(
    alert_state: dict, rows: list[dict], today_d: date,
) -> set[str]:
    """Repair a proven log/state split without replaying a notification.

    The state has one session cursor, not a historical session ledger. An older
    missing cooldown cannot be reconstructed after that cursor has advanced.
    """
    cursor_value = alert_state.get("as_of")
    cursor = _alert_date(cursor_value, "alert state cursor") if cursor_value is not None else None
    if cursor is not None and cursor > today_d:
        raise ValueError("alert state cursor cannot move backwards")
    cooldown = alert_state.setdefault("cooldown", {})
    cooldown_dates: dict[str, date] = {}
    for ticker, cd in cooldown.items():
        if (not isinstance(cd, dict) or not isinstance(cd.get("role"), str)
                or cd["role"] not in _COOLDOWNS):
            raise ValueError("alert cooldown entry must contain a valid role")
        count = cd.get("sessions_since")
        if type(count) is not int or count < 0:
            raise ValueError("alert cooldown sessions must be a nonnegative integer")
        last = _alert_date(cd.get("last_alert"), "alert cooldown date")
        if last > today_d:
            raise ValueError("alert cooldown date is in the future")
        cooldown_dates[ticker] = last

    events: dict[str, list[tuple[date, int, dict]]] = {}
    identities: dict[str, dict] = {}
    for index, row in enumerate(rows):
        if row.get("source") != "portfolio_desk":
            continue
        ticker, role = row.get("ticker"), row.get("type")
        lanes, position_id, alert_id = row.get("lanes"), row.get("position_id"), row.get("alert_id")
        if (not isinstance(ticker, str) or not ticker.strip() or ticker != ticker.upper()
                or not isinstance(role, str) or role not in _COOLDOWNS
                or not isinstance(position_id, str) or not position_id
                or not isinstance(lanes, list)
                or any(not isinstance(lane, str) or not lane.strip() for lane in lanes)
                or lanes != sorted(set(lanes))
                or not isinstance(alert_id, str)):
            raise ValueError("recorded portfolio alert identity is malformed")
        prefix = f"pfolio:{ticker}:{role}:"
        if not alert_id.startswith(prefix) or ":" not in alert_id[len(prefix):]:
            raise ValueError("recorded portfolio alert id is malformed")
        decision_date = _alert_date(alert_id[len(prefix):].rsplit(":", 1)[0], "recorded alert date")
        if alert_id != _make_alert_id(ticker, role, decision_date.isoformat(), lanes):
            raise ValueError("recorded portfolio alert id does not match its evidence")
        if decision_date > today_d:
            raise ValueError("recorded alert date is in the future")
        if alert_id in identities:
            _recorded_alert_matches([identities[alert_id]], row)
        identities[alert_id] = row
        events.setdefault(ticker, []).append((decision_date, index, row))

    recovered: set[str] = set()
    for ticker, history in events.items():
        event_date, event_index, event = max(history, key=lambda value: (value[0], value[1]))
        cd, last = cooldown.get(ticker), cooldown_dates.get(ticker)
        if last is not None and last > event_date:
            continue
        if last == event_date and cd["role"] == event["type"]:
            continue
        if last == event_date and not any(
            day == event_date and index < event_index and row["type"] == cd["role"]
            for day, index, row in history
        ):
            raise ValueError("same-date cooldown ordering is unavailable")
        if (cursor is not None and cursor > event_date) or (cursor is None and event_date < today_d):
            raise ValueError("alert cooldown recovery history is unavailable")
        cooldown[ticker] = {
            "role": event["type"],
            "last_alert": event_date.isoformat(),
            "sessions_since": 0 if event_date == today_d else 1,
        }
        recovered.add(ticker)
    return recovered


def _elevated_lanes(pos: dict) -> set[str]:
    """Return set of lane names currently elevated for a position."""
    lanes = pos.get("lanes") or {}
    return {name for name, lane in lanes.items() if lane.get("state") == "elevated"}


def _check_cooldown(ticker: str, role: str, alert_state: dict) -> bool:
    """Return True if alert should fire (not in cooldown), False if suppressed."""
    cooldown_sessions = _COOLDOWNS.get(role, 1)
    cd = alert_state.get("cooldown", {}).get(ticker, {})
    sessions_since = cd.get("sessions_since", 999)
    last_role = cd.get("role")

    if last_role == role and sessions_since < cooldown_sessions:
        return False
    return True


def _build_headline(
    ticker: str,
    role: str,
    lane_names: list[str],
    reasons: list[str],
    alert_date: str,
) -> str:
    """Build alert headline per PRD-R4 template. No advice verbs."""
    role_label = _ROLE_LABELS.get(role, role)
    pairs = []
    for name, reason in zip(lane_names[:3], reasons[:3]):
        if reason:
            pairs.append(f"{name}: {reason[:80]}")
        else:
            pairs.append(name)
    detail = "; ".join(pairs) if pairs else "see risk lanes"
    headline = f"PORTFOLIO \u00b7 {ticker} {role_label} \u2014 {detail} ({alert_date})"
    if _ADVICE_VERB_RE.search(headline):
        headline = _ADVICE_VERB_RE.sub("[review]", headline)
    return headline


def _run_alerts_locked(
    prev_state: dict | None,
    new_state: dict,
    today_d: date,
) -> list[dict]:
    today_str = today_d.isoformat()
    alert_state = _load_alert_state()
    rows = _load_alert_rows()
    recovered = _reconcile_alert_cooldowns(alert_state, rows, today_d)
    fired: list[dict] = []

    last_as_of = alert_state.get("as_of")
    new_session = last_as_of != today_str
    if new_session:
        for ticker, cd in alert_state.get("cooldown", {}).items():
            if ticker not in recovered:
                cd["sessions_since"] += 1

    prev_positions: dict[str, dict] = {}
    if prev_state:
        for pos in (prev_state.get("positions") or []):
            ticker = (pos.get("ticker") or "").upper()
            if ticker:
                prev_positions[ticker] = pos

    for pos in (new_state.get("positions") or []):
        ticker = (pos.get("ticker") or "").upper()
        if not ticker:
            continue

        role = pos.get("role", "ok")
        elevated = _elevated_lanes(pos)
        active_lanes = sorted(elevated)
        if role not in ("ok", "info"):
            _recorded_alert_matches(rows, {
                "alert_id": _make_alert_id(ticker, role, today_str, active_lanes),
                "source": "portfolio_desk", "ticker": ticker, "type": role,
                "position_id": str(pos.get("position_id", ticker)), "lanes": active_lanes,
            })
        prev_pos = prev_positions.get(ticker)
        prev_role = prev_pos.get("role", "ok") if prev_pos else "ok"
        prev_elevated = _elevated_lanes(prev_pos) if prev_pos else set()

        role_worsened = _role_index(role) > _role_index(prev_role)
        new_lanes = elevated - prev_elevated
        same_role_new_lane = (
            role == prev_role
            and bool(new_lanes)
            and _role_index(role) > _role_index("ok")
        )

        if not (role_worsened or same_role_new_lane):
            continue
        if role in ("ok", "info"):
            continue
        if not _check_cooldown(ticker, role, alert_state):
            continue

        reasons = []
        lanes_dict = pos.get("lanes") or {}
        for lane_name in active_lanes[:3]:
            lane = lanes_dict.get(lane_name, {})
            lane_reasons = lane.get("reasons") or []
            reasons.append(lane_reasons[0] if lane_reasons else "")

        alert_id = _make_alert_id(ticker, role, today_str, active_lanes)
        headline = _build_headline(
            ticker,
            role,
            active_lanes,
            reasons,
            today_str,
        )

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "portfolio_desk",
            "type": role,
            "ticker": ticker,
            "position_id": str(pos.get("position_id", ticker)),
            "headline": headline,
            "detail": "; ".join(r for r in reasons[:5] if r),
            "lanes": active_lanes,
            "reasons": reasons,
            "alert_id": alert_id,
        }

        newly_written = _append_alert_unlocked(record)
        if newly_written:
            _send_discord(headline)
            fired.append(record)
            alert_state.setdefault("cooldown", {})[ticker] = {
                "role": role,
                "last_alert": today_str,
                "sessions_since": 0,
            }

    alert_state["as_of"] = today_str
    alert_state["last_roles"] = {
        (pos.get("ticker") or "").upper(): pos.get("role", "ok")
        for pos in (new_state.get("positions") or [])
        if (pos.get("ticker") or "").strip()
    }
    _save_alert_state(alert_state)
    return fired


def run_alerts(
    prev_state: dict | None,
    new_state: dict,
    *,
    today: date | None = None,
) -> list[dict]:
    """Run the transition alert governor under one process-safe publication boundary.

    Canonical alert-log and cooldown-state corruption propagate to the existing best-effort
    caller boundary instead of being reinterpreted as empty state. Discord remains fail-soft.
    """
    with _governor_lock():
        return _run_alerts_locked(prev_state, new_state, today or date.today())
