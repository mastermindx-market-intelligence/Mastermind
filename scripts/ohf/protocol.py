"""Codex App Server protocol parsers for the OHF-P0 laboratory.

These parsers accept the shapes documented by the current App Server, not the
shapes that would be convenient for our client.  A flat skills/list payload,
a ``roots`` extra-roots field, or a top-level ``authMode`` account document
must not be treated as success.
"""
from __future__ import annotations

from typing import Any, Mapping

from scripts.ohf.fixtures import OHF_PROBE_MCP_SERVER, OHF_PROBE_MCP_TOOL, OHF_PROBE_SKILL_NAME


def extra_roots_set_params(paths: list[str]) -> dict[str, list[str]]:
    """Real ``skills/extraRoots/set`` params.  The field is ``extraRoots``, not ``roots``."""
    return {"extraRoots": list(paths)}


def skills_list_params(cwd: str, extra_user_roots: list[str] | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"cwds": [cwd], "forceReload": True}
    if extra_user_roots:
        params["perCwdExtraUserRoots"] = [
            {"cwd": cwd, "extraUserRoots": list(extra_user_roots)}
        ]
    return params


def parse_skills_list(result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return skill objects from a grouped per-CWD ``skills/list`` result.

    A flat ``{data:[{name, path}]}`` payload is rejected: that is the unreal
    laboratory shape, not the current App Server contract.
    """
    if not isinstance(result, Mapping):
        return []
    data = result.get("data")
    if not isinstance(data, list) or not data:
        return []
    skills: list[dict[str, Any]] = []
    for group in data:
        if not isinstance(group, dict):
            return []
        if "cwd" not in group or "skills" not in group:
            return []
        rows = group.get("skills")
        if not isinstance(rows, list):
            return []
        for row in rows:
            if isinstance(row, dict) and str(row.get("name") or "").strip():
                skills.append(dict(row))
            else:
                return []
    return skills


def skill_names(result: Mapping[str, Any] | None) -> list[str]:
    return sorted({str(item["name"]) for item in parse_skills_list(result)})


def parse_account_read(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Record only safe identity facts.  Never persist email or token bytes.

    Real ``account/read`` is ``{account: {type, planType, ...}|null,
    requiresOpenaiAuth: bool}``.  A top-level ``authMode`` is not evidence.
    """
    parsed = {
        "auth_type": "UNKNOWN",
        "plan_type": "UNKNOWN",
        "requires_openai_auth": None,
    }
    if not isinstance(result, Mapping):
        return parsed
    if "requiresOpenaiAuth" in result:
        flag = result.get("requiresOpenaiAuth")
        parsed["requires_openai_auth"] = flag if isinstance(flag, bool) else None
    account = result.get("account")
    if account is None and "account" in result:
        return parsed
    if not isinstance(account, dict):
        return parsed
    auth_type = str(account.get("type") or "").strip()
    plan_type = str(account.get("planType") or "").strip()
    parsed["auth_type"] = auth_type or "UNKNOWN"
    parsed["plan_type"] = plan_type or "UNKNOWN"
    return parsed


def parse_mcp_status(result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, Mapping):
        return []
    data = result.get("data")
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and str(item.get("name") or "").strip():
            rows.append(dict(item))
    return rows


def mcp_server_names(result: Mapping[str, Any] | None) -> list[str]:
    return sorted({str(row["name"]) for row in parse_mcp_status(result)})


def mcp_tool_names(result: Mapping[str, Any] | None) -> list[str]:
    names: list[str] = []
    for row in parse_mcp_status(result):
        tools = row.get("tools") or []
        if not isinstance(tools, list):
            continue
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                names.append(str(tool["name"]))
            elif isinstance(tool, str) and tool.strip():
                names.append(tool)
    return sorted(set(names))


def parse_config_read(result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    config = result.get("config")
    return dict(config) if isinstance(config, dict) else {}


def config_mcp_names(config: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(config, Mapping):
        return []
    servers = config.get("mcp_servers") or config.get("mcpServers") or {}
    if isinstance(servers, dict):
        return sorted(str(name) for name in servers if str(name).strip())
    if isinstance(servers, list):
        names: list[str] = []
        for item in servers:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
            elif isinstance(item, str):
                names.append(item)
        return sorted(names)
    return []


def config_plugin_names(config: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(config, Mapping):
        return []
    plugins = config.get("plugins") or []
    if isinstance(plugins, dict):
        return sorted(str(name) for name in plugins if str(name).strip())
    if isinstance(plugins, list):
        names: list[str] = []
        for item in plugins:
            if isinstance(item, dict) and (item.get("name") or item.get("id")):
                names.append(str(item.get("name") or item.get("id")))
            elif isinstance(item, str) and item.strip():
                names.append(item)
        return sorted(names)
    return []


def parse_rate_limits(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Preserve provider-reported windows.  Do not estimate remaining capacity."""
    out: dict[str, Any] = {
        "classification": "unknown",
        "source": "",
    }
    if not isinstance(result, Mapping):
        return out
    limits = result.get("rateLimits")
    if not isinstance(limits, dict):
        return out
    out["classification"] = "provider_reported"
    out["source"] = "account/rateLimits/read"
    for key in ("primary", "secondary"):
        window = limits.get(key)
        parsed = _rate_window(window)
        if parsed:
            out[key] = parsed
    if "rateLimitReachedType" in limits and limits.get("rateLimitReachedType") is not None:
        out["rate_limit_reached_type"] = limits.get("rateLimitReachedType")
    return out


def _rate_window(window: Any) -> dict[str, Any] | None:
    if not isinstance(window, dict):
        return None
    parsed: dict[str, Any] = {}
    if "usedPercent" in window:
        parsed["used_percent"] = window.get("usedPercent")
    if "windowDurationMins" in window:
        parsed["window_duration_minutes"] = window.get("windowDurationMins")
    if "resetsAt" in window:
        parsed["resets_at"] = window.get("resetsAt")
    return parsed or None


def parse_usage_read(result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    summary = result.get("summary")
    buckets = result.get("dailyUsageBuckets")
    out: dict[str, Any] = {"classification": "provider_reported", "source": "account/usage/read"}
    if isinstance(summary, dict):
        out["summary"] = {
            key: summary.get(key)
            for key in (
                "lifetimeTokens",
                "peakDailyTokens",
                "longestRunningTurnSec",
                "currentStreakDays",
                "longestStreakDays",
            )
            if key in summary
        }
    if isinstance(buckets, list):
        out["daily_usage_buckets"] = [
            {"start_date": row.get("startDate"), "tokens": row.get("tokens")}
            for row in buckets
            if isinstance(row, dict)
        ]
    return out


def thread_turns(result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, Mapping):
        return []
    thread = result.get("thread") if isinstance(result.get("thread"), dict) else result
    if not isinstance(thread, dict):
        return []
    turns = thread.get("turns") or []
    return [dict(item) for item in turns if isinstance(item, dict)]


def turn_texts(turns: list[Mapping[str, Any]]) -> list[str]:
    texts: list[str] = []
    for turn in turns:
        text = turn.get("text")
        if text:
            texts.append(str(text))
    return texts


DEFAULT_REQUESTED_SKILLS = (OHF_PROBE_SKILL_NAME,)
DEFAULT_REQUESTED_MCP = (OHF_PROBE_MCP_SERVER,)
DEFAULT_REQUESTED_TOOLS = (OHF_PROBE_MCP_TOOL,)
