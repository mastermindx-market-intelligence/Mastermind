#!/usr/bin/env python3
"""pool_status.py — local slot/usage helpers for the lease broker.

Secret-free. Reads slot state, bailian_usage.json, ledger.jsonl.
`pool status` is served by ext/lease_broker.py, which writes
orch/fabric/status.json (schema mastermind.provider_capacity.v1) and
imports build_status() here for off-peak / last-402 / per-key cooldown.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
POOLS_DIR = os.path.join(HERE, "..", "orch", "fabric")
POOLS_YAML = os.path.join(POOLS_DIR, "pools.yaml")
STATUS_JSON = os.path.join(POOLS_DIR, "status.json")
LEDGER_PATH = os.path.join(POOLS_DIR, "ledger.jsonl")
BAILIAN_USAGE = os.path.join(HERE, "bailian_usage.json")
SLOT_ROOT = os.path.join(HERE, "slots")
GROK_EXHAUSTED = os.path.join(HERE, "GROK_EXHAUSTED")
SHANGHAI_TZ = "Asia/Shanghai"
GO_SHIM_URL = "http://127.0.0.1:4142/status"
GO_SHIM_TOKEN_PATH = os.path.normpath(os.path.join(HERE, "go_shim", ".token"))

CAPS = {"grok": 6, "cursor": 3, "minimax": 7}
ROUTING_POOLS = ("grok", "cursor", "bailian", "minimax", "glm", "claude")

if HERE not in sys.path:
    sys.path.insert(0, HERE)

import model_tier

# ── helpers ────────────────────────────────────────────────────────────────────

def _now_sh() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(SHANGHAI_TZ))


def _parse_ts(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
    except Exception:
        return str(ts)


def _slot_dir(pool: str) -> str:
    return os.path.join(SLOT_ROOT, pool)


def _alive_pids(pool: str) -> List[int]:
    """Return PIDs still alive in pool's slot dir."""
    d = _slot_dir(pool)
    if not os.path.isdir(d):
        return []
    alive = []
    for fn in os.listdir(d):
        if not fn.endswith(".lock"):
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, encoding="utf-8") as fh:
                pid = int(fh.read().strip().split()[0])
            if pid > 0:
                try:
                    os.kill(pid, 0)
                    alive.append(pid)
                except OSError:
                    pass
        except Exception:
            pass
    return alive


def _active(pool: str) -> int:
    return len(_alive_pids(pool))


def _cap(pool: str) -> int:
    if pool == "bailian":
        try:
            sys.path.insert(0, HERE)
            import bailian_keys
            return int(bailian_keys.total_cap())
        except Exception:
            return 8
    return CAPS.get(pool, 1)


def _bailian_per_key_cap() -> int:
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        return int(bailian_keys.current_per_key_cap())
    except Exception:
        return 7


def _grok_exhausted() -> bool:
    return os.path.exists(GROK_EXHAUSTED)


def _load_usage() -> dict:
    if not os.path.exists(BAILIAN_USAGE):
        return {}
    try:
        with open(BAILIAN_USAGE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _bailian_usage_is_current(usage: dict, now: Optional[datetime] = None) -> bool:
    """Only display reconstructed per-account usage when ALL rows are timely.

    A stale reconstruction never represents provider-authoritative quota.
    Slot and account admission remain governed by bailian_keys/lease_broker.
    """
    import math
    if not isinstance(usage, dict):
        return False
    rows = usage.get("keys")
    if not isinstance(rows, dict) or not rows:
        return False
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return False
    for row in rows.values():
        if not isinstance(row, dict):
            return False
        pct = row.get("pct_7d")
        if isinstance(pct, bool) or not isinstance(pct, (int, float)):
            return False
        if not math.isfinite(float(pct)) or not 0 <= pct <= 100:
            return False
        try:
            observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
            reset = datetime.fromisoformat(str(row["resets_at"]).replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError, OverflowError):
            return False
        if observed.tzinfo is None or reset.tzinfo is None:
            return False
        age = (now - observed).total_seconds()
        until_reset = (reset - now).total_seconds()
        if not 0 <= age <= 86400 or not 0 < until_reset <= 8 * 86400:
            return False
    return True


def _bailian_key_status() -> List[Dict[str, Any]]:
    """Per-key status from bailian_keys + usage file."""
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        all_names = bailian_keys.key_names()
    except Exception:
        return []
    usage = _load_usage()
    fresh_usage = _bailian_usage_is_current(usage)
    keys_data = usage.get("keys", {})
    result = []
    for name in all_names:
        info = keys_data.get(name, {})
        parked = info.get("parked", False) if fresh_usage else False
        pct = info.get("pct_7d") if fresh_usage else None
        resets_at = info.get("resets_at", "unknown") if fresh_usage else "unknown(stale)"
        try:
            cd_info = bailian_keys.cooldown_info(name)
        except Exception:
            cd_info = None
        if cd_info:
            expiry, reason = cd_info
            remain = max(0, expiry - int(time.time()))
            cooldown_s = f"{remain}s"
        else:
            cooldown_s = "none"
        if not fresh_usage:
            parked = bool(cd_info and len(cd_info) > 1 and cd_info[1] != "http_429")
        try:
            active = bailian_keys.active_count(name)
        except Exception:
            active = 0
        result.append({
            "name": name,
            "parked": parked,
            "pct_7d": pct,
            "resets_at": resets_at,
            "active": active,
            "cooldown": cooldown_s,
        })
    return result


def _is_offpeak() -> bool:
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        return bailian_keys.is_offpeak()
    except Exception:
        dt = _now_sh()
        h, m = dt.hour, dt.minute
        mins = h * 60 + m
        return mins >= 22 * 60 or mins < 8 * 60


def _offpeak_window() -> Dict[str, str]:
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        win = bailian_keys.offpeak_window()
        return win
    except Exception:
        return {"start": "22:00", "end": "08:00", "tz": "Asia/Shanghai"}


def _read_ledger(pool: Optional[str] = None, limit: int = 5000) -> List[dict]:
    records = []
    if not os.path.exists(LEDGER_PATH):
        return records
    try:
        with open(LEDGER_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if pool and rec.get("pool") != pool:
                    continue
                records.append(rec)
    except Exception:
        pass
    return records[-limit:]


def _model_share_view(limit: int = 5000) -> Optional[Dict[str, Any]]:
    """Combine bounded shim credits with attributed lane-ledger rows."""
    try:
        sys.path.insert(0, HERE)
        import pool_ledger

        share = pool_ledger.shim_model_share(limit=limit)
        by_model: Dict[str, Any] = {}
        for model, entry in share.get("by_model", {}).items():
            by_model[model] = dict(entry)
        lane_rows = {model: 0 for model in by_model}
        recorded = 0
        null_rows = 0
        for record in _read_ledger(pool="glm"):
            model = record.get("model")
            if record.get("pool") != "glm":
                continue
            if model is None:
                null_rows += 1
                continue
            recorded += 1
            lane_rows[model] = lane_rows.get(model, 0) + 1
        return {
            "limit": share.get("limit", limit),
            "rows_scanned": share.get("rows_scanned", 0),
            "lines_selected": share.get("lines_selected", limit),
            "by_model": by_model,
            "lane_rows": lane_rows,
            "ledger_model_field": {"recorded": recorded, "null": null_rows},
        }
    except Exception:
        return None


def _last_402_429(pool: str) -> Optional[str]:
    records = _read_ledger(pool=pool, limit=1000)
    for rec in reversed(records):
        sig = rec.get("signal", "")
        if sig in ("402", "429"):
            ts = rec.get("ts", 0)
            return _parse_ts(ts)
    return None


def _window_remaining(pool: str) -> str:
    """Human estimate of remaining window."""
    if pool == "minimax":
        # Weekly reset ~Sun 00:20Z
        now = datetime.now(timezone.utc)
        days_until = (6 - now.weekday()) % 7
        if days_until == 0 and (now.hour > 0 or (now.hour == 0 and now.minute >= 20)):
            days_until = 7
        if days_until == 0:
            days_until = 7
        hrs = days_until * 24 - now.hour - 1
        mins = now.minute
        return f"~{days_until}d {hrs}h"
    if pool == "grok":
        if _grok_exhausted():
            return "EXHAUSTED"
        return "weekly"
    if pool == "cursor":
        return "monthly"
    if pool == "bailian":
        if _is_offpeak():
            win = _offpeak_window()
            return f"offpeak {win['start']}-{win['end']} {_now_sh().tzname()}"
        usage = _load_usage()
        if not _bailian_usage_is_current(usage):
            return "quota_7d_unknown(stale_local_usage)"
        keys_data = usage.get("keys", {})
        low_pct = 100.0
        reset_str = "unknown"
        for name, info in keys_data.items():
            pct = info.get("pct_7d", 0)
            if pct < low_pct:
                low_pct = pct
                reset_str = info.get("resets_at", "unknown")
        return f"pct_7d={low_pct:.2f}% resets {reset_str}"
    return "—"


def _quota_states(provider: str) -> List[Dict[str, Any]]:
    try:
        import quota_remote
        return [vars(state) for state in quota_remote.read_provider(provider)]
    except Exception:
        return []


# ── routing law (R22/R23) ─────────────────────────────────────────────────────

def _load_pools_doc() -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
        with open(POOLS_YAML, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _roles_of(pool: str, doc: Optional[Dict[str, Any]] = None) -> List[str]:
    spec = ((doc or _load_pools_doc()).get("pools") or {}).get(pool) or {}
    role = spec.get("role", [])
    if isinstance(role, str):
        return [role]
    return list(role or [])


def _floor_policy(doc: Optional[Dict[str, Any]] = None) -> Tuple[float, int, str]:
    raw = ((doc or _load_pools_doc()).get("routing") or {}).get(
        "acceptance_floor", "0.6 over last 20"
    )
    label = str(raw)
    try:
        import re
        m = re.search(r"([0-9.]+)\s*over\s*last\s*(\d+)", label, re.I)
        if m:
            return float(m.group(1)), int(m.group(2)), label
    except Exception:
        pass
    return 0.6, 20, label


def _glm_enabled() -> bool:
    """True iff ~/.glm/config.json is present with non-empty api_key and model."""
    try:
        sys.path.insert(0, HERE)
        import glm_keys  # type: ignore
        return bool(glm_keys.enabled())
    except Exception:
        return False


def _glm_burn_snapshot() -> Optional[Dict[str, Any]]:
    """R26 credit burn via pool_ledger.glm_burn(); None when unavailable."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import pool_ledger
        return pool_ledger.glm_burn()
    except Exception:
        return None


def _glm_entry(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """R20-ish glm row: HOLD/note='no key' when disabled, PASS/cap+model when enabled.

    R26: when enabled, the entry also carries credits_5h/credits_week/pcts/state
    from glm-burn, and the acceptance floor flips to HOLD 'glm soft gate'
    SPILL (5-hour ≥ 90 %) or PARKED (weekly ≥ 95 %).
    """
    threshold, window, label = _floor_policy(doc)
    burn: Optional[Dict[str, Any]] = None
    if _glm_enabled():
        try:
            sys.path.insert(0, HERE)
            import glm_keys  # type: ignore
            cap_val = int(glm_keys.cap())
            model_val = str(glm_keys.model())
            floor = {
                "policy": label,
                "threshold": threshold,
                "window": window,
                "n": 0,
                "n_sample": 0,
                "rate": None,
                "state": "PASS",
                "demoted": False,
                "note": "key present",
            }
        except Exception:
            cap_val = 0
            model_val = ""
            floor = acceptance_floor_state("glm", doc)
            floor["note"] = "no key"
        if cap_val:
            burn = _glm_burn_snapshot()
            if burn:
                if burn.get("state") == "PARKED":
                    floor["state"] = "PARKED"
                    floor["note"] = "glm parked (weekly >= 95%)"
    else:
        cap_val = 0
        model_val = ""
        floor = {
            "policy": label,
            "threshold": threshold,
            "window": window,
            "n": 0,
            "n_sample": 0,
            "rate": None,
            "state": "HOLD",
            "demoted": False,
            "note": "no key",
        }
    return {
        "cap": cap_val,
        "active": _active("glm"),
        "remaining": max(0, cap_val - _active("glm")) if cap_val else 0,
        "last_402_429": "—",
        "window_remaining": "—",
        "role": _roles_of("glm", doc),
        "acceptance_floor": floor,
        "model": model_val,
        "credits_5h": burn.get("five_h_credits") if burn else None,
        "credits_week": burn.get("weekly_credits") if burn else None,
        "cap_5h": burn.get("cap_5h") if burn else None,
        "cap_week": burn.get("cap_week") if burn else None,
        "pct_5h": burn.get("pct_5h") if burn else None,
        "pct_week": burn.get("pct_week") if burn else None,
        "credit_state": burn.get("state") if burn else None,
        "target_5h": burn.get("pro_rata_target_5h") if burn else None,
        "raw_estimate_5h": burn.get("raw_five_h_credits") if burn else None,
        "calibration_factor": burn.get("calibration_factor") if burn else None,
        "calibration": burn.get("calibration") if burn else None,
        "calibration_age_hours": burn.get("calibration_age_hours") if burn else None,
        "five_h_anchor": str(burn.get("five_h_window_start")) if burn and burn.get("five_h_window_start") is not None else None,
        "anchor_source": burn.get("anchor_source") if burn else None,
        "five_h_reset": str(burn.get("five_h_reset")) if burn and burn.get("five_h_reset") else None,
        "weekly_reset": str(burn.get("weekly_reset")) if burn and burn.get("weekly_reset") else None,
        "quota_source": burn.get("quota_source", "UNKNOWN") if burn else "UNKNOWN",
        "quota_observed_at": burn.get("quota_observed_at") if burn else None,
        "quota_detail": burn.get("quota_detail") if burn else None,
        "credits_by_account": burn.get("credits_by_account") if burn else None,
    }


def acceptance_floor_state(pool: str, doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """R22 floor over last N outcome jobs for this pool (any class)."""
    threshold, window, label = _floor_policy(doc)
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import pool_ledger
        recs = pool_ledger.read_recent(limit=10_000)
        jobs = pool_ledger.outcome_jobs(recs, pool=pool)
        n = len(jobs)
        sample = jobs[-window:] if jobs else []
        n_sample = len(sample)
        if n_sample == 0:
            rate: Optional[float] = None
            state = "HOLD"
        else:
            rate = sum(1 for j in sample if pool_ledger.is_first_pass(j)) / float(n_sample)
            if n_sample < window:
                state = "HOLD"
            elif rate < threshold:
                state = "DEMOTE"
            else:
                state = "PASS"
        demoted = pool_ledger.below_acceptance_floor(
            jobs, threshold=threshold, window=window
        )
    except Exception:
        rate = None
        n = 0
        n_sample = 0
        state = "HOLD"
        demoted = False
    return {
        "policy": label,
        "threshold": threshold,
        "window": window,
        "n": n,
        "n_sample": n_sample,
        "rate": rate,
        "state": state,
        "demoted": demoted,
    }


# ── build status dict ─────────────────────────────────────────────────────────

def _go_status_snapshot() -> Optional[Dict[str, Any]]:
    try:
        with open(GO_SHIM_TOKEN_PATH, "r", encoding="utf-8") as token_file:
            token = token_file.read().strip()
        if not token:
            return None
        request = urllib.request.Request(
            GO_SHIM_URL,
            headers={"Authorization": " ".join(("Bearer", token))},
        )
        with urllib.request.urlopen(request, timeout=1.5) as response:
            document = json.load(response)
        return document if isinstance(document, dict) else None
    except Exception:
        return None


def _print_go_pool() -> None:
    snapshot = _go_status_snapshot()
    if snapshot is None:
        print("  GO POOL")
        print("    state=UNAVAILABLE (shim not running or token missing)")
        return

    print("  GO POOL")
    accounts = snapshot.get("accounts") if isinstance(snapshot.get("accounts"), dict) else {}
    pool = snapshot.get("pool") if isinstance(snapshot.get("pool"), dict) else {}
    for account_name in sorted(accounts):
        account = accounts.get(account_name)
        if not isinstance(account, dict):
            continue
        windows = account.get("provider_windows") if isinstance(account.get("provider_windows"), dict) else {}
        rolling = windows.get("rolling") if isinstance(windows.get("rolling"), dict) else {}
        weekly = windows.get("weekly") if isinstance(windows.get("weekly"), dict) else {}
        monthly = windows.get("monthly") if isinstance(windows.get("monthly"), dict) else {}
        reason = account.get("auth_failed_reason")
        exhausted = account.get("exhausted_until")
        print(
            f"    account={account_name} "
            f"rolling={rolling.get('percent', '-')}% "
            f"weekly={weekly.get('percent', '-')}% "
            f"monthly={monthly.get('percent', '-')}% "
            f"rolling_reset={rolling.get('resetsAt') or '-'} "
            f"weekly_reset={weekly.get('resetsAt') or '-'} "
            f"monthly_reset={monthly.get('resetsAt') or '-'} "
            f"rolling_status={rolling.get('status') or '-'} "
            f"weekly_status={weekly.get('status') or '-'} "
            f"monthly_status={monthly.get('status') or '-'} "
            f"exhausted_until={exhausted or '-'} "
            f"auth_failed={str(bool(account.get('auth_failed'))).lower()} "
            f"auth_failed_reason={reason or '-'}"
        )

    headroom = []
    for account_name, account in accounts.items():
        if not isinstance(account, dict):
            continue
        models = account.get("local_models") if isinstance(account.get("local_models"), dict) else {}
        for model_name, model_windows in models.items():
            rolling = model_windows.get("rolling") if isinstance(model_windows, dict) and isinstance(model_windows.get("rolling"), dict) else {}
            try:
                used_pct = float(rolling.get("pct"))
            except (TypeError, ValueError):
                used_pct = 0.0
            headroom.append((100.0 - used_pct, model_name))
    headroom.sort(key=lambda item: (-item[0], item[1]))
    model_text = " ".join(f"model={name} headroom={pct:.1f}%" for pct, name in headroom[:5])
    print(f"    top-5 per-model headroom: {model_text}")
    in_flight = sum(int((account or {}).get("in_flight") or 0) for account in accounts.values())
    print(
        f"    pool totals: accounts={pool.get('accounts', 0)} "
        f"eligible={pool.get('eligible', 0)} in_flight={in_flight}"
    )


def build_status() -> Dict[str, Any]:
    pools = ["grok", "cursor", "bailian", "minimax"]
    offpeak = _is_offpeak()
    offpeak_win = _offpeak_window()
    bailian_per_key = _bailian_per_key_cap()
    doc = _load_pools_doc()

    per_pool: Dict[str, Any] = {}
    quota_provenance = {
        provider: _quota_states(provider)
        for provider in ("minimax", "bailian")
    }

    for pool in pools:
        cap = _cap(pool)
        active = _active(pool)
        remaining = cap - active
        last_err = _last_402_429(pool) or "—"
        win_rem = _window_remaining(pool)
        roles = _roles_of(pool, doc)
        floor = acceptance_floor_state(pool, doc)

        entry: Dict[str, Any] = {
            "cap": cap,
            "active": active,
            "remaining": remaining,
            "last_402_429": last_err,
            "window_remaining": win_rem,
            "role": roles,
            "acceptance_floor": floor,
        }

        if pool == "grok":
            entry["exhausted"] = _grok_exhausted()
        if pool == "bailian":
            entry["per_key_cap"] = bailian_per_key
            entry["offpeak"] = offpeak
            entry["offpeak_window"] = offpeak_win
            entry["keys"] = _bailian_key_status()
        per_pool[pool] = entry

    for pool in ("glm", "claude"):
        if pool in per_pool:
            continue
        if pool == "glm":
            per_pool[pool] = _glm_entry(doc)
            continue
        per_pool[pool] = {
            "cap": _cap(pool) if pool != "claude" else None,
            "active": _active(pool) if pool != "claude" else 0,
            "remaining": None,
            "last_402_429": "—",
            "window_remaining": "—",
            "role": _roles_of(pool, doc),
            "acceptance_floor": acceptance_floor_state(pool, doc),
        }

    return {
        "generated_at": int(time.time()),
        "generated_at_human": datetime.now(timezone.utc).isoformat(),
        "pools": per_pool,
        "offpeak": offpeak,
        "acceptance_floor_policy": _floor_policy(doc)[2],
        "quota_provenance": quota_provenance,
    }


# ── HOST table (P1 multi-host routing) ────────────────────────────────────────

HOSTS_JSON_PATH = os.path.join(HERE, "hosts.json")
HOSTS_STATE_DIR = os.path.join(HERE, "state", "hosts")
HOST_STALE_SECS = 600

_DAY_TOKENS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_ERROR_SHORT = {
    "ssh_unreachable": "ssh",
    "probe_timeout": "tmo",
    "bad_probe_output": "bad",
}


def _short_error(err: Any) -> str:
    err = str(err or "unknown")
    return _ERROR_SHORT.get(err, err[:5])


def _days_match(days: Any, weekday: int) -> bool:
    """True when `days` ("Mon-Fri|Sat-Sun|All", comma lists ok) covers weekday."""
    days = str(days or "All").strip()
    if days in ("", "All", "*"):
        return True
    for part in days.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                i, j = _DAY_TOKENS.index(a), _DAY_TOKENS.index(b)
            except ValueError:
                continue
            if i <= j:
                if i <= weekday <= j:
                    return True
            elif weekday >= i or weekday <= j:  # wrapped range, e.g. Fri-Mon
                return True
        elif _DAY_TOKENS[weekday] == part:
            return True
    return False


def _hhmm_to_minutes(value: Any) -> Optional[int]:
    try:
        h, m = str(value).split(":")
        hh, mm = int(h), int(m)
    except (TypeError, ValueError):
        return None
    if 0 <= hh < 24 and 0 <= mm < 60:
        return hh * 60 + mm
    return None


def window_state(windows: Any, now_utc: datetime) -> str:
    """OPEN/CLOSED for a hosts.json `windows` list against a UTC datetime.

    Empty list (or anything falsy) = always open. A window applies when the
    current weekday matches `days` and the UTC minute-of-day falls in
    [open_utc, close_utc); close_utc <= open_utc wraps midnight.
    """
    if not windows:
        return "OPEN"
    mins = now_utc.hour * 60 + now_utc.minute
    weekday = now_utc.weekday()
    for win in windows:
        if not isinstance(win, dict):
            continue
        if not _days_match(win.get("days"), weekday):
            continue
        opened = _hhmm_to_minutes(win.get("open_utc"))
        closed = _hhmm_to_minutes(win.get("close_utc"))
        if opened is None or closed is None:
            continue
        if opened <= closed:
            inside = opened <= mins < closed
        else:
            inside = mins >= opened or mins < closed
        if inside:
            return "OPEN"
    return "CLOSED"


def _load_host_registry() -> Dict[str, Dict[str, Any]]:
    try:
        with open(HOSTS_JSON_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception:
        return {}
    if not isinstance(doc, dict):
        return {}
    return {k: v for k, v in doc.items() if k != "_doc" and isinstance(v, dict)}


def _fmt_host_age(secs: int) -> str:
    secs = max(0, int(secs))
    if secs < 5400:
        return f"{secs}s"
    if secs < 129600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"


def host_rows(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """One HOST-table row per registry host; state read from HOSTS_STATE_DIR only.

    Row flags: probe=NO_PROBE when no state file (or unreadable ts);
    age_label=STALE when the file is older than HOST_STALE_SECS; reachable
    False renders DOWN. The three conditions are independent — a stale DOWN
    probe shows both.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    registry = _load_host_registry()
    rows: List[Dict[str, Any]] = []
    for name in sorted(registry):
        entry = registry[name] or {}
        row: Dict[str, Any] = {
            "host": name,
            "roles": ",".join(str(r) for r in (entry.get("roles") or [])),
            "cores": entry.get("cores"),
            "lane_ceiling": entry.get("lane_ceiling"),
            "window": window_state(entry.get("windows"), now),
            "probe": "NO_PROBE",
            "reachable": None,
            "age": None,
            "age_label": "NO_PROBE",
        }
        path = os.path.join(HOSTS_STATE_DIR, name + ".json")
        try:
            with open(path, encoding="utf-8") as fh:
                st = json.load(fh)
        except Exception:
            rows.append(row)
            continue
        try:
            age = max(0, int(now.timestamp() - float(st.get("ts"))))
        except (TypeError, ValueError):
            rows.append(row)
            continue
        row["probe"] = "FILE"
        row["age"] = age
        row["age_label"] = "STALE" if age > HOST_STALE_SECS else _fmt_host_age(age)
        row["reachable"] = bool(st.get("reachable"))
        if row["reachable"]:
            row["load1"] = st.get("load1")
            row["mem_free_gb"] = st.get("mem_free_gb")
            row["disk_free_gb"] = st.get("disk_free_gb")
            row["active_lanes"] = st.get("active_lanes")
            row["on_ac"] = st.get("on_ac")
        else:
            row["error"] = st.get("error")
        rows.append(row)
    return rows


def print_host_table(now: Optional[datetime] = None) -> None:
    """P1 HOST table — ext/state/hosts/*.json only; no network here."""
    rows = host_rows(now=now)
    print("  HOST  (ext/state/hosts/*.json; refresh: bash ext/host_pull.sh --once)")
    if not rows:
        print("  (no hosts registered in hosts.json)")
        return
    print(
        f"  {'HOST':<5} {'ROLES':<17} {'LOAD1/CORES':>12} {'MEM_FREE':>9} "
        f"{'DISK_FREE':>10} {'ACTIVE/CEIL':>12} {'WINDOW':>7} {'AGE':>8}"
    )
    print(
        f"  {'─'*5} {'─'*17} {'─'*12} {'─'*9} {'─'*10} {'─'*12} {'─'*7} {'─'*8}"
    )
    for r in rows:
        roles = r.get("roles") or "—"
        if len(roles) > 17:
            roles = roles[:16] + "…"
        ceil = r.get("lane_ceiling")
        ceil_s = str(ceil) if isinstance(ceil, int) else "—"
        if r.get("probe") == "NO_PROBE":
            load = mem = disk = act = "—"
        elif not r.get("reachable"):
            load = f"DOWN({_short_error(r.get('error'))})"
            mem = disk = "—"
            act = f"—/{ceil_s}"
        else:
            l1 = r.get("load1")
            load = "—" if not isinstance(l1, (int, float)) else f"{float(l1):.1f}/{r.get('cores')}"
            mem_v = r.get("mem_free_gb")
            mem = "—" if not isinstance(mem_v, (int, float)) else f"{float(mem_v):.1f}g"
            dk_v = r.get("disk_free_gb")
            disk = "—" if not isinstance(dk_v, (int, float)) else f"{float(dk_v):.1f}g"
            act_v = r.get("active_lanes")
            act = f"{act_v if isinstance(act_v, int) else '—'}/{ceil_s}"
        print(
            f"  {r['host']:<5} {roles:<17} {load:>12} {mem:>9} {disk:>10} "
            f"{act:>12} {r.get('window', '—'):>7} {r.get('age_label', '—'):>8}"
        )


# ── human table ────────────────────────────────────────────────────────────────

COLS = 72

def _glm_credits_view(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """W4-G8b: convert a percentage-only authoritative snapshot to credits.

    The z.ai reader normalizes the 5h/weekly limits to percentage credits
    (used=pct, cap=100, detail 'z.ai quota/limit'), so printing its numbers
    next to the credit pro-rata target mixes units. Convert for display
    with the plan caps from glm_keys.plan() (credits_5h=28000,
    credits_week=140000): used_credits = pct / 100 * cap_credits.
    Returns None when the snapshot already carries credits (quota_source
    LOCAL_RECONSTRUCTION, or caps other than the percentage-only 100) and
    the existing credit-based line must stand. Presentation only — the
    FILL/OK/SPILL/PARKED decision logic is untouched.
    """
    if entry.get("quota_source") != "PROVIDER_AUTHORITATIVE":
        return None
    detail = str(entry.get("quota_detail") or "").lower()
    if "percent" not in detail and "quota/limit" not in detail:
        return None
    plan_caps: Dict[str, Tuple[str, float]] = {}
    for cap_key, plan_key, default in (
        ("cap_5h", "credits_5h", 28000.0),
        ("cap_week", "credits_week", 140000.0),
    ):
        try:
            if float(entry.get(cap_key)) != 100.0:
                return None
        except (TypeError, ValueError):
            return None
        plan_caps[cap_key] = (plan_key, default)
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import glm_keys
        plan: Dict[str, Any] = glm_keys.plan()
    except Exception:
        plan = {}
    view: Dict[str, Any] = {}
    for cap_key, pct_key, used_key in (
        ("cap_5h", "pct_5h", "used_5h"),
        ("cap_week", "pct_week", "used_week"),
    ):
        plan_key, default = plan_caps[cap_key]
        cap_credits = float(plan.get(plan_key, default) or default)
        pct = entry.get(pct_key)
        view[used_key] = (
            None if pct is None else float(pct) / 100.0 * cap_credits
        )
        view[cap_key] = cap_credits
    return view


def print_table(status: Dict[str, Any]) -> None:
    print()
    print(f"═" * COLS)
    print("  AGENT POOL STATUS".center(COLS))
    print(f"═" * COLS)
    offpeak = status.get("offpeak", _is_offpeak())
    print(f"  Off-peak window: {offpeak}  ({_offpeak_window()['start']}–{_offpeak_window()['end']} {_offpeak_window()['tz']})")
    print(f"  Generated: {status.get('generated_at_human', '?')}")
    print(f"─" * COLS)
    print(f"  {'POOL':<10} {'CAP':>4} {'ACTIVE':>6} {'REM':>4} {'LAST 402/429':>14} {'WINDOW REMAINING':<22}")
    print(f"  {'─'*10} {'─'*4} {'─'*6} {'─'*4} {'─'*14} {'─'*22}")

    for pool in ("grok", "cursor", "bailian", "minimax"):
        p = status["pools"].get(pool, {})
        cap = p.get("cap", 0)
        active = p.get("active", 0)
        rem = p.get("remaining", 0)
        last_err = p.get("last_402_429", "—")
        win = p.get("window_remaining", "—")
        exhausted = p.get("exhausted", False)
        if pool == "grok" and exhausted:
            rem = 0
            win = "EXHAUSTED"
        if pool == "cursor":
            win = "fallback (monthly, no window)"
        print(f"  {pool:<10} {cap:>4} {active:>6} {rem:>4} {last_err:>14} {win:<22}")

    print(f"─" * COLS)
    print("  ROUTING LAW  (R22/R23 role + acceptance floor)")
    print(f"  {'POOL':<10} {'ROLE':<22} {'FLOOR':<38}")
    print(f"  {'─'*10} {'─'*22} {'─'*38}")
    policy = status.get("acceptance_floor_policy", "0.6 over last 20")
    for pool in ROUTING_POOLS:
        p = status["pools"].get(pool, {})
        roles = p.get("role") or []
        role_s = ",".join(roles) if roles else "—"
        floor = p.get("acceptance_floor") or {}
        state = floor.get("state", "HOLD")
        n = floor.get("n", 0)
        rate = floor.get("rate")
        rate_s = "n/a" if rate is None else f"{rate:.2f}"
        print(f"  {pool:<10} {role_s:<22} {state} {rate_s} n={n} ({policy})")

    share_view = _model_share_view()
    view_limit = 5000
    if share_view:
        view_limit = int(share_view.get("limit", view_limit))
        rows_scanned = int(share_view.get("rows_scanned", 0))
        tail_lines = int(share_view.get("lines_selected", view_limit))
    else:
        rows_scanned = 0
        tail_lines = view_limit
    print(
        f"  MODEL SHARE  ({rows_scanned} rows scanned of {tail_lines} tail lines, cap {view_limit}; tier law: "
        "orch/fabric/MODEL_EFFICIENCY_RULING_2026-09-14.md)"
    )
    now = datetime.now(timezone.utc)
    if model_tier.flash_window_active(now):
        print("    campaign window: ACTIVE until 01:00Z")
    elif now >= model_tier.FLASH_WINDOW_END_TIME:
        print("    campaign window: expired")
    else:
        print("    campaign window: inactive")
    if not share_view or not share_view.get("by_model"):
        print("    state=UNAVAILABLE (no shim usage rows)")
    else:
        by_model = share_view.get("by_model", {})
        total_credits = sum(
            float(entry.get("credits", 0.0)) for entry in by_model.values()
        )
        lane_rows = share_view.get("lane_rows", {})
        for model, entry in sorted(
            by_model.items(),
            key=lambda item: (-float(item[1].get("credits", 0.0)), item[0]),
        ):
            credits = float(entry.get("credits", 0.0))
            share = credits * 100.0 / total_credits if total_credits else 0.0
            model_field = f"model:{model}"
            rows = int(lane_rows.get(model, 0))
            print(
                f"    {model_field:<20} credits={credits:.1f} "
                f"share={share:.1f}%  lane_rows={rows}"
            )
        ledger_field = share_view.get("ledger_model_field", {})
        recorded = int(ledger_field.get("recorded", 0))
        null_rows = int(ledger_field.get("null", 0))
        print(
            f"    ledger model field: recorded={recorded} null={null_rows} "
            "(null rows are unattributable)"
        )

    glm_p = status["pools"].get("glm", {})
    print("  GLM UTILIZATION")
    target = glm_p.get("target_5h")
    reset_5h = glm_p.get("five_h_reset")
    reset_week = glm_p.get("weekly_reset")
    target_s = "unavailable" if target is None else f"{float(target):.1f}"
    reset_5h_s = "unknown" if reset_5h is None else str(reset_5h)
    reset_week_s = "unknown" if reset_week is None else str(reset_week)
    raw = glm_p.get("raw_estimate_5h")
    factor = glm_p.get("calibration_factor")
    anchor = glm_p.get("five_h_anchor")
    calibration = glm_p.get("calibration")
    age = glm_p.get("calibration_age_hours")
    raw_s = "unavailable" if raw is None else f"{float(raw):.1f}"
    factor_s = "unavailable" if factor is None else f"{float(factor):.6f}"
    anchor_s = "unknown" if anchor is None else str(anchor)
    source_s = glm_p.get("anchor_source") or "rolling"
    calibration_s = "UNCALIBRATED"
    if calibration == "CALIBRATED":
        age_s = "unknown" if age is None else f"{float(age):.1f}h"
        calibration_s = f"CALIBRATED({factor_s}, age {age_s})"
    print("    cursor=fallback (monthly, no window)")
    state = glm_p.get("credit_state") or "UNAVAILABLE"
    credits_view = _glm_credits_view(glm_p)
    if credits_view is not None:
        # W4-G8b: authoritative snapshot is percentage-only — show plan
        # credits for used/cap so both slots share the target's unit.
        used_5h = credits_view["used_5h"]
        used_week = credits_view["used_week"]
        used_5h_s = "unavailable" if used_5h is None else f"{used_5h:.1f}"
        used_week_s = "unavailable" if used_week is None else f"{used_week:.1f}"
        print(
            f"    5h used/cap/pct={used_5h_s}/"
            f"{credits_view['cap_5h']:.0f}/{glm_p.get('pct_5h', 0):.1f}%  "
            f"target={target_s}  "
            f"source={glm_p.get('quota_source', 'UNKNOWN')} "
            f"observed_at={glm_p.get('quota_observed_at') or '-'}  "
            f"weekly used/cap/pct={used_week_s}/"
            f"{credits_view['cap_week']:.0f}/{glm_p.get('pct_week', 0):.1f}%  "
            f"source={glm_p.get('quota_source', 'UNKNOWN')} "
            f"observed_at={glm_p.get('quota_observed_at') or '-'}  state={state}"
        )
    else:
        print(
            f"    5h used/target/pct={glm_p.get('credits_5h', 0):.1f}/"
            f"{target_s}/{glm_p.get('pct_5h', 0):.1f}%  "
            f"source={glm_p.get('quota_source', 'UNKNOWN')} "
            f"observed_at={glm_p.get('quota_observed_at') or '-'}  "
            f"weekly used/pct={glm_p.get('credits_week', 0):.1f}/"
            f"{glm_p.get('pct_week', 0):.1f}%  "
            f"source={glm_p.get('quota_source', 'UNKNOWN')} "
            f"observed_at={glm_p.get('quota_observed_at') or '-'}  state={state}"
        )
    print(
        f"    5h raw={raw_s} factor={factor_s} "
        f"calibration={calibration_s}"
    )
    print(
        f"    5h anchor={anchor_s} source={source_s} "
        f"next reset: 5h={reset_5h_s} weekly={reset_week_s}"
    )
    # W4-G9: one line per account with shim credits. Lines omitted when no
    # shim contribution is in the window (e.g., ledger-only test fixtures).
    credits_by_account = glm_p.get("credits_by_account") or {}
    if credits_by_account:
        print("  GLM ACCOUNT BREAKDOWN")
        for account_name in sorted(credits_by_account):
            bucket = credits_by_account[account_name] or {}
            total = float(bucket.get("credits") or 0.0)
            rows = int(bucket.get("rows") or 0)
            print(
                f"    account={account_name} "
                f"credits={total:.1f} rows={rows}"
            )
    _print_go_pool()
    print("  QUOTA PROVENANCE")
    for provider in ("minimax", "bailian"):
        rows = status.get("quota_provenance", {}).get(provider, [])
        if not rows:
            print(
                f"    {provider} window=7d source=UNKNOWN used=UNKNOWN "
                "cap=UNKNOWN remaining_pct=UNKNOWN reset_at=unknown "
                "observed_at=- confidence=0.000"
            )
            continue
        for row in rows:
            used = "UNKNOWN" if row.get("used") is None else f"{row['used']:.2f}"
            cap = "UNKNOWN" if row.get("cap") is None else f"{row['cap']:.2f}"
            remain = (
                "UNKNOWN" if row.get("remaining_pct") is None
                else f"{row['remaining_pct']:.2f}"
            )
            confidence = (
                "UNKNOWN" if row.get("confidence") is None
                else f"{row['confidence']:.3f}"
            )
            print(
                f"    {provider} window={row.get('window', 'UNKNOWN')} "
                f"used={used} cap={cap} remaining_pct={remain} "
                f"reset_at={row.get('reset_at') or 'unknown'} "
                f"source={row.get('source', 'UNKNOWN')} "
                f"observed_at={row.get('observed_at') or '-'} "
                f"confidence={confidence}"
            )
    print(f"─" * COLS)
    print("  BAILIAN KEYS")
    print(f"  {'─'*10} {'─'*10} {'─'*8} {'─'*10} {'─'*8}")
    print(f"  {'NAME':<12} {'PARKED':>8} {'PCT_7D':>8} {'RESETS_AT':>22} {'COOLDOWN':>10}")
    print(f"  {'─'*12} {'─'*8} {'─'*8} {'─'*22} {'─'*10}")
    bailian_keys = status["pools"].get("bailian", {}).get("keys", [])
    for k in bailian_keys:
        name = k.get("name", "?")
        parked = "YES" if k.get("parked") else "no"
        observed_pct = k.get("pct_7d")
        pct = (f"{observed_pct:.2f}%" if type(observed_pct) in (int, float)
               else "unknown")
        resets = str(k.get("resets_at") or "unknown")[:22]
        cd = k.get("cooldown", "—")
        print(f"  {name:<12} {parked:>8} {pct:>8} {resets:>22} {cd:>10}")
    print(f"─" * COLS)
    print_host_table()
    print(f"═" * COLS)
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    # The broker owns fleet-wide leases and this shared projection. Local PID
    # files are supporting legacy evidence, not the cluster's worker count.
    # Keep build_status() available to the broker without delegating recursively.
    try:
        from lease_broker import default_broker
        broker = default_broker()
        status = broker.write_status_json()
    except Exception as exc:
        print(
            f"pool_status: canonical broker unavailable ({type(exc).__name__}); "
            "no local-count fallback was published",
            file=sys.stderr,
        )
        return 1

    broker.print_status(status)
    print_host_table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
