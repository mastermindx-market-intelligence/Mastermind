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
owner-issued placement receipt, accepted only from a path the fenced session
cannot write (owner service-account channel). Refusal classes: missing binding,
stale fence, provider substitution after reservation, unaccounted descendant.
There is no independent signing authority — the binding is only an assignment
of opaque references, trusted exactly as far as it matches the owner's current
lease. The gate fences every lexically observed launch in the commands it is
shown through this provider hook; it does not claim to fence arbitrary processes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
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
    "assignment_generation",
)
_BINDING_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
#: Optional owner-projected integrity pin for the receipt file: the SHA-256
#: of the receipt bytes the owner wrote. Defence in depth only — the trust
#: basis is the owner-only receipt channel (see ``_receipt_channel_problem``).
PLACEMENT_RECEIPT_DIGEST_ENV = "MASTERMIND_PLACEMENT_RECEIPT_DIGEST"
#: The only lease state that admits a launch (exact, case-sensitive).
LEASE_STATE_HELD = "HELD"
#: Exact env tokens that arm the gate (a projected binding also arms it).
SHARED_PLACEMENT_ARM_TOKENS = ("1", "true", "yes", "on")

#: Closed per-wrapper mode vocabularies (the alternations FABRIC_LAUNCH_RE
#: recognizes). Under shared placement a wrapper invoked with any OTHER
#: mode is an unknown paid launch and is refused, never ignored.
_SUB_MODES = frozenset(_SUB_LAUNCH_MODE[3:-1].split("|"))
_REMOTE_MODES = frozenset(_REMOTE_LAUNCH_MODE[3:-1].split("|"))
_SLOT_POOLS = frozenset(_SLOT_POOL[3:-1].split("|"))
#: Wrapper-internal pure helper modes that never acquire a slot or spawn a
#: provider (documented in sub.sh): not paid launches.
NON_LAUNCH_WRAPPER_MODES = frozenset({"__launch_plan", "__glm_memory"})
#: Every wrapper shape: (name, index of the mode/pool argument, closed mode
#: vocabulary or None for the open ``pool`` vocabulary, matched exactly).
_WRAPPER_SHAPES = {
    "pool run": (0, None),
    "pool remote": (1, None),
    "sub.sh": (0, _SUB_MODES),
    "remote_sub.sh": (1, _REMOTE_MODES),
    "slot.py": (0, _SLOT_POOLS),
}
_WRAPPER_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_./-]+/)?"
    r"(?P<wrapper>pool[ \t]+(?:run|remote)|remote_sub\.sh|sub\.sh|slot\.py)"
    r"(?![A-Za-z0-9_.-])",
    re.I,
)
_WRAPPER_ARG_RE = re.compile(r"[ \t]+([^\s;&|<>()`{}]+)")
_SIMPLE_COMMAND_SPLIT_RE = re.compile(r"[;&|\n(){}`]|\$\(")
#: Read-only inspectors: a wrapper NAME given to them as an argument is a
#: file being read, not a launch (``grep -n slot.py docs/runbook.md``).
_INSPECTORS = frozenset({
    "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg",
    "wc", "ls", "stat", "file", "diff", "cmp", "shasum", "sha1sum",
    "sha256sum", "md5", "md5sum", "nl", "od", "xxd",
})
_COMMAND_PREFIX_WORDS = frozenset({
    "do", "then", "else", "elif", "if", "while", "until", "!",
})
#: Constructs that can change the launch environment outside lexical
#: observation: eval/source of computed text, shell startup files, and
#: assignments through a computed variable name.
#: Wrapper source fed to a shell (``cat sub.sh | bash -s grok``) launches
#: without a lexically visible invocation.
_SHELL_FEED_RE = re.compile(
    r"\|\s*(?:\S*/)?(?:ba|z|da|k)?sh\b"
    r"|(?:^|[\s;&|(])(?:\S*/)?(?:ba|z|da|k)?sh\s+(?:-\S+\s+)*<"
)
_UNOBSERVABLE_ENV_RE = re.compile(
    r"(?:^|[;&|(`{\n]|\$\()\s*(?:eval|source|\.)(?=\s)"
    r"|(?:^|[\s;&|(`{])(?:BASH_ENV|ENV)\+?="
    r"|(?:^|[\s;&|(`{])(?:export|declare|typeset|readonly|local)"
    r"(?:\s+-\S+)*\s+[A-Za-z0-9_]*\$"
    r"|(?:^|[\s;&|(`{])printf\s+-v\s*\$"
)

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


def _command_assignments(command: str, name: str) -> list[str]:
    """EVERY shell-level ``NAME=value`` assignment of ``name`` in the command,
    in positional order (prefix assignments, ``env NAME=…``, nested
    ``export NAME=…`` inside quoted sub-commands). A dynamic value (``$``,
    backtick) cannot prove stable identity and is recorded as ``''``.

    POSIX applies prefix assignments left-to-right (the LAST wins in the
    launched child) and a nested ``export`` overrides at runtime, so any
    check that inspects only the first occurrence compares a decoy while
    the child runs under a different identity. Callers must therefore
    judge all occurrences, never one.
    """
    pattern = re.compile(
        rf"(?:^|[\s;&|]){re.escape(name)}="
        rf"(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|]*))"
    )
    values: list[str] = []
    for match in pattern.finditer(command):
        value = next(
            (value for value in match.groups() if value is not None),
            "",
        ).strip()
        if any(token in value for token in ("$", "`")):
            value = ""
        values.append(value)
    return values


def _command_assignment(command: str, name: str) -> tuple[bool, str]:
    """(assigned?, effective value): the value the launched child actually
    receives — the LAST literal assignment — or ``''`` when any occurrence
    is empty/dynamic (an unstable identity is treated as missing)."""
    values = _command_assignments(command, name)
    if not values:
        return False, ""
    if not all(values):
        return True, ""
    return True, values[-1]


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
    return (
        os.environ.get(SHARED_PLACEMENT_ENV, "").strip().lower()
        in SHARED_PLACEMENT_ARM_TOKENS
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
        # Required, never defaulted: an absent fence must not pass as fence 0.
        value = binding.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return f"{owner}: {name} must be present as an integer >= 0"
    return ""


def _canonical_command(command: str) -> str:
    """The command with shell quoting (quotes, backslashes) removed, so a
    name or mode split or hidden by quotes (``"POOL_ORCH""ESTRATOR_ID=x"``,
    ``sub.sh "grok"``) is scanned as the shell will see it."""
    return re.sub(r"[\"'\\]", "", command.replace("\\\n", " "))


def _simple_command_head(canon: str, offset: int) -> str:
    """Basename of the first word of the simple command containing
    ``offset`` (assignments and compound-command keywords skipped)."""
    starts = [m.end() for m in _SIMPLE_COMMAND_SPLIT_RE.finditer(canon, 0, offset)]
    prefix = canon[(starts[-1] if starts else 0):offset].split()
    for word in prefix:
        if word in _COMMAND_PREFIX_WORDS or re.match(r"[A-Za-z_][A-Za-z0-9_]*\+?=", word):
            continue
        return word.rsplit("/", 1)[-1].lower()
    return ""


def _wrapper_invocations(command: str) -> list[tuple[int, str, str, bool]]:
    """EVERY wrapper invocation in ``command``, positional:
    ``(offset, wrapper, token, known_mode)`` for all five shapes, repeated.

    Unlike :data:`FABRIC_LAUNCH_RE`, the mode is NOT required to be on the
    wrapper's list: an off-list mode (``sub.sh zebra-glm``) is still an
    invocation (``known_mode=False``) so it can be refused instead of
    passing unobserved. A wrapper name with no argument, an argument of a
    read-only inspector (``cat sub.sh``), or a documented pure helper mode
    (``sub.sh __launch_plan``) is not a paid launch.
    """
    canon = _canonical_command(command)
    found: list[tuple[int, str, str, bool]] = []
    for match in _WRAPPER_RE.finditer(canon):
        wrapper = re.sub(r"\s+", " ", match.group("wrapper").lower())
        index, modes = _WRAPPER_SHAPES[wrapper]
        args: list[str] = []
        position = match.end()
        while len(args) < index + 2:
            arg = _WRAPPER_ARG_RE.match(canon, position)
            if not arg:
                break
            args.append(arg.group(1).lower())
            position = arg.end()
        if not args:
            continue
        head = _simple_command_head(canon, match.start())
        if head in _INSPECTORS:
            continue
        token = args[index] if len(args) > index else ""
        if token in NON_LAUNCH_WRAPPER_MODES or (
            len(args) > index + 1 and args[index + 1] == "__launch_plan"
        ):
            continue
        known = bool(token) and (modes is None or token in modes)
        found.append((match.start(), wrapper, token, known))
    return found


def launch_provider_tokens(command: str) -> list[tuple[int, str]]:
    """``(offset, token)`` for EVERY paid launch in ``command``, positional.

    Covers every wrapper shape: ``pool run <pool>``, ``pool remote <host>
    <pool>``, ``sub.sh <mode>``, ``remote_sub.sh <host> <mode>`` and
    ``slot.py <pool>`` — the same wrappers every engine's paid launch goes
    through. Each token is read from its own launch's arguments, so a later
    launch can never stand in for an earlier one.
    """
    return [(offset, token) for offset, _, token, _ in _wrapper_invocations(command)]


def launch_provider_token(command: str) -> str:
    """The provider/pool token of the FIRST paid launch (lowercased), or ''.
    Gate logic must use :func:`launch_provider_tokens` (all launches)."""
    tokens = launch_provider_tokens(command)
    return tokens[0][1] if tokens else ""


def _env_clear_offsets(canon: str) -> list[int]:
    """Offsets of ``env`` invocations that clear the inherited environment
    (``env -i``, ``env -``, ``--ignore-environment``, clustered ``-iv``) or
    re-split their arguments (``-S``), which can hide a clear."""
    offsets: list[int] = []
    for match in re.finditer(r"(?<![A-Za-z0-9_.-])env(?=[ \t])", canon):
        words = re.match(r"[^;&|\n()`]*", canon[match.end():]).group(0).split()
        index = 0
        while index < len(words):
            word = words[index]
            if (
                word in ("-", "--ignore-environment", "-S")
                or word.startswith("--split-string")
                or re.fullmatch(r"-[A-Za-z]*[iS][A-Za-z]*", word)
            ):
                offsets.append(match.start())
                break
            if word in ("-u", "-C", "-P", "--unset", "--chdir"):
                index += 2
                continue
            if word.startswith("-") or re.match(r"[A-Za-z_][A-Za-z0-9_]*=", word):
                index += 1
                continue
            break
    return offsets


def _effective_identity_values(command: str, name: str) -> list[str] | None:
    """Canonical view of every way ``command`` sets ``name`` for its child.

    Returns ``None`` when the command does not touch ``name`` (the inherited
    session value governs); otherwise EVERY value the child could receive:
    each literal assignment in any form — prefix (last wins), ``env``,
    ``export``/``declare``/``readonly``, ``+=``, quoted or split by quotes,
    nested inside ``sh -c '…'`` — plus ``''`` for every clearing or
    non-literal form (``unset``, ``env -u``, ``env -i`` not followed by a
    reassignment, ``printf -v``, ``read``, ``declare -n``, ``${NAME:=…}``,
    dynamic ``$``/backtick values). The caller refuses unless every value
    equals the server-derived projection.
    """
    canon = _canonical_command(command)
    values = list(_command_assignments(command, name))
    events: list[tuple[int, str]] = []
    occurrence = re.compile(
        rf"(?:(?<![A-Za-z0-9_])|(?<=-u)){re.escape(name)}(?![A-Za-z0-9_])"
    )
    for match in occurrence.finditer(canon):
        before, after = canon[:match.start()], canon[match.end():]
        if after.startswith("="):
            value = re.match(r"=([^\s;&|<>()`{}]*)", after).group(1)
            events.append((match.start(), "" if "$" in value else value))
        elif before.endswith("$") or (
            before.endswith("${") and not re.match(r":?=", after)
        ):
            continue  # a read of the value, not a change
        elif re.search(r"(?:^|[\s;&|(])export\s+$", before) and re.match(
            r"(?:[\s;&|)]|$)", after
        ):
            continue  # bare `export NAME` re-exports the inherited value
        else:
            events.append((match.start(), ""))
    for offset in _env_clear_offsets(canon):
        if not any(at > offset and value for at, value in events):
            events.append((offset, ""))
    canonical = [value for _, value in events]
    extra = [value for value in values if value not in canonical]
    if not canonical and not extra:
        return None
    return canonical + extra


def _principal_ids() -> tuple[int, frozenset[int]]:
    """(effective uid, group ids) of the fenced principal (this session)."""
    return os.geteuid(), frozenset({os.getegid(), *os.getgroups()})


def _principal_controls(info: os.stat_result, uid: int, gids: frozenset[int]) -> bool:
    if uid == 0 or info.st_uid == uid:
        return True  # root, or the owner (who can always chmod/replace)
    mode = info.st_mode
    if stat.S_ISLNK(mode):
        return False  # replacing a symlink is governed by its directory
    writable = bool(mode & stat.S_IWOTH) or (
        info.st_gid in gids and bool(mode & stat.S_IWGRP)
    )
    if writable and stat.S_ISDIR(mode) and mode & stat.S_ISVTX:
        return False  # sticky: entries the principal does not own are safe
    return writable


def _receipt_channel_problem(path_text: str) -> str:
    """'' when the receipt can only have been produced by the placement owner.

    Trust basis (no signing authority exists by design): the owner runs as
    its own service account (``_mastermind_exec``) and projects the receipt
    into a path the fenced principal cannot write. Every component of both
    the literal and the resolved path must be outside the principal's
    control — not owned by it, not writable by it — so it can neither
    rewrite the receipt, restore an older copy, nor re-point a symlink. A
    receipt the session could have written itself is refused outright.
    """
    uid, gids = _principal_ids()
    literal = Path(os.path.abspath(path_text))
    resolved = Path(os.path.realpath(path_text))
    for chain in (literal, resolved):
        for component in (*reversed(chain.parents), chain):
            try:
                info = os.lstat(component)
            except OSError:
                return f"{component} cannot be inspected"
            if _principal_controls(info, uid, gids):
                return (
                    f"{component} is owned or writable by this session's "
                    "principal"
                )
    try:
        if not stat.S_ISREG(os.stat(resolved).st_mode):
            return f"{resolved} is not a regular file"
    except OSError:
        return f"{resolved} cannot be inspected"
    return ""


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


def validate_execution_binding(command: str) -> None:
    """Refuse paid launches/delegations not covered by the CURRENT
    broker-issued ExecutionBinding (WO-11; Rev 4 S3.D l.287-289, S4 steps
    3-4).

    Refusal classes: missing binding, stale fence (the reservation moved,
    was released or expired), provider substitution after reservation, and
    unaccounted descendants (a binding that does not cover this launch's
    child identity, or more than one paid launch under one binding). The
    binding is only an assignment of opaque references — never a
    credential, and there is no independent signing authority: it is
    trusted exactly as far as it matches the owner's current lease receipt.

    Trust basis and what remains trusting:

    * Session environment (binding, receipt path, optional digest pin): the
      owner projects it into the provider process; a launched command cannot
      alter the environment this hook runs in, so command-level assignments
      of these names are ignored.
    * Receipt: accepted only from an owner-only channel — every component
      of its path must be outside the fenced principal's control (see
      ``_receipt_channel_problem``). The principal therefore cannot forge,
      roll back or replay it; a receipt it could have written is refused.
      This relies on the OS uid boundary between the session and the
      owner's service account: a same-uid owner gets no shared-placement
      launches at all (fail closed), and root is outside this model.
    * Lease currency: the receipt is as current as the owner's re-projection
      (atomic replace per lease event, WO-18). If the owner stops
      re-projecting, ``lease_expires_at_ms`` still bounds the lease.

    Lexical scope (documented, not claimed): the gate judges the command
    text it is shown — every wrapper invocation in it (all five shapes,
    repeated, heredoc bodies included, off-list modes refused) and every
    identity assignment form. Scripts staged in an EARLIER command or a
    file and executed later, and environment injected by provider-side
    mechanisms outside the command, are not observed; eval/source/
    computed-name assignments in a launch command are refused as
    unobservable.
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
    channel_problem = _receipt_channel_problem(receipt_path)
    if channel_problem:
        deny(
            "Mastermind shared-placement guard: the placement receipt is not "
            f"owner-authenticated — {channel_problem}, so the fenced session "
            "could have forged, rolled back or replayed it. The receipt must "
            "be projected by the placement owner into a path this session "
            "cannot write. Never launch a paid child while placement truth "
            "is uncertain."
        )
    try:
        receipt_bytes = Path(receipt_path).read_bytes()
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (OSError, ValueError):
        deny(
            "Mastermind shared-placement guard: the owner placement receipt "
            f"at {receipt_path} is unreadable; the binding cannot be checked "
            "against the current lease. Never launch a paid child while "
            "placement truth is uncertain."
        )
    pinned_digest = os.environ.get(PLACEMENT_RECEIPT_DIGEST_ENV, "").strip().lower()
    if pinned_digest:
        if not _BINDING_HEX64_RE.match(pinned_digest):
            deny(
                "Mastermind shared-placement guard: receipt integrity — "
                f"{PLACEMENT_RECEIPT_DIGEST_ENV} must be the 64-char hex "
                "SHA-256 of the owner-written receipt."
            )
        if hashlib.sha256(receipt_bytes).hexdigest() != pinned_digest:
            deny(
                "Mastermind shared-placement guard: receipt integrity — the "
                f"placement receipt at {receipt_path} does not match the "
                "digest the owner pinned into this session; the receipt was "
                "rewritten, replayed or re-projected since claim. Re-claim "
                "through the placement authority instead of launching on an "
                "unverifiable lease."
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
    # child) identity, same admitted digest, same fenced attempt and
    # assignment generation.
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
    if fence_now != current.get("fence_counter") or str(
        receipt.get("attempt_ref")
    ) != str(current.get("attempt_ref")):
        deny(
            "Mastermind shared-placement guard: placement receipt is "
            "internally inconsistent (top-level fence_counter/attempt_ref "
            "disagree with its embedded execution_binding)."
        )
    fence_held = binding.get("fence_counter")
    lease_state = receipt.get("lease_state")
    expires_ms = receipt.get("lease_expires_at_ms")
    if isinstance(expires_ms, bool) or not isinstance(expires_ms, int):
        deny(
            "Mastermind shared-placement guard: placement receipt "
            "lease_expires_at_ms must be an integer (epoch milliseconds)."
        )
    expired = int(time.time() * 1000) >= expires_ms
    if fence_held != fence_now or lease_state != LEASE_STATE_HELD or expired:
        deny(
            "Mastermind shared-placement guard: stale fence — the presented "
            f"binding holds fence {fence_held} but the owner's current "
            f"lease is fence {fence_now} (lease_state="
            f"{lease_state or 'UNKNOWN'}" + (", lease expired" if expired else "")
            + "). The reservation moved; re-claim through the placement "
            "authority instead of launching on a superseded assignment."
        )

    if not command:
        launches: list[tuple[int, str, str, bool]] = []
    else:
        if _UNOBSERVABLE_ENV_RE.search(_canonical_command(command)):
            deny(
                "Mastermind shared-placement guard: unobservable launch "
                "environment — eval, source/., BASH_ENV/ENV or a computed "
                "variable name can change the child's POOL_* identity outside "
                "what this guard can check. Run the paid launch as a plain "
                "command."
            )
        launches = _wrapper_invocations(command)

    # Server-derived projections: EVERY identity value the launched child
    # could receive must equal what the binding projects (canonical view of
    # all assignment/clearing forms; see _effective_identity_values).
    for env_name, expected_value in _expected_projection(binding).items():
        declared = _effective_identity_values(command, env_name)
        if declared is None:
            declared = [os.environ.get(env_name, "").strip()]
        offending = [value for value in declared if value != expected_value]
        if offending:
            deny(
                "Mastermind shared-placement guard: "
                f"{env_name} is a server-derived projection of the current "
                f"{EXECUTION_BINDING_SCHEMA}; this launch declares "
                f"{offending[0]!r} but the binding projects {expected_value!r}"
                + (
                    f" ({len(declared)} assignments of {env_name} in one "
                    "command; every one must equal the projection)"
                    if len(declared) > 1
                    else ""
                )
                + ". A child cannot re-root, re-parent or promote itself by "
                "changing the environment (unset/env -i/nested shells count)."
            )

    # Every paid launch in the command, positionally: an off-list wrapper
    # mode is refused (never ignored); every token must equal the reserved
    # pool_ref EXACTLY (no composite/segment acceptance); one binding covers
    # one attempt, so a second launch is an unaccounted descendant.
    reserved = str(binding.get("pool_ref") or "").strip().lower()
    for _, wrapper, token, known in launches:
        if not known:
            deny(
                "Mastermind shared-placement guard: unknown wrapper mode — "
                f"{wrapper} {token or '<missing>'!r} is not on the recognised "
                "paid-launch vocabulary, so it is treated as a paid launch the "
                "guard cannot attribute and refused."
            )
        if token != reserved:
            deny(
                "Mastermind shared-placement guard: provider substitution — "
                f"the current binding reserved pool_ref {reserved!r} but this "
                f"launch requests {token!r}. Launch tokens must equal the "
                "reserved pool exactly; a reservation cannot be re-pointed at "
                "a different provider after the fact. Re-claim through the "
                "placement authority."
            )
    if len(launches) > 1:
        deny(
            "Mastermind shared-placement guard: unaccounted descendant — "
            f"this command carries {len(launches)} paid launches "
            f"{[token for _, _, token, _ in launches]} but the current binding "
            "covers exactly one attempt. Every paid child must be admitted "
            "and claimed through the placement authority before launch."
        )


def guard_fabric_launch(command: str, raw_command: str | None = None) -> None:
    raw = command if raw_command is None else raw_command
    launches = list(FABRIC_LAUNCH_RE.finditer(command))
    armed = shared_placement_armed()
    # An off-list wrapper mode is still an observed launch (REVIEW_2329
    # M-4): under shared placement it is refused by the gate; otherwise it
    # gets the legacy identity checks instead of passing unchecked.
    invocations = _wrapper_invocations(raw if armed else command)
    if armed:
        canon = _canonical_command(raw)
        if _WRAPPER_RE.search(canon) and _SHELL_FEED_RE.search(canon):
            deny(
                "Mastermind shared-placement guard: unobservable launch — "
                "wrapper source fed to a shell launches without a visible "
                "wrapper invocation. Invoke the wrapper directly."
            )
    if not launches and not invocations:
        return

    # WO-11: shared-placement sessions validate the broker-issued
    # ExecutionBinding against the owner's current lease BEFORE any other
    # launch check — on the common paid-launch path, engine-independent.
    # The armed gate judges the raw command, heredoc bodies included.
    if armed:
        validate_execution_binding(raw)

    inherited_root = os.environ.get("POOL_ORCHESTRATOR_ID", "").strip()
    assigned_roots = _command_assignments(command, "POOL_ORCHESTRATOR_ID")
    if inherited_root and any(root != inherited_root for root in assigned_roots):
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
    guard_fabric_launch(clean, command)
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
