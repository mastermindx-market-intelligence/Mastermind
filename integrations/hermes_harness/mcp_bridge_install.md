# Bridge release install runbook (release 3, compat admission) — mmx-browser MCP server

Build/checkout commit `NEW = 8eb080b55bcb08a67b83ecca319288fb8168912b` on branch
`t3/mmos-v4-br`, rollback release `OLD = 5aa30969241163b4abb3e025bc9e52123ee4b478`
throughout. This runbook's own commits may sit atop `NEW`. The BR-COMPATFIX
(ruling-15) commits DO touch closure files (`install_browser.py`,
`tests/test_browser_profiles_fleet.py`) and add `runtime_pin.py`, so an install
run from that branch head re-curates step 1's manifest at its own head and the
installed `release_commit` is that head, not `8eb080b5`. That does not move the
transport compatibility constants: the fix touches no protocol source, so the
three step-1 runtime hashes and `EXPECTED_CAPABILITY_DIGEST = "1c40ec98…"` hold
unchanged at the branch head, and the compat admission window is identical. The
same text is mirrored at `~/.mastermind/mmos_evidence/br-20261111/brcompat/`.

The first install attempt (2026-11-12) followed a 15-file copy procedure and
**failed at step 5 with every local profile TRANSPORT_HANDSHAKE_FAILED**; it was
rolled back and `OLD` is live again, byte-identical. Release 2's runbook
(`50bc52459..81aee45fb`) diagnosed both causes; release 3 adds the compatibility
admission that removes its residual breakage window and reorders the steps so
**no moment of the install makes any running session fail** (ruling 16: a method
that makes running sessions fail is not installed while other programmes have
operators at work). Every step below was rehearsed end to end in scratch
(`~/.mastermind/mmos_dev/br/compat/`, logs under `logs/`); see "Rehearsal
record".

## Why the first attempt failed (proven, not inferred)

`transport_capability_digest()` (`integrations/chairman_surfaces/web_sol_protocol.py`)
hashes the document that includes `"browser_actions": sorted(browser.ACTIONS)`.
This release adds the `read` action, so:

- a client (bridge) at `NEW` computes digest
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
which the client reports as `transport_handshake_failed`. Proofs from the
release-2 rehearsal remain in force (digests computed from both release roots;
live A/B/C switch matrix reproducing the 5× TRANSPORT_HANDSHAKE_FAILED and the
digest-equal control that showed 5× CONNECTED). The 175-vs-15 file count was
**not** the cause; a full closure built by the installer is used anyway.

## What release 3 changes: previous-release admission and per-connection action sets

The host no longer admits exactly one digest. It admits **exactly two**: its
own and the immediately previous release's, as a named constant next to the
commit it belongs to (`PREVIOUS_TRANSPORT_CAPABILITY_DIGEST` =
`e0216d3d…`, `PREVIOUS_TRANSPORT_CAPABILITY_RELEASE_COMMIT` = `5aa30969…` in
`web_sol_protocol.py`; no wildcard, no "any older" — any third digest is
refused at the handshake, and a foreign extension presenting one exits 65).

A connection admitted on the old digest is **held by the host to the old action
set** (`web_sol_browser_protocol.PREVIOUS_ACTIONS`, the 40 old actions —
everything except `read`). A request for an action outside the set the
connection presented — whatever the client sends — is answered with an explicit
`ACTION_UNAVAILABLE / NOT_APPLIED` receipt carrying
`reason: transport_capability_mismatch` and is never forwarded to the extension.
The extension end is held the same way: the host captures the extension's own
handshake digest and refuses to forward an action the running extension cannot
execute. So a fleet mixed across the two releases can never dispatch an action
one side of the connection cannot execute, and no refusal breaks a connection —
the next old action on a fresh connection still works.

The old client is unmodified and stays unmodified: the transport ack
(`build_transport_hello_ack`) preserves every peer hello field, so the ack
**echoes the digest the peer presented**. The old client's own check
(`_accepted_transport_ack`: the ack's `capability_digest` must equal the
client's own computed digest) passes against the new host's answer. This was
proven at protocol level against the real `OLD` release modules — no stand-in
client — plus a raw hand-built connection presenting the old digest and asking
for `read`, and a third digest refused at the handshake (rehearsal record,
`logs/compat_proof.txt`).

## What Chrome reads from disk after load, and the staging method

An unpacked extension is **not** a snapshot: Chrome keeps reading the loaded
folder's bytes after installation.

- `background.js` is an MV3 service worker. Chrome suspends and kills it on
  idle and re-runs it on every wake; each wake re-executes its
  `importScripts("instance_config.js", "census_core.js", "browser_cdp.js",
  "browser_control.js")` **from disk**.
- `content.js` is declared in `manifest.json` `content_scripts`; Chrome reads it
  from disk at **every injection** (each navigation of a matched page).
- `browser_page.js` is injected on demand via
  `chrome.scripting.executeScript({files:["browser_page.js"]})` — read from
  disk **per action**.
- `browser.html` (options) and `census.html` (popup) load their scripts from
  disk when opened.

So copying new bytes into a folder Chrome has already loaded takes effect with
no person acting: the next service-worker wake runs new worker code, the next
navigation injects a new page script, and between the copy and a deliberate
reload a profile can momentarily mix an old worker closure with new page bytes
(old worker answers a probe while a newly-injected `browser_page.js` runs new
code, or the reverse). That is why release 2's step "pre-update the staging
folders" is **deleted**: it copied new bytes into the loaded
`~/Downloads/Mastermind-Browser-0.5.0/Chrome-*` folders and left the mix to
chance until each reload.

The method instead: **the bytes of a folder Chrome has already loaded are never
changed by any step.** The installer stages each profile's render into a
**fresh per-release staging root** (`--staging-root
~/Downloads/Mastermind-Browser-0.6.0-8eb080b5/Chrome-<alias>`, created by the
installer; it must not be a folder any Chrome has loaded), and its default
`update_loaded=False` skips the loaded-folder rewrite entirely (the rewrite
exists only behind an explicit `--update-loaded` flag for a requested in-place
update). The profile is moved to the new bytes only by the operator's step 2
below: remove the extension and Load unpacked from the new staging folder.

What that does to identities: nothing. The extension id
`kmpbpccecbofdnhpcmjogofgmdodpnko` is derived from `manifest.json`'s `"key"`
(not from the folder path), so loading from a different folder keeps the id,
and the native hosts' manifests' `allowed_origins`
(`chrome-extension://kmpbpccecbofdnhpcmjogofgmdodpnko/`) stay valid with no
registration change. The extension uses no `chrome.storage`, so remove+load
loses no extension state.

## Why "no daemon restart needed" was wrong, and the versioned-runtimes fix

`server.js` captures `runtime.json`'s bytes at startup and re-verifies them
before **every dispatch**. Editing the live
`~/.t3/mcp/mmx-browser/runtime.json` in place makes every already-running
server answer `REFUSED / NATIVE_SOURCE_CLOSURE_STALE` (retry not allowed) until
its session restarts — during the first attempt that hit 31 running servers.

Therefore: **never edit the live `runtime.json`.** This runbook switches
releases with versioned runtime folders plus a `current` symlink; `server.js`
is byte-identical everywhere and no pinned file ever changes under a running
server. Rehearsal proved a server started through `current/` keeps answering,
on its original commit, across a symlink repoint, while the next server spawned
through `current/` resolves the new release (`logs/rehearsal_switch.log`).

## What a release folder must contain and how it is built

A release root (`~/.local/share/mastermind-browser-control/releases/<commit>/`)
built by `integrations/hermes_harness/install_browser.py` holds ~155 files:

- the **pinned source closure** from the build manifest (65 files at this head:
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
(`BROWSER_README.md`, `PROFILE_FLEET_PLAN.md`), add the new browser tests. The
exact command is step 1 below and reproduces the used manifest bit-for-bit
(65 files).

## Install steps — order matters: build, reload, switch the pin LAST

`BASE=~/.local/share/mastermind-browser-control`,
`STAGING=~/Downloads/Mastermind-Browser-0.6.0-8eb080b5`,
`MMX=~/.t3/mcp/mmx-browser`. The installer is run from the repo root checked
out at `$NEW` (it stages from the checkout; run it as a module, not a path).
Check after every step; every step has a rollback.

0. **Preconditions.** Pick a quiet window. Nothing below writes to a Chrome
   profile directory or to any extension folder a Chrome has loaded. Verify
   `readlink`-free cleanliness: `STAGING` must not exist yet (the installer
   creates it; if a previous attempt left one, move it aside — the prepared
   guard refuses changed bytes in an existing folder, which is the guard
   working). The enrollment file from release 2
   (`~/.mastermind/mmos_evidence/br-20261111/release2/enrollment.json`,
   sha256 `5cef20bf0382127876667cbac4021fc2064dc86394b6346faffc619a5ccf177a`)
   must still match the live `deployments-v2.json` rows (6 local profiles, 2
   ssh hosts); re-derive it if rows changed.

1. **Stage the tree and curate the build manifest** (until `build_browser.py`'s
   cap is repaired). Check out `$NEW` in the work tree.
   Check: `git rev-parse HEAD` = `$NEW`; `shasum -a 256` of the changed runtime
   files equals `7e801a71ad620688096a636754550ed72cfc1da5b367e933d4d83e43056ddb97`
   (`web_sol_browser_protocol.py`),
   `f1d78a60343c113ea01fef399ec93cd0b6da461c7b944bf932524cc4f4788d18`
   (`browser_bridge.py`),
   `c34bf7a30383a6eab3079259e6d9333d4dc8be179565b7a104d86860308cdf55`
   (`browser_tool_schema.json`); `background.js` pins
   `EXPECTED_CAPABILITY_DIGEST = "1c40ec98…b6f60d40"`. Then:

   ```bash
   python3 - <<'EOF'
   import json, hashlib, pathlib
   ROOT = pathlib.Path(".")                     # repo root at $NEW
   OLD = "5aa30969241163b4abb3e025bc9e52123ee4b478"
   NEW = "8eb080b55bcb08a67b83ecca319288fb8168912b"
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
       "tests/browser_settings_playwright.cjs",
       "tests/test_web_sol_transport_compat.py"]})
   json.dump({"schema": "mastermind.browser_direct_build.v1", "source_commit": NEW, "files": files},
             open("BUILD-8eb080b5.json", "w"), indent=2, sort_keys=True)
   print(len(files), "files")
   EOF
   ```

   The schema string must be exactly `mastermind.browser_direct_build.v1`
   (`install_browser.py` refuses anything else) and the filename must be
   `BUILD-8eb080b5.json` — step 2 reads that exact name.
   Check: `65 files`; the three hashes above appear in it.
   Rollback: `git checkout` back, delete the file. Nothing else changed.

2. **Build the release and register the hosts** (the installer). This builds
   the full release folder, stages every profile's render under `STAGING`, and
   re-registers every profile's Chrome `NativeMessagingHosts` manifest into the
   new release root. From this moment any host respawn runs new host code —
   which is safe at every moment below precisely because the new host admits
   the previous release's digest (compat admission, proven in rehearsal):

   ```bash
   python3 -m integrations.hermes_harness.install_browser \
     --build-manifest BUILD-8eb080b5.json \
     --install-base ~/.local/share/mastermind-browser-control \
     --python ~/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3.14 \
     --enrollment ~/.mastermind/mmos_evidence/br-20261111/release2/enrollment.json \
     --staging-root ~/Downloads/Mastermind-Browser-0.6.0-8eb080b5 \
     --prior-source 5aa30969241163b4abb3e025bc9e52123ee4b478
   ```

   `--staging-root` names the fresh per-release staging tree; without
   `--update-loaded` (default) the installer never rewrites a folder Chrome
   has loaded. The enrollment keys must be exactly
   `{host_ref, label, profiles, remote_hosts, remote_profiles}`.
   Check: stdout JSON `state` = `INSTALLED_PENDING_CHROME_LOAD`,
   `source_commit` = `$NEW`, all six `chrome[]` rows `ok: true`, every
   loaded row `activation: CHROME_RELOAD_REQUIRED`; the release folder holds
   ~155 files incl. `BUILD.json`; `bin/<host-id>` scripts `cd` into
   `releases/$NEW`; `STAGING/Chrome-<alias>/instance_config.js` carries
   digest `1c40ec98…`; the loaded `0.5.0` folders are byte-identical to
   before the run (`shasum -a 256` a folder before and after).
   Rollback (complete undo — the installer cannot rebuild `OLD` from a `$NEW`
   checkout, so do not rerun it with `--prior-source $NEW`): for every
   `.previous.<16hex>` file the installer left under `BASE` and under
   `~/Library/Application Support/Google/Chrome/NativeMessagingHosts`, move it
   back over the file it backs up; then delete the new-only files:
   `releases/$NEW/`, `installation-$NEW.json`, `packages/$NEW/`, `STAGING/`.
   Restore `deployments-v2.json` from its own `.previous` backup the same way.
   The `OLD` release directory is never modified by any step.

3. **Operator extension reloads, profile by profile** (human/operator action;
   ChatGPT1-4 and personal-default; `mastermindx` has a pre-existing
   `PROFILE_IDENTITY_MISMATCH` unrelated to this release). **⟳ alone is not
   enough** — it re-reads the *old loaded folder*, whose bytes step 2
   deliberately never changed. For each profile, in `chrome://extensions`:
   remove the Mastermind extension, then Load unpacked from
   `STAGING/Chrome-<alias>`. The id and `allowed_origins` are unchanged (the
   manifest `key` derives the id), no `chrome.storage` state exists to lose,
   and the removal drops the native-host connection so Chrome re-reads the
   `NativeMessagingHosts` manifest — now pointing into `releases/$NEW` — and
   spawns a new-code host. One profile at a time, confirming the previous one
   still answers (its next browser call) before moving on. Do all five; the
   loaded version string stays `0.4.1` — the observable change is the `read`
   action. Every session, old-pin or new-pin, keeps working across each reload
   (window table below; proven rows in `logs/compat_proof.txt` S1/S2).
   Check per profile: reload done, `STAGING` folder is the loaded one.
   Rollback: repoint nothing yet — reload the profile back from its untouched
   `~/Downloads/Mastermind-Browser-0.5.0/Chrome-<alias>` folder (those bytes
   were never changed by any step, so they are today's working state).

4. **Switch the pin — LAST.** By now every profile runs the new extension and
   a new-code host, and every session in the fleet still holds the old pin and
   works. The pin writer is `integrations/hermes_harness/runtime_pin.py` —
   guarded: no default root (`--mmx-root` is required), it never edits the
   flat live pin files, never writes inside the folder `current` resolves to,
   never overwrites a delivered `runtimes/<commit>` (ruling 19: a delivery
   mark is permanent), and switches only by atomic symlink replace. Run from
   the repo root. First the one-time migration to versioned runtimes (zero
   behavior change; `current` → `OLD`):

   ```bash
   MMX=~/.t3/mcp/mmx-browser
   OLD=5aa30969241163b4abb3e025bc9e52123ee4b478
   NEW=8eb080b55bcb08a67b83ecca319288fb8168912b
   python3 -m integrations.hermes_harness.runtime_pin migrate \
     --mmx-root $MMX --old-commit $OLD --new-commit $NEW \
     --build-manifest BUILD-8eb080b5.json \
     --new-source-root ~/.local/share/mastermind-browser-control/releases/$NEW
   ```

   It delivers `runtimes/$OLD` (the verbatim flat pin plus a byte-identical
   `server.js` copy) and `runtimes/$NEW` (the pin updated to the new commit,
   the new source root, and the closure hashes `BUILD-8eb080b5.json` pins),
   then points `current` at `OLD` atomically. The flat `$MMX/runtime.json`
   and `$MMX/server.js` are never edited, so every running server — which
   captured the flat pin at startup and re-verifies it before each dispatch —
   is untouched. If installing from the compatfix branch head, `$NEW`, the
   manifest filename and `--new-source-root` are that head's values instead.
   Check: stdout JSON `state` = `PIN_MIGRATED`; `readlink $MMX/current` ends
   `/runtimes/$OLD`; the flat pin files are byte-identical before/after;
   every `runtimes/*/runtime.json` is mode `0600` (server.js refuses
   group/world-writable pins with `NATIVE_SOURCE_UNSAFE`).

   Then switch the registered server path — do NOT hand-edit these files.
   Running sessions rewrite `.claude.json`, so a hand edit can lose a race
   either way; no source writer ever registered mmx-browser there. Use the
   guarded command: it checks all four provider homes
   (`experiential-claude`, `fabric-experiential`, `fabric-unified-router`,
   `fabric-anthropic-oauth`) BEFORE the first write — each
   `mcpServers.mmx-browser.args` must end exactly at the old flat
   `$MMX/server.js`, and the JSON-encoded old path must occur exactly once
   in each file's raw bytes (zero or several occurrences refuse the whole
   run as `OLD_VALUE_NOT_UNIQUE` before any write, in any home). The change
   itself is a raw-byte replacement of that one span: the file is never
   re-serialised, so key order, non-ASCII text, float spellings, the
   trailing-newline state and the file mode survive byte for byte, and the
   replaced bytes must re-parse to exactly the intended one-value change.
   Writes go through the owned CAS writer, so a file changed since its check
   refuses alone (`WRITE_RACE`, keeping the session's bytes, leaving no
   backup) and every landed write leaves a `.claude.json.previous.<16hex>`
   backup; a write error that is not a digest mismatch is reported as what
   it is (`WRITE_FAILED` with the errno name), never as a race.
   After a short wait it reads every switched file back, so a session that
   rewrote a file is reported (`READBACK_RACE_*`), not silently believed. It
   prints home names and status codes only — never contents. The written arg
   is the literal `$MMX/current/server.js` symlink path, so later migrations
   only re-point `current` and never touch these files again. The fifth home
   (`fabric-unified-router-worker`) carries no entry and is never written; an
   entry there refuses the whole run.

   ```bash
   python3 -m integrations.hermes_harness.mmx_provider_registration \
     --providers-root ~/.t3/providers --mmx-root $MMX
   ```

   Check: stdout JSON `state` = `PROVIDER_ARGS_SWITCHED`, one row per home
   (`SWITCHED`, or `ALREADY_SWITCHED` on a re-run — already-switched homes
   are no-ops, so one re-run after a race is safe: a `WRITE_RACE` or
   `WRITE_FAILED` home kept the session's bytes and has no backup, the
   other homes stay switched, and the re-run skips those as
   `ALREADY_SWITCHED` while it switches only the failed home). Each
   `.claude.json` parses and its last arg is `current/server.js`; a fresh
   session's read-only `browsers` (no probe) still shows
   `bridge_release_commit` `5aa309692…`. If `state` =
   `PROVIDER_ARGS_SWITCHED_WITH_RACES`, or the command refuses (it names
   the home and a code), re-run ONCE when the racing session is idle — do
   not loop; a refusal means the files are not in the expected state and
   must be diagnosed, not retried blindly.
   Then the atomic repoint:

   ```bash
   python3 -m integrations.hermes_harness.runtime_pin switch --mmx-root $MMX --commit $NEW
   ```

   Check: stdout `state` = `PIN_SWITCHED`; a fresh session shows
   `bridge_release_commit` `8eb080b5…` and the actions enum has `read`
   (44 actions); the old sessions keep answering on `5aa309692…` —
   rehearsed: same server, same commit and action set before and after the
   repoint (`logs/rehearsal_switch.log`).
   Rollback: the same `switch` command with `--commit $OLD` — one atomic
   repoint, no rewrite. To undo the whole migration instead: restore the
   four `.claude.json.previous.<16hex>` backups the guarded switch left (one
   per provider home) so spawns use the flat `$MMX/server.js` again, and
   LEAVE `runtimes/` and `current` in place — deleting them would break any
   server spawned via `current/server.js`, which re-verifies `runtime.json`
   from its own folder on every dispatch. Running sessions are untouched
   either way.

5. **Verify in a fresh session** (read-only):
   - `browsers` with `probe: true`: the five local profiles `CONNECTED`,
     `bridge_release_commit` `8eb080b5…`;
   - actions enum: 44 entries incl. `read`;
   - `status` shows the new commit;
   - one old session (started before step 4, if any is handy) still answers
     `browsers`/`status` on the old commit — its `read` is absent, which is
     correct for its pin.
   Rollback: steps 4 → 3 → 2 in reverse order.

## Rollback window

Per step: what is actually live once the step is done, how to undo exactly
that step, and until when that undo is the right one (MED-2: a bare pin
rollback with no procedure strands every profile reloaded at step 3 — after
the reload those extensions present the NEW digest, and the OLD host is
single-digest-strict, so the truthful rollback names the reverse reload and
the order). Roll back in reverse step order; the OLD release directory and
the old loaded `0.5.0` folders are never modified by any step, so the bytes
every undo needs always exist.

| Step | What is live | How to undo | Until when |
| --- | --- | --- | --- |
| 1 | Nothing runtime-side: only the curated `BUILD-*.json` in the checkout; the OLD release, OLD pin and all loaded folders are untouched. | Delete the curated `BUILD-*.json`; `git checkout` the work tree back. No installed state exists yet. | Until step 2 consumes the manifest; after step 2, undo step 2 first. |
| 2 | New release root under `BASE`; every profile's `NativeMessagingHosts` manifest points into `releases/$NEW`, so any host respawn runs new-code (it admits the OLD digest); loaded extension folders are byte-identical; running sessions and old hosts are unchanged. | Restore every `.previous.<16hex>` backup the installer left under `BASE` and under `~/Library/Application Support/Google/Chrome/NativeMessagingHosts` (including `deployments-v2.json`'s own `.previous`), then delete the new-only files: `releases/$NEW/`, `installation-$NEW.json`, `packages/$NEW/`, `STAGING/`. | Only while no profile has been reloaded at step 3. After any step-3 reload, undo step 3 first (reverse reload): restoring the OLD host manifests under a profile running the NEW extension makes the OLD single-digest host refuse its handshake. |
| 3 | Per reloaded profile: NEW extension bytes plus a new-code host; the profile answers old-pin and new-pin sessions alike (compat admission). Not-yet-reloaded profiles are fully old. Every session keeps working throughout. | The reverse reload: in `chrome://extensions` remove the extension and Load unpacked from its untouched `~/Downloads/Mastermind-Browser-0.5.0/Chrome-<alias>` folder — those bytes were never changed by any step, so they are the working state. | Valid at any later point (the NEW host admits the OLD digest, and after a step-4 rollback the OLD host matches the old extension again); in a full rollback do it after undoing step 4 so the fleet stays uniform. |
| 4 | New spawns resolve `current` → `runtimes/$NEW` (new commit, `read` present); providers' `.claude.json` args point at `current/server.js`; every running session keeps its already-resolved OLD files and answers unchanged. | The same atomic repoint back: `runtime_pin switch --mmx-root $MMX --commit $OLD`. To undo the whole migration instead, restore the four `.claude.json.previous.<16hex>` backups the guarded switch left (one per provider home) and LEAVE `runtimes/` and `current` in place — deleting them breaks servers spawned via `current/server.js`, which re-verify their folder's `runtime.json` on every dispatch. | Until step 5 verifies and the fleet has run the release; once the NEXT release replaces the compat-admission window (it admits only one previous digest), `$OLD` is no longer a rollback target and the reverse reload of step 3 must target that release's OLD folders instead. |
| 5 | Everything: all five profiles reloaded, all new spawns on the NEW pin, old sessions draining on their resolved OLD files. | Nothing to undo — step 5 is read-only verification. On a failed check, roll back 4 → 3 → 2 in reverse order as above. | End of the install sitting; afterwards the window table above is history and the next release owns rollback. |

## The window table (every cell works; `read` appears only where both ends describe it)

"Old-pin session" = any session whose server resolved `current` (or the direct
path) before step 4's repoint; "new-pin session" = a session whose server
spawned after it. "Reloaded profile" = step 3 has moved that profile to the new
extension folder and a new-code host; "not-yet-reloaded" = step 3 has not
reached it. `read` absent means exactly that: old actions all work, the `read`
action does not exist for that session (it never asks for it).

| Moment | Session pin | Reloaded profile | Not-yet-reloaded profile |
|---|---|---|---|
| after step 2 (build+register) | old | — | works; host is old-code while alive, new-code on respawn — either admits the old digest; `read` absent |
| during step 3, per profile done | old | works (new extension + new-code host, old client admitted on the previous digest); `read` absent | works as the row above |
| after step 3, before step 4 | old | works; `read` absent | none left — step 3 does all five |
| after step 4 repoint | old | works, unchanged; `read` absent | none (by the step 3 gate) |
| after step 4 repoint | new | works; `read` admitted and executed | none (by the step 3 gate) |
| step 5 verify | old / new | works / works + `read` | none |

Two invariants make the empty cells structural, not luck: (a) the pin switch
is last, so no new-pin session exists while any profile is still on the old
extension; (b) step 3 completes every profile before step 4, so no new client
can ever meet a live old-code host process (the one combination the old host
refuses, having no compat admission). If a profile is skipped in step 3, stop
before step 4 and finish its reload. A session spawned at *any* moment
resolves the pin that `current` held at its spawn — old pin until step 4, new
after — and every row above holds for it.

## Residual effects (honest)

- Old-pin sessions keep the old action set until they restart; their `read` is
  refused with `ACTION_UNAVAILABLE` (never a handshake failure, never a broken
  connection). A restart moves them to the new pin.
- A third digest (anything but the current and previous release's) is refused
  at the handshake, and an extension presenting one exits 65 — by design.
- `mastermindx` stays `PROFILE_IDENTITY_MISMATCH` as it is today.
- The extension manifest version intentionally stays `0.4.1`.

## Rehearsal record (scratch `~/.mastermind/mmos_dev/br/compat/`)

| what | result | log |
|---|---|---|
| installer at `$NEW` (fresh staging root, second hop from the 36691feb9 scratch release) | `INSTALLED_PENDING_CHROME_LOAD`, 6/6 rows ok, ~155-file release, all six native manifests into `releases/$NEW` with unchanged `allowed_origins` | `logs/installer_h1.txt` |
| loaded folders untouched | every file under the loaded 0.5.0 staging byte-identical before/after the installer run | `logs/loaded_before_h1.txt` = `logs/loaded_after_h1.txt` |
| S1 pre-reload window (extension on previous digest, host from built release) | real `OLD`-release client: `status`/`tabs` OK; new client: old actions OK, `read` → `ACTION_UNAVAILABLE/NOT_APPLIED`; raw old-digest connection sending `read` refused, extension never sees it | `logs/compat_proof.txt` |
| S2 post-reload window (extension on current digest) | real `OLD`-release client still OK (the compat core); new client `read` OK/APPLIED and forwarded; third digest refused at the handshake | `logs/compat_proof.txt` |
| S3 foreign extension | wrapper presenting a third digest exits 65 | `logs/compat_proof.txt` |
| pin-switch rehearsal | server on `current`→OLD: 43 actions, no `read`, commit `5aa309692…`, identical after the atomic repoint; next server via `current`: 44 actions incl. `read`, commit `8eb080b5…` | `logs/rehearsal_switch.log` |

Scratch boundary: no Chrome instance runs on the scratch instance ids, so the
reload journey (remove + Load unpacked) and step 5's five-profile `CONNECTED`
proof are the operator's on the real machine; the transport rows those steps
rely on are proven at protocol level against the built release's real host
wrapper (`compat_proof.txt`) and the digest equality of the built release is
proven by computation. No transport probe, extension reload or host restart
was performed against any real profile during rehearsal.

## Operator call: paged whole-answer read (unchanged)

Tool `mmx_browser` (T3: `mcp__mmx-browser__mmx_browser`). First call (after
`snapshot` gives `snapshot_id` and the element `ref`):

```json
{"action":"read","browser_id":"<browsers>","connection_id":"<status>",
 "tab_id":0,"url_fingerprint":"<tabs>","snapshot_id":"<snapshot>","ref":"<element ref>","offset":0}
```

Loop while `next_offset` is not null, repeating with `offset` set to it; every
other argument identical — never skip or repeat a page (a skipped or repeated
page silently corrupts the transcript; there is no drift guard across pages).
The reply carries `content` (always untrusted text), `total_characters`,
`next_offset` (null at the end) and `content_is_untrusted: true`. Reads never
consume the snapshot, mutate, scroll or focus. Invalid offsets return
`READ_OFFSET_INVALID`; a wrong argument shape returns `INPUT_REFUSED`.
Read-contract limits: the worker enforces an 800,000-byte `RESULT_TOO_LARGE`
and the native host a 921,600-byte `MAX_MESSAGE_BYTES`; repeated blank lines
can hide a dropped empty line; for fills, read the box before sending —
`APPLIED` means the box held the asked content at the re-read after pending
microtasks plus one settle interval (250 ms in this build); `settle_interval_ms`
is a floor, not a ceiling (hidden tabs settle later — do not timeout-and-retry
a fill that may have applied).

## Rollback target

`5aa30969241163b4abb3e025bc9e52123ee4b478` — its release directory is never
modified by any step; step 4's repoint back plus step 3's reload from the
untouched `0.5.0` folders returns every profile and session to it. Lane BR
wrote nothing under `~/.local/share/mastermind-browser-control`, `~/.t3`,
`~/Library/Application Support/Google/Chrome`, any Chrome folder or any
provider home; every step above is the principal's.
