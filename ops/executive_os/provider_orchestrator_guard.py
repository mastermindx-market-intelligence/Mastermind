#!/usr/bin/env python3
"""User-scope Mastermind provider guard.

This is a deployment artifact for local Codex/Claude CEO/orchestrator sessions.
It creates no lifecycle, queue, merge, retry, watcher, or source-custody authority.
It enforces bounded provider-edge anti-burn invariants inside Mastermind workspaces:
asynchronous CI waits, stable Fabric root accounting, and the standing native-Claude
child routing fence.

WO-11 (MMOS V1, CRITICAL): for sessions the placement owner has armed onto the
shared placement path, every paid launch and native delegation must be covered
by the CURRENT broker-issued ExecutionBinding.v1, validated against the
owner-issued placement receipt over the authenticated owner channel. Refusal
classes: missing binding, stale fence, provider substitution after reservation,
unaccounted descendant. There is no independent signing authority — the binding
is only an assignment of opaque references, trusted exactly as far as it matches
the owner's current lease. The gate fences the launches it observes through this
provider hook; it does not claim to fence arbitrary processes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import NoReturn


MIN_WATCH_INTERVAL_S = 60
RECOMMENDED_WATCH_INTERVAL_S = 150
POLL_COOLDOWN_S = 300

ROUTE_RE = re.compile(r"(?mi)^\s*ROUTE\s*:\s*(orchestration|audit|review|auditor)\s*$")
WHY_RE = re.compile(r"(?mi)^\s*WHY OPUS\s*:\s*(\S.{19,})$")
READ_ONLY_RE = re.compile(r"(?mi)^\s*(?:MODE|SCOPE)\s*:\s*READ[_ -]?ONLY\s*$")

HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
    re.S | re.M,
)


def strip_heredocs(command: str) -> str:
    previous = None
    output = command
    while previous != output:
        previous = output
        output = HEREDOC_RE.sub("<<HEREDOC", output)
    return output


CMD_POS = r"(?:^|[;&|\n(]|\b(?:do|then|else)\s)\s*"
CI_WATCH_RE = re.compile(
    CMD_POS
    + r"(?P<call>gh\s+(?:run\s+watch\b[^;&|\n]*"
      r"|run\s+view\b[^;&|\n]*--watch\b[^;&|\n]*"
      r"|pr\s+checks\b[^;&|\n]*--watch\b[^;&|\n]*))",
    re.I,
)
CI_READ_RE = re.compile(
    CMD_POS
    + r"gh\s+(?:pr\s+(?:view|checks|status)\b"
      r"|run\s+(?:view|list|watch)\b"
      r"|api\b[^;&|\n]*(?:actions/runs|check-runs))",
    re.I,
)
INTERVAL_RE = re.compile(r"(?i)(?:--interval|(?<!\w)-i)[=\s]+(\d+)")
SLEEP_RE = re.compile(r"(?i)\bsleep\s+(\d+)\b")
DO_DONE_RE = re.compile(r"(?:^|[;&|\n)])\s*do\b(.*?)\bdone\b", re.S | re.I)

# Cooldown only direct CI-status reads. General `gh pr view` / `gh pr status`
# stays available for post-mutation/effect reconciliation; a rate guard must never
# prevent the readback needed to prove a write's outcome.
PR_READ_RE = re.compile(
    CMD_POS + r"gh\s+pr\s+checks\s+(?P<id>\d+)\b",
    re.I,
)
RUN_READ_RE = re.compile(
    CMD_POS + r"gh\s+run\s+(?:view|watch)\s+(?P<id>\d+)\b",
    re.I,
)
API_RUN_READ_RE = re.compile(
    CMD_POS + r"gh\s+api\b[^;&|\n]*/actions/runs/(?P<id>\d+)\b",
    re.I,
)
REPO_ARG_RE = re.compile(
    r"(?:^|\s)(?:-R|--repo)(?:=|\s+)(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
    re.I,
)

_SUB_LAUNCH_MODE = (
    r"(?:grok|qwen|minimax|glm|minimax-codex|glm-codex|go-codex|"
    r"go-claude|oc-free|cursor|__glm_vision)"
)
_REMOTE_LAUNCH_MODE = (
    r"(?:glm|glm-codex|minimax|minimax-codex|grok|cursor|qwen|go-codex|"
    r"codex-native|claude-native|oc-free)"
)
_SLOT_POOL = (
    r"(?:grok|minimax|glm|glm-frontier|bailian|cursor|go|ocfree|"
    r"codex-native|claude-native)"
)
FABRIC_LAUNCH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"(?:[A-Za-z0-9_./-]+/)?pool\s+(?:run|remote)\b"
    r"|(?:[A-Za-z0-9_./-]+/)?sub\.sh\s+" + _SUB_LAUNCH_MODE + r"\b"
    r"|(?:[A-Za-z0-9_./-]+/)?remote_sub\.sh\s+\S+\s+"
    + _REMOTE_LAUNCH_MODE
    + r"\b"
    r"|(?:python(?:3(?:\.\d+)?)?\s+)?(?:[A-Za-z0-9_./-]+/)?slot\.py\s+"
    + _SLOT_POOL
    + r"\b"
    r")",
    re.I,
)
_FABRIC_IDENTITY_NAMES = (
    "POOL_ORCHESTRATOR_ID",
    "POOL_PARENT_RUN_ID",
    "POOL_TASK_CLASS",
)

# --- WO-11 shared-placement ExecutionBinding gate (engine independent) --------

#: Scoped arming (OQ-7): the placement owner sets these when the session's
#: work is claimed on the shared path (WO-14 claim -> binding at
#: claim_payload -> projection into the session environment). Sessions not
#: on the shared path keep the legacy identity checks unchanged.
SHARED_PLACEMENT_ENV = "MASTERMIND_SHARED_PLACEMENT"
#: The broker-issued ExecutionBinding.v1 (JSON), projected into the session
#: environment by the authenticated owner at claim. Never self-declared
#: authority: the guard trusts it only while it matches the owner receipt.
BINDING_ENV = "POOL_EXECUTION_BINDING"
#: Owner-written current-lease receipt (JSON file path). This is the
#: authenticated owner channel for the guard: no independent signing
#: authority exists, so the binding is validated for consistency against
#: this owner-issued projection of the CURRENT lease (attempt, fence,
#: child identity, lease state, expiry).
PLACEMENT_RECEIPT_ENV = "MASTERMIND_PLACEMENT_RECEIPT"
PLACEMENT_RECEIPT_SCHEMA = "mastermind.placement_receipt/v1"
EXECUTION_BINDING_SCHEMA = "ExecutionBinding.v1"
#: Fields that make the presented binding BE the owner's current fenced
#: assignment: the (root, immediate parent, logical child) identity triple,
#: the admitted request digest, and the fenced attempt.
_BINDING_IDENTITY_FIELDS = (
    "root_run_ref",
    "immediate_parent_run_ref",
    "logical_child_key",
    "request_digest",
    "attempt_ref",
)
_BINDING_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

# Provider/pool token of each supported paid-launch wrapper shape.
_POOL_RUN_RE = re.compile(r"(?is)\bpool\s+run\s+([A-Za-z0-9_.-]+)")
_POOL_REMOTE_RE = re.compile(
    r"(?is)\bpool\s+remote\s+([A-Za-z0-9_.-]+)\s+([A-Za-z0-9_.-]+)")
_SUB_SH_RE = re.compile(r"(?is)\bsub\.sh\s+([A-Za-z0-9_.-]+)")
_REMOTE_SUB_SH_RE = re.compile(
    r"(?is)\bremote_sub\.sh\s+([A-Za-z0-9_.-]+)\s+([A-Za-z0-9_.-]+)")
_SLOT_RE = re.compile(r"(?is)\bslot\.py\s+([A-Za-z0-9_.-]+)")


def family(model: str) -> str:
    lowered = (model or "").strip().lower()
    for name in ("fable", "opus", "sonnet", "haiku"):
        if name in lowered:
            return name
    return lowered


def _emit(payload: dict[str, object]) -> NoReturn:
    print(json.dumps({"hookSpecificOutput": payload}, sort_keys=True))
    raise SystemExit(0)


def deny(reason: str) -> NoReturn:
    _emit(
        {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    )


def allow_context(context: str) -> None:
    _emit({"hookEventName": "PreToolUse", "additionalContext": context})


def _scope_roots(home: Path) -> tuple[Path, ...]:
    roots = [
        home / ".mastermind" / "worktrees",
        home / "lanes",
        home / "terminals",
        home / "Documents" / "Cluade",
        home / "Documents" / "GitHub",
        home / "Projects" / "MastermindX" / "repos",
        Path("/Volumes/Mastermind/agent-workspaces"),
    ]
    extra = os.environ.get("MASTERMIND_SCOPE_ROOTS", "")
    for raw in extra.split(os.pathsep):
        if raw.strip():
            roots.append(Path(raw).expanduser())
    return tuple(Path(os.path.realpath(path)) for path in roots)


def is_project_scope(payload: dict[str, object]) -> bool:
    cwd = Path(os.path.realpath(str(payload.get("cwd") or os.getcwd())))
    home = Path(os.path.expanduser("~"))
    for root in _scope_roots(home):
        try:
            cwd.relative_to(root)
            return True
        except ValueError:
            if cwd == root:
                return True
    return False


def _session_scope(payload: dict[str, object]) -> str:
    """Return a stable best-effort provider-session scope for local cooldowns.

    Prefer explicit provider/session identifiers. Fall back to documented/installed
    environment identities, then the long-lived provider parent process. This state is
    only a local anti-poll hint; it is not lifecycle or RuntimeBinding authority.
    """

    for key in (
        "session_id",
        "sessionId",
        "thread_id",
        "threadId",
        "conversation_id",
        "conversationId",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_SESSION_ID"):
        value = os.environ.get(name, "").strip()
        if value:
            return f"{name}:{value}"
    return f"ppid:{os.getppid()}"


def _poll_key(command: str, cwd: str, session_scope: str) -> str | None:
    repo_match = REPO_ARG_RE.search(command)
    scope = repo_match.group("repo").lower() if repo_match else os.path.realpath(cwd)
    for label, regex in (
        ("pr", PR_READ_RE),
        ("run", RUN_READ_RE),
        ("run", API_RUN_READ_RE),
    ):
        match = regex.search(command)
        if match:
            return f"{session_scope}:{label}:{scope}:{match.group('id')}"
    return None


def _poll_state_dir() -> Path:
    uid = getattr(os, "getuid", lambda: 0)()
    return Path(
        os.environ.get(
            "MASTERMIND_CI_POLL_STATE_DIR",
            str(Path(tempfile.gettempdir()) / f"mastermind-ci-poll-{uid}"),
        )
    )


def repeat_poll_reason(key: str, *, now: float | None = None) -> str | None:
    moment = time.time() if now is None else now
    try:
        root = _poll_state_dir()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        path = root / f"{digest}.json"
        last = 0.0
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            last = float(value.get("at") or 0.0) if isinstance(value, dict) else 0.0
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError, OSError):
            last = 0.0
        waited = moment - last
        if 0 < waited < POLL_COOLDOWN_S:
            return (
                f"Mastermind CI wait guard: redundant status read for {key}; the same "
                f"target was read {int(waited)}s ago. Do not wait for the cooldown. "
                "The existing watcher/event is the next observation; immediately "
                "continue another independent authorized project lane."
            )
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps({"at": moment, "key": key}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        return None
    return None


def _command_assignment(command: str, name: str) -> tuple[bool, str]:
    pattern = re.compile(
        rf"(?:^|[\s;&|]){re.escape(name)}="
        rf"(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|]*))"
    )
    match = pattern.search(command)
    if not match:
        return False, ""
    value = next(
        (value for value in match.groups() if value is not None),
        "",
    ).strip()
    # Dynamic shell expansion cannot prove stable identity. A caller should
    # inherit an already-bound value or pass an explicit literal.
    if any(token in value for token in ("$", "`")):
        return True, ""
    return True, value


def _command_or_environment_value(command: str, name: str) -> str:
    # An explicit shell assignment wins over inherited process state, including
    # an explicit empty assignment. This mirrors the environment the launched
    # child will actually receive instead of letting a parent value mask a reset.
    found, value = _command_assignment(command, name)
    if found:
        return value
    return os.environ.get(name, "").strip()


def shared_placement_armed() -> bool:
    """True when this session's paid launches run under the shared placement
    path: the owner armed the scope (per-session, OQ-7 scoped arming) or has
    already projected a binding into the session environment."""
    if os.environ.get(BINDING_ENV, "").strip():
        return True
    return os.environ.get(SHARED_PLACEMENT_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _binding_problems(binding: object, owner: str) -> str:
    """Stdlib-only ExecutionBinding.v1 shape validation. The guard is a
    verbatim-copy deployment artifact and cannot import the shared contracts
    module, so it re-states the binding's structural law locally."""
    if not isinstance(binding, dict):
        return f"{owner}: binding is not a JSON object"
    if str(binding.get("schema") or "") != EXECUTION_BINDING_SCHEMA:
        return f"{owner}: schema must be {EXECUTION_BINDING_SCHEMA}"
    for name in ("root_run_ref", "immediate_parent_run_ref", "logical_child_key"):
        if not str(binding.get(name) or "").strip():
            return f"{owner}: {name} is required"
    if not _BINDING_HEX64_RE.match(str(binding.get("request_digest") or "")):
        return f"{owner}: request_digest must be a 64-char lowercase hex digest"
    for name in ("fence_counter", "assignment_generation"):
        value = binding.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return f"{owner}: {name} must be an integer >= 0"
    return ""


def launch_provider_token(command: str) -> str:
    """The provider/pool token of a matched paid launch (lowercased), or ''.

    Covers every wrapper shape the common launch path recognizes:
    ``pool run <pool>``, ``pool remote <host> <pool>``, ``sub.sh <mode>``,
    ``remote_sub.sh <host> <mode>`` and ``slot.py <pool>`` — the same
    wrappers every engine's paid launch goes through, which is what makes
    the gate engine-independent.
    """
    for regex, group in (
        (_POOL_REMOTE_RE, 2),
        (_REMOTE_SUB_SH_RE, 2),
        (_POOL_RUN_RE, 1),
        (_SUB_SH_RE, 1),
        (_SLOT_RE, 1),
    ):
        match = regex.search(command)
        if match:
            return match.group(group).strip().lower()
    return ""


def _provider_token_matches(token: str, allowed: set[str]) -> bool:
    """Composite launch modes (``glm-codex``, ``codex-native``) match when a
    dash/underscore segment equals a reserved value; a wholly different lane
    (``grok`` vs a ``glm`` reservation) does not."""
    if not token:
        return True
    segments = set(re.split(r"[-_]", token))
    return any(value and (value == token or value in segments) for value in allowed)


def _expected_projection(binding: dict) -> dict[str, str]:
    """POOL_ORCHESTRATOR_ID / POOL_PARENT_RUN_ID are server-derived
    projections of the binding (Rev 4 l.287): children cannot promote,
    re-root or re-parent themselves by changing the environment."""
    root = str(binding.get("original_root_orchestrator_ref") or "").strip()
    if not root:
        root = str(binding.get("root_run_ref") or "").strip()
    return {
        "POOL_ORCHESTRATOR_ID": root,
        "POOL_PARENT_RUN_ID": str(
            binding.get("immediate_parent_run_ref") or ""
        ).strip(),
    }


def validate_execution_binding(
    command: str, launch: "re.Match[str] | None" = None
) -> None:
    """Refuse paid launches/delegations not covered by the CURRENT
    broker-issued ExecutionBinding (WO-11; Rev 4 S3.D l.287-289, S4 steps
    3-4).

    Refusal classes: missing binding, stale fence (the reservation moved,
    was released or expired), provider substitution after reservation, and
    unaccounted descendants (a binding that does not cover this launch's
    child identity). The binding is only an assignment of opaque references
    — never a credential, and there is no independent signing authority:
    it is trusted exactly as far as it matches the authenticated owner's
    current lease receipt. This gate fences the launches it observes
    through the provider hook; it does not fence arbitrary processes.
    """
    raw_binding = os.environ.get(BINDING_ENV, "").strip()
    if not raw_binding:
        deny(
            "Mastermind shared-placement guard: missing binding — this "
            "session is armed for shared placement but carries no "
            f"broker-issued {EXECUTION_BINDING_SCHEMA} ({BINDING_ENV}). No "
            "paid launch may proceed without the placement authority's "
            "current binding; recover through the original operation key, "
            "never by launching locally."
        )
    try:
        binding = json.loads(raw_binding)
    except ValueError:
        deny(
            "Mastermind shared-placement guard: missing binding — "
            f"{BINDING_ENV} is not valid JSON."
        )
    problem = _binding_problems(binding, "shared-placement guard")
    if problem:
        deny(f"Mastermind shared-placement guard: {problem}.")

    receipt_path = os.environ.get(PLACEMENT_RECEIPT_ENV, "").strip()
    if not receipt_path:
        deny(
            "Mastermind shared-placement guard: the owner placement receipt "
            f"channel ({PLACEMENT_RECEIPT_ENV}) is unavailable; the binding "
            "cannot be checked against the current lease. Never launch a "
            "paid child while placement truth is uncertain."
        )
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        deny(
            "Mastermind shared-placement guard: the owner placement receipt "
            f"at {receipt_path} is unreadable; the binding cannot be checked "
            "against the current lease. Never launch a paid child while "
            "placement truth is uncertain."
        )
    if (
        not isinstance(receipt, dict)
        or str(receipt.get("schema") or "") != PLACEMENT_RECEIPT_SCHEMA
    ):
        deny(
            "Mastermind shared-placement guard: placement receipt schema "
            f"must be {PLACEMENT_RECEIPT_SCHEMA}."
        )
    current = receipt.get("execution_binding")
    problem = _binding_problems(current, "placement receipt")
    if problem:
        deny(f"Mastermind shared-placement guard: {problem}.")

    # Unaccounted descendants: the presented binding must BE the owner's
    # current fenced assignment — same (root, immediate parent, logical
    # child) identity, same admitted digest, same fenced attempt. A binding
    # for a different child under this session is a descendant the
    # placement authority never admitted or claimed.
    for name in _BINDING_IDENTITY_FIELDS:
        if str(binding.get(name)) != str(current.get(name)):
            deny(
                "Mastermind shared-placement guard: unaccounted descendant "
                f"— {name} in the presented binding does not match the "
                "owner's current assignment. Every paid child must be "
                "admitted and claimed through the placement authority "
                "before launch."
            )

    # Current lease: the fence must not have moved and the lease must be
    # held and unexpired. Launching on a stale fence double-spends the
    # reserved host slot, root concurrency and shared quota.
    fence_now = receipt.get("fence_counter")
    if isinstance(fence_now, bool) or not isinstance(fence_now, int):
        deny(
            "Mastermind shared-placement guard: placement receipt "
            "fence_counter must be an integer."
        )
    fence_held = binding.get("fence_counter", 0)
    lease_state = str(receipt.get("lease_state") or "").strip().upper()
    expires_ms = receipt.get("lease_expires_at_ms")
    expired = (
        isinstance(expires_ms, int)
        and not isinstance(expires_ms, bool)
        and int(time.time() * 1000) >= expires_ms
    )
    if fence_held != fence_now or lease_state != "HELD" or expired:
        deny(
            "Mastermind shared-placement guard: stale fence — the presented "
            f"binding holds fence {fence_held} but the owner's current "
            f"lease is fence {fence_now} (lease_state="
            f"{lease_state or 'UNKNOWN'}" + (", lease expired" if expired else "")
            + "). The reservation moved; re-claim through the placement "
            "authority instead of launching on a superseded assignment."
        )

    # Server-derived projections: the effective identity (explicit command
    # assignment wins over inherited environment) must equal what the
    # binding projects.
    for env_name, expected_value in _expected_projection(binding).items():
        effective = _command_or_environment_value(command, env_name)
        if effective != expected_value:
            deny(
                "Mastermind shared-placement guard: "
                f"{env_name} is a server-derived projection of the current "
                f"{EXECUTION_BINDING_SCHEMA}; this launch declares "
                f"{effective!r} but the binding projects {expected_value!r}. "
                "A child cannot re-root, re-parent or promote itself by "
                "changing the environment."
            )

    # Provider substitution: after reservation the launch must use the
    # reserved provider/pool, not a different paid lane.
    if launch is not None:
        token = launch_provider_token(command[launch.start():])
        allowed = {
            str(binding.get("pool_ref") or "").strip().lower(),
            str(binding.get("provider_ref") or "").strip().lower(),
        }
        if not _provider_token_matches(token, allowed):
            reserved = sorted(name for name in allowed if name)
            deny(
                "Mastermind shared-placement guard: provider substitution — "
                f"the current binding reserved {reserved} but this launch "
                f"requests {token!r}. A reservation cannot be re-pointed at "
                "a different provider after the fact; re-claim through the "
                "placement authority."
            )


def guard_fabric_launch(command: str) -> None:
    launch = FABRIC_LAUNCH_RE.search(command)
    if launch is None:
        return

    # WO-11: shared-placement sessions validate the broker-issued
    # ExecutionBinding against the owner's current lease BEFORE any other
    # launch check — on the common paid-launch path, engine-independent.
    if shared_placement_armed():
        validate_execution_binding(command, launch)

    inherited_root = os.environ.get("POOL_ORCHESTRATOR_ID", "").strip()
    root_assigned, assigned_root = _command_assignment(
        command, "POOL_ORCHESTRATOR_ID"
    )
    if inherited_root and root_assigned and assigned_root != inherited_root:
        deny(
            "Mastermind Fabric root-budget guard: POOL_ORCHESTRATOR_ID may not "
            "be rebound inside an already-rooted provider session. Preserve the "
            "original root identity; a new chat/helper is not a fresh budget."
        )

    missing = [
        name
        for name in _FABRIC_IDENTITY_NAMES
        if not _command_or_environment_value(command, name)
    ]
    if missing:
        deny(
            "Mastermind Fabric root-budget guard: provider launch is missing "
            + ", ".join(missing)
            + ". Every Fabric launch (pool run/remote or direct approved wrapper) "
            "must preserve the existing root "
            "orchestrator identity, true parent run, and task class so fair-share, "
            "descendant accounting, and routing economics cannot be reset by a new "
            "chat or helper."
        )


def guard_bash(payload: dict[str, object], tool_input: dict[str, object]) -> None:
    if not is_project_scope(payload):
        return
    command = str(tool_input.get("command") or "")
    clean = strip_heredocs(command)
    guard_fabric_launch(clean)
    if "gh " not in clean:
        return

    background = tool_input.get("run_in_background") is True
    watches = list(CI_WATCH_RE.finditer(clean))

    for watch in watches:
        call = watch.group("call")
        interval = INTERVAL_RE.search(call)
        if not interval or int(interval.group(1)) < MIN_WATCH_INTERVAL_S:
            deny(
                "Mastermind CI wait guard: GitHub watcher cadence must be explicit and "
                f"at least {MIN_WATCH_INTERVAL_S}s; {RECOMMENDED_WATCH_INTERVAL_S}s is "
                "preferred. Keep exactly one watcher for the exact PR/head/run."
            )
        if not background:
            deny(
                "Mastermind CI wait guard: foreground GitHub watch would pin this "
                "orchestrator for the external CI window. Launch exactly one watcher "
                "with run_in_background=true, then immediately continue another "
                "independent authorized project lane. The watcher notification is the "
                "next CI observation; repair/merge/live-proof accountability stays local."
            )

    loop_poll = any(
        CI_READ_RE.search(body) and SLEEP_RE.search(body)
        for body in (match.group(1) for match in DO_DONE_RE.finditer(clean))
    )
    delayed_poll = bool(CI_READ_RE.search(clean) and SLEEP_RE.search(clean))
    if not background and (loop_poll or delayed_poll):
        deny(
            "Mastermind CI wait guard: do not emulate a watcher with a foreground "
            "CI status + sleep/poll loop at any cadence. Perform one bounded state "
            "read, bind one asynchronous watcher (or the repository merge sweeper), "
            "then continue independent project work."
        )

    if not background and not watches and not loop_poll and not delayed_poll:
        key = _poll_key(
            clean,
            str(payload.get("cwd") or os.getcwd()),
            _session_scope(payload),
        )
        if key:
            repeat = repeat_poll_reason(key)
            if repeat:
                deny(repeat)

    if background and (watches or loop_poll or delayed_poll):
        allow_context(
            "CI WATCHER ARMED ASYNC: this background task is the CI observation owner. "
            "Do not tail or poll it and do not spend a reasoning cycle waiting for it. "
            "Immediately start the next highest-value independent authorized project "
            "lane. Return only on completion/event, genuine red, merge/conflict, or "
            "watcher failure/staleness."
        )


def guard_native_child(tool_input: dict[str, object]) -> None:
    # WO-11: native Agent/Task delegations under shared placement must be
    # covered by the CURRENT binding exactly like paid launches (missing
    # binding / stale fence / unaccounted descendant refusals; there is no
    # launch token to compare on this path, so no substitution check).
    if shared_placement_armed():
        validate_execution_binding("")
    model = str(tool_input.get("model") or "").strip()
    prompt = str(tool_input.get("prompt") or "")
    model_family = family(model)

    if not model:
        deny(
            "Mastermind fabric-first routing: native Claude children may not inherit "
            "the parent/default model. Send routine child work through the canonical "
            "Executive/Subagent Fabric. Native exception: explicit Opus orchestration "
            "or read-only audit/review with a WHY OPUS reason."
        )
    if model_family in ("sonnet", "haiku"):
        deny(
            f"Mastermind fabric-first routing: native {model_family} children are not "
            "default worker lanes. Route bounded labor through Executive/Subagent Fabric."
        )
    if model_family == "fable":
        deny(
            "Mastermind fabric-first routing: do not spend a second Fable child. Keep "
            "principal judgment in the Fable parent and route bounded labor through Fabric."
        )
    if model_family != "opus":
        deny(
            "Mastermind fabric-first routing: unrecognized native child model. Routine "
            "work belongs on Executive/Subagent Fabric; only explicit Opus "
            "orchestration/audit is a native exception."
        )

    route_match = ROUTE_RE.search(prompt)
    if not route_match:
        deny(
            "Opus native child requires an explicit ROUTE: ORCHESTRATION or "
            "ROUTE: AUDIT/REVIEW line."
        )
    route = route_match.group(1).lower()
    if not WHY_RE.search(prompt):
        deny("Opus native child requires WHY OPUS: <specific reason of at least 20 characters>.")
    if route in ("audit", "review", "auditor") and not READ_ONLY_RE.search(prompt):
        deny(
            "Opus audit/review child must declare MODE: READ_ONLY (or SCOPE: READ_ONLY). "
            "Proof-bearing child mutations belong to the canonical Fabric path."
        )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return

    if tool == "Bash":
        guard_bash(payload, tool_input)
        return

    if tool in ("Agent", "Task") and is_project_scope(payload):
        guard_native_child(tool_input)


if __name__ == "__main__":
    main()
