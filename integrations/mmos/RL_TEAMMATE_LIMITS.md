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

> **Repair round 2 (2026-11-11, after panel 2 scored `7e9a29aa4` —
> "install: ready after listed repairs"):** all nine repairs landed in
> two commits — `9cd4df3a7` (R1–R6) and `2f82f6c8a` (the rule-layer
> cut). The gate's web check now reads exactly the `url` field and
> refuses every address literal, so only plain DNS names pass to
> resolution, where every resolved address must clear an explicit
> refusal-net list stricter than `is_global` (R1/R2/R6a). The hook
> command is interpreter-isolated and fail-closed:
> `/usr/bin/env python3 -I '<gate>' --config '<cfg>' || exit 2` (R4 —
> hooks run with `HOME` = the real user home). One unreadable set
> (preimage, credentials, `.claude.json` + backups, carrier, limits,
> `settings*.json`, `projects/`) gates reads AND search roots, with
> searchable-folder hints (R3). `@` import lines are refused in
> client-loaded files (R5 — the client resolves them at session
> start). The rule layer is bare census denies plus the score's
> "Volume" short list (R6b): **8,629 → 1,127 deny rules, 441 → 69 KB
> per teammate.** `status` now fails on gate-mode drift, missing
> python3, `disableAllHooks`, or a canary that does not exit 2 (R6c).
> Live probes: evidence 13. Residuals in §4, plainly.

> **Repair round 3 (2026-11-11, after panel 3 — the last round under the
> programme's repair-loop rule):** three of four findings fixed, one
> commit each — `9d4c75ad3` (H-2: the unreadable set is now DERIVED from
> the gate's one canonical list, so the read fence can no longer drift
> from the write-fence class; `.claude/settings.json`,
> `.claude/.credentials.json`, `.mcp.json`, `keybindings.json`,
> `sessions/`, `CLAUDE.md.backup` and friends are unreadable at both
> layers), `506645157` (M-R1: config-side firmlink spellings are
> canonicalized at load — a Data-prefixed `home`/`read_roots`/`deny_reads`
> entry binds identically to its primary spelling; non-string entries are
> refused), `d891ef66b` (M-R2: the hook interpreter is the validated
> absolute binary `/usr/bin/python3`, checked at apply and by `status` —
> no PATH lookup; live before/after proof: the as-was 0000-mode refusal
> showed homebrew Python 3.14 executing the gate, the fixed one shows the
> Xcode CLT shim target of the pinned path). H-1 (DNS rebinding +
> redirects, one root) is NOT closeable inside the spec + gate and was
> escalated with five costed options (`dec288b79`, evidence 15) —
> `h1=needs-decision`; no half-measure was shipped. Rule layer grows to
> **1,355 deny rules (95.8 KB)** covering the H-2 config class. All 9
> probes (the seven + H-2 + M-R1) PASS on the round-3 install: evidence
> 16. Kept rulings held: url-field web check, one unreadable set for
> Read/Glob/Grep incl. preimage and Claude config, `|| exit 2` +
> `python3 -I`.

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

## 3a. The PRIMARY fence: the PreToolUse hook gate (repair rounds 1–2)

One program, `tools/mmos_team_server/teammate_gate.py`, installed by
`apply` at `<server root>/bin/teammate_gate.py` (mode 0555 — `bin` is
Write-denied for every teammate, and the gate itself refuses writes
outside the home, so it protects its own binary). Each teammate's
`tool-limits.json` wires it as:

```json
{"hooks": {"PreToolUse": [{"matcher": "*", "hooks":
  [{"type": "command",
    "command": "/usr/bin/python3 -I '<root>/bin/teammate_gate.py' --config '<root>/config/teammate-gate/<slug>.json' || exit 2",
    "timeout": 20}]}]}}
```

Round 2 (R4) rewrote that command and round 3 (M-R2) pinned its
interpreter; each part earns its place (`test_r4_gate_command_shape`,
`test_r4_fail_closed_through_the_wired_command`, `test_mr2_*`, live
evidence 13 items 4–5 and 16):

- **Both paths single-quoted** by the generator — a server root
  containing a space still parses (tested with root `"server root"`).
- **`-I` (isolated mode)** — hooks run with `HOME=/Users/chriswong`
  (the REAL user home; only `CLAUDE_CONFIG_DIR` points at the teammate
  home — live-captured, evidence 13 item 4), so a bare `python3` hook
  would load `usercustomize.py` and user site-packages from the user's
  own home, a file any teammate could try to plant. `-I` skips
  site-packages, `PYTHON*` env vars and usercustomize (panel N1).
- **`/usr/bin/python3` (pinned, M-R2)** — an absolute, validated binary:
  `apply` and `status` both die if it is missing or not executable, so
  the hook never resolves an interpreter through the runtime PATH (the
  as-was defect, proved live: `/usr/bin/env python3` let PATH pick
  homebrew Python 3.14 to execute the gate — evidence 16 baseline). The
  gate's own exec bit is irrelevant to this command (`python3 <file>`
  reads the file); mode integrity is `status`'s job (R6c).
- **`|| exit 2`** — the client fails OPEN on any hook exit other than
  0/2 (panel M2); the wrapper collapses crash (exit 1), kill, missing
  file and unreadable file all to 2 = refuse. Live: gate at mode 0000
  → the client shows the refusal.

The per-teammate config (0600, under server-private `config/`) carries
`home`, `read_roots` (workspace + spec `allow_read_roots` — **always
rooted**, which is the P5 fix: the production spec needs no new key to
get read rooting), `deny_reads`, and `write_names` (mirrors
`home_write_allow`).

What it enforces at every tool call (live-proved from a real seat,
evidence 12 for round 1, evidence 13 for the round-2 checks):

- **writes** (Write/Edit/NotebookEdit/MultiEdit): only inside the home,
  never a protected name (`HOME_LOCKED` ∪ `HOME_CONFIG` ∪
  `.claude.json.backup`); with `write_names`, only those entries.
  Writes into ANOTHER teammate's home are refused by the same
  home-fence line (`test_bcu_m14_write_into_other_teammate_home_refused`
  — lane BCU's M14 question, answered yes with a pinned test).
- **@ import lines** (R5): Write/Edit/MultiEdit are refused when the
  new content would add a line starting with `@` to a client-loaded
  file (`CLAUDE.md` and friends). Why load-bearing: the client
  RESOLVES `@/abs/path` imports in CLAUDE.md at session start and
  pulls the target into model context with no warning (live, N2,
  evidence 13) — a planted import is a read-primitive outside every
  fence. @ lines in non-client-loaded files (`notes/memo.md`) stay
  allowed.
- **reads** (Read): only inside home + read roots, minus `deny_reads`,
  checked AFTER resolution. In deny-list mode (spec without
  `allow_read_roots`) the deny list alone decides, matching the rule
  layer's semantics — but the production shape still gets rooting
  because the gate always roots to home + workspace + spec roots
  (spec `home`/`read_roots`/`deny_reads` spellings are canonicalized
  at gate-config load, M-R1 — a Data-prefixed firmlink spelling binds
  identically to its primary twin, and a non-string entry refuses the
  config).
  One unreadable set (R3 + round-3 H-2): the runtime-private names
  (`cutover-preimage.json`, `cutover-result.json`, `carrier.json`,
  `tool-limits.json`), restart backups (`.claude.json.backup`,
  `CLAUDE.md.backup`), and the whole Claude-config class
  (`CLAUDE_CONFIG_NAMES`: `.claude/settings.json`,
  `.claude/.credentials.json`, `.mcp.json`, `keybindings.json`,
  `sessions/`, `.claude.json` + backups, `settings*.json`,
  `projects/`, …) — **derived from the gate's one canonical list**
  (`teammate_gate.py` exports it; `team_roster.py` imports and derives
  HOME_UNREADABLE/HOME_LOCKED/HOME_CONFIG from it), so the read fence
  and the write-fence class cannot drift apart; the rule layer carries
  the same expansion, sync-tested.
- **searches** (Glob/Grep): the search root must pass the read policy,
  must not sit at or above any unreadable/denied path (P4 + R3), and
  when refused the message NAMES searchable folders ("search instead:
  <workspace>, <home>/notes"). Patterns containing braces (`{...}`),
  backslashes or `..` are refused outright (R2 family; live: `{..}/*`
  arrives at the hook VERBATIM — the client does not expand braces
  before PreToolUse, N3).
- **web** (WebFetch + any `webReader` tool): the gate reads exactly
  the `url` field (R1 — a public address in `prompt` never reaches
  the check; live item 1a) and refuses BEFORE any request on: any
  address literal in any notation (dotted, integer, octal `0177.0.0.1`,
  hex, IPv6), userinfo, backslashes (incl. the `\@` confusion form),
  whitespace/control characters, percent- or non-ASCII authority,
  non-http(s) schemes, and non-default ports. Only plain DNS-label
  hostnames (all-digit and 0x-prefixed labels refused) pass to
  resolution, and EVERY resolved address must clear an explicit net
  list (R6a): loopback, private, link-local, ULA, multicast,
  unspecified, reserved, IPv4-mapped/-compatible, NAT64
  (`64:ff9b::/96` and the IPv4-translatable well-known prefix),
  6to4, Teredo, and CGNAT `100.64.0.0/10` — stricter than
  `ipaddress.is_global`, which passes several of those (M1). DNS
  lookups run in a thread with a 5-second join (R4), so a hung
  resolver fails closed rather than hanging the call.
- **unknown tools / unparseable input / unreadable config**: refused.
  The census surface is refused here AND bare-denied in the rule
  layer (`TOOL_DENY_CENSUS`, §3); those tools are NOT denied in the
  real server's shipped limits today — that gap is part of the
  install recommendation.

**Spelling family closed by resolution**: the gate resolves symlinks,
`..`, `//`, `/./`, expands `~`, canonicalizes each component to its
on-disk spelling (case) and compares NFC-casefold keys, and strips the
`/System/Volumes/Data` firmlink prefix. Live: case flips of protected
names, `~/.SSH/...`, `/USERS/...`, `//Users/...`, `/./`, and a symlink
inside the home pointing out were ALL refused (evidence 12, items 1–8;
the rule layer refused them — the matcher canonicalizes case and
firmlinks too — and the gate refuses them independently).

**Fail-open, stated plainly** (design ruling requirement): the CLIENT
lets the call through on any hook exit other than 0/2 and on a missing
hook binary (live-proved in the calibration round). Round 2 closes
what a wrapper can close: `|| exit 2` collapses every non-0/2 exit
(crash, kill, unreadable gate — live item 5) to refuse; the gate wraps
every decision in a fail-closed handler (any internal error → exit 2,
and `refuse` survives a broken stderr pipe); it refuses on
missing/corrupt config. `status` (R6c) now fails with exit 1 /
`FENCE BROKEN` when the gate mode is not exactly 0555, `python3` is
not on PATH, any applying settings file sets `disableAllHooks`, or the
wired canary call does not exit 2 — so a drifted fence is caught
before a teammate sits down, not mid-call. What no wrapper closes: the
client itself timing out or killing the hook (20 s wired; the gate
answers in tens of ms), the hook subsystem being removed server-side
(the rule layer still stands alone), and the gate binary being
replaced by something that exits 0 — which is exactly what the canary
and sha256 checks exist to catch.

**A new folder needs no regeneration** (step 6 of the panel score): the
gate resolves and roots at CALL time, so a folder created after apply is
still refused (unit test `test_gate_refuses_post_apply_folder_without_
regeneration`; live items 9–10 refused a fresh stand-in in `run/`).
Since the round-2 cut the deny-rule snapshot no longer tracks the
surrounding directories at all — re-running `apply` matters only for
spec edits (roots, census, `deny_read_paths`); no separate `refresh`
command exists or is needed.

**Cost**: 20 warm gate calls ran at 56.0 ms/call in a quiet moment;
143.4 ms/call best-of-5 under machine load ~45 (the spread is load,
not code — round-1 measurements of 171–740 ms were taken on the same
loaded box). **Rule volume, round 2 (the cut)**: 8,629 → 1,127 deny
rules (441 → 69 KB per teammate). The cut cannot change gate latency:
the gate never reads the rules file.

## 3. The rule layer after the round-2 cut (commit `2f82f6c8a`)

The gate is the primary fence, so the rule snapshot is now deliberately
SMALL: the two sibling enumerations (rooted reads; always-on write
fence) were deleted. Why they had to go: a directory deny matches its
whole subtree (live, 10 D2), so rooting by enumeration meant denying
every non-chain directory on the volume — 8,629 rules on the dev box,
~66,000 in the production shape — and the snapshot went stale whenever
the surrounding directories changed. The gate roots at CALL time
(§3a); the rules now keep only what the panel score's "Volume" short
list names:

- **Bare tool denies — `TOOL_DENY_CENSUS` (R6b)**: every
  non-allowlisted tool from the live census of the dev-server teammate
  session (Agent, AskUserQuestion, ListAgents, ReportFindings,
  ScheduleWakeup, Skill, Workflow, `mcp__t3-code__request_secret`,
  `mcp__web_reader__webReader`) plus a belt of client tools another
  build may offer (Bash, Task, LS, NotebookEdit/NotebookRead,
  SlashCommand, BashOutput, KillShell, EnterPlanMode/ExitPlanMode,
  Monitor, ReadMcpResource, ListMcpResources, MultiEdit, SendMessage,
  CronCreate/CronDelete/CronList). **Exact MCP names only** —
  live-proved (N4, evidence 13) that neither `mcp__*` wildcards, nor
  prefix forms, nor bare `webReader` binds; a new MCP tool needs a
  census update. Allowlist (Read, Glob, Grep, WebFetch, WebSearch,
  TodoWrite, ToolSearch) untouched.
- **Write/Edit file+tree denies** for: `HOME_LOCKED` ∪ `HOME_CONFIG` ∪
  backup names (inside the home, whether or not they exist);
  `SERVER_INFRASTRUCTURE` — `<server root>/{bin, config, runtime, run,
  home, claude-home}` and `fabric.env`; the t3 CLI install dir
  (`dirname` of `server.t3_bin`); every `deny_write_roots` entry
  (spec key, realpath + firmlink twin); every OTHER teammate's home;
  and the user-protected family (`~/.zshenv`, `~/.ssh`,
  `~/Library/LaunchAgents`, `~/.claude`, `~/.codex`, `~/.gitconfig`).
  These are the surfaces the attack round proved load-bearing (evidence
  11, N1–N7): the server's own `userdata/settings.json` is reloaded
  LIVE by the running server, and other homes' limits bind at their
  next process start — lateral takeover paths.
- **Read/Glob/Grep denies** for `deny_read_paths` (spec key, kept).

Spec keys unchanged in MEANING but not in compilation:
`allow_read_roots` and `home_write_allow` now configure the GATE config
(rooted reads; named home writes) instead of compiling to sibling
enumerations; locked/config names remain ungrantable either way. The
regression tests were rewritten to the cut semantics: read rooting
holds through named rules + gate
(`test_allow_read_roots_enforced_by_named_rules_and_gate`), and a home
that stops matching the spec fails closed
(`test_home_enumeration_fails_closed`).

Historical note (why `assets_dir` does not exist, Q4): moving the
`--settings` file outside the teammate home loads it, but its
Read/Glob/Grep deny rules then silently never bind (10 D1, proved both
directions with the same 9-rule file) — a "hardening" that disabled
the read fence while keeping the write fence. `tool-limits.json` and
`CHARTER.md` stay in the home, guarded by `HOME_LOCKED` denies
(live-proved in 10b), and `load_spec` refuses the key.

## 4. What is still not covered (stated plainly, after round 2)

The panel accepted the fence with these known residuals; they are the
principal's named list plus two round-2 discoveries:

1. **DNS rebinding**: a name that resolves public at check time and
   private at fetch time. The gate resolves when the hook fires; the
   client fetches afterwards. **Round 3 (panel 3 H-1): not closeable
   inside the spec + gate — a PreToolUse hook cannot pin what the client
   re-resolves at fetch time, and no second-resolve/TTL half-measure was
   shipped. Five options with costs and real-root requirements are
   escalated for decision in `15-h1-options.md` (lane recommendation:
   deny WebFetch now as the bridge, a pinned fetch tool as the
   destination).**
2. **Redirects**: a redirect from a public host to a private one. The
   gate checks the original URL only. **Same root as 1 — the same
   options close it (deny/proxy/pinned-fetcher); an allowlist alone does
   not (the client follows redirects with no hook).**
3. **The client timing out or killing the hook process** (20 s
   wired). `|| exit 2` covers the hook failing, not the client
   discarding it; the gate answers in tens of ms, so the margin is
   large but not infinite.
4. **A teammate sending what it MAY read** — its own home, the shared
   workspace — **to a public host** by WebFetch. No secrets remain in
   the readable set, but the channel is open at both layers; a
   charter/trust matter.
5. **`mcp__web_reader__webReader` executes SERVER-side and is
   unfenced at every client-side layer** (round-2 finding, beyond the
   panel): the transcript records the bare name `webReader` in
   `mcp_tool_use` — no PreToolUse hook fires for it (contrast:
   `request_secret`'s call was hook-refused live), and no permissions
   deny binds MCP tools (N4). Only its server-side "Network error"
   behavior currently limits it. **Post-panel W-task pinned the source
   (evidence 14): the tool is attached API-side by the upstream behind
   the fabric router** — the teammate env's
   `ANTHROPIC_BASE_URL=http://127.0.0.1:8313` routes to the unified
   router, and that route's glm-5.3 upstream offers `web_reader`
   server-side; no MCP registration exists anywhere in the teammate
   home, spec, generated settings, workspace, managed config or CLI
   argv (`claude mcp list` shows none), and the T3 server itself
   injects only `t3-code`. So no team_roster change can un-offer it;
   the close is a router-route change — escalation steps, census and
   rollbacks in `14-webreader-close.md`. The gate fences the name
   whenever a hook does fire and R6b bare-denies the exact name;
   neither reaches a server-side execution path.
6. **New MCP tools need exact-name census updates** (consequence of
   N4): a newly offered MCP tool carries no wildcard protection in the
   rule layer until its exact name joins `TOOL_DENY_CENSUS`; the
   gate's allowlist-only stance refuses it meanwhile — where a hook
   fires.

Two former rule-layer residuals (chain-directory name enumeration,
post-apply folders) are closed by the gate and, after the cut, moot
for the rules — the snapshot no longer enumerates chains, so it cannot
go stale against them. They reopen only in the fail-open states of
§3a, and `status` (R6c) now detects the drift states that produce
those (mode, python3, disableAllHooks, canary).

Still-true rule semantics worth remembering when editing the short
list: deny beats allow at any specificity (no cascade, 09b); a deny on
a directory matches its whole subtree (10 D2); the matcher resolves
symlinks and canonicalizes firmlinks (09, 11 S2) — and the gate
resolves both again at call time.

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
| panel 2 blind score of `7e9a29aa4` (3 HIGH, 6 MED, two live-proof items, "install: ready after listed repairs") | `panel2/SCORE.md` + reviewer files beside it |
| repair round 2: the 7 live probes (url-field, octal/backslash-`@`, home Grep with hints, `@` write + what the client does with an `@` import, hook env `HOME`/`CLAUDE_CONFIG_DIR`, gate mode 0644/0000 + `status` exit 1, brace-verbatim + 20-call timing), N4 MCP-wildcard non-binding, the webReader server-side finding, the BCU M14 answer, red logs + suite logs | `13-repair2-live-probes.md` + `probe2/` |
| W-task: webReader source pinned to the router's upstream (full offer census, 96 tools, webReader present, all other MCP = t3-code hook-visible and gate-refused live; restore byte-identical; escalated close steps with checks/rollbacks; the two one-liners) | `14-webreader-close.md` + `probe2/w-census-reply.json` |
| repair round 3 H-1: DNS rebinding/redirect not closeable in-spec; five options with costs and real-root flags escalated for decision (deny WebFetch bridge, pinned fetch tool, egress proxy, hostname allowlist, accept) | `15-h1-options.md` |
| repair round 3: all 9 live probes on the round-3 install (the seven re-runs under the pinned `/usr/bin/python3` command, H-2 config-class unreadable at both layers, M-R1 Data-spelled spec canonicalized) incl. as-was baseline showing the PATH-resolved interpreter defect, 1,355-rule count, 20-call latency | `16-repair3-live-probes.md` + `probe2/` |
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
  …) and every OTHER teammate's home become read-refused — by the GATE
  at call time (the round-2 cut removed the rule enumeration; today's
  shipped limits deny neither). If a future workflow needs another
  root, it is one more list entry (per-teammate rooting is not
  implemented; a teammate that genuinely needs a different root than
  its peers needs that follow-up).
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
after the file mtimes. Expected size after the round-2 cut: ~1,100
deny rules per teammate (~69 KB) — and, because the rules no longer
enumerate sibling directories, the file no longer changes when the
surrounding directories change; re-running `apply` matters only for
spec edits (roots, census, `deny_read_paths`). The GATE layer needs no
regeneration for new folders (§3a, step 6).

Two install notes from repair round 1:

1. The gate program (`teammate_gate.py`) must ship beside
   `team_roster.py` in the installed tools tree — `apply` refuses to run
   without it (a missing hook is fail-open, so absence is fatal, not
   cosmetic).
2. The real server's currently-shipped limits do NOT deny
   Workflow/SendMessage/ListAgents/ScheduleWakeup/Skill/
   `mcp__t3-code__request_secret` (live census, evidence 12 round C3).
   The generated limits now bare-deny the full census
   (`TOOL_DENY_CENSUS`, R6b — every non-allowlisted tool from the live
   census plus a belt of build-dependent names; MCP tools by exact
   name only, N4) and the gate refuses unknown tools at call time;
   installing the new limits closes that gap on the real roster.

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
- Repair rounds 1–2: the gate was live-proved on the DEV seat only;
  the real roster's fence must be verified with `status` — which now
  checks limits-bytes, gate sha, hook wiring, instance launchArgs,
  gate mode 0555, `python3` on PATH, no `disableAllHooks` in any
  applying settings file, and a canary call exiting 2 (R6c) — plus one
  spelling-family probe from a real seat before any credential-bearing
  roster relies on it (the panel's own condition). WebFetch
  exfiltration to PUBLIC hosts remains possible at both layers; that is
  accepted residual, §4. The tool census is build-dependent (TodoWrite,
  WebSearch, LS, Bash were not offered in the probed build but stay in
  the belt denies) — re-run the census probe after any server/client
  upgrade. `webReader` executes server-side and stays unfenced until
  the server lane removes it (§4 item 5).
