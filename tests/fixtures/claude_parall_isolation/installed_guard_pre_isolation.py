#!/usr/bin/env python3
import hashlib, json, os, re, subprocess, sys, tempfile, time

ROUTE_RE = re.compile(r"(?mi)^\s*ROUTE\s*:\s*(orchestration|audit|review|auditor)\s*$")
WHY_RE = re.compile(r"(?mi)^\s*WHY OPUS\s*:\s*(\S.{19,})$")
READ_ONLY_RE = re.compile(r"(?mi)^\s*(?:MODE|SCOPE)\s*:\s*READ[_ -]?ONLY\s*$")

HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
    re.S | re.M,
)


def strip_heredocs(cmd):
    """Remove heredoc bodies so documentation/script creation is not mistaken for execution."""
    prev = None
    out = cmd
    while prev != out:
        prev = out
        out = HEREDOC_RE.sub("<<HEREDOC", out)
    return out


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

# Session-local anti-babysitting ledger. This is ephemeral hook state, not company
# lifecycle or memory. It exists only to stop one principal from re-reading the same
# external CI state every few seconds while useful project work remains.
POLL_COOLDOWN_S = 300
POLL_STATE_DIR = os.path.join(tempfile.gettempdir(), "mastermind-ci-poll-cooldown-v2")
PR_CHECK_RE = re.compile(r"\bgh\s+pr\s+checks\s+(?P<id>\d+)\b", re.I)
PR_VIEW_RE = re.compile(r"\bgh\s+pr\s+view\s+(?P<id>\d+)\b(?P<tail>[^;&|\n]*)", re.I)
PR_VIEW_STATUS_FIELDS_RE = re.compile(
    r"statusCheckRollup|mergeStateStatus|reviewDecision|mergedAt|mergeCommit|isDraft|\bstate\b",
    re.I,
)
RUN_VIEW_RE = re.compile(r"\bgh\s+run\s+view\s+(?P<id>\d+)\b", re.I)
RUN_API_RE = re.compile(
    r"\bgh\s+api\b[^;&|\n]*/actions/runs/(?P<id>\d+)(?![^;&|\n]*(?:/cancel|/force-cancel|/rerun|/approve))",
    re.I,
)
RUN_WATCH_ID_RE = re.compile(r"\bgh\s+run\s+watch\s+(?P<id>\d+)\b", re.I)
PR_MUTATION_RE = re.compile(
    r"\bgh\s+pr\s+(?:edit|ready|merge|close|reopen|review|comment)\s+(?P<id>\d+)\b",
    re.I,
)
RUN_MUTATION_RE = re.compile(
    r"\bgh\s+run\s+(?:rerun|cancel)\s+(?P<id>\d+)\b"
    r"|\bgh\s+api\b[^;&|\n]*/actions/runs/(?P<api_id>\d+)/(?:rerun|cancel|force-cancel|approve)",
    re.I,
)
GIT_PUSH_RE = re.compile(CMD_POS + r"git\s+push\b", re.I)
WATCH_MUTATION_RE = re.compile(
    r"\bgh\s+pr\s+(?:update-branch|edit|ready|merge|close|reopen|review|comment)\b"
    r"|\bgh\s+run\s+(?:rerun|cancel)\b"
    r"|\bgh\s+workflow\s+run\b"
    r"|\bgh\s+api\b[^;&|\n]*(?:--method|-X)\s+(?:POST|PATCH|PUT|DELETE)\b"
    r"|\bgit\s+(?:push|commit|merge|rebase|reset|cherry-pick)\b",
    re.I,
)


def _poll_state_path(payload):
    """Return a session-scoped ephemeral ledger path, or None when no session id exists."""
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return None
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return os.path.join(POLL_STATE_DIR, digest + ".json")


def _load_poll_state(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_poll_state(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        # Anti-waste state must fail open; it is never evidence of authorization.
        try:
            if "tmp" in locals() and os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass


def _poll_key(clean):
    m = PR_CHECK_RE.search(clean)
    if m:
        return f"pr-checks:{m.group('id')}"
    m = PR_VIEW_RE.search(clean)
    if m and PR_VIEW_STATUS_FIELDS_RE.search(m.group("tail") or ""):
        return f"pr-view:{m.group('id')}"
    m = RUN_VIEW_RE.search(clean)
    if m:
        return f"run-view:{m.group('id')}"
    m = RUN_API_RE.search(clean)
    if m:
        return f"run-view:{m.group('id')}"
    return None


def _clear_poll_state_for_mutation(payload, clean):
    """A material self-mutation or push invalidates the session's previous status read."""
    path = _poll_state_path(payload)
    if not path:
        return
    if GIT_PUSH_RE.search(clean):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return

    state = _load_poll_state(path)
    changed = False
    for match in PR_MUTATION_RE.finditer(clean):
        pr = match.group("id")
        for key in (f"pr-checks:{pr}", f"pr-view:{pr}"):
            changed = state.pop(key, None) is not None or changed
    for match in RUN_MUTATION_RE.finditer(clean):
        run_id = match.group("id") or match.group("api_id")
        if run_id:
            changed = state.pop(f"run-view:{run_id}", None) is not None or changed
    if changed:
        _save_poll_state(path, state)


def _record_poll_key(payload, key, now=None):
    path = _poll_state_path(payload)
    if not path or not key:
        return
    now = time.time() if now is None else float(now)
    state = _load_poll_state(path)
    # Bound stale state. Entries older than two windows are irrelevant.
    state = {
        k: v for k, v in state.items()
        if isinstance(v, (int, float)) and now - float(v) < POLL_COOLDOWN_S * 2
    }
    state[key] = now
    _save_poll_state(path, state)


def _repeat_poll_reason(payload, clean, now=None):
    """Record a first bounded CI read; return a deny reason for an unchanged repeat."""
    key = _poll_key(clean)
    if not key:
        return None
    path = _poll_state_path(payload)
    if not path:
        return None
    now = time.time() if now is None else float(now)
    state = _load_poll_state(path)
    last = state.get(key)
    if isinstance(last, (int, float)) and 0 <= now - float(last) < POLL_COOLDOWN_S:
        remaining = max(1, int(POLL_COOLDOWN_S - (now - float(last))))
        return (
            f"Mastermind CI wait guard: REDUNDANT POLL for {key}. "
            f"READ_COOLDOWN_ONLY: this repeat is blocked for about {remaining}s "
            f"within a {POLL_COOLDOWN_S}s window. This is not a permanent permission denial. "
            "Do not sleep/retry, switch readers, reset guard state, or mutate to clear it. "
            "Continue independent authorized work. Prefer a verified existing observer's "
            "result. If no verified observer supplies completion, one bounded same-carrier "
            "read is eligible at the next real integration boundary or existing scheduled "
            "wake after expiry. Preserve genuine permission, safety and effect-unknown holds."
        )
    _record_poll_key(payload, key, now)
    return None


def family(model):
    m = (model or "").strip().lower()
    for fam in ("fable", "opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return m


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    raise SystemExit(0)


def allow_context(context):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": context,
    }}))
    raise SystemExit(0)


def is_mastermind_scope(payload):
    cwd = os.path.realpath(str(payload.get("cwd") or os.getcwd()))
    roots = (
        "/Users/chriswong/Documents/Cluade",
        "/Volumes/Mastermind/agent-workspaces",
        "/Volumes/Mastermind/claude-ssh-worktrees",
        "/Volumes/Mastermind/repos",
        "/Users/chriswong/Documents/GitHub/Mastermind",
        "/Users/chriswong/Documents/GitHub/macro",
        "/Users/chriswong/Documents/GitHub/mastermind-terminal",
        "/Users/chriswong/Documents/GitHub/mastermind-worktrees",
    )
    return any(cwd == root or cwd.startswith(root + os.sep) for root in roots)


def _legacy_macro_root_reason(payload, tool):
    """Return a migration reason only for pre-root-admission Macro carriers.

    This is a compatibility fence for historical worktrees whose branch-local
    project hook predates Macro's current root quarantine. Current hooks remain
    the admission owner; this global guard only prevents an old checkout from
    performing new effects long enough to hit its legacy unsafe_branch Stop loop.
    """
    if not is_mastermind_scope(payload):
        return None
    cwd = os.path.realpath(str(payload.get("cwd") or os.getcwd()))
    try:
        top = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if top.returncode != 0:
            return None
        root = top.stdout.strip()
        hook = os.path.join(root, ".claude", "hooks", "ship_loop_guard.py")
        if not os.path.isfile(hook):
            return None
        with open(hook, "r", encoding="utf-8", errors="replace") as handle:
            # The current marker sits near the top of the hook; keep this bounded.
            hook_head = handle.read(96 * 1024)
        if "_ROOT_ADMISSION_VERSION" in hook_head:
            return None
        remote = subprocess.run(
            ["git", "-C", root, "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if remote.returncode != 0 or "mastermindx-market-intelligence/macro" not in remote.stdout:
            return None
        branch = subprocess.run(
            ["git", "-C", root, "branch", "--show-current"],
            capture_output=True, text=True, timeout=2, check=False,
        ).stdout.strip()
        if branch.startswith("claude/") or tool == "EnterWorktree":
            return None
        location = branch or "detached HEAD"
        return (
            f"Mastermind legacy Macro carrier fence: this session is rooted on {location}, "
            "whose branch-local ship-loop hook predates the current root-admission repair. "
            "Do not mutate, delegate, or repoint this historical carrier to satisfy Stop. "
            "Use Claude's EnterWorktree tool now to move this SAME conversation onto a fresh "
            "origin/main-backed claude/* worktree, then retry the intended action there. "
            "This avoids the known false SHIP LOOP unsafe_branch cycle without weakening "
            "the current delivery guard."
        )
    except Exception:
        # Compatibility assistance is not a new authority plane and must fail open.
        return None


def guard_bash(payload, ti):
    if not is_mastermind_scope(payload):
        return
    cmd = str(ti.get("command") or "")
    clean = strip_heredocs(cmd)

    # A push or explicit GitHub mutation is a material invalidator for this session's
    # previous status read. Clear the narrow cooldown before considering a later read.
    _clear_poll_state_for_mutation(payload, clean)

    if "gh " not in clean:
        return
    background = ti.get("run_in_background") is True
    # Codex hands long Bash calls back through native session handles. Its
    # documented turn_id is a nonempty string; transcript_path may be a string
    # or null on BOTH surfaces and cannot classify Claude versus Codex.
    # This identifies the existing watch capability, not authentication/grants.
    # Explicit intervals, observation-only scope and cooldowns still apply.
    codex_native = (isinstance(payload.get("turn_id"), str)
                    and bool(payload["turn_id"].strip()))

    watches = list(CI_WATCH_RE.finditer(clean))
    for watch in watches:
        call = watch.group("call")
        m = INTERVAL_RE.search(call)
        if not m or int(m.group(1)) < 60:
            deny(
                "Mastermind CI wait guard: GitHub watch commands must use an explicit "
                "safe interval of at least 60s. Prefer 150s. Bind one watcher to the exact "
                "PR/head/run; do not spend the shared GitHub quota on a hot watcher."
            )
        if not background and not codex_native:
            deny(
                "Mastermind CI wait guard: foreground GitHub watch would pin this Claude "
                "principal for the external CI window. Launch exactly one watcher with the "
                "Bash tool's run_in_background=true, then immediately continue another "
                "independent authorized project lane. The watcher notification is the next "
                "CI observation; ownership of repair/merge/live proof stays with this operation."
            )

    # The measured failure also appears as hand-written polling loops rather than a native
    # watch. Strip heredocs first so creating/documenting a watcher is never treated as running one.
    loop_poll = any(
        CI_READ_RE.search(body) and SLEEP_RE.search(body)
        for body in (m.group(1) for m in DO_DONE_RE.finditer(clean))
    )
    delayed_poll = bool(CI_READ_RE.search(clean) and SLEEP_RE.search(clean))

    # A watcher owns OBSERVATION only. Repair, branch refresh, rerun, merge, comment,
    # push, and source mutation return to the owning principal/repair lane. Otherwise
    # a "watcher" can continuously update-branch/retrigger CI and create the exact
    # 30-50 minute traffic jam it was meant to absorb.
    if (watches or loop_poll or delayed_poll) and WATCH_MUTATION_RE.search(clean):
        deny(
            "Mastermind CI wait guard: CI WATCHERS ARE OBSERVATION-ONLY. This watcher "
            "contains a modifying action (for example update-branch/rerun/merge/push). "
            "Remove the mutation. Let exactly one watcher report the terminal event, "
            "then return repair/refresh/merge work to the owning principal or canonical "
            "repair lane. Do not silently restart CI from inside a wait loop."
        )

    # A loop/sleep may be the watcher only when Claude Bash itself is backgrounded.
    # Codex native background-terminal handoff is reserved for one native gh watch,
    # not a custom polling loop.
    if not background:
        if loop_poll or delayed_poll:
            deny(
                "Mastermind CI wait guard: do not emulate a watcher with a foreground "
                "sleep/poll loop. Perform one bounded state read, then use one background/"
                "native watcher or the repository's existing merge sweeper and continue "
                "independent project work."
            )

    repeat_reason = _repeat_poll_reason(payload, clean)
    if repeat_reason:
        deny(repeat_reason)

    async_observer = background or (codex_native and bool(watches))
    if async_observer and (watches or (CI_READ_RE.search(clean) and SLEEP_RE.search(clean))):
        # A native run watcher should fence an immediate direct run-view from the same
        # session even when no diagnosis read preceded it.
        run_watch = RUN_WATCH_ID_RE.search(clean)
        if run_watch:
            _record_poll_key(payload, f"run-view:{run_watch.group('id')}")
        surface = (
            "Codex native background-terminal handoff"
            if codex_native and not background
            else "background task"
        )
        allow_context(
            f"CI WATCHER REQUEST ADMITTED via {surface}; launch is NOT yet verified. "
            "After the tool returns, retain its actual handle, exact PR/head/run and "
            "supported result-consumption path in the existing checkpoint. Do not invent "
            "an idle wake or treat PreToolUse as execution evidence. Continue useful work; "
            "consume the same handle at a useful boundary if automatic return is unavailable. "
            "No hot polling or duplicate observer. A failed launch is not a running watcher; "
            "preserve uncertain effects and genuine refusals on the original carrier."
        )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        return

    legacy_root_reason = _legacy_macro_root_reason(payload, tool)
    if legacy_root_reason:
        deny(legacy_root_reason)

    if tool == "Bash":
        guard_bash(payload, ti)
        return

    if tool not in ("Agent", "Task"):
        return
    model = str(ti.get("model") or "").strip()
    prompt = str(ti.get("prompt") or "")
    fam = family(model)

    if not model:
        deny("Mastermind fabric-first routing: native Claude children may not inherit the parent/default model. Send routine child work through the canonical Executive/Subagent Fabric. Native child exception: explicit model opus with ROUTE: ORCHESTRATION or ROUTE: AUDIT plus WHY OPUS.")
    if fam in ("sonnet", "haiku"):
        deny(f"Mastermind fabric-first routing: native {fam} children are not default worker lanes. Route the bounded mission through Executive/Subagent Fabric so Capacity/Model Router selects the least-scarce eligible worker.")
    if fam == "fable":
        deny("Mastermind fabric-first routing: do not spend a second Fable child. Keep principal judgment in the Fable parent and send bounded labor through Executive/Subagent Fabric.")
    if fam != "opus":
        deny("Mastermind fabric-first routing: unrecognized native child model. Routine work belongs on Executive/Subagent Fabric; only explicit Opus orchestration/audit is a native child exception.")

    m = ROUTE_RE.search(prompt)
    if not m:
        deny("Opus native child requires an explicit ROUTE: ORCHESTRATION or ROUTE: AUDIT/REVIEW line.")
    route = m.group(1).lower()
    if not WHY_RE.search(prompt):
        deny("Opus native child requires WHY OPUS: <specific reason of at least 20 characters>.")
    if route in ("audit", "review", "auditor") and not READ_ONLY_RE.search(prompt):
        deny("Opus audit/review child must declare MODE: READ_ONLY (or SCOPE: READ_ONLY). Proof-bearing mutations belong to the canonical fabric child-work path.")


if __name__ == "__main__":
    main()
