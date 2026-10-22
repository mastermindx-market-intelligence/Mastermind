#!/usr/bin/env python3
"""Install/verify the user-scope Mastermind orchestrator policy for Codex + Claude.

This is a host configuration deployer, not a lifecycle/control plane. It preserves
unrelated user configuration, never reads credentials, and only manages:
- one marked policy block in ~/.codex/AGENTS.md and ~/.claude/CLAUDE.md;
- exact native-agent safety settings in ~/.codex/config.toml and Claude settings;
- one PreToolUse hook registration in each provider home; and
- identical copies of the reviewed provider_orchestrator_guard.py source.

Apply/verify are intentionally separate so source review, installation, provider
selection, and behavior proof cannot be conflated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import sys
import tomllib
from typing import Any, Sequence


BEGIN = "<!-- mastermind-ceo-forward-execution-v2 -->"
END = "<!-- /mastermind-ceo-forward-execution-v2 -->"
TEMP_NATIVE_OVERRIDE_HEADING = "## Native Codex CEO routing override"
TEMP_NATIVE_OVERRIDE_SENTINELS = (
    "Native Codex child cap is **0 by default**.",
    "This is routing policy only. It grants no Fabric admission",
)

LEGACY_BLOCKS = (
    (
        "<!-- mastermind-ceo-async-ci-v1 -->",
        "<!-- /mastermind-ceo-async-ci-v1 -->",
    ),
    (
        "<!-- mastermind-ceo-context-discipline-v1 -->",
        "<!-- /mastermind-ceo-context-discipline-v1 -->",
    ),
    (
        "<!-- mastermind-ceo-forward-execution -->",
        "<!-- /mastermind-ceo-forward-execution -->",
    ),
    (
        "<!-- mastermind-orchestration-burn-guard-v1 -->",
        "<!-- /mastermind-orchestration-burn-guard-v1 -->",
    ),
    (
        "<!-- mastermind-fabric-routing-operational-v1 -->",
        "<!-- /mastermind-fabric-routing-operational-v1 -->",
    ),
)
BACKUP_SUFFIX = ".mastermind-orchestrator-backup"

# Fixed source assets, not a role/identity/grant registry.
ROLE_PACKAGE = "mastermind-fabric-orchestration"
CLAUDE_FABRIC_SKILL_PACKAGE = "mastermind-claude-fabric-delegation"
# Git blob digest of the separately reviewed local Skill source; not a runtime grant.
CLAUDE_FABRIC_SKILL_BLOB_SHA = "3dc63723e0e002bdb2337aaf68dfa97b7c0ced5f"
CODEX_FABRIC_SKILL_PACKAGE = "mastermind-fabric-delegate"
CODEX_FABRIC_SKILL_BLOB_SHA = "7fb137a1d2b2a0f4244897d3a71b1f17a70c0a73"
CODEX_FABRIC_LEGACY_SHA256 = "4700ec891fc040df4d0e4a351ede5acc5cd89eebd5b19bb06e659656033d0b9c"
CODEX_FABRIC_ENTRY_BEGIN = "<!-- mastermind-codex-fabric-entrypoint-v1 -->"
CODEX_FABRIC_ENTRY_END = "<!-- /mastermind-codex-fabric-entrypoint-v1 -->"
CODEX_FABRIC_ENTRY_BODY = """<!-- mastermind-codex-fabric-entrypoint-v1 -->
## Codex -> existing Subagent Fabric

When assigned an authorized M2 Codex orchestration mission, load the existing
`~/.codex/skills/mastermind-fabric-delegate/SKILL.md` for the original-root,
child request/status/result/accept and admitted operator-to-leaf procedures.
Native Codex child spawning is not paid Fabric admission. Preserve the current
thread lineage, provider grants, root budget and active effects; no second router.
<!-- /mastermind-codex-fabric-entrypoint-v1 -->
"""
FABRIC_ENTRY_BEGIN = "<!-- mastermind-claude-fabric-entrypoint-v1 -->"
FABRIC_ENTRY_END = "<!-- /mastermind-claude-fabric-entrypoint-v1 -->"
FABRIC_ENTRY_BODY = """<!-- mastermind-claude-fabric-entrypoint-v1 -->
## M2 Claude: delegate through existing Mastermind Subagent Fabric

When you are the currently assigned, authorized orchestrator and a bounded worker
will save effort, read `~/.claude/skills/mastermind-claude-fabric-delegation/SKILL.md`
first. It gives the real M2 Fabric CLI/MCP request, status, result and acceptance
path, as well as operator -> child return. Require verified original root and
actual immediate parent, authorized tools and existing admission. No native
Agent/Task or direct provider/SSH substitute and no inherited authorization.
Leaf workers cannot fan out; only a separately admitted operator with the
controller-issued child scope may request C0/C1 descendants.
<!-- /mastermind-claude-fabric-entrypoint-v1 -->
"""
ROLE_SHA256 = {'SKILL.md': '2afa8ef094b9a6a8236973d7e28a5b0781b8376f4aba0ce9cbd31f3f8e1e72f8', 'references/meta-ceo.md': 'df5076efcc355507f7589126048120b817f3ceefd2295974a825914b8f161240', 'references/program-ceo.md': '91652d5e0c68b092aa442c3f7af5f280ed344b1321b47a0ae87f86402cbc3b47', 'references/operator.md': '8c4c5aca6321d4dc9c0a2e6cf4265e9a40a56ded7b247b5e0f17cd346b94259c', 'references/worker.md': 'c43c135729a0565f1dabfc2e912c18cf7f7d8f3786f49cc7647853b84402b924', 'references/reviewer.md': '0d10a348c874d3288636e449fe1961357cb30e81fe0be87cefef3246feac5d5c'}

POLICY_BODY = f"""{BEGIN}
## Mastermind CEO / orchestrator forward execution

For Mastermind CEO/orchestrator, end-to-end delivery, substantial continuation, or
project-convergence work, optimize **accepted capability delta per root budget** rather than
agent count, tokens, elapsed time, tool calls, PR count, or administrative motion.

### Operating shape

__OPERATOR_FIRST_CORE__

### M2 Claude delegation discovery

- For an assigned M2 Claude CEO/orchestrator, read the installed
  `~/.claude/skills/mastermind-claude-fabric-delegation/SKILL.md` before external
  worker submission. It gives the exact incumbent Fabric CLI/MCP path and
  same-root submit, collect, review and acceptance sequence. A missing skill,
  session identity, or authenticated entrypoint is not a delegation grant.
- Paid Fabric operators spawned as `domain_orchestration` receive a separate
  per-run capability and auto-injected instructions only when admitted. They use
  the existing `mastermindStudio` `fabric_operator_scope` and `fabric_child_*`
  tools, never native subagents, raw SSH or borrowed parent credentials.

### Forward-execution and burn guards

- Load current protected Mastermind procedure once for substantial work, then execute. Re-census
  only on a material invalidator that can change the next action.
- A CEO cycle is event/phase-scoped, not tool/turn-scoped. Tool calls, Stop-hook re-entry, progress
  nudges, watcher registration, and steps inside one phase do not restart bootstrap or global census.
- Freeze the parent OUTCOME / DONE_WHEN, one current critical dependency, one active phase, and only
  a small path-disjoint ready set. Program-sized worker packets must be decomposed before dispatch.
- Every worker packet owns one independently useful bounded outcome and names exact source/ref,
  owned scope, DONE_WHEN/evidence, non-goals, and escalation condition. Send compact capsules and
  exact refs, not parent transcripts, giant handoffs, repository trees, full logs, or accepted worker
  transcripts.
- Leaf workers receive no recursive fan-out authority. An admitted coordinator may delegate only
  within its existing depth/budget and every helper counts as a descendant of the original root.
- Capacity is a ceiling, not a target. Do not fill slots merely because capacity is available.
  Reserve review/repair/integration capacity before increasing build fan-out.
- Status reads, comments, watcher maintenance, CI observations, checkpoints, PR metadata, handoffs,
  and planning are support work. Two consecutive support-only parent cycles with no capability delta
  or newly resolved blocker are a NO_DELTA_LOOP: change tactic or lane immediately.
- Two consecutive status-only/no-delta returns from the same worker dependency trip a worker breaker:
  do not send generic Continue. Park, re-scope, change tactic/route after effect reconciliation, or
  name the exact blocker and next observable capability delta.
- Consume and adjudicate a returned child before launching a duplicate/replacement for the same
  dependency. A queued/delivered child is not START, and a STARTed/effect-unknown child is never
  silently duplicated on another carrier.
- Continuously integrate source work. Keep one modifying candidate per conflicting source lane and
  prefer reviewable dependency-correct verticals over indefinitely growing private branches.
  Before starting a second semantic vertical on the same overlapping source lane, publish/hand off
  the first as a reviewable candidate unless an explicit atomic dependency requires them together.
- Context is working memory, not the program ledger. Keep exact artifact/revision refs plus compact
  accepted conclusions; do not repeatedly rehydrate full transcripts, PR bodies, logs, trees, or
  already-accepted proof.
- Pending CI/release freezes that lane, not the mission. After one bounded state read, bind exactly
  one native/background watcher to the exact PR/head/run or use the repository's durable merge
  controller, then immediately continue another independent authorized lane.
- Never foreground `gh run watch`, `gh run view --watch`, `gh pr checks --watch`, or a hand-written
  CI status + sleep/poll loop. The watcher event is the next CI observation. A PID/session handle
  alone is not a verified return path.
- PR ownership stays with the originating operation through genuine red repair, conflict resolution,
  merge, and required live proof. Accountability is not foreground occupation.
- Keep principals working while workers/watchers work. A queued job, watcher, green PR, merge,
  install, or checkpoint is a milestone, not automatic end-to-end completion.
- Finalization ceremony is pre-yield only. A clean task/phase/checkpoint boundary is a save-and-
  reassess point; start the next useful authorized phase in the same healthy turn when ready.
- Only when useful independent in-scope work is genuinely exhausted may a verified external owner +
  real return path on the sole remaining wait justify an external-wait turn boundary.

This block creates no lifecycle, queue, retry, watcher, merge, source-custody, permission,
provider admission, routing, or release authority. Executive OS, Agent OS, GitHub, Capacity,
repository law, and existing effect owners remain authoritative.
{END}
"""


class OrchestratorPolicyError(RuntimeError):
    """Unsafe or malformed host policy input."""


class OrchestratorPolicyApplyIncomplete(OrchestratorPolicyError):
    """At least one managed file changed before a later write failed."""

    def __init__(
        self,
        detail: str,
        *,
        modified_files: Sequence[str],
        verify_issues: Sequence[str],
    ) -> None:
        super().__init__(detail)
        self.modified_files = tuple(modified_files)
        self.verify_issues = tuple(verify_issues)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _regular_bytes(path: Path, *, missing: bytes | None = None) -> bytes:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing is not None:
            return missing
        raise OrchestratorPolicyError(f"required file missing: {path}")
    except OSError as exc:
        raise OrchestratorPolicyError(f"cannot inspect file: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise OrchestratorPolicyError(f"refuse non-regular provider file: {path}")
    if info.st_size > 4 * 1024 * 1024:
        raise OrchestratorPolicyError(f"provider file unexpectedly large: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise OrchestratorPolicyError(f"cannot read provider file: {path}") from exc


def _mode(path: Path, default: int = 0o600) -> int:
    try:
        return stat.S_IMODE(path.lstat().st_mode) or default
    except FileNotFoundError:
        return default


def _preflight_destination(path: Path, home: Path) -> None:
    """Reject unsafe existing target/parent shapes before the first apply write."""
    home = home.expanduser().resolve()
    current = path.parent
    while True:
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise OrchestratorPolicyError(
                    f"refuse unsafe provider directory in target chain: {current}"
                )
        if current == home or current.parent == current:
            break
        current = current.parent
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise OrchestratorPolicyError(f"refuse unsafe provider file: {path}")


def _safe_dir(path: Path) -> None:
    if path.exists():
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise OrchestratorPolicyError(f"refuse unsafe provider directory: {path}")
        return
    parent = path.parent
    if parent != path and not parent.exists():
        _safe_dir(parent)
    path.mkdir(mode=0o700)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError("short write")
            view = view[count:]
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


def _atomic_write(path: Path, payload: bytes) -> bool:
    _safe_dir(path.parent)
    current = _regular_bytes(path, missing=b"")
    mode = _mode(path)
    if current == payload:
        return False
    if path.exists():
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            _write_exclusive(backup, current, mode)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.mastermind.tmp")
    try:
        _write_exclusive(temporary, payload, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
        _fsync_dir(path.parent)
    except OSError as exc:
        raise OrchestratorPolicyError(f"provider policy write failed: {path}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return True


def _strip_marked_block(text: str, begin: str, end: str) -> str:
    begins = text.count(begin)
    ends = text.count(end)
    if begins != ends or begins > 1:
        raise OrchestratorPolicyError(
            f"managed orchestrator policy markers are malformed/duplicated: {begin}"
        )
    if begins == 0:
        return text
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    return (text[:start] + text[finish:]).strip()


def _strip_temporary_native_override(text: str) -> str:
    count = text.count(TEMP_NATIVE_OVERRIDE_HEADING)
    if count == 0:
        return text
    if count != 1:
        raise OrchestratorPolicyError(
            "temporary native Codex override appears more than once"
        )
    start = text.index(TEMP_NATIVE_OVERRIDE_HEADING)
    next_legacy_marker = text.find(
        "<!-- mastermind-ceo-forward-execution -->", start
    )
    next_current_marker = text.find(BEGIN, start)
    next_heading = text.find("\n## ", start + len(TEMP_NATIVE_OVERRIDE_HEADING))
    candidates = [
        value
        for value in (next_legacy_marker, next_current_marker, next_heading)
        if value >= 0
    ]
    if not candidates:
        raise OrchestratorPolicyError(
            "temporary native Codex override has no safe migration boundary"
        )
    end = min(candidates)
    block = text[start:end]
    if not all(sentinel in block for sentinel in TEMP_NATIVE_OVERRIDE_SENTINELS):
        raise OrchestratorPolicyError(
            "refuse ambiguous Native Codex CEO routing override migration"
        )
    prefix = text[:start].rstrip()
    suffix = text[end:].lstrip()
    if prefix and suffix:
        return prefix + "\n\n" + suffix
    return prefix + suffix


def _managed_text(original: str) -> str:
    text = _strip_temporary_native_override(original)
    for begin, end in LEGACY_BLOCKS:
        text = _strip_marked_block(text, begin, end)

    begins = text.count(BEGIN)
    ends = text.count(END)
    if begins != ends or begins > 1:
        raise OrchestratorPolicyError(
            "managed orchestrator policy v2 markers are malformed/duplicated"
        )
    core = _canonical_role_files()["SKILL.md"].decode("utf-8").split("---", 2)[2].strip()
    block = POLICY_BODY.replace("__OPERATOR_FIRST_CORE__", core).rstrip() + "\n"
    if begins == 1:
        start = text.index(BEGIN)
        finish = text.index(END, start) + len(END)
        replacement = text[:start] + block.rstrip() + text[finish:]
        return replacement.rstrip() + "\n"
    prefix = text.rstrip()
    return ((prefix + "\n\n") if prefix else "") + block


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OrchestratorPolicyError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise OrchestratorPolicyError(f"{label} must be a JSON object")
    return value


def _remove_managed_hook(rows: object) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        if rows is None:
            return []
        raise OrchestratorPolicyError("provider hook event must be a list")
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise OrchestratorPolicyError("provider hook row must be an object")
        hooks = row.get("hooks")
        if not isinstance(hooks, list):
            output.append(dict(row))
            continue
        kept = []
        for hook in hooks:
            if not isinstance(hook, dict):
                kept.append(hook)
                continue
            command = str(hook.get("command") or "")
            if "mastermind_fabric_routing_guard.py" in command:
                continue
            kept.append(hook)
        if kept:
            copied = dict(row)
            copied["hooks"] = kept
            output.append(copied)
    return output


def _hook_row(matcher: str, command: str, message: str) -> dict[str, Any]:
    return {
        "matcher": matcher,
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 10,
                "statusMessage": message,
            }
        ],
    }


def _render_claude_settings(raw: bytes, guard: Path) -> bytes:
    value = _json_object(raw, "Claude settings")
    env = value.setdefault("env", {})
    if not isinstance(env, dict):
        raise OrchestratorPolicyError("Claude env must be an object")
    env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "2"
    env["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] = "1"
    hooks = value.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise OrchestratorPolicyError("Claude hooks must be an object")
    rows = _remove_managed_hook(hooks.get("PreToolUse"))
    rows.append(
        _hook_row(
            "Agent|Task|Bash",
            f'python3 "{guard}"',
            "Enforcing Mastermind fabric routing and asynchronous CI waits",
        )
    )
    hooks["PreToolUse"] = rows
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


_TOML_TABLE_RE = re.compile(r"^\s*\[[^\]]+\]\s*(?:#.*)?$")
_TOML_AGENT_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>enabled|max_concurrent_threads_per_session)\s*=.*$"
)


def _native_codex_isolation(config: dict[str, object]) -> bool | None:
    """Recognize the Chairman-accepted bounded native/peer-denied exception.

    None: legacy/non-enrolled config, keep default disable policy.
    True: exactly compatible native policy; never overwrite its configuration.
    False: enabled native cap-2 but peer protections invalid/missing; refuse.
    This inspects configuration only, NOT a provider/Runtime/capacity grant.
    """
    agents = config.get("agents")
    if not isinstance(agents, dict) or agents.get("enabled") is not True:
        return None
    if type(agents.get("max_concurrent_threads_per_session")) is not int:
        return None
    if agents["max_concurrent_threads_per_session"] != 2:
        return None

    features = config.get("features")
    multi = features.get("multi_agent_v2") if isinstance(features, dict) else None
    if not isinstance(multi, dict):
        return False
    if (
        multi.get("enabled") is not True
        or multi.get("disable_direct_message") is not True
        or type(multi.get("max_concurrent_threads_per_session")) is not int
        or multi["max_concurrent_threads_per_session"] != 2
    ):
        return False

    plugins = config.get("plugins")
    app = plugins.get("codex-app-tools@openai-bundled") if isinstance(plugins, dict) else None
    mcp = app.get("mcp_servers") if isinstance(app, dict) else None
    tools = mcp.get("codex_app") if isinstance(mcp, dict) else None
    if not isinstance(tools, dict):
        return False
    disabled = tools.get("disabled_tools")
    if not isinstance(disabled, list) or not all(type(item) is str for item in disabled):
        return False
    return {
        "send_message_to_thread", "create_thread",
        "fork_thread", "handoff_thread",
    }.issubset(set(disabled))


def _render_codex_config(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise OrchestratorPolicyError("Codex config is not UTF-8") from exc
    try:
        parsed = tomllib.loads(text) if text.strip() else {}
    except tomllib.TOMLDecodeError as exc:
        raise OrchestratorPolicyError("Codex config is malformed TOML") from exc
    agents = parsed.get("agents")
    if agents is not None and not isinstance(agents, dict):
        raise OrchestratorPolicyError("Codex agents config must be a table")

    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == "[agents]"]
    if len(starts) > 1:
        raise OrchestratorPolicyError("Codex config contains duplicate [agents] tables")
    native_reset = _native_codex_isolation(parsed)
    if (
        native_reset is None
        and bool(starts)
        and isinstance(agents, dict)
        and agents.get("enabled") is True
    ):
        raise OrchestratorPolicyError(
            "Codex native capacity differs from managed policy; "
            "refusing to change existing provider capacity during quality rollout"
        )
    if native_reset is not None:
        if not starts or native_reset is False:
            raise OrchestratorPolicyError(
                "Codex native reset lacks exact peer-message isolation; "
                "refusing to overwrite it with older orchestrator policy"
            )
        return raw
    required = {
        "max_concurrent_threads_per_session": "max_concurrent_threads_per_session = 1",
        "enabled": "enabled = false",
    }
    if not starts:
        if agents is not None:
            raise OrchestratorPolicyError(
                "Codex agents config must use one explicit [agents] table"
            )
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(
            [
                "[agents]",
                required["max_concurrent_threads_per_session"],
                required["enabled"],
            ]
        )
        return ("\n".join(lines).rstrip() + "\n").encode("utf-8")

    start = starts[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _TOML_TABLE_RE.match(lines[index]):
            end = index
            break

    seen: set[str] = set()
    for index in range(start + 1, end):
        match = _TOML_AGENT_KEY_RE.match(lines[index])
        if not match:
            continue
        key = match.group("key")
        if key in seen:
            raise OrchestratorPolicyError(f"Codex agents config duplicates {key}")
        seen.add(key)
        lines[index] = match.group("indent") + required[key]

    missing = [
        required[key]
        for key in ("max_concurrent_threads_per_session", "enabled")
        if key not in seen
    ]
    if missing:
        lines[end:end] = missing
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _render_codex_hooks(raw: bytes, guard: Path) -> bytes:
    value = _json_object(raw, "Codex hooks")
    value.setdefault(
        "description",
        "User lifecycle hooks with Mastermind asynchronous CI-wait enforcement.",
    )
    hooks = value.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise OrchestratorPolicyError("Codex hooks must be an object")
    rows = _remove_managed_hook(hooks.get("PreToolUse"))
    rows.append(
        _hook_row(
            "^Bash$",
            f'python3 "{guard}"',
            "Keeping Mastermind CI waits asynchronous",
        )
    )
    hooks["PreToolUse"] = rows
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _paths(home: Path) -> dict[str, Path]:
    home = home.expanduser().resolve()
    paths = {
        "codex_doc": home / ".codex" / "AGENTS.md",
        "claude_doc": home / ".claude" / "CLAUDE.md",
        "codex_hooks": home / ".codex" / "hooks.json",
        "codex_config": home / ".codex" / "config.toml",
        "claude_settings": home / ".claude" / "settings.json",
        "codex_guard": home / ".codex" / "hooks" / "mastermind_fabric_routing_guard.py",
        "claude_guard": home / ".claude" / "hooks" / "mastermind_fabric_routing_guard.py",
    }

    for provider, directory in (("codex", ".agents"), ("claude", ".claude")):
        for index, relative in enumerate(ROLE_SHA256):
            paths[f"{provider}_role_{index}"] = home / directory / "skills" / ROLE_PACKAGE / relative
    paths["claude_fabric_skill"] = (home / ".claude" / "skills" /
                                    CLAUDE_FABRIC_SKILL_PACKAGE / "SKILL.md")
    paths["codex_fabric_skill"] = (home / ".codex" / "skills" /
                                   CODEX_FABRIC_SKILL_PACKAGE / "SKILL.md")
    return paths


def _canonical_guard(source: Path | None = None) -> bytes:
    path = source or Path(__file__).with_name("provider_orchestrator_guard.py")
    return _regular_bytes(path)


def _canonical_role_files() -> dict[str, bytes]:
    """Read a fixed reviewed instruction closure, never discover or select roles.

    Presence/digest is installation evidence only. The existing launch/capability
    owner must separately bind and attest one actual role for each Attempt.
    """
    source_root = Path(__file__).resolve().parents[2]
    root = source_root / "skills" / ROLE_PACKAGE
    rows: dict[str, bytes] = {}
    for relative, expected in ROLE_SHA256.items():
        path = root / relative
        _preflight_destination(path, source_root)
        payload = _regular_bytes(path)
        if len(payload) > 8192 or _sha256(payload) != expected:
            raise OrchestratorPolicyError("orchestration role source digest mismatch")
        rows[relative] = payload
    return rows


def _canonical_claude_fabric_skill() -> bytes:
    """Pin the audited invocation instructions, not an account or tool entitlement."""
    source_root = Path(__file__).resolve().parents[2]
    path = source_root / "skills" / CLAUDE_FABRIC_SKILL_PACKAGE / "SKILL.md"
    _preflight_destination(path, source_root)
    payload = _regular_bytes(path)
    blob = hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()
    if not 0 < len(payload) <= 8192 or blob != CLAUDE_FABRIC_SKILL_BLOB_SHA:
        raise OrchestratorPolicyError("Claude Fabric Skill source digest mismatch")
    return payload


def _canonical_codex_fabric_skill() -> bytes:
    """The existing M2 Codex skill, with a reviewed operator-tool quickstart."""
    root = Path(__file__).resolve().parents[2]
    source = root / "skills" / CODEX_FABRIC_SKILL_PACKAGE / "SKILL.md"
    _preflight_destination(source, root)
    payload = _regular_bytes(source)
    blob = hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()
    if not 0 < len(payload) <= 24576 or blob != CODEX_FABRIC_SKILL_BLOB_SHA:
        raise OrchestratorPolicyError("Codex Fabric Skill source digest mismatch")
    return payload


def _refuse_existing_claude_native_limit_reset(raw: bytes) -> None:
    """Do not silently downshift incumbent Claude native capacity.

    Quality instruction installation does not authorize a capacity change.
    Existing non-default caps require a separately accepted release.
    """
    obj = _json_object(raw, "Claude settings")
    env = obj.get("env", {})
    if not isinstance(env, dict):
        raise OrchestratorPolicyError("Claude env must be an object")
    expected = {
        "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "2",
        "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
    }
    if any(k in env and env[k] != v for k, v in expected.items()):
        raise OrchestratorPolicyError(
            "Claude native limit differs from managed policy; "
            "refusing to change existing provider capacity during quality rollout"
        )


def apply_policy(home: Path, *, guard_source: Path | None = None) -> dict[str, object]:
    resolved_home = Path(home).expanduser().resolve()
    paths = _paths(resolved_home)
    guard = _canonical_guard(guard_source)
    roles = _canonical_role_files()
    claude_fabric_skill = _canonical_claude_fabric_skill()
    _preflight_destination(paths["claude_settings"], resolved_home)
    _refuse_existing_claude_native_limit_reset(
        _regular_bytes(paths["claude_settings"], missing=b"{}\n")
    )

    # Reject known unsafe path shapes before any managed file can change. Unexpected
    # I/O failure can still interrupt a multi-file apply and is handled separately.
    for target in paths.values():
        _preflight_destination(target, resolved_home)

    codex_doc = _regular_bytes(paths["codex_doc"], missing=b"").decode("utf-8")
    claude_doc = _regular_bytes(paths["claude_doc"], missing=b"").decode("utf-8")
    claude_settings = _regular_bytes(paths["claude_settings"], missing=b"{}\n")
    codex_hooks = _regular_bytes(paths["codex_hooks"], missing=b"{}\n")
    codex_config = _regular_bytes(paths["codex_config"], missing=b"")

    # Validate every render before the first mutation so malformed peer config
    # cannot leave a half-applied provider pair.
    rendered = {
        "codex_doc": _managed_text(codex_doc).encode("utf-8"),
        "claude_doc": _managed_text(claude_doc).encode("utf-8"),
        "claude_settings": _render_claude_settings(
            claude_settings, paths["claude_guard"]
        ),
        "codex_hooks": _render_codex_hooks(codex_hooks, paths["codex_guard"]),
        "codex_config": _render_codex_config(codex_config),
    }

    operations = [
        ("codex_guard", guard),
        ("claude_guard", guard),
        ("codex_doc", rendered["codex_doc"]),
        ("claude_doc", rendered["claude_doc"]),
        ("claude_settings", rendered["claude_settings"]),
        ("codex_hooks", rendered["codex_hooks"]),
        ("codex_config", rendered["codex_config"]),
    ]
    # Supporting references stay discoverable/on-demand. Only the shared core is
    # embedded into the managed parent block; no role body is concatenated there.
    role_operations = [
        (f"{provider}_role_{index}", roles[relative])
        for provider in ("codex", "claude")
        for index, relative in enumerate(ROLE_SHA256)
    ]
    operations = operations[:2] + role_operations + [("claude_fabric_skill", claude_fabric_skill)] + operations[2:]
    modified: list[str] = []
    try:
        for key, payload in operations:
            if _atomic_write(paths[key], payload):
                modified.append(str(paths[key]))
    except OrchestratorPolicyError as exc:
        if modified:
            try:
                observed = verify_policy(home, guard_source=guard_source)
                verify_issues = tuple(str(item) for item in observed.get("issues", ()))
            except Exception:
                verify_issues = ("verify_after_partial_apply_failed",)
            raise OrchestratorPolicyApplyIncomplete(
                "provider orchestrator policy apply stopped after a partial write; "
                "do not switch carriers or blindly replay. Verify this same home first.",
                modified_files=modified,
                verify_issues=verify_issues,
            ) from exc
        raise

    return verify_policy(home, guard_source=guard_source)


def _managed_hook_count(raw: bytes, guard: Path, *, claude: bool) -> int:
    value = _json_object(raw, "provider hooks")
    hooks = value.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    rows = hooks.get("PreToolUse")
    if not isinstance(rows, list):
        return 0
    expected_matcher = "Agent|Task|Bash" if claude else "^Bash$"
    expected_command = f'python3 "{guard}"'
    count = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("matcher") != expected_matcher:
            continue
        nested = row.get("hooks")
        if not isinstance(nested, list):
            continue
        count += sum(
            1
            for hook in nested
            if (
                isinstance(hook, dict)
                and hook.get("type") == "command"
                and hook.get("command") == expected_command
                and hook.get("timeout") == 10
                and hook.get("async") in (None, False)
            )
        )
    return count


def _managed_hook_reference_count(raw: bytes) -> int:
    value = _json_object(raw, "provider hooks")
    hooks = value.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    rows = hooks.get("PreToolUse")
    if not isinstance(rows, list):
        return 0
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        nested = row.get("hooks")
        if not isinstance(nested, list):
            continue
        count += sum(
            1
            for hook in nested
            if (
                isinstance(hook, dict)
                and "mastermind_fabric_routing_guard.py"
                in str(hook.get("command") or "")
            )
        )
    return count


def verify_policy(home: Path, *, guard_source: Path | None = None, provider: str = "all") -> dict[str, object]:
    if provider not in ("all", "codex", "claude"):
        raise OrchestratorPolicyError("provider must be all, codex or claude")
    selected = ("codex", "claude") if provider == "all" else (provider,)
    paths = _paths(home)
    canonical = _canonical_guard(guard_source)
    issues: list[str] = []
    roles = _canonical_role_files()
    claude_fabric_skill = _canonical_claude_fabric_skill() if "claude" in selected else None
    for enrolled_provider in selected:
        for index, relative in enumerate(ROLE_SHA256):
            key = f"{enrolled_provider}_role_{index}"
            try:
                _preflight_destination(paths[key], Path(home).expanduser().resolve())
                installed = _regular_bytes(paths[key])
            except OrchestratorPolicyError:
                issues.append(f"{key}.missing_or_unsafe")
                continue
            if installed != roles[relative]:
                issues.append(f"{key}.digest")


    if "claude" in selected:
        try:
            _preflight_destination(paths["claude_fabric_skill"], Path(home).expanduser().resolve())
            installed_skill = _regular_bytes(paths["claude_fabric_skill"])
        except OrchestratorPolicyError:
            issues.append("claude_fabric_skill.missing_or_unsafe")
        else:
            if installed_skill != claude_fabric_skill:
                issues.append("claude_fabric_skill.digest")

    for name in (f"{p}_guard" for p in selected):
        try:
            installed = _regular_bytes(paths[name])
        except OrchestratorPolicyError:
            issues.append(f"{name}.missing")
            continue
        if installed != canonical:
            issues.append(f"{name}.digest")

    for name in (f"{p}_doc" for p in selected):
        try:
            text = _regular_bytes(paths[name]).decode("utf-8")
        except (OrchestratorPolicyError, UnicodeError):
            issues.append(f"{name}.missing_or_invalid")
            continue
        if (
            text.count(BEGIN) != 1
            or text.count(END) != 1
            or _managed_text(text) != text
        ):
            issues.append(f"{name}.managed_block")

    if "claude" in selected:
        try:
            claude_raw = _regular_bytes(paths["claude_settings"])
            claude_value = _json_object(claude_raw, "Claude settings")
            claude_env = claude_value.get("env")
            if not isinstance(claude_env, dict):
                issues.append("claude_settings.env")
            else:
                if claude_env.get("CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS") != "2":
                    issues.append("claude_settings.max_concurrent_subagents")
                if claude_env.get("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH") != "1":
                    issues.append("claude_settings.max_subagent_spawn_depth")
            if (
                _managed_hook_count(claude_raw, paths["claude_guard"], claude=True) != 1
                or _managed_hook_reference_count(claude_raw) != 1
            ):
                issues.append("claude_settings.pretool")
        except OrchestratorPolicyError:
            issues.append("claude_settings.missing")

    if "codex" in selected:
        try:
            codex_raw = _regular_bytes(paths["codex_hooks"])
            if (
                _managed_hook_count(codex_raw, paths["codex_guard"], claude=False) != 1
                or _managed_hook_reference_count(codex_raw) != 1
            ):
                issues.append("codex_hooks.pretool")
        except OrchestratorPolicyError:
            issues.append("codex_hooks.missing")

        try:
            codex_config_raw = _regular_bytes(paths["codex_config"])
            try:
                codex_config = tomllib.loads(codex_config_raw.decode("utf-8"))
            except (UnicodeError, tomllib.TOMLDecodeError) as exc:
                raise OrchestratorPolicyError("Codex config is malformed") from exc
            codex_agents = codex_config.get("agents")
            if not isinstance(codex_agents, dict):
                issues.append("codex_config.agents")
            else:
                native_reset = _native_codex_isolation(codex_config)
                if native_reset is False:
                    issues.append("codex_config.native_message_isolation")
                if native_reset is not True:
                    if codex_agents.get("enabled") is not False:
                        issues.append("codex_config.agents_enabled")
                    if codex_agents.get("max_concurrent_threads_per_session") != 1:
                        issues.append("codex_config.max_concurrent_threads")
        except OrchestratorPolicyError:
            issues.append("codex_config.missing_or_invalid")

    return {
        "state": "READY" if not issues else "DRIFT",
        "home": str(Path(home).expanduser().resolve()),
        "issues": issues,
        "guard_sha256": _sha256(canonical),
        "role_source_sha256": dict(ROLE_SHA256),
        "claude_fabric_skill_blob_sha": CLAUDE_FABRIC_SKILL_BLOB_SHA if "claude" in selected else None,
        "session_loading_proven": False,
        "runtime_admission_proven": False,
        "managed_files": {
            key: str(value)
            for key, value in paths.items()
            if any(key.startswith(p + "_") for p in selected)
        },
        **({"provider_scope": provider} if provider != "all" else {}),
        "credentials_read": False,
        "permissions_changed": False,
        "lifecycle_created": False,
    }


def verify_provider_policy(
    home: Path, provider: str, *, guard_source: Path | None = None
) -> dict[str, object]:
    """Use the canonical verifier with one explicit provider scope."""
    return verify_policy(home, guard_source=guard_source, provider=provider)


def apply_provider_policy(
    home: Path, provider: str, *, guard_source: Path | None = None
) -> dict[str, object]:
    """Install through the one canonical source owner into one provider scope.

    This is an optional subset of apply_policy, not a separate override plane.
    It never reads/changes native capacity or user files of the other provider.
    """
    if provider not in ("codex", "claude"):
        raise OrchestratorPolicyError("provider must be codex or claude")
    resolved_home = Path(home).expanduser().resolve()
    paths = _paths(resolved_home)
    selected = {k: path for k, path in paths.items() if k.startswith(provider + "_")}
    guard = _canonical_guard(guard_source)
    roles = _canonical_role_files()
    claude_fabric_skill = _canonical_claude_fabric_skill() if provider == "claude" else None

    # All destination and exact-config preconditions before a single write.
    for path in selected.values():
        _preflight_destination(path, resolved_home)
    if provider == "claude":
        original_settings = _regular_bytes(paths["claude_settings"], missing=b"{}\n")
        _refuse_existing_claude_native_limit_reset(original_settings)
        original_doc = _regular_bytes(paths["claude_doc"], missing=b"").decode("utf-8")
        operations = [
            ("claude_guard", guard),
            ("claude_doc", _managed_text(original_doc).encode("utf-8")),
            (
                "claude_settings",
                _render_claude_settings(original_settings, paths["claude_guard"]),
            ),
        ]
    else:
        original_doc = _regular_bytes(paths["codex_doc"], missing=b"").decode("utf-8")
        original_hooks = _regular_bytes(paths["codex_hooks"], missing=b"{}\n")
        original_config = _regular_bytes(paths["codex_config"], missing=b"")
        operations = [
            ("codex_guard", guard),
            ("codex_doc", _managed_text(original_doc).encode("utf-8")),
            ("codex_hooks", _render_codex_hooks(original_hooks, paths["codex_guard"])),
            ("codex_config", _render_codex_config(original_config)),
        ]
    role_operations = [
        (f"{provider}_role_{index}", roles[relative])
        for index, relative in enumerate(ROLE_SHA256)
    ]
    operations = operations[:1] + role_operations + ([("claude_fabric_skill", claude_fabric_skill)] if provider == "claude" else []) + operations[1:]
    modified: list[str] = []
    try:
        for key, payload in operations:
            if _atomic_write(paths[key], payload):
                modified.append(str(paths[key]))
    except OrchestratorPolicyError as exc:
        if modified:
            try:
                observed = verify_provider_policy(
                    resolved_home, provider, guard_source=guard_source
                )
                verify_issues = tuple(str(item) for item in observed.get("issues", ()))
            except Exception:
                verify_issues = ("verify_after_partial_apply_failed",)
            raise OrchestratorPolicyApplyIncomplete(
                "provider-scoped policy apply stopped after partial write; "
                "do not switch carrier or blindly replay; verify this same home",
                modified_files=modified,
                verify_issues=verify_issues,
            ) from exc
        raise
    return verify_provider_policy(
        resolved_home, provider, guard_source=guard_source
    )



def _render_claude_fabric_entry_doc(raw: bytes) -> bytes:
    """Add one discoverable pointer without changing other Claude instructions."""
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise OrchestratorPolicyError("Claude instructions are not UTF-8") from exc
    if text.count(FABRIC_ENTRY_BEGIN) != text.count(FABRIC_ENTRY_END) or text.count(FABRIC_ENTRY_BEGIN) > 1:
        raise OrchestratorPolicyError("Claude Fabric entrypoint markers ambiguous")
    # A successfully installed full managed policy already contains this entry.
    if text.count(BEGIN) == text.count(END) == 1:
        block = text[text.index(BEGIN):text.index(END) + len(END)]
        if "mastermind-claude-fabric-delegation/SKILL.md" in block and FABRIC_ENTRY_BEGIN not in text:
            return raw
    if FABRIC_ENTRY_BEGIN in text:
        start = text.index(FABRIC_ENTRY_BEGIN)
        end = text.index(FABRIC_ENTRY_END, start) + len(FABRIC_ENTRY_END)
        updated = text[:start] + FABRIC_ENTRY_BODY.rstrip() + text[end:]
        return (updated.rstrip() + "\n").encode("utf-8")
    return ((text.rstrip() + "\n\n") if text.strip() else "").encode("utf-8") + FABRIC_ENTRY_BODY.encode("utf-8")


def verify_claude_fabric_entrypoint(home: Path) -> dict[str, object]:
    """Verify only the delegated M2 Claude guide, not native capacity policy."""
    paths = _paths(home)
    expected_skill = _canonical_claude_fabric_skill()
    issues: list[str] = []
    try:
        _preflight_destination(paths["claude_fabric_skill"], Path(home).expanduser().resolve())
        actual_skill = _regular_bytes(paths["claude_fabric_skill"])
    except OrchestratorPolicyError:
        issues.append("claude_fabric_skill.missing_or_unsafe")
    else:
        if actual_skill != expected_skill:
            issues.append("claude_fabric_skill.digest")
    try:
        raw_doc = _regular_bytes(paths["claude_doc"])
        doc = raw_doc.decode("utf-8")
        has_short = doc.count(FABRIC_ENTRY_BEGIN) == doc.count(FABRIC_ENTRY_END) == 1
        has_full = doc.count(BEGIN) == doc.count(END) == 1
        if has_full:
            block = doc[doc.index(BEGIN):doc.index(END) + len(END)]
            has_full = "mastermind-claude-fabric-delegation/SKILL.md" in block
        if not has_short and not has_full:
            issues.append("claude_fabric_entrypoint.missing")
    except (OrchestratorPolicyError, UnicodeError, ValueError):
        issues.append("claude_fabric_entrypoint.unreadable")
    return {
        "state": "READY" if not issues else "DRIFT",
        "provider_scope": "claude-fabric",
        "home": str(Path(home).expanduser().resolve()),
        "issues": issues,
        "claude_fabric_skill_blob_sha": CLAUDE_FABRIC_SKILL_BLOB_SHA,
        "session_loading_proven": False,
        "runtime_admission_proven": False,
        "native_capacity_modified": False,
        "provider_settings_modified": False,
        "credentials_read": False,
    }


def apply_claude_fabric_entrypoint(home: Path) -> dict[str, object]:
    """Install just the guide through the incumbent user-policy file owner.

    In particular, do NOT normalize an existing native Claude concurrency of
    twelve (or any other non-default value) to the older full-policy limit two.
    """
    resolved = Path(home).expanduser().resolve()
    paths = _paths(resolved)
    for key in ("claude_doc", "claude_fabric_skill"):
        _preflight_destination(paths[key], resolved)
    skill = _canonical_claude_fabric_skill()
    original_doc = _regular_bytes(paths["claude_doc"], missing=b"")
    new_doc = _render_claude_fabric_entry_doc(original_doc)
    modified: list[str] = []
    # Install skill before publishing the doc pointer; no identity/credential changes.
    try:
        for key, payload in (("claude_fabric_skill", skill), ("claude_doc", new_doc)):
            if _atomic_write(paths[key], payload):
                modified.append(str(paths[key]))
    except OrchestratorPolicyError as exc:
        if modified:
            try:
                issues = verify_claude_fabric_entrypoint(resolved)["issues"]
            except Exception:
                issues = ["verify_after_partial_apply_failed"]
            raise OrchestratorPolicyApplyIncomplete(
                "Claude Fabric entrypoint install partial; verify original home before retry",
                modified_files=modified, verify_issues=issues,
            ) from exc
        raise
    return verify_claude_fabric_entrypoint(resolved)



def _render_codex_fabric_entry_doc(raw: bytes) -> bytes:
    """Preserve an existing Codex Fabric instruction pointer without duplication."""
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise OrchestratorPolicyError("Codex instructions are not UTF-8") from exc
    if (text.count(CODEX_FABRIC_ENTRY_BEGIN) != text.count(CODEX_FABRIC_ENTRY_END)
            or text.count(CODEX_FABRIC_ENTRY_BEGIN) > 1):
        raise OrchestratorPolicyError("Codex Fabric entrypoint markers ambiguous")
    if CODEX_FABRIC_ENTRY_BEGIN in text:
        start = text.index(CODEX_FABRIC_ENTRY_BEGIN)
        end = text.index(CODEX_FABRIC_ENTRY_END, start) + len(CODEX_FABRIC_ENTRY_END)
        updated = text[:start] + CODEX_FABRIC_ENTRY_BODY.rstrip() + text[end:]
        return (updated.rstrip() + "\n").encode("utf-8")
    # The incumbent M2 AGENTS.md already names the exact installed skill.
    if "~/.codex/skills/mastermind-fabric-delegate/SKILL.md" in text:
        return raw
    return ((text.rstrip() + "\n\n") if text.strip() else "").encode("utf-8") + CODEX_FABRIC_ENTRY_BODY.encode("utf-8")


def verify_codex_fabric_entrypoint(home: Path) -> dict[str, object]:
    """Read back only this guide; never infer provider admission from files."""
    paths = _paths(home)
    expected = _canonical_codex_fabric_skill()
    issues: list[str] = []
    try:
        _preflight_destination(paths["codex_fabric_skill"], Path(home).expanduser().resolve())
        installed = _regular_bytes(paths["codex_fabric_skill"])
    except OrchestratorPolicyError:
        issues.append("codex_fabric_skill.missing_or_unsafe")
    else:
        if installed != expected:
            issues.append("codex_fabric_skill.digest")
    try:
        doc = _regular_bytes(paths["codex_doc"]).decode("utf-8")
        if (doc.count(CODEX_FABRIC_ENTRY_BEGIN) != doc.count(CODEX_FABRIC_ENTRY_END)
                or doc.count(CODEX_FABRIC_ENTRY_BEGIN) > 1
                or "~/.codex/skills/mastermind-fabric-delegate/SKILL.md" not in doc):
            issues.append("codex_fabric_entrypoint.missing_or_ambiguous")
    except (OrchestratorPolicyError, UnicodeError):
        issues.append("codex_fabric_entrypoint.unreadable")
    return {
        "state": "READY" if not issues else "DRIFT",
        "provider_scope": "codex-fabric",
        "home": str(Path(home).expanduser().resolve()),
        "issues": issues,
        "codex_fabric_skill_blob_sha": CODEX_FABRIC_SKILL_BLOB_SHA,
        "session_loading_proven": False, "runtime_admission_proven": False,
        "native_capacity_modified": False, "provider_settings_modified": False,
        "credentials_read": False,
    }


def apply_codex_fabric_entrypoint(home: Path) -> dict[str, object]:
    """Upgrade only the existing M2 Codex Fabric skill and optional discovery pointer.

    Legacy preimage is exact SHA-bound; unknown content is never overwritten.
    Keep the user's native agent 32/33 configuration, hooks, models and MCP untouched.
    """
    resolved = Path(home).expanduser().resolve()
    paths = _paths(resolved)
    for key in ("codex_doc", "codex_fabric_skill"):
        _preflight_destination(paths[key], resolved)
    candidate = _canonical_codex_fabric_skill()
    existing = _regular_bytes(paths["codex_fabric_skill"], missing=b"")
    if existing and existing != candidate and _sha256(existing) != CODEX_FABRIC_LEGACY_SHA256:
        raise OrchestratorPolicyError("Codex Fabric installed Skill changed; refusing replacement")
    original_doc = _regular_bytes(paths["codex_doc"], missing=b"")
    updated_doc = _render_codex_fabric_entry_doc(original_doc)
    modified: list[str] = []
    try:
        for key, payload in (("codex_fabric_skill", candidate), ("codex_doc", updated_doc)):
            # Re-read exact preimage before a change; do not clobber concurrent edits.
            current = _regular_bytes(paths[key], missing=b"")
            expected = existing if key == "codex_fabric_skill" else original_doc
            if current != expected:
                raise OrchestratorPolicyError("Codex Fabric install source drift; reconcile current home")
            if _atomic_write(paths[key], payload):
                modified.append(str(paths[key]))
    except OrchestratorPolicyError as exc:
        if modified:
            try:
                issues = verify_codex_fabric_entrypoint(resolved)["issues"]
            except Exception:
                issues = ["verify_after_partial_apply_failed"]
            raise OrchestratorPolicyApplyIncomplete(
                "Codex Fabric install partially applied; verify the same home first",
                modified_files=modified, verify_issues=issues,
            ) from exc
        raise
    return verify_codex_fabric_entrypoint(resolved)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify", "apply"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--guard-source", type=Path)
    parser.add_argument("--provider", choices=("all", "codex", "claude", "claude-fabric", "codex-fabric"), default="all")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.provider == "codex-fabric":
            result = (apply_codex_fabric_entrypoint(args.home) if args.mode == "apply"
                      else verify_codex_fabric_entrypoint(args.home))
        elif args.provider == "claude-fabric":
            result = (apply_claude_fabric_entrypoint(args.home) if args.mode == "apply"
                      else verify_claude_fabric_entrypoint(args.home))
        elif args.provider == "all":
            result = (
                apply_policy(args.home, guard_source=args.guard_source)
                if args.mode == "apply"
                else verify_policy(args.home, guard_source=args.guard_source)
            )
        else:
            result = (
                apply_provider_policy(args.home, args.provider, guard_source=args.guard_source)
                if args.mode == "apply"
                else verify_provider_policy(args.home, args.provider, guard_source=args.guard_source)
            )
    except OrchestratorPolicyApplyIncomplete as exc:
        print(
            json.dumps(
                {
                    "state": "APPLY_INCOMPLETE_VERIFY_REQUIRED",
                    "detail": str(exc),
                    "modified_files": list(exc.modified_files),
                    "verify_issues": list(exc.verify_issues),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 70
    except (OrchestratorPolicyError, UnicodeError, OSError) as exc:
        print(json.dumps({"state": "REFUSED", "detail": str(exc)}, sort_keys=True))
        return 65
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
