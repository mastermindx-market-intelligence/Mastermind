# RL_TEAMMATE_LIMITS — what actually binds a steered teammate

Written for the independent reviewer of lane RL (branch `t3/mmos-v4-rl`).
Every claim below is either cited to server source (pin
`~/.mastermind/t3-team-server/pin-0770446-textdelta`, read-only) or proved
live on the lane dev server (`~/.mastermind/mmos_dev/rl`, port 50821) with
evidence files in `~/.mastermind/mmos_evidence/rl-20261111/`.

> **Repair round 1 (2026-11-11, after the blind panel's 19 findings):**
> the fence now has a PRIMARY layer — a PreToolUse hook gate
> (`teammate_gate.py`) installed by `apply` at `<server root>/bin`
> (0555, no teammate can write there) and wired into every
> tool-limits.json as `{"matcher": "*"}` — plus the deny-rule snapshot
> (this document's sections 2–3) as the SECOND layer. See §3a. The gate
> resolves every path (symlinks, `..`, `//`, `/./`, case on a
> case-insensitive volume, Unicode form, firmlinks) at call time, roots
> reads (home + workspace + `allow_read_roots`), fences writes to the
> home minus protected names, refuses loopback/private/link-local web
> targets by resolved address, and refuses every tool not on the
> teammate's allowlist. Fail-open caveat stated in §3a.

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
| exact-path `Read(//path)` rule alone | **DOES bind** (asymmetric with Write) | 11, S1 (2-rule file, exact-only Read on an existing file → refused) |
| macOS firmlink spellings (`/System/Volumes/Data/Users/...`) | **the matcher canonicalizes them** — a `/Users`-spelled deny refused a Data-spelled read. realpath does NOT canonicalize (generator emits twin spellings as insurance) | 11, S2 |
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

## 3a. The PRIMARY fence: the PreToolUse hook gate (repair round 1)

One program, `tools/mmos_team_server/teammate_gate.py`, installed by
`apply` at `<server root>/bin/teammate_gate.py` (mode 0555 — `bin` is
Write-denied for every teammate, and the gate itself refuses writes
outside the home, so it protects its own binary). Each teammate's
`tool-limits.json` wires it as:

```json
{"hooks": {"PreToolUse": [{"matcher": "*", "hooks":
  [{"type": "command",
    "command": "<root>/bin/teammate_gate.py --config <root>/config/teammate-gate/<slug>.json",
    "timeout": 20}]}]}}
```

The per-teammate config (0600, under server-private `config/`) carries
`home`, `read_roots` (workspace + spec `allow_read_roots` — **always
rooted**, which is the P5 fix: the production spec needs no new key to
get read rooting), `deny_reads`, and `write_names` (mirrors
`home_write_allow`).

What it enforces at every tool call (all live-proved from a real seat,
evidence 12):

- **writes** (Write/Edit/NotebookEdit/MultiEdit): only inside the home,
  never a protected name (`HOME_LOCKED` ∪ `HOME_CONFIG` ∪
  `.claude.json.backup`); with `write_names`, only those entries.
- **reads** (Read): only inside home + read roots, minus `deny_reads`,
  checked AFTER resolution. In deny-list mode (spec without
  `allow_read_roots`) the deny list alone decides, matching the rule
  layer's semantics — but the production shape still gets rooting
  because the gate always roots to home + workspace + spec roots.
- **searches** (Glob/Grep): the search root must pass the read policy
  AND must not sit at or above a denied folder (P4: enumerating a
  denied folder's parent leaks its names); patterns must be relative
  and non-climbing.
- **web** (WebFetch + any `webReader` tool): the host is resolved;
  loopback, link-local, private and reserved addresses are refused —
  `localhost` was refused as `127.0.0.1` (probe 12), no request sent.
- **unknown tools / unparseable input / unreadable config**: refused.
  The live census surface (Workflow, SendMessage, ListAgents,
  ScheduleWakeup, Skill, `mcp__t3-code__request_secret`) is refused
  here AND bare-denied in the rule layer (`EXTRA_TOOL_DENIES`); those
  tools are NOT denied in the real server's shipped limits today —
  that gap is part of the install recommendation.

**Spelling family closed by resolution**: the gate resolves symlinks,
`..`, `//`, `/./`, expands `~`, canonicalizes each component to its
on-disk spelling (case) and compares NFC-casefold keys, and strips the
`/System/Volumes/Data` firmlink prefix. Live: case flips of protected
names, `~/.SSH/...`, `/USERS/...`, `//Users/...`, `/./`, and a symlink
inside the home pointing out were ALL refused (evidence 12, items 1–8;
the rule layer refused them — the matcher canonicalizes case and
firmlinks too — and the gate refuses them independently).

**Fail-open, stated plainly** (design ruling requirement): a hook that
exits any code other than 0/2, or a missing hook binary, lets the tool
call THROUGH (live-proved in the calibration round). Mitigations: the
gate wraps every decision in a fail-closed handler (any internal error
→ exit 2), refuses when its config is missing/corrupt, and
`apply`/`status` verify presence + sha256 + wiring, with `status`
exiting 1 and printing `FENCE BROKEN` on any problem. If the server's
hook support were ever removed, the second layer (deny rules) still
stands on its own.

**A new folder needs no regeneration** (step 6 of the panel score): the
gate resolves and roots at CALL time, so a folder created after apply is
still refused (unit test `test_gate_refuses_post_apply_folder_without_
regeneration`; live items 9–10 refused a fresh stand-in in `run/`). The
deny-rule snapshot is the layer that needs regeneration — re-running
`apply` regenerates it; no separate `refresh` command exists or is
needed.

**Cost**: 171–740 ms per gated tool call (Python startup + path
canonicalization), measured on a production-shaped config. Rule volume
is unchanged in kind: the dev seat ran 8,560 rules / 486 KB fully
enforced; the production shape generates 66,386 rules / 3.9 MB.

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
  Write/Edit denied on the path itself and its whole tree, built from
  realpath (a symlinked spelling would never match) plus its firmlink
  twin when under /Users.
- **Always-on write fence (attack round, findings 1-4)**: in every spec,
  with no new keys, Write/Edit are fenced to the teammate's own home by
  the same sibling enumeration. This closes what the attack round
  confirmed writable under the real spec today: the server's own home
  (its `userdata/settings.json` is watched and reloaded **live** by the
  running server — writing it rewrites launchArgs and can drop
  `--settings` at the next session spawn), `fabric.env`, every OTHER
  teammate's home (their limits/charter would bind at their next
  process start — lateral takeover), and the user's own config surfaces
  (`~/.zshenv`, `~/.ssh`, `~/Library/LaunchAgents`, `~/.claude`,
  `~/.codex`, `~/.gitconfig` — `deny_read_roots` never covered writes).
  The t3 CLI install dir (`dirname` of `server.t3_bin`) gets its own
  explicit deny: apply/status execute that binary with the team home,
  and it need not sit near the home chain. Live-proof: evidence 11,
  actions N1-N7.
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

- **Glob/Grep name enumeration on a chain directory** (rule-layer
  residual, CLOSED by the gate for search roots at/above denied folders
  and outside the read roots — gate §3a; live items 9–10): chain dirs
  carry no RULE (see D2), so the snapshot alone still lets a Glob whose
  path IS a chain directory list sibling NAMES one level above an
  allowed root. The gate refuses any search root outside home+roots and
  any root at/above a deny entry, so through the gate this is closed;
  it remains open only if the hook is missing/crashing (fail-open).
- **Future top-level names in the home** (rule-layer residual, CLOSED
  by the gate: `write_names` mode refuses every non-named entry, and
  default mode still refuses nothing NEW outside the home): a file
  named neither in `HOME_CONFIG`/`HOME_LOCKED` nor among existing
  children at apply time was creatable under `home_write_allow` (W7).
  Under the gate, a post-apply folder OUTSIDE the home/roots is refused
  without regeneration (§3a, step 6); inside the home the spec's own
  `write_names` decides. Load surfaces (shell startup files, launchd
  plists dir, `HOME_CONFIG`) are denied at both layers whether or not
  they exist (P3).
- **Symlink escapes are blocked by the matcher AND by the gate** (both
  resolve links — evidence 09, gate unit tests, live item 8): a link
  inside an allowed root pointing outside is refused when the target is
  outside the roots or denied.
- **Web tools**: the GATE refuses loopback/link-local/private/reserved
  targets by resolved address and requires http(s) (live, evidence 12,
  items 11–12; closed port also refused). Remaining rule-layer residual
  without the gate: a public-destination WebFetch is unrestricted (Q5,
  evidence 07) — exfiltration to a public host is NOT prevented by
  either layer; that is a charter/trust matter, stated plainly.
- **Deny beats allow at any specificity** (evidence 09b): a more-specific
  allow inside a tree deny does NOT unlock the subtree. There is no
  gitignore-style cascade, so a compact deny/allow cascade is impossible
  and the enumeration must be precise.
- **Rule volume**: the always-on write fence alone compiles to ~3,400
  deny rules on this Mac (838 non-chain sibling paths, 710 of them in
  the user home alone, × 4); with the rooted read keys the final
  measured dev file is 8,560 rules / ~486 KB, and the production shape
  (no rooted keys, P3/P5 user-protected family included) generates
  66,386 rules / 3.9 MB. No cap was observed — files of that size load
  and enforce fully (panel scratch runs to 167k) — but apply time, file
  size and per-call hook latency (§3a) are the cost.

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
| attack round: 12 findings + dispositions, exact-Read binding (S1), firmlink canonicalization (S2), final 8-action fence proof on the 445c2662e-generated file (N1-N7 refused, N8 allowed, disk clean) | `11-attack-round-and-fixes.md`, `11-attack-findings.txt`, `11-fence-probe-reply.txt` |
| repair round 1: the hook gate live from a real seat (12/12 probes refused, hook-text refusals for search/web), hook freshness in a running session, restart semantics, `.claude.json` corruption blocks start (backup not honored), volume + latency, status verification | `12-gate-hook-live-proof.md` |
| Q1 source citations and reconciliation (incl. two child claims refuted by live proof) | `08-q1-child-answers.md`, `08-q1-reconciliation.md` |
| web-tool facts for the three real charters | `07-q5-web-facts.md` |
| Part A atomic writes / Paperclip binding / pairing URL | ledger lines 1-5 in `LEDGER.md` |

## 7. Proposed spec diff for the real roster (for the principal)

Not applied by this lane (`specs/team_roster.json` is outside my edit
scope). After the attack-round fixes (commit 445c2662e) the write fence
is always-on — the server's own home, `fabric.env`, other teammates'
homes, the t3 install dir and the user's config surfaces no longer need
spec entries. The proposed diff is exactly two added keys:

```json
+"allow_read_roots": ["~/.mastermind/t3-team/team-project"],
+"home_write_allow": ["CLAUDE.md"],
```

Optional belt-and-braces (covered by the always-on fence already):
adding `"/Users/chriswong/.mastermind/t3-team-server"` and
`"/Users/chriswong/Library/LaunchAgents"` to `deny_write_roots` is
harmless but redundant.

What each key does for Assurance, Design Lead and Secretary (the keys
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
  locked/config names can never be granted (refused at load). TodoWrite
  is unaffected (its permission is the bare tool name, not a Write path
  rule).

Install procedure (section 5): edit the spec, `team_roster.py apply`
(writes new `tool-limits.json` per home + installs the gate + writes
gate configs, reports `limitsPendingRestart` with the running PIDs),
let each teammate's session restart at a safe boundary (30-min idle
self-exit or an attended `thread.stop`/`releaseUnlessBusy` — never from
this lane on the real server), then confirm the new processes started
after the file mtimes. Expected size: ~8,500 deny rules per teammate on
this Mac (~480 KB; loads fully — evidence 10/11); the production shape
(no rooted keys) generates ~66,000 rules / ~3.9 MB per teammate with
the P3/P5 user-protected family included. Apply is content-diffed: when
the surrounding directories change, the generated rules change and the
next apply rewrites the file — re-run apply after any team-layout
change (the `_note` in each generated file says so). The GATE layer
needs no regeneration for new folders (§3a, step 6).

Two install notes from repair round 1:

1. The gate program (`teammate_gate.py`) must ship beside
   `team_roster.py` in the installed tools tree — `apply` refuses to run
   without it (a missing hook is fail-open, so absence is fatal, not
   cosmetic).
2. The real server's currently-shipped limits do NOT deny
   Workflow/SendMessage/ListAgents/ScheduleWakeup/Skill/
   `mcp__t3-code__request_secret` (live census, evidence 12 round C3).
   The generated limits now bare-deny them (`EXTRA_TOOL_DENIES`) and the
   gate refuses them at call time; installing the new limits closes
   that gap on the real roster.

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
- Repair round 1: the gate was live-proved on the DEV seat only; the
  real roster's fence must be verified with `status` (which now checks
  limits-bytes, gate sha, hook wiring and instance launchArgs) plus one
  spelling-family probe from a real seat before any credential-bearing
  roster relies on it (the panel's own condition). WebFetch
  exfiltration to PUBLIC hosts remains possible at both layers (only
  loopback/private is refused); that is accepted residual, §4.
