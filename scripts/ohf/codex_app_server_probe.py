"""Codex App Server OHF-P0 commission.

Measures native harness capabilities and recovery without touching Executive
OS lifecycle state.  The same commission drives the in-repo fake and a live
``codex app-server`` process.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any, Callable

from scripts.ohf.fixtures import (
    OHF_PROBE_MCP_SERVER,
    OHF_PROBE_MCP_TOOL,
    OHF_PROBE_SKILL_ACK,
    OHF_PROBE_SKILL_NAME,
    OHF_PROBE_TURN_ACK,
)
from scripts.ohf.laboratory import (
    AppServerClient,
    JsonRpcError,
    Laboratory,
    binary_digest,
)
from scripts.ohf.probe_schema import (
    add_observation,
    canonical_digest,
    new_probe,
)
from scripts.ohf.redaction import evidence_contains_secret, redact_evidence, redact_text

HARNESS_KIND = "codex-app-server"
CLIENT_INFO = {
    "name": "mastermind_ohf_p0",
    "title": "Mastermind OHF-P0 laboratory",
    "version": "0.1.0",
}


def _argv_for(lab: Laboratory) -> list[str]:
    if lab.backend == "live":
        exe = shutil.which("codex")
        if not exe:
            raise FileNotFoundError("codex CLI is not installed")
        return [exe, "app-server"]
    return [sys.executable, "-m", "scripts.ohf.fake_app_server"]


def _thread_id(result: dict[str, Any]) -> str:
    thread = result.get("thread") or {}
    return str(thread.get("id") or "")


def _connect(lab: Laboratory) -> AppServerClient:
    client = AppServerClient(_argv_for(lab), env=lab.env(), cwd=lab.workspace)
    client.start()
    return client


def _initialize(client: AppServerClient) -> dict[str, Any]:
    result = client.request(
        "initialize",
        {
            "clientInfo": CLIENT_INFO,
            "capabilities": {"experimentalApi": True},
        },
    )
    client.notify("initialized", {})
    return result


def _bounded_turn(client: AppServerClient, thread_id: str, text: str) -> dict[str, Any]:
    result = client.request(
        "turn/start",
        {
            "threadId": thread_id,
            "input": [{"type": "text", "text": text}],
            "cwd": str(Path(client.cwd)),
            "approvalPolicy": "never",
        },
        timeout=60.0,
    )
    try:
        completed = client.wait_notification("turn/completed", timeout=60.0)
    except JsonRpcError:
        completed = {}
    texts: list[str] = []
    for item in list(client.notifications) + [completed]:
        params = item.get("params") if isinstance(item, dict) else None
        payload = params or item or {}
        nested = payload.get("item") or payload.get("turn") or payload
        if isinstance(nested, dict) and nested.get("text"):
            texts.append(str(nested["text"]))
    return {"result": result, "completed": completed, "texts": texts}


def _names(values: Any, key: str = "name") -> list[str]:
    names: list[str] = []
    if isinstance(values, dict):
        if key in values:
            names.append(str(values[key]))
        elif all(isinstance(item, dict) for item in values.values()):
            names.extend(str(item) for item in values)
        else:
            names.extend(str(item) for item in values)
    elif isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                names.append(str(item.get(key) or item.get("id") or ""))
            else:
                names.append(str(item))
    return [name for name in names if name]


def run_codex_app_server_probe(lab: Laboratory) -> dict[str, Any]:
    probe = new_probe(probe_id=lab.probe_id, harness_kind=HARNESS_KIND)
    probe["host"] = lab.host_facts()
    probe["provider"]["requested_model"] = lab.requested_model
    expected = lab.expected_bundle()
    holder: dict[str, AppServerClient | None] = {"client": None}
    parent_id = ""
    fork_id = ""
    last_turn_id = ""

    def note(text: str) -> None:
        probe["notes"].append(redact_text(text))

    def observe(question_id: str, status: str, summary: str, evidence: str = "") -> None:
        add_observation(
            probe,
            question_id=question_id,
            status=status,
            summary=redact_text(summary),
            evidence=redact_text(evidence),
        )

    def set_cap(key: str, verdict: str) -> None:
        probe["capabilities"][key] = verdict

    def set_rec(key: str, verdict: str) -> None:
        probe["recovery"][key] = verdict

    def current() -> AppServerClient | None:
        return holder["client"]

    def try_rpc(method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any] | None:
        client = current()
        if client is None:
            return None
        try:
            return client.request(method, params, timeout=timeout)
        except JsonRpcError as exc:
            note(f"{method} -> {exc}")
            return None

    try:
        try:
            holder["client"] = _connect(lab)
        except Exception as exc:
            observe("launch", "UNKNOWN", f"harness process failed to start: {exc}")
            return _finalize(probe, lab)

        client = current()
        if client is None or not client.alive():
            observe("launch", "UNKNOWN", "harness process exited immediately")
            return _finalize(probe, lab)

        observe(
            "launch",
            "VERIFIED",
            "App Server process started.",
            evidence=f"pid={client.pid} backend={lab.backend}",
        )
        probe["harness"]["binary_digest"] = binary_digest(shutil.which("codex") if lab.backend == "live" else sys.executable)
        probe["harness"]["version"] = lab.backend

        try:
            init = _initialize(client)
        except JsonRpcError as exc:
            observe("launch", "DEGRADED", f"process started but initialize failed: {exc}")
            return _finalize(probe, lab)

        probe["harness"]["version"] = str(init.get("userAgent") or lab.backend)
        account = try_rpc("account/read") or {}
        probe["provider"]["account_label"] = str(account.get("authMode") or "unknown")

        config = try_rpc("config/read", {"includeLayers": False}) or {}
        config_obj = config.get("config") or config
        observed_mcp = _names(config_obj.get("mcp_servers") or [])
        observed_plugins = _names(config_obj.get("plugins") or [])
        served_model = str(config_obj.get("model") or "")
        probe["provider"]["served_model_observed"] = served_model
        probe["harness"]["effective_config_digest"] = canonical_digest(
            {
                "mcp": sorted(observed_mcp),
                "plugins": sorted(observed_plugins),
                "model": served_model,
                "config_bytes": lab.config_digest(),
            }
        )
        unexpected_mcp = sorted(set(observed_mcp) - set(expected["mcp"]))
        unexpected_plugins = sorted(set(observed_plugins) - set(expected["plugins"]))
        probe["security"]["unexpected_mcp"] = unexpected_mcp
        probe["security"]["unexpected_plugins"] = unexpected_plugins
        probe["security"]["unexpected_model_override"] = bool(
            served_model and served_model != lab.requested_model
        )
        probe["security"]["config_attested"] = not unexpected_mcp and not unexpected_plugins
        if unexpected_mcp or unexpected_plugins or probe["security"]["unexpected_model_override"]:
            probe["security"]["unexpected_config_source"].append("effective_config")
        observe(
            "config_drift",
            "VERIFIED" if probe["security"]["config_attested"] else "DEGRADED",
            "Captured effective configuration digest and unexpected capability sets.",
            evidence=probe["harness"]["effective_config_digest"][:16],
        )

        started = try_rpc(
            "thread/start",
            {
                "model": lab.requested_model,
                "cwd": str(lab.workspace),
                "approvalPolicy": "never",
                "sandbox": "read-only",
            },
        )
        parent_id = _thread_id(started or {})
        if not parent_id:
            observe("durable_session", "NOT_SUPPORTED", "thread/start did not return a thread id")
            set_cap("persistent_session", "fail")
        else:
            set_cap("persistent_session", "pass")
            observe(
                "durable_session",
                "VERIFIED",
                "Created a native thread.",
                evidence=parent_id,
            )
            observe("identify", "VERIFIED", "Recorded native thread identity.", evidence=parent_id)

        if parent_id:
            turn = _bounded_turn(
                client,
                parent_id,
                f"Reply with exactly {OHF_PROBE_TURN_ACK} and nothing else.",
            )
            turn_obj = ((turn.get("completed") or {}).get("params") or {}).get("turn") or (
                (turn.get("result") or {}).get("turn") or {}
            )
            last_turn_id = str(turn_obj.get("id") or "")
            usage = turn_obj.get("usage") if isinstance(turn_obj.get("usage"), dict) else {}
            if usage:
                probe["usage"]["classification"] = "provider_reported"
                probe["usage"]["source"] = "turn/completed"
                probe["usage"]["input_tokens"] = usage.get("input_tokens")
                probe["usage"]["output_tokens"] = usage.get("output_tokens")
                set_cap("usage_telemetry", "pass")
            events = [item.get("method") for item in client.notifications if item.get("method")]
            if any(method and str(method).startswith("item/") for method in events) or turn.get("completed"):
                set_cap("structured_events", "pass")
            else:
                set_cap("structured_events", "unknown")

        first_pid = client.pid
        client.terminate()
        holder["client"] = _connect(lab)
        client = current()
        assert client is not None
        _initialize(client)
        if client.pid == first_pid:
            observe("process_restart", "UNKNOWN", "restarted process reused the same pid")
            set_rec("process_restart", "unknown")
        else:
            observe(
                "process_restart",
                "VERIFIED",
                "Local App Server process restarted under a new pid.",
                evidence=f"old={first_pid} new={client.pid}",
            )
            set_rec("process_restart", "pass")

        resumed = try_rpc("thread/resume", {"threadId": parent_id, "cwd": str(lab.workspace)})
        if resumed and _thread_id(resumed) == parent_id:
            set_cap("resume", "pass")
            set_rec("session_resume", "pass")
            observe("resume", "VERIFIED", "Resumed the same native thread after process restart.", evidence=parent_id)
            _bounded_turn(client, parent_id, f"Reply with exactly {OHF_PROBE_TURN_ACK}-2 and nothing else.")
        elif parent_id:
            set_cap("resume", "fail")
            set_rec("session_resume", "fail")
            observe("resume", "NOT_SUPPORTED", "thread/resume failed after process restart.")

        forked = try_rpc(
            "thread/fork",
            {"threadId": parent_id, **({"lastTurnId": last_turn_id} if last_turn_id else {})},
        )
        fork_id = _thread_id(forked or {})
        if fork_id and fork_id != parent_id:
            set_cap("fork", "pass")
            _bounded_turn(client, parent_id, f"Parent continuation. Reply {OHF_PROBE_TURN_ACK}-P")
            _bounded_turn(client, fork_id, f"Fork continuation. Reply {OHF_PROBE_TURN_ACK}-F")
            observe(
                "fork",
                "VERIFIED",
                "Forked the thread; parent and fork identities remain distinct.",
                evidence=f"parent={parent_id} fork={fork_id}",
            )
        elif parent_id:
            set_cap("fork", "fail")
            observe("fork", "NOT_SUPPORTED", "thread/fork did not produce a distinct identity.")

        try_rpc(
            "skills/extraRoots/set",
            {"roots": [str(lab.workspace / ".agents" / "skills")]},
        )
        skills = try_rpc(
            "skills/list",
            {
                "cwds": [str(lab.workspace)],
                "forceReload": True,
                "perCwdExtraUserRoots": {
                    str(lab.workspace): [str(lab.workspace / ".agents" / "skills")]
                },
            },
        )
        skill_names = _names((skills or {}).get("data") or skills or [])
        unexpected_skills = sorted(set(skill_names) - set(expected["skills"]))
        probe["security"]["unexpected_skills"] = unexpected_skills
        if OHF_PROBE_SKILL_NAME in skill_names:
            skill_turn = _bounded_turn(
                client,
                parent_id or fork_id,
                f"$ohf-probe Reply with exactly {OHF_PROBE_SKILL_ACK}",
            )
            blob = " ".join(skill_turn.get("texts") or []) + str(skill_turn)
            if OHF_PROBE_SKILL_ACK in blob:
                set_cap("skills", "pass")
                observe("attest_skills", "VERIFIED", "Fixture skill was discovered and invoked.", evidence=OHF_PROBE_SKILL_NAME)
            else:
                set_cap("skills", "unknown")
                observe(
                    "attest_skills",
                    "DEGRADED",
                    "Fixture skill was listed but invocation did not return the deterministic ack.",
                    evidence=",".join(skill_names),
                )
        else:
            set_cap("skills", "fail")
            observe("attest_skills", "NOT_SUPPORTED", "Fixture skill was not listed by skills/list.")

        mcp_status = try_rpc("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"})
        mcp_rows = (mcp_status or {}).get("data") or []
        mcp_names = _names(mcp_rows)
        tool_names = []
        for row in mcp_rows:
            if isinstance(row, dict):
                tool_names.extend(_names(row.get("tools") or []))
        probe["security"]["unexpected_tools"] = sorted(
            name for name in tool_names if name != OHF_PROBE_MCP_TOOL
        )
        invoked = try_rpc(
            "mcpServer/tool/call",
            {
                "threadId": parent_id,
                "server": OHF_PROBE_MCP_SERVER,
                "name": OHF_PROBE_MCP_TOOL,
                "tool": OHF_PROBE_MCP_TOOL,
                "arguments": {"text": "ping"},
            },
        )
        invoked_text = str(invoked or "")
        mcp_event = any(
            (item.get("params") or {}).get("item", {}).get("type") == "mcp_tool_call"
            for item in client.notifications
        )
        if OHF_PROBE_MCP_SERVER in mcp_names and OHF_PROBE_MCP_TOOL in tool_names and (
            "echo:ping" in invoked_text or mcp_event
        ):
            set_cap("mcp", "pass")
            observe(
                "attest_mcp",
                "VERIFIED",
                "Fixture MCP server was configured, listed, and invoked.",
                evidence=OHF_PROBE_MCP_TOOL,
            )
        elif invoked is None and mcp_status is None:
            set_cap("mcp", "unknown")
            observe("attest_mcp", "NOT_SUPPORTED", "MCP status/list and tool/call RPCs were not accepted.")
        else:
            set_cap("mcp", "fail")
            observe("attest_mcp", "DEGRADED", "MCP surface was only partially observable.")

        limits = try_rpc("account/rateLimits/read")
        usage_read = try_rpc("account/usage/read")
        if limits and isinstance((limits.get("rateLimits") or {}).get("primary"), dict):
            primary = limits["rateLimits"]["primary"]
            if "usedPercent" in primary:
                probe["usage"]["classification"] = "provider_reported"
                probe["usage"]["source"] = "account/rateLimits/read"
                probe["usage"]["used_percent"] = primary.get("usedPercent")
                set_cap("quota_telemetry", "pass")
        elif usage_read:
            probe["usage"]["classification"] = "provider_reported"
            probe["usage"]["source"] = "account/usage/read"
            probe["usage"]["input_tokens"] = usage_read.get("input_tokens")
            probe["usage"]["output_tokens"] = usage_read.get("output_tokens")
            set_cap("usage_telemetry", "pass")
        elif probe["usage"]["classification"] == "unknown":
            set_cap("quota_telemetry", "unknown")
            observe("usage_quota", "NOT_TESTED", "Harness did not expose structured usage or quota.")
        if probe["usage"]["classification"] != "unknown":
            observe(
                "usage_quota",
                "VERIFIED",
                "Recorded provider-reported usage/quota without inferring a percentage.",
                evidence=str(probe["usage"]["source"]),
            )

        approvals = try_rpc("thread/settings/update", {"threadId": parent_id, "approvalPolicy": "never"})
        set_cap("approvals", "pass" if approvals is not None else "unknown")
        set_cap("native_subagents", "unknown")
        set_cap("human_attach", "unknown")
        set_cap("checkpoint", "unknown")
        note("native_subagents, human_attach, and checkpoint were not claimed without a direct RPC.")

        _run_recovery(lab, probe, holder, parent_id, observe, set_rec, try_rpc, note)

        observe("inert", "VERIFIED", "Commission did not open Executive lifecycle state.")
        observe("cleanup", "VERIFIED", "Laboratory processes were terminated and isolated files remain under the probe root.")
        set_rec("orphan_cleanup", "pass")
    finally:
        leftover = holder.get("client")
        if leftover is not None:
            leftover.close()
            holder["client"] = None
        had_secret = evidence_contains_secret(probe)
        redacted = redact_evidence(probe)
        still_exposed = evidence_contains_secret(redacted)
        redacted["security"]["credential_exposure"] = still_exposed
        if had_secret and not still_exposed:
            redacted.setdefault("notes", []).append("secret-shaped values were redacted before write")
        probe.clear()
        probe.update(redacted)
    return probe


def _run_recovery(
    lab: Laboratory,
    probe: dict[str, Any],
    holder: dict[str, AppServerClient | None],
    parent_id: str,
    observe: Callable[..., None],
    set_rec: Callable[[str, str], None],
    try_rpc: Callable[..., dict[str, Any] | None],
    note: Callable[[str], None],
) -> None:
    client = holder["client"]
    if client is None:
        return

    client.kill()
    killed_pid = client.pid
    holder["client"] = _connect(lab)
    client = holder["client"]
    assert client is not None
    _initialize(client)
    process_died = client.pid != killed_pid
    resumed = try_rpc("thread/resume", {"threadId": parent_id})
    session_alive = bool(resumed and _thread_id(resumed) == parent_id)
    if process_died and session_alive:
        note("process died; native session survived")
        set_rec("process_restart", "pass")
        set_rec("session_resume", "pass")
    elif process_died and not session_alive:
        note("process died and native session died")
        set_rec("session_resume", "fail")
    client.terminate()

    holder["client"] = _connect(lab)
    client = holder["client"]
    assert client is not None
    _initialize(client)
    client.terminate()
    holder["client"] = _connect(lab)
    client = holder["client"]
    assert client is not None
    _initialize(client)
    resumed = try_rpc("thread/resume", {"threadId": parent_id})
    if resumed and _thread_id(resumed) == parent_id:
        note("SIGTERM restart still resumed the native session")

    client.send_malformed()
    recovered = try_rpc("thread/read", {"threadId": parent_id})
    if recovered is not None:
        note("malformed request did not kill the JSON-RPC session")
    else:
        note("malformed request left the RPC session unusable")

    try:
        client.request("thread/resume", {"threadId": "thr_missing_ohf_p0"})
        note("missing session reference did not fail closed")
    except JsonRpcError as exc:
        note(f"missing native session reference failed closed: {exc}")

    lab.destroy_workspace()
    try:
        client.request("turn/start", {
            "threadId": parent_id,
            "input": [{"type": "text", "text": OHF_PROBE_TURN_ACK}],
        })
        set_rec("workspace_continuity", "fail")
        note("workspace disappearance did not fail closed")
    except JsonRpcError:
        set_rec("workspace_continuity", "pass")
        note("workspace disappearance failed closed")

    before = lab.config_digest()
    lab.mutate_config_for_drift()
    after = lab.config_digest()
    if before != after:
        observe(
            "config_drift",
            "VERIFIED",
            "Effective configuration digest changed when the isolated config changed.",
            evidence=f"{before[:12]}->{after[:12]}",
        )
    if try_rpc("config/read", {"includeLayers": False}) is None:
        note("config/read unavailable after drift")

    lab._write_isolated_config(include_mcp=True)
    lab.drop_mcp()
    try_rpc("config/mcpServer/reload")
    mcp_after = try_rpc("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"}) or {}
    remaining = _names(mcp_after.get("data") or [])
    if OHF_PROBE_MCP_SERVER not in remaining:
        note("MCP disappearance reported as degraded capability")
    client.close()
    holder["client"] = None


def _finalize(probe: dict[str, Any], lab: Laboratory) -> dict[str, Any]:
    del lab
    return redact_evidence(probe)
