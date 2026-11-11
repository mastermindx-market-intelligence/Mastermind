# RL_TEAMMATE_LIMITS — what actually binds a steered teammate

Written for the independent reviewer of lane RL (branch `t3/mmos-v4-rl`).
Every claim below is either cited to server source (pin
`~/.mastermind/t3-team-server/pin-0770446-textdelta`, read-only) or proved
live on the lane dev server (`~/.mastermind/mmos_dev/rl`, port 50821) with
evidence files in `~/.mastermind/mmos_evidence/rl-20261111/`.

## 1. How a teammate session actually launches

A teammate is a T3 thread pinned to a per-teammate provider instance
(`claudeAgent` driver) whose `config.homePath` is the teammate home folder
and whose `config.launchArgs` carry `--append-system-prompt-file
<home>/CHARTER.md` and `--settings <home>/tool-limits.json`
(`tools/mmos_team_server/team_roster.py`, `instance_for`).

- `homePath` becomes `CLAUDE_CONFIG_DIR` in the session environment; `HOME`
  is deliberately unchanged (macOS Keychain access) —
  `apps/server/src/provider/Drivers/ClaudeHome.ts:15-46`. **The teammate
  home is the Claude configuration folder.**
- The server consumes the launchArgs flags itself (`--settings` → SDK
  `settings` option, `--append-system-prompt-file` → appended system prompt);
  they are not raw argv (`ClaudeAdapterV2.ts:1785-1845`).
- The session process is `/bin/sh -c <group-watch script> t3-claude
  <command>...` — a wrapper plus the CLI; `session_processes` in
  team_roster.py reports exactly those two PIDs (`ClaudeAdapterV2.ts:360-400`).
- Permission mode: the thread's `runtime_mode` decides
  (`full-access` → **bypassPermissions**), and a launchArgs
  `--permission-mode` beats everything (`ClaudeAdapterV2.ts:1841-1845`,
  `:2803-2850`). The dev thread and the real team threads run
  `full-access`.

## 2. What binds and what does not (all proved live, evidence 06/09)

| control | binds? | proof |
|---|---|---|
| `permissions.deny` path rules (Read/Grep/Glob) | **YES** | probe 1-3 in 09; real-server TSR probes in R2a |
| `permissions.deny` bare tool name | **YES — removes the tool from the toolset entirely** (stronger than call-time refusal) | Bash probe in 06 |
| `*` wildcards inside deny paths | **YES** | `*.txt` probe in 09 |
| symlink whose given path is not denied but whose target is | **REFUSED — the matcher resolves links** | symlink probe in 09 |
| `permissions.allow` as a restriction | **NO — inert in bypassPermissions** | unmatched Write outside every root succeeded instantly (06) |
| a tool call matching neither allow nor deny | **silently allowed** (no prompt, no hang) | 06, action 2 |

Consequences:

1. Every restriction must be a **deny** rule. Allow lists only document
   intent (they would bind only under a prompting mode, and a headless
   session then stalls on unmatched calls — mode changes are the
   principal's call).
2. Deny rules bind at **process start**. A rewritten `tool-limits.json`
   does not affect a running session (principal's live finding; `apply`
   now reports `limitsPendingRestart` per teammate with a plain
   not-in-force-until-restart line and the running PIDs).
3. `settings.json` planted in the teammate home **loads at the next
   process start and its hooks run commands inside teammate turns**
   (proved with a PreToolUse canary hook, evidence 06 — four firings).
   That is why the `HOME_CONFIG` write denies matter: a steered teammate
   that could write its home's `settings.json`/`.mcp.json`/`skills/` gains
   arbitrary command execution on the next restart.

## 3. The rooted design (spec keys; absent = exactly today's rules)

`allow_read_roots` and `home_write_allow` compile to deny rules in
`tool_limits()` (Q2/Q3). Both are second layers: every existing deny
survives, deny wins, and a spec without the keys (or with empty lists)
generates byte-identical permissions to today's (regression test
`test_absent_keys_give_exactly_today_rules`).

- `allow_read_roots` (list of absolute dirs): reads allowed only under
  those roots plus the teammate's own home. Compiled by **sibling
  enumeration from `/` down each root's chain**: every directory not on a
  chain gets file+tree denies for Read/Glob/Grep; chain directories get
  file-form denies only (a tree form would deny the allowed root below
  them, and deny wins). The own home stays readable; locked files stay
  denied. Plain `Read`/`Glob`/`Grep` allows are replaced by rooted allows
  (documentation under bypass; correct if a mode ever changes).
  Bonus vs today: the enumeration denies `~/.t3` and every other user
  folder for reads, which today's deny list does not cover.
- `home_write_allow` (list of home-relative names, e.g. `["CLAUDE.md",
  "notes/"]`): replaces the home-wide write allow. Every existing home
  child except the allowed names is denied (Write+Edit, file+tree), all
  `HOME_CONFIG` and `HOME_LOCKED` names are denied whether or not they
  exist, and the allowed names/subtrees stay writable.
- `assets_dir` (Q4): moves `tool-limits.json`/`CHARTER.md` out of the
  teammate home (launchArgs point at the new location; other teammates
  get read-denies on it). Cheap and provable; the in-home files become
  impossible rather than merely denied.

## 4. What a list still does not cover (stated plainly)

- **Future top-level names in the home**: a file named neither in
  `HOME_CONFIG`/`HOME_LOCKED` nor among existing children at apply time is
  creatable under `home_write_allow` (unmatched = allowed). It is
  writable-but-not-loaded: Claude Code loads config only under the known
  names, all of which are denied. The list is the maintenance surface —
  a reviewer re-checks `HOME_CONFIG` against the CLI's config inventory.
- **Symlink escapes are blocked by the matcher** (it resolves links —
  evidence 09), so a link inside an allowed root pointing outside is
  refused when the target is denied. A link to an *undenied* target is
  readable, same as the target itself; rooting denies the targets.
- **Glob name enumeration one level above an allowed root** is closed by
  the chain-dir file-form denies; listing `/` itself is not denied
  (top-level names only).
- **Web tools** remain unrestricted for all teammates (Q5, evidence 07);
  a domain allowlist is not enforceable under bypass (allow rules inert).
- **Deny beats allow at any specificity** (evidence 09b): a more-specific
  allow inside a tree deny does NOT unlock the subtree. There is no
  gitignore-style cascade, so a compact deny/allow cascade is impossible
  and the enumeration must be precise.
- **The 203-deny real file grows to ~5,000 deny rules** under the rooted
  keys (measured on this Mac: 838 non-chain sibling paths across the
  chain levels — 710 of them in the user home alone — times 6 rules each,
  ~300 KB). The round-2 dev proof validates that the CLI loads and
  enforces a generated file of that shape.

## 5. Safe session restart (for installing new limits)

Limits bind at process start, so installing new limits for a teammate
requires its session process to restart. Server-side, the safe stop is
`thread.stop` / `releaseUnlessBusy` (`ProviderSessionManager.ts:2585-2629`),
which refuses to release a session busy on another thread. Idle sessions
self-exit after **30 minutes** (`DEFAULT_IDLE_TIMEOUT_MS`,
`ProviderSessionManager.ts:59`; up to 4 h while pinned, `:60`). Proved on
the dev server only (evidence 06): SIGTERM to the two idle session
processes, server healthy, next `t3 thread send` spawns fresh processes
and resumes the same thread with full history (transcript-based resume,
`ClaudeAdapterV2.ts:1806-1808`; the transcript lives under
`<home>/projects/`, so never delete a teammate home to force a restart).
**Never end a process on the real server from this lane.**

## 6. Proofs and their evidence files

| claim | evidence |
|---|---|
| launch mode, unmatched write allowed, Bash tool removed, hook canary, safe restart | `06-launch-mode-probe.md` + `06-*` |
| deny binds for Read/Grep/Glob, `*` wildcards, symlink resolution | `09-rule-semantics-probe.md` + `09-reply.txt` |
| Q1 source citations and reconciliation (incl. two child claims refuted by live proof) | `08-q1-child-answers.md`, `08-q1-reconciliation.md` |
| web-tool facts for the three real charters | `07-q5-web-facts.md` |
| Part A atomic writes / Paperclip binding / pairing URL | ledger lines 1-5 in `LEDGER.md` |

## 7. Proposed spec diff for the real roster (for the principal)

Not written yet — appended after the rooted keys are implemented and
proved live (round 2), with exact `allow_read_roots` /
`home_write_allow` / `assets_dir` values for Assurance, Design Lead and
Secretary.

## 8. What could not be proved

- Whether the real team threads' `runtime_mode` is `full-access` was not
  read from the real server (no request, no DB read beyond the allowed
  file); the dev thread is `full-access` and the principal's live evidence
  (same process across 16 minutes, denies binding, unmatched writes
  landing) matches `bypassPermissions` behavior.
- Idle self-exit (30 min) is source-cited, not waited out live.
- The Claude CLI's internal rule evaluation is not in the server tree;
  every CLI-side claim here is live-probed instead (06/09).
