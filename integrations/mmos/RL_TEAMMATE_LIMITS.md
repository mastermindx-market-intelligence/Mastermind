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
| `permissions.deny` path rules (Read/Grep/Glob) | **YES — but only from a settings file inside the teammate home** (see next row) | probe 1-3 in 09; E3 in 10 |
| Read/Glob/Grep denies in a settings file OUTSIDE the home | **NO — silently never bind.** The file loads; Write/Edit tree rules in it still bind. `--settings` must point inside the home | E2b vs E3 in 10 (same 9-rule file, both directions) |
| `permissions.deny` bare tool name | **YES — removes the tool from the toolset entirely** (stronger than call-time refusal) | Bash probe in 06 |
| `*` wildcards inside deny paths | **YES** | `*.txt` probe in 09 |
| a deny rule naming a DIRECTORY | **matches the directory's whole subtree** ("File is in a directory that is denied") — never deny a chain directory in any form | 10, D2: first-cut design refused all 21 actions incl. allowed roots |
| exact-path `Write(//path)` rule alone | **never binds — the `//path/**` member is what binds** | 10, D3 (and 10b: this was guarding the teammate's own limits file) |
| single-slash forms `Read(/path)`, `Write(/path)` | **never bind; the generator's `//path` double-slash form is required** | 10, D4 |
| symlink whose given path is not denied but whose target is | **REFUSED — the matcher resolves links** | symlink probe in 09 |
| `permissions.allow` as a restriction | **NO — inert in bypassPermissions** | unmatched Write outside every root succeeded instantly (06) |
| a tool call matching neither allow nor deny | **silently allowed** (no prompt, no hang) | 06, action 2 |
| number of rules in one settings file | **no cap observed: 8,409 deny rules / 480,927 bytes load and enforce fully in-home** | 10, final run |

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
  enumeration**: collect every chain from `/` down to each root (the own
  home included), then every directory NOT on any chain gets file+tree
  denies for Read/Glob/Grep. **Chain directories get no rule in any
  form** — a deny on a directory matches its whole subtree, so even a
  file-form deny on a chain directory refuses the allowed roots beneath
  it (live-proved, 10 D2: the first-cut design did exactly that and
  refused all 21 probe actions, allowed reads included). Enumeration is
  two-pass so a directory that sits on root 2's chain is never denied as
  root 1's sibling. Locked files stay denied; plain
  `Read`/`Glob`/`Grep` allows are replaced by rooted allows
  (documentation under bypass; correct if a mode ever changes).
  Bonus vs today: the enumeration read-denies `~/.t3`, every other user
  folder, AND every other teammate's home — none of which today's deny
  list covers.
- `home_write_allow` (list of home-relative names, e.g. `["CLAUDE.md",
  "notes/"]`): replaces the home-wide write allow. The named entries stay
  writable; every existing home child and every `HOME_CONFIG` /
  `HOME_LOCKED` name is denied (Write+Edit, file+tree) whether or not it
  exists — locked/config names are never grantable even if a spec lists
  them. With this key set, the same sibling enumeration is also emitted
  for Write/Edit, so writes outside the home + read roots are denied
  structurally. Note the scopes: `allow_read_roots` are *read* scopes;
  the shared workspace stays write-denied by the base rule regardless.
- `deny_write_roots` (list of absolute paths, predates round 2):
  Write/Edit denied on the path itself and its whole tree. `abspath` does
  not expand `~` — entries must be absolute or `~`-expanded by the caller.
- `SERVER_INFRASTRUCTURE` (no key; always on): Write/Edit denies
  (file+tree) for `<server root>/{bin,config,runtime,run}` in every
  spec. Whoever can write those folders chooses which program the server
  runs at its next start — the defense cannot be optional.
- `assets_dir` (Q4): **implemented, then removed and refused by
  `load_spec`.** Moving the `--settings` file outside the teammate home
  loads it, but its Read/Glob/Grep deny rules then silently never bind
  (10 D1 — proved both directions with the same 9-rule file), so the
  "hardening" disabled the read fence while keeping the write fence:
  a regression. `tool-limits.json` and `CHARTER.md` stay in the home,
  guarded by `HOME_LOCKED` file+tree denies (live-proved in 10b).

## 4. What the rooted design still does not cover (stated plainly)

- **Glob/Grep name enumeration on a chain directory** (accepted residual):
  chain dirs carry no rule (see D2), so a Glob whose path IS a chain
  directory runs and lists its names — revealing sibling names one level
  above an allowed root (R4 in the final probe: 3 names). Names only,
  never content: the siblings themselves stay denied (R3/R5 refused).
  Listing `/` itself is likewise not denied. Closing this would require
  denying a chain directory, which denies the allowed root beneath it.
- **Future top-level names in the home**: a file named neither in
  `HOME_CONFIG`/`HOME_LOCKED` nor among existing children at apply time is
  creatable under `home_write_allow` (W7 in the final probe: ALLOWED).
  It is writable-but-not-loaded: Claude Code loads config only under the
  known names, all of which are denied. The list is the maintenance
  surface — a reviewer re-checks `HOME_CONFIG` against the CLI's config
  inventory.
- **Symlink escapes are blocked by the matcher** (it resolves links —
  evidence 09), so a link inside an allowed root pointing outside is
  refused when the target is denied (R6 in the final probe). A link to an
  *undenied* target is readable, same as the target itself; rooting
  denies the targets.
- **Web tools** remain unrestricted for all teammates (Q5, evidence 07);
  a domain allowlist is not enforceable under bypass (allow rules inert).
- **Deny beats allow at any specificity** (evidence 09b): a more-specific
  allow inside a tree deny does NOT unlock the subtree. There is no
  gitignore-style cascade, so a compact deny/allow cascade is impossible
  and the enumeration must be precise.
- **Rule volume**: on this Mac the rooted keys compile to ~8400 deny
  rules / ~480 KB (838 non-chain sibling paths, 710 of them in the user
  home alone, × 6 rules each, plus base rules). No cap was observed —
  the dev proof's 8,409-rule file loaded and enforced fully — but apply
  time and file size are the practical cost of deny-only rooting.

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
| deny absolute over allow; no cascade | `09b-*` |
| round-2 rule semantics: settings-in-home requirement (D1), directory-subtree matching (D2), exact-write forms (D3), single-slash forms (D4), no rule cap; final 21-action proof of the rooted design incl. infrastructure refusals; invalid runs disclosed | `10-rule-semantics-round2.md` + `10-probe-reply.txt` |
| HOME_LOCKED exact-form hole and the tree-member fix, live-proved on today's-shape rules | `10b-locked-tree-member-proof.md` + `10b-probe-reply.txt` |
| Q1 source citations and reconciliation (incl. two child claims refuted by live proof) | `08-q1-child-answers.md`, `08-q1-reconciliation.md` |
| web-tool facts for the three real charters | `07-q5-web-facts.md` |
| Part A atomic writes / Paperclip binding / pairing URL | ledger lines 1-5 in `LEDGER.md` |

## 7. Proposed spec diff for the real roster (for the principal)

Not applied by this lane (`specs/team_roster.json` is outside my edit
scope). Exact proposed change — two added keys, two added entries:

```json
 "deny_write_roots": [
   "/tmp",
   "/private/tmp",
   "/private/var/folders",
+  "/Users/chriswong/.mastermind/t3-team-server",
+  "/Users/chriswong/Library/LaunchAgents"
 ],
+"allow_read_roots": ["~/.mastermind/t3-team/team-project"],
+"home_write_allow": ["CLAUDE.md"],
```

What each piece does for Assurance, Design Lead and Secretary (the keys
are spec-level; all three teammates get the same compile):

- `allow_read_roots: ["~/.mastermind/t3-team/team-project"]` — reads
  rooted to the shared workspace plus each teammate's own home. Per the
  charters (evidence 07): Assurance reviews artifacts, Design Lead
  critiques artifacts, Secretary reads/notes — all in the team
  workspace; charter sources (`~/.hermes/.../SOUL.md`) are build-time
  inputs apply already inlined, not runtime reads. Side effects that are
  pure gains: every other user folder (`~/.t3`, `~/.claude`, `~/.ssh`,
  …) and every OTHER teammate's home become read-denied — today nothing
  denies them. If a future workflow needs another root, it is one more
  list entry (per-teammate rooting is not implemented; a teammate that
  genuinely needs a different root than its peers needs that follow-up).
- `home_write_allow: ["CLAUDE.md"]` — all three charters define the
  home CLAUDE.md as the only long-term memory ("nothing else
  persists"); Secretary's records go to issue comments, not home files.
  Add `"notes/"` for a teammate if the principal wants scratch space;
  locked/config names can never be granted. TodoWrite is unaffected
  (its permission is the bare tool name, not a Write path rule).
- `deny_write_roots` + the two absolute paths — the server build folder
  and LaunchAgents: whoever can write them chooses which program runs at
  next start (the infrastructure proof, refusals I5/I6). The
  `<root>/{bin,config,runtime,run}` folders are already covered
  always-on by `SERVER_INFRASTRUCTURE`, no spec entry needed.

Install procedure (section 5): edit the spec, `team_roster.py apply`
(writes new `tool-limits.json` per home, reports
`limitsPendingRestart` with the running PIDs), let each teammate's
session restart at a safe boundary (30-min idle self-exit or an
attended `thread.stop`/`releaseUnlessBusy` — never from this lane on
the real server), then confirm the new processes started after the
file mtimes. Expected size: ~8,400 deny rules per teammate on this
Mac (~480 KB; loads fully — evidence 10).

## 8. What could not be proved

- Whether the real team threads' `runtime_mode` is `full-access` was not
  read from the real server (no request, no DB read beyond the allowed
  file); the dev thread is `full-access` and the principal's live evidence
  (same process across 16 minutes, denies binding, unmatched writes
  landing) matches `bypassPermissions` behavior.
- Idle self-exit (30 min) is source-cited, not waited out live.
- The Claude CLI's internal rule evaluation is not in the server tree;
  every CLI-side claim here is live-probed instead (06/09/10/10b).
  Round-2 probes are n=1 per cell (same file and actions across the
  contrast pair wherever it matters — D1's location pair used one
  identical 9-rule file); the CLI build probed is whatever `t3-claude`
  resolves at spawn on this Mac today.
- Several probe runs were invalidated mid-round (stale session processes
  surviving a kill, one wrapper respawn with old launchArgs); every
  invalid run, including one that briefly landed real canary files
  outside the dev root before deletion, is disclosed in
  `10-rule-semantics-round2.md`. Only runs with verified
  process-start > limits-mtime count as proof.
