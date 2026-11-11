# BCU teammate switch — how teammates get session tools, and a per-teammate browser/computer-use switch (default off)

Lane BCU research return, 2026-11-11. Read-only investigation; this document is
the only artifact. Blind-review copy: no lane-author judgment is presented as
fact; every unverified line is marked **UNVERIFIED**. Checkout:
`/Users/chriswong/.t3/worktrees/Mastermind/t3-5c290d50` (branch `t3/mmos-v4-bcu`).

Scope answers, with citations. Companion lane design: `BCU_BROWSER_COMPUTER_USE.md`
(component 4 names this switch; :43–45).

---

## 1. How a teammate session starts, and where its MCP servers come from today

**The server.** launchd runs `<root>/bin/server_runner.sh <root>` (plist written by
`team_server.sh install`, `tools/mmos_team_server/team_server.sh:289–309`). The runner
resolves the packed runtime via receipts (`server_runner.sh:48–69`;
`node_install.py:415–458` — pinned Node + `dist/bin.mjs`, or legacy
`<root>/config/server-bin`), takes an exclusive `flock` on `<root>/run/home.lock`,
sets `T3CODE_HOME=<root>/home`, `T3CODE_PORT`, `T3CODE_HOST=127.0.0.1`,
`T3CODE_NO_BROWSER=1` and execs `node <server_bin> serve`
(`server_runner.sh:74–117`, env at :108–111). Server root per the real spec:
`~/.mastermind/t3-team`; server program per spec `t3_bin`:
`~/.mastermind/t3-team-server/bin/t3` (`specs/team_roster.json:2–8`).

**The Claude session.** No MMOS tool starts a teammate's Claude process. The T3
server's `claudeAgent` driver spawns it when a turn is dispatched to the thread.
Everything MMOS controls lives in the provider-instance row that
`tools/mmos_team_server/team_roster.py apply` merges into
`<T3 home>/userdata/settings.json` → `providerInstances[<instance>]`
(`team_roster.py:421–451`, `ensure_instances`; live-proven, `T7_TEAM_ROSTER.md:19–24`).
The row built by `instance_for` (`team_roster.py:402–418`) is:

- `driver: "claudeAgent"`;
- `config.homePath` = `<server-root>/teammates/<slug>` (`team_roster.py:255–257`,
  `402–418`);
- `config.launchArgs` = one shell-style string:
  `--append-system-prompt-file <home>/CHARTER.md --settings <home>/tool-limits.json`
  (`team_roster.py:404–407`; the string form is noted in
  `tools/mmos_teammate/setup_teammate.py:159–163`).

The teammate's home **is** its Claude configuration folder — stated in the code
comment at `team_roster.py:282–293` ("A teammate's home is also its Claude
configuration folder"), and enforced by `HOME_CONFIG` write-denies on
`settings.json`, `.claude.json`, `.mcp.json`, `skills`, `hooks`, …
(`team_roster.py:288–293`, applied in `tool_limits` at :345–348; live-proven after
restart, `PROGRAM_PLAN_V4.md` §26 :1018–1022, MAS-17). The driver file itself is
not in this repo: **UNVERIFIED** whether the driver sets the env var literally as
`CLAUDE_CONFIG_DIR=<homePath>`. Supporting evidence for the equivalence: (a)
provider homes `~/.t3/providers/<name>/` carry a `.claude.json` whose `mcpServers`
reach those sessions — verified by this lane, `BCU_BROWSER_COMPUTER_USE.md:12`
("Registered in 4 of 5 provider homes… Not registered in
`fabric-unified-router-worker` — delegated children get nothing"); (b) this
worker's own session memory lives at
`~/.t3/providers/fabric-unified-router-worker/projects/...` — the config-dir
layout; (c) `--settings`-file and scratch-`CLAUDE_CONFIG_DIR` behavior of the same
CLI line is live-proven in `LANE_EXECUTIVE_DIRECTOR_C6.md:155–161`. Driver env
merge seam: provider-instance `environment` is merged into the Claude process env
at `apps/server/src/provider/Drivers/ClaudeHome.ts:82` (cited from
`LANE_EXECUTIVE_DIRECTOR_C7.md:189–193` and
`REVIEW4_GUARD_R8_C7_PIN_OPUS_20261110.md:19`; source file not read here —
**UNVERIFIED** directly).

**MCP servers today.** Three possible sources; for a teammate today:

1. *T3-injected orchestrator MCP* (`mcp__t3-code__*`): present in T3-hosted Claude
   sessions even when the home has no MCP registration — the
   `fabric-unified-router-worker` home's `.claude.json` has **no `mcpServers` key**
   (listing this session), yet its sessions carry `mcp__t3-code__*` tools
   (`LANE_FLEET_DIRECTOR_G.md:100–103` names that tool prefix as the observed
   marker of T3-hosted harness sessions). The exact injection seam (SDK
   `mcpServers` option → CLI) is **UNVERIFIED** here. The T3 build uses Claude CLI
   2.1.322 with `@anthropic-ai/claude-agent-sdk@0.3.316`
   (`XP_CROSS_PROJECT_CHILD.md:169–170`).
2. *User-scope `.claude.json` `mcpServers` in the home*: the incumbent
   registration surface (four of five provider homes register `paper`,
   `desktop-commander`, `studio-direct`, `linear-server`, `mastermind-executive`,
   `mmx-browser` there — names/commands listed this session; entries also in
   `tools/mmos_browser_use/generate_staging.py:49–58`). **A teammate has none
   today**: `apply` writes only `CLAUDE.md` (first creation), `CHARTER.md` and
   `tool-limits.json` (`team_roster.py:363–388`), and the teammate is denied
   writing `.claude.json`/`.mcp.json` (above).
3. *A `--mcp-config` flag in `launchArgs`*: not used for teammates today. The flag
   exists and is used elsewhere in this repo: the executive wake harness runs
   `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`
   (`integrations/executive_wake/claude_code.py:637–639`), and
   `LANE_EXECUTIVE_DIRECTOR_C6.md:160–161` exercised `--strict-mcp-config` on CLI
   2.1.319.

The wake path never touches session tools: Paperclip's process adapter spawns
`wake_carrier.py`, which drives the `t3` CLI (`t3 thread send/show` with
`T3CODE_HOME` env) and never the Claude binary (`wake_carrier.py:16`, :649–671;
`T2_TEAMMATE_BINDING_AND_DISPATCH.md:26–43`).

**Net:** a teammate today gets the T3-injected tool set plus file tools bounded by
`tool-limits.json` (allow: Read/Glob/Grep/WebFetch/WebSearch/TodoWrite +
Write/Edit inside own home; deny: Bash, Agent, NotebookEdit, config names, other
homes, server-private paths — `team_roster.py:335–360`), and **no browser or
computer-use MCP, with no way to give itself one**.

## 2. Where the roster spec is parsed; where the switch lives

Parsed once, in `load_spec` (`team_roster.py:84–155`): requires `server`, `project`,
`model`, `teammates` (:89–91), per-server keys `root/home/t3_bin/port` (:93–95),
per-project `title/workspace_root` (:96–98), and per-teammate `name, slug, role,
role_line, accent_color, instance, charter` (:113–118), with duplicate and title
validation (:119–154). Spec files: `tools/mmos_team_server/specs/team_roster.json`
(real roster, 3 teammates, :43–77) and `specs/team_roster_dev_tsr.json` (dev).
Top-level optional fields read elsewhere via `spec.get(...)`: `state_file`,
`urls_file`, `browser_profile` (+`browser_profile_root`, `browser_node`,
`rename_evidence_file` in `rename_threads` :605–636), `deny_write_roots`,
`deny_read_roots`, `deny_read_root_siblings`, `allow_long_titles` (:129,
:320–326, :337–338). **No `tools` field exists anywhere today.** The only consumers
of this spec shape are `team_roster.py` itself and its tests
(`tests/test_mmos_team_roster*.py`); the cutover/installed specs under
`tools/mmos_teammate/specs/` are a different shape (no charter/tools; e.g.
`assurance.installed.json`).

**Where the switch should live:** a per-teammate object in the roster spec —

```json
"tools": { "browser_use": false, "computer_use": false }
```

— validated in `load_spec` (die on non-bool values or unknown keys, matching the
file's strict style), and consumed **only inside `team_roster.py`** (team-server
code): a helper feeding (a) a new apply-owned file written into the teammate home
and (b) the `launchArgs` built by `instance_for`. Reasons this is the only-reader
property:

- `team_roster.py apply` runs from the repo by the operator/principal; a teammate
  has `Bash` denied (`team_roster.py:339`) and cannot run it.
- The produced file is added to `HOME_LOCKED` (`team_roster.py:278–279`), so the
  teammate's Write/Edit tools cannot alter or delete it (deny applied at :342–344;
  live-proven pattern MAS-17, `PROGRAM_PLAN_V4.md` §26 :1018–1022).
- The `.claude.json`/`.mcp.json` alternative surfaces stay write-denied
  (`HOME_CONFIG`, `team_roster.py:288–293`), so the teammate cannot register an
  MCP entry itself — the exact hole closed in §25 after MAS-15/16
  (`PROGRAM_PLAN_V4.md:960–974`).

## 3. The exact minimal staged change

**Recommendation: a dedicated apply-owned `<home>/mcp-servers.json` passed via
`--mcp-config` in `launchArgs`** — not a merge into `<home>/.claude.json`. The
dedicated file is fully apply-owned and idempotent via the existing
`write_if_changed` (`team_roster.py:260–268`); `.claude.json` is runtime-owned
state (the provider-home staging needed preimage hashes, backups and
merge-only-our-keys machinery for that reason,
`tools/mmos_browser_use/generate_staging.py:64–86`), and `--mcp-config` is already
an incumbent-proven flag in this repo (`claude_code.py:637–639`). Do **not** add
`--strict-mcp-config` without the R2 check below.

**Files changed: one — `tools/mmos_team_server/team_roster.py`** (plus spec edit to
flip a switch, plus tests). Sketch (≤40 lines):

```python
# --- constants (near HOME_CONFIG, ~line 295) ---
MMX_BROWSER_MCP = {"type": "stdio",
    "command": "/Users/chriswong/.local/share/mastermind-runtime/node/bin/node",
    "args": ["/Users/chriswong/.t3/mcp/mmx-browser/server.js"]}
MMOS_COMPUTER_USE_MCP = {"type": "stdio", "command": "python3",
    "args": ["/Users/chriswong/.t3/mcp/mmos-computer-use/server.py"]}
TOOL_KEYS = {"browser_use", "computer_use"}

def mcp_servers_for(mate):
    tools = mate.get("tools") or {}          # load_spec already died on bad shape
    out = {}
    if tools.get("browser_use") is True:     out["mmx-browser"] = MMX_BROWSER_MCP
    if tools.get("computer_use") is True:    out["mmos-computer-use"] = MMOS_COMPUTER_USE_MCP
    return out

# --- in load_spec's per-teammate loop (~line 118) ---
    tools = mate.get("tools") or {}
    if not isinstance(tools, dict) or set(tools) - TOOL_KEYS or \
            any(v is not True and v is not False for v in tools.values()):
        die(f"{where}.tools must be an object of booleans with keys "
            f"{sorted(TOOL_KEYS)}")

# --- HOME_LOCKED gains: "mcp-servers.json" (line 278) ---

# --- in write_file_assets (~line 385), after tool-limits.json ---
    mcp_path = os.path.join(home, "mcp-servers.json")
    if write_if_changed(mcp_path, json.dumps(
            {"mcpServers": mcp_servers_for(mate)}, indent=2) + "\n", 0o600):
        wrote.append("mcp-servers.json")

# --- in instance_for (~line 406), after the two existing launch args ---
    if mcp_servers_for(mate):
        launch_args += ["--mcp-config", os.path.join(home, "mcp-servers.json")]
```

(Entries are the same stdio commands the BCU browser staging generator stages for
provider homes — `generate_staging.py:49–58`. Per the brief, the referenced
programs are cited, not verified present at those paths by this pass; `mmx-browser`
existence at `~/.t3/mcp/mmx-browser/` is stated verified in
`BCU_BROWSER_COMPUTER_USE.md:12`; the installed location of
`mmos-computer-use/server.py` under `~/.t3/mcp/` is **UNVERIFIED** — the repo copy
is `tools/mmos_computer_use/server.py`.)

**How the mcp config differs for a switched-on teammate** (e.g. Assurance with
`tools: {browser_use: true, computer_use: true}`):

- `settings.json → providerInstances["assurance"].config.launchArgs` becomes:
  `--append-system-prompt-file <home>/CHARTER.md --settings <home>/tool-limits.json
  --mcp-config <home>/mcp-servers.json` (single string, space-separated;
  `team_roster.py:404–416`).
- `<home>/mcp-servers.json` (0600, apply-written) holds the one or two stdio
  entries above; session tool names become `mcp__mmx-browser__*` /
  `mcp__mmos-computer-use__*`.
- Switch-off converges: file rewrites to `{"mcpServers": {}}`, launchArg drops,
  `ensure_instances` sees `have != want` and rewrites (`team_roster.py:439–446`).
- `settings.json` is watched and reloaded live by the running server
  (`team_roster.py:33–36` docstring; `T7_TEAM_ROSTER.md:42–45`), but a running
  teammate **process** reads settings/MCP at start: a live idle process binds the
  change only after it exits and restarts — the same binding behavior proven for
  limits in `PROGRAM_PLAN_V4.md` §25 (:966–974) and §26 MAS-17 (:1018–1022).

**Tests** (extend `tests/test_mmos_team_roster.py`, alongside
`test_own_claude_configuration_not_writable` :207): `tools` validation (non-bool,
unknown key refused); `instance_for` adds/omits the flag; `write_file_assets`
writes `mcp-servers.json` 0600 with exactly the enabled entries; `tool_limits`
denies Write/Edit on it; second `apply` is a no-change run (idempotence, matching
`test_merge_is_idempotent` :144).

## 4. What is installed where today; what an installer adds

Team-server install root `~/.mastermind/t3-team-server` (listing this session,
names only): `bin/` (`t3`, `t3-0770446-textdelta`) and `pin-0770446-textdelta/`.
Per the specs and installer code, the server root `~/.mastermind/t3-team` holds
`home/` (T3 state incl. `userdata/settings.json`), `run/` (port, server.log,
access.txt, team_urls.json), `bin/` (server_runner.sh, node_install.py),
`config/`, `scratch-project/`, `team-project/`, `claude-home/`, `fabric.env`,
`teammates/<slug>/` and `carrier/` (`team_server.sh:268–287`;
`team_roster.json:2–16`; `assurance.installed.json:6–7`). **UNVERIFIED by listing**
(the brief allowed listing only `t3-team-server`). Contents the roster tool itself
creates per teammate home: `CLAUDE.md`, `CHARTER.md`, `tool-limits.json`
(`team_roster.py:363–388`) plus carrier/cutover files
(`HOME_LOCKED`, `team_roster.py:278–279`).

An installer for this switch adds **nothing outside the repo change**: the
`mcp-servers.json` files are produced by `team_roster.py apply` itself. Install
sequence: (1) land the `team_roster.py` change + tests; (2) edit the spec's
`tools` block for the chosen teammate; (3) run `apply` (works against the running
server; `T7_TEAM_ROSTER.md:49–56`); (4) let/restart the teammate's idle process
and probe its tool list. The MCP programs the entries point at are installed by
the other BCU components, not by this change (`mmx-browser` already at
`~/.t3/mcp/mmx-browser/` per `BCU_BROWSER_COMPUTER_USE.md:12`; `mmos-computer-use`
staged by the browser/computer-use lanes — installed-copy location **UNVERIFIED**).

## 5. Risks / unknowns, each with its exact next check

| # | Risk / unknown | Next check that resolves it |
|---|---|---|
| R1 | The `claudeAgent` driver's exact hand-off (`CLAUDE_CONFIG_DIR`? which claude binary? how `launchArgs` strings are split?) is **UNVERIFIED** — `ClaudeHome.ts`/driver source is not in this repo. | Read the pinned T3 source `apps/server/src/provider/Drivers/ClaudeHome.ts` and the driver's SDK `Options` construction (the tree the T6/T1s/XP lanes used), or empirically: dev server + test teammate whose `launchArgs` gains `--mcp-config` with a one-tool echo server; confirm the tool appears. |
| R2 | Interaction with `--strict-mcp-config` (proposed NOT to use): might suppress T3-injected `t3-code` MCP or `.claude.json`-scope servers in ways we have not measured. | One dev-server turn with a switched-on test teammate (non-strict) asserting BOTH `mcp__t3-code__*` and the new server are live; repeat with `--strict-mcp-config` before ever adopting it. |
| R3 | A live idle teammate process may not re-read `launchArgs`/MCP until it exits (limits precedent: §25 MAS-16, §26 MAS-17). | Process-start-time + tool-list probe after `apply`, mirroring MAS-17's file-system/process check (`PROGRAM_PLAN_V4.md:1018–1022`). |
| R4 | `launchArgs` is one shell-style string (`setup_teammate.py:159–163`): path spaces or quoting would break it. Splitting rule **UNVERIFIED** (R1). | Keep paths space-free (they are); assert the exact launchArgs string in the unit test; R1's source read confirms the tokenizer. |
| R5 | MCP entry commands are user-absolute paths (`generate_staging.py:49–58` pattern); a moved runtime silently breaks the server at session start. | Confirmation probe in the install sequence (tool list actually served), plus the staged-install rollback entries the BCU browser lane already writes. |
| R6 | Whether Claude Code lazily creates/writes `<home>/.claude.json` for teammates (runtime state we do not own) is **UNVERIFIED**; irrelevant to the `--mcp-config` route but relevant if anyone later proposes the merge route. | `ls` a dev teammate home before/after one turn (dev server only). |
| R7 | Deny-list drift: if a future edit removes `mcp-servers.json` from `HOME_LOCKED`, a teammate could edit its own tool registration. | Add the negative test (Write/Edit on `mcp-servers.json` denied) so the regression is caught by `tests/test_mmos_team_roster.py`. |
| R8 | Charter/limits currently promise "no shell, no helper agents" (e.g. Secretary charter, `team_roster.json:75`); browser/computer-use tools change that surface for a switched teammate. Human/lease gates live in the BCU computer-use server (`BCU_BROWSER_COMPUTER_USE.md:66–77`), not here. | The enabling decision stays with the principal per the lane's "Reserved to the principal" list (`BCU_BROWSER_COMPUTER_USE.md:95–99`); charter text update rides the same spec edit. |

---

### Evidence index (reads performed for this return)

Repo: `PROGRAM_PLAN_V4.md` §1–5, §25–27; `BCU_BROWSER_COMPUTER_USE.md`;
`T6_TEAM_SERVER.md`; `T7_TEAM_ROSTER.md`; `T2_TEAMMATE_BINDING_AND_DISPATCH.md`;
`LANE_EXECUTIVE_DIRECTOR_C6.md` (:150–178), `C7.md` (:187–197);
`REVIEW4_GUARD_R8_C7_PIN_OPUS_20261110.md`; `LANE_FLEET_DIRECTOR_G.md` (:88–117);
`XP_CROSS_PROJECT_CHILD.md` (:155–199). Tools:
`team_server.sh`; `server_runner.sh`; `node_install.py`; `pack_server.mjs` (:1–80);
`roster_browser.js` (:1–60); `team_roster.py`; `specs/team_roster.json`;
`specs/team_roster_dev_tsr.json`; `setup_teammate.py`; `wake_carrier.py` (outline +
cited lines); `specs/{assurance,design-lead,secretary}.installed.json`,
`specs/{atlas,mira}_test.dev.json`; `integrations/executive_wake/claude_code.py`
(:620–649); `tools/mmos_browser_use/generate_staging.py` (:1–120);
`tools/mmos_dev/t3/seed_dev_home.py`. Tests: `tests/test_mmos_team_roster.py`
(outline). External (permitted): `~/.t3/providers/*/.claude.json` `mcpServers`
names/commands only; `ls ~/.mastermind/t3-team-server` (names only).
