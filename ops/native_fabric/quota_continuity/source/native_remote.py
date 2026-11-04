"""Command construction inside remote_sub_exec's existing host/process owner.

No lease acquisition, credentials, shell interpolation, transport or retry here.
The controller owns the shared provider lease; remote_sub_exec owns the host.
"""
from __future__ import annotations
import json
import math
import os
import sys
import subprocess
import re
import socket
import time
import stat
import shutil
from pathlib import Path

from fabric_client_projection import project_fabric_client

STUDIO_MCP_READ_URL = "https://m2studio.taila6eca1.ts.net/studio-fabric"
STUDIO_MCP_DESIGN_URL = "https://m2studio.taila6eca1.ts.net/studio-design"
STUDIO_PROVIDER_BY_MODE = {
    "grok": "grok",
    "cursor": "cursor",
    "codex-native": "codex",
    "claude-native": "claude",
    "oc-free": "opencode",
}

IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
# Stable adapter IDs and legacy rs_* IDs share the incumbent safe alphabet.
RUN = IDENT
SCHEMA = "mastermind.native.remote-terminal.v1"
MODELS = {
    "grok": {"grok-4.6"},
    "cursor": {"composer-2.5", "cursor-grok-4.6-high"},
    "codex-native": {"gpt-6-sol", "gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"},
    "claude-native": {"opus", "sonnet"},
    "oc-free": {"mimo-v2.5-free", "mimo-v2.6-flash-free", "ling-3.0-flash-fin-free"},
}
MODES = set(MODELS)

def studio_projection(mode, env):
    provider = STUDIO_PROVIDER_BY_MODE.get(mode)
    if provider is None:
        raise ValueError("native_studio_provider_refused")
    task_class = str(env.get("POOL_TASK_CLASS") or "default").strip().lower()
    return project_fabric_client(
        provider,
        task_class,
        read_url=STUDIO_MCP_READ_URL,
        design_url=STUDIO_MCP_DESIGN_URL,
        operator_delegation=bool(env.get("FABRIC_OPERATOR_CAPABILITY")),
    )

def scope(key, mode, model, here, env, *, timing=None):
    names = {"root":"POOL_ORCHESTRATOR_ID", "lease_id":"POOL_LEASE_ID",
             "account":"POOL_ACCOUNT", "host":"LANE_REMOTE_HOST",
             "run_id":"REMOTE_SUB_RUN_ID"}
    value = {k: env.get(v, "") for k, v in names.items()}
    value.update(mode=mode, model=model)
    if not RUN.fullmatch(key) or value["run_id"] != key:
        raise ValueError("native_remote_run_invalid")
    if not all(IDENT.fullmatch(v) for v in value.values()):
        raise ValueError("native_remote_scope_invalid")
    account = "C1" if mode == "oc-free" else "default"
    if env.get("LANE_LEASED") != "1" or value["account"] != account:
        raise ValueError("native_remote_provider_lease_required")
    if model not in MODELS.get(mode, set()):
        raise ValueError("native_remote_model_refused")
    digest = env.get("SUPPORT_DIGEST", "")
    if not re.fullmatch(r"[a-f0-9]{64}", digest) or here.parent.name != digest:
        raise ValueError("native_remote_support_invalid")
    hosts = json.loads((here / "hosts.json").read_text())
    entry = hosts.get(value["host"], {})
    if entry.get("local") is True or "lanes" not in entry.get("roles", []):
        raise ValueError("native_remote_host_refused")
    allowed = entry.get("allowed_modes")
    if not isinstance(allowed, list) or mode not in allowed:
        raise ValueError("native_remote_mode_not_enrolled")
    actual = socket.gethostname().split(".", 1)[0]
    if actual not in [h.split(".", 1)[0] for h in entry.get("hostnames", [])]:
        raise ValueError("native_remote_host_identity_mismatch")
    issued = float(env.get("NATIVE_LEASE_ISSUED", "0"))
    deadline = float(env.get("NATIVE_LEASE_DEADLINE", "0"))
    now = time.time()
    # This is the SAME clock sample used by admission, not a later estimate.
    # Diagnostic values never participate in admission or lease settlement.
    if timing is not None:
        timing["remote_scope_checked_at"] = now
    if not 0 < deadline-issued <= 7200 or not -30 <= now-issued <= 30 or now >= deadline:
        raise ValueError("native_remote_lease_window_invalid")
    return value

def command(mode, model, prompt, cwd, *, validated=False, packet_path=None):
    if model not in MODELS.get(mode, set()):
        raise ValueError("native_remote_model_refused")
    if not validated and mode in {"oc-free", "codex-native", "claude-native"}:
        return [sys.executable, str(Path(__file__).resolve()), "launch", mode, model, cwd, prompt]
    if mode == "grok" and model == "grok-4.6":
        prompt_args = ["-p", prompt] if packet_path is None else ["--prompt-file", str(packet_path)]
        return ["grok", *prompt_args, "--output-format", "json",
                "--permission-mode", "bypassPermissions", "--max-turns", "140",
                "--cwd", cwd, "--reasoning-effort", "high", "-m", model]
    if mode == "cursor":
        return ["cursor-agent", "-p", "--trust", "--force", "--sandbox", "disabled",
                "--approve-mcps", "--output-format", "text", "--model", model, prompt]
    if mode == "codex-native":
        projection = studio_projection(mode, os.environ)
        override = "mcp_servers.mastermindStudio.url=" + json.dumps(
            projection.url, ensure_ascii=True)
        return ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                "-c", "features.multi_agent=false", "-c", override,
                "-c", 'model_provider="openai"', "-c", 'approval_policy="never"',
                "--sandbox", "workspace-write", "-m", model, "-C", cwd, prompt]
    if mode == "claude-native":
        projection = studio_projection(mode, os.environ)
        return ["claude", "-p", prompt, "--model", model, "--output-format", "json",
                "--max-turns", "30", "--permission-mode", "acceptEdits",
                "--setting-sources", "", "--disallowedTools", "Agent,Task",
                "--strict-mcp-config", "--mcp-config", projection.config_text]
    if mode == "oc-free":
        return ["opencode", "run", "--pure", "--auto", "--agent", "build", "--dir", cwd,
                "-m", "opencode/"+model, prompt]
    raise ValueError("native_remote_model_refused")

def environment(mode, model, key, here, env):
    result = dict(env)
    if mode in {"claude-native", "codex-native", "oc-free"}:
        # No provider/key/model/config overrides from an orchestrator's shell.
        # Subscription credentials remain in the host's native secure store.
        for name in list(result):
            if name.startswith(("ANTHROPIC_", "CLAUDE_", "CODEX_", "OPENAI_", "OPENCODE_")):
                result.pop(name)
    if mode == "grok":
        for name in list(result):
            if name.startswith("GROK_"):
                result.pop(name)
        projection = studio_projection(mode, env)
        home = here / "lanes" / (key+".grok")
        home.mkdir(mode=0o700, parents=True)
        config = home / "config.toml"
        fd = os.open(config, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            hook_text = ''
            if env.get('FABRIC_OPERATOR_CAPABILITY'):
                from fabric_operator_client import grok_hook_toml
                hook_text = grok_hook_toml(here, env)
            stream.write(projection.config_text + hook_text)
            stream.flush()
            os.fsync(stream.fileno())
        auth = Path(env.get("HOME", str(Path.home()))) / ".grok" / "auth.json"
        auth_stat = os.lstat(auth)
        if not stat.S_ISREG(auth_stat.st_mode) or stat.S_ISLNK(auth_stat.st_mode):
            raise ValueError("native_grok_auth_unsafe")
        if hasattr(os, "getuid") and auth_stat.st_uid != os.getuid():
            raise ValueError("native_grok_auth_owner_refused")
        result.update(GROK_HOME=str(home), GROK_AUTH_PATH=str(auth))
    if mode == "cursor":
        projection = studio_projection(mode, env)
        config_path = Path(env.get("HOME", str(Path.home()))) / ".cursor" / "mcp.json"
        config_stat = os.lstat(config_path)
        if not stat.S_ISREG(config_stat.st_mode) or stat.S_ISLNK(config_stat.st_mode):
            raise ValueError("native_cursor_mcp_config_unsafe")
        if hasattr(os, "getuid") and config_stat.st_uid != os.getuid():
            raise ValueError("native_cursor_mcp_config_owner_refused")
        config = json.loads(config_path.read_text())
        expected = {"url": "${env:STUDIO_MCP_URL}"}
        if config.get("mcpServers", {}).get("mastermindStudio") != expected:
            raise ValueError("native_cursor_mcp_config_missing")
        result["STUDIO_MCP_URL"] = projection.url
    if mode == "oc-free":
        projection = studio_projection(mode, env)
        home = here / "lanes" / (key+".opencode")
        home.mkdir(mode=0o700, parents=True)
        for name in ("config", "data", "cache", "state"):
            (home/name).mkdir(mode=0o700)
        result.update(HOME=str(home), XDG_CONFIG_HOME=str(home/"config"),
                      XDG_DATA_HOME=str(home/"data"), XDG_CACHE_HOME=str(home/"cache"),
                      XDG_STATE_HOME=str(home/"state"))
        result["OPENCODE_CONFIG_CONTENT"] = json.dumps({
            "model":"opencode/"+model,"small_model":"opencode/"+model,
            "default_agent":"build", "subagent_depth":0,
            "permission":{"task":"deny"}, "tools":{"task":False},
            "enabled_providers":["opencode"],"autoupdate":False,"share":"disabled",
            "mcp":{"mastermindStudio":{"type":"remote","url":projection.url}},
        })
    return result

def _diagnostic_timestamp(value):
    """Bounded non-secret observation; malformed/missing timestamps stay unknown."""
    if type(value) not in (str, int, float) or (type(value) is str and len(value) > 32):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and 0 < result <= 2**53 else None


def launch_timing(env, timing):
    """Diagnostic only; wall clocks on separate hosts may differ."""
    result = {name: _diagnostic_timestamp(env.get(variable)) for name, variable in (
        ("controller_issued_at", "NATIVE_LEASE_ISSUED"),
        ("controller_deadline_at", "NATIVE_LEASE_DEADLINE"),
        ("remote_shell_entered_at", "NATIVE_REMOTE_SHELL_ENTERED"),
        ("remote_env_ready_at", "NATIVE_REMOTE_ENV_READY"),
        ("remote_python_invoked_at", "NATIVE_REMOTE_PYTHON_INVOKED"),
    )}
    for name in ("remote_exec_entered_at", "remote_scope_checked_at"):
        result[name] = _diagnostic_timestamp((timing or {}).get(name))
    issued, checked = result["controller_issued_at"], result["remote_scope_checked_at"]
    result["scope_age_seconds"] = checked - issued if issued is not None and checked is not None else None
    digest = env.get("SUPPORT_DIGEST", "")
    result["support_digest"] = digest if re.fullmatch(r"[a-f0-9]{64}", digest) else None
    return result


def terminal(here, key, mode, model, env, started, rc, *, timing=None, output_binding=None):
    """Record refusal or proven cleanup, never infer cleanup from exit code."""
    import os
    from lane_runtime import cleanup_receipt_is_proven
    names = {"root":"POOL_ORCHESTRATOR_ID", "lease_id":"POOL_LEASE_ID",
             "account":"POOL_ACCOUNT", "host":"LANE_REMOTE_HOST",
             "run_id":"REMOTE_SUB_RUN_ID"}
    value = {k: env.get(v, "") for k, v in names.items()}
    if not RUN.fullmatch(key):
        return
    cleanup = None
    capture = {}
    if started:
        try:
            row = json.loads((here / "lanes" / f"{key}.process.jsonl").read_text().splitlines()[-1])
            if row.get("schema") == "mastermind.local_owned_process_receipt.v1" and row.get("label") == key:
                cleanup = row.get("cleanup")
                capture = {k:row.get(k) for k in ('stdout_bytes','stderr_bytes','stdout_truncated','stderr_truncated')}
        except (OSError, ValueError, IndexError):
            pass
    value.update(schema=SCHEMA, mode=mode, model=model, started=started,
                 returncode=rc, cleanup=cleanup, capture=capture,
                 output_complete=not started or (capture.get('stdout_truncated') is False and capture.get('stderr_truncated') is False),
                 cleanup_proven=not started or cleanup_receipt_is_proven(cleanup or {}))
    value["launch_timing"] = launch_timing(env, timing)
    if output_binding is not None:
        value["output_binding"] = output_binding
    target = here / "lanes" / f"{key}.native-terminal.json"
    target.parent.mkdir(exist_ok=True)
    fd = os.open(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    if value["cleanup_proven"] and mode in {"grok", "oc-free"}:
        suffix = ".grok" if mode == "grok" else ".opencode"
        ephemeral = here / "lanes" / f"{key}{suffix}"
        try:
            if ephemeral.is_dir() and not ephemeral.is_symlink():
                shutil.rmtree(ephemeral)
        except OSError:
            # Cleanup failure never changes the already-proven worker receipt.
            # A later storage census can remove the inert per-run directory.
            pass


def validate_free_config(config, model, expected_mcp_url=STUDIO_MCP_READ_URL):
    """Validate merged configuration, including managed and agent overrides.

    No configuration contents or credentials are logged. Reject conflicting
    policy rather than rewriting the user's project or managed settings.
    """
    target = "opencode/"+model
    expected_mcp = {
        "mastermindStudio": {"type": "remote", "url": expected_mcp_url}
    }
    if (config.get("model") != target or config.get("small_model") != target
            or config.get("enabled_providers") != ["opencode"]
            or config.get("default_agent") != "build"
            or config.get("subagent_depth") != 0
            or config.get("permission", {}).get("task") != "deny"
            or config.get("tools", {}).get("task") is not False
            or config.get("mcp") != expected_mcp):
        raise ValueError("native_free_effective_config_refused")
    # A provider stanza can redirect a nominally free model to a paid gateway.
    # The exact Mastermind MCP stanza above is the only admitted extension.
    if any(config.get(k) for k in ("provider", "plugin", "command", "mode")):
        raise ValueError("native_free_inherited_extension_refused")
    for agent in config.get("agent", {}).values():
        if not isinstance(agent, dict):
            raise ValueError("native_free_agent_config_refused")
        if agent.get("model") not in (None, target) or agent.get("permission") or agent.get("tools"):
            raise ValueError("native_free_agent_override_refused")


def preflight(mode, model, cwd, env):
    # These subprocesses run INSIDE run_owned_process's process group/deadline.
    # Their outputs are private checks, not credentials or model calls.
    def check(argv):
        p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=15)
        if p.returncode:
            raise ValueError("native_preflight_refused")
        return p.stdout + (p.stderr if mode == "codex-native" else "")
    if mode == "codex-native":
        user_home = Path(env.get("HOME", str(Path.home()))).resolve()
        for directory in [Path(cwd).resolve(), *Path(cwd).resolve().parents]:
            # --ignore-user-config already excludes this exact native user file.
            if directory != user_home and (directory/".codex"/"config.toml").exists():
                raise ValueError("native_codex_project_provider_config_requires_review")
        if "--ignore-user-config" not in check(["codex", "exec", "--help"]):
            raise ValueError("native_codex_config_isolation_unavailable")
        if "Logged in using ChatGPT" not in check(["codex", "login", "status"]):
            raise ValueError("native_codex_subscription_login_required")
    elif mode == "claude-native":
        status = json.loads(check(["claude", "--setting-sources", "", "auth", "status", "--json"]))
        if status.get("loggedIn") is not True or status.get("authMethod") != "claude.ai":
            raise ValueError("native_claude_subscription_login_required")
    elif mode == "oc-free":
        projection = studio_projection(mode, env)
        validate_free_config(
            json.loads(check(["opencode", "debug", "config", "--pure"])),
            model,
            projection.url,
        )


if __name__ == "__main__":
    try:
        if len(sys.argv) != 6 or sys.argv[1] != "launch":
            raise ValueError("native_launch_arguments_invalid")
        _, _, mode, model, cwd, prompt = sys.argv
        preflight(mode, model, cwd, os.environ)
        argv = command(mode, model, prompt, cwd, validated=True)
        os.execvpe(argv[0], argv, os.environ)
    except (ValueError, OSError, subprocess.SubprocessError):
        print("NATIVE_PREFLIGHT_REFUSED", file=sys.stderr)
        raise SystemExit(78)
