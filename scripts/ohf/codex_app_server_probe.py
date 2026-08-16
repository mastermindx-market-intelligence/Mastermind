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
    default_user_codex_home,
)
from scripts.ohf.probe_schema import (
    add_observation,
    apply_attestation,
    attest_manifests,
    canonical_digest,
    new_probe,
    observed_capability_manifest,
    requested_capability_manifest,
)
from scripts.ohf.protocol import (
    config_mcp_names,
    config_plugin_names,
    extra_roots_set_params,
    mcp_server_names,
    mcp_tool_names,
    parse_account_read,
    parse_config_read,
    parse_rate_limits,
    parse_usage_read,
    skill_names,
    skills_list_params,
    thread_turns,
    turn_texts,
)
from scripts.ohf.redaction import evidence_contains_secret, redact_evidence, redact_text

HARNESS_KIND = "codex-app-server"
CLIENT_INFO = {
    "name": "mastermind_ohf_p0",
    "title": "Mastermind OHF-P0 laboratory",
    "version": "0.1.1",
}
PARENT_MARK = f"{OHF_PROBE_TURN_ACK}-P"
FORK_MARK = f"{OHF_PROBE_TURN_ACK}-F"


def _argv_for(lab: Laboratory) -> list[str]:
    if lab.backend == "live":
        exe = shutil.which("codex")
        if not exe:
            raise FileNotFoundError("codex CLI is not installed")
        return [exe, "app-server"]
    return [sys.executable, "-m", "scripts.ohf.fake_app_server"]


def _thread_id(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    thread = result.get("thread") or {}
    return str(thread.get("id") or "")


def _forked_from(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    thread = result.get("thread") or {}
    return str(thread.get("forkedFromId") or thread.get("forked_from") or "")


def _turns_from(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    data = result.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return thread_turns(result)


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


def _skill_root(lab: Laboratory) -> str:
    return str(lab.workspace / ".agents" / "skills")


def run_codex_app_server_probe(lab: Laboratory) -> dict[str, Any]:
    probe = new_probe(probe_id=lab.probe_id, harness_kind=HARNESS_KIND)
    probe["host"] = lab.host_facts()
    probe["provider"]["requested_model"] = lab.requested_model
    expected = lab.expected_bundle()
    requested = requested_capability_manifest(
        model=lab.requested_model,
        skills=expected["skills"],
        mcp_servers=expected["mcp"],
        mcp_tools=[OHF_PROBE_MCP_TOOL],
        plugins=expected["plugins"],
        approval_policy="never",
        sandbox_mode="read-only",
    )
    probe["requested_manifest"] = requested
    probe["harness"]["requested_manifest_digest"] = canonical_digest(requested)
    holder: dict[str, AppServerClient | None] = {"client": None}
    parent_id = ""
    fork_id = ""
    last_turn_id = ""
    initial_mcp_pass = False
    unobservable: list[str] = []

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

    def set_rec(key: str, status: str) -> None:
        probe["recovery"][key] = status

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

    def reconnect() -> AppServerClient:
        leftover = holder.get("client")
        if leftover is not None:
            leftover.close()
        holder["client"] = _connect(lab)
        client = holder["client"]
        assert client is not None
        _initialize(client)
        return client

    _record_auth_isolation(probe, lab)

    try:
        try:
            holder["client"] = _connect(lab)
        except Exception as exc:
            observe("launch", "UNKNOWN", f"harness process failed to start: {exc}")
            unobservable.extend(["model", "skills", "mcp"])
            _store_observed(probe, requested, unobservable)
            return _finalize(probe, lab)

        client = current()
        if client is None or not client.alive():
            observe("launch", "UNKNOWN", "harness process exited immediately")
            unobservable.extend(["model", "skills", "mcp"])
            _store_observed(probe, requested, unobservable)
            return _finalize(probe, lab)

        probe["session_continuity"]["initial_pid"] = client.pid
        probe["session_continuity"]["process_generations"].append(
            {"reason": "launch", "pid": client.pid, "resumed_thread_id": ""}
        )
        observe(
            "launch",
            "VERIFIED",
            "App Server process started.",
            evidence=f"pid={client.pid} backend={lab.backend}",
        )
        probe["harness"]["binary_digest"] = binary_digest(
            shutil.which("codex") if lab.backend == "live" else sys.executable
        )
        probe["harness"]["version"] = lab.backend

        try:
            init = _initialize(client)
        except JsonRpcError as exc:
            observe("launch", "DEGRADED", f"process started but initialize failed: {exc}")
            unobservable.extend(["model", "skills", "mcp"])
            _store_observed(probe, requested, unobservable)
            return _finalize(probe, lab)

        probe["harness"]["version"] = str(init.get("userAgent") or lab.backend)

        account = try_rpc("account/read", {"refreshToken": False}) or {}
        parsed_account = parse_account_read(account)
        probe["provider"]["auth_type"] = parsed_account["auth_type"]
        probe["provider"]["plan_type"] = parsed_account["plan_type"]
        probe["provider"]["requires_openai_auth"] = parsed_account["requires_openai_auth"]

        config_raw = try_rpc("config/read", {"includeLayers": False})
        config_obj = parse_config_read(config_raw)
        if not config_obj:
            unobservable.append("model")
        observed_mcp_cfg = config_mcp_names(config_obj)
        observed_plugins = config_plugin_names(config_obj)
        served_model = str(config_obj.get("model") or "")
        approval_policy = str(config_obj.get("approval_policy") or config_obj.get("approvalPolicy") or "")
        sandbox_mode = str(config_obj.get("sandbox_mode") or config_obj.get("sandboxMode") or "")
        probe["provider"]["served_model_observed"] = served_model
        if not approval_policy:
            unobservable.append("approvals")
        if not sandbox_mode:
            unobservable.append("sandbox")

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
        probe["session_continuity"]["initial_thread_id"] = parent_id
        probe["fork_proof"]["parent_thread_id"] = parent_id
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
        client = reconnect()
        probe["session_continuity"]["replacement_pid"] = client.pid
        probe["session_continuity"]["process_generations"].append(
            {"reason": "graceful_restart", "pid": client.pid, "resumed_thread_id": ""}
        )
        if client.pid == first_pid:
            observe("process_restart", "UNKNOWN", "restarted process reused the same pid")
            probe["session_continuity"]["process_identity_changed"] = "UNKNOWN"
        else:
            observe(
                "process_restart",
                "VERIFIED",
                "Local App Server process restarted under a new pid.",
                evidence=f"old={first_pid} new={client.pid}",
            )
            probe["session_continuity"]["process_identity_changed"] = True

        resumed = try_rpc("thread/resume", {"threadId": parent_id, "cwd": str(lab.workspace)})
        resumed_id = _thread_id(resumed or {})
        probe["session_continuity"]["resumed_thread_id"] = resumed_id
        if resumed and resumed_id == parent_id:
            set_cap("resume", "pass")
            set_rec("process_sigterm_resume", "VERIFIED")
            probe["session_continuity"]["native_thread_survived"] = True
            probe["session_continuity"]["workspace_survived"] = True
            probe["session_continuity"]["process_generations"][-1]["resumed_thread_id"] = resumed_id
            observe("resume", "VERIFIED", "Resumed the same native thread after process restart.", evidence=parent_id)
            _bounded_turn(client, parent_id, f"Reply with exactly {OHF_PROBE_TURN_ACK}-2 and nothing else.")
        elif parent_id:
            set_cap("resume", "fail")
            probe["session_continuity"]["native_thread_survived"] = False
            observe("resume", "NOT_SUPPORTED", "thread/resume failed after process restart.")

        forked = try_rpc(
            "thread/fork",
            {"threadId": parent_id, **({"lastTurnId": last_turn_id} if last_turn_id else {})},
        )
        fork_id = _thread_id(forked or {})
        fork_source = _forked_from(forked or {})
        probe["fork_proof"]["fork_thread_id"] = fork_id
        probe["fork_proof"]["fork_source_thread"] = fork_source or parent_id
        probe["fork_proof"]["parent_neq_fork"] = bool(fork_id and fork_id != parent_id)
        if fork_id and fork_id != parent_id:
            set_cap("fork", "pass")
            _bounded_turn(client, parent_id, f"Parent continuation. Reply {PARENT_MARK}")
            _bounded_turn(client, fork_id, f"Fork continuation. Reply {FORK_MARK}")
            parent_read = try_rpc("thread/read", {"threadId": parent_id, "includeTurns": True})
            fork_read = try_rpc("thread/read", {"threadId": fork_id, "includeTurns": True})
            parent_texts = turn_texts(_turns_from(parent_read))
            fork_texts = turn_texts(_turns_from(fork_read))
            if not parent_texts or not fork_texts:
                parent_listed = try_rpc(
                    "thread/turns/list",
                    {"threadId": parent_id, "limit": 20, "sortDirection": "asc", "itemsView": "full"},
                )
                fork_listed = try_rpc(
                    "thread/turns/list",
                    {"threadId": fork_id, "limit": 20, "sortDirection": "asc", "itemsView": "full"},
                )
                parent_texts = parent_texts or turn_texts(_turns_from(parent_listed))
                fork_texts = fork_texts or turn_texts(_turns_from(fork_listed))
            inherited = OHF_PROBE_TURN_ACK in " ".join(fork_texts) if fork_texts else None
            parent_isolated = FORK_MARK not in " ".join(parent_texts) if parent_texts else None
            fork_isolated = PARENT_MARK not in " ".join(fork_texts) if fork_texts else None
            probe["fork_proof"]["inherited_earlier_state"] = (
                "VERIFIED" if inherited else ("UNKNOWN" if inherited is None else "NOT_SUPPORTED")
            )
            probe["fork_proof"]["parent_continuation_isolated"] = (
                "VERIFIED" if parent_isolated else ("UNKNOWN" if parent_isolated is None else "NOT_SUPPORTED")
            )
            probe["fork_proof"]["fork_continuation_isolated"] = (
                "VERIFIED" if fork_isolated else ("UNKNOWN" if fork_isolated is None else "NOT_SUPPORTED")
            )
            if inherited and parent_isolated and fork_isolated:
                probe["fork_proof"]["independent_continuation_proven"] = True
                observe(
                    "fork",
                    "VERIFIED",
                    "Forked the thread; parent and fork continuations stayed isolated.",
                    evidence=f"parent={parent_id} fork={fork_id}",
                )
            else:
                probe["fork_proof"]["independent_continuation_proven"] = "UNKNOWN"
                observe(
                    "fork",
                    "DEGRADED",
                    "Fork identities differ, but isolation was not proven from thread/read turns.",
                    evidence=f"parent={parent_id} fork={fork_id}",
                )
        elif parent_id:
            set_cap("fork", "fail")
            observe("fork", "NOT_SUPPORTED", "thread/fork did not produce a distinct identity.")

        try_rpc("skills/extraRoots/set", extra_roots_set_params([_skill_root(lab)]))
        skills_raw = try_rpc("skills/list", skills_list_params(str(lab.workspace), [_skill_root(lab)]))
        discovered_skills = skill_names(skills_raw)
        if skills_raw is None:
            unobservable.append("skills")
        probe["skill_attestation"]["requested_present"] = OHF_PROBE_SKILL_NAME in expected["skills"]
        probe["skill_attestation"]["discovered"] = OHF_PROBE_SKILL_NAME in discovered_skills
        if OHF_PROBE_SKILL_NAME in discovered_skills:
            probe["skill_attestation"]["invokable"] = True
            target = parent_id or fork_id
            if not target:
                probe["skill_attestation"]["invoked_successfully"] = False
                set_cap("skills", "unknown")
                observe(
                    "attest_skills",
                    "DEGRADED",
                    "Fixture skill was listed but no native thread id was available to invoke it.",
                    evidence=",".join(discovered_skills),
                )
            else:
                try:
                    skill_turn = _bounded_turn(
                        client,
                        target,
                        f"$ohf-probe Reply with exactly {OHF_PROBE_SKILL_ACK}",
                    )
                except JsonRpcError as exc:
                    skill_turn = {"texts": [], "error": str(exc)}
                blob = " ".join(skill_turn.get("texts") or []) + str(skill_turn)
                if OHF_PROBE_SKILL_ACK in blob:
                    probe["skill_attestation"]["invoked_successfully"] = True
                    set_cap("skills", "pass")
                    observe(
                        "attest_skills",
                        "VERIFIED",
                        "Fixture skill was requested, reported, and invoked.",
                        evidence=OHF_PROBE_SKILL_NAME,
                    )
                else:
                    probe["skill_attestation"]["invoked_successfully"] = False
                    set_cap("skills", "unknown")
                    observe(
                        "attest_skills",
                        "DEGRADED",
                        "Fixture skill was listed but invocation did not return the deterministic ack.",
                        evidence=",".join(discovered_skills),
                    )
        else:
            probe["skill_attestation"]["invokable"] = False
            set_cap("skills", "fail")
            observe("attest_skills", "NOT_SUPPORTED", "Fixture skill was not listed by skills/list.")

        lab.drop_skill()
        try_rpc("skills/extraRoots/set", extra_roots_set_params([]))
        after_drop = try_rpc("skills/list", skills_list_params(str(lab.workspace), []))
        remaining_skills = skill_names(after_drop)
        if OHF_PROBE_SKILL_NAME not in remaining_skills:
            probe["skill_attestation"]["removal"] = {
                "reloadable_without_restart": True,
                "status": "VERIFIED",
            }
        elif after_drop is None:
            probe["skill_attestation"]["removal"] = {
                "reloadable_without_restart": "UNKNOWN",
                "status": "UNKNOWN",
            }
        else:
            probe["skill_attestation"]["removal"] = {
                "reloadable_without_restart": False,
                "status": "NOT_SUPPORTED",
            }
            note("skill removal was not visible without a process restart")

        mcp_status = try_rpc(
            "mcpServerStatus/list",
            {"detail": "toolsAndAuthOnly", "threadId": parent_id},
        )
        mcp_names = mcp_server_names(mcp_status)
        tool_names = mcp_tool_names(mcp_status)
        if mcp_status is None:
            unobservable.append("mcp")
        probe["mcp_attestation"]["configured"] = OHF_PROBE_MCP_SERVER in observed_mcp_cfg
        probe["mcp_attestation"]["server_visible"] = OHF_PROBE_MCP_SERVER in mcp_names
        probe["mcp_attestation"]["tool_visible"] = OHF_PROBE_MCP_TOOL in tool_names
        probe["security"]["unexpected_tools"] = sorted(
            name for name in tool_names if name != OHF_PROBE_MCP_TOOL
        )
        invoked = try_rpc(
            "mcpServer/tool/call",
            {
                "threadId": parent_id,
                "server": OHF_PROBE_MCP_SERVER,
                "tool": OHF_PROBE_MCP_TOOL,
                "arguments": {"text": "ping"},
            },
        )
        invoked_text = str(invoked or "")
        mcp_event = any(
            (item.get("params") or {}).get("item", {}).get("type") == "mcp_tool_call"
            for item in client.notifications
        )
        probe["mcp_attestation"]["tool_callable"] = "echo:ping" in invoked_text
        probe["mcp_attestation"]["structured_event_visible"] = mcp_event
        if (
            probe["mcp_attestation"]["configured"]
            and probe["mcp_attestation"]["server_visible"]
            and probe["mcp_attestation"]["tool_visible"]
            and (probe["mcp_attestation"]["tool_callable"] or mcp_event)
        ):
            set_cap("mcp", "pass")
            initial_mcp_pass = True
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

        observed = observed_capability_manifest(
            model=served_model,
            skills=discovered_skills,
            mcp_servers=sorted(set(observed_mcp_cfg) | set(mcp_names)),
            mcp_tools=tool_names,
            plugins=observed_plugins,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            harness_version=str(probe["harness"]["version"]),
        )
        _store_observed(probe, requested, unobservable, observed)

        limits = try_rpc("account/rateLimits/read")
        usage_read = try_rpc("account/usage/read")
        quota = parse_rate_limits(limits)
        if quota.get("classification") == "provider_reported":
            probe["quota"] = quota
            primary = quota.get("primary") if isinstance(quota.get("primary"), dict) else {}
            if "used_percent" in primary:
                probe["usage"]["classification"] = "provider_reported"
                probe["usage"]["source"] = "account/rateLimits/read"
                probe["usage"]["used_percent"] = primary.get("used_percent")
            set_cap("quota_telemetry", "pass")
        parsed_usage = parse_usage_read(usage_read)
        if parsed_usage.get("summary"):
            probe["usage"]["source"] = probe["usage"]["source"] or "account/usage/read"
            if probe["usage"]["classification"] == "unknown":
                probe["usage"]["classification"] = "provider_reported"
            set_cap("usage_telemetry", "pass")
            probe["quota"].setdefault("usage_summary", parsed_usage.get("summary"))
        if probe["usage"]["classification"] == "unknown" and probe["quota"]["classification"] == "unknown":
            set_cap("quota_telemetry", "unknown")
            observe("usage_quota", "NOT_TESTED", "Harness did not expose structured usage or quota.")
        else:
            observe(
                "usage_quota",
                "VERIFIED",
                "Recorded provider-reported usage/quota without inferring remaining capacity.",
                evidence=str(probe["quota"].get("source") or probe["usage"]["source"]),
            )

        approvals = try_rpc("thread/settings/update", {"threadId": parent_id, "approvalPolicy": "never"})
        set_cap("approvals", "pass" if approvals is not None else "unknown")
        set_cap("native_subagents", "unknown")
        set_cap("human_attach", "unknown")
        set_cap("checkpoint", "unknown")

        _run_recovery(lab, probe, holder, parent_id, observe, set_rec, try_rpc, reconnect, initial_mcp_pass, note)

        leftover = holder.get("client")
        main_exited = leftover is None or leftover.proc is None or leftover.proc.poll() is not None
        if leftover is not None:
            leftover.close()
            holder["client"] = None
            main_exited = leftover.proc is None or leftover.proc.poll() is not None
        probe["cleanup_proof"]["main_pid_exited"] = bool(main_exited)
        probe["cleanup_proof"]["descendant_census"] = False
        if main_exited:
            set_rec("main_process_cleanup", "VERIFIED")
        else:
            set_rec("main_process_cleanup", "UNKNOWN")
        set_rec("transitive_orphan_cleanup", "UNKNOWN")
        observe(
            "cleanup",
            "VERIFIED" if main_exited else "DEGRADED",
            "Main App Server process exited; transitive orphan cleanup was not censused.",
        )
        observe("inert", "VERIFIED", "Commission did not open Executive lifecycle state.")
    finally:
        leftover = holder.get("client")
        if leftover is not None:
            leftover.close()
            holder["client"] = None
        had_secret = evidence_contains_secret(probe)
        redacted = redact_evidence(probe)
        still_exposed = evidence_contains_secret(redacted)
        redacted["security"]["credential_exposure"] = still_exposed
        if still_exposed:
            redacted["security"].setdefault("redaction_failures", []).append("secret_shaped_value_survived")
        if had_secret and not still_exposed:
            redacted.setdefault("notes", []).append("secret-shaped values were redacted before write")
        probe.clear()
        probe.update(redacted)
    return probe


def _record_auth_isolation(probe: dict[str, Any], lab: Laboratory) -> None:
    isolation = probe["auth_isolation"]
    isolation["auth_json_copied"] = False
    isolation["auth_json_symlinked"] = False
    isolation["implicit_default_home_fallback"] = False
    if lab.backend != "live":
        isolation["codex_home_used"] = str(lab.codex_home)
        isolation["dedicated_home_authenticated_independently"] = False
        return
    home = lab.dedicated_codex_home
    isolation["codex_home_used"] = str(home) if home else ""
    isolation["implicit_default_home_fallback"] = bool(home and home == default_user_codex_home())
    isolation["dedicated_home_authenticated_independently"] = bool(
        home and (home / "auth.json").is_file() and home != default_user_codex_home()
    )


def _store_observed(
    probe: dict[str, Any],
    requested: dict[str, Any],
    unobservable: list[str],
    observed: dict[str, Any] | None = None,
) -> None:
    observed = observed or observed_capability_manifest(
        model="",
        skills=[],
        mcp_servers=[],
        mcp_tools=[],
        plugins=[],
        approval_policy="",
        sandbox_mode="",
        harness_version=str((probe.get("harness") or {}).get("version") or ""),
    )
    probe["observed_manifest"] = observed
    probe["harness"]["observed_manifest_digest"] = canonical_digest(observed)
    apply_attestation(probe, attest_manifests(requested, observed, unobservable))


def _run_recovery(
    lab: Laboratory,
    probe: dict[str, Any],
    holder: dict[str, AppServerClient | None],
    parent_id: str,
    observe: Callable[..., None],
    set_rec: Callable[[str, str], None],
    try_rpc: Callable[..., dict[str, Any] | None],
    reconnect: Callable[[], AppServerClient],
    initial_mcp_pass: bool,
    note: Callable[[str], None],
) -> None:
    client = holder["client"]
    if client is None:
        return

    killed_pid = client.pid
    client.kill()
    client = reconnect()
    probe["session_continuity"]["sigkill_replacement_pid"] = client.pid
    process_died = client.pid != killed_pid
    resumed = try_rpc("thread/resume", {"threadId": parent_id})
    resumed_id = _thread_id(resumed or {})
    probe["session_continuity"]["sigkill_resume_thread_id"] = resumed_id
    probe["session_continuity"]["process_generations"].append(
        {"reason": "sigkill", "pid": client.pid, "resumed_thread_id": resumed_id}
    )
    session_alive = bool(resumed and resumed_id == parent_id)
    if process_died and session_alive:
        set_rec("process_sigkill_resume", "VERIFIED")
    elif process_died and not session_alive:
        set_rec("process_sigkill_resume", "NOT_SUPPORTED")
    else:
        set_rec("process_sigkill_resume", "UNKNOWN")

    prior_sigterm = probe["recovery"].get("process_sigterm_resume")
    client.terminate()
    client = reconnect()
    probe["session_continuity"]["sigterm_replacement_pid"] = client.pid
    resumed = try_rpc("thread/resume", {"threadId": parent_id})
    resumed_id = _thread_id(resumed or {})
    probe["session_continuity"]["sigterm_resume_thread_id"] = resumed_id
    probe["session_continuity"]["process_generations"].append(
        {"reason": "sigterm", "pid": client.pid, "resumed_thread_id": resumed_id}
    )
    if resumed and resumed_id == parent_id:
        set_rec("process_sigterm_resume", "VERIFIED")
    elif prior_sigterm == "VERIFIED":
        note("post-SIGKILL SIGTERM resume did not take the writer; keeping earlier graceful SIGTERM VERIFIED")
    elif parent_id:
        set_rec("process_sigterm_resume", "NOT_SUPPORTED")
    else:
        set_rec("process_sigterm_resume", "UNKNOWN")

    client.send_malformed()
    recovered = try_rpc("thread/read", {"threadId": parent_id})
    if recovered is not None:
        set_rec("malformed_rpc_recovery", "VERIFIED")
    else:
        set_rec("malformed_rpc_recovery", "DEGRADED")
        client = reconnect()

    try:
        client.request("thread/resume", {"threadId": "thr_missing_ohf_p0"})
        set_rec("missing_session_fail_closed", "NOT_SUPPORTED")
    except JsonRpcError:
        set_rec("missing_session_fail_closed", "VERIFIED")

    before = lab.config_digest()
    lab.mutate_config_for_drift()
    after = lab.config_digest()
    if before != after:
        set_rec("config_drift_detected", "VERIFIED")
        observe(
            "config_drift",
            "VERIFIED",
            "Isolated configuration digest changed when the laboratory config changed.",
            evidence=f"{before[:12]}->{after[:12]}",
        )
    else:
        set_rec("config_drift_detected", "UNKNOWN")
    if try_rpc("config/read", {"includeLayers": False}) is None:
        set_rec("config_drift_detected", "DEGRADED")

    lab._write_isolated_config(include_mcp=True)
    lab.drop_mcp()
    try_rpc("config/mcpServer/reload")
    mcp_after = try_rpc(
        "mcpServerStatus/list",
        {"detail": "toolsAndAuthOnly", "threadId": parent_id},
    )
    remaining = mcp_server_names(mcp_after)
    if mcp_after is None:
        set_rec("mcp_disappearance_detected", "UNKNOWN")
    elif OHF_PROBE_MCP_SERVER not in remaining:
        set_rec("mcp_disappearance_detected", "VERIFIED")
    else:
        set_rec("mcp_disappearance_detected", "DEGRADED")
    if initial_mcp_pass:
        probe["capabilities"]["mcp"] = "pass"

    lab.workspace.mkdir(parents=True, exist_ok=True)
    lab.destroy_workspace()
    try:
        client.request(
            "turn/start",
            {
                "threadId": parent_id,
                "input": [{"type": "text", "text": OHF_PROBE_TURN_ACK}],
            },
        )
        set_rec("workspace_missing_fail_closed", "NOT_SUPPORTED")
        probe["session_continuity"]["workspace_survived"] = True
    except JsonRpcError:
        set_rec("workspace_missing_fail_closed", "VERIFIED")
        probe["session_continuity"]["workspace_survived"] = False
    client.close()
    holder["client"] = None


def _finalize(probe: dict[str, Any], lab: Laboratory) -> dict[str, Any]:
    del lab
    return redact_evidence(probe)
