#!/usr/bin/env python3
"""Usage-aware compaction recommendations for the existing T3 provider homes.

Uses only local Claude session usage metadata and the local T3 rate catalog.
Application is held until the existing settings owner is qualified.
No model requests, process restarts, or conversation text in retained output.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

HOME = Path.home()
T3 = HOME / ".t3"
PROVIDERS = {
    "capacity_fabric": "fabric-unified-router",
    "fabric_claude": "fabric-anthropic-oauth",
    "fabric_experiential": "fabric-experiential",
}
RATE_FILE = T3 / "userdata" / "usage-model-rates.json"
FABLE = ("claude-fable-5-2", "claude-fable-5.2", "claude-fable-5-1",
         "claude-fable-5.1", "claude-fable-5")
OPUS = ("claude-opus-5-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7")
LOW_CONTEXT_OPUS = ("claude-opus-4-6",)
CHEAP = ("glm-5.3", "glm-5.3-flash", "deepseek-v4.1-flash",
         "deepseek-v4.1-flash-1017", "deepseek-v4.1-flash-uncensored",
         "minimax-m3.1-flash", "qwen3.8-flash", "claude-fable-5.2:free")
# No model is admitted to a larger context by these numbers. The provider/model
# context cap always wins, and the external Capacity Fabric limit must be checked.
POLICY = {
    "fable": {"base": 200000, "minimum": 175000, "maximum": 350000,
              "budget_usd": 0.35},
    "opus": {"base": 250000, "minimum": 225000, "maximum": 400000,
             "budget_usd": 0.30},
    "low_context_opus": {"base": 180000, "minimum": 180000,
                         "maximum": 180000, "budget_usd": None},
    "economical": {"base": 900000, "minimum": 900000,
                   "maximum": 900000, "budget_usd": None},
}
MAX_TAIL_BYTES = 512000
MAX_FILES_PER_PROFILE = 36
MAX_SAMPLES_PER_FILE = 24
MAX_SAMPLES_PER_MODEL = 200
MAX_AGE_SECONDS = 6 * 3600


def family(model: str) -> str | None:
    if model in CHEAP:
        return "economical"
    if model in FABLE:
        return "fable"
    if model in OPUS:
        return "opus"
    if model in LOW_CONTEXT_OPUS:
        return "low_context_opus"
    return None


def recent_files(projects: Path, now: float) -> list[Path]:
    entries = []
    if not projects.is_dir():
        return []
    try:
        for folder in os.scandir(projects):
            if not folder.is_dir(follow_symlinks=False):
                continue
            for file in os.scandir(folder.path):
                if not file.name.endswith(".jsonl") or not file.is_file(follow_symlinks=False):
                    continue
                st = file.stat(follow_symlinks=False)
                if now - st.st_mtime <= MAX_AGE_SECONDS and st.st_size > 0:
                    entries.append((st.st_mtime, Path(file.path)))
    except (OSError, PermissionError):
        return []
    entries.sort(reverse=True)
    return [path for _, path in entries[:MAX_FILES_PER_PROFILE]]


def tail_records(path: Path):
    """Bound reads even when a session transcript is tens of megabytes."""
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            offset = max(0, size - MAX_TAIL_BYTES)
            stream.seek(offset)
            chunk = stream.read(MAX_TAIL_BYTES)
        lines = chunk.splitlines()
        if offset:
            lines = lines[1:]  # first line might be partial
        seen: set[str] = set()
        count = 0
        for line in reversed(lines):
            try:
                item = json.loads(line)
                if item.get("type") != "assistant":
                    continue
                msg = item.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                model = msg.get("model")
                if not isinstance(usage, dict) or not isinstance(model, str) or family(model) is None:
                    continue
                identifier = msg.get("id")
                if not isinstance(identifier, str) or identifier in seen:
                    continue
                seen.add(identifier)
                sample = {}
                for key in ("input_tokens", "cache_read_input_tokens",
                            "cache_creation_input_tokens", "output_tokens"):
                    value = usage.get(key, 0)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        raise ValueError("invalid usage")
                    sample[key] = value
                if not sum(sample.values()):
                    continue
                yield model, sample
                count += 1
                if count >= MAX_SAMPLES_PER_FILE:
                    break
            except (ValueError, TypeError, AttributeError, KeyError, json.JSONDecodeError):
                continue
    except (OSError, PermissionError):
        return


def collect_usage(profile: Path, now: float) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for transcript in recent_files(profile / "projects", now):
        for model, sample in tail_records(transcript):
            group = grouped.setdefault(model, [])
            if len(group) < MAX_SAMPLES_PER_MODEL:
                group.append(sample)
    return grouped


def price_catalog() -> dict:
    try:
        catalog = json.loads(RATE_FILE.read_text())
        if not isinstance(catalog, dict):
            return {}
        rates = catalog.get("document", {})
        return rates if isinstance(rates, dict) else {}
    except (OSError, ValueError):
        return {}


def rate_for(model: str, rates: dict) -> tuple[dict | None, str]:
    # Fable 5.2 is not in the current local catalog. 5.1 price is only a
    # proxy and must not be called the true Fable 5.2 bill.
    candidates = [model, "anthropic." + model]
    if model.startswith("claude-fable-5-2") or model == "claude-fable-5.2":
        candidates += ["claude-fable-5-1", "anthropic.claude-fable-5-1"]
    for candidate in candidates:
        rec = rates.get(candidate)
        if not isinstance(rec, dict):
            continue
        vals = [rec.get(x) for x in ("input_cost_per_token",
                                     "cache_read_input_token_cost",
                                     "cache_creation_input_token_cost")]
        try:
            valid = all(type(x) in (float, int) and x >= 0 and math.isfinite(x)
                        for x in vals)
        except OverflowError:
            valid = False
        if valid:
            return rec, "catalog-exact" if candidate in candidates[:2] else "proxy-fable-5-1"
    return None, "unknown"


def stats(samples: list[dict], price: dict | None) -> dict:
    n = len(samples)
    if not n:
        return {"samples": 0, "cache_ratio": None, "mean_input_usd": None,
                "mean_context_tokens": None}
    inputs = sum(x["input_tokens"] for x in samples)
    reads = sum(x["cache_read_input_tokens"] for x in samples)
    writes = sum(x["cache_creation_input_tokens"] for x in samples)
    total = inputs + reads + writes
    cost = None
    if price is not None:
        try:
            cost = (
                inputs * price["input_cost_per_token"] +
                reads * price["cache_read_input_token_cost"] +
                writes * price["cache_creation_input_token_cost"]
            ) / n
        except OverflowError:
            cost = None
        if cost is not None and not math.isfinite(cost):
            cost = None
    return {"samples": n,
            "cache_ratio": round(reads / total, 4) if total else None,
            "mean_input_usd": round(cost, 5) if cost is not None else None,
            "mean_context_tokens": total // n}


def target_window(model: str, sample_stats: dict) -> tuple[int, str]:
    group = family(model)
    if group is None:
        raise ValueError("unsupported model")
    p = POLICY[group]
    base = p["base"]
    if group in ("economical", "low_context_opus"):
        return base, "fixed-economical" if group == "economical" else "legacy-context-safe"
    if sample_stats["samples"] < 6 or sample_stats["cache_ratio"] is None or sample_stats["mean_input_usd"] is None:
        return base, "baseline-insufficient-evidence"
    cache_ratio = sample_stats["cache_ratio"]
    input_cost = sample_stats["mean_input_usd"]
    budget = p["budget_usd"]
    if cache_ratio >= 0.92 and input_cost <= budget * 0.65:
        target, reason = base + 100000, "high-cache-reuse-low-input-cost"
    elif cache_ratio >= 0.78 and input_cost <= budget:
        target, reason = base + 50000, "good-cache-reuse"
    elif cache_ratio <= 0.40 and input_cost > budget:
        target, reason = base - 25000, "high-cache-miss-cost"
    else:
        target, reason = base, "neutral-economics"
    return min(p["maximum"], max(p["minimum"], target)), reason


def step_limit(old: int | None, target: int, group: str) -> int:
    policy = POLICY[group]
    if old is None or group in ("economical", "low_context_opus"):
        effective = target
    # The first pass must establish the requested 200K/250K baselines,
    # not leap directly from 160K/200K to a speculative 300K/350K.
    elif old < policy["base"] <= target:
        effective = policy["base"]
    else:
        effective = max(old - 50000, min(old + 50000, target))
    # Policy bounds take priority when an existing value is outside the
    # legal range; normal in-range recommendations retain the 50K step.
    return min(policy["maximum"], max(policy["minimum"], effective))


def snapshot_profile(profile: str, enabled: bool, data: dict, usages: dict, rates: dict) -> tuple[dict, list[dict]]:
    out = json.loads(json.dumps(data))
    if not enabled:
        return out, []
    model_settings = out.setdefault("modelSettings", {})
    if not isinstance(model_settings, dict):
        raise ValueError("modelSettings is not an object")
    active = set(model_settings)
    if profile == "fabric-anthropic-oauth":
        active |= set(FABLE + OPUS + LOW_CONTEXT_OPUS)
    elif profile == "fabric-experiential":
        active |= set(CHEAP)
    else:
        active |= set(FABLE + OPUS + LOW_CONTEXT_OPUS + CHEAP)
    decisions = []
    for model in sorted(active):
        group = family(model)
        if group is None:
            continue  # never claim ownership of other model settings
        rec = model_settings.get(model)
        if rec is None:
            rec = {}
        if not isinstance(rec, dict):
            continue
        price, source = rate_for(model, rates)
        measurements = stats(usages.get(model, []), price)
        target, rationale = target_window(model, measurements)
        old = rec.get("autoCompactWindow")
        old = old if type(old) is int and 100000 <= old <= 1000000 else None
        effective = step_limit(old, target, group)
        rec["autoCompactWindow"] = effective
        model_settings[model] = rec
        decisions.append({"model": model, "family": group, "from": old,
                          "target": target, "set_to": effective,
                          "reason": rationale, "price_source": source,
                          **measurements})
    return out, decisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="held: shared-settings application is not qualified")
    parser.add_argument("--json", action="store_true", help="show safe decisions as JSON")
    args = parser.parse_args()
    if args.apply:
        parser.error("application held: shared-settings writer is not qualified; "
                     "use report mode until the existing settings owner is integrated")
    state = json.loads((T3 / "userdata" / "settings.json").read_text())
    instances = state.get("providerInstances", {})
    rates = price_catalog()
    now = time.time()
    records = {}
    for instance, profile in PROVIDERS.items():
        cfg = instances.get(instance, {})
        enabled = cfg.get("enabled") is True
        p = T3 / "providers" / profile / "settings.json"
        if not p.is_file():
            continue
        records[instance] = {"provider_home": profile, "enabled": enabled,
                             "would_change": False, "applied": False,
                             "models": []}
        if not enabled:
            continue
        raw = p.read_bytes()
        data = json.loads(raw)
        usage = collect_usage(p.parent, now)
        updated, decisions = snapshot_profile(profile, True, data, usage, rates)
        records[instance]["would_change"] = data != updated
        records[instance]["models"] = decisions
    snapshot = {"schema": "mastermind.t3.adaptive_compaction_snapshot.v1",
                "epoch": int(now), "mode": "dry_run",
                "application_status": "held-settings-owner-unqualified",
                "pricing": "local catalog API-equivalent proxy, not subscription bill",
                "provider_records": records}
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False))
    else:
        for instance, entry in records.items():
            print(instance, "active" if entry["enabled"] else "disabled",
                  "recommend-change" if entry["would_change"] else "no-change",
                  "relevant", len(entry["models"]))
            for item in entry["models"]:
                if item["model"] in ("claude-fable-5-2", "claude-opus-5-5",
                                     "glm-5.3", "glm-5.3-flash"):
                    print(" ", item["model"], item["from"], "->", item["set_to"],
                          item["reason"], "samples", item["samples"],
                          "cache_ratio", item["cache_ratio"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
