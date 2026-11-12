# Bridge release install runbook (release 2) — mmx-browser MCP server

For branch `t3/mmos-v4-br`, head `e778e5658ba7ec9b3ea88223cf0e4d2658e92cbc`,
rollback release `OLD = 5aa30969241163b4abb3e025bc9e52123ee4b478` throughout.
The same text is mirrored at `~/.mastermind/mmos_evidence/br-20261111/release2/`.

The first install attempt (2026-11-12) followed a 15-file copy procedure and
**failed at step 5 with every local profile TRANSPORT_HANDSHAKE_FAILED**; it was
rolled back and `OLD` is live again, byte-identical. This runbook replaces that
procedure. Every step below was rehearsed end to end in scratch
(`~/.mastermind/mmos_dev/br/release2/`, logs under `logs/`); see
"Rehearsal record".

## Why the first attempt failed (proven, not inferred)

`transport_capability_digest()` (`integrations/chairman_surfaces/web_sol_protocol.py`)
hashes the document that includes `"browser_actions": sorted(browser.ACTIONS)`.
This release adds the `read` action, so:

- a client (bridge) at `e778e5658` computes digest
  `1c40ec98d1086a8f8005151757b040698057019f5e9169cace91e393b6f60d40` (41 actions);
- a client at `OLD` computes `e0216d3d9e9f05edef32ff642cb82a1281b1a9766d5cc35f694c88e0ef0bb0bb`
  (40 actions);
- `WEB_SOL_PACKAGE_VERSION` is `0.4.0` on both sides, so the version check
  never fires — only the digest differs.

The native host that Chrome spawns for each profile is a shell script that
`cd`s into a **release root** and runs
`python3.14 -E -s -B -m integrations.chairman_surfaces.web_sol_native_host`.
Those scripts live under `releases/OLD/chrome/<profile>/bin/` and the Chrome
`NativeMessagingHosts` manifests point there. Copying 15 files into a new
`releases/$NEW/` directory changed **only the client side**; the hosts kept
importing protocol code from the `OLD` root, computed the old digest, and
`_accepted_peer_hello` (`_web_sol_native_host_impl.py`) raised
`transport_capability_mismatch` and dropped the connection before the ack —
which the client reports as `transport_handshake_failed`.

Proofs: digests computed from both release roots (`logs/digest_proof.txt`); a
live A/B/C matrix (`logs/rehearsal_switch.log`) where a server pinned to the
new 15-file root reproduced the principal's exact 5× TRANSPORT_HANDSHAKE_FAILED
against today's running extension, and the same root with only
`web_sol_browser_protocol.py` reverted showed 5× CONNECTED. The 175-vs-15 file
count was **not** the cause: `BUILD.json` is read only by `REMOTE_BOOT` (ssh,
`browser_routes.py`) and by the installer as `--prior-source`; the MCP server
never reads it, and a 15-file closure runs the server fine.

## Why "no daemon restart needed" was wrong, and the fix

`server.js` captures `runtime.json`'s bytes at startup and re-verifies them
before **every dispatch**. Editing the live
`~/.t3/mcp/mmx-browser/runtime.json` in place makes every already-running
server answer `REFUSED / NATIVE_SOURCE_CLOSURE_STALE` (retry not allowed) until
its session restarts — during the first attempt that hit 31 running servers.

Therefore: **never edit the live `runtime.json` again.** This runbook switches
releases with versioned runtime folders plus a `current` symlink; `server.js`
is byte-identical everywhere and no pinned file ever changes under a running
server. Rehearsal proved a server started through `current/` keeps its pin
across a symlink repoint (old session keeps working) while the next server
spawned through `current/` gets the new release.

## What a release folder must contain and how it is built

A release root (`~/.local/share/mastermind-browser-control/releases/<commit>/`)
built by `integrations/hermes_harness/install_browser.py` holds ~155 files:

- the **pinned source closure** from the build manifest (64 files at this head:
  `integrations/chairman_surfaces/` incl. the 16 `web_sol_extension/` sources,
  `integrations/hermes_harness/` incl. `browser_plugin/`, `control_plane/`,
  `docs/`, `tests/`);
- `BUILD.json` — the manifest the installer wrote (commit + file→sha256 map);
- **generated per profile**: `chrome/<Profile-N>/bin/<host-id>` (the `sh`
  wrapper that `cd`s into the release root and execs the pinned python),
  `chrome/<Profile-N>/native-hosts/<host-id>.json`, and
  `chrome/<Profile-N>/extensions/<id24>/` (13 rendered files).

**Known gap (report, not fixed here):** `build_browser.py` hashes every tracked
file at HEAD with a 300-file cap; the repo has grown from 56 to ~10,300 tracked
files, so it refuses (`invalid source closure`). Until that is repaired, the
manifest is curated from the `OLD` BUILD.json: keep every path that still
exists, re-hashed at `$NEW`, drop paths that no longer exist
(`BROWSER_README.md`, `PROFILE_FLEET_PLAN.md`), add new browser tests. The
exact command is step 2 below and reproduces the used manifest bit-for-bit
(64 files, 10 changed hashes).

## Install steps — check after every step, roll back after every step

`NEW=e778e5658ba7ec9b3ea88223cf0e4d2658e92cbc`,
`BASE=~/.local/share/mastermind-browser-control`,
`MMX=~/.t3/mcp/mmx-browser`. The installer is run from the repo root checked
out at `$NEW` (it stages from the checkout; run it as a module, not a path).

0. **Preconditions.** The 0.6.0 staging exists at
   `~/Downloads/Mastermind-Browser-0.6.0/Chrome-chatgpt{1..4}` (done 2026-11-11).
   Pick a quiet window; see "Residual effects" before starting. Nothing below
   writes to a Chrome profile directory.
   Check: `shasum -a 256 ~/Downloads/Mastermind-Browser-0.6.0/Chrome-chatgpt1/browser_control.js`
   = `72a1ce524dfa0371…b58097`, `browser_page.js` = `49b6f21873e3d4ae…c6d41ead`.

1. **Stage the tree.** Check out `$NEW` in the work tree.
   Check: `git rev-parse HEAD` = `$NEW`; `shasum -a 256` of the three changed
   runtime files equals `ee7a84ac07da45184aa39458f75f0ba0ca5a2945c21581366054291dcd5a2f9b`
   (`web_sol_browser_protocol.py`), `4ff2113f4eebf9abbfc4aa847a1264f95e01d549459c9b08bae1d6a9460db67f`
   (`browser_bridge.py`), `08c4066074d7ac5cbc21943b8bdb4d33262b2291121c30ed493c60c8fd516edb`
   (`browser_tool_schema.json`). Rollback: nothing changed yet.

2. **Curate the build manifest** (until `build_browser.py`'s cap is repaired):

   ```bash
   python3 - <<'EOF'
   import json, hashlib, pathlib
   ROOT = pathlib.Path(".")                     # repo root at $NEW
   OLD = "5aa30969241163b4abb3e025bc9e52123ee4b478"
   NEW = "e778e5658ba7ec9b3ea88223cf0e4d2658e92cbc"
   BASE = pathlib.Path.home()/".local/share/mastermind-browser-control"
   old = json.load(open(BASE/f"releases/{OLD}/BUILD.json"))["files"]
   sha = lambda p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
   files = {p: sha(p) for p in old if (ROOT/p).exists()}
   files.update({p: sha(p) for p in [
       "tests/browser_editable_variants_playwright.cjs",
       "tests/browser_fill_bounds_playwright.cjs",
       "tests/browser_fill_fallback_truth_playwright.cjs",
       "tests/browser_fill_receipt_playwright.cjs",
       "tests/browser_fill_settle_playwright.cjs",
       "tests/browser_fill_structure_playwright.cjs",
       "tests/browser_page_registration.cjs",
       "tests/browser_paste_playwright.cjs",
       "tests/browser_read_paging_playwright.cjs",
       "tests/browser_settings_playwright.cjs"]})
   json.dump({"schema": "mastermind.browser.build.v1", "source_commit": NEW, "files": files},
             open(f"BUILD-{NEW[:8]}.json", "w"), indent=2, sort_keys=True)
   print(len(files), "files")
   EOF
   ```

   Check: `64 files`; the three step-1 hashes appear in it.
   Rollback: delete the file.

3. **Pre-update the four real staging folders** so the installer's
   prepared-extension guard passes. The live
   `~/Downloads/Mastermind-Browser-0.5.0/Chrome-chatgpt{1,2,3}` hold
   `fb74011a…/93bfeb4f…` (neither the new pair nor the `OLD` prior) and the
   installer refuses exactly that (`prepared extension changed`, rehearsed run
   B). Copy every file **except `instance_config.js`** from the matching 0.6.0
   folder over the 0.5.0 one, keeping a backup first:

   ```bash
   for p in chatgpt1 chatgpt2 chatgpt3 chatgpt4; do
     cp -R ~/Downloads/Mastermind-Browser-0.5.0/Chrome-$p \
           ~/Downloads/Mastermind-Browser-0.5.0/Chrome-$p.pre-release2
     for f in ~/Downloads/Mastermind-Browser-0.6.0/Chrome-$p/*; do
       b=$(basename "$f"); [ "$b" = instance_config.js ] && continue
       cp "$f" ~/Downloads/Mastermind-Browser-0.5.0/Chrome-$p/"$b"
     done
   done
   ```

   Check: chatgpt1–3 `browser_control.js` = `72a1ce52…`, chatgpt4 still
   `9117db2a…` (the `OLD` prior — the guard accepts it and the installer
   updates it in place). Rollback: `rm -rf` the four folders and `mv` the
   `.pre-release2` copies back.

4. **Run the installer.** This builds the full release folder and re-registers
   every profile's Chrome `NativeMessagingHosts` manifest into the new release
   root (inert until each profile's host respawns — see step 7):

   ```bash
   python3 -m integrations.hermes_harness.install_browser \
     --build-manifest BUILD-e778e5658.json \
     --install-base ~/.local/share/mastermind-browser-control \
     --python ~/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3.14 \
     --enrollment <enrollment.json> \
     --prior-source 5aa30969241163b4abb3e025bc9e52123ee4b478
   ```

   (`<enrollment.json>`: the current local enrollment — 6 local profiles, real
   `data_directory` values. Ask the lane for the copy used in the scratch
   rehearsal if unsure.) Check: stdout JSON `state` = `INSTALLED_PENDING_CHROME_LOAD`,
   `source_commit` = `$NEW`, all six `chrome[]` rows `ok: true`; the release
   folder holds ~155 files incl. `BUILD.json` and `chrome/<Profile-N>/`;
   `bin/<host-id>` scripts `cd` into `releases/$NEW`. Rollback: the installer
   keeps `.previous.<16hex>` backups beside what it replaced; restore them, or
   rerun with `--prior-source $NEW` after removing the new release folder —
   the `OLD` release directory itself is never modified.

5. **Create the versioned runtime folders; move registrations to `current`.**
   One-time migration, zero behavior change at this step:

   ```bash
   MMX=~/.t3/mcp/mmx-browser
   mkdir -p $MMX/runtimes/$OLD $MMX/runtimes/$NEW
   cp $MMX/server.js $MMX/runtimes/$OLD/server.js
   cp $MMX/server.js $MMX/runtimes/$NEW/server.js      # byte-identical, never edited
   cp $MMX/runtime.json $MMX/runtimes/$OLD/runtime.json  # verbatim live pin
   python3 - <<'EOF'
   import json, pathlib
   MMX = pathlib.Path.home()/".t3/mcp/mmx-browser"
   NEW = "e778e5658ba7ec9b3ea88223cf0e4d2658e92cbc"
   rt = json.load(open(MMX/"runtime.json"))
   rt["release_commit"] = NEW
   rt["source_root"] = str(pathlib.Path.home()/".local/share/mastermind-browser-control/releases"/NEW)
   pins = json.load(open("BUILD-e778e5658.json"))["files"]
   for f, h in pins.items():
       if f in rt["source_files"]: rt["source_files"][f] = h
   json.dump(rt, open(MMX/f"runtimes/{NEW}/runtime.json", "w"), indent=2)
   EOF
   ln -sfn $MMX/runtimes/$OLD $MMX/current   # current -> OLD first: no behavior change yet
   ```

   Then edit `mcpServers.mmx-browser.args` in each of the four provider homes
   (`~/.t3/providers/{experiential-claude,fabric-experiential,fabric-unified-router,fabric-anthropic-oauth}/.claude.json`,
   backup each first) from `…/mmx-browser/server.js` to
   `…/mmx-browser/current/server.js`.
   Check: `readlink $MMX/current` ends `/runtimes/$OLD`; each `.claude.json`
   parses and its last arg is `current/server.js`; a fresh probe now
   (read-only `browsers` without probe) still shows `bridge_release_commit`
   `5aa309692…`. Rollback: restore the four `.claude.json` backups, delete
   `runtimes/` and `current`. Running sessions are untouched either way — they
   already hold their resolved `server.js`.

6. **Switch the pin.** Atomic repoint, seconds after step 5:

   ```python
   import os, pathlib
   MMX = pathlib.Path.home()/".t3/mcp/mmx-browser"
   NEW = "e778e5658ba7ec9b3ea88223cf0e4d2658e92cbc"
   tmp = MMX/"current.tmp"
   if tmp.is_symlink() or tmp.exists(): tmp.unlink()
   tmp.symlink_to(MMX/f"runtimes/{NEW}")
   os.replace(tmp, MMX/"current")   # atomic; no running server is disturbed
   ```

   Check: a fresh probe shows `bridge_release_commit` `e778e5658…` and the
   actions enum has `read` (44 actions). Servers already running on the old pin
   keep working — rehearsed: same server, 5× CONNECTED before and after the
   repoint. Rollback: the same `os.replace` snippet pointed back at
   `runtimes/$OLD`.

7. **Operator extension reloads** (human/operator action per profile:
   ChatGPT1-4 and personal-default; `mastermindx` has a pre-existing
   `PROFILE_IDENTITY_MISMATCH` unrelated to this release). Reloading the
   extension drops the native-host connection; Chrome re-reads the
   `NativeMessagingHosts` manifest — now pointing into `releases/$NEW` — and
   spawns a **new-code host** whose digest equals the new client's
   (`1c40ec98…`, computed from the built release root in rehearsal). The
   loaded extension version string stays `0.4.1` (the release process does not
   bump the manifest); the observable change is the `read` action.
   Rollback: point `current` back (step 6), then reload extensions from the
   `Chrome-$p.pre-release2` staging copies; or rerun the installer with the
   roles reversed. The `OLD` release root still exists throughout.

8. **Verify in a fresh session** (read-only):
   - `browsers` with `probe: true`: the five local profiles `CONNECTED`
     (digest equality is the handshake gate — proven by the control matrix),
     `bridge_release_commit` `e778e5658…`;
   - actions enum: 44 entries incl. `read`;
   - `status` shows the new commit.
   Rollback: steps 6→5→4 in reverse order.

## Residual effects (honest)

- Sessions whose server was spawned **before** step 6 keep the old pin. After
  step 7 flips a profile's host, such a session's browser-transport calls
  against that profile return `TRANSPORT_HANDSHAKE_FAILED` rows (symmetric to
  the first attempt's cause) until the session restarts and re-resolves
  `current`. Bounded: no `NATIVE_SOURCE_CLOSURE_STALE` (no pinned file ever
  changes under a running server), non-transport answers still work, and a
  refusal sends nothing to any page. Schedule the window accordingly.
- `mastermindx` stays `PROFILE_IDENTITY_MISMATCH` as it is today.
- The extension manifest version intentionally stays `0.4.1`.

## Rehearsal record (scratch `~/.mastermind/mmos_dev/br/release2/`)

| what | result | log |
|---|---|---|
| baseline installer run (fresh staging) | `INSTALLED_PENDING_CHROME_LOAD`, 6/6 rows ok, ~155-file release built | `logs/installer_runA…` |
| drifted staging (real bytes mirrored) | guard refused `prepared extension changed: …Chrome-chatgpt1/browser_control.js` | `logs/installer_runB_refusal.txt` |
| staging pre-updated from 0.6.0, rerun | 6/6 ok, staging at new bytes | `logs/installer_runC.json` |
| release structure | BUILD.json (64 files), chrome trees, bin + native-host manifests all inside scratch root | `logs/release_structure.txt` |
| host digest from built release | `1c40ec98…` = new client digest; live OLD root `e0216d3d…` (40 actions) | `logs/digest_proof.txt` |
| switch matrix | old session 5× CONNECTED across `current` repoint; new session 44 actions/`read`; control 5× CONNECTED | `logs/rehearsal_switch.log` |
| server on installer-built release | 44 actions, `read` present, `bridge_release_commit e778e5658…` | `logs/probe_full_release.txt` |

Scratch boundary: no Chrome instance runs on the scratch instance ids (they
hash the redirected `data_directory`), so the scratch probe ends at
`CHROME_LOAD_REQUIRED` rather than 5× CONNECTED; the 5× CONNECTED side is
proven live by the control matrix (digest-equal ⇒ connected against today's
extension), and the digest equality of the built release is proven by
computation. The full 5× CONNECTED on the new commit is step 8 on the real
machine.

## Operator call: paged whole-answer read (unchanged)

Tool `mmx_browser` (T3: `mcp__mmx-browser__mmx_browser`). First call (after
`snapshot` gives `snapshot_id` and the element `ref`):

```json
{"action":"read","browser_id":"<browsers>","connection_id":"<status>",
 "tab_id":0,"url_fingerprint":"<tabs>","snapshot_id":"<snapshot>","ref":"<element ref>","offset":0}
```

Loop while `next_offset` is not null, repeating with `offset` set to it; every
other argument identical. The reply carries `content` (always untrusted text),
`total_characters`, `next_offset` (null at the end) and
`content_is_untrusted: true`. Reads never consume the snapshot, mutate,
scroll or focus. Invalid offsets return `READ_OFFSET_INVALID`; a wrong
argument shape returns `INPUT_REFUSED`. Read-contract limits: no drift guard
across pages; repeated blank lines can hide a dropped empty line; for fills,
read the box before sending — `APPLIED` means the box held the asked content
at the re-read after pending microtasks plus one settle interval (250 ms in
this build); `settle_interval_ms` is a floor, not a ceiling (hidden tabs
settle later — do not timeout-and-retry a fill that may have applied).

## Rollback target

`5aa30969241163b4abb3e025bc9e52123ee4b478` — its release directory is never
modified by any step; step 6's repoint plus step 7's reload-from-backup
returns every session to it. Lane BR wrote nothing under
`~/.local/share/mastermind-browser-control`, `~/.t3`, `~/Library/Application Support/Google/Chrome`
or any provider home; every step above is the principal's.
