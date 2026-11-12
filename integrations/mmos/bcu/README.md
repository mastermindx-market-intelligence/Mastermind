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
  staged for **all five** homes. Launches
  `["/usr/bin/python3", "<mcp-root>/mmos-computer-use/server.py"]` — an
  absolute launcher, so the registration does not depend on `PATH` (the
  roster entry already uses `/usr/bin/python3`). The server supports 3.9+.

## One-command install (copies the server first)

The installer now owns the server copy, so a registration never points at a
path that does not exist:

```
python3 integrations/mmos/bcu/generated/install.py \
    --home /Users/chriswong/.t3/providers/<name>/.claude.json \
    --copy-server tools/mmos_computer_use
```

`--copy-server SRC_DIR` copies `server.py`, `deny.json` and `runtime.json`
(when present) from `SRC_DIR` into `<mcp-root>/mmos-computer-use/` (default
mcp-root `/Users/chriswong/.t3/mcp`) with **mode 0600**, *before* writing the
registration that points at that copy. `runtime.json` is optional in the
checkout (`runtime.json.dev` is the template); if it is absent the copy
prints `RUNTIME_JSON_ABSENT` and continues.

Without `--copy-server` the entry is registered as-is and a missing target
only draws a `SERVER_TARGET_MISSING` warning on stderr. `--mcp-root DIR`
overrides the server root (tests use it so nothing touches `~/.t3`).

## What gets written, where, and with which mode

| Artifact | Location | Mode |
|---|---|---|
| Home `.claude.json` | the `--home` file | 0600, preserved from the original |
| Backup | `<home dir>/.claude.json.bak-pre-bcu-<stamp>` | **0600** (never world-readable) |
| `postimage.sha256` | `<staging>/<home-dir-name>/postimage.sha256` | **0600** |
| `added-keys.json` | `<staging>/<home-dir-name>/added-keys.json` | **0600** |
| Copied server files | `<mcp-root>/mmos-computer-use/{server,deny,runtime}.json/py` | **0600** |

`added-keys.json` is the install's receipt: it records `added` (keys that did
not exist before), `modified` (keys whose value this install changed, with
their `previous_values`), and whether this install created the server
directory. Rollback is driven by it.

## Rollback semantics

```
python3 integrations/mmos/bcu/generated/rollback.py \
    --home <file> [--remove-server]
```

- **With a backup**: restores the newest backup's exact bytes (this discards
  any changes made since the install — including Claude's own runtime writes).
- **Without a backup**: rollback **REFUSES** (`NO_BACKUP`, exit 7) unless
  `added-keys.json` exists. With the manifest it removes **only the keys this
  install added**, restores the prior values of keys it only modified, and
  never deletes a key that pre-existed (e.g. an `mmx-browser` entry that was
  already registered).
- **`--remove-server`**: deletes `<mcp-root>/mmos-computer-use/` **only** when
  the manifest says this install created it; otherwise prints `SERVER_DIR_KEPT`.

## Atomic writes

Every write goes to a temp file in the destination directory, is `chmod`-ed,
then `os.replace`d into place. The destination's sha256 is re-checked
immediately before the replace; if the file changed since it was first read
the operation aborts (`PREIMAGE_MISMATCH` for install, `CHANGED_SINCE_READ`
for rollback) and the just-written backup is removed so no stale snapshot can
be restored later.

## Refreshing the preimage (`--refresh-preimage`)

Live T3 sessions rewrite `.claude.json` on every start, so a staged preimage
goes stale quickly. The default remains **strict**: a mismatch aborts.
`--refresh-preimage` is the explicit, operator-only override. It does **not**
install; it prints which staged keys are already present / matching / changed
/ absent and re-records the CURRENT file hash as the preimage (clearing the
stale postimage and receipt):

```
python3 integrations/mmos/bcu/generated/install.py --home <file> --refresh-preimage
```

Then run the install normally.

## Generated tree

Produced by `tools/mmos_browser_use/generate_staging.py` (default mode, five
standard homes):

```
generated/
  MANIFEST.json            generation timestamp, target paths, sha256s, entry keys
  install.py / rollback.py / verify.py   generic scripts, stdlib only
  <home>/entries.json      exact JSON fragment merged into mcpServers
  <home>/preimage.sha256   sha256 of the home .claude.json at generation time
  <home>/postimage.sha256  written by install: sha256 of the edited file (0600)
  <home>/added-keys.json   written by install: added/modified keys + server-dir receipt (0600)
```

Scripts are generic: they take `--home <path ending in .claude.json>`
(required — they refuse otherwise) and read the staging for that home's
directory name. They never print or modify anything outside our two
registration keys. If install aborts `PREIMAGE_MISMATCH`, the file changed
since staging (live T3 sessions rewrite these files): re-run the generator
with `--force`, review the diff, recommit, then install.

## Install manifest

| # | Target file | Preimage sha256 (generated 2026-11-11) | Install | Rollback |
|---|---|---|---|---|
| 1 | `/Users/chriswong/.t3/providers/experiential-claude/.claude.json` | `67f8773efdcd8cae106592f8f655b889ba8b6d104943370fa28418f2e6ce3ee4` | `python3 integrations/mmos/bcu/generated/install.py --home <file> --copy-server tools/mmos_computer_use` | `python3 integrations/mmos/bcu/generated/rollback.py --home <file> [--remove-server]` |
| 2 | `/Users/chriswong/.t3/providers/fabric-anthropic-oauth/.claude.json` | `b4618ce1cb8b8832da50b450c3d257a83b2f66b01385d45de6453d4c95521a4b` | same as above | same as above |
| 3 | `/Users/chriswong/.t3/providers/fabric-experiential/.claude.json` | `bf4849a4e99ddbcd7c881ec97a997fda1ad72f3a7a7ad26409275436793f901e` | same as above | same as above |
| 4 | `/Users/chriswong/.t3/providers/fabric-unified-router/.claude.json` | `1c5429799fe0ee913f3beb1369d55aeba5d5df50fd0b17a8db161955134ef41f` (drifts — see note) | same as above | same as above |
| 5 | `/Users/chriswong/.t3/providers/fabric-unified-router-worker/.claude.json` | `6b209296964005114716078e315f24ea02768ec65affc9fce9024eb8835bbf05` | same as above | same as above |
| 6 | `/Users/chriswong/.t3/skills/mmos-browser-computer-use/SKILL.md` (new file — no preimage; install = mkdir + copy) | — | `mkdir -p ~/.t3/skills/mmos-browser-computer-use && cp integrations/mmos/bcu/skill/SKILL.md ~/.t3/skills/mmos-browser-computer-use/SKILL.md` | `rm ~/.t3/skills/mmos-browser-computer-use/SKILL.md && rmdir ~/.t3/skills/mmos-browser-computer-use` |
| 7 | MMOS team-server homes (`<teammate-home>/mcp-servers.json`, per teammate) | new file — none exist; created by `apply` only for switched-on teammates | set `"tools": {"browser_use": true}` / `"computer_use": true}` in the roster spec and run `tools/mmos_team_server/team_roster.py apply` (source change already in this branch: spec validation, `mcp-servers.json` 0600 runtime-written + `HOME_LOCKED`, `--mcp-config` launch arg; default off = file absent, flag absent) | remove the `tools` flags from the spec and re-run `apply` (stale file is removed automatically; `--mcp-config` arg drops) |

Row 7 touches the **installed team server's runtime** (it runs a packed copy,
not this checkout). Deploying it there is the principal's staged action, not
this package's; see `integrations/mmos/BCU_TEAMMATE_SWITCH_PROPOSAL.md`.

Entries per home: homes 1–4 stage `mmos-computer-use` only; home 5 stages
`mmos-computer-use` + `mmx-browser`. Substitute `<file>` with the target row's
full path. Every install writes a timestamped 0600 backup
`.claude.json.bak-pre-bcu-<ts>` next to the file before editing.

**The principal chooses the set.** The staged set is a proposal, not a
default armed by this lane: registering a home gives **every session served
by that home** the tool. The five homes and the sessions they serve:

| Home | Sessions served |
|---|---|
| `fabric-unified-router` | this lane's sessions + `capacity_fabric` children, including the gpt-6.1-terra, gpt-6.1-sol, glm-5.3 and deepseek model routes |
| `fabric-unified-router-worker` | `capacity_fabric_worker` children (delegated workers; currently zero MCP tools) |
| `experiential-claude` | that provider's own sessions |
| `fabric-anthropic-oauth` | that provider's own sessions |
| `fabric-experiential` | that provider's own sessions |

The principal's own home is **not** registered by default; they decide which
of the five (or any other) to install into.

**Preimage drift.** Live T3 sessions rewrite these files continuously —
`fabric-unified-router` changed three times while this package was being
built. The hashes above are the values observed at the last regeneration
(`MANIFEST.json` is authoritative); row 4 is expected to be stale by the
time anyone installs. **Procedure: run the generator with `--force`
immediately before installing, review the diff, commit the refreshed
preimages with the install receipt, then install** — the scripts enforce the
guard at run time regardless of what this README says. The generator
**refuses** a default-`--out` run when `generated/` already exists
(`GENERATED_TREE_EXISTS`, exit 6, naming the files it would overwrite), so a
routine regeneration can never silently overwrite the committed tree; pass
`--force` deliberately, or `--out` to stage elsewhere. If the drift is small
or the run must not wait for a new commit, `install.py --refresh-preimage`
re-records the current hash (see above) — strict preimage remains the default.

Verify after each install:

```
python3 integrations/mmos/bcu/generated/verify.py --home <file> [--mcp-root DIR]
```

prints one `VERIFY <key> PRESENT|ABSENT|PRESENT_MISMATCH` line per staged
entry plus `SHA256 <hash>` of the edited file; exit 0 only when all staged
entries are present and equal. Pass the same `--mcp-root` used at install
when it was not the default.

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

## Peekaboo runtime

The copied `server.py` drives the pinned Peekaboo binary; its macOS Screen
Recording / Accessibility grants are the ones observed working on M2 (see
`tools/mmos_computer_use/README.md` for the vendored binary). The copy step
above covers the Python files only.

## Safety properties (mirrors `integrations/mmos/BCU_BROWSER_COMPUTER_USE.md`)

- Preimage guard: install aborts `PREIMAGE_MISMATCH` unless the file's
  sha256 matches the staged preimage (or the recorded postimage of a prior
  install of this same package). `--refresh-preimage` is the only override
  and is explicit.
- Merge-only: only the staged keys are written; every other key in the file
  is untouched (round-tripped through `json` with `indent=2`).
- Backup before every edit: `.claude.json.bak-pre-bcu-<ts>` at mode 0600;
  rollback restores the newest backup, or — with no backup — refuses unless
  the added-keys manifest exists, in which case it removes only keys this
  install added and restores prior values of keys it modified.
- Atomic writes with a hash re-check immediately before `os.replace`.
- Never run install/rollback against a real home inside tests; tests use
  tmpdir fixtures and a tmpdir `--mcp-root` only
  (`tests/test_mmos_bcu_browser_use_staging.py`).
