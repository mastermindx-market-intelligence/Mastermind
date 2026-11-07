#!/usr/bin/env python3
"""GLM provider config reader (library + CLI).

Reads api_key, model, URLs and concurrency_cap from $GLM_CONFIG (else
~/.glm/config.json). The api_key value is only ever returned by `config()`;
CLI commands and `status_lines()` never include it.

R26 credit metering helpers live here too: plan(), is_peak(), credit_rate(),
credits_for(), weekly_reset_utc() — all reading the config "plan" dict with
POOL_LIMITS.md §GLM defaults when absent.

Usage:
  glm_keys.py enabled
  glm_keys.py cap
  glm_keys.py model
  glm_keys.py anthropic_base_url
  glm_keys.py openai_base_url
  glm_keys.py is-peak
  glm_keys.py credit-rate
  glm_keys.py credits <model> <input_tokens> <cached_tokens> <output_tokens>
  glm_keys.py status
"""
from __future__ import annotations

import json
from copy import deepcopy
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, NoReturn, Optional, Tuple, Union

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — zoneinfo is stdlib on 3.9+
    ZoneInfo = None  # type: ignore

DEFAULT_CAP = 6
DEFAULT_ANTHROPIC_URL_INTL = "https://api.z.ai/api/anthropic"
DEFAULT_OPENAI_URL_INTL = "https://api.z.ai/api/paas/v4"
DEFAULT_ANTHROPIC_URL_CN = "https://open.bigmodel.cn/api/anthropic"
DEFAULT_OPENAI_URL_CN = "https://open.bigmodel.cn/api/paas/v4"
EXPECTED_MODE = 0o600

USAGE = (
    "Usage: glm_keys.py <enabled|cap|model|anthropic_base_url|"
    "openai_base_url|is-peak|credit-rate|status> | "
    "glm_keys.py credits <model> <input> <cached> <out>"
)


def _config_path() -> str:
    return os.environ.get("GLM_CONFIG") or os.path.expanduser("~/.glm/config.json")


def _defaults(region: str) -> Dict[str, str]:
    if region == "cn":
        return {
            "anthropic_base_url": DEFAULT_ANTHROPIC_URL_CN,
            "openai_base_url": DEFAULT_OPENAI_URL_CN,
        }
    return {
        "anthropic_base_url": DEFAULT_ANTHROPIC_URL_INTL,
        "openai_base_url": DEFAULT_OPENAI_URL_INTL,
    }


def _load_raw() -> Dict[str, Any]:
    path = _config_path()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return {}
    return data


def config() -> Dict[str, Any]:
    """Return the resolved config dict with defaults applied.

    Raises FileNotFoundError when the config file is absent.
    """
    raw = _load_raw()
    region_raw = raw.get("region", "")
    region = region_raw if region_raw in ("intl", "cn") else "intl"
    defaults = _defaults(region)
    api_key = raw.get("api_key", "")
    model_name = raw.get("model", "")
    anthro = raw.get("anthropic_base_url")
    openai = raw.get("openai_base_url")
    return {
        "api_key": api_key if isinstance(api_key, str) else "",
        "model": model_name if isinstance(model_name, str) else "",
        "anthropic_base_url": anthro if isinstance(anthro, str) and anthro else defaults["anthropic_base_url"],
        "openai_base_url": openai if isinstance(openai, str) and openai else defaults["openai_base_url"],
        "concurrency_cap": int(raw.get("concurrency_cap", DEFAULT_CAP) or DEFAULT_CAP),
        "region": region,
    }


def _file_mode() -> int:
    try:
        return stat.S_IMODE(os.stat(_config_path()).st_mode)
    except OSError:
        return -1


def _format_mode(mode: int) -> str:
    if mode < 0:
        return "missing"
    return f"0o{mode:o}"


def enabled() -> bool:
    """True iff the config file exists, api_key is non-empty, and model is set."""
    try:
        cfg = config()
    except FileNotFoundError:
        return False
    return bool(cfg.get("api_key")) and bool(cfg.get("model"))


# ── W4-G9 multi-account view ───────────────────────────────────────────────────

def _warn(msg: str) -> None:
    """Print a WARN to stderr; never includes any secret value."""
    print(f"WARN {msg}", file=sys.stderr)


def accounts() -> Dict[str, Dict[str, str]]:
    """Return the ordered dict {name: {api_key, plan, added}} from config.

    When the config has no top-level ``accounts`` dict (or it is empty),
    synthesize a single account named ``chairman-max`` whose ``api_key`` is
    the legacy top-level ``api_key``. This keeps the legacy single-account
    behaviour intact.

    Malformed entries (non-dict values, missing ``api_key``) are skipped
    with a WARN that names the account only; the ``api_key`` value is
    never written to stderr.

    The returned dict preserves the file's iteration order (Python 3.7+).
    """
    try:
        raw = _load_raw()
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    raw_accounts = raw.get("accounts")
    if not isinstance(raw_accounts, dict) or not raw_accounts:
        legacy = raw.get("api_key")
        if isinstance(legacy, str) and legacy:
            return {"chairman-max": {"api_key": legacy, "plan": "", "added": ""}}
        return {}

    out: Dict[str, Dict[str, str]] = {}
    for name, info in raw_accounts.items():
        if not isinstance(info, dict):
            _warn(f"glm_keys.accounts: skipping malformed entry name={name!r}")
            continue
        api_key = info.get("api_key")
        if not isinstance(api_key, str) or not api_key:
            _warn(
                f"glm_keys.accounts: skipping entry name={name!r} "
                "(missing api_key)"
            )
            continue
        plan = info.get("plan", "")
        if not isinstance(plan, str):
            plan = ""
        added = info.get("added", "")
        if not isinstance(added, str):
            added = ""
        out[str(name)] = {"api_key": api_key, "plan": plan, "added": added}
    return out


def cap() -> int:
    return int(config().get("concurrency_cap", DEFAULT_CAP))


def model() -> str:
    return str(config().get("model", ""))


def anthropic_base_url() -> str:
    return str(config().get("anthropic_base_url", ""))


def openai_base_url() -> str:
    return str(config().get("openai_base_url", ""))


# ── R26 credit metering ────────────────────────────────────────────────────────

DEFAULT_PLAN: Dict[str, Any] = {
    "credits_5h": 28000,
    "credits_week": 140000,
    # multipliers per POOL_LIMITS.md §GLM: in / cached / out
    "multipliers": {
        "glm-5.3": {"in": 6.9, "cached": 1.7, "out": 24.0},
        "glm-5.3-flash": {"in": 2.3, "cached": 0.56, "out": 8.0},
    },
    "peak_hours": {
        "tz": "Asia/Singapore",
        "days": "Mon-Fri",
        "window": "14:00-18:00",
        "offpeak_rate": 0.5,
    },
    "weekly_reset_local": "2026-09-21T05:16+08:00",
}

_SGT = ZoneInfo("Asia/Singapore") if ZoneInfo else timezone(timedelta(hours=8))
_DAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def plan() -> Dict[str, Any]:
    """Return the config "plan" dict deep-merged over DEFAULT_PLAN.

    Unlike config(), a missing/unreadable config file is not an error — the
    metering helpers must keep working with defaults.
    """
    try:
        raw = _load_raw().get("plan")
    except (OSError, ValueError):
        raw = None
    if not isinstance(raw, dict):
        return _deep_merge(DEFAULT_PLAN, {})
    return _deep_merge(DEFAULT_PLAN, raw)


def _to_sgt(now: Optional[datetime]) -> datetime:
    """Resolve `now` (None | naive → Asia/Singapore | aware) to SGT wall time."""
    if now is None:
        return datetime.now(_SGT)
    if now.tzinfo is None:
        return now.replace(tzinfo=_SGT)
    return now.astimezone(_SGT)


def _to_utc(now: Union[datetime, None]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=_SGT).astimezone(timezone.utc)
    return now.astimezone(timezone.utc)


def _parse_days(spec: Any) -> frozenset:
    """Parse 'Mon-Fri' / 'mon,wed' / ['mon','tue'] into weekday ints (Mon=0)."""
    if isinstance(spec, (list, tuple, set)):
        out: set = set()
        for item in spec:
            out |= _parse_days(item)
        return frozenset(out)
    text = str(spec or "").strip().lower()
    if not text:
        return frozenset()
    days: set = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            ia, ib = _DAY_NAMES.get(a[:3]), _DAY_NAMES.get(b[:3])
            if ia is None or ib is None:
                continue
            lo, hi = min(ia, ib), max(ia, ib)
            days.update(range(lo, hi + 1))
        else:
            day = _DAY_NAMES.get(part[:3])
            if day is not None:
                days.add(day)
    return frozenset(days)


def _parse_window(text: Any) -> Tuple[int, int]:
    """Parse 'HH:MM-HH:MM' into (start_min, end_min); end exclusive."""
    try:
        a, _, b = str(text).partition("-")
        ah, am = a.strip().split(":")
        bh, bm = b.strip().split(":")
        return int(ah) * 60 + int(am), int(bh) * 60 + int(bm)
    except Exception:
        return 14 * 60, 18 * 60


def _is_peak_for(plan_data: Dict[str, Any],
                 now: Optional[datetime] = None) -> bool:
    """Peak test against an already-resolved plan dict (no config reads)."""
    ph = plan_data.get("peak_hours") or {}
    days = _parse_days(ph.get("days", "Mon-Fri"))
    start, end = _parse_window(ph.get("window", "14:00-18:00"))
    local = _to_sgt(now)
    return local.weekday() in days and start <= local.hour * 60 + local.minute < end


def is_peak(now: Optional[datetime] = None) -> bool:
    """True inside the plan's peak window (default Mon–Fri 14:00–18:00 SGT)."""
    return _is_peak_for(plan(), now)


def _credit_rate_for(plan_data: Dict[str, Any],
                     now: Optional[datetime] = None) -> float:
    """Rate against an already-resolved plan dict (no config reads)."""
    if _is_peak_for(plan_data, now):
        return 1.0
    try:
        rate = float((plan_data.get("peak_hours") or {}).get("offpeak_rate", 0.5))
    except (TypeError, ValueError):
        rate = 0.5
    return rate if rate > 0 else 0.5


def credit_rate(now: Optional[datetime] = None) -> float:
    """1.0 in the peak window, else the plan's offpeak_rate (default 0.5)."""
    return _credit_rate_for(plan(), now)


def _multipliers_for(plan_data: Dict[str, Any], model: str) -> Dict[str, float]:
    """Per-model in/cached/out multipliers; unknown model → glm-5.3 (conservative)."""
    mults = plan_data.get("multipliers") or {}
    row = mults.get(model) if isinstance(mults, dict) else None
    if not isinstance(row, dict):
        row = mults.get("glm-5.3")
    if not isinstance(row, dict):
        row = {}
    out: Dict[str, float] = {}
    for key, default in (("in", 6.9), ("cached", 1.7), ("out", 24.0)):
        try:
            out[key] = float(row.get(key, default))
        except (TypeError, ValueError):
            out[key] = default
    return out


def _multipliers(model: str) -> Dict[str, float]:
    return _multipliers_for(plan(), model)


def _credits_for_plan(plan_data: Dict[str, Any], model: str, input_tokens: int,
                      cached_tokens: int, output_tokens: int,
                      now: Optional[datetime] = None) -> float:
    """Plan credits from an already-resolved plan dict (no config reads)."""
    m = _multipliers_for(plan_data, model)
    total_input = float(input_tokens or 0)
    cached = max(0.0, min(float(cached_tokens or 0), total_input))
    uncached = total_input - cached
    raw = (
        uncached * m["in"]
        + cached * m["cached"]
        + float(output_tokens or 0) * m["out"]
    ) / 10000.0
    return raw * _credit_rate_for(plan_data, now)


def credits_for(model: str, input_tokens: int, cached_tokens: int,
                output_tokens: int, now: Optional[datetime] = None) -> float:
    """Plan credits with OpenAI total-prompt semantics.

    ``input_tokens`` is the total prompt-token count and includes
    ``cached_tokens``. Only the uncached portion uses ``m_in``.
    """
    return _credits_for_plan(plan(), model, input_tokens, cached_tokens,
                             output_tokens, now)


def make_credit_calculator():
    """Capture one resolved plan and return a read-free ``credits_for`` callable.

    The returned callable has the same signature as ``credits_for`` and
    performs zero plan/config file reads. It keeps this snapshot even if the
    config changes later; calling ``make_credit_calculator`` again resolves a
    fresh plan. No global cache or shared mutable plan is involved.
    """
    plan_data = deepcopy(plan())

    def calculate(model: str, input_tokens: int, cached_tokens: int,
                  output_tokens: int,
                  now: Optional[datetime] = None) -> float:
        return _credits_for_plan(plan_data, model, input_tokens, cached_tokens,
                                 output_tokens, now)

    return calculate


def weekly_reset_utc(now: Optional[datetime] = None) -> datetime:
    """Next future weekly boundary (UTC, tz-aware) from plan.weekly_reset_local.

    The anchor rolls forward in +7 d steps until it is strictly in the future.
    """
    anchor_raw = str(plan().get("weekly_reset_local") or
                     DEFAULT_PLAN["weekly_reset_local"])
    try:
        anchor = datetime.fromisoformat(anchor_raw)
    except ValueError:
        anchor = datetime.fromisoformat(DEFAULT_PLAN["weekly_reset_local"])
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=_SGT)
    anchor = anchor.astimezone(timezone.utc)
    now_utc = _to_utc(now)
    while anchor <= now_utc:
        anchor += timedelta(days=7)
    return anchor


def status_lines() -> List[str]:
    """Return status lines; never includes the api_key value."""
    path = _config_path()
    mode = _file_mode()
    try:
        cfg = config()
    except FileNotFoundError:
        return [
            f"file={path}",
            f"mode={_format_mode(mode)}",
            "key=unset",
            "model=",
            f"cap={DEFAULT_CAP}",
            f"anthropic_base_url={DEFAULT_ANTHROPIC_URL_INTL}",
            f"openai_base_url={DEFAULT_OPENAI_URL_INTL}",
        ]
    api_key = cfg.get("api_key", "")
    key_state = "set" if api_key else "unset"
    lines = [
        f"file={path}",
        f"mode={_format_mode(mode)}",
        f"key={key_state}",
        f"model={cfg.get('model', '')}",
        f"cap={cfg.get('concurrency_cap', DEFAULT_CAP)}",
        f"anthropic_base_url={cfg.get('anthropic_base_url', '')}",
        f"openai_base_url={cfg.get('openai_base_url', '')}",
    ]
    if mode != EXPECTED_MODE:
        lines.append(f"WARN mode={_format_mode(mode)} expected=0o600")
    return lines


def _die(msg: str, rc: int = 2) -> NoReturn:
    print(msg, file=sys.stderr)
    raise SystemExit(rc)


def cmd_enabled(argv: List[str]) -> int:
    if enabled():
        print(1)
        return 0
    print(0)
    return 1


def cmd_cap(argv: List[str]) -> int:
    if not enabled():
        return 1
    print(cap())
    return 0


def cmd_model(argv: List[str]) -> int:
    if not enabled():
        return 1
    print(model())
    return 0


def cmd_anthropic_base_url(argv: List[str]) -> int:
    if not enabled():
        return 1
    print(anthropic_base_url())
    return 0


def cmd_openai_base_url(argv: List[str]) -> int:
    if not enabled():
        return 1
    print(openai_base_url())
    return 0


def cmd_status(argv: List[str]) -> int:
    for line in status_lines():
        print(line)
    return 0


def cmd_is_peak(argv: List[str]) -> int:
    print("true" if is_peak() else "false")
    return 0


def cmd_credit_rate(argv: List[str]) -> int:
    print(f"{credit_rate():.1f}")
    return 0


def cmd_credits(argv: List[str]) -> int:
    if len(argv) != 4:
        _die(
            "Usage: glm_keys.py credits <model> <input_tokens> "
            "<cached_tokens> <output_tokens> "
            "(input_tokens is TOTAL prompt tokens)",
            2,
        )
    try:
        in_tok, cached_tok, out_tok = int(argv[1]), int(argv[2]), int(argv[3])
    except ValueError:
        _die("token counts must be integers", 2)
    print(f"{credits_for(argv[0], in_tok, cached_tok, out_tok):.2f}")
    return 0


COMMANDS = {
    "enabled": cmd_enabled,
    "cap": cmd_cap,
    "model": cmd_model,
    "anthropic_base_url": cmd_anthropic_base_url,
    "openai_base_url": cmd_openai_base_url,
    "is-peak": cmd_is_peak,
    "credit-rate": cmd_credit_rate,
    "credits": cmd_credits,
    "status": cmd_status,
}


def main(argv: Any = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    cmd = args[0]
    if cmd not in COMMANDS:
        _die(f"unknown command {cmd!r}\n{USAGE}", 2)
    try:
        return COMMANDS[cmd](args[1:])
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
