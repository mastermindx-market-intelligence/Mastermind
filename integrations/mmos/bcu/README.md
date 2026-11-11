# BCU staged install — browser + computer use registration (lane BCU)

Status: **staged, nothing installed by this lane.** This directory holds the
offline install package: registration entries, preimage hashes, generic
install/rollback/verify scripts, the guidance skill, and a loopback fixture.
An operator session installs it by running the commands below; nothing is
executed at generation time.

## What gets installed

Two MCP registrations in provider-home `.claude.json` `mcpServers` objects:

- `mmx-browser` — existing pinned browser bridge (already registered in 4 of
  5 homes; staged for `fabric-unified-router-worker` only, which currently
  has **no** `mcpServers` at all — delegated worker children get zero MCP tools).
- `mmos-computer-use` — new stdlib computer-use MCP server (sibling lane),
  staged for **all five** homes. Launches `["python3", "/Users/chriswong/.t3/mcp/mmos-computer-use/server.py"]`;
  the operator copies `tools/mmos_computer_use/server.py` to that path at
  install time (that copy is that lane's step, not this package's).

## Generated tree

Produced by `tools/mmos_browser_use/generate_staging.py` (default mode, five
standard homes):

```
generated/
  MANIFEST.json            generation timestamp, target paths, sha256s, entry keys
  install.py / rollback.py / verify.py   generic scripts, stdlib only
  <home>/entries.json      exact JSON fragment merged into mcpServers
  <home>/preimage.sha256   sha256 of the home .claude.json at generation time
```

Scripts are generic: they take `--home <path ending in .claude.json>`
(required — they refuse otherwise) and read the staging for that home's
directory name. They never print or modify anything outside our two
registration keys. If install aborts `PREIMAGE_MISMATCH`, the file changed
since staging (live T3 sessions rewrite these files): re-run the generator,
review the diff, recommit, then install.

## Install manifest

| # | Target file | Preimage sha256 (generated 2026-11-11) | Install | Rollback |
|---|---|---|---|---|
| 1 | `/Users/chriswong/.t3/providers/experiential-claude/.claude.json` | `67f8773efdcd8cae106592f8f655b889ba8b6d104943370fa28418f2e6ce3ee4` | `python3 integrations/mmos/bcu/generated/install.py --home <file>` | `python3 integrations/mmos/bcu/generated/rollback.py --home <file>` |
| 2 | `/Users/chriswong/.t3/providers/fabric-anthropic-oauth/.claude.json` | `b4618ce1cb8b8832da50b450c3d257a83b2f66b01385d45de6453d4c95521a4b` | same as above | same as above |
| 3 | `/Users/chriswong/.t3/providers/fabric-experiential/.claude.json` | `bf4849a4e99ddbcd7c881ec97a997fda1ad72f3a7a7ad26409275436793f901e` | same as above | same as above |
| 4 | `/Users/chriswong/.t3/providers/fabric-unified-router/.claude.json` | `14dfe4ebc4c2196523d8cacb5b3e3450c2c26ed816825ed6fb3481bce647dec9` (drifts — see note) | same as above | same as above |
| 5 | `/Users/chriswong/.t3/providers/fabric-unified-router-worker/.claude.json` | `6b209296964005114716078e315f24ea02768ec65affc9fce9024eb8835bbf05` | same as above | same as above |
| 6 | `/Users/chriswong/.t3/skills/mmos-browser-computer-use/SKILL.md` (new file — no preimage; install = mkdir + copy) | — | `mkdir -p ~/.t3/skills/mmos-browser-computer-use && cp integrations/mmos/bcu/skill/SKILL.md ~/.t3/skills/mmos-browser-computer-use/SKILL.md` | `rm ~/.t3/skills/mmos-browser-computer-use/SKILL.md && rmdir ~/.t3/skills/mmos-browser-computer-use` |
| 7 | MMOS team-server homes (`<teammate-home>/mcp-servers.json`, per teammate) | new file — none exist; created by `apply` only for switched-on teammates | set `"tools": {"browser_use": true}` / `"computer_use": true}` in the roster spec and run `tools/mmos_team_server/team_roster.py apply` (source change already in this branch: spec validation, `mcp-servers.json` 0600 runtime-written + `HOME_LOCKED`, `--mcp-config` launch arg; default off = file absent, flag absent) | remove the `tools` flags from the spec and re-run `apply` (stale file is removed automatically; `--mcp-config` arg drops) |

Row 7 touches the **installed team server's runtime** (it runs a packed copy,
not this checkout). Deploying it there is the principal's staged action, not
this package's; see `integrations/mmos/BCU_TEAMMATE_SWITCH_PROPOSAL.md`.

Entries per home: homes 1–4 stage `mmos-computer-use` only; home 5 stages
`mmos-computer-use` + `mmx-browser`. Substitute `<file>` with the target row's
full path. Every install writes a timestamped backup
`.claude.json.bak-pre-bcu-<ts>` next to the file before editing.

**Preimage drift.** Live T3 sessions rewrite these files continuously —
`fabric-unified-router` changed three times while this package was being
built. The hashes above are the values observed at the last regeneration
(`MANIFEST.json` is authoritative); row 4 is expected to be stale by the
time anyone installs. **Procedure: re-run
`python3 tools/mmos_browser_use/generate_staging.py` immediately before
installing, commit the refreshed preimages with the install receipt, then
install** — the scripts enforce the guard at run time regardless of what
this README says.

Verify after each install:

```
python3 integrations/mmos/bcu/generated/verify.py --home <file>
```

prints one `VERIFY <key> PRESENT|ABSENT|PRESENT_MISMATCH` line per staged
entry plus `SHA256 <hash>` of the edited file; exit 0 only when all staged
entries are present and equal.

## Confirmation probes

T3 sessions read the provider-home `.claude.json` **at session start**, so
already-running sessions do not pick up a registration. The probes:

1. **Primary (new session):** open a **new** T3 session on the installed
   home and call the tool (`mcp__mmx-browser__mmx_browser` with
   `{"action":"browsers"}`, or `mmos_computer_use` with a read-only call such
   as `cu_apps`). A successful structured response confirms registration.
2. **Headless (no model call, fast):**
   `CLAUDE_CONFIG_DIR=/Users/chriswong/.t3/providers/<home> claude mcp list`
   must list `mmx-browser` / `mmos-computer-use` for that home.
3. **Headless end-to-end:**
   `CLAUDE_CONFIG_DIR=/Users/chriswong/.t3/providers/<home> claude -p "Name every MCP server registration you have available, by name only."`
   must name the installed servers. If `CLAUDE_CONFIG_DIR` does not resolve
   the provider-home layout on a given host, fall back to probe 1 and note it.

## Install-time prerequisite

The `mmos-computer-use` entry points at
`/Users/chriswong/.t3/mcp/mmos-computer-use/server.py`. Before installing
into any home, the operator copies it there together with its runtime
config and the pinned Peekaboo binary (exact commands in
`tools/mmos_computer_use/README.md`; the vendored binary copy carries the
macOS Screen Recording / Accessibility grants observed working on M2).
Registering before the file exists is safe — Claude Code reports the
server as failing to start — but the probe will not pass until the file is
in place.

## Safety properties (mirrors `integrations/mmos/BCU_BROWSER_COMPUTER_USE.md`)

- Preimage guard: install aborts `PREIMAGE_MISMATCH` unless the file's
  sha256 matches the staged preimage (or the recorded postimage of a prior
  install of this same package).
- Merge-only: only the staged keys are written; every other key in the file
  is untouched (round-tripped through `json` with `indent=2`).
- Backup before every edit: `.claude.json.bak-pre-bcu-<ts>`; rollback
  restores the newest backup, or with no backup removes only our keys.
- Never run install/rollback against a real home inside tests; tests use
  tmpdir fixtures only (`tests/test_mmos_bcu_browser_use_staging.py`).
