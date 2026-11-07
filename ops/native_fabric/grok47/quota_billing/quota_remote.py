#!/usr/bin/env python3
"""Provider quota readers with provenance, caching, and safe CLI output."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import math
import selectors
import shutil
import signal
import subprocess
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
# Resolve the fixed native-generation alias before atomic cache replacement.
CACHE_PATH = os.path.realpath(os.path.join(HERE, "quota_cache.json"))
BAILIAN_USAGE = os.path.join(HERE, "bailian_usage.json")
REFRESH_INTERVAL_S = 300
TIMEOUT_S = 10
FRESH_S = 600
CACHE_LOCK_WAIT_S = 1.0

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
    # Optional v1-compatible provenance. These identify the original owner;
    # they are not credentials, provider account attestation or admission.
    account: Optional[str] = None
    config_generation: Optional[str] = None
    account_generation: Optional[str] = None
    allowance_scope: Optional[str] = None
    endpoint: Optional[str] = None
    units: str = "provider_percent"
    refresh_error: Optional[str] = None
    failure_config_generation: Optional[str] = None


class ProviderQuotaRefusal(RuntimeError):
    """Terminal account observation refusal, reconciled by the existing owner."""


class QuotaCacheWriteError(RuntimeError):
    """Original cache persistence failed; the owner must reconcile before retry."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if type(value) in (int, float):
        seconds = _num(value)
        if seconds is None or seconds <= 0:
            return None
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        try:
            return _iso(datetime.fromtimestamp(seconds, tz=timezone.utc))
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
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
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _public_endpoint(value: Any) -> Optional[str]:
    if not isinstance(value, str) or len(value) > 512:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or any(ord(c) < 33 for c in value)):
            return None
        return value.rstrip("/")
    except ValueError:
        return None


def _config_binding(provider: str) -> Optional[Dict[str, Any]]:
    """Fence the existing credential owner's file revision without hashing a key.

    This is a local configuration generation, NOT a provider account identity.
    Only file metadata and public endpoint fields enter the digest. A key change
    or atomic file replacement invalidates previous observations. Nothing here
    writes configuration or creates another credential/entitlement store.
    """
    if provider not in ("glm", "minimax"):
        return None
    path = os.environ.get(provider.upper() + "_CONFIG") or os.path.expanduser(
        "~/." + provider + "/config.json")
    try:
        before = os.stat(path)
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        after = os.stat(path)
        def identity(st):
            return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if not isinstance(raw, dict) or identity(before) != identity(after):
            return None
        endpoint = _public_endpoint(raw.get("openai_base_url"))
        # Default endpoints are not inferred from a key or a plan label.
        public = {"stat": identity(after), "endpoint": endpoint,
                  "anthropic_endpoint": _public_endpoint(raw.get("anthropic_base_url"))}
        digest = hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()
        return {"config_generation": "config-" + digest, "endpoint": endpoint}
    except (OSError, ValueError, TypeError):
        return None


def _bind_states(states: Iterable[ProviderQuotaState], account: str,
                 binding: Optional[Dict[str, Any]]) -> List[ProviderQuotaState]:
    return [replace(state, account=account,
                    config_generation=(binding or {}).get("config_generation"),
                    endpoint=(binding or {}).get("endpoint")) for state in states]


def _binding_generation(binding: Any) -> Optional[str]:
    value = binding.get("config_generation") if isinstance(binding, dict) else None
    return value if isinstance(value, str) and value else None


def _has_pending(entry: Any) -> bool:
    return isinstance(entry, dict) and "refresh_pending" in entry


def _pending_matches(pending: Any, attempt_id: Any, provider: str,
                     account: Optional[str], binding: Any, started_at: float) -> bool:
    return (isinstance(pending, dict) and isinstance(attempt_id, str) and bool(attempt_id)
            and pending.get("attempt_id") == attempt_id and pending.get("provider") == provider
            and pending.get("account") == account and pending.get("binding") == binding
            and pending.get("started_at") == started_at)


def _cache_fresh(entry: Any, now: float, binding: Any = None) -> bool:
    if not isinstance(entry, dict) or not isinstance(entry.get("states"), list):
        return False
    if entry.get("refresh_error") or entry.get("terminal_refusal") or _has_pending(entry):
        return False
    stamp = _num(entry.get("refreshed_at"))
    if stamp is None or not 0 <= now - stamp < REFRESH_INTERVAL_S:
        return False
    if binding is not None and entry.get("binding") != binding:
        return False
    for row in entry["states"]:
        if not isinstance(row, dict):
            return False
        age = _cache_age(row, now)
        reset = _iso(row.get("reset_at"))
        if age is None or age > FRESH_S:
            return False
        if row.get("reset_at") is not None and reset is None:
            return False
        if reset and datetime.fromisoformat(reset.replace("Z", "+00:00")).timestamp() <= now:
            return False
    return bool(entry["states"])


def parse_go_usage_payload(payload: Any, observed_at: Any, *, account: str,
                           config_generation: Optional[str] = None,
                           endpoint: Optional[str] = None) -> List[ProviderQuotaState]:
    """Normalize the incumbent Go /usage response; do not poll or cache it.

    The Go owner supplies its *original* successful-refresh clock and binding.
    Legacy /status without that clock is unknown, even when read right now.
    Each percentage belongs to its own shared account window, never a model
    wallet. Model-equivalent dollar allowances are not balance observations.
    """
    usage = payload.get("usage") if isinstance(payload, dict) else None
    out = []
    for native, window in (("rolling", "5h"), ("weekly", "weekly"), ("monthly", "monthly")):
        row = usage.get(native) if isinstance(usage, dict) else None
        pct = _num(row.get("percent")) if isinstance(row, dict) else None
        valid = (isinstance(row, dict) and row.get("status") == "ok"
                 and pct is not None and 0 <= pct <= 100)
        reset = row.get("resetsAt") if isinstance(row, dict) else None
        if reset is not None and _iso(reset) is None:
            valid = False
        state = _state("go", window, pct if valid else None, 100.0 if valid else None,
                       100.0 - pct if valid else None, reset,
                       "PROVIDER_AUTHORITATIVE" if valid else "UNKNOWN", observed_at,
                       0.98 if valid else 0.0, "OpenCode Go /usage" if valid else "Go window unavailable")
        out.append(replace(state, account=account, config_generation=config_generation,
                           endpoint=_public_endpoint(endpoint)))
    return out


def parse_go_response_allowance(payload: Any, observed_at: Any, *, account: str) -> ProviderQuotaState:
    """Normalize one complete API response or its usage block, never a balance.

    Chat/Responses/Messages use usage; Gemini uses usageMetadata. Missing final
    usage or price is unknown, even when a different response reports cost=0.
    """
    usage = payload
    if isinstance(payload, dict):
        containers = [payload[key] for key in ("usage", "usageMetadata") if key in payload]
        if containers:
            usage = containers[0] if len(containers) == 1 else None
    opencode = usage.get("opencode") if isinstance(usage, dict) else None
    debit = _num(opencode.get("allowance")) if isinstance(opencode, dict) else None
    if debit is not None and debit < 0:
        debit = None
    state = _state("go", "request", debit, None, None, None,
                   "PROVIDER_RESPONSE_USAGE" if debit is not None else "UNKNOWN",
                   observed_at, 0.98 if debit is not None else 0.0, "response debit; not a balance")
    return replace(state, account=account, units="monthly_allowance_usd")


def account_quota_view(provider: str, account: str, states: Iterable[ProviderQuotaState], *,
                       config_generation: Optional[str], endpoint: Optional[str],
                       allowance_scope: Optional[str] = None,
                       account_generation: Optional[str] = None,
                       required_windows: Optional[Iterable[str]] = None,
                       now_ts: Optional[float] = None,
                       refresh_error: Optional[str] = None,
                       failure_config_generation: Optional[str] = None) -> Dict[str, Any]:
    """Secret-free read projection for H3/H4/H5 over existing owner observations.

    A true quota_ready means only current allowance evidence. The existing
    entitlement, budget, no-overage, lease and provider refusal gates still decide
    whether an actual model/workload may run. This helper owns no admission.
    """
    now = _utc_now().timestamp() if now_ts is None else _num(now_ts)
    if now is None or now <= 0:
        raise ValueError("invalid observation time")
    defaults = {"glm": ("5h", "weekly"), "minimax": ("5h", "weekly"),
                "go": ("5h", "weekly", "monthly")}
    required = tuple(required_windows if required_windows is not None else defaults.get(provider, ()))
    if not required or len(required) != len(set(required)):
        raise ValueError("applicable quota windows required")
    if not set(defaults.get(provider, ())).issubset(required):
        raise ValueError("provider windows cannot be omitted")
    rows = [state for state in states if isinstance(state, ProviderQuotaState)]
    own_rows = [s for s in rows if s.provider == provider and s.account == account]
    failures = {s.refresh_error for s in own_rows if s.refresh_error}
    if refresh_error is None and failures:
        refresh_error = next(iter(failures)) if len(failures) == 1 else "WINDOW_REFRESH_FAILED"
    generations = {s.failure_config_generation for s in own_rows if s.failure_config_generation}
    if failure_config_generation is None and len(generations) == 1:
        failure_config_generation = next(iter(generations))
    windows = []
    binding_endpoint = _public_endpoint(endpoint)
    for window in required:
        candidates = [s for s in rows if s.provider == provider and s.account == account and s.window == window]
        reason = None
        state = candidates[0] if len(candidates) == 1 else None
        age = _cache_age(asdict(state), now) if state else None
        reset = _iso(state.reset_at) if state else None
        reset_ts = datetime.fromisoformat(reset.replace("Z", "+00:00")).timestamp() if reset else None
        pct = _num(state.remaining_pct) if state else None
        confidence = _num(state.confidence) if state else None
        if refresh_error or state is not None and state.refresh_error:
            reason = "REFRESH_FAILED"
        elif state is None:
            reason = "WINDOW_MISSING" if not candidates else "WINDOW_AMBIGUOUS"
        elif not config_generation or state.config_generation != config_generation:
            reason = "CONFIG_GENERATION_UNQUALIFIED"
        elif not binding_endpoint or state.endpoint != binding_endpoint:
            reason = "ENDPOINT_UNQUALIFIED"
        elif account_generation is not None and state.account_generation != account_generation:
            reason = "ACCOUNT_GENERATION_CHANGED"
        elif allowance_scope is not None and state.allowance_scope != allowance_scope:
            reason = "ALLOWANCE_SCOPE_CHANGED"
        elif state.source != "PROVIDER_AUTHORITATIVE":
            reason = "NON_AUTHORITATIVE"
        elif confidence is None or not 0 < confidence <= 1:
            reason = "CONFIDENCE_INVALID"
        elif age is None or age > FRESH_S:
            reason = "OBSERVATION_STALE_OR_INVALID"
        elif state.reset_at is not None and reset is None:
            reason = "RESET_INVALID"
        elif reset_ts is not None and reset_ts <= now:
            reason = "RESET_REQUIRES_OBSERVATION"
        elif pct is None or not 0 <= pct <= 100:
            reason = "BALANCE_UNKNOWN"
        elif pct == 0:
            reason = "EXHAUSTED"
        windows.append({"window": window, "remaining_pct": pct, "reset_at": reset,
                        "observed_at": _iso(state.observed_at) if state else None,
                        "source": state.source if state else "UNKNOWN", "age_s": age,
                        "confidence": confidence if confidence is not None else 0.0,
                        "units": state.units if state else "provider_percent",
                        "reset_state": "UNKNOWN" if reset is None else "DUE" if reset_ts <= now else "FUTURE",
                        "ready": reason is None, "reason": reason})
    return {"provider": provider, "account": account, "allowance_scope": allowance_scope,
            "account_generation": account_generation, "config_generation": config_generation,
            "endpoint": binding_endpoint, "windows": windows,
            "refresh_error": refresh_error,
            "failure_config_generation": failure_config_generation,
            "quota_ready": all(row["ready"] for row in windows),
            "entitlement": "NOT_EVALUATED", "no_overage": "NOT_EVALUATED",
            "admission": "NOT_EVALUATED"}


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
    reset = _iso(reset_at)
    if source == "PROVIDER_AUTHORITATIVE" and reset_at is not None and reset is None:
        source, remaining_pct, confidence = "UNKNOWN", None, 0.0
    return ProviderQuotaState(
        provider=provider,
        window=window,
        used=used,
        cap=cap,
        remaining_pct=remaining_pct,
        reset_at=reset,
        source=source,
        # An absent/invalid producer clock must never acquire read-time freshness.
        observed_at=observed or "",
        confidence=max(0.0, min(1.0, _num(confidence) or 0.0)),
        detail=detail,
    )


def parse_glm_payload(payload: Dict[str, Any], observed_at: Any) -> List[ProviderQuotaState]:
    """Parse Z.ai quota limits; numbers are normalized to percentage credits."""
    observed = observed_at
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    limits = data.get("limits") if isinstance(data, dict) else None
    if not isinstance(limits, list):
        return []
    classified: List[Tuple[str, Dict[str, Any]]] = []
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
                # Array order is not evidence of a 5h or weekly window.
                continue
        elif kind == "TIME_LIMIT":
            window = "monthly"
        else:
            continue
        classified.append((window, item))
    out: List[ProviderQuotaState] = []
    for window, item in classified:
        pct = _num(item.get("percentage"))
        if pct is not None and not 0 <= pct <= 100:
            pct = None
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
    observed = observed_at
    if not isinstance(payload, dict):
        return []
    rows = payload.get("model_remains")
    if not isinstance(rows, list):
        return []
    general = [candidate for candidate in rows
         if isinstance(candidate, dict)
         and str(candidate.get("model_name") or "").lower() == "general"]
    if len(general) != 1:
        return []
    row = general[0]
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
        counts_valid = cap is not None and cap > 0 and used is not None and 0 <= used <= cap
        if remaining_key not in row and counts_valid:
            remaining_pct = 100.0 * (cap - used) / cap
        if remaining_pct is not None and not 0 <= remaining_pct <= 100:
            remaining_pct = None
        state = _state(
            "minimax", window, used, cap, remaining_pct, row.get(reset_key),
            "PROVIDER_AUTHORITATIVE" if remaining_pct is not None else "UNKNOWN",
            observed, 0.98 if remaining_pct is not None else 0.0,
            "minimax token_plan/remains general",
        )
        out.append(replace(state, units="provider_usage_count"))
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
    the api_key to authenticate with. A terminal authentication/permission
    refusal ends the observation: do not retry it with another header shape.
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
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code in (401, 403):
                raise ProviderQuotaRefusal("provider refused quota observation") from None
            errors.append(type(exc).__name__)
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


def parse_grok_billing_payload(
    payload: Dict[str, Any], observed_at: Any,
) -> List[ProviderQuotaState]:
    """First-party ACP weekly evidence; absent usage percent is UNKNOWN."""
    if not isinstance(payload, dict):
        return []
    config = payload.get("config")
    if not isinstance(config, dict):
        return []
    period = config.get("currentPeriod")
    if not isinstance(period, dict) or period.get("type") != "USAGE_PERIOD_TYPE_WEEKLY":
        return []
    # Never reinterpret a provider timestamp lacking a timezone in the
    # local host timezone. That would move the reset and model a false window.
    raw_start, raw_end = period.get("start"), period.get("end")
    if type(raw_start) is not str or type(raw_end) is not str:
        return []
    try:
        if (datetime.fromisoformat(raw_start.replace("Z", "+00:00")).utcoffset() is None
                or datetime.fromisoformat(raw_end.replace("Z", "+00:00")).utcoffset() is None):
            return []
    except ValueError:
        return []
    start = _iso(raw_start)
    end = _iso(raw_end)
    observed = _iso(observed_at)
    if not all((start, end, observed)):
        return []
    try:
        def seconds(v: str) -> float:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        start_s, end_s, obs_s = map(seconds, (start, end, observed))
    except (ValueError, OverflowError):
        return []
    if not (4 * 86400 <= end_s - start_s <= 12 * 86400
            and start_s <= obs_s < end_s):
        return []
    pct = config.get("creditUsagePercent")
    if type(pct) in (int, float) and math.isfinite(pct) and 0 <= pct <= 100:
        used, remaining, cap = float(pct), 100.0 - float(pct), 100.0
    else:
        used = remaining = cap = None
    return [_state(
        "grok", "weekly", used, cap, remaining, end,
        "GROK_BUILD_ACP_BILLING" if remaining is not None
        else "GROK_BUILD_ACP_WINDOW_ONLY",
        observed, 0.95 if remaining is not None else 0.0,
        "authenticated billing; unified="
        + str(config.get("isUnifiedBillingUser") is True)
        + "; period_start=" + start
        + ("; quota UNKNOWN" if remaining is None else ""),
    )]


def _live_grok() -> List[ProviderQuotaState]:
    """Read _x.ai/billing without session/new, prompt or paid model turn."""
    path = shutil.which("grok")
    if not path:
        raise RuntimeError("grok_acp_missing")
    proc = None
    poller = None
    try:
        proc = subprocess.Popen(
            [path, "agent", "stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, start_new_session=True,
        )
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("grok_acp_missing_stream")
        poller = selectors.DefaultSelector()
        poller.register(proc.stdout, selectors.EVENT_READ)
        pending = b""

        def rpc(method: str, rid: int, timeout: float, params: dict) -> dict:
            nonlocal pending
            proc.stdin.write((json.dumps({
                "jsonrpc": "2.0", "id": rid, "method": method,
                "params": params,
            }, separators=(",", ":")) + "\n").encode())
            proc.stdin.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError("grok_acp_exited")
                for _key, _events in poller.select(
                        min(.5, max(0., deadline - time.monotonic()))):
                    data = os.read(proc.stdout.fileno(), 65536)
                    if not data:
                        raise RuntimeError("grok_acp_closed")
                    pending += data
                    if len(pending) > 1024 * 1024:
                        raise RuntimeError("grok_acp_oversize")
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        try:
                            result = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if not isinstance(result, dict) or result.get("id") != rid:
                            continue
                        if "error" in result or not isinstance(result.get("result"), dict):
                            raise RuntimeError("grok_acp_refused")
                        return result["result"]
            raise RuntimeError("grok_acp_timeout")

        rpc("initialize", 1, 12., {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
        })
        # Verified on installed M2 Grok CLI 2026-10-22: x.ai/billing
        # returned method-not-found (-32601), _x.ai/billing succeeded.
        return parse_grok_billing_payload(
            rpc("_x.ai/billing", 2, 20., {}), _utc_now(),
        )
    finally:
        if poller is not None:
            poller.close()
        if proc is not None:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    # SIGKILL is only process termination; reap its child to
                    # avoid a zombie while this long-lived broker host runs.
                    proc.wait(timeout=3)
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass


READERS: Dict[str, Callable[[], List[ProviderQuotaState]]] = {
    "glm": _live_glm_no_args,
    "minimax": _live_minimax,
    "grok": _live_grok,
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
        age = now_ts - datetime.fromisoformat(
            observed[:-1] + "+00:00"
        ).timestamp()
        return age if math.isfinite(age) and age >= 0 else None
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
    confidence = _num(state.confidence)
    if confidence is None or not 0 <= confidence <= 1:
        return None
    state.used, state.cap = _num(state.used), _num(state.cap)
    state.remaining_pct = _num(state.remaining_pct)
    if state.remaining_pct is not None and not 0 <= state.remaining_pct <= 100:
        state.remaining_pct = None
    if keep_authoritative and age is not None and age <= FRESH_S:
        state.confidence = confidence
    else:
        state.source = "LOCAL_RECONSTRUCTION"
        state.confidence = _confidence_for_age(confidence, age)
        state.detail = "stale cache after remote read failure: " + error
    return state


def _cache_states(entry: Any, reason: str,
                  keep_authoritative: bool = False) -> List[ProviderQuotaState]:
    rows = entry.get("states") if isinstance(entry, dict) else None
    if not isinstance(rows, list):
        return []
    failure = entry.get("refresh_error") or ("REFRESH_IN_PROGRESS" if _has_pending(entry) else None)
    states = [
        state for state in (
            _from_cache_entry(row, reason, keep_authoritative and not failure)
            for row in rows if isinstance(row, dict)
        ) if state is not None
    ]
    failure_generation = _binding_generation(entry.get("failure_binding"))
    return [replace(state, refresh_error=failure,
                    failure_config_generation=failure_generation) for state in states]


def _record_refresh_failure(cache_path: str, provider: str, account: Optional[str],
                            entry: Any, binding: Any, now: float, exc: Exception,
                            *, attempt_id: Optional[str] = None) -> str:
    """Retain failure alongside the original cache, never in a second ledger."""
    terminal = (isinstance(exc, ProviderQuotaRefusal)
                or isinstance(exc, urllib.error.HTTPError) and exc.code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN))
    if isinstance(exc, urllib.error.HTTPError):
        exc.close()
    code = "PROVIDER_REFUSED" if terminal else "REMOTE_READ_FAILED"
    def update(cache):
        container, key = _cache_target(cache, provider, account)
        current = container.get(key)
        if isinstance(current, dict) and current.get("terminal_refusal"):
            return False, current
        pending = current.get("refresh_pending") if isinstance(current, dict) else None
        if _has_pending(current) and not _pending_matches(pending, attempt_id, provider, account, binding, now):
            return False, current
        # An older read cannot erase a later observation/failure. A permission
        # refusal is retained even when a concurrent read happened to succeed.
        if not terminal and _attempt_at(current) > now:
            return False, current
        row = dict(current) if isinstance(current, dict) else {"states": [], "binding": binding}
        row.pop("refresh_pending", None)
        row.update(refresh_error=code, refresh_failed_at=now, failure_binding=binding,
                   terminal_refusal=bool(terminal or row.get("terminal_refusal")))
        container[key] = row
        return True, row
    _update_cache(cache_path, update)
    return code


def _attempt_at(entry: Any) -> float:
    if not isinstance(entry, dict):
        return float("-inf")
    stamps = [_num(entry.get(k)) for k in
              ("refresh_started_at", "refreshed_at", "refresh_failed_at")]
    return max((s for s in stamps if s is not None), default=float("-inf"))


def _cache_target(cache: Dict[str, Any], provider: str,
                  account: Optional[str]) -> Tuple[Dict[str, Any], str]:
    if account is None:
        return cache, provider
    if not isinstance(cache.get(provider), dict):
        cache[provider] = {}
    if not isinstance(cache[provider].get("accounts"), dict):
        cache[provider]["accounts"] = {}
    return cache[provider]["accounts"], account


def _update_cache(path: str, update: Callable) -> Any:
    """Serialize only publication in the incumbent cache, never network I/O.

    Atomic rename alone loses concurrent account changes. This advisory lock is
    shared by every writer in this successor. A bounded wait acquires this same
    short lock; it never repeats a provider request or a failed publication.
    """
    try:
        with open(path + ".lock", "a", encoding="utf-8") as lock:
            deadline = time.monotonic() + CACHE_LOCK_WAIT_S
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise
                    time.sleep(min(.02, remaining))
            try:
                cache = _load_cache(path)
                changed, result = update(cache)
                if changed:
                    _atomic_write(path, cache)
                return result
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except QuotaCacheWriteError:
        raise
    except OSError:
        raise QuotaCacheWriteError("quota cache publication unavailable; reconcile original owner") from None


def _begin_refresh(path: str, provider: str, account: Optional[str],
                   binding: Any, started_at: float) -> Optional[str]:
    """Invalidate old positive evidence before a GET can return a refusal.

    Completion must replace this exact marker in the existing cache. If final
    publication fails or the reader exits, the unresolved marker remains closed
    until the original owner reconciles it; force/TTL cannot replay that read.
    """
    marker = {"attempt_id": uuid.uuid4().hex, "provider": provider,
              "account": account, "binding": binding, "started_at": started_at}
    def update(cache):
        container, key = _cache_target(cache, provider, account)
        current = container.get(key)
        if (isinstance(current, dict) and
                (current.get("terminal_refusal") or _has_pending(current))
                or _attempt_at(current) > started_at):
            return False, current
        row = dict(current) if isinstance(current, dict) else {"states": [], "binding": binding}
        marker["previous_error"] = row.get("refresh_error")
        row.update(refresh_pending=marker, refresh_error="REFRESH_IN_PROGRESS",
                   refresh_started_at=started_at, failure_binding=binding)
        container[key] = row
        return True, row
    retained = _update_cache(path, update)
    if isinstance(retained, dict) and retained.get("refresh_pending") == marker:
        return marker["attempt_id"]
    return None


def _publish_observation(path: str, provider: str, account: Optional[str],
                         states: List[ProviderQuotaState], binding: Any,
                         started_at: float, *, attempt_id: Optional[str] = None) -> Dict[str, Any]:
    def update(cache):
        container, key = _cache_target(cache, provider, account)
        current = container.get(key)
        pending = current.get("refresh_pending") if isinstance(current, dict) else None
        matched = _pending_matches(pending, attempt_id, provider, account, binding, started_at)
        if (isinstance(current, dict) and current.get("terminal_refusal")
                or _has_pending(current) and not matched
                or _attempt_at(current) > started_at
                or isinstance(current, dict) and current.get("refresh_error")
                and _attempt_at(current) == started_at and not matched):
            return False, current
        row = {"refreshed_at": started_at, "refresh_started_at": started_at,
               "binding": binding, "states": [asdict(state) for state in states]}
        if provider == "glm" and account is not None:
            previous = dict(current, refresh_error=pending.get("previous_error")) if matched else current
            row["quota_change"] = _glm_quota_change(previous, row, account)
        container[key] = row
        return True, row
    return _update_cache(path, update)


def _glm_quota_change(previous: Any, current: Dict[str, Any], account: str) -> Dict[str, Any]:
    """Describe observed counter/clock changes, without inferring voucher use."""
    change = {"cause": "UNDETERMINED", "windows": []}
    if (not isinstance(previous, dict) or previous.get("binding") != current.get("binding")
            or previous.get("refresh_error") or previous.get("terminal_refusal")):
        return change
    prior_states = previous.get("states")
    if not isinstance(prior_states, list):
        return change
    for window in ("5h", "weekly"):
        old = [s for s in prior_states if isinstance(s, dict)
               and s.get("window") == window and s.get("account") == account]
        new = [s for s in current["states"] if s.get("window") == window]
        if len(old) != 1 or len(new) != 1:
            continue
        a, b = old[0], new[0]
        if any(s.get("source") != "PROVIDER_AUTHORITATIVE" or
               _num(s.get("remaining_pct")) is None or
               not 0 <= _num(s.get("remaining_pct")) <= 100 or
               not _iso(s.get("observed_at")) or
               s.get("reset_at") is not None and not _iso(s.get("reset_at"))
               for s in (a, b)):
            continue
        if _iso(b["observed_at"]) <= _iso(a["observed_at"]):
            continue
        before, after = _num(a["remaining_pct"]), _num(b["remaining_pct"])
        if after > before or _iso(b.get("reset_at")) != _iso(a.get("reset_at")):
            change["windows"].append({
                "window": window, "previous_remaining_pct": before,
                "remaining_pct": after, "previous_reset_at": a.get("reset_at"),
                "reset_at": b.get("reset_at"), "observed_at": b["observed_at"],
            })
    return change


def _load_cache(path: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(path or CACHE_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _atomic_write(path: str, value: Dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".quota_cache.", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            if tmp is not None:
                os.unlink(tmp)
        except OSError:
            pass
        raise QuotaCacheWriteError("quota cache publication failed; owner reconciliation required") from None


def read_provider(provider: str, force: bool = False,
                  now_ts: Optional[float] = None,
                  cache_path: Optional[str] = None) -> List[ProviderQuotaState]:
    provider = provider.lower()
    if provider not in {"glm", "minimax", "bailian", "grok"}:
        raise ValueError("unknown provider")
    if provider == "grok":
        # Unlike other pools, an older cached positive balance can never
        # release a later 402. This read is manual and never mutates marker.
        try:
            states = READERS["grok"]()
            if (len(states) != 1 or states[0].provider != "grok"
                    or states[0].window != "weekly"):
                raise ValueError("grok_billing_window_unusable")
            return states
        except Exception:
            return [_state(
                "grok", "weekly", None, None, None, None, "UNKNOWN",
                _utc_now(), 0.0, "billing unavailable; marker unchanged",
            )]
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
            cached_states = _cache_states(entry, "cached", keep_authoritative=True)
            if not force and _cache_fresh(entry, now):
                return [state for state in cached_states if state is not None]
            try:
                live = READERS["glm"]()
                retained = _publish_observation(path, "glm", None, live, None, now)
                return _cache_states(retained, "cached", keep_authoritative=True)
            except QuotaCacheWriteError:
                raise
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
    binding = _config_binding(provider) if provider == "minimax" else None
    same_binding = binding is not None and isinstance(entry, dict) and entry.get("binding") == binding
    cached_states = _cache_states(entry, "cached", keep_authoritative=True)
    if isinstance(entry, dict) and (entry.get("terminal_refusal") or _has_pending(entry)):
        return cached_states if same_binding else []
    if not force and same_binding and _cache_fresh(entry, now, binding):
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
    attempt_id = _begin_refresh(path, provider, None, binding, now)
    if attempt_id is None:
        return _cache_states(_load_cache(path).get(provider), "cached", keep_authoritative=True)
    try:
        live = READERS[provider]()
        after = _config_binding(provider)
        if binding != after:
            _record_refresh_failure(path, provider, None, entry, binding, now,
                                    ValueError("configuration changed during refresh"), attempt_id=attempt_id)
            return []
        live = _bind_states(live, "default", binding)
        retained = _publish_observation(path, provider, None, live, binding, now, attempt_id=attempt_id)
        return _cache_states(retained, "cached", keep_authoritative=True)
    except QuotaCacheWriteError:
        raise
    except Exception as exc:
        code = _record_refresh_failure(path, provider, None, entry, binding, now, exc, attempt_id=attempt_id)
        if same_binding and isinstance(entry.get("states"), list):
            stale = [
                _from_cache_entry(row, type(exc).__name__)
                for row in entry["states"]
            ]
            return [replace(state, refresh_error=code,
                            failure_config_generation=(binding or {}).get("config_generation"))
                    for state in stale if state is not None]
        return []


def cached_glm_account_parked(account: str, *, now_ts: Optional[float] = None,
                              cache_path: Optional[str] = None,
                              config_generation: Optional[str] = None) -> bool:
    """Narrow existing admission from a fresh authoritative account observation.

    No network, credential access, cache refresh or lease mutation. The caller
    must supply its current configuration generation. Unknown data cannot
    establish this narrow account hold; it also cannot establish quota readiness.
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
        if (not config_generation or not isinstance(entry.get("binding"), dict)
                or entry["binding"].get("config_generation") != config_generation
                or entry.get("refresh_error") or entry.get("terminal_refusal") or _has_pending(entry)):
            return False
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


def glm_config_binding() -> Optional[Dict[str, Any]]:
    """Public, secret-free binding from the existing GLM configuration owner."""
    return _config_binding("glm")


def _glm_cached_entry(path: str, account: str) -> Dict[str, Any]:
    provider = _load_cache(path).get("glm")
    accounts = provider.get("accounts") if isinstance(provider, dict) else None
    entry = accounts.get(account) if isinstance(accounts, dict) else None
    return entry if isinstance(entry, dict) else {}


def cached_glm_account_view(account: str, *, binding: Any,
                            now_ts: Optional[float] = None,
                            cache_path: Optional[str] = None) -> Dict[str, Any]:
    """Cache-only paired evidence for the incumbent broker; never refresh here."""
    now = _utc_now().timestamp() if now_ts is None else now_ts
    binding = binding if isinstance(binding, dict) else None
    entry = _glm_cached_entry(cache_path or CACHE_PATH, account)
    matches = bool(binding and entry.get("binding") == binding)
    result = account_quota_view(
        "glm", account, _cache_states(entry, "cached", keep_authoritative=True) if matches else [],
        config_generation=_binding_generation(binding),
        endpoint=(binding or {}).get("endpoint"), now_ts=now,
        refresh_error=("PROVIDER_REFUSED" if entry.get("terminal_refusal") else
                       entry.get("refresh_error") or
                       ("REFRESH_IN_PROGRESS" if _has_pending(entry) else None))
                      if matches else "CONFIG_UNQUALIFIED",
        failure_config_generation=_binding_generation(entry.get("failure_binding")))
    result["refresh_started_at"] = _num(entry.get("refresh_started_at")) if matches else None
    result["quota_change"] = entry.get("quota_change") if matches else None
    result["refresh_due"] = not _cache_fresh(entry, now, binding)
    return result


def glm_accounts_state(
    now_ts: Optional[float] = None,
    cache_path: Optional[str] = None,
    force: bool = False,
    *, account: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Refresh current GLM accounts through their original owner and cache.

    An explicit account selects only that configured account. The normal 300s
    on-demand cadence still visits quota-exhausted accounts. A manual reset can
    therefore replace both windows before the previously recorded deadline.
    This function never redeems a reset card or clears a broker hold.
    """
    now = _utc_now().timestamp() if now_ts is None else float(now_ts)
    path = cache_path or CACHE_PATH
    binding = _config_binding("glm")
    accounts = _glm_accounts_dict()
    if binding != _config_binding("glm"):
        return []
    if account is not None:
        if not isinstance(account, str) or account not in accounts:
            raise ValueError("GLM account is not configured")
        accounts = {account: accounts[account]}
    out: List[Dict[str, Any]] = []
    for name, info in accounts.items():
        cached = _glm_cached_entry(path, name)
        same_binding = bool(binding and isinstance(cached, dict) and cached.get("binding") == binding)
        terminal = isinstance(cached, dict) and (cached.get("terminal_refusal") or _has_pending(cached))
        failed_at = _num(cached.get("refresh_failed_at"))
        retry_due = (force or cached.get("failure_binding") != binding or failed_at is None
                     or not 0 <= now - failed_at < REFRESH_INTERVAL_S)
        if not terminal and retry_due and (force or not same_binding or not _cache_fresh(cached, now, binding)):
            key = str(info.get("api_key") or "") if isinstance(info, dict) else ""
            attempt_id = _begin_refresh(path, "glm", name, binding, now)
            if attempt_id is not None:
                try:
                    states = _bind_states(_live_glm(name, key), name, binding)
                except Exception as exc:
                    _record_refresh_failure(path, "glm", name, cached, binding, now, exc, attempt_id=attempt_id)
                else:
                    if binding != _config_binding("glm"):
                        _record_refresh_failure(path, "glm", name, cached, binding, now,
                                                ValueError("configuration changed during refresh"), attempt_id=attempt_id)
                        return []
                    # No provider I/O occurs while holding the publication lock.
                    _publish_observation(path, "glm", name, states, binding, now, attempt_id=attempt_id)
        # A concurrent newer observation/refusal wins, including on this return.
        retained = _glm_cached_entry(path, name)
        same_binding = bool(binding and retained.get("binding") == binding)
        states = _cache_states(retained, "cached", keep_authoritative=True) if same_binding else []
        error = retained.get("refresh_error") or ("REFRESH_IN_PROGRESS" if _has_pending(retained) else None)
        if retained.get("terminal_refusal"):
            error = ("PROVIDER_REFUSED" if retained.get("failure_binding") == binding
                     else "PRIOR_GENERATION_REFUSAL_UNRECONCILED")
        out.append({
            "name": name, "states": states,
            "source": states[0].source if states and not error else "UNKNOWN",
            "observed_at": states[0].observed_at if states else None,
            "error": error,
            "failure_config_generation": _binding_generation(retained.get("failure_binding")),
            "config_generation": _binding_generation(binding),
            "endpoint": (binding or {}).get("endpoint"),
            "refresh_started_at": _num(retained.get("refresh_started_at")),
            "quota_change": retained.get("quota_change"),
        })
    if binding != _config_binding("glm"):
        return []
    return out


def fresh_authoritative(provider: str, window: str,
                        now_ts: Optional[float] = None,
                        cache_path: Optional[str] = None,
                        account: Optional[str] = None) -> Optional[ProviderQuotaState]:
    read_started = _utc_now().timestamp()
    now = read_started if now_ts is None else float(now_ts)
    eligible = []
    observed_states = read_provider(provider, now_ts=now, cache_path=cache_path)
    # The provider response can arrive after the read began. Judge its clock
    # against completion time, without rewriting the producer's observation.
    now += max(0.0, _utc_now().timestamp() - read_started)
    for state in observed_states:
        if state.window != window or account is not None and state.account != account:
            continue
        observed = _iso(state.observed_at)
        try:
            age = now - datetime.fromisoformat(
                observed[:-1] + "+00:00"
            ).timestamp() if observed else None
        except (OSError, ValueError):
            age = None
        reset = _iso(state.reset_at)
        reset_ts = datetime.fromisoformat(reset.replace("Z", "+00:00")).timestamp() if reset else None
        pct = _num(state.remaining_pct)
        if (state.source == "PROVIDER_AUTHORITATIVE" and age is not None and 0 <= age <= FRESH_S
                and not state.refresh_error
                and pct is not None and 0 <= pct <= 100
                and (state.reset_at is None or reset is not None)
                and (reset_ts is None or reset_ts > now)):
            eligible.append(state)
    # A provider-wide flattened account list is not one physical allowance.
    return eligible[0] if len(eligible) == 1 else None


def glm_quota_decision(now_ts: Optional[float] = None,
                       local_estimate: Optional[Dict[str, Any]] = None,
                       cache_path: Optional[str] = None,
                       fallback_reader: Optional[Callable[[Optional[float]], Dict[str, Any]]] = None,
                       read_remote: bool = True) -> Dict[str, Any]:
    """R29 GLM quota decision (W4-G9 multi-account).

    State rules:
      * ``PARKED`` when every account has qualified evidence and EACH is
        exhausted in at least one required window (95-percent park threshold).
      * ``SPILL`` when every otherwise usable account's 5h pct >= 90 %.
      * ``OK`` only when at least one account has paired, qualified headroom.
      * ``UNKNOWN`` when no usable account exists and evidence is incomplete.

    Returns the BEST account's quota fields at the top level (so callers
    like ``pool_ledger.glm_burn`` keep working) plus a per-account
    breakdown under ``accounts`` (ordered list, one entry per configured
    account).
    """
    read_started = _utc_now().timestamp()
    now = read_started if now_ts is None else float(now_ts)
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
        estimate["observed_at"] = _iso(estimate.get("observed_at"))
        # Historical reconstruction is useful telemetry, not live allowance.
        estimate["state"] = "UNKNOWN"
        estimate.setdefault("detail", "W4-G7 calibrated local reconstruction")
        estimate["confidence"] = max(0.0, min(0.80, _num(estimate.get("confidence")) or 0.0))
        estimate.setdefault("accounts", [])
        return estimate

    now += max(0.0, _utc_now().timestamp() - read_started)
    breakdown: List[Dict[str, Any]] = []
    best_idx = -1
    best_score: Optional[Tuple[float, float, int]] = None
    usable_indices = []
    evidence_complete = []
    parked_accounts = []
    for idx, entry in enumerate(per_account):
        states = entry.get("states") or []
        qualified = account_quota_view(
            "glm", entry["name"], states,
            config_generation=entry.get("config_generation"),
            endpoint=entry.get("endpoint"), now_ts=now,
            refresh_error=entry.get("error"),
            failure_config_generation=entry.get("failure_config_generation"),
        )
        complete = all(row["reason"] in (None, "EXHAUSTED") for row in qualified["windows"])
        parked = complete and any(row["remaining_pct"] <= 5 for row in qualified["windows"])
        usable = qualified["quota_ready"] and not parked
        evidence_complete.append(complete)
        parked_accounts.append(parked)
        if usable:
            usable_indices.append(idx)
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
            "qualified_quota": qualified,
        })
        score = (
            (pct_5h if pct_5h is not None else float("inf")) if usable else float("inf"),
            (pct_week if pct_week is not None else float("inf")) if usable else float("inf"),
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

    if usable_indices:
        state = "SPILL" if all(breakdown[i]["pct_5h"] >= 90 for i in usable_indices) else "OK"
    elif all(evidence_complete) and all(parked_accounts):
        state = "PARKED"
    else:
        state = "UNKNOWN"

    best = breakdown[best_idx]
    observed = best.get("observed_at") or ""
    confidence = min(row["confidence"] for row in best["qualified_quota"]["windows"])
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


def qualified_provider_view(provider: str, *, force: bool = False,
                            now_ts: Optional[float] = None,
                            cache_path: Optional[str] = None,
                            account: Optional[str] = None) -> List[Dict[str, Any]]:
    """Join the incumbent GLM/MiniMax refresh to its per-account read view.

    This does not perform Go authentication or replace the GoRouter refresh
    owner. That owner must supply its original observation clock and binding to
    parse_go_usage_payload/account_quota_view before publishing Go readiness.
    """
    read_started = _utc_now().timestamp()
    now = read_started if now_ts is None else _num(now_ts)
    if now is None or now <= 0:
        raise ValueError("invalid observation time")
    if provider == "glm":
        entries = glm_accounts_state(force=force, now_ts=now, cache_path=cache_path,
                                     account=account)
    elif provider == "minimax":
        if account not in (None, "default"):
            raise ValueError("MiniMax account is not configured")
        before = _config_binding(provider)
        states = read_provider(provider, force=force, now_ts=now, cache_path=cache_path)
        after = _config_binding(provider)
        retained = _load_cache(cache_path or CACHE_PATH).get(provider)
        retained = retained if isinstance(retained, dict) else {}
        failure_binding = retained.get("failure_binding")
        error = retained.get("refresh_error") or ("REFRESH_IN_PROGRESS" if _has_pending(retained) else None)
        if retained.get("terminal_refusal") and failure_binding != after:
            error = "PRIOR_GENERATION_REFUSAL_UNRECONCILED"
        entries = [{"name": "default", "states": states if before == after else [],
                    "config_generation": (after or {}).get("config_generation"),
                    "endpoint": (after or {}).get("endpoint"),
                    "failure_config_generation": _binding_generation(failure_binding),
                    "error": error if before == after else "CONFIG_CHANGED"}]
    else:
        raise ValueError("qualified live reader only available for glm/minimax")
    now += max(0.0, _utc_now().timestamp() - read_started)
    return [dict(account_quota_view(provider, entry["name"], entry.get("states") or [],
                               config_generation=entry.get("config_generation"),
                               endpoint=entry.get("endpoint"), now_ts=now,
                               refresh_error=entry.get("error"),
                               failure_config_generation=entry.get("failure_config_generation")),
                 refresh_started_at=entry.get("refresh_started_at"),
                 quota_change=entry.get("quota_change"))
            for entry in entries]


def reconcile_glm_reset(account: str, *, now_ts: Optional[float] = None,
                        cache_path: Optional[str] = None) -> Dict[str, Any]:
    """One named-account quota read after an operator's reset; no redemption."""
    rows = qualified_provider_view("glm", force=True, account=account,
                                   now_ts=now_ts, cache_path=cache_path)
    ready = len(rows) == 1 and rows[0]["quota_ready"]
    return {"account": account, "state": "QUOTA_READY" if ready else "QUOTA_NOT_READY",
            "redemption": "NOT_PERFORMED", "reset_cause": "UNDETERMINED",
            "automatic_redemption": "NO_SUPPORTED_PUBLIC_CONTRACT",
            "broker_hold": "NOT_MUTATED", "quota": rows[0] if len(rows) == 1 else None}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("--provider", choices=("glm", "minimax", "bailian", "grok"))
    show.add_argument("--force", action="store_true")
    show.add_argument("--json", action="store_true")
    show.add_argument("--account", help="read only this configured GLM account")
    show.add_argument("--qualified", action="store_true",
                      help="per-account freshness/binding view; does not grant admission")
    reconcile = sub.add_parser("reconcile-reset", help="refresh GLM after a manual reset; never consume a card")
    reconcile.add_argument("--account", required=True)
    args = parser.parse_args(argv)
    if args.command == "reconcile-reset":
        try:
            result = reconcile_glm_reset(args.account)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0 if result["state"] == "QUOTA_READY" else 2
    if args.account and args.provider != "glm":
        parser.error("--account requires --provider glm")
    if args.qualified:
        if args.provider not in ("glm", "minimax"):
            parser.error("--qualified requires --provider glm or minimax")
        print(json.dumps(qualified_provider_view(args.provider, force=args.force, account=args.account),
                         indent=2, sort_keys=True, allow_nan=False))
        return 0
    providers = (args.provider,) if args.provider else ("glm", "minimax", "bailian")
    now_ts = _utc_now().timestamp()
    for provider in providers:
        if provider == "glm":
            per_account = glm_accounts_state(
                now_ts=now_ts, force=args.force, account=args.account,
            )
            _print_glm_accounts(per_account, args.json)
            continue
        states = read_provider(provider, force=args.force)
        _print(states, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
