#!/usr/bin/env python3
"""Provider quota readers with provenance, caching, and safe CLI output."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
# Resolve the fixed native-generation alias before atomic cache replacement.
CACHE_PATH = os.path.realpath(os.path.join(HERE, "quota_cache.json"))
BAILIAN_USAGE = os.path.join(HERE, "bailian_usage.json")
REFRESH_INTERVAL_S = 300
TIMEOUT_S = 10
FRESH_S = 600

GLM_URL = "https://api.z.ai/api/monitor/usage/quota/limit"
MINIMAX_URL = "https://www.minimax.io/v1/token_plan/remains"
ALIBABA_DETAIL = (
    "management reader UNAVAILABLE: no documented Alibaba Token Plan "
    "subscription-balance endpoint"
)


@dataclass
class ProviderQuotaState:
    provider: str
    window: str
    used: Optional[float]
    cap: Optional[float]
    remaining_pct: Optional[float]
    reset_at: Optional[str]
    source: str
    observed_at: str
    confidence: float
    detail: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds <= 0:
            return None
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        try:
            return _iso(datetime.fromtimestamp(seconds, tz=timezone.utc))
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text or text.lower() in ("none", "null", "unknown"):
        return None
    try:
        raw = text[:-1] + "+00:00" if text.endswith("Z") else text
        return _iso(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _state(
    provider: str,
    window: str,
    used: Optional[float],
    cap: Optional[float],
    remaining_pct: Optional[float],
    reset_at: Optional[str],
    source: str,
    observed_at: Any,
    confidence: float,
    detail: str,
) -> ProviderQuotaState:
    observed = _iso(observed_at)
    return ProviderQuotaState(
        provider=provider,
        window=window,
        used=used,
        cap=cap,
        remaining_pct=remaining_pct,
        reset_at=_iso(reset_at),
        source=source,
        observed_at=observed or _iso(_utc_now()) or "",
        confidence=max(0.0, min(1.0, confidence)),
        detail=detail,
    )


def parse_glm_payload(payload: Dict[str, Any], observed_at: Any) -> List[ProviderQuotaState]:
    """Parse Z.ai quota limits; numbers are normalized to percentage credits."""
    observed = observed_at or _utc_now()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    limits = data.get("limits") if isinstance(data, dict) else None
    if not isinstance(limits, list):
        return []
    classified: List[Tuple[str, Dict[str, Any]]] = []
    fallback: List[Dict[str, Any]] = []
    for item in limits:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").upper()
        unit = _num(item.get("unit"))
        if kind in ("TOKENS_LIMIT", "CREDIT_LIMIT"):
            if unit == 3:
                window = "5h"
            elif unit == 6:
                window = "weekly"
            else:
                window = ""
                fallback.append(item)
                continue
        elif kind == "TIME_LIMIT":
            window = "monthly"
        else:
            continue
        classified.append((window, item))
    for item in fallback:
        if not any(window == "5h" for window, _ in classified):
            classified.append(("5h", item))
        elif not any(window == "weekly" for window, _ in classified):
            classified.append(("weekly", item))
    out: List[ProviderQuotaState] = []
    for window, item in classified:
        pct = _num(item.get("percentage"))
        detail = "z.ai quota/limit"
        if window == "monthly":
            current = _num(item.get("currentValue"))
            cap = _num(item.get("usage"))
            used = current if current is not None else (
                cap * pct / 100.0 if cap is not None and pct is not None else None
            )
            out.append(_state(
                "glm", "mcp/monthly", used, cap,
                None if pct is None else 100.0 - pct,
                item.get("nextResetTime"), "PROVIDER_AUTHORITATIVE", observed,
                0.95 if pct is not None else 0.70, detail,
            ))
            continue
        out.append(_state(
            "glm", window, pct, 100.0,
            None if pct is None else 100.0 - pct,
            item.get("nextResetTime"), "PROVIDER_AUTHORITATIVE", observed,
            0.98 if pct is not None else 0.50, detail,
        ))
    return out


def parse_minimax_payload(payload: Dict[str, Any], observed_at: Any) -> List[ProviderQuotaState]:
    observed = observed_at or _utc_now()
    rows = payload.get("model_remains")
    if not isinstance(rows, list):
        return []
    row = next(
        (candidate for candidate in rows
         if isinstance(candidate, dict)
         and str(candidate.get("model_name") or "").lower() == "general"),
        None,
    )
    if row is None:
        return []
    out: List[ProviderQuotaState] = []
    fields = (
        ("5h", "current_interval_remaining_percent",
         "current_interval_usage_count", "current_interval_total_count", "end_time"),
        ("weekly", "current_weekly_remaining_percent",
         "current_weekly_usage_count", "current_weekly_total_count", "weekly_end_time"),
    )
    for window, remaining_key, used_key, cap_key, reset_key in fields:
        remaining_pct = _num(row.get(remaining_key))
        used = _num(row.get(used_key))
        cap = _num(row.get(cap_key))
        if remaining_pct is None:
            if used is not None and cap:
                remaining_pct = max(0.0, 100.0 * (cap - used) / cap)
            else:
                continue
        out.append(_state(
            "minimax", window, used, cap, remaining_pct, row.get(reset_key),
            "PROVIDER_AUTHORITATIVE", observed, 0.98,
            "minimax token_plan/remains general",
        ))
    return out


def _glm_key() -> Optional[str]:
    try:
        import glm_keys
        value = str(glm_keys.config().get("api_key") or "")
        return value or None
    except Exception:
        return None


def _glm_accounts_dict() -> Dict[str, Dict[str, str]]:
    """Read the multi-account table from glm_keys, tolerating any error.

    Returns an empty dict when the config file is missing or unreadable so
    callers can fall back to the legacy single-account path.
    """
    try:
        import glm_keys  # noqa: WPS433
        return glm_keys.accounts()
    except Exception:
        return {}


def _minimax_key() -> Optional[str]:
    path = os.environ.get("MINIMAX_CONFIG") or os.path.expanduser(
        "~/.minimax/config.json"
    )
    try:
        with open(path, encoding="utf-8") as handle:
            value = str(json.load(handle).get("api_key") or "")
        return value or None
    except Exception:
        return None


def _json_get(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        body = response.read(1_048_576)
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("non-object JSON response")
    return payload


def _live_glm(account_name: str, key: str) -> List[ProviderQuotaState]:
    """Per-account Z.ai quota read (W4-G9).

    ``account_name`` is informational (used in error messages); ``key`` is
    the api_key to authenticate with. The Bearer/raw header retry strategy
    is unchanged from the legacy single-account reader.
    """
    if not key:
        raise RuntimeError(
            f"glm key unavailable for account={account_name!r}"
        )
    attempts: Tuple[Tuple[str, str], ...] = (
        ("Authorization", "Bearer"),
        ("Authorization", "raw"),
    )
    errors: List[str] = []
    for header, mode in attempts:
        try:
            value = f"Bearer {key}" if mode == "Bearer" else key
            payload = _json_get(GLM_URL, {
                header: value,
                "Content-Type": "application/json",
                "Accept-Language": "en-US,en",
            })
            states = parse_glm_payload(payload, _utc_now())
            if states:
                return states
            errors.append("no quota windows")
        except Exception as exc:
            errors.append(type(exc).__name__)
    raise RuntimeError(
        f"glm read failed for account={account_name!r}: " + ",".join(errors)
    )


def _live_glm_no_args() -> List[ProviderQuotaState]:
    """Legacy no-arg wrapper used by the READERS dict for backwards compat.

    Resolves the legacy top-level api_key and delegates to the per-account
    reader under the synthetic account name ``"default"``.
    """
    key = _glm_key()
    if not key:
        raise RuntimeError("glm key unavailable")
    return _live_glm("default", key)


def _legacy_glm_mode() -> bool:
    """True when the legacy single-account interface is in effect.

    Tests that patch ``READERS["glm"]`` directly signal they want the
    legacy ``READERS["glm"]`` + top-level cache path. In production the
    no-arg ``_live_glm_no_args`` wrapper is the canonical entry point,
    so any other callable here is taken as a signal to fall back to the
    pre-W4-G9 contract.
    """
    return READERS.get("glm") is not _live_glm_no_args


def _live_minimax() -> List[ProviderQuotaState]:
    key = _minimax_key()
    if not key:
        raise RuntimeError("minimax key unavailable")
    payload = _json_get(MINIMAX_URL, {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    states = parse_minimax_payload(payload, _utc_now())
    if not states:
        raise RuntimeError("minimax read failed: no active windows")
    return states


READERS: Dict[str, Callable[[], List[ProviderQuotaState]]] = {
    "glm": _live_glm_no_args,
    "minimax": _live_minimax,
}


def local_bailian_states() -> List[ProviderQuotaState]:
    """Wrap ext/bailian_usage.json when present; no undocumented network reads."""
    path = getattr(__import__(__name__), "BAILIAN_USAGE", None) or os.path.join(
        HERE, "bailian_usage.json"
    )
    try:
        with open(path, encoding="utf-8") as handle:
            usage = json.load(handle)
        rows = usage.get("keys") if isinstance(usage, dict) else None
    except Exception:
        rows = None
    if not isinstance(rows, dict) or not rows:
        return []
    out: List[ProviderQuotaState] = []
    for name in sorted(rows):
        row = rows[name]
        if not isinstance(row, dict):
            continue
        pct = _num(row.get("pct_7d"))
        if pct is None:
            continue
        out.append(_state(
            "bailian", "7d", pct, 100.0, 100.0 - pct, row.get("resets_at"),
            "LOCAL_RECONSTRUCTION", row.get("observed_at") or row.get("updated_at"),
            0.65, f"local bailian_usage key={name}",
        ))
    return out


def _live_bailian() -> List[ProviderQuotaState]:
    raise RuntimeError(ALIBABA_DETAIL)


def _cache_age(entry: Dict[str, Any], now_ts: float) -> Optional[float]:
    observed = _iso(entry.get("observed_at"))
    if not observed:
        return None
    try:
        return max(0.0, now_ts - datetime.fromisoformat(
            observed[:-1] + "+00:00"
        ).timestamp())
    except (OSError, ValueError):
        return None


def _confidence_for_age(base: float, age_s: Optional[float]) -> float:
    if age_s is None:
        return 0.25
    days = age_s / 86400.0
    return max(0.0, min(base, base * 0.5 ** (days / 3.0)))


def _from_cache_entry(entry: Dict[str, Any], error: str,
                      keep_authoritative: bool = False) -> Optional[ProviderQuotaState]:
    if not isinstance(entry, dict):
        return None
    try:
        state = ProviderQuotaState(**entry)
    except TypeError:
        return None
    age = _cache_age(entry, _utc_now().timestamp())
    if keep_authoritative:
        state.confidence = max(0.25, float(state.confidence))
    else:
        state.source = "LOCAL_RECONSTRUCTION"
        state.confidence = _confidence_for_age(float(state.confidence), age)
        state.detail = "stale cache after remote read failure: " + error
    return state


def _cache_states(entry: Any, reason: str,
                  keep_authoritative: bool = False) -> List[ProviderQuotaState]:
    rows = entry.get("states") if isinstance(entry, dict) else None
    if not isinstance(rows, list):
        return []
    return [
        state for state in (
            _from_cache_entry(row, reason, keep_authoritative)
            for row in rows if isinstance(row, dict)
        ) if state is not None
    ]


def _load_cache(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(path or CACHE_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _atomic_write(path: str, value: Dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".quota_cache.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def read_provider(provider: str, force: bool = False,
                  now_ts: Optional[float] = None,
                  cache_path: Optional[str] = None) -> List[ProviderQuotaState]:
    provider = provider.lower()
    if provider not in {"glm", "minimax", "bailian"}:
        raise ValueError("unknown provider")
    path = cache_path or CACHE_PATH
    now = _utc_now().timestamp() if now_ts is None else float(now_ts)
    if provider == "glm":
        # W4-G9: multi-account aware. When the legacy single-account
        # interface is in effect (detected via a non-canonical
        # ``READERS["glm"]``), the cache lives at ``cache["glm"]`` top
        # level and ``READERS["glm"]`` does the live read. Otherwise,
        # round-trip through ``glm_accounts_state`` (caches per account
        # under ``glm.accounts.<name>``) and flatten the per-account
        # states to the legacy ``List[ProviderQuotaState]`` contract.
        if _legacy_glm_mode():
            cache = _load_cache(path)
            entry = cache.get("glm")
            refreshed_at = (
                float((entry or {}).get("refreshed_at") or 0)
                if isinstance(entry, dict) else 0.0
            )
            cached_states = _cache_states(entry, "cached", keep_authoritative=True)
            if (
                not force and refreshed_at
                and now - refreshed_at < REFRESH_INTERVAL_S
            ):
                return [state for state in cached_states if state is not None]
            try:
                live = READERS["glm"]()
                cache = _load_cache(path)
                cache["glm"] = {
                    "refreshed_at": int(now),
                    "states": [asdict(state) for state in live],
                }
                _atomic_write(path, cache)
                return live
            except Exception as exc:
                if isinstance(entry, dict) and isinstance(
                    entry.get("states"), list
                ):
                    stale = [
                        _from_cache_entry(row, type(exc).__name__)
                        for row in entry["states"]
                    ]
                    return [state for state in stale if state is not None]
                return []
        per_account = glm_accounts_state(
            now_ts=now, cache_path=path, force=force,
        )
        flat: List[ProviderQuotaState] = []
        for entry in per_account:
            flat.extend(entry.get("states") or [])
        return flat
    cache = _load_cache(path)
    entry = cache.get(provider)
    refreshed_at = float((entry or {}).get("refreshed_at") or 0) if isinstance(entry, dict) else 0.0
    cached_states = _cache_states(entry, "cached", keep_authoritative=True)
    if not force and refreshed_at and now - refreshed_at < REFRESH_INTERVAL_S:
        return [state for state in cached_states if state is not None]
    live: List[ProviderQuotaState]
    if provider == "bailian":
        try:
            _live_bailian()
            raise AssertionError("unreachable")
        except Exception as exc:
            locals_ = local_bailian_states()
            if locals_:
                return locals_
            return [_state(
                "bailian", "7d", None, None, None, None, "UNKNOWN", now,
                0.0, ALIBABA_DETAIL,
            )]
    try:
        live = READERS[provider]()
        cache[provider] = {
            "refreshed_at": int(now),
            "states": [asdict(state) for state in live],
        }
        _atomic_write(path, cache)
        return live
    except Exception as exc:
        if isinstance(entry, dict) and isinstance(entry.get("states"), list):
            stale = [
                _from_cache_entry(row, type(exc).__name__)
                for row in entry["states"]
            ]
            return [state for state in stale if state is not None]
        return []


def cached_glm_account_parked(account: str, *, now_ts: Optional[float] = None,
                              cache_path: Optional[str] = None) -> bool:
    """Narrow existing admission from a fresh authoritative account observation.

    No network, credential access, cache refresh or lease mutation. Unknown data
    preserves the incumbent decision; a passed reset never retains an old hold.
    Use the same 95-percent park threshold as glm_quota_decision, per account.
    """
    if not isinstance(account, str) or not account:
        return False
    now = _utc_now().timestamp() if now_ts is None else now_ts
    if type(now) not in (int, float) or not (0 < now < float("inf")):
        return False
    try:
        cache = _load_cache(cache_path or CACHE_PATH)
        entry = cache["glm"]["accounts"][account]
        refreshed = entry.get("refreshed_at")
        if (type(refreshed) not in (int, float)
                or not 0 <= now - refreshed <= FRESH_S):
            return False
        states = entry.get("states")
        if not isinstance(states, list):
            return False
        for state in states:
            if (not isinstance(state, dict) or state.get("provider") != "glm"
                    or state.get("source") != "PROVIDER_AUTHORITATIVE"
                    or state.get("window") not in ("5h", "weekly")):
                continue
            remaining = state.get("remaining_pct")
            if type(remaining) not in (int, float) or not 0 <= remaining <= 5:
                continue
            observed = _iso(state.get("observed_at"))
            if not observed:
                continue
            stamp = datetime.fromisoformat(observed.replace("Z", "+00:00")).timestamp()
            if not 0 <= now - stamp <= FRESH_S:
                continue
            reset = state.get("reset_at")
            if reset is not None:
                parsed_reset = _iso(reset)
                if not parsed_reset or datetime.fromisoformat(
                    parsed_reset.replace("Z", "+00:00")
                ).timestamp() <= now:
                    continue
            return True
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError):
        pass
    return False


def glm_accounts_state(
    now_ts: Optional[float] = None,
    cache_path: Optional[str] = None,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """Per-account GLM quota state (W4-G9).

    Returns one entry per account in ``glm_keys.accounts()``:

        {
            "name": str,
            "states": List[ProviderQuotaState],
            "source": str,
            "observed_at": Optional[str],
            "error": Optional[str],
        }

    Reads from ``cache["glm"]["accounts"][<name>]`` when fresh; otherwise
    falls back to ``_live_glm(name, key)`` and writes the result back.
    Stale-cache entries are preserved on live-read failure.
    """
    now = _utc_now().timestamp() if now_ts is None else float(now_ts)
    path = cache_path or CACHE_PATH
    cache = _load_cache(path)
    glm_entry = cache.get("glm")
    if not isinstance(glm_entry, dict):
        glm_entry = {}
    accounts_block = glm_entry.get("accounts")
    if not isinstance(accounts_block, dict):
        accounts_block = {}
    new_accounts_block = dict(accounts_block)

    accounts = _glm_accounts_dict()
    out: List[Dict[str, Any]] = []
    changed = False

    for name, info in accounts.items():
        key = ""
        if isinstance(info, dict):
            key = str(info.get("api_key") or "")
        cached = new_accounts_block.get(name)
        cached_refresh = (
            float(cached.get("refreshed_at") or 0)
            if isinstance(cached, dict) else 0.0
        )
        cached_age = now - cached_refresh if cached_refresh else None

        states: List[ProviderQuotaState] = []
        source = "UNKNOWN"
        observed_at: Optional[str] = None
        error: Optional[str] = None

        fresh_cache = (
            not force
            and isinstance(cached, dict)
            and cached_age is not None
            and cached_age < REFRESH_INTERVAL_S
            and isinstance(cached.get("states"), list)
        )
        if fresh_cache:
            cached_states = _cache_states(cached, "cached", keep_authoritative=True)
            states = list(cached_states)
            if states:
                source = states[0].source
                observed_at = states[0].observed_at

        if not states:
            try:
                states = _live_glm(name, key)
                source = "PROVIDER_AUTHORITATIVE"
                observed_at = states[0].observed_at if states else None
                new_accounts_block[name] = {
                    "refreshed_at": int(now),
                    "states": [asdict(state) for state in states],
                }
                changed = True
            except Exception as exc:
                error = type(exc).__name__
                # Stale-cache fallback: keep the previous authoritative
                # reading, demoted to LOCAL_RECONSTRUCTION.
                if isinstance(cached, dict) and isinstance(
                    cached.get("states"), list
                ):
                    stale = [
                        s for s in (
                            _from_cache_entry(row, error)
                            for row in cached["states"]
                            if isinstance(row, dict)
                        ) if s is not None
                    ]
                    if stale:
                        states = stale
                        source = stale[0].source
                        observed_at = stale[0].observed_at

        out.append({
            "name": name,
            "states": states,
            "source": source,
            "observed_at": observed_at,
            "error": error,
        })

    if changed:
        glm_entry["accounts"] = new_accounts_block
        cache["glm"] = glm_entry
        try:
            _atomic_write(path, cache)
        except Exception:
            pass
    return out


def fresh_authoritative(provider: str, window: str,
                        now_ts: Optional[float] = None,
                        cache_path: Optional[str] = None) -> Optional[ProviderQuotaState]:
    now = _utc_now().timestamp() if now_ts is None else float(now_ts)
    for state in read_provider(provider, now_ts=now, cache_path=cache_path):
        if state.window != window:
            continue
        observed = _iso(state.observed_at)
        try:
            age = now - datetime.fromisoformat(
                observed[:-1] + "+00:00"
            ).timestamp() if observed else None
        except (OSError, ValueError):
            age = None
        if state.source == "PROVIDER_AUTHORITATIVE" and age is not None and age <= FRESH_S:
            return state
    return None


def glm_quota_decision(now_ts: Optional[float] = None,
                       local_estimate: Optional[Dict[str, Any]] = None,
                       cache_path: Optional[str] = None,
                       fallback_reader: Optional[Callable[[Optional[float]], Dict[str, Any]]] = None,
                       read_remote: bool = True) -> Dict[str, Any]:
    """R29 GLM quota decision (W4-G9 multi-account).

    State rules:
      * ``PARKED`` when EVERY account's weekly pct >= 95 % (or every 5h pct
        >= 95 %).
      * ``SPILL`` only when EVERY account's 5h pct >= 90 % (no single account
        has spare capacity).
      * ``OK`` otherwise (at least one account has headroom).

    Returns the BEST account's quota fields at the top level (so callers
    like ``pool_ledger.glm_burn`` keep working) plus a per-account
    breakdown under ``accounts`` (ordered list, one entry per configured
    account).
    """
    now = _utc_now().timestamp() if now_ts is None else float(now_ts)
    per_account: List[Dict[str, Any]] = []
    if read_remote:
        if _legacy_glm_mode():
            # Legacy single-account path: ``READERS["glm"]`` is the no-arg
            # reader and the cache lives at ``cache["glm"]["refreshed_at"]``.
            # Synthesize a single ``"default"`` entry so the same breakdown
            # logic drives both code paths.
            flat = read_provider(
                "glm", now_ts=now, cache_path=cache_path,
            )
            if flat:
                per_account = [{
                    "name": "default",
                    "states": flat,
                    "source": flat[0].source,
                    "observed_at": flat[0].observed_at,
                    "error": None,
                }]
        else:
            # W4-G9 multi-account path.
            per_account = glm_accounts_state(now_ts=now, cache_path=cache_path)

    if not per_account or all(not entry.get("states") for entry in per_account):
        if local_estimate is None and fallback_reader is not None:
            try:
                local_estimate = fallback_reader(now)
            except Exception:
                local_estimate = None
        if not isinstance(local_estimate, dict):
            return {
                "state": "UNKNOWN", "source": "UNKNOWN", "observed_at": None,
                "pct_5h": None, "pct_week": None,
                "detail": "quota unavailable after remote and local reads",
                "accounts": [],
            }
        estimate = dict(local_estimate)
        estimate["source"] = "LOCAL_RECONSTRUCTION"
        estimate["observed_at"] = estimate.get("observed_at") or _iso(now)
        estimate.setdefault("state", "OK")
        estimate.setdefault("detail", "W4-G7 calibrated local reconstruction")
        estimate["confidence"] = min(0.80, float(estimate.get("confidence", 0.70)))
        estimate.setdefault("accounts", [])
        return estimate

    breakdown: List[Dict[str, Any]] = []
    best_idx = -1
    best_score: Optional[Tuple[float, float, int]] = None
    for idx, entry in enumerate(per_account):
        states = entry.get("states") or []
        s_5h = next((s for s in states if s.window == "5h"), None)
        s_wk = next((s for s in states if s.window == "weekly"), None)
        pct_5h = (
            None if s_5h is None or s_5h.remaining_pct is None
            else 100.0 - s_5h.remaining_pct
        )
        pct_week = (
            None if s_wk is None or s_wk.remaining_pct is None
            else 100.0 - s_wk.remaining_pct
        )
        breakdown.append({
            "name": entry["name"],
            "pct_5h": pct_5h,
            "pct_week": pct_week,
            "remaining_pct_5h": s_5h.remaining_pct if s_5h else None,
            "remaining_pct_week": s_wk.remaining_pct if s_wk else None,
            "used_5h": s_5h.used if s_5h else None,
            "cap_5h": s_5h.cap if s_5h else None,
            "reset_at_5h": s_5h.reset_at if s_5h else None,
            "used_week": s_wk.used if s_wk else None,
            "cap_week": s_wk.cap if s_wk else None,
            "reset_at_week": s_wk.reset_at if s_wk else None,
            "source": entry["source"],
            "observed_at": entry["observed_at"],
            "error": entry.get("error"),
        })
        score = (
            pct_5h if pct_5h is not None else float("inf"),
            pct_week if pct_week is not None else float("inf"),
            idx,
        )
        if best_score is None or score < best_score:
            best_score = score
            best_idx = idx

    if best_idx < 0:
        return {
            "state": "UNKNOWN", "source": "UNKNOWN", "observed_at": None,
            "pct_5h": None, "pct_week": None,
            "detail": "no per-account state available",
            "accounts": breakdown,
        }

    pct_5h_values = [b["pct_5h"] for b in breakdown if b["pct_5h"] is not None]
    pct_week_values = [b["pct_week"] for b in breakdown if b["pct_week"] is not None]
    all_5h_at_or_above_95 = bool(pct_5h_values) and all(
        p >= 95.0 for p in pct_5h_values
    )
    all_5h_at_or_above_90 = bool(pct_5h_values) and all(
        p >= 90.0 for p in pct_5h_values
    )
    all_week_at_or_above_95 = bool(pct_week_values) and all(
        p >= 95.0 for p in pct_week_values
    )
    if all_5h_at_or_above_95 or all_week_at_or_above_95:
        state = "PARKED"
    elif all_5h_at_or_above_90:
        state = "SPILL"
    else:
        state = "OK"

    best = breakdown[best_idx]
    observed = best.get("observed_at") or ""
    confidence = min(
        best["remaining_pct_5h"] if best["remaining_pct_5h"] is not None else 1.0,
        best["remaining_pct_week"] if best["remaining_pct_week"] is not None else 1.0,
    )
    return {
        "state": state,
        "source": best["source"],
        "observed_at": observed or None,
        "pct_5h": best["pct_5h"],
        "pct_week": best["pct_week"],
        "remaining_pct_5h": best["remaining_pct_5h"],
        "remaining_pct_week": best["remaining_pct_week"],
        "used_5h": best["used_5h"],
        "cap_5h": best["cap_5h"],
        "reset_at_5h": best["reset_at_5h"],
        "used_week": best["used_week"],
        "cap_week": best["cap_week"],
        "reset_at_week": best["reset_at_week"],
        "confidence": confidence,
        "detail": "z.ai quota/limit",
        "accounts": breakdown,
        "best_account": best["name"],
    }


def _age_seconds(state: ProviderQuotaState, now_ts: float) -> float:
    observed = _iso(state.observed_at)
    try:
        return abs(now_ts - datetime.fromisoformat(
            observed[:-1] + "+00:00"
        ).timestamp()) if observed else float("inf")
    except (OSError, ValueError):
        return float("inf")


def _public(state: ProviderQuotaState) -> Dict[str, Any]:
    value = asdict(state)
    return {key: item for key, item in value.items() if key != "detail"}


def _print(states: Iterable[ProviderQuotaState], as_json: bool) -> None:
    rows = [_public(state) for state in states]
    if as_json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return
    for row in rows:
        used = "UNKNOWN" if row["used"] is None else f"{row['used']:.2f}"
        cap = "UNKNOWN" if row["cap"] is None else f"{row['cap']:.2f}"
        remaining = "UNKNOWN" if row["remaining_pct"] is None else f"{row['remaining_pct']:.2f}"
        confidence = f"{row['confidence']:.3f}"
        print(
            f"provider={row['provider']} window={row['window']} "
            f"used={used} cap={cap} remaining_pct={remaining} "
            f"reset_at={row['reset_at'] or 'unknown'} source={row['source']} "
            f"observed_at={row['observed_at']} confidence={confidence}"
        )


def _print_glm_accounts(
    per_account: List[Dict[str, Any]],
    as_json: bool,
) -> None:
    """W4-G9 per-account rendering for ``show --provider glm``.

    Each account is one line with name, pct_5h, pct_week, reset_at, source —
    no api_key material, ever.
    """
    if as_json:
        rows = []
        for entry in per_account:
            states = entry.get("states") or []
            s_5h = next((s for s in states if s.window == "5h"), None)
            s_wk = next((s for s in states if s.window == "weekly"), None)
            rows.append({
                "name": entry["name"],
                "pct_5h": s_5h.used if s_5h else None,
                "pct_week": s_wk.used if s_wk else None,
                "reset_at": s_5h.reset_at if s_5h else None,
                "source": entry["source"],
                "observed_at": entry["observed_at"],
            })
        print(json.dumps(rows, indent=2, sort_keys=True))
        return
    for entry in per_account:
        states = entry.get("states") or []
        s_5h = next((s for s in states if s.window == "5h"), None)
        s_wk = next((s for s in states if s.window == "weekly"), None)
        pct_5h = "UNKNOWN" if s_5h is None or s_5h.used is None else f"{s_5h.used:.2f}"
        pct_week = (
            "UNKNOWN" if s_wk is None or s_wk.used is None
            else f"{s_wk.used:.2f}"
        )
        reset = s_5h.reset_at if s_5h and s_5h.reset_at else "unknown"
        print(
            f"account={entry['name']} pct_5h={pct_5h} pct_week={pct_week} "
            f"reset_at={reset} source={entry['source']} "
            f"observed_at={entry['observed_at'] or '-'}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("--provider", choices=("glm", "minimax", "bailian"))
    show.add_argument("--force", action="store_true")
    show.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    providers = (args.provider,) if args.provider else ("glm", "minimax", "bailian")
    now_ts = _utc_now().timestamp()
    for provider in providers:
        if provider == "glm":
            per_account = glm_accounts_state(
                now_ts=now_ts, force=args.force,
            )
            _print_glm_accounts(per_account, args.json)
            continue
        states = read_provider(provider, force=args.force)
        _print(states, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
